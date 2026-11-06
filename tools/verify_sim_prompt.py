# -*- coding: utf-8 -*-
"""验证：第一轮推演优化真的接上了（世界观进 prompt / 动作落地 / 截断可见）。

这一轮改的三件事都是"**代码里早就写好、但从来没人调用**"或"**从来没写回世界**"
那类问题 —— 光看代码像是对的，所以每条都要有能红的判据。

用法：.venv/Scripts/python.exe tools/verify_sim_prompt.py

English:
Verification: the first round of deduction optimization is really wired up (worldview into
prompt / action lands / truncation visible).
The three things changed this round are all of the "**written in the code long ago, but nobody
ever called it**" or "**never written back to the world**"
kind of problem —— just looking at the code it seems right, so each one needs a criterion that
can go red.
Usage: .venv/Scripts/python.exe tools/verify_sim_prompt.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG                                    # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('OUTPUT_FORMAT', 'script')

from i18n import set_lang                                 # noqa: E402
set_lang('zh')

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


async def main() -> None:
    from verify_ui_common import isolate_projects_dir, safe_rmtree
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim.setup import assemble
    from agent.core import llm as agent_llm, Agent, Action
    import agent.core as AC

    tmp = Path(tempfile.mkdtemp(prefix='nws_simprompt_'))
    isolate_projects_dir(tmp / 'Projects')
    try:
        proj = make_project(tmp / '提示词验证')
        run = RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
        loop, world, _ = assemble(proj, run)
        world.progress_nodes = []

        # 给世界一点可辨认的内容，好断言它真的进了 prompt
        # [EN] Give the world something recognizable, so we can assert it actually made it into the prompt
        world.worldview_text = '临河小城，常年落雨，人情密、口风紧。' * 3
        world.style_card = {'句长': '中短句', '叙事距离': '限知',
                            'AI腔禁词表': ['首先', '值得注意的是', '在这个过程中']}
        world.genre_card = {'主题材': '悬疑', '结构': '单元剧', '频道': '男频'}
        loop.agents[0].ps.secret = '腕上那道旧痕的来历'   # 只该角色自己知道
        # [EN] only that character should know it

        # ── 拦下发出去的 prompt（这是唯一能证明"真的注入了"的办法）──
        # [EN] ── intercept the outgoing prompt (this is the only way to prove it was "really injected") ──
        seen: list[dict] = []
        real_chat = agent_llm.chat

        async def spy(tier, messages, **kw):
            seen.append({'purpose': kw.get('purpose', ''),
                         'text': '\n'.join(str(m.get('content', '')) for m in messages)})
            return await real_chat(tier, messages, **kw)

        agent_llm.chat = spy
        try:
            agent = loop.agents[0]
            await agent.decide()
            # ⚠ 直接调 `_inject_event`：`on_tick` 要满足「张力<0.4 且掷骰命中」
            #   才发请求，随机 —— 用它的话 ev 常常是空的，判据就变成恒真了
            #   （踩过：第一版写成 `'x' in ev if ev else True`，永远绿）。
            # [EN] ⚠ calling `_inject_event` directly: `on_tick` must satisfy "tension < 0.4 and dice roll hits"
            # [EN] only then is a request sent, random —— if we use it, ev is often empty, and the criterion
            # [EN] degenerates into a tautology
            # [EN] (been burned: the first version was written as `'x' in ev if ev else True`, always green).
            await loop.director._inject_event()
        finally:
            agent_llm.chat = real_chat

        dec = next((s['text'] for s in seen if s['purpose'] == 'agent_decide'), '')
        ev = next((s['text'] for s in seen if s['purpose'] == 'director_event'), '')
        report['decide_prompt_head'] = dec[:600]
        ok('A1 角色决策的 prompt 里带上了**世界观**（原来是死代码）',
           '临河小城' in dec, dec[:120].replace('\n', '⏎'))
        ok('A1b 带上了**风格卡**（含 AI 腔禁词表）',
           '禁词' in dec and '首先' in dec, dec[:200].replace('\n', '⏎'))
        ok('A1c 带上了**类型卡**', '悬疑' in dec, '')
        ok('A2 导演的事件 prompt 里也带上了世界观（事件要贴得住这本小说）',
           '临河小城' in ev, ev[:160].replace('\n', '⏎'))
        ok('A3 导演的 prompt 里**没有**角色自己的秘密（它不该知道）',
           ev and '腕上那道旧痕的来历' not in ev, ev[:200].replace('\n', '⏎'))

        # ── 动作落地 ──
        # [EN] ── action lands ──
        ps = agent.ps
        ps.location = world.scene
        n_before = len(loop.agents)
        ok('B0 夹具就绪：至少一位前台人物', n_before >= 1, n_before)

        # ① move：位置真的变
        # [EN] ① move: position actually changes
        loop._apply_action(agent, Action(verb='move', target='后院井边'))
        ok('B1 move 真的写进了人物位置（原来 move 是空操作）',
           ps.location == '后院井边', ps.location)

        # ② emote：记的是**自然语言神态**，且**不许**污染数值情绪字典
        #    （踩过：第一版往 `ps.emotion['神色']` 塞字符串 → 下一次
        #     `_emotion_str` 做 `v > 0.5` 比较当场 TypeError，整个 RunLoop 停摆。
        #     所以这条判据的后半句就是那个 bug 的绊线。）
        # [EN] ② emote: records **natural-language demeanor**, and must **not** pollute the numeric emotion
        # [EN] dict
        # [EN] (been burned: the first version stuffed a string into `ps.emotion['神色']` → the next time
        # [EN] `_emotion_str` did `v > 0.5` comparison and immediately TypeError'd, the whole RunLoop stalled.
        # [EN] So the second half of this criterion is the tripwire for that bug.)
        loop._apply_action(agent, Action(verb='emote', target='强作镇定'))
        ok('B2 emote 记进"神态"，且情绪字典里仍然全是数值',
           getattr(ps, 'mood_note', '') == '强作镇定'
           and all(isinstance(v, (int, float)) for v in ps.emotion.values()),
           f'mood={getattr(ps, "mood_note", None)} emotion={ps.emotion}')

        # ③ 还有人在原地 → **不许**换场（反例）
        # [EN] ③ someone is still in place → **not allowed** to switch scenes (counterexample)
        others = [a for a in loop.agents if a is not agent]
        for a in others:
            a.ps.location = world.scene
        scene0 = world.scene
        loop._maybe_shift_scene()
        ok('B3 还有人在原地时**不换场**（这一场戏没完）',
           world.scene == scene0, f'{scene0} → {world.scene}')

        # ④ 目标**不是设定里的地点** → 也不许换场（模型随口给的词不当场景名）
        # [EN] ④ target is **not a location in the setting** → also not allowed to switch scenes (the model's
        # [EN] offhand word is not a valid scene name)
        world.place_names = ['临河茶肆', '城外渡口']
        for a in loop.agents:
            a.ps.location = '门外'
        loop._maybe_shift_scene()
        ok('B4 目标不在设定地点表里 → **不换场**（「门外」「对方」不是场景名）',
           world.scene == scene0, f'{scene0} → {world.scene}')

        # ⑤ 全场走光 + 去的是**设定里真有的地点** → 换场（分幕的触发之一）
        # [EN] ⑤ everyone has left + the destination is **a location that really exists in the setting** →
        # [EN] switch scenes (one of the act-break triggers)
        for a in loop.agents:
            a.ps.location = '城外渡口'
        loop._maybe_shift_scene()
        ok('B5 全场转移到设定里的地点 → 场景跟着换（这才叫换场）',
           world.scene == '城外渡口', f'{scene0} → {world.scene}')

        # ⑥ interact 不该乱改状态
        # [EN] ⑥ interact should not arbitrarily change state
        before = (ps.location, dict(ps.emotion))
        loop._apply_action(agent, Action(verb='interact', target='擦紫砂壶'))
        ok('B5 interact 不碰世界状态（只有它真的知道的才落地）',
           (ps.location, dict(ps.emotion)) == before, '')

        # ── 截断要说一声 ──
        # [EN] ── truncation must be announced ──
        import inspect
        src = inspect.getsource(AC.Agent.decide)
        ok('C1 角色决策开了 return_meta 且截断时会告警',
           "return_meta=True" in src and 'truncated' in src,
           '')

        # ── 世界前缀本身就该是"世界观 + 类型 + 风格禁词" ──
        # [EN] ── the world prefix itself should be "worldview + genre + style banned words" ──
        pre = world.world_prefix()
        ok('D1 world_prefix() 三样都有（它是这次的注入源）',
           '[世界观]' in pre and '[类型]' in pre and '[风格]' in pre,
           pre[:160].replace('\n', '⏎'))
    finally:
        safe_rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except BaseException:                                    # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()

    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'sim_prompt_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"断言 {len(report['checks']) - len(bad)}/{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1200:])
    print('ok:', report['ok'])
    raise SystemExit(0 if report['ok'] else 2)
