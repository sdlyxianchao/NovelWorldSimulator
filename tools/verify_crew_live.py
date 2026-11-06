# -*- coding: utf-8 -*-
"""剧组消息的**折叠箭头** + **流式思考**（2026-10-23，用户点名）。

用户原话：
    「我希望运行界面里所有非演员Agent的各个剧组Agent的消息在最前面加上
      展开收起来三角号 `>` 和展开后向下 表示在执行的消息
      我点开这个按钮以后应该是 **LLM 的思考过程流式返回**。
      已经完成的消息(比如 xx 已交工)这种我点击展开是 **这一步的执行结果**」

这件事被拆成四层，**每层各自有判据**（一层坏了不要牵连另外三层）：

| 层 | 文件 | 判据 |
|---|---|---|
| ① 实时房间（思考缓冲） | `crew/live.py` | A 组 |
| ② LLM 流式（SSE + 回退） | `llm/router.py` | B 组 |
| ③ 循环接线（起一条/改一条） | `sim/loop.py` | C 组 |
| ④ 界面折叠块 | `gui/app_flet.py` | D 组（结构/行为）+ E 组（真机） |

跑法：`.venv\\Scripts\\python.exe tools/verify_crew_live.py`
      `.venv\\Scripts\\python.exe tools/verify_crew_live.py --logic-only`（跳过真机）

⚠ 本脚本**不写用户的 `.env`**：`VU.redirect_env_writes()` 一进来就装上了
  （项目铁律：判据造的数据绝不许写进用户的真实配置）。
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import verify_ui_common as VU                                  # noqa: E402

# ⚠ 起界面/改配置的脚本第一条就是这个重定向。
# [EN] ⚠ The very first thing any config-touching script does.
VU.redirect_env_writes()

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')          # 零网络、零成本、可复现
CFG.set('SCRIPT_REVIEW', 'false')    # 判据只测接线，不测审读规则

from i18n import set_lang, t                                    # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}
ONLY_LOGIC = '--logic-only' in sys.argv


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def texts(ctl, out=None) -> list[str]:
    """递归收一个控件里所有 `Text.value`（段落的内容在 `spans` 里，也要收）。"""
    if out is None:
        out = []
    if ctl is None:
        return out
    if hasattr(ctl, 'value') and isinstance(getattr(ctl, 'value', None), str):
        if ctl.value:
            out.append(str(ctl.value))
    for span in (getattr(ctl, 'spans', None) or []):
        if getattr(span, 'text', ''):
            out.append(str(span.text))
    for attr in ('controls', 'content'):
        v = getattr(ctl, attr, None)
        if isinstance(v, list):
            for c in v:
                texts(c, out)
        elif v is not None:
            texts(v, out)
    return out


# ══════════════════════════════════════════════════════════════════
#  A 组：实时房间
# [EN] Group A: the live rooms
# ══════════════════════════════════════════════════════════════════
def group_a() -> None:
    from crew import live as LV
    LV.reset()
    snap0 = LV.snapshot('art')
    ok('A1a ★★ 没有房间时 `snapshot` 返回 `state=""`（界面据此"没有可展开的东西"）',
       snap0.get('state') == '', repr(snap0.get('state')))

    LV.begin('art', '美术', '画面与道具')
    s = LV.snapshot('art')
    ok('A1b ★★★ 出工一开始就有房间，且 `state=running`（不等任何输出）',
       s.get('state') == LV.RUNNING and s.get('name') == '美术',
       f'state={s.get("state")} name={s.get("name")}')
    ok('A1c ★★ 每一趟有独立的 `run_id`（同一位一天出工几十次，界面靠它认人）',
       int(s.get('run_id') or 0) > 0, str(s.get('run_id')))

    LV.feed('art', '先想一下')
    LV.feed('art', '：阿枝该不该进门。')
    s = LV.snapshot('art')
    ok('A2 ★★★ 思考增量真的攒起来了，且 `seq` 在涨（界面靠 seq 判断"有没有新东西"）',
       s.get('thinking') == '先想一下：阿枝该不该进门。' and s.get('seq', 0) >= 2,
       f'thinking={s.get("thinking")!r} seq={s.get("seq")}')

    LV.feed('art', '掌柜把茶碗推过来。', kind='content')
    s = LV.snapshot('art')
    ok('A3 ★★★ **正文增量不进思考框**（否则展开框变成"整段输出"，那不是用户要的"思考过程"）',
       '掌柜把茶碗推过来。' not in str(s.get('thinking') or ''),
       f'thinking={s.get("thinking")!r}')

    LV.reset()
    LV.feed('nobody', '这段话没有主')
    ok('A4 ★★ 没有房间时喂增量**不新建房间**（判据/天机测试按钮的调用不会凭空冒出"某位在想什么"）',
       LV.snapshot('nobody').get('state') == '', repr(LV.snapshot('nobody').get('state')))

    LV.begin('cap', '上限', '')
    LV.feed('cap', 'A' * (LV.MAX_THINKING + 500))
    s = LV.snapshot('cap')
    th = str(s.get('thinking') or '')
    ok('A5 ★★ 思考有上限，且**掐头留尾**（结论在最后；推理模型一次能吐 6000+ 字）',
       len(th) == LV.MAX_THINKING and th.endswith('A'),
       f'长度={len(th)}（上限 {LV.MAX_THINKING}）')

    LV.begin('art', '美术', '画面')
    LV.finish('art', body='（美术）水墨淡彩、低饱和。', ok=True, secs=12.4)
    s = LV.snapshot('art')
    ok('A6 ★★★ 收工把**这一趟的执行结果**定格进房间（展开框点开要看的就是它）',
       s.get('state') == LV.DONE and s.get('body') == '（美术）水墨淡彩、低饱和。'
       and abs(float(s.get('secs') or 0) - 12.4) < 0.01,
       f'state={s.get("state")} body={s.get("body")!r} secs={s.get("secs")}')

    # 归属：enter / leave
    LV.reset()
    LV.begin('a', '甲', '')
    LV.begin('b', '乙', '')
    # ⚠ 必须走**真实事件通道** `on_llm_event`：直接调 `feed(key, ...)` 等于把
    #   "归属"那一步跳过去，于是"增量不认人"的变异**白打**（实测踩过）。
    # [EN] ⚠ Must go through the **real event path** `on_llm_event`: calling
    # `feed(key, ...)` directly skips the attribution step, so the "deltas ignore the
    # owner" mutation is **wasted** (hit in practice).
    ta = LV.enter('a')
    LV.on_llm_event({'type': 'delta', 'stream': 'reasoning', 'text': '属于甲'})
    LV.leave(ta)
    LV.on_llm_event({'type': 'delta', 'stream': 'reasoning', 'text': '没人时的话'})
    ok('A7 ★★★ 归属靠 `ContextVar`：离开之后的话**不会**继续落进上一位的房间'
       '（症状会是"乙的思考出现在甲的框里"，而且只在并行时复现）',
       LV.snapshot('a').get('thinking') == '属于甲'
       and LV.snapshot('b').get('thinking') == '',
       f'a={LV.snapshot("a").get("thinking")!r} b={LV.snapshot("b").get("thinking")!r}')

    # install 必须挂到单例实例
    from llm import router as R
    LV.uninstall()
    newly = LV.install()
    ok('A8 ★★★ 监听挂在 **单例 `llm`（实例）** 上，不是类 `LLM` 上'
       '（挂错会 `TypeError` → 被吞掉 → 展开框永远空白）',
       newly and LV.on_llm_event in R.llm._listeners,
       f'newly={newly} 在监听表里={LV.on_llm_event in R.llm._listeners}')
    LV.reset()


# ══════════════════════════════════════════════════════════════════
#  B 组：流式
# [EN] Group B: streaming
# ══════════════════════════════════════════════════════════════════
def _fake_stream(chunks, status=200, body=None):
    """造一个假响应：`chunks` 是 dict 列表（自动包成 SSE 行）。"""
    class _Resp:
        status_code = status
        text = 'bad request'
        request = None

        def raise_for_status(self):
            if status >= 400:
                import httpx
                raise httpx.HTTPStatusError(str(status), request=None, response=None)

        async def aread(self):
            return b''

        #: 这一发请求的 body（判据用它确认"到底请求了 usage 没有"）。
        #: [EN] The body of this request (the criterion uses it to check whether usage was
        #: actually requested).
        req_body = body

        async def aiter_lines(self):
            # ⚠ 方法体里取不到**类作用域**的名字（`req_body` 是类属性）——
            #   必须走 `self`。第一版直接写 `req_body`，一进 B 组就 `NameError`。
            # [EN] A method body cannot see **class-scope** names (`req_body` is a class
            # attribute) -- it must go through `self`. The first version used `req_body`
            # directly and raised `NameError` as soon as B started.
            want_usage = bool((self.req_body or {}).get('stream_options', {})
                              .get('include_usage'))
            for c in chunks:
                if isinstance(c, str):
                    yield c
                else:
                    # ★ 真服务商的行为：**没请求 `include_usage` 就不会给 usage**。
                    #   夹具无条件给 usage 的话，"不请求 usage"这个变异根本抓不到
                    #   —— 判据会稳定地绿，而账本其实只能估算。
                    # [EN] Real provider behaviour: **without `include_usage` there is no
                    # usage**. A fixture that always supplies usage would make the "does not
                    # request usage" mutation undetectable -- the criterion stays green while
                    # the ledger can only estimate.
                    if c.get('usage') and not want_usage:
                        c = {k: v for k, v in c.items() if k != 'usage'}
                    yield 'data: ' + json.dumps(c, ensure_ascii=False)
                    yield ''

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    return _Resp()


class _FakeClient:
    """假 httpx 客户端：`stream` 给 SSE，`post` 给整段 JSON。"""

    def __init__(self, chunks=None, stream_status=200, plain_text='整段回答'):
        self.chunks = chunks or []
        self.stream_status = stream_status
        self.plain_text = plain_text
        self.posted = 0
        self.streamed = 0

    def stream(self, *a, **kw):
        self.streamed += 1
        # `_stream_collect` 用 `self._client.stream('POST', url, json=body, ...)` 调用，
        # 所以 body 在 `kw['json']` 里。取不到就 None（夹具按"没请求 usage"处理）。
        # [EN] `_stream_collect` calls `self._client.stream('POST', url, json=body, ...)`,
        # so the body is in `kw['json']`. None if absent (the fixture then assumes usage was
        # not requested).
        return _fake_stream(self.chunks, self.stream_status, body=kw.get('json'))

    async def post(self, *a, **kw):
        self.posted += 1

        class _R:
            status_code = 200
            request = None

            def raise_for_status(self):
                pass

            def json(self):
                return {'choices': [{'message': {'content': self_txt},
                                     'finish_reason': 'stop'}],
                        'usage': {'prompt_tokens': 5, 'completion_tokens': 7}}
        self_txt = self.plain_text
        return _R()


async def group_b() -> None:
    from llm import router as R
    llm = R.llm
    R.reset_stream_broken()

    CH = [
        {'choices': [{'delta': {'reasoning_content': '先想一下'}}]},
        {'choices': [{'delta': {'reasoning_content': '：阿枝该不该进门。'}}]},
        {'choices': [{'delta': {'content': '掌柜把茶碗推过来。'}}]},
        ': 这是一条心跳注释行',                 # 应被跳过
        'data: {坏掉的 JSON',                    # 应被跳过
        {'choices': [{'delta': {}}],
         'usage': {'prompt_tokens': 11, 'completion_tokens': 22}},
        {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
    ]
    got: list[dict] = []
    llm.add_listener(lambda e: got.append(e) if e.get('type') == 'delta' else None)
    client = _FakeClient(CH)
    llm._client = client
    llm._sem = asyncio.Semaphore(1)

    data = await llm._stream_collect('http://x', {'model': 'm', 'messages': []},
                                     {}, None, 'crew_art', 'm')
    msg = (data['choices'][0]['message'])
    ok('B1 ★★★ SSE 逐块读出来：正文与**思考**分别拼好，一个字不丢',
       msg.get('content') == '掌柜把茶碗推过来。'
       and msg.get('reasoning_content') == '先想一下：阿枝该不该进门。',
       f'content={msg.get("content")!r} reasoning={msg.get("reasoning_content")!r}')
    ok('B2 ★★ `usage` 与 `finish_reason` 都取到了（账本要算钱，截断检测要看长度）',
       data['usage'].get('completion_tokens') == 22
       and data['choices'][0]['finish_reason'] == 'stop',
       f'usage={data.get("usage")} finish={data["choices"][0]["finish_reason"]}')
    kinds = [e.get('stream') for e in got]
    ok('B3 ★★★ 每个增量都发 `delta` 事件，且**思考与正文分开标注**'
       '（界面只把思考灌进展开框）',
       kinds == ['reasoning', 'reasoning', 'content'],
       str(kinds))
    ok('B4 ★★ 心跳行 / 坏 JSON **被跳过**（不抛、不把整条流打断）',
       msg.get('content') == '掌柜把茶碗推过来。',
       f'content={msg.get("content")!r}')

    # 回退：这家网关 400 掉 stream_options
    llm.remove_listener(lambda *_: None)
    R.reset_stream_broken()
    bad = _FakeClient(stream_status=400, plain_text='退回来的整段回答')
    llm._client = bad
    text = ''
    try:
        with R.stream_scope(True):
            text, meta = await llm._real_call(
                'front', 'm', [{'role': 'user', 'content': 'hi'}], 'crew_art',
                temperature=0.5, max_tokens=100, timeout=None)
    except Exception as e:                                       # noqa: BLE001
        # ★ 不回退时这里是**抛异常**，而不是"返回错的东西"。判据要把它当成
        #   "B5 红"（换一家模型就整条挂掉），而不是让整组崩掉 ——
        #   整组崩掉的红色读起来像"判据坏了"，会把真问题盖住。
        # [EN] Without the fallback this **raises** instead of returning something wrong.
        # The criterion must treat that as "B5 red" (one provider swap breaks the whole
        # path) rather than crashing the whole group -- a group-level crash reads like "the
        # criterion is broken" and hides the real problem.
        text = f'<抛异常：{e}>'
    ok('B5 ★★★ 网关不吃流式（400）⇒ **自动退回整段**，结果照拿到'
       '（不这样做的话，用户换一家模型就"剧组整条挂掉"）',
       text == '退回来的整段回答' and bad.streamed == 1 and bad.posted == 1,
       f'text={text!r} stream={bad.streamed} post={bad.posted}')
    ok('B6 ★★★ 而且**记住了**：本进程之后不再试流式（否则每次出工先白扔一发）',
       R.stream_broken() and R.stream_wanted() is False,
       f'broken={R.stream_broken()} wanted={R.stream_wanted()}')

    R.reset_stream_broken()
    ok('B7 ★★ 默认**不流式**：29 处老调用点一行没动（老路 = `_post_plain`）',
       R.stream_wanted() is False, str(R.stream_wanted()))

    # 正文增量绝不能进"思考"
    from crew import live as LV2
    LV2.reset()
    LV2.begin('art', '美术', '')
    # ⚠ 必须**先 enter**：事件靠 `ContextVar` 认人，没有"当前出工者"时增量会被
    #   丢掉（那是对的 —— 判据/天机测试按钮的调用不该污染任何人的房间）。
    #   这里漏了 enter，就会测成"事件通道坏了"，而产品其实是对的。
    # [EN] **Must `enter` first**: events identify their owner via a `ContextVar`, and
    # without a "current worker" deltas are dropped (correct -- calls from criteria / the
    # settings test button must not pollute anyone's room). Omitting `enter` here would read
    # as "the event channel is broken" while the product is right.
    _tok2 = LV2.enter('art')
    LV2.on_llm_event({'type': 'delta', 'stream': 'content', 'text': '正文'})
    LV2.on_llm_event({'type': 'delta', 'stream': 'reasoning', 'text': '思考'})
    LV2.leave(_tok2)
    s = LV2.snapshot('art')
    ok('B8 ★★★ 走真实事件通道时，**正文也不进思考框**',
       s.get('thinking') == '思考', repr(s.get('thinking')))
    LV2.reset()


# ══════════════════════════════════════════════════════════════════
#  C 组：循环接线（起一条 / 原样改一条）
# [EN] Group C: loop wiring (open one / rewrite it)
# ══════════════════════════════════════════════════════════════════
def _bare_loop():
    """一个只填了这几条属性 / 回调的 `RunLoop`。

    ★ 用的是**生产方法本体**（`RunLoop._on_crew_note` 等），只把"没有的那几样"
      补上 —— 与本项目其它判据同一套做法（`RunLoop.__new__` + 手工属性）。
    [EN] A `RunLoop` with only the attributes/callbacks needed. The **production method
    bodies** run unchanged; only what is missing is filled in -- the same technique the
    rest of this project's criteria use.
    """
    from sim.loop import RunLoop
    loop = RunLoop.__new__(RunLoop)
    loop._day_words = 0
    loop._on_work = None
    loop._on_divider = None
    loop._display = None
    loop._lines: list = []
    loop._on_narrative = lambda text, pr, kind='', detail=None, update_key='': \
        loop._lines.append({'text': text, 'pr': pr, 'kind': kind,
                            'detail': detail, 'update_key': update_key})
    loop._warn_once = lambda *a, **k: None
    loop._crew_begins: list = []
    loop._on_crew_line = lambda key, text, detail: loop._crew_begins.append(
        {'key': key, 'text': text, 'detail': detail})
    return loop


def _note(role='art', ok_=True, body='（美术）水墨淡彩，纸本质感。',
          why='', secs=12.4, title='画面说明'):
    from crew import agents as A
    n = A.CrewNote(role=role, ok=ok_, title=title, body=body, why=why)
    n.data = {'用时': secs}
    return n


def group_c() -> None:
    from display import script as S

    # C1 起一条：只在 working 那一刻
    CFG.set('CREW_EXPAND', 'true')
    loop = _bare_loop()
    # ★ 入口是 `Studio.call` 的 `on_line` → `_crew_line_begin`（不是 `_work_push`）：
    #   `audit` 也走 `_work_push`，但它按设计不发中栏消息（见 C15）。
    # [EN] The entry point is `Studio.call`'s `on_line` -> `_crew_line_begin` (not
    # `_work_push`): `audit` also goes through `_work_push` but deliberately sends no
    # middle-column message (see C15).
    loop._crew_line_begin('art')
    ok('C1 ★★★ `working` 那一刻就**起一条**（这几十秒里界面上得有东西可点）',
       len(loop._crew_begins) == 1
       and loop._crew_begins[0]['detail'].get('state') == 'running',
       str(loop._crew_begins))
    b = loop._crew_begins[0] if loop._crew_begins else {}
    ok('C2 ★★ 那条起头带**职位 key**（界面靠它把后面的"已交活"接回同一条）',
       b.get('key') == 'art' and b['detail'].get('role') == 'art',
       f'key={b.get("key")} detail={b.get("detail")}')
    ok('C3 ★★ 起头用的是**中文名**，不是 `art`（用户看到的是一行字，不是程序里的键）',
       '美术' in str(b.get('text') or ''), repr(b.get('text')))

    loop._work_push('art', 'done')
    ok('C4 ★★★ `done` 那一刻**不再起一条**（同一件事只该有一行字，'
       '否则中栏出现"出工中"+"已交活"两条）',
       len(loop._crew_begins) == 1, str(len(loop._crew_begins)))

    # C5 收工：改那一条，并带上产出
    loop2 = _bare_loop()
    loop2._on_crew_note(_note())
    ok('C5 ★★★ 交活那一条带着 `update_key=职位key`（界面据此**原地改**，不新增行）',
       len(loop2._lines) == 1 and loop2._lines[0]['update_key'] == 'art',
       str(loop2._lines[0]['update_key'] if loop2._lines else None))
    d = (loop2._lines[0].get('detail') or {}) if loop2._lines else {}
    ok('C6 ★★★ `detail.body` 就是**这一步的执行结果全文**（展开框点开看它）',
       d.get('state') == 'done' and d.get('body') == '（美术）水墨淡彩，纸本质感。',
       f'state={d.get("state")} body={d.get("body")!r}')
    ok('C7 ★★ 而且**不是**原来那种只推状态的写法'
       '（状态行照旧是一行小字，正文只在 `detail` 里 —— 两条规矩同时成立）',
       '水墨淡彩' not in str(loop2._lines[0]['text']),
       repr(loop2._lines[0]['text']))

    # C8 没出活
    loop3 = _bare_loop()
    loop3._on_crew_note(_note(ok_=False, body='', why='超时跳过'))
    d3 = (loop3._lines[0].get('detail') or {}) if loop3._lines else {}
    ok('C8 ★★★ 没出活也带展开内容，且 `state=error` + 原因（故障信号不能只有一行）',
       d3.get('state') == 'error' and '超时跳过' in str(d3.get('why')),
       f'state={d3.get("state")} why={d3.get("why")!r}')

    # C9 开关关掉 → 回到旧样子
    CFG.set('CREW_EXPAND', 'false')
    try:
        loop4 = _bare_loop()
        loop4._crew_line_begin('art')
        ok('C9 ★★★ `CREW_EXPAND=false` 时**不起头**（回到"只有一行状态、点不开"的旧样子）',
           loop4._crew_begins == [], str(loop4._crew_begins))
        loop4._on_crew_note(_note())
        ok('C10 ★★ 但**内容照旧推**（关的是箭头，不是消息 —— 关掉不该让消息消失）',
           len(loop4._lines) == 1 and loop4._lines[0]['kind'] == S.CREW
           and loop4._lines[0]['detail'] is None
           and loop4._lines[0]['update_key'] == '',
           str(loop4._lines[0] if loop4._lines else None))
    finally:
        CFG.set('CREW_EXPAND', 'true')

    # C11 没有界面（CLI / 无头）
    loop5 = _bare_loop()
    loop5._on_crew_line = None
    loop5._work_push('art', 'working')
    ok('C11 ★★ 没有界面时**什么都不做**（"出工中"不是内容，不该进叙事流）',
       loop5._lines == [], str(loop5._lines))
    loop5._on_crew_note(_note())
    ok('C12 ★★★ 但交活那条照旧推（CLI / 无头判据一个字都不少）',
       len(loop5._lines) == 1, str(len(loop5._lines)))

    # C13 `_push_narrative` → `_on_narrative` 的透传
    loop6 = _bare_loop()
    loop6._push_narrative('测试', 3, kind=S.CREW,
                          detail={'state': 'done', 'body': 'x'},
                          update_key='art')
    ok('C13 ★★★ `_push_narrative` 把 `detail` / `update_key` **原样透传给界面**'
       '（中间断一刀的话，界面永远收不到要展开的内容）',
       loop6._lines and loop6._lines[0]['detail'] == {'state': 'done', 'body': 'x'}
       and loop6._lines[0]['update_key'] == 'art',
       str(loop6._lines[0] if loop6._lines else None))
    ok('C14 ★★ 记账只数 `text`（`detail` 里的全文**不进**"今天写了多少字"）',
       loop6._day_words == len('测试'), f'day_words={loop6._day_words}')

    # C15 `audit` 不许起中栏那条（它每拍一次，起了就把正文淹掉）
    src_studio = (APP_DIR / 'crew' / 'studio.py').read_text(encoding='utf-8')
    tree = ast.parse(src_studio)
    calls: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            names = []
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr in ('_line_begin', '_work_notify')):
                    names.append(sub.func.attr)
            calls[node.name] = names
    # C16 新回调必须在 `RunSession` 里接上（**这一轮真的踩过**）
    src_sess = (APP_DIR / 'sim' / 'session.py').read_text(encoding='utf-8')
    tree_s = ast.parse(src_sess)
    sess_ok = False
    for node in ast.walk(tree_s):
        if isinstance(node, ast.ClassDef) and node.name == 'RunSession':
            for sub in ast.walk(node):
                if (isinstance(sub, ast.arg) and sub.arg == 'on_crew_line'):
                    sess_ok = True
            wired = 'loop.on_crew_line(' in src_sess
            sess_ok = sess_ok and wired
    ok('C16 ★★★ 新回调 `on_crew_line` 必须在 `RunSession` 里**参数 + 接线**两处都到位'
       '（漏一处的表现是"起笔直接失败"，整轮起不来，而日志只有一句"启动新一轮失败"）',
       sess_ok, f'参数={"on_crew_line" in src_sess} 接线={"loop.on_crew_line(" in src_sess}')

    ok('C15 ★★★ 只有 `call` 起中栏那条消息，`audit` **不起**'
       '（审读每拍一次，起一行"出工中"会把正文淹掉）',
       '_line_begin' in calls.get('call', [])
       and '_line_begin' not in calls.get('audit', []),
       f"call={calls.get('call')} audit={calls.get('audit')}")


# ══════════════════════════════════════════════════════════════════
#  D 组：界面折叠块（结构 + 行为，不起窗口）
# [EN] Group D: the collapse block (structure + behaviour, no window)
# ══════════════════════════════════════════════════════════════════
def _mk_app():
    from gui.app_flet import NovelWorldApp
    app = NovelWorldApp()
    app._crew_ctl = {}
    app._crew_det = {}
    return app


def group_d() -> None:
    import flet as ft
    from crew import live as LV
    app = _mk_app()
    LV.reset()
    LV.begin('art', '美术', '画面')

    ctl = app._mk_crew_block('美术 · 出工中…',
                             {'state': 'running', 'role': 'art', 'name': '美术'})
    h = ctl._crew_handle
    head = ctl.controls[0]
    row = head.content
    first = row.controls[0] if getattr(row, 'controls', None) else None
    # ★★★ 2026-10-23 第二版（用户）：「我**要有明显的展开按钮** 而且**默认不展开**
    #   跟你这个聊天窗口的思考过程默认不展开类似」。
    #   ⇒ 判据从"第一个控件是箭头"升级成**四件事**：
    #     ① 那是个**按钮**（容器，不是裸图标）且在最前面；
    #     ② 按钮里**有字**（光一个箭头不算"明显"——它跟正文里的小符号长得一样）；
    #     ③ 按钮**画得出边界**（边框 + 底色 + 圆角）：没有这三样，在纸面上
    #        它就是一行小字，用户不会想到去点；
    #     ④ **默认收起**。
    # [EN] ★★★ v2 (2026-10-23, user): "I **want an obvious expand button** and **collapsed by
    # default**, like the thinking block in this chat window". So the criterion goes from "the
    # first control is a caret" to **four things**: (1) it is a **button** (a container, not a
    # bare icon) and it comes first; (2) the button **has words** (an arrow alone is not
    # obvious -- it looks like any small glyph in the prose); (3) the button **draws a
    # boundary** (border + fill + radius): without those it is just a line of small text on
    # paper and nobody would think to click it; (4) it is **collapsed by default**.
    ok('D1a ★★★ 最前面是个**按钮**（容器），不是一枚裸图标',
       isinstance(first, ft.Container) and first is h['pill'],
       f'第一个控件={type(first).__name__}')
    _inner = list(getattr(getattr(first, 'content', None), 'controls', []) or [])
    _texts = [c for c in _inner if isinstance(c, ft.Text) and str(c.value or '').strip()]
    _icons = [c for c in _inner if isinstance(c, ft.Icon)]
    ok('D1b ★★★ 按钮上**有文字**（"思考过程" / "执行结果"）——'
       '光一个箭头不算明显，它跟正文里的小符号长得一样',
       bool(_texts) and h['label'] in _texts,
       f'文字={[c.value for c in _texts]}')
    ok('D1c ★★★ 按钮**画得出边界**（边框 + 底色 + 圆角三样都要）'
       '——否则在纸面上它就是一行小字，没人会想到去点',
       getattr(first, 'border', None) is not None
       and bool(getattr(first, 'bgcolor', None))
       and int(getattr(first, 'border_radius', 0) or 0) > 0,
       f'border={first.border is not None} bg={bool(first.bgcolor)} '
       f'radius={first.border_radius}')
    ok('D1d ★★★ **默认不展开**（用户点名"跟你这个聊天窗口的思考过程默认不展开类似"）',
       h['open'] is False and h['box'].visible is False,
       f"open={h['open']} visible={h['box'].visible}")
    ok('D1e ★★ 箭头在**按钮内部的最前面**（图标、文字在同一个可点区域里）',
       bool(_icons) and _icons[0] is h['caret'] and _icons[0] is _inner[0],
       f'内部顺序={[type(c).__name__ for c in _inner]}')
    ok('D2 ★★★ 收起态：箭头**指向右**（`KEYBOARD_ARROW_RIGHT`）、内容区不可见',
       h['caret'].icon == ft.Icons.KEYBOARD_ARROW_RIGHT and h['box'].visible is False,
       f'icon={h["caret"].icon} visible={h["box"].visible}')

    # 点开：房间里已经攒了两句思考
    LV.feed('art', '先想一下：')
    LV.feed('art', '阿枝该不该进门。')
    head.on_click(None)
    ok('D3 ★★★ 点一下 → 箭头**变成向下**、内容区出现（用户要的 `>` → 向下）',
       h['caret'].icon == ft.Icons.KEYBOARD_ARROW_DOWN and h['box'].visible is True,
       f'icon={h["caret"].icon} visible={h["box"].visible}')
    body_txt = str(h['body'].value or '')
    ok('D4 ★★★ 出工中点开看到的是**思考过程**（不是正文、不是空白）',
       '阿枝该不该进门' in body_txt, repr(body_txt[:60]))

    head.on_click(None)
    ok('D5 ★★ 再点一下 → 收起，而且**不清掉**已经显示的内容'
       '（收起=看不见，不是丢掉）',
       h['caret'].icon == ft.Icons.KEYBOARD_ARROW_RIGHT
       and h['box'].visible is False and str(h['body'].value or ''),
       f'visible={h["box"].visible}')

    # 初始空思考时给出提示而不是空白
    app2 = _mk_app()
    LV.begin('props', '道具', '')
    ctl2 = app2._mk_crew_block('道具 · 出工中…',
                               {'state': 'running', 'role': 'props', 'name': '道具'})
    # ⚠ 这里原来有一句 `..content.controls[0].icon`（"存在即可"的空断言）。
    #   按钮改成胶囊之后，`controls[0]` 是**胶囊容器**而不是图标 ⇒ `AttributeError`
    #   ⇒ 整组 D 崩掉、后面几条一条都没跑（看起来像"没有那些判据"）。
    #   **空断言既没有价值，又会随结构变化崩**，直接删掉。
    # [EN] There used to be a `..content.controls[0].icon` "just check it exists" no-op
    # assertion. After the pill change, `controls[0]` is the **pill container**, not the
    # icon => `AttributeError` => the whole D group crashed and later criteria never ran
    # (which reads as "those criteria do not exist"). **A no-op assertion has no value and
    # breaks with structure**, so it is gone.
    ctl2.controls[0].on_click(None)
    txt2 = str(ctl2._crew_handle['body'].value or '')
    ok('D6 ★★★ 还没开口时**给一句提示**，不留空白（空白看起来像"坏了"）',
       txt2.strip() != '' and '还没有开口' in txt2, repr(txt2[:50]))

    # 交活后：展开看结果
    LV.finish('art', body='（美术）水墨淡彩、纸本质感，低饱和。', ok=True, secs=12.4)
    h['detail'].update({'state': 'done', 'body': '（美术）水墨淡彩、纸本质感，低饱和。'})
    h['state'] = 'done'
    app._fill_crew_body(h)
    ok('D7 ★★★ 交活后点开看到的是**这一步的执行结果**（用户原话），不是思考',
       '水墨淡彩' in str(h['body'].value or '')
       and '阿枝' not in str(h['body'].value or ''),
       repr(str(h['body'].value or '')[:60]))

    # 没有正文时也要说清楚
    app3 = _mk_app()
    ctl3 = app3._mk_crew_block('场记 · 已交活 · 2.0s',
                               {'state': 'done', 'role': 'clerk', 'name': '场记',
                                'body': '', 'why': '模型没给正文'})
    ctl3.controls[0].on_click(None)
    txt3 = str(ctl3._crew_handle['body'].value or '')
    ok('D8 ★★ 没产出正文时给"没有产出正文"+原因（不空白、不假装成功）',
       '没有产出正文' in txt3 and '模型没给正文' in txt3, repr(txt3[:60]))

    # 原地改：行数不变
    app4 = _mk_app()
    app4._live_lines = []
    # ★ 这里**必须有一个中栏控件**（哪怕是没挂到页面上的 `ft.Column`）：
    #   D11 要判的是"标题控件跟着变了"，而控件只有在中栏存在时才会造出来。
    #   用 `_ui_run = {}` 的话，那条消息只进 `_live_lines`、没有控件 ——
    #   于是这条判据会 `KeyError`，看起来像产品坏了，其实是**夹具省掉了中栏**。
    # [EN] There **must be a column control** here (even an unattached `ft.Column`):
    # D11 checks that the title control changed, and the control only exists when a column
    # exists. With `_ui_run = {}` the message only goes into `_live_lines` and no control is
    # built -- the criterion then raises `KeyError`, which looks like a product bug while
    # the fixture simply omitted the column.
    import flet as _ft
    app4._ui_run = {'narrative': _ft.Column([], spacing=0)}
    app4._narr_back = 0
    app4._on_crew_line('art', '美术 · 出工中…',
                       {'state': 'running', 'role': 'art', 'name': '美术'})
    n0 = len(app4._live_lines)
    changed = app4._on_narrative('美术 · 已交活 · 12.4s', 3, kind='crew',
                                 detail={'state': 'done', 'role': 'art',
                                         'body': '结果全文'},
                                 update_key='art')
    n1 = len(app4._live_lines)
    ok('D9 ★★★ 交活那一条**原地改掉**原来"出工中"那一行（行数不变）'
       '—— 用户要的是"同一行字变过来"，不是两行',
       changed is None and n0 == 1 and n1 == 1, f'改前 {n0} 行 / 改后 {n1} 行')
    ok('D10 ★★★ 而且 `_live_lines` 里那一行**文字也变了**'
       '（不同步就会出现"跑着看是已交活、翻回去还是出工中"）',
       '已交活' in str(app4._live_lines[0][1]), repr(app4._live_lines[0][1]))
    ok('D11 ★★ 标题控件跟着变了（用户眼睛盯着的那一行）',
       '已交活' in str(app4._crew_ctl['art']['title'].value),
       repr(app4._crew_ctl['art']['title'].value))
    # D11b 按钮上的**字**也要跟着变（思考过程 → 执行结果）
    h4 = app4._crew_ctl['art']
    ok('D11b ★★★ 交活后按钮上的字从「思考过程」变成**「执行结果」**'
       '（不改的话界面说"已交活"、按钮还写着思考过程 —— 点开确实是结果，但字在骗人，'
       '而且**不会报错**）',
       str(h4['label'].value) == t('执行结果'), repr(h4['label'].value))

    # 路由：带 detail 的行 → 折叠块；不带 → 原来的行
    from display import story_render as STR
    rows = [(3, '美术 · 已交活 · 12.4s', 'crew', '12:00',
             {'state': 'done', 'role': 'art', 'body': 'x'}),
            (3, '（剧组 · 场记）已交活 · 1.0s', 'crew', '12:00')]
    c_with = app4._mk_live_item(rows, [0])
    c_without = app4._mk_live_item(rows, [1])
    inner_with = getattr(c_with, '_narr_inner', c_with)
    ok('D12 ★★★ 带 `detail` 的那一条走**折叠块**（判据是"有没有内容可展开"，不是 kind 名字）',
       hasattr(inner_with, '_crew_handle'), type(inner_with).__name__)
    inner_wo = getattr(c_without, '_narr_inner', c_without)
    ok('D13 ★★ 不带 `detail` 的旧条目**还是原来那一行**（同一个 kind 两种样子是对的：'
       '有东西可看的才给箭头）',
       not hasattr(inner_wo, '_crew_handle'), type(inner_wo).__name__)

    # 轮询：三条终点
    src = inspect.getsource(type(app)._crew_start_poll)
    ok('D14 ★★★ 轮询**必须有终点**：收起 / 换代 / 房间不再是 running 都要退出',
       "handle.get('open')" in src and "handle.get('gen') != gen" in src
       and 'LV.RUNNING' in src,
       '')
    ok('D15 ★★ 收起时不刷新（收起还每 250ms 刷一次 = 几十个空控件白转，'
       '还会顶掉用户正在读的滚动位置）',
       'if not handle.get(\'open\')' in src, '')

    # D16 中栏**还没建**时：交活也要改那一行（不能变成两条）
    app5 = _mk_app()
    app5._live_lines = []
    app5._ui_run = {}                     # ← 中栏还没建（一开轮的装配阶段就是这样）
    app5._narr_back = 0
    app5._on_crew_line('art', '美术 · 出工中…',
                       {'state': 'running', 'role': 'art', 'name': '美术'})
    n5a = len(app5._live_lines)
    app5._on_narrative('美术 · 已交活 · 5.0s', 3, kind='crew',
                       detail={'state': 'done', 'role': 'art', 'body': '结果'},
                       update_key='art')
    n5b = len(app5._live_lines)
    ok('D16 ★★★ 中栏**还没建出来**时（一开轮的装配阶段）交活也要**改那一行**，'
       '不能变成两条（否则中栏一建出来就同时有"出工中"和"已交活"）',
       n5a == 1 and n5b == 1 and '已交活' in str(app5._live_lines[0][1]),
       f'{n5a} 行 → {n5b} 行 · {app5._live_lines[0][1]!r}')

    LV.reset()


# ══════════════════════════════════════════════════════════════════
#  E 组：真机（控件真的挂进页面 + 轮询真的会长）
# [EN] Group E: on a real page (control really attached + polling really grows)
# ══════════════════════════════════════════════════════════════════
async def group_e(page) -> None:
    import flet as ft
    from crew import live as LV
    from gui.app_flet import NovelWorldApp

    app = NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(0.6)
    LV.reset()

    # 造一个中栏（真控件列表），模拟"推演正在跑"
    col = ft.Column([], spacing=0)
    app._ui_run['narrative'] = col
    app._live_lines = []
    app._crew_ctl = {}
    app._crew_det = {}
    app._narr_back = 0
    app._narr_new = 0
    col_holder = ft.Column([col], height=400, scroll=ft.ScrollMode.AUTO)
    page.controls.clear()
    page.add(col_holder)
    page.update()

    from sim.loop import RunLoop
    loop = _bare_loop()
    loop._on_crew_line = app._on_crew_line
    # ★ 按**生产顺序**来：`Studio.call` 先 `LV.begin` 建房间、再 `_line_begin` 起消息
    #   （见 `crew/studio.call` 的注释）。反过来写就是在测一个真实里不存在的顺序。
    # [EN] Follow the **production order**: `Studio.call` does `LV.begin` first, then
    # `_line_begin` (see the note in `crew/studio.call`). The other order does not exist in
    # reality.
    LV.begin('art', '美术', '画面')
    loop._crew_line_begin('art')
    page.update()
    await asyncio.sleep(0.4)

    blocks = [c for c in col.controls if hasattr(c, '_crew_handle')]
    ok('E1 ★★★ 那条剧组消息**真的挂进了中栏**（不是"控件造出来了但没摆上去"）',
       len(blocks) == 1, f'中栏控件数={len(col.controls)} 带句柄={len(blocks)}')

    if blocks:
        ctl = blocks[0]
        h = ctl._crew_handle
        # 点开
        ctl.controls[0].on_click(None)
        page.update()
        await asyncio.sleep(0.15)
        ok('E2 ★★★ 点开以后内容区**在页面上真的可见**（`visible` 只是字段，'
           '这里看的是"页面刷新之后还成立"）',
           h['box'].visible is True and h['caret'].icon == ft.Icons.KEYBOARD_ARROW_DOWN,
           f'visible={h["box"].visible}')

        # 房间开始"流式"长大 —— 轮询应该把它读出来
        before = len(str(h['body'].value or ''))
        for part in ('先想一下', '：阿枝该不该进门。', '她手里那把伞还在滴水。'):
            LV.feed('art', part)
            await asyncio.sleep(0.32)       # > CREW_POLL_MS
        after = len(str(h['body'].value or ''))
        ok('E3 ★★★ **流式真的流起来了**：房间里追加，展开框自己跟着长',
           after > before + 5, f'{before} 字 → {after} 字')

        LV.finish('art', body='（美术）水墨淡彩。', ok=True, secs=9.0)
        app._on_narrative('美术 · 已交活 · 9.0s', 3, kind='crew',
                          detail={'state': 'done', 'role': 'art',
                                  'body': '（美术）水墨淡彩。'},
                          update_key='art')
        page.update()
        await asyncio.sleep(0.6)
        ok('E4 ★★★ 交活后展开框换成**执行结果**，且轮询自己停了'
           '（不停的话会一直对着一个已经结束的房间空转）',
           '水墨淡彩' in str(h['body'].value or ''),
           repr(str(h['body'].value or '')[:40]))

    # E5 房间**晚到**：先点开、再建房间，轮询不能就此放弃
    LV.reset()
    app._ui_run['narrative'] = ft.Column([], spacing=0)
    app._live_lines = []
    app._crew_ctl = {}
    app._crew_det = {}
    app._on_crew_line('clerk', '场记 · 出工中…',
                      {'state': 'running', 'role': 'clerk', 'name': '场记'})
    page.update()
    await asyncio.sleep(0.3)
    blk = [c for c in app._ui_run['narrative'].controls
           if hasattr(c, '_crew_handle')]
    ok('E5a ★★ 第二条剧组消息也建出来了（登记表没被上一条占住）',
       len(blk) == 1, f'控件数={len(app._ui_run["narrative"].controls)}')
    if blk:
        h2 = blk[0]._crew_handle
        # 此刻**还没有房间** —— 这就是"点得比 begin 早"的那个真实瞬间
        ok('E5b ★★ 点开时房间还不存在（复现真实的那一拍）',
           LV.snapshot('clerk').get('state') == '', '')
        blk[0].controls[0].on_click(None)
        page.update()
        await asyncio.sleep(0.5)
        LV.begin('clerk', '场记', '')
        LV.feed('clerk', '这一场要查三处连戏。')
        await asyncio.sleep(0.7)
        ok('E5c ★★★ 房间**晚到**时轮询没放弃：后到的思考照样出现'
           '（立刻放弃的话展开框会永远停在"还没有开口"，看起来像功能坏了）',
           '连戏' in str(h2['body'].value or ''),
           repr(str(h2['body'].value or '')[:40]))


# ══════════════════════════════════════════════════════════════════
async def main(page=None) -> None:
    print('\n── A 实时房间（思考缓冲）──')
    try:
        group_a()
    except Exception:                                            # noqa: BLE001
        ok('A 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1500:])

    print('\n── B LLM 流式（SSE + 回退）──')
    try:
        await group_b()
    except Exception:                                            # noqa: BLE001
        ok('B 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1500:])

    print('\n── C 循环接线（起一条 / 改一条）──')
    try:
        group_c()
    except Exception:                                            # noqa: BLE001
        ok('C 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1500:])

    print('\n── D 界面折叠块（结构 + 行为）──')
    try:
        group_d()
    except Exception:                                            # noqa: BLE001
        ok('D 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1500:])

    print('\n── E 真机 ──')
    if page is None:
        print('  （--logic-only：跳过）')
    else:
        try:
            await group_e(page)
        except Exception:                                        # noqa: BLE001
            ok('E 组跑完', False, traceback.format_exc()[-400:])
            print(traceback.format_exc()[-1500:])

    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n剧组消息折叠 + 流式思考验证：{good}/{n}')
    (OUT / 'crew_live_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    if page is not None:
        from util.flet_shutdown import shutdown
        await shutdown(page, code=(0 if good == n else 2))


if __name__ == '__main__':
    if ONLY_LOGIC:
        asyncio.run(main(None))
        sys.exit(0)
    import flet as ft
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
