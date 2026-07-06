"""Zip 上传、解压与规范性校验。"""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from collections.abc import Callable
from collections.abc import Iterable
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import UploadFile


class ZipValidationError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


def _safe_path(path: str) -> str:
    """校验并标准化 zip 内路径，防止路径穿越。"""
    normalized = path.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    if normalized.startswith("/") or ".." in parts:
        raise ZipValidationError(f"路径穿越尝试: {path}")
    return "/".join(parts)


def _is_noise_path(path: str) -> bool:
    parts = [p for p in path.split("/") if p]
    return bool(parts) and (parts[0] == "__MACOSX" or parts[-1] == ".DS_Store")


def _archive_stem(filename: str | None) -> str | None:
    if not filename:
        return None
    stem = Path(filename).stem.strip()
    return stem or None


def _extract_zip_members(zf: zipfile.ZipFile, extract_dir: Path) -> None:
    for info in zf.infolist():
        safe = _safe_path(info.filename)
        if not safe or _is_noise_path(safe):
            continue

        dest = extract_dir / safe
        try:
            dest.relative_to(extract_dir)
        except ValueError:
            raise ZipValidationError(f"路径穿越尝试: {info.filename}")

        if info.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out)


def _meaningful_top_items(extract_dir: Path) -> list[Path]:
    return [p for p in extract_dir.iterdir() if not _is_noise_path(p.name)]


def _wrap_flat_root(top_items: Iterable[Path], tmp: Path) -> Path:
    root = tmp / "package-root"
    root.mkdir()
    for item in top_items:
        shutil.move(str(item), str(root / item.name))
    return root


def _rewrite_skill_name(root: Path, name: str) -> None:
    """让平铺技能包的 SKILL.md name 与 zip 文件名保持一致。"""
    skill_md = root / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    updated = re.sub(
        r"(?m)^name:\s*.+$",
        f"name: {name}",
        text,
        count=1,
    )
    skill_md.write_text(updated, encoding="utf-8")


def extract_and_validate_zip(
    file: UploadFile,
    target_dir: Path,
    validate_fn: Callable[[Path], str],
    max_size: int = 50 * 1024 * 1024,  # 50MB
    allow_overwrite: bool = False,
    use_archive_name_for_flat_root: bool = False,
) -> str:
    """解压 zip 到临时目录，校验通过后再移动到 target_dir。

    返回提取后的根目录名（即 skill/plugin 名称）。

    validate_fn(temp_extract_dir: Path) -> str: 校验函数，返回名称。
    """
    raw = file.file.read()
    if len(raw) > max_size:
        raise ZipValidationError("zip 包大小超过 50MB 限制")

    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        extract_dir = tmp / "extracted"
        extract_dir.mkdir()

        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                _extract_zip_members(zf, extract_dir)
        except zipfile.BadZipFile:
            raise ZipValidationError("zip 文件格式无效")

        # 兼容两种结构:
        # 1. zip 根目录只有一个顶层目录:直接使用该目录。
        # 2. zip 根目录直接放 SKILL.md/manifest 等文件:包一层临时目录。
        top_items = _meaningful_top_items(extract_dir)
        fallback_name = _archive_stem(file.filename)
        is_flat_root = not (len(top_items) == 1 and top_items[0].is_dir())
        if is_flat_root:
            if not top_items:
                raise ZipValidationError("zip 包不能为空")
            root = _wrap_flat_root(top_items, tmp)
        else:
            root = top_items[0]

        # 校验
        validated_name = validate_fn(root)
        name = (
            fallback_name
            if is_flat_root and use_archive_name_for_flat_root and fallback_name
            else validated_name
        )

        # 校验名称合法性（防止目录名包含非法字符）
        if not re.match(r"^[a-zA-Z0-9_\-]+$", name):
            raise ZipValidationError(f"名称包含非法字符: {name}")

        if is_flat_root and use_archive_name_for_flat_root:
            _rewrite_skill_name(root, name)

        # 移动到目标目录
        dest = target_dir / name
        if dest.exists():
            if not allow_overwrite:
                raise ZipValidationError("技能/插件已存在")
            shutil.rmtree(dest)
        shutil.move(str(root), str(dest))

        return name


def validate_skill_dir(root: Path) -> str:
    """校验技能目录结构，返回技能名称。"""
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        raise ZipValidationError("技能根目录必须包含 SKILL.md 文件")

    text = skill_md.read_text(encoding="utf-8")
    # 匹配 YAML frontmatter
    m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        raise ZipValidationError("SKILL.md 缺少 YAML frontmatter")

    front = m.group(1)
    name_match = re.search(r"^name:\s*(.+)$", front, re.MULTILINE)
    if not name_match:
        raise ZipValidationError("SKILL.md frontmatter 中缺少 name 字段")
    name = name_match.group(1).strip()

    desc_match = re.search(r"^description:\s*(.+)$", front, re.MULTILINE)
    if not desc_match:
        raise ZipValidationError("SKILL.md frontmatter 中缺少 description 字段")

    return name


def validate_plugin_dir(root: Path) -> str:
    """校验插件目录结构，返回插件名称。

    支持两种布局:
    1. 平铺布局: root/.claude-plugin/plugin.json
    2. 版本布局: root/<version>/.claude-plugin/plugin.json
    """
    manifest = root / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        # 查找版本布局
        candidates = [
            p
            for p in root.iterdir()
            if p.is_dir() and (p / ".claude-plugin" / "plugin.json").exists()
        ]
        if not candidates:
            raise ZipValidationError("插件根目录必须包含 .claude-plugin/plugin.json 文件")
        if len(candidates) > 1:
            raise ZipValidationError("插件根目录下存在多个版本目录，只能包含一个")
        manifest = candidates[0] / ".claude-plugin" / "plugin.json"

    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ZipValidationError("plugin.json 不是有效的 JSON")

    if not isinstance(data, dict):
        raise ZipValidationError("plugin.json 必须是一个 JSON 对象")

    name = data.get("name")
    if not name:
        raise ZipValidationError("plugin.json 中缺少 name 字段")

    version = data.get("version")
    if not version:
        raise ZipValidationError("plugin.json 中缺少 version 字段")

    description = data.get("description")
    if not description:
        raise ZipValidationError("plugin.json 中缺少 description 字段")

    return str(name)
