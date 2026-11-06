# -*- coding: utf-8 -*-
"""句法闸：**一段是不是被写成了"清单"**（2026-10-19）。

为什么要有这个模块
------------------
用户原话：「下面这样的小短句子特别多 每一句都恨不得交代一个事情 而没有像正常小说
一样 用长一些的句子慢慢描写」。

`crew/agents.Novelist._transcribe_once` 的提示词里已经写了很多条（长短交错、
别写成清单），**而产物照样是分镜表** —— 这是"prompt 里写了 ≠ 生效"的第 N 次实证。
所以这里给出一个**可算的判据**，让提示词之外还有一道闸：

  `list_like_spans(text)`   找出"连着三句以上、每句都在十字以内"的段落
  `long_sentence_ratio(text)` 长句（≥25 字）占比

判据不是最终目的 —— `_transcribe_once` 拿它**自检**：写出来若是清单，
把那几段挑出来重写一次（见 `rewrite_prompt`）。这样"约束"落在解析层，
而不是又加一句模型可以无视的话。

⚠ 三条边界（都是实测踩过的）
  · **对白天然短**：引号里的内容不计入 —— 否则"他说：'嗯。'"会被判成碎句；
  · **两个短句连用是正常的**（真人样本里到处都是）⇒ 门槛取 **3 句**，不是 2 句；
  · **跨度还要够长**（≥25 字），否则"他停了。她没动。屋里静。"
    这种短促的开场会被误伤（那是有意的节奏，不是清单）。

判据：`tools/verify_prose_flow.py` G 组。
"""
from __future__ import annotations

import re

#: 一句话最多几个汉字算"短"—— 真人样本里 4–6 字句占三成，所以"短"本身不判，
#: 判的是**连着短**。
SHORT_MAX = 10
#: 连着几句短句算"清单"。取 3：两个短句连用是正常节奏（真人样本大量存在）。
RUN_MIN = 3
#: 这一段至少多长才算清单（汉字数）。防止误伤「某地。某楼。某人的房间在二楼。」
#: 这类**有意的短促开场**（实测误伤过 —— 地点三连是有节奏的，不是分镜表）。
SPAN_MIN_CHARS = 30
#: "长句"的门槛（汉字数）：提示词里给模型的是"二十五个字以上"，这里同口径。
LONG_MIN = 25
#: **一个句号里最多几个汉字**（含容差）—— 与提示词"不超过四十个字"同口径。
#: ★★★ 2026-10-19 第二次真跑加：第一版只治"太碎"，结果矫枉过正 ——
#:   模型把整段写成一条**逗号长龙**（句长中位 12 → 31 字、最长 69 字），
#:   而 `list_like_spans` 一条都不报（因为整段"有长句"，看着"铺开了"）。
#:   ⇒ 钟摆的两头都要判：**太碎**和**太长**是同一种病（都是没有节奏）。
# [EN] Max CJK characters inside one full stop. Added after the second real run: the first version
# [EN] only treated "too choppy", so the model overcorrected into one long comma chain (median
# [EN] 12 -> 31 chars, longest 69) and `list_like_spans` reported nothing (the paragraph "has long
# [EN] sentences", so it looks opened up). Both ends of the swing must be judged.
SENTENCE_MAX = 45

_QUOTED = re.compile(r'[“"「『]([^”"」』]*)[”"」』]')
_SENT = re.compile(r'[^。！？…]*[。！？…]+|[^。！？…]+$')
_CJK = re.compile(r'[\u4e00-\u9fff]')


def zh_len(s: str) -> int:
    return len(_CJK.findall(s))


def _strip_quotes(text: str) -> str:
    """把引号里的台词换成等长的空位（保留位置，方便回贴）。"""
    return _QUOTED.sub(lambda m: '\u3000' * len(m.group(0)), text)


def _bare_with_ends(text: str) -> str:
    """蒙掉台词，但**在台词收尾处留一个句末标记**（仍是等长替换，位置一一对应）。

    ★★★ 为什么必须有这一个（2026-10-20，`diag_quote_boundary.py` 量过）
    ---------------------------------------------------------------
    `_strip_quotes` 把台词连**里面的句号**一起蒙成空格。于是这种极常见的写法
    **整段并成一句**：

        他低头翻了翻膝头破旧洋装书：“书嘛，还是那些。”（14 字叙述）
        门外叶子声音清亮：“先生，您真的要在这里待上十天吗？”（9 字）
        岛村转向纸门：“嗯，待上十天，也没别的事。”（7 字）
        ……

    蒙完只剩「…书：　　　　　　门外叶子声音清亮：　　　　　　岛村转向纸门：…」，
    中间**一个句末标点都没有** ⇒ 61 字 / 85 字的"长句"就这么来的，
    而它其实是"多人对话连排"，读者一点不觉得憋气。
    ⇒ 台词收尾本身就是句子边界：最后一个字符位置放一个 `。`（长度不变，
      回贴位置照样对得上）。

    实测（真人 18 章 与各版真跑，`diag_quote_boundary.py`）：
      真人「太长」段数 中位 0 / 最大 1 —— **改前改后完全一样**（零误伤）；
      真跑 v19 4→1、v21 2→**0**、v22 2→**0**（误报消失）。
    [EN] Mask dialogue but leave a sentence-end marker where the quote closes. Without
    [EN] it, dialogue-heavy paragraphs collapse into one 61/85-char "long sentence"
    [EN] because every full stop sits inside the quotes and gets masked too.
    [EN] Measured: human chapters unchanged (median 0 / max 1), real runs 2 -> 0.
    """
    def _sub(m):
        s = m.group(0)
        return '\u3000' * max(0, len(s) - 1) + '。'
    return _QUOTED.sub(_sub, text)


def _sentences(text: str) -> list[tuple[int, int, int]]:
    """切成 (start, end, 汉字数)，**引号内的台词不算**。

    ⚠ 蒙引号用的是 `_bare_with_ends`（台词收尾留句末标记），不是 `_strip_quotes` ——
      详见那边的说明：用纯空位会把"多人对话连排"整段并成一句 61 字的长句，
      于是去重写一段本来没问题的对话。
    [EN] Masking uses `_bare_with_ends` (a sentence-end marker survives where a quote
    [EN] closes), not plain blanks -- otherwise dialogue runs merge into one long sentence.
    """
    bare = _bare_with_ends(text)
    out: list[tuple[int, int, int]] = []
    for m in _SENT.finditer(bare):
        n = zh_len(m.group(0))
        if n == 0:
            continue
        out.append((m.start(), m.end(), n))
    return out


def merge_one_line_paragraphs(text: str, *, min_lines: int = 4,
                              max_chars: int = 90, max_para: int = 220) -> str:
    """把"**一句一段**"的连续短行合并成正常段落。**只改换行，一个字不动。**

    ★★★ 为什么单独一步、而且不用模型（2026-10-19 第四次真跑）
    ------------------------------------------------------
    那一跑出现了这样的排版：

        驹子急切催他喝酒。
        岛村把火钵挪膝前。火光照纸门。
        自己在这儿倒叫她不好进来。

    每行一句 —— 读者读到的还是"一句一件事"，只是换行把它包装成了诗。
    这种形态**提示词治不了**（属于排版，不属于措辞），`list_like_spans`
    也抓不到（每行只有 1 句 < `RUN_MIN`）。⇒ 用纯代码合并：不调模型、不改一个字。

    ★★★ **空行不许打断连续判断**（2026-10-19 第八轮真跑，这条是补丁）
    ---------------------------------------------------------------
    第八轮整篇变成了"一句一段 + **每段之间一个空行**"：

        岛村靠窗边坐，驹子伏在火钵旁，头发散着。
        （空行）
        叶子将酒壶轻轻放在驹子身旁的矮几上，手指在壶身停留了一瞬。她收回手。
        （空行）

    第一版按"连续 `min_lines` 行"判，而空行会 `_flush()` ⇒ 每次攒到 1 行就断
    ⇒ **一行都没合并**（实测 44 行正文 / 47 个空行，全没动）。
    ⇒ 现在的规则：**空行算作"连续"**（模型用空行分的是"句子"，不是"段落"），
      只有遇到真正的段落（一行里多句、且都不短）才 flush。
    ⚠ 但也不能把整篇并成一段：门槛 `min_lines=4` 仍然管着 ——
      少于 4 个短行的地方原样保留（真人本来就有"一句成段"的写法）。
    [EN] Merge runs of "one sentence per line" into normal paragraphs. **Newlines only, not a
    [EN] single character changed.** ⚠ **Blank lines must not break the run** (round eight): the
    [EN] model wrote one sentence per line **with a blank line between each**, and the first
    [EN] version flushed on every blank line, so it accumulated one line at a time and merged
    [EN] **nothing** (44 body lines, 47 blanks, untouched). Blank lines now count as "continuous";
    [EN] only a real paragraph flushes. The `min_lines=4` floor still keeps genuine
    [EN] one-sentence paragraphs as they are.
    """
    lines = (text or '').split('\n')
    out: list[str] = []
    buf: list[str] = []          # 攒着的一句行（已 strip）
    gaps: list[int] = []         # 每一行**后面**跟着几个空行（合并时丢掉；不合并时原样还回去）

    def _is_one_line(s: str) -> bool:
        if not s or s.startswith(('#', '>', '▸', '·', '◇', '∿', '〔')):
            return False
        if len(s) > max_chars:
            return False
        return len([x for x in _sentences(s) if x[2] >= 2]) <= 2

    def _flush() -> None:
        if len(buf) >= min_lines:
            out.append(''.join(buf))          # 合并：中间的换行和空行一起不要
        else:
            # ⚠ 不合并时必须**原样还回去**（含空行）—— 第一版把空行吃了，
            #   于是"三句一段、段间空行"的正常排版被改成了"三行挤在一起"
            #   （判据 G7「正常的段落不许动」当场抓到）。
            # [EN] When not merging, **give the blank lines back verbatim**: the first version ate
            # [EN] them, so a normal "three sentences, blank line between" layout was squashed into
            # [EN] three consecutive lines (criterion G7 caught it).
            for x, g in zip(buf, gaps):
                out.append(x)
                out.extend([''] * g)
        buf.clear()
        gaps.clear()

    for ln in lines:
        s = ln.strip()
        if not s:
            # ⚠ 空行**不 flush**：它在模型笔下是"句子分隔"，不是"段落分隔"。
            #   只有已经攒着东西时才记下来（开头的空行照原样输出）。
            if buf:
                gaps[-1] = gaps[-1] + 1
            else:
                out.append(ln)
            continue
        if _is_one_line(s):
            # ⚠ **攒到一段够长就断**（第八轮实测）：空行不再 flush 之后，
            #   整篇 44 个短行会被并成 **2 段**（全篇一段），比原来更难读。
            #   一段给到 220 字（约 3–5 句）就另起一段 —— 真人一段也就这个量级。
            # [EN] ⚠ **Break once the paragraph is long enough**: after blank lines stopped
            # [EN] flushing, all 44 short lines merged into **2 paragraphs** (the whole piece as
            # [EN] one), which reads worse. Cap a paragraph at 220 chars (~3-5 sentences), which is
            # [EN] the size humans actually write.
            if buf and sum(len(x) for x in buf) + len(s) > max_para:
                _flush()
            buf.append(s)
            gaps.append(0)
            continue
        _flush()
        out.append(ln)
    _flush()
    # 收尾把连续空行压成一个（上面 flush 时已处理，这里兜底）
    res: list[str] = []
    for ln in out:
        if not ln.strip() and res and not res[-1].strip():
            continue
        res.append(ln)
    return '\n'.join(res)


def long_span_issues(text: str) -> list[tuple[int, int]]:
    """只找**太长**的段落（段内长句过半，或冒出一个超长句）。

    ★★★ 2026-10-20 从 `list_like_spans` 里拆出来，理由是一条硬证据：
      把「太平」（整段没有一句 ≥`LONG_MIN` 字的句子）和「太长」**分开量**：
        真人 18 章：太平 中位 **3**、最大 **9**；太长 中位 **0**、最大 **1**
        `snow_v21`：太平 **0**、太长 **2**
      ⇒ **「太平」在真人小说里满地都是**（真跑反而一个都没有），它不是病；
        拿它去改稿，就是**在改本来没问题的段落**。
        实测代价：`_fix_flat_paragraphs` 在 v21 上每重写一次，平铺段就多一段
        （2 → 3 → 6，多轮时越改越差），因为重写出来的段落更短、更容易被判成平铺。
      ⇒ 「太长」保留（真人有天花板 1），「太平」退出自动修复。
    [EN] Only the "too long" half. Split out after measuring the two halves separately:
    [EN] across 18 human chapters, flat paragraphs run median 3 / max 9 while long ones
    [EN] run median 0 / max 1; the real run had 0 flat and 2 long. "Flat" is how human
    [EN] prose is written, so rewriting those paragraphs damages healthy text -- measured
    [EN] (2 -> 3 -> 6 across rounds, each rewrite shorter and therefore "flatter").
    """
    out: list[tuple[int, int]] = []
    pos = 0
    for para in (text or '').split('\n'):
        start, pos = pos, pos + len(para) + 1
        p = para.strip()
        if not p or p.startswith(('#', '>')):
            continue
        sents = [x for x in _sentences(p) if x[2] >= 2]
        if len(sents) < RUN_MIN:
            continue
        if sum(x[2] for x in sents) < SPAN_MIN_CHARS:
            continue
        _long = sum(1 for x in sents if x[2] >= LONG_MIN)
        too_long = (_long * 2 > len(sents)) or any(x[2] >= SENTENCE_MAX for x in sents)
        if too_long:
            out.append((start, start + len(para)))
    return out


#: **一句一件事**的阈值：段内"逗号数 / 句子数"低于它就判。
#: ★★★ 这个口径是量出来的（2026-10-20 第三次修正，见 `flat_span_issues`）：
#:   真人 18 章 60 个叙述段的「逗号/句」最小 **0.25**、5% 分位 0.67、中位 1.00；
#:   真跑 v23 有两段是 **0.06 / 0.1**、v22 一段 0.17、v19 一段 0.23。
#:   取 **0.2**（比真人下限再留 20% 余量）：只抓"明显一句一件事"的段落，
#:   宁可漏改，不改坏 —— 真人那种「三年前二月，宣阳坊。」的枚举段是 1.0，抓不到。
# [EN] Clause ratio threshold for "one event per sentence". Measured: across 60 human
# [EN] paragraphs the minimum is 0.25 / median 1.00, while real runs hit 0.06-0.17.
# [EN] 0.2 keeps a 20% margin below the human floor: catch the obvious cases only.
FLAT_CLAUSE_RATIO = 0.2


def flat_span_issues(text: str, *, thr: float = FLAT_CLAUSE_RATIO) -> list[tuple[int, int]]:
    """找"**一句一件事**"的段落：**句内几乎没有分句**（逗号比句子还少）。

    ★★★ 这是用户 2026-10-19 点名的那个毛病，也是我量错过两次的那个（读我这段历史）
    ---------------------------------------------------------------------------
    用户原话：「下面这样的小短句子特别多 **每一句都恨不得交代一个事情**
    而没有像正常小说一样 用长一些的句子慢慢描写」。

    **第一次量错**：判"整段有没有 ≥25 字的句子"（`list_like_spans` 的太平那一路）。
      真人 18 章该指标 **中位 3 / 最大 9**、真跑 v21 是 **0** ⇒ 真人比真跑还"平"，
      这个口径**根本分不开**，拿它改稿只会打健康段落（实测 2→3→6 越改越差）。
    **第二次量错**：以为"太碎不是病"，干脆不修了（R49 的第一版结论）。
      可 v23 那段读起来明明白白是病。
    **真正的区分点**：不是"句子多长"，是"**句子有没有分句**"。
      真人的段落再碎也有逗号：
        「三年前二月，宣阳坊。三年前七月，亲仁坊。」—— 7 句 7 个逗号（1.0）
        「上头原本写着什么，他不知道。」—— 一句里两截
      真跑那种病段落是**光秃秃的主谓宾**：
        「岛村倚着窗框。驹子坐在火钵旁。炭火映着她半边脸颊。」—— 17 句 1 个逗号（0.06）

    量过的分布（真人 60 段 vs 真跑）：
      真人：最小 **0.25** / 5% 分位 0.67 / 中位 1.00
      真跑：v23 **0.06、0.1** / v22 0.17 / v19 0.23 / v20 全部 ≥0.25
    ⇒ 阈值 0.2。台词不计（台词短是自然的），只在 ≥`RUN_MIN` 句的段落上判。
    [EN] The real signal is not sentence length but **absence of internal clauses**:
    [EN] human paragraphs stay at >=0.25 commas per sentence even when they are choppy;
    [EN] the broken ones run at 0.06. Threshold 0.2, dialogue excluded.
    """
    out: list[tuple[int, int]] = []
    pos = 0
    for para in (text or '').split('\n'):
        start, pos = pos, pos + len(para) + 1
        p = para.strip()
        if not p or p.startswith(('#', '>')):
            continue
        sents = [x for x in _sentences(p) if x[2] >= 2]
        if len(sents) < RUN_MIN:
            continue
        if sum(x[2] for x in sents) < SPAN_MIN_CHARS:
            continue
        bare = _bare_with_ends(p)
        commas = bare.count('，') + bare.count('、')
        if commas / len(sents) < thr:
            out.append((start, start + len(para)))
    return out


def list_like_spans(text: str) -> list[tuple[int, int]]:
    """找出**该重写的段落**。两种病，本质是同一种：**句子长度没有起伏**。

    ① **太碎**：整段一句都没铺开（全是"主语 + 动作 + 结果"的报告句）。
    ② **太长**：段里有**超长句**（一个句号 >= `SENTENCE_MAX` 汉字，逗号长龙）。

    ★★★ 为什么两种都判（2026-10-19，同一天两次真跑各撞一头）
    ------------------------------------------------------
    第一版只判 ①：判的是"连着三句短句"，结果**用户点名的那一段一条都抓不到**
    （`他伸手，指尖碰了碰她耳后的皮肤，凉的。` 这句 16 个字，不算短）。
    改成"整段没有一句铺开"后抓到了，第一次真跑也治好了 ——
    可模型当场荡到另一头：整段写成一条逗号长龙（句长中位 12 → 31 字、最长 69 字），
    而 ① 一条都不报（"有长句"看着像"铺开了"）。
    ⇒ 碎和长是同一种病的两头，必须**成对判**。

    判法（每条都实测调过）：
      · 台词不计入（台词短是自然的）；两句的段落不判（正常的短促节奏）；
      · 段内汉字总数 < `SPAN_MIN_CHARS` 不判（"某地。某楼。某人的房间在二楼。"是有意的开场）。
    """
    out: list[tuple[int, int]] = []
    pos = 0
    for para in (text or '').split('\n'):
        start, pos = pos, pos + len(para) + 1
        p = para.strip()
        if not p or p.startswith(('#', '>')):
            continue
        sents = [x for x in _sentences(p) if x[2] >= 2]
        if len(sents) < RUN_MIN:
            continue
        # ⚠ 太短的段落不判：「某地。某旅馆。某人的房间在二楼。」
        #   是有意的短促开场（地点三连），不是分镜表 —— 实测误伤过。
        if sum(x[2] for x in sents) < SPAN_MIN_CHARS:
            continue
        too_flat = not any(x[2] >= LONG_MIN for x in sents)      # ① 一句都没铺开
        # ② **长句成灾**：段内长句过半（真人整体只有 14.8%），或者冒出一个超长句。
        #   ⚠ 只判"有超长句"不够 —— 第二次真跑里 6 段只有 1 段撞到 45 字，
        #     另外 5 段全是清一色 25–44 字的中等长句，读起来一样是憋气。
        # [EN] ② Long sentences dominate: over half of the paragraph's sentences are long
        # [EN] (human samples run at 14.8% overall), or one exceeds `SENTENCE_MAX`.
        _long = sum(1 for x in sents if x[2] >= LONG_MIN)
        too_long = (_long * 2 > len(sents)) or any(x[2] >= SENTENCE_MAX for x in sents)
        if too_flat or too_long:
            out.append((start, start + len(para)))
    return out


def long_sentence_ratio(text: str) -> float:
    """长句（>= LONG_MIN 汉字）占比，0–1。**台词不计入**（台词短是自然的）。"""
    sents = _sentences(text or '')
    if not sents:
        return 0.0
    return sum(1 for x in sents if x[2] >= LONG_MIN) / len(sents)


def describe(text: str) -> dict:
    """给日志/探针用的一份摘要。"""
    sents = _sentences(text or '')
    spans = list_like_spans(text)
    return {
        '叙述句数': len(sents),
        '长句占比': round(long_sentence_ratio(text), 3),
        '清单段': len(spans),
        '句长中位': (sorted(x[2] for x in sents)[len(sents) // 2] if sents else 0),
    }


# ═══════════════════════════════════════════════════════════════════
# 反思通道（Reflexion）：把"上一轮为什么被退回"带进这一次的提示词
# ═══════════════════════════════════════════════════════════════════
#: ★★★ Reflexion 范式的核心：**学习发生在文本里，不在权重里**。
#:   被验收层拒掉的那次尝试不是白费 —— 它的"具体差异"（哪一类、几处、哪一句）
#:   写成教训，进下一次的上下文。旧实现把它整份丢掉，于是每一轮都在从零瞎试
#:   （实测平铺段 2→3→6 就是这个形态）。
#:
#: ⚠ 用 `ContextVar` 不用模块级字符串：导出关口逐天串行没问题，但推演侧是
#:   `asyncio.gather` 并发的 —— 模块级变量会让两个人物的改写互相拿到对方的教训。
#: ⚠ **默认空串**，`apply_hint` 原样返回提示词 ⇒ 没反思时与旧版**逐字一致**。
#:   这是"改了但零回归"的保证（判据 Z1 钉着它）。
_HINT_CTX = __import__('contextvars').ContextVar('prose_reflect_hint', default='')

_HINT_HEAD = '\n\n【上一轮被退回的教训 —— 这一轮必须避开】\n'


def set_reflect_hint(text: str):
    """设置本次改写的反思提示。返回 token，用完请 `reset_reflect_hint(token)`。"""
    return _HINT_CTX.set(str(text or '').strip())


def reset_reflect_hint(token) -> None:
    try:
        _HINT_CTX.reset(token)
    except (ValueError, RuntimeError):
        _HINT_CTX.set('')


def reflect_hint() -> str:
    return _HINT_CTX.get()


def apply_hint(prompt: str) -> str:
    """把当前反思拼到提示词末尾。**空提示词一律原样返回**（零回归）。"""
    hint = _HINT_CTX.get()
    if not hint:
        return prompt
    return str(prompt) + _HINT_HEAD + hint


def rewrite_prompt(span_text: str, *, too_long: bool = False) -> str:
    """把一段"没有节奏"的文字交给模型重写时说的话。

    ★ 两个方向都要能说（2026-10-19，同一天两次真跑各撞一头）：
      · 太碎 → **并句**（一条一件事 ⇒ 一句里套着写）；
      · 太长 → **拆句**（逗号长龙 ⇒ 一个句号不超过四十字）。
    两个方向**改的都是写法**，事实一个字不动（与原整理要求同口径）。

    ⚠ 为什么要传方向而不是笼统说"改得像小说"：模型对"并句"的响应极强
      （实测把它从碎句推到 31 字中位），对"长短适中"几乎无响应 ——
      必须明确告诉它**这一次往哪边调**。
    [EN] Both directions must be expressible: too choppy -> merge; too long -> split. Both change
    [EN] **wording only**, never facts. ⚠ Pass the direction rather than a vague "make it read like
    [EN] a novel": the model responds strongly to "merge" and hardly at all to "moderate length".
    """
    if too_long:
        task = (
            '下面这一段**憋气**：一个句号里塞了太多东西（逗号串成一长串），读起来喘不上来。\n'
            '请**重写这一段**，要求：\n'
            '1. **事实一个字都不许改**：谁做了什么、说了什么、先后顺序，全部照旧；\n'
            '2. **一个句号里的字不超过四十个** —— 超过就断开，该断的地方断；\n'
            '3. 拆完之后**别只剩短句**：留一句长的（二十五个字上下）撑住，'
               '其余短的跟上；\n'
            '4. ⚠ **长句最多一句** —— 长句过半读起来一样憋气，别把病从"太长"改成"太碎"；\n'
            '5. 台词照原样保留，加引号。\n'
        )
    else:
        task = (
            '下面这一段被写成了**清单**：连着好几个短句，每句只交代一件事，读起来像分镜表。\n'
            '请**重写这一段**，要求：\n'
            '1. **事实一个字都不许改**：谁做了什么、说了什么、先后顺序、发生没发生，全部照旧；\n'
            '2. 把相邻的几件事**并进一个句子**：动作 + 手上的触感 + 对方的反应 + 周围的声音，\n'
            '   用逗号串起来，一个句号收；\n'
            '3. ⚠ **但一个句号里的字不超过四十个** —— 并句不等于写长句；\n'
            '4. ⚠ **长句只留一句**（二十五个字上下那一种），其余的都短 —— '
               '**长句过半读起来就憋气了**，别把病从"太碎"改成"太长"；\n'
            '5. 台词照原样保留（台词可以短，那不是问题），**加引号**；\n'
            '   台词之间如果接不上，用一句动作或环境垫在中间把时间接过去；\n'
            '6. 不许增加原文没有的事，也不许删掉原有的事。\n'
        )
    return (
        task
        + '7. 只输出重写后的这一段正文，不要标题、不要解释。\n\n'
        + '── 原文 ──\n'
        + f'{span_text}'
    )


# ══════════════════════════════════════════════════════════════
#  时序锚（2026-10-19 第六轮，用户贴的分析第一条）
# [EN] Time anchors (round six; the user's own analysis puts this first)
# ══════════════════════════════════════════════════════════════
#: **一次性**短语 —— 抵达 / 初见这件事，一整章只能说一次。
#: 用户原话：「岛村两次说"终于到了，先休息一下吧"」。
#: ⚠ 这些词判的是**语义标签**，不是字面：模型会换说法重复同一件事
#:   （"终于到了" / "总算到了" / "可算到家了"），所以按词表判而**不**按句子相似度。
# [EN] **One-shot** phrases -- arriving / meeting for the first time happens once per chapter.
# [EN] The user's words: "Island Village says 'finally arrived, rest a bit' twice". ⚠ This judges a
# [EN] **semantic tag**, not literal text: the model rewords the same beat, so judge by a word list
# [EN] rather than sentence similarity.
ONE_SHOT = (
    '终于到了', '总算到了', '可算到了', '可算到家', '一路辛苦', '一路奔波',
    '刚到', '初到', '头一回见', '初次见面', '第一次见',
)

#: **时段转折**词 —— 一章里同一转折出现太多次，就是时间被乱放。
#: 用户原话：「"夜深了"作为时间推进的自然节点，而不是反复强调」。
#: ⚠ 上限给 2（允许"入夜"和"夜深"各一次这类自然推进），不是 1。
# [EN] **Time-of-day turn** words -- too many occurrences means time is being scattered. The user:
# [EN] "'it is late' should be a natural node of time advancing, not repeated emphasis." Cap is 2.
PERIOD_TURN = {
    '夜深了': 2, '夜深': 2, '入夜': 2, '天亮了': 1, '天色暗下来': 1,
    '日头偏西': 1, '更鼓': 3, '天色发白': 1,
}


def quotable_examples(src: str) -> list[str]:
    """从**提示词**里挑出"可以直接当台词照抄"的例子。

    ★★★ 为什么要查这个（2026-10-19，R23）
    ------------------------------------
    实测两次，正反例都被抄：
      · 正面例子 `"你这个人哪。"` —— 真跑里用了 **8 次**；
      · 反面例子 `"你觉得我是个什么样的人？"` —— 模型**照抄进了正文**。
    ⇒ **举例子只许给形态和占位，不许给句子。** 带逗号或以句号收尾的一句话，
      对模型来说就是"可以拿来用的素材"，不管你在它前面写 ❌ 还是 ✅。

    ★★★ 口径为什么收得这么窄（试过两版更宽的，都误伤）
    ------------------------------------------------
    第一版判"含逗号或句末标点的引号内容"，结果把**叙述示例**全抓了：
      `擦得慢，像在磨什么`、`配角盘腿坐西条案，拨两下算盘…画圈`
    —— 那些是教"怎么写看得见的样子"，**删了模型就不会写**。
    第二版加"含人称代词"，又把 `像在磨什么`（含"什么"）抓了进来。

    **"动作示例"和"台词示例"形状完全一样**（都是句子），靠形状分不开。
    唯一稳定可分的是**开头**：张嘴说话的人，开头不是第二人称就是呼语；
    叙述句开头是动作、环境或第三人称。
    ⇒ 只抓"**以「你 / 您 / 先生 / 小姐 / 太太…」开头**的整句"。
    ⚠ 已知会漏：以"我"开头的台词（`我没听清`）、以说话人名字开头的台词。
      这两类形状上与叙述重叠，**只能靠人读**。**这条判据不假装完备。**
    [EN] Pick out prompt examples a model can lift **verbatim as dialogue**. Measured twice: a
    [EN] positive example was reused 8 times, and a negative example was copied into the prose.
    [EN] The scope is deliberately narrow: two wider versions flagged **narration** examples
    [EN] (`擦得慢，像在磨什么`) which are exactly what teaches the model to write visible action, so
    [EN] deleting them would make things worse. Action and dialogue examples have **identical
    [EN] shape**; only the opening separates them -- a speaking mouth starts with the second person
    [EN] or a term of address, narration starts with an action, the setting, or a third person.
    [EN] Known misses: dialogue starting with "I" or with the speaker's name. Those cannot be told
    [EN] apart by shape and still need a human read. **This criterion does not claim completeness.**
    """
    #: 台词的开头：第二人称与呼语。叙述句几乎不会这样开头。
    # [EN] How dialogue opens: second person and terms of address. Narration almost never does.
    lead = ('你', '您', '先生', '小姐', '太太', '奶奶', '老爷', '夫人',
            '老师', '大夫', '掌柜', '娘', '爹')
    out: list[str] = []
    # ⚠ 用自己的正则：模块级的 `_QUOTED` 允许跨行（`*`），一段文字里的**多个成对引号**
    #   会被它从一个引号吞到隔了好几句的那个引号，抓出一大段根本不是引文的内容。
    # [EN] A private regex: the module-level `_QUOTED` allows newlines, so several paired quotes in
    # [EN] one paragraph get swallowed into one span that is not a quotation at all.
    pat = re.compile(r'[“"「『]([^”"」』\n]{2,40})[”"」』]')
    for m in pat.finditer(str(src or '')):
        t = m.group(1).strip()
        if zh_len(t) < 4 or zh_len(t) > 30:
            continue
        if '…' in t or '...' in t:
            continue                      # 省略号就是"这里随便写"的占位
        if any(ch in t for ch in '〔〕·_'):
            continue                      # 机器标记与字段名，不是话
        if not t.startswith(lead):
            continue                      # 不是张嘴说话的开头 ⇒ 当作叙述示例，放过
        if ('，' in t or ',' in t) or t[-1:] in '。！？!?':
            out.append(t)
    return out


def time_anchor_issues(text: str) -> list[dict]:
    """这一章里**时间锚用坏了**的地方。返回 `[{kind, what, times, cap}]`，空列表 = 没问题。

    ★★★ 为什么这个检测器单独存在（2026-10-19 第六轮）
    ------------------------------------------------
    用户贴的分析第一条：「时序与因果关系的混乱（最严重的问题）」
    ——「岛村两次说"终于到了，先休息一下吧"」「"夜深了"反复强调」。

    代码层的根因是**材料里没有时间**（`_day_lines` 把幕的 `time_label` 丢了，
    已在那边修）。但只修材料还不够：材料给了时间，模型仍然会写下"终于到了"
    两次 —— 因为那句话读起来太好用。所以要配一个**可数的检查**。

    判两件事：
      ① **一次性短语**重复（`ONE_SHOT`）：超过 1 次就是"人到过了两回"；
      ② **时段转折**超配额（`PERIOD_TURN`）：同一个转折反复出现，时间轴就糊了。
    ⚠ 台词不计入（`_strip_quotes`）：人物嘴上说"夜深了"是台词，不是叙述的时间标记。
      —— 这一条很重要：不分台词会把"角色在复述时间"误判成"叙述乱了"。
    [EN] Where the time anchors are misused in this chapter. Empty list = fine. Why this detector
    [EN] exists: the user's first complaint is scrambled chronology. The code root cause is that the
    [EN] material had no time (fixed in `_day_lines`), but material alone is not enough -- the model
    [EN] still writes "finally arrived" twice because it reads well. It judges ① one-shot phrases
    [EN] repeated and ② period-turn words over quota. ⚠ Dialogue is excluded: a character saying
    [EN] "it is late" is dialogue, not a narration time marker -- without that split, a character
    [EN] restating the time reads as scrambled narration.
    """
    # ★★★ **两类词的台词口径不同**（这是本轮唯一一处要想清楚的地方）：
    #   · `ONE_SHOT`（终于到了 / 刚到）**台词也要算** —— 它不是"说话方式"，
    #     而是**事件本身**。人只到一次；他说两遍"终于到了"，读者就知道这里出错了
    #     （用户原文点名的正是台词里的那句）。
    #   · `PERIOD_TURN`（夜深了 / 更鼓）**只算叙述** —— 人物嘴上说"夜深了"是台词，
    #     是角色在说话，不是作者在盖章。算进去会把正常对白判成"叙述乱了"。
    # [EN] ★★★ **The two word classes treat dialogue differently**: `ONE_SHOT` includes dialogue
    # [EN] because it is not a manner of speech but **the event itself** (a person arrives once; the
    # [EN] user's own example is a line of dialogue). `PERIOD_TURN` counts narration only -- a
    # [EN] character saying "it is late" is dialogue, not the author stamping the time.
    full = str(text or '')
    bare = _strip_quotes(full)
    out: list[dict] = []
    for w in ONE_SHOT:
        n = full.count(w)
        if n >= 2:
            out.append({'kind': 'once', 'what': w, 'times': n, 'cap': 1})
    # ⚠ 「夜深了」和「夜深」是**同一个转折**，短的被长的包含时只报长的
    #   （第一版两个都报，日志里读起来像"犯了两个错"）。与 `_repeat_phrase_line`
    #   的短语去重同一条规矩。
    # [EN] 「夜深了」and「夜深」are the **same turn**; when a shorter one is contained in a longer
    # [EN] one, report only the longer (the first version reported both, reading like two faults).
    for w in sorted(PERIOD_TURN, key=len, reverse=True):
        cap = PERIOD_TURN[w]
        n = bare.count(w)
        if n <= cap:
            continue
        if any(w in b['what'] for b in out if b['kind'] == 'turn'):
            continue
        out.append({'kind': 'turn', 'what': w, 'times': n, 'cap': cap})
    return out


#: **钟点当句首**的样子（"二十三点三十五分，叶子折回"）—— 读起来像值班记录。
#: 只认"数字钟点 + 逗号"这一种形态：写成"更鼓敲过三下"这种**藏在事里**的算好的。
# [EN] A clock time at the head of a sentence ("23:35, Yoko returns") -- reads like a log.
# [EN] Only this shape is flagged; "the drum struck three times" (time hidden inside an event) is fine.
_CLOCK_HEAD = re.compile(
    r'(?:[零一二三四五六七八九十]{1,4}点[零一二三四五六七八九十]{1,3}分?'
    r'|\d{1,2}[:：]\d{2})\s*[，,、]')


def clock_stamps(text: str) -> int:
    """正文里"钟点当句首"的处数。"""
    return len(_CLOCK_HEAD.findall(text or ''))


def time_note(text: str) -> str:
    """把 `time_anchor_issues` 压成一句给日志/提示词用的话。没问题返回空串。"""
    bad = time_anchor_issues(text)
    # ⚠ 先算钟点，再判空 —— 第一版把 `if not bad: return ''` 写在前面，
    #   于是"只有钟点太多、没有别的毛病"的那一篇**永远报不出来**
    #   （而那正是第六轮真跑的实际形态：唯一的问题就是钟点当句首）。
    # [EN] Compute the clock count **before** the empty check: the first version returned early,
    # [EN] so a draft whose only fault was too many clock heads never reported it (and that was
    # [EN] exactly the shape of the round-six run).
    _ck = clock_stamps(text)
    if not bad and _ck <= 2:
        return ''
    bits = []
    for b in bad:
        if b['kind'] == 'once':
            bits.append(f'「{b["what"]}」说了 {b["times"]} 次（这种事一辈子一次）')
        else:
            bits.append(f'「{b["what"]}」{b["times"]} 次（上限 {b["cap"]}）')
    if _ck > 2:
        bits.append(f'钟点当句首 {_ck} 处（上限 2，多了像日志）')
    return '；'.join(bits)


def normalize_quotes(text: str) -> str:
    """**引号混用**时统一成中文引号 —— 纯代码，零调用。单一样式一个字符不动。

    ★★★ 这条判据我写错过一次，值得记下来
    -------------------------------------
    初版看到 `snow_v24` 整篇 24 个英文 `"`、0 个中文引号，就判它"硬伤"，
    无条件把 `"` 全换成 `“”`。
    **量了真人才发现**：`samples/zh` 那 18 章**全部用 ASCII `"`，中文引号 0 个**
    —— 那是正常写法，不是病。而 `_QUOTED` 两种都认，所有下游检测照常工作。
    ⇒ 真正的病是**同一篇里混着用**（`snow_v23`：16 个 `"` + 10 个 `“”`）。
      单一 ASCII（真人同款）/ 单一中文 都不该动 —— **少改一处就少一处风险**。
    [EN] The first version rewrote every ASCII quote, judging "ASCII = defect". Measuring
    [EN] the human samples showed they use ASCII quotes exclusively (zero Chinese ones),
    [EN] so a single style is fine and must be left alone. Only **mixing** both in one
    [EN] piece is a defect (`snow_v23`: 16 ASCII + 10 Chinese).

    ⚠ **只处理一行内成对的情况**（引号数是偶数）。奇数个说明台词跨了行，
      猜左右会猜错，**原样不动**（宁可留一处英文引号，不许把台词配对搞反）。
    ⚠ 幂等：跑两遍结果一样。
    """
    raw = str(text or '')
    if '"' not in raw or '“' not in raw:
        # 单一 ASCII（真人同款）或单一中文 ⇒ 不混用，一个字符都不动
        return raw

    def _fix_line(line: str) -> str:
        n = line.count('"')
        if n < 2 or n % 2:
            return line
        out: list[str] = []
        open_next = True
        for ch in line:
            if ch == '"':
                out.append('“' if open_next else '”')
                open_next = not open_next
            else:
                out.append(ch)
        return ''.join(out)

    return '\n'.join(_fix_line(ln) for ln in raw.split('\n'))


def normalize_quotes_count(text: str) -> int:
    """这一篇里**还能改**的英文引号有多少个（判据与日志用）。"""
    raw = str(text or '')
    if '"' not in raw:
        return 0
    return sum(1 for ln in raw.split('\n')
               if ln.count('"') >= 2 and ln.count('"') % 2 == 0)


def split_long_sentences(text: str, *, hard_max: int = 26,
                         min_part: int = 10, names: tuple[str, ...] = ()) -> str:
    """把**逗号长龙**切开 —— 但**每段要留一句长的撑节奏**。

    ★★★ 为什么这条必须是硬闸，不能只靠提示词（2026-10-19 第六轮）
    ------------------------------------------------------------
    实测同一组提示词连跑四次，长句占比：**21% → 60% → 47% → 85.7%**（真人 14.8%）。
    提示词里"一个句号不超过四十个字""长句掺着用"每一条都写着，而产出**一次比一次长**
    —— "prompt 里写了 ≠ 生效"的又一个现场。

    ★★★ 关键发现：**"全切到 24 字"是错的**（第七轮实测）
    ----------------------------------------------------
    第一版对所有超长句一律切。扫参数的结果是"两头同时恶化"：

    | hard_max | 句长中位 | 长句% | 平铺段 |
    |---|---|---|---|
    | （原文） | 31 | 57.9 | 0 |
    | 32 | 21 | 43.5 | 1 |
    | 24 | 17 | 31.0 | **4** |

    长句是压下去了，**平铺段从 0 涨到 4** —— 而那正是第四轮花大力气治的病。
    原因很简单：`list_like_spans` 判的是"整段一句都没铺开"，切得越碎越像它。
    ⇒ 两个判据在**互相打架**，机器不能只朝一个方向使力。

    所以现在改成**按段配平**，不是按句切：
      · 每段**先留一句最长的**不动（它是这一段的骨架，也是"不是清单"的凭据）；
      · 其余超长句切到 `hard_max`；
      · 切完若这一段仍被判成平铺段，**这一段整体退回原文**（逐段退，不是整篇退）。
    这样长句占比**停在 30% 左右而不再往下**，平铺段回到 0 ——
    这是"两头都不越界"的位置，不是一个更小的数字。
    ⚠ 真人是 14.8%，但那个数是**整本书**的数；按段配平后单日 30% 属于同一量级，
      再往下压只会换来碎片。**不要为了追一个百分比把节奏切没。**

    切点怎么选（三条，都是被碎片逼出来的）：
      ① **离中点最近**的逗号（偏好"的/了/着"之后的）；
      ② ⚠ **引导语不切**：切点后面若是 `弯身放下：“…”` 这种"动作+冒号"，
         切了会得到"弯身放下："单独成句 —— 那是连动结构，不是句子；
      ③ ⚠ **人物名前面优先**：切在"……回来，叶子端着……"比切在"……回来，弯身……"好。
      · 每段两半都必须 >= `min_part` 字，否则不切；
      · **台词（引号里）不动**；**只动标点，一个字不删不改**。
    [EN] Cut comma dragons, but **keep one long sentence per paragraph to carry the rhythm**.
    [EN] Cutting every long sentence to 24 chars was measured to trade 26 points of long sentences
    [EN] for **4 new flat paragraphs** -- the very disease round four fixed. So: keep the longest
    [EN] sentence in each paragraph intact, cut the rest, and restore a paragraph wholesale if it
    [EN] still reads flat. Long-sentence share stops around 30% **by design**, and that is the
    [EN] point where neither end of the swing is crossed -- not a smaller number.
    """
    if not text:
        return text
    src = str(text)
    spans: list[tuple[int, int, str]] = []

    def _mask(m: re.MATCH) -> str:
        spans.append((m.start(), m.end(), m.group(0)))
        return '\u3000' * len(m.group(0))

    masked = _QUOTED.sub(_mask, src)

    _BAD_HEAD = ('弯身', '伸手', '抬脚', '回头', '低头', '抬头', '转身', '起身',
                 '站起', '坐下', '放下', '拿起', '点头', '摇头', '侧过', '偏头',
                 '回身', '俯身', '直起', '垂下', '抬眼', '合上', '推开', '拉拢')
    _SUBJ = ('他', '她', '它', '两人', '众人', '自己', '那个人') + tuple(names or ())

    def _leadin(tail: str) -> bool:
        m = re.match(r'^([^，。！？]{0,12}?)：', tail)
        return bool(m)

    def _cut_one(one: str) -> str:
        """把单个句子切到 <= hard_max（尽量只留一句长的在外面调用）。"""
        for _ in range(10):
            if zh_len(one) <= hard_max:
                break
            cuts = [i for i, ch in enumerate(one[:-1]) if ch in '，,、']
            if not cuts:
                break
            mid = len(one) / 2
            usable = []
            for i in cuts:
                tail = one[i + 1:]
                if zh_len(one[:i]) < min_part or zh_len(tail) < min_part:
                    continue
                if _leadin(tail):
                    continue
                if tail.lstrip('\u3000 ').startswith(_BAD_HEAD):
                    continue
                usable.append(i)
            if not usable:
                break
            _subj = [i for i in usable
                     if one[i + 1:].lstrip('\u3000 ').startswith(_SUBJ)]
            _pref = [i for i in (_subj or usable)
                     if i > 0 and one[i - 1] in '的了着过']
            cand = _pref or _subj or usable
            cut = min(cand, key=lambda i: abs(i - mid))
            one = one[:cut] + '。' + one[cut + 1:]
        return one

    out: list[str] = []
    for para in masked.split('\n'):
        if not para.strip():
            out.append(para)
            continue
        sents = list(_SENT.finditer(para))
        if not sents:
            out.append(para)
            continue
        # ★★★ **先判这一段是不是"长句成灾"**，不是就整段不动（2026-10-19 第七轮）
        #   否则"有长有短"的好段落也会被切 —— 切完变全短句 ⇒ 被平铺判据接住 ⇒
        #   白花一次重写调用（判据 H4「好文字不动」抓到的就是这一条）。
        #   门禁与 `list_like_spans` 的 ② 同口径：**长句过半**，或者有一句真的超长。
        # [EN] ★★★ **First ask whether this paragraph is long-heavy at all**; if not, leave it
        # [EN] alone. Otherwise "long-and-short" paragraphs get chopped too, become all-short, and
        # [EN] burn a rewrite (criterion H4, "good text is not touched", caught exactly this).
        _lens = [zh_len(m.group(0)) for m in sents]
        _nlong = sum(1 for n in _lens if n >= LONG_MIN)
        # ★★★ **"该不该切"按主语切换次数判，不按长度判**（2026-10-19 第七轮定案）
        # ------------------------------------------------------------------
        # 拿两段等长的真句子对比，长度完全分不开它们：
        #
        #   ✅ 好文字（43 字，**主语只有 2 个**）：
        #      `他伸手过去，指尖碰到的那片皮肤是凉的，她没动，屋里静得能听见灯芯炸响…`
        #      —— 一条连续的动作链，长是对了。
        #   ❌ 长龙（40 字，**主语换了 3 次**）：
        #      `驹子拨了拨火箸，火苗跳一下，廊板响，叶子端着壶回来，弯身放下，她退去…`
        #      —— 驹子→火苗→廊板→叶子→她，一句话里换了四件事。
        #
        # ⇒ 用户说的"一句恨不得交代好几件事"，**可数形状就是"主语换了几次"**。
        #   所以门禁是：**不同主语 >= 3** 或 **有真超长句（>=45）** 或 **段内多句且长句过半**。
        #   这样"一句长长的描写"不会被切，"一句串了四件事"才会被切。
        # [EN] ★★★ **Judge "should this be cut" by subject switches, not by length.** Two real
        # [EN] sentences of the same length cannot be told apart by length: a 43-char span with
        # [EN] **2 subjects** is one continuous action chain (long is correct); a 40-char span with
        # [EN] **3 subjects** (Jouji -> flame -> floorboard -> Yoko -> she) packs four things into
        # [EN] one sentence. The user's "one sentence wants to say several things" has a countable
        # [EN] shape: **how many times the subject changes**. So the gate is: >= 3 distinct
        # [EN] subjects, or a truly overlong sentence (>=45), or long-heavy within a 3+ sentence
        # [EN] paragraph.
        _nsubj = sum(1 for w in _SUBJ if w in para)
        _heavy = (_nsubj >= 3
                  or any(n >= SENTENCE_MAX for n in _lens)
                  or (len(_lens) >= RUN_MIN and _nlong * 2 > len(_lens)))
        if not _heavy:
            out.append(para)
            continue
        # ★ 找出这一段**最长的那一句**，它不动（骨架）
        if max(_lens) <= hard_max:
            out.append(para)                     # 整段都不超，不用动
            continue
        # ⚠ **段内少于 3 句时不要"留骨架"**（第七轮实测）：那一段本身就只有一句
        #   40 字的逗号长龙，"留最长那句"等于**一句都不切** ⇒ 整篇长句占比纹丝不动
        #   （第一版就是这么写的，扫参数时四个门槛给出同一个 57.9%）。
        #   少于 3 句时没有"节奏"可言，全切。
        # [EN] ⚠ Do **not** "keep the skeleton" when a paragraph has fewer than 3 sentences:
        # [EN] the paragraph is then a single 40-character comma dragon, and keeping the longest
        # [EN] sentence means keeping **all of it**, so the share never moves (the first version did
        # [EN] exactly this -- four thresholds all returned 57.9%). With fewer than 3 sentences
        # [EN] there is no rhythm to protect; cut them all.
        _keep = _lens.index(max(_lens)) if len(sents) >= 3 else -1
        buf = ''
        for k, m in enumerate(sents):
            one = m.group(0)
            buf += one if k == _keep else _cut_one(one)
        out.append(buf)
    res = '\n'.join(out)
    for a, b, frag in reversed(spans):
        if a <= len(res):
            res = res[:a] + frag + res[b:]

    # ★★★ **这里不做"切碎了就回滚"**（2026-10-19 第七轮，两次实测推翻）
    # ------------------------------------------------------------------
    # 试过两版回滚，都掉进同一个死循环：
    #   ① 用 `list_like_spans` 整体判 ⇒ 它同时判"太碎"和"太长"，
    #      切完**仍然长句过半**的段被判中 → 回滚 → 一个字都没切（66 字长句切完还是 66）；
    #   ② 只判"太碎"（`_flat`）⇒ **一段只有一句长句时，切开必然是"全短句"**，
    #      而那正好等于平铺段 → 回滚 → 又没切。
    #
    # 根因不是回滚写错了，是**职责没分开**：一个 66 字的逗号长龙，
    # 靠"切"永远修不好 —— 要么还长，要么切碎。这种段落只能**重写**（要模型铺开）。
    # ⇒ 现在的分工是干净的：
    #     · 本函数**只治"太长"**，切完不管碎不碎；
    #     · `list_like_spans` + 重写**只治"太碎"**；
    #     · `Novelist._fix_flat_paragraphs` 把**切句排在检测之前** ——
    #       切完产生的平铺段，正好被重写那一步接住，铺成有长有短。
    # [EN] ★★★ **No "roll back if it got choppy" here.** Two versions of that rule deadlocked the
    # [EN] same way: (a) judging with `list_like_spans` also judges "too long", so a paragraph still
    # [EN] long-heavy after cutting was rolled back (a 66-char sentence stayed 66); (b) judging only
    # [EN] "choppy" fails because **a one-sentence paragraph turns into all-short sentences when
    # [EN] cut**, which *is* a flat paragraph => rolled back again.
    # [EN] The root cause is not the rollback logic, it is mixed responsibilities: a 66-char comma
    # [EN] dragon cannot be fixed by cutting -- it is either still long or chopped. It needs a
    # [EN] **rewrite**. So: this function **only cures "too long"**; `list_like_spans` + rewrite
    # [EN] **only cures "too choppy"**; and `_fix_flat_paragraphs` now **splits before detecting**,
    # [EN] so the flat paragraphs the split creates get rewritten into long-and-short.
    return res


# ══════════════════════════════════════════════════════════════
#  「反应标签」配额（2026-10-19 第十一轮，用户报的第二条）
# [EN] Reaction-tag quota (round eleven; the user's second complaint)
# ══════════════════════════════════════════════════════════════
#: 一个人**没接住话**时的那套现成写法。第一次是惊艳，第三次开始是疲劳。
#: 用户原话：「这个手法第一次用是惊艳，第二次用是强化，第三次开始是重复，
#: 第四次之后就变成了读者的疲劳。岛村成了一个'复读机'式的角色，失去了鲜活感。」
#:
#: ⚠ 这是**叙述层**的复读，与 `agent/core._repeat_phrase_line`（台词层的口癖）
#:   是两回事：那个管"这个人说话老是用同一个开头"，这个管"作家老用同一个手法
#:   描写他反应慢"。两条都要有，否则修了台词层，作家照样把人写成复读机。
# [EN] Ready-made ways of writing "he did not catch it". The user: "the first use is striking, the
# [EN] second reinforces, the third is repetition, and from the fourth it is fatigue." ⚠ This is
# [EN] **narration-level** repetition, distinct from `_repeat_phrase_line` (dialogue-level tics):
# [EN] that one guards "he always opens the same way", this one guards "the author always uses the
# [EN] same device to say he is slow". Both are needed.
REACTION_TAGS: dict[str, int] = {
    '慢一拍': 2, '慢半拍': 2, '迟了半拍': 2,
    '没听清': 2, '听不清': 2, '没听见': 2,
    '迟疑': 2, '顿了顿': 2, '怔了怔': 2, '愣了愣': 2, '顿了一下': 2,
    '半晌没': 2, '一时没': 2, '没接话': 2, '没作声': 2,
}


def reaction_tag_issues(text: str) -> list[dict]:
    """这一章里**反应标签用超了**的地方。返回 `[{what, times, cap}]`，空列表 = 没问题。

    判法：每个标签出现次数 > 它的配额（默认 2）就报一条。
    ⚠ **只数叙述**（台词里的"我没听清"是人物在说话，不是作家在用标签）。
    ⚠ 「慢一拍」与「慢半拍」是同一个手法，短的被长的包含时只报长的
      —— 与 `time_anchor_issues` 同一条去重规矩。
    [EN] Where reaction tags are used past quota. Empty list = fine. ⚠ **Narration only**: a
    [EN] character saying "I didn't catch that" is speech, not the author deploying a device.
    [EN] ⚠ 「慢一拍」and「慢半拍」are the same device; report only the longer on containment.
    """
    bare = _strip_quotes(str(text or ''))
    out: list[dict] = []
    for w in sorted(REACTION_TAGS, key=len, reverse=True):
        cap = REACTION_TAGS[w]
        n = bare.count(w)
        if n <= cap:
            continue
        if any(w in b['what'] for b in out):
            continue
        out.append({'what': w, 'times': n, 'cap': cap})
    return out


def reaction_tag_note(text: str) -> str:
    """把 `reaction_tag_issues` 压成一句话。没问题返回空串。"""
    bad = reaction_tag_issues(text)
    if not bad:
        return ''
    return '；'.join(f'「{b["what"]}」{b["times"]} 次（上限 {b["cap"]}）' for b in bad)


# ══════════════════════════════════════════════════════════════════════
#  沉默只走一条路 / 口癖 / 细节复读（2026-10-19 第十一轮，用户第 5、6 条）
# [EN] Silence that only goes one way / tics / detail repetition (round eleven)
# ══════════════════════════════════════════════════════════════════════
#: 三类重复共用一个入口 `repeat_issues(text)`，修复与判据都调它 ——
#: **同一件事只许有一处实现**。
#: [EN] All three checks share one entry point, `repeat_issues(text)`; both the repair
#: [EN] and the criteria call it -- one implementation only.

#: 短语计数的停用开头表。**只管 3 字滑窗**（碎片风险在那儿）：
#: 5 字连续重合 3 次以上几乎一定是真短语，不能因为首字是「你」就跳过 ——
#: 那正好把「你这个人哪」这种口癖漏掉（`agent/core` 第十轮实测）。
# [EN] Stop-head table for sliding windows, **3-char windows only** -- a 5-char run that
# [EN] recurs 3+ times is almost certainly a real phrase and must not be skipped for
# [EN] starting with 你 (that is exactly how 「你这个人哪」 went undetected).
_PHRASE_STOP_HEAD = set('的了着过是在和与就都也还很太更最把被将给让对向为从一这那他她我你'
                        '们个上下里外中间前后些怎样谁')

#: 细节复读的虚词整词表（"什么 / 怎么 / 这个"切出来也不是道具）
# [EN] Whole-word stop list for the detail check.
_STOP_PHRASE_WHOLE = {'什么', '怎么', '这个', '那个', '一个', '就是', '不是',
                      '还是', '已经', '现在', '时候', '他们', '我们', '自己',
                      '一下', '有些', '没有', '忽然', '接着', '然后', '这时',
                      '于是', '知道', '觉得', '声音', '轻声', '低声'}


def quoted_texts(text: str) -> list[str]:
    """正文里**每一段引语的内容**（按出现顺序）。

    ⚠ 摘引语只走 `_quoted_spans`（按出现顺序两两配对）—— 中文正文里 ASCII 的
      `"` 开闭同形，按方向配对会把「说\"她恨我\"，又笑\"算了\"」拆坏。
    [EN] The content of every quoted span, in order of appearance. Only `_quoted_spans`
    [EN] (paired in order of appearance) may be used -- ASCII quotes share one glyph for
    [EN] open and close in Chinese prose.
    """
    out: list[str] = []
    try:
        spans = _quoted_spans(str(text or ''))
    except Exception:                                         # noqa: BLE001
        return out
    for _a, _b, inner in spans:
        c = str(inner or '').strip()
        if c:
            out.append(c)
    return out


def phrase_hotspots(body: str, *, min_times: int = 3) -> list[tuple[str, int]]:
    """一段文字里**反复出现**的短语 `[(短语, 次数)]`（长的优先、被包含的不再报）。

    ★★ 口径与 `agent/core._repeat_phrase_line` **逐字一致**（第十轮修过的版）：
      · 先记**标点围住的整段**（2–8 字）—— 最短、最规整的口癖恰恰是
        2–5 字（「是啊。」「你这个人哪」），它们正是最容易被漏掉的一类；
      · 再取 5/4/3 字滑窗；**停用开头只管 3 字窗**；
      · 每段只记一次（"在几段里出现过"才是读者感受到的重复）；
      · 只留 >= `min_times` 的，按长度降序，被更长同频短语包含的不再报。
    ⚠ **两处实现**（这里与 `agent/core`）由 `verify_prose_flow` 的成对判据钉住：
      给同一份材料必须给出一致的短语表。真要合并成一处，先过那条判据。
    [EN] Phrases that recur in a piece of text. The counting rule is **identical** to
    [EN] `agent/core._repeat_phrase_line` (round ten). The two implementations are pinned
    [EN] by a paired criterion in `verify_prose_flow`.
    """
    counts: dict[str, int] = {}
    for run in re.findall(r'[\u4e00-\u9fff]+', str(body or '')):
        seen: set[str] = set()
        if 2 <= len(run) <= 8:
            seen.add(run)
        for size in (5, 4, 3):
            for i in range(len(run) - size + 1):
                w = run[i:i + size]
                if size <= 3 and w[0] in _PHRASE_STOP_HEAD:
                    continue
                seen.add(w)
        for w in seen:
            counts[w] = counts.get(w, 0) + 1
    hot = {w: n for w, n in counts.items() if n >= max(2, min_times)}
    keep: list[tuple[str, int]] = []
    for w, n in sorted(hot.items(), key=lambda kv: (-len(kv[0]), -kv[1])):
        if any(w in k and kn >= n for k, kn in keep):
            continue
        keep.append((w, n))
    return keep


# ── ① 沉默只走一条路：成套句式 ────────────────────────────────────
#: 「否定回应 + 紧跟视线落点」—— "岛村没应，看那道门缝雪光"。
#: 用户原话：「岛村沉默无层次：全段只有'不说话看雪光'和'嗯……'两种反应，
#: 建议用身体语言 / 感知细节 / 回忆联想增加层次。」
#: ★★ 可数形状**不是**"通道少"（实测按通道判会漏：岛村那天身体 / 感知 / 声音
#:   三种通道都用了），而是**这个成套句式本身被复用**。
#: 实测（三处对照，`developers/probe_silence_shape.py`）：
#:   真人 18 章：17 章 0 处、1 章 1 处，**从来没有 >=2**；
#:   真跑 55 份：50 份 0、4 份 1、1 份 2 —— 那 1 份正是 snow_v11 那个白天。
#: ⇒ 阈值取"一天 >=2 处"：真人从不越界，越界的只有这个句式的复用。
# [EN] The set piece "negated response + an immediate gaze landing". Measured: human
# [EN] chapters never reach 2 in a day; the one run that did is the very day the user
# [EN] named. So the threshold is ">= 2 per day".
SILENCE_GAZE_RE = re.compile(
    '[没不未](?:应|答|接话|搭腔|说话|作声|做声|开口|言语|回声|理会|回头|理)'
    '[，,、\\s]*(?:只|也|就|又|才)?'
    '(?:[看望向瞧瞥盯注聆听闻觉感]|目光|视线|眼神|瞄)')
SILENCE_GAZE_CAP = 1


def silence_gaze_spans(text: str) -> list[str]:
    """正文（**叙述层**）里「否定回应 + 紧跟视线落点」的成套句式。

    只数叙述：台词里的"我没听清"是人物在说话，不是作家在用装置
    （与 `reaction_tag_issues` 同一条纪律，走同一个 `_strip_quotes`）。
    [EN] Narration only -- a character *saying* "I didn't catch that" is speech, not the
    [EN] author deploying a device (same rule and same `_strip_quotes` as the tag quota).
    """
    bare = _strip_quotes(str(text or ''))
    if not bare:
        return []
    return [m.group(0) for m in SILENCE_GAZE_RE.finditer(bare)]


def silence_gaze_issues(text: str) -> list[dict]:
    """成套句式用超了的地方。返回 `[{what, times, cap}]`，空列表 = 没问题。"""
    bad = silence_gaze_spans(text)
    if len(bad) <= SILENCE_GAZE_CAP:
        return []
    return [{'what': '没接住话，紧跟一个视线落点', 'times': len(bad),
             'cap': SILENCE_GAZE_CAP}]


# ── ② 台词口癖 ──────────────────────────────────────────────────
#: 指称类短语（时间 / 数字 / 方位）**不是口癖** —— 实测真人一章里「十五年前」
#: 出现 3 次，那是在说同一件事；「你这个人哪」出现 3 次才是复读。
# [EN] Reference-type phrases are not tics: measured, 「十五年前」 three times in one
# [EN] human chapter is talking about the same thing.
_REFERENCE_MARK = ('年月日号点半时分秒时辰刻'
                   '一二三四五六七八九十百千万零两半几第每各某另')
TIC_MIN_LEN, TIC_CAP = 4, 2


def repeated_tic_issues(text: str) -> list[dict]:
    """对白里同一段 >=4 字的话，一天用了超过 `TIC_CAP` 次。**不问说话人是谁。**

    ⚠ 为什么不能按说话人判：实测从正文归属说话人完全不可靠 ——
      「你这个人哪」四次的说话人被判成「驹子转」「火钵边」「炭塌了」「又说」，
      四段口癖被劈成四个"人"，一次都报不出来。
    ⚠ 为什么口径是"整篇对白"而不是"每个人"：真人一章里同一段话被**不同人**
      说 3 次以上同样罕见（18 章 0 次），算成口癖不冤。
    [EN] The same stretch of dialogue used more than `TIC_CAP` times a day, **without
    [EN] asking who spoke** (attribution from prose is unreliable: measured the four
    [EN] speakers of 「你这个人哪」 as 驹子转 / 火钵边 / 炭塌了 / 又说).
    """
    body = chr(10).join(quoted_texts(text))
    if len(body) < 20:
        return []
    out: list[dict] = []
    for w, n in phrase_hotspots(body, min_times=TIC_CAP + 1):
        if len(w) < TIC_MIN_LEN or any(c in w for c in _REFERENCE_MARK) \
                or w[-1] in '前后里':
            continue
        if any(w in x['what'] for x in out):
            continue
        out.append({'what': w, 'times': n, 'cap': TIC_CAP})
    return sorted(out, key=lambda d: -d['times'])


# ── ③ 细节复读（道具 + 状态动词）──────────────────────────────
#: 名词指代**不判**：真人的「漏刻」一章出现 4–8 次是正常的 —— 那是在说
#: 同一件事。判的是**同一个道具经历了同一个状态变化**：炭塌了、灯灭了、水凉了。
# [EN] Noun references are not judged (a human chapter says 漏刻 4-8 times); what is
# [EN] judged is the same prop undergoing the same state change.
_STATE_VERBS = ('塌灭熄凉透干皱散颤抖晃停静暗亮落沉飘断裂碎洒溅溢缩蜷软硬冷热温麻胀谢'
                '淌滴流传浮升退进合开张破裂')
_DETAIL_RE = re.compile('([\u4e00-\u9fff]{1,2})([' + _STATE_VERBS + '])')
DETAIL_CAP = 2


def detail_repeat_issues(text: str) -> list[dict]:
    """旁白里同一「道具 + 状态动词」，一天用了 >= `DETAIL_CAP + 1` 次。

    ⚠ 虚词整词与滑窗开头都在这里挡掉（"半天没塌"切出的"没塌"不算复读）。
    [EN] The same prop-state pair used >= DETAIL_CAP+1 times a day.
    """
    bare = _strip_quotes(str(text or ''))
    if not bare:
        return []
    counts: dict[tuple[str, str], int] = {}
    for seg in re.split(r'[，。！？；：、\s]+', bare):
        for m in _DETAIL_RE.finditer(seg):
            prop, verb = m.group(1), m.group(2)
            if prop in _STOP_PHRASE_WHOLE or prop[0] in _PHRASE_STOP_HEAD:
                continue
            key = (prop, verb)
            counts[key] = counts.get(key, 0) + 1
    out: list[dict] = []
    for (prop, verb), n in counts.items():
        if n > DETAIL_CAP:
            out.append({'what': f'{prop}{verb}', 'times': n, 'cap': DETAIL_CAP})
    return sorted(out, key=lambda d: -d['times'])


# ── ④ 称呼式台词（配角按模版刷存在感）─────────────────────────────
#: 每句都以「先生，」「X姐，」开头 ⇒ 那个角色不是在对话，是在**按模版刷屏**。
#: 真人 18 章（samples/zh，6 部作品 × 3 章）**一条都没有**：中位 0%、最大 0%。
#: 真跑 snow_v11 19.1% / snow_v12 30.0%（叶子九句全是「先生，…」）。
#: ⚠ 前缀必须是 {0,4} 而不是 {1,4}：真跑里那九句全都是**以称呼开头**的，
#:   要求称呼前面还有字会一条都抓不到 —— 探针第一版就栽在这里，
#:   把 voc_share 量成了 0，差点得出"配角没抢戏"的反向结论。
#: ⚠ 为什么不用"相邻台词共享二元组"判"答非所问"（同一个探针一起量过）：
#:   真人问→答的字面零承接率是 **100%**，比真跑还高 ⇒ 字面重合判不了语义
#:   是不是同一条线（R02）。拿它立判据会把真人一起判死，所以不立。
# [EN] Lines opening with a vocative. Zero occurrences in 18 human chapters.
VOCATIVE_CAP = 0.15
_VOCATIVE_RE = re.compile('^[一-龥]{0,4}(?:姐|哥|先生|小姐|姑娘|君|桑|大人)[，、：:]')


def vocative_lines(text: str) -> list[str]:
    """以「称呼 + 停顿标点」开头的台词（按出现顺序）。"""
    return [q for q in quoted_texts(str(text or '')) if _VOCATIVE_RE.match(q)]


def vocative_share_issues(text: str) -> list[dict]:
    """称呼式台词多到像模版刷屏时报警。

    ⚠ 上限按**条数**给（`int(总台词 * VOCATIVE_CAP)`），与另外三类共用
      `{what, times, cap}` 这一个形状 —— 否则占比 0.15 和条数 12 混在一个
      字段里，修复提示词会说不清"最多留几条"。
    [EN] Cap is expressed as a **count** so it shares the {what, times, cap}
    [EN] shape with the other three kinds.
    """
    qs = quoted_texts(str(text or ''))
    n = len(qs)
    if n < 8:                                # 台词太少时占比没有意义
        return []
    voc = [q for q in qs if _VOCATIVE_RE.match(q)]
    cap = int(n * VOCATIVE_CAP)
    if len(voc) <= cap:
        return []
    return [{'what': '以「称呼 + 停顿」开头的台词（像按模版刷存在感）',
             'times': len(voc), 'cap': max(cap, 1)}]


# ── ⑤ 含糊应答：「唔……这么晚了。」────────────────────────────────
#: 语气词开头、再拖一句**不相干的尾巴** —— 这是"答非所问"的主力形态，
#: 也是最难抓的一种：它看着像一句人话，其实什么都没答。
#: ⚠ 与"纯应答"的分工：「是啊」整句是应答词（那是口癖检测器的事）；
#:   这一类专门抓**带尾巴**的（「唔……路上滑吧。」），纯应答抓不到它们。
#: ⚠ 阈值来自真人 18 章的**绝对条数**：14 章是 0 条，最多的一章也才 **1 条**。
#:   真跑 snow_v13 是 5 条（34 句台词）—— 5 倍于真人最大值。
#: ⚠ **必须用绝对条数，不能用占比**：真人样本每章只有 3~44 句台词，
#:   拿占比当基线会被小样本毁掉（5 句里 1 句 = 20%，比真跑还高），
#:   探针第一版就是这么得出"含糊占比无区分度"的错误结论的。
# [EN] Absolute counts, not ratios: human chapters are short (3--44 lines), so
# [EN] ratio baselines are destroyed by small-sample variance.
HEDGE_CAP = 2
_HEDGE_HEAD = '唔嗯啊哦噢唉哎呃嗨'
_HEDGE_PUNCT = '…，。！？、；：—～·“”"\''
_HEDGE_WORD = ('是啊', '是的', '对', '好', '行', '知道', '有劳', '好吧', '行的')


def is_hedge_reply(q: str) -> bool:
    """以语气词开头、去掉语气词和尾巴后几乎没内容的台词。"""
    t = str(q or '').strip().lstrip('…—-· ')
    if not t or t[0] not in _HEDGE_HEAD:
        return False
    rest = t
    for ch in _HEDGE_PUNCT:
        rest = rest.replace(ch, '')
    for w in _HEDGE_WORD:
        rest = rest.replace(w, '')
    return len(rest.strip()) <= 8


def hedge_reply_issues(text: str) -> list[dict]:
    """含糊应答多到"整篇没人正面回答过问题"时报警。"""
    qs = quoted_texts(str(text or ''))
    if len(qs) < 8:                            # 台词太少，条数没有意义
        return []
    hedges = [q for q in qs if is_hedge_reply(q)]
    if len(hedges) <= HEDGE_CAP:
        return []
    return [{'what': '含糊应答（语气词开头、拖一句不相干的话，等于没回答）',
             'times': len(hedges), 'cap': HEDGE_CAP}]


#: ⚠ 「追问链」**试过，已删，别再捡回来**（2026-10-19 第十一轮）。
#:   想法：同一个问题被问到第 N 遍 ⇒ 中间那些问都没被接住，是"结构"，能数。
#:   实测两头都不成立：
#:     · 真跑 snow_v12 上它抓到的 5 条**全是叶子那几句「先生，…」** —— 它们
#:       只是共享了「先生」「驹子姐」这几个词，跟"追问"没关系，而叶子刷屏
#:       `vocative` 已经抓过了 ⇒ **换个角度把同一个现象又抓一遍**，零新增信息。
#:     · 真正的追问（「您就不好奇…吗？」「您还没回答我呢。」「就没一句话要问我？」）
#:       字面**一个二元组都不共享**，一条都抓不到。
#:   结论：追问是语义的，字面聚类只能捞到"共享实词的问句复读"，
#:   那已经被 `vocative` / `tic` 覆盖了。立它只会多一份重复实现。
# [EN] "Re-ask chain" was tried and removed: it only re-catches what `vocative`
# [EN] already catches, and misses genuinely re-asked questions (no literal overlap).

#: 五类重复的中文名（给人看的那一行用）
# [EN] Chinese labels for the five kinds (used in the human-readable line).
_REPEAT_KIND_CN = {'silence': '沉默只走一条路', 'tic': '台词口癖',
                   'detail': '细节复读', 'vocative': '称呼式台词刷屏',
                   'hedge': '含糊应答'}


# ══════════════════════════════════════════════════════════════
#  派活层（上游）：只派了"不做什么"的角色
# ══════════════════════════════════════════════════════════════
#: 角色的任务如果**条条都是**否定型（不 / 别 / 沉默 / 退 …），那他在场上
#: 就无事可做 —— 只能不动、不说。主角被这么派一次，整篇就少一个能共情的支点。
#: ⚠ 这是**结构性约束**，不是统计阈值：一个"只被派了不做什么"的人不可能有戏，
#:   跟"多少算多"无关，所以**不需要**真人样本定阈值（R11 管的是阈值类判据）。
#: ⚠ 根因在上游（R21 配角像 NPC 的根因在派活）：下游再怎么改也改不出主动性。
#: ⚠ 反过来也别一刀切：只要有**任何一条**肯定性动作就不算（下面 `aff` 那一半），
#:   否则会把"先忍着、末了挑明"这种好派活一起判死。
# [EN] Structural (not statistical): a role told only what NOT to do has nothing
# [EN] to play. Any single affirmative task clears it -- otherwise good dispatches
# [EN] like "hold back, then say it at the end" would be killed too.
_NEG_MARK = ('不', '别', '勿', '莫', '沉默', '忍', '掖', '藏着', '按住', '退开')
#: ⚠ **不许**放"要 / 做 / 观察"这种万能词 —— 每条任务都以"要"开头，放进去
#:   等于给所有任务发通行证，这条判据就永远绿（这是"一刀切也能绿"的反面：
#:   一条都抓不到）。只留**真的会让人开口 / 动手**的那几个。
#: ⚠ 但**位移与具体肢体动作要放进来** —— 2026-10-20 真跑实证：叶子被派
#:   「从廊道**走到**纸门外**停步**不出声惊动屋内」，她明明有事可做，
#:   却因"走 / 停"不在表里被判成"只派了不做什么"（**误报**，v13 日志里
#:   那条 WARNING 就是它）。区分标准：万能词**每条任务都有**，
#:   位移/肢体动词**只有真要动起来才有** —— 后者不会让判据失效。
# [EN] No filler verbs like "要/做" (every task starts with them => criterion dies),
# [EN] but DO include movement/body verbs: 走到/停步 is real business to play.
_AFF_VERB = ('说', '问', '给', '讨', '认', '追', '留', '送', '接', '讲', '念',
             '挑明', '开口', '劝', '拦', '抱', '拉', '写', '翻', '拿', '放',
             '应', '答', '承认', '说出',
             # 位移 / 肢体：真要动起来才写得出来（不会每条任务都有）
             '走', '停', '进', '退', '坐', '站', '端', '掀', '敲', '拨', '推',
             '挪', '靠', '跪', '蹲', '起', '转身', '递', '取', '摆', '铺')


def _has_affirmative(t: str) -> bool:
    """这条任务里有没有一个**没有被否定掉**的肯定性动词。

    ⚠ 不能只做子串匹配：实测「不说话」里就有"说"，照子串判它是**肯定**动作，
      于是"全否定"的那一条被放过去了（第一版就栽在这里，该报的没报）。
      所以要看动词**前面两个字符**里有没有否定词 —— 有，就是这个动词被否掉了。
      窗口取 2 是为了同时挡住「不要说话」（"要"挡不住，得看得到前面的"不"）。
    [EN] Substring matching is not enough: 「不说话」 contains 说 but is negated.
    [EN] Check the two chars before the verb; a window of 2 also catches 不要说话.
    """
    for v in _AFF_VERB:
        p = t.find(v)
        while p >= 0:
            if not any(m in t[max(0, p - 2):p] for m in ('不', '别', '勿', '莫')):
                return True
            p = t.find(v, p + 1)
    return False


def passive_task_roles(roles: dict) -> list[dict]:
    """任务**条条都是**否定型的角色 —— 他被派成了在场但无事可做。

    入参 `roles` 是解析后的 `{人名: [任务, ...]}`（就是 `角色任务` 那一份）。
    返回 `[{who, tasks}]`，空列表 = 没问题。
    [EN] Roles whose every task is negative -- present on stage with nothing to do.
    """
    out: list[dict] = []
    for name, tasks in (roles or {}).items():
        ts = [str(t).strip() for t in (tasks or []) if str(t).strip()]
        if not ts:
            continue
        neg = [t for t in ts if any(m in t for m in _NEG_MARK)]
        aff = [t for t in ts if _has_affirmative(t)]
        if len(neg) == len(ts) and not aff:
            out.append({'who': str(name), 'tasks': ts})
    return out


def passive_task_note(roles: dict) -> str:
    """把 `passive_task_roles` 压成给作家看的一行。没问题返回空串。"""
    bad = passive_task_roles(roles)
    if not bad:
        return ''
    who = '、'.join(x['who'] for x in bad)
    return (f'{who} 今天只被派了"不做什么"（{len(bad)} 人）—— '
            '他（们）在场上无事可做，必须至少有一条**肯开口 / 肯动手**的事。')


def repeat_issues(text: str) -> list[dict]:
    """这一天正文里的三类重复：`[{kind, what, times, cap}]`，空列表 = 没问题。

    三个检测都是**纯代码、零成本**；修复（`repeat_rewrite_prompt`）只在真有问题时
    才发生（见 `crew/agents._fix_repeats`）。
    [EN] The three kinds of repetition in one day's prose. All three detectors are pure
    [EN] code at zero cost; the repair only happens when something actually fires.
    """
    out: list[dict] = []
    for kind, fn in (('silence', silence_gaze_issues),
                     ('tic', repeated_tic_issues),
                     ('detail', detail_repeat_issues),
                     ('vocative', vocative_share_issues),
                     ('hedge', hedge_reply_issues)):
        try:
            for x in fn(text or ''):
                out.append(dict(x, kind=kind))
        except Exception:                                         # noqa: BLE001
            continue
    return out


def repeat_note(text: str) -> str:
    """把 `repeat_issues` 压成给人看的一行。没问题返回空串。"""
    bad = repeat_issues(text)
    if not bad:
        return ''
    parts: list[str] = []
    for x in bad:
        kind = _REPEAT_KIND_CN.get(str(x.get('kind')), str(x.get('kind')))
        parts.append('{}「{}」{} 次（上限 {}）'.format(
            kind, x.get('what', ''), x.get('times', 0), x.get('cap', 0)))
    return '；'.join(parts)


def repeat_rewrite_prompt(text: str, issues: list[dict]) -> str:
    """把"重复用超了"的正文交给模型修时说的话。

    ★ 与 `rewrite_prompt` 同一条纪律：**只换写法，事实一个字不动**。
      重复不是"写错了"，是"同一个法子用了一次又一次" —— 换的是法子。
    ⚠ 必须给**可数的事实**（"已经 4 次，最多留 2 次"），不说"别重复"这种空话
      （本项目反复实测：可数的事实才压得住）。
    [EN] What to say when handing the model prose that reused a device too often. Same
    [EN] discipline as `rewrite_prompt`: wording only, facts untouched, and always give
    [EN] the **countable fact**.
    """
    lines: list[str] = []
    for x in issues:
        kind = _REPEAT_KIND_CN.get(str(x.get('kind')), str(x.get('kind')))
        lines.append('- {}：\"{}\" 已经用了 **{} 次**，最多留 {} 次'.format(
            kind, x.get('what', ''), x.get('times', 0), x.get('cap', 0)))
    facts = chr(10).join(lines)
    return (
        '下面这一章有**同一个写法用了一次又一次**的地方。请**重写这一章**，把重复散开 —— 要求：' + chr(10)
        + '1. **事实一个字都不许改**：谁做了什么、说了什么、先后顺序、'
           '发生没发生，全部照旧；' + chr(10)
        + '2. 下面这些是**可数的事实**，按上限收：' + chr(10) + facts + chr(10)
        + '3. 收的办法是**换个法子写同一件事**，不是删掉它：' + chr(10)
        + '   · 人物没接住话 ⇒ 别总是\"没应，看某个东西\"：写他**手上的动作**、'
           '写**别人看见他沉默的样子**、写**他想起的一件事**、'
           '或者**干脆跳过这个反应**直接写下一个动作；' + chr(10)
        + '   · 同一句口头禅 ⇒ 只留最有分量的那一两次，其余的换成**别的说法**，'
           '或者让别人替他把话说完；' + chr(10)
        + '   · 同一个道具状态反复交代（炭塌了、灯灭了）⇒ **最多留两次**，'
           '其余地方让它在别人手底下**换个样子出现**（被拨一下、被风扑一下），'
           '或者干脆不写它的状态、只写它在场；' + chr(10)
        + '4. ' + _NO_META_CLAUSE + chr(10)
        + '5. 台词的**原句照留**（口癖那几处除外，那正是要收的）；加引号；' + chr(10)
        + '6. 字数不许因此变少：省下的篇幅补给**别的细节**。' + chr(10)
        + '7. 只输出重写后的正文，不要标题、不要解释。' + chr(10) + chr(10)
        + '── 原文 ──' + chr(10) + str(text or ''))


# ══════════════════════════════════════════════════════════════
#  段落拥挤：一大段塞了十几件事（流水账）
# ══════════════════════════════════════════════════════════════
#: ★★★ **这是"读不下去"最可数的那一条**（2026-10-20 第十二轮）：
#:   真人 18 章（samples/zh）**段落最长 125 字、段内最多 7 件事**；
#:   真跑 snow_v12 最长一段 **638 字、44 件事**，v13 293 字/12 件，v14 334 字/19 件。
#:   —— 5 倍于真人上限，18 章**没有一章越界**。比之前量过的所有指标都干净，
#:   而且它是**纯结构**的（数句子和空行），一点语义都不用判。
#: ⚠ 为什么它比"答非所问""情感轻放"好判：那些是语义层（真人问→答字面零承接
#:   率就 100%）；段落挤不挤只看**一段里断了几句**，没有歧义。
#: ⚠ **不并入 `repeat_issues`**：那边的改写提示词整段都在讲"同一个写法用了一次
#:   又一次"，把"一段太挤"混进去会指错方向 —— 这是独立的毛病，走独立的提示词。
#: ⚠ 判的是**段内事件数**而不是字数：一段可以很长但只要在一件事里打转就不挤
#:   （真人最长那段 125 字只有 7 件事）；反过来，短短一段塞十件事同样是流水账。
# [EN] Structural, not semantic: count clauses per paragraph. Not merged into
# [EN] repeat_issues, whose rewrite prompt is entirely about "same wording again".
PARA_EVENT_CAP = 7
_PARA_SPLIT_RE = re.compile(r'\n\s*\n')


def prose_paragraphs(text: str) -> list[str]:
    """正文段落（跳过标题与引用块）。"""
    body = chr(10).join(l for l in str(text or '').splitlines()
                        if not l.lstrip().startswith(('#', '>')))
    return [p.strip() for p in _PARA_SPLIT_RE.split(body) if p.strip()]


def paragraph_event_counts(text: str) -> list[int]:
    """每段里塞了多少件事（按句号/问号/叹号切出的子句数）。"""
    out = []
    for p in prose_paragraphs(text):
        n = len([s for s in re.split(r'[。！？]', p) if len(s.strip()) > 2])
        out.append(n)
    return out


def crowded_paragraph_issues(text: str) -> list[dict]:
    """某一段塞的事超过 `PARA_EVENT_CAP` ⇒ 读者眼里就是一坨流水账。"""
    counts = paragraph_event_counts(str(text or ''))
    if not counts:
        return []
    worst = max(counts)
    if worst <= PARA_EVENT_CAP:
        return []
    return [{'what': '最长的一段里塞了这么多件事（读起来是一坨流水账）',
             'times': worst, 'cap': PARA_EVENT_CAP}]


def crowded_rewrite_prompt(text: str, issues: list[dict]) -> str:
    """把"一段太挤"的正文交给模型修时说的话。

    ★ 与 `repeat_rewrite_prompt` 同一条纪律：**事实一个字不动**，只动分段。
      这段不是写错了，是**没分好段** —— 十几件事连成一大坨，读者没有换气的地方。
    ⚠ 必须给**可数的事实**（"已经 19 件，最多 7 件"），不说"分一下段"这种空话。
    [EN] Same discipline: facts untouched, only paragraphing changes. Always give the
    [EN] countable fact.
    """
    facts = chr(10).join(
        '- {}：已经 **{} 件**，最多 {} 件'.format(
            x.get('what', ''), x.get('times', 0), x.get('cap', 0))
        for x in issues)
    return (
        '下面这一章有**一段塞了太多件事**的地方（读起来是一坨，没有换气的地方）。'
        '请**重写这一章**，把挤在一起的事拆开 —— 要求：' + chr(10)
        + '1. **事实一个字都不许改**：谁做了什么、说了什么、先后顺序、'
           '发生没发生，全部照旧；' + chr(10)
        + '2. 下面这些是**可数的事实**，按上限收：' + chr(10) + facts + chr(10)
        + '3. 收的办法是**把一段拆成几段**，不是删掉事情：' + chr(10)
        + '   · 换一个人说话、换一个动作的主体、换一个时间上的停顿，'
           '就是另起一段的地方；' + chr(10)
        + '   · 挑**最有分量的两三件**各自写足（那句话、那个动作、对方的反应），'
           '其余的**一句带过**；' + chr(10)
        + '4. ' + _NO_META_CLAUSE + chr(10)
        + '5. 台词的**原句照留**；加引号；' + chr(10)
        + '6. 字数不许因此变少：省下的篇幅补给**别的细节**（手上的动作、'
           '屋里的变化、别人在做什么）。' + chr(10)
        + '7. 只输出重写后的正文，不要标题、不要解释。' + chr(10) + chr(10)
        + '── 原文 ──' + chr(10) + str(text or ''))


# ══════════════════════════════════════════════════════════════
#  话题打转 / 动作打转（2026-10-20 第十二轮，用户点名"用 LLM 判官"）
# ══════════════════════════════════════════════════════════════
#: ★★★ 这一条的**判决不在代码里**，在 LLM 判官那儿。代码只做三件可数的事：
#:   (a) 给判官**备料**（哪些词出现得密，帮它快速定位）；
#:   (b) 判官回话的**解析层**（判官说没打转 ⇒ 一个字都不许改）；
#:   (c) 修复提示词（只给可数事实，不说空话）。
#:
#: 为什么字面判据在这里**必须**让位（这是正面证据，不是偷懒）：
#:   · 打转是**换了说法**的重复。v16 里驹子把同一件事问了 7 遍 ——
#:     「好人是不是都没好报」「什么样的人才算有好报」「我是不是好人」
#:     「我到底算不算好人」—— 措辞一次都不重样，二元组聚类捞不到；
#:   · 叶子送酒 5 次同样不重样：「将酒壶搁在火钵旁」「端进一壶温酒」
#:     「把温酒放火钵边」「壶搁这儿」「酒给您放这了」。实测**动宾紧邻**的
#:     正则在真人 18 章最大 1 次、真跑也是 1 次 —— **零区分度**；
#:   · 全文 2-gram 峰值也废：真人的 top 是**角色名**（阿箬 14、沈砚 10），
#:     剔掉名字后是**核心道具**（老河 14、簿子 8），真跑 v16 是火钵 13。
#:     人是这么写小说的，这个量分不出病；
#:   · 而"字面零承接"在真人里是 **100%**（比真跑还高），拿来判会打死真人。
#:   ⇒ 四条路全堵死后，唯一判得了的是**读得懂语义的那一位**，即判官。
#:
#: ⚠ 所以**不设门槛**：正文够长就问判官（用户原话"阈值可以低一些"）。
#:   误报的代价只是多花一次调用 —— 判官说"没打转"就绝不改稿，安全在解析层。
# [EN] The verdict lives in the LLM judge, not in code. Code only prepares material,
# [EN] parses the verdict, and writes the repair prompt. No gating threshold: a false
# [EN] alarm costs one call, and "no spin" means the text is never touched.

#: 给判官备料时用：出现 >= 这么多次的实词才值得提一句。
# [EN] Material for the judge: only content words appearing at least this often.
TOPIC_HOT_CAP = 3

#: 这么短的正文没什么可打转的，不值得问判官。
# [EN] Too short to spin; not worth a judge call.
SPIN_MIN_LINES = 3

#: 会被当成实词的虚字（2-gram 里任一位命中就丢掉）。
# [EN] Function characters: a 2-gram is dropped if either slot hits these.
_TOPIC_GRAM_STOP = set('的了着过是在和与就都也还很太更最把被将给让对向为从'
                       '一二三四五六七八九十这那他她我你它'
                       '们个上下里外中间前后些怎样谁么呢吗吧啊呀哦噢啦')


def topic_hotspots(text: str, *, cap: int = TOPIC_HOT_CAP,
                   names: tuple = ()) -> list[tuple[str, int]]:
    """全文里出现 >= `cap` 次的实词（2 字），按次数降序。

    ⚠ 这只是**给判官看的备料**，不是判决 —— 见本块顶部那四条实测。
      真人小说的 top 永远是角色名和核心道具，所以这里把**角色名剔掉**，
      剩下的高频词交给判官当线索，判不判打转由它说了算。
    [EN] Material for the judge, never a verdict. Character names are stripped; what
    [EN] remains is handed to the judge as a hint.
    """
    counts: dict[str, int] = {}
    for run in re.findall(r'[\u4e00-\u9fff]{2,}', str(text or '')):
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            if g[0] in _TOPIC_GRAM_STOP or g[1] in _TOPIC_GRAM_STOP:
                continue
            counts[g] = counts.get(g, 0) + 1
    names = tuple(str(n or '') for n in (names or ()) if n)
    out = [(w, n) for w, n in counts.items()
           if n >= max(2, cap)
           and not any(w in nm or nm in w for nm in names)]
    return sorted(out, key=lambda kv: (-kv[1], kv[0]))[:8]


#: 判"同一件事"时要剥掉的**疑问外壳与语气词**。只去外壳，不动实词 ——
#: 「我是不是个好人」「好人是不是都没好报」剥完剩「个」「没好报」，
#: 「算不算好人」剥完剩「算好人」，实词部分重合才判同题。
# [EN] Shell words stripped before comparing two lines' content skeletons.
_REP_SHELL_RE = re.compile(
    r'[？?！!。，、；：…—\s“”"「」『』]|'
    r'是不是|好不好|对不对|算不算|要不要|能不能|可不可|'
    r'到底|究竟|倒是|你就|我说|你说|我就|'
    # ⚠ `我是` 必须加负向前瞻：不加它会在「我是不是」里把 `我是` 先吃掉，
    #   剩一个「不是个好人」⇒ 骨架失真，「我是不是个好人」与
    #   「算不算好人」再也聚不到一起（实测：这正是 X1 变红的原因）。
    # [EN] `我是` needs the negative lookahead, otherwise it eats the `我是` inside
    # [EN] 「我是不是」 and the remaining skeleton no longer matches its siblings.
    r'我是(?![不])|你看')
_REP_STOP_RE = re.compile(r'[\u4e00-\u9fff]{2,3}(?=（|说|道|问|笑|听|看|站|走)')
#: **纯虚字**。两个字**都**在里面的 2-gram 不算"共同话题"。
#: ⚠ 不滤这个，`了的`「人也」「是啊」会把毫不相干的台词串成一个大组 ——
#:   实测 v19 聚出一个 **15 条**的巨组、v18 一个 14 条，全是这么串起来的。
#: 只滤"两个都虚"的（`凉了` 里"凉"是实字，保留）。
# [EN] Function words. A bigram whose two characters are **both** function words is not
# [EN] a topic; keeping them merged unrelated lines into 15-line blobs.
_REP_FUNC = set('的了是在有和这那就都不也很还要会说着到上下里外来去过把被让给'
                '对于与以及或其所更最一二三四五六七八九十好多次个件条张只'
                '我你他她它们么呢吗呀啊吧嘛哦嗯之而且但如若虽因所以从向')


def _unit_of(text: str, a: int, b: int) -> str:
    """取**最小可删单位**：`[引导语起点, 闭引号]`。

    ★ 为什么不用 `_narration_spans` 的"整句"：那在台词面前会被拉成**一整段**
      （台词里的 `。` 全被蒙掉，段落末尾的 `。` 才算句末），拿去删会一口气删掉
      半段 —— 实测走的就是这条路，删掉了「给句准话」这种好句子。
      ⇒ 单位 = 从上一个句末（或行首）到这一句的闭引号：
        `驹子抬头看岛村，轻声说：“你看我，是不是个好人？”`
        这才是"一句台词 + 它的引导语"，删掉正好是一个拍子。
    [EN] Minimal deletable unit: from the previous sentence end (or line start) up to
    [EN] the closing quote of this line. `_narration_spans` yields paragraph-sized
    [EN] "sentences" once dialogue marks are masked, which deletes far too much.
    """
    src = str(text or '')
    start = a
    while start > 0 and src[start - 1] not in '。！？…' + chr(10):
        start -= 1
    end = b + 1 if b < len(src) and src[b] in '”」』"' else b
    return src[start:end].strip().lstrip('”」』"')


def repeat_clusters(text: str, *, thr: float = 0.5,
                    min_share: int = 2,
                    rare_df: int = 3,
                    min_size: int = 2) -> list[list[str]]:
    """把**疑似同一件事**的台词聚成组，返回**最小可删单位**（引导语 + 台词）。

    ★★★ 2026-10-20 加。分工的理由：
      打转的病根是**换了说法的重复**（「我是不是好人」「好人是不是都没好报」
      「算不算好人」），所以字面比对**抓不到**（`diag_repeat_context.py` 实测：
      真人最长同题链 4、真跑全是 1–2，零区分度）。
      但"哪几句疑似说的是同一件事"是**可算**的；"这几句里哪句是手法、哪句是病"
      才是**要语境**的。
      ⇒ 代码算前一半，判官判后一半。判官拿到这些组，就不必自己在一整章里找，
        也就不会把「给句准话」这种**推进句**当成重复删掉（实测踩过）。

    ★ 返回**可删单位**而不是台词：判官按组内序号表态（"删第 2 条"），
      代码直接用那一整段去删 —— 不必让判官抄句子（抄错一个字就删不动，
      这是上一版实测到的另一个坑）。
    ⚠ 聚类要**共享至少 `min_share` 个实词**：只按比例算，剥掉人称与疑问外壳后
      2-gram 只剩一两个，会把不相干的句子连成一组（实测把「是不是个好人」
      和「叶子她不太会说话」连到了一起）。
    [EN] Return the minimal deletable unit per line, and require at least
    [EN] `min_share` shared content bigrams: ratio alone lets two-word remnants
    [EN] link unrelated sentences.
    """
    raw = str(text or '')
    spans = _quoted_spans(raw)
    if len(spans) < min_size:
        return []
    qs: list[str] = []
    units: list[str] = []
    for a, b, inner in spans:
        qs.append(str(inner or '').strip())
        units.append(_unit_of(raw, a, b))
    n = len(qs)
    sk: list[set[str]] = []
    for q in qs:
        body = _REP_SHELL_RE.sub('', str(q or ''))
        body = _REP_STOP_RE.sub('', body)
        body = re.sub(r'[^\u4e00-\u9fff]', '', body)
        sk.append({body[i:i + 2] for i in range(max(0, len(body) - 1))
                   if not (body[i] in _REP_FUNC and body[i + 1] in _REP_FUNC)})
    parent = list(range(n))

    # ★★★ **文档频率**（2026-10-20 实测补的那一刀）
    #   长句的共享比例天然低：v20 里「茶凉了的话，我让人再送一壶来」与
    #   「茶凉了就凉了吧，喝口凉的也无妨」共享 {茶凉, 凉了} 两个词，
    #   但两边各有 12 个 2-gram ⇒ 比例 0.17，按比例算一条都聚不到。
    #   而「茶凉」这种词**只在 2–3 条台词里出现**，它恰恰就是"具体共同话题"。
    #   ⇒ 加一条并列条件：共享的词里有任何一个 df ≤ `rare_df`，也算同一件事。
    # [EN] Document frequency: long lines share only two bigrams out of twelve
    # [EN] (ratio 0.17), yet those two are the actual topic. A shared bigram that
    # [EN] appears in at most `rare_df` lines is itself evidence of a common topic.
    df: dict[str, int] = {}
    for s in sk:
        for w in s:
            df[w] = df.get(w, 0) + 1

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        # ⚠ **不限近邻**：打转的重复本来就是**跨拍**的 —— 实测 v19 里
        #   「我是不是个好人」出现在第 0 / 12 / 30 条，限 8 条近邻就一条都聚不到。
        #   代价是 O(n²)，但一章台词几十条，可以忽略。
        # [EN] No adjacency window: a spin repeats **across beats**, so limiting to
        # [EN] neighbours misses every real case. O(n^2) on a few dozen lines is free.
        for j in range(i + 1, n):
            a, b = sk[i], sk[j]
            if not a or not b:
                continue
            shared = a & b
            if not shared:
                continue
            # ⚠ `min_share` 要**自适应**：短句剥掉外壳后骨架可能只剩一个词
            #   （「我是不是个好人」→ {好人}），这时共享 1 个就已经是全部证据，
            #   写死 2 会让它们永远聚不到一起（实测：X1 就是这么变红的）。
            # [EN] `min_share` must adapt: after stripping shell words a short line may
            # [EN] keep a single bigram, and one shared bigram is then all the evidence.
            _need = min(min_share, len(a), len(b))
            _ratio_ok = (len(shared) >= _need
                         and len(shared) / min(len(a), len(b)) >= thr)
            _topic_ok = any(df[w] <= rare_df for w in shared)
            if not (_ratio_ok or _topic_ok):
                continue
            ra, rb = find(i), find(j)
            if ra != rb:
                parent[rb] = ra
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out: list[list[str]] = []
    for idxs in groups.values():
        if len(idxs) < min_size:
            continue
        seen: list[str] = []
        for i in sorted(idxs):
            u = units[i] or qs[i]
            if u and u not in seen:
                seen.append(u)
        if len(seen) >= min_size:
            out.append(seen)
    return out


def repeat_groups_note(text: str) -> str:
    """把疑似重复组写成给判官看的一段话（组号 + 条号 + 整句原样）。

    ⚠ 只给**事实**（哪几句像是同一件事），不给结论 —— 结论是判官的事。
    ⚠ 组里给的是**整句**（含说话人和动作）：判官只要回"删第几条"，
      代码就能精确删掉那一整句，不必让模型抄句子。
    """
    groups = repeat_clusters(text)
    if not groups:
        return ''
    out = ['下面这几组**像是**在说同一件事（按实词骨架算的，仅供参考）：']
    for k, g in enumerate(groups, 1):
        out.append(f'组 {k}（{len(g)} 条）：')
        for i, x in enumerate(g[:6], 1):
            out.append('  %d) %s' % (i, str(x)[:80]))
    out.append('⚠ 这是**候选**，不是结论。**每一组都要真的判一次**：')
    out.append('  · 有些组是正经写法（回声式对答 / 复沓 / 被逼问的第二次 / '
               '一个人反复用同一句挡话）—— 那种整组留；')
    out.append('  · 有些组就是病（换个说法把同一件事再说一遍，对面**毫无新反应**，'
               '删掉中间那几条读者什么也不损失）—— 那种要删。')
    out.append('  ⚠ **不许因为"可能是手法"就一律放过**：'
               '一组的条数越多、对面的反应越没变化，越像是病。')
    return chr(10).join(out)


def spin_judge_prompt(text: str, hots: list[tuple[str, int]]) -> str:
    """请判官判"这一章有没有在同一个地方打转"时说的话。

    ★ 关键是**把"不算打转"的三条也写进去** —— 只写正例的话，判官会把
      "火钵出现 13 次"当成打转，于是改稿改掉舞台，稿子反而更空。
    [EN] Ask the judge whether this chapter spins in place. The negative examples
    [EN] matter as much as the positive ones: without them the judge would call the
    [EN] recurring *stage props* a spin and strip the setting out of the prose.

    ★★★ 2026-10-20 改：**从"整章是不是打转"变成"每一条该留还是该删"**
    ---------------------------------------------------------------
    用户原话：「不是所有重复都有问题，要结合上下文语境进行分析」。
    他说得对，而且这条在真人小说里能直接验到：`samples/zh` 有一章通篇是
    一问一答的**回声式对答**，字面重合 100%，却是**极好**的写法
    （语气一句比一句短，戏在往前走；具体是哪一章记在
    `developers/diag_repeat_context.py` 的注释里，**故意不写进提示词**——
    提示词里的例子会被模型当素材抄，这是本项目的老坑）。
    上一版判官只回一句"打转 + 出处"，代码就只能整章重写；
    整章重写改掉一处会碰别处，于是复检一报"还打转"，整篇被退回原文
    （snow_v19 的日志就是：`打转判官报了（5 条出处）`→`修复后判官仍报（保留原文）`）。

    ⇒ 判官的活儿要细到**每一条**：这条删了，读者损失什么？
      · 说得出一件具体的损失（谁知道了新东西 / 谁的态度变了 / 谁被逼到哪一步 /
        前面的伏笔在这里落地）⇒ **留**；
      · 说不出来 ⇒ **删**。
    这是"结合语境"的可执行化：不是"重复了几次"，而是"这一次有没有承载"。
    [EN] ★★★ Changed to a **per-line keep/drop** judgement. The single standard is
    [EN] deletability: what does the reader lose if this line goes? A concrete loss
    [EN] (new knowledge, a shift in attitude, pressure applied, a setup paying off)
    [EN] means keep; nothing concrete means drop. Literal repetition proves nothing --
    [EN] one human sample answers "你认得路。/ 认得。" at 100% overlap and it is superb.
    """
    hint = chr(10).join('- {} ×{}'.format(w, n) for w, n in (hots or []))
    if not hint:
        hint = '- （没有明显的高频词）'
    groups = repeat_groups_note(text)
    return (
        '你是中文小说的终审编辑。下面这一章，只请你判一件事：'
        '它有没有在**同一个地方打转**。' + chr(10) + chr(10)
        + '⚠ 先把标准说清楚：**重复本身不是毛病**。' + chr(10)
        + '小说里有好几种重复是**正经写法**，遇到要留着：' + chr(10)
        + '· **回声式对答**：一个问，另一个把话捡回去再说一遍（语气越来越短）；' + chr(10)
        + '· **复沓 / 顶真**：把上一句的尾音重复一次，做成确认或者递进；' + chr(10)
        + '· **不同的人说同一句**：信息在传，或者听岔了；' + chr(10)
        + '· **激动时同句连说两遍**：那时的语气本身就是内容；' + chr(10)
        + '· **呼应**：前面说过的话，到后面再出现一次，意思已经变了；' + chr(10)
        + '· **对面明确回避之后的再一次追问**：那是在逼，逼一次是戏。' + chr(10) + chr(10)
        + '⚠ 但上面这几条**都有边界**，别拿它们当免罪符：' + chr(10)
        + '· **敷衍只有在态度有层次时才算手法**：第一次敷衍、第二次不耐烦、'
           '第三次干脆不答 —— 那是在立人物。如果他从头到尾只有同一句、'
           '同一个动作、连语气词都一样，那不是立态度，是**作者图省事**。' + chr(10)
        + '· **逼问只在对面有反应变化时才算戏**：对面一直没变，'
           '第二遍是在逼，第三遍起就只是重复。' + chr(10) + chr(10)
        + '★★★ **最强的病的信号是：对面的反应一模一样。**' + chr(10)
        + '一个人问了 N 遍，对面每一遍都是同一句、同一个动作'
        + '（连"是啊""嗯"这种语气词都一样，换的只是手上的小动作）——'
        + '那就是打转，**哪怕提问的措辞每次都不同**。'
        + '措辞变了不算推进；只有**信息、态度、处境**变了才算推进。' + chr(10) + chr(10)
        + '打转是另一回事 —— 它有两种样子：' + chr(10)
        + '1. **话题打转**：同一个人把**同一个诉求**问了两遍以上，'
           '而对面**每一遍的反应都一样**（还是那句回避，还是没接住）；' + chr(10)
        + '2. **动作打转**：同一个人把**同一个动作**做了一遍又一遍'
           '（送东西、搁下、带门、添火、提醒夜深、劝人歇息……），'
           '每次换个说法，办的是同一件事。' + chr(10) + chr(10)
        + '★★★ 判每一条的时候，只用一个办法：' + chr(10)
        + '**假设把这一条整句删掉，读者会损失什么？**' + chr(10)
        + '· 说得出一件**具体**的损失（谁知道了新东西 / 谁的态度变了 / '
           '谁被逼到了哪一步 / 哪一处伏笔在这里落地）⇒ 判「留」；' + chr(10)
        + '· 说不出具体的损失，只剩"气氛""节奏""她又在问" ⇒ 判「删」。' + chr(10)
        + '⚠ 一组里**必须留下第一条和最后一条**（第一次开口、和最后那次收束）；'
           '要删就删中间那几条 —— 除非中间那条本身就带来新东西。' + chr(10)
        + '⚠ **敷衍式的应答不算重复**：一个人反复用同一个短句挡话'
           '（同意、嗯、是啊），那是他的态度，删掉这个人物就没有嘴脸了 —— '
           '这种组**整组判「留」**。' + chr(10)
        + '⚠ 逼问也一样有边际：**对面一直没换反应**时，第二遍是在逼，'
           '第三遍开始就只是重复 —— 中间那几遍判「删」，留第一遍和最后一遍。' + chr(10) + chr(10)
        + '⚠ 下面这些**不许算进打转**，也不许判删：' + chr(10)
        + '· 同一个**道具或场景**被反复提到（火钵、纸门、雪、窗）—— '
           '那是舞台，不是动作；' + chr(10)
        + '· **人名、地名、物件名**出现得多 —— 真人小说本来就是这样。' + chr(10) + chr(10)
        + '这一章里出现得比较密的词（**仅供参考，别当成证据**）：' + chr(10)
        + hint + chr(10) + chr(10)
        + (groups + chr(10) + chr(10) if groups else '')
        + '只输出下面这个格式，不要解释、不要别的字：' + chr(10) + chr(10)
        + '判定：打转' + chr(10)
        + '那一件事：<一句话说清是哪一件事在打转>' + chr(10)
        + ('逐组：' + chr(10)
           + '- 组 1：删 2' + chr(10)
           + '- 组 2：整组留' + chr(10)
           + '（每一组都要表态；"删 N" 是**只删第 N 条**，'
             '也可以写成 "删 2,3" 删两条。）' + chr(10)
           if groups else
           '逐条：' + chr(10)
           + '- 删｜<把这一句**整句原样**抄下来，连说话人和动作一起>｜'
             '删掉损失：没有' + chr(10)
           + '- 留｜<同样整句抄>｜删掉损失：<一句话，写清具体损失什么>' + chr(10))
        + chr(10) + '（如果没打转，就写两行：' + chr(10)
        + '判定：没打转' + chr(10)
        + '理由：<一句话说清为什么这些重复不算病 —— 是舞台？是人物关系？'
          '是有推进？>）' + chr(10)
        + chr(10) + chr(10)
        + '── 这一章 ──' + chr(10) + str(text or ''))


#: 判官回话里"判定："那一行。**否定词必须比"打转"先查**：「没打转」里也有"打转"。
# [EN] The verdict line. Negations must be checked first: 没打转 contains 打转.
_SPIN_VERDICT_RE = re.compile(r'判定\s*[：:]\s*([^\n]{0,24})')
_SPIN_NEG_RE = re.compile('(没|不|无|非|未)')
_SPIN_WHAT_RE = re.compile(r'那一件事\s*[：:]\s*([^\n]{0,120})')
#: 判"没打转"时的理由行。**只进日志**，不参与任何判断 ——
#: 它的用处是排查"判官凭什么放过这一章"（判官有抖动，不给理由就查不清）。
# [EN] The reason line when the judge says "no spin". Log-only; never a decision input.
_SPIN_WHY_RE = re.compile(r'理由\s*[：:]\s*([^\n]{0,120})')
_SPIN_WHERE_RE = re.compile(r'重复的出处\s*[：:]\s*(.*)', re.S)
#: 「逐条」块里的一条：`- 删｜<整句>｜删掉损失：…`（竖线全角半角都收）。
#: ⚠ 判决词必须在**最前面**且**只认单字**：写成"不删"会被 `删` 命中 ——
#:   这与「没打转」「没听清」「没问题」是同一个坑（本项目第四次）。
# [EN] One line of the per-line verdict. The verdict word must be at the head and is
# [EN] matched as a single character; "不删" would otherwise be read as 删.
_SPIN_ITEM_RE = re.compile(
    r'^[-·*•\s]*([删留])\s*[｜|]\s*(.+?)(?:\s*[｜|]\s*删掉损失\s*[：:]\s*(.*))?$')
_SPIN_ITEMS_RE = re.compile(r'逐条\s*[：:]\s*(.*)', re.S)
#: 判「删」时"损失"必须写成**没有**之类；写成具体损失的，**按留处理**（安全侧）。
_SPIN_NOLOSS_RE = re.compile(r'^(没有|无|没什么|说不上|无损失|0|零)\s*[。.]?$')
#: 「逐组」块的一行：`- 组 2：删 2` / `- 组 2：整组留` / `- 组 2：删 2,3`
_SPIN_GROUP_RE = re.compile(
    r'^[-·*•\s]*组\s*(\d+)\s*[：:]\s*(.+)$')
_SPIN_GROUPS_RE = re.compile(r'逐组\s*[：:]\s*(.*)', re.S)
_SPIN_DEL_RE = re.compile(r'删\s*([\d\s,，、]+)')


def parse_spin_verdict(raw: str, text: str = '') -> dict:
    """解析判官回话 ⇒ `{'spin', 'what', 'where', 'drops', 'keeps'}`。

    ★★★ **看不懂一律当"没打转"** —— 这一步回的是"要不要改稿"，
      宁可漏改，也不许因为解析错把一篇好稿改坏。
    [EN] Parse the judge's verdict. Anything unreadable counts as "no spin": this
    [EN] answers whether to rewrite, and a wrong **yes** damages good prose.

    ★★★ 2026-10-20：多了 `drops` / `keeps` 两组（判官逐条给的"删/留"）。
    `text` 传原文时要用来**重算重复组**（判官回的是"组 N 删 M"，得知道第 N 组第 M 条
    是哪一句）；不传就只认「逐条」那种老格式。
    `drops` 只收**同时满足**的：
      ① 判词是「删」；② 用的是组内序号、且不是首尾两条；③
      「逐条」老格式里还要求"删掉损失"写的是**没有**。
    这是"结合语境"的落点：语境判断在判官那儿，代码只负责**不越权**。
    [EN] `drops` requires all three: verdict 删, an interior index (never the first or
    [EN] last of a group), and -- in the legacy per-line format -- an explicit "no loss".
    """
    s = str(raw or '')
    m = _SPIN_VERDICT_RE.search(s)
    if not m:
        return {'spin': False, 'what': '', 'where': [],
                'drops': [], 'keeps': [], 'reason': '没有判定行'}
    verdict = m.group(1).strip()
    if '打转' not in verdict:
        return {'spin': False, 'what': '', 'where': [],
                'drops': [], 'keeps': [], 'reason': '判定行里没有"打转"'}
    if _SPIN_NEG_RE.search(verdict):
        _why = _SPIN_WHY_RE.search(s)
        return {'spin': False, 'what': '', 'where': [],
                'drops': [], 'keeps': [],
                'reason': ('判官说没打转：' + _why.group(1).strip())
                if _why else '判官说没打转'}
    wm = _SPIN_WHAT_RE.search(s)
    what = wm.group(1).strip() if wm else ''
    where: list[str] = []
    dm = _SPIN_WHERE_RE.search(s)
    if dm:
        for ln in str(dm.group(1) or '').splitlines():
            c = ln.strip().lstrip('-·*0123456789. ')
            if len(c) >= 4:
                where.append(c)

    drops: list[str] = []
    keeps: list[str] = []
    # ① 「逐组」表态（2026-10-20 起的主路）：组 N 删 M ⇒ 取第 N 组第 M 条。
    #   ★ 组里的"条"是 `repeat_clusters` 算出来的**最小可删单位**，
    #     所以判官不必抄句子（抄错一个字就删不动，这是上一版实测的坑）。
    #   ★ 每组**第一条与最后一条永远不删**：那是"第一次开口"与"最后收束"，
    #     提示词里写过，但 prompt 写了 ≠ 生效 ⇒ 这里硬拦。
    # [EN] Group verdicts: 组 N 删 M. The first and last item of every group are
    # [EN] never droppable -- both ends carry the beat.
    gm = _SPIN_GROUPS_RE.search(s)
    groups: list[list[str]] = []
    if gm and text:
        try:
            groups = repeat_clusters(str(text))
        except Exception:                                        # noqa: BLE001
            groups = []
        for ln in str(gm.group(1) or '').splitlines():
            ln = ln.strip()
            if not ln:
                continue
            mm = _SPIN_GROUP_RE.match(ln)
            if not mm:
                continue
            gi = int(mm.group(1)) - 1
            body = mm.group(2)
            if gi < 0 or gi >= len(groups):
                continue
            dm = _SPIN_DEL_RE.search(body)
            if not dm:
                continue                          # 「整组留」
            picks: list[int] = []
            for tok in re.split(r'[,，、\s]+', dm.group(1).strip()):
                if tok.isdigit():
                    picks.append(int(tok))
            for p in picks:
                i = p - 1
                # ⚠ 第一条**永远不删**（第一次开口）。
                #   最后一条只在**三条以上**时才保 —— 两条的组若保两头，
                #   这条就一条也删不了（实测踩过：组 1 只有 2 条，判官说"删 2"，
                #   被首尾规则整条拦掉，`drops` 直接变 0，整条修复链静默失效）。
                # [EN] Never drop the first item. Keep the last only in groups of three
                # [EN] or more: in a two-item group that rule blocks everything.
                if i <= 0:
                    continue
                if len(groups[gi]) >= 3 and i >= len(groups[gi]) - 1:
                    continue
                cand = groups[gi][i]
                if cand and cand not in drops:
                    drops.append(cand)
    # ② 「逐条」表态（老路，兼容没有组的章）
    im = _SPIN_ITEMS_RE.search(s)
    for ln in str(im.group(1) if im and not groups else '').splitlines():
        ln = ln.strip()
        if not ln or ln.startswith('（'):
            continue
        mm = _SPIN_ITEM_RE.match(ln)
        if not mm:
            continue
        mark, body, loss = mm.group(1), mm.group(2).strip(), \
            (mm.group(3) or '').strip()
        body = body.strip().strip('“”"「」')
        if len(body) < 6:
            continue
        if mark == '留':
            keeps.append(body)
            continue
        # 判「删」：损失那栏必须是**明写的"没有"**，否则按留处理（安全侧）
        if loss and not _SPIN_NOLOSS_RE.match(loss):
            keeps.append(body)
            continue
        if not loss:
            continue                 # 没写损失 ⇒ 不下结论，两边都不进
        drops.append(body)
    return {'spin': True, 'what': what, 'where': where,
            'drops': drops, 'keeps': keeps, 'reason': ''}


def spin_rewrite_prompt(text: str, verdict: dict) -> str:
    """判官说打转了 ⇒ 把这一章交给模型收拢时说的话。

    ★ 与 `repeat_rewrite_prompt` 同一条纪律：**事实一个字不动**。
      这里给的"可数事实"是判官抄出来的**原句**，不是我们猜的。
    [EN] Same discipline: facts untouched. The countable facts are the judge's own
    [EN] quoted lines, not our guesses.
    """
    what = str(verdict.get('what') or '').strip() or '（判官没写清是哪一件事）'
    where = verdict.get('where') or []
    lines = chr(10).join('- {}'.format(x) for x in where[:8]) \
        or '- （判官没抄出原句）'
    return (
        '下面这一章**在同一个地方打转了**。判官给出的事实如下：' + chr(10)
        + '· 打转的那一件事：' + what + chr(10)
        + '· 打转的出处（原句）：' + chr(10) + lines + chr(10) + chr(10)
        + '请**重写这一章**，把打转的地方收拢 —— 要求：' + chr(10)
        + '1. **事实一个字都不许改**：谁做了什么、说了什么、先后顺序、'
           '发生没发生，全部照旧；' + chr(10)
        + '2. **同一件事别一直绕**：问了就得有人接住 —— 哪怕答得含糊、'
           '哪怕答得躲，也必须是**往前走的一句**；连着两次没被接住，'
           '就该换话题了；' + chr(10)
        + '3. **同一个动作别做第二遍**：她已经来过一次了，'
           '后面再需要这个人出现在门口，就该是另一件事、另一只手 —— '
           '别让读者觉得"她怎么又端着这个来了"；' + chr(10)
        + '4. ' + _NO_META_CLAUSE
        + '（上一版的这一章真出过这个病，最后是靠删掉那半句治好的。）' + chr(10)
        + '5. 省下的篇幅补给**别的东西**：那个人当时手上的动作、屋里的变化、'
           '旁边的人在做什么；' + chr(10)
        + '6. 台词的**原句照留**（可以挪位置）；加引号；' + chr(10)
        + '7. **字数不许因此变少**；' + chr(10)
        + '8. 只输出重写后的正文，不要标题、不要解释。' + chr(10) + chr(10)
        + '── 原文 ──' + chr(10) + str(text or ''))


# ══════════════════════════════════════════════════════════════
#  悬空第三人称（2026-10-19 第十一轮，用户点名"最致命"的一条）
# ══════════════════════════════════════════════════════════════
#: 所有会被当成引号的字符。**ASCII 的 `"` 和 `'` 开闭同形**，
#: 所以不能按"开/闭"配对（见 `_quoted_spans`）。
# [EN] Every character treated as a quote mark. ASCII `"` and `'` are the same glyph for
# [EN] open and close, so they cannot be paired by direction (see `_quoted_spans`).
_QUOTE_CHARS = '“”「」『』＂＂"\'\''

#: 第三人称单数代词。**不含"他们/她们"** —— 复数往往指一群人，
#: 而"一群人没有先行语"是另一种病（此处不判，免得把正常写法打死）。
# [EN] Third-person singular pronouns. **Not 他们/她们** -- the plural refers to a group,
#: # [EN] and "a group with no antecedent" is a different illness (not judged here).
_PRONOUNS = ('他', '她')


def _quoted_spans(text: str) -> list[tuple[int, int, str]]:
    """成对的引语区间：`[(起, 止, 内容)]`。**按出现顺序两两配对**。

    为什么不能按方向配对：中文正文里 `"`（ASCII 双引号）和 `'`（ASCII 单引号）
    **开闭是同一个字符** —— 剧本体、导演事件、LLM 返回里到处都是。
    按方向配会把 `说"她恨我"，又笑"算了"` 拆坏。

    ⚠ 落单的那个引号（奇数个）**忽略**：宁少判，也不把半句话当引语。
    [EN] Paired quoted spans as `[(start, end, content)]`, paired **in order of appearance**.
    [EN] ASCII `"` and `'` use the same glyph for open and close in Chinese prose, so
    [EN] direction-based pairing would break 「说"她恨我"，又笑"算了"」 apart. ⚠ An unpaired
    [EN] (odd) quote mark is **ignored**: better to under-report than to treat half a
    [EN] sentence as a quotation.
    """
    t = str(text or '')
    if not t:
        return []
    pos = [i for i, ch in enumerate(t) if ch in _QUOTE_CHARS]
    out: list[tuple[int, int, str]] = []
    for k in range(0, len(pos) - 1, 2):
        a, b = pos[k], pos[k + 1]
        if b <= a + 1:
            continue
        inner = t[a + 1:b]
        if not inner.strip() or len(inner) > 200:
            continue
        out.append((a, b, inner))
    return out


def has_quoted_speech(text: str) -> bool:
    """这段文字里**有没有引语**（成对的引号包着非空内容）。

    唯一的调用方是导演事件的硬闸（`director/engine._inject_event`：
    事件是"发生的事"，不是"某人说的一句话"）。做成**公开函数**而不是让那边
    自己写个正则 —— "同一件事两处实现"是万恶之源，引号口径必须一处定。
    [EN] Whether the text contains quoted speech (a non-empty span between paired quote
    [EN] marks). Its only caller is the director's event gate. Kept public rather than
    [EN] letting the caller write its own regex: the quote rule must be defined in one place.
    """
    return bool(_quoted_spans(text))


def _third_persons(inner: str) -> list[tuple[int, str]]:
    """引语里出现的第三人称单数代词（`[(位置, 代词)]`）。

    排除两种**不是指代**的形状：
      · `其他` 的 `他`（"其他"是一个词，不指人）；
      · `他们` / `她们`（复数，见 `_PRONOUNS` 上面的说明）。
    [EN] Third-person singular pronouns inside a quotation, excluding 其他 and plurals.
    """
    s = str(inner or '')
    out: list[tuple[int, str]] = []
    for i, ch in enumerate(s):
        if ch not in _PRONOUNS:
            continue
        if i and s[i - 1] == '其':
            continue
        if s[i + 1:i + 2] == '们':
            continue
        out.append((i, ch))
    return out


def dangling_reference(text: str, *, speaker: str = '', to: str = '',
                       names=()) -> list[dict]:
    """**引语里的第三人称指代落不到地上**的地方。返回 `[{pron, quote, at}]`，空 = 没问题。

    ★★★ 为什么要有它（2026-10-19 第十一轮，用户点名"最致命"）
    -------------------------------------------------------------------
    真跑产物里反复出现同一句：`驹子忽然安静，说"她恨我"，又笑着说"算了"`。
    **六次独立真跑、五次命中同一句**（`snow_v10` / `snow_v11` / `scale1` /
    `snow_thread3` / `snow_time1` / `ykg1000`），而这句话在正文里
    **全文找不到"她"是谁** —— 情感分量很重，却没有一点承接。

    它的**可数形状**是：
    > 一句引语里用了第三人称代词，而**同一行里、引语之前**，
    > 除说话人自己之外**没有出现过任何人名**。

    为什么按"同一行"判，不按"同段"或"全文"：
      · 这一行材料的**读者就是改写层的小说作家** —— 他手上只有这些行。
        写的人都不知道"她"是谁，读的人更不可能知道；
      · 按"全文"判就永远抓不到：这一章里到处都有名字（实测：放宽到同段后
        这条判据一次都不红）。

    ⚠ **认不出的那种**（已知的漏，写在这里免得后来人以为它万能）：
      同一行里**出现过别的名字**时不判 —— 即使那个名字只是顺带被提到
      （`驹子接下门边叶子递来的酒壶…说"她恨我"`）。那需要"铺垫足不足"
      这种语义判断，可数性就没了。
    ⚠ `speaker` 不传时**按"行内最早出现的那个名字"**推断（中文叙述句的
      主语在前）；调用方知道说话人时应该显式传。
    [EN] Where a third-person pronoun inside a quotation has nothing to land on.
    [EN] Returns `[{pron, quote, at}]`; empty = fine. Countable shape: a quotation uses a
    [EN] third-person pronoun and **no name other than the speaker appears before it in the
    [EN] same line**. Judged per line, not per paragraph, because the line's reader is the
    [EN] novelist who rewrites it -- if the writer cannot resolve it, the reader cannot either.
    [EN] ⚠ Known gap: a name appearing elsewhere in the same line is not flagged.
    """
    t = str(text or '')
    if not t:
        return []
    known = [str(x).strip() for x in (names or ()) if str(x).strip()]
    sp = str(speaker or '').strip()
    if not sp and known:
        # 行内**位置最靠前**的那个名字当说话人（中文叙述主语在前）。
        # [EN] The **earliest** name in the line is the speaker (Chinese puts the subject first).
        best: tuple[int, str] | None = None
        for n in known:
            p = t.find(n)
            if p >= 0 and (best is None or p < best[0]):
                best = (p, n)
        if best is not None:
            sp = best[1]
    out: list[dict] = []
    for a, _b, inner in _quoted_spans(t):
        prons = _third_persons(inner)
        if not prons:
            continue
        head = t[:a]
        seen = [n for n in known if n and n in head and n != sp]
        # 听话人算一个"落点"：对着某人说话时，代词可能就是指他
        # （`驹子（向岛村）：她来了吗` 里的"她"当然不是岛村，但这行里
        #   岛村已经作为人名出现过，上面那行已经把它算进 `seen` 了）
        # [EN] The addressee counts as a landing spot -- though in practice the addressee's
        # [EN] name already appears in the head, so it is already in `seen` above.
        tgt = str(to or '').strip()
        if tgt and tgt in t:
            seen.append(tgt)
        if seen:
            continue
        out.append({'pron': prons[0][1], 'quote': inner.strip(), 'at': a})
    return out


def dangling_reference_note(text: str, *, names=()) -> str:
    """把 `dangling_reference` 压成一句给日志/提示词用的话。没问题返回空串。"""
    bad = dangling_reference(text, names=names)
    if not bad:
        return ''
    return '；'.join(f'「{b["pron"]}」（"{b["quote"]}"）' for b in bad)


# ══════════════════════════════════════════════════════════════
#  进出场断链（2026-10-19 第十二轮，用户报的第四条）
# [EN] Presence-chain breaks (round twelve; the user's fourth complaint)
# ══════════════════════════════════════════════════════════════
#: 材料行的**出场 / 退场标记**（`script_render.one_line` 的形状，见那边）。
# [EN] The **entrance / exit marks** on a material line (`script_render.one_line`).
_EXIT_MARK = re.compile(r'^〔退场〕([^（〕\s]+)')
_ENTER_MARK = re.compile(r'^〔出场〕([^（〕\s]+)')
#: 一幕的开头（`sim/loop._day_lines` 的幕头）—— 换幕就是换局面，
#: 上一幕的在场状态**不许带过来**（同一角色在另一幕重新进场很正常）。
# [EN] An act header (`sim/loop._day_lines`) -- changing acts changes the situation,
# [EN] so the previous act's presence state must **not** carry over.
_SCENE_HEAD = re.compile(r'^〔第\s*\d+\s*幕')
#: 一眼能看出"这事发生在别处"的后缀（`script_render._vis_suffix`）。
#: 它正是"这个不在场的人"的合法形状 —— 不能判成断链。
# [EN] The suffix that marks "this happens elsewhere" — the legitimate shape for
# [EN] someone not present, so it must not be flagged.
_VIS_ELSEWHERE = '（别处）'


def material_speaker(line: str, names=()) -> str:
    """这一行**材料**的说话人（`{speaker}：…` / `{speaker}（…）对Y：…`）。

    ★ 只认 `script_render.one_line` 的形状，别的行（`〔心声·X〕…` / `〔环境〕…` /
      `〔事件·…〕…` / 旁白）一律返回空串 —— 那些行**没有说话人前缀**，
      硬猜主语就是造一个判据（实测：按"行内最早出现的名字"推事件主语，
      十次里九次推到旁边那个人头上）。

    ⚠ `〔心声·X〕` **故意不算**：人走了也能在心里说话。心声不是在场证据。
    ⚠ 带 `（别处）` 的行不算：那是"这事在别处发生"的合法形状。
    [EN] The speaker of a **material** line. ⚠ `〔心声·X〕` deliberately does not
    [EN] count: a person who left can still think. An aside is not evidence of presence.
    """
    t = str(line or '')
    if not t or t.startswith('〔') or _VIS_ELSEWHERE in t:
        return ''
    best = ''
    for n in (names or ()):
        n = str(n).strip()
        if n and t.startswith(n) and len(n) > len(best):
            best = n
    if not best:
        return ''
    rest = t[len(best):]
    # 冒号必须在很近的位置（说话人后面只允许跟括注 / "对某人"），
    # 否则是"叶子将纸门推开…"这种**叙述句刚好以名字开头**，不是"谁：…"行。
    # [EN] The colon must come very close after the name; otherwise it is a narration
    # [EN] sentence that merely starts with a name.
    i = rest.find('：')
    if i < 0 or i > 24 or '。' in rest[:i]:
        return ''
    return best


def presence_chain_breaks(lines, *, names=()) -> list[dict]:
    """**标了退场的人又动了，中间没有标进场**的那些材料行。
    返回 `[{who, at, line}]`；空列表 = 没问题。

    可数形状：
      `〔退场〕X（…）` 之后，X 又作为**说话人**出现在一行 `X：…` 里，
      而两者之间既没有 `〔出场〕X`，也没有换幕。

    ★★★ 为什么这道判据只能挂在这两个**结构化标记**上（2026-10-19 第十二轮）
    -----------------------------------------------------------------------
    动手之前先量过，另外两条路都被实测堵死：

      ① **挂在词表上不可行**。拿 19 个真跑项目 / 47 份白天材料试按
         "退下 / 回去 / 离开 / 出门…" 判：**11 命中里 10 条是误报** ——
         「离开膝上的白羽折扇」「半起又压回去」「把后半句咽回去」
         「又收回去」「天亮前不要出门（台词）」。自由文本里的"走"，
         十个里九个不是离场。词表一放宽就滥、一收严就漏，没有可用的档位。

      ② **挂在世界状态上也不可行**。`scene_builder._sync_cast` 的退场那一支
         在生产里**一次都没响过**：19 个项目 / 47 天里 `exit` 词条 **0 条**、
         `enter` 词条 77 条。原因是 `world._loc_matches` **有意从宽**
         （"他只是挪到门外/柜台后"算在场），而人物 `status` 永远是「在场」。

    ⇒ 唯一可靠的来源是标记本身。而标记以前**根本不存在** ——
      "叶子低头退下"只活在一句事件描述里，落在长句中间、
      和后面的动作隔了四行。所以修法分两半（缺一不可）：
        · **先把标记造出来**：`scene_builder.observe_event` 按导演事件的
          结构化 `离场人物` / `进场人物` 两栏，往材料里补 `〔退场〕X` /
          `〔出场〕X`（有据才补，没据不猜）；
        · **再让判据盯着它**：就是本函数。
    [EN] Material lines where a character marked **exited** acts again with no
    [EN] **entrance** mark in between. ★★ Two cheaper routes were measured dead:
    [EN] ① word lists on free text (11 hits, **10 false**), ② the world's own
    [EN] state (`_sync_cast`'s exit branch **never fires**: 0 `exit` entries in
    [EN] 47 days vs 77 `enter`). So the only reliable source is the mark itself --
    [EN] and the mark did not exist. Hence the fix is two halves: make the mark
    [EN] (`scene_builder.observe_event`, structured) then watch it (this function).
    """
    out: list[dict] = []
    if not names:
        # 没有在场名单 ⇒ 连"这是不是一个名字"都判不了。**不判**（也不猜）。
        # [EN] No cast list => cannot even tell whether something is a name.
        return out
    gone: set[str] = set()
    for idx, raw in enumerate(lines or ()):
        ln = str(raw or '')
        if not ln.strip():
            continue
        if _SCENE_HEAD.match(ln):
            gone.clear()
            continue
        m = _EXIT_MARK.match(ln)
        if m:
            who = m.group(1)
            if who in names:
                gone.add(who)
            continue
        m = _ENTER_MARK.match(ln)
        if m:
            gone.discard(m.group(1))
            continue
        if not gone:
            continue
        who = material_speaker(ln, names)
        if who and who in gone:
            out.append({'who': who, 'at': idx, 'line': ln})
    return out


def presence_break_note(lines, *, names=()) -> str:
    """把 `presence_chain_breaks` 压成一句给作家看的指令。没问题返回空串。"""
    bad = presence_chain_breaks(lines, names=names)
    if not bad:
        return ''
    who = '、'.join(sorted({b['who'] for b in bad}))
    return (f'材料里 {who} 标了退场，之后又动了/说了话，中间没有进场标记 —— '
            f'整理时要么补一次"他回来"，要么把两次并成**一次完整动作**'
            f'（拿走 → 送回），别让他人在门外却伸手进屋。')


# ══════════════════════════════════════════════════════════════════════
#  元叙述：叙述者跳出来讲结构（2026-10-20 第十三轮）
# [EN] Meta-narration: the narrator stepping out to comment on its own structure.
# ══════════════════════════════════════════════════════════════════════
#: ★★★ 病根不在模型"不会写"，在我们的**修复提示词给了太多结构**：
#:   `spin_rewrite_prompt` 里写过"同一件事最多来回三轮""后面再需要它就换个由头"，
#:   模型照着做，做出来的却是**把这条要求念给读者听** ——
#:   「算是第二层的新问」「把这第三轮收住」「这回不重复进门送物」「这回只换了个由头」。
#:   这是本轮之前**没有**的新病：snow_v12 / v15 / v16 四类信号**全为 0**，
#:   v17 一上打转判官就冒出来（序数 4 条、对比 2 条）。
#:   ⇒ 提示词里的"做法"会被当成正文的结构抄出来 —— 与第九轮那条教训
#:   （"提示词里的例子会被当素材抄"）是同一件事的两种形态。
#:   ⇒ 所以这里有**两层**：提示词改写抽象措辞（治本，但 prompt 写了 ≠ 生效），
#:     加上这里一个**确定性剥离器**（治标， executor guaranteed —— 删掉它谁也拦不住）。
#: [EN] Root cause is our own repair prompt: it told the model to "cap at three rounds"
#: [EN] and "vary the pretext next time", and the model narrated those constraints back
#: [EN] to the reader. Two layers then: abstract wording (root) plus a deterministic
#: [EN] stripper here (guaranteed), because a prompt alone is not enforcement.

#: ① 序数 + 言语行为：「第二轮追问」「第三层的新问」「把这第三轮收住」。
#: ⚠ **光有序数不行** —— 真人 18 章里「抄第二遍」「第七遍的时候」「第一遍：…」
#:   有 7 条（"第一遍/第二遍"是叙事里的**事实**），而加了言语行为的组合是 **0 条**。
#:   这就是为什么判据必须带上下文词，不能只匹配「第N轮」。
_ORD_CN = '一二三四五六七八九十两'
_META_ORDER_RE = re.compile('第[' + _ORD_CN + ']+(?:轮|层|遍|遭|回合|番)')
_META_ORDER_CTX_RE = re.compile('(追问|提问|反问|问答|应答|回应|回应着|辩白|辩解|'
                                '解释|收住|逼出|逼问|追逼|新问|询问|话头|话茬|'
                                '盘问|打听)')

#: ② 与前文写法对比：「这回不再…」「换个由头」「改了说法」。
#: ⚠ 「不再」单独不成立：真人 18 章里「她没听懂，也没再问」「老板没再问」
#:   是**叙事事实**，出现了 5 条；只有配上「这回/这次……」或者落在
#:   「由头/说法/理由」这类**写作材料**上才是元叙述 —— 那样是 **0 条**。
_META_THIS_RE = re.compile('(这回|这次|这一回|此番|这一遭|这番)')
_META_NEG_RE = re.compile('(不再|不重复|没再|不再提|不再来|不再做|不作重复)')
#: ⚠ `[了个]{0,2}` 而不是 `[了个]?`：**「换了个由头」中间是"了""个"两个字**，
#:   写成至多一个的话这一条会永远不命中（v17 实测 0 命中，查了半天root cause）。
_META_SWAP_RE = re.compile('(?:换|改|另换)[了个]{0,2}(?:由头|说法|理由|题目|提法|'
                           '花样|借口)')

#: 删完元叙述从句后，剩下的叙述少于这么多个汉字 ⇒ 整句也没得留了，连句删掉。
#: [EN] If less than this many narration characters survive, drop the whole sentence.
META_KEEP_MIN = 10

_META_CLAUSE_SPLIT = re.compile(r'([，、；：])')

#: ⚠ **连"不许写"这句本身也不许举那些词的例子** —— 本项目的老教训是
#:   "提示词里的例子会被当素材抄"（第九轮），所以禁律里也只描述形状。
#: [EN] Every rewrite prompt carries this clause, and it deliberately contains **no
#: [EN] examples** of the offending words: they would get copied into the prose.
_NO_META_CLAUSE = (
    '⚠ **不许把上面的要求写进正文**：不要出现**讲第几次、讲第几层、'
    '讲自己是怎么换个说法的**这类话 —— 叙述者只写戏，不写自己怎么安排这场戏。')
_META_MARK_CN = {'order': '序数元叙述（「第二轮追问」这类）',
                 'contrast': '元叙述对比（「这回不再…」「换个由头」这类）'}


def _narration_view(s: str) -> str:
    """把**这一句里**的成对引语换成等长空位 ⇒ 只看叙述的那层。

    ⚠ 为什么不能只在整篇上一次做完：真正的坑在**切句**，见 `_narration_spans`。
    [EN] Blank out paired quotations **within one sentence**, leaving lengths intact.
    [EN] The real trap is sentence splitting; see `_narration_spans`.
    """
    t = str(s or '')
    for a, b, _inner in reversed(_quoted_spans(t)):
        t = t[:a] + '\u3000' * (b - a + 1) + t[b + 1:]
    return t


def _narration_spans(text: str) -> list[tuple[int, int]]:
    """正文里的"叙述句" `[(起, 止)]` —— **切句时不许切在台词中间**。

    ★★★ 为什么不能直接拿 `_SENT.finditer(原文)` 切（实测，v17 就是被它带偏的）：
      台词内部自带句末标点 —— `驹子问…："我是个好人吧？"` 里的那个 `？`
      也会被当成句末。于是整句被从台词中间劈开，后半句带着"半个引号"开始：
        (a) 句号资格的台词 ⇒ 前后两半各自**奇数个引号** ⇒ 配对整体错位；
        (b) 「驹子便问，逼出第三层」被错当成**台词**mask 住 ⇒ 检测器看不见它。
      修法：**先在整篇上把引号内的内容换成等长空位**，再在蒙好的版本上找句末
      —— 位置一一对应（`_strip_quotes` 是等长替换），切出来的句边界绝不会落在台词里。
    [EN] Sentence spans that never fall inside dialogue. Naive splitting breaks on
    [EN] sentence-end punctuation *inside* quotes, which both desynchronises quote
    [EN] pairing and masks real narration as speech. Mask first, then split.
    """
    raw = str(text or '')
    if not raw:
        return []
    return [(m.start(), m.end()) for m in _SENT.finditer(_strip_quotes(raw))]


def _has_quote_char(s: str) -> bool:
    """这一句/这个从句里有没有引号 —— 有就**不许删**（那是人物说的话）。

    ⚠ 用"有没有引号字符"而不是"有没有成对的引语"：孤零零一个引号就是
       **判不了**，那就保守地当成台词，宁可不删。
    [EN] Any quote character means hands off. Chars, not pairs: a lone quote mark is
    [EN] undiagnosable, so play it safe.
    """
    return any(c in _QUOTE_CHARS for c in str(s or ''))


def meta_markers(sent: str) -> list[str]:
    """这一句命中了哪些元叙述标记。返回 `['order']` / `['contrast']` / 两者 / `[]`。

    ⚠ **只看叙述**：台词里角色自己说「这回不重复了」是人物在说话，不是作家在讲结构。
    [EN] Which meta markers a sentence hits. Narration only: a character saying
    [EN] 「这回不重复了」 is speech, not the author narrating structure.
    """
    s = str(sent or '')
    out: list[str] = []
    if _META_ORDER_RE.search(s) and _META_ORDER_CTX_RE.search(s):
        out.append('order')
    if _META_SWAP_RE.search(s) or (
            _META_THIS_RE.search(s) and _META_NEG_RE.search(s)):
        out.append('contrast')
    return out


def meta_narration_issues(text: str) -> list[dict]:
    """这一章里**叙述者跳出来讲结构**的句子。空列表 = 没问题。

    返回 `[{kind, what, sent}]`，`kind` ∈ `order` / `contrast`。
    [EN] Sentences where the narrator narrates the structure. Empty list = fine.
    """
    out: list[dict] = []
    raw = str(text or '')
    if not raw:
        return out
    for a, b in _narration_spans(raw):
        for k in meta_markers(_narration_view(raw[a:b])):
            out.append({'kind': k, 'what': _META_MARK_CN[k],
                        'sent': raw[a:b].strip()})
    return out


def _narration_runs(s: str) -> list[tuple[int, int]]:
    """句内的**叙述段** `[(起, 止)]` —— 引号那段跳过，其余按连续算一段。

    ⚠ `_narration_view` 是**等长**替换（U+3000），所以这里的下标能直接用回原文。
    [EN] Runs of narration inside a sentence (quotations skipped). The view is
    [EN] length-preserving, so these offsets point straight back into the raw text.
    """
    nv = _narration_view(s)
    out: list[tuple[int, int]] = []
    i, n = 0, len(nv)
    while i < n:
        if nv[i] == '\u3000':
            i += 1
            continue
        j = i
        while j < n and nv[j] != '\u3000':
            j += 1
        out.append((i, j))
        i = j
    return out


def _clean_meta_punct(s: str) -> str:
    """删从句之后留下的孤立标点收拾干净（`，，` / 句首的 `，` / `，：`）。

    ⚠ **必须跑，且必须成对检查**：删掉中间一个从句后，前后两个逗号会撞在一起
      （叶子对岛村，，只站在门边），看着比元叙述本身还刺眼。
    [EN] Clean up orphaned punctuation left by clause deletion; without it the cure
    [EN] looks worse than the disease.
    """
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'[，、；]{2,}', '，', s)
        s = re.sub(r'^[，、；]+', '', s)
        s = re.sub(r'，(?=[：。！？…])', '', s)
    return s


def strip_meta_narration(text: str) -> tuple[str, int]:
    """把带元叙述标记的**整个从句**删掉。返回 `(新正文, 删掉几处)`。

    ★ 为什么是"删"而不是"让模型重写"（与上一轮 `_fix_crowded` 只准拆句是同一条纪律）：
      元叙述是**加法**写出来的毛病 —— 叙述者是多余地多讲了一句；
      重写整章会让好不容易维稳的事实又一次暴露在模型手里（ R42 的教训：
      merge 排在 split 之后就把刚拆好的段并回去了）。删是不会写坏的：
      它只会把读者本来就不该看到的那半句拿掉。

    ⚠ 三条护栏，缺一条就会删坏：
      · **引号里的字一个都不动**（那是人物说的话，不是叙述者的话）；
      · **带台词的句子永不断句删整句**（删了就把台词连锅端了）；
      · 删完剩下的叙述不足 `META_KEEP_MIN` 个汉字且句内没有台词 ⇒ 整句删掉
        （否则会留下「叶子声：」这种光秃秃的报幕）。
    [EN] Delete the offending clause. Why delete rather than rewrite: meta-narration is
    [EN] an *addition*, and rewriting would re-expose settled facts to the model. Three
    [EN] guardrails: never touch quoted speech, never drop a sentence that carries a
    [EN] line of dialogue, and drop whole sentences that are left all but empty.
    """
    raw = str(text or '')
    if not raw:
        return raw, 0
    pieces: list[str] = []
    cursor = 0
    hits = 0
    for a, b in _narration_spans(raw):
        pieces.append(raw[cursor:a])
        sent = raw[a:b]
        if not meta_markers(_narration_view(sent)):
            pieces.append(sent)
            cursor = b
            continue
        has_quote = _has_quote_char(sent)
        parts = _META_CLAUSE_SPLIT.split(sent)      # 文本、标点交替
        keep = [p for p in parts
                if not (p and not _has_quote_char(p)
                        and meta_markers(_narration_view(p)))]
        new = _clean_meta_punct(''.join(keep).strip())
        # ★ 第二层：标点切不开的时候（元叙述贴在台词后面 share 同一个从句），
        #   改按"叙述段"删 —— 引号里面的字照样一个不动。
        # [EN] Second pass: when the marker shares a clause with dialogue, delete the
        # [EN] narration *runs* around it instead. Still never touches quoted text.
        if new and meta_markers(_narration_view(new)):
            # ⚠ 内层循环**不许再叫 `a`/`b`** —— 那会把这一句的句边界踩掉，
            #   后面的 `cursor = b` 就退回到句中，于是同一段正文被吐出来两遍
            #   （2026-10-20 实测：输出里出现了「…收走了。"东西我先收走了。"」）。
            # [EN] Do not reuse `a`/`b` here: shadowing corrupts the sentence span and
            # [EN] makes `cursor = b` rewind, emitting the same passage twice.
            runs = [(ra, rb) for ra, rb in _narration_runs(new)
                    if meta_markers(_narration_view(new[ra:rb]))]
            if runs:
                pieces2: list[str] = []
                cur = 0
                for ra, rb in runs:
                    pieces2.append(new[cur:ra])
                    cur = rb
                pieces2.append(new[cur:])
                new = _clean_meta_punct(''.join(pieces2).strip())
        if not has_quote and zh_len(_narration_view(new)) < META_KEEP_MIN:
            new = ''
        if new == sent:
            pieces.append(sent)
            cursor = b
            continue
        hits += 1
        pieces.append(new)
        cursor = b
    pieces.append(raw[cursor:])
    return ''.join(pieces), hits


# ══════════════════════════════════════════════════════════════════════
#  感知/物理自洽："听不见的话被听清了"（2026-10-20 第十三轮）
# [EN] Plausibility: an inaudible line that someone hears outright.
# ══════════════════════════════════════════════════════════════════════
#: ★★★ 这一条来自用户真刀真枪的读稿反馈：驹子那句「唇几乎没动、像叹息般溜出来」
#:   的私语，叶子"正进门便听见了" —— 隔着一道纸门的门外人，听见了唇几乎没动的话。
#:   这是**动作/因果层面的硬伤**，不是文风：**删掉的是悬念，留着的是漏洞**。
#:   ⚠ 可数的只有"这一处"的形态。物理瑕疵（「釉面流过一道亮痕」—— 干的釉面
#:     不会自己流动）和微距细节（隔着门看清睫毛）判不了字面，交给判官（见下）。
#: [EN] Reported from a real read-through: a line written as barely audible is heard
#: [EN] outright by someone at the door. Hard, countable shape below; purely physical
#: [EN] glazes go to the judge.

#: 被写成"几乎听不见"的那些说法。⚠ 不含「低声道」「轻声道」——
#:   那是音量小但**听得见**，真人常用（第 4 部第 1 章「他低声说了一遍」）。
# [EN] Phrasings that mean *inaudible*. 「低声道」 is deliberately absent: soft but
# [EN] audible, and used by human writers.
_LOWVOL_RE = re.compile('(私语|低语|耳语|悄声|细得几乎|低得几乎|唇几乎没动|'
                        '唇几乎未动|唇没动|唇未动|唇不动|只见嘴形|'
                        '像叹息|似叹息|气音|几乎听不见|几乎听不到|'
                        '喃喃|嘟喃|嘟囔|嘀咕|含混不清|含混)')

#: "听见"的肯定说法。**否定必须比肯定先查**（前面第 3 个字里有否定词就不算）：
#:   真人第 6 部第 3 章「说了三个字，又断在一个收不住的气音上。那三个字他**没听清**」——
#:   那正是作家处理"听不清"的**正确写法**，把它当成病就冤枉了
#:   （和 `parse_spin_verdict` 里「没打转」含"打转"是同一个坑）。
# [EN] Affirmative hearing. Negation first: "he did **not** catch it" is how a human
# [EN] writes it correctly, and flagging that would punish the right answer.
_HEARD_RE = re.compile('(听见|听到|听得|听清|听出|听了个|辨得出|'
                       '传入耳|钻进耳|飘进耳|灌进耳|入了耳|一字不漏|全听去)')
_HEARD_NEG = ('没', '不', '未', '别', '无', '非')

#: 隔着多远还看得见的"微距" —— 睫毛、瞳仁、 Flutter 上的汗。
# [EN] Micro-detail that needs you to be right there.
_MICRO_RE = re.compile('(睫毛|睫影|睫尖|瞳仁|瞳孔|眼白|眼角内侧|唇纹|'
                       '鼻尖上的汗|耳垂上的|后颈上的汗毛|寒毛|汗毛|毛孔)')
#: 同一句里出现这些 ⇒ 读者被告知"看不清/离得远"。
# [EN] Same sentence says you are far away or the light is bad.
_FAR_RE = re.compile('(半张脸|探进|门外|门边|门口|廊下|隔着|纸门|纸影|影子里|'
                     '昏暗|灯影|暗处|背光|逆光|看不清|看不分|瞧不真|'
                     '夜色里|雪光里)')

#: 低语与"听见"之间最多隔几句还算同一件事。再远就是另一回事了。
# [EN] How far apart the whisper and the hearing may sit and still be one event.
PERCEPT_WINDOW = 6

_PERCEPT_CN = {'whisper': '写成了几乎听不见的话，却在隔了几句后被"听见/听清"',
               'micro': '被告知隔着距离/光线很暗，却写到了睫毛、瞳仁这一层的微距'}


def percept_issues(text: str) -> list[dict]:
    """这一章里**读者的感官被前后打脸**的地方。空列表 = 没问题。

    返回 `[{kind, what, sent, pair}]`，`kind` ∈ `whisper` / `micro`。
    ⚠ 只看**叙述**：引号里的「我听见了」是人物自述，管不着。
    [EN] Places where the prose contradicts the reader's senses. Narration only.
    """
    raw = str(text or '')
    if not raw:
        return []
    spans = _narration_spans(raw)
    if not spans:
        return []
    views = [_narration_view(raw[a:b]) for a, b in spans]
    out: list[dict] = []
    # ① 私语 × 听见：把连续几句低语合成"一簇"，簇后 PERCEPT_WINDOW 句内找肯定听见。
    # [EN] Cluster consecutive whisper sentences, then look for affirmative hearing.
    low_idx = [i for i, (a, b) in enumerate(spans)
               if _LOWVOL_RE.search(views[i])]
    for i in low_idx:
        if i and i - 1 in low_idx:
            continue                              # 已经是上一簇里的一员
        for j in range(i + 1, min(len(spans), i + 1 + PERCEPT_WINDOW)):
            a, b = spans[j]
            hit = _HEARD_RE.search(views[j])
            if not hit:
                continue
            if any(c in views[j][max(0, hit.start() - 3):hit.start()]
                   for c in _HEARD_NEG):
                continue                          # 「没听清」⇒ 没问题
            out.append({'kind': 'whisper', 'what': _PERCEPT_CN['whisper'],
                        'sent': raw[spans[i][0]:spans[i][1]].strip(),
                        'pair': raw[a:b].strip()})
            break
    # ② 微距 × 距离/弱光：必须落在**同一句**里。
    # [EN] Micro-detail must sit in the same sentence as the distance cue.
    for k, (a, b) in enumerate(spans):
        if _MICRO_RE.search(views[k]) and _FAR_RE.search(views[k]):
            out.append({'kind': 'micro', 'what': _PERCEPT_CN['micro'],
                        'sent': raw[a:b].strip(), 'pair': ''})
    return out


def percept_note(text: str) -> str:
    """把 `percept_issues` 压成一句话给作家看。没问题返回空串。"""
    bad = percept_issues(str(text or ''))
    if not bad:
        return ''
    marks = sorted({b['kind'] for b in bad})
    return ('这一章有 {} 处让读者在感官上被前后打脸的地方（{}）：'
            '写成了几乎听不见的话，就不能再让隔着一扇门的人听见；'
            '写了"半张脸""廊下""昏暗"，就别再写到睫毛、瞳仁那一层。'
            '改的办法只有两种 —— **把话说出声**，或者**让人没听清**。'
            .format(len(bad),
                    '、'.join(_PERCEPT_CN.get(m, m) for m in marks)))


#: 判官最少要看多少句台词才值得问（与 `SPIN_MIN_LINES` 同一条规矩）。
# [EN] Below this many lines there is nothing to judge.
PLAUS_MIN_LINES = 2


def plausibility_judge_prompt(text: str) -> str:
    """请判官判"这一章有没有读起来不成立的地方"时说的话。

    ★ 与 `spin_judge_prompt` 同一条写法：**把"不算"的也写进去**。
      不写的话，判官会把"冬天手会红""雪会化"当成物理不成立。
    [EN] Same shape as the spin prompt: the negative examples are as important as the
    [EN] positive ones, or the judge starts reporting ordinary physical facts.
    """
    return (
        '你是中文小说的终审编辑。下面这一章，只请你判一件事：'
        '它有没有"**读起来不成立**"的地方。三种样子，中一种就算：' + chr(10) + chr(10)
        + '1. **听不见的话被听清了**：正文把一句话写成几乎听不见'
           '（唇几乎没动、像叹息、私语、闷在喉咙里），'
           '后面却让一个人**清清楚楚听见了**，'
           '而这个人在物理上听不到（在门外、刚进门、隔着一道门/一个院子）。' + chr(10)
        + '2. **看不见的细节被看清了**：正文写了"半张脸""门外""昏暗""隔着纸门"'
           '这类距离或光线，却同时写到了**睫毛上的东西、瞳仁里的光、'
           '皮肤底下的青筋**这一层才看得见的细节。' + chr(10)
        + '3. **物理上做不到**：干燥的釉面自己"流过一道亮痕"、'
           '熄灭的炭"又亮了一瞬"、端平的酒"一滴不洒地泼出来"'
           '—— 动作与物性对不上。' + chr(10) + chr(10)
        + '⚠ 下面这些**不算**，别误报：' + chr(10)
        + '· 合乎常识的物理事实（雪会化、手会冻红、酒会洒、灯会晃）；' + chr(10)
        + '· **比喻与通感**（"她的声音像雪落下来"）—— 那是修辞，不是物理；' + chr(10)
        + '· 人物自己的夸张、错觉、酒后的糊涂 —— 那是人物状态，不是作者的错；' + chr(10)
        + '· 视角上的**合理贴近**（这个人本来就在眼前看得清）—— 那是正常描写。' + chr(10)
        + chr(10)
        + '只输出下面这个格式，不要解释、不要别的字：' + chr(10) + chr(10)
        + '判定：有问题' + chr(10)
        + '不成立的地方：<原样抄出那一句>' + chr(10) + chr(10)
        + '（如果都成立，就只写一行「判定：没问题」。）' + chr(10) + chr(10)
        + '── 这一章 ──' + chr(10) + str(text or ''))


_PL_VERDICT_RE = re.compile(r'判定\s*[：:]\s*([^\n]{0,24})')
#: ★★★ **否定比"问题"先查**：「没问题」里也有"问题" —— 这是第三次踩同一个坑了
#:   （`parse_spin_verdict` 的「没打转」、`percept_issues` 的「没听清」）。
# [EN] Negation before the keyword: 没问题 contains 问题. Third time this shape has
# [EN] bitten us; keep it in one place per instance, always first.
_PL_NEG_RE = re.compile('(没|不|无|非|未|都成立|没问题)')


def parse_plausibility_verdict(raw: str) -> dict:
    """解析判官回话 ⇒ `{'bad', 'lines', 'reason'}`。

    ★★★ **看不懂一律当"没问题"** —— 这一步回的是"要不要改稿"，
      宁可漏改，也不许因为解析错把一篇好稿改坏（与 `parse_spin_verdict` 同一安全侧）。
    [EN] Anything unreadable counts as "fine": this decides whether to rewrite, and a
    [EN] wrong *yes* damages good prose.
    """
    s = str(raw or '')
    m = _PL_VERDICT_RE.search(s)
    if not m:
        return {'bad': False, 'lines': [], 'reason': '没有判定行'}
    verdict = m.group(1).strip()
    if '问题' not in verdict:
        return {'bad': False, 'lines': [], 'reason': '判定行里没有"问题"'}
    if _PL_NEG_RE.search(verdict):
        return {'bad': False, 'lines': [], 'reason': '判官说没问题'}
    lines: list[str] = []
    for ln in s.splitlines():
        if '不成立的地方' in ln or '那一句' in ln:
            c = ln.split('：', 1)[-1].split(':', 1)[-1].strip()
            c = c.lstrip('-·*')
            if len(c) >= 4:
                lines.append(c)
    if not lines:
        return {'bad': False, 'lines': [], 'reason': '判官没抄出原句'}
    return {'bad': True, 'lines': lines, 'reason': ''}


def plausibility_rewrite_prompt(text: str, verdict: dict) -> str:
    """判官说"有读起来不成立的地方" ⇒ 请模型**只改那几句**时说的话。

    ★★★ 与 `spin_rewrite_prompt` 最大的不同：那边是整章重写，这里是**定点改句**。
      理由是成本与风险对称 —— 整章重写等于把已修好的其它毛病再一次暴露给模型，
      而这一类的毛病通常只有一两句话的事。**只输出替换后的那几句**，不要重写全章。
    [EN] Unlike the spin repair this one is **targeted**: only the flagged sentences
    [EN] are rewritten, because a full pass would re-expose already-healed defects.
    """
    lines = verdict.get('lines') or []
    quoted = chr(10).join('- {}'.format(x) for x in lines[:8])
    return (
        '下面这一章里有**读起来不成立**的句子，判官抄出来的原句是：' + chr(10)
        + quoted + chr(10) + chr(10)
        + '请**只改这几句**，其余句子一个字都不许动 —— 要求：' + chr(10)
        + '1. 每一句给出**改法只有两种**，二选一：' + chr(10)
        + '   · **让它成立**（把话说出声、让人别听见/没听清、把距离写近、'
           '把细节改成远看得见的那一种）；' + chr(10)
        + '   · 或者**删掉那半句**（写了矛盾的那部分），保留戏还在的那部分；' + chr(10)
        + '2. **事实一个字都不许改**：谁说了什么、做了什么、先后顺序，全部照旧；' + chr(10)
        + '3. **不许替叙述者做总结** —— 不要出现'
           '「第二轮追问」「第三层」「换个由头」「这回不再」这类讲结构的话；' + chr(10)
        + '4. 台词引号内的**原句照留**；' + chr(10)
        + '5. 每句改完的字数不少于原句；' + chr(10)
        + '6. 只输出**替换后的那几句**（原句 → 新句，一行一对），'
           '不要输出全章、不要标题、不要解释：' + chr(10)
        + '   原句：<照抄上面的原句>' + chr(10)
        + '   新句：<改好的那一句>' + chr(10) + chr(10)
        + '── 原文（只供对照，别整章输出）──' + chr(10) + str(text or ''))


def swap_lines(text: str, pairs: list[tuple[str, str]]) -> str:
    """把 `<原句>` 换成 `<新句>`。换不动的那些（对不上、原文里没有）**一律不换**。

    ⚠ 返回值一定是"要么换成了、要么原样"，不会有一半替换一半没换的中间态引发
      悬空引用：这里只在**整句完全对得上**时才动手。
    [EN] Swap sentences, and only on an exact full-sentence match; anything that fails
    [EN] to line up is left untouched rather than half-applied.
    """
    out = str(text or '')
    for old, new in pairs:
        if not old or not new or old not in out:
            continue
        out = out.replace(old, new, 1)
    return out


# ══════════════════════════════════════════════════════════════
#  R47 道具循环（"手在打转"）—— 2026-10-20
# ══════════════════════════════════════════════════════════════
#
# ★★★ 用户原话：「继续修复道具循环」。
#
# 病的形状（snow_v20）：茶凉 → 我让人再送一壶 → 茶凉了就说一声 → 叫壶热的来
#   → 酒还温着再喝一杯 → 杯子空了半天 → 酒壶往火边挪。
#   **台词每句都不同，手上的事一遍没变** —— 东西凉了、续上、又凉了、再续上。
#
# ★★★ 这与 R43（打转）是两件事，判官的分工也正好对上：
#   R43 数的是"**话**"（同一诉求反复问），R44/R45 数的是"叙述者/感知"，
#   这一条数的是"**手**"（同一个东西被反复复位）。
#   所以打转判官会放过 v20 —— 它看到台词有推进（"岛村的反应在变"），
#   这是对的判断；它只是**不管手上的事**。
#
# ★★★ 口径（先在 samples/zh 的 18 章上量过才敢立）：
#   `最大复位` = 同一类东西里，**既被补给（斟/倒/添/续/换/再送）又被消耗
#   （凉了/空了/见了底）的句子数之和**的最大值。
#     真人 18 章：中位 **0**、最大 **0**（一次都没有）
#     真跑：v12=0 v15=0 v18=2 | v16=4 v17=3 v19=5 **v20=5**
#   ⇒ 阈值 **≥3**，真人零误报。
#   ⚠ 这个数**必须贴着东西**算：不限定"句子里有名有姓的器皿或可消耗物"，
#     真人科幻那一章会被判进 11 次"消耗"——全是表格里的「没有」「空着」。
#     量过错了一次，记在这里。
# [EN] R47 prop cycle ("the hands spinning"): the same object gets replenished and
# [EN] drained again and again. Measured on 18 human chapters: max resets per object is
# [EN] **0**; real runs reach 5. Threshold >= 3, zero false positives on human prose.
# [EN] The count must be **anchored to a named object**, otherwise ordinary 「没有」
# [EN] lines in a human chapter register as consumption (measured, 11 false hits).

#: 补给动作：把被消耗掉的东西补回去。**通用词表**。
#: ⚠ 不收"拿/放/递"—— 那些是传递，不是补给（真人小说里到处都是）。
# [EN] Replenish verbs. Deliberately excludes carry/put/pass: transfers, not refills.
_PROP_REFILL_RE = re.compile(
    r'斟|倒(?:上|满|些|了)?(?:酒|茶|水|一杯|半杯)|添(?:上|些|了)?(?:酒|茶|炭|水|灯)?|'
    r'续(?:上|了)?|换(?:一|壶|杯)|再送|送(?:一壶|一坛)|满上|端(?:来|上|进)|'
    r'(?:再|又)(?:喝|倒|添|斟)(?:一)?(?:杯|壶|碗)')
#: 消耗信号。**必须与器皿或可消耗物同句**才算（见 `_prop_classes`）。
_PROP_CONSUME_RE = re.compile(
    r'空(?:了|着|掉)|凉(?:了|透)|(?:没|喝|吃|用)(?:了|光|完|尽)|见底|干了|冷(?:了|透)')
#: 器皿。归一成**类别**：`粗陶酒壶`／`那把壶`／`壶底` 必须算同一件东西。
# [EN] Vessels, normalised to a class so 「粗陶酒壶」「那把壶」「壶底」 merge.
_PROP_VESSEL = ('壶', '杯', '碗', '盏', '盘', '碟', '炉', '钵', '盆', '罐', '瓶',
                '坛', '匣', '箱', '盒', '灯', '琴')
#: 可消耗物：会被喝掉、吃掉、烧掉的东西。通用词，不是某一部作品的道具。
_PROP_STUFF = ('茶', '酒', '水', '饭', '汤', '粥', '炭', '油', '柴', '纸',
               '墨', '烟', '药', '雪')
#: 复位次数阈值。真人 18 章最大 0。
PROP_CYCLE_MIN = 3


def _prop_classes(s: str) -> list[str]:
    """这一句里出现的"东西"类别（器皿 + 可消耗物），去重保序。"""
    out: list[str] = []
    for c in _PROP_VESSEL + _PROP_STUFF:
        if c in s and c not in out:
            out.append(c)
    return out


def _prop_sents(text: str) -> list[str]:
    """按句切 —— **句子边界绝不落在台词中间**。

    ⚠ 第一版直接拿 `_SENT.finditer(原文)` 切，台词里的 `。` 会把一句台词劈成两半：
        `他把茶端来：“喝口热的。` / `”\n她抿了一口：“又凉了。`
      ⇒ 「又凉了」那一半里没有"茶"，类别是空的，**整条检测永远数不到 2**
        （实测：夹具里六句清清楚楚的循环，一段都报不出来）。
    ⚠ 第二版改用 `_narration_spans`（整篇蒙引号再切），但**整篇都是台词时**
      它会把整章并成一个 span（台词内的句末全被蒙掉，段落末尾又常常没有句号）
      ⇒ 又数不出来。所以最终是**按行切，行内再在蒙好引号的版本上切句末**：
      一行通常就是一拍，这也正是"手上的动作"该有的粒度。
    [EN] Sentence bounds must never fall inside dialogue. Splitting raw text on `。`
    [EN] halves a quoted line, so the "凉了" half carries no object class. Masking the
    [EN] whole chapter then merging everything into one span fails too when the text is
    [EN] almost all dialogue -- so split **per line**, then on masked sentence ends.
    """
    raw = str(text or '')
    if not raw:
        return []
    out: list[str] = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        masked = _strip_quotes(ln)          # 等长替换，位置一一对应
        for m in _SENT.finditer(masked):
            s = ln[m.start():m.end()].strip()
            if len(s) >= 4:
                out.append(s)
    return out


def prop_cycle_issues(text: str) -> list[dict]:
    """同一件东西被反复复位的那些句子 ⇒ `[{'cls', 'n', 'lines', 'editable'}]`。

    `lines` 是**涉及的整句**（补给句或消耗句），`editable` 是能改的中间那几句
    —— **第一句不动**（第一次用它），最后一句也不动（收束），与 R43 同一条纪律。
    [EN] Sentences where one object cycles. `editable` excludes the first and last,
    [EN] matching R43's discipline: the opening use and the closing beat both stay.
    """
    ss = _prop_sents(text)
    if not ss:
        return []
    per: dict[str, list[tuple[int, str]]] = {}
    for i, s in enumerate(ss):
        cls = _prop_classes(s)
        if not cls:
            continue
        if not (_PROP_REFILL_RE.search(s) or _PROP_CONSUME_RE.search(s)):
            continue
        for k in cls:
            per.setdefault(k, []).append((i, s))
    out: list[dict] = []
    for k, hits in per.items():
        if len(hits) < PROP_CYCLE_MIN:
            continue
        # 首尾不动：只把中间那些交出去
        mid = [s for _i, s in hits[1:-1]]
        if not mid:
            continue
        out.append({'cls': k, 'n': len(hits),
                    'lines': [s for _i, s in hits],
                    'editable': mid})
    out.sort(key=lambda x: -x['n'])
    return out


def prop_cycle_note(text: str) -> str:
    """把"哪件东西在循环"说给模型听（放进重写提示词）。"""
    iss = prop_cycle_issues(text)
    if not iss:
        return ''
    rows = []
    for x in iss:
        rows.append('· 「%s」被反复补给/耗掉 **%d 次**。涉及这几句：'
                    % (x['cls'], x['n']))
        for s in x['lines'][:6]:
            rows.append('   - ' + str(s)[:70])
    return chr(10).join(rows)


def prop_cycle_rewrite_prompt(text: str, note: str) -> str:
    """请模型把"道具循环"改掉时说的话。

    ★★★ 要求是**换成别的事**，不是删戏：
      这类毛病的特点是"台词各不相同、手上的事一遍没变"。
      删掉那些句子会把戏删空（一场戏只剩两个人干坐着），
      所以只许**把重复的那个动作换成另一件事**（窗外、炭、琴、衣角、沉默……）。
    ★ 只改被点名的那几句（`swap_lines` 整句精确替换），与 R46 同一套骨架。
    [EN] Rewrite the repeated action into something else -- never delete: the lines all
    [EN] differ, only the hands repeat, so deleting would empty the scene.
    """
    return (
        '下面这一章有一处毛病：**同一件东西被反复"续上—耗掉"**。'
        '台词每句都不一样，可手上的事一遍没变 —— 读者会觉得这场戏在原地踏步。'
        '已经替你标出来了：' + chr(10) + chr(10)
        + str(note or '') + chr(10) + chr(10)
        + '请只改**每件东西中间那 1–2 句**（第一句和最后一句必须原样留着：'
        '那是第一次用它和收束），要求：' + chr(10)
        + '1. **不删戏、不减台词**：改的是"手上做什么"，不是"说不说话"；' + chr(10)
        + '2. 把重复的那个动作换成**另一件事**（窗外、炭、琴、衣角、'
           '某个人的沉默或走神……），要顺着上下文，别硬塞；' + chr(10)
        + '3. **不许**再换成"又喝了/又添了/又换了"这类同族动作 —— '
           '换汤不换药等于没改；' + chr(10)
        + '4. 事实不许改：谁在哪儿、谁说了什么、先后顺序；' + chr(10)
        + '5. 每句改完的字数不少于原句；' + chr(10)
        + '6. ' + _NO_META_CLAUSE.replace('⚠ **不许把上面的要求写进正文**：', '')
        + chr(10)
        + '7. 只输出**被改的那几句**（原句 → 新句，一行一对），'
           '不要输出全章、不要标题、不要解释：' + chr(10)
        + '   原句：<照抄原句>' + chr(10)
        + '   新句：<改好的那一句>' + chr(10) + chr(10)
        + '── 原文（只供对照，别整章输出）──' + chr(10) + str(text or ''))


def drop_spin_lines(text: str, drops: list[str], *,
                    max_quote_drops: int = 0,
                    max_drop_chars: int = 80) -> str:
    """把判官逐条判「删」的那些句子**整句删掉**（确定性，不调模型）。

    ★★★ 为什么"删"而不是"重写"（用户 2026-10-20：「不是所有重复都有问题」）：
      判官已经用**语境**逐条判过"删掉会不会损失东西"，代码再去重写就等于
      把那个判断作废一次；而且重写的风险面大得多 —— snow_v19 就是被
      "整章重写 → 复检还报 → 整篇退回原文"卡死的。
      删是唯一**不会写进新东西**的动作（与 R44 元叙述剥离同一条理由）。

    ⚠ **不按标点扩边界**。第一版写的是"向前找到句首、向后找到句末"，
      实测立刻出事：判官抄的整句以 `？”` 结尾，向后扩时把下一句的
      `岛村说：“是啊。` 一起吃了，正文里剩一个孤零零的 `”`。
      根因是"句子边界"在台词面前根本不可靠（台词自带句末标点，
      这正是 R44 踩过的同一个坑，只是方向相反）。
      ⇒ 改成**按引号守恒删**：只删判官抄的那一段（外加紧贴着它的闭引号），
        删掉的字符里 `“` 与 `”` 必须**一样多**，否则说明切断了台词 ⇒ 不删。

    ⚠ **删的量必须封顶，否则就是"一刀切"**。第一版只封了"40% 的句子"，
      实测在 snow_v19 上删掉 8 句台词（34 → 26）、字数掉 19%，
      把「就别拿酒挡我，给句准话」「窗户给您掩上吧」这种**好句子**也削了 ——
      这正是用户警告的那种改法。
      ⇒ 两道新闸：① 单条超过 `max_drop_chars` 字不收（判官抄的是段落，不是句子）；
        ② 删掉的**引语**不超过 `max_quote_drops` 条（默认 3）。
      理由是量过的：真人最长"同题链"是 4 条（`diag_repeat_context.py`），
      一条链里去掉中间那一两条就够把链打断，删更多没有收益、只有损失。

    ⚠ 六道安全带，缺一条都会删坏：
      ① 整句对得上才删（判官抄错一个字 ⇒ 这条不动）；
      ② 删掉的片段里**引号必须配平**（切断台词的一律不删）；
      ③ 不许把一段删空（段落全空比重复更难看）；
      ④ 不许删这一段最后一句（收束常常在段末）；
      ⑤ 单条长度与删掉的引语条数都有上限（见上）;
      ⑥ 一次最多删 40% 的句子（判官要是整章判删，这条兜住）。
    [EN] Delete the whole sentences the judge marked droppable. Do **not** widen to
    [EN] punctuation-based sentence bounds -- measured failure: the quote-internal `？`
    [EN] made the widening swallow the next line's opening. Instead require that the
    [EN] deleted slice has balanced quote marks. Also cap how much may go: a single
    [EN] entry longer than `max_drop_chars` is a paragraph, not a sentence, and at most
    [EN] `max_quote_drops` quoted lines may be removed -- otherwise this becomes the
    [EN] blanket pruning the author explicitly warned against.
    """
    src = str(text or '')
    if not src or not drops:
        return src
    total_sent = sum(1 for _ in _SENT.finditer(src))
    budget = max(1, int(total_sent * 0.4))
    # ⑤ 引语额度：不写死 3 条 —— 写死会把"一对几乎一样的问句"永远剩下一句
    #   （实测 v19：删到 3 条就停，「好人是不是都没好报啊」与
    #     「你倒是说呀，好人是不是都没好报？」两句几乎一字不差地留着）。
    #   改成按台词总数的 15% 算，最低 2 条；上限那一道由"单条 80 字 +
    #   引号必须配平"来兜（判官抄段落的那些进不来）。
    # [EN] The quote budget scales with the dialogue count instead of a fixed 3:
    # [EN] a fixed cap left one of two near-identical questions in place. Quality is
    # [EN] guarded by the 80-char limit and the balanced-quote check instead.
    if max_quote_drops <= 0:
        total_q = src.count('“') + src.count('「') + src.count('『')
        max_quote_drops = max(2, int(total_q * 0.15))
    quote_left = max(0, int(max_quote_drops))
    hits: list[tuple[int, int]] = []
    for d in drops:
        if len(hits) >= budget or quote_left <= 0:
            break
        key = str(d or '').strip()
        if not key:
            continue
        # ⑤ 判官抄的是段落而不是句子 ⇒ 不收（它会连带删掉好句子）
        if len(key) > max_drop_chars:
            continue
        at = src.find(key)
        if at < 0:                            # 判官去掉过引号的情形，再试一次
            key = key.strip('“”"「」『』')
            at = src.find(key) if key else -1
        if at < 0:
            continue
        a, b = at, at + len(key)
        # 吸收紧贴着的闭引号 / 句末标点（属于被删的这一句）
        while b < len(src) and src[b] in '”」』"':
            b += 1
        # ② 引号必须配平 —— 切断台词的一律不删
        seg = src[a:b]
        if seg.count('“') + seg.count('「') + seg.count('『') \
                != seg.count('”') + seg.count('」') + seg.count('』'):
            continue
        # ⑤ 引语条数封顶
        nq = seg.count('“') + seg.count('「') + seg.count('『')
        if nq > quote_left:
            continue
        # ③ 段落删空
        ls = src.rfind(chr(10), 0, a) + 1
        le = src.find(chr(10), b)
        le = len(src) if le < 0 else le
        if len((src[ls:a] + src[b:le]).strip()) < 2:
            continue
        # ④ 不许删这一段最后一句
        if not src[b:le].strip():
            continue
        # 检查：删完不许留下"说话人 + 冒号"这种半截（`他说：` 后面空了）
        if a > 0 and src[a - 1] in '：:':
            continue
        hits.append((a, b))
        quote_left -= nq
    if not hits:
        return src
    hits.sort()
    merged: list[tuple[int, int]] = []
    for a, b in hits:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    out = src
    for a, b in reversed(merged):
        out = out[:a] + out[b:]
    cleaned = [ln.strip() for ln in out.split(chr(10))]
    out = chr(10).join(ln for ln in cleaned if ln)
    return out if out.strip() else src


def parse_line_swaps(raw: str) -> list[tuple[str, str]]:
    """解析"原句 / 新句"两行一对的输出 ⇒ `[(old, new)]`。看不懂的一对就丢掉。

    ⚠ **太短的一律不收**：新句比原句短掉一半，那是模型在偷懒删戏，不是修bug。
    [EN] Parse 原句/新句 pairs; drop unreadable ones, and drop any rewrite that is
    [EN] materially shorter than the original (the model deleting scene, not fixing it).
    """
    pairs: list[tuple[str, str]] = []
    old = None
    for ln in str(raw or '').splitlines():
        ln = ln.strip().lstrip('-·*')
        if not ln:
            continue
        head, sep, body = ln.partition('：')
        if not sep:
            head, sep, body = ln.partition(':')
        if head not in ('原句', '新句'):
            continue
        body = body.strip()
        if not body:
            continue
        if head == '原句':
            old = body
        elif head == '新句' and old:
            if len(body) >= len(old) * 0.6:
                pairs.append((old, body))
            old = None
    return pairs


# ══════════════════════════════════════════════════════════════
#  R46 问答不接（"牛头不对马嘴"）—— 2026-10-20
# ══════════════════════════════════════════════════════════════
# 用户原话：「为何两个主角 说的话又完全牛头不对马嘴了」。
#
# ★★★ 先量了才敢动手（`developers/diag_qa_drift.py`，人 18 章 vs 五版真跑）：
#
#   | 口径           | 人 18 章            | v12/v15/v16/v17 | v18   |
#   |----------------|---------------------|-----------------|-------|
#   | 悬空率（问了没直接答的比例） | 中位 0.8，最高 **1.0** | 0.75/0.89/0.4/0.6 | 0.846 |
#   | 最长**连续**悬空      | **最高 2**          | 2 / 2 / 2 / 1   | **5** |
#
#   ⇒ **"问一句不答"本身不是病**（真人中位 80%、最高 100%，比我们还高）；
#     病的是**连着几句问出去都没人接**。真人的天花板是 2 ⇒ 阈值取 ≥3，
#     在 18 章真人上**零误报**。
#
# ★★★ 这毛病为什么一路漏到终端：`sim/loop.py::_audit_talk` **每拍都算，也会报**
#   （v18 日志里报了 5 次「连着 5 句没人接上一句（各说各话）」），
#   但那一层的注释白纸黑字写着 **只算不拦**。⇒ **看见了不等于处置了**：
#   凡是"只写日志、不上手段"的护栏，等于没有护栏。
# [EN] ★★★ Why it reached the user: `sim/loop.py::_audit_talk` computes this every beat
# [EN] and *did* report it five times during snow_v18, but that layer is explicitly
# [EN] "compute only, never block". Seeing a defect is not handling it.
QA_DRIFT_MIN = 3

_QA_QUOTE_RE = re.compile(r'[“”"]([^“”"\n]{1,120})[”"]')
_QA_ASK_RE = re.compile(r'[？?]|吗|呢|么|什么|怎么|为什么|要不要|能不能|'
                        r'可不可|几时|多久|何时|何处|多少')
#: ★★★ 应答标记只收**句首**："是不回答一个字"说得通，"他这些年不去打听是不答应"
#:   这种句子里半腰冒出的"不"会被当成应答 —— 那会把真人整章都算成"答了"。
# [EN] Answer markers only count **at the head** of the line; a mid-sentence 不 means
# [EN] nothing about answering.
_QA_ANS_RE = re.compile(
    r'^(?:是|不是|对|不对|好|也好|好罢|行|不行|嗯|唉|哦|啊|不了|没|没有|'
    r'别说|算了|罢|自然|当然|也许|大概|谁知道|你说呢|你问这|何必|怎么会|'
    r'不妨|问问|你去|我替|由他|随他|你看|怎)', re.M)
_QA_STOP = {'一个', '什么', '这个', '那个', '怎么', '就是', '不是', '还是', '这样',
            '那样', '知道', '觉得', '时候', '现在', '已经', '自己', '我们', '你们',
            '他们', '先生', '他说', '她说', '一句', '样子', '回去', '可是', '因为'}


def _qa_quotes(text: str) -> list[str]:
    return [m.group(1).strip()
            for m in _QA_QUOTE_RE.finditer(str(text or ''))]


def _qa_grams(s: str) -> set[str]:
    body = re.sub(r'[^\u4e00-\u9fff]', '', str(s or ''))
    return {body[i:i + 2] for i in range(max(0, len(body) - 1))} - _QA_STOP


def _qa_is_ask(s: str) -> bool:
    return bool(_QA_ASK_RE.search(str(s or '')))


def _qa_answered(prev: str, nxt: str) -> bool:
    """后一句算不算"接住了"前一句。★ **宁可漏、不可冤**（仿 `percept_issues`）。

    三条，中一条就算接上：① 句首是应答词；② 把上一句重说了一遍（反问/重复追问）；
    ③ 两句共享实词（2-gram，去掉太泛的那些）。
    [EN] Conservative on purpose: answer marker at head, restating the previous line,
    [EN] or sharing a content bigram. Missing some real drift beats false-alarming.
    """
    a, b = str(prev or '').strip(), str(nxt or '').strip()
    if not a or not b:
        return True
    if _QA_ANS_RE.match(b):
        return True
    if len(a) >= 6 and a in b:
        return True
    return bool(_qa_grams(a) & _qa_grams(b))


def qa_drift_runs(text: str) -> list[list[tuple[str, str]]]:
    """连着几句"问出去没人接" ⇒ 每段一条 `[(问句, 没接住的那句), ...]`。

    ⚠ 只认**相邻**台词（按引号出现的顺序），中间只要有一句接住了，段就断在这里。
      这正是把关的关键：**稀释过就不算病**（真人 80% 的单次悬空是无意的留白）。
    [EN] Consecutive unanswered questions only; one real answer resets the run.
    """
    qs = _qa_quotes(text)
    hangs: list[int] = []
    pairs: list[tuple[str, str]] = []
    for i in range(len(qs) - 1):
        if not _qa_is_ask(qs[i]) or _qa_answered(qs[i], qs[i + 1]):
            continue
        hangs.append(i)
        pairs.append((qs[i], qs[i + 1]))
    out: list[list[tuple[str, str]]] = []
    cur: list[tuple[str, str]] = []
    prev: int | None = None
    for k, idx in enumerate(hangs):
        if cur and prev is not None and idx != prev + 1:
            if len(cur) >= QA_DRIFT_MIN:
                out.append(cur)
            cur = []
        cur.append(pairs[k])
        prev = idx
    if len(cur) >= QA_DRIFT_MIN:
        out.append(cur)
    return out


def qa_drift_issues(text: str) -> list[dict]:
    """给判据/日志用的形状：[{'n': 长度, 'pairs': [(问, 没接住的), ...]}]。"""
    return [{'n': len(run), 'pairs': run} for run in qa_drift_runs(text)]


def qa_drift_note(text: str) -> str:
    """把"哪几句各说各话"说给模型听（放进重写提示词）。"""
    runs = qa_drift_runs(str(text or ''))
    if not runs:
        return ''
    body = []
    for r in runs:
        body.append('连着 %d 句问出去没人接：' % len(r)
                    + ' ／ '.join('「%s」→「%s」' % (a, b) for a, b in r))
    return chr(10).join(body)


def best_swap_prefix(text: str, pairs: list[tuple[str, str]],
                     *, min_run: int = QA_DRIFT_MIN) -> tuple[str, int, int]:
    """从**少**到多试 `pairs` 的前缀，取第一个把"最长连续悬空"压到 `min_run` 以下的。

    返回 `(改后的文本, 用了几对, 改后的最长连续)`；一对都换不动 ⇒ `(原文, 0, 原值)`。

    ★★★ 为什么是"试前缀"而不是"全用"：实测（`developers/probe_drift_fix.py`，
      拿用户点名的那串五连问）—— 模型一次给了 4 句改写，全用能把最长连续压到 0，
      但**每一句都变成"半句回答；自己的问题"**，四句连排是**新的模版腔**，
      比原来的毛病更难救；用前 2 句只压到 4（不够），用前 3 句就到 0。
      ⇒ 不猜"该改哪几句"，用**确定性的前缀搜索**取最小够用的一档：
      既不手软（必须压到人的天花板以下），也不贪多（多改一句就多一分模版味）。
    [EN] Try prefixes of the proposed swaps and return the first one that brings the longest
    [EN] unanswered run below the human ceiling; falling back to the best reduction found.
    [EN] Empirical: using every proposed swap rewrote 4 lines and produced a fresh
    [EN] template-like cadence; the smallest sufficient prefix is both safer and enough.
    """
    base = max([len(r) for r in qa_drift_runs(text)] or [0])
    best_text, best_max, used = text, base, 0
    for n in range(1, len(pairs) + 1):
        cand = swap_lines(text, pairs[:n])
        if not cand or cand == text:
            continue
        cur = max([len(r) for r in qa_drift_runs(cand)] or [0])
        if cur < best_max:
            best_text, best_max, used = cand, cur, n
        if cur < min_run:
            break
    return best_text, used, best_max


def answer_drift_rewrite_prompt(text: str, note: str) -> str:
    """请模型把"连着几句没人接"的链条**修出一处真答复**时说的话。

    ★★★ 检测是**确定性的**（`qa_drift_runs`），所以这里**不再设判官** ——
      已经知道有毛病，再来一轮判官只是多花一次调用（成本要给在刀刃上，
      见 `config.py` 里 `PROSE_DRIFT_FIX` 的说明）。
    ★★★ 收货靠四道闸（在 `agents._fix_answer_drift`）：
      毛病变少 / 台词没少 / 长度 0.9–1.3 倍 / 每句不短于原句 0.6 倍，
      任何一道不过 ⇒ **原样返回**（宁可留着毛病，不许改出新毛病）。
    [EN] Detection is deterministic here, so no judge round-trip; acceptance is guarded
    [EN] by four checks in `_fix_answer_drift`, any failure means keep the original.
    """
    return (
        '下面这一章里有几段对话是**各说各话**：上一句问出去，紧接那句答的不是这个，'
        '再下一句又问新的，连着几句没人真正接住。已经替你标出来了：' + chr(10) + chr(10)
        + str(note or '') + chr(10) + chr(10)
        + '请把它修掉 —— 要求：' + chr(10)
        + '1. 每一段里**只改 1 句**（最多 2 句），把它改成**真的接住上一句**的那一种：'
           '承认听见了、给了半个回应、或者把话题**明写地**转开'
           '（「这话他没接，只把杯子推过去」也算接住了 —— 那是有意的回避）。' + chr(10)
        + '2. **不许把所有问句都改成有问必答** —— 回避、答非所问、沉默都是好小说'
           '常用的东西，**留一处**就够了；改多了这场戏就没味道了。' + chr(10)
        + '3. 其余台词一个字都不许动；事实不许改（谁问的、问的是什么、先后顺序）。' + chr(10)
        + '4. 每句改完的字数不少于原句。' + chr(10)
        + '5. ' + _NO_META_CLAUSE.replace('⚠ **不许把上面的要求写进正文**：', '')
        + chr(10)
        + '6. 只输出**被改的那几句**（原句 → 新句，一行一对），'
           '不要输出全章、不要标题、不要解释：' + chr(10)
        + '   原句：<照抄原句>' + chr(10)
        + '   新句：<改好的那一句>' + chr(10) + chr(10)
        + '── 原文（只供对照，别整章输出）──' + chr(10) + str(text or ''))


# ══════════════════════════════════════════════════════════════
#  R48 多轮检查（写小说时 / 导出前 两个关口）—— 2026-10-20
# ══════════════════════════════════════════════════════════════
#
# ★★★ 用户原话：「我希望一开始写小说和最后导出的时候都可以进行几轮的问题检查
#   也修复，把常见的问题都修复掉」。
#
# 此前的问题：**一轮串行跑完就走**（`_transcribe_once` 里七个 `_fix_*` 各跑一次），
# 每条修复都只管自己那一类，而且**改完从不复查**：
#   · 修 A 的时候可能把 B 又弄坏了（删一句答话 ⇒ R46 变悬空；
#     整章重写 ⇒ 又添一句元叙述）；
#   · 一轮修不好的，没人再试第二次（snow_v19 六次追问就是这么留下来的）。
# ⇒ 现在把它做成**闭环**：跑一轮 → 数一遍还剩多少毛病 → 没清干净再来一轮。
#
# ★★★ 两条止损（不然会烧钱烧到天亮）：
#   ① **没有变少就停**：这一轮改完毛病数没下降，说明剩下的这一轮也改不动了；
#   ② **轮数封顶**：默认 3 轮（`PROSE_CHECK_ROUNDS`），够用且可控。
#   每一轮内部仍然按"改坏风险从小到大"排：先删（确定性）→ 再改（要模型）→ 最后排版。
# [EN] R48: a closed loop instead of one shot. Run a round, count what is left, run
# [EN] again if anything remains -- with two brakes: stop when a round does not reduce
# [EN] the count, and cap the rounds (default 3).


# ══════════════════════════════════════════════════════════════════════
#  2026-10-28：**副词盖章式对话标签**（"他严肃地说道"）
# [EN] 2026-10-28: **adverb-stamped dialogue tags** ("he said sternly")
# ══════════════════════════════════════════════════════════════════════
#: 一章里最多允许几处「××地说 / ××地道」
#: ★ 为什么给出配额而不是一律清零：真人小说里这种句式**偶尔会有**（一章一两处），
#:   它的病不在"出现过"，而在"通篇靠它标记情绪"。配额取自编辑圈稿的口径：
#:   同一章里第三次出现，就是作者在给台词盖章，不是人物在说话。
# [EN] A per-chapter quota rather than zero: real novels do use the pattern occasionally; the
# [EN] disease is stamping every line with it, not its existence.
TAG_ADV_CAP = 2

#: **闭集**（本项目铁律：可数槽必须闭集 —— 同义词是字面判据的漏报后门）。
#: ⚠ 为什么不做"任意 1~3 字 + 地"的通配：`他低声地问道` 会被切成 `他低声` + `问道`，
#:   连主语一起删掉（实测：改成 `问道` 后那一句没人说话了）。闭集只删**副词**，
#:   主语和动词一个不动 ⇒ 最坏情况是"漏报"，不会改坏句子。
# [EN] A **closed set** (project rule: countable slots must be closed sets -- synonyms are the
# [EN] back door). A wildcard `1-3 chars + 地` ate the subject in testing; deleting only the
# [EN] adverb from a closed list can ignore a case but never damages a sentence.
_TAG_ADVS: tuple[str, ...] = (
    '低声', '高声', '大声', '轻声', '厉声', '沉声', '柔声', '哑声', '颤声', '恨声',
    '冷冷', '淡淡', '幽幽', '缓缓', '慢慢', '急急', '匆匆', '轻轻', '低低', '喃喃',
    '严肃', '平静', '冷笑', '笑着', '咬牙', '恨恨', '默默', '哽咽', '沉沉', '细细',
)
_TAG_VERB = r'(?P<v>说道|问道|答道|说|问|答|道)'
#: 副词 + 地 + 说/问/答/道，**后面必须紧跟引号或标点** ——
#: ⚠ 不要求紧跟，「他好好地说道理」会被切成「他说道理」（意思全变）。
# [EN] The verb must be followed by quote marks or punctuation, otherwise `说道理` breaks.
_TAG_ADV = re.compile(
    '(?:%s)地%s(?=[：:，,。！？!?、；;\\s「“"\'‘])' % ('|'.join(_TAG_ADVS), _TAG_VERB))
#: 引号里的内容（台词）—— 检测与修复都**只动叙述**，台词一个字不碰。
#: ⚠⚠ **必须带捕获组**：`re.split` 没有捕获组时会把分隔符**直接丢掉** ——
#:   第一版就漏了这个括号，冒烟测试里"他严肃地说道：「这账不对。」"整句台词被吃掉了。
#:   有捕获组才是 `[叙述, 台词, 叙述, …]` 的交替形态，`i % 2` 那套判断才成立。
# [EN] ⚠⚠ The capture group is mandatory: `re.split` without one **drops the separators**,
# [EN] which ate entire lines of dialogue in the first version.
_QUOTED_BIT = re.compile(r'(「[^」]*」|“[^”]*”|『[^』]*』)')


def dialogue_tag_spans(text: str) -> list[str]:
    """**副词盖章式对话标签**在叙述里出现的那几处（原文片段，给日志看）。

    ★ 为什么只数叙述：台词里可以有"我慢慢地说"这种话（人在说自己在怎么说），
      那是内容；作者在台词外面贴"严肃地说"，才是盖章。
    ⚠ 只认闭集里那三十个副词（见 `_TAG_ADVS`）—— 漏报接受，误改不接受。
    [EN] Counts the pattern in narration only, never inside quoted lines, and only for the
    [EN] closed adverb list. False negatives accepted, false rewrites not.
    """
    raw = str(text or '')
    if not raw.strip():
        return []
    parts = _QUOTED_BIT.split(raw)
    hits: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:                        # 引号里的内容，跳过
            continue
        hits.extend(m.group(0) for m in _TAG_ADV.finditer(part))
    return hits


def dialogue_tag_issues(text: str) -> list[str]:
    """超过配额 `TAG_ADV_CAP` 的**那几处**（前两处不报：真人也这么写）。

    [EN] Only the occurrences beyond the quota; the first two are how humans write.
    """
    return dialogue_tag_spans(text)[TAG_ADV_CAP:]


#: 超配额时把动词**归一到最朴素的三个**（说 / 问 / 答）。
#: ★ 为什么连动词一起归一：只删副词会留下「他道：」「她说道：」—— 这正是编辑说的
#:   "标签换十个花样，还是标签"。「他道」还偏文言，与"不许半文半白"直接冲突。
# [EN] Normalise the verb too: deleting only the adverb leaves 「他道：」, which is both another
# [EN] fancy tag and half-classical Chinese, banned by the book's own rules.
_TAG_PLAIN = {'道': '说', '说道': '说', '问道': '问', '答道': '答'}


def strip_dialogue_tag_adverbs(text: str, keep: int = TAG_ADV_CAP) -> tuple[str, int]:
    """把「××地说」的**副词删掉**、动词归一（确定性，只动标点级的字，不重写句子）。

    ✅ `他严肃地说道：「坐。」` → `他说：「坐。」`
    ✅ `她低声地问` → `她问`
    ✅ `他冷冷地道` → `他说`
    ❌ **不碰台词**：`「我慢慢地说给你听」` 原样保留
    ⚠ 保留**主语和动词**：整段"××地说"全删会连"谁在说"一起消失，而读者需要
      知道这句话是谁说的（这是对话标签唯一的正当用途）。
    ★ `keep`：**留下前几处**（默认等于配额）。整篇一律清零等于比口径更狠 ——
      真人也这么写（一章一两处），全删会把必要提示也削掉。
    [EN] Deletes the adverb, normalises the verb, keeps the subject, never touches quoted
    [EN] speech. `keep` preserves the first N occurrences (the quota), because wiping them all
    [EN] is harsher than the criterion.
    """
    raw = str(text or '')
    if not raw.strip():
        return raw, 0
    budget = max(0, int(keep or 0))
    seen = [0]

    def _sub(m):
        if seen[0] < budget:
            seen[0] += 1
            return m.group(0)                 # 配额内：原样留着
        v = m.group('v')                      # 超配额：只留动词（并归一）
        return _TAG_PLAIN.get(v, v)

    parts = _QUOTED_BIT.split(raw)
    n = 0
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part)
            continue
        new, k = _TAG_ADV.subn(_sub, part)
        n += k
        out.append(new)
    return ''.join(out), n


# ════════════════════════════════════════════════════════════════════════════════
#  ★★★ 2026-10-28：中文「套话」闭集检测（**只查叙述**）
# [EN] ★★★ 2026-10-28: closed-set Chinese "slop" patterns (**narration only**)
# ════════════════════════════════════════════════════════════════════════════════
#  来源：no-ai-slop（原版 petergyang/no-ai-slop，MIT；中文版 shenxianpeng/no-ai-slop）
#  的 "Patterns to cut"。⚠ 原版那份是**针对英文**的（delve into / it's worth noting），
#  中文版作者自己重写了一份 —— 我们这里再收一遍，**只留中文叙述层能确定性匹配的几条**。
#
#  ⚠ 两条边界（都是从本项目的实测里来的，别删）：
#    ① **只查叙述，引号里的台词一条都不查**：人物说"不是 X，是 Y"是完全自然的，
#       设定集里那句「这页没写坏。是写完了。」就是活的对白 —— 把它判成套话 = 误伤；
#    ② **漏报接受、误报不接受**：宁可少报几条，不可把作者的好句子判成套话。
#
#  Source: no-ai-slop "Patterns to cut" (petergyang/no-ai-slop, MIT; CN fork
#  shenxianpeng/no-ai-slop). The original targets English; the CN fork rewrote the list.
#  ⚠ Two boundaries (both measured in this project): ① narration only, never quoted speech --
#  a character saying "not X, Y" is perfectly natural; ② prefer under-reporting to
#  flagging the author's good lines.
# ════════════════════════════════════════════════════════════════════════════════
#: 一章配额。真人也偶尔这么写（一章一两处），全报等于比口径更狠。
SLOP_CAP = 2

SLOP_PATTERNS: tuple[tuple[str, str], ...] = (
    # 「不是 X，而是 Y」—— 把一句平实的话装成"洞察"
    ('二元对立', r'不是[^。，！？；]{1,14}[，,、]\s*(?:而是|是)[^。，！？；]{1,14}'),
    # 「不是 A。不是 B。而是 C。」—— 三段式，最典型的模型腔
    ('否定列举', r'不是[^。！？]{1,12}[。！？]\s*不是[^。！？]{1,12}[。！？]'),
    # 「最关键的一点：」「真相是：」—— 用冒号造假悬念
    ('冒号揭示', r'(?:最关键|最重要|最要紧|真正的|答案|真相|秘密)[^。：]{0,6}：'),
    # 把一件事说成"意义重大"，却不给事实
    ('重要性吹捧', r'(?:标志着|彰显了|体现了|印证了|诠释着|'
                   r'扮演着至关重要的角色|具有深远的意义|不可忽视的意义)'),
    # 叙述者跳出来替读者总结（StoryScope：真人 52%、AI 77%）
    ('总结式点题', r'(?:终于明白|终于懂得|这才明白|此刻他明白|他终于知道|'
                   r'说到底|归根结底|正所谓|这就是所谓)'),
)

_SLOP_RE: tuple[tuple[str, 're.Pattern[str]'], ...] = tuple(
    (name, re.compile(pat)) for name, pat in SLOP_PATTERNS)


def slop_spans(text: str) -> list[tuple[str, str]]:
    """叙述层里命中的套话，按出现顺序给 `(类名, 原文)`。

    ⚠ 与 `dialogue_tag_spans` 同一个规矩：**跳过引号里的台词**。
    [EN] Same rule as `dialogue_tag_spans`: **skip quoted speech**.
    """
    raw = str(text or '')
    if not raw.strip():
        return []
    out: list[tuple[str, str]] = []
    for i, part in enumerate(_QUOTED_BIT.split(raw)):
        if i % 2 == 1:                       # 奇数段 = 引号内 = 台词，不查
            continue
        for name, rx in _SLOP_RE:
            for m in rx.finditer(part):
                out.append((name, m.group(0)))
    return out


def slop_issues(text: str) -> list[str]:
    """超过配额 `SLOP_CAP` 的那几处（前两处不报：真人也这么说）。

    返回的每条形如 `二元对立：不是钱的事，是信任`。
    [EN] Only the hits beyond the quota; the first two are how humans write.
    """
    return [f'{name}：{snip}' for name, snip in slop_spans(text)[SLOP_CAP:]]


def prose_issue_count(text: str) -> dict:
    """这一类文本还剩多少毛病（按类分开数，给多轮检查用）。

    ⚠ 只收**确定性检测得到**的那些类。判官类（打转 / 自洽）不进这个数 ——
      它们每判一次要花一次调用，而且它们自己会抖动；把它们算进"收敛判据"里，
      会让循环因为判官改口而白跑。**这是有意的取舍。**
    [EN] Counts only what deterministic detectors can see. The judge-based checks are
    [EN] deliberately excluded: they cost a call each and jitter, so including them in
    [EN] the convergence test would make the loop run on noise.
    """
    raw = str(text or '')
    out: dict[str, int] = {}
    if not raw.strip():
        return out
    for name, fn in (('憋气段', long_span_issues),
                     ('平铺段', flat_span_issues),
                     ('重复', repeat_issues),
                     ('拥挤段', crowded_paragraph_issues),
                     ('元叙述', meta_narration_issues),
                     ('感知自洽', percept_issues),
                     ('问答悬空', qa_drift_issues),
                     ('道具循环', prop_cycle_issues),
                     ('对话标签', dialogue_tag_issues),
                     ('套话', slop_issues)):
        try:
            out[name] = len(fn(raw))
        except Exception:                                        # noqa: BLE001
            out[name] = 0
    return out


def issue_total(counts: dict) -> int:
    """毛病总数（只看**计数表**，不认识的东西忽略）。"""
    return sum(int(v or 0) for v in (counts or {}).values())


def checkup_report(before: dict, after: dict) -> str:
    """两轮之间的一句话报告（进日志，给排查用）。"""
    parts = []
    for k in sorted(set(before) | set(after)):
        b, a = int(before.get(k, 0)), int(after.get(k, 0))
        if b or a:
            parts.append(f'{k} {b}→{a}')
    return '，'.join(parts) or '（无）'
