# -*- coding: utf-8 -*-
"""Windows 系统托盘图标（任务栏右下角那颗）—— 纯 ctypes，不引入第三方依赖。

为什么自己写
------------
Flet 1.0.3 **没有托盘 API**（`page.window` 只管窗口本身：显示/隐藏/最大化/图标）。
常见替代是 `pystray`，但它只是 pywin32 `Shell_NotifyIcon` 的一层封装，而本机
已经有 pywin32 —— 再多一个依赖，打包与"首次运行装环境"就多一处可能失败。
这里直接用 `ctypes` 调两个 DLL（user32 / shell32），约 300 行，可控。

工作机制（Win32 的规矩，不是我们的选择）
----------------------------------------
托盘图标不挂在"程序"上，它挂在**一个窗口句柄**上（`NOTIFYICONDATAW.hWnd`）。
所以：
  · 起一个**后台线程**，在它里面 `RegisterClass` + `CreateWindow`（隐藏窗口）；
  · `Shell_NotifyIcon(NIM_ADD)` 把图标挂到这个窗口上；
  · 这个线程跑 `PumpMessage` 消息循环，图标上的鼠标事件以
    `uCallbackMessage`（`WM_APP + 1`）送到窗口过程；
  · **窗口必须由创建它的线程处理消息** —— 所以"起图标"和"收菜单"必须在
    同一个线程里，不能图省事在界面线程建、在别处收。
  · 停：`WM_CLOSE` → `DestroyWindow` → `WM_DESTROY` 里 `NIM_DELETE` + `WM_QUIT`。

两个必须踩过的坑（都写进代码了）
--------------------------------
1. **`TrackPopupMenu` 前要 `SetForegroundWindow`，之后要 `PostMessage(WM_NULL)`**。
   漏了前者，菜单弹出来但**点别处不消失**（经典 bug，MSDN 的 KB135788 说的就是这个）。
2. **explorer.exe 重启后图标会消失**（登录/崩溃/桌面刷新）。系统会广播一个
   `RegisterWindowMessage("TaskbarCreated")`，必须收它并重新 `NIM_ADD`。
   不收就变成"用着用着图标没了，只能重启程序"。

与界面的边界
------------
这个模块**不认识 Flet，也不认识配置**：它只做三件事 —— 显示图标、弹出菜单、
把点击翻译成字符串命令交出去。**决策**（关窗还是退出、菜单里哪几项灰）全在
`gui/app_flet.py` 里，理由与那边 `resolve_close()` 的注释一致：
"同一件事只许一处实现"。

English:
Windows system-tray icon (the one in the bottom-right corner) -- plain ctypes, no new
third-party dependency.

Why hand-rolled
---------------
Flet 1.0.3 has **no tray API** (`page.window` only covers the window itself). The usual
stand-in is `pystray`, which is just a wrapper over pywin32's `Shell_NotifyIcon`, and pywin32
is already here -- one more dependency means one more thing that can fail at packaging time
and on a first run. This calls two DLLs (user32 / shell32) through `ctypes`: ~300 lines,
fully under control.

How it works (Win32's rules, not our choice)
--------------------------------------------
A tray icon is not attached to "the program"; it is attached to **a window handle**
(`NOTIFYICONDATAW.hWnd`). Therefore: start a **background thread**, in it `RegisterClass` +
`CreateWindow` (a hidden window); `Shell_NotifyIcon(NIM_ADD)` hangs the icon on that window;
the thread runs `PumpMessage`, and mouse events arrive at the window procedure as
`uCallbackMessage` (`WM_APP + 1`). **A window must be pumped by the thread that created it**,
so "start the icon" and "handle the menu" must live in the same thread.
Stop: `WM_CLOSE` -> `DestroyWindow` -> `WM_DESTROY` does `NIM_DELETE` + `WM_QUIT`.

Two traps that are handled here
-------------------------------
1. **`SetForegroundWindow` before `TrackPopupMenu`, `PostMessage(WM_NULL)` after.** Without the
   former the menu shows up but **does not dismiss when clicking elsewhere** (KB135788).
2. **The icon disappears when explorer.exe restarts.** The shell broadcasts
   `RegisterWindowMessage("TaskbarCreated")`; it must be received and `NIM_ADD` redone --
   otherwise "the icon vanished after a while, only restarting the app brings it back".

Boundary with the UI
--------------------
This module **knows nothing about Flet or the config**: it shows an icon, pops a menu, and
translates clicks into string commands. **Decisions** (close vs. exit, which entries are grey)
live in `gui/app_flet.py` -- same rule as `resolve_close()` there: one thing, one implementation.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# ── Win32 常量（用到哪几个就只写哪几个）──────────────────────────────
# [EN] ── Win32 constants (only the ones actually used) ──────────────────────────────
WM_APP = 0x8000
WM_NULL = 0x0000
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

MF_STRING = 0x00000000
MF_GRAYED = 0x00000001
MF_SEPARATOR = 0x00000800
MF_DEFAULT = 0x00001000

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IDI_APPLICATION = 32512

#: 图标点击的回调消息（自己定一个 WM_APP 之后的号码，别撞系统消息）。
# [EN] Callback message for icon clicks (an id past WM_APP; never collide with system messages).
CALLBACK_MSG = WM_APP + 21

#: 窗口类名（带 pid + id，避免同进程多次起、或多实例互相干扰）。
# [EN] Window class name (pid + id, so repeated starts / several instances never collide).
_CLASS_PREFIX = 'NwsTrayWnd'


@dataclass
class MenuItem:
    """托盘菜单的一项。

    `key` 是**交回界面的命令**（`'show'` / `'exit'` / `'pick'` …），不是数字 ——
    数字是 Win32 的约定，在模块内部映射，界面那一侧永远只见到字符串。
    `default` = 加粗（用户按回车或左键双击时的那一项，按 Win32 惯例只有一项）。
    `sep=True` 画一条分隔线（此时 `key` / `text` 都不用）。
    
        English:
    One entry of the tray menu. `key` is **the command handed back to the UI** (a string, not
    a number -- numbers are Win32's business and are mapped inside this module). `default`
    bolds the entry. `sep=True` draws a separator (`key` / `text` unused).
    """
    key: str = ''
    text: str = ''
    enabled: bool = True
    default: bool = False
    sep: bool = False


#: 菜单值的类型：一张"现取"的回调 —— 右键那一刻才问界面要（勾/灰会随书状态变）。
# [EN] Menu value type: a "fetch now" callback -- asked at the moment of right-click (states
# change with the project).
MenuFn = Callable[[], list[MenuItem]]


def available() -> bool:
    """这台机器**能不能**有托盘图标（非 Windows / 缺 DLL ⇒ False）。

    ⚠ 它只回答"平台支持吗"，**不回答"图标起来了吗"** —— 后者是 `TrayIcon.start()`
      的返回值。关窗行为必须按**后者**判：`available()` 为真但 `start()` 失败
      （图标文件坏了之类）时若还去藏窗口，用户就再也叫不出界面了。
    [EN] Whether this machine **can** have a tray icon (non-Windows / missing DLL => False).
    ⚠ It answers "does the platform support it", **not "did the icon come up"** -- the latter
    is `TrayIcon.start()`'s return value. The close behaviour must key off the latter: if
    `available()` is true but `start()` failed, hiding the window would leave the user with no
    way to bring the UI back.
    """
    if not sys.platform.startswith('win'):
        return False
    try:
        ctypes.windll.user32                      # noqa: B018  —— 只为探一下 DLL
        ctypes.windll.shell32                     # noqa: B018
    except Exception:                             # noqa: BLE001
        return False
    return True


def _load_win32():
    """把这一堆 Win32 结构体/原型装好，返回一个句柄包。**只应在 Windows 上调用**。"""
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class GUID(ctypes.Structure):
        _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD),
                    ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [('style', wintypes.UINT),
                    ('lpfnWndProc', WNDPROC),
                    ('cbClsExtra', ctypes.c_int),
                    ('cbWndExtra', ctypes.c_int),
                    ('hInstance', wintypes.HINSTANCE),
                    ('hIcon', wintypes.HICON),
                    ('hCursor', wintypes.HANDLE),
                    ('hbrBackground', wintypes.HBRUSH),
                    ('lpszMenuName', wintypes.LPCWSTR),
                    ('lpszClassName', wintypes.LPCWSTR)]

    class NOTIFYICONDATAW(ctypes.Structure):
        """完整版（V3）结构体。

        ⚠ **不能只定义到 `dwInfoFlags`**：Windows 按 `cbSize` 认结构版本，
          结构体被截短 + 传小 cbSize 时，新系统上的行为会随版本变（历史上踩过
          "能加图标、但气泡/提示不显示"）。这里宁可多写两个字段，尺寸一次到位。
        [EN] The full (V3) struct. ⚠ **Do not truncate at `dwInfoFlags`**: Windows keys the
        version off `cbSize`; a shortened struct plus a small cbSize behaves differently across
        versions ("icon adds fine, tooltip never shows" has been seen). Two extra fields are
        cheaper than that class of bug.
        """
        _fields_ = [('cbSize', wintypes.DWORD),
                    ('hWnd', wintypes.HWND),
                    ('uID', wintypes.UINT),
                    ('uFlags', wintypes.UINT),
                    ('uCallbackMessage', wintypes.UINT),
                    ('hIcon', wintypes.HICON),
                    ('szTip', wintypes.WCHAR * 128),
                    ('dwState', wintypes.DWORD),
                    ('dwStateMask', wintypes.DWORD),
                    ('szInfo', wintypes.WCHAR * 256),
                    ('uVersion', wintypes.UINT),
                    ('szInfoTitle', wintypes.WCHAR * 64),
                    ('dwInfoFlags', wintypes.DWORD),
                    ('guidItem', GUID),
                    ('hBalloonIcon', wintypes.HICON)]

    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR,
                                       wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                       wintypes.HINSTANCE, wintypes.LPVOID]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadIconW.restype = wintypes.HICON
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                   ctypes.c_size_t, wintypes.LPCWSTR]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                      wintypes.LPVOID]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                          ctypes.POINTER(NOTIFYICONDATAW)]

    return {
        'ctypes': ctypes,
        'wintypes': wintypes,
        'user32': user32,
        'shell32': shell32,
        'kernel32': kernel32,
        'WNDPROC': WNDPROC,
        'WNDCLASSW': WNDCLASSW,
        'NOTIFYICONDATAW': NOTIFYICONDATAW,
    }


class TrayIcon:
    """一颗托盘图标。

    用法（界面那侧）::

        tray = TrayIcon(icon_path=..., tooltip='小说世界AI模拟',
                        menu=self._tray_menu, on_command=self._tray_command,
                        on_activate=self._tray_activate)
        ok = tray.start()        # ← 只认这个返回值判断"图标到底起来没有"
        ...
        tray.stop()

    ⚠ `on_command` / `on_activate` 在**托盘线程**里被调用（不是界面线程）。它们
      必须只做"把活丢回界面线程"这一件事（本项目的写法是 `page.run_task(...)`，
      它内部是 `run_coroutine_threadsafe`，跨线程安全）。
      在这里做耗时工作会卡住图标（菜单弹不出来、提示不更新）。
    
        English:
    One tray icon. `ok = tray.start()` -- **judge "is the icon really up" by this value only**.
    ⚠ `on_command` / `on_activate` run on the **tray thread** (not the UI thread). They must
    only hand work back to the UI thread (`page.run_task(...)`, which is thread-safe); doing
    slow work here freezes the icon (menu won't pop, tooltip won't update).
    """

    def __init__(self, *, icon_path: str | Path, tooltip: str,
                 menu: MenuFn, on_command: Callable[[str], None],
                 on_activate: Callable[[], None] | None = None,
                 uid: int = 1):
        self.icon_path = str(icon_path or '')
        self.tooltip = (tooltip or '')[:120]
        self.uid = int(uid)
        self._menu = menu
        self._on_command = on_command
        self._on_activate = on_activate

        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._hwnd = 0
        self._hicon = 0
        self._win = None                     # _load_win32() 的返回值（含结构体与函数）
        self._wndproc = None                 # ⚠ 必须留引用：被 GC 掉窗口过程就崩
        self._taskbar_msg = 0
        self._ok = False

    # ── 对外 ────────────────────────────────────────────────────────
    @property
    def running(self) -> bool:
        """图标此刻**在不在**（不是"起过没有"）。"""
        return bool(self._hwnd) and bool(self._thread and self._thread.is_alive())

    @property
    def ready(self) -> bool:
        """`start()` 那次到底成没成（界面据此决定"能不能藏窗口"）。"""
        return bool(self._ok)

    def start(self, timeout: float = 3.0) -> bool:
        """起图标，返回**真的起来了没有**。幂等：已经在跑就直接返回 True。

        ⚠ 失败**不抛异常**：托盘是增强项，起不来最多是没有那颗图标，
          绝不能让程序起不来。调用方按返回值决定"关窗时藏不藏"。
        [EN] Start the icon; returns whether it **really came up**. Idempotent.
        ⚠ Never raises: the tray is an enhancement; the app must start without it. The caller
        uses the return value to decide "hide the window or not".
        """
        if self.running:
            return True
        if not available():
            return False
        self._ready.clear()
        self._ok = False
        self._thread = threading.Thread(target=self._run, name='nws-tray',
                                        daemon=True)
        self._thread.start()
        # 等它把窗口建好、NIM_ADD 成功（最多 timeout 秒）。
        # ⚠ 等的是"线程内那一段跑完"，不是"图标出现在屏幕上" —— 后者系统不给回调，
        #   而 NIM_ADD 返回 False 已经是最准的信号了。
        # [EN] Wait until the window is created and NIM_ADD succeeded. ⚠ We wait for that
        # section, not for the icon to appear on screen (the shell reports neither) --
        # NIM_ADD returning false is the most accurate signal available.
        self._ready.wait(timeout)
        return self.ready

    def stop(self, timeout: float = 2.0) -> None:
        """摘掉图标并让托盘线程退出。**重复调用无害**（退出流程里会调好几次）。

        ⚠ 先 `NIM_DELETE` 再退出线程：只让线程退出、不删图标，那颗图标会**留到
          鼠标划过才消失**（残影），用户会以为程序还在。
        [EN] Remove the icon and end the tray thread. Safe to call repeatedly (the exit path
        calls it several times). ⚠ NIM_DELETE before the thread ends, or the icon stays as a
        ghost until hovered over, and the user thinks the app is still running.
        """
        hwnd = self._hwnd
        if hwnd:
            try:
                self._win['user32'].PostMessageW(hwnd, WM_CLOSE, 0, 0)
            except Exception:                             # noqa: BLE001
                pass
        th = self._thread
        if th and th.is_alive() and th is not threading.current_thread():
            th.join(timeout)
        self._hwnd = 0
        self._thread = None
        self._ok = False

    def set_tooltip(self, text: str) -> None:
        """改悬停提示（例：把"还没打开的书"换成书名）。

        ⚠ 只改 NIF_TIP；`hIcon` 必须一起带上（`NIM_MODIFY` 的 flags 决定改哪几项），
          少了它某些系统版本会把图标清掉。
        [EN] Change the hover text. ⚠ Only NIF_TIP changes, but `hIcon` must still be passed
        in the struct: omitting it has been seen to clear the icon on some Windows builds.
        """
        self.tooltip = (text or '')[:120]
        hwnd = self._hwnd
        if not hwnd:
            return
        try:
            nid = self._make_nid(hwnd)
            nid.uFlags = NIF_TIP | NIF_ICON
            self._win['shell32'].Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:                                 # noqa: BLE001
            pass

    def notify(self, title: str, text: str) -> None:
        """弹一条**气泡提示**（Windows 10/11 上会进通知中心）。

        用途只有一个：用户选了「只关闭窗口」，窗口一收起来他会以为程序没了。
        这时弹一句"程序还在后台运行，点右下角的图标就能回来" —— 比任何设置项
        说明都管用（说明写在配置页里，而他此刻已经不在配置页了）。
        ⚠ 失败什么都不做：专注助手/通知被关掉是系统的事，不该抛异常。
        [EN] Show a balloon tip (goes to the Action Center on Win10/11). Its only job: the user
        picked "close the window only", and when it vanishes they think the app is gone -- this
        line says "still running, click the icon to come back". ⚠ Failures are swallowed:
        Focus Assist is the system's business.
        """
        hwnd = self._hwnd
        if not hwnd or not self._win:
            return
        try:
            nid = self._make_nid(hwnd)
            nid.uFlags = NIF_INFO | NIF_ICON
            nid.szInfoTitle = (title or '')[:60]
            nid.szInfo = (text or '')[:250]
            nid.dwInfoFlags = NIIF_INFO
            self._win['shell32'].Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:                                 # noqa: BLE001
            pass

    # ── 线程里的一切 ────────────────────────────────────────────────
    def _run(self) -> None:
        try:
            win = _load_win32()
        except Exception:                                 # noqa: BLE001
            self._ready.set()
            return
        self._win = win
        wintypes = win['wintypes']
        user32 = win['user32']

        cls_name = f'{_CLASS_PREFIX}_{os.getpid()}_{id(self)}'
        try:
            self._wndproc = win['WNDPROC'](self._on_message)
            wc = win['WNDCLASSW']()
            wc.style = 0
            wc.lpfnWndProc = self._wndproc
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = win['kernel32'].GetModuleHandleW(None)
            wc.hIcon = 0
            wc.hCursor = 0
            wc.hbrBackground = 0
            wc.lpszMenuName = None
            wc.lpszClassName = cls_name
            if not user32.RegisterClassW(ctypes.byref(wc)):
                # 已注册（同一个 TrayIcon 被 start 两次）也算成功路径
                pass
            hwnd = user32.CreateWindowExW(0, cls_name, 'nws-tray', 0,
                                          0, 0, 0, 0, None, None,
                                          win['kernel32'].GetModuleHandleW(None), None)
        except Exception:                                 # noqa: BLE001
            self._ready.set()
            return
        if not hwnd:
            self._ready.set()
            return

        self._hwnd = int(hwnd)
        self._hicon = self._load_icon()
        nid = self._make_nid(hwnd)
        try:
            ok = bool(win['shell32'].Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
        except Exception:                                 # noqa: BLE001
            ok = False
        self._ok = ok
        try:
            self._taskbar_msg = int(user32.RegisterWindowMessageW('TaskbarCreated') or 0)
        except Exception:                                 # noqa: BLE001
            self._taskbar_msg = 0
        self._ready.set()

        if not ok:
            # 图标没挂上 ⇒ 别让线程空转（留着一个永远收不到消息的窗口只会更难查）。
            # [EN] The icon didn't attach => don't keep an idle thread around.
            try:
                user32.DestroyWindow(hwnd)
            except Exception:                             # noqa: BLE001
                pass
            self._hwnd = 0
            return

        try:
            # ⚠ **不要用 `user32.PumpMessage`**（第一版就是栽在这里）：那是未文档化的
            #   内部函数，**只处理一条消息就返回** —— 图标挂上去 0.2 秒线程就退出了，
            #   表现是"图标闪一下没了"，而 `NIM_ADD` 明明返回了成功。
            #   文档化的写法只有 GetMessage / TranslateMessage / DispatchMessage 三件套。
            # [EN] ⚠ **Do not use `user32.PumpMessage`** (that is where v1 died): it is an
            #   undocumented internal that **handles one message and returns** -- the thread
            #   exited 0.2s after the icon went up, showing as "icon flashes and vanishes"
            #   while NIM_ADD had reported success.
            msg = wintypes.MSG()
            while True:
                r = int(user32.GetMessageW(ctypes.byref(msg), None, 0, 0))
                if r in (0, -1):          # 0 = WM_QUIT；-1 = 出错（同样不该空转）
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:                                 # noqa: BLE001
            pass
        finally:
            self._hwnd = 0

    def _load_icon(self) -> int:
        """装图标：先试程序自己的 .ico，失败退回系统默认图标。

        ⚠ `LoadImageW` 对**路径里的中文**没问题（宽字符版），但文件不存在 / 不是
          合法 ico 时只是返回 0，不抛异常 —— 所以必须判返回值再退回，否则图标位
          是空的：图标还在托盘区、但**看不见**（用户视角＝没图标）。
        [EN] Load the icon; fall back to the system default. ⚠ `LoadImageW` returns 0 (no
        exception) for a missing/invalid file, so check the return or the icon sits in the tray
        **invisibly** -- from the user's side, no icon at all.
        """
        user32 = self._win['user32']
        h = 0
        p = self.icon_path
        if p and Path(p).exists():
            try:
                h = int(user32.LoadImageW(None, p, IMAGE_ICON, 0, 0,
                                          LR_LOADFROMFILE | LR_DEFAULTSIZE) or 0)
            except Exception:                             # noqa: BLE001
                h = 0
        if not h:
            try:
                # MAKEINTRESOURCE：资源 ID 得当指针传（`LoadIconW(None, 32512)` 直接传 int
                # 会被 argtypes 拒掉 —— 返回 0 还是抛异常都不好，明写 cast 最稳）。
                # [EN] MAKEINTRESOURCE: the resource id must be passed as a pointer.
                res = ctypes.cast(ctypes.c_void_p(IDI_APPLICATION),
                                  self._win['wintypes'].LPCWSTR)
                h = int(user32.LoadIconW(None, res) or 0)
            except Exception:                             # noqa: BLE001
                h = 0
        return h

    def _make_nid(self, hwnd):
        win = self._win
        nid = win['NOTIFYICONDATAW']()
        nid.cbSize = ctypes.sizeof(nid)
        nid.hWnd = hwnd
        nid.uID = self.uid
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = CALLBACK_MSG
        nid.hIcon = self._hicon
        nid.szTip = self.tooltip
        return nid

    def _on_message(self, hwnd, msg, wparam, lparam):
        """窗口过程。**必须在任何分支都兜住异常** —— 这里抛出去会杀掉整个托盘线程。

        ⚠ 回调（`on_command` / `on_activate`）也在 try 里：界面那侧出问题最多是
          "这次点击没反应"，不能让图标消失。
        [EN] Window procedure. **Catch everything**: an exception escaping here kills the tray
        thread. ⚠ The callbacks are inside try too: a UI-side failure should cost one ignored
        click, not the icon.
        """
        win = self._win
        if win is None:
            return 0
        user32 = win['user32']
        try:
            if msg == CALLBACK_MSG:
                low = int(lparam) & 0xFFFF
                if low in (WM_LBUTTONUP, WM_CONTEXTMENU):
                    if low == WM_LBUTTONUP:
                        self._fire_activate()
                    else:
                        self._show_menu(hwnd)
                elif low == WM_RBUTTONUP:
                    self._show_menu(hwnd)
                return 0
            if msg == WM_COMMAND:
                cmd = int(wparam) & 0xFFFF
                self._fire_command_by_id(cmd)
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                try:
                    nid = self._make_nid(hwnd)
                    win['shell32'].Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                except Exception:                         # noqa: BLE001
                    pass
                user32.PostQuitMessage(0)
                return 0
            # explorer 重启 → 图标没了 → 重新挂上
            # [EN] explorer restarted -> icon gone -> hang it up again
            if self._taskbar_msg and msg == self._taskbar_msg:
                try:
                    nid = self._make_nid(hwnd)
                    win['shell32'].Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
                except Exception:                         # noqa: BLE001
                    pass
                return 0
        except Exception:                                 # noqa: BLE001
            return 0
        return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))

    # ── 菜单 ────────────────────────────────────────────────────────
    def _build_menu(self) -> tuple:
        """把界面给的清单变成 Win32 菜单，返回 `(hmenu, {id: key})`。

        ⚠ 菜单 id **从 1 开始**：0 在 `TrackPopupMenu` 里表示"用户什么都没选"，
          占用 0 的话"点空白处取消"会被误判成点了第一项。
        [EN] Turn the UI's list into a Win32 menu, returning `(hmenu, {id: key})`.
        ⚠ Ids **start at 1**: 0 means "nothing chosen" in `TrackPopupMenu`; using 0 would make
        "clicked outside to dismiss" look like clicking the first entry.
        """
        user32 = self._win['user32']
        hmenu = user32.CreatePopupMenu()
        mapping: dict[int, str] = {}
        next_id = 1
        try:
            items = list(self._menu() or [])
        except Exception:                                 # noqa: BLE001
            items = [MenuItem(key='show', text='Show', default=True)]
        for it in items:
            if isinstance(it, dict):                      # 容错：也接受 dict
                it = MenuItem(**it)
            if it.sep:
                user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                continue
            flags = MF_STRING
            if not it.enabled:
                flags |= MF_GRAYED
            if it.default:
                flags |= MF_DEFAULT
            user32.AppendMenuW(hmenu, flags, next_id, it.text)
            mapping[next_id] = it.key
            next_id += 1
        return hmenu, mapping

    def _show_menu(self, hwnd) -> None:
        user32 = self._win['user32']
        wintypes = self._win['wintypes']
        try:
            hmenu, mapping = self._build_menu()
        except Exception:                                 # noqa: BLE001
            return
        try:
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            # ⚠ 这两句是"点别处菜单会消失"的前提（KB135788），删了就成了粘住的菜单。
            # [EN] These two lines are what makes "click elsewhere and it dismisses" work.
            user32.SetForegroundWindow(hwnd)
            cmd = int(user32.TrackPopupMenu(
                hmenu, TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                pt.x, pt.y, 0, hwnd, None) or 0)
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        finally:
            try:
                user32.DestroyMenu(hmenu)
            except Exception:                             # noqa: BLE001
                pass
        if cmd:
            self._fire_command_by_id(cmd, mapping)

    def _fire_command_by_id(self, cmd: int, mapping: dict | None = None) -> None:
        if mapping is None:
            return                # 没有映射表的 WM_COMMAND 说明不是我们的菜单
        key = mapping.get(int(cmd))
        if not key:
            return
        try:
            self._on_command(key)
        except Exception:                                 # noqa: BLE001
            pass

    def _fire_activate(self) -> None:
        if self._on_activate is None:
            return
        try:
            self._on_activate()
        except Exception:                                 # noqa: BLE001
            pass


#: 给判据/调用方一个"这个模块能不能用"的结论（非 Windows 时永远是 False）。
# [EN] A single "can this module work here" verdict for criteria and callers.
TRAY_SUPPORTED = available()
