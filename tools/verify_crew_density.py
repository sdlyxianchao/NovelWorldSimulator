# -*- coding: utf-8 -*-
"""真机/逻辑验证：**「剧组」那一栏一屏能显示全部 Agent**（2026-10-17）。

用户 2026-10-17 原话：
    「右侧的剧组这部分有办法调整下布局 让它所有Agents一次性显示出来吗？」

### 为什么需要改（实测出来的账，1920×1129 窗口、19 个职位）

    · 右栏视口高 **1017px**，改前内容 **1208px** ⇒ 超出 **191px**，必须滚动；
    · 「剧组」面板上沿 y=422，到屏幕底只剩 **668px**；
    · 两行版每行 **41–42px** ⇒ 19 行要 **790px**，差 120px。
    ⇒ 一行版每行 **22px** ⇒ 19 行 **418px**（改后实测 `max_scroll_extent == 0`）。

### 改法：每个 Agent 一行（`_crew_row(compact=True)`，默认）

单行文本 = `head` + ` · ` + `line`，**原来上下两行原样拼接**，一个词都不删。
放不下的部分用省略号，**悬停看得到全文**（`tooltip` 给完整一句）。

### 判据（行为为主，AST 为辅）

  A **结构**：`compact` 参数默认开、单行那一支真的单行（`expand=True` + 省略号）
  B **文案一个字都没丢**：六种状态各自该出现的词都还在
     （成对：`compact=False` 时**仍是两行** —— 别一刀切把两行版也砍掉）
  C **真机：19 个职位 `max_scroll_extent == 0`**（这是用户诉求本身）
  D **每行高度 ≈ 22px**（改前 41px；用像素量，不读代码）

跑法：.venv\\Scripts\\python.exe tools/verify_crew_density.py
      .venv\\Scripts\\python.exe tools/verify_crew_density.py --logic-only
产出：assets/screenshots/crew_density_report.json

English:
Real-machine / logic verification: **the "Cast" column can show all Agents in one screen** (2026-10-17).
User's exact words: "Is there a way to adjust the layout of the Cast section on the right so that all
Agents are displayed at once?"
### Why it had to change (measured, 1920x1129 window, 19 positions)
    · the right column's viewport is **1017px**, content was **1208px** => **191px over**, scrolling
      unavoidable;
    · the "Cast" panel starts at y=422, leaving only **668px** to the bottom;
    · the two-line version takes **41-42px** per row => 19 rows need **790px**, 120px short.
    => the one-line version takes **22px** per row => 19 rows = **418px** (measured
      `max_scroll_extent == 0` after the change).
### The change: one line per Agent (`_crew_row(compact=True)`, the default)
The single-line text is `head` + ` · ` + `line`, **the previous two lines concatenated verbatim**,
not a single word deleted. What doesn't fit gets an ellipsis and **is readable on hover** (the
`tooltip` carries the full sentence).
### Criteria (behavior first, AST as support)
  A **Structure**: the `compact` parameter defaults on, and the one-line branch really is one line
    (`expand=True` + ellipsis)
  B **Not a word of wording was lost**: the words each of the six states must show are all still
    there (paired: with `compact=False` it is **still two lines** -- don't一刀切 away the two-line
    version)
  C **Real machine: 19 positions give `max_scroll_extent == 0`** (this is the user's request itself)
  D **Row height ≈ 22px** (was 41px; measured in pixels, not read from code)
How to run: .venv\\Scripts\\python.exe tools/verify_crew_density.py
      .venv\\Scripts\\python.exe tools/verify_crew_density.py --logic-only
Output: assets/screenshots/crew_density_report.json
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
from util.flet_shutdown import shutdown                         # noqa: E402
import verify_ui_common as VU                                  # noqa: E402

from config import CFG                                         # noqa: E402
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')
CFG.set('SHOW_OPENING', 'false')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from crew import studio as ST                                   # noqa: E402
from gui.app_flet import NovelWorldApp                          # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}
ONLY_LOGIC = '--logic-only' in sys.argv


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _texts(ctl, out=None) -> list[str]:
    if out is None:
        out = []
    if ctl is None:
        return out
    if isinstance(ctl, ft.Text) and ctl.value:
        out.append(str(ctl.value))
    if isinstance(ctl, ft.GestureDetector):
        _texts(ctl.content, out)
        return out
    for attr in ('controls', 'content'):
        v = getattr(ctl, attr, None)
        if isinstance(v, list):
            for c in v:
                _texts(c, out)
        elif v is not None:
            _texts(v, out)
    return out


def _unwrap(ctl):
    """剥掉**外面那两层壳**：整行可点（`GestureDetector`）与整行悬停（`Container`）。

    ★★★ 2026-10-24：`_crew_row` 给**所有行**都加了一层带 tooltip 的 `Container`
      （用户要求"点不动的那种行也要有完整 Tip"），而这里原来只剥
      `GestureDetector` ⇒ B0 拿到 `Container` 去读 `.controls`，当场
      `AttributeError`（实测：B 组整组崩）。所以两层都要剥。
    ⚠ **出工高亮**那一层 `Container` 有底色，**必须留着** —— 它不是一个壳，
      而是那一行的样式本身（B0 用 busy=False 的行，本来就不会碰到它）。
    [EN] Peel **both** shells: whole-row clickable (`GestureDetector`) and whole-row hover
    [EN] (`Container`).
    [EN] ★★★ 2026-10-24: `_crew_row` now wraps **every** row in a tooltip-carrying `Container` (the
    [EN] user asked that non-clickable rows have a full tip too), while this only peeled the
    [EN] `GestureDetector` => B0 got a `Container`, read `.controls` and raised `AttributeError`
    [EN] (measured: the whole B group crashed). Both shells must go.
    [EN] ⚠ The **busy highlight** `Container` has a background and must stay -- it is not a shell but
    [EN] the row's own styling (B0 uses busy=False, so it never meets it anyway).
    """
    while True:
        if isinstance(ctl, ft.GestureDetector):
            ctl = ctl.content
            continue
        if (isinstance(ctl, ft.Container)
                and getattr(ctl, 'bgcolor', None) is None
                and getattr(ctl, 'content', None) is not None):
            ctl = ctl.content
            continue
        break
    return ctl


def _make_row(**kw) -> ft.Control:
    """用**真的** `_crew_row` 造一行（不接 page）。
        English:
    Build one row with the **real** `_crew_row` (no page).
    """
    app = object.__new__(NovelWorldApp)
    return NovelWorldApp._crew_row(app, {'key': 'k', 'name': kw.pop('name', '探针职位')},
                                   **kw)


# ══════════════════════════════════════════════════════════════
#  A —— 结构：默认单行，且单行那一支真的单行
# [EN] A -- structure: one line by default, and that branch really is one line
# ══════════════════════════════════════════════════════════════
def structure_checks() -> None:
    sig = inspect.signature(NovelWorldApp._crew_row)
    ok('A1 ★★★ `_crew_row` 有 `compact` 参数，且**默认为 True**'
       '（默认就是一行 —— 不然产品代码里漏传一处就又变回两行）',
       'compact' in sig.parameters
       and sig.parameters['compact'].default is True,
       str(sig.parameters.get('compact')))

    # ⚠★★★ A2/A3 **不能**用"源码含 `expand=True`"这种字符判据：
    #   `_crew_row` 的**双行分支里也有** `expand=True` / `no_wrap=True`（Column 的），
    #   变异把单行那处删掉之后，字符串照样命中 ⇒ 假绿（反例法 ②③ 各撞一次）。
    #   ⇒ 用 AST 认准 `if compact:` 那一支里的 `ft.Text(...)`，只看它自己的关键字。
    # [EN] ⚠★★★ A2/A3 **must not** use "the source contains `expand=True`" style string criteria:
    # [EN] the **two-line branch of `_crew_row` also has** `expand=True` / `no_wrap=True` (on the
    # [EN] Column), so after a mutation deletes the one-line copy the string still matches => false
    # [EN] green (counterexamples 2 and 3 each hit this). => Use AST to pin the `ft.Text(...)` inside
    # [EN] the `if compact:` branch and look only at its own keywords.
    tree = ast.parse((APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8'))
    fn = None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == '_crew_row':
            fn = n
    ok('A7 ★ `_crew_row` 在 AST 里找得到', fn is not None, '')
    if fn is None:
        return
    compact_if = None
    for n in ast.walk(fn):
        if (isinstance(n, ast.If) and isinstance(n.test, ast.Name)
                and n.test.id == 'compact'):
            compact_if = n
            break
    ok('A8a ★ `_crew_row` 里有 `if compact:` 这个分支', compact_if is not None, '')
    if compact_if is None:
        return

    def _texts_in(node) -> list:
        return [n for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'Text']

    def _kw(call, name):
        for kw in call.keywords:
            if kw.arg == name:
                return kw.value
        return None

    def _is_const(v, val):
        return isinstance(v, ast.Constant) and v.value is val

    one_texts = [c for s in compact_if.body for c in _texts_in(s)]
    ok('A8b 单行那一支里有 `ft.Text(...)`（找得到才谈得上"拉满宽度"）',
       bool(one_texts), f'{len(one_texts)} 个')
    src_all = inspect.getsource(NovelWorldApp._crew_row)

    # ── 拼接规则那个函数：真的存在、且真的被调用 ──
    # [EN] ── the concatenation helper: really exists, and is really called ──
    ok('A5 ★★ 拼接规则抽成了 `_crew_oneline`（判据好钉、也方便核对去重）',
       callable(getattr(NovelWorldApp, '_crew_oneline', None)), '')
    ok('A6 ★★ `_crew_row` 真的调了它（不是写了个函数没人用）',
       '_crew_oneline(' in src_all, '')

    body_src = '\n'.join(ast.unparse(s) for s in compact_if.body)
    ok('A8 ★★★ 单行分支里**没有 `ft.Column`**（有 Column 就是又变回两行了）',
       'ft.Column' not in body_src, body_src.replace('\n', ' ')[:160])
    ok('A2 ★★★ 单行那一支的文字**会拉满宽度**（`expand=True`）'
       '（不给 expand，省略号永远不触发 —— 那一行会按内容一直往外长）',
       any(_is_const(_kw(c, 'expand'), True) for c in one_texts),
       '单行分支里的 Text 都没有 expand=True')
    ok('A3 ★★ 单行那一支配了 `no_wrap=True` + `overflow=ELLIPSIS`'
       '（放不下就省略号，不换行 —— 换行就变回两行了）',
       any(_is_const(_kw(c, 'no_wrap'), True) for c in one_texts)
       and any(isinstance(_kw(c, 'overflow'), ast.Attribute)
               and _kw(c, 'overflow').attr == 'ELLIPSIS' for c in one_texts),
       'no_wrap / ELLIPSIS 缺一个')
    # ★★★ 2026-10-24：这一处的写法从内联 f-string 抽成了 `_crew_row_tip()`
    #   （要给"点不动的那种行"也挂 tooltip —— 见 `verify_run_panel_hints` 的 F2）。
    #   守的意图没变：**悬停能看到被省略号截掉的那一整句**。
    #   ⚠ "真的完整"由 `verify_run_panel_hints` 的 F1 行为级判（拿 79 字的真句子
    #     断言 tooltip 里原样包含它）；这里只判**接线**（有没有走那个函数），
    #     两道闸各管一件事 —— 只判源码串的老写法在重构后必然假红。
    # [EN] ★★★ 2026-10-24: this spot went from an inline f-string to `_crew_row_tip()` (so that
    # [EN] **non-clickable** rows get a tooltip too -- see F2 in `verify_run_panel_hints`). The intent is
    # [EN] unchanged: **hover shows the whole sentence** the ellipsis cut off.
    # [EN] ⚠ "Really complete" is judged behaviourally by F1 there (a real 79-char sentence must appear
    # [EN] verbatim); this one only judges **the wiring** -- two gates, two jobs. The old
    # [EN] source-string check always goes false-red after a refactor.
    ok('A4 ★★ 悬停提示走的是 `_crew_row_tip()`（省略号截掉的部分在那里看得到）',
       'self._crew_row_tip(r, one' in src_all, '')


# ══════════════════════════════════════════════════════════════
#  B —— 文案一个字都没丢（六种状态各自的关键词）
# [EN] B -- not a word of wording was lost (each of the six states' keywords)
# ══════════════════════════════════════════════════════════════
def wording_checks() -> None:
    # ── 单行：一个 Agent 只占一个 `ft.Text`（除圆点外）──
    # [EN] ── one line: an Agent occupies exactly one `ft.Text` (besides the dot)
    ctl = _unwrap(_make_row(busy=False, head='小说作家', line='还没轮到',
                            text_key='muted', dot_key='muted'))
    ok('B0 ★★★ 单行版：一个 Agent 只有一个 `ft.Text`（圆点那个不算）'
       '（两个 Text 就是原来的两行版了）',
       isinstance(ctl, ft.Row) and len([c for c in ctl.controls
                                        if isinstance(c, ft.Text)]) == 2,
       f'类型={type(ctl).__name__} 子控件={[type(c).__name__ for c in ctl.controls]}')

    blob = ' | '.join(_texts(ctl))
    ok('B1 ★★★ 单行文本 = `名字 · 第二行`（原样拼接，不重排文案）',
       '小说作家' in blob and '还没轮到' in blob and '·' in blob, blob)

    # ── 六种状态，各自该有的词一个都不能少 ──
    # [EN] ── six states, not one of the words each must carry may be missing
    cases = [
        ('idle', dict(busy=False, head='小说作家', line='还没轮到',
                      text_key='muted', dot_key='muted'),
         ['小说作家', '还没轮到']),
        ('off', dict(busy=False, head='造型 · 未启用', line='这一轮没启用',
                     text_key='muted', dot_key='muted'),
         ['造型', '这一轮没启用']),
        ('onduty', dict(busy=False, head='导演', line='在岗 · 正在做：定框架、派活',
                        text_key='text', dot_key='accent'),
         ['导演', '在岗', '正在做', '定框架、派活']),
        ('busy', dict(busy=True, head='美术 · 出工中 · 已跑 3 秒',
                      line='正在做：定这一部的画风与配色',
                      text_key='text', dot_key='accent'),
         ['美术', '出工中', '已跑 3 秒', '正在做', '定这一部的画风与配色']),
        ('done', dict(busy=False, head='剧本审读', line='上屏之前逐条读了一遍',
                      text_key='text', dot_key='accent_green'),
         ['剧本审读', '上屏之前逐条读了一遍']),
    ]
    for st, kw, must in cases:
        row = _unwrap(_make_row(name=kw.pop('name', '') or
                                kw['head'].split(' · ')[0], **kw))
        b = ' | '.join(_texts(row))
        for w in must:
            ok(f'B2 ★★★ `{st}` 那一行仍然写着「{w}」'
               f'（改布局不许丢信息 —— 旧判据也认这些词）',
               w in b, b)

    # ── off 那档不许把同一件事说两遍 ──
    # [EN] ── the off case must not say the same thing twice
    off = _unwrap(_make_row(busy=False, head='造型 · 未启用', line='这一轮没启用',
                            text_key='muted', dot_key='muted'))
    ob = ' | '.join(_texts(off))
    ok('B3 ★★ `off` 那行**不重复**说"没启用"'
       '（`head` 里有「未启用」、`line` 是「这一轮没启用」，拼起来会变两遍）',
       ob.count('启用') == 1, ob)

    # ── 空 line：只给名字，不留一个孤零零的分隔点 ──
    # [EN] ── empty line: just the name, no dangling separator
    empty = _unwrap(_make_row(busy=False, head='空档位', line='',
                              text_key='muted', dot_key='muted'))
    eb = ' | '.join(_texts(empty))
    ok('B4 ★★ `line` 为空时只写名字，不拖一个多余的「 · 」',
       eb.strip() == '空档位' or (not eb.rstrip().endswith('·')), eb)

    # ── 成对判据：`compact=False` **仍然是两行**（别一刀切把两行版也砍了）──
    # [EN] ── paired criterion: `compact=False` is **still two lines** (don't一刀切 away the two-line
    # [EN] version as well)
    two = _unwrap(_make_row(busy=False, head='小说作家', line='还没轮到',
                            text_key='muted', dot_key='muted', compact=False))
    col = None
    if isinstance(two, ft.Row):
        col = next((c for c in two.controls if isinstance(c, ft.Column)), None)
    ok('B5 ★★★ 显式 `compact=False` 时**仍是两行**（`Column` 里两个 `Text`）'
       '—— 这一条是"不许一刀切"的成对判据',
       col is not None and len(col.controls) == 2,
       f'类型={type(two).__name__} 找到Column={col is not None}')

    # ── 悬停那一句带完整内容 ──
    # [EN] ── the hover sentence carries the full content
    app = object.__new__(NovelWorldApp)
    box = NovelWorldApp._crew_row(
        app, {'key': 'k', 'name': '美术'},
        busy=True, head='美术 · 出工中 · 已跑 3 秒',
        line='正在做：定这一部的画风与配色', text_key='text', dot_key='accent',
        on_click=lambda e: None)
    tp = str(getattr(box, 'tooltip', '') or '')
    ok('B6 ★★★ 悬停能看到**完整那一句**（省略号截掉的部分在这里）',
       '正在做：定这一部的画风与配色' in tp and '已跑 3 秒' in tp, tp)


# ══════════════════════════════════════════════════════════════
#  C/D —— 真机：一屏放下 + 每行 22px
# [EN] C/D -- real machine: fits in one screen + 22px per row
# ══════════════════════════════════════════════════════════════
def _text_rows(png, box, *, min_ink: int = 3) -> list[int]:
    im = VU.image_of(png).convert('L')
    x0, y0, x1, y1 = box
    im = im.crop((x0, y0, x1, y1))
    w, h = im.size
    px = im.load()
    out = []
    for y in range(h):
        d = sum(1 for x in range(w) if px[x, y] < 150)
        if min_ink <= d <= w * 0.5:
            out.append(y)
    return out


def _bands(ys: list[int], gap: int = 3) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for y in ys:
        if out and y - out[-1][1] <= gap:
            out[-1] = (out[-1][0], y)
        else:
            out.append((y, y))
    return out


async def real_checks(page: ft.Page) -> None:
    import tempfile
    from sim import setup as SU
    from sim.session import RunSession
    from store.runfolder import RunFolder
    from verify_run_control import make_project

    VU.patch_flat_background()
    from gui.app_flet import NovelWorldApp as NWA

    tmp = Path(tempfile.mkdtemp(prefix='nws_crewdense_'))
    proj = make_project(tmp / '剧组密度', chars=3, nodes=2)
    run = RunFolder(proj.root, '第1次模拟2026-10-17-00-00').create()
    loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)

    app = NWA()
    app.main(page)
    page.enable_screenshots = True
    await asyncio.sleep(1.8)
    app.current_project = proj
    app.session = RunSession(loop, world, run, on_crew_work=app._on_crew_work)
    app.show_main_screen()
    await asyncio.sleep(0.9)

    # 把在场人物撑到最长那一档（3 个演员各占一行）——剧组被挤得最狠的情况。
    # [EN] Stretch On-stage Characters to its longest case (3 actors, one row each) -- the case where the
    # [EN] Cast column is squeezed hardest.
    for ps in world.people.values():
        ps.status = '在场'
        ps.role = '前台'
        ps.location = ''
    names = list(world.on_stage_names())
    world.actor_think = {n: f'{n}正在盘算这一场该怎么接' for n in names}
    world.tension = 0.68
    app._refresh_crew_panel()
    app._refresh_char_panel()
    app._refresh_plot_panel()
    page.update()
    await asyncio.sleep(0.7)

    n_pos = len([r for r in loop.studio.ledger() if not r.get('is_sub')])
    ok(f'C0 ★ 剧组里确实有 {n_pos} 个职位要显示', n_pos >= 19, f'n={n_pos}')

    # ── C1 ★★★ 用户诉求本身：`max_scroll_extent == 0` ──
    # [EN] ── C1 ★★★ the user's request itself: `max_scroll_extent == 0` ──
    seen: dict = {}

    def _on_scroll(e):
        seen['max'] = float(getattr(e, 'max_scroll_extent', 0) or 0)
        seen['vp'] = float(getattr(e, 'viewport_dimension', 0) or 0)

    # ⚠ 右栏宽度**读产品常量**（2026-10-24 用户要求右栏加宽 240→400 之后，
    #   这里写死的 240 会让右栏直接找不到 ⇒ C1/C2/D1 全红）。
    #   判据量的就是产品上那个 Column，尺寸只能有一个事实来源。
    # [EN] ⚠ The width comes from **the product constant** (after the user asked for a wider right
    # [EN] column on 2026-10-24, the hardcoded 240 made it unfindable => C1/C2/D1 all red).
    # [EN] The criterion measures that very Column, so the size may have only one source of truth.
    from gui.app_flet import RUN_RIGHT_W as _RW
    cand = [c for c in VU.walk(page)
            if isinstance(c, ft.Column) and getattr(c, 'width', None) == _RW]
    right = min(cand, key=lambda c: len(list(VU.walk(c)))) if cand else None
    ok('C1a ★ 右栏那个可滚 Column 找得到（宽随 `RUN_RIGHT_W`）', right is not None,
       f'候选 {len(cand)} 个 · 期望宽 {_RW}')
    if right is not None:
        right.on_scroll = _on_scroll
        try:
            await right.scroll_to(offset=1)
        except Exception:                                        # noqa: BLE001
            pass
        await asyncio.sleep(0.4)
        try:
            await right.scroll_to(offset=0)
        except Exception:                                        # noqa: BLE001
            pass
        await asyncio.sleep(0.3)
    mx = seen.get('max')
    ok('C1 ★★★ 右栏**一格都不用滚**就装下了全部职位'
       '（`max_scroll_extent == 0` —— 用户原话"所有Agents一次性显示出来"）',
       mx == 0.0, f'max={mx} viewport={seen.get("vp")}')

    # ── C2 屏幕上真的画出来了：数剧组面板里的行 ──
    # [EN] ── C2 really drawn on screen: count the rows inside the Cast panel ──
    png = await page.take_screenshot()
    (OUT / 'crew_density_after.png').write_bytes(png or b'')
    W, H = VU.image_of(png).size
    # ⚠ 右栏宽度**读常量**：写死 264/34 的话，右栏一变宽扫描窗口就整个错位，
    #   屏幕上明明有 19 行也数出 0 行（2026-10-24 加宽到 400 时实测）。
    # [EN] ⚠ Read the width from the constant: with 264/34 hardcoded, widening the column
    # [EN] shifts the scan window off the panel and nineteen visible rows count as zero
    # [EN] (measured when widening to 400 on 2026-10-24).
    from gui.app_flet import RUN_RIGHT_W as _RW
    _lane = 8 + 12 + 12          # 栏间距 + 面板左右内边距
    X0, X1 = W - (_RW + _lane), W - 34
    im = VU.image_of(png).convert('L')
    px = im.load()
    crew_top = None
    for y in range(300, 620):
        d = sum(1 for x in range(X0 + 20, X1 - 20) if px[x, y] < 190)
        if d > (X1 - X0) - 60:
            crew_top = y
            break
    ok('C2a 屏幕上找得到「剧组」面板的上边框', crew_top is not None, f'y={crew_top}')
    if crew_top:
        ys = _text_rows(png, (X0 + 24, crew_top + 4, X1 - 6, H - 8))
        bs = _bands(ys)
        # 第一条是标题「剧组」，最后一条是面板底下那句提示。
        # [EN] the first band is the "Cast" title, the last one is the hint under the panel.
        row_bands = max(0, len(bs) - 2)
        ok(f'C2 ★★★ 屏幕上数出来的职排行数 ≥ {n_pos}'
           f'（标题与底部提示不算；一屏画全了才算"一次性显示出来"）',
           row_bands >= n_pos, f'数出 {row_bands} 行（带 {len(bs)} 条）/ 应有 {n_pos}')
        starts = [a for a, _ in bs]
        deltas = [starts[i + 1] - starts[i] for i in range(1, len(starts) - 1)]
        if deltas:
            mid = sorted(deltas)[len(deltas) // 2]
            ok('D1 ★★★ 每个 Agent 只占 **≈22px**（改前 41–42px）'
               '—— 像素量的，不读代码',
               16 <= mid <= 28, f'相邻行距中位数 = {mid}px')
        else:
            ok('D1 ★★★ 每个 Agent 只占 ≈22px（改前 41–42px）', False, '没量到行距')

    # ── C3 剧组面板底部还留在屏幕里 ──
    # [EN] ── C3 the bottom of the Cast panel is still on screen ──
    if crew_top:
        ys = _text_rows(png, (X0 + 24, crew_top + 4, X1 - 6, H - 8))
        bs = _bands(ys)
        if bs:
            last_y = crew_top + bs[-1][1]
            ok('C3 ★★★ 「剧组」最后一行**还在屏幕内**（没被切在视口外）',
               last_y < H - 40, f'最后一行 y={last_y} / 窗口高 {H}')


# ══════════════════════════════════════════════════════════════
async def main(page: ft.Page | None) -> None:
    print('\n── A 结构：默认单行 ──')
    try:
        structure_checks()
    except Exception:                                            # noqa: BLE001
        ok('A 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── B 文案一个字都没丢 ──')
    try:
        wording_checks()
    except Exception:                                            # noqa: BLE001
        ok('B 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── C/D 真机：一屏放下、每行 22px ──')
    if page is None:
        print('  （--logic-only：跳过）')
    else:
        try:
            await real_checks(page)
        except Exception:                                        # noqa: BLE001
            ok('C 组跑完', False, traceback.format_exc()[-400:])
            print(traceback.format_exc()[-1200:])

    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n剧组一屏显示验证：{good}/{n}')
    (OUT / 'crew_density_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if page is not None:
        await shutdown(page, code=(0 if good == n else 2))


if __name__ == '__main__':
    if ONLY_LOGIC:
        asyncio.run(main(None))
        sys.exit(0)
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
