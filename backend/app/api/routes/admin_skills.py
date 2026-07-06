"""管理员技能管理 API。"""

import shutil

from fastapi import APIRouter, Body, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import Agent, Category, SkillBinding
from app.modules.catalog.file_manager import (
    build_file_tree,
    create_file,
    delete_file,
    read_file,
    write_file,
)
from app.modules.catalog.skills import _skills_dir
from app.modules.catalog.zip_validator import (
    ZipValidationError,
    extract_and_validate_zip,
    validate_skill_dir,
)

router = APIRouter(prefix="/api/admin/skills", dependencies=[Depends(require_admin)])


@router.post("/upload")
async def upload_skill(
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
            file,
            _skills_dir(),
            validate_skill_dir,
            allow_overwrite=True,
            use_archive_name_for_flat_root=True,
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
        insert(SkillBinding)
        .values(skill_name=name, category_id=category_id)
        .on_conflict_do_update(
            index_elements=["skill_name"],
            set_={"category_id": category_id},
        )
    )
    await db.execute(stmt)
    await db.commit()

    return {"name": name, "message": f"技能 '{name}' 上传成功"}


class WriteFileRequest(BaseModel):
    content: str


class CreateFileRequest(BaseModel):
    path: str
    content: str


class CategoryUpdateRequest(BaseModel):
    category_id: int


@router.get("/{name}/files")
async def list_skill_files(name: str):
    root = _skills_dir() / name
    return build_file_tree(root)


@router.get("/{name}/files/{path:path}", response_class=PlainTextResponse)
async def get_skill_file(name: str, path: str):
    root = _skills_dir() / name
    return read_file(root, path)


@router.put("/{name}/files/{path:path}")
async def update_skill_file(name: str, path: str, body: WriteFileRequest):
    root = _skills_dir() / name
    write_file(root, path, body.content)
    return {"ok": True}


@router.post("/{name}/files")
async def add_skill_file(name: str, body: CreateFileRequest):
    root = _skills_dir() / name
    create_file(root, body.path, body.content)
    return {"ok": True}


@router.patch("/{name}/category")
async def update_skill_category(
    name: str,
    body: CategoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新技能与分类的绑定关系。"""
    root = _skills_dir() / name
    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在"
        )

    category = await db.get(Category, body.category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="分类不存在",
        )

    stmt = (
        insert(SkillBinding)
        .values(skill_name=name, category_id=body.category_id)
        .on_conflict_do_update(
            index_elements=["skill_name"],
            set_={"category_id": body.category_id},
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"name": name, "category_id": body.category_id}


@router.delete("/{name}/files/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_skill_file(name: str, path: str):
    root = _skills_dir() / name
    delete_file(root, path)
    return None


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    name: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    root = _skills_dir() / name
    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在"
        )

    # 检查引用（精确匹配逗号分隔的 skills 字段）
    result = await db.execute(
        select(Agent).where(
            or_(
                Agent.skills == name,
                Agent.skills.like(f"{name},%"),
                Agent.skills.like(f"%,{name},%"),
                Agent.skills.like(f"%,{name}"),
            )
        )
    )
    agents = result.scalars().all()
    if agents and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"技能 '{name}' 正被 {len(agents)} 个智能体引用",
                "agents": [{"id": a.id, "name": a.name, "code": a.code} for a in agents],
            },
        )

    if agents and force:
        for agent in agents:
            skills = [s.strip() for s in agent.skills.split(",") if s.strip() != name]
            agent.skills = ",".join(skills)
        await db.commit()

    # 删除绑定记录
    await db.execute(delete(SkillBinding).where(SkillBinding.skill_name == name))
    await db.commit()

    shutil.rmtree(root)
    return None
