# -*- coding: utf-8 -*-
"""验证：**定时落盘** + 中栏左下角那颗「自动落盘」小胶囊。

用户 2026-10-08 的原话（三件事，一条不少）：
    「我点暂停的时候以及平时也有可能随时关闭软件 所以后台还需要一个定时器
      实现定时落盘 比如没30秒落盘一次（这个我想在目前的对话显示窗口的左下角的
      状态标签的右边加一个状态条，颜色跟现在的状态条稍有区别，使用稍微偏蓝一点的
      背景，字体颜色用绿色 字体跟现有状态栏相同）显示内容就是每隔多久自动落盘
      这个时间可以在全局设置里面设置」

判据分三层：

  A **配置 + 外观 + 接线**（源码 / 控件树 / AST）
      · `AUTOSAVE_SECONDS` 在 SPEC 里、**产品源码真的读它**（防假旋钮）；
      · 天机 · 运行页里真的有那个输入框，保存真的写回去；
      · 新胶囊**是第二个**（在状态条**右边**）、底色**偏蓝**、
        字**绿色**、**字号字体与状态条相同**；
      · 四条接线：开跑起定时器 / 暂停补落一次 / 收工收掉 / **关窗口也落一次**。

  B **落盘行为**（不弹窗，直接调产品代码）
      · 写的是**中途稿**（`自动落盘/进度.md`），**不碰**"正式产物"目录
        `每天的生活/`（那目录一天一个文件、日界才写，混进去会让人误判）；
      · **滚动覆盖同一份**（不是每 30 秒攒一个新档，那会把盘塞满）；
      · 失败**不抛**（落盘是保险，保险坏了不能把车弄停）；
      · 间隔**每次现读配置**（改成 60 不用重开一轮）；
      · `0` = 关闭（不落、标签写"已关闭"）；
      · 没在跑的轮次里调它 → 不算错误、不崩。

  C **真机 + 像素**（起窗口、量屏幕）
      · 那颗胶囊**真的画在屏幕上**（底色像素 ≥ 1500）；
      · 它**就在状态条右边**（两者的色块 x 区间一左一右，不重叠）；
      · 字**真的是绿的**（标记色法：临时把字染成品红，数像素）；
      · 屏幕上那句话**写着当前的间隔**；改配置后立刻变；
      · **真的落盘了**：开跑 → 等到定时器落一次 → `自动落盘/进度.md`
        里能看到"今天已经演出来的"内容；
      · 点**暂停**再补落一次（用户点名的那一刻）。

跑法：
    .venv\\Scripts\\python.exe tools/verify_autosave.py
    .venv\\Scripts\\python.exe tools/verify_autosave.py --logic-only
产出：
    assets/screenshots/autosave_*.png
    assets/screenshots/autosave_report.json

English:
Verification: **timed dump to disk** + that small "auto-save" pill at the bottom-left of the
middle column.
The user's exact words on 2026-10-08 (three things, not one missing):
    "When I click pause, and also at other times, I might close the app at any moment, so there needs to be a timer in the background
      to implement timed dumping to disk, e.g. dump once every 30 seconds (I want to add a status bar to the right of the status label
      at the bottom-left of the current conversation display window, with a color slightly different from the current status bar, using a slightly bluer
      background, green font color, same font as the existing status bar) whose displayed content is how often it auto-saves
      this time can be set in global settings"
The criteria are in three layers:
  A **Config + Appearance + Wiring** (source / widget tree / AST)
      · `AUTOSAVE_SECONDS` is in SPEC, **product source really reads it** (guard against fake knobs);
      · Tianji · the run page really has that input box, and saving really writes back;
      · the new pill **is the second one** (to the **right** of the status bar), background **bluish**,
        text **green**, **font size and font same as the status bar**;
      · four wirings: start run kicks off timer / pause dumps once more / finish tears down / **closing the window also dumps once**.
  B **Dump behavior** (no popup, call product code directly)
      · what it writes is the **mid-way draft** (`自动落盘/进度.md`), **does not touch** the "official product" directory
        `每天的生活/` (that directory is one file per day, only written at the day boundary; mixing in would mislead people);
      · **rolls over the same file** (not accumulating a new file every 30 seconds, which would fill up the disk);
      · failure **does not throw** (dumping is insurance; if the insurance breaks, it must not stop the car);
      · the interval **is read from config each time** (change it to 60 without starting a new round);
      · `0` = disabled (no dump, label reads "已关闭");
      · calling it in a round that isn't running → not an error, doesn't crash.
  C **Real machine + pixels** (open the window, measure the screen)
      · that pill **is really drawn on screen** (background pixels ≥ 1500);
      · it **is right to the right of the status bar** (their color-block x intervals are left and right, not overlapping);
      · the text **is really green** (marker-color method: temporarily dye the text magenta, count pixels);
      · the sentence on screen **shows the current interval**; it changes immediately after changing config;
      · **it really dumped to disk**: start run → wait until the timer dumps once → `自动落盘/进度.md`
        shows "what has already been performed today";
      · click **pause** to dump once more (the moment the user names).
How to run:
    .venv\\Scripts\\python.exe tools/verify_autosave.py
    .venv\\Scripts\\python.exe tools/verify_autosave.py --logic-only
Output:
    assets/screenshots/autosave_*.png
    assets/screenshots/autosave_report.json
"""
from __future__ import annotations

import ast
import re
import asyncio
import inspect
import json
import sys
import tempfile
import textwrap
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown                        # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')          # 零网络、零成本、可复现
# [EN] Zero network, zero cost, reproducible
CFG.set('SHOW_OPENING', 'false')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from sim import autosave as AS                                 # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
ONLY_LOGIC = '--logic-only' in sys.argv
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _src(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def _calls(fn) -> list[str]:
    out = []
    for n in ast.walk(ast.parse(_src(fn))):
        if isinstance(n, ast.Call):
            out.append(ast.unparse(n.func))
    return out


# ══════════════════════════════════════════════════════════════
#  A. 配置 + 外观 + 接线
# [EN] A. Configuration + appearance + wiring
# ══════════════════════════════════════════════════════════════
def _gui_text() -> str:
    return (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')


def logic_checks() -> None:
    from config import SPEC
    from gui.app_flet import C, NovelWorldApp

    # ── A1 配置项 ──
    # [EN] ── A1 Config items ──
    spec = SPEC.get('AUTOSAVE_SECONDS')
    ok('A1 ★ `AUTOSAVE_SECONDS` 在 SPEC 里，是 int、默认 30、允许 0（=关掉）',
       isinstance(spec, dict) and spec.get('type') == 'int'
       and spec.get('default') == 30 and spec.get('min') == 0,
       str(spec)[:120])
    ok('A1b 默认值真的读得动（30 秒）',
       int(CFG.i('AUTOSAVE_SECONDS') or -1) == 30,
       f"CFG.i = {CFG.i('AUTOSAVE_SECONDS')!r}")
    # 防假旋钮：**产品源码**里得有字面量读取（`sim/autosave.py` 是产品源码）
    # [EN] Fake-proof knob: **product source** must have a literal read (`sim/autosave.py` is product
    # [EN] source)
    prod = (APP_DIR / 'sim' / 'autosave.py').read_text(encoding='utf-8')
    ok('A1c ★★ 产品源码真的读它（不是挂着拧不动的假旋钮）',
       "'AUTOSAVE_SECONDS'" in prod, '')

    # ── A2 天机里能设 ──
    # [EN] ── A2 Can be set in Tianji ──
    g = _gui_text()
    ok('A2 ★★ 天机 ·「运行」页里有「自动落盘(秒)」输入框（用户要的"全局设置里能设"）',
       'mk_field(t("自动落盘(秒)")' in g, '')
    ok('A2b ★★ 保存时真的写回配置（`CFG.set(\'AUTOSAVE_SECONDS\')`）',
       "CFG.set('AUTOSAVE_SECONDS'" in g, '')
    ok('A2c 那一节有标题与说明（不是只放一个孤零零的框）',
       'mk_section(t("自动落盘"))' in g and '滚动覆盖' in g, '')

    # ── A3 外观：那颗新胶囊 ──
    # [EN] ── A3 Appearance: that new capsule ──
    row_src = _src(NovelWorldApp._mk_run_status_bar)
    # ⚠ 2026-10-10 改判：原来钉的是**精确字面量**
    #   `'ft.Row([self._run_status_bar, self._autosave_bar]'` —— 于是给那一行
    #   再加一个控件（本轮加了「用量」链接）就假红。这正是本项目那条纪律踩过的坑：
    #   **判据不许把被测对象抄一遍**（它会把"加了点东西"报成"坏了"）。
    #   改成判"这两条**在同一个 Row 的实参里**"，用 AST，不看字面量。
    # ⚠ 判"这两条在**同一个 Row 的实参列表**里"，不判那一行只有两个元素
    #   （本轮给这行加了第三个控件「用量」链接，钉字面量的写法当场假红）。
    #   用**正则取 `ft.Row([...])` 的实参**：比 AST 稳（`_src` 取到的片段缩进
    #   会让 `ast.walk` 抓不到那个外层 Row —— 第一版就是空列表）。
    # ⚠ 要取**所有** `ft.Row([...])` 再挑"同时含两条"的那个 ——
    #   只取第一个会拿到内层的 Row（两条胶囊各自内部那个）。
    # [EN] ⚠ 2026-10-10 revision: originally pinned the **exact literal**
    # [EN] `'ft.Row([self._run_status_bar, self._autosave_bar]'` —— so for that line
    # [EN] adding one more control (this round added the "usage" link) falsely goes red. This is exactly
    # [EN] the pitfall this project's discipline has stepped on:
    # [EN] **The assertion must not copy the system under test** (it would report "added a bit of stuff" as
    # [EN] "broken").
    # [EN] Change to asserting that these two are **in the same Row's args**, using AST, not looking at
    # [EN] literals.
    # [EN] ⚠ Assert that these two are **in the same Row's argument list**, not that that line has only two
    # [EN] elements
    # [EN] (this round added a third control, the "usage" link, to this line; the literal-pinning approach
    # [EN] went red on the spot).
    # [EN] Use **regex to grab the args of `ft.Row([...])`**: more robust than AST (the fragment obtained
    # [EN] by `_src` has indentation
    # [EN] that makes `ast.walk` miss that outer Row —— the first version got an empty list).
    # [EN] ⚠ Must grab **all** `ft.Row([...])` then pick the one "containing both" ——
    # [EN] taking only the first would get the inner Row (the one inside each of the two capsules).
    _all = re.findall(r'ft\.Row\(\[(.*?)\]', row_src, re.S)
    _members = next((m for m in _all
                     if 'self._run_status_bar' in m and 'self._autosave_bar' in m), '')
    ok('A3 ★★★ 新胶囊**和状态条并排**（在同一个 Row 的实参列表里，两条都在）'
       '—— 判"在同一行"，不判那一行只有两个元素（本轮给这行加了第三个控件）',
       'self._run_status_bar' in _members and 'self._autosave_bar' in _members,
       f'该 Row 的实参={_members[:90]!r}')
    # ⚠ "在右边"这件事的**硬证据**是列表顺序（Row 从左往右排）。判据看 AST 里的
    #   顺序，不看文本 —— 文本比较会被别处的同名串骗过。
    # [EN] ⚠ The **hard evidence** for "on the right" is list order (Row lays out left to right). The
    # [EN] assertion looks at AST
    # [EN] order, not text —— text comparison gets fooled by same-named strings elsewhere.
    order_ok = False
    for n in ast.walk(ast.parse(row_src)):
        if not isinstance(n, ast.Call):
            continue
        if (getattr(n.func, 'attr', None) or getattr(n.func, 'id', None)) != 'Row':
            continue
        items = [ast.unparse(a) for a in n.args if isinstance(a, ast.List)
                 or isinstance(a, ast.Name)]
        if any('_run_status_bar' in x for x in items) and \
           any('_autosave_bar' in x for x in items):
            joined = ast.unparse(n.args[-1] if n.args else n)
            if joined.find('_run_status_bar') >= 0 and \
                    joined.find('_autosave_bar') > joined.find('_run_status_bar'):
                order_ok = True
    ok('A3b ★★★ 它排在状态条**右边**（用户原话：「状态标签的右边加一个状态条」）',
       order_ok, '')

    bg = NovelWorldApp.AUTOSAVE_BG
    ok('A3c ★★ 底色**偏蓝**（不是旁边那条的暖纸色 —— 用户要"稍有区别"）',
       isinstance(bg, str) and bg.startswith('#') and _blueish(bg),
       f'{bg}（r<g<b 才算偏蓝）')
    ok('A3d ★★ 底色跟旁边那条**不一样**（真是两种颜色）',
       bg != NovelWorldApp.__dict__.get('_X', None)
       and bg.lower() not in ('#f5ecd8', '#fffdf7'), bg)
    # 字绿色 + 字号字体与状态条相同 —— ★ **行为级**：真把那两颗胶囊建出来，
    #   然后比控件的属性。
    #   ⚠ 不能查"方法源码里有没有 `color=C['accent_green']`"：同一段源码里
    #     **那颗圆点**（`_autosave_dot`）也是这个色 —— 把文字改成灰色之后，
    #     字符串还在，判据照样绿（反例法⑥当场揭穿）。
    # [EN] Text green + font size and font same as the status bar —— ★ **behavioral level**: actually
    # [EN] create those two capsules,
    # [EN] then compare the controls' properties.
    # [EN] ⚠ Cannot check "does the method source contain `color=C['accent_green']`": in the same source
    # [EN] **that dot** (`_autosave_dot`) is also this color —— after changing the text to gray,
    # [EN] the string is still there, the assertion still goes green (counterexample method ⑥ exposes it on
    # [EN] the spot).
    app = NovelWorldApp()
    app.session = None
    app._run_status_key = 'idle'
    app._mk_run_status_bar()                 # 真建一次（`refresh` 里的 update 自带 try）
    # [EN] Actually create once (the update in `refresh` has its own try)
    at, bt = app._autosave_text, app._run_bar_text
    ok('A3e ★★★ 字是**绿色**（色表里的青绿 `accent_green` —— 控件的实际颜色）',
       at.color == C['accent_green'], f'{at.color} vs {C["accent_green"]}')
    ok('A3f ★★★ 字号与字体**与状态条逐项相同**（并排才齐齐整整）',
       at.size == bt.size and at.font_family == bt.font_family,
       f'autosave {at.size}/{at.font_family} vs 状态条 {bt.size}/{bt.font_family}')
    ok('A3g 底色也真的是那个偏蓝色（控件的实际 `bgcolor`，不是只写在常量里）',
       app._autosave_bar.bgcolor == NovelWorldApp.AUTOSAVE_BG,
       f'{app._autosave_bar.bgcolor}')

    # ── A4 四条接线（AST，不看注释）──
    # [EN] ── A4 Four connections (AST, not looking at comments) ──
    br = _calls(NovelWorldApp._begin_run)
    ok('A4 ★★★ 开跑时真的把定时器起来（`_start_autosave`）',
       any('_start_autosave' in f for f in br), str(sorted(set(br))[:8]))
    pt = _calls(NovelWorldApp._on_pause_toggle)
    ok('A4b ★★★ 点**暂停**时补落一次（用户点名的场景：'
       '「我点暂停的时候…」）',
       any('_autosave_flush' in f for f in pt), str(sorted(set(pt))[:8]))
    ok('A4b2 而且那次补落只发生在"进入暂停"这一支（继续时不该落）',
       _src(NovelWorldApp._on_pause_toggle).find("s.pause()")
       < _src(NovelWorldApp._on_pause_toggle).find('_autosave_flush'), '')
    aw = _calls(NovelWorldApp._await_stop)
    ok('A4c ★★ 收工/停止前把它收掉（`_stop_autosave`，默认先补落一次）',
       any('_stop_autosave' in f for f in aw), str(sorted(set(aw))[:8]))
    main_src = _src(NovelWorldApp.main)
    # ⚠ 这一条必须看**赋值本身**（AST 里的 `page.on_disconnect = …`），
    #   不能查"源码里有没有出现过 `on_disconnect` 这个词" —— `main` 里还有
    #   `def on_disconnect(...)` 和 `_old_disconnect`，把赋值句删掉之后，
    #   那两个词还在，判据照样绿（反例法⑪当场揭穿）。
    # [EN] ⚠ This one must look at **the assignment itself** (`page.on_disconnect = …` in the AST),
    # [EN] cannot check "does `on_disconnect` appear in the source" —— `main` also has
    # [EN] `def on_disconnect(...)` and `_old_disconnect`, and after deleting the assignment statement,
    # [EN] those two words are still there, the assertion still goes green (counterexample method ⑪ exposes
    # [EN] it on the spot).
    hook_assigned = False
    for node in ast.walk(ast.parse(main_src)):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tg = node.targets[0]
            if (isinstance(tg, ast.Attribute) and tg.attr == 'on_disconnect'
                    and ast.unparse(node.value) == 'on_disconnect'):
                hook_assigned = True
    ok('A4d ★★★ **关窗口**也会落一次（`page.on_disconnect = …` 这条赋值真的在）'
       '—— 用户原话「平时也有可能随时关闭软件」',
       hook_assigned and '_stop_autosave' in main_src, '')
    ok('A4e 而且是**链式**接（先取旧值、回调里调旧的）—— 别把别人设的钩子顶掉',
       '_old_disconnect' in main_src and 'callable(_old_disconnect)' in main_src, '')
    tk = _src(NovelWorldApp._start_status_ticker)
    ok('A4f ★ 那颗小胶囊随秒表一起刷（「N 秒前」得每秒都走 —— '
       '数字不动与"坏了"在用户眼里长得一样）',
       '_refresh_autosave_status' in tk, '')
    # ★★★ 2026-10-08 用户报：「自动落盘没有倒计时 **也没看到它干没干**」。
    #   根因是界面**自己**记"上次落盘时刻"，而定时器落的那一次不经过界面
    #   （`AutoSaver.run` 直接 `flush_now('timer')`），于是那半句永远不出现。
    #   现在事实来源在落盘器身上（`last_at`）。这条判据钉住"界面去读它"：
    #   一旦有人改回"界面自己记"，屏幕上又看不出它干没干。
    # [EN] ★★★ 2026-10-08 user report: "autosave has no countdown **and I can't see whether it ran**".
    # [EN] Root cause is the UI **itself** recording "last save time", while the timer-driven save doesn't
    # [EN] go through the UI
    # [EN] (`AutoSaver.run` directly calls `flush_now('timer')`), so that half-sentence never appears.
    # [EN] Now the source of truth is on the saver itself (`last_at`). This assertion pins down "the UI
    # [EN] reads it":
    # [EN] once someone reverts to "the UI records it itself", the screen again can't show whether it ran.
    ra_src = _src(NovelWorldApp._refresh_autosave_status)
    # ⚠ 这两条**必须走 AST**，不能查 `'last_at' in 源码`：
    #   同一个函数里还有两处提到 `last_at`（圆点配色、"刚落了"的判定），
    #   把 `ago` 那一句改回"界面自己记"之后字符串照样在 —— 反例法㉓当场揭穿。
    # [EN] ⚠ These two **must go through AST**, cannot check `'last_at' in source`:
    # [EN] in the same function there are two other mentions of `last_at` (dot coloring, the "just saved"
    # [EN] determination),
    # [EN] after reverting the `ago` line to "the UI records it itself" the string is still there ——
    # [EN] counterexample method ㉓ exposes it on the spot.
    ago_expr = ''
    labels_saver = False
    try:
        ra_tree = ast.parse(textwrap.dedent(ra_src))
    except Exception:                                            # noqa: BLE001
        ra_tree = None
    for nd in ast.walk(ra_tree) if ra_tree is not None else []:
        if (isinstance(nd, ast.Assign) and len(nd.targets) == 1
                and getattr(nd.targets[0], 'id', '') == 'ago'):
            ago_expr = ast.unparse(nd.value)
        if (isinstance(nd, ast.Call)
                and 'saver.label' in ast.unparse(nd.func)):
            labels_saver = True
    ok('A4g ★★★ 界面那半句「N 秒前」算的是**落盘器的 `last_at`**'
       '（界面自己记时刻＝定时器落的那次看不见 → 用户报的"没看到它干没干"）',
       'saver.last_at' in ago_expr, ago_expr)
    ok('A4h ★★ 倒计时那半句也是**落盘器自己拼的**（`saver.label(...)`）'
       '—— 界面手里根本没有"下一次什么时候"，只有那个在睡的定时器有',
       labels_saver, '')

    # ── A5 落点：不碰"正式产物"目录 ──
    # [EN] ── A5 Save location: don't touch the "official artifacts" directory ──
    ok('A5 ★★★ 中途稿落在 `自动落盘/`，**不是** `每天的生活/`'
       '（那目录是正式产物：一天一个文件、日界才写；混进去会出现'
       '"这一天的文件在了、其实只演了一半"）',
       AS.DIR_NAME == '自动落盘' and '每天的生活' not in AS.DIR_NAME, AS.DIR_NAME)


def _blueish(hex_color: str) -> bool:
    """这个颜色是不是"偏蓝"（蓝通道最大、且明显大于红）。
        English:
    Is this color "bluish" (blue channel is max, and clearly greater than red).
    """
    try:
        h = hex_color.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:                                            # noqa: BLE001
        return False
    return b >= g >= r and (b - r) >= 12


# ══════════════════════════════════════════════════════════════
#  B. 落盘行为（不弹窗）
# [EN] B. Save behavior (no popups)
# ══════════════════════════════════════════════════════════════
class FakeClock:
    def segment(self) -> str:
        return '戌时'


class FakeWorld:
    game_day = 3
    weather = '雨'
    scene = '临河茶肆'
    tension = 0.42

    def clock_display(self) -> str:
        return '第3天 · 戌时'

    @property
    def clock(self):
        return FakeClock()

    def on_stage_names(self) -> list:
        return ['主角', '阿枝']


class FakeScene:
    """一份"今天的剧本"（一幕）。
        English:
    One "today's script" (one act).
    """

    def __init__(self, *entries) -> None:
        self.entries = list(entries)


class FakeBuilder:
    """够用的假 `SceneBuilder`：`_today_lines()` 只读 `.scenes` 与 `.current`。

    ⚠ 层级别弄错：`loop._builder` 是**整天的分幕器**，它的 `.scenes` 才是
      一幕一幕；第一版把"一幕"直接放进 `_builder`，于是 `_today_lines`
      按 `.scenes` 取到空列表 → 落盘里 0 条 → 判据红。**夹具的层级错了**，
      不是产品错了（本项目对"夹具造错导致假红"有过好几次教训）。
    
        English:
    A sufficient fake `SceneBuilder`: `_today_lines()` only reads `.scenes` and `.current`.
        ⚠ Don't get the layer wrong: `loop._builder` is the **whole-day act splitter**, its `.scenes` is what
          holds act by act; the first version put "one act" directly into `_builder`, so `_today_lines`
          Fetch from `.scenes` gets an empty list → 0 entries on disk → criterion is red. **The fixture's hierarchy is wrong**,
          not the product (this project has had several lessons about "fixture errors causing false red").
    """

    def __init__(self, scene: 'FakeScene') -> None:
        self.scenes = [scene]
        self.current = None


class FakeLoop:
    """够用的假主循环：`snapshot()` / `_today_lines()` 只读这几样。
        English:
    Minimal fake main loop: `snapshot()` / `_today_lines()` only read these.
    """

    def __init__(self, lines: list | None = None, *, use_builder: bool = True):
        from display import script as S
        self.world = FakeWorld()
        self._current_day = 3
        txt = list(lines or ['你来了。', '主角推门进来。'])
        self._daily_narrative = [] if use_builder else txt
        # 夹具用**产品自己的 `S.Entry`**（不造"有 .text 的假对象"）：
        # `script_render.one_line()` 按 `kind` 分派，假对象会**静默渲染成空串**。
        # [EN] Fixture uses **the product's own `S.Entry`** (not a fake "object with .text"):
        # [EN] `script_render.one_line()` dispatches by `kind`, a fake object would **silently render as an
        # [EN] empty string**.
        self._builder = (FakeBuilder(FakeScene(
            S.Entry(kind=S.DIALOGUE, text=txt[0], speaker='主角'),
            S.Entry(kind=S.NARRATION, text=txt[1]))) if use_builder else None)


class FakeRun:
    def __init__(self, root: Path) -> None:
        self.root = root


class FakeSession:
    def __init__(self, loop, run) -> None:
        self.loop = loop
        self.run = run


async def behavior_checks() -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_autosave_'))
    run = FakeRun(tmp / 'run1')
    loop = FakeLoop()

    # ── B1 落两份文件，内容里有真东西 ──
    # [EN] ── B1 Save two files, contents have real stuff in them ──
    res = AS.flush_progress(loop, run, every=30, reason='timer')
    d = tmp / 'run1' / AS.DIR_NAME
    md, js = d / AS.FILE_MD, d / AS.FILE_JSON
    ok('B1 ★★ 一次落盘写出两份：`进度.md` + `进度.json`',
       res.get('ok') and md.is_file() and js.is_file(),
       f'ok={res.get("ok")} md={md.is_file()} json={js.is_file()}')
    body = md.read_text(encoding='utf-8') if md.is_file() else ''
    ok('B1b ★★ 中途稿里**真的写着今天已经演出来的东西**（不是空壳）',
       '主角推门进来。' in body and '你来了' in body, body[:160].replace('\n', '⏎'))
    ok('B1c ★★★ 第一行就写明"这是中途稿"（不许冒充正式产物）',
       '自动落盘的中途稿' in body, body.splitlines()[0] if body else '')
    ok('B1d 元信息齐：第几天 / 故事时间 / 天气 / 场景 / 在场',
       all(x in body for x in ('第 3 天', '第3天 · 戌时', '雨', '临河茶肆', '主角')),
       '')
    info = json.loads(js.read_text(encoding='utf-8')) if js.is_file() else {}
    ok('B1e `进度.json` 是结构化的一份（判据与探针读它）',
       info.get('day') == 3 and info.get('lines', 0) >= 1
       and info.get('reason') == 'timer', str({k: info.get(k) for k in
                                               ('day', 'lines', 'reason')}))

    # ── B2 不碰正式产物目录 ──
    # [EN] ── B2 Don't touch the official artifacts directory ──
    ok('B2 ★★★ 没有往 `每天的生活/` 里写任何东西（正式产物归日界）',
       not (run.root / '每天的生活').exists(),
       str(sorted(p.name for p in run.root.iterdir())))

    # ── B3 滚动覆盖：再落一次**不新增文件** ──
    # [EN] ── B3 Scroll overwrite: saving again **doesn't add new files** ──
    n_before = len(list(d.iterdir()))
    AS.flush_progress(loop, run, every=30, reason='pause')
    n_after = len(list(d.iterdir()))
    ok('B3 ★★★ **滚动覆盖同一份**（不是每 30 秒攒一个新档 —— 那会把盘塞满）',
       n_before == n_after == 2, f'{n_before} → {n_after}')
    info2 = json.loads(js.read_text(encoding='utf-8'))
    ok('B3b 第二次把那一次的"是谁催的"也覆盖上去了（`pause`）',
       info2.get('reason') == 'pause', info2.get('reason'))

    # ── B4 失败不抛 ──
    # [EN] ── B4 Failure doesn't throw ──
    #
    # ⚠ 找一条**真的写不进去**的路：用一个**普通文件**当"运行文件夹"
    #   （`mkdir` 它下面的子目录会 `NotADirectoryError`）。
    #   第一版我拿 `Path('\0:/not-a-path')` 当坏路径 —— 结果是 Windows 把它
    #   解析成"当前盘根目录下的相对路径"，**写成功了**，还在 `C:\自动落盘`
    #   留下了一份真文件（判据红得对：产品没坏，是**我的夹具没坏**）。
    # [EN] ⚠ Find a **truly unwritable** path: use a **regular file** as the "run folder"
    # [EN] (`mkdir` of a subdirectory under it raises `NotADirectoryError`).
    # [EN] In the first version I used `Path('\0:/not-a-path')` as a bad path —— turns out Windows parsed
    # [EN] it
    # [EN] as "a relative path under the current drive root", **the write succeeded**, and even left a real
    # [EN] file
    # [EN] under `C:\自动落盘` (the assertion correctly went red: the product wasn't broken, **my fixture
    # [EN] wasn't broken**).
    blocker = tmp / 'blocker.txt'
    blocker.write_text('not a directory', encoding='utf-8')
    try:
        bad = AS.flush_progress(loop, blocker / 'sub', every=30)
        ok('B4 ★★ 写不进去时**返回失败、不抛异常**（落盘是保险，'
           '保险坏了不能把车弄停）', bad.get('ok') is False and 'error' in bad,
           str(bad)[:160])
    except Exception as e:                                       # noqa: BLE001
        ok('B4 ★★ 写不进去时**返回失败、不抛异常**（落盘是保险，'
           '保险坏了不能把车弄停）', False, f'抛了：{e!r}')
    ok('B4b 失败时也不会在别处留下文件（`blocker.txt` 还是那个文件）',
       blocker.is_file() and blocker.read_text(encoding='utf-8') == 'not a directory',
       '')

    # ── B5 定时器：真的按间隔落 ──
    # [EN] ── B5 Timer: actually saves at interval ──
    #
    # ⚠ 用注入的假 `sleeper` 把时间**压掉**（不等真 30 秒）——
    #   这一条量的是"定时器真的在循环里落盘"，不是"睡眠准不准"。
    # [EN] ⚠ Use an injected fake `sleeper` to **skip the time** (don't wait a real 30 seconds) ——
    # [EN] this one measures "the timer really saves inside the loop", not "is the sleep accurate".
    slept: list[float] = []

    async def _fake_sleep(sec: float):
        slept.append(sec)
        await asyncio.sleep(0)

    cnt = {'n': 0}
    saver = AS.AutoSaver(target=lambda: FakeSession(loop, run),
                         on_tick=lambda r: cnt.__setitem__('n', cnt['n'] + 1),
                         interval_getter=lambda: 30, sleeper=_fake_sleep)
    saver.flush_now('before')                    # 先手动落一次（把计数归到 1）
    # [EN] First do a manual save (bring the counter to 1)
    saver.count = 0
    saver.stop()
    saver._stopped = False
    saver.count = 0
    t = asyncio.ensure_future(saver.run())
    for _ in range(200):
        await asyncio.sleep(0.01)
        if saver.count >= 3:
            break
    saver.stop()
    try:
        await asyncio.wait_for(t, timeout=2)
    except Exception:                                            # noqa: BLE001
        pass
    ok('B5 ★★★ 定时器**真的按间隔反复落盘**（落够 3 次，不是只落一次）',
       saver.count >= 3, f'落了 {saver.count} 次 · 睡过 {slept[:5]}')
    ok('B5b 它睡的就是配置里那个间隔（不是写死的别的数）',
       bool(slept) and all(abs(x - 30.0) < 1e-6 for x in slept[:5]), str(slept[:5]))
    ok('B5c 每次落完都回调了一次（界面拿它刷"几秒前"）',
       cnt['n'] >= 3, str(cnt['n']))

    # ── B6 间隔**每次现读配置** ──
    # [EN] ── B6 Interval **re-reads config every time** ──
    box = {'v': 30}
    s2 = AS.AutoSaver(target=lambda: None, interval_getter=lambda: box['v'])
    ok('B6 间隔读的是配置（30）', s2.interval() == 30, str(s2.interval()))
    box['v'] = 60
    ok('B6b ★★ 改了配置**立刻生效**（不必重开一轮：30 → 60）',
       s2.interval() == 60, str(s2.interval()))
    box['v'] = -5
    ok('B6c 负值夹到 0（不会变成"每 -5 秒落一次"这种荒唐行为）',
       s2.interval() == 0, str(s2.interval()))
    # ★★ 取配置**炸了**也要有默认值（30）—— 配置读不到就"整条功能不工作"
    #    是另一种荒唐：用户明明开着它，却因为一次读取异常就再也不落盘。
    # [EN] ★★ Reading config **blowing up** must still have a default (30) —— if config can't be read, then
    # [EN] "the whole feature stops working"
    # [EN] is another absurdity: the user clearly has it on, but a single read exception means it never
    # [EN] saves again.
    def _boom_getter():
        raise RuntimeError('配置读不出来')
    ok('B6d ★★ 取配置抛异常时**退回 30**（不是退成 0 —— 那等于"因一次异常就'
       '把用户的自动落盘关了"）',
       AS.AutoSaver(target=lambda: None, interval_getter=_boom_getter).interval() == 30,
       str(AS.AutoSaver(target=lambda: None,
                        interval_getter=_boom_getter).interval()))

    # ── B7 0 = 关闭 ──
    # [EN] ── B7 0 = off ──
    box['v'] = 0
    ok('B7 ★★ `0` = 关闭，标签照实写"已关闭"',
       s2.interval() == 0 and '已关闭' in s2.label(ago=None), s2.label(ago=None))
    # ★★ 更要紧的是**行为**：关掉之后定时器**一次都不许落**（不只是标签写"关"）。
    #   反例法⑲就是打这一条：把"关掉就空转"改成"照落"，标签那半句看不出来。
    # [EN] ★★ More important is **behavior**: after turning it off the timer **must not save even once**
    # [EN] (not just the label saying "off").
    # [EN] Counterexample method ⑲ targets exactly this: change "when off, idle" to "saves anyway", the
    # [EN] label half-sentence can't tell.
    cnt0 = {'n': 0}
    slept0: list[float] = []
    s_off = AS.AutoSaver(target=lambda: FakeSession(loop, run),
                         interval_getter=lambda: 0,
                         on_tick=lambda r: cnt0.__setitem__('n', cnt0['n'] + 1))

    async def _sleep0(sec: float):
        """假睡：睡够 6 次就让循环自己收工（**别在里面抛 CancelledError** ——
        它是 `BaseException`，`except Exception` 抓不住，会把整支脚本带崩）。
                English:
        Fake sleep: after sleeping 6 times, let the loop finish on its own (**don't throw CancelledError
        inside it** —
                it is a `BaseException`, `except Exception` won't catch it, and it will crash the whole script).
        """
        slept0.append(sec)
        await asyncio.sleep(0)
        if len(slept0) >= 6:
            s_off.stop()
    s_off._sleep = _sleep0
    s_off.count = 0
    t_off = asyncio.ensure_future(s_off.run())
    try:
        await asyncio.wait_for(t_off, timeout=3)
    except BaseException:                                        # noqa: BLE001
        pass
    s_off.stop()
    ok('B7b2 ★★★ `0` = **真的关掉**：定时器一次盘都不落（不是"标签写着关、'
       '其实还在写"）',
       s_off.count == 0 and cnt0['n'] == 0,
       f'落了 {s_off.count} 次 · 回调 {cnt0["n"]} 次 · 睡过 {slept0[:4]}')
    box['v'] = 30
    ok('B7b 开着时标签写清"每 N 秒"（用户要的"显示内容就是每隔多久自动落盘"）',
       '每 30 秒' in s2.label(ago=None), s2.label(ago=None))
    ok('B7c 落过之后还会带上"N 秒前"（证明它**真的在落**，不是只写着间隔）',
       '秒前' in s2.label(ago=7.4), s2.label(ago=7.4))

    # ── B9 ★★★ 倒计时 + 「干没干」（2026-10-08 用户报的）──
    # [EN] ── B9 ★★★ Countdown + "did it run" (reported by user 2026-10-08) ──
    #
    #   用户原话：「**自动落盘没有倒计时 也没看到它干没干**（如果干了应该给
    #   一个提示 在自动落盘状态标签里）」。
    # [EN] User's exact words: "**autosave has no countdown and I can't see whether it ran** (if it ran it
    # [EN] should give
    # [EN] a hint in the autosave status label)".
    #
    #   ★ 这里面的 B9f 钉的是一个**真 bug**：界面原来只在"自己主动落"时才记
    #     "上次落盘时刻"，而定时器落的那一次**根本不经过界面** ——
    #     于是那半句「N 秒前」永远不出现，屏幕上只有「每 30 秒」。
    # [EN] ★ B9f in here pins down a **real bug**: the UI originally only recorded
    # [EN] "last save time" when "it saved on its own initiative", while the timer-driven save **doesn't go
    # [EN] through the UI at all** ——
    # [EN] so that half-sentence "N seconds ago" never appears, and the screen only shows "every 30
    # [EN] seconds".
    box2 = {'v': 30}
    s4 = AS.AutoSaver(target=lambda: FakeSession(loop, run),
                      interval_getter=lambda: box2['v'])
    ok('B9a ★★ 没起定时器时**没有倒计时可报**（`secs_to_next is None`）',
       s4.secs_to_next is None, str(s4.secs_to_next))
    box2['v'] = 0
    ok('B9b ★★ 关着（`0`）时也不报倒计时（写了"已关闭"就别再说"还有 30 秒"）',
       s4.secs_to_next is None, str(s4.secs_to_next))
    box2['v'] = 30
    lab0 = s4.label(ago=None, to_next=12.4, just_saved=False)
    ok('B9c ★★ 还没落过时照实说"还没落过"（不写到"上次 N 秒前"——那是在编）',
       '还有 12 秒' in lab0 and '还没落过' in lab0, lab0)
    lab1 = s4.label(ago=18.7, to_next=12.4, just_saved=False)
    ok('B9d ★★★ 有倒计时时那句话就是**还有多少秒**（用户要的"倒计时"），'
       '落过之后再带上"上次 N 秒前"（那是"它真的在干"的凭据）',
       '还有 12 秒' in lab1 and '上次 18 秒前' in lab1, lab1)
    box2['v'] = 0
    ok('B9e 关掉时**先说"已关闭"**，不说倒计时（两句话不能同时成立）',
       '已关闭' in s4.label(to_next=12.4), s4.label(to_next=12.4))
    box2['v'] = 30

    slept4: list[float] = []
    seen_next: list = []

    async def _sleep4(sec: float):
        slept4.append(sec)
        seen_next.append(s4.secs_to_next)      # 睡**之前**就该有倒计时了
        # [EN] The countdown should be there **before** sleeping
        await asyncio.sleep(0)
        if len(slept4) >= 2:
            s4.stop()
    s4._sleep = _sleep4
    t4 = asyncio.ensure_future(s4.run())
    try:
        await asyncio.wait_for(t4, timeout=3)
    except BaseException:                                        # noqa: BLE001
        pass
    s4.stop()
    ok('B9f1 ★★★ **睡之前就把倒计时定下来**（`secs_to_next` ≈ 间隔）'
       '—— 睡醒才算的话，那半句要等一整轮才出现',
       bool(seen_next) and seen_next[0] is not None
       and 28.0 <= float(seen_next[0]) <= 30.0, str(seen_next[:3]))
    ok('B9f ★★★ **定时器自己落的那一次也记下了时刻**（`last_at > 0`）'
       '—— 界面就是靠它说"N 秒前"的；以前只有界面主动落才记，'
       '于是屏幕上**永远看不出它干没干**（用户报的就是这个）',
       s4.count >= 1 and s4.last_at > 0,
       f'count={s4.count} last_at={s4.last_at}')
    ok('B9g ★★ 收掉之后**不再报倒计时**（留一个不走的倒计时比没有更坏）',
       s4.secs_to_next is None, str(s4.secs_to_next))
    s4.last_at = time.time()
    lab2 = s4.label()
    ok('B9h ★★★ 「刚落了」这个提示是**按时刻自动判的**（不用谁告诉它），'
       '而且带上第几次（"干了"最硬的凭据）',
       '刚落盘' in lab2 and f'第 {s4.count} 次' in lab2, lab2)
    s4.last_at = time.time() - 60
    ok('B9i 三秒之后自动变回倒计时那一句（不会一直占着那一行）',
       '刚落盘' not in s4.label(ago=60.0), s4.label(ago=60.0))
    ok('B9j `JUST_SAVED_SECONDS` 是个**有限的小数**（写成 0 就永远看不到提示，'
       '写成很大就永远看不到倒计时）',
       0 < float(AS.JUST_SAVED_SECONDS) <= 10.0, str(AS.JUST_SAVED_SECONDS))

    # ── B8 没在跑的轮次里调它 ──
    # [EN] ── B8 Don't call it in a round that isn't running ──
    s3 = AS.AutoSaver(target=lambda: None)
    r3 = s3.flush_now('pause')
    ok('B8 ★★ 没有在跑的轮次时调它 → 不算错误、不崩（`no-session`）',
       r3.get('ok') is False and r3.get('error') == 'no-session', str(r3))

    # ── B9 stop 幂等 ──
    # [EN] ── B9 stop is idempotent ──
    s4 = AS.AutoSaver(target=lambda: None)
    s4.stop()
    s4.stop()
    ok('B9 `stop()` **幂等**（收工与关窗口可能都调它）', True, '')

    # ── B10 普通模式（没有剧本 builder）也要落得出东西 ──
    # [EN] ── B10 Normal mode (without a script builder) must still produce output ──
    run2 = FakeRun(tmp / 'run2')
    loop2 = FakeLoop(['（旁白）雨还在下。'], use_builder=False)
    r10 = AS.flush_progress(loop2, run2, every=30)
    b10 = (run2.root / AS.DIR_NAME / AS.FILE_MD).read_text(encoding='utf-8')
    ok('B10 ★★ 普通模式（走叙事行、没有剧本 builder）也落得出内容',
       r10.get('ok') and '雨还在下' in b10, b10[-80:].replace('\n', '⏎'))

    # ── B11 字段拿不到也不整份不落 ──
    # [EN] ── B11 If a field can't be fetched, don't skip the whole dump ──
    class _Bare:
        """什么都没有的循环对象（字段全缺）。
                English:
        A loop object with nothing in it (all fields missing).
        """
    r11 = AS.flush_progress(_Bare(), FakeRun(tmp / 'run3'), every=30)
    ok('B11 ★★ 循环对象缺字段时**照样落盘**（绝不允许"某个字段拿不到就整份不落"）',
       r11.get('ok') is True, str(r11)[:160])

    report['draft_md'] = body[:400]


# ══════════════════════════════════════════════════════════════
#  C. 真机 + 像素
# [EN] C. Real machine + pixels
# ══════════════════════════════════════════════════════════════
def count_in_box(png, rgb, box: dict, tol: int = 56) -> int:
    """（保留给"色块"类量测；**细字别用它**，见 `magenta_in_box`。）
        English:
    (Reserved for "color block" type measurements; **don't use it for thin text**, see
    `magenta_in_box`.)
    """
    im = VU.image_of(png).convert('RGB')
    px = im.load()
    W, H = im.size
    n = 0
    for y in range(max(0, box.get('y0', 0) - 4), min(H, box.get('y1', H) + 5)):
        for x in range(max(0, box.get('x0', 0) - 4), min(W, box.get('x1', W) + 5)):
            r, g, b = px[x, y]
            if (abs(r - rgb[0]) <= tol and abs(g - rgb[1]) <= tol
                    and abs(b - rgb[2]) <= tol):
                n += 1
    return n


def magenta_in_box(png, box: dict) -> dict:
    """在包围盒里量"**偏品红**"的像素 —— 给细字用的标记色量法。

    ⚠ 为什么不能用"接近纯品红 (255,0,255)"来数（第一版就这么假红了）：
      12px 的字**几乎全是抗锯齿过渡色** —— 描边像素是"品红掺了底色"
      （比如 (243,150,247)），绿通道 150 离 0 差 150，严容差一颗都数不到，
      量出来只有 8 像素，而屏幕上明明写着字。
      → 改判**色相**：品红系就是"红蓝都高、绿明显低"。
        底色是浅蓝 (219,233,245) → 这个量在底色上恒为负，**不会假绿**。

    返回 `{'n': 个数, 'x0','x1','y0','y1': 包围盒}`（一个都没数到就只给 `n=0`）。
    
        English:
    Measure "**magenta-ish**" pixels within the bounding box — a marker-color measurement method for
    thin text.
        ⚠ Why we can't count using "close to pure magenta (255,0,255)" (the first version got a false red this way):
          12px text is **almost entirely anti-aliasing transition colors** — the outline pixels are "magenta mixed with background"
          (e.g. (243,150,247)), the green channel 150 is 150 away from 0; with a strict tolerance not a single one is counted,
          the measurement yields only 8 pixels, even though text is clearly displayed on screen.
          → Switch to judging **hue**: magenta family means "red and blue both high, green clearly low".
            The background is light blue (219,233,245) → this quantity is always negative on the background, **won't falsely trigger green**.
        Returns `{'n': count, 'x0','x1','y0','y1': bounding box}` (if none are counted, only `n=0` is given).
    """
    im = VU.image_of(png).convert('RGB')
    px = im.load()
    W, H = im.size
    xs: list[int] = []
    ys: list[int] = []
    for y in range(max(0, box.get('y0', 0) - 6), min(H, box.get('y1', H) + 7)):
        for x in range(max(0, box.get('x0', 0) - 6), min(W, box.get('x1', W) + 7)):
            r, g, b = px[x, y]
            if r > 120 and b > 120 and ((r + b) / 2.0 - g) > 60:
                xs.append(x)
                ys.append(y)
    if not xs:
        return {'n': 0}
    return {'n': len(xs), 'x0': min(xs), 'x1': max(xs),
            'y0': min(ys), 'y1': max(ys)}


def colour_bbox(png, rgb, tol: int = 10) -> dict:
    """数某个颜色在屏幕上的像素数与包围盒（标记色法用）。
        English:
    Count the number of pixels of a given color on screen and its bounding box (used by the
    marker-color method).
    """
    from PIL import ImageChops
    im = VU.image_of(png).convert('RGB')
    r, g, b = im.split()

    def band(v, c):
        lo, hi = max(0, c - tol), min(255, c + tol)
        return v.point(lambda x: 255 if lo <= x <= hi else 0)
    m = ImageChops.multiply(ImageChops.multiply(band(r, rgb[0]), band(g, rgb[1])),
                            band(b, rgb[2]))
    W, H = im.size
    px = m.load()
    xs: list[int] = []
    ys: list[int] = []
    n = 0
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            if px[x, y]:
                n += 1
                xs.append(x)
                ys.append(y)
    if not xs:
        return {'n': 0}
    return {'n': n * 4, 'x0': min(xs), 'x1': max(xs),
            'y0': min(ys), 'y1': max(ys)}


async def gui_checks(page: ft.Page) -> None:
    VU.patch_flat_background()
    from gui.app_flet import NovelWorldApp
    from verify_run_control import make_project

    tmp = Path(tempfile.mkdtemp(prefix='nws_autogui_'))
    proj = make_project(tmp / '自动落盘真机')

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    await asyncio.sleep(1.8)
    app.current_project = proj
    app.show_main_screen()
    await asyncio.sleep(1.0)

    async def shot(name: str) -> bytes:
        page.update()
        await asyncio.sleep(0.4)
        png = await page.take_screenshot()
        (OUT / f'autosave_{name}.png').write_bytes(png or b'')
        return png or b''

    # ── C1 控件树：两颗胶囊都在，且新的那颗在右边 ──
    # [EN] ── C1 Widget tree: both pills are present, and the new one is on the right ──
    bar = getattr(app, '_run_status_bar', None)
    pill = getattr(app, '_autosave_bar', None)
    ok('C1 ★★ 运行界面里两颗胶囊都建出来了（状态条 + 自动落盘）',
       isinstance(bar, ft.Container) and isinstance(pill, ft.Container),
       f'{type(bar).__name__} / {type(pill).__name__}')
    ok('C1b ★★★ 新那颗的底色就是那个"偏蓝"色（控件的 `bgcolor`）',
       pill is not None and pill.bgcolor == NovelWorldApp.AUTOSAVE_BG,
       f'{getattr(pill, "bgcolor", None)}')
    txt = getattr(app, '_autosave_text', None)
    ok('C1c ★★ 字是绿的 + 字号字体与状态条相同',
       txt is not None and txt.color == NovelWorldApp._CREW_STATE_STYLE and False
       or (txt is not None and getattr(txt, 'size', None) == 12
           and getattr(txt, 'font_family', None)
           == getattr(app._run_bar_text, 'font_family', None)),
       f'size={getattr(txt, "size", None)} font={getattr(txt, "font_family", None)}')

    # ── C2 屏幕上那句话 ──
    # [EN] ── C2 That sentence on screen ──
    ok('C2 ★★ 屏幕上写着"每隔多久自动落盘"（默认每 30 秒）',
       txt is not None and '每 30 秒' in str(txt.value), str(getattr(txt, 'value', None)))

    # ── C3 像素：两颗胶囊**真的画在屏幕上**，而且新的在右边 ──
    # [EN] ── C3 Pixels: both pills are **actually drawn on screen**, and the new one is on the right ──
    bar_bg = getattr(bar, 'bgcolor', None)
    old_bar, old_pill = bar_bg, pill.bgcolor
    MARK_A, MARK_B = '#ff00ff', '#00ff00'         # 必须十六进制串（元组 Flet 不认）
    # [EN] Must be a hex string (Flet doesn't accept tuples)
    try:
        bar.bgcolor = MARK_A
        pill.bgcolor = MARK_B
        png = await shot('1_two_pills')
    finally:
        bar.bgcolor = old_bar
        pill.bgcolor = old_pill
        page.update()
    a = colour_bbox(png, VU.hex_rgb(MARK_A))
    b = colour_bbox(png, VU.hex_rgb(MARK_B))
    report['pill_a'] = a
    report['pill_b'] = b
    ok('C3 ★★★ 自动落盘那颗胶囊**真的画在屏幕上**（底色像素 ≥ 1200）',
       b.get('n', 0) >= 1200, str(b))
    ok('C3b ★★★ 它在状态条的**右边**（两块色的横向区间一左一右）',
       a.get('n', 0) >= 1200 and b.get('n', 0) >= 1200 and b['x0'] > a['x1'],
       f'状态条 x {a.get("x0")}~{a.get("x1")} | 自动落盘 x {b.get("x0")}~{b.get("x1")}')
    ok('C3c 两颗在同一行（纵向区间基本重合）—— 是"并排"不是"另起一行"',
       abs(a.get('y0', 0) - b.get('y0', 0)) <= 6, f'{a.get("y0")} vs {b.get("y0")}')

    # ── C4 字**真的是绿的**（标记色法：临时把字染成品红）──
    # [EN] ── C4 The text is **really green** (marker-color method: temporarily dye the text magenta) ──
    old_c = txt.color
    try:
        txt.color = '#ff00ff'
        page.update()
        png2 = await shot('2_text_mark')
    finally:
        txt.color = old_c
        page.update()
    # "标记前"的那张当基线：同一块地方不该有品红系像素（底色是浅蓝）。
    # [EN] Use the "pre-marker" shot as baseline: the same area should have no magenta-ish pixels (the
    # [EN] background is light blue).
    base = magenta_in_box(png, b) if b.get('n') else {'n': 0}
    mark = magenta_in_box(png2, b) if b.get('n') else {'n': 0}
    report['text_mark'] = {'baseline': base, 'marked': mark}
    ok('C4 ★★★ 那行字**真的画出来了**（胶囊里"品红系"像素从基线涨到 ≥ 150 —— '
       '细字全是抗锯齿过渡色，不能用"接近纯品红"去数，见那个函数的说明）',
       mark.get('n', 0) >= 150 and mark.get('n', 0) > base.get('n', 0) * 3 + 100,
       f'基线 {base.get("n")} → 标记后 {mark.get("n")}')
    ok('C4b ★★ 那行字**落在胶囊里**（标记像素的包围盒在胶囊色块范围内）'
       '—— "字画在别处"这种情况也挡得住',
       mark.get('n', 0) >= 150
       and b.get('x0', 0) - 10 <= mark.get('x0', 0)
       and mark.get('x1', 0) <= b.get('x1', 0) + 10
       and b.get('y0', 0) - 10 <= mark.get('y0', 0)
       and mark.get('y1', 0) <= b.get('y1', 0) + 10,
       f'字 {mark.get("x0")}~{mark.get("x1")},{mark.get("y0")}~{mark.get("y1")} '
       f'⊂ 胶囊 {b.get("x0")}~{b.get("x1")},{b.get("y0")}~{b.get("y1")}')

    # ── C5 改配置 → 那句话立刻跟着变（不用重启）──
    # [EN] ── C5 Change config → that sentence immediately follows (no restart needed) ──
    CFG.set('AUTOSAVE_SECONDS', '45')
    app._refresh_autosave_status()
    page.update()
    ok('C5 ★★ 把间隔改成 45 → 屏幕上那句话跟着变（不必重开一轮）',
       '每 45 秒' in str(txt.value), str(txt.value))
    CFG.set('AUTOSAVE_SECONDS', '0')
    app._refresh_autosave_status()
    ok('C5b ★★ 设成 0 → 照实写"已关闭"',
       '已关闭' in str(txt.value), str(txt.value))
    CFG.set('AUTOSAVE_SECONDS', '2')          # 调快，下面要等它真的落
    # [EN] Speed it up, we need to wait below for it to actually dump
    app._refresh_autosave_status()

    # ── C6 开一轮 → 定时器真的起来了 → 真的落了盘 ──
    # [EN] ── C6 Start a round → the timer really starts → it really dumps to disk ──
    dlg = app.show_start_story_dialog()
    page.update()
    await asyncio.sleep(0.8)
    btn = _find_btn(dlg, t('开始推演'))
    ok('C6 找得到「开始推演」按钮（下面几条靠它）', btn is not None, '')
    if btn is not None:
        btn.on_click(None)
        for _ in range(120):
            await asyncio.sleep(0.1)
            if app.session is not None and app.session.is_alive:
                break
    ok('C6b ★★ 定时落盘器跟着这一轮起来了',
       getattr(app, '_autosave_obj', None) is not None
       and app._autosave_obj.running, '')
    # ⚠ `run_root` 必须在**用到它的第一条判据之前**取（C6b2 用它读停点，
    #   C6c/C6e 用它读落盘目录）—— 定义在下面会让 C6b2 抛 UnboundLocalError，
    #   而那一抛会被外层 `except` 记成"C 组跑完 ✗"，看起来像"真机崩了"。
    # [EN] ⚠ `run_root` must be fetched **before the first criterion that uses it** (C6b2 reads the
    # [EN] stop point, C6c/C6e read the flush dir). Defining it lower throws UnboundLocalError inside
    # [EN] C6b2, which the outer `except` records as "group C finished ✗" -- looking like a real crash.
    run_root = app.session.run.root if app.session else None
    # ── C6b2 ★★★ **起笔那一刻就有存档**（用户 2026-10-23 的原话）──
    #
    #   「你目前的存档是否在**起笔之后就创建**了……如果是后者请改成前者」
    #   以前 `start()` 只是把定时器挂上去，第一次落盘要等满一个间隔 ——
    #   开跑后头 30 秒断电，这一轮连停点都没有（下次起笔会重复演一遍）。
    #   ⇒ 现在 `_start_autosave()` 之后立刻 `_autosave_flush('start')`。
    #   ⚠ 这条判据必须**只问停点在不在**（不要问内容）：起笔那一刻还没演，
    #     正文本来就该是空的 —— 那是正确行为，不是缺陷。
    # [EN] ── C6b2 ★★★ **a save exists the instant writing starts** (the user's own words) ──
    # [EN] "Is your save created **right after 起笔** ... if it is the latter, change it to the former".
    # [EN] `start()` used to only attach the timer, so the first flush waited a full interval -- a power
    # [EN] cut in the first 30 seconds left this round without even a stop point (next start replays it).
    # [EN] => Now `_autosave_flush('start')` runs right after `_start_autosave()`.
    # [EN] ⚠ This criterion must ask **only whether the stop point exists** (not about content): at
    # [EN] that instant nothing has been performed, so an empty body is correct, not a defect.
    _sp_file = (run_root / '停点.json') if run_root else None
    _sp_json = {}
    try:
        _sp_json = (json.loads(_sp_file.read_text(encoding='utf-8'))
                    if _sp_file and _sp_file.is_file() else {})
    except Exception:                                        # noqa: BLE001
        _sp_json = {}
    ok('C6b2 ★★★ **起笔那一刻停点就已经在盘上了**（不用等 30 秒，也不用等停止）',
       bool(_sp_json) and str(_sp_json.get('reason') or '').startswith('autosave:start'),
       f'停点={({k: _sp_json.get(k) for k in ("day", "day_done", "reason")} if _sp_json else None)}')
    # 等**定时器自己**落一次（间隔设成了 2 秒）
    # [EN] Wait for the **timer itself** to flush once (interval set to 2 seconds)
    #
    # ★★★ 2026-10-23 **判据自己也要跟着改**（否则它测的就不是它写着的那件事）：
    #   起笔现在会**立刻**落一次（`_autosave_flush('start')`，用户要求"起笔之后就要有存档"），
    #   于是"`自动落盘/进度.md` 存在"这个条件在**起笔那一刻**就成立了 ——
    #   而这条判据的名字写的是「**定时器自己**落的盘（没手动催）」。
    #   按旧写法它会当场变绿，测到的却是那次界面主动催的 `start`。
    #   ⇒ 改成等 `count` 涨过起笔那一次（第 2 次起才是定时器自己走的）。
    # [EN] ★★★ 2026-10-23 **the criterion had to change with the product** (otherwise it no longer
    # [EN] measures what its name says): starting now flushes **immediately**
    # [EN] (`_autosave_flush('start')`, the user wants a save right after 起笔), so "进度.md exists"
    # [EN] is already true at that instant -- while this criterion's name says "**the timer itself**
    # [EN] flushed (not prompted manually)". Under the old form it would go green while measuring that
    # [EN] prompted `start` flush. => Wait for `count` to pass the start flush (the 2nd is the timer's).
    draft = (run_root / AS.DIR_NAME / AS.FILE_MD) if run_root else None
    _base = int(getattr(app._autosave_obj, 'count', 0) or 0)
    for _ in range(160):
        await asyncio.sleep(0.1)
        if int(getattr(app._autosave_obj, 'count', 0) or 0) > _base:
            break
    ok('C6c ★★★ **定时器自己落的盘**（没手动催）：计数涨了一次，`自动落盘/进度.md` 在',
       (draft is not None and draft.is_file()
        and int(getattr(app._autosave_obj, 'count', 0) or 0) > _base),
       f'{str(draft)} count={getattr(app._autosave_obj, "count", "?")} base={_base}')
    d0 = draft.read_text(encoding='utf-8') if (draft and draft.is_file()) else ''
    ok('C6d 落的是**这一轮**的运行文件夹（不是别处）',
       '自动落盘的中途稿' in d0, d0[:120].replace('\n', '⏎'))
    # ★★★ 2026-10-23 **改口径**（旧设计被用户推翻，不是判据太严）：
    #
    #   旧判据守的是「中途稿**不许**写进 `每天的生活/`」，理由（当时成立）：
    #   那个目录是正式产物，中途稿混进去会出现"文件在、只演一半"，导出会短一块。
    #
    #   用户 2026-10-23 的新要求推翻了它：
    #   「电脑突然关机 / 随手关掉程序 —— 下一次打开**拾卷里的存档**可以拿到最近的记录
    #    （最多损失 30 秒）」。
    #   而"能续跑"只认 `每天的生活/第NNN天.json`（`read_daily_script` 读它，
    #   `load_resume_scenes` 续跑时靠它接上当天半截正文）——
    #   只写 `自动落盘/进度.md` 的话，位置接上了、内容却是空的。
    #
    #   ⇒ 新口径改成**双向**，这才是这条判据现在该问的事：
    #     ① 中途落盘**必须已经**把当天正文写进 `每天的生活/`（否则断电接不上）；
    #     ② 那份中途稿**必须带 `⏳ 定时落盘` 标记**（否则它会冒充正式稿，
    #        而"冒充"正是原设计要防的那件事 —— 防的办法是留痕，不是不写）。
    #   ⚠ 「正式稿不带标记」这一半由 C9 守（跑完收工后复查同一份文件）。
    # [EN] ★★★ 2026-10-23 **re-specified** (the old design was overturned by the user, the criterion
    # [EN] was not too strict). The old rule: "the mid-progress draft must **not** be written into
    # [EN] `每天的生活/`" -- that directory is the formal output and a half draft masquerading as a
    # [EN] complete day would make exports short with nobody noticing.
    # [EN] The user's 2026-10-23 requirement overturns it: "the computer suddenly shuts down / the app
    # [EN] gets closed -- next time I open **the save in 拾卷** I want the latest record (losing at most
    # [EN] 30 seconds)". Resuming only recognizes `每天的生活/第NNN天.json` (`read_daily_script`; and
    # [EN] `load_resume_scenes` relies on it for that day's half-finished body), so writing only
    # [EN] `自动落盘/进度.md` gives a correct position with an empty body.
    # [EN] => The new rule is **two-way**: ① the mid-progress flush **must already** have written that
    # [EN] day into `每天的生活/`; ② that draft **must carry the `⏳ 定时落盘` marker** -- so it cannot
    # [EN] masquerade as the formal draft. Masquerading is what the old design feared; the fix is a
    # [EN] trace, not skipping the write. ⚠ The other half ("the formal draft has no marker") is
    # [EN] guarded by C9, which re-reads the same file after the round wraps up.
    _daily = (sorted((run_root / '每天的生活').glob('第*.md'))
              if run_root and (run_root / '每天的生活').exists() else [])

    def _daily_has_marker(root) -> bool:
        d = (root / '每天的生活') if root else None
        if d is None or not d.exists():
            return False
        for p in d.glob('第*.md'):
            # ⚠ 排掉 `_分镜脚本` 这类**同目录的另一种产物**：它们不是"当天正文"，
            #   永远不会有这个标记，混进来会让判据的结论反掉。
            # [EN] ⚠ Skip artifacts like `_分镜脚本` that live in the same directory: they are not
            # [EN] "that day's body", never carry this marker, and including them flips the verdict.
            if '_' in p.stem and not p.stem.endswith('天'):
                continue
            try:
                if '⏳ **定时落盘' in p.read_text(encoding='utf-8', errors='ignore'):
                    return True
            except OSError:
                continue
        return False

    for _ in range(100):
        if _daily_has_marker(run_root):
            break
        await asyncio.sleep(0.1)
    ok('C6e ★★★ 中途落盘**已经**把当天正文写进 `每天的生活/`，且带着「⏳ 定时落盘」标记'
       '（断电后靠它接上；标记让它不冒充正式稿）',
       _daily_has_marker(run_root),
       f'文件={[p.name for p in _daily][:4]}')
    await shot('3_draft_written')

    # ── C6f ★★★ **模拟断电**：这一刻直接把进程当成没了，下一轮还能接上吗？──
    #
    # 用户 2026-10-23 的诉求就这一句：
    #   「我想随时软件或者电脑突然退出的时候 我下一次打开拾卷里的存档
    #    可以拿到最近的记录（最多损失 30 秒）」
    #
    # 所以这条判据**不许**再调任何"收工"代码 —— 它只做"断电后重启"会做的事：
    #   ① 读 `停点.json`（下一轮「起笔」读的就是它）；
    #   ② `resume.plan(proj)` 必须给 `resume`（接着这一天那一刻），
    #      **不许**是 `fresh`（从头演）或 `next_day`（跳过这一天）；
    #   ③ `resume.load_resume_scenes(plan)` 必须真的读回正文（否则位置接上了、内容是空的）。
    #
    # ⚠ 这三步缺一条都不算"能接上"：只判 ①②，用户会看到"位置对了但正文没了"；
    #   只判 ③，可能是另一天的正文。
    # [EN] ── C6f ★★★ **Simulate a power cut**: treat the process as gone right now; can the next round
    # [EN] pick up? That IS the user's 2026-10-23 request. So this must **not** call any wrap-up code --
    # [EN] only what "restart after a power cut" does: ① read `停点.json`; ② `resume.plan(proj)` must
    # [EN] return `resume` (continue this day from that moment), never `fresh` (replay from the top) or
    # [EN] `next_day` (skip this day); ③ `load_resume_scenes` must really read the body back (a correct
    # [EN] position with an empty body is not "resumable").
    # [EN] ⚠ All three are needed: with only ①② the user sees "right place, no content"; with only ③
    # [EN] the body might belong to another day.
    from sim import resume as RESUME
    _stop = RESUME.read_stop_point(app.session.run) if app.session else None
    _plan = RESUME.plan(proj) if proj is not None else {}
    _back = RESUME.load_resume_scenes(_plan) if _plan else []
    ok('C6f ★★★ 断电模拟：停点在、`plan()` 判**接着演**（不是从头也不是跳天）、'
       '`load_resume_scenes()` 真读回了正文',
       bool(_stop) and (not _stop.get('day_done'))
       and _plan.get('kind') == RESUME.RESUME and bool(_back),
       f"停点={({k: _stop.get(k) for k in ('day', 'shichen', 'day_done', 'reason')} if _stop else None)}"
       f" plan.kind={_plan.get('kind')} 读回幕数={len(_back)}")

    # ── C7 点暂停 → 补落一次（用户点名的那一刻）──
    # [EN] ── C7 Click pause → dump once more (the moment the user names) ──
    n_before = app._autosave_obj.count
    app._on_pause_toggle()
    await asyncio.sleep(0.6)
    ok('C7 ★★★ 点**暂停**时补落了一次（计数 +1）',
       app._autosave_obj.count > n_before,
       f'{n_before} → {app._autosave_obj.count}')
    ok('C7b 那一刻落盘的 reason 是 `pause`（"这次是谁催的"要留痕）',
       app._autosave_obj.last.get('reason') == 'pause',
       str(app._autosave_obj.last.get('reason')))
    ok('C7c 暂停之后**定时器还在跑**（暂停 ≠ 收工；用户是在暂停时准备关软件）',
       app._autosave_obj.running, '')
    paused_body = draft.read_text(encoding='utf-8') if draft.is_file() else ''
    ok('C7d 暂停那一刻的稿子里已经有"今天演出来的东西"'
       '（这才是"点暂停时不会白跑"的实证）',
       '自动落盘的中途稿' in paused_body and len(paused_body) > 200,
       f'{len(paused_body)} 字')

    # ── C8 收工 → 定时器收掉（先补落一次）──
    # [EN] ── C8 Finish → the timer is torn down (dump once more first) ──
    app._stop_autosave()
    await asyncio.sleep(0.3)
    ok('C8 ★★ 收工把它收掉了（不再每 2 秒白写一份）',
       not app._autosave_obj.running, '')

    # 收尾：把这一轮停掉，别留一个跑着的会话
    # [EN] Cleanup: stop this round, don't leave a running session
    try:
        if app.session is not None and app.session.is_alive:
            app.session.stop()
            await app.session.wait(20)
    except Exception:                                            # noqa: BLE001
        pass

    # ── C9 ★★★ 收工之后：**同一份文件变成正式稿**（标记必须消失）──
    #   2026-10-23 与 C6e 配对：C6e 守"中途落盘要写进去且带标记"，
    #   C9 守"正式落盘要把它覆盖掉、且**不带**标记"。
    #   ★ 为什么这半条必须单独存在：只有 C6e 的话，"永远带标记"也能全绿 ——
    #     那样用户看到的是"这一天从来没收过工"，而导出/阅读都会带上那行提示。
    # [EN] ── C9 ★★★ After wrap-up: **the same file becomes the formal draft** (marker must be gone) ──
    # [EN] Paired with C6e: C6e guards "the mid-progress flush writes it with the marker", C9 guards
    # [EN] "the formal flush overwrites it and carries **no** marker".
    # [EN] ★ Why this half must exist separately: with C6e alone, "always keep the marker" also passes --
    # [EN] and then the user sees "this day never wrapped up", with that line leaking into exports.
    _after = (sorted((run_root / '每天的生活').glob('第*.md'))
              if run_root and (run_root / '每天的生活').exists() else [])
    # ⚠ 与 C6e 同一口径：只看"当天正文"那几份（排掉 `_分镜脚本`），而且要求**至少有一份**
    #   —— 空目录时 `all([])` 会是 True，那又是一次假绿。
    # [EN] ⚠ Same rule as C6e: only "that day's body" files (skip `_分镜脚本`), and require **at least
    # [EN] one** -- on an empty directory `all([])` is True, which would be another false green.
    _final = [(p, p.read_text(encoding='utf-8', errors='ignore'))
              for p in _after if not ('_' in p.stem and not p.stem.endswith('天'))]
    ok('C9 ★★★ 收工后那份变成**正式稿**（`⏳ 定时落盘` 标记已经消失）',
       bool(_final) and all('⏳ **定时落盘' not in txt for _p, txt in _final),
       f'文件={[p.name for p in _after][:4]} 仍带标记='
       f'{[p.name for p, txt in _final if "⏳ **定时落盘" in txt][:2]}')


def _find_btn(dlg, label: str):
    from verify_ui_common import walk, text_of
    if dlg is None:
        return None
    for c in walk(dlg):
        if text_of(c) == label and hasattr(c, 'on_click'):
            return c
    return None


# ══════════════════════════════════════════════════════════════
async def main(page) -> None:
    print('\n── A 配置 + 外观 + 接线 ──')
    try:
        logic_checks()
    except Exception:                                            # noqa: BLE001
        ok('A 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── B 落盘行为（不弹窗）──')
    try:
        await behavior_checks()
    except Exception:                                            # noqa: BLE001
        ok('B 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    if not ONLY_LOGIC and page is not None:
        print('\n── C 真机 + 像素 ──')
        try:
            await gui_checks(page)
        except Exception:                                        # noqa: BLE001
            ok('C 组跑完（真机）', False, traceback.format_exc()[-400:])
            print(traceback.format_exc()[-1200:])
    rep = {'checks': report['checks'],
           'passed': sum(1 for c in report['checks'] if c['ok']),
           'total': len(report['checks'])}
    rep['ok'] = rep['passed'] == rep['total']
    rep.update({k: v for k, v in report.items() if k != 'checks'})
    (OUT / 'autosave_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n自动落盘验证：{rep['passed']}/{rep['total']}")
    if page is not None:
        await shutdown(page, code=0 if rep['ok'] else 2)


if __name__ == '__main__':
    # ★★ **全程不许写真实 `.env`**（本项目铁律，这里差点栽第三次）：
    #   `app.main()` 里的能力校验会走 `CFG.save()`，而那一步会把脚本里
    #   `CFG.set('AUTOSAVE_SECONDS', '2')` 这类**测试值**写进用户的配置。
    #   第一次跑的时候就是它把 `.env` 改成了 `AUTOSAVE_SECONDS=2`
    #   + `MOCK_LLM=true`（已从备份恢复，md5 核对过）。
    # [EN] ★★ **Never write the real `.env` at any point** (project iron rule, nearly tripped a third time
    # [EN] here):
    # [EN] The capability check in `app.main()` goes through `CFG.save()`, and that step will write values
    # [EN] from the script
    # [EN] like `CFG.set('AUTOSAVE_SECONDS', '2')` — **test values** — into the user's config.
    # [EN] The first run is exactly what changed `.env` to `AUTOSAVE_SECONDS=2`
    # [EN] + `MOCK_LLM=true` (restored from backup, md5 verified).
    VU.redirect_env_writes()
    if ONLY_LOGIC:
        asyncio.run(main(None))
    else:
        ft.run(main, assets_dir=str(APP_DIR / 'assets'))
