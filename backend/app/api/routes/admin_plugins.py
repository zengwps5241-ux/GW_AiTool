"""管理员插件管理 API（只读文件查看 + 上传/删除）。"""

import shutil

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import Agent, Category, PluginBinding
from app.modules.catalog.file_manager import build_file_tree, read_file
from app.modules.catalog.plugins import _plugins_dir
from app.modules.catalog.zip_validator import (
    ZipValidationError,
    extract_and_validate_zip,
    validate_plugin_dir,
)

router = APIRouter(prefix="/api/admin/plugins", dependencies=[Depends(require_admin)])


class CategoryUpdateRequest(BaseModel):
    category_id: int


@router.post("/upload")
async def upload_plugin(
    file: UploadFile,
    category_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请上传 .zip 文件",
        )
    try:
        name = extract_and_validate_zip(
            file, _plugins_dir(), validate_plugin_dir, allow_overwrite=True
        )
    except ZipValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=e.detail
        )

    # 验证分类存在
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="分类不存在",
        )

    # UPSERT 绑定记录
    stmt = (
        insert(PluginBinding)
        .values(plugin_path=name, category_id=category_id)
        .on_conflict_do_update(
            index_elements=["plugin_path"],
            set_={"category_id": category_id},
        )
    )
    await db.execute(stmt)
    await db.commit()

    return {"name": name, "message": f"插件 '{name}' 上传成功"}


@router.get("/{name}/files")
async def list_plugin_files(name: str):
    root = _plugins_dir() / name
    return build_file_tree(root)


@router.get("/{name}/files/{path:path}", response_class=PlainTextResponse)
async def get_plugin_file(name: str, path: str):
    root = _plugins_dir() / name
    return read_file(root, path)


@router.patch("/{path:path}/category")
async def update_plugin_category(
    path: str,
    body: CategoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新插件与分类的绑定关系。"""
    root = _plugins_dir() / path
    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在"
        )

    category = await db.get(Category, body.category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="分类不存在",
        )

    stmt = (
        insert(PluginBinding)
        .values(plugin_path=path, category_id=body.category_id)
        .on_conflict_do_update(
            index_elements=["plugin_path"],
            set_={"category_id": body.category_id},
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"path": path, "category_id": body.category_id}


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(
    name: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    root = _plugins_dir() / name
    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="插件不存在"
        )

    result = await db.execute(
        select(Agent).where(
            or_(
                Agent.plugins == name,
                Agent.plugins.like(f"{name},%"),
                Agent.plugins.like(f"%,{name},%"),
                Agent.plugins.like(f"%,{name}"),
            )
        )
    )
    agents = result.scalars().all()
    if agents and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"插件 '{name}' 正被 {len(agents)} 个智能体引用",
                "agents": [{"id": a.id, "name": a.name, "code": a.code} for a in agents],
            },
        )

    if agents and force:
        for agent in agents:
            plugins = [p.strip() for p in agent.plugins.split(",") if p.strip() != name]
            agent.plugins = ",".join(plugins)
        await db.commit()

    # 删除绑定记录
    await db.execute(delete(PluginBinding).where(PluginBinding.plugin_path == name))
    await db.commit()

    shutil.rmtree(root)
    return None
