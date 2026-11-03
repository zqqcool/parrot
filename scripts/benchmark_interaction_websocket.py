from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import cast

import websockets
from websockets.typing import Origin, Subprotocol

_TERMINAL_EVENTS = frozenset({"ai.output.completed", "ai.output.failed", "ai.output.cancelled"})


@dataclass(frozen=True)
class Sample:
    interaction_id: str
    terminal_event: str
    accepted_ms: float
    first_delta_ms: float | None
    completed_ms: float


async def run_sample(
    url: str, origin: str, prompt: str, label: str, timeout_seconds: float
) -> Sample:
    async with websockets.connect(
        url,
        origin=Origin(origin),
        subprotocols=[Subprotocol("parrot.im.v1")],
        open_timeout=min(timeout_seconds, 15),
    ) as socket:
        ready = _object(await asyncio.wait_for(socket.recv(), timeout=timeout_seconds))
        if ready.get("type") != "connection.ready":
            raise RuntimeError("WebSocket did not send connection.ready")
        token = uuid.uuid4().hex
        await socket.send(
            json.dumps(
                {
                    "version": "1",
                    "type": "interaction.create",
                    "message_id": f"msg_benchmark_{label}_{token}",
                    "request_id": f"req_benchmark_{label}_{token}",
                    "interaction_id": None,
                    "sequence": 0,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "data": {"text": prompt},
                },
                ensure_ascii=False,
            )
        )
        return await _collect_sample(socket, time.perf_counter(), timeout_seconds)


async def _collect_sample(
    socket: websockets.ClientConnection, started_at: float, timeout_seconds: float
) -> Sample:
    interaction_id = ""
    accepted_ms: float | None = None
    first_delta_ms: float | None = None
    while True:
        event = _object(await asyncio.wait_for(socket.recv(), timeout=timeout_seconds))
        elapsed_ms = round((time.perf_counter() - started_at) * 1_000, 3)
        event_type = event.get("type")
        if event_type == "interaction.accepted":
            interaction_id = _text(event.get("interaction_id"), "interaction_id")
            accepted_ms = elapsed_ms
        elif event_type == "ai.output.delta" and first_delta_ms is None:
            first_delta_ms = elapsed_ms
        elif event_type in _TERMINAL_EVENTS:
            if accepted_ms is None or not interaction_id:
                raise RuntimeError("Terminal event arrived before interaction.accepted")
            return Sample(
                interaction_id=interaction_id,
                terminal_event=cast(str, event_type),
                accepted_ms=accepted_ms,
                first_delta_ms=first_delta_ms,
                completed_ms=elapsed_ms,
            )


async def benchmark(args: argparse.Namespace) -> dict[str, object]:
    for index in range(args.warmup):
        await run_sample(args.url, args.origin, args.prompt, args.label, args.timeout_seconds)
        print(f"warmup {index + 1}/{args.warmup} completed", file=sys.stderr, flush=True)
    samples: list[Sample] = []
    for index in range(args.samples):
        sample = await run_sample(
            args.url, args.origin, args.prompt, args.label, args.timeout_seconds
        )
        samples.append(sample)
        print(
            f"sample {index + 1}/{args.samples} completed in {sample.completed_ms:.1f} ms",
            file=sys.stderr,
            flush=True,
        )
    return _report(args, samples)


def _report(args: argparse.Namespace, samples: list[Sample]) -> dict[str, object]:
    completed = [item for item in samples if item.terminal_event == "ai.output.completed"]
    first_deltas = [item.first_delta_ms for item in completed if item.first_delta_ms is not None]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "url": args.url,
        "origin": args.origin,
        "label": args.label,
        "samples": len(samples),
        "warmup": args.warmup,
        "completed_samples": len(completed),
        "streamed_samples": len(first_deltas),
        "metrics_ms": {
            "accepted": _summary([item.accepted_ms for item in completed]),
            "first_delta": _summary(first_deltas),
            "completed": _summary([item.completed_ms for item in completed]),
        },
        "runs": [asdict(item) for item in samples],
    }


def _summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "min": round(ordered[0], 3),
        "p50": round(median(ordered), 3),
        "p95": round(_percentile(ordered, 0.95), 3),
        "max": round(ordered[-1], 3),
    }


def _percentile(ordered: list[float], quantile: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _object(raw: object) -> dict[str, object]:
    if not isinstance(raw, str):
        raise RuntimeError("WebSocket returned a non-text frame")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise RuntimeError("WebSocket returned a non-object envelope")
    return cast(dict[str, object], decoded)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"WebSocket envelope is missing {field}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure real Parrot WebSocket interaction latency without printing model output."
        )
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--confirm-real-requests",
        action="store_true",
        help="Required because the benchmark creates durable interactions and provider charges.",
    )
    args = parser.parse_args()
    if not args.confirm_real_requests:
        parser.error("--confirm-real-requests is required")
    if re.fullmatch(r"[a-z0-9-]{1,32}", args.label) is None:
        parser.error("--label must contain 1 to 32 lowercase letters, digits, or hyphens")
    if not 1 <= args.samples <= 100:
        parser.error("--samples must be between 1 and 100")
    if not 0 <= args.warmup <= 10:
        parser.error("--warmup must be between 0 and 10")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return args


def main() -> None:
    args = parse_args()
    report = asyncio.run(benchmark(args))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if report["completed_samples"] != report["samples"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
