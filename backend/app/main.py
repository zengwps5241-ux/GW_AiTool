"""应用入口:工厂创建 + 中间件 + 路由挂载。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth_guard import install_api_auth_guard
from app.core import config
from app.core import logging as app_logging
from app.db.migrations import init_db


@asynccontextmanager
async def _lifespan(_: FastAPI):
    app_logging.configure_logging()
    config.apply_environment()
    await init_db()
    # M3.2：把内置 7 个顾问 Skill 模板播种到 master 目录，供项目 Agent 拷贝加载
    from app.modules.agents.workdir import seed_default_skills
    seed_default_skills()
    # M3.3：把内置 3 个顾问 Plugin 模板播种到 master 目录，供项目 Agent 拷贝加载
    from app.modules.agents.workdir import seed_default_plugins
    seed_default_plugins()
    # 为 DB 中所有 Agent 兜底初始化工作目录(缺则补)
    from app.modules.agents.workdir import ensure_all_agent_workdirs
    await ensure_all_agent_workdirs()
    # M5.5.7：方法论库默认种子（表空才播种，非破坏性，admin 可后续维护）
    from app.db.session import async_session
    from app.modules.team_spaces.service import seed_default_methodology
    async with async_session() as db:
        await seed_default_methodology(db)
    # DEPRECATED: 企微部门同步已停用，切换为自建组织架构
    # from app.db.session import async_session
    # from app.modules.auth.departments import sync_departments
    # async with async_session() as db:
    #     await sync_departments(db)
    from app.modules.conversions.service import (
        enqueue_pending_conversion_tasks,
        start_conversion_task_dispatcher,
        stop_conversion_task_dispatcher,
    )
    await start_conversion_task_dispatcher()
    await enqueue_pending_conversion_tasks()
    try:
        yield
    finally:
        await stop_conversion_task_dispatcher()


def build_app() -> FastAPI:
    settings = config.get_settings()
    app = FastAPI(title="GokTech Agent", lifespan=_lifespan)
    install_api_auth_guard(app)
    app.add_middleware(SessionMiddleware, secret_key=settings.app_secret)

    from app.api.router import router as api_router

    app.include_router(api_router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    # 优先挂载 Vite 构建产物 (frontend/dist),回退到 legacy 静态资源 (frontend/legacy)
    frontend_root = Path(__file__).resolve().parent.parent.parent / "frontend"
    dist_dir = frontend_root / "dist"
    legacy_dir = frontend_root / "legacy"
    static_dir = dist_dir if dist_dir.exists() else legacy_dir if legacy_dir.exists() else None
    if static_dir is not None:
        app.mount(
            "/",
            StaticFiles(directory=str(static_dir), html=True),
            name="frontend",
        )

    return app


app = build_app()
