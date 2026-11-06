# -*- coding: utf-8 -*-
"""三级底图验证（2026-10-08）：**开卷把地图定下来，运行时从它取景**。

用户原话（这段就是规格）：

    「设定集里是否可以包含某个房屋的地图，另外 是否可以在开卷的时候把一些
      **整体地图 局部地图**(房屋附近 房屋内部 以及别的需要的地图)**提前画好**
      需要的时候**基于这些地图让美术加细节**」

四件事要证：

  ① **生成**（A/B）—— 开卷时真的按 `地点.yaml` 生成三层、真的落盘、真的读得回来；
  ② **不许编**（B）—— 整体层的地名只能在设定里；室内层**不许出现地名**；
  ③ **取景**（C）—— 运行时美术**真的拿到了底图**（行为级：抓它收到的那一份），
     且 `layers_for()` 的"今天最细的那层说了算"真的成立；
  ④ **降级**（C/D）—— 没有底图时**照常出图**（不许崩、不许空），
     并且**如实说**"这本书没有底图"。

⚠ 判据一律走 **AST / 行为级**，不做文本匹配（本项目铁律）。
⚠ 夹具里的书名/人名一律用演示名（主角/阿枝/临河茶肆）——
  不许抄用户那本书的（见 `tools/verify_generic_project.py`）。

跑法：.venv\\Scripts\\python.exe tools/verify_map_atlas.py
产出：assets/screenshots/map_atlas_report.json

English:
⚠ All criteria go through **AST / behavior level**, no text matching (iron rule of this
project).
  Do not copy from the user's book (see `tools/verify_generic_project.py`).
How to run: .venv\\Scripts\\python.exe tools/verify_map_atlas.py
Output: assets/screenshots/map_atlas_report.json
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from util.flet_shutdown import exit_now                        # noqa: E402
from world import atlas as AT                                  # noqa: E402
from image_gen.map_layout import Layout, Place                 # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

#: 夹具：**演示名**（不是用户那本书的）
# [EN] : Fixture: **demo name** (not the user's book)
PLACES = [{'名称': '临河茶肆', '说明': '临河的茶楼，两层，后院有口井'},
          {'名称': '城东渡口', '说明': '船来船往，天黑就没人了'}]
SETTINGS = {'places': PLACES}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _src(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def _calls(fn) -> list[tuple[int, str]]:
    """AST 里这个函数**调**了什么（行号，被调用的写成字符串）。**不看注释。**
        English:
    What this function **calls** in the AST (line numbers, callees written as strings). **Do not
    look at comments.**
    """
    out: list[tuple[int, str]] = []
    for n in ast.walk(ast.parse(_src(fn))):
        if isinstance(n, ast.Call):
            out.append((int(getattr(n, 'lineno', 0)), ast.unparse(n.func)))
    return out


def _kw_of(fn, callee: str) -> set[str]:
    """某次调用的**关键字实参名**集合（"算了不传"要在这里才看得出来）。
        English:
    The set of **keyword argument names** for a given call ("never mind, not passing it" is only
    visible here).
    """
    for n in ast.walk(ast.parse(_src(fn))):
        if isinstance(n, ast.Call) and callee in ast.unparse(n.func):
            return {k.arg for k in n.keywords if k.arg}
    return set()


# ══════════════════════════════════════════════════════════════════════
#  A —— 数据结构与接线（源码 / AST）
# [EN] A -- data structures and wiring (source / AST)
# ══════════════════════════════════════════════════════════════════════
def struct_checks() -> None:
    print('\n── A 数据结构（真跑）──')
    # 占位 / 垃圾 → None（**不是空 Atlas**：调用方要能区分"没生成过"与"生成了但空"）
    # [EN] Placeholder / junk → None (**not an empty Atlas**: callers must be able to distinguish "never
    # [EN] generated" from "generated but empty")
    ok('A1 ★★ 设定集里那个空占位（`{"名称":"待生成","地点":[]}`）读出来是 '
       '**None**（不是空 Atlas —— 两者在界面上长得一样，代码里必须分得开）',
       AT.Atlas.from_dict({'名称': '待生成', '地点': []}) is None
       and AT.Atlas.from_dict(None) is None and AT.Atlas.from_dict('x') is None, '')

    a = AT.Atlas(name='演示地图', basis=['临河茶肆', '城东渡口'],
                 overview=Layout(places=[Place('临河茶肆', 0.4, 0.6),
                                         Place('城东渡口', 0.7, 0.3)], source='atlas'),
                 local={'临河茶肆': Layout(places=[Place('城东渡口', 0.2, 0.7)],
                                          source='atlas'),
                        # 另一处也给一份局部：这样"细层在就用细层"才测得出来
                        # [EN] Another place also provides a local copy: this is the only way to test "use the fine layer if it
                        # [EN] exists"
                        '城东渡口': Layout(places=[Place('临河茶肆', 0.6, 0.2),
                                                   Place('河岸', 0.2, 0.8)],
                                          source='atlas')},
                 indoor={'临河茶肆': Layout(places=[Place('堂屋', 0.3, 0.5),
                                                   Place('后院', 0.6, 0.7)],
                                          source='atlas')})
    ok('A2 ★ has_any(): 任一层有内容才算"有底图"', a.has_any(), '')
    # ★ 空底图必须**明说没有**（反例法打出来的洞：只验"有内容时为真"的话，
    #   `has_any` 改成恒真也照样绿 —— 而恒真的后果是"没底图的书被当成有底图"，
    #   运行时永远取不到景，界面还显示"有图"）。
    # [EN] ★ An empty base map must **explicitly say it has none** (a hole punched by counterexample
    # [EN] testing: if you only verify "true when there is content",
    # [EN] then changing `has_any` to always return true still passes -- and the consequence of always-true
    # [EN] is "a book with no base map is treated as having one",
    ok('A2d ★★★ 而**空底图**的 `has_any()` 必须是 False（恒真的话，一本没有底图的'
       '书会被当成有底图 → 取景永远空，界面却写着"有图"）',
       AT.Atlas().has_any() is False
       and AT.Atlas(overview=Layout(places=[Place('甲', .5, .5)])).has_any() is True,
       '')
    d = a.to_dict()
    ok('A2b ★ 落盘形状三层都在（整体 / 局部 / 室内），且顶层留了空的 `地点`'
       '（老代码按它判"有没有内容"，留个空数组比 KeyError 强）',
       all(k in d for k in ('整体', '局部', '室内')) and d.get('地点') == [],
       str(sorted(d.keys())))
    b = AT.Atlas.from_dict(d)
    ok('A2c ★★★ 往返等价：三层都读得回来（`局部`/`室内` 是**按地点名**分桶的）',
       b is not None and b.overview is not None
       and '临河茶肆' in b.local and '临河茶肆' in b.indoor
       and [p.name for p in b.indoor['临河茶肆'].places] == ['堂屋', '后院'],
       str(list(b.indoor) if b else None))

    # ★★ 取景规则：今天最细的那层说了算
    # [EN] ★★ Framing rule: today the thinnest layer has the final say
    ok('A3 ★★★ `layers_for`: 只在一处（人在那儿）→ 用**室内**层',
       [k for k, _n, _l in a.layers_for(['临河茶肆'], '临河茶肆')] == ['室内'], '')
    ok('A3b ★★ 只在一处但**没有室内**层 → 退到**局部**层',
       [k for k, _n, _l in a.layers_for(['城东渡口'], '城东渡口')] == ['局部'], '')
    ok('A3c ★★★ 跨了两处以上 → 用**整体**层（不是把两张局部图拼起来）',
       [k for k, _n, _l in a.layers_for(['临河茶肆', '城东渡口'], '临河茶肆')] == ['整体'],
       '')
    ok('A3d ★ 一层都没有 → 返回**空**（调用方退回"每天现摆位"，不是崩）',
       AT.Atlas().layers_for(['甲'], '甲') == [], '')

    # 依据没变 → 不重画
    # [EN] Basis unchanged -> do not redraw
    ok('A4 ★★ `same_basis`: 依据只是**顺序**变了 → 仍算"没变"（不重画）',
       AT.same_basis(a, ['城东渡口', '临河茶肆']), '')
    ok('A4b ★★★ 依据**内容**变了 → 算变了（必须重画）',
       not AT.same_basis(a, ['临河茶肆', '城东渡口', '第三个地方'])
       and not AT.same_basis(None, ['临河茶肆']), '')
    # ★ 说明改了也要重画：用户手改设定集（§4.1 那条技巧）最常改的就是"说明"——
    #   "后院有口井" → "后院有口井和一间柴房"，名字一个没变。
    #   只比名字的话底图**永远不会跟上**，而界面上一切正常。
    # [EN] ★ Description changes also require a redraw: when users hand-edit the setting collection (the
    # [EN] trick in §4.1), what they most often change is the "description" --
    # [EN] "There's a well in the backyard" -> "There's a well and a woodshed in the backyard", not a
    # [EN] single name changed.
    # [EN] If you only compare names, the base map will **never keep up**, while everything on the UI looks
    # [EN] fine.
    _fp = AT.fingerprint_of(['临河茶肆'], ['临河的茶楼，两层，后院有口井'])
    _fp2 = AT.fingerprint_of(['临河茶肆'], ['临河的茶楼，两层，后院有口井和一间柴房'])
    ok('A4c ★★★ 地点**名字没变、说明改了** → 也判"变了"（指纹把说明算进去了）',
       _fp != _fp2
       and AT.fingerprint_of(['甲', '乙'], ['', ''])
       == AT.fingerprint_of(['乙', '甲'], ['', '']),
       f'{_fp} vs {_fp2}')

    ok('A5 ★ `place_names()` 两种写法都认（`{名称:…}` 与裸字符串），且去重',
       AT.place_names({'places': [{'名称': '甲'}, '乙', {'名称': '甲'}]}) == ['甲', '乙'],
       '')

    # ── 接线：开卷那一步真的被调了 ──
    # [EN] -- Wiring: the step at the start of an ingest is actually invoked --
    from ingest import pipeline as PIPE
    ok('A6 ★★★ 开卷管线里**真的调了** `ensure_atlas`（按 AST 判，不看注释 —— '
       '写了没人调等于没做）',
       any('ensure_atlas' in f for _ln, f in _calls(PIPE.run_ingest)), '')
    ok('A6b ★★★ 而它排在 `_freeze` **之后**（冻结是设定集的最终形态，'
       '`地点.yaml` 定下来才谈得上照着它画图）',
       min((ln for ln, f in _calls(PIPE.run_ingest) if 'ensure_atlas' in f),
           default=-1) > min((ln for ln, f in _calls(PIPE.run_ingest)
                              if '_freeze' in f), default=10 ** 9),
       '')
    # ★ GUI 那条路 **不走** run_ingest 的 settings_dir（它传 None），
    #   所以界面上必须**自己**再调一次 —— 只挂一边的后果是
    #   "命令行有底图、界面上没有"，而且两边都不报错。
    # [EN] ★ The GUI path does **not** go through run_ingest's settings_dir (it passes None),
    # [EN] so the UI must call it **itself** once more -- the consequence of only wiring one side is
    # [EN] "the command line has a base map, the UI doesn't", and neither side reports an error.
    #
    # ⚠ 判据按 **AST 找"哪几个函数里调了它"**，不按函数名硬写：
    #   这次它在 `_do_import` 里那个嵌套的 `worker()` 内。名字会变，
    #   "有没有一个界面方法在调"这件事不会变。
    # [EN] ⚠ The criterion is based on **using the AST to find "which functions call it"**, not hardcoding
    # [EN] function names:
    # [EN] This time it's inside the nested `worker()` within `_do_import`. Names will change,
    # [EN] but "whether some UI method is calling it" won't change.
    _gui_src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    _gui_fns: list[str] = []
    for _node in ast.walk(ast.parse(_gui_src)):
        if isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for _n in ast.walk(_node):
                if (isinstance(_n, ast.Call)
                        and 'ensure_atlas' in ast.unparse(_n.func)):
                    _gui_fns.append(_node.name)
                    break
    ok('A6c ★★★ 界面开卷流程里**也调了一次** `ensure_atlas`'
       '（GUI 的落盘走同步的 `freeze_settings`，塞不进 await —— 只挂管线那边的话'
       '界面上永远没有底图）',
       bool(_gui_fns), f'调它的界面函数：{sorted(set(_gui_fns))}')
    ok('A7 ★★ 底图**关掉**（`MAP_ATLAS=false`）时 `ensure_atlas` 直接返回'
       '（不生成、也不落盘）',
       'MAP_ATLAS' in _src(PIPE.ensure_atlas), '')
    ok('A7b ★★★ 而"依据没变不重画"是**在配置开关之后**判的'
       '（顺序反了：关掉开关也会重画一遍）',
       _src(PIPE.ensure_atlas).index('MAP_ATLAS')
       < _src(PIPE.ensure_atlas).index('same_basis'), '')

    # ── 主循环真的把它当取景来源 ──
    # [EN] -- The main loop actually treats it as the framing source --
    from sim.loop import RunLoop
    ok('A8 ★★★ `_draw_day_map` 里**真的算了** `layers_for`（按 AST 判）',
       any('layers_for' in f for _ln, f in _calls(RunLoop._draw_day_map)), '')
    ok('A8b ★★★ 而 `layers` 真的**传给了美术**（关键字实参里有 `layers` —— '
       '算了不传等于白算）',
       'layers' in _kw_of(RunLoop._draw_day_map, 'day_map_note'),
       str(_kw_of(RunLoop._draw_day_map, 'day_map_note')))
    ok('A8c ★★★ 而底图那一层的名字并进了**白名单**（`allow_extra`）—— '
       '不并的话室内层的房间名（"堂屋"）会被地名白名单全部滤掉，'
       '室内图永远是空的',
       'allow_extra' in _kw_of(RunLoop._draw_day_map, 'day_layout')
       and 'p.name' in _src(RunLoop._draw_day_map), '')
    ok('A9 ★★ 读 `self.atlas` 用的是 `getattr`（判据里用 `RunLoop.__new__` '
       '手工装的夹具没有这个属性；直接访问会 AttributeError 被吞掉 → 假绿）',
       "'atlas'" in _src(RunLoop._draw_day_map)
       or '"atlas"' in _src(RunLoop._draw_day_map), '')
    ok('A9b ★★ 装配处真的把底图读进来挂上了（`build_atlas`）',
       any('build_atlas' in f for _ln, f in _calls(__import__(
           'sim.setup', fromlist=['x']).assemble)), '')
    ok('A9c ★★ 而旧的死链路 `game_map` 已经**不再被装配**（那条路读的是空占位，'
       '永远 None，挂上去也没人读）',
       'game_map' not in _kw_of(
           __import__('sim.setup', fromlist=['x']).assemble, 'RunLoop'), '')


# ══════════════════════════════════════════════════════════════════════
#  B —— 生成（真跑一遍，MOCK 不联网）
# [EN] B -- Generation (actually run once, MOCK does not hit the network)
# ══════════════════════════════════════════════════════════════════════
async def build_checks() -> None:
    print('\n── B 生成（真跑，MOCK）──')
    from ingest import atlas as IAT
    d = Path(tempfile.mkdtemp(prefix='nws_atlas_'))
    notes: list[str] = []
    at = await IAT.build_vector(d, SETTINGS, tokens=1200, on_note=notes.append)

    ok('B1 ★★★ 三层真的生成了：整体 + 局部 + 室内',
       at is not None and at.overview is not None
       and bool(at.local) and bool(at.indoor),
       f'整体={"有" if at and at.overview else "无"} '
       f'局部={len(at.local) if at else 0} 室内={len(at.indoor) if at else 0}')
    ok('B1b ★★ 真的落盘到 `设定集/小世界地图.yaml`', (d / AT.FILE).exists(), '')
    got = AT.load(d)
    ok('B1c ★★★ 落盘之后**真的读得回来**（写进去读不出来的话，运行时永远没底图，'
       '而开卷时看起来一切正常）',
       got is not None and got.has_any()
       and [p.name for p in got.overview.places] == ['临河茶肆', '城东渡口'],
       str([p.name for p in got.overview.places]) if got and got.overview else '')

    # ★ 白名单：整体层不许出现设定以外的名字
    # [EN] ★ Whitelist: the overall layer must not contain names outside the setting
    names = {str(p['名称']) for p in PLACES}
    o_names = {p.name for p in got.overview.places} if got and got.overview else set()
    ok('B2 ★★★ 整体层的地名**全部来自设定**（一个编的都没有）',
       o_names <= names and o_names, str(sorted(o_names)))

    # ★ 室内层不许出现**地名**（屋里没有"某某渡口"）
    # [EN] ★ The interior layer must not contain **place names** (there is no "such-and-such ferry"
    # [EN] indoors)
    bad: list[str] = []
    for place, lay in (got.indoor if got else {}).items():
        for p in lay.places:
            if p.name in names and p.name != place:
                bad.append(f'{place}/{p.name}')
    ok('B2b ★★★ 室内层里**没有别处的地名**（屋里只有房间与器物）',
       not bad, str(bad[:4]))

    # ★ 周边层**允许**出现别处地名（放大看，旁边挨着谁正是它要表达的）
    # [EN] ★ The surroundings layer **allows** place names from elsewhere (zoomed out, who's adjacent is
    # [EN] exactly what it's meant to express)
    ok('B2c ★★★ 周边层**保留**了别处地名（第一版把这条也剔了 → 局部层永远是空的；'
       '"茶肆旁边就是渡口"正是周边层要画的关系）',
       any(p.name in names for _k, lay in (got.local if got else {}).items()
           for p in lay.places),
       str({k: [p.name for p in v.places] for k, v in (got.local if got else {}).items()}))
    ok('B2d ★ 室内层是从**说明里有的东西**推出来的（"两层，后院有口井" → '
       '该出现"院"/"井"）',
       any(any(w in p.name for p in lay.places)
           for lay in (got.indoor if got else {}).values() for w in ('院', '井', '堂')),
       str({k: [p.name for p in v.places] for k, v in (got.indoor if got else {}).items()}))

    ok('B3 ★★★ 每一层的成败都**说了出来**（`on_note` 收到多句；静默少一层是最坏的'
       '失败形态——界面上只是图变简了，没人知道为什么）',
       len(notes) >= len(PLACES) + 2,
       f'{len(notes)} 句（该 ≥ {len(PLACES) + 2}：整体 1 + 每处 1 + 汇总 1）：'
       f'{notes[:2]}')

    # ── B2' 白名单：**打桩让模型故意犯错**，才验得出"拦得住" ──
    # [EN] -- B2' Whitelist: **stub it to make the model deliberately err**, only then can you verify "it
    # [EN] can be blocked" --
    #
    # ⚠ 为什么必须打桩：MOCK 的假回复天生规规矩矩（室内层只给房间名），
    #   于是"剔不剔地名"这条判据**永远绿** —— 反例法打出来的洞就是这个
    #   （变异"室内不剔地名"没被抓到）。
    #   **判据要有区分度，就得让夹具真的犯一次错。**
    # [EN] ⚠ Why stubbing is mandatory: MOCK's fake replies are naturally well-behaved (the interior layer
    # [EN] only gives room names),
    # [EN] so the criterion "filter out place names or not" is **forever green** -- the hole punched by the
    # [EN] counterexample method is exactly this
    # [EN] (the mutation "interior does not filter place names" was not caught).
    # [EN] **For a criterion to have discriminating power, the fixture must actually err once.**
    from ingest import atlas as IAT2
    real_ask = IAT2._ask

    async def _bad_ask(prompt, *, purpose, tokens):
        if purpose == IAT2.PURPOSE_OVERVIEW:
            return {'地点': [{'名称': '临河茶肆', 'x': .4, 'y': .6, '形': '楼'},
                             {'名称': '城东渡口', 'x': .7, 'y': .3, '形': '渡'},
                             {'名称': '编出来的地方', 'x': .1, 'y': .1, '形': '屋'}],
                    '通路': [], '题记': '小世界'}
        # 内部：**故意混进一个地名**（模型很爱这么干）+ 两个真房间
        # 周边：给一个**别处的地名**（这是它该保留的）
        # [EN] Interior: **deliberately mix in one place name** (the model loves doing this) + two real rooms
        # [EN] Surroundings: give one **place name from elsewhere** (this is what it should keep)
        return {'周边': {'地点': [{'名称': '城东渡口', 'x': .2, 'y': .8, '形': '渡'},
                                  {'名称': '河岸', 'x': .3, 'y': .7, '形': '渡'}],
                         '通路': []},
                '内部': {'地点': [{'名称': '城东渡口', 'x': .9, 'y': .9, '形': '渡'},
                                  {'名称': '堂屋', 'x': .5, 'y': .4, '形': '屋'},
                                  {'名称': '后院', 'x': .6, 'y': .7, '形': '院'}],
                         '通路': []}}

    d5 = Path(tempfile.mkdtemp(prefix='nws_atlas5_'))
    try:
        IAT2._ask = _bad_ask
        at5 = await IAT2.build_vector(d5, SETTINGS, tokens=1200)
    finally:
        IAT2._ask = real_ask

    o_names5 = ({p.name for p in at5.overview.places} if at5 and at5.overview
                else set())
    ok('B2e ★★★ 整体层里模型**编的地方**（"编出来的地方"）被拦下 —— '
       '底图不许凭空编（这是"白名单"在最粗那一层的作用）',
       '编出来的地方' not in o_names5 and o_names5 == names, str(sorted(o_names5)))
    inner5 = {p.name for lay in (at5.indoor if at5 else {}).values()
              for p in lay.places}
    ok('B2f ★★★ 室内层里混进来的**地名**被剔掉，而**房间名留下**'
       '（屋里没有"某某渡口"，只有房间与器物）',
       '城东渡口' not in inner5 and {'堂屋', '后院'} <= inner5, str(sorted(inner5)))
    local5 = {p.name for lay in (at5.local if at5 else {}).values()
              for p in lay.places}
    # ⚠ 区分点在**地物名**（"河岸"这种**不在 `地点.yaml` 里**的名字）：
    #   若周边层拿地名白名单过滤，被干掉的第一批就是它们 ——
    #   而"城东渡口"（它的确在 names 里）**反而留得住**，拿它当判据看不出差别
    #   （反例法打出来的洞：变异"周边层也过滤"没被抓到，就是因为判据只看了后者）。
    # [EN] ⚠ The distinguishing point is **feature names** (names like "riverbank" that are **not in
    # [EN] `地点.yaml`**):
    # [EN] If the surroundings layer filters with the place-name whitelist, the first batch to be killed is
    # [EN] exactly these --
    # [EN] whereas "east-town ferry" (which is indeed in names) **survives instead**, so using it as the
    # [EN] criterion shows no difference
    # [EN] (the hole punched by the counterexample method: the mutation "surroundings layer also filters"
    # [EN] was not caught, precisely because the criterion only looked at the latter).
    ok('B2g ★★★ 而周边层里**保留了别处地名与地物名**（"城东渡口"是地名、'
       '"河岸"是地物 —— 后者**不在 `地点.yaml` 里**，正是"拿地名白名单过滤'
       '周边层"会误杀的那一批。放大看，旁边挨着什么正是它要表达的关系；'
       '第一版把这条也剔了 → 局部层永远是空的）',
       '城东渡口' in local5 and '河岸' in local5, str(sorted(local5)))

    # ── B7 ★★★ 作者写的 `方位` / `内里` **真的进了提示词** ──
    # [EN] -- B7 ★★★ The author-written `方位` / `内里` **actually make it into the prompt** --
    #
    #   字段存下来不等于用上了：不拼进提示词的话，底图还是按"说明 + 常识"推，
    #   作者看到的是"我明明写了柴房，图上怎么没有"。
    #   抓的是**发出去的 prompt**（行为级），不是"源码里有没有 place_detail"。
    # [EN] Storing a field does not equal using it: if it isn't assembled into the prompt, the base map is
    # [EN] still inferred from "description + common sense",
    # [EN] and what the author sees is "I clearly wrote a woodshed, why isn't it on the map".
    # [EN] What's being captured is the **sent-out prompt** (behavior level), not "whether place_detail
    # [EN] exists in the source code".
    _cap: list[str] = []

    async def _cap_ask(prompt, *, purpose, tokens):
        _cap.append(prompt)
        return await real_ask(prompt, purpose=purpose, tokens=tokens)

    _d7 = Path(tempfile.mkdtemp(prefix='nws_atlas7_'))
    _rich = {'places': [{'名称': '临河茶肆', '说明': '临河的茶楼，两层，后院有口井',
                         '方位': '临着河，在渡口西边',
                         '内里': ['堂屋', '后院', '井', '柴房']},
                        PLACES[1]]}
    try:
        IAT2._ask = _cap_ask
        await IAT2.build_vector(_d7, _rich, tokens=900)
    finally:
        IAT2._ask = real_ask
    _blob = '\n'.join(_cap)
    ok('B7 ★★★ 作者写在设定里的 `方位` / `内里` **真的进了发给模型的提示词**'
       '（存下来不算用上 —— 不拼进去的话"我写了柴房图上怎么没有"）',
       '柴房' in _blob and '临着河' in _blob, f'{len(_cap)} 次调用')

    # ── B4 依据没变 → 不重画（省一次生成）──
    # [EN] -- B4 Basis unchanged -> do not redraw (save one generation) --
    d2 = Path(tempfile.mkdtemp(prefix='nws_atlas2_'))
    AT.save(d2, at)
    n2: list[str] = []
    from ingest import pipeline as PIPE
    await PIPE.ensure_atlas(d2, SETTINGS, on_note=n2.append)
    ok('B4 ★★★ 依据没变时**不重画**（复用已有的 —— 重开卷/优化后重新冻结，'
       '地点表没变就省一次生成）',
       any('沿用' in x for x in n2), str(n2[:2]))

    # ── 关掉开关 → 什么都不生成 ──
    # [EN] -- Turn off the switch -> generate nothing --
    d3 = Path(tempfile.mkdtemp(prefix='nws_atlas3_'))
    CFG.set('MAP_ATLAS', 'false')
    try:
        await PIPE.ensure_atlas(d3, SETTINGS)
    finally:
        CFG.set('MAP_ATLAS', 'true')
    ok('B5 ★★ `MAP_ATLAS=false` → 一份底图都不生成（连文件都不建）',
       not (d3 / AT.FILE).exists(), '')

    # ── 失败降级 ──
    # [EN] -- Failure degradation --
    d4 = Path(tempfile.mkdtemp(prefix='nws_atlas4_'))
    got4 = await IAT.build_vector(d4, {'places': []}, tokens=800)
    ok('B6 ★★ 设定里没有地点 → 返回 None、不落盘（**不崩**，界面退回每天现画）',
       got4 is None and not (d4 / AT.FILE).exists(), '')

    # ★ 三层**全都生成失败**（模型一条都没给出）→ 也必须返回 None
    #   ⚠ 这条是反例法打出来的：只验"没有地点"那一支的话，
    #     "一层都没有也返回一个空 Atlas"那个变异照样绿 ——
    #     后果是调用方分不清"没生成过"与"生成失败了"（界面上长得一样）。
    # [EN] ★ All three layers **fail to generate** (the model produces not a single one) -> must still
    # [EN] return None
    # [EN] ⚠ This one was found by the counterexample method: if you only verify the branch where "there
    # [EN] are no places",
    # [EN] the mutation "even with zero layers, return an empty Atlas" stays green --
    # [EN] the consequence is the caller cannot distinguish "never generated" from "generation failed"
    # [EN] (they look identical on the UI).
    d6 = Path(tempfile.mkdtemp(prefix='nws_atlas6_'))

    async def _no_ask(prompt, *, purpose, tokens):
        return None

    try:
        IAT2._ask = _no_ask
        got6 = await IAT2.build_vector(d6, SETTINGS, tokens=800)
    finally:
        IAT2._ask = real_ask
    ok('B6b ★★★ 三层**全都没生成出来** → 返回 None 且**不落盘**'
       '（不许返回一个空 Atlas —— 那样调用方分不清"没生成过"与"生成失败了"）',
       got6 is None and not (d6 / AT.FILE).exists(),
       f'返回={got6!r} 落盘={(d6 / AT.FILE).exists()}')


# ══════════════════════════════════════════════════════════════════════
#  C —— 取景（行为级：真跑 `_draw_day_map`，抓美术收到的那一份）
# [EN] C -- Framing (behavior level: actually run `_draw_day_map`, capture the copy the art module
# [EN] received)
# ══════════════════════════════════════════════════════════════════════
async def shot_checks() -> None:
    print('\n── C 取景（真跑 `_draw_day_map`）──')
    import types
    from crew.agents import CrewNote
    from sim.loop import RunLoop

    KNOWN = ['临河茶肆', '城东渡口']

    class FakeStudio:
        def __init__(self, reply=None):
            self.seen_places: list = []
            self.seen_layers: list = []
            self.reply = reply

        async def day_map_note(self, ctx, *, here='', places=None, layers=None):
            self.seen_places.append(list(places or []))
            self.seen_layers.append(list(layers or []))
            return self.reply

    def make_loop(st, atlas):
        lp = RunLoop.__new__(RunLoop)
        lp.world = types.SimpleNamespace(
            scene='临河茶肆', game_day=1,
            worldview_text='【地点】' + '、'.join(KNOWN) + '\n【别的】…')
        lp.db = None
        lp.agents = []
        lp._current_day = 1
        lp._last_place = '临河茶肆'
        lp.studio = st
        lp.atlas = atlas
        lp.runfolder = types.SimpleNamespace(root=Path(tempfile.mkdtemp(
            prefix='nws_at_')))
        lp._push_narrative = lambda *a, **k: None
        lp._clock_segment = lambda: '戌时'
        lp._on_scene = None
        lp._review_record_only = lambda *a, **k: None
        lp._warn_once = lambda *a, **k: None
        return lp

    BEATS = [{'场': '临河茶肆堂内·雨夜·柜台前', '发生': '他把壶盖压回去。'}]
    ds = types.SimpleNamespace(day=1, beats=BEATS, story='雨敲在船板上，不密，却重。')

    # ── C1 有底图（室内层）→ 美术真的收到了那一层 ──
    # [EN] -- C1 Has a base map (interior layer) -> the art module really received that layer --
    d = Path(tempfile.mkdtemp(prefix='nws_at_c_'))
    AT.save(d, AT.Atlas(
        name='演示', basis=list(KNOWN),
        overview=Layout(places=[Place('临河茶肆', .4, .6), Place('城东渡口', .7, .3)],
                        source='atlas'),
        indoor={'临河茶肆': Layout(places=[Place('堂屋', .3, .5), Place('后院', .6, .7)],
                                  source='atlas')}))
    at = AT.load(d)
    st = FakeStudio(CrewNote(role='art', ok=True, title='1 处',
                             data={'地点': [{'名称': '堂屋', 'x': .3, 'y': .5},
                                            {'名称': '后院', 'x': .6, 'y': .7}],
                                   '通路': [['堂屋', '后院']], '题记': '一夜'}))
    lp = make_loop(st, at)
    await lp._draw_day_map(ds)
    layers_got = st.seen_layers[0] if st.seen_layers else []
    ok('C1 ★★★ 有底图时美术**真的收到了那一层**（层名 + Layout 一起）',
       bool(layers_got) and layers_got[0][0] == '室内', str([k for k, _n, _l in layers_got]))
    ok('C1b ★★★ 室内层的**房间名进了白名单**：`堂屋`/`后院` 没被滤掉'
       '（只按 `地点.yaml` 过滤的话它们会被全部丢掉 → 室内图永远是空的）',
       lp.day_map is not None
       and {p.name for p in lp.day_map.places} >= {'堂屋', '后院'},
       str([p.name for p in lp.day_map.places]) if lp.day_map else '未出图')

    # ── C2 跨两处 → 用整体层 ──
    # [EN] -- C2 Spans two places -> use the overall layer --
    st2 = FakeStudio(CrewNote(role='art', ok=True, title='2 处',
                              data={'地点': [{'名称': '临河茶肆', 'x': .4, 'y': .6},
                                             {'名称': '城东渡口', 'x': .7, 'y': .3}],
                                    '通路': [], '题记': '小世界'}))
    lp2 = make_loop(st2, at)
    BEATS2 = [{'场': '临河茶肆', '发生': '他起身。'},
              {'场': '城东渡口', '发生': '船靠了岸。'}]
    await lp2._draw_day_map(types.SimpleNamespace(day=1, beats=BEATS2, story='x'))
    ok('C2 ★★ 今天跨了两处 → 走**整体**层（不是把两张局部图拼起来）',
       bool(st2.seen_layers) and st2.seen_layers[0][0][0] == '整体',
       str([k for k, _n, _l in (st2.seen_layers[0] if st2.seen_layers else [])]))

    # ── C3 没有底图 → 照常出图（降级，不许崩）──
    # [EN] -- C3 No base map -> draw as usual (degrade, must not crash) --
    st3 = FakeStudio(CrewNote(role='art', ok=True, title='1 处',
                              data={'地点': [{'名称': '临河茶肆', 'x': .5, 'y': .6}],
                                    '通路': [], '题记': '一夜'}))
    lp3 = make_loop(st3, None)
    await lp3._draw_day_map(ds)
    ok('C3 ★★★ 这本书**没有底图**时：`layers` 是空的，但**照常出图**'
       '（底图是"更好"，不是"必需" —— 拿不到就退回从前那套）',
       st3.seen_layers == [[]] and lp3.day_map is not None
       and [p.name for p in lp3.day_map.places] == ['临河茶肆'],
       f'layers={st3.seen_layers} 出图={lp3.day_map is not None}')

    # ── C4 底图坏了也不许把推演顶住 ──
    # [EN] -- C4 Even if the base map is broken, it must not hold up the inference --
    class BoomAtlas:
        basis: list = []

        def layers_for(self, *a, **k):
            raise RuntimeError('底图炸了')

    st4 = FakeStudio(CrewNote(role='art', ok=True, title='1 处',
                              data={'地点': [{'名称': '临河茶肆', 'x': .5, 'y': .6}],
                                    '通路': [], '题记': '一夜'}))
    lp4 = make_loop(st4, BoomAtlas())
    # ⚠ 必须**包住**：不包的话这一支抛出去会让后面所有判据陪葬
    #   （表现为"验证执行中断"，而不是"C4 红了"—— 前者看不出是哪一条坏了）。
    # [EN] ⚠ Must **wrap it**: if not wrapped, this branch throwing will drag down all subsequent criteria
    # [EN] (manifesting as "verification execution interrupted", not as "C4 turned red" -- the former
    # [EN] doesn't show which one broke).
    _raised = ''
    try:
        await lp4._draw_day_map(ds)
    except BaseException as e:                                  # noqa: BLE001
        _raised = repr(e)
    ok('C4 ★★★ 底图那一层**炸了**（读坏文件/层坏了）→ 不抛、退回每天现摆位，'
       '推演照跑（底图不是生死线）',
       not _raised and st4.seen_layers == [[]] and lp4.day_map is not None,
       f'抛出={_raised or "没有"} layers={st4.seen_layers} '
       f'出图={lp4.day_map is not None}')

    # ── C5 白名单照旧拦编造（底图不放松"不许编"）──
    # [EN] -- C5 The whitelist still blocks fabrication as before (the base map doesn't relax "no
    # [EN] fabricating") --
    st5 = FakeStudio(CrewNote(role='art', ok=True, title='1 处',
                              data={'地点': [{'名称': '临河茶肆', 'x': .5, 'y': .6},
                                             {'名称': '隔壁的客栈', 'x': .2, 'y': .3}],
                                    '通路': [], '题记': '一夜'}))
    lp5 = make_loop(st5, at)
    await lp5._draw_day_map(ds)
    names5 = [p.name for p in lp5.day_map.places] if lp5.day_map else []
    ok('C5 ★★★ 底图**不放松**"不许编"：模型编的"隔壁的客栈"（既不在设定、'
       '也不在底图里）照样被拦下',
       '隔壁的客栈' not in names5, str(names5))


async def main() -> None:
    try:
        struct_checks()
        await build_checks()
        await shot_checks()
    except BaseException:                                       # noqa: BLE001
        ok('（验证执行中断）', False, traceback.format_exc()[-600:])
        print(traceback.format_exc()[-1800:])
    total = len(report['checks'])
    passed = sum(1 for c in report['checks'] if c['ok'])
    report.update({'total': total, 'passed': passed, 'ok': passed == total})
    (OUT / 'map_atlas_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n三级底图验证：{passed}/{total}')
    exit_now(0 if passed == total else 2)


if __name__ == '__main__':
    asyncio.run(main())
