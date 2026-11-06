# -*- coding: utf-8 -*-
"""真机验证：运行页面板搬家 + 点标题跳设置（2026-10-11 用户点名）。

用户四句话：
  ① 运行页面**右侧下面的「系统」Panel 移动到左侧「风格控制」下面**；
  ② **小地图移动到「运行配置」的上面**；
  ③ 「运行配置」「风格控制」点了标题（**用下划线表示可以点击**）进入对应配置
     位置（**项目设置的**）**且配置之后马上起效**；
  ④ 右侧「剧组」点剧组（也可以点击）进入项目的 Agent 列表，
     **点击某一个 Agent 则直接进入项目的 Agent 设置**。
  规则（用户拍板"在跑→书斋，没跑→天问"）：
     · 推演**正在跑** → 书斋（项目设置）对应页；
     · 推演**还没启动** → 天问（全局设置）对应页。

判据分两组：
  **A 组（纯逻辑，不起窗口）**
    A1 ★ 六个页签下标常量与两个对话框里 `tab_defs` 的**真实标题**一一对上
        （硬编码数字与真实顺序脱钩 ⇒ 点标题会静默落到隔壁那一页，所以必须反查）
    A2 ★★ `_settings_target` 按"在跑 / 没在跑"给出书斋 / 天问两个不同目标
    A3 ★★ 可点标题：下划线 + `↗` + 手型光标 + 悬停说明齐备，且抓手 `_panel_goto` 在
    A4 ★★ 书斋那三块（运行边界 / 风格控制 / 导演）**真的写 CFG**：源码里
        每个键都有 `CFG.set` 的落点（不是"看着像接上了"）
  **B 组（真启窗口）**
    B1 ★★ 左栏顺序 = 时间 / **小地图** / **运行配置** / 风格控制 / **系统**；
        右栏 = 在场人物 / 剧情 / 剧组（系统已不在右栏）
    B2 ★★ 点「运行配置」标题（没在跑）⇒ 去 **天问 · 运行**（tab=TAB_GLOBAL_RUN）
    B3 ★★ 点「风格控制」标题（没在跑）⇒ 去 **天问 · 导演与合规**
    B4 ★★ 点「剧组」标题（没在跑）⇒ 去 **天问 · 剧组 Agents**（列表，不带 agent）
    B5 ★★ 把"在跑"打开（`_run_alive` 置真）⇒ 同样这三个标题改去**书斋**
        （类型风格 / 风格控制 / 剧组 Agents）—— 这是用户那条规则的另一半
    B6 ★★ 真打开一次：`show_project_settings(tab=TAB_BOOK_STYLEPANEL)` 落到的
        真的是「风格控制」那一页（读 `ft.Tabs.selected_index` 与标题反查）
    B7 ★★ 剧组某一行 ⇒ 带 **agent key** 去剧组 Agents 页，且真机上**编辑框真的叠出来**
    B8 ★★ 书斋「风格控制」的滑杆：**初值读 CFG**、**改一下就写回 CFG**
        （"配置之后马上起效"的实处；改之前这两条都不成立）

产出：`assets/screenshots/run_panel_nav.png` + `run_panel_nav_report.json`

English:
Real-device verification: run page panel relocation + clicking titles jumps to settings (user
called it out on 2026-10-11).
User's four sentences:
  ① The run page's **"System" Panel at the lower right moves to below "Style Control" on the left**;
  ② **The minimap moves above "Run Config"**;
  ③ Clicking the titles of "Run Config" and "Style Control" (**underlined to indicate clickable**) enters the corresponding config
     location (**of the project settings**) **and takes effect immediately after configuration**;
  ④ Clicking the crew on the right "Crew" (also clickable) enters the project's Agent list,
     **clicking a particular Agent goes directly to the project's Agent settings**.
  Rule (user decided "running→Shuzhai, not running→Tianwen"):
     · Simulation **currently running** → Shuzhai (project settings) corresponding page;
     · Simulation **not yet started** → Tianwen (global settings) corresponding page.
Criteria split into two groups:
  **Group A (pure logic, no window launched)**
    A1 ★ The six tab index constants match one-to-one with the **real titles** of `tab_defs` in the two dialogs
        (hardcoded numbers decoupled from real order ⇒ clicking a title silently lands on the neighboring page, so must reverse-lookup)
    A2 ★★ `_settings_target` gives the two different targets Shuzhai / Tianwen by "running / not running"
    A3 ★★ Clickable titles: underline + `↗` + hand cursor + hover tooltip all present, and the grabber `_panel_goto` is in
    A4 ★★ Shuzhai's three blocks (run boundary / style control / director) **really write CFG**: in source
        every key has a `CFG.set` landing point (not "looks like it's wired up")
  **Group B (actually launch window)**
    B1 ★★ Left column order = Time / **Minimap** / **Run Config** / Style Control / **System**;
        right column = present characters / plot / crew (System is no longer in the right column)
    B2 ★★ Click "Run Config" title (not running) ⇒ go to **Tianwen · Run** (tab=TAB_GLOBAL_RUN)
    B3 ★★ Click "Style Control" title (not running) ⇒ go to **Tianwen · Director & Compliance**
    B4 ★★ Click "Crew" title (not running) ⇒ go to **Tianwen · Crew Agents** (list, without agent)
    B5 ★★ Turn "running" on (`_run_alive` set true) ⇒ these same three titles go to **Shuzhai**
        (type style / style control / crew Agents) —— this is the other half of the user's rule
    B6 ★★ Really open once: `show_project_settings(tab=TAB_BOOK_STYLEPANEL)` lands on
        really the "Style Control" page (read `ft.Tabs.selected_index` and reverse-lookup the title)
    B7 ★★ A crew row ⇒ go to the Crew Agents page with the **agent key**, and on real device **the edit box really stacks out**
    B8 ★★ Shuzhai "Style Control" sliders: **initial value reads CFG**, **change once and write back to CFG**
        (the substance of "takes effect immediately after configuration"; before the change neither held)
Output: `assets/screenshots/run_panel_nav.png` + `run_panel_nav_report.json`
"""
from __future__ import annotations

import ast
import asyncio
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
from util.flet_shutdown import shutdown  # noqa: E402
import verify_ui_common as VU  # noqa: E402
VU.redirect_env_writes()

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')

import os  # noqa: E402
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

VU.patch_flat_background()

from gui.app_flet import NovelWorldApp  # noqa: E402
from store.project import Project  # noqa: E402
from i18n import set_lang  # noqa: E402
set_lang(_lang)

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {}
CHECKS: list = []
_FAILS = 0


def ok(name: str, cond, detail='') -> bool:
    """记一条判据（`detail` 是**实测值**，红了要能一眼看出差在哪）。
        English:
    Record one criterion (`detail` is the **measured value**; when red you must see at a glance
    where it differs).
    """
    global _FAILS
    good = bool(cond)
    if not good:
        _FAILS += 1
    CHECKS.append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    print(f'  {"[OK]  " if good else "[FAIL]"} {name}'
          + (f'   ← {detail}' if detail != '' else ''))
    return good


G = NovelWorldApp


# ══════════════════════════════════════════════════════════════════
#  A 组：纯逻辑
# [EN] Group A: pure logic
# ══════════════════════════════════════════════════════════════════
def _tab_titles(fn_name: str) -> list[str]:
    """从**源码**里读某个对话框 `tab_defs` 的标题列表（i18n 的中文 key）。

    ⚠ 用 ast 读源码、而不是调那个方法：这两个对话框都要 `page` 才能跑，
       而 A 组刻意不起窗口。读的是**真实顺序**，不是我们以为的顺序。
    
        English:
    Read a dialog's `tab_defs` title list from **source** (the Chinese i18n keys).
        ⚠ Use ast to read the source, not call that method: both dialogs need `page` to run,
           and Group A deliberately does not launch a window. Read the **real order**, not the order we think.
    """
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Assign)
                        and any(getattr(t, 'id', None) == 'tab_defs'
                                for t in sub.targets)):
                    out = []
                    for el in sub.value.elts:
                        first = el.elts[0]
                        arg = first.args[0] if isinstance(first, ast.Call) else None
                        out.append(str(getattr(arg, 'value', '<expr>')))
                    return out
    return []


def _bare_app():
    """一个**不跑 `__init__`** 的实例（A 组只调不碰界面状态的方法）。
        English:
    An instance that **does not run `__init__`** (Group A only calls methods that don't touch UI
    state).
    """
    return object.__new__(G)


def group_a_bare(app) -> None:
    glob_titles = _tab_titles('show_global_settings')
    book_titles = _tab_titles('show_project_settings')
    REPORT['tab_titles'] = {'global': glob_titles, 'book': book_titles}

    print('\n── A 组：页签下标与真实顺序 ──')
    pairs = [
        ('天问 · 运行', G.TAB_GLOBAL_RUN, glob_titles, '运行'),
        ('天问 · 导演与合规', G.TAB_GLOBAL_STYLE, glob_titles, '导演与合规'),
        ('天问 · 剧组 Agents', G.TAB_GLOBAL_CREW, glob_titles, '剧组 Agents'),
        ('书斋 · 类型风格', G.TAB_BOOK_STYLE, book_titles, '类型风格'),
        ('书斋 · 风格控制', G.TAB_BOOK_STYLEPANEL, book_titles, '风格控制'),
        ('书斋 · 剧组 Agents', G.TAB_BOOK_CREW, book_titles, '剧组 Agents'),
    ]
    bad = []
    got = {}
    for label, idx, titles, want in pairs:
        real = titles[idx] if 0 <= idx < len(titles) else '<越界>'
        got[label] = f'[{idx}]={real}'
        if real != want:
            bad.append(f'{label}: 下标 {idx} 实际是「{real}」，应为「{want}」')
    REPORT['tab_index_check'] = got
    ok('A1 ★★ 六个跳转目标下标与两个对话框的真实页签**一一对上**'
       '（脱钩就会静默跳到隔壁那页）', not bad, ' · '.join(bad) if bad else got)

    # ── A2：`_settings_target` 按"在跑 / 没在跑"分流 ──
    # [EN] ── A2: `_settings_target` branches by "running / not running" ──
    print('\n── A2：在跑→书斋，没在跑→天问 ──')
    app.current_project = object()          # 有项目（运行页必然有）
    # [EN] Has project (the run page always has one)
    app._run_alive = lambda: False
    idle = (app._settings_target(book_tab=G.TAB_BOOK_STYLEPANEL,
                                 global_tab=G.TAB_GLOBAL_STYLE))
    app._run_alive = lambda: True
    live = (app._settings_target(book_tab=G.TAB_BOOK_STYLEPANEL,
                                 global_tab=G.TAB_GLOBAL_STYLE))
    REPORT['targets'] = {'idle': idle, 'live': live}
    ok('A2 ★★ 没在跑 →（天问 / 导演与合规）；在跑 →（书斋 / 风格控制）',
       idle == ('global', G.TAB_GLOBAL_STYLE)
       and live == ('book', G.TAB_BOOK_STYLEPANEL),
       f'没跑={idle} 在跑={live}')

    # 没项目时即便"在跑"也走天问（书斋无从打开）
    # [EN] With no project, even if "running" it goes to Tianwen (Shuzhai cannot be opened)
    app.current_project = None
    ok('A2b ★ 没有项目时一律走天问（书斋是"本书设置"，没书就无从打开）',
       app._settings_target(book_tab=1, global_tab=0) == ('global', 0),
       app._settings_target(book_tab=1, global_tab=0))

    # ── A3：可点标题的四个记号 ──
    # [EN] ── A3: the four markers for clickable titles ──
    print('\n── A3：标题可点的四个记号 ──')
    holder: list = []
    ctl = app._clickable_title('运行配置', lambda e: holder.append(1), '去改这些值')
    kids = VU.walk(ctl)
    txts = [c for c in kids if isinstance(c, ft.Text)]
    underline = [c for c in txts
                 if getattr(getattr(c, 'style', None), 'decoration', None)
                 is not None]
    REPORT['title_ctl'] = {
        'type': type(ctl).__name__,
        'goto': bool(getattr(ctl, '_panel_goto', False)),
        'on_tap': getattr(ctl, 'on_tap', None) is not None,
        'cursor': str(getattr(ctl, 'mouse_cursor', None)),
        'tooltip': str(getattr(ctl, 'tooltip', '')),
        'underline_texts': [str(c.value) for c in underline],
    }
    ok('A3 ★★ 标题是**下划线 + ↗ + 手型光标 + 悬停说明**，且带 `_panel_goto` 抓手',
       getattr(ctl, '_panel_goto', False)
       and getattr(ctl, 'on_tap', None) is not None
       and 'CLICK' in str(getattr(ctl, 'mouse_cursor', ''))
       and str(getattr(ctl, 'tooltip', '')).strip() != ''
       and any(str(c.value) == '运行配置' for c in underline)
       and any(str(c.value) == G._PANEL_GOTO_MARK for c in txts),
       REPORT['title_ctl'])
    try:
        ctl.on_tap(None)
    except Exception:                                            # noqa: BLE001
        pass
    ok('A3b ★ 点下去真的调到回调（不是只画了个像按钮的壳）', holder == [1], holder)


def group_a_source() -> None:
    """A4：书斋那三块的"改了就写 CFG"是**源码里真有**，不是看着像。

    ⚠⚠ **一律走 AST，不走字符串包含**（2026-10-11 反例法 M15 抓到的假绿）：
      第一版写的是 `'CFG.save()' in body`，而那一段**注释里**正好有一句
      "见 `save()` 里的 `CFG.save()`" —— 把真正的调用换成 `pass` 之后，
      注释里的那几个字照样让判据绿着。**判据拿文本当尺子 = 量不出任何东西。**
    
        English:
    A4: Shuzhai's three blocks' "change writes CFG" is **really in the source**, not just looking
    like it.
        ⚠⚠ **Always use AST, do not use string containment** (false green caught by counterexample method M15 on 2026-10-11):
          The first version wrote `'CFG.save()' in body`, and in that segment **in the comments** there happened to be a line
          "see `CFG.save()` in `save()`" —— after replacing the real call with `pass`,
          those characters in the comment still kept the criterion green. **Using text as a ruler = measuring nothing.**
    """
    print('\n── A4：书斋三块真的写 CFG（AST 判，不看文本）──')
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'show_project_settings':
            fn = node
    calls_live: set = set()
    has_cfg_save = False
    has_cfg_f_loopvar = False
    live_by_loopvar = False
    style_keys: set = set()
    if fn is not None:
        for n in ast.walk(fn):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            # `_live('KEY', …)` / `_live_dd('KEY', …)`：第一个参数就是这个键
            # [EN] `_live('KEY', …)` / `_live_dd('KEY', …)`: the first argument is this key
            if isinstance(f, ast.Name) and f.id in ('_live', '_live_dd'):
                if n.args and isinstance(n.args[0], ast.Constant):
                    calls_live.add(str(n.args[0].value))
            # ★★★ 2026-10-30：运行模式 / 起始点 / 主线吸附力**改走项目覆盖层**
            #   （`_ov_live` / `_ov_live_dd`，写这本书的 `[运行]` 段，不碰 `.env`）。
            #   ⇒ 它们仍然"改了就生效"，只是生效的**去处**变了；判据要把这条路也认上，
            #     否则会把"接好了"误判成"没接"（A4 就是为了抓"看着接上了"）。
            #   ⚠ 这不是放宽：认可的名字只有这两个，且它们写的是配置（见 D7 反着查——
            #     同一个键**不许**再出现在 `_live*` 里，两处写同一个键才是真事故）。
            # [EN] ★★★ 2026-10-30: run mode / start point / plot adherence now go through the
            # [EN] **project override layer** (`_ov_live` / `_ov_live_dd`), which writes this
            # [EN] book's `[运行]` section instead of `.env`. They still "write on change"; only
            # [EN] the destination moved, so the criterion must recognize that path too. This is
            # [EN] not a loosening: only these two names count, and D7 checks the reverse -- the
            # [EN] same key must **not** also appear in `_live*` (two writers is the real bug).
            if isinstance(f, ast.Name) and f.id in ('_ov_live', '_ov_live_dd'):
                if n.args and isinstance(n.args[0], ast.Constant):
                    calls_live.add(str(n.args[0].value))
                # ⚠ 风格那 7 根是**循环里**接的（`_live(key, slider, …)`，
                #   `key` 是循环变量、AST 里不是字面量）—— 所以这里额外认
                #   "首参是名为 `key` 的变量"，再由下面的 `style_params` 补名字。
                #   不这么写就只能认字面量，把 7 个真接上的键误判成"没接"。
                # [EN] ⚠ Those seven style sliders are wired **inside a loop** (`_live(key, slider, ...)`
                # [EN] where `key` is a loop variable, not a literal in the AST) -- so we additionally
                # [EN] recognize "first arg is the variable named `key`", and the names come from
                # [EN] `style_params` below. Without this, only literals would count and the seven
                # [EN] genuinely-wired keys would be misjudged as "not wired".
                if n.args and isinstance(n.args[0], ast.Name) \
                        and n.args[0].id == 'key':
                    live_by_loopvar = True
            # `_cfg_f(key, default)`：滑杆初值**读 CFG** 的落点
            # [EN] `_cfg_f(key, default)`: where the slider's initial value **reads CFG**
            if isinstance(f, ast.Name) and f.id == '_cfg_f' and len(n.args) >= 2:
                if isinstance(n.args[0], ast.Name) and n.args[0].id == 'key':
                    has_cfg_f_loopvar = True
            # `CFG.save()`
            if (isinstance(f, ast.Attribute) and f.attr == 'save'
                    and isinstance(f.value, ast.Name) and f.value.id == 'CFG'):
                has_cfg_save = True
        # `style_params = [(标签, 'KEY', 默认), …]` 里那 7 个键
        # [EN] The 7 keys in `style_params = [(label, 'KEY', default), …]`
        for n in ast.walk(fn):
            if (isinstance(n, ast.Assign)
                    and any(getattr(t, 'id', None) == 'style_params' for t in n.targets)
                    and isinstance(n.value, ast.List)):
                for el in n.value.elts:
                    if (isinstance(el, ast.Tuple) and len(el.elts) >= 2
                            and isinstance(el.elts[1], ast.Constant)):
                        style_keys.add(str(el.elts[1].value))
    if live_by_loopvar:
        calls_live |= style_keys
    keys = ['RUN_MODE', 'STORY_START_POINT', 'PLOT_ADHERENCE', 'PACING_STYLE',
            'TENSION_CURVE', 'ANGST_LEVEL', 'HUMOR_LEVEL', 'SATISFACTION_DENSITY',
            'ROMANCE_RATIO', 'SUSPENSE_DENSITY', 'WORLDBUILDING_PACE',
            'CHARACTER_IQ']
    miss = [k for k in keys if k not in calls_live]
    REPORT['book_live_keys'] = sorted(calls_live)
    REPORT['style_keys_from_loop'] = sorted(style_keys)
    ok('A4 ★★ 书斋「运行边界 / 风格控制 / 导演」那 12 个键都真的进了 `_live*` 调用'
       '（AST：调用实参，不是注释里的字符串；7 个风格键从 `style_params` 补名）',
       not miss, f'缺={miss}' if miss else f'{len(keys)} 个键全在')
    ok('A4b ★★ 风格滑杆初值**读 CFG**（AST：`_cfg_f(key, default)` 这个调用在）',
       has_cfg_f_loopvar,
       '' if has_cfg_f_loopvar else 'AST 里没有 `_cfg_f(key, …)` 调用')
    ok('A4c ★★ 书斋「保存」里**真的调了** `CFG.save()`（AST：Call，不是注释里的字）',
       has_cfg_save,
       '' if has_cfg_save else 'AST 里没有 `CFG.save()` 调用')


# ══════════════════════════════════════════════════════════════════
#  B 组：真启窗口
# [EN] Group B: actually launch the window
# ══════════════════════════════════════════════════════════════════
def _panels(col: ft.Column) -> list:
    """左/右栏那个 `ft.Column` 的**直接子控件**（每个是一块面板 Container）。
        English:
    The **direct children** of the `ft.Column` in the left/right column (each is a panel Container).
    """
    return [c for c in (getattr(col, 'controls', None) or [])]


def _first_text(ctrl) -> str:
    """面板里**第一个非空 `ft.Text`** = 这一块的标题。

    ⚠ 现在是 `GestureDetector(Row([Text(标题), Text('↗')]))`，
      所以不能只看 `content.controls[0]`（那会拿到 GestureDetector 本身）。
    
        English:
    The **first non-empty `ft.Text`** in the panel = this block's title.
        ⚠ Currently it's `GestureDetector(Row([Text(title), Text('↗')]))`,
          so you can't just look at `content.controls[0]` (that would get the GestureDetector itself).
    """
    for c in VU.walk(ctrl):
        if isinstance(c, ft.Text) and str(c.value or '').strip():
            return str(c.value).strip()
    return ''


def _find_columns(page) -> tuple:
    """页面里的左栏与右栏。

    ★★★ 2026-10-24：右栏的宽度**不再写死 240** —— 用户要求右栏加宽（240 → 400，
      见 `app_flet.RUN_RIGHT_W` 的说明），而这里原来写的是 `w == 240`。
      于是加宽之后**右栏直接找不到了**，`right` 为 None ⇒ B1b 报"右栏只剩
      [] 三块"（实测：`verify_run_panel_nav` 从 8/8 掉到 9/11）。
      ⇒ 改成读产品那个常量。**判据不许自己写一份尺寸**：它量的对象就是
        产品上那个 `Column`，尺寸只有一个事实来源。

    [EN] The left and right columns on the page.
    [EN] ★★★ 2026-10-24: the right column's width is **no longer hardcoded to 240** -- the user asked
    [EN] for it to be wider (240 -> 400, see `app_flet.RUN_RIGHT_W`), and this used `w == 240`. After
    [EN] the widening the right column **could not be found at all**, so `right` was None and B1b
    [EN] reported "the right column is [] pieces" (measured: `verify_run_panel_nav` fell from 8/8 to
    [EN] 9/11). => Read the product's constant instead. **A criterion must not carry its own copy of a
    [EN] size**: it measures that very `Column`, and the size has exactly one source of truth.
    """
    from gui.app_flet import RUN_RIGHT_W
    left = right = None
    for c in VU.walk(page):
        if isinstance(c, ft.Column):
            w = getattr(c, 'width', None)
            if w == 220 and left is None:
                left = c
            elif w == RUN_RIGHT_W and right is None:
                right = c
    return left, right


def _goto_of(panel):
    """面板标题上那个可点控件（`_panel_goto`），没有就 None。
        English:
    The clickable control on the panel title (`_panel_goto`), or None if absent.
    """
    for c in VU.walk(panel):
        if getattr(c, '_panel_goto', False):
            return c
    return None


def _tabs_in(dlg) -> object:
    for c in VU.walk(dlg):
        if isinstance(c, ft.Tabs):
            return c
    return None


def _tab_label_at(tabs, idx: int) -> str:
    try:
        bar = tabs.content.controls[0]
        return str(getattr(bar.tabs[idx], 'label', ''))
    except Exception:                                            # noqa: BLE001
        return ''


async def group_b(page, app, tmp: Path) -> None:
    print('\n── B 组：真机 ──')

    # ── B1：栏位顺序 ──
    # [EN] -- B1: column order --
    app.show_main_screen()
    page.update()
    await asyncio.sleep(1.0)
    left, right = _find_columns(page)
    lt = [_first_text(p) for p in _panels(left)] if left is not None else []
    rt = [_first_text(p) for p in _panels(right)] if right is not None else []
    REPORT['left_order'] = lt
    REPORT['right_order'] = rt
    ok('B1 ★★ 左栏顺序 = 时间 / 小地图 / 运行配置 / 风格控制 / 系统'
       '（小地图在运行配置**上面**、系统接在风格控制**下面**）',
       len(lt) == 5 and lt[1:3] == ['小地图', '运行配置']
       and lt[3] == '风格控制' and lt[4] == '系统', lt)
    ok('B1b ★★ 右栏只剩 在场人物 / 剧情 / 剧组（系统已搬走）',
       rt == ['在场人物', '剧情', '剧组'], rt)
    # 像素取证：这一屏存一张（给人看的底片）
    # [EN] Pixel evidence: save one screenshot of this screen (a negative for humans)
    try:
        png = await page.take_screenshot()
        (OUT / 'run_panel_nav.png').write_bytes(png or b'')
    except Exception:                                            # noqa: BLE001
        pass

    # ── 三个标题都得可点 ──
    # [EN] ── all three titles must be clickable ──
    panels = {t: p for t, p in zip(lt, _panels(left))}
    gotos = {t: _goto_of(panels.get(t)) for t in ('运行配置', '风格控制')}
    crew_goto = _goto_of(_panels(right)[2]) if len(rt) >= 3 else None
    ok('B1c ★★ 左栏「运行配置」「风格控制」与右栏「剧组」三块标题都可点',
       all(g is not None for g in gotos.values()) and crew_goto is not None,
       {k: (v is not None) for k, v in gotos.items()} | {'剧组': crew_goto is not None})

    # ── B2~B4：没在跑 ⇒ 天问 ──
    # [EN] ── B2~B4: not running ⇒ Tianwen ──
    calls: list = []
    orig_g = app.show_global_settings
    orig_b = app.show_project_settings
    app.show_global_settings = lambda tab=None, agent=None: calls.append(
        ('global', tab, agent))
    app.show_project_settings = lambda tab=None, agent=None: calls.append(
        ('book', tab, agent))
    try:
        for t in ('运行配置', '风格控制'):
            gotos[t].on_tap(None)
        crew_goto.on_tap(None)
        app._goto_crew_agent('novelist')      # 剧组**某一行**
        # [EN] **Some row** of the crew
    finally:
        app.show_global_settings = orig_g
        app.show_project_settings = orig_b
    REPORT['idle_calls'] = calls
    want_idle = [('global', G.TAB_GLOBAL_RUN, None),
                 ('global', G.TAB_GLOBAL_STYLE, None),
                 ('global', G.TAB_GLOBAL_CREW, None),
                 ('global', G.TAB_GLOBAL_CREW, 'novelist')]
    ok('B2 ★★ **没在跑**时：运行配置→天问·运行、风格控制→天问·导演与合规、'
       '剧组→天问·剧组Agents（列表不带 agent）', calls[:3] == want_idle[:3], calls[:3])
    ok('B4 ★★ 剧组**某一行**带着该职位的 key 去同一页（`agent=novelist`）'
       '—— 这就是"点某一个 Agent 直接进它的设置"',
       calls[3:4] == want_idle[3:4], calls[3:4])

    # ── B5：在跑 ⇒ 书斋 ──
    # [EN] ── B5: running ⇒ Shuzhai ──
    calls2: list = []
    app._run_alive = lambda: True
    app.show_global_settings = lambda tab=None, agent=None: calls2.append(
        ('global', tab, agent))
    app.show_project_settings = lambda tab=None, agent=None: calls2.append(
        ('book', tab, agent))
    try:
        for t in ('运行配置', '风格控制'):
            gotos[t].on_tap(None)
        crew_goto.on_tap(None)
    finally:
        app.show_global_settings = orig_g
        app.show_project_settings = orig_b
        del app._run_alive                     # 复原成真正的方法
        # [EN] Restore to the real method
    REPORT['live_calls'] = calls2
    # ★ 2026-10-30：书斋那头改成**「运行」页**（运行边界搬过去了）。
    # [EN] ★ 2026-10-30: the Study side is now the **Run** tab (boundaries moved there).
    want_live = [('book', G.TAB_BOOK_RUN, None),
                 ('book', G.TAB_BOOK_STYLEPANEL, None),
                 ('book', G.TAB_BOOK_CREW, None)]
    ok('B5 ★★ **正在跑**时同样三个标题改去**书斋**（运行 / 风格控制 / 剧组 Agents）'
       '—— 这是用户那条规则的另一半', calls2 == want_live, calls2)

    # ── B6：真打开一次，看落到的页签对不对 ──
    # [EN] ── B6: really open it once, check the tab landed on is correct ──
    page.pop_dialog()
    page.update()
    await asyncio.sleep(0.3)
    app.show_project_settings(tab=G.TAB_BOOK_STYLEPANEL)
    page.update()
    await asyncio.sleep(0.9)
    dlgs = VU.open_dialogs(page)
    tabs = _tabs_in(dlgs[-1]) if dlgs else None
    REPORT['book_tabs'] = {
        'selected_index': getattr(tabs, 'selected_index', None),
        'label': _tab_label_at(tabs, G.TAB_BOOK_STYLEPANEL) if tabs else '',
    }
    ok('B6 ★★ `show_project_settings(tab=书斋·风格控制)` 真的落在「风格控制」那一页',
       tabs is not None and tabs.selected_index == G.TAB_BOOK_STYLEPANEL
       and _tab_label_at(tabs, G.TAB_BOOK_STYLEPANEL) == '风格控制',
       REPORT['book_tabs'])

    # ── B8：书斋风格滑杆「初值读 CFG + 改一下就写回」 ──
    # [EN] -- B8: the study's style sliders "initial value from CFG + write back on change" --
    sliders = [c for c in VU.walk(dlgs[-1]) if isinstance(c, ft.Slider)] if dlgs else []
    old_humor = CFG.raw('HUMOR_LEVEL')
    CFG.set('HUMOR_LEVEL', '0.9')
    page.pop_dialog()
    app.show_project_settings(tab=G.TAB_BOOK_STYLEPANEL)
    page.update()
    await asyncio.sleep(0.9)
    dlgs = VU.open_dialogs(page)
    sliders = [c for c in VU.walk(dlgs[-1]) if isinstance(c, ft.Slider)] if dlgs else []
    REPORT['sliders'] = {'n': len(sliders),
                         'humor_value': getattr(sliders[1], 'value', None)
                         if len(sliders) > 1 else None}
    ok('B8 ★★ 风格滑杆的**初值来自 CFG**（把 HUMOR_LEVEL 设成 0.9 → 那一根滑杆就是 0.9）',
       len(sliders) >= 2 and abs(float(sliders[1].value) - 0.9) < 0.02,
       REPORT['sliders'])
    # 改一下 → CFG 跟着变（"配置之后马上起效"的实处）
    # [EN] Change it → CFG changes accordingly (the substance of "takes effect immediately after
    # [EN] configuration")
    if len(sliders) >= 2:
        CFG.set('HUMOR_LEVEL', '0.1')
        s = sliders[1]
        s.value = 0.7
        try:
            s.on_change(None)
        except Exception as e:                                   # noqa: BLE001
            REPORT['slider_on_change_err'] = repr(e)
        page.update()
        await asyncio.sleep(0.3)
    REPORT['humor_after'] = CFG.raw('HUMOR_LEVEL')
    ok('B8b ★★ 拖动那根滑杆 ⇒ `CFG` 里立刻变成新值'
       '（改之前这条**恒不成立**：书斋一个 CFG.set 都没有）',
       str(REPORT['humor_after']).startswith('0.7'), REPORT['humor_after'])
    CFG.set('HUMOR_LEVEL', old_humor or '0.3')

    # ── B11：书斋的下拉/输入框也真的写 CFG（不只是滑杆）──
    # ⚠ 这一条同时守住"`_live` 必须接在 `_field` 上"：`mk_dropdown` 返回的是 `Row`，
    #   真正的下拉挂在 `row._field` 上。接在 `Row` 上不会报错、**只是永不触发**
    #   （反例法 M17 就是往这里扎的）。
    # [EN] ⚠ This also guards "`_live` must wire `_field`": `mk_dropdown` returns a `Row` and the real
    # [EN] dropdown hangs on `row._field`. Wiring the `Row` raises nothing and **just never fires**
    # [EN] (reverse experiment M17 aims exactly here).
    dlg_now = VU.open_dialogs(page)[-1]
    dds = [c for c in VU.walk(dlg_now)
           if type(c).__name__ == 'DropdownM2']
    pace = next((d for d in dds
                 if {str(getattr(o, 'key', '')) for o in (getattr(d, 'options', None) or [])}
                 == {'slow', 'medium', 'fast', 'roller'}), None)
    old_pace = CFG.raw('PACING_STYLE')
    if pace is not None:
        pace.value = 'fast'
        try:
            pace.on_change(None)
        except Exception as e:                                   # noqa: BLE001
            REPORT['pacing_err'] = repr(e)
        page.update()
        await asyncio.sleep(0.3)
    REPORT['pacing_after'] = CFG.raw('PACING_STYLE')
    ok('B11 ★★ 书斋的**下拉框**也接上了（改「节奏感」⇒ `PACING_STYLE` 立刻变；'
       '这也证明 `_live` 接的是 `_field`、不是外面那层 `Row`）',
       pace is not None and str(REPORT['pacing_after']) == 'fast',
       f'找到下拉={pace is not None} PACING_STYLE={REPORT["pacing_after"]}')
    CFG.set('PACING_STYLE', old_pace or 'medium')

    # ── B10：改完**关掉设置**⇒ 运行页面板立刻显示新值 ──
    # [EN] -- B10: after closing the settings, the run page panels immediately show the new values --
    rows_now = dict(app._ui_run.get('style_rows') or {})
    before_txt = rows_now['HUMOR_LEVEL'][1].value if 'HUMOR_LEVEL' in rows_now else '—'
    CFG.set('HUMOR_LEVEL', '0.6')
    acts = list(getattr(dlg_now, 'actions', None) or [])
    if acts:
        acts[-1].on_click(None)          # 「取消」→ pop + 重建运行页
        # [EN] "Cancel" → pop + rebuild the run page
    page.update()
    await asyncio.sleep(1.2)
    rows_after = dict(app._ui_run.get('style_rows') or {})
    now_txt = rows_after['HUMOR_LEVEL'][1].value if 'HUMOR_LEVEL' in rows_after else '—'
    REPORT['panel_refresh'] = {'before': before_txt, 'after': now_txt}
    ok('B10 ★★ 在书斋改完（点「取消」关掉）之后，运行页「风格控制」那条'
       '**立刻变成新值** 6/10（关掉设置就重建一次，见 `_after_settings_closed`）',
       now_txt == '6/10', REPORT['panel_refresh'])

    # ── B9：剧组**每一行**都能点开该职位的设置（用假台账喂真台账渲染）──
    # [EN] -- B9: **every row** of the cast panel opens that position's settings (feed a fake ledger into
    # [EN] the real renderer) --
    class _Studio:
        @staticmethod
        def ledger() -> list:
            return [
                {'key': 'novelist', 'name': '小说作家', 'duty': '写正文',
                 'state': 'idle', 'busy': False, 'secs': 0.0, 'line': ''},
                {'key': 'director', 'name': '导演', 'duty': '编排',
                 'state': 'working', 'busy': True, 'secs': 3.0, 'line': ''},
            ]

    class _Loop:
        studio = _Studio()

    class _Ses:
        loop = _Loop()
        is_alive = True

    app.session = _Ses()
    app._refresh_crew_panel()
    page.update()
    await asyncio.sleep(0.6)
    crew_rows = list(getattr(app._ui_run.get('crew_list'), 'controls', None) or [])
    row_keys = [getattr(c, '_crew_goto', None) for c in crew_rows]
    REPORT['crew_rows'] = row_keys
    calls9: list = []
    app.show_global_settings = lambda tab=None, agent=None: calls9.append(
        ('global', tab, agent))
    app.show_project_settings = lambda tab=None, agent=None: calls9.append(
        ('book', tab, agent))
    try:
        for c in crew_rows:
            if getattr(c, '_crew_goto', None):
                c.on_tap(None)
    finally:
        app.show_global_settings = orig_g
        app.show_project_settings = orig_b
    app.session = None
    REPORT['crew_row_calls'] = calls9
    ok('B9 ★★ 剧组每一行都带**该职位的 key**，点一下就带着它去剧组 Agents 页'
       '（"点某一个 Agent 直接进它的设置"；在跑 ⇒ 书斋）',
       row_keys == ['novelist', 'director']
       and calls9 == [('book', G.TAB_BOOK_CREW, 'novelist'),
                      ('book', G.TAB_BOOK_CREW, 'director')],
       f'行={row_keys} 调用={calls9}')

    # ── B7：剧组某一行 ⇒ 编辑框真的叠出来 ──
    # [EN] ── B7: a crew row ⇒ the edit box really stacks out ──
    page.pop_dialog()
    page.update()
    await asyncio.sleep(0.3)
    before = len(VU.open_dialogs(page))
    app._agents_tab(project=None, allow_new=True, open_agent='novelist')
    page.update()
    await asyncio.sleep(0.8)
    dlgs2 = VU.open_dialogs(page)
    top_txt = ' '.join(VU.all_texts(dlgs2[-1])) if dlgs2 else ''
    REPORT['agent_editor'] = {
        'dialogs_before': before, 'dialogs_after': len(dlgs2),
        'has_editor': ('系统提示词' in top_txt) or ('提示词' in top_txt),
    }
    ok('B7 ★★ 点剧组某一行 ⇒「剧组 Agents」列表铺好之外，'
       '**那个职位的编辑框真的叠在上面**（不是只开列表让人自己找）',
       len(dlgs2) > before and REPORT['agent_editor']['has_editor'],
       REPORT['agent_editor'])
    while VU.open_dialogs(page):
        page.pop_dialog()
    page.update()


async def main(page: ft.Page):
    app = G()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)

    tmp = Path(tempfile.mkdtemp(prefix='nws_panel_nav_'))
    try:
        bare = _bare_app()
        group_a_bare(bare)
        group_a_source()

        # ★★★ 2026-10-17 修：`isolate_projects_dir()` 返回的是**换之前的老值**
        #   （`.env` 里的 `DEFAULT_PROJECTS_DIR`），不是新目录 ——
        #   原写法把它拼上夹具名，等于**直接往用户真实项目目录里写**，
        #   用户机上那个「面板跳转验证」残留就是这么来的。
        #   ⇒ 返回值只作还原用，落点自己留。
        # [EN] ★★★ Fixed 2026-10-17: `isolate_projects_dir()` returns the **old value** (the `.env`
        # [EN] `DEFAULT_PROJECTS_DIR`), not the new directory -- the old form appended the fixture name to
        # [EN] it, i.e. **wrote straight into the user's real project directory**; the leftover
        # [EN] "面板跳转验证" on their machine came from exactly this.
        # [EN] => The return value is only for restoring; keep the landing path yourself.
        _seed = APP_DIR / 'assets' / 'screenshots' / '_proj' / '面板跳转验证'
        VU.isolate_projects_dir(_seed)
        root = _seed / '面板跳转验证'
        root.mkdir(parents=True, exist_ok=True)
        for sub in ('设定集', '优化后设定', '完整设定集导出'):
            (root / sub).mkdir(exist_ok=True)
        proj = Project(root, '面板跳转验证')
        proj.write_nwsproj()
        app.current_project = proj
        await group_b(page, app, tmp)
    finally:
        REPORT['checks'] = CHECKS
        REPORT['passed'] = len(CHECKS) - _FAILS
        REPORT['total'] = len(CHECKS)
        (OUT / 'run_panel_nav_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=1), encoding='utf-8')
        shutil.rmtree(tmp, ignore_errors=True)
        print(f'\n运行页面板跳转验证：{REPORT["passed"]}/{REPORT["total"]}')
        print(f'报告：assets/screenshots/run_panel_nav_report.json')
        await shutdown(page, code=0 if _FAILS == 0 else 1)


if __name__ == '__main__':
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
