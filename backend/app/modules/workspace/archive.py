"""流式 zip 归档生成。"""

import zipfile
from collections.abc import Iterator
from pathlib import Path

_ZIP_CHUNK = 64 * 1024


class _ChunkBuffer:
    """ZipFile 写入会落到这里;每次 drain() 把累积字节取走交给生成器。"""

    def __init__(self) -> None:
        self._buf = bytearray()

    def write(self, data: bytes) -> int:
        self._buf.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def drain(self) -> bytes:
        if not self._buf:
            return b""
        out = bytes(self._buf)
        self._buf.clear()
        return out


def walk_filtered(root: Path, ws_root: Path) -> Iterator[Path]:
    """递归产出 root 下的文件路径,跟随 should_skip 过滤,跳过越出工作区的符号链接。"""
    from app.modules.workspace.paths import should_skip

    visited: set[Path] = set()

    def _walk(current: Path) -> Iterator[Path]:
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            return
        for entry in entries:
            if should_skip(entry):
                continue
            try:
                resolved = entry.resolve()
            except (OSError, RuntimeError):
                continue
            if not resolved.is_relative_to(ws_root):
                continue
            if entry.is_dir():
                if resolved in visited:
                    continue
                visited.add(resolved)
                yield from _walk(entry)
            elif entry.is_file():
                yield entry

    try:
        visited.add(root.resolve())
    except (OSError, RuntimeError):
        pass
    yield from _walk(root)


def iter_zip(root: Path, ws_root: Path) -> Iterator[bytes]:
    """边压边发的 zip 生成器,内存峰值 ~ _ZIP_CHUNK。"""
    buf = _ChunkBuffer()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in walk_filtered(root, ws_root):
            try:
                rel = entry.relative_to(root).as_posix()
            except ValueError:
                continue
            arcname = f"{root.name}/{rel}"
            try:
                with entry.open("rb") as src, zf.open(arcname, "w") as dst:
                    while True:
                        chunk = src.read(_ZIP_CHUNK)
                        if not chunk:
                            break
                        dst.write(chunk)
                        data = buf.drain()
                        if data:
                            yield data
            except FileNotFoundError:
                continue
            data = buf.drain()
            if data:
                yield data
    tail = buf.drain()
    if tail:
        yield tail
