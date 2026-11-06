# -*- coding: utf-8 -*-
"""文本与文件小工具。
English:
Text and file utilities.
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from pathlib import Path

_HTML_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_HTML_ALL = re.compile(r"<[^>]+>")
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def clip(s: str, n: int, tail: str = "…") -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + tail


def truncate_mid(s: str, n: int, tail: str = " …(略)… ") -> str:
    s = s or ""
    if len(s) <= n:
        return s
    half = max(1, (n - len(tail)) // 2)
    return s[:half] + tail + s[-half:]


def dedent(s: str) -> str:
    lines = (s or "").splitlines()
    lines = [ln.rstrip() for ln in lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    indents = [len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()]
    pad = min(indents) if indents else 0
    return "\n".join(ln[pad:] if len(ln) >= pad else ln.lstrip() for ln in lines)


def host_of(url: str) -> str:
    """从服务地址里取出「协议://主机」这一段（用于"内容会发到哪"的提示）。

    **只保留主机名是有意的**：API Key 可能出现在 query / path 里，
    把整串地址贴到界面上等于泄密。取不出来就原样返回（这里不猜）。
    
        English:
    Extract the "scheme://host" part from a service address (used for the "where will the content be
    sent" hint).
        **Keeping only the hostname is intentional**: the API Key may appear in the query / path,
        pasting the whole address into the UI amounts to leaking it. If it cannot be extracted, return it as-is (no guessing here).
    """
    s = (url or "").strip()
    if not s:
        return ""
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(s)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    except Exception:                                       # noqa: BLE001
        pass
    return s.split("?", 1)[0]


def slugify(s: str, default: str = "x") -> str:
    s = re.sub(r"\s+", "", (s or "").strip())
    s = _INVALID.sub("_", s)
    return s or default


def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)


def contains_any(text: str, words) -> list[str]:
    t = text or ""
    return [w for w in words if w and w in t]


def similarity(a: str, b: str) -> float:
    def grams(s: str) -> set:
        s = re.sub(r"\s+", "", s or "")
        return {s[i:i + 2] for i in range(len(s) - 1)} or {s}
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def norm_line(text: str) -> str:
    """去掉标点与空白，只留字 —— 判"是不是同一句"用。

    ★ 唯一实现（2026-10-18 提到这里）：`display/scene_builder` 的
      `norm_line` / `SceneBuilder._norm_line` 与 `crew/review` 的重复候选扫描
      都读这一个 —— 三处各写一份，迟早一处改了另两处没改。
    ⚠ 只去标点，**不去字**：`我不知道。` 与 `我不知道` 是同一句；
      `我不知道` 与 `我知道` 必须不同（少一个"不"，意思正好反过来）。
    [EN] Strip punctuation and whitespace, keep the characters only -- for "is this the same
    [EN] sentence". ★ The single implementation (hoisted here 2026-10-18): the `norm_line` in
    [EN] `display/scene_builder` and the duplicate-candidate scan in `crew/review` both read this
    [EN] one. ⚠ Punctuation only, **never characters**.
    """
    drop = set(' \t\r\n「」『』“”"\'‘’、，。．！？；：…—-·（）()《》〈〉[]{}<>.,!?;:')
    return ''.join(ch for ch in str(text or '') if ch not in drop)


def strip_html_tags(html: str) -> str:
    s = _HTML_TAG.sub(" ", html or "")
    s = _HTML_ALL.sub("\n", s)
    for k, v in {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
                 "&#39;": "'"}.items():
        s = s.replace(k, v)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def hash_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()

def fill(template: str, **kw) -> str:
    """安全模板替换：只替换 {key}，不动其它花括号。

    提示词里常内嵌 JSON 示例（大量 `{}`），用 str.format() 会把这些花括号
    当成字段名而抛 KeyError；本函数只做字面量 replace，天然免疫。
    
        English:
    Safe template substitution: only replace {key}, leave other braces untouched.
        Prompts often embed JSON examples (lots of `{}`); using str.format() would treat these braces
        as field names and raise KeyError; this function only does literal replace, naturally immune.
    """
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# ══════════════════════════════════════════════════════════════════
#  中文分句 / 按句截断（2026-10-10 加，外部调研第 04 类第 2 条）
# [EN] Chinese sentence splitting / split at sentence boundaries (added 2026-10-10, external research
# [EN] category 04 item 2)
# ══════════════════════════════════════════════════════════════════
#: **中文分句正则**。来历：`Hello-SimpleAI/chatgpt-comparison-detection`
#: 的 `detect/ml_train.py` 里有一段 `sent_cut_zh`。
#: ⚠ 那份仓**没有 LICENSE**（HC3 语料是 CC-BY-SA）⇒ **只重写正则、绝不抄词表**。
# [EN] : **Chinese sentence-splitting regex**. Origin: a `sent_cut_zh` block in
# [EN] `Hello-SimpleAI/chatgpt-comparison-detection`
# [EN] : in `detect/ml_train.py`.
# [EN] : ⚠ That repo has **no LICENSE** (the HC3 corpus is CC-BY-SA) ⇒ **only rewrite the regex, never
# [EN] copy the word list**.
#:
#: 它解决英文那套分句（按 `.` 切）在中文上的两个典型错：
#:   ① 把「」里的对白跟外面的叙述粘成一句（对白该独立成句）；
#:   ② 把省略号 `……` 当成两个点，切出空句。
# [EN] : It fixes two typical failures of the English-style splitting (split on `.`) when applied to
# [EN] Chinese:
# [EN] : ① glueing the dialogue inside "" to the surrounding narration into one sentence (dialogue
# [EN] should stand alone);
# [EN] :   ② treating the ellipsis `……` as two dots, cutting out empty sentences.
_SENT_ZH = re.compile(
    r'[^。！？!?…；;\n]*'                      # 句身：不吃句末标点
    r'(?:[。！？!?]+|…{2,}|…|；|;)?'          # 句末：句号族 / 省略号 / 分号
    # [EN] Sentence body: does not consume sentence-ending punctuation
    # [EN] Sentence end: period family / ellipsis / semicolon
)
#: 算作"句子已经收住"的收尾字符（`head_sentences` 用）
# [EN] : treated as trailing characters meaning "the sentence has already closed" (used by
# [EN] `head_sentences`)
_SENT_END = '。！？!?…」』）)"\''


def sentences_zh(text: str) -> list[str]:
    """把中文切成**句子**（保留标点、去空白、丢掉空句）。

    ★ 与 `style/ai_metrics.sentences()` 的分工（**别混用**）：
      那边切的是**用于计数**的粗分（只认 `.。！？!?`，切完扔掉标点）；
      这边切的是**用于取片段**的细分（保留标点、认省略号与分号），
      因为截出来要给人/模型读，句子读断了就白截。
    
        English:
    Split Chinese into **sentences** (keep punctuation, strip whitespace, drop empty sentences).
        ★ Division of labor with `style/ai_metrics.sentences()` (**do not mix them up**):
          that one does coarse splitting **for counting** (only recognizes `.。！？!?`, discards punctuation after splitting);
          this one does fine splitting **for extracting snippets** (keeps punctuation, recognizes ellipsis and semicolon),
          because the result is meant to be read by a human/model; a broken sentence makes the cut pointless.
    """
    out: list[str] = []
    for line in str(text or '').splitlines():
        for m in _SENT_ZH.finditer(line):
            s = m.group(0).strip()
            if s:
                out.append(s)
    return out


#: 动作描写开头的**自称主语**（"我把壶搁下" 的 "我"）。
#: ⚠ 必须排除「我的 / 我们」：「我的账本被翻开了」剥掉"我"会变成"的账本被翻开了"。
# [EN] The **first-person subject** at the head of an action description.
# [EN] ⚠ Must exclude 我的 / 我们: stripping 我 from "我的账本…" leaves a broken "的账本…".
_SELF_HEAD = re.compile(r'^我(?![们的])')
#: 开头的**括号提示语**（"（抬眼）我把碗挪开"）—— 演员很爱这么写，
#: 剥主语时必须跨过它，否则 `（抬眼）我…` 里的"我"就漏掉了。
# [EN] Leading **parenthetical cue** ("(glancing up) I move the bowl") -- actors write this often;
# [EN] the subject strip must step over it, or the 我 in "（抬眼）我…" survives.
_LEAD_PAREN = re.compile(r'^(?:[（(【\[][^）)】\]]*[）)】\]]\s*)+')


def bare_detail(text: str, limit: int = 80) -> str:
    """动作描写去掉**开头的自称主语**，并截断到 `limit` 字。

    ★★★ 2026-10-28（实测出来的硬伤）：
      演员写出来的 `Action.detail` 是"**我**把壶搁在柜面上"，而落盘那一步是
      `desc = f"{agent.name}{detail}"` ⇒ 正文成了「**张三我把壶搁在柜面上**」。
      三个演员各写各的"我"，一篇里就有三个"我"（这本书是第一人称，读者会读成
      李四一个人在做三件事）。
      根因：演员拿到的是"**动作怎么写**"，它自然用第一人称；而拼名字的那一层
      假定 detail **不带主语**。两边约定不一致，谁也没错，成品是坏的。
      ⇒ 提示词里写清楚（`detail` 不写主语），**并且**在这里兜底剥一次 ——
        "prompt 里写了 ≠ 生效"，这条在项目里已经量过（遵守率 40–74%）。

    ⚠ 为什么不在拼名字那边 `replace('我', '')`：会把"我的"「我们」一起砸了，
      也会砸到句子中间（"他递给我"）。只处理**开头那一个自称**。

        English:
    Strip the **leading self-reference** from an action description and clip it to `limit`.
        ★★★ 2026-10-28 (a defect found by actually running a scene):
          actors write `Action.detail` as "**我**把壶搁在柜面上", while the landing step does
          `desc = f"{agent.name}{detail}"` => the prose reads "**张三我把壶搁在柜面上**".
          With three actors each writing "我", one page has three "I"s (this book is
          first-person, so readers attribute all three actions to Chen Wang).
          Root cause: the actor is told **how to describe an action** and naturally uses the first
          person, while the layer that prefixes the name assumes detail has **no subject**.
          Neither side is wrong; the product is broken.
          => Say it in the prompt (`detail` carries no subject), **and** strip it here as a
             safety net: "written in the prompt != in effect" (40-74% compliance, measured).
        ⚠ Why not `replace('我','')` where the name is prefixed: that would wreck 我的 / 我们 and
          also hit mid-sentence ("他递给我"). Only the **leading** self-reference is handled.
    """
    s = ' '.join(str(text or '').split())
    if not s:
        return ''
    m = _LEAD_PAREN.match(s)
    head = m.group(0) if m else ''
    rest = s[len(head):]
    rest = _SELF_HEAD.sub('', rest, count=1).lstrip('，,、　 ')
    if not rest:
        rest = s[len(head):]              # 别把整句剥没了
    return (head + rest)[:max(0, int(limit))]


def head_sentences(text: str, limit: int) -> str:
    """取前 `limit` 个字符，但**尽量在句子边界上收尾**。

    为什么需要它：开卷要给模型看"风格卡（正文前 4000 字）"与
    "前情对齐（每章前 1500 字）"（见 `ingest/style.py` / `ingest/progress.py`）。
    直接 `text[:4000]` 会**截在半句上** —— 而模型读到的最后那句是残的，
    它照样会照着这个"风格"往下写（**残句在它眼里也是一种句式**）。
    所以在句子边界收尾。

    ★ 允许**回退的底线是 40%**（`lim*0.4`）：退得比这还多就等于白给预算，
      那时候宁可交一个略超预算的整句，也不交半句。
    
        English:
    Take the first `limit` characters, but **try to end on a sentence boundary**.
        Why it is needed: book-opening requires showing the model the "style card (first 4000 chars of body)" and
        "preceding-context alignment (first 1500 chars of each chapter)" (see `ingest/style.py` / `ingest/progress.py`).
        Plain `text[:4000]` would **cut mid-sentence** — and the last sentence the model reads is truncated,
        yet it will still keep writing in that "style" (**a truncated sentence is, in its eyes, also a sentence pattern**).
        So end on a sentence boundary.
        ★ The allowed **fallback floor is 40%** (`lim*0.4`): backing off more than that is as good as wasting the budget,
          in that case better to hand over a whole sentence slightly over budget than half a sentence.
    """
    src = str(text or '')
    lim = max(0, int(limit))
    if len(src) <= lim:
        return src
    head = src[:lim]
    if head and head[-1] in _SENT_END:
        return head
    floor = int(lim * 0.4)
    for i in range(len(head) - 1, floor - 1, -1):
        if head[i] in '。！？!?…':
            return head[:i + 1]                 # 收到上一句句末，宁可少几十字
            # [EN] cut at the previous sentence end, better a few dozen characters short
    nl = head.rfind('\n', floor)
    if nl > 0:
        return head[:nl]
    return head


def tail_sentences(text: str, limit: int) -> str:
    """取**末尾** `limit` 个字符，但**尽量在句子边界上起头**（`head_sentences` 的镜像）。

    为什么需要它（2026-10-28，用户：「导入故事的时候包含一部分之前故事的
    提要和之前故事的最后部分」）：正文对齐原来只给每章**前** 1500 字 ——
    一部长篇的**结局**在最后一章的**末尾**，模型从头到尾没见过它，
    于是「前情提要」停在倒数第二章的半中间，推演起点自然对不上。
    直接 `text[-500:]` 会**从半句中间开始** —— 模型读到的第一句是残的，
    它会把残句当成"故事就停在这"。所以从句子边界起头。

    ★ 允许**回退的底线是 40%**（与 `head_sentences` 同一个口径）。
    [EN] Take the **last** `limit` characters but try to **start on a sentence boundary**
    [EN] (mirror of `head_sentences`). Needed because body alignment only fed the **first**
    [EN] 1500 chars per chapter -- the ending of a long story sits at the **tail** of the last
    [EN] chapter, so the recap always stopped mid-previous-chapter. Cutting `text[-500:]`
    [EN] would start mid-sentence; same 40% floor as `head_sentences`.
    """
    src = str(text or '').strip()
    lim = max(0, int(limit))
    if len(src) <= lim:
        return src
    tail = src[-lim:]
    # 起点越**早**保留越多 —— 要的是**第一个**句末标点之后的那个字，
    # 且起点不得早于 floor（再早就丢掉超过 60% 预算，等于白给）。
    # 省略号「……」占两个字：落在半个省略号上不算句末。
    # [EN] The earlier the start, the more is kept -- take the char right after the **first**
    # [EN] sentence-end punctuation, no earlier than the floor; half an ellipsis is not a boundary.
    floor = len(tail) - int(lim * 0.4)
    for i in range(len(tail)):
        if tail[i] in '。！？!?…':
            if i + 1 < len(tail) and tail[i + 1] == '…':
                continue                      # 省略号的前半个，不是句末
            # [EN] the first half of an ellipsis is not a sentence end
            if i + 1 <= floor:
                return tail[i + 1:].lstrip('　 \n')
            break                             # 残句太长（>60% 预算）→ 整段照给，宁超勿残
            # [EN] the dangling sentence is too long -> hand over the whole tail
    return tail

