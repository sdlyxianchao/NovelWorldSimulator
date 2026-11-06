# -*- coding: utf-8 -*-
"""跨平台安装 / 卸载：桌面图标 + 开始菜单（启动器）+ 卸载入口。

目标
----
让不碰命令行的人也能用：
  - 双击 setup.exe（Windows）/ setup（Linux、macOS）一次
  - 桌面和「开始菜单」出现图标，图标指向**本平台自己的 start 启动器**
  - 卸载走 uninstall.*，**只删自己创建的快捷方式**；
    用户的小说项目数据（Projects/）永不删除

平台差异（按各平台惯例设计，不强行统一）
----------------------------------------
Windows
    桌面 .lnk + 开始菜单文件夹 `%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\小说世界AI模拟\\`
    文件夹内含「启动 / 打开项目文件夹 / 使用说明 / 卸载」四项（按要求含卸载项）。
    建 .lnk 用 PowerShell 的 WScript.Shell COM。

macOS
    macOS 没有「开始菜单」，等价物是 Launchpad / Spotlight。
    因此把 `小说世界AI模拟.app` 装进 `~/Applications`（自动进 Launchpad 与 Spotlight），
    并在桌面放一个替身。.app 内部直接 exec 同目录的 start（首次装依赖时
    它自己会弹进度窗，不需要借 Terminal）。卸载沿用系统惯例（拖到废纸篓），
    另备 uninstall（同名可执行文件）。

Linux
    `~/.local/share/applications/*.desktop`（应用菜单）+ `~/Desktop/*.desktop`（桌面图标，
    尽量标记 trusted）+ 图标装到 `~/.local/share/icons/hicolor/256x256/apps/`。
    启动项 `Terminal=false`：启动器**没有控制台**，装依赖的进度由它自己的
    进度窗显示，所以不需要终端。

为什么用 PowerShell -EncodedCommand
-----------------------------------
简体中文 Windows 的控制台走 GBK 代码页，`powershell -Command` 里的中文
（中文路径、中文快捷方式名）极易乱码或被截断。把 PowerShell 脚本编码成
UTF-16LE + base64 用 `-EncodedCommand` 传入，可以彻底绕开代码页问题；
执行结果由 PowerShell 写成 UTF-8 JSON，再由 Python 读回。

命令行
------
    python tools/platform_install.py install   [--dry-run] [--dest-root DIR]
    python tools/platform_install.py uninstall [--purge] [--yes] [--dest-root DIR]
    python tools/platform_install.py status

`--dest-root` 把「桌面 / 开始菜单 / Applications」的根换到别处，供自动化测试使用，
这样验证安装器时不会真的往用户桌面上放东西。

English:
Cross-platform install / uninstall: desktop icon + start menu (launcher) + uninstall entry.
Goal
----
Let people who never touch the command line use it too:
  - Double-click setup.exe (Windows) / setup (Linux, macOS) once
  - Icons appear on the desktop and in the "Start Menu", pointing to **this platform's own start launcher**
  - Uninstall goes through uninstall.*, **deleting only the shortcuts it created itself**;
    the user's novel project data (Projects/) is never deleted
Platform differences (designed per each platform's conventions, no forced unification)
----------------------------------------
Windows
    Desktop .lnk + Start Menu folder `%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\小说世界AI模拟\\`
    The folder contains four items: "Launch / Open project folder / Instructions / Uninstall" (including the uninstall item as required).
    Create the .lnk using PowerShell's WScript.Shell COM.
macOS
    macOS has no "Start Menu"; the equivalent is Launchpad / Spotlight.
    So install `小说世界AI模拟.app` into `~/Applications` (automatically appearing in Launchpad and Spotlight),
    and place an alias on the desktop. The .app internally execs the start in the same directory (when installing
    dependencies for the first time it shows its own progress window, no need to borrow Terminal). Uninstall follows
    system convention (drag to Trash), with an additional uninstall (executable of the same name).
Linux
    `~/.local/share/applications/*.desktop` (application menu) + `~/Desktop/*.desktop` (desktop icons,
    mark trusted where possible) + icons installed to `~/.local/share/icons/hicolor/256x256/apps/`.
    Launch entry has `Terminal=false`: the launcher **has no console**, and the dependency-install progress is shown by its own
    progress window, so no terminal is needed.
Why use PowerShell -EncodedCommand
-----------------------------------
The console on Simplified Chinese Windows uses the GBK code page, so Chinese in `powershell
-Command`
(Chinese paths, Chinese shortcut names) is highly prone to garbling or truncation. Encoding the
PowerShell script as
UTF-16LE + base64 and passing it via `-EncodedCommand` completely bypasses the code page
problem;
the execution result is written by PowerShell as UTF-8 JSON, then read back by Python.
Command line
------
    python tools/platform_install.py install   [--dry-run] [--dest-root DIR]
    python tools/platform_install.py uninstall [--purge] [--yes] [--dest-root DIR]
    python tools/platform_install.py status
`--dest-root` redirects the root of "Desktop / Start Menu / Applications" elsewhere, for
automated testing,
so that verifying the installer does not actually put things on the user's desktop.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ★★★ 输出**一律 UTF-8**（2026-10-25 "启动界面出现乱码"）：本文件是启动器起的子进程，
# stdout 是管道 ⇒ Python 退回系统 locale（中文 Windows = cp936/GBK），而启动器把子进程输出
# **字节直通**写进 `logs/launcher.log`（它自己写的行是 UTF-8），启动窗口再按 UTF-8 读
# ⇒ 同一个文件两种编码，GBK 行全成乱码。详见 `novelservices/service_ctl.py` 同一段注释。
# ⚠ 只在**非控制台**时改：真控制台下走 `WriteConsoleW`，本来就是宽字符；手跑时用户要跟码页走。
# [EN] ★★★ Output is **always UTF-8** (2026-10-25 "mojibake in the splash"): the launcher spawns this
# [EN] file and its stdout is a pipe => Python falls back to the system locale (cp936/GBK on Chinese
# [EN] Windows), while the launcher passes child stdout **byte for byte** into `logs/launcher.log`
# [EN] (its own lines are UTF-8) and the splash decodes that as UTF-8 => two encodings in one file.
# [EN] Full rationale: the same block in `novelservices/service_ctl.py`.
# [EN] ⚠ Only when **not** a console: a real console uses `WriteConsoleW` (already wide), and a human
# [EN] running it by hand expects the system code page.
if not sys.stdout.isatty():
    # ⚠ 不能无条件 `del _st`：isatty() 为真时循环一次都没跑，会 NameError。
    for _st in (sys.stdout, sys.stderr):
        try:
            _st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        del _st
    except NameError:
        pass

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

APP_ZH = '小说世界AI模拟'
APP_EN = 'Novel World AI Simulator'
SLUG = 'novel-world-simulator'
BUNDLE_ID = 'com.zhizhi.novelworldsimulator'


def _app_version() -> str:
    """从**唯一的**版本源 `config.py` 里读出 `VERSION`（读不到就返回 `'0.0.0'`）。

    ★★★ 2026-10-22：这里原来写死 `VERSION = '0.3.0'`，而 `config.VERSION` 已经是 0.3.2 ——
      **两个地方各写一份版本号，必然分叉**。它只被 macOS 那两行 `Info.plist` 用到，
      所以后果是"装好的 .app 在系统里报 0.3.0"，而程序里写着 0.3.2，用户报版本时对不上。
      这与"同一件事两处实现"是同一条病：能算的不要抄。
    ★ 为什么**不 `import config`**：这个脚本要在**刚解压、还没装依赖**的机器上跑，
      而 `config` 会连带 import 一堆东西、还可能建目录。这里只**读那一段文本**，
      副作用为零（`developers/check_release.py` 判包里版本时也是这么做的）。

        English:
    Read `VERSION` from the **single** source of truth, `config.py` (`'0.0.0'` if unreadable).
    ★★★ 2026-10-22: this used to be a hard-coded `VERSION = '0.3.0'` while `config.VERSION` was already
      0.3.2 -- **two copies of a version number always drift**. It is only used by the two macOS
      `Info.plist` lines, so the effect was "the installed .app reports 0.3.0" while the program says
      0.3.2, and the user's bug report would name the wrong version. Same disease as "one thing, two
      implementations": anything computable must not be copied.
    ★ Why **not `import config`**: this script runs on a **freshly extracted, dependency-free** machine,
      and `config` pulls in a lot and may create directories. Reading just that text has zero side
      effects (`developers/check_release.py` does the same when checking the version inside a package).
    """
    try:
        head = (APP_DIR / 'config.py').read_text(encoding='utf-8').split('\n')[:40]
    except OSError:
        return '0.0.0'
    for line in head:
        if line.startswith('VERSION'):
            return line.split('=', 1)[1].strip().strip('\'"') or '0.0.0'
    return '0.0.0'


VERSION = _app_version()

MANIFEST_NAME = '.install_manifest.json'

#: 三个启动器的**基名**（`launchers/` 编出来的，见 `launchers/build.py`）。
# [EN] : **basenames** of the three launchers (built by `launchers/`, see `launchers/build.py`).
LAUNCHERS = ('setup', 'start', 'uninstall')


def launcher_name(mode: str, plat: str) -> str:
    """启动器的文件名：Windows 带 `.exe`，Linux / macOS 同名无后缀。
        English:
    Launcher file name: Windows has `.exe`, Linux / macOS have the same name with no suffix.
    """
    return mode + ('.exe' if plat == 'windows' else '')


def no_window_kw() -> dict:
    """Windows：让子进程**不要**被分配控制台。

    ★★ 2026-10-10 实测（`developers/_probe_console_windows.py`，直接枚举桌面上
      **可见的**顶层控制台窗口）：
        父进程没有控制台 + 子进程不带标志            → **多出 1 个黑窗** ★
        父进程没有控制台 + 子进程带 CREATE_NO_WINDOW → 0 个窗口 ✓

      为什么现在才要紧：本脚本现在是被 `setup.exe` / `uninstall.exe` 用
      **pythonw** 拉起的（顶层已经没有控制台），而它自己会去起 PowerShell
      （建 .lnk）/ sips / iconutil / gio / osascript —— 这些都是 console 子系统程序，
      不声明就会被 Windows 各分一个新控制台并**显示**出来。
      ⚠ 只影响"窗不窗口"，不影响输出：下面 `_run` 全都 `capture_output=True`。
    
        English:
    Windows: make sure the child process is **not** allocated a console.
        ★★ Measured on 2026-10-10 (`developers/_probe_console_windows.py`, directly enumerating on the desktop
          **Visible** top-level console window):
            Parent has no console + child without flag            → **1 extra black window** ★
            Parent has no console + child with CREATE_NO_WINDOW → 0 windows ✓
          Why this matters now: this script is currently launched by `setup.exe` / `uninstall.exe` via
          **pythonw** (the top level has no console anymore), and it itself will spawn PowerShell
          (to create .lnk) / sips / iconutil / gio / osascript -- these are all console subsystem programs,
          if not declared, Windows will give each a new console and **show** it.
          ⚠ Only affects "window or not", not output: all `_run` below use `capture_output=True`.
    """
    if os.name != 'nt':
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {'creationflags': 0x08000000, 'startupinfo': si}


def _run(cmd, **kw):
    """`subprocess.run` + "别弹控制台"。

    ★ 为什么不让每个调用点各自写一遍：这个文件里 7 处 `subprocess.run`
      散在四个平台分支里（PowerShell / sips / iconutil / gio / osascript / xdg-user-dir），
      **漏一个就是一个黑窗**，而且只在特定平台特定分支才出现 —— 正是最难发现的那种。
      收成一个入口，新加调用点时想漏也漏不掉（判据另有一条查"没有裸 subprocess.run"）。
    
        English:
    `subprocess.run` + "don't pop a console".
        ★ Why not let each call site write it on its own: there are 7 `subprocess.run` in this file
          scattered across four platform branches (PowerShell / sips / iconutil / gio / osascript / xdg-user-dir),
          **miss one and you get a black window**, and it only appears on a specific platform in a specific branch -- exactly the hardest kind to find.
          Consolidate into a single entry point, and when adding new call sites you can't miss it even if you try (a separate check enforces "no bare subprocess.run").
    """
    for k, v in no_window_kw().items():
        kw.setdefault(k, v)
    return subprocess.run(cmd, **kw)


def _ask_yes_no(prompt: str) -> str | None:
    """问一句 y/N。返回的字符串已经去空白、转小写；**返回 None = 根本问不出来**。

    ★★ 为什么"能不能问"只能靠**真去读一次**来判断（2026-10-10 实测）
    ----------------------------------------------------------------
    第一直觉是 `sys.stdin.isatty()`，但它在 Windows 上会**撒谎**：

        Windows 的 `nul` 是**字符设备**，而 CPython 的 `_isatty()` 判的就是
        "是不是字符设备" —— 于是 `< NUL` 报 `isatty() == True`。
        本机实测（两个都报 True，可一读就 EOF）：
            subprocess.DEVNULL        → isatty=True
            Git-Bash 的 `< /dev/null` → isatty=True
            subprocess.PIPE           → isatty=False
    也就是说 `isatty` 既漏报（DEVNULL）又可能误报，**当不了判据**。

    这件事正是 2026-10-10 那个 bug 的本质：`input()` 在没有终端时**不报错、
    直接 EOF**，于是"问不出来"和"用户答了 N"在代码里长得**一模一样**。
    这里把 EOF 显式收成 `None`，调用方就能把那种"沉默的假答案"变成
    一句能定位的报错（见 `uninstall()` 里那段）。

    ⚠ 唯一的代价：终端真的在时，提示语仍然由 `input()` 打印；
      没有终端时那行提示会先出现在日志里，紧跟着下面那句"问不出来"。
      这点重复换来的是**行为可判定**，值得。
    
        English:
    Ask a y/N question. The returned string is already stripped and lowercased; **returning None =
    can't ask at all**.
        ★★ Why "can we ask" can only be determined by **actually reading once** (measured 2026-10-10)
        ----------------------------------------------------------------
        The first instinct is `sys.stdin.isatty()`, but it **lies** on Windows:
            Windows `nul` is a **character device**, and CPython's `_isatty()` checks exactly
            "is it a character device" -- so `< NUL` reports `isatty() == True`.
            Measured on this machine (both report True, yet reading gives EOF immediately):
                subprocess.DEVNULL        → isatty=True
                Git-Bash's `< /dev/null` → isatty=True
                subprocess.PIPE           → isatty=False
        In other words `isatty` both under-reports (DEVNULL) and can over-report, **it can't serve as the criterion**.
        This is exactly the essence of that 2026-10-10 bug: `input()` with no terminal **doesn't error,
        just EOFs**, so "can't ask" and "user answered N" look **identical** in the code.
        Here EOF is explicitly collected into `None`, so callers can turn that "silent fake answer" into
        a locatable error (see that block in `uninstall()`).
        ⚠ The only cost: when a terminal really exists, the prompt is still printed by `input()`;
          when there's no terminal that prompt line first appears in the log, immediately followed by the "can't ask" line below.
          This bit of duplication buys **deterministic behavior**, worth it.
    """
    try:
        if not sys.stdin:
            return None
        return input(prompt).strip().lower()
    except EOFError:                                               # 没有终端
    # [EN] No terminal
        return None
    except Exception:                                              # noqa: BLE001
        return None




# ══════════════════════════════════════════════════════════════
#  通用小工具
# [EN] General-purpose small tools
# ══════════════════════════════════════════════════════════════
def platform_key() -> str:
    if sys.platform.startswith('win'):
        return 'windows'
    if sys.platform == 'darwin':
        return 'macos'
    return 'linux'


def sh_quote(p) -> str:
    """POSIX 单引号引用（路径含空格/中文/单引号都安全）。
        English:
    POSIX single-quote quoting (safe for paths containing spaces/Chinese/single quotes).
    """
    return "'" + str(p).replace("'", "'\\''") + "'"


def applescript_str(s: str) -> str:
    """把字符串安全嵌进 AppleScript 的双引号字面量。
        English:
    Safely embed a string into an AppleScript double-quoted literal.
    """
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def ps_quote(s) -> str:
    """PowerShell 单引号字面量（单引号本身用两个单引号转义）。
        English:
    PowerShell single-quoted literal (a single quote itself is escaped by doubling it).
    """
    return "'" + str(s).replace("'", "''") + "'"


def read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except Exception:
        return {}


# KNOWNFOLDERID（Windows 的「已知文件夹」）
# [EN] KNOWNFOLDERID (Windows "Known Folders")
_GUID_DESKTOP = 'B4BFCC3A-DB2C-424C-B029-7FE99A87C641'
_GUID_PROGRAMS = 'A77F5D77-2E2B-44C3-A6A2-ABA601054A51'


def win_known_folder(guid_str: str) -> Path | None:
    """用 SHGetKnownFolderPath 取 Windows 已知文件夹的真实路径。

    为什么不能直接写 `~/Desktop`：OneDrive 会把「桌面」「文档」重定向到
    `OneDrive\\桌面` 之类的路径，`Path.home()/'Desktop'` 可能是个空壳目录，
    快捷方式丢进去用户根本看不见。
    
        English:
    Use SHGetKnownFolderPath to get the real path of a Windows known folder.
        Why not just write `~/Desktop`: OneDrive redirects "Desktop", "Documents" to
        paths like `OneDrive\\桌面`, so `Path.home()/'Desktop'` may be an empty shell directory,
        and shortcuts dropped into it are simply invisible to the user.
    """
    if not sys.platform.startswith('win'):
        return None
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [('Data1', wintypes.DWORD),
                        ('Data2', wintypes.WORD),
                        ('Data3', wintypes.WORD),
                        ('Data4', ctypes.c_ubyte * 8)]

        guid = GUID.from_buffer_copy(uuid.UUID(guid_str).bytes_le)
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p)]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        buf = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None,
                                        ctypes.byref(buf)) == 0 and buf.value:
            path = Path(buf.value)
            ole32.CoTaskMemFree(buf)
            return path
    except Exception:
        pass
    return None


def xdg_desktop_dir() -> Path:
    """Linux 下取桌面目录（可能是本地化名字，如「桌面」）。
        English:
    Get the desktop directory on Linux (may be a localized name, e.g. "桌面").
    """
    if shutil.which('xdg-user-dir'):
        try:
            p = _run(['xdg-user-dir', 'DESKTOP'],
                               capture_output=True, text=True, timeout=10)
            if p.returncode == 0 and p.stdout.strip():
                return Path(p.stdout.strip())
        except Exception:
            pass
    return Path.home() / 'Desktop'


def atomic_write(path: Path, text: str, *, encoding: str = 'utf-8',
                 newline: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    if newline:
        text = text.replace('\r\n', '\n').replace('\n', newline)
    tmp.write_text(text, encoding=encoding, newline='')
    os.replace(tmp, path)
# ══════════════════════════════════════════════════════════════
#  Windows：用 PowerShell 建 .lnk
# [EN] Windows: create .lnk via PowerShell
# ══════════════════════════════════════════════════════════════
def ps_run(script: str, *, timeout: int = 120) -> tuple[int, str]:
    """跑一段 PowerShell。用 -EncodedCommand 传，彻底避开代码页/编码问题。
        English:
    Run a PowerShell snippet. Pass it via -EncodedCommand, completely avoiding codepage/encoding
    issues.
    """
    import base64
    enc = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    try:
        p = _run(
            ['powershell', '-NoProfile', '-NonInteractive',
             '-ExecutionPolicy', 'Bypass', '-EncodedCommand', enc],
            capture_output=True, timeout=timeout)
    except Exception as e:                                    # pragma: no cover
        return 127, f'{e}'
    out = (p.stdout or b'').decode('gbk', 'replace')
    err = (p.stderr or b'').decode('gbk', 'replace')
    return p.returncode, (out + err).strip()


def ps_job(body: str, payload: dict, *, timeout: int = 120) -> tuple[int, str, dict]:
    """执行一段 PowerShell，输入输出都走 JSON 文件。

    为什么不让 PowerShell 读命令行参数、也不把路径拼进脚本正文：
    快捷方式路径里可能有空格、中文、单引号，甚至反斜杠结尾，
    拼进脚本文本迟早被 PowerShell 的解析器拆错（实测就踩过：报的是
    「Missing expression after unary operator」，实际是长路径被折行拆开）。
    写成一个 UTF-8 JSON 文件让 PowerShell 读，任何字符都安全。

    约定：脚本里可以用 $job（输入，对象）和 $res（输出文件路径），
    最后自行把结果 JSON 写进 $res。
    
        English:
    Execute a PowerShell snippet, with both input and output going through JSON files.
        Why not let PowerShell read command-line arguments, nor splice paths into the script body:
        a shortcut path may contain spaces, Chinese, single quotes, even a trailing backslash,
        splicing it into the script text will eventually be mis-parsed by PowerShell's parser (measured: it reported
        "Missing expression after unary operator", when actually a long path got line-wrapped and split).
        Writing it as a UTF-8 JSON file for PowerShell to read is safe for any character.
        Convention: within the script you may use $job (input, object) and $res (output file path),
        and finally write the result JSON into $res yourself.
    """
    tag = f'{os.getpid()}_{int(time.time() * 1000) % 1000000}'
    tmp = Path(tempfile.gettempdir())
    job_f = tmp / f'nws_job_{tag}.json'
    res_f = tmp / f'nws_res_{tag}.json'
    job_f.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    script = '\n'.join([
        f'$job = Get-Content -LiteralPath {ps_quote(job_f)} -Raw -Encoding UTF8 '
        '| ConvertFrom-Json',
        f'$res = {ps_quote(res_f)}',
        body,
    ])
    rc, msg = ps_run(script, timeout=timeout)
    data = read_json(res_f) if res_f.exists() else {}
    for f in (job_f, res_f):
        try:
            f.unlink()
        except OSError:
            pass
    return rc, msg, data


def read_shortcut_info(paths) -> tuple[dict, str]:
    """回读 .lnk 的目标/参数/工作目录/图标/说明。返回 (信息, 诊断文本)。

    Windows 专用；其它平台返回空。用于验证脚本核对快捷方式是否真建对了。
    
        English:
    Read back a .lnk's target/arguments/working directory/icon/description. Returns (info,
    diagnostic text).
        Windows-only; other platforms return empty. Used by the verification script to check whether the shortcut was actually created correctly.
    """
    if not sys.platform.startswith('win'):
        return {}, '非 Windows，跳过'
    body = '\n'.join([
        '$sh = New-Object -ComObject WScript.Shell',
        '$res_map = @{}',
        '$errs = New-Object System.Collections.ArrayList',
        'foreach ($p in @($job.paths)) {',
        '  try {',
        '    if (Test-Path -LiteralPath $p) {',
        '      $l = $sh.CreateShortcut($p)',
        '      $res_map[$p] = @{ target = $l.TargetPath; args = $l.Arguments;',
        '                        workdir = $l.WorkingDirectory;',
        '                        icon = $l.IconLocation; desc = $l.Description }',
        '    } else { [void]$errs.Add("missing: $p") }',
        '  } catch { [void]$errs.Add("$p : $_") }',
        '}',
        '@{ lnks = $res_map; errors = @($errs) } | ConvertTo-Json -Depth 5 | '
        'Set-Content -LiteralPath $res -Encoding UTF8',
    ])
    rc, msg, data = ps_job(body, {'paths': [str(p) for p in paths]})
    note = f'rc={rc}' + (f' errs={data.get("errors")}' if data.get('errors') else '')
    if rc != 0 and not data:
        note += ' | ' + msg[:300].replace('\n', ' ')
    return data.get('lnks') or {}, note


# ══════════════════════════════════════════════════════════════
#  中英双语输出
# [EN] Bilingual Chinese-English output
#
#  用户 2026-10-07：「所有的 setup 和 start uninstall 等脚本里的提示语
#  你都改成中英双语（后续我不会再加别的语言了）」。
# [EN] User 2026-10-07: "All prompts in setup and start, uninstall and other scripts
# [EN] you should change to bilingual Chinese-English (I won't add other languages later)."
#
#  ★ 为什么是「中 + 英同时显示」而不是可切换的 i18n：
#    这些是**双击就跑**的控制台脚本，窗口可能被立刻关掉、也可能被截图发出来
#    （用户就是这么做的）。两种语言同时在场，谁都能看懂，
#    也不用去猜对方的语言设置 —— 代价只是每行长一点。
# [EN] ★ Why "display Chinese + English simultaneously" instead of switchable i18n:
# [EN] These are **double-click-and-run** console scripts; the window may be closed instantly or may be
# [EN] screenshotted
# [EN] (that's what the user does). With both languages present, anyone can understand,
# [EN] and you don't have to guess the other party's language settings — the only cost is each line
# [EN] being longer.
#
#  ★ 为什么在**输出口统一翻译**，而不是把 55 处 `self.say(...)` 改成
#    "模板 + 参数"：那些中文 f-string 是**文案真源**，逐句改成模板等于把
#    55 条字符串全部重排（易错，而且 diff 会被噪音淹没）。规则表集中在这里，
#    一眼看完；改文案只动这一处。
#    ⚠ 代价：**必须在输出口翻译**（`say()` / `status()` 是仅有的出口），
#      别在别处直接 `print` —— 那就绕过去了。`untranslated()` 会把漏掉的句子
#      记下来，`tools/verify_script_bilingual.py` 拿它兜底。
# [EN] ★ Why translate at the **output port** uniformly, instead of changing 55 `self.say(...)` calls
# [EN] to
# [EN] "template + params": those Chinese f-strings are the **source of truth for the copy**; changing
# [EN] each sentence to a template amounts to
# [EN] rearranging all 55 strings (error-prone, and the diff would be drowned in noise). The rule table
# [EN] is centralized here,
# [EN] visible at a glance; editing copy touches only this one place.
# [EN] ⚠ Cost: **must translate at the output port** (`say()` / `status()` are the only exits),
# [EN] don't `print` directly elsewhere — that would bypass it. `untranslated()` will
# [EN] record missed sentences, and `tools/verify_script_bilingual.py` uses it as a fallback.
#
#  ★ 规则按顺序**首个匹配即用**，所以"更具体的"要排在前面
#    （例如 `应用菜单项 X（卸载入口）` 必须排在 `应用菜单项 X` 之前）。
#  ★ 替换串一律用 raw string：普通字符串里的 `\1` 会被 Python 当八进制转义。
# [EN] ★ Rules are **first match wins** in order, so "more specific" ones must come first
# [EN] ★ Replacement strings must always use raw strings: `\1` in a normal string is interpreted by
# [EN] Python as an octal escape.
# ══════════════════════════════════════════════════════════════

# 装饰行 / 无语言内容的行 / **本来就是双语的行** → 英文留空（不记入"漏译"清单）
# [EN] Decorative lines / lines with no language content / **lines that are already bilingual** → leave
# [EN] English empty (not counted in the "missing translation" list)
_BI_NO_EN: list[str] = [
    r'=+',                      # 分隔线
    r'\s*',                     # 空行
    r'小说世界AI模拟  /  Novel World AI Simulator',   # 抬头行本身就是双语
    r'\s+[A-Za-z]:[\\/].*',     # 纯路径行（删除清单里那种）
    r'\s+[~/\w].*\.(desktop|app|lnk|png|ico)',   # 纯路径行（无盘符）
    # [EN] Divider line
    # [EN] Blank line
    # [EN] Header line is itself bilingual
    # [EN] Pure path line (the kind in the uninstall list)
    # [EN] Pure path line (no drive letter)
]

BI_RULES: list[tuple[str, str]] = [
    # ── 头部 / 概览 ──
    # [EN] ── Header / overview ──
    (r'程序目录: (.*)', r'App folder: \1'),
    (r'运行平台: (.*)', r'Platform: \1'),
    (r'平台: (.*)', r'Platform: \1'),
    (r'安装根目录（测试用覆盖）: (.*)', r'Install root (test override): \1'),
    (r'演练模式（--dry-run）：只显示将要做的改动，不写任何文件',
     r'Dry run (--dry-run): shows what would change and writes nothing'),
    (r'找不到启动脚本 (.*)，无法关联',
     r'Launcher \1 not found — cannot create a link to it'),
    (r'演练结束：未创建任何文件。去掉 --dry-run 即真正安装。',
     r'Dry run finished: nothing was created. '
     r'Drop --dry-run to install for real.'),
    (r'完成：共创建 (.*) 项。', r'Done: \1 item(s) created.'),
    (r'桌面和「开始菜单」里应该能看到图标了；卸载走 uninstall 脚本。',
     r'The icons should now be on your Desktop and in the Start Menu; '
     r'use the uninstall script to remove them.'),

    # ── 创建条目（带箭头缩进的两行要排在前面）──
    # [EN] ── Create entries (the two arrow-indented lines must come first) ──
    (r'\s*→ 目标 (.*)', r'    -> Target  \1'),
    (r'\s*→ 可执行文件 Contents/MacOS/(.*)（调 (.*)）',
     r'    -> Executable Contents/MacOS/\1 (runs \2)'),
    (r'\s*→ 图标 Contents/Resources/appicon\.icns',
     r'    -> Icon       Contents/Resources/appicon.icns'),
    (r'\s*→ 图标 (.*)', r'    -> Icon    \1'),
    (r'新建快捷方式 (.*)', r'Create shortcut   \1'),
    (r'创建应用包 (.*)', r'Create app bundle \1'),
    (r'桌面替身 (.*)', r'Desktop alias     \1'),
    (r'应用菜单项 (.*)（卸载入口）', r'Menu entry        \1  (uninstaller)'),
    (r'应用菜单项 (.*)', r'Menu entry        \1'),
    (r'桌面图标 *(.*)', r'Desktop icon      \1'),
    (r'图标文件 *(.*)', r'Icon file         \1'),
    (r'卸载 (.*)', r'Uninstall  \1'),

    # ── _touch() 的条目名 ──
    # [EN] ── _touch() entry names ──
    (r'快捷方式: (.*)', r'Shortcut: \1'),
    (r'应用包: (.*)', r'App bundle: \1'),
    (r'桌面替身: (.*)', r'Desktop alias: \1'),
    (r'桌面图标: (.*)', r'Desktop icon: \1'),
    # ⚠ 具体的要排在 `图标: (.*)` **前面**，否则永远轮不到它（规则是首个匹配即用）
    # [EN] ⚠ Specific ones must come **before** `图标: (.*)`, otherwise it never gets its turn (rules are
    # [EN] first match wins)
    (r'图标: （未生成，用系统默认）', r'Icon: (not generated; system default)'),
    (r'图标: (.*)', r'Icon: \1'),
    (r'\.ico 图标: (.*)', r'.ico icon: \1'),
    (r'PNG 图标: (.*)', r'PNG icon: \1'),

    # ── 警告 / 错误 ──
    # ── 图标产物对齐（2026-10-07：用户报「setup 跑完桌面图标还是老图标」）──
    #   ⚠ 这几条要排在 `图标: (.*)` **前面**，否则永远轮不到（首个匹配即用）
    # [EN] ── Warnings / errors ──
    # [EN] ── Icon artifact alignment (2026-10-07: user reported "after setup finishes, desktop icon is
    # [EN] still the old one") ──
    # [EN] ⚠ These rules must come **before** `图标: (.*)`, otherwise they never get their turn (first match
    # [EN] wins)
    (r'图标：已按当前设计重做（指纹 (.*)）',
     r'Icon: rebuilt to match the current design (fingerprint \1)'),
    (r'图标：已是最新一版（指纹 (.*)）',
     r'Icon: already the latest version (fingerprint \1)'),
    (r'图标产物已按当前设计重做', r'Icon files rebuilt to match the current design'),
    (r'图标产物已强制重做', r'Icon files rebuilt (forced)'),
    (r'图标产物刷新失败，沿用现有的（(.*)）',
     r'Could not rebuild the icon files — using the existing ones (\1)'),
    (r'读不到图标模块，沿用现有图标文件（(.*)）',
     r'Icon module could not be loaded — using the existing icon files (\1)'),
    (r'图标指纹算不出来（(.*)）—— 沿用现有产物',
     r'Could not compute the icon fingerprint (\1) — using the existing files'),
    (r'图标生成失败（(.*)）—— 沿用现有产物',
     r'Icon generation failed (\1) — using the existing files'),
    (r'已通知桌面刷新图标缓存',
     r'Desktop icon cache refresh requested'),
    (r'刷新图标缓存没成功（不影响安装）：(.*)',
     r'Icon cache refresh did not go through (installation is unaffected): \1'),
    (r'找不到 \.ico 图标，快捷方式会用系统默认图标',
     r'.ico icon not found — shortcuts will use the system default icon'),
    (r'找不到 PNG 图标，桌面项会显示为默认图标',
     r'PNG icon not found — the menu entry will show the default icon'),
    (r'缺少 sips / iconutil，跳过 \.icns（用系统默认图标）',
     r'sips / iconutil missing — skipping .icns (system default icon)'),
    (r'生成 \.icns 失败（(.*)），用系统默认图标',
     r'Failed to build .icns (\1) — using the system default icon'),
    (r'创建桌面替身失败：(.*)', r'Failed to create the desktop alias: \1'),
    (r'创建快捷方式失败（PowerShell 退出码 (\d+)）',
     r'Shortcut creation failed (PowerShell exit code \1)'),
    (r'创建失败: (.*)', r'Create failed: \1'),
    (r'PowerShell 没有报告任何创建结果',
     r'PowerShell reported no creation result'),
    (r'删除失败（PowerShell 退出码 (\d+)）',
     r'Deletion failed (PowerShell exit code \1)'),
    (r'删除失败: (.*)', r'Delete failed: \1'),
    (r'删除失败 (.*): (.*)', r'Delete failed \1: \2'),
    (r'确认卸载？\[y/N\]', r'Confirm uninstall? [y/N]'),
    (r'没有可以询问的终端 ⇒ 请加 `--yes` 明确确认'
     r'（图形界面版卸载会先弹确认框，再带 --yes 调这里）',
     r'No terminal to ask for confirmation — pass `--yes` to confirm explicitly '
     r'(the GUI uninstaller asks with its own dialog, then calls this with --yes)'),

    # ── 提示 / 结果 ──
    # [EN] ── Prompts / results ──
    (r'用 Spotlight 搜「小说世界」或打开 Launchpad 也能看到',
     r'You can also find it via Spotlight or Launchpad'),
    (r'已标记桌面图标为可信（GNOME 双击需要）',
     r'Desktop icon marked as trusted (needed for double-click on GNOME)'),
    (r'没有找到本程序创建的快捷方式，无需清理。',
     r'No shortcuts created by this app were found — nothing to clean up.'),
    (r'将删除以下快捷方式：', r'The following shortcuts will be removed:'),
    (r'--purge 还会删除运行环境与日志（不动你的小说项目数据）：',
     r'--purge also removes the runtime env and logs '
     r'(your novel projects are never touched):'),
    (r'小说项目数据始终保留：(.*)',
     r'Your novel project data is always kept: \1'),
    (r'演练模式：未做任何删除', r'Dry run: nothing was deleted'),
    (r'已取消。', r'Cancelled.'),
    (r'已删除 (.*) 项。', r'\1 item(s) removed.'),
    (r'已删除: (.*)', r'Removed: \1'),

    # ── status ──
    (r'启动脚本: (.*) \(存在\)', r'Launcher: \1 (present)'),
    (r'启动脚本: (.*) \(缺失\)', r'Launcher: \1 (MISSING)'),
    (r'小说项目目录: (.*)', r'Novel projects folder: \1'),
    (r'快捷方式:', r'Shortcuts / menu entries:'),
    (r'    \[有\] (.*)', r'    [yes] \1'),
    (r'    \[无\] (.*)', r'    [ no] \1'),
    (r'安装记录: (.*) \(有，安装于 (.*)\)',
     r'Install manifest: \1 (installed at \2)'),
    (r'安装记录: (.*) \(无\)', r'Install manifest: \1 (none)'),
] + [(p, '') for p in _BI_NO_EN]


_BI_COMPILED = [(re.compile('^' + p + '$'), rep) for p, rep in BI_RULES]
_BI_MISSING: list[str] = []


def translate_en(zh: str) -> str:
    """把一句中文提示翻成英文；没有对应规则时返回 `''` 并**记下来**。

    记下来是为了让验证脚本能兜住"漏译"：漏了不报错、只是少一行英文，
    这种静默降级最难发现（本项目反复吃过这个教训）。
    
        English:
    Translate a Chinese prompt into English; when there's no matching rule return `''` and **record
    it**.
        Recording it is so the verification script can catch "missing translations": a miss doesn't error, it just lacks one English line,
        this kind of silent degradation is the hardest to find (this project has repeatedly been burned by this lesson).
    """
    s = zh or ''
    for rx, rep in _BI_COMPILED:
        m = rx.match(s)
        if m:
            return m.expand(rep)
    _BI_MISSING.append(s)
    return ''


def untranslated() -> list[str]:
    """到目前为止**没翻出来**的句子（验证脚本用它兜底；正常应为空）。
        English:
    Sentences that **have not been translated** so far (the validation script uses this as a
    fallback; normally it should be empty).
    """
    return list(_BI_MISSING)


# ══════════════════════════════════════════════════════════════
#  安装器
# [EN] Installer
# ══════════════════════════════════════════════════════════════
class Installer:
    def __init__(self, *, dest_root: Path | None = None, dry_run: bool = False,
                 verbose: bool = True, manifest_path: Path | None = None,):
        self.root = APP_DIR
        self.dest_root = Path(dest_root).expanduser().resolve() if dest_root else None
        self.dry_run = dry_run
        self.verbose = verbose
        self.plat = platform_key()
        self.created: list[str] = []
        # ★★ 安装记录要**跟着 dest_root 走**（2026-10-10 实测出来的一个真 bug）
        # [EN] ★★ Install records must **follow dest_root** (a real bug found by actual testing on 2026-10-10)
        # -----------------------------------------------------------------
        # `--dest-root` 的用途是"把桌面 / 开始菜单 / Applications 整个挪到别处"，
        # 也就是**测试沙盒**。可记录原来一律写在工程根目录 —— 于是一次
        # "沙盒安装"就会把**真实**记录覆盖成 `dest_root=<临时目录>`，接着：
        #   · 用户下次真卸载 → `uninstall()` 读到那条 dest_root → 跑去临时目录里删
        #     （那里什么都没有）⇒ 桌面图标**一个都没删掉**，而且**返回成功**
        #     （"没有找到本程序创建的快捷方式，无需清理"）。属于本项目最忌讳的
        #     "不报错但给你错结果"。
        #   · 沙盒卸载还会把那条真实记录本身删掉（实测：`uninstall --yes
        #     --dest-root <空目录>` 报「已删除 1 项」—— 删的就是真实记录）。
        # 修法就是把记录放进沙盒里：测试状态不可能再碰到生产状态。
        # [EN] `--dest-root` is meant to "move Desktop / Start Menu / Applications entirely elsewhere",
        # [EN] i.e. a **test sandbox**. But records were always written to the project root — so a single
        # [EN] "sandbox install" would overwrite the **real** record with `dest_root=<temp dir>`, and then:
        # [EN] · Next time the user really uninstalls → `uninstall()` reads that dest_root → goes to delete in
        # [EN] the temp dir
        # [EN] (where there's nothing) ⇒ **not a single** desktop icon is deleted, yet it **returns success**
        # [EN] ("No shortcuts created by this program were found, nothing to clean up."). This is the project's
        # [EN] most taboo
        # [EN] "no error but wrong result".
        # [EN] · Sandbox uninstall would also delete that real record itself (observed: `uninstall --yes
        # [EN] --dest-root <empty dir>` reports "Deleted 1 item" — what was deleted is the real record).
        # [EN] The fix is to put the record inside the sandbox: test state can never again touch production
        # [EN] state.
        self.manifest_path = (
            Path(manifest_path) if manifest_path
            else (self.dest_root / MANIFEST_NAME if self.dest_root
                  else APP_DIR / MANIFEST_NAME))

    # ── 输出 ──
    # [EN] ── Output ──
    def say(self, msg: str, mark: str = ' ') -> None:
        """输出一行**中英双语**：中文那行照旧，英文另起一行对齐。

        这里是全脚本的**唯一输出口**（`status()` 也走它）—— 双语化就做在这一层，
        所以 55 处 `self.say('中文…')` 一句都不用改（见 `BI_RULES` 上方的说明）。
        
                English:
        Output a line of **bilingual Chinese-English**: the Chinese line stays as-is, the English goes
        on a new aligned line.
                This is the **sole output point** of the whole script (`status()` also goes through it) -- bilingualization is done at this layer,
                so the 55 `self.say('Chinese...')` calls don't need any changes (see the note above `BI_RULES`).
        """
        if not self.verbose:
            return
        if mark == ' ':
            print(f'  {msg}', flush=True)
        else:
            print(f'  [{mark}] {msg}', flush=True)
        en = translate_en(msg)
        if not en:
            return
        # 与中文对齐：带标记时中文从 index 5+len(mark) 开始
        # [EN] Align with Chinese: with a marker, Chinese starts at index 5+len(mark)
        pad = ' ' * (3 + len(mark)) if mark != ' ' else ''
        print(f'  {pad}{en}', flush=True)

    def _touch(self, path: Path, what: str) -> None:
        self.created.append(str(path))
        self.say(f'{what}: {path}')

    # ── 目录定位（dest_root 只影响「桌面 / 开始菜单 / Applications」的根）──
    # [EN] ── Directory location (dest_root only affects the root of "Desktop / Start Menu / Applications")
    # [EN] ──
    def _d(self, *parts: str) -> Path:
        base = self.dest_root if self.dest_root else Path.home()
        return base.joinpath(*parts)

    @property
    def desktop_dir(self) -> Path:
        if self.dest_root:
            return self.dest_root / 'Desktop'
        if self.plat == 'windows':
            real = win_known_folder(_GUID_DESKTOP)
            if real:
                return real
        if self.plat == 'linux':
            return xdg_desktop_dir()
        return Path.home() / 'Desktop'

    @property
    def projects_dir(self) -> Path:
        try:
            from config import CFG
            return Path(CFG.projects_dir())
        except Exception:
            return self.root.parent / 'Projects'

    # ── 图标来源 ──
    # [EN] ── Icon source ──
    def sync_icons(self) -> None:
        """**装之前先把图标产物对齐到当前设计**（2026-10-07 加）。

        用户报「setup 跑完桌面图标还是老图标」，根因之一就在这儿：
        产物（`assets/app_icon.ico` 等五份）**一直只在启动程序时刷新**，
        而安装器只读现成的。于是"改完图标 → 直接跑 setup"（没先启动程序）
        装出来的就是旧图标 —— 这恰好是**最自然的操作顺序**。

        所以这里调 `image_gen.icon.ensure_assets()`（按源码指纹判定，
        对得上就一行不动、约 0ms；对不上就重做五份）。
        ★ 安装器**不能** import `gui.app_flet`（会把整个 Flet 界面拉起来），
          所以那段逻辑已经搬到 `image_gen/icon.py`（见那边的说明）。

        **失败不当场退出**：拿不到新图就沿用现有的，并**说清楚** ——
        没有图标是缺憾，装不上更糟。
        
                English:
        **Before installing, first align the icon artifacts with the current design** (added
        2026-10-07).
                The user reported "after setup runs, the desktop icon is still the old icon"; one of the root causes is here:
                the artifacts (the five files such as `assets/app_icon.ico`) **have always only been refreshed when the launcher program starts**,
                while the installer only reads what is already there. So "change the icon -> run setup directly" (without starting the program first)
                installs the old icon -- and this is exactly the **most natural order of operations**.
                So here we call `image_gen.icon.ensure_assets()` (decided by source fingerprint;
                if it matches, nothing is touched, about 0ms; if not, the five files are regenerated).
                ★ The installer **must not** import `gui.app_flet` (that would bring up the entire Flet UI),
                  so that logic has been moved to `image_gen/icon.py` (see the note there).
                **On failure do not exit immediately**: if a new image can't be obtained, use the existing one and **say so clearly** --
                having no icon is a shortcoming, but failing to install is worse.
        """
        try:
            import sys
            if str(self.root) not in sys.path:
                sys.path.insert(0, str(self.root))
            from image_gen.icon import (assets_up_to_date, ensure_assets,
                                        icon_signature)
        except Exception as e:                                   # noqa: BLE001
            self.say(f'读不到图标模块，沿用现有图标文件（{e}）', '!')
            return
        try:
            # `ensure_assets` 只在**真的重做**时才回调，所以先把结论记下来：
            # 无论它做没做事，都要告诉用户"手上这份图标是哪一版"（否则
            # "桌面图标还是老的"这种事又只能靠肉眼猜）。
            # [EN] `ensure_assets` only calls back on a **real redo**, so record the conclusion first:
            # [EN] whether or not it did anything, tell the user "which version of the icon they currently have"
            # [EN] (otherwise
            # [EN] "desktop icon is still the old one" can only be guessed by eye again).
            changed = not assets_up_to_date()
            ensure_assets(log=lambda m: self.say(m, 'i'))
            self.say('图标：' + ('已按当前设计重做' if changed else '已是最新一版')
                     + f'（指纹 {icon_signature()[:8]}）', 'i')
        except Exception as e:                                   # noqa: BLE001
            self.say(f'图标产物刷新失败，沿用现有的（{e}）', '!')

    def icon_ico(self) -> Path | None:
        """给快捷方式用的 .ico —— **带指纹的那个副本**（不是固定名那个）。

        为什么要换名字：Windows 的图标缓存**按路径认**。`.lnk` 里的
        `IconLocation` 一直写 `assets\app_icon.ico`，路径不变 → 即使文件内容
        已经换成新图标，资源管理器还是拿缓存里那张旧图来画
        （用户看到的"还是老图标"就是这么来的）。
        复制成 `app_icon.<指纹>.ico` 后**路径一变，缓存必然失效**。

        拿不到带指纹的那份就退回固定名（宁可可能被缓存，也别没图标）。
        
                English:
        The .ico used for the shortcut -- **the copy with the fingerprint** (not the fixed-name one).
                Why change the name: Windows' icon cache **identifies by path**. The `.lnk`'s
                `IconLocation` always writes `assetspp_icon.ico`; the path doesn't change -> even if the file contents
                have already been replaced with a new icon, Explorer still draws the old image from the cache
                (this is where the user's "still the old icon" comes from).
                After copying to `app_icon.<fingerprint>.ico`, **the path changes and the cache is necessarily invalidated**.
                If the fingerprinted copy can't be obtained, fall back to the fixed name (better a possible cache hit than no icon).
        """
        try:
            from image_gen.icon import versioned_ico
            v = versioned_ico()
            if v and v.exists():
                return v
        except Exception:                                        # noqa: BLE001
            pass
        for rel in ('assets/app_icon.ico', 'assets/images/icon.ico'):
            p = self.root / rel
            if p.exists():
                return p
        return None

    def icon_png(self, min_size: int = 0) -> Path | None:
        cands = ['assets/images/icon.png', 'assets/images/icon_256.png',
                 'assets/app_icon.png']
        found = [(self.root / r) for r in cands if (self.root / r).exists()]
        if not found:
            return None
        if min_size:
            from PIL import Image
            for p in found:
                try:
                    with Image.open(p) as im:
                        if max(im.size) >= min_size:
                            return p
                except Exception:
                    continue
        return found[0]

    # ── 启动器 ──
    # [EN] ── Launchers ──
    #
    # ★ 2026-10-10：这里以前返回的是 `start.bat` / `start.command` / `start.sh`
    #   （三对脚本）。现在那 9 个脚本**已经删掉**，改成 `launchers/` 里用 Go 写的、
    #   交叉编译成各平台可执行文件的三个启动器（用户要求：「删掉，只留 exe」）。
    #   属性名保留 `start_script` / `uninstall_script` 只是不想让下面十几个调用点
    #   全部改名 —— 它们要的本来就是"快捷方式该指向哪个文件"。
    # [EN] ★ 2026-10-10: this used to return `start.bat` / `start.command` / `start.sh`
    # [EN] (three pairs of scripts). Now those 9 scripts **have been deleted**, replaced by Go-written,
    # [EN] cross-compiled per-platform executables in `launchers/` — the three launchers (user requirement:
    # [EN] "delete them, keep only the exe").
    # [EN] The property names `start_script` / `uninstall_script` are kept only to avoid renaming all the
    # [EN] dozen or so call sites below
    # [EN] — what they want is simply "which file the shortcut should point to".
    @property
    def start_script(self) -> Path:
        return self.root / launcher_name('start', self.plat)

    @property
    def uninstall_script(self) -> Path:
        return self.root / launcher_name('uninstall', self.plat)

    # ══════════════════════════════════════════════════════════
    #  安装入口
    # [EN] Install entry
    # ══════════════════════════════════════════════════════════
    def install(self) -> bool:
        self.say(f'{APP_ZH}  /  {APP_EN}')
        self.say('=' * 46)
        self.say(f'程序目录: {self.root}')
        self.say(f'运行平台: {self.plat}')
        if self.dest_root:
            self.say(f'安装根目录（测试用覆盖）: {self.dest_root}')
        if self.dry_run:
            self.say('演练模式（--dry-run）：只显示将要做的改动，不写任何文件', 'i')
        if not self.start_script.exists():
            self.say(f'找不到启动脚本 {self.start_script.name}，无法关联', 'X')
            return False

        self.say('')
        # ★ **先对齐图标产物，再建快捷方式**（顺序不能反：快捷方式一旦建好就
        #   把 icon 路径写死了，之后再生成也换不上去）。`--dry-run` 不写任何文件，
        #   所以演练时跳过这一步。
        # [EN] ★ **Align icon artifacts first, then create shortcuts** (order can't be reversed: once a
        # [EN] shortcut is created it
        # [EN] hardcodes the icon path, and generating afterward won't swap it in). `--dry-run` writes no
        # [EN] files,
        # [EN] so skip this step during dry runs.
        if not self.dry_run:
            self.sync_icons()
        ok = {'windows': self._install_windows,
              'macos': self._install_macos,
              'linux': self._install_linux}[self.plat]()
        if not ok:
            return False

        self._write_manifest()
        self.say('')
        if self.dry_run:
            self.say('演练结束：未创建任何文件。去掉 --dry-run 即真正安装。', 'OK')
            return True
        self.say(f'完成：共创建 {len(self.created)} 项。', 'OK')
        self.say('桌面和「开始菜单」里应该能看到图标了；卸载走 uninstall 脚本。')
        return True

    # ── manifest ──
    def _write_manifest(self) -> None:
        data = {
            'version': 1,
            'platform': self.plat,
            'app_dir': str(self.root),
            'dest_root': str(self.dest_root) if self.dest_root else None,
            'created': list(self.created),
            'installed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        if self.dry_run:
            return
        atomic_write(self.manifest_path,
                     json.dumps(data, ensure_ascii=False, indent=2), newline='\n')

    # ══════════════════════════════════════════════════════════
    #  Windows
    # ══════════════════════════════════════════════════════════
    def _sm_folder(self) -> Path:
        """开始菜单里的程序文件夹。用系统已知文件夹，避开 OneDrive/系统盘重定向。
                English:
        The program folder in the Start menu. Use a system-known folder to avoid OneDrive/system-drive
        redirection.
        """
        if not self.dest_root and self.plat == 'windows':
            real = win_known_folder(_GUID_PROGRAMS)
            if real:
                return real / APP_ZH
        return self._d('Start Menu', 'Programs', APP_ZH)

    def _install_windows(self) -> bool:
        ico = self.icon_ico()
        if not ico:
            self.say('找不到 .ico 图标，快捷方式会用系统默认图标', '!')
        desktop = self.desktop_dir / f'{APP_ZH}.lnk'
        sm = self._sm_folder()

        items = [
            # (快捷方式, 目标, 参数, 工作目录, 说明)
            # [EN] (shortcut, target, params, working dir, description)
            (desktop, str(self.start_script), '', str(self.root), '启动小说世界AI模拟'),
            (sm / f'{APP_ZH}.lnk', str(self.start_script), '', str(self.root),
             '启动小说世界AI模拟'),
            (sm / '打开项目文件夹.lnk',
             str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'explorer.exe'),
             f'"{self.projects_dir}"', str(self.root), '打开小说项目文件夹'),
            (sm / '使用说明.lnk', str(self.root / '使用说明.md'), '', str(self.root),
             '查看使用说明'),
            (sm / '卸载 小说世界AI模拟.lnk', str(self.uninstall_script), '',
             str(self.root), '卸载：删除桌面与开始菜单里的图标'),
        ]

        if self.dry_run:
            for path, target, args, wd, desc in items:
                self.say(f'新建快捷方式 {path}')
                self.say(f'    → 目标 {target} {args}'.rstrip())
                self.say(f'    → 图标 {ico or "(默认)"}')
            return True

        icon_loc = f'{ico},0' if ico else ''
        payload = {'items': [
            {'path': str(path), 'target': target, 'args': args,
             'workdir': wd, 'icon': icon_loc, 'desc': desc}
            for path, target, args, wd, desc in items]}

        # 路径通过 JSON 文件传给 PowerShell，不拼进脚本正文（见 ps_job 的说明）
        # [EN] Paths are passed to PowerShell via a JSON file, not spliced into the script body (see ps_job's
        # [EN] note)
        body = '\n'.join([
            '$made = New-Object System.Collections.ArrayList',
            '$errs = New-Object System.Collections.ArrayList',
            '$sh = New-Object -ComObject WScript.Shell',
            'foreach ($it in @($job.items)) {',
            '  try {',
            '    $d = Split-Path -Parent $it.path',
            '    if (-not (Test-Path -LiteralPath $d)) {',
            '      New-Item -ItemType Directory -Force -Path $d | Out-Null }',
            '    $l = $sh.CreateShortcut($it.path)',
            '    $l.TargetPath = $it.target',
            '    if ($it.args) { $l.Arguments = $it.args }',
            '    if ($it.workdir) { $l.WorkingDirectory = $it.workdir }',
            '    if ($it.icon) { $l.IconLocation = $it.icon }',
            '    if ($it.desc) { $l.Description = $it.desc }',
            '    $l.WindowStyle = 1',
            '    $l.Save()',
            '    [void]$made.Add($it.path)',
            '  } catch { [void]$errs.Add("$($it.path) : $_") }',
            '}',
            '@{ made = @($made); errors = @($errs) } | ConvertTo-Json -Depth 4 | '
            'Set-Content -LiteralPath $res -Encoding UTF8',
        ])
        rc, msg, data = ps_job(body, payload)
        made = data.get('made') or []
        if data.get('errors'):
            for e in data['errors']:
                self.say(f'创建失败: {e}', 'X')
        if rc != 0 and not data:
            self.say(f'创建快捷方式失败（PowerShell 退出码 {rc}）', 'X')
            if msg:
                self.say(msg[:800])
            return False

        for p in made:
            self._touch(Path(p), '快捷方式')
        if not made:
            self.say('PowerShell 没有报告任何创建结果', 'X')
            return False
        if ico:
            self.say(f'图标: {ico}')
        self.refresh_shell_icons()
        return not data.get('errors')

    def refresh_shell_icons(self) -> None:
        """让资源管理器**立刻重读图标**（Windows）。

        两道保险里的第二道：
          ① 快捷方式的图标路径带指纹（`app_icon.<指纹>.ico`）—— 缓存按路径
             key，路径变了必然 miss；
          ② 这里再发一次 `SHChangeNotify(SHCNE_ASSOCCHANGED)`，让 shell 主动
             刷新关联缓存 —— 刚建出来的快捷方式**当场**就显示新图标，
             而不必等它自己想起来（有时要注销或重启资源管理器才动）。

        **失败只提示，不影响安装结果** —— 快捷方式已经建好了，
        最坏也就是"晚一会儿才变过来"，为此报安装失败是轻重倒置。
        
                English:
        Make Explorer **immediately reread the icon** (Windows).
                The second of two safeguards:
                  (1) The shortcut's icon path carries a fingerprint (`app_icon.<fingerprint>.ico`) -- the cache is keyed
                     by path, so a path change necessarily misses;
                  (2) Here we additionally send `SHChangeNotify(SHCNE_ASSOCCHANGED)` so the shell actively
                     refreshes the association cache -- the just-created shortcut **immediately** shows the new icon,
                     without having to wait for it to remember on its own (sometimes it takes a logout or restarting Explorer).
                **Failure only warns, does not affect the install result** -- the shortcut has already been created,
                the worst case is "it changes over a bit later"; reporting an install failure for this would be putting the cart before the horse.
        """
        if self.plat != 'windows':
            return
        body = '\n'.join([
            '$ok = $false',
            '$why = ""',
            'try {',
            "  $sig = '[DllImport(\"shell32.dll\")]public static extern void "
            "SHChangeNotify(int e, uint f, IntPtr a, IntPtr b);'",
            "  $t = Add-Type -MemberDefinition $sig -Name 'NwsShell' "
            "-Namespace 'Nws' -PassThru",
            '  # 0x08000000 = SHCNE_ASSOCCHANGED, 0x1000 = SHCNF_FLUSH',
            '  $t::SHChangeNotify(0x08000000, 0x1000, [IntPtr]::Zero, '
            '[IntPtr]::Zero)',
            '  $ok = $true',
            '} catch { $why = "$_" }',
            # ⚠ **必须显式写结果**：Add-Type 出错时 PowerShell 的退出码仍是 0
            #   （非终止错误），只看 rc 会把失败当成功。
            # [EN] ⚠ **Must write results explicitly**: when Add-Type errors, PowerShell's exit code is still 0
            # [EN] (non-terminating error); checking only rc treats failure as success.
            '@{ ok = $ok; why = $why } | ConvertTo-Json | '
            'Set-Content -LiteralPath $res -Encoding UTF8',
        ])
        try:
            rc, msg, data = ps_job(body, {'items': []})
            if data.get('ok'):
                self.say('已通知桌面刷新图标缓存', 'i')
            else:
                self.say(f'刷新图标缓存没成功（不影响安装）：'
                         f'{str(data.get("why") or msg or "")[:120]}', '!')
        except Exception as e:                                   # noqa: BLE001
            self.say(f'刷新图标缓存没成功（不影响安装）：{e}', '!')

    # ══════════════════════════════════════════════════════════
    #  macOS
    # ══════════════════════════════════════════════════════════
    def _mac_launcher(self) -> str:
        """生成 .app 内部的可执行脚本：**直接 exec 同目录的 `start`**。

        ★ 2026-10-10 改：以前这一段是"经 Terminal 调 `start.sh`"——
          理由写在旧注释里："首次运行要装依赖，所以借 Terminal 显示进度"。
          现在这个理由**不成立了**：`start` 是个无控制台的可执行文件，
          而它要装依赖时**自己会弹一个进度窗**。再借 Terminal 只会多出一个
          终端窗口 —— 正是这次要消灭的东西。
        
                English:
        Generate the executable script inside the .app: **directly exec the `start` in the same
        directory**.
                ★ Changed 2026-10-10: this section used to be "invoke `start.sh` via Terminal" --
                  the reason was written in the old comment: "first run needs to install dependencies, so borrow Terminal to show progress".
                  Now this reason **no longer holds**: `start` is a console-less executable,
                  and when it needs to install dependencies **it pops up a progress window itself**. Borrowing Terminal again only adds
                  an extra terminal window -- exactly the thing we're trying to eliminate this time.
        """
        root = sh_quote(self.root)
        return f"""#!/bin/bash
# 由 tools/platform_install.py 生成 —— {APP_ZH}
# 作用：启动程序。真实逻辑在同目录的 start（launchers/ 编出来的可执行文件）。
ROOT={root}
cd "$ROOT" || exit 1
# 从 zip 解出来的文件常常丢掉执行位 —— 顺手补一下，否则"双击没反应"。
[ -x ./start ] || chmod +x ./start 2>/dev/null
exec ./start
"""

    def _build_icns(self, out_icns: Path) -> bool:
        """用系统自带的 sips + iconutil 从 PNG 生成 .icns。失败返回 False。
                English:
        Use the system's built-in sips + iconutil to generate .icns from PNG. On failure, return False.
        """
        src = self.icon_png(min_size=256)
        if not src:
            return False
        if not (shutil.which('sips') and shutil.which('iconutil')):
            self.say('缺少 sips / iconutil，跳过 .icns（用系统默认图标）', '!')
            return False
        try:
            with tempfile.TemporaryDirectory() as td:
                iconset = Path(td) / 'app.iconset'
                iconset.mkdir()
                # (文件名, 像素边长)，@2x 是给 Retina 的
                # [EN] (filename, pixel side length), @2x is for Retina
                specs = [('icon_16x16.png', 16), ('icon_16x16@2x.png', 32),
                         ('icon_32x32.png', 32), ('icon_32x32@2x.png', 64),
                         ('icon_128x128.png', 128), ('icon_128x128@2x.png', 256),
                         ('icon_256x256.png', 256), ('icon_256x256@2x.png', 512),
                         ('icon_512x512.png', 512), ('icon_512x512@2x.png', 1024)]
                from PIL import Image
                with Image.open(src) as im:
                    src_max = max(im.size)
                    # macOS 的图标惯例是四周留白（图形约占 82%），
                    # 我们的 PNG 是接近满幅的圆角方，直接转成 icns 会比别的应用显大。
                    # [EN] macOS icon convention leaves padding around the edges (graphic occupies about 82%),
                    # [EN] our PNG is a nearly full-bleed rounded square, so converting directly to icns makes it look
                    # [EN] larger than other apps.
                    src_img = Image.new('RGBA', (src_max, src_max), (0, 0, 0, 0))
                    side = int(src_max * 0.82)
                    src_img.paste(im.convert('RGBA').resize(
                        (side, side), Image.Resampling.LANCZOS),
                        ((src_max - side) // 2, (src_max - side) // 2))
                pad = Path(td) / 'padded.png'
                src_img.save(pad)
                for name, size in specs:
                    if size > src_max * 2:      # 不无限放大
                    # [EN] Do not upscale indefinitely
                        continue
                    _run(['sips', '-z', str(size), str(size), str(pad),
                                    '--out', str(iconset / name)],
                                   capture_output=True, check=True)
                _run(['iconutil', '-c', 'icns', str(iconset),
                                '-o', str(out_icns)],
                               capture_output=True, check=True)
            return out_icns.exists()
        except Exception as e:
            self.say(f'生成 .icns 失败（{e}），用系统默认图标', '!')
            return False

    def _install_macos(self) -> bool:
        apps_dir = self._d('Applications')
        bundle = apps_dir / f'{APP_ZH}.app'
        exe_name = SLUG
        contents = bundle / 'Contents'
        macos_dir = contents / 'MacOS'
        res_dir = contents / 'Resources'

        if self.dry_run:
            self.say(f'创建应用包 {bundle}')
            self.say(f'    → 可执行文件 Contents/MacOS/{exe_name}（调 {self.start_script.name}）')
            self.say(f'    → 图标 Contents/Resources/appicon.icns')
            self.say(f'桌面替身 {self.desktop_dir / APP_ZH}')
            return True

        macos_dir.mkdir(parents=True, exist_ok=True)
        res_dir.mkdir(parents=True, exist_ok=True)

        exe = macos_dir / exe_name
        atomic_write(exe, self._mac_launcher(), newline='\n')
        exe.chmod(0o755)
        self._touch(bundle, '应用包')

        icns = res_dir / 'appicon.icns'
        prebuilt = self.root / 'assets/app_icon.icns'
        if prebuilt.exists():
            shutil.copy2(prebuilt, icns)
        else:
            self._build_icns(icns)
        has_icon = icns.exists()

        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>{APP_ZH}</string>
    <key>CFBundleDisplayName</key><string>{APP_ZH}</string>
    <key>CFBundleExecutable</key><string>{exe_name}</string>
    <key>CFBundleIdentifier</key><string>{BUNDLE_ID}</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>{VERSION}</string>
    <key>CFBundleVersion</key><string>{VERSION}</string>
    <key>CFBundleDevelopmentRegion</key><string>zh_CN</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSMinimumSystemVersion</key><string>10.15</string>
{'    <key>CFBundleIconFile</key><string>appicon</string>' if has_icon else ''}
</dict>
</plist>
"""
        atomic_write(contents / 'Info.plist', plist)
        atomic_write(contents / 'PkgInfo', 'APPL????')
        self.say(f'应用包: {bundle}')
        self.say(f'图标: {"appicon.icns" if has_icon else "（未生成，用系统默认）"}')

        # 桌面替身：优先 Finder 真替身，失败退回符号链接
        # [EN] Desktop alias: prefer a real Finder alias, fall back to a symlink on failure
        self.desktop_dir.mkdir(parents=True, exist_ok=True)
        alias = self.desktop_dir / APP_ZH
        if alias.exists() or alias.is_symlink():
            self._remove_silent(alias)
        made_alias = False
        if shutil.which('osascript'):
            script = (
                'tell application "Finder"\n'
                f'  make alias file to (POSIX file {applescript_str(str(bundle))}) '
                f'at (POSIX file {applescript_str(str(self.desktop_dir))})\n'
                'end tell')
            rc, _ = ps_run_for_osascript(script)
            made_alias = rc == 0 and alias.exists()
        if not made_alias:
            try:
                alias.symlink_to(bundle)
                made_alias = True
            except OSError as e:
                self.say(f'创建桌面替身失败：{e}', 'X')
        if made_alias:
            self._touch(alias, '桌面替身')
        self.say('用 Spotlight 搜「小说世界」或打开 Launchpad 也能看到', 'i')
        return True

    # ══════════════════════════════════════════════════════════
    #  Linux
    # ══════════════════════════════════════════════════════════
    def _linux_desktop_entry(self, *, name: str, exec_line: str, comment: str,
                             categories: str) -> str:
        icon = self._linux_icon_path()
        return f"""[Desktop Entry]
Type=Application
Version=1.0
Name={name}
Comment={comment}
Exec={exec_line}
Path={self.root}
Icon={icon}
Terminal=false
Categories={categories}
StartupNotify=true
"""

    def _linux_icon_path(self) -> str:
        icons = self._d('.local', 'share', 'icons', 'hicolor', '256x256', 'apps')
        return str(icons / f'{SLUG}.png')

    def _install_linux(self) -> bool:
        apps_dir = self._d('.local', 'share', 'applications')
        icons_dir = self._d('.local', 'share', 'icons', 'hicolor', '256x256', 'apps')
        launcher = apps_dir / f'{SLUG}.desktop'
        uninstaller = apps_dir / f'{SLUG}-uninstall.desktop'
        desk_icon = self.desktop_dir / f'{SLUG}.desktop'

        launcher_txt = self._linux_desktop_entry(
            name=APP_ZH,
            exec_line=f'bash "{self.start_script}"',
            comment='在已有小说设定范围内推演情节（写作辅助工具）',
            categories='Office;TextTools;')
        uninstall_txt = self._linux_desktop_entry(
            name=f'卸载 {APP_ZH}',
            exec_line=f'bash "{self.uninstall_script}"',
            comment='删除桌面与应用菜单里的图标',
            categories='Utility;')

        if self.dry_run:
            self.say(f'应用菜单项 {launcher}')
            self.say(f'应用菜单项 {uninstaller}（卸载入口）')
            self.say(f'桌面图标   {desk_icon}')
            self.say(f'图标文件   {icons_dir}/{SLUG}.png')
            return True

        png = self.icon_png(min_size=128)
        if png:
            icons_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, icons_dir / f'{SLUG}.png')
            self._touch(icons_dir / f'{SLUG}.png', '图标')
        else:
            self.say('找不到 PNG 图标，桌面项会显示为默认图标', '!')

        apps_dir.mkdir(parents=True, exist_ok=True)
        for path, txt, what in ((launcher, launcher_txt, '应用菜单项'),
                                (uninstaller, uninstall_txt, '应用菜单项（卸载）')):
            atomic_write(path, txt, newline='\n')
            path.chmod(0o755)
            self._touch(path, what)

        self.desktop_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(desk_icon, launcher_txt, newline='\n')
        desk_icon.chmod(0o755)
        self._touch(desk_icon, '桌面图标')
        # GNOME 需要标记 trusted 才允许双击；失败不影响使用
        # [EN] GNOME requires the trusted mark to allow double-click; failure does not affect usability
        if shutil.which('gio'):
            _run(['gio', 'set', str(desk_icon),
                            'metadata::trusted', 'true'], capture_output=True)
            self.say('已标记桌面图标为可信（GNOME 双击需要）', 'i')
        if shutil.which('update-desktop-database'):
            _run(['update-desktop-database', str(apps_dir)],
                           capture_output=True)
        return True

    # ══════════════════════════════════════════════════════════
    #  卸载
    # [EN] Uninstall
    # ══════════════════════════════════════════════════════════
    def uninstall(self, *, purge: bool = False, assume_yes: bool = False) -> bool:
        manifest = read_json(self.manifest_path)
        if manifest.get('dest_root') and not self.dest_root:
            self.dest_root = Path(manifest['dest_root'])

        self.say(f'卸载 {APP_ZH}')
        self.say('=' * 46)
        targets = self._targets()
        existing = [Path(p) for p in targets if Path(p).exists()
                    or Path(p).is_symlink()]

        if not existing:
            self.say('没有找到本程序创建的快捷方式，无需清理。', 'i')
        else:
            self.say('将删除以下快捷方式：')
            for p in existing:
                self.say(f'    {p}')
        if purge:
            self.say('')
            self.say('--purge 还会删除运行环境与日志（不动你的小说项目数据）：', '!')
            for p in self._purge_targets():
                if p.exists():
                    self.say(f'    {p}')
        self.say('')
        self.say(f'小说项目数据始终保留：{self.projects_dir}', 'i')
        if self.dry_run:
            self.say('演练模式：未做任何删除', 'i')
            return True
        if not assume_yes:
            # ★★ 问不出来就**明说**，不要假装问过了（2026-10-10 用户报的那个 bug）
            # [EN] ★★ If it cannot ask, **say so explicitly**; do not pretend the question was asked (the bug
            # [EN] reported by the user on 2026-10-10)
            # ------------------------------------------------------------------
            # 这里原来直接 `input(...)`，`except EOFError: ans = ''` ⇒ 当成 "N"
            # ⇒ 打印"已取消"、返回 False ⇒ 退出码 1 ⇒ 用户看到的是
            # [EN] This used to call `input(...)` directly, with `except EOFError: ans = ''` ⇒ treated as "N"
            # [EN] ⇒ prints "cancelled", returns False ⇒ exit code 1 ⇒ what the user sees is
            # 「The step "Removing desktop icon / Start Menu entry" did not succeed.」
            # —— 一句话都指不到"其实是因为问不出来"。
            # 被图形化启动器拉起时**必然**走到这条路（没有终端），
            # 也就是说 double-click 卸载**从来没成功过**。
            # 实测：`platform_install.py uninstall < /dev/null` 稳定 `EXIT=1`。
            # [EN] —— not a single word points to "it's actually because the question couldn't be asked".
            # [EN] When launched by a graphical launcher, this path is **always** taken (no terminal),
            # [EN] in other words, double-click uninstall **has never succeeded**.
            # [EN] Measured: `platform_install.py uninstall < /dev/null` reliably gives `EXIT=1`.
            #
            # 现在把它**命名**出来：调用方（`uninstall.exe`）看到这句就知道该传
            # `--yes`，而它确实会先用自己的原生确认框问过、再带 `--yes` 调这里。
            # [EN] Now **name** it: the caller (`uninstall.exe`) sees this line and knows to pass
            # [EN] `--yes`, and it does first ask via its own native confirmation dialog, then call here with
            # [EN] `--yes`.
            ans = _ask_yes_no('  确认卸载？[y/N] Confirm uninstall? [y/N] ')
            if ans is None:
                self.say('没有可以询问的终端 ⇒ 请加 `--yes` 明确确认'
                         '（图形界面版卸载会先弹确认框，再带 --yes 调这里）', 'X')
                return False
            if ans not in ('y', 'yes'):
                self.say('已取消。')
                return False

        removed = self._remove_many(existing)
        if purge:
            removed += self._remove_many([p for p in self._purge_targets()
                                          if p.exists()])
        if self.manifest_path.exists():
            self.manifest_path.unlink()
            removed.append(str(self.manifest_path))
        self.say('')
        self.say(f'已删除 {len(removed)} 项。', 'OK')
        return True

    def _targets(self) -> list[str]:
        """要删除的路径。用**确定性路径推算**，不依赖 manifest，避免清单丢失后删不掉。
                English:
        The path to delete. Use **deterministic path derivation**, not relying on a manifest, to avoid
        being unable to delete after the manifest is lost.
        """
        if self.plat == 'windows':
            sm = self._sm_folder()
            return [
                str(self.desktop_dir / f'{APP_ZH}.lnk'),
                str(sm / f'{APP_ZH}.lnk'),
                str(sm / '打开项目文件夹.lnk'),
                str(sm / '使用说明.lnk'),
                str(sm / f'卸载 {APP_ZH}.lnk'),
                str(sm),
            ]
        if self.plat == 'macos':
            apps = self._d('Applications') / f'{APP_ZH}.app'
            return [str(self.desktop_dir / APP_ZH), str(apps)]
        apps_dir = self._d('.local', 'share', 'applications')
        return [
            str(self.desktop_dir / f'{SLUG}.desktop'),
            str(apps_dir / f'{SLUG}.desktop'),
            str(apps_dir / f'{SLUG}-uninstall.desktop'),
            str(self._d('.local', 'share', 'icons', 'hicolor', '256x256',
                        'apps', f'{SLUG}.png')),
        ]

    def _purge_targets(self) -> list[Path]:
        return [self.root / '.venv', self.root / 'logs',
                self.root / 'assets' / 'screenshots']

    def _remove_many(self, paths: list[Path]) -> list[str]:
        done: list[str] = []
        if self.plat == 'windows':
            # 路径通过 JSON 文件传给 PowerShell：中文/空格/单引号都不会出问题
            # [EN] Paths are passed to PowerShell via a JSON file: Chinese/spaces/single quotes all work fine
            body = '\n'.join([
                '$gone = New-Object System.Collections.ArrayList',
                '$errs = New-Object System.Collections.ArrayList',
                'foreach ($p in @($job.paths)) {',
                '  try {',
                '    if (Test-Path -LiteralPath $p) {',
                '      Remove-Item -LiteralPath $p -Force -Recurse',
                '    }',
                '    if (-not (Test-Path -LiteralPath $p)) { [void]$gone.Add($p) }',
                '    else { [void]$errs.Add("still there: $p") }',
                '  } catch { [void]$errs.Add("$p : $_") }',
                '}',
                '@{ gone = @($gone); errors = @($errs) } | ConvertTo-Json -Depth 4 | '
                'Set-Content -LiteralPath $res -Encoding UTF8',
            ])
            rc, msg, data = ps_job(body, {'paths': [str(p) for p in paths]})
            if data.get('errors'):
                for e in data['errors']:
                    self.say(f'删除失败: {e}', 'X')
            for p in (data.get('gone') or []):
                done.append(str(p))
                self.say(f'已删除: {p}')
            if rc != 0 and not data:
                self.say(f'删除失败（PowerShell 退出码 {rc}）', 'X')
                if msg:
                    self.say(msg[:600])
            return done

        for p in paths:
            if self._remove_silent(p):
                done.append(str(p))
                self.say(f'已删除: {p}')
        return done

    @staticmethod
    def _remove_silent(p: Path) -> bool:
        try:
            if p.is_symlink() or p.is_file():
                p.unlink()
                return True
            if p.is_dir():
                shutil.rmtree(p)
                return True
        except OSError as e:
            self.say(f'删除失败 {p}: {e}', 'X')
        return False

    # ══════════════════════════════════════════════════════════
    #  状态
    # [EN] Status
    # ══════════════════════════════════════════════════════════
    def status(self) -> bool:
        # ⚠ 一律走 `self.say()` —— 它是双语的**唯一出口**；
        #   这一块原来是直接 `print` 的，那样双语化会漏掉整个 status。
        # [EN] ⚠ Always go through `self.say()` —— it is the **sole outlet** for bilingual output;
        # [EN] this block used to call `print` directly, which would leave the entire status out of the
        # [EN] bilingual conversion.
        self.say(f'平台: {self.plat}')
        self.say(f'程序目录: {self.root}')
        self.say(f'启动脚本: {self.start_script} '
                 f'({"存在" if self.start_script.exists() else "缺失"})')
        self.say(f'.ico 图标: {self.icon_ico() or "缺失"}')
        self.say(f'PNG 图标: {self.icon_png() or "缺失"}')
        self.say(f'小说项目目录: {self.projects_dir}')
        self.say('快捷方式:')
        for p in self._targets():
            q = Path(p)
            mark = '有' if (q.exists() or q.is_symlink()) else '无'
            self.say(f'    [{mark}] {p}')
        m = read_json(self.manifest_path)
        self.say(f'安装记录: {self.manifest_path} '
                 f'({"有，安装于 " + str(m.get("installed_at")) if m else "无"})')
        return True


def ps_run_for_osascript(script: str) -> tuple[int, str]:
    """在 macOS 上跑一段 AppleScript。
        English:
    Run a piece of AppleScript on macOS.
    """
    try:
        p = _run(['osascript', '-e', script],
                           capture_output=True, timeout=60)
    except Exception as e:                                    # pragma: no cover
        return 127, str(e)
    return p.returncode, (p.stdout or b'').decode('utf-8', 'replace').strip()


# ══════════════════════════════════════════════════════════════
#  入口
# [EN] Entry point
# ══════════════════════════════════════════════════════════════
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog='platform_install.py',
        description=f'{APP_ZH} / {APP_EN} —— 桌面图标与开始菜单的安装/卸载'
                    ' | install and uninstall desktop icons and Start Menu entries')
    ap.add_argument('action', choices=['install', 'uninstall', 'status'])
    ap.add_argument('--purge', action='store_true',
                    help='卸载时一并删除 .venv / logs / 截图（不动小说项目数据）'
                         ' | also remove .venv, logs and screenshots '
                         '(novel projects untouched)')
    ap.add_argument('--yes', '-y', action='store_true',
                    help='跳过确认 | skip the confirmation prompt')
    ap.add_argument('--dry-run', action='store_true',
                    help='只显示将要做的改动，不写任何文件'
                         ' | show what would change, write nothing')
    ap.add_argument('--dest-root', default=None,
                    help='把桌面/开始菜单/Applications 的根换到这里（自动化测试用）'
                         ' | put the Desktop / Start Menu / Applications root here '
                         '(for automated tests)')
    ap.add_argument('--quiet', action='store_true')
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inst = Installer(dest_root=Path(args.dest_root) if args.dest_root else None,
                     dry_run=args.dry_run, verbose=not args.quiet)
    if args.action == 'install':
        return 0 if inst.install() else 1
    if args.action == 'uninstall':
        return 0 if inst.uninstall(purge=args.purge, assume_yes=args.yes) else 1
    return 0 if inst.status() else 1


if __name__ == '__main__':
    sys.exit(main())
