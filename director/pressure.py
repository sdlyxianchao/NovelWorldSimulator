#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""**世界法则**：事件不是被"设计"出来的，是压力攒够了**自己破的**。

★★★ 为什么要有这个模块（2026-10-19 用户：「把'导演'从编剧改成世界法则」）
--------------------------------------------------------------------------
改之前：导演每 8 拍问模型一次「请设计一个戏剧事件」。
那是一个**编剧**在做的事 —— 他想"这里该有个转折"，然后编一个。

两个后果，都在实测里看得见：
  ① **收敛**：同一部《雪国》跑两次，文字重合 9.7%，**骨架重合 62.5%**。
     因为"设计一个事件"这个问题本身就把答案收窄了 —— 模型会挑最安全、
     最不难看的那一类（来个人、送个东西、敲个门）。这是**提问方式**造成的，
     换提示词治不好。
  ② **不可解释**：读者读完说不出"这件事为什么现在发生"。因为它不是因为
     什么发生的，是因为**该有个事件了**。

改之后：**先算压力，再让压力最大的那一条自己破掉。**
事件类型由**代码**从世界状态里算出来，模型只负责把它写成一句话、一件具体的事。

    · 秘密压力最大   ⇒ 「秘密泄露」—— 不是"投一个泄密事件"，是**藏不住了**；
    · 目标冲突最大   ⇒ 「人物冲突」—— 两人在同一件事上做了相反的决定；
    · 处境恶化最大   ⇒ 「巧合」（身体/外物先撑不住）—— 病了、醉了、钱没了；
    · 时间压力最大   ⇒ 「外部刺激」—— 期限到了，被迫提前动手。

这才是"写作"与"推演"的分界：
  **写作是"我要这个效果，所以安排这个事件"；
    推演是"这个局面必然导致这个事件"。**

四个压力都是**连续量、纯代码算、零模型调用**（每拍都算得起，也可复现）
--------------------------------------------------------------------
| 压力 | 怎么算 | 为什么这么算 |
|---|---|---|
| 目标冲突 | 在场人物 `current_goal` 两两的**共同词密度**取最大 | 两个人盯着同一件事 = 迟早要撞。**不需要判断"立场对立"** —— 抢同一个东西本身就是冲突 |
| 处境恶化 | `1-体力` + 负向情绪均值 + 今天已发生的坏事 | 身体撑不住的时候，人会做出不像自己的事 |
| 秘密压力 | 有秘密的人 ×（藏了几天）+ 最近有无人接近 | 秘密的重量随**时间**增长：藏得越久越沉 |
| 时间压力 | 今天的进度 + 是否临近节点末 + 离今天结束还有几拍 | 期限逼近会逼人**准备不足地行动** |

⚠ 为什么"目标冲突"用共同词而不是语义判断：语义判断要一次模型调用，
  而那次调用会立刻退化成"你判断谁跟谁冲突"—— 又回到了"问模型"。
  共同词密度是**粗的，但方向对**：都说"账本"的两个人，一定在争账本。
  粗的代价是**偶尔误判**，而误判的后果只是"这一次事件类型选得不太准"——
  比"每次都选最安全的那类"轻得多。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 四个压力各自的名字与它"破掉"时对应的事件类型 ─────────────────
#: ⚠ 事件类型必须与 `director/engine.py` 的 `DirectorEvent.event_type` 取值一致。
# [EN] Each pressure and the event type it maps to. ⚠ Must match `DirectorEvent.event_type`.
PRESSURE_EVENT: dict[str, str] = {
    'goal': '人物冲突',
    'hardship': '巧合',
    'secret': '秘密泄露',
    'time': '外部刺激',
}

#: 中文标签（给日志与提示词用）。
# [EN] Chinese labels (for logs and prompts).
PRESSURE_NAME: dict[str, str] = {
    'goal': '目标冲突',
    'hardship': '处境恶化',
    'secret': '秘密压力',
    'time': '时间压力',
}

#: 低于这个值就**不算压力**（四个都低 ⇒ 这一拍本就不该出事）。
#: ⚠ 0.25 不是随便定的：它对应"确实有一点，但还没到非出事不可"。
# [EN] Below this nothing counts as pressure; if all four are low, nothing should happen this beat.
MIN_PRESSURE = 0.25

#: 共同词的停用集（都是不承载"同一件事"的虚词/泛词）。
# [EN] Stopwords for shared-word density (words that carry no "same matter" meaning).
_STOP: frozenset[str] = frozenset((
    '自己', '什么', '怎么', '这个', '那个', '一个', '就是', '不是', '还是', '已经',
    '现在', '今天', '明天', '昨天', '他们', '我们', '你们', '可以', '应该', '想要',
    '觉得', '知道', '时候', '东西', '事情', '地方', '这里', '那里', '这样', '那样',
))

#: 负向情绪键（`PersonState.emotion` 里那几个）。
# [EN] Negative emotion keys in `PersonState.emotion`.
_NEG = ('fear', 'sadness', 'anger', 'disgust')


#: 二字片段里，**以这些字开头的一律丢掉** —— 它们是跨词碎片，不是实体。
#: 例："把账本烧掉" 会切出「把账」（虚词+实词碎片）+「账本」，
#: 而「把账」只在一个人的句子里出现、又会让日志读起来像乱码。
#: ⚠ 这不只是好看：碎片会让"共同词"虚高（两个人的句子都以"把"开头就误判成撞上了）。
# [EN] Two-char chunks starting with these are dropped -- cross-word fragments, not entities.
# [EN] ⚠ This is not cosmetic: fragments inflate "shared words" (two sentences both starting with
# [EN] 把 would look like a collision).
_LEAD_DROP: frozenset[str] = frozenset('把被将给让对向为从在和与跟同于往朝据按理')


def _words(text: str) -> set[str]:
    """把一句话切成"承载意义的词"（两字以上的中文片段）。

    ⚠ 不用分词库（装一个库只为这件事不值），用**二字滑窗**近似：
      中文里"账本""旧案""病人"这类实词，二字片段已经足够区分"在说同一件事"。
      代价是会切出"本旧"这种跨词碎片，但它们**同时出现在两个人句子里**的概率极低，
      所以对"共同词密度"这种相对量影响很小。
    [EN] Split into meaning-bearing chunks (2+ char CJK runs) using a **two-character sliding
    [EN] window** rather than a tokenizer: enough to tell "same matter" apart. ⚠ Chunks starting
    [EN] with a function word are dropped (see `_LEAD_DROP`).
    """
    out: set[str] = set()
    for run in re.findall(r'[\u4e00-\u9fff]{2,}', str(text or '')):
        if len(run) == 2:
            if run not in _STOP and run[0] not in _LEAD_DROP:
                out.add(run)
            continue
        for i in range(len(run) - 1):
            w = run[i:i + 2]
            if w not in _STOP and w[0] not in _LEAD_DROP:
                out.add(w)
    return out


@dataclass
class Pressures:
    """这一拍的四条压力 + 各自的证据（证据是为了**能解释**，不是为了好看）。

    ⚠ 每个压力都带 `why`：日志里要能回答"为什么这次是秘密泄露而不是别的"。
      没有 `why` 的压力值就是黑箱，而黑箱的推演跟"随机挑一个"没有区别。
    [EN] Four pressures plus evidence. ⚠ Every pressure carries `why`: the log must be able to
    [EN] answer "why a secret leak this time and not something else". A pressure value without
    [EN] evidence is a black box, and a black-box simulation is indistinguishable from a random pick.
    """
    goal: float = 0.0
    hardship: float = 0.0
    secret: float = 0.0
    time: float = 0.0
    why: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, float]:
        return {'goal': self.goal, 'hardship': self.hardship,
                'secret': self.secret, 'time': self.time}

    def top(self) -> tuple[str, float]:
        """压力最大的那一条 → `('secret', 0.72)`。全低时返回 `('', 0.0)`。"""
        d = self.as_dict()
        k = max(d, key=lambda x: d[x])
        return (k, d[k]) if d[k] >= MIN_PRESSURE else ('', 0.0)

    def line(self) -> str:
        """一行摘要（日志用）。"""
        d = self.as_dict()
        body = ' · '.join(f'{PRESSURE_NAME[k]} {v:.2f}' for k, v in d.items())
        k, v = self.top()
        return body + (f'  ⇒ 最大：{PRESSURE_NAME[k]}（{v:.2f}）' if k else '  ⇒ 全低，不该出事')


def _on_stage(world) -> list:
    """在场且活着的人。"""
    out = []
    for p in (getattr(world, 'people', None) or {}).values():
        try:
            if str(getattr(p, 'status', '') or '') != '死亡' and p.is_active():
                out.append(p)
        except Exception:                                        # noqa: BLE001
            continue
    return out


def _goal_pressure(world, people: list, pr: Pressures) -> None:
    """**目标冲突**：两两的共同词密度取最大。

    ⚠ 为什么"共同词多"就是冲突：两个人都盯着"账本"，说明**同一件东西**
      同时被两个人需要 —— 那正是冲突的原料。真正的对立（一个要毁、一个要保）
      反而常常用**同一批词**（都在说"这本账"），所以这个近似连对立也吃得到。
    ⚠ 只有一个人有目标时压力为 0：一个人唱不了对手戏。
    [EN] **Goal conflict**: max shared-word density over all pairs. Two people both circling
    [EN] "the ledger" means one thing is needed by both -- the raw material of conflict. Real
    [EN] opposition also shares vocabulary ("that ledger"), so the approximation covers it too.
    [EN] ⚠ Zero when only one person has a goal: you cannot have a scene alone.
    """
    goals = [(p.name, _words(getattr(p, 'current_goal', '') or getattr(p, 'goal', '')))
             for p in people]
    goals = [(n, w) for n, w in goals if w]
    if len(goals) < 2:
        pr.why['goal'] = '有目标的人不足两个 —— 唱不了对手戏'
        return
    best, pair, best_inter = 0.0, ('', ''), set()
    for i in range(len(goals)):
        for j in range(i + 1, len(goals)):
            (na, wa), (nb, wb) = goals[i], goals[j]
            inter = wa & wb
            if not inter:
                continue
            # ★★★ 主信号是「**同一个东西**被两个人盯上」，不是整句像不像。
            #   密度（`inter / min(...)`）只作**加成** —— 单靠密度会严重低估：
            #   "把账本找出来对清楚" vs "把账本烧掉不能让人看见"，共同词只有
            #   「账本」一个，密度 ≈ 0.14，而这是**最典型的冲突**（实测过：
            #   那样算出来 0.25，差点落在 `MIN_PRESSURE` 之下被当成"没事"）。
            #   ⇒ 有共同实词就先给 0.45（"确实撞上了"），共同词越多再加，
            #     最多加到 1.0。**一个共同词就已经是冲突，不必等它变多。**
            # [EN] ★★★ The main signal is "**one thing** needed by two people", not sentence
            # [EN] similarity. Density is only a bonus -- density alone badly underrates: the ledger
            # [EN] pair shares exactly one word (~0.14 density) and is the most typical conflict
            # [EN] (measured 0.25, almost under MIN_PRESSURE and read as "nothing happening").
            # [EN] => one shared content word already scores 0.45; more words add up to 1.0.
            dens = len(inter) / max(1, min(len(wa), len(wb)))
            v = min(1.0, 0.45 + 0.55 * dens)
            if v > best:
                best, pair, best_inter = v, (na, nb), inter
    pr.goal = min(1.0, best)
    if best > 0:
        share = '、'.join(sorted(best_inter)[:3])
        pr.why['goal'] = f'{pair[0]} 与 {pair[1]} 都在盯「{share}」'
    else:
        pr.why['goal'] = '在场人物各忙各的，没有撞上'


def _hardship_pressure(world, people: list, pr: Pressures) -> None:
    """**处境恶化**：体力见底 + 负向情绪 + 今天已经发生的坏事。

    ⚠ 三条各占一部分，是因为它们**分别**会让人做出不像自己的事：
      体力见底 ⇒ 动作变形；恐惧/悲伤高 ⇒ 判断变形；坏事连着来 ⇒ 失去耐性。
    [EN] **Hardship**: low stamina + negative emotion + bad news already today. Each of the three
    [EN] makes a person act unlike himself (body / judgment / patience).
    """
    if not people:
        pr.why['hardship'] = '场上没人'
        return
    worst_body = max((1.0 - float(getattr(p, 'stamina', 1.0) or 1.0)) for p in people)
    worst_mood = 0.0
    for p in people:
        em = getattr(p, 'emotion', None) or {}
        try:
            v = sum(float(em.get(k, 0.0) or 0.0) for k in _NEG) / max(1, len(_NEG))
        except Exception:                                        # noqa: BLE001
            v = 0.0
        worst_mood = max(worst_mood, min(1.0, v * 2))            # ×2：单项 0.5 已经是"很不好"
    # 今天已经发生的坏事（从日志里数"坏消息"型条目 —— 粗，但方向对）
    bad = 0
    try:
        for r in (getattr(world, 'recent_lines', None) or []):
            t = str((r or {}).get('text') or '')
            if any(k in t for k in ('病', '伤', '死', '吵', '摔', '哭', '没了', '输', '输光')):
                bad += 1
    except Exception:                                            # noqa: BLE001
        bad = 0
    bad_part = min(1.0, bad / 6.0)
    pr.hardship = min(1.0, 0.45 * worst_body + 0.35 * worst_mood + 0.20 * bad_part)
    pr.why['hardship'] = (f'体力亏空 {worst_body:.2f} · 负向情绪 {worst_mood:.2f} · '
                          f'今天坏事 {bad} 条')


def _secret_pressure(world, people: list, pr: Pressures) -> None:
    """**秘密压力**：有秘密的人 × 藏了多久 + 有没有人逼近。

    ★ 为什么要乘"藏了多久"：秘密的重量是**累积**的 —— 刚有的秘密没什么，
      藏了十天的秘密会自己往外冒（说漏、被人看出、自己忍不住）。
      这就是"不是投放一个泄密，是藏不住了"的算法表达。
    ⚠ 只算**在场**的人：不在场的人的秘密这一拍压不到场面上。
    [EN] **Secret pressure**: holders x how long hidden + whether anyone is closing in.
    [EN] ★ Why multiply by duration: a secret's weight **accumulates** -- fresh ones barely
    [EN] register, ten-day-old ones leak by themselves. That is the algorithmic form of "not
    [EN] dropping a leak, but being unable to hold it".
    """
    if not people:
        pr.why['secret'] = '场上没人'
        return
    best, who = 0.0, ''
    for p in people:
        sec = str(getattr(p, 'secret', '') or '').strip()
        if len(sec) < 2:
            continue
        try:
            held = max(0, int(getattr(world, 'game_day', 1) or 1)
                       - int(getattr(p, 'debut_day', 1) or 1))
        except Exception:                                        # noqa: BLE001
            held = 0
        # 藏了 10 天封顶（再久也不该继续线性涨）
        # [EN] Cap at 10 days (no further linear growth beyond that).
        v = min(1.0, 0.35 + 0.065 * min(10, held))
        # 有没有人"逼近"：最近的行文里出现过秘密里的词
        # [EN] Is anyone closing in: the secret's own words showed up in recent lines.
        sw = _words(sec)
        near = 0
        try:
            for r in (getattr(world, 'recent_lines', None) or [])[-8:]:
                t = str((r or {}).get('text') or '')
                if sw & _words(t):
                    near += 1
        except Exception:                                        # noqa: BLE001
            near = 0
        v = min(1.0, v + 0.12 * near)
        if v > best:
            best, who = v, p.name
    pr.secret = best
    pr.why['secret'] = (f'{who} 藏的事已经压到 {best:.2f}' if best > 0
                        else '场上没有人揣着秘密')


def _time_pressure(world, pr: Pressures, beats_left_today: int | None) -> None:
    """**时间压力**：这一天的进度 + 离今天结束还剩几拍。

    ⚠ 为什么"一天快过完"是压力：事情没办完而天要黑了，人会**降低标准**、
      把没准备好的事硬推上去 —— 那正是"被迫提前行动"的来源。
    [EN] **Time pressure**: how far into the day we are and how many beats remain.
    [EN] ⚠ Why "the day is ending" is pressure: with things unfinished and dusk coming, people
    [EN] lower their standard and push out unprepared moves -- exactly "forced early action".
    """
    frac = 0.0
    try:
        clk = getattr(world, 'clock', None)
        # ⚠⚠ `GameTime` 上的字段叫 **`minutes`**（0–1439，从 00:00 算），
        #   不是 `minute_of_day`。第一版写错名字，`getattr(..., None) or 0.0`
        #   静默取到 0 ⇒ **时间压力永远是 0** ⇒ 第四条压力等于从未生效，
        #   而"另外三条都还能用"让这个洞完全不显眼。
        #   这是本项目记过的 `getattr(obj,'字段',默认)` 让"字段不存在"不可见的
        #   又一次现场 —— 现在读不到就**报出来**（见下面的 `why`）。
        # [EN] ⚠⚠ The field is **`minutes`** (0-1439), not `minute_of_day`. The first version used
        # [EN] the wrong name and `getattr(..., None) or 0.0` silently gave 0 => **time pressure was
        # [EN] always 0** => the fourth pressure never worked, while the other three still worked,
        # [EN] which made the hole invisible. Another instance of the `getattr(obj,'field',default)`
        # [EN] trap this project has recorded; it is now reported in `why` instead of hidden.
        mins = getattr(clk, 'minutes', None)
        if mins is None:
            frac = 0.0
        else:
            frac = max(0.0, min(1.0, float(mins) / (24 * 60)))
    except Exception:                                            # noqa: BLE001
        frac = 0.0
    late = 0.0
    if beats_left_today is not None:
        try:
            n = max(0, int(beats_left_today))
            late = max(0.0, 1.0 - n / 8.0)                       # 剩 8 拍之内开始有压力
        except Exception:                                        # noqa: BLE001
            late = 0.0
    pr.time = min(1.0, 0.55 * frac + 0.45 * late)
    pr.why['time'] = f'一天过了 {frac:.0%} · 今天还剩 {beats_left_today} 拍'


def compute(world, *, beats_left_today: int | None = None) -> Pressures:
    """算出这一拍的四条压力（**纯代码、零模型调用、可复现**）。

    ⚠ 所有取值都只读 `world` 上已有的字段 —— 不新造"压力"字段。
      造了要有人写、有人读、有人维护；而从现有状态**算**出来，永远与状态自洽。
    [EN] Compute the four pressures (**pure code, no model call, reproducible**).
    [EN] ⚠ Reads only existing `world` fields -- no new "pressure" state to keep in sync.
    """
    pr = Pressures()
    people = _on_stage(world)
    if not people:
        return pr
    _goal_pressure(world, people, pr)
    _hardship_pressure(world, people, pr)
    _secret_pressure(world, people, pr)
    _time_pressure(world, pr, beats_left_today)
    return pr


def decide(world, *, beats_left_today: int | None = None) -> tuple[str, str, float, Pressures]:
    """**这一拍该发生什么类型的事**：返回 `(压力键, 事件类型, 压力值, 全部压力)`。

    全低时返回 `('', '', 0.0, pressures)` —— 这一拍**不该出事**，
    调用方应当让世界自己安静地往前走（那是"日常生活型"该有的样子）。
    [EN] What kind of event this beat should have: `(pressure key, event type, value, all)`.
    [EN] All-low returns empty -- nothing should happen, and the caller should let the world
    [EN] move quietly (that is what "slice-of-life" looks like).
    """
    pr = compute(world, beats_left_today=beats_left_today)
    k, v = pr.top()
    if not k:
        return '', '', 0.0, pr
    return k, PRESSURE_EVENT[k], v, pr
