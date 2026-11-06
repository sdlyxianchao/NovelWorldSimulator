#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""自由度验证：**任务规训**与**文笔规训**是两个旋钮，各管各的。

★★★ 这一支守的是什么（2026-10-19 用户把定位改成「推演工具」，随后点名拆分旋钮）
------------------------------------------------------------------------------
原话：「AGENT_FREEDOM 拆分成任务规训和文笔规训」。

拆的理由不是"多一个开关更灵活"，而是**两件事松开的后果不一样**：

| 旋钮 | 松开之后 | 代价 |
|---|---|---|
| 任务规训 | 人物自己决定干什么 | 剧情比"排好的戏"散，可能跑题、可能空转 |
| 文笔规训 | 句子可以更长/更野/更留白 | 可能出现**难看的句子**；口癖会回弹 |

一个旋钮同时管这两件事，会逼出两种坏结果之一：
· 想要意外 ⇒ 顺手把文笔也松了 ⇒ **更散且更难看**；
· 想保住文笔 ⇒ 连任务也不敢松 ⇒ 回到"照剧本演"。

⇒ 所以这一支最要紧的一条是 **C 组：正交性**。
   只判"两个旋钮各自有作用"是不够的 —— 那样"两个旋钮其实接的是同一根线"
   （改一个，两个都变）照样绿。必须判"**只动 A 时 B 一点不变，反之亦然**"。

⚠⚠ **两个旋钮都碰不到的那一条**：`SPEAKER_ISOLATION_RULES`（不许替别人说话）。
  它不是"规训"，是世界的物理法则。E 组把它钉在四个象限上（都是恰好 1 次）。
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

_n = _bad = 0


def ok(desc: str, cond: bool, detail: str = '') -> None:
    global _n, _bad
    _n += 1
    if not cond:
        _bad += 1
    print(f"  {'✓' if cond else '✗'} {desc}" + (f"  — {detail}" if detail else ''))


def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _at(task: float | None = None, style: float | None = None):
    """把两个档位**直接换掉**（绕开配置读取），返回恢复函数。

    ⚠ 不能用环境变量：`CFG` 在导入时就把值读进内存了，改 env 不会生效
      （第一版这么试过，三档拿到同一份 prompt —— 判据"什么都没看见"）。
    [EN] Swap both levels **directly**. ⚠ Environment variables do not work: `CFG` reads values
    [EN] into memory at import, so all three "bands" got the same prompt.
    """
    from agent import freedom as F

    ot, os_ = F.task_level, F.style_level
    if task is not None:
        F.task_level = lambda: task
    if style is not None:
        F.style_level = lambda: style

    def restore() -> None:
        F.task_level, F.style_level = ot, os_

    return restore


# ══════════════════════════════════════════════════════════════
#  A. 任务规训（三档）
# [EN] A. Task discipline (three bands)
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    from agent import freedom as F

    def probe(v: float) -> tuple[str, bool, float, str]:
        r = _at(task=v)
        try:
            return F.frame_scope(), F.stage_visible(), F.temperature(), F.license_line()
        finally:
            r()

    s0, st0, t0, lic0 = probe(0.0)
    s50, st50, t50, lic50 = probe(0.5)
    s90, st90, t90, lic90 = probe(0.9)

    ok('A1 ★★★ 任务规训低 = 照剧本演（full + 分拍表）',
       s0 == 'full' and st0 is True, f'{s0}/{st0}')
    ok('A2 ★★★ 任务规训中 = 只给要办的事（agenda，**不给分拍表**）',
       s50 == 'agenda' and st50 is False, f'{s50}/{st50}')
    ok('A3 ★★★ 任务规训高 = 只给议程（brief）',
       s90 == 'brief' and st90 is False, f'{s90}/{st90}')
    ok('A4 ★★ 温度随任务规训**单调上升**（它管的是"挑哪个动作"，不是"怎么写句子"）',
       t0 < t50 < t90, f'{t0:.2f} / {t50:.2f} / {t90:.2f}')
    ok('A5 ★★★ 温度**下限不是 0**（完全确定 = 播放录音，不是推演）'
       '且**上限不超过 0.95**（再高出语病与人形走失，那是故障不是自由）',
       t0 >= 0.5 and t90 <= 0.95, f'{t0:.2f}–{t90:.2f}')
    ok('A6 ★★★ 低任务规训**不给许可**（那时人物确实该照剧本演，给许可只会打架）',
       lic0 == '', repr(lic0[:30]))
    ok('A7 ★★★ 中/高任务规训**都给许可**（只删禁令，模型会停在原地 —— 必须成对补一句）',
       bool(lic50.strip()) and bool(lic90.strip()), '')
    ok('A8 ★★★ 许可里**明确排除两件事**（替别人说话 / 说出不可能知道的事）',
       '替别人说话' in lic50 and '不可能知道' in lic50, '')


# ══════════════════════════════════════════════════════════════
#  B. 文笔规训（三档）
# [EN] B. Prose discipline (three bands)
# ══════════════════════════════════════════════════════════════
def group_b() -> None:
    from agent import freedom as F

    def probe(sv: float) -> dict:
        r = _at(style=sv)
        try:
            return {'deai': F.deai_items(5), 'dist': F.distance_forced(),
                    'cot': F.cot_full(), 'tic': F.tic_quota(), 'lic': F.style_license()}
        finally:
            r()

    lo, mid, hi = probe(0.0), probe(0.5), probe(0.9)
    ok('B1 ★★★ 文笔规训低（很讲究）：清单全列 / 距离强制 / 思维链五问 / 口癖配额 / 无许可',
       lo['deai'] == 5 and lo['dist'] and lo['cot'] and lo['tic'] and lo['lic'] == '',
       f"{lo['deai']}/{lo['dist']}/{lo['cot']}/{lo['tic']}")
    ok('B2 ★★ 文笔规训中（标准）：清单比严格少；距离仍强制；思维链仍是五问',
       lo['deai'] > mid['deai'] and mid['dist'] and mid['cot'],
       f"清单 {lo['deai']}/{mid['deai']}/{hi['deai']} · "
       f"距离 {mid['dist']} · 思维链 {mid['cot']}")
    ok('B3 ★★★ 文笔规训高（松）：**距离不强制** / **思维链只留一问** / **口癖配额关**',
       not hi['dist'] and not hi['cot'] and not hi['tic'], str(hi))
    ok('B4 ★★★ 清单**永不降到 0**（0 条 = 提示词完全不提禁词，模型会大量写套话，'
       '而事后审计只能发现问题、救不回句子）',
       hi['deai'] >= 2, f"松档 {hi['deai']} 条")
    ok('B5 ★★★ 文笔许可**只在松/标准档出现**，且明确说"松的是句法、不是禁词表"'
       '（否则"松文笔"会被读成"允许 AI 腔"—— 那两件事相反）',
       '句法' in hi['lic'] and '禁词' in hi['lic'], hi['lic'][:60])
    ok('B6 ★★★ 而且它把**唯一不变的那条**写明：心声第一人称、不替别人说话',
       '第一人称' in hi['lic'], '')


# ══════════════════════════════════════════════════════════════
#  C. ★★★ 正交性（拆分这件事的全部意义）
# [EN] C. ★★★ Orthogonality (the whole point of splitting)
# ══════════════════════════════════════════════════════════════
def group_c() -> None:
    from agent import freedom as F

    def snap() -> dict:
        return {'scope': F.frame_scope(), 'stage': F.stage_visible(),
                'temp': round(F.temperature(), 4), 'lic': bool(F.license_line()),
                'deai': F.deai_items(5), 'dist': F.distance_forced(),
                'cot': F.cot_full(), 'tic': F.tic_quota(),
                'slic': bool(F.style_license())}

    def pair(task: float, style: float) -> dict:
        r = _at(task=task, style=style)
        try:
            return snap()
        finally:
            r()

    a_low, a_high = pair(0.0, 0.5), pair(0.9, 0.5)
    t_keys = ('deai', 'dist', 'cot', 'tic', 'slic')
    bad = [f'{k}:{a_low[k]}→{a_high[k]}' for k in t_keys if a_low[k] != a_high[k]]
    ok('C1 ★★★ **只动任务规训时，文笔那五项一个字都不变**'
       '（变了就是"两个旋钮接了同一根线"，拆了等于没拆）',
       not bad, ' / '.join(bad) or '全同')
    ok('C1b ★★★ 成对：而任务那三项**确实变了**（否则这条判据什么都没证明）',
       a_low['scope'] != a_high['scope'] and a_low['temp'] != a_high['temp']
       and a_low['lic'] != a_high['lic'], '')

    s_low, s_high = pair(0.5, 0.0), pair(0.5, 0.9)
    a_keys = ('scope', 'stage', 'temp', 'lic')
    bad2 = [f'{k}:{s_low[k]}→{s_high[k]}' for k in a_keys if s_low[k] != s_high[k]]
    ok('C2 ★★★ **只动文笔规训时，任务那四项一个字都不变**（反方向同样要成立）',
       not bad2, ' / '.join(bad2) or '全同')
    ok('C2b ★★★ 成对：而文笔那几项**确实变了**',
       s_low['deai'] != s_high['deai'] and s_low['dist'] != s_high['dist']
       and s_low['tic'] != s_high['tic'], '')


# ══════════════════════════════════════════════════════════════
#  D. 生产路径：真跑 decide，看真发出去的 prompt（四象限）
# [EN] D. Production path: run decide, inspect the prompt actually sent
# ══════════════════════════════════════════════════════════════
class _DB:
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


class _DS:
    # ⚠ 故事必须够长（> 200 字），否则 agenda 档的 160 字上限压不到它 ⇒ 三档一样。
    # [EN] The story must be long enough (> 200 chars) or the agenda cap cannot bite.
    story = (
        '驹子夜里醉着来找岛村，两人隔着一炉火说话。她把纸门拉开一半，雪光一下子照进来，'
        '落在榻榻米上，也落在她散开的头发上。岛村没有起身，只是把手里的杯子放下，'
        '看着她一步一步走过来，在火钵边上坐下，膝盖几乎碰到他的膝盖。'
        '叶子在廊下来回走了两趟，脚步声很轻，像怕惊动屋里的人；谁也没有提那个躺在'
        '后面房间里的病人，谁也没有提明天。驹子说她今天陪了客，喝得有点多，'
        '说这话的时候她笑了一下，那个笑很快就没了。岛村问她冷不冷，她说不冷，'
        '又说过一会儿就冷了。窗外的雪一直在下，没有一点要停的意思。'
    )
    roles = {'主角': ['把话问清楚']}


def _prompt(task: float, style: float) -> tuple[str, float]:
    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    r = _at(task=task, style=style)
    real = AC.llm.chat
    got: list[tuple[str, object]] = []

    async def spy(tier, messages, **kw):
        got.append((messages[-1]['content'] if messages else '', kw.get('temperature')))
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '判据'}, ensure_ascii=False), {})

    try:
        w = WorldState()
        w.scene = '温泉旅馆'
        w.clock = GameTime()
        w.day_script = _DS()
        w.narrative_distance = '贴近'
        w.people['主角'] = PersonState(name='主角', identity='客人', location='温泉旅馆',
                                       catchphrase='你这个人哪', current_goal='把话问清楚')
        w.people['驹子'] = PersonState(name='驹子', identity='艺伎', location='温泉旅馆')
        w.note_line('主角', '你这个人哪，别敲了', kind='speak')
        a = Agent(w.people['主角'], _DB(), w)
        AC.llm.chat = spy
        asyncio.run(a.decide())
    finally:
        AC.llm.chat = real
        r()
    return (str(got[0][0]), float(got[0][1] or -1.0)) if got else ('', -1.0)


def group_d() -> None:
    p00, t00 = _prompt(0.0, 0.0)
    p09, _ = _prompt(0.0, 0.9)
    p90, t90 = _prompt(0.9, 0.0)
    p99, _ = _prompt(0.9, 0.9)

    ok('D1 ★★ 四象限都真抓到 prompt（没抓到的话下面几条全是空的）',
       all(len(p) > 1500 for p in (p00, p09, p90, p99)),
       f'{[len(p) for p in (p00, p09, p90, p99)]}')

    ok('D2 ★★★ 任务低：prompt 里有 `[今日剧本]` 全文',
       '[今日剧本]' in p00 and '驹子夜里醉着' in p00, '')
    ok('D3 ★★★ 任务高：**连局面都不给**（只有"今天打算推进的事"，也没有分拍表）',
       '[今日剧本]' not in p90 and '[今天要办的事]' not in p90
       and '[你今天打算推进的事]' in p90, '')
    ok('D4 ★★★ 温度**真的传到了调用上**（不是只在 `freedom.py` 里算）',
       abs(t00 - 0.55) < 0.02 and abs(t90 - 0.91) < 0.03, f'{t00:.2f} / {t90:.2f}')

    ok('D5 ★★★ 文笔松：**距离档不见了**、**口癖配额不见了**、**文笔许可出现了**',
       '[这一拍的距离' not in p09 and '这一场已经用了' not in p09
       and '可以不那么整齐' in p09, '')
    ok('D6 ★★★ 文笔严：距离档在、口癖配额在、文笔许可**不在**',
       '[这一拍的距离' in p00 and '这一场已经用了' in p00
       and '可以不那么整齐' not in p00, '')

    i_lic = p99.find('[没人替你决定这一拍]')
    later = re.findall(r'\n\[[^\]\n]{2,24}\]', p99[i_lic:]) if i_lic >= 0 else []
    ok('D7 ★★★ 任务许可**排在最后一块**（它在说"上面那些不是台词提示"，'
       '后面再跟一块就自相矛盾）',
       i_lic > 0 and not later, f'许可@{i_lic} 之后还有 {later[:3]}')


# ══════════════════════════════════════════════════════════════
#  E. ★★★ 成对：说话人隔离**两个旋钮都碰不到**
# [EN] E. ★★★ Paired: speaker isolation is untouchable by both knobs
# ══════════════════════════════════════════════════════════════
def group_e() -> None:
    """四个象限里，三块规则各出现**恰好一次**。

    ★★★ 为什么这是最要紧的一条：把"自由度"实现成"少挂几条规则"是最省事的写法，
      而它做出的是**更差的文字**（不是更自由的人物）。E 组就是拦这个的。
    [EN] ★★★ The most important check: implementing "freedom" as "attach fewer rules" is easy
    [EN] and yields **worse prose**, not freer characters. E blocks exactly that.
    """
    probe = {
        # ⚠ 指纹必须是**整行**：`不是旁白` 这四个字在输出格式说明里还有一处
        #   （"`内心` 必须是你自己的心里话（第一人称），不是旁白"）⇒
        #   判"恰好一次"会恒红。用带破折号的那一整行才唯一。
        # [EN] The fingerprint must be the **whole line**: `不是旁白` also appears in the
        # [EN] output-format note, so "exactly once" would always be red.
        '说话人隔离（世界法则）': '你是**一个人**，不是旁白',
        '去 AI 清单': '别写成 AI 腔',
        '思维链骨架': '开口之前，先在心里按顺序过一遍',
    }
    for i, (tag, (task, style)) in enumerate((('双低', (0.0, 0.0)), ('任务高', (0.9, 0.0)),
                                              ('文笔高', (0.0, 0.9)), ('双高', (0.9, 0.9)))):
        p, _t = _prompt(task, style)
        bad = {k: p.count(v) for k, v in probe.items() if p.count(v) != 1}
        ok(f'E{1 + i} ★★★ {tag}：三块规则**各出现恰好一次**（0 = 掉了，2 = 重复烧钱）',
           not bad, str(bad) if bad else '各 1 次')

    p_hi, _ = _prompt(0.5, 0.9)
    p_lo, _ = _prompt(0.5, 0.0)

    def _n_questions(p: str) -> int:
        i = p.find('开口之前')
        return len(re.findall(r'\n\d+\. ', p[i:i + 900])) if i >= 0 else 0

    ok('E5 ★★★ 思维链在松档**精简但没消失**（精简 ≠ 删掉：完全不挂时决策退化成关键词反应）',
       _n_questions(p_hi) == 1 and _n_questions(p_lo) >= 4,
       f'严 {_n_questions(p_lo)} 问 / 松 {_n_questions(p_hi)} 问')


# ══════════════════════════════════════════════════════════════
#  F. 配置、环境、只此一处
# [EN] F. Config, env, one implementation
# ══════════════════════════════════════════════════════════════
def group_f() -> None:
    cfg = _read('config.py')
    core = _read('agent/core.py')

    ok('F1 ★★ 两个旋钮都在配置里（用户能自己调，而不是改代码）',
       '"TASK_FREEDOM"' in cfg and '"STYLE_FREEDOM"' in cfg, '')
    ok('F2 ★★★ 旧键 `AGENT_FREEDOM` **已经删掉**（留着就是"假旋钮"：'
       '界面上调它什么都不变，而用户会以为调到了）',
       '"AGENT_FREEDOM"' not in cfg, '')
    ok('F3 ★★ 两个默认值都是 50（中间档）',
       bool(re.search(r'"TASK_FREEDOM":\s*dict\([^)]*default=50', cfg))
       and bool(re.search(r'"STYLE_FREEDOM":\s*dict\([^)]*default=50', cfg)), '')

    ok('F4 ★★★ 档位判定**只有一处实现**（`agent/freedom.py`），'
       '演员提示词只调用它，不自己读配置再判一遍',
       'from agent import freedom' in core
       and "CFG.i('TASK_FREEDOM')" not in core
       and "CFG.i('STYLE_FREEDOM')" not in core, '')

    ok('F5 ★★★ 决策温度**不再写死**（`temperature=0.7` 那种硬编码已经不在了）',
       'purpose="agent_decide"' in core
       and re.search(r'purpose="agent_decide",\s*\n?\s*json_mode=True, temperature=0\.\d',
                     core) is None, '')

    env = _read('.env')
    ok('F6 ★★ `.env` 里两项都有（缺了的话界面上改了也存不住）',
       'TASK_FREEDOM' in env and 'STYLE_FREEDOM' in env, '')


def main() -> int:
    print('═' * 62)
    print('  自由度验证 · 任务规训与文笔规训是两个旋钮')
    print('═' * 62)
    print('\n【A】任务规训三档')
    group_a()
    print('\n【B】文笔规训三档')
    group_b()
    print('\n【C】★★★ 正交性（拆分的全部意义）')
    group_c()
    print('\n【D】生产路径（真跑 decide，四象限）')
    group_d()
    print('\n【E】★★★ 成对：说话人隔离两个旋钮都碰不到')
    group_e()
    print('\n【F】配置、环境、只此一处')
    group_f()
    print()
    print('═' * 62)
    print(f'自由度验证：{_n - _bad}/{_n} 通过')
    print('═' * 62)
    return 0 if _bad == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
