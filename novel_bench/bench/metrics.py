# -*- coding: utf-8 -*-
"""Deterministic, model-free measurements.

Everything here is cheap, reproducible and explainable, which is why it is the
backbone of the report: LLM judges drift, counters do not.  The numbers answer
"is the prose mechanically broken?" -- repetition, meta-mark leakage, cast
coverage, period anachronisms, first-person drift.  They deliberately do not
try to answer "is it good"; that is the judge's job.

Score construction (see docs/methodology.md for the rationale and anchors):
start at 100, subtract penalties; each penalty is capped so a single pathology
cannot zero the score on its own.  The formula is intentionally blunt and
published, so a change in score can be traced to a change in text.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .dataset import Case, Work

META_PATTERNS = [
    (r"〔[^〕]{1,40}〕", "方括号元标记"),
    (r"【(?:action|aside|旁白|系统|提示)", "内部标签"),
    (r"(?m)^\s*[◇▸◆◈]\s*", "符号引导行"),
    (r"\*\*[^*\n]{1,40}\*\*", "markdown 加粗"),
    (r"(?m)^\s*(?:人物|地点|时间|场景)\s*[：:]", "字段式抬头"),
    (r"（并入第\s*\d+\s*条[^）]*）", "整理备注"),
    (r"(?m)^\s*第[一二三四五六七八九十百\d]+[拍幕场]\s*$", "分拍标记"),
]

MODERN_WORDS = [
    "手机", "电话", "咖啡", "汽车", "火车", "公里", "地铁", "电视", "电脑",
    "网络", "警察", "医院", "公司", "领导", "项目", "数据", "系统", "情绪",
    "压力", "沟通", "效率", "自信", "观点", "状态", "基因", "病毒", "感染",
    "分钟", "小时", "秒钟", "公里", "公斤", "百分", "逻辑", "概念", "氛围",
]

# Only these kinds carry prose. Everything else is production chrome:
# crew progress lines, stage banners, scene markers, recaps, day summaries.
PROSE_KINDS = {
    "action", "aside", "dialogue", "ambient", "event", "narration",
    "recall", "inner", "inner_voice", "voice", "description", "monologue",
}

SENT_SPLIT = re.compile(r"[。！？!?…]+|\n+")
CJK = re.compile(r"[\u4e00-\u9fff]")


def _sentences(text: str) -> list[str]:
    out = [s.strip() for s in SENT_SPLIT.split(text)]
    return [s for s in out if len(s) >= 2]


QUOTE_RE = re.compile(r"[“”「」『』\"']")

# ══════════════════════════════════════════════════════════════
#  2026-10-20 晚新增：从主程序那一轮修复带过来的四条计数
# ══════════════════════════════════════════════════════════════
#
# ★★★ **为什么 bench 要自己实现一份、又必须跟主程序同口径**
#   README 写着这套工具「独立于主程序运行时」，所以它不 import `crew/`（那边会拖进
#   config / llm，且是推演侧的东西）。但「量什么」必须与产品侧是**同一个定义** ——
#   否则 bench 说「变好了」、产品侧判据说「更差了」，两边永远吵不完。
#   ⇒ 这里的每个阈值都注明对齐 `crew/prose_flow.py` 的哪个常量，
#     且 `tools/verify_bench_parity.py` 会**自动对账**（两边数字不一致就红）。
# [EN] bench stays independent of the main runtime (no `crew/` import), yet the *definitions*
# [EN] must match. Every threshold below names the `crew/prose_flow.py` constant it mirrors,
# [EN] and `tools/verify_bench_parity.py` reconciles them automatically.

#: 台词蒙版：台词整体换成等长空格，但**收尾留一个句末标记**。
#: ⚠ 这条是主程序实测踩出来的（`prose_flow._bare_with_ends`）：不这么做，
#:   多人对话连排会**整段并成一句 61 字的长句**，于是被当成"憋气"去重写。
#:   实测 v22：这么蒙之后「太长」段数 2→0，而真人 18 章分布一毫米没动。
# [EN] Mask dialogue but leave a sentence-end where the quote closes; without it a run of
# [EN] dialogue collapses into one 61-char "long sentence" (measured on the product side).
_QUOTED = re.compile(r'[“「『]([^”」』]*)[”」』]|"([^"]*)"')


def _mask_quotes(text: str) -> str:
    """台词换成等长空格，**收尾处留 `。`**（位置一一对应，可回贴）。"""
    def _sub(m):
        s = m.group(0)
        return '\u3000' * max(0, len(s) - 1) + '。'
    return _QUOTED.sub(_sub, str(text or ''))


#: 句子的**区间**（不是分隔符）。
#: ⚠ 不能用 `SENT_SPLIT.finditer` —— 那个正则是**分隔符**，finditer 拿到的是标点本身，
#:   取回来一句话都取不到（实测：bench 句数 0、道具循环恒为 0）。
#:   产品侧 `_SENT` 也是这个形状（`[^。！？…]*[。！？…]+|$`），两边一致。
# [EN] Sentence **spans**, not delimiters. `SENT_SPLIT.finditer` yields the punctuation
# [EN] itself, so nothing was extracted (measured: 0 sentences, prop cycle always 0).
SENT_SPAN = re.compile(r'[^。！？…]*[。！？…]+|[^。！？…]+$')


def _narr_sentences(text: str) -> list[str]:
    """**只算叙述**的句子（台词内部的标点不切）。

    ⚠ `_sentences`（上面那个）是按 `。！？` 直接切的，台词里的句号也会切开 ——
      算句长时把台词混进叙述了。这里的几条指标一律用这个。
    [EN] Narrative-only sentences: `_sentences` splits on punctuation inside dialogue too,
    [EN] mixing speech into the length statistics. These metrics use this one instead.
    """
    out: list[str] = []
    for para in str(text or '').split('\n'):
        masked = _mask_quotes(para)
        for m in SENT_SPAN.finditer(masked):
            seg = para[m.start():m.end()].strip()
            if len(CJK.findall(seg)) >= 2:
                out.append(seg)
    return out


def _paras(text: str) -> list[str]:
    return [p.strip() for p in str(text or '').split('\n')
            if p.strip() and not p.strip().startswith(('#', '>'))]


def _para_sent_lens(p: str) -> list[int]:
    lens = []
    for s in _narr_sentences(p):
        n = len(CJK.findall(s))
        if n >= 2:
            lens.append(n)
    return lens


#: 道具循环的阈值 = 同一类东西里"被补给 + 被消耗"的句子数之和。
#: 对齐 `prose_flow.PROP_CYCLE_MIN`（产品侧 3）。
#: 真人 18 章「最大复位」中位 0、**最大 0**；真跑 v16/v19/v20 是 4 ⇒ 3 在真人上零误报。
PROP_CYCLE_MIN = 3
#: 补给动作（把消耗掉的东西补回去）。⚠ 不收"拿/放/递"——那些是传递，真人里到处都是。
PROP_REFILL = re.compile(
    r'斟|倒(?:上|满|些|了)?(?:酒|茶|水|一杯|半杯)|添(?:上|些|了)?(?:酒|茶|炭|水|灯)?|'
    r'续(?:上|了)?|换(?:一|壶|杯)|再送|送(?:一壶|一坛)|满上|端(?:来|上|进)|'
    r'(?:再|又)(?:喝|倒|添|斟)(?:一)?(?:杯|壶|碗)')
#: 消耗信号。**必须与器皿/可消耗物同句**才算 —— 否则真人科幻那章会被判进 11 次
#: "消耗"（全是表格里的「没有」「空着」）。
PROP_CONSUME = re.compile(
    r'空(?:了|着|掉)|凉(?:了|透)|(?:没|喝|吃|用)(?:了|光|完|尽)|见底|干了|冷(?:了|透)')
PROP_VESSEL = ('壶', '杯', '碗', '盏', '盘', '碟', '炉', '钵', '盆', '罐', '瓶',
               '坛', '匣', '箱', '盒', '灯', '琴')
PROP_STUFF = ('茶', '酒', '水', '饭', '汤', '粥', '炭', '油', '柴', '纸',
              '墨', '烟', '药', '雪')

#: 「太碎」的阈值 = 段内「逗号数 / 句子数」，**低于**它判病。
#: 对齐 `prose_flow.FLAT_CLAUSE_RATIO`（产品侧 0.2）。
#: 真人 60 段：最小 **0.25** / 中位 1.00；真跑 v23 是 **0.06**。
FLAT_CLAUSE_RATIO = 0.2
#: 「太长」：段内长句（>=25 汉字）过半，或冒出一个 >=45 字的超长句。
#: 对齐 `prose_flow.LONG_MIN` / `SENTENCE_MAX`。真人 18 章最大 **1** 段。
LONG_MIN = 25
SENTENCE_MAX = 45
#: 段要够长才判（与产品侧一致：至少 3 句、30 个汉字）。
RUN_MIN = 3
SPAN_MIN_CHARS = 30


def prop_cycle_max(text: str) -> tuple[int, str]:
    """同一件东西**被反复"续上—耗掉"**的最多次数 ⇒ `(次数, 是哪件东西)`。

    用户 2026-10-20：「继续修复道具循环」。台词每句都不同，可手上的事一遍没变。
    对齐 `crew/prose_flow.py::prop_cycle_issues`（R47）。
    [EN] Max refill/drain cycles on one object; mirrors `prose_flow.prop_cycle_issues` (R47).
    """
    per: dict[str, int] = {}
    for p in _paras(text):
        for s in _narr_sentences(p) or [p]:
            cls = [c for c in PROP_VESSEL + PROP_STUFF if c in s]
            if not cls:
                continue
            if not (PROP_REFILL.search(s) or PROP_CONSUME.search(s)):
                continue
            for k in cls:
                per[k] = per.get(k, 0) + 1
    if not per:
        return 0, ''
    k = max(per, key=lambda x: per[x])
    return per[k], k


def flat_span_count(text: str) -> int:
    """「一句一件事」的段落数（段内**几乎没有分句**）。对齐 `flat_span_issues`（R49）。"""
    n = 0
    for p in _paras(text):
        lens = _para_sent_lens(p)
        if len(lens) < RUN_MIN or sum(lens) < SPAN_MIN_CHARS:
            continue
        masked = _mask_quotes(p)
        commas = masked.count('，') + masked.count('、')
        if commas / len(lens) < FLAT_CLAUSE_RATIO:
            n += 1
    return n


def long_span_count(text: str) -> int:
    """「憋气」的段落数（长句过半 / 有超长句）。对齐 `long_span_issues`（R49）。"""
    n = 0
    for p in _paras(text):
        lens = _para_sent_lens(p)
        if len(lens) < RUN_MIN or sum(lens) < SPAN_MIN_CHARS:
            continue
        _long = sum(1 for x in lens if x >= LONG_MIN)
        if (_long * 2 > len(lens)) or any(x >= SENTENCE_MAX for x in lens):
            n += 1
    return n


def quote_mixed(text: str) -> tuple[int, int]:
    """引号**混用**检测 ⇒ `(ASCII 引号数, 中文引号数)`，两者都 >0 才算混用。

    ★★★ 这条差点变成"专杀真人"的判据（我量真人之前就写好了它）
    ---------------------------------------------------------
    初版判的是"英文引号个数，应当是 0"。可真跑 v24 整篇 24 个 `"`、0 个中文引号，
    看着像硬伤 —— 一量真人样本才发现：**samples/zh 那 18 章全部用 ASCII `"`，
    中文引号 0 个**。那是正常写法，不是病。
    真正的病是**同一篇里混着用**：v23 有 16 个 `"` + 10 个 `“”` ⇒ 读者一眼看出没统一。
    ⇒ 口径改成"是否混用"：单一 ASCII（真人同款）/ 单一中文 都不扣分。
    [EN] The first version judged "any ASCII quote is a defect" -- then the human samples
    [EN] turned out to use ASCII quotes exclusively (zero Chinese ones). Single-style is
    [EN] fine either way; only **mixing** the two in one piece is the defect.
    """
    raw = str(text or '')
    return raw.count('"'), raw.count('“')


#: 中文对白在散文里的标志：成对引号，或「某某道：「…」」。
#: 台本体里对白是独立条目（kind == dialogue），散文里它**揉在叙述句里** ——
#: 按条目数算会严重偏低（实测红楼梦只算出 0.091，远低于实际的对话密度）。
#: [EN] Dialogue markers in prose: paired quotation marks. In script output dialogue is a separate
#: entry (kind == dialogue); in prose it is **folded into narrative sentences**, so counting entries
#: badly under-reports it (measured: Dream of the Red Chamber came out at 0.091).


def name_hit(text: str, name: str, aliases: dict[str, list[str]]) -> str:
    """这个人在正文里出现了吗？返回**命中的那个写法**，没有则空串。

    ★★★ 2026-10-18：先认本名，再认别称。为什么必须认别称见 `Work.people_aliases()`。
    ⚠ 单字别称**不算**（"女""生"这种会被"女儿""学生"误命中）——
      数据里请写两个字以上的称谓，`check` 会拦。
    [EN] Did this person appear? Returns **the form that matched**, or "".
    [EN] ★★★ 2026-10-18: real name first, then aliases (see `Work.people_aliases()` for why).
    [EN] ⚠ Single-character aliases **do not count** ("女"/"生" would hit "女儿"/"学生");
    [EN] write two characters or more in the data, `check` enforces it.
    """
    if name and name in text:
        return name
    for a in aliases.get(name) or []:
        if len(a) >= 2 and a in text:
            return a
    return ""


def _dialogue_share(text: str, source: str, entries: list[dict]) -> tuple[float, str]:
    """对白占比。两种产物两种算法，并**回报用的是哪一种**。

    · `transcript`（台本）：按条目 kind 数，口径精确；
    · `novel`（散文）：按"含引号的行"数。散文把对白揉进叙述句，
      按条目数会低估（红楼梦实测 0.091，实际对话很多）。
    [EN] Dialogue share. Two algorithms for two artefacts, and the one used is **reported**.
    [EN] · `transcript` (script): count entries by kind, exact;
    [EN] · `novel` (prose): count lines containing quotation marks (prose folds dialogue into
    [EN] narrative sentences, so counting entries under-reports it -- 0.091 measured on the
    [EN] Red Chamber while the text is dialogue-heavy).
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if source == "novel":
        if not lines:
            return 0.0, "quote"
        withq = sum(1 for l in lines if QUOTE_RE.search(l))
        return round(withq / len(lines), 3), "quote"
    body = [e for e in entries if str(e.get("text") or "").strip()]
    dial = sum(1 for e in entries
               if e.get("kind") in ("dialogue", "speak", "line"))
    return (round(dial / max(1, len(body)), 3), "kind")


def _dup_sentences(text: str, threshold: float = 0.8, window: int = 8) -> int:
    """**句级**近似重复（相邻 8 句内）。

    ★★★ 2026-10-18 加。原来的 `_similar_pairs` 只在**整行**之间比，
    而散文里一句一段，重复往往发生在"行内的两句"上 —— 实测《嫌疑人X》那一例：
    "冰箱低鸣接着响。门铃停后，门内无人应声。" 整段复现了一次，
    但两行文字不完全相同 ⇒ 行级判据记 0 处，`repeat_4gram` 只有 6.6% 也没报警。
    [EN] **Sentence-level** near-duplicates (within 8 neighbouring sentences).
    [EN] ★★★ Added 2026-10-18. `_similar_pairs` only compared **whole lines**, and prose puts one
    [EN] sentence per line, so repeats happen **inside** lines. Measured on the Suspect X case:
    [EN] "冰箱低鸣接着响。门铃停后，门内无人应声。" recurred wholesale, yet the two lines differ, so
    [EN] the line-level check reported 0 and `repeat_4gram` at 6.6% raised nothing.
    """
    from difflib import SequenceMatcher

    sents = _sentences(text)
    n = 0
    for i, a in enumerate(sents):
        for b in sents[i + 1:i + 1 + window]:
            if len(a) < 6 or len(b) < 6:
                continue
            if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.5:
                continue
            if SequenceMatcher(None, a, b).ratio() >= threshold:
                n += 1
    return n


def _ngram_repeat(text: str, n: int = 4) -> tuple[float, list[tuple[str, int]]]:
    """Share of n-grams that are repeats (0 = no repetition at all).

    Only CJK characters are kept, so punctuation does not dilute the count.
    """
    chars = "".join(CJK.findall(text))
    if len(chars) < n * 4:
        return 0.0, []
    grams = Counter(chars[i:i + n] for i in range(len(chars) - n + 1))
    total = sum(grams.values())
    dup = sum(c - 1 for c in grams.values() if c > 1)
    return dup / total, grams.most_common(8)


def _similar_pairs(lines: list[str], threshold: float = 0.82) -> int:
    """How many adjacent lines are near-duplicates (the 'replay' pathology)."""
    from difflib import SequenceMatcher

    n = 0
    for a, b in zip(lines, lines[1:]):
        if not a or not b:
            continue
        if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.6:
            continue
        if SequenceMatcher(None, a, b).ratio() >= threshold:
            n += 1
    return n


def prose_entries(entries: list[dict]) -> list[dict]:
    """Keep only entries that are part of the story itself.

    The run pushes a lot of production chrome onto the same channel -- "美术 已交活",
    "▸ 作者写小说 · 49s", scene markers, the day summary. Counting those as prose
    inflates every metric (they are short, repetitive and have no dialogue), so the
    filter lives here and is reused by the judge.
    """
    out = []
    for e in entries:
        kind = str(e.get("kind") or "")
        text = str(e.get("text") or "").strip()
        if not text or kind == "_divider":
            continue
        if kind in PROSE_KINDS:
            out.append(e)
        elif not kind and not text.startswith(("·", "▸", "▷", "▤", "■", "§")):
            out.append(e)
    return out


def _strip_export_header(text: str) -> str:
    """Drop the装订稿 header (title, metadata block, horizontal rules)."""
    lines = text.splitlines()
    start = 0
    for i, l in enumerate(lines):
        if l.startswith("## 第"):
            start = i
            break
    body = [l for l in lines[start:] if l.strip() and not l.strip().startswith("---")]
    return "\n".join(body)


def load_result_text(case_dir: Path) -> tuple[str, str]:
    """What to judge/measure: the exported novel text if we have it.

    The live transcript is a script: action / aside / dialogue lines with speaker
    tags. The product's actual output is the bound daily text under `导出/`.
    Those differ a lot, so the harness prefers the export and records which one
    it used -- otherwise two runs could look different merely because one had
    `novel.md` and the other did not.
    """
    p = case_dir / "novel.md"
    if p.is_file():
        text = _strip_export_header(p.read_text(encoding="utf-8", errors="replace"))
        if len(text) >= 200:
            return text, "novel"
    return "", "transcript"


def compute(work: Work, case: Case, case_dir: Path) -> dict[str, Any]:
    tpath = case_dir / "transcript.jsonl"
    if not tpath.is_file():
        return {"case": case.id, "error": "no transcript"}
    entries = []
    for line in tpath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    body = prose_entries(entries)
    script_text = "\n".join(e["text"].strip() for e in body)
    novel_text, source = load_result_text(case_dir)
    text = novel_text or script_text
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    dialogue = [e for e in body if e.get("kind") in ("dialogue", "speak", "line")]
    sents = _sentences(text)
    lens = [len(s) for s in sents]

    repeat, top = _ngram_repeat(text, 4)
    dup_pairs = _similar_pairs(lines)
    dup_sents = _dup_sentences(text)
    dialogue_ratio, dialogue_metric = _dialogue_share(text, source, body)

    meta_hits: list[str] = []
    for pat, name in META_PATTERNS:
        found = re.findall(pat, text)
        if found:
            meta_hits.append(f"{name}×{len(found)}")

    # ★★★ 2026-10-18：按"本名 or 别称"判出场（见 `name_hit` / `Work.people_aliases()`）。
    #   以前只认本名，把"用称谓写对了"判成"没出场"。
    # [EN] ★★★ 2026-10-18: count a character as present via "real name or an alias" (see
    # [EN] `name_hit` / `Work.people_aliases()`). Previously only real names counted, so writing
    # [EN] correctly with titles was graded as "absent".
    aliases = work.people_aliases()
    names = work.people_names
    cast_hits = {n: name_hit(text, n, aliases) for n in names}
    cast_hits = {k: v for k, v in cast_hits.items() if v}
    present_hits = {n: name_hit(text, n, aliases) for n in case.present}
    present_hits = {k: v for k, v in present_hits.items() if v}
    by_alias = {k: v for k, v in present_hits.items() if v != k}
    # ★★★ 2026-10-18：**不该在场的人出现了**（offstage leak）。
    #   实测五例里四例中招：hlm-01 的"贾宝玉也在屋里"、lz-01 的"院中……吴生同在"、
    #   sx-01 的"汤川在屋里"、st-01 的"伏羲皆已在场" —— 都不在 `present` 里。
    #   根因在产品侧（作家拿不到本轮上场名单），但**指标必须先能抓到**，
    #   否则这类错误全靠人读正文才看得见。
    #   口径：设定集里有、但这一场 `present` 里没有的人，出现在正文里。
    #   ⚠ 只数**出现**，不数"被提到"（"宝玉不在家"这种提及不该算）。
    #     难分辨时宁可少报：这里只在**动作/对白/环境类文本**里找（`prose` 已经过滤过）。
    # [EN] ★★★ 2026-10-18: **someone off stage appeared** (offstage leak). Measured: four of five
    # [EN] cases had it (hlm-01 "贾宝玉也在屋里", lz-01 "吴生同在", sx-01 "汤川在屋里",
    # [EN] st-01 "伏羲皆已在场") -- none of them in `present`. The root cause is on the product side
    # [EN] (the novelist never receives the on-stage roster), but **the metric has to catch it first**,
    # [EN] otherwise these errors are only visible by reading the prose by hand.
    # [EN] Definition: people in the settings but not in this case's `present`, appearing in the text.
    # [EN] ⚠ Count **appearances**, not mentions ("宝玉不在家" is only a mention). When it is hard to
    # [EN] tell, prefer under-reporting.
    offstage = [n for n in names if n not in set(case.present)]
    leaks = {n: name_hit(text, n, aliases) for n in offstage}
    leaks = {k: v for k, v in leaks.items() if v}

    taboos = [str(t) for t in (work.style().get("taboos") or [])]
    era = str(work.style().get("era") or "")
    if era == "premodern" or work.category == "古典":
        taboos = taboos + MODERN_WORDS
    taboo_hits = {t: text.count(t) for t in dict.fromkeys(taboos) if t and text.count(t)}
    taboo_total = sum(taboo_hits.values())

    # ★★★ 2026-10-20：`aside`（**心里的话**）必须跟 `dialogue` 一样排掉。
    #   实测证据（snow_v18）：成品小说引号外**一个「我」都没有**（13 个全在台词里），
    #   可这一栏照报「第三人称里出现『我』×18」，白扣 7.9 分。
    #   追下去全是这种条目 —— `驹子心想：我借着酒劲才敢开口，他会怎么回应我呢？`
    #   第三人称小说里**人物心里自称"我"是对的**，那不是视角漂移。
    #   ⚠ 这一栏量的是"叙述者"有没有冒出第一人称，心里的话不是叙述者的嗓子，
    #     前提是 `aside` 这一支真的只装心声；若将来它混进别的写法，这条要重估。
    # [EN] ★★★ 2026-10-20: `aside` (inner thought) must be excluded like `dialogue`.
    # [EN] Evidence (snow_v18): the finished novel had **zero** 我 outside quote marks,
    # [EN] yet this column reported "18 first-person marks in a third-person work"
    # [EN] and docked 7.9 points. Every hit was an entry like
    # [EN] "驹子心想：我借着酒劲才敢开口" -- a character thinking "I" in a third-person
    # [EN] novel is correct, not POV drift. This column measures whether the *narrator*
    # [EN] slips into first person; an inner voice is not the narrator's voice.
    narr_text = "\n".join(e["text"] for e in body
                          if e.get("kind") not in
                          ("dialogue", "speak", "line", "aside"))
    first_person = len(re.findall(r"我", narr_text))
    pov = str(work.style().get("pov") or "")
    third = "第三" in pov
    fp_ratio = first_person / max(1, len(narr_text) / 100)

    idle = sum(1 for e in body if "没动" in e["text"] and len(e["text"]) < 30)

    # ── 2026-10-20 晚新增的四条（口径同 `crew/prose_flow.py`，见上面的常量块）──
    prop_n, prop_who = prop_cycle_max(text)
    flat_spans = flat_span_count(text)
    long_spans = long_span_count(text)
    ascii_q, zh_q = quote_mixed(text)
    quotes_mixed = bool(ascii_q and zh_q)

    # -- score ---------------------------------------------------------
    penalties = {
        "重复率": min(35.0, max(0.0, (repeat - 0.05) * 220)),
        "近似复读": min(20.0, (dup_pairs + dup_sents * 0.6) * 2.5),
        "元标记泄漏": min(15.0, sum(int(h.split("×")[1]) for h in meta_hits if "×" in h) * 3),
        "时代禁忌词": min(15.0, taboo_total * 2.0),
        "在场人物缺席": min(10.0, (1 - len(present_hits) / max(1, len(case.present))) * 10),
        "空拍": min(10.0, idle * 1.5),
        # 不该在场的人出现了：每处 4 分，最多 16 —— 这是**硬错**（读者会当场出戏）。
        # [EN] Someone off stage appeared: 4 points each, capped at 16 -- this is a **hard error**
        # [EN] (the reader is thrown out immediately).
        "场外人物": min(16.0, len(leaks) * 4.0),
        "视角漂移": min(10.0, max(0.0, fp_ratio - 1.2) * 6) if third else 0.0,
        # ── 2026-10-20 晚新增（四条，全部先在真人 18 章上量过零误报）──
        # 道具循环：同一件东西被反复"续上—耗掉"。真人最大 **0**，真跑 4。
        # 每超阈值一次扣 3 分，封顶 12 —— 不算硬错，但读起来像在原地踏步。
        # [EN] Prop cycle: deepest refill/drain on one object. Human max 0, real runs 4.
        "道具循环": min(12.0, max(0, prop_n - PROP_CYCLE_MIN + 1) * 3.0),
        # 太碎：段内「逗号/句」低于 0.2（真人 60 段最小 0.25，零命中）。
        # 每段 2 分封顶 10 —— 这是用户点名过的毛病，但他要的是"段落感"不是"不许短句"。
        # [EN] Too choppy: commas per sentence under 0.2. Two points per paragraph, cap 10.
        "太碎段": min(10.0, flat_spans * 2.0),
        # 太长：长句过半或有超长句（真人最高 1 段）。同样每段 2 分封顶 8。
        # [EN] Too long: over half long sentences, or one over-long sentence. Cap 8.
        "憋气段": min(8.0, max(0, long_spans - 1) * 2.0),
        # 引号混用：**同一篇里**既有 `"` 又有 `“”`。⚠ 单一 ASCII 不扣分 ——
        # samples/zh 那 18 章全用 ASCII，那是正常写法（这条差点写成专杀真人）。
        # [EN] Mixed quote styles only. Single ASCII is fine: all 18 human chapters use it.
        "引号混用": 4.0 if quotes_mixed else 0.0,
    }
    score = round(max(0.0, 100 - sum(penalties.values())), 1)

    issues: list[str] = []
    if repeat > 0.12:
        issues.append(f"四字重复率 {repeat:.1%}（真人基线 0–3%）")
    if dup_pairs >= 3:
        issues.append(f"相邻行近似复读 {dup_pairs} 处")
    if dup_sents >= 2:
        issues.append(f"相邻句近似复读 {dup_sents} 处（行内重复，行级判据看不到）")
    if meta_hits:
        issues.append("元标记泄漏：" + "、".join(meta_hits))
    if taboo_total:
        top_taboo = sorted(taboo_hits.items(), key=lambda kv: -kv[1])[:4]
        issues.append("时代禁忌词：" + "、".join(f"{k}×{v}" for k, v in top_taboo))
    if leaks:
        issues.append("场外人物出场：" + "、".join(f"{k}→{v}" for k, v in leaks.items()))
    if len(present_hits) < len(case.present):
        missing = [n for n in case.present if n not in text]
        issues.append("在场却没出场：" + "、".join(missing))
    if idle >= 3:
        issues.append(f"空拍 {idle} 次")
    if third and fp_ratio > 2.4:
        issues.append(f"第三人称作品里叙述层出现『我』×{first_person}")
    # ── 2026-10-20 晚新增 ──
    if prop_n >= PROP_CYCLE_MIN:
        issues.append(f"道具循环：「{prop_who}」被反复续上/耗掉 {prop_n} 次"
                      f"（真人最大 0，阈值 {PROP_CYCLE_MIN}）")
    if flat_spans:
        issues.append(f"太碎 {flat_spans} 段（段内逗号比句子还少 = 一句一件事；"
                      f"真人最小 0.25/句，阈值 {FLAT_CLAUSE_RATIO}）")
    if long_spans > 1:
        issues.append(f"憋气 {long_spans} 段（长句过半或有超长句；真人最高 1 段）")
    if quotes_mixed:
        issues.append(f"引号混用：ASCII {ascii_q} 个 + 中文 {zh_q} 个"
                      f"（单一样式不扣分，混着用才乱）")

    return {
        "case": case.id,
        "work": work.id,
        "source": source,
        "script_chars": len(script_text),
        "entries": len(body),
        "chars": len(text),
        "lines": len(lines),
        "dialogue_ratio": dialogue_ratio,
        "dialogue_metric": dialogue_metric,
        "sentence_len_median": round(statistics.median(lens), 1) if lens else 0,
        "sentence_len_mean": round(statistics.fmean(lens), 1) if lens else 0,
        "sentence_len_p90": round(sorted(lens)[int(len(lens) * 0.9)], 1) if lens else 0,
        "repeat_4gram": round(repeat, 4),
        "repeat_top": [{"gram": g, "n": c} for g, c in top[:5]],
        "dup_pairs": dup_pairs,
        "dup_sent_pairs": dup_sents,
        #: 用了**别称**出场的人：`{本名: 正文里的写法}`。空 = 都写了本名。
        #: 报告里要显示它，否则"0.75 出场率"看不出是"漏了人"还是"写了称谓"。
        #: [EN] People who appeared **under an alias**: `{real name: form used in the text}`.
        #: [EN] Empty = everyone was written by real name. The report must show this, otherwise a
        #: [EN] coverage of 0.75 cannot be read as "missing person" vs "written by title".
        "present_by_alias": by_alias,
        #: **不该在场却出现了**：`{姓名: 正文里的写法}`。空 = 干净。
        #: [EN] **Off stage but appeared**: `{name: form used in the text}`. Empty = clean.
        "offstage_leak": leaks,
        "meta_marks": meta_hits,
        "cast_coverage": round(len(cast_hits) / max(1, len(names)), 3),
        "present_coverage": round(len(present_hits) / max(1, len(case.present)), 3),
        "missing_cast": [n for n in names if n not in cast_hits],
        "taboo_hits": taboo_hits,
        "first_person_marks": first_person,
        "idle_beats": idle,
        # ── 2026-10-20 晚新增（口径同 `crew/prose_flow.py`，由 verify_bench_parity 对账）──
        #: 同一件东西被反复"续上—耗掉"的最多次数，以及是哪件东西。
        #: 真人 18 章最大 **0**；真跑 v20 是 4 ⇒ `>= PROP_CYCLE_MIN` 才算病。
        #: [EN] Deepest refill/drain count on one object, plus which object.
        "prop_cycle_max": prop_n,
        "prop_cycle_item": prop_who,
        #: 「一句一件事」的段数（段内逗号比句子还少）。真人 18 章 **0 段**。
        #: [EN] "One event per sentence" paragraphs; human chapters have zero.
        "flat_spans": flat_spans,
        #: 「憋气」的段数（长句过半 / 有超长句）。真人最高 **1 段**。
        #: [EN] "Breathless" paragraphs; human max is one.
        "long_spans": long_spans,
        #: 引号混用：`{ascii, zh}` 两种都 >0 才是问题（单一 ASCII 是真人同款写法）。
        #: [EN] Mixed quote styles; single ASCII is how the human samples are written.
        "quotes_ascii": ascii_q,
        "quotes_zh": zh_q,
        "quotes_mixed": quotes_mixed,
        "penalties": {k: round(v, 1) for k, v in penalties.items()},
        "hygiene_score": score,
        "issues": issues,
    }


def load_meta(case_dir: Path) -> dict:
    p = case_dir / "meta.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}
