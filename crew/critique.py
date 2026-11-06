# -*- coding: utf-8 -*-
"""**外部批评分诊** —— 把一份评审意见拆开、逐条验、分级，只吃"真的那一部分"。

★★★ 为什么需要它（2026-10-20 晚，一份真实的外部评审）
====================================================
作者把望江楼的一段发给另一个 AI，让它以"资深小说作家 + 剧作改编"的身份挑毛病，
拿回来 5 条批评。**逐条量过之后，5 条里只有 2 条能直接用**：

| 外部批评 | 实测 | 判定 |
|---|---|---|
| ① 人物标识混乱（"沈砚"像动词） | 人名 10 次里 **2 处**真会被读成祈使句 | **成立**，但处方错 |
| ② 时空跳跃（亥时→夜色） | "亥时"×2、"夜色"×1，没有过渡句 | 成立（弱） |
| ③ 对话与动作脱节（"大量"抹壶放壶） | 茶具动作 **6 处 / 692 字** | **夸大** |
| ④ 悬念过密（"5 次追问白绫"） | 带问号的只有 **2 次**，但同主题台词 **13/34 句** | **数字错、方向对** |
| ⑤ 第一人称混全知视角 | 需要位置推理，没有可数代理 | 无法验证 |

⚠⚠ **最要紧的是 ① 的处方**：「若'沈砚'是动词，应改为'别问'」。
  查设定：「沈砚」同时是**楼名**、**掌柜人名**、楼的**规矩**（"不问来路，不问去处"），
  掌柜的口头禅就是「沈砚。」
  —— 这是作者的核心双关。**照处方改，整本书的骨架就没了。**
  ⇒ 外部批评也是"判官"，同样要**降级为顾问**：它的诊断可以采信，
     它的处方必须过一遍"会不会撞上既定设计"。

## 四档判定（这是本模块的全部价值）

| 判定 | 含义 | 怎么处理 |
|---|---|---|
| `confirmed` | 有可数证据支持 | 进 Reflexion 教训库；**修法用我们自己的**（`fix` 字段），不用它的 |
| `exaggerated` | 方向对、数字被放大 | 只报数字差，不进教训（按放大后的数字去改会过度矫正） |
| `refuted` | 有可数证据反驳 | 丢弃，并记一条"别按它改" |
| `unverifiable` | 没有可数代理 | **明说验不了**，交人工；绝不假装验过 |

★★ `unverifiable` 这一档是刻意存在的。这一轮撞了三次墙才认下来：
  "追问几次""主题多集中""悬念密不密"**在真人与真跑之间分不开**
  （真人最大主题覆盖 33%，望江楼 20%）；硬做检测器就会变成专杀真人的假判据。
  所以这类只报"验不了"，不进自动修复 —— **不知道就说不知道**。

[EN] Adjudication for external critiques. A real review returned five complaints; measuring
[EN] each one showed only two were usable, one was exaggerated (6 actions, not "many"), one
[EN] had the direction right but the count wrong (2 question marks, not 5), and one could
[EN] not be verified at all. Worst of all, its prescription ("rename 沈砚") would have
[EN] destroyed a deliberate pun that is the book's spine. So an external critique is a
[EN] judge too: its diagnosis may be trusted, its prescription must be checked, and
[EN] anything without a countable proxy stays `unverifiable` instead of being faked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: 批评类型 → 验证器名。**只有这里登记过的类型才可能得到 `confirmed`。**
#: 没登记的一律 `unverifiable` —— 这是刻意的：宁可少修，不可假验。
VERIFIERS: dict[str, str] = {
    '人名歧义': 'name',          # `crew.name_guard`
    '动作密度': 'actions',       # 数动作短语
    '元叙述': 'meta',            # 已有检测器
    '问答悬空': 'qa',
    '道具循环': 'prop',
    '平铺段': 'flat',
    '憋气段': 'long',
}

#: 关键词 → 批评类型。按优先级排（长词在前，避免短的抢走长的）。
#: ⚠ `视角` 这一类**故意映射到空**（= `unverifiable`）：
#:   第一版把它接到 `percept_issues`（那个测的是"隔着纸门看见睫毛上沾着雪"），
#:   结果评审第 5 条被"检测器命中 0 处"判成 **✗ 反驳** —— 这是**假反驳**：
#:   「我背对柜台却看见布纹掠过壶钮」需要位置推理，`percept_issues` 根本没有那个判断。
#:   **接错验证器比不接更糟** —— 它会给出一个看似有理的否定结论。
#: [EN] POV mixing maps to nothing on purpose: wiring it to `percept_issues` (which detects
#: [EN] impossible perception, not off-camera vision) produced a **false refutation**.
#: [EN] A wrong verifier is worse than none: it yields a plausible-looking negative.
_KEYWORDS: tuple[tuple[str, str], ...] = (
    ('人名歧义', '人名歧义'), ('人物标识', '人名歧义'), ('标识混乱', '人名歧义'),
    ('说话者', '人名歧义'), ('是谁说', '人名歧义'),
    ('动作描写', '动作密度'), ('动作密度', '动作密度'), ('动作脱节', '动作密度'),
    ('元叙述', '元叙述'),
    ('视角混杂', ''), ('视角不统一', ''), ('全知视角', ''),
    ('感知', '感知越界'),
    ('问答脱节', '问答悬空'), ('答非所问', '问答悬空'),
    ('道具', '道具循环'),
    ('一句一件事', '平铺段'), ('句子太碎', '平铺段'),
    ('长句', '憋气段'),
    # ⚠ 下面这几类**故意不给验证器**：它们分不开真人与真跑（见模块顶部）。
    ('悬念', ''), ('追问', ''), ('节奏', ''), ('时空', ''), ('过渡', ''),
    ('信息密度', ''), ('戏剧行动', ''),
)

#: 可数的"新事实"标记（判 `confirmed` 时用来给证据，不做判据）
_NUMBER = re.compile(r'\d+\s*(?:次|处|句|个|段)')

#: 处方里出现这些词 ⇒ 它要**改设定**（改名/删人/换身份），必须人工过一遍。
#: @为什么必须单列这一栏：这一轮最贵的教训就是外部评审建议「把'沈砚'改为'别问'」，
#: 而「沈砚」是楼名 + 人名 + 规矩 + 口头禅四合一的双关。照改一本书就废了。
#: [EN] Prescriptions containing these words want to change the setting (rename / cut a
#: [EN] character). They must be reviewed by a human: the measured case proposed renaming
#: [EN] a pun that is simultaneously the building, the owner, the rule and his catchphrase.
_SETTING_CHANGE = re.compile(r'改名|改为|换成|删掉这个|不叫|应改为|统一定为')


@dataclass
class Item:
    """一条被拆开的批评。"""
    index: int
    title: str
    kind: str = ''                       # 批评类型（空 = 没认出来）
    claim: str = ''                      # 它说的数字/现象
    verdict: str = 'unverifiable'        # confirmed / exaggerated / refuted / unverifiable
    measured: str = ''                   # 我方实测（带数字）
    fix: str = ''                        # **我方**的修法（不用它给的）
    note: str = ''
    prescription: str = ''               # 它给的处方原文
    prescription_risky: bool = False

    def line(self) -> str:
        tag = {'confirmed': '✓ 成立', 'exaggerated': '~ 夸大',
               'refuted': '✗ 反驳', 'unverifiable': '? 无法验证'}[self.verdict]
        s = f'{tag}｜{self.title}'
        if self.measured:
            s += f'｜实测：{self.measured}'
        if self.prescription_risky:
            s += '｜⚠ 处方会改设定，勿照改'
        return s


def split_items(text: str) -> list[tuple[str, str]]:
    """把一份自由文本的评审拆成 `[(标题, 正文), ...]`。

    认三种常见的分条写法（都在真实报告里出现过）：
      · `【问题1】标题`
      · `## 1. 标题` / `一、标题`
      · `问题1：标题`
    ⚠ 拆不出来就返回空列表（调用方据此退回"整段当一条 `unverifiable`"），
      **不许瞎猜标题** —— 拆错会把 A 的实测挂到 B 头上。
    """
    raw = str(text or '')
    pats = [
        re.compile(r'^\s*【问题\s*(\d+)】\s*(.*)$', re.M),
        re.compile(r'^\s*(?:##+\s*)?(?:问题)?\s*(\d+)[.、]\s*(.*)$', re.M),
        re.compile(r'^\s*([一二三四五六七八九十]+)、\s*(.*)$', re.M),
    ]
    for pat in pats:
        marks = list(pat.finditer(raw))
        if len(marks) >= 2:
            out = []
            for i, m in enumerate(marks):
                end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
                out.append((m.group(2).strip()[:40], raw[m.end():end]))
            return out
    return []


def _classify(title: str, body: str) -> str:
    """标题 + 正文 → 批评类型（认不出返回空串）。**标题优先**。"""
    for kw, kind in _KEYWORDS:
        if kw in title:
            return kind
    for kw, kind in _KEYWORDS:
        if kw in body[:120]:
            return kind
    return ''


def _claimed_number(body: str) -> tuple[int, str]:
    """它说了个什么数。返回 `(数字, 原文片段)`；没有返回 `(0, '')`。

    ⚠ 只认 `N 次 / N 处 / N 句`。`7个谜团` 这种**不认** —— "谜团"的个数没法核。
    """
    m = re.search(r'(\d+)\s*(?:次|处|句|个)', body)
    if not m:
        return 0, ''
    return int(m.group(1)), m.group(0)


# ── 各验证器：返回 `(verdict, measured, fix)` ──

def _v_name(text: str, names, claimed: int) -> tuple[str, str, str]:
    from crew import name_guard as NG
    cand = [n for n in (names or ()) if NG.collides(str(n))]
    if not cand:
        return 'refuted', '没有形似常用短语的人名', ''
    total = 0
    detail = []
    for n in cand:
        hits = NG.risky_positions(text, str(n))
        total += len(hits)
        if hits:
            detail.append(f'「{n}」{len(hits)} 处')
    if total == 0:
        return 'refuted', '名下有歧义风险的人名，但正文里没有会被误读的位置', ''
    fixes = ('句首人名后面加身份标记（「掌柜沈砚…」）或用介词隔开（「沈砚对柳氏…」）；'
             '**不许改名** —— 形似常用短语的名字往往是刻意设计')
    if claimed and claimed > total * 2:
        return 'exaggerated', f'实际只有 {total} 处（{"、".join(detail)}）', fixes
    return 'confirmed', f'{total} 处（{"、".join(detail)}）', fixes


def _v_actions(text: str, _names, claimed: int) -> tuple[str, str, str]:
    # ★ 口径**只有一处实现**（`global_checks.action_density`）——
    #   这里再写一份正则，两处迟早漂开（项目的老教训）。
    from crew import global_checks as GC
    d = GC.action_density(text)
    zh, n, per = d['zh'], d['n'], d['per_k']
    # 阈值来自这一轮实测：望江楼 6 处/692 字 ≈ 8.7 处每千字，
    # 而外部评审说"大量"。8 处每千字对茶馆戏不算异常（倒茶续水本来就是戏）。
    measured = f'{n} 处 / {zh} 字（每千字 {per:.1f} 处）'
    fix = ('只挑**与人物心理相反**的动作留下（说"不记得"、手却抖），'
           '其余压到每段不超过 2 个')
    # ⚠ 这里原来还有一道 `zh < 120` —— 它和下面的 `judged`（<300）**重复**，
    #   而且更窄 ⇒ 短文本永远走不到 `judged` 那条分支，于是
    #   "把 judged 硬设成 True" 这种变异**改不动行为**（反例法 M39 一开始就是这么隐身的）。
    #   两道闸都在管同一件事时，**只留一个**，否则另一条是死代码。
    # [EN] The old `zh < 120` guard duplicated (and was narrower than) `judged`, so short
    # [EN] texts never reached the `judged` branch and the M39 mutation could not bite.
    if n == 0:
        return 'unverifiable', measured, fix
    if claimed and claimed >= n * 2:
        return 'exaggerated', measured + f'，它说 {claimed} 处', fix
    # ⚠ 阈值 `ACTION_PER_K` 是**量过真人之后**才定的（见 `developers/probe_action.py`）。
    if not d.get('judged', True):
        # 样本太短：**验不了**，不判"没超"（那会是一句自相矛盾的结论）
        return 'unverifiable', measured + f'（不足 {d.get("need", 300)} 字，样本太小）', fix
    if not d['over']:
        return 'refuted', measured + f'（未超过 {d["limit"]}）', ''
    return 'confirmed', measured, fix


def _v_detector(kind: str, text: str) -> tuple[str, str, str]:
    """走 `prose_flow` 里已有的确定性检测器。"""
    from crew import prose_flow as PF
    fn = {'元叙述': PF.meta_narration_issues, '感知越界': PF.percept_issues,
          '问答悬空': PF.qa_drift_issues, '道具循环': PF.prop_cycle_issues,
          '平铺段': PF.flat_span_issues, '憋气段': PF.long_span_issues}.get(kind)
    if fn is None:
        return 'unverifiable', f'「{kind}」没有登记验证器', ''
    try:
        hits = fn(text)
    except Exception as e:                                       # noqa: BLE001
        return 'unverifiable', f'检测器报错：{type(e).__name__}', ''
    n = len(hits)
    if n == 0:
        return 'refuted', '检测器命中 0 处', ''
    return 'confirmed', f'检测器命中 {n} 处', '按该检测器对应的修复合约处理'


def adjudicate(report_text: str, *, text: str,
               names=()) -> list[Item]:
    """**主入口**：把一份评审意见拆条、逐条量、分级。

    `text` 是被评审的那段正文（用于实测）；`names` 是作品里的人物名
    （人名歧义要用它 —— **从设定取，不从正文猜**）。
    """
    chunks = split_items(report_text)
    if not chunks:
        chunks = [('（未分条）', str(report_text or ''))]

    items: list[Item] = []
    for i, (title, body) in enumerate(chunks, 1):
        kind = _classify(title, body)
        claimed, claimed_raw = _claimed_number(body)
        it = Item(index=i, title=title or f'第 {i} 条', kind=kind,
                  claim=claimed_raw)
        # 处方：取"修复方法"那一段（有就摘出来，只用来判风险）
        m = re.search(r'修复方法[：:]\s*(.{0,200})', body, re.S)
        if m:
            it.prescription = m.group(1).strip()
            it.prescription_risky = bool(_SETTING_CHANGE.search(it.prescription))

        vname = VERIFIERS.get(kind, '')
        if not vname:
            it.verdict = 'unverifiable'
            it.measured = ('这一类**没有可数代理**' if kind else '认不出属于哪一类')
            it.note = ('真人与真跑在这上面分不开（实测），硬做检测器会误伤；'
                       '交给人工或顾问')
        elif vname == 'name':
            it.verdict, it.measured, it.fix = _v_name(text, names, claimed)
        elif vname == 'actions':
            it.verdict, it.measured, it.fix = _v_actions(text, names, claimed)
        else:
            it.verdict, it.measured, it.fix = _v_detector(kind, text)
        items.append(it)
    return items


def lessons(items, *, by_rule: bool = True) -> list[dict]:
    """把 `confirmed` 的条目转成 Reflexion 能吃的教训。

    ⚠ **只用 `confirmed`**。`exaggerated` 不进 —— 按被放大的数字去改会过度矫正；
      `refuted` 不进 —— 那是错的；`unverifiable` 不进 —— 没验过的东西不该驱动改写。
    """
    out = []
    for it in items or ():
        if getattr(it, 'verdict', '') != 'confirmed':
            continue
        out.append({
            'label': it.kind or it.title,
            'why': f'外部评审指出「{it.title}」，实测{it.measured}',
            'advice': it.fix or '按检测器对应的修复合约处理',
            'span': '',
        })
    return out


def markdown(items, *, title: str = '外部评审分诊') -> str:
    """一份给人看的分诊表（进 `导出/反思记录.md`）。"""
    L = [f'## {title}', '',
         '| # | 判定 | 批评 | 实测 | 我方修法 |',
         '|---|---|---|---|---|']
    for it in items or ():
        tag = {'confirmed': '**✓ 成立**', 'exaggerated': '~ 夸大',
               'refuted': '✗ 反驳', 'unverifiable': '? 无法验证'}[it.verdict]
        L.append(f'| {it.index} | {tag} | {it.title[:24]} | '
                 f'{it.measured[:34]} | {(it.fix or "—")[:30]} |')
    risky = [it for it in (items or ()) if it.prescription_risky]
    if risky:
        L += ['', '> ⚠ **这些处方要求改动设定，不要照改**：']
        for it in risky:
            L.append(f'> · 第 {it.index} 条：{it.prescription[:60]}')
        L.append('> 形似常用短语的人名往往是刻意的双关（楼名/人名/规矩同形时尤其如此）。')
    n_ok = sum(1 for it in (items or ()) if it.verdict == 'confirmed')
    L += ['', f'共 {len(items or ())} 条：成立 {n_ok} 条'
              f'（只有这些会进改写的教训库），其余**不驱动改写**。', '']
    return '\n'.join(L)


__all__ = ['Item', 'split_items', 'adjudicate', 'lessons', 'markdown', 'VERIFIERS']
