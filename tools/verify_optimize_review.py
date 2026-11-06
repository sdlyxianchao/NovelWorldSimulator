# -*- coding: utf-8 -*-
"""验证：开卷「AI 优化」拿不到东西时的三档处理 + 数组抢救 + 界面不许空气泡。

## 这份脚本盯的是哪次事故

用户 2026-10-06 报：「开卷的 AI 优化还是有问题」。当时的对话日志里：

    对话 · AI → 作者          ← 标题后面**一片空白**

根因不是"提示词写得不好"，是**预算**：`review_settings` 当时写死 `max_tokens=800`，
而模型是**推理型** —— 思考内容也吃这份额度，800 个 token 全被思考吃掉，
`content` 是空字符串、`finish_reason=length`。界面上就是 AI 一个空气泡。

同一次开卷里还有第二个受害者：`progress`（进度表）用默认 2000 被截断
（日志 849 行 `3228+2000 token`），而**数组当时没有抢救**（`repair_json` 只认 dict），
`extract_json_list` 返回空表 → 进度表**静默变成 0 个节点**，没有任何报错。

## 检查什么

A 纯逻辑（用**日志里那段真实截断数据**当夹具，零网络）
  · 截断的 JSON 数组能救回「已经写完的那几个节点」，严格解析救不回
  · 救回的内容**必须是原文子串**（政策：只补结构、不补内容）
  · 「空容器」必须算"没拿到"（否则重试与抢救是死代码）
  · 提示词里写死了格式与长度约束；且**不再写死"请用中文"**（改由输出语言管）
B 打桩 LLM（零网络）驱动 `review_settings` 的四条路：
  正常一次过 / 空正文→加大预算重试 / 一直空→非空兜底 / 太短→重试
C 打桩 LLM 驱动 `build_progress_table`：截断的数组要被救回来，并留下说明
D **真机**：走完整开卷向导（AI 优化打开），把 `optimize_review` 打桩成"永远返回空正文"
  · AI 气泡**不能是空的**（用户看到的原始症状）
  · 日志里要有"重试过一次"的说明

跑法：
    .venv\\Scripts\\python.exe tools/verify_optimize_review.py
产出：
    assets/screenshots/optimize_review_report.json
    assets/screenshots/optimize_review_1_empty_reply.png

English:
Verify: the three tiers of handling when open-book "AI optimization" gets nothing + array rescue
+ the interface must not have empty bubbles.
## Which accident does this script target
User reported on 2026-10-06: "open-book AI optimization still has problems". In the dialogue log
at the time:
    Dialogue · AI -> Author          <- **completely blank** after the title
The root cause wasn't "the prompt was poorly written", it was **budget**: `review_settings`
hardcoded `max_tokens=800` at the time,
and the model is a **reasoning** type -- the thinking content also consumes this quota, all 800
tokens were eaten by thinking,
`content` was an empty string, `finish_reason=length`. On the interface it was one empty AI
bubble.
In the same open-book session there was a second victim: `progress` (the progress table) was
truncated using the default 2000
(log line 849 `3228+2000 token`), and **the array had no rescue at the time** (`repair_json`
only recognized dict),
`extract_json_list` returned an empty table -> the progress table **silently became 0 nodes**,
without any error.
## What to check
A pure logic (using **that real truncated data from the log** as the fixture, zero network)
  · a truncated JSON array can rescue "the nodes that were already written", strict parsing cannot
  · the rescued content **must be a substring of the original text** (policy: fix structure only, not content)
  · "empty container" must count as "nothing obtained" (otherwise retry and rescue are dead code)
  · the prompt hardcodes the format and length constraints; and **no longer hardcodes "please use Chinese"** (now governed by the output language)
B stub LLM (zero network) drives `review_settings` through four paths:
  normal one-shot pass / empty body->retry with larger budget / always empty->non-empty fallback / too short->retry
C stub LLM drives `build_progress_table`: the truncated array must be rescued, and a note left
behind
D **real machine**: run the full open-book wizard (AI optimization on), stub `optimize_review`
to "always return empty body"
  · the AI bubble **must not be empty** (the original symptom the user saw)
  · the log must contain a note that "it retried once"
How to run:
    .venv\\Scripts\\python.exe tools/verify_optimize_review.py
Output:
    assets/screenshots/optimize_review_report.json
    assets/screenshots/optimize_review_1_empty_reply.png
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')          # 演示模式：零网络、零成本、可复现
# [EN] Demo mode: zero network, zero cost, reproducible
CFG.set('UI_LANG', 'zh')

from gui.app_flet import NovelWorldApp  # noqa: E402
from i18n import set_lang, t  # noqa: E402
set_lang('zh')

import ingest.optimize as OPT  # noqa: E402
import ingest.progress as PROG  # noqa: E402
from llm.router import llm  # noqa: E402
from util import jsonio  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
LOG_DIR = APP_DIR / 'logs'

_ITEMS: list = []


def ok(name: str, cond, detail: str = '') -> bool:
    _ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


# ══════════════════════════════════════════════════════════════════════
#  A 组夹具：一段**被砍在半句话里**的进度表 JSON 数组
# [EN] Group A fixture: a progress table JSON array **cut off mid-sentence**
# ══════════════════════════════════════════════════════════════════════
# ⚠ 早先这里直接去读 `logs/nws-dialogue-<日期>.log`，把**某一次真实运行**的原文捞出来当夹具。
#   两个毛病：① 它把**一本具体的书**的内容带进了测试（这个程序必须与任何具体作品无关）；
#   ② 它依赖一个随时会被 `cleanup_old_logs` 清掉、或用户自己删掉的**用户文件**。
#   现在改成脚本**自己造**一条同样形状的样本 —— 判据要证的是"这种形状能被救回来"，
#   而不是"某本书的那一段能被救回来"。
# [EN] ⚠ Previously this directly read `logs/nws-dialogue-<date>.log` and pulled the raw text of **some
# [EN] real run** as the fixture.
# [EN] Two problems: ① it dragged the content of **a specific book** into the test (this program must
# [EN] be unrelated to any specific work);
# [EN] ② it depended on a **user file** that could be cleared at any time by `cleanup_old_logs`, or
# [EN] deleted by the user.
# [EN] Now changed so the script **builds its own** sample of the same shape -- the criterion must
# [EN] prove "this shape can be rescued",
# [EN] not "that passage from some book can be rescued".
#
# ★ 形状要**逐字同形**（这条是事故的"指纹"）：第一个节点完整，
#   第二个节点写完「名称」之后**断在「概要」的半句话中间** ——
#   所以严格解析一个都拿不到，而抢救只该拿回**两个**节点名，
#   且第二个节点的「概要」必须**整条丢掉**（不许把半句话塞进设定里）。
# [EN] ★ The shape must be **verbatim identical** (this is the accident's "fingerprint"): the first
# [EN] node is complete,
# [EN] the second node, after writing the "name", **breaks off in the middle of a sentence in the
# [EN] "summary"** --
# [EN] so strict parsing gets nothing, while rescue should only recover **two** node names,
# [EN] and the second node's "summary" must be **entirely discarded** (no stuffing half a sentence into
# [EN] the settings).
_CUT_TAIL = '最可信的人露出破绽而没人察觉'


def synthetic_truncated_progress() -> str:
    """一条被 max_tokens 砍断的进度表数组（自带夹具，不读任何用户文件）。
        English:
    A progress-table array truncated by max_tokens (comes with its own fixture, does not read any
    user files).
    """
    return (
        '[\n'
        ' {\n'
        '  "名称": "开端",\n'
        '  "概要": "故事开始，人物登场，核心悬念提出。",\n'
        '  "完成判据": "起始场景完成，主角被卷入。"\n'
        ' },\n'
        ' {\n'
        '  "名称": "发展",\n'
        '  "概要": "悬念展开，线索逐渐揭开，' + _CUT_TAIL
    )


# ══════════════════════════════════════════════════════════════════════
#  打桩工具：让 `llm.chat` 按脚本吐东西（零网络）
# [EN] Stubbing tool: make `llm.chat` emit things according to the script (zero network)
# ══════════════════════════════════════════════════════════════════════
class Stub:
    """按 `purpose` 返回预先安排好的 `(text, meta)`，并记录每次的 max_tokens。
        English:
    Return the pre-arranged `(text, meta)` according to `purpose`, and record the max_tokens of each
    call.
    """

    def __init__(self, script: dict):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[dict] = []
        self._orig = llm.chat

    async def __aenter__(self):
        llm.chat = self._fake
        return self

    async def __aexit__(self, *exc):
        llm.chat = self._orig
        return False

    async def _fake(self, tier, messages, *, purpose="", json_mode=False,
                    temperature=0.7, max_tokens=2000, timeout=None,
                    return_meta=False, **kw):
        self.calls.append({'purpose': purpose, 'max_tokens': max_tokens,
                           'n_messages': len(messages)})
        seq = self.script.get(purpose)
        if not seq:
            # 没安排的 purpose → 交回原实现（MOCK 模式，离线）
            # [EN] Unarranged purpose -> fall back to the original implementation (MOCK mode, offline)
            return await self._orig(tier, messages, purpose=purpose,
                                    json_mode=json_mode, temperature=temperature,
                                    max_tokens=max_tokens, timeout=timeout,
                                    return_meta=return_meta, **kw)
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, Exception):
            raise item
        text, meta = item
        meta = dict(meta or {})
        meta.setdefault('purpose', purpose)
        meta.setdefault('max_tokens', max_tokens)
        meta.setdefault('tout', 0)
        meta.setdefault('tin', 0)
        # ★ **必须照着真 router 广播事件**（`llm.chat` 的 request/response）。
        #   第一版没做这一步，于是"界面把空输出写在日志里"这条判据永远红 ——
        #   不是产品没写，是桩函数把广播整个跳过了：GUI 的 `on_llm` 压根没被调用。
        #   **替换掉 `llm.chat` 就等于替换掉了它所有的副作用**，这一条要记住。
        # [EN] ★ **Must broadcast events exactly like the real router** (`llm.chat`'s request/response).
        # [EN] The first version didn't do this step, so the criterion "the interface writes empty output into
        # [EN] the log" stayed red forever --
        # [EN] not because the product didn't write it, but because the stub function skipped the broadcast
        # [EN] entirely: the GUI's `on_llm` was never called at all.
        # [EN] **Replacing `llm.chat` means replacing all its side effects**; remember this one.
        if purpose in self.script:
            llm._emit({'type': 'request', 'tier': tier, 'model': 'stub',
                       'purpose': purpose, 'messages': messages})
            llm._emit({'type': 'response', 'tier': tier, 'model': 'stub',
                       'purpose': purpose, 'text': text,
                       'tin': meta.get('tin', 0), 'tout': meta.get('tout', 0),
                       'cost': 0.0, 'ms': 0,
                       'finish_reason': meta.get('finish_reason', 'stop'),
                       'truncated': bool(meta.get('truncated')),
                       'has_reasoning': bool(meta.get('has_reasoning')),
                       'empty_output': bool(meta.get('empty_output')),
                       'max_tokens': max_tokens})
        return (text, meta) if return_meta else text


def _empty_meta() -> dict:
    """「额度全被思考吃掉」的响应形状 —— 与日志里那条一模一样。
        English:
    The response shape for "the entire quota eaten by thinking" — exactly the same as the one in the
    logs.
    """
    return {'finish_reason': 'length', 'truncated': True, 'has_reasoning': True,
            'empty_output': True}


# ══════════════════════════════════════════════════════════════════════
#  A / B / C —— 纯逻辑 + 打桩，不需要窗口
# [EN] A / B / C -- pure logic + stubbing, no window needed
# ══════════════════════════════════════════════════════════════════════
async def test_logic(report: dict) -> None:
    # ── A1 数组抢救（**自带夹具**：一条被砍断的进度表数组）──
    # [EN] -- A1 array rescue (**self-contained fixture**: a cut-off progress table array) --
    raw = synthetic_truncated_progress()
    report['fixture_len'] = len(raw)
    report['fixture_cut_tail'] = _CUT_TAIL
    strict = jsonio.extract_json_list(raw, None)
    salv = jsonio.repair_json_list(raw, None)
    report['arr'] = {'strict': strict, 'salvaged_names':
                     [x.get('名称') for x in (salv or [])]}
    ok('A：★ 严格解析**救不回**被截断的数组（复现事故）', not strict, str(strict))
    ok('A：★ 「最长可闭合前缀」抢救能把已经写完的节点捞回来',
       bool(salv) and len(salv) >= 2, f'{len(salv or [])} 个')
    ok('A：★ 捞回来的正好是**两个**节点（第一个完整、第二个只写到「名称」就断了）',
       [x.get('名称') for x in (salv or [])] == ['开端', '发展'],
       str([x.get('名称') for x in (salv or [])]))
    ok('A：★ 捞回的内容**都是原文子串**（政策：只补结构、不补内容）',
       all(str(v) in raw for nd in (salv or []) for v in nd.values() if v),
       json.dumps(salv, ensure_ascii=False)[:100])
    ok('A：被砍在半句话里的那个字段**整条丢掉**，不塞半句话进去',
       all(_CUT_TAIL not in str(v) for nd in (salv or []) for v in nd.values()),
       json.dumps(salv, ensure_ascii=False)[:100])

    # ── A2 空容器必须算"没拿到"（否则重试/抢救是死代码）──
    # [EN] -- A2 empty container must count as "nothing obtained" (otherwise retry/rescue is dead code) --
    v, _s = jsonio.parse_or_repair('[{"名称":"甲"},{"名称":"乙"', [], want=list)
    ok('A：★ `parse_or_repair` 把「空容器」判成失败并继续抢救', bool(v), str(v))
    empty_hit, _s2 = jsonio.parse_or_repair('[]', [], want=list)
    ok('A：模型真的返回空数组时仍然返回空（不误报成功、也不死循环）',
       empty_hit == [], str(empty_hit))

    # ── A3 提示词：格式与长度写死了没 ──
    # [EN] -- A3 prompt: are format and length hardcoded --
    rp = OPT._REVIEW_PROMPT
    report['review_prompt_len'] = len(rp)
    for pat, why in (('【最突出的问题】', '给出了要照抄的三段结构'),
                     ('300 字', '写死了总长度'),
                     ('第一行就是', '禁止开场白'),
                     ('不要输出思考过程', '明确不要思考内容'),
                     ('不要用 JSON', '禁止 JSON')):
        ok(f'A：体检提示词{why}', pat in rp, pat)
    ok('A：★ 体检提示词**不再写死「请用中文」**'
       '（输出语言由 `util/outlang` 统一管，写死会跟「输出英文」打架）',
       '请用中文' not in rp, '')
    ok('A：体检预算不再是 800（日志里就是撞的这个数）',
       OPT._REVIEW_MAX_TOKENS >= 2000, str(OPT._REVIEW_MAX_TOKENS))

    pp = PROG._BUILD_PROMPT
    for pat, why in (('4~8 个', '写死了节点条数上界'),
                     ('不超过 6 个字', '写死了名称长度'),
                     ('不超过 80 个字', '写死了概要长度'),
                     ('只输出 JSON 数组本身', '禁止开场白/代码块')):
        ok(f'A：进度表提示词{why}', pat in pp, pat)
    ok('A：进度表/对齐都显式给了预算（不再吃默认 2000）',
       PROG._PROGRESS_MAX_TOKENS > 2000 and PROG._ALIGN_MAX_TOKENS > 2000,
       f'{PROG._PROGRESS_MAX_TOKENS}/{PROG._ALIGN_MAX_TOKENS}')

    # ── B 打桩驱动 review_settings ──
    # [EN] -- B stub-driven review_settings --
    body = ('【最突出的问题】主线悬念太散。'
            '\n【建议优先打磨】· 反派的动机……'
            '\n【等你回话】告诉我先改哪条。')
    settings = {'人物': [{'姓名': '甲'}], '世界观': '示例世界观'}

    async with Stub({'optimize_review': [(body, {'finish_reason': 'stop'})]}) as st:
        got = await OPT.review_settings(settings, name='我的新书', tier='黄金')
        c = list(st.calls)
    report['b_normal'] = {'calls': len(c), 'max_tokens': [x['max_tokens'] for x in c]}
    ok('B：正常一次就拿到 → **不重试**（省一次调用）',
       len(c) == 1 and got == body, f'{len(c)} 次 / {c}')
    ok('B：第一次的预算就是加大后的值（不是 800）',
       c and c[0]['max_tokens'] == OPT._REVIEW_MAX_TOKENS, str(c))

    # 空正文 + 截断 + 有思考 → 应重试一次，且第二次预算更大
    # [EN] empty body + truncated + has thinking -> should retry once, and the second time the budget is
    # [EN] larger
    async with Stub({'optimize_review': [('', _empty_meta()), (body, {'finish_reason': 'stop'})]}) as st:
        got = await OPT.review_settings(settings, name='我的新书', tier='黄金')
        c = list(st.calls)
    budgets = [x['max_tokens'] for x in c]
    # ⚠ `take_review_notes()` 是**取走并清空**（跟 `extractor.take_notes()` 一个规矩），
    #   所以只能取一次 —— 第一版在这里取了两次，第二次当然是空表，
    #   判据跟着红了一条，看着像"产品没记说明"，其实是判据自己把证据吃掉了。
    # [EN] ⚠ `take_review_notes()` is **take-and-clear** (same rule as `extractor.take_notes()`),
    # [EN] so it can only be taken once -- the first version took it twice here, and the second time was of
    # [EN] course an empty table,
    # [EN] and a criterion went red along with it, looking like "the product didn't record the
    # [EN] description", when actually the criterion itself ate the evidence.
    notes = OPT.take_review_notes()
    report['b_retry'] = {'calls': len(c), 'budgets': budgets, 'notes': notes}
    ok('B：★ 空正文 → **重试一次**（复现用户那个空气泡的场景）',
       len(c) == 2, f'{len(c)} 次')
    ok('B：★ 重试的预算**确实更大**', len(budgets) == 2 and budgets[1] > budgets[0],
       str(budgets))
    ok('B：重试成功后返回的是正文', got == body, got[:40])
    ok('B：重试这件事被记进说明（界面才讲得清）',
       any('重试' in n for n in notes), str(notes))

    # 一直空 → 兜底必须**非空**
    # [EN] always empty -> the fallback must be **non-empty**
    async with Stub({'optimize_review': [('', _empty_meta())]}) as st:
        got = await OPT.review_settings(settings, name='我的新书', tier='黄金')
        c = list(st.calls)
    report['b_fallback'] = {'calls': len(c), 'len': len(got or '')}
    ok('B：★ 两次都空 → 返回的兜底**非空**（空气泡就是用户报的那个 bug）',
       bool(got.strip()) and len(got) > 20, f'len={len(got or "")}')
    ok('B：兜底里明确告诉作者"可以直接下指令"',
       '打字' in got or '告诉我' in got, got[:60])

    # 太短（残句）也要重试
    # [EN] too short (fragment) also requires a retry
    async with Stub({'optimize_review': [('好的，', {'finish_reason': 'stop'}),
                                         (body, {'finish_reason': 'stop'})]}) as st:
        got = await OPT.review_settings(settings, name='我的新书', tier='黄金')
        c = list(st.calls)
    report['b_short'] = {'calls': len(c), 'got': got[:24]}
    ok('B：★ 只吐出几个残字（<40 字）也算没拿到 → 重试',
       len(c) == 2 and got == body, f'{len(c)} 次 / {got[:20]}')

    # 调用直接抛错
    # [EN] the call throws directly
    async with Stub({'optimize_review': [RuntimeError('boom')]}) as st:
        got = await OPT.review_settings(settings, name='我的新书', tier='黄金')
    ok('B：调用抛错也返回兜底（界面不会崩、也不会是空的）',
       bool(got.strip()), got[:40])
    OPT.take_review_notes()

    # ── C 打桩驱动 build_progress_table：截断数组要救回来 ──
    # [EN] -- C stub-driven build_progress_table: a truncated array must be rescued --
    async with Stub({'progress': [(raw, {**_empty_meta(), 'max_tokens': 3000})]}) as st:
        nodes = await PROG.build_progress_table('起：甲。承：乙。转：丙。合：丁。')
        c = list(st.calls)
    report['c_progress'] = {'nodes': [n.name for n in nodes],
                            'calls': len(c), 'budgets': [x['max_tokens'] for x in c]}
    ok('C：★ 进度表被截断后**救回节点**（以前这里是 0 个，且不报错）',
       len(nodes) >= 2, f'{len(nodes)} 个：{[n.name for n in nodes]}')
    ok('C：进度表给了显式预算（不吃默认 2000 —— 日志里正好撞了 2000）',
       bool(c) and c[0]['max_tokens'] == PROG._PROGRESS_MAX_TOKENS, str(c))
    ok('C：抢救回来的节点里没有"空壳节点"（补悬空括号的产物要被丢掉）',
       all(n.name.strip() for n in nodes), str([n.name for n in nodes]))


# ══════════════════════════════════════════════════════════════════════
#  D —— 真机：走完整开卷向导，AI 体检永远返回空正文
# [EN] D -- real machine: run the full open-book wizard, AI checkup always returns an empty body
# ══════════════════════════════════════════════════════════════════════
def make_fixture(root: Path) -> Path:
    src = root / '雨夜来客'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text(
        '# 大纲\n\n起：雨夜来客打破平静。\n承：旧事被翻出。\n转：最可信的人露出破绽。\n合：有人离开。\n',
        encoding='utf-8')
    (src / '人物设定.md').write_text(
        '# 人物\n\n## 主角\n掌柜，沉默寡言。\n\n## 阿枝\n伙计，嘴上不饶人。\n', encoding='utf-8')
    (src / '正文' / '第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。\n\n'
        '「你今日话里有话。」\n\n「话就是话，哪来的里外。」\n' * 8, encoding='utf-8')
    return src


async def test_gui(page: ft.Page, report: dict) -> None:
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.window.width = 1260
    page.window.height = 860
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_optrev_'))
    try:
        VU.isolate_projects_dir(tmp / 'Projects')
        src = make_fixture(tmp)

        async def shot(name: str):
            page.update()
            await asyncio.sleep(0.35)
            png = OUT / name
            png.write_bytes(await page.take_screenshot())
            return png

        # AI 体检永远返回"空正文 + 截断 + 有思考" —— 一比一复现事故现场
        # [EN] AI checkup always returns "empty body + truncated + has thinking" -- a one-to-one reproduction
        # [EN] of the accident scene
        async with Stub({'optimize_review': [('', _empty_meta())]}):
            app.show_import_wizard()
            page.update()
            await asyncio.sleep(0.6)
            app._wizard_path = str(src)
            app._wizard_name = '空回复验证'
            app._wizard_opts['ai_optimize'] = True
            app._wizard_opts['repair_source'] = False    # 这一步会停下等确认，脚本里跳过
            # [EN] this step will stop and wait for confirmation, skipped in the script
            app._do_import(page)

            st = app._ingest_state
            # 同意门（夹具含正文 → 必然出现）
            # [EN] consent gate (fixture contains body text -> will necessarily appear)
            for _ in range(200):
                await asyncio.sleep(0.1)
                ui = st.get('ui') or {}
                p = ui.get('consent_panel')
                if p is not None and getattr(p, 'visible', False):
                    break
            ui = st.get('ui') or {}
            for b in (ui.get('consent_boxes') or []):
                b.value = True
                if getattr(b, 'on_change', None):
                    b.on_change(None)
                await asyncio.sleep(0.02)
            if ui.get('consent'):
                ui['consent'](True)

            # 等它进到 AI 对话阶段（体检已经跑完、气泡已经加进去）
            # [EN] wait for it to reach the AI dialogue stage (checkup already finished, bubbles already added)
            for _ in range(400):
                await asyncio.sleep(0.1)
                if st.get('phase') == 'chat':
                    break
            await asyncio.sleep(1.4)
            ui = st.get('ui') or {}
            await shot('optimize_review_1_empty_reply.png')

            # 把气泡里的字全收上来
            # [EN] collect all the text in the bubbles
            bubbles: list[str] = []
            for row in (ui['chat_list'].controls if ui.get('chat_list') else []):
                for c in getattr(row, 'controls', []) or []:
                    if isinstance(c, ft.Container):
                        inner = c.content
                        bubbles.append(str(getattr(inner, 'value', inner) or ''))
            report['d_bubbles'] = bubbles
            # ⚠ 取**整段**日志，不要只取尾部几格：日志最后是阶段分隔线 + 空行
            #   （`[空行]` / `[分隔线]`），只取尾巴会什么都搜不到 ——
            #   第一版就是这么误报的（'重试' 那条能过是因为取巧搜的是别处）。
            # [EN] ⚠ take the **entire** log, not just the last few cells: the log ends with a stage divider +
            # [EN] blank line
            # [EN] (`[blank line]` / `[divider]`); taking only the tail will find nothing --
            # [EN] the first version misreported it exactly this way (the 'retry' one passed because it sneakily
            # [EN] searched elsewhere).
            report['d_log_all'] = VU.log_cells(
                ui['log_list'].controls) if ui.get('log_list') else []
            report['d_log_tail'] = report['d_log_all'][-14:]
            logs = report['d_log_all']

            ok('D：★ 真机走到 AI 对话阶段（体检那一轮已经跑过）',
               st.get('phase') == 'chat', str(st.get('phase')))
            ok('D：★★ 界面上 AI 的气泡**一个都不是空的**'
               '（用户报的就是这里一片空白）',
               bool(bubbles) and all(b.strip() for b in bubbles),
               f'{len(bubbles)} 个气泡，空的有 '
               f'{sum(1 for b in bubbles if not b.strip())} 个')
            ok('D：★ AI 那条气泡里有实打实的兜底文案',
               any(len(b.strip()) > 20 for b in bubbles),
               str([b[:30] for b in bubbles]))
            ok('D：日志里有一条"重试过一次"的说明（作者才知道背后发生了什么）',
               any('重试' in x for x in logs),
               str([x for x in logs if '重试' in x][:2]))
            ok('D：日志里点破了"正文为空 / 思考吃掉额度"',
               any('空' in x and ('思考' in x or '一个字' in x) for x in logs),
               str([x for x in logs if '空' in x][:2]))

            await shutdown_ingest(page, app)
    finally:
        for b in [tmp]:
            try:
                shutil.rmtree(b, ignore_errors=True)
            except Exception:                                     # noqa: BLE001
                pass


async def shutdown_ingest(page, app) -> None:
    """把摄取对话框收掉（不关窗口 —— 收尾统一由 main 做）。
        English:
    Dismiss the ingestion dialog (do not close the window — cleanup is handled uniformly by main).
    """
    try:
        st = app._ingest_state
        if st.get('running'):
            st['cancel'] = True
        ui = st.get('ui') or {}
        if ui.get('cancel'):
            ui['cancel'](None)
    except Exception:                                             # noqa: BLE001
        pass
    await asyncio.sleep(0.5)


# ══════════════════════════════════════════════════════════════════════
async def main(page: ft.Page) -> None:
    report: dict = {}
    try:
        await test_logic(report)
        await test_gui(page, report)
        report['ok'] = all(i['ok'] for i in _ITEMS)
    except BaseException:                                         # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()[-1800:]
        report['ok'] = False
        print(report['fatal'])
    finally:
        report['items'] = _ITEMS
        (OUT / 'optimize_review_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        n_ok = sum(1 for i in _ITEMS if i['ok'])
        print(f'开卷优化验证：{n_ok}/{len(_ITEMS)}')
        await shutdown(page, code=0 if report.get('ok') else 1)


if __name__ == '__main__':
    ft.run(main)
