# -*- coding: utf-8 -*-
"""**分层创作（atelier）** —— 先总后分，每层交代"变了什么"，交代不出就不许往下走。

用户 2026-10-21
--------------
「为何小说作家 / 剧作家 / 导演等创作三人组不能够根据已经有的故事先生成一个大的
  故事框架，然后再补充一些小的细节，然后再补充人物细节以及别的细节，一点点最终
  变成小说？就是把打草稿、审核剧情、单独修改草稿、最终确认、补充细节等等真实世界
  文学创作的流程引入进来，按照总分结构、思维导图等等真实工具来优化创作……
  在这个过程中，每完成一个步骤都确认没有剧情空转了、逻辑错误等等剧情的问题，
  没问题了再继续。等到导出的时候也是这个过程：先从推演里抽取总体框架，
  然后按照前面说的这个步骤进行，唯一的区别是所有的细节信息都来自这一次推演。」

★★★ 要解决的根本问题
--------------------
此前的做法是「**先写完整篇，再回头挑毛病**」。三个绕不过去的后果：

1. **空转只能事后发现**。望江楼连跑三版都在原地打转（问白绫 → 挡回去 → 再问），
   而八项指标全 0 —— 空转不是"某一句写坏了"，是**整章没有让任何事情发生变化**，
   逐句尺子天生看不见。
2. **毛病修不起**。写完再改，改一处碰坏另一处（实测修"太碎"让"太长"从 0 涨到 2）。
3. **改不动结构**。文字层只能换说法，换不了"这一章到底该发生什么"。

★★★ 第一原则：变化账本
----------------------
每一层都必须产出一份 `Change` 账本：**谁 · 关于什么 · 从哪个状态到哪个状态**。
说不出"什么变了"，这一层就不许往下走。空转于是变成一句可数的话：

    这一层的账本签名，与上一章/上一拍**逐字相同** ⇒ 没有推进。

★★★ 为什么账本必须是**闭集结构**，不许自由文本
--------------------------------------------
第一版把 `after` 写成自由文本（`他知道井里有白绫`），实测**当场被同义词击穿**：
三章分别写「他知道 / 他晓得 / 他明白井里有白绫」，签名各不相同 ⇒ 三章打转
却一条都没报。这与上一轮 `_goal_key` 踩的是同一个坑：
**凡可数指标吃模型写的自由文本，换个说法就归零。**

所以账本只许填：
    kind   ∈ 信息 / 关系 / 处境 / 物
    subject∈ 人物表里的人
    obj    ∈ 推演里真出现过的东西（props / 事件文本里出现过的词）
    before/after ∈ **该 kind 的状态闭集**（见 `STATE_SETS`）
签名 = `kind|subject|obj|after` —— 措辞再也无处可逃。

English
-------
**Layered composition (atelier)** -- outline first, details later; every layer declares what
changed, and no layer proceeds without one.

The old flow wrote everything, then hunted for flaws: stalls were only visible after the fact
(text metrics cannot see "nothing happened"), repairs broke other dimensions, and structure was
unreachable from prose.

First principle: a `Change` ledger -- *who / about what / from which state to which state*. A
stall is one countable sentence: this ledger signature is identical to the previous one.

Why the ledger must be a **closed-vocabulary structure**: the first version used free text
(`he learns there is a white silk in the well`), and synonyms broke it immediately -- three
chapters said `知道 / 晓得 / 明白`, signatures all differed, and three stalled chapters passed
clean. Same trap as `_goal_key`: any countable metric fed free text resets when re-worded.

分层（自顶向下，每层过闸）
--------------------------
    L0 骨架   全书分幕分章 + 每章"推进什么" + 事件分配            ← 总
       ↓ 闸：事件全覆盖 / 无凭空事件 / 时序单调 / 每章有变化 / 章间不重复
    L1 章纲   每章节拍（谁·要什么·被什么挡住·从哪到哪）            ← 分（导图一层）
       ↓ 闸：每拍有变化 / 相邻拍不重复 / 状态不许倒退 / 在场人合法 / 拍覆盖事件
    L2 草稿   把节拍写成正文
       ↓ 闸：每拍必须**引原句自证落点** / 不许新增专名 / 不许泄漏事件编号
    L3 细节   补人物细节、感官、道具 —— **只许改质地，不许改事实**
       ↓ 闸：台词数 / 字数 0.85~1.45 / 句子数不暴涨
    定稿

每层的闸都是**确定性代码**（`gates_*`），模型只负责写。闸不过就带"哪条不过、
原句是什么"重写该层（最多 N 轮，用 `reflexion` 那套有界记忆）。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = [
    'Change', 'Beat', 'Chapter', 'Skeleton', 'Source', 'Problem',
    'LAYERS', 'KINDS', 'STATE_SETS', 'SIG_EMPTY', 'SIG_MAX',
    'signature', 'ledger_signatures', 'advanced', 'stalled_pairs',
    'duplicate_signatures', 'state_rank', 'regressions',
    'gates_l0', 'gates_l1', 'gates_l2', 'gates_l3', 'gate_all',
    'walk', 'tree_text', 'flat_beats', 'coverage', 'obj_vocab',
    'load', 'dump', '_in_source',
]

#: 四层 + 定稿。顺序**不许改**：闸依赖"上一层已经过"。
LAYERS = ('L0', 'L1', 'L2', 'L3')

#: 变化种类。**只有四个** —— 开放字段会被用来发明新种类绕开重复检查。
KINDS = ('信息', '关系', '处境', '物')

#: 每种 kind 的**状态闭集**（有序：越往后越"往前走了"）。
#: 只许从这里选，不许自己造词 —— 这是账本抗同义词的唯一保证。
STATE_SETS = {
    '信息': ('不知', '疑', '知', '确证'),
    '关系': ('疏', '试', '逼', '破'),
    '处境': ('安', '扰', '危', '失'),
    '物': ('在', '移', '失', '毁'),
}

#: 空白签名 —— 表示"这一格什么都没变"。
SIG_EMPTY = ''

#: 同一签名最多出现几次（1 = 埋伏笔，2 = 回收，3 = 空转）。
SIG_MAX = 2


# ══════════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════════

@dataclass
class Change:
    """**一个变化** —— 整层的核心单位，不是文字，是"哪一格从哪挪到哪"。

    `subject` 是谁，`obj` 是关于什么，`before/after` 是状态闭集里的两个值。
    `before == after` ⇒ 这一拍什么都没发生（空转）。

    `reversal=True` 表示这是**有意的反转**（"他刚知道，又被推翻了"）。
    反转不报"倒退"，但仍然计入签名 —— 反转两遍就是空转。
    """
    kind: str = ''
    subject: str = ''
    obj: str = ''
    before: str = ''
    after: str = ''
    cause: str = ''               # 由哪件事引起（事件 id 或动作）
    tick: str = ''
    reversal: bool = False

    def empty(self) -> bool:
        return not str(self.after or '').strip() or \
            str(self.before or '').strip() == str(self.after or '').strip()

    def one_line(self) -> str:
        r = '（反转）' if self.reversal else ''
        return f'[{self.kind}] {self.subject}·{self.obj}：{self.before}→{self.after}{r}'


@dataclass
class Beat:
    """L1 的最小单位：谁、要什么、被什么挡住、最后哪一格变了。"""
    id: str
    who: list[str] = field(default_factory=list)
    want: str = ''
    obstacle: str = ''
    change: Change = field(default_factory=Change)
    events: list[str] = field(default_factory=list)
    #: **这一拍在正文里的原句**（L2 写完由模型自证，代码只验它真的在正文里）。
    #: ★ 这是"落点"唯一防伪的查法：编出来的引文对不上正文。
    lands: str = ''


@dataclass
class Chapter:
    """L0 的节点 = 思维导图的一层。"""
    idx: int
    title: str = ''
    act: str = '承'               # 起 / 承 / 转 / 合
    spine: str = ''               # 这一章推进主线哪一句
    place: str = ''
    present: list[str] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    beats: list[Beat] = field(default_factory=list)
    draft: str = ''               # L2 产物
    final: str = ''               # L3 产物

    def beats_change(self) -> list[Change]:
        return [b.change for b in self.beats]


@dataclass
class Skeleton:
    """L0 全书骨架。**这是"总"，后面三层都是它的展开。**"""
    logline: str = ''
    spine: list[str] = field(default_factory=list)
    cast: dict[str, str] = field(default_factory=dict)
    props: list[str] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)

    def chapter(self, idx: int) -> Chapter | None:
        for c in self.chapters:
            if int(c.idx) == int(idx):
                return c
        return None


@dataclass
class Source:
    """这一次推演的事实底账。**所有细节只能来自这里**（用户的要求）。"""
    title: str = ''
    logline: str = ''
    cast: dict[str, str] = field(default_factory=dict)
    #: [{id, text, tick, who}]  —— `event` 是唯一"真的发生了"的东西
    events: list[dict] = field(default_factory=list)
    #: [{tick, place, present}]  —— 场景切换，给"空间"与"在场人"
    scenes: list[dict] = field(default_factory=list)
    #: [{who, text}]  —— 真实说过的台词（L2/L3 可以引用，不许被改）
    lines: list[dict] = field(default_factory=list)
    #: 每天的过程稿（给模型当素材，不当结构）
    days: list[dict] = field(default_factory=list)
    #: 主题（作品名 / 一句话），用于提示词
    genre: str = ''
    era: str = ''

    @classmethod
    def from_run(cls, run, *, days: dict | None = None,
                 transcript: list[dict] | None = None) -> 'Source':
        """从运行目录抽事实。**只抽事实，不抽结构** —— 结构由 L0 生成。"""
        src = cls()
        src.title = _run_field(run, ('title', 'name')) or ''
        rows = list(transcript or [])
        if not rows:
            rows = _read_transcript(run)
        ev, sc, li = [], [], []
        for r in rows:
            if not isinstance(r, dict):
                continue
            kind = str(r.get('kind') or '')
            text = str(r.get('text') or '').strip()
            if not text:
                continue
            tick = str(r.get('t') or '')
            if kind == 'event':
                ev.append({'id': f'E{len(ev) + 1}', 'text': text,
                           'tick': tick, 'who': str(r.get('who') or '')})
            elif kind == 'scene':
                sc.append({'tick': tick, 'place': text,
                           'present': [str(x) for x in (r.get('who') or [])]})
            elif kind == 'dialogue':
                li.append({'who': str(r.get('who') or ''), 'text': text,
                           'tick': tick})
        src.events, src.scenes, src.lines = ev, sc, li
        # ★★★ 2026-10-21：**只报了个到的群演，不进事实底账**（用户报"群众演员出现没道理"）。
        #   判据是**可删除性**：这个称呼在整份台本里只出现过那一次 ⇒ 删掉读者什么都没丢，
        #   那它就不是一件事，只是一声门响。后文有人提过他的，一条都不动
        #   （否则后文就成了凭空出现的人）。
        #   ⚠ 放在 `Source` 这一层而不是提示词里：L0~L3 的事实只能来自 `Source`，
        #     在源头摘掉，下游就没有机会"照抄一个不该出现的人"。
        # [EN] ★★★ 2026-10-21: **extras who only reported in do not enter the fact ledger** (the
        # [EN] user reported "extras appear for no reason"). Criterion is **deletability**: if the
        # [EN] appellation appears exactly once in the whole transcript, deleting it loses nothing
        # [EN] for the reader -- it was not an event, just a knock. Rows where anyone mentions him
        # [EN] later are left untouched (otherwise a person would appear out of nowhere).
        # [EN] ⚠ Placed at the `Source` layer rather than in the prompt: L0~L3 facts may only come
        # [EN] from `Source`, so removing it at the source means downstream never gets a chance to
        # [EN] "copy a person who should not be there".
        try:
            from world import crowd as _crowd
            src.events, _n_orphan = _crowd.drop_orphan_casts(src.events, rows)
        except Exception:                                        # noqa: BLE001
            _n_orphan = 0
        src.days = [{'day': int(d), 'text': str(t or '')}
                    for d, t in (days or {}).items()]
        src.logline = _guess_logline(src)
        src.cast = _guess_cast(src)
        return src


@dataclass
class Problem:
    """闸报出的一条问题。**必须带 `fix`** —— 只报"不对"的审计没人看。"""
    layer: str
    code: str
    detail: str
    fix: str = ''
    where: str = ''

    def one_line(self) -> str:
        w = f'（{self.where}）' if self.where else ''
        return f'[{self.layer}/{self.code}] {self.detail}{w}'


# ══════════════════════════════════════════════════════════════════
# 变化账本：空转的唯一判据
# ══════════════════════════════════════════════════════════════════

def _norm(text: str) -> str:
    """归一：只留汉字与字母数字，去标点空白。

    ⚠ 必须归一：`白绫` 与 `白绫。` 是同一个对象，否则换个标点就骗过比较
      （`director/stall.py` 已踩过一次）。
    """
    return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', str(text or ''))


def signature(ch: Change) -> str:
    """一个变化的签名 —— **四个槽全来自闭集**，措辞无处可逃。

    ★ 为什么 `cause` 不进签名：同一件事可以由不同原因引起，那是"换了个由头"。
    ★ 为什么 `before` 不进签名：`未知→知` 与 `疑→知` 都是"知道了"，
      放进签名会让"换个起点"变成"新变化"。
    """
    if ch is None or not str(ch.after or '').strip():
        return SIG_EMPTY
    return f'{str(ch.kind).strip()}|{_norm(ch.subject)}|{_norm(ch.obj)}|{str(ch.after).strip()}'


def _as_change(x) -> Change | None:
    if isinstance(x, Change):
        return x
    if isinstance(x, Beat):
        return x.change
    if isinstance(x, Chapter):
        return _pseudo_ch(x)
    return None


def ledger_signatures(items) -> list[str]:
    """一组变化（章节 / 节拍 / 层）的签名序列，空签名**去掉**。"""
    out = []
    for x in items or ():
        ch = _as_change(x)
        s = signature(ch) if ch is not None else SIG_EMPTY
        if s:
            out.append(s)
    return out


def advanced(before_items, after_items) -> bool:
    """后面那一层，相比前面那一层，**有没有出现新的签名**。

    ★ 用集合差，不用"长度变多"：上一层 3 条、这一层还是那 3 条（顺序换了）
      ⇒ 没推进；上一层 3 条、这一层 2 条但多一条新的 ⇒ 推进了（压缩也算动）。
    """
    a = set(ledger_signatures(before_items))
    b = set(ledger_signatures(after_items))
    return bool(b - a)


def stalled_pairs(items) -> list[tuple[int, int, str]]:
    """相邻两项签名完全相同 ⇒ (i, j, 签名)。这是"空转"最直接的形态。"""
    sigs = ledger_signatures(items)
    out = []
    for i in range(len(sigs) - 1):
        if sigs[i] == sigs[i + 1]:
            out.append((i, i + 1, sigs[i]))
    return out


def duplicate_signatures(items) -> dict[str, list[int]]:
    """同一签名出现 ≥2 次的全部位置。

    ★ 允许复现，但**不许超过 2 次**：第一次埋伏笔、第二次回收，第三次就是打转。
    """
    seen: dict[str, list[int]] = {}
    for i, s in enumerate(ledger_signatures(items)):
        seen.setdefault(s, []).append(i)
    return {k: v for k, v in seen.items() if len(v) >= 2}


def state_rank(kind: str, state: str) -> int:
    """状态在闭集里的序号；不在闭集里返回 -1。"""
    seq = STATE_SETS.get(str(kind or '').strip())
    if not seq:
        return -1
    try:
        return seq.index(str(state or '').strip())
    except ValueError:
        return -1


def regressions(items) -> list[tuple[int, int, str]]:
    """同一 (kind, subject, obj) 上**状态倒退**的地方 ⇒ (i, j, 说明)。

    ★ 倒退不一定是错（"他刚知道又被推翻"是好戏），所以要看 `reversal`：
      标了 reversal 就跳过；没标就是逻辑倒了 —— **人物不可能忘掉刚知道的事**。
    """
    last: dict[str, tuple[int, int]] = {}
    out = []
    for i, x in enumerate(items or ()):
        ch = _as_change(x)
        if ch is None or ch.empty():
            continue
        key = f'{ch.kind}|{_norm(ch.subject)}|{_norm(ch.obj)}'
        r = state_rank(ch.kind, ch.after)
        if key in last:
            j, prev = last[key]
            if r >= 0 and prev >= 0 and r < prev and not ch.reversal:
                out.append((j, i, f'{ch.subject}·{ch.obj} 从 '
                                   f'{STATE_SETS[ch.kind][prev]} 退回 '
                                   f'{STATE_SETS[ch.kind][r]}'))
        last[key] = (i, r)
    return out


def _in_source(word: str, src: Source, sk: Skeleton | None = None) -> bool:
    """这个词在**本次推演的全部材料**里出现过吗（子串匹配，口径宽松）。"""
    w = _norm(word)
    if not w:
        return True
    parts = [str(e.get('text') or '') for e in src.events]
    parts += [str(s.get('place') or '') for s in src.scenes]
    parts += [str(x.get('text') or '') for x in src.lines]
    parts += [str(d.get('text') or '') for d in src.days]
    if sk is not None:
        parts += [str(p) for p in (sk.props or ())]
        parts += list(sk.cast or {})
    parts += list(src.cast or {})
    return w in _norm(''.join(parts))


def obj_vocab(src: Source, sk: Skeleton | None = None) -> set[str]:
    """**对象白名单**：推演里真出现过的东西。

    来源三处：骨架 props、事件文本、人物表。**不许凭空发明对象**
    （"他知道了自己的身世"里"身世"若推演没提过，就不许当变化对象）。
    """
    out: set[str] = set()
    for p in (sk.props if sk else ()) or ():
        if str(p).strip():
            out.add(_norm(p))
    for e in src.events:
        for w in re.findall(r'[\u4e00-\u9fff]{2,4}', str(e.get('text') or '')):
            out.add(w)
    for w in (sk.cast if sk else {}) or {}:
        out.add(_norm(w))
    for w in src.cast:
        out.add(_norm(w))
    out.discard('')
    return out


# ══════════════════════════════════════════════════════════════════
# 闸（全部纯函数，零模型调用）
# ══════════════════════════════════════════════════════════════════

def gates_l0(sk: Skeleton, src: Source) -> list[Problem]:
    """L0 骨架的闸：**结构层**的致命问题。"""
    out: list[Problem] = []
    if not sk.chapters:
        return [Problem('L0', 'empty', '骨架没有分章', '至少分 3 章', '')]

    used = {e for c in sk.chapters for e in (c.events or ())}
    used |= {e for c in sk.chapters for b in c.beats for e in (b.events or ())}
    known = {e['id'] for e in src.events}

    # ① 事件覆盖：推演里发生的事，要么被用，要么明确说明为什么不用
    missing = sorted(known - used)
    if missing:
        out.append(Problem(
            'L0', 'events_unused',
            f'推演里有 {len(missing)} 件事没被任何一章使用：{", ".join(missing[:6])}',
            '给每一件事安排一章；确实用不上的，合并进相邻章并说明为什么',
            'source.events'))

    # ② 事件不许凭空出现（编号必须是推演里真有的）
    ghost = sorted(used - known)
    if ghost:
        out.append(Problem(
            'L0', 'events_ghost',
            f'骨架引用了推演里不存在的事件：{", ".join(ghost[:6])}',
            '只许引用推演里真发生过的事 —— 这是"细节全部来自本次推演"的底线',
            ''))

    # ③ 时序：章节不许用更早的事件
    ticks = []
    for c in sk.chapters:
        t = _first_tick(c, src)
        if t and _is_num(t):
            ticks.append((int(c.idx), float(t)))
    for (i1, t1), (i2, t2) in zip(ticks, ticks[1:]):
        if t2 < t1:
            out.append(Problem('L0', 'time_back',
                               f'第 {i2} 章用的事件早于第 {i1} 章（{t2} < {t1}）',
                               '按推演发生的先后排章；要插叙就单独标出来，不许混在顺叙里',
                               f'第 {i2} 章'))

    # ④ 每章必须有变化
    for c in sk.chapters:
        if not ledger_signatures(c.changes):
            out.append(Problem('L0', 'no_change',
                               f'第 {c.idx} 章没有任何变化',
                               '写清这一章让哪一格变了（信息/关系/处境/物）',
                               f'第 {c.idx} 章'))

    # ⑤ 相邻章不许是同一个变化
    for a, b in zip(sk.chapters, sk.chapters[1:]):
        sa = set(ledger_signatures(a.changes))
        sb = set(ledger_signatures(b.changes))
        if sa and sa == sb:
            out.append(Problem(
                'L0', 'stall',
                f'第 {a.idx} 章与第 {b.idx} 章的变化**完全相同**（{sorted(sa)[:2]}）',
                '两章是同一件事写了两遍：删掉一章，或让后一章产生**新的**变化',
                f'第 {b.idx} 章'))

    # ⑥ 同一变化 ≥3 次 = 空转
    for sig, idxs in duplicate_signatures(sk.chapters).items():
        if len(idxs) > SIG_MAX:
            where = '、'.join(f'第 {sk.chapters[i].idx} 章' for i in idxs[:6])
            out.append(Problem('L0', 'repeat',
                               f'同一个变化出现了 {len(idxs)} 次（{sig}）：{where}',
                               f'最多留 2 次（伏笔 + 回收），第 3 次起必须换成新变化',
                               ''))

    # ⑦ 每章必须指向主线
    if sk.spine:
        for c in sk.chapters:
            if not str(c.spine or '').strip():
                out.append(Problem('L0', 'no_spine',
                                   f'第 {c.idx} 章没说它推进主线哪一句',
                                   '一句话写清这一章在主线上的位置', f'第 {c.idx} 章'))
    return out


def gates_l1(sk: Skeleton, src: Source, *, chapter: int | None = None) -> list[Problem]:
    """L1 章纲的闸：节拍层。"""
    out: list[Problem] = []
    chs = [c for c in sk.chapters if chapter is None or int(c.idx) == int(chapter)]
    vocab = obj_vocab(src, sk)
    cast = set(sk.cast) | {str(e.get('who') or '') for e in src.lines}
    cast.discard('')

    for c in chs:
        if not c.beats:
            out.append(Problem('L1', 'empty',
                               f'第 {c.idx} 章没有节拍', '至少拆 3 拍',
                               f'第 {c.idx} 章'))
            continue
        for b in c.beats:
            where = f'{c.idx}/{b.id}'
            # ① 变化必须有效、且四个槽都合法
            if signature(b.change) == SIG_EMPTY:
                out.append(Problem(
                    'L1', 'no_change',
                    f'第 {c.idx} 章第 {b.id} 拍没有有效变化'
                    f'（{b.change.before}→{b.change.after}）',
                    '写清这一拍之前是哪一格、之后是哪一格；两栏一样等于什么都没发生',
                    where))
            if str(b.change.kind or '') not in KINDS:
                out.append(Problem(
                    'L1', 'bad_kind',
                    f'第 {c.idx} 章第 {b.id} 拍的变化种类是「{b.change.kind}」',
                    f'只许用：{" / ".join(KINDS)}（开放字段会被用来绕开重复检查）',
                    where))
            for slot, val in (('before', b.change.before), ('after', b.change.after)):
                if val and state_rank(b.change.kind, val) < 0:
                    out.append(Problem(
                        'L1', 'bad_state',
                        f'第 {c.idx} 章第 {b.id} 拍的 {slot}=「{val}」不在闭集里',
                        f'{b.change.kind} 只许用：'
                        f'{" / ".join(STATE_SETS.get(b.change.kind, ()))}',
                        where))
            # ★ 判"推演里有没有这个东西"用**整份来源文本里搜一下**，
            #   不用 n-gram 词表：词表会把"茶账"这种从过程稿里来的正当对象漏掉
            #   （真跑实测：`茶账` 出自事件文本，却被词表判成"没出现过"）。
            #   宁可漏，不可误杀。
            # ★ 对象必须是**东西的名字**（壶/井/白绫/茶账），不是短语。
            #   真跑实测模型写成「井里沉下去的东西」—— 那不是物件，
            #   而且长短语永远搜不到，会把正常节拍卡死。先判长度，再判来源。
            _obj_len = len(_norm(b.change.obj))
            if _obj_len > 6:
                out.append(Problem(
                    'L1', 'obj_too_long',
                    f'第 {c.idx} 章第 {b.id} 拍的变化对象写成了一句话'
                    f'（「{b.change.obj}」，{_obj_len} 字）',
                    'obj 只填 2~4 字的**东西的名字**（壶 / 井 / 白绫 / 茶账）；'
                    '要表达"井里那东西"，就填「井」或「白绫」',
                    where))
            elif b.change.obj and not _in_source(b.change.obj, src, sk):
                out.append(Problem(
                    'L1', 'ghost_obj',
                    f'第 {c.idx} 章第 {b.id} 拍的变化对象「{b.change.obj}」'
                    '在推演里没出现过',
                    '变化对象必须是推演里真有的东西（物件/人物/事件里的词）—— '
                    '这是"细节全部来自本次推演"的底线',
                    where))
            # ② 在场人合法
            for w in (b.who or ()):
                # ⚠ 必须容忍"身份 + 名字"的写法（`送炭何二`、`布店朝奉`）：
                #   真跑实测模型会这么写，而 cast 里登记的是 `何二`。
                #   严格相等会把人名判成"不存在的人"，把正常节拍卡死。
                if cast and not any(w in cc or cc in w for cc in cast if cc):
                    out.append(Problem(
                        'L1', 'ghost_cast',
                        f'第 {c.idx} 章第 {b.id} 拍里出现了不存在的人「{w}」',
                        '只用推演里真出现过的人；要新角色先在骨架 cast 里登记',
                        where))
        # ③ 相邻拍不许同一变化
        for i, j, sig in stalled_pairs(c.beats):
            out.append(Problem(
                'L1', 'stall',
                f'第 {c.idx} 章第 {i + 1} 拍与第 {j + 1} 拍是同一个变化（{sig}）',
                '后一拍必须产生**新的**变化；只是换个人再问一遍不算',
                f'{c.idx}/{c.beats[j].id}'))
        # ④ 同一变化最多 2 次
        for sig, idxs in duplicate_signatures(c.beats).items():
            if len(idxs) > SIG_MAX:
                out.append(Problem('L1', 'repeat',
                                   f'第 {c.idx} 章「{sig}」出现 {len(idxs)} 次',
                                   '最多 2 次（伏笔 + 回收），第 3 次起换新变化',
                                   f'{c.idx}'))
        # ⑤ 状态不许倒退（人物不会忘掉刚知道的事）
        for j, i, why in regressions(c.beats):
            out.append(Problem(
                'L1', 'regress',
                f'第 {c.idx} 章第 {i + 1} 拍状态倒退：{why}',
                '确实是"刚知道又被推翻"，就标 reversal=True；否则改成往前走',
                f'{c.idx}/{c.beats[i].id}'))
        # ⑥ 节拍必须覆盖本章事件
        used = {e for b in c.beats for e in (b.events or ())}
        for e in (c.events or ()):
            if e not in used:
                out.append(Problem(
                    'L1', 'event_uncovered',
                    f'第 {c.idx} 章分配了事件 {e}，但没有哪一拍用它',
                    '给这一拍安排：这件事发生在谁身上、改变了哪一格',
                    f'{c.idx}/{e}'))
    return out


def gates_l2(sk: Skeleton, src: Source, *, chapter: int | None = None) -> list[Problem]:
    """L2 草稿的闸：只能验"覆盖"与"不许新增事实"。"""
    out: list[Problem] = []
    chs = [c for c in sk.chapters if chapter is None or int(c.idx) == int(chapter)]
    allowed = set(sk.cast) | {str(e.get('who') or '') for e in src.lines}
    allowed |= {str(p) for p in (sk.props or ())}
    allowed |= {c.place for c in sk.chapters if c.place}
    allowed.discard('')

    for c in chs:
        text = str(c.draft or '').strip()
        if not text:
            out.append(Problem('L2', 'empty', f'第 {c.idx} 章没有正文',
                               '按章纲写出来', f'第 {c.idx} 章'))
            continue
        body = _norm(text)
        for b in c.beats:
            # ① 每拍必须**引原句自证落点**，且引文真的在正文里
            quote = str(b.lands or '').strip()
            if not quote:
                out.append(Problem(
                    'L2', 'beat_missing',
                    f'第 {c.idx} 章第 {b.id} 拍没有自证落点'
                    f'（要写的：{b.want or b.change.one_line()}）',
                    '每拍必须从正文里**原样抄一句**（≥8 字）放进 lands；'
                    '抄不出来就是没写成',
                    f'{c.idx}/{b.id}'))
            elif len(_norm(quote)) < 8 or _norm(quote) not in body:
                out.append(Problem(
                    'L2', 'bad_quote',
                    f'第 {c.idx} 章第 {b.id} 拍的落点引文对不上正文：'
                    f'「{quote[:24]}」',
                    '必须逐字从这一章正文里抄；改写过的引文不算（编的引文一定对不上）',
                    f'{c.idx}/{b.id}'))
        # ② 不许新增骨架里没有的人名
        for name in _person_names(text, allowed):
            if allowed and name not in allowed and len(name) >= 2:
                out.append(Problem(
                    'L2', 'ghost_name',
                    f'第 {c.idx} 章正文出现了骨架里没有的名字「{name}」',
                    '所有细节只能来自本次推演；要新角色先在骨架里登记',
                    f'第 {c.idx} 章'))
        # ③ 不许**重演前章的开头**（2026-10-21 真跑实测的最大问题）
        #   骨架和账本都是对的（第 2 章该问"锁"），但正文为了"接上"，
        #   把第 1 章的取壶、见无影、井台滑又演了一遍 —— 读者看两遍开场。
        #   ★ 可数代理：本章开头 200 字里，若出现 ≥2 组**前章拍子**的
        #     「谁 + 什么」同句，就是重演（一组可能只是正常承接）。
        #   ⚠ 用词表外的判断一律交给 L1/L2 的账本，这里只查这一种形态。
        # [EN] Do not re-stage the previous chapter's opening. The skeleton and ledger were
        # [EN] right, yet the prose re-dramatised chapter 1's beats just to "connect" --
        # [EN] the reader sees the same opening twice. Countable proxy: in the first 200
        # [EN] characters, >= 2 previous chapters' (who + object) pairs in one sentence.
        if int(c.idx) > 1:
            head = text[:200]
            sents = [x for x in re.split(r'[。！？…\n]', head) if x.strip()]
            earlier = [b for p2 in sk.chapters if int(p2.idx) < int(c.idx)
                       for b in p2.beats]
            # ⚠ 不能靠人名判：第一人称正文里写的是"我"，不是"阿九"
            #   （第一版要求"谁 + 什么"同句，于是第一人称的稿子一条都抓不到）。
            #   改成"前章的**两个不同物件**都出现在开头" —— 一个物件可能只是承接，
            #   两个物件出现在 200 字里，基本就是把上一场又摆了一遍。
            hits = []
            for b in earlier:
                obj = str(b.change.obj or '').strip()
                if obj and obj in head:
                    for sen in sents:
                        if obj in sen:
                            hits.append(obj)
                            break
            if len(set(hits)) >= 2:
                out.append(Problem(
                    'L2', 'replay_open',
                    f'第 {c.idx} 章开头在重演前面演过的动作'
                    f'（{", ".join(sorted(set(hits))[:4])}）',
                    '本章从上一章停下的地方**接着写**；前面的事最多一句话带过，'
                    '不许再演一遍',
                    f'第 {c.idx} 章'))

        # ④ 事件编号不许裸奔
        if re.search(r'\bE\d+\b', text):
            out.append(Problem('L2', 'event_id_leak',
                               f'第 {c.idx} 章正文里出现了事件编号',
                               '编号是给程序看的，正文里不许出现',
                               f'第 {c.idx} 章'))
    return out


def gates_l3(sk: Skeleton, src: Source, *, chapter: int | None = None) -> list[Problem]:
    """L3 细节填充的闸：**只许改质地，不许改事实**。

    硬约束与 `crew/verdict.py` 同一套口径：台词不许变少、字数 0.85~1.45、
    句子数不许暴涨。细节填充最容易犯的就是这两条。
    """
    out: list[Problem] = []
    chs = [c for c in sk.chapters if chapter is None or int(c.idx) == int(chapter)]
    for c in chs:
        base, now = str(c.draft or ''), str(c.final or '')
        if not now.strip():
            out.append(Problem('L3', 'empty', f'第 {c.idx} 章没有定稿',
                               '在草稿上补细节，不要重写结构', f'第 {c.idx} 章'))
            continue
        qb, qn = _quote_count(base), _quote_count(now)
        if qn < qb:
            out.append(Problem('L3', 'speech_lost',
                               f'第 {c.idx} 章台词从 {qb} 句掉到 {qn} 句',
                               '补细节不许把台词并进叙述 —— 那是"没人替角色说话"',
                               f'第 {c.idx} 章'))
        zb, zn = _zh(base), _zh(now)
        if zb >= 200:
            ratio = zn / zb
            if ratio < 0.85 or ratio > 1.45:
                out.append(Problem(
                    'L3', 'length',
                    f'第 {c.idx} 章字数 {zb}→{zn}（{ratio:.2f}×）',
                    '补细节只在 0.85~1.45 倍之间；超了就是重写，不是补',
                    f'第 {c.idx} 章'))
        # ★ 补完细节还要**再验一次落点**：细节是重写的近亲，能把节拍写没。
        #   引文必须仍在定稿里 —— 这是"结构没被补细节冲掉"的硬证据。
        for b in c.beats:
            q = str(b.lands or '').strip()
            if q and _norm(q) not in _norm(now):
                out.append(Problem(
                    'L3', 'beat_lost',
                    f'第 {c.idx} 章第 {b.id} 拍的落点在定稿里消失了',
                    '补细节不许把这一拍写没；找不到就说明结构被冲掉了，'
                    '退回草稿重补', f'{c.idx}/{b.id}'))
        sb, sn = _sent_count(base), _sent_count(now)
        if sb and sn > sb * 2:
            out.append(Problem('L3', 'split',
                               f'第 {c.idx} 章句子数 {sb}→{sn}',
                               '补细节不是把句子拆碎；拆碎会让节奏崩',
                               f'第 {c.idx} 章'))
    return out


def gate_all(layer: str, sk: Skeleton, src: Source, **kw) -> list[Problem]:
    """按层调闸。**未知层直接报错**（不许静默放过）。"""
    fn = {'L0': gates_l0, 'L1': gates_l1, 'L2': gates_l2, 'L3': gates_l3}.get(layer)
    if fn is None:
        raise ValueError(f'未知层：{layer}（只认 {"/".join(LAYERS)}）')
    # ⚠ L0 是**全书**闸，没有 `chapter` 参数。统一入口必须把多余的 kw 去掉，
    #   否则调用方（`atelier_run.key_of`）每处都要写一遍 if —— 那种写法迟早漏一个。
    # [EN] L0 gates the whole book and takes no `chapter`; drop the extra kw here so callers
    # [EN] don't each need their own `if`.
    if layer == 'L0':
        kw.pop('chapter', None)
    return fn(sk, src, **kw)


# ══════════════════════════════════════════════════════════════════
# 思维导图：把骨架摊成一张可读的树
# ══════════════════════════════════════════════════════════════════

def walk(sk: Skeleton):
    """深度优先产出 `(深度, 类型, 对象, 父索引路径)` —— 总分结构的遍历器。

    ★ 为什么要有遍历器："每层过闸"听着像三条独立检查，其实是**树的每一层各一道**。
      没有统一遍历，就会出现"有的章查了、有的章漏了"。
    """
    for ci, c in enumerate(sk.chapters):
        yield 0, 'chapter', c, (ci,)
        for bi, b in enumerate(c.beats):
            yield 1, 'beat', b, (ci, bi)


def tree_text(sk: Skeleton, *, max_beats: int = 8) -> str:
    """把骨架渲染成缩进树 —— **这是给模型看的"思维导图"**。

    不用 markdown 表格：表格会被模型当成"资料"照抄，缩进树才会被当成"结构"。
    """
    if not sk.chapters:
        return '（空骨架）'
    L = []
    if sk.logline:
        L.append(f'主线：{sk.logline}')
    for s in sk.spine:
        L.append(f'  · {s}')
    for c in sk.chapters:
        head = f'第 {c.idx} 章〔{c.act}〕{c.title}'
        if c.place:
            head += f' · {c.place}'
        L.append(head)
        if c.spine:
            L.append(f'   └ 推进：{c.spine}')
        for ch in c.changes:
            L.append(f'   ├ 变化 {ch.one_line()}')
        for b in c.beats[:max_beats]:
            L.append(f'   ├ {b.id}　{b.want}｜挡：{b.obstacle}｜'
                     f'变：{b.change.before}→{b.change.after}'
                     f'（{b.change.subject}·{b.change.obj}）')
        if len(c.beats) > max_beats:
            L.append(f'   └ （另有 {len(c.beats) - max_beats} 拍）')
    return '\n'.join(L)


def flat_beats(sk: Skeleton) -> list[Beat]:
    return [b for c in sk.chapters for b in c.beats]


def coverage(sk: Skeleton, src: Source) -> dict:
    """覆盖统计：日志与判据都用它，**也是"细节全部来自推演"的证据**。"""
    used = {e for c in sk.chapters for e in (c.events or ())}
    used |= {e for c in sk.chapters for b in c.beats for e in (b.events or ())}
    known = {e['id'] for e in src.events}
    # ⚠ 两套计数**别混**：
    #   `changes` / `unique_changes` 是**章级代表**（每章压成一条）——判空转用；
    #   `changes_all` / `unique_all` 是**全部变化**（章级 + 拍级）——判"丰富度"用。
    #   第一版只有前者，于是"多加一拍、多一个变化"在键里看不出来，
    #   "问题一样多时选变化更丰富的"这条根本测不出来（D2 白测了一轮）。
    sigs = ledger_signatures(sk.chapters)
    sigs_all = list(sigs)
    for c in sk.chapters:
        sigs_all += [x for x in ledger_signatures(c.changes) if x]
        sigs_all += [x for x in ledger_signatures(c.beats) if x]
    return {
        'events_total': len(known),
        'events_used': len(known & used),
        'events_ghost': len(used - known),
        'chapters': len(sk.chapters),
        'beats': len(flat_beats(sk)),
        'changes': len(sigs),
        'unique_changes': len(set(sigs)),
        'changes_all': len(sigs_all),
        'unique_all': len(set(sigs_all)),
        'stall_pairs': len(stalled_pairs(sk.chapters)),
        'duplicate_sigs': len(duplicate_signatures(sk.chapters)),
        'regressions': len(regressions(sk.chapters)),
    }


# ══════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════

_PUNCT = re.compile(r'[\s\u3000，。、；：！？,.;:!?「」“”"\'（）()《》—…·]')


def _zh(text: str) -> int:
    return len([c for c in str(text or '') if '\u4e00' <= c <= '\u9fff'])


def _quote_count(text: str) -> int:
    return len(re.findall(r'“[^”]{2,}”|"[^"]{2,}"', str(text or '')))


def _sent_count(text: str) -> int:
    bare = re.sub(r'“[^”]*”|"[^"]*"', '', str(text or ''))
    return len([x for x in re.split(r'[。！？…]+', bare) if _zh(x) >= 2])


def _is_num(t: str) -> bool:
    try:
        float(t)
        return True
    except (TypeError, ValueError):
        return False


def _first_tick(c: Chapter, src: Source) -> str:
    m = {e['id']: str(e.get('tick') or '') for e in src.events}
    for e in (c.events or ()):
        if m.get(e):
            return m[e]
    for b in c.beats:
        for e in (b.events or ()):
            if m.get(e):
                return m[e]
    return ''


def _pseudo_ch(c: Chapter) -> Change:
    """把一章的多个变化压成一条代表（章节层比较用）。

    ⚠ 压法必须**稳定**：按签名排序取第一条 —— 否则同一组变化因为顺序不同
      就被判成"不同"，空转会漏。
    """
    sigs = sorted(ledger_signatures(c.changes)) or sorted(
        ledger_signatures(c.beats))
    if not sigs:
        return Change()
    k, s, o, a = (sigs[0].split('|') + ['', '', '', ''])[:4]
    return Change(kind=k, subject=s, obj=o, after=a)


def _person_names(text: str, allowed=()) -> list[str]:
    """疑似人名：**同一串"X说/X问/X道"里出现 ≥2 次的**才算候选。

    ★ 为什么必须加"≥2 次"（2026-10-21 真跑实测，误报惨重）：
      只用"说/问/道前面的 2~3 个字"，会把
      `台后头说` `我正想问` `她只说` `压着声道` `汉子又说` 全算成人名 ——
      真跑一次报了 7~12 条，**全是误报**，把 L2 卡死。
      真人写作用指代（"她""汉子"），真正的**新造人名**会反复出现。
      ⇒ 频次 ≥2 是一个便宜且稳的门槛；一次性的生名会漏（宁可漏，不可误杀）。
    ★ `allowed` 里的词一律不算（人物表、物件、地名）。
    """
    skip = {'他们', '我们', '你们', '自己', '这时', '忽然', '于是',
            '低声', '轻声', '声音', '有人', '众人', '一面', '一边',
            '汉子', '女子', '那人', '这人', '掌柜', '客人', '众人'}
    cnt: dict[str, int] = {}
    #: 动词前的单字副词（"王二**又**说""她**就**问"）。不剥掉的话，
    #: 同一个名字会被拆成"王二"与"王二又"两条，频次各 1 ⇒ 真名反而漏掉。
    adv = '又再才便就却也还已正忽'
    for m in re.finditer(r'([\u4e00-\u9fff]{2,3})(?:说|问|道|笑|答|应|唤|叫)', text):
        n = m.group(1)
        if len(n) == 3 and n[-1] in adv:
            n = n[:-1]
        cnt[n] = cnt.get(n, 0) + 1
    out = []
    for n, k in cnt.items():
        if k < 2 or n in skip:
            continue
        if any(n in str(a) or str(a) in n for a in allowed if a):
            continue
        out.append(n)
    return list(dict.fromkeys(out))


def _run_field(run, names) -> str:
    for n in names:
        v = getattr(run, n, None)
        if v:
            return str(v)
    return ''


def _read_transcript(run) -> list[dict]:
    """从运行目录读 `transcript.jsonl`（读不到就返回空）。"""
    for attr in ('root', 'dir', 'path'):
        root = getattr(run, attr, None)
        if not root:
            continue
        p = Path(root)
        for cand in list(p.rglob('transcript.jsonl'))[:1]:
            try:
                return [json.loads(x) for x in
                        cand.read_text(encoding='utf-8').splitlines() if x.strip()]
            except Exception:                                    # noqa: BLE001
                return []
    return []


def _guess_logline(src: Source) -> str:
    for e in src.events[:2]:
        if e.get('text'):
            return str(e['text'])[:60]
    return ''


def _guess_cast(src: Source) -> dict[str, str]:
    """人物表：**从真实台词里抽**，不猜。"""
    out: dict[str, str] = {}
    for x in src.lines:
        w = str(x.get('who') or '').strip()
        if w and w not in out:
            out[w] = ''
    for e in src.events:
        w = str(e.get('who') or '').strip()
        if w and w not in out:
            out[w] = ''
    return out


# ══════════════════════════════════════════════════════════════════
# 存取（断点续跑 / 给作者看）
# ══════════════════════════════════════════════════════════════════

def dump(sk: Skeleton, path) -> None:
    """落盘成 JSON —— **每层过闸后都存一次**，中断了不用从头再来。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(sk), ensure_ascii=False, indent=2),
                 encoding='utf-8')


def load(path) -> Skeleton:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    sk = Skeleton(logline=data.get('logline', ''),
                  spine=list(data.get('spine') or ()),
                  cast=dict(data.get('cast') or {}),
                  props=list(data.get('props') or ()))
    for cd in data.get('chapters') or ():
        ch = Chapter(idx=int(cd.get('idx', 0)), title=cd.get('title', ''),
                     act=cd.get('act', '承'), spine=cd.get('spine', ''),
                     place=cd.get('place', ''),
                     present=list(cd.get('present') or ()),
                     changes=[_chg(x) for x in (cd.get('changes') or ())],
                     events=list(cd.get('events') or ()),
                     draft=cd.get('draft', ''), final=cd.get('final', ''))
        for bd in cd.get('beats') or ():
            ch.beats.append(Beat(id=bd.get('id', ''),
                                 who=list(bd.get('who') or ()),
                                 want=bd.get('want', ''),
                                 obstacle=bd.get('obstacle', ''),
                                 change=_chg(bd.get('change') or {}),
                                 events=list(bd.get('events') or ()),
                                 lands=bd.get('lands', '')))
        sk.chapters.append(ch)
    return sk


def _chg(d: dict) -> Change:
    return Change(kind=d.get('kind', ''), subject=d.get('subject', ''),
                  obj=d.get('obj', ''), before=d.get('before', ''),
                  after=d.get('after', ''), cause=d.get('cause', ''),
                  tick=d.get('tick', ''), reversal=bool(d.get('reversal')))
