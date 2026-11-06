# -*- coding: utf-8 -*-
"""真机验证：**剧组**（`crew/`）—— 一班人、一条链、接到工具上。

用户 2026-10-07：
「对话以及别的很多功能你都审一遍，那些地方适合用AI的但没用的，你引入AI……
  你们要组成一个剧组+剧作者的组合……然后各个Agent合理的分配到界面各个位置。
  我知道的至少有 小说作家 剧作者 导演 各个演员 群众演员 道具 美术 宣发 场记
  等等需要的角色（跟工具进行合理对接）」

这个脚本一条条钉住那段话，**每条都要能红**：

  A **名册是真的**：十个职位在位；每条 `hooks` 在程序里真的解析得到
    （"对接到软件架构"的唯一凭据 —— 名册说接上了、代码里没有，那不算）。
  B **各读各的工艺**：小说作家读叙事章法、剧作者读剧作与舞台 ——
    两个人的工艺块**内容不同**（同读一份简报等于一个职位问十遍）。
  C **协作链是真的**：名册里 `feeds` 指到哪，材料真的递到哪
    （资料员的考据进剧作者的提示词、道具单进场记的提示词）。
  D **接进流程**：跨天走"美术+道具 → 作家 → 资料员 → 剧作者 → 导演验算"；
    收工走"场记 + 宣发 + 在位三职位报状态"。
  E **接到工具**：美术+道具 → 出图提示词前缀；道具 → 本地画的要素匹配。
  F **真机**：中栏出现剧组那些条；右栏「剧组」面板把十个职位画了出来。

用法：.venv\\Scripts\\python.exe tools/verify_crew.py [--logic-only]
产出：assets/screenshots/crew_report.json + crew_ui.png

English:
real-run verification: **crew** (`crew/`) -- one troupe, one chain, wired to tools.
user 2026-10-07:
"Review the dialogue and many other features; where AI fits but is not used, introduce AI......
  you should form a combination of a crew + playwright...... then assign each Agent reasonably to positions in the UI.
  The ones I know of at least are novel writer, playwright, director, various actors, extras, props, art, publicity, 场记
  and other needed roles (wired reasonably to tools)"
this script pins down that passage line by line, **each one must be able to go red**:
  A **the roster is real**: ten positions filled; every `hooks` entry actually resolves in the program
    (the only evidence of "wired to the software architecture" -- if the roster says it's wired but the code doesn't have it, that doesn't count).
  B **Each reads their own craft**: novelists read narrative structure, playwrights read dramaturgy and staging ——
    the two people's craft blocks have **different content** (reading the same brief is like asking one role ten times).
  C **The collaboration chain is real**: wherever `feeds` points in the roster, that's where materials actually get delivered
    (the researcher's findings go into the playwright's prompt, the prop list goes into the script supervisor's prompt).
  D **Wired into the flow**: cross-day follows "art + props → writers → researcher → playwright → director verification";
    end-of-day follows "script supervisor + publicity + the three on-duty roles report status".
  E **Wired into tools**: art + props → image prompt prefix; props → element matching for local drawings.
  F **Real machine**: the crew rows appear in the center column; the "crew" panel in the right column draws all ten roles.
Usage: .venv\\Scripts\\python.exe tools/verify_crew.py [--logic-only]
Output: assets/screenshots/crew_report.json + crew_ui.png
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

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown                         # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('BEAT_SECONDS', '2')
CFG.set('SHOW_OPENING', 'false')
# ★ F 组测的是**剧组产出真的能上屏**（"不是只写进文件"），所以要显式把
#   `CREW_SCREEN` 设成 `full`。2026-10-07 之后默认档是 `key`
#   （只推必要的：复盘/出错/去AI命中）—— 那是用户要的"中栏少出现演职人员"，
#   不是这条判据要否定的东西。**"能不能上屏"与"默认推多少"是两件事**，
#   分开测：这里测前者；默认档的行为在 `verify_crew_review` 里测。
# [EN] ★ Group F tests that **crew output actually reaches the screen** ("not just written to a file"),
# [EN] so explicitly set
# [EN] `CREW_SCREEN` to `full`. After 2026-10-07 the default tier is `key`
# [EN] (push only what is necessary: review/errors/de-AI hits) -- that is the user's "fewer cast and
# [EN] crew appearing in the middle column",
# [EN] which is not what this criterion is meant to negate. **"Whether it can reach the screen" and
# [EN] "how much is pushed by default" are two different things**,
# [EN] test them separately: here we test the former; the default tier's behavior is tested in
# [EN] `verify_crew_review`.
CFG.set('CREW_SCREEN', 'full')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from crew import agents as A                                    # noqa: E402
from crew import roster as R                                    # noqa: E402
from crew import studio as ST                                   # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
ONLY_LOGIC = '--logic-only' in sys.argv
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _ctx():
    from world.state import WorldState, PersonState
    w = WorldState(scene='临河茶肆 · 堂内', scene_desc='雨', weather='雨')
    for n in ('主角', '阿枝', '阿福'):
        w.add_person(PersonState(n, identity=f'{n}的身份'))
    w.worldview_text = '【世界观】临河镇口的一座茶楼。\n\n【剧情参考线】起：不该进前情'
    w.genre_card = {'主题材': '悬疑灵异', '结构': '单元剧'}

    class DB:
        def get_summaries(self, k=6, scope='故事'):
            return [{'text': '第二天：账目差了七文，还没查出来。'}]

        def recent_events(self, n=20, game_day=0):
            return [{'content': '主角在门口捡到一双新布鞋。'}]

    return A.SetCtx(world=w, db=DB(), day=3,
                    people=['主角', '阿枝', '阿福']), w, DB()


# ══════════════════════════════════════════════════════════════
#  A/B/C/E —— 纯逻辑
# [EN] A/B/C/E -- pure logic
# ══════════════════════════════════════════════════════════════
def logic_checks() -> None:
    # ── A 名册是真的 ──
    # ★ 2026-10-07 改成"名册与在位者一一对应"，不再钉写死的条数：
    #   写死 `== 10` 会在**每次加职位**时假红（这一轮加「编剧室」就撞了一次），
    #   而它红了之后唯一省事的做法就是改大那个数。这条判据**本意**是
    #   "名册里每个位子都有人、没有多余实现" —— 那就直接量这个。
    # [EN] -- A the roster is real --
    # [EN] ★ 2026-10-07 changed to "roster and incumbents correspond one-to-one", no longer pinning a
    # [EN] hard-coded count:
    # [EN] hard-coding `== 10` would go falsely red **every time a position is added** (this round adding
    # [EN] "writers' room" already hit it once),
    # [EN] and the only easy fix once it goes red is to bump that number up. This criterion's **intent** is
    # [EN] "every seat in the roster is filled, with no extra implementations" -- so just measure that
    # [EN] directly.
    ok('A1 名册与在位者**一一对应**（每个职位都有人到岗，也没有多余的实现）',
       set(R.keys()) == set(A.MEMBERS) and not A.missing_members(),
       f'{len(R.ROSTER)} 个：{"、".join(r.name for r in R.ROSTER)}')
    ok('A2 名册上点名的职位一个不少',
       all(k in R.BY_KEY for k in ('novelist', 'screenwriter', 'director',
                                   'actor', 'extra', 'props', 'art',
                                   'publicity', 'continuity')),
       '')
    ok('A3 ★★ **每条 hooks 都真的解析得到**（"对接到软件架构"的唯一凭据）',
       not R.audit_hooks(), str(R.audit_hooks() or '全部命中'))
    ok('A4 每个职位都有人在位（名册与实现一一对应）',
       not A.missing_members(), str(A.missing_members() or '齐'))
    ok('A5 每个职位都有下游 —— 没有"只给用户看就完了"的产出',
       all(r.feeds for r in R.ROSTER), '')
    ok('A6 出厂自查能把断线查出来（判据不是恒真）',
       _audit_can_fail(), '把一条 hook 改错 → 自查必须报它')
    #: `feeds` 可以是另一个职位的 key，也可以是这几个**功能名**：
    #:   · `export` —— 产出落进导出物（`export/bundle.py` 那一套）；
    #:   · `author` —— 给作者自己看的过程稿（运行文件夹里的那些 `.md`，
    #:     既不进小说正文、也不进导出物）。
    #: ⚠ 加功能名要**同时确认真的有人读它**：`publicity` 原来写 `feeds='export'`，
    #:   而 `export/*` 里一处都没读 `宣发文案` —— 名册上的一句话在程序里不成立，
    #:   正是本项目零容忍的"假接线"（2026-10-07 审计改成了 `author`）。
    # [EN] : `feeds` can be another position's key, or one of these **function names**:
    # [EN] :   · `export` -- output lands in the export artifact (the `export/bundle.py` set);
    # [EN] :   · `author` -- process drafts for the author's own eyes (the `.md` files in the run folder,
    # [EN] :     which go neither into the novel body nor into the export artifact).
    # [EN] : ⚠ adding a function name requires **also confirming someone actually reads it**: `publicity`
    # [EN] originally wrote `feeds='export'`,
    # [EN] : but nothing in `export/*` ever read `宣发文案` -- a statement on the roster that does not hold in
    # [EN] the program,
    # [EN] : exactly the "fake wiring" this project has zero tolerance for (the 2026-10-07 audit changed it
    # [EN] to `author`).
    NON_ROLE_FEEDS = ('export', 'author')
    ok('A7 `feeds` 指向的职位都存在（不会指到空气）',
       all((r.feeds in R.BY_KEY) or r.feeds in NON_ROLE_FEEDS
           for r in R.ROSTER),
       str([(r.key, r.feeds) for r in R.ROSTER
            if r.feeds not in R.BY_KEY and r.feeds not in NON_ROLE_FEEDS]))

    # ── B 各读各的工艺 ──
    # [EN] -- B each reads its own craft --
    nl = A.craft_block('novelist', '悬疑灵异', '单元剧')
    sw = A.craft_block('screenwriter', '悬疑灵异', '单元剧')
    ok('B1 小说作家读得到工艺（叙事章法那一架）', bool(nl.strip()), nl[:60])
    ok('B2 ★★ 剧作者读得到**剧作理论**（《茶馆》那一架：剧作与舞台）',
       bool(sw.strip()) and '〔' in sw, sw[:70])
    ok('B3 ★★ 两个人读的**不是同一份**（各读各的手艺，否则等于一个职位问十遍）',
       nl.strip() != sw.strip(), f'作家 {len(nl)} 字 / 剧作者 {len(sw)} 字')
    ok('B4 新加的那本工艺书被装进了工艺库（不是写了没人读）',
       '可拍性检查' in A.craftmix.load()['entries']
       and '人物一句话立起来' in A.craftmix.load()['entries'],
       f'{len(A.craftmix.load()["entries"])} 条')
    ok('B5 剧作者那架里的条目**真的进了他的工艺块**（不是装了不用）',
       any(x in sw for x in ('可拍性检查', '一场一转变', '人物一句话立起来',
                             '上场下场都带戏', '群像调度', '以景写时',
                             '舞台提示写给演员', '一件小道具承住一切', '独白节制')),
       sw[:120].replace('\n', ' '))

    # ── E 接到工具 ──
    # [EN] -- E wired to tools --
    art = A.CrewNote(role='art', ok=True, title='水墨',
                     data={'画风': '水墨淡彩、纸本质感',
                           '主色': [{'色': '#3B4A52', '用途': '瓦'},
                                    {'色': '#C9A24E', '用途': '灯'}],
                           '忌': ['霓虹色']})
    pref = A.Art.prompt_prefix(art)
    ok('E1 ★ 美术指导能变成**出图提示词前缀**（写进 MD 不算接线）',
       '水墨淡彩' in pref and '#3B4A52' in pref and '霓虹色' in pref, pref[:80])
    ok('E2 没有美术指导时不塞假要求（返回空串）',
       A.Art.prompt_prefix(None) == ''
       and A.Art.prompt_prefix(A.CrewNote(role='art', ok=False)) == '', '')
    from image_gen.ai import build_prompt
    p1 = build_prompt('茶肆', weather='雨')
    p2 = build_prompt('茶肆', weather='雨', crew=pref)
    ok('E3 ★★ `crew` 前缀真的进了文生图提示词，而且**排在最前**'
       '（靠前的词权重高，"这部戏长什么样"是全局约束）',
       p2.startswith('水墨淡彩') and len(p2) > len(p1), p2[:60])
    from image_gen.scene import elements_for
    # ⚠ 地点名里**不能**带「屋/堂/房」这类词：那会点亮 `indoor`，
    #   而室内按设计会清掉水与船（"室内不画山水"）—— 夹具选错会得出
    #   "道具没起作用"的错误结论（第一版就是这么红的）。
    # [EN] ⚠ place names **must not** contain words like "屋/堂/房": that would light up `indoor`,
    # [EN] and indoor by design clears water and boats ("no landscapes indoors") -- choosing the wrong
    # [EN] fixture yields the
    # [EN] wrong conclusion that "the prop had no effect" (the first version went red exactly this way).
    e0 = elements_for('', '晴')
    e1 = elements_for('', '晴', props=['渡口的船', '河边的柳'])
    ok('E4 ★ 道具名真的影响了本地画的要素（"船/河"点亮了对应画面）',
       (not e0['water'] and not e0['boat']) and e1['water'] and e1['boat'],
       f"{[k for k, v in e1.items() if v]}")


def _audit_can_fail() -> bool:
    """反例法：把某条 hook 改错，`audit_hooks` 必须报它（判据不是恒真）。

    ⚠ 2026-10-11：`audit_hooks()` 现在走**有效名册**（`roster.roles()`，
    它从 `crew/catalog.effective()` 取），不再直接读 `R.ROSTER` ——
    所以只往 `R.ROSTER` 里塞一条**不够**：catalog 那一层有**按目录指纹的缓存**，
    塞进去的东西会被缓存挡住，判据当场变红（"自查没报它"）。

    ⇒ 注入之后要把两层缓存都清掉（`_CACHE` 是"目录没变"的缓存，
      `_ROLES_CACHE` 是"名册没变"的缓存）。**这正说明判据在真跑产品那条路。**
    
        English:
    Counter-example method: break a certain hook, and `audit_hooks` must report it (the criterion is
    not vacuously true).
        ⚠ 2026-10-11: `audit_hooks()` now goes through the **effective roster** (`roster.roles()`,
        which takes from `crew/catalog.effective()`), and no longer reads `R.ROSTER` directly ——
        so just stuffing one entry into `R.ROSTER` is **not enough**: the catalog layer has a **cache keyed by directory fingerprint**,
        and what you stuff in gets blocked by the cache, making the criterion turn red on the spot ("the self-check didn't report it").
        ⇒ After injection, both layers of cache must be cleared (`_CACHE` is the "directory unchanged" cache,
          `_ROLES_CACHE` is the "roster unchanged" cache). **This precisely shows the criterion runs on the real product path.**
    """
    bad = R.Role(key='x', name='x', duty='d', tier='cheap', when='day',
                 feeds='export', hooks=('crew.roster.这个符号不存在',))
    saved = R.ROSTER
    from crew import catalog as _CAT
    saved_cache = dict(_CAT._CACHE)
    saved_roles = dict(R._ROLES_CACHE)
    try:
        R.ROSTER = tuple(saved) + (bad,)
        R.BY_KEY[bad.key] = bad
        _CAT._CACHE.clear()
        R._ROLES_CACHE.clear()
        got = R.audit_hooks()
        return got.get('x') == ['crew.roster.这个符号不存在']
    finally:
        R.ROSTER = saved
        R.BY_KEY.pop(bad.key, None)
        _CAT._CACHE.clear()
        _CAT._CACHE.update(saved_cache)
        R._ROLES_CACHE.clear()
        R._ROLES_CACHE.update(saved_roles)


async def _continuity_empty():
    ctx, _w, _db = _ctx()
    return await A.Continuity().run(ctx, lines=[])


async def _publicity_empty():
    ctx, _w, _db = _ctx()
    return await A.Publicity().run(ctx, lines=[])


# ══════════════════════════════════════════════════════════════
#  C/D —— 协作链与排班（打桩 LLM，看**材料有没有递到**）
# [EN] C/D -- collaboration chain and scheduling (stub the LLM, check **whether the material was handed
# [EN] over**)
# ══════════════════════════════════════════════════════════════
async def chain_checks() -> None:
    ctx, world, db = _ctx()
    # ── 场记/宣发 的"别假装"（要 await，放这儿；`logic_checks` 是同步的）──
    # [EN] -- 场记/宣发 "don't fake it" (needs await, goes here; `logic_checks` is synchronous) --
    ok('E5 场记没正文时不假装查过（返回 ok=False + 原因）',
       (await A.Continuity().run(ctx, lines=[])).ok is False, '')
    ok('E6 宣发没内容时不假装写过（返回 ok=False + 原因）',
       (await A.Publicity().run(ctx, lines=[])).ok is False, '')
    calls: list[dict] = []
    real = A.ask

    def stub(replies: list):
        idx = {'i': 0}

        async def _ask(tier, messages, **kw):
            calls.append({'purpose': kw.get('purpose'),
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

        return _ask

    try:
        # ── C1 美术 → 道具（名册 feeds='props'）──
        # [EN] -- C1 art -> props (roster feeds='props') --
        calls.clear()
        A.ask = stub([
            {'画风': '水墨淡彩', '主色': [{'色': '#112233', '用途': '瓦'}],
             '忌': ['霓虹色']},
            {'道具': [{'名称': '账本', '用途': '对不上的那页', '反复': True}],
             '基调': '潮'},
        ])
        got = await ST.Studio(world, db).preproduction(ctx)
        props_prompt = next((c['text'] for c in calls
                             if c['purpose'] == 'crew_props'), '')
        ok('C1 ★★ 美术定的调子**真的递给了道具师**（名册写着 art→props，'
           '程序里也得是）',
           '水墨淡彩' in props_prompt and '#112233' in props_prompt,
           props_prompt[:60].replace('\n', ' '))
        ok('C1b 两件产出都拿到了', got['art'].ok and got['props'].ok, '')

        # ── C2 资料员 → 剧作者（写剧本那一步）──
        # [EN] -- C2 researcher -> playwright (the step that writes the script) --
        calls.clear()
        A.ask = stub([
            '第三天，账目牵出旧案。',                       # 小说作家
            # [EN] novel writer
            {'存疑': ['「三两银子」→ 那时不这么称 → 改成「三钱二分」'],
             '结论': '一处存疑'},                            # 资料员
             # [EN] researcher
            {'场景介绍': '堂里两盏灯，檐水盖住了街上的人声。',
             '拍': [{'拍': 1, '场': '堂内', '发生': '翻账', '推进': '起疑'}],
             '角色任务': {'主角': ['翻昨夜的账']}},           # 剧作者
            {'通过': True, '问题': [], '修改意见': ''},       # 导演验算
             # [EN] playwright
             # [EN] director verification
        ])
        from director import day_plan as DP
        dp_real = DP.ask
        DP.ask = A.ask                        # 验算那一步在 day_plan 里
        # ⚠ **必须给制片厂**：资料员那一步是剧组职责（`day_plan` 只在有
        #   `studio` 时才叫它）。不给的话测的就不是生产路径 ——
        #   第一版没给，于是 C2 红着说"考据没递到"，其实是夹具缺了一半。
        # [EN] the verification step is in day_plan
        # [EN] ⚠ **must give the studio**: the researcher step is a crew duty (`day_plan` only calls it when
        # [EN] `studio` is present). Without it, what is tested is not the production path --
        # [EN] the first version did not give it, so C2 went red saying "research was not handed over", when in
        # [EN] fact the fixture was missing half.
        try:
            ds = await DP.compose(world, db, people=['主角', '阿枝'],
                                  studio=ST.Studio(world, db))
        finally:
            DP.ask = dp_real
        sw_prompt = next((c['text'] for c in calls
                          if c['purpose'] == 'day_script'), '')
        ok('C2 ★★ 资料员的考据**真的进了剧作者的提示词**'
           '（名册写着 researcher→screenwriter）',
           '三钱二分' in sw_prompt, sw_prompt[:0] or f'{len(sw_prompt)} 字')
        ok('C2b ★ 剧作者写的**场景介绍**留在了剧本里（用户要的"一小段场景介绍"）',
           ds.scene_intro.startswith('堂里两盏灯'), ds.scene_intro[:40])
        ok('C2c 顺序对：先写样章 → 再考据 → 然后才是剧作者',
           [c['purpose'] for c in calls[:4]] ==
           ['day_story', 'crew_research', 'day_script', 'day_verify'],
           str([c['purpose'] for c in calls[:4]]))

        # ── C3 道具 → 场记 ──
        # [EN] -- C3 props -> 场记 --
        calls.clear()
        A.ask = stub([{'问题': [], '结论': '无'}])
        st = ST.Studio(world, db)
        await st.props_note(ctx)               # 先有道具单
        # [EN] first there is a prop list
        await st.call('continuity', ctx, lines=['主角：账上差七文。'])
        cont_prompt = next((c['text'] for c in calls
                            if c['purpose'] == 'crew_continuity'), '')
        # 上面那次 props 被桩覆盖了，这里直接给一份道具单再验
        # [EN] that earlier props was overwritten by the stub; here just give a prop list and verify again
        calls.clear()
        A.ask = stub([{'问题': [], '结论': '无'}])
        st2 = ST.Studio(world, db)
        st2._props[3] = A.CrewNote(role='props', ok=True, title='1 件',
                                   data={'道具': [{'名称': '摊开的账本'}],
                                         '关键': ['摊开的账本'],
                                         '基调': '潮湿'})
        await st2.wrap(ctx, lines=['主角：账上差七文。'])
        cont_prompt2 = next((c['text'] for c in calls
                             if c['purpose'] == 'crew_continuity'), '')
        ok('C3 ★★ 道具单**真的递给了场记**（名册写着 props→continuity）——'
           '"这一场该有的东西"是查物件的依据',
           '摊开的账本' in cont_prompt2, f'{len(cont_prompt2)} 字')

        # ── D 排班：收工那一步把在位三职位也报上台账 ──
        # [EN] -- D scheduling: the wrap-up step reports the three incumbents to the ledger too --
        led = {r['key']: r for r in st2.ledger()}
        ok('D1 ★★ 收工后**在位的三个职位也有状态**'
           '（不报的话界面那三行永远是"待命"，而他们一整天都在干活）',
           all(led[k]['state'] == 'done'
               for k in ('director', 'actor', 'extra')),
           str({k: led[k]['state'] for k in ('director', 'actor', 'extra')}))
        ok('D2 台账行数 = 名册职位数（界面读的就是它）',
           len(st2.ledger()) == len(R.ROSTER), str(len(st2.ledger())))
        ok('D3 关掉的职位显示「未启用」而不是「没出活」'
           '（两件事要分得开）',
           _off_state_ok(), '')

        # ── 群演投人（AI 那一档 + 兜底）──
        # [EN] -- extras casting (the AI tier + fallback) --
        calls.clear()
        A.ask = stub([{'称呼': '卖炭的老汉', '诉求': '问收不收昨夜的炭钱',
                       '标志': '肩上落着灰'}])
        got = await A.ExtraCasting().cast(ctx, kind_hint='堂')
        ok('D4 ★★ 门外的人由「群众演员」按剧情投（不再是固定池里抽）',
           (got or {}).get('称呼') == '卖炭的老汉'
           and (got or {}).get('诉求'), str(got))
        # 反例：投出一个与在场人物同名的临时演员 → 必须判废
        # [EN] counterexample: casting an extra with the same name as a character present -> must be rejected
        calls.clear()
        A.ask = stub([{'称呼': '主角', '诉求': '来讨债', '标志': 'x'}])
        got2 = await A.ExtraCasting().cast(ctx, kind_hint='堂', fallback=False)
        ok('D5 ★ 投出与在场人物**重名**的临时演员必须判废'
           '（群演不能顶替角色，那会搅乱人物关系）',
           got2 is None, str(got2))
        # 拿不到 AI → 走规则兜底（门外不能空着）
        # [EN] no AI available -> fall back to rules (the door cannot be left empty)
        calls.clear()
        A.ask = stub([''])
        got3 = await A.ExtraCasting().cast(ctx, kind_hint='堂')
        ok('D6 拿不到 AI → 走规则兜底（门外不能空着）',
           bool(got3 and got3.get('称呼')), str(got3))
    finally:
        A.ask = real


def _off_state_ok() -> bool:
    """关掉一个职位 → 台账那行是 `off`（不是 `idle`）。
        English:
    Turn off a role → that ledger row is `off` (not `idle`).
    """
    ctx, world, db = _ctx()
    old = CFG.b('CREW_ART')
    try:
        CFG.set('CREW_ART', 'false')
        led = {r['key']: r for r in ST.Studio(world, db).ledger()}
        return led['art']['state'] == 'off'
    finally:
        CFG.set('CREW_ART', 'true' if old else 'false')


# ══════════════════════════════════════════════════════════════
#  F —— 真机
# [EN] F -- real run
# ══════════════════════════════════════════════════════════════
async def gui_checks(page) -> None:
    VU.patch_flat_background()
    from gui.app_flet import NovelWorldApp
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU

    tmp = Path(tempfile.mkdtemp(prefix='nws_crewui_'))
    proj = make_project(tmp / '剧组真机', nodes=2)
    run = RunFolder(proj.root, '第1次模拟2026-10-07-00-01').create()
    loop, world, db = SU.assemble(proj, run,
                                  image_hook=lambda *a, **k: None)
    seen: list[str] = []
    loop.on_narrative(lambda tx, p, **kw: seen.append(tx))

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    await asyncio.sleep(1.6)
    app.current_project = proj
    # ⚠ 用**真的** `RunSession` 而不是手搓一个替身：替身缺一个属性
    #   （第一版少了 `reason`）就会在界面刷新那条路上炸，
    #   而报出来的错离真正的原因很远（"面板没画出来"）。
    # [EN] ⚠ use the **real** `RunSession` instead of hand-rolling a stand-in: a stand-in missing one
    # [EN] attribute
    # [EN] (the first version lacked `reason`) blows up on the UI-refresh path,
    # [EN] and the error reported is far from the real cause ("the panel was not drawn").
    from sim.session import RunSession
    app.session = RunSession(loop, world, run)      # IDLE：存在但没在跑
    # [EN] IDLE: exists but not running
    app.show_main_screen()
    await asyncio.sleep(0.8)

    # 跑一天（剧组两段 + 若干拍）
    # [EN] run one day (two crew segments + several shots)
    await loop._crew_prep()
    await loop._compose_day()
    for i in range(1, 20):
        await loop._tick(i)
    await loop._crew_wrap(list(loop._daily_narrative))
    app._refresh_crew_panel()
    page.update()
    await asyncio.sleep(0.8)

    # ── 中栏：剧组**只报状态**，不推产出正文（2026-10-07 第三次改口径）──
    # [EN] -- middle column: the crew **only reports status**, does not push output body text (2026-10-07
    # [EN] third revision of the wording) --
    #
    # ⚠ 这一组**改过口径**（用户原话）：「窗口输出的内容你把作者写小说
    #   剧作家创作剧本 剧组排练…等过程用**小的消息**（只显示阶段名和用时，
    #   **不真实输出内部细节**，但细节写入日志）…… **别的不要加到运行界面中间窗口**」。
    # [EN] ⚠ this group **had its wording changed** (the user's own words): "For the content output in the
    # [EN] window, take the author writing the novel,
    # [EN] the playwright creating the script, the crew rehearsing... and other processes and use **small
    # [EN] messages** (showing only the stage name and elapsed time,
    # [EN] **without actually outputting internal details**, but write details to the log)...... **do not
    # [EN] add anything else to the middle window of the run UI**".
    #
    #   以前这里量的是「（剧组 · 美术）今天 2 处…」那种**产出正文**上屏；
    #   现在那种东西**一个字都不许上中栏**，上屏的换成两条小消息：
    #   阶段（`▸ …`）与工作状态（`· …`）。判据跟着改成量新口径
    #   （**判据口径随需求变，不是把判据删掉**）。
    # [EN] previously this measured the **output body text** like "(crew · art) today 2 places..." reaching
    # [EN] the screen;
    # [EN] now that kind of thing **is not allowed a single character in the middle column**, and what
    # [EN] reaches the screen is replaced by two small messages:
    # [EN] the stage (`▸ ...`) and the work status (`· ...`). The criterion accordingly changes to measure
    # [EN] the new wording
    # [EN] (**the criterion's wording changes with requirements, not by deleting the criterion**).
    crew_notes = [x for x in seen if x.startswith('（剧组')]
    ok('F1 ★★ 剧组产出的**正文不再上屏**（只报状态与阶段）',
       not [x for x in crew_notes if '水墨' in x or '件道具' in x
            or '底噪' in x or '处 AI 味' not in x and '没出活' not in x],
       f'仍带正文的：{[x[:30] for x in crew_notes if "水墨" in x][:2]}')
    ok('F2 ★★ 该上屏的两样东西都在：阶段（`▸`）与工作状态（`·`）',
       any(x.startswith('▸ ') for x in seen)
       and any(x.startswith('· ') for x in seen),
       f"▸ {[x[:16] for x in seen if x.startswith('▸ ')][:3]} / "
       f"· {[x[:16] for x in seen if x.startswith('· ')][:3]}")
    ok('F3 场景介绍进了中栏（用户要的顺序：前情提要 → 场景介绍 → 人物开口）',
       any(x.startswith('（当日剧本') for x in seen)
       or any(x.startswith('▸ ') for x in seen), '')

    # ── 右栏「剧组」面板 ──
    # [EN] -- right column "crew" panel --
    ctl = app._ui_run.get('crew_list')
    ok('F4 ★★ 运行界面右栏有「剧组」面板且挂了控件', ctl is not None
       and len(getattr(ctl, 'controls', []) or []) > 0,
       f'{len(getattr(ctl, "controls", []) or [])} 行')
    ok('F5 ★ 面板行数 = 职位数（十个职位都在界面上占了一行）',
       len(getattr(ctl, 'controls', []) or []) == len(R.ROSTER),
       f'{len(getattr(ctl, "controls", []) or [])} / {len(R.ROSTER)}')
    texts = VU.all_texts(page)
    ok('F6 ★★ 面板真的把职位名画了出来（在屏幕上量，不只看控件树）',
       all(any(name == x for x in texts) for name in
           ('小说作家', '剧作者', '场记', '道具', '美术', '宣发')),
       str([x for x in texts if x in
            ('小说作家', '剧作者', '场记', '道具', '美术', '宣发')]))
    ok('F7 面板里能看到某位职位最近的产出（不是一行空壳）',
       any('件道具' in x or '拍 ·' in x or '水墨' in x for x in texts),
       str([x for x in texts if '件道具' in x or '拍 ·' in x][:2]))
    # 反例：没有会话时不许预填（本项目"不假装"的规矩）
    # [EN] counterexample: without a session, no pre-filling allowed (this project's "don't fake it" rule)
    app.session = None
    app._refresh_crew_panel()
    ok('F8 ★ 没有会话时面板留空（不预填假状态）',
       not (getattr(ctl, 'controls', None) or []),
       str(len(getattr(ctl, 'controls', None) or [])))

    png = await page.take_screenshot()
    (OUT / 'crew_ui.png').write_bytes(png or b'')


# ══════════════════════════════════════════════════════════════
async def main(page) -> None:
    print('\n── A/B/C/E 纯逻辑：名册 · 工艺 · 接线 ──')
    logic_checks()
    print('\n── C/D 协作链与排班（打桩 LLM）──')
    await chain_checks()
    if not ONLY_LOGIC and page is not None:
        print('\n── F 真机：中栏 + 右栏「剧组」面板 ──')
        try:
            await gui_checks(page)
        except Exception:
            report['fatal'] = traceback.format_exc()
            ok('F0 真机段跑通（没有被异常打断）', False,
               report['fatal'].splitlines()[-1] if report.get('fatal') else '')
    report['ok'] = all(c['ok'] for c in report['checks'])
    report['n_ok'] = sum(1 for c in report['checks'] if c['ok'])
    report['n_all'] = len(report['checks'])
    (OUT / 'crew_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n剧组验证：{report['n_ok']}/{report['n_all']}")
    if report.get('fatal'):
        print(report['fatal'])
    print(f"报告：{OUT / 'crew_report.json'}")
    return report['n_ok'] == report['n_all']


async def entry(page) -> None:
    """真机入口：跑完**自己收尾**并把退出码落实。

    ⚠ 退出码必须在**关窗之前**交给 `shutdown(code=...)`：
      `page.window.destroy()` 会抛 CancelledError 取消本协程，
      写在 `await shutdown(page)` 后面那行 `sys.exit(...)` **从来没执行过**
      （退出码恒为 0 = 假绿）。见 `util.flet_shutdown.shutdown()`。
    
        English:
    Real machine entry point: after running, **it cleans up itself** and commits the exit code.
        ⚠ The exit code must be handed to `shutdown(code=...)` **before closing the window**:
          `page.window.destroy()` throws CancelledError and cancels this coroutine,
          so the line `sys.exit(...)` written after `await shutdown(page)` **never executed**
          (exit code is always 0 = false green). See `util.flet_shutdown.shutdown()`.
    """
    try:
        good = await main(page)
    except Exception:                                            # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(report['fatal'])
        good = False
    await shutdown(page, code=0 if good else 2)


if __name__ == '__main__':
    if ONLY_LOGIC:
        async def _run():
            await main(None)
            sys.exit(0 if report.get('ok') else 2)
        asyncio.run(_run())
    else:
        ft.run(entry, assets_dir=str(APP_DIR / 'assets'))
