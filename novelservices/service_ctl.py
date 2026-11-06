# -*- coding: utf-8 -*-
"""外部创作服务的**统一控制器**（给 Go 启动器用：setup / uninstall / start）。

谁调用它
--------
`launchers/` 下三个 Go 程序（setup.exe / uninstall.exe / start.exe）。
它们要在三个时刻跟外部服务打交道，而**自己不方便干这些活**：

  · `setup`     —— 装完之后把服务的运行环境备好（建 venv、装依赖），
                   让第一次启动不必卡几分钟；
  · `start`     —— 主窗口退出时，按 `*_FOLLOW_APP` 开关把服务停掉；
  · `uninstall` —— 删快捷方式之前先把服务停掉（不停会一直占着端口）。

服务**不由启动器拉起**：主程序 `gui/app_flet.py` 的
`_maybe_autostart_service` 受 `*_AUTOSTART` 控制自己拉（那件事要在界面里
报进度、要绕代理，本来就在 Python 侧）。启动器只负责**备环境**和**停**。

为什么是"一个控制器"而不是每个服务一套调用约定
------------------------------------------
Go 那边三个平台共用一份代码，"怎么跟某个服务打交道"如果散成三套约定
（这个跑 scripts/x.py、那个跑 -m uvicorn…），Go 侧就要为每个服务写一遍分支，
而分支正是最容易和主程序悄悄不一致的地方。所以收敛到一个入口：

    python service_ctl.py prepare penshot      # 备环境（幂等，齐了就秒过）
    python service_ctl.py stop    penshot      # 停掉（幂等，没在跑也算成功）

服务 id 就两个：`penshot` / `plotpilot`。

★ 为什么 MuMuAINovel 不进来（2026-10-17）
----------------------------------------
它自己就有 `MuMuAINovel/backend/novelservice.py`，而且那里面全是**踩过坑的
差异化逻辑**：只认 Python 3.10~3.12 的牢笼（3.13 上 SQLAlchemy 2.0.25 会炸）、
alembic 建表、pid 文件不可信时按端口反查……把它也接进来，就要在这里**第二份**
实现"挑哪个解释器跑它"。两处实现同一件事是这条产品线反复吃的亏。
所以 MuMu 保持原样：Go 侧直接跑它自己的脚本（测试钩子
`NWS_TEST_SERVICE_DIR` 的夹具机制因此完全不动）。

三条纪律（与两座桥一致）
------------------------
1. **纯标准库、Python 3.10+ 都能跑。** 本文件由启动器找到的**任意** Python
   执行（不一定是主程序的 .venv），所以只用 stdlib；服务自己的 venv 由本文件
   去建、由服务自己的解释器去 import 校验。
2. **绝不成为单点故障。** 目录不在（发布包把 `novelservices/` 整体排掉了）、
   venv 建不了、依赖装失败 —— 一律给一句人话 + 非 0 退出码，**由启动器决定**
   要不要因此失败；本文件自己不去动主程序。
3. **子进程一律不许冒控制台。** 顶层（setup/uninstall/start.exe）是 Windows 上
   的无控制台 GUI 进程，下面每一层起 console 子进程的地方都得自己声明
   CREATE_NO_WINDOW —— 见 `no_window_kw()`。

English:
**Unified controller for the external creation services** (for the Go launchers:
setup / uninstall / start).
Who calls it
------------
The three Go programs under `launchers/`. They must deal with the external
services at three moments, and **cannot conveniently do that work themselves**:

  · `setup`     -- after installing, prepare the service runtime (venv + deps)
                   so the first start doesn't stall for minutes;
  · `start`     -- when the main window exits, stop the services per their
                   `*_FOLLOW_APP` switches;
  · `uninstall` -- stop the services before removing the shortcuts (a running
                   service keeps holding its port).

Services are **not started by the launcher**: the main program's
`gui/app_flet.py::_maybe_autostart_service` starts them itself under
`*_AUTOSTART` (that path needs UI progress and proxy-bypassing anyway).
The launcher only **prepares the runtime** and **stops**.

Why one controller instead of one calling convention per service
--------------------------------------------------------------
Three platforms share one Go codebase; if "how to talk to a service" scattered
into three conventions, the Go side would need one branch per service, and
branches are exactly where silent divergence from the main program creeps in.
So everything converges on one entry point:

    python service_ctl.py prepare penshot      # prepare runtime (idempotent)
    python service_ctl.py stop    penshot      # stop (idempotent)

Only two service ids: `penshot` / `plotpilot`.

★ Why MuMuAINovel is not in here (2026-10-17)
---------------------------------------------
It already owns `MuMuAINovel/backend/novelservice.py`, full of
pitfall-specific logic: the Python 3.10~3.12 cage (SQLAlchemy 2.0.25 explodes on
3.13), alembic schema init, port-reverse-lookup when the pid file lies...
Wiring it in here would mean a **second** implementation of "which interpreter
runs it". Two implementations of one thing is a recurring loss on this product
line. So MuMu stays as-is: the Go side runs its own script directly (and the
`NWS_TEST_SERVICE_DIR` fixture mechanism is therefore untouched).

Three disciplines (same as the two bridges)
-------------------------------------------
1. **Pure stdlib, any Python 3.10+.** This file runs under **whatever** Python
   the launcher found (not necessarily the app's .venv), so stdlib only; each
   service's own venv is created here and import-checked by its own interpreter.
2. **Never a single point of failure.** Missing directory (the release bundle
   drops `novelservices/` entirely), venv creation failure, dependency install
   failure -- always a human-readable line plus a non-zero exit code, and it's
   **the launcher's call** whether that fails the job; this file never touches
   the main program itself.
3. **Child processes must never spawn a console.** The top level (setup /
   uninstall / start.exe) is a console-less GUI process on Windows, so every
   layer that starts a console child must declare CREATE_NO_WINDOW itself --
   see `no_window_kw()`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
#  ★★★ 输出**一律 UTF-8**（2026-10-25 用户报的"启动界面出现乱码"）
#
#  现象：启动窗口的消息条里出现
#        `PenShot �־����� �� ֹͣ` / `[ok] ��ֹ��pid=10184��`
#  根因：本文件被启动器当子进程调起，stdout **不是控制台**（是一根管道）⇒
#        Python 退回**系统 locale 编码**，中文 Windows 上是 cp936(GBK)。
#        而启动器（Go）把子进程 stdout **字节直通**写进 `logs/launcher.log`，
#        它自己写的行是 UTF-8；启动窗口再用 `decode('utf-8','replace')` 读回来
#        ⇒ **同一个文件里两种编码**，GBK 那几行全成乱码。
#        实测：`'停止'.encode('gbk')` = `cd a3 d6 b9`，
#        按 UTF-8 解码正是 `ֹͣ` —— 与用户看到的完全一致。
#  修法：重定向时也强制 UTF-8。三个脚本（本文件 / `tools/platform_install.py` /
#        `tools/launcher_progress.py`）都要有，因为它们都是启动器起的子进程。
#  ⚠ 只在**非控制台**时改：真控制台下 Python 走 `WriteConsoleW`，本来就是宽字符，
#    reconfigure 没有意义；而手跑时用户希望跟着系统码页走。
#  ⚠ `errors='replace'`：控制台码页装不下的字符不该让整个收尾崩掉。
# [EN] ★★★ Output is **always UTF-8** (user-reported "mojibake in the splash", 2026-10-25).
# [EN] Symptom: `PenShot �־����� �� ֹͣ` in the splash message strip.
# [EN] Cause: launched as a child process, stdout is a **pipe**, so Python falls back to the
# [EN] system locale encoding (cp936/GBK on Chinese Windows). The Go launcher passes child stdout
# [EN] **byte for byte** into `logs/launcher.log` while writing its own lines as UTF-8, and the
# [EN] splash reads it back with `decode('utf-8','replace')` => **two encodings in one file**.
# [EN] Measured: `'停止'.encode('gbk')` = `cd a3 d6 b9`, which decodes as `ֹͣ` — exactly what the
# [EN] user saw.
# [EN] Fix: force UTF-8 even when redirected. All three scripts (this one,
# [EN] `tools/platform_install.py`, `tools/launcher_progress.py`) need it — the launcher spawns all
# [EN] of them. ⚠ Only when **not** a console: on a real console Python uses `WriteConsoleW`
# [EN] (already wide), and a human running it by hand expects the system code page.
if not sys.stdout.isatty():
    # ⚠ 循环变量用完要清，但**不能无条件 `del`**：`isatty()` 为真时循环一次都没跑，
    #   `del _st` 会当场 `NameError`（而那条路是"人手工在控制台里跑"，最容易漏测）。
    for _st in (sys.stdout, sys.stderr):
        try:
            _st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):          # 老 Python / 已被替换的流
            pass
    try:
        del _st
    except NameError:
        pass

# ── sys.path：两处都要能 import ──────────────────────────────
# [EN] ── sys.path: two places must be importable ──
# 本文件被 `python novelservices/service_ctl.py` 跑时，sys.path[0] 只有
# novelservices/ 这一层。而 `stop` 要 import 两座桥（同目录 ⇒ 要 novelservices/），
# 桥里的 `_config()` 又要 `from config import Config` 读主程序 .env 里的端口
# （⇒ 要程序根目录）。两个都显式补上，不依赖调用方从哪儿跑。
# [EN] When run as `python novelservices/service_ctl.py`, sys.path[0] is only the
# [EN] novelservices/ layer. But `stop` imports the two bridges (same dir), and
# [EN] their `_config()` does `from config import Config` to read the real ports
# [EN] from the app's .env (root dir). Both are added explicitly, so it doesn't
# [EN] matter where the caller runs it from.
HERE = Path(__file__).resolve().parent          # novelservices/
APP_ROOT = HERE.parent                            # 程序根目录
for _p in (str(APP_ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

IS_WIN = os.name == "nt"

#: pip 镜像源（官方源兜底）—— 与 `MuMuAINovel/backend/novelservice.py` 同一套，
#: 两台机器实测：镜像源装不动时官方源偶尔能救回来。
# [EN] : pip mirror (official source as fallback) -- same as in
# [EN] `MuMuAINovel/backend/novelservice.py`.
MIRROR = "https://mirrors.aliyun.com/pypi/simple"

#: 这两个服务的 venv 的 Python 下限。MuMu 那个"只认 3.10~3.12"的牢笼**不适用**：
#: PenShot 的 `requires-python >= 3.10`、PlotPilot 的开发 venv 就是 3.13，
#: 本地两个 .venv 都是 3.13.14 且实测跑得动。
# [EN] : Python floor for these two services' venvs. MuMu's "3.10~3.12 only" cage
# [EN] **does not apply**: PenShot declares requires-python >= 3.10, PlotPilot's
# [EN] dev venv is 3.13, and both local .venvs are 3.13.14 and verified working.
PY_MIN = (3, 10)


# ══════════════════════════════════════════════════════════════════
#  服务表
# [EN] Service table
# ══════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Svc:
    """一个外部服务的"怎么备环境、怎么停"。

    English:
    One external service's "how to prepare and how to stop".
    """

    sid: str                 #: 命令行里的 id（稳定，判据/测试钩子都认它）
    zh: str                  #: 给用户看的中文名
    en: str                  #: 给用户看的英文名
    dir: Path                #: 服务自己的目录（venv 就在它下面）
    deps_args: tuple[str, ...]   #: `pip install` 的参数（在 dir 下跑）
    import_check: str        #: venv 里 import 什么才算"依赖齐了"


#: pip 装依赖时的两个刻意选择（都写在注释里，因为都是"少装点"的决策）：
#:   · PenShot 用 `pip install -e .` 而**不带 `[full]`** —— `full` 是
#:     dashscope / langchain-ollama / sentence-transformers 那一堆可选能力，
#:     缺了桥那边会降级（能力探测），装了要多拉近 2GB。用户机上不允许
#:     "默默联网装 2GB"。
#:   · PlotPilot 用 `pip install -r requirements.txt` 而**不碰
#:     `requirements-local.txt`** —— 同理，那是 sentence-transformers / torch /
#:     faiss 的本地向量模型（~2GB），按需再说。
# [EN] Two deliberate choices in the pip args (both commented, both are
# [EN] "install less" decisions):
# [EN]   · PenShot: `pip install -e .` **without `[full]`** -- `full` is the
# [EN]     dashscope / langchain-ollama / sentence-transformers optional set;
# [EN]     the bridge degrades via capability probing, installing it would pull
# [EN]     ~2GB more. "Silently installing 2GB over the network" is unacceptable
# [EN]     on a user machine.
# [EN]   · PlotPilot: `pip install -r requirements.txt` and **never touch
# [EN]     `requirements-local.txt`** -- same reason: local vector models
# [EN]     (sentence-transformers / torch / faiss, ~2GB), on demand only.
SERVICES: dict[str, Svc] = {
    "penshot": Svc(
        sid="penshot",
        zh="PenShot 分镜服务",
        en="PenShot storyboard service",
        dir=HERE / "PenShot",
        deps_args=("-e", "."),
        # import 的就是 uvicorn 真正要加载的那个模块（`penshot.app:app`）——
        # "依赖齐了"的判据必须是**服务入口本身能 import**，不是随便挑几个包名。
        # [EN] Import exactly the module uvicorn will load (`penshot.app:app`) --
        # [EN] "deps are complete" must mean **the service entry itself imports**,
        # [EN] not some hand-picked package names.
        import_check="import penshot.app",
    ),
    "plotpilot": Svc(
        sid="plotpilot",
        zh="PlotPilot 编剧服务",
        en="PlotPilot screenwriting service",
        dir=HERE / "PlotPilot",
        deps_args=("-r", "requirements.txt"),
        import_check="import interfaces.main",
    ),
}


# ══════════════════════════════════════════════════════════════════
#  输出（中文 Windows 控制台是 GBK，emoji 会直接崩，所以只用 ASCII 记号）
# [EN] Output (Chinese Windows consoles are GBK; emoji would crash it,
# [EN] so ASCII markers only)
# ══════════════════════════════════════════════════════════════════
def say(msg: str = "") -> None:
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def ok(msg: str) -> None:
    say(f"  [ok] {msg}")


def warn(msg: str) -> None:
    say(f"  [!]  {msg}")


def fail(msg: str) -> None:
    say(f"  [x]  {msg}")


def tail(r: subprocess.CompletedProcess, n: int = 300) -> str:
    """一条命令输出的尾巴（出错时那几行比退出码有用）。"""
    s = ((r.stdout or "") + (r.stderr or "")).strip()
    return s[-n:].replace("\n", " ； ")


# ══════════════════════════════════════════════════════════════════
#  起子进程：一律静默（无控制台）
# [EN] Spawning child processes: always silent (console-less)
# ══════════════════════════════════════════════════════════════════
def no_window_kw() -> dict:
    """Windows：让子进程**不要**被分配控制台。

    ★ 2026-10-10 实测（`developers/_probe_console_windows.py`，直接数桌面上
      **可见的**控制台窗口）：
        父进程没有控制台 + 子进程不带标志            → **多出 1 个黑窗** ★
        父进程没有控制台 + 子进程带 CREATE_NO_WINDOW → 0 个窗口 ✓
      与 `novelservice.py` / `tools/launcher_progress.py` 里同款的那份完全一致
      （三处各有一份是刻意的：它们分属三个进程层，改一处漏两处正是这个坑的
      来源；真正共用一份的话，谁被单独拷走谁就丢标志）。

    English:
    Windows: make the child process **not** be allocated a console.
    ★ Measured 2026-10-10 (`developers/_probe_console_windows.py`, counting
      **visible** top-level console windows on the desktop):
        parent without console + child without flag → **1 extra black window** ★
        parent without console + child with CREATE_NO_WINDOW → 0 windows ✓
    Same as the twin copies in `novelservice.py` / `tools/launcher_progress.py`
    (three copies on purpose: they belong to three process layers, and
    "changed one, missed two" is exactly how this pitfall is born; truly sharing
    one copy means whoever gets copied away alone loses the flag).
    """
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {"creationflags": 0x08000000, "startupinfo": si}


def run(cmd: list[str], cwd: Path | None = None,
        timeout: float | None = None) -> subprocess.CompletedProcess:
    """跑一条命令并收输出（合并 stdout+stderr，UTF-8，GBK 安全）。"""
    kw = no_window_kw()
    if timeout is not None:
        kw["timeout"] = timeout
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


# ══════════════════════════════════════════════════════════════════
#  venv：建 / 验 / 装
# [EN] venv: create / verify / install
# ══════════════════════════════════════════════════════════════════
def venv_py(venv: Path) -> Path | None:
    """venv 的**控制台版**解释器（pip / import 校验要收输出，用 python.exe）。"""
    rels = ("Scripts/python.exe",) if IS_WIN else ("bin/python",)
    for rel in rels:
        p = venv / rel
        if p.exists():
            return p
    return None


def py_version_of(exe: Path) -> tuple[int, int] | None:
    """问一个 python 解释器它的版本；不是 python 就返回 None。"""
    try:
        r = run([str(exe), "-c", "import sys;print('%d.%d' % sys.version_info[:2])"])
    except OSError:
        return None
    if r.returncode != 0:
        return None
    try:
        a, b = (r.stdout or "").strip().split(".")
        return int(a), int(b)
    except Exception:                                          # noqa: BLE001
        return None


def bootstrap_candidates() -> list[list[str]]:
    """候选的"建 venv 用"解释器（自己优先 —— 启动器已经挑好一个能用的）。"""
    cands: list[list[str]] = []
    if sys.executable:
        cands.append([sys.executable])
    if IS_WIN:
        cands.append(["py", "-3"])                  # Windows 官方 launcher
    for name in (("python3", "python") if not IS_WIN else ("python", "python3")):
        if shutil.which(name):
            cands.append([name])
    return cands


def ensure_venv(svc: Svc) -> Path | None:
    """确保服务的 venv 存在且能用；返回解释器路径（失败返回 None）。

    与 `novelservice.py` 的同款决定：**坏的 venv 挪开而不是删** ——
    万一是用户手动装过东西的，删了找不回来。

    English:
    Ensure the service's venv exists and works; return the interpreter path
    (None on failure). Same decision as `novelservice.py`: **a broken venv is
    moved aside, not deleted** -- if the user installed something in it by hand,
    deletion would be unrecoverable.
    """
    venv = svc.dir / ".venv"
    py = venv_py(venv)
    if py is not None and py_version_of(py) is not None:
        return py

    if venv.exists():
        aside = venv.with_name(f".venv.broken-{int(time.time())}")
        warn(f"现有 .venv 不可用，移到 {aside.name}/（不删除，确认没用可自行清理）")
        try:
            venv.rename(aside)
        except OSError as e:
            fail(f"挪不动 .venv（{e!r}），请手动删掉它再试")
            return None

    for cand in bootstrap_candidates():
        tag = " ".join(cand)
        v = py_version_of(Path(cand[0])) if len(cand) == 1 else None
        if v is None:
            try:
                r = run(cand + ["-c",
                                "import sys;print('%d.%d' % sys.version_info[:2])"])
            except OSError:
                continue
            if r.returncode != 0:
                continue
            try:
                a, b = (r.stdout or "").strip().split(".")
                v = (int(a), int(b))
            except Exception:                              # noqa: BLE001
                continue
        if v is None or v < PY_MIN:
            warn(f"{tag} 不可用或版本低于 {PY_MIN[0]}.{PY_MIN[1]}，跳过")
            continue
        say(f"  用 {tag}（Python {v[0]}.{v[1]}）建虚拟环境…")
        try:
            r = run(cand + ["-m", "venv", str(venv)])
        except OSError as e:
            warn(f"{tag} 建 venv 失败：{e!r}")
            continue
        if r.returncode == 0:
            py = venv_py(venv)
            if py is not None:
                ok(f"虚拟环境已建好（.venv）")
                return py
        warn(f"{tag} 建 venv 失败：{tail(r)}")

    fail(f"没找到 Python {PY_MIN[0]}.{PY_MIN[1]} 以上的解释器来建虚拟环境")
    return None


def pip_install(svc: Svc, py: Path) -> bool:
    """装依赖（先镜像源、后官方源）。失败只警告不抛 —— 由调用方决定。"""
    say("  正在安装依赖（首次可能要几分钟，请耐心）…")
    base = [str(py), "-m", "pip", "install",
            "--no-cache-dir", "--disable-pip-version-check"]
    # 老 pip 解析不了新包的元数据（这台机器上实测过），先升一下；
    # 升失败不拦 —— 下面的安装会自己再报一次。
    # [EN] Old pip cannot resolve new packages' metadata (measured on this
    # [EN] machine); upgrade first. Failure here is not fatal -- the install
    # [EN] below will report again by itself.
    try:
        run(base + ["--upgrade", "pip", "-i", MIRROR], cwd=svc.dir)
    except OSError:
        pass
    for extra, label in ((["-i", MIRROR], "镜像源"), ([], "官方源")):
        try:
            r = run(base + list(svc.deps_args) + extra, cwd=svc.dir)
        except OSError as e:
            warn(f"{label}安装失败：{e!r}")
            continue
        if r.returncode == 0:
            return True
        warn(f"{label}安装失败，尾部输出：{tail(r)}")
    return False


def import_ok(py: Path, code: str, cwd: Path) -> bool:
    """venv 里 import 一遍服务入口（超时给宽一点：PenShot 首次 import 约 13 秒）。"""
    try:
        r = run([str(py), "-c", code], cwd=cwd, timeout=600)
    except subprocess.TimeoutExpired:
        warn("import 校验超时（600 秒）")
        return False
    except OSError as e:
        warn(f"import 校验跑不起来：{e!r}")
        return False
    if r.returncode != 0:
        warn(f"import 校验没过：{tail(r)}")
        return False
    return True


# ══════════════════════════════════════════════════════════════════
#  两个动作：prepare / stop
# [EN] The two actions: prepare / stop
# ══════════════════════════════════════════════════════════════════
def cmd_prepare(svc: Svc) -> int:
    """备环境。幂等：依赖齐了就秒过（只付一次 import 校验的钱）。

    English:
    Prepare the runtime. Idempotent: when the deps are complete it returns
    almost immediately (paying only for one import check).
    """
    say()
    say(f"  {svc.zh} · 准备运行环境")
    say("  " + "=" * 34)
    if not svc.dir.exists():
        # 发布包把 novelservices/ 整体排掉了 ⇒ 用户机上这很正常，不是错误。
        # [EN] The release bundle drops novelservices/ entirely, so this is
        # [EN] normal on user machines -- not an error.
        ok(f"没找到 {svc.zh} 目录（external services are optional），无需准备")
        return 0
    py = ensure_venv(svc)
    if py is None:
        return 1
    if import_ok(py, svc.import_check, svc.dir):
        ok("依赖已齐全，跳过安装")
        return 0
    if not pip_install(svc, py):
        fail(f"依赖安装失败。检查网络后重试，或手动进 {svc.dir} 目录装依赖。")
        return 1
    if not import_ok(py, svc.import_check, svc.dir):
        fail("依赖装完了，但服务入口仍然 import 失败 —— 看上面的输出。")
        return 1
    ok("准备完成。主程序启动时会按「外部创作服务」里的开关自动拉起它。")
    return 0


def cmd_stop(svc: Svc) -> int:
    """停掉服务。**委托服务自己的桥**（`*_bridge.stop_service()`）——
    那边已经有完整的"pid 文件 → 端口反查 → taskkill"（PenShot）与
    "POST /internal/shutdown"（PlotPilot）逻辑，且都是幂等的
    （没在跑返回成功）。在这里重写一遍就是两处实现同一件事。

    为什么 import 桥而不是起子进程跑它：桥是**纯标准库**的（三条纪律第 2 条），
    随便哪个 Python 都能 import；而起子进程还要再挑一次解释器。

    English:
    Stop the service. **Delegated to the service's own bridge**
    (`*_bridge.stop_service()`) -- it already owns the complete "pid file →
    port reverse lookup → taskkill" (PenShot) and "POST /internal/shutdown"
    (PlotPilot) logic, both idempotent (returns success when not running).
    Re-implementing that here would be two implementations of one thing.

    Why import the bridge instead of spawning a subprocess: the bridge is
    **pure stdlib** (discipline #2), importable by any Python; spawning would
    require choosing an interpreter yet again.
    """
    say()
    say(f"  {svc.zh} · 停止")
    say("  " + "=" * 20)
    if not svc.dir.exists():
        ok(f"没找到 {svc.zh} 目录，无需停止")
        return 0
    try:
        if svc.sid == "penshot":
            import penshot_bridge
            good, msg = penshot_bridge.stop_service()
        else:
            import plotpilot_bridge
            good, msg = plotpilot_bridge.stop_service()
    except Exception as e:                                      # noqa: BLE001
        # 桥 import 失败（比如目录被删空）不该把卸载/退出拖死：
        # 报清楚，返回 0 —— "停不了"≠"卸载失败"，服务没起来时本来就没得停。
        # [EN] A failed bridge import (e.g. the directory was emptied) must not
        # [EN] stall the uninstall/exit: report clearly and return 0 --
        # [EN] "cannot stop" != "uninstall failed"; when the service isn't
        # [EN] running there is nothing to stop anyway.
        warn(f"加载 {svc.zh} 的桥失败（{type(e).__name__}: {e}）")
        return 0
    if good:
        ok(msg)
        return 0
    fail(msg)
    return 1


# ══════════════════════════════════════════════════════════════════
#  入口
# [EN] Entry point
# ══════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        add_help=True,
        description="外部创作服务统一控制器（prepare / stop）")
    ap.add_argument("action", choices=["prepare", "stop"],
                    help="prepare=备运行环境；stop=停掉服务")
    ap.add_argument("service", choices=sorted(SERVICES),
                    help="服务 id")
    a = ap.parse_args(argv)

    svc = SERVICES[a.service]
    if a.action == "prepare":
        return cmd_prepare(svc)
    return cmd_stop(svc)


if __name__ == "__main__":
    raise SystemExit(main())
