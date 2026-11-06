# -*- coding: utf-8 -*-
"""阅读节奏器（设计稿 §11.7）：模拟钟与显示队列解耦。

解决问题：LLM 一次生成就是一整段，×60 倍率下多个 Agent 的输出排队砸向屏幕——不控制就是瀑布刷屏。

解法：
- 显示队列（带优先级 P0-P3）
- 阅读档/速览档切换
- 打字机效果（可关）
- 积压策略（compress/jump/block）
- 关键事件自动放慢

English:
Reading rhythm controller (design doc §11.7): decouples the simulation clock from the display
queue.
Problem: LLM generates an entire segment at once, and at ×60 rate the output of multiple Agents
queues up and slams onto the screen — without control it's a waterfall of scrolling.
Solution:
- Display queue (with priorities P0-P3)
- Reading profile / quick view profile switching
- Typewriter effect (can be disabled)
- Backlog strategy (compress/jump/block)
- Auto slowdown for key events
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Any
from enum import IntEnum

from config import CFG

_LOG = __import__("logging").getLogger("nws.display")


class Priority(IntEnum):
    """显示优先级四档（§11.7）。
        English:
    Four display priority levels (§11.7).
    """
    P0 = 0  # 关键事件 / 分支提案 / 管理员警告
    P1 = 1  # 对话
    P2 = 2  # 前台动作 / 旁白
    P3 = 3  # 日常琐事 / 后台摘要
    # [EN] Key events / branch proposals / admin warnings
    # [EN] Dialogue
    # [EN] Foreground actions / narration
    # [EN] Daily trivia / background summaries


@dataclass
class DisplayEntry:
    """显示队列条目。
        English:
    Display queue entry.
    """
    priority: Priority
    content: str
    timestamp: float = field(default_factory=time.time)
    game_time: str = ""
    is_key_event: bool = False  # 关键事件标记（自动放慢）
    compressed: bool = False    # 是否已被压缩
    # [EN] Key event marker (auto slowdown)
    # [EN] Whether already compressed


class DisplayProfile:
    """显示配置档（§11.7 两档配置）。
        English:
    Display profiles (two-profile config in §11.7).
    """

    def __init__(self, name: str, typewriter: bool, cps: int,
                 auto_slow_on_key: bool, compress_p3: bool):
        self.name = name
        self.typewriter = typewriter
        self.cps = cps  # 字/秒
        # [EN] chars/sec
        self.auto_slow_on_key = auto_slow_on_key
        self.compress_p3 = compress_p3


# 预置配置档
# [EN] Preset profiles
READING_PROFILE = DisplayProfile(
    name="reading",
    typewriter=True,
    cps=18,
    auto_slow_on_key=True,
    compress_p3=True,
)

FAST_PROFILE = DisplayProfile(
    name="fast",
    typewriter=False,
    cps=100,  # 速览档：整段直接上屏
    # [EN] Quick view profile: entire segment goes straight to screen
    auto_slow_on_key=False,
    compress_p3=True,
)


class DisplayRhythm:
    """阅读节奏器：管理显示队列，按优先级和阅读速度呈现内容。
        English:
    Reading rhythm controller: manages the display queue, presents content by priority and reading
    speed.
    """

    def __init__(self):
        self._queue: list[DisplayEntry] = []
        self._lock = asyncio.Lock()
        self._profile: DisplayProfile = READING_PROFILE
        self._follow: bool = True  # 自动跟随
        self._lock_sim: bool = CFG.b("DISPLAY_LOCK_SIM")  # 锁定模式
        # [EN] Auto follow
        # [EN] Lock mode
        self._backlog_limit: int = CFG.i("DISPLAY_BACKLOG_LIMIT")
        self._catchup_policy: str = CFG.s("DISPLAY_CATCHUP_POLICY")  # compress/jump/block

        # 回调
        # [EN] Callbacks
        self._on_display: Callable[[DisplayEntry], None] | None = None
        self._on_compressed: Callable[[int], None] | None = None  # (count,)

        # 统计
        # [EN] Stats
        self._displayed_count: int = 0
        self._compressed_count: int = 0

        # 加载配置
        # [EN] Load config
        self._load_config()

    def _load_config(self) -> None:
        """从 .env 加载显示配置。
                English:
        Load display config from .env.
        """
        profile_name = CFG.s("DISPLAY_PROFILE")
        if profile_name == "reading":
            self._profile = READING_PROFILE
        elif profile_name == "fast":
            self._profile = FAST_PROFILE

        # 覆盖 CPS
        # [EN] Override CPS
        cps = CFG.i("READING_CPS")
        if cps > 0:
            self._profile.cps = cps

        self._backlog_limit = CFG.i("DISPLAY_BACKLOG_LIMIT")
        self._catchup_policy = CFG.s("DISPLAY_CATCHUP_POLICY")
        self._lock_sim = CFG.b("DISPLAY_LOCK_SIM")

    # ── 回调注册 ──
    # [EN] ── Callback registration ──
    def on_display(self, cb: Callable[[DisplayEntry], None]) -> None:
        """注册显示回调：当有内容需要呈现时调用。
                English:
        Register display callback: called when content needs to be presented.
        """
        self._on_display = cb

    def on_compressed(self, cb: Callable[[int], None]) -> None:
        """注册压缩回调：当有内容被压缩时调用。
                English:
        Register compression callback: called when content is compressed.
        """
        self._on_compressed = cb

    # ── 入队 ──
    # [EN] ── Enqueue ──
    async def enqueue(self, content: str, priority: Priority = Priority.P2,
                      game_time: str = "", is_key_event: bool = False) -> None:
        """将内容加入显示队列。
                English:
        Add content to the display queue.
        """
        entry = DisplayEntry(
            priority=priority,
            content=content,
            game_time=game_time,
            is_key_event=is_key_event,
        )
        async with self._lock:
            self._queue.append(entry)

            # 检查积压
            # [EN] Check backlog
            if len(self._queue) > self._backlog_limit:
                await self._handle_backlog()

    async def enqueue_narrative(self, text: str, priority: int = 2,
                                game_time: str = "", is_key_event: bool = False) -> None:
        """便捷方法：将叙事文本加入队列。
                English:
        Convenience method: enqueue narrative text.
        """
        try:
            p = Priority(priority)
        except ValueError:
            p = Priority.P2
        await self.enqueue(text, p, game_time, is_key_event)

    # ── 出队（供 TUI 消费）──
    # [EN] ── Dequeue (for TUI consumption) ──
    async def dequeue(self) -> DisplayEntry | None:
        """取出队首条目（FIFO，但 P0 优先）。
                English:
        Pop the head entry (FIFO, but P0 first).
        """
        async with self._lock:
            if not self._queue:
                return None

            # P0 优先
            # [EN] P0 priority
            p0_indices = [i for i, e in enumerate(self._queue) if e.priority == Priority.P0]
            if p0_indices:
                idx = p0_indices[0]
                return self._queue.pop(idx)

            # FIFO
            return self._queue.pop(0)

    async def dequeue_all(self) -> list[DisplayEntry]:
        """取出所有条目。
                English:
        Pop all entries.
        """
        async with self._lock:
            entries = list(self._queue)
            self._queue.clear()
            return entries

    async def peek(self) -> DisplayEntry | None:
        """查看队首条目（不取出）。
                English:
        Peek at the head entry (without popping).
        """
        async with self._lock:
            if not self._queue:
                return None
            return self._queue[0]

    # ── 积压处理 ──
    # [EN] ── Backlog handling ──
    async def _handle_backlog(self) -> None:
        """处理积压内容（§11.7 积压策略）。
                English:
        Handle backlog content (§11.7 backlog strategy).
        """
        if self._catchup_policy == "compress":
            await self._compress_backlog()
        elif self._catchup_policy == "jump":
            await self._jump_to_latest()
        elif self._catchup_policy == "block":
            # block 模式：等待显示完成（由外部控制）
            # [EN] block mode: wait for display completion (controlled externally)
            pass

    async def _compress_backlog(self) -> None:
        """压缩积压：P3 折叠成一行式，P2 提速。
                English:
        Compress backlog: P3 collapses into one-line form, P2 speeds up.
        """
        compressed_count = 0
        new_queue: list[DisplayEntry] = []

        # 分离 P3
        # [EN] Split P3
        p3_entries = [e for e in self._queue if e.priority == Priority.P3 and not e.compressed]
        non_p3 = [e for e in self._queue if e.priority != Priority.P3]

        # 压缩 P3
        # [EN] Compress P3
        if p3_entries:
            # 合并为一行
            # [EN] Merge into one line
            combined = "（收起 {} 条日常）".format(len(p3_entries))
            compressed_entry = DisplayEntry(
                priority=Priority.P3,
                content=combined,
                timestamp=time.time(),
                compressed=True,
            )
            new_queue.append(compressed_entry)
            compressed_count += len(p3_entries) - 1

        new_queue.extend(non_p3)
        self._queue = new_queue
        self._compressed_count += compressed_count

        if self._on_compressed and compressed_count > 0:
            self._on_compressed(compressed_count)

        _LOG.debug("压缩积压：%d 条 P3 内容折叠", compressed_count)

    async def _jump_to_latest(self) -> None:
        """跳到最新：清空队列，只保留最新条目。
                English:
        Jump to latest: clear the queue, keep only the latest entry.
        """
        if not self._queue:
            return

        # 保留 P0 和最新一条
        # [EN] Keep P0 and the latest entry
        p0 = [e for e in self._queue if e.priority == Priority.P0]
        latest = self._queue[-1] if self._queue else None

        compressed = len(self._queue) - len(p0) - (1 if latest else 0)
        self._compressed_count += compressed

        self._queue = p0
        if latest and latest not in p0:
            self._queue.append(latest)

        if self._on_compressed and compressed > 0:
            self._on_compressed(compressed)

        _LOG.debug("跳到最新：%d 条内容跳过", compressed)

    # ── 配置切换 ──
    # [EN] ── Config switching ──
    def switch_profile(self, profile_name: str) -> None:
        """切换显示档（Ctrl+D）。
                English:
        Switch display profile (Ctrl+D).
        """
        if profile_name == "reading":
            self._profile = READING_PROFILE
        elif profile_name == "fast":
            self._profile = FAST_PROFILE
        else:
            _LOG.warning("未知显示档: %s", profile_name)
            return

        # 覆盖 CPS
        # [EN] Override CPS
        cps = CFG.i("READING_CPS")
        if cps > 0:
            self._profile.cps = cps

        _LOG.info("切换显示档: %s (CPS=%d, 打字机=%s)",
                  self._profile.name, self._profile.cps, self._profile.typewriter)

    def toggle_follow(self) -> bool:
        """切换自动跟随。
                English:
        Toggle auto follow.
        """
        self._follow = not self._follow
        _LOG.info("自动跟随: %s", "开" if self._follow else "关")
        return self._follow

    @property
    def follow(self) -> bool:
        return self._follow

    @property
    def profile(self) -> DisplayProfile:
        return self._profile

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def backlog_size(self) -> int:
        return max(0, len(self._queue) - self._backlog_limit)

    # ── 计算呈现延迟 ──
    # [EN] ── Compute presentation delay ──
    def calc_delay(self, text: str, is_key_event: bool = False) -> float:
        """计算文本呈现延迟（秒）。
                English:
        Compute text presentation delay (seconds).
        """
        if not self._profile.typewriter:
            return 0.0

        # 字符数
        # [EN] Character count
        char_count = len(text)

        # 基础延迟
        # [EN] Base delay
        base_delay = char_count / self._profile.cps

        # 关键事件自动放慢
        # [EN] Auto slowdown for key events
        if is_key_event and self._profile.auto_slow_on_key:
            base_delay *= 1.5  # 放慢 50%
            # [EN] Slow down 50%

        return base_delay

    # ── 状态查询 ──
    # [EN] ── Status query ──
    def get_status(self) -> dict:
        """获取显示状态（供 TUI 显示）。
                English:
        Get display status (for TUI display).
        """
        return {
            "profile": self._profile.name,
            "cps": self._profile.cps,
            "typewriter": self._profile.typewriter,
            "follow": self._follow,
            "lock_sim": self._lock_sim,
            "queue_size": len(self._queue),
            "backlog_size": self.backlog_size,
            "displayed": self._displayed_count,
            "compressed": self._compressed_count,
        }

    # ── 清空队列（catchup 命令）──
    # [EN] ── Clear queue (catchup command) ──
    async def catchup(self) -> int:
        """追上最新：清空队列，返回跳过的条目数。
                English:
        Catch up to latest: clear the queue, return the number of skipped entries.
        """
        async with self._lock:
            count = len(self._queue)
            # 保留 P0
            # [EN] Keep P0
            p0 = [e for e in self._queue if e.priority == Priority.P0]
            self._queue = p0
            skipped = count - len(p0)
            self._compressed_count += skipped
            return skipped


# 全局单例
# [EN] Global singleton
display_rhythm = DisplayRhythm()