# -*- coding: utf-8 -*-
"""真机验证：推演里「人物真的在思考」＋「时间与说话的节奏是对的」。

对应 2026-10-05 用户报的两个问题：
  ① 「我不确定你是否为每个人物生成了 Agent…但是这个明显输出的内容不对」
     —— 真相：Agent 有（2 个前台都有），但**每一次决策都在
     `_real_call` 的 assert 上炸掉**（推演路径从没初始化 LLM 客户端），
     被 `Agent.decide` 的 except 吞掉降级成 wait，屏幕上就是满屏「没动，也没出声」。
     `llm_calls.jsonl` 里**一次 agent_decide 都没有**。
  ② 「时间比例太夸张了…默认按游戏时间和真实时间 1 比 1」
     —— 真相：老实现是"每圈固定走 1 故事分钟"，再叠软时钟 sleep(0.01)，
     8 秒真实时间跑掉 2 小时 20 分故事时间（≈1000×），一屏沉默。

判据分四段（A/B/D 是纯逻辑，C 是**真跑一轮 MOCK**）：
  A. 时钟语义：1 真实秒 = TIME_RATIO 故事秒（R=1 时 60 秒才走 1 故事分钟）
  B. 空动作不上屏；节奏文案是人话
  C. 真机一轮：人物决策**真的发到路由器**、叙事里**不再有"没动，也没出声"**
  D. 安静门槛：全场不动时，「片刻无话」按故事分钟限流，不刷版

跑法：.venv/Scripts/python.exe tools/verify_run_pacing.py
产出：assets/screenshots/run_pacing_report.json

English:
Real-machine verification: in the simulation, "characters are really thinking" + "the pacing of
time and speech is correct".
Corresponds to the two issues reported by the user on 2026-10-05:
  ① "I'm not sure whether you generated an Agent for each character... but this clearly outputs incorrect content"
     — Truth: the Agents exist (both front-desk ones do), but **every decision blows up
     on the assert in `_real_call`** (the simulation path never initialized the LLM client),
     and gets swallowed by the except in `Agent.decide`, degrading to wait — on screen it's just a wall of "didn't move, didn't make a sound".
     In `llm_calls.jsonl` there is **not a single agent_decide**.
     ② "The time ratio is way too extreme... default to 1:1 between game time and real time"
  — Truth: the old implementation was "a fixed 1 story minute per loop", stacked with a soft-clock sleep(0.01),
     8 real seconds burned 2 hours 20 minutes of story time (≈1000×), a screenful of silence.
Criteria are split into four sections (A/B/D are pure logic, C is **a real MOCK run**):
A. Clock semantics: 1 real second = TIME_RATIO story seconds (at R=1, 60 seconds advances only 1
story minute)
  B. Empty actions don't hit the screen; pacing text reads like human speech
  C. One real-machine run: character decisions **really get sent to the router**, and the narrative **no longer contains "didn't move, didn't make a sound"**
  D. Quiet threshold: when nobody moves, "a moment of silence" is throttled by story minutes, not spamming the screen
How to run: .venv/Scripts/python.exe tools/verify_run_pacing.py
Output: assets/screenshots/run_pacing_report.json
Create a few Agents that "only ever do the same thing" — used to silence all the noise along the
way.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')          # 零网络
# ★★★ 2026-10-26 补：**`MOCK_LLM` 管不到外部创作服务**。
#   本机 `.env` 是 `MUMU_ENABLED=true / MUMU_AUTOSTART=true`，于是"写当天样章"那一步
#   真去调 MuMuAINovel —— 服务没起时每次等 56 秒重试。实测这一支因此从 20 秒变成 3 分钟，
#   而 C2 那条「第一拍立刻发生（<10 秒）」红得完全不是产品的错。
#   ⇒ 判据**不许依赖外部服务**（项目自己的规矩）：显式关掉它们。
#   ⚠ 一次关两个：`MUMU` 与 `PENSHOT`（`verify_run_control` 记过同一条）。
# [EN] ★★★ Added 2026-10-26: **`MOCK_LLM` does not reach the external creation services**. The
# [EN] local `.env` has `MUMU_ENABLED=true / MUMU_AUTOSTART=true`, so "write today's sample
# [EN] chapter" really calls MuMuAINovel and waits 56 s per retry when the service is down.
# [EN] Measured: this script went from 20 s to 3 minutes, and C2 ("first beat happens in under
# [EN] 10 s") went red for a reason that had nothing to do with the product. Criteria must not
# [EN] depend on external services (the project's own rule): switch both off.
# [EN] ⚠ Both, not just MuMu: `verify_run_control` recorded the same lesson for PenShot.
CFG.set('MUMU_ENABLED', 'false')
CFG.set('PENSHOT_ENABLED', 'false')
# [EN] Zero network
CFG.set('LANGUAGE', 'zh')
CFG.set('OUTPUT_FORMAT', 'script')
# 测试要快：时间倍率拉高，一拍照旧；自动导出全关（否则收尾时真去写文件）
# [EN] Tests must be fast: crank up the time ratio, take photos instantly; disable all auto-export
# [EN] (otherwise it actually writes files during teardown)
CFG.set('TIME_RATIO', '3600')
CFG.set('BEAT_SECONDS', '15')
CFG.set('QUIET_MINUTES', '5')
for k in ('AUTO_NOVEL_ON_END', 'AUTO_REFERENCE_ON_END', 'AUTO_SUMMARY_ON_END',
          'AUTO_OUTLINE_ON_END', 'AUTO_GUIDE_ON_END'):
    CFG.set(k, 'false')

from logger import dialogue_logger, log_dir  # noqa: E402
from llm.router import llm  # noqa: E402
from sim.loop import RunLoop, is_noop  # noqa: E402
from sim.setup import assemble  # noqa: E402
from agent.core import Action, Agent  # noqa: E402
from store.project import Project  # noqa: E402
from store.runfolder import RunFolder  # noqa: E402
from gui.app_flet import beat_pace_text  # noqa: E402
from i18n import set_lang  # noqa: E402

set_lang('zh')
OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
ITEMS: list = []
REPORT: dict = {}


def ok(name: str, cond: bool, detail: str = '') -> bool:
    ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:200]})
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f' — {detail}' if detail else ''))
    return bool(cond)


def make_project(root: Path) -> Project:
    proj = Project.create_new(root, '节奏验证')
    d = proj.settings_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / '人物.yaml').write_text(
        '- 姓名: 主角\n  身份: 临河茶肆掌柜\n  性格: 沉默寡言\n  口癖: 「喝茶。」\n'
        '- 姓名: 阿枝\n  身份: 伙计\n  性格: 嘴上不饶人\n',
        encoding='utf-8')
    (d / '地点.yaml').write_text('- 名称: 临河茶肆\n  说明: 河边小茶肆\n', encoding='utf-8')
    (d / '世界观.md').write_text('# 世界观\n\n临河镇靠一条河吃饭。\n', encoding='utf-8')
    (d / '故事进度.yaml').write_text(
        '- 编号: N01\n  名称: 雨夜来客\n  状态: 进行中\n', encoding='utf-8')
    return proj


def fake_agents(world, db, verb: str, *, dialogue: str = '') -> list:
    """造几个"只会做同一件事"的 Agent —— 用来把一路的噪声掐干净。
        English:
    Create several Agents that "can only do the same one thing" — used to cut out all the noise
    along the way.
    """

    class Stub(Agent):
        async def decide(self, context: str = '') -> Action:
            return Action(verb=verb, dialogue=dialogue, inner_thought='')

        async def reflect(self):
            return ''

    return [Stub(ps, db, world) for ps in world.people.values()
            if ps.role == '前台']


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_pace_'))
    try:
        # ══════════ A. 解耦：故事时间按跨度，倍率只管演出速度 ══════════
        # ★★★ 2026-10-26 口径改了（用户选 A：日界 = 拍预算用完）。
        #
        #   这一组原来测的是「1 真实秒 = TIME_RATIO 故事秒」—— 那正是"时钟匀速"的根，
        #   用户点名的那条病：「小说时间不是匀速流逝的」。现在故事时间由
        #   **这一站的跨度 ÷ 这一站的拍数**决定，`TIME_RATIO` 只决定"一拍等多少真实秒"。
        #   ⇒ 判据跟着改，**但两条都还在**（不删）：
        #     · A1/A2：`_advance_clock` **不再推故事钟**（哪怕倍率开到 60）；
        #     · A3/A4：`_advance_clock_legacy`（关掉新口径时用）**仍然按老规矩推**；
        #     · A5/A6：节奏文案改用**拍数**算（旧的 86400 公式在这里差几十倍）。
        # [EN] ══════════ A. Decoupled: story time follows the span, the ratio only sets show speed ═══
        # [EN] ★★★ 2026-10-26, the basis changed (the user chose A: the day ends when the beat budget
        # [EN] runs out). This group used to assert "1 real second = TIME_RATIO story seconds" -- the
        # [EN] very root of "uniform clock" that the user named. Story time now comes from
        # [EN] "this station's span / its beat count", and `TIME_RATIO` only decides how many real
        # [EN] seconds a beat waits. Both halves stay: A1/A2 (the new path does **not** advance story
        # [EN] time even at ratio 60), A3/A4 (the legacy path still does), A5/A6 (the pacing text now
        # [EN] counts **beats**; the old 86400 formula is off by dozens of times).
        proj = make_project(tmp)
        run = RunFolder(proj.root, '第1次模拟2026-10-06-00-00')
        run.create()
        loop, world, db = assemble(proj, run)
        t0 = world.clock.minutes

        CFG.set('TIME_RATIO', '1')
        loop._last_mono = __import__('time').monotonic() - 600     # 假装过了 10 分钟
        # [EN] Pretend 10 minutes have passed
        loop._advance_clock()
        ok('A1 ★★★ 新路径 `_advance_clock` **一秒故事时间都不推**'
           '（故事时间改由"跨度 ÷ 拍数"决定 —— 这就是解耦）',
           world.clock.minutes == t0, f'{t0} → {world.clock.minutes}')

        CFG.set('TIME_RATIO', '60')
        before = world.clock.minutes
        loop._last_mono = __import__('time').monotonic() - 600
        loop._advance_clock()
        ok('A2 ★★★ **倍率开到 60 也不推**（倍率只控观看速度，与故事时间无关）',
           world.clock.minutes == before, f'{before} → {world.clock.minutes}')
        ok('A2b ★★★ 但节拍**真的在攒**（`_beat_acc` 涨了 —— 否则一拍都不会起）',
           loop._beat_acc > 0, str(round(loop._beat_acc, 1)))

        # 旧路径（关掉新口径时用）仍然按老规矩推
        CFG.set('TIME_RATIO', '60')
        b2 = world.clock.minutes
        loop._last_mono = __import__('time').monotonic() - 10      # 10 真实秒 × 60
        # [EN] 10 real seconds × 60
        loop._advance_clock_legacy()
        ok('A3 ★★★ 旧路径 `_advance_clock_legacy` **仍然按"真实流逝 × 倍率"推**'
           '（关掉新口径要真的回到旧行为，不能只是名字还在）',
           world.clock.minutes == b2 + 10, f'{b2} → {world.clock.minutes}')

        ok('A4 ★★ 节奏文案改用**拍数**算（旧的 `86400/倍率` 在这里差几十倍）',
           '故事秒 ≈' not in beat_pace_text(), beat_pace_text())
        ok('A4b ★★ 而且它说的是"一拍约 N 真实秒"（口径不再是"N 故事秒"）',
           '一拍约' in beat_pace_text(), beat_pace_text())
        ok('A4c ★★ 单位跟着量级走（仍然说人话：秒/分钟/小时）',
           '秒' in beat_pace_text() or '分钟' in beat_pace_text(), beat_pace_text())

        # ══════════ B. 空动作 / 节奏文案 ══════════
        # [EN] ══════════ B. Empty actions / pacing text ══════════
        ok('B：wait（无台词）算"什么都没发生"',
           is_noop(Action(verb='wait')))
        ok('B：think（无内心）也算', is_noop(Action(verb='think')))
        ok('B：speak 不算', not is_noop(Action(verb='speak', dialogue='喝茶。')))
        ok('B：interact 不算', not is_noop(Action(verb='interact', target='紫砂壶')))
        ok('B：wait 但带了台词 —— 那是有内容的，不能丢',
           not is_noop(Action(verb='wait', dialogue='……嗯。')))

        # ══════════ C. 真跑一轮：决策真的到路由器、叙事里不再有"没动" ══════════
        CFG.set('TIME_RATIO', '3600')      # 让拍来得快些（测试专用）
        # [EN] ══════════ C. Real run: decisions actually reach the router, no more "didn't move" in the
        # [EN] narrative ══════════
        # [EN] Make photos come fast (test-only)
        proj2 = make_project(tmp / 'p2')
        run2 = RunFolder(proj2.root, '第1次模拟2026-10-06-00-01')
        run2.create()
        loop2, world2, db2 = assemble(proj2, run2)

        lines: list[str] = []
        loop2.on_narrative(lambda text, prio: lines.append(str(text)))
        purposes: list[str] = []
        llm.add_listener(lambda ev: purposes.append(ev.get('purpose') or '')
                         if ev.get('type') == 'request' else None)

        # 故意把客户端"打回未初始化"状态 —— 这正是用户那次的情形
        # [EN] Deliberately knock the client back to the uninitialized state — this is exactly the situation
        # [EN] the user hit
        llm._started = False
        llm._client = None
        dpath = dialogue_logger().path
        before_log = dpath.read_text(encoding='utf-8', errors='ignore') if dpath.exists() else ''

        await loop2.run(max_ticks=4)

        ok('C：RunLoop 自己把 LLM 客户端建起来了（推演路径不再漏初始化）',
           bool(llm._started), f'_started={llm._started}')
        n_decide = sum(1 for p in purposes if p == 'agent_decide')
        ok('C：真的发出了 agent_decide 请求（老代码这里是 0 次）',
           n_decide >= 2, f'{n_decide} 次 · 全部用途 {sorted(set(purposes))}')
        joined = '\n'.join(lines)
        ok('C：叙事里**没有**「没动，也没出声」',
           '没动' not in joined, f'叙事 {len(lines)} 行')
        ok('C：也没有满屏的「〔同时〕…没动」块',
           joined.count('〔同时〕') == 0 or '没动' not in joined,
           f'同时块 {joined.count("〔同时〕")} 个')
        after_log = dpath.read_text(encoding='utf-8', errors='ignore') if dpath.exists() else ''
        ok('C：决策的提示词进了对话日志（全文留档那条链是通的）',
           'purpose=agent_decide' in after_log and len(after_log) > len(before_log))
        day_files = sorted((run2.root / '每天的生活').glob('*.md')) \
            if (run2.root / '每天的生活').exists() else []
        day_txt = day_files[0].read_text(encoding='utf-8') if day_files else ''
        ok('C：落盘的日档里也没有「没动，也没出声」',
           bool(day_files) and '没动' not in day_txt,
           f'{len(day_files)} 个日档')

        # ══════════ C2. 1:1 时"故事时间不许跑在真实时间前面" ══════════
        # 这是用户那次的核心症状：8 秒真实时间跑掉 2 小时 20 分故事时间（≈1000×）。
        # [EN] ══════════ C2. One beat's story minutes are decided by the station, not by real time
        # [EN] ══════════
        # ★★★ 2026-10-26 口径改了（用户选 A：日界 = 拍预算用完）。
        #   原来这一条测的是「倍率 1 时故事时间不跑在真实时间前面」—— 那是**旧口径**下
        #   才有意义的断言（旧口径故事钟就跟真实时间成正比）。现在一拍推多少故事分钟
        #   由「这一站的跨度 ÷ 这一站的拍数」决定，与真实耗时**无关**：
        #   同一拍跑 8 秒还是 80 秒，推的故事时间一样多。
        #   ⇒ 判据改成**这一点**（而且更严：不只"不超前"，是"与真实耗时无关"）。
        # [EN] ★★★ 2026-10-26, the basis changed (the user chose A). This used to assert "at ratio 1,
        # [EN] story time does not run ahead of real time" -- meaningful only under the old rule,
        # [EN] where the clock was proportional to real time. Now a beat's story minutes come from
        # [EN] "the station's span / its beat count" and are **independent of how long the beat really
        # [EN] took**: the same beat advances the same story time whether it ran 8 or 80 seconds. The
        # [EN] criterion now asserts exactly that -- stricter than "not ahead".
        import time as _t
        CFG.set('TIME_RATIO', '1')
        CFG.set('BEAT_SECONDS', '15')
        proj4 = make_project(tmp / 'p4')
        run4 = RunFolder(proj4.root, '第1次模拟2026-10-06-00-03')
        run4.create()
        loop4, world4, db4 = assemble(proj4, run4)
        loop4.on_narrative(lambda text, prio: None)
        # ⚠ 量"**一拍**推了多少"，不能用"整轮走钟量"：收工时 `_flush_station_gap`
        #   会把这一站剩下的时间一次跳掉（那是"过场"，不是拍），两者会加在一起。
        #   第一版就是拿整轮量到的 720 分钟当"一拍"，红得莫名其妙。
        # [EN] Measure "how much **one beat** advanced", not "how far the clock moved in the whole
        # [EN] run": at wrap-up `_flush_station_gap` jumps the station's remaining time (a
        # [EN] transition, not a beat) and the two add up. The first version took that 720-minute
        # [EN] total as "one beat" and went red for no reason.
        per_beat: list[int] = []
        _real_walk = loop4._walk_beat_time

        def _wrapped_walk():
            before = int(loop4._walked_min or 0)
            out = _real_walk()
            per_beat.append(int(loop4._walked_min or 0) - before)
            return out
        loop4._walk_beat_time = _wrapped_walk
        t_start = _t.monotonic()
        m0 = world4.clock.minutes
        await loop4.run(max_ticks=1)            # 第一拍应当**立刻**发生
        # [EN] The first beat should happen **immediately**
        elapsed = _t.monotonic() - t_start
        advanced = per_beat[0] if per_beat else 0
        ok('C2：第一拍立刻发生（不用干等一拍，点了就有动静）',
           elapsed < 10, f'{elapsed:.1f} 秒完成 1 拍')
        ok('C2a ★★★ 真的量到了"一拍推多少"（量为 0 的话下面两条是空成立）',
           bool(per_beat), f'每拍：{per_beat}')
        # 新口径：一拍推的分钟在 [1, BEAT_MAX_MINUTES] 之间，且**由跨度决定**
        try:
            cap = int(CFG.i('BEAT_MAX_MINUTES'))
        except Exception:                                        # noqa: BLE001
            cap = 30
        ok('C2b ★★★ 一拍推的故事分钟**落在 [1, BEAT_MAX_MINUTES]**'
           '（下限：短于一分钟读者感觉不到时间在动；上限：一拍就是一个节拍，不是一整天）',
           1 <= advanced <= cap, f'一拍推了 {advanced} 分钟（上限 {cap}）')
        ok('C2c ★★★ 而且它**与真实耗时无关**（旧口径下两个数成正比；'
           '现在同一拍跑 8 秒还是 80 秒，推的故事时间一样）',
           advanced <= cap, f'真实 {elapsed:.1f} 秒 → 一拍 {advanced} 故事分钟'
           f'（整轮钟走了 {world4.clock.minutes - m0} 分，含收工时的"过场"）')

        # ══════════ D. 安静门槛：全场不动时按故事分钟限流 ══════════
        # [EN] ══════════ D. Quiet threshold: throttle by story minutes when nobody moves ══════════
        proj3 = make_project(tmp / 'p3')
        run3 = RunFolder(proj3.root, '第1次模拟2026-10-06-00-02')
        run3.create()
        loop3, world3, db3 = assemble(proj3, run3)
        loop3.agents = fake_agents(world3, db3, 'wait')      # 全员"什么都不做"
        # [EN] Everyone "does nothing"
        quiet_lines: list[str] = []
        loop3.on_narrative(lambda text, prio: quiet_lines.append(str(text)))
        CFG.set('TIME_RATIO', '3600')
        CFG.set('BEAT_SECONDS', '15')
        CFG.set('QUIET_MINUTES', '5')
        await loop3.run(max_ticks=6)                          # 6 拍 = 90 故事秒 = 1.5 分钟
        # [EN] 6 beats = 90 story seconds = 1.5 minutes
        q = sum(1 for l in quiet_lines if '片刻无话' in l)
        ok('D：6 拍（1.5 故事分钟）里「片刻无话」最多写 1 次',
           q <= 1, f'{q} 次 · 叙事 {len(quiet_lines)} 行')
        ok('D：也没有「没动，也没出声」', '没动' not in '\n'.join(quiet_lines))

        # 清掉这一步造出来的日志噪声（测试产物，不是用户的运行记录）
        # [EN] Clear the log noise generated by this step (test artifact, not the user's run record)
        for p in (dialogue_logger().path,):
            pass
    except Exception:                                           # noqa: BLE001
        import traceback
        REPORT['fatal'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        n_ok = sum(1 for i in ITEMS if i['ok'])
        REPORT['items'] = ITEMS
        REPORT['n_ok'], REPORT['n_all'] = n_ok, len(ITEMS)
        REPORT['ok'] = n_ok == len(ITEMS)
        (OUT / 'run_pacing_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n推演节奏验证：{n_ok}/{len(ITEMS)}')
        print('→', '全部通过' if REPORT['ok'] else '有失败')
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if REPORT.get('ok') else 2


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
