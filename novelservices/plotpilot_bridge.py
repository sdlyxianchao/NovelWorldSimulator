# -*- coding: utf-8 -*-
"""NWS → PlotPilot（墨枢）的**接入层**（桥）。

给谁用的
--------
给主程序里的 **剧作者 / 编剧（screenwriter）** 用。目的是：
**把"设计这一章该发生什么、结构怎么立"这件事交给 PlotPilot 去干**，
而不是让编剧 Agent 自己拼提示词问模型。PlotPilot 是叙事引擎内核，
擅长在长篇跨度里维护人物一致性、因果链、伏笔与故事线结构 —— 正是编剧的活。

它不做什么
----------
**不改 PlotPilot 的源码。** 一切通过它自己的 REST 接口
（`interfaces/main:app` 起的 uvicorn 服务，默认 `http://127.0.0.1:8005`）走。
所以上游怎么升级都不影响这里 —— 顶多是接口不兼容，那也只会**降级**，不会崩主程序。

三条设计纪律（与 mumu_bridge 一致，都是被坑出来的）
------------------------------------------------
1. **绝不成为单点故障。** 服务没起、超时、生成失败、返回空章 —— 一律返回
   `BridgeResult(ok=False, reason=...)`，**由调用方回退到原来的内部编剧逻辑**。
   这种外部生成环节不能挂在关键路径上赌它成功。
2. **纯标准库。** 主程序跑在 Python 3.13，PlotPilot 的 venv 是 3.13/3.14
   （依赖各不相同）。两边**环境不同**，所以这里只用 stdlib，通过 HTTP 说话 ——
   不 import 对方 venv 里的任何东西。
3. **回环请求必须绕代理。** 本机设了系统代理，连 127.0.0.1 的请求会被丢给代理，
   一个死的服务看起来是活的。清 `HTTP_PROXY` 不够（Windows 上 urllib 还读注册表）
   → 显式空 `ProxyHandler`。

English:
**Integration layer** (bridge) from NWS → PlotPilot.
Who it's for
--------
For the **screenwriter** Agent in the main program. The goal is:
**hand off "designing what should happen in this chapter and how the structure holds"**
to PlotPilot, instead of letting the screenwriter Agent assemble prompts itself.
PlotPilot is a narrative-engine kernel, good at maintaining character consistency,
causal chains, foreshadowing and storyline structure across a long span — exactly the screenwriter's job.
What it does not do
----------
**Does not modify PlotPilot's source.** Everything goes through its own REST API
(the uvicorn service started by `interfaces/main:app`, default `http://127.0.0.1:8005`).
Three design disciplines (same as mumu_bridge)
------------------------------------------------
1. **Never become a single point of failure.**
2. **Pure standard library.**
3. **Loopback requests must bypass the proxy.**
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "PLOTPILOT_DIR", "PLOTPILOT_BASE_URL", "PLOTPILOT_ENV",
    "BridgeStatus", "BridgeResult", "ScreenTask",
    "service_status", "service_url", "read_service_env", "save_service_env",
    "model_env_for", "write_llm_env",
    "start_service", "stop_service", "ensure_novel", "forget_novel",
    "generate_chapter", "generate_outline", "describe",
]

# ── 路径（全部相对本文件，不写死盘符）──────────────────────────────
# [EN] ── Paths (all relative to this file, no hardcoded drive letters) ──
HERE = Path(__file__).resolve().parent
PLOTPILOT_DIR = HERE / "PlotPilot"

#: 上游项目地址（界面上要标出来 —— 这套服务不是本项目写的）
# [EN] : Upstream project address (must be shown in the UI)
UPSTREAM = "https://github.com/shenminglinyi/PlotPilot"

#: 默认连接地址（真值从本程序 Config 的 PLOTPILOT_HOST/PLOTPILOT_PORT 读）
# [EN] : Default connection address (real value from Config PLOTPILOT_HOST/PLOTPILOT_PORT)
PLOTPILOT_BASE_URL = "http://127.0.0.1:8005"

#: PlotPilot 自己的 `.env`（仓库根；`load_env.py` 起的 uvicorn 会读它）
# [EN] : PlotPilot's own `.env` (repo root; read by the uvicorn started via `load_env.py`)
PLOTPILOT_ENV = PLOTPILOT_DIR / ".env"

#: 小说(项目)映射缓存：把 NWS 的书名映射到 PlotPilot 的 novel_id。
# [EN] : Novel mapping cache: maps NWS book name to PlotPilot novel_id.
_MAP_NAME = ".plotpilot_novels.json"

# API 前缀（与 interfaces/api/settings.py 的 API_V1_PREFIX 对齐）
# [EN] : API prefix (aligned with interfaces/api/settings.py API_V1_PREFIX)
API = "/api/v1"


# ══════════════════════════════════════════════════════════════════
#  结果类型
# [EN] Result types
# ══════════════════════════════════════════════════════════════════
@dataclass
class BridgeStatus:
    """服务状态。`reason` 是**给人看的一句话**，要能直接显示在界面上。

    English:
    Service status. `reason` is a one-liner for humans, displayable in the UI.
    """

    ok: bool
    reason: str = ""
    base_url: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class BridgeResult:
    """一次生成的结果。失败时 `reason` **必须**说清是哪一环坏的。

    English:
    The result of one generation. On failure `reason` must state which link broke.
    """

    ok: bool
    text: str = ""
    reason: str = ""
    chapter_number: int = 0
    elapsed: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenTask:
    """交给 PlotPilot 的一件事：**为这一章设计结构 / 产出章节方案**。

    PlotPilot 是叙事引擎，给它"书名 + 梗概 + 人物 + 本章要讲什么(outline)"，
    它返回一章的结构化方案（含细纲与正文草稿），编剧据此提炼当天的细纲。

    English:
    One thing handed to PlotPilot: **design the structure / produce the chapter plan
    for this chapter**. PlotPilot returns a structured chapter plan; the screenwriter
    distills the day's detailed outline from it.
    """

    project_key: str                     # NWS 这边的书名（用来找/建对应的 PlotPilot novel）
    novel_dir: Path | None = None        # NWS 项目目录（放映射缓存；可为 None）
    title: str = ""                      # 这一章的标题
    premise: str = ""                    # 小说梗概（建 novel 时一次性写入）
    outline: str = ""                    # 本章要讲什么（喂给 generate-chapter-stream 的 outline）
    characters: list[str] = field(default_factory=list)
    genre: str = ""
    target_words: int = 2500
    model: str = ""                      # 空 = 用服务端默认
    chapter_number: int = 0              # 0 = 自动取下一章号
    timeout: float = 900.0               # 等生成完成的上限（秒）


# ══════════════════════════════════════════════════════════════════
#  连接地址 / 配置读写（天机的「外部创作服务」页读写本程序 Config）
# [EN] Connection / config read-write (Tianji's "External Services" page writes NWS Config)
# ══════════════════════════════════════════════════════════════════
def _config() -> Any:
    """懒加载本程序 Config **实例**（本模块要能独立跑，不强制依赖主程序）。

    ★★★ 2026-10-23 **修**：这里原来返回的是 `Config` **类本身**（不是实例）。
      `getattr(Config, 'PLOTPILOT_PORT')` 拿不到用户配置（那些值在实例的
      `_raw` 里）⇒ 下面所有读配置的地方**永远落到硬编码的默认值**：

        · `service_url()`   → 永远 127.0.0.1:8005（**用户改了端口也不生效**）
        · `start_service()` → `uvicorn --port 8005`（起的不是用户配的那个端口）
        · `stop_service()`  → 去默认端口找 pid（改了端口就**停不掉**）
        · `read_service_env()` → 永远返回 `{}`（天机里那几行读不到真实值）

      ⚠ 这不是新发现：本文件 2026-10-17 修 `save_service_env` 时**已经写明**
        "`_config()` 返回的是 `Config` 类本身（不是实例）"，但当时只改了写入那一条，
        读的那四条漏了 —— 典型的"**修了一半**"。用户端口恰好都是默认值，
        所以一直没有症状（真 bug 藏着）。
      ⚠ 类属性还是要能取到：`Config.redirect_save` 是**类变量**（测试期写盘重定向），
        它走的是 `from config import Config`，不经过这里，所以不受影响。
    [EN] ★★★ 2026-10-23 **fixed**: this used to return the `Config` **class itself** rather
    than an instance. `getattr(Config, 'PLOTPILOT_PORT')` cannot see the user's settings
    (they live in the instance's `_raw`), so every reader below **fell back to the
    hard-coded default**: `service_url()` was always 127.0.0.1:8005 (a changed port had no
    effect), `start_service()` launched uvicorn on 8005, `stop_service()` looked for the pid
    on the default port (it could not stop a service on a changed port), and
    `read_service_env()` always returned `{}`.
    ⚠ Not a new finding: the 2026-10-17 fix to `save_service_env` in this very file already
    stated "`_config()` returns the `Config` class itself", but only the write path was
    fixed and the four readers were missed -- a textbook **half-fix**. The user's ports
    happen to be the defaults, so there was no symptom (the bug simply hid).
    ⚠ Class attributes still work: `Config.redirect_save` is a **class variable** (the
    test-time write redirect) and is imported directly, not through here.
    """
    try:
        from config import CFG                     # 单例实例（**读配置要走 `s()`/`i()`**）
        return CFG
    except Exception:                                    # noqa: BLE001
        return None


def _cfg_s(cfg: Any, key: str, default: str = '') -> str:
    """从 Config **实例**读一个字符串配置（读不到就是 `default`）。

    ★★★ 2026-10-23：这里**不能**用 `getattr(cfg, key, default)`。
      `Config` 没有 `__getattr__`（类与实例都没有），
      `getattr` 永远拿到 `default` —— 于是本文件所有读配置的地方
      **一律落到硬编码的默认值**：改了端口不生效、停服务停不掉、天机里读不到真实值。
      读配置的唯一入口是 `cfg.s()` / `cfg.i()` / `cfg.b()`。
    [EN] ★★★ 2026-10-23: **never** use `getattr(cfg, key, default)` here. `Config` has no
    `__getattr__` (neither on the class nor the instance), so `getattr` always yields the
    default -- which made every config read in this file fall back to the hard-coded value:
    a changed port had no effect, the service could not be stopped, and Tianji read no real
    values. The only entry points are `cfg.s()` / `cfg.i()` / `cfg.b()`.
    """
    try:
        v = cfg.s(str(key))
        return str(v) if str(v).strip() else default
    except Exception:                                    # noqa: BLE001
        return default


def service_url() -> str:
    """服务地址（从本程序 Config 的 PLOTPILOT_HOST/PLOTPILOT_PORT 现读，带默认值）。

    English:
    Service address (read live from Config PLOTPILOT_HOST/PLOTPILOT_PORT, with defaults).
    """
    cfg = _config()
    host = _cfg_s(cfg, "PLOTPILOT_HOST", "127.0.0.1")
    try:
        port = int(_cfg_s(cfg, "PLOTPILOT_PORT", "8005"))
    except (TypeError, ValueError):
        port = 8005
    return f"http://{host}:{port}"


def read_service_env() -> dict[str, str]:
    """读回天机写进来的 PlotPilot 连接配置（host/port/model/enabled）。

    English:
    Read back the PlotPilot connection config written by Tianji (host/port/model/enabled).
    """
    cfg = _config()
    if cfg is None:
        return {}
    out: dict[str, str] = {}
    for k in ("PLOTPILOT_HOST", "PLOTPILOT_PORT", "PLOTPILOT_MODEL", "PLOTPILOT_ENABLED"):
        v = _cfg_s(cfg, k, "")
        if v:
            out[k] = v
    return out


def save_service_env(kv: dict[str, Any]) -> str | None:
    """把若干键写进 **PlotPilot 自己的 `.env`**。返回 `None` = 成功，否则是给人看的一句话。

    ★★★ 2026-10-17 **修**：这个函数以前写的是**本程序的 Config**（`setattr` + `save`），
      而且 `_config()` 返回的是 `Config` **类本身**（不是实例）⇒
      `getattr(Config, 'PLOTPILOT_HOST')` 拿不到用户配置、`setattr` 改的是类属性、
      `Config.save()` 直接 `TypeError: missing 1 required positional argument: 'self'`。
      后果（真机日志里一直有，只是被"不影响自写"吞掉了）：

          WARNING: PlotPilot 模型没推过去（不影响自写）：
                   写配置失败：TypeError("Config.save() missing 1 required positional argument: 'self'")

      ⇒ **用户在「AI模型配置」里点的那个模型，从来没进过 PlotPilot 的 `.env`**，
      它一直在用 `.env` 里原有的（或内置假模型）。`PenShot` 那座桥 2026-10-16
      已经按名字的语义改成"写服务自己的 `.env`"，这座当时漏了。
      现在对齐：逐行替换 PlotPilot `.env` 里的同名键，保留注释与未知键，
      写前留 `.env.bak`，回归期间走 `NWS_ENV_SINK` 重定向。

    [EN] ★★★ 2026-10-17 **fixed**: this function used to write the **NWS Config**
    [EN] (`setattr` + `save`), and `_config()` returns the `Config` **class itself** (not an instance)
    [EN] => `getattr(Config, ...)` cannot read the user's settings, `setattr` mutates class attributes,
    [EN] and `Config.save()` raises `TypeError: missing 1 required positional argument: 'self'`.
    [EN] Consequence (always present in the real-machine log, only swallowed by "does not affect
    [EN] self-writing"): **the model the user picked was never pushed into PlotPilot's `.env`**; it kept
    [EN] using whatever was already there (or the built-in fake model). The PenShot bridge was already
    [EN] fixed on 2026-10-16 to "write the service's own `.env`"; this one was missed. Now aligned.
    """
    return write_llm_env(kv)


def _sink_path() -> Path | None:
    """回归/验证期间的**写盘重定向**（与 `mumu_bridge` / `penshot_bridge` 同一套保险丝）。

    ★ 为什么必须守：天机的「外部创作服务」页会写**另一个文件**（PlotPilot 的 `.env`），
      而验证脚本会点"保存"。没有这道闸，跑一次判据就把测试值写进用户真实的服务配置。

    [EN] **Disk-write redirection** during regression/verification (same fuse as the other bridges).
    [EN] ★ Why it must be guarded: Tianji's page writes **another file** (PlotPilot's `.env`) and the
    [EN] verification scripts click "Save". Without this gate, one criteria run writes test values into
    [EN] the user's real service config.
    """
    p = (os.environ.get("NWS_ENV_SINK") or "").strip()
    if p:
        return Path(p).expanduser().with_suffix(".plotpilot")
    try:
        from config import Config                          # 懒加载：本模块要能独立跑
        # [EN] Lazy loading: this module must be able to run standalone
        if Config.redirect_save is not None:
            return Path(Config.redirect_save).with_suffix(".plotpilot")
    except Exception:                                      # noqa: BLE001
        pass
    return None


def write_llm_env(kv: dict[str, Any]) -> str | None:
    """把键写进 PlotPilot 自己的 `.env`（起服务时 cwd 钉在本目录，它才会读）。

    与 `penshot_bridge.write_llm_env` / `mumu_bridge.write_llm_env` 同一范式：
      · 逐行替换已知键，**保留注释与未知键**（用户自己加的配置不能被抹掉）；
      · 表里没有的键追加到末尾的「由天机写入」小节；
      · 写之前留一份 `.env.bak`；
      · `NWS_ENV_SINK` / `Config.redirect_save` 命中时**不写真文件**。
    返回 `None` = 成功，否则是给人看的一句话。

    [EN] Write keys into PlotPilot's own `.env`. Same pattern as the other two bridges: replace known
    [EN] keys line by line keeping comments and unknown keys; append new keys to a "written by Tianji"
    [EN] section; back up `.env` first; honour the sink redirection.
    """
    if PLOTPILOT_ENV.exists():
        try:
            base_text = PLOTPILOT_ENV.read_text(encoding="utf-8")
        except OSError as e:
            return f"读不了 {PLOTPILOT_ENV.name}：{e!r}"
    else:
        base_text = ""
        example = PLOTPILOT_DIR / ".env.example"
        try:
            if example.exists():
                base_text = example.read_text(encoding="utf-8")
        except OSError:
            pass

    sink = _sink_path()
    target = sink if sink else PLOTPILOT_ENV

    want = {k: str(v) for k, v in (kv or {}).items() if k}
    seen: set[str] = set()
    out: list[str] = []
    for ln in base_text.splitlines():
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
        out += ["", "# ── 由天机 ·「外部创作服务」页写入（NovelWorldSimulator）──"]
        out += [f"{k}={want[k]}" for k in missing]

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not sink and PLOTPILOT_ENV.exists():
            PLOTPILOT_ENV.with_suffix(".env.bak").write_bytes(
                PLOTPILOT_ENV.read_bytes())
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError as e:
        return f"写不了 {target.name}：{e!r}"
    return None


# ══════════════════════════════════════════════════════════════════
#  模型选择 → 服务自己的 .env（天机「外部创作服务」页的「来自 AI模型配置」下拉）
# [EN] Model pick → the service's own .env (the "from AI Model Config" dropdown)
# ══════════════════════════════════════════════════════════════════
def _sink_path() -> Path | None:
    """回归/验证期间的**写盘重定向**（沿用 mumu_bridge 那套保险丝）。

    ★ 为什么这里也要守：天机的「外部创作服务」页会写**另一个文件**
      （PlotPilot 仓库根的 `.env`）。验证脚本点一下"保存"，就会把测试值
      写进用户真实的服务配置里。所以父进程给了 `NWS_ENV_SINK`
      （或进程内设了 `Config.redirect_save`）时，这里**不写真实文件**，
      写进旁边一个 `*.plotpilot-sink` 里。

    English:
    **Disk-write redirection** during regression/verification (same fuse as mumu_bridge).
    """
    p = (os.environ.get("NWS_ENV_SINK") or "").strip()
    if p:
        return Path(p).expanduser().with_suffix(".plotpilot")
    try:
        from config import Config                          # 懒加载：本模块要能独立跑
        # [EN] Lazy loading: this module must be able to run standalone
        if Config.redirect_save is not None:
            return Path(Config.redirect_save).with_suffix(".plotpilot")
    except Exception:                                      # noqa: BLE001
        pass
    return None


def model_env_for(entry: Any) -> tuple[dict[str, str], str]:
    """把 NWS「AI模型配置」里的一条模型，映射成 PlotPilot `.env` 认的键。

    返回 `(键值表, 警告)`；**警告非空 = 不兼容，调用方不许写**，应把警告
    原样显示给用户。

    PlotPilot 认四套凭证（见 `infrastructure/ai/llm_environment.py` 与
    `application/ai/llm_control_service.py` 的 `_build_initial_config`）：
    `ANTHROPIC_*` / `OPENAI_*` / `GEMINI_*` / `ARK_*`。按 base_url 的
    host 认领：
      * host 含 `anthropic`       → `ANTHROPIC_*`（钉 `LLM_PROVIDER=anthropic`）
      * host 含 `volces`/`ark.cn` → `ARK_*`（钉 `LLM_PROVIDER=ark`）
      * 其余（含 ollama）          → `OPENAI_*`（钉 `LLM_PROVIDER=openai`）

    ★ 钉 `LLM_PROVIDER` 是必须的：`.env` 里若残留别家的 API key，
      `_build_initial_config` 按「anthropic > openai > gemini > ark」的
      固定顺序挑**第一个有 key 的**，我们新写的键会被旧键压掉。
    ★ base_url 写在 `/v1` 这一层就行：anthropic provider 自己会剥掉尾部
      `/v1`（SDK 再拼 `/v1/messages`），openai/ark 由 SDK 拼
      `/chat/completions`（`infrastructure/ai/url_utils.py` 也会兜底剥后缀）。
    ★ 没有 API Key 时不写：PlotPilot 的 `provider_factory` 在缺 key/缺模型时
      **静默退回内置假模型**（比报错更坏），所以这里直接给警告。

    English:
    Map one NWS model-registry entry to the keys PlotPilot's `.env` understands.
    A non-empty warning means "incompatible — do not write".
    """
    model = str(getattr(entry, "model", "") or "").strip()
    base = str(getattr(entry, "base_url", "") or "").strip()
    key = str(getattr(entry, "api_key", "") or "").strip()
    provider = str(getattr(entry, "provider", "") or "").strip()
    if not model:
        return {}, "这个模型没填模型名（model 是空的），没法写"
    if not base:
        return {}, "这个模型没填服务地址（base_url 是空的），没法写"
    host = (urllib.parse.urlsplit(base).netloc or base).lower()
    if "anthropic" in host:
        if not key:
            return {}, "Anthropic 通道要求 API Key（PlotPilot 缺 key 会静默改用内置假模型）"
        kv = {"ANTHROPIC_API_KEY": key, "ANTHROPIC_BASE_URL": base,
              "ANTHROPIC_MODEL": model, "LLM_PROVIDER": "anthropic"}
    elif "volces" in host or "ark.cn" in host:
        if not key:
            return {}, "火山方舟(Ark)通道要求 API Key（PlotPilot 缺 key 会静默改用内置假模型）"
        kv = {"ARK_API_KEY": key, "ARK_BASE_URL": base,
              "ARK_MODEL": model, "LLM_PROVIDER": "ark"}
    else:
        if not key and provider != "ollama":
            return {}, ("PlotPilot 的 OpenAI 兼容通道要求 API Key"
                        "（缺 key 它会静默改用内置假模型，比报错更坏）")
        kv = {"OPENAI_API_KEY": key, "OPENAI_BASE_URL": base,
              "OPENAI_MODEL": model, "LLM_PROVIDER": "openai"}
    return kv, ""


def write_llm_env(kv: dict[str, Any]) -> str | None:
    """把模型键写进 PlotPilot 自己的 `.env`（仓库根，`load_env.py` 读它）。

    与 `mumu_bridge.save_service_env` 同一套范式：
      · 逐行替换已知键，**保留注释与未知键**；
      · 表里没有的键追加到末尾的「由天机写入」小节；
      · 写之前留一份 `.env.bak`；
      · `NWS_ENV_SINK` / `Config.redirect_save` 命中时**不写真文件**。
    `.env` 不存在时从 `.env.example` 播种（例文件也没有就新建）。
    返回 `None` = 成功，否则是给人看的一句话。

    English:
    Write the model keys into PlotPilot's own `.env`. Same pattern as mumu_bridge.
    """
    if PLOTPILOT_ENV.exists():
        try:
            base_text = PLOTPILOT_ENV.read_text(encoding="utf-8")
        except OSError as e:
            return f"读不了 {PLOTPILOT_ENV.name}：{e!r}"
    else:
        example = PLOTPILOT_DIR / ".env.example"
        try:
            base_text = example.read_text(encoding="utf-8") if example.exists() else ""
        except OSError:
            base_text = ""

    sink = _sink_path()
    target = sink if sink else PLOTPILOT_ENV

    want = {k: str(v) for k, v in (kv or {}).items() if k}
    seen: set[str] = set()
    out: list[str] = []
    for ln in base_text.splitlines():
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
        out += ["", "# ── 由天机 ·「外部创作服务」页写入（NovelWorldSimulator）──"]
        out += [f"{k}={want[k]}" for k in missing]

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not sink and PLOTPILOT_ENV.exists():
            PLOTPILOT_ENV.with_suffix(".env.bak").write_bytes(PLOTPILOT_ENV.read_bytes())
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError as e:
        return f"写不了 {target.name}：{e!r}"
    return None


# ══════════════════════════════════════════════════════════════════
#  服务探活 / 起停
# [EN] Service liveness probe / start-stop
# ══════════════════════════════════════════════════════════════════
#: 只连本机 —— **必须显式禁用代理**，理由见模块头第 3 条。
# [EN] : Connect only to localhost —— proxy must be explicitly disabled.
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def service_status(timeout: float = 1.5) -> BridgeStatus:
    """服务在不在？**永不抛异常**（调用方常在界面线程里问它）。

    English:
    Is the service up? Never throws an exception.
    """
    if not PLOTPILOT_DIR.exists():
        return BridgeStatus(False, "没找到 PlotPilot（novelservices 目录被删掉了？）")
    base = service_url()
    try:
        with _NO_PROXY.open(base + "/health", timeout=timeout) as r:
            ok = 200 <= getattr(r, "status", 0) < 300
        return BridgeStatus(ok, "" if ok else f"/health 返回 {r.status}", base)
    except urllib.error.HTTPError as e:
        return BridgeStatus(False, f"/health 返回 HTTP {e.code}", base)
    except Exception as e:                                   # noqa: BLE001
        return BridgeStatus(False, f"连不上 {base}（{type(e).__name__}）", base)


def _venv_python() -> Path | None:
    """PlotPilot venv 的解释器（Windows 优先 pythonw.exe，避免多黑窗）。

    English:
    PlotPilot venv interpreter (pythonw.exe on Windows to avoid extra consoles).
    """
    for rel in (("Scripts/pythonw.exe", "Scripts/python.exe", "bin/python")
                if os.name == "nt" else ("bin/python",)):
        p = PLOTPILOT_DIR / ".venv" / rel
        if p.exists():
            return p
    return None


#: uvicorn 日志与 pid 文件（与 `penshot_bridge` 同一套做法：日志落盘才好排查）
# [EN] uvicorn log & pid file (same approach as `penshot_bridge`: keep the log on disk)
_LOG_DIR = PLOTPILOT_DIR / "logs"
_UVICORN_LOG = _LOG_DIR / "uvicorn.log"


def _emit(on_line, line: str) -> None:
    """把一行输出交给调用方（没回调就什么都不做，绝不因它中断）。
        English:
    Hand one line to the caller (no-op without a callback; never let it break the flow).
    """
    if on_line is None:
        return
    try:
        on_line(line)
    except Exception:                                        # noqa: BLE001
        pass


def _tail_into(log_path, pos: int, on_line) -> int:
    """把日志文件里 `pos` 之后的新内容**逐行**发出去，返回新位置（实时输出的来源）。

    ★ 子进程是 `Popen(stdout=日志文件)` 起的（detach 后父进程不能持有管道），
      所以"实时输出"只能从它已经在写的那个文件里取。
    [EN] The child runs with `Popen(stdout=<log file>)` (a detached child must not hold a
    [EN] pipe), so live output can only come from the file it is already writing.
    """
    if on_line is None or log_path is None:
        return pos
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size <= pos:
                return size if size < pos else pos
            f.seek(pos)
            data = f.read()
    except OSError:
        return pos
    for ln in data.decode("utf-8", "replace").splitlines():
        if ln.strip():
            _emit(on_line, ln)
    return pos + len(data)


def _wait_health(timeout: float, log_path=None, on_line=None) -> tuple[bool, float]:
    """等健康检查通过（最多 `timeout` 秒）。返回 (就绪?, 等了几秒)。

    给了 `log_path` 就**边等边**把日志新行发出去。
        English:
    Wait until the health check passes (up to `timeout` seconds). Returns (ready?, seconds waited).
    With `log_path` given, new log lines are emitted **while waiting**.
    """
    t0 = time.time()
    pos = 0
    if log_path is not None:
        try:
            pos = log_path.stat().st_size
        except OSError:
            pos = 0
    while time.time() - t0 < timeout:
        if service_status(timeout=1.5).ok:
            pos = _tail_into(log_path, pos, on_line)
            return True, time.time() - t0
        pos = _tail_into(log_path, pos, on_line)
        time.sleep(1.0)
    _tail_into(log_path, pos, on_line)
    return False, time.time() - t0


def start_service(timeout: float = 600.0, on_line=None) -> tuple[bool, str]:
    """后台拉起 PlotPilot 服务（**detached**，uvicorn 单进程）。**慢**，别在界面线程同步调。

    默认禁止自动驾驶守护进程（DISABLE_AUTO_DAEMON=1），因为我们走
    generate-chapter-stream 单章直出，不需要连写守护进程。

    ★★ 2026-10-17 修（用户：「start 程序你看下是否可以成功启动所有外部服务」——
       实测 PlotPilot **一台都起不来**，而且就算起来了也回不来）。旧实现是：

           subprocess.run([uvicorn, ...], capture_output=True, timeout=timeout+60)

       两个病，都很隐蔽：
         ① **不 detach**：uvicorn 是前台进程，`subprocess.run` 会一直等到它退出 ——
            于是"服务已经就绪"的那一刻函数**永远不返回**，非等到 timeout 才报
            「启动超过 N 秒还没返回」，把它判成失败（而服务其实活得好好的）；
         ② 失败时只把 **stdout** 的尾巴拼进消息，而 uvicorn 的报错在 **stderr** ⇒
            用户只拿到一句"退出码 1"，没有任何线索。
       ⇒ 改成与 `penshot_bridge` 同一套：`Popen`（DETACHED + NEW_GROUP + NO_WINDOW，
         带 BREAKAWAY_FROM_JOB，宿主作业不允许脱离时退一次）+ **轮询健康检查**，
         日志落 `logs/uvicorn.log`，失败时把那几行尾巴交出去。

        English:
    Launch the PlotPilot service detached (uvicorn, single process). Slow; don't call it
    synchronously on the UI thread. Disables the autopilot daemon by default.

    ★★ Fixed 2026-10-17 (user: "check whether start can bring up all external services" --
       PlotPilot could not start at all, and even when it did the call never returned).
       The old implementation was:
           subprocess.run([uvicorn, ...], capture_output=True, timeout=timeout+60)
       Two hidden diseases:
         ① **not detached**: uvicorn runs in the foreground, so `subprocess.run` waits for it to
            exit -- the moment the service becomes ready, the function **never returns**; it only
            times out and reports "startup exceeded N seconds" (while the service is perfectly alive);
         ② on failure only the **stdout** tail was reported, while uvicorn prints errors to
            **stderr** ⇒ the user got "exit code 1" and nothing else.
       ⇒ Same approach as `penshot_bridge`: `Popen` (DETACHED + NEW_GROUP + NO_WINDOW, with
         BREAKAWAY_FROM_JOB and a retry without it) + **health polling**; log to
         `logs/uvicorn.log`; hand back the tail on failure.
    """
    import subprocess

    if service_status().ok:
        _emit(on_line, "● 服务本来就在跑（幂等：不再起第二个）")
        return True, "服务本来就在跑"

    py = _venv_python()
    if py is None:
        _emit(on_line, "✘ PlotPilot 的 venv 还没建好（先装依赖）")
        return False, "PlotPilot 的 venv 还没建好（先装依赖）"
    cfg = _config()
    host = _cfg_s(cfg, "PLOTPILOT_HOST", "127.0.0.1")
    try:
        port = int(_cfg_s(cfg, "PLOTPILOT_PORT", "8005"))
    except (TypeError, ValueError):
        port = 8005

    argv = [str(py), "-m", "uvicorn", "interfaces.main:app",
            "--host", str(host), "--port", str(port),
            "--workers", "1", "--log-level", "info"]
    # 弹窗里先看到"到底跑的是什么命令"（用户 2026-10-17 明确要这个）
    # [EN] Show "what command is actually being run" first (user's request, 2026-10-17)
    _emit(on_line, "$ " + " ".join(argv))
    _emit(on_line, f"# 工作目录：{PLOTPILOT_DIR}；日志：{_UVICORN_LOG}")

    child_env = dict(os.environ)
    child_env["DISABLE_AUTO_DAEMON"] = "1"
    # ★ 2026-10-17：**跳过它自带的"清理残留进程"**。那一段按关键字 `uvicorn` 匹配，
    #   会把同时在跑的 PenShot 一起杀掉（实测连杀三个）—— 生命周期由本桥管，
    #   启动时不需要它再"打扫"一遍。上游补丁见 `interfaces/daemon_manager.py`。
    # [EN] ★ 2026-10-17: **skip its built-in "orphan cleanup"** -- it matches by the
    # [EN] keyword `uvicorn` and therefore kills a co-running PenShot (three processes
    # [EN] in the measurement). Lifecycle belongs to this bridge; no extra sweep needed.
    # [EN] The upstream patch is in `interfaces/daemon_manager.py`.
    child_env["PLOTPILOT_SKIP_ORPHAN_CLEANUP"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        child_env.pop(k, None)                  # 本地回环别走代理

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(_UVICORN_LOG, "ab", buffering=0)
    except OSError as e:
        return False, f"开不了日志文件 {_UVICORN_LOG}：{e!r}"

    kw: dict = {"cwd": str(PLOTPILOT_DIR), "env": child_env,
                "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log}
    if os.name == "nt":
        # 与 penshot/mumu 同一套标志（坑都写在 penshot_bridge 那段注释里）：
        # DETACHED|NEW_GROUP|NO_WINDOW + BREAKAWAY_FROM_JOB，宿主作业不允许脱离时退一次。
        # [EN] Same flags as penshot/mumu (pitfalls documented in penshot_bridge):
        # [EN] DETACHED|NEW_GROUP|NO_WINDOW + BREAKAWAY_FROM_JOB, with a retry without breakaway.
        base_flags = 0x00000008 | 0x00000200 | 0x08000000
        kw["creationflags"] = base_flags | 0x01000000
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kw["startupinfo"] = si
        try:
            p = subprocess.Popen(argv, **kw)
        except OSError:
            kw["creationflags"] = base_flags
            try:
                p = subprocess.Popen(argv, **kw)
            except OSError as e:
                log.close()
                return False, f"起不了子进程：{e!r}"
    else:
        kw["start_new_session"] = True
        try:
            p = subprocess.Popen(argv, **kw)
        except OSError as e:
            log.close()
            return False, f"起不了子进程：{e!r}"
    log.close()

    ok, waited = _wait_health(timeout, _UVICORN_LOG, on_line)
    if ok:
        _emit(on_line, f"✔ 服务已就绪（{waited:.0f} 秒，pid={p.pid}）")
        return True, f"服务已就绪（{waited:.0f} 秒，pid={p.pid}）"
    tail = ""
    try:
        with open(_UVICORN_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 800))
            tail = f.read().decode("utf-8", "replace").strip().splitlines()[-3:]
    except OSError:
        pass
    _emit(on_line, f"✘ {timeout:.0f} 秒还没就绪（日志：{_UVICORN_LOG}）")
    return False, (f"{timeout:.0f} 秒还没就绪"
                   + (f"；日志尾巴：{'；'.join(tail)}" if tail else "")
                   + f"（完整日志 {_UVICORN_LOG}）")


def _pid_on_port(port: int) -> int | None:
    """谁在监听这个端口（Windows: netstat -ano；Unix: lsof）。找不到就 None。

    ★ 停服务用它兜底：PlotPilot 的 `/internal/shutdown` 是**尽力而为**，
      服务卡住时那个端点也回不来 —— 那时候只剩"按端口找 pid 再 taskkill"这一条路。
      没有它，用户点了「停止服务」会看到"发了请求但还在跑"，然后只能自己去任务管理器。
    [EN] Who is listening on this port (Windows: netstat -ano; Unix: lsof); None if unknown.
    [EN] Used as the stop fallback: `/internal/shutdown` is best-effort, and when the
    [EN] service is wedged that endpoint won't answer either -- the only remaining path is
    [EN] "find the pid by port, then taskkill". Without it, clicking Stop reports "request
    [EN] sent but still running" and the user has to open Task Manager.
    """
    import subprocess

    if os.name == "nt":
        try:
            r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15,
                               **_no_window())
        except Exception:                                  # noqa: BLE001
            return None
        for ln in (r.stdout or "").splitlines():
            parts = ln.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") \
                    and parts[3].upper() == "LISTENING" and parts[4].isdigit():
                return int(parts[4])
        return None
    try:
        r = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-s", "TCP:LISTEN"],
                           capture_output=True, text=True, timeout=15,
                           encoding="utf-8", errors="replace")
    except Exception:                                      # noqa: BLE001
        return None
    for ln in (r.stdout or "").splitlines():
        if ln.strip().isdigit():
            return int(ln.strip())
    return None


def _no_window() -> dict:
    """起子进程不冒窗口的那套参数（与 `start_service` 同源，抽出来复用）。"""
    import subprocess

    kw: dict = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kw["startupinfo"] = si
    return kw


def stop_service(on_line=None) -> tuple[bool, str]:
    """停掉 PlotPilot 服务（向 /internal/shutdown 发请求；不行就按端口 pid 强停）。

    `on_line`：逐行回调（界面弹窗用它显示**停止过程的全套输出**）。

        English:
    Stop the PlotPilot service (POST /internal/shutdown; fall back to taskkill by port pid).

    `on_line`: per-line callback (the UI dialog uses it to show the **full stop output**).
    """
    import subprocess

    st = service_status()
    if not st.ok:
        _emit(on_line, "○ 服务本来就不在跑")
        return True, "服务本来就不在跑"
    url = service_url() + "/internal/shutdown"
    _emit(on_line, f"$ POST {url}")
    sent = False
    try:
        req = urllib.request.Request(url, method="POST")
        with _NO_PROXY.open(req, timeout=3.0) as r:
            code = getattr(r, "status", 0)
            _emit(on_line, f"HTTP {code}")
            sent = 200 <= code < 300
    except Exception as e:                               # noqa: BLE001
        _emit(on_line, f"✘ 关闭请求没成功：{e!r}（改用按端口强停）")

    # 等它真的退（HTTP 关闭是异步生效的）
    for _ in range(10):
        if not service_status(timeout=1.0).ok:
            _emit(on_line, "✔ 已停止（关闭请求生效）")
            return True, "已发送关闭请求"
        time.sleep(0.5)

    # 兜底：按端口找 pid 再 taskkill —— 卡住的服务只有这一条路
    cfg = _config()
    try:
        port = int(_cfg_s(cfg, "PLOTPILOT_PORT", "8005"))
    except (TypeError, ValueError):
        port = 8005
    pid = _pid_on_port(port)
    if pid is None:
        _emit(on_line, f"✘ 服务还在跑，但端口 {port} 上找不到 pid —— 请手动结束进程")
        return False, "服务还在跑，且找不到它的 pid —— 请手动结束占用该端口的进程"
    cmd = (["taskkill", "/F", "/T", "/PID", str(pid)] if os.name == "nt"
           else ["kill", "-TERM", str(pid)])
    _emit(on_line, "$ " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace")
    except Exception as e:                               # noqa: BLE001
        _emit(on_line, f"✘ 强停失败：{e!r}")
        return False, f"停不掉 pid={pid}：{e!r}"
    for _ln in ((r.stdout or "") + (r.stderr or "")).splitlines():
        if _ln.strip():
            _emit(on_line, _ln.strip())
    for _ in range(10):
        if not service_status(timeout=1.0).ok:
            _emit(on_line, f"✔ 已停止（强停 pid={pid}）")
            return True, f"已停止（pid={pid}）"
        time.sleep(0.5)
    _emit(on_line, f"✘ 强停之后服务还在响应（pid={pid}）")
    return False, f"停不掉（pid={pid}）"


def stop_service_detached() -> bool:
    """**不等结果**地把服务停掉 —— 专供「关窗口那一刻」用。

    为什么不能直接调同步的 `stop_service()`：调用点是 `on_disconnect`，
    事件循环随时会停、`arm_exit_watchdog` **5 秒**后直接 `os._exit`，
    而这里要先 POST `/internal/shutdown`、再循环等它生效、必要时还要 taskkill
    —— 同步等根本等不到；开线程也没用，**`os._exit` 不等任何线程**，
    停一半就被带走。
    ⇒ 甩一个**独立的 python 进程**去跑同步版：它活过我们，于是"不等"
      不影响它把活干完。
    （「怎么甩」三家桥共用一份：`novelservices/_detach.py`。）

    返回 True = 子进程起来了（**不代表**服务已经停了）。

        English:
    Stop the service **without waiting** — for the moment the window closes.
    Why not just call the synchronous `stop_service()`: the caller is
    `on_disconnect`, the event loop may stop any time and `arm_exit_watchdog`
    does a bare `os._exit` after **5 s**, while this has to POST
    `/internal/shutdown`, then loop until it takes effect, then possibly
    taskkill — waiting synchronously can't finish; a thread doesn't help either,
    **`os._exit` waits for no thread** and it would be cut off half-way.
    => Throw out a **separate python process** to run the synchronous version:
    it outlives us, so "not waiting" doesn't stop it from finishing.
    ("How to throw" is one shared copy: `novelservices/_detach.py`.)
    Returns True = the child started (**not** that the service has stopped).
    """
    try:                                    # 包导入（主程序：`from novelservices import plotpilot_bridge`）
        from ._detach import run_detached   # [EN] package import (the app)
    except ImportError:                     # noqa: BLE001
        from _detach import run_detached    # 顶层导入（`service_ctl` 把本目录塞进 `sys.path` 后 import）
                                            # [EN] top-level import (`service_ctl` puts this dir on `sys.path`)
    import sys
    app = str(Path(__file__).resolve().parents[1])
    code = "from novelservices.plotpilot_bridge import stop_service as _s; _s()"
    return run_detached([sys.executable, "-c", code], cwd=app)


# ══════════════════════════════════════════════════════════════════
#  NWS 书 ↔ PlotPilot novel 的映射
# [EN] Mapping between NWS book ↔ PlotPilot novel
# ══════════════════════════════════════════════════════════════════
_NULL_MAP = PLOTPILOT_DIR / ".nws_novels.json"


def _map_file(novel_dir: Path | None) -> Path:
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
        pass


def forget_novel(novel_dir: Path | None, key: str = "") -> None:
    """忘掉映射（服务端把 novel 删了、或想重新建一个时用）。

    English:
    Forget the mapping (used when the server deleted the novel, or to rebuild).
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


def _slug(project_key: str) -> str:
    """把书名转成安全的 novel_id（PlotPilot 的 novel_id 由客户端指定）。

    English:
    Turn a book name into a safe novel_id (PlotPilot's novel_id is client-specified).
    """
    s = "".join(ch if (ch.isalnum() or ch in "-_") else "_"
                for ch in (project_key or "nov")).strip("_")
    return s or "nov"


def ensure_novel(task: ScreenTask) -> tuple[str, str]:
    """找到（或建好）这本书在 PlotPilot 里的 novel。返回 `(novel_id, 错误)`。

    English:
    Find (or create) this book's novel in PlotPilot. Returns `(novel_id, error)`.
    """
    key = task.project_key or "未命名"
    cache = _load_map(task.novel_dir, key)
    nid = str(cache.get("novel_id") or "").strip()
    if nid:
        try:
            with _NO_PROXY.open(service_url() + f"{API}/novels/{nid}",
                                 timeout=5.0) as r:
                if 200 <= getattr(r, "status", 0) < 300:
                    return nid, ""
        except Exception:                                    # noqa: BLE001
            forget_novel(task.novel_dir, key)                # novel 没了 → 重建

    nid = _slug(key)
    body = {
        "novel_id": nid,
        "title": key,
        "author": "NWS",
        "premise": (task.premise or "")[:2000],
        "genre": task.genre or "",
        "target_chapters": 0,
        "target_words_per_chapter": int(task.target_words or 2500),
    }
    try:
        req = urllib.request.Request(
            service_url() + f"{API}/novels/",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with _NO_PROXY.open(req, timeout=20.0) as r:
            if not (200 <= getattr(r, "status", 0) < 300):
                return "", f"建 novel 失败：HTTP {getattr(r, 'status', 0)}"
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:                                     # noqa: BLE001
        return "", f"建 novel 失败：{e!r}"
    nid = str(data.get("id") or nid)
    cache["novel_id"] = nid
    cache["title"] = key
    cache["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_map(task.novel_dir, key, cache)
    return nid, ""


# ══════════════════════════════════════════════════════════════════
#  SSE 读取 + 主入口
# [EN] SSE reader + main entry
# ══════════════════════════════════════════════════════════════════
def _read_sse(base: str, path: str, body: dict[str, Any],
              deadline: float) -> tuple[dict[str, Any] | None, str]:
    """读 SSE 流，直到 `type=="done"` / `type=="error"`，或超时。

    返回 `(done_event_or_None, error_reason)`。

    English:
    Read the SSE stream until done/error or timeout. Returns `(done_event_or_None, error)`.
    """
    try:
        req = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "text/event-stream"}, method="POST")
        resp = _NO_PROXY.open(req, timeout=30.0)
    except Exception as e:                                     # noqa: BLE001
        return None, f"发起生成请求失败：{e!r}"

    buf = ""
    try:
        for raw in resp:
            if time.time() > deadline:
                return None, "生成超过上限时间（疑似卡住）"
            line = raw.decode("utf-8", "replace")
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if not payload:
                continue
            try:
                evt = json.loads(payload)
            except ValueError:
                continue
            etype = evt.get("type")
            if etype == "error":
                return None, str(evt.get("message") or evt.get("detail") or "生成报错")
            if etype == "done":
                return evt, ""
            # 其余事件（phase / chunk / progress）忽略，等待 done
    except urllib.error.HTTPError as e:
        return None, f"生成请求返回 HTTP {e.code}"
    except Exception as e:                                     # noqa: BLE001
        return None, f"读生成流失败：{e!r}"
    return None, "流结束但没收到 done 事件"


def generate_chapter(task: ScreenTask) -> BridgeResult:
    """把一件事交给 PlotPilot：**为这一章设计结构 / 产出章节方案，拿回正文**。

    流程（每一步只要不对就**立刻返回失败**，不硬撑）：
        ① 服务在不在 → 不在就请调用方回退
        ② 找到/建好 novel
        ③ POST generate-chapter-stream（SSE）→ 等 done 事件
        ④ 读回 `content`（完整正文），空章判失败

    返回的 `BridgeResult.ok=False` 全部是**可回退**的失败 —— 调用方应当
    退回内部编剧逻辑，而不是把这一天的戏弄丢。

    English:
    Hand one task to PlotPilot: design the chapter structure and return the body.
    All `BridgeResult.ok=False` are fallback-able failures.
    """
    t0 = time.time()

    def _fail(msg: str) -> BridgeResult:
        return BridgeResult(False, reason=msg, elapsed=time.time() - t0)

    if not task.outline.strip():
        return _fail("本章要讲什么(outline)是空的 —— 没有它 PlotPilot 不知道写啥")

    st = service_status()
    if not st.ok:
        return _fail(f"PlotPilot 没在跑：{st.reason}")

    nid, err = ensure_novel(task)
    if err:
        return _fail(err)

    # 章号：没指定就取 novel 现有章节数 +1
    # [EN] Chapter number: auto = existing chapter count + 1
    number = int(task.chapter_number or 0)
    if number <= 0:
        try:
            with _NO_PROXY.open(service_url() + f"{API}/novels/{nid}",
                                 timeout=5.0) as r:
                if 200 <= getattr(r, "status", 0) < 300:
                    data = json.loads(r.read().decode("utf-8"))
                    number = len(data.get("chapters") or []) + 1
        except Exception:                                    # noqa: BLE001
            number = 1
    if number <= 0:
        number = 1

    body: dict[str, Any] = {
        "chapter_number": number,
        "outline": task.outline.strip(),
    }
    if task.model:
        body["profile_id"] = task.model          # 覆盖 LLM 档案（若服务端支持）

    deadline = time.time() + float(task.timeout or 900.0)
    done, msg = _read_sse(service_url(),
                          f"{API}/novels/{nid}/generate-chapter-stream",
                          body, deadline)
    if msg:
        return _fail(msg)
    if done is None:
        return _fail("没拿到生成结果")

    text = str((done or {}).get("content") or "").strip()
    if len(text) < 50:
        return _fail(f"拿回来的正文只有 {len(text)} 字（疑似空章）")

    return BridgeResult(True, text=text, chapter_number=number,
                        elapsed=time.time() - t0,
                        raw={"novel_id": nid, "chars": len(text)})


def generate_outline(task: ScreenTask) -> BridgeResult:
    """**编剧入口**（剧作者用）：调用 PlotPilot 产出本章方案，拿回正文草稿。

    与 `generate_chapter` 同一条链路 —— PlotPilot 的产出本身已是结构化叙事
    （含规划与正文），编剧据此提炼当天的细纲。放回失败一律可回退到内部编剧逻辑。

    English:
    **Screenwriter entry**: call PlotPilot to produce the chapter plan and return the draft.
    Same pipeline as generate_chapter; all failures are fallback-able.
    """
    return generate_chapter(task)


def describe() -> str:
    st = service_status()
    return (f"PLOTPILOT_DIR = {PLOTPILOT_DIR}\n"
            f"服务地址      = {service_url()}\n"
            f"服务状态      = {'在跑' if st.ok else '不在跑'} {st.reason}\n"
            f"上游          = {UPSTREAM}")


if __name__ == "__main__":
    print(describe())
