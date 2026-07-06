"""技能/插件目录的文件树读取、内容读写。"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status


def _resolve_safe(root: Path, rel_path: str) -> Path:
    """解析相对路径,确保结果在 root 目录内。"""
    # 移除 .. 和空段
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p and p != ".."]
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="非法文件路径"
        )
    return target


def build_file_tree(root: Path) -> dict:
    """构建文件树 JSON,与 WorkspaceNode 结构保持一致。"""
    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="技能/插件不存在"
        )

    def _walk(p: Path, rel: str) -> dict:
        node = {
            "name": p.name,
            "path": rel,
            "type": "dir" if p.is_dir() else "file",
        }
        if p.is_file():
            node["size"] = p.stat().st_size
            node["mtime"] = int(p.stat().st_mtime)
        elif p.is_dir():
            children = []
            for child in sorted(p.iterdir()):
                child_rel = f"{rel}/{child.name}" if rel else child.name
                children.append(_walk(child, child_rel))
            node["children"] = children
        return node

    return _walk(root, "")


def read_file(root: Path, rel_path: str) -> str:
    target = _resolve_safe(root, rel_path)
    if not target.exists() or target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
        )
    return target.read_text(encoding="utf-8")


def write_file(root: Path, rel_path: str, content: str) -> None:
    target = _resolve_safe(root, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def create_file(root: Path, rel_path: str, content: str) -> None:
    target = _resolve_safe(root, rel_path)
    if target.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="文件已存在"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def delete_file(root: Path, rel_path: str) -> None:
    target = _resolve_safe(root, rel_path)
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
        )
    if target.is_dir():
        import shutil
        shutil.rmtree(target)
    else:
        target.unlink()
