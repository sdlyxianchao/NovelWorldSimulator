# -*- coding: utf-8 -*-
"""以《使用说明》为根据的使用问答（帮助面板的「问个问题」）。

为什么单独一层
--------------
用户要的是「点开帮助，直接问使用上的问题，后台**以使用文档为基础**回答」。
这里的要害不是"接一个聊天框"，而是**回答的根据必须是说明书本身**：
说明书里没写的，就得说没写 —— 不许拿一般常识补一个这个软件根本没有的功能。
用户会照着答案去点，点了找不到就是坑；而"文档问答"最容易翻车的正是这一点。

三件事，都很朴素：

  ① **切段** —— 按 `##` / `###` / `####` 切开，并带上**父级标题路径**
     （`6. 输入文件夹标准 › 6.6 顶级规则`）。说明书结构规整，一个三级标题
     差不多正好是"一个问题一个落点"。
  ② **检索** —— 纯本地、**零成本**：标题命中权重高，正文用二元组重叠
     （`store.db.tokens`）。没有向量库、不联网：说明书是**自带**的、体量有限
     （一千八百行），本地打分够用，还省一次 embedding 的钱。
  ③ **回答** —— 只把检索到的段落喂给模型，并要求它给出「依据」。

检索为空时**不发请求**，直接告诉用户"说明书里没找到相关的章节" ——
让模型在"什么都没给它"的情况下自由发挥，是这类功能最不该做的事。

English:
Why a separate layer
--------------
What the user wants is "open help, directly ask a usage question, and have the backend **answer
based on the usage documentation**".
The key here is not "hook up a chat box", but that **the basis of the answer must be the manual
itself**:
what is not written in the manual must be said to be not written — it is not allowed to use
general common sense to patch in a feature this software simply doesn't have.
The user will click according to the answer; if they can't find it after clicking, that's a
trap; and "document Q&A" is exactly where this most easily goes wrong.
Three things, all very plain:
  ① **Split into sections** — split by `##` / `###` / `####`, and carry the **parent heading path**
     is roughly exactly "one question, one anchor point".
  ② **Retrieval** — purely local, **zero cost**: heading hits have high weight, body text uses bigram overlap
     (`store.db.tokens`). No vector store, no network: the manual is **bundled**, and its size is limited
     (1800 lines), so local scoring is enough, and it saves an embedding cost too.
  ③ **Answer** — feed only the retrieved paragraphs to the model, and require it to give 「依据」.
When retrieval is empty, **do not send a request**; directly tell the user "no relevant section
was found in the manual" —
letting the model freewheel when "nothing was given to it" is the last thing this kind of
feature should do.
"""
from __future__ import annotations

import re
from pathlib import Path

from config import CFG
from i18n import t
from llm.router import llm
from logger import log_dir
from store.db import tokens

_LOG = __import__("logging").getLogger("nws.manual_qa")

APP_DIR = Path(__file__).resolve().parent.parent

# 说明书按界面语言选（两份内容对应，但不保证逐句一致）
# [EN] Manuals are selected by UI language (the two copies correspond in content, but are not
# [EN] guaranteed to match sentence by sentence)
MANUAL_NAME = {"zh": "使用说明.md", "en": "User_Manual.md"}

# ── 多轮对话（2026-10-06：问问题改成聊天式之后加的）────────────────
# 聊天界面里会有追问（"那怎么改？""在哪里点？"）。两件事要分清：
#   · **发给模型的**：带上最近几轮，否则"那怎么改"里的"那"指什么它不知道；
#   · **检索用的**：只在**当前问题自己说不清**（片段太少）时才借用上一轮的问题，
#     否则正常提问会被上一轮的话题带偏。
HISTORY_MAX_TURNS = 3        # 最多带几轮（一轮 = 问 + 答）
HISTORY_MAX_CHARS = 400      # 每轮问题 / 回答各截多少字
# [EN] ── Multi-turn conversation (2026-10-06: added after changing Q&A to chat style) ────────────────
# [EN] In the chat UI there will be follow-up questions ("then how do I change it?" "where do I
# [EN] click?"). Two things need to be distinguished:
# [EN] · **What is sent to the model**: include the last few turns, otherwise it doesn't know what
# [EN] "that" in "then how do I change that" refers to;
# [EN] · **What is used for retrieval**: only borrow the previous turn's question when **the current
# [EN] question itself is unclear** (too few fragments),
# [EN] otherwise a normal question will be led astray by the previous turn's topic.
# [EN] How many turns to include at most (one turn = question + answer)
# [EN] How many characters to truncate each turn's question / answer to

# 一次问答最多喂多少字（说明书单节最长约 8 千字，取 4 节就可能上万）
# [EN] How many characters to feed at most for one Q&A (the longest single section of the manual is
# [EN] about 8k characters, taking 4 sections can easily exceed 10k)
MAX_CONTEXT_CHARS = 6000
DEFAULT_TOP_K = 5

# ── 阈值：**宁可宽，不可漏** ─────────────────────────────────────────
# 这里的取舍是明确的：检索层只是"把可能相关的章节挑出来"，**判断相关性是模型的活**
# （prompt 里明确要求"没写就说没写"）。所以：
#   · 漏命中 = 用户得不到答案（体验直接坏掉）；
#   · 多给一节 = 多花一点 token，模型看了会说"这跟问题无关"。
# 两害相权，门槛偏松。唯一要挡住的是"**整句问题只有一个片段碰巧撞上**"那种噪声。
# [EN] ── Thresholds: **better loose than miss** ─────────────────────────────────────────
# [EN] The tradeoff here is clear: the retrieval layer only "picks out possibly relevant sections";
# [EN] **judging relevance is the model's job**
# [EN] (the prompt explicitly requires "if it's not written, say it's not written"). So:
# [EN] · Missed hit = the user gets no answer (the experience is directly ruined);
# [EN] · Giving one extra section = spending a bit more tokens; the model will look and say "this is
# [EN] irrelevant to the question".
# [EN] Weighing the two harms, the threshold leans loose. The only thing to block is that kind of noise
# [EN] where "**a whole-sentence question has only one fragment that happens to hit**".
MIN_SCORE = 0.5
# 覆盖率：问题里的片段至少这么多比例能在这一节里找到。
# 只有一个片段的问题（"怎么开卷"）要求 **100%** —— 否则"你好""谢谢"也会撞进来。
# [EN] Coverage: at least this proportion of the fragments in the question can be found in this
# [EN] section.
# [EN] A question with only one fragment ("how to open a scroll") requires **100%** — otherwise "hello"
# [EN] and "thanks" would also hit.
MIN_COVER = 0.34
MIN_COVER_SINGLE = 1.0

# ── 问题侧要丢掉的词 ─────────────────────────────────────────────────
# 为什么要丢：`tokens("今天天气怎么样")` 里有「怎么」这种**任何问题都会带**的片段，
# 跟说明书里满地的「怎么办」一碰就命中 —— 结果是"跟软件毫无关系的问题"也能
# 检索出三节内容来（实测就是这样）。文档问答最怕这种**看起来很努力**的假命中：
# 模型拿到三节不相干的东西，还要硬着头皮回答。
# [EN] ── Words to drop on the question side ─────────────────────────────────────────────────
# [EN] which hit immediately upon touching the 「怎么办」 scattered all over the manual — the result is that
# [EN] "questions with no relation to the software at all" can also
# [EN] retrieve three sections of content (this is what actually happens in testing). Document Q&A
# [EN] fears most this kind of **seemingly hardworking** false hit:
# [EN] the model gets three irrelevant sections and still has to grit its teeth and answer.
_STOP = {
    "怎么", "什么", "如何", "哪个", "哪些", "哪里", "是否", "可以", "能不能",
    "有没有", "为什么", "怎样", "咋", "请问", "麻烦", "帮我", "告诉",
    "how", "what", "where", "which", "when", "who", "why", "can", "could",
    "the", "is", "are", "was", "were", "do", "does", "did", "to", "of", "in",
    "on", "for", "and", "or", "it", "this", "that", "please",
}

# ── 提示词 ───────────────────────────────────────────────────────────
# 中文（说明书正文是中文，问题多半也是中文）
# [EN] ── Prompt ───────────────────────────────────────────────────────────
# [EN] Chinese (the manual body is in Chinese, and questions are mostly in Chinese too)
_PROMPT_ZH = """你是「小说世界AI模拟」的使用助手。下面是从随程序附带的《使用说明》里挑出的**可能相关**的章节。

请**只根据这些内容**回答用户的问题。硬要求：

- 说明书里没有写到的，**直接说**「《使用说明》里没有写这一条」，并说清去哪儿找
  （帮助面板的目录，或程序目录下的《使用说明.md》）。
- **不要**凭一般常识补充这个软件没有的功能。用户会照着做，做不到就是坑。
- 提到设置项时写出**键名**（如 `RUN_MODE`）；提到界面位置时写清路径（如「天机 · 界面外观」）。
- 回答简短、分点，不写客套话。
- 最后另起一行，写「依据：」并列出你用到的小节名（照抄上面的标题）。

【相关章节】
{context}
{history}
【用户的问题】
{question}"""

_PROMPT_EN = """You are the usage assistant for "小说世界AI模拟 / Novel World AI Simulator".
Below are the chapters of the bundled User Manual that look**possibly relevant**.

Answer the user's question using**only these chapters**. Hard requirements:

- If the manual does not cover it,**say so plainly** ("The manual does not cover this"),
  and point to where to look (the Help panel's table of contents, or `User_Manual.md`
  in the program folder).
- **Do not** invent features from general knowledge. The user will follow your answer,
  and anything that does not exist is a trap.
- When mentioning a setting, give its**key name** (e.g. `RUN_MODE`); when mentioning a
  place in the UI, give the full path (e.g. "Settings · Appearance").
- Keep it short and use bullets; no pleasantries.
- End with a separate line "依据：" listing the section titles you used (copy them above).

【Relevant chapters】
{context}
{history}
【User question】
{question}"""

# 追问那段。注意措辞 —— 不写这句，模型会**回头把上一轮的问题再答一遍**。
# [EN] The follow-up part. Watch the wording — without this sentence, the model will **turn back and
# [EN] answer the previous turn's question again**.
_HISTORY_ZH = """【此前对话】（只用来理解这次的追问，不要回头重答旧问题）
{lines}
"""
_HISTORY_EN = """【Earlier conversation】(only to understand this follow-up; do not re-answer old questions)
{lines}
"""


# ══════════════════════════════════════════════════════════════
#  ① 读 + 切段
# [EN] ① Read + split into sections
# ══════════════════════════════════════════════════════════════
def manual_path(lang: str = "zh") -> Path:
    return APP_DIR / MANUAL_NAME.get(lang, MANUAL_NAME["zh"])


def _split_sections(text: str) -> list[dict]:
    """按 `##`~`####` 切段，`title` 是**带父级的路径**（`A › B › C`）。

    为什么带父级：光看「4.5.0 第 2 步的项目名称与三个下拉框」不知道在讲哪一步；
    带上「4.5 开卷对话框（导入向导）›」之后，模型引用时也不会张冠李戴。

    ★ 实现搬到 `util.md.split_sections()`（2026-10-06）：以前这里的正则
    **不认代码围栏**，而 `使用说明.md` §4.2.4 的 ```markdown 示例块里有
    `## 登场人物` —— 于是检索结果里出现 `登场人物 › 4.8 书斋对话框 › …`
    这种假路径，模型照着引用就张冠李戴。同一个 bug 在
    `gui.app_flet.read_manual()` 里还有一份，两处统一到 `util.md`。
    
        English:
    Split sections by `##`~`####`; `title` is a **path with parents** (`A › B › C`).
        ★ Implementation moved to `util.md.split_sections()` (2026-10-06): the regex here previously
        **did not recognize code fences**, and the ```markdown example block in `使用说明.md` §4.2.4 contains
        and the model misattributed things when citing them. The same bug has another copy in
        `gui.app_flet.read_manual()`; both are unified into `util.md`.
    """
    from util.md import split_sections
    return split_sections(text)


_SECTION_CACHE: dict[str, list[dict]] = {}


def load_sections(lang: str = "zh", *, reload: bool = False) -> list[dict]:
    """读说明书并切段（按语言缓存；`reload=True` 强制重读）。
        English:
    Read the manual and split it into sections (cached by language; `reload=True` forces a re-read).
    """
    if not reload and lang in _SECTION_CACHE:
        return _SECTION_CACHE[lang]
    p = manual_path(lang)
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        _LOG.warning("读不到说明书 %s: %s", p, e)
        _SECTION_CACHE[lang] = []
        return []
    secs = _split_sections(text)
    _SECTION_CACHE[lang] = secs
    _LOG.info("说明书已切段：%s → %d 节", p.name, len(secs))
    return secs


# ══════════════════════════════════════════════════════════════
#  ② 检索（本地、零成本）
# [EN] ② Retrieval (local, zero cost)
# ══════════════════════════════════════════════════════════════
def _query_terms(question: str) -> set[str]:
    """问题侧的检索片段：**先去虚词、再丢掉单字**。

    两遍都要：
      · **先在整句上剔掉疑问词**（`"前情提要是什么"` → `"前情提要"`）——
        不先做这一步，分词会把「是什」「什么」这类边界二元组留下来（"什么"
        在停用词表里，但"是什"不在）。
      · 再丢掉长度 < 2 的片段（中文单字"有""的""几"在检索里全是噪声）。
    
        English:
    Retrieval fragments on the question side: **first remove function words, then drop single
    characters**.
        Both passes are needed:
            is in the stopword list, but "是什" is not).
          · Then drop fragments with length < 2 (single Chinese characters like "有", "的", "几" are all noise in retrieval).
    """
    s = str(question or "")
    for w in sorted(_STOP, key=len, reverse=True):          # 长词先替，避免"怎么样"被"怎么"先吃掉
    # [EN] Replace long words first, to avoid "怎么样" being eaten by "怎么" first
        s = s.replace(w, " ")
    return {x for x in tokens(s) if len(x) >= 2 and x not in _STOP}


def search(question: str, lang: str = "zh", *, top_k: int = DEFAULT_TOP_K,
           max_chars: int = MAX_CONTEXT_CHARS) -> list[dict]:
    """在说明书里找相关章节。

    两道闸门（先覆盖率、再打分），都是"宁可漏，不可滥"：

      · **覆盖率 ≥ `MIN_COVER`** —— 问题里一半以上的片段要能在这一节里找到。
        这是比总分更本质的一道：`「1+1等于几」` 能靠一个「等于」蹭到 0.5 分，
        但覆盖率只有 1/5，进不来。
      · 分数 ≥ `MIN_SCORE`，分数 = 标题命中 × 3 + 正文命中 × 1
        （标题是作者亲手写的"这一节讲什么"，最该信），
        问题原句**整句出现**再加 2 分（用户往往直接抄界面上的词）。

    返回的每项带 `score`；`body` 可能被截断（注明"其余部分略"）——
    总长压在 `max_chars` 以内，避免把说明书半本塞进一次请求。
    
        English:
    Find the relevant section in the manual.
        Two gates (coverage first, then score), both follow "rather miss than over-include":
          · **Coverage ≥ `MIN_COVER`** —— more than half of the fragments in the question must be found in this section.
            This is a more essential gate than total score: `「1+1等于几」` can ride a single 「等于」 to a 0.5 score,
            but coverage is only 1/5, so it does not get in.
          · Score ≥ `MIN_SCORE`, score = title hits × 3 + body hits × 1
            (the title is the author's own "what this section covers", most trustworthy),
            plus 2 points if the question's **entire sentence appears** (users often copy the exact wording from the UI).
        Each returned item carries `score`; `body` may be truncated (noted as "其余部分略") ——
        total length is kept within `max_chars`, to avoid stuffing half the manual into one request.
    """
    q = _query_terms(question)
    if not q:
        _LOG.info("说明书检索：问题全是虚词，不检索（%r）", question[:30])
        return []
    need_cover = MIN_COVER_SINGLE if len(q) == 1 else MIN_COVER
    qtext = str(question or "").strip()
    scored: list[dict] = []
    for sec in load_sections(lang):
        tt, bt = tokens(sec["title"]), tokens(sec["body"])
        if len(q & (tt | bt)) / len(q) < need_cover:
            continue
        # ★★★ 2026-10-14：**第三道闸门 —— 标题至少要命中一个查询词**。
        #   用户报的现象：问「今天天气怎么样」，界面照样端出三节《主界面详解》。
        #   根因是**二连切词**把「今天天气」切成 `{今天, 天天, 天气}`，而正文里
        #   刚好有「今天」「天气」这两个词 ⇒ 覆盖率 2/3 = 0.667 过了第一道闸门，
        #   分数 1×2/3 = 0.667 又过了第二道 —— 可它跟这本软件**毫无关系**。
        #   ⇒ 加一道：这一节**标题**里至少要出现一个查询词。
        #     标题是作者亲手写的"这一节讲什么"（本函数注释里本来就写着
        #     "标题最该信"），拿它当门槛最本质，也不用去维护一张
        #     "今天/天气/晚饭/电影…"的无限停用词表。
        #   ★ 实测（8 条正例 × 5 条反例）：加闸门前 正例 0 漏 / 反例命中 1；
        #     加闸门后 **正例 0 漏 / 反例 0 命中**（`tools/verify_help_qa.py` A3/A7 钉着）。
        #   ★ 例外：**问题原句整句出现在这一节里**时放行（下方 `exact`）——
        #     那是"用户直接抄了界面上/文档里的原话"的强信号，比标题闸门更硬；
        #     而且这种问题对**英文**同样成立（`What is the weather today?` 之前
        #     也会命中，同一个根因）。
        # [EN] ★★★ 2026-10-14: **a third gate -- the title must hit at least one query term**.
        # [EN] What the user reported: asking "今天天气怎么样" (what's the weather today) still
        # [EN] served up three sections of "Main Interface Explained".
        # [EN] Root cause: bigram tokenization splits 「今天天气」 into `{今天, 天天, 天气}`, and the
        # [EN] body happens to contain 「今天」 and 「天气」 => coverage 2/3 = 0.667 passes the first
        # [EN] gate, score 1x2/3 = 0.667 passes the second -- yet it has **nothing to do with this
        # [EN] software**.
        # [EN] => Add a gate: this section's **title** must contain at least one query term.
        # [EN]   The title is the author's own "what this section covers" (this function's docstring
        # [EN]   already says "the title is the most trustworthy"), making it the most essential
        # [EN]   threshold -- and it avoids maintaining an endless stop word list of
        # [EN]   "today/weather/dinner/movie...".
        # [EN] ★ Measured (8 positive x 5 negative cases): before the gate, positives 0 missed /
        # [EN]   negatives 1 hit; after the gate, **positives 0 missed / negatives 0 hit**
        # [EN]   (pinned by A3/A7 of `tools/verify_help_qa.py`).
        # [EN] ★ Exception: when the **whole question sentence appears verbatim** in this section,
        # [EN]   let it through (the `exact` flag below) -- that is a strong signal of "the user
        # [EN]   copied the exact wording from the UI/docs", stronger than the title gate; and the
        # [EN]   same problem occurs for **English** (`What is the weather today?` also matched
        # [EN]   before, same root cause).
        exact = bool(qtext) and len(qtext) >= 2 and qtext in (sec["title"] + "\n" + sec["body"])
        if not (q & tt) and not exact:
            continue
        score = (3.0 * (len(q & tt) / len(q))
                 + 1.0 * (len(q & bt) / len(q)))
        if exact:
            score += 2.0
        if score >= MIN_SCORE:
            scored.append({**sec, "score": round(score, 3)})
    scored.sort(key=lambda x: -x["score"])

    out: list[dict] = []
    used = 0
    for s in scored[:max(1, top_k)]:
        room = max_chars - used
        if room < 200:
            break
        body = s["body"]
        if len(body) > room:
            body = body[:room].rstrip() + "\n…（本节其余部分略）"
        out.append({**s, "body": body})
        used += len(body)
    _LOG.info("说明书检索「%s」→ 命中 %d 节（候选 %d）",
              question[:30], len(out), len(scored))
    return out


# ══════════════════════════════════════════════════════════════
#  ③ 回答
# [EN] ③ Answer
# ══════════════════════════════════════════════════════════════
def _history_text(history, lang: str = "zh") -> str:
    """把最近几轮对话拼成一段（**只给模型看**，不参与检索）。

    `history` 形如 `[{'role': 'user'|'assistant', 'content': str}, …]`，
    是聊天界面自己攒的。截断规则：只取最后 `HISTORY_MAX_TURNS` 轮、
    每段最多 `HISTORY_MAX_CHARS` 字 —— 聊天可以很长，但喂进 prompt 的部分
    必须**有界**（否则聊到二三十轮时，光历史就把上下文吃光了）。
    
        English:
    Concatenate the most recent few turns of dialogue into one block (**only shown to the model**,
    not used for retrieval).
        `history` has the form `[{'role': 'user'|'assistant', 'content': str}, …]`,
        accumulated by the chat UI itself. Truncation rule: take only the last `HISTORY_MAX_TURNS` turns,
        each at most `HISTORY_MAX_CHARS` characters —— the chat can be long, but the part fed into the prompt
        must be **bounded** (otherwise after twenty or thirty turns, history alone eats up the context).
    """
    if not history:
        return ""
    tag_q, tag_a = ("问", "答") if lang == "zh" else ("Q", "A")
    lines: list[str] = []
    for item in list(history)[-(HISTORY_MAX_TURNS * 2):]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        text = str(item.get("content") or "").strip().replace("\n", " ")
        if not text:
            continue
        text = text[:HISTORY_MAX_CHARS] + ("…" if len(text) > HISTORY_MAX_CHARS else "")
        lines.append(f"{tag_q}：{text}" if role == "user" else f"{tag_a}：{text}")
    if not lines:
        return ""
    tpl = _HISTORY_ZH if lang == "zh" else _HISTORY_EN
    return tpl.replace("{lines}", "\n".join(lines))


def _search_query(question: str, history) -> str:
    """检索用的查询串：**当前问题自己说不清时**才借上一轮的话。

    判据是"当前问题剔掉虚词后还剩几个片段"：
      · 「那怎么改？」→ 剔完只剩「那」→ 片段太少 → 拼上一轮的问题去检索；
      · 「顶级规则怎么写」→ 够清楚 → **不动**（免得被上一轮话题带偏，
        问到第三个问题时检索还在命中第一个问题的章节）。
    
        English:
    Query string for retrieval: only borrow the previous turn's words **when the current question
    cannot express itself clearly**.
        The criterion is "how many fragments remain after removing function words from the current question":
          · 「那怎么改？」 → after removal only 「那」 remains → too few fragments → prepend the previous turn's question for retrieval;
            so that by the third question, retrieval is still hitting the section of the first question).
    """
    if len(_query_terms(question)) >= 2 or not history:
        return question
    last_q = ""
    for item in reversed(list(history)):
        if isinstance(item, dict) and str(item.get("role")) == "user":
            last_q = str(item.get("content") or "").strip()
            break
    return f"{last_q} {question}".strip() if last_q else question


def build_prompt(question: str, hits: list[dict], lang: str = "zh",
                 history=None) -> str:
    """把命中段落拼成 prompt。**只有这一处拼**（判据直接查它）。
        English:
    Concatenate the hit paragraphs into the prompt. **Only concatenated here** (criteria query it
    directly).
    """
    context = "\n\n".join(f"## {h['title']}\n{h['body']}" for h in hits)
    tpl = _PROMPT_ZH if lang == "zh" else _PROMPT_EN
    return (tpl.replace("{context}", context)
               .replace("{history}", _history_text(history, lang))
               .replace("{question}", str(question)))


async def answer(question: str, lang: str = "zh", *, top_k: int = DEFAULT_TOP_K,
                 history=None) -> dict:
    """回答问题。返回 `{'ok', 'text', 'sources', 'why'}`。

    `ok=False` 表示**这次没答成**（没命中 / 调用失败）——调用方要把 `text`
    原样显示（它已经是给人看的一句话），别把它吞掉换成"出错了"。
    `history` 是多轮对话（聊天界面传进来的最近几轮），只影响 prompt 与检索，
    不影响"检索为空就不发请求"这条硬规矩。
    
        English:
    Answer the question. Return `{'ok', 'text', 'sources', 'why'}`.
        `ok=False` means **this attempt did not succeed** (no hits / call failed) —— the caller must display `text`
        as-is (it is already a human-readable sentence), do not swallow it and replace it with "出错了".
        `history` is the multi-turn dialogue (the most recent turns passed in by the chat UI), affecting only the prompt and retrieval,
        not the hard rule "if retrieval is empty, do not send a request".
    """
    question = str(question or "").strip()
    if not question:
        return {"ok": False, "text": t("先写下你的问题"), "sources": [], "why": "empty"}

    hits = search(_search_query(question, history), lang, top_k=top_k)
    sources = [h["title"] for h in hits]
    if not hits:
        # ⚠ 检索为空时**不发请求**：什么都不给模型、又让它回答，等于让它编。
        # [EN] ⚠ When retrieval is empty, **do not send a request**: giving the model nothing and still asking
        # [EN] it to answer is equivalent to asking it to make things up.
        return {"ok": False, "why": "no_hit", "sources": [],
                "text": t("《使用说明》里没有找到和这个问题相关的章节。"
                          "换个说法再问一次，或者打开帮助面板翻目录会更准。")}

    try:
        await llm.ensure_started(log_dir())
    except Exception as e:                                   # noqa: BLE001
        _LOG.warning("LLM 初始化失败：%r", e)

    prompt = build_prompt(question, hits, lang, history=history)
    try:
        text = await llm.chat("cheap", [{"role": "user", "content": prompt}],
                              purpose="help_qa", temperature=0.2)
    except Exception as e:                                   # noqa: BLE001
        _LOG.warning("说明书问答调用失败：%r", e)
        return {"ok": False, "why": "call_failed", "sources": sources,
                "text": t("这次没能问到模型（{e}）。可以稍后再试，"
                          "或直接看下面的相关章节。", e=str(e)[:80])}

    if isinstance(text, (list, tuple)):        # 别假设下游一定给 str
    # [EN] Don't assume downstream definitely gives a str
        text = " ".join(str(x) for x in text if str(x).strip())
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "why": "empty_reply", "sources": sources,
                "text": t("模型这次没有给出内容。换个说法再问一次试试。")}
    return {"ok": True, "text": text, "sources": sources, "why": ""}


def format_answer(res: dict) -> str:
    """把结果拼成给用户看的一段 Markdown（回答 + 依据）。
        English:
    Concatenate the result into a Markdown block shown to the user (answer + evidence).
    """
    parts = [str(res.get("text") or "").strip()]
    src = [s for s in (res.get("sources") or []) if s]
    if src and "依据" not in parts[0][-40:]:
        # 模型自己写了「依据」就不重复（它是照标题抄的，通常更贴题）
        # [EN] If the model writes 「依据」 itself, don't repeat it (it copied from the heading, which is usually
        # [EN] more on-topic)
        parts.append("\n---\n" + t("**参考章节**：") + " · ".join(src))
    return "\n".join(p for p in parts if p)
