# 技能与插件分类管理实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为技能和插件引入共用分类体系，支持分类管理、上传时选择分类、列表页按分类分组展示。

**Architecture:** 轻量级映射表方案。保留现有文件系统扫描逻辑，新增 `categories`、`skill_bindings`、`plugin_bindings` 三张表。后端 API 增加 `/api/admin/categories` CRUD，改造现有 skills/plugins 列表和上传接口。前端 SkillsPage 增加分类管理 Tab，列表按分类分组展示，上传改为弹窗选择分类。

**Tech Stack:** FastAPI, SQLAlchemy(async), PostgreSQL, React, TypeScript, Vite, pytest

---

## 文件结构映射

| 文件 | 动作 | 职责 |
|------|------|------|
| `backend/app/models/category.py` | 新建 | Category、SkillBinding、PluginBinding ORM 模型 |
| `backend/app/models/__init__.py` | 修改 | 导出新模型，使 Base.metadata 包含新表 |
| `backend/app/db/migrations.py` | 修改 | 新增分类相关表创建和默认分类插入 |
| `backend/app/schemas/categories.py` | 新建 | CategoryOut、CategoryCreate、CategoryRename Schema |
| `backend/app/schemas/skills.py` | 修改 | SkillOut 增加 category 字段 |
| `backend/app/schemas/plugins.py` | 修改 | PluginOut 增加 category 字段 |
| `backend/app/api/routes/admin_categories.py` | 新建 | 分类管理 CRUD API |
| `backend/app/api/router.py` | 修改 | 注册 admin_categories 路由 |
| `backend/app/api/routes/agents.py` | 修改 | /skills 和 /plugins 返回分类信息 |
| `backend/app/api/routes/admin_skills.py` | 修改 | 上传增加 category_id，删除时清理绑定 |
| `backend/app/api/routes/admin_plugins.py` | 修改 | 上传增加 category_id，删除时清理绑定 |
| `frontend/src/types/index.ts` | 修改 | 增加 Category 类型，Skill/Plugin 增加 category |
| `frontend/src/api/client.ts` | 修改 | 增加分类管理 API，改造上传接口 |
| `frontend/src/pages/SkillsPage.tsx` | 大幅修改 | 分类分组展示、分类管理 Tab、上传弹窗 |
| `backend/tests/test_categories_api.py` | 新建 | 分类管理 API 测试 |
| `backend/tests/conftest.py` | 修改 | 增加新模块 reload |

---

### Task 1: Category 数据库模型

**Files:**
- Create: `backend/app/models/category.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/db/migrations.py`
- Test: `backend/tests/test_db.py`

- [ ] **Step 1: 创建 Category、SkillBinding、PluginBinding 模型**

```python
# backend/app/models/category.py
"""分类与技能/插件绑定模型。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )


class SkillBinding(Base):
    __tablename__ = "skill_bindings"

    skill_name: Mapped[str] = mapped_column(String, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=False
    )


class PluginBinding(Base):
    __tablename__ = "plugin_bindings"

    plugin_path: Mapped[str] = mapped_column(String, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=False
    )
```

- [ ] **Step 2: 修改 models/__init__.py 导出新模型**

```python
# backend/app/models/__init__.py
from app.db.base import Base
from app.models.agent import Agent
from app.models.category import Category, PluginBinding, SkillBinding
from app.models.conversion_task import ConversionTask
from app.models.session import ChatSession
from app.models.user import User

__all__ = [
    "Base",
    "Agent",
    "Category",
    "ChatSession",
    "ConversionTask",
    "PluginBinding",
    "SkillBinding",
    "User",
]
```

- [ ] **Step 3: 修改 migrations.py 添加分类表创建和默认分类插入**

在 `init_db()` 的末尾（`conversion_tasks` 迁移之后）添加：

```python
# backend/app/db/migrations.py
# ... existing code ...

# categories 表
result = await conn.execute(text(
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='categories'"
))
if result.scalar() == 0:
    await conn.execute(text(
        "CREATE TABLE categories ("
        "id SERIAL PRIMARY KEY, "
        "name VARCHAR UNIQUE NOT NULL, "
        "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ")"
    ))

# skill_bindings 表
result = await conn.execute(text(
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='skill_bindings'"
))
if result.scalar() == 0:
    await conn.execute(text(
        "CREATE TABLE skill_bindings ("
        "skill_name VARCHAR PRIMARY KEY, "
        "category_id INTEGER NOT NULL REFERENCES categories(id)"
        ")"
    ))

# plugin_bindings 表
result = await conn.execute(text(
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='plugin_bindings'"
))
if result.scalar() == 0:
    await conn.execute(text(
        "CREATE TABLE plugin_bindings ("
        "plugin_path VARCHAR PRIMARY KEY, "
        "category_id INTEGER NOT NULL REFERENCES categories(id)"
        ")"
    ))

# 插入默认分类
result = await conn.execute(text(
    "SELECT COUNT(*) FROM categories WHERE name='默认'"
))
if result.scalar() == 0:
    await conn.execute(text(
        "INSERT INTO categories (name) VALUES ('默认')"
    ))
```

- [ ] **Step 4: 运行现有测试确保迁移不破坏现有功能**

```bash
cd /Users/moses/Projects/guoke/智能体平台/backend
pytest tests/test_smoke.py tests/test_db.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/category.py backend/app/models/__init__.py backend/app/db/migrations.py
git commit -m "feat: 新增分类数据库模型和迁移"
```

---

### Task 2: Pydantic Schema 更新

**Files:**
- Create: `backend/app/schemas/categories.py`
- Modify: `backend/app/schemas/skills.py`
- Modify: `backend/app/schemas/plugins.py`

- [ ] **Step 1: 新建 categories schema**

```python
# backend/app/schemas/categories.py
"""分类相关 Pydantic 模型。"""

from pydantic import BaseModel


class CategoryOut(BaseModel):
    id: int
    name: str


class CategoryCreate(BaseModel):
    name: str


class CategoryRename(BaseModel):
    name: str
```

- [ ] **Step 2: 修改 SkillOut 增加 category 字段**

```python
# backend/app/schemas/skills.py
"""技能相关 Pydantic 模型。"""

from pydantic import BaseModel


class SkillOut(BaseModel):
    name: str
    description: str
    category: str | None = None
```

- [ ] **Step 3: 修改 PluginOut 增加 category 字段**

```python
# backend/app/schemas/plugins.py
"""插件相关 Pydantic 模型。"""

from pydantic import BaseModel


class PluginOut(BaseModel):
    name: str
    version: str
    description: str
    path: str
    category: str | None = None
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/categories.py backend/app/schemas/skills.py backend/app/schemas/plugins.py
git commit -m "feat: 更新技能/插件 schema，新增分类 schema"
```

---

### Task 3: 分类管理 API 路由

**Files:**
- Create: `backend/app/api/routes/admin_categories.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_categories_api.py`

- [ ] **Step 1: 新建分类管理 API 路由**

```python
# backend/app/api/routes/admin_categories.py
"""管理员分类管理 API。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models import Category
from app.schemas.categories import CategoryCreate, CategoryOut, CategoryRename

router = APIRouter(
    prefix="/api/admin/categories", dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
) -> list[CategoryOut]:
    result = await db.execute(select(Category).order_by(Category.id))
    return [CategoryOut(id=c.id, name=c.name) for c in result.scalars().all()]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
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
        "UPDATE skill_bindings SET category_id = :default_id WHERE category_id = :cat_id",
        {"default_id": default_category.id, "cat_id": category_id},
    )

    # 将插件绑定移到默认分类
    from app.models import PluginBinding
    await db.execute(
        "UPDATE plugin_bindings SET category_id = :default_id WHERE category_id = :cat_id",
        {"default_id": default_category.id, "cat_id": category_id},
    )

    await db.delete(category)
    await db.commit()
    return None
```

- [ ] **Step 2: 修改 router.py 注册新路由**

```python
# backend/app/api/router.py
"""API 路由聚合器。"""

from fastapi import APIRouter

from app.api.routes import (
    admin_categories,
    admin_plugins,
    admin_skills,
    agents,
    auth,
    conversion_tasks,
    sessions,
    uploads,
    workspace,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(sessions.router)
router.include_router(agents.router)
router.include_router(uploads.router)
router.include_router(workspace.router)
router.include_router(conversion_tasks.router)
router.include_router(admin_skills.router)
router.include_router(admin_plugins.router)
router.include_router(admin_categories.router)
```

- [ ] **Step 3: 修改 conftest.py 增加新模块 reload**

在 conftest.py 的 Layer 2 (models, schemas) 部分，新增 category 模型和 schemas 的 reload：

```python
# backend/tests/conftest.py
# ... existing imports ...

# Layer 2: models, schemas
# 在现有 reload 之后添加：
from app.models import category as model_category
from app.schemas import categories as schema_categories
reload(model_category)
reload(schema_categories)

# 在 Layer 5: api 部分，添加：
from app.api.routes import admin_categories as admin_categories_routes
reload(admin_categories_routes)
```

- [ ] **Step 4: 写分类管理 API 测试**

```python
# backend/tests/test_categories_api.py
import pytest


async def test_list_categories(admin_client):
    r = await admin_client.get("/api/admin/categories")
    assert r.status_code == 200
    data = r.json()
    # 迁移已插入默认分类
    assert len(data) >= 1
    assert any(c["name"] == "默认" for c in data)


async def test_create_category(admin_client):
    r = await admin_client.post("/api/admin/categories", json={"name": "数据分析"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "数据分析"
    assert "id" in data


async def test_create_duplicate_category(admin_client):
    await admin_client.post("/api/admin/categories", json={"name": "重复分类"})
    r = await admin_client.post("/api/admin/categories", json={"name": "重复分类"})
    assert r.status_code == 409


async def test_rename_category(admin_client):
    r = await admin_client.post("/api/admin/categories", json={"name": "待改名"})
    cat_id = r.json()["id"]

    r = await admin_client.patch(
        f"/api/admin/categories/{cat_id}", json={"name": "已改名"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "已改名"


async def test_delete_category_moves_bindings(admin_client, monkeypatch, tmp_path):
    # 创建分类
    r = await admin_client.post("/api/admin/categories", json={"name": "将被删除"})
    cat_id = r.json()["id"]

    # 获取默认分类 id
    r = await admin_client.get("/api/admin/categories")
    default_id = next(c["id"] for c in r.json() if c["name"] == "默认")

    # 创建一个技能目录
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: test-skill\n---\n", encoding="utf-8")
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)

    # 绑定技能到将被删除的分类
    from app.db.session import async_session
    from app.models import SkillBinding
    async with async_session() as session:
        session.add(SkillBinding(skill_name="test-skill", category_id=cat_id))
        await session.commit()

    # 删除分类
    r = await admin_client.delete(f"/api/admin/categories/{cat_id}")
    assert r.status_code == 204

    # 验证绑定已移到默认分类
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(SkillBinding).where(SkillBinding.skill_name == "test-skill")
        )
        binding = result.scalar_one()
        assert binding.category_id == default_id


async def test_delete_default_category_fails(admin_client):
    r = await admin_client.get("/api/admin/categories")
    default_id = next(c["id"] for c in r.json() if c["name"] == "默认")

    r = await admin_client.delete(f"/api/admin/categories/{default_id}")
    assert r.status_code == 400


async def test_delete_nonexistent_category(admin_client):
    r = await admin_client.delete("/api/admin/categories/99999")
    assert r.status_code == 404


async def test_categories_require_admin(logged_in_client):
    r = await logged_in_client.get("/api/admin/categories")
    assert r.status_code == 403
```

- [ ] **Step 5: 运行测试**

```bash
cd /Users/moses/Projects/guoke/智能体平台/backend
pytest tests/test_categories_api.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/admin_categories.py backend/app/api/router.py backend/tests/conftest.py backend/tests/test_categories_api.py
git commit -m "feat: 新增分类管理 CRUD API"
```

---

### Task 4: 技能/插件列表 API 改造

**Files:**
- Modify: `backend/app/api/routes/agents.py`
- Test: `backend/tests/test_skills_api.py`
- Test: `backend/tests/test_plugins_api.py`

- [ ] **Step 1: 修改 agents.py 的 /skills 和 /plugins 返回分类信息**

```python
# backend/app/api/routes/agents.py
"""智能体 CRUD 与技能清单。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_admin
from app.db.session import get_db
from app.models import Agent, Category, PluginBinding, SkillBinding, User
from app.modules.agents.service import (
    create_agent as create_agent_svc,
    delete_agent as delete_agent_svc,
    get_agent as get_agent_svc,
    list_agents as list_agents_svc,
    update_agent as update_agent_svc,
)
from app.modules.agents.workdir import get_agent_workdir, reinit_agent_workdir
from app.modules.catalog.commands import scan_agent_commands
from app.modules.catalog.plugins import scan_plugins
from app.modules.catalog.skills import scan_skills
from app.schemas import (
    AgentCommandOut,
    AgentOut,
    CreateAgentRequest,
    PluginOut,
    SkillOut,
    UpdateAgentRequest,
)

router = APIRouter(prefix="/api")


# ... existing agent routes unchanged ...


@router.get("/skills", response_model=list[SkillOut])
async def list_skills(
    _user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillOut]:
    skills = scan_skills()

    # 获取所有绑定
    bindings_result = await db.execute(select(SkillBinding))
    bindings = {b.skill_name: b.category_id for b in bindings_result.scalars().all()}

    # 获取所有分类
    categories_result = await db.execute(select(Category))
    categories = {c.id: c.name for c in categories_result.scalars().all()}

    # 获取默认分类
    default_cat_result = await db.execute(
        select(Category).where(Category.name == "默认")
    )
    default_category = default_cat_result.scalar_one()

    # 为未绑定的技能创建默认绑定
    for skill in skills:
        if skill["name"] not in bindings:
            db.add(SkillBinding(skill_name=skill["name"], category_id=default_category.id))
            bindings[skill["name"]] = default_category.id

    if any(s["name"] not in bindings for s in skills):
        await db.commit()

    return [
        SkillOut(
            name=s["name"],
            description=s["description"],
            category=categories.get(bindings.get(s["name"]), "默认"),
        )
        for s in skills
    ]


@router.get("/plugins", response_model=list[PluginOut])
async def list_plugins(
    _user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PluginOut]:
    plugins = scan_plugins()

    # 获取所有绑定
    bindings_result = await db.execute(select(PluginBinding))
    bindings = {b.plugin_path: b.category_id for b in bindings_result.scalars().all()}

    # 获取所有分类
    categories_result = await db.execute(select(Category))
    categories = {c.id: c.name for c in categories_result.scalars().all()}

    # 获取默认分类
    default_cat_result = await db.execute(
        select(Category).where(Category.name == "默认")
    )
    default_category = default_cat_result.scalar_one()

    # 为未绑定的插件创建默认绑定
    for plugin in plugins:
        if plugin["path"] not in bindings:
            db.add(PluginBinding(plugin_path=plugin["path"], category_id=default_category.id))
            bindings[plugin["path"]] = default_category.id

    if any(p["path"] not in bindings for p in plugins):
        await db.commit()

    return [
        PluginOut(
            name=p["name"],
            version=p["version"],
            description=p["description"],
            path=p["path"],
            category=categories.get(bindings.get(p["path"]), "默认"),
        )
        for p in plugins
    ]
```

- [ ] **Step 2: 修改测试验证分类字段**

```python
# backend/tests/test_skills_api.py
import pytest


async def test_skills_endpoint_returns_list(logged_in_client, monkeypatch, tmp_path):
    c = logged_in_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo desc\n---\n", encoding="utf-8"
    )
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)
    r = await c.get("/api/skills")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "demo-skill"
    assert data[0]["category"] == "默认"


async def test_skills_endpoint_returns_category(logged_in_client, monkeypatch, tmp_path):
    c = logged_in_client
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "cat-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: cat-skill\n---\n", encoding="utf-8")
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)

    # 创建分类和绑定
    from app.db.session import async_session
    from app.models import Category, SkillBinding
    async with async_session() as session:
        cat = Category(name="测试分类")
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        session.add(SkillBinding(skill_name="cat-skill", category_id=cat.id))
        await session.commit()

    r = await c.get("/api/skills")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["category"] == "测试分类"
```

```python
# backend/tests/test_plugins_api.py
import pytest


async def test_plugins_endpoint_returns_list(logged_in_client, monkeypatch, tmp_path):
    c = logged_in_client
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    plugin_dir = plugins_dir / "demo-plugin"
    plugin_dir.mkdir()
    (plugin_dir / ".claude-plugin").mkdir()
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "demo-plugin", "version": "1.0.0", "description": "demo"}',
        encoding="utf-8",
    )
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)
    r = await c.get("/api/plugins")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "demo-plugin"
    assert data[0]["category"] == "默认"
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/moses/Projects/guoke/智能体平台/backend
pytest tests/test_skills_api.py tests/test_plugins_api.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/agents.py backend/tests/test_skills_api.py backend/tests/test_plugins_api.py
git commit -m "feat: 技能/插件列表 API 返回分类信息"
```

---

### Task 5: 技能管理 API 改造

**Files:**
- Modify: `backend/app/api/routes/admin_skills.py`
- Test: `backend/tests/test_admin_skills_api.py`

- [ ] **Step 1: 修改 admin_skills.py**

```python
# backend/app/api/routes/admin_skills.py
"""管理员技能管理 API（只读文件查看 + 上传/删除）。-"""

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


# ... existing file CRUD routes unchanged ...


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

    # 检查引用
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
```

- [ ] **Step 2: 写测试**

```python
# backend/tests/test_admin_skills_api.py
# 在现有测试后添加

async def test_upload_skill_with_category(admin_client, monkeypatch, tmp_path):
    import zipfile
    import io

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)

    # 创建分类
    from app.db.session import async_session
    from app.models import Category
    async with async_session() as session:
        cat = Category(name="上传测试分类")
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        cat_id = cat.id

    # 创建 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("upload-skill/SKILL.md", "---\nname: upload-skill\n---\n")
    buf.seek(0)

    r = await admin_client.post(
        "/api/admin/skills/upload",
        data={"category_id": cat_id},
        files={"file": ("skill.zip", buf, "application/zip")},
    )
    assert r.status_code == 200

    # 验证绑定
    from app.models import SkillBinding
    async with async_session() as session:
        result = await session.execute(
            select(SkillBinding).where(SkillBinding.skill_name == "upload-skill")
        )
        binding = result.scalar_one()
        assert binding.category_id == cat_id


async def test_delete_skill_removes_binding(admin_client, monkeypatch, tmp_path):
    import zipfile
    import io

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("app.modules.catalog.skills._skills_dir", lambda: skills_dir)

    # 创建技能 ZIP 并上传
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("del-skill/SKILL.md", "---\nname: del-skill\n---\n")
    buf.seek(0)

    from app.db.session import async_session
    from app.models import Category
    async with async_session() as session:
        cat = await session.execute(select(Category).where(Category.name == "默认"))
        default_id = cat.scalar_one().id

    await admin_client.post(
        "/api/admin/skills/upload",
        data={"category_id": default_id},
        files={"file": ("skill.zip", buf, "application/zip")},
    )

    # 删除技能
    r = await admin_client.delete("/api/admin/skills/del-skill")
    assert r.status_code == 204

    # 验证绑定已删除
    from app.models import SkillBinding
    async with async_session() as session:
        result = await session.execute(
            select(SkillBinding).where(SkillBinding.skill_name == "del-skill")
        )
        assert result.scalar_one_or_none() is None
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/moses/Projects/guoke/智能体平台/backend
pytest tests/test_admin_skills_api.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/admin_skills.py backend/tests/test_admin_skills_api.py
git commit -m "feat: 技能上传和删除 API 支持分类绑定"
```

---

### Task 6: 插件管理 API 改造

**Files:**
- Modify: `backend/app/api/routes/admin_plugins.py`
- Test: `backend/tests/test_admin_plugins_api.py`

- [ ] **Step 1: 修改 admin_plugins.py**

```python
# backend/app/api/routes/admin_plugins.py
"""管理员插件管理 API（只读文件查看 + 上传/删除）。-"""

import shutil

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
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

    # 计算相对路径
    rel_path = name

    # UPSERT 绑定记录
    stmt = (
        insert(PluginBinding)
        .values(plugin_path=rel_path, category_id=category_id)
        .on_conflict_do_update(
            index_elements=["plugin_path"],
            set_={"category_id": category_id},
        )
    )
    await db.execute(stmt)
    await db.commit()

    return {"name": name, "message": f"插件 '{name}' 上传成功"}


# ... existing file routes unchanged ...


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
```

- [ ] **Step 2: 写测试**

```python
# backend/tests/test_admin_plugins_api.py
# 在现有测试后添加

async def test_upload_plugin_with_category(admin_client, monkeypatch, tmp_path):
    import zipfile
    import io

    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)

    # 创建分类
    from app.db.session import async_session
    from app.models import Category
    async with async_session() as session:
        cat = Category(name="插件测试分类")
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        cat_id = cat.id

    # 创建 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("upload-plugin/.claude-plugin/plugin.json", '{"name":"upload-plugin"}')
    buf.seek(0)

    r = await admin_client.post(
        "/api/admin/plugins/upload",
        data={"category_id": cat_id},
        files={"file": ("plugin.zip", buf, "application/zip")},
    )
    assert r.status_code == 200

    # 验证绑定
    from app.models import PluginBinding
    async with async_session() as session:
        result = await session.execute(
            select(PluginBinding).where(PluginBinding.plugin_path == "upload-plugin")
        )
        binding = result.scalar_one()
        assert binding.category_id == cat_id


async def test_delete_plugin_removes_binding(admin_client, monkeypatch, tmp_path):
    import zipfile
    import io

    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("app.modules.catalog.plugins._plugins_dir", lambda: plugins_dir)

    # 创建插件 ZIP 并上传
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("del-plugin/.claude-plugin/plugin.json", '{"name":"del-plugin"}')
    buf.seek(0)

    from app.db.session import async_session
    from app.models import Category
    async with async_session() as session:
        cat = await session.execute(select(Category).where(Category.name == "默认"))
        default_id = cat.scalar_one().id

    await admin_client.post(
        "/api/admin/plugins/upload",
        data={"category_id": default_id},
        files={"file": ("plugin.zip", buf, "application/zip")},
    )

    # 删除插件
    r = await admin_client.delete("/api/admin/plugins/del-plugin")
    assert r.status_code == 204

    # 验证绑定已删除
    from app.models import PluginBinding
    async with async_session() as session:
        result = await session.execute(
            select(PluginBinding).where(PluginBinding.plugin_path == "del-plugin")
        )
        assert result.scalar_one_or_none() is None
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/moses/Projects/guoke/智能体平台/backend
pytest tests/test_admin_plugins_api.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/admin_plugins.py backend/tests/test_admin_plugins_api.py
git commit -m "feat: 插件上传和删除 API 支持分类绑定"
```

---

### Task 7: 前端类型和 API 客户端更新

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: 修改 types/index.ts**

```typescript
// frontend/src/types/index.ts
// ... existing types ...

export interface Skill {
  name: string;
  description: string;
  category: string;
}

export interface Plugin {
  name: string;
  version: string;
  description: string;
  path: string;
  category: string;
}

export interface Category {
  id: number;
  name: string;
}

// ... rest unchanged ...
```

- [ ] **Step 2: 修改 api/client.ts**

```typescript
// frontend/src/api/client.ts
// ... existing imports ...
import type {
  Agent,
  AgentCommand,
  Category,  // 新增
  ChatEvent,
  ConversionTask,
  FileNode,
  Plugin,
  Session,
  Skill,
  UploadedFile,
  UploadBatch,
  UserMe,
  WorkspaceNode,
} from "@/types";

// ... existing api object ...

export const api = {
  // ... existing APIs ...

  // 分类管理
  categories: () => request<Category[]>("/api/admin/categories"),

  createCategory: (name: string) =>
    request<Category>("/api/admin/categories", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  renameCategory: (id: number, name: string) =>
    request<Category>(`/api/admin/categories/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  deleteCategory: (id: number) =>
    request<void>(`/api/admin/categories/${id}`, { method: "DELETE" }),

  // 管理员 — 技能上传（改造为支持分类）
  adminUploadSkill: async (file: File, categoryId: number) => {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("category_id", String(categoryId));
    const res = await fetch("/api/admin/skills/upload", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    handleUnauthorizedResponse(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<{ name: string; message: string }>;
  },

  // 管理员 — 插件上传（改造为支持分类）
  adminUploadPlugin: async (file: File, categoryId: number) => {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("category_id", String(categoryId));
    const res = await fetch("/api/admin/plugins/upload", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    handleUnauthorizedResponse(res);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
    }
    return res.json() as Promise<{ name: string; message: string }>;
  },

  // ... rest unchanged ...
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: 前端类型和 API 客户端支持分类管理"
```

---

### Task 8: 前端页面改造

**Files:**
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 改造 SkillsPage 为按分类分组展示 + 分类管理 Tab + 上传弹窗**

由于 `SkillsPage.tsx` 当前约 1636 行，改造幅度大。以下是**关键代码变更指引**，完整文件需要在现有基础上做以下修改：

**A. 新增类型和状态：**

```typescript
// 在文件顶部新增导入
import type { Category } from "@/types";

// TabKey 增加 "categories"
type TabKey = "skills" | "plugins" | "categories";

// 新增状态
const [categories, setCategories] = useState<Category[]>([]);

// 上传弹窗状态
const [uploadModalOpen, setUploadModalOpen] = useState(false);
const [uploadCategoryId, setUploadCategoryId] = useState<number | null>(null);

// 分类管理状态
const [newCategoryName, setNewCategoryName] = useState("");
const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null);
const [editingCategoryName, setEditingCategoryName] = useState("");
const [creatingCategory, setCreatingCategory] = useState(false);
const [categoryActionLoading, setCategoryActionLoading] = useState(false);
```

**B. 修改 reload 函数加载分类：**

```typescript
const reload = useCallback(async () => {
  setLoading(true);
  try {
    const [sk, pl, cats] = await Promise.all([
      api.skills(),
      api.plugins(),
      api.categories(),
    ]);
    setSkills(sk);
    setPlugins(pl);
    setCategories(cats);
    // 默认选中第一个分类（通常是"默认"）
    if (cats.length > 0 && uploadCategoryId === null) {
      setUploadCategoryId(cats[0].id);
    }
  } catch {
    // 静默
  } finally {
    setLoading(false);
  }
}, [uploadCategoryId]);
```

**C. 新增分类分组逻辑：**

```typescript
// 按分类分组的技能
const groupedSkills = useMemo(() => {
  const groups: Record<string, Skill[]> = {};
  for (const s of filteredSkills) {
    const cat = s.category || "默认";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(s);
  }
  // 排序：默认在前，其余按名称
  const sorted: Record<string, Skill[]> = {};
  const defaultItems = groups["默认"];
  if (defaultItems) sorted["默认"] = defaultItems;
  for (const name of Object.keys(groups).sort()) {
    if (name !== "默认") sorted[name] = groups[name];
  }
  return sorted;
}, [filteredSkills]);

// 按分类分组的插件
const groupedPlugins = useMemo(() => {
  const groups: Record<string, Plugin[]> = {};
  for (const p of filteredPlugins) {
    const cat = p.category || "默认";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(p);
  }
  const sorted: Record<string, Plugin[]> = {};
  const defaultItems = groups["默认"];
  if (defaultItems) sorted["默认"] = defaultItems;
  for (const name of Object.keys(groups).sort()) {
    if (name !== "默认") sorted[name] = groups[name];
  }
  return sorted;
}, [filteredPlugins]);
```

**D. 新增分类管理操作函数：**

```typescript
const createCategory = async () => {
  const name = newCategoryName.trim();
  if (!name) return;
  setCreatingCategory(true);
  try {
    await api.createCategory(name);
    setNewCategoryName("");
    await reload();
  } catch (err) {
    alert("创建失败: " + (err as Error).message);
  } finally {
    setCreatingCategory(false);
  }
};

const renameCategory = async (id: number) => {
  const name = editingCategoryName.trim();
  if (!name) return;
  setCategoryActionLoading(true);
  try {
    await api.renameCategory(id, name);
    setEditingCategoryId(null);
    setEditingCategoryName("");
    await reload();
  } catch (err) {
    alert("重命名失败: " + (err as Error).message);
  } finally {
    setCategoryActionLoading(false);
  }
};

const deleteCategory = async (id: number, name: string) => {
  if (!confirm(`确认删除分类 "${name}"? 该分类下的技能/插件将移到默认分类。`)) return;
  setCategoryActionLoading(true);
  try {
    await api.deleteCategory(id);
    await reload();
  } catch (err) {
    alert("删除失败: " + (err as Error).message);
  } finally {
    setCategoryActionLoading(false);
  }
};
```

**E. 修改上传流程为弹窗：**

```typescript
const triggerUpload = () => {
  setUploadModalOpen(true);
};

const closeUploadModal = () => {
  setUploadModalOpen(false);
  if (fileInputRef.current) fileInputRef.current.value = "";
};

const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0];
  if (!file || !uploadCategoryId) return;
  setUploading(true);
  try {
    if (tab === "skills") {
      await api.adminUploadSkill(file, uploadCategoryId);
    } else {
      await api.adminUploadPlugin(file, uploadCategoryId);
    }
    closeUploadModal();
    await reload();
  } catch (err) {
    alert("上传失败: " + ((err as Error).message || ""));
  } finally {
    setUploading(false);
    e.target.value = "";
  }
};
```

**F. 修改渲染部分：**

Tab 按钮增加分类管理：

```tsx
<TabButton
  active={tab === "skills"}
  label={`技能管理 · ${skills.length}`}
  onClick={() => { setTab("skills"); setSearchKw(""); }}
/>
<TabButton
  active={tab === "plugins"}
  label={`插件管理 · ${plugins.length}`}
  onClick={() => { setTab("plugins"); setSearchKw(""); }}
/>
<TabButton
  active={tab === "categories"}
  label="分类管理"
  onClick={() => { setTab("categories"); setSearchKw(""); }}
/>
```

技能/插件列表渲染改为按分类分组：

```tsx
// 在列表内容区域
{tab === "skills" && (
  Object.entries(groupedSkills).map(([catName, items]) => (
    <div key={catName} style={{ marginBottom: 24 }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        marginBottom: 12,
        paddingBottom: 8,
        borderBottom: "1px solid var(--line)",
      }}>
        <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>
          {catName}
        </span>
        <span style={{
          fontSize: 12,
          color: "var(--ink-3)",
          background: "var(--bg-2)",
          padding: "2px 8px",
          borderRadius: 10,
        }}>
          {items.length}
        </span>
      </div>
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
        gap: 12,
      }}>
        {items.map((item) => (
          <ItemCard
            key={item.name}
            name={item.name}
            description={item.description}
            fileCount={0}
            type="skill"
            onEdit={() => openEdit(item.name, "skill")}
            onDelete={() => askDelete(item.name, "skill")}
          />
        ))}
      </div>
    </div>
  ))
)}
```

插件列表同理。

分类管理 Tab 渲染：

```tsx
{tab === "categories" && (
  <div style={{ maxWidth: 600 }}>
    <div style={{
      display: "flex",
      flexDirection: "column",
      gap: 8,
      marginBottom: 20,
    }}>
      {categories.map((cat) => (
        <div
          key={cat.id}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid var(--line)",
            background: "var(--bg)",
          }}
        >
          {editingCategoryId === cat.id ? (
            <>
              <Input
                value={editingCategoryName}
                onChange={(e) => setEditingCategoryName(e.target.value)}
                autoFocus
                containerStyle={{ flex: 1 }}
              />
              <Btn
                variant="ghost"
                size="sm"
                onClick={() => { setEditingCategoryId(null); setEditingCategoryName(""); }}
                disabled={categoryActionLoading}
              >
                取消
              </Btn>
              <Btn
                variant="primary"
                size="sm"
                onClick={() => renameCategory(cat.id)}
                disabled={categoryActionLoading || !editingCategoryName.trim()}
              >
                确认
              </Btn>
            </>
          ) : (
            <>
              <span style={{ flex: 1, fontSize: 14, color: "var(--ink)" }}>
                {cat.name}
                {cat.name === "默认" && (
                  <span style={{ fontSize: 12, color: "var(--ink-3)", marginLeft: 8 }}>
                    (不可删除)
                  </span>
                )}
              </span>
              {cat.name !== "默认" && (
                <>
                  <button
                    onClick={() => {
                      setEditingCategoryId(cat.id);
                      setEditingCategoryName(cat.name);
                    }}
                    className="focus-ring"
                    style={iconBtnStyle}
                    title="重命名"
                  >
                    <I.Edit size={14} />
                  </button>
                  <button
                    onClick={() => deleteCategory(cat.id, cat.name)}
                    className="focus-ring"
                    style={{ ...iconBtnStyle, color: "var(--danger)" }}
                    title="删除"
                  >
                    <I.Trash size={14} />
                  </button>
                </>
              )}
            </>
          )}
        </div>
      ))}
    </div>
    <div style={{
      display: "flex",
      gap: 8,
      alignItems: "center",
      paddingTop: 12,
      borderTop: "1px solid var(--line)",
    }}>
      <Input
        placeholder="新分类名称"
        value={newCategoryName}
        onChange={(e) => setNewCategoryName(e.target.value)}
        containerStyle={{ flex: 1 }}
      />
      <Btn
        variant="primary"
        onClick={createCategory}
        disabled={creatingCategory || !newCategoryName.trim()}
      >
        {creatingCategory ? "创建中…" : "新建分类"}
      </Btn>
    </div>
  </div>
)}
```

**G. 上传弹窗组件：**

```tsx
{uploadModalOpen && tab !== "categories" && (
  <>
    <div
      onClick={closeUploadModal}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.32)",
        zIndex: 42,
      }}
    />
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 43,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          pointerEvents: "auto",
          width: "min(420px, 100%)",
          background: "var(--bg)",
          border: "1px solid var(--line)",
          borderRadius: 12,
          boxShadow: "var(--shadow-lg)",
          padding: "20px 20px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <h3 style={{
          fontFamily: "var(--serif)",
          fontSize: 16,
          fontWeight: 500,
          color: "var(--ink)",
          margin: 0,
        }}>
          上传{tab === "skills" ? "技能" : "插件"}
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label style={{ fontSize: 13, color: "var(--ink-2)" }}>选择分类</label>
          <select
            value={uploadCategoryId ?? ""}
            onChange={(e) => setUploadCategoryId(Number(e.target.value))}
            style={{
              padding: "8px 10px",
              borderRadius: 8,
              border: "1px solid var(--line)",
              background: "var(--bg)",
              color: "var(--ink)",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>{cat.name}</option>
            ))}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label style={{ fontSize: 13, color: "var(--ink-2)" }}>选择文件</label>
          <Btn
            variant="secondary"
            onClick={() => fileInputRef.current?.click()}
            icon={<I.Upload size={14} />}
          >
            选择 ZIP 文件
          </Btn>
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            onChange={onFileChange}
            style={{ display: "none" }}
          />
        </div>
        <div style={{
          display: "flex",
          justifyContent: "flex-end",
          gap: 8,
        }}>
          <Btn variant="ghost" onClick={closeUploadModal} disabled={uploading}>
            取消
          </Btn>
          <Btn
            variant="primary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || !uploadCategoryId}
            icon={uploading ? <I.Loader size={14} /> : <I.Upload size={14} />}
          >
            {uploading ? "上传中…" : "确认上传"}
          </Btn>
        </div>
      </div>
    </div>
  </>
)}
```

- [ ] **Step 2: 验证前端构建**

```bash
cd /Users/moses/Projects/guoke/智能体平台/frontend
npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "feat: 前端技能/插件分类展示和管理"
```

---

## 自检

**1. Spec 覆盖检查：**

| Spec 需求 | 对应 Task |
|-----------|-----------|
| 分类保存在数据库 | Task 1 |
| 共用一套分类 | Task 1 (categories 单表) |
| 初始"默认"分类 | Task 1 (migrations) |
| 上传弹窗选择分类 | Task 5, 6, 8 |
| 列表按分类展示 | Task 4, 8 |
| 分类显示数量 | Task 8 (前端计算) |
| 分类管理 CRUD | Task 3 |
| 默认分类不可删除 | Task 3 |
| 删除分类移到默认 | Task 3 |
| 现有内容归为默认 | Task 4 (延迟初始化) |

**2. 占位符扫描：** 无 TBD/TODO/"implement later"。

**3. 类型一致性：**
- `CategoryOut` / `CategoryCreate` / `CategoryRename` 在 Task 2 定义，Task 3 使用
- `SkillOut.category` / `PluginOut.category` 在 Task 2 定义，Task 4 使用
- `Category` 类型在 Task 7 定义，Task 8 使用
- `api.categories()` / `api.createCategory()` 等在 Task 7 定义，Task 8 使用

一致，无冲突。
