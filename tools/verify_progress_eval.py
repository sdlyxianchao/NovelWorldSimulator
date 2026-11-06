# -*- coding: utf-8 -*-
"""验证：进度评估（`progress_eval`）的预算 / 关思考 / **不许静默降级**。

用户 2026-10-06 拿着一屏日志来问：「是不是设置问题 还是代码问题？」
日志里 7 分钟出现 **8 条**同一个告警：

    LLM 一个字都没拿到（max_tokens=2000 全被用光，共 2000 token，含思考内容）
    purpose=progress_eval model=deepseek-flash

查下来是三件事**叠在一起**，本脚本逐条钉住：

  ① **模型侧**：`.env` 里 `MODEL_DAILY`/`MODEL_CHEAP = deepseek-flash`
     （DeepSeek V4 Flash），它**默认开着思考模式**，而**思考是连 max_tokens
     一起吃的**。直连复现（`developers/probe_thinking.py` 同款探针）：
     问它「请判断：阿福被掌柜收留了吗？」，它思考 3233 token、正文 **0 字**，
     `finish_reason=length`；加上 `thinking:{"type":"disabled"}` 之后
     **61 token 就答完了**。一个 6 行的判定问题，快 50 倍。
  ② **知识库侧**：`llm/capabilities.py` 里**没有** `deepseek-flash` 这个名字，
     于是它落到笼统的 `deepseek` 上被判成**非推理模型** —— 用户 `.env` 里
     `LLM_CAP_REASONING=false` 就是这么来的：**声明与事实不符**。
     同时代码里**根本没有关掉思考这条路**，用户从界面上也没处可调。
  ③ **代码侧（最要命的一条）**：`director/evaluate_progress` 是**每拍都调**的
     用途，却 ① 吃 `llm.chat()` 默认的 2000 预算；② 绕过了 v1.43 建的统一
     容错通道 `llm.replies.ask()`（截断/空 → 上限翻倍重试 → 抢救）；
     ③ **把"没拿到"和"判据确实没满足"返回成同一个值** `(False, "")`。
     于是"模型把额度吃光了"表现成"故事还没走到那儿"：
     **节点永远不推进，而界面上一个字都没有**（本项目一直在打击的沉默降级）。

对应改动：`llm/router.NO_THINK_PURPOSES`（结论型用途关思考，按
`llm/capabilities.CAP_THINKING` 决定发不发）× `director.engine.ProgressVerdict`
（拿不到就 `ok=False`，不许冒充"不满足"）× `sim/loop._check_progress`
（连续 3 拍拿不到就讲给用户听）。

⚠ 本脚本是**纯逻辑**的：不发真请求、不弹窗、不建项目（打桩 client 抓请求体）。
   「改完在真机上是不是真的不再爆预算」另有一次直连实测，记在
   `logs/`（`developers/probe_thinking.py` 的输出）。

用法：.venv\\Scripts\\python.exe tools/verify_progress_eval.py
产出：assets/screenshots/progress_eval_report.json

English:
Verification: progress evaluation (`progress_eval`) budget / disable thinking / **no silent
degradation**.
On 2026-10-06 the user came with a screenful of logs and asked: "Is this a settings issue or a
code issue?"
In the logs, in 7 minutes the same warning appeared **8 times**:
    LLM got not a single character (max_tokens=2000 all used up, 2000 tokens total, including thinking content)
    purpose=progress_eval model=deepseek-flash
Investigation found three things **stacked together**; this script pins down each one:
  ① **Model side**: in `.env`, `MODEL_DAILY`/`MODEL_CHEAP = deepseek-flash`
     (DeepSeek V4 Flash), it **has thinking mode enabled by default**, and **thinking shares the max_tokens
     budget**. Direct reproduction (same probe as `developers/probe_thinking.py`):
     asking it "Please judge: was A-Fu taken in by the shopkeeper?", it thought 3233 tokens, body text **0 chars**,
     `finish_reason=length`; after adding `thinking:{"type":"disabled"}`
     **it answered in just 61 tokens**. A 6-line judgment question, 50x faster.
  ② **Knowledge base side**: `llm/capabilities.py` does **not** have the name `deepseek-flash`,
     so it falls back to the generic `deepseek` and is judged a **non-reasoning model** - the user's `.env`
     `LLM_CAP_REASONING=false` comes from exactly this: **declaration does not match reality**.
     At the same time, the code has **no path to turn off thinking at all**, and the user has nowhere in the UI to adjust it.
  ③ **Code side (the most critical one)**: `director/evaluate_progress` is called **every beat**
     for this purpose, yet ① it eats `llm.chat()`'s default 2000 budget; ② it bypasses the unified
     fault-tolerance channel `llm.replies.ask()` built in v1.43 (truncated/empty → double the limit and retry → salvage);
     ③ **it returns "didn't get it" and "criteria really not met" as the same value** `(False, "")`.
     So "the model burned through the budget" manifests as "the story hasn't reached there yet":
     **the node never advances, and there is not a single word in the UI** (the silent degradation this project has been fighting all along).
Corresponding changes: `llm/router.NO_THINK_PURPOSES` (conclusion-type purposes disable
thinking, decided by
`llm/capabilities.CAP_THINKING` whether to send it) × `director.engine.ProgressVerdict`
(if it can't get it then `ok=False`, not allowed to masquerade as "not satisfied") ×
`sim/loop._check_progress`
(if it can't get it 3 beats in a row, tell the user).
⚠ This script is **pure logic**: it sends no real requests, pops no dialogs, creates no projects
(it stubs the client to capture request bodies).
   "Whether it really stops blowing the budget on the real machine after the fix" has a separate direct live test, recorded in
   `logs/` (the output of `developers/probe_thinking.py`).
Usage: .venv\\Scripts\\python.exe tools/verify_progress_eval.py
Output: assets/screenshots/progress_eval_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import verify_ui_common as VU                                  # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'false')       # A 组要打桩 client 看**真实请求体**
# [EN] Group A needs to stub the client to see the **real request body**
# ★★★ 2026-10-22：**两层缓存都必须关掉**（A1 时红时绿的真正原因）。
#   A 组要判的是"**请求体里**带没带 thinking"，而缓存命中时**根本不发请求** ——
#   `fake.body` 是 None ⇒ 判据说"没带"。更糟的是：这个脚本打桩拿到的
#   **假答复会被写进跨会话共享缓存**（`router.chat` 的 `_dkey` 分支只看
#   `MOCK_LLM`，打桩的 client 与真 client 在它眼里一模一样），
#   于是 ① 用户机器上多出一条 `{"满足": false}` 的假答案；② 下一次跑这个脚本
#   直接命中它、又红一遍 —— **"每次都在报同一个没修好的错"，其实是判据自己留下的。**
# [EN] ★★★ 2026-10-22: **both cache layers must be off** (the real reason A1 flip-flopped).
# [EN] Group A judges "does the **request body** carry thinking", but a cache hit sends **nothing**,
# [EN] so `fake.body` is None and the criterion says "not carried". Worse: the stubbed reply gets
# [EN] written into the **cross-session shared cache** (`router.chat`'s `_dkey` branch only looks at
# [EN] `MOCK_LLM`; a stubbed client looks exactly like a real one), so (1) the user's machine gains a
# [EN] fake `{"满足": false}` answer, and (2) the next run hits it and goes red again -- "it reports the
# [EN] same unfixed error every time" was the criterion leaving it there itself.
CFG.set('LLM_DEDUP_ENABLED', 'false')
CFG.set('LLM_CACHE_ENABLED', 'false')
CFG.set('LLM_CAP_JSON_MODE', 'true')
CFG.set('LLM_CAP_SYSTEM_ROLE', 'true')
CFG.set('LLM_CAP_REASONING', 'true')
CFG.set('LLM_CAP_THINKING', 'true')

from i18n import set_lang                                   # noqa: E402
set_lang('zh')

# `S.NOTE` 的字面量是 `'note'`（小写）—— 别凭印象写 `'NOTE'`，
# 那种"恒假"的判据会一直绿着骗人（本项目踩过）。
# [EN] The literal for `S.NOTE` is `'note'` (lowercase) -- don't write `'NOTE'` from memory,
# [EN] that kind of "always false" predicate will stay green forever and lie to you (this project has
# [EN] been burned by it).
from display.script import NOTE as NOTE_KIND                # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:500]})
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  打桩工具
# [EN] Stubbing tool
# ══════════════════════════════════════════════════════════════
class FakeWorld:
    """`evaluate_progress` 只读 `current_node_info()`；

    ⚠ `DirectorEngine.__init__` 还会读 `world.clock`（`_game_min()` 算停滞窗口）
    —— 假桩要把**全部可观察效果**都模仿到，漏一个就在构造时炸
    （"打桩要模仿全部可观察效果"是本项目的老规矩）。
    
        English:
    `evaluate_progress` only reads `current_node_info()`;
        ⚠ `DirectorEngine.__init__` also reads `world.clock` (`_game_min()` computes the stagnation window)
        - the stub must imitate **all observable effects**; miss one and it blows up at construction
        ("a stub must imitate all observable effects" is an old rule of this project).
    """

    # 用**哨兵**而不是 `None` 表示"要默认值"：`None` 在这个测试里是
    # 「项目压根没有进度表」，两者必须分得开（C11 就是靠它）。
    # [EN] Use a **sentinel** instead of `None` to mean "use the default": `None` in this test is
    # [EN] "the project has no progress table at all" -- the two must be distinguishable (C11 depends on
    # [EN] it).
    DEFAULT = {
        '名称': '楼前失忆',
        '完成判据': '阿福被掌柜收留，随楼迁徙并替鬼客了结未了之事。',
        # ★ 2026-10-27：**章数下限**生效之后，夹具必须说清这一站要几章 ——
        #   不写就按篇幅档兜底（这里连 `篇幅` 都没有 ⇒ 默认档「中」⇒ 3 章），
        #   于是"判据满足了"也会被闸门按住，D5/D6 看到的就不再是它们要验的那件事。
        #   ⚠ 这里填 1，是因为这一支判据验的是"**判满足了就推进**"，
        #     不是"演不够章数不许推进" —— 后者由 `verify_length_plan` 的 G 组专测，
        #     两边各守一道闸，别互相稀释。
        # [EN] ★ 2026-10-27: once the **minimum-chapter gate** exists, a fixture must say how many
        # [EN] chapters its station needs -- otherwise the tier fallback applies (no `篇幅` here =>
        # [EN] default "medium" => 3) and the gate holds even when the criterion is met, so D5/D6
        # [EN] stop measuring what they exist to measure. ⚠ 1 here because this verifier checks
        # [EN] "**criterion met -> advance**", not "short chapters -> hold"; the latter is guarded
        # [EN] by group G of `verify_length_plan`. One gate each; don't dilute them.
        '章数': 1,
    }

    class _Clock:
        minutes = 0
        day = 1

    def __init__(self, node=DEFAULT) -> None:
        self._info = node
        self.clock = FakeWorld._Clock()

    def current_node_info(self):
        return self._info

    def clock_display(self) -> str:
        return '第1天 · 辰时'


class FakeDB:
    def __init__(self, events=None) -> None:
        self._events = events if events is not None else [{'content': '阿福擦门柱。'}]

    def recent_events(self, n: int = 5) -> list:
        return self._events[:n]


class FakeDisplay:
    """`_push_narrative` 会 `asyncio.create_task(display.enqueue_narrative(...))`。
        English:
    `_push_narrative` will `asyncio.create_task(display.enqueue_narrative(...))`.
    """

    async def enqueue_narrative(self, *a, **kw) -> None:
        return None


class FakeChat:
    """替换 `llm.chat`：按脚本回话，并把每次参数记下来。
        English:
    Replace `llm.chat`: reply according to the script, and record the arguments each time.
    """

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def __call__(self, tier, messages, **kw):
        self.calls.append({'tier': tier, 'messages': messages, **kw})
        i = min(len(self.calls) - 1, len(self.replies) - 1)
        text = self.replies[i]
        meta = {'truncated': not text.strip(), 'empty_output': not text.strip(),
                'has_reasoning': not text.strip(),
                'finish_reason': 'length' if not text.strip() else 'stop',
                'max_tokens': kw.get('max_tokens'), 'no_think': kw.get('no_think'),
                'purpose': kw.get('purpose'), 'tier': tier}
        return (text, meta) if kw.get('return_meta') else text


class FakeDirector:
    """给循环用的假导演：按脚本依次给结论，用完了就一直给最后一条。
        English:
    The fake director for the loop: give conclusions in order per the script, and once exhausted
    keep giving the last one.
    """

    def __init__(self, verdicts: list) -> None:
        self.verdicts = list(verdicts)
        self._i = 0

    async def evaluate_progress(self, recent_events):
        i = min(self._i, len(self.verdicts) - 1)
        self._i += 1
        return self.verdicts[i]

    def advance_node(self):
        return None

    def is_at_end(self) -> bool:
        return True


def engine_for(node=FakeWorld.DEFAULT):
    from director.engine import DirectorEngine
    return DirectorEngine(FakeWorld(node), FakeDB())


# ══════════════════════════════════════════════════════════════
#  A. 请求体：结论型用途关思考，别的用途不关
# [EN] A. Request body: conclusive-purpose uses turn off thinking, others don't
# ══════════════════════════════════════════════════════════════
def test_no_think_body() -> bool:
    ok = True
    from llm.router import llm, NO_THINK_PURPOSES

    class _Resp:
        status_code = 200
        # ⚠ 2026-10-26：`router._post_plain` 现在会读 `resp.text` 去判"这家服务是不是没钱了"
        #   （`CREDIT.detect`）。替身少这一个属性 ⇒ 直接 AttributeError，
        #   整个脚本在第一次假调用就崩，后面的判据一条都跑不到。
        # [EN] `router._post_plain` now reads `resp.text` to detect "this provider is out of
        # [EN] credit" (`CREDIT.detect`). Without it the double raises AttributeError on the very
        # [EN] first fake call and no later criterion even runs.
        text = '{"choices":[{"finish_reason":"stop","message":{"content":"{}"}}]}'

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {'choices': [{'finish_reason': 'stop',
                                 'message': {'content': '{"满足": false}'}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}

    class _Client:
        def __init__(self) -> None:
            self.body = None

        # ★ 2026-10-12：同上 —— _real_call 现在逐发传 headers。
        # [EN] 2026-10-12: same as above -- _real_call now passes headers per request.
        async def post(self, url, json=None, headers=None, timeout=None):
            self.body = json
            return _Resp()

    async def _run() -> None:
        nonlocal ok
        saved = (llm._client, llm._sem, llm._started, llm._loop)
        fake = _Client()
        llm._client = fake
        llm._sem = asyncio.Semaphore(4)
        llm._started = True
        llm._loop = asyncio.get_running_loop()
        try:
            # (a) 结论型用途 + 支持关思考 → 带 thinking
            # [EN] (a) conclusive-purpose use + supports disabling thinking -> include thinking
            CFG.set('LLM_CAP_THINKING', 'true')
            fake.body = None
            await llm.chat('cheap', [{'role': 'user', 'content': 'hi'}],
                           purpose='progress_eval', json_mode=True)
            ok = rec('A1 ★ 结论型用途（progress_eval）请求体带 '
                     'thinking:{"type":"disabled"}',
                     (fake.body or {}).get('thinking') == {'type': 'disabled'},
                     json.dumps(sorted((fake.body or {}).keys()),
                                ensure_ascii=False))
            # (b) ★ 闸门：模型不支持关思考 → **一个字都不发**（会 400）
            # [EN] (b) ★ Gate: model doesn't support disabling thinking -> **send not a single character** (would
            # [EN] 400)
            CFG.set('LLM_CAP_THINKING', 'false')
            fake.body = None
            await llm.chat('cheap', [{'role': 'user', 'content': 'hi'}],
                           purpose='progress_eval', json_mode=True)
            ok &= rec('A2 ★★ LLM_CAP_THINKING=false 时不发 thinking'
                      '（不认识这个参数的模型会 400）',
                      'thinking' not in (fake.body or {}),
                      json.dumps(sorted((fake.body or {}).keys()),
                                 ensure_ascii=False))
            # (c) 要写东西的用途 → 不关（思考对它们有用）
            # [EN] (c) Uses that need to write something -> don't disable (thinking helps them)
            CFG.set('LLM_CAP_THINKING', 'true')
            for purpose in ('agent_decide', 'dialogue', 'summary', 'extract',
                            'director_event'):
                fake.body = None
                await llm.chat('daily', [{'role': 'user', 'content': 'hi'}],
                               purpose=purpose)
                ok &= rec(f'A3 「{purpose}」是**写东西**的用途 → 不关思考',
                          'thinking' not in (fake.body or {}),
                          json.dumps(sorted((fake.body or {}).keys()),
                                     ensure_ascii=False))
            # (d) 显式覆盖也要听
            # [EN] (d) Explicit overrides must also be honored
            fake.body = None
            await llm.chat('daily', [{'role': 'user', 'content': 'hi'}],
                           purpose='dialogue', no_think=True)
            ok &= rec('A4 显式 no_think=True 能压过用途表',
                      (fake.body or {}).get('thinking') == {'type': 'disabled'},
                      json.dumps((fake.body or {}).get('thinking')))
            fake.body = None
            await llm.chat('daily', [{'role': 'user', 'content': 'hi'}],
                           purpose='progress_eval', no_think=False)
            ok &= rec('A5 显式 no_think=False 也能压过用途表',
                      'thinking' not in (fake.body or {}),
                      json.dumps(sorted((fake.body or {}).keys()),
                                 ensure_ascii=False))
            # (e) ★★ 混配：三档不一定是同一个模型。闸门必须落到"这一次用谁"上。
            #     真实场景（用户的 .env 就是这样）：华彩档 deepseek-chat
            #     （本来就不思考）、摘要档 deepseek-flash（思考、且能关）。
            # [EN] (e) ★★ Mixed configuration: the three tiers aren't necessarily the same model. The gate must
            # [EN] apply to "who is used for this call".
            # [EN] Real-world scenario (the user's .env is exactly like this): showcase tier deepseek-chat
            # [EN] (doesn't think anyway), summary tier deepseek-flash (thinks, and can be turned off).
            CFG.set('MODEL_FRONT', 'deepseek-chat')
            CFG.set('MODEL_DAILY', 'deepseek-flash')
            CFG.set('MODEL_CHEAP', 'deepseek-flash')
            from llm import capabilities as CAP
            det = CAP.check_capabilities(CFG, apply=False).detected
            ok &= rec('A6 ★★ 混配（华彩=deepseek-chat / 摘要=deepseek-flash）'
                      '不能把「思考开关」判成不支持 —— 那会让摘要档明明能关却关不了，'
                      'progress_eval 继续爆预算（真机抓到的就是这个）',
                      det.get(CAP.CAP_THINKING) is True, str(det))
            # 危险组合：某一档是不认识 thinking 参数的模型 → **一个字都不发**
            # ★★★ 2026-10-22（用户：「为何每次都会检查没修复的错误」——这条时红时绿）：
            #   **只改 `MODEL_DAILY=o3-mini` 是没有用的**：`llm/models.resolve()` 是按
            #   **登记表**解析这一发用谁的 —— 登记表里没有 o3-mini 这一条时，
            #   它会落到「③ 默认模型」（这是 A4 明文要求的行为，不是 bug）。
            #   于是这条判据一直在拿 **deepseek-flash** 测「o3-mini 的闸门」：
            #   deepseek-flash 支持关思考 ⇒ 请求体里当然有 thinking ⇒ **恒红**。
            #   ⇒ 必须真的让"这一发用 o3-mini"：用临时登记表（`MODELS.use_path`），
            #     跑完自动还原，绝不碰用户的 `llm_models.json`。
            # [EN] Dangerous combo: some tier uses a model that doesn't understand the thinking
            # [EN] parameter -> **send not a single character**.
            # [EN] ★★★ 2026-10-22 (user: "why does it keep checking unfixed errors" -- this line
            # [EN] flip-flopped): **setting `MODEL_DAILY=o3-mini` alone does nothing**:
            # [EN] `llm/models.resolve()` decides who serves this request from the **registry**, and
            # [EN] with no o3-mini entry it falls to "③ default model" (which is what A4 explicitly
            # [EN] requires, not a bug). So this criterion kept testing "o3-mini's gate" against
            # [EN] **deepseek-flash**: that model does support disabling thinking, so the body carries
            # [EN] thinking => **always red**. => Make the request really use o3-mini, via a temporary
            # [EN] registry (`MODELS.use_path`), restored afterwards; the user's `llm_models.json` is
            # [EN] never touched.
            from llm import models as MODELS
            _tmp_reg = Path(tempfile.mkdtemp(prefix='nws_pe_reg_')) / 'llm_models.json'
            with MODELS.use_path(_tmp_reg):
                MODELS.save([MODELS.ModelEntry(
                    key='o3-mini', label='OpenAI o3-mini', model='o3-mini',
                    base_url='https://example.invalid/v1', api_key='k')])
                CFG.set('MODEL_DAILY', 'o3-mini')
                fake.body = None
                await llm.chat('daily', [{'role': 'user', 'content': 'hi'}],
                               purpose='progress_eval')
            ok &= rec('A7 ★★ 混配里有 o3-mini 时，发给它的请求**不发** thinking'
                      '（逐模型闸门：全局开关开着也挡得住 400）',
                      'thinking' not in (fake.body or {}),
                      f"model={CFG.model_of('daily')} · "
                      + json.dumps(sorted((fake.body or {}).keys()), ensure_ascii=False))
            CFG.set('MODEL_DAILY', 'deepseek-flash')
        finally:
            llm._client, llm._sem, llm._started, llm._loop = saved

    asyncio.run(_run())
    # ⚠ 这条原来写的是 `set(NO_THINK_PURPOSES) == {三个}` —— **判据写窄了**：
    #   2026-10-06 加了第四个结论型用途（`minimap_layout`：一小份 JSON）之后它当场变红，
    #   而那是**对**的（结论型产出，开思考会把额度烧光）。
    #   意图是"这张表里不许混进**要写东西**的用途"（叙事 / 台词 / 设定 / 摘要 ——
    #   那些正需要思考，关掉反而伤质量）—— 所以判成"这三个必须在，且不含有写东西的"。
    # [EN] ⚠ This line used to read `set(NO_THINK_PURPOSES) == {three}` -- **the predicate was written too
    # [EN] narrow**:
    # [EN] On 2026-10-06 a fourth conclusive-purpose use (`minimap_layout`: a small JSON blob) was added
    # [EN] and it turned red on the spot,
    # [EN] and that was **correct** (conclusive output; enabling thinking would burn the quota).
    # [EN] The intent is "this table must not contain **writing-something** uses" (narrative / lines /
    # [EN] settings / summary --
    # [EN] those genuinely need thinking; turning it off hurts quality) -- so the judgment is "these three
    # [EN] must be present, and none may be writing-something uses".
    _must = {'progress_eval', 'genre', 'alignment'}
    _writing = {'narrative', 'dialogue', 'extract', 'summary', 'rewrite',
                'optimize', 'opening', 'prose'}
    ok &= rec('A8 策略表里含那三个"只要结论"的用途，且**不含写东西的**',
              _must <= set(NO_THINK_PURPOSES)
              and not (set(NO_THINK_PURPOSES) & _writing),
              str(sorted(NO_THINK_PURPOSES)))
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 提示词：限字数；模板不留未替换的占位符
# [EN] B. Prompt: enforce character limit; template leaves no unreplaced placeholders
# ══════════════════════════════════════════════════════════════
def test_prompt() -> bool:
    ok = True
    from director import engine as E

    tpl = E._PROGRESS_PROMPT
    ok &= rec('B1 ★ 提示词给「理由」「进展描述」都限了字数'
              '（原来是不限长的自由文本，形状上就在鼓励写长）',
              tpl.count('不超过 40 字') == 2, str(tpl.count('不超过 40 字')))
    ok &= rec('B2 ★ 明说"只输出 JSON、不要写思考"',
              '只输出 JSON' in tpl and '不要写任何思考' in tpl)
    ok &= rec('B3 JSON 示例是**字面量花括号**（模板必须走 `util.text.fill`，'
              '不能走 `str.format`）',
              '{"满足": true|false' in tpl)

    # 真渲染一遍：不留占位符、也不误伤 JSON 示例
    # [EN] Render it for real once: no leftover placeholders, and don't accidentally break the JSON
    # [EN] examples
    from util.text import fill
    p = fill(tpl, name='楼前失忆', criteria='阿福被收留', events='- 一件小事')
    ok &= rec('B4 渲染后占位符全替换掉，JSON 示例原样保留',
              '{name}' not in p and '{criteria}' not in p and '{events}' not in p
              and '{"满足": true|false' in p and '楼前失忆' in p and '一件小事' in p,
              p.replace('\n', ' | ')[:200])
    p_no_events = _prompt_when_no_events()
    ok &= rec('B5 「最近发生的事」为空时给「（暂无）」而不是留一片空白'
              '（空列表也要能走通，不能因为没事件就崩）',
              '（暂无）' in p_no_events, p_no_events[:160])
    return ok


def _prompt_when_no_events() -> str:
    """真跑一次"没有最近事件"的评估，把发给模型的提示词抓回来。
        English:
    Actually run an evaluation of "no recent events" once, and capture back the prompt sent to the
    model.
    """
    from llm.router import llm

    captured: list = []

    async def _fake(tier, messages, **kw):
        captured.append(messages[-1]['content'])
        return ('{"满足": false, "理由": "无", "进展描述": ""}',
                {'truncated': False, 'empty_output': False, 'has_reasoning': False,
                 'max_tokens': kw.get('max_tokens')})

    real = llm.chat
    llm.chat = _fake
    try:
        asyncio.run(engine_for().evaluate_progress([]))
    finally:
        llm.chat = real
    return captured[0] if captured else ''


# ══════════════════════════════════════════════════════════════
#  C. 「没拿到」不许冒充「判据没满足」
# [EN] C. "Didn't get it" must not be passed off as "predicate not satisfied"
# ══════════════════════════════════════════════════════════════
def test_verdict() -> bool:
    ok = True
    from llm.router import llm

    async def _case(replies: list[str]):
        fake = FakeChat(replies)
        real = llm.chat
        llm.chat = fake
        try:
            return await engine_for().evaluate_progress([{'content': 'x'}]), fake
        finally:
            llm.chat = real

    # (a) 正常：判据没满足 → ok=True, done=False
    # [EN] (a) Normal: predicate not satisfied -> ok=True, done=False
    v, _f = asyncio.run(_case(['{"满足": false, "理由": "还没收留", '
                               '"进展描述": "刚触发记忆线索"}']))
    ok &= rec('C1 ★ 真的"判据没满足" → ok=True / done=False（★ C2~C4 的对照组，'
              '别把"报故障"做成"凡失败都算没满足"）',
              v.ok is True and v.done is False and v.desc == '刚触发记忆线索',
              f'ok={v.ok} done={v.done} desc={v.desc!r}')

    v, _f = asyncio.run(_case(['{"满足": true, "理由": "收了", "进展描述": "已收留"}']))
    ok &= rec('C2 判据满足 → ok=True / done=True',
              v.ok is True and v.done is True and v.desc == '已收留',
              f'ok={v.ok} done={v.done} desc={v.desc!r}')

    # (b) ★ 空正文（额度被思考吃光）→ 必须报"没拿到"，不能报"没满足"
    # [EN] (b) ★ Empty body (quota eaten by thinking) -> must report "didn't get it", not "not satisfied"
    v, f = asyncio.run(_case(['', '']))
    ok &= rec('C3 ★★ 正文为空（思考把额度吃光）→ ok=False'
              '（回归：以前它和 C1 返回的是同一个值，节点永远不推进且无人知晓）',
              v.ok is False and v.done is False and v.why,
              f'ok={v.ok} done={v.done} why={v.why!r}')
    ok &= rec('C4 失败时 `why` 是一句能给用户看的话（不是空串）',
              len(v.why) >= 4, repr(v.why))
    ok &= rec('C5 ★ 拿不到时会**重试一次**（v1.43 的统一通道，'
              '原来 progress_eval 绕过了它）',
              len(f.calls) == 2, f'调了 {len(f.calls)} 次')
    ok &= rec('C6 重试的预算翻倍（2000 → 更大），不是原样再来一遍',
              len(f.calls) == 2 and f.calls[1]['max_tokens'] > f.calls[0]['max_tokens'],
              str([c['max_tokens'] for c in f.calls]))
    ok &= rec('C7 重试时会说明上一次的病情（提示语里带"思考"字样 —— '
              '空正文和"被截断"是两种病，药不一样）',
              len(f.calls) == 2
              and '思考' in str(f.calls[1]['messages'][-1]['content']),
              str(f.calls[1]['messages'][-1]['content'])[-120:])

    # (c) 返回一堆非 JSON 废话 → 也必须是"没拿到"
    # [EN] (c) Returns a pile of non-JSON garbage -> also must be "didn't get it"
    v, _f = asyncio.run(_case(['好的，我看看……\n我觉得还没有满足条件。'] * 2))
    ok &= rec('C8 ★ 回了一堆非 JSON 文本 → ok=False（不是"没满足"）',
              v.ok is False and v.why, f'ok={v.ok} why={v.why!r}')

    # (d) JSON 合法但空对象 `{}` → "空的容器不算拿到东西"
    # [EN] (d) Valid JSON but empty object `{}` -> "an empty container doesn't count as getting something"
    v, _f = asyncio.run(_case(['{}', '{}']))
    ok &= rec('C9 ★ 解析出空对象 `{}` → ok=False（"空的容器不算拿到东西"）',
              v.ok is False and v.why, f'ok={v.ok} why={v.why!r}')

    # (e) 被截断的半截 JSON → 抢救回来也算拿到
    # [EN] (e) Truncated half-JSON -> salvaged also counts as gotten
    v, _f = asyncio.run(_case(['{"满足": true, "理由": "收']))
    ok &= rec('C10 半截 JSON → 按可闭合前缀抢救，拿到就要算数',
              v.ok is True and v.done is True, f'ok={v.ok} done={v.done}')

    # (f) 没有进度表 → "没得评" ≠ "没拿到"
    # [EN] (f) No progress table -> "nothing to evaluate" ≠ "didn't get it"
    v, _f = asyncio.run(_case(['{"满足": true}']))
    v2 = asyncio.run(engine_for(node=None).evaluate_progress([{'content': 'x'}]))
    ok &= rec('C11 ★ 项目没有进度表 → ok=True / done=False'
              '（"没得评"不是故障，不该让循环去播报失败）',
              v2.ok is True and v2.done is False, f'ok={v2.ok} done={v2.done}')

    # (g) 调用方拿到的一定是结果对象，不是二元组
    # [EN] (g) What the caller receives is definitely a result object, not a tuple
    ok &= rec('C12 返回值是 `ProgressVerdict`（不再是 `(bool, str)` 二元组 —— '
              '那对写法把两种意思压成同一个值）',
              hasattr(v2, 'ok') and hasattr(v2, 'why'))
    return ok


# ══════════════════════════════════════════════════════════════
#  D. 循环接线：连续 3 拍拿不到 → 讲给用户听（且不刷屏）
# [EN] D. Loop wiring: 3 consecutive ticks with nothing received -> tell the user (and don't spam)
# ══════════════════════════════════════════════════════════════
def test_loop_wiring() -> bool:
    ok = True
    from sim.loop import RunLoop
    from director.engine import ProgressVerdict

    def build(verdicts: list, db=None):
        fd = FakeDirector(verdicts)
        loop = RunLoop(world=FakeWorld(), agents=[], director=fd,
                       db=db if db is not None else FakeDB(), run=None)
        loop.display = FakeDisplay()
        seen: list[tuple] = []
        # ⚠ 2026-10-26：回调现在带的是 `detail` + `update_key`（中栏折叠/原地更新用）。
        #   替身签名不全 ⇒ 主循环 TypeError → 退回**两参调用**，`kind` 丢了 ⇒
        #   这里 `x[1] == NOTE_KIND` 永远不成立，D1~D4 全红
        #   （日志里那句"叙事回调不收 kind 参数（… unexpected keyword argument 'detail'）"
        #     就是它在说话 —— 红的原因是替身过期，与播报本身无关）。
        #   ⚠ 必须**把 `_push_narrative` 的整串关键字都收下**，少一个就退回两参。
        # [EN] The callback now carries `detail` + `update_key` (middle-column folding / in-place
        # [EN] updates). An incomplete double raises TypeError, the loop falls back to a
        # [EN] **two-argument call**, `kind` is lost, and `x[1] == NOTE_KIND` never holds -- the red
        # [EN] is an expired double, not a broadcast bug. ⚠ Accept **every** keyword
        # [EN] `_push_narrative` passes; missing one triggers the fallback.
        loop.on_narrative(
            lambda text, prio, kind='', detail=None, update_key='':
            seen.append((text, kind)))
        return loop, seen

    async def _run() -> None:
        nonlocal ok
        fail = ProgressVerdict.failed('模型没有返回可用的结论')
        idle = ProgressVerdict(ok=True, done=False)

        # (a) 连着 3 拍拿不到 → 恰好在第 3 拍播报一次
        # [EN] (a) 3 consecutive ticks with nothing -> broadcasts exactly once on the 3rd tick
        loop, seen = build([fail])
        for _ in range(3):
            await loop._check_progress()
        notes = [x for x in seen if x[1] == NOTE_KIND]
        ok = rec('D1 ★ 连续 3 拍拿不到结论 → 播报一条给用户看（回归：'
                 '以前节点不推进而界面上一个字都没有）',
                 len(notes) == 1 and '进度评估连续 3 拍没拿到结论' in notes[0][0],
                 str([n[0] for n in seen])[:220])
        ok &= rec('D2 播报里带了失败原因（用户能顺着去查日志）',
                  bool(notes) and '模型没有返回可用的结论' in notes[0][0],
                  notes[0][0][:160] if notes else '')
        ok &= rec('D3 第 4 拍**不再重复播报**（每拍都调，不节流会刷屏 —— '
                  '这个项目以前被 550 条"没动也没出声"刷过屏）',
                  len([x for x in seen if x[1] == NOTE_KIND]) == 1,
                  str(len([x for x in seen if x[1] == NOTE_KIND])))

        # (b) ★ 计数在成功之后清零。
        #    脚本要挑**能分辨"清没清零"**的那种情形：第一轮已经报过一条，
        #    之后成功一次、再来一轮 3 次失败 —— 清零了才会有第 2 条；
        #    若不清零，计数会一路数到 6，第二轮**永远等不到"第 3 拍"**。
        # [EN] (b) ★ Counter resets to zero after a success.
        # [EN] The script must pick a scenario that **can tell whether the counter was reset**: the first round
        # [EN] already broadcast one message,
        # [EN] then one success, then another round of 3 failures -- only if reset will there be a 2nd message;
        # [EN] if not reset, the counter just keeps counting up to 6, and the second round **never reaches
        # [EN] "tick 3"**.
        #
        #    ⚠ 2026-10-10 改：**每一拍都要有新事件**。加了"同一份输入不问第二遍"
        #      之后，输入不变时第 2、3 拍会被短路掉（压根不问模型），
        #      于是"连续 3 拍失败"这一串在这份静态夹具里**再也凑不出来**。
        #      真实推演里事件一直在写，所以这里跟着动一下才贴近现实 ——
        #      顺带也让这条判据顺便验了"信息变了要重新问"。
        # [EN] ⚠ Changed 2026-10-10: **every tick must have a new event**. After adding "don't ask a second
        # [EN] time for the same input",
        # [EN] when the input is unchanged, ticks 2 and 3 get short-circuited (the model isn't asked at all),
        # [EN] so the sequence "3 consecutive failed ticks" can **no longer be assembled** in this static
        # [EN] fixture.
        # [EN] In real replay, events keep being written, so moving along with it here is closer to reality --
        # [EN] and incidentally it also exercises this predicate's "information changed, re-ask" behavior.
        fd_b = FakeDirector([fail, fail, fail, idle, fail, fail, fail, idle])
        db_b = FakeDB([{'id': 'E1', 'content': '第一件小事。'}])
        loop, seen = build([fail, fail, fail, idle, fail, fail, fail, idle],
                           db=db_b)
        for i in range(8):
            db_b._events = [{'id': f'E{i + 1}', 'content': f'第 {i + 1} 件小事。'}]
            await loop._check_progress()
        notes_b = [x for x in seen if x[1] == NOTE_KIND]
        ok &= rec('D4 ★ 成功过一次 → 连续计数清零：两轮各自的第 3 拍各报一条'
                  '（共 2 条）；不清零的话第二轮一条都不会有',
                  len(notes_b) == 2 and all('连续 3 拍' in x[0] for x in notes_b),
                  f'{len(notes_b)} 条 / ' + str([n[0][:34] for n in seen]))

        # (c) 判据满足 → 播"节点完成"，且到最后返回 True
        # [EN] (c) Predicate satisfied -> broadcast "node complete", and return True at the end
        done = ProgressVerdict(ok=True, done=True, desc='已收留')
        loop, seen = build([done])
        reached = await loop._check_progress()
        ok &= rec('D5 判据满足 → 播一条「节点完成」并推进节点',
                  any('节点完成' in x[0] for x in seen), str([x[0] for x in seen]))
        ok &= rec('D6 最后一个节点完成 → `_check_progress` 返回 True'
                  '（主循环据此收尾）', reached is True, repr(reached))

        # (d) 没有最近事件 → 不调模型、不播报
        # [EN] (d) No recent events -> don't call the model, don't broadcast
        fd = FakeDirector([fail])
        loop = RunLoop(world=FakeWorld(), agents=[], director=fd, db=FakeDB([]),
                       run=None)
        loop.display = FakeDisplay()
        seen_d: list = []
        loop.on_narrative(lambda text, prio, kind='': seen_d.append((text, kind)))
        await loop._check_progress()
        ok &= rec('D7 没有"最近发生的事"时**不调模型、不播报**'
                  '（省一次请求，也不该报故障）',
                  not seen_d and loop._progress_fail_streak == 0,
                  f'{seen_d} / streak={loop._progress_fail_streak}')

        # (e) ★★★ **同一份输入不问第二遍**（2026-10-10，真机日志量出来的浪费）
        # [EN] (e) ★★★ **Don't ask a second time for the same input** (2026-10-10, waste measured from
        # [EN] real-machine logs)
        #
        #   进度评估的输入 = 「当前节点 + 最近 5 条事件」，而事件表只在有值得记的
        #   事情时才写。那次实测：它一整天只写了 **2 行**，19:32 之后再没变过 ⇒
        #   接下来 45 分钟每次问的都是**一模一样的问题**
        #   （`progress_eval` 385 次，其中 **326 次输入完全相同**）。
        # [EN] Progress-evaluation input = "current node + most recent 5 events", and the event table is only
        # [EN] written
        # [EN] when something worth recording happens. That real measurement: it wrote only **2 lines** the
        # [EN] whole day, and after 19:32 never changed again ⇒
        # [EN] for the next 45 minutes every ask was the **exact same question**
        # [EN] (`progress_eval` 385 times, of which **326 had completely identical input**).
        #
        #   ⚠ 判据用 `FakeDirector._i`（**真被调用的次数**）来数，不数别的 ——
        #     这个桩的 `_i` 就是"问了几次"，最直接。
        # [EN] ⚠ The predicate counts with `FakeDirector._i` (**the number of times it was actually called**),
        # [EN] nothing else --
        # [EN] the stub's `_i` is exactly "how many times it was asked", the most direct.
        idle2 = ProgressVerdict(ok=True, done=False)
        fd5 = FakeDirector([idle2])
        db5 = FakeDB([{'id': 'E1', 'content': '甲把茶盏搁下。'}])
        loop5 = RunLoop(world=FakeWorld(), agents=[], director=fd5, db=db5,
                        run=None)
        loop5.display = FakeDisplay()
        await loop5._check_progress()
        await loop5._check_progress()
        await loop5._check_progress()
        ok &= rec('D8 ★★★ 输入没变时**只问一次**（连调 3 拍，模型只被问 1 次）',
                  fd5._i == 1, f'问了 {fd5._i} 次（应为 1）')
        # 信息真的变了 → 必须重新问（不能把"省请求"做成"永远不再问"）
        # [EN] Information really changed -> must re-ask (can't turn "save requests" into "never ask again")
        db5._events = [{'id': 'E2', 'content': '乙推门进来。'}]
        await loop5._check_progress()
        ok &= rec('D8b ★★★ 事件一变就**重新问**（省请求不能省成"再也不问"）',
                  fd5._i == 2, f'问了 {fd5._i} 次（应为 2）')
        # 节点推进之后也要重新问（签名里带着 current_node）
        # [EN] After the node advances, also re-ask (the signature carries current_node)
        loop5.world.current_node = 'N02'
        await loop5._check_progress()
        ok &= rec('D8c ★ 节点一推进就重新问（签名里带着当前节点）',
                  fd5._i == 3, f'问了 {fd5._i} 次（应为 3）')
        # ★ 拿不到结论（`ok=False`）**不许**被当成"问过了" —— 失败要允许重问，
        #   否则一次网络抖动就把这个节点永远钉死在"没结论"上。
        # [EN] ★ Failure to get a conclusion (`ok=False`) **must not** be treated as "already asked" --
        # [EN] failures must allow re-asking,
        # [EN] otherwise one network hiccup pins this node forever in "no conclusion".
        fd6 = FakeDirector([fail])
        db6 = FakeDB([{'id': 'E1', 'content': '甲把茶盏搁下。'}])
        loop6 = RunLoop(world=FakeWorld(), agents=[], director=fd6, db=db6,
                        run=None)
        loop6.display = FakeDisplay()
        await loop6._check_progress()
        await loop6._check_progress()
        ok &= rec('D8d ★★★ 上一次**没拿到结论**不算"问过了"：同一份输入还会再问'
                  '（否则一次抖动就把这个节点永远钉死）',
                  fd6._i == 2, f'问了 {fd6._i} 次（应为 2）')

    asyncio.run(_run())
    return ok


# ══════════════════════════════════════════════════════════════
#  E. 能力表：把 deepseek-flash 认对
# [EN] E. Capability table: recognize deepseek-flash correctly
# ══════════════════════════════════════════════════════════════
def test_capabilities() -> bool:
    ok = True
    from llm import capabilities as CAP

    for name in ('deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-pro'):
        caps, label = CAP.detect(name)
        ok &= rec(f'E {name} → 认出来了（{label}），且判为**推理模型**'
                  '（以前落到笼统的 deepseek 上，被判成非推理）',
                  bool(caps) and caps.get(CAP.CAP_REASONING) is True, str(caps))
        ok &= rec(f'E {name} → 判为**可以关思考**',
                  CAP.detect_thinking_switch(name) is True,
                  repr(CAP.detect_thinking_switch(name)))

    ok &= rec('E deepseek-chat → 非推理、也不支持关思考'
              '（直连实测：它本来就不思考）',
              CAP.detect_thinking_switch('deepseek-chat') is False)
    ok &= rec('E deepseek-reasoner → 能关（实测它认这个参数）',
              CAP.detect_thinking_switch('deepseek-reasoner') is True)
    ok &= rec('E o3-mini（推理但不支持关）/ gpt-4o（非推理）→ 都不发 thinking',
              CAP.detect_thinking_switch('o3-mini') is False
              and CAP.detect_thinking_switch('gpt-4o') is False)
    ok &= rec('E ★ 认不出的模型名 → `None`（**不猜**，否则会去改用户配置）',
              CAP.detect_thinking_switch('my-private-proxy') is None
              and CAP.detect_thinking_switch('') is None)

    # 新能力键必须**真的被代码用到**（这个项目对"假开关"零容忍）
    # [EN] New capability keys must **actually be used by code** (this project has zero tolerance for "fake
    # [EN] switches")
    from llm.router import llm                                     # noqa: F401
    src = (APP_DIR / 'llm' / 'router.py').read_text(encoding='utf-8')
    ok &= rec('E ★★ `CAP_THINKING` 在 router 里**真的被读到**'
              '（假开关零容忍：新加的能力项必须影响请求体）',
              'CAP_THINKING' in src, 'router.py 里没提到 CAP_THINKING')
    ok &= rec('E 新能力键进了 `CAP_KEYS`（设置界面自动多一个开关）',
              CAP.CAP_THINKING in CAP.CAP_KEYS, str(CAP.CAP_KEYS))
    ok &= rec('E 新能力键在 `config.SPEC` 里有对应项（否则界面上改不了、也存不下）',
              CAP.CAP_THINKING in __import__('config').SPEC)
    return ok


# ══════════════════════════════════════════════════════════════
def main() -> int:
    print('进度评估（progress_eval）· 关思考 · 不许静默降级 —— 验证', flush=True)
    ok_all = True
    for head, fn in (('A. 请求体：结论型用途关思考', test_no_think_body),
                     ('B. 提示词：限字数 + 模板渲染', test_prompt),
                     ('C. 「没拿到」不许冒充「没满足」', test_verdict),
                     ('D. 循环接线：失败要让人看见', test_loop_wiring),
                     ('E. 能力表：把 deepseek-flash 认对', test_capabilities)):
        print(f'\n{"=" * 62}\n{head}', flush=True)
        try:
            ok_all &= bool(fn())
        except Exception:
            report.setdefault('fatal', []).append(traceback.format_exc())
            print(traceback.format_exc()[-1500:], flush=True)
            ok_all = False

    report['ok'] = bool(ok_all)
    (OUT / 'progress_eval_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)),
          flush=True)
    if report.get('fatal'):
        print('\n⚠ 验证中途崩溃：\n' + '\n'.join(report['fatal'])[-1200:], flush=True)
    return 0 if ok_all else 2


if __name__ == '__main__':
    # 护身符：本脚本只 `CFG.set`（内存），**不点「开始推演」**，理论上不会写 .env；
    # 但用户 .env 被测试值污染过一次（`verify_ui_common.env_guard` 的 docstring），
    # 便宜保险就上一条。
    # [EN] Amulet: this script only does `CFG.set` (in-memory), **doesn't click "Start Replay"**, so in
    # [EN] theory it won't write .env;
    # [EN] but the user's .env was once polluted by test values (the docstring of
    # [EN] `verify_ui_common.env_guard`),
    # [EN] so a cheap insurance policy is added.
    with VU.env_guard():
        sys.exit(main())
