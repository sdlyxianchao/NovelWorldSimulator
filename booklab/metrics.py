# -*- coding: utf-8 -*-
"""拆书的**定量层**：用纯统计给"这本书怎么写"提供一层**不靠模型**的佐证。

为什么要有它（外部调研第 04/06 类都指向同一个问题）
--------------------------------------------------
拆书现在**全由 LLM 下结论**（"节奏很快""对话很密"）。这有两个毛病：

1. **没法复核**。模型说"这本书对话密集"，你只能信；而"引号内字数占比 41%"
   是能自己算的，两边对不上就是有问题。
2. **模型会附和**。它读到"节奏快"这个说法之后，后面的笔记会一路顺着说。

⇒ 这个模块把一层**可复算**的数字摆出来，让 LLM 的结论有地方对着站。
参考：`QQ-L-XX/novel-deconstruct`（**MIT**）的定量扫描步骤；
指标定义由本项目自己定（针对中文，与 `style/ai_metrics.py` 口径一致但**用途不同**）。

★ 与 `style/ai_metrics.py` 的分工（**别混用**）
--------------------------------------------
- `style/ai_metrics` 判的是「**像不像 AI 写的**」（突发度 / 句首多样性 / 文体漂移），
  用在**质量门**上，拿作者的**定稿**当基线；
- 这里量的是「**这本书怎么写**」（对话多不多 / 句子长不长 / 虚词重不重），
  用在**拆书**上，拿**被拆的那本书**当对象。

两者都算句长，但一个是为了"对不对"，一个是为了"是什么"。

English:
The **quantitative layer** of book deconstruction: use pure statistics to provide a layer of
**model-independent** evidence for "how this book is written".
Why it exists (external research categories 04/06 both point to the same problem)
--------------------------------------------------
Book deconstruction is currently **entirely concluded by the LLM** ("fast pacing", "dense
dialogue"). This has two flaws:
1. **Not verifiable**. When the model says "this book is dialogue-dense", you can only trust it; whereas "quoted character ratio 41%"
   can be computed yourself, and if the two disagree, something is wrong.
2. **The model will agree with itself**. After it reads the phrase "fast pacing", later notes will follow along with it all the way.
=> This module puts a layer of **recomputable** numbers on the table, giving the LLM's
conclusions something to stand against.
Reference: the quantitative scanning step of `QQ-L-XX/novel-deconstruct` (**MIT**);
metric definitions are set by this project itself (targeting Chinese, consistent with
`style/ai_metrics.py` in calibration but with a **different purpose**).
★ Division of labor with `style/ai_metrics.py` (**do not mix them up**)
--------------------------------------------
- `style/ai_metrics` judges "**does it look AI-written**" (burstiness / sentence-start diversity / style drift),
  used on the **quality gate**, taking the author's **final draft** as baseline;
- Here we measure "**how this book is written**" (lots of dialogue or not / long sentences or not / heavy function words or not),
  used on **book deconstruction**, taking **the book being deconstructed** as the object.
Both compute sentence length, but one is for "is it right", the other for "what is it".
"""
from __future__ import annotations

import re
import statistics

#: 中文虚词（**疲劳词**）—— 它们本身没有错，密度过高说明文字发软。
#: ⚠ 这张表是**本项目自己整理**的常见虚词，不是从别处抄的。
# [EN] : Chinese function words (**fatigue words**) - they are not wrong in themselves, but excessive
# [EN] density means the prose is soft.
# [EN] : ⚠ This table is **compiled by this project itself**, not copied from elsewhere.
FATIGUE_WORDS: tuple[str, ...] = ('的', '了', '着', '是', '就', '都', '很', '也', '在', '和')
#: 虚词密度的警戒线（每千汉字出现次数）。超过它就该在报告里说一句。
# [EN] : Warning threshold for function-word density (occurrences per thousand Chinese characters).
# [EN] Above it, the report should say something.
FATIGUE_ALERT = 55.0
#: 短句的界（不超过几个汉字算"短句"）
# [EN] : Bound for short sentences (at most how many Chinese characters counts as a "short sentence")
SHORT_SENTENCE = 8

_HAN = re.compile(r'[\u4e00-\u9fff]')
_QUOTE = re.compile(r'[「『“"]([^」』”"]{1,400})[」』”"]')
_SENT_SPLIT = re.compile(r'[^。！？!?…；;\n]*[。！？!?…；;]?')


def _han_len(s: str) -> int:
    return len(_HAN.findall(s or ''))


def sentences(text: str) -> list[str]:
    """切句（与 `util.text.sentences_zh` 同一套口径：**保留标点、不切空句**）。
        English:
    Sentence splitting (same calibration as `util.text.sentences_zh`: **keep punctuation, do not
    split empty sentences**).
    """
    out: list[str] = []
    for line in str(text or '').splitlines():
        for m in _SENT_SPLIT.finditer(line):
            s = m.group(0).strip()
            if s:
                out.append(s)
    return out


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r'\n\s*\n', str(text or '')) if p.strip()]


def scan(text: str) -> dict:
    """一本书（或一段正文）的定量画像。**纯本地、零成本、可复算。**
        English:
    A quantitative portrait of a book (or a passage of body text). **Purely local, zero cost,
    recomputable.**
    """
    src = str(text or '')
    han = _han_len(src)
    if han < 50:
        return {'汉字数': han, '可用': False,
                '说明': '正文太短（不足 50 汉字），定量指标不可信'}
    ss = sentences(src)
    ps = paragraphs(src)
    lens = [_han_len(s) for s in ss]
    lens = [x for x in lens if x > 0]
    plens = [_han_len(p) for p in ps]
    plens = [x for x in plens if x > 0]
    # 对话：引号里的字数占全文的比例（对白密度）
    # [EN] Dialogue: ratio of characters inside quotes to the full text (dialogue density)
    quoted = sum(_han_len(m.group(1)) for m in _QUOTE.finditer(src))
    # 虚词密度
    # [EN] Function-word density
    fat = {w: src.count(w) for w in FATIGUE_WORDS}
    fat_total = sum(fat.values()) / max(1, han) * 1000.0
    # 词面重复：4 字滑动窗的**重复占比** = 1 − 不同窗数 / 总窗数
    # ⚠ 2026-10-10 修：第一版写的是 `sum(出现≥2次的窗的总次数) / 不同窗数` ——
    #   那个比值**没有上界**（一段重复文本能算出 10.5），既不叫"率"也没法和
    #   别的书比。判据 I11e 用一段重复文本试的时候把它试出来了。
    # [EN] Surface repetition: **repetition ratio** of 4-character sliding windows = 1 - distinct window
    # [EN] count / total window count
    # [EN] ⚠ Fixed 2026-10-10: the first version wrote `sum(total count of windows appearing >= 2 times) /
    # [EN] distinct window count` --
    # [EN] that ratio **has no upper bound** (a repeated passage could compute to 10.5), is not a "rate",
    # [EN] and cannot be
    # [EN] compared across books. Criterion I11e exposed this when testing it with a repeated passage.
    body = _HAN.findall(src)
    total_win = max(0, len(body) - 3)
    ngram: dict[str, int] = {}
    for i in range(total_win):
        g = ''.join(body[i:i + 4])
        ngram[g] = ngram.get(g, 0) + 1
    repeat = (1.0 - len(ngram) / total_win) if total_win else 0.0
    out: dict = {
        '可用': True,
        '汉字数': han,
        '段落数': len(ps),
        '段长中位': round(statistics.median(plens), 1) if plens else 0,
        '句数': len(lens),
        '句长中位': round(statistics.median(lens), 1) if lens else 0,
        '句长均': round(statistics.fmean(lens), 1) if lens else 0,
        '短句占比': round(sum(1 for x in lens if x <= SHORT_SENTENCE) / len(lens), 3)
        if lens else 0,
        '对白占比': round(quoted / han, 3),
        '虚词密度': round(fat_total, 1),
        '四字重复率': round(repeat, 4),
    }
    out['疲劳词'] = {w: c for w, c in sorted(fat.items(), key=lambda kv: -kv[1])[:5]}
    # ★ 两档分开：`提示`= 真的越线（该看一眼），`特征`= 中性描述（用来对照）
    # [EN] ★ Two tiers kept separate: `hint` = actually over the line (worth a look), `trait` = neutral
    # [EN] description (for comparison)
    out['提示'] = _hints(out)
    out['特征'] = _traits(out)
    return out


def _hints(m: dict) -> list[str]:
    """**越线警告** —— 只放真正反常的（阈值取**极端**档）。

    ★★ 2026-10-10 修：第一版把"特征"和"越线"混在一栏里念（"句长中位 8 字——
      短句为主"也当一条提示），于是**一段完全正常的文本能刷出五条提示**，
      而那正是这个模块自己声明要避免的（"不把七个数字原样念一遍"）。
      判据 I11e 用一段正常文本把它试出来了。
      ⇒ 现在分两档：`提示`（越线）与 `特征`（中性描述），阈值的取法也不同 ——
        句长 8 字对明清白话**是正常的**，不该当警告（本项目作者定稿就大量用短句）。
    
        English:
    **Over-the-line warnings** -- only include genuinely abnormal ones (thresholds take the
    **extreme** tier).
        ★★ Fixed 2026-10-10: the first version read "traits" and "over-the-line" mixed in one column ("median sentence length 8 chars --
          mostly short sentences" was also treated as a hint), so **a completely normal passage could produce five hints**,
          which is exactly what this module itself declares it wants to avoid ("do not read the seven numbers back verbatim").
          Criterion I11e exposed this when testing it with a normal passage.
          => Now split into two tiers: `hint` (over the line) and `trait` (neutral description), with different threshold choices --
            a sentence length of 8 chars is **normal** for Ming-Qing vernacular, and should not be a warning (this project's author uses many short sentences in final drafts).
    """
    out: list[str] = []
    if not m.get('可用'):
        return out
    if m['虚词密度'] >= FATIGUE_ALERT:
        top = '、'.join(f'{k}{v}' for k, v in list(m.get('疲劳词', {}).items())[:3])
        out.append(f"虚词密度 **{m['虚词密度']}**/千字（警戒 {FATIGUE_ALERT}）—— 偏软；"
                   f"最多的几个：{top}")
    if m['四字重复率'] >= 0.12:
        out.append(f"四字组合重复率 **{m['四字重复率']:.3f}**"
                   f"（1 − 不同四字窗 / 总窗数）—— 用词有明显反复（可能是风格，也可能是凑字）")
    if m['段长中位'] >= 150:
        out.append(f"段长中位 **{m['段长中位']}** 字 —— 段落极长（读者会觉得闷）")
    if m['句长中位'] >= 30:
        out.append(f"句长中位 **{m['句长中位']}** 字 —— 句子极长")
    if m['对白占比'] >= 0.5:
        out.append(f"对白占 **{m['对白占比']:.0%}** —— 几乎全靠对话推进")
    elif m['对白占比'] <= 0.02:
        out.append(f"对白只占 **{m['对白占比']:.0%}** —— 几乎没有对话")
    return out


def _traits(m: dict) -> list[str]:
    """**中性特征**（不是问题）—— 这些是"这本书长什么样"的描述。

    它们进报告是为了让人**对照模型写的那几条**有没有说反
    （模型说"对话密集"而这写着 7%，那就该回去核）。
    
        English:
    **Neutral traits** (not problems) -- these are descriptions of "what this book looks like".
        They go into the report so people can **cross-check the few items the model wrote** for reversals
        (if the model says "dialogue-dense" but this says 7%, then go back and verify).
    """
    out: list[str] = []
    if not m.get('可用'):
        return out
    if m['对白占比'] >= 0.35:
        out.append(f"对白占 **{m['对白占比']:.0%}**（引号内字数/全文）—— 靠「人说」推进")
    elif m['对白占比'] <= 0.08:
        out.append(f"对白只占 **{m['对白占比']:.0%}** —— 基本靠叙述推进")
    if m['句长中位'] >= 24:
        out.append(f"句长中位 **{m['句长中位']}** 字 —— 长句为主")
    elif m['句长中位'] <= 11:
        out.append(f"句长中位 **{m['句长中位']}** 字 —— 短句为主")
    if m['段长中位'] >= 90:
        out.append(f"段长中位 **{m['段长中位']}** 字 —— 段落很长（多是「一大段到底」）")
    elif m['段长中位'] <= 25:
        out.append(f"段长中位 **{m['段长中位']}** 字 —— 段落切得很勤")
    if m['短句占比'] >= 0.45:
        out.append(f"短句（≤{SHORT_SENTENCE} 字）占 **{m['短句占比']:.0%}** —— 节奏靠短句顶")
    return out


def render_block(m: dict, *, title: str = '这本书的定量画像（量出来的，不是判断）') -> str:
    """渲染成报告里的一节。**没有可用数字时返回空串**（宁可不写，也不写"数据不足"）。
        English:
    Render as a section in the report. **Return an empty string when no numbers are available**
    (rather than write "insufficient data", prefer not to write at all).
    """
    if not m.get('可用'):
        return ''
    lines = [f'## {title}', '',
             '| 指标 | 值 | 怎么读 |',
             '|---|---|---|',
             f"| 汉字数 | {m['汉字数']} | 这次真正读到的量 |",
             f"| 段落数 / 段长中位 | {m['段落数']} / {m['段长中位']} 字 | 段长小 = 断段勤 |",
             f"| 句数 / 句长中位 | {m['句数']} / {m['句长中位']} 字 | |",
             f"| 短句占比（≤{SHORT_SENTENCE} 字） | {m['短句占比']:.0%} | 高 = 靠短句做节奏 |",
             f"| 对白占比 | {m['对白占比']:.0%} | 引号内字数 / 全文 |",
             f"| 虚词密度 | {m['虚词密度']}/千字 | 越高文字越软（警戒 {FATIGUE_ALERT}） |",
             f"| 四字重复率 | {m['四字重复率']:.3f} | 用词的反复程度 |",
             '']
    lines.append('> ⚠ 这些是**量出来的数字**，不是对好坏的判断 ——')
    lines.append('> 数字只用来核对面那部分（模型写的那几条）有没有说过头。')

    def _section(title: str, items: list[str]) -> None:
        if items:
            lines.append('')
            lines.append(f'**{title}**：')
            lines.append('')
            lines.extend(f'- {x}' for x in items)

    # ★ 两档分开：上面那些是**越线**（该看一眼），这里是**中性描述**（用来对照）
    # [EN] ★ Two tiers kept separate: the above are **over the line** (worth a look), these are **neutral
    # [EN] descriptions** (for comparison)
    _section('这本书长什么样（中性描述，不是问题）', m.get('特征') or [])
    _section('值得看一眼的', m.get('提示') or [])
    return '\n'.join(lines) + '\n'
