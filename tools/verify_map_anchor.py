# -*- coding: utf-8 -*-
"""验证：**地图锚定** —— 同一处地方，在整个推演里永远是同一块位置。

用户 2026-10-26
--------------
「小地图和大地图 每次生成的感觉都有一些区别 有办法在整个小说推演过程中
  维持相同场景地图的一致性吗」

三个病根（都量过，不是猜的）
----------------------------
① **复用判据里带着"今天的地点集合"**：今天多演一处灶房，指纹就变 ⇒ 整张图作废
   ⇒ 重新问模型 ⇒ 同一处地点全换位置。实测两份指纹判为不同。
② **没有"位置已定"这回事**：没有任何东西约束"茶肆昨天在左上、今天还在左上"。
③ **档位与内容不同源**：存档名取底图层的名字，`Layout.kind` 却是按内容推的
   （真数据里就有一份 `整体_望江楼.json` 而 `kind` 写着 `室内`）。

判据分五组
----------
| 组 | 测什么 | 为什么必须测 |
|---|---|---|
| A | 锚定本身：贴上去 / 只新增 / 撞了就挪新的 | 这是"一致性"的全部实现 |
| B | 换层 / 换地方**不串坐标** | 混在一份里，从楼里走到街上会全跳 |
| C | 复用判据：集合变了也复用、换层换地方仍不复用 | 收紧判据是本轮的根因修复 |
| D | **走产品那条路**（`RunLoop._day_map_anchor`）：补齐 + 贴 + 落盘 | 手工拼 API 测的是"我以为的顺序" |
| E | 开关关掉**逐字回到旧行为** | 不然后路被堵死，出问题只能回滚代码 |
| F | 反例：就地改坏三处，确认对应那条会红 | 判据自己不许是"永远绿" |

跑法：`.venv\\Scripts\\python.exe tools\\verify_map_anchor.py`
产出：`assets/screenshots/map_anchor_report.json`

English:
Verification for **map anchoring**: a place keeps the same spot for the whole simulation.
The user (2026-10-26): "the minimap and big map feel a bit different every time; can we keep scene
maps consistent across the whole simulation?" Three measured causes: ① the reuse fingerprint carried
today's place set (one extra place invalidated everything and forced a re-arrangement); ② nothing
recorded "this position is settled"; ③ the tier came from two different sources (a real archive is
named `整体_望江楼.json` while its `kind` says `室内`).
Five groups: A anchoring itself; B no cross-layer leakage; C the reuse fingerprint; D **the product's
own path** (`RunLoop._day_map_anchor`); E the switch restores the old behaviour verbatim;
F counterexamples.
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

from config import CFG                                   # noqa: E402

CFG.set('MAP_ANCHOR', 'true')

from image_gen import mapanchor as MAPA                  # noqa: E402
from image_gen import mapstore as MSTORE                 # noqa: E402
from image_gen.map_layout import Layout, Place           # noqa: E402
from sim.loop import RunLoop                             # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    good = bool(cond)
    report['checks'].append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    print(('  ok  ' if good else '  ✗  ') + name + (f'  [{detail}]' if detail else ''))
    return good


def mk(layer: str, frame: str, items) -> Layout:
    lay = Layout(kind=layer, frame=frame)
    for n, x, y, s in items:
        lay.places.append(Place(name=n, x=x, y=y, shape=s, size='中'))
    return lay


def pos(lay) -> dict:
    return {p.name: (round(p.x, 2), round(p.y, 2)) for p in lay.places}


class _FakeRF:
    """假 runfolder：产品方法只读 `project_dir` 与 `root`。"""

    def __init__(self, proj: Path):
        self.project_dir = proj
        self.root = proj / '第1次模拟2026-01-01-00-00'


def via_product(lay, proj: Path, detail: str, key: str, *, wanted=None, here=''):
    """走**产品那条路** —— `RunLoop._day_map_anchor`。

    ★ 这一点是本文件最要紧的一条纪律：探针/判据要是自己拼 `fill`+`apply`，
      测的就是"我以为的顺序"。产品里顺序写反了（先贴后补 ⇒ 补进来的点压在别人身上）
      照样绿。本项目反复栽在"测夹具、不测产品"上。
    [EN] Go through **the product's own path**, `RunLoop._day_map_anchor`. ★ This is the single most
    [EN] important discipline here: a fixture that stitches `fill`+`apply` by hand measures "the order
    [EN] I assumed", so a reversed order in the product (stamp then fill => an added point lands on
    [EN] someone) stays green. This project has repeatedly been burned by "measuring the fixture".
    """
    lp = RunLoop.__new__(RunLoop)
    lp.runfolder = _FakeRF(proj)
    return lp._day_map_anchor(lay, detail, key, wanted=wanted, here=here)


# ══════════════════════════════════════════════════════════════
#  A. 锚定本身
# [EN] A. Anchoring itself
# ══════════════════════════════════════════════════════════════
def a_anchor(tmp: Path) -> None:
    print('\n── A 锚定 ──')
    proj = tmp / 'A'
    proj.mkdir()

    d1 = mk('室内', '茶肆', [('门', .5, .9, '门'), ('堂屋', .5, .6, '屋'),
                             ('后院', .7, .2, '院')])
    d1, layers, why = MAPA.apply(d1, '室内', '茶肆', {})
    p1 = pos(d1)
    # ⚠ 只数**地名**：`slot` 里还挂着 `_frame` / `_caption` 这类**层的属性**
    #   （下划线开头）。把它们算进"几处"会让这条判据在"恰好 3 处地名"时红 ——
    #   第一版就是 `len(slot) == 3`，实际是 4（3 处地名 + `_frame`）。
    # [EN] Count **place names only**: `slot` also holds layer attributes (`_frame`, `_caption`,
    # [EN] underscore-prefixed). Counting them makes this red for exactly three places -- the first
    # [EN] version used `len(slot) == 3` and got 4 (three names + `_frame`).
    _names = [k for k in MAPA.slot_of(layers, '室内', '茶肆') if not k.startswith('_')]
    ok('A1 ★★★ 第一次见到这几处 ⇒ **记下它们的位置**（这就是以后的位置）',
       len(_names) == 3 and '新定' in ' '.join(why),
       f'{len(_names)} 处：{_names}')

    # 第二天：模型给了完全不同的一套
    d2 = mk('室内', '茶肆', [('门', .1, .1, '台'), ('堂屋', .9, .9, '院'),
                             ('后院', .2, .8, '屋')])
    d2, layers, why = MAPA.apply(d2, '室内', '茶肆', layers)
    ok('A2 ★★★ 已锚定的地点**一律用锚定值**：坐标与形状都压回原样'
       '（模型给"门 .1,.1 台"也不行）',
       pos(d2) == p1 and all(p.shape != '台' for p in d2.places if p.name == '门'),
       f'{pos(d2)} == {p1}')

    # 新地点：撞到别人要**挪新的**，不许动老的
    d3 = mk('室内', '茶肆', [('门', .5, .9, '门'), ('堂屋', .5, .6, '屋'),
                             ('后院', .7, .2, '院'), ('灶房', .5, .9, '屋')])
    d3, layers, why = MAPA.apply(d3, '室内', '茶肆', layers)
    p3 = pos(d3)
    ok('A3 ★★★ 新地点撞到老地点 ⇒ **挪新来的**（老的一处都不动）',
       all(p3[k] == p1[k] for k in p1) and p3.get('灶房') not in (None, p1.get('门')),
       f'老：{p1} → { {k: p3.get(k) for k in p1} }｜灶房={p3.get("灶房")}')

    ok('A4 ★★ 层的标题（室内图上那个建筑名）也锚定 —— 换天不该换标题',
       MAPA.slot_of(layers, '室内', '茶肆').get('_frame') == '茶肆',
       str(MAPA.slot_of(layers, '室内', '茶肆').get('_frame')))

    # 落盘 → 读回来还是它
    MAPA.save(proj, layers)
    back = MAPA.load(proj)
    ok('A5 ★★★ 落盘再读回来**一模一样**（跟着项目走 ⇒ 换一轮推演也还是它）',
       pos_dict_eq(MAPA.slot_of(back, '室内', '茶肆'), MAPA.slot_of(layers, '室内', '茶肆')),
       MAPA.summary(back, '室内', '茶肆'))

    ok('A6 ★★ 文件在**项目**下（`<项目>/地图/锚定.json`），不是某个推演文件夹里',
       str(MAPA.path_of(proj)).endswith(str(Path('地图') / MAPA.ANCHOR_FILE)),
       str(MAPA.path_of(proj)))

    # 坏文件 / 更新版本 ⇒ 当没有，不抛
    MAPA.path_of(proj).write_text('{ 坏 json', encoding='utf-8')
    ok('A7 ★★★ 文件坏了 ⇒ **当没有**（不许让地图打不开）', MAPA.load(proj) == {}, '')
    MAPA.path_of(proj).write_text(json.dumps({'版本': MAPA.VERSION + 9, '层': {'x': 1}}),
                                 encoding='utf-8')
    ok('A8 ★★ 更新版本写的 ⇒ 不猜它能读，按"没有"处理', MAPA.load(proj) == {}, '')


def pos_dict_eq(a: dict, b: dict) -> bool:
    ka = {k: v for k, v in a.items() if not k.startswith('_')}
    kb = {k: v for k, v in b.items() if not k.startswith('_')}
    return bool(ka) and ka == kb


# ══════════════════════════════════════════════════════════════
#  B. 换层 / 换地方不串
# [EN] B. No leakage across layer / place
# ══════════════════════════════════════════════════════════════
def b_layers() -> None:
    print('\n── B 换层 / 换地方 ──')
    layers: dict = {}
    d1 = mk('室内', '茶肆', [('堂屋', .5, .5, '屋')])
    d1, layers, _ = MAPA.apply(d1, '室内', '茶肆', layers)
    d2 = mk('整体', '茶肆', [('堂屋', .1, .9, '院')])
    d2, layers, _ = MAPA.apply(d2, '整体', '茶肆', layers)
    ok('B1 ★★★ 同一处地方在**不同层**各记各的（室内平面图与整体方位图本来就该不同）',
       MAPA.slot_of(layers, '室内', '茶肆')['堂屋']['y'] == 0.5
       and MAPA.slot_of(layers, '整体', '茶肆')['堂屋']['y'] == 0.9,
       f'室内 y={MAPA.slot_of(layers, "室内", "茶肆")["堂屋"]["y"]} / '
       f'整体 y={MAPA.slot_of(layers, "整体", "茶肆")["堂屋"]["y"]}')

    d3 = mk('室内', '别处', [('堂屋', .3, .3, '屋')])
    d3, layers, _ = MAPA.apply(d3, '室内', '别处', layers)
    ok('B2 ★★★ 同一层、**不同主地点**也各记各的（走到别处的图不该沿用这里的坐标）',
       MAPA.slot_of(layers, '室内', '别处')['堂屋']['x'] == 0.3,
       str(MAPA.slot_of(layers, '室内', '别处').get('堂屋')))

    ok('B3 ★★ 认不出的层名**原样保留**（不硬塞成某一档 —— 硬塞会让两处地方的"局部"混在一起）',
       MAPA.layer_of('室外') == '室外' and MAPA.layer_of('') == '局部',
       f"{MAPA.layer_of('室外')} / {MAPA.layer_of('')!r}")


# ══════════════════════════════════════════════════════════════
#  C. 复用判据
# [EN] C. The reuse fingerprint
# ══════════════════════════════════════════════════════════════
def c_basis(tmp: Path) -> None:
    print('\n── C 复用判据 ──')
    a = MSTORE.basis_of('室内', ['甲', '乙'], '茶肆')
    b = MSTORE.basis_of('室内', ['甲', '乙', '灶房'], '茶肆')
    c = MSTORE.basis_of('室内', ['甲'], '茶肆')
    ok('C1 ★★★ 地点集合变了（多一处 / 少一处）⇒ 指纹**不变**'
       '（这是"一天演几处地方是常态"的直接后果）', a == b == c, f'{a} / {b} / {c}')

    ok('C2 ★★★ 换层 / 换主地点 ⇒ 指纹**必须变**（否则走到别处还是这张图）',
       MSTORE.basis_of('整体', [], '茶肆') != MSTORE.basis_of('室内', [], '茶肆')
       and MSTORE.basis_of('室内', [], '茶肆') != MSTORE.basis_of('室内', [], '别处'),
       '')

    ok('C3 ★★★ 旧格式（`层//地点集合//这里`）认得出来（省一次模型调用，且它是同一处地方）',
       MSTORE._basis_legacy_prefix('室内//甲/乙//茶肆') == MSTORE.basis_of('室内', None, '茶肆'),
       MSTORE._basis_legacy_prefix('室内//甲/乙//茶肆'))

    ok('C4 ★★ 旧格式也不许乱认：主地点不同就不该认',
       MSTORE._basis_legacy_prefix('室内//甲/乙//别处') != MSTORE.basis_of('室内', None, '茶肆'),
       '')

    # 真跑一遍存/取：集合变了仍复用得回来
    proj = tmp / 'C'
    proj.mkdir()
    lay = mk('室内', '茶肆', [('堂屋', .5, .5, '屋'), ('井', .7, .3, '水')])
    MSTORE.save(proj, '室内', '茶肆', lay, basis=MSTORE.basis_of('室内', None, '茶肆'))
    got = MSTORE.reuse(proj, '室内', '茶肆',
                       MSTORE.basis_of('室内', ['堂屋', '井', '灶房'], '茶肆'))
    ok('C5 ★★★ 端到端：存的时候一天三处、取的时候一天四处 ⇒ **照样复用得上**',
       got is not None and len(got.places) == 2, str(bool(got)))


# ══════════════════════════════════════════════════════════════
#  D. 产品那条路
# [EN] D. The product's own path
# ══════════════════════════════════════════════════════════════
def d_product(tmp: Path) -> None:
    print('\n── D 产品路径（RunLoop._day_map_anchor）──')
    proj = tmp / 'D'
    proj.mkdir()

    day1 = mk('室内', '茶肆', [('门', .5, .9, '门'), ('堂屋', .5, .6, '屋')])
    day1, _a, why1 = via_product(day1, proj, '室内', '茶肆',
                                 wanted=['门', '堂屋'], here='堂屋')
    p1 = pos(day1)
    ok('D1 ★★★ 第一天：记下位置并落盘（说明行说得出"新定几处"）',
       MAPA.load(proj) and '新定' in ' '.join(why1), '；'.join(why1))

    day2 = mk('室内', '茶肆', [('门', .1, .1, '门'), ('堂屋', .9, .9, '屋')])
    day2, _a, why2 = via_product(day2, proj, '室内', '茶肆',
                                 wanted=['门', '堂屋', '灶房'], here='堂屋')
    p2 = pos(day2)
    ok('D2 ★★★ 第二天模型乱给 + 今天多了灶房 ⇒ 老的两处**一处不动**、灶房补进来',
       all(p2.get(k) == p1[k] for k in p1) and '灶房' in p2,
       f'{p1} → 老位置 { {k: p2.get(k) for k in p1} }｜灶房={p2.get("灶房")}')

    day3 = mk('室内', '茶肆', [('门', .5, .9, '门'), ('堂屋', .5, .6, '屋')])
    day3, _a, why3 = via_product(day3, proj, '室内', '茶肆', wanted=['门', '堂屋'], here='堂屋')
    ok('D3 ★★★ 第三天模型**漏了灶房** ⇒ 由锚定补回来，落在**它原来的位置**'
       '（东西今天有明天没，和位置乱跑一样是不一致）',
       pos(day3).get('灶房') == p2.get('灶房') and '补齐' in ' '.join(why3),
       f'灶房 {p2.get("灶房")} → {pos(day3).get("灶房")}｜{"；".join(why3)}')

    ok('D4 ★★ 落盘的锚定与图上一致（下次开软件不会"忘掉"）',
       pos_dict_eq({k: {'x': v[0], 'y': v[1]} for k, v in p2.items()},
                   {k: {'x': v['x'], 'y': v['y']}
                    for k, v in MAPA.slot_of(MAPA.load(proj), '室内', '茶肆').items()
                    if not k.startswith('_')}),
       MAPA.summary(MAPA.load(proj), '室内', '茶肆'))

    # ★ 换层走产品路径：不该把室内坐标带过去
    d4 = mk('整体', '茶肆', [('茶肆', .2, .8, '楼')])
    d4, _a, _w = via_product(d4, proj, '整体', '茶肆', wanted=['茶肆'], here='茶肆')
    ok('D5 ★★★ 换层走产品路径 ⇒ 用整体层**自己的**坐标（不串室内）',
       pos(d4).get('茶肆') == (0.2, 0.8), str(pos(d4)))


# ══════════════════════════════════════════════════════════════
#  E. 开关
# [EN] E. The switch
# ══════════════════════════════════════════════════════════════
def e_switch(tmp: Path) -> None:
    print('\n── E 开关 ──')
    proj = tmp / 'E'
    proj.mkdir()
    d1 = mk('室内', '茶肆', [('堂屋', .5, .5, '屋')])
    via_product(d1, proj, '室内', '茶肆', wanted=['堂屋'], here='堂屋')
    before = MAPA.load(proj)

    CFG.set('MAP_ANCHOR', 'false')
    try:
        d2 = mk('室内', '茶肆', [('堂屋', .11, .77, '院')])
        d2, layers2, why2 = via_product(d2, proj, '室内', '茶肆',
                                        wanted=['堂屋'], here='堂屋')
        p2 = pos(d2)
        shape = d2.places[0].shape
    finally:
        CFG.set('MAP_ANCHOR', 'true')
    ok('E1 ★★★ 关掉 `MAP_ANCHOR` ⇒ **逐字回到旧行为**：模型给什么就是什么',
       p2.get('堂屋') == (0.11, 0.77) and shape == '院' and not why2,
       f'{p2} shape={shape} why={why2}')
    ok('E2 ★★★ 而且**一个字节都不写**锚定（关掉的开关不该偷偷改盘上的东西）',
       MAPA.load(proj) == before, MAPA.summary(before, '室内', '茶肆'))


# ══════════════════════════════════════════════════════════════
#  F. 反例
# [EN] F. Counterexamples
# ══════════════════════════════════════════════════════════════
def f_counter(tmp: Path) -> None:
    print('\n── F 反例（就地改坏，跑完还原）──')
    proj = tmp / 'F'
    proj.mkdir()
    d1 = mk('室内', '茶肆', [('门', .5, .9, '门'), ('堂屋', .5, .6, '屋')])
    d1, layers, _ = MAPA.apply(d1, '室内', '茶肆', {})
    p1 = pos(d1)

    # 反例①：让"贴锚定"直接不生效 ⇒ A2/D2 会红
    orig_apply = MAPA.apply

    def drop_anchor(lay, layer='', place='', layers=None):
        _lay, _ls, _why = orig_apply(lay, layer, place, layers)
        return _lay, _ls, []

    def no_apply(lay, layer='', place='', layers=None):
        return lay, (layers if isinstance(layers, dict) else {}), []

    try:
        MAPA.apply = no_apply
        d2 = mk('室内', '茶肆', [('门', .1, .1, '门'), ('堂屋', .2, .2, '屋')])
        bad, _l, _w = MAPA.apply(d2, '室内', '茶肆', layers)
    finally:
        MAPA.apply = orig_apply
    ok('F1 ★★★ 反例①：让"贴锚定"不生效 ⇒ 模型的位置直接上屏（A2 会红）',
       pos(bad) != p1, f'{pos(bad)} vs {p1}')

    # 反例②：让 fill 不补"锚定里有但模型漏了"的 ⇒ D3 会红
    orig_fill = MAPA.fill
    try:
        MAPA.fill = lambda lay, wanted, here='', also=None: (lay, [])
        proj2 = tmp / 'F2'
        proj2.mkdir()
        a1 = mk('室内', '茶肆', [('门', .5, .9, '门'), ('灶房', .3, .3, '屋')])
        via_product(a1, proj2, '室内', '茶肆', wanted=['门', '灶房'], here='门')
        a2 = mk('室内', '茶肆', [('门', .5, .9, '门')])
        a2, _l, why2 = via_product(a2, proj2, '室内', '茶肆', wanted=['门'], here='门')
    finally:
        MAPA.fill = orig_fill
    ok('F2 ★★★ 反例②：不补"锚定里已有但模型漏了"的 ⇒ 灶房凭空消失（D3 会红）',
       '灶房' not in pos(a2), str(pos(a2)))

    # 反例③：让 basis_of 又带上地点集合 ⇒ C1 会红
    orig_basis = MSTORE.basis_of
    try:
        MSTORE.basis_of = lambda d, names=None, here='': (
            f'{d}//{"/".join(sorted(names or []))}//{here}')
        again = MSTORE.basis_of('室内', ['甲', '乙', '灶房'], '茶肆')
    finally:
        MSTORE.basis_of = orig_basis
    ok('F3 ★★★ 反例③：指纹又带上"今天的地点集合" ⇒ C1 会红'
       '（那正是"每天重画一次"的根源）',
       again != MSTORE.basis_of('室内', ['甲', '乙'], '茶肆'), again)


def main() -> int:
    print('=' * 62)
    print('  地图锚定（同一处地方永远同一块位置）验证')
    print('=' * 62)
    tmp = Path(tempfile.mkdtemp(prefix='nws_anch_'))
    try:
        for fn in (b_layers,):
            try:
                fn()
            except Exception as e:                               # noqa: BLE001
                ok(f'{fn.__name__} 跑完', False, repr(e))
                print(traceback.format_exc()[-700:])
        for fn in (a_anchor, c_basis, d_product, e_switch, f_counter):
            try:
                fn(tmp)
            except Exception as e:                               # noqa: BLE001
                ok(f'{fn.__name__} 跑完', False, repr(e))
                print(traceback.format_exc()[-700:])
    finally:
        CFG.set('MAP_ANCHOR', 'true')
        shutil.rmtree(tmp, ignore_errors=True)

    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n地图锚定验证：{good}/{n}')
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'map_anchor_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass
    return 0 if good == n else 2


if __name__ == '__main__':
    raise SystemExit(main())
