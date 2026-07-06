async def test_usage_models_are_registered():
    from app.models import Base

    assert "usage_events" in Base.metadata.tables
    assert "usage_resource_events" in Base.metadata.tables

    usage_table = Base.metadata.tables["usage_events"]
    resource_table = Base.metadata.tables["usage_resource_events"]

    assert usage_table.c.status.nullable is False
    assert usage_table.c.input_tokens.default.arg == 0
    assert usage_table.c.output_tokens.default.arg == 0
    assert usage_table.c.total_tokens.default.arg == 0
    assert resource_table.c.usage_event_id.nullable is False
    assert resource_table.c.resource_type.nullable is False
    assert resource_table.c.resource_name.nullable is False

    usage_indexes = {index.name for index in usage_table.indexes}
    resource_indexes = {index.name for index in resource_table.indexes}

    assert "idx_usage_events_started_at" in usage_indexes
    assert "idx_usage_events_user_started" in usage_indexes
    assert "idx_usage_events_agent_started" in usage_indexes
    assert "idx_usage_events_status_started" in usage_indexes
    assert "idx_usage_resource_event" in resource_indexes
    assert "idx_usage_resource_type_name" in resource_indexes
    assert "idx_usage_resource_plugin" in resource_indexes
