# -*- coding: utf-8 -*-
"""验证：设窗口图标时**只碰自己的窗口**，绝不改到别人。

用户 2026-10-07 报的：

> 我发现为何 explorer.exe 的图标也被替换了 你看下是怎么回事

## 查出来的根因（本判据要挡住的就是它）

`find_app_hwnd()` 的兜底是「标题里含 `VERSION`（= "0.1.0"）/ `Novel World` /
`小说世界` 的窗口 → 收集起来 → **取第一个**」；下游 `apply_icon_to_hwnd()` 里有

    SetClassLongPtrW(hwnd, GCLP_HICON / GCLP_HICONSM, hicon)

**那改的是窗口【类】图标 —— 会波及那个进程里所有同类窗口。**
于是命中谁就换谁一整类。本机实测会命中的非本程序窗口：

  · 文件夹窗口（类 `CabinetWClass`，属 **explorer.exe**）—— 用户打开
    `小说世界虚拟模拟` 文件夹时窗口标题就含「小说世界」
    ⇒ 改了它 = **资源管理器（含任务栏那个）图标全变**
  · Windows 终端（类 `CASCADIA_HOSTING_WINDOW_CLASS`）—— 标题跟着工作目录走

## 检查什么

A 纯判定 `should_take_window(cls, title, own)`（零窗口）
  · 三把锁的各种组合：**只有三项皆中才 True**
  · 文件夹窗口 / 终端 / 别人的 Flet 程序（类名撞了）→ 一律 False
  · `_OWN_TITLE_MARKS` 里**不许有版本号**（拿 `0.1.0` 当标识谁都会中）
B 真机（MOCK，起真窗口）
  · `find_app_hwnd()` 仍然找得到自己的窗口（**别把功能一并修坏了**）
  · 它返回的窗口 `is_own_window` 为真、窗口类是 Flet 的
  · 把**全机所有可见窗口**喂进判定：被接受的**只能是我们自己的**
  · 拒绝护栏：拿一个真·别人的窗口调 `apply_icon_to_hwnd` → 返回 0、一字不改
C 源码级
  · 护栏 `is_own_window` 必须排在 `SetClassLongPtrW` **之前**（按 AST 行号）
  · `find_app_hwnd` 里不许再出现 `VERSION in txt`
  · `FindWindowW.restype` 是 `c_void_p`（句柄别被 ctypes 按 32 位截）

跑法：
    .venv\\Scripts\\python.exe tools\\verify_window_icon_target.py
    .venv\\Scripts\\python.exe tools\\verify_window_icon_target.py --logic-only
产出：
    assets/screenshots/window_icon_target_report.json

English:
Verify: when setting the window icon **only touch our own window**, never change someone else's.
Reported by user 2026-10-07:
> I found out why explorer.exe's icon also got replaced. Take a look at what's going on
## Root cause found (this is exactly what the criterion must block)
`find_app_hwnd()`'s fallback is "windows whose title contains `VERSION` (= "0.1.0") / `Novel
World` /
`小说世界` → collect them → **take the first**"; downstream in `apply_icon_to_hwnd()` there is
    SetClassLongPtrW(hwnd, GCLP_HICON / GCLP_HICONSM, hicon)
**That changes the window [class] icon —— it affects all windows of the same class in that
process.**
So whoever it hits, it swaps that entire class. Non-app windows on this machine that actually
get hit:
  · Folder windows (class `CabinetWClass`, belonging to **explorer.exe**) —— when the user opens
    ⇒ changing it = **the Explorer (including the one on the taskbar) icon all change**
  · Windows Terminal (class `CASCADIA_HOSTING_WINDOW_CLASS`) —— the title follows the working directory
## What to check
A pure decision `should_take_window(cls, title, own)` (zero windows)
  · various combinations of the three locks: **only True when all three hit**
  · folder windows / terminal / someone else's Flet app (class name collides) → all False
  · `_OWN_TITLE_MARKS` must **not contain a version number** (using `0.1.0` as a marker would hit everyone)
B real machine (MOCK, spawn real windows)
  · `find_app_hwnd()` can still find its own window (**don't break the feature along with it**)
  · the window it returns has `is_own_window` true, and the window class is Flet's
  · feed **all visible windows on the machine** into the decision: the ones accepted **can only be our own**
  · rejection guardrail: call `apply_icon_to_hwnd` with a real·someone else's window → returns 0, changes nothing
C source level
  · the guardrail `is_own_window` must come **before** `SetClassLongPtrW` (by AST line number)
  · `find_app_hwnd` must no longer contain `VERSION in txt`
  · `FindWindowW.restype` is `c_void_p` (so the handle isn't truncated to 32 bits by ctypes)
How to run:
    .venv\\Scripts\\python.exe tools\\verify_window_icon_target.py
    .venv\\Scripts\\python.exe tools\\verify_window_icon_target.py --logic-only
Output:
    assets/screenshots/window_icon_target_report.json
"""
from __future__ import annotations

import ast
import asyncio
import ctypes
import inspect
import json
import os
import sys
import textwrap
import traceback
from ctypes import wintypes
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

_ITEMS: list[dict] = []


def ok(name: str, cond, detail: str = '') -> bool:
    good = bool(cond)
    _ITEMS.append({'name': name, 'ok': good, 'detail': str(detail)[:240]})
    print(f'  [{"OK" if good else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))
    return good


def head(text: str) -> None:
    print(f'\n{"=" * 68}\n {text}\n{"=" * 68}')


# ══════════════════════════════════════════════════════════════
#  A. 纯判定
# [EN] A. Pure logic
# ══════════════════════════════════════════════════════════════
def test_logic() -> bool:
    head('A. 纯判定 should_take_window(cls, title, own)')
    from gui.app_flet import (should_take_window, _FLET_WINDOW_CLASS,
                              _OWN_TITLE_MARKS)
    from config import VERSION
    good = True
    FLET = _FLET_WINDOW_CLASS

    ok('A0 前提：Flet 的窗口类名就是实测到的那一个',
       FLET == 'FLUTTER_RUNNER_WIN32_WINDOW', FLET)

    good &= ok('A1 ★★ 我们自己的窗口 → 接受（三个条件全中）',
               should_take_window(FLET, '小说世界AI模拟 v0.1.0 · 界面 23:05', True)
               and should_take_window(FLET, 'Novel World AI Simulator', True),
               '')
    good &= ok('A2 ★★★ 文件夹窗口（`CabinetWClass`，属 explorer.exe）→ **拒绝**'
               '（用户报的"explorer.exe 图标被换"就是漏了这条）',
               not should_take_window('CabinetWClass', '小说世界虚拟模拟', False), '')
    good &= ok('A3 ★★★ Windows 终端（`CASCADIA_HOSTING_WINDOW_CLASS`）→ 拒绝',
               not should_take_window('CASCADIA_HOSTING_WINDOW_CLASS',
                                      '小说世界AI模拟 / Novel World AI Simulator',
                                      False), '')
    good &= ok('A4 ★★★ **别人的 Flet 程序**（窗口类名一样）→ 拒绝'
               '（实测本机 `Abysswalker.exe` 也用这个类名 —— 光靠类名不够）',
               not should_take_window(FLET, '小说世界AI模拟', False), '')
    good &= ok('A5 ★★ 就算进程是我们的，窗口类不对也拒绝',
               not should_take_window('Notepad', '小说世界', True), '')
    good &= ok('A6 ★ 标题里没有我们的字样 → 拒绝',
               not should_take_window(FLET, 'Untitled', True), '')
    good &= ok('A7 ★★ 标题里只有版本号 → 拒绝'
               '（上一版拿 `VERSION` 当标识，谁标题带 `0.1.0` 都会中）',
               not should_take_window('CabinetWClass', f'某工具 {VERSION}', False)
               and VERSION in f'某工具 {VERSION}', f'VERSION={VERSION}')
    good &= ok('A8 空类名 / 空标题 / 空标题串 → 拒绝',
               not should_take_window('', '小说世界', True)
               and not should_take_window(FLET, '', True)
               and not should_take_window(FLET, None, True), '')
    good &= ok('A9 ★★ 标题标识里**不许出现版本号**'
               '（`_OWN_TITLE_MARKS` 是"像我们的窗口"的唯一凭据，它得是专名）',
               not any(VERSION in m for m in _OWN_TITLE_MARKS),
               str(_OWN_TITLE_MARKS))
    return good


# ══════════════════════════════════════════════════════════════
#  C. 源码级
# [EN] C. Source-level
# ══════════════════════════════════════════════════════════════
def test_source() -> bool:
    head('C. 源码级')
    import gui.app_flet as A
    good = True

    src = textwrap.dedent(inspect.getsource(A.apply_icon_to_hwnd))
    tree = ast.parse(src)
    fn = tree.body[0]
    guard_ln = None
    guard_return_ln = None          # 护栏那个 `if` 里**真的 return** 的行号
    # [EN] The line number where the guard `if` **actually returns**
    effect_lns: list[int] = []
    # ⚠ `SetClassLongPtrW` 在源码里是 `getattr(u32, 'SetClassLongPtrW', None)`
    #   **动态取**的 —— AST 里根本没有这个名字（第一版判据就栽在这，
    #   报 `set@None` 假红）。所以按**会改图标的那些调用**来定位：
    # [EN] ⚠ `SetClassLongPtrW` appears in the source as `getattr(u32, 'SetClassLongPtrW', None)`
    #   LoadImageW / SendMessageW(WM_SETICON) / `_setclass(...)`。
    _EFFECTS = {'LoadImageW', 'SendMessageW', '_setclass', 'SetClassLongW'}
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            attr = getattr(n.func, 'attr', '') or getattr(n.func, 'id', '')
            if attr == 'is_own_window' and guard_ln is None:
                guard_ln = n.lineno
            if attr in _EFFECTS:
                effect_lns.append(n.lineno)
        # 护栏那个 if：test 里有 is_own_window，body 里必须有 return
        # [EN] That guardrail if: test has is_own_window, body must have return
        if isinstance(n, ast.If):
            ids = {x.id for x in ast.walk(n.test) if isinstance(x, ast.Name)}
            if 'is_own_window' in ids:
                rets = [x.lineno for x in ast.walk(n)
                        if isinstance(x, ast.Return)]
                if rets:
                    guard_return_ln = min(rets)
    set_ln = min(effect_lns) if effect_lns else None
    good &= ok('C1 ★★★ `apply_icon_to_hwnd` 里**真的有**拒绝护栏（调 `is_own_window`）',
               guard_ln is not None, f'guard@{guard_ln}')
    good &= ok('C2 ★★★ 护栏**真的拦**（那个 `if` 里直接 `return 0`）'
               '**且排在任何会动的语句之前**'
               '（只"检查一下"却不返回 = 等于没护栏，反例法 ⑥ 专门打这条）',
               guard_return_ln is not None and set_ln is not None
               and guard_return_ln < set_ln,
               f'guard-return@{guard_return_ln} effect@{sorted(effect_lns)}')
    good &= ok('C3 ★★ 护栏拒绝时**直接返回**（不往下走 LoadImage / SendMessage）',
               'return 0,' in src and '拒绝' in src, '')

    fsrc = textwrap.dedent(inspect.getsource(A.find_app_hwnd))
    good &= ok('C4 ★★★ `find_app_hwnd` 里**不再拿版本号当标识**'
               '（`VERSION in txt` 是上一版的错）',
               'VERSION in' not in fsrc, '')
    good &= ok('C5 ★★ 兜底那道过滤**真的走** `should_take_window`'
               '（三道锁只有一处实现）',
               'should_take_window' in fsrc, '')

    # ⚠ C6 必须**按分支定位**：`find_app_hwnd` 的函数体里别处也调
    #   `is_own_window`（兜底那一路），所以"整段源码里有没有这个词"是假绿
    #   —— 反例法 ⑧ 当场揭穿过。用 AST 找 `if title:` 那个 If，
    #   只认**它的 body** 里有没有校验。
    # [EN] ⚠ C6 must be **located by branch**: `find_app_hwnd`'s function body also calls it elsewhere
    # [EN] `is_own_window` (the fallback path), so "does this word appear anywhere in the whole source" is
    # [EN] a false green
    # [EN] —— the counterexample method ⑧ exposed this on the spot. Use AST to find that `if title:` If,
    # [EN] only recognize whether **its body** contains the check.
    _ft = ast.parse(fsrc)
    _exact_guard = False
    for _n in ast.walk(_ft.body[0]):
        if isinstance(_n, ast.If):
            names = {x.id for x in ast.walk(_n.test) if isinstance(x, ast.Name)}
            if 'title' not in names:
                continue
            for _c in ast.walk(_n):
                if isinstance(_c, ast.Call) and (
                        getattr(_c.func, 'attr', '') or
                        getattr(_c.func, 'id', '')) == 'is_own_window':
                    _exact_guard = True
    good &= ok('C6 ★★ **精确查那条分支**（`if title: FindWindowW(...)`）也校验归属'
               '（标题不是身份 —— 别人的窗口也可能用同一个标题）',
               _exact_guard, '')

    dsrc = textwrap.dedent(inspect.getsource(A._u32_decls))
    good &= ok('C7 ★★ `FindWindowW.restype` 声明成 `c_void_p`'
               '（句柄 > 0x7FFFFFFF 时按默认 `c_int` 会变成负数）',
               'FindWindowW.restype' in dsrc and 'c_void_p' in dsrc, '')
    # ⚠ C8 也要精确到**那两行**：`_u32_decls` 里别处也用 `c_ssize_t`
    #   （`SendMessageW.restype`），所以"整段里有没有 c_ssize_t"同样是假绿
    #   —— 反例法 ⑩ 揭穿过。
    # [EN] ⚠ C8 must also be precise to **those two lines**: `_u32_decls` also uses `c_ssize_t` elsewhere
    # [EN] (`SendMessageW.restype`), so "is there c_ssize_t anywhere in the whole thing" is likewise a
    # [EN] false green
    # [EN] —— the counterexample method ⑩ exposed this.
    good &= ok('C8 ★ `SetClassLongPtrW` 的签名**那两行**都声明了'
               '（LONG_PTR 是 64 位，不声明就按 32 位传）',
               '_set.argtypes' in dsrc and '_set.restype' in dsrc
               and 'c_ssize_t' in dsrc, '')
    return good


# ══════════════════════════════════════════════════════════════
#  B. 真机
# [EN] B. Real machine
# ══════════════════════════════════════════════════════════════
def _enum_visible() -> list[dict]:
    from gui.app_flet import (_u32_decls, _win32, process_exe, hwnd_class,
                              hwnd_pid, hwnd_title)
    d = _u32_decls()
    w = _win32()
    if not d or not w:
        return []
    u32 = d[0]
    ctypes_, wintypes_ = w
    rows: list[dict] = []

    def _cb(h, _l):
        if not u32.IsWindowVisible(h):
            return True
        hid = int(h)
        rows.append({'hwnd': hid, 'cls': hwnd_class(hid),
                     'title': hwnd_title(hid), 'pid': hwnd_pid(hid)})
        return True

    proc = ctypes_.WINFUNCTYPE(ctypes_.c_bool, wintypes_.HWND, wintypes_.LPARAM)
    u32.EnumWindows(proc(_cb), 0)
    for r in rows:
        r['exe'] = process_exe(r['pid']) if r['pid'] else ''
    return rows


async def test_gui(page) -> bool:
    from gui.app_flet import (NovelWorldApp, apply_icon_to_hwnd, find_app_hwnd,
                              get_window_icon_ico, is_own_window, hwnd_class,
                              hwnd_pid, hwnd_title, should_take_window,
                              _FLET_WINDOW_CLASS, _parent_pid)

    head('B. 真机（MOCK，起真窗口）')
    good = True
    app = NovelWorldApp()
    app.main(page)
    page.window.width = 1260
    page.window.height = 860
    page.update()
    await asyncio.sleep(3.0)

    me = os.getpid()
    print(f'  本进程 pid={me}  page.title={page.title!r}')

    # ── B1~B3 还能找得到自己的窗口吗（别把功能一并修坏）──
    # [EN] ── Can B1~B3 still find its own window (don't break the feature along with it) ──
    hwnd = find_app_hwnd()
    good &= ok('B1 ★★★ 改完之后**仍然找得到**自己的窗口'
               '（找不到 = 图标设不上，那是把功能修坏了）',
               bool(hwnd), f'hwnd={hwnd}')
    if not hwnd:
        return good
    cls = hwnd_class(hwnd)
    pid = hwnd_pid(hwnd)
    good &= ok('B2 ★★★ 找到的那个窗口**确实是我们的**（`is_own_window` 为真）',
               is_own_window(hwnd),
               f'类={cls} pid={pid} 父={_parent_pid(pid)}')
    good &= ok('B3 ★★ 而且窗口类是 Flet 的', cls == _FLET_WINDOW_CLASS, cls)
    good &= ok('B4 ★★ 归属判定认得出来：pid 是本进程，或是本进程起的 flet.exe',
               pid == me or _parent_pid(pid) == me,
               f'pid={pid} me={me} 父={_parent_pid(pid)}')

    # ── B5 全机窗口喂进判定：接受的只能是我们自己的 ──
    # [EN] ── B5 feed all machine windows into the decision: the only ones accepted can be our own ──
    rows = _enum_visible()
    accepted = [r for r in rows
                if should_take_window(r['cls'], r['title'],
                                      is_own_window(r['hwnd']))]
    strangers = [r for r in accepted if r['cls'] != _FLET_WINDOW_CLASS]
    print(f'  全机可见窗口 {len(rows)} 个，判定接受 {len(accepted)} 个')
    for r in accepted:
        print(f'    ✔ hwnd={r["hwnd"]} 类={r["cls"]} 标题={r["title"]!r}')
    good &= ok('B5 ★★★ **全机窗口**里被接受的，窗口类都是 Flet 的'
               '（一个别的进程都没有）',
               not strangers,
               str([(r['cls'], r['title'][:30]) for r in strangers]))
    good &= ok('B6 ★ 被接受的数量 ≤ 3（我们的主窗口就那么一两个，'
               '多出来说明判定松了）',
               len(accepted) <= 3, f'{len(accepted)} 个')

    # ── B7 拒绝护栏：拿真·别人的窗口试 ──
    # [EN] ── B7 rejection guardrail: try with a real·someone else's window ──
    skip = {'', 'Progman', 'Shell_TrayWnd', 'Windows.UI.Core.CoreWindow',
            'WorkerW', 'Shell_SecondaryTrayWnd'}
    stranger = next((r for r in rows
                     if r['cls'] not in skip and r['cls'] != _FLET_WINDOW_CLASS),
                    None)
    if stranger is None:
        print('  （本机当前没有可拿来做拒绝测试的窗口 —— 这条跳过）')
    else:
        ico = get_window_icon_ico()
        hid, why = apply_icon_to_hwnd(stranger['hwnd'], ico)
        good &= ok('B7 ★★★ 拿**一个真·别人的窗口**调 `apply_icon_to_hwnd`'
                   '→ 返回 0（一个字都没改）',
                   hid == 0,
                   f'目标 {stranger["cls"]} / {stranger["title"][:30]!r} → '
                   f'hicon={hid} why={why}')
        good &= ok('B8 ★ 而且说清了为什么（"拒绝：…不是本程序的窗口"）',
                   '拒绝' in str(why), str(why)[:120])

    # ── B9 证明老逻辑真的会误伤（现场取证，条件化）──
    # [EN] ── B9 prove the old logic really does false-positive (on-site evidence, conditionalized) ──
    from config import VERSION
    olds = [r for r in rows
            if (VERSION in (r['title'] or '')) or ('Novel World' in (r['title'] or ''))
            or ('小说世界' in (r['title'] or ''))]
    hurt = [r for r in olds if r['cls'] != _FLET_WINDOW_CLASS]
    print(f'  老逻辑会命中 {len(olds)} 个窗口，其中**非我们自己的** {len(hurt)} 个：')
    for r in hurt:
        print(f'    ★ {r["cls"]}  {r["title"][:40]!r}  ({r["exe"]})')
    if hurt:
        ok('B9 ★★★ 现场取证：老逻辑确实会命中**别人的窗口**'
           '（这就是"explorer.exe 图标被换"的来源）', True,
           f'{len(hurt)} 个，例如 {hurt[0]["cls"]}')
    else:
        print('  （当前没有开着这类窗口，取证跳过 —— 不算失败）')
    return good


# ══════════════════════════════════════════════════════════════
async def main(page) -> None:
    from util.flet_shutdown import shutdown
    good = True
    try:
        good &= test_logic()
        good &= test_source()
        good &= await test_gui(page)
    except BaseException:                                        # noqa: BLE001
        traceback.print_exc()
        _ITEMS.append({'name': '（执行中断）', 'ok': False,
                       'detail': traceback.format_exc()[-400:]})
        good = False
    n_ok = sum(1 for i in _ITEMS if i['ok'])
    print(f'\n{"-" * 68}\n  窗口图标归属：{n_ok}/{len(_ITEMS)}'
          + ('' if good else '   ← 有失败'))
    for i in _ITEMS:
        if not i['ok']:
            print(f'    ! {i["name"]}  [{i["detail"][:130]}]')
    (OUT / 'window_icon_target_report.json').write_text(
        json.dumps({'passed': n_ok, 'total': len(_ITEMS), 'ok': good,
                    'checks': _ITEMS}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    await shutdown(page, code=0 if good else 2)


if __name__ == '__main__':
    if '--logic-only' in sys.argv:
        a = test_logic()
        b = test_source()
        n = sum(1 for i in _ITEMS if i['ok'])
        print(f'\n  窗口图标归属（逻辑段）：{n}/{len(_ITEMS)}'
              + ('' if (a and b) else '   ← 有失败'))
        for i in _ITEMS:
            if not i['ok']:
                print(f'    ! {i["name"]}  [{i["detail"][:140]}]')
        sys.exit(0 if (a and b) else 2)
    import flet as ft
    ft.run(main)
