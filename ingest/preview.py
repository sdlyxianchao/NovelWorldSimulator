# -*- coding: utf-8 -*-
"""开卷「交给 AI 之前」的内容概览（同意门）。

为什么要有它
------------
摄取管线里前面几步（扫描、读取、分章）都只在本机做，**一分钱不花**；
真正花 token、也真正把作者的东西**发到外部服务**的，是后面的 AI 几步。
所以在第一次 LLM 调用之前，把「到底传进来了什么」摊开给作者看一眼，
并针对两件事分别取同意：

  ① **含正文** → 正文内容会被发送到所配置的大模型服务（隐私相关，必须说清发去哪）；
  ② **内容较多** → 可能消耗较多 token（花钱相关）。

设计原则
--------
- **数字要真。** 各步送进提示词的量都有硬上限（`ingest/*.py` 里的截取），
  所以"预计 token"按**这些上限**算，而不是按源文件大小乘以一个魔法系数。
  源文件很大时真正的后果是**中间会被截断**，这一点也必须如实告诉作者
  —— 比一句含糊的"可能很贵"有用得多。
- **只算本机能算的。** 「剧情参考线」那一步在本地还没有（要先由 AI 从正文里提出来），
  所以用大纲文件的内容估；这是**下界**，实际不会更少。
- **不猜价格上限**：按当前【摘要档】模型的单价算，作者自己配的价目覆盖
  （`MODEL_PRICE_OVERRIDES`）也照用。

English:
Content overview for the start of the book "before handing to AI" (consent gate).
Why it exists
------------
In the ingestion pipeline, the earlier steps (scan, read, split chapters) all run locally,
**costing nothing**;
what actually spends tokens, and actually **sends the author's material to external services**,
are the later AI steps.
So before the first LLM call, lay out "exactly what got passed in" for the author to see,
and obtain consent separately for two things:
  ① **Contains body text** -> the body content will be sent to the configured LLM service (privacy-related, must state clearly where it's sent);
  ② **Content is fairly large** -> may consume more tokens (cost-related).
Design principles
--------
- **Numbers must be real.** The amount sent into the prompt at each step has a hard limit (the truncation in `ingest/*.py`),
  so "estimated tokens" is calculated by **these limits**, not by source file size multiplied by some magic coefficient.
  When the source file is very large, the real consequence is that **the middle gets truncated**, and this must also be honestly told to the author
  -- far more useful than a vague "might be expensive".
- **Only compute what can be computed locally.** The "plot reference line" step doesn't exist locally yet (it must first be extracted from the body by AI),
  so estimate using the outline file's content; this is a **lower bound**, the actual amount won't be less.
- **Don't guess a price upper bound**: calculate by the current [summary tier] model's unit price; the author's own configured price overrides
  (`MODEL_PRICE_OVERRIDES`) are also used as-is.
"""
from __future__ import annotations

from typing import Any

from llm.tokens import cost_of, estimate_tokens, parse_overrides, price_of

# 源内容达到这个字数就提醒「内容比较多」（约一本中篇）。
# 想调松紧改这一个数即可 —— 没做成配置项，是因为它不改变行为、只改变提示时机，
# 摆一个没人会去动的开关没有任何意义。
# [EN] When the source content reaches this word count, warn "content is fairly large" (about a
# [EN] novella).
# [EN] To loosen or tighten, just change this one number -- it wasn't made a config item because it
# [EN] doesn't change behavior, only the timing of the warning,
# [EN] and putting a switch nobody would ever touch serves no purpose.
BIG_SOURCE_CHARS = 60_000

# 各步实际送进提示词的字符上限。**与 `ingest/*.py` 里的截取一一对应**：
#   extractor._MAX_CONTENT=20000（2026-10-27 从 12000 提上来；那边改了这里必须跟着改）· genre 3000 · style 4000
# [EN] The actual character limits sent into the prompt at each step. **Corresponds one-to-one with the
# [EN] truncation in `ingest/*.py`**:
# [EN] extractor._MAX_CONTENT=20000 (raised from 12000 on 2026-10-27; changing it there means changing
# [EN] it here) · genre 3000 · style 4000
#   progress 4000 · progress.align 8000
# 改了那边的上限，这里要一起改（`tools/verify_ingest_ui.py` 会核对）。
# [EN] If you change the limits there, change them here too (`tools/verify_ingest_ui.py` will check).
CAPS: dict[str, int] = {
    'extract': 20_000,
    'genre': 3_000,
    'style': 4_000,
    'progress': 4_000,
    'align': 8_000,
}

# 各步预留的输出上限（extract 要 3000，其余 JSON 都很短）
# [EN] Reserved output limits for each step (extract needs 3000, the rest of the JSON is very short)
EST_OUTPUT_TOKENS = 6_000

CATEGORY_ORDER = ('规则', '正文', '人物', '大纲', '设定', '伏笔', '杂项')


def build_brief(items, *, full_text: str = '', novel_text: str = '',
                outline_text: str = '', chapters: dict | None = None,
                mock: bool = False, model: str = '',
                base_url: str = '', overrides: dict | None = None) -> dict[str, Any]:
    """把一次摄取"交给 AI 之前"的概览算成一个可断言、可展示的字典。

    `full_text` / `novel_text` / `outline_text` / `chapters` 一律由调用方传入
    （就是管线里**真正要发出去的那几个字符串**），所以这里的估算不会跟实际脱节。
    
        English:
    Compute an overview of an ingestion "before handing to AI" as an assertable, displayable dict.
        `full_text` / `novel_text` / `outline_text` / `chapters` are all passed in by the caller
        (they are **the very strings that will actually be sent out** in the pipeline), so the estimates here won't drift from reality.
    """
    chapters = chapters or {}

    # ── 按分类统计 ──
    # [EN] ── Statistics by category ──
    by_cat: dict[str, int] = {}
    chars_by_cat: dict[str, int] = {}
    for it in items:
        content = getattr(it, 'content', '') or ''
        if not content:
            continue
        cat = getattr(it, 'category', '') or '杂项'
        by_cat[cat] = by_cat.get(cat, 0) + 1
        chars_by_cat[cat] = chars_by_cat.get(cat, 0) + len(content)

    total_chars = sum(chars_by_cat.values())
    novel_files = by_cat.get('正文', 0)
    novel_chars = chars_by_cat.get('正文', 0)

    # ── 预计送出去多少（按各步上限）──
    #    key 与 `ingest/*.py` 里那几次调用一一对应；extract/genre 用的是整份全文，
    #    style 只看正文、progress 只看大纲、align 看分章结果。
    # [EN] ── How much is expected to be sent out (by each step's limit) ──
    # [EN] The key corresponds one-to-one with those calls in `ingest/*.py`; extract/genre use the full
    # [EN] text,
    # [EN] style only looks at the body, progress only looks at the outline, align looks at the chapter
    # [EN] split result.
    chapters_text = '\n'.join(str(v) for v in chapters.values())
    texts: dict[str, str] = {
        'extract': full_text,
        'genre': full_text,
        'style': novel_text or full_text,
        'progress': outline_text or full_text,
        'align': chapters_text,
    }
    sent_chars = {k: min(len(v), CAPS[k]) for k, v in texts.items()}
    est_in = sum(estimate_tokens(texts[k][:CAPS[k]]) for k in CAPS)
    est_out = EST_OUTPUT_TOKENS

    price = price_of(model or '', overrides) if model else (0.0, 0.0)
    est_cost = cost_of(model or '', est_in, est_out, overrides) if model else 0.0

    return {
        'files_total': len(items),
        'files_read': sum(by_cat.values()),
        'by_category': by_cat,
        'chars_by_category': chars_by_cat,
        'total_chars': total_chars,
        'novel_files': novel_files,
        'novel_chars': novel_chars,
        'has_novel': novel_files > 0,
        'sent_chars': sent_chars,
        'sent_chars_total': sum(sent_chars.values()),
        'est_input_tokens': est_in,
        'est_output_tokens': est_out,
        'est_cost': est_cost,
        'price': price,
        'model': model,
        'base_url': base_url,
        'mock': bool(mock),
        # 源内容超过"提取设定"那一步的上限 → 中间会被掐掉
        # [EN] Source content exceeds the limit of the "extract settings" step -> the middle will be cut off
        'truncated': total_chars > CAPS['extract'],
        'big': total_chars >= BIG_SOURCE_CHARS,
        'big_threshold': BIG_SOURCE_CHARS,
        'caps': dict(CAPS),
    }


def brief_from_cfg(items, *, full_text: str = '', novel_text: str = '',
                   outline_text: str = '', chapters: dict | None = None) -> dict:
    """`build_brief` 的便捷版：单价、模型名、端点都从 `CFG` 现取。
        English:
    Convenience version of `build_brief`: unit price, model name, and endpoint are all fetched live
    from `CFG`.
    """
    from config import CFG
    from util.text import host_of
    tier_model = ''
    try:
        tier_model = CFG.model_of('cheap')
    except Exception:                                       # noqa: BLE001
        tier_model = CFG.s('MODEL_CHEAP') or ''
    return build_brief(
        items, full_text=full_text, novel_text=novel_text,
        outline_text=outline_text, chapters=chapters,
        mock=bool(CFG.b('MOCK_LLM')),
        model=tier_model,
        base_url=host_of(CFG.s('LLM_BASE_URL') or ''),
        overrides=parse_overrides(CFG.s('MODEL_PRICE_OVERRIDES') or ''),
    )


def category_rows(brief: dict) -> list[tuple[str, int, int]]:
    """按固定顺序给出 (分类, 文件数, 字数)，只含有内容的分类。
        English:
    Provide (category, file count, word count) in a fixed order, including only categories with
    content.
    """
    rows = []
    for cat in CATEGORY_ORDER:
        n = brief['by_category'].get(cat, 0)
        if n:
            rows.append((cat, n, brief['chars_by_category'].get(cat, 0)))
    # 不在固定顺序里的分类（万一以后加了新类）也别忘了摆出来
    # [EN] Don't forget to list categories that aren't in the fixed order (in case new categories are added
    # [EN] later)
    for cat, n in brief['by_category'].items():
        if cat not in CATEGORY_ORDER:
            rows.append((cat, n, brief['chars_by_category'].get(cat, 0)))
    return rows
