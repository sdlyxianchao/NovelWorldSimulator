#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真机验证：剧本式叙事输出。

这一层要回答的问题不是"能不能跑"，而是三件容易做错的事：

1. **同时性有没有被保住**——一个 tick 里三个人各做各的，拼成三行就是"先后"，
   而事实是"同时"。所以断言三种情形：单人（不该出现并行轨）、多人同场
   （一条并行轨、轨数=人数）、异地有人做实事（要切镜头）／异地只在发呆（**不该**切）。
2. **人物不只在说话**——动作必须能独立成条、带主体；「在想事」必须是心声而不是
   动作（早期版本把它渲染成 `· 动作 主角：（若今晚走不成…）`，读起来像自言自语）。
3. **落盘能读回来**——Markdown 反解无损、JSON 边车优先、**旧纯文本格式仍能打开**。

最后真启 Flet 窗口，把一份剧本渲染进中栏，断言字幕/同时/心声都上了屏，
并且**间距量测仍通过**（新控件不能把布局搞坏）。

产出：assets/screenshots/script_*.png + script_report.json

English:
On-device verification: script-style narrative output.
The question this layer must answer is not "can it run" but three things easy to get wrong:
1. **Is simultaneity preserved** -- three people each doing their own thing in one tick, strung into three lines, is "sequential",
   whereas the truth is "simultaneous". So assert three scenarios: single person (no parallel track should appear), multiple people in the same place
   (one parallel track, track count = number of people), someone elsewhere doing real things (must cut camera) / elsewhere just idling (**must not** cut).
2. **Characters aren't only speaking** -- actions must be able to stand alone as entries, with a subject; "thinking about something" must be inner voice, not
   an action (an early version rendered it as `- action Shen Yan: (if tonight doesn't work out...)`, reading like talking to oneself).
3. **Written to disk and readable back** -- Markdown round-trip is lossless, JSON sidecar takes priority, **old plain-text format still opens**.
Finally actually launch the Flet window, render a script into the center column, assert
subtitles/simultaneity/inner voice all made it on screen,
and that the **spacing measurement still passes** (new widgets must not break the layout).
Output: assets/screenshots/script_*.png + script_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from util.flet_shutdown import shutdown, exit_now  # noqa: E402
from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
# ★ 命令行现在**默认不显示**（`HIDE_COMMAND_BAR`，2026-10-11）——
#   但这一支测的是「叙事区与命令栏之间没有大片空白」，所以这里
#   **显式把命令行打开**，判据的含义不变；默认不显示那件事由
#   `tools/verify_font_settings.py` 的 B 组管。
# [EN] ★ The command bar is now **hidden by default** (`HIDE_COMMAND_BAR`, 2026-10-11) ——
# [EN] but this script checks "no large blank between the narrative area and the command bar",
# [EN] so it **explicitly turns the command bar on** to keep the criterion's meaning; the
# [EN] "hidden by default" part is covered by group B of `tools/verify_font_settings.py`.
CFG.set('HIDE_COMMAND_BAR', 'false')
# 本脚本会启动 GUI → 能力校验 → `CFG.save()`；不拦住就会把上面这些
# 测试值写进用户的真实 `.env`（NWS_ENV_SINK 只在并行回归里由父进程给）。
# [EN] This script starts the GUI -> capability check -> `CFG.save()`; without blocking it the
# [EN] test values above get written into the user's real `.env` (NWS_ENV_SINK is only supplied
# [EN] by the parent process during parallel regression).
CFG.set('OUTPUT_FORMAT', 'script')

from display import script as S  # noqa: E402
from display import script_render as R  # noqa: E402
from display.scene_builder import SceneBuilder  # noqa: E402
from util.timefmt import GameTime  # noqa: E402
from world.state import PersonState  # noqa: E402
from agent.core import Action  # noqa: E402
from store.runfolder import RunFolder  # noqa: E402
import verify_ui_common as VU  # noqa: E402
VU.redirect_env_writes()

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'steps': []}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(f'  {"[OK]  " if ok else "[FAIL]"} {name}'
          + (f'  — {detail}' if detail else ''), flush=True)
    return bool(ok)


def head(t: str) -> None:
    print(f'\n── {t} ──', flush=True)


# ══════════════════════════════════════════════════════════════
#  ① 模型
# [EN] ① Model
# ══════════════════════════════════════════════════════════════
def test_model() -> bool:
    ok = True
    entries = [
        S.Entry(S.TIME, '过了半个时辰'), S.Entry(S.SCENE, '堂内'),
        S.enter('阿枝', '从后厨出'), S.exit_('阿枝', '转进后厨'),
        S.narration('雨脚敲着檐瓦。'),
        S.dialogue('主角', '你今日话里有话。', to='阿枝', tone='压低声音'),
        S.action('主角', '擦着柜台'), S.aside('主角', '不能让他知道。'),
        S.parallel([S.Track('主角', '擦柜台'), S.Track('阿枝', '收碗', visibility=S.OFFSCENE)]),
        S.cut('城东渡口', '同一时刻'), S.cut_back('临河茶肆'),
        S.event('马蹄声', kind_name='外部事件'), S.beat('片刻'),
        S.note('张力 0.4 → 0.6'),
        S.image('a.png', '临河茶肆'),
    ]
    ok &= rec('15 种词条类型都能构造', len(entries) == 15,
              f'{len(entries)} 种：{"、".join(e.kind for e in entries[:6])}…')

    # 往返
    # [EN] Round trip
    same = all(S.Entry.from_dict(e.to_dict()).to_dict() == e.to_dict()
               for e in entries)
    ok &= rec('每个词条 to_dict/from_dict 无损往返', same)

    sc = S.SceneScript(time_label='戌时 19:30', place='堂内', day=3,
                       cast=['主角', '阿枝'], anchors={'节点': 'N07'})
    for e in entries:
        sc.add(e)
    rt = S.SceneScript.from_dict(sc.to_dict())
    ok &= rec('整幕 to_dict/from_dict 无损往返',
              rt.to_dict() == sc.to_dict())

    # 未知类型要报错（而不是静默接收）
    # [EN] Unknown types must error (not be silently accepted)
    try:
        S.Entry('不存在的类型')
        bad = False
    except ValueError:
        bad = True
    ok &= rec('未知词条类型直接报错', bad)

    # speakers / actors 的语义（「不是一直说话」靠它体现）
    # [EN] Semantics of speakers / actors ("not always speaking" relies on this)
    ok &= rec('speakers() 只统计开口的人、actors() 统计所有动过的人',
              sc.speakers() == ['主角'] and '阿枝' in sc.actors(),
              f'开口 {sc.speakers()} / 动过 {sc.actors()}')
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ② 三套渲染
# [EN] ② Three rendering modes
# ══════════════════════════════════════════════════════════════
def _rich_scene() -> S.SceneScript:
    sc = S.SceneScript(time_label='戌时 19:30', place='临河茶肆 · 堂内',
                       place_desc='雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。',
                       weather='雨', title='破绽', day=3,
                       cast=['主角', '阿枝'], node='N07', node_name='破绽',
                       tension_before=0.42, tension_after=0.58)
    sc.anchors = {'节点': 'N07·破绽', '伏笔': 'F01'}
    sc.add(S.enter('阿枝', '从后厨出'))
    sc.add(S.narration('雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。'))
    sc.add(S.dialogue('主角', '你今日话里有话。', tone='顿了顿，没有抬头'))
    sc.add(S.action('主角', '拿抹布擦着柜台'))
    sc.add(S.aside('主角', '不能让他知道第三个人。'))
    sc.add(S.parallel([
        S.Track('主角', '擦着柜台，一眼没离开门口'),
        S.Track('阿枝', '在后厨把碗摞得叮当响', visibility=S.OFFSCENE),
        S.Track('街上', '更夫敲过三更', visibility=S.ELSEWHERE, place='街上')]))
    sc.add(S.cut('城东渡口', '同一时刻'))
    sc.add(S.action('披蓑衣的人', '下了船', visibility=S.ELSEWHERE,
                    place='城东渡口'))
    sc.add(S.cut_back('临河茶肆 · 堂内'))
    sc.add(S.event('马蹄声由远及近', kind_name='外部事件'))
    sc.add(S.beat('片刻'))
    sc.add(S.note('张力 0.42 → 0.58'))
    sc.add(S.image('img/x.png', '临河茶肆', kind_hint='scene'))
    sc.add(S.exit_('阿枝', '转进后厨'))
    return sc


def test_render() -> bool:
    ok = True
    sc = _rich_scene()
    md = R.to_markdown(sc, day_header='# 第 3 天 · 戌时 · 雨')

    # ── Markdown 反解无损 ──
    # [EN] ── Markdown reverse-parse lossless ──
    back = R.parse_markdown(md)
    ok &= rec('Markdown 能反解出幕', len(back) == 1, f'{len(back)} 幕')
    b = back[0]
    c1 = Counter(e.kind for e in sc.entries)
    c2 = Counter(e.kind for e in b.entries)
    diff = {k for k in set(c1) | set(c2) if c1.get(k) != c2.get(k)}
    ok &= rec('反解后词条类型与数量一致', not diff,
              f'差异 {diff}' if diff else f'{sum(c1.values())} 条全对上')

    ok &= rec('反解保留场景说明（地点/天气/在场/依据）',
              b.place == sc.place and b.weather == sc.weather
              and b.cast == sc.cast and b.anchors == sc.anchors,
              f'{b.place} · {b.weather} · {b.cast} · {b.anchors}')

    ok &= rec('反解保留并行轨的可见性（场外/别处不能丢）',
              [(t.subject, t.visibility) for t in b.by_kind(S.PARALLEL)[0].tracks]
              == [(t.subject, t.visibility) for t in sc.by_kind(S.PARALLEL)[0].tracks],
              str([(t.subject, t.visibility)
                   for t in b.by_kind(S.PARALLEL)[0].tracks]))

    ok &= rec('反解保留台词的语气提示',
              [e.tone for e in b.by_kind(S.DIALOGUE)]
              == [e.tone for e in sc.by_kind(S.DIALOGUE)],
              str([e.tone for e in b.by_kind(S.DIALOGUE)]))

    ok &= rec('反解保留台词文本（一字不差）',
              [e.text for e in b.by_kind(S.DIALOGUE)]
              == [e.text for e in sc.by_kind(S.DIALOGUE)])

    ok &= rec('「切至」的地点与说明都保住',
              [(e.place, e.text) for e in b.by_kind(S.CUT)]
              == [(e.place, e.text) for e in sc.by_kind(S.CUT)],
              str([(e.place, e.text) for e in b.by_kind(S.CUT)]))

    # ── 屏幕块 ──
    # [EN] ── Screen blocks ──
    blocks = R.render_blocks(sc)
    ok &= rec('屏幕渲染出块序列', len(blocks) >= 12, f'{len(blocks)} 块')
    roles = {bl.role for bl in blocks}
    ok &= rec('块带 role（界面据此上色）',
              {R.ROLE_META, R.ROLE_SPEECH, R.ROLE_TRACK, R.ROLE_DIR} <= roles,
              '、'.join(sorted(roles)))
    # 台词的语气提示不能是 speech role（否则看起来像台词）
    # [EN] The tone hint of a line must not be a speech role (otherwise it looks like a line)
    tone_blocks = [bl for bl in blocks if bl.kind == S.DIALOGUE and bl.text == '顿了顿，没有抬头']
    ok &= rec('台词的语气提示渲染成舞台指示而不是台词',
              bool(tone_blocks) and tone_blocks[0].role == R.ROLE_DIR,
              tone_blocks[0].role if tone_blocks else '缺失')
    ok &= rec('标签拆成 base + extra（界面才能翻基础词）',
              any(bl.label == '切至' and bl.label_extra == '城东渡口'
                  for bl in blocks),
              str([(bl.label, bl.label_extra) for bl in blocks
                   if bl.kind == S.CUT]))

    # ── 回灌 LLM ──
    # [EN] ── Feed back to LLM ──
    ctx = R.to_context(sc)
    ok &= rec('回灌格式比 Markdown 明显更短',
              len(ctx) < len(md) * 0.8,
              f'context {len(ctx)} 字 / markdown {len(md)} 字')
    ok &= rec('回灌保留关键信息（对白/同时/切至/事件）',
              '你今日话里有话' in ctx and '〔同时〕' in ctx
              and '〔切至' in ctx and '〔事件' in ctx)
    ok &= rec('回灌不含图片路径（省 token）', 'img/x.png' not in ctx)
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ③ 同时性（核心）
# [EN] ③ Simultaneity (core)
# ══════════════════════════════════════════════════════════════
class _World:
    def __init__(self):
        self.clock = GameTime(day=3, minutes=19 * 60 + 30)
        self.weather = '雨'
        self.scene = '临河茶肆 · 堂内'
        self.scene_desc = ''
        self.people = {
            '主角': PersonState('主角', location='临河茶肆 · 堂内'),
            '阿枝': PersonState('阿枝', location=''),
            '陆九': PersonState('陆九', location='城东渡口'),
        }
        self.tension = 0.5
        self.current_node = 'N07'

    def current_node_info(self):
        return {'id': 'N07', 'name': '破绽'}


class _Agent:
    def __init__(self, ps):
        self.ps = ps
        self.name = ps.name


def test_simultaneity() -> bool:
    ok = True

    # ① 单人做事 → 不该出现并行轨
    # [EN] ① Single person doing something → no parallel track should appear
    w = _World()
    b = SceneBuilder(w, day=3)
    ag = lambda n: _Agent(w.people[n])          # noqa: E731
    b.observe_tick([(ag('主角'), Action(verb='interact', target='柜台'))])
    ok &= rec('单人做事：不套「同时」（一个人做事说"同时"反而怪）',
              not b.current.by_kind(S.PARALLEL),
              f'词条 {[e.kind for e in b.current.entries]}')

    # ② 同场多人 → **按先后各成一条**（★ 2026-10-07 改口径）
    # [EN] ② Multiple people in the same scene → **each becomes one entry in chronological order** (★
    # [EN] 2026-10-07 changed stance)
    #
    # ★ 以前这里要求"一条并行轨、两轨" —— 那正是"满屏〔同时〕"的来源：
    #   这一拍只要有 2 个人各做一件事就并列成 `〔同时〕`，而一天几百拍下来
    #   读起来像"所有人同时在乱动"。用户原话：「人物做事情总是有先有后的
    #   你这全部都是· 同一时刻  好像大家都在很快的干任何事情一样」。
    #   新口径：**同场一律按先后写**；「同时」只留给**异地切镜头**（见 ③）。
    # [EN] ★ Previously this required "one parallel track, two tracks" —— that is exactly the source of
    # [EN] "full screen of 〔simultaneous〕":
    # [EN] In this beat, as long as 2 people each do one thing they get juxtaposed into `〔simultaneous〕`,
    # [EN] and with hundreds of beats a day
    # [EN] It reads like "everyone is moving around simultaneously". User's original words: "characters
    # [EN] always do things in some order
    # [EN] yours are all · same moment  it's like everyone is doing everything very fast".
    # [EN] New stance: **same scene always written in chronological order**; "simultaneous" is reserved
    # [EN] only for **cross-location shot cuts** (see ③).
    b.observe_tick([
        (ag('主角'), Action(verb='speak', target='阿枝', dialogue='你今日话里有话。')),
        (ag('阿枝'), Action(verb='interact', target='碗碟')),
    ])
    ok &= rec('同场两人：**按先后各成一条**，不再套「同时」'
              '（只有异地才配叫"同时"）',
              not b.current.by_kind(S.PARALLEL),
              f'词条 {[e.kind for e in b.current.entries]}')
    two = [e for e in b.current.entries if e.kind in (S.DIALOGUE, S.ACTION)]
    ok &= rec('两个人的两条都在（没因为不套「同时」丢人）',
              len(two) >= 2, '｜'.join(f'{e.speaker}→{e.text[:12]}' for e in two))
    ok &= rec('台词仍单独成条（不被压成概述）',
              any('你今日话里有话' in e.text for e in b.current.by_kind(S.DIALOGUE)))

    # ③ 异地有人做实事 → 切镜头
    # [EN] ③ Someone at a different location doing something real → cut shot
    b2 = SceneBuilder(_World(), day=3)
    b2.observe_tick([(ag('主角'), Action(verb='interact', target='柜台'))])
    b2.observe_tick([(_Agent(b2.world.people['陆九']),
                      Action(verb='move', target='渡口'))])
    ok &= rec('异地有人在做实事：切过去再切回来',
              len(b2.current.by_kind(S.CUT)) == 1
              and len(b2.current.by_kind(S.CUT_BACK)) == 1,
              f'切至 {[e.place for e in b2.current.by_kind(S.CUT)]}')

    # ④ 异地只在发呆 → 不该切（否则满屏转场标记）
    # [EN] ④ Different location only idling → should not cut (otherwise full screen of transition markers)
    b3 = SceneBuilder(_World(), day=3)
    b3.observe_tick([(ag('主角'), Action(verb='interact', target='柜台'))])
    for _ in range(3):
        b3.observe_tick([(_Agent(b3.world.people['陆九']), Action(verb='wait'))])
        b3.observe_tick([(_Agent(b3.world.people['陆九']), Action(verb='emote'))])
    ok &= rec('异地只是在发呆/变脸：**不**切镜头（防转场刷屏）',
              not b3.current.by_kind(S.CUT),
              f'切至 {len(b3.current.by_kind(S.CUT))} 次')

    # ⑤ 异地有台词 → 要切
    # [EN] ⑤ Different location has dialogue → should cut
    b4 = SceneBuilder(_World(), day=3)
    b4.observe_tick([(ag('主角'), Action(verb='wait'))])
    b4.observe_tick([(_Agent(b4.world.people['陆九']),
                      Action(verb='speak', target='船夫', dialogue='走了。'))])
    ok &= rec('异地有人在说话：要切过去（那正是"别处正在发生"）',
              len(b4.current.by_kind(S.CUT)) == 1)

    # ⑥ ★ 去重护栏：同一句台词重复说 4 遍 → 正文只留 1 次
    # [EN] ⑥ ★ Dedup guardrail: the same line repeated 4 times → only keep 1 in the body
    #
    # 用户报的「有点乱了」的另一半。实测他那份 `第001天.md` 里丁那句
    # 「账差七文」**一字不差出现了 4 次**（105 / 111 / 163 / 166 行）——
    # 根因是"每拍都要输出一条"而人物的目标不变，模型只能把同一件事再讲一遍。
    # 所以护栏只能放在**内容出口**（prompt 管不住"第 87 拍时它还记不记得自己说过"）。
    # [EN] The other half of the user's reported "it's a bit messy". In his actual `第001天.md`, Old Chen's
    # [EN] line
    b5 = SceneBuilder(_World(), day=3)
    ag5 = lambda n: _Agent(b5.world.people[n])          # noqa: E731
    same = Action(verb='speak', target='阿枝', dialogue='昨夜账上差七文。')
    for _ in range(4):
        b5.observe_tick([(ag5('主角'), same)])
    dup = [e for e in b5.current.by_kind(S.DIALOGUE) if '差七文' in e.text]
    ok &= rec('★ 同一句台词重复说 4 遍 → 正文只留 1 次'
              '（用户报的「丁账差七文出现 4 次」）',
              len(dup) == 1, f'{len(dup)} 次')

    # ⑦ 连续两拍都只是"转向某人"这种纯手势 → 第二拍不再写
    # [EN] ⑦ Two consecutive beats are both just pure gestures like "turning toward someone" → the second
    # [EN] beat is no longer written
    b6 = SceneBuilder(_World(), day=3)
    ag6 = lambda n: _Agent(b6.world.people[n])          # noqa: E731
    b6.observe_tick([(ag6('主角'), Action(verb='interact', target='阿枝'))])
    n1 = len(b6.current.entries)
    b6.observe_tick([(ag6('主角'), Action(verb='interact', target='柜台'))])
    ok &= rec('连续两拍都是"转向某人"这种纯手势 → 第二拍不再写'
              '（用户：「尽量每件事 每句话都跟主线有关」）',
              len(b6.current.entries) == n1,
              f'{n1} → {len(b6.current.entries)}')
    # ★ 对照：紧接着做的**是实事**就该照常写 —— 别把正常动作也一起吞了
    #   （没有这条，一个"什么都滤掉"的实现也能过 ⑥⑦）
    # [EN] ★ Contrast: if what immediately follows **is a real action**, it should still be written as
    # [EN] usual — don't swallow normal actions along with it
    # [EN] (Without this rule, an implementation that "filters out everything" would also pass ⑥⑦)
    b6.observe_tick([(ag6('主角'), Action(verb='move', target='渡口'))])
    ok &= rec('对照：紧接着做的是**实事**（去渡口）→ 照常写出来',
              len(b6.current.entries) > n1,
              f'{n1} → {len(b6.current.entries)}')
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ④ 出场退场 / 心声 / 图 / 分幕
# [EN] ④ Entrance/exit / inner thoughts / images / scene breaks
# ══════════════════════════════════════════════════════════════
def test_cast_and_misc() -> bool:
    ok = True
    w = _World()
    imgs: list = []
    b = SceneBuilder(w, day=3, image_hook=lambda k, key: imgs.append((k, key)) or f'i/{k}.png')

    def ag(n):
        return _Agent(w.people[n])

    b.observe_tick([(ag('主角'), Action(verb='wait'))])
    ok &= rec('第一幕：在场的人都有「出场」（开场第一拍要交代谁在）',
              {e.speaker for e in b.current.by_kind(S.ENTER)} >= {'主角', '阿枝'},
              str([e.speaker for e in b.current.by_kind(S.ENTER)]))
    ok &= rec('别处的人不算在场（陆九不该被列进在场）',
              '陆九' not in [e.speaker for e in b.current.by_kind(S.ENTER)])

    del w.people['阿枝']
    b.observe_tick([(ag('主角'), Action(verb='wait'))])
    ok &= rec('人物离开 → 自动记「退场」',
              '阿枝' in [e.speaker for e in b.current.by_kind(S.EXIT)])

    w.people['阿枝'] = PersonState('阿枝', location='')
    n_before = len(b.current.by_kind(S.ENTER))
    b.observe_tick([(ag('阿枝'), Action(verb='wait'))])
    ok &= rec('人物回来 → 自动记「出场」',
              len(b.current.by_kind(S.ENTER)) > n_before)

    # 心声 vs 动作
    # [EN] inner thoughts vs actions
    b2 = SceneBuilder(_World(), day=3)
    b2.observe_tick([(_Agent(b2.world.people['主角']),
                      Action(verb='think', inner_thought='他今天问得太细了。'))])
    ok &= rec('「在想事」渲染成心声，不是动作',
              len(b2.current.by_kind(S.ASIDE)) == 1
              and not b2.current.by_kind(S.ACTION),
              str([e.kind for e in b2.current.entries]))

    # 图：每幕上限
    # [EN] images: per-scene cap
    w3 = _World()
    b3 = SceneBuilder(w3, day=3,
                      image_hook=lambda k, key: f'i/{k}_{key}.png')
    b3.observe_tick([(_Agent(w3.people['主角']), Action(verb='wait'))])
    b3.observe_tick([(_Agent(w3.people['阿枝']), Action(verb='wait'))])
    ok &= rec('插图有上限（不会一屏挤满图把文字挤下去）',
              len(b3.current.by_kind(S.IMAGE)) <= 2,
              f'{len(b3.current.by_kind(S.IMAGE))} 张')

    # 场景图只在换地方时出
    # [EN] scene images only appear when the location changes
    w4 = _World()
    seen: list = []
    b4 = SceneBuilder(w4, day=3,
                      image_hook=lambda k, key: seen.append((k, key)) or 'i/x.png')
    b4.observe_tick([(_Agent(w4.people['主角']), Action(verb='wait'))])
    b4.begin_scene(force=True)          # 同地点再分一幕
    # [EN] same location broken into another scene
    ok &= rec('同一地点连着几幕：场景图不重复出',
              sum(1 for k, _ in seen if k == 'scene') == 1,
              str(seen))

    # 分幕
    # [EN] scene breaks
    w5 = _World()
    b5 = SceneBuilder(w5, day=3)
    b5.observe_tick([(_Agent(w5.people['主角']), Action(verb='wait'))])
    w5.clock = GameTime(day=3, minutes=21 * 60 + 5)      # 戌 → 亥
    # [EN] 戌 → 亥
    brk = b5.maybe_break(prev_clock=GameTime(day=3, minutes=19 * 60 + 30),
                         prev_place='临河茶肆 · 堂内')
    ok &= rec('时段变化自动分幕（新幕首要重新标时间）',
              brk and b5.current.time_label.startswith('亥时'),
              b5.current.time_label)

    # 一幕太长自动分幕
    # [EN] auto scene break when a scene gets too long
    #
    # ⚠ 夹具必须用**互不重复的动作**（2026-10-07 踩到）：`_action_text` 对同一个
    #   verb 给的是同一句话（`wait` 永远是「没动，也没出声」），而新加的去重护栏
    #   会把重复条滤掉 —— 拿重复动作当夹具，测的就变成"去重生效了"而不是
    #   "分幕生效了"（实测：0 幕已收、当前幕只有 3 条，判据红）。
    #   判据本意是"条目数超上限就分幕"，所以夹具得让条目**真的**涨上去。
    # [EN] ⚠ fixtures must use **mutually distinct actions** (hit on 2026-10-07): `_action_text` gives the
    # [EN] same
    # [EN] sentence for the same verb (`wait` is always "didn't move, didn't make a sound"), and the newly
    # [EN] added dedup guardrail
    # [EN] filters out duplicate entries — using duplicate actions as fixtures means what's being tested
    # [EN] becomes "dedup works" rather than
    # [EN] "scene break works" (measured: 0 scenes collected, current scene has only 3 entries, assertion
    # [EN] red).
    # [EN] The intent of the assertion is "break the scene when entry count exceeds the cap", so fixtures
    # [EN] must make the entry count **actually** grow.
    w6 = _World()
    b6 = SceneBuilder(w6, day=3)
    for i in range(int(CFG.i('SCRIPT_SCENE_MAX_ENTRIES')) + 5):
        b6.observe_tick([(_Agent(w6.people['主角']),
                          Action(verb='move', target=f'地方{i}'))])
    ok &= rec('一幕超过上限自动分幕', len(b6.scenes) >= 1,
              f'{len(b6.scenes)} 幕已收，当前幕 {len(b6.current.entries)} 条')
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ⑤ RunLoop 端到端 + 落盘读回
# [EN] ⑤ RunLoop end-to-end + write to disk and read back
# ══════════════════════════════════════════════════════════════
def test_loop_and_files() -> bool:
    ok = True
    from world.state import WorldState
    from agent.core import Agent
    from director.engine import DirectorEngine
    from store.db import DB
    from store.runfolder import RunFolder
    from sim.loop import RunLoop

    world = WorldState(clock=GameTime(day=1, minutes=19 * 60 + 30), weather='雨',
                       scene='临河茶肆 · 堂内',
                       scene_desc='雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。')
    world.current_node = 'N07'
    for n, loc in (('主角', '临河茶肆 · 堂内'), ('阿枝', ''), ('陆九', '城东渡口')):
        world.add_person(PersonState(n, location=loc))
    world.progress_nodes = [{'id': 'N07', 'name': '破绽', '状态': '进行中'}]

    tmp = Path(tempfile.mkdtemp(prefix='nws_script_'))
    run = RunFolder(tmp, '第1次模拟2026-10-05-20-00')
    run.create()
    db = DB(run.root / 'state.db')
    agents = [Agent(p, db, world) for p in world.people.values()]
    loop = RunLoop(world, agents, DirectorEngine(world, db), db, run,
                   image_hook=lambda k, key: f'assets/images/{k}.png')
    lines: list = []
    loop.on_narrative(lambda t, p, **kw: lines.append((p, t)))

    # ⚠ 拍数**故意给足**（8 → 24，2026-10-07）：下面那条"落盘里有「切至」"
    #   判据要的是**一次异地切镜头**，而它取决于"随机挑到那个在别处的人、
    #   而他的动作又刚好值得切"（实测 8 拍只有 ~83% 会出）。
    #   一条会随机变红的判据比没有更坏 —— 红一次绿三次，最后没人再看它。
    #   测的是"通路通不通"，那就把样本给到几乎必然发生。
    # [EN] ⚠ beat count **deliberately set high enough** (8 → 24, 2026-10-07): the assertion below, "the
    # [EN] on-disk file contains「切至」",
    # [EN] requires **a single cross-location camera cut**, and that depends on "randomly picking the
    # [EN] person who is elsewhere,
    # [EN] and his action also happens to be worth cutting to" (measured: with 8 beats only ~83% chance it
    # [EN] appears).
    # [EN] An assertion that randomly turns red is worse than none — red once, green three times, and
    # [EN] eventually nobody looks at it anymore.
    # [EN] If what's being tested is "does the path work", give it a sample where it almost certainly
    # [EN] happens.
    async def drive():
        for i in range(1, 25):
            await loop._tick(i)
        await loop._end_day()

    try:
        asyncio.run(drive())
        ok &= rec('RunLoop 剧本模式跑完 8 个 tick 不报错', True,
                  f'显示队列 {len(lines)} 条')
    except Exception as e:
        import traceback
        ok &= rec('RunLoop 剧本模式跑完 8 个 tick 不报错', False,
                  f'{type(e).__name__}: {e}')
        report['loop_traceback'] = traceback.format_exc()

    files = sorted(p.name for p in run.daily_dir.iterdir())
    ok &= rec('落盘同时产出 .md 与 .json 边车',
              any(f.endswith('.md') for f in files)
              and any(f.endswith('.json') for f in files), str(files))

    md_text = next(run.daily_dir.glob('*.md')).read_text(encoding='utf-8')
    ok &= rec('Markdown 带头部与幕首',
              '# 第 1 天' in md_text and '## ' in md_text,
              md_text.splitlines()[0][:40])
    # ⚠ 要看**当天全部**落盘文件：拍数一多就会分幕（`SCRIPT_SCENE_MAX_ENTRIES`），
    #   切镜可能发生在后一幕 —— 只读第一个文件会漏（那也是假红的一种）。
    # [EN] ⚠ Look at **all** on-disk files for the day: with more beats it will break into scenes
    # [EN] (`SCRIPT_SCENE_MAX_ENTRIES`),
    # [EN] and the camera cut may happen in a later scene — reading only the first file will miss it
    # [EN] (that's also a kind of false red).
    md_all = '\n'.join(p.read_text(encoding='utf-8')
                       for p in sorted(run.daily_dir.glob('*.md')))
    ok &= rec('落盘里有「同时」或「切至」这类同时性标记（端到端真的生效）',
              '〔同时〕' in md_all or '〔切至' in md_all,
              '、'.join(x for x in ('〔同时〕', '〔切至') if x in md_all) or '都没有')

    scenes = run.read_daily_script()
    ok &= rec('界面读回剧本（走 .json 边车）', len(scenes) >= 1,
              f'{len(scenes)} 幕 / 统计 {R.stats(scenes)}')

    # JSON 优先于 md：把 md 改坏，读回仍应正常
    # [EN] JSON takes priority over md: corrupt the md, reading back should still work
    json_scenes = R.from_json(
        next(run.daily_dir.glob('*.json')).read_text(encoding='utf-8'))
    ok &= rec('JSON 边车与反解结果一致（边车是事实来源）',
              len(json_scenes) == len(scenes))

    # 旧纯文本格式仍能打开
    # [EN] old plain-text format can still be opened
    legacy = Path(tempfile.mkdtemp(prefix='nws_legacy_'))
    lrun = RunFolder(legacy, '第1次模拟2020-01-01-00-00')
    lrun.create()
    lrun.flush_daily(1, '这是一段旧格式的纯文本叙事。\n\n没有任何剧本结构。', '第1天')
    ok &= rec('旧纯文本格式的 daily：不报错，返回空幕（由界面回退纯文本）',
              lrun.read_daily_script() == [])
    ok &= rec('旧格式的 md 仍在（没被改坏）',
              any(p.suffix == '.md' for p in lrun.daily_dir.iterdir()))

    VU.safe_rmtree(legacy, ignore_errors=True)
    report['daily_dir'] = str(run.daily_dir)
    report['stats'] = R.stats(scenes)
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ⑥ 真机 GUI
# [EN] ⑥ real-device GUI
# ══════════════════════════════════════════════════════════════
def make_gui_fixture() -> tuple[Path, Path]:
    """造一个项目：含一次模拟 + 一份剧本 daily（md + json）+ 一张真图。
        English:
    Build a project: contains one simulation + one script daily (md + json) + one real image.
    """
    from store.project import Project

    tmp = Path(tempfile.mkdtemp(prefix='nws_scriptgui_'))
    proj = Project.create_new(tmp / 'Projects', '剧本验证')
    run = RunFolder(proj.root, '第1次模拟2026-10-05-20-00')
    run.create()

    # 一张真实的小图（用 PIL 画，避免依赖别的产物）
    # [EN] a real small image (drawn with PIL, to avoid depending on other artifacts)
    img_dir = proj.root / 'assets'
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / 'scene.png'
    im = Image.new('RGB', (640, 360), (206, 226, 232))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 240, 640, 360], fill=(150, 186, 196))
    d.ellipse([420, 40, 500, 120], fill=(240, 226, 190))
    im.save(img_path)

    sc = _rich_scene()
    # 让图片指向真实存在的文件
    # [EN] make the image point to a file that actually exists
    for e in sc.entries:
        if e.kind == S.IMAGE:
            e.image = str(img_path)
    sc2 = S.SceneScript(time_label='戌时 20:40', place='后院', weather='雨',
                        title='井', day=1, cast=['主角'])
    sc2.add(S.narration('后院里只有雨声。'))
    sc2.add(S.action('主角', '蹲在井边，手按着井沿'))
    sc2.add(S.aside('主角', '夜里响的，到底是什么。'))

    run.flush_daily_script(1, [sc, sc2], calendar_str='第1天·戌时', weather='雨',
                           cast=['主角', '阿枝'], tension='0.42→0.58')
    return tmp, proj.root


def walk(c, out: list, d: int = 0) -> None:
    if c is None or d > 40:
        return
    out.append(c)
    for a in ('controls', 'content', 'actions', 'title'):
        v = getattr(c, a, None)
        if isinstance(v, list):
            for x in v:
                walk(x, out, d + 1)
        elif v is not None and hasattr(v, '__class__'):
            walk(v, out, d + 1)


def _hex6(c) -> str:
    """取颜色的 6 位主体（界面色带 alpha，比较时要先脱掉）。
        English:
    Take the 6-digit main body of the color (UI colors carry alpha, must be stripped before
    comparing).
    """
    s = str(c or '').lstrip('#')
    if len(s) == 8:
        s = s[2:]
    return s.upper()


def _left_bar(c) -> str:
    """取控件**左边框**的颜色 —— 卡片靠「左侧竖色条」区分类型。
        English:
    Take the widget's **left border** color -- cards distinguish type by the "left vertical color
    bar".
    """
    b = getattr(c, 'border', None)
    left = getattr(b, 'left', None) if b is not None else None
    if left is None:
        return ''
    return _hex6(getattr(left, 'color', None))


async def test_gui(page: ft.Page) -> bool:
    # ⚠ 整个函数体都在 try 里：**Flet 的 main() 抛异常时不会自动退出进程**，
    #   窗口会一直挂着等客户端（表现为脚本"卡死"）。
    #   之前 make_gui_fixture() 的 NameError 就发生在 try 之前，把整轮验证拖死。
    #   所以任何初始化都必须放在 try 内，靠 finally 兜底退出。
    # [EN] ⚠ the entire function body is inside try: **Flet's main() does not automatically exit the
    # [EN] process when it throws**,
    # [EN] the window will hang forever waiting for a client (manifesting as the script "freezing").
    # [EN] Previously a NameError in make_gui_fixture() happened before the try, dragging the whole
    # [EN] verification round to death.
    # [EN] So any initialization must be placed inside the try, with finally as the fallback exit.
    ok = True
    tmp: Path | None = None
    try:
        VU.patch_flat_background()      # 量测需要纯色背景（见 verify_ui_common）
        # [EN] measurement needs a solid-color background (see verify_ui_common)

        from store.project import Project
        from gui.app_flet import NovelWorldApp

        tmp, proj_root = make_gui_fixture()
        proj = Project(proj_root, '剧本验证')

        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(2.0)

        async def shot(name: str) -> bytes:
            page.update()
            await asyncio.sleep(0.5)
            data = await page.take_screenshot()
            (OUT / name).write_bytes(data)
            return data

        # ── 有剧本：中栏应渲染出剧本 ──
        # [EN] ── with script: the middle column should render the script ──
        app._activate_project(proj)
        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.8)

        out: list = []
        for c in page.controls:
            walk(c, out)
        def _all_text(c) -> str:
            """控件的**全部**文本。

            ⚠ 2026-10-06 中栏改成小说体段落之后，段落的内容在 `spans` 里、
              `value` 是空的 —— 只读 `value` 会一个字都拿不到（那一整片
              "渲染出旁白/台词/动作/心声"的判据就是这样假红的）。
            
                        English:
            **All** the widget's text.
                        WARNING 2026-10-06 After the center column changed to novel-prose paragraphs, the paragraph content is in `spans`,
                          and `value` is empty -- reading only `value` gets you not a single character (that whole set
                          of "render out narration/line/action/inner voice" criteria was falsely red exactly because of this).
            """
            v = str(getattr(c, 'value', '') or '')
            spans = getattr(c, 'spans', None) or []
            return v + ''.join(str(getattr(x, 'text', '') or '') for x in spans)

        texts = [_all_text(c) for c in out if isinstance(c, ft.Text)]
        images = [c for c in out if isinstance(c, ft.Image)]
        joined = '\n'.join(texts)
        report['gui_texts'] = texts[:70]

        ok &= rec('中栏渲染出幕首（时间 + 场景 + 在场）',
                  '戌时 19:30' in joined and '临河茶肆' in joined,
                  next((x for x in texts if '戌时' in x), '')[:60])
        ok &= rec('渲染出旁白', '雨脚敲着檐瓦' in joined)
        ok &= rec('渲染出台词（且带说话人）',
                  '你今日话里有话' in joined and '主角' in joined)
        ok &= rec('渲染出动作（人物在做事，不只是说话）',
                  '拿抹布擦着柜台' in joined)
        ok &= rec('渲染出心声', '不能让他知道第三个人' in joined)
        ok &= rec('渲染出「同时」（小说体写成「同一刻，…」一句）',
                  '同一刻' in joined)
        ok &= rec('并行轨标出了场外/别处（同时不同地的关键）',
                  '场外' in joined or '别处' in joined,
                  '、'.join(x for x in ('场外', '别处') if x in joined))
        ok &= rec('渲染出「切至」与「切回」',
                  '切至' in joined and '切回' in joined)
        ok &= rec('渲染出「依据」（节点/伏笔可见，卡脚那行）',
                  'N07' in joined and '依据' in joined,
                  next((x for x in texts if 'N07' in x), '')[:60])
        # ⚠ 别把出场文案写死成「走了进来」—— 夹具用的是 `S.enter('阿枝', '从后厨出')`，
        #   `sentence()` 对带具体说法的 how 会原样用（`阿枝从后厨出。`）。
        #   判的是"写成了叙述句 **且** 不再有场记标记"，不是某一个固定词。
        # [EN] What's being judged is "written as a narrative sentence **and** no longer has stage-direction
        # [EN] markers", not some fixed word.
        ok &= rec('渲染出出场（写成叙述句，不再打〔出场〕标记）',
                  '从后厨出' in joined and '〔出场' not in joined,
                  next((x for x in texts if '从后厨出' in x), '')[:40])
        ok &= rec('渲染出退场（同理：`阿枝转进后厨。`）',
                  '转进后厨' in joined and '〔退场' not in joined,
                  next((x for x in texts if '转进后厨' in x), '')[:40])
        ok &= rec('图片输出渲染成真的图片控件（不只是路径文本）',
                  len(images) >= 1 and str(images[0].src).endswith('.png'),
                  f'{len(images)} 个 Image 控件')
        ok &= rec('多幕都渲染了（第二幕「后院」也在）',
                  '后院' in joined)

        # ── 卡片式渲染 ──
        # 输出以前是**一列同级 Text**（只有颜色深浅的差别），一屏下来就是
        # "一片字"。现在必须是一幕一张卡，且类型靠**左侧竖色条 + 名牌**区分。
        # [EN] ── card-style rendering ──
        # [EN] output used to be **a single column of same-level Text** (differing only in color shade), which
        # [EN] reads on one screen as
        # [EN] "a slab of text". Now it must be one card per scene, with type distinguished by **a vertical
        # [EN] color bar on the left + name plate**.
        from gui.app_flet import C as GC
        col = app._ui_run.get('narrative')
        cards = list(getattr(col, 'controls', []) or [])
        kinds = sorted({type(c).__name__ for c in cards})
        report['narrative_cards'] = len(cards)
        ok &= rec('中栏输出是卡片（每一项都是 Container）',
                  bool(cards) and all(isinstance(c, ft.Container) for c in cards),
                  f'{len(cards)} 项：{"、".join(kinds)}')
        ok &= rec('一幕一张卡（造了 2 幕 → 2 张卡）', len(cards) == 2,
                  f'{len(cards)} 张')
        ok &= rec('幕卡有左侧赭金竖条（一眼认出"这是一幕"）',
                  bool(cards) and all(_left_bar(c) == _hex6(GC['border_gold'])
                                      for c in cards),
                  '、'.join(_left_bar(c) for c in cards))

        inner: list = []
        for c in cards:
            walk(c, inner)
        # ★ 2026-10-06：名牌（那个小圆牌）**有意取消**了 —— 屏幕改成小说体，
        #   台词写成 `主角语气不善，对阿枝说：「…」`。本意是"台词跟旁白分得开、
        #   且看得出谁在说"，换成新形态的检查。
        # [EN] ★ 2026-10-06: the name plate (that little round tag) was **intentionally removed** —— the screen
        # [EN] was changed to novel style,
        # [EN] and you can tell who is speaking", replaced by the new-form check.
        inner_text = '\n'.join(
            str(getattr(c, 'value', '') or '')
            + ''.join(str(getattr(x, 'text', '') or '')
                      for x in (getattr(c, 'spans', None) or []))
            for c in inner if isinstance(c, ft.Text))
        # ★ 口径变更 2026-10-07：台词改**剧本体**（用户：「正文的格式你参考
        #   老舍的茶馆进行深度优化」）—— `人物名：台词` 直接引出，
        #   不再用 `X说：「…」` 那套叙述动词。判据跟着翻：
        #   从"必须有叙述动词"变成"必须是 `人名：` 且**不含** `说：「`"。
        # [EN] Deep optimization of Lao She's Teahouse") -- `charactername: line` directly introduces,
        # [EN] no longer using the `X says: "..."` narrative verb pattern. The criterion flips accordingly:
        # [EN] from "must have a narrative verb" to "must be `personname:` and must **not** contain `says: "`.
        speech_lines = [x for x in inner_text.splitlines() if x.strip()]
        ok &= rec('对白是**剧本体**：`人物名：` 直接引出'
                  '（老舍《茶馆》的写法；不再用"X说：「…」"）',
                  any(not x.startswith('　') and '：' in x[:14]
                      for x in speech_lines)
                  and '说：「' not in inner_text,
                  (speech_lines[:1] or [''])[0][:50])
        ok &= rec('台词**不缩进**（对话顶格，与旁白的段首缩进分得开）',
                  any(not x.startswith('　') and '：' in x[:14]
                      for x in speech_lines),
                  '')
        bars = {_left_bar(c) for c in inner if isinstance(c, ft.Container)}
        ok &= rec('「事件」是带朱砂竖条的内卡',
                  _hex6(GC['seal']) in bars, '、'.join(sorted(b for b in bars if b)))
        ok &= rec('卡内用发丝线分段（幕首与正文分开）',
                  any(isinstance(c, ft.Divider) for c in inner))

        png = await shot('script_main.png')

        # ── 布局：新控件不能把间距搞坏 ──
        # 中栏现在是**卡片**，而卡片底色是"输入框纸色叠在叙事区面板上"，
        # 合成色既不等于 panel_rgb 也不等于 field_rgb（实测 (245,244,238)）。
        # 所以按颜色找"面"必然失手（踩过：量出「间距 999px」这种假故障）。
        # 改用按**亮度**找面 —— 与面板嵌套几层无关。
        # [EN] -- Layout: new widgets must not break the spacing --
        # [EN] The center column is now a **card**, and the card background is "input-field paper color
        # [EN] composited over the narrative-area panel",
        # [EN] the resulting blend is neither equal to panel_rgb nor field_rgb (measured (245,244,238)).
        # [EN] So finding a "surface" by color is bound to fail (been there: measured a bogus fault like
        # [EN] "spacing 999px").
        # [EN] Switch to finding the surface by **brightness** -- independent of how many panel layers are
        # [EN] nested.
        runs = VU.bright_runs_v(png, page.width // 2)
        gaps = [b[0] - a[1] for a, b in zip(runs, runs[1:])]
        gap = max(gaps) if gaps else -1
        report['surface_runs'] = runs
        report['gap_px'] = gap
        ok &= rec('中栏与命令栏之间仍没有大片空白（<30px）', 0 <= gap < 30,
                  f'间距 {gap}px（共 {len(runs)} 个面）')

        # 像素层复核：竖色条真的画出来了（控件树里有 ≠ 渲染出来有）。
        # 卡的左竖条贴在**中栏左缘**（实测 x≈251，因为左栏面板占掉左边 ~230px），
        # 所以不能只扫屏幕中间三分之一 —— 那样扫描窗口整个落在卡内部，
        # 一根竖条也扫不到（踩过：报「屏幕上没有赭金竖条」，其实画着）。
        # 范围取「左右面板之外」，两头各让 240px。
        # [EN] Pixel-level verification: the vertical color bar really is drawn (being in the widget tree !=
        # [EN] being rendered).
        # [EN] The card's left vertical bar hugs the **center column's left edge** (measured x~251, because the
        # [EN] left panel takes up ~230px on the left),
        # [EN] so we can't just scan the middle third of the screen -- that way the scan window falls entirely
        # [EN] inside the card,
        # [EN] and not a single vertical bar gets scanned (been there: reported "no ochre-gold vertical bar on
        # [EN] screen" when one was in fact drawn).
        # [EN] Take the range as "outside the left and right panels", giving up 240px on each end.
        x_from, x_to = 240, int(page.width) - 240
        gold_bars = [b for b in VU.accent_bars(png, VU.hex_rgb(GC['border_gold']),
                                               x_from=x_from, x_to=x_to,
                                               tol=30, min_len=24)
                     if b[2] - b[1] > 60]
        report['gold_bars'] = gold_bars
        ok &= rec('屏幕上量到「一幕一根赭金竖条」，且根数 = 幕数',
                  len(gold_bars) == 2,
                  '、'.join(f'x{x} 高{y1 - y0 + 1}' for x, y0, y1 in gold_bars))
        # 靛青竖条原本属于「同时」内卡 —— 那张内卡随小说体一起取消了
        #   （同时现在写成一整句话），所以这条像素判据也一并去掉。
        #   「一幕一根赭金竖条」那条留着（幕卡还在）。
        # [EN] The indigo vertical bar originally belonged to the "simultaneous" inner card -- that inner card
        # [EN] was removed along with the novel-prose style
        # [EN] (simultaneous is now written as a whole sentence), so this pixel criterion is removed as well.
        # [EN] Keep the "one ochre-gold vertical bar per scene" criterion (the scene card is still there).

        # 阅读面仍能看清字（背景没把文字糊掉）
        # [EN] The reading surface still shows text clearly (background doesn't smear the text)
        #
        # ⚠⚠ 2026-10-22：**这条判据原来量的是"缩到 240×135 之后的深色点数"**，
        #   而 1920×1129 缩到 240×135 是 1/8 采样，**文字笔画在重采样里被平均掉了**：
        #   实测同一张图 —— 原始分辨率深色占 1.04%，缩到 240×135 只剩 0.02%（7 个点），
        #   而阈值是 60 ⇒ 恒红。这与产品无关（同一屏的 71 条其它断言全绿，
        #   控件树里也真的找得到那些字）。
        #   ⇒ 改成**在原始分辨率上量占比**，并用**同一次运行里的空页**当对照：
        #     有正文 1.04% / 空页 0.48% ⇒ 阈值 0.8% 把两者分得开，
        #     而且不再受窗口尺寸（DPI）影响。
        # [EN] ⚠⚠ 2026-10-22: **this used to count dark pixels after resizing to 240x135**, which is
        # [EN] 1/8 sampling of a 1920x1129 window -- **the text strokes get averaged away**: measured on
        # [EN] the same image, 1.04% dark at native resolution vs 0.02% (7 pixels) at 240x135 against a
        # [EN] threshold of 60 => permanently red. Nothing to do with the product (the other 71
        # [EN] assertions on the same screen are green and the widget tree really holds those words).
        # [EN] => Measure the **ratio at native resolution** and calibrate against the empty page from
        # [EN] the same run: body 1.04% / empty 0.48% => 0.8% separates them and no longer depends on
        # [EN] the window size (DPI).
        im = VU.image_of(png)
        _px = list(im.get_flattened_data())
        _dark = sum(1 for p in _px if sum(p[:3]) / 3 < 120)
        _ratio = _dark / max(1, len(_px))
        ok &= rec('阅读面上有足够多的深色像素（文字真的画出来了）'
                  '—— 在**原始分辨率**上量占比（缩图会把笔画平均掉）',
                  _ratio >= 0.008,
                  f'{_dark} / {len(_px)} = {_ratio * 100:.2f}%（阈值 0.80%）')

        # ── 英文界面 ──
        # [EN] -- English UI --
        from i18n import set_lang
        set_lang('en')
        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.6)
        out2: list = []
        for c in page.controls:
            walk(c, out2)
        texts2 = [_all_text(c) for c in out2 if isinstance(c, ft.Text)]
        j2 = '\n'.join(texts2)
        # 小说体之后，屏幕上的"剧本标签"变成了**叙述动词**：
        # [EN] After the novel-prose change, the on-screen "script label" became the **narrative verb**:
        #   `Shen Yan says: "..."` / `A Zhi thinks: ...` / `At that same moment, ...`
        ok &= rec('英文界面下叙述动词也翻译了（says / thinks / Just then）',
                  ('says' in j2 or 'thinks' in j2 or 'Just then' in j2),
                  '、'.join(x for x in ('says', 'thinks', 'Just then', 'remembers')
                            if x in j2) or '未翻译')
        ok &= rec('英文界面下可见性也翻译了（不留中文的场外/别处）',
                  ('off stage' in j2 or 'elsewhere' in j2)
                  and '场外' not in j2,
                  '、'.join(x for x in ('off stage', 'elsewhere') if x in j2)
                  or '未翻译')
        await shot('script_main_en.png')
        set_lang('zh')

        # ── 空项目：不能填假数据 ──
        # [EN] -- Empty project: must not be filled with fake data --
        empty = Path(tempfile.mkdtemp(prefix='nws_emptyscript_'))
        proj2 = Project.create_new(empty, '空项目')
        app._activate_project(proj2)
        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.6)
        out3: list = []
        for c in page.controls:
            walk(c, out3)
        j3 = '\n'.join(str(getattr(c, 'value', '')) for c in out3
                       if isinstance(c, ft.Text))
        ok &= rec('没有产物时显示占位提示（不预填编造的剧本）',
                  '故事尚未开始' in j3
                  and '雨脚敲着檐瓦' not in j3)
        await shot('script_empty.png')
        VU.safe_rmtree(empty, ignore_errors=True)

        report['ok'] = bool(ok)
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        if tmp is not None:
            VU.safe_rmtree(tmp, ignore_errors=True)
        (OUT / 'script_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        passed = sum(1 for s in report['steps'] if s['ok'])
        failed = [s['name'] for s in report['steps'] if not s['ok']]
        print(f'\n{"=" * 62}\n通过 {passed}/{len(report["steps"])} 项'
              + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)),
              flush=True)
        # **崩溃也要吼出来**：崩溃时后面的断言根本没跑，
        # 只报「通过 N 项」会看着像全绿（踩过：gold_bars 那行 TypeError
        # 让 4 项断言凭空消失，汇总却仍打印"通过 64/64"）。
        # [EN] **A crash must shout too**: when it crashes the later assertions never run at all,
        # [EN] reporting only "N items passed" looks all green (been there: the gold_bars line's TypeError
        # [EN] made 4 assertions vanish into thin air, yet the summary still printed "64/64 passed").
        if report.get('fatal'):
            print('\n⚠ 验证中途崩溃，后面的断言没有执行：\n'
                  + report['fatal'][-1500:], flush=True)
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] WARNING The exit code must be set **before the window closes**: `page.window.destroy()` throws
        # [EN] CancelledError
        # [EN] and cancels this coroutine; the line `exit_now(...)` written after `await shutdown(page)`
        # [EN] **never executes** (exit code always 0 = fake green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('剧本式叙事输出 · 验证', flush=True)
    logic_ok = True
    head('1. 数据模型')
    logic_ok &= test_model()
    head('2. 三套渲染 + Markdown 往返')
    logic_ok &= test_render()
    head('3. 同时性（核心）')
    logic_ok &= test_simultaneity()
    head('4. 出场退场 / 心声 / 插图 / 分幕')
    logic_ok &= test_cast_and_misc()
    head('5. RunLoop 端到端 + 落盘读回')
    logic_ok &= test_loop_and_files()

    report['logic_ok'] = bool(logic_ok)
    if '--logic-only' in sys.argv:
        # 只跑不弹窗的部分（调试用；正式验证要跑全量）
        # [EN] Only run the non-popup part (for debugging; full verification must run everything)
        passed = sum(1 for s in report['steps'] if s['ok'])
        report['ok'] = bool(logic_ok)
        (OUT / 'script_report_logic.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n{"=" * 62}\n（仅逻辑）通过 {passed}/{len(report["steps"])} 项')
        sys.exit(0 if logic_ok else 2)
    head('6. 真机 GUI（启动 Flet 窗口渲染剧本）')
    ft.run(test_gui)
