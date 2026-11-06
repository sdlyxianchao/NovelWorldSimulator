# -*- coding: utf-8 -*-
"""验证：**某个模型服务没钱了 ⇒ 明确报错 + 推演暂停 + 点继续会重试**（2026-10-25）。

用户原话
--------
    「我配置了好几个 LLM 服务，我想如果哪个 LLM 没钱了，是否有办法给出明确的报信息，
      且当前推演暂停，如果没充值点继续，还报这个错误。充值之后点继续就可以继续推演。」

为什么这不是"再加一个 except"
----------------------------
原来的行为是：402 落进 `except (httpx.HTTPStatusError, …)` ⇒ **退避重试 3 次**
（1s→2s→4s）⇒ 抛 `RuntimeError("LLM 调用失败（已重试 3 次）: Client error '402 …'")`。
两个毛病：
  · 那句话**没有一个字说要充值**，"重试"对欠费**永远不会成功**；
  · 上层 `llm.replies.ask()` 与一路上十几个 `except Exception` 会把它降级成
    "这一次没拿到东西"，`Agent.decide` 再降成"这一拍什么都没做" ——
    屏幕上就是满屏"没动，也没出声"，也就是**哑掉**。

所以这条通道的设计是「**异常 + 登记表**」两件套：
  · `OutOfCredit` 异常 —— 不重试、带服务端原话，能让调用栈快速短路；
  · `llm.credit` 登记表 —— **唯一事实来源**。主循环靠它暂停、状态条靠它写文案。
    哪怕某处 `except Exception` 把异常吞了，**账还在**，主循环下一轮照样停。

判据分组（一条判据守一道闸）
--------------------------
  A **口径**：什么才算"没钱"。核心是**别把限流当欠费**（那会让一个还能用的服务
     被误判、还让用户去充一笔不需要充的钱）
  B **不重试 / 同一家 fail-fast**：欠费重试一万次也不会成功；而整理稿一天 18 段 ×
     每段一套 Reflexion，不 fail-fast 就是几千次注定失败的请求
  C **暂停与继续**：停要停得住、说得清；点「继续」要**真的重试**（清登记），
     没充就再停一次再报一次（正是用户要的语义）
  D **状态条**：已暂停那一行要写清是谁没钱；而**没有欠费时不许挂这句**

跑法：.venv\\Scripts\\python.exe tools/verify_llm_credit.py
产出：assets/screenshots/llm_credit_report.json

English:
Verify that **a model provider running out of money gives a clear message, pauses the run, and
resuming retries** (2026-10-25).
The user's words: "I've configured several LLM services. If one runs out of money, can it give a
clear message and pause the simulation? If I haven't topped up and click resume, it should report
the same error again; after topping up, clicking resume continues."
Before: 402 fell into the retry branch (1s -> 2s -> 4s), then raised
`RuntimeError("LLM 调用失败（已重试 3 次）: Client error '402 …'")` -- a sentence that **never
mentions topping up**, and retrying billing **can never succeed**. Worse, `ask()` and a dozen
`except Exception` degrade it to "this call got nothing", then `Agent.decide` to "this beat did
nothing": the screen goes silent.
So this channel is **exception + registry**: `OutOfCredit` (no retry, carries the server's own
words, short-circuits fast) plus the `llm.credit` registry (**single source of truth** -- the loop
pauses on it, the status bar writes it; even if something swallows the exception, the ledger
remains and the loop still stops next iteration).
Groups: A what counts as out-of-money (above all, **do not mistake rate limiting for billing**) /
B no retry + fail-fast per provider / C pause and resume semantics / D the status bar line.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

import httpx                                                  # noqa: E402

from i18n import t                                            # noqa: E402
from llm import credit as CREDIT                              # noqa: E402
from llm.router import LLM                                    # noqa: E402

OUT = APP / 'assets' / 'screenshots'
REPORT = OUT / 'llm_credit_report.json'
_rows: list[dict] = []


def ok(name: str, cond, detail='') -> bool:
    _rows.append({'判据': name, '通过': bool(cond), '实测': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''))
    return bool(cond)


# ── HTTP 替身（零网络、零花费）────────────────────────────────
class _Resp:
    def __init__(self, status: int, text: str):
        self.status_code = status
        self.text = text
        self.request = httpx.Request('POST', 'https://example.invalid/v1/chat/completions')

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return {}

    def raise_for_status(self) -> None:
        if not self.is_success:
            raise httpx.HTTPStatusError(f'Client error {self.status_code}',
                                        request=self.request, response=self)


class _Client:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    async def post(self, *a, **kw):
        self.calls += 1
        st, tx = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        return _Resp(st, tx)


def _llm(replies) -> tuple[LLM, _Client]:
    obj = LLM()
    cli = _Client(replies)
    obj._client = cli                 # type: ignore[assignment]
    obj._sem = asyncio.Semaphore(4)
    return obj, cli


async def _call(obj: LLM):
    return await obj._real_call(
        'daily', 'deepseek-flash', [{'role': 'user', 'content': '喂'}],
        'probe', 0.2, 64, 5.0, res=None, caps={})


# ── A 口径 ──────────────────────────────────────────────────────
def a_scope():
    print('\n【A】什么才算"没钱"')
    ok('A1 ★★★ 402 一律算（正文是空的也算）—— 这个码的语义就是 Payment Required，'
       '没有第二种解释', CREDIT.detect(402, ''), '')

    # ⚠ **这一条是整组最要紧的**：把它判错，一个还能用的服务会被误判成没钱，
    #   而用户会跑去充一笔根本不需要充的钱。
    # [EN] ⚠ **The most important one in this group**: getting it wrong marks a working service as
    # [EN] broke, and the user goes and tops up for nothing.
    ok('A2 ★★★ **429 纯限流不算欠费**（429 最常见的含义是"太快了，等会儿"）',
       not CREDIT.detect(429, 'Rate limit reached for requests in 1s'), '')
    ok('A3 ★★★ 成对：429 带 `insufficient_quota` **要算**（OpenAI 的欠费就发 429）',
       CREDIT.detect(429, '{"error":{"code":"insufficient_quota"}}'), '')
    ok('A4 ★★★ 403 是"没权限"不算；403 带欠费字样才算（这两件事下一步完全不同：'
       '一个去改 Key 授权，一个去充钱）',
       (not CREDIT.detect(403, 'this key has no access to model x'))
       and CREDIT.detect(403, '{"code":"Arrearage","message":"account is in good standing"}'),
       '')
    ok('A5 ★★ 400 带中文「已欠费，请充值」要算（国内几家就是这么回的）',
       CREDIT.detect(400, '您的账户已欠费，请充值后重试'), '')
    ok('A6 ★★ 5xx **不算**（对方自己出故障时停下来等它恢复是错的；'
       '而且那时"余额不足"这几个字多半是网关的模板文案）',
       not CREDIT.detect(500, '余额不足'), '')
    ok('A7 ★★★ 标记表里**不许有裸 `quota`** —— 加进去就等于把 429 限流全判成欠费',
       'quota' not in {m.strip().lower() for m in CREDIT.OUT_OF_CREDIT_MARKERS},
       '')


# ── B 不重试 / fail-fast ────────────────────────────────────────
def b_retry():
    print('\n【B】不重试，同一家不再发网络')
    from config import CFG
    retries = int(CFG.i('LLM_MAX_RETRIES'))
    ok('B0 ★★ 前提：重试次数不是 0（否则下面"只发一发"证明不了任何事）',
       retries >= 1, f'LLM_MAX_RETRIES={retries}')

    CREDIT.clear()
    CREDIT.forget_callbacks()
    obj, cli = _llm([(402, '{"error":{"message":"Insufficient Balance"}}')])
    # ⚠ **必须接住任意异常**：如果产品走了老路，抛出来的是 `RuntimeError`，
    #   只写 `except OutOfCredit` 会让它一路冲出这一组 —— 那样报的是
    #   "b_retry 整组没跑完"，而不是"B1 红了"（反例法第一版就是这么漏判的）。
    # [EN] ⚠ **Catch any exception**: if the product takes the old path it raises `RuntimeError`,
    # [EN] and only catching `OutOfCredit` lets it escape the whole group -- reporting
    # [EN] "b_retry did not finish" instead of "B1 red" (the first counterexample run missed it that way).
    got = None
    try:
        asyncio.run(_call(obj))
        got = '没抛异常'
    except Exception as e:                                   # noqa: BLE001
        got = e
    ok('B1 ★★★ 402 ⇒ **只发一发**（对欠费重试永远不会成功，只会让日志和耗时难看）',
       isinstance(got, CREDIT.OutOfCredit) and cli.calls == 1,
       f'请求数={cli.calls}（重试上限 {retries} ⇒ 走老路会是 {retries + 1}）'
       f' · 抛的是 {type(got).__name__}')
    ok('B2 ★★★ 抛出来的异常**带着服务端原话**（是不是真欠费，用户看一眼那句话就能判断）',
       isinstance(got, CREDIT.OutOfCredit)
       and 'Insufficient Balance' in got.detail, getattr(got, 'detail', ''))
    # ⚠ 这条单独立：异常抛得出去 ≠ 登记表里记上了。**不登记 ⇒ 主循环永远不知道**
    #   （它读的是登记表，不是异常），于是"抛了、被吞了、没人停"。
    # [EN] ⚠ Separate criterion: raising the exception is **not** the same as recording it. Without
    # [EN] the record the main loop never knows (it reads the registry, not the exception) -- so it
    # [EN] "raises, gets swallowed, nobody stops".
    ok('B6 ★★★ 而且**真的登记了**（主循环读的是登记表，不是异常 —— 只抛不记等于没人会停）',
       CREDIT.first() is not None and CREDIT.first().status == 402,
       f'{CREDIT.first().summary() if CREDIT.first() else "登记表是空的"}')

    before = cli.calls
    try:
        asyncio.run(_call(obj))
    except CREDIT.OutOfCredit:
        pass
    ok('B3 ★★★ 同一家再来一发 ⇒ **不发网络**（整理稿一天 18 段 × 每段一套 Reflexion，'
       '不 fail-fast 就是几千次注定失败的请求，每次还要等超时）',
       cli.calls == before, f'新增请求={cli.calls - before}')

    # 成对：限流那条老路一个字都不许变（否则"不重试"就把 429 的退避一起砍了）
    CREDIT.clear()
    obj2, cli2 = _llm([(429, 'Rate limit reached for requests')])
    try:
        asyncio.run(_call(obj2))
    except CREDIT.OutOfCredit:
        pass
    except Exception:                                        # noqa: BLE001
        pass
    ok('B4 ★★★ 成对：429 纯限流**照旧重试到上限**（老行为没被"不重试"顺手砍掉）',
       cli2.calls == retries + 1, f'请求数={cli2.calls}')

    CREDIT.clear()
    from llm.router import llm as GLOBAL_LLM
    from llm.replies import ask
    seen_chat = {'n': 0}

    async def _fake_chat(*a, **kw):
        seen_chat['n'] += 1
        raise CREDIT.OutOfCredit(provider='x', label='X 家', status=402, detail='no money')

    # ⚠ 必须打在**模块里那个单例**上：`ask()` 用的是 `from llm.router import llm`，
    #   另造一个 `LLM()` 再给它挂 `chat` 是打不中的（第一版就这么白跑了一次，
    #   报"chat 调了 0 次"，看起来像产品没抛）。
    # [EN] ⚠ Must patch the **module-level singleton**: `ask()` uses `from llm.router import llm`,
    # [EN] so attaching `chat` to a fresh `LLM()` hits nothing (the first version failed exactly
    # [EN] that way: "chat called 0 times", which looked like the product not raising).
    _old_chat = GLOBAL_LLM.chat
    GLOBAL_LLM.chat = _fake_chat                                 # type: ignore[assignment]
    try:
        asyncio.run(ask('daily', [{'role': 'user', 'content': '喂'}], purpose='probe'))
        re_raised = False
    except CREDIT.OutOfCredit:
        re_raised = True
    finally:
        GLOBAL_LLM.chat = _old_chat                              # type: ignore[assignment]
    ok('B5 ★★★ `ask()` **原样再抛**，不许降级成"这一次没拿到东西"'
       '（降级了就会一路哑掉：这一拍什么都没做，用户永远看不到"去充值"）',
       re_raised and seen_chat['n'] == 1, f'chat 调了 {seen_chat["n"]} 次')


# ── C 暂停 / 继续 ───────────────────────────────────────────────
def _loop_fixture():
    from sim.loop import RunLoop
    loop = RunLoop.__new__(RunLoop)
    loop._paused = False
    loop._running = True
    loop._stop_requested = False
    loop._credit_paused = False
    # ⚠ `resume()` 会摸 `self.director._pending_intervention` 与 `_ask_pending`：
    #   夹具得给空壳，否则崩在"确认导演介入"，看起来像欠费功能坏了。
    loop.director = type('_D', (), {'_pending_intervention': None})()
    loop._ask_pending = None
    pushed: list[str] = []
    loop._push_narrative = (lambda text, *a, **k: pushed.append(text))   # type: ignore
    loop._notes = pushed
    return loop


def c_pause_resume():
    print('\n【C】暂停与继续')
    CREDIT.clear()
    CREDIT.forget_callbacks()
    loop = _loop_fixture()
    loop._credit_cb = loop._on_credit_block
    CREDIT.on_block(loop._credit_cb)
    # ⚠ 计数回调必须**在第一条登记之前**挂上：`note()` 只在"头一回发现这一家"时发回调，
    #   挂晚了就一次都收不到（第一版写成挂在后面，C5 报"回调 0 次"，看起来像产品没发）。
    # [EN] ⚠ The counting callback must be registered **before the first note**: `note()` only fires
    # [EN] when a provider is first found broke, so registering later receives nothing (the first
    # [EN] version registered late and C5 reported "0 callbacks", looking like the product did not fire).
    hits = {'n': 0}
    CREDIT.on_block(lambda _e: hits.__setitem__('n', hits['n'] + 1))

    CREDIT.note(CREDIT.OutOfCredit(provider='deepseek', label='DeepSeek 官方',
                                   model='deepseek-flash', purpose='crew_day_novel',
                                   status=402, detail='Insufficient Balance'))
    # ⚠ 真机上这条回调是从一次真实请求里触发的；`note()` 是同一入口。
    ok('C1 ★★★ 一登记就**立刻暂停**（不等这一拍跑完）—— 否则那 12 个人会各撞一次、'
       '各降级一次，屏幕上是一排"没动，也没出声"', loop.paused, '')

    text = '\n'.join(loop._notes)
    ok('C2 ★★★ 而且**说清是哪一家**（"某个模型没钱了"这种话没法让人去充值）',
       'DeepSeek 官方' in text, text.splitlines()[0][:40] if text else '')
    ok('C3 ★★★ 还说清了**怎么办**（充值 → 点继续 → 从停下的地方接着跑）',
       '充值' in text and '继续' in text, '')
    ok('C4 ★★ 带上**服务端原话**（用户要靠它判断"这真的是欠费吗"）',
       'Insufficient Balance' in text, '')

    # 同一家连撞 5 次只回调 1 次（否则整理稿那 18 段会刷出一堵墙）。
    # ⚠ 用**自己的计数回调**量，别拿主循环推了几条来量：`_on_credit_block` 自己是幂等的，
    #   回调被调 5 次它也只推 1 条 ⇒ 用条数判会**永远绿**（反例法第一版就是这么漏的）。
    # [EN] ⚠ Measure with **own counting callback**, not the loop's pushed lines: `_on_credit_block`
    # [EN] is idempotent, so 5 callback calls still push 1 line and counting lines stays green forever
    # [EN] (the first counterexample run missed exactly that).
    for _ in range(4):
        CREDIT.note(CREDIT.OutOfCredit(provider='deepseek', label='DeepSeek 官方',
                                       status=402))
    ok('C5 ★★★ 同一家连撞 5 次**只回调 1 次**（回调只在"头一回发现这一家没钱"时发 —— '
       '否则整理稿 18 段会刷出一堵墙）',
       hits['n'] == 1 and len(loop._notes) == 1,
       f'回调 {hits["n"]} 次 · 推了 {len(loop._notes)} 条')

    loop.resume()
    ok('C6 ★★★ 点「继续」⇒ **清掉登记**（不清的话路由器 fail-fast 会在第一发就把人挡回来，'
       '用户充了钱、点了继续，屏幕上还是"余额不足"）', CREDIT.first() is None, '')
    ok('C7 ★★★ 而且 `_credit_paused` 要复位（不复位 ⇒ 第二次撞上时回调被幂等判断挡住、'
       '再也不会暂停）', loop._credit_paused is False, '')

    # 成对：**没充就点继续** ⇒ 会再停一次、再报一次（这正是用户要的语义）
    # ⚠ 别拿"总共几条"当断言：`resume()` 自己也推了一条"正在重试"，
    #   比绝对条数会写成 2 而实际是 3（第一版就这么红的，红得像产品没推）。
    # [EN] ⚠ Don't assert on the total count: `resume()` itself pushes a "retrying" line, so an
    # [EN] absolute count of 2 is really 3 (the first version went red that way, looking as if the
    # [EN] product pushed nothing).
    _n_before = len(loop._notes)
    CREDIT.note(CREDIT.OutOfCredit(provider='deepseek', label='DeepSeek 官方', status=402))
    ok('C8 ★★★ 成对：清完登记后再撞一次 ⇒ **又停住、又推了一条**'
       '（"没充值点继续，还报这个错误"就是这条）',
       loop.paused and len(loop._notes) == _n_before + 1,
       f'推了 {len(loop._notes)} 条（撞之前 {_n_before} 条）')
    loop._paused = False

    # ⚠ 点了停止之后不许再因为欠费暂停（收工那一段会再调模型）
    CREDIT.clear()
    loop2 = _loop_fixture()
    loop2._stop_requested = True
    loop2._credit_cb = loop2._on_credit_block
    CREDIT.on_block(loop2._credit_cb)
    CREDIT.note(CREDIT.OutOfCredit(provider='deepseek', label='DeepSeek 官方', status=402))
    ok('C9 ★★ 已经点了停止 ⇒ **不再暂停**（收工那段会再调模型，一暂停就把'
       '「正在停止」顶成「等你点继续」）',
       not loop2.paused and not loop2._credit_paused, '')
    CREDIT.off_block(loop._credit_cb)
    CREDIT.off_block(loop2._credit_cb)


# ── D 状态条 ────────────────────────────────────────────────────
def d_status_bar():
    print('\n【D】状态条那一行')
    from gui.app_flet import NovelWorldApp

    class _S:
        status = 'paused'
        reason = ''
        is_alive = True

    app = NovelWorldApp.__new__(NovelWorldApp)
    app.session = _S()
    app._launch_phase = 'done'
    app._run_status_kw = {}

    CREDIT.clear()
    base, _c0 = app._status_view('idle', {})
    ok('D1 ★★ 没有欠费时**仍是原来那句**（不许把"所有暂停"都写成"余额不足"）',
       '余额不足' not in base and '暂停' in base, base)

    CREDIT.note(CREDIT.OutOfCredit(provider='deepseek', label='DeepSeek 官方', status=402))
    line, color = app._status_view('idle', {})
    ok('D2 ★★★ 挂着欠费时，那一行写清**是谁**没钱了、以及要充值',
       '余额不足' in line and 'DeepSeek 官方' in line and '充值' in line, line)
    ok('D3 ★★ 而且颜色换成报警色（不是普通的「已暂停」金色）',
       color != _c0, f'{color} vs {_c0}')
    CREDIT.clear()

    # ⚠ `t()` 按**当前界面语言**查表，默认是中文 ⇒ 不切到 en 的话，
    #   这条判据量到的是中文原文，永远"没有英文"（或者永远"就是它自己"）。
    # [EN] ⚠ `t()` looks up by the **current UI language** (Chinese by default), so without switching
    # [EN] to `en` this criterion measures the Chinese original and can never see the English.
    from i18n import get_lang, set_lang
    _back = get_lang()
    set_lang('en')
    try:
        en = t('已暂停 —— {who} 余额不足或欠费，充值后点「继续」', who='DeepSeek 官方')
    finally:
        set_lang(_back)
    ok('D4 ★★ 有英文文案（`verify_ui_english` 那套口径：新增文案必须登记，'
       '否则英文界面里冒中文）', 'DeepSeek' in en and '余额' not in en, en)


def main() -> int:
    print('═' * 62)
    print('  模型服务没钱了：明确报错 + 暂停 + 点继续重试（2026-10-25）')
    print('═' * 62)
    for fn in (a_scope, b_retry, c_pause_resume, d_status_bar):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f'{fn.__name__} 整组没跑完：{e!r}', False, '')
        finally:
            CREDIT.clear()
            CREDIT.forget_callbacks()

    bad = [r for r in _rows if not r['通过']]
    print('\n' + '─' * 62)
    print(f'  「没钱了」这条通道：{len(_rows) - len(bad)}/{len(_rows)}'
          + ('   ← 有失败' if bad else ''))
    for r in bad:
        print(f'    ! {r["判据"]}  [{r["实测"]}]')
    print('─' * 62)
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(_rows, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
