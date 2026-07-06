"""共享工具函数。"""

from __future__ import annotations

import re
from pathlib import Path

# 危险字符:控制符、路径分隔符、Windows 禁用符、空白(含全角空格)。
# 视觉易混淆字符:CJK 部首 ``丨`` 看起来像 ASCII ``|``;中英文弯引号也常被
# LLM 在生成工具调用时静默规整成 ASCII 等价物,造成 Read/Write 失败,
# 因此在这里一并替换成下划线,保证文件名在磁盘和 prompt 之间能稳定回环。
_UNSAFE_CHARS = re.compile(
    r"[\x00-\x1f/\\<>:\"|?*\s丨“”‘’]"
)


def safe_filename(raw: str) -> str:
    """清理文件名中的特殊字符和空格，避免跨平台兼容性问题。"""
    base = Path(raw.replace("\\", "/")).name.strip()
    safe = _UNSAFE_CHARS.sub("_", base).strip(". ")
    # 合并连续的下划线
    safe = re.sub(r"_+", "_", safe)
    # 去掉首尾下划线
    safe = safe.strip("_")
    return safe or "file"
