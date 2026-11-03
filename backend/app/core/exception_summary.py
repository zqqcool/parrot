from __future__ import annotations

from pathlib import Path
from traceback import walk_tb
from typing import cast


def safe_exception_summary(error: BaseException) -> str:
    """Keep failure types and call sites without exception text, locals or source code."""
    lines: list[str] = []
    seen: set[int] = set()
    pending = [error]
    while pending and len(seen) < 16:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        lines.append(type(current).__name__)
        for frame, lineno in walk_tb(current.__traceback__):
            filename = Path(frame.f_code.co_filename).name
            lines.append(f"  {filename}:{lineno} in {frame.f_code.co_name}")
        cause = current.__cause__
        if cause is None and not current.__suppress_context__:
            cause = current.__context__
        if cause is not None:
            pending.append(cause)
        if isinstance(current, BaseExceptionGroup):
            group = cast(BaseExceptionGroup[BaseException], current)
            pending.extend(group.exceptions[:16])
    return "\n".join(lines)
