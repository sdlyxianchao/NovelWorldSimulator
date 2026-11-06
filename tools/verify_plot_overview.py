# -*- coding: utf-8 -*-
"""验证：「剧情总览」—— 一份从头到尾的流程图数据 + 那张从上往下的图。

用户 2026-10-26：
    「我希望运行界面右侧的剧情Panel的按钮 可以点击 …… 其中包含了本次推演从开始到现在的
     故事线，包含所有主要情节，其中每个情节用少量文字总结 …… 从开头到结尾用一个流程图
     （从上往下的）展示，如果中间涉及到了让用户选择剧情，则展示一个多选，并从用户选择
     的剧情继续流程 …… 对话框的最上面加一个跑马灯形式的左右切换，我还可以切换到之前的
     推演 …… 目前和之前已经进行的推演的数据由你生成一下，后续的数据则由软件自动生成。」

⚠ **不要叫 `verify_story_flow`** —— 那个名字已经被"中栏故事体"那支占了
  （`display/story_render.py` 的阅读感）。同名不同事，是这种判据最容易踩的坑：
  跑全量的人看到绿的 `verify_story_flow`，会以为流程图这条也被守住了。

这一支按"数据 → 存取 → 控件 → 接线 → 反例"五段测：

| 段 | 测什么 | 为什么必须测 |
|---|---|---|
| A | 纯函数：选项怎么来的、选择怎么记 | "三条路"是本项目唯一的选择点来源，读错就是凭空造一个分叉 |
| B | 生成：谁演过、谁在演、实据几个幕 | 用户要核对"你说演过了，演了多少" |
| C | 存取：旧了就重算、**重算不许覆盖选择** | 选的线第二天没了 ⇒ "点了没反应" |
| D | 控件：卡片之间连不连、选项能不能点、没后续时说什么 | 图是给人看的，断开的一列不是"流程" |
| E | 接线：面板三个入口、循环两处自动刷新、英文清单 | 写好了没人调 = 一个字都不生效 |
| F | 反例：就地改坏三处，确认对应那条会红 | 判据自己不许是"永远绿" |

跑法：`.venv\\Scripts\\python.exe tools/verify_plot_overview.py`
产出：`assets/screenshots/plot_overview_report.json`

English:
Verification for the "story overview": the start-to-finish flowchart data plus the top-down chart.
⚠ **Not named `verify_story_flow`** -- that name already belongs to the middle column's prose
rendering. Two things under one name is the classic trap here: whoever reads the full run sees a
green `verify_story_flow` and assumes the chart is guarded too.
Five sections: data -> persistence -> controls -> wiring -> counterexamples.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft                                       # noqa: E402

from plot import flow as PF                             # noqa: E402
from gui import story_flow_dialog as SFD                # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    good = bool(cond)
    report['checks'].append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    print(('  ok  ' if good else '  ✗  ') + name + (f'  [{detail}]' if detail else ''))
    return good


# ══════════════════════════════════════════════════════════════
#  夹具
# [EN] Fixtures
# ══════════════════════════════════════════════════════════════
_NODES = [
    {'id': 'N01', '名称': '入楼收留', '概要': '阿九在街头醒来，被掌柜收留当伙计。',
     '完成判据': '阿九得到伙计身份。', '状态': '已完成'},
    {'id': 'N02', '名称': '金华旧账', '概要': '金华站翻旧账，认出一笔自己的笔迹。',
     '完成判据': '阿九在旧账上认出笔迹。', '状态': '进行中'},
    {'id': 'N03', '名称': '重走旧路', '概要': '三站旧事，老陈酒后讲起从前掌柜。',
     '完成判据': '阿九听老陈讲出前任掌柜的事。', '状态': '未开始'},
    {'id': 'N04', '名称': '开庭抉择',
     '概要': '重审开庭，阿九面对归籍、祭献、留门三条路，必须当众给出终局选择。',
     '完成判据': '阿九当众宣布终局选择。', '状态': '未开始'},
]


def mk_project(root: Path, nodes=None) -> Path:
    """造一个项目：`设定集/故事进度.yaml`（+ 一句剧情走向）。"""
    (root / '设定集').mkdir(parents=True, exist_ok=True)
    import yaml
    (root / '设定集' / '故事进度.yaml').write_text(
        yaml.safe_dump({'节点': nodes if nodes is not None else _NODES},
                       allow_unicode=True, sort_keys=False), encoding='utf-8')
    (root / '设定集' / '剧情走向.md').write_text(
        '起：醒来被收留。承：学楼规。转：旧账见笔迹。合：终局抉择。\n', encoding='utf-8')
    return root


def mk_run(root: Path, name: str = '第1次模拟2026-01-01-00-00') -> Path:
    r = root / name
    (r / '每天的生活').mkdir(parents=True, exist_ok=True)
    return r


def mk_day(run: Path, day: int, stations: list[str]) -> Path:
    """造一天的 `.json` 边车：每站一幕（`node_name` 是**站名**）。"""
    from display import script as S
    from display import script_render as SR
    scenes = []
    for i, nm in enumerate(stations):
        scenes.append(S.SceneScript(
            time_label=f'辰时 {8 + i:02d}:00', place='楼里', node_name=nm, day=day,
            cast=['甲'], entries=[S.Entry(kind=S.DIALOGUE, speaker='甲',
                                          text=f'第{day}天第{i}场。')]))
    p = run / '每天的生活' / f'第{day:03d}天.json'
    p.write_text(SR.to_json(scenes), encoding='utf-8')
    return p


def mk_script(run: Path, day: int, *, beats=None, story='', brief='', intro='',
              shots=None, problems=None) -> Path:
    """造 `当日剧本.json`（剧作家的底稿）—— **详细剧情那一层唯一的素材来源**。"""
    import json as _json
    p = run / '当日剧本.json'
    data = {}
    if p.is_file():
        try:
            data = _json.loads(p.read_text(encoding='utf-8'))
        except Exception:                                        # noqa: BLE001
            data = {}
    data[str(day)] = {
        'day': day,
        'day_brief': brief,
        'scene_intro': intro,
        'beats': beats or [],
        'shots': shots or [],
        'story': story,
        'problems': problems or [],
        'source': 'ai',
    }
    p.write_text(_json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return p


def mk_scene_rich(run: Path, day: int, rows: list[dict]) -> Path:
    """造一天**带事件/张力/换场**的幕：`rows` 每项 `{time, place, node, t0, t1, events, cast}`。

    详细剧情的转折点全从这些字段里数出来（`event` 条目、`node` 变化、张力跳、`place` 变化），
    所以夹具必须能把它们单独摆出来 —— 只造"一句话的幕"是测不到判据的。
    """
    import json as _json
    from display import script as S
    from display import script_render as SR
    scenes = []
    for r in rows:
        entries = []
        for ev in (r.get('events') or []):
            entries.append(S.Entry(kind='event', text=ev.get('text', ''),
                                   caption=ev.get('caption', ''), priority=0))
        entries.append(S.Entry(kind='dialogue', speaker='甲', text='台词。'))
        scenes.append(S.SceneScript(
            time_label=r.get('time', '辰时 08:00'), place=r.get('place', '楼里'),
            node_name=r.get('node', ''), day=day, cast=r.get('cast') or ['甲'],
            tension_before=r.get('t0', 0.3), tension_after=r.get('t1', 0.3),
            entries=entries))
    p = run / '每天的生活' / f'第{day:03d}天.json'
    p.write_text(SR.to_json(scenes), encoding='utf-8')
    return p


def _style() -> SFD.FlowStyle:
    return SFD.FlowStyle(
        font='', body_fs=14, hint_fs=13.5,
        color={'gold': '#a8781f', 'accent': '#2f7fb0', 'muted': '#6a6f78',
               'seal': '#c02c22', 'text': '#232830', 'border': '#d9c9a3',
               'border_gold': '#c9a24e', 'panel': '#fdfaf2', 'paper_hi': '#fffdf6',
               'hover': '#f5ecd8'})


def _point(flow: dict, title: str) -> dict:
    return next((p for p in flow.get('points') or [] if p.get('title') == title), {})


def _texts(ctl) -> list[str]:
    """把一串控件里所有 `Text.value` 收上来（判"那句话在不在"）。"""
    out: list[str] = []

    def walk(c):
        if c is None:
            return
        if isinstance(c, ft.Text) and c.value:
            out.append(str(c.value))
        for attr in ('content', 'controls', 'actions'):
            v = getattr(c, attr, None)
            if isinstance(v, list):
                for x in v:
                    walk(x)
            else:
                walk(v)
    for x in (ctl if isinstance(ctl, list) else [ctl]):
        walk(x)
    return out


def _clickable_labels(ctl) -> list[str]:
    """一串控件里**能点**的胶囊上写了什么（选项）。"""
    out: list[str] = []

    def walk(c):
        if c is None:
            return
        if isinstance(c, ft.Container) and getattr(c, 'on_click', None):
            txt = getattr(c.content, 'value', None)
            if txt:
                out.append(str(txt))
        for attr in ('content', 'controls'):
            v = getattr(c, attr, None)
            if isinstance(v, list):
                for x in v:
                    walk(x)
            else:
                walk(v)
    walk(ctl)
    return out


def _click_one(ctl, label: str) -> bool:
    """点一个写了 `label` 的胶囊（真调它的 `on_click`）。"""
    done = {'hit': False}

    def walk(c):
        if c is None or done['hit']:
            return
        if (isinstance(c, ft.Container) and getattr(c, 'on_click', None)
                and str(getattr(getattr(c, 'content', None), 'value', '') or '') == label):
            c.on_click(None)
            done['hit'] = True
            return
        for attr in ('content', 'controls'):
            v = getattr(c, attr, None)
            if isinstance(v, list):
                for x in v:
                    walk(x)
            else:
                walk(v)
    walk(ctl)
    return done['hit']


# ══════════════════════════════════════════════════════════════
#  A. 选项：怎么来的、怎么记
# [EN] A. Options: where they come from, how a pick is recorded
# ══════════════════════════════════════════════════════════════
def a_choices() -> None:
    print('\n── A 选择点 ──')
    inf, inferred = PF.choice_options(
        {'summary': '阿九面对归籍、祭献、留门三条路，必须当众给出选择。'})
    ok('A1 ★★★ 概要用「A、B、C三条路」写法 ⇒ 读出**三个选项**，且标着"是推出来的"',
       [o['label'] for o in inf] == ['归籍', '祭献', '留门'] and inferred,
       str([o['label'] for o in inf]) + f' inferred={inferred}')

    own, own_inf = PF.choice_options({'summary': '随便什么。', 'options': ['走', '留']})
    ok('A2 ★★★ 作者写了 `选项:` 就用**他的**（顺序照原样），且不算推断',
       [o['label'] for o in own] == ['走', '留'] and not own_inf,
       str([o['label'] for o in own]) + f' inferred={own_inf}')

    none, _ = PF.choice_options({'summary': '他做了个选择，然后走了。'})
    ok('A3 ★★★ 读不出选项时**不许凭空造一个分叉**（直路上多一个选择点，用户会真去点）',
       none == [], str(none))

    five, _ = PF.choice_options({'summary': '他要在一、二、三、四、五这几个里挑，共五条路可选。'})
    ok('A4 ★★ 选项数超过 4 个 ⇒ 不认（那多半是句子里的并列，不是"选一条路"）',
       five == [], str([o['label'] for o in five]))

    data = {'points': [{'pid': 'P04', 'options': [{'label': '归籍'}, {'label': '留门'}]}]}
    PF.set_pick(data, 'P04', '飞升')
    kept = PF.pick_of(data, 'P04')
    PF.set_pick(data, 'P04', '留门')
    ok('A5 ★★★ 记选择只认**这一站真有的**选项（点了个不存在的标签不当真）',
       kept == '' and PF.pick_of(data, 'P04') == '留门',
       f'乱填后={kept!r} 正常后={PF.pick_of(data, "P04")!r}')

    PF.set_pick(data, 'P04', '')
    ok('A6 ★★★ 传空标签 = **取消**（选错了要能退回来，不然只有一个方向）',
       PF.pick_of(data, 'P04') == '', f'picks={data["picks"]}')

    p_br = {'options': [{'label': '归籍', 'points': [{'名称': '销籍', '概要': '名字从册上划掉。'}]},
                        {'label': '留门', 'points': []}]}
    ok('A7 ★★★ 选了哪条就从哪条往下接：`后续` 有就取出来、没有就是空（**不编结局**）',
       len(PF.branch_points_of(p_br, '归籍')) == 1
       and PF.branch_points_of(p_br, '留门') == [],
       f'归籍={len(PF.branch_points_of(p_br, "归籍"))} 留门={len(PF.branch_points_of(p_br, "留门"))}')


# ══════════════════════════════════════════════════════════════
#  B. 生成：谁演过、谁在演、实据
# [EN] B. Generation: who was played, who is playing, the evidence
# ══════════════════════════════════════════════════════════════
def b_build(tmp: Path) -> None:
    print('\n── B 生成 ──')
    proj = mk_project(tmp / '书')
    run = mk_run(proj)
    mk_day(run, 1, ['入楼收留'] * 3 + ['金华旧账'] * 2)
    f = PF.build_flow(proj, run)

    ok('B1 ★★★ 演过且已收尾 = **已演过**；最后一幕所在的站 = **正在演**；其余 = 还没演到',
       _point(f, '入楼收留').get('state') == PF.STATE_DONE
       and _point(f, '金华旧账').get('state') == PF.STATE_NOW
       and _point(f, '重走旧路').get('state') == PF.STATE_TODO,
       '/'.join(f'{p["title"]}:{p["state"]}' for p in f['points'][:3]))

    _p1, _p2 = _point(f, '入楼收留'), _point(f, '金华旧账')
    ok('B2 ★★★ 实据是**数出来的**（第 1 天 3 幕 / 2 幕），不是估的',
       (_p1.get('days'), _p1.get('scenes')) == ([1], 3)
       and (_p2.get('days'), _p2.get('scenes')) == ([1], 2)
       and SFD.detail_text(_p1) == '第 1 天 · 3 幕',
       f'{_p1.get("days")}/{_p1.get("scenes")} → {SFD.detail_text(_p1)}')

    ok('B2b ★★★ 数据里存的是**数字不是句子**（存"第 1 天 · 3 幕"就等于把中文冻进盘里，'
       '切英文这行还是中文）',
       'detail' not in _p1 and 'days' in _p1 and 'scenes' in _p1, str(sorted(_p1))[:80])

    ok('B3 ★★★ 选择点认出来了（开庭抉择），并且**标着是从概要里读的**',
       _point(f, '开庭抉择').get('kind') == 'choice'
       and _point(f, '开庭抉择').get('options_inferred') is True,
       f'{_point(f, "开庭抉择").get("kind")} inferred={_point(f, "开庭抉择").get("options_inferred")}')

    nodes = [dict(n) for n in _NODES]
    nodes[2]['状态'] = '已完成'
    proj2 = mk_project(tmp / '书2', nodes)
    run2 = mk_run(proj2)
    mk_day(run2, 1, ['入楼收留'])
    f2 = PF.build_flow(proj2, run2)
    p3 = _point(f2, '重走旧路')
    ok('B4 ★★★ 设定集说"已完成"、而**这次没演到** ⇒ 仍是"还没演到"，并写明原因',
       p3.get('state') == PF.STATE_TODO and p3.get('unplayed_done') is True
       and '没演到' in SFD.detail_text(p3),
       f'{p3.get("state")} / {SFD.detail_text(p3)}')

    run3 = mk_run(proj, '第2次模拟2026-01-02-00-00')
    (run3 / '每天的生活' / '第001天.md').write_text('# 第 1 天 · 辰时\n\n正文。\n', encoding='utf-8')
    f3 = PF.build_flow(proj, run3)
    ok('B5 ★★★ 只有 `.md` 的老运行 ⇒ **一天都不算**（宁可说"还没演到"，不许猜）',
       f3['stats']['days'] == 0 and all(p['state'] == PF.STATE_TODO for p in f3['points']),
       str(f3['stats']))

    ok('B6 ★★ 数字自洽：`stats.played` = 状态不是"还没演到"的站数',
       f['stats']['played'] == sum(1 for p in f['points']
                                   if p['state'] in (PF.STATE_DONE, PF.STATE_NOW)),
       str(f['stats']))

    empty = tmp / '空项目'
    empty.mkdir()
    f4 = PF.build_flow(empty, mk_run(empty))
    ok('B7 ★★★ 设定集里没有情节表时**说清楚**（不留白屏、也不假装有故事）',
       not f4['points'] and f4.get('tail') == 'no_table'
       and '故事进度' in SFD.tail_text(f4),
       f'{f4.get("tail")} / {SFD.tail_text(f4)[:30]}')


# ══════════════════════════════════════════════════════════════
#  C. 存取：旧了就重算、重算不许覆盖选择
# [EN] C. Persistence: recompute when stale, never overwrite picks
# ══════════════════════════════════════════════════════════════
def c_store(tmp: Path) -> None:
    print('\n── C 存取 ──')
    proj = mk_project(tmp / '存取')
    run = mk_run(proj)
    mk_day(run, 1, ['入楼收留', '金华旧账'])

    first = PF.ensure_flow(proj, run)
    ok('C1 ★★ 第一次调用会**落盘**（盘上没有就生成一份）',
       PF.flow_path(run).is_file(), str(PF.flow_path(run)))

    again = PF.ensure_flow(proj, run)
    ok('C2 ★★★ 素材没变就**直接用盘上那份**（不重写 —— 否则"更新于"每秒都在跳）',
       again.get('generated_at') == first.get('generated_at'),
       f'{first.get("generated_at")} → {again.get("generated_at")}')

    d = PF.load_flow(run)
    PF.set_pick(d, 'P04', '留门')
    PF.save_flow(run, d)

    import os
    import time
    time.sleep(0.01)
    mk_day(run, 2, ['重走旧路'])
    os.utime(PF.flow_path(run), (time.time() - 10, time.time() - 10))   # 让文件"变旧"
    f2 = PF.ensure_flow(proj, run)
    ok('C3 ★★★ 素材变新（又演了一天）⇒ **重算**，新的一天出现在 days 里',
       f2['stats']['days'] == 2, str(f2['stats']))

    ok('C3b ★★★ **重算不许清掉用户选过的分支**（清掉了就是"我选的线第二天没了"）',
       PF.pick_of(f2, 'P04') == '留门', f'picks={f2.get("picks")}')

    PF.flow_path(run).write_text('{ 这不是 json', encoding='utf-8')
    try:
        f3 = PF.ensure_flow(proj, run)
        good = f3['stats']['days'] == 2
    except Exception as e:                                       # noqa: BLE001
        good, f3 = False, {'err': repr(e)}
    ok('C4 ★★★ 文件坏了 ⇒ **当没有、重算一份**（不许让对话框打不开）', good, str(f3)[:80])

    d4 = PF.load_flow(run)
    d4['schema'] = PF.SCHEMA + 5
    PF.save_flow(run, d4)
    ok('C5 ★★ 文件是**更新版本**写的（schema 更大）⇒ 不猜它能读，按"没有"处理',
       PF.load_flow(run) is None, '')


# ══════════════════════════════════════════════════════════════
#  D. 控件：连不连、能不能点、没后续说什么
# [EN] D. Controls: connected, clickable, what it says with no branch
# ══════════════════════════════════════════════════════════════
def d_controls(tmp: Path) -> None:
    print('\n── D 控件 ──')
    proj = mk_project(tmp / '控件')
    run = mk_run(proj)
    mk_day(run, 1, ['入楼收留', '金华旧账'])
    f = PF.build_flow(proj, run)
    st = _style()

    rows = SFD.build_flow_controls(f, style=st, picks={}, on_pick=lambda a, b: None)
    cards = [r for r in rows if isinstance(r, ft.Row) and len(r.controls) == 2]
    ok('D1 ★★ 每一站一张卡（4 站 ⇒ 4 张），左轨道 + 卡片成对出现',
       len(cards) == len(f['points']), f'{len(cards)} 张 / {len(f["points"])} 站')

    cons = [r for r in rows if isinstance(r, ft.Row) and len(r.controls) == 1]
    ok('D2 ★★★ 卡片之间**有竖线连接**（N 站之间 N-1 段 —— 断开的一列不是"流程"）',
       len(cons) == max(0, len(f['points']) - 1),
       f'{len(cons)} 段 / 应有 {max(0, len(f["points"]) - 1)} 段')

    choice_rows = [r for r in rows if '开庭抉择' in ' '.join(_texts(r))]
    labels: list[str] = []
    for r in choice_rows:
        labels += _clickable_labels(r)
    ok('D3 ★★★ 选择点上是**三个可点的选项**（多选一，点了就往下走）',
       labels == ['归籍', '祭献', '留门'], str(labels))

    got: list[tuple] = []
    rows2 = SFD.build_flow_controls(f, style=st, picks={},
                                    on_pick=lambda pid, lb: got.append((pid, lb)))
    hit = any(_click_one(r, '归籍') for r in rows2 if '开庭抉择' in ' '.join(_texts(r)))
    ok('D4 ★★★ 点一下选项 ⇒ 回调拿到 `(站号, 选项名)`（界面才知道该记哪条）',
       hit and got and got[0] == ('P04', '归籍'), f'hit={hit} got={got}')

    f_pick = dict(f)
    f_pick['picks'] = {'P04': '留门'}
    t_sel = ' '.join(_texts(SFD.build_flow_controls(f_pick, style=st)))
    t_raw = ' '.join(_texts(SFD.build_flow_controls(f, style=st)))
    ok('D5 ★★★ 未选时说"点一条，从这里往下看"；选了之后换成"沿「留门」这条线往下看"',
       '点一条' in t_raw and '沿「留门」这条线往下看' in t_sel,
       f'未选={"点一条" in t_raw} 已选={"沿「留门」" in t_sel}')

    ok('D6 ★★★ 选了但没有后续情节 ⇒ **明说"还没演到"**（绝不编一个结局出来）',
       '这条线后面的事还没演到' in t_sel, '')

    f_br = {'points': [{'pid': 'P1', 'title': '开庭抉择', 'kind': 'choice', 'state': 'todo',
                        'summary': '选一条。', 'detail': '',
                        'options': [{'label': '归籍',
                                     'points': [{'名称': '销籍', '概要': '名字从册上划掉。'}]}],
                        'options_inferred': False}],
            'picks': {'P1': '归籍'}, 'synopsis': ''}
    t_br = ' '.join(_texts(SFD.build_flow_controls(f_br, style=st)))
    ok('D7 ★★★ 选项带了 `后续` ⇒ 接在选中那条线下面（"从用户选择的剧情继续流程"）',
       '销籍' in t_br, t_br[:60])


# ══════════════════════════════════════════════════════════════
#  E. 接线：三个入口 + 两处自动刷新
# [EN] E. Wiring: three entries + two automatic refreshes
# ══════════════════════════════════════════════════════════════
def e_wiring() -> None:
    print('\n── E 接线 ──')
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    loop = (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')

    ok('E1 ★★★ 剧情面板的**标题**是入口（`goto=self._open_story_flow`）—— '
       '这是本项目所有面板统一的"点标题进详情"',
       'goto=self._open_story_flow' in src, '')

    ok('E2 ★★★ **站名胶囊**也能点（用户想看图，手自然落在写着站名的那一块）',
       src.count('on_click=self._open_story_flow') >= 2,
       f'出现 {src.count("on_click=self._open_story_flow")} 次')

    ok('E3 ★★★ 跑马灯那一行**多了一个总览按钮**（看得见的独立按钮，才有人敢点）',
       'plot_prev_btn, plot_chip, plot_next_btn, plot_flow_btn' in src, '')

    ok('E4 ★★★ 推演循环在**日界**与**收工**两处自动刷新（后续数据由软件自己生成）',
       loop.count('_refresh_story_flow') >= 3 and 'def _refresh_story_flow' in loop,
       f'引用 {loop.count("_refresh_story_flow")} 次')

    _fn = loop.split('def _refresh_story_flow')[1].split('\n    def ')[0]
    ok('E5 ★★★ 刷新是**零 LLM** 的（只读盘；让模型总结会把"查看"变成付费动作）',
       'PF.ensure_flow' in _fn and 'ask(' not in _fn, '')

    ok('E6 ★★★ 对话框的跑马灯**复用** `plot_carousel_step`（两处各写一遍，'
       '早晚一处循环一处到头停）',
       "state['idx'] = plot_carousel_step(" in src, '')

    uie = (APP_DIR / 'tools' / 'verify_ui_english.py').read_text(encoding='utf-8')
    ok('E7 ★★★ 这个对话框进了**英文判据的清单**（没进 ⇒ 整窗硬编码中文也没人守，'
       '`show_usage_dialog` 就是这么漏的）',
       "'_open_story_flow'" in uie, '')

    ok('E8 ★★ 回填脚本走的是**同一个** `ensure_flow`（脚本自己算一遍 ⇒ '
       '补出来的图和界面不一样）',
       'PF.ensure_flow' in (APP_DIR / 'tools' / 'build_story_flow.py').read_text(encoding='utf-8'),
       '')

    ok('E9 ★★★ 判据文件名**不叫** `verify_story_flow`（那个名字是"中栏故事体"的，'
       '同名不同事会让跑全量的人以为这条也被守住了）',
       Path(__file__).name == 'verify_plot_overview.py', Path(__file__).name)


# ══════════════════════════════════════════════════════════════
#  F. 反例：就地改坏，确认对应那条会红
# [EN] F. Counterexamples: break it in place, confirm the matching check goes red
# ══════════════════════════════════════════════════════════════
def f_counter(tmp: Path) -> None:
    print('\n── F 反例（就地改坏，跑完还原）──')
    orig_build = PF.build_flow

    def broken_state(project_dir, run_root, *, picks=None):
        """变异①：把"设定集已完成但这天没演到"错画成"正在演" ⇒ B4 会红。"""
        data = orig_build(project_dir, run_root, picks=picks)
        for p in data['points']:
            if p['state'] == PF.STATE_TODO and p.get('unplayed_done') is True:
                p['state'] = PF.STATE_NOW
        return data

    nodes = [dict(_NODES[0]), dict(_NODES[2], 状态='已完成')]
    proj = mk_project(tmp / '反例', nodes)
    run = mk_run(proj)
    mk_day(run, 1, ['入楼收留'])
    try:
        PF.build_flow = broken_state
        bad = PF.build_flow(proj, run)
    finally:
        PF.build_flow = orig_build
    p = next(x for x in bad['points'] if x['title'] == '重走旧路')
    ok('F1 ★★★ 反例①：把"设定集已完成、这次没演到"错画成"正在演" ⇒ B4 那条会红',
       not (p['state'] == PF.STATE_TODO and p.get('unplayed_done') is True),
       f'变异后 state={p["state"]} unplayed_done={p.get("unplayed_done")}')

    def drop_picks(project_dir, run_root, *, picks=None):
        """变异②：重算时不带 picks ⇒ C3b 会红。"""
        return orig_build(project_dir, run_root, picks={})

    proj2 = mk_project(tmp / '反例2')
    run2 = mk_run(proj2)
    mk_day(run2, 1, ['入楼收留'])
    f0 = PF.ensure_flow(proj2, run2)
    PF.set_pick(f0, 'P04', '留门')
    PF.save_flow(run2, f0)
    try:
        PF.build_flow = drop_picks
        f1 = PF.ensure_flow(proj2, run2, force=True)
    finally:
        PF.build_flow = orig_build
    ok('F2 ★★★ 反例②：重算时**不带 picks** ⇒ C3b 会红（"选的线第二天没了"）',
       PF.pick_of(f1, 'P04') == '', f'重算后 picks={f1.get("picks")}')

    # 变异③：把"没后续时那句话"去掉 ⇒ D6 会红。就地改 SFD 的那句文案。
    orig_txt = '（这条线后面的事还没演到）'
    src_patch = SFD.__file__
    raw = Path(src_patch).read_text(encoding='utf-8')
    try:
        Path(src_patch).write_text(
            raw.replace(f"t('{orig_txt}')", "t('（已删）')"), encoding='utf-8')
        import importlib
        importlib.reload(SFD)
        f_br = {'points': [{'pid': 'P1', 'title': '开庭抉择', 'kind': 'choice', 'state': 'todo',
                            'summary': '选一条。', 'detail': '', 'options_inferred': False,
                            'options': [{'label': '归籍', 'points': []}]}],
                'picks': {'P1': '归籍'}, 'synopsis': ''}
        t_br = ' '.join(_texts(SFD.build_flow_controls(f_br, style=_style())))
    finally:
        Path(src_patch).write_text(raw, encoding='utf-8')
        import importlib
        importlib.reload(SFD)
    ok('F3 ★★★ 反例③：删掉"这条线后面还没演到"那句 ⇒ D6 会红（用户会以为图画断了）',
       '这条线后面的事还没演到' not in t_br, t_br[:60])


# ══════════════════════════════════════════════════════════════
#  H. 详细层的反例（就地改坏三处）
# [EN] H. Counterexamples for the detail layer
# ══════════════════════════════════════════════════════════════
def h_detail_counter(tmp: Path) -> None:
    print('\n── H 详细层反例（就地改坏，跑完还原）──')
    proj = mk_project(tmp / 'H')
    run = mk_run(proj)
    mk_scene_rich(run, 1, [
        {'time': '辰时 08:30', 'place': '楼里', 'node': '入楼收留', 't0': .30, 't1': .44},
        {'time': '午时 11:00', 'place': '楼里', 'node': '入楼收留', 't0': .44, 't1': .44,
         'events': [{'text': '牌背旧痕露出半个忘字。', 'caption': '秘密泄露'}]},
        {'time': '戌时 19:00', 'place': '院子', 'node': '金华旧账', 't0': .45, 't1': .70},
    ])
    mk_script(run, 1, beats=[{'拍': 1, '主题': '传话', '发生': 'x'}],
              story='第一段。\n\n第二段。')

    # 反例①：不读 `event` 条目 ⇒ 最大的那类转折全丢（G5/G7 会红）
    orig_marks = PF._marks_of

    def no_event(scenes, prev_node='', prev_cast=None):
        out, seen, node = orig_marks(scenes, prev_node, prev_cast)
        return [m for m in out if m.get('why') != 'event'], seen, node
    try:
        PF._marks_of = no_event
        f1 = PF.build_flow(proj, run)
    finally:
        PF._marks_of = orig_marks
    whys1 = [m.get('why') for m in (f1.get('detail') or {}).get('turns') or []]
    ok('H1 ★★★ 反例①：不读导演事件 ⇒ **转折少一整类**（G5 的集合相等立刻红）',
       'event' not in whys1, str(sorted(set(whys1))))

    # 反例②：把张力阈值调到不可能 ⇒ `tension` 那条再也数不出来（G5 会红）
    saved_thr = PF.TURN_TENSION
    try:
        PF.TURN_TENSION = 9.9
        f2 = PF.build_flow(proj, run)
    finally:
        PF.TURN_TENSION = saved_thr
    whys2 = [m.get('why') for m in (f2.get('detail') or {}).get('turns') or []]
    ok('H2 ★★★ 反例②：张力阈值调到 9.9 ⇒ `tension` 那条消失（G5 会红）',
       'tension' not in whys2, str(sorted(set(whys2))))

    # 反例③：让数据层又去拼中文句子 ⇒ G8 会红（这是上一轮踩过的那个坑）
    orig_scan = PF.scan_detail

    def baked(project_dir, run_root, *, days=None):
        d = orig_scan(project_dir, run_root, days=days)
        for m in d.get('turns') or []:
            if m.get('why') in ('place', 'node', 'tension') and not m.get('text'):
                m['text'] = '换场：甲 → 乙'
        return d
    try:
        PF.scan_detail = baked
        f3 = PF.build_flow(proj, run)
    finally:
        PF.scan_detail = orig_scan
    bad = [m for m in (f3.get('detail') or {}).get('turns') or []
           if m.get('why') in ('place', 'node', 'tension') and m.get('text')]
    ok('H3 ★★★ 反例③：数据层又去拼中文句子 ⇒ G8 会红'
       '（切英文那几行还是中文 —— 上一轮 `detail`/`tail` 就这么栽过）',
       bool(bad), str([str(x.get('text'))[:12] for x in bad[:2]]))


# ══════════════════════════════════════════════════════════════
#  G. 详细剧情（2026-10-26 第二轮：用户嫌总览太简略）
# [EN] G. Detailed story (round two: the user found the overview too brief)
# ══════════════════════════════════════════════════════════════
def g_detail(tmp: Path) -> None:
    """**详细到剧作家的小段**：分拍读到了、正文读到了、转折点数出来了、不上限不炸。

    用户 2026-10-26：「剧情总览太简略了 我希望是每次推演里面的**细节剧情** 要很详细
    （到达每次剧作家写**小段剧情**的程度）要包含当前这次推演的**关键剧情和转折点**」
    """
    print('\n── G 详细剧情 ──')
    proj = mk_project(tmp / 'G')
    run = mk_run(proj)

    # 一天 6 幕：有事件、有站切换、有张力大跳、有换场
    mk_scene_rich(run, 1, [
        {'time': '辰时 08:30', 'place': '楼里', 'node': '入楼收留', 't0': .30, 't1': .44},
        {'time': '午时 11:00', 'place': '楼里', 'node': '入楼收留', 't0': .44, 't1': .44,
         'events': [{'text': '牌背旧痕露出半个忘字。', 'caption': '秘密泄露'}]},
        {'time': '申时 15:30', 'place': '院子', 'node': '入楼收留', 't0': .44, 't1': .45},
        {'time': '戌时 19:00', 'place': '院子', 'node': '金华旧账', 't0': .45, 't1': .70},
    ])
    mk_script(run, 1,
              brief='阿九挂上牌子，接了扫院的差事。',
              intro='楼下一进院子，井在院中间。',
              beats=[
                  {'拍': 1, '场': '望江楼·灶房（屋里）', '主题': '阿贵传话',
                   '出场': ['阿九', '阿贵'], '发生': '阿九喝完碗底最后一口。',
                   '要点': ['他放下碗。', '阿贵抬头说掌柜找他。'],
                   '推进': '从闲人变成有差事的人', '目标': '把话传到',
                   '情绪': '半醒', '道具': ['碗'], '难题': '门口堵着柴垛'},
                  {'拍': 2, '场': '望江楼·老陈屋（屋里）', '主题': '老陈交代规矩',
                   '出场': ['阿九', '老陈'], '发生': '老陈让他先揭瓦。',
                   '要点': ['老陈修竹签。'], '推进': '知道规矩', '目标': '搬箱',
                   '情绪': '平静', '道具': [], '难题': ''},
              ],
              shots=[
                  {'镜': 1, '拍': 1, '景别': '中景', '画面': '灶房内，阿九仰头喝净碗底。',
                   '台词': '白天不用守柜台。', '叙事点': '阿九被支去搬箱。'},
              ],
              story='阿九把碗里最后一口米汤灌下去。\n\n“哪摞？”\n\n阿贵拿火钳往灶膛里一捅。',
              problems=['第 1 拍传话太顺，可以让他先漏说一句。'])

    f = PF.build_flow(proj, run)
    det = f.get('detail') or {}
    day = (det.get('days') or [{}])[0]

    ok('G1 ★★★ 分拍读到了 —— 那是**剧作家交付的最小叙事单元**'
       '（场/主题/发生/要点/推进），不是界面自己编的概要',
       len(day.get('beats') or []) == 2
       and day['beats'][0].get('theme') == '阿贵传话'
       and day['beats'][0].get('happen') == '阿九喝完碗底最后一口。'
       and len(day['beats'][0].get('points') or []) == 2,
       f'{len(day.get("beats") or [])} 拍 / 首拍={day["beats"][0].get("theme") if day.get("beats") else "-"}')

    ok('G2 ★★★ **正文**按段读到了（这是"细节剧情"的本体）',
       len(day.get('story') or []) == 3
       and '哪摞' in (day.get('story') or [''])[1],
       f'{len(day.get("story") or [])} 段')

    ok('G3 ★★★ 分镜读到了（画面/台词各就各位）',
       len(day.get('shots') or []) == 1
       and day['shots'][0].get('size') == '中景'
       and day['shots'][0].get('frame', '').startswith('灶房内'),
       str((day.get('shots') or [{}])[0])[:70])

    ok('G4 ★★★ 当天梗概与场景介绍都在（作者写的那两句）',
       '扫院' in str(day.get('brief')) and '井在院中间' in str(day.get('intro')),
       f'{str(day.get("brief"))[:24]} / {str(day.get("intro"))[:20]}')

    # ── 转折点：四条判据各自能单独触发 ──
    turns = det.get('turns') or []
    whys = [m.get('why') for m in turns]
    ok('G5 ★★★ 四个转折判据**各自都数得出**：`event`（导演事件）/ `node`（站切换）/ '
       '`tension`（张力大跳）/ `place`（换场）',
       set(whys) == {'event', 'node', 'tension', 'place'}, str(sorted(set(whys))))

    ok('G6 ★★★ `event` 归**转折**（direction 变了），其余三个归**关键**'
       '（只是火候变了）—— 混成一档会让"转折点"这个词失去意义',
       all(m.get('kind') == PF.MARK_TURN for m in turns if m.get('why') == 'event')
       and all(m.get('kind') == PF.MARK_KEY for m in turns
               if m.get('why') in ('tension', 'place')),
       str([(m.get('why'), m.get('kind')) for m in turns]))

    ok('G7 ★★★ 导演事件的**原文与类别**都留下来了（不是"某某事件"这种概括）',
       any('忘字' in str(m.get('text')) and m.get('caption') == '秘密泄露'
           for m in turns),
       next((str(m.get('text'))[:30] for m in turns if m.get('why') == 'event'), ''))

    # ── ★★★ 不冻语言：数据层只给代码与参数 ──
    _bad = []
    for m in turns:
        if m.get('why') in ('place', 'node', 'tension'):
            if m.get('text'):
                _bad.append(str(m['text'])[:20])
        if m.get('why') == 'place' and not ('a' in m and 'b' in m):
            _bad.append('place 缺 a/b')
        if m.get('why') == 'tension' and not ('a' in m and 'b' in m):
            _bad.append('tension 缺 a/b')
    ok('G8 ★★★ **数据里不许存拼好的中文句子**（换场/站切换/张力只给代码+参数，'
       '排版归界面）—— 否则切英文那几行还是中文',
       not _bad, str(_bad[:3]))

    # 界面按当前语言拼得出来（中英各一次）
    import i18n as I18N
    _zh = [SFD.mark_text(m) for m in turns if m.get('why') in ('place', 'node', 'tension')]
    I18N.set_lang('en')
    try:
        _en = [SFD.mark_text(m) for m in turns if m.get('why') in ('place', 'node', 'tension')]
    finally:
        I18N.set_lang('zh')
    # ⚠ 判的是**模板翻了没有**，不是"整句没有中文"：站名与地名是**用户素材**
    #   （"金华旧账"是这本书的站名），英文界面里它们本来就该保持原样。
    #   第一版判"整句无 CJK"，于是 `Plot advances to 「金华旧账」` 被判红 ——
    #   那会把"素材里带中文"和"文案没翻"混成一件事。
    # [EN] Judge **whether the template got translated**, not "the whole line has no CJK": station
    # [EN] and place names are **user material** and must stay as-is in an English UI. The first
    # [EN] version required zero CJK, so `Plot advances to 「金华旧账」` went red -- conflating
    # [EN] "material contains Chinese" with "copy not translated".
    _TEMPLATES_ZH = ('情节推进到', '换场：', '张力 ')
    ok('G9 ★★★ 同一份数据，**英文界面拼得出英文**（模板真的翻了，只剩站名/地名这类素材是原文）',
       bool(_zh) and not any(any(w in x for w in _TEMPLATES_ZH) for x in _en)
       and any(w in ' '.join(_en) for w in ('Plot advances', 'Change of place', 'Tension')),
       f'中={_zh[:1]} 英={_en[:1]}')

    # ── 界面上真的有这些控件 ──
    st = _style()
    rows = SFD.build_detail_controls(f, style=st)
    txt = ' '.join(_texts(rows))
    ok('G10 ★★★ 详细页面上**有关键剧情与转折点那一块**（结论先行，不埋在第 8 天里）',
       '关键剧情与转折点' in txt, '')
    ok('G11 ★★★ 详细页面上**有剧作家的分拍**与**正文**两块（小节标题带数量）',
       '剧作家的分拍' in txt and '正文' in txt, '')
    ok('G12 ★★ 当天的梗概与场景介绍也在（一看就知道这一天讲什么）',
       '当天梗概' in txt and '场景：' in txt, '')
    import flet as _ft
    ok('G13 ★★ 折叠控件用的是**重建**（`_render`），不是 `visible=False` —— '
       '后者在 3000 个控件时照样先渲染一遍，等于没省',
       '_render(open_now' in (APP_DIR / 'gui' / 'story_flow_dialog.py').read_text(encoding='utf-8')
       or 'def _render(open_now' in (APP_DIR / 'gui' / 'story_flow_dialog.py').read_text(encoding='utf-8'),
       '')

    # ── 读不出底稿时仍然给"按天 + 标记"（老运行照样能看）──
    proj2 = mk_project(tmp / 'G2')
    run2 = mk_run(proj2)
    mk_scene_rich(run2, 1, [{'time': '辰时 08:30', 'node': '入楼收留', 't0': .3, 't1': .3}])
    f2 = PF.build_flow(proj2, run2)
    d2 = (f2.get('detail') or {}).get('days') or [{}]
    ok('G14 ★★★ 没有 `当日剧本.json`（老运行）⇒ 仍给**按天 + 幕数**，'
       '只是没有分拍与正文（不许整块消失）',
       len(d2) == 1 and int(d2[0].get('scenes') or 0) == 1
       and not d2[0].get('beats') and not d2[0].get('story'),
       f'{len(d2)} 天 / {d2[0].get("scenes")} 幕 / beats={len(d2[0].get("beats") or [])}')

    # ── 一天很多幕也不炸（上限）──
    proj3 = mk_project(tmp / 'G3')
    run3 = mk_run(proj3)
    mk_scene_rich(run3, 1, [{'time': f'辰时 {8 + i:02d}:00', 'node': '入楼收留',
                             't0': .3, 't1': .3} for i in range(60)])
    mk_script(run3, 1, beats=[{'拍': i + 1, '主题': f'第{i + 1}拍', '发生': 'x'} for i in range(60)],
              story='\n\n'.join(f'第{i}段。' for i in range(300)))
    f3 = PF.build_flow(proj3, run3)
    d3 = ((f3.get('detail') or {}).get('days') or [{}])[0]
    ok('G15 ★★ 异常长的一天会**截断并说明**（`另有 N 拍未收录`），不是静默截断',
       len(d3.get('beats') or []) <= PF.MAX_BEATS_DAY
       and len(d3.get('story') or []) <= PF.MAX_STORY_PARAS
       and any('未收录' in str(x) for x in (d3.get('notes') or [])),
       f'{len(d3.get("beats") or [])} 拍 / {len(d3.get("story") or [])} 段 / {d3.get("notes")}')


def main() -> int:
    print('=' * 62)
    print('  剧情总览（流程图）验证')
    print('=' * 62)
    tmp = Path(tempfile.mkdtemp(prefix='nws_flow_'))
    try:
        for fn in (a_choices, e_wiring):
            try:
                fn()
            except Exception as e:                               # noqa: BLE001
                ok(f'{fn.__name__} 跑完', False, repr(e))
                print(traceback.format_exc()[-700:])
        for fn in (b_build, c_store, d_controls, f_counter, g_detail, h_detail_counter):
            try:
                fn(tmp)
            except Exception as e:                               # noqa: BLE001
                ok(f'{fn.__name__} 跑完', False, repr(e))
                print(traceback.format_exc()[-700:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n剧情总览验证：{good}/{n}')
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'plot_overview_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass
    return 0 if good == n else 2


if __name__ == '__main__':
    raise SystemExit(main())
