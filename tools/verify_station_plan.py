# -*- coding: utf-8 -*-
"""验证：**站表这条链**（大纲 → 切片 → 建节点 → 拆站 → 装配 → 推演）不丢东西（2026-10-27）。

★ 起因（用户更新了一份真实设定集之后实测出来的）：
  作者写的是 **8 站 32 章**，程序落盘的是 **9 站 35 章**，而且
    · 第 6 站跨度「数月」被写成「数日」、第 7 站「当日」被写成「一场」；
    · 第 8 站判据从「主角在庭上做出选择」变成「掌柜把话讲全」
      —— **作者写的结局三选一（归籍 / 祭献 / 留门）整个没了**。
  根因两条：
    ① 建节点只取**大纲前 4000 字**，而大纲 + 章纲有 13,581 字
       ⇒ 第 5~8 站的判据与章数**一个字都没进提示词**，模型是编的；
    ② 拆站那条路**漏搬 `章数`**（"配置字段漏搬"坑的第四例）。

★ 本判据守的是**链上每一道闸**，不测"字段存在"：
    A 组 站表切片（后半本要真的在窗口里、章纲不能混进来、英文也要认）
    B 组 作者站表**覆盖**模型那一版（判据照抄 ⇒ 不会再被拆）
    C 组 拆站时每个字段都跟着走（章数 / 高潮 / 情节线 / 选项 / 章纲）
    D 组 装配层（`sim.setup.load_settings`）搬运
    E 组 推演侧（`_nodes_text`）真的拿到这一站的台阶
    F 组 结局选项：作者写的那几个**一个都不能少**
    G 组 章纲按站挂载

English:
Verification: the **station-table chain** (outline -> slice -> build nodes -> split -> assembly ->
run) loses nothing (2026-10-27). Cause found by measurement after the author updated the a real project
settings: the author wrote **8 stations / 32 chapters**, the program persisted **9 stations / 35
chapters**, station 6's span "months" became "days", station 7's "one day" became "one scene", and
station 8's criterion changed from "the protagonist makes a choice in court" to "the keeper says it all"
-- **the author's three ending options vanished entirely**. Two root causes: ① node building read
only **the first 4000 chars** of a 13,581-char outline, so stations 5-8 never reached the prompt
and the model invented them; ② the split path **dropped `章数`** (fourth instance of the documented
dropped-field trap). This guards **every gate on the chain**, not "the field exists".
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from ingest import progress as PR                 # noqa: E402
from director.engine import shape_branches        # noqa: E402
from director.day_plan import _nodes_text         # noqa: E402
from sim import setup as SU                       # noqa: E402

REPORT: list[dict] = []


def rec(name: str, ok_: bool, detail: str = '') -> bool:
    REPORT.append({'name': name, 'ok': bool(ok_), 'detail': detail})
    print(f"  {'✓' if ok_ else '✗'} {name}"
          + (f'  | {detail}' if detail else ''), flush=True)
    return bool(ok_)


# ── 样例：仿一份真实项目的大纲（八站只写四站，够验"后半本在不在窗口里"）────────
_CN_OUTLINE = """# 故事大纲

## 三、篇幅规划
- **总章数**：32
- **总字数**：7.5万字
- **每章字数**：2400

## 四、分站清单

### 第 1 站 · 白日入门（第 1 章）

- **跨度**：当日
- **篇幅**：中
- **章数**：3
- **概要**：主角白日醒在楼门口台阶下，没包袱、鞋底没磨、只记得自己的名字。
  城里墙根下确有一群逃荒的，他照着他们给自己安了个由头。
- **完成判据**：主角被掌柜留下做了楼里的伙计。
- **情节线**（3 个单元）：
  1. 醒在台阶下，照着逃荒的人给自己安了个身份
  2. 伙计盘问他从哪儿来、吃什么
  3. 当夜挂白灯笼，他第一次看见没有影子的女客
- **高潮**：掌柜灌下那碗苦茶，说了一句「留下吧」。
- **情绪**：松 → 紧
- **可笑处**：老陈非要给他记一笔，却不知道该记哪一栏。

### 第 2 站 · 兰若寺外（第 5–8 章）

- **跨度**：数日
- **篇幅**：详
- **章数**：5
- **概要**：楼落在金华城北一处渡口，主角被派去递一碗茶。
- **完成判据**：主角把那个书生从兰若寺门口劝了回来。
- **情节线**（5 个单元）：
  1. 楼落在金华城北的渡口
  2. 书生嫌城里房价贵，要去兰若寺过夜
  3. 主角第一次用看影看气
  4. 把书生从寺门口劝回来
  5. 回楼翻旧账
- **高潮**：主角说出「寺里那位好心的老婆子没有影子」。

### 第 7 站 · 府城（第 88–96 章）

- **跨度**：当日
- **篇幅**：详
- **章数**：5
- **概要**：泰安府城雨夜，楼门口来了两个人。
- **完成判据**：主角自己把那七个地方数清了。
- **高潮**：数到第七个的时候，手停在半空。

### 第 8 站 · 重审（第 140–150 章）

- **跨度**：一场
- **篇幅**：详
- **章数**：4
- **概要**：七桩悬案并卷，楼无处可去。
- **完成判据**：主角在庭上做出了选择。
- **情节线**（4 个单元）：
  1. 七桩悬案并卷
  2. 掌柜把话讲全
  3. 开庭，阿九褪下袖子作证
  4. 留在主角手上的是个选择
- **高潮**：阿九褪下袖子露出后颈的疤，一个字不说。
- **选项**：归籍 / 祭献 / 留门
"""

# ── 样例：章纲（**没有**完成判据，站号与大纲重合）─────────────────────
_CN_PLAN = """# 章纲

## 第 1 站 · 白日入门（第 1–3 章）

**第 1 章 · 入门**
- 推进：主角得给自己找一个能站住脚的由头。
- **高潮**：老陈摊开账本要给他记一笔，最后一栏都没记。

**第 2 章 · 上灯**
- 推进：他得在楼里有个位置。
- **高潮**：掌柜灌他一碗苦茶，说了一句「留下吧」。

## 第 8 站 · 重审（第 29–32 章）

**第 29 章 · 并卷**
- 推进：七桩悬案并到一处。
- **高潮**：掌柜三百年来第一次把话讲全。
"""

_EN_OUTLINE = """# Story outline

## 4. Station list

### Station 1 · The early drum

- **Span**: one scene
- **Length**: normal
- **Chapters**: 2
- **Summary**: Shen Yan is on night duty. The drum is a full quarter-hour ahead
  of the clock; he goes down to check.
- **Done when**: Shen Yan confirms the drum was a quarter-hour early while the water
  level was not off.
- **Climax**: He confirms it -- this moment is the station's climax.
- **Beats** (3 units):
  1. He hears the drum
  2. He checks the water
  3. He writes it down

### Station 8 · Confess it himself

- **Span**: the same day
- **Length**: full
- **Chapters**: 4
- **Done when**: Shen Yan publicly admits he made that clock change.
- **Climax**: He says it in front of the ward.
- **Options**: return / offer / leave the door
"""


# ══════════════════════════════════════════════════════════════════
#  【A】站表切片
# ══════════════════════════════════════════════════════════════════
def group_a() -> None:
    print('\n【A】站表切片 —— 后半本书要真的在窗口里', flush=True)
    blocks = PR._station_blocks(_CN_OUTLINE)
    sliced, n = PR.slice_stations(_CN_OUTLINE)
    rec('A1 八站大纲切出 4 站（样例写了 4 站）', n == 4 and len(blocks) == 4,
        f'站数={n}')
    rec('A2 ★★★ 最后一站（第 8 站）的**判据**在切片里'
        '（以前它落在 4000 字截断线之外，模型只能编）',
        '主角在庭上做出了选择' in sliced, f'{len(sliced)} 字')
    rec('A3 ★★★ 最后一站的**章数 / 跨度 / 选项**也在',
        ('章数' in sliced or '4' in sliced) and '归籍' in sliced,
        '选项=' + str([x for x in ('归籍', '祭献', '留门') if x in sliced]))
    rec('A4 切片比原文短（**更省 token**，不是靠放大窗口解决的）',
        len(sliced) < len(_CN_OUTLINE), f'{len(_CN_OUTLINE)} → {len(sliced)}')
    rec('A5 情节线的编号单元**一条都不丢**（正则不能跨行吃掉第一条）',
        '醒在台阶下' in sliced and '伙计盘问' in sliced and '当夜挂白灯笼' in sliced)
    rec('A6 跨行的**概要续行**拼回来（不拼回来就是半句话，比没有更误导）',
        '城里墙根下确有一群逃荒的' in sliced)
    rec('A7 「情绪 / 可笑处」这些**不是站表**的东西不进切片',
        '可笑处' not in sliced and '老陈非要给他记一笔' not in sliced)

    # 章纲混进来时不能把站数翻倍
    merged = _CN_OUTLINE + '\n\n' + _CN_PLAN
    _s2, n2 = PR.slice_stations(merged)
    rec('A8 ★★★ 章纲.md 里那些 `## 第 N 站`（**没有完成判据**）不会当成站'
        '（否则 8 站变 16 站）', n2 == n, f'合并后站数={n2}（原 {n}）')

    # 英文
    _s3, n3 = PR.slice_stations(_EN_OUTLINE)
    rec('A9 ★★★ 英文站块（`### Station 1` + `- **Span**: one scene`）也切得出来',
        n3 == 2, f'站数={n3}')
    rec('A10 英文的跨度 / 篇幅**归一成档位**（`one scene`→一场、`normal`→中）',
        '一场' in _s3 and '中' in _s3, _s3.split('\n')[2] if len(_s3.split('\n')) > 2 else '')
    rec('A11 英文判据的**续行**拼回来且补空格（不能出现 "the waterlevel"）',
        'while the water level was not off' in _s3 and 'waterlevel' not in _s3)

    # 兜底
    _s4, n4 = PR.slice_stations('# 大纲\n\n## 一、起承转合\n\n起：他醒在门口。\n')
    rec('A12 没有「第 N 站」标题 ⇒ 返回空（**不编造**，调用方回退老口径）',
        n4 == 0 and _s4 == '', f'站数={n4}')

    # ★ 章纲里**站号不重复**的那些块（大纲只有 1/2/7/8 站，章纲写了 21/22 站）
    #   ⇒ 这时"同一站号只取第一次"那道保险**救不了**，只能靠"至少有一个站字段"
    #   这道过滤。两道闸各守一半，缺一道就会多出两站。
    # [EN] ★ Chapter-plan blocks whose **station numbers do not repeat** (the outline has 1/2/7/8,
    # the plan has 21/22) => the "first occurrence of a number wins" guard cannot help; only the
    # "at least one station field" filter can. The two gates guard different halves.
    extra = ('\n\n### 第 21 站 · 章纲里的站（第 21 章）\n\n'
             '- **推进**：这一章要往前推。\n'
             '- **高潮**：章纲写的高潮。\n'
             '- **钩子**：下一章的钩子。\n')
    _s6, n6 = PR.slice_stations(_CN_OUTLINE + extra)
    rec('A14 ★★★ 章纲里**站号不重复**的块也**不能**当成站'
        '（A8 只守"站号重复"那半边；这道是"没有站字段"那半边）',
        n6 == n, f'加了一个章纲块后站数={n6}（原 {n}）')

    # ★ 同一个站号**写了两遍**、两遍都有完成判据 ⇒ 只能算一站。
    #   ⚠ A8/A14 那两道闸都是"字段过滤"，守不到"号重复"这道（反例法 ⑥b 实测：
    #   把去重删掉，A8 照样绿 ⇒ 那道去重当时**没人守**）。
    # [EN] ★ The same station number **written twice**, both with a criterion => count it once.
    #   ⚠ A8/A14 are both "field filter" gates and cannot guard "duplicate number" (mutation knife
    #   ⑥b: deleting the dedup left A8 green => nobody was guarding the dedup).
    dup = ('\n\n### 第 1 站 · 又写了一遍（第 1 章）\n\n'
           '- **跨度**：当日\n- **篇幅**：中\n- **章数**：3\n'
           '- **完成判据**：主角被掌柜留下做了楼里的伙计。\n')
    _s7, n7 = PR.slice_stations(_CN_OUTLINE + dup)
    rec('A15 ★★★ 同一个站号出现两次（**两遍都有完成判据**）⇒ 只算一站',
        n7 == n, f'重复写一遍第 1 站后站数={n7}（原 {n}）')

    # 装不下时保标题与判据
    long_outline = _CN_OUTLINE
    for i in range(9, 40):
        long_outline += (f'\n\n### 第 {i} 站 · 第{i}站\n\n- **跨度**：数日\n'
                         f'- **篇幅**：中\n- **章数**：3\n'
                         f'- **完成判据**：第{i}站的事办成了。\n'
                         f'- **情节线**（3 个单元）：\n  1. 第一件事\n'
                         f'  2. 第二件事\n  3. 第三件事\n')
    _s5, n5 = PR.slice_stations(long_outline, max_chars=1200)
    rec('A13 ★★★ 装不下时**先砍情节线 / 概要，标题与判据永远留着**'
        '（丢判据 = 没有站表）',
        len(_s5) <= 1200 and '完成判据' in _s5 and '###' in _s5,
        f'{len(_s5)} 字 / {n5} 站')


# ══════════════════════════════════════════════════════════════════
#  【B】作者站表覆盖模型那一版
# ══════════════════════════════════════════════════════════════════
def group_b() -> None:
    print('\n【B】作者写了的字段 ⇒ **用回作者的**（模型改写会拆站）', flush=True)
    blocks = PR._station_blocks(_CN_OUTLINE)

    def _node(name, criteria, chapters=0, span='', weight=''):
        return PR.ProgressNode(id='N01', name=name, summary='模型的概要',
                               criteria=criteria, chapters=chapters,
                               span=span, weight=weight)

    # 模型改写了判据（还加了并列词）
    nodes = [_node('白日入门', '掌柜灌下苦茶后，开口把主角留下做楼里的伙计'),
             _node('府城数地', '主角独自在雨里数到了第七个'),
             _node('庭上重审', '主角在庭上就自己的去留做出选择')]
    n = PR.apply_author_stations(nodes, blocks)
    rec('B1 ★★★ 模型改写的判据**被覆盖回作者的原句**',
        nodes[0].criteria == '主角被掌柜留下做了楼里的伙计。',
        nodes[0].criteria)
    rec('B2 ★★★ 站名被模型改写（「府城」→「府城数地」）**仍能匹配**'
        '（按站名双向包含，不按站号）',
        nodes[1].criteria == '主角自己把那七个地方数清了。', nodes[1].criteria)
    rec('B3 「重审」→「庭上重审」也匹配得上',
        nodes[2].criteria == '主角在庭上做出了选择。', nodes[2].criteria)
    rec('B4 章数 / 跨度 / 篇幅 / 高潮 / 情节线 / 选项一并覆盖',
        (nodes[0].chapters, nodes[0].span, nodes[0].weight) == (3, '当日', '中')
        and '留下吧' in nodes[0].climax and len(nodes[0].beats) == 3,
        f"章数={nodes[0].chapters} 跨度={nodes[0].span} 篇幅={nodes[0].weight} "
        f"情节线={len(nodes[0].beats)} 条")
    rec('B5 选项也覆盖（最后一个节点的三个结局）',
        list(nodes[2].options) == ['归籍', '祭献', '留门'], str(list(nodes[2].options)))
    rec('B6 覆盖条数与匹配上的站数一致', n == 3, str(n))

    # 作者没写的字段不能被清空
    nd = _node('白日入门', '模型的判据', chapters=7, span='数月', weight='略')
    PR.apply_author_stations([nd], [('### 第 1 站 · 白日入门', {'概要': '作者的概要'}, [])])
    rec('B7 ★★★ 作者没写的字段**不清空**（模型的推断仍然算数）',
        (nd.chapters, nd.span, nd.weight) == (7, '数月', '略')
        and nd.criteria == '模型的判据',
        f"{nd.chapters}/{nd.span}/{nd.weight}/{nd.criteria}")
    rec('B8 作者写了概要就用作者的', nd.summary == '作者的概要', nd.summary)

    # 匹配不上就不动
    nd2 = _node('编出来的站', '模型的判据', chapters=2)
    PR.apply_author_stations([nd2], blocks)
    rec('B9 匹配不上的节点**原样不动**（不冒险）',
        nd2.criteria == '模型的判据' and nd2.chapters == 2)

    # ★ 双向包含里**另一半**：模型把站名写得比作者的**短**（「白日入门」→「入门」）
    #   —— 单向 `sn in n` 匹配不上，必须靠 `n in sn`。
    # [EN] ★ The **other half** of two-way containment: the model writes a **shorter** name than the
    # author's ("白日入门" -> "入门") -- one-way `sn in n` misses it; only `n in sn` catches it.
    nd3 = _node('入门', '模型的判据')
    PR.apply_author_stations([nd3], blocks)
    rec('B11 ★★★ 模型把站名写得**比作者的短**（「白日入门」→「入门」）也要匹配上'
        '（这是双向包含的另一半）',
        nd3.criteria == '主角被掌柜留下做了楼里的伙计。', nd3.criteria)

    # 覆盖之后不再触发"串了几件事"的拆分
    from world import progress_split as _PS
    before = [_node('白日入门', '掌柜灌下苦茶后，开口把主角留下做楼里的伙计')]
    _d, made_before = _PS.split_fat_nodes([{'名称': '白日入门',
                                            '完成判据': before[0].criteria}])
    PR.apply_author_stations(before, blocks)
    after = PR.split_and_rebuild(before)
    rec('B10 ★★★ 覆盖之后再拆 ⇒ **不会多站**'
        '（模型改写前会拆成 2 站，作者的判据只有一件事）',
        made_before >= 1 and len(after) == 1,
        f'改写时拆出 {made_before} 站；覆盖后 {len(after)} 站')


# ══════════════════════════════════════════════════════════════════
#  【C】拆站：每个字段都跟着走
# ══════════════════════════════════════════════════════════════════
def group_c() -> None:
    print('\n【C】拆站 —— 章数与站内的台阶不许丢（漏搬坑第四例）', flush=True)
    nd = PR.ProgressNode(id='N01', name='府城', summary='概要',
                         criteria='主角数完七处，并明白那些地方都是他死过的地方',
                         span='当日', weight='详', chapters=5,
                         climax='数到第七个，手停在半空。',
                         beats=('他看见疤', '他开始数'),
                         options=('归籍', '祭献'), chapter_plan='第 24 章 …')
    out = PR.split_and_rebuild([nd])
    rec('C1 判据串了两件事 ⇒ 真的拆成 2 站', len(out) == 2, f'{len(out)} 站')
    rec('C2 ★★★ 拆出来的站**章数还在**（以前丢成 0 ⇒ 兜底 ⇒ 32 章变 35 章）',
        all(x.chapters == 5 for x in out), str([x.chapters for x in out]))
    rec('C3 跨度 / 篇幅照抄母站',
        all(x.span == '当日' and x.weight == '详' for x in out),
        str([(x.span, x.weight) for x in out]))
    rec('C4 ★★★ 高潮 / 情节线 / 选项 / 章纲也跟着走'
        '（丢了这两站就只剩终点线、没有过程）',
        all(x.climax and x.beats and x.options and x.chapter_plan for x in out),
        str([(len(x.beats), len(x.options), bool(x.chapter_plan)) for x in out]))
    rec('C5 拆完重新编号（N01 / N02）',
        [x.id for x in out] == ['N01', 'N02'], str([x.id for x in out]))

    # 反面：不串事的判据不该被拆
    nd2 = PR.ProgressNode(id='N01', name='府城', summary='',
                          criteria='主角自己把那七个地方数清了。', chapters=5)
    rec('C6 只写了一件事的判据**不被拆**（新闸门不许误伤）',
        len(PR.split_and_rebuild([nd2])) == 1)


# ══════════════════════════════════════════════════════════════════
#  【D】装配层搬运（`sim.setup.load_settings`）
# ══════════════════════════════════════════════════════════════════
def group_d(tmp: Path) -> None:
    print('\n【D】装配层 —— yaml 里写了要真的运到运行时', flush=True)
    import yaml
    d = tmp / 'sd'
    d.mkdir(parents=True, exist_ok=True)
    (d / '故事进度.yaml').write_text(yaml.dump({'节点': [{
        'id': 'N01', '名称': '重审', '概要': '概要',
        '完成判据': '主角在庭上做出了选择。', '状态': '未开始',
        '跨度': '一场', '篇幅': '详', '章数': 4,
        '高潮': '阿九褪下袖子，一个字不说。',
        '情节线': '七桩悬案并卷；掌柜把话讲全',   # 手写成一串也要认
        '选项': ['归籍', '祭献', '留门'],
        '章纲': '第 29 章 …',
    }]}, allow_unicode=True), encoding='utf-8')
    st = SU.load_settings(d)
    node = (st.get('nodes') or [{}])[0]
    rec('D1 章数搬过来', int(node.get('章数') or 0) == 4, str(node.get('章数')))
    rec('D2 高潮搬过来', '阿九褪下袖子' in str(node.get('高潮') or ''))
    rec('D3 ★★★ 情节线**手写成一串**也归一成列表（"A；B" ⇒ 2 条）',
        node.get('情节线') == ['七桩悬案并卷', '掌柜把话讲全'],
        str(node.get('情节线')))
    rec('D4 选项 / 章纲搬过来',
        node.get('选项') == ['归籍', '祭献', '留门']
        and str(node.get('章纲') or '').startswith('第 29 章'),
        f"{node.get('选项')} / {str(node.get('章纲'))[:8]}")
    rec('D5 跨度 / 篇幅 / 章数三兄弟都还在（老字段没被新字段挤掉）',
        node.get('跨度') == '一场' and node.get('篇幅') == '详')


# ══════════════════════════════════════════════════════════════════
#  【E】推演侧：`_nodes_text` 真的拿到这一站的台阶
# ══════════════════════════════════════════════════════════════════
class _W:
    def __init__(self, rows):
        self.current_node = 'N01'
        self.progress_nodes = rows


class _DB:
    pass


def group_e() -> None:
    print('\n【E】推演侧 —— 导演要看见这一站的台阶与章纲', flush=True)
    rows = [{'id': 'N01', '名称': '重审', '概要': '概要',
             '完成判据': '主角在庭上做出了选择。',
             '高潮': '阿九褪下袖子露出后颈的疤。',
             '情节线': ['七桩悬案并卷', '掌柜把话讲全', '开庭'],
             '章纲': '第 29 章 · 并卷\n- 推进：七桩悬案并到一处。\n'}]
    t = _nodes_text(_W(rows), _DB())
    rec('E1 高潮进推演文本', '阿九褪下袖子露出后颈的疤' in t)
    rec('E2 情节线进推演文本', '七桩悬案并卷' in t)
    rec('E3 ★★★ 台阶那行的措辞必须是**参考**不是清单'
        '（写"按顺序打勾"会让推演变成逐条执行）'
        ' ⚠ 必须**逐处**判：只判"文本里有『参考』两个字"的话，'
        '章纲那行带着"参考"就能把它顶过去 ⇒ 台阶那行写成清单也照样绿（反例法 ⑲ 实测）',
        '这一站的台阶（**参考**，不必按顺序打勾）' in t and '不是排期' in t)
    rec('E4 章纲（当前站那几章）进推演文本', '第 29 章' in t)

    # 老项目（没有这些字段）行为不变
    old = [{'id': 'N01', '名称': '开端', '概要': '概要',
            '完成判据': '起始场景完成'}]
    t2 = _nodes_text(_W(old), _DB())
    rec('E5 ★★★ 老项目（没有高潮 / 情节线 / 章纲）**文本不含新内容**'
        '（新层不能给老项目添噪音）',
        '这一站的高潮' not in t2 and '这一站的台阶' not in t2
        and '章纲' not in t2 and '起始场景完成' in t2)

    # 章纲超长时限长。⚠ 样例必须**真的够长**：以前写 400 行（约 1600 字）而阈值是
    # 2000 ⇒ 不限长也就 1700 字，判据照样绿 ⇒ 那是一条空靶（反例法 ⑳ 实测）。
    # [EN] The sample must genuinely exceed the cap: 400 lines (~1600 chars) against a 2000
    # threshold meant even an uncapped plan passed => an empty target (mutation knife ⑳).
    rows3 = [dict(rows[0]), ]
    rows3[0]['章纲'] = '第 29 章\n' + '内容。\n' * 1200
    t3 = _nodes_text(_W(rows3), _DB())
    rec('E6 ★★★ 章纲过长时**限长**（不能把整本 32 章塞进每天的提示词）',
        len(t3) < 2000, f'{len(t3)} 字（上限 {t3 and 900}）')


# ══════════════════════════════════════════════════════════════════
#  【F】结局选项：作者写的那几个一个都不能少
# ══════════════════════════════════════════════════════════════════
def group_f() -> None:
    print('\n【F】结局选项 —— 作者写的必须在、且必须在最前', flush=True)
    opts = ['归籍', '祭献', '留门']
    rows = [{'标题': '归籍', '后果': '他重新有籍'},
            {'标题': '祭献', '后果': '楼空了'}]
    got = shape_branches(rows, opts)
    rec('F1 ★★★ 模型漏掉的那个**补回来**（作者写了 3 个就不能只给 2 个）',
        [b['标题'] for b in got] == opts, str([b['标题'] for b in got]))
    # ⚠ 先判长度再取下标：判据一崩，后面的组就**一条都不报**了
    #   （反例法 ㉒ 实测：崩掉之后只看得到 F1 红，F2~F6 全被吞）。
    # [EN] Check the length before indexing: once a criterion raises, every later group goes
    # unreported (mutation knife ㉒: only F1 showed red, F2-F6 were swallowed by the crash).
    rec('F2 补回来的那条后果留空（模型该补没补，**空着比编一句强**）',
        len(got) == 3 and got[2]['后果'] == '',
        repr(got[2]['后果']) if len(got) > 2 else f'只有 {len(got)} 条')

    rows2 = [{'标题': '归籍', '后果': 'A'}, {'标题': '祭献', '后果': 'B'},
             {'标题': '留门', '后果': 'C'}, {'标题': '自己出去闯', '后果': 'D'}]
    got2 = shape_branches(rows2, opts)
    rec('F3 模型多编的候选排**在作者那几个后面**（不丢，但作者的必须在最前）',
        [b['标题'] for b in got2][:3] == opts
        and got2[-1]['标题'] == '自己出去闯', str([b['标题'] for b in got2]))
    rec('F4 id 统一重排成 E1..En（界面按 id 回选，编号必须与返回的一致）',
        [b['id'] for b in got2] == ['E1', 'E2', 'E3', 'E4'],
        str([b['id'] for b in got2]))

    rows3 = [{'标题': '归籍2', '后果': 'A'}]
    got3 = shape_branches(rows3, opts)
    rec('F5 ★★★ 模型把标题改写了（「归籍」→「归籍2」）⇒ **认出来并用作者的原词**'
        '（只认全等的话这句"以作者原词为准"是死代码 —— 反例法 ㉔ 实测）',
        got3 and got3[0]['标题'] == '归籍' and len(got3) == 3,
        str([b['标题'] for b in got3]))

    got4 = shape_branches([{'标题': '往东走', '后果': 'A'},
                           {'标题': '往西走', '后果': 'B'}], None)
    rec('F6 ★★★ 没有作者选项时**行为不变**（id 仍是 B1..Bn）',
        [b['id'] for b in got4] == ['B1', 'B2'], str([b['id'] for b in got4]))


# ══════════════════════════════════════════════════════════════════
#  【G】章纲按站挂载
# ══════════════════════════════════════════════════════════════════
def group_g() -> None:
    print('\n【G】章纲 —— 按站挂到节点上，推演只喂当前站', flush=True)
    rec('G1 `章纲.md` 被认成章纲', PR.is_chapter_plan('章纲.md'))
    rec('G2 英文 `chapter-outline.md` 也认',
        PR.is_chapter_plan('chapter-outline.md'))
    rec('G3 ★★★ `故事大纲.md` **不**被认成章纲（认错了整本大纲会当章纲挂上去）',
        not PR.is_chapter_plan('故事大纲.md')
        and not PR.is_chapter_plan('story-outline.md'))

    blocks = PR.slice_chapter_plan(_CN_PLAN)
    rec('G4 章纲按站切成 2 块', len(blocks) == 2, str(len(blocks)))

    nodes = [PR.ProgressNode(id='N01', name='白日入门', summary='',
                             criteria='x'),
             PR.ProgressNode(id='N08', name='庭上重审', summary='',
                             criteria='y')]
    n = PR.attach_chapter_plan(nodes, blocks)
    rec('G5 按站名挂载（**站名被模型改写也算**）', n == 2, f'挂上 {n} 个')
    rec('G6 挂的是**这一站**的章节（第 1 站拿到"第 1 章 · 入门"）',
        '第 1 章 · 入门' in nodes[0].chapter_plan
        and '第 29 章' in nodes[1].chapter_plan,
        f"{nodes[0].chapter_plan[:10]} / {nodes[1].chapter_plan[:10]}")

    nodes2 = [PR.ProgressNode(id='N02', name='不存在的站', summary='',
                              criteria='x')]
    rec('G7 匹配不上就不挂（**错位的章纲比没有更糟**）',
        PR.attach_chapter_plan(nodes2, blocks) == 0
        and nodes2[0].chapter_plan == '')


# ══════════════════════════════════════════════════════════════════
#  【H】★ 抽取函数时**不许把类里的方法吞掉**（2026-10-27 真事故）
# ══════════════════════════════════════════════════════════════════
#: 只扫**运行时包**（`tools/` 与 `developers/` 里的验证器/探针会故意写
#: `def _spy(self)` 这种闭包，扫它们全是误报）。
# [EN] Runtime packages only (verifiers/probes under `tools/` and `developers/` deliberately write
# closures like `def _spy(self)`; scanning them is all false positives).
_RUNTIME_DIRS = ('director', 'sim', 'ingest', 'world', 'actors', 'agent',
                 'agents', 'crew', 'craft', 'export', 'display', 'booklab',
                 'compliance')


def _swallowed_methods() -> list[str]:
    """找出**嵌在模块级函数里**的 `def`（带 `self` 或带装饰器）—— 那就是被吞掉的。

    ⚠ 为什么连"带装饰器"也算：`pick_branch` 是 `@staticmethod`，**没有 `self`**，
    只按 `self` 判会正好漏掉这次被吞掉的那一个。
    
        English:
    Find `def`s **nested inside a module-level function** (with `self` or with decorators) -- those
    are the swallowed ones. ⚠ Why decorators count: `pick_branch` is a `@staticmethod` with **no
    `self`**, so a `self`-only check misses exactly the one that got swallowed.
    """
    import ast
    out: list[str] = []
    for d in _RUNTIME_DIRS:
        base = APP / d
        if not base.exists():
            continue
        for f in base.rglob('*.py'):
            if '__pycache__' in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue

            def _walk(node, in_class: bool, in_mod_fn: bool) -> None:
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [a.arg for a in ch.args.args]
                        if in_mod_fn and not in_class and (args[:1] == ['self']
                                                           or ch.decorator_list):
                            out.append(f'{f.relative_to(APP)}:{ch.lineno} '
                                       f'def {ch.name}')
                        _walk(ch, in_class, in_mod_fn or not in_class)
                    elif isinstance(ch, ast.ClassDef):
                        _walk(ch, True, False)
                    else:
                        _walk(ch, in_class, in_mod_fn)
            _walk(tree, False, False)
    return out


def group_h() -> None:
    print('\n【H】★ 抽出模块级函数时，后面的类方法不许被吞掉', flush=True)
    from director.engine import DirectorEngine
    rec('H1 ★★★ `DirectorEngine.pick_branch` **还在类上**'
        '（`sim/loop.py` 调它，被吞了要到真跑才 AttributeError）',
        'pick_branch' in vars(DirectorEngine))
    rec('H2 ★★★ `DirectorEngine._is_stalling` 还在类上'
        '（`engine.py` 每拍都调它）',
        '_is_stalling' in vars(DirectorEngine))
    import director.engine as _EN
    rec('H3 `shape_branches` 在**模块级**（抽取确实完成了，不是没抽）',
        'shape_branches' not in vars(DirectorEngine)
        and callable(getattr(_EN, 'shape_branches', None)))
    rec('H4 两个方法的 `__qualname__` 都挂在 `DirectorEngine.` 下'
        '（嵌进别的函数里就是 `shape_branches.<locals>.pick_branch`）',
        DirectorEngine.pick_branch.__qualname__ == 'DirectorEngine.pick_branch'
        and DirectorEngine._is_stalling.__qualname__ == 'DirectorEngine._is_stalling',
        DirectorEngine.pick_branch.__qualname__)
    bad = _swallowed_methods()
    rec('H5 ★★★ 运行时包里**没有一个 `def` 被嵌在模块级函数里**'
        '（这次事故就是这个形状：语法合法、永不执行）',
        not bad, '；'.join(bad[:4]))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_station_'))
    try:
        group_a()
        group_b()
        group_c()
        group_d(tmp)
        group_e()
        group_f()
        group_g()
        group_h()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [c for c in REPORT if not c['ok']]
    print('\n' + '─' * 62)
    print(f'  站表链验证：{len(REPORT) - len(bad)}/{len(REPORT)}'
          + ('' if not bad else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
