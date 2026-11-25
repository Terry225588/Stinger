"""画面稳定之后才提交一次识别，并且同一时间只跑一题。

“画面没变化就不重复识别”参考了 Lihvarya/ibosOCR（Apache-2.0）。
稳定等待和单飞队列是重新写的，没有拷贝它的循环。

画面没变就不再提交。识别还在进行时，新的稳定画面只保留最后一帧，
当前这次结束后再跑，不会叠两份识别。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class _Queued(Generic[T]):
    signature: str
    payload: T


class JobGate(Generic[T]):
    def __init__(self) -> None:
        self.busy = False
        self.last_done: str | None = None
        self._inflight: str | None = None
        self._queued: _Queued[T] | None = None

    def request(self, signature: str, payload: T) -> T | None:
        if self.busy:
            if signature == self._inflight:
                self._queued = None
            else:
                self._queued = _Queued(signature, payload)
            return None
        if signature == self.last_done:
            return None
        self.busy = True
        self._inflight = signature
        self._queued = None
        return payload

    def finish(self, *, drop_followup: bool = False) -> T | None:
        self.last_done = self._inflight
        self.busy = False
        self._inflight = None
        queued = self._queued
        self._queued = None
        if drop_followup or queued is None:
            return None
        return self.request(queued.signature, queued.payload)

    def drop_queued(self) -> None:
        self._queued = None


class WatchController(Generic[T]):
    def __init__(self, stable_s: float = 0.45) -> None:
        if stable_s < 0:
            raise ValueError("stable_s 不能为负")
        self.stable_s = stable_s
        self.jobs: JobGate[T] = JobGate()
        self._pending: str | None = None
        self._pending_since: float | None = None
        self._immediate = False
        self._paused = False
        self._lock = threading.RLock()

    def arm_immediate(self) -> None:
        with self._lock:
            self._immediate = True
            self._pending = None
            self._pending_since = None
            self.jobs.drop_queued()

    def pause(self) -> None:
        with self._lock:
            self._paused = True
            self.jobs.drop_queued()

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def push(self, signature: str, payload: T, now: float) -> T | None:
        with self._lock:
            if self._paused:
                return None
            if self._immediate:
                self._immediate = False
                self._pending = signature
                self._pending_since = now
                self.jobs.last_done = None
                return self.jobs.request(signature, payload)
            if signature != self._pending:
                self._pending = signature
                self._pending_since = now
                # 离开上一帧之后又回到旧内容，也要允许再查一次。
                if self.jobs.last_done is not None and signature != self.jobs.last_done:
                    self.jobs.last_done = None
                return None
            if self._pending_since is None or now - self._pending_since < self.stable_s:
                return None
            return self.jobs.request(signature, payload)

    def finish(self, *, drop_followup: bool = False) -> T | None:
        with self._lock:
            if self._paused:
                drop_followup = True
            return self.jobs.finish(drop_followup=drop_followup)


class ScreenWatch(Generic[T]):
    """给界面和测试用的同一套调度。payload 由调用方保存，这里只决定何时开工。"""

    def __init__(self, stable_s: float = 0.45) -> None:
        self.controller = WatchController[T](stable_s)

    def arm_immediate(self) -> None:
        self.controller.arm_immediate()

    def pause(self) -> None:
        self.controller.pause()

    def resume(self) -> None:
        self.controller.resume()

    def observe(self, signature: str, payload: T, now: float) -> T | None:
        return self.controller.push(signature, payload, now)

    def complete(self, *, drop_followup: bool = False) -> T | None:
        return self.controller.finish(drop_followup=drop_followup)

    @property
    def busy(self) -> bool:
        return self.controller.jobs.busy
