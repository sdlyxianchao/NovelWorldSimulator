# -*- coding: utf-8 -*-
"""验证：帮助面板的关键字检索 + 开始界面右上角的帮助按钮 + 没配 LLM 时「问个问题」变灰。

要证的四件事（每条都要能红）：

  ① **检索本身对** —— 命中 / 不命中 / 多词是「都出现」 / 一个都没全命中时退回
     「只沾到一部分」并且**标明不保证相关**；大小写不敏感；中英各走各的手册。
  ② **一次模型都不调** —— 关键字检索是纯本地的（`search_manual()`），
     所以**没配 LLM 也能用**，这正是「问个问题」用不了时的退路。
  ③ **在界面上真用得到** —— 开始界面**右上角**有「❓ 帮助」（像素取证：真的画在
     那个角上，不是只挂在控件树里）；帮助默认页有检索框，输入能过滤左栏目录、
     点结果能看到命中处。
  ④ **没配 LLM → 「问个问题」变灰** —— 输入框 / 发送 / 示例按钮全 disabled，
     并说清"缺什么""去哪配"；配好之后必须恢复可点（反例）。
  ⑤ **代码围栏不许被当成标题** —— 用户报「左栏有个**登场人物**，为什么没序号」，
     根子是这个（见 `fence_checks()`）。

用法：.venv\\Scripts\\python.exe tools/verify_help_search.py [--logic-only]
产出：assets/screenshots/help_search_*.png / help_search_report.json

English:
Verification: keyword search in the help panel + the help button in the top-right of the start
screen + "Ask a question" turns gray when no LLM is configured.
Four things to prove (each must be able to go red):
  ① **The search itself is correct** — hit / miss / multiple words means "all appear" / when not all match, fall back
     to "only partially matched" and **mark that relevance isn't guaranteed**; case-insensitive; Chinese and English each use their own manual.
  ② **Not a single model call** — keyword search is purely local (`search_manual()`),
     so **it works with no LLM configured**, which is exactly the fallback when "Ask a question" is unavailable.
  ③ **Actually usable in the UI** — the start screen has "❓ Help" in the **top-right** (pixel evidence: really drawn in
     that corner, not just attached in the widget tree); the help default page has a search box, typing filters the left TOC,
     and clicking a result shows the hit location.
  ④ **No LLM configured → "Ask a question" turns gray** — input box / send / example buttons all disabled,
     and clearly state "what's missing" and "where to configure it"; once configured it must become clickable again (counterexample).
  ⑤ **Code fences must not be treated as headings** — user reported "the left TOC has a **登场人物**, why no number",
     the root cause is this (see `fence_checks()`).
Usage: .venv\\Scripts\\python.exe tools/verify_help_search.py [--logic-only]
Output: assets/screenshots/help_search_*.png / help_search_report.json
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑（不起窗口）
# [EN] A. Pure logic (no window)
# ══════════════════════════════════════════════════════════════
# 夹具：**故意造得能隔离每一条规则**（别拿真手册当夹具 —— 手册一改判据就漂）
# [EN] Fixture: **deliberately built to isolate each rule** (don't use the real manual as fixture --
# [EN] once the manual changes, the criteria drift)
FIX = [
    ('甲章 · 规则说明', '这一章专门讲规则。规则很重要，规则要写清楚。'),
    ('乙章 · 杂记', '这里提到 关键 两个字；规则在这儿只顺口提了一句。'),
    ('丙章 · 无关', '这一段什么都有，就是没有那两个词。'),
]


def logic_checks() -> bool:
    from gui.app_flet import read_manual, search_manual, _snippets
    ok = True

    # ── A1 空 / 纯空白查询 → 空结果（"没查"和"查了没中"是两件事）──
    # [EN] -- A1 empty / whitespace-only query -> empty result ("didn't query" and "queried but no hit" are
    # [EN] two different things) --
    ok &= rec('A1 空查询与纯空白查询都返回空（界面用"空 = 显示全部"，是另一条分支）',
              search_manual(FIX, '') == [] and search_manual(FIX, '   ') == []
              and search_manual(FIX, '\n\t') == [],
              f"{search_manual(FIX, '   ')}")

    # ── A2 单词命中，且**命中标题的排最前** ──
    # [EN] -- A2 single word hit, and **title hits rank first** --
    rows = search_manual(FIX, '规则')
    ok &= rec('A2 ★ 单词检索命中（甲、乙都在讲规则；丙一个字都不沾）',
              [r['idx'] for r in rows] == [0, 1] or [r['idx'] for r in rows] == [1, 0],
              [(r['idx'], r['title'], r['count']) for r in rows])
    ok &= rec('A2b ★★ **命中标题的排在最前**（标题是作者写的"这节讲什么"，最该信）',
              rows and rows[0]['idx'] == 0 and rows[0]['in_title'] is True,
              [(r['idx'], r['in_title']) for r in rows])
    ok &= rec('A2c **完全不沾的那一节不许出现**（检索的意义就是收敛）',
              all(r['idx'] != 2 for r in rows), [r['idx'] for r in rows])

    # ── A3 只在正文里出现的词：说清"标题没中" ──
    # [EN] -- A3 word only appearing in body: make clear "title didn't hit" --
    rows = search_manual(FIX, '关键')
    ok &= rec('A3 ★ 只命中正文时 `in_title=False`（界面靠它把标题色写淡）',
              len(rows) == 1 and rows[0]['idx'] == 1 and rows[0]['in_title'] is False,
              [(r['idx'], r['in_title']) for r in rows])
    ok &= rec('A3b 命中处给得出摘录，且摘录里**真的有那个词**',
              rows and rows[0]['snippets']
              and all('关键' in s for s in rows[0]['snippets']),
              rows[0]['snippets'] if rows else '')

    # ── A4 ★★ 多词 = 「都出现」（AND），不是"沾一个就行" ──
    # [EN] -- A4 ★★ multi-word = "all appear" (AND), not "hit any one" --
    both = search_manual(FIX, '规则 关键')
    ok &= rec('A4 ★★ 两个词都要出现：只剩乙（甲没有"关键"、丙两样都没有）',
              [r['idx'] for r in both] == [1], [(r['idx'], r['title']) for r in both])
    ok &= rec('A4b 多词比单词更收敛（一节都不多给）',
              len(both) <= len(search_manual(FIX, '规则'))
              and len(both) <= len(search_manual(FIX, '关键')),
              f"{len(both)} vs 规则 {len(search_manual(FIX, '规则'))}")

    # ── A5 反例：压根没有的词 → 空（**不许随便给几节**）──
    # [EN] -- A5 counterexample: word that doesn't exist at all -> empty (**don't just hand out a few
    # [EN] sections**) --
    ok &= rec('A5 ★ 反例：一个完全不存在的词 → 空结果',
              search_manual(FIX, '绝不可能出现的词zzz') == [], '')

    # ── A6 ★ 都命中不全 → 退回"沾到一部分"，且**每一行都标 loose** ──
    # [EN] -- A6 ★ not all hit -> fall back to "hit some", and **every line marked loose** --
    loose = search_manual(FIX, '规则 绝不可能出现的词zzz')
    ok &= rec('A6 ★★ 一个词谁都不含 → 退回「只沾到一部分」（比冷冰冰的"没找到"有用）',
              len(loose) >= 1 and all(r['loose'] for r in loose),
              [(r['idx'], r['loose']) for r in loose])
    ok &= rec('A6b ★ 而且**明说它可能不相关**（界面文案要按 loose 换一句）',
              all(r['loose'] for r in loose) and loose[0]['idx'] == 0,
              str([r['idx'] for r in loose]))

    # ── A7 摘录的形状：≤5 条、条条含关键词、单行、有界 ──
    # ⚠ 夹具的命中点必须**互相不重叠**（间隔 > 窗口长 80 字），否则
    #   `_snippets` 会把挤在一起的命中当同一处跳掉 —— 那时 limit=5 与 limit=99
    #   都只吐 3 条，"超限"这个变异就测不出来（反例法抓到的）。
    # [EN] -- A7 shape of snippets: <=5 items, each containing the keyword, single line, bounded --
    # [EN] ⚠ Fixture hit points must **not overlap each other** (gap > window length of 80 chars),
    # [EN] otherwise
    # [EN] `_snippets` will treat clustered hits as the same spot and skip -- then limit=5 and limit=99
    # [EN] both only emit 3 items, and the "exceeds limit" mutation can't be tested (caught by
    # [EN] counterexample method).
    many = [('丁章', ('规则' + '甲' * 90) * 10)]
    rows = search_manual(many, '规则')
    sn = rows[0]['snippets'] if rows else []
    ok &= rec('A7 ★ 摘录最多 5 条（一章里命中几十处时不能把正文顶爆）',
              len(sn) == 5, f'{len(sn)} 条（夹具里有 10 处互不重叠的命中）')
    ok &= rec('A7b 每条摘录都含关键词、都是**单行**（换行已压成空格）',
              all('规则' in s and '\n' not in s for s in sn), str(sn[:2]))
    ok &= rec('A7c 摘录长度有界（一行内能看完，不是整段抄回来）',
              all(len(s) <= 120 for s in sn), str([len(s) for s in sn]))
    ok &= rec('A7d 返回结构齐全（界面按这些键取值，少一个就炸）',
              all(set(r) >= {'idx', 'title', 'count', 'in_title', 'loose',
                             'snippet', 'snippets'} for r in rows),
              str(sorted(rows[0]) if rows else []))

    # ── A8 大小写不敏感（英文手册就是按英文关键字查）──
    # [EN] -- A8 case-insensitive (English manual is queried by English keywords) --
    EN = [('Chapter A · Run mode', 'The run mode decides when to pause.'),
          ('Chapter B', 'Nothing here.')]
    ok &= rec('A8 ★ 大小写不敏感（输 `run` 也命中 `Run mode`）',
              [r['idx'] for r in search_manual(EN, 'run')] == [0]
              and [r['idx'] for r in search_manual(EN, 'RUN')] == [0],
              str([r['idx'] for r in search_manual(EN, 'RUN')]))

    # ── A9 ★★ 一次模型都不调（这条是"没配 LLM 也能用"的全部依据）──
    # [EN] -- A9 ★★ model is not called even once (this is the entire basis for "usable without LLM
    # [EN] configured") --
    from llm.router import llm
    calls = {'n': 0}
    real_chat = llm.chat

    async def counting(*a, **kw):
        calls['n'] += 1
        return await real_chat(*a, **kw)

    llm.chat = counting
    try:
        search_manual(FIX, '规则')
        search_manual(FIX, '规则 关键')
        search_manual(FIX, '')
    finally:
        llm.chat = real_chat
    ok &= rec('A9 ★★ 关键字检索**一次模型都不调**（纯本地 → 没配 LLM 也能用）',
              calls['n'] == 0, f'{calls["n"]} 次')

    # ── A10 真手册上走一遍（夹具之外还得见真章）──
    # [EN] -- A10 run once on the real manual (beyond the fixture, must see real results) --
    intro, secs = read_manual(APP_DIR / '使用说明.md')
    items = ([(t('开篇'), intro)] if intro.strip() else []) + list(secs)
    hits = search_manual(items, '运行模式')
    ok &= rec('A10 ★ 真手册：`运行模式` 能命中，且**标题里就有**（排最前）',
              len(hits) >= 1 and hits[0]['in_title'] is True,
              [h['title'][:26] for h in hits[:3]])
    ok &= rec('A10b 真手册：跟软件无关的词给不出结果（宁可说没有）',
              search_manual(items, '奥运会闭幕式舞蹈') == [], '')
    ok &= rec('A10c 手册被切成了章（没有节就是读文件出了问题）',
              len(items) >= 15, f'{len(items)} 节')

    report['fixture_rows'] = [{'q': q, 'n': len(search_manual(FIX, q))}
                              for q in ('规则', '关键', '规则 关键', '不存在zzz')]
    return ok


# ══════════════════════════════════════════════════════════════
#  D. 代码围栏不许被当成标题（`util.md`）
# [EN] D. Code fences must not be treated as headings (`util.md`)
# ══════════════════════════════════════════════════════════════
# 夹具：**围栏里放假的二级标题** —— 每一段都能隔离一条规则。
# [EN] Fixture: **put fake level-2 headings inside fences** -- each paragraph can isolate one rule.
_FENCE_DOC = (
    "# 前言\n"
    "\n"
    "## 真章一\n"
    "\n"
    "正文一。\n"
    "\n"
    "```markdown\n"
    "## 假标题甲\n"
    "示例内容\n"
    "```\n"
    "\n"
    "## 真章二\n"
    "\n"
    "正文二。\n"
    "\n"
    "~~~\n"
    "## 假标题乙\n"
    "~~~\n"
    "\n"
    "## 真章三\n"
)
# 未闭合的围栏：**绝不能**把后面整片屏蔽掉（否则文档写坏一个 ``` 目录就空了）
# [EN] Unclosed fence: **must never** shield the entire rest (otherwise one broken ``` in the doc
# [EN] empties the directory)
_UNCLOSED_DOC = (
    "# 前言\n"
    "\n"
    "## 甲\n"
    "\n"
    "正文\n"
    "\n"
    "```markdown\n"
    "## 乙\n"
    "（这个围栏没闭合）\n"
    "\n"
    "## 丙\n"
)


def fence_checks() -> bool:
    """用户 2026-10-06 报的现象：「帮助信息里左边有一个**登场人物**是什么？为什么没序号」。

    根因：切分 Markdown 的正则**不认代码围栏**，而 `使用说明.md` §4.2.4
    「每轮开场」里的 ```markdown 示例块第 497 行就是 `## 登场人物`。
    于是它成了目录项（本来就不是章节，自然没序号），还**吞掉了 §4.3~§4.16**
    （实测 23158 字），点「4. 主界面详解」读不到那半个 §4。
    
        English:
    The symptom reported by the user on 2026-10-06: "What is this **登场人物** on the left of the help
    info? Why no number".
        Root cause: the regex that splits Markdown **doesn't recognize code fences**, and in `使用说明.md` §4.2.4
        So it became a TOC item (it was never a section, so of course no number), and also **swallowed §4.3~§4.16**
    """
    from util import md as MD
    from gui.app_flet import read_manual
    ok = True

    # ── D1 夹具：围栏里的 `##` 不是标题 ──
    # [EN] -- D1 fixture: `##` inside fence is not a heading --
    intro, secs = MD.split_h2(_FENCE_DOC)
    titles = [x for x, _ in secs]
    ok &= rec('D1 ★★ 围栏里的 `## 假标题甲` **不算章节**（这是用户报的那个 bug）',
              titles == ['真章一', '真章二', '真章三'] and '假标题甲' not in titles,
              str(titles))
    ok &= rec('D1b ★ `~~~` 围栏同样认（不是只认三个反引号）',
              '假标题乙' not in titles and '真章三' in titles, str(titles))
    ok &= rec('D1c ★ ```markdown 这种**带 info string** 的开头也认',
              titles.count('真章一') == 1 and '假标题甲' not in titles, str(titles))
    ok &= rec('D1d 围栏里的**内容没被删掉** —— 它仍在正文里（渲染时才显示为代码块）',
              '假标题甲' in dict(secs).get('真章一', '')
              and '示例内容' in dict(secs).get('真章一', ''),
              dict(secs).get('真章一', '')[:60].replace('\n', '⏎'))
    ok &= rec('D1e 前言照旧切出来（修围栏没把导言弄丢）',
              intro.strip() == '# 前言'.strip(), repr(intro))

    # ── D2 ★★ 未闭合的围栏**不屏蔽**（文档写坏一个 ``` 时宁可多切，不能整片丢）──
    # [EN] -- D2 ★★ unclosed fence **does not shield** (when one ``` is broken in the doc, prefer
    # [EN] over-splitting, never lose the whole block) --
    _, secs2 = MD.split_h2(_UNCLOSED_DOC)
    t2 = [x for x, _ in secs2]
    ok &= rec('D2 ★★ 围栏没闭合 → 后面的标题**照样切出来**'
              '（否则文档坏一个 ``` 目录就整片空了）',
              t2 == ['甲', '乙', '丙'], str(t2))

    # ── D3 ★★ 真手册：那个假目录项必须消失，且 §4 的正文不再被割裂 ──
    # [EN] -- D3 ★★ real manual: that fake directory entry must disappear, and §4's body is no longer split
    # [EN] --
    for lang, doc, cap, main_key, must in (
            ('zh', '使用说明.md', '登场人物', '4. 主界面详解',
             ('### 4.3', '### 4.5', '### 4.7', '### 4.10', '### 4.16')),
            ('en', 'User_Manual.md', 'On stage', '4. Main Interface',
             ('### 4.3', '### 4.5', '### 4.10'))):
        intro_i, secs_i = read_manual(APP_DIR / doc)
        items = ([(t('开篇'), intro_i)] if intro_i.strip() else []) + list(secs_i)
        names = [x for x, _ in items]
        d = dict(items)
        ok &= rec(f'D3 ★★ [{lang}] 左栏里**不再有**「{cap}」这一项'
                  f'（它是代码块里的示例，不是章节）',
                  cap not in names, str(names[:8]))
        ok &= rec(f'D3b ★★ [{lang}] 「{main_key}」的正文**含全部小节**'
                  f'（以前 §4.3~§4.16 被那个假标题吞走了）',
                  all(k in d.get(main_key, '') for k in must),
                  str([k for k in must if k not in d.get(main_key, '')]))

    # ── D4 ★ 检索侧同源：假路径不许留在标题里 ──
    # [EN] -- D4 ★ retrieval side shares origin: fake path must not remain in headings --
    from research import manual_qa as M
    for lang, cap in (('zh', '登场人物'), ('en', 'On stage')):
        secs_l = M.load_sections(lang, reload=True)
        bad = [s['title'] for s in secs_l if s['title'].startswith(cap)]
        ok &= rec(f'D4 ★★ [{lang}] 检索的章节路径里没有以「{cap}」开头的'
                  f'（否则模型引用会张冠李戴）',
                  not bad, str(bad[:3]))
    ok &= rec('D4b ★ 检索路径回到了正确的大章下（例：帮助面板在 §4.10）',
              any(h['title'].startswith('4. 主界面详解 › 4.10')
                  for h in M.search('帮助面板怎么看', 'zh', top_k=3)),
              str([h['title'][:34] for h in M.search('帮助面板怎么看', 'zh', top_k=2)]))

    # ── D5 ★★ 两处解析器**同一份实现**（行为一致，不是各写一遍）──
    # [EN] -- D5 ★★ two parsers **same implementation** (consistent behavior, not written twice) --
    sec_titles = [s['title'] for s in MD.split_sections(_FENCE_DOC)
                  if '›' not in s['title']]
    ok &= rec('D5 ★★ 帮助面板（按 ## 切）与问答检索（按 ##~#### 切）'
              '在同一份夹具上给出**一致**的顶级标题',
              sec_titles == ['真章一', '真章二', '真章三'], str(sec_titles))
    src_ok = 'from util.md import' in inspect.getsource(read_manual)
    import research.manual_qa as _MQ
    src_ok &= 'from util.md import' in inspect.getsource(_MQ._split_sections)
    ok &= rec('D5b 源码层面确认：两处都调 `util.md`（**唯一实现**）—— '
              '弱判据，配合 D5 的行为判据用',
              src_ok, '')
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 真机
# [EN] B. Real machine
# ══════════════════════════════════════════════════════════════
def magenta_px(png: bytes, box: tuple = None, *, tight: bool = True) -> int:
    """数品红像素。

    `tight=True` 只认"几乎纯品红"（`#ff00ff` 是不透明填充，画出来就是原色）——
    开始界面底下是淡彩水彩背景，用色相判据会把桃粉/樱色算进来。
    `box=(x0, y0, x1, y1)` 限定区域（用来证明"真的画在右上角"）。
    
        English:
    Count magenta pixels.
        `tight=True` only accepts "almost pure magenta" (`#ff00ff` is an opaque fill, drawn as the original color) —
        the bottom of the start screen is a light watercolor background, and a hue criterion would count peach pink / cherry pink.
        `box=(x0, y0, x1, y1)` restricts the region (used to prove "really drawn in the top-right").
    """
    if not png:
        return 0
    im = VU.image_of(png)
    W, H = im.size
    x0, y0, x1, y1 = box or (0, 0, W, H)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    px = im.load()
    n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if tight:
                if r > 230 and b > 230 and g < 60:
                    n += 1
            elif r > 135 and b > 135 and g < r - 45 and g < b - 45:
                n += 1
    return n


def _cyan_box(png: bytes):
    """右栏底色的 bbox（探针里给它染的是青）——用来定**车道**的 x 范围。
        English:
    bbox of the right column background (dyed cyan in the probe) — used to define the x range of the
    **lane**.
    """
    return _color_box(png, lambda r, g, b: b > 170 and g > 170 and r < min(g, b) - 45)


def _green_box(png: bytes, *, x_lo: int = 0, x_hi: int = 10 ** 9):
    """绿条的 bbox（**只在给定 x 范围里找**）。

    ⚠ 两个坑都是踩出来的：
      · 不能整屏找 —— 会撞上别处的金色/黄色元素（第一版量到"高 623"，
        比面板本身还高，一眼就知道量错了）；
      · 不能按原色匹配 —— 界面半透明（`UI_OPACITY`），纯绿会被混淡，
        按 `(0,255,0)` 精确匹配是 0。所以判**色相**：绿高、红蓝明显低。
    
        English:
    bbox of the green bar (**only searched within the given x range**).
        ⚠ Both pitfalls were learned the hard way:
          · Can't search the whole screen — it would hit gold/yellow elements elsewhere (the first version measured "height 623",
            taller than the panel itself, obviously wrong at a glance);
          · Can't match by original color — the UI is semi-transparent (`UI_OPACITY`), pure green gets diluted,
            exact match on `(0,255,0)` gives 0. So judge by **hue**: green high, red and blue clearly low.
    """
    return _color_box(png, lambda r, g, b: g > 170 and r < g - 45 and b < g - 45,
                      x_lo=x_lo, x_hi=x_hi)


def _color_box(png: bytes, pred, *, x_lo: int = 0, x_hi: int = 10 ** 9):
    if not png:
        return None
    im = VU.image_of(png)
    W, H = im.size
    px = im.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(H):
        for x in range(max(0, x_lo), min(W, x_hi)):
            r, g, b = px[x, y][:3]
            if pred(r, g, b):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _text_controls(root):
    return [c for c in VU.walk(root) if isinstance(c, ft.Text)]


def _find_button(root, label: str):
    """找"文字是 `label` 的按钮"。`mk_btn()` 造的 Button 文字挂在 `content` 上。
        English:
    Find the button whose "text is `label`". The Button text created by `mk_btn()` is attached to
    `content`.
    """
    for c in VU.walk(root):
        if getattr(c, 'on_click', None) and VU.text_of(c) == label:
            return c
    return None


def _find_help_dialog(page):
    return next((d for d in VU.open_dialogs(page)
                 if any('帮 助' in x for x in VU.all_texts(d))), None)


def _toc_holder(dlg):
    """左栏那个容器：里面装着 `Stack`（`App._scroll_bar` 的产物）。

    ★★ 2026-10-12 改为**优先用产品挂出来的抓手**（`_recap_toc_w`）：
      左栏宽度现在是**算出来的**（跟着窗口等比长大），按常量 `HELP_TOC_W` 找
      在最大化之后永远找不到 —— 本轮实测就是 0 行、连带 5 条前置一起红，
      看起来像"产品坏了"，其实是**判据在按旧尺寸找控件**。
    抓手不存在时退回常量（老对话框/老版本仍然能跑）。

        English:
    That container in the left column: it holds a `Stack` (a product of `App._scroll_bar`).
        ★★ 2026-10-12 changed to **prefer the handle the product exposes** (`_recap_toc_w`): the left
          column's width is now **computed** (growing in proportion to the window), so searching by the
          constant `HELP_TOC_W` never finds it after maximizing -- measured this round as 0 rows with 5
          preconditions going red along with it, looking like "the product is broken" when in fact **the
          criterion was locating the widget by its old size**.
        Falls back to the constant when the handle is absent (older dialogs/versions still work).
    """
    import gui.app_flet as AC
    wanted = int(getattr(dlg, '_recap_toc_w', 0) or 0) or int(AC.HELP_TOC_W)
    return next((c for c in VU.walk(dlg)
                 if isinstance(c, ft.Container)
                 and int(getattr(c, 'width', 0) or 0) == wanted
                 and isinstance(content_of(c), ft.Stack)), None)


def _toc_rows(dlg, *legacy) -> list:
    """左栏目录行 = 左栏 `ListView` 里带 `on_click` 的那些项。

    ⚠ 别再按"行宽 == `HELP_TOC_W - 14`"去找（第一版就是那样）——
    行宽现在由 `ListView` 的**紧约束**自动撑满，控件属性上是 `None`，
    按宽度找永远是 0 行（判据自己坏掉，而不是产品坏了）。
    多收一个 `*legacy` 只是让老调用点不改也能跑。
    
        English:
    Left TOC rows = the items in the left `ListView` that have `on_click`.
        ⚠ Don't look for it by "row width == `HELP_TOC_W - 14`" again (the first version did that) —
        row width is now automatically stretched to full by the **tight constraints** of `ListView`, and is `None` on the widget property,
        Searching by width always yields 0 rows (the criterion itself is broken, not the product).
        Accepting an extra `*legacy` just lets old call sites keep working without changes.
    """
    holder = _toc_holder(dlg)
    if holder is None:
        return []
    lv = next((c for c in VU.walk(holder) if isinstance(c, ft.ListView)), None)
    return [c for c in (getattr(lv, 'controls', None) or [])
            if getattr(c, 'on_click', None)]


def content_of(c):
    return getattr(c, 'content', None)


class _Ev:
    """假事件：`on_change=lambda e: _rebuild(e.control.value)` 只用到 `.control`。
        English:
    Fake event: `on_change=lambda e: _rebuild(e.control.value)` only uses `.control`.
    """

    def __init__(self, control):
        self.control = control


async def test_gui(page) -> bool:
    with VU.env_guard():
        return await _test_gui(page)


async def _test_gui(page) -> bool:
    import gui.app_flet as AC

    ok = True

    async def shot(name: str) -> bytes:
        png = await page.take_screenshot()
        (OUT / name).write_bytes(png or b'')
        return png or b''

    VU.isolate_projects_dir(Path(tempfile.mkdtemp(prefix='nws_helpsearch_')))
    VU.redirect_env_writes()          # 一启动就会跑能力校验 → `CFG.save()`
    # [EN] On startup it runs capability validation -> `CFG.save()`
    from gui.app_flet import NovelWorldApp

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.5)

    # ── B1 ★★ 开始界面右上角有「帮助」（带回调）──
    # [EN] -- B1 ★★ start screen top-right has "Help" (with callback) --
    start_nodes = list(VU.walk(page))
    label = t('❓ 帮 助')
    btn = next((c for c in start_nodes
                if getattr(c, 'on_click', None)
                and any(x == label for x in VU.all_texts(c))), None)
    ok &= rec('B1 ★★ 开始界面上有「帮助」按钮，而且**带回调**（不是画着好看的）',
              btn is not None, f'label={label!r}')

    # ── B2 ★★ 像素取证：它真的画在**右上角** ──
    # [EN] -- B2 ★★ pixel forensics: it's really drawn at **top-right** --
    if btn is not None:
        png0 = await shot('help_search_start.png')
        im = VU.image_of(png0)
        W, H = im.size
        corner = (max(0, W - 200), 0, W, 90)     # 右上角那一小块
        # [EN] that small block at top-right
        base = magenta_px(png0, corner)
        btn.bgcolor = '#ff00ff'
        page.update()
        await asyncio.sleep(0.6)
        png1 = await shot('help_search_start_marker.png')
        marked = magenta_px(png1, corner)
        elsewhere = magenta_px(png1, (0, 200, W, H))
        btn.bgcolor = None
        page.update()
        await asyncio.sleep(0.5)
        png2 = await shot('help_search_start_after.png')
        cleared = magenta_px(png2, corner)
        report['corner_px'] = [base, marked, elsewhere, cleared]
        ok &= rec('B2 ★★ 帮助按钮**真的画在右上角**（品红像素只出现在右上角那一块）',
                  marked > 40 and elsewhere == 0,
                  f'右上角 {marked} px，画面其余 {elsewhere} px')
        ok &= rec('B2b ★★ 反例：把底色去掉 → 那一块品红归零（判据不是恒真）',
                  base == 0 and cleared == 0, f'{base} → {marked} → {cleared}')

    # ── B3 ★ 点它 → 帮助面板真的开了（行为，不是查控件属性）──
    # [EN] -- B3 ★ click it -> help panel really opens (behavior, not checking widget attributes) --
    if btn is not None:
        btn.on_click(None)
        await asyncio.sleep(0.9)
        dlg = _find_help_dialog(page)
        ok &= rec('B3 ★★ 点右上角那个按钮 → 帮助面板真的打开了', dlg is not None,
                  f'{len(list(VU.open_dialogs(page)))} 个对话框')
    else:
        dlg = None
        ok &= rec('B3 ★★ 点右上角那个按钮 → 帮助面板真的打开了', False, '没有按钮')

    if dlg is None:
        return ok

    # ── B4 默认页（第 1 页）有检索框 ──
    # [EN] -- B4 default page (page 1) has search box --
    tabs = next((c for c in VU.walk(dlg)
                 if hasattr(c, 'selected_index') and hasattr(c, 'length')), None)
    search = next((c for c in VU.walk(dlg)
                   if isinstance(c, ft.TextField)
                   and '检索' in str(getattr(c, 'hint_text', '') or '')), None)
    ok &= rec('B4 ★★ 帮助**默认页**上有关键字检索框（用户要的就是不用切页就能搜）',
              search is not None and tabs is not None
              and int(getattr(tabs, 'selected_index', -1) or 0) == 0,
              f'selected_index={getattr(tabs, "selected_index", None)} search={search is not None}')

    all_rows = _toc_rows(dlg)
    report['toc_total'] = len(all_rows)
    ok &= rec('B4b 左栏目录已经列出来了（检索的前置条件）', len(all_rows) >= 15,
              f'{len(all_rows)} 行')
    # ★ 回调**真的接上了**才算"检索能用"。
    #   ⚠ 为什么要单列这一条：下面 B5/B6 都是**手工调** `search.on_change(假事件)`
    #   —— 那等于绕开了"接线"这一行，`on_change=None` 的变异照样能通过
    #   （反例法抓到的，正是本项目"测了实现、没测接线"的老坑）。
    # [EN] ★ Callback **actually wired up** counts as "search works".
    # [EN] ⚠ Why this is listed separately: B5/B6 below both **manually call** `search.on_change(fake
    # [EN] event)`
    # [EN] -- that bypasses the "wiring" line, and the `on_change=None` mutation still passes
    # [EN] (caught by counterexample method, exactly this project's old pitfall of "tested implementation,
    # [EN] didn't test wiring").
    ok &= rec('B4c ★★ 检索框的回调**真的接上了**（没接的话输字毫无反应）',
              callable(getattr(search, 'on_change', None)),
              repr(getattr(search, 'on_change', None))[:60])

    # ── B5 ★★ 输入关键字 → 左栏真的被过滤 + 命中数出现在屏幕上 ──
    # [EN] -- B5 ★★ enter keyword -> left column really filtered + hit count appears on screen --
    if search is not None:
        search.value = '运行模式'
        search.on_change(_Ev(search))
        await asyncio.sleep(0.7)
        rows2 = _toc_rows(dlg)
        report['toc_filtered'] = len(rows2)
        txts = VU.all_texts(dlg)
        ok &= rec('B5 ★★ 输入关键字后左栏被**真的过滤**（行数变少，不是装饰）',
                  0 < len(rows2) < len(all_rows),
                  f'{len(all_rows)} → {len(rows2)}')
        ok &= rec('B5b ★ 命中数写在屏幕上（用户要知道"到底中了几节"）',
                  any('命中' in x for x in txts),
                  [x for x in txts if '命中' in x][:2])

        # ── B6 ★★ 点结果 → 正文里出现关键词（端到端）──
        # ⚠ 判据前提：`_rebuild()` 已经把**第一条**命中自动打开了（省一次点击），
        #   所以"点第一条"必然看不到任何变化 —— 要点**另一条**才算"有反应"。
        #   （第一版点的就是 `rows2[0]`，功能正常却假红。）
        # [EN] -- B6 ★★ click result -> keyword appears in body (end-to-end) --
        # [EN] ⚠ Criterion premise: `_rebuild()` has already auto-opened the **first** hit (saves one click),
        # [EN] so "clicking the first" necessarily shows no change -- must click **another** one to count as
        # [EN] "reaction".
        # [EN] (First version clicked `rows2[0]`, functionality was fine but it falsely failed.)
        bool_body = [x for x in VU.all_texts(dlg) if '在这一节出现' in x]
        ok &= rec('B6 ★★ 检索后正文顶部写出「在这一节出现 N 次」（自动落到第一条命中）',
                  bool(bool_body), str(bool_body[:1]))
        ok &= rec('B6a 前置：`运行模式` 在手册里命中 ≥2 节（否则下面那条无从对比）',
                  len(rows2) >= 2, f'{len(rows2)} 节')
        if len(rows2) >= 2:
            before = ' '.join(VU.all_texts(dlg))
            rows2[-1].on_click(None)
            await asyncio.sleep(0.7)
            ok &= rec('B6b ★★ 点**另一条**结果 → 正文真的换了内容（不是点了个寂寞）',
                      ' '.join(VU.all_texts(dlg)) != before, '')
            ok &= rec('B6c 换过去之后，命中提示也跟着换了（说明是那一节自己的数）',
                      any('在这一节出现' in x for x in VU.all_texts(dlg)), '')
        await shot('help_search_hits.png')

        # ── B7 ★ 反例：清空检索 → 目录恢复全部 ──
        # [EN] -- B7 ★ counterexample: clear search -> directory restores all --
        clear = _find_button(dlg, t('清除'))
        ok &= rec('B7 ★ 检索框旁边有「清除」（否则只能一个字一个字删）',
                  clear is not None, str(clear))
        if clear is not None:
            clear.on_click(None)
            await asyncio.sleep(0.7)
            rows3 = _toc_rows(dlg)
            ok &= rec('B7b ★★ 点「清除」→ 目录恢复成全部（反例，也证明过滤不是恒真）',
                      len(rows3) == len(all_rows),
                      f'{len(rows2)} → {len(rows3)}（应为 {len(all_rows)}）')
            ok &= rec('B7c 输入框也被清空了（不留一个"看着还在过滤"的词）',
                      not str(search.value or '').strip(), repr(search.value))

        # ── B8 没命中的词 → 空目录 + 明说没找到 ──
        # [EN] -- B8 word with no hit -> empty directory + explicitly says not found --
        search.value = '绝不可能出现的词zzz'
        search.on_change(_Ev(search))
        await asyncio.sleep(0.6)
        ok &= rec('B8 ★ 查不到的词 → 目录空 + 屏幕上明说"没有找到"',
                  len(_toc_rows(dlg)) == 0
                  and any('没有找到' in x for x in VU.all_texts(dlg)),
                  [x[:40] for x in VU.all_texts(dlg) if '没有找到' in x])
        search.value = ''
        search.on_change(_Ev(search))
        await asyncio.sleep(0.5)

        # ── B9 ★★ 像素：检索框真的画在屏幕上（写死高度的面板会裁内容）──
        # [EN] -- B9 ★★ pixels: search box really drawn on screen (a panel with hardcoded height would clip
        # [EN] content) --
        keep = search.bgcolor
        search.bgcolor = '#ff00ff'
        page.update()
        await asyncio.sleep(0.6)
        png_m = await shot('help_search_field_marker.png')
        n_on = magenta_px(png_m)
        search.bgcolor = keep
        page.update()
        await asyncio.sleep(0.5)
        png_c = await shot('help_search_field_after.png')
        n_off = magenta_px(png_c)
        report['search_px'] = [n_on, n_off]
        ok &= rec('B9 ★★ 检索框**真的画在屏幕上**（品红像素 > 0，没被裁掉）',
                  n_on > 200, f'{n_on} px')
        ok &= rec('B9b ★★ 反例：恢复底色 → 归零（判据不是恒真）', n_off == 0,
                  f'{n_on} → {n_off}')

    # ══════════════════════════════════════════════════════════
    #  E. 左右两栏的滚动条（用户：「左边和右边有下拉条吗？没有就加上」）
    # [EN] E. Scrollbars of both left and right columns (user: "do the left and right have dropdown bars?
    # [EN] add them if not")
    # ══════════════════════════════════════════════════════════
    #  背景（都是实测，别再走一遍）：
    #   · 框架给的"常驻滚动条"**不生效** —— 主题上的
    #     `ScrollbarTheme(thumb_visibility=True)` 与控件上的
    #     `ListView(scroll=ft.Scrollbar(thumb_visibility=True,…))` 都试过，
    #     把车道里的像素逐列数过：`thickness` 从 8 调到 40，车道里始终空的。
    #   · 所以条是**自己画的**（`gui/app_flet.App._scroll_bar`），判据也就必须
    #     落在"屏幕上有没有、动没动"，不能只查控件属性。
    #   · 还有个坑：右栏默认显示第一项「开篇」（百来字），**它本来就不该滚** ——
    #     直接量会得出"没有滚动条"的错误结论。要先点开**长章节**（§4）。
    # [EN] Background (all measured, don't walk through it again):
    # [EN] · Framework's "always-on scrollbar" **doesn't work** -- the theme's
    # [EN] `ScrollbarTheme(thumb_visibility=True)` and the widget's
    # [EN] `ListView(scroll=ft.Scrollbar(thumb_visibility=True,...))` were both tried,
    # [EN] counted pixels column by column in the lane: `thickness` adjusted from 8 to 40, the lane stays
    # [EN] empty.
    # [EN] · So the bar is **drawn by ourselves** (`gui/app_flet.App._scroll_bar`), and the criterion must
    # [EN] rest on "is it on screen, did it move", not just querying widget attributes.
    # [EN] · Another pitfall: right column by default shows the first item "Opening" (~100 chars), **it
    # [EN] shouldn't scroll at all** --
    # [EN] measuring directly gives the wrong conclusion of "no scrollbar". Must first open a **long
    # [EN] chapter** (§4).
    if dlg is not None:
        lvs = [c for c in VU.walk(dlg) if isinstance(c, ft.ListView)]
        ok &= rec('E1 ★★ 两栏都是**可滚动**控件（`ListView` 且设了 `scroll`）',
                  len(lvs) >= 2 and all(getattr(c, 'scroll', None) is not None
                                        for c in lvs[:2]),
                  str([getattr(c, 'scroll', None) for c in lvs[:2]]))
        thumbs = [c for c in VU.walk(dlg)
                  if isinstance(c, ft.Container)
                  and getattr(c, 'width', None) == 4
                  and getattr(c, 'right', None) is not None]
        ok &= rec('E2 ★★ 两栏各挂了一条**自绘**的滚动条'
                  '（框架那条常驻不生效，只能自己画）',
                  len(thumbs) >= 2, f'{len(thumbs)} 条')

        toc_h = _toc_holder(dlg)
        body_h = next((c for c in VU.walk(dlg)
                       if isinstance(c, ft.Container) and c is not toc_h
                       and isinstance(content_of(c), ft.Stack)), None)
        rows_e = _toc_rows(dlg)
        target_e = next((r for r in rows_e
                         if '4. 主界面详解' in ' '.join(VU.all_texts(r))), None)
        ok &= rec('E3 前置：左栏里找得到长章节「4. 主界面详解」'
                  '（两万多字，最该出现滚动条的那一章）',
                  target_e is not None, f'{len(rows_e)} 行')
        if target_e is not None and body_h is not None and len(thumbs) >= 2:
            target_e.on_click(None)
            page.update()
            await asyncio.sleep(1.3)
            body_lv = next(c for c in VU.walk(body_h) if isinstance(c, ft.ListView))

            # ⚠ **先测"初次该不该画条"，再测"能不能滚"** —— 顺序要紧：
            #   滚一下会让条自己显形（`on_scroll` 会把 `visible` 置 True），
            #   先滚就测不出"**初次**那一帧有没有画"（第一版就是这样，
            #   于是"换章时不重判"那个变异永远抓不到）。
            # [EN] ⚠ **First test "should a bar be drawn initially", then test "can it scroll"** -- order matters:
            # [EN] scrolling once makes the bar reveal itself (`on_scroll` sets `visible` to True),
            # [EN] scrolling first makes it impossible to test whether the **initial** frame drew it (first version
            # [EN] was like this,
            # [EN] so the mutation of "no re-judge on chapter change" could never be caught).
            #
            # ── E5 ★★ 条**画在屏幕上**、而且**在车道里**（像素取证）──
            #   染色用纯绿（车道里不会有别的东西是这个色相）；判据按**色相**，
            #   因为半透明界面会把纯色混淡（按原色匹配会量到 0，踩过）。
            # ⚠ 循环变量**别叫 `t`** —— 它会屏蔽模块级的 i18n `t()`，
            #   后面任何 `t('…')` 都会 `UnboundLocalError`（踩过）。
            # ⚠ 两栏容器也要染色 —— 不染就**定不出车道在哪一段**，
            #   整屏找绿会撞上别处的元素（第一版就是这么量到 None 的）。
            #   右栏染青（`_cyan_box` 靠它拿右边界），左栏染品红以作区分。
            # [EN] -- E5 ★★ bar **drawn on screen**, and **inside the lane** (pixel forensics) --
            # [EN] Use pure green for tinting (nothing else in the lane has this hue); criterion by **hue**,
            # [EN] because semi-transparent UI washes pure colors out (matching by original color measures 0, been
            # [EN] there).
            # [EN] ⚠ Loop variable **don't name it `t`** -- it shadows the module-level i18n `t()`,
            # [EN] any later `t('...')` will throw `UnboundLocalError` (been there).
            # [EN] ⚠ Two-column containers must also be tinted -- without tinting you **can't tell which segment
            # [EN] the lane is**,
            # [EN] searching the whole screen for green hits other elements (first version measured None this way).
            # [EN] Right column tinted cyan (`_cyan_box` uses it to get right boundary), left column tinted magenta
            # [EN] to distinguish.
            old_bg = [th.bgcolor for th in thumbs]
            old_hb = [toc_h.bgcolor if toc_h is not None else None, body_h.bgcolor]
            for th in thumbs:
                th.bgcolor = '#00ff00'
            if toc_h is not None:
                toc_h.bgcolor = '#ff00ff'
            body_h.bgcolor = '#00ffff'
            page.update()
            await asyncio.sleep(0.8)
            png_bar = await shot('help_scrollbar_marker.png')
            # ⚠ 颜色**先别恢复**：下面 E6/E6b 还要继续找那条绿
            #   （第一版在这里就恢复了，于是 E6 永远"量不到"）。
            # [EN] ⚠ **Don't restore colors yet**: E6/E6b below still need to find that green
            # [EN] (first version restored here, so E6 could never "measure" it).
            box_body = _cyan_box(png_bar)
            x_lo_e = (box_body[2] - 40) if box_body else 0
            x_hi_e = (box_body[2] + 30) if box_body else 10 ** 9
            bar = _green_box(png_bar, x_lo=x_lo_e, x_hi=x_hi_e)
            report['bar_box'] = bar
            ok &= rec('E5 ★★ 滚动条**真的画在屏幕上**，而且在右栏车道里'
                      '（像素取证，不是查控件属性）',
                      bar is not None and bar[3] > bar[1], str(bar))

            # ── E6 ★★ 条**跟着滚动按比例走** ──
            #   ⚠ 手工喂一个**真实形状**的事件：`scroll_to` 这种"程序滚动"
            #     在某些版本不回调 `on_scroll`，而用户滚轮/拖动一定会回调。
            #     这里验的是"事件来了之后，条算得对不对、画得动不动"。
            class _ScrollEv:        # ⚠ 别叫 `_Ev`：B 组用的是模块级 `_Ev`，
                pass                #   同名会让它在这个函数里变成局部名（踩过）
            # [EN] -- E6 ★★ bar **moves proportionally with scrolling** --
            # [EN] ⚠ Manually feed an event of **real shape**: `scroll_to` kind of "programmatic scroll"
            # [EN] doesn't call back `on_scroll` in some versions, whereas user wheel/drag always calls back.
            # [EN] Here we verify "once the event arrives, does the bar compute correctly, does it move".
            # [EN] ⚠ Don't call it `_Ev`: group B uses a module-level `_Ev`,
            # [EN] the same name would make it a local name inside this function (been burned before)
            ev = _ScrollEv()
            ev.pixels, ev.max_scroll_extent, ev.viewport_dimension = 1500.0, 6000.0, 452.0
            y_before = bar[1] if bar else None
            body_lv.on_scroll(ev)
            page.update()
            await asyncio.sleep(0.8)
            png_mid = await page.take_screenshot()
            b_mid = _green_box(png_mid, x_lo=x_lo_e, x_hi=x_hi_e)
            ok &= rec('E6 ★★ 滚动之后条**按比例下移**（不是画着好看的）',
                      y_before is not None and b_mid is not None
                      and b_mid[1] > y_before,
                      f'top {y_before} → {b_mid[1] if b_mid else "量不到"}')
            ev.pixels = 0.0
            body_lv.on_scroll(ev)
            page.update()
            await asyncio.sleep(0.7)
            png_top = await page.take_screenshot()
            b_top = _green_box(png_top, x_lo=x_lo_e, x_hi=x_hi_e)
            ok &= rec('E6b ★ 反例：滚回顶部 → 条也回到原位',
                      b_top is not None and b_mid is not None
                      and abs(b_top[1] - (y_before or 0)) <= 3,
                      f'{b_mid[1] if b_mid else "?"} → '
                      f'{b_top[1] if b_top else "量不到"}（原位 {y_before}）')
            # 到这里才把标记色恢复原样（E5/E6/E6b 都靠它）
            # [EN] Only here is the marker color restored (E5/E6/E6b all rely on this)
            for th, bg in zip(thumbs, old_bg):
                th.bgcolor = bg
            if toc_h is not None:
                toc_h.bgcolor = old_hb[0]
            body_h.bgcolor = old_hb[1]
            page.update()
            await asyncio.sleep(0.4)

        # ── E8 ★★ 真的能滚（放在条那几条**之后**：滚一下会让条显形）──
        # [EN] ── E8 ★★ actually scrolls (placed **after** those bar items: scrolling makes the bar appear) ──
        if body_h is not None:
            body_lv2 = next((c for c in VU.walk(body_h)
                             if isinstance(c, ft.ListView)), None)
            if body_lv2 is not None:
                before = await page.take_screenshot()
                try:
                    await body_lv2.scroll_to(offset=1200, duration=0)
                except TypeError:
                    body_lv2.scroll_to(offset=1200)
                page.update()
                await asyncio.sleep(1.0)
                after = await page.take_screenshot()
                ok &= rec('E8 ★★ 右栏在长章节下**真的能滚**'
                          '（以前整章交给一个 `ft.Markdown`、高度量不准 → '
                          '滚不动、后半章根本读不到）', before != after, '')
                try:
                    await body_lv2.scroll_to(offset=0, duration=0)
                except TypeError:
                    body_lv2.scroll_to(offset=0)
                page.update()
                await asyncio.sleep(0.4)

        # ── E7 ★ 内容短的时候**不画多余的条** ──
        # [EN] ── E7 ★ when content is short, **don't draw extra bars** ──
        rows_now = _toc_rows(dlg)
        short = next((r for r in rows_now
                      if '开篇' in ' '.join(VU.all_texts(r))), None)
        if short is not None:
            short.on_click(None)
            page.update()
            await asyncio.sleep(1.0)
            vis = [getattr(th, 'visible', None) for th in thumbs]
            report['thumb_vis_short'] = vis
            ok &= rec('E7 ★ 切到短章节（开篇，百来字）→ 右栏那条**收起来**'
                      '（放得下就不该画，否则是多余的装饰）',
                      len(vis) >= 2 and vis[-1] is False, str(vis))
        # 让后面的 C 组从干净状态开始
        # [EN] Let the subsequent group C start from a clean state
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.5)

    # ══════════════════════════════════════════════════════════
    #  C. 没配 LLM → 「问个问题」变灰
    # [EN] C. No LLM configured → "Ask a question" turns gray
    # ══════════════════════════════════════════════════════════
    real_ready = AC.probe.llm_ready
    opened: list = []
    real_settings = app.show_global_settings

    def _fake_settings(tab=None):
        # ⚠ 默认值给 `None`（哨兵）而不是真方法那个 1：
        #   照抄的话"忘了传 tab=1"和"传了 tab=1"记下来一模一样，
        #   那个变异永远抓不到（本项目的老坑）。
        # [EN] ⚠ Give the default value `None` (sentinel) instead of the 1 used by the real method:
        # [EN] Copying it as-is makes "forgot to pass tab=1" and "passed tab=1" look identical,
        # [EN] that mutation can never be caught (long-standing pitfall in this project).
        opened.append(tab)

    app.show_global_settings = _fake_settings
    AC.probe.llm_ready = lambda *a, **k: (False, '没有填 API Key')
    try:
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.5)
        app.show_help_dialog(tab=1)
        await asyncio.sleep(0.9)
        dlg2 = _find_help_dialog(page)
        ok &= rec('C1 没配 LLM 时帮助面板照样能开（检索那页还要用）', dlg2 is not None,
                  '')
        if dlg2 is not None:
            send = _find_button(dlg2, t('发送'))
            inp = next((c for c in VU.walk(dlg2)
                        if isinstance(c, ft.TextField)
                        and '例如' in str(getattr(c, 'hint_text', '') or '')), None)
            txts = VU.all_texts(dlg2)
            examples = [t('怎么设置运行模式'), t('顶级规则怎么写'), t('对话插图有哪几种')]
            ex_btns = [b for b in (_find_button(dlg2, x) for x in examples) if b]
            report['disabled'] = {
                'send': getattr(send, 'disabled', None),
                'input': getattr(inp, 'disabled', None),
                'examples': [getattr(b, 'disabled', None) for b in ex_btns],
            }
            ok &= rec('C2 ★★ 没配 LLM → 「发送」按钮变灰（disabled）',
                      send is not None and send.disabled is True, str(send))
            ok &= rec('C2b ★★ 输入框也变灰（不能输字，否则用户会觉得"点了没反应"）',
                      inp is not None and inp.disabled is True, str(inp))
            ok &= rec('C2c ★ 示例问题按钮一起灰掉（它们点了也是走同一条路）',
                      len(ex_btns) >= 2 and all(b.disabled for b in ex_btns),
                      str([b.disabled for b in ex_btns]))
            ok &= rec('C3 ★★ 屏幕上要说清"为什么不能用"',
                      any('LLM 还没配置' in x for x in txts),
                      [x[:44] for x in txts if '还没配置' in x][:2])
            ok &= rec('C3b ★ 还要告诉用户**缺什么**（`llm_ready()` 的原话）',
                      any('没有填 API Key' in x for x in txts),
                      [x[:44] for x in txts if '没有填' in x][:2])
            ok &= rec('C3c ★ 并且指出退路：用「帮助信息」页的检索（那个不调模型）',
                      any('检索' in x and '不调模型' in x for x in txts),
                      [x[:52] for x in txts if '检索' in x][:1])
            await shot('help_search_llm_off.png')

            # ── C4 ★ 「去配置」真的跳去天机 · LLM 接入（tab=1）──
            # [EN] ── C4 ★ "Go to config" actually jumps to Tianji · LLM Access (tab=1) ──
            go = _find_button(dlg2, t('去配置'))
            ok &= rec('C4 ★ 变灰那段里有「去配置」（否则用户还得自己找）',
                      go is not None, str(go))
            if go is not None:
                go.on_click(None)
                await asyncio.sleep(0.6)
                # ⚠ 期望值取 `TAB_LLM`，**不写死**：2026-10-08 天机多了
                #   「常规」页签（排在「LLM 接入」左边），写死的 `1` 就成了
                #   「常规」—— 判据假红（实测记录到 tab=[2]，产品其实是对的）。
                #   "这个常量指没指对"由 `verify_regular_tab` 的 A3 照页签表核。
                # [EN] ⚠ The expected value uses `TAB_LLM`, **not hardcoded**: on 2026-10-08 Tianji added
                # [EN] the "General" tab (placed to the left of "LLM Access"), and a hardcoded `1` becomes
                # [EN] "General" — a false red for the criterion (measured tab=[2], the product is actually correct).
                # [EN] "Whether this constant points to the right one" is checked by A3 of `verify_regular_tab` against
                # [EN] the tab table.
                _want = NovelWorldApp.TAB_LLM
                ok &= rec(f'C4b ★★ 点「去配置」→ 打开天机、并且落在「LLM 接入」页'
                          f'（tab={{TAB_LLM}}={{_want}}）',
                          opened == [_want], f'记录到的 tab = {opened}')

        # ── C5 ★★ 反例：配好了就必须恢复可点 ──
        # [EN] ── C5 ★★ counterexample: once configured, it must become clickable again ──
        AC.probe.llm_ready = lambda *a, **k: (True, '')
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.5)
        app.show_help_dialog(tab=1)
        await asyncio.sleep(0.9)
        dlg3 = _find_help_dialog(page)
        if dlg3 is not None:
            send3 = _find_button(dlg3, t('发送'))
            txts3 = VU.all_texts(dlg3)
            ok &= rec('C5 ★★ 反例：LLM 配好后「发送」**恢复可点**（灰是有条件的，不是恒灰）',
                      send3 is not None and not send3.disabled, str(send3))
            ok &= rec('C5b ★ 也不该再出现"没有配置"那段说明',
                      not any('LLM 还没配置' in x for x in txts3),
                      [x[:36] for x in txts3 if '还没配置' in x][:2])
            await shot('help_search_llm_on.png')
    finally:
        AC.probe.llm_ready = real_ready
        app.show_global_settings = real_settings

    return ok


def finish() -> int:
    # ★★ 崩溃**必须自己留一条红的**（本项目铁律，`verify_model_probe` 上踩过）：
    #   只 `print` traceback 的话，红是"没有 checks 条目"——变异脚本按
    #   `✗` 统计时看到的是"0 条红"，于是**变异没抓到**看起来像判据不灵，
    #   其实是崩溃被静默了。
    # [EN] ★★ A crash **must leave a red of its own** (iron rule of this project, burned on
    # [EN] `verify_model_probe`):
    # [EN] If you only `print` the traceback, the red is "no checks entry" — the mutation script counts by
    # [EN] `✗` and sees "0 reds", so **the mutation isn't caught** and it looks like the criterion is
    # [EN] broken,
    # [EN] when in fact the crash was silenced.
    if report.get('fatal') and not any('崩溃' in c['name'] for c in report['checks']):
        rec('★ 验证没有中途崩溃（有崩溃就不是全绿）', False,
            str(report['fatal'])[-300:])
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'help_search_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"\n帮助检索/按钮/变灰 —— 验证："
          f"{len(report['checks']) - len(bad)}/{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1500:])
    print('报告：assets/screenshots/help_search_report.json')
    return 0 if report['ok'] else 2


async def entry(page) -> None:
    try:
        ok = await test_gui(page)
        report['ok'] = bool(ok)
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    # ⚠ 顺序是硬约束：**验证 → 写报告/打印 → shutdown → exit_now**
    #   （`page.window.destroy()` 会取消当前协程并抛 CancelledError，
    #    写在它后面的代码一行都不会执行）
    # [EN] ⚠ The order is a hard constraint: **verify → write report/print → shutdown → exit_now**
    # [EN] (`page.window.destroy()` cancels the current coroutine and throws CancelledError,
    # [EN] code written after it won't execute a single line)
    from util.flet_shutdown import exit_now, shutdown
    code = finish()
    await shutdown(page, code=code)
    exit_now(code)


if __name__ == '__main__':
    if '--logic-only' in sys.argv:
        try:
            report['ok'] = bool(logic_checks() and fence_checks())
        except BaseException:                                  # noqa: BLE001
            report['fatal'] = traceback.format_exc()
        raise SystemExit(finish())
    try:
        logic_checks()
        fence_checks()
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    ft.run(entry)
