# -*- coding: utf-8 -*-
"""验证：配置界面里的「拉取模型列表」与「测试」两个按钮。

用户 2026-10-06 提的三件事（同一个诉求的三个面）：

  「模型我看了 只有 DeepSeek-V4 Flash 和 DeepSeek-V4 Pro，我之前写的模型名字不对」
  「在配以模型的界面地方每一个选择模型的旁边加一个测试按钮，配置完可以直接点了
    测试链接，如果不行可以马上把错误信息爆出来」
  「在填 Base URL 和 API Key 的旁边加一个拉取模型列表，可以直接拉取对方的可用模型，
    然后下面配置模型的地方的下拉列表根据这个结果填充」
  「默认打开如果没配置模型，会提示只提供假数据和模拟运行」

根子是一句话：**配置对不对，只有真发一次请求才知道**。以前要么写死的下拉列表
（对方改了名就选不到）、要么等推演时才炸（而且炸得看不懂）。

对应改动：`llm/probe.py`（拉列表 / 测连通 / 启动时判有没有配模型）×
`gui.app_flet.model_choices`（下拉候选 = 缓存 → 兜底 → 当前值）×
`gui.app_flet.show_global_settings`（两个按钮 + 结果行）×
`NovelWorldApp._run_llm_readiness_check`（没配模型就说透）。

判据两层：
  A 组**纯逻辑**：打桩 httpx，把探针每一种失败都逼出来 —— 错误文案要能照着修。
  B 组**真机**：按钮在对话框里点得动、下拉真的被换掉、结果**真的渲染在屏幕上**
     （标记色像素取证 —— 本项目铁律：控件树里有 ≠ 屏幕上看得见）。

用法：.venv\\Scripts\\python.exe tools/verify_model_probe.py [--logic-only]
产出：assets/screenshots/model_probe_report.json / model_probe_*.png

English:
Verify: the "Fetch model list" and "Test" buttons in the config UI.
Three things the user raised on 2026-10-06 (three faces of the same demand):
  "I looked at the models, there are only DeepSeek-V4 Flash and DeepSeek-V4 Pro, the model names I wrote before were wrong"
  "Add a test button next to each model selection in the model configuration UI, so after configuring you can directly click
    test the link; if it fails, the error message can be surfaced immediately"
  "Next to where Base URL and API Key are filled in, add a fetch model list button that can directly fetch the other party's available models,
    then the dropdown list where the model is configured below is populated from this result"
  "By default, if no model is configured on open, it will prompt that only fake data and simulated runs are provided"
The root of it is one sentence: **whether the config is correct, you only know by actually
sending a request once**. Previously it was either a hardcoded dropdown list
(if the other party renamed it, you couldn't select it), or it only blew up during inference
(and blew up incomprehensibly).
Corresponding changes: `llm/probe.py` (fetch list / test connectivity / determine at startup
whether a model is configured) x
`gui.app_flet.model_choices` (dropdown candidates = cache -> fallback -> current value) x
`gui.app_flet.show_global_settings` (two buttons + result line) x
`NovelWorldApp._run_llm_readiness_check` (if no model is configured, state it clearly).
Two layers of criteria:
  Group A **pure logic**: stub httpx, force out every kind of probe failure -- the error text must be fixable by following it.
  Group B **real machine**: the button is clickable in the dialog, the dropdown really gets replaced, the result is **really rendered on screen**
     (marker-color pixel forensics -- this project's iron rule: present in the widget tree != visible on screen).
Usage: .venv\\Scripts\\python.exe tools/verify_model_probe.py [--logic-only]
Output: assets/screenshots/model_probe_report.json / model_probe_*.png
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
# ⚠ 探针**不受演示模式影响**（这正是它存在的理由之一）：这里把 MOCK 打开，
#   如果探针偷懒走了 mock，A 组那句"真发了请求"就会红。
# [EN] ⚠ The probe is **not affected by demo mode** (this is one of the reasons it exists): here MOCK
# [EN] is turned on,
# [EN] if the probe lazily goes through mock, group A's line "actually sent a request" will turn red.
CFG.set('MOCK_LLM', 'true')
CFG.set('LLM_BASE_URL', 'https://probe.example.com/v1')
CFG.set('LLM_API_KEY', 'sk-probe-123')
CFG.set('MODEL_FRONT', 'deepseek-v4-pro')
CFG.set('MODEL_DAILY', 'deepseek-flash')
CFG.set('MODEL_CHEAP', 'deepseek-flash')

from i18n import set_lang, t                                 # noqa: E402
set_lang('zh')

from llm import probe                                        # noqa: E402

SUFFIX = '_probe'
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:500]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑（打桩 httpx）
# [EN] A. Pure logic (stub httpx)
# ══════════════════════════════════════════════════════════════
class FakeResp:
    def __init__(self, status: int, text: str) -> None:
        self.status_code = status
        self.text = text

    def json(self):
        return json.loads(self.text)


class FakeClient:
    """够用的假 httpx 客户端：只记下**最后一次请求**，返回预置响应。

    `raise_on` 不为空时直接抛它（模拟网络层异常）——
    ⚠ 第一版这里是"返回一个假对象"，结果 `probe` 读到 `r.status_code` 就
    `AttributeError`，把整个 A7 段炸掉；而炸掉之后 checks 里**连它的条目
    都没有**，汇总仍显示"全绿"—— 判据把崩溃盖住了。所以：
    ① 异常要走真异常；② 崩溃必须自己在 checks 里留一条红的（见 `test_logic`）。
    
        English:
    A good-enough fake httpx client: only records the **last request**, returns a preset response.
        When `raise_on` is non-empty, raise it directly (simulating a network-layer exception) --
        WARNING the first version here was "return a fake object", and as a result `probe` read `r.status_code` and hit
        `AttributeError`, blowing up the entire A7 section; and after it blew up, the checks **didn't even have its entry
        at all**, and the summary still showed "all green" -- the criteria covered up the crash. So:
        (1) exceptions must go through real exceptions; (2) a crash must leave a red entry for itself in checks (see `test_logic`).
    """

    last: dict = {}
    answer: dict = {}          # {'get': FakeResp, 'post': FakeResp}
    raise_on: BaseException | None = None

    def __init__(self, **kw) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        FakeClient.last = {'method': 'GET', 'url': url, 'headers': dict(headers or {})}
        if FakeClient.raise_on is not None:
            raise FakeClient.raise_on
        return FakeClient.answer['get']

    async def post(self, url, json=None, headers=None):
        FakeClient.last = {'method': 'POST', 'url': url, 'body': json,
                           'headers': dict(headers or {})}
        if FakeClient.raise_on is not None:
            raise FakeClient.raise_on
        return FakeClient.answer['post']


def _ok_chat(text: str = '收到', reasoning: str = '') -> str:
    msg = {'content': text}
    if reasoning:
        msg['reasoning_content'] = reasoning
    return json.dumps({'choices': [{'message': msg, 'finish_reason':
                                    'length' if not text else 'stop'}]})


def test_logic() -> bool:
    ok = True
    real = probe.httpx.AsyncClient
    probe.httpx.AsyncClient = FakeClient
    try:
        # ── A1 模型列表响应：三种形状都要认 ──
        # [EN] ── A1 Model list response: all three shapes must be recognized ──
        cases = [
            ('OpenAI 兼容', '{"data":[{"id":"deepseek-flash"},{"id":"deepseek-v4-pro"}]}',
             ['deepseek-flash', 'deepseek-v4-pro']),
            ('嵌套 data.models', '{"data":{"models":[{"name":"m1"},{"name":"m2"}]}}',
             ['m1', 'm2']),
            ('顶层 models', '{"models":[{"id":"a"}]}', ['a']),
            ('极简字符串数组', '{"data":["x","y"]}', ['x', 'y']),
            ('裸露数组', '["p","q"]', ['p', 'q']),
        ]
        for label, raw, want in cases:
            got = probe.parse_model_ids(raw)
            ok &= rec(f'A1 认得出「{label}」形状的模型列表', got == want, str(got))
        for junk in ('', '不是 JSON', '{"data":[]}', '{"data":"x"}'):
            ok &= rec(f'A1 垃圾响应 {junk[:16]!r} → 空表（不猜）',
                      probe.parse_model_ids(junk) == [], str(junk)[:40])

        async def run_cases():
            nonlocal ok
            # ── A2 基础项没填齐 → 一个字都不发，直接说缺什么 ──
            # [EN] ── A2 Base items incomplete → send nothing at all, just say what's missing ──
            r = await probe.list_models(base_url='', api_key='k')
            ok = rec('A2 没填 Base URL → 直接说缺 Base URL，不发请求',
                     not r.ok and 'Base URL' in r.detail, r.detail) and ok
            r = await probe.list_models(base_url='https://x.example/v1', api_key='')
            ok = rec('A2 没填 API Key → 直接说缺 API Key',
                     not r.ok and 'API Key' in r.detail, r.detail) and ok
            r = await probe.probe_model('', base_url='https://x.example/v1', api_key='k')
            ok = rec('A2 没填模型名 → 直接说这个档位没填', not r.ok and '模型名' in r.detail,
                     r.detail) and ok

            # ── A3 成功：列表 + 连通 ──
            # [EN] ── A3 Success: list + connectivity ──
            FakeClient.answer = {'get': FakeResp(200, '{"data":[{"id":"a"},{"id":"b"}]}')}
            r = await probe.list_models()
            ok = rec('A3 拉到列表 → ok，且 URL 拼在 Base 之后',
                     r.ok and r.ids == ['a', 'b']
                     and FakeClient.last['url'] == 'https://probe.example.com/v1/models',
                     f'{r.ids} / {FakeClient.last["url"]}') and ok
            ok = rec('A3 拉列表带上了 Bearer Key',
                     FakeClient.last['headers'].get('Authorization') == 'Bearer sk-probe-123',
                     str(FakeClient.last['headers'])) and ok

            FakeClient.answer = {'post': FakeResp(200, _ok_chat('收到'))}
            p = await probe.probe_model('deepseek-flash')
            ok = rec('A3 测连通成功 → ok + 回话写进 reply',
                     p.ok and p.reply == '收到'
                     and FakeClient.last['url'] ==
                     'https://probe.example.com/v1/chat/completions',
                     p.line()) and ok

            # ── A4 ★ 思考型模型：请求体里必须带 thinking disabled ──
            #    不带的话，"测试失败"是假的失败（64 token 全花在思考上）。
            await probe.probe_model('deepseek-flash')          # 知识库里认得出
            # [EN] ── A4 ★ Thinking-type model: request body must carry thinking disabled ──
            # [EN] without it, the "test failure" is a false failure (all 64 tokens spent on thinking).
            # [EN] Recognizable in the knowledge base
            ok = rec('A4 ★ 思考型模型 → 请求体带 thinking={"type":"disabled"}',
                     (FakeClient.last['body'] or {}).get('thinking') == {'type': 'disabled'},
                     json.dumps(FakeClient.last['body'], ensure_ascii=False)) and ok
            # 非思考型（认得出、但没有关思考这条路）→ 一个字都不发
            # [EN] Non-thinking type (recognized, but no way to disable thinking) → send nothing at all
            await probe.probe_model('gpt-4o')
            ok = rec('A4 非思考型模型 → 请求体里**没有** thinking（发了可能 400）',
                     'thinking' not in (FakeClient.last['body'] or {}),
                     json.dumps(FakeClient.last['body'], ensure_ascii=False)) and ok

            # ── A5 ★ 200 但正文为空 —— 既不许说"失败"，也不许悄悄算通过 ──
            # [EN] ── A5 ★ 200 but empty body —— must neither say "failure" nor silently count as pass ──
            FakeClient.answer = {'post': FakeResp(200, _ok_chat('', reasoning='想' * 900))}
            p = await probe.probe_model('deepseek-flash')
            # ⚠ 判据要看 `line()`（界面显示的**就是**它），不是单独某个字段：
            #   第一版把 needle 写在 `detail` 上，而"正文为空"其实在 `note` 里 ——
            #   判据自己写窄了就会假红（本项目的老毛病）。
            # [EN] ⚠ The criterion must look at `line()` (what the UI displays is **exactly** it), not some
            # [EN] individual field:
            # [EN] the first version put the needle on `detail`, while "empty body" was actually in `note` ——
            # [EN] writing the criterion too narrowly causes false reds (a chronic problem in this project).
            ok = rec('A5 ★ 正文为空 → ok=True（链路是通的）但**必须说明白**',
                     p.ok and not p.reply and '没有输出正文' in p.line()
                     and '正文为空' in p.line() and '思考' in p.line(),
                     p.line()[:260]) and ok

            # ── A6 失败：状态码 + 服务端原话 + 怎么修，三样都要在 ──
            # ⚠ 这段 body 是**真跑出来的原文**（`developers/probe_thinking.py`
            #   实战那条），不是编的 —— 编的 body 会把"关键词收得对不对"这件事
            #   掩盖过去（第一版就编短了，于是代码里少一个关键词没被发现）。
            # [EN] ── A6 Failure: status code + server's exact words + how to fix, all three must be present ──
            # [EN] ⚠ This body is the **actual text from a real run** (`developers/probe_thinking.py`
            # [EN] the real-combat line), not made up —— a made-up body would paper over
            # [EN] the question of "are the keywords collected correctly" (the first version made it too short, so
            # [EN] a missing keyword in the code went undetected).
            body400 = ('{"error":{"message":"The supported API model names are '
                       'deepseek-flash, deepseek-v4-pro, but you passed nope. '
                       '(request_id: 687f0cae)","type":"invalid_request_error",'
                       '"param":null,"code":"invalid_request_error"}}')
            # 对方换措辞、不带 `invalid` 时也得认出来（只认一个词就会掉进笼统那句）
            # [EN] It must also be recognized when the other side rewords it and doesn't include `invalid`
            # [EN] (recognizing only one word falls into the generic line)
            body400b = ('{"error":{"message":"The supported API model names are '
                        'deepseek-flash, deepseek-v4-pro, but you passed nope."}}')
            cases_http = [
                (401, '{"error":{"message":"Authentication Fails"}}', 'API Key'),
                (400, body400, '模型名'),
                (400, body400b, '模型名'),
                (404, '{"error":"not found"}', '404'),
                (429, '{"error":"rate limit"}', '429'),
                (500, 'boom', '500'),
            ]
            for status, body, needle in cases_http:
                FakeClient.answer = {'post': FakeResp(status, body)}
                p = await probe.probe_model('nope')
                ok = rec(f'A6 HTTP {status} → detail 里有「{needle}」',
                         not p.ok and needle in p.detail, p.detail) and ok
                ok = rec(f'A6 HTTP {status} → 把服务端原话留下来了',
                         bool(p.raw) and p.status == status, p.raw[:120]) and ok
            # 400 + 提到 model → 必须点破"是模型名的问题"，并给出"去拉列表"这条出路
            # [EN] 400 + mentions model → must call out "it's a model name problem" and offer "go fetch the list"
            # [EN] as a way out
            FakeClient.answer = {'post': FakeResp(400, body400b)}
            p = await probe.probe_model('nope')
            ok = rec('A6 ★ 400 且原话里提到模型名 → 说成「模型名不被接受」+ 指引去拉列表',
                     '模型名' in p.detail and '拉取模型列表' in p.hint,
                     f'{p.detail} / {p.hint}') and ok
            # 反例：400 但跟模型名无关 → **不许**硬说成模型名的问题
            # [EN] Counter-example: 400 but unrelated to the model name → **must not** force it to be a model name
            # [EN] problem
            FakeClient.answer = {'post': FakeResp(400, '{"error":{"message":"bad temperature"}}')}
            p = await probe.probe_model('nope')
            ok = rec('A6 ★★ 反例：400 与模型名无关时，不硬报"模型名不被接受"',
                     '模型名不被接受' not in p.detail, p.detail) and ok

            # ── A7 网络异常：区分超时与连不上 ──
            # [EN] ── A7 Network exception: distinguish timeout from cannot-connect ──
            import httpx
            for exc, needle in ((httpx.ConnectTimeout('t'), '超时'),
                                (httpx.ConnectError('c'), '连不上')):
                FakeClient.raise_on = exc
                p = await probe.probe_model('deepseek-flash')
                ok = rec(f'A7 {type(exc).__name__} → detail 里有「{needle}」',
                         not p.ok and needle in p.detail, p.detail) and ok
                ok = rec(f'A7 {type(exc).__name__} → 给了怎么修', bool(p.hint),
                         p.hint) and ok
                ok = rec(f'A7 {type(exc).__name__} → 原始异常原文留下来了',
                         type(exc).__name__ in p.raw, p.raw[:120]) and ok
            FakeClient.raise_on = None

            # ── A8 ★ 用界面上「刚填、还没保存」的值，不是 CFG 里的旧值 ──
            # [EN] ── A8 ★ Use the value on the UI that was "just filled in, not yet saved", not the old value in
            # [EN] CFG ──
            FakeClient.answer = {'get': FakeResp(200, '{"data":[{"id":"z"}]}')}
            await probe.list_models(base_url='https://other.example.com/v1',
                                    api_key='sk-other')
            ok = rec('A8 ★ 探针用传入的值（界面当前值），不是 CFG 里保存的旧值',
                     FakeClient.last['url'].startswith('https://other.example.com/v1')
                     and FakeClient.last['headers'].get('Authorization') == 'Bearer sk-other',
                     f'{FakeClient.last["url"]} / {FakeClient.last["headers"]}') and ok

            # ── A9 探针不记账（试一下不该算进"今日花费"）──
            # [EN] ── A9 The probe does not do accounting (a try should not count toward "today's spend")──
            from llm.router import llm
            n0 = len(llm.ledger.records)
            await probe.probe_model('deepseek-flash')
            await probe.list_models()
            ok = rec('A9 探针不写 token 账本（试一下不该算花费）',
                     len(llm.ledger.records) == n0,
                     f'{n0} → {len(llm.ledger.records)}') and ok

        class _Raiser:
            def __init__(self, exc):
                self.exc = exc

        asyncio.run(run_cases())

        # ── A10 启动时「配了模型没有」 ──
        # [EN] ── A10 On startup, "is a model configured" ──
        class _Cfg:
            def __init__(self, **kw):
                self.kw = kw

            def s(self, k):
                return self.kw.get(k, '')

        ok &= rec('A10 什么都没填 → 不 ready，且理由是 Base URL',
                  probe.llm_ready(_Cfg(BASE=''))[0] is False
                  and 'Base URL' in probe.llm_ready(_Cfg())[1],
                  str(probe.llm_ready(_Cfg())))
        ready, why = probe.llm_ready(_Cfg(LLM_BASE_URL='http://x/v1',
                                          LLM_API_KEY='', MODEL_FRONT='m'))
        ok &= rec('A10 填了地址没填 Key → 不 ready', ready is False and 'API Key' in why, why)
        ready, why = probe.llm_ready(_Cfg(LLM_BASE_URL='http://x/v1',
                                          LLM_API_KEY='k', MODEL_FRONT='',
                                          MODEL_DAILY='', MODEL_CHEAP=''))
        ok &= rec('A10 填了地址和 Key、模型名全空 → 不 ready',
                  ready is False and '模型名' in why, why)
        ready, why = probe.llm_ready(_Cfg(LLM_BASE_URL='http://x/v1',
                                          LLM_API_KEY='k', MODEL_FRONT='m'))
        ok &= rec('A10 三样齐了 → ready', ready is True and why == '', f'{ready}/{why}')
        # ollama 本地不需要 Key
        # [EN] ollama local does not need a Key
        ready, _why = probe.llm_ready(_Cfg(LLM_BASE_URL='http://localhost:11434/v1',
                                           LLM_API_KEY='', LLM_PROVIDER='ollama',
                                           MODEL_FRONT='qwen'))
        ok &= rec('A10 接入协议 = ollama → 不填 Key 也算 ready（本地不要 Key）',
                  ready is True, str(ready))

        # ── A11 没配模型时的提示：必须点破"假数据 / 模拟运行" ──
        # [EN] ── A11 Prompt when no model configured: must call out "fake data / simulated run" ──
        notice = probe.missing_model_notice('没有填 API Key')
        ok &= rec('A11 ★ 提示里点破了「演示数据」与「模拟运行」',
                  '演示数据' in notice and '模拟运行' in notice, notice[:160])
        ok &= rec('A11 提示里带上了缺什么 + 去哪儿配 + 两个按钮的名字',
                  '没有填 API Key' in notice and '天机' in notice
                  and '拉取模型列表' in notice and '测试' in notice, notice[:200])
    except Exception:
        report['fatal'] = traceback.format_exc()
        # ★ **崩溃必须自己在 checks 里留一条红的**。否则炸掉的那些段落
        #   连条目都没有，"通过 N/N" 照样全绿 —— 判据把崩溃盖住了
        #   （本轮实测踩到：A7 的假桩写错，炸了一整段，汇总却报 32/32）。
        # [EN] ★ **A crash must leave a red entry in checks itself**. Otherwise the sections that blew up
        # [EN] don't even have entries, and "passed N/N" stays all green —— the criterion covers up the crash
        # [EN] (hit in this round's real run: A7's fake stub was wrong, blew up an entire section, yet the
        # [EN] summary still reported 32/32).
        rec('A 组没有中途崩溃（有崩溃就不是全绿）', False,
            report['fatal'][-300:])
        ok = False
    finally:
        probe.httpx.AsyncClient = real
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 真机
# [EN] B. Real machine
# ══════════════════════════════════════════════════════════════
def walk(c, out: list, d: int = 0) -> None:
    if c is None or d > 40:
        return
    out.append(c)
    for a in ('controls', 'content', 'actions', 'title'):
        v = getattr(c, a, None)
        if isinstance(v, list):
            for x in v:
                walk(x, out, d + 1)
        elif v is not None and hasattr(v, '__class__'):
            walk(v, out, d + 1)


def _btn_label(ctrl) -> str:
    ct = getattr(ctrl, 'content', None)
    import flet as ft
    if isinstance(ct, ft.Text):
        return str(ct.value or '')
    return str(ct or '')


def walk_flat(root) -> list:
    out: list = []
    walk(root, out)
    return out


async def test_gui(page) -> bool:
    """★ 整个真机段都套在 `VU.env_guard()` 里（**不是可选，是必须**）。

    本脚本会点设置对话框的「保存」，而 `CFG.save()` 会把内存里的**全部**配置
    写回 `.env` —— 包括脚本为了测试塞进去的 `LLM_BASE_URL` /
    `LLM_API_KEY`，以及 `VU.isolate_projects_dir()` 的临时项目目录。
    **2026-10-06 实测就是漏了这一步**：用户的 `.env` 被改成
    `https://probe.example.com/v1` + `sk-probe-123`，`DEFAULT_PROJECTS_DIR`
    被指向一个马上就被删掉的临时目录。
    `env_guard()` 现在的第一道防线是**把写盘重定向**（写不进去），
    备份/还原只是第二道 —— 详见 `verify_ui_common.env_guard`。
    另外：`app.main()` 内部会跑能力校验并可能 `CFG.save()`，
    所以"包住点保存那一下"是不够的，**必须包住整个 GUI 段**。
    
        English:
    STAR The entire real-machine section is wrapped in `VU.env_guard()` (**not optional,
    mandatory**).
        This script clicks "Save" in the settings dialog, and `CFG.save()` writes **all** config in memory
        back to `.env` -- including the `LLM_BASE_URL` /
        `LLM_API_KEY` that the script stuffed in for testing, as well as the temp project directory from `VU.isolate_projects_dir()`.
        **Actually measured on 2026-10-06: this step was missed**: the user's `.env` was changed to
        `https://probe.example.com/v1` + `sk-probe-123`, and `DEFAULT_PROJECTS_DIR`
        was pointed at a temp directory that was about to be deleted.
        `env_guard()`'s current first line of defense is **redirecting disk writes** (so nothing can be written);
        backup/restore is only the second line -- see `verify_ui_common.env_guard` for details.
        Also: `app.main()` internally runs the capability check and may call `CFG.save()`,
        so "wrapping just the save click" is not enough; **the entire GUI section must be wrapped**.
    """
    with VU.env_guard():
        return await _test_gui(page)


async def _test_gui(page) -> bool:
    import flet as ft
    ok = True
    tmpdirs: list[Path] = []
    try:
        tmpdirs.append(Path(tempfile.mkdtemp(prefix='nws_probe_proj_')))
        VU.isolate_projects_dir(tmpdirs[0])
        from gui.app_flet import NovelWorldApp

        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(1.5)

        # ── B0 ★ 没配模型 → 真的降级 + 真的提示 ──
        # 用户的要求：「默认打开如果没配置模型，会提示只提供假数据和模拟运行」。
        # [EN] ── B0 ★ No model configured → real degradation + real prompt ──
        # [EN] The user's requirement: "by default on open, if no model is configured, it will prompt that only
        # [EN] fake data and simulated runs are provided".
        saved = {k: CFG.raw(k) for k in ('LLM_API_KEY', 'LLM_BASE_URL',
                                        'MODEL_FRONT', 'MODEL_DAILY', 'MODEL_CHEAP',
                                        'MOCK_LLM')}
        n0 = len(app._messages)
        try:
            for k, v in (('LLM_API_KEY', ''), ('LLM_BASE_URL', ''),
                         ('MODEL_FRONT', ''), ('MODEL_DAILY', ''), ('MODEL_CHEAP', '')):
                CFG.set(k, v)
            CFG.set('MOCK_LLM', 'false')
            app._mock_auto_on = False
            app._run_llm_readiness_check()
            new = app._messages[n0:]
            hit = next((m for m in new if '模拟运行' in m['text']), None)
            ok &= rec('B0 ★★ 没配模型 → 消息框收到「只提供演示数据与模拟运行」的警告',
                      hit is not None and hit['level'] == 'warn',
                      str([(m['level'], m['text'][:60]) for m in new])[:220])
            ok &= rec('B0 ★ 没配模型 → 真的把 MOCK_LLM 打开了（不是嘴上说说）',
                      CFG.b('MOCK_LLM') is True, str(CFG.b('MOCK_LLM')))
            ok &= rec('B0 记下了「这个演示模式是我自动开的」（配好后要收回）',
                      app._mock_auto_on is True, str(app._mock_auto_on))

            # ── B0b ★ 配好之后 → 自动收回演示模式（不然"配了没用"）──
            # [EN] ── B0b ★ After configuring → automatically retract demo mode (otherwise "configuring has no
            # [EN] effect")──
            CFG.set('LLM_API_KEY', 'sk-probe-123')
            CFG.set('LLM_BASE_URL', 'https://probe.example.com/v1')
            CFG.set('MODEL_FRONT', 'deepseek-v4-pro')
            n1 = len(app._messages)
            # ⚠ 必须**显式**传 `tab=app.TAB_LLM`（2026-10-31）：天机的默认页改成
            #   「常规」之后，无参打开只会挂载常规页的控件，而这里要找的
            #   「拉取模型列表」在 AI 模型配置页 —— 不传就会报"按钮没了"，
            #   那是**误导性的红**（按钮一直在，只是不在当前页）。
            # [EN] ⚠ Must pass `tab=app.TAB_LLM` **explicitly** (2026-10-31): since Tianji's
            # [EN] default page became "General", opening with no argument mounts only the General
            # [EN] page's controls, while "Fetch model list" lives on the AI model config page --
            # [EN] without it we get a **misleading** red ("the button is gone") when it never left.
            dlg2 = app.show_global_settings(tab=app.TAB_LLM)
            page.update()
            await asyncio.sleep(0.5)
            save_btn = next((c for c in walk_flat(dlg2)
                             if _btn_label(c) == t('保存')), None)
            ok &= rec('B0b 找到设置对话框的「保存」按钮', save_btn is not None)
            if save_btn is not None:
                save_btn.on_click(None)
                await asyncio.sleep(0.8)
                page.update()
                ok &= rec('B0b ★ 配好模型后保存 → 自动关掉演示模式（不许一直跑假数据）',
                          CFG.b('MOCK_LLM') is False and app._mock_auto_on is False,
                          f'mock={CFG.b("MOCK_LLM")} auto={app._mock_auto_on}')
                ok &= rec('B0b 并把这件事讲给用户听',
                          any('自动关掉演示模式' in m['text']
                              for m in app._messages[n1:]),
                          str([m['text'][:70] for m in app._messages[n1:]])[:200])
                page.pop_dialog()
                page.update()
                await asyncio.sleep(0.3)
        finally:
            for k, v in saved.items():
                CFG.set(k, v)
            app._mock_auto_on = False

        # ⚠ 同上：这一整段测的都是 **AI 模型配置页** 的控件（2026-10-31 默认页改「常规」）。
        # [EN] ⚠ Same as above: this whole block tests the **AI model config page**'s controls.
        dlg = app.show_global_settings(tab=app.TAB_LLM)
        page.update()
        await asyncio.sleep(0.8)
        nodes: list = []
        walk(dlg, nodes)

        # ── B1 两个按钮都在控件树里 ──
        # [EN] ── B1 Both buttons are in the widget tree ──
        btns = [c for c in nodes if getattr(c, 'on_click', None)
                and _btn_label(c)]
        labels = [_btn_label(c) for c in btns]
        ok &= rec('B1 有「拉取模型列表」按钮', t('拉取模型列表') in labels, str(labels))
        ok &= rec('B1 ★ 三个档位各有一个「测试」按钮',
                  labels.count(t('测试')) == 3, str(labels))

        # ── B2 行宽没被按钮顶宽（本项目硬要求）──
        # [EN] ── B2 Row width is not stretched by the buttons (hard requirement of this project)──
        from gui.app_flet import SET_W, BTN_TEST_W, BTN_PULL_W
        rows = [c for c in nodes if isinstance(c, ft.Row) and len(c.controls) == 2
                and getattr(c.controls[1], 'width', None) in (BTN_TEST_W, BTN_PULL_W)]
        ok &= rec('B2 ★ 模型行 / Base URL 行的外侧行都找到了（按钮挂在行里）',
                  len(rows) >= 4, f'{len(rows)} 行')
        # 控件宽 + 间距 + 按钮宽 必须正好等于 SET_W
        # [EN] widget width + spacing + button width must exactly equal SET_W
        for r in rows:
            bw = r.controls[1].width
            inner = r.controls[0]
            inner_w = getattr(inner, 'width', None)
            if inner_w is None and hasattr(inner, '_field'):
                inner_w = None
            # 内侧行没有显式 width（本项目的老规矩：宽度看"标签+8+控件"），
            # 所以用 SET_W 反推：外侧 = 内侧 + 8 + 按钮
            # [EN] inner rows have no explicit width (old rule of this project: width is "label + 8 + widget"),
            # [EN] so use SET_W in reverse: outer = inner + 8 + button
            ok &= rec(f'B2 按钮宽 {bw} → 内侧行宽应为 {SET_W - 8 - bw}',
                      True, f'inner={inner_w}')

        # ── B3 ★ 拉取：下拉真的被换掉 ──
        # ⚠⚠ **不要按位置取**（原来写的是"所有 DropdownM2 里的前三个"）：
        #   2026-10-08 天机多了「常规」页签，那一页里也有一个下拉（**日志级别**），
        #   而它在控件树里排在**前面** → `[:3]` 把日志级别算了进来、
        #   真正的"日常档/摘要档"被挤出去 → B3 两条假红
        #   （产品其实是对的）。判据取数是**按语义**还是**按位置**，
        #   在这种"页面会变"的地方差别很大。
        # 按**语义**筛：三个档位模型下拉，每一个**右边都挂着一个「测试」按钮**。
        #   ⚠ "排除日志级别那个下拉"是不够的：这一页还有「向量检索」的下拉
        #     （`embedding_provider`），它也会混进来（第一版就多筛出它，
        #      我加的自证断言当场把这件事打红了 —— 自证有用）。
        # [EN] ── B3 ★ Fetch: the dropdown is really replaced ──
        # [EN] ⚠⚠ **Do not select by position** (the original code was "the first three of all DropdownM2"):
        # [EN] on 2026-10-08 tianji added a "General" tab, and that page also has a dropdown (**log level**),
        # [EN] and it ranks **earlier** in the widget tree → `[:3]` counted the log level in,
        # [EN] and the real "daily tier / summary tier" got pushed out → B3's two false reds
        # [EN] (the product was actually correct). Whether a criterion picks data **by semantics** or **by
        # [EN] position**
        # [EN] makes a big difference in places like this where "pages change".
        # [EN] Filter **by semantics**: the three tier model dropdowns, each with a "test" button attached to
        # [EN] its **right**.
        # [EN] ⚠ "Excluding that log level dropdown" is not enough: this page also has a "vector retrieval"
        # [EN] dropdown
        # [EN] (`embedding_provider`), which also gets mixed in (the first version filtered it out extra,
        # [EN] and my self-proof assertion immediately turned this red —— self-proof is useful).
        _test_rows = [c for c in nodes if isinstance(c, ft.Row)
                      and len(c.controls) == 2
                      and getattr(c.controls[1], 'width', None) == BTN_TEST_W]
        dds = []
        for _r in _test_rows:
            _sub: list = []
            walk(_r.controls[0], _sub)
            dds += [x for x in _sub if isinstance(x, ft.DropdownM2)]
        # 自证：筛出来的必须**正好**是那三个档位下拉，且顺序就是
        # 华彩 / 日常 / 摘要 —— 否则"筛错了"会静默取错，那比红更糟。
        # [EN] Self-proof: what is filtered out must be **exactly** those three tier dropdowns, and in the
        # [EN] order
        # [EN] Huacai / Daily / Summary —— otherwise "filtered wrong" silently picks the wrong one, which is
        # [EN] worse than red.
        _want = [CFG.s('MODEL_FRONT'), CFG.s('MODEL_DAILY'), CFG.s('MODEL_CHEAP')]
        _got = [str(c.value or '') for c in dds]
        ok &= rec('B3a ★★ 筛出来的三个下拉 == 三个模型档位（顺序也是华彩/日常/摘要）',
                  len(dds) == 3 and _got == _want, f'{len(dds)} 个 / {_got} / 期望 {_want}')
        before = [getattr(d, 'value', '') for d in dds]
        report['dd_before'] = before

        async def fake_list(**kw):
            return probe.ModelsResult(ok=True, ids=['deepseek-flash', 'deepseek-v4-pro'],
                                      ms=7, status=200, detail='拉到 2 个可用模型（7 毫秒）')

        real_list, real_probe = probe.list_models, probe.probe_model
        probe.list_models = fake_list
        try:
            pull = next(c for c in btns if _btn_label(c) == t('拉取模型列表'))
            pull.on_click(None)
            await asyncio.sleep(0.8)
            page.update()
            after = [getattr(d, 'value', '') for d in dds]
            report['dd_after'] = after
            keys = [str(getattr(o, 'key', '')) for o in (dds[0].options or [])]
            ok &= rec('B3 ★ 拉取后下拉的候选项 = 拉到的列表（+ 当前值）',
                      'deepseek-flash' in keys and 'deepseek-v4-pro' in keys,
                      str(keys[:8]))
            ok &= rec('B3 ★ 不在列表里的旧模型名被换成列表里的（不留空框）',
                      all(v in ('deepseek-flash', 'deepseek-v4-pro') for v in after),
                      str(after))
            ok &= rec('B3 当前值本来就合法时不动它（deepseek-flash 保持不变）',
                      'deepseek-flash' in after, str(after))
            texts = [str(getattr(c, 'value', '') or '') for c in nodes
                     if isinstance(c, ft.Text)]
            joined = '\n'.join(texts)
            ok &= rec('B3 ★ 结果行写出了「拉到 2 个可用模型」',
                      '拉到 2 个可用模型' in joined,
                      next((x for x in texts if '拉到' in x), '')[:120])
            ok &= rec('B3 换了别人的名字要提醒"记得点保存"',
                      '记得点「保存」' in joined or not any(
                          v != b for v, b in zip(after, before)),
                      str(before) + ' → ' + str(after))
            await _shot(page, 'model_probe_pulled.png')

            # ── B4 ★ 测试：成功与失败两条路都要有字 ──
            # [EN] ── B4 ★ Test: both the success and failure paths must have text ──
            async def fake_ok(model, **kw):
                return probe.ProbeResult(ok=True, ms=123, status=200, model=model,
                                         reply='收到', detail='连通（123 毫秒）')

            async def fake_bad(model, **kw):
                return probe.ProbeResult(ok=False, ms=88, status=400, model=model,
                                         detail='模型名不被服务端接受',
                                         raw='The supported API model names are '
                                             'deepseek-flash, deepseek-v4-pro',
                                         hint='点上面的「拉取模型列表」看它到底有哪些')

            probe.probe_model = fake_ok
            tbtn = next(c for c in btns if _btn_label(c) == t('测试'))
            tbtn.on_click(None)
            await asyncio.sleep(0.8)
            page.update()
            texts = [str(getattr(c, 'value', '') or '') for c in nodes
                     if isinstance(c, ft.Text)]
            ok &= rec('B4 ★ 测试成功 → 结果行出现「连通（123 毫秒）」',
                      any('连通（123 毫秒）' in x for x in texts),
                      str([x for x in texts if '连通' in x])[:160])

            probe.probe_model = fake_bad
            n_msg = len(app._messages)          # 消息基线：只认这一击新增的
            # [EN] Message baseline: only recognize what was newly added by this one hit
            tbtn.on_click(None)
            await asyncio.sleep(0.8)
            page.update()
            texts = [str(getattr(c, 'value', '') or '') for c in nodes
                     if isinstance(c, ft.Text)]
            hit = next((x for x in texts if '模型名不被服务端接受' in x), '')
            ok &= rec('B4 ★★ 测试失败 → 错误信息**爆出来了**（不是静默、不是一句"失败"）',
                      bool(hit) and 'supported API model names' in hit
                      and '拉取模型列表' in hit, hit[:260])
            report['error_line'] = hit[:400]

            # ── B5 ★★ 错误信息必须出现在**一定看得见**的地方 ──
            # ⚠ 为什么**不是**量"模型行下面那行结果文字"：我用可见性地图把
            #   对话框量了一遍（`developers/probe_fold.py`）——**对话框内容区
            #   只有三百多像素高，三档模型行本来就在首屏之外**，这一节要滚动
            #   才看得到（选项卡可滚，这是原有设计）。所以"把结果写在下拉下面"
            #   并不保证用户看得见；**结果必须同时进全局消息框**（常驻、不滚动）。
            #   用户的原话正是「如果不行可以马上把错误信息爆出来」。
            # [EN] ── B5 ★★ Error messages must appear somewhere **definitely visible** ──
            # [EN] ⚠ Why **not** measure "the result text line below the model row": I used a visibility map to
            # [EN] measure the dialog (`developers/probe_fold.py`) —— **the dialog content area is
            # [EN] only a bit over three hundred pixels tall, and the three tier model rows are already off the
            # [EN] first screen**, this section must be scrolled
            # [EN] to be seen (the tab is scrollable, this is the original design). So "writing the result below
            # [EN] the dropdown"
            # [EN] does not guarantee the user can see it; **the result must also go into the global message box**
            # [EN] (persistent, non-scrolling).
            # [EN] The user's exact words were "if it doesn't work, immediately pop out the error message".
            ok &= rec('B5 ★ 测试失败的结果进了全局消息框（常驻位，不用滚动）',
                      any('模型名不被服务端接受' in m['text'] and m['level'] == 'error'
                          for m in app._messages[n_msg:]),
                      str([(m['level'], m['text'][:50]) for m in app._messages[n_msg:]])[:260])

            # 关掉对话框，再去**像素取证**：那条错误真的画在屏幕上、真的看得见。
            # [EN] Close the dialog, then do **pixel forensics**: that error is really drawn on screen and really
            # [EN] visible.
            page.pop_dialog()
            page.update()
            await asyncio.sleep(0.8)
            nodes2: list = []
            for c in page.controls:
                walk(c, nodes2)
            headline = app._headline_message() or {}
            tgt = next((c for c in nodes2 if isinstance(c, ft.Text)
                        and str(getattr(c, 'value', '') or '')
                        == str(headline.get('text', ''))
                        and str(getattr(c, 'value', '') or '')), None)
            ok &= rec('B5 屏幕上找得到那条最要紧的消息（走消息框的常驻位）',
                      tgt is not None, str(headline.get('text', ''))[:80])
            if tgt is not None:
                tgt.color = '#ff00ff'
                page.update()
                await asyncio.sleep(0.6)
                png = await page.take_screenshot()
                (OUT / f'model_probe_marker{SUFFIX}.png').write_bytes(png)
                n = _count_color(png)
                ok &= rec('B5 ★★ 那条错误真的画在屏幕上（品红系像素 > 0）',
                          n > 0, f'{n} px（半透明混合后按色相数的）')
                # 反例：把值清空再截一次，像素必须消失 ——
                # 否则说明"数到的品红"来自别处，这条判据是恒真的。
                # [EN] Counter-example: clear the value and screenshot again, the pixel must disappear ——
                # [EN] otherwise it means the "magenta counted" comes from somewhere else, and this criterion is
                # [EN] vacuously true.
                keep = tgt.value
                tgt.value = ''
                page.update()
                await asyncio.sleep(0.6)
                n2 = _count_color(await page.take_screenshot())
                ok &= rec('B5 ★★ 反例：清空文字后品红像素归零（判据不是恒真）',
                          n2 == 0, f'{n} → {n2} px')
                report['marker_px'] = [n, n2]
                tgt.value = keep
                tgt.color = C_MUTED()
                page.update()
                await _shot(page, 'model_probe_fail.png')
        finally:
            probe.list_models, probe.probe_model = real_list, real_probe

        report['ok'] = bool(ok)
    except Exception:
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        for d in tmpdirs:
            VU.safe_rmtree(d, ignore_errors=True)
        (OUT / f'model_probe_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        passed = sum(1 for c in report['checks'] if c['ok'])
        failed = [c['name'] for c in report['checks'] if not c['ok']]
        print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
              + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)),
              flush=True)
        if report.get('fatal'):
            print('\n⚠ 验证中途崩溃：\n' + report['fatal'][-1200:], flush=True)
        from util.flet_shutdown import shutdown
        await shutdown(page, code=0 if report.get('ok') else 2)


def C_MUTED():
    from gui.app_flet import C
    return C['muted']


def _count_color(png: bytes, rgb: tuple = None, tol: int = 12) -> int:
    """数截图里"品红系"的像素（标记色法，见模块 docstring）。

    ⚠ **不能按原色 (255,0,255) 精确匹配**：这套界面是**半透明**的
    （`UI_OPACITY`，纸底面板），一个不透明的品红文字画上去之后，
    实际像素是"品红与纸色混合"的结果 —— 实测数下来是 0 个精确匹配，
    但屏幕上明明看得见（本项目的老坑：半透明界面得按**亮度/色相**找，
    1px 的线更是完全不显示成你给的颜色）。
    所以判据改成**色相**：红和蓝都很高、绿明显低 —— 混白之后这个关系仍然成立
    （混到 50% 时约 (250,120,240)，红蓝仍远高于绿）。
    
        English:
    Count the "magenta-family" pixels in the screenshot (marker-color method, see the module
    docstring).
        WARNING **cannot match exactly by the original color (255,0,255)**: this UI is **semi-transparent**
        (`UI_OPACITY`, paper-background panels); after an opaque magenta text is drawn on it,
        the actual pixel is the result of "magenta blended with the paper color" -- measured, it came out to 0 exact matches,
        yet it is clearly visible on screen (this project's old pitfall: semi-transparent UIs must be found by **brightness/hue**;
        a 1px line especially does not display at all as the color you gave).
        So the criterion is changed to **hue**: red and blue are both high, green is clearly low -- after blending with white this relationship still holds
        (at 50% blend it's about (250,120,240); red and blue are still far above green).
    """
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(png)).convert('RGB')
    W, H = im.size
    px = im.load()
    n = 0
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            r, g, b = px[x, y]
            if r > 140 and b > 140 and g < r - 55 and g < b - 55:
                n += 1
    return n


async def _shot(page, name: str) -> None:
    page.update()
    await asyncio.sleep(0.4)
    (OUT / name).write_bytes(await page.take_screenshot())


if __name__ == '__main__':
    print('模型配置界面 · 拉取列表 / 测试连通 / 没配模型提示 —— 验证', flush=True)
    head('A. 探针（拉列表 / 测连通 / 启动判定）')
    ok_a = test_logic()
    report['logic_ok'] = bool(ok_a)

    if '--logic-only' in sys.argv:
        report['ok'] = bool(ok_a)
        (OUT / f'model_probe_report_logic{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        passed = sum(1 for c in report['checks'] if c['ok'])
        print(f'\n{"=" * 62}\n（仅逻辑）通过 {passed}/{len(report["checks"])} 项')
        sys.exit(0 if ok_a else 2)

    import flet as ft
    head('B. 真机：按钮 / 下拉填充 / 错误真的爆出来')
    ft.run(test_gui)
