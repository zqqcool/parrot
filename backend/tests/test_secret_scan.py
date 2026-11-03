import subprocess
import sys
from pathlib import Path

import pytest

SCANNER = Path(__file__).resolve().parents[2] / "scripts/quality/check_secrets.py"


def _scan(root: Path) -> subprocess.CompletedProcess[str]:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def test_secret_scan_rejects_tokens_without_printing_their_value(tmp_path: Path) -> None:
    token = "sk-" + "aB31" * 8
    (tmp_path / "credentials.txt").write_text(token)
    result = _scan(tmp_path)
    assert result.returncode == 1
    assert "credentials.txt: line 1" in result.stdout
    assert token not in result.stdout + result.stderr


@pytest.mark.parametrize("replacement", [None, "unapproved-deployment-secret"])
def test_secret_scan_enforces_public_configuration_placeholders(
    tmp_path: Path,
    replacement: str | None,
) -> None:
    source = Path(__file__).resolve().parents[1] / "config/dev.toml"
    content = source.read_text()
    if replacement:
        content = content.replace("test-only-qiniu-access-key", replacement)
    target = tmp_path / "backend/config/dev.toml"
    target.parent.mkdir(parents=True)
    target.write_text(content)
    result = _scan(tmp_path)
    assert result.returncode == (1 if replacement else 0)
    if replacement:
        assert replacement not in result.stdout + result.stderr
