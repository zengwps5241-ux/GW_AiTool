def test_serialize_text():
    from claude_agent_sdk import AssistantMessage, TextBlock
    from app.integrations.claude.serializers import serialize_block

    msg = AssistantMessage(
        content=[TextBlock(text="hello")],
        model="claude",
        parent_tool_use_id=None,
        error=None,
        usage=None,
        message_id="m1",
        stop_reason=None,
        session_id="s1",
        uuid="u1",
    )
    out = list(serialize_block(msg))
    assert out == [{"type": "assistant_text", "text": "hello"}]


def test_serialize_tool_use():
    from claude_agent_sdk import AssistantMessage, ToolUseBlock
    from app.integrations.claude.serializers import serialize_block

    msg = AssistantMessage(
        content=[ToolUseBlock(id="t1", name="Read", input={"path": "README.md"})],
        model="claude",
        parent_tool_use_id=None,
        error=None,
        usage=None,
        message_id="m2",
        stop_reason=None,
        session_id="s1",
        uuid="u2",
    )
    out = list(serialize_block(msg))
    assert out == [
        {"type": "tool_use", "id": "t1", "name": "Read", "input": {"path": "README.md"}}
    ]


def test_serialize_success_tool_result_keeps_status_without_content():
    from claude_agent_sdk import ToolResultBlock, UserMessage
    from app.integrations.claude.serializers import serialize_block

    msg = UserMessage(
        content=[ToolResultBlock(tool_use_id="t1", content="# Hello", is_error=False)],
        uuid="u3",
        parent_tool_use_id=None,
        tool_use_result=None,
    )
    assert list(serialize_block(msg)) == [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": False}
    ]


def test_serialize_error_tool_result_kept():
    from claude_agent_sdk import ToolResultBlock, UserMessage
    from app.integrations.claude.serializers import serialize_block

    msg = UserMessage(
        content=[ToolResultBlock(tool_use_id="t1", content="Read failed", is_error=True)],
        uuid="u3",
        parent_tool_use_id=None,
        tool_use_result=None,
    )
    out = list(serialize_block(msg))
    assert out == [
        {"type": "tool_result", "tool_use_id": "t1", "content": "Read failed", "is_error": True}
    ]


def test_serialize_history_success_tool_result_keeps_status_without_content():
    from claude_agent_sdk import SessionMessage
    from app.integrations.claude.serializers import serialize_block

    msg = SessionMessage(
        type="user",
        uuid="u-history-success",
        session_id="s1",
        message={
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "file content",
                    "is_error": False,
                }
            ]
        },
    )

    assert list(serialize_block(msg, streaming=False)) == [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": False}
    ]


def test_serialize_history_error_tool_result_kept():
    from claude_agent_sdk import SessionMessage
    from app.integrations.claude.serializers import serialize_block

    msg = SessionMessage(
        type="user",
        uuid="u-history-error",
        session_id="s1",
        message={
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "Permission denied",
                    "is_error": True,
                }
            ]
        },
    )

    assert list(serialize_block(msg, streaming=False)) == [
        {
            "type": "tool_result",
            "tool_use_id": "t1",
            "content": "Permission denied",
            "is_error": True,
        }
    ]


def test_serialize_result():
    from claude_agent_sdk import ResultMessage
    from app.integrations.claude.serializers import serialize_block

    msg = ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s1",
        stop_reason=None,
        total_cost_usd=None,
        usage=None,
        result=None,
        structured_output=None,
        model_usage=None,
        permission_denials=[],
        deferred_tool_use=None,
        errors=None,
        api_error_status=None,
        uuid="u4",
    )
    out = list(serialize_block(msg))
    assert out and out[0]["type"] == "result"
    assert out[0]["session_id"] == "s1"


def test_serialize_user_plain_text_skipped_in_streaming():
    """Streaming 中用户消息不重复推回前端(前端已自己显示),返回空。"""
    from claude_agent_sdk import TextBlock, UserMessage
    from app.integrations.claude.serializers import serialize_block

    msg = UserMessage(
        content=[TextBlock(text="hi")],
        uuid="u5",
        parent_tool_use_id=None,
        tool_use_result=None,
    )
    assert list(serialize_block(msg, streaming=True)) == []


def test_serialize_user_plain_text_kept_in_history():
    """加载历史时,用户消息要回显出来。"""
    from claude_agent_sdk import TextBlock, UserMessage
    from app.integrations.claude.serializers import serialize_block

    msg = UserMessage(
        content=[TextBlock(text="hi")],
        uuid="u6",
        parent_tool_use_id=None,
        tool_use_result=None,
    )
    assert list(serialize_block(msg, streaming=False)) == [
        {"type": "user_text", "text": "hi"}
    ]
