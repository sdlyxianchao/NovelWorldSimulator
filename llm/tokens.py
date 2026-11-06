# -*- coding: utf-8 -*-
"""token 估算与计价。
English:
token estimation and pricing.
"""
from __future__ import annotations

import datetime as _dt
import re

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")
_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")
_PUNCT = re.compile(r"[，。、；：？！""''（）《》—…·,.!?;:()\\[\\]{}<>\"'`~-]")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    words = len(_WORD.findall(text))
    punct = len(_PUNCT.findall(text))
    return int(cjk * 0.7 + words * 1.3 + punct * 0.5) + 1


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(m.get("content") or "") + 4
    return total


# ══════════════════════════════════════════════════════════════════
#  价格表：值一律是 **(缓存命中输入, 未命中输入, 输出)**，单位 **元 / 百万 token**
# [EN] Price table: a value is always **(cache-hit input, cache-miss input, output)** in
# [EN] **CNY per million tokens**
# ══════════════════════════════════════════════════════════════════
#: ⚠⚠ **这张表只是「参考基准」，不是权威价格**（2026-10-12 抄录）。它有两个用途：
#:   ① 没有登记表条目时兜底算账；② 界面上给人一个"这个模型大概多少钱"的参照。
#:   为什么必须这么讲：**价格一直在动**（DeepSeek 2026-08-17 刚调过一次，缓存命中
#:   价一次涨了 11 倍）。把某一时刻的数字当真理写死，只会让账本"看起来很精确、
#:   其实全错"。**想让账准，请在「模型与LLM → 编辑某条模型」里填你自己账单上的单价**
#:   —— 填了就以你填的为准（见 `llm/models.py::price_overrides()`）。
#:   取价口径：**一律取"贵的那个"当上限**。DeepSeek 是峰谷定价（高峰是空闲的 2 倍），
#:   表里取**高峰价** —— 这本账是"预算闸门"用的，**低估会让闸门失效**（超支了才发现）。
#:   真按空闲时段跑的人，用 `LLM_OFFPEAK_DISCOUNT`（默认 0.5）自动打折，见 `peak_now()`。
# [EN] ⚠⚠ **This table is only a "reference baseline", not authoritative pricing** (transcribed
# [EN] 2026-10-12). It has two uses: (1) fall back when a registry entry has no prices;
# [EN] (2) give a human a "roughly how much does this model cost" reference in the UI.
# [EN] Why this must be stated: **prices keep moving** (DeepSeek changed them on 2026-08-17; the
# [EN] cache-hit rate jumped 11x in one go). Hardcoding one moment's numbers as truth only makes the
# [EN] ledger "look precise while being entirely wrong". **To make the ledger accurate, fill in the
# [EN] prices on your own bill under "Models & LLM -> edit a model"** -- whatever you fill in wins
# [EN] (see `llm/models.py::price_overrides()`).
# [EN] Which price is taken: **always the more expensive one** as the upper bound. DeepSeek uses
# [EN] peak/off-peak pricing (peak is 2x off-peak); the table takes the **peak price** -- this ledger
# [EN] is a "budget gate", and **underestimating it makes the gate useless** (you only find out after
# [EN] overspending). Anyone actually running off-peak gets a discount via `LLM_OFFPEAK_DISCOUNT`
# [EN] (default 0.5), see `peak_now()`.
PRICE_TABLE: dict[str, tuple[float, float, float]] = {
    # ── DeepSeek（人民币，2026-08-17 峰谷调价后的**高峰价**）──
    # 官方口径：高峰 = 北京时间周一至周五 9:00-12:00、14:00-18:00（不含法定节假日）；
    # 空闲时段为高峰的 **一半**。
    # [EN] ── DeepSeek (CNY, **peak price** after the 2026-08-17 peak/off-peak adjustment) ──
    # [EN] Official rule: peak = Beijing time Mon-Fri 09:00-12:00 and 14:00-18:00 (statutory
    # [EN] holidays excluded); off-peak is **half** of peak.
    "deepseek-v4-pro": (0.3, 9.0, 27.0),        # official: 0.3 hit / 9 miss / 27 out
    "deepseek-v4-flash": (0.1, 2.0, 8.0),       # no official peak price for Flash; from history
    "deepseek-flash": (0.1, 2.0, 8.0),          # official recommended name; same as above
    "deepseek-chat": (0.1, 2.0, 8.0),           # deprecated old name; billed as flash
    "deepseek-reasoner": (0.2, 4.0, 16.0),      # deprecated old name (thinking); flash thinking
    # ── 国内其余主要模型（元 / 百万 token；2026-10-12 抄录，**务必按自己账单校准**）──
    # [EN] ── Other major Chinese models (CNY per million tokens; transcribed 2026-10-12,
    # [EN] **calibrate against your own bill**) ──
    "hy3": (0.25, 1.0, 4.0),                    # Tencent Hunyuan Hy3 release
    "hunyuan": (0.25, 1.0, 4.0),                # Hunyuan fallback (substring hits hy3 first)
    "glm-4-flash": (0.0, 0.0, 0.0),             # Zhipu free tier
    "glm-4.6": (0.2, 1.0, 3.2),
    "glm-5": (0.2, 1.0, 3.2),
    "kimi-k2": (0.15, 0.6, 3.0),
    "kimi": (0.15, 0.6, 3.0),
    "qwen-plus": (0.2, 2.8, 8.0),
    "qwen-max": (0.8, 8.0, 24.0),
    "qwen-turbo": (0.1, 1.0, 3.0),
    "qwen": (0.2, 2.8, 8.0),
    "minimax": (0.05, 0.3, 1.2),
    "mimo": (0.2, 1.0, 3.0),
    # ── 国外（按 ≈7.1 折人民币；原价以美元记在行尾，方便你自己核）──
    # [EN] ── Overseas (converted at ~7.1 CNY/USD; the USD price is in the trailing comment so you
    # [EN] can check it yourself) ──
    "gpt-4o": (1.7, 17.0, 68.0),                # $2.5/$10 (old price, kept for legacy configs)
    "gpt-4o-mini": (0.1, 1.0, 4.0),             # $0.15/$0.6
    "gpt-5.5": (0.5, 35.0, 213.0),              # $5/$30
    "gpt-5.4": (0.3, 17.8, 106.5),              # $2.5/$15
    "gpt-5.4-nano": (0.02, 1.4, 8.9),           # $0.2/$1.25
    "claude-opus": (4.5, 44.0, 177.0),          # $6.25/$25
    "claude-sonnet": (0.3, 21.0, 106.5),        # $3/$15 (hit price at the usual 1/10)
    "claude-haiku": (0.7, 7.1, 35.5),           # $1/$5
    "claude": (0.3, 21.0, 106.5),               # fallback: Sonnet tier
    "gemini-3-flash": (0.05, 3.5, 21.3),        # $0.5/$3
    "gemini-3": (0.1, 14.2, 85.2),              # $2/$12 (Pro)
    "gemini": (0.1, 14.2, 85.2),
    "grok": (0.2, 8.9, 17.8),                   # $1.25/$2.5
}
#: 认不出来时的兜底价。取一个**偏保守（偏高）**的中档数字 —— 宁可高估（闸门会提前拦），
#: 也别低估（超支了才发现）。
# [EN] : fallback price when nothing matches. A **conservative (higher)** mid-tier number --
# [EN] better to overestimate (the gate catches it early) than underestimate (you find out after
# [EN] overspending).
_DEFAULT_PRICE: tuple[float, float, float] = (0.3, 3.0, 10.0)


def _norm(v) -> tuple[float, float, float]:
    """把 2 元组或 3 元组统一成 `(命中, 未命中, 输出)`。

    · `(a, b)` —— **老写法**（输入 / 输出），命中价按**未命中的 1/10** 推
      （DeepSeek / OpenAI / Anthropic 三家都大致是这个比例，是个安全的近似）；
    · `(a, b, c)` —— 命中 / 未命中 / 输出。
    
        English:
    Normalize a 2-tuple or 3-tuple into `(hit, miss, output)`.
        · `(a, b)` -- **the old form** (input / output); the hit price is inferred as **1/10 of
          the miss price**
          (roughly the ratio at DeepSeek / OpenAI / Anthropic, a safe approximation);
        · `(a, b, c)` -- hit / miss / output.
    """
    try:
        vals = [float(x) for x in v]
    except (TypeError, ValueError):
        return _DEFAULT_PRICE
    if len(vals) >= 3:
        return (vals[0], vals[1], vals[2])
    if len(vals) == 2:
        return (vals[0] * 0.1, vals[0], vals[1])
    return _DEFAULT_PRICE


def parse_overrides(s: str) -> dict[str, tuple[float, float, float]]:
    """解析 `MODEL_PRICE_OVERRIDES`。

    每条 `名字=未命中/输出`（旧写法，命中价自动按 1/10）或
    `名字=命中/未命中/输出`（新写法，三段都能自己填）。
    
        English:
    Parse `MODEL_PRICE_OVERRIDES`.
        Each entry is `name=miss/output` (old form; the hit price is auto-derived at 1/10) or
        `name=hit/miss/output` (new form, all three parts fillable).
    """
    out: dict[str, tuple[float, float, float]] = {}
    for part in (s or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, price = part.split("=", 1)
        nums = price.split("/")
        if not name.strip() or not 2 <= len(nums) <= 3:
            continue
        try:
            vals = [float(x) for x in nums]
        except ValueError:
            continue
        out[name.strip()] = _norm(vals if len(vals) == 3
                                  else (vals[0] * 0.1, vals[0], vals[1]))
    return out


def peak_now(ts: float | None = None) -> bool:
    """现在是不是 DeepSeek 的**高峰时段**（北京时间周一至周五 9:00-12:00、14:00-18:00）。

    ★ 为什么本项目要管这个（2026-10-12，用户要求"降低费用"）：DeepSeek 空闲时段是
      高峰的**一半**价。模拟是**可以挑时间跑**的活（不是在线问答），把大批量推演放到
      夜里跑，账直接砍一半 —— 这是"不改一行提示词就能省"的最大一项。
      ⚠ 只对**认得出是峰谷定价**的模型有意义（现在只有 DeepSeek），别的家是平价。
    
        English:
    Whether it is DeepSeek's **peak window** right now (Beijing time Mon-Fri 09:00-12:00 and
    14:00-18:00).
        ★ Why this project cares (2026-10-12, user asked to "reduce cost"): DeepSeek's off-peak is
          **half** the peak price. A simulation is work that **can pick its time** (unlike an
          online Q&A); running bulk simulation at night cuts the bill in half -- the biggest single
          saving that needs no prompt change.
          ⚠ Only meaningful for models **recognizable as peak/off-peak priced** (DeepSeek today);
          other providers are flat.
    """
    try:
        bj = _dt.datetime.fromtimestamp(ts if ts is not None else _dt.datetime.now().timestamp(),
                                        tz=_dt.timezone(_dt.timedelta(hours=8)))
    except Exception:                                            # noqa: BLE001
        return False
    if bj.weekday() >= 5:            # weekends are off-peak all day
        return False
    h = bj.hour + bj.minute / 60.0
    return (9.0 <= h < 12.0) or (14.0 <= h < 18.0)


def is_peak_model(model: str) -> bool:
    """这个模型是不是峰谷定价的（DeepSeek 一家）。
        English:
    Whether this model is peak/off-peak priced (DeepSeek only).
    """
    m = (model or '').strip().lower()
    return m.startswith('deepseek')


def _builtin_of(model: str) -> tuple[float, float, float]:
    """内置表这一档（先全等、再**最长前缀**匹配、最后兜底）。
        English:
    The built-in tier for this one (exact match, then **longest-prefix** match, then fallback).
    """
    if model in PRICE_TABLE:
        return PRICE_TABLE[model]
    low = (model or '').strip().lower()
    best: tuple[str, tuple[float, float, float]] | None = None
    for k, v in PRICE_TABLE.items():
        if low.startswith(k.lower()) and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best is not None else _DEFAULT_PRICE


def price_of(model: str,
             overrides: dict | None = None) -> tuple[float, float, float]:
    """这个模型的三段单价 `(命中, 未命中, 输出)`。

    查找顺序：**用户填的（登记表 / `MODEL_PRICE_OVERRIDES`）→ 内置表（先全等、再最长前缀）→ 兜底**。
    ⚠ 用户填的那份**允许只填一部分**（没填的段是负数）—— 那几段就回去用内置表。
      所以"我只知道输出价"也能填，不必三段齐。
    ⚠ 前缀匹配要**先挑最长的那个键**（`deepseek-v4-flash` 必须赢过 `deepseek`），
      否则"哪个键先定义"就决定了价格 —— 那种 bug 只在改了表顺序时才现形。
    
        English:
    The three-part unit prices `(hit, miss, output)` for this model.
        Lookup order: **user-filled (registry / `MODEL_PRICE_OVERRIDES`) -> built-in table (exact
        then longest prefix) -> fallback**.
        ⚠ The user-filled copy **may fill only part of it** (unfilled parts are negative) -- those
          parts fall back to the built-in table. So "I only know the output price" is enough; you
          need not fill all three.
        ⚠ Prefix matching must **pick the longest key** (`deepseek-v4-flash` must beat `deepseek`),
          otherwise "which key is defined first" decides the price -- a bug that only shows up when
          the table order changes.
    """
    base = _builtin_of(model)
    ov = None
    if overrides:
        if model in overrides:
            ov = _norm(overrides[model])
        else:
            low = (model or '').strip().lower()
            best = None
            for k, v in overrides.items():
                ks = str(k)
                if low.startswith(ks.lower()) and (best is None or len(ks) > len(best)):
                    best = ks
            if best is not None:
                ov = _norm(overrides[best])
    if ov is None:
        return base
    return tuple(ov[i] if float(ov[i]) >= 0 else base[i] for i in range(3))


def saved_by_cache(model: str, cache_tok: int,
                   overrides: dict | None = None) -> float:
    """这些命中缓存的 token，比"没命中"少花了多少钱（元）。

    ★ 为什么需要一个**单独**的函数（2026-10-12）：账本里只有"实际花了多少"，
      而"本来要花多少"要靠 `(未命中价 − 命中价) × 命中量` 反推。没有这个数，
      用户看到的就只有一个总数 —— **他不知道自己有没有享受到那 90% 的折扣**，
      也就无从判断"要不要继续优化提示词顺序"。
    
        English:
    How much less these cache-hit tokens cost compared with "no hit" (CNY).
        ★ Why a **separate** function (2026-10-12): the ledger only has "what was actually spent",
          while "what it would have cost" must be derived as `(miss price - hit price) x hit
          volume`. Without this number the user only sees a total -- **they cannot tell whether they
          got that 90% discount**, and so cannot judge "should I keep optimizing prompt order".
    """
    hit_p, miss_p, _out_p = price_of(model, overrides)
    delta = float(miss_p) - float(hit_p)
    if delta <= 0:
        return 0.0
    return delta * max(0, int(cache_tok or 0)) / 1_000_000.0


def hit_ratio(tin: int, cache_tok: int) -> float:
    """命中率（0~1）。输入为 0 时返回 0（不是 None —— 界面直接拿去乘 100）。
        English:
    Hit ratio (0~1). Returns 0 when input is 0 (not None -- the UI multiplies by 100 directly).
    """
    t = max(0, int(tin or 0))
    if t <= 0:
        return 0.0
    return min(1.0, max(0, int(cache_tok or 0)) / float(t))


def cost_of(model: str, tin: int, tout: int, overrides: dict | None = None,
            cache_tok: int = 0, *, peak: bool | None = None) -> float:
    """这一发花了多少钱（元）。

    `cache_tok`：这次输入里**命中前缀缓存**的 token 数（DeepSeek 会在响应里报）。
    命中部分按命中价算 —— 不区分的话，缓存省下的钱**在账本上完全看不见**，
    用户也就永远不知道自己有没有享受到那 90% 的折扣。

    `peak`：这一发算在**高峰**还是**空闲**时段。`None`（默认）= 按当前钟点自己判。
    ⚠ 参数名是 `peak` 不是 `offpeak` —— 早先那版叫 `offpeak` 却按"是不是高峰"用，
      判据里 `offpeak=False` 反而触发了折扣（一次就写错、而且看不出来）。
    
        English:
    How much this request costs (CNY).
        `cache_tok`: how many input tokens **hit the prefix cache** (DeepSeek reports this in the
        response). Hit tokens are billed at the hit price -- without the distinction, the money
        cached away is **invisible in the ledger**, and the user can never tell whether they got
        that 90% discount.
        `peak`: whether this request counts in the **peak** or **off-peak** window. `None` (the
        default) decides from the current clock.
        ⚠ The parameter is `peak`, not `offpeak` -- an earlier version was named `offpeak` but used
          as "is it peak", so `offpeak=False` in a criterion actually triggered the discount (wrong
          once, and invisibly).
    """
    hit_p, miss_p, out_p = price_of(model, overrides)
    c = max(0, int(cache_tok or 0))
    if c > int(tin or 0):
        c = max(0, int(tin or 0))
    miss_in = max(0, int(tin or 0) - c)
    # 峰谷：认得出是峰谷定价的模型，空闲时段按折扣算（默认 0.5 = 半价）。
    # [EN] Peak/off-peak: for recognizable peak-priced models, off-peak gets the discount
    # [EN] (default 0.5 = half price).
    factor = 1.0
    if is_peak_model(model):
        try:
            from config import CFG
            disc = float(CFG.f('LLM_OFFPEAK_DISCOUNT'))
        except Exception:                                        # noqa: BLE001
            disc = 0.5
        pk = peak_now() if peak is None else bool(peak)
        if not pk and 0.0 <= disc <= 1.0:
            factor = disc
    return factor * (c * hit_p + miss_in * miss_p + int(tout or 0) * out_p) / 1_000_000.0
