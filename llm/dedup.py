# -*- coding: utf-8 -*-
"""同题复用：**完全相同的请求**在保质期内只真发一次，第二次直接给上次的答案。

English:
Same-question reuse: an **identical request** is really sent only once within its shelf life; the
second time returns the previous answer directly.

## 为什么要有这个模块（2026-10-12）

用户原话：「现在用AI的地方越来越多 花费太快 …… 尽量降低费用」。

推演里"**同一件事被问两遍**"比想象中多得多：

| 什么时候 | 为什么会有两遍 |
|---|---|
| 重试 | 第一次输出被截断 → 上层重试（`llm/replies.ask` 的重试） |
| 同拍两阶段 | 导演先判一遍、场记再核一遍，**输入是同一段事实** |
| 作者重跑 | 「这一拍我不满意，重放一次」—— 输入一个字都没变 |
| 界面按钮 | 「刷新一下」被连点两下 |

这些请求**输入一模一样**，输出本来就该一样，**再发一次纯粹是烧钱**。
命中的时候一分钱不花、一次额度不占，而且**结果还是对的**（不是拿旧的顶上）。

## ⚠ 三条不许破的规矩

1. **只对白名单用途生效**（`LLM_DEDUP_PURPOSES`，默认判定 / 抽取 / 校对）。
   **说话、写正文、起名绝不在内** —— 那些要的正是"每次都不一样"，
   缓存会让全场人说着同一句话。这条是本模块存在的**前提**，不是可选项。
2. **key 必须覆盖所有影响输出的输入**（模型、消息、温度、上限、JSON、思考）。
   漏一个就会出现"改了温度却拿到老答案"这种最难查的 bug。
3. **过期就重算**（TTL，默认 1 小时）。设定会改、进度会变，老答案不能一直用 ——
   省钱不能省出"用半天前的结论回答现在的局面"。

## 谁用、怎么用

`llm/router.chat()` 在**真发请求之前**问一次 `key_for()` + `get()`，
拿到就**直接返回**（并广播一个 `dedup` 事件，界面据此说明"这一发是复用"）；
拿不到就照常发，回来后 `put()` 存起来。

    key = key_for(model=..., purpose=..., messages=...)
    if key and (hit := get(key)):
        return hit
    text = await real_call(...)
    if key and text:
        put(key, text)

[EN] ## Why this module exists (2026-10-12)
[EN] The user's words: "AI is used in more and more places and the cost is rising fast ... please
[EN] reduce the cost as much as possible".
[EN] In a simulation, "the same question asked twice" is far more common than one would think:
[EN] table: retry (first output truncated -> the upper layer retries), two stages of the same tick
[EN] (the director judges, then the continuity checker verifies -- **same facts in**), author replay
[EN] ("I don't like this tick, replay it" -- the input is byte-identical), double-clicked UI button.
[EN] Those requests have **identical input**, so the output should be identical too; **sending it
[EN] again is pure waste**. On a hit, no money is spent, no quota is used, and **the result is still
[EN] correct** (it is not "substituting an old answer").
[EN] ## ⚠ Three rules that must not be broken
[EN] 1. **Only whitelisted purposes take effect** (`LLM_DEDUP_PURPOSES`: judging / extraction /
[EN]    proofreading by default). **Speech, prose and naming are never included** -- those want
[EN]    "different every time", and caching would make the whole cast say the same line. This rule is
[EN]    the **premise** of this module, not an option.
[EN] 2. **The key must cover everything that affects the output** (model, messages, temperature,
[EN]    cap, JSON, thinking). Miss one and you get the hardest bug to trace: "changed the
[EN]    temperature but got the old answer".
[EN] 3. **Expire and recompute** (TTL, 1 hour by default). Settings change and progress moves; an
[EN]    old answer must not be reused forever -- saving money must not save you into "answering
[EN]    today's situation with a conclusion from half a day ago".
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict

from logger import get_logger

_LOG = get_logger('nws.dedup')

#: 最多记多少条。**必须有上限**：推演一天几百次调用，不设上限就是内存泄漏。
#  满了丢**最久没用过的**（LRU）—— 它也是最不可能被再问一次的。
# [EN] : how many entries to keep at most. **A cap is mandatory**: a day of simulation makes
# [EN] hundreds of calls, and without a cap it is a memory leak. When full, evict the **least
# [EN] recently used** (LRU) -- it is also the least likely to be asked again.
MAX_ENTRIES = 300

_LOCK = threading.Lock()
#: key → (存入时刻, 文本)。`OrderedDict` 是为了 LRU：命中时 `move_to_end`。
# [EN] key -> (stored_at, text). `OrderedDict` is for LRU: `move_to_end` on a hit.
_STORE: 'OrderedDict[str, tuple[float, str]]' = OrderedDict()
_STATS = {'hits': 0, 'misses': 0, 'stores': 0, 'expired': 0}
_MISS_KEYS: set[str] = set()          # remembered "asked but absent"; avoids recomputing keys


def _cfg_bool(key: str, dflt: bool) -> bool:
    try:
        from config import CFG
        return bool(CFG.b(key))
    except Exception:                                            # noqa: BLE001
        return dflt


def _cfg_int(key: str, dflt: int) -> int:
    try:
        from config import CFG
        return int(CFG.i(key))
    except Exception:                                            # noqa: BLE001
        return dflt


def _cfg_str(key: str, dflt: str) -> str:
    try:
        from config import CFG
        return str(CFG.s(key) or dflt)
    except Exception:                                            # noqa: BLE001
        return dflt


def enabled() -> bool:
    """总开关（`LLM_DEDUP_ENABLED`）。
        English:
    Master switch (`LLM_DEDUP_ENABLED`).
    """
    return _cfg_bool('LLM_DEDUP_ENABLED', True)


def ttl() -> float:
    """保质期（秒）。`0` = 不过期。
        English:
    Shelf life (seconds). `0` = never expires.
    """
    return float(max(0, _cfg_int('LLM_DEDUP_TTL_SECONDS', 3600)))


#: 内置的**默认可复用用途**（判定 / 抽取 / 校对一类）。
#: ⚠ 为什么要写在代码里当兜底（2026-10-12 实测的坑）：`CFG.s()` 对 **str 类型
#:   **不回落到 SPEC 默认值**（只有 bool/int/float/enum 会）—— 配置表里写了
#:   一长串默认白名单，`.env` 里没这一行时读出来却是**空串**，
#:   于是"白名单是空的"、复用**静默失效**（一点错都不报）。
#:   所以：**代码里给默认，配置项只当覆盖**（空 = 用这里的默认）。
# [EN] : the built-in **default reusable purposes** (judging / extraction / proofreading and the
# [EN] like).
# [EN] ⚠ Why the default must live in code (a real trap hit on 2026-10-12): `CFG.s()` does **not**
# [EN] fall back to the SPEC default for **str** (only bool/int/float/enum do) -- a long default
# [EN] whitelist written in the config table reads back as an **empty string** when `.env` has no
# [EN] such line, so "the whitelist is empty" and reuse **silently stops working** (not a single
# [EN] error is raised). So: **the default lives in code, the config item is only an override**
# [EN] (empty = use this default).
DEFAULT_PURPOSES = ('progress_eval,progress,genre,style,extract,book_scan,'
                    'compliance,day_verify,summary,day_summary,memory_compact')


def purposes() -> set[str]:
    """当前生效的白名单（配置为空就用内置默认）。
        English:
    The currently effective whitelist (empty config uses the built-in default).
    """
    raw = _cfg_str('LLM_DEDUP_PURPOSES', '') or DEFAULT_PURPOSES
    return {x.strip().lower() for x in str(raw).split(',') if x.strip()}


def allowed(purpose: str) -> bool:
    """这个用途允许复用吗（对照白名单）。

    ⚠ **认不出就说不允许**（白名单是"必须显式写上"的）—— 反过来的话，
      以后新加的创作类用途会被**默认缓存**，那是最坏的方向。
    
        English:
    Whether this purpose may be reused (against the whitelist).
        ⚠ **Unrecognized means not allowed** (the whitelist is "must be written explicitly") --
        [EN] otherwise a newly added creative purpose would be **cached by default**, the worst
        [EN] possible direction to err in.
    """
    p = (purpose or '').strip().lower()
    if not p:
        return False
    return p in purposes()


def _fingerprint(*, model: str, purpose: str, messages: list[dict],
                 temperature: float, max_tokens: int, json_mode: bool,
                 no_think: bool) -> str:
    """把"所有能改变输出的输入"压成一个短哈希。

    ★ 用**规范化后的 JSON**（`sort_keys` + 固定分隔符）而不是 `repr()`：
      字典的插入顺序、空格差异都会让同一个请求算出两个 key ——
      那样缓存命中率会莫名其妙地低，而且只在改了消息构造顺序时才现形。
    
        English:
    Squash "everything that can change the output" into a short hash.
        ★ Uses **normalized JSON** (`sort_keys` + fixed separators) rather than `repr()`: dict
          insertion order and whitespace differences would give the same request two keys -- the
          hit rate would then be inexplicably low, and it would only show up when the message
          assembly order changes.
    """
    payload = {
        'model': str(model or ''),
        'purpose': str(purpose or '').lower(),
        'temperature': round(float(temperature or 0.0), 4),
        'max_tokens': int(max_tokens or 0),
        'json': bool(json_mode),
        'no_think': bool(no_think),
        'messages': [{'role': str(m.get('role') or ''),
                      'content': str(m.get('content') or '')}
                     for m in (messages or [])],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:32]


def key_for(*, model: str, purpose: str, messages: list[dict],
            temperature: float = 0.0, max_tokens: int = 0,
            json_mode: bool = False, no_think: bool = False) -> str | None:
    """这一发请求的复用键；**不该复用就返回 `None`**（调用方据此完全跳过缓存）。

    返回 `None` 的三种情形：总开关关着、这个用途不在白名单里、没有消息。
    
        English:
    The reuse key for this request; **returns `None` when reuse does not apply** (the caller then
    skips caching entirely).
        Returns `None` in three cases: the master switch is off, the purpose is not whitelisted, or
        there are no messages.
    """
    if not enabled() or not messages:
        return None
    if not allowed(purpose):
        return None
    try:
        return _fingerprint(model=model, purpose=purpose, messages=messages,
                            temperature=temperature, max_tokens=max_tokens,
                            json_mode=json_mode, no_think=no_think)
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('算复用键失败（这一发就不复用）：%r', e)
        return None


def get(key: str | None) -> str | None:
    """拿上次的答案；没有 / 过期 / 开关关了都返回 `None`。

    过期的条目**就地删掉**（而不是留着占位）—— 否则 LRU 会把内存花在死条目上。
    
        English:
    Get the previous answer; `None` when absent / expired / disabled.
        Expired entries are **deleted in place** (rather than left occupying space) -- otherwise
        the LRU would spend memory on dead entries.
    """
    if not key or not enabled():
        return None
    age_limit = ttl()
    now = time.time()
    with _LOCK:
        item = _STORE.get(key)
        if item is None:
            _STATS['misses'] += 1
            return None
        stored_at, text = item
        if age_limit > 0 and (now - stored_at) > age_limit:
            _STORE.pop(key, None)
            _STATS['expired'] += 1
            _STATS['misses'] += 1
            return None
        _STORE.move_to_end(key)
        _STATS['hits'] += 1
    _LOG.info('同题复用命中（这一发不发请求、不计费）：purpose=%s', key[:8])
    return text


def put(key: str | None, text: str) -> None:
    """存下这次答案（空文本不存 —— 存了会把"失败"固化下来）。
        English:
    Store this answer (empty text is not stored -- storing it would freeze a failure).
    """
    if not key or not text or not str(text).strip():
        return
    if not enabled():
        return
    with _LOCK:
        _STORE[key] = (time.time(), str(text))
        _STORE.move_to_end(key)
        while len(_STORE) > MAX_ENTRIES:
            _STORE.popitem(last=False)
        _STATS['stores'] += 1


def clear() -> None:
    """清空（改了设定、要重跑同一段时手动清）。统计数不清 —— 那是"这次运行省了多少"。
        English:
    Clear (call manually after changing settings or to rerun a stretch). Stats are kept -- they
    [EN] are "how much this run saved".
    """
    with _LOCK:
        _STORE.clear()


def stats() -> dict:
    """这次运行复用了多少发。界面可以显示"省了 N 次调用"。
        English:
    How many requests this run reused. The UI can show "saved N calls".
    """
    with _LOCK:
        d = dict(_STATS)
    d['size'] = len(_STORE)
    d['enabled'] = enabled()
    d['ttl'] = ttl()
    return d
