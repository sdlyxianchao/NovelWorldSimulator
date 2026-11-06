# -*- coding: utf-8 -*-
"""判据：**这一段是不是各说各话**（对话接续 + 场景/话题延续）。

来历（2026-10-18 用户原话）
---------------------------
「雪国的小说 好几次人物说的话互相不对应 就是一个人说的话 另外一个人不去接
 两个人各说各话的现象到处存在。还是这个问题，在很短的一段时间内 出场人物应该是
 按照一个主题展开对话的 而不是每个人自己一个主题 中间应该有协调者 特别是导演
 应该消除这种自说自话的问题…而且场景本身的迁移和场景之间的话题主题之间的延续性
 也是必须要注意的问题 大的故事应该有一个接一个的小故事组成 小故事则有一个接一个
 的场景组成 这之间除非有特殊的安排 比如剧情跳跃或者故意简略 否则应该都是有连续性的」

先量（`developers/probe_dialogue_cohesion.py`，三份真产物）：

| 产物 | 接话率 | 最长无人接 |
|---|---|---|
| 雪国 ykg-01（18 拍） | **0.273** | **4 句** |
| 边城 bc-01 | 0.500 | 2 句 |
| 西游 xyj-01 | 0.900 | 1 句 |

雪国那段三个话题并行（驹子质问 / 叶子招呼 / 岛村回避），
**而每个人单独看都"说得对"** —— 这类错任何单人护栏都抓不到。

它和"重复"必须在不同层解决（两件事）：
  · 好几个人**说同一句话** ⇒ `scan_repetition`（已有）
  · 好几个人**各说各的** ⇒ 本条（对话接续）

守的四件事：
  A. `talk_audit()` 判得对（能认出各说各话、**不误报正常对话**）
  B. 它给的"话题锚 / 谁欠一句"真的用得上（不是算完就扔）
  C. 提示词里**真挂上了**（真跑抓 prompt，不看 AST）
  D. 换场**不丢**话题、收工**才清**（用户要的场景间延续）

跑法：`.venv/Scripts/python.exe tools/verify_dialogue_cohesion.py`
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail='') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(f'  {"✓" if cond else "✗"} {name}'
          + (f'   [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _src(rel: str) -> str:
    return _read(rel)


#: 雪国那段的**真实台词序列**（`rhythm-ykg` 的 transcript 里逐字抄下来的）
#: ⚠ 夹具用真产物，不用自己编 —— 编的夹具会正好躲开真实的坏形状。
# [EN] The **real** dialogue sequence from the Snow Country run, copied verbatim from its
# [EN] transcript. ⚠ Fixtures come from real output; hand-made ones dodge the real bad shape.
#: 雪国 `story-1000`（18 拍）的**真实台词序列，逐字从 transcript 抄下来**。
#: ⚠ 不许简化！第一版我"照记忆"写，把 `（向岛村）` 省掉了 ⇒ `to` 字段全空
#:   ⇒ A2（谁欠一句）找不到人，而解析器本身是对的。
#:   夹具必须**逐字**来自真实产物：省掉一个括号，测的就不是那条路。
# [EN] The **real** dialogue sequence of Snow Country `story-1000` (18 beats), copied verbatim
# [EN] from the transcript. ⚠ Never simplify it: the first version wrote it "from memory" and
# [EN] dropped `(to Shimamura)`, so every `to` was empty => A2 found nobody, while the parser was
# [EN] fine. Fixtures must come **verbatim** from real output; dropping one bracket tests a
# [EN] different path.
BAD = [
    '驹子：（向岛村）（声音轻得仿佛被雪吸走）我……',
    '叶子：（向岛村）（站在纸门外，声音清亮地）先生。',
    '驹子：（向岛村）……雪还下着么。',
    '驹子：（向岛村）你这个人哪……怎么不说话。',
    '驹子：岛村先生，您到了呀，路上还顺利吗？',
    '叶子：岛村先生，热水备好了，要去泡吗？',
    '岛村：嗯，先看看吧，不着急。',
    '驹子：（向岛村）（声音稍大了些，带着些倔强）岛村先生，您倒是说句话呀。',
    '叶子：（向岛村）（站在纸门外，声音清亮地）先生，驹子姐她……（欲言又止）',
    '叶子：（向岛村）先生，水还温着。',
    '驹子：（向岛村）（抬头看他，声音轻得仿佛被雪吸走）我……我就是想看看您。',
    '驹子：（向岛村）岛村先生，您……觉得我是个什么样的人呢？',
    '叶子：（向岛村）（声音像唱歌般）先生，有新摘的果子，要尝尝吗？',
    '岛村：（对着纸门的方向，轻声）外面的雪，应该还在下吧。',
    '叶子：（在纸门外轻声应道）是呢，先生，雪还在下呢。',
    '驹子：（拉开纸门，笑着看向岛村）雪下得可大了，先生要去看看吗？',
]

#: 一段**正常的一问一答**（同一件事往下走）
# [EN] A **normal** exchange (one matter moving forward)
GOOD = [
    '沈砚对小伙计：更鼓是几时敲的。',
    '小伙计对沈砚：三更刚过，博士。',
    '沈砚对小伙计：漏刻呢，看过没有。',
    '小伙计对沈砚：漏刻快了，掌柜的说过。',
    '沈砚对小伙计：那就不是鼓手的错。',
]


# ══════════════════════════════════════════════════════════
#  A  `talk_audit` 判得对
# ══════════════════════════════════════════════════════════
def group_a() -> None:
    from director import supervisor as SUP

    issue, led = SUP.talk_audit(BAD)
    ok('A1 ★★★ 认出"各说各话"（雪国那段真台词：连着好几句子没人接）',
       issue is not None and int(led.get('run') or 0) >= 3,
       f"run={led.get('run')} issue={issue.line() if issue else None}")
    ok('A2 ★★★ 找得出**谁欠一句**（被点名多次、一句没回的那个人）',
       led.get('open_with') == '岛村', repr(led.get('open_with')))
    ok('A3 ★★★ 话题锚是**原样引文**，不是"这一段在讨论X"这种概括'
       '（引文是事实，概括要调模型且会歪）',
       bool(led.get('topic')) and led['topic'] in ''.join(BAD),
       repr(led.get('topic')))
    # ⚠ 两条都要：不含"对"（没把 `对岛村` 当人名）**和**不含括号
    #   （括号没切干净时，`驹子（向岛村）` 会整个成为"一个人" ⇒ 谁接谁全错）。
    # [EN] Both: no 对 (did not swallow `to B`) **and** no bracket (an uncleaned bracket makes
    # [EN] `A (to B)` one single "person" => every link is wrong).
    _sp = led.get('speakers') or []
    ok('A4 ★★★ 说话人解析干净（既没把"对岛村"吃进人名，也没留下括号）',
       bool(_sp) and all('对' not in x and '（' not in x and '(' not in x for x in _sp),
       repr(_sp))
    # ⚠ 上面那条在 `BAD` 上**测不到 who 的括号**：那批行的括号都在**冒号后**
    #   （`驹子：（向岛村）…` ⇒ `who` 天然只有"驹子"）。
    #   要测"括号在冒号前"的写法，必须**另给一组夹具**；
    #   否则"人名解析不切括号"这个变异不会红（反例法 M03b 当场抓出来）。
    # [EN] ⚠ The check above cannot see brackets in `who` on the `BAD` fixture: there the brackets
    # [EN] are all **after the colon**, so `who` is naturally just the name. To test the
    # [EN] bracket-before-colon spelling you need **another fixture**; otherwise the "name parser
    # [EN] keeps the bracket" mutation stays green (caught by counterexample M03b).
    _mix = ['驹子（向岛村）（声音轻）：你这个人哪。', '叶子（向岛村）：先生，水还温着。']
    _mix_sp = SUP.talk_audit(_mix)[1].get('speakers') or []
    ok('A4b ★★★ 括号写在**冒号前**时，人名也要切干净（`驹子（向岛村）` 不许整个当人名）',
       bool(_mix_sp) and all('（' not in x and '对' not in x for x in _mix_sp),
       repr(_mix_sp))

    # ── 成对：正常对话**不许**报 ──
    g_issue, g_led = SUP.talk_audit(GOOD)
    ok('A5 ★★★ 成对：**正常的一问一答不报**（误报会让每拍都在"回档/重说"里打转）',
       g_issue is None, f"run={g_led.get('run')}")
    ok('A6 ★★ 成对：正常对话里 `open_with` 也不该乱指（最后一句冲着谁、谁答过）',
       g_led.get('open_with') in ('', '小伙计'), repr(g_led.get('open_with')))

    # 两句不接**不算**（真人对话里"听岔/各想各的"很常见，连到 3 句才是毛病）
    # ⚠ 夹具必须**真的**两句不接：第一版写的 `甲对乙` / `乙对丙` / `丙对甲`
    #   恰好首尾相接（a.to == b.who）⇒ run=0，于是"min_run 降到 1"的变异根本不红。
    # [EN] The fixture must **really** be two unlinked lines: the first version used
    # [EN] `A to B` / `B to C` / `C to A`, which happen to chain (a.to == b.who) => run=0, so the
    # [EN] "min_run lowered to 1" mutation stayed green.
    two = ['甲：外头下雪了。', '乙：灶上水开了。', '丙：柴不够了。']
    ok('A7 ★★★ 成对：只有**两句**不接不算（阈值 3 —— 低了会把正常对话判成毛病）',
       SUP.talk_audit(two)[0] is None,
       str(SUP.talk_audit(two)[1].get('run')))


# ══════════════════════════════════════════════════════════
#  B  算出来的东西**真的被用上**
# ══════════════════════════════════════════════════════════
def group_b() -> None:
    src = _src('sim/loop.py')
    ok('B1 ★★★ 每拍都算一次（不是每 N 拍 —— 这是零成本的，见 `talk_audit` 的说明）',
       '_audit_talk()' in src, '')
    ok('B2 ★★★ 算出来的三样**写进了世界**（否则算完就扔，谁也看不到）',
       all(f'world.topic{s}' in src or f"'{s}'" in src for s in ('', '_open_with', '_run'))
       and 'self.world.topic = ' in src
       and 'self.world.topic_open_with = ' in src
       and 'self.world.topic_run = ' in src, '')
    ok('B3 ★★★ **只算不拦**：这一层不删任何词条（删了会留空白，比各说各话更伤）',
       '_audit_talk' in src and '_drop_entries' not in src.split('def _audit_talk')[1]
       .split('def ')[0], '')
    ok('B4 ★★ 算不出来时**保持原值**（清零会让"上一场欠的那一句"凭空消失）',
       "if led.get('topic'):" in src and "if led.get('open_with'):" in src, '')

    # 选人：欠答的人**占满名额**，不是"挑一个 + 随机补"
    tree = ast.parse(src)
    tick = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == '_tick':
            tick = n
    body = ast.unparse(tick) if tick is not None else ''
    ok('B5 ★★★ 有人在等回答时，**这一拍的坑位先给他**（不是挑一个当领说、剩下的随机补）',
       'ordered[:slots]' in body and 'slots = max(1, min(2' in body,
       '')
    ok('B6 ★★★ 成对：**没人欠话时仍然随机补满**（不能因为改了选人就让人少说）',
       'random.sample(pool' in body, '')


# ══════════════════════════════════════════════════════════
#  C  提示词里**真挂上了**（真跑抓 prompt）
# ══════════════════════════════════════════════════════════
class _FakeDB:
    def retrieve_memory(self, *a, **k):
        return []

    def add_memory(self, *a, **k):
        pass

    def count_memories(self, *a, **k):
        return 0

    def get_summaries(self, *a, **k):
        return []

    def recent_events(self, *a, **k):
        return []


def _capture(*, topic: str, owe: str, run: int, recent: list) -> str:
    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    w.topic = topic
    w.topic_open_with = owe
    w.topic_run = run
    w.recent_lines = list(recent)
    ps = PersonState(name='主角', location='临河茶肆', role='前台',
                     identity='茶肆掌柜', personality='话少，先听后说',
                     current_goal='把账上的窟窿弄清')
    w.people['主角'] = ps
    a = Agent(ps, _FakeDB(), w)
    seen: dict = {}
    real = AC.llm.chat

    async def fake_chat(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '测试'}, ensure_ascii=False), {})

    AC.llm.chat = fake_chat
    try:
        asyncio.run(a.decide())
    finally:
        AC.llm.chat = real
    return str(seen.get('prompt') or '')


def group_c() -> None:
    _recent = [{'who': '伙计', 'text': '外头雪停了。', 'kind': 'speak',
                'to': '', 'place': '临河茶肆'}]
    p = _capture(topic='你倒是说句话呀。', owe='岛村', run=3, recent=_recent)
    ok('C1 ★★★ 真跑 `decide()` 抓到了 prompt（不是空跑）', len(p) > 500, f'{len(p)} 字')
    ok('C2 ★★★ 发出去的 prompt 里**真有** `[这一段在谈的]`，'
       '而且带着那句**引文**（不是"在某处提到过"）',
       '[这一段在谈的]' in p and '你倒是说句话呀' in p, '')
    ok('C3 ★★★ 里有"**岛村 还欠一句**"（点名要那个人先接）',
       '岛村 还欠一句' in p, '')
    ok('C4 ★★★ 里有"连着 **3 句**没人接"（把量出来的数告诉他，别只说"要接话"）',
       '连着' in p and '3 句' in p and '各说各话' in p, '')

    # ── 成对：正常对话**不啰嗦**（每拍挂一段"你在谈X"会把提示词变成噪声）
    p2 = _capture(topic='你冷不冷。', owe='', run=0, recent=_recent)
    ok('C5 ★★★ 成对：**没人欠话、也没连着断**时，这一段不挂'
       '（否则每拍都有一段"你在谈X"，模型会当背景噪声）',
       '[这一段在谈的]' not in p2 and '[上一场没说完的]' not in p2, '')

    # ── 换场：改成"上一场没说完的" ──
    p3 = _capture(topic='你倒是说句话呀。', owe='岛村', run=0, recent=[])
    ok('C6 ★★★ 刚换场（`[刚才]` 空）时，标题变成 `[上一场没说完的]`，'
       '并明写"把上一场没谈完的事**带过来**"（用户要的场景间延续）',
       '[上一场没说完的]' in p3 and '带过来' in p3, '')


# ══════════════════════════════════════════════════════════
#  D  换场不丢话题、收工才清
# ══════════════════════════════════════════════════════════
def group_d() -> None:
    from world.state import WorldState

    w = WorldState()
    w.topic = '你倒是说句话呀。'
    w.topic_open_with = '岛村'
    w.topic_run = 3
    w.clear_lines()
    ok('D1 ★★★ **换场不丢话题**（`clear_lines` 只清 `[刚才]`）—— '
       '清掉它，新场第一拍就没有上下文，只能自己开一个新话题',
       w.topic == '你倒是说句话呀。' and w.topic_open_with == '岛村',
       f'{w.topic!r} / {w.topic_open_with!r}')
    w.reset_topic()
    ok('D2 ★★★ 成对：**收工才清**（`reset_topic` 三样全清）',
       not w.topic and not w.topic_open_with and w.topic_run == 0, '')
    ok('D3 ★★ `_end_day` 真的调了 `reset_topic`（写在别处不算）',
       'reset_topic()' in _src('sim/loop.py').split('async def _end_day')[1][:1200], '')


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            ok(f'{fn.__name__} 执行失败', False, repr(e))
    bad = [c for c in CHECKS if not c[1]]
    print(f'\n对话接续/场景延续验证：{len(CHECKS) - len(bad)}/{len(CHECKS)}', flush=True)
    if bad:
        print('有失败项：', flush=True)
        for n, _, _d in bad:
            print(f'  ✗ {n}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
