from datetime import datetime, timezone
from types import SimpleNamespace


def test_extract_token_counts_prefers_usage_fields():
    from app.modules.usage.service import extract_token_counts

    usage = {"input_tokens": 12, "output_tokens": 34}

    assert extract_token_counts(usage) == (12, 34, 46)


def test_extract_token_counts_supports_nested_model_usage():
    from app.modules.usage.service import extract_token_counts

    usage = None
    model_usage = {
        "claude-sonnet": {
            "input_tokens": 7,
            "output_tokens": 8,
        },
        "claude-haiku": {
            "input_tokens": 2,
            "output_tokens": 3,
        },
    }

    assert extract_token_counts(usage, model_usage) == (9, 11, 20)


def test_collect_resources_records_skill_tool_use_and_plugin_prefix():
    from app.modules.usage.service import collect_usage_resources

    resources = collect_usage_resources(
        prompt="普通问题",
        commands=[],
        tool_uses=[
            {"id": "t1", "name": "Skill", "input": {"skill": "employee-management"}},
            {"id": "t2", "name": "Skill", "input": {"skill": "superpowers:brainstorming"}},
        ],
        tool_results=[{"tool_use_id": "t2", "is_error": True}],
    )

    assert [r.resource_type for r in resources] == ["skill", "plugin"]
    assert resources[0].resource_name == "employee-management"
    assert resources[0].source == "tool_use"
    assert resources[1].resource_name == "superpowers:brainstorming"
    assert resources[1].plugin_name == "superpowers"
    assert resources[1].is_error is True


def test_collect_resources_records_valid_slash_commands_only():
    from app.modules.usage.service import collect_usage_resources

    resources = collect_usage_resources(
        prompt="/superpowers:brainstorming 请先设计\n/unknown 不应记录",
        commands=[
            {"name": "superpowers:brainstorming", "source": "plugin", "plugin": "superpowers"},
            {"name": "employee-management", "source": "skill", "plugin": None},
        ],
        tool_uses=[],
        tool_results=[],
    )

    assert len(resources) == 1
    assert resources[0].resource_type == "plugin"
    assert resources[0].resource_name == "superpowers:brainstorming"
    assert resources[0].source == "slash_command"


async def test_persist_usage_event_writes_main_and_resources(app_env):
    from app.db.session import async_session
    from app.models import Agent, ChatSession, UsageEvent, User
    from app.modules.usage.service import CollectedResource, persist_usage_event
    from sqlalchemy import select

    async with async_session() as session:
        user = User(username="alice", password_hash="x", display_name="Alice")
        agent = Agent(name="分析助手", code="analysis-agent")
        session.add_all([user, agent])
        await session.commit()
        await session.refresh(user)
        await session.refresh(agent)
        chat = ChatSession(id="sid-1", user_id=user.id, agent_id=agent.id, title="t")
        session.add(chat)
        await session.commit()

    await persist_usage_event(
        user=SimpleNamespace(id=user.id, username="alice"),
        session_id="sid-1",
        agent=SimpleNamespace(id=agent.id, name="分析助手", code="analysis-agent"),
        started_at=datetime(2026, 5, 20, 1, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 20, 1, 1, tzinfo=timezone.utc),
        status="success",
        stop_reason="end_turn",
        usage={"input_tokens": 10, "output_tokens": 20},
        model_usage=None,
        duration_ms=1000,
        duration_api_ms=900,
        total_cost_usd=None,
        error_message=None,
        resources=[
            CollectedResource(
                resource_type="skill",
                resource_name="employee-management",
                plugin_name=None,
                source="tool_use",
                tool_use_id="t1",
                is_error=False,
            )
        ],
    )

    from sqlalchemy.orm import selectinload

    async with async_session() as session:
        event = (await session.execute(
            select(UsageEvent).options(selectinload(UsageEvent.resources))
        )).scalar_one()
        assert event.username == "alice"
        assert event.agent_name == "分析助手"
        assert event.input_tokens == 10
        assert event.output_tokens == 20
        assert event.total_tokens == 30
        assert len(event.resources) == 1
        assert event.resources[0].resource_name == "employee-management"
