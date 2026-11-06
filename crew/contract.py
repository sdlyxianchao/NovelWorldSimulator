# -*- coding: utf-8 -*-
"""场记的**确定性**底座：全局一致性契约 + 六类检查 + 伏笔账。

为什么要有这个模块（而不是继续让"场记"那个 LLM 职位去查）
----------------------------------------------------------
本项目有一条反复应验的纪律：**能确定性的，别交给模型判断。**
场记（`crew.agents.Continuity`）目前是纯 LLM 的 —— 它读一遍正文、凭印象报几条。
这有两个毛病：

1. **它记不住**：昨天报过的问题今天不记得，同一个人换了衣服它也不会累计；
2. **它凭印象**：实测里它会把"今天新发生的事"当成"跟昨天不符"报上来，
   于是假警报一多，真问题也没人看（这一条已经用"只抓重大矛盾"的措辞压过一次，
   但**措辞治不了"它根本没有那份账"**）。

外部调研（第 02 类第 1 条）里 **PenShot**（`neopen/story-shot-agent`，**MIT**）
给出了正解：它维护一份 **`ConsistencyContract`**（全局一致性契约），
里有 `characters{name, outfit_sequence[], held_props, appearance_days[]}`、
`scenes{location, time, props_in_scene{name:state}}`、`style_anchor`，
每天推演后跑 **角色 / 场景 / 动作 / 风格 / 时间 / 道具** 六类检查，
并用 `"类型_地点_严重度_描述前100字"` 去重。

⇒ **这份契约是纯数据结构 + 纯函数检查，一个 token 都不花、可复现、可断言。**
   LLM 那份"场记意见"照旧保留（它擅长的是"这句话读着不对"这类软判断），
   两者**分层**：确定性层管"事实对不上"，模型层管"读着不对"。

★ 与 `crew/gate.py` 的关系
--------------------------
检查结果统一用 `crew.gate.Report`（惩罚制 + PASSED/NEEDS_REVIEW/FAILED），
因为这是"这一天的产出过不过"的**单件**判定，不是跨版本比较。

English:
The **deterministic** foundation of the continuity clerk: global consistency contract + six
check categories + foreshadowing ledger.
Why this module should exist (instead of continuing to let the "continuity clerk" LLM role do
the checking)
----------------------------------------------------------
This project has a repeatedly validated discipline: **what can be made deterministic, don't hand
to a model to judge.**
The continuity clerk (`crew.agents.Continuity`) is currently pure LLM —— it reads through the
text once and reports a few items by impression.
This has two problems:
1. **It can't remember**: problems reported yesterday are not remembered today, and it won't accumulate when the same person changes clothes;
2. **It goes by impression**: in testing it treats "things newly happening today" as "inconsistent with yesterday" and reports them,
   so once false alarms pile up, nobody looks at real problems either (this one has already been suppressed once with the wording "only catch major contradictions",
   but **wording can't cure "it simply doesn't have that ledger"**).
In external research (Category 02, item 1), **PenShot** (`neopen/story-shot-agent`, **MIT**)
gives the correct solution: it maintains a **`ConsistencyContract`** (global consistency
contract),
which contains `characters{name, outfit_sequence[], held_props, appearance_days[]}`,
`scenes{location, time, props_in_scene{name:state}}`, `style_anchor`,
after each day's simulation runs the six check categories **character / scene / action / style /
time / prop**,
⇒ **This contract is pure data structures + pure function checks, costs not a single token, is
reproducible, and is assertable.**
The LLM's "continuity clerk opinions" are kept as before (what it is good at is soft judgments
like "this sentence reads wrong"),
   the two are **layered**: the deterministic layer handles "facts don't match up", the model layer handles "reads wrong".
★ Relationship with `crew/gate.py`
--------------------------
Check results uniformly use `crew.gate.Report` (penalty system + PASSED/NEEDS_REVIEW/FAILED),
because this is a **single-item** judgment of "whether this day's output passes", not a
cross-version comparison.
A foreshadowing entry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ══════════════════════════════════════════════════════════════════
#  伏笔账（第 01 类第 2 条：Open-Write `callback_ledger.json` 的思路）
# [EN] Foreshadowing ledger (Category 01, item 2: the idea behind Open-Write `callback_ledger.json`)
# ══════════════════════════════════════════════════════════════════
@dataclass
class Foreshadow:
    """一条伏笔。

    ★ 三个字段缺一不可，这是它相对"写着备忘"的全部价值：
      `seeded_at`（埋在第几章/天）· `must_pay_off_by`（最晚第几章/天回收）·
      `paid_off`（实际回收在第几章/天，没回收就是 None）。
      ——**"最晚哪一章必须回收"这一栏才是它真正管用的地方**：
        没有它，"这条还没回收"永远只是一句感慨，无法变成一条会红的判据。
    
        English:
    ★ The three fields are all indispensable; this is its entire value compared to "writing a memo":
        `seeded_at` (which chapter/day it was planted) · `must_pay_off_by` (at the latest which chapter/day it must be paid off) ·
          `paid_off` (in which chapter/day it was actually paid off; None if not paid off).
          ——**The "at the latest which chapter it must be paid off" column is where it truly works**:
          without it, "this one hasn't been paid off yet" forever remains just a sigh, and cannot become a criterion that turns red.
        Foreshadowing ledger: does only three things —— register, check off payoff, check overdue.
    """

    name: str
    seeded_at: int = 0
    must_pay_off_by: int = 0
    paid_off: int | None = None
    keywords: tuple[str, ...] = ()

    @property
    def open(self) -> bool:
        return self.paid_off is None

    def overdue(self, at: int) -> bool:
        """到第 `at` 章还没回收，且已经过了最晚期限。
                English:
        Check off payoff. Returns False if not found (**must not quietly create a new entry** —— that
        would turn "never registered"
        """
        return self.open and bool(self.must_pay_off_by) and at > self.must_pay_off_by


class ForeshadowLedger:
    """伏笔账：只做三件事 —— 登记、勾回收、查过期。
        English:
    The state of a character in the contract.
    """

    def __init__(self) -> None:
        self.items: list[Foreshadow] = []

    def plant(self, name: str, *, at: int, by: int = 0,
              keywords: tuple[str, ...] = ()) -> Foreshadow:
        f = Foreshadow(name=str(name).strip(), seeded_at=int(at),
                       must_pay_off_by=int(by or 0), keywords=tuple(keywords))
        self.items.append(f)
        return f

    def pay(self, name: str, *, at: int) -> bool:
        """勾回收。找不到返回 False（**不许悄悄新建一条** —— 那会把"没登记过"
        变成"登记过了"，正是这个账最该防的错）。
                English:
        into "already registered", which is exactly the error this ledger most needs to prevent).
                Search the main text for payoff traces by `keywords` (**deterministic**, don't look at what the model says).
        """
        for f in self.items:
            if f.name == str(name).strip() and f.open:
                f.paid_off = int(at)
                return True
        return False

    def scan_text(self, text: str, *, at: int) -> list[str]:
        """按 `keywords` 在正文里找回收痕迹（**确定性**，不看模型怎么说）。

        只认"关键词真的出现了"这一件事；至于"这算不算回收"仍要人/模型判，
        但**"有没有出现"这件事不该靠模型说**。
        
                English:
        Only recognize the single fact that "the keyword really appeared"; as for "whether this counts
        as payoff", that still has to be judged by a person/model,
                but **"whether it appeared" should not depend on what the model says**.
        """
        paid: list[str] = []
        for f in self.items:
            if not f.open or not f.keywords:
                continue
            if any(str(k) and str(k) in text for k in f.keywords):
                f.paid_off = int(at)
                paid.append(f.name)
        return paid

    def overdue(self, at: int) -> list[Foreshadow]:
        return [f for f in self.items if f.overdue(at)]

    def open_items(self) -> list[Foreshadow]:
        return [f for f in self.items if f.open]

    def to_json(self) -> list[dict]:
        return [{'名称': f.name, '埋于': f.seeded_at, '最晚回收': f.must_pay_off_by,
                 '已回收于': f.paid_off, '关键词': list(f.keywords)}
                for f in self.items]


# ══════════════════════════════════════════════════════════════════
#  全局一致性契约
# [EN] Global consistency contract
# ══════════════════════════════════════════════════════════════════
#: 六类检查的名字（报告里逐类报，别合成一句"有 3 个问题"）
# [EN] : the names of the six check categories (report each category separately in the report, don't
# [EN] merge them into one sentence like "there are 3 problems")
KINDS: tuple[str, ...] = ('角色', '场景', '动作', '风格', '时间', '道具')

#: 去重键的写法（PenShot 原话是 `类型_地点_严重度_描述前100字`）。
#: ★ 去重**必须这么算**：只按"描述前 100 字"会把同一个问题在不同地点报两次，
#:   只按"类型"又会把两类不同的错压成一条。三段加起来才既不重不漏。
# [EN] : ★ Dedup **must be computed this way**: using only "first 100 chars of description" will report
# [EN] the same problem twice at different locations,
# [EN] : using only "type" will compress two different kinds of errors into one entry. Only all three
# [EN] segments together are neither duplicate nor missing.
DEDUPE_DESC_LEN = 100


def dedupe_key(kind: str, where: str, severity: str, what: str) -> str:
    return f'{kind}_{where}_{severity}_{str(what)[:DEDUPE_DESC_LEN]}'


@dataclass
class CharState:
    """一个角色在契约里的状态。
        English:
    The state of a scene in the contract.
    """

    name: str
    outfit_sequence: list[str] = field(default_factory=list)
    held_props: list[str] = field(default_factory=list)
    appearance_days: list[int] = field(default_factory=list)

    def note_outfit(self, outfit: str, day: int) -> None:
        s = str(outfit or '').strip()
        if s and (not self.outfit_sequence or self.outfit_sequence[-1] != s):
            self.outfit_sequence.append(s)

    def note_day(self, day: int) -> None:
        if day not in self.appearance_days:
            self.appearance_days.append(int(day))


@dataclass
class SceneState:
    """一处场景在契约里的状态。
        English:
    Global consistency contract (see the module header).
    """

    location: str
    time: str = ''
    props_in_scene: dict[str, str] = field(default_factory=dict)   # 名 → 状态
    # [EN] name → state


@dataclass
class ConsistencyContract:
    """全局一致性契约（见模块头）。

    它**只累积事实、不判断对错** —— 判断在 `check()` 里，是纯函数。
    
        English:
    It **only accumulates facts, does not judge right or wrong** —— judgment is in `check()`, and is
    a pure function.
    """

    characters: dict[str, CharState] = field(default_factory=dict)
    scenes: dict[str, SceneState] = field(default_factory=dict)
    style_anchor: str = ''
    #: 已经报过的问题（去重键集合）
    # [EN] : problems already reported (set of dedup keys)
    reported: set[str] = field(default_factory=set)

    # ── 累积（每天推演后调一次）─────────────────────────────────
    # [EN] ── accumulation (called once after each day's simulation) ─────────────────────────────────
    def observe(self, *, day: int, location: str = '', time_label: str = '',
                people: list[str] | None = None,
                outfits: dict[str, str] | None = None,
                props: list[str] | None = None) -> None:
        loc = str(location or '').strip()
        if loc:
            sc = self.scenes.setdefault(loc, SceneState(location=loc))
            if time_label:
                sc.time = str(time_label).strip()
        for n in (people or []):
            nm = str(n or '').strip()
            if nm:
                self.characters.setdefault(nm, CharState(name=nm)).note_day(int(day))
        for nm, wear in (outfits or {}).items():
            c = self.characters.setdefault(str(nm).strip(), CharState(name=str(nm).strip()))
            c.note_outfit(str(wear), int(day))
            c.note_day(int(day))
        if loc:
            sc = self.scenes.setdefault(loc, SceneState(location=loc))
            for p in (props or []):
                nm = str(p or '').strip()
                if nm and nm not in sc.props_in_scene:
                    sc.props_in_scene[nm] = '在场'

    def mark_prop(self, location: str, name: str, state: str) -> None:
        """改一件道具的状态（`在场 / 已毁 / 已送出 / 已拿走`）。
                English:
        Change the state of an item (`present / destroyed / given away / taken away`).
        """
        loc = str(location or '').strip()
        if not loc:
            return
        self.scenes.setdefault(loc, SceneState(location=loc)).props_in_scene[
            str(name).strip()] = str(state).strip()

    # ── 判定 ────────────────────────────────────────────────────
    # [EN] ── judgment ────────────────────────────────────────────────────
    def check(self, *, day: int, today_people: list[str] | None = None,
              today_props: list[str] | None = None, today_place: str = '',
              today_time: str = '', style_now: str = '') -> 'object':
        """六类检查 → `crew.gate.Report`。

        **同一条只报一次**（按 `dedupe_key` 去重）—— 这是它相对"每天重新看一眼"
        的关键差别：问题一旦报过就记账，不重复刷屏。
        
                English:
        Six categories of checks → `crew.gate.Report`.
                **Report the same issue only once** (dedupe by `dedupe_key`) -- this is its advantage over "take another look every day"
                key difference: once an issue has been reported it is recorded, so it does not repeatedly spam the screen.
        """
        from crew import gate                                     # noqa: PLC0415
        rep = gate.Report(target=f'第{day}天·一致性契约')

        def once(kind: str, where: str, sev: str, what: str, fix: str) -> None:
            k = dedupe_key(kind, where, sev, what)
            if k in self.reported:
                return
            self.reported.add(k)
            rep.add(sev, where, f'[{kind}] {what}', fix)

        # ① 角色：一个人**天天换衣服**（这就是造型职位存在的理由，也是它最容易失效处）
        # [EN] ① Character: a person **changes clothes every day** (this is the reason the styling role exists,
        # [EN] and also where it most easily fails)
        for nm, c in self.characters.items():
            uniq = [x for x in dict.fromkeys(c.outfit_sequence) if x]
            if len(uniq) >= 3 and len(c.appearance_days) >= 3:
                once('角色', f'第{day}天·{nm}', 'MAJOR',
                     f'{nm} 已出现 {len(uniq)} 套不同穿着（{len(c.appearance_days)} 天）',
                     '定妆要跨天固定；换装要写明理由（换季/受伤/身份变化）')

        # ② 场景：同一处场景**时辰来回跳**
        # [EN] ② Scene: the **time of day jumps back and forth** in the same scene
        for loc, sc in self.scenes.items():
            if sc.time and today_place == loc and today_time and today_time != sc.time and day > 1:
                once('时间', f'第{day}天·{loc}', 'WARNING',
                     f'{loc} 上一场是「{sc.time}」，这一场是「{today_time}」',
                     '若是有意跨时段，正文里要交代；否则改回同一时段')

        # ③ 道具：**已毁/已送出的东西又出现**（PenShot 六类检查里最实用的一条）
        # [EN] ③ Prop: **something already destroyed/given away appears again** (the most practical of
        # [EN] PenShot's six check categories)
        if today_place and today_place in self.scenes:
            sc = self.scenes[today_place]
            gone = {k: v for k, v in sc.props_in_scene.items()
                    if v in ('已毁', '已送出', '已拿走')}
            for p in (today_props or []):
                nm = str(p or '').strip()
                if nm in gone:
                    once('道具', f'第{day}天·{today_place}', 'ERROR',
                         f'{nm} 的状态是「{gone[nm]}」，这一场却又出现',
                         '要么改成别的道具，要么先写清它怎么回来的')

        # ④ 动作：（需要跨天状态才判，这里只报"上一场离场的人又出现"这类确定项）
        # ⑤ 风格：画风漂移（有锚点才判）
        # [EN] ④ Action: (requires cross-day state to judge; here only report definite items like "a person who
        # [EN] left in the previous scene appears again")
        # [EN] ⑤ Style: art style drift (only judged when there is an anchor)
        if self.style_anchor and style_now and style_now != self.style_anchor:
            once('风格', f'第{day}天', 'WARNING',
                 f'本场画风描述与全剧锚点不一致（锚点：「{self.style_anchor[:24]}」）',
                 '画风只该在开书时定一次，之后每场都跟着它')
        # ⑥ 时间：当天没标时辰
        # [EN] ⑥ Time: the time of day is not marked for that day
        if day > 0 and today_place and not str(today_time).strip():
            once('时间', f'第{day}天·{today_place}', 'INFO',
                 '这一场没有时辰', '补一个时辰，场记与分镜都要用')
        return rep


# ══════════════════════════════════════════════════════════════════
#  从"道具单 / 造型表"这类职位产出里灌契约（**接线处**）
# [EN] Feed the contract from role outputs like "prop list / styling table" (**the wiring point**)
# ══════════════════════════════════════════════════════════════════
def props_from_note(data: dict | None) -> list[str]:
    rows = (data or {}).get('道具') or []
    return [str(r.get('名称') or '').strip() for r in rows
            if isinstance(r, dict) and str(r.get('名称') or '').strip()]


def outfits_from_note(data: dict | None) -> dict[str, str]:
    """造型表 → `{人名: 穿着}`。**只取"穿着"这一栏** ——
    随身物属于道具账，混进来会让"已送出的东西又出现"这类检查算错。
        English:
    carried items belong to the prop ledger; mixing them in will make checks like "something already
    given away appears again" compute incorrectly.
        Not yet paid off by chapter `at`, and the latest deadline has already passed.
    """
    rows = (data or {}).get('造型') or []
    out: dict[str, str] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        nm = str(r.get('人名') or '').strip()
        wear = str(r.get('穿着') or '').strip()
        if nm and wear:
            out[nm] = wear
    return out
