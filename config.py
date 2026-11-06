# -*- coding: utf-8 -*-
"""配置中心：.env 读取 / 校验 / 写回。
English:
Config center: .env read / validate / write-back.
"""
from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
ENV_PATH = APP_DIR / ".env"
ENV_EXAMPLE_PATH = APP_DIR / ".env.example"
VERSION = "0.3.3"


def env_sink_path() -> "Path | None":
    """回归器给子进程设的**写盘重定向**（环境变量 `NWS_ENV_SINK`）。

    ★★ 为什么要有它（2026-10-06，做并行回归时第 5 次栽在同一个坑上）：

    有些验证脚本会设一堆测试值（`CFG.set('MOCK_LLM','true')`、把
    `DEFAULT_PROJECTS_DIR` 指到临时目录、`BEAT_SECONDS=2`…），然后在
    **点「开始推演」/ 跑真机段**时触发 `CFG.save()`，把这些值写进**用户的 `.env`**。
    这些年陆续加过三道防线：备份/还原、`VU.env_guard()`、`Config.redirect_save`。
    但**只要漏一个脚本**、或者"还原晚了半步"，用户的真实配置就没了。

    并行回归把这件事从"偶发"变成了"必然"：多个脚本同时跑时，
    A 脚本的 `save()` 可能落在 B 脚本**备份与还原之间** ——
    于是 B 还原回来的干净内容又被 A 覆盖掉。实测就是这么中招的：
    并行跑完整套之后 `.env` 里躺着 `MOCK_LLM=true`、
    `DEFAULT_PROJECTS_DIR=<某个脚本的临时目录>`、`BEAT_SECONDS=2`。

    所以**别再用"记得还原"这种约定**（本项目铁律：会写用户文件的路径，
    默认就该写不进去）。回归器给每个子进程设 `NWS_ENV_SINK`，
    指向一个临时文件 —— 子进程怎么 `save()` 都写不到真实 `.env`。

    ⚠ 与 `Config.redirect_save` 的关系：那个是**进程内**的保险丝（脚本自己设），
    这个是**进程外**的（父进程给子进程设）。两者取其一即可，互不冲突。
    ⚠ 用户正常跑程序时**不会有这个环境变量**，所以对产品行为零影响。
    
        English:
    The **write redirection** set by the regressor for child processes (env var `NWS_ENV_SINK`).
        ★★ Why it's needed (2026-10-06, fell into the same pit the 5th time when doing parallel regression):
        Some verification scripts set a bunch of test values (`CFG.set('MOCK_LLM','true')`, point
        `DEFAULT_PROJECTS_DIR` at a temp directory, `BEAT_SECONDS=2`…), then when
        **clicking "Start deduction" / running the real-machine segment** trigger `CFG.save()`, writing these values into **the user's `.env`**.
        Over the years three lines of defense were added one after another: backup/restore, `VU.env_guard()`, `Config.redirect_save`.
        But **as long as one script is missed**, or "restore happens half a step late", the user's real config is gone.
        Parallel regression turned this from "occasional" into "inevitable": when multiple scripts run at the same time,
        script A's `save()` may land **between script B's backup and restore** ——
        so the clean content restored by B gets overwritten by A again. This is exactly how it got hit in real testing:
        after running the full parallel suite, `.env` contains `MOCK_LLM=true`,
        `DEFAULT_PROJECTS_DIR=<some script's temp dir>`, `BEAT_SECONDS=2`.
        So **stop using the "remember to restore" convention** (iron rule of this project: a path that writes user files
        should by default be unwritable). The regression harness sets `NWS_ENV_SINK` for each subprocess,
        pointing to a temp file —— no matter how the subprocess `save()`s, it can't write to the real `.env`.
        ⚠ Relationship with `Config.redirect_save`: that one is an **in-process** fuse (set by the script itself),
        this one is **out-of-process** (set by the parent process for the subprocess). Either one suffices; they don't conflict.
        ⚠ When the user runs the program normally, **this environment variable won't exist**, so zero impact on product behavior.
    """
    p = (os.environ.get('NWS_ENV_SINK') or '').strip()
    if p:
        return Path(p).expanduser()
    # ★★ 第四道防线（2026-10-11 加）：**进程自己认得出"我是验证脚本"**。
    #   前三道各有各的漏口，这次漏在**"手工单跑一支判据"**上：
    #     · `NWS_ENV_SINK` —— 只有**回归器**给子进程设；
    #     · `VU.redirect_env_writes()` —— 得**脚本自己记得调**（124 支里大多数没调）；
    #     · 备份/还原 —— 单跑时没人还原。
    #   2026-10-11 实测踩到：手工跑 `tools/verify_help_book.py`（它在真机段点了「保存」），
    #   于是用户的真实 `.env` 被写成 `MOCK_LLM=true` +
    #   `DEFAULT_PROJECTS_DIR=<某脚本的临时目录>` —— 用户下次跑推演只会看到
    #   "怎么不调模型了"，而根因在两小时前的某次判据运行里。
    #   ⇒ 按铁律"会写用户文件的路径，默认就该写不进去"：只要进程**看得出是验证脚本**
    #     （`verify_*` / `probe_*` / `mutate_*` / `shoot_*`），写盘一律落到临时文件。
    #   ⚠ 判据只认**脚本文件名前缀**，不认"路径里含 tools" —— 后者会把
    #     `tools/make_release.py` 这类正经工具也拦掉。用户正常启动程序
    #     （`main_gui.py` / 打包后的 exe）名字不匹配，**零影响**。
    #   ⚠ 这条**替代不了**前三道，只是"最后兜底"：前面任意一道生效时都走前面那道
    #     （`NWS_ENV_SINK` 优先，便于回归器统一收集）。
    # [EN] ★★ Fourth line of defense (added 2026-10-11): **the process recognizes "I am a verification
    # [EN] script" by itself**.
    # [EN] Each of the first three has its own gap, and this time it leaked through **"running one
    # [EN] criterion by hand"**: `NWS_ENV_SINK` is only set by the **regressor** for subprocesses;
    # [EN] `VU.redirect_env_writes()` requires **the script to remember to call it** (most of the 124 don't);
    # [EN] backup/restore has nobody restoring when run standalone. Measured 2026-10-11: running
    # [EN] `tools/verify_help_book.py` by hand (it clicks "Save" in the real-machine segment) wrote the
    # [EN] user's real `.env` as `MOCK_LLM=true` + `DEFAULT_PROJECTS_DIR=<some script's temp dir>` -- the
    # [EN] user would next see "why isn't it calling the model", with the root cause two hours earlier in
    # [EN] a criterion run.
    # [EN] ⇒ Per the iron rule "a path that writes user files should by default be unwritable": if the
    # [EN] process **looks like a verification script** (`verify_*` / `probe_*` / `mutate_*` / `shoot_*`),
    # [EN] every write goes to a temp file.
    # [EN] ⚠ The test only looks at the **script filename prefix**, not "the path contains tools" -- the
    # [EN] latter would also block legitimate tools like `tools/make_release.py`. When the user starts the
    # [EN] program normally (`main_gui.py` / a packaged exe) the name doesn't match, so **zero impact**.
    # [EN] ⚠ This does **not replace** the first three; it is only the last resort (whichever earlier fuse
    # [EN] is active takes priority, `NWS_ENV_SINK` first, so the regressor can collect uniformly).
    if _is_verify_process():
        return _auto_env_sink()
    return None


def _is_verify_process() -> bool:
    """这个进程是不是**验证 / 探针脚本**（决定要不要自动拦住写盘）。

    判据只看**脚本文件名前缀**：验证判据、探针、反例法、截图、度量、预览、审计
    —— 这些都是"开发期为产品服务、本身不是产品"的东西，**它们跑出来的配置
    一律不该落到用户的 `.env`**（`measure_` / `preview_` / `audit_` 那几支同样会
    起 GUI、点按钮，一样会触发 `CFG.save()`，所以一并纳入）。
    外加 `tools/verify_` 这一种路径形态（有些脚本用 `python -m` 或相对路径启动）。
    ⚠ **不要**写成"路径里含 `developers/`"之类 —— 那会把 `developers/` 下的
      正经产物（如 `check_release.py`）也拦掉；也不要认 `tools/`，
      那里有 `make_release.py` / `i18n_check.py` 这类**会正经读配置**的工具。
    [EN] Is this process a **verification / probe script** (deciding whether to block writes
    [EN] automatically)?
    [EN] The test only looks at the **script filename prefix**: verification criteria, probes, reverse
    [EN] experiments, screenshot scripts, measurement, preview and audit tools -- these are all "built
    [EN] during development to serve the product, not the product itself", and **config they write must
    [EN] never land in the user's `.env`** (the `measure_` / `preview_` / `audit_` ones also start a GUI and
    [EN] click buttons, so they trigger `CFG.save()` too -- hence included).
    [EN] Plus the `tools/verify_` path shape (some scripts are started via `python -m` or a relative path).
    [EN] ⚠ **Do not** write "path contains `developers/`" or the like -- that would also block legitimate
    [EN] artifacts under `developers/` (e.g. `check_release.py`); nor match on `tools/`, which holds tools
    [EN] like `make_release.py` / `i18n_check.py` that **legitimately read config**.
    """
    try:
        argv0 = str(sys.argv[0] or '')
        stem = Path(argv0.replace('\\', '/')).name
        if stem.startswith(('verify_', 'probe_', 'mutate_', 'shoot_',
                            'measure_', 'preview_', 'audit_')):
            return True
        norm = argv0.replace('\\', '/')
        return '/tools/verify_' in norm
    except Exception as e:                                       # noqa: BLE001
        # ⚠ 兜底**必须留痕**（2026-10-11 血的教训）：这条 `except` 原来是
        #   `return False`（"宁可漏拦，不可误拦"—— 方向是对的），但它把
        #   **`NameError: name 'sys' is not defined`** 一起吞了：
        #   本文件顶部当时**没有 `import sys`**，于是整个保险丝**静默失效**，
        #   而 `_is_verify_process()` 老老实实每次都返回 False、看不出任何异常。
        #   ⇒ 方向不变（兜底仍判"不是验证进程"），但**把原因打到 stderr** ——
        #     一个"看起来很安全"的 catch-all 不该让"写错了名字"变成"功能不存在"。
        # [EN] ⚠ The fallback **must leave a trace** (hard lesson 2026-10-11): this `except` used to be
        # [EN] `return False` ("rather miss than falsely block" -- the right direction), but it also
        # [EN] swallowed **`NameError: name 'sys' is not defined`**: this file had **no `import sys`** at
        # [EN] the top at the time, so the whole fuse **silently failed**, while `_is_verify_process()`
        # [EN] dutifully returned False every time with nothing visibly wrong.
        # [EN] ⇒ Direction unchanged (the fallback still says "not a verification process"), but **print
        # [EN] the reason to stderr** -- a "looks safe" catch-all must not turn "a misspelled name" into
        # [EN] "the feature does not exist".
        print(f'⚠ config._is_verify_process 判定失败（按"不是验证进程"处理）：{e!r}',
              file=sys.stderr)
        return False


def _auto_env_sink() -> Path:
    """验证脚本的**自动落点**（临时目录里，按脚本名 + 进程号分开）。

    ⚠ 按 `pid` 分开是有意的：并行跑时多支脚本同时写，共用一个文件会互相覆盖
      （而 `NWS_ENV_SINK` 那条路是回归器**统一给一个** sink —— 它是只写的，
      没人读回来，所以共用无妨；这一条是"没人给"时的兜底，各自分开更稳）。
    [EN] The **automatic landing spot** for verification scripts (in the temp directory, separated by
    [EN] script name + process id).
    [EN] ⚠ Separating by `pid` is deliberate: when several scripts run in parallel they write at the same
    [EN] time, and sharing one file would overwrite each other (the `NWS_ENV_SINK` path uses a **single**
    [EN] shared sink from the regressor -- it is write-only and nobody reads it back, so sharing is fine;
    [EN] this one is the fallback for "nobody provided one", so separate is safer).
    """
    import tempfile
    d = Path(tempfile.gettempdir()) / 'nws_envsink'
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    stem = Path(str(sys.argv[0] or 'verify').replace('\\', '/')).stem or 'verify'
    return d / f'{stem}-{os.getpid()}.env'


def ui_build_stamp() -> str:
    """**界面源码最后被改动的时间**（`MM-DD HH:MM`）。

    为什么要有这个东西：用户多次看着一个**几小时前启动的旧窗口**说
    「还是没修好」—— 模块只在启动时加载一次，`.py` 改了不重启就一点变化都没有，
    而他没法分辨眼前这个窗口是新是旧。把它写进窗口标题，一眼就能看出来。
    **自动算**（读 `gui/app_flet.py` 的 mtime），不需要谁记得更新版本号。
    
        English:
    **Last modified time of the GUI source code** (`MM-DD HH:MM`).
        Why this is needed: users have repeatedly looked at an **old window started hours ago** and said
        "still not fixed" —— modules are only loaded once at startup, so `.py` edits have zero effect without a restart,
        and they can't tell whether the window in front of them is new or old. Write it into the window title and it's obvious at a glance.
        **Computed automatically** (reads mtime of `gui/app_flet.py`), so nobody needs to remember to bump the version number.
    """
    try:
        import datetime
        for rel in ("gui/app_flet.py", "config.py"):
            f = APP_DIR / rel
            if f.exists():
                return datetime.datetime.fromtimestamp(
                    f.stat().st_mtime).strftime("%m-%d %H:%M")
    except OSError:
        pass
    return ""


def window_title(project_name: str = "") -> str:
    """窗口标题：项目名（有的话）+ 版本 + **界面构建时间**。
        English:
    Window title: project name (if any) + version + **GUI build time**.
    """
    stamp = ui_build_stamp()
    base = f"小说世界AI模拟 v{VERSION}"
    if stamp:
        base += f" · 界面 {stamp}"
    return f"{base} — {project_name}" if project_name else base

SPEC: dict[str, dict[str, Any]] = {
    # ⚠️ 本组（推演服务LLM设定 / LLM 能力）全部标记 `restart=True`：
    # LLM 客户端在启动时一次性建好（连接池、认证头、并发信号量都在 `LLM.start()`），
    # 运行中改这些值不会自动重建 —— 所以界面上必须写明「改完要重启」。
    # [EN] ⚠️ This group (simulation service LLM settings / LLM capabilities) all marked `restart=True`:
    # [EN] The LLM client is built once at startup (connection pool, auth headers, concurrency semaphore
    # [EN] are all in `LLM.start()`),
    # [EN] changing these values at runtime will not automatically rebuild it -- so the UI must state
    # [EN] "restart after changing".
    "LLM_PROVIDER": dict(group="模型与LLM", type="enum", default="openai_compatible",
                         opt=["openai_compatible", "ollama"], desc="接入协议", restart=True),
    "LLM_BASE_URL": dict(group="模型与LLM", type="str", default="https://api.deepseek.com/v1",
                         restart=True),
    "LLM_API_KEY": dict(group="模型与LLM", type="str", default="", secret=True, restart=True),
    "LLM_TIMEOUT_SECONDS": dict(group="模型与LLM", type="int", default=60, min=5, max=600,
                                restart=True),
    "LLM_MAX_RETRIES": dict(group="模型与LLM", type="int", default=3, min=0, max=10,
                            restart=True),
    "LLM_MAX_CONCURRENCY": dict(group="模型与LLM", type="int", default=4, min=1, max=32,
                                restart=True),
    "MOCK_LLM": dict(group="模型与LLM", type="bool", default=False, desc="演示模式",
                     restart=True),
    # 模型名按 **2026-10-06 实测的 DeepSeek 官方可用列表**给默认值：
    # 对方 `/models` 只回 `deepseek-flash` 与 `deepseek-v4-pro` 两个名字
    # （`deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 弃用、仍能调）。
    # [EN] Model names are given as defaults based on the **DeepSeek official available list tested on
    # [EN] 2026-10-06**:
    # [EN] The other party's `/models` only returns two names, `deepseek-flash` and `deepseek-v4-pro`
    # [EN] (`deepseek-chat` / `deepseek-reasoner` were deprecated on 2026-07-24, but can still be called).
    # ★★★ 2026-10-15（用户）：「你检查下有用 Deepseek Pro 模型的吗？有就改成 Flash，Pro 太贵了」
    #   ⇒ 三档**全部**改成 `deepseek-flash`。价差（元/百万 token，命中/未命中/输出）：
    #     · `deepseek-v4-pro` (0.3, 9.0, **27.0**)
    #     · `deepseek-flash`  (0.1, 2.0, **8.0**)  ← 输出便宜 3.4 倍
    #   ⚠ 三档同名 ⇒ "档位"退化成"一处配置"：想再分档时把 `MODEL_FRONT` 改回强模型即可，
    #     接线本身（Agent 的 `tier:` → 这三个旋钮）一个字都没动。
    # [EN] ★★★ 2026-10-15 (user): "check whether DeepSeek Pro is used anywhere; if so switch to Flash,
    # [EN] Pro is too expensive" => **all three tiers** become `deepseek-flash`. Price gap (CNY per M
    # [EN] tokens, hit / miss / output): pro (0.3, 9.0, **27.0**) vs flash (0.1, 2.0, **8.0**) -- output
    # [EN] is 3.4x cheaper. ⚠ With all three the same, "tiers" degrade to a single config; to split them
    # [EN] again just point `MODEL_FRONT` back at a stronger model -- the wiring itself (Agent `tier:` ->
    # [EN] these three knobs) is untouched.
    "MODEL_FRONT": dict(group="模型与LLM", type="str", default="deepseek-flash", restart=True),
    "MODEL_DAILY": dict(group="模型与LLM", type="str", default="deepseek-flash", restart=True),
    "MODEL_CHEAP": dict(group="模型与LLM", type="str", default="deepseek-flash", restart=True),
    # ★★ 默认模型（2026-10-12 用户点名）。
    #   值是**模型登记表里的键**（`llm/models.py`，存 `llm_models.json`）。
    #   解析顺序：Agent 点名 → 该 Agent 的档位 → **默认模型** → 登记表第一条。
    #   ⇒ 所以"把三档都留空、只指定一个默认模型"也是一种合法配法：
    #     全程序都用这一个模型，只有明确点名的 Agent 例外。
    # [EN] ★★ Default model (called out by the user on 2026-10-12).
    # [EN] The value is a **key in the model registry** (`llm/models.py`, stored in
    # [EN] `llm_models.json`).
    # [EN] Resolution order: Agent named one -> that Agent's tier -> **default model** -> first entry.
    # [EN] => So "leave all three tiers empty and name just a default model" is also a legal setup:
    # [EN] the whole program uses that one model, except for Agents that explicitly named another.
    "LLM_DEFAULT_MODEL": dict(group="模型与LLM", type="str", default="", restart=True),
    "MODEL_PRICE_OVERRIDES": dict(group="模型与LLM", type="str", default=""),
    # 上次从 Base URL 拉到的可用模型名（逗号分隔）。**不是给人改的设置**，是
    # 「拉取模型列表」按钮的缓存：模型下拉的候选项按
    # 「缓存 → 内置兜底 → 当前填的值」拼（见 `gui.app_flet.model_choices`）。
    # 没有它的话，下次打开天机就又只剩几个写死的名字，
    # 而对方服务上真正有哪些模型只有拉过才知道。
    # [EN] Available model names last fetched from the Base URL (comma-separated). **Not a setting for
    # [EN] humans to edit**, it is
    # [EN] the cache for the "Fetch model list" button: the model dropdown's candidates are assembled as
    # [EN] "cache → built-in fallback → currently entered value" (see `gui.app_flet.model_choices`).
    # [EN] Without it, next time Tianji is opened there are only a few hardcoded names left,
    # [EN] yet the only way to know which models actually exist on the other party's service is to fetch
    # [EN] them.
    "MODEL_LIST_CACHE": dict(group="模型与LLM", type="str", default="",
                             desc="上次拉取到的可用模型列表（逗号分隔，由"
                                  "「拉取模型列表」按钮写入）"),

    # ── LLM 能力（模型自带的特性；启动时按模型名自动校验并纠偏，见 llm/capabilities.py）──
    # 这四项是**对当前模型的声明**：程序按它决定发不发某些参数、走不走某个接口。
    # 启动时会拿模型名去 llm/capabilities.py 的知识库里比对，不一致以知识库为准写回，
    # 并在界面消息框里说明改了什么 —— 所以**手填错了也不会一直错下去**。
    # [EN] ── LLM capabilities (features intrinsic to the model; at startup auto-validated and corrected by
    # [EN] model name, see llm/capabilities.py) ──
    # [EN] These four items are a **declaration about the current model**: the program uses them to decide
    # [EN] whether to send certain parameters and whether to use a certain interface.
    # [EN] At startup the model name is compared against the knowledge base in llm/capabilities.py; on
    # [EN] mismatch the knowledge base wins and is written back,
    # [EN] and the UI message box explains what was changed -- so **a manual entry error will not persist
    # [EN] forever**.
    "LLM_CAP_IMAGE": dict(group="LLM 能力", type="bool", default=False, restart=True,
                          desc="模型支持文生图（能调 /images/generations）。"
                               "关掉则「全彩文生图」这一档自动降级为本地 PNG 矢量图，"
                               "肖像图出不来时只是不插肖像。由 IMAGE_AI_MODEL 的型号决定"),
    "LLM_CAP_REASONING": dict(group="LLM 能力", type="bool", default=False, restart=True,
                              desc="模型是推理模型（自带思维链，如 deepseek-reasoner / o1 / o3）。"
                                   "开启后请求里不再发送 temperature —— 这类模型会拒绝该参数"),
    "LLM_CAP_THINKING": dict(group="LLM 能力", type="bool", default=True, restart=True,
                             desc="允许在「只要结论」的用途上关掉思考模式"
                                  "（发 thinking:{\"type\":\"disabled\"}）。进度评估、"
                                  "类型判定、正文对齐这三处只要一个结论，而**思考会连 "
                                  "max_tokens 一起吃**：2026-10-06 实测一句「判据满足了"
                                  "吗」让 deepseek-flash 思考 3233 token、2000 的额度"
                                  "全用光、正文一个字都没写出来。**关掉之后 56 token "
                                  "就答完，快 3 倍**。程序每次都还会按当次请求的模型"
                                  "再确认一遍，不认识这个参数的模型（o1 / Claude…）"
                                  "一个字都不会发 —— 所以这项只在你想「宁可多想一点、"
                                  "也别给不出结论」时才关掉"),
    "LLM_CAP_JSON_MODE": dict(group="LLM 能力", type="bool", default=True, restart=True,
                              desc="模型支持 JSON 模式（response_format=json_object）。"
                                   "关掉则退回「在提示词末尾追加『请仅以 JSON 回答』」"),
    "LLM_CAP_SYSTEM_ROLE": dict(group="LLM 能力", type="bool", default=True, restart=True,
                                desc="模型接受 role=system 的消息。不支持时把系统提示"
                                     "并入首条 user 消息（部分模型会直接 400）"),
    "EMBEDDING_PROVIDER": dict(group="模型与LLM", type="enum", default="none",
                               opt=["local", "api", "ollama", "none"], desc="向量方案；none=关键词退化"),
    "EMBEDDING_MODEL_LOCAL": dict(group="模型与LLM", type="str", default="BAAI/bge-small-zh-v1.5"),
    "EMBEDDING_MODEL_API": dict(group="模型与LLM", type="str", default="text-embedding-3-small"),
    "EMBEDDING_OLLAMA_MODEL": dict(group="模型与LLM", type="str", default="nomic-embed-text",
                                    desc="Ollama embedding 模型名（需先 ollama pull）"),
    "EMBEDDING_OLLAMA_URL": dict(group="模型与LLM", type="str", default="http://localhost:11434",
                                  desc="Ollama 服务地址"),
    "DEFAULT_PROJECTS_DIR": dict(group="项目与运行", type="path", default="",
                                 # ⚠ **故意不标 `restart=True`**（2026-10-08 实测）：
                                 #   `CFG.projects_dir()` 是**每次现读**的
                                 #   （`scan_projects` / `Project.create_new` 都现调它），
                                 #   所以改完**回到开始界面**书列表就换了 —— 不用重启。
                                 #   贴一个"要重启"的标签会骗人：用户会以为"现在改了没用"，
                                 #   而根目录其实已经切过去了（那种"以为没生效、其实生效了"
                                 #   比"要重启"危险得多）。界面上如实写着这句结论。
                                 # [EN] ⚠ **Deliberately not marked `restart=True`** (tested 2026-10-08):
                                 # [EN] `CFG.projects_dir()` is **read fresh every time**
                                 # [EN] (both `scan_projects` / `Project.create_new` call it fresh),
                                 # [EN] so after changing it, **returning to the start screen** refreshes the book list -- no restart
                                 # [EN] needed.
                                 # [EN] Slapping on a "requires restart" label would be misleading: users would think "changing it now
                                 # [EN] has no effect",
                                 # [EN] while the root directory has actually already switched (that kind of "thought it had no effect,
                                 # [EN] but it actually did"
                                 # [EN] is far more dangerous than "requires restart"). The UI states this conclusion truthfully.
                                 desc="小说项目存在哪个目录（每本一个文件夹）；"
                                      "留空 = 默认的「桌面 · 小说世界AI模拟/Projects」"),
    "OPTIMIZE_ON_IMPORT": dict(group="项目与运行", type="bool", default=True),
    # ── 开卷打磨 Agent（2026-10-07）──────────────────────────────────
    #   这一组管的是"AI 优化那一段到底怎么跑"。用户的报修是「你没有生成一个
    #   Agent，而且每次我输入新对话，你发给 LLM 的内容不包含之前的历史信息」——
    #   所以默认就是 Agent（带历史 + 工具 + 自省）。关掉退回老的"一问一答"
    #   （省调用次数，但模型看不到历史，代词指代会落空）。
    # [EN] ── Open-book polishing Agent (2026-10-07) ──────────────────────────────────
    # [EN] This group governs "how exactly the AI optimization segment runs". The user's complaint was "you
    # [EN] did not generate an
    # [EN] Agent, and every time I enter a new conversation, the content you send to the LLM does not
    # [EN] include the previous history" --
    # [EN] so the default is the Agent (with history + tools + introspection). Turning it off falls back to
    # [EN] the old "question-and-answer"
    # [EN] (saves call count, but the model cannot see history, and pronoun references fail).
    "POLISH_AGENT": dict(group="项目与运行", type="bool", default=True,
                         desc="开卷的 AI 优化用打磨 Agent（带历史、会用工具、会自查）。"
                              "关掉退回老的「一问一答」，省调用但模型看不到历史"),
    "POLISH_MAX_STEPS": dict(group="项目与运行", type="int", default=6, min=1, max=20,
                             desc="打磨 Agent 一轮最多走几步（想→用工具→看结果 算一步）"),
    "POLISH_MAX_TOOL_CALLS": dict(group="项目与运行", type="int", default=60,
                                  min=5, max=400,
                                  desc="一场打磨总共最多调多少次工具（防死循环烧钱）"),
    # ★ 对话轮数上限（2026-10-08 用户要求：「开卷 AI 优化 要有轮数上限且有地方配置，
    #   而且可以点击某个按钮强制停止」）。
    #   这一项管的是**外层**：作者每发一条指令算一轮。以前这一层没有任何上限 ——
    #   一路聊下去就是一路花钱（每轮内部还有 `POLISH_MAX_STEPS` 步 + 一次自查）。
    #   注意它**不是**"强制停止"的替代：那个按钮随时能打断**正在跑的那一轮**，
    #   而这一项管的是"还能不能再开新一轮"。
    # [EN] ★ Conversation round limit (2026-10-08 user request: "Open-book AI optimization needs a round
    # [EN] limit with a place to configure it,
    # [EN] and there should be a button that can force stop it").
    # [EN] This item governs the **outer** layer: each instruction the author sends counts as one round.
    # [EN] Previously this layer had no limit --
    # [EN] chatting all the way down means spending all the way down (each round internally also has
    # [EN] `POLISH_MAX_STEPS` steps + one self-check).
    # [EN] Note it is **not** a substitute for "force stop": that button can interrupt **the round
    # [EN] currently running** at any time,
    # [EN] whereas this item governs "whether another new round can be started".
    "POLISH_MAX_ROUNDS": dict(group="项目与运行", type="int", default=10, min=1, max=100,
                              desc="开卷 AI 优化最多来回几轮（你发一条指令算一轮）。"
                                   "到上限就不再收新指令，会让你点「完成优化并进入」"),
    "POLISH_REFLECT": dict(group="项目与运行", type="bool", default=True,
                           desc="打磨 Agent 收尾后换一双眼睛自查（漏改 / 改坏 / 越权 / 编造）"),
    "POLISH_REFLECT_ROUNDS": dict(group="项目与运行", type="int", default=1, min=0, max=3,
                                  desc="自查出问题时，最多再走几轮把它改掉"),
    "POLISH_TOOLS": dict(group="项目与运行", type="bool", default=True,
                         desc="允许打磨 Agent 现场写代码：动态生成工具 + 临时跑代码"
                              "（在沙盒里跑，只能写打磨输出区）"),
    "POLISH_SANDBOX_TIMEOUT": dict(group="项目与运行", type="int", default=20,
                                   min=3, max=120,
                                   desc="沙盒里跑一次生成代码的硬超时（秒）"),
    "POLISH_WRITE_BACK": dict(group="项目与运行", type="bool", default=True,
                              desc="把打磨结论**追加**回引用文件夹（只追加、自动留 .bak；"
                                   "项目一开始就不再动它）"),
    # ══════════════════════════════════════════════════════════════════
    #  拆书（2026-10-07 第六轮）
    # [EN] Book dissection (2026-10-07, sixth round)
    # ══════════════════════════════════════════════════════════════════
    # 一句话：**把一本别人写得好的书读成"写法"**，存进 `skills/`，
    # 以后写同类故事时被各职位引用（三人小组拿完整版）。
    # 与"开卷"是两件事：开卷把书变成**设定集**（进项目），
    # 拆书把书变成**写法**（进技能库）。见 `booklab/__init__.py` 那张对照表。
    # [EN] In one sentence: **read a well-written book by someone else into a "writing method"**, store it
    # [EN] in `skills/`,
    # [EN] and later when writing similar stories it is referenced by each role (the three-person team gets
    # [EN] the full version).
    # [EN] It is two different things from "open-book": open-book turns a book into a **setting
    # [EN] collection** (into the project),
    # [EN] book dissection turns a book into a **writing method** (into the skill library). See the
    # [EN] comparison table in `booklab/__init__.py`.
    "BOOKLAB_ENABLED": dict(group="项目与运行", type="bool", default=True,
                            desc="拆书功能总开关（关掉后开始菜单那一项会说明它被关了）"),
    "BOOKLAB_MAX_BATCHES": dict(group="项目与运行", type="int", default=26, min=1, max=200,
                                desc="粗扫最多跑几批（每批十几章）。一本长篇分层取样后"
                                     "约 24 批；调小=省钱但读得更粗"),
    "BOOKLAB_LESSON_PACKS": dict(group="项目与运行", type="int", default=2, min=1, max=5,
                                 desc="一本新书最多引用几份拆书经验（多了会挤掉别的上下文）"),
    "BOOKLAB_SKIP_WRITERS": dict(group="项目与运行", type="bool", default=False,
                                 desc="关掉后**三人小组也只拿压缩版**的拆书经验"
                                      "（省 token，但少了节奏/立人/不要照搬那几节）"),
    "STORY_GENRE": dict(group="类型与风格", type="str", default="auto"),
    "NOVEL_STYLE": dict(group="类型与风格", type="enum", default="auto",
                        opt=["auto", "plain", "custom"]),
    "NOVEL_STYLE_CUSTOM": dict(group="类型与风格", type="str", default=""),
    "CRAFT_LIBRARY": dict(group="类型与风格", type="str", default="builtin"),
    "CRAFT_CASES_ENABLED": dict(group="类型与风格", type="bool", default=True),
    "SCENE_NAME": dict(group="类型与风格", type="str", default="auto"),
    "SCENE_START_HINT": dict(group="类型与风格", type="str", default=""),
    #: 时钟怎么显示。★ 2026-10-18 审计删掉了 `regnal`（年号）那一档：
    #:   `format_game_clock` 里那一支要求**外部传年号**（`regnal="昭和三年"`），
    #:   而全库**没有任何地方传** ⇒ 用户选了"年号"，界面永远还是"第1天·辰时"，
    #:   一切看起来正常。**假旋钮要删**，不是留着等以后。
    #:   想恢复：先给 `WorldState` 补一个年号来源（从设定读），再把这一档加回来，
    #:   `verify_repetition_guards` 的 **H9** 会守住"每个选项都真能改变显示"。
    # [EN] How the clock is displayed. ★ The 2026-10-18 audit removed the `regnal` (era name) tier:
    # [EN] that branch requires an era name **passed in from outside**, and nothing in the codebase
    # [EN] passes one => picking "era name" left the display unchanged while everything looked
    # [EN] normal. **Delete fake knobs** instead of keeping them for later. To restore it: give
    # [EN] `WorldState` an era-name source first, then re-add the tier; H9 in
    # [EN] `verify_repetition_guards` guards "every option really changes the display".
    "CALENDAR_DISPLAY": dict(group="类型与风格", type="enum", default="auto",
                             opt=["auto", "ganzhi", "modern", "daycount"]),
    "RUN_MODE": dict(group="运行边界", type="enum", default="story",
                     opt=["story", "open", "story_day"],
                     desc="story=按进度表走到终点；open=不限期推演；story_day=按进度表但定期暂停"),
    # ⚠ `min=0`（0 = 不自动停）：以前是 `min=1`，于是"关掉存档点"做不到 ——
    #   验证时才发现，顺手放开。默认 3 与老行为一致。
    # [EN] ⚠ `min=0` (0 = do not auto-stop): it used to be `min=1`, so "turn off the save checkpoint" was
    # [EN] impossible --
    # [EN] only discovered during verification, fixed along the way. Default 3 matches the old behavior.
    "OPEN_CHECKPOINT_EVERY_DAYS": dict(group="运行边界", type="int", default=3,
                                       min=0, max=99,
                                       desc="不限期限模式下每几天停一次存档"
                                            "（0=不自动停）"),
    "STORY_DAY_EVERY_DAYS": dict(group="运行边界", type="int", default=3, min=1, max=99,
                                 desc="story_day 模式每隔 N 虚拟日落一次盘、说一声"
                                      "（默认**不停下来等你** —— 见下面的 "
                                      "`CHECKPOINT_PAUSE`）"),
    # ★★ 存档点要不要**停下等确认**（2026-10-11）。
    # [EN] ★★ Whether the save checkpoint should **stop and wait for confirmation** (2026-10-11).
    # 用户原话：「这个时候实在推演中的 我没点暂停」，还有一条更早的诉求：
    # 「1.尽可能想办法不要让用户干预」。
    # [EN] The user's exact words: "at this time it was still in simulation and I did not click pause",
    # [EN] plus an earlier request:
    # [EN] "1. Try as much as possible not to require user intervention".
    # 起因是真机事故：`STORY_DAY_EVERY_DAYS=1` + `story_day`，于是**每一天**
    # 都在日界停住等人点「继续」。中栏冒出一条 `▸ 临时暂停`，状态条却还写着
    # 「正在核对故事进度」（主循环自己开的暂停不经过会话层，见 `RunLoop.pause`
    # 的说明）。作者看到的是"它自己停了，我不知道为什么，也没有「继续」可点"。
    # [EN] The cause was a real-machine incident: `STORY_DAY_EVERY_DAYS=1` + `story_day`, so **every day**
    # [EN] stopped at the day boundary waiting for someone to click "continue". A `▸ temporary pause`
    # [EN] popped up in the center column, yet the status bar still said
    # [EN] "verifying story progress" (the main loop's own pause does not go through the session layer, see
    # [EN] the note on `RunLoop.pause`
    # [EN] ). What the author saw was "it stopped by itself, I do not know why, and there is no "continue"
    # [EN] to click".
    # 为什么默认改成**不停**：日界检查点 / 存档点回答的是"我存档了没有"，
    # 它**不需要作者做任何决定** —— 那就不该打断推演。
    # 「定期暂停」这个模式的本意是**定期**（有节奏地存档 + 报一句进度），
    # 不是"每次都拦下来问一句"。想拦的人把这个开关打开。
    # [EN] Why the default was changed to **no stop**: the day-boundary checkpoint / save checkpoint
    # [EN] answers "have I saved or not",
    # [EN] it **does not require the author to make any decision** -- so it should not interrupt the
    # [EN] simulation.
    # [EN] The original intent of the "periodic pause" mode was **periodic** (save at a regular rhythm +
    # [EN] report a line of progress),
    # [EN] not "stop and ask a question every time". Those who want to stop should turn this switch on.
    # `true` 时会走**提问对话框**（不是裸暂停）：说明 + 选项 + 确定/取消。
    # [EN] When `true` it goes through a **question dialog** (not a bare pause): description + options +
    # [EN] confirm/cancel.
    "CHECKPOINT_PAUSE": dict(group="运行边界", type="bool", default=False,
                             desc="存档点（日界 / open 存档）是否**停下来等你确认**。"
                                  "默认否 —— 只落盘并在中栏说一句，接着演；"
                                  "打开则弹提问对话框等你拍板"),
    "STORY_START_POINT": dict(group="运行边界", type="str", default="auto"),
    # ★ 定时落盘（2026-10-08 用户要求）：「我点暂停的时候以及平时也有可能随时
    #   关闭软件 所以后台还需要一个定时器实现定时落盘 比如没30秒落盘一次」。
    #   ⚠ 它管的是**中途稿**（`<运行文件夹>/自动落盘/进度.md`，滚动覆盖），
    #     不是那份"一天一个文件"的正式产物 —— 后者照旧在日界/收工写。
    #     为什么要中途稿：主循环只在日界落盘，暂停或直接关窗口时，
    #     当天已经演了大半的戏**只在内存里**，白跑。
    #   `0` = 关闭（界面那条状态小字会写"已关闭"）。
    # [EN] ★ Timed flush to disk (2026-10-08 user request): "when I click pause, and at other times, I
    # [EN] might at any moment
    # [EN] close the software, so the backend also needs a timer to flush to disk periodically, e.g. flush
    # [EN] once every 30 seconds".
    # [EN] ⚠ It governs the **in-progress draft** (`<run folder>/auto-flush/progress.md`, rolling
    # [EN] overwrite),
    # [EN] not the formal artifact of "one file per day" -- the latter is still written at the day boundary
    # [EN] / end of work as before.
    # [EN] Why an in-progress draft: the main loop only flushes at the day boundary; when paused or when
    # [EN] the window is closed directly,
    # [EN] the day's scenes that have already run more than half exist **only in memory**, wasted.
    # [EN] `0` = disabled (the small status text in the UI will say "disabled").
    "AUTOSAVE_SECONDS": dict(group="运行边界", type="int", default=30, min=0, max=600,
                             # ★ 2026-10-23 改描述（**不是改行为，是改说法**）：以前它
                             #   只写"中途稿"，用户读不出"断电能不能接上"。
                             #   现在它落的正是**可续跑的那两份**（当天正文 + 停点），
                             #   所以要写清楚这一层意义 —— 用户就是照这行字判断要不要开。
                             # [EN] ★ 2026-10-23 description rewrite (not behaviour): it used to say
                             # [EN] only "mid-progress draft", which does not tell the user whether a
                             # [EN] power cut can be survived. It now writes **the two resumable
                             # [EN] files** (that day's body + the stop point), so say so.
                             desc="每隔几秒自动落盘一次：把**这一天的正文**和**停点**"
                                  "一起写盘 —— 断电或随手关掉程序后，下次「起笔」会从"
                                  "这里接着演，最多损失这个间隔。点暂停、关窗口时"
                                  "也会各落一次。0 = 关闭"),
    "ENDING_SCENE": dict(group="运行边界", type="bool", default=True),
    "PLOT_ADHERENCE": dict(group="运行边界", type="float", default=0.7, min=0, max=1),
    # ══ 本轮推演（2026-10-11，用户点名在「起笔」里控制的那几件事）══════════
    # [EN] ══ This round's simulation (2026-10-11, the few things the user specifically named as controlled
    # [EN] in "start writing") ══════════
    # 用户原话：「我想在起笔的时候控制 这次推演要不要发生关联事件还是只是一次
    # 日常生活型的推演不带关键剧情，大概发生几件事情，没事的时候时间要不要跳过
    # （即用旁白描述一下就过去这段时间），你再看下还有别的可以定制吗？」
    # [EN] The user's exact words: "I want to control at the start of writing whether this simulation
    # [EN] should have related events or just a
    # [EN] daily-life type simulation without key plot, roughly how many things happen, and whether time
    # [EN] should skip when nothing is happening
    # [EN] (i.e. use narration to describe it and let that period pass), and see if there is anything else
    # [EN] that can be customized?"
    # ★★ **为什么必须做成配置项、不能靠「建议」那个输入框**（用户自己也问了
    #    "这些话可以通过现在起笔里的用输入框实现吗"）：那只输入框里的字是进
    #    `craft_block` 的**提示词**（给剧组的一句"往哪走"），模型可以不理；
    #    而这六件事都是**程序行为** —— 要不要真去调一次"挑事"的模型（花钱）、
    #    这一轮总共挑几件、时钟要不要一口气跳过一段、谁算在场。
    #    提示词既数不清数、也推不动时钟，而且必须是确定的（写"只发生三件"，
    #    模型不会替你数）。判据 `verify_round_controls` 逐条钉住这六件事。
    # [EN] ★★ **Why it must be made a config item and cannot rely on the "suggestion" input box** (the user
    # [EN] also asked this
    # [EN] "can these words be realized through the input box in the current start-of-writing"): the text
    # [EN] in that input box goes into
    # [EN] the **prompt** of `craft_block` (a single "where to go" for the crew), and the model can ignore
    # [EN] it;
    # [EN] whereas these six things are all **program behavior** -- whether to actually make a call to a
    # [EN] "stir things up" model (spending money),
    # [EN] how many things to stir up in total this round, whether the clock should skip a stretch in one
    # [EN] go, who counts as present.
    # [EN] A prompt can neither count numbers nor push the clock, and it must be deterministic (writing
    # [EN] "only three things happen",
    # [EN] the model will not count for you). The criterion `verify_round_controls` pins down these six
    # [EN] things one by one.
    # ⚠ 六项都存 `.env`（与同一个对话框里的「运行边界 / 风格控制」完全一致）——
    #   所以**下次起笔它们还在**（对话框里看得见，不是"隐形的复活"）。
    #   其中两项（出场人物 / 固定场景）写的是**这本书里的名字**，
    #   装配时会跟这本书的人物表 / 地点表核对，认不出来的**丢掉并说一句** ——
    #   否则换一本书之后会出现"名单里的人一个都不在这本书里、于是没人上场"。
    # [EN] ⚠ All six items are stored in `.env` (exactly the same as "run boundary / style control" in the
    # [EN] same dialog) --
    # [EN] so **they're still there the next time you start writing** (visible in the dialog, not a "hidden
    # [EN] resurrection").
    # [EN] Two of them (cast / fixed scenes) contain **names from this book**,
    # [EN] checked at assembly time against this book's character table / location table; anything
    # [EN] unrecognized is **dropped with a note** --
    # [EN] otherwise after switching books you'd get "no one from the list is in this book, so no one takes
    # [EN] the stage".
    "ROUND_KIND": dict(group="本轮推演", type="enum", default="normal",
                       opt=["normal", "daily"],
                       desc="这一轮的性质：normal=正常（导演照常挑事）；"
                            "daily=日常生活型（不主动注入关键事件，只过日子）"),
    "ROUND_EVENT_LIMIT": dict(group="本轮推演", type="int", default=0, min=0, max=99,
                              desc="这一轮最多发生几件**关键事件**（导演注入的那种）。"
                                   "上限一到就不再挑事，故事靠人物自己走。0 = 不限"),
    "ROUND_CAST": dict(group="本轮推演", type="str", default="",
                       desc="本轮**只让这几个人上场**（逗号分隔；空 = 全体）。"
                            "⚠ 名字要跟人物卡里一致，认不出来的会被丢掉并在日志里说明"),
    "ROUND_SCENE": dict(group="本轮推演", type="str", default="",
                        desc="本轮**锁在一个地点**（不发生换场；空 = 不锁）"),
    "PLACE_PERSIST": dict(group="本轮推演", type="bool", default=True,
                          desc="剧作家写到**设定集里没有的地点**时（比如「河岸柳树下」），"
                               "把它**补进「设定集/地点.yaml」**长期保留（下次开卷还认它，"
                               "地图也能画到那儿）。关掉就只在**本轮**临时认它，"
                               "下一轮又变回不认识（地图又会卡在开头那一张）。"
                               "⚠ 只追加一条、绝不重写你原来的条目；写之前留一份 "
                               "`.bak-新地点-时间戳` 备份"),
    "ROUND_DAILY_WORDS": dict(group="本轮推演", type="int", default=0, min=0, max=50000,
                              desc="每个故事日大概写多少字（软目标：会告诉编剧组与"
                                   "各人，并显示在运行界面的状态条上）。0 = 不限"),
    "SKIP_IDLE_TIME": dict(group="本轮推演", type="bool", default=True,
                           desc="**没事的时候把时间跳过去**：连着几拍谁都没做事，"
                                "就用一句旁白带过一段时间，不再一拍拍空转（省 token）。"
                                "默认开（2026-10-11 用户拍板）"),
    "SKIP_IDLE_BEATS": dict(group="本轮推演", type="int", default=6, min=1, max=50,
                            desc="连着几拍**谁都没做事**才跳"
                                 "（`SKIP_IDLE_TIME` 开着才有效）"),
    "SKIP_IDLE_MINUTES": dict(group="本轮推演", type="int", default=30, min=5, max=720,
                              desc="每次跳过多少**故事分钟**（上限 720 = 半天，"
                                   "最多跨一次日界）"),
    "STALL_BREAK_BEATS": dict(group="本轮推演", type="int", default=3, min=0, max=30,
                              desc="连着几拍**大多数人都在等同一件事**，就让导演"
                                   "给那件事一个结果（门开了 / 人进来了 / 东西掉了）。"
                                   "设 0 = 关掉这个破局（戏可能一直停在原地）。"
                                   "2026-10-19 加：《雪国》实测 34 拍里 7 次 wait，"
                                   "全在等门外那脚步，而那脚步一直没结果。"),
    "PROSE_FLOW_FIX": dict(group="本轮推演", type="int", default=2, min=0, max=6,
                           desc="整理成小说时，**整段一句都没铺开**的段落最多重写几段。"
                                "设 0 = 不重写（只靠提示词，改回 2026-10-19 之前的行为）。"
                                "重写只动被判出来的那几段，失败一律保留原文。"),
    "PROSE_REPEAT_FIX": dict(group="本轮推演", type="int", default=1, min=0, max=1,
                             desc="整理成小说时，**同一个写法用了一次又一次**"
                                  "（沉默总是“没应+看一眼” / 口头禅 / 道具状态反复交代）就修一次。"
                                  "设 0 = 只报不修。2026-10-19 加：《雪国》实测“你这个人哪”一天 4 次、"
                                  "“没应，看雪光”这类成套句式一天 2 次。"
                                  "修的方式是给可数的事实、让模型换法子重写，事实一个字不动；失败一律保留原文。"),
    "PROSE_CROWD_FIX": dict(group="本轮推演", type="int", default=1, min=0, max=1,
                            desc="整理成小说时，**一大段塞了太多件事**（读起来是一坨流水账）就修一次。"
                                 "设 0 = 只报不修。2026-10-20 加：真人 18 章段内最多 7 件事、"
                                 "18 章没有一章越界；《雪国》实测最长一段塞了 44 件事（638 字）。"
                                 "修法是**拆段**，不是删事 —— 事实一个字不动，失败一律保留原文。"),
    "PROSE_SPIN_FIX": dict(group="本轮推演", type="int", default=1, min=0, max=1,
                           desc="整理成小说时，**在同一个地方打转**（同一个人把同一个诉求"
                                "换着说法问了一遍又一遍 / 同一个动作做了一遍又一遍）就修一次。"
                                "设 0 = 只报不修。2026-10-20 加：《雪国》实测驹子把"
                                "「我是不是好人」问了 7 遍、叶子送酒 5 次。"
                                "⚠ 这一条的**判决在 LLM 判官**，不在代码 —— 打转是换了说法的重复，"
                                "字面量法（动宾紧邻 / 2-gram 峰值 / 字面承接）实测全部零区分度。"
                                "代码只管安全：判官说没打转、或回话看不懂，就一个字都不改。"),
    "PROSE_PLAUS_FIX": dict(group="本轮推演", type="int", default=1, min=0, max=1,
                            desc="整理成小说时，**读起来不成立的句子**（写成了几乎听不见的话"
                                 "却被隔着一扇门的人听见 / 隔着距离写到睫毛那一层的微距 / "
                                 "干燥的釉面自己“流过一道亮痕”这类物理瑕疵）就定点改一句。"
                                 "设 0 = 只报不修。2026-10-20 加：前两类有可数的形状"
                                 "（真人 18 章 0 条，《雪国》v17 2 条），第三类写不出字面判据，"
                                 "所以三类一起交给判官。⚠ 不整章重写 —— 只替换判官点名的那几句，"
                                 "并有四道闸（毛病不许变多 / 台词不许变少 / 长度 0.9–1.3 倍 / 新句不短于原句）。"),
    "PROSE_META_FIX": dict(group="本轮推演", type="int", default=1, min=0, max=1,
                           desc="整理成小说时，**叙述者跳出来讲结构**的那半句就删掉"
                                "（「算是第二层的新问」「把这第三轮收住」「这回不重复进门送物」）。"
                                "设 0 = 只留着。2026-10-20 加：这个病是我们自己的修复提示词喂出来的 ——"
                                "提示词里写了“最多来回三轮”“换个由头”，模型就把它念给读者听；"
                                "真人 18 章 0 条，《雪国》v17 6 条。"
                                "⚠ 这一条**故意不调模型**：元叙述是“多写了一句”，删是唯一不会写坏的动作。"),
    "PROSE_DRIFT_FIX": dict(group="本轮推演", type="int", default=1, min=0, max=1,
                            desc="整理成小说时，**连着三句问出去没人接**的对话就修出一处真答复"
                                 "（上一句问「你要不要看」，下一句答「这酒还够喝吗」，"
                                 "再下一句又问新的 —— 两个人各说各话）。设 0 = 只报不修。"
                                 "2026-10-20 加：先量过，**单句悬空不是病**（真人 80%–100% 都不直接答），"
                                 "真人最长连续悬空 2，《雪国》v18 到 5 ⇒ 阈值 ≥3，真人 18 章零误报。"
                                 "⚠ 推演层的对话审计早就看得见（每拍都在报），但只算不拦 —— "
                                 "这一条在成篇的散文上把其中一两句改成半句回应。"
                                 "四道闸：毛病必须变少 / 台词不许变少 / 长度 0.9–1.3 倍 / 新句不短于原句。"
                                 "**改几句也管**：从少到多试，第一次压到阈值以下就停 —— "
                                 "全改会把四句连排都写成「半句回答；自己的问题」，是新的模版腔。"),
    "PROSE_PROP_FIX": dict(group="本轮推演", type="int", default=1, min=0, max=1,
                           desc="**道具循环**：同一件东西被反复「续上—耗掉」就改掉中间那一两句"
                                "（茶凉了 → 续上 → 又凉了 → 再续上；台词每句都不同，"
                                "手上的事一遍没变）。设 0 = 只报不修。"
                                "2026-10-20 加（用户：「继续修复道具循环」）：先量过 —— "
                                "真人 18 章「同一件东西的最大复位次数」中位 0、最大 0；"
                                "真跑 v12/v15/v17/v18 是 0，v16/v19/v20 是 4 ⇒ 阈值 ≥3，零误报。"
                                "⚠ 这个数必须**贴着东西**算（句子里要有器皿或可消耗物），"
                                "否则真人科幻那章会被判进 11 次「消耗」（全是表格里的「没有」）。"
                                "⚠ 与「打转」是两件事：那边数话，这边数手 —— 所以打转判官放过它。"
                                "**不删戏，只换动作**，并明写不许换成同族动作（又喝了/又添了）。"),
    "PROSE_CHECK_ROUNDS": dict(group="本轮推演", type="int", default=5, min=1, max=8,
                               desc="整理稿**查几轮**（R48）。每一轮把「删 → 改内容 → 排版」"
                                    "全部走一遍，然后**重新数一遍还剩多少毛病**；"
                                    "没了就停，连续几轮没变少也停（见下一项）。"
                                    "2026-10-20 加（用户：「一开始写小说和最后导出的时候"
                                    "都要进行几轮检查也修复」）。"
                                    "以前是**一轮串行跑完就走**、改完从不复查 —— 修 A 时"
                                    "把 B 弄坏了没人管（删一句答话 ⇒ 问答变悬空；"
                                    "整章重写 ⇒ 又添一句元叙述）。"
                                    "**作者 2026-10-20 明确：成本可以接受、以质量优先** ⇒ "
                                    "默认从 3 提到 5，实测 3 轮时常停在「还剩 2 处」。"
                                    "设 1 = 退回老样子（只跑一轮）。"
                                    "⚠ 每一轮要跑 8 个步骤，其中 5 步要调模型 ⇒ "
                                    "轮数越多越慢越贵。"),
    "EXPORT_ATELIER": dict(group="导出", type="bool", default=True, restart=False,
                           desc="导出时走**分层创作**（默认开）：先从本次推演抽出全书骨架，"
                                "再逐章拆纲、写草稿、补细节，**每层过闸才往下走**。"
                                "解决的是老流程治不了的病：按日拼出来的是"
                                "「每天的过程稿首尾相接」，没有全书骨架，"
                                "所以「好几章在问同一件事」在结构上就已注定，"
                                "事后修句子没用（实测某本书连跑三版都在原地打转）。"
                                "闸是确定性代码：事件必须全覆盖、每章必须交代"
                                "「哪一格变了」、相邻章/相邻拍不许是同一个变化、"
                                "状态不许倒退、正文必须能引原句自证落点。"
                                "⚠ 关掉就退回按日装订（老样子）；"
                                "失败也会自动退回，不会因此导不出书。"
                                "产物落在 `<运行>/导出/`：骨架.json / 分层稿.md / 分层日志.md。"),
    "EXPORT_ATELIER_ROUNDS": dict(group="导出", type="int", default=3, restart=False,
                                  desc="分层创作每层最多写几轮（默认 3）。"
                                       "一轮不过闸就带着「哪一条不过」重写；"
                                       "用完还不过就**标出来**装订，不假装过。"),
    "PROSE_REFLEXION": dict(group="本轮推演", type="bool", default=True, restart=False,
                            desc="多轮修稿走**Reflexion 路径**（默认开）。"
                                 "旧路径是「跑 8 个步骤 → 数总数 → 降了就留」，"
                                 "它的四个结构性缺陷都不是某一步写得不好："
                                 "① 每一步自己判自己（跨类退化没人看得见，"
                                 "实测修好太碎却把憋气从 0 改到 2）；"
                                 "② 被拒的尝试整份丢掉，下一轮从零瞎试；"
                                 "③ 一轮只有一个候选；"
                                 "④ 收敛判据是单标量求和，把「两类互换」看成「没变化」。"
                                 "新路径把判定交给确定性验收层（多目标分别判、"
                                 "退化就拒、硬约束先于优劣、满分可疑），"
                                 "被拒时写一条**带原句的教训**进有界记忆，下一轮进提示词；"
                                 "每步可出 2 个候选；最终从 Pareto archive 里取最优"
                                 "（按 毛病 → 台词 → 字数 三级排序）。"
                                 "设 0 = 逐字回到旧路径（保留是为可回退）。"),
    "PROSE_REFLECT_MEMORY": dict(group="本轮推演", type="int", default=24, min=4, max=64,
                                 restart=False,
                                 desc="反思记忆最多存几条教训（默认 24）。"
                                      "Reflexion 的老毛病是记忆越堆越长、最后把上下文吃光；"
                                      "这一项就是那个上限。同类别 + 同差异的教训会自动去重，"
                                      "所以 24 条足够覆盖一轮里会重复踩的坑。"),
    "PROSE_CHECK_PATIENCE": dict(group="本轮推演", type="int", default=2, min=1, max=5,
                                 desc="**连续几轮没有进展才收工**（默认 2）。"
                                      "一轮没变少**不代表改不动了** —— 模型有抖动，"
                                      "同一句它可能这一轮改不动、下一轮换个说法就通了。"
                                      "设 1 = 老规矩（一轮没变少立刻停，最省钱）。"
                                      "配上一项用：`PROSE_CHECK_ROUNDS` 管最多跑几轮，"
                                      "这一项管什么时候认输。"),
    # ══════════════════════════════════════════════════════════════
    #  场次编排（2026-10-11，作者点名"东一句西一句、场景乱跳"之后补的）
    # [EN] Stage scheduling (added 2026-10-11 after the author called out "all over the place,
    # [EN] scenes jumping around")
    # ══════════════════════════════════════════════════════════════
    "SCENE_BEATS": dict(group="本轮推演", type="bool", default=True,
                        desc="**按剧作家的分拍表一场戏一场戏地演**（默认开）。"
                             "开了以后：① 剧作家写的每一拍（在哪、讲什么、有谁、"
                             "要动什么道具、要落到哪些动作）**真的下发到演员与导演**；"
                             "② 该出场的都露过面、戏量也够了，这一场就收，换下一拍；"
                             "③ 换场按这一拍的「场」来定，不再等「人都走光」。"
                             "关掉 = 回到从前（表还在台账里，只是不按它推进）"),
    "SCENE_BEAT_MIN_TICKS": dict(group="本轮推演", type="int", default=3, min=1, max=60,
                                 desc="**一场戏最少演几拍**（`BEAT_SECONDS` 那一种「拍」）"
                                      "才允许收场。设太小会让「一场戏」和「一拍」"
                                      "一样长，反而更碎 —— 这是下限，不是目标"),
    "SCENE_BEAT_MAX_TICKS": dict(group="本轮推演", type="int", default=12, min=1, max=200,
                                 desc="**一场戏最多演几拍**，到点强制收场"
                                      "（防止一场戏无限拖下去）。不能小于"
                                      "「一场戏最少演几拍」"),
    "SCENE_BEAT_MIN_ACTS": dict(group="本轮推演", type="int", default=2, min=1, max=20,
                                desc="**这一场至少要发生几条实动作**才算「演过了」。"
                                     "用的是「真做了事」的条数（说话、走动、交手），"
                                     "不是「跑了几拍」—— 全场发呆不算演过"),
    "AUTO_SUMMARY_ON_END": dict(group="运行边界", type="bool", default=False,
                                desc="本轮结束自动导出**运行报告**（运行小结）。"
                                     "默认关：报告含账单与 OOC 分析，跑完再手动出更有用；"
                                     "手动导出随时可用，不受此项影响"),
    "STORY_DOC_MODEL": dict(group="运行边界", type="enum", default="MODEL_FRONT",
                            opt=["MODEL_FRONT", "MODEL_DAILY"]),
    "SUMMARY_MODEL": dict(group="运行边界", type="enum", default="MODEL_FRONT",
                          opt=["MODEL_FRONT", "MODEL_DAILY"]),
    # ★★ 起笔的**装配超时**（2026-10-12 用户点名的"超时机制"）：
    #   「引入超时机制，如果后台没成功，界面可以主动停止等待」。
    #   点「开始推演」之后，装配（读设定集 → 建世界 → 冻结快照）是有可能卡住的
    #   （磁盘、OneDrive 同步、杀软扫描都会），而卡住的表现就是"点了没反应"。
    #   超过这个秒数还没装配完，界面就**不再等**：把这一趟作废（后台那一趟
    #   落地前会对号，对不上自己退场），状态条回到可以重来的样子。
    #   ⚠ 不是"杀掉后台"：它多半卡在没有超时的等待上，硬杀杀不掉。
    #   默认 180 秒（正常机器十几秒就装完，给足慢机器与首次生成的余量）。
    # [EN] ★★ The **assembly timeout** for start-writing (the "timeout mechanism" the user named on
    # [EN] 2026-10-12):
    # [EN] "introduce a timeout mechanism; if the background never succeeds, the UI can stop waiting on
    # [EN] its own".
    # [EN] After clicking "start", assembly (read the settings collection -> build the world -> freeze a
    # [EN] snapshot) can get stuck (disk, OneDrive sync, antivirus scanning all can do it), and a stuck
    # [EN] assembly looks exactly like "nothing happened after clicking".
    # [EN] If it has not finished after this many seconds the UI **stops waiting**: it voids this launch
    # [EN] (the background pass re-checks before taking over and exits on a mismatch) and the status bar
    # [EN] returns to a retryable look.
    # [EN] ⚠ This is not "killing the background": it is most likely stuck on a wait with no timeout, so a
    # [EN] kill would not take.
    # [EN] Default 180 seconds (a normal machine finishes in ten-odd seconds; this leaves room for slow
    # [EN] machines and first-time generation).
    "LAUNCH_TIMEOUT_S": dict(group="运行边界", type="int", default=180, min=20, max=3600,
                             desc="点「开始推演」后**最多等多久**（秒）。装配超过这个时间"
                                  "还没完成，界面就停止等待（可以再点一次「起笔」）；"
                                  "后台那一趟会自己作废，不会偷跑。正常机器十几秒就装完，"
                                  "一般不用改"),
    "GAME_START_TIME": dict(group="时间系统", type="str", default=""),
    # 故事秒 / 真实秒。**1 = 实时**（故事时间和真实时间同速，一个故事日 ≈ 24 小时真实时间）；
    # 60 = 1 真实秒走 1 故事分钟（一个故事日 ≈ 24 分钟）。
    # ⚠ 这个值以前**只在"事件真的发生时"才兑现在时钟上**，而且软时钟下
    # `TIME_RATIO//60` 会退化成"每 tick 1 分钟" —— 8 秒能跑掉 2 小时故事时间（≈1000×）。
    # 现在时钟按**真实流逝 × TIME_RATIO** 走（见 `sim/loop.py::_advance_clock`），
    # 所以这个数字是"说多少就是多少"。
    # [EN] Story seconds / real seconds. **1 = real time** (story time and real time run at the same speed;
    # [EN] one story day ≈ 24 hours of real time);
    # [EN] 60 = 1 real second advances 1 story minute (one story day ≈ 24 minutes).
    # [EN] ⚠ This value used to be **cashed into the clock only "when an event actually happened"**, and
    # [EN] under the soft clock
    # [EN] `TIME_RATIO//60` would degrade to "1 minute per tick" -- 8 seconds could burn through 2 hours of
    # [EN] story time (≈1000×).
    # [EN] Now the clock runs by **real elapsed × TIME_RATIO** (see `sim/loop.py::_advance_clock`),
    # [EN] so this number is "exactly what it says".
    "TIME_RATIO": dict(group="时间系统", type="int", default=1, min=1, max=3600),
    "TICK_REAL_MS": dict(group="时间系统", type="int", default=1000, min=50, max=60000),
    # 一拍 = 多少**真实秒**的等待（2026-10-26 起 `TIME_RATIO` 只管演出速度，
    # 这一拍不再吃"故事秒"——故事时间由「这一站的跨度 ÷ 拍数」在每拍里推）。
    # 攒够一拍才做一次"决策"（一次决策 = 1~2 次 LLM 调用，所以它也是**花钱的节拍器**）。
    # ★ 默认 60（2026-10-29，用户："一天几分钟就推演结束了…每天演示不了多少故事"）。
    # ★★ 2026-10-30 更正上面那条推算：一天几拍 **不再固定 15~25**。
    #   设定集（或「起笔」）写了「每章字数」时，拍数 = 每章字数 ÷ 实测 550 字/拍
    #   （`ingest.progress.beats_for_words`，见 `director/day_plan._cap_by_words`）——
    #   一本"每章 2,500 字"的书一天就是 **5 拍**。60 秒一拍 ⇒ 一天 5 分钟、2,500 字；
    #   觉得太快就把它调大（150 → 一天 12 分钟），**别调 `TIME_RATIO`**（那是除在拍上的）。
    # [EN] ★ Default 60 (2026-10-29). ★★ 2026-10-30 correction: a day is **no longer always 15-25
    # [EN] beats**. When the book declares "words per chapter", beats = words / 550 measured chars per
    # [EN] beat, so a 2,500-word chapter means **5 beats a day** -- 5 minutes at 60 s. Raise this number
    # [EN] (150 -> 12 min) to watch slower; do NOT touch `TIME_RATIO` (it divides into the beat).
    "BEAT_SECONDS": dict(group="时间系统", type="int", default=60, min=1, max=3600),
    # ★★★ 2026-10-26 新增（用户选 A：**日界 = 拍预算用完**）。
    # 开（默认）：**这一站的拍演完就收一天的稿**。小说的"一天"＝这一天写出来的那些事，
    #   不再要求填满 24 小时 —— 详的站 60 拍、带过 1 拍，演完就过天。
    #   一拍推多久也不再恒定，而是「这一站的跨度时长 ÷ 这一站的拍数」：
    #   一场审讯（一场+详）= 一拍 2 分钟，三个月赶路（数月+带过）= 一拍 30 分钟 + 站末跳 89 天。
    # 关：逐字回到旧行为 —— 一拍恒定 `BEAT_SECONDS` 故事秒，跨 24 点才换天。
    #   ⚠ 旧行为实测一天演 **133 幕 / 21.3 万字**（用户：「小说时间不是匀速流逝的，
    #     现在这个模拟最大的问题就是这里」）。留着这个开关只为可回退与对照。
    # [EN] ★★★ Added 2026-10-26 (the user chose A: **the day ends when the beat budget runs out**).
    # [EN] On (default): **wrap up the day once this station's beats are played**. A novel's "day"
    # [EN] is what got written that day, not 24 filled hours -- `详` stations get 60 beats, `带过` 1.
    # [EN] The per-beat duration is no longer constant either: it is "the station's span / its beat
    # [EN] count", so one interrogation (`一场+详`) is 2 minutes a beat while three months on the road
    # [EN] (`数月+带过`) is 30 minutes a beat plus an 89-day jump at the station's end.
    # [EN] Off: byte-for-byte the old behaviour -- a constant `BEAT_SECONDS` per beat, day boundary on
    # [EN] midnight. ⚠ Measured, the old behaviour ran **133 acts / 213k characters in one day** (the
    # [EN] user: "novel time is not uniform; this is the biggest problem with the simulation"). The
    # [EN] switch exists only for rollback and comparison.
    "DAY_ENDS_ON_BEAT_BUDGET": dict(group="时间系统", type="bool", default=True),
    # 一拍最多推多少**故事分钟**（2026-10-26）。
    # ★ 这是"一拍"这个概念本身的边界，不是拍的：一拍 = 场景内的一个节拍
    #   （一个人做一件事、说一两句），一次换场/一段等待最多半小时。
    #   比这更长的"时间流逝"不是拍该干的活 —— 那是**过场**：站末把剩余时间一次跳掉
    #   （`sim/loop._flush_station_gap`），并推一句旁白让读者看见。
    # ⚠ 调大它会让"一场戏"里出现"过了两小时"这种一拍，读者会觉得戏被剪了。
    # [EN] The most story minutes one beat may advance (2026-10-26). This is the bound of the
    # [EN] *concept* "one beat": a beat is one pulse inside a scene (one person, one action, a line or
    # [EN] two), and a scene change or a wait is at most half an hour. Longer passages of time are not
    # [EN] a beat's job -- they are a **transition**, jumped at the station's end and narrated.
    # [EN] ⚠ Raising it puts "two hours passed" inside a single beat, which reads as a cut.
    "BEAT_MAX_MINUTES": dict(group="时间系统", type="int", default=30, min=1, max=24 * 60),
    # 全场都没人动时，隔多少**故事分钟**才写一次「片刻无话」——
    # 不设这个门槛，安静的时刻会把版面刷满（用户报过「满屏 没动，也没出声」）。
    # [EN] When no one moves at all, how many **story minutes** pass before writing 「片刻无话」once --
    "QUIET_MINUTES": dict(group="时间系统", type="int", default=5, min=0, max=240),
    # ★★★ 2026-10-14 新增（用户：「正常小说…应该有…**大量的环境**…不应该只有对话」）。
    #   每隔这么多**故事分钟**补一条环境白描（`AMBIENT`），
    #   **与"有没有人在动"无关** —— 原来环境只在"全场都没动"时才写
    #   （`QUIET_MINUTES` 那条），而推演里"有动静"是常态 ⇒ 环境几乎不出现。
    # ⚠ 单位是**故事分钟**，而默认 `TIME_RATIO=1`（故事 1 分钟 = 真实 1 分钟）
    #   ⇒ 填 1 就是"每真实 1 分钟一条"。
    #   填 0 = **关掉**这条通路（回到老行为：环境只在空场时出现）。
    # [EN] ★★★ Added 2026-10-14 (user: "a normal novel should have ... **a lot of environment**
    # [EN] ... it should not be only dialogue").
    # [EN] Every this many **story minutes**, emit one line of environmental description
    # [EN] (`AMBIENT`), **independent of whether anyone is moving** -- environment used to be written
    # [EN] only when "nobody moved at all" (the `QUIET_MINUTES` path), while "something is happening"
    # [EN] is the norm in a deduction => environment almost never appeared.
    # [EN] ⚠ The unit is **story minutes**, and the default `TIME_RATIO=1` (1 story minute = 1 real
    # [EN] minute) => 1 means "one line per real minute".
    # [EN] 0 = **turn this path off** (back to the old behavior: environment only in empty scenes).
    "AMBIENT_MINUTES": dict(group="时间系统", type="int", default=1, min=0, max=240),
    #: 同一句环境白描，隔多少条之后才可以**再出现**（0 = 永不复现，即旧行为）。
    #: ★★★ 2026-10-18：旧实现是"用过就永不"，而候选池实测只有 1–5 条
    #:   （`sound_design` 为空时 1 条）⇒ **一天最多 5 条环境句**，长跑 1080 拍也一样，
    #:   于是 `AMBIENT_MINUTES` 调多小都不会让环境变多 —— 那是个假旋钮。
    #:   实测：6 拍 54 条条目里只有 1 条环境句（真人样本约 20% 是环境/体感）。
    #:   ⚠ 别把它调小来"加环境"：池子就那么大，调小只会让同一句回来得更快。
    #:     真正的"空气"由演员的 `细节` 承担，这里只是兜底。
    # [EN] How many ambient lines must pass before **the same line may reappear**
    # [EN] (0 = never, the old behavior). ★★★ 2026-10-18: the old implementation was "used once,
    # [EN] never again", and the pool is measured at 1-5 lines => **at most 5 ambient lines per
    # [EN] day**, even in a 1080-beat run, so `AMBIENT_MINUTES` could not add any -- a fake knob.
    # [EN] Measured: 6 beats / 54 entries had 1 ambient line (a human sample is ~20%).
    # [EN] ⚠ Do not shrink it to "add environment": the pool is small, shrinking only makes the
    # [EN] same line return sooner. The real air comes from the actor's `细节`; this is a fallback.
    "AMBIENT_REPEAT_EVERY": dict(group="时间系统", type="int", default=24, min=0, max=9999),
    "AUTO_RUN_DAYS": dict(group="时间系统", type="int", default=0, min=0, max=999),
    "PAUSE_AT_NIGHT": dict(group="时间系统", type="bool", default=False),
    "AGENT_MAX": dict(group="Agent 核心", type="int", default=12, min=1, max=64),
    "MEMORY_RETRIEVE_K": dict(group="Agent 核心", type="int", default=8, min=1, max=64),
    "WEIGHT_RECENCY": dict(group="Agent 核心", type="float", default=1.0, min=0, max=5),
    "WEIGHT_IMPORTANCE": dict(group="Agent 核心", type="float", default=1.0, min=0, max=5),
    "WEIGHT_RELEVANCE": dict(group="Agent 核心", type="float", default=1.0, min=0, max=5),
    "RECENCY_DECAY": dict(group="Agent 核心", type="float", default=0.995, min=0.9, max=1),
    "IMPORTANCE_SCORING": dict(group="Agent 核心", type="enum", default="hybrid",
                               opt=["hybrid", "llm", "heuristic"]),
    "REFLECTION_THRESHOLD": dict(group="Agent 核心", type="int", default=100, min=0, max=100000),
    "REFLECTION_MAX_PER_DAY": dict(group="Agent 核心", type="int", default=2, min=0, max=20),
    "PLANNING_ENABLED": dict(group="Agent 核心", type="bool", default=True),
    # 当日剧本（2026-10-07）：跨天时**导演先定框架**（写当天要演的故事 → 改写成剧本
    # → 分派到人 → 验算），人物再在框架内自由发挥。
    # 关掉就退回老行为：每个人各自排计划，彼此不管（屏幕上容易变成"各做各的小事"）。
    # [EN] Daily script (2026-10-07): across day boundaries the **director sets the framework first**
    # [EN] (writes the day's story → rewrites it into a script
    # [EN] → assigns to people → verifies), then characters improvise freely within the framework.
    # [EN] Turn it off to fall back to old behavior: each person plans on their own, ignoring each other
    # [EN] (on screen this easily becomes "each doing their own small things").
    "DAY_PLAN": dict(group="Agent 核心", type="bool", default=True,
                     desc="跨天时先由导演写「当天要演的故事」并改写成剧本、分派到人；"
                          "关掉则退回各人自己排计划"),
    # ★ **今日任务分配**（2026-10-07 第八轮）：开演前把"今天谁负责哪几件事"
    #   推一张卡到中栏（用户白名单里的「导演工作分配」）。
    #   关掉则那块不出现（任务照旧写进各人的「今日计划」—— 人物自己看得见，
    #   只是读者看不到）。
    # [EN] ★ **Today's task assignment** (2026-10-07 round eight): before the show starts, take "who's
    # [EN] responsible for which things today"
    # [EN] Turn it off and that block doesn't appear (tasks are still written into each person's 「今日计划」--
    # [EN] characters can see them,
    # [EN] just not readers).
    "DAY_TASKS": dict(group="Agent 核心", type="bool", default=True,
                      desc="开演前把**今天分到谁头上是哪几件事**推一张卡到中栏"
                           "（用户白名单里的「导演工作分配」）；"
                           "关掉则只写进人物自己的「今日计划」，不上屏"),
    # 验算不过关时最多重写几轮。0 = 不重写（只验一次，把问题记下来）。
    # 别调大：写不出更好的就是写不出，那笔钱留给推演更值。
    # [EN] How many rounds of rewriting at most when verification fails. 0 = no rewriting (verify once
    # [EN] only, record the issues).
    # [EN] Don't raise it: if it can't write better, it can't; that money is better spent on simulation.
    "DAY_PLAN_FIX_ROUNDS": dict(group="Agent 核心", type="int", default=2, min=0, max=5,
                                desc="当日剧本验算不过关时，带意见重写的最多轮数"),
    # ── 前情提要（2026-10-07 用户提的粒度要求）──
    #   原话：「前情提要内容要小 是针对已经发生的最近今天或者一段时间的故事的总结
    #          除非第一章 否则不要用很大的背景故事来作为前情提要」。
    #   以前这个上限写在 `director/day_plan._recap_text(limit=3000)` 里 ——
    #   3000 字，屏幕上是一大段，完全不是"提要"。而且它是**从尾部截**，
    #   于是"最近三天"里只剩最后一天的后半句。现在按天分配额度。
    # [EN] -- Recap (2026-10-07 user's granularity requirement) --
    # [EN] This limit used to live in `director/day_plan._recap_text(limit=3000)` --
    # [EN] 3000 chars, a big wall of text on screen, not a "recap" at all. And it was **truncated from the
    # [EN] tail**,
    # [EN] so "the last three days" would leave only the second half of the last day's final sentence. Now
    # [EN] the quota is allocated per day.
    "RECAP_MAX_CHARS": dict(group="Agent 核心", type="int", default=240, min=60, max=1200,
                            desc="「前情提要」总字数上限。**要小** —— 它是提要不是梗概，"
                                 "几天的内容按天平分这个额度"),
    "RECAP_DAYS": dict(group="Agent 核心", type="int", default=3, min=1, max=14,
                       desc="前情提要往回取几天（跨天摘要）。取最近这几天，"
                            "不是取全书"),
    # ── 对话衔接（2026-10-07，见 `world/state.recent_text`）──
    #   用户原话：「所有人说话都给我一种一直在自说自话的感觉，正常应该是有一个
    #   事情大家都对这个事情进行讨论，互相针对别人说的话回应……造成的结果
    #   就是看对话很割裂」。
    #   根因：人物决策时**看不到别人刚说了什么**（输入里只有场景、在场名单、
    #   自己的记忆）—— 于是"针对别人的话回应"在物理上就不可能发生。
    #   开 = 决策提示词里多一段 `[刚才]`（场上最近说了什么），
    #   并且**被点名的人优先被选去决策**（有来有回）；
    #   关 = 与从前一字不差（那段不出现，挑人回到纯随机）。
    # [EN] -- Dialogue continuity (2026-10-07, see `world/state.recent_text`) --
    # [EN] Root cause: when making decisions, characters **can't see what others just said** (input only
    # [EN] has the scene, present list,
    # [EN] their own memory) -- so "responding to others' words" is physically impossible.
    # [EN] On = the decision prompt gains a `[刚才]` section (what was recently said on stage),
    # [EN] and **the person named gets priority when choosing who decides** (back-and-forth);
    # [EN] Off = identical to before, word for word (that section doesn't appear, picking reverts to pure
    # [EN] randomness).
    "DIALOGUE_CONTEXT": dict(group="Agent 核心", type="bool", default=True,
                            desc="把「刚才场上说了什么」放进人物决策提示词，"
                                 "并让被点名的人优先答话（关掉退回"
                                 "「各说各的」的老行为）"),
    "DIALOGUE_CONTEXT_LINES": dict(group="Agent 核心", type="int", default=6,
                                   min=0, max=8,
                                   desc="`[刚才]` 那段最多给几条（0 = 不给）。"
                                        "留太多会变成流水账，越早的话越没人看"),
    # ★ 重复台词的处理（2026-10-07）——
    #   去重护栏只认"一模一样"，分不清"模型偷懒复读"和"这句话非说不可"。
    #   以前一律丢：丢掉的代价是**那一拍可能整拍空白**。
    #   现在改成：把决定权交回人物 —— 让他"重新想清楚当前情况"再说一次；
    #   若他仍坚持原话，就是"必须重复"，放行。
    # [EN] ★ Handling repeated lines (2026-10-07) --
    # [EN] The dedup guard only recognizes "exactly identical" and can't tell "the model is lazily looping"
    # [EN] from "this line must be said".
    # [EN] Previously it always dropped them: the cost of dropping was that **that beat might be completely
    # [EN] blank**.
    # [EN] Now it's changed to: hand the decision back to the character -- have them "re-think the current
    # [EN] situation" and say it again;
    # [EN] if they still insist on the original line, it's "must repeat", and it's allowed through.
    "DIALOGUE_RETRY_DUP": dict(group="Agent 核心", type="bool", default=True,
                               desc="人物说了已说过的话时，先让他重新想清楚"
                                    "当前情况、换一句再说；仍坚持原话就当他"
                                    "非说不可（关掉则直接丢掉那句）"),
    "DIALOGUE_RETRY_MAX": dict(group="Agent 核心", type="int", default=2,
                               min=0, max=4,
                               desc="一拍最多让几个人重说（安全阀：重说要多花"
                                    "一次调用；0 = 不重说，等同关掉）"),
    # 目标金字塔：决策提示词里给人物看**几层**目标（由近及远：此刻 / 这一站 /
    # 今日计划 / 这一程 / 你想要的）。3 = 与老行为对齐（新增「此刻」那一层）。
    # [EN] Goal pyramid: how many **layers** of goals the character sees in the decision prompt (near to
    # [EN] far: this moment / this stop /
    # [EN] today's plan / this journey / what you want). 3 = aligned with old behavior (plus the newly
    # [EN] added 「此刻」layer).
    "GOAL_LADDER": dict(group="Agent 核心", type="int", default=3, min=2, max=5,
                        desc="决策提示词里给人物几层目标（目标金字塔，2~5 层；"
                             "由近及远：此刻 / 这一站 / 今日计划 / 这一程 / 你想要的）"),
    "PLAN_BLOCK_MINUTES": dict(group="Agent 核心", type="int", default=30, min=5, max=480),
    # ══════════════════════════════════════════════════════════════════
    #  剧组（2026-10-07）
    # [EN] Crew (2026-10-07)
    # ══════════════════════════════════════════════════════════════════
    # 一句话：**把推演组织成一个能出活的影视公司**，而不是一堆各说各话的提示词。
    # [EN] In one sentence: **organize the simulation into a film-and-TV company that can ship work**, not
    # [EN] a pile of prompts each talking to itself.
    # 名册（谁是干什么的、接到软件的哪个东西、产出交给谁）在 `crew/roster.py`；
    # 各职位的实现与提示词在 `crew/agents.py`；排班与台账在 `crew/studio.py`。
    # 界面上的「剧组」面板显示的**就是这份名册**（不是另画一套）。
    # [EN] The roster (who does what, which software thing they hook into, who gets their output) is in
    # [EN] `crew/roster.py`;
    # [EN] each role's implementation and prompts are in `crew/agents.py`; scheduling and ledger are in
    # [EN] `crew/studio.py`.
    # [EN] The 「剧组」panel in the UI displays **exactly this roster** (not a separately drawn one).
    # ⚠ 与 `DAY_PLAN` 的关系：那一天里写故事/改剧本两步**本来就是**剧组流程
    #   （小说作家 → 剧作者 → 导演验算）。`DAY_PLAN` 现在指的是"要不要走编剧组"；
    #   关掉它，剧组里剩下的职位（场记/道具/美术/宣发）照样出工 ——
    #   两条线是分开的，别把它们并成一个开关（那样关一个会连带关掉另一个）。
    # [EN] ⚠ Relation to `DAY_PLAN`: the two steps of writing the story / rewriting the script that day
    # [EN] **were always** the crew flow
    # [EN] (novelist → screenwriter → director verification). `DAY_PLAN` now means "whether to go through
    # [EN] the writing crew";
    # [EN] turn it off and the remaining roles in the crew (script supervisor / props / art / publicity)
    # [EN] still work --
    # [EN] the two lines are separate; don't merge them into one switch (that would turn one off along with
    # [EN] the other).
    "CREW": dict(group="剧组", type="bool", default=True,
                 desc="启用剧组：小说作家写样章 → 剧作者改成能拍的剧本 → "
                      "导演定框架，另有场记/道具/美术/宣发各司其职"),
    # ★★ 2026-10-10 用户点名要的两条（**全局**：这是"剧组怎么写"的方法，
    #    与某一本书无关，所以放全局而不是项目里）。
    # [EN] ★★ Two things the user specifically asked for on 2026-10-10 (**global**: this is the method for
    # [EN] "how the crew writes",
    # [EN] unrelated to any particular book, so it goes global rather than in the project).
    "CREW_SCENE_CARD": dict(group="剧组", type="bool", default=True,
                            desc="小说作家写样章时**先把场景交代清楚**（谁在哪、器物在哪一侧、光从哪来）"
                                 "—— 标准是**美术据此能画出当天地图**。关掉则回到从前（只写气氛）"),
    "CREW_FILMABLE": dict(group="剧组", type="bool", default=True,
                          desc="顺手把样章写得**能拍**（一场一事 / 只写拍得到的 / "
                               "对白写出话 / 不用「与此同时」跳）"
                               "—— 给剧作者分场、给演员念台词用。关掉会更散文、更难改成剧本"),
    # ★★ 2026-10-12 用户点名：真人说话会犹豫、不是每句都回应、速度不会太快、
    #    说话习惯由性格决定；而"很多 AI 生成的"对白**没有卡顿、很快、从不犹豫**，
    #    还**很容易吼** ⇒ 一听就不是人。这一条把"怎么说才像活人"写成**跨职位**的
    #    硬约束（**全局**：这是"话该怎么说"的方法，与某一本书无关，
    #    所以放全局而不是项目里 —— 与 `CREW_FILMABLE` 同类）。
    # [EN] ★★ 2026-10-12, named by the user: real people hesitate, do not answer every line, do not talk
    # [EN] fast, and their speech habits follow their character; whereas "much AI-generated" dialogue has
    # [EN] **no stumbles, is fast, never hesitates**, and **shouts easily** ⇒ it sounds non-human. This
    # [EN] turns "how to speak like a live person" into a **cross-position** hard constraint (**global**:
    # [EN] it is the method of "how a line should be said", unrelated to any particular book, so it goes
    # [EN] global rather than in the project -- same category as `CREW_FILMABLE`).
    "CREW_LIVE_SPEECH": dict(group="剧组", type="bool", default=True,
                             desc="让台词**像活人说的**（卡顿与改口落在关键处 / 不必每句都接 / "
                                  "默认平常声量·吼要付代价 / 一次说一件事 / "
                                  "停顿与口气写在纸上 / 对谁说话换一副样子）"
                                  "—— 小说作家、剧作者、演员、审读**同一条**。关掉则回到从前"),
    # ★★★ 2026-10-28（叙事层，来自 StoryScope 61,608 篇对照实验 + sepia 的 narrative-pass）：
    #   机器味的**大头在结构不在词句** —— 只把表面词句换干净，识别率仅从 95.5% 降到
    #   93.9%（1.6 个点）；而只给分类器看叙事结构，准确率仍有 93.2%。
    #   ⇒ 上面那条 `CREW_LIVE_SPEECH` 治的是"一句话怎么说"（最外层皮），
    #     这一条治的是"故事怎么搭"（最里层）：情绪别只会写身子、天气就是天气、
    #     别把意思点破、给一处真东西，外加两条"别改过头"。
    #   ⚠ 只挂**小说作家与剧作者**，不挂演员（长段落离输出太远会被忽略）。
    # [EN] ★★★ 2026-10-28 (narrative layer, from StoryScope's 61,608-story controlled experiment +
    # [EN] sepia's narrative-pass): the bulk of the machine smell is **structure, not wording** --
    # [EN] rewording the surface only moves detection from 95.5% to 93.9% (1.6 points), while a
    # [EN] classifier given narrative structure alone still reaches 93.2%.
    # [EN] => `CREW_LIVE_SPEECH` above treats *how one line is said* (outermost layer); this one
    # [EN] treats *how the story is built* (innermost): emotion is not only the body, weather is
    # [EN] weather, do not spell the theme out, name one real thing, plus two "do not over-correct"
    # [EN] rules. ⚠ Mounted on **novelist and playwright only**, never the actor.
    "CREW_ANTI_FP": dict(group="剧组", type="bool", default=True,
                         desc="叙事层去机器味（情绪四种写法混用·身子上的反应全书只留一两处 / "
                              "天气就是天气·气味要省 / 别跳出来替读者总结意思 / "
                              "点出一件真有的东西 / 且**一章只挑三五处改、别改过头**）"
                              "—— 小说作家与剧作者**同一条**。关掉则回到从前"),
    "CREW_CONTINUITY": dict(group="剧组", type="bool", default=True,
                            desc="场记每日连戏检查（时间·物件·称呼·在场状态·与前情矛盾）"
                                 "—— **只报不改**，提请作者注意"),
    "CREW_PROPS": dict(group="剧组", type="bool", default=True,
                       desc="道具每日出单（这一场有哪些具体物件、哪件要反复出现）"
                            "—— 产出会进出图提示词，画面里真的会多出这些东西"),
    "CREW_ART": dict(group="剧组", type="bool", default=True,
                     desc="美术定这部的画风与主色（一次定、全剧用），"
                          "让各天的出图保持一致"),
    "CREW_RESEARCH": dict(group="剧组", type="bool", default=True,
                          desc="资料员每日考据（名物·制度·称谓站不站得住）；"
                               "查不到会明说查不到，不编"),
    "CREW_PUBLICITY": dict(group="剧组", type="bool", default=True,
                           desc="宣发写一句话卖点、看点、预告（收工与导出时出）"),
    # ★★ 2026-10-10（用户：「拆书功能落地之后 你还得修改相关Agent，让他们在
    #    需要的时候选择合适的SKILL用起来」）——**全局**：这是"剧组怎么用技能"的
    #    方法，与某一本书无关，所以放全局而不是项目里（与 `CREW_SCENE_CARD` 同类）。
    # [EN] the method, unrelated to any particular book, so it goes global rather than in the project (same
    # [EN] category as `CREW_SCENE_CARD`).
    "CREW_SKILL_ROUTE": dict(group="剧组", type="bool", default=True,
                             desc="各职位**按自己这一刻的活儿**从 `skills/` 里挑合适的"
                                  "知识包（题材 + 职位的关心点 + 你在书斋手写的那几句"
                                  "一起进检索）。挑不到就不给 —— 见运行文件夹里的"
                                  "《本书可用的技能.md》；关掉则完全不查技能"),
    "CREW_SKILL_LIMIT": dict(group="剧组", type="int", default=2, min=1, max=5,
                             desc="每个职位最多带几份知识包进提示词"
                                  "（一张卡五 K，十二个职位全塞进去会把注意力淹掉）"),
    # ── 设定分层（2026-10-07，见 `world/layers.py`）──
    #   用户：「我导入的设定文件夹…包括很大的设定 也包括很细节的设定 你要自己分层管理
    #          有些很大的背景只在后台特定的时候发挥作用 具体每天的故事可能是由很小的
    #          设定影响的」
    #   开 = 设定按作用范围分四层（世界/主线/场景/细节），大背景平时只给一句
    #   "气候"、只在开篇·高潮日·每 3 天展开；细节层每天都出场。
    #   关 = **行为与从前一字不差**（仍旧是一整段世界观取前 500 字）。
    # [EN] -- Setting layering (2026-10-07, see `world/layers.py`) --
    # [EN] On = settings are split into four layers by scope (world / mainline / scene / detail); big
    # [EN] backdrops usually give only one line of
    # [EN] "climate" and are expanded only at the opening, on climax days, and every 3 days; the detail
    # [EN] layer appears every day.
    # [EN] Off = **behavior identical to before, word for word** (still one whole block of worldview, first
    # [EN] 500 chars).
    "SETTING_LAYERS": dict(group="Agent 核心", type="bool", default=True,
                           desc="设定分层：大背景平时只当气候（开篇·高潮日·每 3 天"
                                "才展开），细节层每天都出场；关掉则退回"
                                "「一整段世界观取前 500 字」的老做法"),
    "CREW_SETTING_TALK": dict(group="剧组", type="bool", default=True,
                              desc="编剧室：导演·小说作家·剧作者三方会审，"
                                   "为该推进的故事补**局部**设定（只进场景层/细节层，"
                                   "动不了总体设定）"),
    "CREW_SETTING_EVERY_DAYS": dict(group="剧组", type="int", default=2, min=1, max=30,
                                    desc="编剧室每几天会审一次（1 = 每天；"
                                         "没有需要时它会返回空，只花一次摘要档调用）"),
    # 样章的长度区间。**下限是"够拆成几拍"**，不是文采要求；
    # 上限防它写成中篇（后一步要把它整个读进去，越长越贵）。
    # [EN] Length range for sample chapters. **The lower bound is "enough to split into a few beats"**, not
    # [EN] a literary requirement;
    # [EN] the upper bound prevents it from becoming a novella (the next step reads it in full; the longer
    # [EN] it is, the more expensive).
    "SHOW_NOVEL_IN_WINDOW": dict(group="推演窗口", type="bool", default=True,
                                desc="把推演写成的小说**自动推送到推演窗口**（收工时 / 点停止时）。关掉就只落盘、不占窗口。"),
    "NOVEL_WINDOW_OPEN": dict(group="推演窗口", type="bool", default=False,
                              desc="推送到窗口的那篇小说**默认展开还是收起**。默认收起：几百到几千字，展开会把正在看的戏挤出屏幕；想看的人点一下标题就展开。"),
    # ⚠ 2026-10-26 删掉 `WRAP_WAIT_SECONDS`：**它只有判据在读，产品源码一次都没读过**
    #   （`config_sweep` 的 D1 就是这么抓到的）。一个用户拧了却什么都没变的旋钮，
    #   比没有这个旋钮更坏 —— 正是本项目删那 28 个假旋钮的同一条理由。
    #   判据那边的等待上限改成它们自己的常量（见 `tools/verify_run_control.py` 的
    #   `WRAP_WAIT_LIMIT`），不再借产品的配置项当自己的旋钮。
    # [EN] ⚠ Removed `WRAP_WAIT_SECONDS` on 2026-10-26: **only criteria read it, the product
    # [EN] source never did** (caught by `config_sweep` D1). A knob the user can turn with no
    # [EN] effect is worse than no knob at all -- the same reason the 28 fake knobs were deleted.
    # [EN] The criteria now use their own constant (`WRAP_WAIT_LIMIT` in verify_run_control.py).
    "CREW_STORY_MIN": dict(group="剧组", type="int", default=180, min=60, max=2000,
                           desc="小说作家每天写的原著样章最少多少字"),
    "CREW_STORY_MAX": dict(group="剧组", type="int", default=600, min=200, max=4000,
                           desc="原著样章最多多少字"),
    # 接受样章的字数底线（低于它就算"没写出来"）。比 `CREW_STORY_MIN` 松：
    # 提示词里说 180 字，模型写 120 字也是能用的东西 ——
    # **别因为差几十字就把它扔掉**（那等于白花一次调用）。
    # [EN] The minimum word count to accept a sample chapter (below this it counts as "not written").
    # [EN] Looser than `CREW_STORY_MIN`:
    # [EN] The prompt says 180 characters; if the model writes 120 it's still usable stuff --
    # [EN] **Don't throw it away just because it's a few dozen characters short** (that wastes a whole
    # [EN] call).
    "CREW_STORY_MIN_FLOOR": dict(group="剧组", type="int", default=80, min=10, max=2000,
                                 desc="样章低于多少字就算没写出来（宽容下限）"),
    "CREW_MAX_BEATS": dict(group="剧组", type="int", default=6, min=1, max=20,
                           desc="剧作者最多分几拍（拍太多等于把一天写死，"
                                "人物没有发挥空间）"),
    # ★★★ 2026-10-15（用户）：「如果某些Agents特别是一些临时不可用不影响后续工作流程
    #   的Agents 比如 美工 场记等 设置一个超时时间比如300秒 超时之后就暂时跳过它的工作」。
    #   加在 `studio.call()`（所有出工的**唯一入口**）—— 非阻塞 Agent 的 `member.run()`
    #   包在 `asyncio.wait_for()` 里，超时直接 `CrewNote(ok=False, why='超时跳过')`。
    #   ★ 不影响阻塞 Agent（director / novelist / actor 等），只作用在 `NONBLOCK_ROLES` 上。
    # [EN] ★★★ 2026-10-15 (user): "if certain agents -- especially ones whose temporary unavailability
    # [EN] doesn't affect the workflow, like art director, continuity -- set a timeout like 300s; once
    # [EN] timed out, skip their work." Applied in `studio.call()` (the **sole entry point** for all work)
    # [EN] -- non-blocking agents' `member.run()` is wrapped in `asyncio.wait_for()`, and on timeout
    # [EN] returns `CrewNote(ok=False, why='超时跳过')`.
    # [EN] ★ Does not affect blocking agents (director / novelist / actor etc.), only acts on
    # [EN] `NONBLOCK_ROLES`.
    "CREW_STAGE_TIMEOUT": dict(group="剧组", type="int", default=300,
                               min=0, max=3600,
                               desc="非阻塞 Agent（美工/场记/道具等）出工的**总预算**（秒）"
                                    "—— 0 = 不限（只用 LLM 层的超时）。"
                                    "⚠ 是**总共**等这么久（重试也在这个预算内），"
                                    "不是「每次窗口」：默认 300s + 重试 1 次 = 每次 150s，"
                                    "合起来仍是 300s。超时后该职位标记为跳过，不堵后面的人。"),
    # ★★★ 2026-10-15（用户）：「还有 我希望加入超时重试」。
    #   非阻塞 Agent 超时后**先重试 N 次**再跳过；重试**不额外延长**总时长
    #   （每次窗口 = 剩余预算 ÷ 剩余次数）。
    # [EN] ★★★ 2026-10-15 (user): "I also want timeout retries."
    # [EN] Non-blocking agents **retry** N times before skipping; retries do **not** extend the total
    # [EN] (each window = remaining budget / remaining attempts).
    "CREW_STAGE_RETRIES": dict(group="剧组", type="int", default=1,
                               min=0, max=5,
                               desc="非阻塞 Agent 超时后重试几次（0 = 不重试，直接跳过；"
                                    "1 = 重试 1 次，共试 2 次）。"
                                    "⚠ 重试**不延长总时长**，只是把预算切成几段用。"),
    # ── 各职位的输出上限（token）。都是**安全网**不是目标值：
    #    实测一段 400 字的中文约 600 token，这里给的都是两倍以上余量。
    # [EN] -- Output cap per role (tokens). All are **safety nets**, not target values:
    # [EN] Measured: a 400-character Chinese passage is about 600 tokens; everything here gives more than
    # [EN] double the margin.
    "CREW_STORY_TOKENS": dict(group="剧组", type="int", default=2400, min=400, max=8000),
    "CREW_SCRIPT_TOKENS": dict(group="剧组", type="int", default=4000, min=400, max=8000),
    "CREW_CONTINUITY_TOKENS": dict(group="剧组", type="int", default=2000, min=200, max=4000),
    "CREW_PROPS_TOKENS": dict(group="剧组", type="int", default=1600, min=200, max=4000),
    "CREW_ART_TOKENS": dict(group="剧组", type="int", default=1400, min=200, max=4000),
    "CREW_RESEARCH_TOKENS": dict(group="剧组", type="int", default=1600, min=200, max=4000),
    "CREW_PUBLICITY_TOKENS": dict(group="剧组", type="int", default=1400, min=200, max=4000),
    # 编剧室会审的输出上限（一个讨论 + 最多 4 条短设定的 JSON）
    # [EN] Output cap for the writers' room review (a discussion + a JSON of at most 4 short settings).
    "CREW_SETTINGS_TOKENS": dict(group="剧组", type="int", default=2600, min=300, max=6000),
    # 群众演员投人的输出上限（一件 JSON，三个短字段，余量很大）。
    # [EN] Output cap for extras casting (one JSON, three short fields, lots of margin).
    "CREW_EXTRA_TOKENS": dict(group="剧组", type="int", default=1000, min=100, max=3000),
    # ★ 群众演员**投人**的开关（`crew` 之外单独一个，因为它是**每拍可能触发**的：
    #   客流一多就会连着投人，是剧组里唯一有"频率"风险的那一项）。
    #   关掉不影响别的职位，门外照旧按老规矩（从固定池抽）出人。
    # [EN] ★ Switch for extras **casting** (separate from `crew` because it's **potentially triggered every
    # [EN] beat**:
    # [EN] once foot traffic picks up, casting fires repeatedly -- the only item in the crew with a
    # [EN] "frequency" risk).
    # [EN] Turning it off doesn't affect other roles; outside the door people are still produced by the old
    # [EN] rules (drawn from a fixed pool).
    "CREW_EXTRA_CASTING": dict(group="剧组", type="bool", default=True,
                               desc="门外的新面孔由「群众演员」按剧情投人"
                                    "（关掉则退回从固定池抽 —— 省 token，"
                                    "但每次来的路人都长一个样）"),
    # ★ **剧组产出往剧情窗口（中栏）推多少**（2026-10-07 改成分级）。
    # [EN] ★ **How much crew output is pushed to the story window (middle column)** (changed to tiers on
    # [EN] 2026-10-07).
    # 用户：「中间剧情对话窗口尽可能少出现演职人员 除非必要」——
    # 以前这里是个 bool（默认 true = **全都推**），于是中栏里塞满
    # 「（剧组 · 美术）…」「（剧组 · 道具）…」，读起来像拍摄现场的花絮，
    # 而不是小说。而作者要读的是**故事**。
    # [EN] User: "In the middle story dialogue window, show cast and crew as little as possible unless
    # [EN] necessary" --
    # [EN] this used to be a bool (default true = **push everything**), so the middle column was stuffed
    # [EN] with
    # [EN] "(crew · art) ..." "(crew · props) ...", which reads like behind-the-scenes footage of a shoot
    # [EN] rather than a novel. But what the author wants to read is the **story**.
    # 三档的分界是"它是不是故事的一部分"：
    #   · `off`  —— 一条都不推（只落盘 + 台账 + 状态栏）
    #   · `key`  —— **只推必要的**（默认）：出错 / 没出活 / 每日复盘 / 去AI审计命中
    #   · `full` —— 旧行为（所有产出都推）
    # 产出**照旧落盘**（`剧组台账.md` / `道具单.md` / …），与上屏是两件事。
    # [EN] The dividing line between the three tiers is "is it part of the story":
    # [EN] · `off`  -- push nothing (only persist to disk + ledger + status bar)
    # [EN] · `key` -- **push only what's necessary** (default): errors / no output produced / daily review
    # [EN] / de-AI audit hits
    # [EN] · `full` -- old behavior (push all output) [EN] Output is **still persisted to disk** (`剧组台账.md` / `道具单.md` / ...); that's separate from
    # [EN] on-screen display.
    "CREW_SCREEN": dict(group="剧组", type="enum", default="key",
                        opt=["off", "key", "full"],
                        desc="剧组产出推到剧情窗口的程度："
                             "off=一条都不推（只落盘）· key=只推必要的"
                             "（出错/没出活/复盘/去AI命中）· full=全都推（旧行为）"),
    # ★★★ 2026-10-23（用户点名）：剧组消息**前面的展开箭头**。
    #   用户原话：「所有非演员Agent的各个剧组Agent的消息在最前面加上展开收起来三角号，
    #   展开后向下…… 我点开这个按钮以后应该是 LLM 的思考过程流式返回，
    #   已经完成的消息（比如 xx 已交工）我点击展开是这一步的执行结果」。
    #   ⇒ 关掉它就回到"只有一行状态、点不开"的旧样子（消息本身照旧）。
    # [EN] ★★★ 2026-10-23 (named by the user): the **expand arrow in front of crew
    # [EN] messages**. Turning it off restores the old "one status line, not clickable"
    # [EN] look (the message itself stays).
    "CREW_EXPAND": dict(group="剧组", type="bool", default=True,
                        desc="剧组/剧务消息**前面带一个折叠箭头**：点开看"
                             "「正在出工时 LLM 的思考过程（流式）」或"
                             "「这一步的执行结果」。关掉就只有一行状态、点不开"),
    "CREW_STREAM": dict(group="剧组", type="bool", default=True,
                        desc="剧组出工时**用流式接收**（展开框里的思考才会逐字出现）。"
                             "关掉=等整段返回（展开框点开时已经有全文，看不到过程）。"
                             "个别网关不支持流式会自动退回整段，不影响推演"),
    # ── 剧组新补的四位（2026-10-07；见 `crew/roster.py` 的职责说明）──
    # [EN] -- The four new crew roles (2026-10-07; see the role descriptions in `crew/roster.py`) --
    "CREW_REVIEW": dict(group="剧组", type="bool", default=True,
                        desc="**复盘**：每天收工时出「今日总结」（剧情总结 + "
                             "存在的问题 + 后续修改意见），并可在必要时改当天的戏。"
                             "⚠ 它是这件事**唯一**的开关 —— 别再加一个 DAY_REVIEW，"
                             "两个开关表达同一件事就是上次删掉的那种假旋钮"),
    "CREW_STYLIST": dict(group="剧组", type="bool", default=True,
                         desc="**造型**：人物身上的东西（衣着·随身物·仪态），"
                              "喂给美术与出图提示词 —— 道具管物件，造型管人"),
    "CREW_SOUND": dict(group="剧组", type="bool", default=True,
                       desc="**声音**：这一场的声音层（环境音·静默·声音的转折），"
                            "喂给场景的环境句"),
    "CREW_POLISH": dict(group="剧组", type="bool", default=True,
                        desc="**语言审校**：读当天样章，点名哪几句 AI 味重、"
                             "该怎么改（去 AI 库的每日深查；改不改由你定）"),
    "CREW_REVIEW_TOKENS": dict(group="剧组", type="int", default=2200, min=300, max=6000),
    "CREW_STYLIST_TOKENS": dict(group="剧组", type="int", default=1400, min=200, max=4000),
    "CREW_SOUND_TOKENS": dict(group="剧组", type="int", default=1400, min=200, max=4000),
    "CREW_POLISH_TOKENS": dict(group="剧组", type="int", default=2000, min=300, max=6000),
    # ── 排练（2026-10-07）──
    #   用户 2026-10-07：「排练你是说剧本出来所有人先快速走一遍但是不出现结果
    #   在窗口里吗？如果是的话可以加排练这个阶段。」
    # [EN] -- Rehearsal (2026-10-07) --
    # [EN] User 2026-10-07: "For rehearsal you mean once the script is out everyone quickly walks through
    # [EN] it but without results
    # [EN] appearing in the window? If so, go ahead and add a rehearsal stage."
    "CREW_REHEARSAL": dict(group="剧组", type="bool", default=True,
                           desc="**排练**：剧本定稿后、开演前，把这一天**空走一遍**"
                                "（谁做不到 / 人不在场 / 写死了台词）——"
                                "**不产生正文、不上中栏**，只落 `排练记录.md` 与日志；"
                                "排不过去就带意见退回剧作者重写"),
    "CREW_REHEARSAL_TOKENS": dict(group="剧组", type="int", default=1800,
                                  min=300, max=6000),
    "CREW_REHEARSAL_ROUNDS": dict(group="剧组", type="int", default=1, min=0, max=3,
                                  desc="**排练不过就重写**最多几轮（0 = 排完只记"
                                       "不改）。它与 `DAY_PLAN_FIX_ROUNDS`（导演验算"
                                       "的轮数）是两件事：一个从**能不能演**挑毛病，"
                                       "一个从**故事顺不顺**挑毛病"),
    "CREW_STORYBOARD": dict(group="剧组", type="bool", default=True,
                           desc="**分镜师**：剧本定稿后、开演前，把分拍拆成**镜头清单**"
                                "（景别 / 画面描述 / 台词 / 镜头运动），落 `分镜.md`；"
                                "开源漫剧流程里「剧本→分镜」这一步——让导演与演员"
                                "在演之前先有「每一镜怎么拍」"),
    "CREW_STORYBOARD_TOKENS": dict(group="剧组", type="int", default=1800,
                                  min=300, max=6000),
    "CREW_VISREF": dict(group="剧组", type="bool", default=True,
                        desc="**视觉参考图**：分镜定稿后，为出场人物 / 关键场景生成"
                             "**一致性参考图**（接 image_gen），落 `视觉参考.md` + 图片；"
                             "开源漫剧流程里「分镜→视觉（角色/场景）」这一步——"
                             "下游生图 / 视频有统一参照，不每次重新瞎画"),
    # ★★★ 2026-10-17 **删掉了 `CREW_VISREF_TOKENS`** —— 它是真·假旋钮：
    #   `crew/agents.VisualRef.work()` **一次模型都不调**（它直接调 `image_gen`
    #   生成图片，产出的是图片 + 一份清单 markdown），所以"最多写多少 token"
    #   在逻辑上根本没有落点。`verify_config_sweep` 的 D1 一直在报它（"零读取"），
    #   而用户界面上又看得见一个数字框 —— 改了什么都不发生。
    #   按本项目"对假按钮零容忍"的规矩：**没有语义就删掉**，不补一个勉强的用途。
    # [EN] ★★★ 2026-10-17 **removed `CREW_VISREF_TOKENS`** -- a genuine fake knob:
    # [EN] `crew/agents.VisualRef.work()` **calls no model at all** (it calls `image_gen` to produce
    # [EN] images plus a markdown list), so "how many tokens to write at most" has nowhere to land.
    # [EN] `verify_config_sweep` D1 kept reporting it as "zero reads", while the user sees a number
    # [EN] box in the UI that changes nothing. Per this project's "zero tolerance for fake buttons"
    # [EN] rule: **delete what has no semantics** rather than inventing a strained use.
    "CREW_DAY_NOVEL": dict(group="剧组", type="bool", default=True,
                           desc="**当天这一章**：收工时把这一天的戏整理成**小说形式**"
                                "（落 `当天故事.md`，按天累积；「今日总结」里也带一节）。"
                                "它与导出的最终改写稿是两件事：这份是**作者回头读**的"),
    "CREW_DAY_NOVEL_TOKENS": dict(group="剧组", type="int", default=6000,
                                  min=400, max=16000,
                                  desc="**整理当天这一章**时**每一块**最多写多少 token。"
                                       "它是**输出**上限：太小会把一天的戏写成一段摘要"
                                       "（2026-10-17 之前默认 2600，实测一天 4.4 万字的材料"
                                       "被写成 900 字）。分块后每块都按这个上限写"),
    "CREW_DAY_NOVEL_CHUNK": dict(group="剧组", type="int", default=6000,
                                 min=0, max=40000,
                                 desc="整理当天这一章时**多少字一块**（0 = 不分块，整段一次交给模型）。"
                                      "分块是为了让模型**每一段都写完整**而不是挑几段写；"
                                      "设 0 适合上下文很大的模型"),
    # ══════════════════════════════════════════════════════════════════
    #  剧本审读（2026-10-08）
    # [EN] Script review (2026-10-08)
    # ══════════════════════════════════════════════════════════════════
    # 用户原话：「你看是否有独立的Agent 而不是导演在盯着演员说的每一句话
    #   没有就做一个 **在演员真的说出来之前**，把新生成的话放到已经出现的话里
    #   过一遍，看是否通顺 而且这个Agent要**一直记录生成的所有信息**…
    #   **不是就不要放出来**」。
    # [EN] User's original words: "See whether there's an independent Agent rather than the director
    # [EN] watching every line the actors say
    # [EN] if not, make one that **before the actor actually says it**, puts the newly generated line among
    # [EN] the lines already shown
    # [EN] and checks whether it reads smoothly, and this Agent must **keep recording all information
    # [EN] generated**...
    # [EN] **if not, don't let it out**".
    # 它是**每一拍都要跑**的那个闸门，所以这里的三个数（要不要跑 / 跑多勤 /
    # 带多少上文）直接决定成本 —— 都放在这儿给用户自己拿主意。
    # ⚠ 它与 `CREW_SCREEN`（剧组产出推到中栏的程度）无关：审读的产出
    #   **永远不上中栏**（那是读稿意见，不是故事），只进台账与《剧本审读.md》。
    # [EN] It's the gate that **runs every beat**, so the three numbers here (whether to run / how often /
    # [EN] how much context) directly determine cost -- they're all here for the user to decide.
    # [EN] ⚠ It's unrelated to `CREW_SCREEN` (how far crew output is pushed to the middle column): the
    # [EN] review's output
    # [EN] **never goes to the middle column** (that's script feedback, not story), only to the ledger and [EN] 《剧本审读.md》.
    "SCRIPT_REVIEW": dict(group="剧组", type="bool", default=True,
                          desc="**剧本审读**：上屏**之前**逐条过一遍（是不是人话·"
                               "像不像这个人·接不接上文·是不是一个主题），"
                               "不通过就改写或**拦下**；同时**记录一切上屏的东西**"
                               "（动作/对话/场景切换/伏笔激活/导演动作…）。"
                               "关掉 = 既不审也不记"),
    "SCRIPT_REVIEW_MODEL": dict(group="剧组", type="bool", default=True,
                                desc="审读要不要**问模型**。关掉 = 只跑零成本的"
                                     "**规则层**（残留的 JSON/占位话/出戏词/标点乱敲/"
                                     "半截话）—— 那几条抓不住语感，"
                                     "但一分钱不花（`SCRIPT_REVIEW` 仍是总闸）"),
    "SCRIPT_REVIEW_EVERY_TICKS": dict(group="剧组", type="int", default=1,
                                      min=1, max=20,
                                      desc="每几拍让审读过一次模型（默认 1 = **每拍都过**）。"
                                           "调大更省，但中间那几拍只有规则层把关"),
    "SCRIPT_REVIEW_HISTORY": dict(group="剧组", type="int", default=30,
                                  min=5, max=80,
                                  desc="审读时带**多少条已上屏的历史**当上文 —— "
                                       "它判「接不接上文 / 是不是一个主题」全靠这个"),
    "SCRIPT_REVIEW_NEWCOMER_TICKS": dict(group="剧组", type="int", default=8,
                                         min=2, max=60,
                                         desc="**进了场、过了几拍还没人跟他说上话**"
                                              "就往导演提示里加一句「谁在场谁接住他」"
                                              "（用户：「人物进场了肯定是有用的…"
                                              "不然不要突然来一个人」）"),
    "SCRIPT_REVIEW_STRICT": dict(group="剧组", type="bool", default=True,
                                 desc="判不过时**真的拦下**（默认）。关掉 = 只记"
                                      "（`剧本审读.md` 里照样列出来），不拦"),
    "SCRIPT_REVIEW_TOKENS": dict(group="剧组", type="int", default=1600,
                                 min=300, max=4000),
    # ══════════════════════════════════════════════════════════════════
    #  认知模式（2026-10-07 第七轮）—— 思维链 / 反思链 / 组合
    # [EN] Cognitive modes (2026-10-07, seventh round) -- chain-of-thought / reflection chain / composition
    # ══════════════════════════════════════════════════════════════════
    # 一句话：让该"先想后答"的职位**先想后答**，让该"产出后审一遍"的地方**真审**。
    # 模式表、思考骨架、反思判据都在 `crew/cognition.py`（一处一实现）。
    # [EN] In one sentence: make roles that should "think before answering" **think before answering**, and
    # [EN] make places that should "review after producing" **really review**.
    # [EN] The mode table, thought skeletons, and reflection criteria are all in `crew/cognition.py` (one
    # [EN] implementation per place).
    # 参考：《AI Agent 从入门到精通》第四章（ReAct / Plan-and-Solve / Reflection）
    # 与第七章（Agent 框架化）。本项目挑的是其中**用得上**的三样：
    #   · 思维链（CoT）—— 一次调用内先填 `推演/构思` 再填答案（**零额外调用**）；
    #   · 反思链（Reflection）—— 产出之后换一双眼睛审，有问题就重做；
    #   · 组合 —— 三人小组那条（构思 + 验算 + 排练）与开卷打磨 Agent。
    # [EN] and Chapter 7 (Agent frameworkization). This project picks the three of them that are **actually
    # [EN] useful**:
    # [EN] · Chain-of-thought (CoT) -- within one call, fill in `推演/构思` first then the answer (**zero extra
    # [EN] calls**);
    # [EN] · Reflection chain -- after producing output, review it with fresh eyes, and redo if there's a
    # [EN] problem;
    # [EN] · Composition -- the three-person team item (conceive + verify + rehearse) and the open-book
    # [EN] polishing Agent.
    # ⚠ 与 `DAY_PLAN_FIX_ROUNDS` / `CREW_REHEARSAL_ROUNDS` 的关系：那两个是
    #   **剧本侧**的反思轮（验算 / 排练），早就有了；这一组管的是**认知层**——
    #   思考骨架（先想）与台词自省（说之前再审一遍）。别把它们并成一个开关。
    # [EN] ⚠ Relationship with `DAY_PLAN_FIX_ROUNDS` / `CREW_REHEARSAL_ROUNDS`: those two are
    # [EN] **script-side** reflection rounds (verify / rehearse), which existed long ago; this group
    # [EN] governs the **cognitive layer** --
    # [EN] thought skeletons (think first) and line self-reflection (review again before speaking). Don't
    # [EN] merge them into one switch.
    "COGNITION": dict(group="认知模式", type="bool", default=True,
                      desc="**设计模式总闸**：给该「先想后答」的职位装上思考骨架"
                           "（演员的台词、剧本、样章、派活……），"
                           "并按规则给不像人话的台词做一次自省重说。"
                           "关掉则**逐字退回**从前的行为（提示词里不出现思考段）"),
    "COT_ACTOR": dict(group="认知模式", type="bool", default=True,
                      desc="**演员的思维链**：他开口之前先在心里过一遍"
                           "（我要什么 / 刚才那句对我做了什么 / 换个人说成不成立 / "
                           "该说多长），答案压进 `推演`。演员是每拍都跑的职位，"
                           "所以它单独一个开关（想省额度先关这条花钱最多的）"),
    "COT_CREW": dict(group="认知模式", type="bool", default=True,
                     desc="**剧组职位的思维链**：剧作者（怎么分拍）、小说作家"
                          "（这一章怎么写）、导演（先看清谁卡在哪儿再派活）、"
                          "场记/资料员/语言审校（先逐条核再下结论）。"
                          "它们一天出工几次，比演员便宜得多"),
    "ACTOR_SELF_REVIEW": dict(group="认知模式", type="bool", default=True,
                              desc="**台词自省**（反思链）：某句台词**明显不像人在"
                                   "场上说的**（书面连接词 / 情绪直说 / 长得像作文）时，"
                                   "让演员在说出口之前再审一遍自己这句，可以改也可以"
                                   "坚持原话。只处理规则挑出来的那一小撮 —— "
                                   "不是每句都问，所以不会把对话变成「总在重说」"),
    "ACTOR_SELF_REVIEW_MAX": dict(group="认知模式", type="int", default=2, min=0, max=6,
                                  desc="**每一拍**最多让几个人自省重说（安全阀："
                                       "重说要额外花一次调用；0 = 等同关掉）"),
    "DIALOGUE_MIN_TURNS": dict(group="Agent 核心", type="int", default=2, min=1, max=20),
    # ★★ 2026-10-14：8 → 4。用户原话「我看现在的推演结果 是大量的对话 …
    #   不应该只有对话」—— 每拍只要有人开口，`Agent.talk()` 就会产
    #   `DIALOGUE_MAX_TURNS` 句台词（原来 8 句），这是"对话刷屏"的最大来源。
    #   4 句仍然是一次完整来回（A→B→A→B），但不再喧宾夺主。
    # ⚠ 老用户的 `.env` 里写着 8 ⇒ **那里不改就还是 8**（见 `.env` 那一行同时改）。
    # [EN] ★★ 2026-10-14: 8 -> 4. User's words: "I see the deduction output is mostly dialogue ...
    # [EN] should not be only dialogue" -- whenever anyone speaks in a beat, `Agent.talk()` produces
    # [EN] `DIALOGUE_MAX_TURNS` lines (8 before), the single biggest source of "dialogue spam".
    # [EN] 4 is still a complete exchange (A->B->A->B) without overwhelming everything else.
    # [EN] ⚠ An existing user's `.env` says 8 => **without changing that it stays 8** (the same line
    # [EN] in `.env` is changed together).
    "DIALOGUE_MAX_TURNS": dict(group="Agent 核心", type="int", default=4, min=1, max=40),
    "GROUP_CHAT_MAX": dict(group="Agent 核心", type="int", default=6, min=2, max=20),
    # ── 前后台双制（设计稿 §五）──
    # 2026-10-06 之前这四项**一个都没人读**："后台人物"只是装配时贴的
    # `role="后台"` 标签 —— 既不行动、也不留记忆、更不会在需要时走到台前。
    # 现在 `sim/backstage.py` 真的在跑（≤AGENT_MAX 全 LLM 前台，后台批次推进）。
    # [EN] -- Front/back-stage dual system (design doc §5) --
    # [EN] Before 2026-10-06, **nobody read** any of these four items: "backstage character" was just a
    # [EN] `role="后台"` tag stuck on at assembly time -- it neither acted, nor kept memory, nor came on
    # [EN] stage when needed.
    # [EN] Now `sim/backstage.py` is actually running (≤AGENT_MAX all-LLM front stage, backstage advanced
    # [EN] in batches).
    "BACKGROUND_MODE": dict(group="前后台", type="enum", default="light",
                            opt=["off", "light", "full"],
                            desc="off=后台完全不管；light=规则补经历记忆 +"
                                 "按事件率批量摘要（默认，最省）；full=后台也逐个决策"),
    "BACKGROUND_TICK_MINUTES": dict(group="前后台", type="int", default=30, min=1, max=1440,
                                    desc="每多少**故事分钟**跑一批后台（跟故事时间走，"
                                         "不是真实时间）"),
    "PROMOTE_ON_STAGE": dict(group="前后台", type="bool", default=True,
                             desc="前台缺位时，把被点名 / 地点对得上的后台人物提到台前"),
    "BACKGROUND_EVENT_RATE": dict(group="前后台", type="float", default=0.15, min=0, max=1,
                                  desc="每批后台掷骰出一次「后堂那边的动静」的概率"
                                       "（light 档唯一花钱的地方）"),
    # ── 群演（临演池，2026-10-06）──
    # 起因：真机跑一轮的日志里「看 627、擦 565、买 0、顾客 0」——
    # 茶楼没有客人，人物只能内循环。群演不是装饰，是**外部输入**。
    # ⚠ 别在这里写具体作品名：`tools/verify_generic_project.py` 盯着这条
    #   （程序必须与具体作品无关）。
    # [EN] -- Extras (temporary actor pool, 2026-10-06) --
    # [EN] Origin: in a real-machine run's logs, "look 627, wipe 565, buy 0, customer 0" --
    # [EN] the teahouse had no guests, so characters could only loop internally. Extras aren't decoration,
    # [EN] they're **external input**.
    # [EN] ⚠ Don't write specific work titles here: `tools/verify_generic_project.py` watches for this
    # [EN] (the program must be independent of any specific work).
    "EXTRAS_ENABLED": dict(group="群演（临演池）", type="bool", default=True,
                           desc="按客流生成背景/功能群演（给故事一个外部输入）"),
    "EXTRAS_MAX_ALIVE": dict(group="群演（临演池）", type="int", default=6, min=0, max=30,
                             desc="同一时刻最多几个群演在场上"),
    # ── 钩子群演（2026-10-06）──
    # 三档里的第三档：「反复出现、像有故事的客人」。它要**跨场记忆** ——
    # 同一个人第二次进门时得记得上回的事（不然就是换了张脸的路人）。
    # 攒够 `EXTRAS_HOOK_PROMOTE_AT` 次，程序**只给建议**（写一张
    # `可转正群演.md`），**不自动造人物卡**：造人物是作者的事。
    # [EN] -- Hook extras (2026-10-06) --
    # [EN] The third of the three tiers: "guests who recur, as if they have a story". They need
    # [EN] **cross-scene memory** --
    # [EN] the same person must remember last time's events when entering the second time (otherwise
    # [EN] they're just a passerby with a different face).
    # [EN] After accumulating `EXTRAS_HOOK_PROMOTE_AT` times, the program **only gives a suggestion**
    # [EN] (writes a
    # [EN] `可转正群演.md`), and **does not auto-create a character card**: creating characters is the author's
    # [EN] job.
    "EXTRAS_HOOKS": dict(group="群演（临演池）", type="bool", default=True,
                         desc="允许少数群演反复出现（带跨场记忆，像有故事的人）"),
    "EXTRAS_HOOK_PROMOTE_AT": dict(group="群演（临演池）", type="int", default=3,
                                   min=2, max=20,
                                   desc="同一个钩子群演出现过几次后，建议转正为正式人物卡"),
    "EXTRAS_DAILY_BUDGET": dict(group="群演（临演池）", type="int", default=8, min=0, max=50,
                                desc="每个故事日最多新生成几个（防刷屏）"),

    # ── 每轮开场（§3.6.1）──
    # [EN] -- Per-round opening (§3.6.1) --
    "SHOW_OPENING": dict(group="每轮开场", type="bool", default=True,
                         desc="开跑前出一屏「场景介绍 + 登场人物介绍」"),
    "OPENING_DETAIL": dict(group="每轮开场", type="enum", default="full",
                           opt=["full", "brief"],
                           desc="full = 引子 + 每人三行；brief = 信息条 + 每人一行"),
    "OPENING_PROSE": dict(group="每轮开场", type="bool", default=True,
                          desc="引子调一次便宜档模型；关掉 = 纯拼装、零成本"),
    "OPENING_ON_RESUME": dict(group="每轮开场", type="enum", default="previously",
                              opt=["previously", "full"],
                              desc="续跑时：previously = 前情一行 + 本轮场景；full = 完整重介"),

    # ── 反空转（2026-10-06）：目标全空时不许"原地打转" ──
    # [EN] -- Anti-idling (2026-10-06): when all goals are empty, no "spinning in place" --
    "ANTI_IDLE_GATE": dict(group="导演引擎", type="bool", default=True,
                           desc="三层目标全空时禁止 wait / 原地动作，强制重新决策"),
    # 导演派活：每 N 拍给在场人物各派一件"此刻该推进的事"。
    # **派"要什么"，从不派"怎么做"** —— 它是目标金字塔最内层（〔此刻〕）的来源。
    # 0 = 关闭派活（那一层就空着，人物只靠自己与进度节点驱动）。
    # ★★★ 2026-10-19：**两个自由度旋钮**（用户把定位从「AI 写作工具」改成「推演工具」，
    #   随后点名「AGENT_FREEDOM 拆分成任务规训和文笔规训」）。
    #
    #   为什么必须拆：两件事松开的**后果不一样**，混成一个旋钮会逼出两种坏结果之一 ——
    #     想要意外 ⇒ 顺手把文笔也松了 ⇒ 得到"更散**且**更难看"；
    #     想保住文笔 ⇒ 连任务也不敢松 ⇒ 回到"照剧本演"。
    #
    #   ── `TASK_FREEDOM`（任务规训）：人物能自己决定干什么 ──
    #     · 低（< 35）：`[今日剧本]` 全文 + **本场分拍表** ⇒ 人物在演一场排好的戏；
    #     · 中（35–65）：剧本压到 160 字 + 派活，**不给分拍表** ⇒ 知道要办什么，
    #       不知道"这一拍该演什么"；
    #     · 高（≥ 65）：只给"今天打算推进的事"，连今天要演什么都不说。
    #     同时影响采样温度（55℃–95℃）—— 温度低时模型反复挑"最得体"的动作，
    #     那正是"每拍都等一等"的来源。
    #     ⚠ **不是越高越好**：高到只给议程时人物容易原地打转（实测过）。
    #
    #   ── `STYLE_FREEDOM`（文笔规训）：字有多讲究 ──
    #     · 低（< 35，很讲究）：去 AI 清单全列 / 心理距离强制 / 思维链五问 / 口癖配额
    #     · 中（35–65，标准）：清单约 3/4 / 距离强制 / 思维链五问 / 口癖配额
    #     · 高（≥ 65，松）：清单约 1/2（至少 2 条）/ **距离不强制** / 思维链只留一问 /
    #       **口癖配额关掉**
    #     ⚠ 松的是**当场约束**，不是**事后验收**：落盘的「去AI审计」与 `DEAI_STRIP`
    #       仍然全量跑。少列几个禁词 ≠ 允许 AI 腔（AI 腔恰恰是最不讲究的写法）。
    #
    #   ⚠⚠ **两个旋钮都碰不到的那一条**：`SPEAKER_ISOLATION_RULES`（不许替别人说话）。
    #     它不是"规训"，是世界的物理法则。`verify_agent_freedom` 的 E 组守它。
    # [EN] ★★★ 2026-10-19: **two freedom knobs** (the product was repositioned from "AI writing tool"
    # [EN] to "simulation tool"; the user then asked to **split AGENT_FREEDOM into task discipline and
    # [EN] prose discipline**).
    # [EN] Why split: the two have **different consequences** when loosened, and one knob forces one of
    # [EN] two bad outcomes -- wanting surprise loosens prose too ("scattered **and** uglier"), or
    # [EN] protecting prose prevents loosening the task ("back to performing a script").
    # [EN] —— `TASK_FREEDOM` (character decides what to do) ——
    # [EN] Low: full script + this scene's beat sheet; middle: script cut to 160 chars + assignments,
    # [EN] no beat sheet; high: only "what you plan to advance today". It also drives temperature
    # [EN] (55-95 C). ⚠ **Higher is not better** -- at the top band characters idle (measured).
    # [EN] —— `STYLE_FREEDOM` (how careful the prose is) ——
    # [EN] Low: full de-AI list / distance enforced / 5-question CoT / tic quota. Middle: list ~3/4.
    # [EN] High: list ~1/2 (min 2) / **distance not enforced** / CoT trimmed to one question /
    # [EN] **tic quota off**. ⚠ It loosens **on-the-spot constraints**, not **post-hoc audit**.
    # [EN] ⚠⚠ Untouchable by both knobs: `SPEAKER_ISOLATION_RULES`. Not "discipline" -- the world's
    # [EN] physical law. Group E of `verify_agent_freedom` guards it.
    "TASK_FREEDOM": dict(group="导演引擎", type="int", default=50, min=0, max=100,
                         desc="任务规训：人物能自己决定干什么。低＝照剧本演（剧本+分拍表都给），"
                              "中＝只给要办的事（不给分拍表），高＝连今天要演什么都不说。"
                              "同时影响采样温度（55℃–95℃）。"
                              "⚠ 想清楚：调高会带来意外，也会带来跑题与空转"),
    "STYLE_FREEDOM": dict(group="导演引擎", type="int", default=50, min=0, max=100,
                          desc="文笔规训：字有多讲究。低＝最讲究（禁词全列/距离强制/思维链五问/"
                               "口癖配额），高＝松（禁词只列一半/距离由人物自己选/"
                               "思维链只留一问/口癖配额关）。"
                               "⚠ 松的是“当场怎么写”，不是“写完不查”—— 审计照旧全量跑"),
    # [EN] Director assigns tasks: every N beats, assign each character present one "thing that should be
    # [EN] advanced right now".
    # [EN] **Assign "what's wanted", never "how to do it"** -- it's the source of the innermost layer of
    # [EN] the goal pyramid (〔此刻〕).
    # [EN] 0 = disable task assignment (that layer stays empty; characters are driven only by themselves
    # [EN] and progress nodes).
    "DISPATCH_EVERY_TICKS": dict(group="导演引擎", type="int", default=8, min=0, max=999,
                                 desc="每 N 拍给在场人物派一次活（0=关闭）。"
                                      "派的是「要达成什么」，不派「怎么做」"),
    # ★★★ 派活**卡死放行闸**（2026-10-19 第十二轮，治 v11 字数暴跌的第二个原因）
    # ------------------------------------------------------------------
    # 「上一件还在办就不换」这道硬机制原来**没有出口**：它判"还在办"靠的是
    # "上一件的关键词还在他最近 6 条自己言行里"，而这句子在另一种卡住形状下会
    # **永真** —— 关键词一直在嘴里、事一直没办成。真跑实录（snow_v11）：
    # 同一个人被连拦两轮，第三轮起再也拿不到新目标，当天正文条目少掉三分之一。
    # ⇒ 新旋钮：连续被拦几轮就判卡死、**强制换新的**。轮数只在该人被拦时 +1，
    #   派到新活立刻归零，所以它不会把"正常在办"误判成卡死。
    # ⚠ 0 = 关闸（回到老行为：可能把人锁死一整晚）。别默认关。
    # ⚠ 记的是**轮**不是拍：DISPATCH_EVERY_TICKS 改了也不用重新配。
    # [EN] ★★★ Dead-stuck release valve for assignments. "Don't switch while the previous one is
    # [EN] still being worked on" had **no exit**: it decides "still working on it" by the previous
    # [EN] task's keywords appearing in his last six own actions/lines, which is **eternally true**
    # [EN] in the other stuck shape -- keywords keep being said while the thing never gets done.
    # [EN] Real run (snow_v11): one person blocked two rounds in a row, then never got new work
    # [EN] again, and that day's entries dropped by a third. ⇒ New knob: after this many
    # [EN] consecutive blocks, judge it dead-stuck and **force a new one**. ⚠ 0 = off.
    "DISPATCH_STUCK_ROUNDS": dict(group="导演引擎", type="int", default=2, min=0, max=99,
                                  desc="同一件派活连续几轮被判「还在办」就判卡死、强制换新的"
                                       "（0=不限，可能永远换不了）"),

    "DIRECTOR_ENABLED": dict(group="导演引擎", type="bool", default=True),
    "DRAMA_LEVEL": dict(group="导演引擎", type="float", default=0.6, min=0, max=1),
    "CONFLICT_FREQUENCY": dict(group="导演引擎", type="float", default=0.4, min=0, max=1),
    "REVEAL_PACING": dict(group="导演引擎", type="float", default=0.5, min=0, max=1),
    "COINCIDENCE_RATE": dict(group="导演引擎", type="float", default=0.2, min=0, max=1),
    "NEW_FACE_RATE": dict(group="导演引擎", type="float", default=0.1, min=0, max=1),
    "TENSION_CURVE": dict(group="导演引擎", type="enum", default="auto",
                          opt=["auto", "flat", "medium", "roller"]),
    "CLIMAX_EVERY_DAYS": dict(group="导演引擎", type="int", default=5, min=1, max=99),
    "BRANCH_PROPOSALS": dict(group="导演引擎", type="int", default=3, min=2, max=4),
    # 岔路口等用户多久（秒）。120 → **300**（2026-10-07 用户：「下面的倒计时太短了
    # 要设置长一些 比如5分钟 让用户有时间思考」）—— 现在面板上还有自定义输入框，
    # 5 分钟是"够他把一句走向想清楚并打完"的量级。
    # ⚠ 用户开始动手（选中候选 / 开始打字）后倒计时会**停表**，不会把他的输入丢掉。
    # `0` = 面板不自动收（一直等他点）。
    # [EN] How long to wait for the user at a fork (seconds). 120 → **300** (user 2026-10-07: "the
    # [EN] countdown below is too short
    # [EN] make it longer, like 5 minutes, so the user has time to think") -- there's now also a custom
    # [EN] input box on the panel,
    # [EN] and 5 minutes is the order of magnitude that's "enough to think through a direction and finish
    # [EN] typing it".
    # [EN] ⚠ Once the user starts acting (selecting a candidate / starting to type), the countdown
    # [EN] **pauses** and won't discard their input.
    # [EN] `0` = the panel doesn't auto-close (wait for the click indefinitely).
    "BRANCH_WAIT_SECONDS": dict(group="导演引擎", type="int", default=300, min=0, max=3600),
    "BRANCH_AUTO_POLICY": dict(group="导演引擎", type="enum", default="weighted",
                               opt=["weighted", "first", "random", "pause"]),
    # ── 导演引擎 ──
    #   ⚠ 这一组的值都在 `director/engine.py` 里被读，改一处要顺手看那边。
    #   `STALL_WINDOW_BEATS` = **停滞救急**（导演挂住等作者确认）的**主判据**；
    #   `DIRECTOR_QUIET_MINUTES` = **常规挑事**的兜底（不等作者，自己往下走）。"
    # [EN] -- Director engine --
    # [EN] ⚠ The values in this group are all read in `director/engine.py`; when changing one, glance over
    # [EN] there too.
    # [EN] `STALL_WINDOW_BEATS` = the **primary** threshold for **stall rescue** (director hangs waiting
    # [EN] for author confirmation);
    # [EN] `DIRECTOR_QUIET_MINUTES` = the fallback for **routine provocation** (doesn't wait for the
    # [EN] author, proceeds on its own)."
    # ★★★ 2026-10-26 新增：**停滞按拍数算，不按故事分钟**。
    #
    #   用户报的三个问题里，「过一会又回到这个循环」最直接的机制就在这里：
    #   旧口径 `180 故事分钟`，而"一拍推多少分钟"由 `跨度 ÷ 拍数` 决定 ——
    #   实测 20 个「跨度 × 篇幅」组合里 **15 个是"6 拍就触发"**
    #   （任一跨度 + 略/带过、或当日+中，一拍都是 30 分钟）。
    #   于是演 6 拍（= 6 次人物决策）就弹一次"导演想介入"，
    #   而弹出来的还是同样两个选项 + 同样那句硬编码 —— 看起来就是死循环。
    #
    #   ⇒ 主判据改成**拍数**：不管一拍推 2 分钟还是 30 分钟，都是"连续 N 拍没事件"才问。
    #     N 取 50：够演完一个像样的段落，又不会让停滞拖成大半天。
    # [EN] ★★★ Added 2026-10-26: **stall is counted in beats, not story minutes**.
    # [EN] The old `180 story minutes` interacted badly with "minutes per beat = span / beats":
    # [EN] measured, **15 of 20** (span x weight) combinations fired after only **6 beats**
    # [EN] (30 minutes per beat). Six character decisions and up comes the same dialog again --
    # [EN] which reads as a loop. => Count beats instead: N=50 is roughly one decent passage.
    "STALL_WINDOW_BEATS": dict(group="导演引擎", type="int", default=50, min=5, max=500),
    #: 停滞的**故事时间保护下限**（分钟，0 = 不看）。★ 默认 **0（关）**。
    #: ★★★ 2026-10-26 语义彻底改了：它不再是主判据，而且**默认不起作用**。
    #:   为什么默认关：只用拍数时，原来担心的"跨天一跳 90 天、两拍就上千分钟"
    #:   **根本不是问题** —— 只有 2 拍拍数条件就不成立，压根到不了这里。
    #:   留着它的唯一理由是给"想按故事时间兜底"的人一个口子；
    #:   而给它非 0 默认值会**帮倒忙**：实测 `一场+详` 一拍只推 2 分钟，
    #:   50 拍才 100 分钟，下限一旦是 180 就**永远不触发**（那一档从此没有停滞介入）。
    #:   ⚠ 老用户的 `.env` 里可能还留着旧值 180（旧语义的"3 小时"），
    #:     那是**语义漂移导致的错误配置**，需要一起搬成 0。
    # [EN] Story-time **floor** for stall (minutes, 0 = off). ★ Default **0 (off)**.
    # [EN] ★★★ Semantics fully changed 2026-10-26: no longer primary, and **off by default**.
    # [EN] Why off: with beats alone, the old worry ("a day jump makes 2 beats 1000+ minutes") never
    # [EN] materializes -- 2 beats simply fail the beat test. It is kept only as an opt-in fallback
    # [EN] for people who want story time involved; a non-zero default actively hurts: measured,
    # [EN] `一场+详` advances 2 min/beat, so 50 beats is 100 minutes, and a floor of 180 would mean
    # [EN] **that combination never fires at all**. ⚠ Old `.env` files may still hold 180 (the old
    # [EN] "3 hours"), which is a wrong value under the new semantics and must be migrated to 0.
    "STALL_WINDOW_MINUTES": dict(group="导演引擎", type="int", default=0, min=0, max=10000),
    # ★★ 2026-10-10 加：**常规挑事的"安静上限"**。
    # [EN] ★★ Added 2026-10-10: the **quiet upper limit for routine provocation**.
    #   起因（用户第一次真跑一天之后报的「五人台词几乎原地循环、
    #   掌柜该给的坦白拍没有落地」）：导演原来只有 `张力 < 0.4` 一个闸，
    #   而张力**一天之内只升不降**（回落只在跨天那一刻）——一次事件抬到 0.41
    #   之后，这个闸当天就再也打不开。实测那一天的拍数是 **391 拍**，
    #   而 `director_event` 只在头 3 拍被问过：**之后 49 分钟零事件**，
    #   人物没有外部刺激，只能自己跟自己重复。
    # [EN] Cause (reported by the user after the first real full-day run: "the five characters' lines loop
    # [EN] in place,
    # [EN] and the shopkeeper's confession beat that should land never lands"): the director originally had
    # [EN] only one gate, `tension < 0.4`,
    # [EN] and tension **only rises within a day, never falls** (it only drops at the day boundary) — once
    # [EN] an event pushes it to 0.41
    # [EN] the gate can never open again for the rest of that day. In the actual measured run that day, the
    # [EN] beat count was **391 beats**,
    # [EN] and `director_event` was only queried in the first 3 beats: **then 49 minutes with zero
    # [EN] events**,
    # [EN] so the characters had no external stimulus and could only repeat themselves.
    #   这个旋钮就是那个兜底：**距上次事件超过这么多故事分钟，就算张力还高也照常挑事**。
    #   它**不是**用来调事件密度的（密度由「戏剧强度 × 冲突频率」那两个旋钮说了算），
    #   只是保证密度不会掉到零。
    # [EN] This knob is that fallback: **once more than this many story minutes have passed since the last
    # [EN] event, provoke an event as usual even if tension is still high**.
    # [EN] It is **not** for tuning event density (density is governed by the two knobs "dramatic intensity
    # [EN] × conflict frequency"),
    # [EN] it only ensures density never drops to zero.
    #   取值：5 故事分钟 ≈ 60 拍（`BEAT_SECONDS=5` 时）。比它小 → 事件勤；
    #   比它大 → 更依赖张力那一路。想退回旧行为就设成一个很大的数。
    # [EN] Value: 5 story minutes ≈ 60 beats (when `BEAT_SECONDS=5`). Smaller than this → more frequent
    # [EN] events;
    # [EN] larger than this → more reliance on the tension path. To revert to the old behavior, set it to a
    # [EN] very large number.
    "DIRECTOR_QUIET_MINUTES": dict(group="导演引擎", type="int", default=5, min=1, max=10000,
                                   desc="距上次事件超过这么多**故事分钟**，"
                                        "即使张力还高也照常挑事（防止一整天都没有外部刺激）"),
    # ── 导演盯戏（2026-10-07）──
    #   用户：「有好几个人连续重复一句话 一件事情的问题(之前是一个人单独
    #          现在我发现了有几个人一起单独做一件事的问题 注意升级导演能力
    #          演员演绎过程中 导演要一直盯着 如果有演员演的台词和动作不对
    #          要及时提出来 导演随时可以要求回档…导演要一直心里有一个大纲
    #          从顶层到细节一直把控剧情进展)」
    # [EN] ── Director watching the drama (2026-10-07) ──
    # [EN] User: "Several people repeat the same line / the same thing consecutively (previously it was one
    # [EN] person alone
    # [EN] now I've found the problem of several people acting out one thing alone; mind upgrading the
    # [EN] director's ability
    # [EN] during the actors' performance, the director must keep watching; if an actor's line or action is
    # [EN] wrong
    # [EN] raise it promptly; the director may request a rollback at any time... the director must always
    # [EN] keep an outline in mind
    # [EN] controlling story progress from top level down to details)"
    #   盯戏**每拍都做、但规则层零成本**（词/句式相似度是用 `store.db` 的
    #   二元组打分算的，不调模型）。只有"要不要真回档"这种才可能花一次调用，
    #   且受 `DIRECTOR_ROLLBACK_MAX` 兜着。
    # [EN] Watching the drama is **done every beat, but the rule layer is zero-cost**
    # [EN] (word/sentence-pattern similarity is scored via `store.db`'s
    # [EN] bigram scores, without calling the model). Only "whether to actually roll back" may cost a call,
    # [EN] and is capped by `DIRECTOR_ROLLBACK_MAX`.
    "DIRECTOR_WATCH": dict(group="导演引擎", type="bool", default=True,
                           desc="导演盯戏：查「多人各自独立重复同一件事/同一句话」"
                                "与整拍空转，命中就让相关人重说，必要时回档"),
    "DIRECTOR_WATCH_EVERY": dict(group="导演引擎", type="int", default=2, min=1, max=20,
                                 desc="每几拍盯一次戏（1 = 每拍；盯戏本身不花钱）"),
    "DIRECTOR_WATCH_MIN_PEOPLE": dict(group="导演引擎", type="int", default=3, min=2, max=8,
                                      desc="几个不同的人各自说了类似的话才算"
                                           "「多人各自独立重复」（2 就会常常误报："
                                           "对话里附和/复述确认本来就像）"),
    "DIRECTOR_ROLLBACK_MAX": dict(group="导演引擎", type="int", default=6, min=0, max=40,
                                  desc="一次最多删掉刚生成的几条戏（0 = 只提醒不回档）。"
                                       "回档会同时把屏幕上那几条撤掉并写进日志"),
    "DAY_REVIEW_REPLAY": dict(group="导演引擎", type="bool", default=False,
                              desc="复盘标了「需要重演」时，允许回档当天最后一幕重排"
                                   "（默认关：一天最多一次，且会在日志里记明）"),
    "DAY_BRIEF": dict(group="Agent 核心", type="bool", default=True,
                      desc="正式剧情之前先给一段「今日剧情简介」（一句话说清"
                           "今天要演什么）—— 它排在「前情提要」之后"),
    "REPETITION_SIMILARITY": dict(group="导演引擎", type="float", default=0.85, min=0, max=1),
    "INTERVENTION_POLICY": dict(group="导演引擎", type="enum", default="pause",
                                opt=["pause", "auto_resolve"]),

    # ★ **正文被思考吃光时，关掉思考自动重试一次**（2026-10-07）。
    #   真模型（deepseek-flash / v4-*）默认思考，而思考连 max_tokens 一起吃 ——
    #   实测一轮真推演里有九处「正文一个字符都没拿到」，直接让当天地图、
    #   每日摘要、导演验算、资料员/场记/道具/宣发**整块不出活**。
    #   开着就是"先按原样发，空了才关思考重发一次"（代价是多一次调用）。
    # [EN] ★ **When the body text is eaten up by thinking, turn off thinking and retry once** (2026-10-07).
    # [EN] Real models (deepseek-flash / v4-*) think by default, and thinking is consumed together with
    # [EN] max_tokens —
    # [EN] in an actual measured real inference round there were nine places where "not a single character
    # [EN] of body text was obtained", directly causing that day's map,
    # [EN] daily summary, director verification, and archivist/script supervisor/props/publicity to
    # [EN] **produce nothing at all**.
    # [EN] Leaving it on means "first send as-is, and only if empty turn off thinking and resend once" (at
    # [EN] the cost of one extra call).
    "LLM_NO_THINK_RETRY": dict(group="模型与额度", type="bool", default=True,
                               desc="正文被思考吃光时，自动关掉思考重试一次"
                                    "（关掉则只记一条警告，不再多发一次请求）"),
    # ★★★ 2026-10-18：**思考模式总开关**。
    #   为什么加它：新版 `deepseek-flash`（滚动别名，2026-10 起）**默认输出思考内容**，
    #   而思考按**输出**计费、并且和正文**抢同一个 `max_tokens`**。实测同一句
    #   "写 300 字小说"：开思考 6.1s / 900 token 全花在思考上 / **正文 0 字**；
    #   关思考 1.9s / 217 token / 286 字正文。用户机器上一次 `agent_decide`
    #   out=3600–4300 token（正常 200–400），约合每拍 0.027 元、一个故事日 29 元
    #   纯思考开销。
    #   以前只有 `NO_THINK_PURPOSES` 那张**写死的用途表**能关，创作类没有开关
    #   ⇒ 想省这笔钱只能改代码。
    #   ⚠ `off` **不绕过**后面那两道闸（`LLM_CAP_THINKING` + 按模型名判定）：
    #     给 o1 / Claude 发 `thinking` 会 400，这条红线不能为省钱的开关让路。
    #   ⚠ `always` 时仍保留「正文为空 → 自动关思考重试一次」那条救命逻辑
    #     （`LLM_NO_THINK_RETRY`）：要"思考"不等于要"一个字都没有"。
    # [EN] ★★★ 2026-10-18: **thinking-mode master switch**.
    # [EN] Why: the new `deepseek-flash` (a rolling alias, since 2026-10) **emits thinking by
    # [EN] default**, and thinking is billed as **output** and competes with the body for the same
    # [EN] `max_tokens`. Measured on the same "write 300 characters of fiction" prompt: thinking on
    # [EN] 6.1s / all 900 tokens spent thinking / **0 characters of body**; thinking off 1.9s / 217
    # [EN] tokens / 286 characters. On the user's machine one `agent_decide` costs out=3600-4300
    # [EN] tokens (normally 200-400), i.e. about CNY 0.027 per beat and CNY 29 per story day of
    # [EN] pure thinking overhead. Previously only the hardcoded `NO_THINK_PURPOSES` table could turn
    # [EN] it off, so creative calls had no switch and saving that money meant editing code.
    # [EN] ⚠ `off` does **not** bypass the two gates below (`LLM_CAP_THINKING` + per-model name
    # [EN] detection): sending `thinking` to o1 / Claude returns 400, and a money-saving switch must
    # [EN] not cross that line.
    # [EN] ⚠ Under `always` the "empty body -> retry once with thinking off" rescue still applies
    # [EN] (`LLM_NO_THINK_RETRY`): wanting thinking is not the same as accepting an empty answer.
    "LLM_THINKING_MODE": dict(group="模型与额度", type="enum", default="auto",
                              opt=["auto", "off", "always"],
                              desc="思考模式：auto=只有结论型用途关（默认）；"
                                   "off=一律关思考（快且省，创作类也关）；"
                                   "always=一律开思考（连判定也不关）"),

    # ══ 网文风格控制（项目级别）══
    # [EN] ══ Web-fiction style control (project level) ══
    "ANGST_LEVEL": dict(group="风格控制", type="float", default=0.3, min=0, max=1,
                        desc="虐心程度：0=纯甜，0.3=小虐怡情，0.5=适度虐心，0.8=大虐，1=虐到极致"),
    "HUMOR_LEVEL": dict(group="风格控制", type="float", default=0.3, min=0, max=1,
                        desc="幽默度：0=纯正剧，0.3=偶尔幽默，0.5=适度搞笑，0.8=轻松喜剧，1=纯喜剧"),
    "SATISFACTION_DENSITY": dict(group="风格控制", type="float", default=0.5, min=0, max=1,
                                 desc="爽点密度：0=无爽点，0.3=偶尔爽，0.5=适中，0.8=高密度爽点"),
    "ROMANCE_RATIO": dict(group="风格控制", type="float", default=0.3, min=0, max=1,
                          desc="感情线占比：0=无感情线，0.3=少量，0.5=适中，0.8=感情线为主"),
    "SUSPENSE_DENSITY": dict(group="风格控制", type="float", default=0.5, min=0, max=1,
                             desc="悬念密度：0=无悬念，0.3=偶尔，0.5=适中，0.8=高悬念"),
    "WORLDBUILDING_PACE": dict(group="风格控制", type="float", default=0.5, min=0, max=1,
                               desc="世界观展开速度：0=缓慢渗透，0.5=适中，0.8=快速展开"),
    "CHARACTER_IQ": dict(group="风格控制", type="float", default=0.5, min=0, max=1,
                         desc="人物智商：0=降智剧情，0.5=正常，0.8=高智商，1=天才级别"),
    "PACING_STYLE": dict(group="风格控制", type="enum", default="medium",
                         opt=["slow", "medium", "fast", "roller"],
                         desc="节奏感：slow=慢热，medium=适中，fast=快节奏，roller=过山车"),
    # ★★★ 2026-10-27：这七个旋钮以前是**死的**（读进 world 之后没有任何消费者），
    #   `STYLE_CONTROL_ACTIVE` 是把它们接上提示词的总开关。
    #   关掉＝回到从前（旋钮只影响界面上那行摘要，推演一模一样）。
    # [EN] ★★★ 2026-10-27: those seven knobs used to be **dead** (read into `world` and then nothing
    # [EN] consumed them). `STYLE_CONTROL_ACTIVE` is the master switch that wires them into the prompt.
    # [EN] Off = back to the old behavior (the knobs only affect that summary line in the UI).
    "STYLE_CONTROL_ACTIVE": dict(group="风格控制", type="bool", default=True,
                                  desc="风格控制真的进提示词：把「虐心/幽默/爽点/感情/悬念/"
                                       "世界观/智商/节奏」翻译成**能数、能查、能照做**的一句话"
                                       "（不是'幽默度 30%'——模型执行不了百分比）。"),
    "COMPLIANCE_ENABLED": dict(group="合规", type="bool", default=True),
    "COMPLIANCE_JURISDICTION": dict(group="合规", type="enum", default="zh_us", opt=["zh_us", "zh", "us"]),
    "COMPLIANCE_LEVEL": dict(group="合规", type="enum", default="standard",
                             opt=["strict", "standard", "relaxed"]),
    "COMPLIANCE_SCAN_ON_INGEST": dict(group="合规", type="bool", default=True),
    "COMPLIANCE_LLM_REVIEW": dict(group="合规", type="enum", default="hybrid",
                                  opt=["hybrid", "always", "never"]),
    "COMPLIANCE_ACTION": dict(group="合规", type="enum", default="rewrite",
                              opt=["rewrite", "block", "pause"]),
    "COMPLIANCE_LOG": dict(group="合规", type="bool", default=True),
    "COMPLIANCE_WHITELIST": dict(group="合规", type="str", default=""),
    "COMPLIANCE_MODEL": dict(group="合规", type="str", default=""),
    "COMPLIANCE_POLICY_DIR": dict(group="合规", type="path", default=""),
    "COMPLIANCE_WATCH_POLICY": dict(group="合规", type="bool", default=True),
    "COMPLIANCE_CHECKPOINTS": dict(group="合规", type="enum", default="all", opt=["all", "minimal"]),
    "TOKEN_BUDGET_PER_DAY": dict(group="Token 经济", type="int", default=200000, min=0),
    "TOKEN_WARN_AT": dict(group="Token 经济", type="float", default=0.8, min=0, max=1),
    "BUDGET_EXHAUST_POLICY": dict(group="Token 经济", type="enum", default="degrade",
                                  opt=["degrade", "pause"]),
    "CONTEXT_CACHE": dict(group="Token 经济", type="bool", default=True),
    "SUMMARIZE_MEMORY_AFTER": dict(group="Token 经济", type="int", default=200, min=10, max=100000),
    #   ★★ 2026-10-10 抬高 6000 → 16000。依据是**真机日志**，不是拍脑袋：
    #   那天 `agent_decide` 的 `in` 有 11 次是 5378、8 次 5407、6 次 5364 ——
    #   都在 6000 预算的 **90% 上下**，也就是**已经在裁了**。
    #   而裁掉的是动态层（记忆 / 当前情况），`llm/context.py` 自己的注释写着
    #   "静默少喂是事故"。所以这个数不是"绰绰有余"，是**卡在日常水位上**。
    #   ⚠ 它本质是**成本预算**（不是模型窗口：deepseek 那边有 64k），
    #     所以不跟着模型上限走；抬到 16000 之后，配合 `LLM_TOKEN_WARN_RATIO`
    #     那条 85% 警戒线，涨回去的时候能提前看见。
    # [EN] ★★ Raised from 6000 to 16000 on 2026-10-10. The basis is **real-machine logs**, not guesswork:
    # [EN] that day `agent_decide`'s `in` was 5378 eleven times, 5407 eight times, 5364 six times —
    # [EN] all around **90%** of the 6000 budget, i.e. **already being truncated**.
    # [EN] And what gets cut is the dynamic layer (memory / current situation); `llm/context.py`'s own
    # [EN] comment says
    # [EN] "silently feeding less is an incident". So this number is not "more than enough", it is **stuck
    # [EN] right at the daily watermark**.
    # [EN] ⚠ It is essentially a **cost budget** (not the model window: deepseek's side has 64k),
    # [EN] so it does not follow the model's upper limit; after raising it to 16000, combined with the
    # [EN] `LLM_TOKEN_WARN_RATIO`
    # [EN] 85% warning line, when it climbs back up you can see it in advance.
    "MAX_CONTEXT_TOKENS": dict(group="Token 经济", type="int", default=16000, min=500, max=200000),
    # ── 输出上限怎么定（2026-10-10，用户点名）────────────────────────────
    # [EN] ── How to set the output limit (2026-10-10, called out by the user) ────────────────────────────
    #   用户原话：「如果是token上限引起的问题，就把所有相关的 token 上限都
    #   大幅增加，尽量让大部分任务不被 token 上限限制（比如按照模型的上限来
    #   限制而不是手动设置的上限）」。
    # [EN] User's exact words: "If it's a problem caused by the token limit, then substantially increase
    # [EN] all related
    # [EN] token limits, so that most tasks aren't limited by the token limit as much as possible (e.g.
    # [EN] limit
    # [EN] according to the model's upper limit rather than a manually set upper limit)".
    #   这句话有出处：2026-10-10 那次真跑，日志里 `day_script` 两次
    #   `out=3998`（上限 4000，正好卡住）、`day_summary` 一次 `out=2000`
    #   （上限 2000）—— 都是**写到一半被砍断**，而复盘里"掌柜该给的坦白拍
    #   没有落地"、"剧本重写 4 轮仍判不通过"就是它的后果。
    # [EN] This claim has a source: in the real run on 2026-10-10, the logs showed `day_script` twice at
    # [EN] `out=3998` (limit 4000, exactly pinned), and `day_summary` once at `out=2000`
    # [EN] (limit 2000) — all **cut off halfway through writing**, and the retrospective notes "the
    # [EN] shopkeeper's confession beat
    # [EN] that should land never lands" and "the script was rewritten 4 rounds and still judged as not
    # [EN] passing" are its consequences.
    #   问题不在"值设小了"，而在**这个值本来就不该由我们猜**：
    #   模型自己知道它能写多少（见 `llm/capabilities.MAX_OUTPUT_TOKENS`）。
    # [EN] The problem is not "the value was set too small", but that **this value should never have been
    # [EN] guessed by us in the first place**:
    # [EN] the model itself knows how much it can write (see `llm/capabilities.MAX_OUTPUT_TOKENS`).
    "LLM_TOKEN_BUDGET_MODE": dict(group="Token 经济", type="enum", default="model",
                                  opt=["model", "manual"],
                                  desc=("输出上限怎么定：model = 按**模型自己的**上限"
                                        "（推荐，自动查表，查不到用下面的兜底）；"
                                        "manual = 按各用途的 *_TOKENS 旋钮（老行为）")),
    # ★★★ 2026-10-14（用户）：「调用模型的时候会报错撞到 max_tokens 8192……
    #   如果是本地配置的 这个很明显已经过时了」→ 要求改成 **819200**。
    #   这一档是**兜底**（只在"认不出模型"时用）；认得出的模型走
    #   `llm/capabilities.MAX_OUTPUT_TOKENS`（hy3 那一行已同步提到 819200）。
    #   ⚠⚠ `max` 必须**一起放**：`coerce()` 按 `spec['max']` **静默夹紧**，
    #      max 留在 200000 的话，default 写 819200 会被夹回 20 万 —— 不报错、很难查。
    # [EN] ★★★ 2026-10-14 (user): "calling a model errors out hitting max_tokens 8192 ... if it's a
    # [EN] local config it's clearly outdated" -> change it to **819200**.
    # [EN] This tier is the **fallback** (only for unrecognized models); recognized models go through
    # [EN] `llm/capabilities.MAX_OUTPUT_TOKENS` (hy3's row was raised in step).
    # [EN] ⚠⚠ `max` must be **loosened together**: `coerce()` clamps to `spec['max']` **silently**, so
    # [EN] leaving `max` at 200000 would clamp a default of 819200 back to 200000 -- no error, hard to find.
    "LLM_MAX_TOKENS_FALLBACK": dict(group="Token 经济", type="int", default=819200,
                                    min=256, max=819200,
                                    desc=("`model` 模式下**认不出这个模型**时用的兜底上限。"
                                          "2026-10-14 从 8192 提到 819200（用户：显然已过时）——"
                                          "旧值太保守：带思考的模型光思考就吃掉 8192。"
                                          "⚠ 若某个服务真被拒（400），有「减半重试」兜着，"
                                          "但每次减半都是一次真实调用")),
    "LLM_TOKEN_SCALE": dict(group="Token 经济", type="float", default=1.0,
                            min=0.1, max=10.0,
                            desc=("把所有 `*_TOKENS` 旋钮**整体**放大这么多倍"
                                  "（只在 `manual` 模式下参与计算）。"
                                  "想在老口径上再放宽，调这一个就行，"
                                  "不用去改十几个旋钮")),
    "LLM_TOKEN_WARN_RATIO": dict(group="Token 经济", type="float", default=0.85,
                                 min=0.1, max=1.0,
                                 desc=("**警戒线**：一次输出用到上限的这个比例，"
                                       "就记一条日志（「快撞上限了」）—— "
                                       "好在被截断之前先看见")),
    # ── 上下文**主动压缩**（2026-10-10，用户点名）────────────────────────
    # [EN] ── Context **active compression** (2026-10-10, called out by the user) ────────────────────────
    #   用户原话：「不是要提醒我自己去调整 而是系统要提示我 并且进行主动压缩」。
    #   也就是说：到线了**系统自己动手**，而不是把问题推回给作者。
    # [EN] User's exact words: "It's not about reminding me to adjust it myself, but the system should
    # [EN] prompt me and perform active compression".
    # [EN] In other words: when the line is reached, **the system acts on its own**, rather than pushing
    # [EN] the problem back to the author.
    #   四个数是一套，照 WorkBuddy 自己的上下文压缩设计搬过来的：
    #     触发 → 保留最近一段原文 → 把更老的折成摘要 → 落到目标水位以下。
    #   「保留最近一段」是最要紧的一条：记忆本来就按「重要性 × 新近度」排，
    #   折的永远是最老的 —— 刚刚发生的事一个字都不能丢。
    # [EN] The four numbers are a set, ported over from WorkBuddy's own context-compression design:
    # [EN] trigger → keep the most recent stretch of original text → fold the older part into a summary →
    # [EN] drop below the target watermark.
    # [EN] "Keep the most recent stretch" is the most important one: memory is already ordered by
    # [EN] "importance × recency",
    # [EN] so what gets folded is always the oldest — not a single word of what just happened may be lost.
    "CTX_COMPACT_AT": dict(group="Token 经济", type="float", default=0.80,
                           min=0.3, max=1.0,
                           desc="**主动压缩的触发线**：上下文用到预算的这个比例就动手压"
                                "（不等到撞墙、也不只是提醒）"),
    "CTX_COMPACT_KEEP": dict(group="Token 经济", type="float", default=0.35,
                             min=0.05, max=0.95,
                             desc="压缩后**保留最近多少比例**的记忆原文"
                                  "（更老的折成一条摘要）"),
    "CTX_COMPACT_TARGET": dict(group="Token 经济", type="float", default=0.50,
                               min=0.1, max=0.95,
                               desc="**目标水位**：压完要落回预算的这个比例以下 ——"
                                    "否则下一拍立刻又触发，来回抖"),
    "CTX_COMPACT_MAX_ROUNDS": dict(group="Token 经济", type="int", default=2,
                                   min=1, max=5,
                                   desc="一次最多压几轮（防跑飞；压不动就停下并说明）"),
    # ── 省钱三件（2026-10-12，用户要求「尽量降低费用」）─────────────────────
    # [EN] ── Three money savers (2026-10-12, user asked to "reduce cost as much as possible") ──
    #   ① **空闲时段折扣**：DeepSeek 是峰谷定价（高峰 = 北京时间周一至周五
    #      9:00-12:00、14:00-18:00；空闲半价）。模拟**可以挑时间跑**，夜里跑直接省一半。
    #   ② **同题复用**：完全相同的输入+模型，短时间内再问一次**直接返回上次的答案**，
    #      不再发请求。只对"同一输入就该给同一结论"的用途开（判定 / 抽取 / 校对），
    #      **说话、写正文、起名一律不缓存** —— 那些要的正是"每次都不一样"。
    #   ③ 存量：模型分级（每个 Agent 指定模型）、输出上限、关思考，都在别处配。
    # [EN] ① **Off-peak discount**: DeepSeek is peak/off-peak priced (peak = Beijing time Mon-Fri
    # [EN] 09:00-12:00 and 14:00-18:00; off-peak is half). A simulation **can pick its time**;
    # [EN] running at night halves the bill.
    # [EN] ② **Same-question reuse**: an identical input+model asked again shortly after **returns the
    # [EN] previous answer** without a new request. Only for uses where "same input must give the same
    # [EN] conclusion" (judging / extraction / proofreading); **speech, prose and naming are never
    # [EN] cached** -- those want "different every time".
    # [EN] ③ Already in place elsewhere: model tiering (per-Agent model), output caps, thinking off.
    "LLM_OFFPEAK_DISCOUNT": dict(group="Token 经济", type="float", default=0.5,
                                 min=0.0, max=1.0,
                                 desc="**空闲时段按这个折扣计价**（默认 0.5 = 半价，"
                                      "照 DeepSeek 官方口径）。只作用于**认得出是峰谷定价**"
                                      "的模型（现在只有 DeepSeek）；别家是平价，不受影响。"
                                      "填 1.0 = 关掉这个折扣（一律按高峰价算）"),
    "LLM_DEDUP_ENABLED": dict(group="Token 经济", type="bool", default=True,
                              desc="**同题复用**开关：完全相同的请求短时间内只真发一次。"
                                   "只对下面那张白名单里的用途生效；"
                                   "关掉它 = 每次请求都真调模型（最贵、但绝对不会有复用）"),
    "LLM_DEDUP_PURPOSES": dict(group="Token 经济", type="str",
                               default=("progress_eval,progress,genre,style,extract,"
                                        "book_scan,compliance,day_verify,summary,"
                                        "day_summary,memory_compact"),
                               desc="**可以复用的用途**（逗号分隔的 purpose）。"
                                    "这些用途的共同点：**同一段输入就该给出同一个结论**，"
                                    "所以复用不会伤质量。"
                                    "⚠ 绝对不要往里加 `dialogue` / `narrate` / `crew_novelist` / "
                                    "`day_story` 这类 —— 那些要的正是「每次不一样」，"
                                    "缓存会让全场人说着同一句话"),
    "LLM_DEDUP_TTL_SECONDS": dict(group="Token 经济", type="int", default=3600,
                                  min=0, max=604800,
                                  desc="复用的**保质期**（秒，默认 1 小时）。"
                                       "超过这个时间就重新问模型 —— "
                                       "知识会变（设定改了、进度变了），老答案不能一直用。"
                                       "0 = 不过期（不建议）"),
    # ★★★ 2026-10-19：**跨进程共享缓存**（`llm/cache.py`）。
    #   与 `LLM_DEDUP_*`（进程内、纳秒级）是两层：先问内存，再问这个磁盘库。
    #   存在的理由：主程序与三个外挂服务是**不同进程**，进程内缓存它们互相看不见；
    #   而这个库是一个 sqlite 文件，谁都能按同一张表读写（外挂用标准库即可，不改代码）。
    #   ⚠ 白名单与 dedup **同一套**（`LLM_DEDUP_PURPOSES`）—— 说话/写正文绝不缓存。
    # [EN] ★★★ 2026-10-19: **cross-process shared cache** (`llm/cache.py`). Two layers with
    # [EN] `LLM_DEDUP_*` (in-process, nanosecond): memory first, then this on-disk library. Why it
    # [EN] exists: the main program and the three external services are **different processes**, so an
    # [EN] in-process cache is invisible to them; this is a sqlite file anyone can read/write with the
    # [EN] same table (extras need only the standard library, no code changes).
    # [EN] ⚠ Same whitelist as dedup (`LLM_DEDUP_PURPOSES`) -- speech/prose are never cached.
    "LLM_CACHE_ENABLED": dict(group="Token 经济", type="bool", default=True,
                              desc="跨进程共享缓存（主程序与三个外挂共用一份问答缓存）；"
                                   "只对「判定/抽取/校对」这类用途生效"),
    "LLM_CACHE_TTL_SECONDS": dict(group="Token 经济", type="int", default=7200,
                                  min=0, max=864000,
                                  desc="共享缓存的保质期（秒）；0 = 永不过期"),
    "LLM_CACHE_PATH": dict(group="Token 经济", type="str", default="",
                           desc="共享缓存文件的位置；留空 = 软件根目录的 llm_cache.db"),
    "LOG_DIR": dict(group="输出与日志", type="str", default="", restart=True,
                    desc="日志文件夹。**留空 = 程序目录下的 logs/**（推荐）；"
                         "填绝对路径则写到那里。日志器在启动时一次性建好，"
                         "所以改这项要重启程序才生效"),
    # ⚠ **如实标注**（2026-10-08 写《使用说明》的「日志」一章时查出来的）：
    #   这一项现在是个**哑旋钮** —— 它会存进 `.env`，但日志器那边从来没读过它，
    #   主日志固定记 DEBUG 及以上（见 `logger.py` 里同一段说明）。
    #   没顺手接上是因为"接上"就是一次行为变更：`.env` 里现写着 `INFO`，
    #   接上之后主日志会立刻少掉约八成行数。要接就当一件事做。
    # [EN] ⚠ **Annotate truthfully** (found on 2026-10-08 while writing the "Logs" chapter of the User
    # [EN] Guide):
    # [EN] this item is currently a **dummy knob** — it gets stored into `.env`, but the logger side has
    # [EN] never read it,
    # [EN] the main log is fixed to record DEBUG and above (see the same note in `logger.py`).
    # [EN] The reason it wasn't wired up in passing is that "wiring it up" is a behavior change: `.env`
    # [EN] currently says `INFO`,
    # [EN] and after wiring it up the main log would immediately lose about 80% of its lines. If it's to be
    # [EN] wired up, treat it as a proper task.
    "LOG_LEVEL": dict(group="输出与日志", type="enum", default="INFO",
                      opt=["DEBUG", "INFO", "WARNING", "ERROR"],
                      desc="⚠ **目前不生效**：这一项会被保存，但日志器还没读它 —— "
                           "主日志**固定记录 DEBUG 及以上**（排障需要的那些内部细节"
                           "都在）。想安静点只能暂时手动清理 `logs/`。"),
    "DEBUG_MODE": dict(group="输出与日志", type="bool", default=False,
                       desc="调试模式：记录 LLM 请求/响应全文、Agent 决策详情、导演判断逻辑、内存检索结果等，便于后续改进"),
    "SAVE_RAW_LOGS": dict(group="输出与日志", type="bool", default=True),
    "LANGUAGE": dict(group="界面", type="enum", default="zh", opt=["zh", "en"],
                     desc="界面语言：zh=中文，en=English（可在「天机 · 全局设置」中切换）"),
    "UI_OPACITY": dict(group="界面", type="int", default=70, min=0, max=100,
                       desc="界面透明度（%）：**数值越大越透** —— 0=完全不透（背景图一点不透出），"
                            "100=最透。面板底色最低保留 30%（再透字就糊在背景花纹上了），"
                            "所以 70%~100% 都停在最透那一档。"
                            "**只作用于开始界面与运行界面（含叙事区），不影响任何对话框** —— "
                            "对话框始终是不透明的纸；"
                            "文字与 1px 描边不透明（半透明文字会伤可读性），"
                            "输入框有 85% 的下限（要看清自己打的字）"),
    "BG_DIM": dict(group="界面", type="int", default=35, min=0, max=70,
                   desc="背景滤镜不透明度（%）：**只对开始界面与运行界面生效，不影响任何对话框**。"
                        "0=完全不压暗（背景最清晰），数值越大纸色滤镜越浓、背景越退到文字后面。"
                        "这一项是「运行时滤镜」，图片本身保持高清——调它不会改到图片文件；"
                        "调完立刻生效，在「天机 · 全局设置 → 界面外观」里拖动即可"),
    # ── 界面字体 / 字号（2026-10-11 用户要求）──
    # [EN] ── UI font / font size (requested by the user 2026-10-11) ──
    "UI_FONT": dict(group="界面", type="enum", default="auto",
                    opt=["auto", "serif", "sans", "kai", "system",
                         "yahei", "simsun", "simhei", "kaiti", "dengxian",
                         "pingfang", "songti", "noto-cjk"],
                    desc="界面字体。可在「天机 · 全局设置 → 界面外观」里切换，改完立刻生效。"
                         "auto=随附宋体（=serif，推荐）；serif=随附宋体（思源宋体，字形合规、"
                         "跨平台一致）；sans=随附黑体（思源黑体）；"
                         "kai=随附楷体（霞鹜文楷：手写感强，但部分汉字用的是日文字形，"
                         "例如「门」的第一笔写成斜长撇）；system=跟随系统默认。"
                         "其余取值是**系统字体**，只在该系统上真实存在时界面才会列出来："
                         "yahei=微软雅黑 / simsun=宋体 / simhei=黑体 / kaiti=楷体 / "
                         "dengxian=等线（Windows）；pingfang=苹方 / songti=宋体-简（macOS）；"
                         "noto-cjk=思源黑体（Linux）。"
                         "⚠ 系统字体**不随程序分发**（许可限制），换到没装的机器上会回落到系统默认"),
    "HIDE_COMMAND_BAR": dict(group="界面", type="bool", default=False,
                             desc="运行窗口底部是一个 **AI 对话输入框**（总体协调引擎的入口）："
                                  "用自然语言给剧组下指令，例如「让导演今天多写点感情戏」「整体节奏放慢一点」"
                                  "「让王二这一拍别那么冲动」。协调引擎会把这句话解析成某一类操作，"
                                  "立刻改写对应 Agent 的实时行为指令，下一拍推演就生效；做不了的事会"
                                  "如实告诉你去「天机」里手动操作。默认 **false = 显示**这个输入框"
                                  "（它已不再是命令框，没有 /help 之类的内置命令）。"
                                  "改完立刻生效，可在「天机 · 全局设置 → 界面外观」里开关"),
    "UI_FONT_SCALE": dict(group="界面", type="int", default=100, min=80, max=150,
                          desc="界面字号缩放（%）：100=标准。整块界面文字与控件高度"
                               "按同一比例缩放（标题、正文、提示、按钮一起变），"
                               "改完立刻生效。80~150 之外会被夹紧；"
                               "150 时对话框可能需要滚动查看"),
    # ★★★ 2026-10-31（用户：「加一个任务栏右下角图标，然后可以在天机 常规里设置
    #   点击右上角关闭以及归去是完全退出还是只是关闭窗口 但是任务栏图标还存在」）。
    #   **一个开关管两处**：点 × 与「归　去」本来就是同一条收尾路（见 `_on_exit`
    #   的注释），分成两个键只会让"我以为两个都关了、其实只关了一个"。
    #   ⚠ 取 `tray` 而托盘**没起来**时，一律按 `exit` 走（见 `resolve_close()`）——
    #     藏了窗口又没有图标把窗口叫回来，等于把程序弄丢。
    # [EN] ★★★ 2026-10-31: **one switch covers both** clicking the × and "Leave" -- they
    #   already share one shutdown path, and two keys would only create "I thought both were
    #   set, but only one was". ⚠ With `tray` selected but the icon **not up**, the behaviour
    #   falls back to `exit` (see `resolve_close()`): hiding a window with no icon to bring it
    #   back is losing the program.
    "CLOSE_ACTION": dict(group="界面", type="enum", default="exit",
                         opt=["exit", "tray"],
                         desc="点窗口右上角的 ×（以及开始菜单的「归　去」）时做什么："
                              "exit=完全退出程序；tray=只关闭窗口，任务栏右下角的图标留着，"
                              "点它可以再把界面叫回来。"
                              "⚠ 选 tray 而图标没能挂上时，一律按 exit 处理（不然窗口一关就"
                              "再也叫不出来）；挂没挂上在「天机 · 常规」里写着，"
                              "也能在那里点「重新挂上托盘图标」。"
                              "这一项**改完立刻生效**，不用重启"),
    "LOG_ROTATE_DAYS": dict(group="输出与日志", type="int", default=0, min=0),
    # ★ 2026-11-01（用户：「这个报告…能不能在天机里有一个Tab…有一个按钮进行智能分析」）：
    #   「花费与优化」那一页的分析**走哪一档模型**。默认 `daily`：
    #   省钱建议本身是"看一眼账、算一笔"的活，用最便宜的档容易给回"少调用就好了"
    #   这种正确的废话；用主力档又等于"为了省钱先花钱"。
    #   ⚠ 它只影响**分析那一次调用**，不影响推演。
    # [EN] Which tier the "Cost & Tuning" page's analysis uses. Default `daily`: the job is
    #   "read the books, do one calculation"; the cheapest tier tends to answer "just call it
    #   less", and the top tier is "spending money to save money". Only affects that one call.
    "COST_ADVISOR_TIER": dict(group="输出与日志", type="enum", default="daily",
                              opt=["cheap", "daily", "front"],
                              desc="「天机 · 花费与优化」里点「智能分析 / 深度优化」时用哪一档模型："
                                   "cheap=便宜档（省钱，但建议可能笼统）、daily=日常档（推荐）、"
                                   "front=主力档（建议最好，单次也最贵）。"
                                   "它**只影响分析那一次调用**，不影响推演用的模型；"
                                   "每次分析大约 1 次调用（输入约 2~4 千 token）"),

    "SNAPSHOT_KEEP": dict(group="输出与日志", type="int", default=30, min=0),

    # ── 叙事输出（剧本式）见 剧本输出格式.md ──
    # [EN] ── Narrative output (script-style) see 剧本输出格式.md ── [Output language] All **output text** must
    # [EN] be written in **Simplified Chinese** — narrative, narration, dialogue, documentation, summaries,
    # [EN] and suggestions all count, **even if the source material is in another language**. Proper nouns
    # [EN] such as person names, place names, and book titles **retain their original spelling**; do not
    # [EN] transliterate or translate them. **Key names in JSON stay as-is** (e.g. "动作", "台词"); only write
    # [EN] the **values** in Chinese.
    "OUTPUT_FORMAT": dict(group="叙事输出", type="enum", default="script",
                          opt=["script", "prose"],
                          desc="叙事输出格式：script=剧本式（时间/场景/出场/旁白/对白/动作），"
                               "prose=旧的自由文本"),
    "SCRIPT_AMBIENT": dict(group="叙事输出", type="bool", default=True,
                           desc="空场/幕首自动补环境句（由真实时段与天气推，不编造剧情）"),
    "SCRIPT_IMAGES": dict(group="叙事输出", type="enum", default="both",
                          opt=["off", "map", "portrait", "both"],
                          desc="插图位置：off=不出图，map=场景图（小地图帧），"
                               "portrait=人物肖像（首次出场），both=两者"),
    "SCRIPT_SCENE_MAX_ENTRIES": dict(group="叙事输出", type="int", default=40,
                                     min=5, max=500,
                                     desc="一幕最多多少条，超过自动分幕（太长的一幕读起来累）"),
    # ── 叙事窗口：分页与时间戳（2026-10-11，用户点名）──
    # [EN] ── Narrative window: paging and timestamps (2026-10-11, user request) ──
    "NARR_TIMESTAMP": dict(group="叙事输出", type="bool", default=True,
                           desc="**叙事窗口里每一条的左上角标一行很小的时间**"
                                "（真实时间 · 剧情时间），方便对照「哪句话是什么时候说的」。"
                                "默认开；嫌挤可以关掉。"
                                "⚠ 只对本轮**实时产生**的条目有效 —— "
                                "从落盘文件读回来的历史没有真实时间，不编（留空）"),
    "NARR_PAGE_ENTRIES": dict(group="叙事输出", type="int", default=200,
                              min=20, max=2000,
                              desc="叙事窗口**一页显示多少条**（条 = 一条叙事/台词/分隔符）。"
                                   "超过一页底部会出现翻页条，可以往回翻到**本次推演的最开头**"
                                   "（以前只渲染最近 200 条，再往前的在界面上看不到）。"
                                   "调大 = 一页装更多、翻页少，但一次画的控件多、切换稍慢"),

    # ── 对话插图（§10.6 插图那一段）──
    # **注意：真正生效的那一档存在项目文件 `.nwsproj` 的 `[项目] 对话图片=`**，
    # 「书斋 · 图片」里选；这里两项只是"全彩文生图"这一档的技术参数
    # （换别的出图服务时改这两个，不用动代码）。
    # [EN] ── Dialogue illustration (§10.6, the illustration paragraph) ──
    # [EN] **Note: the tier that actually takes effect is stored in the project file `.nwsproj` under `[项目] [EN] 对话图片=`**,
    # [EN] selected in "书斋 · 图片"; the two items here are just the technical parameters of the "full-color
    # [EN] text-to-image" tier
    # [EN] (when switching to another image-generation service, change these two, no need to touch the
    # [EN] code).
    "IMAGE_AI_MODEL": dict(group="对话插图", type="str", default="", restart=True,
                           desc="全彩文生图用的模型名（如 gpt-image-1 / dall-e-3）；"
                                "留空 = 不启用这一档（选了会自动降级为 PNG 矢量图）。"
                                "这一项决定 LLM_CAP_IMAGE 的取值"),
    "IMAGE_AI_SIZE": dict(group="对话插图", type="enum", default="1024x1024",
                          opt=["1024x1024", "1024x1536", "1536x1024", "512x512"],
                          desc="文生图尺寸（方图最便宜；横向更适合当插画）", restart=True),
    # ★★★ 2026-10-19 新增：**一张图多少钱**（元）。
    #   为什么必须有：图片调用走的是自己建的 httpx（`image_gen/ai.py`），
    #   原来**一笔账都不记** —— 用量窗口里看得到小说花了多少，看不到插图花了多少。
    #   而图片是按**张**计费的，不按 token，所以不能塞进"输入/输出 token"那两列，
    #   只能把单价乘出来落在 `cost` 上。
    #   ⚠ 默认 0 = **不估钱**（调用次数与张数照记）。填了才计费 —— 因为各家单价差十倍，
    #     猜一个数比不填更糟（用户会照那个数做预算）。
    # [EN] ★★★ Added 2026-10-19: **price per image** (yuan). Why it must exist: image calls use
    # [EN] their own httpx client (`image_gen/ai.py`) and were **not recorded at all** -- the usage
    # [EN] window showed what the novel cost but not what illustrations cost. Images bill **per
    # [EN] image**, not per token, so it cannot go into the input/output token columns; the price
    # [EN] has to be multiplied out into `cost`.
    # [EN] ⚠ Default 0 = **do not estimate money** (call count and image count are still recorded).
    # [EN] Only when filled in does it charge -- prices differ tenfold between providers, and
    # [EN] guessing a number is worse than leaving it blank (users budget against that number).
    "IMAGE_AI_UNIT_PRICE": dict(group="对话插图", type="float", default=0.0, min=0.0,
                                desc="每张图的费用（元）。0 = 不估钱（调用次数照记）"),

    # ── 小地图（2026-10-06；2026-10-08 改语义）──
    # 小地图是**矢量**画的（`ft.canvas`），每次切场景重画一次（很便宜）。
    # ★ 2026-10-08 用户第二次点名这处：小地图上，主角所在的那一处旁边画着
    #   一串**世界层级**的名字（各界、各域），用户说「**这些不是真实的地名**」，
    #   要求「**只根据当前发生的故事所在的地点画图**，而不是根据整本小说设定画图」。
    #   于是取景来源从"整本设定的地点表"换成"当天剧本里真的出现过的那几处"，
    #   这一项**跟着改了语义**：现在管的是**当天这张图要不要美术用 AI 摆位**。
    #   （以前它管的是"全书总图要不要 AI 摆位" —— 那条链路整段拆掉了，
    #     因为那张总图正是用户不想要的东西。）
    # [EN] ── Minimap (2026-10-06; semantics changed 2026-10-08) ──
    # [EN] The minimap is drawn **vectorially** (`ft.canvas`), redrawn once per scene switch (very cheap).
    # [EN] ★ 2026-10-08, the user called out this spot a second time: on the minimap, next to the spot
    # [EN] where the protagonist is, a
    # [EN] string of **world-hierarchy** names is drawn (each realm, each domain); the user said "**these
    # [EN] are not real place names**",
    # [EN] and requested "**draw the map only based on the location of the currently occurring story**, not
    # [EN] based on the entire novel's setting".
    # [EN] So the framing source was changed from "the location table of the entire setting" to "the few
    # [EN] places that actually appeared in that day's script",
    # [EN] This item's **semantics changed along with it**: it now governs **whether AI should be used to
    # [EN] position this day's image for the artist**.
    # [EN] (Previously it governed "whether AI positioning should be used for the whole book's master map"
    # [EN] — that whole pipeline was torn out,
    # [EN] because that master map is exactly what the user didn't want.)
    "MINIMAP_AI": dict(group="小地图", type="bool", default=True,
                       desc="今天这张小地图交给剧组美术按当天剧情摆位"
                            "（更像戏里那个地方）。关掉 = 按剧情顺序沿一条主路"
                            "铺开（不联网、零成本）"),

    # ══════════════════════════════════════════════════════════════════
    #  三级底图（2026-10-08）—— 见 `world/atlas.py` 与 `ingest/atlas.py`
    # [EN] Three-level base map (2026-10-08) — see `world/atlas.py` and `ingest/atlas.py`
    # ══════════════════════════════════════════════════════════════════
    # 用户原话：「设定集里是否可以包含某个房屋的地图，另外 是否可以在开卷的时候
    #   把一些整体地图 局部地图 (房屋附近 房屋内部 以及别的需要的地图) 提前画好
    #   需要的时候基于这些地图让美术加细节」。
    # [EN] User's exact words: "Can the setting collection include the map of a certain house, and also,
    # [EN] when opening the book,
    # [EN] can the overall maps, local maps (near the house, inside the house, and other needed maps) be
    # [EN] drawn in advance,
    # [EN] and when needed, have the artist add details based on these maps".
    # 做的是：**开卷时**按 `地点.yaml` 把三层底图一次定下来，存进
    # `设定集/小世界地图.yaml`；之后每天美术**从底图里取景 + 补细节**，
    # 不再凭空摆位（那样同一处地方今天画左、明天画右）。
    # [EN] What it does: **at book-opening time**, lock in the three-level base map once according to
    # [EN] `地点.yaml`, store it into
    # [EN] `设定集/小世界地图.yaml`; after that, each day the artist **takes a framing from the base map + fills in
    # [EN] details**,
    # [EN] no longer positioning from scratch (which would draw the same place on the left today, on the
    # [EN] right tomorrow).
    "MAP_ATLAS": dict(group="小地图", type="bool", default=True,
                      desc="**开卷时生成三级底图**（整体 = 地点之间的方位与通路；"
                           "局部 = 一处地点周边；室内 = 房屋内部的房间与院落），"
                           "存进设定集、之后各轮复用。开着 = 位置稳定、室内画得出来"
                           "（多花 1+N 次文本调用）；关掉 = 退回「美术每天现摆位」"),
    "MAP_ATLAS_BITMAP": dict(group="小地图", type="bool", default=False,
                             desc="三级底图之外**再出位图氛围底画**"
                                  "（整体一张 + 每处局部一张，走文生图，"
                                  "每张一次出图、耗时且花钱）。矢量底图不依赖它 —— "
                                  "关着也照样有稳定的图，只是少一层画面质感"),
    "MAP_ATLAS_TOKENS": dict(group="小地图", type="int", default=1800,
                             min=400, max=4000,
                             desc="每层底图一次生成允许多少 token（整体一次、"
                                  "每处地点一次）"),

    # ── 地图锚定（2026-10-26）──
    # 用户原话：「小地图和大地图 每次生成的感觉都有一些区别 有办法在整个小说推演过程中
    #   维持相同场景地图的一致性吗」。
    # 病根：① 复用判据里带着"今天的地点集合" ⇒ 一天演几处地方是常态 ⇒ 几乎从不命中；
    #      ② 没有任何东西约束"这处地方昨天在左上、今天还在左上" ⇒ 每次重排。
    # 这一项做的是②：同一 `(层, 主地点)` 下，每个地点名一旦有坐标就**永不改**，
    # 今天只允许**补进没见过的地点**（`image_gen/mapanchor.py`）。
    # 锚定跟着**项目**走（`<项目>/地图/锚定.json`），所以换轮次继续写同一本书也一致。
    # [EN] ── Map anchoring (2026-10-26) ──
    # [EN] User's words: "the minimap and big map feel a bit different every time; can we keep scene
    # [EN] maps consistent across the whole simulation?"
    # [EN] Root causes: ① the reuse fingerprint carried today's set of places, and the story moving
    # [EN] between a few places a day is normal, so it almost never matched; ② nothing recorded "this
    # [EN] place was top-left yesterday", so every layout re-arranged everything.
    # [EN] This setting does ②: under one `(layer, main place)`, a place name keeps its coordinates
    # [EN] **forever**; today may only **add** places never seen before
    # [EN] (`image_gen/mapanchor.py`). Anchors live at the **project** level
    # [EN] (`<project>/地图/锚定.json`), so continuing the same book in another round stays consistent.
    "MAP_ANCHOR": dict(group="小地图", type="bool", default=True,
                       desc="**同一处地方永远画在同一块位置**：位置一旦定下就不再变，"
                            "新的地点只往空处补（存在项目的 `地图/锚定.json` 里，"
                            "换一轮推演也还是它）。关掉 = 每次都按模型给的重新排，"
                            "同一处地方在不同天里可能换位置"),

    "MAP_ART_RESEARCH": dict(group="小地图", type="bool", default=True,
                             desc="**画地图时缺建筑常识就让美术去查**：判出建筑类型后，"
                                  "如果这一类的资料还没落盘，就用一次模型调用问清"
                                  "（开间/进深、院几进、门窗在哪面墙），"
                                  "结果写进 `skills/地图-<类型>/`，以后**直接读盘不再查**。\n"
                                  "- 开: 每类建筑最多查一次（换类型才再查）\n"
                                  "- 关: 只按内置档案画，缺的部分不查（省钱，但布局更粗）\n"
                                  "⚠ 这是唯一一处「推演过程中会联网查资料」的地方；"
                                  "失败不影响出图"),

    # ── 导出（§10.10）：产物落到 <运行文件夹>/导出/ ──
    # [EN] ── Export (§10.10): artifacts go to <run folder>/导出/ ──
    # ★★★ 2026-10-26：**三条「结束时自动导出」全部改默认关**（用户：「自动导出默认关闭」）。
    #   原因是一件实测事故：点「停止」会顺带自动导出（用户不觉得那也是"导了一次"），
    #   而开 `MUMU_FOR_EXPORT` 时导出要逐天重写、能跑十分钟 ⇒ 用户以为卡死 →
    #   又点一次手动导出 ⇒ 同时产出 v1/v2，两份正文完全不同。
    #   ⇒ **"导出"这件事回到"你点了才发生"**。想要收工自动出，到导出对话框
    #     「③ 结束时自动导出」里自己勾（一次勾上、之后一直生效，写进配置文件）。
    #   ⚠ 只改默认值**对老用户无效**：`.env` 里已经写着 `true`，改默认值不会覆盖它。
    #     用户自己那台已经同步改成 false（本次一并做），新装用户默认就是关的。
    # [EN] ★★★ 2026-10-26: **all three "auto-export on finish" switches default to off** (user:
    # [EN] "auto export default off"). Reason: clicking Stop also auto-exported, which the user did
    # [EN] not perceive as an export; with MUMU_FOR_EXPORT on that takes minutes, so the user assumed
    # [EN] a freeze and exported again => two drafts with completely different prose.
    # [EN] ⚠ Changing a default does **not** affect existing users: `.env` already says `true`.
    # [EN] The user's own file was updated as well; fresh installs start off.
    "EXPORT_ON_END_RAW": dict(group="导出", type="bool", default=False,
                              desc="本轮结束自动导出**原始稿**（那一天真实演出的全部正文，"
                                   "从 `每天的生活/第NNN天.json` 铺出来；不剃痕迹、不润色、不重写）。"
                                   "默认**关**（2026-10-26）：导出只在你说的时候发生；"
                                   "要收工自动出就在这里勾上"),
    "EXPORT_ON_END_REFERENCE": dict(group="导出", type="bool", default=False,
                                    desc="本轮结束自动导出**原始稿加细节**（原始稿 + "
                                         "在场名单/本幕依据/机制备注/图片路径；"
                                         "正文一字不改、可复现）。默认**关**，理由同上"),
    "EXPORT_ON_END_NOVEL": dict(group="导出", type="bool", default=False,
                                desc="本轮结束自动导出**最终改写稿**（成品稿：剃掉过程细节；"
                                     "零成本、不调 LLM。⚠ 开 MUMU_FOR_EXPORT 时每天会被重写）。"
                                     "默认**关**，理由同上"),
    "EXPORT_ON_END_GUIDE": dict(group="导出", type="bool", default=False,
                                desc="本轮结束自动导出**写作指导**（大纲建议）。"
                                     "要调 LLM 生成，默认关，想省钱就手动出"),
    "EXPORT_NOVEL_POLISH": dict(group="导出", type="bool", default=False,
                                desc="导出最终改写稿时额外出一份 **LLM 润色稿**"
                                     "（另存为「最终改写稿_vN_润色.md」，不覆盖合订本）。"
                                     "会花 token 并改写措辞，默认关"),
    "EXPORT_FINAL_CHECK": dict(group="导出", type="bool", default=True,
                               desc="**成书前整本复查**（默认开，2026-10-20 加）：\n"
                                    "把每一天的正文再跑几轮「检查→修复」才装订成书，"
                                    "用的是和写小说时**同一套规则**（删元叙述、"
                                    "接住问出去的话、拆道具循环、收拥挤段……）。\n"
                                    "为什么要再查一遍：写小说时每章都查过，但那是**单章视角** —— "
                                    "**跨天才暴露的毛病只有合并后看得见**"
                                    "（同一件东西昨天续、今天续、后天还续；"
                                    "同一句问话昨天问、今天还问）。\n"
                                    "⚠ 只改「最终改写稿 / 参考」这一档；"
                                    "**「原始稿」一个字符都不动** —— 它是「一字未改」的凭据稿。\n"
                                    "⚠ 复查失败一律**按原样导出**，不许因此丢稿。\n"
                                    "跑几轮由 `PROSE_CHECK_ROUNDS` 决定；设 0 = 不复查（快，但跨天毛病留着）。"),

    "DISPLAY_PROFILE": dict(group="显示节奏", type="enum", default="reading",
                            opt=["reading", "fast"]),
    "READING_CPS": dict(group="显示节奏", type="int", default=18, min=1, max=200),
    "DISPLAY_BACKLOG_LIMIT": dict(group="显示节奏", type="int", default=40, min=1, max=1000),
    "DISPLAY_CATCHUP_POLICY": dict(group="显示节奏", type="enum", default="compress",
                                   opt=["compress", "jump", "block"]),
    "DISPLAY_LOCK_SIM": dict(group="显示节奏", type="bool", default=False),
    "REFERENCE_DIR": dict(group="资料与考据", type="path", default=""),
    "REFERENCE_INJECT_MAX": dict(group="资料与考据", type="int", default=500, min=0),
    "SKILLS_DIR": dict(group="资料与考据", type="path", default=".\\skills"),
    "SKILLS_ENABLED": dict(group="资料与考据", type="bool", default=True),
    "MCP_CONFIG": dict(group="资料与考据", type="path", default=".\\mcp_servers.yaml"),
    "MCP_ENABLED": dict(group="资料与考据", type="bool", default=True),
    "MCP_TIMEOUT_SECONDS": dict(group="资料与考据", type="int", default=20, min=1, max=300),
    "RESEARCH_AUTO": dict(group="资料与考据", type="bool", default=True),
    "RESEARCH_MAX_PER_DAY": dict(group="资料与考据", type="int", default=10, min=0),
    "RESEARCH_CACHE_DAYS": dict(group="资料与考据", type="int", default=30, min=0),
    "ONLINE_LOOKUP": dict(group="资料与考据", type="bool", default=False),
    "PROMPTS_DIR": dict(group="AI 质量", type="path", default=".\\prompts"),
    "PROMPT_WATCH": dict(group="AI 质量", type="bool", default=True),
    "REVIEW_PASS": dict(group="AI 质量", type="bool", default=True),
    "REVIEW_THRESHOLD": dict(group="AI 质量", type="float", default=0.7, min=0, max=1),
    "FEWSHOT_FROM_NOVEL": dict(group="AI 质量", type="bool", default=True),
    # ── 去 AI 味（2026-10-07；库在 `style/deai.py`）──
    #   用户：「有时候演员说话会有 AI 味道…做一个去 AI 库，所有演员说话之前、
    #          所有工作人员产出任何内容之前，都做去 AI 味道审计处理」。
    #   两半都不花钱：**事前**把清单写进提示词（别写出来）+ **事后**逐条查
    #   （词表比对，零成本）。所以"每次产出都过一遍"才做得起 ——
    #   要是审计本身要调模型，那就只能抽样，抽样一定漏。
    # [EN] ── De-AI flavor (2026-10-07; library at `style/deai.py`) ──
    # [EN] User: "Sometimes the actors' speech has an AI flavor... make a de-AI library; before all actors
    # [EN] speak,
    # [EN] and before all staff produce any content, run de-AI-flavor audit processing."
    # [EN] Neither half costs money: **beforehand** write the list into the prompt (don't write it out) +
    # [EN] **afterward** check item by item
    # [EN] (wordlist comparison, zero cost). So "run it once for every output" is affordable —
    # [EN] if the audit itself required calling a model, then it could only sample, and sampling always
    # [EN] misses.
    "DEAI": dict(group="AI 质量", type="bool", default=True,
                 desc="启用去 AI 味：演员决策提示词带上禁词与句式清单，"
                      "产出（台词 + 剧组各职位）逐条审计，落盘「去AI审计.md」"),
    "DEAI_PROMPT_ITEMS": dict(group="AI 质量", type="int", default=5, min=0, max=40,
                              desc="提示词里每类列几个禁词（0 = 不列词、只列句式）。"
                                   "列太多会挤占上下文，剩下的交给事后审计"),
    "DEAI_STRIP": dict(group="AI 质量", type="bool", default=True,
                       desc="台词里偶发写进的**套话词**（首先/其次/五味杂陈）直接删掉"
                            "（只删词，不动句式；删了什么会记进日志与审计页）"),
    "FILM_MODE": dict(group="影视镜头", type="bool", default=False),
    "DISPLAY_FILM_CARDS": dict(group="影视镜头", type="bool", default=True),

    # ══════════════════════════════════════════════════════════════
    #  ★★ 创作服务LLM设定 · MuMuAINovel（2026-10-09 新增）
    # [EN] ★★ Creative Service LLM Settings · MuMuAINovel (added 2026-10-09)
    # ══════════════════════════════════════════════════════════════
    #  **这一组服务的不是本项目写的代码**，是接入的开源项目 MuMuAINovel：
    # [EN] **This group of services is not code written by this project**, it's the integrated open-source
    # [EN] project MuMuAINovel:
    #      https://github.com/xiamuceer-j/MuMuAINovel （GPL-3.0）
    #  它是一套独立的「写小说」后端（FastAPI + SQLite），跑在本机 8001 端口，
    #  本项目通过 `novelservices/mumu_bridge.py` 用 HTTP 调它。
    # [EN] It is a standalone "novel-writing" backend (FastAPI + SQLite), running on local port 8001,
    # [EN] and this project calls it over HTTP via `novelservices/mumu_bridge.py`.
    #  这一组旋钮只回答一个问题：**要不要用、用在哪儿**。
    #  服务自己的连接/模型参数（Base URL、Key、模型名、端口）**不在 `.env` 里**，
    #  而是存在它自己的 `novelservices/MuMuAINovel/backend/.env`
    #  —— 天机的同名页面上直接编辑那个文件（单一来源，不抄两份）。
    # [EN] This group of knobs answers only one question: **whether to use it and where to use it**.
    # [EN] The service's own connection/model parameters (Base URL, Key, model name, port) are **not in
    # [EN] `.env`**,
    # [EN] but stored in its own `novelservices/MuMuAINovel/backend/.env`
    # [EN] — edit that file directly on the same-named page in 天机 (single source, don't duplicate).
    #  ⚠ **默认全关**。理由：它是**增强项**，不是主程序的前提。
    #    服务没起、被删、超时，主程序必须照常能写小说（剧组自己那条路一直都在）。
    #    打开之后走的也是"失败自动回退 + 把降级原因写下来"。
    # [EN] ⚠ **Off by default**. Reason: it's an **enhancement**, not a prerequisite of the main program.
    # [EN] If the service isn't up, is deleted, or times out, the main program must still be able to write
    # [EN] novels as usual (the crew's own path is always there).
    # [EN] Even when turned on, it still follows "auto-fallback on failure + write down the degradation
    # [EN] reason".
    "MUMU_ENABLED": dict(group="创作服务 · MuMuAINovel", type="bool", default=False,
                         desc="总开关：允许剧组把写作交给 MuMuAINovel（本机 8001 端口的"
                              "独立写小说服务，上游 https://github.com/xiamuceer-j/MuMuAINovel ）。"
                              "关掉 = 完全用本项目自己的写法；打开后若服务没起/超时/写空，"
                              "会自动退回本项目自己的写法并记明原因"),
    "MUMU_FOR_NOVELIST": dict(group="创作服务 · MuMuAINovel", type="bool", default=True,
                              desc="小说作家（写当天样章、收工整理稿）改走 MuMuAINovel。"
                                   "关掉则只有别的职位用它"),
    # ★ 2026-10-16（用户：「导出的时候如果需要重写小说，应该是根据原始稿和推演过程"
    #   调用 MuMuAINovel 去写新的，而不是用自己内部的 Agent 编写」）。
    #   这一项**只管导出时的『最终改写稿』重写**：打开后，导出最终改写稿会据
    #   『原始稿 + 推演过程』调 MuMuAINovel 重写每一天；服务没起/超时/写空
    #   则那一天退回内部整理稿（绝不丢戏）。默认**关**（导出沿用内部整理稿）。
    # [EN] ★ 2026-10-16 (user: "when exporting, if the novel needs rewriting, it should call
    # [EN] MuMuAINovel based on the novel's raw text and the derivation process to write a new one,
    # [EN] instead of using this program's own internal Agent").
    # [EN] This item **only governs the 'novel version' rewrite at export time**: when on, exporting
    # [EN] the novel version calls MuMuAINovel with 'raw novel text + derivation process' to rewrite
    # [EN] each day; if the service isn't up/timed out/empty, that day falls back to the internal
    # [EN] edited draft (never loses the day's content). Default **off** (export keeps the internal
    # [EN] edited draft).
    "MUMU_FOR_EXPORT": dict(group="创作服务 · MuMuAINovel", type="bool", default=False,
                            desc="导出『最终改写稿』时改走 MuMuAINovel：据『原始稿 + 推演过程』"
                                 "重写每一天。关掉则导出沿用内部整理稿；打开后若服务没起/"
                                 "超时/写空，会自动退回内部整理稿并记明原因（不丢戏）"),
    "MUMU_AUTOSTART": dict(group="创作服务 · MuMuAINovel", type="bool", default=True,
                           restart=True,
                           desc="程序启动时自动拉起写小说服务（后台起，起不来只提示、"
                                "不拦主程序）。关掉则要自己跑 "
                                "`novelservices/MuMuAINovel/backend/novelservice.py start`"),
    # ★ 2026-10-10 用户要求：「必须主窗口退出的时候后台服务也跟着退出」。
    #   默认**开**，于是"关掉程序"这件事终于是"关掉程序"，
    #   而不是"关掉窗口、后台还留一个服务占着 8001 端口"。
    #   ⚠ 两处都会读它，必须同名同默认值：
    #     · `start.exe`（`launchers/flow.go: followService`）—— 主窗口退出后由它收尸；
    #     · 本程序自己（正常退出时补一刀，见 `_stop_service_on_exit`）。
    #   两处都是幂等的（`novelservice.py stop` 对"没在跑"返回 0），所以重复调用无害。
    #   ⚠ 关掉它 = 服务常驻后台：下次启动**不用冷启动**（首次要下模型，可能几分钟），
    #     代价是关掉程序之后它还在跑。
    # [EN] ★ 2026-10-10 user requested: "The background service must also exit when the main window exits".
    # [EN] Default **on**, so "closing the program" is finally "closing the program",
    # [EN] rather than "closing the window, while a service still lingers in the background occupying port
    # [EN] 8001".
    # [EN] ⚠ Read in both places, must share the same name and default value:
    # [EN] · `start.exe` (`launchers/flow.go: followService`) — it cleans up after the main window exits;
    # [EN] · This program itself (adds a final blow on normal exit, see `_stop_service_on_exit`).
    # [EN] Both are idempotent (`novelservice.py stop` returns 0 for "not running"), so repeated calls are
    # [EN] harmless.
    # [EN] ⚠ Turning it off = service stays resident in the background: next startup **doesn't need a cold
    # [EN] start** (the first one downloads models, may take minutes),
    # [EN] the cost is that it's still running after the program is closed.
    "MUMU_FOLLOW_APP": dict(group="创作服务 · MuMuAINovel", type="bool",
                            default=True,
                            desc="关闭程序时**一并停掉**写小说服务。默认开（关掉程序就"
                                 "真的什么都不留）。关掉 = 服务常驻后台，下次启动更快，"
                                 "但要自己记得停它"),
    "MUMU_TIMEOUT_SECONDS": dict(group="创作服务 · MuMuAINovel", type="int",
                                 default=900, min=60, max=3600,
                                 desc="等 MuMuAINovel 写完一章的上限（秒）。"
                                      "**别调太小**：实测同一章 17 秒到 207 秒都出现过，"
                                      "推理模型想多久控不住；超时会造成这一章白等"),
    "MUMU_EXPORT_TRIES": dict(group="创作服务 · MuMuAINovel", type="int",
                              default=2, min=1, max=4,
                              desc="导出重写**最多让服务写几遍**（含第一遍）。"
                                   "每遍拿回来先过**本项目自己的**检查清单，"
                                   "有可数的毛病就把「哪一类、几处」退回让它重写，"
                                   "并且**两版按验收层比，取更好的**——不是无条件采用新稿。"
                                   "1 = 只要一遍（旧行为）；"
                                   "调大会明显变慢，而且超过 3 遍收益很小"),
    "MUMU_SAMPLE_WORDS": dict(group="创作服务 · MuMuAINovel", type="int",
                              default=0, min=0, max=8000,
                              desc="**开演前那份「样章」**目标多少字。0 = 跟随剧组自己的口径（CREW_STORY_MIN~MAX，即 180~600 字的**质感样本**）。"
                                   "⚠ 别拿 MUMU_TARGET_WORDS（2500）当它用：那是**导出重写整章**的字数。"
                                   "实测两条路差 4~14 倍，而它们的产物都交给同一个编剧去拆拍 ——"
                                   "2500 字的样章会让编剧拆出更细的拍，把演员框死（用户 2026-10-21 问的正是这个）。"),
    "MUMU_TARGET_WORDS": dict(group="创作服务 · MuMuAINovel", type="int",
                              default=2500, min=300, max=12000,
                              desc="交给 MuMuAINovel 那一章的目标字数"),
    "MUMU_ENABLE_ANALYSIS": dict(group="创作服务 · MuMuAINovel", type="bool",
                                 default=False,
                                 desc="让 MuMuAINovel 给每章做一次分析（角色状态/伏笔/"
                                      "剧情总结）。开着它下一章能「记得住」，代价是明显更慢"),
    # ⚠ 默认值留空（不是写死 `deepseek-chat`）：`coerce()` 对 `str` 类型的空值
    #   **不会**回落到 SPEC 默认值（只有 bool/int/float/enum 会）——
    #   给一个非空默认值，界面上却显示空白，是个会骗人的组合。
    #   所以约定跟别的 str 项一致：**留空 = 代码里的自动档**。
    # [EN] ⚠ Leave the default value empty (don't hardcode `deepseek-chat`): `coerce()` for empty values of
    # [EN] `str` type
    # [EN] **will not** fall back to the SPEC default (only bool/int/float/enum do) —
    # [EN] giving a non-empty default but showing blank in the UI is a deceptive combination.
    # [EN] So the convention matches other `str` items: **empty = auto mode in code**.
    "MUMU_ANALYSIS_MODEL": dict(group="创作服务 · MuMuAINovel", type="str",
                                default="",
                                desc="MuMuAINovel 的章节分析用哪个模型。"
                                     "**留空 = deepseek-chat**（推荐）：它不思考，"
                                     "而推理模型会把输出预算烧在思考上"
                                     "（实测最坏一次想 22876 字符、正文 0 字）"),
    "MUMU_SKILL_KEY": dict(group="创作服务 · MuMuAINovel", type="str", default="",
                           desc="用 MuMuAINovel 的哪个技能（可空）。候选见 "
                                "novelservices/MuMuAINovel/backend/app/skills/。"
                                "留空 = 用它的默认写作流程。常用：story-long-write"),
    # ★ 2026-10-17（用户：「让 MuMuAINovel / PlotPilot / PenShot 使用我在 AI模型配置里
    #   已经配置好的模型，选了之后写入到对应的 .env 文件」）：
    #   这一项只是**下拉框的回显**（保存时按它把登记表里那条模型的
    #   key/地址/模型名写进服务自己的 .env）。空 = 不覆盖。
    # [EN] ★ 2026-10-17 (user: "let the three services use models already configured in
    # [EN] AI Model Config; the pick is written into the corresponding .env"):
    # [EN] this key only **echoes the dropdown** (on save it writes the picked registry entry's
    # [EN] key/url/model into the service's own .env). Empty = don't override.
    "MUMU_LLM_PICK": dict(group="创作服务 · MuMuAINovel", type="str", default="",
                          desc="「来自 AI模型配置」下拉的当前选择（登记表的 key）。"
                               "空 = 不覆盖，服务用它自己 .env 里的配置"),

    # ══════════════════════════════════════════════════════════════
    #  ★★ 创作服务 · PlotPilot（墨枢，编剧/叙事引擎，2026-10-16 接入）
    # [EN] ★★ Creative Service · PlotPilot (narrative engine, integrated 2026-10-16)
    # ══════════════════════════════════════════════════════════════
    #  这一组是**另一个本机服务**，不是本项目写的：
    # [EN] This group is **another local service**, not written by this project:
    #      https://github.com/shenminglinyi/PlotPilot （Apache-2.0 + Commons Clause）
    #  它是「叙事引擎内核」：维护人物一致性/因果链/伏笔/故事线结构，
    #  擅长在长篇跨度里把"这一章该发生什么、结构怎么立"想清楚 —— 给**剧作者/编剧**用。
    #  本项目通过 `novelservices/plotpilot_bridge.py` 用 HTTP 调它（默认本机 8005）。
    # [EN] It is a "narrative-engine kernel": maintains character consistency / causal chains /
    # [EN] foreshadowing / storyline structure — for the **screenwriter**. Called via
    # [EN] `novelservices/plotpilot_bridge.py` (local 8005 by default).
    #  ⚠ **默认全关**。它是增强项，不是前提；服务没起/超时/空章，编剧退回本项目自己那条路。
    # [EN] ⚠ **Off by default**. Enhancement, not prerequisite; on failure the screenwriter falls back.
    "PLOTPILOT_ENABLED": dict(group="创作服务 · PlotPilot", type="bool", default=False,
                              desc="总开关：允许剧作者把『本章方案』交给 PlotPilot（本机 8005 端口的"
                                   "独立叙事引擎，上游 https://github.com/shenminglinyi/PlotPilot ）。"
                                   "关掉 = 完全用本项目自己的编剧逻辑；打开后若服务没起/超时/空章，"
                                   "会自动退回本项目自己的编剧逻辑并记明原因"),
    "PLOTPILOT_FOR_SCREENWRITER": dict(group="创作服务 · PlotPilot", type="bool", default=True,
                                       desc="剧作者（screenwriter）改走 PlotPilot 产出本章方案。"
                                            "关掉则只有别处用到它"),
    "PLOTPILOT_HOST": dict(group="创作服务 · PlotPilot", type="str", default="127.0.0.1",
                           desc="PlotPilot 服务监听地址（默认 127.0.0.1，本机）"),
    "PLOTPILOT_PORT": dict(group="创作服务 · PlotPilot", type="int", default=8005,
                           min=1, max=65535,
                           desc="PlotPilot 服务端口（默认 8005）"),
    "PLOTPILOT_MODEL": dict(group="创作服务 · PlotPilot", type="str", default="",
                            desc="覆盖 PlotPilot 用的 LLM 档案/模型（可空）。"
                                 "留空 = 用 PlotPilot 自己的默认；"
                                 "具体填法取决于 PlotPilot 的 profile_id"),
    # ★ 2026-10-17：「来自 AI模型配置」下拉的当前选择（登记表 key）。
    #   保存时按它把那条模型的 key/地址/模型名映射成 PlotPilot .env 认的键
    #   （ANTHROPIC_*/ARK_*/OPENAI_*，按地址自动认；不兼容会警告、不写）。
    # [EN] ★ 2026-10-17: current pick of the "from AI Model Config" dropdown (registry key).
    # [EN] On save it maps the picked entry to PlotPilot's .env keys
    # [EN] (ANTHROPIC_*/ARK_*/OPENAI_*, recognized by address; incompatible => warn, don't write).
    "PLOTPILOT_LLM_PICK": dict(group="创作服务 · PlotPilot", type="str", default="",
                               desc="「来自 AI模型配置」下拉的当前选择（登记表的 key）。"
                                    "空 = 不覆盖，服务用它自己 .env 里的配置"),
    # ★ 2026-10-17：`restart=True` —— 与 `MUMU_AUTOSTART` 同一条道理：
    #   `_maybe_autostart_service` 只在**程序启动时**读它一次，改完当下不生效。
    #   标了才会在保存时提醒「要重启」，不标就是骗人。
    # [EN] ★ 2026-10-17: `restart=True` -- same rationale as `MUMU_AUTOSTART`:
    # [EN] `_maybe_autostart_service` reads it **once at program startup**, so a mid-session
    # [EN] change doesn't take effect. Marking it makes save-time remind "restart needed";
    # [EN] not marking it would be a lie.
    "PLOTPILOT_AUTOSTART": dict(group="创作服务 · PlotPilot", type="bool", default=False,
                                restart=True,
                                desc="程序启动时自动拉起 PlotPilot（它需要 LLM 凭证，"
                                     "默认**关**避免无谓冷启动；要常驻再打开）"),
    "PLOTPILOT_FOLLOW_APP": dict(group="创作服务 · PlotPilot", type="bool", default=True,
                                 desc="关闭程序时一并停掉 PlotPilot（默认开）"),
    "PLOTPILOT_TIMEOUT_SECONDS": dict(group="创作服务 · PlotPilot", type="int",
                                      default=900, min=60, max=3600,
                                      desc="等 PlotPilot 产出一章方案的上限（秒）"),

    # ══════════════════════════════════════════════════════════════
    #  ★★ 创作服务 · PenShot（AI 导演/分镜引擎，2026-10-17 接入）
    # [EN] ★★ Creative Service · PenShot (AI film-director / storyboard engine, integrated 2026-10-17)
    # ══════════════════════════════════════════════════════════════
    #  这一组是**另一个本机服务**，不是本项目写的：
    # [EN] This group is **another local service**, not written by this project:
    #      https://github.com/neopen/story-shot-agent （MIT）
    #  它是「AI 导演 / 分镜引擎」：把一段剧本拆成镜头分解（分镜）、
    #  情绪评分、配乐建议、可视化时间线 —— 给**导演（director）**用。
    #  ★ 与前任 CutAI 的唯一硬差别：CutAI 只接 Groq，PenShot 走
    #    **OpenAI 兼容协议**（detect_ai_provider_by_url 的兜底），
    #    天机「AI模型配置」里登记的模型（Moonshot / DeepSeek / 硅基流动 /
    #    本地 Ollama… 任何 OpenAI 兼容端点）都能直接用。
    # [EN] It is an "AI film-director / storyboard engine": breaks a script into shot
    # [EN] breakdown, emotion scoring, music suggestions, visual timeline — for the
    # [EN] **director**. ★ Only hard difference vs its predecessor CutAI: CutAI was
    # [EN] Groq-only, PenShot speaks **OpenAI-compatible** protocol, so any model
    # [EN] registered in Tianji's AI Model Config (Moonshot / DeepSeek / SiliconFlow /
    # [EN] local Ollama... any OpenAI-compatible endpoint) works directly.
    #  本项目通过 `novelservices/penshot_bridge.py` 用 HTTP 调它（默认本机 8000）。
    # [EN] Called via `novelservices/penshot_bridge.py` (local 8000 by default).
    #  ⚠ **默认全关**。它是增强项，不是前提；服务没起/超时，导演退回本项目自己那条路。
    # [EN] ⚠ **Off by default**. Enhancement, not prerequisite; on failure the director falls back.
    "PENSHOT_ENABLED": dict(group="创作服务 · PenShot", type="bool", default=False,
                           desc="总开关：允许导演把『分镜方案』交给 PenShot（本机 8000 端口的"
                                "独立导演/分镜引擎，上游 https://github.com/neopen/story-shot-agent ）。"
                                "关掉 = 完全用本项目自己的导演逻辑；打开后若服务没起/超时，"
                                "会自动退回本项目自己的导演逻辑并记明原因"),
    "PENSHOT_FOR_DIRECTOR": dict(group="创作服务 · PenShot", type="bool", default=True,
                                desc="导演（director）改走 PenShot 产出分镜方案。"
                                     "关掉则只有别处用到它"),
    "PENSHOT_HOST": dict(group="创作服务 · PenShot", type="str", default="127.0.0.1",
                        desc="PenShot 服务监听地址（默认 127.0.0.1，本机）"),
    "PENSHOT_PORT": dict(group="创作服务 · PenShot", type="int", default=8000,
                        min=1, max=65535,
                        desc="PenShot 服务端口（默认 8000）"),
    "PENSHOT_MODEL": dict(group="创作服务 · PenShot", type="str", default="",
                         desc="覆盖 PenShot 用的模型（可空）。留空 = 用 PenShot 自己 .env 里的"
                              "配置（PENSHOT_LLM__DEFAULT__*）"),
    # ★ 2026-10-17：「来自 AI模型配置」下拉的当前选择（登记表 key）。
    #   保存时按它把那条模型的 key/地址/模型名映射成 PenShot .env 认的键
    #   （PENSHOT_LLM__DEFAULT__* + PENSHOT_EMBED__DEFAULT__*）。
    #   ⚠ PenShot 的厂商识别按 base_url 兜底走 OpenAI 兼容协议，
    #      任何 OpenAI 兼容服务都能写；本地 Ollama 会被识别成原生协议、不写 key。
    # [EN] ★ 2026-10-17: current pick of the "from AI Model Config" dropdown (registry key).
    # [EN] On save it maps the picked entry to PenShot's .env keys
    # [EN] (PENSHOT_LLM__DEFAULT__* + PENSHOT_EMBED__DEFAULT__*).
    # [EN] ⚠ PenShot's provider detection falls back to the OpenAI-compatible protocol,
    # [EN] so any OpenAI-compatible endpoint is writable; local Ollama is detected as
    # [EN] native protocol and gets no key.
    "PENSHOT_LLM_PICK": dict(group="创作服务 · PenShot", type="str", default="",
                            desc="「来自 AI模型配置」下拉的当前选择（登记表的 key）。"
                                 "空 = 不覆盖，服务用它自己 .env 里的配置"),
    # ★ 2026-10-17：`restart=True` —— 与 `MUMU_AUTOSTART` 同一条道理：
    #   `_maybe_autostart_service` 只在**程序启动时**读它一次，改完当下不生效。
    # [EN] ★ 2026-10-17: `restart=True` -- same rationale as `MUMU_AUTOSTART`:
    # [EN] `_maybe_autostart_service` reads it **once at program startup**.
    "PENSHOT_AUTOSTART": dict(group="创作服务 · PenShot", type="bool", default=False,
                             restart=True,
                             desc="程序启动时自动拉起 PenShot（它需要 LLM 凭证，"
                                  "默认**关**避免无谓冷启动；要常驻再打开）"),
    "PENSHOT_FOLLOW_APP": dict(group="创作服务 · PenShot", type="bool", default=True,
                               desc="关闭程序时一并停掉 PenShot（默认开）"),
    "PENSHOT_TIMEOUT_SECONDS": dict(group="创作服务 · PenShot", type="int",
                                    default=900, min=60, max=3600,
                                    desc="等 PenShot 产出分镜的上限（秒）"),
}

# ══════════════════════════════════════════════════════════════════════════════
#  配置文件说明补全（2026-10-25）
#
#  为什么要有这一段：`Config.save()` / `write_example()` 生成的配置文件，注释只
#  取 `desc` 字段。原先 354 个键里有 123 个（35%）根本没写 `desc` ⇒ 用户打开
#  `.env` 想改一项，那一项头上**一个字说明都没有**（而 `.env.example` 里手写过，
#  两份说明因此差了几百行 —— 同一个配置两套说法，最容易改错）。
#
#  做法：**不碰上面 354 条 dict 定义**，只在这里补一张表、循环填进去。
#  内容不是新编的：优先取 `.env.example` 里已有的手工注释；它没有的 22 项
#  （时间系统 / 记忆权重 / 各剧组 Agent 的 token 上限）取自各自在下方 dict 里的
#  上方注释。想回滚：删掉这一段即可，其余代码不依赖它。
#
#  ⚠ `desc` 允许含换行（`Config.save()` 会逐行加 `#`）；它只用于生成配置文件，
#    不参与界面显示，所以写长不影响布局。
#
# [EN] Why this block exists: the config files written by `Config.save()` / `write_example()` take
# [EN] their comments from the `desc` field only. 123 of the 354 keys (35%) had no `desc` at all, so
# [EN] a user opening `.env` to change something found **not one word of explanation** above that
# [EN] key -- while `.env.example` had hand-written notes for it, leaving the same setting documented
# [EN] two different ways (a reliable recipe for editing the wrong knob).
# [EN] Approach: **do not touch the 354 dict definitions above**; add one table and a loop here.
# [EN] The text is not newly invented: it is taken from the existing hand-written comments in
# [EN] `.env.example`, and for the 22 keys that had none (time system / memory weights / each crew
# [EN] agent's token cap) from the comments above each dict below. To roll back: delete this block;
# [EN] nothing else depends on it.
# [EN] ⚠ `desc` may contain newlines (per-line `#` is added); it is used only for generating config
# [EN] files and never rendered in the UI, so length does not affect layout.
# ══════════════════════════════════════════════════════════════════════════════
DESC_SUPPLEMENT: dict[str, str] = {
    "LLM_BASE_URL": (
        "API 地址（OpenAI 兼容协议）\n"
        "- DeepSeek: https://api.deepseek.com/v1\n"
        "- OpenAI: https://api.openai.com/v1\n"
        "- 智谱: https://open.bigmodel.cn/api/paas/v4\n"
        "- Moonshot: https://api.moonshot.cn/v1\n"
        "- 本地 Ollama: http://localhost:11434/v1"
    ),
    "LLM_API_KEY": (
        "API Key（必填，演示模式除外）\n"
        "- 从对应平台获取：https://platform.deepseek.com\n"
        "- 演示模式（MOCK_LLM=true）时可留空"
    ),
    "LLM_TIMEOUT_SECONDS": (
        "单次请求超时（秒）\n"
        "- 太小会大量重试反而费 token\n"
        "- 建议：60（默认）~ 120（复杂生成）"
    ),
    "LLM_MAX_RETRIES": (
        "失败重试次数\n"
        "- 0 = 失败即暂停\n"
        "- 建议：3（默认）"
    ),
    "LLM_MAX_CONCURRENCY": (
        "全局并发上限（防 429 限流）\n"
        "- 多前台 Agent 决策排队 + 指数退避\n"
        "- 建议：4（默认），可根据 API 限额调整"
    ),
    "MODEL_FRONT": (
        "三档模型（**快速配置**，2026-10-12 起从\"唯一方式\"降级为\"Agent 没点名时的兜底\"）\n"
        "- MODEL_FRONT: 华彩档（关键事件/重要对话/反思/故事文档/运行小结）~15% 调用量\n"
        "- MODEL_DAILY: 日常档（常规循环/日志整理）~55% 调用量\n"
        "- MODEL_CHEAP: 摘要档（压缩/打分/后台/进度评估）~30% 调用量\n"
        "- 值 = 模型登记表里的 **key**（迁移后通常就是原来的模型名）\n"
        "- 空 = 跳过这一档，往下走\"默认模型 → 第一条\"\n"
        "★ 想按\"某一位 Agent 用什么\"来配，**不要在这里配** —— 去\n"
        "「天问 · 剧组 Agents」点那一位，它有一个「模型」选项，旁边写着推荐的模型。\n"
        "（用户 2026-10-12：「后续LLM不再针对特定功能进行模型配置」）\n"
        "★ 「哪个功能推荐用什么模型」有一张现成的表：界面上的\n"
        "「天问 · 模型与LLM · 推荐：哪个功能用什么模型」，代码在 `llm/recommend.py`。"
    ),
    "MODEL_DAILY": (
"日常档模型，约 55% 调用量（常规循环 / 「每天的生活」整理）。值 = 模型登记表里的 key；空 = 跳过这一档，往下走「默认模型 → 第一条」。"
    ),
    "MODEL_CHEAP": (
"摘要档模型，约 30% 调用量（压缩 / 打分 / 后台 / 进度评估）。值 = 模型登记表里的 key；空 = 跳过这一档，往下走「默认模型 → 第一条」。"
    ),
    "LLM_DEFAULT_MODEL": (
        "默认模型（谁都没指定时用哪一个）\n"
        "- 值 = 模型登记表里的 **key**（不是发给服务端的模型名，虽然迁移后两者通常相同）\n"
        "- 空 = 用登记表里的第一条\n"
        "⚠ 改这一项要重启程序才生效。"
    ),
    "MODEL_PRICE_OVERRIDES": (
        "手填价格覆盖（元/百万 token）\n"
        "- 格式（新）：模型名=命中价/未命中价/输出价\n"
        "- 格式（老）：模型名=未命中价/输出价（命中价自动按 1/10 推）\n"
        "- 示例：hy3=0.25/1/4,my-proxy=1/3/12,deepseek-chat=2/8\n"
        "- 空 = 使用内置价目表\n"
        "⚠️ 价格说明：LLM 服务价格会随市场调整，内置价目表仅为参考预估。\n"
        "实际费用请以 LLM 服务商（如 DeepSeek、OpenAI 等）官方公布的最新价格为准。\n"
        "如需精确计费，请使用此配置项手动填入当前官方价格；\n"
        "也可以在「天问 · 模型与LLM」里逐条模型填（推荐，那样每条模型带自己的价）。"
    ),
    "EMBEDDING_MODEL_LOCAL": (
        "本地向量模型（EMBEDDING_PROVIDER=local 时生效）\n"
        "- 首次运行会自动下载模型（约 100MB）\n"
        "- 推荐：BAAI/bge-small-zh-v1.5（中文效果好）"
    ),
    "EMBEDDING_MODEL_API": (
        "API 向量模型（EMBEDDING_PROVIDER=api 时生效）\n"
        "- OpenAI: text-embedding-3-small\n"
        "- 智谱: embedding-3"
    ),
    "OPTIMIZE_ON_IMPORT": (
        "导入未达黄金档时自动进 AI 优化向导\n"
        "- true: 自动进入优化向导（推荐）\n"
        "- false: 跳过优化，直接使用原始设定"
    ),
    "STORY_GENRE": (
        "故事类型\n"
        "- auto: LLM 自动判定 + 人工确认（推荐）\n"
        "- 手填：「主题材+副题材|结构|频道」\n"
        "- 示例：悬疑+灵异|单元剧|男频"
    ),
    "NOVEL_STYLE": (
        "风格来源\n"
        "- auto: 从正文提取风格卡（推荐，需有正文）\n"
        "- plain: 使用默认白描风格\n"
        "- custom: 使用 NOVEL_STYLE_CUSTOM 自定义描述"
    ),
    "NOVEL_STYLE_CUSTOM": (
        "自定义风格描述（NOVEL_STYLE=custom 时生效）\n"
        "- 示例：长句绵密、冷笔白描、对话占比低"
    ),
    "CRAFT_LIBRARY": (
        "工艺库\n"
        "- builtin: 使用内置工艺库（推荐）\n"
        "- none: 关闭工艺库（纯沙盒）\n"
        "- 自定义目录：指向你的工艺库目录"
    ),
    "CRAFT_CASES_ENABLED": (
        "案例库是否参与提示\n"
        "- true: 案例库内容会注入 LLM 提示（推荐）\n"
        "- false: 关闭案例库（省 token）"
    ),
    "SCENE_NAME": (
        "场景名称\n"
        "- auto: 提议 2~3 个候选由你选定（推荐）\n"
        "- 手填：直接指定场景名，跳过提议"
    ),
    "SCENE_START_HINT": (
        "开局情境（自然语言，可选）\n"
        "- 示例：雨夜，茶肆打烊前\n"
        "- 空 = 由 LLM 根据设定生成"
    ),
    "CALENDAR_DISPLAY": (
        "历法显示\n"
        "- auto: 自动推断（推荐）\n"
        "- regnal: 年号纪年（如「康熙三年」）\n"
        "- ganzhi: 干支纪年（如「甲子日」）\n"
        "- modern: 现代日期（如「2026-10-04」）\n"
        "- daycount: 第 N 天（如「第 42 天」）"
    ),
    "STORY_START_POINT": (
        "故事起始点\n"
        "- auto: 有正文接续最新进度，无正文大纲起点（推荐）\n"
        "- begin: 从头开始\n"
        "- 节点 ID: 从指定节点开始（如 N03）"
    ),
    "ENDING_SCENE": (
        "到达终点后是否由导演安排收束场景\n"
        "- true: 先安排收束场景再停（推荐，结尾更完整）\n"
        "- false: 直接停"
    ),
    "PLOT_ADHERENCE": (
        "主线吸附力（0~1）\n"
        "- 越高导演越积极把剧情拉回进度节点\n"
        "- 0.7: 适度引导（推荐）\n"
        "- 0.3: 放养，看人物自己长戏"
    ),
    "STORY_DOC_MODEL": (
        "故事文档/运行小结的生成档位\n"
        "- MODEL_FRONT: 华彩档（质量优先，推荐）\n"
        "- MODEL_DAILY: 日常档（省钱）"
    ),
    "SUMMARY_MODEL": (
"运行报告用哪一档模型（MODEL_FRONT / MODEL_DAILY / MODEL_CHEAP）。报告含账单与 OOC 分析，默认走华彩档。"
    ),
    "GAME_START_TIME": (
        "故事开始时间\n"
        "- 空 = 随开局方案\n"
        "- 格式：YYYY-MM-DD HH:MM\n"
        "- 示例：2026-10-04 08:00"
    ),
    "TIME_RATIO": (
        "时间倍率\n"
        "- 1 现实秒 = 多少故事秒\n"
        "- 60: 现实 1 秒 = 故事 1 分钟（推荐）\n"
        "- 3600: 现实 1 秒 = 故事 1 小时（快节奏）"
    ),
    "TICK_REAL_MS": (
        "心跳间隔（毫秒）\n"
        "- 主循环 tick 间隔\n"
        "- 1000: 1 秒（推荐）\n"
        "- 500: 0.5 秒（更流畅但更耗资源）"
    ),
    "BEAT_SECONDS": (
"**演出节拍**：一拍等多久**真实秒**（`TIME_RATIO` 倍率再除）。攒够一拍才做一次决策，所以它也是**花钱的节拍器**（一拍 = 1~2 次 LLM 调用）。默认 60 = 一拍一分钟：中档一天 15~25 拍，一天演 15~25 分钟，看着是一章的量。⚠ 它**不决定故事时间**：一拍推多少故事分钟由「这一站的跨度 ÷ 这一站的拍数」算（见「日界按拍预算」）；调小只会让同样的内容冲得更快，**不会多演故事** —— 想一天更厚改进度表里那一站的「篇幅」。"
    ),
    "DAY_ENDS_ON_BEAT_BUDGET": (
"开（默认）：**这一站的拍演完就收一天的稿** —— 小说的「一天」是这一天写出来的那些事，不再要求填满 24 小时。关掉逐字回到旧行为（一拍恒定故事秒、跨 24 点换天），旧行为实测一天演 133 幕 / 21.3 万字。"
    ),
    "BEAT_MAX_MINUTES": (
"一拍最多推多少**故事分钟**。一拍 = 场景内的一个节拍（一个人做一件事、说一两句），一次换场或一段等待最多半小时。更长的时间流逝不是拍该干的活，而是「过场」：站末把剩余时间一次跳掉并推一句旁白。调大它会让一场戏里冒出「过了两小时」，读者会觉得戏被剪了。"
    ),
    "QUIET_MINUTES": (
"全场都没人动时，隔多少**故事分钟**才写一次「片刻无话」。不设这个门槛，安静的时刻会把版面刷满（满屏「没动，也没出声」）。"
    ),
    "AMBIENT_MINUTES": (
"每隔这么多**故事分钟**补一条环境白描，**与有没有人在动无关**。0 = 关掉这条通路（环境只在空场时出现）。⚠ 单位是故事分钟；默认 TIME_RATIO=1 时，填 1 就是「每真实 1 分钟一条」。"
    ),
    "AMBIENT_REPEAT_EVERY": (
"同一句环境白描隔多少条之后才可以再现（0 = 永不复现）。⚠ 别靠调小它来「加环境」：候选池只有 1~5 条，池子就那么大，调小只会让同一句回来得更快。真正的「空气」由演员的细节承担。"
    ),
    "AUTO_RUN_DAYS": (
        "跑满 N 故事日自动暂停\n"
        "- 0 = 不限（story 模式以终点为准）\n"
        "- 示例：10（跑 10 天后暂停）"
    ),
    "PAUSE_AT_NIGHT": (
        "全员就寝自动暂停省 token\n"
        "- true: 夜间自动暂停\n"
        "- false: 不暂停（推荐，可手动 pause）"
    ),
    "AGENT_MAX": (
        "前台人数上限\n"
        "- 超出的 Agent 降格为后台 light\n"
        "- 建议：12（默认）"
    ),
    "MEMORY_RETRIEVE_K": (
        "记忆检索 top-K\n"
        "- 每次决策检索多少条记忆\n"
        "- 建议：8（默认）"
    ),
    "WEIGHT_RECENCY": (
        "记忆检索权重（三权重加权）\n"
        "- WEIGHT_RECENCY: 时间衰减权重（越新越重要）\n"
        "- WEIGHT_IMPORTANCE: 重要性权重\n"
        "- WEIGHT_RELEVANCE: 相关性权重（关键词命中）\n"
        "- 建议：1.0（默认）"
    ),
    "WEIGHT_IMPORTANCE": (
"记忆检索打分里「重要性」这一项的权重（0~5）。调大 = 更优先想起重要的事；调小 = 更看近期。"
    ),
    "WEIGHT_RELEVANCE": (
"记忆检索打分里「相关度」这一项的权重（0~5）。调大 = 更优先想起跟当前场景有关的事。"
    ),
    "RECENCY_DECAY": (
        "时间衰减系数\n"
        "- 0.995: 24 小时衰减约 50%（推荐）\n"
        "- 0.99: 更快衰减\n"
        "- 0.999: 更慢衰减"
    ),
    "IMPORTANCE_SCORING": (
        "重要性打分策略\n"
        "- hybrid: 规则粗筛 + LLM 精评（推荐，省约 70%）\n"
        "- llm: 全部用 LLM 打分（贵但准）\n"
        "- heuristic: 纯规则（免费但粗糙）"
    ),
    "REFLECTION_THRESHOLD": (
        "反思触发阈值\n"
        "- 累计重要性过此值触发反思\n"
        "- 建议：100（默认）"
    ),
    "REFLECTION_MAX_PER_DAY": (
        "每日每 Agent 反思上限\n"
        "- 建议：2（默认）"
    ),
    "PLANNING_ENABLED": (
        "分层计划\n"
        "- true: 启用日计划 → 时段块 → 当前动作（推荐）\n"
        "- false: 关闭计划"
    ),
    "PLAN_BLOCK_MINUTES": (
        "计划时段块长度（分钟）\n"
        "- 建议：30（默认）"
    ),
    "CREW_STORY_TOKENS": (
"小说作家（novelist）单次输出的 token 上限。写样章用，调大才写得更长。"
    ),
    "CREW_SCRIPT_TOKENS": (
"剧作者（screenwriter）单次输出的 token 上限。剧本比样章长，所以默认给得最大。"
    ),
    "CREW_CONTINUITY_TOKENS": (
"场记（continuity）单次输出的 token 上限。"
    ),
    "CREW_PROPS_TOKENS": (
"道具（props）单次输出的 token 上限。"
    ),
    "CREW_ART_TOKENS": (
"美术（art）单次输出的 token 上限。"
    ),
    "CREW_RESEARCH_TOKENS": (
"资料员（researcher）单次输出的 token 上限。"
    ),
    "CREW_PUBLICITY_TOKENS": (
"宣发（publicity）单次输出的 token 上限。"
    ),
    "CREW_SETTINGS_TOKENS": (
"编剧室会审的输出上限（token）—— 安全网，不是目标值。"
    ),
    "CREW_EXTRA_TOKENS": (
"群众演员（extra）单次输出的 token 上限。"
    ),
    "CREW_REVIEW_TOKENS": (
"四位各自的输出上限（安全网，不是目标值）"
    ),
    "CREW_STYLIST_TOKENS": (
"造型（stylist）单次输出的 token 上限。"
    ),
    "CREW_SOUND_TOKENS": (
"声音（sound）单次输出的 token 上限。"
    ),
    "CREW_POLISH_TOKENS": (
"语言审校（polisher）单次输出的 token 上限。"
    ),
    "CREW_REHEARSAL_TOKENS": (
"排练（rehearsal）单次输出的 token 上限。"
    ),
    "CREW_STORYBOARD_TOKENS": (
"分镜师（storyboard）单次输出的 token 上限。"
    ),
    "SCRIPT_REVIEW_TOKENS": (
"剧本审读（script_doctor）单次输出的 token 上限。"
    ),
    "DIALOGUE_MIN_TURNS": (
        "对话轮数\n"
        "- DIALOGUE_MIN_TURNS: 最少轮数\n"
        "- DIALOGUE_MAX_TURNS: 最多轮数（封顶）"
    ),
    "DIALOGUE_MAX_TURNS": (
"一场对话最多几轮（1~40）。防止两个人来回客套把戏拖住。"
    ),
    "GROUP_CHAT_MAX": (
        "群聊同场发言人数上限\n"
        "- 3 人及以上同场进入群聊模式\n"
        "- 建议：6（默认）"
    ),
    "DIRECTOR_ENABLED": (
        "导演引擎总开关\n"
        "- true: 启用导演（推荐）\n"
        "- false: 关闭导演（纯 Agent 自由发挥）"
    ),
    "DRAMA_LEVEL": (
        "戏剧总闸（0~1）\n"
        "- 0.6: 适度戏剧性（推荐）\n"
        "- 0.3: 平淡日常\n"
        "- 0.9: 高强度冲突"
    ),
    "CONFLICT_FREQUENCY": (
        "冲突频率（0~1）\n"
        "- 0.4: 中等频率（推荐）"
    ),
    "REVEAL_PACING": (
        "伏笔/秘密揭示节奏（0~1）\n"
        "- 0.5: 适中（推荐）"
    ),
    "COINCIDENCE_RATE": (
        "巧合概率（0~1）\n"
        "- 0.2: 少量巧合（推荐）"
    ),
    "NEW_FACE_RATE": (
        "新人物登场倾向（0~1）\n"
        "- 0.1: 偶尔引入新人物（推荐）"
    ),
    "TENSION_CURVE": (
        "张力曲线\n"
        "- auto: 取类型档案节奏模板（推荐）\n"
        "- flat: 平淡\n"
        "- medium: 中等波动\n"
        "- roller: 过山车式"
    ),
    "CLIMAX_EVERY_DAYS": (
        "每 N 日至少一次小高潮\n"
        "- 建议：5（默认）"
    ),
    "BRANCH_PROPOSALS": (
        "分支提案数量\n"
        "- 建议：3（默认，2~4 个）"
    ),
    "BRANCH_WAIT_SECONDS": (
        "分支等待秒数（岔路口那个面板等你多久）\n"
        "- 300 = 等 5 分钟后自动选（默认；面板上还有自定义输入框，\n"
        "留够把一句走向想清楚并打完的时间）\n"
        "- 0 = 基本不等：面板照开，但主循环立刻按 `BRANCH_AUTO_POLICY` 挑\n"
        "（想\"必须我选\"就把它设 0 **并且**让策略 = pause）\n"
        "★ 你一动它（选中候选 / 开始在框里打字）倒计时就**停表**，不会把你的输入丢掉。"
    ),
    "BRANCH_AUTO_POLICY": (
        "分支超时策略\n"
        "- weighted: 按权重随机选（推荐）\n"
        "- first: 选第一个\n"
        "- random: 完全随机\n"
        "- pause: 暂停等人工"
    ),
    "STALL_WINDOW_BEATS": (
        "停滞检测窗口（拍）\n"
        "- 50: 连续 50 拍没有事件才视为停滞（推荐）\n"
        "- 调小=导演更爱插手；调大=更放手让人物自己演"
    ),
    "STALL_WINDOW_MINUTES": (
        "停滞检测的时间下限（分钟，0=不看，推荐 0）\n"
        "- 0: 只看拍数（推荐）—— 一拍推几分钟都不影响，各档频率一致\n"
        "- 非 0: 额外要求故事时间也过这么久（会压低慢节奏档的触发）"
    ),
    "REPETITION_SIMILARITY": (
        "对话循环检测相似度阈值\n"
        "- 0.85: 相似度超过此值视为循环（推荐）"
    ),
    "INTERVENTION_POLICY": (
        "干预策略\n"
        "- pause: 暂停等人工（推荐）\n"
        "- auto_resolve: 自动解决"
    ),
    "COMPLIANCE_ENABLED": (
        "合规总开关\n"
        "- true: 启用合规检测（推荐）\n"
        "- false: 关闭（强烈不建议）"
    ),
    "COMPLIANCE_JURISDICTION": (
        "法域基准\n"
        "- zh_us: 双法并集，冲突以中国法为准（推荐）\n"
        "- zh: 仅中国法\n"
        "- us: 仅美国法"
    ),
    "COMPLIANCE_LEVEL": (
        "审查力度\n"
        "- strict: C1 从严\n"
        "- standard: 标准档（推荐）\n"
        "- relaxed: 只拦法律禁止生成类（C0）"
    ),
    "COMPLIANCE_SCAN_ON_INGEST": (
        "摄取时对项目文档做合规静态扫描\n"
        "- true: 扫描（推荐）\n"
        "- false: 跳过"
    ),
    "COMPLIANCE_LLM_REVIEW": (
        "LLM 复核策略\n"
        "- hybrid: 仅规则命中或敏感场景才复核（推荐，省钱）\n"
        "- always: 每条都复核（贵）\n"
        "- never: 仅规则层（快但可能漏）"
    ),
    "COMPLIANCE_ACTION": (
        "命中后的默认动作\n"
        "- rewrite: 降尺度重写（推荐）\n"
        "- block: 回滚该事件\n"
        "- pause: 暂停等管理员"
    ),
    "COMPLIANCE_LOG": (
        "合规命中日志\n"
        "- true: 记录（推荐）\n"
        "- false: 不记录"
    ),
    "COMPLIANCE_WHITELIST": (
        "项目级白名单（题材标签，逗号分隔）\n"
        "- 示例：冤案,战争场面\n"
        "- 需在向导/设置里显式确认才生效"
    ),
    "COMPLIANCE_MODEL": (
        "合规 Agent 专用模型\n"
        "- 空 = 用 MODEL_CHEAP（默认，够用）\n"
        "- 可指定更强的模型（合规判定错不起的场景）"
    ),
    "COMPLIANCE_POLICY_DIR": (
        "自定义策略库目录\n"
        "- 空 = 内置默认库\n"
        "- 自定义目录会与内置库叠加，同名文件用户优先"
    ),
    "COMPLIANCE_WATCH_POLICY": (
        "策略文件变动热重载\n"
        "- true: 运行中改词表立即生效（推荐）\n"
        "- false: 需重启"
    ),
    "COMPLIANCE_CHECKPOINTS": (
        "检查点覆盖\n"
        "- all: CP1~CP8 全查（推荐）\n"
        "- minimal: 只查摄取+前台事件+导出物（最省）"
    ),
    "TOKEN_BUDGET_PER_DAY": (
        "每日 token 预算（硬闸）\n"
        "- 200000: 约 20 万 token/天（推荐）\n"
        "- 0 = 不限\n"
        "- 首跑建议 AUTO_RUN_DAYS=1 试一晚再放大"
    ),
    "TOKEN_WARN_AT": (
        "预算告警阈值（0~1）\n"
        "- 0.8: 达到 80% 时告警（推荐）"
    ),
    "BUDGET_EXHAUST_POLICY": (
        "预算耗尽策略\n"
        "- degrade: 降级阶梯（推荐，关反思→后台 off→换便宜档→叙事模板化→暂停）\n"
        "- pause: 直接暂停"
    ),
    "CONTEXT_CACHE": (
        "上下文缓存\n"
        "- true: 启用前缀缓存（推荐，省 token）\n"
        "- false: 关闭"
    ),
    "SUMMARIZE_MEMORY_AFTER": (
        "记忆压缩阈值\n"
        "- 超过此条数后压缩记忆\n"
        "- 建议：200（默认）"
    ),
    "MAX_CONTEXT_TOKENS": (
        "最大上下文 token 数\n"
        "- 超过此值从动态层尾部往前裁，固定前缀永不裁\n"
        "- 建议：6000（默认）"
    ),
    "SAVE_RAW_LOGS": (
        "保存调用账本（logs/llm_calls.jsonl）\n"
        "- true: 记（推荐，一行一次调用：模型/用途/进出 token/耗时）\n"
        "- false: 不记\n"
        "⚠ 只影响**账本**，不影响主日志与对话日志；账本**不在自动清理范围内**，会一直涨。"
    ),
    "LOG_ROTATE_DAYS": (
        "日志的**额外**清理天数（只管 `nws*.log`）\n"
        "⚠ 先说清一件事：**不管这里填什么**，程序每次启动都会清掉\n"
        "**30 天前**的 `nws*.log`（主日志与对话日志都在内）。\n"
        "要留档的，先复制走。\n"
        "这一项是在那次之上**再**清一遍：\n"
        "- 0 = 不做额外清理（默认；启动时那一次 30 天照旧生效）\n"
        "- 30: 额外再清一次 30 天前的\n"
        "⚠ `llm_calls.jsonl`（调用账本）**不在任何清理范围内**，会一直涨，嫌大就手动删。"
    ),
    "SNAPSHOT_KEEP": (
        "快照保留份数\n"
        "- 30: 保留 30 份（推荐）\n"
        "- 0 = 不限"
    ),
    "DISPLAY_PROFILE": (
        "显示档位\n"
        "- reading: 看戏阅读档（打字机+18 字/秒，推荐）\n"
        "- fast: 监控速览档（关打字机，整段上屏）"
    ),
    "READING_CPS": (
        "阅读呈现速度（字/秒）\n"
        "- 18: 中文舒适区（推荐）\n"
        "- 15: 慢读\n"
        "- 25: 快读"
    ),
    "DISPLAY_BACKLOG_LIMIT": (
        "显示队列积压上限（条）\n"
        "- 超过按积压策略处理"
    ),
    "DISPLAY_CATCHUP_POLICY": (
        "积压策略\n"
        "- compress: P3 折叠成一行式（推荐）\n"
        "- jump: 跳到最新\n"
        "- block: 等同锁定模式"
    ),
    "DISPLAY_LOCK_SIM": (
        "锁定模式\n"
        "- true: 模拟等显示，一字不漏（速度受阅读速度限制）\n"
        "- false: 自由队列（推荐）"
    ),
    "REFERENCE_DIR": (
        "用户资料库根目录\n"
        "- 空 = 不使用资料库\n"
        "- 示例：E:\\参考资料\n"
        "- 目录结构：参考书/ 参考小说/ 规则/"
    ),
    "REFERENCE_INJECT_MAX": (
        "单次注入资料片段上限（字）\n"
        "- 500: 适中（推荐）"
    ),
    "SKILLS_DIR": (
        "技能目录\n"
        "- .\\skills: 默认技能目录"
    ),
    "SKILLS_ENABLED": (
        "技能启用\n"
        "- true: 启用技能（推荐）\n"
        "- false: 关闭技能"
    ),
    "MCP_CONFIG": (
        "MCP 服务配置文件\n"
        "- .\\mcp_servers.yaml: 默认配置（随程序发行，含 3 个本地服务 + 4 个联网模板）\n"
        "- 配置格式与写法见 mcp/README.md"
    ),
    "MCP_ENABLED": (
        "MCP 总开关\n"
        "- true: 允许调用 MCP 服务（推荐；本地服务不出机）\n"
        "- false: 完全不拉起任何 MCP 进程\n"
        "注意：这是**总闸**。每个服务还有自己的 enabled 开关，\n"
        "联网模板（fetch / duckduckgo-search / wikipedia / time）默认都是 false，\n"
        "要用得自己改成 true —— 它们会把查询词发出本机。"
    ),
    "MCP_TIMEOUT_SECONDS": (
        "单次 MCP 调用的超时（秒）\n"
        "- 20: 适中（推荐）\n"
        "- 服务启动慢或查询重时可调大；上限 300"
    ),
    "RESEARCH_AUTO": (
        "知识缺口自动考据\n"
        "- true: 自动考据（推荐）\n"
        "- false: 仅手动 research 命令"
    ),
    "RESEARCH_MAX_PER_DAY": (
        "每日自动考据上限\n"
        "- 10: 适中（推荐）"
    ),
    "RESEARCH_CACHE_DAYS": (
        "考据结果缓存期（天）\n"
        "- 30: 30 天（推荐）"
    ),
    "ONLINE_LOOKUP": (
        "联网搜索兜底\n"
        "- true: 启用（出机警告，向导二次确认）\n"
        "- false: 关闭（推荐，隐私优先）"
    ),
    "PROMPTS_DIR": (
        "提示词模板目录\n"
        "- .\\prompts: 默认目录\n"
        "- 用户目录同名文件优先覆盖"
    ),
    "PROMPT_WATCH": (
        "提示词热重载\n"
        "- true: 改词不动码（推荐）\n"
        "- false: 需重启"
    ),
    "REVIEW_PASS": (
        "叙事整理审稿 pass\n"
        "- true: 低于阈值重写一次（推荐）\n"
        "- false: 关闭审稿（省 token）"
    ),
    "REVIEW_THRESHOLD": (
        "审稿阈值（0~1）\n"
        "- 0.7: 良好以上通过（推荐）"
    ),
    "FEWSHOT_FROM_NOVEL": (
        "从正文取 few-shot\n"
        "- true: 关键生成注入正文好段落做示例（推荐，风格卡的活体版）\n"
        "- false: 不注入（无正文时自动跳过）"
    ),
    "FILM_MODE": (
        "影视镜头卡\n"
        "- true: 叙事段附镜头卡（机位/拍法/出场人物）\n"
        "- false: 关闭（推荐，省 token 约 10-20%）"
    ),
    "DISPLAY_FILM_CARDS": (
        "TUI 显示镜头卡\n"
        "- true: 段首显示镜头卡（FILM_MODE=true 时生效）\n"
        "- false: 隐藏"
    ),
}

for _k, _d in DESC_SUPPLEMENT.items():
    if _k in SPEC and not (SPEC[_k].get("desc") or "").strip():
        SPEC[_k]["desc"] = _d
del _k, _d

GROUPS: list[str] = []
for _k, _v in SPEC.items():
    if _v["group"] not in GROUPS:
        GROUPS.append(_v["group"])


def restart_keys() -> set[str]:
    """需要重启才生效的配置项（SPEC 里标了 `restart=True` 的那些）。

    主要用于两处：
      1. 天机对话框保存时判断「这次改的东西要不要重启」；
      2. 设置界面上给这些项加一行醒目的提示。
    
        English:
    Config items that require a restart to take effect (those marked `restart=True` in SPEC).
        Mainly used in two places:
          1. When the Tianji dialog saves, decide "does this change need a restart";
          2. Add a prominent hint line for these items in the settings UI.
    """
    return {k for k, v in SPEC.items() if v.get("restart")}

_TRUE = {"1", "true", "yes", "on", "是", "开"}
_FALSE = {"0", "false", "no", "off", "否", "关"}


def coerce(key: str, raw: str) -> tuple[Any, str | None]:
    spec = SPEC.get(key)
    if spec is None:
        return raw, None
    t = spec["type"]
    v = (raw or "").strip()
    try:
        if t in ("str", "path"):
            return v, None
        if t == "bool":
            lv = v.lower()
            # 空值必须回 SPEC 默认值，不能当 False。
            # 这里曾经是 `if lv in _FALSE or lv == "": return False`，
            # 于是**所有 default=True 的布尔项在 .env 里没写时都变成 False**——
            # 默认值形同虚设（int / enum 分支都正确处理了空值，只有 bool 漏了）。
            # [EN] Empty values must fall back to the SPEC default, not be treated as False.
            # [EN] This used to be `if lv in _FALSE or lv == "": return False`,
            # [EN] so **all boolean items with default=True became False when not written in .env** —
            # [EN] the default value was effectively void (int / enum branches both handled empty values correctly,
            # [EN] only bool was missed).
            if lv == "":
                return bool(spec["default"]), None
            if lv in _TRUE:
                return True, None
            if lv in _FALSE:
                return False, None
            return bool(spec["default"]), f"{key} 需要 true/false"
        if t == "int":
            n = int(v) if v else spec["default"]
            lo, hi = spec.get("min"), spec.get("max")
            if lo is not None and n < lo:
                return lo, f"{key} 小于下限 {lo}，已夹紧"
            if hi is not None and n > hi:
                return hi, f"{key} 大于上限 {hi}，已夹紧"
            return n, None
        if t == "float":
            n = float(v) if v else spec["default"]
            lo, hi = spec.get("min"), spec.get("max")
            if lo is not None and n < lo:
                return lo, f"{key} 小于下限 {lo}，已夹紧"
            if hi is not None and n > hi:
                return hi, f"{key} 大于上限 {hi}，已夹紧"
            return n, None
        if t == "enum":
            if v == "":
                return spec["default"], None
            if v not in spec["opt"]:
                return spec["default"], f"{key}={v!r} 不在候选内，已回默认"
            return v, None
    except ValueError:
        return spec["default"], f"{key}={raw!r} 无法解析，已回默认"
    return v, None


def parse_env_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        else:
            m = re.search(r"\s+#.*$", v)
            if m:
                v = v[: m.start()].strip()
        if k:
            out[k] = v
    return out


def home_candidates() -> tuple[Path, ...]:
    """桌面目录的几个候选（有的机器桌面在 OneDrive 下）。
        English:
    Several desktop directory candidates (on some machines the desktop is under OneDrive).
    """
    home = Path.home()
    return (home / "OneDrive" / "Desktop", home / "Desktop", home)


def _has_any(p: Path) -> bool:
    """目录里**有没有东西**（空目录 = False）。

    ⚠ 判据故意是"有任何条目"而不是"含 `.nwsproj`"：`config.py` 被 `store` 依赖，
    反向 import `store` 会成环。宁可保守一点 —— 里头有东西就当成"用户在这儿放过书"。
    
        English:
    Whether there is **anything** in the directory (empty directory = False).
        ⚠ The criterion is deliberately "has any entry" instead of "contains `.nwsproj`": `config.py` is depended on by `store`,
        and importing `store` in reverse would create a cycle. Better to be conservative —— if there's anything inside, treat it as "the user once put books here".
    """
    try:
        next(p.iterdir())
        return True
    except (StopIteration, OSError):
        return False


def default_projects_dir() -> Path:
    """默认项目根：`<桌面>/<软件名>/Projects`。

    ★ 软件 2026-10-06 改名（小说世界虚拟模拟 → 小说世界AI模拟），但**数据目录不能跟着改**：
    用户的书全在旧目录里，一改就等于"我的项目不见了"。
    所以规则是 **新名优先、旧名兜底**：
      · 已经存在 `小说世界虚拟模拟/Projects` 的**老用户** → 继续用它（书还在）；
      · 都没有（新装的）→ 建到**新名**下。

    ★★ 2026-10-09 给旧名加了一条**"必须真有书"**的门（用户当天报的
    「`C:\\Users\\chao\\OneDrive\\桌面\\小说世界虚拟模拟` 这个地址有时候会用到，
    但是我已经不想用了」）：
      实测本机 `C:\\Users\\chao\\Desktop\\小说世界虚拟模拟\\Projects` 是**空的**
      —— 书早搬走了，可旧规则会让"默认根"**落在这个空文件夹上**。
      表现出来就是：清空「项目根目录」这一项之后，**一本书都看不见**，
      而用户完全不知道为什么（目录存在、路径也"对"）。
      ⇒ 旧名只有**非空**才作数；空的旧目录直接忽略，落到新名。
      这一条同时治了两个病：不再"用那个不想再用的地址"，
      也不会把一个空文件夹当成"用户的默认书库"。
    
        English:
    Default project root: `<Desktop>/<software name>/Projects`.
        the user's books are all in the old directory, and renaming would mean "my projects are gone".
        So the rule is **new name preferred, old name as fallback**:
          · If neither exists (fresh install) → create under the **new name**.
        ★★ 2026-10-09 added a **"must actually have books"** gate to the old name (reported by the user that day:
        but I don't want to use it anymore"):
          —— the books were moved away long ago, but the old rule would make the "default root" **land on this empty folder**.
          The symptom: after clearing the "project root directory" item, **not a single book is visible**,
          and the user has no idea why (the directory exists, the path is also "correct").
          ⇒ The old name only counts if it is **non-empty**; an empty old directory is simply ignored and it falls through to the new name.
          This one rule cures two diseases at once: no more "using that address I don't want to use anymore",
          and no more treating an empty folder as "the user's default library".
    """
    names = ("小说世界AI模拟", "小说世界虚拟模拟")   # 顺序就是优先级
    # [EN] Order is priority
    for cand in home_candidates():
        if not cand.exists():
            continue
        for name in names:
            p = cand / name / "Projects"
            # 新名：只要目录在就用（它就是当前命名）。
            # 旧名：**必须非空**才作数（否则会指向一个"看着对、其实没书"的地方）。
            # [EN] New name: use it as long as the directory exists (it is the current naming).
            # [EN] Old name: **must be non-empty** to count (otherwise it points to a place that "looks right but
            # [EN] actually has no book").
            if p.exists() and (name == names[0] or _has_any(p)):
                return p
        return cand / names[0] / "Projects"          # 谁都没有 → 用新名建
        # [EN] If neither exists → create using the new name
    return Path.home() / names[0] / "Projects"


class Config:
    """`.env` 的内存映射 + 落盘。

    ★ **`redirect_save`：写盘重定向（给验证脚本用的保险丝）**。
    原因见 `save()` 里的说明 —— 「验证脚本点了一下对话框的『保存』，
    把测试值写进用户真实 `.env`」这件事已经发生**四次**（`MOCK_LLM`、
    `BEAT_SECONDS`、`DEFAULT_PROJECTS_DIR`，以及本轮的 `LLM_BASE_URL` /
    `LLM_API_KEY`）。备份+还原挡不住"脚本中途崩了"和"漏了包"。
    改成：守卫期间**根本不许写真实文件**，从"记得还原"变成"写不进去"。
    
        English:
    In-memory mapping + persistence to disk for `.env`.
        ★ **`redirect_save`: write-to-disk redirection (fuse for verification scripts)**.
        See the explanation in `save()` for the reason —— "a verification script clicked the dialog's Save
        and wrote test values into the user's real `.env`" has already happened **four times** (`MOCK_LLM`,
        `BEAT_SECONDS`, `DEFAULT_PROJECTS_DIR`, and this round's `LLM_BASE_URL` /
        `LLM_API_KEY`). Backup + restore can't stop "the script crashed midway" and "a package was missed".
        Change it to: during the guard, **writing to real files is simply forbidden**, turning "remember to restore" into "can't write".
    """

    # 非 None 时，`save()` 一律写到这里，**绝不碰真实 `.env`**。
    # 由 `tools/verify_ui_common.env_guard()` 设置/恢复。
    # [EN] When non-None, `save()` always writes here, **never touches the real `.env`**.
    # [EN] Set/restored by `tools/verify_ui_common.env_guard()`.
    redirect_save: "Path | None" = None

    def __init__(self, raw: dict[str, str] | None = None):
        self._raw: dict[str, str] = dict(raw or {})
        # ★★★ 2026-10-30：**项目级覆盖层**（书斋 · 运行）。
        #   用户在书斋里改了运行设定 → 只对**这本书**生效，不写 `.env`。
        #   `raw()` 是**所有**定型读法（`s/i/f/b`）的唯一入口，所以闸门只设在那里，
        #   全程序（推演循环、界面、导演）一起跟着变，不用逐个改调用点。
        #   ⚠ 它和 `_raw` 是**两层**：`save()` 只写 `_raw` ⇒ 项目覆盖永远不会
        #     漏进用户的 `.env`（"改了书斋、全局被改掉"是这里最怕的事）。
        #   ⚠ 天机要改的是**全局值**，那里必须读 `g()` 而不是 `raw()`。
        # [EN] ★★★ 2026-10-30: **project-level override layer** (Study · Run).
        # [EN] Edited in the Study -> applies to **this book only**, never written to `.env`.
        # [EN] `raw()` is the single entry point of every typed getter (`s/i/f/b`), so the
        # [EN] gate lives there and the whole program (loop, UI, director) follows without
        # [EN] touching each call site. `save()` writes `_raw` only, so an override can never
        # [EN] leak into the user's `.env`. Tianji edits the **global** value: read `g()` there.
        self._ov: dict[str, str] = {}
        self._lock = threading.RLock()

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        p = path or ENV_PATH
        if p.exists():
            return cls(parse_env_text(p.read_text(encoding="utf-8")))
        return cls()

    def save(self, path: Path | None = None) -> None:
        # ⚠ 顺序要紧：`path` 显式给了就用它（程序自己启动时就是这么存的），
        #   否则看有没有重定向。**重定向优先于默认路径**。
        #   `env_sink_path()` 是**父进程**（回归器）给的保险丝，见它的 docstring：
        #   并行跑时"备份/还原"这种约定会被别的进程踩掉，必须让子进程**写不进去**。
        # [EN] ⚠ Order matters: if `path` is explicitly given, use it (that's how the program itself stores it
        # [EN] at startup),
        # [EN] otherwise check for a redirect. **Redirect takes priority over default path**.
        # [EN] `env_sink_path()` is a fuse given by the **parent process** (the regressor), see its docstring:
        # [EN] When running in parallel, conventions like "backup/restore" get trampled by other processes; the
        # [EN] child process must be made **unable to write**.
        p = path or Config.redirect_save or env_sink_path() or ENV_PATH
        with self._lock:
            lines = ["# 小说世界AI模拟 · 配置文件（程序自动生成）", f"# 版本 {VERSION}", ""]
            for g in GROUPS:
                lines.append(f"# ══════════ {g} ══════════")
                for k, spec in SPEC.items():
                    if spec["group"] != g:
                        continue
                    v = self._raw.get(k, "")
                    # 没设过的项写 SPEC 默认值，别写空串：
                    # 空串会让人以为「这一项没有默认」，也不利于手改配置时对照。
                    # [EN] For items never set, write the SPEC default, not an empty string:
                    # [EN] an empty string makes people think "this item has no default", and isn't good for cross-checking
                    # [EN] when hand-editing config.
                    if v == "" and not spec.get("secret"):
                        d = spec["default"]
                        if spec["type"] == "bool":
                            d = "true" if d else "false"
                        v = "" if d is None else str(d)
                    if spec.get("desc"):
                        # ⚠ `desc` 可以含换行（2026-10-25 起，见 `DESC_SUPPLEMENT`）：
                        #   直接 f-string 拼会**只给第一行加 `#`**，后面的行裸着落进文件，
                        #   而它们常常含 `=`（"设 0 = 不复查"）⇒ 下次读取时会被当成**键**。
                        #   逐行加 `#` 才是对的。
                        # [EN] `desc` may contain newlines (since 2026-10-25, see `DESC_SUPPLEMENT`):
                        # [EN] a plain f-string puts `#` only on the first line, leaving the rest bare,
                        # [EN] and those lines often contain `=` ("0 = off") => they get parsed as **keys**
                        # [EN] on the next read. Add `#` per line.
                        for _seg in str(spec["desc"]).split("\n"):
                            lines.append(f"# {_seg}" if _seg.strip() else "#")
                    if spec["type"] == "enum":
                        lines.append(f"# 候选：{' / '.join(spec['opt'])}")
                    lines.append(f"{k}={v}")
                lines.append("")
            # ⚠ 建目录：`ENV_PATH` 的父目录（程序根）当然存在，但**重定向目标**
            #   （`redirect_save` / `NWS_ENV_SINK`）可能指向一个还没建的临时目录 ——
            #   不建就 `FileNotFoundError`，而 `save()` 抛错会以各种面目出现在
            #   别的脚本里（实测：第一次接 `NWS_ENV_SINK` 时就这么炸了一下）。
            # [EN] ⚠ Create directory: the parent directory of `ENV_PATH` (program root) of course exists, but the
            # [EN] **redirect target**
            # [EN] (`redirect_save` / `NWS_ENV_SINK`) may point to a temp directory that hasn't been created yet —
            # [EN] if not created it'll be `FileNotFoundError`, and a `save()` throw shows up in various guises in
            # [EN] other scripts (observed: it blew up exactly like this the first time we wired in
            # [EN] `NWS_ENV_SINK`).
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\n".join(lines), encoding="utf-8")

    def write_example(self, path: Path | None = None) -> None:
        p = path or ENV_EXAMPLE_PATH
        lines = ["# 小说世界AI模拟 · 配置样例", "# 复制为 .env 后按需要修改。", ""]
        for g in GROUPS:
            lines.append(f"# ══════════ {g} ══════════")
            for k, spec in SPEC.items():
                if spec["group"] != g:
                    continue
                if spec.get("desc"):
                    # 同 `save()`：逐行加 `#`（多行 desc 的裸行会被当成键）。
                    # [EN] Same as `save()`: add `#` per line (a bare line of a multi-line desc becomes a key).
                    for _seg in str(spec["desc"]).split("\n"):
                        lines.append(f"# {_seg}" if _seg.strip() else "#")
                if spec["type"] == "enum":
                    lines.append(f"# 候选：{' / '.join(spec['opt'])}")
                d = spec["default"]
                if spec["type"] == "bool":
                    d = "true" if d else "false"
                if spec.get("secret"):
                    d = ""
                lines.append(f"{k}={d}")
            lines.append("")
        p.write_text("\n".join(lines), encoding="utf-8")

    def raw(self, key: str) -> str:
        """**有效值**：这本书覆盖过就用覆盖值，否则用 `.env` 里的全局值。

        ⚠ 别在别处再拼一遍"先看覆盖再看全局"—— 那就是"同一件事两处实现"，
          两处迟早在"空串算不算覆盖"这种细节上分岔。
        [EN] **Effective value**: the project override when there is one, else the global `.env`
        [EN] value. Do not re-implement this lookup anywhere else.
        """
        with self._lock:
            if key in self._ov:
                ov = str(self._ov[key])
                # 空串**不算**覆盖（与 `has()` 同一个口径：空 = 没设过）。
                # [EN] An empty string is **not** an override (same rule as `has()`).
                if ov != "":
                    return ov
            return self._raw.get(key, "")

    def g(self, key: str) -> str:
        """**只看全局值**（无视项目覆盖）—— 天机里显示、编辑的就是它。

        ⚠ 天机若读 `raw()`：一旦这本书覆盖过，天机里显示的就是这本书的数，
          用户点"保存"会把它写进 `.env` ⇒ 全局被一本书悄悄改掉。
        [EN] **Global value only** (ignores project overrides) -- what Tianji shows and edits.
        [EN] If Tianji read `raw()` while an override was active, saving would write another
        [EN] book's number into `.env`.
        """
        with self._lock:
            return self._raw.get(key, "")

    def gs(self, key: str) -> str:
        """全局值的字符串读法（同上，只是过了 `coerce`）。"""
        v, _ = coerce(key, self.g(key))
        return str(v)

    def gi(self, key: str) -> int:
        """全局值的整数读法（与 `i()` 同一套兜底，只是**不看覆盖**）。"""
        v, _ = coerce(key, self.g(key))
        try:
            return int(v)
        except (ValueError, TypeError):
            spec = SPEC.get(key)
            if spec and "default" in spec:
                return int(spec["default"])
            return 0

    # ── 项目级覆盖（书斋 · 运行）──
    # [EN] ── Project overrides (Study · Run) ──
    def overrides(self) -> dict[str, str]:
        """当前生效的项目覆盖（**副本**，改它不会影响配置）。"""
        with self._lock:
            return dict(self._ov)

    def set_overrides(self, kv: dict[str, str] | None) -> None:
        """**整体替换**覆盖层（切书时用；`None`/空 = 回到纯全局）。"""
        with self._lock:
            self._ov = {str(k): str(v) for k, v in (kv or {}).items()
                        if str(v).strip() != ""}

    def set_override(self, key: str, value) -> None:
        """给某一项设/换覆盖值（`''` = 取消这一项的覆盖）。"""
        with self._lock:
            txt = str(value)
            if txt.strip() == "":
                self._ov.pop(str(key), None)
            else:
                self._ov[str(key)] = txt

    def clear_overrides(self) -> None:
        with self._lock:
            self._ov = {}

    def has(self, key: str) -> bool:
        with self._lock:
            return self.raw(key) != ""

    def s(self, key: str) -> str:
        v, _ = coerce(key, self.raw(key))
        return str(v)

    def i(self, key: str) -> int:
        v, _ = coerce(key, self.raw(key))
        try:
            return int(v)
        except (ValueError, TypeError):
            # 如果转换失败，尝试从 SPEC 获取默认值
            # [EN] If conversion fails, try to get the default value from SPEC
            spec = SPEC.get(key)
            if spec and "default" in spec:
                return int(spec["default"])
            return 0

    def f(self, key: str) -> float:
        v, _ = coerce(key, self.raw(key))
        return float(v)

    def b(self, key: str) -> bool:
        v, _ = coerce(key, self.raw(key))
        return bool(v)

    def set(self, key: str, value: Any) -> str | None:
        with self._lock:
            self._raw[key] = str(value)
        return None

    def update(self, kv: dict[str, Any]) -> list[str]:
        msgs = []
        for k, v in kv.items():
            m = self.set(k, v)
            if m:
                msgs.append(m)
        return msgs

    def as_dict(self) -> dict[str, Any]:
        return {k: (coerce(k, self._raw.get(k, ""))[0] if k in self._raw else SPEC[k]["default"])
                for k in SPEC}

    def resolved(self, key: str) -> Path:
        v = self.s(key)
        if not v:
            return APP_DIR
        p = Path(os.path.expandvars(v))
        if not p.is_absolute():
            p = APP_DIR / p
        return p

    def projects_dir(self) -> Path:
        v = self.s("DEFAULT_PROJECTS_DIR")
        return Path(v) if v else default_projects_dir()

    @property
    def mock(self) -> bool:
        return self.b("MOCK_LLM")

    def model_of(self, tier: str) -> str:
        return self.s({"front": "MODEL_FRONT", "daily": "MODEL_DAILY", "cheap": "MODEL_CHEAP"}[tier])


CFG = Config.load()