"""API 路由聚合器。"""

from app.api.routes import (
    admin_categories,
    admin_login_whitelist,
    admin_plugins,
    admin_skills,
    admin_usage,
    agents,
    auth,
    business_map,
    conversion_tasks,
    customers,
    feedback,
    model_settings,
    organizations,
    projects,
    sessions,
    team_spaces,
    upload_tasks,
    uploads,
    workspace,
    workspace_tasks,
)
from fastapi import APIRouter

router = APIRouter()
router.include_router(auth.router)
router.include_router(sessions.router)
router.include_router(agents.router)
router.include_router(team_spaces.router)
router.include_router(uploads.router)
router.include_router(upload_tasks.router)
router.include_router(workspace_tasks.router)
router.include_router(workspace.router)
router.include_router(workspace.kkfileview_router)
router.include_router(conversion_tasks.router)
router.include_router(admin_skills.router)
router.include_router(admin_plugins.router)
router.include_router(admin_categories.router)
router.include_router(admin_login_whitelist.router)
router.include_router(feedback.router)
router.include_router(model_settings.router)
router.include_router(admin_usage.router)
router.include_router(organizations.router)
router.include_router(customers.router)
router.include_router(projects.router)
router.include_router(business_map.router)
