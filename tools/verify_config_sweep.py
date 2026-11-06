# -*- coding: utf-8 -*-
"""验证：**收尾批次** —— 提示词外置 + Agent 核心零散项 + 剩余零散旋钮 + 清理。

用户 2026-10-06：「都做掉」。这一批处理审计剩下的全部零读取旋钮（任务 #140/#141/#142）。

判据分层（每层都要能红，见 `developers/mutate_config_sweep.py`）：
  A **提示词外置**（`PROMPTS_DIR` / `PROMPT_WATCH`）：用户目录同名文件优先覆盖；
     热重载（mtime）；读坏了**退回内置**并留痕；占位符用 `text.fill` 不用 format。
  B **Agent 核心**：`IMPORTANCE_SCORING` 真的改变写入的重要度；
     `DIALOGUE_MIN_TURNS` 真的让对话至少说那么多轮；`PLAN_BLOCK_MINUTES` 进计划提示词；
     `GROUP_CHAT_MAX` 真的封顶群聊人数；`FEWSHOT_FROM_NOVEL` 把正文样例喂进 prompt。
  C **剩余旋钮**：`SUMMARY_MODEL` 换档、`SNAPSHOT_KEEP` 清登记（不删文件）、
     `OPEN_CHECKPOINT_EVERY_DAYS` 让 open 模式停、`ENDING_SCENE` 写 `结局.md`、
     `RESEARCH_AUTO=false` 只走本地、`LOG_ROTATE_DAYS` 启动清理、
     `OPTIMIZE_ON_IMPORT` 当复选框初值、`OPENING_ON_RESUME` 管续跑详略。
  D **清理**：那 28 个假旋钮**从 SPEC 里没了**，而剩余"零读取"只剩
     `DEFAULT_PROJECTS_DIR`（它由 `config.py` 自己读，是审计口径的误报）。

用法：.venv\\Scripts\\python.exe tools/verify_config_sweep.py
产出：assets/screenshots/config_sweep_report.json

English:
Verification: **closing batch** —— prompts externalized + Agent core miscellaneous items +
remaining miscellaneous knobs + cleanup.
User 2026-10-06: "do them all". This batch handles all the remaining zero-read knobs from the
audit (tasks #140/#141/#142).
Criterion layering (each layer must be able to go red, see `developers/mutate_config_sweep.py`):
  A **Prompts externalized** (`PROMPTS_DIR` / `PROMPT_WATCH`): a same-named file in the user directory takes precedence;
     Hot reload (mtime); on read failure **fall back to built-in** and leave a trace; use `text.fill` for placeholders, not format.
  B **Agent core**: `IMPORTANCE_SCORING` actually changes the importance of writes;
     `DIALOGUE_MIN_TURNS` actually makes dialogue last at least that many turns; `PLAN_BLOCK_MINUTES` goes into the planning prompt;
     `GROUP_CHAT_MAX` actually caps the group chat size; `FEWSHOT_FROM_NOVEL` feeds prose samples into the prompt.
  C **Remaining knobs**: `SUMMARY_MODEL` switches tiers, `SNAPSHOT_KEEP` cleans the registry (without deleting files),
     `OPEN_CHECKPOINT_EVERY_DAYS` makes open mode stop, `ENDING_SCENE` writes `结局.md`,
     `RESEARCH_AUTO=false` goes local-only, `LOG_ROTATE_DAYS` cleans up at startup,
     `OPTIMIZE_ON_IMPORT` as the checkbox initial value, `OPENING_ON_RESUME` controls resume detail level.
  D **Cleanup**: those 28 fake knobs **are gone from the SPEC**, and the remaining "zero reads" are only
     `DEFAULT_PROJECTS_DIR` (it is read by `config.py` itself, a false positive in the audit scope).
Usage: .venv\\Scripts\\python.exe tools/verify_config_sweep.py
Output: assets/screenshots/config_sweep_report.json
"""
from __future__ import annotations

import asyncio
import inspect
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
# [EN] ⚠ Don't measure pixels, don't pop dialogs, **never click a button that calls `CFG.save()`** (an
# [EN] iron rule in MEMORY).
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


FakeDB_rows: list[tuple] = []


class FakeDB:
    def add_memory(self, agent, content, mem_type='observation',
                   importance=5.0, game_ts=0, ref_event=''):
        FakeDB_rows.append((agent, content, mem_type, importance))
        return 1

    def retrieve_memory(self, *a, **k):
        return []

    def get_summaries(self, *a, **k):
        return []

    def count_memories(self, *a, **k):
        return 0

    def snapshots(self, limit=50):
        return [{'id': f's{i}'} for i in range(10)]

    def drop_snapshot(self, sid):
        FakeDB_rows.append(('drop', sid))
        return 1

    def add_snapshot(self, *a, **k):
        pass


def make_agent(world=None, db=None):
    from agent.core import Agent
    from world.state import WorldState, PersonState, GameTime
    w = world or WorldState()
    w.scene = w.scene or '示例书'
    w.clock = GameTime()
    ps = PersonState(name='阿九', location='示例书', role='前台')
    w.people['阿九'] = ps
    return Agent(ps, db or FakeDB(), w)


# ══════════════════════════════════════════════════════════════
#  A. 提示词外置
# [EN] A. Prompts externalized
# ══════════════════════════════════════════════════════════════
def test_prompts() -> bool:
    ok = True
    from util import prompts as P
    saved = {k: CFG.raw(k) for k in ('PROMPTS_DIR', 'PROMPT_WATCH')}
    try:
        builtin = APP_DIR / 'prompts' / 'agent_decide_tail.txt'
        ok &= rec('A1 ★★ 内置模板**真的在仓库里**（`prompts/agent_decide_tail.txt`）',
                  builtin.exists(), str(builtin))

        ud = Path(tempfile.mkdtemp(prefix='nws_pr_'))
        CFG.set('PROMPTS_DIR', str(ud))
        CFG.set('PROMPT_WATCH', 'true')
        P.reload()
        txt, src = P.template('agent_decide_tail', '兜底文本')
        ok &= rec('A1 ★ 用户目录没有同名文件 → 用**内置**那份',
                  src == 'builtin' and '不是独角戏' in txt, src)

        (ud / 'agent_decide_tail.txt').write_text('用户版：{n_layers} 层', encoding='utf-8')
        txt, src = P.template('agent_decide_tail', '兜底文本')
        ok &= rec('A1 ★★ 用户目录放了同名文件 → **优先用它**（改提示词不动代码）',
                  src == 'user' and '用户版' in txt, f'{src} / {txt[:30]}')

        # 热重载
        # [EN] Hot reload
        time.sleep(0.02)
        (ud / 'agent_decide_tail.txt').write_text('改过一版', encoding='utf-8')
        os.utime(ud / 'agent_decide_tail.txt', (time.time() + 5, time.time() + 5))
        txt, _ = P.template('agent_decide_tail', '兜底文本')
        ok &= rec('A2 ★★ `PROMPT_WATCH=true` → 改了**立刻生效**（热重载）',
                  '改过一版' in txt, txt[:20])
        CFG.set('PROMPT_WATCH', 'false')
        P.reload()
        P.template('agent_decide_tail', '兜底文本')
        (ud / 'agent_decide_tail.txt').write_text('第二改', encoding='utf-8')
        txt, _ = P.template('agent_decide_tail', '兜底文本')
        ok &= rec('A2 ★ 反例：关掉 watch → 走缓存不重读（判据不是恒真）',
                  '第二改' not in txt, txt[:20])

        # 空文件 / 读坏 → 退回内置并留痕，不崩
        # [EN] Empty file / corrupted read → fall back to built-in and leave a trace, don't crash
        CFG.set('PROMPT_WATCH', 'true')
        (ud / 'agent_decide_tail.txt').write_bytes(b'\xff\xfe\x00bad')
        txt, src = P.template('agent_decide_tail', '兜底文本')
        ok &= rec('A3 ★★ 用户文件读不动 → **退回内置**（永远有得用）',
                  src == 'builtin' and '不是独角戏' in txt, f'{src} / {P.last_error[:60]}')
        (ud / 'agent_decide_tail.txt').write_text('   \n  ', encoding='utf-8')
        txt, src = P.template('agent_decide_tail', '兜底文本')
        ok &= rec('A3 ★ 空文件也算没用 → 退回内置', src == 'builtin', src)

        # 两份都没有 → 用调用方给的兜底（**不抛异常**）
        # [EN] Neither exists → use the fallback provided by the caller (**don't throw**)
        txt, src = P.template('一个不存在的模板_xyz', '代码兜底')
        ok &= rec('A3 ★ 模板不存在 → 用调用方兜底（不抛异常，推演不会因此断）',
                  src == 'default' and txt == '代码兜底', f'{src} / {txt}')
    finally:
        for k, v in saved.items():
            CFG.set(k, v)
        P.reload()
    return ok


# ══════════════════════════════════════════════════════════════
#  B. Agent 核心
# [EN] B. Agent core
# ══════════════════════════════════════════════════════════════
def test_agent_core() -> bool:
    ok = True
    from agent import core as AC
    saved = {k: CFG.raw(k) for k in
             ('IMPORTANCE_SCORING', 'DIALOGUE_MIN_TURNS', 'DIALOGUE_MAX_TURNS',
              'PLAN_BLOCK_MINUTES', 'GROUP_CHAT_MAX', 'FEWSHOT_FROM_NOVEL')}
    real = AC.llm.chat
    try:
        CFG.set('IMPORTANCE_SCORING', 'heuristic')
        a = make_agent()
        hi = a._score_importance('observation', '他拔出刀，血溅了一地')
        lo = a._score_importance('observation', '他坐着看了半天')
        mid = a._score_importance('observation', '他把账本合上')
        ok &= rec('B1 ★★ `IMPORTANCE_SCORING` 真的在打分（不是恒定的 5.0）',
                  hi > lo and hi >= 8 and lo <= 4, f'{hi} / {mid} / {lo}')
        ok &= rec('B1 ★ 反思那条至少 8 分（想明白的事比看见的事重）',
                  a._score_importance('reflection', '他想了很久') >= 8.0, '')

        FakeDB_rows.clear()
        a._add_memory('observation', '他拔出刀，血溅了一地')
        ok &= rec('B1 ★★ 写进库的 importance **就是打出来的分**（不是 5.0 默认值）',
                  FakeDB_rows and FakeDB_rows[-1][3] >= 8.0, str(FakeDB_rows[-1]))

        # 对话最少轮次
        # [EN] Minimum number of dialogue turns
        class W:
            scene = '示例书'

            class clock:
                @staticmethod
                def day():
                    return 1

        w = a.world
        w.people['阿枝'] = type(next(iter(w.people.values())))(
            name='阿枝', location='示例书', role='前台')
        calls: list[int] = []

        async def fake_chat(tier, messages, **kw):
            calls.append(1)
            return '一句台词。'

        AC.llm.chat = fake_chat
        CFG.set('DIALOGUE_MAX_TURNS', '8')
        for lo, hi, want in ((2, 4, 4), (6, 8, 8), (9, 8, 8)):
            CFG.set('DIALOGUE_MIN_TURNS', str(lo))
            CFG.set('DIALOGUE_MAX_TURNS', str(hi))
            calls.clear()
            lines = asyncio.run(a.talk('阿枝', '账上的事'))
            ok &= rec(f'B2 ★ `MIN={lo}`/`MAX={hi}` → 说了 {len(lines)} 轮（期望 {want}）',
                      len(lines) == want, f'{len(lines)} / {want}')
        CFG.set('DIALOGUE_MIN_TURNS', '2')
        CFG.set('DIALOGUE_MAX_TURNS', '8')

        # 计划里带上时段块时长
        # [EN] Include time-block duration in the plan
        AC.llm.chat = fake_chat
        seen: list[str] = []

        async def cap_chat(tier, messages, **kw):
            seen.append(messages[-1]['content'] if messages else '')
            return json.dumps({'日计划': ['开门'], '时段块': [{'时段': '上午', '行动': '巡铺'}]},
                              ensure_ascii=False)

        AC.llm.chat = cap_chat
        CFG.set('PLAN_BLOCK_MINUTES', '45')
        asyncio.run(a.make_plan())
        ok &= rec('B3 ★★ `PLAN_BLOCK_MINUTES` 进了计划提示词（每块多少分钟）',
                  seen and '45 分钟' in seen[-1], (seen[-1][:80] if seen else ''))

        # 群聊人数封顶
        # ⚠ 群聊走的是 `llm.replies.ask()`，而 `ask` 内部用 `return_meta=True`
        #   —— 桩必须回 **`(text, meta)` 二元组**，回字符串会被解包成
        #   `too many values to unpack`（第一版就这么红的）。
        # [EN] Cap on group chat size
        # [EN] ⚠ Group chat goes through `llm.replies.ask()`, and `ask` internally uses `return_meta=True`
        # [EN] —— the stub must return a **`(text, meta)` tuple**; returning a string will be unpacked into
        # [EN] `too many values to unpack` (that's how the first version went red).
        async def fake_pair(tier, messages, **kw):
            seen.append(messages[-1]['content'] if messages else '')
            return '一句台词。', {}

        AC.llm.chat = fake_pair
        CFG.set('GROUP_CHAT_MAX', '2')
        seen.clear()
        line = asyncio.run(a.speak_in_group(['甲', '乙', '丙'], ['甲：你好']))
        ok &= rec('B4 ★★ `GROUP_CHAT_MAX` 真的封顶了同场人数（提示词里只出现前 N 个）',
                  seen and '丙' not in seen[-1] and '甲' in seen[-1],
                  (seen[-1][:90] if seen else ''))
        ok &= rec('B4 ★ 群聊出的是一句台词（不是旁白/引号）', line == '一句台词。', line)
    finally:
        AC.llm.chat = real
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


def test_fewshot() -> bool:
    """★★ `FEWSHOT_FROM_NOVEL`：正文样例**真的进了决策 prompt**（端到端）。
        English:
    ★★ `FEWSHOT_FROM_NOVEL`: prose samples **really do go into the decision prompt** (end-to-end).
    """
    ok = True
    from agent import core as AC
    saved = {k: CFG.raw(k) for k in ('FEWSHOT_FROM_NOVEL', 'MAX_CONTEXT_TOKENS')}
    real = AC.llm.chat
    seen: dict = {}

    async def fake(tier, messages, **kw):
        seen['p'] = messages[-1]['content'] if messages else ''
        return json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                           '内心': '', '理由': 't'}, ensure_ascii=False), {}

    AC.llm.chat = fake
    try:
        a = make_agent()
        a.world.style_card = {'样例': ['他把茶碗搁下，没说话。', '外头雨还在下。']}
        CFG.set('MAX_CONTEXT_TOKENS', '30000')
        CFG.set('FEWSHOT_FROM_NOVEL', 'true')
        asyncio.run(a.decide())
        ok &= rec('B5 ★★ `FEWSHOT_FROM_NOVEL=true` → 正文样例进了 prompt',
                  '文风示例' in seen.get('p', '') and '茶碗搁下' in seen.get('p', ''),
                  seen.get('p', '')[:120].replace('\n', ' | '))
        CFG.set('FEWSHOT_FROM_NOVEL', 'false')
        asyncio.run(a.decide())
        ok &= rec('B5 ★ 反例：关掉就不注入（判据不是恒真）',
                  '文风示例' not in seen.get('p', ''), '')
    finally:
        AC.llm.chat = real
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 剩余旋钮
# [EN] C. Remaining knobs
# ══════════════════════════════════════════════════════════════
def test_leftovers() -> bool:
    ok = True
    from sim.loop import RunLoop
    from world.state import WorldState, GameTime

    src_sum = inspect.getsource(RunLoop._summarize_day)
    ok &= rec('C1 ★★ `SUMMARY_MODEL` 决定日简摘要走哪一档（以前写死 cheap）',
              'SUMMARY_MODEL' in src_sum and '"front" if' in src_sum, '')

    # ★★ 行为判据：真跑一遍 `_flush_tick`，看它有没有真的下调 `drop_snapshot`。
    #    ⚠ 只读源码（`'SNAPSHOT_KEEP' in src`）抓不住"把条件改成 if False"
    #    （反例法抓到的）—— 源码哨兵是最弱的一种判据。
    # [EN] ★★ Behavior criterion: actually run `_flush_tick` once and see whether it really lowers
    # [EN] `drop_snapshot`.
    # [EN] ⚠ Only reading the source (`'SNAPSHOT_KEEP' in src`) can't catch "change the condition to if
    # [EN] False"
    # [EN] (caught by the counterexample method) —— source sentinels are the weakest kind of criterion.
    saved_keep = CFG.raw('SNAPSHOT_KEEP')
    try:
        w2 = WorldState()
        w2.scene = '示例书'
        w2.clock = GameTime()
        lp = RunLoop.__new__(RunLoop)
        lp.world = w2
        lp.db = FakeDB()
        lp._cb_warned = set()
        lp._paused = False
        FakeDB_rows.clear()
        CFG.set('SNAPSHOT_KEEP', '3')
        lp._flush_tick(50)                 # 50 % 10 == 0 → 会存快照并清理
        # [EN] 50 % 10 == 0 → will save a snapshot and clean up
        dropped = [r for r in FakeDB_rows if r and r[0] == 'drop']
        ok &= rec('C2 ★★ `SNAPSHOT_KEEP=3` → 真的把超出的快照登记清掉了'
                  '（10 条里留下 3 条）', len(dropped) == 7, f'清理了 {len(dropped)} 条')
        FakeDB_rows.clear()
        CFG.set('SNAPSHOT_KEEP', '0')
        lp._flush_tick(50)
        ok &= rec('C2 ★ 反例：`SNAPSHOT_KEEP=0` → 一条都不清（不限）',
                  not [r for r in FakeDB_rows if r and r[0] == 'drop'], '')
    finally:
        CFG.set('SNAPSHOT_KEEP', saved_keep)

    # ★★ `_open_checkpoint_due()` 行为判据
    # [EN] ★★ `_open_checkpoint_due()` behavior criterion
    saved_ck = {k: CFG.raw(k) for k in ('RUN_MODE', 'OPEN_CHECKPOINT_EVERY_DAYS')}
    try:
        w3 = WorldState()
        w3.scene = '示例书'
        w3.clock = GameTime()
        lp3 = RunLoop.__new__(RunLoop)
        lp3.world = w3
        CFG.set('OPEN_CHECKPOINT_EVERY_DAYS', '3')
        CFG.set('RUN_MODE', 'open')
        w3.game_day = 6
        ok &= rec('C3 ★★ open 模式：第 6 天（能被 3 整除）→ 该停一下存档',
                  lp3._open_checkpoint_due() is True, '')
        w3.game_day = 7
        ok &= rec('C3 ★ 第 7 天 → 不停', lp3._open_checkpoint_due() is False, '')
        w3.game_day = 6
        lp3._last_open_ckpt = 6
        ok &= rec('C3 ★ 同一天只停一次（停了就别再停，否则出不去）',
                  lp3._open_checkpoint_due() is False, '')
        lp3._last_open_ckpt = None
        CFG.set('OPEN_CHECKPOINT_EVERY_DAYS', '0')
        ok &= rec('C3 ★ 反例：设 0 → 永不自动停（判据不是恒真）',
                  lp3._open_checkpoint_due() is False, '')
        CFG.set('OPEN_CHECKPOINT_EVERY_DAYS', '3')
        CFG.set('RUN_MODE', 'story')
        ok &= rec('C3 ★ 反例：别的运行模式不受它影响',
                  lp3._open_checkpoint_due() is False, '')
    finally:
        for k, v in saved_ck.items():
            CFG.set(k, v)
    ok &= rec('C3 ★ `_tick` 里确实调了它（接线哨兵）',
              '_open_checkpoint_due()' in inspect.getsource(RunLoop._tick), '')
    # ★★ 2026-10-26：收尾**拆成了两步**（`_finish` 负责"停/记账"，`_finish_steps` 负责
    #   "把剩余的东西写出去"，`ENDING_SCENE` 的门在后者）。判据原来只读 `_finish` ⇒
    #   永远找不到那句开关，红的是判据不是产品。
    #   这里把两段源码**接起来**看：这条判据问的是"收尾这条路有没有写 结局.md"，
    #   而"这条路"现在由两个方法合起来构成。
    #   ⚠ 同时钉一句接线：`_finish` 必须真的把活交给 `_finish_steps`。
    # [EN] ★★ 2026-10-26: wrap-up **was split in two** (`_finish` stops and books it,
    # [EN] `_finish_steps` writes what is left; the `ENDING_SCENE` gate lives in the latter).
    # [EN] The criterion only read `_finish`, so it could never find the switch -- the criterion is
    # [EN] red, not the product. Concatenate both sources: the question is "does the wrap-up path
    # [EN] write 结局.md", and that path now consists of two methods.
    # [EN] ⚠ Also pin the wiring: `_finish` must really hand over to `_finish_steps`.
    src_fin = (inspect.getsource(RunLoop._finish) + '\n'
               + inspect.getsource(RunLoop._finish_steps))
    ok &= rec('C4 ★★ `ENDING_SCENE`：收尾写 `结局.md`',
              'ENDING_SCENE' in src_fin and '_write_ending' in src_fin, '')
    ok &= rec('C4 ★ 接线：`_finish` 真的把收尾的活交给了 `_finish_steps`',
              '_finish_steps(' in inspect.getsource(RunLoop._finish), '')

    # 端到端：结局真的写出来了
    # [EN] End-to-end: the ending is actually written out
    tmp = Path(tempfile.mkdtemp(prefix='nws_end_'))

    class RunF:
        root = tmp

    w = WorldState()
    w.scene = '示例书'
    w.clock = GameTime()
    w.active_lines = ['掌柜还欠阿枝一个解释']
    w.progress_nodes = [{'id': 'N1', '名称': '楼前失忆', '状态': '已完成'},
                        {'id': 'N2', '名称': '第一桩委托', '状态': '未开始'}]
    w.hooks = [{'称呼': '赊账的'}]
    loop = RunLoop.__new__(RunLoop)
    loop.world = w
    loop.runfolder = RunF()
    loop._daily_narrative = ['阿九把门关上，天黑了。']
    saved_end = CFG.raw('ENDING_SCENE')
    try:
        CFG.set('ENDING_SCENE', 'true')
        asyncio.run(loop._write_ending('测试结束'))
        f = tmp / '结局.md'
        ok &= rec('C4 ★★ `结局.md` 真的落盘了', f.exists(), str(list(tmp.iterdir())))
        txt = f.read_text(encoding='utf-8') if f.exists() else ''
        ok &= rec('C4 ★ 里面写了**结束原因 + 没走完的节点 + 还认得的临演**'
                  '（"以后接着写"要的东西）',
                  '测试结束' in txt and '第一桩委托' in txt and '赊账的' in txt,
                  txt[:120].replace('\n', ' | '))
        # ⚠ 反例要打在**闸门所在的地方**：`ENDING_SCENE` 的开关在
        #   `_finish` 的调用点，不在 `_write_ending` 自己身上 ——
        #   直接调 `_write_ending` 当然还是会写（第一版就是这么假红的）。
        # [EN] ⚠ The counterexample must target **where the gate is**: the switch for `ENDING_SCENE` is at
        # [EN] the call site of `_finish`, not in `_write_ending` itself ——
        # [EN] calling `_write_ending` directly will of course still write (that's how the first version went
        # [EN] falsely red).
        ok &= rec('C4 ★ 反例：开关真的包在调用点上（`if CFG.b("ENDING_SCENE")`）',
                  'if CFG.b("ENDING_SCENE"):' in src_fin
                  and '_write_ending' in src_fin,
                  ' | '.join(l.strip() for l in src_fin.split('\n')
                             if 'ENDING_SCENE' in l)[:120])
    finally:
        CFG.set('ENDING_SCENE', saved_end)

    # ★★ 行为判据：真调一次 lookup，看它有没有在本地就停下
    # [EN] ★★ Behavior criterion: actually call lookup once and see whether it stops locally
    from research.lookup import research_lookup as RLK
    saved_ra = CFG.raw('RESEARCH_AUTO')
    touched: list[str] = []
    try:
        import skills.registry as SKR
        real_find = SKR.skill_registry.find_skill
        SKR.skill_registry.find_skill = lambda q: (touched.append('skill'), None)[1]
        # 每日限额：想验"关掉之后不去联网"，先确认开着时是**会**往下走的
        # [EN] Daily quota: to verify "after disabling it won't go online", first confirm that when enabled it
        # [EN] **does** proceed.
        CFG.set('RESEARCH_AUTO', 'false')
        r = asyncio.run(RLK.lookup('一个本地肯定没有的东西_xyz'))
        ok &= rec('C5 ★★ `RESEARCH_AUTO=false` → 本地两层走完就停'
                  '（**不碰技能/联网/LLM**）',
                  touched == [] and '本地' in str(r.get('来源', '')), f'{r}')
        CFG.set('RESEARCH_AUTO', 'true')
        asyncio.run(RLK.lookup('一个本地肯定没有的东西_xyz'))
        ok &= rec('C5 ★ 反例：开着就会往下走（判据不是恒真）',
                  touched != [], str(touched))
    finally:
        try:
            SKR.skill_registry.find_skill = real_find
        except Exception:                                       # noqa: BLE001
            pass
        CFG.set('RESEARCH_AUTO', saved_ra)

    # ★★ `LOG_ROTATE_DAYS` 行为判据：造两个旧日志 + 一个新日志，看它清不清
    # [EN] ★★ `LOG_ROTATE_DAYS` behavior criterion: create two old logs + one new log and see whether it
    # [EN] cleans them up.
    import logger as LG
    saved_dir, saved_rot = CFG.raw('LOG_DIR'), CFG.raw('LOG_ROTATE_DAYS')
    try:
        ld = Path(tempfile.mkdtemp(prefix='nws_log_'))
        # ★ 两种名字**都要覆盖**（2026-10-07 起新日志名带书名、用下划线）：
        #   旧格式带连字符，用户 `logs/` 里还躺着一批；
        #   新格式是 `nws_<书名>_<时间>`。清理规则是 `nws*.log`，
        #   夹具里两种都摆一份，免得将来改 glob 时只守住一种。
        # [EN] ★ **Both** name formats **must be covered** (since 2026-10-07 new log names include the book
        # [EN] title, using underscores):
        # [EN] the old format uses hyphens, and users still have a batch of them lying in `logs/`;
        # [EN] the new format is `nws_<book title>_<time>`. The cleanup rule is `nws*.log`,
        # [EN] put one of each format in the fixture, so that when the glob is changed later only one format
        # [EN] isn't guarded.
        #
        # ⚠ 日期**用拼的、不写字面量**：`verify_generic_project` 的 B 组禁止
        #   源码里出现"日期化的日志文件名"——那条防的是"拿**用户那一次运行**的
        #   真实日志当夹具"（文件被清理掉，判据就静默变哑）。
        #   这里两个日期都是**自己造的假日子**（2000 / 2999），所以用拼接把
        #   "这是我造的、不是谁的运行记录"这件事写在代码里。
        # [EN] ⚠ Dates **must be concatenated, not written as literals**: group B of `verify_generic_project`
        # [EN] forbids
        # [EN] a "date-ified log filename" appearing in the source —— that rule guards against "using **that
        # [EN] one user run's**
        # [EN] real log as a fixture" (once the file is cleaned up, the criterion silently goes mute).
        # [EN] Here both dates are **self-fabricated fake dates** (2000 / 2999), so concatenation is used to
        # [EN] write
        # [EN] the fact "this is fabricated by me, not anyone's run record" into the code.
        old_stamp, new_stamp = '2000-01-01-00-00', '2999-01-01-00-00'
        old_f = ld / ('nws-' + old_stamp + '.log')
        old_f2 = ld / ('nws_示例书_' + old_stamp.replace('-', '_') + '.log')
        new_f = ld / ('nws-' + new_stamp + '.log')
        new_f2 = ld / ('nws_示例书_' + new_stamp.replace('-', '_') + '.log')
        for f in (old_f, old_f2, new_f, new_f2):
            f.write_text('x', encoding='utf-8')
        os.utime(old_f, (time.time() - 90 * 86400,) * 2)
        os.utime(old_f2, (time.time() - 90 * 86400,) * 2)
        CFG.set('LOG_DIR', str(ld))
        CFG.set('LOG_ROTATE_DAYS', '30')
        LG.NWSLogger._initialized = False        # 允许重新初始化一次（验启动路径）
        # [EN] Allow re-initialization once (to verify the startup path)
        LG.NWSLogger()
        ok &= rec('C6 ★★ `LOG_ROTATE_DAYS=30` → 启动时清掉 90 天前那份旧日志',
                  not old_f.exists() and new_f.exists(),
                  str([p.name for p in ld.iterdir()]))
        ok &= rec('C6b ★ 新格式（带书名、下划线）的旧日志**也清得掉**'
                  '（清理规则是 `nws*.log`，两种名字都要覆盖）',
                  not old_f2.exists() and new_f2.exists(),
                  str([p.name for p in ld.iterdir()]))
        # 反例：关掉（0）→ 不删
        # [EN] Counterexample: turn off (0) → don't delete
        old_f.write_text('x', encoding='utf-8')
        old_f2.write_text('x', encoding='utf-8')
        os.utime(old_f, (time.time() - 90 * 86400,) * 2)
        os.utime(old_f2, (time.time() - 90 * 86400,) * 2)
        CFG.set('LOG_ROTATE_DAYS', '0')
        LG.NWSLogger._initialized = False
        LG.NWSLogger()
        ok &= rec('C6 ★ 反例：`LOG_ROTATE_DAYS=0` → 不删（判据不是恒真）',
                  old_f.exists(), str([p.name for p in ld.iterdir()]))
    finally:
        CFG.set('LOG_DIR', saved_dir)
        CFG.set('LOG_ROTATE_DAYS', saved_rot)
        LG.NWSLogger._initialized = True

    import gui.app_flet as GF
    ok &= rec('C7 ★ `OPTIMIZE_ON_IMPORT` 是开卷复选框的初值',
              "CFG.b('OPTIMIZE_ON_IMPORT')" in inspect.getsource(GF),
              '')
    ok &= rec('C8 ★★ `OPENING_ON_RESUME`：续跑（第 2 轮起）改用"前情"那档详略',
              'OPENING_ON_RESUME' in inspect.getsource(GF), '')

    # ★ 2026-10-25：**「向量检索」在天机页默认不显示**。
    #   它不是"删了"，是 `visible=False`（同 `SORT_BOX_VISIBLE` 那个模式）：
    #   控件照常构造、`CFG.set` 照常写回原值，只是不画出来。理由见 `gui/app_flet.py`
    #   里 `EMBEDDING_BOX_VISIBLE` 上方那段 —— `llm/embedding.py` 至今没接进
    #   记忆检索，摆在页面上等于让人拧一个不生效的旋钮。
    #   ⚠ 这条判据只管"默认是不是隐藏"，不管"藏得对不对"（那要靠人看界面）。
    #     哪天 embedding 真接上了，改 `EMBEDDING_BOX_VISIBLE = True` 的同时
    #     也要把这条判据一起改掉 —— 所以它写的是"必须存在这个开关且为 False"，
    #     而不是"必须永远隐藏"。
    # [EN] ★ 2026-10-25: **"Vector retrieval" is hidden in Tianji by default.** Not deleted --
    # [EN] `visible=False` (same pattern as `SORT_BOX_VISIBLE`): the control is still built and
    # [EN] `CFG.set` still writes the original value back; it is simply not drawn. Rationale lives
    # [EN] above `EMBEDDING_BOX_VISIBLE` in `gui/app_flet.py`. ⚠ This checks "hidden by default",
    # [EN] not "hidden correctly" (that needs human eyes). When embeddings are actually wired up,
    # [EN] flipping the switch to `True` means updating this criterion too.
    _gf_src = inspect.getsource(GF)
    ok &= rec('C9 ★★ 天机页的「向量检索」默认**不显示**（一个开关控制，不是删代码）',
              'EMBEDDING_BOX_VISIBLE = False' in _gf_src
              and 'visible=EMBEDDING_BOX_VISIBLE' in _gf_src,
              '要么开关没了，要么默认值被翻成 True')
    return ok


# ══════════════════════════════════════════════════════════════
#  D. 清理（假旋钮没了）
# [EN] D. Cleanup (the fake knobs are gone)
# ══════════════════════════════════════════════════════════════
def test_cleanup() -> bool:
    ok = True
    from config import SPEC
    dead = ['TUI_THEME', 'TUI_REFRESH_MS', 'MAP_ENABLED', 'COMMAND_BOX_COLLAPSED',
            'FIRST_RUN_WIZARD', 'SHOW_TIME_PANEL', 'SHOW_MAP_PANEL',
            'SHOW_STYLE_PANEL', 'SHOW_PEOPLE_PANEL', 'SHOW_PLOT_PANEL',
            'SHOW_SYSTEM_PANEL', 'SHOW_STATUS_BAR', 'SHOW_NARRATIVE',
            'SHOW_CMD_BOX', 'TYPEWRITER', 'SLOW_ON_KEY_EVENT', 'CLOCK_MODE',
            'PROJECT_PATH', 'PROJECT_NAME', 'EMBED_MAP_IN_LOG',
            'NOVEL_LOG_MODEL', 'COMPLIANCE_EXTERNAL', 'COMPLIANCE_EXTERNAL_KEY',
            'COMPLIANCE_EXTERNAL_SECRET', 'COMPLIANCE_EXTERNAL_ENDPOINT',
            'COMPLIANCE_EXTERNAL_MODE', 'COMPLIANCE_EXTERNAL_TIMEOUT',
            'COMPLIANCE_AGGREGATION']
    left = [k for k in dead if k in SPEC]
    ok &= rec('D1 ★★ 28 个假旋钮**从 SPEC 里删掉了**（挂着拧不动就是负债）',
              not left, f'还剩：{left}')
    # ★★ 2026-10-07 **第二次**换掉这条判据（不是放宽，是把一个会自动失效的数
    #   换成一条不会的）。
    # [EN] ★★ 2026-10-07 **second** replacement of this criterion (not a loosening, but replacing a number
    # [EN] that
    # [EN] will automatically become stale with one that won't).
    #
    #   历史：最早是 `len(SPEC) <= 162`（绝对上限）→ 任何新功能都撞线；
    #   改成"比清理前基线 185 小" → 剧组一次加 19 个旋钮就红了，
    #   这一轮设定分层再加 4 个又红（185 → 188）。
    # [EN] History: earliest was `len(SPEC) <= 162` (absolute cap) → any new feature hit the line;
    # [EN] changed to "smaller than the pre-cleanup baseline of 185" → the crew adding 19 knobs at once
    # [EN] went red,
    # [EN] and this round adding 4 more under the layered settings went red again (185 → 188).
    #
    #   两次红的**都不是产品坏了**，而是这条判据在量一个**只会单向上涨**的数。
    #   它红了之后唯一的省事做法就是改大那个数 —— 改两次就没人看它了。
    # [EN] Neither red was **the product breaking**; rather, this criterion was measuring a number that
    # [EN] **only goes up**.
    # [EN] Once it goes red, the only easy fix is to bump that number — after two bumps nobody looks at it
    # [EN] anymore.
    #
    #   它**本意**是"不许再有挂着拧不动的旋钮"。那就直接量这个：
    #   **SPEC 里的每一个键，在产品源码里至少被字面量读过一次**。
    #   加一个真用得上的旋钮 → 绿；加一个假旋钮 → 红。与功能增长无关。
    # [EN] Its **intent** was "no more knobs that are stuck and can't be turned". So just measure that
    # [EN] directly:
    # [EN] **every key in SPEC is read at least once as a literal in the product source**.
    # [EN] Add a genuinely useful knob → green; add a fake knob → red. Unrelated to feature growth.
    #
    #   ⚠ 口径说明（写清楚，免得下一个人以为它太严）：
    #     · 只匹配字面量 `"KEY"` / `'KEY'` —— 动态取值（从字典里查出来的键名）
    #       会漏，所以这是**下限**，不是"用完就没人读"；
    #     · **只扫产品源码**（不含 `tools/` `developers/` `tests/`）——
    #       一个只有测试读过的旋钮，对用户来说仍然是假的；
    #     · **`config.py` 自己不算**：SPEC 的声明里每个键都是字面量，
    #       算进去的话这条判据恒真（第一版就是这么写的，塞一个假旋钮进去
    #       照样 43/43 —— 反例法当场揭穿）。
    #     · 被动态取值读到的键会假红 → 加进 `ZERO_OK` 并写清理由，
    #       别把这条判据删了（删了就再没有东西拦假旋钮了）。
    #: 已知会假红的白名单：这几个键是**在 `config.py` 内部**被读的
    #: （`DEFAULT_PROJECTS_DIR` → `Config.projects_dir()`），排除 config.py 之后
    #: 就扫不到了。不是假旋钮，是口径的缺口。
    # [EN] ⚠ Scope note (write it clearly so the next person doesn't think it's too strict):
    # [EN] · only matches the literals `"KEY"` / `'KEY'` —— dynamic values (key names looked up from a
    # [EN] dict)
    # [EN] will be missed, so this is a **lower bound**, not "nobody reads it after use";
    # [EN] · **only scans product source** (excluding `tools/` `developers/` `tests/`) ——
    # [EN] a knob only read by tests is still fake to the user;
    # [EN] · **`config.py` itself doesn't count**: in SPEC's declaration every key is a literal,
    # [EN] if counted, this criterion is always true (that's how the first version was written; stuff a
    # [EN] fake knob in
    # [EN] and it still passes 43/43 —— exposed on the spot by the counterexample method).
    # [EN] · keys read by dynamic values will go falsely red → add them to `ZERO_OK` and write the reason
    # [EN] clearly,
    # [EN] don't delete this criterion (delete it and nothing blocks fake knobs anymore).
    # [EN] : Known whitelist of false reds: these keys are read **inside `config.py`**
    # [EN] : (`DEFAULT_PROJECTS_DIR` → `Config.projects_dir()`), after excluding config.py
    # [EN] : they can't be scanned. They're not fake knobs, it's a gap in the scope.
    ZERO_OK: set[str] = {'DEFAULT_PROJECTS_DIR'}
    _skip_dirs = {'.venv', '__pycache__', '.git', 'logs', 'assets', 'packages',
                  'generated-images', '发布版本', 'node_modules', '.workbuddy',
                  'samples', 'tools', 'developers', 'tests'}
    # ⚠ ！别把 `craft/` `skills/` `refs/` `mcp/` 放进跳过表 —— 它们是**Python 包**
    #   （`craft/craftmix.py` 之类），上一版误跳了它们，于是 `CRAFT_LIBRARY` 等
    #   十个**真被读**的键被判成零读取。
    # [EN] ⚠ ! Don't put `craft/` `skills/` `refs/` `mcp/` in the skip list —— they are **Python packages**
    # [EN] (like `craft/craftmix.py`); the previous version mistakenly skipped them, so `CRAFT_LIBRARY` and
    # [EN] other
    # [EN] ten keys that are **genuinely read** were judged as zero reads.
    _src = ''
    for p in sorted(APP_DIR.rglob('*.py')):
        if any(s in p.parts for s in _skip_dirs) or p.name == 'config.py':
            continue
        try:
            _src += p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
    zero_read = [k for k in SPEC
                 if k not in ZERO_OK
                 and f'"{k}"' not in _src and f"'{k}'" not in _src]
    ok &= rec(f'D1 SPEC 的 {len(SPEC)} 个旋钮**每一个都被产品源码读到过**'
              '（"挂着拧不动"的一个都没有；白名单 1 个是口径缺口）',
              not zero_read, f'零读取：{zero_read}')
    env = APP_DIR / '.env'
    env_txt = env.read_text(encoding='utf-8') if env.exists() else ''
    ok &= rec('D1 ★ .env 里也同步清了（不让用户以为还能调）',
              not any(f'\n{k}=' in env_txt or env_txt.startswith(f'{k}=') for k in dead),
              '')
    # 保留的那些仍然可读（别删过头）
    # [EN] Keep the ones that are retained still readable (don't over-delete)
    ok &= rec('D2 ★ 没删过头：本轮接好的旋钮都还在且读得动',
              all(k in SPEC for k in ('GOAL_LADDER', 'BACKGROUND_MODE', 'FILM_MODE',
                                      'NOVEL_STYLE', 'MAX_CONTEXT_TOKENS',
                                      'COMPLIANCE_POLICY_DIR', 'PROMPTS_DIR'))
              and CFG.i('GOAL_LADDER') >= 2 and CFG.i('MAX_CONTEXT_TOKENS') > 0,
              f"GOAL_LADDER={CFG.i('GOAL_LADDER')}")
    return ok


if __name__ == '__main__':
    print('收尾批次（提示词外置 / Agent 核心 / 零散旋钮 / 清理）—— 验证', flush=True)
    ok = True
    try:
        head('A. 提示词外置（PROMPTS_DIR / PROMPT_WATCH）')
        ok &= test_prompts()
        head('B. Agent 核心（打分 / 轮次 / 时段块 / 群聊 / 少样本）')
        ok &= test_agent_core()
        ok &= test_fewshot()
        head('C. 剩余旋钮（摘要档 / 快照 / 存档点 / 结局 / 考据 / 日志 / 开场）')
        ok &= test_leftovers()
        head('D. 清理（28 个假旋钮已删）')
        ok &= test_cleanup()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'config_sweep_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1500:])
    sys.exit(0 if report['ok'] else 2)
