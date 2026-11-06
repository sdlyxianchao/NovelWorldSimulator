# -*- coding: utf-8 -*-
"""后台批次器（设计稿 §五「前台/后台双制」）。

设计稿原文：
    前台 ≤`AGENT_MAX` 全 LLM 循环；后台 `light`（默认）**规则+批量摘要**，
    **进镜头自动升格并补经历记忆**。`BACKGROUND_MODE=off/light/full`。
    超员走**降格队列**：按「戏份权重 × 最近出场」排队降格为后台 light
    并补过渡记忆，不硬塞、不丢弃。

    每 tick 顺序：… → 前台步进 → **后台批次** → 边界看守 → 落盘。

为什么值得单独一层
------------------
没有它的时候，"后台人物"只是装配时 `role="后台"` 的一个标签：
`BACKGROUND_MODE` / `BACKGROUND_TICK_MINUTES` / `PROMOTE_ON_STAGE` /
`BACKGROUND_EVENT_RATE` 四个旋钮**一个都没人读**，后台的人既不行动、
也不留记忆、更不会在需要的时候走到台前 —— 台前永远只有同一份名册。

三档语义（`BACKGROUND_MODE`）
-----------------------------
  · `off`    —— 后台完全不管（就是老行为，留作对照/省钱）
  · `light`  —— **默认**。每 `BACKGROUND_TICK_MINUTES` 故事分钟跑一批：
                规则给每人补一条经历记忆（零成本）；按
                `BACKGROUND_EVENT_RATE` 掷骰，中了才叫一次 cheap「批量摘要」，
                产出一两句"后堂这边的动静"进事件流。
  · `full`   —— 每个后台人物真走一次 `Agent.decide()`（贵），同样按
                故事分钟节流。**只在"后台也要有戏"的项目里开。**

两条纪律
--------
1. **后台不进决策上下文之外的叙事**：`light` 的产出默认只写记忆与事件流，
   不逐条占中栏 —— 那是主角的位置（`_push_narrative` 由调用方决定）。
2. **失败绝不静默**：批量摘要走 `llm.replies.ask()` 的统一容错通道；
   拿不到就退回"只有规则那一半"，并把原因交给 `warn` 回调（由循环播报）。

English:
Background batcher (design doc §5 "foreground/background dual system").
Design doc original text:
    foreground ≤ `AGENT_MAX` all-LLM loop; background `light` (default) **rules + batch summary**,
    **entering the camera automatically promotes and backfills experience memory**. `BACKGROUND_MODE=off/light/full`.
    over-capacity goes through the **demotion queue**: queue demotions to background light by "screen-share weight × recent appearance"
    and backfill transition memory, no forcing in, no discarding.
    Per-tick order: … → foreground step → **background batch** → boundary guard → persist.
Why it deserves its own layer
------------------
Without it, "background characters" were just a label `role="background"` at assembly time:
`BACKGROUND_MODE` / `BACKGROUND_TICK_MINUTES` / `PROMOTE_ON_STAGE` /
**none** of the four knobs `BACKGROUND_EVENT_RATE` was read by anyone, background people neither
acted,
nor kept memories, nor stepped to the front when needed —— the front always had only the same
roster.
Three-tier semantics (`BACKGROUND_MODE`)
-----------------------------
  · `off`    —— background completely unmanaged (i.e. old behavior, kept for comparison/saving money)
  · `light`  —— **default**. Every `BACKGROUND_TICK_MINUTES` story minutes run a batch:
                rules add one experience memory per person (zero cost); roll dice by
                `BACKGROUND_EVENT_RATE`, and only on success call one cheap "batch summary",
                producing one or two sentences of "goings-on backstage" into the event stream.
  · `full`   —— each background character actually runs `Agent.decide()` once (expensive), also throttled
                by story minutes. **Only enable for projects that "need drama in the background too".**
Two disciplines
--------
1. **Background does not enter narrative beyond the decision context**: `light` output by default only writes memory and event stream,
   does not occupy the middle column line by line —— that's the protagonist's spot (`_push_narrative` is decided by the caller).
2. **Failures are never silent**: batch summary goes through the unified fault-tolerance channel of `llm.replies.ask()`;
   if unavailable, fall back to "only the rule half", and hand the reason to the `warn` callback (broadcast by the loop).
"""
from __future__ import annotations

import random
from typing import Any, Callable

from config import CFG
from llm import models as MODELS

_LOG = __import__("logging").getLogger("nws.sim.backstage")

# 规则层的一行模板：`(身份关键词, 模板)`。命中不了就用兜底的。
# [EN] One-line template for the rule layer: `(identity keyword, template)`. If nothing matches, use
# [EN] the fallback.
_RULE_LINES: tuple[tuple[str, str], ...] = (
    ("掌柜", "在柜上把这几日的流水又过了一遍"),
    ("账", "对着账本核了半天的数"),
    ("伙计", "里外跑了几趟，把该搬的搬了、该擦的擦了"),
    ("厨", "在后厨忙了一阵，灶上没断过火"),
    ("医", "在里间配了半天的药，没出门"),
    ("侠", "在后院练了一趟功，出了些汗"),
    ("官", "在灯下看了几页文书，眉头一直没松"),
    ("女", "在窗下坐了很久，手边的针线没怎么动"),
    ("仆", "把该收拾的都收拾了，没惊动谁"),
    ("徒", "跟着师父交代的活儿认真地做了"),
)
_RULE_DEFAULT = (
    "忙了些不打紧的事，没谁留意",
    "在自己那一摊上守着，没挪地方",
    "歇了一阵，又起来走动了几步",
)


def _rule_line(ps: Any, rng: random.Random) -> str:
    """规则层：这个后台人物这段时间**大概**在做什么（纯本地，零成本）。
        English:
    Rule layer: what this background character **probably** is doing during this period (purely
    local, zero cost).
    """
    blob = f"{getattr(ps, 'identity', '')}{getattr(ps, 'name', '')}"
    for kw, line in _RULE_LINES:
        if kw in blob:
            return line
    goal = str(getattr(ps, "goal", "") or getattr(ps, "current_goal", "") or "").strip()
    if goal:
        return f"手头仍是那件事（{goal[:18]}），忙了一阵"
    return rng.choice(_RULE_DEFAULT)


class BackstageBatcher:
    """后台批次器。**一次推演一个实例**（戏份计数是运行期的，不落盘）。
        English:
    Background batcher. **One instance runs one simulation** (screen-share counts are runtime, not
    persisted).
    """

    def __init__(self, world: Any, agents: list[Any], db: Any,
                 rng: random.Random | None = None,
                 on_warn: Callable[[str, str], None] | None = None):
        self.world = world
        self.agents = agents
        self.db = db
        self._rng = rng or random.Random()
        self._on_warn = on_warn
        self._acc = 0.0                      # 攒了多少故事分钟
        self._screen: dict[str, int] = {}    # 戏份权重（前台出场次数）
        self._last_seen: dict[str, float] = {}   # 最近出场（故事分钟）
        # [EN] How many story minutes accumulated
        # [EN] Screen-share weight (number of on-stage appearances)
        # [EN] Most recent appearance (story minutes)
        self._warned: set[str] = set()

    # ── 节流 ──────────────────────────────────────────────────────
    # [EN] ── Throttle ──────────────────────────────────────────────────────
    def mode(self) -> str:
        return (CFG.s("BACKGROUND_MODE") or "light").strip() or "light"

    def advance(self, minutes: float) -> None:
        """故事时间往前走，攒到点就跑一批。
                English:
        Story time moves forward, and once it accumulates to the point, run a batch.
        """
        try:
            self._acc += max(0.0, float(minutes))
        except (TypeError, ValueError):
            pass

    def due(self) -> bool:
        if self.mode() == "off":
            return False
        if not self.backstage_people():
            return False
        return self._acc >= max(1, CFG.i("BACKGROUND_TICK_MINUTES"))

    # ── 名册 ──────────────────────────────────────────────────────
    # [EN] ── Roster ──────────────────────────────────────────────────────
    def backstage_people(self) -> list[Any]:
        """在场的后台人物（`role == '后台'` 且没死没离场）。
                English:
        Background characters present (`role == 'background'` and not dead, not departed).
        """
        out = []
        for a in self.agents:
            ps = getattr(a, "ps", None)
            if ps is None:
                continue
            if getattr(ps, "role", "") != "后台":
                continue
            if str(getattr(ps, "status", "")) not in ("在场",):
                continue
            out.append(a)
        return out

    def frontstage_people(self) -> list[Any]:
        return [a for a in self.agents
                if getattr(getattr(a, "ps", None), "role", "") == "前台"
                and str(getattr(a.ps, "status", "")) == "在场"]

    # ── 戏份账（升/降格的依据）──────────────────────────────────────
    # [EN] ── Screen-share ledger (basis for promotion/demotion) ──────────────────────────────────────
    def note_on_screen(self, name: str) -> None:
        """记一次"他上了台"（前台每决策一次调一次）。
                English:
        Record one "he went on stage" (called once per foreground decision).
        """
        self._screen[name] = self._screen.get(name, 0) + 1
        self._last_seen[name] = self._game_min()

    def _game_min(self) -> float:
        clock = getattr(self.world, "clock", None)
        day = float(getattr(clock, "day", 1) or 1)
        minutes = float(getattr(clock, "minutes", 0) or 0)
        return day * 1440.0 + minutes

    def weight(self, name: str) -> float:
        """戏份权重 × 最近出场（都归一到 0~1 附近，越大约该留台前）。

        最久没上过台的（`_last_seen` 缺）按 0 算 —— **新人优先降格**，
        这样"顶着上限塞进来"的人会先回后台，而不是把常驻角色挤走。
        
                English:
        Screen-share weight × recent appearance (both normalized to near 0~1, the larger the more they
        should stay on stage).
                The one who has not been on stage longest (`_last_seen` missing) counts as 0 —— **newcomers demote first**,
                so that people "crammed in at the cap" go back to background first, instead of squeezing out regular characters.
        """
        weight = float(self._screen.get(name, 0))
        last = self._last_seen.get(name)
        if last is None:
            recency = 0.0
        else:
            recency = 1.0 / (1.0 + max(0.0, self._game_min() - last) / 60.0)
        return weight * (0.5 + recency)

    # ── 一批 ──────────────────────────────────────────────────────
    # [EN] ── Batch ──────────────────────────────────────────────────────
    async def run_batch(self, mention: set[str] | None = None) -> list[str]:
        """跑一批后台。返回**要播报的行**（调用方决定推哪条、用什么样式）。

        顺序照设计稿：先升格（该上台的上来）→ 再跑存量 → 最后处理超员降格。
        
                English:
        Run a background batch. Return **the lines to broadcast** (the caller decides which to push, and
        with what style).
                Order follows the design doc: first promote (those who should go on stage come up) → then run the existing → finally handle over-capacity demotion.
        """
        self._acc = 0.0
        news: list[str] = []
        news += self.promote(mention)
        try:
            if self.mode() == "full":
                news += await self._batch_full()
            else:
                news += await self._batch_light()
        except Exception as e:                                  # noqa: BLE001
            self._warn('batch', f"后台批次失败（不影响推演）：{e!r}")
        news += self.demote_over_capacity()
        return news

    async def _batch_light(self) -> list[str]:
        """`light`：规则补经历记忆（零成本）+ 掷骰决定要不要叫一次批量摘要。
                English:
        `light`: rule-based experience memory (zero cost) + roll dice to decide whether to call a batch
        summary.
        """
        rng = self._rng
        people = self.backstage_people()
        if not people:
            return []
        # ① 规则层：每人一条经历记忆。**这是"他们不是僵尸"的最低保证** ——
        #    不写的话，升格上来的人记忆里一片空白（"补经历记忆"补的就是这个）。
        # [EN] ① Rule layer: one experience memory per person. **This is the minimum guarantee that "they are
        # [EN] not zombies"** ——
        # [EN] If not written, a person who gets promoted has blank memory (this is exactly what "backfill
        # [EN] experience memory" fills in).
        for a in people:
            line = _rule_line(a.ps, rng)
            self._remember(a, line)
        # ② 批量摘要：一次调用覆盖所有人，且**按事件率掷骰**（省钱）。
        # [EN] ② Batch summary: one call covers everyone, and **rolls dice by event rate** (saves money).
        rate = max(0.0, min(1.0, CFG.f("BACKGROUND_EVENT_RATE")))
        if rng.random() >= rate:
            return []
        text = await self._summarize(people)
        if not text:
            return []
        try:
            self.db.add_event(f"BG-{int(self._game_min())}", text, "后台",
                              int(self.world.game_day), [], "")
            self.world.event_count = int(getattr(self.world, "event_count", 0) or 0) + 1
        except Exception as e:                                  # noqa: BLE001
            self._warn('bg_event', f"后台事件入库失败：{e!r}")
        return [text]

    @MODELS.agent('memory')
    async def _summarize(self, people: list[Any]) -> str:
        """cheap 档的批量摘要：这一批后台"后堂那边的动静"。

        ⚠ 走 `llm.replies.ask()`（统一容错通道），**不是**裸 `llm.chat()` ——
        裸调没有重试、没有抢救，失败还是静默的（本项目栽过）。
        
                English:
        cheap tier batch summary: the commotion from the back hall for this batch.
                ⚠ Go through `llm.replies.ask()` (unified fault-tolerant channel), **not** bare `llm.chat()` ——
                bare calls have no retry, no rescue, and failures are silent (this project got burned by that).
        """
        from llm.replies import ask
        who = "、".join(
            f"{getattr(a.ps, 'name', '')}（{getattr(a.ps, 'identity', '') or '无身份'}"
            f"；手头的事：{str(getattr(a.ps, 'goal', '') or '')[:20]}）"
            for a in people[:8])
        prompt = (f"这些人物此刻都在后堂/别处，不在当前这场戏里：{who}。\n"
                  f"当前场景：{getattr(self.world, 'scene', '')}；"
                  f"时间：{self.world.clock_display()}；"
                  f"天气：{getattr(self.world, 'weather', '')}。\n\n"
                  f"请用 **一句话**（≤40 字）交代他们这段时间弄出了什么动静 ——"
                  f"只写**可能影响到当前场景**的（谁托人带话、谁出门了、谁在后院弄出响动），"
                  f"没有就回空。不要写他们心里怎么想，不要编造新人物。\n"
                  f"只输出那句话本身。")
        rep = await ask("cheap", [{"role": "user", "content": prompt}],
                        purpose="backstage_summary", want="text",
                        temperature=0.4, max_tokens=200, min_chars=4,
                        default="", retry=False)
        if not rep.ok:
            # `Reply` 没有 `why` 字段（我第一版记错了）—— 拿 `notes` 讲原因，
            # 空就退回一句中性的，别让播报出现 "None"。
            # [EN] `Reply` has no `why` field (I misremembered in the first version) —— use `notes` to explain the
            # [EN] reason,
            # [EN] if empty, fall back to a neutral sentence, don't let "None" appear in the broadcast.
            why = "；".join(rep.notes) if rep.notes else "模型没给可用的正文"
            self._warn('bg_summary', f"后台批量摘要没拿到（{why}），本批只留规则记忆")
            return ""
        text = rep.value
        if isinstance(text, (list, tuple)):
            text = "".join(str(x) for x in text)
        return str(text or "").strip()[:80]

    async def _batch_full(self) -> list[str]:
        """`full`：每个后台人物真走一次决策（贵）。
                English:
        `full`: every background character actually goes through one decision (expensive).
        """
        import asyncio
        people = self.backstage_people()
        if not people:
            return []
        res = await asyncio.gather(*(a.decide() for a in people),
                                   return_exceptions=True)
        news: list[str] = []
        for a, act in zip(people, res):
            if isinstance(act, BaseException):
                self._warn('bg_decide', f"后台「{a.name}」决策失败：{act!r}")
                continue
            self._remember(a, self._act_line(act))
            line = self._act_line(act)
            if line:
                news.append(f"{a.name}{line}")
                try:
                    self.db.add_event(f"BG-{a.name}-{int(self._game_min())}",
                                      f"{a.name}{line}", "后台",
                                      int(self.world.game_day), [a.name], "")
                except Exception:                               # noqa: BLE001
                    pass
        return news[:3]              # 再热闹也只报前三条，别抢主角的戏
        # [EN] no matter how lively, only report the first three, don't steal the protagonist's spotlight

    @staticmethod
    def _act_line(act: Any) -> str:
        verb = str(getattr(act, "verb", "") or "")
        target = str(getattr(act, "target", "") or "").strip()
        talk = str(getattr(act, "dialogue", "") or "").strip()
        if talk:
            return f"说了一句：「{talk[:24]}」"
        if verb == "move" and target:
            return f"往{target}去了"
        if verb == "interact" and target:
            return f"在弄{target}"
        return ""

    def _remember(self, agent: Any, line: str) -> None:
        """给后台人物补一条经历记忆（"补经历记忆"照设计稿的字面意思）。

        记忆类型用 `observation`：他是**自己经历的**这些事，不是听说的。
        
                English:
        Add one experience memory to a background character ("add experience memory" per the literal
        meaning of the design doc).
                Use `observation` as the memory type: he **personally experienced** these things, he didn't hear about them.
        """
        if not line:
            return
        # ⚠ `add_memory` 的第 5 个参数是 **`game_ts`（故事分钟）**，不是 `game_day`
        #   —— 我第一版按 `game_day=` 写，直接 TypeError。照 `agent/core._add_memory`
        #   的算法来：`故事分钟 = 当天分钟 + 天数 × 1440`。
        # [EN] ⚠ The 5th parameter of `add_memory` is **`game_ts` (story minutes)**, not `game_day`
        # [EN] —— I wrote it as `game_day=` in the first version and got a straight TypeError. Follow the
        # [EN] algorithm in `agent/core._add_memory`
        # [EN] : `story minutes = minutes of the day + days × 1440`.
        clock = getattr(self.world, "clock", None)
        game_ts = 0.0
        try:
            game_ts = float(getattr(clock, "minutes", 0) or 0) \
                + float(getattr(clock, "day", 1) or 1) * 1440.0
        except (TypeError, ValueError):
            game_ts = 0.0
        try:
            self.db.add_memory(getattr(agent, "name", ""), line, "observation",
                               5.0, game_ts)
        except Exception as e:                                  # noqa: BLE001
            self._warn('bg_mem', f"后台记忆写入失败：{e!r}")

    # ── 升格（`PROMOTE_ON_STAGE`）──────────────────────────────────
    # [EN] ── Promotion (`PROMOTE_ON_STAGE`) ──────────────────────────────────
    def promote(self, mention: set[str] | None = None) -> list[str]:
        """把该上台的后台人物提到前台。返回播报行。

        两个条件（满足其一即可）：
          · **被点到名**（前台动作里提到了他）—— 剧情把人拉上台，最自然；
          · **地点对得上**（他其实就在这场戏的地点上）—— "他从后堂出来了"。
        且台前有空位（`AGENT_MAX`）。`PROMOTE_ON_STAGE=false` 时一律不动。
        
                English:
        Promote the background characters who should take the stage to the front stage. Return the
        broadcast line.
                Two conditions (either one suffices):
                  · **Being named** (mentioned in a front-stage action) —— the plot pulls the person on stage, most natural;
                  · **Location matches** (he's actually at this scene's location) —— "he came out from the back hall".
                And the front stage has an open slot (`AGENT_MAX`). When `PROMOTE_ON_STAGE=false`, do nothing at all.
        """
        if not CFG.b("PROMOTE_ON_STAGE"):
            return []
        limit = max(1, CFG.i("AGENT_MAX"))
        front = len(self.frontstage_people())
        if front >= limit:
            return []
        mention = {str(x).strip() for x in (mention or set()) if str(x).strip()}
        news: list[str] = []
        for a in self.backstage_people():
            if front >= limit:
                break
            ps = a.ps
            name = str(getattr(ps, "name", "") or "")
            if not name:
                continue
            called = name in mention
            on_site = False
            try:
                on_site = bool(self.world._loc_matches(ps))
            except Exception:                                   # noqa: BLE001
                on_site = False
            if not (called or on_site):
                continue
            ps.role = "前台"
            front += 1
            # 补经历记忆：他刚才在干什么（不然上台的人记忆里一片空白）
            # [EN] Backfill experience memory: what he was just doing (otherwise the promoted person's memory is
            # [EN] blank)
            self._remember(a, "（从后堂/别处来到人前。）")
            news.append(f"（{name}从后堂出来了。）"
                        if on_site and not called else f"（{name}被叫了来。）")
        return news

    # ── 降格（超员队列）────────────────────────────────────────────
    # [EN] ── Demotion (over-capacity queue) ────────────────────────────
    def demote_over_capacity(self) -> list[str]:
        """台前超过 `AGENT_MAX` → 按「戏份权重 × 最近出场」降格。

        ⚠ **不硬塞、不丢弃**：降下去的人仍在世界里、仍写经历记忆，
        只是不再逐个做 LLM 决策 —— 这正是"后台"的意义。
        
                English:
        Front stage exceeds `AGENT_MAX` → demote by "screen-time weight × most recent appearance".
                ⚠ **Don't force in, don't discard**: demoted people are still in the world and still write experience memory,
                they just no longer go through LLM decisions one by one —— which is exactly the meaning of "background".
        """
        limit = max(1, CFG.i("AGENT_MAX"))
        front = self.frontstage_people()
        if len(front) <= limit:
            return []
        # 权重低的先降；同权重时按名字排（保证可复现，测试才判得准）
        # [EN] lowest weight demotes first; ties broken by name (ensures reproducibility, so tests can judge
        # [EN] accurately)
        order = sorted(front, key=lambda a: (self.weight(a.name), a.name))
        news: list[str] = []
        for a in order[:len(front) - limit]:
            a.ps.role = "后台"
            self._remember(a, "（退回后堂，不在人前了。）")
            news.append(f"（{a.name}退到后堂去了。）")
        return news

    # ── 杂 ────────────────────────────────────────────────────────
    # [EN] ── Misc ────────────────────────────────────────────────────────
    def _warn(self, tag: str, msg: str) -> None:
        if tag in self._warned:
            return
        self._warned.add(tag)
        _LOG.warning("%s", msg)
        if self._on_warn:
            try:
                self._on_warn(tag, msg)
            except Exception:                                   # noqa: BLE001
                pass
