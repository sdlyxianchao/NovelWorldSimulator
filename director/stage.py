"""场次编排（运行时）—— 把剧作家的分拍表变成一个**能推进的状态机**。

为什么要有这个（2026-10-11，作者点名）：

    作者看了运行记录之后说：「这些人很多时候会东一句西一句，有些小的场景没
    交代清楚，突然大家就跳到几个新场景了」「场景反复切换却没有任何人物出场、
    动作、情节 —— 放到电视剧里就是无意义的场景切换」。
    他给的判断也是对的：**故事推演应该一场戏接一场戏**，每场戏有明确的
    主题 / 出场人物 / 动作 / 情绪 / 道具，由剧作家提前安排好。

    查下来的结果是：**剧作家确实安排好了，但那张表没下达，运行时也没有"场"
    这个单位** ——
      · 演员收到的"今日剧本"只有 `story[:400]` + 自己分到的那几件事，
        剧作家分的六拍（每拍在哪个场景、发生什么、推进什么）**一个字都看不到**
        （`agent/core.py` 里连 `beats` 这个词都只出现在注释里）；
      · 分幕（`SceneBuilder.maybe_break`）是**事后**按"时段变了 / 地点变了"切的，
        不是"这一拍演完了"；
      · 换场（`RunLoop._maybe_shift_scene`）是**被动**的：要等场上一个人都不剩，
        且目标地点恰好命中地点表 —— 于是要么一直不换，要么被随机位移带着乱换。
    所以这一层要补两件事：**按拍下发** + **逐场调度**。

分工（与本项目一贯的分工一致）：

    · 剧作家（`crew/agents.Screenwriter`）写**表** —— 分几拍、每拍是场什么戏；
    · 本模块（`StagePlan`）持**状态** —— 现在第几拍、这场戏演到哪儿了；
    · 导演（`sim/loop.RunLoop`）按状态**调度** —— 收场、换地方、进下一拍；
    · 演员仍然**自由发挥** —— 这里只给"这场戏的框"，不给台词（给了就是提线木偶）。

⚠ 一条底线：**没表就什么都不做**（`beats` 空 → `current` 恒为 None）。
  这一天没有分拍时，行为与加这一层之前**逐字相同** —— 不会因为多了一层把
  本来跑得通的推演弄坏。

    English:
    Stage scheduling (runtime) -- turn the playwright's beat sheet into a **state machine that can
    advance**.

    Why this exists (2026-10-11, called out by the author):

        After reading a run log the author said: "these people are all over the place most of the
        time, some small scenes are never explained clearly, and then everyone suddenly jumps to
        several new scenes" and "scenes switch back and forth with no character entering, no action,
        no plot -- put that on TV and it is a meaningless scene change".
        His judgement is right too: **a story should run one scene after another**, each scene with a
        clear topic, cast, action, mood and props, arranged in advance by the playwright.

        What the investigation found: **the playwright did arrange it, but that sheet was never
        handed down, and the runtime had no notion of a "scene" at all** --
          · the "today's script" an actor receives is only `story[:400]` + the few things assigned to
            him; the six beats the playwright split (which scene, what happens, what it advances)
            **are not visible at all** (in `agent/core.py` even the word `beats` appears only in
            comments);
          · act breaks (`SceneBuilder.maybe_break`) happen **after the fact**, keyed on "the time
            slot changed / the location changed", not on "this beat is finished";
          · scene changes (`RunLoop._maybe_shift_scene`) are **passive**: they wait until not a single
            person remains on stage and the target location happens to be in the location table --
            so either it never changes, or random movement drags it around.
        So this layer has to supply two things: **hand the beats down** + **schedule scene by scene**.

    Division of labour (consistent with the project's usual split):

        · the playwright (`crew/agents.Screenwriter`) writes the **sheet** -- how many beats, what
          kind of scene each one is;
        · this module (`StagePlan`) holds the **state** -- which beat we are on, how far this scene
          has got;
        · the director (`sim/loop.RunLoop`) **schedules** by that state -- wrap up, change place,
          move to the next beat;
        · the actors still **improvise freely** -- this only supplies the frame of the scene, never
          the lines (writing the lines would make them marionettes).

    ⚠ One bottom line: **with no sheet, do nothing** (empty `beats` -> `current` is always None).
      On a day with no beat breakdown the behavior is **byte-for-byte identical** to before this
      layer existed -- an extra layer must never break a simulation that used to run fine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import CFG

#: 本场提示里最多列几个"该出场的人"（列太多等于没重点）
# [EN] : At most how many "should appear" names to list in the scene brief (too many means no focus)
MAX_LISTED_CAST = 6


def _as_list(value: Any) -> list[str]:
    """把"一个字符串 / 一串字符串"统一成列表（模型两种写法都给过）。

        English:
    Normalize "a single string / a list of strings" into a list (the model has produced both).
    """
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


@dataclass
class Beat:
    """一场戏（剧作家分的一"拍"）。

    字段就是 `crew/agents.Screenwriter` 写的那几栏 —— **两边必须对得上**：
    它写 `要点`，这里就读 `要点`（改名要两处一起改）。

        English:
    One scene (one "beat" as split by the playwright).

        The fields are exactly the columns `crew/agents.Screenwriter` writes -- **the two sides must
        match**: it writes `要点`, this reads `要点` (renaming means changing both).
    """

    index: int = 1
    place: str = ''
    topic: str = ''
    cast: list[str] = field(default_factory=list)
    props: list[str] = field(default_factory=list)
    mood: str = ''
    gist: list[str] = field(default_factory=list)
    what: str = ''
    advance: str = ''

    @property
    def label(self) -> str:
        """这一拍的一句话名字（**没有主题就退回"发生"的前几句**）。

        ⚠ 为什么不是空串：分隔符与台账都要显示"这是第几拍、在演什么"，
          空标题比一个粗糙的标题更让人迷糊。

            English:
        A one-line name for this beat (**fall back to the opening of "what happens" when there is no
        topic**).
            ⚠ Why not an empty string: separators and the ledger both need to show "which beat this
              is and what it is playing"; an empty title is more confusing than a rough one.
        """
        if self.topic:
            return self.topic
        text = ' '.join(str(self.what or '').split())
        return text[:16] if text else ''

    @property
    def full_label(self) -> str:
        """幕首那一行：`第 2 拍 · 堂屋 · 试探`（缺哪样就省哪样）。
            English:
        The act-header line: `beat 2 · the hall · testing him` (omit whatever is missing).
        """
        bits = [f'第 {self.index} 拍']
        if self.place:
            bits.append(self.place)
        if self.label:
            bits.append(self.label)
        return ' · '.join(bits)

    @classmethod
    def from_row(cls, row: Any, index: int) -> 'Beat | None':
        """从剧作家给的那一行字典造一拍。**不是字典就返回 None**（整行丢掉）。
            English:
        Build one beat from the dict row the playwright gave. **Return None if it isn't a dict**
        (drop the whole row).
        """
        if not isinstance(row, dict):
            return None
        def _s(key: str, cap: int = 200) -> str:
            return ' '.join(str(row.get(key) or '').split())[:cap]
        return cls(index=int(row.get('拍') or index),
                   place=_s('场', 20),
                   topic=_s('主题', 40),
                   cast=_as_list(row.get('出场'))[:MAX_LISTED_CAST],
                   props=_as_list(row.get('道具'))[:4],
                   mood=_s('情绪', 16),
                   gist=_as_list(row.get('要点'))[:4],
                   what=_s('发生', 120),
                   advance=_s('推进', 80))


class StagePlan:
    """一天的场次编排：**一场接一场**。

    生命周期（对应 `sim/loop.RunLoop._tick` 里的调用）：

        observe(该拍发生的事)  →  done_reason() 说"可以收场了"  →  advance() 进下一拍

    ⚠ 所有"演完没有"的判断都在**规则**里（出场到齐 / 戏量够了 / 到上限），
      不额外调模型 —— 这一层必须是零成本的，否则"一场戏一场戏"会变成
      "一场戏一次 API 调用"。
    ⚠ 但**可以关**（`SCENE_BEATS`）：关掉就是老行为，表还在（台账还看得见），
      只是不按它推进。

        English:
    One day's stage schedule: **one scene after another**.

        Lifecycle (matching the calls in `sim/loop.RunLoop._tick`):

            observe(what happened this beat) -> done_reason() says "time to wrap up" -> advance()

        ⚠ Every "is it finished" decision lives in **rules** (cast arrived / enough drama / hit the
          cap), with no extra model call -- this layer must be zero-cost, otherwise "one scene after
          another" turns into "one API call per scene".
        ⚠ But it **can be switched off** (`SCENE_BEATS`): off means the old behavior; the sheet is
          still there (still visible in the ledger), it just no longer drives anything.
    """

    def __init__(self, beats: list[dict] | None = None, *,
                 day: int = 1, start_index: int = 0) -> None:
        self.day = int(day or 1)
        self.beats: list[Beat] = []
        for i, row in enumerate(list(beats or []), 1):
            b = Beat.from_row(row, i)
            if b is not None and (b.what or b.place or b.cast):
                self.beats.append(b)
        #: 当前是第几拍（0 起算的下标；== len(beats) 表示演完了）
        # [EN] : Which beat we are on (0-based index; == len(beats) means finished)
        self._i = max(0, int(start_index or 0))
        # ── 本场的记账（`observe` 写，`done_reason` 读）──
        # [EN] -- This scene's ledger (`observe` writes, `done_reason` reads) --
        self.ticks: int = 0
        self.acts: int = 0
        self.seen: set[str] = set()
        self.spoken: set[str] = set()

    # ══════════════════════════════════════════════════════════
    #  只读
    # [EN] Read-only
    # ══════════════════════════════════════════════════════════
    @property
    def index(self) -> int:
        """当前第几拍（**1 起算**，给作者看的那个数）。
            English:
        Which beat we are on (**1-based**, the number shown to the author).
        """
        return self._i + 1

    @property
    def total(self) -> int:
        return len(self.beats)

    @property
    def current(self) -> Beat | None:
        """当前这一场戏。**没有表 / 演完了 → None**（调用方据此什么都不做）。
            English:
        The current scene. **No sheet / all done -> None** (callers do nothing in that case).
        """
        if 0 <= self._i < len(self.beats):
            return self.beats[self._i]
        return None

    @property
    def previous(self) -> Beat | None:
        """**上一场**（第一场时是 None）。

        ★ 2026-10-12：它唯一的用途是算"**从上一场到这一场怎么走**"
          （`Agent._map_line` → `world.spatial.movement_line`）。
          没有它，人物移动只能靠语感 —— 而用户点名的正是这件事：
          「导演和剧作家在设计人物动作的时候要**时时刻刻参考地图**作为
            人物移动的依据」。
        [EN] **The previous beat** (None for the first one).
        [EN] ★ 2026-10-12: its only use is computing "**how to walk from the previous scene to this one**"
        [EN] (`Agent._map_line` -> `world.spatial.movement_line`).
        [EN] Without it, character movement runs on intuition -- and that is exactly the item the user
        [EN] named: "the director and playwright must **constantly consult the map** as the basis for
        [EN] character movement when designing character actions".
        """
        if 0 < self._i <= len(self.beats):
            return self.beats[self._i - 1]
        return None

    def upcoming(self, n: int = 1) -> list[Beat]:
        """接下来 n 拍（用于提示词里给一句"下一场是什么"，让他别抢戏）。
            English:
        The next n beats (used in the prompt to hint "what the next scene is", so he doesn't steal
        the scene).
        """
        out: list[Beat] = []
        for k in range(1, max(0, n) + 1):
            j = self._i + k
            if 0 <= j < len(self.beats):
                out.append(self.beats[j])
        return out

    @property
    def finished(self) -> bool:
        return self._i >= len(self.beats)

    @property
    def enabled(self) -> bool:
        """这一层**这一轮是不是开着**（`SCENE_BEATS`）。
            English:
        Whether this layer is **switched on this round** (`SCENE_BEATS`).
        """
        try:
            return bool(CFG.b('SCENE_BEATS'))
        except Exception:                                        # noqa: BLE001
            return True

    # ══════════════════════════════════════════════════════════
    #  记账与推进
    # [EN] Ledger and advance
    # ══════════════════════════════════════════════════════════
    def observe(self, *, acted: int = 0, present: Any = None,
                spoke: Any = None) -> None:
        """把这一拍发生的事记进本场的账。

        ⚠ `present` / `spoke` 收的是**名字集合**，不是 Agent 对象 ——
          这一层不认识 Agent，只认识名字（判据好写、也好测）。

            English:
        Record what happened this beat into the scene's ledger.
            ⚠ `present` / `spoke` take **sets of names**, not Agent objects -- this layer knows
              nothing about Agents, only names (easier to verify and test).
        """
        self.ticks += 1
        self.acts += max(0, int(acted or 0))
        for name in _as_list(present):
            self.seen.add(name)
        for name in _as_list(spoke):
            self.spoken.add(name)

    def _reset_ledger(self) -> None:
        self.ticks = 0
        self.acts = 0
        self.seen = set()
        self.spoken = set()

    def advance(self) -> Beat | None:
        """收掉这一场，进下一拍。返回**新的一场戏**（演完了返回 None）。
            English:
        Close this scene and move to the next beat. Returns **the new scene** (None when all done).
        """
        self._i += 1
        self._reset_ledger()
        return self.current

    # ══════════════════════════════════════════════════════════
    #  「这一场演完了吗」
    # [EN] "Is this scene finished?"
    # ══════════════════════════════════════════════════════════
    def missing_cast(self) -> list[str]:
        """该出场**却一直没露面**的人（本场的欠账）。
            English:
        People who **should have appeared but never did** (this scene's outstanding debt).
        """
        b = self.current
        if b is None:
            return []
        return [n for n in b.cast if n not in self.seen]

    def limits(self) -> tuple[int, int, int]:
        """`(最少跑几拍, 最多跑几拍, 最少几条实动作)` —— 三个都能从配置改。
            English:
        `(minimum ticks, maximum ticks, minimum real actions)` -- all three configurable.
        """
        def _i(key: str, dflt: int) -> int:
            try:
                v = int(CFG.i(key))
                return v if v > 0 else dflt
            except Exception:                                    # noqa: BLE001
                return dflt
        lo = _i('SCENE_BEAT_MIN_TICKS', 3)
        hi = _i('SCENE_BEAT_MAX_TICKS', 12)
        if hi < lo:
            hi = lo
        return lo, hi, _i('SCENE_BEAT_MIN_ACTS', 2)

    def done_reason(self) -> str:
        """**这一场演完了没有**？演完了返回一句"为什么"，否则空串。

        四条判据（按顺序，**任一条成立就收场**）：

          ① 到硬上限（`SCENE_BEAT_MAX_TICKS`）—— 防一场戏无限拖；
          ② 戏量够了（>= `SCENE_BEAT_MIN_ACTS` 条实动作）**且**该出场的
             都露过面（`seen` 覆盖 `cast`）—— 这是**正常的收场**；
          ③ 戏量够了、且表里没写 `出场`（旧数据）—— 一样收；
          ④ 低于最少拍数（`SCENE_BEAT_MIN_TICKS`）**一律不收** ——
             否则每拍只跑一 tick 就翻页，"一场戏"会和"一拍"一样长，
             反而更碎（这正是作者抱怨的"突然就跳到新场景"）。

        ⚠ ②③ 里的"戏量"用的是**实动作条数**，不是"跑了几 tick"：
          全场发呆也算跑了 tick，但那不该算"演过了"。

            English:
        **Is this scene finished?** Returns a sentence saying why when it is, else an empty string.

            Four criteria (in order; **any one firing wraps the scene up**):

              ① hit the hard cap (`SCENE_BEAT_MAX_TICKS`) -- stops a scene dragging on forever;
              ② enough drama (>= `SCENE_BEAT_MIN_ACTS` real actions) **and** everyone who should
                 appear has appeared (`seen` covers `cast`) -- this is the **normal wrap-up**;
              ③ enough drama and the sheet names no `出场` (old data) -- wrap up the same way;
              ④ below the minimum tick count (`SCENE_BEAT_MIN_TICKS`) it **never** wraps -- otherwise
                 every beat would flip after a single tick and "a scene" would be as short as "a
                 beat", making things *more* fragmented (exactly the author's complaint about
                 "suddenly jumping to a new scene").

            ⚠ The "drama" in ②③ counts **real actions**, not "how many ticks ran": the whole cast
              spacing out still burns ticks, but that shouldn't count as "performed".
        """
        b = self.current
        if b is None:
            return ''
        lo, hi, min_acts = self.limits()
        if self.ticks >= hi:
            return (f'第 {b.index} 拍已跑 {self.ticks} 拍（到上限 {hi}），收场'
                    + (f'；没露面：{"、".join(self.missing_cast())}' if self.missing_cast() else ''))
        if self.ticks < lo:
            return ''
        if self.acts < min_acts:
            return ''
        miss = self.missing_cast()
        if b.cast and miss:
            # 表里点了名却没露面 —— 不收（那正是"没人出场的空场"要治的病）。
            # 但**只在还没到上限时**才等它；到上限已在上面那一条收掉了。
            # [EN] The sheet named someone who never showed -- don't wrap up (that is exactly the
            # [EN] "empty scene with nobody in it" disease). But **only wait while below the cap**;
            # [EN] hitting the cap is handled by the branch above.
            return ''
        return (f'第 {b.index} 拍演完（{b.label or "本场"}）'
                f'：{self.ticks} 拍 / {self.acts} 条实动作')

    # ══════════════════════════════════════════════════════════
    #  给提示词与界面
    # [EN] For prompts and the UI
    # ══════════════════════════════════════════════════════════
    def header(self) -> str:
        """幕首那一行（分隔符与幕首卡片用）。
            English:
        The act-header line (used by separators and the act-opening card).
        """
        b = self.current
        return b.full_label if b is not None else ''

    def prompt_block(self, who: str = '') -> str:
        """**给某个演员看的"本场"提示**（没有表 / 演完了 → 空串）。

        ★ 这是整个改动**最要紧的一块**：剧作家的表就是从这里下达到演员手上的。
          `who` 传进来是为了把"这场戏里有你"这件事说清楚 —— 不在名单里的人
          看的是"这场戏没有你"，那也是一条有用的信息（他该去做别的）。

        ⚠ 只给**当前这一拍**（外加一句"下一场是什么"），**不给全表**：
          给全表等于把后面的戏透给他，他会去抢别人那一场。

            English:
        **The "this scene" brief shown to one actor** (no sheet / all done -> empty string).

        ★ This is **the single most important piece of the whole change**: the playwright's sheet
          reaches the actors right here. `who` is passed in to make "you are in this scene" explicit
          -- someone not on the list reads "this scene doesn't include you", which is also useful
          information (he should go do something else).

        ⚠ Only **the current beat** is given (plus one line about "what the next scene is"),
          **never the whole sheet**: the whole sheet would leak the later scenes to him and he would
          steal someone else's.
        """
        b = self.current
        if b is None:
            return ''
        lines = [f'\n[本场（第 {b.index} / {self.total} 拍）]']
        if b.place:
            lines.append(f'- 在哪儿：{b.place}')
        if b.topic:
            lines.append(f'- 这场戏在讲什么：{b.topic}')
        if b.cast:
            lines.append('- 这场戏该有：' + '、'.join(b.cast[:MAX_LISTED_CAST]))
        if who:
            lines.append(f'- {"你在其中" if who in b.cast else "这场戏没有你"}')
        if b.gist:
            lines.append('- 这一拍要落到：' + '｜'.join(b.gist))
        if b.props:
            lines.append('- 要动的东西：' + '、'.join(b.props))
        if b.mood:
            lines.append(f'- 情绪基调：{b.mood}')
        if b.advance:
            lines.append(f'- 这场戏演完的样子：{b.advance}')
        nxt = self.upcoming(1)
        if nxt:
            lines.append(f'- （下一场：{nxt[0].full_label}）')
        lines.append('（把上面这些演出来就算这场戏成了；**戏没演完别急着走**，'
                     '也别去演别人的场。）')
        return '\n'.join(lines) + '\n'

    def ledger_line(self) -> str:
        """剧组台账 / 状态条上那一行（`第 2/6 拍 · 堂屋 · 试探`）。
            English:
        The line for the crew ledger / status bar (`beat 2/6 · the hall · testing him`).
        """
        b = self.current
        if b is None:
            return f'已演完（共 {self.total} 拍）' if self.total else ''
        head = f'第 {b.index}/{self.total} 拍'
        tail = ' · '.join(x for x in (b.place, b.label) if x)
        return f'{head} · {tail}' if tail else head

    # ── 落盘 ──
    # [EN] -- Persistence --
    def to_dict(self) -> dict:
        return {'day': self.day, 'index': self._i,
                'beats': [{'拍': b.index, '场': b.place, '主题': b.topic,
                           '出场': list(b.cast), '发生': b.what,
                           '要点': list(b.gist), '道具': list(b.props),
                           '情绪': b.mood, '推进': b.advance}
                          for b in self.beats]}

    @classmethod
    def from_dict(cls, data: Any) -> 'StagePlan | None':
        if not isinstance(data, dict):
            return None
        plan = cls(data.get('beats') or [], day=int(data.get('day') or 1),
                   start_index=int(data.get('index') or 0))
        return plan if plan.beats else None
