# -*- coding: utf-8 -*-
"""**修复合约注册表** —— 加一类毛病只登记一行，不改主流程。

★★★ 为什么要有这张表（2026-10-20）
==================================
以前加一类毛病要改**四个地方**，漏一处就半残：

1. `prose_flow.prose_issue_count` —— 不然数不出来，收敛判据看不见它；
2. `Novelist._check_round_steps` —— 不然没有人修；
3. `Novelist._steps_to_run` 的跳过规则 —— 不然它会反复判自己的产物；
4. `tools/verify_prose_flow.py` 的计数表断言 + 反例法 —— 不然没有护栏。

这就是"每次一点一点针对性修复"的来源：**不是懒，是结构逼着你逐点改**。
现在第 2、3 步都从这张表读；`order` 是顺序的**唯一事实来源**；
`covers` 声明"我负责哪些类"，于是"数得出来却没人修"这件事可以被**判据**查出来
（见 `tools/verify_reflexion.py` 的 `C2`）—— 而不是靠人记得。

两条排序纪律（都是踩出来的，别改）
--------------------------------
· **先删后写**：确定性动作（剥离元叙述、逐条删打转）不会写进新东西，
  所以要排在需要模型的重写之前 —— 删掉的不会再被改回来。
· **`元叙述` 必须最后**：它是"多写了一句"，任何先跑的重写都可能再添一句（R44）。
  ⇒ 它的 `order` 是 900，而且 `_should_skip` 对它永远不生效。

`kind` 不是装饰：它解释"为什么排在这里"，也是以后做并行/跳步时的依据。
`n_best` 是每个 step 生成几个候选 —— **确定性动作给 1，改写类才给 2**，
因为候选数是线性花钱的，而"删"这件事没有第二种写法值得试。

[EN] Declarative repair registry. Adding a defect class = one row here plus a detector;
[EN] the step list and the skip rules both read from it, so there is no second place to
[EN] forget. `covers` makes "countable but nobody repairs it" a test failure instead of
[EN] a thing someone has to remember. Order: delete before rewrite, meta-strip last.
"""
from __future__ import annotations

from dataclasses import dataclass

#: 每个 step 最多几个候选。**别随手调大**：成本是线性的，而验收层已经能
#: 把"改坏了"的候选筛掉，多加候选的边际收益很低。
MAX_N_BEST = 2


@dataclass(frozen=True)
class Recipe:
    """一条修复合约。

    order  跑的顺序（唯一事实来源）
    attr   `Novelist` 上的方法名（**只放名字**，绑定在 `build()` 里做，
           这样这张表可以在没有实例的情况下被判据/文档直接读）
    label  它负责哪一类（必须与 `prose_issue_count` 的键一致）
    kind   `strip` 确定性地删 / `rewrite` 要模型改写 / `layout` 只动分段与切句
    covers 它**顺带**覆盖的类（例如平铺段那一步内部先切长句，也治了憋气段）
    """
    order: int
    attr: str
    label: str
    kind: str
    n_best: int = 1
    covers: tuple[str, ...] = ()
    why: str = ''
    #: ★★★ **`defect` 实病 / `style` 文风**（2026-10-25 加）。
    #:
    #: 为什么必须分开（望江楼那轮 49 分钟的整理稿，日志实测）：
    #: 68 次 `crew_day_novel` 里 18 次是"写这一段"，剩下 **50 次是 Reflexion 在改**；
    #: 而触发那 50 次整段重写的，绝大多数是「细节复读」「憋气」「平铺」这些**文风类**。
    #: 这与本项目的既有规则直接冲突 —— "检测器的输出是候选不是判决：
    #: **文风类不触发退回**，只有实病才触发"。规则写在那儿，Reflexion 却没照做。
    #:
    #: 判据很具体：文风类的"毛病"删掉之后**读者不损失任何东西**（真人比模型重复更多），
    #: 花一整段时间去追它，追的还是自己的产物 —— 越改越平、越改越挤。
    #: 实病不是：元叙述会把读者踢出故事、感知自洽会让情节立不住、问答悬空会让对话散掉，
    #: 这些**必须改到为止**。
    #:
    #: ⚠ 这条轴只改"**要不要为它再跑一轮**"，不改"第一轮改不改"——
    #:   文风类第一轮照改（该做的活还得做），只是不再为它多烧几轮整段重写。
    #: [EN] `defect` = a real defect, `style` = a prose-style issue. Why they must be separate
    #: (measured on the 49-minute organizer run): of 68 `crew_day_novel` calls, 18 were "write this
    #: chunk" and **50 were Reflexion rewriting it**, mostly triggered by repetition / breathless /
    #: flat-paragraph -- all **style** classes. That contradicts this project's own rule: "detector
    #: output is a candidate, not a verdict: **style classes do not trigger a rewrite**". A style
    #: "defect" costs the reader nothing when removed (real humans repeat more than the model does);
    #: a defect does (meta-narration throws the reader out, implausible perception breaks the plot).
    #: ⚠ This axis only decides **whether another round runs for it**, not whether round 1 fixes it.
    nature: str = 'defect'

    def all_labels(self) -> tuple[str, ...]:
        return (self.label,) + tuple(self.covers)


#: ★ 顺序 = 老 `_check_round_steps` 的顺序，**一个位置都没有动** ——
#:   那是十几轮真跑调出来的，重排会让已知的连锁反应全部重来一遍。
RECIPES: tuple[Recipe, ...] = (
    Recipe(5, '_fix_dialogue_tags', '对话标签', 'strip', 1, (),
           '确定性删副词（只动叙述、不碰台词）—— 先删后写，所以排最前',
           nature='style'),
    # ★★★ 2026-10-28：套话那一类**必须有人负责**（判据 `verify_style_rounds` A5 /
    #   `verify_reflexion` C2 都盯着"数得出来的都有人负责"）。
    #   ⚠ 只改**超配额**的那几处（检测已限流：一章前两处不报）—— 真人也偶尔这么写。
    #   ⚠ 它是**表层**（研究实测：只改表面词句，机器味只掉 1.6 个点），
    #     所以 `n_best=1`、且在顺序上紧跟确定性的那一步，不额外多烧轮次。
    Recipe(6, '_fix_slop', '套话', 'rewrite', 1, (),
           '把「不是X而是Y」「他终于明白」这类套话改回平实的话（只动叙述、不碰台词）',
           nature='style'),
    Recipe(10, '_fix_topic_spin', '重复', 'rewrite', 1, (),
           '里面先走"逐条删"（确定性），删不动才重写 —— 所以它能排在重写类前面',
           nature='style'),
    Recipe(20, '_fix_answer_drift', '问答悬空', 'rewrite', 2, (),
           '要模型改答话；给 2 个候选，因为"答非所问"的改法有好几种'),
    Recipe(21, '_fix_prop_cycle', '道具循环', 'rewrite', 2, (),
           '把反复续的那件东西换成别的事由，改法同样不止一种',
           nature='style'),
    Recipe(22, '_fix_plausibility', '感知自洽', 'rewrite', 2, (),
           '「隔着纸门看清睫毛」这类，改法是把感知改成立或把遮挡写实'),
    Recipe(30, '_fix_flat_paragraphs', '平铺段', 'layout', 2,
           ('憋气段',),
           '内部先 merge 短行 + split 长句（纯代码），再挑 too-long / too-flat 重写 ⇒ '
           '它顺带治了憋气段，这是"数得出来但没独立步骤"的那一类',
           nature='style'),
    Recipe(31, '_fix_repeats', '重复', 'rewrite', 2, (),
           '与 10 分工：10 治"话在打转"，31 治"同一件事反复说"',
           nature='style'),
    Recipe(40, '_fix_crowded', '拥挤段', 'layout', 1, (),
           '只动分段，不动事实 —— 没有第二种写法值得试，给 1 个候选'),
    Recipe(900, '_fix_meta_narration', '元叙述', 'strip', 1, (),
           '必须最后：它是"多写了一句"，任何先跑的重写都可能再添一句'),
)


def style_labels() -> set[str]:
    """**文风类**那几步的 label（`nature='style'`）。

    Reflexion 用它在第 N 轮之后跳过它们：文风类只在第一轮改，不再为它整段重写。
    ⚠ 返回的是 `r.label`（**不是** `all_labels()`）：跳过是按**步骤**跳的，
      而 `_fix_flat_paragraphs` 顺带治的「憋气段」并不是它自己的 label。
    [EN] Labels of the **style** steps. Reflexion uses this to skip them after round N.
    """
    return {r.label for r in RECIPES if r.nature == 'style'}


def ordered() -> tuple[Recipe, ...]:
    return tuple(sorted(RECIPES, key=lambda r: r.order))


def build(novelist) -> list[tuple[object, str]]:
    """绑定到实例，返回 `[(bound_method, label), ...]`（Reflexion 要的形态）。

    方法名写错时**明确报出来**，别静默跳过 —— 静默跳过等于"这一类没人修"，
    而现象只是"改完还剩几处"，很难追。
    """
    out: list[tuple[object, str]] = []
    for r in ordered():
        fn = getattr(novelist, r.attr, None)
        if fn is None:
            raise AttributeError(f'修复合约 {r.attr} 在 Novelist 上不存在'
                                 f'（负责「{r.label}」）—— 改了方法名就要同步这里')
        out.append((fn, r.label))
    return out


def describe() -> list[dict]:
    """给文档与判据读的纯数据形态。"""
    return [{'order': r.order, 'attr': r.attr, 'label': r.label,
             'kind': r.kind, 'n_best': r.n_best, 'nature': r.nature,
             'covers': list(r.covers), 'why': r.why}
            for r in ordered()]


def uncovered(count_keys) -> list[str]:
    """**数得出来、却没有任何一步负责**的那些类。

    这是这张表最值钱的用法：它把"漏了一类"从"读代码才发现"变成"判据报红"。
    """
    covered: set[str] = set()
    for r in RECIPES:
        covered.update(r.all_labels())
    return sorted(k for k in (count_keys or ()) if k not in covered)


def extra(count_keys) -> list[str]:
    """反过来：登记了、但计数表里没有的类（说明检测器漏了，或名字写错）。"""
    known = set(count_keys or ())
    return sorted({lab for r in RECIPES for lab in r.all_labels()
                   if lab not in known})


__all__ = ['Recipe', 'RECIPES', 'MAX_N_BEST', 'ordered', 'build',
           'describe', 'uncovered', 'extra', 'style_labels']
