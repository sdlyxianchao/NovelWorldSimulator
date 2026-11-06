# -*- coding: utf-8 -*-
"""启动器的**进度窗**：把 `launchers/` 编出来的 setup / uninstall 要跑的活
显示出来（否则去掉控制台之后，装依赖那 1-3 分钟就是一片死寂）。

为什么是 Python + tkinter，而不是让 Go 自己画窗口
--------------------------------------------------
Go 那边要解决的是**"起得干净"**（交叉编译、Windows 上不带控制台）；
"把子进程的输出实时滚进一个窗口"这件事在 Go 里得自己调 Win32 / Cocoa / X11
三套 API。而本项目本来就要 Python，tkinter 又是**标准库** ——
于是分工是：**Go 负责没有窗口，Python 负责看得见**。

怎么被调用
----------
    <python> tools/launcher_progress.py --job <spec.json> --result <result.json>

`<python>` 用**系统** Python（此时工程的 `.venv` 可能还没建出来）。
`spec.json` 由 Go 写好（含标题 / 说明 / 一串步骤），本脚本把结果写进
`result.json`，Go 读它决定下一步。

★ 三条不许省的规矩
------------------
1. **没有图形环境也必须能干活。** 写 `{"gui": false}` 就退出、**一步都不跑**，
   由 Go 退回"静默执行 + 原生消息框"。Linux 上没装 `python3-tk`、
   或者 SSH 里没有 DISPLAY，都属于这一类 —— **功能不能依赖于有没有 GUI**。
2. **每一步的输出都另外落一份日志文件**（`spec["log"]`）。窗口关掉了、
   或者窗口根本没起来，日志还在，出问题能查。
3. **窗口出现的那一刻就要先写一个"我在跑"的结果文件。** 否则窗口跑到一半
   崩了，Go 看到"没有结果文件"，会以为"GUI 压根不可用" —— 那它就重跑一遍。
   步骤虽然幂等（建 venv / 装依赖 / prepare 都可以重复跑），但白等几分钟
   总归是浪费；写个 `running: true` 让 Go 能说清"是它崩了，不是我该重跑"。
4. **窗口关掉之后要再落一份 `closed: true`。** Go 靠它把"用户还开着窗口在看
   失败日志"（不能打扰）和"窗口已经没了、进程却卡在退出上"（该替它收尸）
   分开。少了它，Go 只能拿"等了多久"当判据 —— 那会把用户正在读的窗口杀掉。

用法（正常不用手敲，由 setup.exe / uninstall.exe 调起）
    .venv/Scripts/python.exe tools/launcher_progress.py --job x.json

English:
The launcher's **progress window**: shows the work that setup / uninstall built from
`launchers/` needs to run
(otherwise, after removing the console, the 1-3 minutes of installing deps is dead silence).
Why Python + tkinter, instead of letting Go draw the window itself
--------------------------------------------------
What Go needs to solve is **"starting cleanly"** (cross-compilation, no console on Windows);
"scroll the child process's output into a window in real time" in Go would require calling Win32
/ Cocoa / X11
three separate APIs. And this project already needs Python, and tkinter is a **standard
library** —
so the division of labor is: **Go handles having no window, Python handles being visible**.
How it's invoked
----------
    <python> tools/launcher_progress.py --job <spec.json> --result <result.json>
`<python>` uses the **system** Python (the project's `.venv` may not exist yet at this point).
`spec.json` is written by Go (contains title / description / a list of steps), and this script
writes the result into
`result.json`, which Go reads to decide the next step.
★ Three rules that must not be skipped
------------------
1. **It must be able to do the job even with no graphical environment.** Writing `{"gui": false}` and exiting, **not running a single step**,
   is how Go falls back to "silent execution + native message box". Not having `python3-tk` installed on Linux,
   or having no DISPLAY over SSH, both fall into this category — **functionality must not depend on having a GUI**.
2. **Each step's output is also written to a separate log file** (`spec["log"]`). If the window is closed,
   or the window never came up at all, the log is still there, so problems can be investigated.
3. **The moment the window appears, first write a "I'm running" result file.** Otherwise if the window crashes
   halfway through, Go sees "no result file" and thinks "the GUI isn't available at all" — so it reruns everything.
   Although the steps are idempotent (creating venv / installing deps / prepare can all be rerun), waiting a few minutes
   for nothing is still wasteful; writing a `running: true` lets Go say clearly "it crashed, not that I should rerun".
4. **After the window closes, write another `closed: true`.** Go relies on it to separate "the
user still has the window open reading
   the failure log" (must not disturb) from "the window is gone but the process is stuck on exit" (should reap on its behalf)
   apart. Without it, Go can only use "how long it waited" as the criterion — which would kill the window the user is reading.
Usage (normally you don't type this by hand; it's invoked by setup.exe / uninstall.exe)
    .venv/Scripts/python.exe tools/launcher_progress.py --job x.json
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

# ★★★ 输出**一律 UTF-8**（2026-10-25 "启动界面出现乱码"）：见
# `novelservices/service_ctl.py` 里同一段注释的完整推导（管道 ⇒ locale 编码 ⇒
# 与 Go 写的 UTF-8 行混编在同一份 `logs/launcher.log` 里）。
# ⚠ 只在**非控制台**时改。
# [EN] ★★★ Output is **always UTF-8** (2026-10-25 "mojibake in the splash"): full derivation in
# [EN] `novelservices/service_ctl.py` (pipe => locale encoding => mixed with the Go-written UTF-8
# [EN] lines in one `logs/launcher.log`). ⚠ Only when **not** a console.
if not sys.stdout.isatty():
    for _st in (sys.stdout, sys.stderr):
        try:
            _st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        del _st
    except NameError:
        pass

#: 成功后窗口自己关掉前停留几秒（让用户看得到"完成"）。
# [EN] : After success, stay a few seconds before closing the window (so the user can see "done").
AUTO_CLOSE_SECONDS = 3.0
#: 日志区最多留多少行（装依赖会刷很多，别让一个窗口吃几百 MB）。
# [EN] : Max lines to keep in the log area (installing deps produces a lot of output; don't let one
# [EN] window eat hundreds of MB).
LOG_MAX_LINES = 4000
#: 双语文案一律"中文 / English"，与旧脚本的约定一致（见 verify_script_bilingual）。
# [EN] : Bilingual text is always "Chinese / English", consistent with the old script's convention (see
# [EN] verify_script_bilingual).
T = {
    'waiting': '○ 等待中 / waiting',
    'running': '● 进行中… / running…',
    'done': '✓ 完成 / done',
    'fail': '✗ 失败 / failed',
    'close': '关闭 / Close',
    'finished': '全部完成 / All done',
    'failed': '没能完成，看下面日志 / Failed — see the log below',
    'failed_hint': '看完请点下面「关闭」 / click "Close" below when done',
    'closing': '全部完成，{s:.0f} 秒后自动关闭 / All done, closing in {s:.0f}s',
    'logpath': '日志 / log: {p}',
}


def write_result(path: str, **kw) -> None:
    """写结果文件。**原子写**：Go 那边可能在同时读，别让它读到半个 JSON。
        English:
    Write the result file. **Atomic write**: the Go side may be reading at the same time; don't let
    it read half a JSON.
    """
    p = Path(path)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(kw, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, p)


#: Windows：让子进程**不要**被分配控制台（见 `_no_window_kw`）。
# [EN] : Windows: make sure the child process does **not** get a console allocated (see
# [EN] `_no_window_kw`).
def _no_window_kw() -> dict:
    """父进程没有控制台时，必须显式告诉 Windows"别给子进程建控制台"。

    ★ 2026-10-10 实测（`developers/_probe_console_windows.py`，直接枚举桌面上
      **可见的**顶层控制台窗口）：
        · 父=pythonw（自己没有控制台）+ 子=python.exe **不带标志** → **多出 1 个窗口** ★
        · 父=pythonw + 子=python.exe **带 CREATE_NO_WINDOW**          → 0 个窗口 ✓
      也就是说"父进程没有控制台"**不会**自动传给子进程 —— 子进程会被重新分配一个
      并且**显示出来**。本脚本是被 `setup.exe` / `uninstall.exe` 用 pythonw 拉起的
      （顶层已经没有控制台了），所以这里起的 pip / prepare **必须**带上这个标志，
      否则用户会在装依赖的那几分钟里看着一个黑窗，正是这次要消灭的东西。
      （在终端里手动跑本脚本时无副作用：输出照样走管道。）
    
        English:
    When the parent process has no console, it must explicitly tell Windows "don't create a console
    for the child process".
        ★ 2026-10-10 measured (`developers/_probe_console_windows.py`, directly enumerating on the desktop
          **visible** top-level console window):
            · parent=pythonw (itself has no console) + child=python.exe **without the flag** → **1 extra window** ★
            · parent=pythonw + child=python.exe **with CREATE_NO_WINDOW** → 0 windows ✓
          In other words, "the parent process has no console" is **not** automatically inherited by the child process — the child process gets a new one assigned
          and **shown**. This script is launched by `setup.exe` / `uninstall.exe` via pythonw
          (there is no console at the top level anymore), so the pip / prepare started here **must** carry this flag,
          otherwise the user stares at a black window for the several minutes it takes to install dependencies, which is exactly what this change is meant to eliminate.
          (No side effects when running this script manually in a terminal: output still goes through the pipe.)
    """
    if os.name != 'nt':
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {'creationflags': 0x08000000, 'startupinfo': si}


def run_job(spec: dict, q: 'queue.Queue', logf) -> None:
    """在**后台线程**里按顺序跑所有步骤，把进展丢进队列给界面。

    ★ 为什么不能在主线程跑：主线程要 `mainloop()` 刷界面。任何一个步骤
      （pip install 可以几分钟）同步跑在主线程里，窗口就会**假死** ——
      而"进度窗卡住不动"比"没有进度窗"更让人以为程序坏了。
    
        English:
    Run all steps in order in a **background thread**, and push progress into a queue for the UI.
        ★ Why it cannot run on the main thread: the main thread must run `mainloop()` to refresh the UI. If any step
          (pip install can take minutes) runs synchronously on the main thread, the window will **freeze** —
          and "the progress window is stuck" makes people think the program is broken even more than "no progress window" does.
    """
    env = dict(os.environ)
    # 子进程的输出统一 UTF-8：这台机器默认是 GBK，中文日志混编码会变乱码。
    # [EN] Child process output is uniformly UTF-8: this machine defaults to GBK, mixed encodings turn
    # [EN] Chinese logs into mojibake.
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    # 本地回环别走代理（这台机器设了系统代理，pip 走回环源会莫名其妙地慢/失败）。
    # [EN] Don't route localhost through the proxy (this machine has a system proxy set; pip going through
    # [EN] a loopback source will be inexplicably slow/fail).
    for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
        env.pop(k, None)

    steps = spec.get('steps') or []
    for i, st in enumerate(steps):
        argv = st.get('argv') or []
        if not argv:
            q.put(('step', i, 'done'))
            continue
        q.put(('step', i, 'running'))
        q.put(('line', f'\n$ {" ".join(argv)}\n'))
        try:
            proc = subprocess.Popen(
                argv, cwd=st.get('cwd') or None, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding='utf-8',
                errors='replace', bufsize=1, **_no_window_kw())
        except OSError as e:
            q.put(('line', f'起不了子进程：{e!r}\n'))
            q.put(('done', 127, st.get('label', '')))
            return
        assert proc.stdout is not None
        for line in proc.stdout:
            q.put(('line', line))
            if logf is not None:
                try:
                    logf.write(line)
                    logf.flush()
                except Exception:                                  # noqa: BLE001
                    pass
        code = proc.wait()
        if code != 0:
            q.put(('step', i, 'fail'))
            q.put(('done', code, st.get('label', '')))
            return
        q.put(('step', i, 'done'))
    q.put(('done', 0, ''))


def build_ui(spec: dict, q: 'queue.Queue', result_path: str) -> int:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    # 标题是 `bi()` 拼的"中文\n英文"，而窗口标题里换行很难看 —— 摊平成一行。
    # [EN] The title is "Chinese\nEnglish" joined by `bi()`, and a newline in the window title looks bad —
    # [EN] flatten it to one line.
    root.title((spec.get('title') or 'Novel World AI Simulator')
               .replace('\n', '  /  '))
    root.geometry('640x480')
    root.minsize(540, 400)
    root.attributes('-topmost', True)

    steps = spec.get('steps') or []
    tk.Label(root, text=spec.get('title') or '', font=('', 12, 'bold'),
             anchor='w').pack(fill='x', padx=14, pady=(12, 2))
    tk.Label(root, text=spec.get('intro') or '', anchor='w', justify='left',
             wraplength=600).pack(fill='x', padx=14)

    step_frame = tk.Frame(root)
    step_frame.pack(fill='x', padx=14, pady=(10, 4))
    step_labels = []
    for st in steps:
        lb = tk.Label(step_frame, text=f'{T["waiting"]}  {st.get("label", "")}',
                      anchor='w', justify='left')
        lb.pack(fill='x')
        step_labels.append(lb)

    bar = ttk.Progressbar(root, mode='determinate',
                          maximum=max(1, len(steps)))
    bar.pack(fill='x', padx=14, pady=(6, 6))

    text_frame = tk.Frame(root)
    text_frame.pack(fill='both', expand=True, padx=14)
    scroll = tk.Scrollbar(text_frame)
    scroll.pack(side='right', fill='y')
    logbox = tk.Text(text_frame, height=10, wrap='none',
                     yscrollcommand=scroll.set, state='disabled')
    logbox.pack(side='left', fill='both', expand=True)
    scroll.config(command=logbox.yview)

    status = tk.Label(root, text='', anchor='w', justify='left', wraplength=600)
    status.pack(fill='x', padx=14, pady=(6, 0))
    btn = tk.Button(root, text=T['close'], state='disabled',
                    command=root.destroy)
    btn.pack(pady=(6, 12))

    state = {'done': False, 'closed': False, 'code': -1, 'failed': ''}

    def append(line: str) -> None:
        logbox.configure(state='normal')
        logbox.insert('end', line)
        # 行数上限：装依赖能刷上万行，全留着窗口会越来越卡。
        # [EN] Line cap: installing deps can produce tens of thousands of lines; keeping them all makes the
        # [EN] window slower and slower.
        n = int(logbox.index('end-1c').split('.')[0])
        if n > LOG_MAX_LINES:
            logbox.delete('1.0', f'{n - LOG_MAX_LINES}.0')
        logbox.see('end')
        logbox.configure(state='disabled')

    def pump() -> None:
        """主线程：把队列里攒的进展画出来（**只有主线程碰控件**）。
                English:
        Main thread: draw the progress accumulated in the queue (**only the main thread touches
        widgets**).
        """
        try:
            while True:
                kind, *rest = q.get_nowait()
                if kind == 'line':
                    append(rest[0])
                elif kind == 'step':
                    i, st = rest
                    icon = {'running': T['running'], 'done': T['done'],
                            'fail': T['fail']}.get(st, '')
                    step_labels[i].configure(
                        text=f'{icon}  {steps[i].get("label", "")}')
                    if st == 'done':
                        bar['value'] = i + 1
                elif kind == 'done':
                    code, failed = rest
                    state['done'] = True
                    state['code'] = code
                    state['failed'] = failed
                    bar['value'] = len(steps) if code == 0 else bar['value']
                    if code == 0:
                        status.configure(text=f'{T["finished"]}   （'
                                              f'{T["logpath"].format(p=spec.get("log", ""))}）')
                        btn.configure(state='normal')
                        # 成功后自己关掉：这是"双击一下就不用管"的操作。
                        # [EN] Auto-close on success: this is a "double-click and forget it" operation.
                        tick(int(AUTO_CLOSE_SECONDS) + 1)
                    else:
                        # ★ 失败时窗口**不自己关**：用户要看着日志区找原因。
                        #   启动器那边知道这件事（等 `closed` 落盘才收尸）——
                        #   两边靠 `closed` 这个字段对齐，谁也别猜"等了多久"。
                        # [EN] ★ On failure the window does **not** close itself: the user needs to look at the log area to
                        # [EN] find the cause.
                        # [EN] The launcher side knows about this (it only reaps once `closed` is written to disk) —
                        # [EN] Both sides align on the `closed` field; nobody should guess "how long it waited".
                        status.configure(
                            text=f'{T["failed"]}  ← {failed}\n'
                                 f'{T["failed_hint"]}\n'
                                 f'{T["logpath"].format(p=spec.get("log", ""))}')
                        btn.configure(state='normal')
                        root.focus_force()
                    write_result(result_path, gui=True, code=code,
                                 failed_step=failed, log=spec.get('log', ''),
                                 running=False, closed=False)
        except queue.Empty:
            pass
        if not state['closed']:
            root.after(80, pump)

    def tick(n: int) -> None:
        if state['closed']:
            return
        if n <= 0:
            root.destroy()
            return
        status.configure(text=f'{T["finished"]}   '
                              f'（{T["closing"].format(s=n - 1)}）')
        root.after(1000, tick, n - 1)

    # 「我在跑」先落盘：万一窗口/进程中途没了，Go 能分清"它崩了"和"它压根没起来"。
    # [EN] "I'm running" is written to disk first: if the window/process dies mid-way, Go can distinguish
    # [EN] "it crashed" from "it never even started".
    write_result(result_path, gui=True, code=-1, failed_step='',
                 log=spec.get('log', ''), running=True, closed=False)

    logf = None
    lp = spec.get('log') or ''
    if lp:
        try:
            Path(lp).parent.mkdir(parents=True, exist_ok=True)
            logf = open(lp, 'a', encoding='utf-8', errors='replace')
        except Exception:                                          # noqa: BLE001
            logf = None

    q = q  # 队列由调用方建好（便于"没有 GUI 时"另作他用）
    # [EN] The queue is created by the caller (so it can be reused when "there's no GUI")
    threading.Thread(target=run_job, args=(spec, q, logf), daemon=True).start()
    root.after(80, pump)
    root.mainloop()
    state['closed'] = True
    if logf is not None:
        try:
            logf.close()
        except Exception:                                          # noqa: BLE001
            pass
    # ★★ 「窗口已经关掉了」必须**落盘**（在 `_hard_exit` 之前）。
    # [EN] ★★ "Window has been closed" must be **written to disk** (before `_hard_exit`).
    #
    #   它是启动器唯一能分清下面这两件事的依据：
    #     · `closed=False` ⇒ 窗口还开着，用户正在看日志 ⇒ **不许**替它收尸；
    #     · `closed=True`  ⇒ 屏幕上已经什么都没有了，进程却还没退
    #                        （这台机器上 Tk 跑过之后 `ExitProcess` 会卡）⇒ 该收尸。
    #   没有这一条，启动器就只能拿"等了多久"当判据 —— 而那个判据会在用户
    #   正在读失败日志的时候把窗口杀掉（第一版就是这么干的，用户报的截图后面
    #   紧跟着两行「进度窗写完结论后仍未退出 ⇒ 代为结束」）。
    # [EN] It is the only basis on which the launcher can distinguish the following two cases:
    # [EN] · `closed=False` ⇒ window is still open, user is looking at the log ⇒ **must not** reap it;
    # [EN] · `closed=True`  ⇒ nothing is on screen anymore, but the process hasn't exited
    # [EN] (on this machine, after Tk has run, `ExitProcess` hangs) ⇒ should reap.
    # [EN] Without this, the launcher could only use "how long it waited" as the criterion — and that
    # [EN] criterion would
    # [EN] kill the window while the user is reading the failure log (that's what v1 did; the screenshot
    # [EN] the user reported
    # [EN] was immediately followed by two lines "progress window wrote its conclusion but still hasn't
    # [EN] exited ⇒ kill on its behalf").
    try:
        write_result(result_path, gui=True, code=state['code'],
                     failed_step=state['failed'], log=spec.get('log', ''),
                     running=False, closed=True)
    except Exception:                                              # noqa: BLE001
        pass
    return 0 if state['done'] else 3


def _hard_exit(code: int) -> None:
    """**硬退出**。这一步不是可选的 —— 见下面的实测。

    ★★★ 2026-10-10 实测（这台 Windows 机器，最小复现两行 tkinter）：

      · `os._exit(code)` —— **会挂住，进程永远不消失**。
        它走 CRT 的 `_exit` → `ExitProcess`，而 `ExitProcess` 要逐个跑已加载 DLL 的
        `DllMain(DLL_PROCESS_DETACH)`；这台机器上**只要 Tk 的窗口真的显示过**，
        那一步就死在那儿。反例：窗口建完立刻 `destroy()`（从没显示过）时，
        `os._exit` 反而正常退出 —— 所以"跑过界面"才是触发条件。

      · `TerminateProcess(GetCurrentProcess(), code)` —— **能退**，退出码精确。
        它不跑 DLL 卸载，绕开了那个死锁。

      ⚠⚠ 用 ctypes 调它**必须显式给类型**：`GetCurrentProcess()` 返回的是 64 位
        伪句柄，ctypes 默认按 `c_int` 收会**被截断成无效句柄**，于是
        `TerminateProcess` 静默失败（返回 0）—— 看起来就像"它也没用"。
        第一版就是这么写的，白绕了一整圈。

      后果如果不修：`setup.exe` / `uninstall.exe` 会**永远等**这个子进程
      （判据第一次跑就是 300 秒超时），用户眼里就是"装到一半卡死"。
      ⇒ 跟本项目 `util/flet_shutdown.py` 是同一类药，只是那副药不够：那边用
        `os._exit` 对付"线程 join"，这边要对付"`ExitProcess` 的 DLL 卸载"。
        结果文件是在**这之前**用原子写落好的，所以中途硬退不丢结果。
    
        English:
    **Hard exit**. This step is not optional — see the empirical test below.
        ★★★ Measured on 2026-10-10 (this Windows machine, minimal repro with two lines of tkinter):
          · `os._exit(code)` — **hangs, the process never disappears**.
            It goes through the CRT's `_exit` → `ExitProcess`, and `ExitProcess` runs `DllMain(DLL_PROCESS_DETACH)` for each loaded DLL
            one by one; on this machine, **as long as a Tk window has actually been shown**,
            that step deadlocks right there. Counter-example: when the window is `destroy()`ed immediately after creation (never shown),
            `os._exit` exits normally instead — so "having run the UI" is the triggering condition.
          · `TerminateProcess(GetCurrentProcess(), code)` — **can exit**, with an exact exit code.
            It does not run DLL unload, bypassing that deadlock.
          ⚠⚠ Calling it via ctypes **requires explicitly specifying the types**: `GetCurrentProcess()` returns a 64-bit
            pseudo-handle, and ctypes receiving it as `c_int` by default **truncates it into an invalid handle**, so
            `TerminateProcess` fails silently (returns 0) — it looks like "it doesn't work either".
            The first version was written that way and wasted a whole round for nothing.
          Consequence if not fixed: `setup.exe` / `uninstall.exe` will **wait forever** for this child process
          (the criterion timed out at 300 seconds on the very first run), which to the user looks like "it hung halfway through installation".
          ⇒ It is the same kind of medicine as this project's `util/flet_shutdown.py`, except that medicine is not enough: there
            `os._exit` is used against "thread join", while here it is against "`ExitProcess`'s DLL unload".
            The result file is committed **before** this point using atomic write, so a hard exit midway does not lose results.
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:                                              # noqa: BLE001
        pass
    if os.name == 'nt':
        try:
            import ctypes
            k = ctypes.WinDLL('kernel32', use_last_error=True)
            k.GetCurrentProcess.restype = ctypes.c_void_p
            k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            k.TerminateProcess(k.GetCurrentProcess(),
                               ctypes.c_uint(int(code) & 0xFFFFFFFF))
            # 真走到下一行说明连 TerminateProcess 都失败了（正常不会）⇒ 兜底。
            # [EN] Actually reaching the next line means even TerminateProcess failed (normally it won't) ⇒ last
            # [EN] resort.
        except Exception:                                          # noqa: BLE001
            pass
    os._exit(code)


def main() -> int:
    ap = argparse.ArgumentParser(description='启动器的进度窗')
    ap.add_argument('--job', required=True)
    ap.add_argument('--result', required=True)
    a = ap.parse_args()

    spec = json.loads(Path(a.job).read_text(encoding='utf-8'))

    # 判据用的钩子：强制走"没有窗口"那条路。
    # ★ 为什么需要一个钩子：那条降级路（Linux 没装 python3-tk、SSH 里没有 DISPLAY）
    #   在开发机上**永远走不到**，于是"没窗口也能把活干完"这句话就没人验证过。
    #   这正是本项目最忌讳的"判据看着绿、其实那一支压根没跑"。
    # [EN] Hook used for the criterion: force the "no window" path.
    # [EN] ★ Why a hook is needed: that degraded path (Linux without python3-tk, no DISPLAY over SSH)
    # [EN] is **never reachable** on the dev machine, so the claim "it can finish the job with no window"
    # [EN] has never been verified by anyone.
    # [EN] This is exactly what this project dreads most: "the criterion looks green, but that branch never
    # [EN] even ran".
    if os.environ.get('NWS_TEST_NO_GUI'):
        write_result(a.result, gui=False, code=-1, failed_step='',
                     log=spec.get('log', ''), running=False, closed=True,
                     err='NWS_TEST_NO_GUI=1（判据强制）')
        _hard_exit(0)

    try:
        import tkinter  # noqa: F401
    except Exception as e:                                         # noqa: BLE001
        write_result(a.result, gui=False, code=-1, failed_step='',
                     log=spec.get('log', ''), running=False, closed=True,
                     err=f'tkinter 不可用：{e!r}')
        _hard_exit(0)

    try:
        rc = build_ui(spec, queue.Queue(), a.result)
    except Exception as e:                                         # noqa: BLE001
        # 没有图形环境（SSH / 没有 DISPLAY），或者窗口建到一半炸了。
        # [EN] No graphical environment (SSH / no DISPLAY), or the window blew up halfway through creation.
        write_result(a.result, gui=False, code=-1, failed_step='',
                     log=spec.get('log', ''), running=False, closed=True,
                     err=f'打不开窗口：{e!r}')
        rc = 0
    # ⚠ 不能用 `return rc`：那样会走正常的解释器收尾，而实测**那一步会挂住**
    #   （见 `_hard_exit` 的注释）。必须硬退。
    # [EN] ⚠ Must not use `return rc`: that would go through normal interpreter shutdown, and in practice
    # [EN] **that step hangs**
    # [EN] (see the comment on `_hard_exit`). Must exit hard.
    _hard_exit(rc)


if __name__ == '__main__':
    sys.exit(main())
