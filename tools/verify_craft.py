# -*- coding: utf-8 -*-
"""验证：叙事工艺库接到导演身上（设计稿 §8.4）+ 导演的三个「率」。

用户 2026-10-06：「影视剧的优化都做掉」。
第一件就是 **`craft/` 里那套素材从 10-04 就摆着、一行代码没读** ——
`CRAFT_LIBRARY` / `CRAFT_CASES_ENABLED` 是死的，类型卡的 `playbook映射`
**6 张卡里有 10 个名字在 playbook 里根本不存在**（指向空气，运行时静默少喂一条）。

判据分三层：
  A **数据**：类型卡 / playbook / 案例**全部**能读出来（含那 10 个缺名字补齐后 0 遗漏）；
  B **限流**：§8.4 写的「playbook 片段 ≤2 条、每条 ≤80 token」是**代码截断**，
    不是靠人自觉；且 `案例参照`（版权红线）**绝不进提示词**；
  C **接线**：张力目标按类型卡走、三个率真按概率拦（不是只写在提示词里）。

用法：.venv\\Scripts\\python.exe tools/verify_craft.py
产出：assets/screenshots/craft_report.json

English:
Verification: narrative craft library wired onto the director (design doc §8.4) + the director's
three "rates".
User 2026-10-06: "Do all the film/TV optimizations".
The first thing is that the set of materials in **`craft/`** has been sitting there since 10-04
and not a single line of code reads it ——
`CRAFT_LIBRARY` / `CRAFT_CASES_ENABLED` are dead, the type card's `playbook映射`
**Among the 6 cards, 10 names do not exist in the playbook at all** (pointing at air, silently
feeding one fewer item at runtime).
The criteria are in three layers:
  A **Data**: type cards / playbook / cases **all** readable (including the 10 missing names after being filled in, 0 omissions);
  B **Rate limiting**: what §8.4 writes — "playbook snippets ≤2 items, each ≤80 token" — is **truncated in code**,
    not left to human discipline; and `案例参照` (copyright red line) **never enters the prompt**;
  C **Wiring**: the tension target follows the type card, and the three rates really block by probability (not just written in the prompt).
Usage: .venv\\Scripts\\python.exe tools/verify_craft.py
Output: assets/screenshots/craft_report.json
"""
from __future__ import annotations

import json
import random
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
# ⚠ 本脚本**一个像素都不量、也不弹窗**，但会把 CFG 改来改去 ——
#   最后统一还原，且**绝不点任何会 `CFG.save()` 的按钮**（见 MEMORY 的铁律）。
# [EN] ⚠ This script **does not measure a single pixel, nor does it pop up any dialogs**, but it will
# [EN] modify CFG back and forth ——
# [EN] and restore it all at the end, and **never click any button that calls `CFG.save()`** (see the
# [EN] iron rule in MEMORY).
CFG.set('MOCK_LLM', 'true')

from craft import craftmix as cm                                # noqa: E402
from llm.tokens import estimate_tokens                          # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


# ══════════════════════════════════════════════════════════════
#  A. 数据：全都得读得出来
# [EN] A. Data: everything must be readable
# ══════════════════════════════════════════════════════════════
def test_data() -> bool:
    ok = True
    d = cm.load(force=True)
    ok &= rec('A1 6 张类型档案都读出来了', len(d['genres']) == 6,
              str(sorted(d['genres'])))
    ok &= rec('A1 4 组案例库都读出来了（`古典文学.yaml` 的直双引号曾让整组被静默丢掉）',
              len(d['cases']) == 4, str(sorted(d['cases'])))
    ok &= rec('A1 playbook 条目摊平了（跨三架）', len(d['entries']) >= 30,
              str(len(d['entries'])))

    # ★ 最要紧的一条：映射名与条目名**两边都是人手写的**，会漂。
    # [EN] ★ The most critical one: both the mapping names and the entry names **are hand-written on both
    # [EN] sides**, and they drift.
    miss = cm._misses()
    ok &= rec('A2 ★★ 类型卡的 playbook映射**没有一个指向空气**', not miss,
              '、'.join(miss) or '（全部能解析）')

    # 结构轴也能找卡（设计稿 §8.2 说结构轴与题材正交）
    # [EN] Structural axes can also get stuck (design doc §8.2 says structural axes are orthogonal to
    # [EN] genre)
    ok &= rec('A3 按题材找得到卡', (cm.card('悬疑灵异') or {}).get('类型') == '悬疑灵异')
    ok &= rec('A3 认不出的题材**不瞎给一张卡**（返回 None）',
              cm.card('这个题材不存在') is None)
    ok &= rec('A3 模糊匹配：题材名只是别名时也能命中',
              cm.card('悬疑') is not None, str(cm.card('悬疑') is not None))
    # 子串匹配是必需的（类型卡写"换地图节奏"、条目名是"换地图"）
    # [EN] Substring matching is necessary (a type card writes "map-change pacing", while the entry name is
    # [EN] "map change")
    ok &= rec('A3 ★ 条目名的双向子串能匹配（`换地图节奏` → `换地图`）',
              cm.resolve_entry('换地图节奏') is not None)
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 限流与版权红线
# [EN] B. Rate limiting and copyright red line
# ══════════════════════════════════════════════════════════════
def test_brief() -> bool:
    ok = True
    for g in cm.load()['genres']:
        picked = cm.entries_for(g)
        ok &= rec(f'B1 {g}：playbook 片段 ≤{cm.MAX_ENTRIES} 条',
                  len(picked) <= cm.MAX_ENTRIES, str(len(picked)))
        for name, tip in picked:
            ok &= rec(f'B1 ★ {g}／{name}：每条 ≤{cm.MAX_ENTRY_TOKENS} token（代码截断）',
                      estimate_tokens(tip) <= cm.MAX_ENTRY_TOKENS,
                      f'{estimate_tokens(tip)} token')
    b = cm.brief('悬疑灵异')
    ok &= rec('B2 简报整体 ≤ 兜底上限', estimate_tokens(b) <= cm.BRIEF_TOKEN_CAP,
              f'{estimate_tokens(b)} token')
    ok &= rec('B2 简报里有冲突偏好 / 钩子 / 爽点 / 毒点',
              all(k in b for k in ('冲突主引擎', '可用钩子', '爽点', '毒点')), b[:120])
    # ★★ 版权红线：类型卡的 `案例参照` 是给人看的导航，绝不能进提示词
    # [EN] ★★ Copyright red line: the type card's `案例参照` is navigation meant for humans and must never
    # [EN] enter the prompt
    for g in cm.load()['genres']:
        bb = cm.brief(g)
        bad = [x for x in ((cm.card(g) or {}).get('案例参照') or []) if str(x) in bb]
        ok &= rec(f'B3 ★★ {g}：`案例参照`（{bad or "无"}）**不许进提示词**', not bad,
                  str(bad))
    ok &= rec('B3 认不出的题材 → 简报是空串（不硬塞）', cm.brief('不存在') == '',
              repr(cm.brief('不存在')))

    # `CRAFT_CASES_ENABLED` 真的管着案例（以前这个旋钮是死的）
    # [EN] `CRAFT_CASES_ENABLED` actually controls the cases (this knob used to be dead)
    CFG.set('CRAFT_CASES_ENABLED', 'false')
    off = cm.cases('悬疑灵异')
    CFG.set('CRAFT_CASES_ENABLED', 'true')
    on = cm.cases('悬疑灵异')
    ok &= rec('B4 ★ `CRAFT_CASES_ENABLED` 真的管着案例（0 项 vs 3 项）',
              off == [] and len(on) == 3, f'{len(off)} / {len(on)}')
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 接线：张力目标 + 三个率
# [EN] C. Wiring: tension target + three rates
# ══════════════════════════════════════════════════════════════
def test_wiring() -> bool:
    ok = True
    from director.engine import DirectorEngine, DirectorEvent, _TENSION_CURVE

    class W:
        def __init__(self, genre='悬疑灵异', structure='单元剧'):
            self.genre_card = {'主题材': genre, '结构': structure}
            self.people = {'阿九': 1, '阿福': 1}

    eng = DirectorEngine.__new__(DirectorEngine)
    saved = {k: CFG.raw(k) for k in
             ('TENSION_CURVE', 'PACING_STYLE', 'COINCIDENCE_RATE',
              'NEW_FACE_RATE', 'REVEAL_PACING')}
    try:
        # ── C1 张力目标 = 类型节奏模板 × 用户旋钮 ──
        eng.world = W('悬疑灵异')          # 类型卡 medium
        # [EN] ── C1 Tension target = type pacing template × user knob ──
        # [EN] type card medium
        CFG.set('TENSION_CURVE', 'auto')
        CFG.set('PACING_STYLE', 'roller')  # 节奏感想让它变过山车
        # [EN] The pacing feel should make it a roller coaster
        ok &= rec('C1 ★ auto 时**先看类型卡**（悬疑灵异 medium 压过节奏感的 roller）',
                  eng._curve() == _TENSION_CURVE['medium'], str(eng._curve()))
        eng.world = W('玄幻修仙')          # 类型卡 roller
        # [EN] type card roller
        ok &= rec('C1 ★ 换个类型就换曲线（玄幻修仙 roller）',
                  eng._curve() == _TENSION_CURVE['roller'], str(eng._curve()))
        CFG.set('TENSION_CURVE', 'flat')   # 用户**显式**选了
        # [EN] the user **explicitly** selected
        ok &= rec('C1 ★★ 用户显式选了就听用户的（类型卡不许盖掉它）',
                  eng._curve() == _TENSION_CURVE['flat'], str(eng._curve()))
        CFG.set('TENSION_CURVE', 'auto')
        eng.world = W('认不出的题材')
        CFG.set('PACING_STYLE', 'slow')
        ok &= rec('C1 认不出类型 → 退回跟着节奏感走（slow→flat）',
                  eng._curve() == _TENSION_CURVE['flat'], str(eng._curve()))

        # ── C2 三个率：真按概率拦（不是只写进提示词）──
        # [EN] ── C2 Three rates: really block by probability (not just written into the prompt) ──
        def ev(etype='巧合', involved=None):
            return DirectorEvent(event_type=etype, description='门口有人敲门',
                                 involved=list(involved or []), intensity=0.5,
                                 node_relevant='N1')

        CFG.set('COINCIDENCE_RATE', '0')
        random.seed(1)
        gone = sum(1 for _ in range(40) if eng._rate_gate(ev('巧合')) is None)
        ok &= rec('C2 ★★ 巧合率=0 → 40 次全拦（这个世界没有巧合）', gone == 40,
                  f'拦下 {gone}/40')
        CFG.set('COINCIDENCE_RATE', '1')
        gone0 = sum(1 for _ in range(40) if eng._rate_gate(ev('巧合')) is None)
        ok &= rec('C2 ★ 巧合率=1 → 一次都不拦', gone0 == 0, f'拦下 {gone0}/40')

        CFG.set('NEW_FACE_RATE', '0')
        e = eng._rate_gate(ev('外部刺激', ['阿九', '一个陌生的货郎']))
        ok &= rec('C2 ★★ 新面孔率=0 → 只在场的人留下，凭空造的名字被剔掉',
                  e is not None and e.involved == ['阿九'], str(e.involved if e else None))
        ok &= rec('C2 ★ 剔名字**不丢整件事**（事件本身还有用，不该一起毙）',
                  e is not None, str(e is not None))
        CFG.set('NEW_FACE_RATE', '1')
        e = eng._rate_gate(ev('外部刺激', ['阿九', '一个陌生的货郎']))
        ok &= rec('C2 新面孔率=1 → 名字留着',
                  e is not None and '一个陌生的货郎' in e.involved, str(e.involved))

        CFG.set('REVEAL_PACING', '0')
        random.seed(2)
        g1 = sum(1 for _ in range(40) if eng._rate_gate(ev('秘密泄露')) is None)
        g2 = sum(1 for _ in range(40) if eng._rate_gate(ev('伏笔激活')) is None)
        g3 = sum(1 for _ in range(40) if eng._rate_gate(ev('人物冲突')) is None)
        ok &= rec('C2 ★★ 揭示节奏=0 → 秘密泄露/伏笔激活全攒着不揭',
                  g1 == 40 and g2 == 40, f'秘密 {g1}/40、伏笔 {g2}/40')
        ok &= rec('C2 ★ 揭示节奏只管揭示型 —— 「人物冲突」一次都没被它拦',
                  g3 == 0, f'人物冲突被拦 {g3}/40')
    finally:
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


def test_wiring_e2e() -> bool:
    """★★ 端到端：**接线本身**也要判（不是只判那几个函数各自对不对）。

    为什么要单开一组：反例法把 `_inject_event` 里那句 `self._rate_gate(event)`
    改成空转之后，上面 C 组的判据**一条都不红** —— 因为它们直接调 `_rate_gate()`，
    证明的是"这个函数工作正常"，**没证明"导演真的调用它"**。
    这正是本项目反复栽的那个坑（"测了实现，没测接线"）。

    做法：打桩 `llm.chat` 让它返回一个固定的事件 JSON，然后真的跑一遍
    `_inject_event()`，断言：
      · 提示词里**有**工艺库简报（冲突偏好 / 钩子 / playbook 名）—— 简报真进了提示词；
      · 提示词里**没有** `案例参照`（版权红线）；
      · `COINCIDENCE_RATE=0` 时那次巧合**真的没被注入**（返回 None）。
    
        English:
    ★★ End-to-end: **the wiring itself** must also be judged (not just whether those functions are
    each correct).
        Why open a separate group: after the counterexample method turns the line `self._rate_gate(event)` in `_inject_event`
        into a no-op, **not a single one** of the criteria in group C above goes red —— because they directly call `_rate_gate()`,
        which proves "this function works correctly", **not that "the director actually calls it"**.
        This is exactly the pit this project keeps falling into ("tested the implementation, not the wiring").
        Approach: stub `llm.chat` so it returns a fixed event JSON, then actually run through
        `_inject_event()`, and assert:
          · the prompt **has** the craft library brief (conflict preferences / hooks / playbook names) —— the brief really entered the prompt;
          · the prompt **does not have** `案例参照` (copyright red line);
          · when `COINCIDENCE_RATE=0`, that coincidence **really was not injected** (returns None).
    """
    ok = True
    from director import engine as E

    class _Clock:
        minutes = 0
        day = 1

    class W:
        clock = _Clock()
        genre_card = {'主题材': '悬疑灵异', '结构': '单元剧'}
        people = {'阿九': 1}
        tension = 0.2
        scene = '临河茶肆'
        current_node = 'N1'
        event_count = 0
        game_day = 1

        def world_prefix(self):
            return '[世界观] 这是一座书舟。'

        def current_node_info(self):
            return {'名称': '楼前失忆', '概要': '陈梧初到', '完成判据': '被收留'}

        def on_stage_names(self):
            return ['阿九']

        def off_stage_names(self):
            # ⚠ 2026-10-26 补：产品侧（`sim/loop.py` 的群演"落点"那段）现在会读
            #   `world.off_stage_names()`。夹具少了它，整支判据**直接崩**在
            #   `AttributeError: 'W' object has no attribute 'off_stage_names'`，
            #   报出来的是"验证中途崩溃"，看着像 craft 坏了，其实是夹具没跟上。
            # [EN] ⚠ Added 2026-10-26: the product side reads `world.off_stage_names()`.
            # [EN] Without it the whole check dies on AttributeError and reports
            # [EN] "the verification crashed midway" -- looking like craft is broken when the
            # [EN] fixture simply fell behind.
            return []

        def clock_display(self):
            return '第1天·辰时'

    class D:
        def recent_events(self, n=12):
            return []

        def add_event(self, *a, **k):
            pass

    eng = E.DirectorEngine.__new__(E.DirectorEngine)
    eng.world = W()
    eng.db = D()
    eng._events_since_stall = 0

    seen: dict = {}

    async def fake_chat(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content']
        return json.dumps({
            '是否介入': True, '类型': '巧合', '事件': '一阵风把门吹开了',
            '涉及人物': ['阿九', '一个陌生货郎'], '强度': 0.5, '理由': '凑巧',
        }, ensure_ascii=False)

    saved = {k: CFG.raw(k) for k in ('COINCIDENCE_RATE', 'NEW_FACE_RATE',
                                     'REVEAL_PACING', 'DIRECTOR_ENABLED')}
    real = E.llm.chat
    E.llm.chat = fake_chat
    import asyncio
    try:
        CFG.set('NEW_FACE_RATE', '0')
        CFG.set('COINCIDENCE_RATE', '1')
        # ★★★ 2026-10-19：**必须走强制通道**（`reason_hint`）。
        #   这一支的假世界（`people = {'阿九': 1}`）算不出任何压力 ——
        #   `director.pressure` 要真的 `PersonState`，读不到就全 0 ⇒
        #   "四压全低 ⇒ 不出事、连模型都不调" ⇒ `seen['prompt']` 永远是空的，
        #   四条判据一起红，而产品其实是对的。
        #   工艺库接在 prompt 里，与走哪条通道无关 —— 所以用强制通道测接线，
        #   既保留了这一支要守的东西，也不用把一个假世界改成真世界。
        # [EN] ★★★ 2026-10-19: **must use the forced channel** (`reason_hint`). This fixture's fake
        # [EN] world (`people = {'阿九': 1}`) yields zero pressure -- `director.pressure` needs real
        # [EN] `PersonState`s, reads nothing => all zero => "all low => no event, no model call" =>
        # [EN] `seen['prompt']` stays empty and four checks go red while the product is correct.
        # [EN] The craft library sits in the prompt regardless of channel, so testing wiring through
        # [EN] the forced channel keeps what this group guards without rebuilding the fake world.
        ev = asyncio.run(eng._inject_event(reason_hint='判据：走强制通道'))
        p = seen.get('prompt', '')
        ok &= rec('D1 ★★ 工艺库简报**真的进了**挑事提示词（有冲突主引擎/钩子）',
                  '冲突主引擎' in p and '可用钩子' in p, p[:160].replace('\n', ' | '))
        ok &= rec('D1 ★★ 提示词里带上了 playbook 片段的**名字**（草蛇灰线/志怪笔法）',
                  '草蛇灰线' in p or '志怪笔法' in p, p[:200].replace('\n', ' | '))
        ok &= rec('D1 ★★ 提示词里**没有** `案例参照`（聊斋志异等，版权红线）',
                  not any(x in p for x in ('聊斋志异', '深夜书屋', '隐秘的角落')),
                  p[:160].replace('\n', ' | '))
        ok &= rec('D1 三个率写进了提示词',
                  all(k in p for k in ('巧合型事件出现频率', '新面孔出现频率',
                                       '揭示型')), p[:200].replace('\n', ' | '))
        ok &= rec('D1 ★★ 接线成立：`_inject_event` 真的调了放行闸（新面孔率=0 剔了名字）',
                  ev is not None and ev.involved == ['阿九'],
                  str(ev.involved if ev else None))

        CFG.set('COINCIDENCE_RATE', '0')
        ev2 = asyncio.run(eng._inject_event())
        ok &= rec('D1 ★★ 接线成立：巧合率=0 → `_inject_event` 真的返回 None（不注入）',
                  ev2 is None, str(ev2))
    finally:
        E.llm.chat = real
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


if __name__ == '__main__':
    print('叙事工艺库接线 · 张力目标 · 导演三个率 —— 验证', flush=True)
    ok = True
    try:
        head('A. 数据（类型卡 / playbook / 案例）')
        ok &= test_data()
        head('B. §8.4 限流 + 版权红线')
        ok &= test_brief()
        head('C. 接线（张力目标 / 三个率）')
        ok &= test_wiring()
        head('D. 端到端：接线本身也要判')
        ok &= test_wiring_e2e()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'craft_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1000:])
    sys.exit(0 if report['ok'] else 2)
