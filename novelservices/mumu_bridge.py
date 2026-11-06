# -*- coding: utf-8 -*-
"""NWS → MuMuAINovel 的**接入层**（桥）。

给谁用的
--------
给主程序里的 Agent 用（目前是剧组里的 **小说作家**）。目的是：
**把"写一章正文"这件事交给 MuMuAINovel 去干**，而不是让 Agent 自己拼提示词问模型。

它不做什么
----------
**不改 MuMuAINovel 的源码。** 一切通过它自己的 REST 接口
（`novelservices/MuMuAINovel/backend/` 起的 uvicorn 服务）走。
所以上游怎么升级都不影响这里 —— 顶多是接口不兼容，那也只会**降级**，不会崩主程序。

三条设计纪律（都是被坑出来的）
------------------------------
1. **绝不成为单点故障。** 服务没起、超时、生成失败、返回空章 —— 一律返回
   `BridgeResult(ok=False, reason=...)`，**由调用方回退到原来的自写路径**。
   实测教训：推理模型的"想"耗时不可控（最坏 207 秒返回 0 字），
   这种环节不能挂在关键路径上赌它成功。
2. **纯标准库。** 主程序跑在 Python 3.13，而 MuMuAINovel 的 venv 是 3.10~3.12
   （SQLAlchemy 2.0.25 在 3.13 上会抛 AssertionError）。两边**环境不同**，
   所以这里只用 stdlib，通过 HTTP 说话 —— 不 import 对方 venv 里的任何东西。
3. **回环请求必须绕代理。** 本机设了系统代理，连 127.0.0.1 的请求会被丢给代理：
   服务活着返回 200、死了返回 502，**两者都"有响应"**，于是一个死的服务看起来是活的。
   清 `HTTP_PROXY` 不够（Windows 上 urllib 还读注册表）→ 显式空 `ProxyHandler`。

用法
----
    from novelservices import mumu_bridge as BR

    st = BR.service_status()                 # 服务在不在（1.5 秒超时，不阻塞）
    if st.ok:
        r = BR.generate_chapter(BR.ChapterTask(
            project_key="莫问楼", novel_dir=..., title="莫问",
            outline="今天是第 3 天，……", characters=["陈忘", "阿九"],
            target_words=2500))
        if r.ok:
            text = r.text
        else:
            ...  # 回退：用 llm.replies.ask 自己写

English:
**Integration layer** (bridge) from NWS → MuMuAINovel.
Who it's for
--------
For the Agent in the main program (currently the **novel writer** in the crew). The goal is:
**hand off "writing a chapter of prose" to MuMuAINovel**, instead of letting the Agent assemble
prompts and ask the model itself.
What it does not do
----------
**Does not modify MuMuAINovel's source code.** Everything goes through its own REST API
(the uvicorn service started by `novelservices/MuMuAINovel/backend/`).
So however upstream upgrades, it won't affect here —— at most the API is incompatible, which
would only cause a **degrade**, not a crash of the main program.
Three design disciplines (all learned the hard way)
------------------------------
1. **Never become a single point of failure.** Service not started, timeout, generation failure, empty chapter returned —— all return
   `BridgeResult(ok=False, reason=...)`, **the caller falls back to the original self-written path**.
   Lesson from practice: a reasoning model's "thinking" time is uncontrollable (worst case 207 seconds returning 0 characters),
   this kind of step can't be hung on the critical path gambling on its success.
2. **Pure standard library.** The main program runs on Python 3.13, while MuMuAINovel's venv is 3.10~3.12
   (SQLAlchemy 2.0.25 throws AssertionError on 3.13). The two sides have **different environments**,
   so here we only use stdlib and talk over HTTP -- without importing anything from the other's venv.
3. **Loopback requests must bypass the proxy.** This machine has a system proxy set, and requests to 127.0.0.1 get dropped onto the proxy:
   a live service returns 200, a dead one returns 502, **both "have a response"**, so a dead service looks alive.
   Clearing `HTTP_PROXY` isn't enough (on Windows urllib also reads the registry) -> explicitly empty `ProxyHandler`.
Usage
----
    from novelservices import mumu_bridge as BR
    st = BR.service_status()                 # is the service up (1.5 second timeout, non-blocking)
    if st.ok:
        r = BR.generate_chapter(BR.ChapterTask(
            project_key="莫问楼", novel_dir=..., title="莫问",
            target_words=2500))
        if r.ok:
            text = r.text
        else:
            ...  # fallback: write it yourself with llm.replies.ask
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_LOG = __import__("logging").getLogger("nws.mumu_bridge")

__all__ = [
    "MUMU_DIR", "BACKEND_DIR", "BACKEND_ENV", "MUMU_BASE_URL",
    "BridgeStatus", "BridgeResult", "ChapterTask",
    "service_status", "service_url", "read_service_env", "save_service_env",
    "start_service", "stop_service", "generate_chapter", "polish", "list_skills",
    "ensure_project", "forget_project", "describe",
]

# ── 路径（全部相对本文件，不写死盘符）──────────────────────────────
# [EN] ── Paths (all relative to this file, no hardcoded drive letters) ──────────────────────────────
HERE = Path(__file__).resolve().parent
MUMU_DIR = HERE / "MuMuAINovel"
BACKEND_DIR = MUMU_DIR / "backend"
BACKEND_ENV = BACKEND_DIR / ".env"
_CLIENT_PY = MUMU_DIR / "mumu_client.py"

#: 上游项目地址（界面上要标出来 —— 这套服务不是本项目写的）
# [EN] : Upstream project address (must be shown in the UI —— this service is not written by this
# [EN] project)
UPSTREAM = "https://github.com/xiamuceer-j/MuMuAINovel"

#: 默认连接地址（真值从 `backend/.env` 的 APP_HOST/APP_PORT 读）
# [EN] : Default connection address (real value read from `backend/.env` APP_HOST/APP_PORT)
MUMU_BASE_URL = "http://127.0.0.1:8001"

#: 项目映射缓存的文件名（放在**这本书自己的目录**里，不集中放一处 ——
#: 这样"哪个 NWS 项目对应哪个 MuMuAINovel 项目"跟着书走，书搬走映射也跟着走）
# [EN] : Filename of the project mapping cache (placed in **this book's own directory**, not
# [EN] centralized in one place ——
# [EN] : this way "which NWS project corresponds to which MuMuAINovel project" follows the book, and
# [EN] the mapping moves with the book)
_MAP_NAME = ".mumu_project.json"


# ══════════════════════════════════════════════════════════════════
#  结果类型
# [EN] Result type
# ══════════════════════════════════════════════════════════════════
@dataclass
class BridgeStatus:
    """服务状态。`reason` 是**给人看的一句话**，要能直接显示在界面上。
        English:
    Service status. `reason` is **a one-liner for humans**, it must be directly displayable in the
    UI.
    """

    ok: bool
    reason: str = ""
    base_url: str = ""

    def __bool__(self) -> bool:                                  # 方便 `if st:`
    # [EN] Convenient for `if st:`
        return self.ok


@dataclass
class BridgeResult:
    """一次生成的结果。失败时 `reason` **必须**说清是哪一环坏的。
        English:
    The result of one generation. On failure `reason` **must** state clearly which link broke.
    """

    ok: bool
    text: str = ""
    reason: str = ""
    chapter_number: int = 0
    elapsed: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChapterTask:
    """交给 MuMuAINovel 的一件事：**写一章**。

    `outline` 是**细纲全文** —— 不是摘要、不是关键词，而是"这一章只发生这几件事"
    的完整叙述。为什么要求这么具体：实测 MuMuAINovel 的**文风层很强、结构层不行**
    （它会把你给的一章料压成半章、还顺手砍掉闲笔），只有细纲写到"只准写这几件事"
    才能约束住它。写得含糊 = 拿到一份跑题的第一稿。
    
        English:
    One thing handed to MuMuAINovel: **write a chapter**.
        `outline` is the **full detailed outline** -- not a summary, not keywords, but a complete
        narrative of "only these few things happen in this chapter". Why so specific: in practice MuMuAINovel's **prose-style layer is very strong, its structure layer isn't**
        (it'll compress the chapter material you give into half a chapter, and casually cut the digressions), only an outline written as "you're only allowed to write these few things"
        can constrain it. Vague writing = you get an off-topic first draft.
    """

    project_key: str                     # NWS 这边的书名（用来找/建对应的 MuMuAINovel 项目）
    novel_dir: Path | None               # NWS 项目目录（放映射缓存；可为 None）
    title: str                           # 这一章的标题
    outline: str                         # ★ 细纲全文（会写进 structure["summary"]）
    # [EN] The book name on the NWS side (used to find/create the corresponding MuMuAINovel project)
    # [EN] NWS project directory (holds the mapping cache; may be None)
    # [EN] Title of this chapter
    # [EN] ★ Full detailed outline (will be written into structure["summary"])
    characters: list[str] = field(default_factory=list)
    genre: str = ""
    target_words: int = 2500
    style_id: int | None = None          # MuMuAINovel 里的写作风格 id
    model: str = ""                      # 空 = 用服务端默认
    perspective: str = ""                # 空 = 用服务端默认
    skill_key: str = ""                  # 空 = 用它的默认写作流程
    enable_analysis: bool = False        # 开=它会给这一章做分析（更慢，但下一章记得住）
    timeout: float = 900.0               # 等生成完成的上限（秒）
    # [EN] Writing style id in MuMuAINovel
    # [EN] Empty = use server-side default
    # [EN] Empty = use server-side default
    # [EN] Empty = use its default writing workflow
    # [EN] On = it will run analysis for this chapter (slower, but the next chapter remembers)
    # [EN] Upper limit for waiting for generation to complete (seconds)


# ══════════════════════════════════════════════════════════════════
#  服务端 .env 读写（天机里的「创作服务」页就是读写它）
# [EN] Server-side .env read/write (the "Creation Service" page in Tianji reads and writes it)
# ══════════════════════════════════════════════════════════════════
def read_service_env() -> dict[str, str]:
    """读 MuMuAINovel 服务自己的 `backend/.env`（不存在就返回空表）。
        English:
    Read MuMuAINovel service's own `backend/.env` (returns an empty table if it doesn't exist).
    """
    out: dict[str, str] = {}
    if not BACKEND_ENV.exists():
        return out
    for line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def service_url() -> str:
    """服务地址（从 `backend/.env` 的 `APP_HOST`/`APP_PORT` 现读）。
        English:
    Service address (read live from `backend/.env`'s `APP_HOST`/`APP_PORT`).
    """
    env = read_service_env()
    host = env.get("APP_HOST", "127.0.0.1") or "127.0.0.1"
    port = env.get("APP_PORT", "8001") or "8001"
    return f"http://{host}:{port}"


def _sink_path() -> Path | None:
    """回归/验证期间的**写盘重定向**（沿用主程序那套保险丝）。

    ★ 为什么这条桥也要守：天机的「创作服务」页会写**另一个文件**
      （MuMuAINovel 的 `backend/.env`）。验证脚本点一下"保存"，
      就会把测试值写进用户真实的服务配置里 —— 和主 `.env` 是同一个病。
      所以：父进程给了 `NWS_ENV_SINK`（或进程内设了 `Config.redirect_save`），
      这里就**不写真实文件**，写进旁边一个 `*.mumu-sink` 里。
    
        English:
    **Disk-write redirection** during regression/verification (reusing the main program's set of
    fuses).
        ★ Why this bridge must also be guarded: Tianji's "Creation Service" page writes to **another file**
          (MuMuAINovel's `backend/.env`). One click of "Save" in the verification script
          will write test values into the user's real service config -- the same disease as the main `.env`.
          So: if the parent process gave `NWS_ENV_SINK` (or `Config.redirect_save` was set in-process),
          then here we **don't write the real file**, we write into an adjacent `*.mumu-sink` instead.
    """
    p = (os.environ.get("NWS_ENV_SINK") or "").strip()
    if p:
        return Path(p).expanduser().with_suffix(".mumu")
    try:
        from config import Config                          # 懒加载：本模块要能独立跑
        # [EN] Lazy loading: this module must be able to run standalone
        if Config.redirect_save is not None:
            return Path(Config.redirect_save).with_suffix(".mumu")
    except Exception:                                      # noqa: BLE001
        pass
    return None


def save_service_env(kv: dict[str, Any]) -> str | None:
    """把若干键写回 MuMuAINovel 的 `backend/.env`（**保留原有注释与未知键**）。

    做法：逐行替换已知键、其余原样保留；表里没有的键追加到末尾的
    「NWS 写入」小节里。写之前留一份 `.env.bak`。
    返回 `None` = 成功，否则是给人看的一句话。
    
        English:
    Write several keys back to MuMuAINovel's `backend/.env` (**preserve the original comments and
    unknown keys**).
        Approach: replace known keys line by line, keep the rest as-is; keys not in the table are appended at the end
        in the "NWS written" section. Keep a `.env.bak` before writing.
        Return `None` = success, otherwise it's a one-liner for humans.
    """
    if not BACKEND_ENV.exists():
        return f"找不到服务配置文件：{BACKEND_ENV}"

    sink = _sink_path()
    target = sink if sink else BACKEND_ENV

    try:
        lines = BACKEND_ENV.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return f"读不了 {BACKEND_ENV.name}：{e!r}"

    want = {k: str(v) for k, v in (kv or {}).items() if k}
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in want:
                out.append(f"{k}={want[k]}")
                seen.add(k)
                continue
        out.append(ln)

    missing = [k for k in want if k not in seen]
    if missing:
        out += ["", "# ── 由天机 ·「创作服务」页写入（NovelWorldSimulator）──"]
        out += [f"{k}={want[k]}" for k in missing]

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not sink and BACKEND_ENV.exists():
            BACKEND_ENV.with_suffix(".env.bak").write_bytes(BACKEND_ENV.read_bytes())
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError as e:
        return f"写不了 {target.name}：{e!r}"
    return None


# ══════════════════════════════════════════════════════════════════
#  服务探活 / 起停
# [EN] Service liveness probe / start-stop
# ══════════════════════════════════════════════════════════════════
#: 只连本机 —— **必须显式禁用代理**，理由见模块头第 3 条。
# [EN] : Connect only to localhost —— **proxy must be explicitly disabled**, see reason in point 3 of
# [EN] the module header.
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def service_status(timeout: float = 1.5) -> BridgeStatus:
    """服务在不在？**永不抛异常**（调用方常在界面线程里问它）。
        English:
    Is the service up? **Never throws an exception** (callers often ask it from the UI thread).
    """
    if not _CLIENT_PY.exists():
        return BridgeStatus(False, "没找到 MuMuAINovel（novelservices 目录被删掉了？）")
    base = service_url()
    try:
        with _NO_PROXY.open(base + "/health", timeout=timeout) as r:
            ok = 200 <= getattr(r, "status", 0) < 300
        return BridgeStatus(ok, "" if ok else f"/health 返回 {r.status}", base)
    except urllib.error.HTTPError as e:
        # 走到这儿说明**真的连上了服务器**，只是它返回了错误码
        # [EN] Reaching here means **actually connected to the server**, it just returned an error code
        return BridgeStatus(False, f"/health 返回 HTTP {e.code}", base)
    except Exception as e:                                   # noqa: BLE001
        return BridgeStatus(False, f"连不上 {base}（{type(e).__name__}）", base)


def _venv_python() -> Path | None:
    """venv 的解释器 —— **Windows 上优先 `pythonw.exe`**。

    ★★★ 2026-10-10：用户报「关闭所有窗口之后 还是会有一个控制台不退出」。
      查到根因是 venv 的 `Scripts/python.exe` **不是解释器本体**，而是
      **_`venvlauncher.exe`**（实测与 `C:\\Python312\\python.exe` 的 md5 不同）：
      它启动时会**再 exec 一次真解释器**作为子进程，而且**不把
      `CREATE_NO_WINDOW` / `DETACHED_PROCESS` 传下去** —— 父进程没有控制台、
      子进程是 console 子系统又没得继承 ⇒ **Windows 给它新分配一个控制台**，
      那个黑窗就留下来了。
      实测（`developers/_probe_launcher_console.py`，同一套标志只换解释器）：
        `python.exe`  → 后代含 **conhost.exe**（黑窗）★
        `pythonw.exe` → 后代只有自己，**没有 conhost**
      ⇒ 这里（以及 `novelservice.start_detached`）一律走 `pythonw.exe`。
      ⚠ 已验证 `pythonw.exe` **不影响 `capture_output`**（stdout/stderr 照样收得到，
        所以下面 `_run_service` 回报的那句人话不会变成空串）。
      ⚠ 非 Windows 平台照旧（`bin/python`，没有这个问题）。
    
        English:
    The venv's interpreter -- **on Windows prefer `pythonw.exe`**.
        ★★★ 2026-10-10: user reported "after closing all windows there's still a console that won't exit".
          Root cause traced to the venv's `Scripts/python.exe` being **not the interpreter itself**, but
          **_`venvlauncher.exe`** (measured md5 differs from `C:\\Python312\\python.exe`):
          on startup it **execs the real interpreter again** as a child process, and **doesn't pass
          `CREATE_NO_WINDOW` / `DETACHED_PROCESS` down** -- the parent has no console,
          the child is a console subsystem with nothing to inherit => **Windows allocates it a new console**,
          and that black window stays behind.
          Measured (`developers/_probe_launcher_console.py`, same set of flags, only the interpreter changed):
            `python.exe`  -> descendants include **conhost.exe** (black window) ★
            `pythonw.exe` -> descendants are only itself, **no conhost**
          => here (and `novelservice.start_detached`) always use `pythonw.exe`.
          ⚠ Verified that `pythonw.exe` **doesn't affect `capture_output`** (stdout/stderr is still received,
            so the human-readable line reported by `_run_service` below won't become an empty string).
          ⚠ Non-Windows platforms unchanged (`bin/python`, no such problem).
    """
    for rel in (("Scripts/pythonw.exe", "Scripts/python.exe", "bin/python")
                if os.name == "nt" else ("bin/python",)):
        p = BACKEND_DIR / ".venv" / rel
        if p.exists():
            return p
    return None


def _emit(on_line, line: str) -> None:
    """把一行输出交给调用方（没有回调就什么都不做，绝不因为它出错而中断）。
        English:
    Hand one line to the caller (no-op without a callback; never let it break the flow).
    """
    if on_line is None:
        return
    try:
        on_line(line)
    except Exception:                                        # noqa: BLE001
        pass


def _run_service(cmd: str, timeout: float = 600.0, on_line=None) -> tuple[bool, str]:
    """跑 `novelservice.py <cmd>`。返回 (成功?, 给人看的一句话)。

    `on_line`（2026-10-17 用户要求：「点了启动/停止要弹个小对话框，显示后台命令的
    全套命令行输出，报错了能马上看到」）：逐行回调 —— **命令行本身**先发一行，
    再把子进程的 stdout + stderr **实时**一行行发出去。

    English:
    Run `novelservice.py <cmd>`. Returns (success?, a one-liner for humans).
    `on_line` (user request, 2026-10-17: "clicking start/stop should pop a small dialog
    showing the full command-line output so I see errors immediately"): per-line callback --
    the **command line itself** is emitted first, then the child's stdout + stderr stream
    out **live**, line by line.
    """
    import threading

    script = BACKEND_DIR / "novelservice.py"
    if not script.exists():
        _emit(on_line, "✘ 没找到 novelservice.py")
        return False, "没找到 novelservice.py"
    py = _venv_python()
    argv = ([str(py)] if py else [sys.executable]) + [str(script), cmd, "--timeout", str(int(timeout))]
    _emit(on_line, "$ " + " ".join(argv))
    # ★ 2026-10-10：Windows 上**必须**带 `CREATE_NO_WINDOW`。
    #   这里跑的是 `python.exe`（控制台子系统程序）—— 如果本进程自己没有控制台
    #   （比如主程序被 pythonw / 快捷方式拉起，或者这段跑在 GUI 线程里），
    #   Windows 会**为子进程分配一个新控制台 ⇒ 用户看到多出一个黑窗**。
    #   用户报的「一启动有 2 个命令行窗口」里，这一句是最可疑的一处。
    # [EN] ★ 2026-10-10: On Windows, `CREATE_NO_WINDOW` is **mandatory**.
    # [EN] What runs here is `python.exe` (a console subsystem program) —— if this process itself has no
    # [EN] console
    # [EN] (e.g. the main program was launched by pythonw / a shortcut, or this code runs on a GUI thread),
    # [EN] Windows will **allocate a new console for the child process ⇒ the user sees an extra black
    # [EN] window**.
    # [EN] Among the "2 command line windows appear on startup" reports from users, this line is the most
    # [EN] suspicious spot.
    _kw: dict = {}
    if os.name == "nt":
        _kw["creationflags"] = 0x08000000              # CREATE_NO_WINDOW
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0                            # SW_HIDE
        _kw["startupinfo"] = _si
    try:
        p = subprocess.Popen(argv, cwd=str(BACKEND_DIR), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace", bufsize=1, **_kw)
    except OSError as e:
        _emit(on_line, f"✘ 起不了子进程：{e!r}")
        return False, f"起不了子进程：{e!r}"

    lines: list[str] = []

    def _pump() -> None:
        try:
            for raw in p.stdout:                       # 逐行读 = 真流式
                ln = raw.rstrip()
                if not ln:
                    continue
                lines.append(ln)
                if len(lines) > 4000:                  # 兜个上限，别把内存吃光
                    del lines[:-4000]
                _emit(on_line, ln)
        except Exception:                              # noqa: BLE001
            pass

    th = threading.Thread(target=_pump, daemon=True)
    th.start()
    try:
        rc = p.wait(timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        p.kill()
        th.join(2.0)
        _emit(on_line, f"✘ {cmd} 超过 {int(timeout)} 秒还没返回（已杀）")
        return False, f"{cmd} 超过 {int(timeout)} 秒还没返回"
    th.join(2.0)
    tail = lines[-3:]
    if rc == 0:
        return True, "；".join(tail)
    return False, "；".join(tail) or f"退出码 {rc}"


def start_service(timeout: float = 600.0, on_line=None) -> tuple[bool, str]:
    """后台拉起服务（幂等：已经在跑就直接成功）。**慢**，别在界面线程里同步调。

    `on_line`：逐行回调（界面用它把命令行输出实时显示出来，见 `_run_service`）。
        English:
    Launch the service in the background (idempotent: if already running, just succeed). **Slow**,
    don't call it synchronously on the UI thread.
    `on_line`: per-line callback (the UI uses it to show the command output live; see `_run_service`).
    """
    return _run_service("start", timeout, on_line=on_line)


def stop_service(on_line=None) -> tuple[bool, str]:
    return _run_service("stop", timeout=60.0, on_line=on_line)


def stop_service_detached() -> bool:
    """**不等结果**地把创作服务停掉 —— 专供"关窗口那一刻"用。

    ★★ 为什么不复用 `stop_service()`：它是同步等的（`subprocess.run`，最坏 60 秒）。
      而它要出现的那个时刻是 `on_disconnect`：事件循环随时会停，
      `util.flet_shutdown.arm_exit_watchdog` 5 秒后就直接 `os._exit` ——
      **等不到它跑完**。所以这里把子进程**甩出去**：
      Windows 用 `DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW`，
      Unix 用 `start_new_session`，让它**活过我们自己**，于是"不等"不影响它把活干完。

    ★ 为什么程序自己也要来一刀（明明 `start.exe` 退出时已经收尸了）：
      那条路只在"双击启动器"时成立。开发时直接跑 `main_gui.py`、
      或者从 IDE 里跑，都不经过启动器 —— 那时只有这一刀。
      两刀都读同一个开关（`MUMU_FOLLOW_APP`）、都是幂等的
      （`novelservice.py stop` 对"没在跑"返回 0），所以重复调用无害。

    返回 True 表示"子进程起来了"（**不代表**服务已经停了）。
    
        English:
    **Stop the creation service without waiting for the result** — specifically for the moment "the
    window is closed".
        ★★ Why not reuse `stop_service()`: it waits synchronously (`subprocess.run`, worst case 60 seconds).
          But the moment it needs to appear is `on_disconnect`: the event loop may stop at any time,
          and `util.flet_shutdown.arm_exit_watchdog` will directly `os._exit` after 5 seconds —
          **it won't wait for it to finish**. So here we **throw** the child process out:
          On Windows use `DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW`,
          On Unix use `start_new_session`, so it **outlives us**, and thus "not waiting" doesn't affect it finishing the job.
        ★ Why the program itself also needs to do a cut (even though `start.exe` already reaps on exit):
          That path only holds when "double-clicking the launcher". During development, running `main_gui.py` directly,
          or running from the IDE, doesn't go through the launcher — at that time only this one cut exists.
          Both cuts read the same switch (`MUMU_FOLLOW_APP`), both are idempotent
          (`novelservice.py stop` returns 0 for "not running"), so repeated calls are harmless.
        Returning True means "the child process started" (**does not mean** the service has stopped).
    """
    # ★ 2026-10-28：「怎么甩」抽到 `_detach.run_detached`（三家桥共用一份）。
    #   原来这一段（creationflags / STARTUPINFO / 失败退回不带 breakaway）是**抄**
    #   在别处的同一件事 —— PenShot 与 PlotPilot 也要"甩出去停"时就会变成第二份。
    # [EN] ★ 2026-10-28: "how to throw" moved to `_detach.run_detached` (one copy
    # [EN] shared by all three bridges). This block (creationflags / STARTUPINFO /
    # [EN] retry without breakaway) was the same thing duplicated elsewhere -- it
    # [EN] would have become a second copy as soon as PenShot and PlotPilot needed it.
    try:                                    # 包导入（主程序：`from novelservices import mumu_bridge`）
        from ._detach import run_detached   # [EN] package import (the app)
    except ImportError:                     # noqa: BLE001
        from _detach import run_detached    # 顶层导入（`service_ctl` 把本目录塞进 `sys.path` 后 import）
                                            # [EN] top-level import (`service_ctl` puts this dir on `sys.path`)
    script = BACKEND_DIR / "novelservice.py"
    if not script.exists():
        return False
    py = _venv_python()
    argv = ([str(py)] if py else [sys.executable]) + [str(script), "stop"]
    return run_detached(argv, cwd=str(BACKEND_DIR))


# ══════════════════════════════════════════════════════════════════
#  客户端（按文件路径加载，不污染 sys.path）
# [EN] Client (loaded by file path, does not pollute sys.path)
# ══════════════════════════════════════════════════════════════════
_CLIENT_CLS: Any = None


def _client_class():
    """加载 `MuMuAINovel/mumu_client.py` 里的 `MuMuClient`。

    ★ **按文件路径加载**（不是 `sys.path.insert` + `import mumu_client`）：
      后者会把 `MuMuAINovel/` 塞进全局搜索路径，那儿还躺着一个同名的
      `nws_paths.py`（跟本目录的 `novelservices/` 之下同名），迟早撞上。
      按路径加载还会**顺带把模块缓存加锁** —— 每拍都调也只加载一次。
    
        English:
    Load `MuMuClient` from `MuMuAINovel/mumu_client.py`.
        ★ **Load by file path** (not `sys.path.insert` + `import mumu_client`):
          The latter would stuff `MuMuAINovel/` into the global search path, where there also lies a same-named
          `nws_paths.py` (same name as under `novelservices/` in this directory), and sooner or later they'll collide.
          Loading by path also **incidentally locks the module cache** — called every beat it still only loads once.
    """
    global _CLIENT_CLS
    if _CLIENT_CLS is not None:
        return _CLIENT_CLS
    import importlib.util
    spec = importlib.util.spec_from_file_location("nws_mumu_client", _CLIENT_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了客户端：{_CLIENT_PY}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _CLIENT_CLS = mod.MuMuClient
    return _CLIENT_CLS


def _client():
    cls = _client_class()
    c = cls.from_env(BACKEND_ENV, base_url=service_url())
    c.timeout = 300.0                     # 长任务别用默认 120 秒
    # [EN] Don't use the default 120 seconds for long tasks
    c.login()
    return c


# ══════════════════════════════════════════════════════════════════
#  NWS 书 ↔ MuMuAINovel 项目 的映射
# [EN] Mapping between NWS book ↔ MuMuAINovel project
# ══════════════════════════════════════════════════════════════════
#  ⚠ **这里有个必须记住的坑**：映射**不能只靠"有没有传 novel_dir"**。
#    第一版写成"novel_dir 为 None 就当作没有缓存" —— 后果是
#    **每调一次就新建一个 MuMuAINovel 项目**（一天一个项目），
#    而且它不会报错：生成照样成功，只是库里堆垃圾、章节永远是第 1 章。
#    所以 `novel_dir` 缺席时改用一个**全局的按键映射文件**兜底。
# [EN] ⚠ **There is a pitfall here that must be remembered**: the mapping **must not rely only on
# [EN] "whether novel_dir was passed"**.
# [EN] The first version was written as "if novel_dir is None, treat it as having no cache" —— the
# [EN] consequence is
# [EN] **a new MuMuAINovel project is created on every call** (one project per day),
# [EN] and it won't error out: generation still succeeds, just that garbage piles up in the DB and the
# [EN] chapter is always chapter 1.
# [EN] So when `novel_dir` is absent, fall back to a **global keyed mapping file**.
_NULL_MAP = MUMU_DIR / ".nws_projects.json"


def _map_file(novel_dir: Path | None) -> Path:
    """这本书的映射文件放哪。

    给了 `novel_dir` → 放**那本书自己的目录**里（书搬走，映射跟着走）；
    没给 → 放工具链目录下的全局表（按键索引）。
    
        English:
    Where to put this book's mapping file.
        If `novel_dir` is given → put it in **that book's own directory** (if the book moves, the mapping moves with it);
        if not given → put it in the global table under the toolchain directory (keyed by index).
    """
    return (Path(novel_dir) / _MAP_NAME) if novel_dir else _NULL_MAP


def _load_map(novel_dir: Path | None, key: str = "") -> dict[str, Any]:
    p = _map_file(novel_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}
    if novel_dir:
        return data
    # 全局表：`{书名: {...}}`
    # [EN] Global table: `{book name: {...}}`
    row = data.get(str(key or ""))
    return dict(row) if isinstance(row, dict) else {}


def _save_map(novel_dir: Path | None, key: str, row: dict[str, Any]) -> None:
    p = _map_file(novel_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if novel_dir:
            payload: Any = row
        else:
            try:
                all_rows = json.loads(p.read_text(encoding="utf-8")) or {}
            except (OSError, ValueError):
                all_rows = {}
            if not isinstance(all_rows, dict):
                all_rows = {}
            all_rows[str(key or "")] = row
            payload = all_rows
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    except OSError:
        pass                              # 缓存写不了不算错，下次重建就是
        # [EN] Failure to write the cache is not an error, it'll just be rebuilt next time


def forget_project(novel_dir: Path | None, key: str = "") -> None:
    """忘掉映射（服务端把项目删了、或想重新建一个时用）。
        English:
    Forget the mapping (used when the server deleted the project, or when you want to rebuild one).
    """
    p = _map_file(novel_dir)
    if not p.exists():
        return
    try:
        if novel_dir:
            p.unlink()
        else:
            data = json.loads(p.read_text(encoding="utf-8")) or {}
            data.pop(str(key or ""), None)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    except (OSError, ValueError):
        pass


def ensure_project(task: ChapterTask, c=None) -> tuple[str, str]:
    """找到（或建好）这本书在 MuMuAINovel 里的项目。返回 `(project_id, 错误)`。

    ⚠ **用 `one-to-many` 模式**：`one-to-one` 模式下"建大纲会自动建章节"，
      我们再手动 `create_chapter()` 就成了同一章两行 —— 空的那行会被拿去生成、
      分析空正文必然失败、然后**整批中断**（实测踩过）。
      `one-to-many` 不会自动建章节，两边都由我们显式控制，也不怕重跑。
    
        English:
    Find (or create) this book's project in MuMuAINovel. Returns `(project_id, error)`.
        ⚠ **Use `one-to-many` mode**: in `one-to-one` mode "creating an outline automatically creates chapters",
          and if we then manually `create_chapter()` the same chapter becomes two rows — the empty row will be used for generation,
          analyzing empty body text is bound to fail, and then **the whole batch aborts** (actually hit this in practice).
          `one-to-many` doesn't auto-create chapters, both sides are explicitly controlled by us, and re-runs are safe.
    """
    c = c or _client()
    key = task.project_key or "未命名"
    cache = _load_map(task.novel_dir, key)
    pid = str(cache.get("project_id") or "").strip()
    if pid:
        try:
            c.get_project(pid)
            return pid, ""
        except Exception:                              # noqa: BLE001
            forget_project(task.novel_dir, key)        # 项目没了 → 重建
            # [EN] Project gone → rebuild

    try:
        proj = c.create_project(
            title=f"{key}（NWS 剧组）",
            description="由 NovelWorldSimulator 剧组的小说作家调用；"
                        "逐日写入细纲、逐日取回正文。",
            genre=task.genre or "",
            outline_mode="one-to-many",
        )
    except Exception as e:                             # noqa: BLE001
        return "", f"建项目失败：{e!r}"
    pid = str(proj.get("id") or "")
    if not pid:
        return "", "建项目返回里没有 id"
    cache["project_id"] = pid
    cache["title"] = key
    cache["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_map(task.novel_dir, key, cache)
    return pid, ""


# ══════════════════════════════════════════════════════════════════
#  主入口：写一章
# [EN] Main entry: write a chapter
# ══════════════════════════════════════════════════════════════════
def generate_chapter(task: ChapterTask, c=None) -> BridgeResult:
    """把一件事交给 MuMuAINovel：**按这份细纲写一章，把正文还回来**。

    流程（每一步只要不对就**立刻返回失败**，不硬撑）：

        ① 服务在不在 → 不在就请调用方回退
        ② 找到/建好项目
        ③ 建**大纲**（`structure.summary` = 细纲全文 —— 不给它，细纲一个字都进不去）
        ④ 建**章节**（显式绑 `outline_id`，不靠序号猜）
        ⑤ 批量生成这一章 → 等完成
        ⑥ 读回正文，清掉模型爱加的"第X章 标题"之类元信息

    返回的 `BridgeResult.ok=False` 全部是**可回退**的失败 —— 调用方应当
    退回自己写，而不是把这一天的戏弄丢。
    
        English:
    Hand one task to MuMuAINovel: **write one chapter per this detailed outline, and return the body
    text**.
        Flow (each step **returns failure immediately** if anything is wrong, no forcing through):
            ① Is the service up → if not, ask the caller to fall back
            ② Find/create the project
            ③ Create the **outline** (`structure.summary` = full detailed outline text — without giving it, not a single character of the outline gets in)
            ④ Create the **chapter** (explicitly bind `outline_id`, don't guess by sequence number)
            ⑤ Batch-generate this chapter → wait for completion
            ⑥ Read back the body text, strip out meta-info like "Chapter X Title" that the model loves to add
        All `BridgeResult.ok=False` returned are **fallback-able** failures — the caller should
        fall back to writing it themselves, rather than losing a day's drama.
    """
    t0 = time.time()

    def _fail(msg: str) -> BridgeResult:
        return BridgeResult(False, reason=msg, elapsed=time.time() - t0)

    if not task.outline.strip():
        return _fail("细纲是空的 —— 没有细纲，写出来的必然是跑题的第一稿")

    st = service_status()
    if not st.ok:
        return _fail(f"写小说服务没在跑：{st.reason}")

    try:
        c = c or _client()
    except Exception as e:                                 # noqa: BLE001
        return _fail(f"连不上服务：{e!r}")

    pid, err = ensure_project(task, c)
    if err:
        return _fail(err)

    # ── 找下一个章号（接在已有章节后面，让它有"前文"可续）──
    # [EN] ── Find the next chapter number (append after existing chapters, so it has "preceding text" to
    # [EN] continue from) ──
    try:
        chs = list(c.list_chapters(pid) or [])
    except Exception as e:                                 # noqa: BLE001
        return _fail(f"读章节列表失败：{e!r}")
    # ★★★ 2026-10-21：**上一章是空壳 ⇒ 复用它，别往后加**。
    #   实测：前一次导出时服务端写完正文、分析那步崩掉，整批标 failed，
    #   但**章节记录留在库里且正文是空的**。下一次导出按"最大章号 + 1"去建第 3 章，
    #   服务端直接 400：「起始章节无法生成：需要先完成前置章节：第 2 章」——
    #   一个空壳把后面所有导出全堵死，而用户看到的只是"外部服务回退了"。
    #   ⇒ 找到"最后一章 + 正文为空"就把那一章交给它重写（章号不前进）。
    #   ⚠ 只复用**紧接着的最后一章**：中间的空章说明前面就断了，硬跳过去会让上下文错位。
    # [EN] ★★★ 2026-10-21: **if the previous chapter is an empty shell, reuse it, don't append**.
    # [EN] Measured: on a previous export the service wrote the body but crashed in analysis, marking
    # [EN] the batch failed -- yet the chapter row stayed in the DB with empty content. The next
    # [EN] export computed "max chapter number + 1" and tried chapter 3; the service returned 400:
    # [EN] "cannot start: chapter 2 must be completed first". One shell blocked every later export,
    # [EN] and all the user saw was "the external service fell back".
    # [EN] => If the last chapter has an empty body, hand that number back for a rewrite (do not
    # [EN] advance). ⚠ Only the immediately last chapter: an empty chapter in the middle means the
    # [EN] chain broke earlier, and jumping over it would misalign the context.
    number = max([int(x.get("chapter_number") or 0) for x in chs] or [0]) + 1
    if chs:
        try:
            # ⚠ 要往前扫**一整段**空壳，不能只看最后一章：失败一次可能留下 2、3 两章空壳，
            #   只看最后一章会去复用第 3 章，而服务端仍报"需要先完成第 2 章"（实测如此）。
            #   取"末尾连续空章节"里**最小**的那个章号，从那里往下写。
            # [EN] ⚠ Scan a whole run of empty shells, not just the last one: one failure can leave
            # [EN] both chapters 2 and 3 empty, and reusing only chapter 3 still gets "chapter 2 must
            # [EN] be completed first" (measured). Take the **smallest** number in the trailing run
            # [EN] of empty chapters and write from there.
            empties = trailing_empty_numbers(
                chs, lambda cid: (c.get_chapter(cid) or {}).get("content") or "")
            if empties:
                number = min(empties)
                _LOG.warning("末尾连续 %d 章正文是空的（%s，上次失败留下的壳）→ "
                             "从第 %d 章重写，不往后加新章",
                             len(empties), sorted(empties), number)
        except Exception as e:                             # noqa: BLE001
            _LOG.debug("检查末尾空壳时出错（照旧往后加）：%r", e)

    # ── ③ 大纲：细纲必须写进 `structure["summary"]` ──
    #    为什么：`chapter_context_service` 里 `if outline.structure:` 一旦成立，
    #    `outline.content` 就**被整个丢弃**（只从 structure 取 summary/scenes/…）。
    #    实测判据是日志里 `P0-大纲信息` 的字符数：给 structure 却漏 summary → 175 字符
    #    （细纲全丢）；给 summary → 1477 字符（两边都要到）。
    # [EN] ── ③ Outline: the detailed outline must be written into `structure["summary"]` ──
    # [EN] Why: in `chapter_context_service`, once `if outline.structure:` holds,
    # [EN] `outline.content` is **entirely discarded** (summary/scenes/… are only taken from structure).
    # [EN] The empirical criterion is the character count of `P0-大纲信息` in the log: passing structure but
    # [EN] omitting summary → 175 chars
    # [EN] (the whole detailed outline lost); passing summary → 1477 chars (both sides need it).
    structure: dict[str, Any] = {"summary": task.outline.strip()}
    if task.characters:
        structure["characters"] = list(task.characters)
    try:
        outline = c.create_outline(
            pid, task.title or f"第 {number} 天", task.outline.strip(),
            order_index=number,
            structure=structure,
        )
    except Exception as e:                                 # noqa: BLE001
        return _fail(f"建大纲失败：{e!r}")
    outline_id = str((outline or {}).get("id") or "")

    # ── ④ 章节（显式绑 outline_id，避免"按序号猜"猜错）──
    # [EN] ── ④ Chapter (explicitly bind outline_id, avoiding wrong guesses by "guessing by index") ──
    try:
        c.create_chapter(pid, task.title or f"第 {number} 天", number,
                         outline_id=outline_id or None)
    except Exception as e:                                 # noqa: BLE001
        return _fail(f"建章节失败：{e!r}")

    # ── ⑤ 生成 ──
    # [EN] ── ⑤ Generate ──
    #: 空章换模型重试过了没有（只重试一次，见下面那段）
    # [EN] : whether the empty-chapter model retry has been used (once only, see below)
    _retried = False
    kwargs: dict[str, Any] = {
        "start_chapter_number": number,
        "count": 1,
        "target_word_count": int(task.target_words or 2500),
        "enable_analysis": bool(task.enable_analysis),
    }
    if task.style_id:
        kwargs["style_id"] = int(task.style_id)
    if task.model:
        kwargs["model"] = task.model
    if task.perspective:
        kwargs["narrative_perspective"] = task.perspective
    if task.skill_key:
        kwargs["skill_key"] = task.skill_key
    try:
        batch = c.batch_generate(pid, **kwargs)
        bid = str(batch.get("batch_id") or "")
        if not bid:
            return _fail("批量生成没返回 batch_id")
        final = c.wait_batch(bid, timeout=task.timeout, interval=4.0)
    except Exception as e:                                 # noqa: BLE001
        # ★★★ 2026-10-21：**批次被判失败，不等于这一章没写出来**。
        #   实测（mwl_v5）：服务端写完第 2 章正文之后跑"章节分析"，分析那一步
        #   报「章节不存在或内容为空」→ 整批标 `failed`，而**正文其实已经落库**。
        #   以前这里直接 `return _fail(...)`，等于把写好的稿子丢掉、回退到内部稿 ——
        #   用户看到的就是"外部服务好像没用上"。
        #   ⇒ 现在不在这里放弃：继续往下走「读回正文」，读到了就用。
        #   ⚠ 这也是本项目的核心教训之一：**"全有或全无"的验收要换成"拿到多少算多少"**。
        # [EN] ★★★ 2026-10-21: **a batch marked failed does not mean this chapter wasn't written**.
        # [EN] Measured (mwl_v5): after writing chapter 2 the service runs "chapter analysis", which
        # [EN] reported "chapter missing or empty" -> the whole batch was marked `failed`, while the
        # [EN] **body text had already been persisted**. Previously this did `return _fail(...)`,
        # [EN] throwing away a finished draft and falling back to the in-house one -- which is exactly
        # [EN] why it looked like "the external service never got used".
        # [EN] => Do not give up here: continue to "read back the body" and use it if present.
        # [EN] ⚠ Also a core lesson of this project: **replace all-or-nothing acceptance with
        # [EN] "keep whatever you got"**.
        _LOG.warning("批量任务没正常收尾（%r）→ 继续试着读回正文（分析失败不等于没写出来）", e)
        final = {}

    failed = final.get("failed_chapters") or []
    if failed:
        _LOG.warning("这一章被标记失败（%s）→ 先看正文在不在，别急着丢", str(failed)[:160])

    # ── ⑥ 读回正文 ──
    # [EN] ── ⑥ Read back the body text ──
    try:
        row = next((x for x in c.list_chapters(pid)
                    if int(x.get("chapter_number") or 0) == number), None)
        if row is None:
            return _fail("生成完了但找不到这一章")
        full = c.get_chapter(row["id"])
        text = str(full.get("content") or "")
    except Exception as e:                                 # noqa: BLE001
        return _fail(f"读回正文失败：{e!r}")

    text = _strip_meta(text)
    if len(text) < 50:
        # ★ 空章/近空章是推理模型的**偶发**失败（实测最坏一次思考 22876 字符、
        #   正文 0 字）。当场不报错的话，上游会拿到一个"这一天没写东西"的结果。
        # [EN] ★ Empty chapter/near-empty chapter is an **occasional** failure of reasoning models (worst
        # [EN] observed once: 22876 chars of thinking,
        # [EN] 0 chars of body text). If not reported on the spot, upstream will get a result of "nothing was
        # [EN] written this day".
        # ★★★ 2026-10-21：**空章先换"不思考的模型"重试一次**，别直接判死。
        #   实测（mwl_v5）：服务端日志是
        #     `流式响应结束但正文为空: model=deepseek-v4-pro reasoning_chars=6347
        #      finish_reason=length` —— 4500 个输出 token **全烧在思考上**，
        #      正文 0 字。这不是"服务坏了"，是**选了个会思考的模型 + 输出预算按字数算**。
        #   ⇒ 用 `MUMU_ANALYSIS_MODEL`（默认 deepseek-chat，不思考）再跑一次；
        #     还是空才认失败。这样"优先外部服务"才真能保住，而不是一遇推理模型就回退。
        #   ⚠ 只重试一次：真写不出来（服务/额度问题）重试十次也一样，还白等。
        # [EN] ★★★ 2026-10-21: **on an empty chapter, retry once with a "non-thinking" model**; do
        # [EN] not declare death yet. Measured (mwl_v5), the service log reads "stream ended but body
        # [EN] empty: model=deepseek-v4-pro reasoning_chars=6347 finish_reason=length" -- all 4500
        # [EN] output tokens burned on thinking, 0 characters of prose. That is not "the service is
        # [EN] broken", it is **a thinking model plus an output budget sized by word count**.
        # [EN] => Retry once with `MUMU_ANALYSIS_MODEL` (default deepseek-chat, no thinking); only
        # [EN] accept failure if still empty. That is what makes "prefer the external service" real
        # [EN] instead of falling back the moment a reasoning model shows up.
        # [EN] ⚠ Retry once only: if it genuinely cannot write (service/quota), ten retries are the
        # [EN] same and just waste time.
        if not _retried:
            _LOG.warning("拿回来的正文只有 %d 字（推理模型把预算烧在思考上了）→ "
                         "换不思考的模型重试一次", len(text))
            try:
                c.update_chapter_status(row["id"], 'pending')
            except Exception:                              # noqa: BLE001
                pass
            _retried = True
            kw2 = dict(kwargs)
            kw2["model"] = _plain_model()
            try:
                batch2 = c.batch_generate(pid, **kw2)
                bid2 = str(batch2.get("batch_id") or "")
                if bid2:
                    try:
                        c.wait_batch(bid2, timeout=task.timeout, interval=4.0)
                    except Exception as e:                 # noqa: BLE001
                        _LOG.warning("重试批次没正常收尾（%r）→ 仍试着读回正文", e)
                    row2 = next((x for x in c.list_chapters(pid)
                                 if int(x.get("chapter_number") or 0) == number), None)
                    if row2 is not None:
                        text2 = str((c.get_chapter(row2["id"]) or {}).get("content") or "")
                        text2 = _strip_meta(text2)
                        if len(text2) >= 50:
                            return BridgeResult(True, text=text2, chapter_number=number,
                                                elapsed=time.time() - t0,
                                                raw={"batch_id": bid2, "retried": True})
            except Exception as e:                         # noqa: BLE001
                _LOG.warning("换模型重试失败：%r", e)
        return _fail(f"拿回来的正文只有 {len(text)} 字（疑似空章）")

    return BridgeResult(True, text=text, chapter_number=number,
                        elapsed=time.time() - t0,
                        raw={"batch_id": bid, "status": final.get("status")})


def polish(text: str, *, model: str = "", temperature: float | None = None,
           timeout: float = 300.0) -> BridgeResult:
    """**去 AI 味**：把一段正文交给 MuMuAINovel 改写，拿回改写后的文本。

    ── ⚠ 当前状态：**上游这条链没接完，还不可用**（2026-10-09 实测）──────
    两处都是上游自己缺的，不是我们接错：

    1. 路由**没挂**。`backend/app/api/polish.py` 写好了，但 `app/main.py` 里
       `grep polish` 零命中 —— 请求返回 `HTTP 404 {"detail":"Not Found"}`。
       这一处**我们已经补上**（main.py 里那两行，标了 NWS 补丁）。
    2. 提示词模板 `AI_DENOISING` **全仓不存在**。`polish.py` 里
       `PromptService.get_template("AI_DENOISING", ...)` 是全项目唯一出现它的地方，
       取不到就是 `None` → 挂上路由后报
       `HTTP 500 AI去味失败: 'NoneType' object has no attribute 'format'`。

    ⇒ 所以这个方法**现在调必然失败**（失败原因会说清是 500 还是 404）。
      要启用它，还差**写一份 `AI_DENOISING` 提示词模板**（上游没给），
      属于"替上游补功能"，该单独一次做。在此之前不要把它接进任何 Agent。

    ── 就算补好了，用之前也要想清楚（这是设计冲突，不是实现问题）──────
    · 它是**整段进、整段出**，不做分句对齐 —— 拿回的长度与原文不会逐句对应，
      只能整段替换。
    · 本项目对"改稿"的既定做法是**编辑对**（只改点出来的那几处，见 `quality/edit_ops.py`
      与那条 LaserTagger 的来历）：模型能改的只有它点出来的地方，想"顺手润色"没有出口。
      而这里是**放开让它重写全文**。两者是相反的哲学。
      → 真要用，只适合"**整章终稿去味**"这一个场景，不能用在"逐处定点修订"里。
    
        English:
    **De-AI-ify**: hand a passage of body text to MuMuAINovel for rewriting, get back the rewritten
    text.
        ── ⚠ Current status: **the upstream chain isn't fully wired, not usable yet** (measured 2026-10-09) ──────
        Both spots are missing upstream, not us wiring it wrong:
        1. The route **isn't mounted**. `backend/app/api/polish.py` is written, but in `app/main.py`
           `grep polish` has zero hits — the request returns `HTTP 404 {"detail":"Not Found"}`.
           This spot **we've already patched** (those two lines in main.py, marked NWS patch).
        2. The prompt template `AI_DENOISING` **doesn't exist in the whole repo**. In `polish.py`,
           `PromptService.get_template("AI_DENOISING", ...)` is the only place in the entire project it appears;
           if it can't be fetched it's `None` → after mounting the route it reports
           `HTTP 500 AI去味失败: 'NoneType' object has no attribute 'format'`.
        ⇒ So this method **will necessarily fail if called now** (the failure reason will say clearly whether it's 500 or 404).
          To enable it, there's still **a `AI_DENOISING` prompt template to write** (upstream didn't provide it),
          which belongs to "patching features for upstream", and should be done as a separate task. Don't wire it into any Agent before then.
        ── Even if patched, think it through before using (this is a design conflict, not an implementation problem) ──────
        · It's **whole-passage in, whole-passage out**, no sentence splitting/alignment — the returned length won't correspond sentence-by-sentence with the original,
          Can only be replaced as a whole paragraph.
        · This project's established approach to "revision" is the **edit pair** (only change the specific spots that were pointed out, see `quality/edit_ops.py`
          and the origin of that LaserTagger): what the model can change is only the places it points out; there is no outlet for "incidental polishing".
          Whereas here it is **unleashed to rewrite the entire text**. The two are opposite philosophies.
          → If actually used, it only suits the single scenario of "**de-flavoring the final draft of a whole chapter**", and cannot be used in "point-by-point targeted revision".
    """
    t0 = time.time()

    def _fail(msg: str) -> BridgeResult:
        return BridgeResult(False, reason=msg, elapsed=time.time() - t0)

    src = str(text or "").strip()
    if not src:
        return _fail("原文是空的")
    st = service_status()
    if not st.ok:
        return _fail(f"写小说服务没在跑：{st.reason}")
    try:
        c = _client()
        out = c.polish_text(src, model=model or None, temperature=temperature)
    except Exception as e:                                 # noqa: BLE001
        return _fail(f"去味调用失败：{e!r}")
    out = _strip_meta(out)
    if not out:
        return _fail("去味返回是空的（模型可能把预算烧在思考上了）")
    return BridgeResult(True, text=out, elapsed=time.time() - t0,
                        raw={"before": len(src), "after": len(out)})


def list_skills() -> list[str]:
    """MuMuAINovel 自带技能的名字（服务不在就返回空表）。
        English:
    Names of MuMuAINovel's built-in skills (returns an empty table if the service is not available).
    """
    st = service_status()
    if not st.ok:
        return []
    try:
        rows = _client().list_skills()
    except Exception:                                      # noqa: BLE001
        return []
    out: list[str] = []
    for r in rows or []:
        if isinstance(r, dict):
            k = str(r.get("key") or r.get("name") or r.get("skill_key") or "").strip()
            if k:
                out.append(k)
        elif isinstance(r, str):
            out.append(r)
    return sorted(set(out))


def trailing_empty_numbers(chapters: list[dict], fetch_body) -> list[int]:
    """**末尾连续空章节**的章号（从小到大）。空表 = 最后一章有正文。

    为什么要单独一个函数（2026-10-21）：判据要能测**行为**。
    这段逻辑原来写在 `generate_chapter` 里，只能用"源码里有没有这个字符串"当判据 ——
    而把 `if empties:` 改成 `if False:` 之后字符串还在，判据照样绿（反例法当场戳穿）。
    抽出来之后拿一份假章节表跑一遍就知道有没有生效。

    用法：`fetch_body(chapter_id) -> str`（注入，方便测试）。
    
        English:
    Chapter numbers of the **trailing run of empty chapters** (ascending). Empty = last one has text.
        Why a separate function (2026-10-21): criteria must test **behaviour**. This logic used to
        live inside `generate_chapter`, where the only available criterion was "does the source
        contain this string" -- and after changing `if empties:` to `if False:` the string remains,
        so the criterion stayed green (the counterexample method caught it on the spot). Extracted, a
        fake chapter table shows immediately whether it works.
        Usage: `fetch_body(chapter_id) -> str` (injected for testability).
    """
    out: list[int] = []
    try:
        ordered = sorted(chapters or [], key=lambda x: int(x.get("chapter_number") or 0))
    except Exception:                                        # noqa: BLE001
        return out
    for row in reversed(ordered):
        try:
            no = int(row.get("chapter_number") or 0)
            body = str(fetch_body(row["id"]) or "")
        except Exception:                                    # noqa: BLE001
            break
        if no <= 0 or body.strip():
            break
        out.append(no)
    return out


def _plain_model() -> str:
    """**不思考**的模型名（空章重试用）。

    优先 `MUMU_ANALYSIS_MODEL`（配置文件里本来就推荐它指到一个不思考的模型），
    留空就退回 `deepseek-chat` —— 这条经验在 MEMORY 里写过很久
    （"推理模型会把输出预算烧在思考上，实测最坏一次想 22876 字符、正文 0 字"），
    只是以前只用在"章节分析"上，现在**正文空章**也要用它兜底。

        English:
    The name of a **non-thinking** model (for the empty-chapter retry).
        Prefer `MUMU_ANALYSIS_MODEL` (the config already recommends pointing it at a non-thinking
        model); when empty, fall back to `deepseek-chat` -- this lesson has long been recorded in
        MEMORY ("a reasoning model burns the output budget on thinking; worst observed once: 22876
        characters of reasoning, 0 characters of prose"), it was just only applied to "chapter
        analysis" before; now an **empty body chapter** needs the same safety net.
    """
    try:
        env = read_service_env()
        m = str(env.get("MUMU_ANALYSIS_MODEL") or "").strip()
    except Exception:                                        # noqa: BLE001
        m = ""
    return m or "deepseek-chat"


def _strip_meta(text: str) -> str:
    """去掉模型爱加的『第X章 标题』『（本章完）』之类元信息。

    与 `MuMuAINovel/mumu_client.strip_meta` 同一套规则 —— 这里**重写一份**
    而不是 import：那个模块是给"带 venv 的那一边"用的，这个桥要能在
    主程序的解释器里独立跑（模块头第 2 条）。
    
        English:
    Strip meta-information like "第X章 标题" and "(本章完)" that the model likes to add.
        Same set of rules as `MuMuAINovel/mumu_client.strip_meta` —— here it is **rewritten as a copy**
        rather than imported: that module is for "the side with the venv", while this bridge needs to be able to
        run independently in the main program's interpreter (item 2 of the module header).
    """
    import re
    t = re.sub(r"^\s*#{1,6}?\s*", "", str(text or ""))
    t = re.sub(r"^\s*第[零一二三四五六七八九十百\d]+章[^\n]*\n+", "", t)
    t = re.sub(r"\n+\s*[（(]\s*本章完\s*[)）]\s*$", "", t)
    return t.strip()


def describe() -> str:
    st = service_status()
    return (f"MUMU_DIR    = {MUMU_DIR}\n"
            f"BACKEND_ENV = {BACKEND_ENV}\n"
            f"服务地址     = {service_url()}\n"
            f"服务状态     = {'在跑' if st.ok else '不在跑'} {st.reason}\n"
            f"上游         = {UPSTREAM}")


if __name__ == "__main__":
    print(describe())
