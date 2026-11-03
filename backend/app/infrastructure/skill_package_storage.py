from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path, PurePosixPath


class LocalSkillPackageStorage:
    """Stores validated skill archives below the configured durable storage root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    async def write(
        self,
        tenant_id: str,
        skill_id: str,
        version: int,
        checksum: str,
        content: bytes,
    ) -> str:
        return await asyncio.to_thread(self._write, tenant_id, skill_id, version, checksum, content)

    async def read(self, package_path: str) -> bytes:
        return await asyncio.to_thread(self._read, package_path)

    def _write(
        self,
        tenant_id: str,
        skill_id: str,
        version: int,
        checksum: str,
        content: bytes,
    ) -> str:
        key = PurePosixPath(tenant_id, skill_id, f"v{version}-{checksum[:16]}.zip")
        path = self.root.joinpath(*key.parts).resolve()
        if key.is_absolute() or ".." in key.parts or not path.is_relative_to(self.root):
            raise ValueError("Invalid skill package storage key")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        return key.as_posix()

    def _read(self, package_path: str) -> bytes:
        key = PurePosixPath(package_path)
        path = self.root.joinpath(*key.parts).resolve()
        if key.is_absolute() or ".." in key.parts or not path.is_relative_to(self.root):
            raise ValueError("Invalid skill package storage key")
        return path.read_bytes()
