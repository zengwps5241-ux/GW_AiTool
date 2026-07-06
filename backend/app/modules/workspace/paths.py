"""工作空间路径解析与文件树遍历。"""

from pathlib import Path

from fastapi import HTTPException, status

# 最大递归深度
_MAX_DEPTH = 4
# 单目录最多列出的条目数
_MAX_ENTRIES_PER_DIR = 500
# 跳过的目录名
_SKIP_DIRS = {
    "node_modules",
    "__pycache__",
    ".venv",
    ".git",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def should_skip(entry: Path) -> bool:
    """统一过滤规则:.claude 给用户维护,其他隐藏文件与垃圾目录跳过。"""
    name = entry.name
    if name == ".claude":
        return False
    return name.startswith(".") or name in _SKIP_DIRS


def resolve_inside_workspace(workspace: Path, rel_path: str) -> Path:
    """把相对路径解析到工作区内的绝对路径,越权或不存在直接抛 4xx。"""
    if not rel_path or rel_path.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="路径不能为空"
        )
    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="只能使用工作区相对路径"
        )
    try:
        target = (workspace / rel_path).resolve()
        ws_resolved = workspace.resolve()
    except (OSError, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="路径无效"
        )
    if not target.is_relative_to(ws_resolved):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="路径越出工作区"
        )
    return target


def list_dir(
    d: Path,
    rel_base: str,
    depth: int,
    agent_paths: dict[str, str] | None = None,
    conversion_meta: dict[str, dict] | None = None,
) -> list:
    """读取目录条目,目录优先、按文件名排序。

    ``agent_paths`` 为 ``源相对路径 -> markdown 相对路径`` 的映射,用于
    在文件树节点上携带 ``agent_path``,以便前端在引用工作空间文件时优先
    把可读的 markdown 路径发给智能体。

    ``conversion_meta`` 为 ``源相对路径 -> 转换元数据字典`` 的映射,
    用于在文件树节点上携带转换任务状态。
    """
    from app.schemas import WorkspaceNode

    try:
        entries = list(d.iterdir())
    except (PermissionError, OSError):
        return []

    entries = [e for e in entries if not should_skip(e)]
    entries.sort(key=lambda p: (0 if p.is_dir() else 1, p.name.lower()))
    entries = entries[:_MAX_ENTRIES_PER_DIR]

    mappings = agent_paths or {}
    meta = conversion_meta or {}
    out: list[WorkspaceNode] = []
    for e in entries:
        rel = f"{rel_base}/{e.name}" if rel_base else e.name
        try:
            stat = e.stat()
        except OSError:
            continue
        if e.is_dir():
            children = (
                list_dir(e, rel, depth + 1, mappings, meta) if depth < _MAX_DEPTH else []
            )
            out.append(
                WorkspaceNode(
                    name=e.name,
                    path=rel,
                    type="dir",
                    mtime=stat.st_mtime,
                    children=children,
                )
            )
        else:
            node_meta = meta.get(rel) or {}
            indexed_markdown_path = mappings.get(rel)
            out.append(
                WorkspaceNode(
                    name=e.name,
                    path=rel,
                    type="file",
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    agent_path=indexed_markdown_path,
                    conversion_status=node_meta.get("conversion_status"),
                    conversion_task_id=node_meta.get("conversion_task_id"),
                    conversion_error=node_meta.get("conversion_error"),
                    # 任务表可能被清理或缺少历史记录；文件树仍以 markdown 索引为准。
                    markdown_path=node_meta.get("markdown_path") or indexed_markdown_path,
                )
            )
    return out
