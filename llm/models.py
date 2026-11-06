# -*- coding: utf-8 -*-
"""模型登记表 —— 一个程序里可以配**多个模型**，谁用哪个由「Agent → 模型」决定。

## 为什么要有这一层

用户 2026-10-12 的原话：

> 「我发现只用一种模型是不足以较好的完成任务，Deepseek小说能力不足。
>   我希望你根据不同Agent的功能，结合不同模型的能力，推荐不同的模型。」
> 「把现在的两个LLM设置合并到一起，改成可以配置多个模型……
>   后续LLM不再针对特定功能进行模型配置。」

所以从这一天起，`.env` 里那套「一个 Base URL + 一个 API Key + 三档模型名」
不再是**唯一**的配置方式，而是变成登记表里的一条迁移来源。

## 四个概念，别混

| 概念 | 是什么 | 存在哪 |
|---|---|---|
| **模型条目** `ModelEntry` | 一个**能调用的服务**：显示名 + 接口地址 + 密钥 + 模型名 | `llm_models.json` |
| **默认模型** | 谁都没指定时用哪一个（`.env` 的 `LLM_DEFAULT_MODEL`） | `.env` |
| **三档** | 「华彩/日常/摘要」三个**快速配置**槽位，按档位挑模型 | `.env` 的 `MODEL_FRONT/DAILY/CHEAP` |
| **Agent 绑定** | 某个职位**点名**用哪个模型（覆盖它的档位） | `agents/<slug>.md` 的 `model:` |

## 解析顺序（`resolve()`，唯一入口）

```
① Agent 点名了模型（且那个条目还在）        → 用它
② 该 Agent 所属档位配了模型（华彩/日常/摘要） → 用它
③ 默认模型                                  → 用它
④ 登记表里的第一条                          → 用它
⑤ 一条都没有                               → 返回 None（走老路：全局地址 + CFG.model_of）
```

第 ⑤ 条是**向后兼容**的保险：老用户升级上来、还没打开过新界面时，一切照旧。

## 两条不许改的规矩

1. **`resolve()` 绝不在缺配置时抛异常。** 它的调用方是每一发 LLM 请求，
   抛出去等于"整个程序因为少填一个框而停摆"。拿不到就返回 `None`，让上层走老路。
2. **写盘一律走 `atomic_write_text`**，且**读不动就当空表**（不许因为 JSON 坏了
   让程序起不来）—— 这份文件是用户手也可能去改的。

English:
Model registry — one program can have **several models**, and who uses which is decided by
"Agent -> model".
## Why this layer exists
The user's exact words (2026-10-12):
> "I found that using only one model is not enough to do the job well; DeepSeek's novel ability
> is insufficient. I want you to recommend different models for different Agents based on their
> functions and the models' strengths."
> "Merge the current two LLM settings into one, change it to allow configuring multiple models...
>  afterwards the LLM [page] no longer configures models per function."
So from this day on, the ".env" set of "one Base URL + one API Key + three tier model names" is no
longer the **only** way to configure things; it becomes one migration source for the registry.
## Four concepts, don't mix them
| Concept | What it is | Where it lives |
|---|---|---|
| **Model entry** `ModelEntry` | one **callable service**: display name + endpoint + key + model name | `llm_models.json` |
| **Default model** | which one to use when nobody specified anything (`LLM_DEFAULT_MODEL`) | `.env` |
| **Three tiers** | three **quick-config** slots ("flourish/daily/summary") picking a model per tier | `MODEL_FRONT/DAILY/CHEAP` |
| **Agent binding** | a position **explicitly** picks a model (overrides its tier) | `model:` in `agents/<slug>.md` |
## Resolution order (`resolve()`, the only entry point)
(1) Agent named a model (and that entry still exists) -> use it
(2) the tier that Agent belongs to has a model -> use it
(3) the default model -> use it
(4) the first entry in the registry -> use it
(5) nothing at all -> return None (legacy path: global endpoint + CFG.model_of)
Item (5) is the **backward-compatibility** safety net.
## Two rules that must not change
1. **`resolve()` never raises on missing config** — its caller is every LLM request; raising would
   mean "the whole program stalls because one box wasn't filled in".
2. **Writes always go through `atomic_write_text`**, and **an unreadable file is treated as empty**
   (a corrupt JSON must not stop the program) — this file may be hand-edited by the user.
"""
from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from config import APP_DIR, CFG
from util.io import atomic_write_text

_LOG = logging.getLogger("nws.llm.models")

#: 登记表文件名（程序根目录下，与 `.env` 同级）。
#  ⚠ **它是用户数据**（里面是 API Key），已在 `.gitignore` 里忽略。
# [EN] : Registry file name (in the program root, next to `.env`).
# [EN] ⚠ **It is user data** (it holds API keys) and is ignored in `.gitignore`.
FILE_NAME = 'llm_models.json'

#: 允许的接入协议（与 `LLM_PROVIDER` 同一套取值）。
# [EN] : Allowed protocols (same value set as `LLM_PROVIDER`).
PROVIDERS = ('openai_compatible', 'ollama')

#: 模型条目里的能力开关（与 `llm/capabilities.CAP_KEYS` 一一对应）。
#  ⚠ **不在这里 import capabilities** —— 那是"知识库 + 启动纠偏"，它自己会 import
#    config，两边在启动期互相拉扯容易出循环。这里只留键名，取值时再懒加载。
# [EN] : Capability switches on a model entry (one-to-one with `llm/capabilities.CAP_KEYS`).
# [EN] ⚠ **capabilities is not imported here** — that module is "knowledge base + startup
# [EN] correction" and itself imports config; the two pulling on each other at startup easily
# [EN] creates a cycle. Only key names live here; the real values are lazily loaded.
CAP_FIELDS = ('LLM_CAP_IMAGE', 'LLM_CAP_REASONING', 'LLM_CAP_THINKING',
              'LLM_CAP_JSON_MODE', 'LLM_CAP_SYSTEM_ROLE')

#: 三档的键（与 `.env` 里的 `MODEL_*` 同名）。
# [EN] : Keys of the three tiers (same names as `MODEL_*` in `.env`).
TIER_FIELDS = ('MODEL_FRONT', 'MODEL_DAILY', 'MODEL_CHEAP')
TIER_ZH = {'MODEL_FRONT': '华彩档', 'MODEL_DAILY': '日常档', 'MODEL_CHEAP': '摘要档'}

#: 每一档**是干什么用的**（界面上"先解释再配置"，用户 2026-10-12：
#: 「三档单独解释下 再配置」）。
#: ★ 为什么要解释：三档的名字（华彩/日常/摘要）像黑话 —— 用户不知道
#:   "我的人物说话算哪一档"，于是要么乱配、要么不敢动。写清楚"哪些调用落在这一档、
#:   大概占多少量"，他才知道该给哪一档配贵模型。
#:   ⚠ 这里写的**量级**与 `llm/router.py` 里 `NO_THINK_PURPOSES` 那张表无关，
#:     是从"哪一类调用归到哪一档"的既有实现里数出来的比例（约 15% / 55% / 30%）。
# [EN] What each tier is **for** (the UI "explain before configuring"; user, 2026-10-12: "explain the
# [EN] three tiers individually, then configure").
# [EN] ★ Why explain: the names (flourish/daily/summary) are jargon -- users do not know "which tier
# [EN] does my character speaking fall into", so they either misconfigure or dare not touch it. Spelling
# [EN] out "which calls land here, and roughly what share of the volume" is what tells them which tier
# [EN] deserves an expensive model.
# [EN] ⚠ The magnitudes written here are not tied to the `NO_THINK_PURPOSES` table in `llm/router.py`;
# [EN] they are the shares counted from the existing mapping of calls to tiers (~15% / 55% / 30%).
# [EN] : what each tier is **for** (the UI "explain before configuring"; user, 2026-10-12: "explain
# [EN] the three tiers individually, then configure").
# [EN] ★ Why explain: the names are jargon, so users cannot tell "which tier does my character
# [EN] speaking fall into" and either misconfigure or dare not touch it. Spelling out "which calls
# [EN] land here and roughly what share" is what tells them which tier deserves an expensive model.
# [EN] ⚠ The magnitudes are the shares counted from the existing mapping of calls to tiers
# [EN] (~15% / 55% / 30%).
TIER_WHY: dict[str, str] = {
    'MODEL_FRONT': ('**关键场面的那几步**（约 15% 的调用量）：重要对话、反思、'
                    '故事文档、运行小结。这些地方"差一点"看得出来 —— 想让故事好看，'
                    '钱花在这里。'),
    'MODEL_DAILY': ('**常规循环**（约 55%）：人物决策、台词、导演派活 —— '
                    '量最大的一档。它决定的是"故事跑不跑得动"，'
                    '不一定要最贵的，但太差会明显水。'),
    'MODEL_CHEAP': ('**压缩、打分、后台**（约 30%）：记忆摘要、进度判断、'
                    '校对、抽取。这些只要**一个结论**，便宜档往往做得一样好 —— '
                    '省钱最先该动这一档。'),
}

#: 登记表路径的**测试接管点**（判据/探针要隔离，绝不许写用户的真文件）。
#  ⚠ 生产代码**不要**动它；要换路径请用 `use_path()` 这个上下文管理器。
# [EN] : Test takeover point for the registry path (criteria/probes must isolate, never write the
# [EN] user's real file). ⚠ Production code must not touch it; to change the path use `use_path()`.
_PATH: Path | None = None

#: 当前「谁在用模型」——由 `use()` 设置，`resolve()` 读取。
#  ★ 用 `ContextVar` 而不是全局变量：并行决策（`asyncio.gather`）里多个 Agent
#    同时在跑，全局变量会互相踩。
# [EN] : "Who is using the model right now" — set by `use()`, read by `resolve()`.
# [EN] ★ Uses `ContextVar` rather than a global: in parallel decisions (`asyncio.gather`) several
# [EN] Agents run at once and a global would cross-contaminate.
_ACTIVE: ContextVar[str] = ContextVar('nws_active_agent', default='')


def path() -> Path:
    """登记表路径。
        English:
    Registry path.
    """
    return _PATH or (APP_DIR / FILE_NAME)


@contextmanager
def use_path(p: Path | str | None) -> Iterator[None]:
    """临时把登记表换到别处（**判据与探针专用**）。
        English:
    Temporarily point the registry elsewhere (**for criteria and probes only**).
    """
    global _PATH
    old = _PATH
    _PATH = Path(p) if p else None
    try:
        yield
    finally:
        _PATH = old


def pin_path(p: Path | str | None) -> None:
    """把登记表**钉**在别处，直到进程结束（**判据专用，用完不用还原**）。

    ★★★ 为什么它与 `use_path` 是两件事，而不是"一个够用"（2026-10-22 事故）：
      `use_path` 是 `with` 块，**块一退出路径就还原**。而写盘发生在**按钮回调**里
      （用户点了保存、或判据点了一下）—— 那时 `with` 早已退出、路径又指回真实文件。
      于是"用 with 包住了打开编辑框那一下"看起来是隔离了，实际一个字节都没隔离：
      判据点了一次保存，把用户的 `llm_models.json`（4 条模型，其中两条的密钥**只存在于
      那个文件里**）覆盖成只剩一条夹具条目。
      ⇒ 需要一种"**活到进程结束**"的钉法：判据在 import 时钉一次，之后任何写都写副本。

    ⚠ 传 `None` 表示还原到默认位置。

        English:
    **Pin** the registry somewhere else until the process exits (criteria only, no restore needed).
    ★★★ Why this is a separate thing from `use_path` (the 2026-10-22 incident): `use_path` is a
      `with` block, so **the path is restored the moment the block exits**. But the write happens in a
      **button callback** (the user clicks Save, or the criterion clicks it) -- by then `with` has
      exited and the path points back at the real file. So "wrapping the editor-open call in a with"
      looked like isolation while isolating nothing: one Save click replaced the user's
      `llm_models.json` (4 models, two of whose keys existed **only in that file**) with a single
      fixture entry. => A pin that **lives for the whole process** is what's needed.
    ⚠ Passing `None` restores the default location.
    """
    global _PATH
    _PATH = Path(p) if p else None


# ══════════════════════════════════════════════════════════════════════
#  数据
# [EN] Data
# ══════════════════════════════════════════════════════════════════════
@dataclass
class ModelEntry:
    """一条模型记录：**一个能调用的服务**。

    `key` 是**稳定标识**（存进 `.env` 与 `agents/*.md` 的就是它）——
    ⚠ 别拿 `label` 当键：显示名会改（"混元 Hy3" → "混元 Hy3 正式版"），
    键一改，所有指向它的 Agent 绑定就全断了。

        English:
    One model record: **a callable service**.
        `key` is the **stable identifier** (what gets stored into `.env` and `agents/*.md`) --
        ⚠ don't use `label` as the key: display names change ("Hunyuan Hy3" -> "Hunyuan Hy3 release");
        once the key changes, every Agent binding pointing at it breaks.
    """

    key: str
    label: str = ''                 # 显示名（界面上那一行）
    model: str = ''                 # 发给服务端的模型名（如 hy3 / deepseek-v4-pro）
    base_url: str = ''              # 写到 /v1 这一层（程序自己接 /chat/completions）
    # [EN] Display name (the line shown in the UI)
    # [EN] Model name sent to the server (e.g. hy3 / deepseek-v4-pro)
    # [EN] Write to the /v1 level (the program appends /chat/completions itself)
    api_key: str = ''
    provider: str = 'openai_compatible'
    note: str = ''                  # 备注（写给人看：这家是谁给的、什么时候过期）
    # [EN] Display name (that row in the UI) / model name sent to the server / endpoint /
    # [EN] api key / protocol / human-readable note
    caps: dict[str, bool] = field(default_factory=dict)
    #: 这条是不是**从旧配置迁移出来的**（界面上标一下，让用户知道它从哪来）。
    # [EN] : whether this was **migrated from the old config** (the UI tags it so users know where
    # [EN] it came from).
    migrated: bool = False
    # ── 单价（元 / 百万 token）── 2026-10-12 加，为了**多模型下把账算准**。
    #   `-1` = **没填**（那就按 `llm/tokens.py` 的内置表查，查不到用兜底价）。
    #   为什么要能自己填：内置表只是抄录的参考值，**价格一直在动**
    #   （DeepSeek 2026-08-17 刚把缓存命中价调了 11 倍），只有你自己的账单是真的。
    # [EN] -- Unit prices (CNY per million tokens) -- added 2026-10-12 to **make the books
    # [EN] accurate across several models**.
    # [EN] `-1` = **not filled** (then look up the built-in table in `llm/tokens.py`, falling back
    # [EN] to the default price). Why you should be able to fill it in: the built-in table is only a
    # [EN] transcribed reference, and **prices keep moving** (DeepSeek changed its cache-hit rate 11x
    # [EN] on 2026-08-17); only your own bill is real.
    price_hit: float = -1.0         # 缓存命中输入
    price_miss: float = -1.0        # 缓存未命中输入
    price_out: float = -1.0         # 输出
    # ── 这一家怎么连（2026-10-12 从「天问 · 通用参数」搬过来）──
    #   `-1` = **没填**，用全局兜底（`LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES`）。
    #   ★ 为什么该按模型配：这两项**本来就是"这一家服务"的脾气** —— 有的服务慢
    #     （推理模型想两分钟很正常），有的爱 429；全程序一个超时值只会两边都不合适。
    #     用户 2026-10-12：「通用按数（参数）的这部分去掉 分到各个模型配置里」。
    # [EN] -- how to reach this provider (moved here 2026-10-12 from "Tianji · General
    # [EN] parameters") --
    # [EN] `-1` = **not filled**, use the global fallback (`LLM_TIMEOUT_SECONDS` /
    # [EN] `LLM_MAX_RETRIES`).
    # [EN] ★ Why per model: these two **are the temperament of that one service** -- some are slow (a
    # [EN] reasoning model taking two minutes is normal), some love HTTP 429; one program-wide timeout
    # [EN] value suits neither. User, 2026-10-12: "remove that general-parameters part, distribute it
    # [EN] into each model's configuration".
    timeout: float = -1.0           # 请求超时（秒）
    retries: int = -1               # 最大重试次数
    # [EN] Cache-hit input / cache-miss input / output

    @property
    def has_price(self) -> bool:
        """这条填过价没有（**至少要有一个输入价或输出价**才算填）。
                English:
        Whether this entry has prices (**at least one input or output price counts**).
        """
        return float(self.price_miss) >= 0 or float(self.price_out) >= 0

    def price_tuple(self) -> tuple[float, float, float]:
        """给计价器用的三段价 `(命中, 未命中, 输出)`；**没填的位置补 -1**（那边会兜底）。
                English:
        The three-part price for the calculator `(hit, miss, output)`; **unfilled spots are -1**
        (the calculator falls back).
        """
        return (float(self.price_hit), float(self.price_miss), float(self.price_out))

    def price_label(self) -> str:
        """界面上那一行单价（没填就说没填 —— 别显示成 0，那会让人以为免费）。
                English:
        The unit-price line shown in the UI (say so when unfilled -- never show 0, which would
        make people think it is free).
        """
        if not self.has_price:
            return ''
        def _f(x: float) -> str:
            return f'{float(x):g}'
        hit = '—' if float(self.price_hit) < 0 else _f(self.price_hit)
        miss = '—' if float(self.price_miss) < 0 else _f(self.price_miss)
        out = '—' if float(self.price_out) < 0 else _f(self.price_out)
        return f'{hit}/{miss}/{out}'

    def display(self) -> str:
        """界面上那一行显示什么（名字 + 模型名，一眼能对上服务商）。
                English:
        What that row shows in the UI (name + model name, so the provider is obvious at a glance).
        """
        lbl = (self.label or '').strip() or self.key
        mdl = (self.model or '').strip()
        return f'{lbl}（{mdl}）' if mdl and mdl != lbl else lbl


def _slug(text: str) -> str:
    """把显示名压成一个稳定的键（中英混排也能用）。
        English:
    Squash a display name into a stable key (works for mixed Chinese/English too).
    """
    t = (text or '').strip().lower()
    t = re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '-', t).strip('-')
    return t or 'model'


def from_dict(d: dict[str, Any]) -> ModelEntry:
    """从 JSON 里的一条读成对象（**缺字段补默认，绝不抛**）。
        English:
    Read one JSON object into an entry (**missing fields default, never raise**).
    """
    caps = d.get('caps') if isinstance(d.get('caps'), dict) else {}
    key = str(d.get('key') or '').strip() or _slug(str(d.get('label') or d.get('model') or ''))
    prov = str(d.get('provider') or 'openai_compatible').strip()

    def _num(name: str) -> float:
        """读一个价格字段：**读不出就 -1（= 没填）**，绝不让一条坏数据毁掉整张表。
                English:
        Read one price field: **unreadable becomes -1 (unfilled)**; a bad value must never
        break the whole table.
        """
        v = d.get(name)
        if v is None or v == '':
            return -1.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return -1.0

    return ModelEntry(
        key=key,
        label=str(d.get('label') or '').strip(),
        model=str(d.get('model') or '').strip(),
        base_url=str(d.get('base_url') or '').strip(),
        api_key=str(d.get('api_key') or '').strip(),
        provider=prov if prov in PROVIDERS else 'openai_compatible',
        note=str(d.get('note') or '').strip(),
        caps={str(k): bool(v) for k, v in caps.items()},
        migrated=bool(d.get('migrated')),
        price_hit=_num('price_hit'),
        price_miss=_num('price_miss'),
        price_out=_num('price_out'),
        timeout=_num('timeout'),
        retries=int(_num('retries')),
    )


def to_dict(e: ModelEntry) -> dict[str, Any]:
    """写进 JSON 的形状。
        English:
    Shape written into the JSON.
    """
    d = asdict(e)
    if not d.get('caps'):
        d.pop('caps', None)
    if not d.get('note'):
        d.pop('note', None)
    if not d.get('migrated'):
        d.pop('migrated', None)
    # 没填的价格不落盘（`-1` 落进去只会让文件变脏，读回来也是"没填"）。
    # [EN] Unfilled prices are not written to disk (a `-1` would only dirty the file; it reads back
    # [EN] as "unfilled" anyway).
    for k in ('price_hit', 'price_miss', 'price_out', 'timeout', 'retries'):
        if float(d.get(k, -1) or -1) < 0:
            d.pop(k, None)
    return d


# ══════════════════════════════════════════════════════════════════════
#  读写
# [EN] Read / write
# ══════════════════════════════════════════════════════════════════════
def load() -> list[ModelEntry]:
    """读登记表。**读不动就当空表**（返回 `[]`，不抛）。
        English:
    Read the registry. **Unreadable is treated as empty** (returns `[]`, does not raise).
    """
    p = path()
    try:
        if not p.exists():
            return []
        raw = p.read_text(encoding='utf-8')
        data = json.loads(raw) if raw.strip() else []
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('模型登记表读不动（按空表处理）：%r', e)
        return []
    items = data.get('models') if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: list[ModelEntry] = []
    seen: set[str] = set()
    for row in items:
        if not isinstance(row, dict):
            continue
        e = from_dict(row)
        if not e.key or e.key in seen:
            continue
        seen.add(e.key)
        out.append(e)
    return out


def save(entries: list[ModelEntry]) -> None:
    """写登记表（原子写）。`ensure_ascii=False` 让中文名字在文件里看得懂。
        English:
    Write the registry (atomic). `ensure_ascii=False` keeps Chinese names readable in the file.
    """
    p = path()
    payload = {'version': 1, 'models': [to_dict(e) for e in entries]}
    atomic_write_text(p, json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                      encoding='utf-8')


def migrate_from_env() -> list[ModelEntry]:
    """把 `.env` 里那套**老配置**整理成登记表。

    老配置的形状是「一个地址 + 一个 Key + 三个模型名」，所以这里按**模型名去重**：
    同一个名字出现在两档里（比如日常档与摘要档都是 `deepseek-flash`）只留一条。
    新条目的 `key` 用模型名 slug（`deepseek-flash`），这样 `.env` 里
    `MODEL_DAILY=deepseek-flash` 这种**旧值直接就是合法的新键** —— 迁移后
    三档配置一个字都不用改。

        English:
    Turn the **old** config in `.env` into a registry.
        The old shape is "one endpoint + one key + three model names", so this dedupes by **model
        name**: the same name appearing in two tiers (e.g. daily and summary both
        `deepseek-flash`) yields one entry.
        The new entry's `key` is the model-name slug (`deepseek-flash`), so an **old value like
        `MODEL_DAILY=deepseek-flash` is directly a valid new key** -- after migration none of the
        three tier settings need changing.
    """
    base = CFG.s('LLM_BASE_URL').strip()
    key = CFG.s('LLM_API_KEY').strip()
    prov = CFG.s('LLM_PROVIDER').strip() or 'openai_compatible'
    names: list[str] = []
    for f in TIER_FIELDS:
        n = CFG.s(f).strip()
        if n and n not in names:
            names.append(n)
    if not base and not key and not names:
        return []
    if not names:
        names = ['（未命名模型）']
    out: list[ModelEntry] = []
    for n in names:
        out.append(ModelEntry(key=_slug(n), label=n, model=n, base_url=base,
                              api_key=key, provider=prov, migrated=True,
                              note='从「天问 · LLM 接入」的旧配置迁移而来'))
    return out


def ensure_ready() -> list[ModelEntry]:
    """读登记表；**空表就先用内存里的迁移结果**（不写盘）。

    ⚠ 这里**故意不落盘**：写盘这件事只在用户真的在界面上动过之后发生
      （`save()`）。程序启动时偷偷把 `.env` 抄一份成 JSON，用户会莫名多出一个
      文件、而且删了下次又回来。

        English:
    Read the registry; **if empty, use the in-memory migration result** (no disk write).
        ⚠ This **deliberately does not write to disk**: the write only happens after the user has
        actually changed something in the UI (`save()`). Silently copying `.env` into a JSON at
        startup would surprise the user with an extra file that comes back if deleted.
    """
    cur = load()
    if cur:
        return cur
    return migrate_from_env()


# ══════════════════════════════════════════════════════════════════════
#  默认模型 / 三档
# [EN] Default model / three tiers
# ══════════════════════════════════════════════════════════════════════
def default_key() -> str:
    """默认模型（`.env` 的 `LLM_DEFAULT_MODEL`，可能是空）。
        English:
    The default model (`.env`'s `LLM_DEFAULT_MODEL`, may be empty).
    """
    return CFG.s('LLM_DEFAULT_MODEL').strip()


def tier_key(tier_field: str) -> str:
    """某一档配的是哪个模型。
        English:
    Which model a given tier is configured with.
    """
    if tier_field not in TIER_FIELDS:
        return ''
    return CFG.s(tier_field).strip()


def tier_of_agent(agent_key: str) -> str:
    """这个职位属于哪一档（读 `agents/<slug>.md` 的 `tier`）。

    ⚠ **任何异常都退回「日常档」** —— 这个函数在每一发请求的路径上，
      拿不到就是拿不到，不许把请求打挂。

        English:
    Which tier this position belongs to (reads `tier` from `agents/<slug>.md`).
        ⚠ **Any exception falls back to "daily"** -- this function is on the path of every request;
        if it can't get it, it can't get it, and it must not break the request.
    """
    try:
        from crew import catalog as CAT
        spec = CAT.get(str(agent_key))
        t = str(getattr(spec, 'tier', '') or '').strip()
        return f'MODEL_{t.upper()}' if t in ('front', 'daily', 'cheap') else 'MODEL_DAILY'
    except Exception:                                            # noqa: BLE001
        return 'MODEL_DAILY'


def agent_model_key(agent_key: str) -> str:
    """这个职位**点名**要用的模型键（空 = 没点名，跟着档位走）。
        English:
    The model key this position **explicitly** wants (empty = nothing named, follow the tier).
    """
    try:
        from crew import catalog as CAT
        spec = CAT.get(str(agent_key))
        return str(getattr(spec, 'model', '') or '').strip()
    except Exception:                                            # noqa: BLE001
        return ''


def find(spec: str, entries: list[ModelEntry] | None = None) -> ModelEntry | None:
    """按「键 → 模型名 → 显示名」找一条记录。找不到返回 `None`。

    ★ 后两种是**兼容**用的：`.env` 里老值是模型名（`deepseek-flash`），
      而用户手改 `agents/*.md` 时也可能直接写模型名。

        English:
    Find an entry by "key -> model name -> display name". Returns `None` if not found.
        ★ The latter two are for **compatibility**: old `.env` values are model names
        (`deepseek-flash`), and a user hand-editing `agents/*.md` might write a model name too.
    """
    s = str(spec or '').strip()
    if not s:
        return None
    items = load() if entries is None else entries
    for e in items:
        if e.key == s:
            return e
    for e in items:
        if e.model and e.model == s:
            return e
    for e in items:
        if e.label and e.label == s:
            return e
    return None


@dataclass
class Resolved:
    """一发请求最终落在**哪个服务、哪个模型**上。
        English:
    Which **service and model** a single request finally lands on.
    """

    key: str
    label: str
    model: str
    base_url: str
    api_key: str
    provider: str
    caps: dict[str, bool]
    #: 哪一步定下来的（`agent` / `tier` / `default` / `first` / `legacy`）——
    #: 界面与日志靠它回答"这一发为什么用了这个模型"。
    # [EN] : which step decided it (`agent` / `tier` / `default` / `first` / `legacy`) --
    # [EN] the UI and logs use it to answer "why did this request use this model".
    source: str = 'first'
    #: 这一条**自己填的**三段单价 `(命中, 未命中, 输出)`；`-1` = 这一段没填。
    #: 计价时**填了的用填的、没填的用内置表**（见 `llm/tokens.py::price_of`），
    #: 所以"只知道输出价"也能填一半。
    # [EN] : this entry's own three-part prices `(hit, miss, output)`; `-1` = that part is unfilled.
    # [EN] When pricing, **filled parts are used and unfilled parts come from the built-in table**
    # [EN] (see `llm/tokens.py::price_of`), so "only knowing the output price" can fill half.
    prices: tuple[float, float, float] = (-1.0, -1.0, -1.0)
    #: 这一家的超时与重试；`-1` = 用全局兜底（见 `ModelEntry.timeout`）。
    # [EN] : this provider's timeout and retries; `-1` = use the global fallback (see
    # [EN] `ModelEntry.timeout`).
    timeout: float = -1.0
    retries: int = -1


#: 解析结果的缓存键：(登记表 mtime, 大小, 默认, 三档, agent)。
#  ⚠ 缓存的是**条目**不是 `Resolved`：能力表要按当次模型现算。
# [EN] : Cache key for resolution: (registry mtime, size, default, tiers, agent).
# [EN] ⚠ The cache holds **entries**, not `Resolved`: the capability table is computed per model.
_RESOLVE_CACHE: dict[tuple, list[ModelEntry]] = {}


def _entries_cached() -> list[ModelEntry]:
    """带 mtime 指纹的 `ensure_ready()`（每一发请求都调它，不缓存就是每发读一次盘）。
        English:
    `ensure_ready()` with an mtime fingerprint (called on every request; without a cache it would
    read the disk every time).
    """
    p = path()
    try:
        st = p.stat()
        sig = (str(p), int(st.st_mtime_ns), int(st.st_size))
    except Exception:                                            # noqa: BLE001
        sig = (str(p), 0, 0)
    key = (sig, CFG.s('LLM_DEFAULT_MODEL'), CFG.s('MODEL_FRONT'),
           CFG.s('MODEL_DAILY'), CFG.s('MODEL_CHEAP'))
    hit = _RESOLVE_CACHE.get(key)
    if hit is not None:
        return hit
    out = ensure_ready()
    _RESOLVE_CACHE.clear()
    _RESOLVE_CACHE[key] = out
    return out


def price_overrides(entries: list[ModelEntry] | None = None,
                    ) -> dict[str, tuple[float, float, float]]:
    """登记表里**填过价**的条目 → `{模型名: (命中, 未命中, 输出)}`，喂给计价器。

    ⚠ 键是**模型名**（发给服务端的那个），不是条目 `key` —— 计价只看模型名
      （账本里存的也是模型名）。两条不同条目指向同一个模型名时，**后配的赢**。
    
        English:
    Entries in the registry that **have prices filled in** -> `{model name: (hit, miss, output)}`,
    fed to the price calculator.
        ⚠ The key is the **model name** (the one sent to the server), not the entry `key` -- pricing
          only looks at the model name (the ledger stores model names too). When two entries point
          at the same model name, **the later one wins**.
    """
    out: dict[str, tuple[float, float, float]] = {}
    for e in (entries if entries is not None else _entries_cached()):
        if e.has_price:
            name = (e.model or e.key or '').strip()
            if name:
                out[name] = e.price_tuple()
    return out


def caps_for(model: str, entry_caps: dict[str, bool] | None = None) -> dict[str, bool]:
    """这一条**自己声明过**的能力开关（**只返回它写过的键**）。

    ★★ 2026-10-12 改口径（`verify_llm_caps` 抓到 3 条红之后查出来的）：
      以前这里**把"按模型名判出来的知识库事实"也塞进返回值**，于是调用方
      `router.chat()` 里的 `_res.caps.get(k, CFG.b(k))` **永远取不到全局开关** ——
      结果是天问「模型能力」那一节的四个开关**全成了死控件**：
      用户勾掉「支持 JSON 模式」，请求里照样带 `response_format`；
      用户勾上「推理模型」，`temperature` 照样发出去。

      为什么那样写是错的：知识库事实有**别的通道**进入系统 ——
      启动时 `capabilities.check_capabilities(apply=True)` 会把事实**写回全局开关**
      （界面上也写着"不一致会改回并记进消息"）。所以全局开关**本身就是事实的载体**；
      这里再塞一遍，只会把用户的显式选择盖掉。

    ⚠ 而「用户显式选择」并没有丢：模型编辑框保存时会**把当时判出来的事实
      一整套写进 `entry.caps`**（见 `gui/app_flet._model_editor`），
      所以从界面上加/改过的条目本来就有完整的一套；只有"从旧 `.env` 迁移来的"
      条目是空的 —— 那种正好该退回全局开关。

        English:
    The capability switches **this entry itself declared** (**only the keys it wrote**).
        ★★ 2026-10-12 changed the rule (after `verify_llm_caps` went red on 3 assertions): this used
          to **stuff the "knowledge-base facts detected from the model name" into the return value as
          well**, so the caller's `_res.caps.get(k, CFG.b(k))` in `router.chat()` **never reached the
          global switches** -- making all four switches in Tianji's "model capabilities" section **dead
          controls**: uncheck "supports JSON mode" and the request still carries `response_format`;
          check "reasoning model" and `temperature` is still sent.
          Why that was wrong: the knowledge-base facts have **another channel** into the system --
          at startup `capabilities.check_capabilities(apply=True)` **writes the facts back into the
          global switches** (the UI even says "mismatches are corrected and reported in Messages"). So
          the global switches **are** the carrier of the facts; duplicating them here only overrides
          the user's explicit choice.
        ⚠ And the "explicit choice" is not lost: when the model editor saves, it **writes the whole set
          of facts detected at that moment into `entry.caps`** (see `gui/app_flet._model_editor`), so
          entries added or edited through the UI already carry a full set; only entries **migrated from
          an old `.env`** have none -- and those are exactly the ones that should fall back to the global
          switches.
    """
    out: dict[str, bool] = {}
    for k, v in (entry_caps or {}).items():
        if k in CAP_FIELDS:
            out[k] = bool(v)
    return out


def resolve(agent_key: str = '', tier: str = 'daily',
            entries: list[ModelEntry] | None = None) -> Resolved | None:
    """这一发请求该用哪个模型（**唯一入口**，见模块头那张顺序表）。

    `agent_key` 不传时，用 `use()` 设的「当前在出工的那一位」。
    `tier` 是 `front` / `daily` / `cheap`（老接口，保留）。

        English:
    Which model this request should use (**the only entry point**, see the order table at the top).
        When `agent_key` isn't given, use the "who is currently working" set by `use()`.
        `tier` is `front` / `daily` / `cheap` (the old interface, kept).
    """
    items = _entries_cached() if entries is None else entries
    who = str(agent_key or _ACTIVE.get() or '').strip()

    def _mk(e: ModelEntry, src: str) -> Resolved:
        return Resolved(key=e.key, label=e.label or e.key, model=e.model or e.key,
                        base_url=e.base_url, api_key=e.api_key, provider=e.provider,
                        caps=caps_for(e.model or e.key, e.caps), source=src,
                        prices=e.price_tuple(),
                        timeout=float(e.timeout), retries=int(e.retries))

    # ① Agent 点名
    # [EN] ① Agent specifies it by name
    if who:
        ent = find(agent_model_key(who), items)
        if ent is not None:
            return _mk(ent, 'agent')
    # ② 档位（有 Agent 就用**它自己的档**，没有就看调用方传的 tier）
    # [EN] ② Tier (if there is an Agent, use **its own tier**; otherwise use the tier passed by the caller)
    tf = tier_of_agent(who) if who else f'MODEL_{str(tier or "daily").upper()}'
    if tf not in TIER_FIELDS:
        tf = 'MODEL_DAILY'
    ent = find(tier_key(tf), items)
    if ent is not None:
        return _mk(ent, 'tier')
    # ③ 默认模型
    # [EN] ③ Default model
    ent = find(default_key(), items)
    if ent is not None:
        return _mk(ent, 'default')
    # ④ 第一条
    # [EN] ④ First one
    if items:
        return _mk(items[0], 'first')
    # ⑤ 一条都没有 → 走老路
    # [EN] ⑤ None at all → fall back to the old path
    return None


@contextmanager
def use(agent_key: str) -> Iterator[None]:
    """「下面这一段的 LLM 调用都算这个 Agent 的」。

    ★ 只在**唯一入口**处设一次就够（剧组是 `crew/studio.Studio.call`，
      四个系统服务是各自的编排函数）—— 在这一段里发生的所有调用
      （含 `llm.replies.ask()` 的内部重试）都会用这个 Agent 的模型。

        English:
    "All LLM calls in the following block belong to this Agent."
        ★ Setting it once at the **single entry point** is enough (the crew uses
        `crew/studio.Studio.call`; the four system services use their own orchestration
        functions) — every call happening in this block (including the internal retries of
        `llm.replies.ask()`) uses this Agent's model.
    """
    tok = _ACTIVE.set(str(agent_key or ''))
    try:
        yield
    finally:
        _ACTIVE.reset(tok)


def active() -> str:
    """当前在出工的是谁（没有就是空串）。
        English:
    Who is working right now (empty string if nobody).
    """
    return _ACTIVE.get()


def agent(key: str):
    """装饰器：**这个协程（含它调用的子协程）里的 LLM 调用都算这个 Agent 的**。

    为什么要有它：四个系统服务（开卷摄取 / 记忆摘要 / 进度评估 / 合规复核）
    不是"一个方法里调一次模型"，而是**一次编排里散着好几次调用**
    （还夹着 `asyncio.gather` 的并发分支）。给每个调用点手写一遍 `use()`
    迟早就漏一处 —— 漏掉的那一处会**悄悄用回默认模型**，账单上完全看不出来。
    挂在整个编排函数的门口，一处就够。

    ⚠ 用 `functools.wraps` 保住函数自己的元信息：本项目有判据按函数名/
      签名去查（`inspect.iscoroutinefunction` 之类），丢了会静默变假。

        English:
    Decorator: **all LLM calls inside this coroutine (including sub-coroutines it awaits) count as
    this Agent's**.
        Why it exists: the four system services (book ingest / memory summarization / progress
        evaluation / compliance review) are not "one model call inside one method" but **several
        calls scattered across one orchestration** (with concurrent branches via `asyncio.gather`).
        Hand-writing `use()` at each call site will eventually miss one -- and the missed one
        **quietly falls back to the default model**, completely invisible in the bill. Hanging it at
        the door of the whole orchestration function covers everything.
        ⚠ `functools.wraps` preserves the function's own metadata: this project has criteria that
        look things up by function name/signature (`inspect.iscoroutinefunction` and the like), and
        losing them silently turns those into false negatives.
    """
    import functools

    def _wrap(fn):
        if not callable(fn):
            return fn

        @functools.wraps(fn)
        async def _inner(*a, **kw):
            with use(key):
                return await fn(*a, **kw)

        return _inner

    return _wrap


# ══════════════════════════════════════════════════════════════════════
#  界面要用的几个小工具
# [EN] A few helpers the UI needs
# ══════════════════════════════════════════════════════════════════════
def options(*, include_default: bool = True) -> list[tuple[str, str]]:
    """给下拉框用的 `[(值, 显示文字)]`。

    ★ **「默认」永远排第一**（值 = 空串）—— 用户点开一个 Agent 想改模型时，
      最常见的选择是"跟大家一起用默认的那个"。

        English:
    `[(value, display text)]` for a dropdown.
        ★ **"Default" is always first** (value = empty string) -- when a user opens an Agent to
        change its model, the most common choice is "follow the default like everyone else".
    """
    out: list[tuple[str, str]] = []
    if include_default:
        out.append(('', '（默认）'))
    for e in ensure_ready():
        if not (e.model or e.key):
            continue
        out.append((e.key, e.display()))
    return out


def summary_line() -> str:
    """一行状态：配了几个模型、默认是哪个（给界面顶部那行小字用）。
        English:
    One status line: how many models are configured and which is the default (for the small text at
    the top of the UI).
    """
    items = ensure_ready()
    if not items:
        return ''
    d = find(default_key(), items)
    dname = (d.display() if d else (items[0].display()))
    return f'{len(items)} 个模型 · 默认：{dname}'


def duplicate_key(label: str, *, entries: list[ModelEntry] | None = None) -> str:
    """给一个新条目取一个不冲突的键。
        English:
    Produce a non-conflicting key for a new entry.
    """
    items = load() if entries is None else entries
    used = {e.key for e in items}
    base = _slug(label)
    if base not in used:
        return base
    i = 2
    while f'{base}-{i}' in used:
        i += 1
    return f'{base}-{i}'
