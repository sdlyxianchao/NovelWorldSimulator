# -*- coding: utf-8 -*-
"""验证：**写作层按情节单元写**（详的写足、略的一句带过）。

用户 2026-10-26：
  「真正小说里并不一定每天都有故事 而是根据大纲 可能会快速跳过很多时间
    每隔一段时间才会有1个事件集中描写 …… 小说时间不是匀速流逝的」
  「这个不止改这里，小说写作、框架搭建、情节设定都要优化」
  「注意 一个事件可能跨天」

改之前：`Novelist._transcribe` **按 6000 字机械切块**，每一块都要求
"写完整、事件一处都不许漏" ⇒ 21.3 万字材料被**等密度**转写成 12.9 万字 ——
**赶路那三个月和开庭那一场一样厚**，读起来是"逐块转录剧本"。

这一层（`crew/unit_plan.py`）把"按字数切"换成"按**情节单元**切"，
并把篇幅档翻成**可数**的写作目标（段数/句数，不是字数 —— 模型不数字数）。

判据分组：
  A 切分（纯函数）：按幕头里的站名切；同站连演算一个、分两段演算两个；
    **没标站名 ⇒ 退化成一个单元**（旧行为，不许因此写坏）
  B 篇幅 → 目标：详 > 中 > 略 > 带过单调；略/带过**不看材料量**；
    给模型的是**可数单位**；推断出来的要照实标注
  C 打包：相邻轻站合成一次"掠过"、轻站不被字数切碎、重站切开后目标不翻倍
  D 接线（行为）：目标真的进了提示词；轻站**不许**再出现"一处都不许跳过"；
    轻站写超了**按句末剪**、重站**绝不剪**
  E 反例（就地）：把三处关键实现各改坏一次，对应判据必须变红
    —— 不跑这一步，"判据会不会咬人"永远没被证明过

跑法：.venv\\Scripts\\python.exe tools/verify_writer_units.py
产出：assets/screenshots/writer_units_report.json

English:
Verify **writing by plot unit** (thick where it matters, one line where it does not).
Before: the organizer sliced material into mechanical 6000-character chunks and demanded
"write it in full, skip nothing", so 213k characters became 129k at uniform density.
Groups: A slicing (pure) / B length tier -> countable target / C packing into writing passes /
D wiring (behaviour) -- the target reaches the prompt, light passes lose "skip nothing" and get
trimmed at a sentence boundary while heavy passes never are / E counterexamples: break each key
implementation once and the matching criterion must go red.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from crew import unit_plan as UP                                 # noqa: E402
from crew.agents import Novelist, SetCtx                         # noqa: E402

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''), flush=True)
    return bool(cond)


# ── 夹具 ──────────────────────────────────────────────────────────────
NODES = [
    {'id': 'N01', '名称': '入楼收留', '概要': '街头醒来被收留', '篇幅': '详', '跨度': '当日'},
    {'id': 'N02', '名称': '重走旧路', '概要': '途中往来，一路过去', '篇幅': '略', '跨度': '数月'},
    {'id': 'N03', '名称': '开庭抉择', '概要': '当众摊牌', '篇幅': '中', '跨度': '一场'},
    {'id': 'N04', '名称': '途中', '概要': '一路过去', '篇幅': '带过', '跨度': '数月'},
]
_PAD = '· 环境 檐水一滴一滴落在石阶上，把青苔砸出一个个小坑。'


def act(i: int, station: str = '', chars: int = 900) -> list[str]:
    """一幕材料（与真实同形：幕头 + 动作/心声/对白/环境）。"""
    head = f'第 {i} 幕 · 子时 23:{(i % 60):02d} · 临街楼'
    if station:
        head += f' · {station}'
    out = [f'〔{head}〕',
           f'· 动作 甲：第{i}拍，抬手把壶盖掀开一条缝，看了眼里面的水。',
           '◇ 心声 甲：这话问出口就收不回来了。',
           '「茶凉了。」']
    out += ['· 环境 ' + _PAD.replace('· 环境 ', '')] * max(1, chars // 24)
    return out


def day(n: int, station: str = '', chars: int = 900, start: int = 1) -> list[str]:
    out: list[str] = []
    for i in range(start, start + n):
        out += act(i, station, chars)
    return out


# ══════════════════════════════════════════════════════════════════════
#  A —— 切分（纯函数）
# ══════════════════════════════════════════════════════════════════════
def a_slicing() -> None:
    print('\n── A 切分（按情节单元，不按字数）──')
    lines = day(4, '入楼收留') + day(3, '重走旧路', start=5) + day(2, '开庭抉择', start=8)
    units = UP.plan_units(lines, nodes=NODES, current='N01')
    ok('A1 ★★★ 幕头里的站名把材料切成**三个单元**（三站，按材料顺序）',
       [u.name for u in units] == ['入楼收留', '重走旧路', '开庭抉择'],
       str([u.name for u in units]))
    ok('A2 ★★★ 同一站连演几幕 ⇒ **一个**单元（不是每幕一个）',
       len(units) == 3 and units[0].acts == 4, f'{len(units)} 单元 / 第一站 {units[0].acts} 幕')

    # 同一站分两段演（中间去了别处又回来）⇒ 两个单元（**按出现顺序**，不按名字合并）
    back = day(2, '入楼收留') + day(2, '开庭抉择', start=3) + day(2, '入楼收留', start=5)
    u2 = UP.plan_units(back, nodes=NODES, current='N01')
    ok('A3 ★★★ 同一站**分两段演** ⇒ 算两个单元（按材料顺序切，按名字合并会把时间线搅乱）',
       [u.name for u in u2] == ['入楼收留', '开庭抉择', '入楼收留'],
       str([u.name for u in u2]))

    # 退化：材料没有幕头 / 幕头没有站名
    plain = ['· 动作 甲：擦桌。', '◇ 心声 甲：累。', '「走罢。」'] * 60
    u3 = UP.plan_units(plain, nodes=NODES, current='N03')
    ok('A4 ★★★ **没标站名 ⇒ 退化成一个单元**（旧行为；不许因为"分不出站"就把材料写坏）',
       len(u3) == 1 and u3[0].name == '', f'{len(u3)} 单元 / 名字={u3[0].name!r}')
    u4 = UP.plan_units(day(3, ''), nodes=NODES, current='N03')
    ok('A4b ★★★ 有幕头但**没写站名** ⇒ 也是一个单元（幕头本身仍要留着当时间轴）',
       len(u4) == 1 and u4[0].acts == 3, f'{len(u4)} 单元 / {u4[0].acts} 幕')

    # 幕头最后一个字段是**地点**而不是站名时，不许当站名
    fake = day(2, '临街楼')
    u5 = UP.plan_units(fake, nodes=NODES, current='N01')
    ok('A5 ★★ 幕头最后一字段是**地点**（不在进度表里）⇒ 不当站名（防止把地点当站）',
       len(u5) == 1 and u5[0].name == '', f'{len(u5)} 单元 / 名字={u5[0].name!r}')

    # ★★★ A5c：**转场标记 / 剧情节点行不是幕头**（2026-10-26 真数据踩到的坑）
    #   材料里还有 `〔切至 · 柜上长凳｜同一时刻〕` / `〔事件 · 伏笔激活〕` 这种方括号行，
    #   形状与幕头一模一样。只按 `〔…〕` 判，它们就成了"幕头"，最后一个字段是**地点+时刻**、
    #   匹配不上站名 ⇒ 每两幕切一刀 ⇒ 实测 133 幕炸成 **211 个单元 / 25.7 万字目标**。
    #   `第 N 幕` 是唯一判别特征。
    # [EN] ★★★ A5c: transition markers / plot-node lines are **not** act headers (found on real
    # [EN] data). Same bracket shape; judging by `〔…〕` alone turned them into headers whose last
    # [EN] field is a place+time, splitting every other act -- 133 acts became **211 units /
    # [EN] 257k characters of target**. `第 N 幕` is the only discriminating feature.
    mixed = []
    for i in range(1, 7):
        mixed += act(i, '入楼收留')
        mixed.append('〔切至 · 柜上长凳｜同一时刻〕')
        mixed.append('〔事件 · 伏笔激活〕')
    u6 = UP.plan_units(mixed, nodes=NODES, current='N01')
    ok('A5c ★★★ **转场标记 `〔切至 …〕` / 剧情节点 `〔事件 …〕` 不是幕头**'
       '（否则每两幕切一刀，单元与目标字数一起爆）',
       len(u6) == 1 and u6[0].acts == 6,
       f'{len(u6)} 单元 / {u6[0].acts} 幕（应为 1 单元 / 6 幕）')
    ok('A5d ★★★ 幕数**与 `_day_lines` 写的一致**（数幕头，不数方括号行）',
       UP.acts_of('\n'.join(mixed)) == 6, str(UP.acts_of('\n'.join(mixed))))

    # 一个字节都不改
    joined = '\n'.join(l for u in units for l in u.lines).strip()
    ok('A6 ★★★ 切分**不动材料**（把各单元拼回去 = 原文，一个字不差）',
       joined == '\n'.join(lines).strip(), f'{len(joined)} vs {len(chr(10).join(lines).strip())}')


# ══════════════════════════════════════════════════════════════════════
#  B —— 篇幅 → 目标
# ══════════════════════════════════════════════════════════════════════
def b_targets() -> None:
    print('\n── B 篇幅 → 可数的写作目标 ──')
    t = {w: UP.target_of(w, 6000) for w in ('详', '中', '略', '带过')}
    ok('B1 ★★★ **详 > 中 > 略 > 带过**（上限单调递减 —— 这一条就是"详略"本身）',
       t['详'].max_chars > t['中'].max_chars > t['略'].max_chars > t['带过'].max_chars,
       ' / '.join(f'{w}={t[w].max_chars}' for w in ('详', '中', '略', '带过')))

    # 略/带过 **不看材料量**：演了 30 幕的"略"站还是两句带过
    small = UP.target_of('略', 800)
    huge = UP.target_of('略', 60000)
    ok('B2 ★★★ 「略」**不看材料量**（8 千字和 6 万字都一样：两三句带过 —— '
       '那才是"快速跳过很多时间"）',
       (small.sent_lo, small.sent_hi) == (huge.sent_lo, huge.sent_hi),
       f'{small.sent_lo}~{small.sent_hi} vs {huge.sent_lo}~{huge.sent_hi}')

    # 详/中 跟材料量走，但有绝对下限（材料极短也写成一小段）
    ok('B3 ★★ 重档跟材料量走，但有**绝对下限**（材料再少也不许缩成两句）',
       UP.target_of('详', 100).max_chars >= 1000 and UP.target_of('中', 100).max_chars >= 500,
       f'详 {UP.target_of("详", 100).max_chars} / 中 {UP.target_of("中", 100).max_chars}')
    ok('B3b ★★ 也有**绝对上限**（一块写成 3000 字以上就是"写爆"，不再是"写足"）',
       UP.target_of('详', 60000).max_chars <= 3000, str(UP.target_of('详', 60000).max_chars))

    ok('B4 ★★★ 「带过」是 **1~2 句**，不是 0（0 句等于这一站不存在，读者不知道过了多久）',
       UP.target_of('带过', 0).sent_lo >= 1, str(UP.target_of('带过', 0)))

    # 给模型的必须是**可数单位**（段/句），不是字数
    blk = UP.density_block(UP.Unit(name='开庭', weight='详', lines=day(3, '开庭抉择')))
    ok('B5 ★★★ 重档给模型的是**段数**（"写 N 段"），不是字数 —— 实测模型不数字数',
       '段' in blk and '字' not in blk.replace('两百字以内', ''),
       blk.splitlines()[1][:60])

    # 推断出来的篇幅要照实标注
    n = {'id': 'N09', '名称': '途中赶路', '概要': '一路过去，转眼到了', '状态': '进行中'}
    u = UP.plan_units(day(2, '途中赶路'), nodes=[n], current='N09')[0]
    ok('B6 ★★★ 节点上没写篇幅 ⇒ **程序推一个**，并且**照实标注是推的**（不许冒充作者写的）',
       u.weight in ('略', '带过', '中') and u.inferred is True, f'篇幅={u.weight} 推的={u.inferred}')


# ══════════════════════════════════════════════════════════════════════
#  C —— 打包成写作次
# ══════════════════════════════════════════════════════════════════════
def c_packing() -> None:
    print('\n── C 打包成"写作次" ──')
    lines = (day(2, '重走旧路') + day(2, '途中', start=3) + day(2, '开庭抉择', start=5))
    units = UP.plan_units(lines, nodes=NODES, current='N02')
    groups = UP.pack(units, 6000)
    ok('C1 ★★★ 相邻的两个轻站合成**一次"掠过"**（三站各一句，正是"几个月过去了"的写法）',
       len(groups) == 2 and len(groups[0]) == 2 and groups[1][0].name == '开庭抉择',
       str([[u.name for u in g] for g in groups]))

    import crew.agents as A
    jobs = A._transcribe_jobs(units, 6000, UP)
    ok('C1b ★★★ 合成之后**模型只被叫两次**（省掉一次带全套提示词的调用）',
       len(jobs) == 2, f'{len(jobs)} 次：{[j["label"] for j in jobs]}')
    ok('C1c ★★★ "掠过"那一次的目标是**各站相加**（合成一句等于有两站没写）',
       jobs[0]['target'].sent_hi == (UP.target_of('略', 0).sent_hi
                                     + UP.target_of('带过', 0).sent_hi),
       f'{jobs[0]["target"].sent_lo}~{jobs[0]["target"].sent_hi} 句')

    # 轻站**不按字数切碎**（切了就是"每片两句"，反而写多）
    fat = UP.plan_units(day(8, '重走旧路', chars=1400), nodes=NODES, current='N02')
    jf = A._transcribe_jobs(fat, 6000, UP)
    ok('C2 ★★★ 轻站材料很长也**只写一次**（切成两片就变成"每片两句"，反而写多）',
       len(jf) == 1, f'{len(jf)} 次（材料 {len(fat[0].material())} 字）')

    # 重站材料超上限才切，且目标按**每一片**算（不是每片都按整站）
    big = UP.plan_units(day(24, '入楼收留', chars=1200), nodes=NODES, current='N01')
    jb = A._transcribe_jobs(big, 6000, UP)
    ok('C3 ★★★ 重站材料超上限 ⇒ **切成几片**（模型上下文保护），片数 > 1',
       len(jb) > 1, f'{len(jb)} 片 / 材料 {len(big[0].material())} 字')
    ok('C3b ★★★ 每一片的目标按**它自己那一片**算（按材料量线性，不是每片都按整站）',
       all(j['target'].max_chars <= 3000 for j in jb)
       and sum(j['target'].max_chars for j in jb)
       <= 0.22 * len(big[0].material()) * 1.35,
       f'合计上限 {sum(j["target"].max_chars for j in jb)} / 材料 '
       f'{len(big[0].material())} 字（0.22×材料 = {int(0.22 * len(big[0].material()))}）')

    # 顺序不变
    order = [u.name for u in UP.plan_units(day(2, '入楼收留') + day(2, '重走旧路', start=3)
                                          + day(2, '开庭抉择', start=5),
                                          nodes=NODES, current='N01')]
    ok('C4 ★★★ 打包**不许改顺序**（时间线是整理稿唯一不能错的东西）',
       order == ['入楼收留', '重走旧路', '开庭抉择'], str(order))


# ══════════════════════════════════════════════════════════════════════
#  D —— 接线（真跑 `_transcribe_once`，抓发出去的 prompt）
# ══════════════════════════════════════════════════════════════════════
class _World:
    progress_nodes = NODES
    current_node = 'N01'
    scene = '临街楼'
    weather = '晴'

    def on_stage_names(self):
        return ['甲']

    def world_prefix(self):
        return '这是一个关于账与壶的故事。'

    def clock_display(self):
        return '子时 23:00'


class _Ctx:
    world = _World()
    db = None
    people = ['甲']
    sample = ''
    story = ''

    def world_brief(self, cap=500):
        return '世界观'

    def genre(self):
        return ('', '')


def _run_once(body: str, *, block: str = '', target=None) -> str:
    """真跑一次 `_transcribe_once`，返回**发出去的 prompt**（`ask` 打桩）。"""
    import crew.agents as A
    seen: dict = {}

    async def fake_ask(tier, messages, **kw):
        # ⚠ **只认第一次调用**：`_transcribe_once` 后面还会走 `_fix_*` / `_checkup`，
        #   它们**用的也是同一个 `purpose='crew_day_novel'`** ⇒ 按 purpose 过滤不管用，
        #   会抓到**最后那条修补提示词**（第一版就是这样：prompt 只有 652 字，三条判据全红，
        #   而红的原因是"量错了对象"）。
        #   ⇒ 第一次为准；D0 再证明抓到的确实是**整理那一次**（含"今天实际发生的"）。
        # [EN] Only the **first** call: `_fix_*` / `_checkup` reuse the very same
        # [EN] `purpose='crew_day_novel'`, so filtering by purpose captures the **last repair
        # [EN] prompt** instead (first version: a 652-character prompt, three reds, all from
        # [EN] measuring the wrong object). First call wins; D0 proves it is the organizing one.
        if 'prompt' not in seen:
            seen['prompt'] = messages[0]['content']
            seen['max_tokens'] = kw.get('max_tokens')

        class R:
            ok = True
            value = '他伸手过去，指尖碰到的那片皮肤是凉的。' * 3
            notes = []
        return R()

    real = A.ask
    A.ask = fake_ask
    try:
        n = Novelist.__new__(Novelist)
        n.key = 'novelist'
        asyncio.run(Novelist._transcribe_once(
            n, _Ctx(), body, scope='', link='', craft='', cot_block='',
            unit_block=block, target=target))
    finally:
        A.ask = real
    return seen.get('prompt', '')


def d_wiring() -> None:
    print('\n── D 接线（目标真的进了提示词）──')
    heavy_u = UP.Unit(name='开庭抉择', weight='详', lines=day(6, '开庭抉择'))
    heavy_t = UP.target_for(heavy_u)
    p_heavy = _run_once('\n'.join(heavy_u.lines), block=UP.density_block(heavy_u, heavy_t),
                        target=heavy_t)
    ok('D0 ★★★ 抓到的确实是**整理那一次**的提示词（含"今天实际发生的"）—— '
       '量错对象比量错阈值更致命',
       '今天实际发生的' in p_heavy and len(p_heavy) > 1000, f'prompt {len(p_heavy)} 字')
    ok('D1 ★★★ 有篇幅目标时，提示词里**真的有"这一站要写多厚"**那一段',
       '这一站要写多厚' in p_heavy, f'prompt {len(p_heavy)} 字')

    light_u = UP.Unit(name='重走旧路', weight='略', lines=day(3, '重走旧路'))
    light_t = UP.target_for(light_u)
    p_light = _run_once('\n'.join(light_u.lines), block=UP.density_block(light_u, light_t),
                        target=light_t)
    ok('D2 ★★★ 轻站提示词里**仍然写着"一处都不许跳过"** ⇒ 这是致命的"两条规则互相打架"'
       '（模型只能随机挑一条）',
       '一处都不许跳过' not in p_light, '轻站里出现了"一处都不许跳过"')
    ok('D2b ★★★ 轻站提示词里**明确写着"只留结果"**（不是靠"少写点"这种没法执行的软话）',
       '只留结果' in p_light, '')
    ok('D3 ★★★ 重站提示词里**仍然有"一处都不许跳过"**（详的一站该写足，这条不能一起被删）',
       '一处都不许跳过' in p_heavy, '')

    # 预算跟着目标走（不跟材料走）
    ok('D4 ★★★ 预算按**目标**给，不按材料长度给（材料长而目标两句时，放开预算就会写长）',
       light_t.tokens < heavy_t.tokens, f'轻 {light_t.tokens} < 重 {heavy_t.tokens}')

    # 剪：轻站超长 ⇒ 按句末剪；重站绝不剪
    long_text = '他在路上走了很久很久。' * 40
    kept, cut = UP.trim_light(long_text, light_t)
    ok('D5 ★★★ 轻站写超了 ⇒ **按句末剪到上限**（提示词的遵循率只有 40~74%，关键约束要在解析层）',
       cut > 0 and len(kept) <= light_t.max_chars + 1 and kept.endswith('。'),
       f'{len(long_text)} → {len(kept)}（删 {cut}）')
    kept2, cut2 = UP.trim_light(long_text, heavy_t)
    ok('D5b ★★★ 重站**绝不剪**（那两档要求事件一处不漏，尾巴就是结局）',
       cut2 == 0 and kept2 == long_text, f'删了 {cut2} 字')

    # 服务层：`_transcribe` 真的用了 plan_units（AST）
    import ast
    src = (APP / 'crew' / 'agents.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    used = False
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == '_transcribe':
            used = 'plan_units' in ast.unparse(n) and '_transcribe_jobs' in ast.unparse(n)
    ok('D6 ★★★ `_transcribe` **真的按情节单元摊写作次**（写完不用 = 还是按字数切）',
       used, '')


# ══════════════════════════════════════════════════════════════════════
#  E —— 反例（就地证明判据会咬人）
# ══════════════════════════════════════════════════════════════════════
def e_counterexamples() -> None:
    print('\n── E 反例（把实现改坏一次，判据必须变红）──')
    saved = (UP.target_of, UP.pack, UP.trim_light)

    # ① 篇幅不再影响目标 ⇒ B1 必须红
    try:
        UP.target_of = lambda w, n=0: saved[0]('中', n)
        t = {w: UP.target_of(w, 6000) for w in ('详', '中', '略', '带过')}
        hung = t['详'].max_chars > t['中'].max_chars > t['略'].max_chars > t['带过'].max_chars
    finally:
        UP.target_of = saved[0]
    ok('E1 ★★★ 反例①：篇幅不影响目标 ⇒ B1 变红（否则"详略"根本没被管住）', not hung, '')

    # ② 打包不合并轻站 ⇒ C1 必须红
    try:
        UP.pack = lambda units, size: [[u] for u in units]
        units = UP.plan_units(day(2, '重走旧路') + day(2, '途中', start=3), nodes=NODES,
                              current='N02')
        g = UP.pack(units, 6000)
        merged = len(g) == 1
    finally:
        UP.pack = saved[1]
    ok('E2 ★★★ 反例②：轻站不合并 ⇒ C1 变红（三站变三次调用，每站各起一个场面）',
       not merged, '')

    # ③ 轻站不剪 ⇒ D5 必须红
    try:
        UP.trim_light = lambda text, target: (str(text or ''), 0)
        lt = saved[0]('略', 6000)
        kept, cut = UP.trim_light('他在路上走了很久很久。' * 40, lt)
        trimmed = cut > 0
    finally:
        UP.trim_light = saved[2]
    ok('E3 ★★★ 反例③：轻站不剪 ⇒ D5 变红（"一两句"全靠提示词，遵循率只有 40~74%）',
       not trimmed, '')


def main() -> int:
    print('=' * 62)
    print('  写作层按情节单元写（详的写足、略的一句带过）')
    print('=' * 62)
    for fn in (a_slicing, b_targets, c_packing, d_wiring, e_counterexamples):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            ok(f'{fn.__name__} 跑完', False, f'{e!r}')
            print(traceback.format_exc()[-800:])
    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n写作层按情节单元写验证：{good}/{n}')
    (OUT / 'writer_units_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if good == n else 2


if __name__ == '__main__':
    raise SystemExit(main())
