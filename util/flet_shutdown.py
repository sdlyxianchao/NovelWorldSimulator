# -*- coding: utf-8 -*-
"""Flet 脚本公共收尾：**确保 Flet 客户端窗口被真正关掉**。

为什么需要它
------------
`ft.run()` 会另外拉起一个 `flet.exe` 客户端进程。脚本最后若直接 `os._exit(0)`，
Python 侧虽然退了，但**客户端会变成孤儿留在后台**，卡在启动加载页上
（画面就是一个一直转的 "Working..." 窗口）。跑几次验证就攒出一堆窗口。

正确收尾：先 `await page.window.destroy()` 让客户端自己退出，再 `os._exit()`
（用 `os._exit` 是为了跳过 Flet 后台线程的 join，否则脚本会挂住不退）。

★ 但 `destroy()` 有**一个很坑的性质**（2026-10-06 实测，见 `shutdown()` 的注释）：
它会**抛 `asyncio.CancelledError` 取消当前会话协程** —— 也就是说，
`await page.window.destroy()` **这句话之后的任何代码都不会执行**。
于是老写法「写报告 → `await shutdown(page)` → `exit_now(code)`」里的
**`exit_now` 从来没跑过**：所有验证脚本的**退出码恒为 0**（失败了也报 0，
靠退出码判成败的地方全是假绿），`kill_orphan_clients()` 也没跑（会剩僵尸窗口）。
现在把"设退出码"这件事收进 `shutdown(..., code=N)`，在回来之前就落实。

再兜一层：把「父进程 PID = 本脚本进程」的残留 flet 客户端一并收掉，
即使 `destroy()` 没起作用也不会再漏窗口。

English:
Common shutdown for Flet scripts: **ensure the Flet client window is actually closed**.
Why it is needed
------------
`ft.run()` launches a separate `flet.exe` client process. If the script ends with a direct
`os._exit(0)`,
the Python side exits, but **the client becomes an orphan left in the background**, stuck on the
startup loading page.
(The picture is a "Working..." window spinning forever.) A few verification runs pile up a bunch
of windows.
Correct shutdown: first `await page.window.destroy()` to let the client exit on its own, then
`os._exit()`.
(`os._exit` is used to skip joining Flet's background threads; otherwise the script would hang
and not exit.)
★ But `destroy()` has **a very nasty property** (measured 2026-10-06, see the comment in
`shutdown()`):
It will **throw `asyncio.CancelledError` to cancel the current session coroutine** -- that is,
**any code after the statement `await page.window.destroy()` will never execute**.
So in the old pattern "write report → `await shutdown(page)` → `exit_now(code)`",
**`exit_now` never ran**: all verification scripts had a **constant exit code of 0** (reporting
0 even on failure;
everything relying on exit code to judge success was falsely green), and `kill_orphan_clients()`
also didn't run (zombie windows would remain).
Now the matter of "setting the exit code" is folded into `shutdown(..., code=N)`, settled before
returning.
One more layer of fallback: also collect leftover flet clients whose "parent process PID = this
script's process".
Even if `destroy()` didn't take effect, no window will be missed.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from typing import Callable

_MY_PID = os.getpid()

#: 关窗之后**最多再给几秒**，到点无论如何都退（见 `arm_exit_watchdog`）。
#: 给得比"正常收尾要多久"宽：这个值只在**真的卡住**时才起作用，
#: 卡住时多等两秒没人察觉，而给太短有可能打断一次正当的收尾。
# [EN] : After closing the window, give **at most a few more seconds**; when the time is up, exit no
# [EN] matter what (see `arm_exit_watchdog`).
# [EN] : Give it more leeway than "how long a normal shutdown takes": this value only takes effect when
# [EN] it's **really stuck**.
# [EN] : When stuck, waiting two extra seconds goes unnoticed, whereas giving too little may interrupt
# [EN] a legitimate shutdown.
EXIT_GRACE_SECONDS = 5.0


def arm_exit_watchdog(delay: float = EXIT_GRACE_SECONDS,
                      exit_fn: Callable[[int], None] | None = None
                      ) -> threading.Thread:
    """窗口关掉之后：**最多再等 `delay` 秒，到点强制结束进程**。

    为什么必须有这一道
    ------------------
    `asyncio.to_thread(...)` 走的是**默认线程池**（`ThreadPoolExecutor`）。
    它的工作线程**是非守护（non-daemon）的**，而且解释器退出时会
    `join` 它们（`concurrent.futures.thread._python_exit`）。
    也就是说：**只要有一个后台调用还没回来，`python.exe` 就一直不退出。**

    用户看到的现象不是"程序没关"，而是**那个命令行窗口留着、关不掉**
    （2026-10-10 用户报的第 4 条：「我退出程序之后 总是有一个控制台窗口在
    而且不退出」）—— 因为旧 `start.bat` 那句
    `"%VENV_PY%" "%APP%"` **还没返回**，cmd 就一直等在那里。

    最典型的一个卡点：「自动拉起创作服务」那次
    `BR.start_service(timeout=600)`（`gui/app_flet.py` 的
    `_maybe_autostart_service`）。首次启动要下约 470MB 的 embedding 模型；
    端口被别的程序占着时更是一直等到超时 —— **十分钟**里用户以为程序关不掉。

    做法：起一个 **daemon 线程**，睡 `delay` 秒后 `os._exit(0)`。
    正常退出时它跟着进程一起消失（daemon 不进 join，不会反过来拖住退出）；
    异常卡住时它就是最后那道闸。

    ⚠ `os._exit` 而不是 `sys.exit`：后者只是**抛异常**，而主线程此刻正卡在
      "等线程池 join" 里 —— 那个异常根本没人接。`os._exit` 直接结束进程，
      正是这里要的效果。

    ⚠ **不传 `exit_fn` 时它会真的杀掉当前进程** —— 正常调用点（关窗 / 归去）
      就是想要的；测试里请传一个假的 `exit_fn`。

    返回起出来的那个线程（daemon），方便调用方/判据检查它确实是 daemon。
    
        English:
    After the window is closed: **wait at most `delay` more seconds, then force-terminate the
    process at the deadline**.
        Why this safeguard is required
        ------------------
        `asyncio.to_thread(...)` uses the **default thread pool** (`ThreadPoolExecutor`).
        Its worker threads are **non-daemon**, and at interpreter exit the interpreter will
        `join` them (`concurrent.futures.thread._python_exit`).
        That is: **as long as one background call hasn't returned, `python.exe` will not exit.**
        What the user sees is not "the program didn't close", but **that command-line window staying there, unable to be closed**.
        (User-reported item 4 on 2026-10-10: "After I quit the program there's always a console window that
        won't exit") -- because the old `start.bat` line
        `"%VENV_PY%" "%APP%"` **hadn't returned yet**, so cmd just kept waiting there.
        The most typical blockage: the "auto-start creation service" run,
        `BR.start_service(timeout=600)` (in `gui/app_flet.py`'s
        `_maybe_autostart_service`). The first launch needs to download about 470MB of embedding model;
        when the port is occupied by another program, it waits all the way to the timeout -- **for ten minutes** the user thinks the program can't be closed.
        Approach: start a **daemon thread** that sleeps for `delay` seconds and then calls `os._exit(0)`.
        On a normal exit it disappears along with the process (daemons don't get joined, so they won't drag out the exit the other way);
        when stuck abnormally, it is the final gate.
        ⚠ `os._exit` rather than `sys.exit`: the latter merely **throws an exception**, while the main thread is currently stuck in
          "waiting for the thread pool to join" -- that exception has no one to catch it. `os._exit` directly terminates the process,
          which is exactly the effect wanted here.
        ⚠ **When `exit_fn` is not passed, it will really kill the current process** -- the normal call sites (window close / return)
          are what's wanted; in tests please pass a fake `exit_fn`.
        Return the thread that was started (daemon), so the caller / assertion can check that it really is a daemon.
    """
    def _fire() -> None:
        _flush()
        try:
            (exit_fn or os._exit)(0)
        except Exception:                       # noqa: BLE001 —— 走到这儿只能硬退
        # [EN] noqa: BLE001 -- once we reach here, we can only force-exit
            os._exit(0)

    t = threading.Timer(max(0.1, float(delay)), _fire)
    # ★★ 必须是 daemon：否则这个"看门狗"自己就成了新的、会让解释器等下去的
    #    非守护线程 —— 那就成了"为了修关不掉而加了一个关不掉的东西"。
    # [EN] ★★ Must be a daemon: otherwise this "watchdog" itself becomes a new thread that makes the
    # [EN] interpreter wait.
    # [EN] A non-daemon thread -- that would be "adding something that can't be shut down in order to fix
    # [EN] something that can't be shut down".
    t.daemon = True
    t.start()
    return t


def kill_orphan_clients() -> None:
    """收掉「父进程是本脚本」的 flet 客户端进程（兜底，正常情况下没有）。
        English:
    Collect flet client processes whose "parent process is this script" (fallback; normally there
    are none).
    """
    if sys.platform != 'win32':
        return
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='flet.exe'\" | "
            "Where-Object { $_.ParentProcessId -eq " + str(_MY_PID) + " } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
            "-ErrorAction SilentlyContinue }"
        )
        subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, timeout=20)
    except Exception:
        pass


def _win_list_procs() -> list[dict]:
    """列 `flet.exe` / `python.exe` / `pythonw.exe` 的 `(pid, ppid, name)`（非 Windows 返回空）。

        English:
    List `(pid, ppid, name)` for `flet.exe` / `python.exe` / `pythonw.exe` (empty off Windows).
    """
    if sys.platform != 'win32':
        return []
    ps = ("Get-CimInstance Win32_Process -Filter "
          "\"Name='flet.exe' OR Name='python.exe' OR Name='pythonw.exe'\" | "
          "ForEach-Object { \"$($_.ProcessId)`t$($_.ParentProcessId)`t$($_.Name)\" }")
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=25)
    except Exception:                      # noqa: BLE001
        return []
    out: list[dict] = []
    for ln in (r.stdout or '').splitlines():
        parts = ln.strip().split('\t')
        if len(parts) != 3:
            continue
        try:
            out.append({'pid': int(parts[0]), 'ppid': int(parts[1]),
                        'name': parts[2].strip().lower()})
        except ValueError:
            continue
    return out


def kill_pid_tree(pid: int) -> bool:
    """**连子进程一起**结束 `pid`（Windows 用 `taskkill /T /F`）。

    为什么需要它
    ------------
    `subprocess.run(..., timeout=N)` 超时时**只杀直接子进程**。而判据脚本
    （`python tools/verify_x.py`）自己会再拉起一个 `flet.exe` 客户端 ——
    那是**孙进程**，父进程一死它就成孤儿，卡在「Working...」加载页上永不退出。
    2026-10-17 用户报的「有大量的 flet working 窗口没退出」就是它：当时桌面上
    同时挂着两个跑了一小时半的全量回归，各自卡在一支真机判据上。

        English:
    **Terminate `pid` together with its children** (Windows: `taskkill /T /F`).
        Why it is needed
        ------------
        `subprocess.run(..., timeout=N)` only kills the **direct child** on timeout. The criterion
        script (`python tools/verify_x.py`) itself launches an `flet.exe` client -- that is a
        **grandchild**; once its parent dies it becomes an orphan stuck forever on the
        "Working..." loading page. The user's report on 2026-10-17 ("a pile of flet working windows
        that never exit") was exactly this: two full regressions had been running for 1.5 hours,
        each stuck on one real-machine criterion.
    """
    if sys.platform != 'win32':
        try:
            os.kill(pid, 9)                # noqa: S113 —— 兜底，非 Windows 只杀自己
        except Exception:                  # noqa: BLE001
            return False
        return True
    try:
        r = subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=30)
    except Exception:                      # noqa: BLE001
        return False
    # taskkill 的退出码：0 成功；128 之类的"进程不存在"也算处理好了
    return r.returncode == 0 or 'not found' in (r.stdout + r.stderr).lower()


def _ancestor_pids(procs: list[dict]) -> set[int]:
    """顺着 `ppid` 往上走，返回**本进程的所有祖先进程**的 pid。

    ★★★ 为什么要这一条（2026-10-17 实测踩到）：看门狗在子进程里跑清理时，
    若判定条件写错（比如漏了 `name == 'flet.exe'`），会把**调用它的那个进程
    连同它的父链**一起杀掉 —— 反例法当场把自己杀了，日志停在半路、看不出原因。
    清理逻辑再怎么写错，也不该杀"正在跑我的那条链"。

        English:
    Walk `ppid` upwards and return the pids of **all ancestors of this process**.
        ★★★ Why (measured 2026-10-17): when the watchdog runs the sweep inside a child process, a
        wrong predicate (e.g. missing `name == 'flet.exe'`) kills **the process that invoked it and
        its whole parent chain** -- the counterexample harness killed itself, the log stopped midway
        with no clue. No matter how the sweep's predicate is written wrong, it must not kill "the
        chain that is running me".
    """
    by_pid = {p['pid']: p for p in procs}
    out: set[int] = set()
    cur = by_pid.get(_MY_PID, {}).get('ppid') or os.getppid()
    for _ in range(64):                    # 防环
        if not cur or cur in out:
            break
        out.add(cur)
        cur = by_pid.get(cur, {}).get('ppid') or 0
    return out


def sweep_orphan_clients(*, clients: list[dict] | None = None,
                         killer=None, dry: bool = False,
                         ancestors: set[int] | None = None) -> list[int]:
    """收掉**父进程已死**的 `flet.exe`（判据被超时杀掉后留下的「Working...」窗口）。

    ★ 只认"父进程已经不在"的那批。用户自己的程序（`pythonw.exe` 还活着）拉起的
      客户端**一个都不许碰** —— 这条是它敢在回归开始/结束时自动跑的前提。
    ★★ **自己的祖先进程永不杀**（`_ancestor_pids`）：清理逻辑写错时，
      至少不会把"正在跑它的那条链"一起带走。
    ★ `clients` / `killer` / `ancestors` 可注入：判据拿假进程表就能验证
      "该杀的杀了、不该杀的一个没动"，不必真去起一个 `flet.exe`。

        English:
    Collect `flet.exe` clients **whose parent is already dead** (the "Working..." windows left
    behind after a criterion is killed by the timeout).
        ★ Only the "parent is gone" batch. Clients launched by the user's own app (its
          `pythonw.exe` is still alive) **must not be touched** -- that is the precondition for
          running this automatically at the start/end of a regression.
        ★★ **Never kill our own ancestors** (`_ancestor_pids`): when the predicate is written wrong,
          at least it won't take away "the chain that is running it".
        ★ `clients` / `killer` / `ancestors` are injectable: a criterion can verify "killed what it
          should, left alone what it shouldn't" with a fake process table, without spawning a real
          `flet.exe`.
    """
    procs = _win_list_procs() if clients is None else clients
    if not procs:
        return []
    alive = {p['pid'] for p in procs}
    keep = _ancestor_pids(procs) if ancestors is None else set(ancestors)
    victims = [p['pid'] for p in procs
               if p['name'] == 'flet.exe' and p['ppid'] not in alive
               and p['pid'] not in keep]
    if dry:
        return victims
    kill = killer or kill_pid_tree
    done: list[int] = []
    for pid in victims:
        try:
            if kill(pid):
                done.append(pid)
        except Exception:                  # noqa: BLE001
            pass
    return done


def arm_lifetime_watchdog(seconds: float, *, code: int = 3) -> threading.Thread:
    """整支脚本的**硬超时**：到点关掉自己的客户端并 `os._exit(code)`。

    为什么与 `arm_exit_watchdog` 分开
    --------------------------------
    `arm_exit_watchdog` 管的是"**窗口已经关了**、但后台线程还拖着不退"（宽限 5 秒）；
    这一道管的是"**窗口还开着、脚本卡在某个 await 上永远不动**"（几分钟）。
    后者才是用户看到的「一堆 Working 窗口」：脚本没死，窗口就一直开着。

    ★ 由 **`tools/verify_ui_common` 在 import 时**按环境变量 `NWS_VERIFY_WATCHDOG`
      自动装上 —— 90 支真机判据都 import 它，不必逐支改。
    ★ 也是 daemon 线程（理由同 `arm_exit_watchdog`）。

        English:
    **Hard timeout for the whole script**: when it fires, close this script's clients and
    `os._exit(code)`.
        Why it is separate from `arm_exit_watchdog`
        --------------------------------
        `arm_exit_watchdog` covers "the **window is already closed** but background threads still
        drag out the exit" (5s grace); this one covers "**the window is still open and the script is
        stuck on some await forever**" (minutes). The latter is what the user saw as a pile of
        Working windows: the script is alive, so the window stays.
        ★ **`tools/verify_ui_common` arms it at import** from `NWS_VERIFY_WATCHDOG` -- 90
          real-machine criteria import that module, no per-script edits needed.
        ★ Also a daemon thread (same rationale as `arm_exit_watchdog`).
    """
    def _fire() -> None:
        try:
            print(f'\n[看门狗] 这支判据已跑满 {seconds:.0f}s 仍未收尾 '
                  f'⇒ 强制结束（{code}），避免留下 Flet 窗口。', flush=True)
        except Exception:                  # noqa: BLE001
            pass
        try:
            kill_orphan_clients()
            sweep_orphan_clients()
        except Exception:                  # noqa: BLE001
            pass
        _flush()
        os._exit(code)

    t = threading.Timer(max(1.0, float(seconds)), _fire)
    t.daemon = True
    t.start()
    return t


async def shutdown(page, *, delay: float = 0.6, code: int | None = None) -> None:
    """收尾：关掉 Flet 窗口；（可选）按 `code` 退出。**必须在 `exit_now()` 之前 await。**

    ★★ **为什么退出码要传进来、而不是写在后面**（2026-10-06 实测）：

    实测（`page.window.destroy()` 逐步打点）：

        1 before destroy
        2 destroy raised CancelledError      ← 就这里
        （后面的 await 一律不再执行）

    `page.window.destroy()` 会**取消当前会话协程**，而且抛的是
    **`asyncio.CancelledError`（`BaseException`，`except Exception` 抓不住）**。
    所以"写报告 → `await shutdown(page)` → `exit_now(code)`"这个三件套里，
    **`exit_now` 是死代码**：34 个验证脚本的退出码因此**恒为 0** ——
    脚本明明打印了 `ok: false`，退出码却是 0，`&&` 串起来的下游全被糊过去。
    同一个原因还让 `kill_orphan_clients()` 也被跳过（残留 flet 僵尸窗口）。

    所以现在的规矩是：**要设退出码就传给 `shutdown(code=...)`** ——
    它在"被取消"之前同步退掉，退不掉才怪。

    `delay` 参数保留只为兼容老调用点（`destroy()` 之后等不了，等也没意义）。
    
        English:
    Shutdown: close the Flet window; (optional) exit according to `code`. **Must be awaited before
    `exit_now()`.**
        ★★ **Why the exit code must be passed in, not written afterward** (measured 2026-10-06):
        Measured (stepping through `page.window.destroy()` with logging):
            1 before destroy
            2 destroy raised CancelledError      ← right here
            (any subsequent await is never executed)
        `page.window.destroy()` will **cancel the current session coroutine**, and what it throws is
        **`asyncio.CancelledError` (`BaseException`, `except Exception` cannot catch it)**.
        So in the trio of "write report → `await shutdown(page)` → `exit_now(code)`",
        **`exit_now` is dead code**: the exit codes of 34 verification scripts are therefore **always 0** ——
        the script clearly printed `ok: false`, yet the exit code is 0, and everything downstream chained with `&&` gets glossed over.
        The same cause also makes `kill_orphan_clients()` get skipped (leftover flet zombie windows).
        So the current rule is: **to set an exit code, pass it to `shutdown(code=...)`** ——
        it exits synchronously before "being cancelled"; only if it fails to exit is that a problem.
        The `delay` parameter is kept only for compatibility with old call sites (after `destroy()` you can't wait, and waiting is meaningless anyway).
    """
    try:
        await page.window.destroy()
    except BaseException:               # ⚠ CancelledError 是 BaseException，必须这样抓
    # [EN] ⚠ CancelledError is a BaseException and must be caught this way.
        pass
    # ↓↓ 从上面那句开始，协程随时可能已被取消；**这里必须全是同步代码** ↓↓
    kill_orphan_clients()               # 兜底：destroy 没带走客户端时再收一次
    # [EN] ↓↓ From the sentence above onward, the coroutine may have been cancelled at any time;
    # [EN] **everything here must be synchronous code** ↓↓
    # [EN] Fallback: if destroy didn't take the client away, collect it once more.
    if code is not None:
        _flush()
        os._exit(code)


def _flush() -> None:
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:                   # noqa: BLE001
        pass


def exit_now(code: int = 0) -> None:
    """收尾退出。os._exit 跳过后台线程 join，避免脚本挂住。

    ⚠ **写在 `await shutdown(page)` 后面等于没写**（见 `shutdown()` 的注释）——
    要设退出码请用 `await shutdown(page, code=N)`。
    
        English:
    Final exit. os._exit skips background thread join, to avoid the script hanging.
        ⚠ **Writing it after `await shutdown(page)` is as good as not writing it** (see the comment on `shutdown()`) ——
        To set an exit code, use `await shutdown(page, code=N)`.
    """
    kill_orphan_clients()
    _flush()
    os._exit(code)
