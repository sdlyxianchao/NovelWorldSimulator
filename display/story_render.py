# -*- coding: utf-8 -*-
"""把词条写成**小说体**（运行窗口的中栏用它；落盘仍是剧本格式）。

为什么要有这一层
----------------
`script_render` 那套是**给剧本看的**：一条词条一行、带类型标记
（`〔心声·阿枝〕`、`· 动作`、`〔出场〕`），台词写成 `主角：今夜别出门。`。
它结构清楚、**可反解**，落盘与导出就该是那个样子 —— 一个字都别动
（`parse_markdown` 认的就是它，见 `剧本输出格式.md`）。

但中栏里逐条滚出来的样子，读起来像在看场记单而不是在看小说。用户的原话
（2026-10-06）是「有点过于倾向于剧本了，优化一下让他更像一点故事」。

所以这一层只干一件事 —— **把同一批词条写成小说该有的样子**：

| 原来（剧本体） | 现在（小说体） |
|---|---|
| `主角（压低声音）对阿枝：今夜别出门。` | `主角压低声音，对阿枝说：「今夜别出门。」` |
| `主角：把壶放下` | `主角把壶放下。` |
| `〔心声·阿枝〕他今天不对劲。` | `阿枝心想：他今天不对劲。` |
| `〔回想·主角〕那年也是这样的雨。` | `主角想起，那年也是这样的雨。` |
| `〔出场〕主角（入画）` | `主角走了进来。` |
| `〔片刻无话〕` | `片刻无话。` |
| 一条一行、碎成几十行 | **叙述并成段落**，段首缩进两格，台词独立成段 |

**保留剧本标记的**：机制标注（`※`）、结构标记（`〔切至〕`「〔同时〕」）。
它们本来就不是故事内容 —— 把「进度：节点完成」糊进小说正文里才是真的坏。

分工
----
- `sentence(entry)` —— 一条词条 → 小说体的一句
- `group(rows)` —— 一串 `(priority, text, kind)` → 分段（**纯函数**：
  只看序列，不看"什么时候追加的"，所以实时增量与整屏重建得到同样的分段）
- `join_text(...)` / `SPAN_STYLE` —— 一段拼成文本 / 每个 kind 在段内的样式

⚠ 这一层**不调模型**、不猜内容：说话人、语气、对象都是词条里本来就有的字段。

English:
Write the entries in **novel style** (the middle column of the run window uses it; on disk it
stays in script format).
Why this layer exists
----------------
The `script_render` set is **for reading scripts**: one entry per line, with type markers
It's clearly structured and **reverse-parseable**; on-disk and export should look exactly like
that -- not one character changed
But the way it scrolls out line by line in the middle column reads like a continuity sheet, not
a novel. The user's exact words
(2026-10-06) were "it leans a bit too much toward a script, optimize it to feel a bit more like
a story".
So this layer does exactly one thing -- **write the same set of entries the way a novel should
read**:
| Before (script style) | Now (novel style) |
|---|---|
| one per line, shattered into dozens of lines | **merge narration into paragraphs**, indent the paragraph start by two spaces, put dialogue in its own paragraph |
They were never story content to begin with -- smearing "progress: node done" into the novel
text is the real damage.
Division of labor
----
- `sentence(entry)` -- one entry -> one novel-style sentence
- `group(rows)` -- a run of `(priority, text, kind)` -> paragraphs (**pure function**:
  looks only at the sequence, not at "when it was appended", so live increment and full-screen rebuild produce the same paragraphs)
- `join_text(...)` / `SPAN_STYLE` -- join a paragraph into text / style of each kind within the paragraph
⚠ This layer **does not call the model** and does not guess content: speaker, tone, and
addressee are all fields already present in the entry.
"""
from __future__ import annotations

from i18n import is_en, t

from crew import doing as DO
from display import script as S

# ── 哪些词条能并进同一段 ────────────────────────────────────────────────
#   叙述类的（旁白/环境/动作/回想/心声/出场退场/停顿）互相之间是
#   **同一段话的连续句子**，小说里不会一句一换行。
#   台词**不并**：中文小说的对话本来就独立成段，这是排版规矩不是风格偏好。
#   导演事件也**不并**：它是转折点，小说里另起一段才有那个顿挫。
# [EN] ── Which entries can be merged into the same paragraph
# [EN] ────────────────────────────────────────────────
# [EN] Narration types (narration/environment/action/recollection/inner voice/entrance exit/pause) are
# [EN] mutually
# [EN] **consecutive sentences of the same paragraph**, a novel does not break lines every sentence.
# [EN] Dialogue is **not merged**: dialogue in Chinese novels is naturally its own paragraph, this is a
# [EN] typesetting rule not a style preference.
# [EN] Director events are also **not merged**: it is a turning point, in a novel a new paragraph is
# [EN] what gives that beat.
JOINABLE = frozenset({S.NARRATION, S.AMBIENT, S.ACTION, S.RECALL, S.ASIDE,
                      S.ENTER, S.EXIT, S.BEAT})

# 段首**不缩进**的：台词（对话不缩进）· 机制标注（它不是故事）·
# 结构标记（切至/同时/插图 —— 它们是版面上的路标）·
# 前情提要（它是一整块回顾，缩进两格会让人以为它是正文的第一句）。
# [EN] Paragraphs **not indented** at the start: dialogue (dialogue is not indented) · mechanic
# [EN] annotations (it is not story) ·
# [EN] structural markers (cut to/meanwhile/illustration —— they are signposts on the layout) ·
# [EN] recap (it is a whole block of review, indenting two spaces would make people think it is the
# [EN] first sentence of the body).
NON_INDENT = frozenset({S.DIALOGUE, S.NOTE, S.CUT, S.CUT_BACK, S.PARALLEL,
                        S.IMAGE, S.RECAP, S.BRIEF, S.STAGE, S.CREW, S.SUMMARY})

# 一段最多几句话。小说里的段落有长短，但**一路并下去**会长成一整屏不分段
# 的一大坨 —— 那是另一种难看。4 句是个保守的软上限（不是硬规矩：
# 遇到台词/事件/分隔符照样提前断）。
# [EN] A paragraph has at most a few sentences. Paragraphs in novels vary in length, but **merging all
# [EN] the way** will grow into a full screen without breaks
# [EN] a big blob —— that is another kind of ugliness. 4 sentences is a conservative soft cap (not a
# [EN] hard rule:
# [EN] when hitting dialogue/event/separator still break early).
PARA_MAX_SENTENCES = 4

# 段首缩进（中文排版：首行缩进两格）。用全角空格实现 ——
# 交给渲染层去算"首行"是做不到的（Flet 没有首行缩进），而全角空格是正路。
# [EN] Paragraph first-line indent (Chinese typesetting: first line indented two spaces). Implemented
# [EN] with full-width spaces ——
# [EN] letting the render layer compute "first line" is not doable (Flet has no first-line indent), and
# [EN] full-width spaces are the proper way.
PARA_INDENT = '　　'

# 段内每个 kind 的样式：(颜色键, 斜体)。
# 颜色键取 `gui/app_flet.py` 的 `C` 字典 —— 这里是**语义**，由 GUI 翻译成颜色。
# [EN] Style of each kind within a paragraph: (color key, italic).
# [EN] Color keys take the `C` dict in `gui/app_flet.py` —— here it is **semantic**, the GUI translates
# [EN] it into color.
#
# ⚠ **键集合必须与 `JOINABLE` 完全一致**（判据 A5d 钉着这条）：
#   少配一个 → 它在段落里会走默认（正文色），而"忘了配"和"故意要正文色"
#   在屏幕上长得一样，事后查不出来。
# [EN] ⚠ **The key set must be exactly the same as `JOINABLE`** (criterion A5d pins this):
# [EN] missing one → it will use the default (body color) in the paragraph, and "forgot to configure"
# [EN] and "intentionally want body color"
# [EN] look the same on screen, cannot be traced afterward.
SPAN_STYLE: dict[str, tuple[str, bool]] = {
    S.NARRATION: ('text', False),
    S.ACTION: ('text', False),        # 动作就是正文（"人物在做事"不该是小字）
    S.AMBIENT: ('muted', False),      # 环境白描：比正文淡，退到后面去
    S.ASIDE: ('muted', True),         # 心声：淡 + 斜体
    S.RECALL: ('gold', True),         # 回想：赭金 + 斜体（与"当下心声"分开）
    S.ENTER: ('muted', False),        # 出场：是"谁进来了"的提示，别跟正文抢
    # [EN] Action is body text ("characters doing things" should not be small text)
    # [EN] Environment description: lighter than body, recedes to the back
    # [EN] Inner voice: light + italic
    # [EN] Recollection: ochre gold + italic (separated from "present inner voice")
    # [EN] Entrance: is a hint of "who came in", do not compete with body text
    S.EXIT: ('muted', False),
    S.BEAT: ('muted', False),         # 停顿：淡
    # [EN] Pause: light
}

# 句末标点（没有就补一个，免得段落里两句粘在一起）。
# ⚠ **不含逗号顿号**：那些是句中停顿，拿它们当"这句已经完了"会让
#   `主角把壶放下，` 这种半句话留在段落里。
# [EN] Sentence-ending punctuation (add one if missing, so two sentences in a paragraph do not stick
# [EN] together).
# [EN] ⚠ **Does not include commas or enumeration commas**: those are mid-sentence pauses, using them
# [EN] as "this sentence is done" would make
_END_MARKS = ('。', '！', '？', '…', '」', '〕', '!', '?', '.')
_QUOTES = '「」“”"'


def _clean(s: str) -> str:
    return str(s or '').strip()


def _end(s: str) -> str:
    """句末补标点（已经有就不动）。空串仍是空串。
        English:
    Append end-of-sentence punctuation (leave it alone if it's already there). Empty string stays
    empty string.
    """
    s = s.strip()
    if not s:
        return ''
    return s if s.endswith(_END_MARKS) else s + '。'


def _strip_quotes(s: str) -> str:
    """台词可能自带引号 —— 剥掉再包，免得出现「「…」」。
        English:
    Dialogue may carry its own quotes -- strip them and re-wrap, to avoid `「「…」」`.
    """
    return s.strip().strip(_QUOTES).strip()


def _speech_head(entry) -> str:
    """台词的抬头 —— **剧本体**：`主角：` / `主角：（压低声音，向阿枝）`。

    ★ 2026-10-07 改口径。用户：「正文的格式你参考 老舍的茶馆 进行深度优化」。
      《茶馆》是话剧剧本，台词的样子就是「**人物名：**台词」，舞台提示写在小括号
      里（`王利发：（向李三）…`）—— **不用"他说/她说"这种叙述动词**。
      旧写法 `主角压低声音，对阿枝说：「…」` 是**小说体**，一条条读下来像
      "转述谁说了什么"，而不是"人就站在场上说话"。用户要的正是后者。

    语气与对象都是**词条里本来就有的字段**，一个都不编：
      · `tone`（语气，由情绪推出来）→ 括注在前
      · `to`（对谁说）→ 括注在后

    ⚠ 语气词的实际取值是「语气不善 / 声音发紧 / 声音低下去 / 语气轻快 / 一怔」
      （见 `scene_builder._EMOTION_TONE`）—— 全是**状语/状态**，能安全放进括注。
    
        English:
        ★ 2026-10-07 changed the convention. User: "for the format of the main text, refer to 老舍的茶馆 and optimize it deeply".
          茶馆 is a stage play script; dialogue looks like "**CharacterName:**dialogue", with stage directions written in parentheses
          "relaying who said what", not "a person standing on stage speaking". What the user wants is exactly the latter.
        Tone and addressee are both **fields already present in the entry**; do not invent a single one:
          · `tone` (tone, derived from emotion) -> parenthetical in front
          · `to` (to whom) -> parenthetical after
          (see `scene_builder._EMOTION_TONE`) —— all are **adverbial/state**, safe to put in parenthetical notes.
    """
    who = _clean(getattr(entry, 'speaker', ''))
    tone = _clean(getattr(entry, 'tone', ''))
    to = _clean(getattr(entry, 'to', ''))
    bits = [x for x in (tone, t('向{who}', who=to) if to else '') if x]
    return f'{who}：（{"，".join(bits)}）' if bits else f'{who}：'


def _vis_inline(entry) -> str:
    """「场外 / 别处」这类可见性，写成名字后面的括注。

    ⚠ **这是"同时不同地"看得见的关键**，不能省：`主角（别处）去了后院。`
      读起来是小说，信息也没丢（早期的小说体第一版把它漏掉了 —— 判据当场抓到）。
      中文小说里用括注作补充说明是常见写法，比"在别处的主角…"更省字。
    
        English:
    Visibilities like "offstage / elsewhere" are written as parenthetical notes after the name.
          Reads like a novel, and no information is lost (the early novel-style first draft missed it —— the criterion caught it on the spot).
          Using parenthetical notes for supplementary explanation is common in Chinese novels, more concise than "在别处的主角…".
    """
    from display.script import PRESENT, VISIBILITY_LABEL
    v = str(getattr(entry, 'visibility', PRESENT) or PRESENT)
    if v == PRESENT:
        return ''
    label = VISIBILITY_LABEL.get(v, v)
    return f'（{t(label)}）' if label else ''


def sentence(entry) -> str:
    """一条词条 → **小说体的一句**（可能返回空串：这条不该出现在故事里）。

    只做"换写法"，不做"加内容"：原文一个字不删，只是把场记式的标记
    换成叙述。
    
        English:
    One entry → **one novel-style sentence** (may return empty string: this entry should not appear
    in the story).
        Only "rephrase", not "add content": not a single character of the original is deleted, just replacing the stage-note-style markers
        with narration.
    """
    k = entry.kind
    who = _clean(getattr(entry, 'speaker', ''))
    text = _clean(getattr(entry, 'text', ''))

    if k == S.DIALOGUE:
        # 剧本体：抬头已经带冒号，台词直接接上。
        # **不加引号** —— 引号是小说里为了"把话跟旁白分开"才需要的；
        # 剧本里靠 `谁：` 就分得很清楚了，再加引号反而像转述。
        # [EN] Script form: the header already has a colon, dialogue connects directly.
        # [EN] **No quotes** —— quotes are only needed in novels to "separate speech from narration";
        # [EN] in scripts `谁：` already separates it clearly, adding quotes makes it look like reported speech.
        return _speech_head(entry) + _strip_quotes(text)

    if k == S.ACTION:
        # 舞台提示：写进**括号** —— 剧本里"人在做什么/脸上什么表情"就是这么标的
        # （`王利发：（向李三）…`）。用户明确说过「动作描写…可以不要丢弃」，
        # 所以留着；但要让人**一眼看出这不是台词**，否则它跟对白混在一段里，
        # 读起来还是分不清谁在说话、谁在做动作。
        # [EN] Stage directions: written in **parentheses** —— in scripts "what a person is doing/what
        # [EN] expression on the face" is marked like this
        # [EN] so keep it; but make people **see at a glance that this is not dialogue**, otherwise it mixes
        # [EN] with dialogue in one paragraph,
        # [EN] reading it still cannot tell who is speaking and who is doing action.
        body = f'{who}{_vis_inline(entry)}{text}' if who else text
        return f'（{_end(body)}）' if body.strip() else ''

    if k == S.ASIDE:
        return _end(f'{who}{t("心想：")}{text}' if who else text)

    if k == S.RECALL:
        return _end(f'{who}{t("想起，")}{text}' if who else text)

    if k == S.NARRATION or k == S.AMBIENT:
        return _end(text)

    if k == S.ENTER:
        # `入画` 是场记说法，小说里是"走了进来"；`已在场` 不必说（他本来就在）
        # [EN] `入画` is a script supervisor term, in a novel it is "walked in"; `已在场` need not be said (he was
        # [EN] already there)
        if '已在场' in text or text in ('在场',):
            return ''
        how = text if text and '入画' not in text else t('走了进来')
        return _end(f'{who}{how}')

    if k == S.EXIT:
        how = text if text and '退场' not in text else t('走了出去')
        return _end(f'{who}{how}')

    if k == S.BEAT:
        return _end(text)

    if k == S.EVENT:
        # 导演事件：`【外部刺激】…` → 小说里就是"就在这时，…"
        # 事件类型是给作者看的分类，不进故事正文。
        # [EN] Director event: `【外部刺激】…` → in a novel it is "just then, ..."
        # [EN] Event type is a classification for the author, does not enter the story body.
        body = text
        if body.startswith('【'):
            i = body.find('】')
            if i > 0:
                body = body[i + 1:].strip()
        cap = _clean(getattr(entry, 'caption', ''))
        if not body and cap:
            body = cap
        return _end(f'{t("就在这时，")}{body}' if body else '')

    if k == S.PARALLEL:
        # 同时发生：轨上的每条是「谁在做什么」。小说里用一句话带过。
        # [EN] Simultaneous occurrence: each track is "who is doing what". In a novel use one sentence to cover
        # [EN] it.
        tracks = getattr(entry, 'tracks', None) or []
        bits = [_end(f'{_clean(getattr(x, "subject", ""))}'
                     f'{_clean(getattr(x, "text", ""))}') for x in tracks]
        bits = [b for b in bits if b.strip()]
        return _end(t('同一刻，') + sent_sep().join(bits)) if bits else ''

    if k == S.CUT:
        # ⚠ 结构标记要**带着地点**：`sentence()` 的兜底分支只返回 `entry.text`，
        #   而 cut 的地点存在 `entry.place` 里、note 在 `text` 里 —— 只取 text
        #   会把"切到哪儿去了"丢掉（判据 A5b 当场抓到）。
        # [EN] ⚠ Structural markers must **carry the place**: the fallback branch of `sentence()` only returns
        # [EN] `entry.text`,
        # [EN] while the place of cut is stored in `entry.place`, note is in `text` —— taking only text
        # [EN] would drop "cut to where" (criterion A5b catches it on the spot).
        bits = [x for x in (_clean(getattr(entry, 'place', '')),
                            _clean(text)) if x]
        return f'〔{t("切至")}' + (' · ' + ' · '.join(bits) if bits else '') + '〕'

    if k == S.CUT_BACK:
        place = _clean(getattr(entry, 'place', ''))
        return f'〔{t("切回")}' + (f' · {place}' if place else '') + '〕'

    if k == S.NOTE:
        # 机制标注要留 `※` —— 那是"这不是故事"的唯一视觉信号；
        # 去掉它，屏幕上「进度：节点完成」和正文长得一模一样。
        # [EN] Mechanic annotations must keep `※` —— that is the only visual signal that "this is not story";
        # [EN] remove it and on screen 「进度：节点完成」 looks exactly the same as body text.
        return f'※ {text}' if text else ''

    if k == S.RECAP:
        # 前情提要：**不加 `※`** —— 那是"机制标注"的信号，而这一段是给人读的
        # 故事背景。用 `§` 起头（屏幕上还会套一块专属的底色方块，见
        # [EN] Recap: **no `※`** —— that is the "mechanic annotation" signal, while this paragraph is for
        # [EN] people to read
        # [EN] story background. Start with `§` (on screen it also gets its own background color block, see
        # `gui/app_flet.py::NARR_BLOCK_STYLE['recap']`）。
        return f'§ {t("前情提要")}：{text}' if text else ''

    if k == S.BRIEF:
        # 今日剧情简介：与前情提要并列，用**另一个**符号（`▷` = "接下来"），
        # 一眼能和"前面发生了什么"分开。同样是独立方块，不进正文段落流。
        # [EN] Today's plot summary: parallel to recap, uses **another** symbol (`▷` = "next"),
        # [EN] at a glance can be separated from "what happened before". Also its own block, does not enter the
        # [EN] body paragraph flow.
        return f'▷ {t("今日剧情简介")}：{text}' if text else ''

    if k == S.TASK:
        # 今日任务分配（谁负责哪几件事）：文本在这一层就拼好了（`task_block`），
        # 原样返回 —— 与 `STAGE`/`CREW`/`SUMMARY` 同一手法（**拼句只有一处**）。
        # [EN] Today's task assignment (who is responsible for which items): the text is already assembled at
        # [EN] this layer (`task_block`),
        # [EN] return as-is —— same approach as `STAGE`/`CREW`/`SUMMARY` (**sentence assembly only in one
        # [EN] place**).
        return text

    if k in (S.STAGE, S.CREW, S.SUMMARY):
        # 剧组的过程消息与收工总结：**文本在这一层就拼好了**
        # （`stage_line` / `crew_line` / `summary_block`），到这里原样返回 ——
        # 它们不带 `※`（不是机制标注）、不带 `§`/`▷`（不是给人读的故事背景），
        # 各自有自己的记号（`▸` / `·` / `■`）。
        # [EN] Crew's progress messages and wrap-up summary: **text is already assembled at this layer**
        # [EN] (`stage_line` / `crew_line` / `summary_block`), here return as-is ——
        # [EN] they do not carry `※` (not mechanic annotation), do not carry `§`/`▷` (not story background for
        # [EN] people to read),
        # [EN] each has its own marker (`▸` / `·` / `■`).
        return text

    # 剩下的（插图之类）原样返回
    # [EN] The rest (illustration etc.) return as-is
    return text


# ══════════════════════════════════════════════════════════════
#  剧组过程消息（阶段 · 工作状态）—— 2026-10-07
# [EN] Crew progress messages (stage · work status) —— 2026-10-07
# ══════════════════════════════════════════════════════════════
# 用户：「把作者写小说 剧作家创作剧本 剧组排练 然后重新修改 再排练 再修改等过程
# 用**小的消息**（只显示阶段名和用时，不真实输出内部细节，但细节写入日志）……
# 别的不要加到运行界面中间窗口」。
# [EN] User: "the process of author writing novel, playwright creating script, crew rehearsal, then
# [EN] revise again, rehearse again, revise again etc.
# [EN] use **small messages** (only show stage name and elapsed time, do not actually output internal
# [EN] details, but details are written to log)...
# [EN] do not add anything else to the middle window of the running interface".
#
# ★ 两条硬规矩（判据盯着）：
#   1. **只报阶段名与用时**：`stage_line()` 的输入只有"哪个阶段 + 花了多久"，
#      函数本身拿不到、也不可能带上产出内容 —— 想推内容也推不出去。
#   2. **列表是唯一的**（`_STAGE_KEYS`）：`sim/loop` 只给 key，句子在这一层拼。
#      两处各写一份的话，迟早出现"日志里叫这个名字、屏幕上叫那个名字"。
# [EN] ★ Two hard rules (criteria watch them):
# [EN] 1. **Only report stage name and elapsed time**: the input of `stage_line()` is only "which stage + how long it took",
# [EN] the function itself cannot get and cannot carry output content —— even wanting to push content
# [EN] cannot push it out.
# [EN] 2. **The list is unique** (`_STAGE_KEYS`): `sim/loop` only provides keys, sentences are assembled at this layer.
# [EN] if written separately in two places, sooner or later "it is called this name in the log and that
# [EN] name on screen".
#
# ⚠ `t()` 必须在**调用时**求值（不能写成模块级常量）—— 界面语言可以在运行时切，
#   模块级常量会把第一次 import 时的语言冻住。
# [EN] ⚠ `t()` must be evaluated **at call time** (cannot be written as a module-level constant) —— UI
# [EN] language can be switched at runtime,
# [EN] a module-level constant would freeze the language at the first import.

def _secs_label(secs: float) -> str:
    """用时怎么写：10 秒以内给一位小数，超过就整秒（`0.8s` / `12s`）。
        English:
    How to write the duration: one decimal place within 10 seconds, whole seconds beyond (`0.8s` /
    `12s`).
    """
    try:
        x = float(secs or 0.0)
    except (TypeError, ValueError):
        x = 0.0
    return t('{s}s', s=(f'{x:.1f}' if x < 10 else str(int(round(x)))))


#: 用时低于这个数就**不写那一截**（`▸ 开演`）。
# [EN] : below this number, **do not write that segment** (`▸ 开演`).
#:
#: 为什么不是一个漂亮的 0：**演示模式（MOCK）下每一步都是毫秒级**，
#: 屏幕上会变成一排 `▸ 剧组排练 · 0.0s` —— 那看着像"这东西卡住了/没计时"，
#: 而不是"它很快"。真机下一次调用几秒到几十秒，本来就会显示。
#: 100 毫秒是"人眼还分得出快慢"的下限，再低写出来只会让人分心。
# [EN] : why not a nice 0: **in demo mode (MOCK) every step is at millisecond level**,
# [EN] : on screen it would become a row of `▸ 剧组排练 · 0.0s` —— that looks like "this thing is stuck/not
# [EN] timing",
# [EN] : rather than "it is fast". On a real machine one call takes seconds to tens of seconds, it
# [EN] would display anyway.
# [EN] : 100 milliseconds is the lower limit of "the human eye can still tell fast from slow", anything
# [EN] lower only distracts.
_MIN_SECS_SHOWN = 0.1


def stage_line(key: str, secs: float = 0.0, *, ok: bool = True) -> str:
    """一条**阶段**小消息：`▸ 剧作者写剧本 · 1.4s`。

    `key` 取下面那张表里的名字（`sim/loop` 只给这个 key）。
    认不出的 key **原样显示**（不猜、不编一个好听的名字）——
    与 `roster.role()` 认不出就抛是同一个态度：宁可难看，
    也不要看起来像对的东西。

    ⚠ 用时小于 `_MIN_SECS_SHOWN` 时**不写那一截**：有些阶段本来就没有耗时
      可言（暂停、继续），而演示模式下每一步都快到 0 —— 硬写 `0.0s`
      会让人以为它卡住了（见 `_MIN_SECS_SHOWN`）。
    
        English:
        `key` takes a name from the table below (`sim/loop` only provides this key).
        Unrecognized keys are **displayed as-is** (don't guess, don't invent a nice-sounding name) ——
        same attitude as `roster.role()` throwing when unrecognized: rather ugly,
        than something that looks right.
        ⚠ When the duration is less than `_MIN_SECS_SHOWN`, **that segment is not written**: some stages have no duration at all
          (pause, resume), and in demo mode every step is so fast it's near 0 —— hardwriting `0.0s`
          would make people think it's stuck (see `_MIN_SECS_SHOWN`).
    """
    # ★ 2026-10-21：**名字表搬到 `crew/doing` 了**（唯一一份）。
    #   为什么搬：状态条现在要显示"正在做什么"，它读的是 `crew.doing`；
    #   而阶段消息这里也要显示同一件事。两处各留一份表，就会出现
    #   "中栏写「剧组排练」、状态条写「rehearsal」"这种对不上的情况
    #   （本项目的老账：列表只能有一份）。
    #   ⚠ 认不出的 key **原样显示**（`stage_label` 的行为），不猜、不编。
    # [EN] ★ 2026-10-21: **the name table moved to `crew/doing`** (single copy). Why: the status
    # [EN] bar must show "what is happening now" and reads `crew.doing`, while this stage message
    # [EN] shows the same thing -- two copies would drift ("剧组排练" in the middle column,
    # [EN] "rehearsal" in the status bar). ⚠ Unrecognized keys are shown as-is.
    label = DO.stage_label(key)
    try:
        x = float(secs or 0.0)
    except (TypeError, ValueError):
        x = 0.0
    tail = f' · {_secs_label(x)}' if x >= _MIN_SECS_SHOWN else ''
    return f'▸ {label}{tail}' + ('' if ok else t('（失败）'))


def crew_line(name: str, state: str, secs: float = 0.0,
              detail: str = '') -> str:
    """一条**剧组工作状态**：`· 小说作家 已交活 · 3.1s`。

    `name` 是职位显示名（`crew/roster.Role.name`，已是中文基准）；
    `state` 取 `crew/studio` 那几档（待命 / 出工中 / 已交活 / 未启用 / 没出活）。

    ⚠ 这里**只写状态**，正文（它交了什么）在落盘的 `.md` 与日志里。
      `detail` 只在 `CREW_SCREEN=full` 时才传进来 —— 那时是**一句话标题**
      （"今天 2 处"），仍然不是产出全文。
    
        English:
        `name` is the role display name (`crew/roster.Role.name`, already Chinese-based);
        ⚠ Here **only the status is written**; the body content (what it delivered) is in the persisted `.md` and logs.
          `detail` is only passed in when `CREW_SCREEN=full` —— at that point it's a **one-sentence title**
          ("今天 2 处"), still not the full output text.
    """
    nm = str(name or '').strip() or t('剧组')
    st = str(state or '').strip()
    tail = f' · {_secs_label(secs)}' if float(secs or 0.0) >= _MIN_SECS_SHOWN else ''
    head = f'· {t(nm)}' + (f' {t(st)}' if st else '') + tail
    one = ' '.join(str(detail or '').split())
    return f'{head} —— {one}' if one else head


def task_block(rows: list[tuple[str, list[str]]]) -> str:
    """**今日任务分配**那一块（`▤ 今日任务` + 每人一行）。

    用户白名单里的「导演工作分配」。开演前定下来的那份框架 ——
    今天这台戏分到谁头上是哪几件事（`DayScript.roles`）。

    `rows` = `[(人名, [任务, …]), …]`（**已按人排好序**的那种）。
    空表返回空串 —— 没有派活就**不推这张卡**（不推一条空的框）。

    记号用 `▤`：与旁边那两块的 `§`（前情提要）/ `▷`（今日简介）同属"开演前的
    三块"，但一眼能分得开 —— 那两块是**连贯的话**，这一块是**一张名单**。
    
        English:
        The "director's work assignment" in the user whitelist. The framework decided before the show starts ——
        which few tasks in today's play go to whose head (`DayScript.roles`).
        Empty table returns empty string —— if nothing is assigned, **don't push this card** (don't push an empty frame).
        Use `▤` as the marker: it belongs to the same "three pre-show blocks" as the neighboring `§` (previously on) / `▷` (today's brief),
        but is distinguishable at a glance —— those two are **coherent prose**, this one is **a roster**.
    """
    lines: list[str] = []
    for name, tasks in list(rows or []):
        who = str(name or '').strip()
        todo = [str(x).strip() for x in (tasks or []) if str(x).strip()]
        if not who or not todo:
            continue
        lines.append(f'· {who} —— ' + '；'.join(todo[:3]))
    if not lines:
        return ''
    return f'▤ {t("今日任务")}\n\n' + '\n'.join(lines)


def summary_block(title: str, body: str) -> str:
    """**收工总结**那一块（`■ 今日总结` + 正文）。

    用户白名单里的「手动停止以及一天自动停止之后的总结」——
    这是**唯一**会以"内容"形式上屏的剧组产出（其余产出只报状态）。
    用 `■` 起头：它比 `※`（机制标注）重、比 `§`/`▷`（开演前的两块）更"收束"，
    正是一天最后一件事该有的记号。
    
        English:
        The "summary after manual stop and daily auto-stop" in the user whitelist ——
        this is the **only** crew output that appears on screen as "content" (all other outputs only report status).
        Starts with `■`: it's heavier than `※` (mechanism annotation), more "concluding" than `§`/`▷` (the two pre-show blocks),
        exactly the marker the last thing of the day should have.
    """
    head = t(str(title or '收工总结'))
    text = str(body or '').strip()
    return f'■ {head}\n\n{text}' if text else f'■ {head}'


def is_joinable(kind: str) -> bool:
    """这种词条能不能并进前一段。
        English:
    Whether such an entry can be merged into the previous paragraph.
    """
    return kind in JOINABLE


def group(rows: list[tuple]) -> list[list[int]]:
    """把一串 `(priority, text, kind)` 切成段落，返回**下标分组**。

    ⚠ 必须是**纯函数**：只看序列本身，不看"什么时候追加的"。
      中栏有两处渲染（正在跑时逐条追加、重进界面时整屏重建），
      两处必须得到**同样的分段** —— 否则同一份内容在两种时刻看起来不一样。

    ⚠ **分段不看 priority**。旧的中栏按 `priority >= 3` 把动作/环境/出场
      压成小一号的淡字（`_mk_live_line` 里的 `small`）—— 那正是"场记感"的来源之一：
      故事正文被压成了脚注。现在叙述类一律是正文字号，priority 只留给
      机制标注（`※`）用，而它根本不在 `JOINABLE` 里，不会混进段落。
    
        English:
    Split a sequence of `(priority, text, kind)` into paragraphs, returning **index groupings**.
        ⚠ Must be a **pure function**: only looks at the sequence itself, not at "when it was appended".
          The middle column has two render sites (append one-by-one while running, full-screen rebuild when re-entering the UI),
          both must get the **same paragraphing** —— otherwise the same content looks different at the two moments.
        ⚠ **Paragraphing does not look at priority**. The old middle column used `priority >= 3` to compress actions/environment/entrances
          into smaller, paler text (`small` in `_mk_live_line`) —— that was one source of the "stage-note feel":
          the story body was compressed into a footnote. Now narrative is always at body font size, priority is reserved only for
          mechanism annotations (`※`), which aren't in `JOINABLE` at all and won't mix into paragraphs.
    """
    out: list[list[int]] = []
    for i, row in enumerate(rows):
        kind = row[2] if len(row) > 2 else ''
        cur = out[-1] if out else None
        if cur is not None and is_joinable(kind) and len(cur) < PARA_MAX_SENTENCES:
            prev = rows[cur[-1]]
            prev_kind = prev[2] if len(prev) > 2 else ''
            if is_joinable(prev_kind):
                cur.append(i)
                continue
        out.append([i])
    return out


def sent_sep() -> str:
    """段落内句子之间的连接符。

    中文句子自带标点，**直接连**（`他把壶放下。她没说话。`）；
    英文必须留一个空格，否则 `He...She...` 会粘在一起。
    
        English:
    The connector between sentences within a paragraph.
        English must keep a space, otherwise `He...She...` will stick together.
    """
    return ' ' if is_en() else ''


def join_text(rows: list[tuple], idxs: list[int]) -> str:
    """一段拼成文本。给"要纯文本"的地方用（日志、验证、导出）。

    缩进规则与屏幕一致 —— **必须调 `should_indent()`，不能在这里再判一遍**：
    反例法里"把台词也改成缩进"那个变异红不了，就是因为我在这儿
    复制了一份 `kinds & NON_INDENT` 的判断（两处实现，改一处另一处不动）。
    
        English:
    A piece of assembled text. Used for places that "want plain text" (logs, validation, export).
        Indentation rules are identical to the screen -- **you must call `should_indent()`, do not re-judge it here**:
        In the counterexample method, the mutation "also make dialogue indented" does not go red, precisely because I copied
        a duplicate of the `kinds & NON_INDENT` check here (two implementations; change one and the other stays put).
    """
    parts = [_clean(rows[i][1]) for i in idxs]
    parts = [p for p in parts if p]
    if not parts:
        return ''
    body = sent_sep().join(parts)
    kinds = {(rows[i][2] if len(rows[i]) > 2 else '') for i in idxs}
    return (PARA_INDENT + body) if should_indent(kinds) else body


def should_indent(idxs_kinds: set[str]) -> bool:
    """这一段要不要缩两格（**唯一实现**，屏幕与纯文本都走它）。
        English:
    Whether this paragraph should be indented by two spaces (**the single implementation**; both
    screen and plain text go through it).
    """
    return not (idxs_kinds & NON_INDENT)


def is_speech(kind: str) -> bool:
    """台词 —— 独立成段、不加缩进（小说排版规矩）。
        English:
    Dialogue -- stands as its own paragraph, no indentation added (novel typesetting convention).
    """
    return kind == S.DIALOGUE


# ══════════════════════════════════════════════════════════════════
#  「没事就把时间跳过去」那一句旁白（2026-10-11）
# [EN] The "just skip the time when nothing's up" narration line (2026-10-11)
# ══════════════════════════════════════════════════════════════════
#
# 用户原话：「没事的时候时间要不要跳过（即**用旁白描述一下就过去这段时间**）」。
# [EN] User's exact words: "when nothing's up, should time be skipped (i.e. **use a narration line to
# [EN] describe passing that span**)?"
#
# ★ 为什么这句话在这一层（而不是 `sim/loop.py` 里现拼）：本项目的老规矩 ——
#   **"一句话该怎么说"只由 `display/` 决定**（见模块头那段"分工"）。
#   `sim/loop.py` 负责"什么时候跳、跳多久"，它把数字交给这里，这里给字。
# [EN] ★ Why this line lives at this layer (instead of being assembled in `sim/loop.py`): this
# [EN] project's long-standing rule --
# [EN] **"How a single line should be phrased" is decided only by `display/`** (see the "division of
# [EN] labor" at the module head).
# [EN] `sim/loop.py` handles "when to skip, how long"; it hands the numbers here, and here we give the
# [EN] words.
#
# ★★ **只描述时间，不编故事**（这条最要紧）：跳过不等于"这段时间发生了事"，
#   所以这一句里**不许出现任何人物动作、对话、事件** —— 只有天光、声气、
#   器物这类**没人也成立**的东西。凭这一句编出"他去了城外"之类，等于
#   替作者写了正文，而且后面的人谁也接不上（那件事没人做过）。
# [EN] ★★ **Describe time only, do not invent story** (this one matters most): a skip does not mean
# [EN] "something happened during this span",
# [EN] so this line **must not contain any character action, dialogue, or event** -- only sky light,
# [EN] ambient sound,
# [EN] and objects -- things that **hold up with nobody present**. Inventing "he went outside the city"
# [EN] from this line amounts to
# [EN] writing the main text on the author's behalf, and nobody downstream can pick it up (nobody ever
# [EN] did that thing).
#
# ⚠ 模板走 `t()`（英文界面下中栏不该冒中文），但**填进去的值都是我们自己的
#   常量**（不含花括号），所以 `t()` 里的 `.format()` 不会出岔子。
#   （反例：`sim/resume.py` 里那句前情提要把**正文**塞进 `t()` 的 format，
#     正文里一个 `{` 就抛，被 `t()` 吞成"没替换掉的原样模板"。）
# [EN] ⚠ The template goes through `t()` (the middle column must not show Chinese under an English UI),
# [EN] but **the values filled in are all our own
# [EN] constants** (no braces), so the `.format()` inside `t()` won't blow up.
# [EN] (Counterexample: the recap line in `sim/resume.py` stuffs **main text** into `t()`'s format;
# [EN] a single `{` in the main text throws, and `t()` swallows it into "the unsubstituted template
# [EN] as-is".)

#: 时长分档：`(上限分钟, 说法)`，从短到长取**第一个**够得着的。
# [EN] : duration buckets: `(max minutes, phrasing)`, take the **first** one that reaches, from short
# [EN] to long.
#: 时长档 → 人话。**单位跟量级走**：能说"一盏茶"就不说"15 分钟"。
#:
#: ★★★ 2026-10-26 补了"天/月"那几档（用户选 A：日界 = 拍预算用完）。
#:   补之前最长的档是"大半日"（>120 分钟一律说"大半日"）—— 于是站末跳
#:   90 天时，旁白写的是「**大半日**就这么过去」，而读者刚被告知"此后三个月无事"。
#:   那不是措辞问题，是**时间量级说错了**，比不写更糟。
#: ⚠ 档位顺序是"从短到长，第一个够用的胜"，所以 `None` 必须在最后。
# [EN] Duration tier -> colloquial wording. **The unit follows the magnitude.** ★★★ 2026-10-26: added
# [EN] the days/months tiers (the user chose A: the day ends when the beat budget runs out). Before,
# [EN] the longest tier was "most of a day" (>120 minutes all said that), so a 90-day end-of-station
# [EN] jump was narrated as "**most of a day** passed" right after telling the reader three months
# [EN] went by. That is not a wording problem but **the wrong magnitude of time**, worse than silence.
# [EN] ⚠ Ordered shortest to longest, first fit wins, so `None` must stay last.
_SKIP_DUR = ((15, '一盏茶的工夫'), (45, '小半个时辰'),
             (120, '一两个时辰'), (12 * 60, '大半日'),
             (3 * 24 * 60, '几日'), (10 * 24 * 60, '十来天'),
             (45 * 24 * 60, '一个来月'), (None, '几个月'))

#: 没人也成立的"现场声气"（按时段 / 天气挑；挑不出就用手里那条最普通的）。
#: ⚠ 时段名要跟 `util.timefmt.GameTime.segment()` **逐字对得上**
#:   （它给的是 清晨/上午/晌午/午后/傍晚/入夜/深夜/凌晨）。
#:   写成"晨""暮"这种自造词，那一条就永远挑不中（会一直落到兜底句上）
#:   —— 而现象只是"句子没那么贴"，不报错，很容易一直没人发现。
# [EN] : "ambient sound of the scene" that holds up with nobody present (pick by time segment /
# [EN] weather; if nothing fits, use the plainest one at hand).
# [EN] : ⚠ the time-segment names must match `util.timefmt.GameTime.segment()` **word for word**
# [EN] : If you write coined words like "晨" or "暮", that entry never gets picked (it always falls
# [EN] through to the fallback line)
# [EN] : -- and the symptom is only "the line fits less well", no error, so it's easy for nobody to
# [EN] ever notice.
_SKIP_AMBIENT_WEATHER = {
    '雨': '雨脚一阵密一阵疏，檐水没断过',
    '雪': '雪无声地落，院里的脚印很快填平了',
}
_SKIP_AMBIENT = (
    (('深夜', '凌晨'), '灯芯剪过一回，窗外静得听得见风声'),
    (('入夜', '傍晚'), '天色一寸寸暗下来，街上的声气也淡了'),
    (('清晨', '上午'), '檐水一滴一滴，晨光从门槛上移过去'),
)
_SKIP_AMBIENT_DEFAULT = (
    '茶凉了又续上，院子里始终没有别的声息',
    '案上的账页翻过去几页，谁也没开口',
    '光在墙上慢慢挪，屋里的东西都还在原处',
)

#: **长时间流走**（几天以上）的"现场声气"。
#:
#: ★ 为什么必须另有一组（2026-10-26）：上面那几句写的是**半天之内**的事
#:   （"茶凉了又续上""光在墙上慢慢挪"）。站末跳 90 天时配这句，读起来是
#:   "几个月就这么过去 —— 案上的账页翻过去几页"：量级对不上，
#:   读者会觉得作者根本没意识到自己跳了多久。
#: ⇒ 大于等于 `_LONG_SKIP_MIN` 就用这一组，写的是**季节 / 草木 / 人事**级别的变化。
# [EN] **Long-passage ambient** (several days or more). ★ Why a separate set (2026-10-26): the lines
# [EN] above describe **within half a day** ("tea cooled and was refilled", "light crept along the
# [EN] wall"). Pairing them with a 90-day jump reads as "months went by -- the ledger pages turned a
# [EN] few leaves", which is the wrong magnitude and makes the author look unaware of the jump.
# [EN] At or above `_LONG_SKIP_MIN` this set is used: seasons, plants, the passage of people's lives.
_LONG_SKIP_MIN = 3 * 24 * 60
_SKIP_AMBIENT_LONG = (
    '院里的树换了一茬叶子，墙根生了新的青苔',
    '檐下的旧燕巢空了又满，来往的人换过几张脸',
    '门前的石板被踩得更亮了些，去年挂的灯早收了',
)


def time_skip_label(minutes: int) -> str:
    """「半小时」这种人话（**单位跟量级走**：能说"一盏茶"就不说"15 分钟"）。

    拿不准就退回"N 分钟"（数字是可靠的，说法才是润色）。
    
        English:
    "Half an hour"-style colloquial expressions (**unit follows magnitude**: if you can say "a cup
    of tea's time", don't say "15 minutes").
        When unsure, fall back to "N minutes" (numbers are reliable; phrasing is the polish).
    """
    m = max(1, int(minutes or 0))
    for cap, label in _SKIP_DUR:
        if cap is None or m <= cap:
            return t(label)
    return t('{n} 分钟', n=m)


def skip_ambient(segment: str = '', weather: str = '',
                 seed: int = 0, minutes: int = 0) -> str:
    """这段时间的"现场声气"（**不涉及任何人物**，见上面那段说明）。

    ⚠ `minutes` 决定**量级**：>= `_LONG_SKIP_MIN`（三天）走 `_SKIP_AMBIENT_LONG`
      （季节/草木/人事级别的变化），否则走半天之内的那几句。
      不传 `minutes` = 老行为（按半天写）。
        English:
    The "ambient feel of the scene" during this period (**does not involve any character**; see the
    explanation section above). ⚠ `minutes` decides the **magnitude**: at or above
    `_LONG_SKIP_MIN` (three days) it uses `_SKIP_AMBIENT_LONG` (seasons / plants / lives), otherwise
    the within-half-a-day lines. Omitting `minutes` keeps the old behaviour.
    """
    m = max(0, int(minutes or 0))
    if m >= _LONG_SKIP_MIN:
        pool = list(_SKIP_AMBIENT_LONG)
        return t(pool[int(seed) % len(pool)])
    w = str(weather or '').strip()
    for key, line in _SKIP_AMBIENT_WEATHER.items():
        if key and key in w:
            return t(line)
    s = str(segment or '').strip()
    for keys, line in _SKIP_AMBIENT:
        if any(k in s for k in keys):
            return t(line)
    pool = list(_SKIP_AMBIENT_DEFAULT)
    return t(pool[int(seed) % len(pool)])


def time_skip_line(minutes: int, *, where: str = '', segment: str = '',
                   weather: str = '', seed: int = 0) -> str:
    """跳过一段时间的那句旁白（`S.AMBIENT` 词条用它）。

    形如：`小半个时辰就这么过去 —— 临河茶肆里没什么事：雨脚一阵密一阵疏，
    檐水没断过。`

    `where` 空时省掉地点那一截（宁短不空——**不编一个地名**）。
    
        English:
    The narration line that skips a period of time (`S.AMBIENT` entries use it).
        In the form: `A little over half a shichen passed just like that -- nothing much going on in the riverside tea house: the rain came in spells, now dense now sparse,
        the eaveswater never stopped.`
        When `where` is empty, omit the location part (prefer short over empty -- **do not invent a place name**).
    """
    dur = time_skip_label(minutes)
    amb = skip_ambient(segment, weather, seed, minutes=minutes)
    place = str(where or '').strip()
    if place:
        return t('{dur}就这么过去 —— {place}里没什么事：{amb}。',
                 dur=dur, place=place, amb=amb)
    return t('{dur}就这么过去 —— 没什么事：{amb}。', dur=dur, amb=amb)


def time_pass_line(minutes: int, *, where: str = '', segment: str = '',
                   weather: str = '', seed: int = 0) -> str:
    """**这一段到此为止**的那句旁白（站末补时间用，`_flush_station_gap` 调它）。

    ★★★ 2026-10-26 新增，与 `time_skip_line` **有意分开**：

    两者观感相同（"时间过去了"），但语义不同，而且**必须能分开**：

    | 谁在用 | 什么时候 | 说的是 |
    |---|---|---|
    | `time_skip_line` | 连着几拍没人做事（`_maybe_skip_idle`） | "这会儿没什么事" —— **戏还在继续** |
    | **本函数** | 这一站演完了，跨度还剩一大截 | "这一段到此为止" —— **要换场了** |

    ⚠ 分成两句不只是措辞：`verify_round_controls` 的 C2/C3 用「'就这么过去' 出现 0 次」
      来证明"空闲跳过关掉了 / 有人在说话时没跳"。站末补时间**不是空闲跳过**，
      共用同一句就会让那两条判据误红（实测撞过），而红的原因跟"该不该跳"毫无关系。
    ⚠ 句式必须与 `time_skip_line` **不共享任何短语**，否则按子串判的地方还是会混。
    [EN] **"This stretch is over"** narration, used by the end-of-station top-up
    [EN] (`_flush_station_gap`). ★★★ New on 2026-10-26 and **deliberately separate** from
    [EN] `time_skip_line`: they read alike ("time passed") but mean different things and **must be
    [EN] distinguishable**. `time_skip_line` fires when nobody has done anything for several beats
    [EN] ("nothing much going on" -- the scene continues); this one fires when the station is over and
    [EN] much of its span is left ("this stretch ends here" -- the scene is changing). ⚠ Splitting them
    [EN] is not cosmetic: `verify_round_controls` C2/C3 prove "idle skip is off / nobody was skipped
    [EN] while talking" by "'就这么过去' appears 0 times", and a shared sentence makes both misfire
    [EN] (measured). ⚠ The wording must share **no phrase** with `time_skip_line`, or string checks
    [EN] will confuse them again.
    """
    dur = time_skip_label(minutes)
    amb = skip_ambient(segment, weather, seed, minutes=minutes)
    place = str(where or '').strip()
    if place:
        return t('这一段到这儿为止 —— 此后{dur}，{place}照旧：{amb}。',
                 dur=dur, place=place, amb=amb)
    return t('这一段到这儿为止 —— 此后{dur}，屋里屋外照旧：{amb}。', dur=dur, amb=amb)
