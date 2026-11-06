# -*- coding: utf-8 -*-
"""**确定性验收层** —— 判定权归代码，LLM 只负责写。

★★★ 为什么要有这个模块（2026-10-20，架构层的一次重做）
=====================================================
这一年里反复出现的三类毛病，根子是**同一个**：让"写稿的那一方"同时当裁判。

| 现象（都实测过） | 当时怎么修的 | 为什么还会复发 |
|---|---|---|
| 修完"太碎"变成"太长"（0→2） | 在提示词里加"长句最多一句" | 仍是**模型自己**判自己写得好不好 |
| 某一轮修好两处、把第三类改多（平铺 2→3） | 加"保留最好一版"，但只比**总数** | 单标量把"两类互换"判成"没变化" |
| 同分时保留原文、把第 1 轮的修改丢掉 | 无 | `if after < best` 无 tie-break |
| 判据假绿（`ok(..., 'x' or True)`）| 一条条改判据 | 评估信号本身没有"不可争辩"的层 |

公开研究把这条路走完了，结论很硬（见 `crew/reflexion.py` 顶部的引用）：
**在闭环优化里，LLM 判官不能当 oracle，只能当 advisor** ——
它会偏向自己的输出（rubric 明确时，误判自己合格的概率比判别人高 50%），
在分布外输入上退化到接近抛硬币。可以争辩的判定，优化压力一定会找到缝。

所以这一层只做一件事：**用可数的东西回答"改好了没有"**，并且
**多目标分别判**（不是求和），**退化就拒绝**（不是净收益为正就收）。

三条判定原则
------------
1. **硬约束先于优劣**：台词不许变少、字数不许腰斩、句子不许被拆碎。
   这些是"改动是否合法"，不是"改动是否更好" —— 一旦违反，直接拒绝，
   不管毛病是不是变少了（这正是"把整段砍掉，毛病当然归零"那个坑）。
2. **帕累托优先，权衡要申请**：任何一类毛病变多 ⇒ 默认拒绝。
   只有当总加权改善明显大于那点退化（且单类退化 ≤1）时，才降级成
   `tradeoff`（候选，进 archive 备选，**不直接替换正文**）。
   ⇒ "修好 A、弄坏 B"再也不会被当成进步。
3. **完美成绩本身可疑**（canary）：毛病清零 **且** 字数掉了一大截
   ⇒ 判为"靠删达标"，拒绝。研究里叫 canary case —— 满分是作弊的证据。

⚠ 这一层**不认识**任何语义好坏（写得美不美、像不像人）。那不是它的事：
  语义判断交给 LLM 顾问（`reflexion.Reflector`），它只有一票建议权。

[EN] Deterministic acceptance layer. Verdicts come from countable signals, never
[EN] from the writer. Hard invariants first (speech count, length, sentence count);
[EN] then Pareto: any dimension that regressed is rejected by default, and a genuine
[EN] trade-off only downgrades to `tradeoff` (archived, not applied). A canary rejects
[EN] "defects hit zero because the prose was gutted".
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 每一类毛病有多伤读者 —— **权重不是拍脑袋的**，按"读到会不会出戏"排：
#:   · 感知自洽 / 问答悬空 = 逻辑硬伤，读者当场发现"这不可能"；
#:   · 道具循环 = 反复续同一件东西，读三章就腻（真人中位 0 次）；
#:   · 重复 = 台词与动作打转，但真人也会重复，所以不能给太高（R43 的教训：
#:     真人最长同题链中位 2 / 最大 4，判"重复"要看对面有没有变化）；
#:   · 拥挤 / 憋气 / 平铺 = 版式与节奏，影响阅读体感但不动情节，最低一档；
#:   · 元叙述 = 漏一句"本章到此结束"这种，最容易确定性剥离，权重最低。
RUBRIC: dict[str, float] = {
    '感知自洽': 3.0,
    '问答悬空': 3.0,
    '道具循环': 2.0,
    '重复': 2.0,
    '拥挤段': 1.5,
    '憋气段': 1.5,
    '平铺段': 1.0,
    '元叙述': 1.0,
}

#: 硬约束的门槛。数字来自实测：
#:   · 台词变少是**丢内容**（实测丢过 26 → 23 两句真台词），一律拒；
#:   · 中文改写正常会略微扩写，0.85~1.45 是"改写"的安全区，出了就是删/灌水；
#:   · 句子数暴涨 1.8 倍 = 被拆成清单（R49 的病），那是另一头。
MIN_SPEECH_RATIO = 1.0
MIN_CHAR_RATIO = 0.85
MAX_CHAR_RATIO = 1.45
MAX_SENT_RATIO = 1.8
#: 满分可疑的"缩水"门槛。**必须比 `MIN_CHAR_RATIO`(0.85) 宽** —— 见 `_canary`。
#: 0.90：掉一成以上就值得怀疑"是靠删达标"，但还没到"改动不合法"。
CANARY_SHRINK = 0.90

#: 单类退化能容忍的上限（超过就不许谈"权衡"）
MAX_DIM_REGRESS = 1


def _prose():
    """懒导入 —— 让这个模块可以被 `export/` 单独 import（不拖推演侧）。"""
    from crew import prose_flow
    return prose_flow


@dataclass(frozen=True)
class Score:
    """一次打分：**每类毛病分开数**，外加三项"改动合法性"指标。

    为什么不合成一个分数：合成之后"三类变好、一类变坏"和"四类都没动"
    可能得到同一个数，而这两件事在读者那里完全不同。
    [EN] Per-class counts plus three legality measures. Never collapsed into one scalar:
    [EN] a scalar cannot tell "three classes better, one worse" from "nothing moved".
    """
    counts: dict[str, int] = field(default_factory=dict)
    zh: int = 0            # 汉字数
    speeches: int = 0      # 台词句数
    sentences: int = 0     # 叙述句数

    # ── 派生量 ──
    @property
    def total(self) -> int:
        return sum(int(v or 0) for v in self.counts.values())

    @property
    def weighted(self) -> float:
        return round(sum(RUBRIC.get(k, 1.0) * int(v or 0)
                         for k, v in self.counts.items()), 3)

    def as_dict(self) -> dict:
        return {'counts': dict(self.counts), 'zh': self.zh,
                'speeches': self.speeches, 'sentences': self.sentences,
                'total': self.total, 'weighted': self.weighted}

    # ── 构造 ──
    @classmethod
    def of(cls, text: str) -> 'Score':
        """从正文量一次。**任何一项量不出来都记 0**，绝不让打分本身抛异常 ——
        验收层抛异常等于"这一轮没有判定"，而调用方会把它当成"通过"（§52.4 的坑）。"""
        raw = str(text or '')
        if not raw.strip():
            return cls()
        pf = _prose()
        try:
            counts = dict(pf.prose_issue_count(raw))
        except Exception:                                        # noqa: BLE001
            counts = {}
        zh = len([c for c in raw if '\u4e00' <= c <= '\u9fff'])
        try:
            speeches = len(pf.quoted_texts(raw))
        except Exception:                                        # noqa: BLE001
            speeches = 0
        try:
            sentences = len([x for x in pf._sentences(raw) if x[2] >= 2])
        except Exception:                                        # noqa: BLE001
            sentences = 0
        return cls(counts=counts, zh=zh, speeches=speeches, sentences=sentences)


@dataclass
class Decision:
    """一次"改动是否被接受"的判定。`why` 必须**具体到可行动** ——
    它是 Reflexion 的反馈信号；写"不够好"那种话，反思就会变成空话
    （研究里那条：反思的质量上限由评估信号的具体度决定）。

    level:
      · `accept`   帕累托改进（没人变差，至少一类变好）⇒ 直接替换正文
      · `tradeoff` 净收益为正但有一类轻微变差 ⇒ 只进 archive，**不替换**
      · `reject`   违反硬约束 / 某类明显变差 / 没有改动 ⇒ 保留原文
    """
    level: str
    why: str
    down: tuple[str, ...] = ()      # 变好的类
    up: tuple[str, ...] = ()        # 变坏的类
    violated: tuple[str, ...] = ()  # 违反的硬约束
    suspect: str = ''               # canary 命中原因
    old: Score | None = None
    new: Score | None = None
    label: str = ''                 # 哪一步（'平铺段' 等）

    @property
    def ok(self) -> bool:
        return self.level in ('accept', 'tradeoff')

    @property
    def applied(self) -> bool:
        """能不能**直接替换正文**。`tradeoff` 不算 —— 它只是候选。"""
        return self.level == 'accept'

    def one_line(self) -> str:
        tag = {'accept': '✓ 收', 'tradeoff': '~ 候选', 'reject': '✗ 拒'}[self.level]
        return f'{tag}（{self.label or "?"}）：{self.why}'


def _deltas(old: Score, new: Score) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """逐类比：返回 (变多的类, 变少的类)。新增的类按 0 起算。"""
    up, down = [], []
    for k in sorted(set(old.counts) | set(new.counts)):
        a, b = int(old.counts.get(k, 0)), int(new.counts.get(k, 0))
        if b > a:
            up.append(k)
        elif b < a:
            down.append(k)
    return tuple(up), tuple(down)


def _detail(old: Score, new: Score, up: tuple[str, ...],
            down: tuple[str, ...]) -> str:
    """把差异写成一句**能照着改**的话（带每一类的 before→after）。"""
    parts = [f'{k} {old.counts.get(k, 0)}→{new.counts.get(k, 0)}' for k in up]
    good = [f'{k} {old.counts.get(k, 0)}→{new.counts.get(k, 0)}' for k in down]
    if parts and good:
        return '改好了 ' + '、'.join(good) + '；但把 ' + '、'.join(parts) + ' 改多了'
    if parts:
        return '把 ' + '、'.join(parts) + ' 改多了'
    if good:
        return '改好了 ' + '、'.join(good)
    return '各处数量没有变化'


def _invariants(old: Score, new: Score, *, protect_speeches: bool = True) -> tuple[str, ...]:
    """硬约束：改动是否**合法**（不是是否更好）。"""
    out: list[str] = []
    if protect_speeches and old.speeches > 0:
        if new.speeches < old.speeches * MIN_SPEECH_RATIO:
            out.append(f'台词 {old.speeches}→{new.speeches}（不许变少）')
    if old.zh >= 120:
        if new.zh < old.zh * MIN_CHAR_RATIO:
            out.append(f'字数 {old.zh}→{new.zh}（少于 {MIN_CHAR_RATIO:.0%}，像删内容）')
        elif new.zh > old.zh * MAX_CHAR_RATIO:
            out.append(f'字数 {old.zh}→{new.zh}（多于 {MAX_CHAR_RATIO:.0%}，像灌水）')
    if old.sentences >= 8 and new.sentences > old.sentences * MAX_SENT_RATIO:
        out.append(f'句子 {old.sentences}→{new.sentences}（被拆成清单了）')
    return tuple(out)


def _canary(old: Score, new: Score) -> str:
    """**满分本身可疑**：毛病清零，同时内容明显缩水 ⇒ 更像是删出来的。

    这条不是防"改得好"，是防"把有问题的段落整段删掉"——
    毛病数当然会掉到 0，读者却少读到一段戏。
    [EN] A perfect score is suspicious on its own: defects to zero while the prose
    [EN] shrank is evidence of deletion, not repair.
    """
    if new.total != 0 or old.total < 3:
        return ''
    # ⚠ 阈值必须**比硬约束宽**（0.90 vs 0.85），否则 canary 永远不会独立触发 ——
    #   字数掉到 0.85 以下时 `_invariants` 已经先拦了，canary 成了死代码
    #   （反例法 M3 当场照出来：删掉整段 canary，A4 依然绿）。
    #   两者的分工：硬约束管"改动是否合法"，canary 管"清零是不是靠删"。
    if old.zh >= 200 and new.zh < old.zh * CANARY_SHRINK:
        return f'毛病清零但字数 {old.zh}→{new.zh}（掉了一成以上，像删达标）'
    if new.speeches < old.speeches:
        return f'毛病清零但台词 {old.speeches}→{new.speeches}'
    return ''


def compare_scores(old: Score, new: Score, *, label: str = '',
                   protect_speeches: bool = True) -> Decision:
    """**只比分数**（不碰文本）。判据可以直接构造两个 Score 喂进来 ——
    否则想测"净收益为正但单类退化 1"就得先造出一段恰好长那样的中文，
    而那种夹具本身比被测逻辑还难写对。
    """
    if new.zh == 0 and new.total == 0 and new.sentences == 0:
        return Decision('reject', '改出来是空的（保留原文）', label=label,
                        old=old, new=new, violated=('结果为空',))
    violated = _invariants(old, new, protect_speeches=protect_speeches)
    if violated:
        return Decision('reject', '违反硬约束：' + '；'.join(violated),
                        violated=violated, label=label, old=old, new=new)
    suspect = _canary(old, new)
    if suspect:
        return Decision('reject', '可疑成绩：' + suspect, suspect=suspect,
                        label=label, old=old, new=new)
    up, down = _deltas(old, new)
    detail = _detail(old, new, up, down)
    if not up and not down:
        if new.weighted < old.weighted:
            return Decision('tradeoff', detail + '（总数相同但加权更低，留作候选）',
                            down=down, up=up, label=label, old=old, new=new)
        return Decision('reject', detail + '（没有可量的改善）',
                        down=down, up=up, label=label, old=old, new=new)
    if not up:
        return Decision('accept', detail, down=down, up=up, label=label,
                        old=old, new=new)
    worst = max(int(new.counts.get(k, 0)) - int(old.counts.get(k, 0)) for k in up)
    gain = old.weighted - new.weighted
    if worst <= MAX_DIM_REGRESS and gain > 0:
        return Decision('tradeoff', detail + f'（加权 {old.weighted}→{new.weighted}，'
                                             '留作候选、不直接替换）',
                        down=down, up=up, label=label, old=old, new=new)
    return Decision('reject', detail + '（某一类变多就退回 —— 不许把病换到另一头）',
                    down=down, up=up, label=label, old=old, new=new)


def compare(old_text: str, new_text: str, *, label: str = '',
            old_score: Score | None = None,
            protect_speeches: bool = True) -> Decision:
    """判定一次改动。**这是全项目唯一的"改好了没有"入口**。

    `old_score` 可以传进来复用（同一段原文会被多步比较，重复量一遍很浪费）。
    """
    old = old_score if old_score is not None else Score.of(old_text)
    new = Score.of(new_text)
    if not str(new_text or '').strip():
        return Decision('reject', '改出来是空的（保留原文）', label=label,
                        old=old, new=new, violated=('结果为空',))
    if str(new_text).strip() == str(old_text).strip():
        return Decision('reject', '一个字都没动（不必记一条教训）', label=label,
                        old=old, new=new)

    if str(new_text).strip() == str(old_text).strip():
        return Decision('reject', '一个字都没动（不必记一条教训）', label=label,
                        old=old, new=new)
    return compare_scores(old, new, label=label,
                          protect_speeches=protect_speeches)


def better(a: tuple[Score, str], b: tuple[Score, str]) -> bool:
    """archive 的排序：**谁算"更好的一版"**。

    顺序就是用户读稿时会关心的顺序：
      ① 毛病少（加权，不是求和）；
      ② 台词多（丢台词 = 读者少读到人说话，实测丢过两句）；
      ③ 字数接近原文（`baseline` 由调用方在比较前塞进 counts 之外，这里只比 zh 的绝对值）。
    ⚠ 原来是 `if after_total < best_total`，同分时保留**原始文本**、
      把第 1 轮的修改整份丢掉 —— 那是"什么都没做"的另一个形态。
    [EN] Ranking for the archive. Weighted defects, then speech count, then length.
    [EN] The old `<` comparison discarded a whole round's work on ties.
    """
    (sa, _), (sb, _) = a, b
    # 键越小越优：字数要**多**、台词要**多**，所以取负号
    # （写成 `sa.zh` 会让"更短的一版"胜出 —— 那是反的）。
    # ⚠ 返回 `ka < kb`（a 更优）。这个方向**曾经写反**：
    #   `kb < ka` 让 `better(a, b)` 在 b 更好时返回 True，于是 archive 取到最差那版、
    #   判据 B3 直接红。判据救了一次——但方向问题读代码时几乎看不出来。
    ka = (sa.weighted, sa.total, -sa.speeches, -sa.zh)
    kb = (sb.weighted, sb.total, -sb.speeches, -sb.zh)
    return ka < kb


__all__ = ['RUBRIC', 'Score', 'Decision', 'compare', 'compare_scores', 'better',
           'MIN_CHAR_RATIO', 'MAX_CHAR_RATIO', 'MAX_SENT_RATIO']
