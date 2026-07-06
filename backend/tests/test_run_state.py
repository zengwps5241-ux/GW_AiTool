import asyncio

import pytest

from app.modules.sessions.run_state import InMemoryRunStateStore, RunEvent, RunStatus


def test_start_replaces_previous_run_and_resets_seq():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-old")
    old_seq = store.append_event("session-1", RunEvent(type="text", content="旧消息"))
    assert old_seq == 1

    store.start("session-1", "run-new")
    new_seq = store.append_event("session-1", RunEvent(type="text", content="新消息"))

    snapshot = store.snapshot("session-1")
    assert new_seq == 1
    assert snapshot is not None
    assert snapshot.run_id == "run-new"
    assert snapshot.latest_seq == 1
    assert [event.content for event in snapshot.events] == ["新消息"]


def test_finish_updates_status_and_error_message():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-1")

    store.finish("session-1", RunStatus.FAILED, error_message="执行失败")

    snapshot = store.snapshot("session-1")
    assert snapshot is not None
    assert snapshot.status == RunStatus.FAILED
    assert snapshot.error_message == "执行失败"


def test_finish_accepts_interrupted_status_string():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-1")

    store.finish("session-1", "interrupted")

    snapshot = store.snapshot("session-1")
    assert snapshot is not None
    assert snapshot.status == RunStatus.INTERRUPTED


def test_snapshot_after_seq_returns_only_later_events_but_keeps_latest_seq():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-1")
    store.append_event("session-1", RunEvent(type="text", content="一"))
    store.append_event("session-1", RunEvent(type="text", content="二"))
    store.append_event("session-1", RunEvent(type="text", content="三"))

    snapshot = store.snapshot("session-1", after_seq=1)

    assert snapshot is not None
    assert snapshot.latest_seq == 3
    assert [event.seq for event in snapshot.events] == [2, 3]
    assert [event.content for event in snapshot.events] == ["二", "三"]


def test_append_event_deepcopies_input_event():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-1")
    event = RunEvent(type="text", content="原始", payload={"items": ["a"]})

    store.append_event("session-1", event)
    event.content = "已修改"
    event.payload["items"].append("b")

    snapshot = store.snapshot("session-1")
    assert snapshot is not None
    assert snapshot.events[0].content == "原始"
    assert snapshot.events[0].payload == {"items": ["a"]}


def test_append_event_ignores_stale_run_id():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-old")
    store.start("session-1", "run-new")

    stale_seq = store.append_event(
        "session-1",
        RunEvent(type="text", content="旧消息"),
        run_id="run-old",
    )
    current_seq = store.append_event(
        "session-1",
        RunEvent(type="text", content="新消息"),
        run_id="run-new",
    )

    snapshot = store.snapshot("session-1")
    assert stale_seq is None
    assert current_seq == 1
    assert snapshot is not None
    assert [event.content for event in snapshot.events] == ["新消息"]


def test_finish_ignores_stale_run_id():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-old")
    store.start("session-1", "run-new")

    store.finish("session-1", RunStatus.FAILED, error_message="旧错误", run_id="run-old")
    store.finish("session-1", RunStatus.COMPLETED, run_id="run-new")

    snapshot = store.snapshot("session-1")
    assert snapshot is not None
    assert snapshot.status == RunStatus.COMPLETED
    assert snapshot.error_message is None


def test_is_current_run_tracks_latest_session_run():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-old")

    assert store.is_current_run("session-1", "run-old") is True

    store.start("session-1", "run-new")

    assert store.is_current_run("session-1", "run-old") is False
    assert store.is_current_run("session-1", "run-new") is True
    assert store.is_current_run("missing-session", "run-new") is False


def test_snapshot_deepcopies_returned_events():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-1")
    store.append_event(
        "session-1",
        RunEvent(type="text", content="原始", payload={"items": ["a"]}),
    )

    first_snapshot = store.snapshot("session-1")
    assert first_snapshot is not None
    first_snapshot.events[0].content = "已修改"
    first_snapshot.events[0].payload["items"].append("b")

    second_snapshot = store.snapshot("session-1")
    assert second_snapshot is not None
    assert second_snapshot.events[0].content == "原始"
    assert second_snapshot.events[0].payload == {"items": ["a"]}


def test_text_char_limit_fails_and_keeps_only_error_event():
    store = InMemoryRunStateStore(max_text_chars_per_run=3)
    store.start("session-1", "run-1")

    seq = store.append_event("session-1", RunEvent(type="text", content="四个字啊"))

    snapshot = store.snapshot("session-1")
    assert seq == 1
    assert snapshot is not None
    assert snapshot.status == RunStatus.FAILED
    assert snapshot.error_message == "运行中消息缓存超过限制，请等待本轮完成后重新打开会话"
    assert len(snapshot.events) == 1
    assert snapshot.events[0].type == "error"
    assert snapshot.events[0].message == "运行中消息缓存超过限制，请等待本轮完成后重新打开会话"
    assert snapshot.events[0].content is None
    assert snapshot.events[0].seq == 1


def test_text_char_limit_disables_cache_after_failure():
    store = InMemoryRunStateStore(max_text_chars_per_run=3)
    store.start("session-1", "run-1")

    first_seq = store.append_event("session-1", RunEvent(type="text", content="四个字啊"))
    second_seq = store.append_event("session-1", RunEvent(type="text", content="后续消息"))

    snapshot = store.snapshot("session-1")
    assert first_seq == 1
    assert second_seq is None
    assert snapshot is not None
    assert snapshot.status == RunStatus.FAILED
    assert len(snapshot.events) == 1
    assert snapshot.events[0].type == "error"
    assert snapshot.events[0].message == "运行中消息缓存超过限制，请等待本轮完成后重新打开会话"
    assert snapshot.events[0].content is None
    assert snapshot.events[0].seq == 1


def test_event_count_limit_fails_and_keeps_only_error_event():
    store = InMemoryRunStateStore(max_events_per_run=1)
    store.start("session-1", "run-1")

    first_seq = store.append_event("session-1", RunEvent(type="text", content="一"))
    second_seq = store.append_event("session-1", RunEvent(type="text", content="二"))

    snapshot = store.snapshot("session-1")
    assert first_seq == 1
    assert second_seq == 2
    assert snapshot is not None
    assert snapshot.status == RunStatus.FAILED
    assert snapshot.error_message == "运行中消息缓存超过限制，请等待本轮完成后重新打开会话"
    assert len(snapshot.events) == 1
    assert snapshot.events[0].type == "error"
    assert snapshot.events[0].message == "运行中消息缓存超过限制，请等待本轮完成后重新打开会话"
    assert snapshot.events[0].content is None
    assert snapshot.events[0].seq == 2


def test_event_count_limit_disables_cache_after_failure():
    store = InMemoryRunStateStore(max_events_per_run=1)
    store.start("session-1", "run-1")

    first_seq = store.append_event("session-1", RunEvent(type="text", content="一"))
    second_seq = store.append_event("session-1", RunEvent(type="text", content="二"))
    third_seq = store.append_event("session-1", RunEvent(type="text", content="三"))

    snapshot = store.snapshot("session-1")
    assert first_seq == 1
    assert second_seq == 2
    assert third_seq is None
    assert snapshot is not None
    assert snapshot.status == RunStatus.FAILED
    assert len(snapshot.events) == 1
    assert snapshot.events[0].type == "error"
    assert snapshot.events[0].message == "运行中消息缓存超过限制，请等待本轮完成后重新打开会话"
    assert snapshot.events[0].content is None
    assert snapshot.events[0].seq == 2


@pytest.mark.asyncio
async def test_wait_for_change_wakes_after_append():
    store = InMemoryRunStateStore()
    store.start("session-1", "run-1")

    waiter = asyncio.create_task(
        store.wait_for_change("session-1", after_seq=0, timeout=1)
    )
    await asyncio.sleep(0)

    store.append_event("session-1", RunEvent(type="text", content="新消息"))

    assert await waiter is True


@pytest.mark.asyncio
async def test_wait_for_change_wakes_after_finish():
    store = InMemoryRunStateStore()
    store.start("sid-1", "run-1")

    waiter = asyncio.create_task(
        store.wait_for_change("sid-1", after_seq=0, timeout=1)
    )
    await asyncio.sleep(0)

    store.finish("sid-1", "completed")

    assert await waiter is True


@pytest.mark.asyncio
async def test_wait_for_change_wakes_after_run_restart():
    store = InMemoryRunStateStore()
    store.start("sid-1", "run-1")

    waiter = asyncio.create_task(
        store.wait_for_change("sid-1", after_seq=0, timeout=0.1)
    )
    await asyncio.sleep(0)

    store.start("sid-1", "run-2")

    assert await waiter is True


@pytest.mark.asyncio
async def test_wait_for_change_returns_false_on_timeout():
    store = InMemoryRunStateStore()
    store.start("sid-1", "run-1")

    changed = await store.wait_for_change("sid-1", after_seq=0, timeout=0.01)

    assert changed is False
