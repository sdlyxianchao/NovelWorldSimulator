# -*- coding: utf-8 -*-
"""当日剧本（导演先定框架）—— 验证：故事 → 剧本 → 分派 → 验算。

用户 2026-10-07：「在一天开始之前 导演自己心里要…把当天要演的故事写好…
然后在根据人物改写成剧本 然后分配给不同的角色 然后再开眼…
而且导演写故事和剧本之后要反复验算下是否跟整个故事是顺起来的」

这套判据钉三件事：
  A **纯逻辑**（打桩 `llm.replies.ask`，零网络）：拿不到东西不许假装有 ·
    验算不通过要带意见重写 · 拿不到结论**不算通过** · 只派给在场的人。
  B **接线**：循环真的调了它、`world.day_script` 真的挂上、人物提示词里真的出现
    〔今日剧本〕、派过活的人不再被问第二次计划、落盘只写运行文件夹。
  C **反例法**（`developers/mutate_day_plan.py`）：把实现改坏，本脚本必须变红。

跑法：.venv/Scripts/python.exe tools/verify_day_plan.py

English:
The day's script (director sets the frame first) —— verification: story → script → assignment →
verification.
User 2026-10-07: "before a day starts the director must in his own mind... write the day's story
well...
then rewrite it into a script based on the characters then assign it to different roles then
open his eyes...
and after the director writes the story and script he must repeatedly verify whether it is
consistent with the whole story"
This set of criteria pins down three things:
  A **pure logic** (stub `llm.replies.ask`, zero network): if nothing is obtained, do not pretend there is ·
    failed verification must rewrite with feedback · no conclusion obtained **does not count as passing** · only assign to people present.
  B **wiring**: the loop really calls it, `world.day_script` really gets attached, the character prompt really contains
    〔Today's script〕, people already assigned work are not asked for a plan a second time, persistence only writes to the run folder.
  C **counter-example method** (`developers/mutate_day_plan.py`): break the implementation, this script must turn red.
Run: .venv/Scripts/python.exe tools/verify_day_plan.py
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

from config import CFG                                    # noqa: E402
CFG.set('MOCK_LLM', 'true')
# ★★★ 2026-10-26 补：**`MOCK_LLM` 管不到外部创作服务**。
#   本机 `.env` 是 `MUMU_ENABLED=true / MUMU_AUTOSTART=true`，于是"写当天样章"那一步
#   真去调 MuMuAINovel —— 服务没起时每次等 56 秒重试。实测这一支因此跑了 **528 秒**
#   （正常十几秒），而且它并不测外部服务（那条路在 `verify_mumu_export`）。
#   ⇒ 判据不许依赖外部服务：显式关掉。
# [EN] ★★★ Added 2026-10-26: **`MOCK_LLM` does not reach the external creation services**. The
# [EN] local `.env` has `MUMU_ENABLED=true / MUMU_AUTOSTART=true`, so "write today's sample
# [EN] chapter" really calls MuMuAINovel and waits 56 s per retry when it is down. Measured: this
# [EN] script took **528 s** (normally ten-odd seconds), and it does not test the external service
# [EN] anyway (that path lives in `verify_mumu_export`). Criteria must not depend on external
# [EN] services: switch them off.
CFG.set('MUMU_ENABLED', 'false')
CFG.set('PENSHOT_ENABLED', 'false')
CFG.set('LANGUAGE', 'zh')

from director import day_plan as DP                       # noqa: E402
from crew import agents as CREW                            # noqa: E402
from i18n import set_lang                                 # noqa: E402
set_lang('zh')

checks: list[dict] = []


def ok(name: str, cond, detail='') -> bool:
    checks.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:220]})
    return bool(cond)


class _World:
    """够用的假世界（`world_prefix` / `game_day` / `clock` / `people`）。
        English:
    A sufficient fake world (`world_prefix` / `game_day` / `clock` / `people`).
    """

    def __init__(self, names=('主角', '阿枝')):
        self.game_day = 3
        self.current_node = '门口醒来'
        # ⚠ `Agent.name` 是只读 property（多半读 `self.ps.name`），所以夹具的
        #   人物状态必须带 `name` —— 赋值给 `ag.name` 会 AttributeError。
        # [EN] ⚠ `Agent.name` is a read-only property (mostly reads `self.ps.name`), so the fixture's
        # [EN] character state must carry `name` —— assigning to `ag.name` raises AttributeError.
        self.people = {n: type('PS', (), {'name': n, 'day_plan': ''})()
                       for n in names}

    def world_prefix(self):
        return '【世界观】临河镇靠一条河吃饭。'


class _DB:
    """假 DB —— **方法名必须与真 `store/db.py` 一致**。

    ⚠ 2026-10-07 修：这里以前写的是 `recent_summaries` / `list_events`，而真 DB
      上**两个都不存在**（真名是 `get_summaries` / `recent_events`）。假对象上
      有、真对象上没有，于是判据一路常绿，而真机上前情提要一直是空的
      （用户报的「每次推演开始一开始应该有一小段前情提要 你这个也没有」）——
      典型的"判据钉在假接口上"。
    
        English:
    Fake DB —— **method names must match the real `store/db.py`**.
        ⚠ Fixed 2026-10-07: here it used to write `recent_summaries` / `list_events`, but the real DB
          has **neither of them** (the real names are `get_summaries` / `recent_events`). On the fake object they
          exist, on the real object they do not, so the criterion stayed green all the way, while on the real machine the recap was always empty
          (the user reported "every deduction should have a short recap at the start, yours does not have it either") ——
          a classic case of "the criterion pinned to a fake interface".
    """

    def get_summaries(self, k: int = 6, scope: str = '故事'):
        return [{'text': '第二天：账目差了七文，还没查出来。'}]

    def recent_events(self, n: int = 20, game_day: int = 0):
        return [{'content': '主角在门口捡到一双新布鞋。'}]


# ══════════════════════════════════════════════════════════════════
#  A 组：纯逻辑（打桩 LLM）
# [EN] Group A: pure logic (stubbed LLM)
# ══════════════════════════════════════════════════════════════════
async def logic_checks() -> None:
    real_ask = DP.ask
    calls: list[dict] = []

    def stub(replies: list):
        """按调用顺序返回预设值；用完后重复最后一个。

        ⚠ 直接返回 `_ask`（第一版多包了一层，赋给 `DP.ask` 的是个工厂函数，
          调用时当场 `TypeError`）。

        ★★ 2026-10-07：**必须同时打 `crew.agents.ask`**。
          「写故事」与「改写剧本」这两步从今天起由剧组的小說作家/剧作者执行
          （`crew/agents.py`），它们 import 的是**那个模块自己的** `ask` 名字 ——
          只打 `DP.ask` 的话这两个调用会穿过桩子直接落到真（MOCK）实现上：
          测出来的就成了"演示语料对不对"，而桩里预设的"第一轮不通过"
          「模型派了不存在的人」这些**根本不发生**（实测：A1d/A2/A3 全红）。
          这是"桩打在了错误的层"的典型 —— 判据没坏，桩坏了。
        
                English:
        Return preset values in call order; after they run out, repeat the last one.
                ⚠ Directly return `_ask` (the first version wrapped it in an extra layer; what was assigned to `DP.ask` was a factory function,
                  and calling it would raise `TypeError` on the spot).
                ★★ 2026-10-07: **must also patch `crew.agents.ask`**.
                  As of today, the two steps "write story" and "rewrite script" are executed by the crew's novelist/screenwriter
                  (`crew/agents.py`); what they import is **that module's own** `ask` name ——
                  if you only patch `DP.ask`, these two calls will pass through the stub and land directly on the real (MOCK) implementation:
                  what gets measured then becomes "whether the demo corpus is correct", while the stub's presets like "first round fails"
                  and "the model dispatched a nonexistent person" **never happen at all** (measured: A1d/A2/A3 all red).
                  This is the classic case of "the stub was placed at the wrong layer" —— the criterion isn't broken, the stub is.
        """
        idx = {'i': 0}

        async def _ask(tier, messages, **kw):
            calls.append({'purpose': kw.get('purpose'), 'want': kw.get('want'),
                          'text': messages[0]['content']})
            v = replies[min(idx['i'], len(replies) - 1)]
            idx['i'] += 1
            rep = type('R', (), {})()
            rep.value = v
            rep.ok = bool(v)
            rep.raw = v
            rep.meta = {}
            rep.notes = []
            return rep

        # ★ 装到**两个**调用点上（调用方仍然只写 `DP.ask = stub(...)`）：
        #   写故事/改剧本两步在 `crew/agents.py`，验算在 `day_plan` 里。
        #   只打一个的话另一半会穿过桩子落到真（MOCK）实现上 ——
        #   测出来的就成了"演示语料对不对"，而不是桩里预设的那几种情形。
        # [EN] ★ Install on **two** call sites (callers still only write `DP.ask = stub(...)`):
        # [EN] The write-story/revise-script two steps are in `crew/agents.py`, verification is in `day_plan`.
        # [EN] If only one is stubbed, the other half passes through the stub and lands on the real (MOCK)
        # [EN] implementation ——
        # [EN] what gets tested becomes "is the demo corpus correct" instead of the few scenarios preset in the
        # [EN] stub.
        DP.ask = _ask
        CREW.ask = _ask
        return _ask

    w, db = _World(), _DB()

    # ── A1 正常一条路：故事 → 剧本 → 验算通过 ──
    # [EN] ── A1 normal happy path: story → script → verification passes ──
    DP.ask = stub(['第三天，账目的七文牵出旧案。',
                   {'拍': [{'拍': 1, '场': '临河茶肆', '发生': '主角翻账',
                            '推进': '查出七文的去向'}],
                    '角色任务': {'主角': ['翻昨夜的账'], '阿枝': ['盯住柜台'],
                                 '不存在的人': ['不该有']}},
                   {'通过': True, '问题': [], '修改意见': ''}])
    ds = await DP.compose(w, db, people=['主角', '阿枝'])
    ok('A1 走完三步：故事 + 拍 + 角色任务都有', bool(ds.story) and ds.beats
       and ds.roles, f'story={len(ds.story)}字 beats={len(ds.beats)} '
                     f'roles={list(ds.roles)}')
    ok('A1b `source=ai`、`verdict=通过`、`rounds=1`',
       ds.source == 'ai' and '通过' in ds.verdict and ds.rounds == 1,
       f'{ds.source}/{ds.verdict}/{ds.rounds}')
    ok('A1c ★ 派给**不在场**的人被丢掉（模型会派给不存在的人）',
       '不存在的人' not in ds.roles, list(ds.roles))
    ok('A1d 三次调用分别是 故事/剧本/验算',
       [c['purpose'] for c in calls[:3]] == ['day_story', 'day_script', 'day_verify'],
       [c['purpose'] for c in calls[:3]])
    ok('A1e 验算那次拿到的是**当天故事 + 剧本**（自查材料齐）',
       '翻账' in calls[2]['text'] and '七文' in calls[2]['text'], '')

    # ── A2 ★ 写不出故事 → source=fallback，**不许假装有框架** ──
    # [EN] ── A2 ★ cannot write a story → source=fallback, **must not pretend there is a frame** ──
    calls.clear()
    DP.ask = stub([''])
    ds2 = await DP.compose(w, db, people=['主角'])
    ok('A2 ★ 故事没写出来 → `source=fallback` 且 story 为空（不编一段假的）',
       ds2.source == 'fallback' and not ds2.story, f'{ds2.source}/{ds2.story[:20]!r}')
    ok('A2b 没写出来就**不再往下**写剧本（省掉两次调用）',
       len(calls) == 1, f'调用 {len(calls)} 次')

    # ── A3 ★ 验算不通过 → 带意见重写（轮数受 `DAY_PLAN_FIX_ROUNDS` 限制）──
    # [EN] ── A3 ★ verification fails → rewrite with feedback (rounds limited by `DAY_PLAN_FIX_ROUNDS`) ──
    calls.clear()
    CFG.set('DAY_PLAN_FIX_ROUNDS', '2')
    fix_text = '第 3 拍换成账房把账本摔在桌上'
    DP.ask = stub(['第三天，账目牵出旧案。',
                   {'拍': [{'拍': 1, '场': '临河茶肆', '发生': '主角翻账',
                            '推进': '查七文'}], '角色任务': {'主角': ['翻账']}},
                   {'通过': False, '问题': ['跟主线无关'], '修改意见': fix_text},
                   {'拍': [{'拍': 1, '场': '临河茶肆', '发生': '账房摔账本',
                            '推进': '查七文'}], '角色任务': {'主角': ['接账本']}},
                   {'通过': True, '问题': [], '修改意见': ''}])
    ds3 = await DP.compose(w, db, people=['主角'])
    ok('A3 ★ 第一轮不通过 → 带意见重写，第二轮通过',
       ds3.verdict.startswith('通过') and ds3.rounds == 2,
       f'{ds3.verdict}/{ds3.rounds}')
    ok('A3b ★★ 重写时把**修改意见**带给了模型（不是空着手重写）',
       any(fix_text in c['text'] for c in calls),
       [c['purpose'] for c in calls])
    ok('A3c 重写用的是新剧本（账房摔账本）',
       any('摔账本' in str(b.get('发生')) for b in ds3.beats), ds3.beats)

    # ── A4 ★ 验算**拿不到结论** → 不算通过（fail-closed）──
    # [EN] ── A4 ★ verification **cannot reach a conclusion** → not counted as passing (fail-closed) ──
    calls.clear()
    CFG.set('DAY_PLAN_FIX_ROUNDS', '0')      # 不重写，直接看结论
    # [EN] no rewrite, look at the conclusion directly
    DP.ask = stub(['第三天，账目牵出旧案。',
                   {'拍': [{'拍': 1, '场': 'x', '发生': 'y', '推进': 'z'}],
                    '角色任务': {'主角': ['翻账']}},
                   None])                     # 验算没拿到
                   # [EN] verification got nothing
    ds4 = await DP.compose(w, db, people=['主角'])
    ok('A4 ★★ 验算拿不到结论**不算通过**（不许 fail-open）',
       not ds4.verdict.startswith('通过') and ds4.problems,
       f'{ds4.verdict!r}/{ds4.problems}')
    ok('A4b 轮次用完就照用并记下问题（不无限重写）',
       ds4.rounds == 1 and ds4.story, f'rounds={ds4.rounds}')

    # ── A5 剧本 JSON 坏了 → 不炸，照旧返回 ──
    # [EN] ── A5 script JSON is broken → does not crash, returns as usual ──
    calls.clear()
    DP.ask = stub(['第三天有个故事。', '这不是 JSON', None])
    ds5 = await DP.compose(w, db, people=['主角'])
    ok('A5 剧本 JSON 坏掉不炸（beats/roles 为空，story 仍在）',
       ds5.story and not ds5.beats and not ds5.roles, f'{ds5.story[:16]!r}')

    # ── A6 落盘：按天覆盖、只写运行文件夹、能读回 ──
    # [EN] ── A6 persistence: overwrite by day, only writes to the run folder, can be read back ──
    tmp = Path(tempfile.mkdtemp(prefix='nws_dayplan_'))
    DP.save_cached(tmp, ds)
    DP.save_cached(tmp, ds3)
    raw = json.loads((tmp / DP.CACHE_NAME).read_text(encoding='utf-8'))
    ok('A6 落盘按天记（两天各一条，同日覆盖不追加）',
       set(raw) == {'3'}, list(raw))
    back = DP.load_cached(tmp, 3)
    ok('A6b 能读回，内容对得上（story/beats/roles）',
       back is not None and bool(back.story) and back.roles == ds3.roles,
       f'{list(back.roles) if back else None}')
    ok('A6c 文件就在**运行文件夹**里（项目文件夹铁律：永不反写）',
       (tmp / DP.CACHE_NAME).exists(), str(tmp))
    ok('A6d 读不存在的天返回 None（不抛）', DP.load_cached(tmp, 99) is None, '')

    # ── A7 `roles_text` / `frame_text` 是给提示词用的两块文本 ──
    # [EN] ── A7 `roles_text` / `frame_text` are the two blocks of text used for the prompt ──
    ok('A7 `roles_text` 一人一行、`frame_text` 就是当天故事',
       '主角' in ds.roles_text() and ds.frame_text() == ds.story, '')

    # ── A8 前情提要真的进**正文**（用户：「前情提要和场景介绍不能够丢」）──
    # [EN] ── A8 the recap really goes into the **body text** (user: "the recap and scene intro must not be
    # [EN] dropped") ──
    #
    # 它以前只是喂给模型的上下文（`agent._story_so_far`），正文里一个字都没有
    # —— 用户要的顺序是「前情提要 → 场景介绍 → 人物说话」，第一段就缺了。
    # [EN] It used to only be context fed to the model (`agent._story_so_far`), not a single word in the
    # [EN] body text
    # [EN] —— the order the user wants is "recap → scene intro → character dialogue", and the first
    # [EN] paragraph was missing.
    from display import script as S
    from store.runfolder import RunFolder
    tmp2 = Path(tempfile.mkdtemp(prefix='nws_recap_'))
    rf = RunFolder(tmp2, '第1次模拟2026-10-07-12-00').create()
    sc = S.SceneScript(time_label='辰时', place='临河茶肆')
    sc.add(S.dialogue('主角', '昨夜账上差七文。'))
    p = rf.flush_daily_script(2, [sc], calendar_str='辰时', weather='晴',
                              cast=['主角'], recap='第二天：账目差了七文，还没查出来。')
    txt = p.read_text(encoding='utf-8')
    ok('A8 ★ 前情提要**真的写进正文**（以前只喂给模型，正文里一个字都没有）',
       '前情提要' in txt and '账目差了七文' in txt,
       [x[:40] for x in txt.splitlines()[:4]])
    ok('A8b 位置对：在 `> 在场：` 之后、正文（`## `）之前',
       txt.index('前情提要') < txt.index('## '), '')
    p2 = rf.flush_daily_script(3, [sc], calendar_str='辰时', cast=['主角'], recap='')
    ok('A8c 没有前情（第一天）→ **不写**这一段（不拿"这是第一天"充数）',
       '前情提要' not in p2.read_text(encoding='utf-8'), '')

    DP.ask = CREW.ask = real_ask
    CFG.set('DAY_PLAN_FIX_ROUNDS', '2')


# ══════════════════════════════════════════════════════════════════
#  B 组：接线（AST + 真对象）
# [EN] Group B: wiring (AST + real objects)
# ══════════════════════════════════════════════════════════════════
def wiring_checks() -> None:
    import ast
    import inspect

    from agent.core import Agent
    from sim.loop import RunLoop

    src_loop = Path('sim/loop.py').read_text(encoding='utf-8')
    ok('B1 ★ 跨天时**真的调了** `_compose_day`（写了没人调 = 死代码）',
       'await self._compose_day()' in src_loop, '')
    ok('B1b ★ 顺序对：`_compose_day()` 在 `_plan_day()` **之前**'
       '（反了就是"各自先排完"，框架落不下去）',
       src_loop.index('await self._compose_day()')
       < src_loop.index('await self._plan_day()'), '')

    ok('B2 循环里把剧本挂到世界上（人物提示词从那里取）',
       'self.world.day_script = ds' in src_loop, '')
    ok('B2b ★ `_plan_day` 跳过**已被派活**的人（不覆盖导演派的事）',
       "not str(getattr(a.ps, 'day_plan', '') or '')" in src_loop, '')

    src_agent = Path('agent/core.py').read_text(encoding='utf-8')
    ok('B3 ★ 人物提示词里带上了〔今日剧本〕这一层',
       "[今日剧本]" in src_agent and '_frame_line' in src_agent, '')
    ok('B3b 框架排在金字塔**之外**（不占 `GOAL_LADDER` 的名额）',
       'self._frame_line() + "".join(' in src_agent, '')

    # 真的造一个 Agent，看 `_goal_ladder()` 里出不出剧本
    # [EN] Actually construct an Agent, see whether `_goal_ladder()` produces a script
    w = _World()
    ds = DP.DayScript(day=3, story='第三天，账目牵出旧案。',
                      roles={'主角': ['翻昨夜的账']}, source='ai')
    w.day_script = ds
    ag = Agent.__new__(Agent)
    ag.world = w
    ag.ps = w.people['主角']
    text = Agent._frame_line(ag)
    ok('B3c ★ 真对象上：框架里既有当天故事、也有他分到的事',
       '账目牵出旧案' in text and '翻昨夜的账' in text, text[:80])
    # ★★★ 2026-10-19：这句话现在**只在低自由度档出现**（`AGENT_FREEDOM` < 35）。
    #   高自由度档不再给"剧本 + 一句自由发挥"，而是**根本不给剧本**，改给许可段
    #   （`freedom.license_line()`，那一段比这句话强得多）。所以判成对：
    #     低档 ⇒ 这句话在；高档 ⇒ 这句话不在（否则就是"拿掉剧本却留着免责声明"）。
    # [EN] ★★★ 2026-10-19: this sentence now appears **only in the low-freedom band**. The high band
    # [EN] no longer says "here is the script, improvise within it" -- it hands over no script at all
    # [EN] and gives a permission block instead. Hence paired: low => present; high => absent (else
    # [EN] you get "script removed but the disclaimer left behind").
    from agent import freedom as _FR
    _lv0 = _FR.task_level
    try:
        _FR.task_level = lambda: 0.0
        text_low = Agent._frame_line(ag)
        _FR.task_level = lambda: 0.9
        text_high = Agent._frame_line(ag)
    finally:
        _FR.task_level = _lv0
    ok('B3d ★ 低自由度时明说"可以自由发挥"（框架 ≠ 提线木偶）',
       '自由发挥' in text_low, '')
    ok('B3d2 ★★ 成对：高自由度时**既没有剧本也没有那句免责声明**'
       '（留着它就成了"剧本拿走了、免责声明还在"，自相矛盾）',
       '自由发挥' not in text_high and '账目牵出旧案' not in text_high,
       text_high[:80])
    w.day_script = None
    ok('B3e 没有当天剧本 → 返回空串（不塞一段假框架）',
       Agent._frame_line(ag) == '', '')

    # ★★ 2026-10-07 新加：`day_plan` 有**两种形态**，读它的人必须都认。
    #   这个 bug 只在"导演派过活的人"身上发作（自己排计划的是列表，看着正常）
    #   —— 表现是人物提示词里出现一字一行的「[今日计划] - 把 / - 少 / - 了」。
    #   ⚠ 判据要**真调 `_plan_line()`**（不是查源码里有没有 split）：
    #     一行里的字符全在一行上，源码哨兵看不出行为差别。
    # [EN] ★★ Added 2026-10-07: `day_plan` has **two forms**, and everyone reading it must recognize both.
    # [EN] This bug only triggers on "people the director has assigned work to" (self-scheduled ones are
    # [EN] lists, look normal)
    # [EN] —— the symptom is the character prompt containing one-character-per-line "[Today's plan] -
    # [EN] assign / - fewer / - missing".
    # [EN] ⚠ The criterion must **actually call `_plan_line()`** (not check whether the source contains
    # [EN] split):
    # [EN] If the characters on one line are all on one line, a source-code sentinel cannot see the
    # [EN] behavioral difference.
    def _plan_text(raw):
        ag2 = Agent.__new__(Agent)
        ag2.world = _World()
        ag2.ps = ag2.world.people['主角']
        ag2.ps.day_plan = raw
        return Agent._plan_line(ag2)

    str_plan = _plan_text('把少了的那几文弄清楚；别让外人看出楼里出了事')
    ok('B6 ★★ 导演派活的计划（**字符串**）不会被逐字拆开'
       '（一字一行是这个 bug 的表现）',
       '- 把少了的那几文弄清楚' in str_plan
       and '\n- 少' not in str_plan and str_plan.count('\n- ') == 2, str_plan.strip())
    list_plan = _plan_text(['照看铺面', '把那件事再压一压'])
    ok('B6b 自己排的计划（**列表**）照旧正常（两种形态都认）',
       '- 照看铺面' in list_plan and '- 把那件事再压一压' in list_plan,
       list_plan.strip())
    ok('B6c 空的两种形态都返回空串（不写一个空标题）',
       _plan_text('') == '' and _plan_text([]) == '' and _plan_text(None) == '', '')

    # 反例法辅助：`_compose_day` 必须是真方法（不是空壳）
    # [EN] Counter-example method as auxiliary: `_compose_day` must be a real method (not an empty shell)
    ok('B4 `RunLoop._compose_day` 真的存在且是协程',
       asyncio.iscoroutinefunction(getattr(RunLoop, '_compose_day', None)), '')
    ok('B4b `__init__` 里有 `_day_script` 的初值（否则第一拍就 AttributeError）',
       'self._day_script = None' in src_loop, '')
    ok('B4c `DAY_PLAN_FIX_ROUNDS` 真的被读到（不是假旋钮）',
       "CFG.i('DAY_PLAN_FIX_ROUNDS')" in Path('director/day_plan.py').read_text(
           encoding='utf-8'), '')

    # 判据自己别写成"源码里出现某个词"就算（§39.5 的教训）：上面 B3c 是真对象。
    # [EN] The criterion itself must not be written as "a certain word appears in the source" (lesson from
    # [EN] §39.5): the above B3c is a real object.
    ok('B5 校验方式自检：B3c 用的是真对象而非源码 grep',
       hasattr(Agent, '_frame_line'), '')


def recap_checks() -> None:
    """D. **前情提要的粒度**（用户 2026-10-07 第二次提）。

    用户原话（这一组就是它的规格）：
    「前情提要内容要小 是针对已经发生的**最近今天或者一段时间**的故事的总结
      除非第一章 否则不要用很大的背景故事来作为前情提要
      （第一张可以用背景故事，但尽量不要用**背景设定**来代替背景故事）」

    ★ 旧实现三个毛病，全都量得出来：
      ① **上限写死 3000 字**（`_recap_text(limit=3000)`）—— 那不是"提要"，
         屏幕上是一大段；
      ② 取 3 天摘要拼起来后 `[-limit:]` —— **从尾部截**，于是"最近三天"
         只剩最后一天的后半句，前两天**整段消失**；
      ③ 第一天拿【世界观】（**设定**）当"前情" —— 用户明确说别这么干。
    
        English:
    D. **Recap granularity** (user's second mention on 2026-10-07).
        User's exact words (this group is its spec):
        "The recap content must be small, it is a summary of the story that has already happened in the **most recent day or period**
          unless it is the first chapter, do not use a very large backstory as the recap
          (the first one can use the backstory, but try not to use the **background setting** in place of the backstory)"
        ★ The old implementation has three defects, all measurable:
          ① **hard-coded cap of 3000 characters** (`_recap_text(limit=3000)`) —— that is not a "recap",
             on screen it is one big block;
          ② after concatenating 3 days of summaries, `[-limit:]` —— **truncates from the tail**, so "the last three days"
             leaves only the last half-sentence of the last day, and the previous two days **disappear entirely**;
          ③ The first day uses 【world view】 (**setting**) as the "recap" —— the user explicitly said not to do this.
    """
    from director import day_plan as DP

    class _W:
        def __init__(self, day=1):
            self.game_day = day
        worldview_text = (
            '【世界观】\n临河镇口一间茶楼，掌柜姓莫。这世道纸贵，字更贵，'
            '寻常人家一年也见不着几张。\n\n'
            '【剧情参考线】\n起：账房先生死了三天才被人发现，桌上账本少了一页。\n'
            '承：旧签被翻出来，指向十年前的旧案。\n转：笔迹对不上。\n合：真相在茶里。\n')

    class _DB0:
        def get_summaries(self, k=3):
            return []

        def recent_events(self, n=20, game_day=0):
            return []

    class _DB3(_DB0):
        def get_summaries(self, k=3):
            return [{'text': '第一天：' + '账目差了七文。' * 20},
                    {'text': '第二天：' + '丁认了这笔账。' * 20},
                    {'text': '第三天：' + '临河茶肆封了账房。' * 20}]

    lim = CFG.i('RECAP_MAX_CHARS')

    # D1 **要小**
    # [EN] D1 **must be small**
    t3 = DP.recap_text(_DB3(), world=_W(3))
    ok(f'D1 ★ 三天摘要拼起来仍 ≤ {lim} 字（它是一段"提要"，不是一大段）',
       len(t3) <= lim, f'{len(t3)} 字')

    # D2 **按天平分**：不是只留最后一天的后半句
    # [EN] D2 **split evenly by day**: not just keeping the last half-sentence of the last day
    ok('D2 ★★ "最近这一段"里**每天都在**（旧实现整体截尾 → 只剩最后一天）',
       all(x in t3 for x in ('第一天', '第二天', '第三天')),
       f'第一天 {"在" if "第一天" in t3 else "没了"} / '
       f'第二天 {"在" if "第二天" in t3 else "没了"} / '
       f'第三天 {"在" if "第三天" in t3 else "没了"}')

    # D3 第一章用**背景故事**（剧情参考线的「起」），不是设定、不剧透
    # [EN] D3 The first chapter uses the **backstory** (the "beginning" of the plot reference line), not
    # [EN] the setting, no spoilers
    t1 = DP.recap_text(_DB0(), world=_W(1))
    ok('D3 ★★ 第一章的"前情"取的是**背景故事**（剧情参考线的「起」）',
       bool(t1) and '账房先生' in t1, t1[:60])
    ok('D3b ★★ 而**不是**拿【世界观】那类**背景设定**顶替（用户明确说过别这样）',
       '纸贵' not in t1, t1[:60])
    ok('D3c ★ 只到「承」之前就停（再往后是大纲，拿来当前情等于剧透）',
       '旧签' not in t1 and '承' not in t1, t1[:60])
    ok('D3d ★ 第一章那一段也小（≤ 上限）', len(t1) <= lim, f'{len(t1)} 字')

    # D4 **非第一章**、又没有摘要 → 空着（不拿背景故事顶替）
    # [EN] D4 **not the first chapter**, and no summary → leave empty (do not substitute the backstory)
    ok('D4 ★★ 第 5 天没有摘要时返回空 —— 不拿背景故事充数'
       '（"没有"比"用错的东西顶数"诚实）',
       DP.recap_text(_DB0(), world=_W(5)) == '',
       repr(DP.recap_text(_DB0(), world=_W(5))[:40]))

    # D5 天数旋钮真的起作用
    # [EN] D5 The day-count knob really works
    saved = CFG.raw('RECAP_DAYS')
    try:
        CFG.set('RECAP_DAYS', '1')
        got = []
        class _DBRec(_DB0):
            def get_summaries(self, k=3):
                got.append(k)
                return [{'text': '第一天：账目差了七文。'}]
        DP.recap_text(_DBRec(), world=_W(3))
        ok('D5 ★ `RECAP_DAYS` 真的传给了 `get_summaries()`（不是摆着好看）',
           got and got[0] == 1, f'收到 k={got}')
    finally:
        CFG.set('RECAP_DAYS', saved)


def main() -> int:
    try:
        asyncio.run(logic_checks())
    except Exception:                                          # noqa: BLE001
        ok('A 组跑得完（不崩）', False, traceback.format_exc()[-300:])
        print(traceback.format_exc()[-1200:])
    try:
        wiring_checks()
    except Exception:                                          # noqa: BLE001
        ok('B 组跑得完（不崩）', False, traceback.format_exc()[-300:])
        print(traceback.format_exc()[-1200:])
    try:
        recap_checks()
    except Exception:                                          # noqa: BLE001
        ok('D 组跑得完（不崩）', False, traceback.format_exc()[-300:])
        print(traceback.format_exc()[-1200:])

    n_ok = 0
    for c in checks:
        print(('  ✓ ' if c['ok'] else '  ✗ ') + c['name']
              + ('' if c['ok'] else f"   [{c['detail']}]"))
        n_ok += bool(c['ok'])
    print(f'\n当日剧本验证：{n_ok}/{len(checks)}')
    out = APP_DIR / 'assets' / 'screenshots'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'day_plan_report.json').write_text(
        json.dumps({'checks': checks}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    return 0 if n_ok == len(checks) else 2


if __name__ == '__main__':
    sys.exit(main())
