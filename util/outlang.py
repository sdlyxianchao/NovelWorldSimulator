# -*- coding: utf-8 -*-
"""**输出语言**：程序产出的一切文字用哪种语言写。

和「界面语言」是两件事，别混：

| | 管什么 | 存在哪 | 谁在用 |
|---|---|---|---|
| **界面语言** `i18n` | 按钮、标签、提示、消息 —— **程序自己的话** | 全局 `.env` 的 `UI_LANG` | 界面 |
| **输出语言**（本模块） | 叙事、台词、文档、小结、建议 —— **推演产出的文字** | **项目**的 `.nwsproj` | 给模型的指令 |

用户（2026-10-06）：
「在项目里设置一个输出语言，这样**所有的输出都用这个语言**，
即使小说原来的语言不是这个（默认请支持中文英文即可，后续再加别的）」

☆ 为什么是**项目级**：同一台机器上，「一本英文小说想推成中文」和
「一本中文小说想推成英文」都是正常需求 —— 换个项目就该重选。
（判据就是这条："换个项目还用同一个值吗？" 不用 → 存项目文件。）

☆ 为什么默认是 `auto`（跟随界面语言）：老项目里没有这个字段，
`auto` 让它们的行为**和以前一样**（中文界面 → 中文输出），不用迁移。

☆ 怎么"让所有输出都用这个语言"：只有一条路可靠 —— **在提示词里说清楚**。
落点选在 `llm/router.py:chat()`（所有 LLM 请求的唯一漏斗），
见那里的 `_inject_output_lang()`。选在漏斗而不是 29 个调用点，
是因为"新加一个调用点忘了写"这种事本项目已经踩过好几次。

English:
**Output language**: which language all text produced by the program is written in.
It is a different thing from "UI language", don't confuse them:
| | Controls what | Stored where | Who uses it |
|---|---|---|---|
| **UI language** `i18n` | buttons, labels, hints, messages —— **the program's own words** | global `.env`'s `UI_LANG` | UI |
| **Output language** (this module) | narrative, dialogue, documents, summaries, suggestions —— **text produced by the simulation** | the **project**'s `.nwsproj` | instructions to the model |
User (2026-10-06):
"Set an output language in the project, so that **all output uses this language**
even if the novel's original language is not this (by default just support Chinese and English;
add others later)"
☆ Why **project-level**: on the same machine, "an English novel wants to be adapted into
Chinese" and
"a Chinese novel wants to be adapted into English" are both normal needs —— switching projects
should mean re-choosing.
(The criterion is exactly this: "Would the same value still be used after switching projects?"
No → store it in the project file.)
☆ Why the default is `auto` (follow the UI language): old projects don't have this field,
and `auto` makes their behavior **the same as before** (Chinese UI → Chinese output), with no
migration needed.
☆ How to "make all output use this language": there is only one reliable way —— **state it
clearly in the prompt**.
The injection point is `llm/router.py:chat()` (the single funnel for all LLM requests),
see `_inject_output_lang()` there. Choosing the funnel instead of the 29 call sites
is because "added a new call site and forgot to write it" has already been stepped on several
times in this project.
"""
from __future__ import annotations

from i18n import t

# 语言代码 → 界面显示名。**加语言只改这两处**（+ 下面 `_DIRECTIVE` 里加一条）。
# [EN] Language code → UI display name. **To add a language, change only these two places** (+ add an
# [EN] entry in `_DIRECTIVE` below).
AUTO = 'auto'
LANGS: tuple[str, ...] = ('zh', 'en')
LABELS: dict[str, str] = {
    AUTO: '跟随界面语言',      # 界面语言是中文 → 输出中文，是英文 → 输出英文
    # [EN] UI language is Chinese → output Chinese, is English → output English
    'zh': '中文',
    'en': 'English',
}

# 每种语言**一句给模型看的话**。刻意用**目标语言本身**写 ——
# 「用英文写」这句话本身就写成英文，指令和执行是同一套语言，最不容易被忽略。
# [EN] **One sentence per language for the model to see**. Deliberately written in the **target
# [EN] language itself** ——
# [EN] The sentence "write in English" is itself written in English; instruction and execution use the
# [EN] same language, which is least likely to be ignored.
_DIRECTIVE: dict[str, str] = {
    'zh': (
        '【输出语言】所有**输出文字**一律用**简体中文**书写 —— 叙事、旁白、台词、'
        '文档、小结、建议都算，**即使原始素材是别的语言**。'
        '人名、地名、书名等专有名词**保留原文写法**，不要音译或意译。'
        'JSON 里的**键名保持原样**（如 "动作"、"台词"），只把**值**写成中文。'
    ),
    'en': (
        '[Output language] Write **all output text in English** — narrative, '
        'narration, dialogue, documents, summaries and suggestions — '
        '**even if the source material is in another language**. '
        'Keep proper nouns (character names, place names, titles) in their '
        'original spelling; do not transliterate them. '
        'Structured replies keep their field names exactly as given, and only the '
        'field **values** are written in English.'
    ),
}

_current: str = ''          # 项目里存的值；'' = 没设过（当 auto）
# [EN] Value stored in the project; '' = never set (treated as auto)


def set_from_project(value: str | None) -> str:
    """换项目时调这个：把项目里存的值装进来（`''`/认不出的值 → auto）。
        English:
    Call this when switching projects: load the value stored in the project (`''`/unrecognized value
    → auto).
    """
    global _current
    v = (value or '').strip()
    _current = v if v in LABELS else AUTO
    return _current


def raw() -> str:
    """项目里存的那个值（原样，可能是 `''`）。
        English:
    The value stored in the project (as-is, may be `''`).
    """
    return _current


def resolve(value: str | None = None) -> str:
    """解析成**真正生效**的语言代码（`zh` / `en`）。

    `auto`（或没设过）→ 跟随**界面语言**。
    
        English:
    Resolve to the **actually effective** language code (`zh` / `en`).
        `auto` (or never set) → follow the **UI language**.
    """
    v = _current if value is None else (value or '').strip()
    if v in LANGS:
        return v
    from i18n import get_lang
    lang = get_lang()
    return lang if lang in LANGS else LANGS[0]


def is_auto(value: str | None = None) -> bool:
    v = _current if value is None else (value or '').strip()
    return v not in LANGS


def label(code: str) -> str:
    """人话名（跟随界面语言）。**键永远是字面量**，存盘存的就是 `zh`/`en`。
        English:
    Human-readable name (follows the UI language). **The key is always a literal**, and what is
    saved to disk is `zh`/`en`.
    """
    return t(LABELS.get((code or '').strip(), LABELS[AUTO]))


def options() -> list:
    """下拉项工厂（开卷向导与书斋共用一份 —— 两处各写一份迟早不一致）。
        English:
    Dropdown item factory (shared by the startup wizard and the study —— writing one in each place
    will inevitably diverge).
    """
    import flet as ft
    return [ft.dropdown.Option(AUTO, label(AUTO)),
            ft.dropdown.Option('zh', label('zh')),
            ft.dropdown.Option('en', label('en'))]


def directive() -> str:
    """给模型的那一句（按**生效的输出语言**）。
        English:
    The sentence for the model (according to the **effective output language**).
    """
    return _DIRECTIVE.get(resolve(), '')


def summary() -> str:
    """界面上的一句话说明当前怎么定的（书斋/向导的下拉下面显示）。
        English:
    A sentence in the UI explaining how it is currently determined (shown below the dropdown in the
    study/wizard).
    """
    code = resolve()
    if is_auto():
        return t('跟随界面语言 —— 现在是「{lang}」（输出与界面同一种语言）',
                 lang=label(code))
    return t('固定用「{lang}」输出，不管界面是什么语言、原稿是什么语言',
             lang=label(code))
