# -*- coding: utf-8 -*-
"""验证：**合规 Agent 真的接上了**（设计稿 §十六，CP1 / CP6）。

用户 2026-10-06：「都做掉」。查证结果是**这条链路整个是死的**：
`compliance/agent.py` 写着，`COMPLIANCE_*` 在界面上摆着，
但**全项目没有一个地方实例化过它** —— 推演路径上一次都没调用过。
"独立专职 Agent"变成了"不存在的 Agent"。

判据分层（每层都要能红，见 `developers/mutate_compliance.py`）：
  A **分级**：C0 拦、C1 按 `COMPLIANCE_ACTION`、白名单豁免、关掉全放过、
     检查点名单（`minimal` 只留 CP6）。
  B **LLM 复核**：`hybrid` 无敏感线索**一次都不叫**、有线索才叫；
     `never` 不叫；`COMPLIANCE_MODEL` 认得出就换档。
     ★★ **拿不到结论 → `hold`（不放行）**：旧实现是 `fail-open`（当 pass），
     合规是生死线，"模型没答"不等于"内容没问题"。
  C **策略库**：`COMPLIANCE_POLICY_DIR` 能加载词表；
     `COMPLIANCE_WATCH_POLICY` 改了文件自动重载。
  D **接线**：`assemble()` 真的造了一个挂在 loop 上；
     `_compliance_gate` 三档行为（原样 / 改写 / 替身 + 播报）；
     CP6 在 prose 落盘前、CP1 在 freeze 后（源哨兵 + 端到端）。

用法：.venv\\Scripts\\python.exe tools/verify_compliance.py
产出：assets/screenshots/compliance_report.json

English:
Verification: **the compliance Agent is really wired in** (design doc §16, CP1 / CP6).
User 2026-10-06: "just do it all". The investigation result is that **this entire chain is
dead**:
`compliance/agent.py` exists, `COMPLIANCE_*` sits there in the UI,
but **nothing in the whole project ever instantiates it** —— it was never called once on the
simulation path.
"Independent dedicated Agent" became "Agent that does not exist".
Criteria layered (every layer must be able to go red, see `developers/mutate_compliance.py`):
  A **tiering**: C0 blocks, C1 follows `COMPLIANCE_ACTION`, whitelist exemptions, turn it off to let everything through,
     checkpoint list (`minimal` keeps only CP6).
  B **LLM review**: `hybrid` with no sensitive leads **never calls** it, only calls when there are leads;
     `never` does not call; `COMPLIANCE_MODEL` switches tiers once recognized.
     ★★ **no conclusion obtained → `hold` (do not let through)**: the old implementation was `fail-open` (treated as pass),
     compliance is a lifeline, "the model did not answer" does not mean "the content is fine".
  C **policy library**: `COMPLIANCE_POLICY_DIR` can load the wordlist;
     `COMPLIANCE_WATCH_POLICY` auto-reloads when the file is changed.
  D **wiring**: `assemble()` actually creates one attached to the loop;
     `_compliance_gate` three-tier behavior (as-is / rewrite / replacement + announcement);
     CP6 before prose is written to disk, CP1 after freeze (source sentinel + end-to-end).
Usage: .venv\\Scripts\\python.exe tools/verify_compliance.py
Output: assets/screenshots/compliance_report.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
# ⚠ 不量像素、不弹窗、**绝不点会 `CFG.save()` 的按钮**（MEMORY 的铁律）。
# [EN] ⚠ Do not measure pixels, do not pop up dialogs, **never click any button that triggers
# [EN] `CFG.save()`** (iron rule of MEMORY).
CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


class FakeDB:
    def __init__(self):
        self.rows: list[tuple] = []

    def add_compliance(self, *a, **k):
        self.rows.append(a)

    def exonerate(self, cid):
        return True


def make_agent(policy_dir=None, whitelist=''):
    from compliance.agent import ComplianceAgent
    CFG.set('COMPLIANCE_WHITELIST', whitelist)
    return ComplianceAgent(FakeDB(), policy_dir), None


def _reply(reply_value, ok=True, notes=None):
    """造一个 `Reply`（**同步**函数 —— 别写成 async：在已经跑起来的循环里
    `asyncio.run()` 会直接抛 `cannot be called from a running event loop`，
    而那个异常会被 `ask` 的兜底吞掉，表现成"复核没拿到结论"）。
        English:
    Create a `Reply` (**synchronous** function —— do not write it as async: in an already-running
    loop
        `asyncio.run()` will directly throw `cannot be called from a running event loop`,
        and that exception will be swallowed by `ask`'s fallback, manifesting as "review got no conclusion".
    """
    from llm.replies import Reply
    return Reply(value=reply_value, ok=ok, notes=list(notes or []))


# ══════════════════════════════════════════════════════════════
#  A. 分级
# [EN] A. Tiering
# ══════════════════════════════════════════════════════════════
def test_levels() -> bool:
    ok = True
    import compliance.agent as CA
    saved = {k: CFG.raw(k) for k in
             ('COMPLIANCE_ENABLED', 'COMPLIANCE_ACTION', 'COMPLIANCE_CHECKPOINTS',
              'COMPLIANCE_LLM_REVIEW', 'COMPLIANCE_WHITELIST', 'COMPLIANCE_LOG')}
    real = CA.ask
    try:
        CFG.set('COMPLIANCE_LOG', 'true')
        CFG.set('COMPLIANCE_LLM_REVIEW', 'never')
        CFG.set('COMPLIANCE_ACTION', 'rewrite')
        CFG.set('COMPLIANCE_CHECKPOINTS', 'all')

        # ① 关掉 → 全放过，且**不记日志**
        # [EN] ① Off → pass everything, and **do not log**
        CFG.set('COMPLIANCE_ENABLED', 'false')
        a, _ = make_agent()
        r = asyncio.run(a.check('随便什么', 'CP6'))
        ok &= rec('A1 ★ `COMPLIANCE_ENABLED=false` → 放过（旋钮真被读）',
                  r.passed and a.db.rows == [], f'{r.level}/{r.action}')

        CFG.set('COMPLIANCE_ENABLED', 'true')
        # ② 检查点名单：minimal 只留 CP6
        # [EN] ② Checkpoint list: `minimal` keeps only CP6
        CFG.set('COMPLIANCE_CHECKPOINTS', 'minimal')
        r = asyncio.run(a.check('随便什么', 'CP3'))
        ok &= rec('A2 ★★ `COMPLIANCE_CHECKPOINTS=minimal` → CP3 不查、CP6 才查',
                  r.passed and '不在本轮检查点' in r.reason, r.reason)
        CFG.set('COMPLIANCE_CHECKPOINTS', 'all')

        # ③ C0 词 → block（词表从策略库来，这里手工塞一条）
        # [EN] ③ C0 word → block (wordlist comes from the policy store; manually inject one entry here)
        a._blocked_words = ['绝对禁止词']
        r = asyncio.run(a.check('这里有绝对禁止词哦', 'CP6'))
        ok &= rec('A3 ★★ C0 词命中 → **block**（零成本那一层就能拦住）',
                  r.level == 'C0' and r.action == 'block' and not r.passed,
                  f'{r.level}/{r.action}/{r.reason}')

        # ④ C1 词 → 按 `COMPLIANCE_ACTION` 收口
        # [EN] ④ C1 word → close out per `COMPLIANCE_ACTION`
        a._blocked_words = []
        a._restricted_words = ['限制级词']
        for act in ('rewrite', 'block', 'pause'):
            CFG.set('COMPLIANCE_ACTION', act)
            r = asyncio.run(a.check('这里有限制级词', 'CP6'))
            ok &= rec(f'A4 ★ C1 词命中 + `COMPLIANCE_ACTION={act}` → action 就是它',
                      r.level == 'C1' and r.action == act, f'{r.level}/{r.action}')

        # ⑤ 白名单：豁免词先剔掉再查
        # [EN] ⑤ Whitelist: strip exempt words first, then check
        CFG.set('COMPLIANCE_ACTION', 'rewrite')
        a2, _ = make_agent(whitelist='限制级词')
        a2._restricted_words = ['限制级词']
        CFG.set('COMPLIANCE_LLM_REVIEW', 'never')
        r = asyncio.run(a2.check('这里有 限制级词 但它在白名单里', 'CP6'))
        # ⚠ 判据**不能只判 `passed`**：C1 命中时 action 是 `rewrite`，
        #   而 `rewrite` 也算 `passed` —— 于是"白名单被忽略"那个变异一条都不红
        #   （反例法抓到的）。该断言的是**根本没命中**（level=C2）。
        # [EN] ⚠ The criterion **must not check only `passed`**: when C1 hits, action is `rewrite`,
        # [EN] and `rewrite` also counts as `passed` — so the mutation "whitelist ignored" shows no red at all
        ok &= rec('A5 ★★ 白名单命中 → **根本没命中**（level=C2，虚构创作豁免不是摆设）',
                  r.level == 'C2' and r.passed, f'{r.level}/{r.action}/{r.reason}')
        # 反例：不在白名单的同一条词仍然拦得住
        # [EN] Counterexample: the same word not in the whitelist is still blocked
        a2._whitelist = []
        r = asyncio.run(a2.check('这里有限制级词', 'CP6'))
        ok &= rec('A5 ★ 反例：白名单撤掉后同一条词仍然拦得住（判据不是恒真）',
                  r.level == 'C1', f'{r.level}/{r.action}')
    finally:
        CA.ask = real
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


# ══════════════════════════════════════════════════════════════
#  B. LLM 复核（重点：不许 fail-open）
# [EN] B. LLM review (key point: no fail-open allowed)
# ══════════════════════════════════════════════════════════════
def test_llm_review() -> bool:
    ok = True
    import compliance.agent as CA
    saved = {k: CFG.raw(k) for k in
             ('COMPLIANCE_ENABLED', 'COMPLIANCE_LLM_REVIEW', 'COMPLIANCE_ACTION',
              'COMPLIANCE_CHECKPOINTS', 'COMPLIANCE_MODEL', 'COMPLIANCE_LOG',
              'COMPLIANCE_WHITELIST')}
    real = CA.ask
    calls: list[dict] = []

    def stub(value, ok_=True, notes=None):
        async def _f(tier, messages, **kw):
            calls.append({'tier': tier, **kw})
            return _reply(value, ok_, notes)
        return _f

    try:
        CFG.set('COMPLIANCE_ENABLED', 'true')
        CFG.set('COMPLIANCE_CHECKPOINTS', 'all')
        CFG.set('COMPLIANCE_ACTION', 'rewrite')
        CFG.set('COMPLIANCE_LOG', 'true')
        CFG.set('COMPLIANCE_MODEL', '')
        a, _ = make_agent()

        # ① hybrid + 无敏感线索 → 一次都不叫
        # [EN] ① hybrid + no sensitive clue → not called even once
        CFG.set('COMPLIANCE_LLM_REVIEW', 'hybrid')
        CA.ask = stub({'级别': 'C2', '判定': 'pass', '理由': 'ok'})
        calls.clear()
        r = asyncio.run(a.check('今天茶不错，阿枝给客人添了水。', 'CP6'))
        ok &= rec('B1 ★★ `hybrid` + 无敏感线索 → **一次 LLM 都不叫**'
                  '（"省约 70%"就在这里）', calls == [] and r.passed, str(len(calls)))

        # ② hybrid + 敏感线索 → 叫
        # [EN] ② hybrid + sensitive clue → called
        calls.clear()
        r = asyncio.run(a.check('他拿刀砍了过去，血溅当场。', 'CP6'))
        ok &= rec('B2 ★★ `hybrid` + 有敏感线索 → 真去复核', len(calls) == 1,
                  str(len(calls)))
        ok &= rec('B2 ★ 复核走的是 `compliance` 用途（别拿别的事来凑）',
                  calls and calls[0].get('purpose') == 'compliance',
                  str(calls[:1])[:160])

        # ③ never → 不叫
        # [EN] ③ never → not called
        CFG.set('COMPLIANCE_LLM_REVIEW', 'never')
        calls.clear()
        asyncio.run(a.check('他拿刀砍了过去，血溅当场。', 'CP6'))
        ok &= rec('B3 ★ `COMPLIANCE_LLM_REVIEW=never` → 纯规则层，不叫',
                  calls == [], str(len(calls)))
        CFG.set('COMPLIANCE_LLM_REVIEW', 'hybrid')

        # ④ ★★ 拿不到结论 → hold（**不放行**）
        # [EN] ④ ★★ cannot get a conclusion → hold (**do not let through**)
        CA.ask = stub(None, ok_=False, notes=['模型没给出可用的JSON对象'])
        r = asyncio.run(a.check('他拿刀砍了过去。', 'CP6'))
        ok &= rec('B4 ★★ 复核**拿不到结论** → `hold`，**不放行**'
                  '（旧实现是 fail-open 当 pass —— 合规的生死线不能这么松）',
                  r.action == 'hold' and not r.passed and r.level == 'C?',
                  f'{r.level}/{r.action}/{r.reason[:60]}')
        ok &= rec('B4 ★ 替身文本为空串（调用方据此换一句安全的）',
                  r.apply('原文') == '', repr(r.apply('原文')))

        # ⑤ 判定 C1 → 用模型的改写
        # [EN] ⑤ verdict C1 → use the model's rewrite
        CA.ask = stub({'级别': 'C1', '判定': 'rewrite', '理由': '手法太细',
                       '改写': '他把人制住了。'})
        r = asyncio.run(a.check('他拿刀砍了过去。', 'CP6'))
        ok &= rec('B5 ★★ 模型判 C1+rewrite → `apply()` 给的是**改写后的文本**',
                  r.passed and r.apply('原文') == '他把人制住了。',
                  f'{r.action} / {r.apply("原文")}')

        # ⑥ C0 → 拦
        # [EN] ⑥ C0 → block
        CA.ask = stub({'级别': 'C0', '判定': 'block', '理由': '禁止内容'})
        r = asyncio.run(a.check('他拿刀砍了过去。', 'CP6'))
        ok &= rec('B5 ★ 模型判 C0 → block，不放行',
                  r.action == 'block' and not r.passed, f'{r.level}/{r.action}')

        # ⑦ COMPLIANCE_MODEL 认得出来就换档
        # [EN] ⑦ COMPLIANCE_MODEL can recognize it → switch tier
        CFG.set('COMPLIANCE_MODEL', CFG.s('MODEL_FRONT'))
        calls.clear()
        asyncio.run(a.check('他拿刀砍了过去。', 'CP6'))
        ok &= rec('B6 ★★ `COMPLIANCE_MODEL` 指到华彩档 → 复核真的走华彩档',
                  calls and calls[0].get('tier') == 'front', str(calls[:1])[:120])
        CFG.set('COMPLIANCE_MODEL', '一个不存在的模型名')
        calls.clear()
        asyncio.run(a.check('他拿刀砍了过去。', 'CP6'))
        ok &= rec('B6 ★ 认不出的模型名 → **照旧走摘要档**（不为一个可选旋钮把路弄断）',
                  calls and calls[0].get('tier') == 'cheap', str(calls[:1])[:120])
        CFG.set('COMPLIANCE_MODEL', '')

        # ⑧ COMPLIANCE_LOG=false → 不写库
        # [EN] ⑧ COMPLIANCE_LOG=false → do not write to DB
        CFG.set('COMPLIANCE_LOG', 'false')
        a.db.rows.clear()
        asyncio.run(a.check('他拿刀砍了过去。', 'CP6'))
        ok &= rec('B7 ★ `COMPLIANCE_LOG=false` → 不记库（旋钮真被读）',
                  a.db.rows == [], str(a.db.rows))
        CFG.set('COMPLIANCE_LOG', 'true')
        a.db.rows.clear()
        asyncio.run(a.check('他拿刀砍了过去。', 'CP6'))
        ok &= rec('B7 ★ 反例：开着就记（判据不是恒真）', len(a.db.rows) == 1,
                  str(len(a.db.rows)))
    finally:
        CA.ask = real
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 策略库
# [EN] C. Policy library
# ══════════════════════════════════════════════════════════════
def test_policy_dir() -> bool:
    ok = True
    import compliance.agent as CA
    saved = {k: CFG.raw(k) for k in
             ('COMPLIANCE_POLICY_DIR', 'COMPLIANCE_WATCH_POLICY',
              'COMPLIANCE_LLM_REVIEW', 'COMPLIANCE_ENABLED',
              'COMPLIANCE_CHECKPOINTS', 'COMPLIANCE_WHITELIST')}
    real = CA.ask

    async def _never(*a, **k):
        raise AssertionError('这一段的判定应该由词表给出，不该叫 LLM')

    try:
        CFG.set('COMPLIANCE_LLM_REVIEW', 'never')
        CFG.set('COMPLIANCE_ENABLED', 'true')
        CFG.set('COMPLIANCE_CHECKPOINTS', 'all')
        CFG.set('COMPLIANCE_WHITELIST', '')
        d = Path(tempfile.mkdtemp(prefix='nws_pol_'))
        (d / 'blocked_words.txt').write_text('# 注释\n丙类禁词\n', encoding='utf-8')
        (d / 'restricted_words.txt').write_text('乙类限词\n', encoding='utf-8')
        CFG.set('COMPLIANCE_POLICY_DIR', str(d))
        CA.ask = _never
        a, _ = make_agent(Path(d))
        ok &= rec('C1 ★★ `COMPLIANCE_POLICY_DIR` 里的词表**真的加载了**'
                  '（C0/C1 各一条，注释行不算）',
                  a._blocked_words == ['丙类禁词'] and a._restricted_words == ['乙类限词'],
                  f'{a._blocked_words} / {a._restricted_words}')
        r = asyncio.run(a.check('这里出现了丙类禁词', 'CP6'))
        ok &= rec('C1 ★ 加载来的 C0 词真的拦得住', r.action == 'block',
                  f'{r.level}/{r.action}')

        # 热重载
        # [EN] hot reload
        CFG.set('COMPLIANCE_WATCH_POLICY', 'true')
        time.sleep(0.02)
        (d / 'blocked_words.txt').write_text('丙类禁词\n丁类新词\n', encoding='utf-8')
        os.utime(d / 'blocked_words.txt', (time.time() + 5, time.time() + 5))
        reloaded = a.maybe_watch()
        ok &= rec('C2 ★★ `COMPLIANCE_WATCH_POLICY` → 策略库改了**自动重载**',
                  reloaded and '丁类新词' in a._blocked_words,
                  f'{reloaded} / {a._blocked_words}')
        CFG.set('COMPLIANCE_WATCH_POLICY', 'false')
        os.utime(d / 'blocked_words.txt', (time.time() + 60, time.time() + 60))
        ok &= rec('C2 ★ 反例：关掉之后不再自动重载（判据不是恒真）',
                  a.maybe_watch() is False, '')
    finally:
        CA.ask = real
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


# ══════════════════════════════════════════════════════════════
#  D. 接线
# [EN] D. Wiring
# ══════════════════════════════════════════════════════════════
def test_wiring() -> bool:
    ok = True
    import inspect
    from sim.loop import RunLoop
    import compliance.agent as CA

    src = inspect.getsource(RunLoop._end_day)
    ok &= rec('D1 ★★ CP6：prose 落盘前真的过了 `_compliance_gate`',
              "_compliance_gate(content, 'CP6')" in src,
              ' | '.join(l.strip() for l in src.split('\n') if '_compliance_gate' in l))
    ok &= rec('D1 ★ 顺序对：先过合规**再**落盘',
              src.find('_compliance_gate') < src.find('flush_daily(self._current_day'),
              f"{src.find('_compliance_gate')} < {src.find('flush_daily(self._current_day')}")

    import sim.setup as SU
    src2 = inspect.getsource(SU.assemble)
    ok &= rec('D2 ★★ `assemble()` 真的造了合规 Agent 并挂到 loop 上'
              '（以前全项目零实例化）',
              'ComplianceAgent(' in src2 and 'compliance=compliance' in src2, '')
    src3 = inspect.getsource(SU.assemble)
    ok &= rec('D2 ★ 造不出来时**要说一声**（"悄悄没有合规"是最坏的安静）',
              '没有合规检查' in src3, '')

    import ingest.pipeline as PL
    src5 = inspect.getsource(PL.run_ingest)
    ok &= rec('D3 ★ 冻结之后才扫（定稿了才有意义）',
              src5.find('_freeze(settings_dir') < src5.find('_scan_ingest_compliance'),
              f"{src5.find('_freeze(settings_dir')} < "
              f"{src5.find('_scan_ingest_compliance')}")
    # ★★ CP1 走**端到端**：只看源码抓不到"函数开头就 return"这种变异
    #    （反例法抓到的）。真跑一遍：设定里放一个 C0 词 → 必须写出 `合规提示.md`。
    # [EN] ★★ CP1 goes **end-to-end**: only looking at source code cannot catch mutations like "return at
    # [EN] the start of the function"
    s_saved = {k: CFG.raw(k) for k in
               ('COMPLIANCE_SCAN_ON_INGEST', 'COMPLIANCE_ENABLED',
                'COMPLIANCE_POLICY_DIR', 'COMPLIANCE_CHECKPOINTS',
                'COMPLIANCE_LLM_REVIEW')}
    real_ask = CA.ask          # 这一段临时把 ask 摘掉（走纯词表路径）
    # [EN] This section temporarily removes ask (takes the pure wordlist path)
    CA.ask = None
    try:
        d = Path(tempfile.mkdtemp(prefix='nws_cp1_'))
        (d / 'blocked_words.txt').write_text('丙类禁词\n', encoding='utf-8')
        CFG.set('COMPLIANCE_POLICY_DIR', str(d))
        CFG.set('COMPLIANCE_CHECKPOINTS', 'all')
        CFG.set('COMPLIANCE_LLM_REVIEW', 'never')
        CFG.set('COMPLIANCE_ENABLED', 'true')
        sd = Path(tempfile.mkdtemp(prefix='nws_set_'))

        CFG.set('COMPLIANCE_SCAN_ON_INGEST', 'true')
        asyncio.run(PL._scan_ingest_compliance(
            sd, {'worldview': '这里出现了丙类禁词。', 'rules': '', 'people': []}))
        hit = (sd / '合规提示.md')
        ok &= rec('D3 ★★ CP1 真的跑了：扫到 C0 词 → 写出 `合规提示.md`',
                  hit.exists(), str(list(sd.iterdir())))
        ok &= rec('D3 ★ 提示里**明说程序没改设定**（作者的东西作者定）',
                  hit.exists() and '没有改动' in hit.read_text(encoding='utf-8'),
                  hit.read_text(encoding='utf-8')[:80] if hit.exists() else '')
        # 反例：关掉开关 → 一个字都不写
        # [EN] Counter-example: turn off the switch → not a single character is written
        sd2 = Path(tempfile.mkdtemp(prefix='nws_set2_'))
        CFG.set('COMPLIANCE_SCAN_ON_INGEST', 'false')
        asyncio.run(PL._scan_ingest_compliance(
            sd2, {'worldview': '这里出现了丙类禁词。', 'rules': '', 'people': []}))
        ok &= rec('D3 ★ 反例：`COMPLIANCE_SCAN_ON_INGEST=false` → 不写（判据不是恒真）',
                  not (sd2 / '合规提示.md').exists(), str(list(sd2.iterdir())))
    finally:
        CA.ask = real_ask
        for k, v in s_saved.items():
            CFG.set(k, v)

    # 端到端：`_compliance_gate` 三档行为
    # [EN] End-to-end: the three-tier behavior of `_compliance_gate`
    from llm.replies import Reply
    real = CA.ask
    real_ask = CA.ask

    class _C:
        def __init__(self, res):
            self._res = res

        async def check(self, text, cp):
            return self._res

    loop = RunLoop.__new__(RunLoop)
    # ⚠ `_push_narrative` 要用 `self.world.clock_display()` 拿时间戳 ——
    #   不塞 world 会 AttributeError（第一版就这么红的）。
    # [EN] ⚠ `_push_narrative` must use `self.world.clock_display()` to get the timestamp ——
    # [EN] Without injecting world it will AttributeError (that's how the first version failed).
    from world.state import WorldState, GameTime
    _w = WorldState()
    _w.scene = '临河茶肆'
    _w.clock = GameTime()
    loop.world = _w
    loop._cb_warned = set()
    loop._status = lambda *a, **k: None
    notes: list[tuple] = []
    # ⚠ 回调要收 `**kw` —— 产品侧 `_push_narrative` 现在一次带三个关键字
    #   （`kind` / `detail` / `update_key`）。只写 `kind=''` 会因 `detail` 未预期而抛
    #   TypeError，产品于是**退回两参调用**（它会留一条 warning），`kind` 永远拿不到 ⇒
    #   "词条类型真的传到界面了吗"这条判据永远红，而产品其实是对的。
    # [EN] ⚠ The callback must take `**kw`: `_push_narrative` now passes three keywords
    # [EN] (`kind` / `detail` / `update_key`). Declaring only `kind=''` raises TypeError on
    # [EN] `detail`, the product **falls back to two positional args** (it does log a warning), and
    # [EN] `kind` never arrives -- so "did the entry type reach the UI" stays permanently red while
    # [EN] the product is in fact correct.
    loop._on_narrative = lambda text, pri, kind='', **kw: notes.append((text, kind))

    class Disp:
        async def enqueue_narrative(self, *a, **k):
            pass

    loop.display = Disp()
    try:
        from compliance.agent import ComplianceResult
        loop.compliance = _C(ComplianceResult('C2', 'pass', '没问题'))
        got = asyncio.run(loop._compliance_gate('正文原文'))
        ok &= rec('D4 ★★ `pass` → 原样放行', got == '正文原文', got)

        loop.compliance = _C(ComplianceResult('C1', 'rewrite', '太细了',
                                              rewritten='改写后'))
        got = asyncio.run(loop._compliance_gate('正文原文'))
        ok &= rec('D4 ★★ `rewrite` → 用**改写后**的文本', got == '改写后', got)

        notes.clear()
        loop.compliance = _C(ComplianceResult('C?', 'hold', '没拿到结论'))
        got = asyncio.run(loop._compliance_gate('正文原文'))
        ok &= rec('D4 ★★ `hold` → **不出原文**，换一句安全替身',
                  got != '正文原文' and '略去' in got, got)
        ok &= rec('D4 ★ 拦下来要**播报**（别让作者以为今天没内容）',
                  any('合规' in t for t, _ in notes), str(notes[:2]))
        ok &= rec('D4 ★ 播报里的 `kind` 是 note（不是当成剧情事件）',
                  all(k == 'note' for _, k in notes), str(notes[:2]))

        # 没接上合规 → 原样（且不报错）
        # [EN] Not wired into compliance → pass through as-is (and no error)
        loop.compliance = None
        ok &= rec('D4 ★ 没接上合规 → 原样返回（不因为缺件把推演弄断）',
                  asyncio.run(loop._compliance_gate('正文原文')) == '正文原文', '')

        # 合规自己抛异常 → 不放行
        # [EN] Compliance itself throws → do not let through
        class Boom:
            async def check(self, *a, **k):
                raise RuntimeError('炸了')
        notes.clear()
        loop.compliance = Boom()
        got = asyncio.run(loop._compliance_gate('正文原文'))
        ok &= rec('D4 ★★ 合规**自己出错** → 也**不放行**（fail closed）',
                  got != '正文原文', got)
    finally:
        CA.ask = real
    return ok


if __name__ == '__main__':
    print('合规 Agent（CP1 / CP6）—— 验证', flush=True)
    ok = True
    try:
        head('A. 分级（C0/C1/白名单/检查点）')
        ok &= test_levels()
        head('B. LLM 复核（重点：不许 fail-open）')
        ok &= test_llm_review()
        head('C. 策略库（加载 + 热重载）')
        ok &= test_policy_dir()
        head('D. 接线（assemble / CP6 / CP1）')
        ok &= test_wiring()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'compliance_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1500:])
    sys.exit(0 if report['ok'] else 2)
