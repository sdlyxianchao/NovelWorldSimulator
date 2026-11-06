# -*- coding: utf-8 -*-
"""运行会话（设计稿 §七）：一次推演的「起 / 停 / 暂停 / 继续」与状态。

为什么要包一层
--------------
`RunLoop` 只管「怎么跑」，不管「谁在跑、跑到哪了、界面该显示什么」。
会话层把 asyncio 任务与状态机收在一处，界面只跟它打交道 ——
这样「暂停按钮显示什么文字」「停止后算结束还是算中止」这类判断
不会散在 GUI 的十几个回调里。

状态机（单向，除暂停外不可逆）：

    idle ──start──▶ running ──pause──▶ paused ──resume──▶ running
                      │                   │
                      ├──终点/上限────────┤
                      └──stop─────────────┴──▶ finished / stopped

**running 与 paused 都算「这一轮还活着」**：
只有 finished / stopped 之后才能开新一轮（会话层用 `is_alive` 判定）。

English:
Run session (design doc §7): the "start / stop / pause / resume" and status of one simulation
run.
Why wrap a layer
--------------
`RunLoop` only handles "how to run", not "who's running, how far it's gotten, what the UI should
show".
The session layer gathers the asyncio task and the state machine in one place, and the UI only
talks to it --
this way judgments like "what text the pause button shows" and "after stopping, does it count as
finished or aborted"
won't be scattered across a dozen GUI callbacks.
State machine (one-way, irreversible except for pause):
    idle --start--> running --pause--> paused --resume--> running
                      │                   │
                      ├--end/limit---------┤
                      └--stop--------------┴--> finished / stopped
**Both running and paused count as "this round is still alive"**:
a new round can only be started after finished / stopped (the session layer judges with
`is_alive`).
"""
from __future__ import annotations

import asyncio
import time

from crew import doing as DOING
from typing import Any, Callable

_LOG = __import__("logging").getLogger("nws.sim.session")

IDLE = "idle"
RUNNING = "running"
PAUSED = "paused"
FINISHED = "finished"
STOPPED = "stopped"

ALIVE = (RUNNING, PAUSED)          # 还活着的两个状态（可暂停/可停止）
# [EN] The two states that are still alive (pausable/stoppable)


class RunSession:
    """一次推演的会话。
        English:
    The session of one simulation run.
    """

    def __init__(self, loop, world, run, *,
                 on_narrative: Callable[..., None] | None = None,
                 on_divider: Callable[..., None] | None = None,
                 on_status: Callable[..., None] | None = None,
                 on_state: Callable[[str, str], None] | None = None,
                 on_branch: Callable[[list], None] | None = None,
                 on_ask: Callable[[dict], None] | None = None,
                 on_scene: Callable[[dict], None] | None = None,
                 on_rollback: Callable[[int], None] | None = None,
                 on_crew_work: Callable[[str, str], None] | None = None,
                 on_crew_line: Callable[[str, str, dict], None] | None = None,
                 max_ticks: int = 0):
        self.loop = loop
        self.world = world
        self.run = run
        self._max_ticks = max_ticks        # 0=不限；验证脚本用它限时
        # [EN] 0=unlimited; the verification script uses it to limit time
        self._on_state = on_state
        self._status = IDLE
        self._reason = ""
        self._error = ""
        self._task: asyncio.Task | None = None
        self._t0 = 0.0

        if on_narrative is not None:
            loop.on_narrative(on_narrative)
        if on_divider is not None:
            loop.on_divider(on_divider)
        if on_status is not None:
            loop.on_status(on_status)
        # ★★ **主循环自己开的暂停也要走会话层**（2026-10-10 加）。
        #   这条接线以前是缺的，缺了会出真机上那个大坑：日界检查点 /
        #   存档点 / 岔路口 / 导演介入 / 入夜 这几处都是**主循环直接
        #   `self.pause()`**，绕过会话 —— 于是 `status` 一直停在 `running`，
        #   界面既不会把按钮换成「继续」，也不会把状态条写成「已暂停」，
        #   屏幕上就只剩最后一次细粒度状态（那天恰好是 `evaluating`
        #   ⇒「正在核对故事进度 · 已 2019 秒」）一直涨。
        #   实测那 33 分钟里 **0 次 LLM 调用** —— 它就是在等人点「继续」。
        #   ⚠ 用 `getattr` 取：判据/探针里有一堆**替身主循环**
        #     （`verify_resume_manage` 的 `_FakeLoop` 之类，只实现 `run/stop`），
        #     直接调方法会 `AttributeError` —— 那看起来像产品代码坏了。
        # [EN] ★★ **Pauses initiated by the main loop itself must also go through the session layer** (added
        # [EN] 2026-10-10).
        # [EN] This wiring used to be missing, and missing it causes that big pitfall on the real device: the
        # [EN] day-boundary checkpoint /
        # [EN] save point / branch point / director intervention / nightfall -- all these places are **the main
        # [EN] loop directly
        # [EN] calling `self.pause()`**, bypassing the session -- so `status` stays stuck at `running`,
        # [EN] the UI neither swaps the button to "Resume" nor writes the status bar as "Paused",
        # [EN] and on screen only the last fine-grained status remains (that day it happened to be `evaluating`
        # [EN] => "Verifying story progress, 2019 s elapsed") and keeps ticking up.
        # [EN] Measured: during those 33 minutes, **0 LLM calls** -- it was just waiting for someone to click
        # [EN] "Resume".
        # [EN] ⚠ Fetch with `getattr`: the criteria/probes contain a bunch of **stand-in main loops**
        # [EN] (like `verify_resume_manage`'s `_FakeLoop`, which only implements `run/stop`),
        # [EN] calling the method directly throws `AttributeError` -- which looks like the product code is
        # [EN] broken.
        _wire = getattr(loop, 'on_self_pause', None)
        if callable(_wire):
            _wire(self._on_loop_pause)
        # 岔路口的走向候选（`BRANCH_*` / `INTERVENTION_POLICY` 那一套，2026-10-06 接）。
        # 界面拿到就弹选择面板；点选后调 `loop.choose_branch(id)`。
        # [EN] Branch direction candidates (the `BRANCH_*` / `INTERVENTION_POLICY` set, wired in 2026-10-06).
        # [EN] The UI pops up a selection panel on receipt; after choosing, it calls `loop.choose_branch(id)`.
        if on_branch is not None:
            loop.on_branch(on_branch)
        # ★★ **统一的提问对话框**（2026-10-11）：岔路口 / 导演介入 / 预算耗尽 /
        #   存档点 四处共用同一条通道（界面那边只有一处建面板的代码）。
        #   用户点名要的"取消 → 暂停 → 点继续重新弹"就落在这条通道上
        #   （见 `RunLoop.cancel_ask` / `RunLoop.resume`）。
        # [EN] ★★ **Unified question dialog** (2026-10-11): branch point / director intervention / budget
        # [EN] exhausted /
        # [EN] save point -- these four places share one channel (on the UI side there is only one place that
        # [EN] builds the panel).
        # [EN] The "cancel -> pause -> click Resume to re-pop" that the user explicitly asked for lands on this
        # [EN] channel
        # [EN] (see `RunLoop.cancel_ask` / `RunLoop.resume`).
        if on_ask is not None:
            loop.on_ask(on_ask)
        # 「换地方了」→ 界面重画小地图（2026-10-06）。同上是纯播报通道。
        # [EN] "Moved somewhere else" -> the UI redraws the minimap (2026-10-06). Same as above, it's a pure
        # [EN] broadcast channel.
        if on_scene is not None:
            loop.on_scene(on_scene)
        # ★ 回档（2026-10-07）：导演删掉刚生成的几条戏时，中栏要同步撤掉 ——
        #   少了这条接线，屏幕上会留着"一句已经被删掉的台词"。
        # [EN] ★ Rollback (2026-10-07): when the director deletes a few just-generated scenes, the middle
        # [EN] column must retract them in sync --
        # [EN] without this wiring, a "line that's already been deleted" would linger on screen.
        if on_rollback is not None:
            loop.on_rollback(on_rollback)
        # ★ 出工状态（2026-10-08）：某位剧组成员开始/结束干活时，界面把那一行
        #   高亮/复原（用户：「谁在干活请高亮显示 等不干活了再恢复普通样式」）。
        # [EN] ★ Working status (2026-10-08): when a crew member starts/finishes work, the UI
        # [EN] highlights/restores that row
        # [EN] (user: "please highlight who's working, and restore normal style when they stop").
        if on_crew_work is not None:
            loop.on_work(on_crew_work)
        # ★★★ 2026-10-23：剧组消息的"起一条"。
        #   ⚠ 加参数时**必须同时改这里**：`RunSession` 是界面与主循环之间唯一的接线处，
        #     漏一条的表现是"起笔直接失败"（`TypeError: unexpected keyword argument`），
        #     而不是某个功能不生效 —— 那一下整轮都起不来（`verify_run_control`
        #     五条真机判据当场全红，日志里只有一句"启动新一轮失败"）。
        # [EN] ★★★ 2026-10-23: "open a crew message".
        # [EN] ⚠ Adding a parameter **requires changing this too**: `RunSession` is the only
        # [EN] wiring point between the UI and the main loop, and missing one shows up as
        # [EN] "starting the run fails outright" (`TypeError: unexpected keyword argument`),
        # [EN] not as a feature silently not working -- the whole round cannot start (five
        # [EN] real-device criteria in `verify_run_control` went red at once, with only
        # [EN] "starting a new round failed" in the log).
        if on_crew_line is not None:
            loop.on_crew_line(on_crew_line)

    # ── 状态 ──
    # [EN] -- Status --
    @property
    def status(self) -> str:
        return self._status

    @property
    def is_alive(self) -> bool:
        """这一轮还在活着（运行中或已暂停）——决定能否开新一轮。
                English:
        This round is still alive (running or paused) -- determines whether a new round can be started.
        """
        return self._status in ALIVE

    @property
    def reason(self) -> str:
        """结束原因（主循环给的字符串，如「到达故事终点」）。
                English:
        End reason (a string given by the main loop, e.g. "reached the story's end").
        """
        return self._reason

    @property
    def error(self) -> str:
        return self._error

    @property
    def elapsed(self) -> float:
        """真实经过秒数（暂停中也算，它本来就是"这一轮跑了多久"）。
                English:
        Actual elapsed seconds (counted even while paused; it's inherently "how long this round has
        run").
        """
        return (time.time() - self._t0) if self._t0 else 0.0

    def _set(self, status: str, reason: str = "") -> None:
        self._status = status
        if reason:
            self._reason = reason
        if status in (FINISHED, STOPPED):
            self._task = None
        if self._on_state is not None:
            try:
                self._on_state(status, self._reason)
            except Exception:                               # noqa: BLE001
                pass                    # 界面回调出问题不该弄挂会话
                # [EN] UI callback problems shouldn't crash the session

    # ── 控制 ──
    # [EN] -- Control --
    def start(self) -> bool:
        """启动。已经在跑（或已暂停）时返回 False，不重复起。
                English:
        Start. Returns False when already running (or already paused); won't start again.
        """
        if self.is_alive:
            return False
        self._reason = ""
        self._error = ""
        self._t0 = time.time()
        self._set(RUNNING)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有事件循环（同步调用点）——那就别假装启动了
            # [EN] No event loop (synchronous call site) -- then don't pretend to start
            self._set(STOPPED, "没有可用的事件循环")
            return False
        self._task = loop.create_task(self._runner())
        return True

    async def _runner(self) -> None:
        try:
            reason = await self.loop.run(self._max_ticks)
        except asyncio.CancelledError:
            self._set(STOPPED, "已取消")
            raise
        except Exception as e:                              # noqa: BLE001
            _LOG.warning("推演出错: %s", e)
            self._error = f"{type(e).__name__}: {e}"
            self._set(STOPPED, self._error)
            return
        # 「手动停止」是我们主动叫停，其余（到终点/到天数上限）都算正常结束
        # [EN] "Manual stop" is us actively halting; everything else (reaching the end / hitting the day limit)
        # [EN] counts as normal completion
        if reason == "手动停止":
            self._set(STOPPED, reason)
        else:
            self._set(FINISHED, reason)

    def pause(self) -> bool:
        if self._status != RUNNING:
            return False
        self.loop.pause()
        self._set(PAUSED)
        return True

    def _on_loop_pause(self, why: str = "") -> None:
        """**主循环自己停的**（日界检查点 / 存档点 / 岔路口 / 导演介入 / 入夜）。

        只做一件事：把会话状态对齐成 `paused` —— 界面正是据此把状态条写成
        「已暂停 —— 等你点「继续」」、把那个按钮换成「▶ 继续」的
        （见 `gui/app_flet._status_view` 与 `_refresh_run_controls`）。

        ⚠ **只在 `running` 时才改**：用户本来就已经暂停/停止过的时候，
          不能再被覆盖一次（那会把"谁停的"揉成一团）。
        ⚠ **不写 `_reason`**：`_reason` 是"这一轮**为什么结束**"（到终点 /
          到天数上限 / 手动停止），暂停不是结束。停的原因由中栏那条消息说
          （日界那条会写「按设置每 N 天停一下」）。
        
                English:
        **The main loop stopped on its own** (day-boundary checkpoint / save point / branch point /
        director intervention / nightfall).
                Does only one thing: align the session state to `paused` -- this is exactly what the UI uses to write the status bar as
                "Paused -- waiting for you to click "Resume"" and swap that button to "▶ Resume"
                (see `gui/app_flet._status_view` and `_refresh_run_controls`).
                ⚠ **Only change it while `running`**: when the user has already paused/stopped it,
                  it must not be overwritten again (that would muddle up "who stopped it").
                ⚠ **Don't write `_reason`**: `_reason` is "why this round **ended**" (reached the end /
                  hit the day limit / manual stop); a pause is not an ending. The reason for stopping is stated by that message in the middle column
                  (the day-boundary one writes "pause every N days per settings").
        """
        if self._status != RUNNING:
            return
        if why:
            _LOG.info("主循环自己暂停了：%s", why)
        self._set(PAUSED)

    def resume(self) -> bool:
        if self._status != PAUSED:
            return False
        self.loop.resume()
        self._set(RUNNING)
        return True

    def stop(self) -> bool:
        """请求停止。**运行中和暂停中都能停**（`RunLoop.stop()` 会解除暂停）。
                English:
        Request stop. **Can stop both while running and while paused** (`RunLoop.stop()` will release
        the pause).
        """
        if not self.is_alive:
            return False
        self.loop.stop()
        # 真正的状态切换在 `_runner` 里做（等收尾跑完：补落最后一天 + 自动导出）。
        # 这里只更新 reasons 让界面显示「正在停止…」，避免用户以为没反应。
        # [EN] The actual state transition happens in `_runner` (after the wrap-up finishes: backfill the last
        # [EN] day + auto-export).
        # [EN] Here we only update reasons so the UI shows "Stopping...", to avoid the user thinking nothing's
        # [EN] happening.
        self._set(self._status, "正在停止…")
        return True

    async def wait(self, timeout: float | None = None) -> bool:
        """等这一轮收尾完成。返回是否已结束。
                English:
        Wait for this round's wrap-up to complete. Returns whether it has ended.
        """
        if self._task is None:
            return True
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout)
            return True
        except asyncio.TimeoutError:
            return False
        except Exception:                                   # noqa: BLE001
            return True

    # ── 给界面用的快照 ──
    # [EN] -- Snapshot for the UI --
    def snapshot(self) -> dict[str, Any]:
        """一次推演的可显示事实（界面每帧取样用，**不编造**）。
                English:
        Displayable facts of one simulation run (used for per-frame sampling in the UI, **do not
        fabricate**).
        """
        w = self.world
        # ★★★ 2026-10-31：`day` 用**写作天**（`loop._current_day`），与中栏幕头、
        #   落盘文件名、停点 `day`、左上角时间面板同源。
        #   原来读 `w.game_day`（故事钟）—— 它会被"站末补时间"推到稿子前面，
        #   于是状态条说第 4 天、稿子是第 3 天（用户报的"时间对不上"）。
        #   ⚠ 取不到（还没装配完）才退回 `game_day`。
        # [EN] ★★★ 2026-10-31: `day` is the **writing day** (`loop._current_day`) -- the same source
        # [EN] as the centre-column header, the persisted file names, the stop point's `day` and the
        # [EN] top-left time panel. It used to read `w.game_day` (story clock), which a station-gap
        # [EN] jump pushes ahead of the drafts, so the status bar said day 4 while the prose was
        # [EN] day 3 (the mismatch the user reported). ⚠ Falls back to `game_day` only when the loop
        # [EN] isn't there yet.
        _day = 0
        try:
            _day = int(getattr(getattr(self, "loop", None), "_current_day", 0) or 0)
        except Exception:                                   # noqa: BLE001
            _day = 0
        return {
            "status": self._status,
            "reason": self._reason,
            "error": self._error,
            "elapsed": self.elapsed,
            "day": _day or w.game_day,
            "clock": w.clock_display() if hasattr(w, "clock_display") else "",
            "weather": getattr(w, "weather", ""),
            "scene": getattr(w, "scene", ""),
            "node": getattr(w, "current_node", ""),
            "node_name": (w.current_node_info() or {}).get("名称", "")
            if hasattr(w, "current_node_info") else "",
            "tension": getattr(w, "tension", 0.0),
            "event_count": getattr(w, "event_count", 0),
            "on_stage": w.on_stage_names() if hasattr(w, "on_stage_names") else [],
            "run_name": self.run.root.name if self.run else "",
            # ★★★ 2026-10-21（用户点名）：「状态条要一直显示**当前正在做什么以及做了多久**」。
            #   两个字段分开给，界面才能各用各的（文字/秒表）：
            #     · `doing`      —— 现在在做的那件事（`场记 · 连戏检查` / `整理当天这一章`），
            #                       没在做事就是空串（**不编一个"思考中"**）；
            #     · `doing_secs` —— **这一件事**已经做了多少秒（不是"这个状态持续多久"）。
            #   ⚠ 数据来自 `crew.doing` 的栈顶：阶段是嵌套的，栈顶永远是最具体那个动作。
            # [EN] ★★★ 2026-10-21 (named by the user): "the status bar must always show **what is being
            # [EN] done and for how long**". Two fields so the UI can use each for its own purpose:
            # [EN] · `doing`      -- the current activity (`场记 · 连戏检查` / `整理当天这一章`), empty
            # [EN]                   string when nothing is running (**never fabricate "thinking..."**);
            # [EN] · `doing_secs` -- how long **this activity** has been running (not the status duration).
            # [EN] ⚠ Data comes from the top of `crew.doing`'s stack: stages nest, and the top is always
            # [EN] the most specific action.
            "doing": str(DOING.snapshot().get("label") or ""),
            "doing_secs": float(DOING.snapshot().get("secs") or 0.0),
        }
