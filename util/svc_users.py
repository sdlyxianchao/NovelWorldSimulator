# -*- coding: utf-8 -*-
"""「谁在用创作服务」登记表 —— 多实例共享一组服务时的**收尸归属**。

为什么需要它
------------
三座外部创作服务都是**绑固定端口**的 HTTP 服务（MuMu 的 `APP_PORT` 写在它自己
的 `backend/.env`，另两家在主程序根 `.env`），端口只有一个 ⇒ **物理上只可能存在
一组服务**。实测过：第二个实例调 `novelservice.py start`，它先 `probe(port)`，
通了就只回一句「已经在运行，不重复启动」（0.1 秒），根本不会去拉第二组。

于是「同时开两个窗口」这件日常事只剩一个真问题：**谁来负责把服务收掉**。

原来那套（`launchers/flow.go:claimLock`，记 `logs/launcher.pid`）比的是
「文件里那个 pid 是不是我自己」：

    A 开 → 起服务；B 开 → 复用
    关 A → 文件里是 B ⇒ 不是我 ⇒ 不停                      ✓
    关 B → 文件里是我 ⇒ 停 ⇒ **A 还在用，服务当场没了**      ✗

它只防住了「先关的那个」，**没防住「后关的那个」** —— 而后者才是更常见的那一次
（人总是先关掉刚开的那个，回头继续用先前那个）。

这里的口径换成**引用计数**：表里每一项是一个**活着的主程序实例**，
「判空」= 一个活着的都没有 ⇒ 那时才真的停服务。

★ 判空**不依赖「撤销成功」**：判的是「登记文件里那个 pid 现在还活着吗」。
  实例被强杀 / 崩溃 / 断电时，`release()` 那一步根本跑不到，文件会残留 ——
  但 pid 已经死了，判活过不了 ⇒ 自动不算数。**僵尸登记是自愈的**，
  不需要任何额外的清理工序（清理只是让目录好看，见 `clear_dead()`）。
★ 每个实例写**自己的一个文件**（文件名就是 pid），不共用单个 JSON：
  两个实例同时启动时各写各的文件 ⇒ **不需要任何锁**，也没有写坏彼此的风险。
⚠ pid 被系统复用会让「判活」误判成活着 ⇒ 后果是**服务多留一会儿**
  （下次启动还更快），而不是「误停」（误停才会打断另一个正在写的实例）。
  这个方向的偏差是**刻意选的**：宁可留着，不可掐掉。

English:
Registry of "who is using the creation services" — **who gets to shut them down**
when several instances share one set of services.
Why it is needed
------------
All three external creation services are HTTP services **bound to a fixed port**
(MuMu's `APP_PORT` lives in its own `backend/.env`, the other two in the app-root
`.env`), so there is only one port => **only one set of services can physically
exist**. Measured: a second instance calling `novelservice.py start` runs
`probe(port)` first and, when it answers, replies only "already running, not
starting again" (0.1 s) — it never pulls up a second set.
So "two windows open at once" leaves exactly one real question: **who shuts them down**.
The old mechanism (`launchers/flow.go:claimLock`, file `logs/launcher.pid`) compares
"is the pid in the file mine?":
    A opens -> service starts; B opens -> reuses it
    close A -> file says B => not mine => don't stop                  OK
    close B -> file says me => stop  => **A is still using it, gone**  BROKEN
It guards "the one that closes first" but **not the one that closes last** — and the
latter is the common case (people close the window they just opened and go back to
the earlier one).
Here the yardstick becomes **reference counting**: each entry is a **live** main
program instance; "empty" means not one of them is alive => only then really stop.
★ "Empty" **does not depend on the release succeeding**: it asks "is the pid in the
  entry file alive right now?". When an instance is killed / crashes / the power goes,
  `release()` never runs and the file stays — but the pid is dead, so the liveness
  check fails and it stops counting. **Zombie entries heal themselves**; no extra
  cleanup step is needed (`clear_dead()` is only cosmetic).
★ Each instance writes **its own file** (named after its pid), never a shared JSON:
  two instances starting at once write two different files => **no lock needed** and
  no risk of corrupting each other.
⚠ A recycled pid makes "alive" wrongly true => the consequence is **the service
  lingers a while** (and next start is faster), never "stopped by mistake" (that
  would interrupt another instance mid-write). This bias is **deliberate**: better
  to leave it running than to cut someone off.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

#: 登记表目录（**相对程序根**，固定）。
#: ⚠⚠ Go 侧（`launchers/flow.go`）硬编码的是同一串 `logs/service_users`。
#:   改名必须两边一起改 —— `tools/verify_svc_users.py` 的 S 组钉着这一条。
#: [EN] Registry directory (relative to the app root, fixed).
#: [EN] ⚠⚠ The Go side (`launchers/flow.go`) hard-codes the same `logs/service_users`.
#: [EN] Renaming must happen on both sides — group S of `tools/verify_svc_users.py`
#: [EN] pins this.
DIR_REL = ('logs', 'service_users')

#: 登记文件的后缀；文件名去掉它剩下的就是 pid。
#: [EN] Suffix of an entry file; the file name minus it is the pid.
SUFFIX = '.use'

#: 判据 / 测试用：把整个登记表挪到别处（别让测试污染真实的 `logs/`）。
#: [EN] For criteria/tests: move the whole registry elsewhere so tests don't
#: [EN] pollute the real `logs/`.
ENV_OVERRIDE = 'NWS_SVC_USERS_DIR'

#: Windows：`OpenProcess` 只问「有限信息」就够了，不请求终止权限
#: （PID 被复用时，「能不能打开」比「能不能杀」安全得多）。
#: [EN] Windows: asking for "limited information" is enough; we never request
#: [EN] terminate rights (with a recycled pid, "can I open it" is far safer than
#: [EN] "can I kill it").
_W_QUERY_LIMITED = 0x1000

#: `ERROR_ACCESS_DENIED`：**打不开，但它存在**（别人的进程）。
#: [EN] `ERROR_ACCESS_DENIED`: **cannot open it, but it exists** (someone else's proc).
_W_ACCESS_DENIED = 5

#: `STILL_ACTIVE`：`GetExitCodeProcess` 给回这个值 = **进程还在跑**。
#: 拿到任何别的数都是"它已经退出了"（退出码就是那个数）。
#: [EN] `STILL_ACTIVE`: `GetExitCodeProcess` returning this = **still running**.
#: [EN] Any other value means "it has already exited" (that value is its exit code).
_W_STILL_ACTIVE = 259


# ══════════════════════════════════════════════════════════════════
#  目录
#  Directory
# ══════════════════════════════════════════════════════════════════
def dir_path(create: bool = False) -> Path:
    """登记表目录。

    `create=True` 时顺手建出来（建不出来**不报错** —— 登记失败只是"少一票"，
    不该让启动流程挂掉）。
        English:
    The registry directory.
    With `create=True` it is also created (failure is **not raised** -- a missed
    entry only means "one vote short", it must not break startup).
    """
    over = os.environ.get(ENV_OVERRIDE, '').strip()
    p = Path(over) if over else Path(__file__).resolve().parent.parent.joinpath(*DIR_REL)
    if create:
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return p


def entry_path(pid: int) -> Path:
    """某个 pid 的登记文件路径（**不**保证它存在）。
        English:
    The entry file path for a pid (does **not** guarantee it exists)."""
    return dir_path() / f'{int(pid)}{SUFFIX}'


# ══════════════════════════════════════════════════════════════════
#  进程还活着吗
#  Is a process still alive
# ══════════════════════════════════════════════════════════════════
def pid_alive(pid: int) -> bool:
    """这个 pid 现在还活着吗？

    ⚠ **Windows 上绝不能用 `os.kill(pid, 0)`**：那里的 `os.kill` 走的是
      `OpenProcess(PROCESS_ALL_ACCESS)` + `TerminateProcess`，`sig=0` 会变成
      "**以退出码 0 终止它**" —— 那是**杀人**，不是探活。所以 Windows 走
      `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`，只问不看也不动。
        English:
    Is this pid alive right now?
    ⚠ **Never use `os.kill(pid, 0)` on Windows**: there `os.kill` goes through
      `OpenProcess(PROCESS_ALL_ACCESS)` + `TerminateProcess`, and `sig=0` turns
      into "**terminate it with exit code 0**" -- that **kills**, it does not
      probe. So Windows uses `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`:
      ask, look, never touch.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == 'nt':
        return _win_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                     # 存在，只是不归我管 ⇒ 算活着
    except OSError:
        return False
    return True


def _win_alive(pid: int) -> bool:
    """Windows 探活。见 `pid_alive` 里那条「不许用 os.kill」的说明。

    ★★★ **光能 `OpenProcess` 不算活着** —— 这是实测踩出来的（2026-10-28）：
      把子进程 `kill()` 掉之后，只要**父进程还攥着它的句柄**，`OpenProcess`
      照样成功（Windows 要等最后一个句柄关掉才真正销毁进程对象）。
      于是"能打开 ⇒ 活着"会把**已经死了的**判成活的 ⇒ 僵尸登记永远自愈不了
      ⇒ 服务再也不停（看着像"跟随退出失效"）。
      ⇒ 必须再问一句 **`GetExitCodeProcess`**：
        退出码 == `STILL_ACTIVE`(259) 才是活着，拿到任何别的退出码就是**已经死了**。
    ⚠ 唯一的漏是"进程退出码恰好是 259" ⇒ 误判成活着 ⇒ 后果是**服务多留一会儿**，
      不是误停。这个方向是刻意的（宁可留着，不可掐掉）。
        English:
    Windows liveness probe. See the "never use os.kill" note in `pid_alive`.
    ★★★ **Being able to `OpenProcess` does not mean alive** -- measured, 2026-10-28:
      after killing a child, `OpenProcess` still succeeds **as long as the parent
      still holds a handle to it** (Windows destroys the process object only when
      the last handle closes). So "can open => alive" calls a **dead** process
      alive => zombie entries never heal => the service never gets stopped (reads
      exactly like "follow-app-exit broke").
      => We must also ask **`GetExitCodeProcess`**: exit code == `STILL_ACTIVE`
      (259) means alive; any other exit code means **already dead**.
    ⚠ The only hole is a process whose exit code happens to be 259 => judged
      alive => the consequence is **the service lingers**, never a wrong stop.
      That direction is deliberate (better lingering than cutting someone off).
    """
    try:
        import ctypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        h = k32.OpenProcess(_W_QUERY_LIMITED, False, pid)
        if not h:
            # 打开失败要**分两种**：进程根本不存在（参数无效）vs 存在但没权限。
            # 后者恰恰证明它活着 —— 判成"死了"就会误停服务。
            # [EN] A failed open has **two** meanings: the process doesn't exist
            # [EN] (invalid parameter) vs exists but no rights. The latter proves
            # [EN] it is alive -- calling it dead would stop the service by mistake.
            return ctypes.get_last_error() == _W_ACCESS_DENIED
        try:
            code = ctypes.c_uint32()
            if k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code)):
                return code.value == _W_STILL_ACTIVE
            return True             # 取不到退出码 ⇒ 保守当活着
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    except Exception:                                   # noqa: BLE001
        return False


# ══════════════════════════════════════════════════════════════════
#  登记 / 撤销
#  Claim / release
# ══════════════════════════════════════════════════════════════════
def claim(pid: int | None = None) -> Path | None:
    """登记「我在用服务」。返回登记文件路径（失败返回 None）。

    ★ 每个实例只写**自己那个文件** ⇒ 两个实例同时启动也不会互相踩。
        English:
    Register "I am using the services". Returns the entry path (None on failure).
    ★ Each instance only writes **its own file** => two instances starting at once
      never step on each other.
    """
    pid = int(pid if pid is not None else os.getpid())
    try:
        p = entry_path(pid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'pid': pid, 'born': time.time(),
                                 'who': 'gui'}, ensure_ascii=False),
                     encoding='utf-8')
        return p
    except OSError:
        return None


def release(pid: int | None = None) -> bool:
    """撤销「我在用服务」。

    ⚠ **返回值不是判空依据**：删不掉（文件被锁 / 安全策略拦）也只是留个文件，
      而 pid 已经退了 ⇒ `alive_pids()` 里它自然不算数。
      「本来就没有」算成功（目标达成了）。
        English:
    Withdraw "I am using the services".
    ⚠ **The return value is not what "empty" is decided by**: if the delete fails
      (locked file / security policy) only a file remains, and since the pid is
      gone it no longer counts in `alive_pids()`. "It was never there" counts as
      success (the goal is already met).
    """
    pid = int(pid if pid is not None else os.getpid())
    try:
        entry_path(pid).unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


# ══════════════════════════════════════════════════════════════════
#  读表
#  Reading the registry
# ══════════════════════════════════════════════════════════════════
def registered_pids() -> list[int]:
    """表上**登记过的** pid（**不问死活**）。
        English:
    All pids **registered** in the registry (liveness not considered)."""
    try:
        entries = list(dir_path().iterdir())
    except OSError:
        return []
    out: list[int] = []
    for f in entries:
        if not f.is_file() or f.suffix != SUFFIX:
            continue
        stem = f.name[: -len(SUFFIX)]
        if stem.isdigit():
            out.append(int(stem))
    return sorted(set(out))


def alive_pids() -> list[int]:
    """表上**还活着**的 pid —— 僵尸登记不在这里面。
        English:
    The pids on the registry that are **still alive** -- zombie entries are not here."""
    return [p for p in registered_pids() if pid_alive(p)]


def alive_others(pid: int | None = None) -> list[int]:
    """除了**自己**，还有谁活着（这是收尸那一刀唯一该问的问题）。
        English:
    Who else is alive **besides me** (the only question the shutdown cut should ask)."""
    me = int(pid if pid is not None else os.getpid())
    return [p for p in alive_pids() if p != me]


def any_other_alive(pid: int | None = None) -> bool:
    """还有别的实例在用服务吗？**是 ⇒ 不许停**。
        English:
    Is another instance still using the services? **Yes => must not stop them**."""
    return bool(alive_others(pid))


def clear_dead() -> int:
    """把已死的登记文件删掉，返回删了几个。

    ⚠ 这**只是收拾**，不是判空的一部分：判空看的是 pid 死活，删不删都不影响结论。
      删不动（被锁 / 被安全策略拦）就留着，下次再试。
        English:
    Delete the entry files whose pids are dead; returns how many were removed.
    ⚠ This is **tidying only**, not part of deciding "empty": that looks at pid
      liveness, so deleting or not changes nothing. If a delete is refused (locked
      / blocked by policy) the file just stays and we try again next time.
    """
    n = 0
    for pid in registered_pids():
        if pid_alive(pid):
            continue
        try:
            entry_path(pid).unlink()
            n += 1
        except OSError:
            pass
    return n


def snapshot() -> dict:
    """表上现在是什么样（调试 / 判据用）。
        English:
    What the registry looks like right now (debug / criteria)."""
    reg = registered_pids()
    alive = alive_pids()
    me = os.getpid()
    return {'dir': str(dir_path()), 'registered': reg, 'alive': alive,
            'dead': [p for p in reg if p not in alive],
            'me': me, 'others': [p for p in alive if p != me]}
