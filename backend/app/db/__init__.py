"""数据库模块（临时兼容 shim，将在后续任务删除）。"""

import sys
from importlib import reload

from app.db import base, migrations, session

reload(base)
reload(session)
reload(migrations)

# 强制重新加载 models 子模块,确保模型类注册到新的 Base 上
for _mod_name in [
    "app.models.user",
    "app.models.category",
    "app.models.agent",
    "app.models.team_space",
    "app.models.session",
    "app.models.upload_task",
    "app.models.conversion_task",
    "app.models.department",
    "app.models.feedback",
    "app.models.login_whitelist",
    "app.models.usage",
]:
    if _mod_name in sys.modules:
        reload(sys.modules[_mod_name])

if "app.models" in sys.modules:
    reload(sys.modules["app.models"])

from app.db.base import Base
from app.db.migrations import init_db
from app.db.session import async_session, engine, get_db

# 确保模型注册到 Base.metadata（首次导入与 reload 都需要）
import app.models  # noqa: E402,F401

__all__ = ["Base", "init_db", "async_session", "engine", "get_db"]
