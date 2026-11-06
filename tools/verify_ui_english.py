# -*- coding: utf-8 -*-
"""验证：**界面切成英文之后，屏幕上不该再出现中文**。

用户（2026-10-06）：「**英语界面下面，很多消息是不是也都得英语化**」

`tools/i18n_check.py` 只管"`t('中文')` 有没有登记英文"；`developers/find_hardcoded_zh.py`
是**静态**绊线（会误报数据键、漏掉变量里的中文）。这一支是**真机判据**：
把语言设成 en，把每个界面/对话框都**真的打开一遍**，然后把控件树里所有
"会被人看到的字"（`Text.value`、按钮 content、`hint_text`、下拉项、tooltip）
收上来，逐个查有没有 CJK。

★ **关键的难点是"哪些中文是合法的"** —— 真机上必然有一些中文不是漏翻：
  · **用户自己的东西**：项目名、书名、人物名（夹具里**故意用英文名**，把这类噪音掐掉）；
  · **路径**：`C:\\Users\\…\\小说世界虚拟模拟\\Projects`（是路径，不是文案）；
  · **原始值**：`.env` / `.nwsproj` 里的真值偶尔会被原样显示（"人话/真值"那套）。
  所以下面有一个显式白名单 `ALLOW`，每条都要写清"为什么它不算漏翻"。

跑法：`.venv\\Scripts\\python.exe tools/verify_ui_english.py`
产出：assets/screenshots/ui_english_report.json

English:
Verification: **after the UI is switched to English, no Chinese should appear on screen
anymore**.
User (2026-10-06): "**Under the English UI, should many messages also be Englishized**"
`tools/i18n_check.py` only handles "whether `t('Chinese')` has English registered";
`developers/find_hardcoded_zh.py`
is a **static** tripwire (it false-alarms on data keys and misses Chinese in variables). This
branch is a **real-machine check**:
set the language to en, **really open** every screen/dialog once, then collect every
"character a human would see" in the control tree (`Text.value`, button content, `hint_text`,
dropdown items, tooltip)
and check each one for CJK.
★ **The key difficulty is "which Chinese is legitimate"** — on a real machine there will
inevitably be some Chinese that is not missing translation:
  · **The user's own stuff**: project names, book titles, character names (the fixtures **deliberately use English names** to cut out this kind of noise);
  · **Raw values**: real values in `.env` / `.nwsproj` occasionally get displayed as-is (the "human-readable/raw-value" situation).
  So below there is an explicit whitelist `ALLOW`, and each entry must clearly state "why it doesn't count as a missing translation".
How to run: `.venv\\Scripts\\python.exe tools/verify_ui_english.py`
Output: assets/screenshots/ui_english_report.json
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown  # noqa: E402

from config import CFG  # noqa: E402
# ⚠ 起了界面的脚本**第一件事就是禁写真实 `.env`**（本项目的老教训，已发生四次）：
#   这一支会走 `app.main()`，那条路上有能力校验 → `CFG.save()`。
#   它以前**没接**这道保险（只是恰好没点到那个按钮）—— 2026-10-08 补上。
# [EN] ⚠ The first thing the GUI-launching script does is **prohibit writing to the real `.env`** (a
# [EN] hard lesson in this project, has happened four times):
# [EN] This branch goes through `app.main()`, and that path has capability validation → `CFG.save()`.
# [EN] It previously **did not** have this safeguard (it just happened that nobody clicked that button)
# [EN] —— added on 2026-10-08.
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')
CFG.set('UI_LANG', 'en')

import gui.app_flet as G  # noqa: E402
from gui.app_flet import NovelWorldApp  # noqa: E402
from i18n import set_lang, t  # noqa: E402
from store.project import Project  # noqa: E402
from store.runfolder import RunFolder  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
CJK = re.compile(r'[\u4e00-\u9fff]')

# 夹具统一用**纯英文名**：项目名/书名一律不该出现在"未翻译"清单里。
# [EN] Fixtures uniformly use **pure English names**: project names/book titles should never appear in
# [EN] the "untranslated" list.
PROJ = 'EnglishUI'

# 白名单：这些位置出现中文**不是漏翻**，每条都要说清理由。
# [EN] Whitelist: Chinese appearing in these locations is **not a missed translation**; each entry must
# [EN] have its reason stated clearly.
#
# ★★ 2026-10-06 改：**路径那几条必须"运行时算出来"，不能写死目录名。**
#   原来这里是 `('小说世界虚拟模拟', 'Projects')` —— 用户当天把工作区改名成
#   `小说世界AI模拟` 之后，写死的那条**当场失效**：「天机 · 程序设置」页里
#   显示的是**日志文件的完整路径**（`…\小说世界AI模拟\NovelWorldSimulator\logs\…`），
#   于是被判成"英文界面下有中文"，**7 条判据一起假红**。
#   ⚠ 路径是**值**不是**文案** —— 它本来就该是用户盘上的原样（用户把目录起成中文，
#     界面就得显示中文）。所以这里放行的是"**这个程序自己所在的那几个目录名**"。
# [EN] ★★ Changed 2026-10-06: **those path entries must be "computed at runtime", not hardcoded
# [EN] directory names.**
# [EN] so it was judged as "Chinese in an English UI", and **7 criteria all went falsely red
# [EN] together**.
# [EN] ⚠ The path is a **value**, not **copy** —— it should be whatever is on the user's disk (if the
# [EN] user names the directory in Chinese,
# [EN] the UI must display Chinese). So what is allowed here is "**those directory names where this
# [EN] program itself resides**".
#
# ⚠ 注意**只放行足够长的具体名字，不放行短词**：
#   `C:\小说世界AI模拟\项目` 的最后一级是「项目」—— 把「项目」加进白名单，
#   等于放行所有含"项目"的文案（那正是要抓的东西）。所以放行的是**整条路径**。
# [EN] ⚠ Note: **only allow sufficiently long concrete names, do not allow short words**:
# [EN] would be equivalent to allowing all copy containing "项目" (which is exactly what we want to
# [EN] catch). So what is allowed is the **entire path**.
_PATH_WORDS = tuple(
    w for w in {
        APP_DIR.name,                  # 程序目录（`NovelWorldSimulator`，ascii 但无害）
        APP_DIR.parent.name,           # **工作区目录名**（改名后 = 小说世界AI模拟）
        '小说世界虚拟模拟',              # 历史名：老用户 / 老截图里还会出现
        'Projects',                    # 默认项目根的最后一级
        (CFG.s('DEFAULT_PROJECTS_DIR') or '').strip(),   # 项目根**整条路径**
        # [EN] Program directory (`NovelWorldSimulator`, ascii but harmless)
        # [EN] Historical names: still appear for old users / in old screenshots
        # [EN] Last level of the default project root
        # [EN] The project root's **entire path**
    } if w
)
ALLOW = _PATH_WORDS

# ★ **运行文件夹名**（`第3次模拟2026-10-06-22-01`）是**故意不翻的**，理由：
#   ① 它是**盘上的目录名**，用户在资源管理器里看到的就是这个；
#      UI 上显示成别的样子反而对不上；
#   ② `Project.list_runs()` / `next_run_index()` 靠 `第(\d+)次模拟` 这个模式
#      **认自己的运行**；名字跟着界面语言变，就要同时认两套写法，
#      而"UI 语言换过一次"的项目会**混着两种名字** —— 为了一行显示的观感
#      去动"能不能认出自己的存档"这条命脉，不划算。
#   所以这里用**窄模式**放行（不是把整个"运行名"都免检）：
#   只有"第N次模拟+日期"这种形状才放过，别的含"模拟"的文案照样会被抓。
# [EN] ★ **Run folder name** (`第3次模拟2026-10-06-22-01`) is **intentionally not translated**, for the
# [EN] following reasons:
# [EN] ① It is a **directory name on disk**; this is what the user sees in the file explorer;
# [EN] displaying it differently in the UI would instead make it not match;
# [EN] ② `Project.list_runs()` / `next_run_index()` rely on the pattern `第(\d+)次模拟`
# [EN] **to recognize their own runs**; if the name changes with the UI language, both spellings must
# [EN] be recognized,
# [EN] and a project where "the UI language was switched once" would have **both names mixed together**
# [EN] —— for the sake of one line's display appearance
# [EN] to mess with the lifeline of "whether one can recognize one's own save" is not worth it.
# [EN] So here a **narrow pattern** is used to allow it (not exempting the entire "run name"):
# [EN] Only the shape "第N次模拟+date" is let through; other copy containing "模拟" will still be caught.
RUN_NAME_RE = re.compile(r'^第\d+次模拟\d{4}-\d{2}-\d{2}-\d{2}-\d{2}')
RUN_NAME_RE2 = re.compile(r'·\s*第\d+次模拟\d{4}-\d{2}-\d{2}-\d{2}-\d{2}\s*$')

# ★ **自动落盘那份中途稿的路径**（2026-10-08）—— 与上面"运行文件夹名"同一条理由：
#   `自动落盘/进度.md` 是**盘上真实存在的路径**，说明文字里指的就是它，
#   英文界面下把它改写成别的写法反而**对不上用户资源管理器里看到的**。
# [EN] ★ **The path of the auto-saved draft** (2026-10-08) —— same reason as the "run folder name"
# [EN] above:
# [EN] `自动落盘/进度.md` is a **path that actually exists on disk**, and the explanatory text refers to
# [EN] exactly that;
# [EN] rewriting it into some other form under an English UI would instead **not match what the user
# [EN] sees in the file explorer**.
#
# ⚠ 刻意用**窄模式**（要求"目录名 + 进度.md/.json"整个形状），
#   不把「自动落盘」这个词单独放进 `ALLOW` —— 那样连**没翻译的标题**
#   （`mk_section(t("自动落盘"))` 漏翻了）也会被一起放过，等于把闸门开在
#   最该拦的地方。路径是**值**，词是**文案**，只放行前者。
# [EN] ⚠ Deliberately use a **narrow pattern** (requiring the whole shape of "directory name +
# [EN] 进度.md/.json"),
# [EN] and do not put the word "自动落盘" alone into `ALLOW` —— that way even an **untranslated title**
# [EN] (`mk_section(t("自动落盘"))` was missed) would be let through along with it, equivalent to opening
# [EN] the gate at
# [EN] the place that most needs to be blocked. A path is a **value**, a word is **copy**; only allow
# [EN] the former.
AUTOSAVE_PATH_RE = re.compile(r'自动落盘/进度\.(md|json)')

# ★ **故事里的时辰**（2026-10-11）—— 与上面两条同一条理由，但更窄：
#   这是**剧情内容**，不是界面文案。
# [EN] ★ **Time of day in the story** (2026-10-11) —— same reason as the above two, but even narrower:
# [EN] This is **story content**, not UI copy.
#
#   `第1天·辰时` / `第 3 天 · 戌时` 由 `util/timefmt.format_game_clock` 生成，
#   它进的是**中栏的叙事**（分隔符 / 前情提要 / 提问对话框那块「当前故事发展」）
#   —— 和一个中文故事里的人物名一样，跟着**故事的语言**（`OUTPUT_LANG`）走，
#   不跟界面语言走。英文界面下把故事里的时辰写成 "Day 1 · 7-9am"
#   反而与正文对不上。
# [EN] and it goes into the **middle-column narrative** (the separators / previously-on recap / the
# [EN] "current story development" in the question dialog)
# [EN] —— like a character name in a Chinese story, it follows the **story's language**
# [EN] (`OUTPUT_LANG`),
# [EN] not the UI language. Writing the time of day in the story as "Day 1 · 7-9am" under an English UI
# [EN] would instead not match the main text.
#
#   ⚠ 所以只放行**这个形状**（`第N天/日` 紧跟 `·` 或空格），
#     不把「第…天」整个词免检 —— 界面标签「第 3 天暂停」不会匹配到这里，
#     漏翻照样会被抓。
# [EN] ⚠ So only allow **this shape** (`第N天/日` immediately followed by `·` or a space),
# [EN] and do not exempt the whole word "第…天" —— the UI label "第 3 天暂停" will not match here,
# [EN] and a missed translation will still be caught.
STORY_CLOCK_RE = re.compile(r'第\d+[天日][·\s]')

# ★ **剧本审读落的那两份**（2026-10-08）—— 同一条理由、同一个窄口径：
#   `剧本审读.md` 与 `审读台账.jsonl` 是**运行文件夹里真的会出现的文件名**，
#   说明文字指的就是它们（作者要照着这个名字去文件夹里找）。
#   ⚠ 同样**不**把「剧本审读」这个词放进 `ALLOW` —— 那样
#     `mk_section(t("剧本审读"))` 漏翻了也会被放过。
# [EN] ★ **The two files written by script review** (2026-10-08) —— same reason, same narrow scope:
# [EN] the explanatory text refers to exactly them (the author needs to find them in the folder by this
# [EN] name).
# [EN] ⚠ Likewise, do **not** put the word "剧本审读" into `ALLOW` —— that way
# [EN] a missed translation of `mk_section(t("剧本审读"))` would also be let through.
REVIEW_FILE_RE = re.compile(r'(剧本审读\.md|审读台账\.jsonl)')

# ★ **三级底图那个文件名**（2026-10-12）—— 与前几条同一条理由、同一个窄口径：
#   `设定集/小世界地图.yaml` 是**项目里真的会有的那个文件**
#   （`world/atlas.py` 的 `FILE = '小世界地图.yaml'`，开卷时写、跨轮复用），
#   小地图那一行的说明文字指的就是它 —— 作者要照着这个名字去设定集里找。
#   ⚠ 同样**不**把「小世界地图」这几个字单独放进 `ALLOW`：那样连
#     `mk_section(t("小世界地图"))` 漏翻了也会被放过。
#     路径是**值**，词是**文案**，只放行前者（要求"目录 + 文件名"整个形状）。
# [EN] ★ **That three-level base map's filename** (2026-10-12) -- same reason as the entries above, and
# [EN] the same narrow scope: `设定集/小世界地图.yaml` is **the file that really exists in a project**
# [EN] (`world/atlas.py`'s `FILE = '小世界地图.yaml'`, written at book-open and reused across rounds),
# [EN] and the explanatory text under the minimap refers to exactly it -- the author needs to find it in
# [EN] the setting collection by this name.
# [EN] ⚠ Likewise, do **not** put the words "小世界地图" alone into `ALLOW`: that way a missed
# [EN] translation of `mk_section(t("小世界地图"))` would also be let through.
# [EN] A path is a **value**, a word is **copy**; only allow the former (the whole shape "directory +
# [EN] filename" is required).
BASE_MAP_FILE_RE = re.compile(r'(设定集|settings)/小世界地图\.yaml')

# ★★ **剧组 Agents 页显示的那几段正文**（2026-10-11）—— 与上面几条同一条理由，
#   而且这一条最需要写清"为什么"：
# [EN] ★★ **Those body paragraphs displayed on the Crew Agents page** (2026-10-11) —— same reason as
# [EN] the above entries,
# [EN] and this one most needs the "why" written clearly:
#
#   `agents/<slug>.md` 的**正文就是那个职位的系统提示词**，它是**作者可编辑的
#   内容**（用户点名要的："用户可以在这里编辑各个Agent的属性"）。性质同
#   `使用说明.md`、`素材/*.md`：那是**文档**，不是界面文案 —— 英文界面下把
#   作者自己写的那段话翻译一遍，反而"看到的和盘上的不是同一份"。
# [EN] The **body of `agents/<slug>.md` is exactly that role's system prompt**, and it is
# [EN] **author-editable
# [EN] content** (what the user explicitly asked for: "users can edit the attributes of each Agent
# [EN] here"). Its nature is the same as
# [EN] `使用说明.md`, `素材/*.md`: that is **documentation**, not UI copy —— translating the passage the
# [EN] author wrote themselves
# [EN] under an English UI would instead mean "what is seen and what is on disk are not the same
# [EN] thing".
#
#   ⚠ 口径要**窄**：只放行**逐字取自那些 md 的那几个字段**（提示词 / 适用场景 /
#     姓名 / 简介），而且**逐条比对**。界面上那些说明、按钮、分页、徽章
#     （"自建"/"文件目录：…"）**照旧必须翻** —— 漏翻照样会被抓。
# [EN] ⚠ The scope must be **narrow**: only allow **those fields taken verbatim from those md files**
# [EN] (prompt / applicable scenarios /
# [EN] name / summary), and **compare item by item**. The descriptions, buttons, pagination, badges in
# [EN] the UI
# [EN] ("自建" / "文件目录: …") **must still be translated as before** —— a missed translation will still be
# [EN] caught.
#
#   怎么拿到这些字符串：直接问 `crew/catalog.effective()`（那是它们的唯一来源），
#   不在判据里另抄一份（抄一份就会过期）。
# [EN] How to get these strings: just ask `crew/catalog.effective()` (that is their sole source),
# [EN] do not copy another version into the criteria (a copy will go stale).
def _agent_doc_texts() -> set:
    out: set = set()
    try:
        from crew import catalog as _CAT
        for _s in _CAT.effective(project=None):
            #  ⚠ 正文要**与界面同口径**：列表里那行用的是 `plain_prompt()`
            #    （剥掉 `<!-- … -->` 那段"给作者看的说明"之后的正文）。
            #    用原始 `_s.prompt` 存进白名单的话，它是以 `<!--` 开头的一长串，
            #    而界面显示的是剥过的正文 ⇒ 前缀匹配不上 ⇒
            #    **17 个内置职位的提示词摘要全被当成"漏翻"**（25/35）。
            #    这不是放宽判据，是让"白名单的口径"跟着"界面的口径"走 ——
            #    那段说明本来就不该出现在列表里。
            # [EN] ⚠ The body must be **in the same scope as the UI**: the line in the list uses `plain_prompt()`
            # [EN] (the body after stripping the `<!-- … -->` "notes for the author" section).
            # [EN] If the raw `_s.prompt` is stored into the whitelist, it is a long string starting with `<!--`,
            # [EN] while what the UI displays is the stripped body ⇒ the prefix will not match ⇒
            # [EN] **the prompt summaries of all 17 built-in roles are treated as "missed translations"** (25/35).
            # [EN] This is not loosening the criteria, it is making "the whitelist's scope" follow "the UI's scope"
            # [EN] ——
            # [EN] that notes section should not appear in the list in the first place.
            for _v in (_CAT.plain_prompt(_s.prompt), _s.usage,
                       _s.name, _s.intro, _s.name_en):
                v = ' '.join(str(_v or '').split())       # ⚠ 与界面同口径：
                if v:                                     #   列表里那句是
                # [EN] ⚠ Same scope as the UI:
                # [EN] The one in the list is.
                    out.add(v)                            #   `' '.join(split())`
    except Exception:                                     # noqa: BLE001
        pass
    return out


AGENT_DOC_TEXTS = _agent_doc_texts()


def visible_texts(root) -> list:
    """控件树里"会被人看到的字"。

    ⚠ 这里**不包含** `Dropdown.value`（那是存盘的真值，界面显示的是 `content`），
    也不包含 `TextField.value`（用户自己填的内容）。
    
        English:
    "Text visible to people" in the widget tree.
        ⚠ This **does not include** `Dropdown.value` (that is the raw value saved to disk; what the UI displays is `content`),
        nor does it include `TextField.value` (content the user entered themselves).
    """
    out: list = []
    for c in VU.walk(root):
        if isinstance(c, ft.Text) and c.value:
            out.append(str(c.value))
        if isinstance(c, ft.TextField):
            if getattr(c, 'hint_text', None):
                out.append(str(c.hint_text))
            if getattr(c, 'label', None):
                out.append(str(c.label))
        # 按钮：文字在 content（可能是裸字符串、Text 或 Row/Column）
        # [EN] Buttons: text is in content (may be a bare string, Text, or Row/Column).
        if type(c).__name__ in ('FilledButton', 'OutlinedButton', 'TextButton',
                                'ElevatedButton'):
            for x in VU.walk(c):
                if isinstance(x, ft.Text) and x.value:
                    out.append(str(x.value))
            if isinstance(getattr(c, 'content', None), str):
                out.append(c.content)
        if isinstance(c, ft.DropdownM2):
            for o in (getattr(c, 'options', None) or []):
                for x in VU.walk(getattr(o, 'content', None)):
                    if isinstance(x, ft.Text) and x.value:
                        out.append(str(x.value))
        for attr in ('tooltip', 'message'):
            v = getattr(c, attr, None)
            if isinstance(v, str) and v:
                out.append(v)
    return out


def bad(texts: list) -> list:
    """筛出"含中文且不在白名单里"的文案（去重、保序）。
        English:
    Filter out copy that "contains Chinese and is not in the whitelist" (deduplicate, preserve
    order).
    """
    seen = set()
    out = []
    for t in texts:
        if not CJK.search(t):
            continue
        if any(a in t for a in ALLOW):
            continue
        if RUN_NAME_RE.match(t) or RUN_NAME_RE2.search(t):
            continue
        if AUTOSAVE_PATH_RE.search(t):
            continue
        if STORY_CLOCK_RE.search(t):
            continue
        if REVIEW_FILE_RE.search(t):
            continue
        if BASE_MAP_FILE_RE.search(t):
            continue
        # 剧组 Agents 页：那几段**作者可编辑的正文**（逐字比对，见上面那段说明）。
        # ⚠ 列表里显示的是**截断版**（前 52 字 + `…`），所以还要认"某段的开头"。
        #   要求前缀 ≥ 20 字：太短的片段会误放过真正的漏翻（例如"名字"）。
        # [EN] Crew Agents page: those **author-editable body texts** (compare verbatim, see the note above).
        # [EN] ⚠ What is shown in the list is the **truncated version** (first 52 chars + `…`), so you must
        # [EN] also recognize "the start of some paragraph".
        # [EN] Require prefix ≥ 20 chars: too-short fragments would falsely let real miss-translations slip
        # [EN] through (e.g. "name").
        _k = t.strip()
        if _k in AGENT_DOC_TEXTS:
            continue
        _core = _k.rstrip('…').strip()
        if len(_core) >= 20 and any(d.startswith(_core) for d in AGENT_DOC_TEXTS):
            continue
        k = t.strip()
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


async def main(page: ft.Page):
    report: dict = {'surfaces': {}, 'ok': True}
    ITEMS: list = []

    def ok(name, cond, detail=''):
        ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
        if not cond:
            print(f'FAIL  {name}   [{detail}]')
        return bool(cond)

    set_lang('en')
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_enui_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    # ★★ 2026-10-12：**模型登记表也要隔离**。
    #   它是用户数据（作者会给模型起中文显示名，比如"混元 Hy3"），
    #   不隔离的话，天问里那条模型记录会被当成"英文界面上有中文"（实测 8 处假红）。
    #   ⚠ 也不能把"用户起的模型名"加进 `ALLOW` —— 那等于放行任意中文，
    #     与本文件既有的"夹具用纯英文、用户数据一律隔离"同一条思路。
    # [EN] ★★ 2026-10-12: **the model registry must be isolated too**.
    # [EN] It is user data (authors give models Chinese display names, e.g. "混元 Hy3"); without
    # [EN] isolation that model record in Tianji is judged as "Chinese in an English UI" (8 false
    # [EN] reds measured).
    # [EN] ⚠ Nor can "a user-chosen model name" be added to `ALLOW` -- that would allow arbitrary
    # [EN] Chinese, contrary to this file's existing rule of "fixtures in pure English, user data
    # [EN] always isolated".
    from llm import models as _MODELS
    _models_guard = _MODELS.use_path(tmp / 'llm_models.json')
    _models_guard.__enter__()

    # ★★ 用量窗要**指着自己的夹具库**（2026-10-10）。
    #   它左栏列的是**项目名**，而项目名是**用户数据**——拿真实的 `usage.db`
    #   去查，判据会把「甲项目」这种中文项目名当成"漏译"（本机一次报了 23 处）。
    #   这与本文件既有做法同源：**夹具一律用纯英文名**，把"用户数据"这类噪音掐掉。
    #   ⚠ 反过来说：**不能**把中文项目名加进 `ALLOW` —— 那就等于放行所有含
    #     "项目"两个字的文案，而"漏译的标题"正是要抓的东西（见 `_PATH_WORDS` 那段）。
    #   ⚠ 举例也用**中性词**（甲项目/乙项目）：这一支被判据本身盯着
    #     —— `verify_generic_project` 不许判据里出现**具体作品**的名字，
    #     注释里举例也不行（第一版我在这里写了真实项目名，当场被它抓住）。
    # [EN] ★★ The usage window must **point at its own fixture library** (2026-10-10).
    # [EN] Its left column lists **project names**, and project names are **user data** — with a real
    # [EN] `usage.db`
    # [EN] it would treat Chinese project names like "Project A" as "miss-translations" (once reported 23
    # [EN] on this machine).
    # [EN] This is the same approach this file already uses: **fixtures always use pure English names**, to
    # [EN] cut out noise like "user data".
    # [EN] ⚠ Conversely: **do not** add Chinese project names to `ALLOW` — that would be letting through
    # [EN] all copy containing
    # [EN] the word "project", whereas "miss-translated titles" is exactly what we are trying to catch (see
    # [EN] the `_PATH_WORDS` section).
    # [EN] ⚠ Examples also use **neutral words** (Project A/Project B): this branch is watched by the check
    # [EN] itself
    # [EN] — `verify_generic_project` forbids the check from containing names of **specific works**,
    # [EN] even in comments (in the first version I wrote a real project name here and got caught
    # [EN] immediately).
    from llm import usage as _U
    _usage_db = tmp / 'usage.db'
    _U.db_path = lambda: _usage_db
    _U.record(model='deepseek-chat', purpose='crew_novelist', in_tok=100,
              out_tok=20, cost=0.01, module='NovelWorldSimulator',
              project='FixtureProject', run='Run1', agent='小说作家',
              path=_usage_db)

    async def check(label: str, root=None):
        page.update()
        await asyncio.sleep(0.45)
        texts = visible_texts(root if root is not None else page)
        hits = bad(texts)
        report['surfaces'][label] = hits
        ok(f'{label}：英文界面下没有中文', not hits,
           f'{len(hits)} 处：' + ' | '.join(hits[:4]))
        return hits

    try:
        # ① 开始界面（无项目）
        # [EN] ① Start screen (no project)
        app.current_project = None
        app._view = 'start'
        app.show_start_screen()
        await check('开始界面（无项目）')

        # ② 开始界面（有项目）
        # [EN] ② Start screen (with project)
        proj = Project.create_new(CFG.projects_dir(), PROJ)
        RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
        app._activate_project(proj)
        app.show_start_screen()
        await check('开始界面（有项目）')

        # ③ 运行界面
        # [EN] ③ Runtime screen
        app.show_main_screen()
        await check('运行界面')

        # ④~⑫ 九个对话框
        # [EN] ④~⑫ Nine dialogs
        for label, meth in (('帮助 · 使用说明', 'show_help_dialog'),
                            ('消息历史', 'show_messages_dialog'),
                            ('开卷 · 导入向导', 'show_import_wizard'),
                            ('天机 · 程序设置', 'show_global_settings'),
                            ('拾卷 · 管理项目', 'show_projects_dialog'),
                            ('书斋 · 本书设置', 'show_project_settings'),
                            ('风格参数说明', 'show_style_help_dialog'),
                            ('起　笔', 'show_start_story_dialog'),
                            ('导出 · 打包设定集', 'show_export_dialog'),
                            # ★ 2026-10-26：**新窗口必须进这个清单**，否则它整窗中文
                            #   也没人守（`show_usage_dialog` 就是这么漏了一整年 ——
                            #   判据从来没打开过它）。
                            # [EN] ★ 2026-10-26: **a new window must join this list**, or it can be
                            # [EN] Chinese throughout with nobody guarding it (`show_usage_dialog`
                            # [EN] leaked for a whole year exactly like this: the check never opened it).
                            ('剧情总览', '_open_story_flow'),
                            # ★ 2026-10-10 补：这一窗**原来是整窗硬编码中文**的
                            #   —— 产品里唯一一个没做双语的窗口。根因不是"忘了翻"，
                            #   而是**判据从来没打开过它**（这个清单里没有它，
                            #   它自己还因为用了 Flet 1.0 不存在的 API 一次都没打开成功）。
                            #   ⇒ 补文案的同时必须把它加进来，否则"翻了"同样没人守。
                            # [EN] ★ Added 2026-10-10: this window **was originally hard-coded Chinese throughout**
                            # [EN] — the only window in the product that was never bilingualized. The root cause is not "forgot to
                            # [EN] translate",
                            # [EN] but that **the check never opened it** (it was not in this list,
                            # [EN] and it itself failed to open even once because it used an API that does not exist in Flet 1.0).
                            # [EN] ⇒ While adding the copy it must also be added here, otherwise "translated" also has no one
                            # [EN] guarding it.
                            ('用量 · LLM 用量', 'show_usage_dialog')):
            fn = getattr(app, meth, None)
            if fn is None:
                ok(f'{label}：找得到入口', False, meth)
                continue
            try:
                fn()
            except Exception as exc:                            # noqa: BLE001
                ok(f'{label}：能打开', False, repr(exc))
                continue
            page.update()
            await asyncio.sleep(0.5)
            dlg = next((d for d in reversed(VU.open_dialogs(page))
                        if not isinstance(d, ft.SnackBar)), None)
            if dlg is None:
                ok(f'{label}：能打开', False, '没有对话框')
                continue
            await check(label, dlg)
            while VU.open_dialogs(page):
                page.pop_dialog()
            page.update()
            await asyncio.sleep(0.25)

        # ⑫b 拾卷 · **回收站页签**（2026-10-26 补）。
        #   ★ 为什么必须单独一步：回收站是拾卷里"最左边那个 Tab"的**另一页**，
        #     `_switch('trash')` 时才把 `pane_box.content` 换成它 ⇒ 上面那一轮
        #     "打开拾卷查一遍"看到的是**拾卷页**，回收站那一页根本不在控件树上。
        #     实测后果：整页七十多条文案一条英文都没登记，判据却一直绿着
        #     （"没被打开过的界面 = 没被守住的界面"）。
        #   ⚠ 不能靠 `walk(dlg)` 收"没选中的页"：它是替换式渲染，没切过去就不存在。
        # [EN] ⑫b Open Story · **the recycle-bin tab** (added 2026-10-26).
        # [EN] ★ Why a separate step: the bin is **another page** of the leftmost tab, swapped in
        # [EN] only by `_switch('trash')` ⇒ the step above inspects the Open Story page, and the bin
        # [EN] page is not in the control tree at all. Measured consequence: 70-odd strings on that
        # [EN] page had no English registered while the check stayed green
        # [EN] ("a screen nobody opens is a screen nobody guards").
        # [EN] ⚠ `walk(dlg)` cannot collect an unselected page either: rendering replaces the
        # [EN] content, so it simply does not exist until switched.
        app.show_projects_dialog()
        page.update()
        await asyncio.sleep(0.5)
        dlg = next((d for d in reversed(VU.open_dialogs(page))
                    if not isinstance(d, ft.SnackBar)), None)
        btn = (next((c for c in VU.walk(dlg)
                     if getattr(c, '_tab_key', '') == 'trash'), None) if dlg else None)
        if btn is None:
            ok('拾卷 · 回收站：找得到页签按钮', False, '没有 _tab_key=trash 的控件')
        else:
            btn.on_click(None)
            page.update()
            await asyncio.sleep(0.45)
            await check('拾卷 · 回收站页签', dlg)
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()
        await asyncio.sleep(0.25)

        # ⑬ 天机：**整框查一遍**（Flet 1.0 的 `Tabs` 内容是 `content=Column([TabBar,
        #   TabBarView])`，没有 `.tabs` —— 第一版按 `.tabs` 取，当场 AttributeError），
        #   再把每个选项卡切一遍（TabBarView 有可能只挂当前那一页）。
        # [EN] ⑬ Tianji: **check the whole frame** (in Flet 1.0 `Tabs` content is `content=Column([TabBar,
        # [EN] TabBarView])`, there is no `.tabs` — the first version fetched by `.tabs` and got an
        # [EN] AttributeError on the spot),
        # [EN] then switch through each tab (TabBarView may only mount the current page).
        app.show_global_settings()
        page.update()
        await asyncio.sleep(0.6)
        dlg = next((d for d in reversed(VU.open_dialogs(page))
                    if not isinstance(d, ft.SnackBar)), None)
        tabs = next((c for c in VU.walk(dlg) if isinstance(c, ft.Tabs)), None) if dlg else None
        if tabs is None:
            ok('天机里找得到选项卡', False, '没找到 Tabs')
        else:
            report['n_tabs'] = int(getattr(tabs, 'length', 0) or 0)
            await check('天机 · 全部选项卡一起查', dlg)
            for i in range(report['n_tabs']):
                tabs.selected_index = i
                await check(f'天机 · 第 {i + 1}/{report["n_tabs"]} 个选项卡', dlg)
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()

        # ⑭ ★ **拼出来的文案**（不在任何控件树里，前面那些界面判据都碰不到）：
        #   能力校验的备注、纠错说明、器械摘要……都是 `t()` 现拼的字符串。
        #   这类东西只能**直接调函数**去查 —— 而且正是"动态取值"最容易漏登记的那一类。
        # [EN] ⑭ ★ **Assembled copy** (not in any control tree; the earlier UI checks cannot reach it):
        # [EN] ability-check notes, correction explanations, item summaries... are all strings assembled on the
        # [EN] fly by `t()`.
        # [EN] Such things can only be checked by **calling the function directly** — and they are exactly the
        # [EN] kind most easily left unregistered for "dynamic values".
        from llm.capabilities import CAP_KEYS, CAP_META, Fix as _Fix
        from sim.setup import settings_summary
        from gui.app_flet import _clip
        gen: list[tuple[str, str]] = [
            ('_clip 省略后缀', _clip('x' * 40, 10)),
            ('settings_summary', settings_summary(
                {'people': [1, 2], 'nodes': [1], 'places': [1], 'foreshadows': [1]})),
            ('Fix.human（自动填入）',
             _Fix('LLM_CAP_JSON_MODE', 'JSON 模式', None, True, 'm', False).human()),
            ('Fix.human（纠错改回）',
             _Fix('LLM_CAP_JSON_MODE', 'JSON 模式', False, True, 'm', True).human()),
        ]
        for k in CAP_KEYS:
            gen.append((f'CAP_META[{k}] 说明', t(CAP_META[k][2])))
        gm = bad([v for _n, v in gen])
        report['generated'] = {n: v for n, v in gen}
        ok('⑭ ★ 现拼出来的文案（能力说明 / 摘要 / 纠错）在英文下也没有中文',
           not gm, f'{len(gm)} 处：' + ' | '.join(gm[:3]))

        # ⑮ ★★ **提问对话框**（2026-10-11 加）。
        # [EN] ⑮ ★★ **Ask dialog** (added 2026-10-11).
        #
        # 为什么必须进来：这一窗是**新做的**（岔路口 / 导演介入 / 预算 /
        # 存档点 四处共用），而上一轮的教训写在这儿 ——
        #   「没被判据看过的东西 = 没做」：
        #   `show_usage_dialog` 那次就是"整窗硬编码中文"而**判据从来没打开过它**。
        # 所以这里**主动把它撑起来**：不靠某个用户动作触发，直接调
        # `app._on_ask(...)`（它就是主循环那条通道的落点）。
        # [EN] Why it must be included: this window is **newly built** (shared by fork / director intervention
        # [EN] / budget /
        # [EN] checkpoint), and the lesson from last round is written here —
        # [EN] "What has not been looked at by a check = not done":
        # [EN] the `show_usage_dialog` case was "hard-coded Chinese throughout" while **the check never opened
        # [EN] it**.
        # [EN] So here we **proactively prop it up**: not relying on some user action to trigger it, directly
        # [EN] call
        # [EN] `app._on_ask(...)` (it is the landing point of that channel from the main loop).
        #
        # ⚠ 只查**题干与选项**由界面自己产出那三个 kind（`checkpoint` /
        #   `intervention` / `budget`）；岔路口的选项是**导演现写的走向**
        #   （`propose_branches`），本来就翻不了，查它只会得到假红。
        # [EN] ⚠ Only check the three kinds where the **prompt and options** are produced by the UI itself
        # [EN] (`checkpoint` /
        # [EN] `intervention` / `budget`); the fork options are **director-written directions**
        # [EN] (`propose_branches`), which cannot be translated anyway, and checking them would only yield
        # [EN] false reds.
        app.show_main_screen()
        await check('运行界面（放提问对话框之前）')
        # ⚠ `_on_ask` 头一行是 `if not self.session: return` —— 不塞一个会话
        #   进去，它会**直接什么都不做**（判据报"没有对话框"，
        #   而那看起来像"对话框坏了"，其实是夹具没搭台）。
        #   这里只要一个**极小的替身**：`_on_ask` 只用到 `session.loop`，
        #   而 `_branch_brief(loop)` 只读 `loop.world`（各段自己 try/except）。
        # [EN] ⚠ The first line of `_on_ask` is `if not self.session: return` — without putting a session
        # [EN] in, it will **directly do nothing** (the check reports "no dialog",
        # [EN] and that looks like "the dialog is broken", but actually the fixture did not set the stage).
        # [EN] Here you only need a **tiny stand-in**: `_on_ask` only uses `session.loop`,
        # [EN] and `_branch_brief(loop)` only reads `loop.world` (each section has its own try/except).
        if app.session is None:
            from types import SimpleNamespace
            from world.state import WorldState
            _w = WorldState()
            # ⚠ 场景名用**ASCII**：它是**用户数据**（来自设定集），和我们
            #   翻不翻没关系 —— 这里填中文只会让本判据报一条假红，
            #   而假红比真红更坏（看多了就没人看这一项了）。
            #   故事时辰那条另有 `STORY_CLOCK_RE` 的窄豁免。
            # [EN] ⚠ Use **ASCII** for scene names: they are **user data** (from the setting book) and have nothing
            # [EN] to do with whether we translate — putting Chinese here would only make this check report a false
            # [EN] red,
            # [EN] and false reds are worse than true reds (once seen too often, no one looks at this item).
            # [EN] The story-clock item has a separate narrow exemption via `STORY_CLOCK_RE`.
            _w.scene = 'Riverside Teahouse'
            app.session = SimpleNamespace(loop=SimpleNamespace(world=_w))
        for _kind in ('checkpoint', 'intervention', 'budget'):
            try:
                app._on_ask({
                    'kind': _kind,
                    'title': '（主循环给的中文兜底，界面应换掉它）',
                    'why': '（同上）',
                    'options': [],
                    'allow_custom': True,
                    'wait': 0,
                    # 让界面把 `{day}/{every}/{used}/{cap}` 都填上真数
                    # [EN] Make the UI fill in real numbers for `{day}/{every}/{used}/{cap}`
                    'data': {'day': 2, 'every': 3, 'used': '123,456',
                             'cap': '500,000', 'cap2': '1,000,000'},
                })
            except Exception as exc:                            # noqa: BLE001
                ok(f'提问对话框（{_kind}）：能打开', False, repr(exc))
                continue
            page.update()
            await asyncio.sleep(0.45)
            dlg = next((d for d in reversed(VU.open_dialogs(page))
                        if not isinstance(d, ft.SnackBar)), None)
            if dlg is None:
                ok(f'提问对话框（{_kind}）：能打开', False, '没有对话框')
                continue
            hits = await check(f'提问对话框 · {_kind}', dlg)
            # ★ 顺带证实"界面真的按 kind 换了自己的英文" ——
            #   不换的话上面那条只能证明"没有中文"，证明不了"有英文内容"
            #   （空白对话框也算"没有中文"）。
            # [EN] ★ Also confirm "the UI really switched to its own English by kind" —
            # [EN] without the switch, the above only proves "no Chinese", not "has English content"
            # [EN] (a blank dialog also counts as "no Chinese").
            _txt = ' '.join(visible_texts(dlg))
            report.setdefault('ask_dialog_texts', {})[_kind] = _txt[:200]
            _is_key = {'checkpoint': ('Day', 'checkpoint'),
                       'intervention': ('director', 'step in'),
                       'budget': ('token', 'budget')}[_kind]
            ok(f'提问对话框（{_kind}）：界面**真的换成了自己的英文**'
               '（不是靠"一片空白"混过中文检查）',
               any(w in _txt for w in _is_key) or bool(hits),
               _txt[:110])
            while VU.open_dialogs(page):
                page.pop_dialog()
            page.update()
            await asyncio.sleep(0.25)

        # ⑯ ★★★ **提问对话框的文案，直接查那个纯函数**（2026-10-11）。
        # [EN] ⑯ ★★★ **For the ask dialog copy, directly check that pure function** (2026-10-11).
        #
        # 上面 ⑮ 是在**控件树**上查的，而 `visible_texts` 只收 `ft.Text` /
        # `TextField` / 按钮里的字 —— 题干与选项用的是 Markdown（`mk_hint`）
        # 和 `Radio`，**根本没被收到**。所以⑮"没有中文"很可能是"没看见"。
        # 这里直接调 `_ask_texts`（纯函数、不经控件树），把它逐字验掉：
        #   · 四个 kind 的标题 / 问句 / 每个选项的标签与后果都不许有中文；
        #   · 而且**必须真的出现那串英文关键词** —— 否则"把文案全删掉"
        #     也能让上一条通过（那是典型的名字断言）。
        # [EN] The above ⑮ checks on the **control tree**, while `visible_texts` only collects `ft.Text` /
        # [EN] `TextField` / text in buttons — the prompt and options use Markdown (`mk_hint`)
        # [EN] and `Radio`, and are **not collected at all**. So ⑮'s "no Chinese" is very likely "did not see".
        # [EN] Here directly call `_ask_texts` (pure function, not through the control tree), and verify it
        # [EN] verbatim:
        # [EN] · The title / question / each option's label and consequence for the four kinds must not contain
        # [EN] Chinese;
        # [EN] · And **that string of English keywords must really appear** — otherwise "delete all the copy"
        # [EN] would also let the previous item pass (that is a typical name assertion).
        _KINDS = {
            'checkpoint': [{'id': 'go'}, {'id': 'hold'}],
            'intervention': [{'id': 'accept'}, {'id': 'skip'}],
            'budget': [{'id': 'extend'}, {'id': 'stop'}],
        }
        # ★★★ 2026-10-27：`intervention` 的关键词去掉了 `Follow the director`。
        #
        #   2026-10-26 修「导演介入只有 accept/skip 两个选项」时，把那两个硬编码选项
        #   **整条删掉**了（选项改由主循环按真实方向现生成，见 `_ASK_TEXT['intervention']`
        #   里那段说明）。于是这里的第三个关键词**指向一个已经不存在的字面** ——
        #   判据从此恒假，红的不是产品、是它自己没跟上。
        #   ⇒ 只留**界面自己的框架文案**（标题 `The director wants to step in`），
        #     再加一条"选项列表非空"来证明"有内容"，而不是靠某个具体措辞。
        #   ★ 教训：判据里钉**措辞**就等于把自己绑在会变的文案上；该钉的是
        #     "这一层真的换出英文了吗"。
        # [EN] ★★★ 2026-10-27: `Follow the director` is gone from `intervention`'s keywords. When the
        # [EN] 2026-10-26 fix removed the hardcoded accept/skip options (the main loop now generates
        # [EN] real directions), that literal disappeared -- so this keyword pointed at nothing and the
        # [EN] check was permanently false: the red was the criterion's own staleness, not the product.
        # [EN] => Keep only the UI's **own** frame copy (the title) and add "the option list is
        # [EN] non-empty" as proof of content, instead of leaning on one particular phrasing.
        # [EN] ★ Lesson: pinning **wording** in a criterion ties it to copy that will change; pin
        # [EN] "did this layer really switch to English".
        _kw = {'checkpoint': ('Day', 'checkpoint', 'Keep writing'),
               'intervention': ('director', 'step in'),
               'budget': ('token', 'budget', 'double the budget')}
        _probe = {'day': 2, 'every': 3, 'used': '123,456',
                  'cap': '500,000', 'cap2': '1,000,000'}
        for _k, _opts in _KINDS.items():
            try:
                _t2, _w2, _o2 = app._ask_texts({
                    'kind': _k, 'title': '中文兜底', 'why': '中文兜底',
                    'options': _opts, 'data': dict(_probe)})
                _all = ([_t2, _w2]
                        + [str(x.get('标题') or '') for x in _o2]
                        + [str(x.get('后果') or '') for x in _o2])
                _hit2 = bad(_all)
                _joined = ' '.join(_all)
                ok(f'⑯ ★★★ 提问对话框（{_k}）的题干与选项在英文下**逐字**都是英文'
                   '（直接查纯函数 —— 控件树收不到 Markdown / Radio 里的字，'
                   '光靠⑮ 是"没看见"不是"没有"）',
                   not _hit2, f'{len(_hit2)} 处：' + ' | '.join(_hit2[:3]))
                ok(f'⑯ ★★ 提问对话框（{_k}）**真的换出了英文**'
                   '（不是靠"文案为空"混过去）',
                   all(w.lower() in _joined.lower() for w in _kw[_k])
                   and bool(_o2),
                   _joined[:140])
                report.setdefault('ask_texts', {})[_k] = _all
            except Exception as exc:                            # noqa: BLE001
                ok(f'⑯ 提问对话框（{_k}）文案可查', False, repr(exc))

        n_ok = sum(1 for i in ITEMS if i['ok'])
        report['items'] = ITEMS
        report['ok'] = n_ok == len(ITEMS)
        report['n_bad_total'] = sum(len(v) for v in report['surfaces'].values())
        print(f'\n英文界面中文检查：{n_ok}/{len(ITEMS)}，'
              f'未翻译文案共 {report["n_bad_total"]} 处')
    except Exception:                                           # noqa: BLE001
        report['items'] = ITEMS
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
        print(report['fatal'])
    finally:
        OUT.mkdir(parents=True, exist_ok=True)
        try:
            _models_guard.__exit__(None, None, None)
        except Exception:                                        # noqa: BLE001
            pass
        (OUT / 'ui_english_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
        VU.safe_rmtree(tmp, ignore_errors=True)
        await shutdown(page, code=0 if report.get('ok') else 1)


if __name__ == '__main__':
    ft.run(main)
