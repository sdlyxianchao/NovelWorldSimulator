# -*- coding: utf-8 -*-
"""**「这个模型没钱了」是一条独立的停止条件**（2026-10-25，用户点名）。

用户原话
--------
    「我配置了好几个 LLM 服务，我想如果哪个 LLM 没钱了，是否有办法给出明确的报信息，
      且当前推演暂停，如果没充值点继续，还报这个错误。充值之后点继续就可以继续推演。」

为什么不能靠现有的"调用失败 → 重试 → 抛 RuntimeError"
--------------------------------------------------
1. **会白等**：欠费是 402/403/429，走 `resp.raise_for_status()` 之后落进重试分支 ⇒
   退避 1s、2s、4s… 把重试次数用完，才吐一句
   `LLM 调用失败（已重试 3 次）: Client error '402 Payment Required'`。
   那句话**没有一个字说要充值**，而且"重试"这件事对欠费**永远不会成功**。
2. **会被吞掉**：`llm/replies.ask()` 与一路上十几个 `except Exception` 都会把它降级成
   "这一次没拿到东西"，`Agent.decide` 甚至会退化成"这一拍什么都没做"。
   屏幕上就是满屏"没动，也没出声"——正是用户要避免的那种哑掉。
3. **一晚上会被报几百次**：每个失败点各报一次，谁也不知道是同一个原因。

所以这里立三件事
----------------
· `OutOfCredit` —— **专门的异常**，带够给人看的信息（哪个服务商、哪个模型、HTTP 状态、
  服务端原话片段）。router 命中后**不再重试**，直接抛。
· **模块级登记表** —— 谁没钱了就登记一条。它是**唯一事实来源**：
  主循环靠它决定暂停、状态条靠它决定写什么、界面靠它决定提示什么。
  这样即使某处 `except Exception` 把异常吞了，**账还在**，主循环下一轮照样会停。
· **同一家 fail-fast** —— 登记过欠费的服务商，后续请求**不发网络**直接抛。
  否则整理稿那 18 段、每段一套 Reflexion，会把几千次注定失败的请求全发一遍。

口径：什么才算"没钱"
--------------------
⚠ 这一节最要紧的是**别把限流当欠费**（那会让一个还能用的服务被误判成没钱、
还让用户跑去充值）：

  · **402** ⇒ 一律算（这个码的语义就是 Payment Required，没有第二种解释）。
  · **429 / 403 / 400** ⇒ **只认欠费字样**。理由：429 最常见的含义是"太快了，等会儿"，
    403 常见是"这个 Key 没这个模型的权限"；把它们一律当欠费，用户会去充一笔
    根本不需要充的钱。OpenAI 的欠费确实也发 429，但它的 body 里带
    `insufficient_quota`；只被限流时带的是 `rate_limit`。
  · 标记表见 `OUT_OF_CREDIT_MARKERS`，中英各一遍（各家措辞见
    `llm/probe.explain_status` 里那批**实测**样本的口径）。

English:
**"This model is out of money" is its own stopping condition** (2026-10-25, requested by the user).

The user's words: "I've configured several LLM services. If one of them runs out of money, can it
give a clear message and pause the simulation? If I haven't topped up and click resume, it should
report the same error again; after topping up, clicking resume continues the simulation."

Why we cannot reuse the existing "call failed -> retry -> raise RuntimeError":
1. **It wastes time**: out-of-credit arrives as 402/403/429, falls into the retry branch after
   `raise_for_status()` => backoff 1s, 2s, 4s..., only to spit out `LLM 调用失败（已重试 3 次）:
   Client error '402 Payment Required'`. That sentence **never says "top up"**, and retrying an
   out-of-credit error **can never succeed**.
2. **It gets swallowed**: `llm/replies.ask()` and a dozen `except Exception` along the way degrade
   it to "this call got nothing", and `Agent.decide` degrades further to "this beat did nothing".
   The screen then shows a wall of "didn't move, didn't speak" -- exactly what the user wants to
   avoid.
3. **It gets reported hundreds of times**: once per failing call site, with nobody able to tell
   they share one cause.

So this module establishes three things:
- `OutOfCredit` -- a **dedicated exception** carrying everything a human needs (provider, model,
  HTTP status, a slice of the server's own words). The router **stops retrying** and raises it.
- **A module-level registry** -- one entry per blocked provider. It is the **single source of
  truth**: the main loop pauses on it, the status bar writes its text, the UI shows its hint. So
  even if some `except Exception` swallows the exception, **the ledger is still there** and the
  loop still stops on the next iteration.
- **Fail-fast per provider** -- once a provider is known to be out of credit, later requests make
  **no network call** and raise immediately. Otherwise the organizer's 18 chunks with a full
  Reflexion pass each would send thousands of requests that are guaranteed to fail.

Scope: what counts as "out of money": the critical part is **not mistaking rate limiting for
out-of-credit** (that would mark a working service as broke and send the user to top up for
nothing). 402 always counts (Payment Required has no other meaning). 429/403/400 count **only with
billing wording** -- 429 usually means "slow down", 403 usually means "this key lacks access to
this model". OpenAI does send 429 for billing, but its body carries `insufficient_quota`, whereas
plain rate limiting carries `rate_limit`.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

_LOG = logging.getLogger('nws.llm.credit')

#: **欠费/余额不足的字样**（小写比对；中文原样比对）。
#:
#: ⚠ 只收"钱"这一件事的措辞，**不要**把 `quota` 单收进来 ——
#:   很多限流响应里也写着 quota（`x-ratelimit-*`），那样 429 就会被误判成欠费。
#:   英文侧认 `insufficient_quota` 这个**完整标识**，不认裸 `quota`。
# [EN] **Out-of-credit wording** (compared lowercased; Chinese compared as-is).
# [EN] ⚠ Only collect wording about **money**. Do **not** add bare `quota`: many rate-limit
# [EN] responses mention quota too, and 429 would be misread as out-of-credit. The English side
# [EN] matches the **full identifier** `insufficient_quota`, never bare `quota`.
OUT_OF_CREDIT_MARKERS: tuple[str, ...] = (
    # ── 英文 ──
    'insufficient_quota', 'insufficient balance', 'insufficient_balance',
    'out of credit', 'no credit', 'credit balance', 'credit_balance',
    'exceeded your current quota', 'check your plan and billing',
    'arrearage', 'payment required', 'account is in good standing',
    'billing', 'unpaid', 'recharge',
    # ── 中文 ──
    '余额不足', '余额为 0', '余额为零', '账户余额', '账户已欠费', '欠费',
    '请充值', '充值后', '额度已用完', '额度用尽', '免费额度已', '资源包',
    '账户余额不足', '已用尽',
)

#: 这些 HTTP 码**一律**算欠费（不需要看正文）。
# [EN] These statuses **always** count (the body is not inspected).
ALWAYS_STATUS: frozenset[int] = frozenset({402})

#: 这些码**只在正文出现欠费字样**时才算（429 最常见的含义是限流，别误判）。
# [EN] These statuses count **only when the body carries billing wording** (429 mostly means
# [EN] rate limiting; do not misjudge).
MAYBE_STATUS: frozenset[int] = frozenset({400, 403, 429})


def key_of(provider: str = '', base_url: str = '') -> str:
    """同一家的标识：**认服务商 / 地址，不认模型名**。

    为什么按服务商而不按模型：一个服务商下挂十个模型，余额是**共用的** ——
    按模型名记账会把"同一笔没钱"记成十条，而且 fail-fast 也会漏掉
    "这一家的另一个模型同样没钱"。

    ⚠ 这里必须是**唯一实现**：`OutOfCredit.key` 用它、router 的 fail-fast 也用它。
      两处各写一份，就会出现"登记时按 provider 记、查询时按 host 查"这种
      永远查不中的错 —— 而症状只是"欠费了还在发请求"。
    [EN] Identity of "one provider": **keyed on provider / host, never the model name**. Ten models
    [EN] under one provider share one balance; keying per model would record one empty wallet as ten
    [EN] entries and would also miss "that provider's other model is out of money too".
    [EN] ⚠ This must be the **only implementation**: `OutOfCredit.key` uses it, and so does the
    [EN] router's fail-fast. Two copies would produce "recorded by provider, looked up by host",
    [EN] which never matches -- and the only symptom is "still sending requests while broke".
    """
    prov = str(provider or '').strip()
    if prov:
        return prov
    url = str(base_url or '').strip()
    if '://' in url:
        host = url.split('://', 1)[1].split('/', 1)[0]
        if host:
            return host
    return url or 'default'


class OutOfCredit(RuntimeError):
    """**这个服务商没钱了**。不是"这一次没拿到东西"，是"再试一万次也一样"。

    ⚠ 继承 `RuntimeError`：万一某处只写了 `except RuntimeError`，它仍然能被认出来
      （那些地方本来就把它当"调用失败"处理，至少不会抛到外面炸掉主循环）。
    ⚠ 但它**故意不是** `httpx.HTTPStatusError` 的子类 —— router 里那个
      `except (httpx.HTTPStatusError, ...)` 会重试，而欠费**绝不能重试**。

    [EN] **This provider is out of money.** Not "this call got nothing" -- "a million more tries
    [EN] give the same result". ⚠ Subclasses `RuntimeError` so a lone `except RuntimeError` still
    [EN] catches it (those places already treat it as a call failure, at least it won't blow up the
    [EN] main loop). ⚠ Deliberately **not** an `httpx.HTTPStatusError` subclass -- that handler in
    [EN] the router retries, and out-of-credit must **never** be retried.
    """

    def __init__(self, *, provider: str = '', label: str = '', model: str = '',
                 purpose: str = '', status: int = 0, detail: str = '',
                 base_url: str = '', at: float = 0.0):
        self.provider = str(provider or '')
        self.label = str(label or '')
        self.model = str(model or '')
        self.purpose = str(purpose or '')
        self.status = int(status or 0)
        self.detail = str(detail or '').strip()
        self.base_url = str(base_url or '')
        self.at = float(at or time.time())
        self.who = self.label or self.provider or self._host() or '未命名的服务'
        super().__init__(self.summary())

    # ── 给人看的三种粒度 ──────────────────────────────────────
    def _host(self) -> str:
        u = self.base_url
        if '://' not in u:
            return ''
        return u.split('://', 1)[1].split('/', 1)[0]

    @property
    def key(self) -> str:
        return key_of(self.provider, self.base_url)

    def summary(self) -> str:
        """一行，进日志用。"""
        bits = []
        if self.model:
            bits.append(f'模型 {self.model}')
        if self.status:
            bits.append(f'HTTP {self.status}')
        head = f'{self.who} 余额不足'
        return f'{head}（{"，".join(bits)}）' if bits else head

    def headline(self) -> str:
        """**状态条**那一行的长度：一句话说清"谁没钱了、我该怎么办"。"""
        return f'{self.who} 余额不足或欠费 —— 充值后点「继续」'

    def describe(self) -> str:
        """**中栏**那条：把"哪一步 / 哪家 / 服务端原话 / 怎么办"一次说全。

        ⚠ 一定要带上服务端原话（哪怕只是片段）：是不是真的欠费，用户看一眼那句话
          就能判断（比如它其实写的是"这个 Key 没有权限"，那一看就不是充钱能解决的）。
        [EN] The line in the middle column: step / provider / the server's own words / what to do.
        [EN] ⚠ Always include a slice of the server's own words -- the user can tell at a glance
        [EN] whether it is really billing (e.g. if it actually says "this key has no access",
        [EN] topping up will not help).
        """
        lines = []
        step = f'（{self.purpose}）' if self.purpose else ''
        lines.append(f'{self.who} 这个模型服务**余额不足或已欠费**{step}，'
                     f'推演已暂停。')
        tail = []
        if self.model:
            tail.append(f'模型 {self.model}')
        if self.status:
            tail.append(f'HTTP {self.status}')
        if tail:
            lines.append('· ' + ' · '.join(tail))
        if self.detail:
            lines.append(f'· 服务端原话：{self.detail}')
        lines.append('· 到这家服务商的后台充值，然后点「▶ 继续」，会从停下的地方接着跑；'
                     '还没充就点继续，还会停在这里并再报一次。')
        return '\n'.join(lines)


def detect(status: int, text: str) -> bool:
    """`(HTTP 状态, 响应正文)` → 这是不是"没钱了"。

    口径见模块头注释：**402 一律算；429/403/400 只认欠费字样**。
    [EN] `(status, body)` -> is this "out of money". 402 always; 429/403/400 only with billing
    [EN] wording.
    """
    try:
        code = int(status or 0)
    except (TypeError, ValueError):
        code = 0
    if code in ALWAYS_STATUS:
        return True
    if code not in MAYBE_STATUS:
        return False
    body = str(text or '')
    low = body.lower()
    for m in OUT_OF_CREDIT_MARKERS:
        if m.isascii():
            if m in low:
                return True
        elif m in body:
            return True
    return False


# ── 模块级登记表（唯一事实来源）──────────────────────────────
_blocked: dict[str, OutOfCredit] = {}
_order: list[str] = []
_callbacks: list[Callable[[OutOfCredit], None]] = []


def note(exc: OutOfCredit) -> OutOfCredit:
    """登记一次欠费。**同一个服务商只记第一条**（后面的原因一样，不必刷屏）。

    ⚠ 回调**只在"头一回发现这一家没钱"时**才发（2026-10-25）：
      整理稿那一路每段都会撞一次，若每次都回调，主循环的"立刻暂停"会被调上百次
      —— 虽然它是幂等的，但日志会变成一堵墙。
    [EN] Record one out-of-credit event. **Only the first per provider** (later ones share the same
    [EN] cause, no need to spam). ⚠ Callbacks fire **only when a provider is first found broke**
    [EN] (2026-10-25): the organizer path hits this once per chunk, and firing every time would call
    [EN] the loop's "pause now" hundreds of times -- idempotent, but the log becomes a wall.
    """
    k = exc.key
    fresh = k not in _blocked
    if fresh:
        _blocked[k] = exc
        _order.append(k)
        _LOG.error('模型服务余额不足：%s（这一家后续请求不再发网络，直到充值后点继续）',
                   exc.summary())
        for cb in list(_callbacks):
            try:
                cb(exc)
            except Exception as e:                               # noqa: BLE001
                # ⚠ 回调是"顺手通知"，它自己炸了不许盖掉欠费这件事本身。
                # [EN] Callbacks are a courtesy notification; their failure must not mask the fact.
                _LOG.warning('欠费回调失败（不影响暂停以外的逻辑）：%r', e)
    return exc


def on_block(cb: Callable[[OutOfCredit], None]) -> None:
    """登记一个"刚发现没钱了"的回调（主循环用它立刻自暂停）。"""
    if cb not in _callbacks:
        _callbacks.append(cb)


def off_block(cb: Callable[[OutOfCredit], None]) -> None:
    """撤掉回调（一轮跑完要撤，否则下一轮的循环也被它拴着）。"""
    try:
        _callbacks.remove(cb)
    except ValueError:
        pass


def first() -> OutOfCredit | None:
    """最早登记的那一条（用它写状态条与提示，**不要用最新那条** ——
    同一笔没钱会被好几处各报一次，用最新那条会让提示来回跳）。"""
    for k in _order:
        e = _blocked.get(k)
        if e is not None:
            return e
    return None


def all_blocked() -> list[OutOfCredit]:
    return [_blocked[k] for k in _order if k in _blocked]


def is_blocked(key: str) -> bool:
    return str(key or '') in _blocked


def blocked_keys() -> set[str]:
    return set(_blocked)


def clear() -> None:
    """清掉全部登记。**点「继续」时调它** —— 不清就等于"连一次都不会再试"，
    那样"充值之后点继续就能继续"永远不成立。"""
    _blocked.clear()
    _order.clear()


def forget_callbacks() -> None:
    """清回调（判据/探针用，避免跨用例串味）。"""
    _callbacks.clear()


__all__ = ['OutOfCredit', 'detect', 'note', 'first', 'all_blocked',
           'is_blocked', 'blocked_keys', 'clear', 'on_block', 'off_block',
           'forget_callbacks', 'key_of', 'OUT_OF_CREDIT_MARKERS', 'ALWAYS_STATUS',
           'MAYBE_STATUS']
