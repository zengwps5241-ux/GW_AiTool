"""企微部门同步逻辑。"""

import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Department
from app.modules.auth import wechat_work

logger = logging.getLogger(__name__)


async def sync_departments(db: AsyncSession) -> None:
    """从企业微信同步部门列表到本地数据库。"""
    settings = get_settings()
    if not settings.wechat_work_corp_id or not settings.wechat_work_secret:
        logger.warning("缺少企微配置，跳过部门同步")
        return

    try:
        access_token = await wechat_work.get_access_token(
            settings.wechat_work_corp_id,
            settings.wechat_work_secret,
        )
        dept_list = await wechat_work.get_department_list(access_token)
    except Exception:
        logger.exception("企微部门同步失败")
        return

    # 全量替换：清空旧数据后插入新数据
    await db.execute(delete(Department))

    for d in dept_list:
        db.add(
            Department(
                id=d["id"],
                name=d["name"],
                parent_id=d.get("parentid"),
                order=d.get("order"),
            )
        )

    await db.commit()
    logger.info("已同步 %d 个企微部门", len(dept_list))


async def get_department_names(
    db: AsyncSession, department_ids: list[int]
) -> list[str]:
    """根据部门 id 列表查询部门名称，顺序保持一致。"""
    from sqlalchemy import text

    if not department_ids:
        return []

    result = await db.execute(
        text("SELECT id, name FROM departments WHERE id = ANY(:ids)").bindparams(
            ids=department_ids
        )
    )
    dept_map = {row.id: row.name for row in result.all()}
    return [dept_map.get(did, str(did)) for did in department_ids]
