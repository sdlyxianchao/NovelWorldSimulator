# -*- coding: utf-8 -*-
"""验证：运行界面的输出样式（类型分层 / 分隔符 / 底部状态条）。

用户需求（2026-10-06）
---------------------
1. 「运行界面的中间输出窗口 我希望在最下面一直有一个小的状态提示条，表示当前在生成
   还是等待用户输入还是别的，字体可以用灰色以示区别，用一个比较小的椭圆形框包起来
   以示区别，以免用户觉得系统卡死。」
2. 「对话界面针对不同内容 比如对话 场景 旁白 心理活动 等等（你补充缺少的）把输出
   样式再美化一下，更好看更容易区分。」
3. 「一天以及一个场景和一个故事结束之后，给一个明显的分隔符，不同类型…用不同的
   分隔符，分隔符还可以用于某个模块开始，分隔符中间可以带时间（小说里的时间）
   标题 以及别的关键信息（不能太长）。」

产出：`assets/screenshots/run_style_*.png` + `run_style_report.json`

用法：
    .venv/Scripts/python.exe tools/verify_run_output_style.py
    .venv/Scripts/python.exe tools/verify_run_output_style.py --logic-only

English:
Verify: output styles of the running UI (type layering / separators / bottom status bar).
User requirements (2026-10-06)
---------------------
1. "The middle output window of the running UI. I want a small status hint bar always at the bottom, showing whether it's currently generating
   or waiting for user input or something else. Gray font to distinguish it, wrapped in a relatively small oval box
   to distinguish it, so the user doesn't think the system is frozen."
2. "For the chat UI, for different content such as dialogue, scene, narration, inner monologue, etc. (you fill in what's missing), make the output
   styles more beautiful, prettier and easier to distinguish."
3. "After a day, a scene and a story end, give an obvious separator; different types... use different
   separators; separators can also be used when a module starts; the middle of the separator can carry time (in-story time),
   title, and other key information (can't be too long)."
Output: `assets/screenshots/run_style_*.png` + `run_style_report.json`
Usage:
    .venv/Scripts/python.exe tools/verify_run_output_style.py
    .venv/Scripts/python.exe tools/verify_run_output_style.py --logic-only
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft                                       # noqa: E402
from util.flet_shutdown import shutdown                 # noqa: E402

from config import CFG                                  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('OUTPUT_FORMAT', 'script')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from i18n import set_lang, t                            # noqa: E402
set_lang(_lang)

from display import dividers as DIV                     # noqa: E402
from display import script as S                         # noqa: E402
from display import script_render as SR                 # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'
ONLY_LOGIC = '--logic-only' in sys.argv
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:300]})
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A 组：纯逻辑
# [EN] Group A: Pure logic
# ══════════════════════════════════════════════════════════════
async def logic_checks() -> None:
    # ── A1 分隔符：五类都能出规范的"细线 + 标签" ──
    # [EN] ── A1 Separators: all five types can produce a canonical "thin line + label" ──
    cases = {
        DIV.DAY_START: DIV.day_start(7, '辰时 07:20'),
        DIV.DAY_END: DIV.day_end(7, scenes=12, events=3),
        DIV.SCENE_END: DIV.scene_end('戌时', '临河茶肆'),
        DIV.STORY_END: DIV.story_end(day=12, scenes=31, note='到达故事终点'),
        DIV.MODULE_START: DIV.module_start('导出', '素材册'),
    }
    ok('A1 五类分隔符都出得了规范形态（细线 + 标签）',
       all(d.line().count('─') > 20 and d.symbol in d.line() and ' · ' in d.line()
           for d in cases.values()),
       [d.line()[:24] for d in cases.values()])
    ok('A1b 每类各有自己的符号（一眼能分清是哪一类分界）',
       len({d.symbol for d in cases.values()}) == 4,     # 两个 day 共用 ◆
       # [EN] Two days share ◆
       {k: v.symbol for k, v in cases.items()})
    ok('A1c 落盘形态是引用块（`> ` 起头），不会被人反解成台词或正文',
       all(d.md_line().startswith('> ──') for d in cases.values()),
       cases[DIV.DAY_START].md_line()[:20])

    # ── A2 信息量上限：**整段塞不下就丢段**，不做半截话 ──
    # [EN] ── A2 Information cap: **if the whole segment doesn't fit, drop the segment**, no half-sentences
    # [EN] ──
    long = DIV.story_end(day=999, scenes=8888, note='这是一个非常长的结束原因' * 3)
    ok('A2 标签总长有上限（不会把细线挤没）',
       len(long.label()) <= DIV.MAX_LABEL + 2, f'{len(long.label())} 字')
    ok('A2b 截断是"丢段"而不是"把句子截成…"',
       not long.label().rstrip().endswith('…') or '…' not in long.label()[:-1],
       long.label())

    # ── A3 未知类型要当场炸（不是静默画个空分隔符）──
    # [EN] ── A3 Unknown types must blow up on the spot (not silently draw an empty separator) ──
    try:
        DIV.Divider('nope')
        ok('A3 未知分隔符类型抛异常', False, '没抛')
    except ValueError as e:
        ok('A3 未知分隔符类型抛异常', True, str(e)[:40])

    # ── A4 新词条类型：markdown 往返不丢类型 ──
    # [EN] ── A4 New entry type: markdown round-trip preserves the type ──
    sc = S.SceneScript(time_label='戌时 19:30', place='临河茶肆', cast=['主角'])
    sc.add(S.dialogue('主角', '今夜别出门。', to='阿枝', tone='压低声音'))
    sc.add(S.ambient('雨脚敲着檐瓦，檐下灯笼晃了晃。'))
    sc.add(S.recall('主角', '那年也是这样的雨。'))
    sc.add(S.aside('阿枝', '他今天不对劲。'))
    back = SR.parse_markdown(SR.to_markdown(sc))[0]
    kinds = [e.kind for e in back.entries]
    ok('A4 环境/回想写进 markdown 再读回来，类型不丢',
       kinds == [S.DIALOGUE, S.AMBIENT, S.RECALL, S.ASIDE], kinds)
    ok('A4b 两者的屏幕前缀互不混淆',
       SR.one_line(sc.entries[1]).startswith('〔环境〕')
       and SR.one_line(sc.entries[2]).startswith('〔回想·'),
       [SR.one_line(e) for e in sc.entries[1:3]])

    # ── A5 样式表要覆盖**全部**词条类型（加了类型忘配样式就会退回默认）──
    # [EN] ── A5 The style table must cover **all** entry types (add a type and forget the style → falls
    # [EN] back to default) ──
    from gui.app_flet import _LIVE_STYLE
    from display import story_render as STR
    missing = [k for k in S.ALL_KINDS if k not in _LIVE_STYLE]
    ok('A5 实时流样式表覆盖所有词条类型（防"加了类型忘配样式"）',
       not missing, f'缺: {missing}')
    ok('A5b 每种类型都有独立的视觉特征（颜色/缩进/斜体/竖线四项不全同）',
       len({v for v in _LIVE_STYLE.values()}) >= 8,
       f'不同样式组合 {len({v for v in _LIVE_STYLE.values()})} 种')
    # ★ 2026-10-06「中栏小说体」之后，样式分成两张表、各管一段：
    #   叙述类（并进段落的）在 `story_render.SPAN_STYLE`，其余仍在 `_LIVE_STYLE`。
    #   两者**必须刚好互补**：漏一个就是"那种词条渲染成了默认样子"。
    # [EN] ★ After 2026-10-06 "middle-column novel style", styles split into two tables, each covering one
    # [EN] part:
    # [EN] Narrative types (merged into paragraphs) live in `story_render.SPAN_STYLE`, the rest remain in
    # [EN] `_LIVE_STYLE`.
    # [EN] The two **must be exactly complementary**: miss one and "that entry type renders as the default
    # [EN] look".
    span_missing = [k for k in STR.JOINABLE if k not in STR.SPAN_STYLE]
    ok('A5c 并进段落的叙述类都配了段内样式（SPAN_STYLE）',
       not span_missing, f'缺: {span_missing}')
    ok('A5d 段内样式表**恰好**对着"能并段的类型"（多一个少一个都是隐患：'
       '多配了说明有类型被误当成叙述，少配了说明它在段落里没样式）',
       set(STR.SPAN_STYLE) == set(STR.JOINABLE),
       f'SPAN_STYLE={sorted(STR.SPAN_STYLE)} JOINABLE={sorted(STR.JOINABLE)}')

    # ── A6 两类新词条**真的有人产生**（不是死类型）──
    # [EN] ── A6 The two new entry types **are actually produced by someone** (not dead types) ──
    import inspect
    from display import scene_builder as SB
    src_q = inspect.getsource(SB.SceneBuilder.observe_quiet)
    src_r = inspect.getsource(SB.SceneBuilder.observe_reflection)
    ok('A6 环境白描有真实来源（没人动的那些片刻写它）',
       'S.ambient(' in src_q, src_q.strip().splitlines()[0][:50])
    ok('A6b 回想有真实来源（人物反思时写它）',
       'S.recall(' in src_r, src_r.strip().splitlines()[0][:50])

    # ── A7 主循环的播报链路（不起窗口，直接装配跑几拍）──
    # [EN] ── A7 The main loop's broadcast chain (no window, just assemble and run a few ticks) ──
    from verify_ui_common import isolate_projects_dir, safe_rmtree
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim.setup import assemble
    from sim.session import RunSession

    tmp = Path(tempfile.mkdtemp(prefix='nws_runstyle_'))
    isolate_projects_dir(tmp / 'Projects')
    try:
        proj = make_project(tmp / '样式验证')
        run = RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
        # ⚠ 跨天**不靠等**：等多久都可能不够，而"拨 `_last_mono`"实测没被主循环
        #   采纳（`_advance_clock` 每圈都会把它重置）。**直接改 `game_day`** 是最
        #   确定的 —— 它触发的正是 `run()` 里那条真实分支（`world.game_day !=
        #   self._current_day`），测到的就是产品代码，不是替身。
        # [EN] ⚠ Crossing days **doesn't rely on waiting**: any wait may be insufficient, and "nudging
        # [EN] `_last_mono`" was measured to not be
        # [EN] adopted by the main loop (`_advance_clock` resets it every cycle). **Directly changing
        # [EN] `game_day`** is the most
        # [EN] certain — what it triggers is exactly the real branch in `run()` (`world.game_day !=
        # [EN] self._current_day`), so what's tested is production code, not a stand-in.
        CFG.set('TIME_RATIO', '1')
        CFG.set('BEAT_SECONDS', '2')
        loop, world, _ = assemble(proj, run)
        world.progress_nodes = []
        got = {'div': [], 'st': [], 'narr': []}
        ses = RunSession(
            loop, world, run,
            on_narrative=lambda tx, pr, **kw: got['narr'].append((tx, kw.get('kind', ''))),
            on_divider=lambda d: got['div'].append(d),
            on_status=lambda k, **kw: got['st'].append(k))
        ses.start()
        await asyncio.sleep(4)              # 先正常跑几拍（攒出叙事/状态/幕终）
        world.game_day = int(world.game_day or 1) + 2   # 制造一次跨天
        await asyncio.sleep(1.8)            # → run() 的跨天分支必然走到
        # [EN] First run a few ticks normally (accumulate narrative/state/act-end)
        # [EN] Manufacture a day crossing
        # [EN] → the day-crossing branch of run() is guaranteed to be hit
        ses.stop()
        await ses.wait(20)

        dk = [d.kind for d in got['div']]
        ok('A7 主循环真的推了分隔符（日始/日终）',
           DIV.DAY_START in dk and DIV.DAY_END in dk, dk)
        ok('A7b 日终分隔符带上了"当天几幕"这种关键信息',
           any(d.kind == DIV.DAY_END and 'scenes' in d.meta for d in got['div']),
           [(d.kind, d.meta) for d in got['div']][:4])
        ok('A7c 新的一天带上了小说里的时辰',
           any(d.kind == DIV.DAY_START and str(d.meta.get('clock') or '').strip()
               for d in got['div']),
           [d.meta for d in got['div'] if d.kind == DIV.DAY_START][:2])
        ok('A7d 主循环真的报了细粒度状态（正在生成/核对进度…）',
           'deciding' in got['st'] and 'evaluating' in got['st'],
           sorted(set(got['st'])))
        ok('A7e 叙事回调拿到了词条类型（界面才能分样式）',
           any(k for _, k in got['narr']),
           f'{len(got["narr"])} 条，带类型的 {sum(1 for _, k in got["narr"] if k)} 条')

        # ── A8 收尾要推「故事结束」 ──
        # [EN] ── A8 The wrap-up must push "story end" ──
        got['div'].clear()
        await loop._finish('到达故事终点')
        ok('A8 收尾推了「全篇终」分隔符',
           any(d.kind == DIV.STORY_END for d in got['div']),
           [d.kind for d in got['div']])

        # ── A9 播报失败**不许静默吞掉**（本项目栽过太多次）──
        # [EN] ── A9 Broadcast failures **must not be silently swallowed** (this project has been burned too
        # [EN] many times) ──
        got2 = {'st': []}
        loop2 = loop

        def _boom(*a, **k):
            raise RuntimeError('回调故意炸')

        loop2._cb_warned.clear()
        loop2._on_status = _boom
        loop2._status('deciding')           # 不许抛出去
        # [EN] Must not raise outward
        loop2._on_status = None
        ok('A9 播报回调抛异常不会打断推演（且留了痕）',
           'status' in loop2._cb_warned, sorted(loop2._cb_warned))
    finally:
        safe_rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
#  B 组：真机（中栏样式 / 分隔符 / 底部状态条）
# [EN] Group B: Real device (middle-column style / separators / bottom status bar)
# ══════════════════════════════════════════════════════════════
async def gui_checks(page: ft.Page, app) -> None:
    from gui.app_flet import C
    from verify_ui_common import isolate_projects_dir, safe_rmtree, all_texts
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim.setup import assemble
    from sim.session import RunSession

    tmp = Path(tempfile.mkdtemp(prefix='nws_runstyle_gui_'))
    isolate_projects_dir(tmp / 'Projects')

    async def shot(name: str, note: str = '') -> bytes:
        page.update()
        await asyncio.sleep(0.35)
        data = await page.take_screenshot()
        (OUT / f'{name}{SUFFIX}.png').write_bytes(data)
        report.setdefault('shots', []).append({'file': name, 'note': note})
        return data

    try:
        proj = make_project(tmp / '样式真机')
        run = RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
        CFG.set('TIME_RATIO', '1')
        CFG.set('BEAT_SECONDS', '2')
        loop, world, _ = assemble(proj, run)
        world.progress_nodes = []
        app.current_project = proj
        app._activate_project(proj)

        # 用界面自己的接线（走真实入口的等价路径）
        # [EN] Use the UI's own wiring (path equivalent to the real entry point)
        app._live_lines = []
        app.session = RunSession(loop, world, run,
                                 on_narrative=app._on_narrative,
                                 on_divider=app._on_divider,
                                 on_status=app._on_status,
                                 on_state=app._on_state)
        app.show_main_screen()
        page.update()
        await asyncio.sleep(1.0)

        # ── B1 底部状态条：椭圆的、灰字、常驻 ──
        # [EN] ── B1 Bottom status bar: oval, gray text, persistent ──
        bar = getattr(app, '_run_status_bar', None)
        txt = getattr(app, '_run_bar_text', None)
        ok('B1 中栏底部建出了常驻状态条', bar is not None and txt is not None,
           f'bar={type(bar).__name__}')
        ok('B1b 是"小椭圆框"（圆角足够大 → 胶囊）',
           int(getattr(bar, 'border_radius', 0) or 0) >= 99,
           getattr(bar, 'border_radius', None))
        ok('B1c 状态字是灰的（以示区别）',
           str(getattr(txt, 'color', '')) == C['muted'], getattr(txt, 'color', None))
        # 像素证据：把胶囊边框涂成品红，证明它**真的画在屏幕上**
        # [EN] Pixel evidence: paint the capsule border magenta, proving it **is actually drawn on screen**
        old_bc = bar.border
        try:
            _mag = ft.BorderSide(width=2, color='#ff00ff')
            bar.border = ft.Border(left=_mag, top=_mag, right=_mag, bottom=_mag)
            page.update()
            await asyncio.sleep(0.3)
            png = await page.take_screenshot()
            (OUT / f'run_style_bar_marker{SUFFIX}.png').write_bytes(png)
            import io as _io
            from PIL import Image
            im = Image.open(_io.BytesIO(png)).convert('RGB')
            px = im.load()
            n = sum(1 for y in range(im.height) for x in range(im.width)
                    if px[x, y][0] > 200 and px[x, y][1] < 80 and px[x, y][2] > 200)
            ok('B1d 胶囊框真的画出来了（标记色像素 > 200）', n > 200, n)
        finally:
            bar.border = old_bc
            page.update()

        # ── B2 跑起来：分隔符与新样式 ──
        # [EN] ── B2 Run it: separators and new styles ──
        app.session.start()
        await asyncio.sleep(5)
        world.game_day = int(world.game_day or 1) + 2   # 制造跨天（分隔符才有戏）
        # [EN] Manufacture a day crossing (only then do separators come into play)
        await asyncio.sleep(2.0)
        col = app._ui_run.get('narrative')
        controls = list(getattr(col, 'controls', []) or [])
        n_items = len(controls)
        report['bars'] = {'n_controls': n_items,
                          'live_lines': len(app._live_lines),
                          'status_text': getattr(txt, 'value', '')}
        await shot('run_style_running', '运行中：分隔符 + 分类型样式 + 底部状态条')

        ok('B2 跑起来后中栏有内容', n_items > 3, n_items)
        ok('B2b 中栏出现了分隔符（含细线 + 胶囊标签）',
           any(isinstance(c, ft.Container) and isinstance(getattr(c, 'content', None), ft.Row)
               and len(getattr(c.content, 'controls', [])) == 3
               for c in controls),
           f'{n_items} 个控件')
        ok('B2c 状态条的字跟着推演在变（不是一句静止的话）',
           str(getattr(txt, 'value', '') or '') != '', getattr(txt, 'value', ''))
        # ⚠ 判据从「**恰好**三元组」放宽成「**至少**记下了前三样」（2026-10-11）：
        #   `_live_lines` 的元素扩成四元组（尾部加时间戳 `ts`），`len(it) == 3` 当场变红。
        #   ★ 这不是放水 —— 这条要守的是"**每一行都带着词条类型**（第三位）"，
        #     而那件事由 `>= 3` 完整保住。真正"时间戳有没有加上去"由
        #     `tools/verify_narr_window.py` 的 C 组管。
        # [EN] ⚠ Loosened from "**exactly** a 3-tuple" to "**at least** the first three are recorded"
        # [EN] (2026-10-11): `_live_lines` elements became a 4-tuple (a timestamp `ts` appended), so
        # [EN] `len(it) == 3` went red on the spot.
        # [EN] ★ This is not watering it down -- what this guards is "**every line carries its entry
        # [EN] kind** (the third field)", and `>= 3` preserves exactly that. Whether the timestamp is
        # [EN] really appended is covered by group C of `tools/verify_narr_window.py`.
        ok('B2d 实时行记下了词条类型（重进界面能按类型恢复样式）',
           all(len(it) >= 3 for it in app._live_lines) and len(app._live_lines) > 0,
           f'{len(app._live_lines)} 行')
        kinds = {it[2] for it in app._live_lines}
        ok('B2e 至少出现了两种以上不同的词条类型',
           len(kinds) >= 2, sorted(kinds))

        # ── B3 分隔符的**屏幕证据**：把一枚日终分隔符直接推上去，涂色量像素 ──
        # [EN] ── B3 **Screen evidence** for separators: push a day-end separator directly, count colored
        # [EN] pixels ──
        #
        # ⚠⚠ 这里踩过两次，两条教训都写下来（2026-10-07）：
        #   ① **不能盲取 `col.controls[-1]`**：推演还在跑，主循环每一拍都往中栏
        #      末尾追加叙事控件，`[-1]` 很可能已经不是刚推的那枚分隔符 ——
        #      涂洋红涂到别的控件上，像素数恒为 0。
        #   ② 即使**按形状找对了那枚控件**，也可能量到 0 —— 它在列表末尾，
        #      **滚出可视区了**。实测同一份代码会时红时绿（假红）。
        #   所以：先**停掉推演**（不再有新内容进来），再**清空中栏**，
        #   然后推那枚分隔符 —— 它是唯一的控件，必定在可视区顶部。
        #   量的是**真的画出来的像素**，不是"控件属性对了"。
        # [EN] ⚠⚠ Two pitfalls here, both lessons written down (2026-10-07):
        # [EN] ① **Don't blindly take `col.controls[-1]`**: the simulation is still running, and every tick of
        # [EN] the main loop appends a narrative control
        # [EN] to the end of the middle column, so `[-1]` may no longer be the just-pushed separator —
        # [EN] painting magenta lands on some other control, pixel count stays at 0.
        # [EN] ② Even if you **find the right control by shape**, you may still measure 0 — it's at the end of
        # [EN] the list,
        # [EN] **scrolled out of the visible area**. In practice the same code is sometimes red, sometimes
        # [EN] green (false red).
        # [EN] So: first **stop the simulation** (no new content comes in), then **clear the middle column**,
        # [EN] then push that separator — it's the only control, guaranteed to be at the top of the visible
        # [EN] area.
        # [EN] What's measured is **the pixels actually drawn**, not "the control properties are right".
        try:
            app.session.stop()
            await app.session.wait(15)
        except Exception:                                          # noqa: BLE001
            pass
        col.controls.clear()
        app._live_lines.clear()
        col.update()
        await asyncio.sleep(0.4)

        app._on_divider(DIV.day_end(3, scenes=5))
        page.update()
        await asyncio.sleep(0.4)
        # 按**形状**找分隔符：`Container(Row([细线, 胶囊, 细线]))`
        # [EN] Find separators by **shape**: `Container(Row([thin line, capsule, thin line]))`
        def _find_divider():
            for c in reversed(list(getattr(col, 'controls', []) or [])):
                if (isinstance(c, ft.Container)
                        and isinstance(getattr(c, 'content', None), ft.Row)
                        and len(getattr(c.content, 'controls', [])) == 3):
                    return c
            return None

        d_ctl = _find_divider()
        ok('B3a 推上去的分隔符在中栏里（按形状找得到）', d_ctl is not None,
           f'{len(getattr(col, "controls", []) or [])} 个控件')
        if d_ctl is None:                       # 找不到就退回旧写法，别让后面炸
        # [EN] If not found, fall back to the old approach, don't let the rest blow up
            d_ctl = col.controls[-1] if getattr(col, 'controls', None) else None
        old_bg = d_ctl.content.controls[1].bgcolor
        try:
            d_ctl.content.controls[1].bgcolor = '#ff00ff'
            _mag2 = ft.BorderSide(width=2, color='#ff00ff')
            d_ctl.content.controls[1].border = ft.Border(
                left=_mag2, top=_mag2, right=_mag2, bottom=_mag2)
            page.update()
            await asyncio.sleep(0.3)
            png = await page.take_screenshot()
            (OUT / f'run_style_divider_marker{SUFFIX}.png').write_bytes(png)
            import io as _io
            from PIL import Image
            im = Image.open(_io.BytesIO(png)).convert('RGB')
            px = im.load()
            n = sum(1 for y in range(im.height) for x in range(im.width)
                    if px[x, y][0] > 200 and px[x, y][1] < 80 and px[x, y][2] > 200)
            ok('B3 分隔符的胶囊标签真的画在屏幕上（标记色像素 > 300）', n > 300, n)
        finally:
            d_ctl.content.controls[1].bgcolor = old_bg
            page.update()
        ok('B3b 分隔符的标签文字是"给人看的一句话"（含天数）',
           '3' in str(getattr(d_ctl.content.controls[1].content, 'value', '')),
           getattr(d_ctl.content.controls[1].content, 'value', ''))

        app.session.stop()
        await app.session.wait(20)
    finally:
        safe_rmtree(tmp, ignore_errors=True)


async def entry(page: ft.Page) -> None:
    await logic_checks()
    if ONLY_LOGIC:
        return
    from gui.app_flet import NovelWorldApp
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)
    await gui_checks(page, app)


def write_report() -> None:
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / f'run_style_report{SUFFIX}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"断言 {len(report['checks']) - len(bad)}/{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1500:])
    print('ok:', report['ok'])


if __name__ == '__main__':
    if ONLY_LOGIC:
        try:
            asyncio.run(logic_checks())
        except BaseException:                                # noqa: BLE001
            report['fatal'] = traceback.format_exc()
        finally:
            CFG.set('TIME_RATIO', '1')       # 验证用的加速值**不许留在 .env 里**
            # [EN] Acceleration values used for verification **must not remain in .env**
            CFG.set('BEAT_SECONDS', '1')
        write_report()
        raise SystemExit(0 if report['ok'] else 2)

    async def main(page: ft.Page) -> None:
        try:
            await entry(page)
        except BaseException:                                # noqa: BLE001
            report['fatal'] = traceback.format_exc()
        finally:
            CFG.set('TIME_RATIO', '1')       # 验证用的加速值**不许留在 .env 里**
            # [EN] Acceleration values used for verification **must not remain in .env**
            CFG.set('BEAT_SECONDS', '1')
            write_report()
            await shutdown(page, code=0 if report['ok'] else 2)

    ft.run(main)
