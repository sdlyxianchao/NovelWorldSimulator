# -*- coding: utf-8 -*-
"""**装订稿末尾的质量指标页** —— 把每个数字的含义写清楚。

★★★ 为什么放在**正文末尾**而不是文件头
=====================================
文件头是"读者进门的门厅"：一上来先看到一堆百分比和阈值，读小说的兴致就没了。
末尾是"放下书之后翻到的附录"，这时候读者（作者）已经在想"这一稿哪里不对"，
正是需要数字的时候。
⚠ 这也意味着**它可以被删掉**：它是给作者看的，不是作品的一部分。
  所以整页用 `---` 隔开，并且在第一行就写明"这一页是附录，可以删"。

一条自我约束
------------
这里**只解释口径，不给建议**。"应该怎么改"是 `导出/反思记录.md` 与
`crew/repair_recipes.py` 的事。混在一起会让这一页变成第二份待办清单，
而没人会去读第二份。
[EN] The quality sheet appended to the bound draft. It explains what each number means;
[EN] it never tells you what to do about it -- that belongs to the reflection record.
"""
from __future__ import annotations

import statistics

#: 真人基线的样本量。**必须写出来** —— 不写样本量的"参考值"是没有信息量的。
#: 这些数字是 `samples/zh` 里 36 篇 ≥150 汉字的成稿（原创短篇，不是公版书）。
_HUMAN_N = 36


def _zh(text: str) -> int:
    return len([c for c in str(text or '') if '\u4e00' <= c <= '\u9fff'])


def _collect(text: str) -> dict:
    """量一遍。**任何一项失败都记 None**，绝不让指标页把导出搞崩。"""
    out: dict = {}
    try:
        from crew import prose_flow as PF
        from crew import global_checks as GC
    except Exception:                                            # noqa: BLE001
        return out
    raw = str(text or '')
    try:
        sents = [x[2] for x in PF._sentences(raw) if x[2] >= 2]
    except Exception:                                            # noqa: BLE001
        sents = []
    out['zh'] = _zh(raw)
    out['sents'] = len(sents)
    if sents:
        out['sent_med'] = float(statistics.median(sents))
        out['sent_max'] = int(max(sents))
    try:
        out['speeches'] = len(PF.quoted_texts(raw))
    except Exception:                                            # noqa: BLE001
        out['speeches'] = None
    try:
        bare = PF._bare_with_ends(raw)
        out['clause'] = ((bare.count('，') + bare.count('、')) / max(1, len(sents))
                         if sents else None)
    except Exception:                                            # noqa: BLE001
        out['clause'] = None
    try:
        out['counts'] = dict(PF.prose_issue_count(raw))
    except Exception:                                            # noqa: BLE001
        out['counts'] = {}
    try:
        out['book'] = GC.audit_book([(1, raw)])
    except Exception:                                            # noqa: BLE001
        out['book'] = {'issues': [], 'counts': {}, 'total': 0}
    return out


#: 八项确定性检测的**逐项释义**。
#: 格式：键 → (显示名, 口径, 真人参考, 为什么算毛病)
_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ('平铺段',
     '段内平均每句**不到 0.2 个逗号**',
     '真人 0 段',
     '整段都是「岛村倚着窗框。驹子坐在火钵旁。」这种光秃秃的主谓宾，'
     '一句一件事，读起来像分镜表。**这是整段口径**，不跟单句比长短。'),
    ('憋气段',
     '段内长句（≥25 字）过半，或冒出一个 ≥45 字的句子',
     '真人中位 0 / 最大 1',
     '整段没有换气的地方，读者会累。注意：**真人也有 1 段**，所以它不是"绝对不能有"。'),
    ('重复',
     '同一句请求/回答/口头禅，在一天内被换着说法说 3 次以上',
     '视作品而定',
     '反复说同一件事，读者会觉得原地打转。**最需要看上下文的一项** —— '
     '真人小说的"回声式对答"字面重合 100% 却极好，所以这一项要看候选原文才能判。'),
    ('拥挤段',
     '一段里塞了太多动作/换人说话，超过阅读节奏',
     '真人中位 0',
     '该分段的地方没分，读起来喘不上气。只动分段、不动内容。'),
    ('元叙述',
     '正文里漏出"本章到此结束""以上是今天的剧情"这类写作者的话',
     '应当为 0',
     '穿帮。把它改写进了小说里，读者会立刻出戏。纯代码剥离，代价为零。'),
    ('感知自洽',
     '「隔着纸门看见他睫毛上的雪」这类**不可能看见**的描写',
     '应当为 0',
     '角色不可能知道/看见的事被写进了叙述。这是逻辑硬伤，读者当场发现。'),
    ('问答悬空',
     '问了一句，对方答的是另一件事，且后文没有交代',
     '应当为 0',
     '对话接不上。常见成因是删句子时删掉了答话那一句。'),
    ('道具循环',
     '同一件东西被反复"续上—耗掉"（续水、添炭、点灯）超过 3 次',
     '真人 18 章最大 0 次',
     '用同一件道具反复起兴，事情没有往前走。'),
)

#: 全书级候选的逐项释义。**这一组不判病**，所以措辞必须区别于上面那张表。
_BOOK_ROWS: tuple[tuple[str, str, str], ...] = (
    ('台词回声',
     '同一段 3~6 字的短语，出现在 4 句以上**不同**的台词里（每句措辞都不一样）',
     '这是"换着说法重复"的可数形态。**它可能是手法**：话题聚焦、称谓反复都算正常'
     '（真人样本里「崇仁坊」「十五年前」都是 0 命中，因为门槛压在 4）。'
     '判据是"删掉它读者会损失什么"，说不出损失才算病。'),
    ('道具流转',
     '同一件东西在"递/推/提/放"这类动作里出现 4 次以上',
     '东西在几个人手里传来传去，事情没往前走。'
     '**也可能是手法**：一件东西被反复推让，本身就是戏。'),
    ('跨天复读',
     '同一句 6 字以上的台词，在**不同天**里逐字一样',
     '单天看每句都合理（当天确实说了这句），装订成书就是复读。'
     '这一项基本没有"手法"的解释空间。'),
    ('概述代场景',
     '一句没有台词、只有"他把什么事说了"的交代'
     '（如「忽然对她吐露自己长年记日记的习惯，说些只有纸笔知道的琐碎」）',
     '读者**被告知**有这件事，却没有看到它发生。'
     '⚠ 这一项机器**只报告、不修改**：修它必须写出"她具体说了什么"，'
     '那是新增内容，不是改写。'),
)


def _fmt(v, nd: int = 2, suffix: str = ''):
    if v is None:
        return '—'
    if isinstance(v, float):
        return f'{v:.{nd}f}{suffix}'
    return f'{v}{suffix}'


def render(text: str, *, title: str = '') -> str:
    """生成指标页的 Markdown。**量不出来就返回空串**（宁可没有附录，不许导出崩）。"""
    d = _collect(text)
    if not d or not d.get('counts'):
        return ''
    counts = d['counts']
    book = d.get('book') or {}
    issues = book.get('issues') or []
    total = sum(int(v or 0) for v in counts.values())

    L: list[str] = []
    L.append('---')
    L.append('')
    L.append('## 附：本稿质量指标')
    L.append('')
    L.append(f'> 这一页是**附录**，给作者看的，可以直接删掉，不影响作品。')
    L.append(f'> 「真人参考」取自 `samples/zh` 里 {_HUMAN_N} 篇成稿'
             f'（原创短篇，每篇 ≥150 汉字）—— 它是**参照**，不是及格线。')
    L.append('')

    # ── 一、体量 ──
    L.append('### 一、体量')
    L.append('')
    L.append('| 项目 | 本稿 | 这个数怎么来的 |')
    L.append('|---|---|---|')
    L.append(f'| 汉字 | {_fmt(d.get("zh"))} | 只数汉字，不含标点与空白 |')
    L.append(f'| 叙述句 | {_fmt(d.get("sents"))} | 按 `。！？` 切，'
             f'**台词内部不算**（否则人物一说话就会被误算成很多短句）|')
    L.append(f'| 台词 | {_fmt(d.get("speeches"))} | 成对引号里的句子数 |')
    L.append('')

    # ── 二、节奏 ──
    L.append('### 二、节奏')
    L.append('')
    L.append('| 指标 | 本稿 | 真人参考 | 说明 |')
    L.append('|---|---|---|---|')
    L.append(f'| 句长中位 | {_fmt(d.get("sent_med"), 1, " 字")} | 14 字（8–29） | '
             f'一半的句子比它短、一半比它长。太短=碎，太长=闷 |')
    L.append(f'| 最长句 | {_fmt(d.get("sent_max"), 0, " 字")} | — | '
             f'超过 45 字就会被"憋气段"抓 |')
    L.append(f'| 逗号 / 句 | {_fmt(d.get("clause"))} | 1.10（0.67–2.40） | '
             f'**平均每个句子有几个逗号**。这是"一句一件事"最有效的口径：'
             f'真人最低 0.67，掉到 0.2 以下就是光秃秃的主谓宾串烧 |')
    L.append('')

    # ── 三、毛病 ──
    L.append(f'### 三、毛病（确定性检测，共 **{total}** 处）')
    L.append('')
    if total == 0:
        L.append('八项检测**全部为 0**。下面逐项列出——为 0 的也列，'
                 '这样你知道它**查过**，而不是没查。')
        L.append('')
    # ★★★ **永远逐项列全八项**，为 0 的也列。
    #   第一版在 total==0 时只写一句"全部为 0" —— 那不是"逐项说清楚"：
    #   读者看不出到底查了哪八样，也分不清"没毛病"和"没检查"。
    # [EN] Always list all eight rows, including zeros: otherwise the reader cannot tell
    # [EN] "no defects" from "not checked".
    L.append('| 项目 | 本稿 | 真人参考 | 它指什么 | 为什么算毛病 |')
    L.append('|---|---|---|---|---|')
    for key, calibre, human, why in _ROWS:
        n = int(counts.get(key, 0) or 0)
        mark = f'**{n}**' if n else '0'
        L.append(f'| {key} | {mark} | {human} | {calibre} | {why} |')
    L.append('')
    L.append('> 这八项是**纯代码**量的（零调用、零成本、结果可复现）。'
             '判官类（打转 / 自洽的语义判断）不在其中 —— 它们会抖动，'
             '拿抖动的东西当"改好了没有"的标准，只会让循环跟着噪声跑。')
    L.append('')

    # ── 四、全书级候选 ──
    L.append(f'### 四、全书级候选（**不是毛病**，共 **{len(issues)}** 条）')
    L.append('')
    L.append('这一组是**跨句、跨段、跨天**才看得见的形态。'
             '它们只在这里列出来供你复核，**不参与上面的计数**，'
             '也没有任何自动修改 —— 因为它们很可能是手法。')
    L.append('')
    if not issues:
        L.append('四类形态**都没有命中**。下面列出它们各查什么——'
                 '命中为 0 不等于没查。')
        L.append('')
    if issues:
        L.append('| 形态 | 次数 | 具体 |')
        L.append('|---|---|---|')
        for x in issues:
            L.append(f'| {x.kind} | {x.count} | {x.detail} |')
        L.append('')
    # 同样逐项列全四类（含 0 命中的），口径一起写清。
    for kind, calibre, why in _BOOK_ROWS:
        hit = [x for x in issues if x.kind == kind]
        n = sum(int(x.count) for x in hit) if kind != '概述代场景' else len(hit)
        L.append(f'- **{kind}**（本稿 {n}）—— 查的是：{calibre}')
        L.append(f'  - {why}')
    L.append('')

    # ── 五、边界 ──
    L.append('### 五、这一页不包含什么')
    L.append('')
    L.append('- **不判断写得好不好。** 上面的数字只能说明"有没有某几类可数的毛病"，'
             '说明不了"这段美不美、这个人物立不立得住"。')
    L.append('- **不给改法。** 该改哪里、怎么改，在运行文件夹的 `导出/反思记录.md` 里。')
    L.append(f'- **真人参考不是及格线。** 真人样本里有 1 段"憋气段"、有 0.67 的逗号密度；'
             f'拿它当"必须 0"去改，会把本来正常的段落改坏（这个项目付过学费）。')
    L.append('')
    return '\n'.join(L)


__all__ = ['render']
