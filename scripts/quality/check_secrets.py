from __future__ import annotations

import argparse
import base64
import binascii
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
_PUBLIC_PREFIXES = ("test-only-", "overridden-by-")
_TOKENS = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{30,}|glpat-[A-Za-z0-9_-]{16,})\b"
)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----\s+[A-Za-z0-9+/=\r\n]{64,}")
_MAX_ARCHIVE_BYTES = 50 * 1024 * 1024


def _config_issues(data: bytes) -> list[str]:
    config = tomllib.loads(data.decode())
    security = config["security"]
    secrets = [security["session_pepper"]]
    storage = config["object_storage"]
    secrets.extend((storage["access_key"], storage["secret_key"]))
    for section in ("memory_credentials", "knowledge_credentials"):
        secrets.extend(config.get(section, {}).get("values", {}).values())
    for url in (*config["database"].values(), config["redis"]["url"]):
        if isinstance(url, str) and "://" in url and (password := urlsplit(url).password):
            secrets.append(unquote(password))
    encoded = security["credential_encryption_key"]
    if encoded.startswith("overridden-by-"):
        secrets.append(encoded)
    else:
        padded = encoded + "=" * (-len(encoded) % 4)
        secrets.append(base64.b64decode(padded, altchars=b"-_", validate=True).decode())
    if any(not value.startswith(_PUBLIC_PREFIXES) for value in secrets):
        return ["deployment configuration contains a non-public credential"]
    return []


def _content_issues(data: bytes) -> list[str]:
    content = data.decode("utf-8", errors="replace")
    issues = []
    for pattern, label in ((_PRIVATE_KEY, "private key"), (_TOKENS, "credential token")):
        for match in pattern.finditer(content):
            # Explicit dummy provider tokens are fixtures, not deployment credentials.
            if label == "credential token" and any(
                marker in match.group().casefold()
                for marker in ("test", "example", "fake", "secret")
            ):
                continue
            line = content.count("\n", 0, match.start()) + 1
            issues.append(f"line {line}: possible {label}")
    return issues


def _file_issues(path: Path, relative: str) -> list[str]:
    data = path.read_bytes()
    issues = _content_issues(data)
    if relative in {f"backend/config/{environment}.toml" for environment in ("dev", "sit", "prod")}:
        issues.extend(_config_issues(data))
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > _MAX_ARCHIVE_BYTES:
                return [*issues, "archive exceeds the secret scan size limit"]
            for item in archive.infolist():
                issues.extend(
                    f"{item.filename}: {issue}" for issue in _content_issues(archive.read(item))
                )
    return issues


def main(root: Path) -> int:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
    )
    findings = []
    paths = sorted(set(result.stdout.decode().split("\0")) - {""})
    for relative in paths:
        path = root / relative
        if not path.is_file():
            continue
        try:
            issues = _file_issues(path, relative)
        except (ValueError, KeyError, UnicodeError, binascii.Error, zipfile.BadZipFile):
            issues = ["file cannot be safely validated"]
        findings.extend(f"{relative}: {issue}" for issue in issues)
    if findings:
        print("Secret scan failed (values omitted):\n" + "\n".join(findings))
        return 1
    print(
        f"Secret scan passed: {len(paths)} files; deployment placeholders and credential patterns"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan publishable files without printing secrets")
    parser.add_argument("--root", type=Path, default=ROOT)
    raise SystemExit(main(parser.parse_args().root.resolve()))
