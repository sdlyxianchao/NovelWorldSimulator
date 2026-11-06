# -*- coding: utf-8 -*-
"""制片厂：排班、台账、落盘。

一句话
------
名册说"谁在"，`agents.py` 说"怎么干"；**这里说"什么时候轮到谁"**。

一天的班次
----------
    ① 开拍前（`preproduction`）—— **先定画面，再写本子**
         美术定这一部的画风与主色（一次定、全剧用）
         道具按场景出这一场的道具单（反复出现的那件由它挑）
         两样都进 `image_gen` 的提示词前缀 → **当天的插图真的会不一样**
    ② 编剧组（`director.day_plan`，由它调 `Novelist` / `Screenwriter`）
         **编剧室先会审**：导演·作家·剧作者 讨论该补哪些**局部**设定
         （只能进场景层/细节层，见 `world/layers`）→
         小说作家写原著样章 → 剧作者改成能拍的剧本 → 导演验算
    ③ 拍摄（`sim.loop` 的每一拍）—— 演员与群众演员，照旧
    ④ 收工（`wrap`）—— 记录与后期
         场记连戏检查（只报不改）· 宣发写那句话
    ⑤ 导出（`export`）—— 宣发的产出进导出物

为什么要"先定画面再写本子"：反了的话，道具单是照着已成稿的戏凑出来的
（"戏里出现过一把壶，那就写一把壶"），它就不再是**创作决定**而只是**事后记录**。
顺序对了，物件才会真的影响戏怎么写。

两条不做的
----------
* **不重排已有流程**。演员还是每拍决策、导演还是每拍判断 —— 这里只多加
  "开拍前"与"收工后"两段，推演的主体一个字没动。
* **不替作者做决定**。场记提请注意，**绝不自动改稿**；宣发写的是宣传语，
  **绝不进正文**。产出的去处都是"给人看的地方"。

English:
Studio: scheduling, ledger, persistence.
In one sentence
------
The roster says "who is present", `agents.py` says "how to work"; **this says "when whose turn
is it"**.
A day's shifts
---------
    ① Preproduction (`preproduction`) —— **First fix the visuals, then write the script**
         Art fixes the art style and main colors for this installment (set once, used for the whole series)
         Props produce the prop list for this scene based on the scene (the recurring item is chosen here)
         Both go into the `image_gen` prompt prefix → **the day's illustrations will really be different**
    ② Screenwriting group (`director.day_plan`, which calls `Novelist` / `Screenwriter`)
         **The writers' room reviews first**: the director, novelist, and screenwriter discuss which **local** settings need to be added
         (can only enter the scene layer/detail layer, see `world/layers`) →
         The novelist writes a sample chapter of the source material → the screenwriter adapts it into a shootable script → the director verifies it
    ③ Shooting (each beat of `sim.loop`) —— actors and extras, as before
    ④ Wrap (`wrap`) —— recording and post-production
         Script supervisor continuity check (report only, no changes) · publicity writes that line
    ⑤ Export (`export`) —— publicity's output goes into the export artifact
Why "first fix the visuals, then write the script": if reversed, the prop list is assembled to
match an already-finished script
("a teapot appeared in the scene, so write in a teapot"), and it is no longer a **creative
decision**, just an **after-the-fact record**.
When the order is right, objects truly influence how the scene is written.
Two things we don't do
----------
* **Don't rearrange the existing flow**. Actors still decide every beat, the director still judges every beat —— here we only add
  the two segments "preproduction" and "after wrap"; the main body of the simulation is untouched.
* **Don't make decisions for the author**. The script supervisor raises attention, **never automatically rewrites the script**; publicity writes promotional copy,
  **never enters the main text**. All outputs go to "places for people to see".
"""
from __future__ import annotations

import contextlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from config import CFG
from crew import agents as A
from crew import doing as DOING
from crew import roster as ROSTER
# ★ 模型登记表（2026-10-12）：出工时按"这一位点名的模型"切换。
# [EN] ★ Model registry (2026-10-12): switch by "the model this one named" during a work session.
from llm import models as MODELS
from logger import get_logger
from util.io import atomic_write_text
import asyncio

_LOG = get_logger('nws.crew')

# ★★★ 2026-10-15（用户）：非阻塞 Agent —— 卡了就跳过，不堵后面的人。
#   ★ 选法：**不选的**是"这一天的故事/剧本/进度全靠它"的那几个；
#     选中的是"有它更好，没它照样写得出一章小说"的。
#     如果拿不准，**宁可不放进来**（宁可多等 5 分钟，别丢关键产出）。
# [EN] ★★★ 2026-10-15 (user): non-blocking agents -- if they hang, skip them rather than blocking
# [EN] the whole pipeline. The selection rule: "if this agent is unavailable, can the day still produce
# [EN] a chapter / script / progress evaluation?" If yes, it goes in. When in doubt, leave it out.
NONBLOCK_ROLES: set[str] = {
    # ── 开拍前：定画面、定物件、定穿着（没有它们，小说照写，出图默认风格）──
    # [EN] Pre-production: fix visuals / props / styling (without them, the novel still writes,
    # [EN] images use default style)
    'art',          # 美术指导（画风 / 主色 / 忌）
    'props',        # 道具（场景里的物件）
    'stylist',      # 造型（衣着 / 随身物 / 仪态）
    # ── 每拍辅助：不影响剧情推进 ──
    # [EN] Per-beat helpers: don't affect story progression
    'extra',        # 群演（投人；门外已有固定池兜底）
    'continuity',   # 场记（连戏检查；只报不改）
    'sound',        # 声音设计（环境音；喂给场景，没有它场景静音）
    # ── 收工后 / 附加：不影响当天故事本身 ──
    # [EN] After wrap / supplementary: doesn't affect the day's story itself
    'reviewer',     # 复盘（收工后才跑）
    'polisher',     # 语言审校（收工后才跑）
    'publicity',    # 宣发（一句话；不影响故事）
    'researcher',   # 研究（背景知识；有它更好，没它也不崩）
    'script_doctor',# 剧本医生（补丁；有它更好）
    'rehearsal',    # 排练（排戏辅助）
    'settings_room',# 编剧室会审（补充设定；没有也能写，只是少补一些细节）
    # 'ingest'     # 摄取：只跑一次（开局），不是每轮，不需要跳过
    # 'memory'     # 记忆：数据库操作，极快，不该卡
    # 'compliance' # 合规：卡了说明大问题，不该静默跳
    # 'progress'   # 进度评估：卡了要报给用户，不该静默跳
    # 'director'   # 导演：主线，绝对不跳
    # 'novelist'   # 小说作家：写当天故事，绝对不跳
    # 'screenwriter' # 编剧：写剧本，绝对不跳
    # 'actor'      # 演员：每拍决策，绝对不跳
}

#: 落盘文件名（都在运行文件夹下；**只写运行文件夹** —— 项目文件夹铁律）
# [EN] : Output filename (all under the run folder; **only write to the run folder** — project folder
# [EN] is an iron rule)
FILE_LEDGER = '剧组台账.md'
#: ★ 角色子 Agent「正在出工」高亮的**有效窗口**（秒）。
#:   台账按 `world.actor_think_at[角色]` 的时间戳判断：距最近一次决策完成
#:   不到这个窗口，就认为它"这一拍在动" → `busy=True` → 暖金高亮；
#:   过期恢复"在岗"。窗口太短会一闪而过、太长则人人常亮，取一个
#:   比一拍间隔略长的数（推演一拍通常 0.5~2s）。
#: [EN] ★ The **valid window** (sec) for a character sub-agent's "working" highlight.
#: [EN] The ledger judges by `world.actor_think_at[name]`: within this window of the
#: [EN] last decision-completion it's "moving this beat" -> `busy=True` -> warm-gold
#: [EN] highlight; after that it reverts to "在岗". Too short flickers, too long keeps
#: [EN] everyone lit; pick a bit longer than one beat (a beat is usually 0.5~2s).
CHAR_BUSY_WINDOW = 2.5
FILE_PROPS = '道具单.md'
FILE_ART = '美术指导.md'
FILE_CONTINUITY = '场记报告.md'
FILE_PUBLICITY = '宣发文案.md'
# ★ 2026-10-07 补的四位各自的落盘文件
# [EN] ★ The four output files added on 2026-10-07
FILE_REVIEW = '今日总结.md'
FILE_STYLIST = '造型表.md'
FILE_SOUND = '声音设计.md'
FILE_POLISH = '语言审校.md'
#: 排练记录（2026-10-07）：**只落这里与日志，不上中栏**。
# [EN] : Rehearsal record (2026-10-07): **only writes here and to the log, not to the middle column**.
FILE_REHEARSAL = '排练记录.md'
#: **当天这一章的小说整理稿**（2026-10-07）：收工时由小说作家把当天的戏
#: 整理成小说形式，**按天累积**在一份文件里（不是一天一覆盖）。
# [EN] : **The novelization of that day's chapter** (2026-10-07): at wrap-up the novelist turns the
# [EN] day's scenes
# [EN] : into novel form, **accumulated by day** in one file (not overwritten each day).
FILE_DAY_NOVEL = '当天故事.md'


@dataclass
class _Slot:
    """台账里的一行：这个职位最近一次出工的结果。
        English:
    One line in the ledger: the result of this role's most recent work call.
    """

    key: str
    state: str = 'idle'          # idle / working / done / off / onduty
    note: A.CrewNote | None = None
    day: int = 0
    #: **这一趟出工是什么时候开始的**（`time.monotonic()`，0 = 没在跑）。
    #: 只给界面用：出工中那一行要显示"已跑 N 秒"—— 用户 2026-10-08 要的
    #: 「让用户知道谁在干活」里，一半是"在跑"，另一半是"跑了多久还没回来"。
    # [EN] : **When did this work session start** (`time.monotonic()`, 0 = not running).
    # [EN] : For the UI only: the working row must show "running for N seconds" - requested by user on
    # [EN] 2026-10-08
    # [EN] : in "let the user know who is working", half is "is running", the other half is "how long it
    # [EN] has been running without coming back".
    t0: float = 0.0


class Studio:
    """制片厂：叫谁出工、记谁交了什么、把产出送到该去的地方。

    `on_note` 是**播报通道**（`cb(CrewNote)`）—— 与 `sim/loop` 的其它回调同一规矩：
    播报失败绝不影响推演（这里连异常都不往外抛）。
    
        English:
    Studio: who to call to work, record what each handed in, and send the output where it should go.
        `on_note` is the **broadcast channel** (`cb(CrewNote)`) —— same rule as the other callbacks in `sim/loop`:
        a broadcast failure never affects the simulation (here it doesn't even throw an exception outward).
    """

    def __init__(self, world: Any, db: Any, runfolder: Any = None, *,
                 on_note: Callable[[A.CrewNote], None] | None = None,
                 on_stage: Callable[[str, float, bool], None] | None = None,
                 on_work: Callable[[str, str], None] | None = None,
                 on_line: Callable[[str], None] | None = None):
        self.world = world
        self.db = db
        self.runfolder = runfolder
        self._on_note = on_note
        #: **阶段播报**（`cb(key, 秒数, 是否成功)`）—— 2026-10-07。
        #: 与 `on_note` 分开：那个报"某个职位交了一份活"（有产出），
        #: 这个报"某段流程走完了"（只有阶段名与用时）。用户要的
        #: 「只显示阶段名和用时，不真实输出内部细节」就是这一条。
        # [EN] : **Stage broadcast** (`cb(key, seconds, success)`) — 2026-10-07.
        # [EN] : Separate from `on_note`: that one reports "a role submitted a piece of work" (has output),
        # [EN] : this one reports "a segment of the flow finished" (only stage name and elapsed time). What the
        # [EN] user asked for
        # [EN] : "only show the stage name and elapsed time, do not actually output internal details" is this
        # [EN] one.
        self._on_stage = on_stage
        #: **出工状态播报**（`cb(职位key, 'working'|'done'|'idle'|'off')`）
        #: —— 2026-10-08。用户：「右侧的剧组成员 谁在干活请高亮显示
        #: 等不干活了再恢复普通样式 以让用户知道谁在干活」。
        # [EN] : **Work status broadcast** (`cb(role_key, 'working'|'done'|'idle'|'off')`)
        # [EN] : —— 2026-10-08. User: "For the crew members on the right, please highlight whoever is working
        # [EN] : and restore the normal style once they stop working, so the user knows who is working".
        #:
        #: ⚠ 为什么要**事件**、而不只靠界面轮询：出工是一阵一阵的，
        #:   界面那 0.5 秒一轮的定时刷新**天然会漏帧** —— 短的一次出工
        #:   （演示模式下几十毫秒）整个在两次刷新之间，界面上根本看不出
        #:   有人动过。有这条，出工**开始那一刻**界面就会立刻重画。
        #: ⚠ 只传 `key` 与 `state`，**不传产出** —— 与 `on_stage` 同一条纪律：
        #:   这是"谁在忙"的播报，不是内容通道（内容走 `on_note`）。
        # [EN] : ⚠ Why **events** are needed instead of relying only on UI polling: work comes in bursts,
        # [EN] :   the UI's 0.5-second periodic refresh **naturally misses frames** — a short work session
        # [EN] : (tens of milliseconds in demo mode) falls entirely between two refreshes, so the UI cannot
        # [EN] tell at all
        # [EN] :   that anyone moved. With this, the UI redraws immediately **at the moment work starts**.
        # [EN] : ⚠ Only pass `key` and `state`, **do not pass output** — same discipline as `on_stage`:
        # [EN] :   this is a "who is busy" broadcast, not a content channel (content goes through `on_note`).
        self._on_work = on_work
        #: **在中栏起一条剧组消息**（`cb(职位key)`）—— 2026-10-23，用户点名。
        #:  为什么它不能挂在 `on_work` 上：`on_work` 是"**谁在忙**"，而
        #:  `audit()`（每拍一次的审读闸）**照样要报它**（右侧面板要亮），
        #:  但它**故意不发中栏消息**（每拍一行"审读已交活"会把正文淹掉，
        #:  见 `audit` 的 docstring）。两件事混在一条回调上，
        #:  要么审读把中栏刷爆，要么右侧不再高亮 —— 都不对。
        #:  ⇒ 只有 `call()`（真正会交活、会有产出的那条路）调这个。
        # [EN] **Open one crew message in the middle column** (`cb(role key)`) -- 2026-10-23,
        # [EN] named by the user. Why it cannot hang off `on_work`: that channel is "**who is
        # [EN] busy**", and `audit()` (the per-beat review gate) **must report it** (the right
        # [EN] panel lights up) while **deliberately not sending a middle-column message** (one
        # [EN] "review submitted" row per beat would drown the prose -- see `audit`'s
        # [EN] docstring). Sharing one callback would either flood the column from review or
        # [EN] stop the highlight -- both wrong.
        # [EN] => Only `call()` (the path that really hands work in and has output) calls this.
        self._on_line = on_line
        # ⚠ 用**有效名册**（`ROSTER.roles()`，含作者改过与自建的职位）——
        #   拿出厂名册铺槽位的话，自建职位永远没有那一行（界面上看不到它），
        #   而内置职位被改名后，台账里还会留下旧名字的僵尸行。
        # [EN] ⚠ Use the **effective roster** (`ROSTER.roles()`, including roles renamed by the author and
        # [EN] custom roles) —
        # [EN] if you lay out slots from the factory roster, a custom role will never have that row (it is
        # [EN] invisible in the UI),
        # [EN] and after a built-in role is renamed, zombie rows with the old name remain in the ledger.
        self._slots: dict[str, _Slot] = {r.key: _Slot(key=r.key)
                                         for r in ROSTER.roles()}
        #: 美术指导只在**一份**里缓存（一次定、全剧用）—— 见 `art_note`。
        # [EN] : The art director is cached in only **one** place (decided once, used for the whole show) — see
        # [EN] `art_note`.
        self._art: A.CrewNote | None = None
        # 当天地图：**按天**缓存（一天一张，别重复问模型）
        # [EN] The day's map: cached **by day** (one per day, do not repeatedly ask the model)
        self._day_maps: dict[int, A.CrewNote] = {}
        #: 道具单按天缓存（同一天重复问没意义，换个落点就白花一次调用）
        # [EN] : The prop list is cached by day (asking again on the same day is meaningless; changing the drop
        # [EN] point wastes one call for nothing)
        self._props: dict[int, A.CrewNote] = {}
        #: 造型表按天缓存（`image_prefix` 要按天取它 → 出图与人物形象一致）
        # [EN] : The modeling sheet is cached by day (`image_prefix` must be fetched by day → images stay
        # [EN] consistent with the character's appearance)
        self._stylist: dict[int, A.CrewNote] = {}
        #: 声音设计按天缓存（同上：`sim/loop` 取它写环境句）
        # [EN] : Sound design is cached by day (same as above: `sim/loop` fetches it to write the ambience
        # [EN] sentence)
        self._sound: dict[int, A.CrewNote] = {}
        #: 每个职位累计出工次数与失败次数（**给人看的事实**，不是打分）
        # [EN] : Cumulative work count and failure count per role (**facts for humans to see**, not scoring)
        self._stats: dict[str, dict[str, int]] = {
            r.key: {'runs': 0, 'fails': 0} for r in ROSTER.roles()}
        # ★ 去 AI 味审计的当日累积（2026-10-07）：所有职位的命中都攒在这儿，
        #   `sim/loop` 在日界取走并落盘 `去AI审计.md`（见 `take_deai_hits`）。
        #   为什么不各自落盘：一天里十几个职位各写一份，作者要翻十几页才知道
        #   "今天 AI 味重不重"。
        # [EN] ★ Daily accumulation for the de-AI audit (2026-10-07): all roles' hits are collected here,
        # [EN] `sim/loop` takes them at the day boundary and writes `去AI审计.md` (see `take_deai_hits`).
        # [EN] Why not write to disk separately: with a dozen-plus roles each writing a file in one day, the
        # [EN] author would have to flip through a dozen pages to know
        # [EN] "whether the AI flavor is strong today".
        self._deai_hits: list = []
        self._deai_checked: int = 0

    # ══════════════════════════════════════════════════════════════════
    #  启动自查
    # [EN] Startup self-check
    # ══════════════════════════════════════════════════════════════════
    @staticmethod
    def selfcheck() -> dict[str, Any]:
        """开机自查：名册与在位者对得上吗？每条 hook 都真的存在吗？

        返回 `{'members_missing': [...], 'hooks_missing': {...}}`。
        两者都空 = 这班人齐了、接线都通。

        为什么放在**这里**而不是写个验证脚本就完事：这两个缺口的表现都是
        "某个职位于是一直不吭声"，而那是**最难查的一类故障**
        （日志里没有报错，界面上只是少了个人）。所以让它开机就说话。
        
                English:
        Startup self-check: do the roster and the seated members match? Does every hook really exist?
                Returns `{'members_missing': [...], 'hooks_missing': {...}}`.
                Both empty = this crew is complete and all wiring is connected.
                Why put it **here** instead of just writing a validation script: the symptom of both gaps is
                "some role just never speaks up", and that is **the hardest class of failure to diagnose**
                (no errors in the logs, the UI just shows one fewer person). So let it speak at startup.
        """
        return {'members_missing': A.missing_members(),
                'hooks_missing': ROSTER.audit_hooks()}

    def stage_now(self, key: str) -> None:
        """**没有耗时可言**的那种阶段（开演 / 暂停 / 继续）。

        与 `stage()` 共用同一条播报通道（`_on_stage`）—— 两处各报一处的话，
        "谁在报阶段"就有两个入口，探针/判据只能看到一个。
        
                English:
        A phase with **no elapsed time to speak of** (start / pause / resume).
                Shares the same broadcast channel as `stage()` (`_on_stage`) —— if each reported separately,
                "who is reporting the phase" would have two entry points, and probes/criteria could only see one.
        """
        _LOG.info('阶段「%s」（瞬时）', key)
        # ⚠ **这里不登记"正在做什么"**（2026-10-21 想清的一件事）：瞬时阶段没有
        #   "结束"可言，登进去就没人弹得出来 —— 栈底会攒下一串永远不退的标签，
        #   状态条最后显示的是"上一件早做完的事"。
        #   收尾那条要靠**有始有终**的登记：`RunLoop._finish` 用 `push/pop`
        #   把整段收尾包起来（见那边的说明），所以"点停止之后一直是收尾"
        #   这件事由它保证。
        # [EN] ⚠ **Do not register "what is happening" here**: an instantaneous stage has no "end",
        # [EN] so nothing can ever pop it -- stale labels accumulate at the bottom of the stack and the
        # [EN] bar ends up showing something long finished. The wrap-up label is guaranteed by a
        # [EN] **push/pop pair** in `RunLoop._finish` instead (see there).
        if self._on_stage is not None:
            try:
                self._on_stage(str(key), 0.0, True)
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('阶段播报失败（不影响推演）：%r', e)

    # ══════════════════════════════════════════════════════════════════
    #  台账（界面读它画「剧组」面板）
    # [EN] Ledger (the UI reads it to draw the "crew" panel)
    # ══════════════════════════════════════════════════════════════════
    def ledger(self) -> list[dict]:
        """名册顺序的一班人，各带当前状态与最近一句产出。

        **界面只读这个**（不自己去翻 `_slots`）——
        这样"谁在干什么"只有一处事实来源，界面上显示的和日志里记的不会打架。

        `busy` / `secs`（2026-10-08）：界面拿它们**高亮"正在出工"的那一行**
        （用户：「谁在干活请高亮显示 等不干活了再恢复普通样式」）。
        为什么另给一个 `busy` 而不是让界面自己判 `state == 'working'`：
        判断口径只有在这里定义一次才不会漂（界面若自己判，将来多一种"在跑"
        的状态时，一定会漏掉某处）；`secs` 是**已经跑了多少秒**（只在忙时有意义）。
        
                English:
        One crew in roster order, each with current state and most recent output line.
                **The UI reads only this** (it doesn't go poking through `_slots` itself) ——
                this way "who is doing what" has only one source of truth, and what the UI shows won't conflict with what the logs record.
                `busy` / `secs` (2026-10-08): the UI uses them to **highlight the row of whoever is currently working**
                (user: "please highlight whoever is working, and restore normal styling when they stop").
                Why provide a separate `busy` instead of letting the UI judge `state == 'working'` itself:
                the criterion is defined only here once so it won't drift (if the UI judged it itself, when a new "running"
                state appears in the future, some place would surely be missed); `secs` is **how many seconds it has already run** (only meaningful while busy).
        """
        out: list[dict] = []
        now = time.monotonic()
        for r in ROSTER.roles():
            s = self._slots.get(r.key) or _Slot(key=r.key)
            st = s.state
            if not self._enabled(r.key):
                st = 'off'
            busy = (st == 'working')
            out.append({
                'key': r.key,
                'name': r.name,
                'duty': r.duty,
                'when': r.when,
                'feeds': r.feeds,
                'existed': r.existed,
                'tier': r.tier,
                'state': st,
                'busy': busy,
                'secs': (round(now - s.t0, 1) if (busy and s.t0) else 0.0),
                'day': s.day,
                'line': (s.note.one_line() if s.note else ''),
                'ok': bool(s.note.ok) if s.note else True,
                **self._stats.get(r.key, {}),
            })
        # ── 常驻岗「演员」按**在场角色**展开成子 Agent（2026-10-16 用户要求）──
        #   推演实际是**每个在场角色各跑各的**（各自有 Agent、各自决策、
        #   各自的思维链落在 `world.actor_think`），但界面一直只显示一个
        #   「演员」角色行。这里把每个在场角色作为 `actor` 的**子条目**挂进台账，
        #   面板据此把它们缩进显示在「演员」下面，并各自显示"在岗 · 正在做：{盘算}"。
        #   ⚠ 数据源是**模拟自己**已记的（`world.actor_think` / `on_stage_names`），
        #     不是界面自己编的 —— 与本项目"台账是唯一事实来源"同一条。
        #   ⚠ 只在 `world` 真有时才展开（无头/测试里 `world=None` ⇒ 不挂，
        #     不影响其它判据）；不在场的角色不挂（它们没在"演"）。
        # [EN] -- The on-duty "actor" role expands into **per-character sub-agents** (user 2026-10-16) --
        # [EN] The simulation actually runs **each on-stage character separately** (each has its own Agent,
        # [EN] its own decision, its chain-of-thought in `world.actor_think`), but the UI only ever showed one
        # [EN] "actor" role row. Here each on-stage character is hung into the ledger as a **sub-entry** of `actor`,
        # [EN] and the panel indents them under "actor", each showing "在岗 · 正在做：{thinking}".
        # [EN] ⚠ The data source is what the simulation **already records** (`world.actor_think` /
        # [EN] `on_stage_names`), not invented by the UI -- same rule as "ledger is the single source of truth".
        # [EN] ⚠ Only expand when `world` exists (headless/tests with `world=None` => no sub-entries,
        # [EN] other checks unaffected); off-stage characters are not hung (they aren't "acting").
        if self.world is not None:
            _on_stage = []
            try:
                _os = self.world.on_stage_names()
                _on_stage = list(_os) if _os else []
            except Exception:                                    # noqa: BLE001
                _on_stage = []
            if _on_stage:
                _think = getattr(self.world, 'actor_think', None) or {}
                _think_at = getattr(self.world, 'actor_think_at', None) or {}
                _now = time.monotonic()
                _actor_day = (self._slots.get('actor').day
                              if self._slots.get('actor') else 0)
                for _nm in _on_stage:
                    _nm = str(_nm)
                    # ★ 这一拍在动吗？（高亮判据，复用 `busy` 口径）
                    #   距最近一次决策完成 < 窗口 ⇒ 正在出工（暖金高亮）；
                    #   否则只是"在岗"。这样界面能实时看到"谁这一拍在盘算/行动"。
                    # [EN] Moving this beat? (highlight criterion, reuses the `busy` flag)
                    # [EN] within the window of last decision -> working (warm-gold);
                    # [EN] else just "在岗". The UI thus sees who is deliberating/acting now.
                    _at = _think_at.get(_nm)
                    _busy = isinstance(_at, (int, float)) and (
                        (_now - _at) < CHAR_BUSY_WINDOW)
                    _secs = (_now - _at) if isinstance(_at, (int, float)) else 0.0
                    out.append({
                        'key': f'actor::{_nm}',
                        'name': f'演员·{_nm}',
                        'duty': str(_think.get(_nm) or '')[:60],
                        'when': '', 'feeds': '', 'existed': True,
                        'tier': 'character',
                        'state': 'onduty',
                        'busy': _busy,
                        'secs': (round(_secs, 1) if _busy else 0.0),
                        'day': _actor_day,
                        'runs': 0,            # 子 Agent 不走 studio.call，出工计数恒为 0
                        'fails': 0,
                        'line': '',           # 面板用 duty 拼"在岗 · 正在做：…" / busy 时"正在做：…"
                        'ok': True,
                        'parent': 'actor',
                        'is_sub': True,
                        **self._stats.get(f'actor::{_nm}', {}),
                    })
        return out

    def _enabled(self, key: str) -> bool:
        """这个职位今天上不上工（关掉的旋钮 → `off`，界面上要**说出来**）。
                English:
        Whether this role works today (a knob turned off → `off`, and the UI must **say so**).
        """
        if not CFG.b('CREW') and key in ('novelist', 'screenwriter',
                                         'continuity', 'props', 'art',
                                         'publicity', 'researcher',
                                         'settings_room', 'reviewer',
                                         'stylist', 'sound', 'polisher',
                                         'rehearsal', 'script_doctor'):
            return False
        return {
            'continuity': CFG.b('CREW_CONTINUITY'),
            # ★ 剧本审读（2026-10-08）：它有自己的总闸（`SCRIPT_REVIEW`），
            #   不挂在 `CREW_*` 那一族上 —— 用户要的是一个**独立的**职位，
            #   关掉"剧组"的时候它该不该跟着关，由它自己的开关说了算。
            # [EN] ★ Script review (2026-10-08): it has its own master switch (`SCRIPT_REVIEW`),
            # [EN] not hung under the `CREW_*` family — what the user wants is an **independent** role,
            # [EN] whether it should close along with "crew" is decided by its own switch.
            'script_doctor': CFG.b('SCRIPT_REVIEW'),
            'props': CFG.b('CREW_PROPS'),
            'art': CFG.b('CREW_ART'),
            'research': CFG.b('CREW_RESEARCH'),
            'publicity': CFG.b('CREW_PUBLICITY'),
            'settings_room': CFG.b('CREW_SETTING_TALK'),
            'reviewer': CFG.b('CREW_REVIEW'),
            'stylist': CFG.b('CREW_STYLIST'),
            'sound': CFG.b('CREW_SOUND'),
            'polisher': CFG.b('CREW_POLISH'),
            'rehearsal': CFG.b('CREW_REHEARSAL'),
        }.get(key, True)

    def note_of(self, key: str) -> A.CrewNote | None:
        s = self._slots.get(str(key))
        return s.note if s else None

    # ══════════════════════════════════════════════════════════════════
    #  出工
    # [EN] Work session
    # ══════════════════════════════════════════════════════════════════
    async def call(self, key: str, ctx: A.SetCtx, **kw) -> A.CrewNote:
        """叫一个职位出工，记进台账，播报，并把产出落盘。

        **唯一入口** —— 所有出工都走这里，所以"台账/落盘/播报"三件事
        不可能漏掉某一个（漏掉的那种表现是"这个职位明明干了活，界面上没有"）。

        ★★ `extra_section`（2026-10-12 用户要求"语言审校并进今日总结"）：
          一支**不属于这位职位、但必须跟着它一起上屏/落盘**的一段 Markdown。
          之所以做成这个参数而不是"事后改文件"：正文要同时到达**四个地方**
          （今日总结.md · 中栏的那条 SUMMARY · 台账 sidecar · 日志），
          而它们**全部发生在这个方法的尾部** —— 在这里合进去，四处一次到位；
          事后补就等于把那条路径重写一遍，迟早漏一处。
          ⚠ 合入的时机在 `_deai_check` **之后**（见下面那两行）：
            合进来的正是"AI 味重的原句"，先查就等于让复盘替语言审校背一次
            `去AI命中`，台账上会记成复盘自己写了 AI 味。
          ⚠ 它**不转发给职位实现**（在 `kw` 里弹掉）—— 那是"给剧本的附加材料"，
            不是这一位要读的输入。

        English:
        Call a role to work, record it in the ledger, broadcast, and persist the output to disk.
                **The only entry point** —— all work calls go through here, so the three things
                "ledger/persist/broadcast"
                cannot have any one missed (the symptom of missing one is "this role clearly did work, but
                the UI shows nothing").
                ★★ `extra_section` (user request 2026-10-12: "merge the language review into today's
                summary"):
                  a block of Markdown that **does not belong to this role but must go on screen / to disk
                  along with it**.
                  Why a parameter rather than "patching the file afterwards": the body must reach **four
                  places** at once
                  (今日总结.md · the middle column's SUMMARY entry · the ledger sidecar · the log),
                  and **all of them happen at the tail of this method** -- merging here gets all four in
                  one shot;
                  patching afterwards means rewriting that path and eventually missing one.
                  ⚠ The merge happens **after** `_deai_check` (see the two lines below):
                    what gets merged in is exactly "the AI-flavoured original sentences"; checking first
                    would make the retrospective carry a `去AI命中` for the language review, and the
                    ledger would record that the retrospective itself wrote AI-flavoured text.
                  ⚠ It is **not forwarded to the role implementation** (popped out of `kw`) -- it is
                    "extra material for the script", not input for this role to read.
        """
        # ⚠ 先弹掉：它会跟着 `**kw` 进 `member.run()`，而职位实现不认识这个参数
        #   （会直接 TypeError）。放在最前面，任何早退路径都不会漏。
        # [EN] ⚠ Pop it first: otherwise it would travel in `**kw` into `member.run()` and the role
        # [EN] implementation does not know this parameter (immediate TypeError). Do it first, so no
        # [EN] early-return path can miss it.
        extra_section = str(kw.pop('extra_section', '') or '')
        member = A.member(key)
        # ★★ 2026-10-10：把「现在是谁在出工」告诉用量台账。
        #   `call` 是**所有出工的唯一入口**，所以在这一处设一次就够 ——
        #   在这一段里发生的所有 LLM 调用（含它内部的多次重试）都会挂到
        #   这个 Agent 名下。收工后清掉（见下面的 finally），
        #   免得"没人出工时的调用"被算到上一个 Agent 头上。
        # [EN] ★★ 2026-10-10: Tell the usage ledger "who is currently working".
        # [EN] `call` is **the only entry point for all work**, so setting it once here is enough —
        # [EN] all LLM calls happening in this block (including its internal multiple retries) will be attached
        # [EN] to
        # [EN] this Agent's name. Clear it after wrap-up (see the `finally` below),
        # [EN] so that "calls made when nobody is working" are not counted against the previous Agent.
        try:
            from llm import usage as USAGE
            USAGE.set_ctx(agent=member.role.name if getattr(member, 'role', None) else key)
        except Exception:                                        # noqa: BLE001
            pass
        # ★★ 2026-10-12：「**这一位用哪个模型**」也在这儿设一次。
        #   `call` 是**所有出工的唯一入口**，所以在这一处设一次就够 ——
        #   这一位内部的所有 LLM 调用（含 `llm.replies.ask()` 的重试）
        #   都会落到它点名的那个模型上；没点名就跟着它的档位/默认模型走
        #   （解析顺序见 `llm/models.resolve()`）。
        # [EN] ★★ 2026-10-12: "**which model this one uses**" is also set once here.
        # [EN] `call` is **the only entry point for all work**, so setting it once here is enough --
        # [EN] every LLM call inside this one (including the retries of `llm.replies.ask()`) lands on
        # [EN] the model it named; if it named none, it follows its tier / the default model (see
        # [EN] `llm/models.resolve()` for the order).
        from contextlib import ExitStack
        _stack = ExitStack()
        try:
            _stack.enter_context(MODELS.use(key))
        except Exception:                                        # noqa: BLE001
            _stack = None
        slot = self._slots.setdefault(key, _Slot(key=key))
        slot.state = 'working'
        slot.t0 = time.monotonic()
        # ══════════════════════════════════════════════════════════════
        #  **实时房间**（2026-10-23，用户点名）：界面靠它展开看"这一位正在想什么"
        # [EN] **Live room** (named by the user 2026-10-23): the UI expands it to show
        # [EN] "what this one is thinking"
        # ══════════════════════════════════════════════════════════════
        #  用户：「表示在执行的消息 我点开这个按钮以后应该是 **LLM 的思考过程流式返回**」。
        #  ★ 顺序是 **先建房间、再报"出工了"**：界面收到"出工"就要能立刻读到房间
        #    （否则那一刻展开是空的，看起来像"没接上"）。
        #  ★ `enter` 设的是 `ContextVar`：这一位内部**所有** LLM 调用（含并行的）
        #    都会把流式增量落进同一个房间。出来必须 `leave`，否则下一位的增量
        #    会继续落进上一位的房间（症状：展开框里是别人的思考）。
        # [EN] The user: "for messages that are executing, clicking this button should show
        # [EN] **the LLM's thinking streaming in**".
        # ★ Order: **create the room first, then report "working"** -- the UI must be able
        #   to read the room the instant it hears "working" (otherwise the expander is empty
        #   at that moment and looks broken).
        # ★ `enter` sets a `ContextVar`: **all** LLM calls inside this role (including
        #   parallel ones) pour their streaming deltas into the same room. It must be
        #   `leave`d on the way out, or the next role's deltas keep landing in this room
        #   (symptom: someone else's thinking in this expander).
        _lv_tok = None
        try:
            from crew import live as LV
            LV.install()
            _r = getattr(member, 'role', None)
            LV.begin(key, getattr(_r, 'name', '') or key,
                     getattr(_r, 'duty', '') or '')
            _lv_tok = LV.enter(key)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧组实时房间没建起来（展开框会看不到思考过程）：%r', e)
        # ★ 流式：挂进**已有的** `_stack`（`finally` 里已经会关掉它）——
        #   再开一个 try/finally 就是"同一件事两处实现"。
        # [EN] Streaming: entered into the **existing** `_stack` (already closed in
        # `finally`) -- a second try/finally would be "the same thing implemented twice".
        try:
            if _stack is not None and CFG.b('CREW_STREAM'):
                from llm import router as _R
                _stack.enter_context(_R.stream_scope(True))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('打开流式失败（改回整段返回，不影响推演）：%r', e)
        # ★ 「谁在干活」——出工**开始的那一刻**就报一次（2026-10-08）。
        #   放在 `await` **之前**：出工那几十秒里界面才是"有东西可看"的，
        #   等跑完再报就等于全程没报过。
        # [EN] ★ "Who is working" — report once **at the moment work starts** (2026-10-08).
        # [EN] Placed **before** `await`: only then does the UI have "something to look at" during those tens
        # [EN] of seconds of work,
        # [EN] reporting only after it finishes is equivalent to never reporting at all.
        # ★★ 2026-10-23：**先起一条中栏消息，再报"出工了"**。
        #   用户要的是"看着这一行字从「出工中」变成「已交活」"，所以这一行要在
        #   任何子步骤之前就存在（那几十秒里才有东西可点）。
        #   ⚠ 只有这条路会调 `_line_begin`（`audit` 不调，理由见 `_on_line`）。
        # [EN] ★★ 2026-10-23: **open the middle-column message first, then report "working"**.
        # [EN] What was asked for is watching that line turn from working to handed-in, so the
        # [EN] line must exist before any sub-step (those tens of seconds need something to click).
        # [EN] ⚠ Only this path calls `_line_begin` (`audit` does not; see `_on_line`).
        self._line_begin(key)
        self._work_notify(key, 'working')
        # ★★★ 2026-10-21（用户点名「每个阶段都要给出正在做什么」）：
        #   在**出工那一刻**把"这一位在做什么"压进登记栈 —— 状态条每 0.5 秒读一次。
        #   这一句是收尾那几个职位能被看见的唯一原因：收尾整段只有一个
        #   `_stage('day_review')`，中间跑场记/宣发/审校/复盘全靠这里逐个替换。
        #   ⚠ 用 `push/pop` 而不是直接设：`call` 可能套在 `stage` 里，弹掉自己就回落给外层。
        # [EN] ★★★ 2026-10-21 (user: "every stage must say what it is doing"): the moment this role
        # [EN] starts working, push "what it is doing" onto the registry -- the status bar reads it
        # [EN] every 0.5 s. This single line is the only reason the wrap-up roles are visible: the
        # [EN] whole wrap-up is one `_stage('day_review')`, and continuity/publicity/polish/review
        # [EN] cycle through here one by one.
        # [EN] ⚠ `push/pop`, not a plain set: a `call` may sit inside a `stage`, and popping itself
        # [EN] falls back to the outer label.
        try:
            _role = getattr(member, 'role', None)
            _doing_tok = DOING.push(DOING.role_label(
                getattr(_role, 'name', '') or key, getattr(_role, 'duty', '') or ''))
        except Exception:                                    # noqa: BLE001
            _doing_tok = 0
        _t0 = time.monotonic()
        # ★★★ 2026-10-15（用户）：非阻塞 Agent 超时跳过。
        #   `CREW_STAGE_TIMEOUT` 的秒数过一遍 `asyncio.wait_for()`；
        #   阻塞 Agent（director / novelist / actor 等）**不在 `NONBLOCK_ROLES` 里**，
        #   走旧路（只受 LLM 层超时约束）。
        #   ⚠ `asyncio.TimeoutError` 和普通异常**都走同一个 finally**清理，
        #     只是 `note` 里的 `ok=False` + `why='超时跳过'` 不同。
        # [EN] ★★★ 2026-10-15 (user): skip non-blocking agents on timeout.
        # [EN] `CREW_STAGE_TIMEOUT` seconds wrap `asyncio.wait_for()`;
        # [EN] blocking agents (director / novelist / actor etc.) are **not in `NONBLOCK_ROLES`**
        # [EN] and take the old path (only LLM-level timeout applies).
        # [EN] ⚠ `asyncio.TimeoutError` and normal exceptions **both go through the same finally**
        # [EN] cleanup; only `note` differs (ok=False, why='超时跳过').
        #
        # ★★★ 2026-10-15 第二版（用户：「美术还是400多秒没结束」）—— **改成"总预算"制**。
        #   第一版是"每次 300 秒、重试 1 次" ⇒ **最坏 600 秒**才跳过，
        #   而用户说的"超时时间比如 300 秒"指的是**总共**等 300 秒。
        #   实据（`logs/nws_<项目名>_2026_10_15_11_07_52.log`）：
        #     11:08:15 发请求 → 11:13:15 第 1 次超时（**300s，机制本来是对的**）
        #     → 11:17:09 **用户手动停止**（他等到 534 秒就失去耐心了）
        #     → 11:18:15 第 2 次超时并跳过（如果没停，会在这里）
        #   ⇒ 机制没错，是**总时长口径**错了：用户要的是"300 秒内试完、不行就跳"。
        #
        #   现在：`CREW_STAGE_TIMEOUT` = **总预算**（不是单次窗口）。
        #   每次尝试的窗口 = **剩余预算 ÷ 剩余尝试次数** ⇒ 无论重试几次，
        #   总耗时都**不会超过预算**（300s 就是 300s）：
        #     · 2 次尝试（默认）：150s + 150s = 300s
        #     · 3 次尝试：100s + 100s + 100s = 300s
        # [EN] ★★★ 2026-10-15 v2 (user: "art still isn't finishing after 400+ seconds") --
        # [EN] **switched to a "total budget" model.**
        # [EN] v1 was "300s per attempt, 1 retry" => **up to 600s** before skipping, but the user's
        # [EN] "a timeout like 300 seconds" meant **300s total**.
        # [EN] Evidence (`logs/nws_<项目名>_2026_10_15_11_07_52.log`): 11:08:15 request sent ->
        # [EN] 11:13:15 attempt 1 timed out (**300s -- the mechanism was right all along**) -> 11:17:09
        # [EN] **user stopped it manually** (lost patience at 534s) -> 11:18:15 attempt 2 timed out and
        # [EN] skipped (where it would have landed).
        # [EN] => The mechanism was fine; the **budget semantics** were wrong: the user wants "try within
        # [EN] 300 seconds, then skip".
        # [EN] Now `CREW_STAGE_TIMEOUT` is the **total budget** (not a per-attempt window).
        # [EN] Each attempt's window = **remaining budget / remaining attempts**, so the total never
        # [EN] exceeds the budget no matter how many retries: 2 attempts => 150s + 150s = 300s;
        # [EN] 3 attempts => 100s + 100s + 100s = 300s.
        _stage_budget = int(CFG.i('CREW_STAGE_TIMEOUT') or 0)
        _stage_retries = max(0, int(CFG.i('CREW_STAGE_RETRIES') or 0))
        try:
            if _stage_budget > 0 and key in NONBLOCK_ROLES:
                _role_name = (getattr(member.role, 'name', key)
                              if getattr(member, 'role', None) else key)
                _attempts = _stage_retries + 1     # 1 次正式 + N 次重试
                _deadline = time.monotonic() + _stage_budget
                note = None
                _used = 0
                for _i in range(_attempts):
                    _left = _deadline - time.monotonic()
                    if _left <= 0:                 # 预算用完了，不再开新的一轮
                        break
                    #: 剩余时间**平均分给剩下的尝试次数** ⇒ 总时长封顶在预算内
                    # [EN] : split the remaining time **evenly across the remaining attempts** so the
                    # [EN] total is capped by the budget
                    _win = _left / max(1, _attempts - _i)
                    try:
                        note = await asyncio.wait_for(
                            member.run(ctx, **kw), timeout=_win)
                        _used = _stage_budget - max(0, _deadline - time.monotonic())
                        break
                    except asyncio.TimeoutError:
                        _used = _stage_budget - max(0, _deadline - time.monotonic())
                        _LOG.warning(
                            '非阻塞 Agent %s（%s）本次窗口 %.0fs 超时 —— 第 %d/%d 次'
                            '（总预算 %ds，已用 %.0fs）',
                            key, _role_name, _win, _i + 1, _attempts,
                            _stage_budget, _used)
                    except Exception as ex:       # noqa: BLE001
                        _LOG.warning(
                            '非阻塞 Agent %s（%s）异常 —— 第 %d/%d 次：%r',
                            key, _role_name, _i + 1, _attempts, ex)
                if note is None:       # 预算内所有尝试都失败了
                    note = A.CrewNote(
                        role=key, ok=False, title=_role_name,
                        why=f'超时跳过（总预算 {_stage_budget}s 内试了 '
                            f'{_attempts} 次均未成功）')
                    self._slots[key].state = 'idle'
                    self._work_notify(key, 'idle')
                    _LOG.warning('非阻塞 Agent %s（%s）超时跳过 —— '
                                 '不影响后续流程（总预算 %ds）',
                                 key, _role_name, _stage_budget)
            else:
                note = await member.run(ctx, **kw)
        finally:
            # ★★★ 2026-10-21：**出场弹掉自己**（按令牌弹，不按栈顶 ——
            #   收尾时几个职位是顺序跑的，但异常路径上可能有乱序退出）。
            #   ⚠ 必须在 `finally` 里：这一位抛异常时，"正在做什么"不能一直挂着，
            #     否则状态条会停在"场记 · 连戏检查"直到整轮结束。
            # [EN] ★★★ 2026-10-21: **pop self on the way out** (by token, not by top -- the wrap-up
            # [EN] roles run sequentially, but exception paths can exit out of order).
            # [EN] ⚠ Must be in `finally`: when this role raises, "what is happening" must not stay
            # [EN] stuck, or the bar sits at "场记 · 连戏检查" until the whole round ends.
            DOING.pop(_doing_tok)
            # ★ 2026-10-23：**退出实时房间**（按令牌弹，与 `DOING` 同一条纪律）。
            #   不弹的后果不是报错，而是**下一位的思考继续落进这一位的房间**
            #   —— 界面上看起来完全正常（有字、在增长），只是主人错了。
            # [EN] ★ 2026-10-23: **leave the live room** (by token, same discipline as
            # [EN] `DOING`). Not leaving does not raise -- the next role's thinking simply
            # [EN] keeps landing in this room, and the UI looks perfectly normal (text
            # [EN] appearing, growing), just attributed to the wrong owner.
            if _lv_tok is not None:
                try:
                    from crew import live as LV
                    LV.leave(_lv_tok)
                except Exception:                                # noqa: BLE001
                    pass
            # ★ 出工结束就清掉 Agent 上下文（清洁性：不让下一个人的账挂到这个人身上）
            # [EN] ★ Clear the Agent context as soon as work ends (cleanliness: do not let the next person's
            # [EN] account be charged to this person)
            try:
                from llm import usage as USAGE
                USAGE.clear_ctx('agent')
            except Exception:                                    # noqa: BLE001
                pass
            # ★ 同上：模型上下文也要还原（它是 `ContextVar`，并行出工时
            #   各走各的栈；**必须在 finally 里**，否则一位出工抛异常
            #   会把它的模型泄漏给后面所有人）。
            # [EN] ★ Same as above: the model context must be restored too (it is a `ContextVar`, so
            # [EN] parallel work sessions each have their own stack; **it must be in `finally`**,
            # [EN] otherwise one failing session leaks its model to everyone after it).
            if _stack is not None:
                try:
                    _stack.close()
                except Exception:                                # noqa: BLE001
                    pass
        # ★ **用时**记进 `data`（2026-10-07）：中栏现在只报「阶段名 + 用时」，
        #   不报产出内容 —— 那个用时就是从这儿来的。
        #   记在 `data` 而不是新字段：`data` 已经是"给程序读的结构化部分"，
        #   而 sidecar / 台账 / 落盘都会带上它（新字段要改四处序列化）。
        # [EN] ★ **Elapsed time** recorded into `data` (2026-10-07): the middle column now only reports "stage
        # [EN] name + elapsed time",
        # [EN] not the output content — that elapsed time comes from here.
        # [EN] Recorded in `data` rather than a new field: `data` is already "the structured part for programs
        # [EN] to read",
        # [EN] and sidecar / ledger / disk-write all carry it (a new field would require changing four
        # [EN] serialization sites).
        try:
            note.data = dict(note.data or {})
            note.data.setdefault('用时', round(time.monotonic() - _t0, 2))
        except Exception:                                        # noqa: BLE001
            pass
        slot.note = note
        slot.state = 'done' if note.ok else 'idle'
        slot.day = int(getattr(ctx, 'day', 0) or 0)
        # ★ 收工也报一次 —— 界面据此**把高亮撤掉、恢复普通样式**
        #   （用户原话：「等不干活了再恢复普通样式」）。
        #   ⚠ 传的是 `slot.state`（不是写死的 'done'）：失败的那一路落回 `idle`，
        #     界面照实显示成"待命"，不该留着"刚交活"的绿点。
        # [EN] ★ Report once at wrap-up too — the UI uses this to **remove the highlight and restore the normal
        # [EN] style**
        # [EN] (user's exact words: "restore the normal style once they stop working").
        # [EN] ⚠ What is passed is `slot.state` (not a hardcoded 'done'): the failed path falls back to `idle`,
        # [EN] and the UI truthfully shows "idle", rather than keeping the green dot for "just submitted work".
        slot.t0 = 0.0
        self._work_notify(key, slot.state)
        st = self._stats.setdefault(key, {'runs': 0, 'fails': 0})
        st['runs'] += 1
        if not note.ok:
            st['fails'] += 1
        # ★ **去 AI 味审计**（2026-10-07）：用户要求「所有工作人员产出任何内容
        #   之前，都做去 AI 味道审计处理」。放在这里是因为 `call` 是**唯一入口**
        #   （见它的 docstring）—— 挂在这一处，15 个职位一个都不会漏。
        #   零成本（词表比对），所以"每次都查"才做得起。
        # [EN] ★ **De-AI audit** (2026-10-07): the user requires "all staff, before producing any content,
        # [EN] must undergo de-AI-flavor audit processing". Placed here because `call` is **the only entry
        # [EN] point**
        # [EN] (see its docstring) — hung at this one spot, none of the 15 roles will be missed.
        # [EN] Zero cost (wordlist comparison), so "check every time" is affordable.
        self._deai_check(note)
        # ★★ `extra_section` 在这里合入正文（**必须在 `_deai_check` 之后**，
        #   理由见 `call()` 的 docstring）：接下来的落盘/播报/台账都会带上它。
        # [EN] ★★ `extra_section` is merged into the body here (**must be after `_deai_check`**, see the
        # [EN] docstring of `call()`): the disk-write / broadcast / ledger that follow all carry it.
        if extra_section and note.ok:
            try:
                _b = str(note.body or '').rstrip()
                note.body = (f'{_b}\n\n{extra_section}' if _b else extra_section)
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('合入附加段落失败（不影响推演）：%r', e)
        # 落盘 + 播报都走各自的小工具（它们各自吞异常，不影响推演）
        # [EN] Disk-write + broadcast each go through their own small utility (each swallows its own
        # [EN] exceptions, not affecting the simulation)
        self._save_note(note)
        # ★★ 2026-10-23：**先把房间定格，再播报**。
        #   界面收到"已交活"那一条时会立刻去读房间拿"这一步的执行结果"，
        #   所以 `finish` 必须排在 `_announce` **之前** —— 反过来的话，
        #   那一刻读到的是"还在跑"的快照，展开框会先空一下再填上。
        #   ⚠ 定格的内容是**整份 `note.body`**（不是截断版）：用户点开就是为了看全文，
        #     而这份内容本来就落在各自的 `.md` 里，界面再露一遍不增加任何风险。
        # [EN] ★★ 2026-10-23: **freeze the room first, then announce.**
        # [EN] The UI reads the room for "this step's result" the moment it receives
        # [EN] "handed in", so `finish` must come **before** `_announce` -- otherwise that
        # [EN] read gets a "still running" snapshot and the expander flashes empty.
        # [EN] ⚠ What is frozen is the **whole `note.body`** (not a truncated version): the
        # [EN] user opened it to read all of it, and this content already goes into its own
        # [EN] `.md`; showing it again in the UI adds no risk.
        try:
            from crew import live as LV
            LV.finish(key, body=str(getattr(note, 'body', '') or ''),
                      ok=bool(getattr(note, 'ok', True)),
                      secs=float((note.data or {}).get('用时') or 0.0),
                      why=str(getattr(note, 'why', '') or ''))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('定格实时房间失败（展开框会停在"还在跑"）：%r', e)
        self._announce(note)
        # ★ **思维链**（2026-10-07 第七轮）：把这一位"动手之前那几句盘算"取出来
        #   记一条日志（那份内容本来就在 `note.data` 里，随台账/JSON 一起落盘）。
        # [EN] ★ **Chain of thought** (2026-10-07 round seven): extract this one's "few lines of deliberation
        # [EN] before acting"
        # [EN] and log it (that content is already in `note.data`, and gets written to disk along with the
        # [EN] ledger/JSON).
        #
        # ⚠ 挂在这一处是因为 `call` 是**唯一入口**（与上面的 `_deai_check` 同源）：
        #   7 个装了思考骨架的职位一个都不会漏，而它们的产出**不上面向用户的窗口**
        #   （用户的中间栏白名单里没有"盘算"）—— 不落到日志里，作者事后就查不到
        #   "这一位当初是怎么想的"，那正是"为什么演出成这样"的第一手线索。
        #   拿不到盘算**不是故障**（模型没给 / 骨架没装 / 开关关着），静默跳过。
        # [EN] ⚠ It is hung here because `call` is **the only entry point** (same origin as `_deai_check`
        # [EN] above):
        # [EN] none of the 7 roles equipped with a thinking skeleton will be missed, and their output **does
        # [EN] not go to the user-facing window**
        # [EN] (the user's middle-column whitelist has no "deliberation") — if it is not written to the log,
        # [EN] the author cannot check afterward
        # [EN] "what this one was thinking at the time", and that is the first-hand clue to "why the
        # [EN] performance turned out this way".
        # [EN] Failure to obtain the deliberation **is not a fault** (model did not provide it / skeleton not
        # [EN] installed / switch off), skip silently.
        try:
            from crew import cognition as _COG
            _who = key
            try:
                _who = ROSTER.role(key).name
            except Exception:                                    # noqa: BLE001
                pass
            _COG.note_think(key, note.data, who=_who)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('取剧组思维链失败（不影响推演）：%r', e)
        return note

    async def audit(self, ctx: A.SetCtx, *, items: list[dict],
                    history: list[str] | None = None) -> A.CrewNote:
        """**上屏前的审读**（`script_doctor`）—— 每拍一次。

        它和 `call()` 有两处**故意不同**（写在这里免得以后有人"统一"掉）：

        | | `call()` | 本方法 |
        |---|---|---|
        | 中栏消息（`_announce`） | 发（工作状态那一行） | **不发** —— 它是闸门，每拍往中栏推一行"审读已交活"会把正文淹掉 |
        | 产出落盘（`_save_note`） | 写 `xxx.md` | **不写** —— 一天几百次调用会写几百个文件；它的产出落进**审读台账**与《剧本审读.md》（一天一份） |
        | 台账状态 / 面板高亮 | 有 | **照样有**（用户要的"谁在干活"必须包括它） |
        | 去 AI 审计 / 思维链日志 | 有 | **照样有** |

        其余一切（不许静默失败、`data['用时']`、`_stats`）与 `call()` 一致 ——
        两条路都从同一个地方取"这次出了什么活"。
        
                English:
        **Pre-screen review** (`script_doctor`) —— once per beat.
                It differs from `call()` in two **intentional ways** (written here so nobody "unifies" them later):
                | | `call()` | This method |
                |---|---|---|
                | Center-column message (`_announce`) | Sends (the working-status row) | **Doesn't send** —— it's a gate; pushing a row of "review submitted" to the center column every beat would drown out the main text |
                | Output persisted to disk (`_save_note`) | Writes `xxx.md` | **Doesn't write** —— hundreds of calls a day would write hundreds of files; its output goes into the **review ledger** and "Script Review.md" (one per day) |
                | Ledger status / panel highlight | Yes | **Still yes** (the user's "who is working" must include it) |
                | Goes through AI audit / chain-of-thought log | yes | **still yes** |
                Everything else (no silent failures, `data['时长']`, `_stats`) is consistent with `call()` ——
                Both paths take "what came out this time" from the same place.
        """
        member = A.member('script_doctor')
        key = 'script_doctor'
        slot = self._slots.setdefault(key, _Slot(key=key))
        slot.state = 'working'
        slot.t0 = time.monotonic()
        self._work_notify(key, 'working')
        # ★★★ 2026-10-21（用户点名「每个阶段都要给出正在做什么」）：
        #   在**出工那一刻**把"这一位在做什么"压进登记栈 —— 状态条每 0.5 秒读一次。
        #   这一句是收尾那几个职位能被看见的唯一原因：收尾整段只有一个
        #   `_stage('day_review')`，中间跑场记/宣发/审校/复盘全靠这里逐个替换。
        #   ⚠ 用 `push/pop` 而不是直接设：`call` 可能套在 `stage` 里，弹掉自己就回落给外层。
        # [EN] ★★★ 2026-10-21 (user: "every stage must say what it is doing"): the moment this role
        # [EN] starts working, push "what it is doing" onto the registry -- the status bar reads it
        # [EN] every 0.5 s. This single line is the only reason the wrap-up roles are visible: the
        # [EN] whole wrap-up is one `_stage('day_review')`, and continuity/publicity/polish/review
        # [EN] cycle through here one by one.
        # [EN] ⚠ `push/pop`, not a plain set: a `call` may sit inside a `stage`, and popping itself
        # [EN] falls back to the outer label.
        try:
            _role = getattr(member, 'role', None)
            _doing_tok = DOING.push(DOING.role_label(
                getattr(_role, 'name', '') or key, getattr(_role, 'duty', '') or ''))
        except Exception:                                    # noqa: BLE001
            _doing_tok = 0
        _t0 = time.monotonic()
        try:
            note = await member.run(ctx, items=list(items or []),
                                    history=list(history or []))
        finally:
            # ★ 2026-10-21：出场弹掉自己（原来这里是 `pass`）——
            #   逐拍审读一天要跑几百次，漏一次就在栈里留一条，
            #   状态条会一直显示"剧本审读中"，哪怕早就不在读了。
            # [EN] ★ 2026-10-21: pop on the way out (this used to be `pass`) -- per-beat review runs
            # [EN] hundreds of times a day, and one missed pop leaves an entry that makes the bar say
            # [EN] "reviewing the script" long after it stopped.
            DOING.pop(_doing_tok)
        try:
            note.data = dict(note.data or {})
            note.data.setdefault('用时', round(time.monotonic() - _t0, 2))
        except Exception:                                        # noqa: BLE001
            pass
        slot.note = note
        slot.state = 'done' if note.ok else 'idle'
        slot.day = int(getattr(ctx, 'day', 0) or 0)
        slot.t0 = 0.0
        self._work_notify(key, slot.state)
        st = self._stats.setdefault(key, {'runs': 0, 'fails': 0})
        st['runs'] += 1
        if not note.ok:
            st['fails'] += 1
        self._deai_check(note)
        try:
            from crew import cognition as _COG
            _COG.note_think(key, note.data, who=self.role_name(key))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('取剧组思维链失败（不影响推演）：%r', e)
        return note

    @staticmethod
    def role_name(key: str) -> str:
        try:
            return ROSTER.role(key).name
        except Exception:                                        # noqa: BLE001
            return str(key)

    def _deai_check(self, note: A.CrewNote) -> None:
        """过一遍去 AI 审计，把命中记进 `note.data` 并攒起来（给每日审计页）。

        ⚠ **不改写产出**：只记。改写剧组产出会把作者要的"原汁原味"改掉，
          而且命中不等于有错（见 `style/deai.py` 的口径）。
          唯一会真改的是**演员台词**里偶发的套话词，那在 `sim/loop` 那边做。
        
                English:
        Run through the de-AI audit, record hits into `note.data` and accumulate them (for the daily
        audit page).
                ⚠ **Does not rewrite output**: only records. Rewriting crew output would destroy the "authentic flavor" the author wants,
                  and a hit does not equal an error (see the standard in `style/deai.py`).
                  The only thing actually changed is the occasional boilerplate phrase in **actor lines**, which is done over in `sim/loop`.
        """
        if not CFG.b('DEAI'):
            return
        try:
            from style import deai
            text = f'{note.title}\n{note.body}'
            res = deai.audit_text(text, who=(note.role or ''))
            if res.hits:
                note.data = dict(note.data or {})
                note.data['去AI命中'] = len(res.hits)
                note.data['去AI硬禁'] = len(res.hard)
                self._deai_hits.extend(res.hits)
            self._deai_checked += 1
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧组产出去 AI 审计失败（不影响推演）：%r', e)

    def deai_hits(self) -> list:
        """本**天**攒下的去 AI 命中（`sim/loop` 落盘时取走并清空）。
                English:
        De-AI hits accumulated this **day** (taken and cleared when `sim/loop` writes to disk).
        """
        return list(self._deai_hits)

    def _line_begin(self, key: str) -> None:
        """让界面在中栏**起一条**这一位的消息（`call()` 专用，见 `_on_line`）。"""
        if self._on_line is None:
            return
        try:
            self._on_line(str(key))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧组消息起头失败（不影响推演）：%r', e)

    def _work_notify(self, key: str, state: str) -> None:
        """报一次「某职位出工状态变了」。**吞掉所有异常。**

        与 `_announce` / `_stage_push` 同一条纪律：播报失败绝不影响推演
        （表现最坏就是"界面上那行没亮"，而那是可以再刷出来的；
        为此把一次真实的出工弄挂掉才是真损失）。
        
                English:
        Report once that "a position's work status changed". **Swallow all exceptions.**
                Same discipline as `_announce` / `_stage_push`: a broadcast failure must never affect the simulation
                (the worst case is "that line on the UI didn't light up", and that can be refreshed;
                crashing a real piece of work over it would be the real loss).
        """
        if self._on_work is None:
            return
        try:
            self._on_work(str(key), str(state))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('出工状态播报失败（不影响推演）：%r', e)

    # ══════════════════════════════════════════════════════════════════
    #  阶段（只报阶段名与用时）
    # [EN] Stage (only reports stage name and elapsed time)
    # ══════════════════════════════════════════════════════════════════
    @contextlib.contextmanager
    def stage(self, key: str):
        """量一段流程的用时，把「阶段名 + 用时」报给界面。

        用户 2026-10-07：「把作者写小说 剧作家创作剧本 剧组排练 然后重新修改
        再排练 再修改等过程用**小的消息**（只显示阶段名和用时，不真实输出
        内部细节，但细节写入日志）」。

        ★ **它拿不到产出**：`yield` 不回传任何东西，这个上下文管理器也不可能
          带上产出内容 —— "只报状态"因此是**结构上**的保证，不是靠调用方自觉。
        ★ 异常也照样报（`finally`）：某段流程挂了，"卡在哪儿"这件事比什么都
          重要，静默不报才是最难查的。
        
                English:
        Measure the duration of a process, and report "stage name + duration" to the UI.
        """
        import time as _time
        t0 = _time.monotonic()
        ok = True
        # ⚠ 用 **push/pop 令牌**而不是"设一个变量"（2026-10-21）：阶段是**嵌套**的
        #   （「一天结束后讨论」里还要逐个跑场记/宣发/审校/复盘），
        #   变量会被内层盖掉、又被内层退出清空 ⇒ 状态条要么空、要么写着已经做完的事。
        #   栈永远显示最内层，内层退出自动回落到外层。
        # [EN] ⚠ **push/pop with a token**, not a variable (2026-10-21): stages **nest** (the
        # [EN] end-of-day discussion runs continuity/publicity/polish/review inside), so a variable
        # [EN] gets overwritten by the inner one and cleared on inner exit => the bar goes blank or
        # [EN] shows something already finished. A stack always shows the innermost and falls back.
        _tok = DOING.push(DOING.stage_label(key))
        try:
            yield
        except BaseException:
            ok = False
            raise
        finally:
            DOING.pop(_tok)
            dt = round(_time.monotonic() - t0, 2)
            _LOG.info('阶段「%s」用时 %.1fs%s', key, dt, '' if ok else '（失败）')
            if self._on_stage is not None:
                try:
                    self._on_stage(str(key), dt, ok)
                except Exception as e:                           # noqa: BLE001
                    _LOG.warning('阶段播报失败（不影响推演）：%r', e)

    def take_deai_hits(self) -> list:
        """取走并清空（"攒着 + 一天落一次盘"这一对的另一半）。
                English:
        Take away and clear (the other half of the "accumulate + flush once a day" pair).
        """
        out = list(self._deai_hits)
        self._deai_hits.clear()
        return out

    async def preproduction(self, ctx: A.SetCtx) -> dict[str, A.CrewNote]:
        """开拍前：美术 + 道具（**一条链**：美术定的调子递给道具师）。

        顺序有意 —— 名册里写着 `art.feeds == 'props'`，那就得**真的是这样**：
        道具师选东西要合美术定的画风与主色。两个都按天缓存（同一天重问没意义）。

        ⚠ 关掉的职位**不产生调用**；台账里那行显示"未启用"
          （**不是"没出活"**：那是两件事，界面要分得开）。
        
                English:
        Before shooting: art + props (**one chain**: the tone set by art is handed to the prop master).
                The order is intentional -- the roster says `art.feeds == 'props'`, so it must **really be that way**:
                The prop master's selections must match the art style and primary colors set by art. Both are cached daily (re-asking on the same day is pointless).
                ⚠ A disabled role **produces no calls**; that row in the ledger shows "not enabled"
                  (**not "produced nothing"**: those are two different things, and the UI must distinguish them).
        """
        out: dict[str, A.CrewNote] = {}
        art = None
        if CFG.b('CREW') and CFG.b('CREW_ART'):
            art = await self.art_note(ctx)
            out['art'] = art
        if CFG.b('CREW') and CFG.b('CREW_PROPS'):
            out['props'] = await self.props_note(ctx, brief=self._art_brief(art))
        # ★ 造型（2026-10-07 补）：与道具**并列**接在美术之后 ——
        #   道具管"场景里的物件"，造型管"人身上的东西"，两边都受美术的调子约束，
        #   谁也不该在谁之前（先后都说得通，所以并列，别编一条假依赖）。
        # [EN] ★ Role design (added 2026-10-07): parallel to props, attached after art --
        # [EN] Props manage "objects in the scene", role design manages "things on people"; both are
        # [EN] constrained by art's tone,
        # [EN] and neither should come before the other (either order works, so make them parallel; don't
        # [EN] invent a fake dependency).
        if CFG.b('CREW') and CFG.b('CREW_STYLIST'):
            note = await self.call('stylist', ctx, brief=self._art_brief(art))
            out['stylist'] = note
            # ★ 缓存下来：`image_prefix()` 要按天取它（否则出图提示词里没有造型，
            #   "定了穿什么"这件事对画面毫无影响 —— 2026-10-07 审计查出来的断链）。
            # [EN] ★ Cache it: `image_prefix()` must fetch it per day (otherwise the image prompt has no role
            # [EN] design,
            # [EN] and "decided what to wear" has zero effect on the image -- a broken link found in the 2026-10-07
            # [EN] audit).
            if note.ok:
                self._stylist[int(getattr(ctx, 'day', 0) or 0)] = note
        return out

    @staticmethod
    def stylist_brief(note: A.CrewNote | None) -> str:
        """把造型表压成给演员看的一小段（"我今天穿什么、带着什么"）。

        没有它，造型就只是一份落盘的 MD —— 演员照旧不知道自己长什么样，
        那这个职位等于没接上（本项目对"假按钮"零容忍）。
        
                English:
        Compress the styling table into a short segment for the actor ("what I'm wearing today, what I'm
        carrying").
                Without it, styling is just an MD file on disk -- the actor still doesn't know what they look like,
                which means this role isn't actually wired up (this project has zero tolerance for "fake buttons").
        """
        if note is None or not note.ok:
            return ''
        rows = (note.data or {}).get('造型') or []
        out: list[str] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            nm = str(r.get('人名') or '').strip()
            if not nm:
                continue
            bits = [str(r.get(k) or '').strip() for k in ('穿着', '随身物', '仪态')]
            bits = [b for b in bits if b]
            if bits:
                out.append(f'- {nm}：' + '｜'.join(bits))
        if not out:
            return ''
        return '【你身上（造型定的，别改）】\n' + '\n'.join(out)

    @staticmethod
    def sound_brief(note: A.CrewNote | None) -> str:
        """把声音设计压成一句可用的环境音（给场景的环境句用）。
                English:
        Compress the sound design into one usable ambient sound (for the scene's ambient line).
        """
        if note is None or not note.ok:
            return ''
        d = note.data or {}
        bits: list[str] = []
        if d.get('底噪'):
            bits.append(str(d['底噪']))
        ev = [str(x) for x in (d.get('事件声') or []) if str(x).strip()]
        if ev:
            bits.append('；'.join(ev[:2]))
        if d.get('静默'):
            bits.append(str(d['静默']))
        return '；'.join(bits)

    async def review(self, ctx: A.SetCtx, *, lines: list[str] | None = None,
                     script: str = '', extra_section: str = '') -> A.CrewNote:
        """**复盘**（收工）：今天的剧情总结 + 问题 + 修改意见。

        见 `crew/agents.Reviewer` —— 它只报不改，`需要重演` 那面旗由调用方定夺。

        `extra_section`：要**跟着这份总结一起上屏/落盘**的附加段落
        （眼下只有一处用途：语言审校那几条"AI 味重的原句 + 怎么改"）——
        见 `call()` 的 docstring（那里写了为什么不在事后改文件）。
        
                English:
        **Retrospective** (wrap-up): today's plot summary + issues + revision notes.
                See `crew/agents.Reviewer` -- it only reports, doesn't fix; the `needs_reshoot` flag is
                decided by the caller.
                `extra_section`: an extra block to **go on screen / to disk along with this summary**
                (currently used in exactly one place: the language review's "AI-flavoured original
                sentences + how to fix") -- see the docstring of `call()` (it explains why not patching
                the file afterwards).
        """
        return await self.call('reviewer', ctx, lines=lines, script=script,
                               extra_section=extra_section)

    async def rehearse(self, ctx: A.SetCtx, *, story: str = '',
                       beats: list[dict] | None = None,
                       roles: dict | None = None) -> A.CrewNote:
        """**排练**（剧本定稿后、开演前）：把这一天空走一遍。

        ★ 产出**不上中栏**：它只落 `排练记录.md` 与日志。
          中栏那一条是 `sim/loop` 的阶段小消息（「剧组排练 · 3.2s」），
          而那个上下文管理器**拿不到这里的任何一行字**（见 `Studio.stage`）。
        
                English:
        **Rehearsal** (after the script is finalized, before the show): walk through this day once.
                ★ Output does **not** go to the center column: it only lands in `排练记录.md` and the log.
                  The center-column entry is `sim/loop`'s stage message ("剧组排练 · 3.2s"),
                  and that context manager **cannot get a single line of text from here** (see `Studio.stage`).
        """
        return await self.call('rehearsal', ctx, story=story, beats=beats,
                               roles=roles)

    async def day_novel(self, ctx: A.SetCtx, *, raw: str = '') -> A.CrewNote:
        """**整理当天这一章**（收工）：把今天实际发生的写成小说形式。

        用户 2026-10-07：「每天总结你看下包含当天故事整理吗(整理成小说形式)」。

        ⚠ 它复用**小说作家**这个职位（`Novelist.work(transcribe=…)`）——
          不另开一个人，因为"写计划"与"写成实际"本来就是同一行手艺
          （见 `Novelist.work` 的说明）。
        ⚠ 它**不写自己的落盘文件**（`ARTIFACT['novelist'] is None`）：
          产物由 `sim/loop._day_novel` 追加进 `当天故事.md`（按天累积）
          并同时进「今日总结.md」——两个写入方写同一个文件迟早会对不上。
        
                English:
        **Organize today's chapter** (wrap-up): write what actually happened today in novel form.
                ⚠ It reuses the **novelist** role (`Novelist.work(transcribe=…)`) --
                  no separate person, because "writing the plan" and "writing what actually happened" are fundamentally the same craft
                  (see the note on `Novelist.work`).
                ⚠ It **does not write its own output file** (`ARTIFACT['novelist'] is None`):
                  the output is appended by `sim/loop._day_novel` into `当天故事.md` (accumulated by day)
                  and also into "今日总结.md" -- two writers writing the same file will eventually disagree.
        """
        return await self.call('novelist', ctx, transcribe=raw)

    async def sound_note(self, ctx: A.SetCtx,
                         *, beats: list[dict] | None = None) -> A.CrewNote:
        """**声音**（开拍前）：这一场听得见什么。

        ⚠ 这个方法原来**没有任何调用点**（2026-10-07 审计查出来）：
        `声音` 职位在名册上、`Sound` 成员写好了、`CREW_SOUND` 默认开着、
        `声音设计.md` 在落盘表里 —— 而它一天都没出过工，台账里永远「待命 0/0」。
        现在由 `sim/loop._sound()` 在**当天剧本写完之后**调（那时才有分拍）。

        按天缓存：同一天重复问没意义（而且换个调用点就白花一次）。
        
                English:
                Now called by `sim/loop._sound()` **after the day's script is written** (only then are there beats).
                Cache by day: repeating the same day's query is pointless (and switching call sites wastes a call).
        """
        day = int(getattr(ctx, 'day', 0) or 0)
        old = self._sound.get(day)
        if old is not None and old.ok and beats is None:
            return old
        note = await self.call('sound', ctx, beats=beats)
        if note.ok and beats:
            self._sound[day] = note
        return note

    async def polish(self, ctx: A.SetCtx, *, story: str = '') -> A.CrewNote:
        """**语言审校**（收到样章之后）：哪几句 AI 味重、该怎么改。
                English:
        **Language review** (after receiving the sample chapter): which sentences feel AI-ish, and how
        to fix them.
        """
        return await self.call('polisher', ctx, story=story)

    @staticmethod
    def polish_has_findings(note: A.CrewNote | None) -> bool:
        """这份语言审校**查出东西了没有**（没出活 / 零命中都算没有）。

        为什么不用 `note.ok` 判：审校"读下来没有问题"时 `ok=True`，
        而它的 `data` 里没有 `问题数` —— 拿 `ok` 当判据会把"今天很干净"
        也当成"有问题"并进总结（总结里就多一节"0 处"，纯噪音）。
        [EN] Does this language review **have findings** (not producing anything / zero hits both count as
        [EN] no).
        [EN] Why not judge by `note.ok`: when the review finds nothing, `ok=True` and its `data` has no
        [EN] `问题数` -- using `ok` would treat "today was clean" as "has problems" and merge it into the
        [EN] summary (adding a "0 spots" section, pure noise).
        """
        if note is None or not note.ok:
            return False
        d = note.data or {}
        return bool(int(d.get('问题数') or 0) or int(d.get('词表命中') or 0))

    @classmethod
    def polish_section(cls, note: A.CrewNote | None) -> str:
        """把语言审校压成一段**能并进今日总结**的 Markdown（没查出东西就给空串）。

        ★ 2026-10-12 用户要求（原话：「每天最后的语言审校**为何都是放到一个 md**，
          而不是输出出来」）——他选了"并进今日总结"。见 `wrap()` 里那段说明。
        ⚠ 保留原句与改法（`note.body` 已经是那个形状）——**不要在这里改写成摘要**：
          "原句「…」"那半截是要作者拿去在稿子里搜的，改写之后他就搜不到了。
        
                English:
        Compress the language review into a block of Markdown **that can be merged into today's summary**
        (empty string when there are no findings).
                ★ User request 2026-10-12 ("why is the day's final language review **always put into an
                  md** instead of being output") -- they chose "merge into today's summary". See the note in
                  `wrap()`.
                ⚠ Keep the original sentences and the fixes (`note.body` is already in that shape) --
                  **do not rewrite it into a summary here**: that "original sentence「...」" half is what
                  the author searches for in the draft, and rewriting it makes it unfindable.
        """
        if not cls.polish_has_findings(note):
            return ''
        body = str(note.body or '').strip()
        if not body:
            return ''
        return (f'---\n\n### 语言审校 · {note.title or "AI 味"}\n\n'
                f'> 收工时语言审校读当天样章点出来的，'
                f'全文另存 `{FILE_POLISH}`。\n\n{body}')

    def polish_brief(self, day: int) -> str:
        """读**上一天**语言审校留下的那几条，压成给**剧作者**的一小段（读不到给空串）。

        ★ 2026-10-12 用户要求"把下游接上"：名册里 `polisher.feeds == 'screenwriter'`
          （文档也写着下游是「剧作者（下一天的剧本）」），而**代码里从来没人读回它**
          —— grep 全仓，那份 md 只有"写"没有"读"。现在真的接上：
          下一天写剧本时，这些"AI 味重的原句 + 怎么改"会作为上游材料递过去。

        ⚠ 认的是文件里那行 `> 第 N 天`，且**必须正好是 `day - 1`**：
          这份 md 每天**覆盖写**，所以：
            · 同一天重写（验算不过 / 排演出问题）时读到的是**上一天**的 —— 对；
            · `DAY_REVIEW_REPLAY` 回档重演当天时，文件已被今天自己覆盖
              （头写着今天）⇒ **读不到就跳过**，不会把"今天的意见"当成"昨天的"喂回去。
        ⚠ 读不到（没有这份文件 / 关着剧组）就是空串，**不编**。
        
                English:
        Read the few items the **previous day's** language review left behind and compress them into a
        short block for the **screenwriter** (empty string when unreadable).
                ★ User request 2026-10-12: "wire up the downstream". The roster says
                  `polisher.feeds == 'screenwriter'` (and the docs say the downstream is "the screenwriter
                  (next day's script)"), yet **nothing in the code ever read it back** -- grep the whole
                  repo and that md is only ever written, never read. Now it really is wired: when writing
                  the next day's script, these "AI-flavoured original sentences + how to fix" are handed
                  over as upstream material.
                ⚠ It recognises the `> 第 N 天` line and it **must be exactly `day - 1`**:
                  this md is **overwrite-written** every day, so:
                  · when rewriting the same day (verification failed / rehearsal found a problem) it reads
                    the **previous** day's -- correct;
                  · when `DAY_REVIEW_REPLAY` rolls the day back and replays it, the file has already been
                    overwritten by today itself (the header says today) ⇒ **skip when unreadable**, so
                    "today's opinions" are never fed back as "yesterday's".
                ⚠ Unreadable (no such file / crew off) means empty string, **no making it up**.
        """
        try:
            if self.runfolder is None or not CFG.b('CREW'):
                return ''
            p = Path(self.runfolder.root) / FILE_POLISH
            if not p.is_file():
                return ''
            text = p.read_text(encoding='utf-8')
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('读「%s」失败（下一天剧作者少了这份参考）：%r', FILE_POLISH, e)
            return ''
        m = re.search(r'^>\s*第\s*(\d+)\s*天', text, re.M)
        if not m or int(m.group(1)) != int(day) - 1:
            return ''
        # 去掉标题那两行（`# 语言审校` + `> 第 N 天`）—— 那是**这份文件**的
        # 书写格式，递给剧作者时不需要（他要知道的是"点出了哪几句"）。
        # [EN] Drop the two heading lines (`# 语言审校` + `> 第 N 天`) -- those are **this file's** writing
        # [EN] format and are not needed when handing it to the screenwriter (what he needs to know is
        # [EN] "which sentences were called out").
        body = '\n'.join(ln for ln in text.splitlines()
                         if not ln.startswith('# ') and not ln.startswith('> ')).strip()
        if not body:
            return ''
        return (f'【昨天语言审校点出的问题 —— 今天写的时候避开】\n'
                f'{body}\n'
                f'（这几句是上一稿里"读起来像机器写的"的地方；'
                f'今天别再用同样的写法。）')

    @staticmethod
    def _art_brief(art: A.CrewNote | None) -> str:
        """把美术指导压成给下游（道具师）看的一小段。没拿到就是空串。
                English:
        Compress the art direction into a short passage for downstream (props artist). Empty string if
        not obtained.
        """
        if art is None or not art.ok:
            return ''
        d = art.data or {}
        bits = [str(d.get('画风') or '').strip()]
        cols = [f"{c.get('色')}（{c.get('用途')}）"
                for c in (d.get('主色') or []) if isinstance(c, dict)]
        if cols:
            bits.append('主色：' + '、'.join(cols))
        if d.get('忌'):
            bits.append('忌：' + '、'.join(str(x) for x in d['忌']))
        return '\n'.join(b for b in bits if b)

    @staticmethod
    def _props_brief(note: A.CrewNote | None) -> str:
        """把道具单压成给下游（场记）看的一小段。没拿到就是空串。
                English:
        Compress the prop list into a short passage for downstream (continuity). Empty string if not
        obtained.
        """
        if note is None or not note.ok:
            return ''
        d = note.data or {}
        names = [str(i.get('名称') or '') for i in (d.get('道具') or [])
                 if isinstance(i, dict)]
        out = []
        if names:
            out.append('这一场的东西：' + '、'.join(n for n in names if n))
        if d.get('关键'):
            out.append('要反复出现的：' + '、'.join(str(x) for x in d['关键']))
        if d.get('基调'):
            out.append(f"基调：{d['基调']}")
        return '\n'.join(out)

    async def art_note(self, ctx: A.SetCtx) -> A.CrewNote:
        """这一部的美术指导（**一次定、全剧用**）。

        为什么不做成每天重算：美术指导要是天天变，出图就又不一致了 ——
        它解决的问题正是"同一部戏前后的画面不是一个样"。
        
                English:
        This installment's art direction (**decided once, used for the whole show**).
                Why not recompute daily: if the art direction changed daily, generated images would be inconsistent again -
                the problem it solves is precisely "the same show looks different before and after".
        """
        if self._art is not None and self._art.ok:
            return self._art
        note = await self.call('art', ctx)
        if note.ok:
            self._art = note
        return note

    async def day_map_note(self, ctx: A.SetCtx, *, here: str = '',
                           places: list[str] | None = None,
                           layers: list | None = None) -> A.CrewNote:
        """**当天这张地图**（按天缓存）—— 由美术根据今天的剧情画。

        用户 2026-10-07：「请把绘制地图改到**导演写完当前的小说之后**
        有剧组**美术**根据**当天剧情涉及到的地点**进行绘制」。

        ★ 时序是要求的一部分：**先有当天的剧本（分拍里有地点），才有当天的图**。
          所以这个方法的唯一调用点是 `sim/loop._compose_day()`，紧跟在
          `DAYPLAN.compose()` 之后 —— 不是开卷时、也不是装配时。

        ★ 当天的**分拍**走 `ctx.beats`（`_crew_ctx(beats=…)` 装进来的）——
          不另开一个形参：剧组每个职位都从 `ctx` 取料（`SetCtx` 的设计就是
          "要什么自己取"），多一个入口就多一处会漏装的地方。

        ★★ `layers`（2026-10-08 加）＝ **开卷时定下来的三级底图里，今天该用的那几层**
          （`world.atlas.Atlas.layers_for()` 算的：只在一处 → 室内或局部；跨了地方 → 整体）。
          有了它，美术不再"凭空摆位"，而是**在既定的空间事实里取景 + 补细节**。
          空列表 = 这本书没生成过底图 → 退回从前的行为（照常能画，只是位置每天重编）。

        按天缓存：同一天重复进界面不该重问一次模型（一张图一天一张）。
        
                English:
        **Today's map** (cached by day) - drawn by art based on today's plot.
                User 2026-10-07: "Please change map drawing to **after the director finishes writing the current novel**,
                with the crew's **art** drawing based on **locations involved in today's plot**.
                ★ The ordering is part of the requirement: **first the day's script (beats contain locations), then the day's map**.
                  So the sole call site of this method is `sim/loop._compose_day()`, immediately after
                  `DAYPLAN.compose()` - not at open-book time, nor at assembly time.
                ★ The day's **beats** come via `ctx.beats` (injected by `_crew_ctx(beats=…)`) -
                  don't add another parameter: every crew position pulls material from `ctx` (the `SetCtx` design is
                  "get what you need yourself"), one more entry point is one more place that can forget to inject.
                ★★ `layers` (added 2026-10-08) = **among the three-level base map decided at open-book time, the layers to use today**
                  (computed by `world.atlas.Atlas.layers_for()`: only in one place → indoor or local; spans places → whole).
                  With it, art no longer "places things out of thin air", but **frames within established spatial facts + fills in details**.
                  Empty list = this book never generated a base map → fall back to previous behavior (still draws, just re-compiles positions daily).
                Cache by day: re-entering the UI on the same day shouldn't re-query the model (one image per day).
        """
        day = int(getattr(ctx, 'day', 0) or 0)
        old = self._day_maps.get(day)
        if old is not None and old.ok:
            return old
        note = await self.call('art', ctx, day_map=True, here=here,
                               places=list(places or []),
                               layers=list(layers or []))
        if note.ok:
            self._day_maps[day] = note
        return note

    async def props_note(self, ctx: A.SetCtx, *, beats: list[dict] | None = None,
                         refresh: bool = False, brief: str = '') -> A.CrewNote:
        """这一天这一场的道具单（按天缓存）。

        `brief` = 上游（美术）给的材料。⚠ **带 brief 的调用不写缓存**：
        缓存住的那份是"没有上游材料时定的单子"，两者的输入不同，
        混在一起会让"美术明明定了调子、道具却像没看见"。
        
                English:
        This day's prop list for this scene (cached by day).
                `brief` = material given by upstream (art). ⚠ **Calls with brief are not cached**:
                the cached copy is "the list decided when there was no upstream material"; the two have different inputs,
                mixing them would make it look like "art clearly set the tone, but props seem to have ignored it".
        """
        day = int(getattr(ctx, 'day', 0) or 0)
        old = self._props.get(day)
        if old is not None and old.ok and not refresh and beats is None and not brief:
            return old
        note = await self.call('props', ctx, beats=beats, brief=brief)
        if note.ok and not brief:
            self._props[day] = note
        elif note.ok:
            self._props[day] = note      # 有上游材料的这份更好，照样收下
            # [EN] The one with upstream material is better; accept it anyway
        return note

    async def cast_extra(self, ctx: A.SetCtx) -> dict | None:
        """**群众演员投人**：门外此刻该走进来的是谁、他要什么。

        接在 `world/crowd` 的**闸门之后**（上限 / 当日预算由调用方先判）：
        AI 不该绕开预算。这里只负责"投成谁"这一件事，
        `world/crowd.new_extra` 那套规则池留在 `ExtraCasting.cast` 里当兜底。

        返回 `{'称呼','诉求','标志'}` 或 `None`（+ `ok` 由调用方看）。
        
                English:
        **Extra casting**: who should walk in from outside right now, and what he wants.
                Attached **after the gate** of `world/crowd` (cap / daily budget are judged by the caller first):
                AI shouldn't bypass the budget. This only handles "cast as whom",
                the rule pool in `world/crowd.new_extra` stays in `ExtraCasting.cast` as fallback.
                Returns `{'title','demand','mark'}` or `None` (+ `ok` checked by caller).
        """
        try:
            from world import crowd
            kind = crowd.scene_kind(str(getattr(ctx.world, 'scene', '') or ''))
        except Exception:                                        # noqa: BLE001
            kind = ''
        try:
            m = A.member('extra')
            got = await m.cast(ctx, kind_hint=kind)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('群演投人失败（走规则兜底）：%r', e)
            return None
        self._slots.setdefault('extra', _Slot(key='extra')).state = 'done'
        return got

    def mark_onduty(self) -> None:
        """开拍后把三位**常驻岗**（导演 / 演员 / 群众演员）标成「在岗」。

        这三者继承 `OnDuty`，每拍直接 `on_tick()`，**不经 `Studio.call`**，
        所以它们整天的出工在台账里**没有 `working`/`done` 的痕迹**
        （只有收工时 `report_onduty` 才补 `done`）。
        结果就是：推演进行中，界面那三行永远是「待命」，而他们其实一整天都在干活
        —— 这正是 `report_onduty` 那条注释自己承认的"界面说假话"。

        这里在**开拍那一刻**就把它们标成 `onduty`（在岗）：既不是"正在出工"的
        高亮（它们并不经 `call`、没有 `t0`/秒数可显示），也不是"待命"
        （明明已经在场），而是第三种状态：常驻、在场、随时在干。
        收工时 `report_onduty` 仍会把它们走到 `done`（已交活），
        所以 `onduty` 只在"开拍 → 收工"这段区间出现。

        ⚠ 只在**不是 `off`** 时标（`off` = 被设置关掉的，不能强行改成在岗）；
          其它状态（`idle` 第一天 · `done` 第二天起）一律覆盖成 `onduty`
          —— 因为开拍即意味着这一班人重新就位。
        ⚠ 不产 LLM 调用、不抛异常（设槽位 + 播报，播报失败由 `_work_notify` 吞掉）。

                English:
        At shoot-open, mark the three **on-duty residents** (director / actor / extra) as "onduty".
                These three inherit `OnDuty` and call `on_tick()` directly every beat, **not through
                `Studio.call`**,
                so their all-day work leaves **no `working`/`done` trace** in the ledger
                (only `report_onduty` at wrap adds `done`).
                The result: during the simulation, those three lines in the UI always say "standby", while
                they actually work all day -- exactly the "UI lying" that `report_onduty`'s comment admits.
                Here, **at the moment shooting opens**, we mark them `onduty`: not the "working" highlight (they
                don't go through `call`, so no `t0`/seconds to show), nor "standby" (they're clearly on the floor),
                but a third state: resident, present, always working. `report_onduty` at wrap still walks them to
                `done`,
                so `onduty` only appears in the "open → wrap" window.
                ⚠ Only mark when **not `off`** (`off` = turned off, can't force to onduty); other states
                (`idle` day one · `done` from day two) are all overwritten to `onduty` -- because shoot-open means
                this crew is back on duty.
                ⚠ Produces no LLM calls and raises no exceptions (set slot + broadcast; broadcast failure is
                swallowed by `_work_notify`).
        """
        for key in ('director', 'actor', 'extra'):
            s = self._slots.get(key)
            if s is None or s.state == 'off':
                continue
            s.state = 'onduty'
            s.t0 = 0.0
            self._work_notify(key, 'onduty')

    async def report_onduty(self, ctx: A.SetCtx) -> list[A.CrewNote]:
        """让**已经在位的三个职位**报一下此刻在干什么（导演 / 演员 / 群众演员）。

        这一步**不产生任何 LLM 调用**（`OnDuty` 只是转述），但要每天都跑一次 ——
        不然界面上那三行永远是「待命」，而他们其实一整天都在干活
        （演员每拍决策、群众演员每拍进出、导演每拍判断）。
        **界面显示"待命"和事实不符，就是界面在说假话**
        （与本项目一贯的"不许假装"是同一条）。
        
                English:
        Have the **three positions already on duty** report what they're doing right now (director /
        actor / extra).
                This step **produces no LLM calls** (`OnDuty` only relays), but it must run once per day -
                otherwise those three lines in the UI will always say "standby", while they actually work all day
                (actor decides every beat, extra enters/exits every beat, director judges every beat).
                **The UI showing "standby" that doesn't match reality means the UI is lying**
                (the same rule as this project's long-standing "no pretending").
        """
        out: list[A.CrewNote] = []
        for key in ('director', 'actor', 'extra'):
            try:
                out.append(await self.call(key, ctx))
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('剧组状态上报失败（%s）：%r', key, e)
        return out

    async def wrap(self, ctx: A.SetCtx, *, lines: list[str] | None = None,
                   story: str = '') -> list[A.CrewNote]:
        """收工：场记连戏检查 + 宣发一句话 + **在位的三个职位报状态**。

        顺序有意：
          · **先场记后宣发** —— 宣发要写的那句话应当建立在"这一场是清楚的"之上；
            连戏有问题时宣发照写（它不负责修），但场记的提请先落到台账里。
          · **连戏检查带上道具单**（名册里 `props.feeds == 'continuity'`）——
            "这一场该有的东西"是查物件的依据，不给它就只能凭印象。
          · 最后 `report_onduty`：导演/演员/群众演员**不产生 LLM 调用**，
            只是把"他们此刻在干什么"记上台账 —— 不记的话界面上那三行
            永远显示"待命"，而他们一整天都在干活（界面就在说假话）。
        
                English:
        Wrap-up: continuity check + one-line promo + **the three on-duty positions report status**.
                The order is intentional:
                  · **continuity before promo** - the line promo writes should be built on "this scene is clear";
                    when continuity has issues promo still writes (it's not responsible for fixing), but continuity's note lands in the ledger first.
                  · **continuity check includes the prop list** (in the roster `props.feeds == 'continuity'`) -
                    "what this scene should have" is the basis for checking objects; without it you can only go by impression.
                  · Finally `report_onduty`: director/actor/extra **produce no LLM calls**,
                    only record "what they're doing right now" into the ledger - without recording, those three lines in the UI
                    will forever show "standby", while they work all day (the UI is lying).
        """
        out: list[A.CrewNote] = []
        if CFG.b('CREW') and CFG.b('CREW_CONTINUITY'):
            out.append(await self.call(
                'continuity', ctx, lines=lines,
                brief=self._props_brief(self._props.get(
                    int(getattr(ctx, 'day', 0) or 0)))))
        if CFG.b('CREW') and CFG.b('CREW_PUBLICITY'):
            out.append(await self.call('publicity', ctx, lines=lines))
        # ★★ **语言审校**（2026-10-07 审计补上）：读当天样章，点名哪几句 AI 味重。
        # [EN] ★★ **Language polish** (added in the 2026-10-07 audit): read the day's sample chapter, call out
        # [EN] which sentences are heavily AI-flavored.
        #
        # ⚠ 它原来**根本没有调用点** —— `Studio.polish()` 写好了、职位在名册上、
        #   开关 `CREW_POLISH` 默认开着、界面上还写着它的职责，而台账里它
        #   天天「待命 0/0」、`语言审校.md` 从来不存在。
        #   这正是本项目零容忍的"假按钮"，而且藏得很深：名册/成员/开关/落盘表
        #   四处都齐，唯独少了**那一行调用**。
        # [EN] ⚠ It originally had **no call site at all** -- `Studio.polish()` was written, the role was on
        # [EN] the roster,
        # [EN] the switch `CREW_POLISH` was on by default, the UI even described its duties, yet in the ledger
        # [EN] it
        # [EN] sat at "standby 0/0" every day, and `语言审校.md` never existed.
        # [EN] This is exactly the "fake button" this project has zero tolerance for, and it was hidden deep:
        # [EN] roster/members/switch/persistence table,
        # [EN] all four were in place, only **that one call line** was missing.
        #
        # 位置有意排在**复盘之前**：复盘读的是"这一天成不成立"，
        #   而语言审校给的是"这几句怎么改" —— 具体的话先落到纸上，
        #   复盘再谈全局（反过来的话，复盘的意见会把这几句盖过去）。
        # 材料取自 `ctx.story`（剧作者之前写的那份样章）；散文模式下没有样章，
        #   就退回**当天上屏的叙事行**（`lines`）—— 总之不能空手。
        # [EN] Positioned intentionally **before the review**: the review reads "did this day hold together",
        # [EN] while language polish gives "how should these sentences be changed" -- concrete words hit paper
        # [EN] first,
        # [EN] then the review discusses the big picture (the other way around, the review's opinions would
        # [EN] drown out these sentences).
        # [EN] Material comes from `ctx.story` (the sample chapter the screenwriter wrote earlier); in prose
        # [EN] mode there is no sample chapter,
        # [EN] so it falls back to **the day's on-screen narrative lines** (`lines`) -- in short, it must not
        # [EN] go in empty-handed.
        pol: A.CrewNote | None = None
        if CFG.b('CREW') and CFG.b('CREW_POLISH'):
            _text = str(getattr(ctx, 'story', '') or '').strip()
            if not _text:
                _text = '\n'.join(str(x) for x in (lines or []) if str(x).strip())
            pol = await self.call('polisher', ctx, story=_text)
            out.append(pol)
        # ★ **复盘**（2026-10-07 补）：用户点名要的「今日总结」。
        #   顺序放在**最后**：它要读的是"这一天完整的样子"——
        #   场记的连戏提请、宣发的落点都该算进它的材料里（虽然它读的是正文）。
        #   ⚠ 它排在这里还有一层：`reviewer` 的 `需要重演` 会回到 `sim/loop`
        #     去决定要不要回档，那时**别的产出都已经记完了**，不会被回档牵连。
        # [EN] ★ **Review** (added 2026-10-07): the "today's summary" the user explicitly asked for.
        # [EN] Ordered **last**: what it reads is "the complete shape of this day" --
        # [EN] the continuity clerk's continuity requests, the publicity's placements should all count as its
        # [EN] material (even though it reads the main text).
        # [EN] ⚠ There is another layer to it being placed here: `reviewer`'s `需要重演` returns to `sim/loop`
        # [EN] to decide whether to roll back; by then **all other outputs are already recorded**, so they
        # [EN] won't be dragged down by the rollback.
        if CFG.b('CREW') and CFG.b('CREW_REVIEW'):
            # ★★ **语言审校并进今日总结**（2026-10-12 用户要求）。
            #   用户问：「每天最后的语言审校**为何都是放到一个 md**，而不是输出出来」——
            #   查下来：正文只在 `语言审校.md` 里，中栏只有一句"细节在「语言审校.md」"，
            #   而全软件只有**复盘**一份是以正文上屏的。用户选了"并进今日总结"。
            #   所以把它作为**附加段落**交给复盘那一份（走 `extra_section`）：
            #   于是它同时进 今日总结.md / 中栏那条 SUMMARY / 台账 / 日志 —— 四处一次到位。
            #   ⚠ **语言审校自己的那份 md 照旧写**（一句话都没少），这里只是多一个出口。
            #   ⚠ 没查出问题（`pol.ok` 且零命中）时不并 —— 空段只会让总结变长。
            # [EN] ★★ **Merge the language review into today's summary** (user request 2026-10-12).
            # [EN] The user asked: "why is the day's final language review **always put into an md**
            # [EN] instead of being output?"
            # [EN] What we found: the body only lived in `语言审校.md`, the middle column only said
            # [EN] "details in 语言审校.md",
            # [EN] and in the whole app only **the retrospective** reaches the screen as content. The user
            # [EN] chose "merge into today's summary".
            # [EN] So it is handed to the retrospective's note as an **extra section** (via
            # [EN] `extra_section`): that gets it into 今日总结.md / the middle column's SUMMARY / the
            # [EN] ledger / the log all at once.
            # [EN] ⚠ The language review's own md is **still written** (not one word less); this just adds
            # [EN] another outlet.
            # [EN] ⚠ When nothing was found (`pol.ok` with zero hits) it is not merged -- an empty section
            # [EN] would only make the summary longer.
            out.append(await self.review(ctx, lines=lines,
                                         extra_section=self.polish_section(pol)))
        # ★★ **自建职位**（2026-10-11）：作者在「剧组 Agents」里新建的职位，
        #   每天收工时出工一次（出工时机固定 `day`，见 `crew/catalog.CUSTOM_WHEN`）。
        # [EN] ★★ **Custom roles** (2026-10-11): roles the author creates in "剧组 Agents",
        # [EN] they produce once each day at wrap-up (fixed wrap-up timing `day`, see
        # [EN] `crew/catalog.CUSTOM_WHEN`).
        #
        #   ⚠ 放在**复盘之后**：它们读的是"这一天完整的样子"，也包括复盘的意见；
        #     排在复盘之前的话，作者自建的"审稿人"就看不到复盘说了什么。
        #   ⚠ 判"哪些是自建"看的是 `A.MEMBERS`（出厂实现表）——
        #     拿名册比会把"名册有、实现也有"的出厂职位也算进来，于是
        #     十几个职位在收工后再跑一遍（一天白烧十几次调用）。
        # [EN] ⚠ Placed **after the review**: what they read is "the complete shape of this day", including the
        # [EN] review's opinions;
        # [EN] if placed before the review, an author-created "reviewer" would not see what the review said.
        # [EN] ⚠ Whether something is "custom" is judged by `A.MEMBERS` (the factory implementation table) --
        # [EN] comparing against the roster would also count factory roles that are "on the roster and
        # [EN] implemented", so
        # [EN] a dozen roles would run again after wrap-up (burning a dozen-plus calls a day for nothing).
        if CFG.b('CREW'):
            for _r in ROSTER.roles():
                if _r.key in A.MEMBERS:
                    continue
                try:
                    out.append(await self.call(_r.key, ctx, lines=lines))
                except Exception as e:                           # noqa: BLE001
                    _LOG.warning('自建职位「%s」出工失败（不影响推演）：%r',
                                 _r.name, e)
        if CFG.b('CREW'):
            out += await self.report_onduty(ctx)
        return out

    async def research(self, ctx: A.SetCtx, *, story: str = '') -> A.CrewNote:
        """资料员考据（对当天样章）。
                English:
        Archivist research (on the day's sample chapter).
        """
        return await self.call('researcher', ctx, story=story)

    async def setting_room(self, ctx: A.SetCtx, *, story: str = '',
                           beats: list[dict] | None = None) -> A.CrewNote:
        """**编剧室会审**：导演 · 小说作家 · 剧作者 补局部设定。

        用户 2026-10-07：「有些时候需要导演 和 小说作者 以及 剧作家 讨论生成
        一些新的设定 这些都要进行推演 以便方便故事推进 同时不能够影响总体设定」

        调用点在 `sim/loop._compose_day()`，**排在写样章之前** —— 先补设定，
        再动笔；反过来的话，新设定对这一天就没有影响了（那正是用户说的
        "要进行推演"落空的样子）。

        ⚠ 它的产出**不落进 `ARTIFACT`**（`临时设定.md` 由
          `world.layers.save_local` 单独维护，见那张表里的注释）——
          两个写入方写同一个文件，迟早会出现"文件里写的和系统里用的不一样"。
        
                English:
        **Writers' room review**: director · novelist · playwright supplement local settings.
                User 2026-10-07: "Sometimes the director and the novelist and the playwright need to discuss and generate
                some new settings; these all need to be simulated to facilitate story progression while not affecting the overall settings."
                The call site is in `sim/loop._compose_day()`, **placed before writing sample chapters** —— settings are filled in first,
                then writing begins; if reversed, the new settings would have no effect on that day (which is exactly what the user meant by
                "simulation must be performed" falling flat).
                ⚠ Its output **does NOT go into `ARTIFACT`** (`临时设定.md` is
                  maintained separately by `world.layers.save_local`, see the comment in that table) ——
                  two writers writing to the same file will eventually produce "what's written in the file differs from what the system uses".
        """
        return await self.call('settings_room', ctx, story=story, beats=beats)

    # ══════════════════════════════════════════════════════════════════
    #  出图：美术 + 道具 → 提示词前缀
    # [EN] Image generation: art + props → prompt prefix
    # ══════════════════════════════════════════════════════════════════
    def image_prefix(self, day: int | None = None) -> str:
        """**给 `image_gen` 的提示词前缀**（美术指导 + 这一场的道具）。

        这就是"道具/美术接到工具上"的那一步：不是把产出写进一个 MD 就完了，
        而是让**当天的插图真的多出这些东西**、且与全剧风格一致。

        拿不到任何一样时返回空串（宁可不加，也别塞一句假的美术要求）。
        
                English:
        **Prompt prefix for `image_gen`** (art direction + this scene's props).
                This is the step of "props/art hooked onto the tool": it's not enough to just write the output into an MD file,
                rather the **day's illustration must actually gain these things** and stay consistent with the whole show's style.
                Return an empty string when none of them can be obtained (better to add nothing than to stuff in a fake art requirement).
        """
        bits: list[str] = []
        art = A.Art.prompt_prefix(self._art) if self._art is not None else ''
        if art:
            bits.append(art)
        d = int(day if day is not None else getattr(self.world, 'game_day', 0) or 0)
        # ★ **造型**（2026-10-07 审计补上）：人身上的东西也要进出图提示词。
        # [EN] ★ **Role design** (added in the 2026-10-07 audit): things on people must also go into the image
        # [EN] prompt.
        #
        # ⚠ 名册里写着 `stylist.feeds='actor'`、hook 指向 `image_gen.ai.build_prompt`，
        #   而它原来**两处都没接**：产出只落了一份 `造型表.md`，
        #   出图提示词里没有它、演员的决策材料里也没有它。
        #   表现就是"今天定了穿什么，明天同一个人画出来又是另一个样" ——
        #   而它存在的理由正是解决这个。
        # [EN] ⚠ The roster says `stylist.feeds='actor'` and the hook points to `image_gen.ai.build_prompt`,
        # [EN] yet it originally **connected neither**: its output only landed in a `造型表.md`,
        # [EN] it was not in the image prompt and not in the actor's decision material either.
        # [EN] The symptom is "today you decide what to wear, tomorrow the same person is drawn differently" --
        # [EN] and the very reason it exists is to solve this.
        s = self._stylist.get(d)
        if s is not None and s.ok:
            rows = (s.data or {}).get('造型') or []
            look = []
            for r in rows[:3]:
                if not isinstance(r, dict):
                    continue
                nm = str(r.get('人名') or '').strip()
                wear = str(r.get('穿着') or '').strip()
                carry = str(r.get('随身物') or '').strip()
                one = '｜'.join(x for x in (wear, carry) if x)
                if nm and one:
                    look.append(f'{nm}：{one}')
            if look:
                bits.append('人物形象：' + '；'.join(look))
        p = self._props.get(d)
        if p is not None and p.ok:
            names = [str(x.get('名称') or '') for x in (p.data.get('道具') or [])
                     if isinstance(x, dict) and str(x.get('名称') or '').strip()]
            if names:
                bits.append('场景中可见：' + '、'.join(names[:8]))
        return '；'.join(b for b in bits if b)

    # ══════════════════════════════════════════════════════════════════
    #  落盘
    # [EN] Persistence
    # ══════════════════════════════════════════════════════════════════
    #: 职位 → 它自己那份产物的文件名（`None` = 不单独落盘，只进台账）
    # [EN] : role → the filename of its own output (`None` = no separate file, ledger only)
    ARTIFACT: dict[str, str | None] = {
        'novelist': None,          # 样章由 `director.day_plan` 写进正文/缓存
        'screenwriter': None,      # 剧本由 `day_plan.save_cached` 落盘
        # ⚠ 编剧室**不写这一份**：`临时设定.md` 由 `world.layers.save_local`
        #   维护（它同时也要在装配时写一次，含"作者原本的设定已经够了"那种表述）。
        #   两个写入方写同一个文件，迟早出现"文件里写的和系统里用的不一样"。
        # [EN] The sample chapter is written into the main text/cache by `director.day_plan`
        # [EN] The script is persisted by `day_plan.save_cached`
        # [EN] ⚠ The writers' room **does not write this one**: `临时设定.md` is maintained by
        # [EN] `world.layers.save_local`
        # [EN] (it must also write once during assembly, including expressions like "the author's original
        # [EN] settings are already enough").
        # [EN] If two writers write the same file, sooner or later "what's in the file differs from what the
        # [EN] system uses".
        'settings_room': None,
        'director': None,
        'actor': None,
        'extra': None,
        'continuity': FILE_CONTINUITY,
        'props': FILE_PROPS,
        'art': FILE_ART,
        'publicity': FILE_PUBLICITY,
        'researcher': '考据笔记.md',
        # ── 2026-10-07 补的四位 ──
        # [EN] -- The four added 2026-10-07 --
        'reviewer': FILE_REVIEW,
        'stylist': FILE_STYLIST,
        'sound': FILE_SOUND,
        'polisher': FILE_POLISH,
        # ★ 排练（2026-10-07）：**唯一一份"明确不进中栏"的产物**。
        # [EN] ★ Rehearsal (2026-10-07): **the only output explicitly kept out of the middle column**.
        'rehearsal': FILE_REHEARSAL,
        # ⚠ `当天故事.md` **不在这张表里**：它不是"某个职位的一份活"，
        #   而是按天**累积**的一份稿（一天追加一节）。
        #   走这张表的话每天会被覆盖掉，第三天回头看就只剩第三天了
        #   （见 `sim/loop._day_novel`）。
        # [EN] ⚠ `当天故事.md` is **not in this table**: it is not "one job of some role",
        # [EN] but a draft **accumulated** per day (one section appended per day).
        # [EN] Going through this table, it would be overwritten every day, and on day three looking back only
        # [EN] day three would remain
        # [EN] (see `sim/loop._day_novel`).
    }

    #: 当天地图的落盘文件名。**必须和美术指导分开** —— 两者 role 都是 'art'，
    #: 走同一张 `ARTIFACT` 表的话，每天画一次图就会把「美术指导.md」覆盖掉
    #: （美术定的画风主色是全剧资产，丢了之后出图一致性就没了）。
    # [EN] : persistence filename for the day map. **Must be separate from the art director** -- both have
    # [EN] role 'art',
    # [EN] : if they went through the same `ARTIFACT` table, drawing once a day would overwrite 「美术指导.md」
    # [EN] : (the style and main colors the art sets are assets for the whole series; once lost, image
    # [EN] consistency is gone).
    FILE_DAY_MAP = '当天地图.md'

    def _custom_artifact(self, key: str) -> str | None:
        """自建职位的落盘文件名（`自定义-<名字>.md`）；出厂职位返回 `None`。
                English:
        The on-disk filename for a self-created role (`自定义-<name>.md`); factory roles return `None`.
        """
        try:
            from crew import catalog as _CAT
            spec = _CAT.get(str(key or ''))
        except Exception:                                        # noqa: BLE001
            return None
        if spec is None or not spec.is_custom:
            return None
        safe = ''.join(ch for ch in str(spec.name or spec.slug)
                       if ch not in '\\/:*?"<>|').strip() or spec.slug
        return f'自定义-{safe[:40]}.md'

    def _save_note(self, note: A.CrewNote) -> None:
        """把一份产出落进运行文件夹（没有 runfolder 就跳过）。

        ⚠ **台账与"这一位的单独产物"是两件事**，别用一个 `if` 串起来：
          第一版是"没有单独产物就直接 return"，于是导演/演员/群众演员
          （他们不单独落盘）那三次上报**都不会重写台账** ——
          磁盘上留着的是更早那份，里面那三行还是"待命"。
          表现就是"界面显示待命，而他们其实一整天都在干活"。
        
                English:
        Write a piece of output into the run folder (skip if there is no runfolder).
                ⚠ **The ledger and "this role's individual output" are two different things**, don't chain them with a single `if`:
                  The first version was "if there's no individual output, just return", so director/actor/extras
                  (they don't persist individually) those three reports **would not rewrite the ledger** ——
                  what remains on disk is an earlier version, in which those three lines still say "standby".
                  The symptom is "the UI shows standby, while they've actually been working all day".
        """
        if self.runfolder is None:
            return
        # 当天地图**走自己的文件**（`data['kind'] == 'day_map'`）——
        # 它和美术指导共用一个 role，但绝不能共用一个文件。
        # [EN] The day map **goes through its own file** (`data['kind'] == 'day_map'`) --
        # [EN] it shares a role with the art director, but must never share a file.
        is_day_map = str((note.data or {}).get('kind') or '') == 'day_map'
        rel = self.FILE_DAY_MAP if is_day_map else self.ARTIFACT.get(note.role)
        if rel is None:
            # ★ 自建职位（2026-10-11）：它不在 `ARTIFACT` 表里（那张表是出厂职位
            #   的落盘表）。给它一个**可预期的**文件名 —— 不落盘的话，作者建了
            #   一个职位、它天天出工，而盘上什么都找不到（那等于白建）。
            # [EN] ★ Custom roles (2026-10-11): it is not in the `ARTIFACT` table (that table is for factory roles'
            # [EN] persistence table). Give it a **predictable** filename -- without persistence, the author
            # [EN] creates
            # [EN] a role, it produces every day, and nothing can be found on disk (that is as good as not creating
            # [EN] it).
            rel = self._custom_artifact(note.role)
        if rel:
            try:
                title = ROSTER.role(note.role).name
                body = note.body or note.title or ''
                md = (f'# {title}\n\n'
                      f'> 第 {int(getattr(self.world, "game_day", 0) or 0)} 天'
                      f' · {"已出工" if note.ok else "没出活"}\n\n'
                      + (f'{body}\n' if body else '')
                      + (f'\n> 没出活的原因：{note.why}\n' if not note.ok else ''))
                atomic_write_text(Path(self.runfolder.root) / rel, md)
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('剧组产出落盘失败（不影响推演）：%r', e)
        # 台账每次都重写（它是"这一班人的近况"，不是逐日累积的稿子）
        # [EN] The ledger is rewritten every time (it is "the recent state of this shift", not a day-by-day
        # [EN] accumulated draft)
        try:
            atomic_write_text(Path(self.runfolder.root) / FILE_LEDGER,
                              self.ledger_md())
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧组台账落盘失败（不影响推演）：%r', e)

    def save_sidecar(self) -> None:
        """把台账另存一份 JSON（给界面/验证脚本读，不用去解析 Markdown）。
                English:
        Save the ledger as a JSON copy too (for the UI/verification scripts to read, without parsing
        Markdown).
        """
        if self.runfolder is None:
            return
        try:
            atomic_write_text(
                Path(self.runfolder.root) / '剧组台账.json',
                json.dumps(self.ledger(), ensure_ascii=False, indent=2))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧组台账 JSON 落盘失败（不影响推演）：%r', e)

    def ledger_md(self) -> str:
        """台账的 Markdown 一页（给人看：这班人各自干到了什么).
                English:
        The ledger's Markdown page (for humans: what each of these people accomplished).
        """
        rows = self.ledger()
        # ★ 认知模式那一列（2026-10-07 第七轮）：谁"先想后答"、谁只负责审 ——
        #   模式表（`crew/cognition.PATTERN`）就是靠这一列被**作者**读到的
        #   （不然它只有判据在读，和写着好看的注释没区别）。
        # [EN] ★ The cognition mode column (2026-10-07, round seven): who "thinks before answering", who only
        # [EN] reviews --
        # [EN] the pattern table (`crew/cognition.PATTERN`) is read by the **author** through this column
        # [EN] (otherwise only the criteria read it, no different from a comment that just looks nice).
        try:
            from crew import cognition as _COG
        except Exception:                                        # noqa: BLE001
            _COG = None
        lines = ['# 剧组台账', '',
                 f'> 第 {int(getattr(self.world, "game_day", 0) or 0)} 天', '',
                 '| 职位 | 状态 | 出工/未成 | 认知 | 最近一次产出 |',
                 '|---|---|---|---|---|']
        _state = {'idle': '待命', 'working': '出工中', 'done': '已交活',
                  'off': '未启用', 'onduty': '在岗'}
        for r in rows:
            line = (r['line'] or '—').replace('|', '/').replace('\n', ' ')
            cog = _COG.label(r['key']) if _COG is not None else '—'
            lines.append(f"| **{r['name']}** | {_state.get(r['state'], r['state'])} | "
                         f"{r['runs']} / {r['fails']} | {cog} | {line[:80]} |")
        lines += ['', '> 状态：`待命` 还没轮到 · `出工中` 正在做 · `已交活` 有产出 · '
                      '`未启用` 被设置关掉了 · `在岗` 常驻、整场都在',
                  '> 认知：`思维链` 先想后答 · `反思链` 产出后审 · '
                  '`思维链+反思` 两条都有 · `—` 不引入（理由见 `developers/docs/Agent认知升级方案.md`）']
        bad = ROSTER.audit_hooks()
        lines.append('> 接线自查：' + ('全部命中 ✓' if not bad
                                       else f'对不上 {bad}'))
        return '\n'.join(lines) + '\n'

    # ══════════════════════════════════════════════════════════════════
    #  播报
    # [EN] Broadcast
    # ══════════════════════════════════════════════════════════════════
    def _announce(self, note: A.CrewNote) -> None:
        """决定**这份产出要不要往界面发一条消息**（发成什么由界面那边定）。

        2026-10-07 再改：中栏现在**根本不显示产出内容**了（只显示阶段名/用时、
        工作状态、以及复盘那份总结），所以这里的口径也跟着变成"这条消息值不值得发"：

        | 档 | 发什么 |
        |---|---|
        | `off` | 只发**故障**与**今日总结** |
        | `key`（默认） | 再发**工作状态**：每位职位一行小字（用户在开头点名要的状态卡） |
        | `full` | 再在那一行后面补一句**标题**（"今天 2 处"）—— 仍然不是产出全文 |

        两条**在任何档位都发**（见 `_is_key_note`）：**没出活**（故障信号）与
        **今日总结**（用户白名单里点名的"一天结束后的总结"）。

        ⚠ 第一版这里写了一句 `or note.role == 'reviewer'` —— 那是**死代码**：
          `_is_key_note()` 早就对复盘返回 True 了。反例法当场揭穿
          （把那一句删掉，判据一条都不红）。所以现在**只有一条判据**
          （`_is_key_note`），"什么必须报"改起来只有一处。
        
                English:
        Decide **whether this output should send a message to the UI** (what to send is determined on
        the UI side).
                2026-10-07 changed again: the middle column now **does not show output content at all** (only stage name/elapsed time,
                work status, and the retro summary), so the criterion here also becomes "is this message worth sending":
                | tier | what to send |
                |---|---|
                | `off` | send only **failures** and **today's summary** |
                | `key` (default) | also send **work status**: one small line per role (the status card the user named at the start) |
                | `full` | also append a **title** after that line ("2 spots today") —— still not the full output text |
                Two items are sent **at any tier** (see `_is_key_note`): **no output produced** (failure signal) and
                **today's summary** (the "summary after the day ends" named in the user's whitelist).
                ⚠ The first version had a line here: `or note.role == 'reviewer'` —— that was **dead code**:
                  `_is_key_note()` already returned True for the retro. Counterexample method exposed it on the spot
                  (delete that line, and not a single criterion turns red). So now there is **only one criterion**
                  (`_is_key_note`), and "what must be reported" changes in only one place.
        """
        if self._on_note is None:
            return
        try:
            lv = str(CFG.s('CREW_SCREEN') or 'key').strip().lower()
            if not note.ok or self._is_key_note(note):
                self._on_note(note)
                return
            if lv in ('key', 'full'):
                self._on_note(note)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧组播报失败（不影响推演）：%r', e)

    @staticmethod
    def _is_key_note(note: A.CrewNote) -> bool:
        """这份产出是不是"**任何档位都要报**"的。

        三条判据，都对应"作者非知道不可"：

        * **复盘**（`reviewer`）—— 用户白名单里点名的
          「手动停止以及一天自动停止之后的总结」。
          ⚠ 这一条是**在 `off` 档也报**的唯一依据（`_announce` 不再另写一句
            `role == 'reviewer'` —— 反例法证明那是死代码：删掉它判据一条都不红，
            因为它本来就被这一句兜住了）。
        * **语言审校查出了问题**（`polisher` 且命中了 AI 味）——
          那是要作者动手改的东西；
        * **去 AI 审计命中了硬禁**（`data['去AI命中']`）——
          任何职位都可能带上这个标记（`Studio.call` 里统一查的）。

        ⚠ 名字里的 `key` 是**历史遗留**（以前它是"只在 `key` 档才问"的意思），
          现在它是"无条件要报"；改名会牵动 `verify_studio_v2` 的一排判据，
          所以留着名字、把口径写在这里。
        
                English:
        Whether this output is something that must be reported **at any tier**.
                Three criteria, all corresponding to "the author must know":
                * **Retro** (`reviewer`) —— the one named in the user's whitelist:
                  "the summary after a manual stop and after the day's automatic stop".
                  ⚠ This is the sole basis for reporting **even at the `off` tier** (`_announce` no longer writes another line
                    `role == 'reviewer'` —— counterexample method proved that was dead code: delete it and not a single criterion turns red,
                    because it was already covered by this line).
                * **Language review found a problem** (`polisher` and hit AI-flavor) ——
                  that's something the author needs to fix by hand;
                * **De-AI audit hit a hard ban** (`data['去AI命中']`) ——
                  any role can carry this flag (checked uniformly in `Studio.call`).
                ⚠ The `key` in the name is a **historical leftover** (it used to mean "only asked at the `key` tier"),
                  now it means "must always be reported"; renaming it would touch a whole row of criteria in `verify_studio_v2`,
                  so keep the name and document the criterion here.
        """
        if note.role == 'reviewer':
            return True
        if note.role == 'polisher' and note.ok:
            d = note.data or {}
            if int(d.get('问题数') or 0) > 0 or int(d.get('词表命中') or 0) > 0:
                return True
            return False
        if int((note.data or {}).get('去AI命中') or 0) > 0:
            return True
        return False
