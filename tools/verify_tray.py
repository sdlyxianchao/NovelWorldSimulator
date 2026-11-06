# -*- coding: utf-8 -*-
"""判据：托盘图标 + 「关窗到底做什么」（2026-10-31 用户）。

用户原话：「我想加一个任务栏右下角图标，然后可以在天机 常规里设置点击右上角关闭
以及归去是完全退出还是只是关闭窗口 但是任务栏图标还存在 这个图标支持 打开主界面
以及 开始菜单各个菜单」。

★ 这条判据必须分成**四层**，因为它们的"真"根本不是一件事：
  A 决策：`close_action` / `resolve_close` 是纯函数 —— 穷举真值表。
    ⚠ 最要紧的一格是 `tray + 图标没起来 ⇒ 退出`：写错这一格，用户点一次 ×
      就永远找不回窗口（藏起来了、又没有图标能点）。这一格必须单独一条断言。
  B 接线：谁调谁、谁在谁之前（AST 看**源码**，不看"关键字出现过没有"）。
    · `prevent_close` **只允许**在图标真的起来之后设（否则点 × 关不掉）；
    · `_tray_stop()` **必须在 `destroy()` 之前**（`destroy()` 抛 `CancelledError`，
      之后的代码一行都不执行 ⇒ 托盘图标留成残影）；
    · 藏窗口之前**必须**补一次自动落盘（`on_disconnect` 不会来）。
  C 真托盘：`start()` 返回 True、`running` 为真、`stop()` 之后干净、重复 stop 无害。
  E 同源：托盘菜单那一段的标题与顺序**必须**等于开始界面的 `menu_items`
    （2026-10-31 用户第一眼挑出三条：少了「开　卷」、多了一个「打开以前的故事」、
    少了「起　笔」—— 根因是我手抄了一份菜单，还把「拾　卷」的**说明**当成了标题）。
  D 真窗口：藏得住（`IsWindowVisible` 为 0）、叫得回（又是 1），且进程还在。
    ⚠ 只读我们发出去的 `page.window.visible` 是**自欺**：那是请求值不是事实，
      必须从外面读 `IsWindowVisible`。

⚠ 本判据**不改**用户 `.env`：要测 `tray` 分支时用 `mock.patch` 顶掉 `close_action`，
  不落盘、不用还原（"在用户真实项目上验证完要清干净"那条教训的现行做法）。

用法：.venv/Scripts/python.exe tools/verify_tray.py

English:
Criterion: the tray icon and "what closing the window really does" (user, 2026-10-31).
★ Four layers, because "true" means different things: A the pure decision functions
(enumerate the truth table -- the critical cell is "tray + icon not up => exit", get it wrong
and one click on the × loses the window forever); B the wiring, read from the AST (source, not
"did the keyword appear"): `prevent_close` only after the icon is up, `_tray_stop()` **before**
`destroy()` (destroy raises CancelledError and no later line runs), a flush before hiding
(`on_disconnect` won't fire); C a real tray (start/running/stop/idempotent); D a real window
(hides -- `IsWindowVisible` 0 -- and comes back, with the process alive). ⚠ Reading back
`page.window.visible` would be self-deception: that is the request, not the fact.
⚠ This criterion **never writes the user's `.env`**: the `tray` branch is exercised with
`mock.patch` on `close_action`.
"""
from __future__ import annotations

import ast
import asyncio
import sys
import ctypes
import time
import traceback
from ctypes import wintypes
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import flet as ft                                        # noqa: E402

from tools.verify_exit import finish                     # noqa: E402
from util.flet_shutdown import shutdown                  # noqa: E402

REPORT = APP / 'assets' / 'screenshots' / 'tray_report.json'
TITLE = 'NWS-TRAY-VERIFY'
results: list[dict] = []


def rec(name: str, ok: bool, detail: str = '') -> None:
    results.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    mark = '✓' if ok else '✗'
    print(f'{mark} {name}' + (f'   [{detail}]' if detail and not ok else ''), flush=True)


# ══════════════════════════════════════════════════════════════════
#  源码（AST）—— B 组用；只读，不执行
# [EN] Source (AST) for group B -- read only, never executed
# ══════════════════════════════════════════════════════════════════
GUI_PATH = APP / 'gui' / 'app_flet.py'
TRAY_PATH = APP / 'util' / 'tray.py'
CFG_PATH = APP / 'config.py'
GUI_SRC = GUI_PATH.read_text(encoding='utf-8')
TRAY_SRC = TRAY_PATH.read_text(encoding='utf-8')
CFG_SRC = CFG_PATH.read_text(encoding='utf-8')
GUI_TREE = ast.parse(GUI_SRC)


def _defs(name: str) -> list:
    """模块里叫 `name` 的所有函数定义（**同名静默覆盖**要先查，见项目记忆）。"""
    return [n for n in ast.walk(GUI_TREE)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == name]


def _fn(name: str):
    ds = _defs(name)
    return ds[0] if ds else None


def _call_lines(node, attr: str) -> list[int]:
    """`node` 里所有 `xxx.attr(...)` 调用的行号（找"谁在谁之前"用）。"""
    out = []
    for n in ast.walk(node or ast.Module(body=[], type_ignores=[])):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr == attr:
                out.append(int(getattr(n, 'lineno', 0)))
            elif isinstance(f, ast.Name) and f.id == attr:
                out.append(int(getattr(n, 'lineno', 0)))
    return sorted(out)


def _has_call(node, attr: str) -> bool:
    return bool(_call_lines(node, attr))


def _assigns_attr(node, attr: str) -> bool:
    """`node` 里有没有**给** `xxx.attr` 赋值（`ast.Store`）。

    ⚠ 为什么不能用"源码里出现 `maximized` 没有"来判（第一版就是那么写的，
      当场假红）：注释里写着"不能同批设 `maximized`"—— 文本当然出现。
      **注释不是代码**，判据要看 AST。
    [EN] Whether `xxx.attr` is **assigned** anywhere in `node`. ⚠ Text search is wrong here
    (v1 was red for exactly that reason): the comment *explains* not to set `maximized`, so the
    word is present. Comments are not code; read the AST.
    """
    for n in ast.walk(node or ast.Module(body=[], type_ignores=[])):
        if (isinstance(n, ast.Attribute) and n.attr == attr
                and isinstance(n.ctx, ast.Store)):
            return True
    return False


def _calls_inside_if(fn_node, attr: str) -> bool:
    """`fn_node` 里有没有把 `attr(...)` 写在某个 `if` 的 body 里。

    用来判"只在条件成立时才做"—— 光看"它调了"会把 `if ok:` 里的调用与无条件调用
    混为一谈（这正是 `prevent_close` 那一条要防的）。
    [EN] Whether `attr(...)` appears inside some `if` body -- "it is called" alone cannot tell
    a guarded call from an unconditional one.
    """
    for n in ast.walk(fn_node or ast.Module(body=[], type_ignores=[])):
        if isinstance(n, ast.If) and _has_call(n, attr):
            return True
    return False


# ══════════════════════════════════════════════════════════════════
#  A 组 · 决策（纯函数）
# [EN] Group A · the decision (pure functions)
# ══════════════════════════════════════════════════════════════════
def group_a() -> None:
    import importlib
    G = importlib.import_module('gui.app_flet')

    rec('A01 配置写 tray ⇒ close_action() == "tray"',
        G.close_action('tray') == G.CLOSE_TRAY, G.close_action('tray'))
    rec('A02 配置空串 ⇒ exit（默认必须是"能退得出去"那一侧）',
        G.close_action('') == G.CLOSE_EXIT, G.close_action(''))
    rec('A03 配置乱写 ⇒ exit（未知值不能当成"藏起来"）',
        G.close_action('驻留') == G.CLOSE_EXIT, G.close_action('驻留'))
    rec('A04 大写 / 空格容错 ⇒ tray',
        G.close_action('  TRAY \n') == G.CLOSE_TRAY, repr(G.close_action('  TRAY \n')))

    rec('A05 tray + 图标在 ⇒ 藏（用户选的就是这个意思）',
        G.resolve_close('tray', tray_ready=True) == G.DO_HIDE)
    rec('A06 ★ tray + 图标**不在** ⇒ 退出（藏了就再也叫不回来）',
        G.resolve_close('tray', tray_ready=False) == G.DO_EXIT,
        G.resolve_close('tray', tray_ready=False))
    rec('A07 exit + 图标在 ⇒ 退出（图标在也不影响"选的是退出"）',
        G.resolve_close('exit', tray_ready=True) == G.DO_EXIT)
    rec('A08 exit + 图标不在 ⇒ 退出',
        G.resolve_close('exit', tray_ready=False) == G.DO_EXIT)
    rec('A09 未知配置 + 图标在 ⇒ 退出（真值表要整列对齐）',
        G.resolve_close('??', tray_ready=True) == G.DO_EXIT)

    # ── 菜单清单 ──
    spec = G.tray_menu_spec(has_current=False, n_books=0, tray_ready=True)
    solid = [i for i in spec if not i.get('sep')]
    rec('A10 菜单第一项是「显示主界面」且是默认项（回车就是它）',
        solid[0].get('key') == 'show' and solid[0].get('default') is True,
        solid[0])
    rec('A11 ★ 菜单最后一项是「完全退出」且**恒可用**（tray 模式下这就是唯一真出口）',
        solid[-1].get('key') == 'exit' and solid[-1].get('enabled') is True,
        solid[-1])
    rec('A12 一本书都没有 ⇒ 起笔/书斋/回卷**和拾卷**都灰掉，开卷/拆书/天机亮',
        all(i['enabled'] is False for i in solid if i['key'] in
            ('start', 'study', 'resume', 'pick'))
        and all(i['enabled'] is True for i in solid if i['key'] in
                ('open', 'booklab', 'tianji')),
        [(i['key'], i['enabled']) for i in solid])
    spec2 = G.tray_menu_spec(has_current=True, n_books=2, tray_ready=True)
    solid2 = [i for i in spec2 if not i.get('sep')]
    rec('A13 手里有书 ⇒ 起笔/书斋/回卷都亮（与开始菜单同一套 `start_menu_state`）',
        all(i['enabled'] is True for i in solid2
            if i['key'] in ('start', 'study', 'resume')))
    spec3 = G.tray_menu_spec(has_current=False, n_books=1, tray_ready=True)
    rec('A14 盘上只有一本书（没打开）⇒ 三项也是亮的（`START_PICK`）',
        all(i['enabled'] is True for i in spec3 if not i.get('sep')
            and i['key'] in ('start', 'study', 'resume')))
    rec('A15 图标不在时菜单里多一行说明（用户能看懂为什么设了 tray 还退出）',
        any('图标' in str(i.get('text')) and i.get('enabled') is False
            for i in G.tray_menu_spec(has_current=True, n_books=1,
                                      tray_ready=False) if not i.get('sep')))
    rec('A16 每一项都有 key 或 sep（空 key 只允许出现在那行说明上）',
        all(bool(i.get('key')) or i.get('sep') or i.get('enabled') is False
            for i in spec))
    rec('A17 菜单项文字全部非空（i18n 漏了会退回中文原文，不能是空串）',
        all(str(i.get('text') or '').strip() for i in spec if not i.get('sep')))

    # 每一项都能被托盘模块的 dataclass 吃掉（`MenuItem(**it)`）
    try:
        from util import tray as TRAY
        built = [TRAY.MenuItem(**it) for it in spec]
        ok = len(built) == len(spec) and built[0].key == 'show'
    except Exception as e:                                # noqa: BLE001
        ok, built = False, e
    rec('A18 清单能直接被 `MenuItem(**it)` 构造（key 名不许对不上）', ok, built)


# ══════════════════════════════════════════════════════════════════
#  E 组 · 托盘菜单与开始界面**同源**（2026-10-31 用户第一眼就挑出三条）
# [EN] Group E · the tray menu and the start screen share **one source**
# ══════════════════════════════════════════════════════════════════
def _start_menu_titles() -> list[str]:
    """开始界面 `menu_items` 里每一项的**标题**（AST 取元组第 2 个元素 + `t('…')`）。

    ★ 取**下标 1**（标题那个位置），不是"这一项里出现的第一个 `t(...)`"：
      「拾　卷」那一项的说明是三元式 `t('打开以前的故事') if n else …`，
      按"出现顺序取第一个"会取到标题（恰好对），但**按说明取**就会取到
      "打开以前的故事" —— 2026-10-31 手抄托盘菜单时犯的正是这个错。
      判据要跟产品用**同一个位置**，不是同一个"看起来最像的串"。
    [EN] The **label** of every start-screen `menu_items` entry (AST: tuple slot 2 + `t('…')`).
    ★ Slot 1 (the label), not "the first `t(...)` in the entry": 「拾　卷」's description is a
    ternary, and taking the description is exactly the 2026-10-31 hand-copy bug.
    """
    for n in ast.walk(GUI_TREE):
        if not (isinstance(n, ast.Assign)
                and any(getattr(tg, 'id', '') == 'menu_items' for tg in n.targets)
                and isinstance(n.value, ast.List)):
            continue
        out: list[str] = []
        for elt in n.value.elts:
            if not (isinstance(elt, ast.Tuple) and len(elt.elts) >= 2):
                out.append('<不是元组>')
                continue
            e = elt.elts[1]
            if (isinstance(e, ast.Call) and isinstance(e.func, ast.Name)
                    and e.func.id == 't' and e.args
                    and isinstance(e.args[0], ast.Constant)):
                out.append(str(e.args[0].value))
            else:
                out.append(f'<非 t() 字面量: {ast.dump(e)[:40]}>')
        return out
    return []


def group_e() -> None:
    import importlib
    G = importlib.import_module('gui.app_flet')

    started = _start_menu_titles()
    mirrored = [x[1] for x in (G.TRAY_START_ITEMS + G.TRAY_SETTING_ITEMS)]
    # ⚠ 开始界面的最后一项是「归　去」，托盘里它叫「完全退出」（还多了最上面的
    #   「显示主界面」）。这两项是**有意不同名**：托盘那项不看配置、永远真退出，
    #   所以它不叫"归去"。⇒ 比对时掐掉开始界面的尾巴，但**先钉住那条尾巴还在**，
    #   否则"给开始界面加一项"会被这段切片静默吃掉。
    # [EN] ⚠ The start screen's last item is 「归　去」 and the tray calls it 「完全退出」
    # [EN] (plus 「显示主界面」 on top). Those two deliberately differ: the tray entry ignores the
    # [EN] config and always really exits, so it isn't called "Leave". => Drop the start screen's tail
    # [EN] when comparing, but **pin that the tail is there first**, or "add an item to the start
    # [EN] screen" would be silently swallowed by the slice.
    tail_ok = bool(started) and started[-1] == '归　去'
    rec('E01 ★★★ 托盘菜单那一段的标题与顺序 == 开始界面 `menu_items`'
        '（2026-10-31：手抄漏了「开　卷」、把「拾　卷」的说明当标题、丢了「起　笔」）',
        tail_ok and started[:-1] == mirrored,
        f'开始界面={started}｜托盘常量={mirrored}')

    # 真正跑一遍 `tray_menu_spec`，取"显示主界面"之后、"完全退出"之前的那一段
    spec = [i for i in G.tray_menu_spec(has_current=True, n_books=1,
                                        tray_ready=True) if not i.get('sep')]
    keys = [i['key'] for i in spec]
    body = spec[1:-1]              # 去掉「显示主界面」与「完全退出」
    rec('E02 ★★★ 真清单里也一模一样（顺序 + 文案），不是只有常量对',
        [i['text'] for i in body] == mirrored,
        f'清单={[i["text"] for i in body]}')
    rec('E03 ★★ 每一项都**只出现一次**（防"拾卷 + 打开以前的故事"这种同一动作两个入口）',
        len(keys) == len(set(keys)), keys)

    # 每个 key 都必须有接收方：菜单里点了没反应，比菜单里少一项更糟
    run_fn = _fn('_tray_run')
    disp: dict[str, str] = {}
    for n in ast.walk(run_fn or ast.Module(body=[], type_ignores=[])):
        if (isinstance(n, ast.Assign)
                and any(getattr(tg, 'id', '') == 'dispatch' for tg in n.targets)
                and isinstance(n.value, ast.Dict)):
            for k, v in zip(n.value.keys, n.value.values):
                if isinstance(k, ast.Constant):
                    disp[str(k.value)] = (ast.get_source_segment(GUI_SRC, v) or '')
    want = [x[0] for x in (G.TRAY_START_ITEMS + G.TRAY_SETTING_ITEMS)]
    rec('E04 ★★★ 清单里每个 key 都接上了处理函数（点了不能没反应）',
        all(k in disp for k in want), f'缺={[k for k in want if k not in disp]}｜有={sorted(disp)}')
    rec('E05 ★★ 「开　卷」接的是 `_on_new_story`（导入小说文件夹，不是拾卷）',
        'self._on_new_story' in disp.get('open', ''), disp.get('open', ''))


# ══════════════════════════════════════════════════════════════════
#  B 组 · 接线（AST）
# [EN] Group B · wiring, read from the AST
# ══════════════════════════════════════════════════════════════════
KEY_FUNCS = ('_tray_start', '_tray_stop', '_tray_show', '_tray_run',
             '_request_close', '_really_exit', '_hide_to_tray',
             '_on_window_event', '_on_exit', '_tray_attach_close_guard')


def group_b() -> None:
    # B0 先查"同名定义静默覆盖"：这些名字在模块里**必须只有一个**定义，
    #    否则改的那个可能永远不生效（项目里踩过：booklab 两个 `_overlap`）。
    dup = {n: len(_defs(n)) for n in KEY_FUNCS if len(_defs(n)) != 1}
    rec('B00 关键函数名各只有一个定义（防"同名静默覆盖"）', not dup, dup)

    main_fn = _fn('main')
    rec('B01 `main()` 里起了托盘（否则图标永远不会出现）',
        _has_call(main_fn, '_tray_start'), 'main 里没找到 _tray_start()')

    guard = _fn('_tray_attach_close_guard')
    rec('B02 接管关窗时**两件都做**了：prevent_close + window.on_event',
        guard is not None
        and 'prevent_close' in (ast.get_source_segment(GUI_SRC, guard) or '')
        and 'on_event' in (ast.get_source_segment(GUI_SRC, guard) or ''))

    start_fn = _fn('_tray_start')
    src_start = ast.get_source_segment(GUI_SRC, start_fn) or ''
    rec('B03 ★ `_tray_attach_close_guard()` 只在 `if ok:` 里调 —— 图标没起来就**不许拦关窗**',
        _calls_inside_if(start_fn, '_tray_attach_close_guard'),
        '无条件调用 ⇒ 图标没起来时点 × 关不掉')

    exit_fn = _fn('_on_exit')
    rec('B04 「归去」走 `_request_close`（与 × 同一条决策路）', _has_call(exit_fn, '_request_close'),
        ast.get_source_segment(GUI_SRC, exit_fn) or '')

    req = _fn('_request_close')
    rec('B05 `_request_close` 先问 `resolve_close`', _has_call(req, 'resolve_close'))
    rec('B06 `_request_close` 会 `_hide_to_tray`', _has_call(req, '_hide_to_tray'))
    rec('B07 ★ 藏失败要落回 `_really_exit`（"关不掉"比"退出了"严重得多）',
        _has_call(req, '_really_exit'))

    really = _fn('_really_exit')
    stop_lines = _call_lines(really, '_tray_stop')
    destroy_lines = _call_lines(really, 'destroy')
    rec('B08 ★ `_tray_stop()` 在 `destroy()` **之前**（之后那段代码根本不执行 ⇒ 残影）',
        bool(stop_lines) and bool(destroy_lines) and min(stop_lines) < min(destroy_lines),
        f'tray_stop={stop_lines} destroy={destroy_lines}')
    rec('B09 真退出前补一次落盘（`_stop_autosave`）',
        _has_call(really, '_stop_autosave'))

    hide = _fn('_hide_to_tray')
    rec('B10 ★ 藏窗口前必须落盘（`on_disconnect` 不会来）',
        _has_call(hide, '_stop_autosave'),
        '藏窗口连接还在，不落盘就是"这段时间白写"')

    rec('B11 ★ `_tray_show` 只发 `visible`，**不给** `maximized` 赋值（否则"最大化但不可见"）',
        not _assigns_attr(_fn('_tray_show'), 'maximized'),
        '同批设 maximized 会复现 2026-10-24 那个"闪一下就没"')

    # ⚠ 用 AST 找 `on_disconnect` 这个**函数**里有没有 `_tray_stop()` 调用。
    #   第一版是 `GUI_SRC.split('def on_disconnect')[1][:2000]` 的文本窗口 —— 假绿：
    #   那 2000 个字符会把后面别处的 `_tray_stop` 也扫进来，于是"这一刀砍掉了
    #   清理点，判据还是绿"。**窗口宽度不是判据**，作用域才是。
    # [EN] Use the AST: does the `on_disconnect` **function** call `_tray_stop()`?
    # [EN] v1 used a 2000-char text window after `def on_disconnect` -- falsely green: the
    # [EN] window swept in `_tray_stop` occurrences from elsewhere, so removing the cleanup
    # [EN] point still passed. A window width is not a criterion; scope is.
    rec('B12 `on_disconnect` 里摘托盘（进程被外面杀掉时的唯一清理点）',
        _has_call(_fn('on_disconnect'), '_tray_stop'), '断开时没有 _tray_stop()')

    menu_fn = _fn('_tray_menu')
    rec('B13 `_tray_menu` 用 `tray_menu_spec`（清单只有一处实现）',
        _has_call(menu_fn, 'tray_menu_spec'))

    rec('B14 `_tray_run` 里 exit 走 `_really_exit`，且**不看配置**（托盘里那一项永远真退出）',
        _has_call(_fn('_tray_run'), '_really_exit')
        and 'close_action' not in (ast.get_source_segment(GUI_SRC, _fn('_tray_run')) or ''))

    rec('B15 托盘模块用 GetMessageW 循环，**没有** `PumpMessage`（第一版就栽在它只处理一条消息）',
        'GetMessageW' in TRAY_SRC and 'PumpMessage()' not in TRAY_SRC,
        'PumpMessage 只处理一条消息 ⇒ 图标闪一下就没')

    rec('B16 托盘模块处理 `TaskbarCreated`（explorer 重启后图标会消失）',
        'TaskbarCreated' in TRAY_SRC)

    rec('B17 天机保存时写了 `CLOSE_ACTION`（只画控件不落盘 = 假旋钮）',
        "CFG.set('CLOSE_ACTION'" in GUI_SRC)

    # SPEC 里的那一项：**用 AST 读** `dict(...)` 的关键字实参（文本正则会把
    # 注释里的同名文字也算进来，而且 `default="exit"` 与 `"default": "exit"` 是两种写法）。
    # [EN] Read the SPEC entry with the AST: text regexes count comment text and the two
    # spellings (`default="exit"` vs `"default": "exit"`) differ.
    spec_ok, spec_detail = False, '没找到 CLOSE_ACTION'
    try:
        cfg_tree = ast.parse(CFG_SRC)
        for n in ast.walk(cfg_tree):
            # ⚠ `SPEC` 在 config.py 里是**带注解**的赋值（`SPEC: dict[...] = {...}`）
            #   ⇒ 节点是 `AnnAssign` 而不是 `Assign`。第一版只认 `Assign`，
            #   于是"没找到 CLOSE_ACTION"—— 假红，而表里明明写着。
            # [EN] `SPEC` is an **annotated** assignment (`AnnAssign`), not `Assign`; v1 only
            #   looked for `Assign` and reported "not found" -- a false red.
            tgt = None
            if isinstance(n, ast.Assign):
                if any(getattr(x, 'id', '') == 'SPEC' for x in n.targets):
                    tgt = n.targets[0]
            elif isinstance(n, ast.AnnAssign):
                if getattr(n.target, 'id', '') == 'SPEC':
                    tgt = n.target
            if tgt is None or not isinstance(n.value, ast.Dict):
                continue
            for k, v in zip(n.value.keys, n.value.values):
                if (isinstance(k, ast.Constant) and k.value == 'CLOSE_ACTION'
                        and isinstance(v, ast.Call)):
                    kw = {a.arg: a.value for a in v.keywords if a.arg}
                    dv = getattr(kw.get('default'), 'value', None)
                    opts = [getattr(e, 'value', None)
                            for e in getattr(kw.get('opt'), 'elts', []) or []]
                    spec_ok = (dv == 'exit' and 'exit' in opts and 'tray' in opts)
                    spec_detail = f'default={dv} opt={opts}'
    except Exception as e:                                # noqa: BLE001
        spec_detail = f'AST 读 SPEC 失败：{e}'
    rec('B18 SPEC 里有 CLOSE_ACTION：默认 exit、两个档位齐全', spec_ok, spec_detail)


# ══════════════════════════════════════════════════════════════════
#  C 组 · 真托盘
# [EN] Group C · a real tray
# ══════════════════════════════════════════════════════════════════
def group_c() -> tuple:
    from util import tray as TRAY
    rec('C01 这台机器支持托盘（非 Windows 上这条会红，属正常）', TRAY.available())
    if not TRAY.available():
        return None, []
    icon = APP / 'assets' / 'app_icon.ico'
    rec('C02 图标文件在（窗口/任务栏用的同一份 `app_icon.ico`）', icon.exists(), str(icon))
    cmds: list[str] = []
    t = TRAY.TrayIcon(icon_path=icon, tooltip='判据 · 托盘',
                      menu=lambda: [TRAY.MenuItem(key='show', text='显示主界面',
                                                  default=True),
                                    TRAY.MenuItem(sep=True),
                                    TRAY.MenuItem(key='exit', text='完全退出')],
                      on_command=cmds.append, on_activate=lambda: cmds.append('show'))
    ok = t.start()
    rec('C03 `start()` 返回 True（NIM_ADD 成功）', ok)
    # ⚠ 睡 0.3 秒再读 `running`：`start()` 只等到"窗口建好、NIM_ADD 成功"，而
    #   消息循环是紧接着跑的 —— 若它立刻退出（第一版用 `PumpMessage` 就是这样），
    #   不睡这一下会读到"还在"，判据就成了假绿。
    # [EN] Sleep 0.3s before reading `running`: `start()` only waits for the window + NIM_ADD,
    # and the message loop starts right after -- if it exits immediately (as v1 did with
    # `PumpMessage`) reading at once reports "alive" and the criterion is falsely green.
    time.sleep(0.3)
    rec('C04 `running` 为真（窗口句柄 + 线程都在）', t.running)
    # 菜单**能被建出来**（弹出的那一瞬间要用户点，自动化测不到；建得出来就说明
    # 清单→Win32 那一步没错，剩下的 "TrackPopupMenu 阻塞" 是系统行为）。
    try:
        hmenu, mapping = t._build_menu()
        built = bool(hmenu) and mapping.get(1) == 'show' and len(mapping) == 2
    except Exception as e:                                # noqa: BLE001
        built, mapping = False, e
    rec('C05 菜单建得出来：hmenu 非 0，id→命令的映射对得上（id 从 1 开始）',
        built, mapping)
    # 幂等：已在跑时再 start 一次，不许起第二颗
    rec('C06 `start()` 幂等（第二次直接 True，不起第二颗）',
        t.start() is True and t.running)
    t.stop()
    rec('C07 `stop()` 之后 running 为假', not t.running)
    t.stop()
    rec('C08 重复 `stop()` 无害（退出流程里会调好几次）', not t.running)
    return t, cmds


# ══════════════════════════════════════════════════════════════════
#  D 组 · 真窗口（藏得住 / 叫得回）
# [EN] Group D · a real window (hides / comes back)
# ══════════════════════════════════════════════════════════════════
def win_state(title: str) -> str:
    """从**外面**读窗口可见性（`IsWindowVisible`）。

    ⚠ 不能读 `page.window.visible`：那是我们发出去的请求值 —— 发了 False 读回来
      就是 False，哪怕窗口还在屏幕上。这条判据要的是系统的事实。
    [EN] Read visibility from outside; `page.window.visible` is the request, not the fact.
    """
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _l):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if title in buf.value:
                found.append(int(hwnd))
        return True

    user32.EnumWindows(_cb, 0)
    if not found:
        return '不在'
    return '可见' if user32.IsWindowVisible(found[0]) else '不可见'


async def group_d(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp
    from util import tray as TRAY

    rec('D01 窗口起来了且看得见', win_state(TITLE) == '可见', win_state(TITLE))
    if win_state(TITLE) != '可见':
        return

    try:
        app = NovelWorldApp()
    except Exception:                                     # noqa: BLE001
        rec('D02 能构造 App 实例（判据要驱动真的产品方法）', False,
            traceback.format_exc(limit=3))
        return
    app.page = page
    icon = APP / 'assets' / 'app_icon.ico'
    tray = TRAY.TrayIcon(icon_path=icon, tooltip='判据 · 窗口',
                         menu=lambda: [TRAY.MenuItem(key='show', text='显示主界面',
                                                     default=True)],
                         on_command=lambda k: None, on_activate=lambda: None)
    tray_ok = tray.start() if TRAY.available() else False
    app._tray = tray                    # ⚠ 先挂上再判 `tray_ready()`（它读的就是这个字段）
    rec('D02 起了一颗真图标给 App 用（`tray_ready()` 因此为真）',
        bool(tray_ok and app.tray_ready()), f'tray_ok={tray_ok}')

    # ⚠ 用 mock 顶掉 `close_action`，**不写用户 .env**。
    with mock.patch('gui.app_flet.close_action', return_value='tray'):
        await app._request_close()
    await asyncio.sleep(0.8)
    hidden = win_state(TITLE)
    rec('D03 ★ 配置=tray + 图标在 ⇒ 点关闭后窗口**真的**藏起来了',
        hidden == '不可见', hidden)
    alive = True
    try:
        page.update()
    except Exception:                                     # noqa: BLE001
        alive = False
    rec('D04 藏起来之后进程还活着（窗口连接还在 ⇒ 程序没退）', alive)

    await app._tray_show()
    await asyncio.sleep(0.8)
    back = win_state(TITLE)
    rec('D05 ★ 点托盘图标能把它**叫回来**（`IsWindowVisible` 又变 1）',
        back == '可见', back)

    # 图标不在时必须落回退出 —— 只测决策（真退出会把判据进程带走）
    with mock.patch('gui.app_flet.close_action', return_value='tray'):
        app._tray = None
        verdict = None

        async def _fake_exit():
            nonlocal verdict
            verdict = 'exit'

        real = app._really_exit
        app._really_exit = _fake_exit        # 只验证"会不会走到退出"
        try:
            await app._request_close()
        finally:
            app._really_exit = real
    rec('D06 ★ 配置=tray 但图标不在了 ⇒ 走的是**退出**（不是藏）',
        verdict == 'exit' and win_state(TITLE) == '可见',
        f'verdict={verdict} 窗口={win_state(TITLE)}')

    tray.stop()
    rec('D07 判据自己的图标摘干净了（不留残影）', not tray.running)


# ══════════════════════════════════════════════════════════════════
def main(page: ft.Page) -> None:
    page.title = TITLE
    page.window.width = 900
    page.window.height = 600
    page.add(ft.Text('托盘判据运行中…'))
    page.update()

    async def run() -> None:
        try:
            group_a()
            group_e()
            group_b()
            group_c()
            await asyncio.sleep(0.5)
            await group_d(page)
        except Exception:                                 # noqa: BLE001
            rec('判据自身没崩', False, traceback.format_exc(limit=5))
        code = finish({'checks': results}, out_path=REPORT, label='断言')
        await shutdown(page, code=code)

    page.run_task(run)


if __name__ == '__main__':
    ft.run(main, assets_dir=str(APP / 'assets'))
