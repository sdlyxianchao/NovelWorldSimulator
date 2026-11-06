# -*- coding: utf-8 -*-
"""LLM 路由器：三档模型 + 并发限流 + 指数退避 + 计费 + mock。

调用方式：
    from llm.router import llm
    text = await llm.chat("front", messages, purpose="narrative")

English:
LLM router: three tiers of models + concurrency rate limiting + exponential backoff + billing +
mock.
Usage:
    from llm.router import llm
    text = await llm.chat("front", messages, purpose="narrative")
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import random
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

import httpx

from config import CFG
from llm.capabilities import (CAP_JSON, CAP_KEYS, CAP_REASONING, CAP_SYSTEM,
                              CAP_THINKING, detect_thinking_switch,
                              max_output_tokens)
# ★ 模型登记表（2026-10-12）：一个程序里可以配多个模型，谁用哪个由
#   「Agent → 模型」决定。解析顺序见 `llm/models.py` 的模块头。
# [EN] ★ Model registry (2026-10-12): one program can hold several models, and who uses which is
# [EN] decided by "Agent -> model". See the module header of `llm/models.py` for the order.
from llm import models as MODELS
# ★★★ 「这一家没钱了」是一条**独立的停止条件**（2026-10-25，用户点名）：
#   它不该走"重试 3 次再抛 RuntimeError"，也不该被下游 `except Exception` 降级成
#   "这一次没拿到东西"。口径与登记表都在 `llm/credit.py`。
# [EN] ★★★ "This provider is out of money" is **its own stopping condition** (2026-10-25,
# [EN] requested by the user): it must not go through "retry 3 times then raise RuntimeError",
# [EN] nor be degraded by a downstream `except Exception` into "this call got nothing".
from llm import credit as CREDIT
from llm.mock import mock_reply
from llm.tokens import cost_of, estimate_messages_tokens, estimate_tokens, parse_overrides
from util.io import atomic_write_text
# 输出语言（项目级）：**只有提示词能决定模型用什么语言写**，所以在这一层统一注入
# [EN] Output language (project level): **only the prompt determines what language the model writes
# [EN] in**, so it is injected uniformly at this layer.
from util import outlang
from util.jsonio import extract_json

_LOG = __import__("logging").getLogger("nws.llm")


# ══════════════════════════════════════════════════════════════════
#  「结论型」用途：思维链帮不上忙，却会把 max_tokens 吃光
# [EN] "Conclusion-type" use: chain-of-thought doesn't help, but it drains max_tokens.
# ══════════════════════════════════════════════════════════════════
#
# **判据**：这个用途要的是**一个结论** —— 是/否、属于哪一类、对上了哪几个节点；
# 附带的自由文本（「理由」「进展描述」）只是说明，不是主体。这类用途一律
# **主动关掉思考**（模型支持的话，见 `LLM_CAP_THINKING`）。
# [EN] **Criterion**: this kind of use wants **a single conclusion** - yes/no, which category it
# [EN] belongs to, which nodes it matched;
# [EN] the accompanying free text ("reason", "progress description") is only explanation, not the main
# [EN] body. This kind of use is always
# [EN] **actively disable thinking** (if the model supports it, see `LLM_CAP_THINKING`).
#
# 为什么要有这张表（2026-10-06 实测，不是猜的）：
#   同一轮推演里，`progress_eval`（每拍一次的进度评估，提示词只有 6 行，
#   问的是"判据满足了没有"）**63 次调用里 8 次**把 2000 token **整份花在思考上**，
#   `finish_reason=length`、正文一个字都没写出来；而同一轮 126 次 `agent_decide`
#   （要写台词与内心，输出 80~112 token）**一次都没超**。
#   差别不在预算，在于**这个任务到底需不需要想那么久**。
#   直连复现：给 `deepseek-flash` 一句「请判断：阿福被掌柜收留了吗？」，
#   它思考 3233 token、正文 0 字；加上 `thinking:{"type":"disabled"}` 之后
#   61 token 就给出完整答案 —— 快 50 倍，而且是真的答完了。
# [EN] Why this table exists (measured on 2026-10-06, not guessed):
# [EN] In the same round of simulation, `progress_eval` (progress evaluation run once per beat, prompt
# [EN] is only 6 lines,
# [EN] asking "has the criterion been met") **in 8 out of 63 calls** spent the entire 2000 tokens **on
# [EN] thinking**,
# [EN] `finish_reason=length`, not a single character of body text written; while in the same round,
# [EN] 126 calls to `agent_decide`
# [EN] (which must write dialogue and inner monologue, output 80~112 tokens) **never once exceeded**.
# [EN] The difference is not the budget, it's **whether this task actually needs to think that long**.
# [EN] Direct reproduction: give `deepseek-flash` the single sentence "Please judge: was A-Fu taken in
# [EN] by the shopkeeper?",
# [EN] it thinks for 3233 tokens, 0 characters of body text; after adding
# [EN] `thinking:{"type":"disabled"}`
# [EN] it gives the complete answer in 61 tokens - 50x faster, and it actually finished answering.
#
# ⚠ 加新用途进这张表的条件：**输出结构的主体是"一个结论"**。
#   要写东西的（叙事、台词、设定、摘要、改写）**一律不进** —— 那些正需要思考，
#   关掉反而伤质量，而且它们的 max_tokens 本来就给得足。
# [EN] ⚠ Condition for adding a new use to this table: **the main body of the output structure is "a
# [EN] single conclusion"**.
# [EN] Uses that need to write things (narrative, dialogue, settings, summaries, rewrites) **never go
# [EN] in** - those genuinely need thinking,
# [EN] disabling it hurts quality instead, and their max_tokens is already given generously to begin
# [EN] with.
NO_THINK_PURPOSES = frozenset({
    'progress_eval',   # 进度判据满足了没有 → 布尔 + 两句说明
    'genre',           # 属于哪个故事类型 → 一个标签
    'alignment',       # 正文对上了哪几个进度节点 → 一串 id
    # 小地图布局（2026-10-06）：一小份 JSON，每个地点就 6 个字段。
    # 让推理模型"想"这个，思考会把 1400 的额度吃掉、正文一个字符不剩
    # （§51 那次事故：开思考 3233 token 答 0 字）。
    # [EN] Has the progress criterion been met → boolean + two sentences of explanation
    # [EN] Which story type it belongs to → a single tag
    # [EN] Which progress nodes the body text matched → a string of ids
    # [EN] Minimap layout (2026-10-06): a small piece of JSON, each location has just 6 fields.
    # [EN] Letting a reasoning model "think" about this, the thinking eats the 1400 quota and not a single
    # [EN] character of body text is left
    # [EN] (the incident in §51: with thinking on, 3233 tokens to answer 0 characters).
    'minimap_layout',
    # ── 下面三个是 2026-10-07 **真跑两天推演**时补的 ──
    #   那次实测（真模型 deepseek-flash，样例《更漏子》）：这几处**正文一个
    #   字符都没拿到**，日志里一排
    #   「LLM 一个字都没拿到（max_tokens 全被用光，含思考内容）」。
    #   后果不是"少一条产出"，而是**功能整块报废**：
    #     · `crew_day_map` 挂了 → **当天地图从来没画出来过**（用户上一轮刚点名的功能）；
    #     · `day_verify` 挂了 → 导演验算永远"拿不到结论"，只能带空意见重写；
    #     · `crew_research` 挂了 → 资料员每天报"没出活"。
    #   三个都是**结论型**（一份布局 JSON / 一个通过与否 / 一份存疑清单），
    #   按本表的标准就该关思考 —— 尤其 `crew_day_map`，它和上面那条
    #   `minimap_layout` 是同一个东西的前后两版（当天地图改造时换了用途名，
    #   这张表**没跟着改**，于是它从"关思考"掉回了"开思考"）。
    'crew_day_map',    # 当天地图 → 布局 JSON（`minimap_layout` 的后继）
    'day_verify',      # 剧本验算 → 通过 / 不通过 + 几条意见
    'crew_research',   # 考据 → 一份「存疑」清单 + 一句结论
    # [EN] ── The following three were added on 2026-10-07 during **two real days of simulation** ──
    # [EN] In that measurement (real model deepseek-flash, sample "Genglouzi"): at these places **not a
    # [EN] single character
    # [EN] of body text was obtained**, the log was a row of
    # [EN] "LLM got not a single character (max_tokens all used up, including thinking content)".
    # [EN] The consequence is not "one fewer output", but **the whole feature is scrapped**:
    # [EN] · `crew_day_map` broke → **the day map was never drawn even once** (the feature the user had
    # [EN] just called out in the previous round);
    # [EN] · `day_verify` broke → the director's verification could never "get a conclusion", and could
    # [EN] only rewrite with empty feedback;
    # [EN] · `crew_research` broke → the researcher reported "no output" every day.
    # [EN] All three are **conclusion-type** (a layout JSON / a pass-or-fail / a list of doubts),
    # [EN] by this table's standard thinking should be disabled - especially `crew_day_map`, which
    # [EN] together with the `minimap_layout` above is the before and after of the same thing (when the day
    # [EN] map was reworked the use name was changed,
    # [EN] but **this table was not updated along with it**, so it fell from "thinking disabled" back to
    # [EN] "thinking enabled").
    # [EN] Day map → layout JSON (successor of `minimap_layout`)
    # [EN] Script verification → pass / fail + a few comments
    # [EN] Research → a list of "doubts" + one concluding sentence
})


# ══════════════════════════════════════════════════════════════════
#  **流式**（2026-10-23，用户点名）
# [EN] **Streaming** (named by the user 2026-10-23)
# ══════════════════════════════════════════════════════════════════
#  用户原话：「表示在执行的消息 我点开这个按钮以后应该是 **LLM 的思考过程流式返回**」。
#
#  ★ 为什么流式要**按作用域打开**，而不是全局改成流式：
#    非流式的返回是"一次拿到 `resp.json()`"，而流式要逐块读 SSE —— 两者的
#    错误形态、超时语义、usage 来源都不同。全局换掉等于把 29 处调用点
#    一次性押上去。所以：**默认仍是老路**，只在 `stream_scope(True)` 里走流式。
#
#  ★ 为什么用 `ContextVar` 而不是给每个调用点加参数：
#    剧组那一路的调用链很深（`Studio.call` → 职位实现 → `llm.replies.ask`
#    → `llm.chat` → `_real_call`），中间那些函数**都不认识"流式"这件事**，
#    给它们每个加参数就是"把界面的需求漏进业务层"。`ContextVar` 在
#    `await` 链上自动传递（并行子任务各自继承一份），设一次就够 ——
#    与 `llm/usage.set_ctx`、`llm/models.use` 是同一套办法。
#
#  ★ 为什么"这家服务商不认流式"要**记住**：`stream_options` 是 OpenAI 的
#    扩展字段，个别兼容网关直接 400。发现了就记一笔，以后这个进程不再试
#    —— 不然每次出工都要先白扔一发请求，用户看到的是"剧组变慢了"。
#
#  English:
#  The user's words: "for messages that are executing, clicking the button should show
#  **the LLM's thinking streaming in**".
#  ★ Why streaming is **scoped** rather than globally enabled: a non-streaming reply is
#    "one `resp.json()`" while streaming reads SSE chunk by chunk -- different error shapes,
#    different timeout semantics, a different source for usage. Swapping it globally would
#    bet all 29 call sites at once. So the old path stays the default and only
#    `stream_scope(True)` takes the streaming route.
#  ★ Why a `ContextVar` instead of a parameter on every call: the crew chain is deep
#    (`Studio.call` -> role implementation -> `llm.replies.ask` -> `llm.chat` ->
#    `_real_call`) and none of those middle functions know about "streaming"; adding a
#    parameter to each would leak a UI concern into the business layer. A `ContextVar`
#    propagates along the `await` chain (parallel subtasks inherit their own copy), so one
#    `set` is enough -- the same mechanism as `llm/usage.set_ctx` and `llm/models.use`.
#  ★ Why "this provider rejects streaming" is **remembered**: `stream_options` is an OpenAI
#    extension and a few compatible gateways answer 400. Once seen, log it and stop trying
#    in this process -- otherwise every single call first wastes a request and the user just
#    sees "the crew got slower".
#: 这一发要不要流式（默认 False = 老路）。
#: [EN] Whether to stream this call (default False = the old path).
_STREAM: contextvars.ContextVar[bool] = contextvars.ContextVar(
    'nws_llm_stream', default=False)

#: 这家服务商被证实**不吃流式**时置 True（进程内一直有效，见上面第 3 条）。
#: [EN] Set True once this provider is proven not to accept streaming (process-wide, see
#: reason 3 above).
_STREAM_BROKEN = [False]


def stream_wanted() -> bool:
    """现在这个上下文要不要流式。**判据与产品共用这一处**。"""
    return bool(_STREAM.get()) and not _STREAM_BROKEN[0]


def stream_broken() -> bool:
    """这家服务商是不是已经被判定"不吃流式"（判据/日志用）。"""
    return bool(_STREAM_BROKEN[0])


def mark_stream_broken(why: str = '') -> None:
    """记下"这家不吃流式"，以后不再试（只记一次日志）。"""
    if _STREAM_BROKEN[0]:
        return
    _STREAM_BROKEN[0] = True
    _LOG.warning('这家模型/网关不接受流式返回（%s）—— 本进程改用整段返回，'
                 '不影响推演，只是展开框里看不到逐字出现的过程', why or '未知原因')


def reset_stream_broken() -> None:
    """清掉"不吃流式"的记忆（换模型 / 判据用）。"""
    _STREAM_BROKEN[0] = False


@contextlib.contextmanager
def stream_scope(on: bool = True):
    """在 `with` 里让所有 LLM 调用走流式（`await` 链上自动生效）。"""
    tok = _STREAM.set(bool(on))
    try:
        yield
    finally:
        try:
            _STREAM.reset(tok)
        except (ValueError, LookupError):
            pass


class _StreamUnsupported(Exception):
    """这家网关不吃流式（`stream` / `stream_options` 被 400 掉）。

    ★ 单独一个异常类型，是为了让 `_real_call` 能**只对这一种**"换回老路重试"，
      而不是把所有 400 都吞掉重来（那样真正的参数错误会被重试掩盖，
      日志里只剩"试了两次都失败"）。
    [EN] This gateway does not accept streaming (`stream` / `stream_options` rejected with
    400). A dedicated type so `_real_call` can "fall back and retry" for **this case only**,
    rather than swallowing every 400 (that would hide real parameter errors behind a retry
    and leave only "both attempts failed" in the log).
    """


def _ooc_from(status: int, text: str, who: dict | None = None) -> CREDIT.OutOfCredit:
    """把"这一发是因为没钱被拒"包成 `OutOfCredit`，并把服务端原话剪一小段带上。

    ⚠ **必须带原话片段**：是不是真的欠费，用户看一眼那句话就能判断
      （有的 403 写的是"这个 Key 没有该模型的权限"，那充钱也没用）。
    ⚠ 片段要**去换行**：模型服务常回一整个 JSON，带换行的那条进中栏会把版面撑散。
    [EN] Wrap "this request was rejected for lack of money" into `OutOfCredit`, carrying a small
    [EN] slice of the server's own words. ⚠ The slice is **required**: the user can tell at a glance
    [EN] whether it is really billing (some 403s say "this key has no access to that model", where
    [EN] topping up will not help). ⚠ Strip newlines: providers often return a whole JSON blob, and a
    [EN] multi-line note would wreck the middle column's layout.
    """
    w = dict(who or {})
    raw = str(text or '')
    snippet = ' '.join(raw.split())
    if len(snippet) > 220:
        snippet = snippet[:220] + '…'
    return CREDIT.OutOfCredit(
        provider=str(w.get('provider') or ''),
        label=str(w.get('label') or ''),
        model=str(w.get('model') or ''),
        purpose=str(w.get('purpose') or ''),
        base_url=str(w.get('base_url') or ''),
        status=int(status or 0),
        detail=snippet,
    )


def _cache_hit_tokens(usage: dict) -> int:
    """从响应的 `usage` 里读出**命中前缀缓存**的输入 token 数（读不出就是 0）。

    ★ 为什么要读它（2026-10-12，用户要求"统计不同模型的费用"）：各家都开始给
      "重复前缀"打折，但**折扣只体现在这两个字段里** —— 不读它们，账本会把
      命中部分也按原价算，于是"明明省了钱却显示花了很多"，用户根本看不出
      缓存有没有生效、要不要继续优化提示词。
    · DeepSeek：`prompt_cache_hit_tokens`（官方明确给的名字）；
    · OpenAI / 兼容实现：`prompt_tokens_details.cached_tokens`。
      两个都查、取大的那个 —— 有的网关会同时给，取大值不会低估省下的量。
    
        English:
    Read the number of **prefix-cache-hit** input tokens from a response's `usage` (0 if
    unreadable).
        ★ Why read it (2026-10-12, the user asked to "count the cost of different models"): every
          provider now discounts repeated prefixes, but **the discount only shows up in these
          fields** -- without reading them the ledger bills the hit portion at full price, so it
          "shows a big spend even though money was saved", and the user cannot tell whether caching
          works or whether to keep optimizing the prompt.
        · DeepSeek: `prompt_cache_hit_tokens` (the official name);
        · OpenAI / compatible implementations: `prompt_tokens_details.cached_tokens`.
          Check both and take the larger -- some gateways report both, and taking the larger never
          underestimates the saving.
    """
    if not isinstance(usage, dict):
        return 0
    vals: list[int] = []
    for key in ('prompt_cache_hit_tokens', 'cache_hit_tokens'):
        v = usage.get(key)
        if isinstance(v, (int, float)):
            vals.append(int(v))
    det = usage.get('prompt_tokens_details')
    if isinstance(det, dict) and isinstance(det.get('cached_tokens'), (int, float)):
        vals.append(int(det['cached_tokens']))
    return max([0, *vals])


def _effective_max_tokens(model: str, purpose: str, requested: int) -> int:
    """这一发请求**实际**用多大的输出上限。

    ★★ 2026-10-10（用户点名）：「就把所有相关的 token 上限都大幅增加，
       尽量让大部分任务不被 token 上限限制（比如按照模型的上限来限制
       而不是手动设置的上限）」。

    这句话有出处。那天真跑一天的 `llm_calls.jsonl` 里：

        day_script    in=3221 out=3998   ← 上限 4000，正好卡住（写了一半）
        day_script    in=3372 out=3998   ← 又一次
        day_summary   in=1439 out=2000   ← 上限 2000，也卡住

    而复盘里"掌柜该给的坦白拍没有落地""剧本重写 4 轮仍被判不通过"，
    根子就在这几条被砍断的输出上。

    问题不是"值设小了"，而是**这个值本来就不该由我们猜** ——
    模型自己知道它能写多长（`capabilities.MAX_OUTPUT_TOKENS`）。

    两种模式（`LLM_TOKEN_BUDGET_MODE`）：

      · `model`（默认）—— 有效上限 = **这个模型自己的上限**
        （查表；认不出这个模型就用 `LLM_MAX_TOKENS_FALLBACK`）。
        调用方传进来的那个数**不再当上限**，它只表达"这次大概要写多少"。
      · `manual` —— 老行为：`调用方给的数 × LLM_TOKEN_SCALE`。
        放大倍数收成一个旋钮，省得为了放宽去改十几个 `*_TOKENS`。

    ⚠ **两条都不许超过模型上限**：表里查得到就封顶在那儿。
      给一个超过模型上限的 `max_tokens`，有的服务是**直接 400**（不是截断）——
      那比"写一半"更糟。所以宁可封顶，剩下的交给下面那道"减半重试"
      （`_looks_like_token_limit_error`）去兜"表猜错了"的情况。
    
        English:
    How large an output cap this request **actually** uses.
        ★★ 2026-10-10 (user called it out): "just greatly increase all the relevant token caps,
           try to keep most tasks from being limited by the token cap (e.g. limit by the model's cap
           rather than a manually set cap)".
        This quote has a source. In that day's actual run of `llm_calls.jsonl`:
            day_script    in=3221 out=3998   <- cap 4000, stuck right there (wrote half)
            day_script    in=3372 out=3998   <- again
            day_summary   in=1439 out=2000   <- cap 2000, also stuck
        And in the retrospective, "the confession shot the shopkeeper should have given never landed" "the script was rewritten 4 rounds and still judged as failing",
        the root cause is right there in these cut-off outputs.
        The problem is not "the value was set too small", it's that **this value should never have been guessed by us** --
        the model itself knows how long it can write (`capabilities.MAX_OUTPUT_TOKENS`).
        Two modes (`LLM_TOKEN_BUDGET_MODE`):
          · `model` (default) -- effective cap = **this model's own cap**
            (look up the table; if the model isn't recognized use `LLM_MAX_TOKENS_FALLBACK`).
            The number passed in by the caller **is no longer treated as a cap**; it only expresses "roughly how much will be written this time".
          · `manual` -- old behavior: `caller-supplied number × LLM_TOKEN_SCALE`.
            The scale factor is consolidated into one knob, so you don't have to edit a dozen `*_TOKENS` just to loosen it.
        ⚠ **Neither may exceed the model limit**: if it's found in the table, cap it there.
          Giving a `max_tokens` that exceeds the model limit: some services **return 400 outright** (not truncation) ——
          that's worse than "writing half". So better to cap, and leave the rest to the "halve and retry" below
          (`_looks_like_token_limit_error`) to cover the case where "the table guessed wrong".
    """
    cap = int(requested or 2000)
    limit = max_output_tokens(model)
    mode = (CFG.s("LLM_TOKEN_BUDGET_MODE") or "model").strip().lower()
    if mode == "manual":
        try:
            cap = int(cap * CFG.f("LLM_TOKEN_SCALE"))
        except Exception:                                        # noqa: BLE001
            pass
    else:
        try:
            cap = int(limit or CFG.i("LLM_MAX_TOKENS_FALLBACK"))
        except Exception:                                        # noqa: BLE001
            # ★ 2026-10-14：硬编码兜底跟着提到 819200（与 `LLM_MAX_TOKENS_FALLBACK`
            #   的默认值一致）—— 同一个"过时的 8192"在仓库里出现三处
            #   （模型表 / 配置 / 这里），漏一处就会在最不该掉链子的异常分支上退回旧值。
            # [EN] ★ 2026-10-14: the hard-coded backstop also moves to 819200 (matching the
            # [EN] `LLM_MAX_TOKENS_FALLBACK` default) -- the same "outdated 8192" appeared in three
            # [EN] places (model table / config / here); missing one would fall back to the old value
            # [EN] in exactly the exception branch that must not fail.
            cap = int(limit or 819200)
    if limit:                       # 认得出模型 ⇒ 一律封顶在它自己的上限内
    # [EN] If the model is recognized ⇒ always cap within its own limit
        cap = min(cap, int(limit))
    return max(1, cap)


def _looks_like_token_limit_error(err: Exception) -> bool:
    """这个报错是不是"你给的 `max_tokens` 太大了"。

    ★ 为什么需要它：`_effective_max_tokens` 里那张模型上限表**是猜的**
      （各家的值不一样，同一个模型名在不同供应商后面也可能不一样）。
      猜大了不是"写得短"，而是**整发请求被拒**。
      ⇒ 认出来之后把上限减半重试，于是"猜错"最多贵一次调用。

    口径刻意宽：只在**响应体里出现和长度有关的字样**时才算，不去猜状态码 ——
    400 也可能是"模型名写错了"，那种情况减半重试只是白烧一次，还掩盖了真错。
    
        English:
    Whether this error is "the `max_tokens` you gave is too large".
        ★ Why it's needed: the model limit table inside `_effective_max_tokens` **is a guess**
          (values differ across providers, and the same model name behind different vendors may also differ).
          Guessing too high isn't "writing shorter", it's **the entire request being rejected**.
          ⇒ After recognizing it, halve the limit and retry, so "guessing wrong" costs at most one extra call.
        Deliberately broad criterion: only counted when **length-related wording appears in the response body**, without guessing at the status code ——
        400 could also be "the model name is misspelled"; in that case halving and retrying just burns an extra call and masks the real error.
    """
    text = str(err or '').lower()
    if not text:
        return False
    keys = ('max_tokens', 'max_completion_tokens', 'max output', 'maximum context',
            'too many tokens', 'length limit', 'exceed', 'invalid_request_error')
    return any(k in text for k in keys)


THINKING_MODES = ("auto", "off", "always")


def resolve_no_think(*, purpose: str, learned: bool = False,
                     explicit: bool | None = None,
                     mode: str | None = None) -> bool:
    """这一发请求**想不想**关思考（**不含**"能不能关"的两道闸）。

    ★★★ 2026-10-18 抽出来的唯一实现。为什么必须只有一个地方：
      这个判断同时被 `chat()`（真的发不发参数）和判据（`verify_thinking_mode`）
      用；两处各写一遍，迟早变成"界面上写着关、请求里还开着"这类看不见的病。
      以前它散在 `chat()` 里（`if no_think is None: ...`），加总开关时无处落脚。

    三种来源，优先级从高到低：
      1. `explicit` —— 调用方点名（`no_think=True/False`）；
      2. `mode` —— 用户的总开关（`LLM_THINKING_MODE`）：`off` 一律想关、
         `always` 一律想开，两者都**盖过** `explicit`（这是"一律"的意思）；
      3. 老规矩 —— 用途在 `NO_THINK_PURPOSES` 里，或这个 (模型, 用途) 学过要关。

    ⚠ 返回值只是"想不想"。真正发 `thinking:{"type":"disabled"}` 之前还要过
      `LLM_CAP_THINKING` 与 `detect_thinking_switch(model)` 两道闸 ——
      给 o1 / Claude 发这个参数会直接 400，省钱的开关不能替那条红线做主。

        English:
    Whether this request **wants** thinking off (**excluding** the two "can it be turned off"
    gates).
        ★★★ Extracted 2026-10-18 as the single implementation. Why it must live in one place:
          this decision is used both by `chat()` (whether the parameter is actually sent) and by the
          criteria (`verify_thinking_mode`); two copies drift into invisible diseases like "the UI
          says off while the request still has it on". It used to be inline in `chat()`
          (`if no_think is None: ...`), which left no place to hang the master switch.
        Three sources, highest priority first:
          1. `explicit` -- the caller's choice (`no_think=True/False`);
          2. `mode` -- the user's master switch (`LLM_THINKING_MODE`): `off` always wants it off,
             `always` always wants it on; both **override** `explicit` (that is what "always" means);
          3. the old rule -- the purpose is in `NO_THINK_PURPOSES`, or this (model, purpose) learned
             to disable it.
        ⚠ The return value is only "wants". Actually sending `thinking:{"type":"disabled"}` still
          has to pass `LLM_CAP_THINKING` and `detect_thinking_switch(model)` -- sending it to
          o1 / Claude returns 400 outright, and a money-saving switch must not overrule that.
    """
    if explicit is None:
        want = (purpose in NO_THINK_PURPOSES) or bool(learned)
    else:
        want = bool(explicit)
    m = (mode if mode is not None else (CFG.s("LLM_THINKING_MODE") or "auto"))
    m = str(m).strip().lower()
    if m not in THINKING_MODES:      # 手改 `.env` 写错 ⇒ 当 auto，别静默变成"一律关"
        m = "auto"
    if m == "off":
        return True
    if m == "always":
        return False
    return want


def should_auto_no_think_retry(*, empty: bool, no_think: bool,
                               has_reasoning: bool, model: str) -> bool:
    """「正文为空、而且额度确实是被思考吃掉的」→ 该不该**关掉思考重试一次**。

    ★★ 一处实现（2026-10-07 抽出来）：这个判断有两处要用 ——
      ① `_real_call` 里"要不要在事件上标 `auto_retry`"（界面据此**不再报假警**，
         见 `gui/app_flet.py` 的 `on_llm`）；
      ② `chat()` 里"要不要真的关思考重试"。

    两处各写一遍迟早会漂 —— 而漂的方向恰恰是用户报的那个病：
    **标记说会重试、实际不重试**（或者反过来），
    于是界面上报了一堆"正文为空"的红字，而其中每一次其实都被救回来了。
    用户 2026-10-07 的日志里，这个自愈触发了 **101 次、失败 0 次**。

    ⚠ 只在**这次没关思考**时才试：已经关了还是空，说明病不在思考，
      再关一次只是浪费（那种情况 `_real_call` 会照旧记 warning）。
    
        English:
    "Body is empty, and the quota was indeed eaten by thinking" → whether to **disable thinking and
    retry once**.
        ★★ One implementation (extracted 2026-10-07): this judgment is needed in two places ——
          ① In `_real_call`, "whether to mark `auto_retry` on the event" (the UI thereby **stops raising false alarms**,
             see `on_llm` in `gui/app_flet.py`);
          ② In `chat()`, "whether to actually disable thinking and retry".
        Writing it twice in two places will drift sooner or later —— and the direction of drift is exactly the disease the user reported:
        **the marker says it will retry, but it doesn't actually retry** (or vice versa),
        so the UI reports a pile of red "empty body" text, while every one of them was actually rescued.
        In the user's 2026-10-07 log, this self-healing triggered **101 times, with 0 failures**.
        ⚠ Only try when **thinking wasn't disabled this time**: if it's already disabled and still empty, the disease isn't thinking,
          disabling again is just waste (in that case `_real_call` records a warning as usual).
    """
    return (CFG.b('LLM_NO_THINK_RETRY') and empty and not no_think
            and has_reasoning and CFG.b(CAP_THINKING)
            and detect_thinking_switch(model) is True)


@dataclass
class UsageRecord:
    ts: float
    tier: str
    model: str
    purpose: str
    in_tok: int
    out_tok: int
    cost: float
    latency_ms: int
    #: 这次输入里**命中前缀缓存**的 token 数（2026-10-12 加；0 = 没命中或对方不报）。
    # [EN] : how many input tokens **hit the prefix cache** this time (added 2026-10-12; 0 = no hit
    # [EN] or the provider doesn't report it).
    cache_tok: int = 0


@dataclass
class Ledger:
    """Token 经济账本：按日/累计/分模型/分用途统计。
        English:
    Token economy ledger: stats by day/cumulative/by model/by purpose.
    """
    records: list[UsageRecord] = field(default_factory=list)
    #: 单价覆盖表。值可以是 `(未命中, 输出)`（老写法）或 `(命中, 未命中, 输出)`
    #: —— 具体解析在 `llm/tokens.py::price_of`，这里只存不解释。
    # [EN] : unit-price override table. A value may be `(miss, output)` (old form) or
    # [EN] `(hit, miss, output)` -- parsing lives in `llm/tokens.py::price_of`; this only stores it.
    overrides: dict[str, tuple] = field(default_factory=dict)

    def add(self, rec: UsageRecord) -> None:
        self.records.append(rec)
        # ★★ 2026-10-10：**同时落进全局台账库**（用户第二个需求）。
        #   为什么要在这一处接（而不是在每个调用方接）：`Ledger.add` 是
        #   **所有 LLM 调用的唯一汇合点** —— 在这儿接一次，全项目每一次调用
        #   都自动记账，一个都漏不掉。在调用方接的话，新加的用途迟早会忘。
        #   ⚠ 落库在 `llm/usage` 内部**自己吞异常**（旁路不该变成故障源），
        #     这里再包一层是为了防 import 本身出问题。
        # [EN] ★★ 2026-10-10: **also write into the global ledger DB** (the user's second requirement).
        # [EN] Why hook in at this one place (instead of at each caller): `Ledger.add` is
        # [EN] **the single convergence point of all LLM calls** - hook once here, and every call in the whole
        # [EN] project
        # [EN] is automatically accounted for, not one is missed. Hooking at the caller, newly added uses will
        # [EN] eventually be forgotten.
        # [EN] ⚠ The DB write **swallows exceptions itself** inside `llm/usage` (a side path should not become
        # [EN] a failure source),
        # [EN] wrapping another layer here is to guard against problems with the import itself.
        try:
            from llm import usage as USAGE
            USAGE.record(model=rec.model, purpose=rec.purpose, in_tok=rec.in_tok,
                         out_tok=rec.out_tok, cost=rec.cost, tier=rec.tier,
                         ts=rec.ts, cache_tok=rec.cache_tok)
        except Exception:                                        # noqa: BLE001
            pass

    @property
    def today_tokens(self) -> int:
        today = date.today().toordinal()
        return sum(r.in_tok + r.out_tok for r in self.records
                   if date.fromtimestamp(r.ts).toordinal() == today)

    @property
    def today_cost(self) -> float:
        today = date.today().toordinal()
        return sum(r.cost for r in self.records
                   if date.fromtimestamp(r.ts).toordinal() == today)

    def cost_by_model(self) -> dict[str, float]:
        d: dict[str, float] = {}
        for r in self.records:
            d[r.model] = d.get(r.model, 0) + r.cost
        return d

    def cost_by_purpose(self) -> dict[str, float]:
        d: dict[str, float] = {}
        for r in self.records:
            d[r.purpose] = d.get(r.purpose, 0) + r.cost
        return d


class LLM:
    """异步 LLM 客户端，OpenAI 兼容协议。mock 模式零网络调用。
        English:
    Async LLM client, OpenAI-compatible protocol. In mock mode, zero network calls.
    """

    def __init__(self):
        self.ledger = Ledger(overrides=parse_overrides(CFG.s("MODEL_PRICE_OVERRIDES")))
        self._client: httpx.AsyncClient | None = None
        self._sem: asyncio.Semaphore | None = None
        self._budget_warn_cb: Callable[[float], None] | None = None
        self._log_dir: Path | None = None
        self._listeners: list[Callable[[dict], None]] = []
        self._started = False
        self._loop = None
        #: ★ **学会的「这个用途不用思考」**（2026-10-07）：`{(model, purpose)}`。
        # [EN] : ★ **learned "this use doesn't need thinking"** (2026-10-07): `{(model, purpose)}`.
        #
        #  用户 2026-10-07 报：「[23:30:00] ⚠ 正文为空（撞到 max_tokens=2400…）
        #  **这一直在报错** 这个要怎么修复」。查真实日志：自愈触发 **101 次**、
        #  自愈失败 **0 次** —— 也就是**每次都救回来了**，但代价是：
        #    · 每一发都白烧一次（那次思考把 2400~4000 的额度整份吃掉）；
        #    · 作者看到一排红字，以为坏了。
        #  这里记下来：某个 (模型, 用途) 一旦靠"关掉思考"救回来过，
        #  以后**直接关着思考发**，那一发就不再白烧。
        # [EN] User reported on 2026-10-07: "[23:30:00] ⚠ Body text is empty (hit max_tokens=2400...)
        # [EN] **this keeps erroring** how do I fix this". Checked the real logs: self-heal triggered **101
        # [EN] times**,
        # [EN] self-heal failed **0 times** - i.e. **it was saved every time**, but the cost is:
        # [EN] · every shot burns one wasted round (that thinking ate the whole 2400~4000 quota);
        # [EN] · the author sees a row of red text and thinks it's broken.
        # [EN] Noting it here: once a given (model, purpose) has been saved by "disabling thinking",
        # [EN] from then on **send directly with thinking disabled**, and that shot no longer burns a wasted
        # [EN] round.
        #
        #  ⚠ 只记在**内存**里（每次重启清空）。为什么不做持久化：
        #    换模型 / 升级模型之后，这个结论很可能就不再成立
        #    （新模型也许思考得很省），留着旧结论等于把一个过时的判断钉死。
        #    每次启动重验一遍，代价是每个用途最多白烧一发 —— 换来的是
        #    "结论永远对得上当前模型"。
        # [EN] ⚠ Only recorded **in memory** (cleared on every restart). Why not persist:
        # [EN] after switching models / upgrading models, this conclusion very likely no longer holds
        # [EN] (the new model may think very frugally), keeping the old conclusion is like nailing down an
        # [EN] outdated judgment.
        # [EN] Re-verifying once on every startup costs at most one wasted shot per use - in exchange for
        # [EN] "the conclusion always matches the current model".
        self._no_think_learned: set[tuple[str, str]] = set()

    def learned_no_think(self) -> set[tuple[str, str]]:
        """已经学会"这个 (模型, 用途) 不用思考"的集合（只读，给判据/排查用）。
                English:
        The set that has learned "this (model, purpose) doesn't need thinking" (read-only, for
        criteria/troubleshooting).
        """
        return set(self._no_think_learned)

    # ── 事件监听（GUI 实时展示 LLM 对话过程）──
    # [EN] ── Event listening (GUI shows the LLM conversation process in real time) ──
    def add_listener(self, cb: Callable[[dict], None]) -> None:
        """注册一个事件回调，收到 dict 事件（request / response / error）。

        回调必须**立即返回**（只做入队等轻量操作），不要在其中 await 或做耗时工作。
        
                English:
        Register an event callback, receiving dict events (request / response / error).
                The callback must **return immediately** (only do lightweight work like enqueuing), don't await or do time-consuming work inside it.
        """
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[dict], None]) -> None:
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    def _emit(self, event: dict) -> None:
        # ① **先落盘**（对话日志）：这一步与监听者无关，所以
        #    "GUI 没开 / 界面上的日志被截断 / 调用方是脚本"都不影响留档。
        #    2026-10-05 用户要求「所有的对话也需要放到日志里」——
        #    此前请求/响应只在 `DEBUG_MODE` 下才进主日志，且**截断**（200/500 字），
        #    界面上那几行又只活在内存里（`_add_log` 截到 700/1200 字）。
        # [EN] ① **Persist to disk first** (conversation log): this step is independent of listeners, so
        # [EN] "GUI not open / on-screen log truncated / caller is a script" none of these affect the archival.
        # [EN] On 2026-10-05 the user requested "all conversations also need to go into the log" -
        # [EN] previously request/response only went into the main log under `DEBUG_MODE`, and **truncated**
        # [EN] (200/500 chars),
        # [EN] and those few lines on the UI only lived in memory (`_add_log` truncated to 700/1200 chars).
        try:
            self._log_dialogue(event)
        except Exception:                                   # noqa: BLE001
            pass
        # ② 再广播给监听者（GUI 实时展示）
        # [EN] ② Then broadcast to listeners (GUI real-time display)
        for cb in list(self._listeners):
            try:
                cb(event)
            except Exception:
                pass

    def _log_dialogue(self, event: dict) -> None:
        """把一次 LLM 交换写进对话日志（全文，不截断）。
                English:
        Write one LLM exchange into the conversation log (full text, no truncation).
        """
        from logger import log_dialogue
        kind = event.get('type')
        purpose = event.get('purpose') or ''
        if kind == 'request':
            msgs = event.get('messages') or []
            lines = [f'── 第 {i + 1}/{len(msgs)} 条 · {m.get("role", "?")} ──\n'
                     f'{m.get("content", "")}'
                     for i, m in enumerate(msgs)]
            log_dialogue(
                'LLM 请求', '\n\n'.join(lines),
                f'tier={event.get("tier")} · model={event.get("model")} · '
                f'purpose={purpose} · {len(msgs)} 条消息'
                + ('（MOCK 演示模式，未联网）' if CFG.mock else ''))
        elif kind == 'response':
            log_dialogue(
                'LLM 响应', str(event.get('text') or ''),
                f'model={event.get("model")} · purpose={purpose} · '
                f'{event.get("tin")}+{event.get("tout")} token · '
                f'{event.get("cost", 0):.5f} · {event.get("ms")}ms')
        elif kind == 'error':
            log_dialogue(
                'LLM 调用失败',
                str(event.get('error') or ''),
                f'尝试 {event.get("attempt")}/{event.get("retries")} · '
                f'model={event.get("model")} · purpose={purpose}')

    async def start(self, log_dir: Path | None = None) -> None:
        if log_dir:
            self._log_dir = log_dir
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._sem = asyncio.Semaphore(max(1, CFG.i("LLM_MAX_CONCURRENCY")))
        if not CFG.mock:
            # ★★ 2026-10-12：**不再把地址与密钥焊死在客户端上**。
            #   登记表里每条模型可以来自**不同服务商**（混元 Hy3 / DeepSeek / Claude…），
            #   地址与密钥是**每一发请求**按 Agent 解析出来的，所以客户端只做
            #   "一个连接池"，目标 URL 与 `Authorization` 头在 `_real_call` 里逐发传。
            #   ⚠ 老行为没丢：登记表为空时解析结果仍是旧的全局地址与密钥。
            # [EN] ★★ 2026-10-12: **no longer weld the endpoint and key onto the client**.
            # [EN] Each model in the registry may come from a **different provider** (Hunyuan Hy3 /
            # [EN] DeepSeek / Claude...), and the endpoint and key are resolved **per request** by
            # [EN] Agent, so the client is just "a connection pool"; the target URL and the
            # [EN] `Authorization` header are passed per request in `_real_call`.
            # [EN] ⚠ The old behaviour is preserved: when the registry is empty, resolution still
            # [EN] yields the old global endpoint and key.
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(CFG.i("LLM_TIMEOUT_SECONDS"), connect=10),
            )
        self._started = True
        self._loop = asyncio.get_running_loop()
        _LOG.info("LLM 启动: mock=%s, 并发=%d", CFG.mock, CFG.i("LLM_MAX_CONCURRENCY"))

    async def ensure_started(self, log_dir: Path | None = None) -> None:
        """按需启动（幂等）。GUI 首次调用 LLM 前调用即可。

        绑定到当前事件循环；若换到另一个 loop（多见于测试），则重建客户端与信号量。
        
                English:
        Start on demand (idempotent). Just call it before the GUI's first LLM call.
                Bind to the current event loop; if switched to another loop (common in tests), rebuild the client and semaphore.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._started and self._loop is loop:
            if log_dir:
                self._log_dir = log_dir
            return
        await self.start(log_dir)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._started = False
        self._loop = None

    # ── 核心调用 ──
    # [EN] ── Core call ──
    async def chat(
        self,
        tier: str,
        messages: list[dict],
        *,
        purpose: str = "",
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: float | None = None,
        return_meta: bool = False,
        no_think: bool | None = None,
    ):
        """调用 LLM 并返回文本。tier = front / daily / cheap。

        请求体按 `LLM_CAP_*`（模型能力，见 `llm/capabilities.py`）组装 ——
        能力开关说这个模型能干什么，这里就照着发什么参数：
          · JSON 模式关掉 → 退回「末尾追加『请仅以 JSON 回答』」的老办法；
          · 推理模型     → 不发 temperature（deepseek-reasoner 这类会拒绝）；
          · 不认 system  → 把系统提示并入首条 user 消息；
          · 能关思考     → 「结论型」用途带 `thinking:{"type":"disabled"}`。

        `no_think`：`True` = 这次请求关掉思考；`False` = 强制不关；
        **`None`（默认）= 按 `NO_THINK_PURPOSES` 自己判**。三种都只在
        `LLM_CAP_THINKING` 说这个模型支持时才真的发出去 —— 不认识这个参数的
        模型（o1 / o3 / Claude…）收到它可能直接 400。

        `return_meta=True` 时返回 `(文本, 元信息)`，元信息里有 **`truncated`** ——
        「输出被 `max_tokens` 截断了吗」。**长文/JSON 的调用方应该打开它**：
        2026-10-06 的事故就是"提取设定"被截在半句话里，而调用方拿不到任何信号，
        只好把整份设定集降级成空骨架（见 `util/jsonio.repair_json`）。
        ⚠ 默认关（29 处 `llm.chat()` 都按字符串用），改签名会一次性炸一片。
        
                English:
        Call the LLM and return text. tier = front / daily / cheap.
                Assemble the request body per `LLM_CAP_*` (model capabilities, see `llm/capabilities.py`) ——
                the capability switches say what this model can do, and here we send parameters accordingly:
                  · JSON mode off → fall back to the old trick of "appending 'please answer in JSON only' at the end";
                  · Reasoning model     → don't send temperature (deepseek-reasoner and the like will reject it);
                  · Doesn't accept system  → merge the system prompt into the first user message;
                  · Can disable thinking     → "conclusion-type" purposes carry `thinking:{"type":"disabled"}`.
                `no_think`: `True` = disable thinking for this request; `False` = force it on;
                **`None` (default) = decide yourself based on `NO_THINK_PURPOSES`**. All three only actually
                get sent when `LLM_CAP_THINKING` says the model supports it -- models that don't recognize
                this parameter (o1 / o3 / Claude...) may return a 400 immediately.
                When `return_meta=True`, returns `(text, meta)`, and meta contains **`truncated`** --
                "was the output cut off by `max_tokens`". **Callers doing long-form/JSON should enable it**:
                the 2026-10-06 incident was exactly "setting extraction" being cut off mid-sentence, with the caller
                getting no signal at all, so it had to downgrade the whole setting collection to an empty skeleton (see `util/jsonio.repair_json`).
                ⚠ Off by default (all 29 call sites of `llm.chat()` use it as a string); changing the signature would blow up everything at once.
        """
        # ★★ 2026-10-12：**这一发到底用哪个模型**由登记表解析（唯一入口
        #   `llm/models.resolve()`）—— 顺序是「Agent 点名 → 它的档位 → 默认 → 第一条」，
        #   一条都没有时退回老路（全局地址 + `CFG.model_of(tier)`）。
        #   解析结果**同时**给出发给服务端的模型名、目标地址、密钥与能力开关：
        #   因为登记表里的条目可以来自不同服务商，这四样必须**成套**取用。
        # [EN] ★★ 2026-10-12: **which model this request actually uses** is resolved by the
        # [EN] registry (the single entry point `llm/models.resolve()`) -- the order is
        # [EN] "Agent named one -> its tier -> default -> first entry", and when there are none it
        # [EN] falls back to the old path (global endpoint + `CFG.model_of(tier)`).
        # [EN] The resolution **also** yields the model name sent to the server, the target
        # [EN] endpoint, the key and the capability switches: because entries may come from
        # [EN] different providers, these four must be taken **as a set**.
        _res = MODELS.resolve(tier=tier)
        if _res is None:
            model = CFG.model_of(tier)
            caps = {k: CFG.b(k) for k in CAP_KEYS}
        else:
            model = _res.model
            caps = {k: bool(_res.caps.get(k, CFG.b(k))) for k in CAP_KEYS}
        use_json_mode = bool(json_mode) and caps[CAP_JSON]
        # ★★ **输出上限改由模型自己决定**（2026-10-10，用户点名）。
        #   见 `_effective_max_tokens` 与 `capabilities.MAX_OUTPUT_TOKENS`
        #   里的说明：那天两次 `out=3998`（上限 4000）就是被"人猜的额度"砍断的。
        # [EN] ★★ **Output limit is now decided by the model itself** (2026-10-10, called out by the user).
        # [EN] See `_effective_max_tokens` and the explanation in `capabilities.MAX_OUTPUT_TOKENS`:
        # [EN] that day's two `out=3998` (limit 4000) were cut off by the "human-guessed quota".
        max_tokens = _effective_max_tokens(model, purpose, max_tokens)
        # ★ 「学会的不用思考」也参与判定（2026-10-07）：某个 (模型, 用途)
        #   靠关思考救回来过 → 以后直接关着发，不再白烧首发。
        # [EN] ★ "learned not to think" also participates in the decision (2026-10-07): a given (model,
        # [EN] purpose)
        # [EN] Recovered by turning thinking off -> from now on just send with it off, no more burning the
        # [EN] first shot for nothing.
        learned = (model, purpose) in self._no_think_learned
        # ★★★ 2026-10-18：**唯一实现**在 `resolve_no_think()`（含总开关 `LLM_THINKING_MODE`）。
        #   以前这三行内联在这儿，加总开关时无处落脚；抽出去之后判据能直接测它。
        # [EN] ★★★ 2026-10-18: **the single implementation** lives in `resolve_no_think()`
        # [EN] (master switch `LLM_THINKING_MODE` included). It used to be inline here, leaving no
        # [EN] place for the switch; extracted so the criteria can test it directly.
        no_think = resolve_no_think(purpose=purpose, learned=learned, explicit=no_think)
        # 两道闸，缺一不可：
        #   ① `LLM_CAP_THINKING` —— **用户总开关**（设置界面里能关掉，
        #      比如他觉得关掉思考之后判定质量下降）；
        #   ② `detect_thinking_switch(本次模型)` —— **按这一发请求用的模型再确认**。
        #      三档常常配不同模型，闸门必须落到"这一次要用谁"上：
        #      给 o1 / Claude 发 `thinking` 会直接 400，光看全局开关挡不住。
        # [EN] Two gates, both required:
        # [EN] ① `LLM_CAP_THINKING` -- **the user's master switch** (can be turned off in the settings UI,
        # [EN] e.g. if they think judgment quality drops after turning thinking off);
        # [EN] ② `detect_thinking_switch(this request's model)` -- **re-confirm based on the model used for
        # [EN] this particular request**.
        # [EN] The three tiers often use different models, so the gate must land on "who is being used this
        # [EN] time":
        # [EN] Sending `thinking` to o1 / Claude returns a 400 outright; the global switch alone can't stop it.
        no_think = (bool(no_think) and caps[CAP_THINKING]
                    and detect_thinking_switch(model) is True)
        # ⚠ **自己把客户端建起来**，别指望调用方记得先 `ensure_started()`。
        # 2026-10-05 踩的坑：推演路径（`sim/loop.py`）从来没调过 `ensure_started`，
        # 而 `_real_call` 开头是一句 `assert self._sem and self._client` ——
        # 于是每一次「人物决策」都在 assert 上炸掉，被 `Agent.decide` 的
        # `except Exception` 吞掉降级成 `wait`，屏幕上就是**满屏「没动，也没出声」**：
        # 8 秒跑了 550 次"决策"，`llm_calls.jsonl` 里**一次 agent_decide 都没有**。
        # [EN] ⚠ **Build the client yourself**, don't expect the caller to remember to `ensure_started()`
        # [EN] first.
        # [EN] Pitfall hit on 2026-10-05: the simulation path (`sim/loop.py`) never called `ensure_started`,
        # [EN] and `_real_call` starts with `assert self._sem and self._client` --
        # [EN] so every "character decision" blew up on the assert and was swallowed by `Agent.decide`'s
        # [EN] `except Exception`, degrading to `wait`; on screen it was **a screen full of "didn't move,
        # [EN] didn't speak"**:
        # [EN] 550 "decisions" in 8 seconds, and `llm_calls.jsonl` had **not a single agent_decide**.
        await self.ensure_started()
        # ★ 「输出语言」在**这个漏斗里**统一注入 —— 见 `_inject_output_lang()`。
        #   ⚠ 顺序要紧：必须在 `_ensure_json_instruction` **之前**，
        #   否则会把「请仅以 JSON 回答」那句挤到语言指令前面去（JSON 提示要留在最后）。
        # [EN] ★ "Output language" is injected uniformly **inside this funnel** -- see `_inject_output_lang()`.
        # [EN] ⚠ Order matters: it must come **before** `_ensure_json_instruction`,
        # [EN] otherwise it pushes the "please answer in JSON only" sentence ahead of the language instruction
        # [EN] (the JSON hint must stay last).
        messages = _inject_output_lang(messages, purpose)
        if not caps[CAP_JSON] and json_mode:
            messages = _ensure_json_instruction(messages)
        if not caps[CAP_SYSTEM]:
            messages = _merge_system_into_user(messages)
        # 广播请求事件（GUI 用它实时展示「完整优化过程」）
        # [EN] Broadcast request event (the GUI uses it to show the "full optimization process" in real time)
        self._emit({"type": "request", "tier": tier, "model": model,
                    "model_key": (getattr(_res, 'key', '') if _res else ''),
                    "purpose": purpose, "messages": messages,
                    "no_think": no_think})
        # ★★ 2026-10-12：**同题复用**（省钱的第一招）。
        #   完全相同的输入 + 模型 + 参数，在保质期内再问一次 → 直接返回上次的答案：
        #   不发请求、不占额度、不花钱，而结果仍然是**对的**（不是拿旧结论顶上现在的局面，
        #   而是"这个问题本来就问过、答案本来就该一样"）。
        #   ⚠ 只对白名单用途生效（判定 / 抽取 / 校对）—— 说话、写正文、起名**绝不缓存**。
        #   注意 `messages` 到这里已经最终化（语言注入、JSON 指令、system 合并都做完了），
        #   所以 key 覆盖的是**真正发给服务端的那份内容**。
        # [EN] ★★ 2026-10-12: **same-question reuse** (money saver #1).
        # [EN] An identical input + model + parameters asked again within its shelf life returns the
        # [EN] previous answer directly: no request, no quota, no money -- and the result is still
        # [EN] **correct** (not "an old conclusion overriding the current situation", but "this
        # [EN] question was already asked and its answer should be the same").
        # [EN] ⚠ Only whitelisted purposes apply (judging / extraction / proofreading) -- speech,
        # [EN] prose and naming are **never cached**.
        # [EN] Note `messages` is final by now (language injection, JSON instruction and system
        # [EN] merging are all done), so the key covers **what is actually sent to the server**.
        _dkey: str | None = None
        if not CFG.mock:
            try:
                from llm import dedup as _DEDUP
                _dkey = _DEDUP.key_for(model=model, purpose=purpose, messages=messages,
                                       temperature=temperature, max_tokens=max_tokens,
                                       json_mode=use_json_mode, no_think=no_think)
                if _dkey:
                    _hit = _DEDUP.get(_dkey)
                    # ★★★ 2026-10-19：内存没命中 ⇒ **再问一次跨进程共享缓存**（`llm/cache.py`）。
                    #   为什么需要第二层：主程序与三个外挂是**不同进程**，进程内那张表
                    #   它们互相看不见；共享层是一个 sqlite 文件，谁都能读。
                    #   顺带它还能**跨会话**（重启后仍在保质期内就直接给，不用再花钱）。
                    #   ⚠ 顺序不能反：内存是纳秒级、磁盘是毫秒级，而这条路上每拍都问一次。
                    #     先磁盘后内存 = 每一拍都多一次 sqlite 打开（实测那正是"不值得"的写法）。
                    #   ⚠ 磁盘这一层**只读不写统计**（写进的是 `dedup` 的计数器吗？不是 ——
                    #     各记各的：`dedup.stats()` 代表"内存省了几发"，`cache.stats()`
                    #     代表"磁盘省了几发"，两个数不能混一个）。
                    # [EN] ★★★ 2026-10-19: memory miss => **ask the cross-process shared cache**
                    # [EN] (`llm/cache.py`). Why a second layer: the main program and the three
                    # [EN] external services are **different processes**, and an in-process table is
                    # [EN] invisible across them; the shared layer is a sqlite file anyone can read.
                    # [EN] It also survives restarts (still within TTL => no new spend).
                    # [EN] ⚠ Order must not be reversed: memory is ns, disk is ms, and this path is
                    # [EN] asked every beat -- disk first would open sqlite each beat (measured: the
                    # [EN] "not worth it" pattern this project has calculated before).
                    # [EN] ⚠ The disk layer keeps its own counters; `dedup.stats()` means "saved in
                    # [EN] memory", `cache.stats()` means "saved on disk" -- never merge the two.
                    if _hit is None:
                        try:
                            from llm import cache as _SHARED
                            _hit = _SHARED.get(_dkey)
                            if _hit is not None:
                                # 从磁盘命中也回填进内存，下一次就是纳秒级
                                # [EN] A disk hit is written back to memory so the next one is ns.
                                _DEDUP.put(_dkey, _hit)
                                self._emit({"type": "cache_shared", "purpose": purpose,
                                            "model": model})
                        except Exception as _e:                  # noqa: BLE001
                            _LOG.debug('共享缓存查询失败（照常发请求）：%r', _e)
                    if _hit is not None:
                        self._emit({"type": "response", "tier": tier, "model": model,
                                    "purpose": purpose, "text": _hit,
                                    "tin": 0, "tout": 0, "cost": 0.0, "ms": 0,
                                    "finish_reason": "dedup", "truncated": False,
                                    "has_reasoning": False, "empty_output": False,
                                    "no_think": no_think, "auto_retry": False,
                                    "max_tokens": max_tokens, "dedup": True})
                        if return_meta:
                            return _hit, {"model": model, "tier": tier, "purpose": purpose,
                                          "finish_reason": "dedup", "truncated": False,
                                          "in_tok": 0, "out_tok": 0, "cost": 0.0,
                                          "dedup": True, "has_reasoning": False,
                                          "empty_output": False}
                        return _hit
            except Exception as e:                               # noqa: BLE001
                _dkey = None
                _LOG.debug('同题复用检查失败（照常发请求）：%r', e)
        if CFG.mock:
            text, meta = await self._mock_call(messages, purpose, model, max_tokens)
        else:
            text, meta = await self._real_call(
                tier, model, messages, purpose, temperature=temperature,
                max_tokens=max_tokens, timeout=timeout, json_mode=use_json_mode,
                no_think=no_think, res=_res, caps=caps)
            # ★★ **额度被思考吃光 → 关掉思考重试一次**（2026-10-07 加）。
            # [EN] ★★ **Quota eaten up by thinking -> turn thinking off and retry once** (added 2026-10-07).
            #
            # 为什么要有这一步：真模型（deepseek-flash / v4-*) 默认**思考**，而
            # 思考**连 `max_tokens` 一起吃**。2026-10-07 真跑两天推演时实测到
            # **九处**「正文一个字符都没拿到」—— 后果不是"少一条产出"，
            # 是**功能整块报废**：
            #   · `crew_day_map` 挂了 → 当天地图从来没画出来；
            #   · `day_verify`  挂了 → 导演验算永远拿不到结论，只能带空意见重写；
            #   · `day_summary` 挂了 → 当天的摘要没有 → **第二天前情提要就空**；
            # [EN] Why this step: real models (deepseek-flash / v4-*) **think** by default, and
            # [EN] thinking **eats `max_tokens` too**. On 2026-10-07, running the simulation for two real days, we
            # [EN] measured
            # [EN] **nine** cases of "not a single character of body text" -- the consequence isn't "one less
            # [EN] output",
            # [EN] it's **an entire feature being scrapped**:
            # [EN] · `crew_day_map` died -> that day's map was never drawn;
            # [EN] · `day_verify` died -> the director's verification never got a conclusion, and could only
            # [EN] rewrite with empty comments;
            # [EN] · `day_summary` died -> no summary for that day -> **the next day's recap is empty**;
            #   · `crew_research` / `crew_continuity` / `crew_props` / `crew_publicity`
            #     都挂了 → 资料员/场记/道具/宣发 天天报"没出活"。
            # [EN] all dead -> archivist/continuity/props/marketing report "no work produced" every day.
            #
            # 「把这个 purpose 的 max_tokens 调大」是**逐个调**的体力活，而且
            # 治不了本：模型换个档、提示词长一点，又会不够。这里改成**自愈** ——
            # 只有在"正文为空且确实带着思考"（= 额度确实花在思考上了）时才触发，
            # 代价是**多一次调用**，而那一发本来就白扔了。
            # [EN] "Increase max_tokens for this purpose" is **one-by-one** manual labor, and
            # [EN] doesn't fix the root cause: change the model tier, make the prompt a bit longer, and it's short
            # [EN] again. Here it's changed to **self-healing** --
            # [EN] it only triggers when "the body is empty and thinking was indeed on" (= the quota was indeed
            # [EN] spent on thinking),
            # [EN] the cost is **one extra call**, and that shot was wasted anyway.
            #
            # ⚠ 只在**这次没关思考**时才试：已经关了还是空，说明问题不在思考，
            #   再试一遍只是浪费（那种情况下面会照旧记 warning）。
            #   ★ 2026-10-07：条件抽成 `should_auto_no_think_retry()`
            #     —— 与 `_real_call` 里那个 `auto_retry` 标记**共用同一份判定**
            #     （两处各写一遍就会漂，见那个函数的说明）。
            # [EN] ⚠ Only try when **thinking wasn't off this time**: if it was already off and still empty, the
            # [EN] problem isn't thinking,
            # [EN] and retrying just wastes (in that case a warning is logged as usual below).
            # [EN] ★ 2026-10-07: the condition is extracted into `should_auto_no_think_retry()`
            # [EN] -- **sharing the same judgment** as the `auto_retry` flag in `_real_call`
            # [EN] (writing it twice in two places would drift, see that function's docstring).
            if should_auto_no_think_retry(empty=not text.strip(), no_think=no_think,
                                          has_reasoning=bool(meta.get('has_reasoning')),
                                          model=model):
                _LOG.warning(
                    "LLM 正文为空（额度被思考吃光）→ **关掉思考重试一次**："
                    "purpose=%s model=%s max_tokens=%d",
                    purpose, model, max_tokens)
                text2, meta2 = await self._real_call(
                    tier, model, messages, purpose, temperature=temperature,
                    max_tokens=max_tokens, timeout=timeout,
                    json_mode=use_json_mode, no_think=True, res=_res, caps=caps)
                if text2.strip():
                    meta2['no_think_retry'] = True
                    text, meta = text2, meta2
                    # ★★ 学会了：这个 (模型, 用途) 以后**直接关着思考发**。
                    #   已经学会过就只记一次日志（别每个用途刷一行）。
                    # [EN] ★★ Learned: this (model, purpose) should **just be sent with thinking off** from now on.
                    # [EN] If already learned, log it only once (don't print a line for every purpose).
                    if (model, purpose) not in self._no_think_learned:
                        self._no_think_learned.add((model, purpose))
                        _LOG.info(
                            "已记住「%s + %s」不用思考（关掉思考就出得来）——"
                            " 以后这个用途直接关着发，不再白烧首发",
                            model, purpose)
                else:
                    _LOG.warning(
                        "关掉思考重试之后**仍然是空的**（purpose=%s）——"
                        "这次不是思考的问题，可能是 max_tokens 真的太小，"
                        "或者提示词让它无法作答", purpose)
        # ★ 存下这一发（**只存非空**：存了空串等于把"失败"固化成"答案"，
        #   下一次问同一个问题时直接返回一段空白）。
        # [EN] ★ Store this shot (**non-empty only**: storing an empty string would freeze a
        # [EN] "failure" into an "answer", and the next identical question would return blank).
        if _dkey:
            try:
                from llm import dedup as _DEDUP
                _DEDUP.put(_dkey, text)
            except Exception:                                    # noqa: BLE001
                pass
            # ★ 同时落进**共享缓存**（跨进程 / 跨会话）。两层各存一份是有意的：
            #   内存那份管"这一轮"（快），磁盘那份管"下次启动 / 别的进程"（慢但留得住）。
            # [EN] ★ Also write into the **shared cache** (cross-process / cross-session). Storing in
            # [EN] both is deliberate: memory covers "this run" (fast), disk covers "next launch /
            # [EN] other processes" (slow but persistent).
            try:
                from llm import cache as _SHARED2
                _SHARED2.put(_dkey, text)
            except Exception:                                    # noqa: BLE001
                pass
        return (text, meta) if return_meta else text

    # ── mock ──
    async def _mock_call(self, messages: list[dict], purpose: str, model: str,
                         max_tokens: int = 0) -> tuple[str, dict]:
        t0 = time.monotonic()
        text = mock_reply(messages, purpose)
        dt = int((time.monotonic() - t0) * 1000)
        tin = estimate_messages_tokens(messages)
        tout = estimate_tokens(text)
        self.ledger.add(UsageRecord(time.time(), "mock", model, purpose, tin, tout, 0.0, dt))
        self._emit({"type": "response", "tier": "mock", "model": model, "purpose": purpose,
                    "text": text, "tin": tin, "tout": tout, "cost": 0.0, "ms": dt,
                    "finish_reason": "stop", "truncated": False})
        return text, {"model": model, "tier": "mock", "purpose": purpose,
                      "finish_reason": "stop", "truncated": False,
                      "has_reasoning": False, "max_tokens": max_tokens,
                      "tin": tin, "tout": tout, "cost": 0.0, "ms": dt}

    # ── 真实调用 ──
    # [EN] -- Real call --
    def _price_overrides(self, res=None) -> dict:
        """这一发计价该用哪套单价。

        三层，**越靠后越优先**：全局 `MODEL_PRICE_OVERRIDES` → 模型登记表里填过的
        → **这一发落在的那条登记表条目自己的价**（`res.prices`）。
        ★ 为什么最后一层还要单独盖一次：登记表允许两条条目指向同一个模型名
          （比如"混元 Hy3 腾讯官方"与"混元 Hy3 代理"），而 `price_overrides()`
          是**按模型名去重**的（后者赢）—— 这一发实际走的是**哪条条目**只有
          `res` 知道，按它取价才不会"走了代理却按官价算"。
        
            English:
        Which price set this request should be priced with.
            Three layers, **later wins**: the global `MODEL_PRICE_OVERRIDES` -> prices filled in the
            model registry -> **the price on the very registry entry this request landed on**
            (`res.prices`).
            ★ Why the last layer is overlaid again: the registry allows two entries pointing at the
              same model name (e.g. "Hunyuan Hy3 official" and "Hunyuan Hy3 proxy"), while
              `price_overrides()` dedupes **by model name** (the later one wins) -- only `res` knows
              **which entry** this request actually went through, and pricing by it avoids "went
              through the proxy but billed at the official rate".
        """
        ov: dict = dict(self.ledger.overrides)
        try:
            from llm import models as _M
            ov.update(_M.price_overrides())
            p = getattr(res, 'prices', None)
            name = str(getattr(res, 'model', '') or '')
            if p is not None and name:
                ov[name] = tuple(float(x) for x in p)
        except Exception:                                        # noqa: BLE001
            pass
        return ov

    async def _post_plain(self, url: str, body: dict, headers: dict,
                          timeout, who: dict | None = None) -> dict:
        """**整段**发一发（老路），返回 `resp.json()`。

        ★ 抽出来只为一件事：流式那条路在"这家不吃流式"时要**在同一处**退回它，
          而"退回去"的那几行必须与老路**逐字一致** —— 复制一份就迟早漂
          （比如某天给 429 加了特殊处理，只改了一处）。
        `who`：这一发落在哪个服务商/模型/用途上（`{'provider','label','model','purpose','base_url'}`），
          只用来把「没钱了」这条异常说清楚（谁没钱、哪一步）。
        [EN] Send one **whole** request (the old path) and return `resp.json()`.
        Extracted for one reason: the streaming path must fall back to it **in the same
        place**, and those lines must be **character-identical** to the old path -- a copy
        would drift (e.g. someone special-cases 429 in one of them only).
        `who`: which provider/model/purpose this request lands on, used only to describe the
        "out of money" exception (who, and at which step).
        """
        resp = await self._client.post(
            url, json=body, headers=headers, timeout=timeout,
        )
        # ★★★ 先判"没钱了"，再判 429（2026-10-25）：
        #   欠费也可能以 429 回来（OpenAI 就是这样，body 里带 `insufficient_quota`），
        #   而 429 那条会进重试 —— 对欠费重试是**永远不会成功**的那种烧时间。
        # [EN] ★★★ Check "out of money" **before** 429 (2026-10-25): billing can also come back as
        # [EN] 429 (OpenAI does exactly that, with `insufficient_quota` in the body), and the 429
        # [EN] branch retries -- retrying billing never succeeds and only burns time.
        if CREDIT.detect(resp.status_code, resp.text):
            raise _ooc_from(resp.status_code, resp.text, who)
        if resp.status_code == 429:
            raise httpx.HTTPStatusError("429", request=resp.request, response=resp)
        resp.raise_for_status()
        return resp.json()

    async def _stream_collect(self, url: str, body: dict, headers: dict,
                              timeout, purpose: str, model: str,
                              who: dict | None = None) -> dict:
        """发一发**流式**请求，把 SSE 逐块读进来，返回**与非流式同形**的 `data`。

        ★ 返回"同形的 data"是这一步的关键设计：下游那一大段（截断检测、
          `has_reasoning`、`empty_output`、计费、缓存）**一行都不用改** ——
          `_real_call` 里只多一个 `if`，两条路的出口完全一样。
          如果改成"流式走一条独立的返回路径"，那两段逻辑迟早漂，
          而它们管的是钱和"输出是不是被截断"，漂了没人看得出来。

        ★ 每个增量都 `_emit({'type': 'delta', ...})`：
          `stream='reasoning'` 是**思考**（`reasoning_content`），
          `stream='content'` 是**正文**。界面只把 reasoning 灌进展开框
          （正文另有去处，见 `crew/live.feed`）。

        ★ `usage` 靠 `stream_options.include_usage`：不请求的话流式响应里
          **根本没有** usage，账本只能按估算记 —— 而"思考吃掉了多少 token"
          正是用户会去看的那个数（见 `no_think` 那段注释里的事故）。

        ⚠ 400/415/422 一律当成"这家不吃流式"（`_StreamUnsupported`）：
          这三个码在"多带了个 `stream_options`"这件事上最常见，而真正的
          参数错误（模型名不存在等）会由**回退之后那一发**照常报出来 ——
          信息不丢，只是多花一发请求。

            English:
        Send one **streaming** request, read the SSE chunk by chunk, and return a `data`
        dict **shaped exactly like the non-streaming one**.
        ★ Returning a "same-shaped data" is the key design point: the large downstream
          block (truncation detection, `has_reasoning`, `empty_output`, billing, caching)
          needs **not one line changed** -- `_real_call` only grows a single `if`, and both
          paths exit identically. Giving streaming its own return path would make the two
          drift, and they govern money and "was the output truncated", where drift is
          invisible.
        ★ Every delta is emitted as `{'type': 'delta', ...}`: `stream='reasoning'` is
          **thinking** (`reasoning_content`), `stream='content'` is the body. The UI only
          pours reasoning into the expander (the body has its own place, see
          `crew/live.feed`).
        ★ `usage` depends on `stream_options.include_usage`: without asking for it a
          streaming response carries **no** usage at all and the ledger can only estimate
          -- and "how many tokens thinking ate" is exactly the number the user looks at.
        ⚠ 400/415/422 are all treated as "this gateway does not stream"
          (`_StreamUnsupported`): those three are the usual suspects for "one extra
          `stream_options` field", and a genuine parameter error (unknown model, etc.) will
          still surface on **the retry after falling back** -- no information is lost, just
          one extra request.
        """
        body = dict(body)
        body['stream'] = True
        body['stream_options'] = {'include_usage': True}
        content: list[str] = []
        reasoning: list[str] = []
        finish = ''
        usage: dict = {}
        async with self._client.stream('POST', url, json=body, headers=headers,
                                       timeout=timeout) as resp:
            # ⚠ 顺序与 `_post_plain` 一致：**先判没钱，再判 429**，再判"不吃流式"。
            #   欠费放进"不吃流式"那一档会被当成"退回整段重发"，于是又发一次、
            #   又失败一次（多花一发，而且日志里看到的是"网关不支持流式"—— 完全误导）。
            # ⚠ **非 2xx 才 `aread()`**：流式响应在没读完之前 `resp.text` 会抛
            #   `ResponseNotRead`；而 200 那条路要的就是"边读边出"，不许先整段读进来。
            # [EN] Same order as `_post_plain`: **out-of-money first**, then 429, then
            # [EN] "no streaming". Putting billing into the "no streaming" bucket would fall back
            # [EN] to a whole request, send it again, fail again -- and the log would read
            # [EN] "gateway doesn't support streaming", which is completely misleading.
            # [EN] ⚠ `aread()` **only for non-2xx**: before the stream is drained `resp.text`
            # [EN] raises `ResponseNotRead`, and the 200 path needs to read incrementally.
            _why = ''
            if not resp.is_success:
                await resp.aread()
                _why = resp.text or ''
            if CREDIT.detect(resp.status_code, _why):
                raise _ooc_from(resp.status_code, _why, who)
            if resp.status_code in (400, 415, 422):
                raise _StreamUnsupported(f'HTTP {resp.status_code}：{_why[:200]}')
            if resp.status_code == 429:
                raise httpx.HTTPStatusError('429', request=resp.request, response=resp)
            resp.raise_for_status()
            async for raw in resp.aiter_lines():
                line = (raw or '').strip()
                if not line or line.startswith(':'):
                    continue
                if line.startswith('data:'):
                    line = line[5:].strip()
                if not line:
                    continue
                if line == '[DONE]':
                    break
                try:
                    chunk = json.loads(line)
                except Exception:                            # noqa: BLE001
                    # 有些网关会往流里插心跳/注释，解析不了就跳过（不是错误）
                    # [EN] Some gateways interleave heartbeats/comment lines; skip
                    # unparsable ones (not an error)
                    continue
                if chunk.get('usage'):
                    usage = chunk['usage'] or {}
                for ch in (chunk.get('choices') or []):
                    d = ch.get('delta') or {}
                    # 思考字段各家写法不同：DeepSeek 是 `reasoning_content`，
                    # 有些网关是 `reasoning`。两个都认，取到的那个才发事件。
                    # [EN] Providers differ on the thinking field: DeepSeek uses
                    # `reasoning_content`, some gateways `reasoning`. Accept both.
                    r = d.get('reasoning_content') or d.get('reasoning') or ''
                    c = d.get('content') or ''
                    if r:
                        reasoning.append(str(r))
                        self._emit({'type': 'delta', 'stream': 'reasoning',
                                    'text': str(r), 'purpose': purpose,
                                    'model': model})
                    if c:
                        content.append(str(c))
                        self._emit({'type': 'delta', 'stream': 'content',
                                    'text': str(c), 'purpose': purpose,
                                    'model': model})
                    if ch.get('finish_reason'):
                        finish = str(ch['finish_reason'])
        if not content and not reasoning:
            raise _StreamUnsupported('流式返回里一个块都没读到')
        return {
            'choices': [{
                'message': {'content': ''.join(content),
                            'reasoning_content': ''.join(reasoning)},
                'finish_reason': finish,
            }],
            'usage': usage,
        }

    async def _real_call(self, tier: str, model: str, messages: list[dict],
                         purpose: str, temperature: float, max_tokens: int,
                         timeout: float | None, json_mode: bool = False,
                         no_think: bool = False,
                         res=None, caps: dict[str, bool] | None = None,
                         ) -> tuple[str, dict]:
        """真发一发请求。

        `res` / `caps`（2026-10-12 加）：这一发**落在哪个服务商**（`llm.models.Resolved`）
        与按那个模型判出来的能力开关。不给就退回老的全局地址与 `CFG` 里的能力开关
        —— 那样老调用点（判据/探针直接调 `_real_call`）一行都不用改。

            English:
        Actually send one request.
            `res` / `caps` (added 2026-10-12): **which provider** this request lands on
            (`llm.models.Resolved`) and the capability switches judged from that model. Without them
            it falls back to the old global endpoint and the capability switches in `CFG` -- so old
            call sites (criteria/probes calling `_real_call` directly) need no change.
        """
        _caps = caps or {k: CFG.b(k) for k in CAP_KEYS}
        # 地址与密钥**逐发解析**：登记表里每条模型可以来自不同服务商。
        # ⚠ 空值时退回 `.env` 的全局值 —— 那是老用户升级上来的唯一通道。
        # [EN] Endpoint and key are **resolved per request**: each registry entry may come from a
        # [EN] different provider.
        # [EN] ⚠ On empty values fall back to the global `.env` values -- that is the only channel
        # [EN] for a user upgrading from an older version.
        _base = str(getattr(res, 'base_url', '') or '').strip().rstrip('/')
        _key = str(getattr(res, 'api_key', '') or '').strip()
        base_url = _base or CFG.s("LLM_BASE_URL").rstrip("/")
        api_key = _key or CFG.s('LLM_API_KEY')
        url = (base_url + '/chat/completions') if base_url else '/chat/completions'
        headers = {"Authorization": f"Bearer {api_key}",
                   "Content-Type": "application/json"}
        assert self._sem and self._client, (
            'LLM 客户端没建起来：调用方要先 `await llm.ensure_started()`，'
            '或者直接走 `llm.chat()`（它自己会补）。'
            '**别把这条当成"返回空结果"用** —— 以前它是一句裸 assert，'
            '异常被上层吞掉后表现成"人物什么都不做"，没人看得出是配置问题。')
        # ★ 2026-10-12：**先取这一家自己填的**（`res.retries`），没填才用全局兜底。
        #   「通用参数」那一节去掉之后，超时与重试挂在**每一条模型**上 ——
        #   理由见 `llm/models.ModelEntry.timeout`（每家的脾气不一样）。
        # [EN] ★ 2026-10-12: **prefer what this provider filled in** (`res.retries`), falling back to the
        # [EN] global value. After the "General parameters" section was removed, timeout and retries hang
        # [EN] on **each model entry** -- see `llm/models.ModelEntry.timeout` (every provider differs).
        _own_retries = int(getattr(res, 'retries', -1) or -1)
        retries = _own_retries if _own_retries >= 0 else CFG.i("LLM_MAX_RETRIES")
        _own_timeout = float(getattr(res, 'timeout', -1) or -1)
        if _own_timeout > 0 and not timeout:
            timeout = _own_timeout
        last_err: Exception | None = None
        # ★★★ 「这一发是谁」—— 只给"没钱了"那条异常用（哪家、哪个模型、哪一步）。
        # [EN] ★★★ "Who is this request" -- used only by the out-of-credit exception.
        _who = {'provider': str(getattr(res, 'provider', '') or ''),
                'label': str(getattr(res, 'label', '') or ''),
                'model': model, 'purpose': purpose, 'base_url': base_url}
        # ★★★ **这一家已经登记过欠费 ⇒ 不发网络，直接抛**（2026-10-25）。
        #   为什么必须有这一条：整理稿一天 18 段 × 每段一套 Reflexion，若每次都发出去，
        #   就是几千次注定失败的请求 —— 每次还要等超时。用户看到的是"点了继续还是不动"。
        #   ⚠ 按**服务商**判（`key` 认 provider/地址，不认模型名）：同一家下的十个模型
        #     共用一笔余额，按模型名判会漏掉"另一个模型也没钱"。
        # [EN] ★★★ **This provider is already known to be out of credit => no network call, raise
        # [EN] immediately** (2026-10-25). Why this must exist: one day of organizing is 18 chunks
        # [EN] with a full Reflexion pass each; sending them all means thousands of requests that
        # [EN] are guaranteed to fail, each also waiting out a timeout. The user sees "clicked
        # [EN] resume and nothing happened".
        # [EN] ⚠ Keyed on the **provider** (`key` uses provider/host, not the model name): ten
        # [EN] models under one provider share one balance, and keying per model would miss
        # [EN] "that other model is out of money too".
        _blk = CREDIT.first()
        _self_key = CREDIT.key_of(_who['provider'], base_url)
        if _blk is not None and CREDIT.is_blocked(_self_key):
            _mine = next((e for e in CREDIT.all_blocked() if e.key == _self_key), _blk)
            raise _ooc_from(_mine.status, _mine.detail, _who)
        for attempt in range(retries + 1):
            async with self._sem:
                t0 = time.monotonic()
                try:
                    body: dict[str, Any] = {
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                    }
                    # 推理模型（deepseek-reasoner / o1 / o3 …）不接受 temperature，
                    # 带上它轻则被忽略、重则直接 400 —— 由能力开关决定发不发。
                    # [EN] Reasoning models (deepseek-reasoner / o1 / o3 ...) don't accept temperature,
                    # [EN] at best it's ignored, at worst it's a direct 400 -- the capability switch decides whether to
                    # [EN] send it.
                    if not _caps.get(CAP_REASONING, CFG.b("LLM_CAP_REASONING")):
                        body["temperature"] = temperature
                    if json_mode:
                        # 真·JSON 模式：让服务端保证返回合法 JSON 对象。
                        # （前提是 messages 里出现了 "json" 字样，否则 OpenAI 会 400，
                        #   而 json_mode 的调用方本来就在提示词里写了 JSON 说明。）
                        # [EN] True JSON mode: make the server guarantee a valid JSON object is returned.
                        # [EN] (Precondition is that the word "json" appears in messages, otherwise OpenAI returns 400,
                        # [EN] and json_mode callers already write JSON instructions in their prompt.)
                        body["response_format"] = {"type": "json_object"}
                    if no_think:
                        # ★ 关掉思考（DeepSeek V4 系列）。**思考是连 max_tokens
                        #   一起吃的**：2026-10-06 那轮推演里，「判据满足了没有」
                        #   这个 6 行的判定问题，让 deepseek-flash 思考 3233 token
                        #   把 2000 的额度用光、正文一个字没写出来（finish=length）。
                        #   调用方按 `NO_THINK_PURPOSES` 决定要不要关，这里照办。
                        # [EN] ★ Turn thinking off (DeepSeek V4 series). **Thinking eats max_tokens
                        # [EN] too**: in the 2026-10-06 simulation round, for the "are the criteria met"
                        # [EN] 6-line judgment question, deepseek-flash thought for 3233 tokens
                        # [EN] and used up the 2000 quota, writing not a single character of body text (finish=length).
                        # [EN] The caller decides whether to turn it off per `NO_THINK_PURPOSES`; here we comply.
                        body["thinking"] = {"type": "disabled"}

                    # DEBUG: 记录完整请求
                    # [EN] DEBUG: log the full request
                    if CFG.b("DEBUG_MODE"):
                        _LOG.debug("LLM 请求 [%s] model=%s purpose=%s msgs=%d"
                                   "%s", tier, model, purpose, len(messages),
                                   "（关思考）" if no_think else "")
                        for i, msg in enumerate(messages):
                            content_preview = msg.get("content", "")[:200]
                            _LOG.debug("  msg[%d] role=%s content=%s", i, msg.get("role", "?"), content_preview)

                    # ★★★ 2026-10-23：**流式 / 整段**在这里分叉，出口完全一样。
                    #   流式只由 `stream_scope(True)` 打开（剧组出工那一路），
                    #   其余 29 处调用点照旧走 `resp.json()` —— 一行都没动。
                    # [EN] ★★★ 2026-10-23: **streaming vs whole-response** forks here, with
                    # [EN] identical exits. Streaming is enabled only via `stream_scope(True)`
                    # [EN] (the crew work path); the other 29 call sites still take
                    # [EN] `resp.json()` -- not one line changed.
                    _tmo = httpx.Timeout(
                        timeout or CFG.i("LLM_TIMEOUT_SECONDS"), connect=10)
                    if stream_wanted():
                        try:
                            data = await self._stream_collect(
                                url, body, headers, _tmo, purpose, model, _who)
                        except _StreamUnsupported as _se:
                            # ★ 这家不吃流式 ⇒ **同一次尝试内**立刻改走整段。
                            #   不 `continue`：那会白扔一次重试预算，而这里
                            #   根本没有失败 —— 只是换了个问法。
                            # [EN] ★ This gateway does not stream => fall back to the whole
                            # [EN] response **within the same attempt**. Not `continue`: that
                            # [EN] would burn one retry of the budget, and nothing failed here
                            # [EN] -- only the way of asking changed.
                            mark_stream_broken(str(_se))
                            data = await self._post_plain(url, body, headers, _tmo, _who)
                    else:
                        data = await self._post_plain(url, body, headers, _tmo, _who)
                    choice = data["choices"][0]
                    text = choice["message"]["content"] or ""
                    # ★ 截断检测（2026-10-06 补）。`finish_reason == 'length'` =
                    #   输出撞到 `max_tokens` 被砍断。**以前这里完全不看它**，
                    #   于是"提取设定被截在半句话里"这件事对上层是不可见的：
                    #   解析失败 → 悄悄降级成空骨架，用户只看到一句"无法解析"。
                    # [EN] ★ Truncation detection (added 2026-10-06). `finish_reason == 'length'` =
                    # [EN] output hit `max_tokens` and was cut off. **Previously this wasn't checked at all**,
                    # [EN] so "setting extraction got truncated mid-sentence" was invisible to upper layers:
                    # [EN] parse failure -> silently degrades to an empty skeleton, the user only sees "cannot parse".
                    finish = str(choice.get("finish_reason") or "")
                    truncated = (finish == "length")
                    # 顺带记一下有没有"思考内容"：推理型模型会把 max_tokens
                    # **连思考一起吃**，正文只写了个开头就没预算了 —— 这时
                    # 光看 `content` 长度会以为"输出很短、不该超限"，越查越糊涂。
                    # [EN] Also note whether there's "thinking content": reasoning models eat max_tokens
                    # [EN] **along with thinking**, and the body only gets a beginning written before the budget runs out
                    # [EN] -- then
                    # [EN] just looking at `content` length makes you think "output is short, shouldn't exceed the limit",
                    # [EN] and the more you investigate the more confused you get.
                    has_reasoning = bool(
                        (choice.get("message") or {}).get("reasoning_content"))
                    # ★ **「一个字都没拿到」与「拿到了但被截断」是两码事**（2026-10-06 补）。
                    #   推理模型的额度可能**整份**花在思考上 → `content` 是空串。
                    #   这跟"写了一半被砍断"完全不同：调用方拿到的是**空**，
                    #   任何"按可闭合前缀抢救"都无从下手（没有前缀）。
                    #   以前两种情况共用一句 warning，日志里看不出区别，
                    #   于是「AI 优化里 AI 一句话都没说」查了很久才找到是预算问题。
                    # [EN] ★ **"Didn't get a single character" and "got it but truncated" are two different things** (added
                    # [EN] 2026-10-06).
                    # [EN] A reasoning model's quota may be spent **entirely** on thinking -> `content` is an empty string.
                    # [EN] This is completely different from "written halfway then cut off": the caller gets **empty**,
                    # [EN] and any "rescue by closable prefix" has nothing to work with (there's no prefix).
                    # [EN] Previously both cases shared one warning line, and the log couldn't tell them apart,
                    # [EN] so "in AI optimization the AI didn't say a single word" took a long time to trace to a budget
                    # [EN] problem.
                    empty_output = not text.strip()
                    usage = data.get("usage") or {}
                    tin = usage.get("prompt_tokens") or estimate_messages_tokens(messages)
                    tout = usage.get("completion_tokens") or estimate_tokens(text)
                    # ★ 2026-10-12：命中前缀缓存的那部分**按命中价算**（便宜得多），
                    #   并且单独记下来 —— 不区分的话，"缓存省了多少钱"在账本上永远看不出来。
                    # [EN] ★ 2026-10-12: the prefix-cache-hit portion is **billed at the hit price**
                    # [EN] (far cheaper) and recorded separately -- without the distinction, "how much
                    # [EN] caching saved" is never visible in the ledger.
                    cache_tok = _cache_hit_tokens(usage)
                    cost = cost_of(model, tin, tout, self._price_overrides(res),
                                   cache_tok=cache_tok)
                    dt = int((time.monotonic() - t0) * 1000)
                    self.ledger.add(UsageRecord(time.time(), tier, model, purpose,
                                                tin, tout, cost, dt, cache_tok))
                    self._maybe_warn()
                    self._log_call(model, purpose, tin, tout, dt, text)
                    # ★★ **「这一发注定要被重试」要标进事件里**（2026-10-07）。
                    #   以前不标：`_real_call` 先广播了一条 `empty_output=True`，
                    #   界面立刻报红字；紧接着 `chat()` 悄悄关掉思考重试并成功，
                    #   而**成功这件事没有任何事件**。用户看到的就是"一直在报错"，
                    #   实际上每一次都救回来了（他的日志：触发 101 次 / 失败 0 次）。
                    #   标上它，界面才能把"注定要被重试的那一发"讲成
                    #   「首次没拿到正文 → 正在关掉思考重试」，而不是一句红字报错。
                    # [EN] ★★ **"This shot is destined to be retried" must be marked in the event** (2026-10-07).
                    # [EN] Previously not marked: `_real_call` first broadcast an `empty_output=True`,
                    # [EN] the UI immediately showed red text; right after, `chat()` silently turned thinking off and
                    # [EN] retried successfully,
                    # [EN] and **the success had no event at all**. What the user saw was "erroring the whole time",
                    # [EN] when in fact every one was rescued (his log: 101 triggers / 0 failures).
                    # [EN] Mark it, and the UI can describe "the shot destined to be retried" as
                    # [EN] "first attempt got no body text -> retrying with thinking off", instead of a red error line.
                    auto_retry = should_auto_no_think_retry(
                        empty=empty_output, no_think=no_think,
                        has_reasoning=has_reasoning, model=model)
                    if empty_output and truncated:
                        # ★ 2026-10-07：这句话原来写的是"请把这个 purpose 的
                        #   max_tokens 调大" —— 那是**错的建议**。真实日志里
                        #   101 次触发、0 次失败：真正管用的是**关掉思考**
                        #   （下一段代码就会自动做），加额度是白花钱。
                        #   所以改成如实说"即将自动重试"。
                        # [EN] ★ 2026-10-07: this sentence originally read "please set this purpose's
                        # [EN] max_tokens bumped up" -- that is **wrong advice**. In real logs
                        # [EN] 101 triggers, 0 failures: what actually works is **turning off thinking**
                        # [EN] (the next code block does this automatically), raising the quota just wastes money.
                        # [EN] So change it to honestly say "about to auto-retry".
                        _LOG.warning(
                            "LLM 一个字都没拿到（max_tokens=%d 全被用光，共 %d token"
                            "%s）：**正文为空**，额度被思考吃掉了 —— "
                            "%s。purpose=%s model=%s",
                            max_tokens, tout,
                            "，含思考内容" if has_reasoning else "",
                            "将**自动关掉思考重试一次**" if auto_retry
                            else "本次**不会**自动重试（开关关着 / 已经关过思考 / "
                                 "或这个模型不支持关思考）",
                            purpose, model)
                    elif truncated:
                        _LOG.warning(
                            "LLM 输出被截断（max_tokens=%d，实际输出 %d token / 正文 %d 字"
                            "%s）：长文或 JSON 很可能不完整 —— purpose=%s model=%s",
                            max_tokens, tout, len(text),
                            "，且本次带思考内容（思考也算在 max_tokens 里）"
                            if has_reasoning else "", purpose, model)
                    elif not empty_output:
                        # ★ **警戒线**（2026-10-10）：这次没被砍断，但已经贴着了 ——
                        #   提前看见，才不会下一次"刚好过线"。
                        #   取上限时**用这一发真正用的那个数**（有效上限），
                        #   不是调用方传进来的那个（两者在 `model` 模式下差很多）。
                        # [EN] ★ **Warning line** (2026-10-10): this time it wasn't cut off, but it's already brushing against
                        # [EN] it --
                        # [EN] See it in advance so that next time it doesn't "just barely cross the line".
                        # [EN] When taking the cap, **use the number this request actually uses** (effective cap),
                        # [EN] not the one passed in by the caller (the two differ a lot in `model` mode).
                        try:
                            warn_at = float(CFG.f("LLM_TOKEN_WARN_RATIO"))
                        except Exception:                            # noqa: BLE001
                            warn_at = 0.85
                        if max_tokens > 0 and tout >= max_tokens * warn_at:
                            _LOG.warning(
                                "LLM 输出已到警戒线（%d / %d token，%.0f%%）："
                                "下一次很可能被截断 —— purpose=%s model=%s",
                                tout, max_tokens, 100.0 * tout / max_tokens,
                                purpose, model)

                    # 广播响应事件
                    # [EN] Broadcast response event
                    self._emit({"type": "response", "tier": tier, "model": model,
                                "purpose": purpose, "text": text,
                                "tin": tin, "tout": tout, "cost": cost, "ms": dt,
                                "finish_reason": finish, "truncated": truncated,
                                "has_reasoning": has_reasoning,
                                "empty_output": empty_output,
                                "no_think": no_think,
                                # ★ 这一发注定会被"关掉思考重试"顶掉 ——
                                #   界面据此**不报红字**（见 `on_llm`）。
                                # [EN] ★ This request is destined to be overridden by the "turn off thinking and retry" --
                                # [EN] the UI accordingly **does not show red text** (see `on_llm`).
                                "auto_retry": auto_retry,
                                "max_tokens": max_tokens})

                    # DEBUG: 记录完整响应
                    # [EN] DEBUG: log full response
                    if CFG.b("DEBUG_MODE"):
                        _LOG.debug("LLM 响应 [%s] purpose=%s tokens=%d+%d cost=%.4f ms=%d",
                                   tier, purpose, tin, tout, cost, dt)
                        _LOG.debug("  响应内容 (%d 字): %s", len(text), text[:500])

                    return text, {"model": model, "tier": tier, "purpose": purpose,
                                  "model_key": str(getattr(res, 'key', '') or ''),
                                  "finish_reason": finish, "truncated": truncated,
                                  "has_reasoning": has_reasoning,
                                  "empty_output": empty_output,
                                  "no_think": no_think,
                                  "auto_retry": auto_retry,
                                  "tin": tin, "tout": tout, "cost": cost, "ms": dt,
                                  "max_tokens": max_tokens}
                except CREDIT.OutOfCredit as e:
                    # ★★★ **欠费不重试、不沉睡，登记完立刻往上抛**（2026-10-25）。
                    #   · 不重试：对"余额不足"重试一万次也不会成功，只会让日志和耗时难看；
                    #   · 要登记：登记表是"谁没钱了"的唯一事实来源，主循环靠它暂停；
                    #   · 往上抛：`ask()` 那边会把这条**原样再抛**（不再降级成"没拿到东西"），
                    #     于是能一路走到能决定"停下"的那一层。
                    # [EN] ★★★ **Out-of-credit is not retried and not slept on; note it and re-raise
                    # [EN] immediately** (2026-10-25). No retry (a million tries cannot fix an empty
                    # [EN] wallet, it only ruins the log and the wall clock); note it (the registry is
                    # [EN] the single source of truth the main loop pauses on); re-raise (the `ask()`
                    # [EN] layer re-raises it verbatim instead of degrading to "got nothing"), so it
                    # [EN] reaches the layer that can decide to stop.
                    CREDIT.note(e)
                    self._emit({"type": "error", "tier": tier, "model": model,
                                "purpose": purpose, "error": str(e),
                                "out_of_credit": True,
                                "provider": e.provider or e.who,
                                "attempt": attempt + 1, "retries": retries})
                    raise
                except (httpx.HTTPStatusError, httpx.HTTPError, OSError) as e:
                    last_err = e
                    _LOG.warning("LLM 调用失败 (attempt %d/%d): %s", attempt + 1, retries + 1, e)
                    self._emit({"type": "error", "tier": tier, "model": model,
                                "purpose": purpose, "error": str(e),
                                "attempt": attempt + 1, "retries": retries})
                    # ★★ 「你给的 max_tokens 太大」⇒ **把上限减半再来**（2026-10-10）。
                    #   为什么会撞上：现在有效上限来自那张模型上限表
                    #   （`_effective_max_tokens`），而**那张表是猜的** ——
                    #   同一个模型名在不同供应商后面可能不一样。
                    #   猜大了不是"写得短"，而是**整发请求被拒**（400）。
                    #   ⇒ 减半重试；两次下去总能落到对方能接受的量级。
                    #   ⚠ 只在"看起来是长度问题"时减半（`_looks_like_token_limit_error`）：
                    #     400 也可能是"模型名写错了"，那种情况减半只是白烧一次、
                    #     还把真错误盖掉。
                    # [EN] ★★ "Your max_tokens is too large" => **halve the cap and try again** (2026-10-10).
                    # [EN] Why it runs into this: the current effective cap comes from that model-cap table
                    # [EN] (`_effective_max_tokens`), and **that table is a guess** --
                    # [EN] the same model name may differ behind different providers.
                    # [EN] Guessing too large doesn't mean "it writes shorter", it means **the whole request gets
                    # [EN] rejected** (400).
                    # [EN] => retry with half; two rounds will always land in a range the other side accepts.
                    # [EN] ⚠ Only halve when it "looks like a length problem" (`_looks_like_token_limit_error`):
                    # [EN] a 400 may also be "the model name is wrong", in which case halving just burns another try
                    # [EN] and also masks the real error.
                    if (max_tokens > 512
                            and _looks_like_token_limit_error(e)):
                        bigger_off = max(512, max_tokens // 2)
                        _LOG.warning(
                            "这一发像是被「输出上限太大」拒了（max_tokens=%d）："
                            "减半到 %d 再试 —— purpose=%s model=%s",
                            max_tokens, bigger_off, purpose, model)
                        max_tokens = bigger_off
                        continue
                    if attempt < retries:
                        wait = min(30.0, 2.0 ** attempt) + random.random() * 0.5
                        _LOG.info("退避 %.1fs 后重试", wait)
                        await asyncio.sleep(wait)
        raise RuntimeError(f"LLM 调用失败（已重试 {retries} 次）: {last_err}")

    # ── 辅助 ──
    # [EN] -- Helper --
    def _maybe_warn(self) -> None:
        budget = CFG.i("TOKEN_BUDGET_PER_DAY")
        if budget <= 0:
            return
        if self.ledger.today_tokens >= budget * CFG.f("TOKEN_WARN_AT"):
            _LOG.warning("今日 token 接近预算: %d / %d", self.ledger.today_tokens, budget)

    def _log_call(self, model, purpose, tin, tout, dt, text):
        if not CFG.b("SAVE_RAW_LOGS") or not self._log_dir:
            return
        # DEBUG 模式记录完整响应，否则只记录前 200 字
        # [EN] In DEBUG mode log the full response, otherwise log only the first 200 chars
        if CFG.b("DEBUG_MODE"):
            preview = text  # 完整记录
            # [EN] Log in full
        else:
            preview = text[:200]
        rec = {"ts": time.time(), "model": model, "purpose": purpose,
               "in": tin, "out": tout, "ms": dt, "preview": preview}
        path = self._log_dir / "llm_calls.jsonl"
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def budget_exceeded(self) -> bool:
        budget = CFG.i("TOKEN_BUDGET_PER_DAY")
        return budget > 0 and self.ledger.today_tokens >= budget


# ★ 「输出语言」**不注入**的用途白名单。
# [EN] ★ Whitelist of uses where "output language" is **not injected**.
#
# 合规检测（`compliance/agent.py`）的提示词里有**严格的输出契约**（三段分类 +
# 固定的 JSON 形状），而且它是**安全功能**：多塞一句"输出用英文写"，
# 换来的只是报告文字换语种，却有可能把判定搅乱 —— 不值。
# 报告本身的语言问题在 `compliance` 模块自己那边解决。
# [EN] The prompt of compliance detection (`compliance/agent.py`) has a **strict output contract**
# [EN] (three-way classification +
# [EN] a fixed JSON shape), and it is a **safety feature**: cramming in one more line "write your
# [EN] output in English"
# [EN] only changes the language of the report text, yet may scramble the verdict -- not worth it.
# [EN] The language issue of the report itself is handled on the `compliance` module's side.
_OUTLANG_SKIP: tuple[str, ...] = ('compliance',)


def _inject_output_lang(messages: list[dict], purpose: str) -> list[dict]:
    """把「所有输出用 X 语言写」这一句挂到**最后一条 user 消息**末尾。

    用户（2026-10-06）要的是「**所有的输出都用这个语言**，即使小说原来的语言不是这个」——
    而"输出什么语言"这件事**只有提示词能决定**（模型不会读我们的 `.env`）。

    为什么做在 `chat()` 这个漏斗里，而不是 29 个调用点各写一遍：
      · 调用点会越来越多（`sim` / `director` / `agent` / `display` / `export` / `ingest`…），
        "新加一个地方忘了写"是本项目反复踩的那类坑；
      · 这一句对**所有**生成类调用都成立，没有例外（除上面那个白名单）。

    挂到**最后一条 user 消息**而不是新加一条 system：后者会在
    `LLM_CAP_SYSTEM_ROLE=false` 时被 `_merge_system_into_user` 并到**第一条**，
    位置就从"最后"变成"最前"，还会跟别的系统提示挤在一起。
    
        English:
    Append the sentence "write all output in X language" to the end of the **last user message**.
        What the user (2026-10-06) wants is "**all output in this language**, even if the novel's original language isn't this" ——
        and "what language to output" **can only be decided by the prompt** (the model won't read our `.env`).
        Why do it in the `chat()` funnel, rather than writing it once at each of the 29 call sites:
          · Call sites keep growing (`sim` / `director` / `agent` / `display` / `export` / `ingest`…),
            "forgot to write it when adding a new place" is the kind of pit this project repeatedly falls into;
          · This sentence holds for **all** generation-type calls, with no exceptions (except the whitelist above).
        Attach to the **last user message** rather than adding a new system one: the latter, when
        `LLM_CAP_SYSTEM_ROLE=false`, gets merged by `_merge_system_into_user` into the **first** message,
        so its position changes from "last" to "first", and it also gets crammed together with other system prompts.
    """
    if purpose in _OUTLANG_SKIP:
        return messages
    line = outlang.directive()
    if not line:
        return messages
    msgs = [dict(m) for m in messages]
    for m in reversed(msgs):
        if (m.get("role") or "") == "user":
            m["content"] = f"{(m.get('content') or '').rstrip()}\n\n{line}"
            return msgs
    # 极端情况：一条 user 都没有（全是 system）→ 自己补一条收尾
    # [EN] Edge case: not a single user message (all system) => append one closing message yourself
    msgs.append({"role": "user", "content": line})
    return msgs


# 「提示词里**已经**要求用 JSON 回答了」的几个说法。
# [EN] The several phrasings for "the prompt **already** requires answering in JSON".
#
# ⚠ 这里**不能只找 "JSON" 这个词**（老写法就是 `if 'JSON' not in tail`）——
#   「输出语言」那句指令里会出现 `JSON` 这个词（"structured replies keep their
#   field names…"），于是本函数以为"已经要求过 JSON 了"、**把指令整句吞掉**：
#   `LLM_CAP_JSON_MODE=false` 的那些模型就再也拿不到「请仅以 JSON 回答」。
#   2026-10-06 `tools/verify_output_lang.py` 的「JSON 那句必须还在最后」这条判据抓到的。
#   所以要认**"在要求用 JSON 回答"的那几个说法**，而不是认这个词本身。
# [EN] ⚠ Here you **cannot just look for the word "JSON"** (the old way was `if 'JSON' not in tail`) --
# [EN] the "output language" instruction contains the word `JSON` ("structured replies keep their
# [EN] field names..."), so this function thinks "JSON has already been required" and **swallows the
# [EN] whole instruction**:
# [EN] models with `LLM_CAP_JSON_MODE=false` then never get "please answer in JSON only".
# [EN] Caught on 2026-10-06 by the criterion in `tools/verify_output_lang.py` that "the JSON sentence
# [EN] must still be last".
# [EN] So you must recognize **the several phrasings that "require answering in JSON"**, not the word
# [EN] itself.
_JSON_ASKED = (
    '请仅以 JSON', '以 JSON 回答', 'JSON 对象回答', '以 JSON 格式',
    'JSON only', 'answer in json', 'respond in json', 'json object',
)
_JSON_MARKER = '\n\n请仅以 JSON 对象回答，不要包含其他文字。'


def _ensure_json_instruction(messages: list[dict]) -> list[dict]:
    msgs = list(messages)
    tail = (msgs[-1]["content"] if msgs else "").strip()
    low = tail.lower()
    if not any(m.lower() in low for m in _JSON_ASKED):
        msgs[-1] = dict(msgs[-1], content=tail + _JSON_MARKER)
    return msgs


def _merge_system_into_user(messages: list[dict]) -> list[dict]:
    """把 system 消息并进首条 user 消息（`LLM_CAP_SYSTEM_ROLE=false` 时走这里）。

    有的模型/网关**不接受 role=system**，直接返回 400。此时唯一的办法是把
    系统提示当普通文本拼进对话——语义上等价（都在最前面），只是少了一层角色标记。
    
        English:
    Merge system messages into the first user message (this path is taken when
    `LLM_CAP_SYSTEM_ROLE=false`).
        Some models/gateways **don't accept role=system** and return 400 outright. The only way then is to
        splice the system prompt as plain text into the conversation —— semantically equivalent (both at the very front), just missing a layer of role marking.
    """
    sys_bits = [str(m.get("content") or "") for m in messages
                if (m.get("role") or "") == "system"]
    if not sys_bits:
        return messages
    rest = [m for m in messages if (m.get("role") or "") != "system"]
    prefix = "\n\n".join(b for b in sys_bits if b)
    if not rest:
        return [{"role": "user", "content": prefix}]
    rest = list(rest)
    first = dict(rest[0])
    if (first.get("role") or "") == "user":
        first["content"] = f"{prefix}\n\n{first.get('content') or ''}"
        rest[0] = first
    else:
        rest.insert(0, {"role": "user", "content": prefix})
    return rest


# 全局单例
# [EN] Global singleton
llm = LLM()