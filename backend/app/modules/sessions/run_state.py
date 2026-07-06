import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


RUN_CACHE_LIMIT_ERROR = "运行中消息缓存超过限制，请等待本轮完成后重新打开会话"


class RunStatus(StrEnum):
    """运行状态，用于恢复流判断本轮是否仍可继续等待。"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class RunEvent:
    type: str
    content: str | None = None
    message: str | None = None
    seq: int = 0
    payload: dict[str, Any] | None = None


@dataclass
class RunSnapshot:
    session_id: str
    run_id: str
    status: RunStatus
    latest_seq: int
    events: list[RunEvent] = field(default_factory=list)
    error_message: str | None = None


@dataclass
class _RunState:
    session_id: str
    run_id: str
    status: RunStatus = RunStatus.RUNNING
    latest_seq: int = 0
    events: list[RunEvent] = field(default_factory=list)
    error_message: str | None = None
    text_chars: int = 0
    cache_enabled: bool = True


@dataclass
class _SessionWaiter:
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    loop: asyncio.AbstractEventLoop | None = None


class InMemoryRunStateStore:
    def __init__(
        self,
        max_events_per_run: int = 2000,
        max_text_chars_per_run: int = 300_000,
    ) -> None:
        self.max_events_per_run = max_events_per_run
        self.max_text_chars_per_run = max_text_chars_per_run
        self._states: dict[str, _RunState] = {}
        self._waiters: dict[str, _SessionWaiter] = {}

    def start(self, session_id: str, run_id: str) -> None:
        self._states[session_id] = _RunState(session_id=session_id, run_id=run_id)
        waiter = self._waiter_for(session_id)
        self._remember_running_loop(waiter)
        self._notify_change(waiter)

    def append_event(
        self,
        session_id: str,
        event: RunEvent,
        run_id: str | None = None,
    ) -> int | None:
        state = self._states.get(session_id)
        if state is None or not state.cache_enabled:
            return None
        if run_id is not None and state.run_id != run_id:
            return None

        waiter = self._waiter_for(session_id)
        self._remember_running_loop(waiter)
        text_chars = self._event_text_chars(event)
        if (
            len(state.events) + 1 > self.max_events_per_run
            or state.text_chars + text_chars > self.max_text_chars_per_run
        ):
            # 超过缓存限制后只保留错误事件，并禁用本轮后续事件缓存。
            seq = self._replace_with_limit_error(state)
            self._notify_change(waiter)
            return seq

        state.latest_seq += 1
        stored_event = deepcopy(event)
        stored_event.seq = state.latest_seq
        state.events.append(stored_event)
        state.text_chars += text_chars
        self._notify_change(waiter)
        return stored_event.seq

    def finish(
        self,
        session_id: str,
        status: RunStatus | Literal["running", "completed", "failed", "interrupted"],
        error_message: str | None = None,
        run_id: str | None = None,
    ) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        if run_id is not None and state.run_id != run_id:
            return

        waiter = self._waiter_for(session_id)
        self._remember_running_loop(waiter)
        state.status = RunStatus(status)
        state.error_message = error_message
        self._notify_change(waiter)

    def is_current_run(self, session_id: str, run_id: str) -> bool:
        """判断指定 run 是否仍是该会话当前运行，避免旧 run 晚到回写。"""
        state = self._states.get(session_id)
        return state is not None and state.run_id == run_id

    def snapshot(self, session_id: str, after_seq: int = 0) -> RunSnapshot | None:
        state = self._states.get(session_id)
        if state is None:
            return None

        return RunSnapshot(
            session_id=state.session_id,
            run_id=state.run_id,
            status=state.status,
            latest_seq=state.latest_seq,
            events=deepcopy([event for event in state.events if event.seq > after_seq]),
            error_message=state.error_message,
        )

    async def wait_for_change(
        self,
        session_id: str,
        after_seq: int,
        timeout: float = 15.0,
    ) -> bool:
        state = self._states.get(session_id)
        if state is None:
            return False

        waiter = self._waiter_for(session_id)
        waiter.loop = asyncio.get_running_loop()
        initial_run_id = state.run_id

        async def _wait() -> bool:
            async with waiter.condition:
                if self._has_change(session_id, initial_run_id, after_seq):
                    return True

                await waiter.condition.wait_for(
                    lambda: self._has_change(session_id, initial_run_id, after_seq)
                )
                return True

        try:
            return await asyncio.wait_for(_wait(), timeout=timeout)
        except TimeoutError:
            return False

    def _replace_with_limit_error(self, state: _RunState) -> int:
        state.latest_seq += 1
        state.status = RunStatus.FAILED
        state.error_message = RUN_CACHE_LIMIT_ERROR
        state.events = [
            RunEvent(type="error", message=RUN_CACHE_LIMIT_ERROR, seq=state.latest_seq)
        ]
        state.text_chars = len(RUN_CACHE_LIMIT_ERROR)
        state.cache_enabled = False
        return state.latest_seq

    def _notify_change(self, waiter: _SessionWaiter) -> None:
        loop = waiter.loop
        if loop is None or loop.is_closed():
            return

        async def _notify() -> None:
            async with waiter.condition:
                waiter.condition.notify_all()

        # append/finish 是同步入口，通知必须投递到等待者所在的事件循环。
        loop.call_soon_threadsafe(lambda: asyncio.create_task(_notify()))

    def _remember_running_loop(self, waiter: _SessionWaiter) -> None:
        try:
            waiter.loop = asyncio.get_running_loop()
        except RuntimeError:
            return

    def _event_text_chars(self, event: RunEvent) -> int:
        if event.type != "text" or event.content is None:
            return 0
        return len(event.content)

    def _has_change(self, session_id: str, initial_run_id: str, after_seq: int) -> bool:
        state = self._states.get(session_id)
        if state is None:
            return False
        # start() 会覆盖同 session 的状态；检测 run_id 切换以唤醒旧 run 的恢复流。
        if state.run_id != initial_run_id:
            return True
        return state.latest_seq > after_seq or state.status != RunStatus.RUNNING

    def _waiter_for(self, session_id: str) -> _SessionWaiter:
        waiter = self._waiters.get(session_id)
        if waiter is None:
            waiter = _SessionWaiter()
            self._waiters[session_id] = waiter
        return waiter


run_state_store = InMemoryRunStateStore()
