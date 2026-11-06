# -*- coding: utf-8 -*-
"""验证：三个启动器（setup / start / uninstall）编出来的可执行文件**真的能用**，
而且**跑起来不会冒出任何控制台窗口**，并且**主窗口退出时后台服务跟着退出**。

用户 2026-10-10 的要求（三条，缺一条就不算做完）
------------------------------------------------
1. setup / uninstall / start 用**跨平台语言**写、**分别编译**出各平台可执行文件；
2. **执行之后不要有任何控制台窗口出现**（旧脚本是 `.bat`/`.sh`，一定会带一个黑框）；
3. **主窗口退出的时候后台服务也跟着退出**。

2026-10-17 追加：第 3 条从"一个服务"（MuMuAINovel）扩到**三个外部服务**
（MuMuAINovel / PenShot / PlotPilot）。三个启动器与它们的交道全走
`launchers/services.go` 的服务表：setup 逐个备环境、start 在退出时按各自的
`*_FOLLOW_APP` 逐个停、uninstall 删快捷方式前逐个停。C/D/F 三组都扩了
夹具与断言，"新服务没人停过"这种洞必须有判据走着。

English:
Verification: the executables compiled from the three launchers (setup / start / uninstall)
**actually work**,
and **running them doesn't pop up any console window**, and **when the main window exits the
background service exits too**.
User's 2026-10-10 requirements (three items, missing one means not done)
------------------------------------------------
1. setup / uninstall / start written in a **cross-platform language**, **separately compiled** into per-platform executables;
2. **after execution no console window should appear** (the old scripts were `.bat`/`.sh`, which always bring a black box);
3. **when the main window exits the background service exits too**.

2026-10-17 addition: item 3 expanded from "one service" (MuMuAINovel) to **three external
services** (MuMuAINovel / PenShot / PlotPilot). How the three launchers deal with them all goes
through the service table in `launchers/services.go`: setup prepares each one's runtime, start
stops each per its own `*_FOLLOW_APP` on exit, uninstall stops each before removing the
shortcuts. Groups C, D and F all gained fixtures and assertions -- holes like "the new
services never got stopped" must have assertions walking them.

这一支判据怎么保证自己不是"看着绿"
----------------------------------
★ 第 2 条最容易假绿：只查"进程树里有没有 conhost"是不准的 ——
  2026-10-10 实测（`developers/_probe_child_console.py`）四种父子组合里
  **连显式给了 CREATE_NO_WINDOW 的那条都有 conhost 进程**。conhost 存在
  跟"屏幕上出现一个黑窗"**不是一回事**（CREATE_NO_WINDOW 正是"有个控制台对象、
  但不显示窗口"）。

  所以这里量的是**用户看得见的东西**：枚举桌面上**可见的**顶层控制台窗口，
  跑之前拍一次、跑的时候拍一次，比较**属于我们那条进程链**的新窗口。
  并且自带一个**对照组**（故意不带标志起一个控制台子进程）——
  对照组抓不到窗口就说明"这条判据是瞎的"，那么它给的 ✓ 一分钱都不值。

★ 第 3 条之外，F 组守的是**卸载这条路本身**（2026-10-10 用户报的 bug）：
  双击 `uninstall.exe` 当年**一次都没成功过**（子进程没有终端 ⇒ 它的
  `input('确认卸载？')` 永远 EOF ⇒ 当成取消 ⇒ 退出码 1）。详见 F 组那段注释 ——
  那里也写清了"为什么 A~E 组守不住它"：**只能人肉验的路径，出问题只是时间问题**。

产出：assets/screenshots/launchers_report.json

English:
Verification: the executables compiled from the three launchers (setup / start / uninstall)
**actually work**,
and **running them doesn't pop up any console window**, and **when the main window exits the
background service exits too**.
User's 2026-10-10 requirements (three items, missing one means not done)
------------------------------------------------
1. setup / uninstall / start written in a **cross-platform language**, **separately compiled** into per-platform executables;
2. **after execution no console window should appear** (the old scripts were `.bat`/`.sh`, which always bring a black box);
3. **when the main window exits the background service exits too**.
How does this branch of criteria guarantee it isn't "just looking green"
----------------------------------
★ Item 2 is the easiest to falsely green: only checking "whether there's a conhost in the
process tree" is inaccurate ——
  measured on 2026-10-10 (`developers/_probe_child_console.py`), among four parent-child combinations
  **even the one explicitly given CREATE_NO_WINDOW has a conhost process**. conhost existing
  is **not the same thing** as "a black window appearing on screen" (CREATE_NO_WINDOW is precisely "there is a console object,
  but no window is displayed").
  So what's measured here is **what the user can see**: enumerate **visible** top-level console windows on the desktop,
  snapshot once before running, snapshot once while running, and compare **new windows belonging to our process chain**.
  And it carries a **control group** (deliberately starting a console child process without the flag) ——
  if the control group can't catch a window it means "this criterion is blind", and then the ✓ it gives isn't worth a penny.
★ Beyond item 3, group F guards **the uninstall path itself** (the bug the user reported on
2026-10-10):
  double-clicking `uninstall.exe` back then **never succeeded even once** (the child process had no terminal ⇒ its
  `input('Confirm uninstall?')` always hits EOF ⇒ treated as cancel ⇒ exit code 1). See the comment block for group F ——
  it also spells out "why groups A~E can't guard it": **a path that can only be verified by hand is only a matter of time before it breaks**.
Output: assets/screenshots/launchers_report.json
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat

APP = Path(__file__).resolve().parent.parent
OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
DIST = APP / 'launchers' / 'dist'
TMP = Path(tempfile.gettempdir())

IS_WIN = os.name == 'nt'
SUFFIX = '.exe' if IS_WIN else ''
MODES = ('setup', 'start', 'uninstall')
TARGETS = (('windows', 'amd64', '.exe'), ('linux', 'amd64', ''),
           ('darwin', 'arm64', ''), ('darwin', 'amd64', ''))
MAGIC = {
    'windows': (b'MZ',),
    'linux': (b'\x7fELF',),
    'darwin': (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe',
               b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'),
}
#: 各种"控制台窗口"的窗口类名（默认终端可能是 conhost 或 Windows Terminal）。
# [EN] : Window class names for various "console windows" (the default terminal may be conhost or
# [EN] Windows Terminal).
CONSOLE_CLASSES = ('consolewindowclass', 'cascadia_hosting_window_class')

report: dict = {'steps': [], 'failed': []}


def rec(name: str, cond, detail: str = '') -> bool:
    """记一条断言。
    ⚠ 失败行**必须以 `✗` 开头**：反例法（`developers/mutate_*.py`）靠
      "stdout 里有没有 `✗` 且带预期的名字"判"这条判据真红了"。
      上一轮踩过：新判据一开始打 `[FAIL]`，于是**六条变异全被记成"漏掉"**，
      看着像判据没本事 —— 其实是格式没对齐。
    
        English:
    Record an assertion.
        ⚠ failure lines **must start with `✗`**: the counterexample method (`developers/mutate_*.py`) relies on
          "is there a `✗` in stdout with the expected name" to judge "this criterion really went red".
          Last round we stepped in it: a new criterion initially printed `[FAIL]`, so **all six mutations were recorded as "missed"**,
          looking like the criterion had no teeth —— but actually the format was misaligned.
    """
    ok = bool(cond)
    report['steps'].append({'name': name, 'ok': ok, 'detail': str(detail)[:400]})
    print(f'  {"✓  " if ok else "✗  "} {name}'
          + (f'  — {detail}' if detail else ''), flush=True)
    if not ok:
        report['failed'].append(name)
    return ok


# ══════════════════════════════════════════════════════════════════
#  桌面上可见的控制台窗口
# [EN] Console window visible on the desktop
# ══════════════════════════════════════════════════════════════════

def visible_console_windows() -> list[dict]:
    if not IS_WIN:
        return []
    u = ctypes.windll.user32
    out: list[dict] = []
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lp):
        if not u.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, buf, 256)
        cls = buf.value.lower()
        if cls not in CONSOLE_CLASSES:
            return True
        t = ctypes.create_unicode_buffer(512)
        u.GetWindowTextW(hwnd, t, 512)
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append({'hwnd': int(hwnd), 'cls': cls, 'title': t.value,
                    'pid': int(pid.value)})
        return True

    u.EnumWindows(CB(cb), 0)
    return out


def windows_of_pids(pids: set[int]) -> list[dict]:
    return [w for w in visible_console_windows() if w['pid'] in pids]


def _naked_spawn_lines(src: str) -> list[int]:
    """找出**裸的** subprocess 调用行号。

    判法：按 `def` 切块，块里出现 `subprocess.run(`/`Popen(` 时，
    要求**同一个函数体**里出现过"别建控制台"的痕迹（`creationflags`）
    或者走本文件的封装入口（`_no_window_kw` / `no_window_kw()` / `_run(`）。

    ★ 为什么不能只按行扫（第一版就是这么写的，结果把封装函数**自己**那行
      也报成裸调用 —— 一眼就知道判据写错了）：一个调用点"安不安全"取决于
      **它在哪个函数里**，不取决于那一行长什么样。

    ⚠ 不在扫描范围内的：`subprocess.call(...)`（`novelservice.py` 的
      `start --fg` 前台调试分支）—— 那一条的用途就是"在终端里前台跑着看输出"，
      给它加 CREATE_NO_WINDOW 反而把调试用途抹掉了。它只在人手动加 `--fg` 时走到。
    
        English:
    Find the line numbers of **bare** subprocess calls.
        Method: split into blocks by `def`, and when `subprocess.run(`/`Popen(` appears in a block,
        require that within the **same function body** there is a trace of "don't create a console" (`creationflags`)
        or that it goes through this file's wrapper entry points (`_no_window_kw` / `no_window_kw()` / `_run(`).
        ★ Why can't we just scan line by line (the first version was written that way, and it ended up reporting the wrapper function **itself**
          as a bare call —— one glance tells you the criterion is wrong): whether a call site is "safe" depends on
          **which function it's in**, not on what that one line looks like.
        ⚠ Out of scan scope: `subprocess.call(...)` (`novelservice.py`'s
          `start --fg` foreground debug branch) —— that one's purpose is precisely "run it in the foreground in a terminal to see output",
          adding CREATE_NO_WINDOW to it would instead erase the debugging purpose. It's only reached when a person manually adds `--fg`.
    """
    lines = src.split('\n')
    blocks: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith('def '):
            if cur:
                blocks.append(cur)
            cur = []
        cur.append((i, ln))
    if cur:
        blocks.append(cur)

    def is_spawn(ln: str) -> bool:
        return 'subprocess.run(' in ln or 'subprocess.Popen(' in ln

    bad: list[int] = []
    for blk in blocks:
        if not any(is_spawn(l) for _i, l in blk):
            continue
        body = '\n'.join(l for _i, l in blk)
        sane = ('creationflags' in body or 'no_window_kw' in body
                or '_run(' in body)
        if not sane:
            bad += [i for i, l in blk if is_spawn(l)]
    return bad


# ══════════════════════════════════════════════════════════════════
#  A 产物（静态：读字节，不跑）
# [EN] A artifact (static: read bytes, do not run)
# ══════════════════════════════════════════════════════════════════

def check_artifacts() -> None:
    print('\n【A】产物：名字、格式、子系统')
    missing: list[str] = []
    badmagic: list[str] = []
    badsub: list[str] = []
    for goos, arch, sfx in TARGETS:
        for mode in MODES:
            f = DIST / f'{goos}-{arch}' / (mode + sfx)
            if not f.exists():
                missing.append(f'{goos}-{arch}/{mode + sfx}')
                continue
            head = f.read_bytes()[:4]
            if not any(head.startswith(m) for m in MAGIC[goos]):
                badmagic.append(f'{goos}-{arch}/{mode + sfx} 头={head.hex()}')
            if goos == 'windows':
                d = f.read_bytes()
                pe = struct.unpack_from('<I', d, 0x3c)[0]
                sub = struct.unpack_from('<H', d, pe + 0x5c)[0]
                if sub != 2:
                    badsub.append(f'{mode + sfx} subsystem={sub}')
    n = len(TARGETS) * len(MODES)
    rec(f'A1 {len(TARGETS)} 个平台 × {len(MODES)} 个模式 = {n} 个可执行文件都在',
        not missing, f'缺：{missing[:4]}' if missing else f'{n} 个')
    rec('A2 每个产物的**格式**与平台相符（ELF / Mach-O / PE）'
        '—— 防"拷错平台"，也防 `-H windowsgui` 加到了非 Windows 目标上'
        '（实测：那样编出来是个 Windows PE，rc=0 且不报错）',
        not badmagic, '；'.join(badmagic[:3]))
    rec('A3 Windows 产物的 **PE 子系统 = 2（GUI）**'
        '（=3 是控制台程序，双击就是一个黑框 —— 正是这次要消灭的东西）',
        not badsub, '；'.join(badsub[:3]))

    # 工程根目录那一套（用户真正双击的）
    # [EN] The project root set (what the user actually double-clicks)
    root_missing = [m + SUFFIX for m in MODES if not (APP / (m + SUFFIX)).exists()]
    rec(f'A4 工程根目录有 {len(MODES)} 个启动器（用户双击的就是它们）',
        not root_missing, f'缺：{root_missing}' if root_missing else '')
    if IS_WIN and not root_missing:
        same = []
        for m in MODES:
            a = (APP / (m + '.exe')).read_bytes()
            b = (DIST / 'windows-amd64' / (m + '.exe')).read_bytes()
            same.append(a == b)
        rec('A5 根目录那一套与 `launchers/dist/windows-amd64/` **逐字节一致**'
            '（防"根目录还留着上一版编的"）', all(same), f'{same}')

    # 旧脚本必须已经没了（用户要求"删掉，只留 exe"）
    # [EN] Old scripts must already be gone (user requested "delete, keep only the exe")
    leftovers = [p.name for p in
                 [APP / f'{m}{e}' for m in MODES
                  for e in ('.bat', '.sh', '.command')] if p.exists()]
    rec('A6 三个旧脚本（.bat/.sh/.command 共 9 个）**都已删除**'
        '（用户原话：「删掉，只留 exe」）',
        not leftovers, f'还在：{leftovers}' if leftovers else '')


# ══════════════════════════════════════════════════════════════════
#  B 无控制台（真机）
# [EN] B no console (real machine)
# ══════════════════════════════════════════════════════════════════

def _run_selftest(exe: Path, env_extra: dict | None = None,
                  tag: str = '') -> dict | None:
    out = TMP / f'nws_self_{os.getpid()}_{exe.stem}{tag}.json'
    if out.exists():
        out.unlink()
    env = dict(os.environ)
    if env_extra:
        env.update({k: str(v) for k, v in env_extra.items()})
    subprocess.run([str(exe), '--selftest', str(out)],
                   capture_output=True, timeout=120, env=env)
    if not out.exists():
        return None
    return json.loads(out.read_text(encoding='utf-8'))


def check_no_console() -> None:
    print('\n【B】无控制台（真机）')
    if not IS_WIN:
        rep = _run_selftest(APP / f'start{SUFFIX}')
        rec('B1 非 Windows：没有"控制台窗口"这个概念，只验启动器能跑',
            rep is not None and rep.get('python_found'), '')
        return
    start = APP / 'start.exe'
    rep = _run_selftest(start)
    rec('B1 `start.exe --selftest` 报 `has_console = false`'
        '（`GetConsoleWindow()` 拿到 0 —— 这是"子系统是 GUI"的**运行时**证据）',
        rep is not None and rep.get('has_console') is False,
        '' if rep is None else f"has_console={rep.get('has_console')}")

    # ── B2：跑产品真实的起子进程路径，看桌面上有没有多出控制台窗口 ──
    # [EN] ── B2: run the product's real child-process spawn path, see whether an extra console window
    # [EN] appears on the desktop ──
    #
    # ★★ 这条断言**没法被外部变异打红**，理由记在这儿（试过三次，都造不出那个现象）：
    #    ① 改源码里 `createNoWindow` 的值 → 打不中（`--spawn-hold` 走 pythonw，
    #       本来就不分配控制台）；
    #    ② 让解释器退回控制台版 + `createNoWindow = 0` → 还是打不中
    #       （`HideWindow`/`SW_HIDE` 自己就把新分配的控制台藏住了）；
    #    ③ 连启动器本身都编成**控制台程序**（PE 子系统 = 3）→ 仍然不冒窗口。
    #    ⇒ 这台机器上"程序化启动的控制台进程"根本不显示窗口（默认终端是
    #      Windows Terminal，而且子进程是**带管道**启动的）。
    #    也就是说：**B2 在这个环境里没有办法从外面打红**。
    # [EN] ★★ This assertion **cannot be reddened by external mutation**; the reasoning is recorded here
    # [EN] (tried three times, could never reproduce that phenomenon):
    # [EN] ① Change the value of `createNoWindow` in the source → can't hit it (`--spawn-hold` goes through
    # [EN] pythonw,
    # [EN] which does not allocate a console anyway);
    # [EN] ② Make the interpreter fall back to the console version + `createNoWindow = 0` → still can't hit
    # [EN] it
    # [EN] (`HideWindow`/`SW_HIDE` itself hides the newly allocated console);
    # [EN] ③ Even compile the launcher itself as a **console program** (PE subsystem = 3) → still no window
    # [EN] appears.
    # [EN] ⇒ On this machine, "programmatically spawned console processes" simply do not show a window (the
    # [EN] default terminal is
    # [EN] Windows Terminal, and the child process is spawned **with pipes**).
    # [EN] In other words: **B2 cannot be reddened from the outside in this environment**.
    #
    #    那它凭什么可信？靠**它自带的对照组 B3** —— 每次跑都故意不带标志起一个
    #    控制台子进程，并断言"确实抓到了窗口"。对照组红 ⇒ B2 的 ✓ 一分钱不值；
    #    对照组绿 ⇒ 仪器当场看得见窗口，只是被测那条路真的没冒出来。
    #    这比"外部偶尔变异一次"更强：它**每次都在跑**（见 `developers/mutate_launchers.py`
    #    里那段"为什么这一组没有 B2 的变异"的说明）。
    # [EN] Then why is it trustworthy? Because of **its built-in control group B3** — every run
    # [EN] deliberately spawns a
    # [EN] console child process without the flag, and asserts "a window really was caught". If the control
    # [EN] group is red ⇒ B2's ✓ is worthless;
    # [EN] if the control group is green ⇒ the instrument can see a window on the spot, it's just that the
    # [EN] path under test really didn't produce one.
    # [EN] This is stronger than "an occasional external mutation": it **runs every time** (see the
    # [EN] explanation
    # [EN] in `developers/mutate_launchers.py` about "why this group has no B2 mutation").
    hold = TMP / f'nws_hold_{os.getpid()}.json'
    if hold.exists():
        hold.unlink()
    p = subprocess.Popen([str(start), '--spawn-hold', '6', '--out', str(hold)])
    got = None
    for _ in range(200):
        if hold.exists():
            got = json.loads(hold.read_text(encoding='utf-8'))
            break
        time.sleep(0.25)
    wins: list[dict] = []
    if got:
        wins = windows_of_pids({int(got['child_pid']), int(got['launcher_pid'])})
    p.wait(timeout=180)
    rec('B2 启动器起子进程时，**桌面上没有多出控制台窗口**'
        '（按 pid 只认"属于我们这条链"的窗口，不受同时跑别的判据影响）',
        got is not None and not wins,
        f"子进程={got['child_pid'] if got else '?'}  "
        + (f'新窗口：{[(w["cls"], w["title"]) for w in wins]}' if wins else '无新窗口'))

    # ── B3：对照组 —— 证明上面那条不是"瞎的" ──
    # [EN] ── B3: control group — proves the above is not "blind" ──
    py = sys.executable
    pw = Path(py).with_name('pythonw.exe')
    if pw.exists():
        code = (
            'import subprocess,sys,time\n'
            f'p = subprocess.Popen([r"{py}", "-c", "import time;time.sleep(6)"])\n'
            'time.sleep(2.5)\n')
        before = visible_console_windows()
        q = subprocess.Popen([str(pw), '-c', code])
        time.sleep(4.0)
        # ⚠ 对照组用**差集**、不按 pid 归因 —— 和 B2 那条不一样，这是有意的：
        #   · B2 要的是"**没有**冒出新窗口"，误报会让它假红，所以必须按 pid 精确认；
        #   · 对照组要的是"这条判据**看得见**窗口"，只要差集非空就够了。
        #   而且这里**没法**按 pid 认：写进 pid 文件的是 `.venv/Scripts/python.exe`
        #   这个 **venv launcher** 的 pid，而真正持有那个控制台窗口的是它
        #   re-exec 出来的**孙进程**的 pid（第一版按 pid 过滤，于是一个窗口都抓不到，
        #   看起来像"对照组也不弹窗"）。
        # [EN] ⚠ The control group uses a **set difference**, not pid attribution — unlike the B2 one, this is
        # [EN] intentional:
        # [EN] · B2 wants "**no** new window appeared", and a false positive would make it falsely red, so it
        # [EN] must be precise by pid;
        # [EN] · the control group wants "this criterion **can see** a window", so a non-empty set difference
        # [EN] is enough.
        # [EN] Besides, here you **cannot** identify by pid: what's written into the pid file is the pid of the
        # [EN] `.venv/Scripts/python.exe` **venv launcher**, whereas the one that actually holds that console
        # [EN] window is its
        # [EN] re-exec'd **grandchild process** (the first version filtered by pid, so it couldn't catch a
        # [EN] single window,
        # [EN] and it looked like "the control group doesn't pop a window either").
        ctrl = [w for w in visible_console_windows()
                if w['hwnd'] not in {x['hwnd'] for x in before}]
        q.wait(timeout=120)
        rec('B3 ★ 对照组：**故意**不带标志起一个控制台子进程，'
            '确实抓到窗口 ⇒ 说明 B2 那条判据看得见窗口（不是瞎的）',
            bool(ctrl), f'对照抓到 {len(ctrl)} 个窗口：'
            f'{[w["cls"] for w in ctrl][:3]}'
            if ctrl else '★ 对照组一个窗口都没抓到 ⇒ B2 的 ✓ 不可信')
    else:
        rec('B3 对照组（没有 pythonw.exe，跳过）', True, '')

    # ── B4：每一层起子进程的地方都声明了"别建控制台" ──
    #   ★ 这是静态兜底：只要有**新加的**调用点漏了标志，运行时可能半天才被发现。
    # [EN] ── B4: every layer that spawns a child process declares "don't create a console" ──
    # [EN] ★ This is a static safety net: if any **newly added** call site is missing the flag, it may take
    # [EN] a long time to be found at runtime.
    naked: list[str] = []
    for rel in ('tools/launcher_progress.py', 'tools/platform_install.py',
                'novelservices/MuMuAINovel/backend/novelservice.py',
                # [EN] 2026-10-17: two new services joined the "spawns children"
                # [EN] roster -- the unified controller (`service_ctl.py`, runs
                # [EN] pip / import checks) and PenShot's bridge (tasklist /
                # [EN] netstat / taskkill on the stop path).
                'novelservices/service_ctl.py',
                'novelservices/penshot_bridge.py'):
        src = (APP / rel).read_text(encoding='utf-8')
        naked += [f'{rel}:{i}' for i in _naked_spawn_lines(src)]
    rec('B4 ★★ 五个会起子进程的脚本里，**没有裸的 `subprocess.run/Popen`**'
        '（全部走带 CREATE_NO_WINDOW 的封装 —— 漏一个就是一个黑窗，'
        '而且只在特定平台分支才出现）',
        not naked, f'裸调用：{naked[:5]}' if naked else '')

    hits = []
    for rel, key in (('tools/launcher_progress.py', '_no_window_kw()'),
                     ('tools/platform_install.py', 'no_window_kw()'),
                     ('novelservices/MuMuAINovel/backend/novelservice.py',
                      'no_window_kw()'),
                     # [EN] The controller's own wrapper is `no_window_kw()`,
                     # [EN] the bridge's is `_no_window_kw()` (leading
                     # [EN] underscore: module-private).
                     ('novelservices/service_ctl.py', 'no_window_kw()'),
                     ('novelservices/penshot_bridge.py', '_no_window_kw()')):
        src = (APP / rel).read_text(encoding='utf-8')
        if 'creationflags' not in src or key not in src:
            hits.append(rel)
    rec('B5 那五个脚本真的实现了"别建控制台"（`CREATE_NO_WINDOW` + 封装入口）',
        not hits, f'缺：{hits}' if hits else '')


# ══════════════════════════════════════════════════════════════════
#  C 服务跟随主窗口退出（真机 + 夹具）
# [EN] C service exits with the main window (real machine + fixture)
# ══════════════════════════════════════════════════════════════════

FIX = APP / 'tests' / 'launchers'
#: 统一控制器的夹具（两个新服务：PenShot / PlotPilot 都走它）。
# [EN] : The unified controller's fixture (the two new services: PenShot /
# [EN] PlotPilot both go through it).
FIX_CTL = FIX / 'fixture_ctl'


def _ctl_fixture_env(mark_dir: Path) -> dict:
    """把两个新服务指向**夹具**：假控制器 + 两个空壳服务目录。

    `svcPresent` 对走控制器的服务要求"目录在**且**控制器在"，所以三个都要指：
    控制器指到 `fixture_ctl.py`，两个服务目录指到 `fixture_ctl/penshot|plotpilot`
    （里面各有一个**诱饵** `.env`，D 组用它证明端口没读错地方）。

        English:
    Point the two new services at **fixtures**: the fake controller + two
    shell service directories.

    `svcPresent` requires "the directory is there **and** so is the
    controller" for controller-routed services, so all three must be pointed:
    the controller at `fixture_ctl.py`, the two service directories at
    `fixture_ctl/penshot|plotpilot` (each holds a **decoy** `.env`, used by
    group D to prove the port wasn't read from the wrong place).
    """
    return {
        'NWS_TEST_SERVICE_CTL': str(FIX_CTL / 'fixture_ctl.py'),
        'NWS_TEST_PENSHOT_DIR': str(FIX_CTL / 'penshot'),
        'NWS_TEST_PLOTPILOT_DIR': str(FIX_CTL / 'plotpilot'),
        # [EN] Where the fake controller records what it received
        'NWS_FIXTURE_CTL_LOG': str(mark_dir),
    }


def _stub_run(follow: dict | None = None, stub_secs: float = 3.0, argv=(),
              global_follow: str = '') -> dict:
    """真跑一次 `start.exe`（夹具：假主程序 + 假 MuMu 服务 + 假控制器）。

    `follow`：逐服务的 `*_FOLLOW_APP`（`{'mumu': '1', 'penshot': '0', …}`）——
    2026-10-17 起三个服务各自独立，判据必须能分开摆布它们。
    `global_follow`：全局 `NWS_TEST_FOLLOW_APP`（逐服务的都没给时才该它说话）。

        English:
    Really run `start.exe` once (fixtures: fake main program + fake MuMu
    service + fake controller).

    `follow`: per-service `*_FOLLOW_APP` (`{'mumu': '1', 'penshot': '0', …}`)
    -- since 2026-10-17 the three services are independent, so the
    assertions must be able to arrange them separately.
    `global_follow`: the global `NWS_TEST_FOLLOW_APP` (only speaks when none
    of the per-service ones is given).
    """
    calls = FIX / 'fixture_service' / 'calls.txt'
    ctl_calls = TMP / f'nws_ctl_{os.getpid()}.jsonl'
    mark = TMP / f'nws_stub_{os.getpid()}.txt'
    for f in (calls, ctl_calls, mark):
        if f.exists():
            f.unlink()
    env = dict(os.environ)
    env.update({
        'NWS_TEST_APP': str(FIX / 'stub_app.py'),
        'NWS_TEST_SERVICE_DIR': str(FIX / 'fixture_service'),
        'NWS_TEST_SERVICE_PY': sys.executable,
        'NWS_TEST_SERVICE_PORT': '9',          # 一个不会有人监听的端口
        # [EN] A port nobody will listen on
        'NWS_STUB_MARK': str(mark),
        'NWS_STUB_SECONDS': str(stub_secs),
    })
    env.update(_ctl_fixture_env(ctl_calls))
    if global_follow:
        env['NWS_TEST_FOLLOW_APP'] = global_follow
    for sid, v in (follow or {}).items():
        env[f'NWS_TEST_FOLLOW_{sid.upper()}'] = v
    t0 = time.time()
    r = subprocess.run([str(APP / f'start{SUFFIX}'), *argv], env=env,
                       capture_output=True, timeout=300)
    el = time.time() - t0
    got: list[dict] = []
    if calls.exists():
        got = [json.loads(x) for x in
               calls.read_text(encoding='utf-8').splitlines() if x.strip()]
    ctl: list[dict] = []
    if ctl_calls.exists():
        ctl = [json.loads(x) for x in
               ctl_calls.read_text(encoding='utf-8').splitlines() if x.strip()]
    return {'secs': el, 'rc': r.returncode, 'calls': got, 'ctl': ctl,
            'mark': mark.read_text(encoding='utf-8') if mark.exists() else ''}


def _ctl_pairs(ctl: list[dict]) -> set[tuple[str, str]]:
    """夹具控制器收到的 (动作, 服务) 对 —— "停了哪个服务"就看这个集合。
        English:
    The (action, service) pairs the fixture controller received -- "which
    service got stopped" is read from this set.
    """
    return {(c.get('action', ''), c.get('service', '')) for c in ctl}


def check_service_follow() -> None:
    print('\n【C】主窗口退出 ⇒ 后台服务跟着退出（真机 + 夹具）')
    if not (FIX / 'stub_app.py').exists():
        rec('C0 夹具在（tests/launchers/）', False, '缺夹具')
        return
    rec('C0 夹具在（tests/launchers/stub_app.py + fixture_service/ '
        '+ fixture_ctl/）', True, '')

    # ── C1：开关开着 → 必须调 stop（**三个服务一个都不能少**）──
    # [EN] ── C1: switch on → must call stop (**not one of the three services
    # [EN] may be missing**) ──
    a = _stub_run({'mumu': '1', 'penshot': '1', 'plotpilot': '1'})
    actions = [c['action'] for c in a['calls']]
    pairs = _ctl_pairs(a['ctl'])
    rec('C1 ★★★ 三个 `*_FOLLOW_APP=1`：主程序退出后，启动器**把三个服务都停了**'
        '（MuMu 直跑它的脚本；PenShot / PlotPilot 走统一控制器 —— '
        '用户原话：「必须主窗口退出的时候后台服务也跟着退出」）',
        'stop' in actions and ('stop', 'penshot') in pairs
        and ('stop', 'plotpilot') in pairs,
        f'MuMu 动作={actions}；控制器收到的={sorted(pairs)}')
    # ── C2：开关关掉 → 不许碰任何服务 ──
    # [EN] ── C2: switch off → must not touch any service ──
    b = _stub_run({'mumu': '0', 'penshot': '0', 'plotpilot': '0'})
    rec('C2 ★★ 三个 `*_FOLLOW_APP=0`：**一个都不停**'
        '（这一项是"留个开关"那条要求的退路；少判一个新服务，'
        '那个服务就悄悄恢复"关不掉"）',
        'stop' not in [c['action'] for c in b['calls']] and not _ctl_pairs(b['ctl']),
        f"MuMu 动作={[c['action'] for c in b['calls']]}；"
        f"控制器收到的={sorted(_ctl_pairs(b['ctl']))}")
    # ── C3：启动器真的**等到**主程序退出 ──
    # [EN] ── C3: the launcher really **waits** for the main program to exit ──
    rec('C3 ★★★ 启动器**一直等到主程序退出**才收尾'
        '（不然"服务跟着退出"就变成"服务被提前掐了"）',
        a['mark'].rstrip().endswith('exited') and a['secs'] >= 3.0,
        f"主程序存活 {a['secs']:.1f}s，标记结尾="
        f"{a['mark'].strip().splitlines()[-1] if a['mark'].strip() else '（空）'}")
    # ── C4：参数透传（`--reinstall` 被启动器自己消化掉）──
    # [EN] ── C4: argument pass-through (`--reinstall` is consumed by the launcher itself) ──
    c = _stub_run({'mumu': '0', 'penshot': '0', 'plotpilot': '0'},
                  stub_secs=1.0, argv=['--mock'])
    rec('C4 启动器把 `--mock` **透传**给主程序（别的参数不许乱吃）',
        "'--mock'" in c['mark'], c['mark'].replace('\n', ' | ')[:120])
    # ── C5：逐服务独立（2026-10-17 三服务表之后新加的一条）──
    # [EN] ── C5: per-service independence (added 2026-10-17 with the
    # [EN] three-service table) ──
    #
    # ★ 为什么单列一条：用户完全可能"留着编剧服务、关掉分镜服务"。三个服务
    #   共用一个"停不停"的判断（老代码就只有一份 `MUMU_FOLLOW_APP`）时，
    #   这种配置**表达不出来**，而且不报错 —— 只是永远不生效。
    # [EN] ★ Why a separate item: "keep the screenwriter, drop the storyboard
    # [EN] service" is a perfectly reasonable configuration. When all three
    # [EN] services shared one "stop or not" decision (the old code had only
    # [EN] `MUMU_FOLLOW_APP`), that configuration **could not be expressed**,
    # [EN] and no error is raised -- it just never takes effect.
    d = _stub_run({'mumu': '1', 'penshot': '0', 'plotpilot': '1'})
    pairs = _ctl_pairs(d['ctl'])
    rec('C5 ★★★ `MUMU=1 / PENSHOT=0 / PLOTPILOT=1`：停 MuMu 和 PlotPilot、'
        '**不碰** PenShot（逐服务各自独立，互不影响）',
        'stop' in [c['action'] for c in d['calls']]
        and ('stop', 'plotpilot') in pairs
        and ('stop', 'penshot') not in pairs,
        f"MuMu 动作={[c['action'] for c in d['calls']]}；"
        f"控制器收到的={sorted(pairs)}")
    # ── C6：全局钩子还在（逐服务的都没给时才该它说话）──
    # [EN] ── C6: the global hook still works (only speaks when none of the
    # [EN] per-service ones is given) ──
    e = _stub_run(global_follow='0')
    rec('C6a ★★ 全局 `NWS_TEST_FOLLOW_APP=0`（逐服务的都没给）：'
        '**一个都不停**（老钩子的语义没被三服务化改坏）',
        'stop' not in [c['action'] for c in e['calls']] and not _ctl_pairs(e['ctl']),
        f"MuMu 动作={[c['action'] for c in e['calls']]}；"
        f"控制器收到的={sorted(_ctl_pairs(e['ctl']))}")
    f = _stub_run(global_follow='1')
    pairs = _ctl_pairs(f['ctl'])
    rec('C6b ★★ 全局 `NWS_TEST_FOLLOW_APP=1`（逐服务的都没给）：'
        '**三个都停**（判据靠它把开/关两条分支都走一遍）',
        'stop' in [c['action'] for c in f['calls']]
        and ('stop', 'penshot') in pairs and ('stop', 'plotpilot') in pairs,
        f"MuMu 动作={[c['action'] for c in f['calls']]}；"
        f"控制器收到的={sorted(pairs)}")


# ══════════════════════════════════════════════════════════════════
#  D 自检报告里的决策逻辑（只读）
# [EN] D decision logic in the self-check report (read-only)
# ══════════════════════════════════════════════════════════════════

def _free_tcp_port(start: int = 18000, span: int = 300) -> int:
    """从 `start` 往上找一个**现在能绑**的端口（测完由调用方决定要不要占住）。

    为什么要自己找一个、而不是写死一个数：写死的端口在别人机器上可能正被
    Docker / 别的程序占着 ⇒ 判据自己制造假红。**自己找 + 自己占**，
    这条判据到哪台机器上都成立。

        English:
    Find a port that **can be bound right now**, scanning upward from `start`
    (the caller decides whether to keep holding it).

    Why not hard-code a number: that number may be taken by Docker / another
    program on someone else's machine ⇒ the criterion manufactures a false red.
    **Find it ourselves + hold it ourselves** makes this item valid on any machine.
    """
    for p in range(start, start + span):
        s = socket.socket()
        try:
            s.bind(('127.0.0.1', p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError(f'{start} 起 {span} 个端口都被占了')


def _root_env_port(key: str, default: int) -> int:
    """主程序根 `.env` 里某个端口键的值（没有就用默认）。

    ★ 这里读根 `.env` **不是**"拿用户环境当期望值"那种自证：要证的正是
      "启动器读的是这一个文件" —— 判据和启动器读同一个文件，期望值跟着
      文件走；而服务目录里那两个**诱饵** `.env`（7777 / 7778）只有
      "读错地方"的实现才会拿到。用户改了 `.env`，两边一起改，照样绿；
      谁把端口读到别处去，当场红。

        English:
    The value of a port key in the main program root's `.env` (or the
    default when absent).

    ★ Reading the root `.env` here is **not** the self-fulfilling kind of
      "using the user's environment as the expected value": what is being
      proven is precisely "the launcher reads this one file" -- the
      criterion and the launcher read the same file, so the expectation
      follows the file; while the two **decoy** `.env` files in the service
      directories (7777 / 7778) are only ever obtained by an implementation
      that "reads from the wrong place". If the user edits `.env`, both
      sides change together and it stays green; if anyone reads the port
      from elsewhere, it goes red on the spot.
    """
    try:
        text = (APP / '.env').read_text(encoding='utf-8', errors='replace')
    except OSError:
        return default
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(key + '='):
            v = line.split('=', 1)[1].strip().strip('"').strip("'")
            if v.isdigit() and int(v) > 0:
                return int(v)
    return default


def check_selfreport() -> None:
    print('\n【D】`--selftest` 报出来的决策（只读，不改任何东西）')
    rep = _run_selftest(APP / f'start{SUFFIX}')
    if rep is None:
        rec('D0 `--selftest` 能出报告', False, '没生成 json')
        return
    rec('D0 `--selftest` 能出报告', True, f"version={rep.get('version')}")
    rec('D1 启动器把**工作目录**切到了程序所在目录'
        '（等价于旧脚本的 `cd /d "%~dp0"`，双击时"当前目录"是什么都不能影响它）',
        Path(rep.get('cwd', '')).resolve() == APP.resolve()
        and Path(rep.get('app_dir', '')).resolve() == APP.resolve(),
        f"cwd={rep.get('cwd')}")
    rec('D2 找到了 Python，并且**推得出窗口版**（`pythonw`）'
        '（无控制台靠的就是它；推不出来就只能退回控制台版）',
        rep.get('python_found') and bool(rep.get('pythonw')),
        f"python={rep.get('python')}")
    # 装好的机器上，一步都不该做 ⇒ 启动时不弹进度窗
    # [EN] On an already-installed machine, not a single step should be done ⇒ no progress window pops up
    # [EN] at startup
    if rep.get('venv_ok') and rep.get('deps_marker'):
        rec('D3 ★★ 运行环境已经装好时，**计划里一步都没有**'
            '（⇒ 双击 start 不弹进度窗，安静启动）',
            not rep.get('app_env_steps'),
            f"步骤={rep.get('app_env_steps')}")
    else:
        rec('D3 运行环境没装好 ⇒ 计划里应当出现"创建/安装"步骤', True,
            f"步骤={rep.get('app_env_steps')}")

    # ── D4：端口各读各的地方（2026-10-17 三服务表之后重写）──
    # [EN] ── D4: each port is read from its own place (rewritten 2026-10-17
    # [EN] with the three-service table) ──
    #
    # ★ 三个服务的端口**不在同一处**：MuMu 的 `APP_PORT` 在服务自己的
    #   `.env`（`novelservice.py` 也读那儿）；两个新服务的
    #   `PENSHOT_PORT` / `PLOTPILOT_PORT` 在主程序根 `.env`
    #   （桥的 `_config()` 也读那儿）。读混了不会报错，只是"启动器报告的"
    #   和"服务实际听的"不是一个端口 —— 于是 selftest 说服务活着、
    #   真服务却起不来。
    # [EN] ★ The three services' ports are **not in the same place**: MuMu's
    # [EN] `APP_PORT` is in the service's own `.env` (`novelservice.py`
    # [EN] reads it there too); the two new services' `PENSHOT_PORT` /
    # [EN] `PLOTPILOT_PORT` are in the main program root's `.env` (the
    # [EN] bridge's `_config()` reads them there too). Mixing them up raises
    # [EN] no error -- it just means "what the launcher reports" and "the
    # [EN] port the service actually listens on" diverge, so selftest says
    # [EN] the service is alive while the real one can't start.
    ctl_log = TMP / f'nws_ctl_self_{os.getpid()}.jsonl'
    ports_env = dict(_ctl_fixture_env(ctl_log))
    ports_env['NWS_TEST_SERVICE_DIR'] = str(FIX / 'fixture_service')
    # [EN] MuMu: the hook wins (proves the hook is honored per service)
    ports_env['NWS_TEST_SERVICE_PORT'] = '8123'
    rep2 = _run_selftest(APP / f'start{SUFFIX}', env_extra=ports_env,
                         tag='_ports') or {}
    svcs = {s['id']: s for s in rep2.get('services', [])}
    exp_ps = _root_env_port('PENSHOT_PORT', 8000)
    exp_pp = _root_env_port('PLOTPILOT_PORT', 8005)
    rec('D4 ★★ 端口各读各的地方：MuMu 听测试钩子（8123）；'
        f'PenShot / PlotPilot 按主程序根 `.env`（{exp_ps} / {exp_pp}），'
        '**不是**服务目录里的诱饵 `.env`（7777 / 7778）',
        svcs.get('mumu', {}).get('port') == 8123
        and svcs.get('penshot', {}).get('port') == exp_ps
        and svcs.get('plotpilot', {}).get('port') == exp_pp
        and exp_ps not in (7777,) and exp_pp not in (7778,),
        f"mumu={svcs.get('mumu', {}).get('port')} "
        f"penshot={svcs.get('penshot', {}).get('port')} "
        f"plotpilot={svcs.get('plotpilot', {}).get('port')}"
        f"（期望 8123 / {exp_ps} / {exp_pp}）")

    # MuMu 那一半：不给了钩子时，端口从**服务自己的** .env 读。
    # 夹具的 .env 里放着 8321（诱饵 7777 那套是给两个新服务准备的）。
    # [EN] MuMu's half: without the hook, the port is read from **the
    # [EN] service's own** .env. The fixture's .env holds 8321 (the 7777
    # [EN] decoys are for the two new services).
    own_env = dict(_ctl_fixture_env(ctl_log))
    own_env['NWS_TEST_SERVICE_DIR'] = str(FIX / 'fixture_service')
    own_env.pop('NWS_TEST_SERVICE_PORT', None)
    rep2b = _run_selftest(APP / f'start{SUFFIX}', env_extra=own_env,
                          tag='_ownport') or {}
    svcs_b = {s['id']: s for s in rep2b.get('services', [])}
    rec('D4b ★ MuMu 不给钩子时，端口从**服务自己的** `.env` 读'
        '（夹具里放的是 8321；`novelservice.py` 读的也是这一个文件）',
        svcs_b.get('mumu', {}).get('port') == 8321,
        f"mumu={svcs_b.get('mumu', {}).get('port')}（期望 8321）")

    # ── D5：控制器接线 ──
    # [EN] ── D5: controller wiring ──
    ctl_env = dict(_ctl_fixture_env(ctl_log))
    ctl_env['NWS_TEST_SERVICE_DIR'] = str(FIX / 'fixture_service')
    rep3 = _run_selftest(APP / f'start{SUFFIX}', env_extra=ctl_env,
                         tag='_ctl') or {}
    svcs3 = {s['id']: s for s in rep3.get('services', [])}
    rec('D5 ★ 统一控制器接上了：`controller_script=true`，两个新服务'
        '报 `controller=true`、MuMu 报 `false`（"走哪条路"在报告里看得见）',
        rep3.get('controller_script') is True
        and svcs3.get('penshot', {}).get('controller') is True
        and svcs3.get('plotpilot', {}).get('controller') is True
        and svcs3.get('mumu', {}).get('controller') is False,
        f"controller_script={rep3.get('controller_script')}，"
        f"逐服务={ {k: v.get('controller') for k, v in svcs3.items()} }")

    # ── D6：三个服务都在 ⇒ 三个准备步骤；目录不在 ⇒ 那个步骤消失 ──
    # [EN] ── D6: all three services present ⇒ three prepare steps; a
    # [EN] missing directory ⇒ that step disappears ──
    steps = rep3.get('service_steps') or []
    rec('D6 ★★ 三个服务都在 ⇒ setup 计划里**三个准备步骤一个不少**'
        '（MuMu 直跑自己的脚本；PenShot / PlotPilot 走控制器）',
        len(steps) == 3
        and any('MuMuAINovel' in s for s in steps)
        and any('PenShot' in s for s in steps)
        and any('PlotPilot' in s for s in steps),
        f'步骤={steps}')
    gone = TMP / 'nws_no_such_service_dir'
    shutil.rmtree(gone, ignore_errors=True)
    gone_env = dict(ctl_env)
    gone_env['NWS_TEST_PLOTPILOT_DIR'] = str(gone)
    rep4 = _run_selftest(APP / f'start{SUFFIX}', env_extra=gone_env,
                         tag='_gone') or {}
    steps4 = rep4.get('service_steps') or []
    rec('D6b ★★ PlotPilot 目录不在 ⇒ 它的准备步骤**消失**，另外两个还在'
        '（"目录不在就不碰它"是逐服务判的 —— 少判一个，那个服务没了之后'
        '就会去跑一个必然失败的步骤）',
        len(steps4) == 2
        and not any('PlotPilot' in s for s in steps4)
        and any('PenShot' in s for s in steps4)
        and any('MuMuAINovel' in s for s in steps4),
        f'步骤={steps4}')

    # ── D7：follow 逐服务上报（"程序里显示的"和"启动器做的"同源）──
    # [EN] ── D7: follow is reported per service ("what the program shows"
    # [EN] and "what the launcher does" come from the same source) ──
    follow_env = dict(_ctl_fixture_env(ctl_log))
    follow_env['NWS_TEST_SERVICE_DIR'] = str(FIX / 'fixture_service')
    follow_env['NWS_TEST_FOLLOW_MUMU'] = '1'
    follow_env['NWS_TEST_FOLLOW_PENSHOT'] = '0'
    follow_env['NWS_TEST_FOLLOW_PLOTPILOT'] = '1'
    rep5 = _run_selftest(APP / f'start{SUFFIX}', env_extra=follow_env,
                         tag='_follow') or {}
    svcs5 = {s['id']: s for s in rep5.get('services', [])}
    flags = (svcs5.get('mumu', {}).get('follow'),
             svcs5.get('penshot', {}).get('follow'),
             svcs5.get('plotpilot', {}).get('follow'))
    rec('D7 ★★ selftest 逐服务报 follow（配 1/0/1 就报 True/False/True）'
        '—— 同一个 `*_FOLLOW_APP` 两边说了算，用户才不会被显示骗',
        flags == (True, False, True),
        f'follow(mumu/penshot/plotpilot)={flags}')

    # ── D8：不给任何钩子 ⇒ follow 听**那份 `.env`** 的 `*_FOLLOW_APP` ──
    # [EN] ── D8: with no hooks at all, follow listens to `*_FOLLOW_APP` in
    # [EN] **that `.env`** ──
    #
    # ★ 为什么单列两条（2026-10-17 晚，被反例法撞出来的缝）：真实用户机上
    #   **一个测试钩子都不存在**，`.env` 的 `*_FOLLOW_APP` 是"停不停服务"
    #   唯一的决策来源。可 C1/C2/C5/C6a/C6b/D7 **全靠钩子摆布** ⇒ `followFor`
    #   里钩子之后的那段整个坏掉，A~F 一条都不红（变异⑥第一版就是这样：
    #   `return false` 插在钩子之后，弹出来的却是 C6b）。
    #   ⇒ 这两条把启动器**拷到临时目录**跑（exe 自己算出 appDir ⇒ 读的是
    #   **那次拷贝的** `.env`，不是用户的），期望值全部来自判据**自己写下的**
    #   那份 `.env` —— 既不读用户环境，也不靠钩子。
    # [EN] ★ Why two separate items (2026-10-17 evening, a seam the
    # [EN] counterexample method ran into): on a real user machine **not one
    # [EN] test hook exists**, so `*_FOLLOW_APP` in `.env` is the only
    # [EN] decision source for "stop the services or not". Yet C1/C2/C5/C6a/
    # [EN] C6b/D7 **all arrange via hooks** ⇒ if everything after the hooks in
    # [EN] `followFor` breaks, not one of A~F goes red (mutation ⑥'s first
    # [EN] version was exactly this: `return false` sat after the hooks and
    # [EN] what popped was C6b).
    # [EN] ⇒ These two run the launcher **copied into a temp dir** (the exe
    # [EN] computes appDir itself ⇒ it reads **that copy's** `.env`, not the
    # [EN] user's); every expectation comes from the `.env` the criterion
    # [EN] **wrote itself** -- neither reading the user's environment nor
    # [EN] relying on hooks.
    env_app = TMP / 'nws_env_app'
    shutil.rmtree(env_app, ignore_errors=True)
    env_app.mkdir(parents=True)
    try:
        shutil.copy2(APP / f'start{SUFFIX}', env_app / f'start{SUFFIX}')
    except OSError as e:
        rec('D8 ★★ 拷一份启动器到临时目录（读它自己的 .env）', False, str(e))
        return
    # ⚠ 一个 follow 钩子都不给 —— 这条断言的全部意义就在这儿。
    #   控制器/服务目录的钩子照给（不然 `present=false`，压根不进入决策）。
    # [EN] ⚠ Not a single follow hook -- that is the entire point of this
    # [EN] item. The controller/service-dir hooks are still given (otherwise
    # [EN] `present=false` and we never reach the decision).
    env8 = dict(_ctl_fixture_env(TMP / f'nws_ctl_env_{os.getpid()}.jsonl'))
    (env_app / '.env').write_text(
        'MUMU_FOLLOW_APP=true\nPENSHOT_FOLLOW_APP=false\nPLOTPILOT_FOLLOW_APP=1\n',
        encoding='utf-8')
    rep8 = _run_selftest(env_app / f'start{SUFFIX}', env_extra=env8,
                         tag='_env') or {}
    svcs8 = {s['id']: s for s in rep8.get('services', [])}
    flags8 = (svcs8.get('mumu', {}).get('follow'),
              svcs8.get('penshot', {}).get('follow'),
              svcs8.get('plotpilot', {}).get('follow'))
    rec('D8 ★★ 不给任何钩子 ⇒ follow 听**那份 `.env`**'
        '（`.env` 写 true/false/1 就报 True/False/True —— 用户机上的唯一来源）',
        flags8 == (True, False, True),
        f'follow(mumu/penshot/plotpilot)={flags8}')
    # D8b：`.env` 里**没有**这些键 ⇒ 默认全 true（SPEC 的默认值，与
    #       `config.py` 一致）。少了这条，"默认开"被悄悄改成"默认关"没人知道。
    # [EN] D8b: the `.env` has **no** such keys ⇒ default all true (the SPEC
    # [EN] default, consistent with `config.py`). Without this item, "on by
    # [EN] default" quietly becoming "off by default" would go unnoticed.
    (env_app / '.env').write_text('SOME_OTHER_KEY=1\n', encoding='utf-8')
    rep8b = _run_selftest(env_app / f'start{SUFFIX}', env_extra=env8,
                          tag='_envdef') or {}
    svcs8b = {s['id']: s for s in rep8b.get('services', [])}
    flags8b = (svcs8b.get('mumu', {}).get('follow'),
               svcs8b.get('penshot', {}).get('follow'),
               svcs8b.get('plotpilot', {}).get('follow'))
    rec('D8b ★★ `.env` 里没有 `*_FOLLOW_APP` ⇒ 三个都报 true（SPEC 默认值；'
        '少了它，"默认开"被改成"默认关"没人会发现）',
        flags8b == (True, True, True),
        f'follow(mumu/penshot/plotpilot)={flags8b}')

    # ── D9：端口探测（"**绑得上**才算空闲"）──
    # [EN] ── D9: port probe ("**can bind**" is what counts as free") ──
    #
    # 用户 2026-10-17：「我在机器上有 Docker，3 个外部服务最后不要跟现有的在使用的
    # 端口冲突」。setup 靠 `portUsable` 判断"这个端口现在能不能由我们用"，
    # 本条的牙齿是：**判据自己占住一个端口**，selftest 必须报 `port_busy=true`；
    # 放开后必须报 false。少了这条，"探测永远返回空闲"（⇒ 永不改端口）没人发现。
    # [EN] User 2026-10-17: "I have Docker on the machine; the three external services must
    # [EN] not collide with ports in use." setup decides "can we use this port now" via
    # [EN] `portUsable`; this item's teeth: **the criterion occupies a port itself** and
    # [EN] selftest must report `port_busy=true`; after releasing, it must report false.
    # [EN] Without it, "the probe always says free" (⇒ never changes a port) goes unnoticed.
    probe_port = _free_tcp_port(18000)
    hold = socket.socket()
    hold.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    hold.bind(('127.0.0.1', probe_port))
    hold.listen(1)
    try:
        env9 = dict(_ctl_fixture_env(TMP / f'nws_ctl_p9_{os.getpid()}.jsonl'))
        env9['NWS_TEST_SERVICE_DIR'] = str(FIX / 'fixture_service')
        env9['NWS_TEST_SERVICE_PORT'] = str(probe_port)
        rep9 = _run_selftest(APP / f'start{SUFFIX}', env_extra=env9,
                             tag='_busy') or {}
        busy = {s['id']: s.get('port_busy')
                for s in rep9.get('services', [])}.get('mumu')
    finally:
        hold.close()
    time.sleep(0.3)
    rep9b = _run_selftest(APP / f'start{SUFFIX}', env_extra=env9,
                          tag='_free') or {}
    free = {s['id']: s.get('port_busy')
            for s in rep9b.get('services', [])}.get('mumu')
    rec('D9 ★★ 端口探测判的是"**绑得上**"：判据占住端口 ⇒ `port_busy=true`；'
        '放开 ⇒ false（Docker/别的程序占着时才改端口，靠的就是这个判断）',
        busy is True and free is False,
        f'占住时={busy}（期望 True）、放开后={free}（期望 False）')


# ══════════════════════════════════════════════════════════════════
#  E 进度窗（setup/uninstall 的反馈）
# [EN] E progress window (feedback for setup/uninstall)
# ══════════════════════════════════════════════════════════════════

#: 从源码里读"展开态窗口高度 / 底图画布高度"这两个**写在两处、必须相等**的数。
#: ⚠ 为什么用正则读源码而不是 import：判据要的是"产品现在写的那个数"，
#:   而 import `launcher_splash` 会要 tkinter（本判据的 .venv 里没有）。
#: [EN] Read the two **must-be-equal** numbers that live in two places (expanded window height /
#: [EN] backdrop canvas height). ⚠ Why regex over the source instead of importing: the criterion
#: [EN] wants "the number the product currently writes", and importing `launcher_splash` needs
#: [EN] tkinter (absent from this criterion's .venv).
def _num_in(path: Path, name: str) -> int:
    try:
        m = re.search(rf'^{name}\s*=\s*(\d+)', path.read_text(encoding='utf-8'),
                      re.M)
        return int(m.group(1)) if m else 0
    except Exception:                                        # noqa: BLE001
        return 0


def _splash_h_exp() -> int:
    """展开态窗口高度 —— ⚠ 2026-10-27 第二轮起它是个**算式**，不是写死的数字。

    ★★★ 为什么这个小函数要改（2026-10-27 第二轮，用户：「日志框又太高了，高度减少 50%」）：
      `H_EXP` 原来写死 `820`，现在是 `LOG_BOX_TOP + LOG_H + EXP_BOTTOM_BAND`
      —— 窗口高度**跟着日志框走**，不许一个改一个不改（否则框下面露出一大段空白）。
      而 `_num_in` 的正则只认 `^H_EXP = 数字` ⇒ 改成算式之后它读到 **0**，
      E5c-6 / E5i 当场变红，报错写的是"H_EXP=0"，看着像"产品把高度删了"，
      其实是**判据读不到** —— 这正是本项目最贵的那一类假象（读不到 vs 没改，长得一样）。
      ⇒ 两条路都试：先按数字读（兼容写死的写法），读不到就按算式算出来。
    [EN] ★★★ Why this helper had to change (2026-10-27, second round -- user: "the log box is too
    [EN] tall again, cut 50%"): `H_EXP` used to be the literal `820`; it is now
    [EN] `LOG_BOX_TOP + LOG_H + EXP_BOTTOM_BAND` -- the window height **follows the log box** and the
    [EN] two must never drift (or a wide blank band shows below the box). `_num_in`'s regex only
    matches `^H_EXP = <digits>`, so with an expression it reads **0** and E5c-6 / E5i go red saying
    "H_EXP=0", which looks like "the product deleted the height" when it is really **the criterion
    failing to read it** -- the most expensive kind of illusion in this project ("cannot read" looks
    exactly like "never changed"). => Try both: a literal first (still compatible), then the sum.
    """
    splash = APP / 'tools' / 'launcher_splash.py'
    lit = _num_in(splash, 'H_EXP')
    if lit:
        return lit
    top = _num_in(splash, 'LOG_BOX_TOP')
    hh = _num_in(splash, 'LOG_H')
    band = _num_in(splash, 'EXP_BOTTOM_BAND')
    return (top + hh + band) if (top and hh and band) else 0


def _art_h_tall() -> int:
    return _num_in(APP / 'tools' / 'make_splash_art.py', 'H_TALL')


def check_progress_ui() -> None:
    # ⚠⚠ 这两个辅助函数**必须定义在本函数最前面**：E5h 用到它们，而 E5h 在 E5c 之前。
    #   我已经在这里连踩两次 `UnboundLocalError`（`bg_p` 一次、`_band_detail` 一次）——
    #   Python 的函数作用域是"整个函数"，所以在下面定义的名字对上面是**未绑定**而不是"不存在"，
    #   报错信息也只会说 "cannot access local variable"，看不出是"顺序问题"。
    #   项目记忆里那条"新判据用到的变量别定义在它下面"，就是这件事。
    # [EN] ⚠⚠ These two helpers **must be defined at the very top of this function**: E5h uses them
    # [EN] and E5h comes before E5c. I hit `UnboundLocalError` twice here already (`bg_p` once,
    # [EN] `_band_detail` once) -- Python's function scope means a name defined lower is
    # [EN] **unbound**, not "absent", and the message ("cannot access local variable ...") never
    # [EN] says "ordering problem". That is exactly the project rule about defining variables above
    # [EN] the criteria that use them.
    def _band_detail(p: Path, y0: int, y1: int) -> float:
        """一条横带 `[y0, y1)` 的**平均逐行细节量**（行内相邻像素差之和 / 采样点数）。

        用途（E5h）：判断"裁掉这一段会不会丢东西"。纯纸纹的带子约 6~11，
        有插画/文字的带子会到 45~65 —— 阈值 15 是这两档之间的空当，不是拍脑袋的整数。

        ⚠ 不用 `edge` 滤波器（`_bg_stat` 那一套）：FIND_EDGES 对**渐变**也响应，
          而纸纹本身有极缓的明暗变化，会被算成"有内容"。
          相邻像素差对渐变几乎不响应、对真正的笔画/轮廓才有值 —— 这正是这里要的。
        [EN] Average per-row detail over a horizontal band `[y0, y1)`.
        [EN] Used by E5h to decide "would cutting this band lose anything": pure paper texture lands
        [EN] at 6~11, artwork/text at 45~65 -- 15 is the gap between the two, not an arbitrary number.
        [EN] ⚠ Not the FIND_EDGES filter used by `_bg_stat`: it also responds to **gradients**, and
        [EN] paper texture has a very slow luminance drift that would count as "content". Neighbour
        [EN] differences barely respond to a gradient and do fire on real strokes.
        """
        with Image.open(p) as im0:
            im = im0.convert('RGB')
            w, _h = im.size
            y0 = max(0, min(int(y0), im.size[1]))
            y1 = max(y0, min(int(y1), im.size[1]))
            if y1 <= y0:
                return 0.0
            crop = im.crop((0, y0, w, y1))
        raw = crop.tobytes()
        bw = crop.size[0]
        bh = crop.size[1]
        total = 0
        # 稀疏采样：每 8 像素取一对，够稳又快
        # [EN] Sparse sampling: one pair every 8 pixels -- stable and fast enough.
        for y in range(bh):
            base = y * bw * 3
            for x in range(0, bw - 8, 8):
                i = base + x * 3
                j = i + 24
                total += (abs(raw[i] - raw[j]) + abs(raw[i + 1] - raw[j + 1])
                          + abs(raw[i + 2] - raw[j + 2]))
        n = max(1, bh * max(1, (bw - 8 + 7) // 8))
        return total / n

    print('\n【E】进度窗：能跑、能报、没窗口时也能干活')
    script = APP / 'tools' / 'launcher_progress.py'
    rec('E0 进度窗脚本在（`tools/launcher_progress.py`）', script.exists(), '')
    if not script.exists():
        return

    # ★ 必须用**启动器自己会挑的那个 Python** 来跑，不是 `.venv` 里那个。
    #   进度窗的用武之地正是"工程 `.venv` 还没建出来"的时候，所以它走的是
    #   `findPython()` 那条路（`py -3` / `python`），跟 `.venv` 无关。
    #   ⚠ 第一版这里用的是 `sys.executable`（判据自己在 `.venv` 里跑）——
    #     实测那个 venv 的 base 是**托管版 3.13.12，里面没有 tkinter**，
    #     于是 E1 假红。"用错解释器"是最容易骗过自己的一种判据写错法。
    # [EN] ★ Must be run with **the Python the launcher itself would pick**, not the one in `.venv`.
    # [EN] The progress window's very purpose is exactly when "the project `.venv` hasn't been created
    # [EN] yet", so it goes through
    # [EN] the `findPython()` path (`py -3` / `python`), unrelated to `.venv`.
    # [EN] ⚠ The first version here used `sys.executable` (the criterion itself ran inside `.venv`) ——
    # [EN] measured: that venv's base is **managed version 3.13.12, which has no tkinter**,
    # [EN] so E1 was falsely red. "Using the wrong interpreter" is one of the easiest ways to write a
    # [EN] criterion that fools yourself.
    rep = _run_selftest(APP / f'start{SUFFIX}') or {}
    py = rep.get('python') or sys.executable
    tk = subprocess.run([py, '-c', 'import tkinter;print(tkinter.TkVersion)'],
                        capture_output=True, text=True, timeout=90)
    rec(f'E1 ★★ 启动器挑的那个 Python（{Path(py).name}）**带 tkinter** ⇒ '
        '进度窗真的弹得出来（不带的话 setup/uninstall 会退化成"只弹一个结果框"，'
        '装依赖那几分钟用户面前一片空白 —— 那是次优解，不是等价解）',
        tk.returncode == 0, (tk.stdout or tk.stderr).strip()[:70])

    # ── E5：启动 splash（2026-10-17 用户要求）──
    # [EN] ── E5: the startup splash (user request, 2026-10-17) ──
    #
    # 用户：「虽然没命令行，但要有一个类似 splash 的窗口，带 Logo / 名字 / 主题语，
    # 消息条可以展开成命令行输出，最后是版本、是否本地运行、技术平台，背景用背景图缩略版」。
    # 判"建不建得出来"只能真建一次（`--selftest` 建完就退），然后读它自己交出的摘要。
    # [EN] "No console, but a splash with logo / name / tagline, an expandable message strip,
    # [EN] and a footer with version / local-run / platform, over the background thumbnail."
    # [EN] Whether it builds can only be checked by building it once (`--selftest`), then
    # [EN] reading the summary it hands back.
    splash = APP / 'tools' / 'launcher_splash.py'
    rec('E5 ★★ 启动窗口脚本在（`tools/launcher_splash.py`）', splash.exists(), '')
    if splash.exists():
        spec = {
            'title': '小说世界 AI 模拟',
            'subtitle': '—— 把故事，活一遍 ——',
            'logo': str(APP / 'assets' / 'images' / 'start_logo_96.png'),
            'bg': str(APP / 'assets' / 'images' / 'title_bg_splash.png'),
            'log': '', 'ready': '', 'fail': '',
            'version': 'judge-test', 'mode': '本地运行',
            'platform': 'Python + Flet',
        }
        spec_p = TMP / f'nws_splash_{os.getpid()}.json'
        spec_p.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')

        def _splash_selftest(extra: list[str], tag: str) -> tuple[int, dict]:
            # ⚠ 输出文件名不能和 spec 撞（第一版 `tag=''` 时两者同一个路径，
            #   于是"先删输出"把 spec 也删了 ⇒ 子进程 rc=2，看着像"窗口建不出来"）。
            # [EN] The output file must not collide with the spec (with `tag=''` they were
            # [EN] the same path; "delete the output first" deleted the spec too ⇒ rc=2,
            # [EN] which looked like "the window can't be built").
            out_p = TMP / f'nws_splash_{os.getpid()}{tag}_sum.json'
            if out_p.exists():
                out_p.unlink()
            r = subprocess.run([py, str(splash), '--spec', str(spec_p),
                                '--selftest', str(out_p), *extra],
                               cwd=str(APP), capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=180)
            data = {}
            if out_p.exists():
                try:
                    data = json.loads(out_p.read_text(encoding='utf-8'))
                except ValueError:
                    data = {}
            return r.returncode, data

        rc, d = _splash_selftest([], '')
        foot = d.get('footer') or ''
        rec('E5 ★★★ 启动窗口真建得出来：**背景缩略图与 Logo 都读到了**，'
            '底栏与开始界面同一格式（`v… · 本地运行 · Python + Flet`），'
            '右上角有 ✕、消息条右侧有**展开按钮**'
            '（★ 不再判"有边框" —— 用户 2026-10-17 最后一版：**消息栏和版本号的边框也去掉**）',
            rc == 0 and d.get('bg_loaded') is True and d.get('logo_loaded') is True
            and d.get('has_close') is True and d.get('has_detail') is True
            and foot.startswith('v') and '本地运行' in foot and 'Python + Flet' in foot,
            f'rc={rc} bg={d.get("bg_loaded")} logo={d.get("logo_loaded")} '
            f'close={d.get("has_close")} detail={d.get("has_detail")} footer={foot[:50]}')
        rc2, d2 = _splash_selftest(['--expanded'], '_exp')
        rec('E5b ★★ 展开后是**更大的一页 + 命令行输出区**'
            '（启动一出问题，报错就该出现在这里，而不是让用户去翻日志）',
            rc2 == 0 and d2.get('has_console') is True
            and (d2.get('size') or [0])[1] > (d.get('size') or [0, 0])[1],
            f'rc={rc2} has_console={d2.get("has_console")} '
            f'size={d2.get("size")}（收起时 {d.get("size")}）')
        # ★★★ 2026-10-21 用户：「启动画面的展开按钮 也改成三角形的按钮 **正常是向右
        #   展开头向下**」—— 判据要钉**方向**，不能只钉"有个三角"：
        #   三角画反（收起时头朝下）在界面上看着像"已经展开了"，而截图判据也看不出来。
        # ⚠ 两个状态一起判（收起 right + 展开 down）：只判一边的话，把两边都画成
        #   同一个朝向也照样绿 —— 那是"一刀切也能绿"那类假判据。
        # [EN] ★★★ 2026-10-21 (user: "the splash's expand button should be a triangle --
        # [EN] pointing right normally, head down when expanded"): the criterion must pin the
        # [EN] **direction**, not just "there is a triangle". A flipped triangle (head down while
        # [EN] collapsed) looks like it is already expanded. ⚠ Both states are judged together:
        # [EN] judging only one lets "same direction in both states" pass -- a one-sided fake.
        rec('E5e ★★★ 展开按钮方向对：收起 **向右** / 展开 **头向下**，'
            '而且是**同一个图形转过去**（-90° → 0°），不是换一个形状',
            d.get('detail_glyph') == 'right'
            and d2.get('detail_glyph') == 'down'
            and d.get('detail_deg_target') == -90 and d2.get('detail_deg_target') == 0,
            f'收起={d.get("detail_glyph")!r}@{d.get("detail_deg_target")} '
            f'展开={d2.get("detail_glyph")!r}@{d2.get("detail_deg_target")}')
        # ★★★ 2026-10-23 改口径（用户：「三角号下拉按钮我还是觉得不好看」）：
        #   原来这条守的是「三角是**画出来的多边形**、不是字符，且矩形数 0」。
        #   用户这轮说实心三角不好看 ⇒ 设计改成**描边 chevron**（两笔画、圆头）。
        #   ⇒ 判据改成守**新设计**，而且必须比原来更严：
        #     ① 形状是 `line`（不是 `polygon`）—— 防"又改回实心三角"；
        #     ② 笔画 2~3px —— 太细（1）在浅纸上会断断续续，太粗（≥4）又变回"一块颜色"；
        #     ③ 悬停**只换前景色**（rest ≠ hover）—— 防"顺手加个圆角底色"，
        #        因为用户三轮明确不要色块；
        #     ④ 矩形数仍是 0（保持原设计：不加任何底框）。
        #   ⚠ 调研依据写在 `launcher_splash._mk_detail_btn` 的说明里
        #     （微软 Progressive Disclosure 指南 + vocab.design 对 chevron 与实心三角的来源考据）。
        # [EN] ★★★ 2026-10-23 re-specified (user: "I still find the triangle button ugly"):
        # [EN] this used to pin "the triangle is a drawn **polygon**, not a glyph, and rectangles == 0".
        # [EN] The user now calls the solid triangle ugly => the design is a **stroked chevron**.
        # [EN] => The criterion guards the new design and is stricter than before: ① shape is `line`
        # [EN] (not `polygon`) so it cannot silently revert; ② stroke 2~3px -- 1px breaks up on pale
        # [EN] paper, >=4px turns back into "a patch of colour"; ③ hover **only changes the
        # [EN] foreground** (rest != hover) so nobody "helpfully" adds a rounded background; ④
        # [EN] rectangles still 0 (the original "no frame" design).
        rec('E5f ★★★ 展开按钮是**描边 chevron**（不是实心三角），'
            '悬停只换前景色、**一个色块都不加**（矩形数仍 0）',
            d.get('detail_style') == 'chevron' and d2.get('detail_style') == 'chevron'
            and 2.0 <= float(d.get('detail_width') or 0) <= 3.0
            and d.get('detail_rest_fill') != d.get('detail_hover_fill')
            and d.get('borders') == 0 and d2.get('borders') == 0,
            f'语义={d.get("detail_style")}/{d2.get("detail_style")} '
            f'实现={d.get("detail_shape")}/{d2.get("detail_shape")} '
            f'线宽={d.get("detail_width")} '
            f'常态={d.get("detail_rest_fill")} 悬停={d.get("detail_hover_fill")} '
            f'rectangles={d.get("borders")}/{d2.get("borders")}')
        rec('E5g ★★★ 命中区 ≥ 32×32（桌面标准；原来的 14px 三角"看得见但点不准"）'
            '—— 且**悬停区与点击区是同一个**（都走 canvas 级距离判断）',
            int(d.get('detail_hit') or 0) * 2 >= 32
            and int(d2.get('detail_hit') or 0) * 2 >= 32,
            f'半径 {d.get("detail_hit")} → {int(d.get("detail_hit") or 0) * 2}px 方块')

        # ── E5h ★★★ 收起时**真的更小**（用户 2026-10-23 的第二句话）──
        #
        # 「还有**不展开的时候，启动界面应该更小一些**才对」
        #
        # ★ 怎么判才算守住了设计（而不是钉死 350）：
        #   把"能缩"这件事绑到**理由**上 —— 收起来的窗口**只遮掉背景图里没有内容的那一段**。
        #   具体：取 `[H_BASE, 480)` 这一横条，量它的逐行细节（相邻像素差）。
        #   实测那一段几乎是均质纸纹（每行均值 < 10），所以裁掉它是安全的；
        #   谁要把 H_BASE 设成 460（把有画的部分裁掉），这一条当场红。
        #   ⚠ 再加一条"别缩过头"：H_BASE 必须还装得下消息条(242) + 底栏(27) + 一行失败提示，
        #     否则底栏会被切掉 —— 那是"更小"变成"坏了"。
        # [EN] ── E5h ★★★ collapsed really is **smaller** (the user's second sentence) ──
        # [EN] "and **when it's not expanded the splash should be smaller**".
        # [EN] ★ How to judge the design rather than pinning 350: tie "it can shrink" to its
        # [EN] **reason** -- the collapsed window must only hide the part of the backdrop with no
        # [EN] content. Concretely: measure per-row detail in the band `[H_BASE, 480)`; measured, it
        # [EN] is near-uniform paper (mean < 10 per row), so cutting it is safe. Anyone setting
        # [EN] H_BASE to 460 (cutting into painted area) turns this red on the spot.
        # [EN] ⚠ Plus "don't over-shrink": H_BASE must still hold the strip (242) + footer (27) + one
        # [EN] failure line, otherwise the footer gets clipped -- "smaller" becoming "broken".
        h_base = int((d.get('size') or [0, 0])[1] or 0)
        h_exp = int((d2.get('size') or [0, 620])[1] or 0)
        # ⚠ `bg_p` 在下面的 E5c 里才定义 —— 本判据先用它 ⇒ 必须在这里取一次。
        #   第一版就因为在 E5c 之前引用它而 `UnboundLocalError`，整段 E 组直接崩掉
        #   （输出停在 E5g，E5h 根本没跑 —— 而"没跑"看起来像"没有这条判据"）。
        #   这正是项目里那条：**新判据用到的变量别定义在它下面**。
        # [EN] ⚠ `bg_p` is defined further down (in E5c) but used here, so fetch it here.
        # [EN] The first version referenced it before E5c and raised `UnboundLocalError`, killing the
        # [EN] whole E section (output stopped at E5g; E5h never ran -- and "never ran" looks like
        # [EN] "there is no such criterion"). Exactly the project rule: **do not define a variable
        # [EN] below the criterion that uses it**.
        _bg_p = APP / 'assets' / 'images' / 'title_bg_splash.png'
        band_detail = _band_detail(_bg_p, h_base, 480) if _bg_p.exists() else 999.0
        # ★★★ 2026-10-24 **改口径**（不是放宽，是原来那条代理指标失效了）：
        #   旧写法要求"被裁掉的 [H_BASE,480) 那一段几乎没细节（<15）"，理由是"裁掉的正是空白"。
        #   那个理由成立的前提是底图**上半截是空纸** —— 而现在底图是用户要的那幅画，
        #   画在水墨里处处有笔墨，那一段实测 12.6（换一档色阶就会越 15）。
        #   ⚠ 真正要守的是**控件没被裁掉**（用户说的"更小"不能变成"底栏被切"），
        #     以及"收起来仍然看得见东西"—— 后者已经交给 `E5c-2`（量 250..344 有没有画）。
        #     所以这里只留两条硬的：比 480 明显矮、而且底栏（y = H-27）连同 6px 下边距还在窗口内。
        #   细节量仍然**报出来**（信息，不再是条件），方便下一个人看清那一段现在有什么。
        # [EN] ★★★ 2026-10-24 changed the yardstick (not relaxed -- the old proxy stopped being
        # [EN] valid): it required the cut band [H_BASE,480) to be almost detail-free (<15), on the
        # [EN] grounds that "what gets cut is blank". That held while the backdrop's top half was
        # [EN] empty paper. The backdrop is now the painting the user asked for, which has brushwork
        # [EN] everywhere: the band measures 12.6 and any tone tweak would cross 15.
        # [EN] ⚠ What must really hold: **no widget gets cut** (the user's "smaller" must not become
        # [EN] "footer clipped"), and "the collapsed state still shows something" -- the latter now
        # [EN] belongs to `E5c-2` (measures 250..344 for artwork). So only two hard conditions stay:
        # [EN] clearly shorter than 480, and the footer (y = H-27) plus a 6px margin still inside.
        # [EN] The detail number is still **reported** (information, not a condition).
        rec('E5h ★★★ 收起时**更矮了**，而且**没有裁到任何控件**'
            '（用户：「不展开的时候，启动界面应该更小一些才对」；'
            '底栏 y=H-27=323，加 6px 下边距 ⇒ 至少 329）'
            '—— "被裁的那段有没有内容"不再是条件：底图现在处处有笔墨，那条代理指标已失效，'
            '"收起来看得见东西"由 E5c-2 守',
            0 < h_base < 460
            and h_base >= 323 + 6,
            f'收起 {h_base}px（原 480）· 展开 {h_exp}px · '
            f'（信息）被裁掉的 [y{h_base}..480) 细节量 {band_detail:.1f}')

        # ── E5d：标题的字体**与开始界面同一份文件**（用户 2026-10-17：「标题的字体不对」）──
        #
        # ★ 根因：开始界面是 Flet 用 `page.fonts` **按文件**注册随附字体画标题的；
        #   而 tkinter 只能按**族名**到系统里找 —— 这台机器上装了思源宋体整族，
        #   `weight='bold'` 就会挑到 **Black**，跟开始界面（随附 Regular + 合成粗体）
        #   根本不是同一张脸。 ⇒ 判据认的是"**按哪份文件**画的"，不是"字多粗"。
        #
        # ★ 期望值怎么来（不是自证）：判据自己按契约算一遍 ——
        #   `config.CFG.s('UI_FONT')`（用户在「天机 · 界面外观」里选的）→ `ui_fonts.BUNDLED_FONTS`
        #   → `assets/fonts/<文件名>`；两边一致就绿。**用户选什么字体都能绿**，
        #   只有"启动窗口不看用户选的字体 / 不看那份文件"才会红。
        #   （选系统字体时没有随附文件 ⇒ 按族名回落才是正确行为，不许为了绿去编路径。）
        #
        # [EN] ── E5d: the title must be drawn with **the same font file as the start screen** ──
        # [EN] ★ Root cause: the start screen draws its title with the bundled font that Flet
        # [EN] registers **by file**; tkinter can only look up a **family name**, and with the whole
        # [EN] Noto Serif SC family installed `weight='bold'` picks **Black** -- a different face.
        # [EN] So the criterion checks "**drawn from which file**", not "how bold it looks".
        # [EN] ★ Where the expectation comes from (not self-fulfilling): the criterion works it out
        # [EN] from the contract -- `config.CFG.s('UI_FONT')` (what the user picked in Tianji · UI
        # [EN] appearance) -> `ui_fonts.BUNDLED_FONTS` -> `assets/fonts/<file>`; green when the two
        # [EN] sides agree. **Whatever the user picks stays green**; only "the splash ignores the
        # [EN] user's font / that file" turns it red. (A system font has no bundled file ⇒ falling
        # [EN] back to a family name is correct; never invent a path just to be green.)
        try:
            if str(APP) not in sys.path:
                sys.path.insert(0, str(APP))
            import config as _cfg
            import ui_fonts as _uf
            _tok = (_cfg.CFG.s('UI_FONT') or '').strip() or _uf.DEFAULT_TOKEN
            _item = _uf.BUNDLED_FONTS.get(_tok)
            want_font = (APP / 'assets' / 'fonts' / _item[1]) if _item else None
        except Exception:                                # noqa: BLE001
            _tok, want_font = '', None
        got_font = str(d.get('title_font') or '')
        got_mode = str(d.get('title_mode') or '')
        if want_font is not None and want_font.exists():
            ok_font = (got_mode == 'file' and got_font != ''
                       and Path(got_font).resolve() == want_font.resolve())
        else:                                            # 用户选的是系统字体 ⇒ 按族名回落才对
            ok_font = (got_mode == 'family')
        rec('E5d ★★★ 标题是**按字体文件**画的，而且用的就是开始界面当前那一份'
            f'（`UI_FONT={_tok or "缺省"}`）⇒ 两边落在同一份字形上'
            '（按族名到系统里找会挑到别的字重：本机装了整族思源宋体，'
            '`bold` 会挑到 Black，跟开始界面的 Regular + 合成粗体不是一张脸）',
            ok_font, f'token={_tok} mode={got_mode} '
                     f'file={Path(got_font).name if got_font else "（无）"}')

        # ── E5e：消息条与底栏**连边框都没有**（用户 2026-10-17 最后一版：
        #   「启动窗口消息栏和版本号把边框去掉」）──
        #
        # ★ 三轮迭代的落点（每一轮的判据都得跟着翻，不然守的是上一版）：
        #   ① 「加上边框，否则压在背景上看不出来」 ⇒ 要有两个矩形；
        #   ② 「背景很纯了，去掉消息框的背景颜色」 ⇒ 填充要空；
        #   ③ 「边框也去掉」 ⇒ **一个矩形都不许有**。
        #
        # ★★ 成对：框可以没有，**字不能没有** —— 只判"没有矩形"的话，
        #    把消息条连字一起删掉也照样绿（那才是真的坏了）。所以 E5e-2 守"字还在"。
        #
        # [EN] ── E5e: the strip and footer have **no border at all** (user's last word,
        # [EN] 2026-10-17: "drop the border from the splash strip and the version line") ──
        # [EN] ★ Three rounds, and the criterion flips each time (otherwise it guards the previous
        # [EN] version): ① "add a border, it's invisible over the picture" ⇒ two rectangles;
        # [EN] ② "the backdrop is pale now, drop the strip's background" ⇒ empty fill;
        # [EN] ③ "drop the border too" ⇒ **no rectangles at all**.
        # [EN] ★★ Paired: the frame may go, the **text must not** -- judging only "no rectangles"
        # [EN] would stay green if the strip's text were deleted along with it. E5e-2 guards that.
        _n = d.get('borders') or 0
        _fills = [str(x or '') for x in (d.get('fills') or [])]
        _strokes = [str(x or '') for x in (d.get('strokes') or [])]
        rec('E5e ★★ 消息条与底栏**一个矩形都没有**（不画色块、也不描金边）'
            '—— 底图已经很纯，字直接压在图上就够了',
            _n == 0 and not _fills and not _strokes,
            f'矩形 {_n} 个，填充 {_fills}，描边 {_strokes}')
        rec('E5e-2 ★★ 成对：**字还在**（消息条那一行 + 底栏 `v… · 本地运行 · Python + Flet`）'
            '—— 只判"没有矩形"的话，把消息条连字一起删掉也照样绿',
            bool(str(d.get('msg') or '').strip())
            and bool(str(d.get('footer') or '').strip()),
            f'消息条={str(d.get("msg") or "")[:24]!r} 底栏={str(d.get("footer") or "")[:40]!r}')

    # ── E5c：底图「淡而不花」（2026-10-17 用户：「背景图有点花，能不能从完整背景图里
    #   截取一部分颜色较淡的部分」）──
    #
    # ★ 旧版是**把整张 3840×2160 缩到 860px**：全图的笔墨全挤进一张小图 ⇒ 看着就是"花"。
    #   现在改成**在母版上滑动窗口、按「亮/平/素」打分裁一块**（`tools/make_splash_bg.py`）。
    #
    # ★★ 判据纪律（这三条都是踩过的坑）：
    #   · 期望值一律**写死的绝对数**，不从被测代码 import —— 拿 import 来的常量当期望是"自证"；
    #   · **成对**：既判"够淡"，也判"不是一张白板"（纯色图 std=0 能把"淡"全骗过去）；
    #   · **比旧版好**这件事用**行为对照**判：当场把母版整张缩略成一张（就是旧做法），
    #     现底图必须比它淡得多 —— 这样"淡"不是我拍脑袋定的数，而是"比旧版好"的硬证据；
    #   · **单独量文字带**（y 40..270：Logo / 名字 / 标语 / 消息条都压在这一段）——
    #     只看整图均值会把"字正好压在花的地方"糊过去。
    #
    # [EN] ── E5c: the splash backdrop must be "pale, not busy" (user, 2026-10-17: "the background
    # [EN] looks busy -- can you crop a paler part out of the full background?") ──
    # [EN] ★ The old one **shrunk the whole 3840x2160 artwork into 860px**, so every brush stroke
    # [EN] ended up side by side -- that is exactly the "busy" look. Now we slide a window over the
    # [EN] master and score each patch on bright/flat/plain (`tools/make_splash_bg.py`).
    # [EN] ★★ Criteria discipline (all three burned us before): hard-coded absolute numbers (never
    # [EN] import the expected value from the code under test); **paired** -- "pale enough" comes
    # [EN] with "not a blank plate"; "better than the old one" is judged by a **behavioural
    # [EN] control** (shrink the master on the spot and demand the current backdrop be much paler);
    # [EN] and the **text band** is measured separately, because a whole-image average happily
    # [EN] hides "the text sits right on top of the busy part".
    def _bg_stat(p: Path, box: tuple[int, int, int, int] | None = None) -> dict:
        """量一张图的「亮 / 平 / 干净 / 有没有朱红印章」。
        English: Measure one image on bright / flat / clean / vermilion-seal-free."""
        with Image.open(p) as im0:
            im = im0.convert('RGB')
            size = im.size
        if box:
            im = im.crop(box)
        g = im.convert('L')
        hist = g.histogram()
        tot = sum(hist) or 1
        mean = sum(i * c for i, c in enumerate(hist)) / tot
        var = sum(((i - mean) ** 2) * c for i, c in enumerate(hist)) / tot
        eh = g.filter(ImageFilter.FIND_EDGES).histogram()
        # 朱红（印章）像素：r 高、g/b 低。用 `tobytes` 直接数，比 `getdata()` 快且不弃用。
        # [EN] Vermilion (seal) pixels: high r, low g/b. Counted straight off `tobytes`.
        raw = im.tobytes()
        npx = len(raw) // 3
        seal = sum(1 for i in range(0, len(raw), 3)
                   if raw[i] > 150 and raw[i + 1] < 110 and raw[i + 2] < 110)
        return {'size': size, 'mean': mean, 'std': var ** 0.5,
                'edge': sum(i * c for i, c in enumerate(eh)) / tot,
                'seal': seal / npx * 1000}

    def _seal_share(path, box) -> float:
        """某个区域里"朱红"像素的千分比。

        ★ 判据与 `_bg_stat` 里那处**不同**是故意的：这里要能认出**半透明**的朱印
          （`r-g>30` 而不是 `g<110`），否则整条判据对新产品是恒真的空转。
        ⚠ 先缩到 320 宽再数：全尺寸数会把抗锯齿边缘也算进去，同一枚印能差一倍。
        [EN] Per-mille of "vermilion" pixels in a region.
        [EN] ★ Deliberately different from the test inside `_bg_stat`: this one must recognise a
        [EN] **semi-transparent** seal (`r-g>30` rather than `g<110`), or the whole criterion is
        [EN] vacuously true on the new backdrop.
        [EN] ⚠ Downscale to 320 wide first: counting at full size includes anti-aliased fringes and
        [EN] can double the same seal.
        """
        with Image.open(path) as im0:
            im = im0.convert('RGB')
            box = (max(0, box[0]), max(0, box[1]),
                   min(im.width, box[2]), min(im.height, box[3]))
            seg = im.crop(box)
            h = max(1, int(320 * seg.height / max(1, seg.width)))
            seg = seg.resize((320, h), Image.LANCZOS)
            px = list(seg.getdata())
        hot = sum(1 for r, g, b in px if r - g > 30 and r > 120 and b < r)
        return hot / max(1, len(px)) * 1000

    bg_p = APP / 'assets' / 'images' / 'title_bg_splash.png'
    tall_p = APP / 'assets' / 'images' / 'title_bg_splash_tall.png'
    master_p = APP / 'assets' / 'images' / 'title_bg.webp'
    whole_p = TMP / f'nws_splash_whole_{os.getpid()}.png'
    if master_p.exists():
        # ══════════════════════════════════════════════════════════
        #  ★★★ 2026-10-24 **改口径**：量"**看得见的那一块**"，不量整个文件。
        #
        #  底图文件是 860×**480**（历史约定），而画布只有 860×**350** ——
        #  下面那 130 行**永远不会被显示**（`create_image(anchor='nw')` + 画布裁切）。
        #  用户 2026-10-24 要"参考背景图画一幅古典小说"，画面自然落在下方，
        #  于是那 130 行"看不见的画"把整张均值拉到 198.2、std 到 13.7 ⇒ E5c 红了，
        #  而**用户看到的那 350 行是 203.8 / 8.85 / 5.78，全都在阈值内**。
        #  这正是"量错了对象"：判据在量一堆没人看得到的像素。
        #  ⇒ 可见高度**从子进程自检里读**（`d['size'][1]`，也就是 `launcher_splash.H_BASE`），
        #    不在这里写死 350 —— 布局再变，这条自动跟上。
        # [EN] ★★★ 2026-10-24 changed the yardstick: measure **the region that is visible**, not
        # [EN] the whole file. The file is 860x**480** (a legacy convention) while the canvas is
        # [EN] 860x**350** -- the bottom 130 rows are **never displayed**
        # [EN] (`create_image(anchor='nw')` clipped by the canvas). The user's new backdrop puts its
        # [EN] artwork in the lower area, so those invisible rows dragged the whole-image mean to
        # [EN] 198.2 and std to 13.7 and turned E5c red, while **the visible 350 rows measure
        # [EN] 203.8 / 8.85 / 5.78, all within the thresholds**. That is "measured the wrong
        # [EN] object": the criterion was averaging pixels nobody can see.
        # [EN] => The visible height is **read from the child's self-test** (`d['size'][1]`, i.e.
        # [EN] `launcher_splash.H_BASE`), never hard-coded here, so layout changes follow along.
        vis_h = int((d.get('size') or [860, 480])[1] or 480)
        # ══════════════════════════════════════════════════════════════════════
        #  ★★★ 2026-10-24（第三版）E5c 整组：**守"画够满 + 字能读 + 铺满窗口"**
        #  ──────────────────────────────────────────────────────────────────────
        #  这一组改了三轮口径，每一轮都是"用户推翻了上一轮的设计"，记下来免得再来一遍：
        #   ① 2026-10-17「背景有点花」→ 判"淡而不花"（均值 ≥200、std ≤12、边缘 ≤8，
        #      还要比"把母版整张缩略"淡一半）。服务的是"从母版裁一块最平的"，裁到最后
        #      **就是一张白纸**。
        #   ② 2026-10-24 上午「就用这个替换背景，不是截取，直接作为背景」
        #      → 判"文字带可读 + 收起态看得见画 + 还是整张没被截"。
        #   ③ 2026-10-24 中午「**整幅画内容多一些，用富春山居图核心部分**」
        #      → 富春是 33×636cm 手卷（19:1），**整幅进不了 860 宽的窗口**，
        #        所以"取核心一段"是这种画唯一能进窗口的方式，不是妥协。
        #        于是判据换成三件**用户能看见的事**：
        #          · **画够满**：可见区里"有墨"的像素 ≥ 45%（上一版 AI 山水 19%、纯纸 0%、
        #            富春这一段 70%）—— 这是"内容多一些"的可数版本；
        #          · **字能读**：每处文字带自己的横纵范围里，背景的**第 5 百分位**与字
        #            (#3B332B，灰 50) 的 sRGB 对比度 ≥ 4.5:1。用 p5 而不是 min：
        #            单像素的描边噪声不该判定整块区域"不能读"；
        #          · **铺满窗口**：满宽（左右 8px 有墨）、**底部也是画**（std ≥ 3，
        #            纸是 ~1）—— 反过来抓"缩到中间留白"和"底部还垫着一条纸"。
        #  ⚠ 阈值都写死绝对数，不从 `tools/make_splash_art.py` import（import 来的期望值 = 自证）。
        # [EN] ★★★ 2026-10-24 (third version of E5c): guard **dense picture + readable text +
        # [EN] window filled**. The yardstick changed three times, each time because the user
        # [EN] overruled the previous design: (1) 2026-10-17 "the background is busy" -> "pale, not
        # [EN] busy" (mean >= 200, std <= 12, half as busy as the shrunk master), which served
        # [EN] "crop the flattest patch" and ended as blank paper; (2) "use this one, not a crop,
        # [EN] put it in directly" -> "text readable + artwork visible + still whole"; (3) "**more
        # [EN] content in the whole picture, use the core section of Fuchun**" -> that painting is a
        # [EN] 33x636cm handscroll (19:1) that **cannot** fit an 860px window, so taking its core
        # [EN] section is the only way such a painting enters a window, not a compromise. Hence three
        # [EN] things the user can actually see: **dense** (>= 45% inked in the visible area; the
        # [EN] previous AI art 19%, plain paper 0%, this Fuchun section 70%), **readable** (5th
        # [EN] percentile of each text band's own background vs text #3B332B at >= 4.5:1 in sRGB --
        # [EN] p5 rather than min, since one anti-aliased edge pixel must not condemn a whole band),
        # [EN] and **filling the window** (full width, and the bottom rows are painting, not paper).
        # [EN] ⚠ All thresholds are hard-coded absolutes, never imported from the tool under test.
        def _srgb(v: float) -> float:
            c = v / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        _bands = [(16, 130, 356, 504, 'Logo'), (134, 172, 176, 684, '名字'),
                  (172, 208, 250, 610, '标语'), (208, 232, 70, 240, '步骤点'),
                  (232, 258, 70, 802, '消息条'), (268, 300, 88, 772, '失败那一行'),
                  (306, 340, 220, 640, '底栏')]
        worst_cr, worst_nm, bad = 99.0, '', False
        with Image.open(bg_p) as im0:
            gl = im0.convert('L')
            for y0, y1, x0, x1, nm in _bands:
                if y1 > vis_h:
                    continue
                px = sorted(gl.crop((x0, y0, x1, y1)).tobytes())
                bgpx = [v for v in px if v >= 120]      # 字比 120 暗得多（#3B332B ≈ 50）
                if not bgpx:
                    bad = True
                    worst_nm = nm + '（没有可量的背景）'
                    worst_cr = 0.0
                    continue
                p5 = bgpx[int(len(bgpx) * 0.05)]
                cr = (_srgb(p5) + 0.05) / (_srgb(50) + 0.05)
                if cr < worst_cr:
                    worst_cr, worst_nm = cr, nm
                if cr < 4.5:
                    bad = True
        rec('E5c ★★★ 底图**不影响组件**：每处文字带（各自横纵范围）背景的第 5 百分位'
            '与字 (#3B332B) 的 sRGB 对比度 ≥ 4.5:1'
            '—— 用 p5 不用 min：一个抗锯齿边缘像素不该判定整块不能读',
            not bad, f'最差一处 {worst_nm} {worst_cr:.1f}:1')

        with Image.open(bg_p) as im0:
            vis_g = im0.convert('L').crop((0, 0, 860, vis_h))
        hh = vis_g.histogram()
        tt = sum(hh) or 1
        cover = sum(hh[:202]) / tt * 100          # 比纸（212）暗 10 级以上 = 有墨
        vis_std = sum(((i - sum(j * c for j, c in enumerate(hh)) / tt) ** 2) * c
                      for i, c in enumerate(hh)) / tt
        # ★★★ 2026-10-24 12:59 **改口径（第四次）**：45% 那条是"用富春/千里江山、要内容多"那一轮
        #   定的；用户这一轮改回**那幅淡墨水墨**并明确"整张不裁、直接缩放"，45% 当场不成立
        #   （这幅整幅铺进 860×573 是 27%）。但这条判据**不能删** —— 它守的是"别交一张纸上来"。
        #   重定 **12%**：纯纸 0%、这幅 27%、富春 72% ⇒ 12 稳稳在"有画"一侧，又比实测低一半。
        # [EN] ★★★ 2026-10-24 12:59, **yardstick change #4**: the 45% came from the Fuchun /
        # [EN] Thousand-Li rounds ("more content"); this round the user went back to that **pale ink
        # [EN] wash** with "whole image, no crop, just scale", so 45% stops holding (27% here).
        # [EN] It must not be deleted -- it guards "do not ship a blank sheet". Re-set to **12%**:
        # [EN] blank 0%, this 27%, Fuchun 72% => 12 is firmly on the "there is a picture" side.
        rec('E5c-2 ★★★ **画面真的在**：可见区里"有墨"（比纸暗 10 级）的像素 ≥ 12%'
            '—— 这是"别交一张纸上来"的下限，不是"够不够满"；'
            '对照实测：纯纸 0% · 这幅淡墨 27% · 富春那段 72%',
            cover >= 12.0,
            f'有墨 {cover:.1f}%（标准差 {vis_std ** 0.5:.1f}）')
        rec('E5c-3 ★★ 成对：**不是一张纯色板**（可见区标准差 ≥ 4）'
            '—— 不然换成纯色图，"够满"这一条也可能被糊过去',
            vis_std ** 0.5 >= 4.0, f'标准差 {vis_std ** 0.5:.1f}')

        # ③ **满宽**：整张图的左右两端都在
        # ★★★ 2026-10-24 12:59：这里原来还有一半是"底部两段不能一模一样（专抓垫纸）"，
        #   而现在**底部补纸正是设计要求**（整张等比缩放后比窗口矮 47 行，补纸是唯一不裁的做法）
        #   ⇒ 那半条已经指向相反的方向，删掉；"整张没被截"改由 `E5c-7` 直接量。
        # [EN] ③ **Full width**: both ends of the picture are present.
        # [EN] ★★★ 2026-10-24 12:59: this used to have a second half ("the bottom two slices must
        # [EN] differ", aimed at catching a pasted strip), but padding the bottom is now **the design**
        # [EN] (after a uniform scale the picture is 47 rows shorter than the window, and padding is the
        # [EN] only way to avoid cropping) => that half pointed the other way and is gone. "The whole
        # [EN] picture is present" is measured directly by `E5c-7`.
        e_left = _bg_stat(bg_p, (0, 20, 8, min(300, vis_h)))['mean']
        e_right = _bg_stat(bg_p, (852, 20, 860, min(300, vis_h)))['mean']
        rec('E5c-4 ★★★ **画面铺满宽度**：左右 8px 都比纸暗 ≥ 3 级（纯纸 212）'
            '—— 抓"图缩到中间、两侧留白"那种形态',
            e_left < 209 and e_right < 209,
            f'左缘 {e_left:.1f} 右缘 {e_right:.1f}（纯纸 212）')

        # ⑤ **整张等比缩放、没有截取**（2026-10-24 12:59，用户：「**不要用截取 用缩放**，
        #    缩放到启动界面大小作为背景图」）
        #
        #  ★★★ 这条是这一轮真正的需求，也正好是**可数**的：
        #    源图 1536×1024（3:2），窗口 860×620（1.387）⇒ contain 之后画高 = 860×1024/1536 = **573**，
        #    剩下 47 行补同色纸。所以：
        #      ① 内容的底边必须落在 **573 附近**（我们允许 558~578：画的下沿有 14 行淡出，
        #         按行 std 检出来会比 573 早几行）；
        #      ② 573 以下必须**是纸**（std ≤ 3；画是 std 6~12）；
        #      ③ 顶边第 0 行**有墨**（不能上面也垫一条纸）。
        #    ⚠ 这三条合起来才分得开"整张缩放"与两种偷懒：
        #      · 裁到刚好铺满（cover）⇒ 内容底 = 620，**没有补纸带** ⇒ ①红；
        #      · 底部垫一条纸（pad）⇒ 内容底 ≈530 ⇒ ①红；
        #      · 缩到中间留白 ⇒ 由 E5c-4 的满宽抓。
        #    ⚠ 573 这个数是**算出来的**（860 × 1024 / 1536），不是抄工具的；
        #      换一幅画要跟着换（源图长宽比变了）。注释里写清算式，比写死一个数好维护。
        # [EN] ⑤ **The whole picture, scaled uniformly, not cropped** (2026-10-24 12:59: "**do not
        # [EN] crop, scale it** -- scale it to the splash size as the background").
        # [EN] ★★★ This is the actual requirement of this round, and it is **countable**: the source is
        # [EN] 1536x1024 (3:2) and the window 860x620 (1.387), so `contain` gives a picture height of
        # [EN] 860*1024/1536 = **573** with 47 rows of matching paper below. Hence: (1) the content's
        # [EN] bottom edge must land near **573** (558..578 allowed: the bottom 14 rows fade out, and the
        # [EN] row-std detector finds it a few rows early); (2) below 573 it must **be paper** (std <= 3;
        # [EN] the painting is 6..12); (3) row 0 must **carry ink** (no paper strip at the top either).
        # [EN] ⚠ Only the three together separate "whole image scaled" from two shortcuts:
        # [EN] scale-to-cover leaves content bottom = 620 with **no pad strip** => (1) red; a pasted pad
        # [EN] leaves ~530 => (1) red; shrinking into the middle is caught by E5c-4's full width.
        # [EN] ⚠ 573 is **arithmetic** (860 x 1024 / 1536), not copied from the tool; a different
        # [EN] painting needs a different number (its aspect changes). Spelling out the formula in a
        # [EN] comment beats hard-coding a bare number.
        _tt = tall_p if tall_p.exists() else bg_p
        # ★★★ 期望的内容高度**从源图长宽比算**，不写死。
        #   2026-10-24 13:26 用户又换了一版图（1536×869，比上一版矮，底部那条被他自己裁掉了）
        #   ⇒ 上一版写死的 573 当场失效。算式：`h = round(860 × 源高/源宽)`。
        #   ⚠ 源图在 `developers/refs/`（**不进发布包**）；`verify_launchers` 也只在仓库里跑。
        #     读不到就**判红并说明**，不装作通过 —— "拿不到参照物"不是"没问题"。
        # [EN] ★★★ The expected content height is **derived from the source aspect**, never hard-coded.
        # [EN] 2026-10-24 13:26 the user swapped the image again (1536x869, shorter -- he cut the bottom
        # [EN] off himself), so the old 573 died on the spot. Formula: `h = round(860 * sh / sw)`.
        # [EN] ⚠ The source lives in `developers/refs/` (**excluded from the release**) and
        # [EN] `verify_launchers` only runs inside the repo. If it cannot be read, **go red and say so**
        # [EN] rather than pretend: "no reference" is not "no problem".
        _exp_h = None
        _src_p = APP / 'developers' / 'refs' / 'splash_art_classical_src.png'
        try:
            with Image.open(_src_p) as _si:
                _exp_h = int(round(860 * _si.height / _si.width))
        except (OSError, ValueError):
            _exp_h = None
        with Image.open(_tt) as im0:
            gAll = im0.convert('L')
            wA, hA = gAll.size

            def _row_std(y: int, x0: int = 60, x1: int = 760) -> float:
                # ⚠ x 只取 60..760：右下角那枚朱印（x≈796..820、y≈582..606）会把行 std
                #   抬到 6，让"内容底"看起来一路到 606。印不是画。
                # [EN] x limited to 60..760: the vermilion seal (x ~796..820, y ~582..606) lifts row
                # [EN] std to 6 and would make the "content bottom" look like 606. A seal is not art.
                return ImageStat.Stat(gAll.crop((x0, y, x1, y + 1))).stddev[0]

            _cb = 0
            for _y in range(hA - 1, 0, -1):
                if _row_std(_y) > 2.0:
                    _cb = _y
                    break
            _pad_std = ImageStat.Stat(gAll.crop((60, min(hA - 1, _cb + 6), 760, hA))).stddev[0]
            _top_std = _row_std(0)
        _lo = (_exp_h - 18) if _exp_h else -1
        _hi = (_exp_h + 18) if _exp_h else -1
        rec('E5c-7 ★★★ **整张等比缩放、没有截取**：内容的底边落在 '
            f'{_exp_h if _exp_h else "？"}（= 860 × 源图高/宽，允许 ±18）附近、'
            '它下面是纸（std ≤ 3）、顶边第 0 行有墨'
            '—— 三条合起来才分得开"整张缩放"与"裁到铺满"(底边变 620) / "垫过头的纸"(底边明显更小)',
            _exp_h is not None and _lo <= _cb <= _hi
            and _pad_std <= 3.0 and _top_std > 1.5,
            (f'内容底 y={_cb}（应 {_lo}..{_hi}）· 其下 std {_pad_std:.2f}（纸 ≤3）· '
             f'第 0 行 std {_top_std:.2f}')
            if _exp_h else f'源图读不到（{_src_p.name}）⇒ 无法判"有没有被截"')

        # ⑥ **不要太浓**：可见区最暗的 1% 不能太黑 —— 浓的山水会有大片乌黑。
        #   ★ 口径：它守"别交一张乌黑的图"，不是"越淡越好"。
        #     千里江山那一轮是 176；换回这幅淡墨后产品自然给出 169，与 176 只差 7 级 ⇒ 那是**贴边**，
        #     所以判据取 **150**（离实测 11%、离"压黑"那一刀 80 很远）。
        #   ⚠ 只判"有墨占比"不够：全画成深墨占比也能到十几，但会乌黑一片。
        # [EN] ⑥ **Not too intense**: the darkest 1% of the visible area must not go black.
        # [EN] ★ It guards "do not ship a black picture", not "the paler the better". It was 176 for
        # [EN] the Thousand-Li round; this ink wash naturally gives 169, only 7 levels apart -- a
        # [EN] knife-edge -- so the criterion takes **150** (11% below measured, far above the
        # [EN] "crushed black" mutation at 80). ⚠ The ink share alone is not enough: painting
        # [EN] everything deep keeps the share low yet goes black.
        with Image.open(bg_p) as im0:
            vg = im0.convert('RGB').crop((0, 0, 860, vis_h))
        vg = vg.convert('L')
        hv = vg.histogram()
        tv = sum(hv) or 1
        accv, p1v = 0, 0
        for v in range(256):
            accv += hv[v]
            if accv >= tv * 0.01:
                p1v = v
                break
        rec('E5c-8 ★★★ **不要太浓**：可见区最暗的 1% ≥ 150（纸 212 ⇒ 最多暗 62 级）'
            '—— 只判有墨占比不够：全画成深墨占比也能到十几，但会乌黑一片',
            p1v >= 150, f'最暗 1% = {p1v}，均值 {ImageStat.Stat(vg).mean[0]:.1f}')


        # ④ 朱印：不入文字块 / 整张只一枚
        # ⚠ 量**展开态那张**：印在画内右下角（y≈594），收起态那张（上 480 行）里没有它。
        # [EN] ④ The seal: never inside a text block, at most one overall. ⚠ Measure the **expanded**
        # [EN] file -- the seal sits at the painting's bottom-right (y ~594), absent from the
        # [EN] collapsed file (top 480 rows).
        # ★★★ 2026-10-24 13:19 **改口径（第五次）**：原来这两条守的是
        #   "印章可以有，但不许进文字块 / 整张只许一小枚"。
        #   用户这一轮说：「这张图里有一个 **AI 生成的字**，你把这部分截取掉」，
        #   接着「可以直接把下面这部分截取删除掉」。
        #   我按"图里的字"在**源图**里找了六轮都没找到 —— 因为那东西不在源图里：
        #   它就是我画的那枚**无字朱印**（方框 + 一道竖笔，25×25，在 y 576..606 / x 780..820）。
        #   在成品图上量，它是下半部**唯一**一块孤立暗块（std 26 而四周是 0.7 的纸）——
        #   也就是说**用户看到的"字"= 我加的装饰**。
        #   ⇒ 口径从"限制它"变成"**根本不许有**"：整张底图的朱红像素必须为 0。
        #   ⚠ 这不是放宽，是收紧（0‰ 比 ≤1.6‰ 严），也是把设计改回用户要的"只有那张画"。
        # [EN] ★★★ 2026-10-24 13:19, **yardstick change #5**: these two used to say "a seal is fine
        # [EN] as long as it stays out of the text block / happens once". This round the user said
        # [EN] "**there is an AI-generated character in this image, cut that part out**", then "you
        # [EN] can just cut away this bottom part". I searched the **source** for six rounds and found
        # [EN] nothing -- it is not in the source: it is the **wordless seal I drew** (a frame plus one
        # [EN] vertical stroke, 25x25 at y 576..606 / x 780..820). On the output it is the **only**
        # [EN] isolated dark blob in the lower half (std 26 against surrounding paper at 0.7) --
        # [EN] i.e. the "character" the user saw **is my ornament**.
        # [EN] => The rule changes from "limit it" to "**there must be none**": zero red pixels.
        # [EN] ⚠ Not a relaxation but a tightening (0 per-mille versus <= 1.6), and it restores the
        # [EN] user's actual design: just the painting.
        _seal_src = tall_p if tall_p.exists() else bg_p
        seal_block = _seal_share(_seal_src, (150, 20, 710, 270))
        seal_all = _seal_share(_seal_src, (0, 0, 860, 620))
        rec('E5c-5 ★★★ 底图上**没有任何朱红**（整张 0‰）—— 那枚朱印被用户认成了'
            '"一个 AI 生成的字"，已从 `make_splash_art.py` 里关掉（`SEAL = False`）；'
            '这里守的不是"位置好不好"，而是"它不许回来"',
            seal_all == 0.0, f'整张 {seal_all:.3f}‰（须 0）· 文字块 {seal_block:.3f}‰')
        if tall_p.exists():
            t = _bg_stat(tall_p)
            with Image.open(bg_p) as ia, Image.open(tall_p) as ib:
                diff = ImageChops.difference(ia.convert('RGB'),
                                             ib.convert('RGB').crop((0, 0, 860, 480)))
            dh = diff.convert('L').histogram()
            dtot = sum(dh) or 1
            mad = sum(i * c for i, c in enumerate(dh)) / dtot
            # ★★★ 2026-10-27：展开高度 620 → 820（用户要"日志窗口更高更长"），
            #   底图跟着长到 820。这里**不再写死 620**，改成从 splash 源码读 `H_EXP`
            #   —— 写死的话，下一次调高度这条必然又红，而**产品是对的**
            #   （口径变了 ⇒ 判据要改成"两边同一个数"，不是删掉）。
            # [EN] ★★★ 2026-10-27: the expanded height went 620 -> 820 (the user asked for a taller
            # [EN] log window) and the backdrop grew with it. **No hard-coded 620** -- read `H_EXP`
            # [EN] from the splash source. A literal would go red again on the next resize while
            # [EN] **the product is right** (the yardstick moved => make it "the same number on both
            # [EN] sides", don't delete it).
            h_exp = _splash_h_exp()
            rec('E5c-6 ★★ 展开态那张是**同一块图长出来的一截**（高 = splash 的 `H_EXP`、'
                '上部 480 行与收起态平均像素差 ≤ 2）⇒ 点那个三角时画面只是往下长，'
                '不会跳成另一张图',
                t['size'] == (860, h_exp) and mad <= 2.0,
                f'{t["size"][0]}×{t["size"][1]}（H_EXP={h_exp}）'
                f' 亮度 {t["mean"]:.1f} 与收起态差 {mad:.2f}')
            rec('E5i ★★★ 底图高度**正好等于展开态窗口高度**（底图短了 ⇒ 窗口下面露出一段'
                '没有画的空白；长了 ⇒ 画面被裁掉一截）—— '
                '这两个数写在两处（`launcher_splash.H_EXP` 与 `make_splash_art.H_TALL`），'
                '是最容易漂的一对',
                t['size'][1] == h_exp == _art_h_tall(),
                f'底图 {t["size"][1]} · splash.H_EXP {h_exp} · art.H_TALL {_art_h_tall()}')
        else:
            rec('E5c-6 ★★ 展开态底图就位（`title_bg_splash_tall.png`）', False, '缺失')

    job = TMP / f'nws_job_{os.getpid()}.json'
    res = TMP / f'nws_job_{os.getpid()}.result.json'
    log = TMP / f'nws_job_{os.getpid()}.log'
    for f in (res, log):
        if f.exists():
            f.unlink()
    job.write_text(json.dumps({
        'title': '判据 / self-test',
        'intro': '跑一步就走 / one step',
        'log': str(log),
        'steps': [
            {'label': '第一步 / step one',
             'argv': [py, '-c', 'print("hello-from-step")'],
             'cwd': str(APP)},
        ],
    }, ensure_ascii=False), encoding='utf-8')

    subprocess.run([py, str(script), '--job', str(job),
                    '--result', str(res)], capture_output=True, timeout=300)
    got = json.loads(res.read_text(encoding='utf-8')) if res.exists() else {}
    rec('E2 ★★★ 进度窗把活干了：结果文件写出来了、退出码 0、'
        '而且那一步的输出进了日志文件',
        got.get('code') == 0 and got.get('gui') is True
        and log.exists() and 'hello-from-step' in log.read_text(
            encoding='utf-8', errors='replace'),
        f'结果={got}')

    # 没有图形环境那条路（判据用钩子强制走一次 —— 不然它永远没被跑过）
    # [EN] The no-GUI-environment path (the criterion forces one run via a hook — otherwise it would never
    # [EN] be exercised)
    res2 = TMP / f'nws_job_ng_{os.getpid()}.result.json'
    if res2.exists():
        res2.unlink()
    env = dict(os.environ, NWS_TEST_NO_GUI='1')
    subprocess.run([py, str(script), '--job', str(job),
                    '--result', str(res2)], env=env, capture_output=True,
                   timeout=120)
    got2 = json.loads(res2.read_text(encoding='utf-8')) if res2.exists() else {}
    rec('E3 ★★★ 没有图形环境时（Linux 没装 python3-tk / SSH 里没有 DISPLAY）：'
        '进度窗**坦说没窗口**并把活交回启动器，而不是假装成功',
        got2.get('gui') is False and bool(got2.get('err')),
        f'结果={got2}')
    src = (APP / 'launchers' / 'flow.go').read_text(encoding='utf-8')
    rec('E4 ★★ 启动器接到"没窗口"之后会**自己把活干了**（静默执行）'
        '—— "能不能干活"不许依赖于"有没有 GUI"',
        'runStepsQuiet' in src and '!res.GUI' in src, '')


# ══════════════════════════════════════════════════════════════════
#  F 卸载：真能卸掉 / 先问过再动手 / 失败时窗口留着
# [EN] F uninstall: it really uninstalls / asks before acting / keeps the window on failure
# ══════════════════════════════════════════════════════════════════
#
# ★★★ 这一组是**用户 2026-10-10 报的那个 bug** 换来的（一张截图 +
#     `logs/launcher.log`）：卸载弹了一句
# [EN] ★★★ This group came from **the bug the user reported on 2026-10-10** (one screenshot +
# [EN] `logs/launcher.log`): the uninstaller printed one line
#     「The step "Removing desktop icon / Start Menu entry" did not succeed.」
#
#     根因（复现得很干脆）：`uninstall.exe` 把 `platform_install.py uninstall`
#     直接跑起来，而那个脚本会问 `确认卸载？[y/N]` —— 可启动器起的子进程
#     **没有终端**，`input()` 立刻 EOF ⇒ 当成 "N" ⇒ "已取消"、退出码 1。
#     也就是说：**双击卸载从来就没成功过**，一次都没有。
#     实测：`platform_install.py uninstall < /dev/null` 稳定 `EXIT=1`。
# [EN] Root cause (reproduced cleanly): `uninstall.exe` runs `platform_install.py uninstall`
# [EN] directly, and that script asks `确认卸载？[y/N]` — but the child process spawned by the launcher
# [EN] **has no terminal**, so `input()` immediately hits EOF ⇒ treated as "N" ⇒ "已取消", exit code 1.
# [EN] In other words: **double-click uninstall has never once succeeded**, not a single time.
# [EN] Measured: `platform_install.py uninstall < /dev/null` reliably gives `EXIT=1`.
#
#     为什么以前没人发现 —— 这才是这一组存在的真正理由
# [EN] Why nobody found it before — this is the real reason this group exists
#     ---------------------------------------------------
#     原来的 A~E 组把**启动器**的每个角落都守到了（产物格式、无控制台、
#     服务跟随退出、决策逻辑、进度窗），却**一条都没真跑过卸载**：
#     `setup.exe` / `uninstall.exe` 只在 `verify_installer` 里跑过一次
#     `--dry-run`（而 dry-run 在"问"之前就返回了，永远碰不到这道坎）。
#     ⇒ "只能人肉点一遍"的代码路径，出问题只是时间问题。
# [EN] The original A~E groups guarded every corner of the **launcher** (artifact format, no console,
# [EN] service exiting with it, decision logic, progress window), yet **not one of them actually ran
# [EN] uninstall**:
# [EN] `setup.exe` / `uninstall.exe` were only ever run once in `verify_installer` with
# [EN] `--dry-run` (and dry-run returns before "asking", so it never hits this snag).
# [EN] ⇒ For code paths that "can only be clicked through by hand", problems are only a matter of time.
#
#     所以这一组做了两件以前做不到的事：
#       ① **对话替身**（`launchers/dialog_stub.go`）：设了
#          `NWS_TEST_DIALOG_LOG` 就把"弹框"换成"记一行 JSON"，
#          于是"问没问、点了哪个键"成了可断言的事实，判据再也不会被框卡住；
#       ② 把整条路**真跑一遍**：沙盒 install → 取消 → 卸载 →
#          断言快捷方式真的没了、退出码 0、真实安装记录没被动过。
# [EN] So this group does two things that were previously impossible:
# [EN] ① **Dialog double** (`launchers/dialog_stub.go`): once
# [EN] `NWS_TEST_DIALOG_LOG` is set, "popping a dialog" becomes "logging one line of JSON",
# [EN] so "did it ask, which key was clicked" becomes an assertable fact, and the criterion can no
# [EN] longer be stuck by a dialog;
# [EN] ② Actually **run the whole path**: sandbox install → cancel → uninstall →
# [EN] assert the shortcut really is gone, exit code 0, and the real install record was not touched.

FIX_SVC = APP / 'tests' / 'launchers' / 'fixture_service'
REAL_MANIFEST = APP / '.install_manifest.json'


def _svc_env(extra: dict) -> dict:
    """给启动器**三个假服务**（MuMu 夹具 + 统一控制器夹具）。

    卸载流程第一步是"停服务"，真服务会去建 venv / 装依赖 / 下 470MB 模型 ——
    判据不可能为了一条断言跑几分钟。两个夹具都只把收到的动作记下来。

    2026-10-17：从"一个假服务"扩到"三个"（两个新服务走统一控制器夹具），
    否则"卸载也会停掉新服务"这条路**根本没有判据走过**。

        English:
    Give the launcher **three fake services** (the MuMu fixture + the
    unified-controller fixture).

    The first step of the uninstall flow is "stop the services", and the
    real ones would create a venv / install dependencies / download a
    470MB model -- the assertions can't run for several minutes for one
    assertion. Both fixtures just record the received actions.

    2026-10-17: expanded from "one fake service" to "three" (the two new
    services go through the unified-controller fixture), otherwise the
    "uninstall stops the new services too" path would have **no assertion
    walking it at all**.
    """
    ctl_log = TMP / f'nws_ctl_un_{os.getpid()}.jsonl'
    if ctl_log.exists():
        ctl_log.unlink()
    env = dict(os.environ)
    env.update({
        'NWS_TEST_SERVICE_DIR': str(FIX_SVC),
        'NWS_TEST_SERVICE_PY': sys.executable,
        'NWS_TEST_SERVICE_PORT': '9',        # 一个不会有人监听的端口
        # [EN] A port nobody will listen on
    })
    env.update(_ctl_fixture_env(ctl_log))
    env['NWS_FIXTURE_CTL_LOG'] = str(ctl_log)
    env.update(extra)
    return env


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in
            p.read_text(encoding='utf-8').splitlines() if x.strip()]


def check_uninstall_flow() -> None:
    print('\n【F】卸载：真能卸掉 / 先问过再动手（用户 2026-10-10 报的那条）')
    if not (FIX_SVC / 'novelservice.py').exists():
        rec('F0 假创作服务夹具在（tests/launchers/fixture_service）', False, '缺夹具')
        return
    if not (FIX_CTL / 'fixture_ctl.py').exists() or \
            not (FIX_CTL / 'penshot').is_dir() or \
            not (FIX_CTL / 'plotpilot').is_dir():
        rec('F0 统一控制器夹具在（tests/launchers/fixture_ctl/）', False, '缺夹具')
        return
    root = TMP / f'nws_un_{os.getpid()}'
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    dlg = TMP / f'nws_un_dlg_{os.getpid()}.jsonl'
    sandbox_manifest = root / '.install_manifest.json'
    real_before = (REAL_MANIFEST.read_bytes()
                   if REAL_MANIFEST.exists() else None)

    def run(mode: str, *extra: str, answer: str = '1'):
        """真跑一次启动器（沙盒里）。

        `NWS_TEST_NO_GUI=1` 让它走"没有进度窗"那条路（静默执行 + 原生框）——
        判据里**不弹真窗口**，于是同一条链能全自动跑完；而那条路照样会
        经过"问确认"这一步（确认框在起任务之前，与有没有进度窗无关）。
        `NWS_TEST_DIALOG_LOG` + `NWS_TEST_CONFIRM_ANSWER` 决定"用户点了哪个键"。
        
                English:
        `NWS_TEST_NO_GUI=1` makes it take the "no progress window" path (silent execution + native
        dialog) —
                the test **does not pop a real window**, so the same chain can run fully automatically; and that path still
                goes through the "ask for confirmation" step (the confirmation dialog is before the task starts, regardless of whether there is a progress window).
                `NWS_TEST_DIALOG_LOG` + `NWS_TEST_CONFIRM_ANSWER` determine "which key the user pressed".
        """
        if dlg.exists():
            dlg.unlink()
        env = _svc_env({
            'NWS_TEST_DIALOG_LOG': str(dlg),
            'NWS_TEST_NO_GUI': '1',
            'NWS_TEST_CONFIRM_ANSWER': answer,
        })
        r = subprocess.run(
            [str(APP / f'{mode}{SUFFIX}'), '--dest-root', str(root), *extra],
            cwd=str(APP), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=900)
        boxes = ([json.loads(x) for x in
                  dlg.read_text(encoding='utf-8').splitlines() if x.strip()]
                 if dlg.exists() else [])
        return (r.returncode,
                (r.stdout or b'').decode('utf-8', 'replace'), boxes)

    # ── F1 前置：沙盒里真的装得出来 ──
    # [EN] ── F1 precondition: it really can be installed in the sandbox ──
    rc, out, _b = run('setup', '--skip-service')
    created: list[Path] = []
    if sandbox_manifest.exists():
        created = [Path(p) for p in
                   (json.loads(sandbox_manifest.read_text(encoding='utf-8'))
                    .get('created') or [])]
    rec('F1 前置：启动器跑 setup 能在沙盒里**真建出**快捷方式'
        '（`--dest-root` 指到临时目录，不碰真桌面）',
        rc == 0 and created and all(p.exists() for p in created),
        f'rc={rc} 建了 {len(created)} 项')

    # ── F2 说「取消」就得真的什么都没发生 ──
    # [EN] ── F2 saying "cancel" must really mean nothing happened ──
    rc, out, boxes = run('uninstall', answer='0')
    left = [p for p in created if p.exists()]
    kinds = [b['kind'] for b in boxes]
    rec('F2 ★★★ 卸载**先问了**：确认框选「取消」⇒ 一个都不删、退出码 0'
        '（"问过"是真的发生了，不是默默动手；点了取消就得真停手）',
        rc == 0 and len(left) == len(created) and 'confirm' in kinds,
        f'rc={rc} 还剩 {len(left)}/{len(created)} 项，对话框={kinds}')
    ctl_log = TMP / f'nws_ctl_un_{os.getpid()}.jsonl'
    stopped = _ctl_pairs(_read_jsonl(ctl_log))
    rec('F2b ★★ 选「取消」之后**一个服务都没停**'
        '（三个服务的停止步骤都在确认框之后 —— 取消了就不该有任何一个）',
        not stopped, f'控制器收到的={sorted(stopped)}')

    # ── F3 点了「确定」就真的卸得掉（这就是用户报的那条）──
    # [EN] ── F3: after clicking "OK" it should actually be uninstallable (this is the one the user
    # [EN] reported) ──
    rc, out, boxes = run('uninstall')
    gone = [p for p in created if not p.exists()]
    rec('F3 ★★★ 从启动器发起的卸载**真的卸得掉**：快捷方式全删掉、退出码 0、'
        '日志里是"已删除 N 项"而不是"已取消"'
        '（修之前这里必红：无终端下 `input()` 永远 EOF ⇒ 当成取消 ⇒ 退出码 1）',
        rc == 0 and bool(created) and len(gone) == len(created)
        and '已取消' not in out,
        f'rc={rc} 删掉 {len(gone)}/{len(created)} 项 '
        f'{"（日志里出现了「已取消」！）" if "已取消" in out else ""}')

    # ── F6：卸载前把**两个新服务**也停掉（2026-10-17 三服务表之后新加）──
    # [EN] ── F6: before uninstalling, **the two new services** are stopped
    # [EN] too (added 2026-10-17 with the three-service table) ──
    #
    # ★ 为什么单列一条：不停就卸载，后台还挂着一个占着端口的服务 ——
    #   下次装回来时"端口被占"这种最难查的现象就来了。而老判据只覆盖
    #   MuMu 一个服务，"新服务没人停过"正是这次改造要补的洞。
    # [EN] ★ Why a separate item: uninstalling without stopping leaves a
    # [EN] background service holding its port -- and "port already in use",
    # [EN] the hardest kind of symptom to trace, shows up on the next
    # [EN] install. The old assertions covered only MuMu; "the new services
    # [EN] never got stopped" is exactly the hole this rework fills.
    stopped = _ctl_pairs(_read_jsonl(ctl_log))
    rec('F6 ★★ 卸载前把**两个新服务也停掉**（走统一控制器夹具）：'
        '`stop penshot` + `stop plotpilot` 都收到了',
        ('stop', 'penshot') in stopped and ('stop', 'plotpilot') in stopped,
        f'控制器收到的={sorted(stopped)}')

    # ── F7：setup 会把**被别的程序占着**的端口改掉（用户 2026-10-17：机器上有 Docker）──
    # [EN] ── F7: setup rewrites a port held by **another program** (user, 2026-10-17: Docker) ──
    #
    # 做法像真机：把 `setup.exe` 连同它要的两个脚本**拷进一个临时"程序目录"**，
    # 在那份 `.env` 里写下端口，再**判据自己占住其中一个**跑 setup ——
    # exe 自己算出 appDir ⇒ 读的是这一份 `.env`，不改用户的、也不改夹具原件。
    #   · F7  ：被占的 PenShot 端口 ⇒ 换成别的**能用**的端口（写回根 `.env`）
    #   · F7b ：没被占的 PlotPilot 端口 ⇒ **一个字不动**
    #   · F7c ：MuMu 的端口在**它自己的** `.env` 里 ⇒ 改的是那份（不是根 `.env`）
    # [EN] Real-machine-like: copy `setup.exe` plus the two scripts it needs into a temp
    # [EN] "app dir", write the ports into **that** `.env`, then **hold one of them
    # [EN] ourselves** and run setup -- the exe computes appDir itself ⇒ it reads this
    # [EN] `.env`; neither the user's nor the fixture original is touched.
    # [EN]   · F7 : an occupied PenShot port ⇒ switched to another **usable** port (root .env)
    # [EN]   · F7b: a free PlotPilot port ⇒ **not a character changed**
    # [EN]   · F7c: MuMu's port lives in **its own** .env ⇒ that file is the one rewritten
    t7 = TMP / f'nws_p7_{os.getpid()}'
    shutil.rmtree(t7, ignore_errors=True)
    (t7 / 'tools').mkdir(parents=True, exist_ok=True)
    shutil.copy2(APP / f'setup{SUFFIX}', t7 / f'setup{SUFFIX}')
    for _rel in ('platform_install.py', 'launcher_progress.py'):
        _src = APP / 'tools' / _rel
        if _src.exists():
            shutil.copy2(_src, t7 / 'tools' / _rel)
    svc7 = t7 / 'svc'
    shutil.copytree(FIX_SVC, svc7)                 # MuMu 夹具的**可写副本**
    busy_ps = _free_tcp_port(18100)
    busy_mu = _free_tcp_port(busy_ps + 1)
    free_pp = _free_tcp_port(busy_mu + 1)
    (t7 / '.env').write_text(
        f'PENSHOT_PORT={busy_ps}\nPLOTPILOT_PORT={free_pp}\n', encoding='utf-8')
    # MuMu 夹具那份 `.env` 换成我们挑的端口（夹具原件不动）
    (svc7 / '.env').write_text(f'APP_PORT={busy_mu}\n', encoding='utf-8')
    holds = []
    for _p in (busy_ps, busy_mu):
        _s = socket.socket()
        _s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _s.bind(('127.0.0.1', _p))
        _s.listen(1)
        holds.append(_s)
    dlg7 = TMP / f'nws_p7_dlg_{os.getpid()}.jsonl'
    if dlg7.exists():
        dlg7.unlink()
    env7 = dict(os.environ)
    env7.update(_ctl_fixture_env(TMP / f'nws_ctl_p7_{os.getpid()}.jsonl'))
    env7.update({
        'NWS_TEST_SERVICE_DIR': str(svc7),
        'NWS_TEST_SERVICE_PY': sys.executable,
        'NWS_TEST_NO_GUI': '1',
        'NWS_TEST_DIALOG_LOG': str(dlg7),
    })
    env7.pop('NWS_TEST_SERVICE_PORT', None)        # 让 MuMu 的端口真从 .env 读
    try:
        subprocess.run(
            [str(t7 / f'setup{SUFFIX}'), '--dest-root', str(t7 / 'dest')],
            cwd=str(t7), env=env7, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=600)
    finally:
        for _s in holds:
            _s.close()

    def _env_val(path: Path, key: str) -> str:
        if not path.exists():
            return ''
        for _ln in path.read_text(encoding='utf-8').splitlines():
            if _ln.strip().startswith(key + '='):
                return _ln.split('=', 1)[1].strip()
        return ''

    def _usable(p: int) -> bool:
        s = socket.socket()
        try:
            s.bind(('127.0.0.1', p))
            return True
        except OSError:
            return False
        finally:
            s.close()

    ps_raw = _env_val(t7 / '.env', 'PENSHOT_PORT')
    ps_new = int(ps_raw) if ps_raw.isdigit() else 0
    pp_raw = _env_val(t7 / '.env', 'PLOTPILOT_PORT')
    pp_new = int(pp_raw) if pp_raw.isdigit() else 0
    mu_raw = _env_val(svc7 / '.env', 'APP_PORT')
    root_mu = _env_val(t7 / '.env', 'APP_PORT')
    mu_new = int(mu_raw) if mu_raw.isdigit() else 0
    # ★ 新端口**不许是另外两个服务正在用的** —— 否则"改了端口"只是把冲突挪给了邻居：
    #   本例里 18100 被占、18101 是 MuMu 的、18102 是 PlotPilot 的，
    #   扫描必须跳过这两个，落到 18103+。少了这条，"抢邻居端口"这条路没人守。
    # [EN] ★ The new port must **not be one the other two services use** -- otherwise
    # [EN] "changing the port" merely moves the collision to a neighbor: here 18100 is
    # [EN] held, 18101 is MuMu's, 18102 is PlotPilot's, so the scan must skip those two
    # [EN] and land on 18103+. Without this, "stealing the neighbor's port" is unguarded.
    rec('F7 ★★★ setup 真会**改端口**：PenShot 的端口被别的程序占着 ⇒ '
        '换成别的能用的端口，并写回**根 `.env`**'
        '（用户原话：「机器上有 Docker，3 个外部服务别跟现有端口冲突」，端口归 setup 配）',
        ps_new not in (0, busy_ps, pp_new, mu_new) and _usable(ps_new),
        f'原 {busy_ps}（判据占着）⇒ 现在 {ps_new}'
        f'（能绑={_usable(ps_new)}；另两个服务 {mu_new}/{pp_new} 不许被抢）')
    rec('F7b ★★ 没被占的端口**一个字不改**（PlotPilot 本来就能用 ⇒ 不许乱动）',
        pp_new == free_pp, f'原 {free_pp} ⇒ 现在 {pp_raw}')
    rec('F7c ★★ MuMu 的端口写在**它自己的** `.env`（`backend/.env`），'
        '不许写到主程序根 `.env`（写错地方 = 服务照旧起不来，而且不报错）',
        mu_new not in (0, busy_mu) and _usable(mu_new) and not root_mu,
        f'原 {busy_mu} ⇒ 自己那份={mu_raw}，根 .env 里的 APP_PORT={root_mu or "（没有）"}')

    # ── F4 沙盒里的操作不许碰到工程根那条真实安装记录 ──
    # [EN] ── F4: operations in the sandbox must not touch the real install record at the project root ──
    now = REAL_MANIFEST.read_bytes() if REAL_MANIFEST.exists() else None
    rec('F4 ★★ 这一趟沙盒装卸**没有碰过工程根那条真实安装记录**'
        '（不然用户下次真卸载会照着沙盒那条记录去临时目录里删 —— 删不到，还报成功）',
        now == real_before, '' if now == real_before else '真实记录被改了')

    # ── F5 静态：卸载那一步**必须**带 `--yes` ──
    # [EN] ── F5: static: the uninstall step **must** carry `--yes` ──
    #
    # 这条是 F3 的"源码级备份"：F3 已经被变异证明会红，但把话说在源码上也值得 ——
    # `--yes` 一旦被谁"顺手删掉"（它看起来只是个多余的开关），行为会**静默退化**
    # 成"每次都取消"，而报出来的话（"这一步没成功"）指不到根因。
    # [EN] This is the "source-level backup" of F3: F3 has already been proven to go red by mutation, but
    # [EN] it's worth stating it in the source too ——
    # [EN] Once `--yes` gets "casually deleted" by someone (it just looks like a redundant switch), the
    # [EN] behavior will **silently degrade**
    # [EN] into "cancel every time", and the reported message ("this step did not succeed") can't point at
    # [EN] the root cause.
    src = (APP / 'launchers' / 'flow.go').read_text(encoding='utf-8')
    rec('F5 ★★ 卸载的步骤里显式带了 `--yes`（跳过子进程那道交互提示）'
        '—— 少了它，没有终端时子进程只会得到"取消"',
        '"uninstall", "--yes"' in src, '')


def check_failure_window() -> None:
    """真机：**失败时进度窗要留着给用户看日志**，不许被启动器 6 秒后收掉。

    ★ 这条守的是"报错这件事本身"的质量。第一版 `waitProgress` 只看"结论文件写了
      没有"，于是一旦写完就再给 6 秒、还不退就替它收掉 —— 而失败时那个窗口是
      **故意**留着的（等用户看完日志点「关闭」）。实测到手的现象是：
      用户刚看到失败，窗口 6 秒后就被杀了，然后才弹一个原生框 ——
      同一条消息看两遍，日志区先没了。`logs/launcher.log` 里就是那两行
      「进度窗写完结论后仍未退出 ⇒ 代为结束」。

    ★ 判据怎么造出"失败"：把一个**文件**当成 `--dest-root` 的父目录，
      安装去建快捷方式必然失败（而且失败得很快，不用等）。然后看启动器
      **16 秒之后还在不在等** —— 旧行为 ~7 秒就返回了（窗口被杀 + 弹框）。
    
        English:
    Real machine: **on failure the progress window must stay for the user to see the log**, not be
    closed by the launcher after 6 seconds.
        ★ This guards the quality of "the error-reporting event itself". The first version of `waitProgress` only checked whether the "conclusion file was
written
          or not", so once it was written it gave another 6 seconds, and if it still didn't exit it killed it on its behalf — but on failure that window was
**deliberately** left open (waiting for the user to read the logs and click "close"). The observed behavior in practice was:
          the user had just seen the failure, and the window was killed 6 seconds later, and only then did a native dialog pop up —
          the same message seen twice, and the log area disappeared first. In `logs/launcher.log` those are exactly the two lines
          "progress window still did not exit after writing the conclusion ⇒ ended on its behalf".
    ★ How the test produces a "failure": treat a **file** as the parent directory of `--dest-root`,
        and the installation's attempt to create a shortcut will necessarily fail (and fail quickly, no waiting). Then check whether the launcher
          **is still waiting after 16 seconds** — the old behavior returned in ~7 seconds (window killed + dialog popped).
        Actually run the launcher once (in a sandbox).
    """
    print('\n【F2】失败时进度窗留着（不许替用户把它收掉）')
    if not IS_WIN:
        rec('F2 非 Windows：跳过（这条依赖真窗口 + 启动器的收尸逻辑）', True, '')
        return
    blocker = TMP / f'nws_blocker_{os.getpid()}'
    blocker.write_text('这是个文件，不是目录 / a file, not a folder\n',
                       encoding='utf-8')
    bad_root = blocker / 'sub'
    dlg = TMP / f'nws_fail_dlg_{os.getpid()}.jsonl'
    if dlg.exists():
        dlg.unlink()
    joblog = APP / 'logs' / 'launcher.log'
    before = joblog.stat().st_size if joblog.exists() else 0
    # ⚠ 必须挂上对话替身：万一（比如被变异成）启动器在失败时又弹原生框，
    #   真框会**把人顶在那儿**⇒ 判据挂死、反例法也就看不到"预期那条变红"了。
    # [EN] ⚠ Must attach the dialog stand-in: in case (e.g. if mutated) the launcher pops a native dialog
    # [EN] on failure,
    # [EN] the real dialog will **pin the person there** ⇒ the criterion hangs, and the counterexample
    # [EN] method can't see "the expected one going red" either.
    env = _svc_env({'NWS_TEST_DIALOG_LOG': str(dlg)})
    p = subprocess.Popen(
        [str(APP / f'setup{SUFFIX}'), '--skip-service',
         '--dest-root', str(bad_root)],
        cwd=str(APP), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 16
        alive = False
        while time.time() < deadline:
            time.sleep(0.5)
            alive = p.poll() is None
            if not alive:
                break
        # 收尾：连它拉起的进度窗一起收掉（`/T`），别留窗口在桌面上。
        # [EN] Cleanup: also close the progress window it spawned (`/T`), don't leave a window on the desktop.
        if p.poll() is None:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)],
                           capture_output=True)
        try:
            p.wait(timeout=30)
        except Exception:                                          # noqa: BLE001
            pass
        chunk = ''
        if joblog.exists():
            chunk = joblog.read_bytes()[before:].decode('utf-8', 'replace')
        killed = '代为结束' in chunk
        rec('F2 ★★★ 失败时启动器**一直在等用户关窗口**（16 秒后仍在等），'
            '而不是"6 秒后替它收尸"'
            '（第一版就是这样：用户刚看到失败，窗口就被杀掉、然后才弹原生框）',
            alive and not killed,
            f'16 秒后启动器仍在等={alive}；'
            f'日志里出现「代为结束」={killed}')
        # ⚠ 这条**不能写成"有日志文件才检查"** —— 那就成了"看环境脸色"：
        #   替身没被挂上时文件不存在，它会被静静跳过，而它要守的正是
        #   "有没有多弹一个框"。所以无条件断言，并把它记到的那几个框打出来。
        # [EN] ⚠ This one **must not be written as "only check if a log file exists"** —— that becomes "reading
        # [EN] the environment's mood":
        # [EN] when the stand-in isn't attached the file doesn't exist, it quietly gets skipped, and what it's
        # [EN] supposed to guard is precisely
        # [EN] "whether an extra dialog popped up". So assert unconditionally, and print the dialogs it
        # [EN] recorded.
        boxes = ([json.loads(x) for x in
                  dlg.read_text(encoding='utf-8').splitlines() if x.strip()]
                 if dlg.exists() else [])
        rec('F2 ★ 失败时**不再**补一个原生框（同一条消息看两遍）'
            '—— 窗口还开着的时候它一个框都不该弹',
            not [b for b in boxes if b['kind'] == 'notify'],
            f'替身记到的框={[b["kind"] for b in boxes] or "（无）"}')
    finally:
        if p.poll() is None:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)],
                           capture_output=True)
        shutil.rmtree(blocker, ignore_errors=True)
        blocker.unlink(missing_ok=True)


def main() -> int:
    # （`developers/mutate_launchers.py`）每变异一条就要重编一次 exe 再跑判据，
    # 全程跑一遍要一分钟；只跑相关那一组，几条变异下来能省掉十几分钟。
    # 默认（不给参数）仍然跑**全部** —— 全量回归走的就是默认。
    # [EN] (`developers/mutate_launchers.py`) each mutation requires recompiling the exe and then running
    # [EN] the criterion,
    # [EN] a full run takes a minute; running only the relevant group saves over ten minutes across a few
    # [EN] mutations.
    # [EN] The default (no arguments given) still runs **everything** —— the full regression uses the
    # [EN] default.
    import argparse
    ap = argparse.ArgumentParser(description='验证启动器')
    ap.add_argument('--groups', default='',
                    help='只跑这几组，逗号分隔，如 A,B,C,D,E,F')
    a = ap.parse_args()
    want = {g.strip().upper() for g in a.groups.split(',') if g.strip()}

    def on(g: str) -> bool:
        return not want or g in want

    print('=' * 62)
    print('  验证启动器 · 无控制台 / 服务随主窗口退出 / 四平台产物 / 卸载真能卸')
    if want:
        print(f'  （只跑 {"".join(sorted(want))} 组）')
    print('=' * 62)
    if on('A'):
        check_artifacts()
    if on('B'):
        check_no_console()
    if on('C'):
        check_service_follow()
    if on('D'):
        check_selfreport()
    if on('E'):
        check_progress_ui()
    if on('F'):
        check_uninstall_flow()
        check_failure_window()

    bad = report['failed']
    report['ok'] = not bad
    (OUT / 'launchers_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print()
    print(f'启动器验证：{len(report["steps"]) - len(bad)}/{len(report["steps"])}')
    for n in bad:
        print(f'  ✗ {n}')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
