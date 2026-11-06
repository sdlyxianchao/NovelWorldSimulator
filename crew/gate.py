# -*- coding: utf-8 -*-
"""后台质量门 —— **统一的一套扣分表 + 判定档 + 问题分级**。

来历（2026-10-10 外部调研，第 02 类第 3 条）
--------------------------------------------
`neopen/story-shot-agent`（PenShot，**MIT**）的 `quality_auditor_prompt.yaml`
把它那套审计做成了**完全确定性的评分表**：

    ERROR −50 · CRITICAL −30 · MAJOR −20 · MODERATE −10 · WARNING −5 · INFO −1
    总分 ≥90 → PASSED ／ 70–89 → NEEDS_REVIEW ／ <50 → FAILED
    每条问题带 **P0…P3** 分级 + 一句修复建议

它值得抄的**不是那几个数**（谁来定都行），而是三件事：

1. **扣分是惩罚制、从满分往下扣** —— 这与本项目质量层一直用的"越界指标个数"
   是两套思路，但**用在"一块产出的自检"上更合适**：自检要的是"这份东西能不能用"，
   不是一个可跨版本比较的分数。
2. **每档都有名字**（ERROR / CRITICAL / …）—— 只看一个数字不知道有多严重。
3. **每条问题都要带"改成什么"** —— 只报"这里不对"的审计没人看。

★ 与本项目已有质量层的关系（**别混用**，这条要记住）
-------------------------------------------------
`novelservices/MuMuAINovel/quality/` 那一层用的是 **区间制 + 字典序**，
因为那里要**跨轮/跨批次比较**（"这一版比上一版好吗"）——
凡是跨批比较的量，**必须与批次规模无关**（用"条数"当罚项曾被 27 条洪水顶爆过）。
这里这套**惩罚制**只用于**同一块产出的"过不过"**，不做跨版比较，
所以"条数越多扣越多"是合理的：问题多就是差。

⇒ 一句话：**跨版比较用区间制，单件过不过用惩罚制。**

English:
Background quality gate —— **a unified set of: deduction table + verdict tiers + issue
severity**.
Origin (2026-10-10 external research, category 02 item 3)
--------------------------------------------
`neopen/story-shot-agent` (PenShot, **MIT**)'s `quality_auditor_prompt.yaml`
turned its audit into a **fully deterministic scoring table**:
    ERROR −50 · CRITICAL −30 · MAJOR −20 · MODERATE −10 · WARNING −5 · INFO −1
    total ≥90 → PASSED / 70–89 → NEEDS_REVIEW / <50 → FAILED
    each issue carries **P0…P3** severity + a one-line fix suggestion
What's worth copying is **not those numbers** (anyone can set them), but three things:
1. **Deductions are a penalty system, starting from full marks and subtracting downward** —— this differs from the
   "count of out-of-bounds metrics" this project's quality layer has always used,
   but it **fits better for "self-check of a single piece of output"**: self-check is about "is this thing usable",
not a score comparable across versions.
2. **Every tier has a name** (ERROR / CRITICAL / …) —— a bare number doesn't tell you how severe it is.
3. **Every issue must carry "change it to what"** —— an audit that only reports "this is wrong"
gets ignored.
★ Relationship to this project's existing quality layer (**do not mix them**, remember this)
-------------------------------------------------
The layer at `novelservices/MuMuAINovel/quality/` uses **interval system + lexicographic
order**,
because there it must **compare across rounds/batches** ("is this version better than the last")
——
any quantity compared across batches **must be independent of batch size** (using "line count"
as a penalty once got blown up by a flood of 27 lines).
This **penalty system** here is only used for **"pass or not" of the same piece of output**, no
cross-version comparison,
so "more lines = more deduction" is reasonable: more problems means worse.
⇒ In one sentence: **cross-version comparison uses the interval system, single-item pass/fail
uses the penalty system.**
"""
from __future__ import annotations

# ── 扣分表（PenShot 的档位，原样采用）────────────────────────────
# [EN] ── Deduction table (PenShot's tiers, adopted as-is) ────────────────────────────
WEIGHTS: dict[str, int] = {
    'ERROR': 50,
    'CRITICAL': 30,
    'MAJOR': 20,
    'MODERATE': 10,
    'WARNING': 5,
    'INFO': 1,
}
FULL = 100
#: 判定档：`下限`（含）→ 档名。**从高往低排**，查表时找第一个够得着的。
# [EN] : Verdict tiers: `lower bound` (inclusive) → tier name. **Sorted high to low**; when looking up,
# [EN] find the first one you reach.
BANDS: tuple[tuple[int, str], ...] = ((90, 'PASSED'), (70, 'NEEDS_REVIEW'), (0, 'FAILED'))
#: 问题分级 → 严重档（P0 最重）。用于把同一条问题同时挂上"扣多少"和"多急"。
# [EN] : Issue severity → severity tier (P0 is the heaviest). Used to attach both "how many points" and
# [EN] "how urgent" to the same issue.
P_LEVEL: dict[str, str] = {'P0': 'ERROR', 'P1': 'CRITICAL', 'P2': 'MAJOR', 'P3': 'WARNING'}


def band(score: int) -> str:
    """总分 → 判定档。
        English:
    Total score → verdict tier.
    """
    for low, name in BANDS:
        if score >= low:
            return name
    return 'FAILED'


def cost(severity: str) -> int:
    """一档的扣分（认不出按 `MAJOR`，不按 0 —— **认不出不等于没问题**）。
        English:
    Deduction for a tier (unrecognized falls back to `MAJOR`, not 0 —— **unrecognized does not mean
    no problem**).
    """
    return WEIGHTS.get(str(severity).upper(), WEIGHTS['MAJOR'])


class Finding:
    """一条问题：**必须带"改成什么"**（没有修法的审计没人看）。

    `where` 是定位（第几场/第几个镜头/哪一句），`fix` 是一句可执行的话。
    
        English:
    Per issue: **must carry "change it to what"** (an audit with no fix gets ignored).
        `where` is the location (which scene / which shot / which line), `fix` is one actionable sentence.
    """

    __slots__ = ('severity', 'where', 'what', 'fix')

    def __init__(self, severity: str, where: str, what: str, fix: str = '') -> None:
        self.severity = str(severity).upper()
        self.where = str(where or '').strip()
        self.what = str(what or '').strip()
        self.fix = str(fix or '').strip()

    def __repr__(self) -> str:                                  # pragma: no cover
        return f'Finding({self.severity}, {self.where!r}, {self.what!r})'

    def line(self) -> str:
        s = f'[{self.severity}] {self.where}：{self.what}'
        return s + (f'　→ {self.fix}' if self.fix else '')


class Report:
    """一块产出的审计结果。
        English:
    Audit result for one piece of output.
    """

    __slots__ = ('target', 'findings')

    def __init__(self, target: str = '') -> None:
        self.target = str(target or '')
        self.findings: list[Finding] = []

    def add(self, severity: str, where: str, what: str, fix: str = '') -> None:
        self.findings.append(Finding(severity, where, what, fix))

    # `p0..p3` 只是 `add` 的糖，让调用点读起来像那份 YAML
    # [EN] `p0..p3` is just sugar for `add`, so call sites read like that YAML
    def p0(self, where: str, what: str, fix: str = '') -> None:
        self.add('ERROR', where, what, fix)

    def p1(self, where: str, what: str, fix: str = '') -> None:
        self.add('CRITICAL', where, what, fix)

    def p2(self, where: str, what: str, fix: str = '') -> None:
        self.add('MAJOR', where, what, fix)

    def p3(self, where: str, what: str, fix: str = '') -> None:
        self.add('WARNING', where, what, fix)

    @property
    def score(self) -> int:
        """满分往下扣，**夹在 0 以上**（负分没有意义，只会让人以为有额外惩罚）。
                English:
        Subtract from full marks, **clamped at 0 or above** (negative scores are meaningless and only
        make people think there's an extra penalty).
        """
        return max(0, FULL - sum(cost(f.severity) for f in self.findings))

    @property
    def verdict(self) -> str:
        return band(self.score)

    def passed(self) -> bool:
        return self.verdict == 'PASSED'

    def worst(self) -> str:
        """最重的那一档（没问题时给 `INFO`）。
                English:
        The heaviest tier (give `INFO` when there are no problems).
        """
        for sev in ('ERROR', 'CRITICAL', 'MAJOR', 'MODERATE', 'WARNING'):
            if any(f.severity == sev for f in self.findings):
                return sev
        return 'INFO'

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def render(self, *, title: str = '') -> str:
        head = title or f'质量门 · {self.target}' if self.target else '质量门'
        lines = [f'## {head}', '',
                 f'**得分 {self.score}/100 · 判定 {self.verdict}**'
                 + (f'（最重：{self.worst()}）' if self.findings else ''),
                 '']
        if not self.findings:
            lines.append('无问题。')
            return '\n'.join(lines) + '\n'
        c = self.counts()
        lines.append('扣分分布：' + ' · '.join(f'{k}×{v}' for k, v in
                                          sorted(c.items(), key=lambda kv: -WEIGHTS.get(kv[0], 0))))
        lines.append('')
        lines.append('| # | 档 | 位置 | 问题 | 改成什么 |')
        lines.append('|---|---|---|---|---|')
        for i, f in enumerate(self.findings, 1):
            lines.append(f'| {i} | {f.severity} | {f.where} | {f.what} | {f.fix or "—"} |')
        return '\n'.join(lines) + '\n'


def worst_of(reports: list[Report]) -> str:
    """多块产出合看时最重的判定档（`FAILED` 最重）。
        English:
    The heaviest verdict tier when multiple pieces of output are viewed together (`FAILED` is
    heaviest).
    """
    order = {'FAILED': 0, 'NEEDS_REVIEW': 1, 'PASSED': 2}
    if not reports:
        return 'PASSED'
    return min((r.verdict for r in reports), key=lambda v: order.get(v, 1))
