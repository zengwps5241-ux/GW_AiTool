"""管理员分类管理 API。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import Category
from app.schemas.categories import CategoryCreate, CategoryOut, CategoryRename

router = APIRouter(prefix="/api/admin/categories")


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> list[CategoryOut]:
    """管理员查看分类列表。"""
    result = await db.execute(select(Category).order_by(Category.id))
    return [CategoryOut(id=c.id, name=c.name) for c in result.scalars().all()]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> CategoryOut:
    result = await db.execute(
        select(Category).where(Category.name == payload.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="分类已存在",
        )
    category = Category(name=payload.name)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return CategoryOut(id=category.id, name=category.name)


@router.patch("/{category_id}", response_model=CategoryOut)
async def rename_category(
    category_id: int,
    payload: CategoryRename,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> CategoryOut:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在"
        )
    if payload.name != category.name:
        result = await db.execute(
            select(Category).where(Category.name == payload.name)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="分类名称已存在",
            )
        category.name = payload.name
        await db.commit()
    return CategoryOut(id=category.id, name=category.name)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> None:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在"
        )
    if category.name == "默认":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="默认分类不可删除",
        )

    # 获取默认分类
    result = await db.execute(
        select(Category).where(Category.name == "默认")
    )
    default_category = result.scalar_one()

    # 将技能绑定移到默认分类
    from app.models import SkillBinding
    await db.execute(
        text("UPDATE skill_bindings SET category_id = :default_id WHERE category_id = :cat_id"),
        {"default_id": default_category.id, "cat_id": category_id},
    )

    # 将插件绑定移到默认分类
    from app.models import PluginBinding
    await db.execute(
        text("UPDATE plugin_bindings SET category_id = :default_id WHERE category_id = :cat_id"),
        {"default_id": default_category.id, "cat_id": category_id},
    )

    await db.delete(category)
    await db.commit()
    return None
