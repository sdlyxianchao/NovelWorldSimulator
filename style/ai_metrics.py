# -*- coding: utf-8 -*-
"""文风的**连续指标**与**文体漂移**（2026-10-10 新增）。

为什么要有这一层
================
本项目的「去 AI 味」原来是**词表级**的（`style/deai.py`）：命中/不命中某个词、
给一份清单。它能告诉你"哪句用了套路词"，但**说不出"这段文字整体像不像人写的"**
—— 而 AI 腔最典型的表现恰恰不在个别词上，在**节奏**上：
句子长度过于均匀、句首过于雷同、四五个字的小段反复出现。

所以这里补的是一组**连续量**（不是二值判断），让"去 AI 味"从"有/无命中"
升级成"有分数、能比较"。

口径来源（都是读代码/论文得来的，不是拍的）
==========================================
* **突发度 / 句长变异 / n-gram 重复率 / 句首多样性** —— 取自 `lmscan`
  （<https://github.com/stef41/lmscan>，**Apache-2.0**，2026-10-10 读的
  `features.py`）。它那几项是英文口径，本模块**自己重写了中文版**
  （英文函数词表一律不用 —— 中文明清白话里没有 the/a/of 那种东西）。
* **滑窗文体漂移的四态与阈值** —— 取自 `pystylometry`
  （<https://github.com/craigtrim/pystylometry>，**MIT**，2026-10-10 读的
  `consistency/drift.py` 与 `_thresholds.py`）。阈值取它的常量：
  `UNIFORM_CV=0.15` / `SPIKE_RATIO=2.5` / `TREND_SLOPE=5.0` / `TREND_R²=0.3`。
* **中文分句正则** —— 参考 `Hello-SimpleAI/chatgpt-comparison-detection`
  的 `sent_cut_zh` 的**思路**（那个仓库**没有 LICENSE** ⇒ 只学思路、不抄代码）。

⚠ 诚实说明：这些指标是**启发式**，它们描述"像不像"，**不判定"是不是 AI 写的"**。
   用它来**比较**同一位作者/同一部书的前后变化，比用它来下结论可靠得多。

用法
----
    from style.ai_metrics import analyze
    m = analyze(text)
    print(m['句长变异'], m['四字重复率'], m['漂移']['态'])

    # 命令行（可读报告）
    .venv/Scripts/python.exe -m style.ai_metrics 使用说明.md
    .venv/Scripts/python.exe -m style.ai_metrics --json 正文.md

English:
The **continuous metrics** and **stylistic drift** of writing style (added 2026-10-10).
Why this layer exists
================
This project's "de-AI-flavor" was originally **word-list level** (`style/deai.py`): whether a
word hits or not,
giving a checklist. It can tell you "which sentence used cliché words", but **cannot say
"whether this passage as a whole reads like a human wrote it"**
-- and the most typical manifestation of AI flavor isn't in individual words at all, it's in the
**rhythm**:
sentence lengths too uniform, sentence openings too similar, small 4-5 character paragraphs
recurring.
So what's added here is a set of **continuous quantities** (not binary judgments), letting
"de-AI-flavor" go from "hit/no-hit"
to "has a score, can be compared".
Provenance of the methodology (all obtained from reading code/papers, not made up)
==========================================
* **Burstiness / sentence-length variation / n-gram repetition rate / sentence-opening diversity** -- taken from `lmscan`
  (<https://github.com/stef41/lmscan>, **Apache-2.0**, read on 2026-10-10 from
  `features.py`). Those items are English methodology; this module **rewrote a Chinese version itself**
  (English function-word lists are not used at all -- Middle and Qing vernacular Chinese has no the/a/of kind of thing).
* **Four states and thresholds of sliding-window stylistic drift** -- taken from `pystylometry`
  (<https://github.com/craigtrim/pystylometry>, **MIT**, read on 2026-10-10 from
  `consistency/drift.py` and `_thresholds.py`). Thresholds take its constants:
  `UNIFORM_CV=0.15` / `SPIKE_RATIO=2.5` / `TREND_SLOPE=5.0` / `TREND_R²=0.3`.
* **Chinese clause-splitting regex** -- references the **idea** of
  `Hello-SimpleAI/chatgpt-comparison-detection`'s `sent_cut_zh` (that repo **has no LICENSE** ⇒ learn the idea only, don't copy code).
⚠ Honest disclaimer: these metrics are **heuristic**; they describe "reads like / doesn't read
like", they **do not judge "whether it was written by AI"**.
   Using them to **compare** the before-and-after changes of the same author/same book is far more reliable than using them to draw conclusions.
Usage
----
    from style.ai_metrics import analyze
    m = analyze(text)
    # Command line (readable report)
    .venv/Scripts/python.exe -m style.ai_metrics 使用说明.md
    .venv/Scripts/python.exe -m style.ai_metrics --json 正文.md
"""
from __future__ import annotations

import math
import re
import statistics
import sys

# ── 中文分句 ────────────────────────────────────────────────────────
# ⚠ **不能只用 `。！？` 切**：本项目要量的正是"短分句"的节奏
#   （作者定稿的分句中位只有 5 个字、≤5 字的分句占 51%），
#   所以逗号、顿号、分号、破折号也算**分句边界**。
#   这是"分句"（clause）不是"句子"（sentence）—— 名字里写清楚，
#   免得后来的人拿它当"句数"用。
# [EN] ── Chinese clause splitting ────────────────────────────────────────────────
# [EN] ⚠ **Cannot split only on `。！？`**: what this project measures is precisely the rhythm of "short
# [EN] clauses"
# [EN] (the author's finalized clause median is only 5 characters, clauses of ≤5 chars account for
# [EN] 51%),
# [EN] so commas, enumeration commas, semicolons, and dashes also count as **clause boundaries**.
# [EN] This is a "clause" not a "sentence" -- make it clear in the name,
# [EN] lest people later use it as "sentence count".

_NOISE_RE = re.compile(r'[\s\u3000]')


def clauses(text: str) -> list[str]:
    """切成**分句**（含标点、去掉空白）。空串不进结果。
        English:
    Split into **clauses** (including punctuation, removing whitespace). Empty strings don't enter
    the result.
    """
    out: list[str] = []
    for chunk in text.split('\n'):
        # 行内再按句末标点切
        # [EN] Within a line, split further on sentence-ending punctuation
        for part in re.findall(r'[^。！？；！?;]+[。！？；！?;]?', chunk):
            p = part.strip()
            if p:
                out.append(p)
    return out


def sentences(text: str) -> list[str]:
    """切成**句子**（只认句末标点 `.。！？!?`）。
        English:
    Split into **sentences** (only recognizes sentence-ending punctuation `.。！？!?`).
    """
    out: list[str] = []
    for chunk in re.split(r'[。！？!?]+', text):
        c = chunk.strip()
        if c:
            out.append(c)
    return out


def _han_len(s: str) -> int:
    """汉字个数（不含标点/空白/字母）。
        English:
    Number of Chinese characters (excluding punctuation/whitespace/letters).
    """
    return len(re.findall(r'[\u4e00-\u9fff]', s))


# ── 连续指标 ────────────────────────────────────────────────────────
# [EN] ── Continuous metrics ──────────────────────────────────────────────────────
def burstiness(lengths: list[int]) -> float | None:
    """突发度 = 句长的**变异系数** `std / mean`。

    人写的文字长短相间（有的十几字，有的两个字），AI 生成的更容易**整齐**
    ⇒ 这个值越小越"平"。`None` = 样本不够（少于 3 个）。
    
        English:
    Burstiness = **coefficient of variation** of sentence length `std / mean`.
        Human-written text alternates long and short (some a dozen-plus chars, some two chars); AI-generated is more likely to be **neat**
        ⇒ the smaller this value, the "flatter". `None` = insufficient sample (fewer than 3).
    """
    ll = [x for x in lengths if x > 0]
    if len(ll) < 3:
        return None
    mean = statistics.fmean(ll)
    if mean <= 0:
        return None
    return statistics.pstdev(ll) / mean


def ngram_repeat_ratio(text: str, n: int = 4) -> float | None:
    """**n-gram 重复率** = 1 − 不同 n-gram 数 / 总 n-gram 数。

    按**汉字**切（跳掉标点与空白）—— 中文的重复要看字串，不是看词。
    越高越像"车轱辘话"。`None` = 样本不够。
    
        English:
    **n-gram repetition rate** = 1 - number of distinct n-grams / total number of n-grams.
        Split by **Chinese characters** (skip punctuation and whitespace) -- repetition in Chinese should be measured on character strings, not on words.
        The higher, the more it resembles "circling talk". `None` = insufficient samples.
    """
    han = ''.join(re.findall(r'[\u4e00-\u9fff]', text))
    if len(han) < n * 4:
        return None
    grams = [han[i:i + n] for i in range(len(han) - n + 1)]
    if not grams:
        return None
    return 1.0 - len(set(grams)) / len(grams)


def opening_diversity(cl: list[str], k: int = 2) -> float | None:
    """**句首多样性** = 不同"开头 k 字"数 / 分句数。

    1.0 = 每个分句开头都不一样；越小说明翻来覆去那几个字起头
    （"他……他……他……"正是 AI 腔最明显的一种）。
    
        English:
    **Sentence-start diversity** = number of distinct "leading k characters" / number of clauses.
        1.0 = every clause starts differently; the smaller, the more it starts with the same few characters over and over.
        ("he... he... he..." is exactly one of the most obvious forms of AI tone).
    """
    if len(cl) < 4:
        return None
    heads = [_NOISE_RE.sub('', c)[:k] for c in cl if _han_len(c) >= k]
    if len(heads) < 4:
        return None
    return len(set(heads)) / len(heads)


# ── 滑窗文体漂移 ────────────────────────────────────────────────────
#: 取自 pystylometry 的阈值（见模块头）。**别随手改**：改之前先量一次基线。
UNIFORM_CV = 0.15        # 窗口内变异系数低于它 ⇒ 过于均匀
SPIKE_RATIO = 2.5        # 某窗口偏离中位数超过它倍 ⇒ 突变
TREND_SLOPE = 5.0        # 回归斜率超过它 ⇒ 持续漂移
TREND_R2 = 0.3           # 且拟合优度超过它
# [EN] ── Sliding-window stylistic drift ──────────────────────────────────────────
# [EN] : thresholds taken from pystylometry (see module header). **Don't change casually**: measure a
# [EN] baseline before changing.
# [EN] If the within-window coefficient of variation is below this ⇒ too uniform
# [EN] If some window deviates from the median by more than this multiple ⇒ spike
# [EN] If regression slope exceeds this ⇒ sustained drift
# [EN] and goodness of fit exceeds this

#: 至少要有这么多个窗口才敢给「漂移」的结论（少于它一律「样本不足」）。
#: ⚠ 这条不是保守，是**实测**：4 个窗口时 CV 天然很小，会把人写的文字误报成
#:   「过于均匀」（第一次拿一份现成定稿试就撞上了）。
# [EN] : at least this many windows are needed to dare conclude "drift" (fewer than this is always
# [EN] "insufficient sample").
# [EN] : ⚠ This is not conservatism, it's **measured**: with 4 windows the CV is naturally very small,
# [EN] which misreports human-written text as
# [EN] :   "too uniform" (hit this the first time testing on an existing finalized text).
_MIN_WIN = 6


def drift(text: str, *, window: int = 1000, overlap: float = 0.5) -> dict:
    """滑窗看**句长的均值是否一路在变**。返回四态之一。

    四态（沿用 pystylometry 的命名，中文注解）：
      · `一致`            —— 各窗口差不多，正常；
      · `过于均匀`        —— 全都短得一样（AI 腔的典型形状）；
      · `突变`            —— 某一窗口明显跳出（**换人写 / 拼接 / 复制粘贴**）；
      · `渐变漂移`        —— 一路单调地变长或变短（**风格在悄悄跑掉**）。
    
        English:
    Use a sliding window to check whether the **mean sentence length keeps changing throughout**.
    Return one of four states.
        Four states (following pystylometry naming, with Chinese annotations):
          · `consistent`       -- each window is about the same, normal;
          · `too uniform`      -- all are equally short (a typical shape of AI tone);
          · `sudden shift`     -- one window clearly jumps out (**changed writer / stitching / copy-paste**);
          · `gradual drift`    -- monotonically getting longer or shorter throughout (**style is quietly slipping away**).
    """
    han_len = len(re.findall(r'[\u4e00-\u9fff]', text))
    # ★★ 窗口**要跟着文本长度缩**（2026-10-10 实测教训，别删）：
    #   固定 1000 字窗、50% 重叠，在一篇 1896 字的**现成中文定稿**上只切出 **4 个窗** ——
    #   4 个数的「变异系数」当然小，于是判据把**人写的**文字报成「过于均匀」。
    #   pystylometry 那个 0.15 的阈值是在**长文档**上标定的，短文本直接套用会误报。
    #   ⇒ 文本不够长就把窗缩小到能切出 ≥`_MIN_WIN` 个窗；再不够就老实说「样本不足」。
    # [EN] ★★ The window **must shrink with text length** (tested lesson from 2026-10-10, don't delete):
    # [EN] A fixed 1000-char window with 50% overlap, on an **existing Chinese finalized text** of 1896
    # [EN] chars, cut out only **4 windows** --
    # [EN] The "coefficient of variation" of 4 numbers is of course small, so the criterion reports
    # [EN] **human-written** text as "too uniform".
    # [EN] pystylometry's 0.15 threshold was calibrated on **long documents**; applying it directly to
    # [EN] short text causes false positives.
    # [EN] ⇒ If the text isn't long enough, shrink the window until at least ≥`_MIN_WIN` windows can be
    # [EN] cut; if still not enough, honestly say "insufficient sample".
    win = int(window)
    if han_len < win * _MIN_WIN:
        win = max(200, han_len // _MIN_WIN)
    if win < 120 or han_len < win * _MIN_WIN:
        return {'态': '样本不足', '窗数': 0, '均值序列': [],
                '说明': f'需要至少 {_MIN_WIN} 个窗口，每窗约 {win} 字；'
                        f'本文只有 {han_len} 汉字'}
    step = max(1, int(win * (1 - overlap)))
    series: list[float] = []
    for start in range(0, len(text) - win + 1, step):
        chunk = text[start:start + win]
        ll = [_han_len(c) for c in clauses(chunk)]
        ll = [x for x in ll if x > 0]
        if len(ll) >= 5:
            series.append(statistics.fmean(ll))
    if len(series) < _MIN_WIN:
        return {'态': '样本不足', '窗数': len(series), '均值序列': series}

    cv = (statistics.pstdev(series) / statistics.fmean(series)
          if statistics.fmean(series) > 0 else 0.0)
    med = statistics.median(series)
    spike = max(abs(x - med) / med for x in series) if med > 0 else 0.0
    # 一元线性回归（最小二乘）
    # [EN] Univariate linear regression (least squares)
    n = len(series)
    xs = list(range(n))
    mx, my = statistics.fmean(xs), statistics.fmean(series)
    den = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, series)) / den
    ss_tot = sum((y - my) ** 2 for y in series)
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, series))
    r2 = (1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    if cv < UNIFORM_CV:
        state = '过于均匀'
    elif spike >= SPIKE_RATIO:
        state = '突变'
    elif abs(slope) >= TREND_SLOPE and r2 >= TREND_R2:
        state = '渐变漂移'
    else:
        state = '一致'
    return {'态': state, '窗数': n, 'CV': round(cv, 4),
            '突跳比': round(spike, 3), '斜率': round(slope, 3),
            'R²': round(r2, 3),
            '均值序列': [round(x, 2) for x in series]}


# ── 一次算全 ────────────────────────────────────────────────────────
# [EN] ── Compute all at once ─────────────────────────────────────────────────────
def analyze(text: str) -> dict:
    """一份文字的全部连续指标（**纯本地、零成本、不调模型**）。
        English:
    All continuous metrics for a piece of text (**purely local, zero cost, no model calls**).
    """
    cl = clauses(text)
    ss = sentences(text)
    cl_lens = [_han_len(c) for c in cl]
    cl_lens = [x for x in cl_lens if x > 0]
    out: dict = {
        '分句数': len(cl_lens),
        '句数': len(ss),
        '汉字数': _han_len(text),
        '分句中位长': (statistics.median(cl_lens) if cl_lens else 0),
        '分句均长': (round(statistics.fmean(cl_lens), 2) if cl_lens else 0),
        # ≤5 字的分句占比：本项目作者定稿的基线是 **51%**，是最能区分"这种声音"的一个数
        # [EN] Proportion of clauses ≤5 chars: the project author's finalized baseline is **51%**, the single
        # [EN] number that best distinguishes "this voice"
        '≤5字分句占比': (round(sum(1 for x in cl_lens if x <= 5) / len(cl_lens), 4)
                        if cl_lens else None),
        '句长变异': burstiness(cl_lens),
        '四字重复率': ngram_repeat_ratio(text, 4),
        '五字重复率': ngram_repeat_ratio(text, 5),
        '句首多样性': opening_diversity(cl),
    }
    out['漂移'] = drift(text)
    return out


def render(m: dict, *, title: str = '') -> str:
    """把 `analyze()` 的结果排成人能读的几行。
        English:
    Format the result of `analyze()` into a few human-readable lines.
    """
    def f(v, nd=3):
        return '—' if v is None else (f'{v:.{nd}f}' if isinstance(v, float) else str(v))

    lines = []
    if title:
        lines.append(f'=== 文风连续指标 · {title} ===')
    lines += [
        f"  规模      {m['汉字数']} 汉字 / {m['分句数']} 分句 / {m['句数']} 句",
        f"  分句长    中位 {f(m['分句中位长'], 1)} 字 · 均 {m['分句均长']} 字 · "
        f"≤5 字占 {('%d%%' % round((m['≤5字分句占比'] or 0) * 100))}",
        f"  句长变异  {f(m['句长变异'])}   （越小越「平」；<0.35 要警惕）",
        f"  重复率    4-gram {f(m['四字重复率'])} · 5-gram {f(m['五字重复率'])}"
        f"   （越高越像车轱辘话）",
        f"  句首多样性 {f(m['句首多样性'])}   （越小越「翻来覆去那几个字起头」）",
        f"  文体漂移  {m['漂移']['态']}"
        + (f"（窗 {m['漂移']['窗数']} · CV {m['漂移'].get('CV')}）"
           if m['漂移'].get('窗数') else ''),
    ]
    return '\n'.join(lines)


def _main(argv: list[str]) -> int:
    import json
    as_json = '--json' in argv
    args = [a for a in argv if not a.startswith('--')]
    if not args:
        print(__doc__.split('用法\n----')[1].split('"""')[0].strip()
              if '用法\n----' in __doc__ else '用法：-m style.ai_metrics [--json] <文件>')
        return 2
    from pathlib import Path
    p = Path(args[0])
    if not p.exists():
        print('找不到文件：', p)
        return 2
    text = p.read_text(encoding='utf-8', errors='replace')
    m = analyze(text)
    if as_json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
    else:
        print(render(m, title=p.name))
    return 0


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv[1:]))
