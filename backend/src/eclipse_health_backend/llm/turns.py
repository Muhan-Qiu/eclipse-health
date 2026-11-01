"""进程内活跃对话登记表（B4-08）。

B3-04 只靠「SSE 断开后 0.5 s 探测」取消；浏览器/代理偶尔不会立刻断开连接，
用户点「停止生成」后回答仍会继续。这里给每条正在生成的消息登记一个
``asyncio.Event``，取消 API 直接置位，agent 的工具循环在下一个等待点抛出
``TurnCancelled``，落库状态与 SSE ``done{cancelled:true}`` 都走原有路径。

单进程 sidecar 足够：Tauri 只启动一个后端进程，不做多 worker。
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field

# 正常情况下单轮最多 TURN_TIMEOUT_S（90s）；超过这个时间仍未注销的登记视为泄漏。
STALE_AFTER_S = 300.0


@dataclass
class ActiveTurn:
    message_id: str
    session_id: str
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    started_at: float = field(default_factory=time.monotonic)

    def is_stale(self, now: float) -> bool:
        return not self.cancel.is_set() and now - self.started_at > STALE_AFTER_S


class TurnRegistry:
    def __init__(self) -> None:
        self._turns: dict[str, ActiveTurn] = {}
        self._lock = threading.Lock()

    def register(self, message_id: str, session_id: str) -> asyncio.Event:
        """登记一条正在生成的回答；同 ID 重复登记会覆盖旧事件。"""
        now = time.monotonic()
        with self._lock:
            self._drop_stale(now)
            turn = ActiveTurn(message_id=message_id, session_id=session_id)
            self._turns[message_id] = turn
        return turn.cancel

    def cancel(self, message_id: str) -> bool:
        """返回是否找到活跃轮次；找不到不代表消息不存在（可能已经结束）。"""
        with self._lock:
            turn = self._turns.get(message_id)
        if turn is None:
            return False
        turn.cancel.set()
        return True

    def is_active(self, message_id: str) -> bool:
        with self._lock:
            return message_id in self._turns

    def unregister(self, message_id: str) -> None:
        with self._lock:
            self._turns.pop(message_id, None)

    def active_count(self) -> int:
        with self._lock:
            return len(self._turns)

    def _drop_stale(self, now: float) -> None:
        stale = [key for key, turn in self._turns.items() if turn.is_stale(now)]
        for key in stale:
            self._turns.pop(key, None)


_registry = TurnRegistry()


def get_turn_registry() -> TurnRegistry:
    return _registry


__all__ = ["STALE_AFTER_S", "ActiveTurn", "TurnRegistry", "get_turn_registry"]
