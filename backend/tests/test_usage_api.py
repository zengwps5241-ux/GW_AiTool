from datetime import datetime, timezone


async def _seed_usage():
    from app.db.session import async_session
    from app.models import UsageEvent, UsageResourceEvent, User

    async with async_session() as session:
        user = User(username="bob", password_hash="x", role="user")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        event = UsageEvent(
            user_id=user.id,
            username="bob",
            session_id="sid",
            agent_id=10,
            agent_name="分析助手",
            agent_code="analysis",
            started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
            status="success",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )
        session.add(event)
        await session.flush()
        session.add_all([
            UsageResourceEvent(
                usage_event_id=event.id,
                resource_type="skill",
                resource_name="employee-management",
                source="tool_use",
                is_error=False,
            ),
            UsageResourceEvent(
                usage_event_id=event.id,
                resource_type="plugin",
                resource_name="superpowers:brainstorming",
                plugin_name="superpowers",
                source="slash_command",
                is_error=False,
            ),
        ])
        await session.commit()


async def test_usage_summary_requires_admin(logged_in_client):
    res = await logged_in_client.get("/api/admin/usage/summary")
    assert res.status_code == 403


async def test_usage_summary_returns_overview_and_rankings(admin_client):
    await _seed_usage()

    res = await admin_client.get("/api/admin/usage/summary?range=custom&start=2026-05-20&end=2026-05-20")

    assert res.status_code == 200
    body = res.json()
    assert body["overview"]["call_count"] == 1
    assert body["overview"]["active_user_count"] == 1
    assert body["overview"]["total_tokens"] == 150
    assert body["agents"][0]["agent_name"] == "分析助手"
    assert body["agents"][0]["call_count"] == 1
    assert body["agents"][0]["active_user_count"] == 1
    assert body["agents"][0]["total_tokens"] == 150
    assert body["agents"][0]["error_count"] == 0
    assert body["skills"][0] == {"resource_name": "employee-management", "trigger_count": 1}
    assert body["plugins"][0] == {
        "plugin_name": "superpowers",
        "resource_name": "superpowers:brainstorming",
        "trigger_count": 1,
    }


async def test_usage_summary_timeseries_uses_shanghai_local_day(admin_client):
    """趋势分桶应按北京时间自然日统计，避免 UTC 日期错位。"""
    from app.db.session import async_session
    from app.models import UsageEvent, User

    async with async_session() as session:
        user = User(username="local-day", password_hash="x", role="user")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        session.add(UsageEvent(
            user_id=user.id,
            username=user.username,
            session_id="sid-local-day",
            started_at=datetime(2026, 5, 19, 16, 30, tzinfo=timezone.utc),
            ended_at=datetime(2026, 5, 19, 16, 31, tzinfo=timezone.utc),
            status="success",
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
        ))
        await session.commit()

    res = await admin_client.get("/api/admin/usage/summary?range=custom&start=2026-05-20&end=2026-05-21")

    assert res.status_code == 200
    buckets = [point["bucket"] for point in res.json()["timeseries"]]
    assert buckets == ["2026-05-20T00:00:00+08:00"]


async def test_usage_summary_filter_by_user(admin_client):
    """按用户id精确过滤应生效。"""
    from app.db.session import async_session
    from app.models import UsageEvent, User

    async with async_session() as session:
        u1 = User(username="alice", password_hash="x", role="user", display_name="爱丽丝")
        u2 = User(username="bob", password_hash="x", role="user", display_name="鲍勃")
        session.add_all([u1, u2])
        await session.commit()
        await session.refresh(u1)
        await session.refresh(u2)

        session.add_all([
            UsageEvent(
                user_id=u1.id, username="alice", session_id="s1",
                started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
                status="success", input_tokens=10, output_tokens=5, total_tokens=15,
            ),
            UsageEvent(
                user_id=u2.id, username="bob", session_id="s2",
                started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
                status="success", input_tokens=20, output_tokens=10, total_tokens=30,
            ),
        ])
        await session.commit()

    res = await admin_client.get("/api/admin/usage/summary?range=custom&start=2026-05-20&end=2026-05-20&user=alice")
    assert res.status_code == 200
    body = res.json()
    assert body["overview"]["call_count"] == 1
    assert body["overview"]["total_tokens"] == 15


async def test_usage_summary_filter_by_department(admin_client):
    """按部门模糊过滤应生效。"""
    from app.db.session import async_session
    from app.models import UsageEvent, User

    async with async_session() as session:
        u1 = User(username="alice", password_hash="x", role="user", department="研发部")
        u2 = User(username="bob", password_hash="x", role="user", department="产品部")
        session.add_all([u1, u2])
        await session.commit()
        await session.refresh(u1)
        await session.refresh(u2)

        session.add_all([
            UsageEvent(
                user_id=u1.id, username="alice", session_id="s1",
                started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
                status="success", input_tokens=10, output_tokens=5, total_tokens=15,
            ),
            UsageEvent(
                user_id=u2.id, username="bob", session_id="s2",
                started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
                status="success", input_tokens=20, output_tokens=10, total_tokens=30,
            ),
        ])
        await session.commit()

    res = await admin_client.get("/api/admin/usage/summary?range=custom&start=2026-05-20&end=2026-05-20&department=研发")
    assert res.status_code == 200
    body = res.json()
    assert body["overview"]["call_count"] == 1
    assert body["overview"]["total_tokens"] == 15


async def test_usage_users_search(admin_client):
    """用户模糊搜索端点应返回匹配的用户信息（姓名+部门+id）。"""
    from app.db.session import async_session
    from app.models import UsageEvent, User

    async with async_session() as session:
        u = User(username="alice", password_hash="x", role="user", display_name="爱丽丝", department="研发部")
        session.add(u)
        await session.commit()
        await session.refresh(u)
        session.add(UsageEvent(
            user_id=u.id, username="alice", session_id="s1",
            started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
            status="success", input_tokens=0, output_tokens=0, total_tokens=0,
        ))
        await session.commit()

    res = await admin_client.get("/api/admin/usage/users?q=爱丽")
    assert res.status_code == 200
    assert res.json() == [{"display_name": "爱丽丝", "department": "研发部", "username": "alice"}]


async def test_usage_departments_search(admin_client):
    """部门模糊搜索端点应返回匹配的部门名。"""
    from app.db.session import async_session
    from app.models import UsageEvent, User

    async with async_session() as session:
        u = User(username="alice", password_hash="x", role="user", department="研发部")
        session.add(u)
        await session.commit()
        await session.refresh(u)
        session.add(UsageEvent(
            user_id=u.id, username="alice", session_id="s1",
            started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
            status="success", input_tokens=0, output_tokens=0, total_tokens=0,
        ))
        await session.commit()

    res = await admin_client.get("/api/admin/usage/departments?q=研发")
    assert res.status_code == 200
    assert res.json() == ["研发部"]
