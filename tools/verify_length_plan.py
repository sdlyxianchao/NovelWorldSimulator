# -*- coding: utf-8 -*-
"""验证：**每个地点几章 / 全书多少字**能在设定集里定，而且真的生效（2026-10-27 用户点名）。

用户原话：
  「第一步是会切换好几个地方 但是我希望每个地方至少有若干章节
    整体故事需要在一定数量的字数 **这个我可以在设定集里设定吗？**」

★ 答：以前**不能**。那时只有
    · `篇幅`（详/中/略/带过）—— 管的是**一天写多厚**（拍预算，**一天**的口径）；
    · `ROUND_DAILY_WORDS` —— 管的是**每天**写多少字，且是**全局**配置、默认 0（不限）。
  "这一站占几章"根本没有字段，"全书多少字"也没有任何地方接得住
  （作者写在大纲里的「全书 8 万字」会被当散文读掉）。

  现在加两处设定，本判据守它们：
    ① 进度节点上的 `章数`（这一站至少几章）→ **判据满足了也不许提前过站**；
    ② 大纲里的「篇幅规划」（总章数 / 总字数 / 每章字数）→ 换算成每天的目标字数。

★ 量的是**行为**，不是"配置项存在"：
  · 章数下限 —— 真跑 `RunLoop._check_progress()`，看它在"判据已成"时**到底推不推进**；
  · 篇幅规划 —— 真走 `sim.setup.load_settings()` + `build_world()`，看 `world.daily_words`
    是不是**从这本书的设定里算出来的**（而不是被全局配置压住）。
  ⚠ "字段在 yaml 里"最容易自欺：装配时漏搬一次就全废（本项目 2026-10-26 刚栽过），
    所以 E/F 两组专测"搬运"。

English:
Verification: **how many chapters per place / how many words for the whole book** can be set in
the setting collection, and really take effect (user asked for this, 2026-10-27).

User's words: "part one switches between several places, but I want each place to have at least
a few chapters, and the whole story needs a certain word count -- **can I set that in the
setting collection?**"

★ Answer: **no**, not before. There was only `篇幅` (how thickly a *single day* is written, a
beat budget) and `ROUND_DAILY_WORDS` (a *per-day*, *global* target defaulting to 0 = unlimited).
"How many chapters this station occupies" had no field at all, and "how many words for the book"
landed nowhere (an outline saying "80,000 words" was read as prose).

Two settings now exist, and this guards them: ① `章数` on a progress node (minimum chapters for
that station -> **no advancing early even when the criterion is met**); ② a 「篇幅规划」 block in
the outline (total chapters / total words / words per chapter -> a per-day word target).

★ It measures **behaviour**, not "the field exists": the minimum is checked by really running
`RunLoop._check_progress()` and seeing whether it advances; the length plan by really going
through `sim.setup.load_settings()` + `build_world()`. ⚠ "The field is in the yaml" is the
easiest self-deception -- one dropped field at assembly kills it all (this project was bitten on
2026-10-26), so groups E/F exist purely to test **carrying**.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from ingest import progress as PR                 # noqa: E402

REPORT: list[dict] = []


def rec(name: str, ok_: bool, detail: str = '') -> bool:
    REPORT.append({'name': name, 'ok': bool(ok_), 'detail': detail})
    print(f"  {'✓' if ok_ else '✗'} {name}"
          + (f'  | {detail}' if detail else ''), flush=True)
    return bool(ok_)


# ══════════════════════════════════════════════════════════════════
#  【A】作者写的「章数」怎么认
# [EN] 【A】How the author's chapter count is parsed
# ══════════════════════════════════════════════════════════════════
def group_a() -> None:
    print('\n【A】作者写的「章数」—— 写法要认得全，认不出必须当"没写"', flush=True)
    p = PR._parse_chapters
    rec('A1 正整数 / 字符串数字 / 中文数字 / 区间都认',
        (p(3), p('3'), p('三'), p('3~4'), p('3-4'), p('3到4')) == (3, 3, 3, 3, 3, 3),
        f"{p(3)},{p('3')},{p('三')},{p('3~4')},{p('3-4')},{p('3到4')}")
    rec('A2 ★★★ 区间取**下限**（"3~4 章" = 至少 3 章，取上限会让每站都演满）',
        p('3~4') == 3, str(p('3~4')))
    rec('A3 ★★★ 认不出 / 负数 / 超出上限 → **0（没写）**，绝不静默当成 1',
        (p(''), p(None), p('好多章'), p(0), p(-2), p(30)) == (0, 0, 0, 0, 0, 0),
        f"空={p('')} None={p(None)} 好多章={p('好多章')} 0={p(0)} -2={p(-2)} 30={p(30)}")
    rec('A4 布尔不当数字（`True` 不是 1 章）', p(True) == 0 and p(False) == 0,
        f'{p(True)},{p(False)}')
    rec('A5 浮点（YAML 可能解出 3.0）也认', p(3.0) == 3, str(p(3.0)))


# ══════════════════════════════════════════════════════════════════
#  【B】这一站到底要几章（`min_chapters_for`）
# [EN] 【B】How many chapters this station needs
# ══════════════════════════════════════════════════════════════════
def group_b() -> None:
    print('\n【B】这一站要几章 —— 作者写的永远优先，没写按篇幅档兜底', flush=True)
    m = PR.min_chapters_for
    rec('B1 ★★★ 作者写的**压过**篇幅档（详 兜底 4，作者写 6 ⇒ 6）',
        m({'篇幅': '详', '章数': 6}) == 6, str(m({'篇幅': '详', '章数': 6})))
    rec('B2 作者写的可以**比兜底更少**（详 兜底 4，作者写 2 ⇒ 2）'
        '—— 兜底只是"没写时"的猜测，不能反过来压作者',
        m({'篇幅': '详', '章数': 2}) == 2, str(m({'篇幅': '详', '章数': 2})))
    rec('B3 没写 ⇒ 按篇幅档（详4 / 中3 / 略2 / 带过1）',
        (m({'篇幅': '详'}), m({'篇幅': '中'}), m({'篇幅': '略'}),
         m({'篇幅': '带过'})) == (4, 3, 2, 1),
        f"{m({'篇幅':'详'})},{m({'篇幅':'中'})},{m({'篇幅':'略'})},{m({'篇幅':'带过'})}")
    rec('B4 ★★★ `略` 兜底是 **2** 不是 1：'
        '「略」的意思是"别细写"，不是"跳过去"，判据一成当天就走等于这一站没写',
        m({'篇幅': '略'}) >= 2, str(m({'篇幅': '略'})))
    rec('B5 篇幅也没定 ⇒ 按默认档（`中` ⇒ 3）',
        m({}) == 3 and m({'篇幅': '不知道什么档'}) == 3,
        f"{m({})},{m({'篇幅':'不知道什么档'})}")
    rec('B6 ★★★ 返回值**恒 >= 1**（0 会让"演 0 章就过站"变成可能）',
        all(m({'篇幅': w}) >= 1 for w in PR.WEIGHTS)
        and all(m({'篇幅': w, '章数': 0}) >= 1 for w in PR.WEIGHTS),
        str([m({'篇幅': w}) for w in PR.WEIGHTS]))
    rec('B7 ⚠ 三种形状都要认（`dict` / `ProgressNode` / 裸篇幅字符串）'
        '—— 只认一种曾让篇幅档对拍数完全失效',
        (m({'篇幅': '详'}), m(PR.ProgressNode('N1', 'a', 's', 'c', weight='详')),
         m('详')) == (4, 4, 4),
        f"{m({'篇幅':'详'})},{m(PR.ProgressNode('N1','a','s','c',weight='详'))},{m('详')}")


# ══════════════════════════════════════════════════════════════════
#  【C】书级「篇幅规划」
# [EN] 【C】The book-level length plan
# ══════════════════════════════════════════════════════════════════
def group_c() -> None:
    print('\n【C】大纲里的「篇幅规划」—— 全书几章 / 多少字', flush=True)
    plan = PR.parse_length_plan(
        '## 篇幅规划\n- 总章数: 32\n- 总字数: 7.5万字\n- 每章字数: 2400\n')
    rec('C1 三个字段都读得到（`7.5万字` 要认成 75000）',
        plan == {'总章数': 32, '总字数': 75000, '每章字数': 2400}, str(plan))
    rec('C2b ★★★ **加粗也要认**（`- **总章数**：32`）—— 作者写大纲时几乎一定加粗，'
        '而"写了却读不到"是最难发现的静默失效（第一版只认不加粗的，栽在这里）',
        PR.parse_length_plan('- **总章数**：32\n- **总字数**：7.5万字\n')
        == {'总章数': 32, '总字数': 75000, '每章字数': 0},
        str(PR.parse_length_plan('- **总章数**：32\n- **总字数**：7.5万字\n')))
    rec('C2 中文冒号 / 纯数字 / 英文键也认',
        PR.parse_length_plan('- 总章数：32\n- 总字数：75000\n')['总字数'] == 75000
        and PR.parse_length_plan('## Length plan\n- Total chapters: 30\n'
                                 '- Total words: 80,000\n')['总字数'] == 80000,
        str(PR.parse_length_plan('## Length plan\n- Total chapters: 30\n'
                                 '- Total words: 80,000\n')))
    _prose = ('## 分站\n'
              '- 第一站：开头（参考：原著全书字数约 300000，这里不照搬）\n')
    rec('C3 ★★★ **散文里的字数不算**（括号里"原著全书字数约 300000"是在形容原著，'
        '不是给程序下命令）',
        PR.parse_length_plan(_prose) == {'总章数': 0, '总字数': 0, '每章字数': 0},
        str(PR.parse_length_plan(_prose)))
    rec('C4 什么都没写 ⇒ 全 0（**不抛、不猜**）',
        PR.parse_length_plan('') == {'总章数': 0, '总字数': 0, '每章字数': 0}
        and PR.parse_length_plan('# 大纲\n- 第一站\n')['总章数'] == 0, '全 0')

    w = PR.words_per_chapter
    rec('C5 每章字数：作者直接写了就用他的',
        w({'每章字数': 2400, '总字数': 75000, '总章数': 32}) == 2400,
        str(w({'每章字数': 2400, '总字数': 75000, '总章数': 32})))
    rec('C6 ★★★ 只给了总字数与总章数 ⇒ **相除**（8 万 ÷ 32 = 2500）',
        w({'总字数': 80000, '总章数': 32}) == 2500,
        str(w({'总字数': 80000, '总章数': 32})))
    rec('C7 都没有 ⇒ **0（不限）**，绝不凭空造一个数',
        w({}) == 0 and w(None) == 0 and w({'总字数': 80000}) == 0,
        f"{w({})},{w(None)},{w({'总字数':80000})}")
    rec('C8 ⚠ 相除结果**保底 300**（一章 300 字以下是段笔记，不是章）',
        w({'总字数': 500, '总章数': 32}) >= 300,
        str(w({'总字数': 500, '总章数': 32})))


# ══════════════════════════════════════════════════════════════════
#  【D】写盘：只写作者真填过的
# [EN] 【D】Persisting: only what the author actually filled in
# ══════════════════════════════════════════════════════════════════
def group_d() -> None:
    print('\n【D】落盘的 yaml —— 兜底值不许假装是作者写的', flush=True)
    written = PR.ProgressNode('N01', '甲站', '概要', '判据', weight='详',
                              chapters=5).to_dict()
    empty = PR.ProgressNode('N02', '乙站', '概要', '判据', weight='详').to_dict()
    rec('D1 作者写了 `章数` ⇒ 落盘里有它',
        written.get('章数') == 5, str(written))
    rec('D2 ★★★ 作者**没写** ⇒ 落盘里**没有这个键**'
        '（兜底由 `min_chapters_for` 现算；写进去会让作者以为自己写过）',
        '章数' not in empty, str(empty))
    rec('D3 篇幅照旧落盘（没被这一轮改坏）',
        empty.get('篇幅') == '详' and written.get('篇幅') == '详', str(empty))


# ══════════════════════════════════════════════════════════════════
#  【E】装配：**字段必须搬**（2026-10-26 栽过的坑）
# [EN] 【E】Assembly: the fields must be **carried**
# ══════════════════════════════════════════════════════════════════
def group_e(tmp: Path) -> None:
    print('\n【E】装配：yaml 里写了 ⇒ 运行时必须读得到（漏搬 = 静默失效）', flush=True)
    import yaml
    d = tmp / '设定集'
    d.mkdir(parents=True, exist_ok=True)
    (d / '故事进度.yaml').write_text(yaml.dump(
        {'节点': [{'id': 'N01', '名称': '甲站', '概要': 's', '完成判据': 'c',
                   '状态': '进行中', '跨度': '数日', '篇幅': '详', '章数': 6}],
         '篇幅规划': {'总章数': 32, '总字数': 80000}},
        allow_unicode=True, default_flow_style=False), encoding='utf-8')

    from sim import setup as SU
    st = SU.load_settings(d)
    node = (st.get('nodes') or [{}])[0]
    rec('E1 ★★★ `章数` 搬进来了（漏搬 ⇒ 运行时永远读不到，'
        '而 `min_chapters_for` 有兜底 ⇒ 两条路都能跑、只是永远不生效）',
        int(node.get('章数') or 0) == 6, str(node))
    rec('E2 `篇幅 / 跨度` 照旧搬进来（没被挤掉）',
        node.get('篇幅') == '详' and node.get('跨度') == '数日', str(node))
    rec('E3 ★★★ `篇幅规划` 也搬进来了',
        int((st.get('length_plan') or {}).get('总字数') or 0) == 80000,
        str(st.get('length_plan')))


# ══════════════════════════════════════════════════════════════════
#  【F】每天目标字数：**这本书的设定**压过全局配置
# [EN] 【F】Per-day word target: this book's setting outranks the global config
# ══════════════════════════════════════════════════════════════════
def group_f(tmp: Path) -> None:
    print('\n【F】每天写多少字 = 设定集里算出来的（不是被全局配置压住）', flush=True)
    import yaml
    from sim import setup as SU

    def build(plan: dict | None, global_words: int):
        d = tmp / f'设定集_{id(plan)}_{global_words}'
        d.mkdir(parents=True, exist_ok=True)
        nodes = {'节点': [{'id': 'N01', '名称': '甲站', '概要': 's',
                           '完成判据': 'c', '状态': '未开始', '篇幅': '中'}]}
        if plan:
            nodes['篇幅规划'] = plan
        (d / '故事进度.yaml').write_text(
            yaml.dump(nodes, allow_unicode=True, default_flow_style=False),
            encoding='utf-8')
        (d / '世界观.md').write_text('一个茶楼。', encoding='utf-8')
        (d / '人物卡.yaml').write_text(
            yaml.dump([{'姓名': '甲', '身份': '伙计', '简介': '忘了来处'}],
                      allow_unicode=True), encoding='utf-8')
        (d / '地点.yaml').write_text(
            yaml.dump([{'名称': '茶楼', '说明': '两层木楼'}], allow_unicode=True),
            encoding='utf-8')
        from config import CFG
        cfg = CFG
        old = cfg.i('ROUND_DAILY_WORDS')
        try:
            cfg.set('ROUND_DAILY_WORDS', str(global_words))
            st = SU.load_settings(d)
            w = SU.build_world(st)
        finally:
            cfg.set('ROUND_DAILY_WORDS', str(old))
        return w

    w1 = build({'总章数': 32, '总字数': 80000}, 0)
    rec('F1 ★★★ 全局为 0（不限）时 ⇒ 从设定集算出 80000÷32 = 2500',
        int(getattr(w1, 'daily_words', 0)) == 2500,
        str(getattr(w1, 'daily_words', 0)))
    w2 = build({'每章字数': 1800}, 0)
    rec('F2 作者直接写「每章字数」⇒ 用它（不与总字数相除）',
        int(getattr(w2, 'daily_words', 0)) == 1800,
        str(getattr(w2, 'daily_words', 0)))
    w3 = build({'总章数': 32, '总字数': 80000}, 3000)
    rec('F3 ★★★ 作者在「起笔」里手填了 ⇒ **手填的赢**（设定集不该反过来压人）',
        int(getattr(w3, 'daily_words', 0)) == 3000,
        str(getattr(w3, 'daily_words', 0)))
    w4 = build(None, 0)
    rec('F4 两边都没写 ⇒ 0（不限），沿用老规矩',
        int(getattr(w4, 'daily_words', 0)) == 0,
        str(getattr(w4, 'daily_words', 0)))


# ══════════════════════════════════════════════════════════════════
#  【G】过站闸门：判据成了但章数没到 ⇒ **不许往前走**
# [EN] 【G】The advance gate: criterion met but chapters short -> do not advance
# ══════════════════════════════════════════════════════════════════
class _V:
    def __init__(self, done: bool, desc: str = '事成了'):
        self.ok, self.done, self.desc = True, done, desc


class _W:
    """只提供闸门用到的那几个字段。
    [EN] Only the fields the gate uses."""
    def __init__(self, node: dict):
        self.current_node = str(node.get('id') or '')
        self.progress_nodes = [node]
        self.progress_note = ''

    def current_node_info(self) -> dict:
        for n in self.progress_nodes:
            if str(n.get('id') or '') == self.current_node:
                return n
        return {}


class _DB:
    """`_check_progress` 要读最近几条事件（用来算"这次评估和上次是不是同一批事实"）。
    [EN] `_check_progress` reads the most recent events (to tell whether this evaluation is about
    the same facts as the last one)."""

    def __init__(self, events):
        self._e = events

    def recent_events(self, n=5, **_kw):
        return list(self._e)[-int(n or 5):]


class _D:
    def __init__(self, verdict, world):
        self._v, self._w = verdict, world
        self.advanced = False

    async def evaluate_progress(self, _events):
        return self._v

    def advance_node(self):
        self.advanced = True
        return 'N02'

    def is_at_end(self):
        return False


def _mk_loop(node: dict, days: int):
    from sim.loop import RunLoop
    lp = RunLoop.__new__(RunLoop)          # 绕过 __init__（与 verify_branch 同一招）
    lp.world = _W(node)
    lp.db = _DB([{'id': 'e1', 'content': '发生了件事'}])
    lp.director = _D(_V(True), lp.world)
    lp._progress_sig = None
    lp._progress_fail_streak = 0
    lp._node_days = max(0, days - 1)
    lp._node_days_id = str(node.get('id') or '')
    lp._hold_note_day = -1
    lp._branch_pending = False
    lp._on_status = None                   # `_status()` 会读它（不广播就什么都不做）
    lp.said = []

    def _push(text, *_a, **_k):
        lp.said.append(text)
    lp._push_narrative = _push
    return lp


def group_g() -> None:
    print('\n【G】过站闸门：判据成了、章数没到 ⇒ **先不往前走**', flush=True)
    node = {'id': 'N01', '名称': '甲站', '概要': 's', '完成判据': 'c',
            '状态': '进行中', '篇幅': '详', '章数': 4}

    lp1 = _mk_loop(node, days=1)
    r1 = asyncio.run(lp1._check_progress())
    rec('G1 ★★★ 第 1 章判据就成 ⇒ **不推进**（导演不 advance）',
        (not r1) and (not lp1.director.advanced), f'返回={r1} 推进={lp1.director.advanced}')

    lp2 = _mk_loop(node, days=4)
    r2 = asyncio.run(lp2._check_progress())
    rec('G2 演到第 4 章（= 作者要的 4 章）⇒ **放行**',
        r2 or lp2.director.advanced, f'返回={r2} 推进={lp2.director.advanced}')

    lp3 = _mk_loop(node, days=1)
    asyncio.run(lp3._check_progress())
    rec('G3 ★★★ 卡住时**说了人话、并且说了接着写什么**'
        '（只卡住不给活干 ⇒ 导演拿一个已成判据反复派活 = 空转）',
        any(('余波' in s and '4' in s) for s in lp3.said), str(lp3.said[:1]))

    lp4 = _mk_loop(node, days=1)
    asyncio.run(lp4._check_progress())
    n1 = len(lp4.said)
    asyncio.run(lp4._check_progress())
    rec('G4 同一章里**只提醒一次**（每次评估都重复会把正文冲淡）',
        len(lp4.said) == n1, f'{n1} → {len(lp4.said)}')

    lp5 = _mk_loop(node, days=6)           # 6 > 4（演超了）
    r5 = asyncio.run(lp5._check_progress())
    rec('G5 ★★ 演**超**了（6 章 > 要 4 章）⇒ 也要放行'
        '（判的是"够不够"，不是"等不等于"；写成 `!=` 会让演超的站永远走不掉）',
        r5 or lp5.director.advanced, f'返回={r5} 推进={lp5.director.advanced}')

    # 计数本身（换站归 1、含"今天"）
    lp6 = _mk_loop(node, days=1)
    rec('G6 `_days_in_node()` **含今天**（日界只在下一天开始时才 +1）',
        lp6._days_in_node() == 1, str(lp6._days_in_node()))
    lp6.world.current_node = 'N01'
    lp6._count_node_day()                  # 同一站，跨到第二天
    rec('G7 同一站再过一天 ⇒ 2',
        lp6._days_in_node() == 2, str(lp6._days_in_node()))
    lp6.world.current_node = 'N02'         # 换站（还没跨日界）
    rec('G8 ★★★ 换站、还没跨日界 ⇒ **1**（新站的第一天就是它的第 1 章）',
        lp6._days_in_node() == 1, str(lp6._days_in_node()))
    lp6._count_node_day()                  # 换站之后过了第一个日界
    rec('G8b ★★★ 换站后跨了第一个日界 ⇒ **仍是 1**'
        '（"跨过的日界数"归 0，今天才是第 1 章；归 1 会让新站一上来就算 2 章）',
        lp6._days_in_node() == 1, str(lp6._days_in_node()))

    # 反面：作者没写章数、篇幅=带过 ⇒ 1 章就放行（不该被新闸门卡住）
    node2 = {'id': 'N01', '名称': '小站', '概要': 's', '完成判据': 'c',
             '状态': '进行中', '篇幅': '带过'}
    lp7 = _mk_loop(node2, days=1)
    r7 = asyncio.run(lp7._check_progress())
    rec('G9 反面：`带过` 的站（兜底 1 章）第 1 章就放行 —— 新闸门不许误伤',
        r7 or lp7.director.advanced, f'返回={r7} 推进={lp7.director.advanced}')


def group_h() -> None:
    print('\n【H】每章字数 → 这一天的拍数（实测 ≈550 字/拍；2026-10-30）', flush=True)
    from ingest import progress as PR
    from director import day_plan as DP

    rec('H1 ★★★ 换算系数在表里、且是**实测那个量级**'
        '（4,949 字 / 9 幕 ≈ 550；旧表按"一拍 76 字"定的，才差出 7 倍）',
        450 <= int(PR.CHARS_PER_BEAT) <= 650, str(PR.CHARS_PER_BEAT))
    rec('H2 ★★★ 2,500 字/章 ⇒ 4~5 拍 —— **不是**旧表的 15~25 拍'
        '（按旧表演就是 8,000~13,000 字，五章的体量，一天把一站写完）',
        4 <= PR.beats_for_words(2500) <= 5, str(PR.beats_for_words(2500)))
    rec('H3 没写（0 / 负数）⇒ 返回 **0**，由调用方判断'
        '（返回 1 会把"没写"悄悄变成"一天一拍"）',
        PR.beats_for_words(0) == 0 and PR.beats_for_words(-5) == 0,
        f'{PR.beats_for_words(0)},{PR.beats_for_words(-5)}')
    rec('H4 封顶 30 拍（误填"五万字一章"不许把一天拉成 90 拍）',
        PR.beats_for_words(10 ** 6) == PR.MAX_BEATS_BY_WORDS == 30,
        str(PR.beats_for_words(10 ** 6)))

    w = _W({'id': 'N01', '名称': '甲站', '状态': '进行中', '篇幅': '中'})
    w.daily_words = 0
    lo, hi, _ = DP.beat_budget_for(w, None)
    rec('H5 ★★ 没写每章字数 ⇒ **原表一动不动**（15~25）',
        (lo, hi) == (15, 25), f'{lo},{hi}')
    w.daily_words = 2500
    lo, hi, why = DP.beat_budget_for(w, None)
    rec('H6 ★★★ 写了 2,500 字/章 ⇒ 上限压到 5 拍、下限也收到 5'
        '（只压上限不压下限的话，"中"的 15 拍起跳又把一天撑成 8,000 字）',
        hi == 5 and lo <= 5, f'{lo},{hi} / {why}')
    w.daily_words = 20000
    lo, hi, _ = DP.beat_budget_for(w, None)
    rec('H7 ★★ 字数写得比原表还厚 ⇒ **不抬**上限（cap 只压不抬：25 拍照旧）',
        (lo, hi) == (15, 25), f'{lo},{hi}')

    w2 = _W({'id': 'N02', '名称': '乙站', '状态': '未开始', '篇幅': '详'})
    w2.current_node = ''
    w2.daily_words = 2500
    lo2, hi2, why2 = DP.beat_budget_for(w2, None)
    rec('H8 ★★★ **没有正在推进的节点**那几天也要封顶'
        '（早退一次就绕过字数目标，而且只在"两站之间"那几天偏厚，最难发现）',
        hi2 == 5, f'{lo2},{hi2} / {why2}')

    # ★★★ 2026-10-30：**字数目标不许把篇幅档抹平**。
    #   只按"字数 ÷ 550"封顶的话，详/中/略 在 2,500 字下算出来都是 5 拍 ——
    #   作者在节点上写的 `篇幅` 就静默失效了（本项目反复栽的那个坑）。
    def _hi_for(weight: str) -> int:
        ww = _W({'id': 'N03', '名称': '丙站', '状态': '进行中', '篇幅': weight})
        ww.daily_words = 2500
        return DP.beat_budget_for(ww, None)[1]

    _x = {'详': _hi_for('详'), '中': _hi_for('中'), '略': _hi_for('略')}
    rec('H9 ★★★ 同样 2,500 字/章 ⇒ **详 > 中 > 略**（详 ×1.4 / 略 ×0.6）'
        '—— 只按字数换算的话三者一模一样，篇幅档就永远不生效了',
        _x['详'] > _x['中'] > _x['略'], str(_x))
    rec('H9b `带过` 仍然 1 拍（一句话交代过去，字数目标也不许把它撑厚）',
        DP.beat_budget_for(
            type('W', (), {'progress_nodes': [{'id': 'N4', '状态': '进行中',
                                               '篇幅': '带过'}],
                           'current_node': '', 'daily_words': 2500})(), None)[1] == 1,
        '')


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_len_'))
    try:
        group_a()
        group_b()
        group_c()
        group_d()
        group_e(tmp)
        group_f(tmp)
        group_g()
        group_h()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [c for c in REPORT if not c['ok']]
    print('\n' + '─' * 62)
    print(f'  篇幅规划验证：{len(REPORT) - len(bad)}/{len(REPORT)}'
          + ('' if not bad else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
