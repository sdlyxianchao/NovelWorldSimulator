# -*- coding: utf-8 -*-
"""验证：**讲故事别空转**（在场 / 登场 / 客流 / 群演 / 反空转）+ **每轮开场**。

起因（用户 2026-10-06）：真机跑《临河茶肆》的日志里，126 次决策的"在场人物"
一模一样（连终局才登场的角色都在场）；词频「看 627、擦 565、账 556」而
「买 0、顾客 0」—— 茶楼没客人；决策提示词里明明白白写着
「手头有事就继续做……比如「擦紫砂壶」」，**系统在教他们闲着**。

要证四件事（每条都要能红）：

  ① **在场是"这一刻在这儿的人"**，不是装配时那份前台名册；
  ② **有人可演**：客流跟着天气/时辰走，门外有背景群演、偶尔来个"有事的"；
  ③ **提示词不再教人闲着**，且三层目标（这一站 / 今天 / 你想要的）真的在 prompt 里；
  ④ **每轮开场**：只列在场者、未登场只给哪天、秘密不进开场、能落盘、能贯通导出；
     而且是**中栏里的一张卡**（不弹对话框、不等确认，用户 2026-10-06 改的要求），
     卡片上看到的与落盘的 `开场.md` **是同一份文本**。

用法：.venv\\Scripts\\python.exe tools/verify_story_depth.py [--logic-only]
产出：assets/screenshots/story_depth_report.json

English:
Verify: **storytelling must not idle** (presence / appearance / foot traffic / extras /
anti-idling) + **opening every round**.
Origin (user 2026-10-06): in the real-machine log of running 《临河茶肆》, the "present characters" of
126 decisions were
identical (even characters who only appear in the finale were present); word frequencies "看 627,
擦 565, 账 556" while
"买 0, 顾客 0" -- the teahouse has no customers; the decision prompt plainly says
"if there's something at hand keep doing it... e.g. 「擦紫砂壶」", **the system is teaching them to
idle**.
Four things must be proven (each must be able to go red):
  ① **Presence means "the people here at this moment"**, not the front-desk roster at assembly time;
  ② **There are people to perform**: foot traffic follows weather/hour, there are background extras outside the door, occasionally a "busy one" shows up;
  ③ **The prompt no longer teaches people to idle**, and the three-layer goals (this stop / today / what you want) are really in the prompt;
  ④ **Each round's opening**: only list who is present, for those not yet appeared only give which day, secrets do not go into the opening, can be persisted, can be exported through consistently;
     and it is **a card in the middle column** (no dialog popup, no waiting for confirmation, requirement changed by user on 2026-10-06),
     what is seen on the card and the persisted `开场.md` **are the same text**.
Usage: .venv\\Scripts\\python.exe tools/verify_story_depth.py [--logic-only]
Output: assets/screenshots/story_depth_report.json
[Output language] All **output text** must be written in **Simplified Chinese** without
exception - narrative, narration, dialogue, documentation, summaries, suggestions all count,
**even if the source material is in another language**. Proper nouns such as person names, place
names, book titles **keep their original spelling**, do not transliterate or paraphrase. **Key
names in JSON stay as-is** (e.g. "动作", "台词"), only write the **values** in Chinese.
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
from util.flet_shutdown import shutdown                        # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('BEAT_SECONDS', '2')
# 本脚本验的就是开场 —— **显式打开，不依赖用户的 .env**
# （脚本要自足：用户把 SHOW_OPENING 关掉了，也不该让这条判据跟着红）。
# [EN] This script verifies the opening -- **explicitly turned on, not relying on the user's .env**
# [EN] (the script must be self-contained: even if the user turned SHOW_OPENING off, this criterion
# [EN] should not turn red because of it).
CFG.set('SHOW_OPENING', 'true')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from sim import opening as OP                                  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def _world(scene='临河茶肆', hour=19, weather='晴'):
    from util.timefmt import GameTime
    from world.state import PersonState, WorldState
    w = WorldState(scene=scene, weather=weather,
                   clock=GameTime(day=1, minutes=hour * 60))
    w.people = {
        '主角': PersonState('主角', identity='掌柜', catchphrase='喝茶。',
                            goal='守住这楼的夜生意', secret='他知道楼底下埋着什么'),
        '阿福': PersonState('阿福', identity='新伙计', catchphrase='我记得。',
                            goal='把今天的活干完', secret='他记得火光'),
        '柳娘': PersonState('柳娘', identity='夜客', status='未登场',
                            debut_day=9, secret='他是三百年前的人'),
    }
    w.progress_nodes = [{'id': 'K2', '名称': '门口醒来', '概要': '主角在门口醒来',
                         '完成判据': '有人收留', '状态': '未开始'}]
    w.current_node = 'K2'
    w.relations = [{'甲': '主角', '乙': '阿福', '关系': '收留他的人'}]
    return w


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑
# [EN] A. Pure logic
# ══════════════════════════════════════════════════════════════
def logic_checks() -> None:
    from world import crowd as C
    from world.state import PersonState
    from sim.setup import _parse_debut
    from agent.core import idle_kind, Action

    # ── A1 在场：未登场 / 地点不对 都不算 ──
    # [EN] -- A1 Presence: not yet appeared / wrong location do not count --
    w = _world()
    ok('A1 ★ 在场 = 这一刻在这儿的人（未登场的人**不在**名单里）',
       w.on_stage_names() == ['主角', '阿福'], w.on_stage_names())
    ok('A1b 未登场的人单独一清二楚（开场那句「未登场：…」用它）',
       w.pending_names() == ['柳娘'], w.pending_names())
    w.people['阿福'].location = '城东渡口'
    ok('A1c ★ 人 `move` 去了别处 → **不再算在场**（以前只看角色分栏，地点根本不参与）',
       w.on_stage_names() == ['主角'] and w.off_stage_names() == ['阿福'],
       f'在场={w.on_stage_names()} 离场={w.off_stage_names()}')
    w.people['阿福'].location = '临河茶肆后厨'
    ok('A1d 地点判定**从宽**：「临河茶肆后厨」仍算在「临河茶肆」这场戏里（不误伤）',
       '阿福' in w.on_stage_names(), w.on_stage_names())
    w.people['阿福'].location = ''
    ok('A1e 没定位的人算在场（装配时多数人没有初始位置，别把人滤没了）',
       '阿福' in w.on_stage_names(), w.on_stage_names())

    # ── A2 登场推进 ──
    # [EN] -- A2 Appearance advancement --
    w2 = _world()
    ok('A2 到日子的人才登场（第 9 天之前不放出来）',
       w2.promote_debuts(3) == [] and '柳娘' not in w2.on_stage_names(),
       w2.on_stage_names())
    ok('A2b ★ 到日子那天真的会登场（不推进的话 `debut_day` 就是个摆设）',
       w2.promote_debuts(9) == ['柳娘'] and '柳娘' in w2.on_stage_names(),
       w2.on_stage_names())
    ok('A2c 登场过的人记了 `met`（续跑介绍"已识人物"要用）',
       w2.people['柳娘'].met is True, w2.people['柳娘'].met)

    # ── A3 「登场」写法 ──
    # [EN] -- A3 "Appearance" notation --
    got = {x: _parse_debut(x) for x in ('', '第3天', '3', '三天', '未登场', '后期')}
    ok('A3 「登场」字段认这几种写法：留空=第1天 / 第3天 / 3 / 三天 / 未登场',
       got[''] == 1 and got['第3天'] == 3 and got['3'] == 3 and got['三天'] == 3
       and got['未登场'] >= 999 and got['后期'] >= 999, got)
    ok('A3b ★ 认不出的写法**当第 1 天**（猜晚会让该出场的人不出场，代价不对称）',
       _parse_debut('??') == 1, _parse_debut('??'))

    # ── A4 客流 ──
    # [EN] -- A4 Foot traffic --
    dry = C.crowd_size(_world(weather='晴', hour=11))
    wet = C.crowd_size(_world(weather='暴雨', hour=11))
    night = C.crowd_size(_world(weather='晴', hour=3))
    ok('A4 ★ 客流跟着天气走（暴雨天明显比晴天少）', wet < dry, f'晴={dry} 暴雨={wet}')
    ok('A4b ★ 客流跟着时辰走（凌晨比晌午少）', night < dry, f'晌午={dry} 凌晨={night}')
    ok('A4c 场所也参与（街市 > 宅院）',
       C.crowd_size(_world(scene='城东街市')) > C.crowd_size(_world(scene='某家宅院')),
       f"{C.crowd_size(_world(scene='城东街市'))} vs "
       f"{C.crowd_size(_world(scene='某家宅院'))}")

    # ── A5 群演：补/减 · 闸门 · 退场 ──
    # [EN] -- A5 Extras: add/remove · gate · exit --
    w3 = _world(weather='晴', hour=11)
    C.sync_crowd(w3)
    bg = [e for e in w3.extras if e['kind'] == '背景']
    ok('A5 客流 > 0 时**门外真的有人**（背景群演，零成本、不跑模型）',
       len(bg) > 0, [e['一行'] for e in bg][:2])
    ok('A5b 背景群演只给"一行"（它是场面，不是人物 —— 所以没有姓名/性格）',
       all('一行' in e and '姓名' not in e for e in bg), bg[:1])
    CFG.set('EXTRAS_DAILY_BUDGET', '1')
    CFG.set('EXTRAS_MAX_ALIVE', '6')
    first = C.new_extra(w3)
    second = C.new_extra(w3)
    ok('A5c ★ 功能群演受**当日预算**拦（第 2 个造不出来）',
       first is not None and second is None, f'1={bool(first)} 2={bool(second)}')
    ok('A5d 功能群演带**一个诉求**（"外部压力"的最小形态）',
       bool(first and first.get('诉求') and first.get('称呼')), first)
    CFG.set('EXTRAS_DAILY_BUDGET', '8')
    n_before = len(w3.extras)
    for _ in range(6):
        C.tick_extras(w3)
    ok('A5e ★ 群演到期会**退场回收**（不留僵尸）', len(w3.extras) < n_before,
       f'{n_before} → {len(w3.extras)}')
    CFG.set('EXTRAS_ENABLED', 'false')
    w4 = _world()
    C.sync_crowd(w4)
    ok('A5f 总开关关掉就一个也不造（`EXTRAS_ENABLED=false`）',
       w4.extras == [], w4.extras)
    CFG.set('EXTRAS_ENABLED', 'true')

    # ── A6 ★ 决策提示词：不再教人闲着 + 三层目标在位 ──
    # [EN] -- A6 ★ Decision prompt: no longer teaching people to idle + three-layer goals in place --
    w5 = _world()
    C.sync_crowd(w5)
    captured: list = []

    async def fake_chat(tier, messages, **kw):
        # ⚠ `Agent.decide()` 用的是 `return_meta=True` → 桩**必须回二元组**。
        #   只回字符串的话解包就炸、被 except 吞成降级 wait，
        #   于是"提示词判据"照样绿、而动作类判据全错（第一版就这么栽的）。
        # [EN] ⚠ `Agent.decide()` uses `return_meta=True` → the stub **must return a tuple**.
        # [EN] If it only returns a string, unpacking blows up and gets swallowed by except into a degraded
        # [EN] wait,
        # [EN] so the "prompt criteria" stay green while all action-type criteria are wrong (that's how the
        # [EN] first version failed).
        captured.append(messages[0]['content'] if messages else '')
        return ('{"动作":"interact","参数":{"目标":"把账本翻出来"},"理由":"今天的活"}',
                {'truncated': False, 'max_tokens': 800})

    from agent import core as AC
    from store.db import DB
    real = AC.llm.chat
    tmpdb = Path(tempfile.mkdtemp(prefix='nws_sd_')) / 't.db'
    try:
        AC.llm.chat = fake_chat
        ag = AC.Agent(w5.people['阿福'], DB(tmpdb), w5)
        asyncio.run(ag.decide())
    finally:
        AC.llm.chat = real
    prompt = captured[0] if captured else ''
    report['prompt_head'] = prompt[:200]
    ok('A6 ★★ 提示词里**没有**"比如「擦紫砂壶」"那种教人闲着的示例'
       '（真机日志里那句话被抄了 565 遍）',
       '擦紫砂壶' not in prompt and '手头有事就继续做' not in prompt, '')
    ok('A6b ★ 改成"推进你此刻最想推进的事"了', '推进你此刻最想推进的事' in prompt, '')
    ok('A6c ★ 明确写了「不要重复同一个原地动作」', '不要重复同一个原地动作' in prompt, '')
    ok('A6d ★ 三层目标在 prompt 里：这一站（进度节点）/ 今天（计划）/ 门外（外部输入）',
       '[这一站]' in prompt and '门口醒来' in prompt and '[门外/堂上]' in prompt,
       prompt[prompt.find('[这一站]'):prompt.find('[这一站]') + 60].replace('\n', '⏎'))

    # ── A7 反空转闸 ──
    # [EN] -- A7 Anti-idling gate --
    ok('A7 「原地打转」的判定：wait / 空 think / **无目标的 interact**',
       idle_kind(Action('wait')) == 'wait'
       and idle_kind(Action('interact', '')) == 'interact(无目标)'
       and idle_kind(Action('interact', '翻账本')) == ''
       and idle_kind(Action('speak', dialogue='嗯')) == '',
       '')
    w6 = _world()
    w6.progress_nodes = []          # 三层目标全空
    # [EN] All three-layer goals empty
    w6.current_node = ''
    w6.people['阿福'].goal = ''
    w6.people['阿福'].day_plan = []
    seen: list = []

    async def fake_wait(tier, messages, **kw):
        return ('{"动作":"wait","参数":{"目标":""},"理由":"没事做"}',
                {'truncated': False, 'max_tokens': 800})

    try:
        AC.llm.chat = fake_wait
        ag2 = AC.Agent(w6.people['阿福'], DB(tmpdb), w6)
        act2 = asyncio.run(ag2.decide())
        seen.append(act2)
    finally:
        AC.llm.chat = real
    ok('A7b ★★ 三层目标全空 + 输出 wait → **闸门留痕**（不替人物改主意，但要能查出来）',
       bool(seen) and '反空转闸' in str(seen[0].reason), seen[0].reason if seen else '')

    # ── A8 开场：字段规格与红线 ──
    # [EN] -- A8 Opening: field spec and red lines --
    from sim import opening as OP
    w7 = _world()
    op = OP.collect(w7, mode='story')
    text = OP.render_text(op, detail='full', title='测试', prose='雨脚敲在檐上，灯还没点。')
    ok('A8 开场只列**本场在场**的人（未登场的柳娘不在「登场人物」里）',
       '柳娘' not in text.split('未登场')[0], text[:120].replace('\n', '⏎'))
    ok('A8b ★★ **秘密一律不进开场**（"他知道楼底下埋着什么"不许出现）',
       '楼底下埋着' not in text and '三百年前' not in text, '')
    ok('A8c ★ 「未登场」只写**哪天会来**，不写是谁（不剧透）',
       '未登场' in text and '第 9 天' in text and '三百年前的人' not in text,
       [ln for ln in text.splitlines() if '未登场' in ln])
    ok('A8d 人物三行都在：姓名·身份 / 关系 / 当下（+标志）',
       '主角　掌柜' in text and '收留他的人' in text and '当下：' in text, '')
    ok('A8e ★ 引子有字数上限（60~150 字）—— 超了截、短了不凑',
       len(OP.assembled_prose(op)) <= 200 and OP.PROSE_MAX == 150,
       OP.assembled_prose(op)[:60])
    brief = OP.render_text(op, detail='brief')
    ok('A8f `brief` 档更短（每人只剩一行）',
       len(brief) < len(text) and brief.count('▸') == text.count('▸'), '')
    md_novel = OP.render_md(op, title='测试', detail='full', for_novel=True)
    ok('A8g ★ 导出给读者看的稿子里**剃掉「未登场」**（那是作者的体检表）',
       '未登场' not in md_novel and '未登场' in OP.render_md(op, title='测试'),
       '')
    # 截断：超长身份/目标要截到 ≤30 字（含省略号）
    # [EN] Truncation: overly long identity/goals must be truncated to ≤30 chars (including ellipsis)
    from world.state import PersonState
    w7.people['长'] = PersonState('长', identity='甲' * 80, goal='乙' * 80)
    rows = OP.person_rows(w7, '长')
    # 行宽 = 名字(1) + 全角空格(1) + 正文(≤30) ≈ 32；「当下：」那行再多 3 字。
    # 判的是"截断真的生效了"（含省略号），不是卡死一个整数。
    # [EN] Line width = name(1) + full-width space(1) + body(≤30) ≈ 32; the "现在:" line is 3 chars more.
    # [EN] It checks that "truncation actually took effect" (including ellipsis), not pinning a fixed
    # [EN] integer.
    ok('A8h 人物每行有上限（超了截断带省略号，不许撑破屏幕）',
       all(len(r) <= 36 for r in rows) and any('…' in r for r in rows), rows)
    ok('A8i 谁都不在场时，开场照样能给（只剩场景块，不炸）',
       '登场人物' in OP.render_text(OP.collect(_world(), mode='story')), '')

    # ── A8j/A8k 形态分工（2026-10-06 改成"卡片进中栏"之后新增的）──
    #   屏幕用 markdown、命令行/落盘 txt 用等宽框 —— 两条都不能串味。
    # [EN] -- A8j/A8k form division (added after the 2026-10-06 change to "card goes in the center column")
    # [EN] --
    # [EN] The screen uses markdown, the command line/saved txt uses a monospace box -- neither may bleed
    # [EN] into the other.
    ok('A8j ★ 等宽形态里**不再有**「开演 / 导出这一屏」那套按键（那个交互取消了）',
       '[Enter]' not in text and '开演' not in text and '导出这一屏' not in text,
       [ln for ln in text.splitlines() if '开场.md' in ln])
    ok('A8k ★ 屏幕形态（`render_md`）带 `## 登场人物` 与「起始节点」，'
       '落盘文件名引常量不硬编码',
       '## 登场人物' in OP.render_md(op, title='测试')
       and '起始节点' in OP.render_md(op, title='测试')
       and OP.FILE_NAME == '开场.md', OP.FILE_NAME)


# ══════════════════════════════════════════════════════════════
#  B. 真机
# [EN] B. Real machine
# ══════════════════════════════════════════════════════════════
def find_btn(root, label: str):
    for c in VU.walk(root):
        if hasattr(c, 'on_click') and c.on_click and label in VU.text_of(c):
            return c
    return None


async def gui_checks(page: ft.Page, app, tmp: Path) -> None:
    from verify_run_control import make_project

    proj = make_project(tmp / '开场验证')
    app.current_project = proj
    app.show_main_screen()
    await asyncio.sleep(1.0)

    # ⚠ **设在这里，不设在模块顶部**：`app.main()` 里会把 .env 重新读一遍，
    #   模块顶部设的值会被它盖掉（实测：顶部设了 'true'，进到这里 raw 又变回 'false'）。
    #   这段是**脚本自足**用的 —— 用户把 SHOW_OPENING 关了，也不该让这条判据跟着红。
    # [EN] ⚠ **Set here, not at module top**: `app.main()` re-reads .env,
    # [EN] values set at module top get overwritten by it (measured: set to 'true' at top, by the time we
    # [EN] get here raw is back to 'false').
    # [EN] This section is for **script self-containment** -- even if the user turned SHOW_OPENING off,
    # [EN] this criterion should not turn red because of it.
    CFG.set('SHOW_OPENING', 'true')
    print('  [诊断] SHOW_OPENING =', CFG.b('SHOW_OPENING'),
          '| DETAIL =', CFG.s('OPENING_DETAIL'), flush=True)
    dlg = app.show_start_story_dialog()
    page.update()
    await asyncio.sleep(0.6)
    btn = find_btn(dlg, t('开始推演'))
    ok('B1 找得到「开始推演」', btn is not None, '')
    if btn is not None:
        btn.on_click(None)
    # ⚠ **别只 sleep 一个固定秒数**：点完按钮之后要先装配世界（读设定集 + 建世界），
    #   快慢取决于机器。轮询到"会话真的起来了"为止，最多等 20 秒。
    # [EN] ⚠ **Don't just sleep a fixed number of seconds**: after clicking the button the world must first
    # [EN] be assembled (read the setting collection + build the world),
    # [EN] speed depends on the machine. Poll until "the session is really up", waiting at most 20 seconds.
    for _ in range(200):
        await asyncio.sleep(0.1)
        if app.session is not None and app.session.is_alive:
            break
    await asyncio.sleep(0.5)

    # ── 开场：**一张卡**，不是一屏对话框（2026-10-06 用户改的）──
    #   原话：「不需要对话框，做一个卡片放到对话里就好，也不用等，
    #   确认了直接开始就行」。所以三条一起验：不弹框 · 进中栏 · 直接开跑。
    # [EN] -- Opening: **one card**, not a screen of dialogs (changed by user 2026-10-06) --
    # [EN] Original words: "No need for a dialog, just make a card and put it in the conversation, and no
    # [EN] need to wait,
    # [EN] once confirmed just start". So verify all three together: no popup · goes in the center column ·
    # [EN] starts running directly.
    dlgs = VU.open_dialogs(page)
    report['dialogs_after_start'] = [VU.all_texts(d)[:2] for d in dlgs]
    # ⚠ 特征要用**卡片形态**的标记（`## 登场人物`），不能用等宽形态的 `【场景】`
    #   —— 卡片走的是 markdown，永远不含 `【场景】`，拿它判会**恒真**。
    #   同理：`open_dialogs()` 会把 SnackBar 也算进来（它也 `open=True`），
    #   所以只能查"有没有**开场内容**的浮层"，不能查"有没有任何浮层"。
    # [EN] ⚠ The feature must use the **card form** marker (`## 登场人物`), not the monospace-form `【场景】`
    # [EN] -- cards go through markdown, never contain `【场景】`, checking with it will be **always true**.
    # [EN] Likewise: `open_dialogs()` also counts SnackBar (it's also `open=True`),
    # [EN] so we can only check "is there an overlay with **opening content**", not "is there any overlay
    # [EN] at all".
    ok('B2 ★★ 开跑**不弹开场对话框**（用户要的是"不用等"）',
       not any(any('## 登场人物' in x for x in VU.all_texts(d)) for d in dlgs),
       report['dialogs_after_start'])
    ok('B3 ★★ 点了「开始推演」就**直接开跑**（没有停下来等点「开演」）',
       app.session is not None and app.session.is_alive,
       getattr(app.session, 'status', None))

    cards = [x for x in app._live_lines if x[2] == 'opening']
    report['opening_cards'] = len(cards)
    ok('B3b ★★ 开场以**卡片**进了中栏的叙事流（kind=opening）',
       len(cards) == 1, f'卡片数={len(cards)}')
    # ⚠ 2026-10-11：起笔时中栏会**先**推一条「这一轮从哪儿开始」的说明
    #   （kind='note' —— 那是**元信息**，不是叙事）。所以不能拿"字面上第一条"
    #   去判，要**跳过机制类词条**再看 —— 这条断言的原意是
    #   「开场卡排在第一句**叙事**之前」（用户：开场是这一轮的第一块内容）。
    #   不跳的话，正确的实现反而被判红（我这次就是）。
    # [EN] ⚠ 2026-10-11: at the start, the center column **first** pushes a "where does this round start
    # [EN] from" note
    # [EN] (kind='note' -- that's **meta info**, not narrative). So we can't judge by "literally the
    # [EN] first",
    # [EN] we must **skip mechanism-type entries** and look again -- the original intent of this assertion
    # [EN] is
    # [EN] "the opening card comes before the first **narrative** line" (user: the opening is the first
    # [EN] block of content of this round).
    # [EN] If we don't skip, a correct implementation gets judged red instead (that's exactly what happened
    # [EN] to me this time).
    #
    #   ✅ **能红**（2026-10-11 手工验过，本支没有专门的反例法）：
    #      在 `_push_opening_card` 之前垫一条 `narration`，这条当场变红
    #      （实测 detail = `['note', 'narration', 'opening', 'recap', 'crew']`）。
    # [EN] ✅ **Can go red** (manually verified 2026-10-11, this branch has no dedicated counterexample
    # [EN] method):
    # [EN] Insert a `narration` before `_push_opening_card`, and this one goes red on the spot
    # [EN] (measured detail = `['note', 'narration', 'opening', 'recap', 'crew']`).
    # ⚠ 读法用**下标**、不用解包（2026-10-11 改）：`_live_lines` 的元素从
    #   `(priority, text, kind)` 扩成四元组（尾部加了时间戳 `ts`，见
    #   `gui/app_flet._stamp`），`for _p, _t, k in …` 会当场
    #   `ValueError: too many values to unpack`（多值解包会当场报错）。
    #   ★ 判据的**语义没变**（"这一段序列里各种词条类型是怎么排的"），
    #     变的只是**读法** —— 下标记法容忍末尾多出字段，与
    #     `display/story_render` 那套（`len(row) > 2` + `row[2]`）同一手法。
    # [EN] ⚠ Read it with **indices**, not unpacking (changed 2026-10-11): `_live_lines` elements grew
    # [EN] from `(priority, text, kind)` to a 4-tuple (a timestamp `ts` appended, see
    # [EN] `gui/app_flet._stamp`), and `for _p, _t, k in …` raises
    # [EN] `ValueError: too many values to unpack` on the spot.
    # [EN] ★ The criterion's **meaning is unchanged** ("how the various entry kinds are ordered in this
    # [EN] sequence"); only the **reading** changed -- indexing tolerates extra trailing fields, the
    # [EN] same technique as `display/story_render` (`len(row) > 2` plus `row[2]`).
    _seq = [it[2] for it in app._live_lines
            if it[2] != 'note' and not str(it[2]).startswith('divider')]
    ok('B3c ★ 它是这一轮的**第一条叙事/卡片**（排在正文之前）—— '
       '判的时候跳过 `note` 这类机制标注',
       bool(cards) and bool(_seq) and _seq[0] == 'opening',
       [it[2] for it in app._live_lines[:5]])
    body = cards[0][1] if cards else ''
    report['opening_card_text'] = body[:300]
    ok('B3d 卡片正文是 Markdown（`## 登场人物` + 人物列表）',
       '## 登场人物' in body and '- **' in body, body[:70].replace('\n', '⏎'))
    ok('B3e ★ 卡片里**没有秘密**（红线：秘密一律不进开场）',
       '秘密' not in body, '')

    # 控件树取证：这张卡真的挂到了中栏（不是只记了数据）
    # [EN] Widget tree forensics: this card is really attached to the center column (not just data
    # [EN] recorded)
    col = app._ui_run.get('narrative')
    md_ctl = None
    for c in (VU.walk(col) if col is not None else []):
        if type(c).__name__ == 'Markdown' and body[:30] \
                and body[:30] in str(getattr(c, 'value', '')):
            md_ctl = c
            break
    ok('B3f ★ 这张卡真的挂在中栏控件树里（不是只记了数据）',
       md_ctl is not None, type(md_ctl).__name__ if md_ctl else '中栏里没找到')
    png = await page.take_screenshot()
    (OUT / 'story_depth_opening.png').write_bytes(png or b'')

    run = app.session.run if app.session else None
    op_md = (run.root / OP.FILE_NAME) if run else None
    ok('B4 ★ 开场仍然落盘到 `<运行文件夹>/开场.md`（与 任务介绍.md 分开）',
       bool(op_md and op_md.exists()), str(op_md))
    if op_md and op_md.exists():
        md = op_md.read_text(encoding='utf-8')
        # ⚠ 别把夹具里的人物名字写进判据（那个项目是 `make_project` 造的，
        #   人物叫主角/柳氏，不是《临河茶肆》的主角）—— 第一版就是这么红的。
        # [EN] ⚠ Don't write the fixture's character names into the criteria (that project is built by
        # [EN] `make_project`,
        ok('B4b 落盘的开场里有场景与人物（不是空文件）',
           '## 登场人物' in md and '- **' in md, md[:80].replace('\n', '⏎'))
        ok('B4c ★★ 卡片上看到的 **就是** 文件里存的（同一份文本）',
           md.strip() == body.strip(),
           f'文件 {len(md)} 字 vs 卡片 {len(body)} 字')

    # 跑几拍：群演/客流真的在动
    # [EN] Run a few beats: extras/foot traffic are really moving
    await asyncio.sleep(6.0)
    w = app.session.world if app.session else None
    extras = list(getattr(w, 'extras', []) or [])
    report['extras'] = [e.get('一行') for e in extras][:4]
    ok('B5 ★★ 跑起来之后**门外真的有人**（客流/群演在工作）',
       len(extras) > 0, report['extras'])
    ok('B5b 在场名单不是"整份名册"（拿到的是那一刻的判断结果）',
       isinstance(w.on_stage_names(), list) and len(w.on_stage_names()) <= len(w.people),
       w.on_stage_names())

    # 重看开场（`show_current_opening`：**再推一张卡**，与开场本身同一形态，不弹对话框）
    # [EN] Re-view opening (`show_current_opening`: **push another card**, same form as the opening
    # [EN] itself, no dialog popup)
    before = len([x for x in app._live_lines if x[2] == 'opening'])
    res = app.show_current_opening()
    await asyncio.sleep(0.4)
    after = len([x for x in app._live_lines if x[2] == 'opening'])
    ok('B6 ★ 重看本轮开场（再推一张卡，不是又弹一个框）',
       after == before + 1, f'{before} → {after} | {res}')
    ok('B6b 重看也不弹**开场**对话框（SnackBar 那种即时提示不算）',
       not any(any('## 登场人物' in x for x in VU.all_texts(d))
               for d in VU.open_dialogs(page)),
       [VU.all_texts(d)[:1] for d in VU.open_dialogs(page)])

    # ── 像素取证：这张卡**真的画在屏幕上**（控件树里有 ≠ 看得见）──
    #   ⚠ 必须在**跑着的时候**做：中栏在"没在跑"时会回落到落盘的最近一天
    #     （`live=False` 那条分支），那时 `_live_lines` 根本不参与渲染 ——
    #     停跑之后再量，量到的是 0 像素（第一版就是这么红的，白查半天）。
    #   ⚠ 也不能直接量：跑起来 `auto_scroll` 会把开场（它是第一条）滚出视野，
    #     同样是假红。所以把流里只留开场卡、重建一次界面，它就没得滚。
    # [EN] -- Pixel forensics: this card is **really drawn on screen** (present in widget tree ≠ visible)
    # [EN] --
    # [EN] ⚠ Must be done **while it's running**: when not running, the center column falls back to the
    # [EN] last saved day
    # [EN] (the `live=False` branch), at which point `_live_lines` doesn't participate in rendering at all
    # [EN] --
    # [EN] measuring after stopping gives 0 pixels (that's how the first version went red, wasted half a
    # [EN] day).
    # [EN] ⚠ Also can't measure directly: once running, `auto_scroll` scrolls the opening (it's the first
    # [EN] line) out of view,
    # [EN] also a false red. So leave only the opening card in the stream, rebuild the UI once, and it has
    # [EN] nothing to scroll.
    real = app._live_lines
    app._live_lines = [x for x in real if x[2] == 'opening'] or cards
    app.show_main_screen()
    await asyncio.sleep(0.5)
    col2 = app._ui_run.get('narrative')
    card_ctl = None
    for c in (getattr(col2, 'controls', None) or []):
        # ⚠ **不要钉死 `content.controls[0]`**（2026-10-11 修）：开了时间戳之后，
        #   每条外面套了一层 `_wrap_ts` 的壳，壳里第一个孩子是**时间戳那行小字**、
        #   卡片本体排到第二 —— 原来那句 `kids[0]` 于是永远找不到（B6c 假红、
        #   B7 跟着量到 0 像素）。改成在整棵子树里找那张 Markdown，
        #   结构怎么套都不影响"这张卡在不在"。
        # [EN] ⚠ **Do not pin `content.controls[0]`** (fixed 2026-10-11): with timestamps on, every
        # [EN] entry is wrapped in a `_wrap_ts` shell whose first child is the **timestamp line**, so
        # [EN] the card itself moves to second place -- the old `kids[0]` therefore never matched
        # [EN] (B6c falsely red, B7 then measured 0 pixels). Changed to search the whole subtree for
        # [EN] that Markdown, so nesting depth no longer matters for "is this card present".
        for k in VU.walk(c):
            if type(k).__name__ == 'Markdown' \
                    and str(getattr(k, 'value', '')).startswith(body[:20]):
                card_ctl = c
                break
        if card_ctl is not None:
            break
    ok('B6c ★ 重建界面后开场卡仍在中栏（`_live_lines` 是本轮的事实来源）',
       card_ctl is not None, type(card_ctl).__name__ if card_ctl else '没找到')
    if card_ctl is not None:
        # ⚠ **标记色要涂在\"真正是容器的那个控件\"上**（2026-10-11 修）：
        #   开着时间戳时 `card_ctl` 是外层 `_wrap_ts` 的 `Column`，而 `Column`
        #   **没有背景色这回事** —— 给它设 `bgcolor` 只是往对象上挂了个没人看的
        #   属性，屏幕上一点变化都没有（B7 量到 0 像素，白查一轮）。
        #   涂到 `_narr_inner`（壳里那个真容器）上才看得见。
        # [EN] ⚠ **Paint the marker color on the control that really is a container** (fixed
        # [EN] 2026-10-11): with timestamps on, `card_ctl` is the outer `_wrap_ts` `Column`, and a
        # [EN] `Column` **has no such thing as a background color** -- setting `bgcolor` on it just
        # [EN] hangs an unread attribute on the object with no visual change (B7 measured 0 pixels,
        # [EN] a wasted round). Painting `_narr_inner` (the real container inside the shell) is what
        # [EN] shows up.
        paint = getattr(card_ctl, '_narr_inner', None) or card_ctl
        paint.bgcolor = '#ff00ff'        # 标记色：全项目没人用（只动颜色不动几何）
        # [EN] Marker color: nobody in the whole project uses it (only color changes, no geometry)
        try:
            page.update()
        except Exception:                                    # noqa: BLE001
            pass
    await asyncio.sleep(0.3)
    png = await page.take_screenshot()
    (OUT / 'story_depth_opening_card.png').write_bytes(png or b'')
    n_mag = 0
    if png and card_ctl is not None:
        import io as _io
        from PIL import Image
        im = Image.open(_io.BytesIO(png)).convert('RGB')
        n_mag = sum(1 for px in im.getdata()
                    if px[0] > 200 and px[1] < 80 and px[2] > 200)
    report['card_px'] = n_mag
    ok('B7 ★★ 开场卡**真的画在屏幕上**（标记色量到成块面积，不是只有控件树里有）',
       n_mag > 2000, f'{n_mag} 像素')
    app._live_lines = real          # 复原真实的流
    # [EN] Restore the real stream

    app._on_stop_run()
    await asyncio.sleep(1.0)
    if app.session is not None:
        await app.session.wait(15)


async def entry(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp
    tmp = Path(tempfile.mkdtemp(prefix='nws_sd_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    # ⚠ **点「开始推演」会 `CFG.save()`**，把脚本里 `CFG.set('MOCK_LLM','true')`
    #   这类测试值写进**用户的 .env**（2026-10-06 实测踩到：MOCK_LLM 被改成 true、
    #   BEAT_SECONDS 被改成 2）。所以整段真机流程前后做备份/还原 ——
    #   别只包"点按钮那一瞬"：按钮触发的是**异步流程**，with 块会在它跑完前结束。
    # [EN] ⚠ **Clicking "开始推演" calls `CFG.save()`**, writing the script's `CFG.set('MOCK_LLM','true')`
    # [EN] and such test values into the **user's .env** (measured on 2026-10-06: MOCK_LLM was changed to
    # [EN] true,
    # [EN] BEAT_SECONDS was changed to 2). So back up/restore around the whole real-machine flow --
    # [EN] don't just wrap "the instant the button is clicked": the button triggers an **async flow**, the
    # [EN] with block ends before it finishes.
    env_path = APP_DIR / '.env'
    env_backup = env_path.read_text(encoding='utf-8') if env_path.exists() else None
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.8)
    try:
        await gui_checks(page, app, tmp)
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    finally:
        if env_backup is not None:
            try:
                env_path.write_text(env_backup, encoding='utf-8')
                report['env_restored'] = True
            except OSError as e:                               # noqa: BLE001
                report['env_restore_error'] = str(e)
    await shutdown(page, code=finish())


def finish() -> int:
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'story_depth_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"\n故事深度验证：{len(report['checks']) - len(bad)}/{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1500:])
    print('报告：assets/screenshots/story_depth_report.json')
    return 0 if report['ok'] else 2


def main() -> int:
    if '--logic-only' in sys.argv:
        try:
            logic_checks()
        except BaseException:                                  # noqa: BLE001
            report['fatal'] = traceback.format_exc()
        return finish()
    try:
        logic_checks()
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    ft.run(entry)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
