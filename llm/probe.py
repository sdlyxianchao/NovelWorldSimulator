# -*- coding: utf-8 -*-
"""「这套模型配置到底能不能用」—— 配置界面用的连通性探针。

## 为什么不直接走 `llm.router`

三件事让它必须自成一路：

1. **要用界面上「刚填、还没保存」的值**。`router.chat()` 读的是 `CFG` 里
   已落盘的值 —— 用户改了 Base URL 或模型名，点「测试」时测的必须是**框里
   那个新值**，否则"测试通过"证明不了任何事（用户下一步就点保存，
   而保存后生效的是新的）。所以这里的 `base_url` / `api_key` 一律**显式传入**。
2. **不能碰账本，也不能被演示模式接管**。`MOCK_LLM=true` 时 `router` 直接返回
   内置假数据 —— 那"测试通过"就是假的。探针**永远真发请求**，并且不在
   token 账本里记账（试一下不该算进"今日花费"）。
3. **失败要摊开讲**。`router` 那套的设计目标是"调用方能继续跑"，异常在上层
   被吞掉、只留一行日志；而按钮要的是**屏幕上立刻出现一句能照着修的话**。
   所以这里返回的是 `ProbeResult.detail`（人话结论）+
   `raw`（HTTP 状态与服务端原话）+ `hint`（怎么修）。

## 一个真实教训（为什么这个模块值得存在）

2026-10-06 那轮推演里，`MODEL_DAILY=deepseek-v4-flash`（当时以为对、其实是旧名）
配着一个**默认开着思考**的模型，`progress_eval` 63 次调用里 8 次把 2000 token
**整份花在思考上**、正文一个字都没写出来，表现成"进度永远不推进、界面上没反应"。
查了很久才定位到"模型在思考"这件事。
—— 而一条「请只回两个字：收到」的测试请求就能当场看出来：
它会回你"通了，但正文是空的（思考把 32 token 用完了）"。

English:
"Is this model configuration actually usable" —— the connectivity probe used by the config UI.
## Why not just go through `llm.router`
Three things force it to be its own path:
1. **It must use the values "just entered, not yet saved" from the UI**. `router.chat()` reads the already-persisted values in `CFG`
   —— when the user changes the Base URL or model name and clicks "Test", what gets tested must be **the new value in the box**,
   otherwise "test passed" proves nothing (the user's next step is to click save,
   and after saving, the new value takes effect). So here `base_url` / `api_key` are always **passed explicitly**.
2. **It must not touch the ledger, nor be taken over by demo mode**. When `MOCK_LLM=true`, `router` directly returns
   built-in fake data —— then "test passed" is fake. The probe **always sends a real request**, and does not record
   in the token ledger (a try shouldn't count toward "today's spend").
3. **Failures must be laid out plainly**. The design goal of the `router` setup is "the caller can keep running", exceptions are
   swallowed at the upper layer leaving only one log line; but the button wants **a sentence appearing immediately on screen that one can fix by following**.
   So what's returned here is `ProbeResult.detail` (plain-language conclusion) +
   `raw` (HTTP status and server's raw words) + `hint` (how to fix).
## A real lesson (why this module deserves to exist)
In the 2026-10-06 round of simulation, `MODEL_DAILY=deepseek-v4-flash` (thought correct at the
time, actually an old name)
was paired with a model that has **thinking on by default**; of `progress_eval`'s 63 calls, 8
spent the full 2000 tokens
**entirely on thinking**, wrote not a single character of body text, and manifested as "progress
never advances, no reaction in the UI".
It took a long time to pinpoint that "the model is thinking".
—— And a test request like "please reply with just two words: received" would have shown it on
the spot:
it would reply "it's working, but the body is empty (thinking used up the 32 tokens)".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from config import CFG

# 探针的提示词与预算：**要小到能秒回，又要大到足以看出"正文是不是空的"**。
# 32 太小（思考型模型一个字的正文都写不出来也判不出来），128 又慢。
# [EN] Probe prompt and budget: **small enough to respond in seconds, yet large enough to reveal
# [EN] "whether the body is empty"**.
# [EN] 32 is too small (a thinking model won't write a single character of body text and can't be
# [EN] judged either), 128 is too slow.
PROBE_PROMPT = "请只回复两个字：收到"
PROBE_MAX_TOKENS = 64
# 服务端原话最多留这么多字（有些 4xx 会甩一整篇 HTML）
# [EN] Keep at most this many chars of the server's raw words (some 4xx responses dump an entire HTML
# [EN] page)
RAW_LIMIT = 300


# ══════════════════════════════════════════════════════════════════
#  结果对象
# [EN] Result object
# ══════════════════════════════════════════════════════════════════
@dataclass
class ProbeResult:
    """一次连通性探测的结果。`ok=False` 时 `detail` 就是给人看的错误信息。
        English:
    The result of one connectivity probe. When `ok=False`, `detail` is the human-readable error
    message.
    """

    ok: bool
    ms: int = 0
    status: int | None = None
    detail: str = ""          # 人话结论（ok 时是"通了…"，失败时是原因）
    raw: str = ""             # 服务端原话 / 异常原文（截断过）
    hint: str = ""            # 怎么修（没有就不显示）
    reply: str = ""           # ok 时模型真回的那句话
    # [EN] Plain-language conclusion (when ok, "it's working..."; on failure, the reason)
    # [EN] Server's raw words / exception text (truncated)
    # [EN] How to fix (not shown if absent)
    # [EN] The sentence the model actually returned when ok
    model: str = ""
    note: str = ""            # 额外观察（例如"正文为空，思考吃掉了额度"）
    # [EN] Extra observations (e.g. "body is empty, thinking ate up the budget")

    def line(self) -> str:
        """一行给人看的文字（界面直接显示这个）。
                English:
        A single line of human-readable text (the UI displays this directly).
        """
        parts = [('✅ ' if self.ok else '❌ ') + self.detail]
        if self.raw and not self.ok:
            parts.append(f'服务端原话：{self.raw}')
        if self.note:
            parts.append(self.note)
        if self.hint:
            parts.append(self.hint)
        return ' ｜ '.join(parts)


@dataclass
class ModelsResult:
    """拉取模型列表的结果。
        English:
    The result of fetching the model list.
    """

    ok: bool
    ids: list[str] = field(default_factory=list)
    ms: int = 0
    status: int | None = None
    detail: str = ""
    raw: str = ""
    hint: str = ""

    def line(self) -> str:
        if not self.ok:
            parts = ['❌ ' + self.detail]
            if self.raw:
                parts.append(f'服务端原话：{self.raw}')
            if self.hint:
                parts.append(self.hint)
            return ' ｜ '.join(parts)
        return f'✅ {self.detail}'


# ══════════════════════════════════════════════════════════════════
#  HTTP 状态 → 人话
# [EN] HTTP status → plain language
# ══════════════════════════════════════════════════════════════════
def _clip(s: str, n: int = RAW_LIMIT) -> str:
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n] + '…'


def explain_http(status: int, body: str, url: str) -> tuple[str, str]:
    """`(人话结论, 怎么修)`。

    ⚠ 判据顺序要紧：**先看状态码，再用原话细分**。同一个 400 既可能是
    "模型名不存在"也可能是"参数不合法"，服务端原话里有没有提到模型是区分点。

    ★ 关键词表是照**真实响应**收的，不是凭空想的。DeepSeek 在模型名写错时回的是：

        {"error":{"message":"The supported API model names are deepseek-flash,
          deepseek-v4-pro, but you passed no-such-model.","code":"invalid_request_error"}}

    这句话里既有 `supported ... model names`、也有 `invalid_request_error`，
    所以两个方向都要认 —— 只认 `invalid` 的话，对方换个措辞（比如说
    "The supported API model names are …" 而不带 code）就会掉进笼统那句，
    用户就看不到"是模型名的问题"这条最重要的线索了。
    
        English:
    `(plain-language conclusion, how to fix)`.
        ⚠ The order of the criteria matters: **first look at the status code, then use the raw words to narrow it down**. The same 400 could be
        "model name doesn't exist" or "invalid parameter"; whether the server's raw words mention the model is the distinguishing point.
        ★ The keyword table was collected from **real responses**, not made up. When the model name is wrong, DeepSeek returns:
            {"error":{"message":"The supported API model names are deepseek-flash,
              deepseek-v4-pro, but you passed no-such-model.","code":"invalid_request_error"}}
        This sentence contains both `supported ... model names` and `invalid_request_error`,
        so both directions must be recognized —— if only `invalid` is recognized, then when the other party changes wording (say
        "The supported API model names are ..." without the code), it falls into the generic sentence,
        and the user won't see the most important clue: "it's a model name problem".
    """
    low = (body or '').lower()
    path = url.split('://', 1)[-1].split('/', 1)[-1] if '://' in url else url

    if status == 400:
        model_words = ('not exist', 'not found', 'invalid', '不存在', '不支持',
                       'no such', 'unsupported', 'supported api model',
                       'unknown model', 'model not')
        if 'model' in low or '模型' in body:
            if any(w in low or w in body for w in model_words):
                return ('模型名不被服务端接受',
                        '这个模型名不在对方的可用列表里 —— 点上面的「拉取模型列表」'
                        '看它到底有哪些，或核对拼写')
        return ('请求被拒绝（参数或模型名不合法）',
                '核对模型名与 Base URL 是否配套')
    if status == 401:
        return ('API Key 被拒绝（401）', '检查 API Key 有没有抄全、有没有过期')
    if status == 402:
        return ('余额不足（402）', '到服务商后台充值后再试')
    if status == 403:
        return ('没有权限（403）', '这个 Key 可能没有调用该模型的权限')
    if status == 404:
        return (f'接口地址不存在（404）：{path}',
                'Base URL 要写到服务的根（OpenAI 兼容一般是 .../v1），'
                '别把它写成某个具体接口的地址')
    if status == 405:
        return ('方法不被允许（405）', 'Base URL 可能指错了服务')
    if status == 429:
        return ('被限流（429）', '等一会儿再试；也可能是免费额度用完了')
    if 500 <= status < 600:
        return (f'服务端出错（{status}）', '多半是对方暂时的故障，等一会儿再试')
    return (f'服务端返回 HTTP {status}', '')


def explain_network(exc: BaseException, url: str) -> tuple[str, str]:
    """网络层异常 → `(人话结论, 怎么修)`。
        English:
    Network-layer exception → `(plain-language conclusion, how to fix)`.
    """
    host = url.split('://', 1)[-1].split('/', 1)[0] if '://' in url else url
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout,
                        httpx.WriteTimeout, httpx.PoolTimeout)):
        return (f'超时：{type(exc).__name__}',
                '网络慢或被墙；也可以把「请求超时(秒)」调大一点')
    if isinstance(exc, httpx.ConnectError):
        return (f'连不上 {host}',
                '检查 Base URL 拼写、本机网络与代理设置'
                '（公司网络常需要代理才能出去）')
    if isinstance(exc, httpx.TooManyRedirects):
        return ('重定向太多', 'Base URL 可能指到了网页而不是 API 地址')
    if isinstance(exc, httpx.HTTPError):
        return (f'网络错误：{type(exc).__name__}: {exc}', '')
    return (f'出错了：{type(exc).__name__}: {exc}', '')


# ══════════════════════════════════════════════════════════════════
#  入口
# [EN] Entry point
# ══════════════════════════════════════════════════════════════════
def _missing(base_url: str, api_key: str, provider: str) -> str:
    """基础项没填齐时，直接说缺什么 —— 别真发请求（发了也是一句莫名其妙的 401）。
        English:
    When the basic fields aren't all filled in, just say what's missing —— don't actually send a
    request (sending one just yields a baffling 401).
    """
    if not (base_url or '').strip():
        return 'Base URL 是空的 —— 先在上面填上（OpenAI 兼容一般是 https://…/v1）'
    if provider != 'ollama' and not (api_key or '').strip():
        return 'API Key 是空的 —— 先在上面填上'
    return ''


def _headers(api_key: str) -> dict:
    h = {'Content-Type': 'application/json'}
    if (api_key or '').strip():
        h['Authorization'] = 'Bearer ' + api_key.strip()
    return h


async def list_models(*, base_url: str = None, api_key: str = None,
                      provider: str = None, timeout: float = None) -> ModelsResult:
    """拉取对方的可用模型列表（`GET {base}/models`）。

    `base_url` / `api_key` / `provider` 默认取 `CFG` 的值；界面传**框里当前的值**。
    
        English:
    Fetch the other party's available model list (`GET {base}/models`).
        `base_url` / `api_key` / `provider` default to the values in `CFG`; the UI passes **the current values in the box**.
    """
    base_url = (CFG.s('LLM_BASE_URL') if base_url is None else base_url) or ''
    api_key = (CFG.s('LLM_API_KEY') if api_key is None else api_key) or ''
    provider = provider or CFG.s('LLM_PROVIDER') or 'openai_compatible'
    timeout = float(timeout or CFG.i('LLM_TIMEOUT_SECONDS') or 30)

    if (why := _missing(base_url, api_key, provider)):
        return ModelsResult(ok=False, detail=why)

    url = base_url.strip().rstrip('/') + '/models'
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10)) as c:
            r = await c.get(url, headers=_headers(api_key))
    except BaseException as e:                                  # noqa: BLE001
        det, hint = explain_network(e, url)
        return ModelsResult(ok=False, ms=int((time.monotonic() - t0) * 1000),
                            detail=det, raw=f'{type(e).__name__}: {e}'[:RAW_LIMIT],
                            hint=hint)
    ms = int((time.monotonic() - t0) * 1000)
    if r.status_code != 200:
        det, hint = explain_http(r.status_code, r.text, url)
        return ModelsResult(ok=False, ms=ms, status=r.status_code,
                            detail=det, raw=_clip(r.text), hint=hint)
    ids = parse_model_ids(r.text)
    if not ids:
        return ModelsResult(ok=False, ms=ms, status=200,
                            detail='拉到了响应，但里面没有模型 id',
                            raw=_clip(r.text),
                            hint='对方可能不是 OpenAI 兼容的 /models 接口')
    return ModelsResult(ok=True, ids=ids, ms=ms, status=200,
                        detail=f'拉到 {len(ids)} 个可用模型（{ms} 毫秒）')


def parse_model_ids(text: str) -> list[str]:
    """从 `/models` 的响应里抠出模型名。

    **三种形状都要认**（换一家服务就换一种，认不出就等于"拉不到"）：
      · OpenAI 兼容：`{"data": [{"id": "..."}, ...]}`
      · 有些网关：`{"data": {"models": [{"name": "..."}]}}` / `{"models": [...]}`
      · 极简：`{"data": ["a", "b"]}`
    
        English:
    Extract the model names from the `/models` response.
        **All three shapes must be recognized** (switching to another service switches the shape; if unrecognized it's as good as "can't fetch"):
          · OpenAI-compatible: `{"data": [{"id": "..."}, ...]}`
          · Some gateways: `{"data": {"models": [{"name": "..."}]}}` / `{"models": [...]}`
          · Minimal: `{"data": ["a", "b"]}`
    """
    import json
    try:
        d = json.loads(text)
    except Exception:                                           # noqa: BLE001
        return []
    pool = None
    if isinstance(d, dict):
        for k in ('data', 'models'):
            v = d.get(k)
            if isinstance(v, list):
                pool = v
                break
            if isinstance(v, dict):
                inner = v.get('models') or v.get('data')
                if isinstance(inner, list):
                    pool = inner
                    break
    elif isinstance(d, list):
        pool = d
    if not pool:
        return []
    out: list[str] = []
    for it in pool:
        if isinstance(it, str):
            name = it
        elif isinstance(it, dict):
            name = it.get('id') or it.get('name') or it.get('model') or ''
        else:
            name = ''
        name = str(name).strip()
        # 去重但保序（同一家服务常有别名指同一个模型）
        # [EN] Deduplicate but preserve order (the same service often has aliases pointing to the same model)
        if name and name not in out:
            out.append(name)
    return sorted(out)


async def probe_model(model: str, *, base_url: str = None, api_key: str = None,
                      provider: str = None, timeout: float = None,
                      can_disable_thinking: bool = None) -> ProbeResult:
    """试发一条最小请求，回答"这个模型名现在能不能用"。

    `can_disable_thinking`：要不要带 `thinking:{"type":"disabled"}`。
    **默认按模型名自己判**（`llm.capabilities.detect_thinking_switch`）——
    思考型模型不关思考时，64 token 会**整份花在思考上**，正文为空，
    看着像"测试失败"，其实链路是通的。带上它才能测出真实结论。
    
        English:
    Send a minimal request to answer "can this model name be used right now?".
        `can_disable_thinking`: whether to include `thinking:{"type":"disabled"}`.
        **Default is determined by the model name itself** (`llm.capabilities.detect_thinking_switch`) ——
        when a thinking model does not disable thinking, the 64 tokens are **entirely spent on thinking**, the body is empty,
        and it looks like a "test failure", but the pipeline is actually working. Only by including it can you test the real conclusion.
    """
    model = (model or '').strip()
    base_url = (CFG.s('LLM_BASE_URL') if base_url is None else base_url) or ''
    api_key = (CFG.s('LLM_API_KEY') if api_key is None else api_key) or ''
    provider = provider or CFG.s('LLM_PROVIDER') or 'openai_compatible'
    timeout = float(timeout or CFG.i('LLM_TIMEOUT_SECONDS') or 30)

    if not model:
        return ProbeResult(ok=False, model=model, detail='这个档位还没填模型名')
    if (why := _missing(base_url, api_key, provider)):
        return ProbeResult(ok=False, model=model, detail=why)

    if can_disable_thinking is None:
        from llm.capabilities import detect_thinking_switch
        can_disable_thinking = bool(detect_thinking_switch(model))

    body: dict = {'model': model, 'max_tokens': PROBE_MAX_TOKENS,
                  'messages': [{'role': 'user', 'content': PROBE_PROMPT}]}
    if can_disable_thinking:
        body['thinking'] = {'type': 'disabled'}

    url = base_url.strip().rstrip('/') + '/chat/completions'
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10)) as c:
            r = await c.post(url, json=body, headers=_headers(api_key))
    except BaseException as e:                                  # noqa: BLE001
        det, hint = explain_network(e, url)
        return ProbeResult(ok=False, ms=int((time.monotonic() - t0) * 1000),
                           model=model, detail=det,
                           raw=f'{type(e).__name__}: {e}'[:RAW_LIMIT], hint=hint)
    ms = int((time.monotonic() - t0) * 1000)
    if r.status_code != 200:
        det, hint = explain_http(r.status_code, r.text, url)
        return ProbeResult(ok=False, ms=ms, status=r.status_code, model=model,
                           detail=det, raw=_clip(r.text), hint=hint)

    try:
        d = r.json()
        ch = (d.get('choices') or [{}])[0]
        msg = ch.get('message') or {}
    except Exception as e:                                      # noqa: BLE001
        return ProbeResult(ok=False, ms=ms, status=200, model=model,
                           detail='返回的不是 JSON —— 这个地址可能不是 API',
                           raw=_clip(r.text), hint=f'{type(e).__name__}: {e}')

    # ★★ 2026-10-19：**探测也要记账**。
    #   它走的是这里自己建的 httpx（不经 `llm/router.Ledger`），而它确实发了一次
    #   chat 请求 —— 每次换模型都探一遍，几十上百次攒起来就不是 0 了。
    #   ⚠ 记的是**这一次真实请求**的 token（服务端给了就用它），不是"探一次算 1 次"。
    #   ⚠ 失败不记（失败那次通常没产生计费），也**不许抛**（探测是给界面看连通性的，
    #     不该因为记账库被锁就说"模型连不上"）。
    # [EN] ★★ 2026-10-19: **probes are recorded too.** They use this module's own httpx (bypassing
    # [EN] `llm/router.Ledger`) and they do send a real chat request -- every model switch probes
    # [EN] once, and dozens to hundreds add up. ⚠ Record the **actual** token usage of this request
    # [EN] (from the response), not "one probe = 1 call". ⚠ Failures are not recorded and this must
    # [EN] **never throw** (probing reports connectivity; a locked bookkeeping DB must not read as
    # [EN] "the model is unreachable").
    try:
        from llm import usage as _U
        _u = (d.get('usage') or {}) if isinstance(d, dict) else {}
        _U.record(model=str(model or ''), purpose='probe',
                  in_tok=int(_u.get('prompt_tokens') or 0),
                  out_tok=int(_u.get('completion_tokens') or 0),
                  cost=0.0, tier='probe')
    except Exception:                                            # noqa: BLE001
        pass

    text = (msg.get('content') or '').strip()
    reasoning = (msg.get('reasoning_content') or '')
    if not text:
        # ⚠ **这是本项目踩过的那个坑**：HTTP 200、链路全通，但正文是空的。
        #   原因是思考型模型把 max_tokens 整份吃在思维链上（`finish_reason=length`）。
        #   说"测试失败"是错的，说"测试通过"也是错的 —— 要把这件事本身讲出来。
        # [EN] ⚠ **This is the pit this project stepped in**: HTTP 200, the whole chain works, but the body is
        # [EN] empty.
        # [EN] The cause is a thinking model consuming the entire max_tokens on the chain of thought
        # [EN] (`finish_reason=length`).
        # [EN] Saying "the test failed" is wrong, and saying "the test passed" is also wrong —— this fact
        # [EN] itself must be stated.
        note = ('正文为空：这个模型把 %d token 全花在思考上（finish=%s）——'
                '链路是通的，但它默认开着思考；程序里靠「思考开关」这类用途处理'
                % (PROBE_MAX_TOKENS, ch.get('finish_reason')))
        if reasoning:
            note += f'（本次思考 {len(reasoning)} 字）'
        return ProbeResult(ok=True, ms=ms, status=200, model=model,
                           detail=f'连通（{ms} 毫秒），但模型没有输出正文',
                           note=note, reply='')
    return ProbeResult(ok=True, ms=ms, status=200, model=model, reply=text,
                       detail=f'连通（{ms} 毫秒）',
                       note=('（这个模型会输出思考内容）' if reasoning else ''))


# ══════════════════════════════════════════════════════════════════
#  启动时：到底配了模型没有
# [EN] At startup: whether a model is configured at all
# ══════════════════════════════════════════════════════════════════
def llm_ready(cfg=None, *, base_url: str = None, api_key: str = None,
              provider: str = None, models: list[str] = None) -> tuple[bool, str]:
    """`(能不能真的联网跑, 不能的话缺什么)`。

    判据只有**静态配置**，一次请求都不发 —— 启动时不能卡在网络上。
    "Key 填错了"这类只能靠界面上的「测试」按钮发现，这里管的是
    **压根没配**（第一次装好、什么都没填）那种情况。

    几个参数都可显式传入：**界面上"填了但还没保存"的值也要能判**
    （保存时用它决定要不要把自动开的演示模式收回去）。
    
        English:
    `(whether it can actually run online, and if not, what is missing)`.
        The criterion is only **static config**, and not a single request is sent —— startup must not get stuck on the network.
        Things like "the Key was filled in wrong" can only be discovered via the "Test" button in the UI; what is handled here is
        **not configured at all** (freshly installed, nothing filled in) that kind of situation.
        Several parameters can all be passed explicitly: **values that are "filled in but not yet saved" in the UI must also be judgable**
        (at save time it is used to decide whether to retract the automatically enabled demo mode).
    """
    cfg = cfg or CFG
    provider = (provider or cfg.s('LLM_PROVIDER') or 'openai_compatible').strip()
    base_url = (cfg.s('LLM_BASE_URL') if base_url is None else base_url) or ''
    api_key = (cfg.s('LLM_API_KEY') if api_key is None else api_key) or ''
    if models is None:
        models = [(cfg.s(k) or '') for k in
                  ('MODEL_FRONT', 'MODEL_DAILY', 'MODEL_CHEAP')]
    if not base_url.strip():
        return False, '没有填 Base URL'
    if provider != 'ollama' and not api_key.strip():
        return False, '没有填 API Key'
    if not any((m or '').strip() for m in models):
        return False, '三个档位的模型名都是空的'
    return True, ''


def missing_model_notice(why: str) -> str:
    """没配模型时的提示语（**要把"会跑假数据"这件事说清楚**）。
        English:
    The prompt text when no model is configured (**must make clear that "fake data will run"**).
    """
    from i18n import t
    return t('尚未配置模型（{why}）—— 本次只提供演示数据与模拟运行，'
             '不会调用真实 AI。到「天机 · 推演服务LLM设定」填好 Base URL 与 API Key，'
             '用「拉取模型列表」挑一个模型、用「测试」确认连通即可。',
             why=t(why))
