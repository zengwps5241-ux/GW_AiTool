"""数据库初始化与兼容性迁移。"""

from sqlalchemy import text

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine

_settings = get_settings()


async def init_db() -> None:
    """初始化建表，兼容迁移（添加列、插入默认智能体、清理旧会话）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS team_spaces ("
            "id SERIAL PRIMARY KEY, "
            "name VARCHAR NOT NULL, "
            "description TEXT NULL, "
            "owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT, "
            "created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT, "
            "lock_holder_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL, "
            "lock_acquired_at TIMESTAMP WITH TIME ZONE NULL, "
            "lock_note TEXT NULL, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS team_space_members ("
            "id SERIAL PRIMARY KEY, "
            "space_id INTEGER NOT NULL REFERENCES team_spaces(id) ON DELETE CASCADE, "
            "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
            "role VARCHAR NOT NULL DEFAULT 'reader', "
            "added_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "CONSTRAINT uq_team_space_members_space_user UNIQUE(space_id, user_id)"
            ")"
        ))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_team_spaces_owner ON team_spaces(owner_user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_team_spaces_updated ON team_spaces(updated_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_team_space_members_user ON team_space_members(user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_team_space_members_space ON team_space_members(space_id)"))

        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name='chat_sessions' AND column_name='agent_id'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE chat_sessions ADD COLUMN agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL"
            ))

        for table_name, col, col_type in [
            ("chat_sessions", "workspace_kind", "VARCHAR NOT NULL DEFAULT 'personal'"),
            ("chat_sessions", "team_space_id", "INTEGER NULL REFERENCES team_spaces(id) ON DELETE CASCADE"),
            ("chat_sessions", "is_shared", "BOOLEAN NOT NULL DEFAULT FALSE"),
            # M3.4.2：项目级会话绑定（FK projects，删除项目→SET NULL）
            ("chat_sessions", "project_id", "INTEGER NULL REFERENCES projects(id) ON DELETE SET NULL"),
        ]:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                f"WHERE table_name='{table_name}' AND column_name='{col}'"
            ))
            if result.scalar() == 0:
                await conn.execute(text(
                    f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}"
                ))

        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sessions_team_space "
            "ON chat_sessions (team_space_id, updated_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sessions_workspace "
            "ON chat_sessions (workspace_kind, team_space_id, updated_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sessions_shared "
            "ON chat_sessions (team_space_id, is_shared, updated_at)"
        ))
        # M3.4.2：按项目列出会话的索引
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sessions_project "
            "ON chat_sessions (project_id, updated_at)"
        ))

        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name='agents' AND column_name='plugins'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE agents ADD COLUMN plugins VARCHAR NOT NULL DEFAULT ''"
            ))

        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name='agents' AND column_name='code'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE agents ADD COLUMN code VARCHAR NOT NULL DEFAULT ''"
            ))
            await conn.execute(text(
                "UPDATE agents SET code = 'agent-' || id WHERE code = ''"
            ))

        # 企业微信认证相关字段迁移
        for col, col_type in [
            ("wechat_user_id", "VARCHAR"),
            ("display_name", "VARCHAR"),
            ("avatar_url", "VARCHAR"),
            ("department", "VARCHAR"),
            ("department_ids", "JSON"),
            ("position", "VARCHAR"),
            ("mobile", "VARCHAR"),
            ("email", "VARCHAR"),
            ("auth_source", "VARCHAR NOT NULL DEFAULT 'local'"),
        ]:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                f"WHERE table_name='users' AND column_name='{col}'"
            ))
            if result.scalar() == 0:
                await conn.execute(text(
                    f"ALTER TABLE users ADD COLUMN {col} {col_type}"
                ))

        # 用户角色字段迁移
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name='users' AND column_name='role'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'user'"
            ))

        # 自建认证体系新增字段
        for col, col_type in [
            ("phone", "VARCHAR UNIQUE NULL"),
            ("status", "VARCHAR NOT NULL DEFAULT 'active'"),
            ("registration_source", "VARCHAR NOT NULL DEFAULT 'admin_create'"),
        ]:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                f"WHERE table_name='users' AND column_name='{col}'"
            ))
            if result.scalar() == 0:
                await conn.execute(text(
                    f"ALTER TABLE users ADD COLUMN {col} {col_type}"
                ))

        # departments 表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='departments'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE departments ("
                "id INTEGER PRIMARY KEY, "
                "name VARCHAR NOT NULL, "
                "parent_id INTEGER NULL, "
                '"order" INTEGER NULL, '
                "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))

        # 登录用户姓名白名单表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='login_whitelist_users'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE login_whitelist_users ("
                "id SERIAL PRIMARY KEY, "
                "name VARCHAR UNIQUE NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))

        # 登录部门白名单表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='login_whitelist_departments'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE login_whitelist_departments ("
                "id SERIAL PRIMARY KEY, "
                "department_id INTEGER UNIQUE NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))

        # 为 wechat_user_id 添加唯一约束(如果不存在)
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.table_constraints tc "
            "JOIN information_schema.constraint_column_usage ccu "
            "ON tc.constraint_name = ccu.constraint_name "
            "WHERE tc.table_name = 'users' "
            "AND tc.constraint_type = 'UNIQUE' "
            "AND ccu.column_name = 'wechat_user_id'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE users ADD CONSTRAINT uq_users_wechat_user_id "
                "UNIQUE (wechat_user_id)"
            ))

        # conversion_tasks 表迁移
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='conversion_tasks'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE conversion_tasks ("
                "id SERIAL PRIMARY KEY, "
                "username VARCHAR NOT NULL, "
                "source_path VARCHAR NOT NULL, "
                "source_name VARCHAR NOT NULL, "
                "status VARCHAR NOT NULL DEFAULT 'queued', "
                "error_message TEXT NULL, "
                "markdown_path VARCHAR NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "started_at TIMESTAMP WITH TIME ZONE NULL, "
                "finished_at TIMESTAMP WITH TIME ZONE NULL"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_conversion_tasks_user_created "
                "ON conversion_tasks (username, created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_conversion_tasks_status "
                "ON conversion_tasks (status)"
            ))

        for col, col_type in [
            ("workspace_kind", "VARCHAR NOT NULL DEFAULT 'personal'"),
            ("team_space_id", "INTEGER NULL"),
        ]:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                f"WHERE table_name='conversion_tasks' AND column_name='{col}'"
            ))
            if result.scalar() == 0:
                await conn.execute(text(
                    f"ALTER TABLE conversion_tasks ADD COLUMN {col} {col_type}"
                ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_conversion_tasks_workspace_created "
            "ON conversion_tasks (workspace_kind, team_space_id, created_at)"
        ))

        await conn.execute(text(
            "UPDATE conversion_tasks "
            "SET status='queued', started_at=NULL, finished_at=NULL, error_message=NULL "
            "WHERE status='running'"
        ))

        # upload_tasks 表迁移
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='upload_tasks'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE upload_tasks ("
                "id SERIAL PRIMARY KEY, "
                "username VARCHAR NOT NULL, "
                "target_dir VARCHAR NOT NULL DEFAULT '', "
                "relative_path VARCHAR NOT NULL, "
                "filename VARCHAR NOT NULL, "
                "status VARCHAR NOT NULL DEFAULT 'queued', "
                "progress INTEGER NOT NULL DEFAULT 0, "
                "size INTEGER NOT NULL DEFAULT 0, "
                "saved_path VARCHAR NULL, "
                "error_message TEXT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "started_at TIMESTAMP WITH TIME ZONE NULL, "
                "finished_at TIMESTAMP WITH TIME ZONE NULL, "
                "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_upload_tasks_user_created "
            "ON upload_tasks (username, created_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_upload_tasks_user_status "
            "ON upload_tasks (username, status)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_upload_tasks_status "
            "ON upload_tasks (status)"
        ))
        for col, col_type in [
            ("workspace_kind", "VARCHAR NOT NULL DEFAULT 'personal'"),
            ("team_space_id", "INTEGER NULL"),
        ]:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                f"WHERE table_name='upload_tasks' AND column_name='{col}'"
            ))
            if result.scalar() == 0:
                await conn.execute(text(
                    f"ALTER TABLE upload_tasks ADD COLUMN {col} {col_type}"
                ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_upload_tasks_workspace_created "
            "ON upload_tasks (workspace_kind, team_space_id, created_at)"
        ))
        await conn.execute(text(
            "UPDATE upload_tasks "
            "SET status='failed', "
            "error_message=COALESCE(error_message, '服务重启导致上传中断，请重新上传'), "
            "finished_at=COALESCE(finished_at, CURRENT_TIMESTAMP) "
            "WHERE status='running'"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_upload_tasks_one_running_per_user "
            "ON upload_tasks (username) WHERE status='running'"
        ))

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

        default_category_result = await conn.execute(text(
            "SELECT id FROM categories WHERE name = '默认' LIMIT 1"
        ))
        default_category_id = default_category_result.scalar()

        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name='agents' AND column_name='category_id'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "ALTER TABLE agents ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL"
            ))

        if default_category_id is not None:
            await conn.execute(text(
                f"UPDATE agents SET category_id = {default_category_id} WHERE category_id IS NULL"
            ))

        result = await conn.execute(text("SELECT COUNT(*) FROM agents"))
        if result.scalar() == 0:
            await conn.execute(text(
                "INSERT INTO agents (name, code, system_prompt, skills, plugins, category_id, is_default) "
                f"VALUES ('国科智能助手', 'default-agent', NULL, '', '', {default_category_id or 'NULL'}, true)"
            ))

        await conn.execute(text(
            "DELETE FROM chat_sessions WHERE agent_id IS NULL"
        ))

        # 问题反馈表迁移
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='feedback_issues'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE feedback_issues ("
                "id SERIAL PRIMARY KEY, "
                "title VARCHAR(200) NOT NULL, "
                "description TEXT NOT NULL DEFAULT '', "
                "reporter_username VARCHAR NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_feedback_issues_created "
                "ON feedback_issues (created_at DESC)"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_feedback_issues_reporter "
                "ON feedback_issues (reporter_username)"
            ))

        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='feedback_attachments'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE feedback_attachments ("
                "id SERIAL PRIMARY KEY, "
                "issue_id INTEGER NOT NULL REFERENCES feedback_issues(id) ON DELETE CASCADE, "
                "filename VARCHAR(255) NOT NULL, "
                "content_type VARCHAR(100) NOT NULL, "
                "file_path VARCHAR(500) NOT NULL, "
                "size INTEGER NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_feedback_attachments_issue "
                "ON feedback_attachments (issue_id)"
            ))

        # usage_events 表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='usage_events'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE usage_events ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "username VARCHAR NOT NULL, "
                "session_id VARCHAR NOT NULL, "
                "agent_id INTEGER NULL, "
                "agent_name VARCHAR NULL, "
                "agent_code VARCHAR NULL, "
                "started_at TIMESTAMP WITH TIME ZONE NOT NULL, "
                "ended_at TIMESTAMP WITH TIME ZONE NOT NULL, "
                "status VARCHAR NOT NULL, "
                "stop_reason VARCHAR NULL, "
                "input_tokens INTEGER NOT NULL DEFAULT 0, "
                "output_tokens INTEGER NOT NULL DEFAULT 0, "
                "total_tokens INTEGER NOT NULL DEFAULT 0, "
                "duration_ms INTEGER NULL, "
                "duration_api_ms INTEGER NULL, "
                "total_cost_usd NUMERIC(12, 6) NULL, "
                "sdk_usage_json JSON NULL, "
                "sdk_model_usage_json JSON NULL, "
                "error_message TEXT NULL"
                ")"
            ))
            await conn.execute(text("CREATE INDEX idx_usage_events_started_at ON usage_events (started_at)"))
            await conn.execute(text("CREATE INDEX idx_usage_events_user_started ON usage_events (user_id, started_at)"))
            await conn.execute(text("CREATE INDEX idx_usage_events_agent_started ON usage_events (agent_id, started_at)"))
            await conn.execute(text("CREATE INDEX idx_usage_events_status_started ON usage_events (status, started_at)"))

        # usage_resource_events 表
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='usage_resource_events'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE usage_resource_events ("
                "id SERIAL PRIMARY KEY, "
                "usage_event_id INTEGER NOT NULL REFERENCES usage_events(id) ON DELETE CASCADE, "
                "resource_type VARCHAR NOT NULL, "
                "resource_name VARCHAR NOT NULL, "
                "plugin_name VARCHAR NULL, "
                "source VARCHAR NOT NULL, "
                "tool_use_id VARCHAR NULL, "
                "is_error BOOLEAN NOT NULL DEFAULT FALSE, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            await conn.execute(text("CREATE INDEX idx_usage_resource_event ON usage_resource_events (usage_event_id)"))
            await conn.execute(text("CREATE INDEX idx_usage_resource_type_name ON usage_resource_events (resource_type, resource_name)"))
            await conn.execute(text("CREATE INDEX idx_usage_resource_plugin ON usage_resource_events (plugin_name)"))

        # intent_routing_logs 表（M3.3.1 consultant-router 路由日志）
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name='intent_routing_logs'"
        ))
        if result.scalar() == 0:
            await conn.execute(text(
                "CREATE TABLE intent_routing_logs ("
                "id SERIAL PRIMARY KEY, "
                "session_id VARCHAR NULL, "
                "project_id INTEGER NULL REFERENCES projects(id) ON DELETE SET NULL, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "prompt TEXT NOT NULL, "
                "intent_label VARCHAR NOT NULL, "
                "route_target VARCHAR NULL, "
                "confidence_source VARCHAR NOT NULL, "
                "llm_label VARCHAR NULL, "
                "llm_confidence DOUBLE PRECISION NULL, "
                "keyword_hits JSON NULL, "
                "llm_raw JSON NULL, "
                "final_prompt TEXT NOT NULL, "
                "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_intent_routing_session ON intent_routing_logs (session_id, created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_intent_routing_project ON intent_routing_logs (project_id, created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX idx_intent_routing_label ON intent_routing_logs (intent_label)"
            ))

        # business_map_drafts 表列迁移（M3.4.3 Chat 调整循环：草稿版本化）
        # previous_data 保留上一版草稿供 diff（§7.2），revision 为修订号（首次=1，更新+1）
        for col, col_type in [
            ("previous_data", "JSONB NULL"),
            ("revision", "INTEGER NOT NULL DEFAULT 1"),
        ]:
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                f"WHERE table_name='business_map_drafts' AND column_name='{col}'"
            ))
            if result.scalar() == 0:
                await conn.execute(text(
                    f"ALTER TABLE business_map_drafts ADD COLUMN {col} {col_type}"
                ))
