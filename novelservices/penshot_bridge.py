# -*- coding: utf-8 -*-
"""NWS → PenShot 的**接入层**（桥）。

给谁用的
--------
给主程序里的 **导演（director）** 用。目的是：
**把"这一场怎么拍、镜头怎么拆、每段画面用什么提示词"这件事交给 PenShot 去干**，
而不是让导演 Agent 自己拼提示词问模型。PenShot 是"剧本分镜智能体"
（上游 `neopen/story-shot-agent`，MIT），把一段剧本拆成场景 → 镜头 →
视频生成提示词（fragment）—— 正是导演的活。

★ 为什么从 CutAI 换成 PenShot（2026-10-16）
----------------------------------------
CutAI 这份 vendored 版本**只接 Groq 云端**：上游把本地 Ollama 通道整体删了
（PSU 安全考虑），`.env` 里写 `LLM_PROVIDER=local` 也只在生成时炸
RuntimeError。也就是说，天机「AI模型配置」里登记的模型——除了 Groq——
**一个都喂不进去**，这与"外部服务要用天机配置的 LLM"直接冲突。
PenShot 则是 OpenAI 兼容通道（openai / deepseek / dashscope / ollama /
以及一切 OpenAI 兼容端点，见 vendored 副本 `client_config.py` 的补丁），
MIT 许可证，单进程（workers=1）即可跑，产出 fragment 提示词与旧的
分镜契约逐项对口。

它不做什么
----------
**不改 PenShot 的源码语义。** 一切通过它自己的 REST 接口走
（`python -m uvicorn penshot.app:app`，默认 `http://127.0.0.1:8000`）。
vendored 副本里只有**三处最小补丁**（全部双语注释标明），都是把上游
"本来就可选/本来就想支持"的东西落到实处：
  1. `utils/redis_utils` 的消费方：Redis 连不上时不再让整个包 import 就炸
     （上游 `ShortTermMemory` 自带"连不上就用内存/文件"的降级，只是默认值
     在类定义时真连了一次 Redis）。
  2. `task_repository`：`RedisClient()` 挪进 try（同上，构造就 ping）。
  3. `client_config.detect_ai_provider_by_url`：未知主机兜底从 Ollama 改为
     OpenAI 兼容协议（Ollama 客户端说 Ollama 原生协议，对 OpenAI 兼容端点
     必然 404；端口 11434 / URL 含 ollama 的仍然走 Ollama）。
所以上游怎么升级都不影响这里 —— 顶多是接口不兼容，那也只会**降级**，不会崩主程序。

三条设计纪律（与 mumu_bridge / plotpilot_bridge 一致）
-----------------------------------------------
1. **绝不成为单点故障。** 服务没起、超时、生成失败 —— 一律返回
   `BridgeResult(ok=False, reason=...)`，**由调用方回退到原来的内部导演逻辑**。
2. **纯标准库。** 主程序跑在 Python 3.13，PenShot 的 venv 是另一套依赖。
   两边**环境不同**，所以这里只用 stdlib，通过 HTTP 说话。
3. **回环请求必须绕代理。** 本机设了 HTTP 代理，`127.0.0.1` 的请求走代理
   必然失败 —— 见模块头第 3 条（与另两座桥相同）。

English:
**Integration layer** (bridge) from NWS → PenShot.
Who it's for
--------
For the **director** Agent in the main program. The goal is to hand off
"how to shoot this scene, how to split the shots, what prompt to use for each
clip" to PenShot (a script-to-storyboard agent, upstream
`neopen/story-shot-agent`, MIT).
★ Why CutAI was replaced by PenShot (2026-10-16): that vendored CutAI is
Groq-cloud-only (upstream deleted the local Ollama channel), so almost no
model registered in NWS's "AI Model Config" could be fed to it. PenShot speaks
the OpenAI-compatible protocol, is MIT-licensed, and runs single-process.
Three design disciplines (same as the other bridges)
-----------------------------------------------
1. Never become a single point of failure. 2. Pure standard library. 3. Loopback bypasses proxy.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "PENSHOT_DIR", "PENSHOT_BASE_URL", "PENSHOT_ENV",
    "BridgeStatus", "BridgeResult", "DirectorTask",
    "service_status", "service_url", "read_service_env", "save_service_env",
    "model_env_for", "write_llm_env",
    "start_service", "stop_service", "generate_storyboard", "describe",
]

# ── 路径（全部相对本文件，不写死盘符）──────────────────────────────
# [EN] ── Paths (all relative to this file, no hardcoded drive letters) ──
HERE = Path(__file__).resolve().parent
PENSHOT_DIR = HERE / "PenShot"

#: PenShot 自己的 `.env`（`penshot.config` 的 DotEnvLoader 读它；**cwd 优先**，
#: 所以起服务时把 cwd 钉在 `PENSHOT_DIR`，它就会读这个文件）。
# [EN] : PenShot's own `.env` (read by DotEnvLoader in `penshot.config`; **cwd first**,
# [EN] so starting the service with cwd pinned to `PENSHOT_DIR` makes it read this file).
PENSHOT_ENV = PENSHOT_DIR / ".env"

#: 上游项目地址（界面上要标出来 —— 这套服务不是本项目写的）
# [EN] : Upstream project address (must be shown in the UI)
UPSTREAM = "https://github.com/neopen/story-shot-agent"

#: 默认连接地址（真值从本程序 Config 的 PENSHOT_HOST/PENSHOT_PORT 读）
# [EN] : Default connection address (real value from Config PENSHOT_HOST/PENSHOT_PORT)
PENSHOT_BASE_URL = "http://127.0.0.1:8000"

#: 服务自己的日志 / pid 文件目录
# [EN] : The service's own log / pid file directory
LOG_DIR = PENSHOT_DIR / "logs"
PID_FILE = LOG_DIR / "penshot.pid"
UVICORN_LOG = LOG_DIR / "uvicorn.out"


# ══════════════════════════════════════════════════════════════════
#  结果类型
# [EN] Result types
# ══════════════════════════════════════════════════════════════════
@dataclass
class BridgeStatus:
    """服务状态。`reason` 是**给人看的一句话**。

    English:
    Service status. `reason` is a one-liner for humans.
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
    elapsed: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DirectorTask:
    """交给 PenShot 的一件事：**把这一段场景拆成分镜**。

    给它"这一场的剧本/场景原文"，它返回场景 → 镜头 → 每段的视频生成提示词
    （fragment：正向/负向提示词、时长、风格、配乐提示词），导演据此安排
    当天的拍摄方案。

    ★ `model` 字段 PenShot **不使用**（它的同步接口没有按请求切模型的参数）——
      模型由 PenShot 自己的 `.env` 决定（`model_env_for`/`write_llm_env` 写）。
      保留这个字段只为**契约不变**（crew 侧零感知）。

    English:
    One thing handed to PenShot: **break this scene into a storyboard**.
    ★ The `model` field is **unused** by PenShot (its sync endpoint has no
      per-request model switch) -- the model comes from PenShot's own `.env`.
      It is kept only so the contract stays unchanged (crew side unaware).
    """

    project_key: str                     # NWS 这边的书名（用于映射/缓存）
    novel_dir: Path | None = None        # NWS 项目目录（可为 None）
    title: str = ""                      # 这一场的标题
    script_text: str = ""                # 场景/剧本原文（核心输入）
    genre: str = ""                      # 类型提示（drama/noir/...）
    num_scenes: int = 5                  # 场景数（提示用，PenShot 自行决定拆多少）
    model: str = ""                      # 空 = 用服务端默认（见类注释：PenShot 不用它）
    timeout: float = 900.0               # 等生成完成的上限（秒）


# ══════════════════════════════════════════════════════════════════
#  连接地址 / 配置读写
# [EN] Connection / config read-write
# ══════════════════════════════════════════════════════════════════
def _config() -> Any:
    """懒加载本程序 Config **实例**（本模块要能独立跑，不强制依赖主程序）。

    ★★★ 2026-10-23 **修**：原来返回 `Config` **类本身**，于是 `service_url()` 永远是
      127.0.0.1:8000、`start/stop_service()` 也只认这个默认端口 ——
      **用户在配置里改端口完全不生效**（详见 `plotpilot_bridge._config()` 的说明）。
      用户端口恰好都是默认值，所以一直没有症状。
    [EN] ★★★ 2026-10-23 **fixed**: this used to return the `Config` **class itself**, so
    `service_url()` was always 127.0.0.1:8000 and start/stop only knew that default port --
    **changing the port in the settings had no effect** (see
    `plotpilot_bridge._config()` for the full story). The user's ports happen to be the
    defaults, so there was no symptom.
    """
    try:
        from config import CFG
        return CFG
    except Exception:                                    # noqa: BLE001
        return None


def _cfg_s(cfg: Any, key: str, default: str = '') -> str:
    """从 Config **实例**读一个字符串配置（读不到就是 `default`）。

    ★★★ 2026-10-23：**不能**用 `getattr(cfg, key, default)` —— `Config`
      没有 `__getattr__`（类与实例都没有），`getattr` 永远拿到 `default`，
      于是改端口不生效、停服务停不掉、天机里读不到真实值。
      读配置的唯一入口是 `cfg.s()` / `cfg.i()` / `cfg.b()`。
      与 `plotpilot_bridge._cfg_s` 是同一件事（两座桥各自要能独立跑）。
    [EN] ★★★ 2026-10-23: **never** `getattr(cfg, key, default)` -- `Config` has no
    `__getattr__` (neither class nor instance), so `getattr` always yields the default:
    a changed port had no effect, the service could not be stopped, Tianji read no real
    values. The only entry points are `cfg.s()` / `cfg.i()` / `cfg.b()`. Same helper as
    `plotpilot_bridge._cfg_s` (each bridge must run standalone).
    """
    try:
        v = cfg.s(str(key))
        return str(v) if str(v).strip() else default
    except Exception:                                    # noqa: BLE001
        return default


def service_url() -> str:
    cfg = _config()
    host = _cfg_s(cfg, "PENSHOT_HOST", "127.0.0.1")
    try:
        port = int(_cfg_s(cfg, "PENSHOT_PORT", "8000"))
    except (TypeError, ValueError):
        port = 8000
    return f"http://{host}:{port}"


def read_service_env() -> dict[str, str]:
    cfg = _config()
    if cfg is None:
        return {}
    out: dict[str, str] = {}
    for k in ("PENSHOT_HOST", "PENSHOT_PORT", "PENSHOT_MODEL", "PENSHOT_ENABLED"):
        v = _cfg_s(cfg, k, "")
        if v:
            out[k] = v
    return out


def save_service_env(kv: dict[str, Any]) -> str | None:
    """把参数写进 **PenShot 自己的 `.env`**（返回 None = 成功）。

    ★ 与另两座桥的差异（2026-10-16 修）：`plotpilot_bridge` /
      `cutai_bridge` 的这个函数写的是**本程序 Config**（setattr + save），
      于是 crew 里"把 Agents 页点名的模型推给服务"那段代码推了个空转 ——
      模型从没进过服务的 .env。PenShot 这座按**名字的语义**实现：
      写服务自己的 `.env`（与 `mumu_bridge` 一致），键就是
      `PENSHOT_*`（pydantic-settings 的 `env_prefix`），例如
      `{"PENSHOT_LLM__DEFAULT__MODEL_NAME": "..."}`。

    English:
    Write the parameters into **PenShot's own `.env`** (None = success).
    ★ Difference from the other two bridges (fixed 2026-10-16): plotpilot/cutai's
      version wrote the **NWS Config**, so the crew's "push the named model to the
      service" code was a no-op. This bridge honors the name's semantics: it writes
      the service's own `.env` (like mumu_bridge), keys being `PENSHOT_*`.
    """
    return write_llm_env(kv)


# ══════════════════════════════════════════════════════════════════
#  模型选择 → 服务自己的 .env（天机「外部创作服务」页的「来自 AI模型配置」下拉）
# [EN] Model pick → the service's own .env (the "from AI Model Config" dropdown)
# ══════════════════════════════════════════════════════════════════
def _sink_path() -> Path | None:
    """回归/验证期间的**写盘重定向**（沿用 mumu_bridge 那套保险丝）。

    ★ 为什么这里也要守：天机的「外部创作服务」页会写**另一个文件**
      （PenShot 的 `.env`）。验证脚本点一下"保存"，就会把测试值
      写进用户真实的服务配置里。所以父进程给了 `NWS_ENV_SINK`
      （或进程内设了 `Config.redirect_save`）时，这里**不写真实文件**，
      写进旁边一个 `*.penshot-sink` 里。

    English:
    **Disk-write redirection** during regression/verification (same fuse as mumu_bridge).
    """
    p = (os.environ.get("NWS_ENV_SINK") or "").strip()
    if p:
        return Path(p).expanduser().with_suffix(".penshot")
    try:
        from config import Config                          # 懒加载：本模块要能独立跑
        # [EN] Lazy loading: this module must be able to run standalone
        if Config.redirect_save is not None:
            return Path(Config.redirect_save).with_suffix(".penshot")
    except Exception:                                      # noqa: BLE001
        pass
    return None


def _is_ollama_url(base: str) -> bool:
    """像不像一个**原生 Ollama**地址（端口 11434，或 URL 里带 ollama）。

    判据与 vendored 副本里 `detect_ai_provider_by_url` 的第 5 步**逐字对齐** ——
    两边不一致就会"桥以为能写、服务以为走 OpenAI 协议"。

    English:
    Does this look like a **native Ollama** address (port 11434, or 'ollama' in
    the URL). Kept word-for-word aligned with step 5 of `detect_ai_provider_by_url`
    in the vendored copy -- a mismatch means "the bridge thinks it can write while
    the service speaks the OpenAI protocol".
    """
    low = (base or "").lower()
    return ":11434" in low or "ollama" in low


def model_env_for(entry: Any) -> tuple[dict[str, str], str]:
    """把 NWS「AI模型配置」里的一条模型，映射成 PenShot `.env` 认的键。

    返回 `(键值表, 警告)`；**警告非空 = 不兼容，调用方不许写**，应把警告
    原样显示给用户。

    PenShot 是 **OpenAI 兼容**服务（langchain-openai），所以映射很直接：
        `PENSHOT_LLM__DEFAULT__BASE_URL`   = 条目的 base_url（登记时已到 /v1 层）
        `PENSHOT_LLM__DEFAULT__API_KEY`    = 条目的 api_key
        `PENSHOT_LLM__DEFAULT__MODEL_NAME` = 条目的 model

    ★ 只从条目取 LLM 三件套 + **同一套端点的 embedding 三件套**，不猜模型名：
        `PENSHOT_LLM__DEFAULT__BASE_URL/API_KEY/MODEL_NAME`
        `PENSHOT_EMBED__DEFAULT__BASE_URL/API_KEY/MODEL_NAME`
      embedding 用**条目自己的端点与模型名**往下打 —— 大多数厂商这里会 404，
      PenShot 会自动降级成"规则引擎做记忆"（只是长期检索质量降级，**不阻断
      分镜生成**）。为什么要写它而不是留空：不写的话 embedding 默认指向
      `api.openai.com`，在天机用户的网络环境下每次检索都干等 ~90 秒超时
      （实测三次 ≈ 4 分钟，全耗在生成之前）—— 写成一个**可达**的端点，
      失败也是**快速失败**。要让长期记忆真正生效，请手动在 `PenShot/.env` 里
      把 `PENSHOT_EMBED__DEFAULT__MODEL_NAME` 改成真正的 embedding 模型名。
      另外把 embedding 超时压到 15 秒：无头服务里没有"慢慢等"的意义。

    ★ 原生 Ollama 地址（端口 11434 / URL 含 ollama）走的是 Ollama 协议，
      **不能带 `/v1` 后缀**（ChatOllama 会拼 `/api/chat`）—— 这里替它去掉；
      也不要 key（Ollama 不认 key，写个空串即可）。

    English:
    Map one NWS model-registry entry to the keys PenShot's `.env` understands.
    PenShot is **OpenAI-compatible**, so the mapping is direct: the LLM triple
    plus the same endpoint for embeddings. Embedding is written so failures are
    *fast* (an unreachable default endpoint would burn ~90s per search); PenShot
    degrades to rule-engine memory when it 404s. Native Ollama URLs get their
    trailing `/v1` stripped (Ollama protocol, not OpenAI) and no key.
    """
    model = str(getattr(entry, "model", "") or "").strip()
    base = str(getattr(entry, "base_url", "") or "").strip()
    key = str(getattr(entry, "api_key", "") or "").strip()
    if not model:
        return {}, "这个模型没填模型名（model 是空的），没法写"
    if not base:
        return {}, "这个模型没填服务地址（base_url 是空的），没法写"

    if _is_ollama_url(base):
        # Ollama 原生协议：去掉 /v1 后缀，不需要 key
        # [EN] Ollama native protocol: strip the /v1 suffix, no key needed
        base = re.sub(r"/v1/?$", "", base).rstrip("/") or base
        return {
            "PENSHOT_LLM__DEFAULT__BASE_URL": base,
            "PENSHOT_LLM__DEFAULT__API_KEY": key,
            "PENSHOT_LLM__DEFAULT__MODEL_NAME": model,
            "PENSHOT_EMBED__DEFAULT__BASE_URL": base,
            "PENSHOT_EMBED__DEFAULT__API_KEY": key,
            "PENSHOT_EMBED__DEFAULT__MODEL_NAME": model,
            "PENSHOT_EMBED__DEFAULT__TIMEOUT": "15",
        }, ""

    if not key:
        # 本地回环服务（vLLM / Ollama 的 OpenAI 兼容层…）一般不校验 key，
        # 写个占位符让客户端能构造起来；云端地址没有 key 是真写不了。
        # [EN] Loopback services (vLLM / Ollama's OpenAI-compatible layer ...) usually
        # [EN] don't check the key -- write a placeholder so the client can be built;
        # [EN] a cloud address without a key genuinely cannot be written.
        host = (urllib.parse.urlsplit(base).netloc or base).lower()
        hostname = host.rsplit("@", 1)[-1].split(":")[0]
        if hostname in ("127.0.0.1", "localhost", "0.0.0.0", "::1", "[::1]"):
            key = "EMPTY"
        else:
            return {}, ("这个模型没填 API Key。PenShot 走 OpenAI 兼容协议，"
                        "云端地址没有 key 会在初始化时直接报错。"
                        "请回「AI模型配置」给这条模型补上密钥再选。")
    return {
        "PENSHOT_LLM__DEFAULT__BASE_URL": base,
        "PENSHOT_LLM__DEFAULT__API_KEY": key,
        "PENSHOT_LLM__DEFAULT__MODEL_NAME": model,
        "PENSHOT_EMBED__DEFAULT__BASE_URL": base,
        "PENSHOT_EMBED__DEFAULT__API_KEY": key,
        "PENSHOT_EMBED__DEFAULT__MODEL_NAME": model,
        "PENSHOT_EMBED__DEFAULT__TIMEOUT": "15",
    }, ""


def write_llm_env(kv: dict[str, Any]) -> str | None:
    """把模型键写进 PenShot 自己的 `.env`（起服务时 cwd 钉在本目录，它才会读）。

    与 `mumu_bridge.write_llm_env` 同一套范式：
      · 逐行替换已知键，**保留注释与未知键**；
      · 表里没有的键追加到末尾的「由天机写入」小节；
      · 写之前留一份 `.env.bak`；
      · `NWS_ENV_SINK` / `Config.redirect_save` 命中时**不写真文件**。
    `.env` 不存在时从仓库根的 `.env.example` 播种（例文件也没有就新建）。
    返回 `None` = 成功，否则是给人看的一句话。

    English:
    Write the model keys into PenShot's own `.env`. Same pattern as mumu_bridge.
    """
    if PENSHOT_ENV.exists():
        try:
            base_text = PENSHOT_ENV.read_text(encoding="utf-8")
        except OSError as e:
            return f"读不了 {PENSHOT_ENV.name}：{e!r}"
    else:
        base_text = ""
        for example in (PENSHOT_DIR / ".env.example",):
            try:
                if example.exists():
                    base_text = example.read_text(encoding="utf-8")
                    break
            except OSError:
                continue

    sink = _sink_path()
    target = sink if sink else PENSHOT_ENV

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
        if not sink and PENSHOT_ENV.exists():
            PENSHOT_ENV.with_suffix(".env.bak").write_bytes(PENSHOT_ENV.read_bytes())
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError as e:
        return f"写不了 {target.name}：{e!r}"
    return None


# ══════════════════════════════════════════════════════════════════
#  服务探活 / 起停
# [EN] Service liveness probe / start-stop
# ══════════════════════════════════════════════════════════════════
#: 只连本机 —— **必须显式禁用代理**，理由见模块头第 3 条。
# [EN] : Connect only to localhost -- **proxy must be explicitly disabled**, see reason in point 3 of
# [EN] the module header.
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _no_window_kw() -> dict:
    """Windows：本座桥自己起的子进程（tasklist / netstat / taskkill）**不许冒控制台**。

    ★ 为什么 stop 这条路上必须补（2026-10-17）：现在 `stop_service()` 会被
      `novelservices/service_ctl.py`（Go 启动器经它停服务）在**pythonw** 下调 ——
      那条路顶层没有控制台，而"父进程没有控制台"**不会**自动传给子进程：
      Windows 会给 `tasklist` / `netstat` / `taskkill` 各新分配一个控制台
      **并显示出来**（`developers/_probe_console_windows.py` 实测：
      父无控制台 + 子无标志 ⇒ 多出可见黑窗）。
      这三条命令都是短命的，窗口一闪而过更难被发现，但"卸载时闪三下黑窗"
      正是本轮要消灭的东西。判据 B4/B5 会扫这里。
      （从终端里手动跑本模块时这个标志无副作用：输出照样走管道。）

    English:
    Windows: this bridge's own children (tasklist / netstat / taskkill) **must not
    spawn a console**.
    ★ Why the stop path needs this (2026-10-17): `stop_service()` is now called
      from `novelservices/service_ctl.py` (the Go launcher stopping services
      through it) under **pythonw** -- that top level has no console, and
      "the parent has no console" is **not** inherited by children: Windows
      allocates a **new, visible** console for each of tasklist / netstat /
      taskkill (measured by `developers/_probe_console_windows.py`:
      parent without console + child without flag ⇒ extra visible black windows).
      All three commands are short-lived, so the windows flash by even harder to
      notice, but "three black flashes during uninstall" is exactly what this
      round eliminates. Assertions B4/B5 scan here.
      (No side effects when running this module manually from a terminal: output
      still goes through the pipes.)
    """
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return {"creationflags": 0x08000000, "startupinfo": si}


def service_status(timeout: float = 1.5) -> BridgeStatus:
    """服务在不在？**永不抛异常**（调用方常在界面线程里问它）。

    探 `/api/v1/health`（rest 路由那个，会真的碰一次任务工厂）——
    比根 `/health` 多一分"服务是好的"的把握。

    English:
    Is the service up? **Never throws an exception** (callers often ask it from the UI thread).
    """
    if not PENSHOT_DIR.exists():
        return BridgeStatus(False, "没找到 PenShot（novelservices 目录被删掉了？）")
    base = service_url()
    try:
        with _NO_PROXY.open(base + "/api/v1/health", timeout=timeout) as r:
            ok = 200 <= getattr(r, "status", 0) < 300
        return BridgeStatus(ok, "" if ok else f"/api/v1/health 返回 {r.status}", base)
    except urllib.error.HTTPError as e:
        # 走到这儿说明**真的连上了服务器**，只是它返回了错误码
        # [EN] Reaching here means **actually connected to the server**, it just returned an error code
        return BridgeStatus(False, f"/api/v1/health 返回 HTTP {e.code}", base)
    except Exception as e:                                   # noqa: BLE001
        return BridgeStatus(False, f"连不上 {base}（{type(e).__name__}）", base)


def _venv_python() -> Path | None:
    """venv 的解释器 —— **Windows 上优先 `pythonw.exe`**。

    ★ 2026-10-10 的实测结论（详见 `mumu_bridge._venv_python` 的同款注释）：
      venv 的 `Scripts/python.exe` 是 `venvlauncher.exe`，它会再 exec 一次真
      解释器且**不把 CREATE_NO_WINDOW 传下去** ⇒ 父进程没控制台时，Windows
      给子进程**新分配一个控制台**（用户看到关不掉的黑窗）。
      换 `pythonw.exe` 后代里不再有 `conhost`。

    English:
    The venv's interpreter -- **on Windows prefer `pythonw.exe`**
    (see the same note in `mumu_bridge._venv_python`).
    """
    for rel in (("Scripts/pythonw.exe", "Scripts/python.exe", "bin/python")
                if os.name == "nt" else ("bin/python",)):
        p = PENSHOT_DIR / ".venv" / rel
        if p.exists():
            return p
    return None


def _port_busy(port: int) -> bool:
    """端口有没有被占（不管是不是我们的服务）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:                                        # noqa: BLE001
        return None


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                               capture_output=True, text=True, timeout=10,
                               encoding="utf-8", errors="replace", **_no_window_kw())
            return f'"{pid}"' in (r.stdout or "")
        except Exception:                                    # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:                                        # noqa: BLE001
        return False


def _pid_on_port(port: int) -> int | None:
    """从端口反查 pid（pid 文件**可能过期或记错**，这是兜底）。"""
    if os.name == "nt":
        try:
            r = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                               text=True, timeout=15, encoding="utf-8",
                               errors="replace", **_no_window_kw())
        except Exception:                                    # noqa: BLE001
            return None
        for ln in (r.stdout or "").splitlines():
            parts = ln.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") \
                    and parts[3].upper() == "LISTENING":
                try:
                    return int(parts[4])
                except ValueError:
                    continue
        return None
    for cmd in (["lsof", "-ti", f"tcp:{port}", "-s", "TCP:LISTEN"],
                ["ss", "-lptn", f"sport = :{port}"]):
        import shutil
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                               encoding="utf-8", errors="replace")
        except Exception:                                    # noqa: BLE001
            continue
        for line in (r.stdout or "").splitlines():
            for tok in line.replace(",", " ").split():
                if tok.startswith("pid="):
                    try:
                        return int(tok[4:])
                    except ValueError:
                        pass
            if cmd[0] == "lsof" and line.strip().isdigit():
                return int(line.strip())
    return None


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
    """把日志文件里 `pos` 之后的新内容**逐行**发出去，返回新位置。

    ★ 为什么要 tail 日志而不是读子进程的 PIPE：PenShot 是用 `Popen(stdout=日志)` 起的
      （detach 后父进程不能持有管道，否则管道一关子进程就收到写错误），
      所以"实时输出"只能从它已经在写的那个文件里取。
    [EN] Why tail the log instead of reading the child's PIPE: PenShot is started with
    [EN] `Popen(stdout=<log file>)` (a detached child must not hold a pipe, or it gets a
    [EN] write error once the parent goes away), so live output can only come from the
    [EN] file it is already writing.
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
    """轮询 `/api/v1/health` 直到通过或超时。返回 (就绪?, 已等秒数)。

    给了 `log_path` 就**边等边**把日志新行发出去（界面用它显示实时输出）。
        English:
    Poll `/api/v1/health` until it passes or times out. Returns (ready?, seconds waited).
    With `log_path` given, new log lines are emitted **while waiting** (the UI shows them live).
    """
    t0 = time.time()
    pos = 0
    if log_path is not None:
        try:
            pos = log_path.stat().st_size
        except OSError:
            pos = 0
    while time.time() - t0 < timeout:
        if service_status().ok:
            pos = _tail_into(log_path, pos, on_line)
            return True, time.time() - t0
        pos = _tail_into(log_path, pos, on_line)
        time.sleep(1.0)
    _tail_into(log_path, pos, on_line)
    return False, time.time() - t0


def start_service(timeout: float = 600.0, on_line=None) -> tuple[bool, str]:
    """后台拉起 PenShot 服务（**detached**，uvicorn 单进程）。

    ★ 为什么不照 `main.py` 起：它会 `run_command("python --version")`（依赖
      PATH 里有 python），并且依赖不满足时**当场 `pip install -e .[full]`** ——
      在用户机器上默默联网装包是不可接受的。我们直接起 uvicorn，等价于
      `main.py` 里 `workers==1 and not reload` 那一支（`uvicorn.Config(app)`）。

    ★ 幂等：已经在跑就直接成功。

    English:
    Launch the PenShot service detached (uvicorn, single process). **Slow**,
    don't call it synchronously on the UI thread. Idempotent.
    """
    if service_status().ok:
        _emit(on_line, "● 服务本来就在跑（幂等：不再起第二个）")
        return True, "服务本来就在跑"

    py = _venv_python()
    if py is None:
        _emit(on_line, "✘ PenShot 的 venv 还没建好（先装依赖）")
        return False, "PenShot 的 venv 还没建好（先装依赖）"

    cfg = _config()
    host = _cfg_s(cfg, "PENSHOT_HOST", "127.0.0.1")
    try:
        port = int(_cfg_s(cfg, "PENSHOT_PORT", "8000"))
    except (TypeError, ValueError):
        port = 8000

    argv = [str(py), "-m", "uvicorn", "penshot.app:app",
            "--host", str(host), "--port", str(port),
            "--workers", "1", "--log-level", "info"]
    # 界面弹窗里先看到"它到底跑的是什么命令"（用户 2026-10-17 明确要这个）
    # [EN] The dialog shows "what command is actually being run" first (user's request, 2026-10-17)
    _emit(on_line, "$ " + " ".join(argv))
    _emit(on_line, f"# 工作目录：{PENSHOT_DIR}；日志：{UVICORN_LOG}")

    child_env = dict(os.environ)
    child_env["PYTHONIOENCODING"] = "utf-8"     # 日志文件统一 UTF-8，别混 GBK
    child_env["PYTHONUTF8"] = "1"
    child_env["PROJECT_ROOT"] = str(PENSHOT_DIR)  # 数据目录钉死在 PenShot/data
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        child_env.pop(k, None)                  # 本地回环别走代理

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(UVICORN_LOG, "ab", buffering=0)
    except OSError as e:
        return False, f"开不了日志文件 {UVICORN_LOG}：{e!r}"

    kw: dict = {"cwd": str(PENSHOT_DIR), "env": child_env,
                "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log}
    if os.name == "nt":
        # 与 mumu 的 novelservice.start_detached 同一套标志（含踩过的坑）：
        # DETACHED_PROCESS 单给不够 —— 父进程在 kill-on-close 的作业对象里时，
        # 子进程会被一起杀（"启动时说就绪、一转身就没了"）；必须再加
        # CREATE_BREAKAWAY_FROM_JOB。宿主作业不允许脱离时 CreateProcess 直接
        # 失败，所以下面兜一次不带这个标志的重试。
        # STARTUPINFO(SW_HIDE) 是"不许显示窗口"的最后一道显式声明。
        # [EN] Same flags as mumu's novelservice.start_detached (pitfalls included):
        # [EN] DETACHED_PROCESS alone is not enough -- inside a kill-on-close job the
        # [EN] child gets killed with the parent ("ready at start, gone a moment later");
        # [EN] CREATE_BREAKAWAY_FROM_JOB is required, with a retry without it when the
        # [EN] host job forbids breakaway. STARTUPINFO(SW_HIDE) is the last explicit
        # [EN] "no window" declaration.
        base_flags = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED|NEW_GROUP|NO_WINDOW
        kw["creationflags"] = base_flags | 0x01000000       # + BREAKAWAY_FROM_JOB
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0                                  # SW_HIDE
        kw["startupinfo"] = si
        try:
            p = subprocess.Popen(argv, **kw)
        except OSError:
            kw["creationflags"] = base_flags
            try:
                p = subprocess.Popen(argv, **kw)
            except OSError as e:
                log.close()
                _emit(on_line, f"✘ 起不了子进程：{e!r}")
                return False, f"起不了子进程：{e!r}"
    else:
        kw["start_new_session"] = True
        try:
            p = subprocess.Popen(argv, **kw)
        except OSError as e:
            log.close()
            _emit(on_line, f"✘ 起不了子进程：{e!r}")
            return False, f"起不了子进程：{e!r}"
    log.close()

    try:
        PID_FILE.write_text(str(p.pid), encoding="utf-8")
    except OSError:
        pass                                                # pid 文件写不了不影响服务

    ok, waited = _wait_health(timeout, UVICORN_LOG, on_line)
    if ok:
        _emit(on_line, f"✔ 服务已就绪（{waited:.0f} 秒，pid={p.pid}）")
        return True, f"服务已就绪（{waited:.0f} 秒，pid={p.pid}）"
    # 没就绪 ≠ 没起来：给一句能自己接着查的话
    # [EN] Not ready doesn't mean not started: give a line the user can act on
    tail = ""
    try:
        with open(UVICORN_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 800))
            tail = f.read().decode("utf-8", "replace").strip().splitlines()[-3:]
    except OSError:
        pass
    return False, (f"{timeout:.0f} 秒还没就绪"
                   + (f"；日志尾巴：{'；'.join(tail)}" if tail else "")
                   + f"（完整日志 {UVICORN_LOG}）")


def stop_service(on_line=None) -> tuple[bool, str]:
    """停掉服务（按 pid 文件 → 端口反查 → taskkill）。返回 (成功?, 人话)。

    `on_line`：逐行回调（界面弹窗用它显示**停止过程的全套输出**）。
        English:
    Stop the service (pid file → port lookup → taskkill). Returns (success?, human text).
    `on_line`: per-line callback (the UI dialog uses it to show the **full stop output**).
    """
    st = service_status()
    pid = _read_pid()
    if (not pid or not _pid_alive(pid)) and st.ok:
        by_port = _pid_on_port(_port_of())
        if by_port:
            pid = by_port
    if not pid or not _pid_alive(pid):
        if st.ok:
            _emit(on_line, "✘ 服务在跑，但找不到它的 pid —— 请手动结束占用该端口的进程")
            return False, "服务在跑，但找不到它的 pid —— 请手动结束占用该端口的进程"
        _emit(on_line, "○ 服务本来就不在跑")
        return True, "服务本来就不在跑"

    if os.name == "nt":
        cmd = ["taskkill", "/F", "/T", "/PID", str(pid)]
    else:
        cmd = ["kill", "-TERM", str(pid)]
    _emit(on_line, "$ " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace", **_no_window_kw())
    except Exception as e:                                   # noqa: BLE001
        _emit(on_line, f"✘ 停不掉 pid={pid}：{e!r}")
        return False, f"停不掉 pid={pid}：{e!r}"
    for _ln in ((r.stdout or "") + (r.stderr or "")).splitlines():
        if _ln.strip():
            _emit(on_line, _ln.strip())

    # 等它真的退（taskkill 是异步生效的）
    # [EN] Wait for it to really exit (taskkill takes effect asynchronously)
    for _ in range(10):
        if not _pid_alive(pid) and not service_status().ok:
            try:
                PID_FILE.unlink()
            except OSError:
                pass
            _emit(on_line, f"✔ 已停止（pid={pid}）")
            return True, f"已停止（pid={pid}）"
        time.sleep(0.5)
    if not service_status().ok:
        _emit(on_line, f"✔ 已停止（pid={pid}，进程可能还在退出中）")
        return True, f"已停止（pid={pid}，进程可能还在退出中）"
    _emit(on_line, f"✘ 发了停止指令但服务还在跑（pid={pid}）")
    return False, (f"发了停止指令但服务还在跑（pid={pid}）"
                   f"：{(r.stdout or r.stderr or '').strip()[-200:]}")


def stop_service_detached() -> bool:
    """**不等结果**地把服务停掉 —— 专供「关窗口那一刻」用。

    为什么不能直接调同步的 `stop_service()`：调用点是 `on_disconnect`，
    事件循环随时会停、`arm_exit_watchdog` **5 秒**后直接 `os._exit`，
    而这里要跑 `taskkill`、还要循环等它退干净 —— 同步等根本等不到；
    开线程也没用，**`os._exit` 不等任何线程**，停一半就被带走。
    ⇒ 甩一个**独立的 python 进程**去跑同步版：它活过我们，于是"不等"
      不影响它把活干完。
    （「怎么甩」三家桥共用一份：`novelservices/_detach.py`。）

    返回 True = 子进程起来了（**不代表**服务已经停了）。

        English:
    Stop the service **without waiting** — for the moment the window closes.
    Why not just call the synchronous `stop_service()`: the caller is
    `on_disconnect`, the event loop may stop any time and `arm_exit_watchdog`
    does a bare `os._exit` after **5 s**, while this has to run `taskkill` and
    then loop until it is really gone — waiting synchronously can't finish; a
    thread doesn't help either, **`os._exit` waits for no thread** and it would
    be cut off half-way. => Throw out a **separate python process** to run the
    synchronous version: it outlives us, so "not waiting" doesn't stop it from
    finishing. ("How to throw" is one shared copy: `novelservices/_detach.py`.)
    Returns True = the child started (**not** that the service has stopped).
    """
    try:                                    # 包导入（主程序：`from novelservices import penshot_bridge`）
        from ._detach import run_detached   # [EN] package import (the app)
    except ImportError:                     # noqa: BLE001
        from _detach import run_detached    # 顶层导入（`service_ctl` 把本目录塞进 `sys.path` 后 import）
                                            # [EN] top-level import (`service_ctl` puts this dir on `sys.path`)
    import sys
    app = str(Path(__file__).resolve().parents[1])
    code = "from novelservices.penshot_bridge import stop_service as _s; _s()"
    return run_detached([sys.executable, "-c", code], cwd=app)


def _port_of() -> int:
    cfg = _config()
    try:
        return int(_cfg_s(cfg, "PENSHOT_PORT", "8000"))
    except (TypeError, ValueError):
        return 8000


# ══════════════════════════════════════════════════════════════════
#  主入口：生成分镜
# [EN] Main entry: generate the storyboard
# ══════════════════════════════════════════════════════════════════
def _safe_script_id(project_key: str) -> str | None:
    """PenShot 用 script_id 做记忆隔离和输出目录名 —— 只留安全字符。

    ★ 中文书名清洗后往往只剩一串 `_`（所有书名撞进同一个桶），这种**退化**
      情况返回 None，让 PenShot 自己按剧本内容生成 id（它内部有生成器）。
      `None` 时调用方要把这个键从请求里去掉。

    English:
    PenShot uses script_id for memory isolation and output directory names --
    keep only safe characters. A **degenerate** result (e.g. a Chinese title
    scrubbed down to underscores, which would collide across books) returns
    None so PenShot generates its own content-hashed id. Callers must omit the
    key from the request when it is None.
    """
    s = re.sub(r"[^0-9A-Za-z_-]+", "_", (project_key or "").strip())[:40].strip("_")
    return s or None


def _render_storyboard(data: dict[str, Any], title: str) -> str:
    """把 PenShot 的结果 JSON 渲染成导演能读的分镜文本。

    数据形状（源码 `workflow_nodes.generate_output_node`）：
        data.instructions.fragments[]  每段的视频生成提示词（prompt/负向/时长/风格/配乐）
        data.shot_sequence.shots[]     镜头清单（类型/情绪/描述/时长/角色）
        data.script_analysis.scenes[]  场景清单（地点/时间）
        data.audit_report              质量审查（分数/状态）

    English:
    Render PenShot's result JSON into a director-readable storyboard text.
    """
    lines: list[str] = []
    lines.append(f"# {title or '分镜方案'}（PenShot · 剧本分镜智能体）")

    scenes = (data.get("script_analysis") or {}).get("scenes") or []
    shots = (data.get("shot_sequence") or {}).get("shots") or []
    instructions = data.get("instructions") or {}
    fragments = instructions.get("fragments") or []
    audit = data.get("audit_report") or {}

    total = 0.0
    for sh in shots:
        try:
            total += float(sh.get("duration") or 0.0)
        except (TypeError, ValueError):
            pass
    head = f"共 {len(shots)} 个镜头 / {len(fragments)} 段提示词"
    if total:
        head += f" · 总时长 ≈ {total:.0f}s"
    if audit:
        head += f" · 质量审查 {audit.get('score')}%（{audit.get('status')}）"
    lines.append(head)

    # 场景头（按 scene_id 分组打印镜头）
    # [EN] Scene headers (shots grouped by scene_id)
    by_scene: dict[str, list[dict[str, Any]]] = {}
    for sh in shots:
        by_scene.setdefault(str(sh.get("scene_id") or ""), []).append(sh)
    scene_titles: dict[str, str] = {}
    for sc in scenes:
        sid = str(sc.get("id") or "")
        loc = (sc.get("location") or "").strip()
        tod = (sc.get("time_of_day") or "").strip()
        scene_titles[sid] = f"{loc} / {tod}".strip(" /")

    for sid, group in by_scene.items():
        lines.append("")
        lines.append(f"【场 {sid or '—'}】{scene_titles.get(sid, '')}".rstrip())
        for sh in group:
            lines.append(f"  镜头 {sh.get('id') or '—'}"
                         f"（{sh.get('shot_type') or '—'} · {sh.get('emotion') or '—'}"
                         f" · {sh.get('duration')}s）：{sh.get('description') or ''}")
            mc = (sh.get("main_character") or "").strip()
            if mc:
                lines.append(f"    角色：{mc}")
    if not by_scene and shots:
        lines.append("")
        for sh in shots:
            lines.append(f"  镜头 {sh.get('id') or '—'}：{sh.get('description') or ''}")

    # fragment 提示词（给下游出图/出视频用）
    # [EN] fragment prompts (for downstream image/video generation)
    if fragments:
        lines.append("")
        lines.append("── 分段生成提示词 ──")
        for i, fr in enumerate(fragments, 1):
            lines.append(f"  片段 {i}（{fr.get('duration')}s"
                         + (f" · {fr.get('style')}" if fr.get("style") else "") + "）：")
            prompt = (fr.get("prompt") or "").strip()
            if prompt:
                lines.append(f"    正向：{prompt}")
            neg = (fr.get("negative_prompt") or "").strip()
            if neg:
                lines.append(f"    负向：{neg}")
            mc = (fr.get("main_character") or "").strip()
            if mc:
                lines.append(f"    角色：{mc}")
            audio = fr.get("audio") or {}
            if audio.get("prompt"):
                lines.append(f"    配乐：{audio['prompt']}"
                             f"（{audio.get('duration_seconds') or audio.get('duration') or '?'}s）")
    return "\n".join(lines).strip()


def generate_storyboard(task: DirectorTask) -> BridgeResult:
    """把一件事交给 PenShot：**把这一段场景拆成分镜，拿回分镜方案**。

    流程：
        ① 服务在不在 → 不在就请调用方回退
        ② POST /api/v1/storyboard/sync（同步等结果）→ 拿 data
        ③ 渲染成导演可读的分镜文本

    ★ 请求里钉 `human_intervention_mode="auto"`：上游默认 `interactive`，
      工作流一旦走到"需要人工干预"会**等输入**—— 无头服务里就是干等超时。

    ★ `timeout` 同时写给服务端（它等这么久）和客户端 socket（再多 60 秒）。

    返回的 `BridgeResult.ok=False` 全部是**可回退**的失败 —— 调用方应当
    退回内部导演逻辑。

    English:
    Hand one task to PenShot: break the scene into a storyboard and return the plan.
    All `BridgeResult.ok=False` are fallback-able failures.
    """
    t0 = time.time()

    def _fail(msg: str) -> BridgeResult:
        return BridgeResult(False, reason=msg, elapsed=time.time() - t0)

    if not task.script_text.strip():
        return _fail("场景原文(script_text)是空的 —— 没有它 PenShot 不知道拆什么")

    st = service_status()
    if not st.ok:
        return _fail(f"PenShot 没在跑：{st.reason}")

    server_timeout = min(float(task.timeout or 900.0), 1800.0)
    body: dict[str, Any] = {
        "script": task.script_text,
        "language": "zh",
        "timeout": server_timeout,
        "config": {
            "human_intervention_mode": "auto",
            "auto_continue_on_human_intervention": True,
        },
    }
    # script_id 只在清洗后没退化时才发；退化（如纯中文书名 → None）时上游
    # 自己按剧本内容生成内容哈希 id，发 null 反而会撞同一个桶。
    # [EN] Only send script_id when it is not degenerate; otherwise upstream
    # generates its own content-hashed id (a JSON null would collide all books).
    sid = _safe_script_id(task.project_key)
    if sid:
        body["script_id"] = sid

    base = service_url()
    try:
        req = urllib.request.Request(
            base + "/api/v1/storyboard/sync",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json"}, method="POST")
        with _NO_PROXY.open(req, timeout=server_timeout + 60.0) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            # ★ 上游（FastAPI 默认异常处理器）的错误体键名是 **"error"**，
            #   不是 FastAPI 的 "detail" —— 两个都读，别只读一个。
            # [EN] Upstream error bodies use the "error" key, not FastAPI's
            # "detail" -- read both.
            err_body = json.loads(e.read().decode("utf-8")) or {}
            detail = err_body.get("detail") or err_body.get("error") or ""
        except Exception:                                    # noqa: BLE001
            pass
        return _fail(f"生成请求返回 HTTP {e.code}"
                     + (f"：{detail}" if detail else ""))
    except Exception as e:                                   # noqa: BLE001
        return _fail(f"生成请求失败：{e!r}")

    if not payload.get("success"):
        return _fail(f"PenShot 没返回成功标记：{payload.get('message') or payload}")

    data = payload.get("data") or {}
    # 空结果判定要落在**数据本体**上，别拿渲染文本做子串匹配（曾经踩过：
    # 用 `in` 判列表成员是精确相等，"共 0 个镜头 / 4 段提示词" 整条都不等于
    # "共 0 个镜头"，空分镜被放过去）。
    # [EN] Judge emptiness on the data itself, not by substring-matching the
    # rendered text (list `in` checks exact equality, so a "0 shots" line
    # slipped through before).
    def _as_dict(v: Any) -> dict[str, Any]:
        return v if isinstance(v, dict) else {}
    shots = _as_dict(data.get("shot_sequence")).get("shots") or []
    fragments = _as_dict(data.get("instructions")).get("fragments") or []
    if not shots and not fragments:
        return _fail("分镜是空的（可能场景原文太短，或服务端走了规则引擎也没拆出东西）")
    text = _render_storyboard(data, task.title or task.project_key)
    return BridgeResult(True, text=text, elapsed=time.time() - t0, raw=data)


def describe() -> str:
    st = service_status()
    return (f"PENSHOT_DIR   = {PENSHOT_DIR}\n"
            f"服务地址      = {service_url()}\n"
            f"服务状态      = {'在跑' if st.ok else '不在跑'} {st.reason}\n"
            f"上游          = {UPSTREAM}")


if __name__ == "__main__":
    print(describe())
