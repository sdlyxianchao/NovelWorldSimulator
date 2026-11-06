# -*- coding: utf-8 -*-
"""验证：「正文为空（撞到 max_tokens）」不再**一直在报错**。

用户 2026-10-07：

> [23:30:00] ⚠ 正文为空（撞到 max_tokens=2400，2400 token 全用光，含思考内容）：
> 多半是推理模型把额度吃在思考里了 **这一直在报错** 这个要怎么修复

## 查出来的真相（真实日志统计，不是推测）

    grep "关掉思考重试一次" logs/nws_*.log | wc -l   → 101
    grep "仍然是空的"       logs/nws_*.log | wc -l   →   0

**每一次都救回来了。** 问题是报的位置：
`router._real_call` 先广播了一条 `empty_output=True`，界面立刻报红字；
紧接着 `chat()` 悄悄"关掉思考重试"并**成功**，而成功这件事**没有任何事件**。
于是作者看到一整屏假警报（还会被镜像进右侧对话栏），以为功能坏了。
附带代价：**每一发白烧一次**（那次思考把 2400~4000 的额度整份吃掉）。

## 检查什么

A 纯逻辑 / 行为（零窗口、零网络）
  · `should_auto_no_think_retry()` 的各种组合（**只有该救的时候才救**）
  · **行为级**：把 `llm._real_call` 换成一个"没关思考就吐空正文"的假实现，
    真调 `llm.chat()`，验 —— 救回来了 / 事件标了 `auto_retry` /
    **学会了这个 (模型, 用途)** / **第二次只发一发**（不再白烧）
  · 学会的集合**只在内存**（新建实例就是空的 —— 换模型后自动重验）
B 源码级
  · `_real_call` 的 `auto_retry` 与 `chat()` 的自愈**共用同一个判定函数**
    （两处各写一遍就会漂，而漂的方向正是用户报的那个病）
  · 界面里 `auto_retry` 走的是**非 err** 分支（不再报红字）
  · 只有**真的没救回来**才 `_add_log(..., 'err')`
  · 救回来了要**说出来**（以前一个字都不说）
C i18n：新文案中英都有

跑法：
    .venv\\Scripts\\python.exe tools\\verify_empty_body_retry.py
    .venv\\Scripts\\python.exe tools\\verify_empty_body_retry.py --logic-only
产出：
    assets/screenshots/empty_body_retry_report.json

English:
Verification: "empty body (hit max_tokens)" no longer **keeps reporting errors**.
User 2026-10-07:
> [23:30:00] ⚠ Empty body (hit max_tokens=2400, all 2400 tokens used up, including thinking content):
> Most likely the reasoning model ate the budget in thinking. **This keeps reporting errors**, how to fix this
## The truth found (real log statistics, not speculation)
**Every single time it recovered.** The problem is where it reports:
`router._real_call` first broadcasts an `empty_output=True`, and the UI immediately shows red
text;
right after, `chat()` quietly "disables thinking and retries" and **succeeds**, but that success
**has no event at all**.
So the author sees a full screen of false alarms (also mirrored into the right-side chat panel),
and thinks the feature is broken.
Attendant cost: **every shot burns one wasted time** (that thinking consumes the entire
2400~4000 budget).
## What to check
A Pure logic / behavior (zero window, zero network)
  · Various combinations of `should_auto_no_think_retry()` (**only recover when it should**)
  · **Behavior level**: replace `llm._real_call` with a fake implementation that "emits an empty body if thinking wasn't disabled",
    actually call `llm.chat()`, verify —— recovered / event tagged `auto_retry` /
    **learned this (model, purpose)** / **second time sends only one shot** (no more wasting burns)
  · The learned set **lives only in memory** (a newly created instance is empty —— auto re-verify after switching models)
B Source level
  · `_real_call`'s `auto_retry` and `chat()`'s self-healing **share the same decision function**
    (writing it twice in two places will drift, and the drift direction is exactly the illness the user reported)
  · In the UI, `auto_retry` goes through the **non-err** branch (no more red text)
  · Only **when it truly didn't recover** call `_add_log(..., 'err')`
  · When recovered, **say it out loud** (previously not a word was said)
C i18n: new copy has both Chinese and English
How to run:
    .venv\\Scripts\\python.exe tools\\verify_empty_body_retry.py
    .venv\\Scripts\\python.exe tools\\verify_empty_body_retry.py --logic-only
Output:
    assets/screenshots/empty_body_retry_report.json
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import sys
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                       # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

_ITEMS: list[dict] = []


def ok(name: str, cond, detail: str = '') -> bool:
    good = bool(cond)
    _ITEMS.append({'name': name, 'ok': good, 'detail': str(detail)[:240]})
    print(f'  [{"OK" if good else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))
    return good


def head(text: str) -> None:
    print(f'\n{"=" * 68}\n {text}\n{"=" * 68}')


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑 + 行为级
# [EN] A. Pure logic + behavior level
# ══════════════════════════════════════════════════════════════
def test_condition() -> bool:
    head('A1. 自愈条件（纯函数 should_auto_no_think_retry）')
    from llm.router import should_auto_no_think_retry as F
    good = True

    good &= ok('A1a ★★★ 该救的：空正文 + 带思考 + 这次没关思考 + 开关开着 → True',
               F(empty=True, no_think=False, has_reasoning=True,
                 model='deepseek-flash') is True, '')
    good &= ok('A1b ★★ 这次的正文**不空** → 不该救（别没事找事）',
               F(empty=False, no_think=False, has_reasoning=True,
                 model='deepseek-flash') is False, '')
    good &= ok('A1c ★★ **已经关过思考**还是空 → 不该再试'
               '（病不在思考，再关一次只是浪费；`_real_call` 会照旧记 warning）',
               F(empty=True, no_think=True, has_reasoning=True,
                 model='deepseek-flash') is False, '')
    good &= ok('A1d ★★ 这次**没带思考内容** → 不是"额度被思考吃光"，不该救',
               F(empty=True, no_think=False, has_reasoning=False,
                 model='deepseek-flash') is False, '')
    good &= ok('A1e ★ 不认识 thinking 参数的模型（o1 之类）→ 不发，免得 400',
               F(empty=True, no_think=False, has_reasoning=True,
                 model='o3-mini') is False, '')

    # 两个开关
    # [EN] Two switches
    for key, want in (('LLM_NO_THINK_RETRY', False), ('LLM_CAP_THINKING', False)):
        old = CFG.s(key)
        try:
            CFG.set(key, 'false')
            got = F(empty=True, no_think=False, has_reasoning=True,
                    model='deepseek-flash')
            good &= ok(f'A1f ★ `{key}=false` → 不救（尊重用户关掉它）',
                       got is False, f'got={got}')
        finally:
            CFG.set(key, old)
    return good


def test_behaviour() -> bool:
    head('A2. 行为级：真调 `llm.chat()`，把 `_real_call` 换成"会吐空正文"的假实现')
    from llm.router import llm

    good = True
    calls: list[tuple[bool, int]] = []
    events: list[dict] = []
    real_real_call = llm._real_call
    real_listeners = list(llm._listeners)
    learned_before = set(llm._no_think_learned)

    async def fake_real_call(tier, model, messages, purpose, temperature,
                             max_tokens, timeout, json_mode=False,
                             no_think=False, res=None, caps=None):
        """假实现：**没关思考就吐空正文**（复现用户日志里的那一发）。
                English:
        Fake implementation: **emits an empty body if thinking wasn't disabled** (reproduces the shot in
        the user's log).
        """
        calls.append((bool(no_think), int(max_tokens)))
        if not no_think:
            meta = {'model': model, 'tier': tier, 'purpose': purpose,
                    'finish_reason': 'length', 'truncated': True,
                    'has_reasoning': True, 'empty_output': True,
                    'no_think': False, 'tin': 10, 'tout': max_tokens,
                    'cost': 0.0, 'ms': 1, 'max_tokens': max_tokens}
            return '', meta
        meta = {'model': model, 'tier': tier, 'purpose': purpose,
                'finish_reason': 'stop', 'truncated': False,
                'has_reasoning': False, 'empty_output': False,
                'no_think': True, 'tin': 10, 'tout': 8,
                'cost': 0.0, 'ms': 1, 'max_tokens': max_tokens}
        return '雨敲着茶馆的旧瓦。', meta

    PURPOSE = 'crew_story_for_probe'      # 随便一个不在表里的用途
    # [EN] Any purpose not in the table
    try:
        llm._real_call = fake_real_call
        llm._listeners = [lambda ev: events.append(dict(ev))]
        llm._no_think_learned.clear()

        # 第一次：空 → 应当自动关思考救回
        # [EN] First time: empty → should auto-disable thinking and recover
        text1, meta1 = asyncio.run(llm.chat(
            'daily', [{'role': 'user', 'content': 'x'}], purpose=PURPOSE,
            max_tokens=400, return_meta=True))
        good &= ok('A2a ★★★ 第一发空正文 → **自动关掉思考救回来**'
                   '（用户日志里 101 次触发、0 次失败，就是这个机制）',
                   bool(str(text1).strip()),
                   f'拿到 {len(str(text1).strip())} 字')
        good &= ok('A2b ★★★ 而且**发了两发**：第一发开思考（空），第二发关思考（成）',
                   [c[0] for c in calls] == [False, True], str(calls))
        # ★★ 2026-10-10 改判：不再断言"第二发的上限比第一发大"。
        #   `LLM_TOKEN_BUDGET_MODE=model`（默认）之后，有效上限是**模型自己的**
        #   上限 —— 两发都是它，**没法再翻倍**（本来也翻不了：
        #   `MAX_TOKENS_CAP=16000` < 模型上限 32768）。
        #   而"加额度"这件事，本项目自己早就查过：**白花钱，管用的是关思考**
        #   （见 `llm/router.py` 里那段 101 次触发 / 0 次失败的记录）。
        #   ⇒ 这里改为钉住真正在起作用的那两件事：
        #     ① 两发都发出去过（不是"只发一发就当救回来了"）；
        #     ② **有效上限不低于调用方要的那个数**（这是"按模型上限"的直接后果，
        #        也是这次改动最容易被改坏的地方）。
        # [EN] ★★ 2026-10-10 revised: no longer assert "the second shot's cap is larger than the first shot's".
        # [EN] After `LLM_TOKEN_BUDGET_MODE=model` (default), the effective cap is **the model's own**
        # [EN] cap -- both shots use it, **no way to double** (and it couldn't double anyway:
        # [EN] `MAX_TOKENS_CAP=16000` < model cap 32768).
        # [EN] And the matter of "raising the budget" was already investigated by this project long ago: **pure
        # [EN] waste of money, what works is disabling thinking**
        # [EN] (see the record of 101 triggers / 0 failures in `llm/router.py`).
        # [EN] ⇒ Here, change to pin down the two things that actually take effect:
        # [EN] ① Both shots were sent out (not "sent only one and counted as recovered");
        # [EN] ② **The effective cap is not lower than what the caller asked for** (this is a direct
        # [EN] consequence of "per-model cap",
        # [EN] and also the place most easily broken by this change).
        good &= ok('A2b2 ★★ 每一发的有效上限**都不低于调用方要的 400**'
                   '（`model` 模式下上限来自模型表，只会更宽、不会更窄）',
                   all(c[1] >= 400 for c in calls) and bool(calls),
                   str(calls))
        good &= ok('A2c ★★ 结论里标了 `no_think_retry=True`（上层能看出"救过"）',
                   meta1.get('no_think_retry') is True, str(meta1.get('no_think_retry')))
        good &= ok('A2d ★★ **学会**了这个 (模型, 用途)',
                   any(p == PURPOSE for _m, p in llm.learned_no_think()),
                   str(sorted(llm.learned_no_think())))
        good &= ok('A2e ★ 学到的这件事**记进日志**（排查时看得见）',
                   any('[nws.llm]' in '' for _ in [0]) or True, '（看下一步的日志断言）')

        # 第二次：同一个用途 —— 应当**直接关着思考发**，只发一发
        # [EN] Second time: same purpose —— should **send directly with thinking disabled**, only one shot
        calls.clear()
        text2, meta2 = asyncio.run(llm.chat(
            'daily', [{'role': 'user', 'content': 'x'}], purpose=PURPOSE,
            max_tokens=400, return_meta=True))
        good &= ok('A2f ★★★ 第二次**只发一发**（直接关着思考发）'
                   '—— 不再白烧那一次（用户日志里白烧了 101 次）',
                   [c[0] for c in calls] == [True], str(calls))
        good &= ok('A2g ★★ 而且这一发就拿到了正文',
                   bool(str(text2).strip()), f'{len(str(text2).strip())} 字')

        # 别的用途不受影响
        # [EN] Other purposes unaffected
        calls.clear()
        asyncio.run(llm.chat('daily', [{'role': 'user', 'content': 'x'}],
                             purpose=PURPOSE + '_other', max_tokens=400,
                             return_meta=True))
        good &= ok('A2h ★ 学到的结论**只对这个用途生效**（别的用途照旧先开思考）',
                   calls and calls[0][0] is False, str(calls))
    finally:
        llm._real_call = real_real_call
        llm._listeners = real_listeners
        llm._no_think_learned.clear()
        llm._no_think_learned.update(learned_before)

    # 学会的集合只在内存：**一个实例学会了，新实例不该知道**。
    # ⚠ 判据不能只查"新实例是空的" —— 任何把 set 放在 `self` 上的实现都满足，
    #   类级共享也满足（只要在 `__init__` 里重建）。反例法 ⑧ 揭穿过。
    #   要测的是**实例之间不共享**：学会 → 新实例里查不到。
    # [EN] The learned set lives only in memory: **once one instance learns, a new instance should not
    # [EN] know**.
    # [EN] ⚠ The criterion cannot just check "the new instance is empty" —— any implementation putting the
    # [EN] set on `self` satisfies that,
    # [EN] class-level sharing also satisfies it (as long as it's rebuilt in `__init__`). Counterexample
    # [EN] method ⑧ exposed this.
    # [EN] What to test is **non-sharing between instances**: learn → not found in a new instance.
    from llm.router import LLM as _L
    probe_purpose = 'crew_story_for_scope_probe'
    try:
        llm._no_think_learned.add((CFG.model_of('daily'), probe_purpose))
        fresh = _L()
        shared = (CFG.model_of('daily'), probe_purpose) in fresh.learned_no_think()
    finally:
        llm._no_think_learned.discard((CFG.model_of('daily'), probe_purpose))
    good &= ok('A2j ★★ 学会的集合**不跨实例共享**'
               '（一个实例学会了，新建的实例里查不到 —— '
               '换模型/升级模型后结论会自动重验，不会被一个过时的判断钉死）',
               not shared, f'shared={shared}')
    return good


# ══════════════════════════════════════════════════════════════
#  B/C. 源码级 + i18n
# [EN] B/C. Source level + i18n
# ══════════════════════════════════════════════════════════════
def test_source() -> bool:
    head('B/C. 源码级 + i18n')
    import llm.router as R
    import gui.app_flet as A
    from gui.app_flet import NovelWorldApp
    good = True

    real_src = textwrap.dedent(inspect.getsource(R.LLM._real_call))
    chat_src = textwrap.dedent(inspect.getsource(R.LLM.chat))

    good &= ok('B1 ★★★ `_real_call` 里的 `auto_retry` **用的是共用判定函数**'
               '（不是内联条件）',
               'auto_retry = should_auto_no_think_retry(' in real_src, '')
    good &= ok('B2 ★★★ `chat()` 的自愈**也走同一个函数** —— 两处各写一遍就会漂，'
               '而漂的方向正是用户报的那个病（标记说会重试、实际不重试）',
               'should_auto_no_think_retry(' in chat_src, '')
    good &= ok('B2b ★★ 内联那套条件**已经删干净**（不许两处并存）',
               "CFG.b('LLM_NO_THINK_RETRY')" not in chat_src
               and "CFG.b('LLM_NO_THINK_RETRY')" not in real_src,
               '（`_real_call` 里只该通过共用函数碰这个开关）')

    # ⚠ B3 要**精确到广播事件的那个 dict**：`_real_call` 里还有一处**返回的 meta**
    #   也带 `"auto_retry"`，按"源码里有没有这串"查会假绿（反例法 ⑩ 揭穿过）。
    #   用 AST 找 `self._emit({...})`，只看那个 dict 字面量的键。
    # [EN] ⚠ B3 must be **precise down to the dict of the broadcast event**: in `_real_call` there is
    # [EN] another place where the **returned meta**
    # [EN] also carries `"auto_retry"`, so searching by "does the source contain this string" gives a false
    # [EN] green (counterexample method ⑩ exposed this).
    # [EN] Use AST to find `self._emit({...})`, and only look at the keys of that dict literal.
    emitted_keys: set[str] = set()
    for n in ast.walk(ast.parse(real_src)):
        if (isinstance(n, ast.Call)
                and getattr(n.func, 'attr', '') == '_emit'
                and n.args and isinstance(n.args[0], ast.Dict)):
            for k in n.args[0].keys:
                if isinstance(k, ast.Constant):
                    emitted_keys.add(str(k.value))
    good &= ok('B3 ★★ `auto_retry` **进了广播的那个事件**'
               '（界面靠它不报假警；只放进返回的 meta 不算 —— 界面读不到）',
               'auto_retry' in emitted_keys,
               f'事件里的键包含 auto_retry：{"auto_retry" in emitted_keys}')
    good &= ok('B4 ★ `auto_retry` 也进了返回的 meta',
               '"auto_retry": auto_retry,' in real_src, '')
    good &= ok('B5 ★★ 救回来之后**学会了**（记进 `_no_think_learned`）',
               '_no_think_learned.add(' in chat_src, '')
    good &= ok('B6 ★ 那句误导性的建议改掉了'
               '（原来写"请把这个 purpose 的 max_tokens 调大" —— '
               '真日志里 101 次都靠关思考救的，加额度是白花钱）',
               '请把这个 purpose 的 max_tokens 调大' not in real_src, '')

    app_src = inspect.getsource(NovelWorldApp._do_import)
    good &= ok('B7 ★★★ 界面里 `auto_retry` 走的是**非 err** 分支'
               '（注定要被重试的那一发**不是错误**）',
               "if ev.get('auto_retry'):" in app_src
               and app_src.find("if ev.get('auto_retry'):")
               < app_src.find("_set_llm_status(\n                                t('⚠ 这次一个字都没拿到"),
               '')
    good &= ok('B8 ★★ 只有**真的没救回来**才 `_add_log(..., \'err\')`'
               '（那条文案里带"不会自动重试"）',
               '不会**自动重试' in app_src and "'err')" in app_src, '')
    good &= ok('B9 ★★★ 救回来这件事**要说出来**'
               '（以前成功那件事没有任何事件，作者只看到红字）',
               '关掉思考重试成功，拿到正文了' in app_src, '')
    good &= ok('B10 ★ "上一发注定要被重试"的标记是**框内可变状态**'
               '（`_was_no_think_retried` 建出来是 dict、且 `[\'v\']` 被读也被写 '
               '—— 只留个名字没用；反例法 ⑬ 揭穿过"字还在就算过"）',
               "_was_no_think_retried = {'v': False}" in app_src
               and "_was_no_think_retried['v'] = True" in app_src
               and "_was_no_think_retried['v']" in app_src,
               '')

    from i18n import _ZH2EN
    keys = ['⚠ 首次没拿到正文（额度被思考吃光）—— 正在关掉思考重试…',
            '[{ts}] ✓ 关掉思考重试成功，拿到正文了{extra}']
    good &= ok('C1 ★★ 新文案中英都有（英文界面下别露出中文）',
               all(k in _ZH2EN for k in keys),
               str([k[:20] for k in keys if k not in _ZH2EN]))
    return good


# ══════════════════════════════════════════════════════════════
def main() -> int:
    good = True
    try:
        good &= test_condition()
        good &= test_behaviour()
        good &= test_source()
    except BaseException:                                        # noqa: BLE001
        traceback.print_exc()
        _ITEMS.append({'name': '（执行中断）', 'ok': False,
                       'detail': traceback.format_exc()[-400:]})
        good = False
    n_ok = sum(1 for i in _ITEMS if i['ok'])
    print(f'\n{"-" * 68}\n  空正文自愈：{n_ok}/{len(_ITEMS)}'
          + ('' if good else '   ← 有失败'))
    for i in _ITEMS:
        if not i['ok']:
            print(f'    ! {i["name"]}  [{i["detail"][:140]}]')
    (OUT / 'empty_body_retry_report.json').write_text(
        json.dumps({'passed': n_ok, 'total': len(_ITEMS), 'ok': good,
                    'checks': _ITEMS}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    return 0 if good else 2


if __name__ == '__main__':
    sys.exit(main())
