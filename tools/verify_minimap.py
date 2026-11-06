# -*- coding: utf-8 -*-
"""真机验证：小地图（**矢量** + 每次切场景重画 + AI 摆位）。

用户 2026-10-06
--------------
「小地图是否可以用矢量图的形式每次都重新画一下（切换场景的时候绘制），
  而且要是根据故事里的设计尽可能的反应其布局（可以稍微简略但是不能够
  一点都不像），要求使用AI动态绘制」

三句话对应三组判据
------------------
| 用户要的 | 判据 |
|---|---|
| 矢量 | A1 渲染器与白名单的字形集合**完全相等**；B 组量像素证明是**真画出来**的 |
| 每次切场景重画 | ★★ B4 **标记色法**：把"当前地点"染成品红，换一次地点后**质心必须移动** |
| AI 按设定摆位 | A5~A8：开关真管事、编出来的地点被丢掉、失败退回兜底、缓存往返 |

★ 像素怎么量（这轮的关键手法）
------------------------------
左栏里那块画布没有名字，屏幕上也找不到"这里就是画布"的标记 —— 所以
**把纸底染成独占色**（`palette={'paper': '#0000ff'}`）：那一大块蓝色矩形
就是画布本身，它的 bbox 一量就准。然后在 bbox 里数"非纸色"像素 = 图上的墨迹。
这比"在左栏里瞎找"可靠得多，也不受面板半透明影响。

跑法：.venv\\Scripts\\python.exe tools/verify_minimap.py
产出：assets/screenshots/minimap_*.png / minimap_report.json

English:
real-machine verification: minimap (**vector** + redraw on every scene switch + AI placement).
User 2026-10-06
--------------
"Can the minimap be redrawn in vector form each time (drawn when switching scenes),
  and should it reflect the layout as much as possible according to the story's design (can be slightly simplified but must not
  look nothing like it), required to use AI to draw dynamically"
three sentences correspond to three groups of criteria
------------------
| what the user wants | criteria |
|---|---|
| vector | A1 the renderer and the whitelist's glyph set are **exactly equal**; group B measures pixels to prove it is **actually drawn** |
| redraw on every scene switch | ★★ B4 **marker color method**: dye the "current location" magenta; after switching location once, **the centroid must move** |
| AI places according to the settings | A5~A8: the switch really works, fabricated locations get dropped, failures fall back to the fallback, cache round-trip |
★ how to measure pixels (the key technique of this round)
------------------------------
that canvas in the left column has no name, and there is no marker on screen saying "this is the
canvas" —— so
**dye the paper background an exclusive color** (`palette={'paper': '#0000ff'}`): that big blue
rectangle
is the canvas itself, and measuring its bbox gives an exact result. Then within the bbox, count
"non-paper-color" pixels = the ink on the map.
this is far more reliable than "blindly searching in the left column", and is unaffected by the
panel's translucency.
how to run: .venv\\Scripts\\python.exe tools/verify_minimap.py
output: assets/screenshots/minimap_*.png / minimap_report.json
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import tempfile
import textwrap
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                        # noqa: E402
import verify_ui_common as VU                            # noqa: E402
from util.flet_shutdown import shutdown, exit_now        # noqa: E402

from config import CFG                                   # noqa: E402
CFG.set('MOCK_LLM', 'true')

import gui.app_flet as G                                 # noqa: E402
import llm.replies as REPLIES                            # noqa: E402
from image_gen import map_layout as ML                   # noqa: E402
from image_gen import minimap as MM                      # noqa: E402
from store.project import Project                        # noqa: E402
from store.runfolder import RunFolder                    # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
VU.redirect_env_writes()

PAPER_MARK = '#0000ff'      # 独占色：纸底（用来标出画布范围）
HERE_MARK = '#ff00ff'       # 独占色：当前地点（用来量它移到哪去了）
# [EN] Exclusive color: paper background (used to mark the canvas extent)
# [EN] Exclusive color: current place (used to measure where it moved to)

PLACES = [{'名称': '临河茶肆', '说明': '河码头旁的小茶肆'},
          {'名称': '城东渡口', '说明': '夜里只有零星渡船'},
          {'名称': '后院', '说明': '堆着柴'},
          {'名称': '县衙', '说明': '在城北'}]
#: 上面那几条的名字（`normalize` 的白名单要它）
# [EN] : the names of the above entries (`normalize`'s whitelist needs them)
PLACES_NAMES = [p['名称'] for p in PLACES]

checks: list = []


def ok(name: str, cond, detail='') -> bool:
    checks.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:200]})
    return bool(cond)


def cjk(s: str) -> None:
    """让人一眼看出红在哪一行。
        English:
    let a person see at a glance which line is red.
    """
    print(('  ✓ ' if s['ok'] else '  ✗ ') + s['name'] + (
        f"   [{s['detail']}]" if not s['ok'] else ''))


# ══════════════════════════════════════════════════════════════════════
#  A 组：纯逻辑（不开窗）
# [EN] Group A: pure logic (no window opened)
# ══════════════════════════════════════════════════════════════════════
def logic_checks() -> None:
    # ── A1 两边的字形集合必须一模一样 ──
    # [EN] ── A1 The glyph sets on both sides must be exactly identical ──
    ok('A1 ★ 渲染器的字形与交给 AI 的白名单**完全相等**'
       '（少一个就会静默掉进"屋"那个默认分支）',
       set(MM.known_shapes()) == set(ML.SHAPES),
       f'{MM.known_shapes()} vs {ML.SHAPES}')

    # ── A2 归一化：夹取 / 丢弃编造的地名 / 补齐漏项 ──
    # [EN] ── A2 Normalization: clamp / drop fabricated place names / fill in missing entries ──
    lay = ML.normalize({
        '地点': [{'名称': '临河茶肆', 'x': 1.7, 'y': -0.2, '形': '屋', '简称': '茶肆'},
                 {'名称': '隔壁客栈', 'x': .5, 'y': .5},          # 设定里没有 → 丢
                 # [EN] not in the settings → drop
                 {'名称': '城东渡口', 'x': .9, 'y': .8, '形': '渡', '大小': '小'}],
        '通路': [{'从': '临河茶肆', '到': '城东渡口', '形': '桥'},
                 {'从': '临河茶肆', '到': '不存在的', '形': '路'}],   # → 丢
                 # [EN] → drop
        '水系': [[0, .4], [.5, .5], [1, .7]], '题记': '临河镇',
    }, ['临河茶肆', '城东渡口', '后院'], source='ai')
    names = [p.name for p in lay.places]
    ok('A2a 坐标被夹到 0~1（AI 会给 1.7 / -0.2）',
       all(0.0 <= p.x <= 1.0 and 0.0 <= p.y <= 1.0 for p in lay.places),
       [(p.name, p.x, p.y) for p in lay.places])
    ok('A2b ★ 模型**编出来的地点被丢掉**（设定里没有的一律不画）',
       '隔壁客栈' not in names, names)
    ok('A2c ★ 模型漏掉的地点被**补**回来（宁可不精确也不能少）',
       '后院' in names, names)
    ok('A2d 连到不存在地点的通路被丢掉',
       all(l['a'] in names and l['b'] in names for l in lay.links), lay.links)
    ok('A2e 水系 / 题记保留', len(lay.water) == 3 and lay.caption == '临河镇',
       f'{lay.water} / {lay.caption}')
    ok('A2f `形` 走了白名单（乱写的退回「屋」）',
       ML.normalize({'地点': [{'名称': 'X', '形': '牌楼水榭戏台'}]},
                    ['X']).places[0].shape in ML.SHAPES, '')

    # ── A3 JSON 往返 ──
    # [EN] ── A3 JSON round-trip ──
    back = ML.Layout.from_dict(lay.to_dict())
    ok('A3 布局能 JSON 往返（缓存靠它；指纹一致）',
       back is not None and back.signature() == lay.signature(),
       f'{back.signature()[:50] if back else None}')
    # ⚠ 这里必须**同时**容忍两种合理结果：`None` 或"空布局"。
    #   第一版写成 `.places == []` 直接取属性 → `from_dict` 返回 None 时
    #   AttributeError 把整个脚本打断（判据自己写窄了，不是产品坏了）。
    # [EN] ⚠ Here we must **simultaneously** tolerate two reasonable results: `None` or an "empty layout".
    # [EN] The first version was written as `.places == []` accessing the attribute directly → when
    # [EN] `from_dict` returns None
    # [EN] AttributeError breaks the whole script (the criterion itself was written too narrowly, not that
    # [EN] the product is broken).
    def _no_places(v) -> bool:
        return v is None or not getattr(v, 'places', None)
    ok('A3b 坏数据不抛：`places` 给了字符串不许被拆成"三个地点"',
       _no_places(ML.Layout.from_dict(None))
       and _no_places(ML.Layout.from_dict({'places': 'abc'}))
       and _no_places(ML.Layout.from_dict({'places': 123})),
       f"{ML.Layout.from_dict({'places': 'abc'})}")
    ok('A3c 缓存里 `links` 给字符串也不炸（同样要走列表判断）',
       _no_places(ML.Layout.from_dict({'places': [{'名称': 'X'}],
                                       'links': 'abc'})) is False, '')

    # ── A4 兜底布局 ──
    # [EN] ── A4 Fallback layout ──
    s1 = ML.simple_layout(['临河茶肆', '城东渡口', '后院'],
                          notes=['河码头旁的小茶肆', '夜里只有零星渡船', ''])
    ok('A4a 兜底：地点一个不少，顺序跟设定一致',
       [p.name for p in s1.places] == ['临河茶肆', '城东渡口', '后院'],
       [p.name for p in s1.places])
    # ★ 「认得河/渡」要**量位移**，不能只比两个地点的先后 ——
    #   第一版写成 `places[0].y > places[2].y`：那条弧线本身就恰好让
    #   places[0] 比 places[2] 低，**把提示删掉它照样成立**（变异抓不到）。
    #   现在拿"同一份设定、给不给说明"两次结果相减，位移才是真的证据。
    # [EN] ★ "Recognizing river/ferry" must **measure displacement**, not just compare the order of two
    # [EN] places ——
    # [EN] The first version was written as `places[0].y > places[2].y`: that arc itself happens to make
    # [EN] places[0] lower than places[2], **deleting the hint still makes it hold** (mutation not caught).
    # [EN] Now we subtract the two results of "same settings, with and without the explanation", so the
    # [EN] displacement is the real evidence.
    s_plain = ML.simple_layout(['临河茶肆', '城东渡口', '后院'],
                               notes=['', '', ''])
    dy = s1.places[0].y - s_plain.places[0].y
    ok('A4b ★ 兜底**认得"河/渡"**：说明里带水的地点被往下挪（位移 ≥ 0.1）',
       dy >= 0.1, f'带说明 y={s1.places[0].y:.2f} / 不带 y={s_plain.places[0].y:.2f}'
                  f'（差 {dy:.2f}）')
    ok('A4c 兜底把相邻地点连起来（有"一条街"的样子，不是散点）',
       len(s1.links) == 2, s1.links)
    ok('A4d 兜底是可复现的（同样输入两次结果一致）',
       ML.simple_layout(['A', 'B']).signature()
       == ML.simple_layout(['A', 'B']).signature(), '')
    ok('A4e 没有地点 → 空布局（不编）', ML.simple_layout([]).places == [], '')

    # ── A5 配置项真的被读（行为判据，不是源码哨兵）──
    # [EN] ── A5 Config items are actually read (behavioral criterion, not a source-code sentinel) ──
    #
    # ★ 2026-10-08 改了**指向**：`MINIMAP_AI` 的语义从"全书总图要不要 AI 摆位"
    #   变成"**当天这张图**要不要美术用 AI 摆位"（那条全书链路整段拆掉了 ——
    #   它画的正是用户不想要的"整本小说设定的地图"）。所以判据从
    #   `_ensure_map_layout` 移到 `RunLoop._draw_day_map`。
    #   （与 `verify_llm_budget` B4 那次同一个做法：开关搬进共用函数，判据跟着搬。）
    # [EN] ★ 2026-10-08 changed the **target**: the semantics of `MINIMAP_AI` went from "does the
    # [EN] whole-book overview map need AI placement"
    # [EN] to "does **today's map** need the artist to use AI placement" (that whole-book chain was torn
    # [EN] out entirely ——
    # [EN] it was drawing exactly the "map of the whole novel's settings" that the user didn't want). So
    # [EN] the criterion moved from
    # [EN] `_ensure_map_layout` to `RunLoop._draw_day_map`.
    # [EN] (Same approach as the `verify_llm_budget` B4 case: move the switch into a shared function, and
    # [EN] the criterion follows.)
    import inspect
    from sim.loop import RunLoop
    dm_src0 = inspect.getsource(RunLoop._draw_day_map)
    ok('A5 ★ `MINIMAP_AI` 被读到、并且**关掉时**不叫模型、直接简化排布',
       "CFG.b('MINIMAP_AI')" in dm_src0
       and 'simple_layout' in dm_src0.split("CFG.b('MINIMAP_AI')")[1][:300],
       [l.strip() for l in dm_src0.split('\n') if 'MINIMAP_AI' in l][:1])
    ok('A5b `minimap_layout` 进了 `NO_THINK_PURPOSES`'
       '（结论型产出，开思考会把额度烧光）',
       ML.PURPOSE in __import__('llm.router', fromlist=['x']).NO_THINK_PURPOSES,
       ML.PURPOSE)

    # ── A6 画布尺寸必须装得进左栏（否则被裁且**不报错**）──
    col_w, pad = 220, 12          # 左栏宽 / `_create_panel` 左右内边距
    # [EN] ── A6 The canvas size must fit into the left column (otherwise it gets clipped and **does not
    # [EN] error**) ──
    # [EN] left column width / `_create_panel` left and right padding
    ok('A6 画布宽 ≤ 左栏内容区（超了会被裁，而且不报错）',
       G.MAP_W <= col_w - 2 * pad, f'{G.MAP_W} vs {col_w - 2 * pad}')

    # ── A7 形状构建：空布局 / 无布局都要能画出东西（不能返回空列表）──
    # [EN] ── A7 Shape construction: both empty layout and no layout must be able to draw something (must
    # [EN] not return an empty list) ──
    ok('A7a 没有布局时画一张"还没有地点设定"的提示（不是空白）',
       len(MM.build_shapes(None)) >= 2, MM.shape_counts(MM.build_shapes(None)))
    ok('A7b 每个地点都写出了**一行小字**（标签数与地点数对得上）',
       sum(1 for s in MM.build_shapes(lay, current='城东渡口')
           if type(s).__name__ == 'Text') >= len(lay.places),
       MM.shape_counts(MM.build_shapes(lay, current='城东渡口')))

    # ★★★ 2026-10-12（用户**第三次**报红点）：「小地图里标记〔那座楼〕和**旁边的红点**还是存在
    #   去掉它 **如果想要标记地点 用小字标记就行了 不要用点**」。
    #   前两轮去掉的是"整座楼那个红点"与"假地点那个红点"，但**地点自己的图形记号**
    #   一直还在（`_glyph` 画的字形 + 当前地点垫的朱砂实心圆）—— 局部图上两者叠加，
    #   屏幕上就是"名字旁边一个红点"。
    #  ⇒ 判据改成**两条**，一条钉"没有点"，一条钉"当前地点靠字色区分"。
    # [EN] ★★★ 2026-10-12 (the user's **third** red-dot report): "the label for [that building] and
    # [EN] **the red dot next to it** are still there; remove it. **If you want to mark a location, just
    # [EN] mark it with small text -- do not use dots**."
    # [EN] The previous two rounds removed "the red dot for the whole building" and "the red dot for a
    # [EN] fake place", but the locations' **own graphical marks** were still there (the glyph `_glyph`
    # [EN] drew + the cinnabar filled circle under the current location) -- on a local map the two stack
    # [EN] up, and on screen that is "a red dot next to the name".
    # [EN] ⇒ The criterion becomes **two**: one pins "no dots", one pins "the current location is
    # [EN] distinguished by text colour".
    plain = MM.build_shapes(lay, current='城东渡口')
    none_cur = MM.build_shapes(lay, current='')
    ok('A7c ★★★ 地点**不用点标记**：不传在场人物时，图上**一个实心圆都没有**'
       '（字形与朱砂圈都不许在）'
       '—— 用户第三次报的就是这个红点：「不要用点」',
       MM.shape_counts(plain).get('Circle', 0) == 0,
       str(MM.shape_counts(plain)))

    def _ink_color(s) -> str:
        return str(getattr(getattr(s, 'style', None), 'color', ''))

    _here = [getattr(s, 'value', '') for s in plain
             if type(s).__name__ == 'Text'
             and _ink_color(s) == str(MM.PALETTE['here'])]
    _here_none = [s for s in none_cur
                  if type(s).__name__ == 'Text'
                  and _ink_color(s) == str(MM.PALETTE['here'])]
    ok('A7d ★★★ 而"我在哪一处"仍然看得出来 —— 靠**朱砂色的字**（不是圈）'
       '—— 没有当前地点时，一个朱砂色都不许有',
       _here == ['城东渡口'] and not _here_none,
       f'当前色字={_here} · 无当前时={len(_here_none)} 个')

    # ══════════════════════════════════════════════════════════════
    #  A10 组：局部取景（小地图画的是"当前地点附近"，不是全书总图）
    # [EN] Group A10: local framing (the minimap draws "near the current place", not the whole-book
    # [EN] overview map)
    #
    #  用户 2026-10-07：「小地图不对 雾泽 里巷 山海 梦话 东馆啥的都出来了
    #  小地图应该是当前这个场景下面 主人公所在地方附近的小地图 不是小说的总地图」
    # [EN] the minimap should be the minimap near where the protagonist is in the current scene, not the
    # [EN] novel's overall map"
    #
    #  ★ 这一组钉的是那个 bug 的**可测形式**：站在一处地点时，
    #    画布上**不许**出现全部地点。用他真实的设定（7 个"界"）当夹具。
    # [EN] ★ This group pins down the **testable form** of that bug: when standing at one place,
    # [EN] the canvas **must not** show all places. Use his real settings (7 "界") as the fixture.
    # ══════════════════════════════════════════════════════════════
    realms = ['临河茶肆', '里巷', '雾泽', '苍梧界', '东馆', '长干界', '落霞界']
    full = ML.normalize({
        '地点': [{'名称': '临河茶肆', 'x': .50, 'y': .50},
                 {'名称': '里巷', 'x': .50, 'y': .08},
                 {'名称': '雾泽', 'x': .15, 'y': .30},
                 {'名称': '苍梧界', 'x': .85, 'y': .25},
                 {'名称': '东馆', 'x': .50, 'y': .75},
                 {'名称': '长干界', 'x': .15, 'y': .72},
                 {'名称': '落霞界', 'x': .85, 'y': .72}],
        '通路': [{'从': '临河茶肆', '到': '里巷'}, {'从': '临河茶肆', '到': '东馆'},
                 {'从': '东馆', '到': '雾泽'}, {'从': '东馆', '到': '苍梧界'},
                 {'从': '东馆', '到': '长干界'}, {'从': '东馆', '到': '落霞界'}],
        '水系': [[0.0, 0.4], [0.5, 0.5], [1.0, 0.7]], '题记': '话界书舟',
    }, realms, source='ai')

    sub = ML.local_view(full, '临河茶肆')
    ok('A10a ★ 取景只留下**当前地点附近**，不是全部 7 处'
       '（用户报的"都出来了"就是这条）',
       sub is not None and 1 < len(sub.places) < len(full.places),
       f'{len(sub.places) if sub else None} vs 全 {len(full.places)}')
    names_sub = [p.name for p in sub.places] if sub else []
    ok('A10b ★ `临河茶肆` 的通路邻居「里巷」「东馆」在内；'
       '跟它没连线的「雾泽」「落霞界」**不在**',
       {'临河茶肆', '里巷', '东馆'} <= set(names_sub)
       and not ({'雾泽', '落霞界'} & set(names_sub)),
       names_sub)
    ok('A10c 当前地点一定在取景里（不然用户找不到自己在哪）',
       '临河茶肆' in names_sub, names_sub)
    ok('A10d ★ 取景后**重新铺满**了画布（不重新缩放的话会挤在角落里）',
       sub is not None and max(max(p.x for p in sub.places) - min(p.x for p in sub.places),
                               max(p.y for p in sub.places) - min(p.y for p in sub.places))
       >= 1.0 - 2 * ML.LOCAL_PAD - 1e-6,
       [f'{p.name}:{p.x},{p.y}' for p in (sub.places if sub else [])])
    ok('A10e 取景后的坐标仍在 0~1 内（飞出去就画到画布外了）',
       sub is not None and all(0.0 <= p.x <= 1.0 and 0.0 <= p.y <= 1.0
                               for p in sub.places),
       [f'{p.name}:{p.x},{p.y}' for p in (sub.places if sub else [])])
    ok('A10f 通路只留**两端都在取景内**的（否则会画一条伸到画布外的线）',
       sub is not None and all(str(l['a']) in names_sub and str(l['b']) in names_sub
                               for l in sub.links), sub.links if sub else None)
    ok('A10g 水系跟着一起缩放（不是留着原坐标）',
       sub is not None and bool(sub.water) and sub.water != full.water,
       sub.water if sub else None)
    ok('A10h `题记` / `source` 保留（图注与"是不是 AI 画的"要照实说）',
       sub is not None and sub.caption == '话界书舟' and sub.source == 'ai',
       f'{sub.caption}/{sub.source}' if sub else None)

    # —— 退化情形：一律返回 None，调用方就**退回总图**（宁可画总图，不画错的局部图）——
    # [EN] —— Degenerate case: always return None, and the caller **falls back to the overview map**
    # [EN] (better to draw the overview map than a wrong local map) ——
    ok('A10i ★ 认不出当前地点 → None（不随便拿一处当地标，那会把人带错地方）',
       ML.local_view(full, '不存在的地方') is None, '')
    ok('A10j 当前地点为空 → None', ML.local_view(full, '') is None, '')
    ok('A10k 布局为空 → None', ML.local_view(None, '临河茶肆') is None, '')
    ok('A10l 只有一处地点 → None（没得取景）',
       ML.local_view(ML.Layout(places=[ML.Place(name='唯一地')]), '唯一地') is None, '')

    # —— 没通路时的兜底：按距离补到 `LOCAL_MIN`，别只剩自己 ——
    # [EN] —— Fallback when there is no path: top up by distance to `LOCAL_MIN`, don't leave only itself ——
    nolink = ML.Layout(source='simple', places=[
        ML.Place(name='A', x=.10, y=.10), ML.Place(name='B', x=.90, y=.90),
        ML.Place(name='C', x=.50, y=.50), ML.Place(name='D', x=.20, y=.80)])
    s2 = ML.local_view(nolink, 'A')
    ok('A10m 没有任何通路 → 按坐标距离补到 `LOCAL_MIN` 处（不至于只剩自己）',
       s2 is not None and len(s2.places) == ML.LOCAL_MIN
       and 'A' in [p.name for p in s2.places],
       [p.name for p in s2.places] if s2 else None)

    # —— 画布层面：取景后画出来的形状数**必须比总图少** ——
    # [EN] —— At the canvas level: after framing, the number of shapes drawn **must be fewer than the
    # [EN] overview map** ——
    ok('A10n ★ 取景后画布上的形状**真的少了**（不是只改数据、照旧画全部）',
       sub is not None
       and len(MM.build_shapes(sub, current='临河茶肆')) <
       len(MM.build_shapes(full, current='临河茶肆')),
       f'{len(MM.build_shapes(sub, current="临河茶肆")) if sub else "-"} vs '
       f'{len(MM.build_shapes(full, current="临河茶肆"))}')

    # —— 接线：界面**不再**走 local_view，改走 here_only ——
    # [EN] —— Wiring: the UI **no longer** goes through local_view, it goes through here_only instead ——
    #
    # ★★ 2026-10-08 用户第二次点名同一个毛病：
    #    「小地图上主角所在的那一处旁边，画着一串**世界层级**的名字（各界、各域）；用户说「这些不是真实的地名」
    #     你让美术画图的时候**只根据当前发生的故事所在的地点画图**
    #     而不是根据整本小说设定画图」。
    #   病根：`local_view` 取的是**设定里的通路邻居**，而那份通路是 AI 摆位时
    #   **编的关系**（`临河茶肆 → 雾泽`）—— 于是"附近"照样是「界」。
    #   所以这两条判据**从"必须调用它"改成"必须不再调用它"**，
    #   并新钉一条"拿不到当天的图时真的用 here_only"。
    # [EN] ★★ 2026-10-08 the user called out the same problem a second time:
    # [EN] "On the minimap, next to where the protagonist is, there is a string of **world-level** names
    # [EN] drawn (各界、各域); the user said "these are not real place names"
    # [EN] when you have the artist draw the map, **draw only based on the place where the current story
    # [EN] takes place**
    # [EN] rather than drawing based on the whole novel's settings".
    # [EN] Root cause: `local_view` takes the **path neighbors in the settings**, and that path is the
    # [EN] So these two criteria **changed from "must call it" to "must no longer call it"**,
    # [EN] and a new one was pinned: "when today's map is unavailable, really use here_only".
    #
    # ★★ 必须**解析 AST 找调用**，不能用 `'local_view' in 源码`：
    #   `_draw_minimap` 的**文档字符串里就写着**这几个名字，子串匹配会被注释骗过
    #   （反例法当场抓到过，见下面 A10o 的说明）。
    # [EN] ★★ Must **parse the AST to find calls**, cannot use `'local_view' in source`:
    # [EN] the **docstring of `_draw_minimap` literally contains** these names, substring matching would be
    # [EN] fooled by the comment
    # [EN] (the counterexample method caught this on the spot, see the A10o note below).
    import ast as _ast
    src_draw = inspect.getsource(G.NovelWorldApp._draw_minimap)
    called: set[str] = set()
    for node in _ast.walk(_ast.parse(textwrap.dedent(src_draw))):
        if isinstance(node, _ast.Call):
            f = node.func
            if isinstance(f, _ast.Attribute):
                called.add(f.attr)
            elif isinstance(f, _ast.Name):
                called.add(f.id)
    ok('A10o ★★ 界面取景**不再**用 `local_view`'
       '（它按设定里 AI 编的通路取景，会把「界」当"附近"拉上屏）',
       'local_view' not in called, sorted(called))
    ok('A10o2 ★★ 当天的图还没出来时，界面**真的调用** `here_only`'
       '（只画当前这一处 —— 写了没人调等于没修；按 AST 判，不看注释）',
       'here_only' in called, sorted(called))
    ok('A10p 界面里**不再有**"全书布局"这一层（`_map_layout` 不再参与绘制）',
       '_map_layout' not in called, sorted(called))


# ══════════════════════════════════════════════════════════════════════
#  A8 组：AI 那条路（打桩，不联网）
# [EN] Group A8: the AI path (stubbed, no network)
# ══════════════════════════════════════════════════════════════════════
async def ai_checks() -> None:
    """AI 那条路（打桩，不联网）。

    ⚠ **整段包在 `try` 里，崩了要留一条红的**（本项目的铁律）：
    变异脚本是按"有没有 `✗` 行"判断抓没抓到的 —— 抛异常时屏幕上一条判据都没有，
    看起来就像"判据不灵"，而实际是"崩了"。这个坑在别的脚本上踩过好几次。
    
        English:
    the AI path (stubbed, no network).
        ⚠ **the whole block is wrapped in `try`; if it crashes, a red line must be left** (an iron rule of this project):
        the mutation script judges whether it caught something by "is there a `✗` line" —— when an exception is thrown there is not a single criterion on screen,
        which looks like "the criteria do not work", when in fact "it crashed". This pit has been stepped into several times on other scripts.
    """
    try:
        await _ai_checks_inner()
    except Exception as e:                                   # noqa: BLE001
        import traceback
        ok('A8 AI 那一组跑得完（不崩）', False, traceback.format_exc()[-300:])
        print(traceback.format_exc()[-900:])


async def _ai_checks_inner() -> None:
    calls: list = []
    real_ask = REPLIES.ask

    def _spy(payload, *, ok=True):
        async def _f(tier, messages, **kw):
            calls.append({'tier': tier, 'purpose': kw.get('purpose'),
                          'want': kw.get('want'), 'max_tokens': kw.get('max_tokens'),
                          'prompt': messages[0]['content'] if messages else ''})
            return REPLIES.Reply(value=payload if ok else None, ok=ok,
                                 raw=json.dumps(payload) if ok else '')
        return _f

    try:
        # ── A8 AI 给的布局被采纳 ──
        # [EN] ── A8 AI-provided layout is adopted ──
        calls.clear()
        REPLIES.ask = _spy({'地点': [{'名称': '临河茶肆', 'x': .2, 'y': .7, '形': '屋'},
                                     {'名称': '城东渡口', 'x': .9, 'y': .8, '形': '渡'}]})
        lay = await ML.ai_layout(['临河茶肆', '城东渡口'], ['靠河', '渡船'])
        ok('A8a AI 布局被采纳（source=ai，两处地点）',
           lay.source == 'ai' and len(lay.places) == 2, f'{lay.source} {len(lay.places)}')
        ok('A8b 走的是 `cheap` 档 + `minimap_layout` 用途 + `want=dict`',
           calls and calls[0]['tier'] == 'cheap'
           and calls[0]['purpose'] == ML.PURPOSE and calls[0]['want'] is dict,
           calls[:1])
        ok('A8c 提示词把**设定里的地名**给了模型（不然它只能瞎编）',
           calls and '临河茶肆' in calls[0]['prompt']
           and '城东渡口' in calls[0]['prompt'], '')
        ok('A8d 提示词里写明了"只许用给出的地点"',
           calls and '只许用' in calls[0]['prompt'], '')

        # ── A8e 失败 → 兜底，**绝不抛** ──
        # [EN] ── A8e failure → fallback, **never throw** ──
        calls.clear()
        REPLIES.ask = _spy({}, ok=False)
        lay2 = await ML.ai_layout(['甲', '乙'], ['', ''])
        ok('A8e ★ AI 拿不到东西 → 退回简化排布（source=simple），不抛异常',
           lay2.source == 'simple' and len(lay2.places) == 2,
           f'{lay2.source} {len(lay2.places)}')

        # ── A8f 抛异常也兜住 ──
        # [EN] ── A8f exceptions are also caught ──
        async def _boom(*a, **k):
            raise RuntimeError('网络断了')
        REPLIES.ask = _boom
        lay3 = await ML.ai_layout(['甲'], [''])
        ok('A8f ★ 调用直接抛异常也兜住（界面不该因为一张图挂掉）',
           lay3.source == 'simple' and len(lay3.places) == 1, lay3.source)

        # ── A8g 没有地点就不叫模型 ──
        # [EN] ── A8g without places, don't call the model ──
        calls.clear()
        REPLIES.ask = _spy({})
        lay4 = await ML.ai_layout([], [])
        ok('A8g 一个地点都没有时**不调模型**（省一次请求）',
           lay4.places == [] and not calls, f'调用 {len(calls)} 次')
    finally:
        REPLIES.ask = real_ask

    # ── A9 缓存往返 ──
    # [EN] ── A9 cache round-trip ──
    tmp = Path(tempfile.mkdtemp(prefix='nws_mapcache_'))
    lay = ML.simple_layout(['甲', '乙'], notes=['靠河', ''])
    ML.save_cached(tmp, lay)
    back = ML.load_cached(tmp)
    ok('A9a 布局缓存能写进运行文件夹、又能读回来',
       back is not None and back.signature() == lay.signature(),
       (back.signature() if back else None))
    ok('A9b 缓存读不到时返回 None（不抛）',
       ML.load_cached(tmp / '不存在') is None, '')
    bad = tmp / ML.CACHE_NAME
    bad.write_text('{坏 json', encoding='utf-8')
    ok('A9c 缓存文件坏了也返回 None（不抛）', ML.load_cached(tmp) is None, '')
    ok('A9d 缓存文件名不在项目文件夹里（**铁律：只写运行文件夹**）',
       ML.CACHE_NAME == '地图布局.json', ML.CACHE_NAME)


# ══════════════════════════════════════════════════════════════════════
#  B 组：真机 + 像素
# [EN] Group B: real machine + pixels
def day_scope_checks() -> None:
    """F. **取景范围只能来自"当前发生的故事"**（用户 2026-10-08）。

    用户原话：
    「小地图上主角所在的那一处旁边是一串世界层级大地名 这个还是不是 **这些不是真实的地名**
     你让美术画图的时候**只根据当前发生的故事所在的地点画图**
     而不是根据**整本小说设定**画图」

    查到底（用户的真实项目）：`地点.yaml` 7 条里 6 条是**世界层级**的名字
    （各界、各域这类**世界层级**的名字），只有一条是主角真正待着的地方
    是他真正待着的地方；而老链路 `ai_layout()` 把这 7 条一次全摆上屏
    （日志 `小地图布局：AI 排好 7 处地点（设定里共 7 处）`）——
    他进运行界面时（当天剧本还没写）看到的就是那张**全书总图**。

    ★ 本组钉的正是"范围从哪来"这件事，一条都不含糊：
      · `places_in_day()`：**拿设定名去当天剧本里匹配**（不是把「场」当地名，
        也不是把整份地点表端出来）；
      · 美术的提示词**只给今天这几处**（给全表就是诱导它画总图）；
      · 一处也画；
      · 全书布局那条链路**没有再上屏**。
    
        English:
    F. **the framing range may only come from "the story currently happening"** (user 2026-10-08).
        the user's exact words:
        "On the minimap, next to the location where the protagonist is, there is a string of world-tier large place names, is this still **these are not real place names**
         when you have art draw the map, **draw only according to the location where the currently happening story is set**
         rather than drawing according to **the entire novel's settings**"
        get to the bottom of it (the user's real project): of the 7 entries in `地点.yaml`, 6 are **world-tier** names
        (names at the **world tier** like various realms and domains), and only one is the place where the protagonist actually stays
        is where he actually stays; and the old pipeline `ai_layout()` put all 7 on screen at once
        When he enters the running UI (the day's script hasn't been written yet), what he sees is that **whole-book overview map**.
        ★ This group pins down exactly "where the scope comes from", without a single ambiguity:
          · `places_in_day()`: **match the setting name against the day's script** (it's not treating "scene" as a place name,
            nor dumping the entire location table);
          · the art prompt **only gives today's few locations** (giving the whole table just induces it to draw the overview map);
          · draw a single location too;
          · the whole-book layout chain **is no longer pushed to screen**.
    """
    from image_gen import map_layout as ML

    # ── F1 匹配：长串「场」也能命中真地名；楼内位置不算地点 ──
    #  夹具取自用户项目的**真实数据**（`地点.yaml` 7 条 + 第 2 次模拟的分拍）。
    # [EN] ── F1 Matching: a long string 「场」 can also hit a real place name; locations inside a building
    # [EN] don't count as places ──
    # [EN] The fixture is taken from the **real data** of the user's project (`地点.yaml` 7 entries + the
    # [EN] beats of the 2nd simulation).
    known = ['临河茶肆', '雾泽', '云洲', '东馆', '北荒', '南沼', '西陵']
    real_beats = [
        {'场': '临河茶肆堂内·雨夜·柜台前', '发生': '周奉抹了把脸推门进来。'},
        {'场': '同夜·侧案旁', '发生': '丁把周奉叫到侧案边添水。'},
        {'场': '次日·茶堂', '发生': '雨停，堂里两排矮桌坐满。'},
        {'场': '茶堂檐下', '发生': '阿九蹲在檐下磨爪。'},
        {'场': '茶堂·白衣席前', '发生': '周奉端茶先到白衣席前。'},
    ]
    got = ML.places_in_day(real_beats, known, extra='临河茶肆')
    ok('F1 ★★★ 拿设定名去**当天剧本**里匹配 —— 「临河茶肆堂内·雨夜·柜台前」'
       '这种长串也命中「临河茶肆」；「侧案旁 / 檐下」这种**楼内位置不算地点**',
       got == ['临河茶肆'], str(got))
    ok('F1b ★★★ 用户报的那几个**世界层级名一个都不进来**'
       '（剧本里今天没到过雾泽/云洲/东馆/西陵）',
       not ({'雾泽', '云洲', '东馆', '西陵', '北荒', '南沼'}
            & set(got)), str(got))

    # ── F2 哪天真的去了「界」，那天就该画它（别矫枉过正）──
    # [EN] ── F2 When the day actually goes to 「界」, that day should draw it (don't overcorrect) ──
    away = [{'场': '雾泽·鬼市', '发生': '周奉被拖进鬼市。'},
            {'场': '雾泽·摊前', '发生': '他看见自己在摊上被明码标价。'}]
    got2 = ML.places_in_day(away, known, extra='雾泽')
    ok('F2 ★★ 哪天戏真的走到「雾泽」，那天图上**就该有**它'
       '（范围由剧情定 —— 不是把"界"一刀切禁掉）',
       got2 == ['雾泽'], str(got2))

    # ── F3 「这里」永远最前；剧情里的先后次序 = 图上的先后 ──
    # [EN] ── F3 「这里」 is always first; the order in the story = the order on the map ──
    two = [{'场': '临河茶肆', '发生': 'x'}, {'场': '东馆', '发生': 'y'}]
    ok('F3 ★ 当前场景排最前，其余按**剧情里出现的先后**',
       ML.places_in_day(two, known, extra='东馆') == ['东馆', '临河茶肆'],
       str(ML.places_in_day(two, known, extra='东馆')))
    ok('F3b 「场 / 发生 / 推进」三栏都看（地点写在「发生」里也算）',
       ML.places_in_day([{'场': '', '发生': '他从临河茶肆出来，进了东馆。'}],
                        known, extra='') == ['临河茶肆', '东馆'],
       str(ML.places_in_day([{'场': '', '发生': '他从临河茶肆出来，进了东馆。'}],
                            known, extra='')))
    ok('F3c 设定里一个地点都没有时：只留当前一处（不硬编）',
       ML.places_in_day(two, [], extra='临河茶肆') == ['临河茶肆']
       and ML.places_in_day(two, [], extra='') == [], '')

    # ── F4 `here_only`：兜底就是"当前这一处" ──
    # [EN] ── F4 `here_only`: the fallback is "the current place" ──
    one = ML.here_only('临河茶肆')
    ok('F4 ★★ 兜底只画**当前这一处**（用户要的就是"只根据当前故事所在地点"）',
       one is not None and [p.name for p in one.places] == ['临河茶肆'],
       [p.name for p in (one.places if one else [])])
    ok('F4b 还不知道在哪儿 → `None`（调用方走"还没有地点设定"的提示，不编）',
       ML.here_only('') is None and ML.here_only('  ') is None, '')
    ok('F4c 兜底图的 `source` 是 `here`（界面要照实说这是兜底，'
       '别让人以为"今天就这一处"）',
       one is not None and one.source == 'here', getattr(one, 'source', None))

    # ── F5 全书布局那条链路**没有再上屏** ──
    # [EN] ── F5 The whole-book layout chain **is no longer rendered on screen** ──
    import ast as _a
    import inspect
    import textwrap as _t
    from gui.app_flet import NovelWorldApp
    from sim.loop import RunLoop

    ok('F5 ★★★ 界面里**没有**任何地方再调 `ai_layout`'
       '（那条链路画的正是"整本小说设定的地图"）',
       not _calls_named(NovelWorldApp, 'ai_layout'),
       str(_calls_named(NovelWorldApp, 'ai_layout')[:3]))
    # ⚠ 这两条也走 **AST**：`_reset_map_state` 的注释里写着"以前这里叫
    #   `_ensure_map_layout()`、放到 run_task 里跑"——拿整段源码查会假红。
    # [EN] ⚠ These two also use **AST**: the comment in `_reset_map_state` says "this used to be called
    # [EN] `_ensure_map_layout()`, run inside run_task" —— searching the whole source would give a false
    # [EN] red.
    ok('F5b ★★ 开一轮时**不再问模型**要全书布局'
       '（顺手省掉每次开轮的一次调用；按 AST 判，不看注释里提没提）',
       not _calls_in(NovelWorldApp._reset_map_state, 'ai_layout')
       and not _calls_in(NovelWorldApp._reset_map_state, 'run_task'), '')
    ok('F5c ★★ `places_in_day` 那条新链路里**没有**把整份设定表直接当选景的地方'
       '（`places_from_settings` 只当"匹配用的词典"，不当"图上画什么"）',
       'places_from_settings' not in inspect.getsource(RunLoop._draw_day_map)
       and 'day_names_from_beats' not in inspect.getsource(RunLoop._draw_day_map), '')

    # ── F6 美术的提示词：只给今天这几处 ──
    # [EN] ── F6 The artist's prompt: only give today's few places ──
    #
    # ⚠ 查**提示词字面量**，不查整个方法源码：方法里有大段注释在讲"以前喂的是什么"
    #   （引用旧文案），拿整段源码查会被自己的注释骗过（第一版就这么假红了）。
    # [EN] ⚠ Check the **prompt literal**, not the whole method source: the method has large comments
    # [EN] talking about "what used to be fed"
    # [EN] (quoting the old text), searching the whole source would be fooled by its own comments (the
    # [EN] first version went falsely red exactly like this).
    art_src = inspect.getsource(
        __import__('crew.agents', fromlist=['x']).Art.draw_day_map)
    prompt = _prompt_of(art_src, 'prompt')
    ok('F6 ★★★ 美术的提示词里**不再有"设定里真实存在的地点"那份全表**'
       '（喂全表 = 诱导它把世界总图画出来 —— 这才是病根）',
       bool(prompt) and '设定里真实存在的地点' not in prompt
       and '这份清单就是这张图的全部内容' in prompt,
       prompt[:120].replace('\n', ' ') or '(没取到提示词字面量)')
    ok('F6b ★★ 提示词明确写了"清单以外的名字一个也不许出现，也不要在'
       '说明/题记里提到它们"（连提都不许提）',
       '清单以外' in prompt and '题记' in prompt, '')
    ok('F6c ★★ 提示词点明了"各界/各域/各国那些大地方一个都不要画"',
       '各界' in prompt and '全书总图' in prompt, '')


def _prompt_of(src: str, var: str = 'prompt') -> str:
    """从方法源码里抠出那个 **f-string 提示词的字面量**。

    为什么要抠：方法里有大段注释（讲"以前喂的是什么"），直接查整段源码会被
    注释骗过 —— 判据必须只看**真正发给模型的那段字**。
    
        English:
    Extract that **f-string prompt literal** from the method source.
        Why extract it: the method has large comment blocks (explaining "what used to be fed in"), and querying the whole source block directly would be
        fooled by the comments — the criterion must only look at **the exact text actually sent to the model**.
    """
    import re as _re
    m = _re.search(var + r'\s*=\s*f?"""(.*?)"""', src, _re.S)
    return m.group(1) if m else ''


def _calls_named(cls, attr: str) -> list[str]:
    """整个类（所有方法）里有没有人调用名为 `attr` 的函数（**AST 判，不看注释**）。
        English:
    Whether anyone in the entire class (all methods) calls a function named `attr` (**decided by
    AST, not comments**).
    """
    out: list[str] = []
    for name, fn in _methods(cls):
        if _calls_in(fn, attr):
            out.append(name)
    return out


def _calls_in(fn, attr: str) -> bool:
    """**单个函数**里有没有调用名为 `attr` 的东西（AST）。
        English:
    Whether a **single function** calls something named `attr` (AST).
    """
    import ast as _a
    import inspect
    import textwrap as _t
    try:
        tree = _a.parse(_t.dedent(inspect.getsource(fn)))
    except Exception:                                            # noqa: BLE001
        return False
    for n in _a.walk(tree):
        if isinstance(n, _a.Call) and attr in _a.unparse(n.func):
            return True
    return False


def _methods(cls):
    import inspect
    for name, fn in inspect.getmembers(cls, predicate=inspect.isfunction):
        yield name, fn


# ══════════════════════════════════════════════════════════════════════
def day_map_checks() -> None:
    """E. **当天的小地图**（用户 2026-10-07：「周围都是小说 而不是实际地图」）。

    用户的要求是这个功能的全部规格：
    「请把绘制地图改到**导演写完当前的小说之后** 有剧组**美术**
      根据**当天剧情涉及到的地点**进行绘制」

    ★ 旧做法为什么错：小地图画的是**全书布局**的一部分（当前地点 + 通路邻居，
      不足按距离补满 6 处）—— **补满就等于总图**，于是图上还是那些
      "雾泽 / 里巷 / 东馆"（书里的分部名），不是"这场戏在哪儿"。
      截图证据：「「临河茶肆」附近 6 处」—— 6 就是上限，说明它填满了。

    这一组钉四件事：**范围**（只今天涉及的）· **时机**（剧本之后）·
    **谁画的**（剧组美术）· **拿不到不编**。
    
        English:
    E. **The day's minimap** (user 2026-10-07: "it's all novel around it, not an actual map").
        The user's requirement is the entire spec for this feature:
        "Please change the map drawing to **after the director finishes writing the current novel**, with the crew's **art
          drawing it based on **the locations involved in the day's plot**"
        ★ Why the old approach was wrong: the minimap drew part of the **whole-book layout** (current location + path neighbors,
          topped up to 6 locations by distance) — **topping up equals the overview map**, so the map still showed those
          "Mistmarsh / Inner Alley / East Hall" (the branch names in the book), not "where this scene is".
          Screenshot evidence: "6 locations near 「临河茶肆」" — 6 is the cap, meaning it filled up.
        This group pins down four things: **scope** (only today's involved) · **timing** (after the script) ·
        **who draws it** (crew art) · **don't make it up if you can't get it**.
    """
    from image_gen import map_layout as ML
    from director.day_plan import _section                        # noqa: SLF001

    # ── E1 取地点：从分拍的「场」里取，去重、保序、「这里」最前 ──
    # [EN] ── E1 Extract places: extract from the 「场」 of the beats, dedupe, preserve order, 「这里」 first ──
    beats = [{'场': '堂内', '发生': 'x'}, {'场': '门口', '发生': 'y'},
             {'场': '堂内', '发生': 'z'}, {'场': '', '发生': 'w'},
             {'场': '这是一句不是地名的话所以该被丢掉', '发生': 'v'}]
    names = ML.day_names_from_beats(beats, extra='后巷')
    ok('E1 ★ 今天涉及的地点 = 「这里」+ 分拍里的「场」（去重、保序、滤掉句子的）',
       names == ['后巷', '堂内', '门口'], str(names))

    # ── E2 **不补齐**：今天几处就画几处（旧做法补满 6 处 = 总图）──
    # [EN] ── E2 **Do not top up**: draw however many places there are today (the old way topped up to 6
    # [EN] places = overview map) ──
    raw = {'地点': [{'名称': '堂内', 'x': 0.5, 'y': 0.6},
                    {'名称': '门口', 'x': 0.8, 'y': 0.35}],
           '通路': [['堂内', '门口']], '题记': '今日'}
    lay = ML.day_layout(raw, ['堂内', '门口'], here='堂内')
    ok('E2 ★★ 当天地图**不补齐**别的地点（今天 2 处就画 2 处，不是全书）',
       [p.name for p in lay.places] == ['堂内', '门口'],
       str([p.name for p in lay.places]))
    all_names = ['堂内', '门口', '里巷', '山海', '梦话', '东馆', '雾泽']
    lay_all = ML.day_layout(raw, all_names, here='堂内')
    ok('E2b ★★ 白名单里有 7 处、今天只涉及 2 处 → 图上仍然只有 2 处'
       '（"周围都是别的书名"就是这么消掉的）',
       len(lay_all.places) == 2, f'{len(lay_all.places)} 处')

    # ── E3 模型编的地名**进不来** ──
    # [EN] ── E3 Model-fabricated place names **cannot get in** ──
    bad = {'地点': [{'名称': '堂内', 'x': 0.5, 'y': 0.6},
                    {'名称': '隔壁的客栈', 'x': 0.2, 'y': 0.2}], '通路': []}
    lay_bad = ML.day_layout(bad, ['堂内', '门口'], here='堂内')
    ok('E3 ★ 模型顺手编的地名被白名单挡掉（画上去就是"编的"）',
       '隔壁的客栈' not in [p.name for p in lay_bad.places],
       str([p.name for p in lay_bad.places]))

    # ── E4 「这里」必须在图上（朱砂点画不出来最丢人）──
    # [EN] ── E4 「这里」 must be on the map (failing to draw the cinnabar dot is the most embarrassing) ──
    lay_here = ML.day_layout({'地点': [{'名称': '门口', 'x': 0.8, 'y': 0.3}]},
                             ['堂内', '门口'], here='堂内')
    ok('E4 ★ 「现在人在哪儿」一定画在图上（模型漏了就补在中心偏下）',
       '堂内' in [p.name for p in lay_here.places],
       str([(p.name, p.x, p.y) for p in lay_here.places]))

    # ── E5 通路**两种形状**都认（提示词给的是 `[["甲","乙"]]`）──
    # [EN] ── E5 The path recognizes **both shapes** (the prompt gives `[["甲","乙"]]`) ──
    ok('E5 ★ 通路认得了列表形状（只认字典时会被静默丢掉，连线全没）',
       bool(ML.day_layout({'地点': [{'名称': '堂内'}, {'名称': '门口'}],
                           '通路': [['堂内', '门口']]},
                          ['堂内', '门口'], here='堂内').links))
    ok('E5b 字典形状也照旧认（老提示词那条路不能被弄坏）',
       bool(ML.day_layout({'地点': [{'名称': '堂内'}, {'名称': '门口'}],
                           '通路': [{'从': '堂内', '到': '门口'}]},
                          ['堂内', '门口'], here='堂内').links))

    # ── E6 取不到范围 → 返回 None（调用方退回旧做法，**不编图**）──
    # [EN] ── E6 Range unavailable → return None (the caller falls back to the old way, **does not
    # [EN] fabricate a map**) ──
    ok('E6 ★ 今天没有地点信息时不硬画（返回 None，退回"附近取景"）',
       ML.day_layout(raw, [], here='') is None
       and ML.day_layout(raw, ['  ', ''], here='') is None)

    # ── E7 接线：时机（剧本之后）+ 谁画的（美术）+ 界面读它 ──
    # [EN] ── E7 wiring: timing (after the script) + who drew it (art) + the UI reads it ──
    #
    # ⚠ 这一组第一版全红，**三条都是判据自己量错了**（不是代码错）：
    #   ① 用 `ast.walk()` 的顺序当"源码先后"—— walk 是**广度优先**，
    #      顺序跟写在哪儿无关。要看先后必须比 `node.lineno`。
    #   ② `day_map_note` 不在 `_compose_day` 里，它在它调用的 `_draw_day_map` 里
    #      —— 判"谁画的"要**顺着两级看**：`_compose_day` 调 `_draw_day_map`，
    #      后者才用 `_crew_ctx` + `studio.day_map_note`。
    #   ③ GUI 那条比的是字符串位置，而 `local_view` 在方法 **docstring**
    #      里就出现过一次（索引 139）→ 比在了注释上。
    #      改 AST：看 `lay = self._map_day` 那一步在 `local_view(...)` 调用**之前**。
    # [EN] ⚠ This group was all red in v1, **all three were the criteria measuring themselves wrong** (not
    # [EN] code bugs):
    # [EN] ① Using `ast.walk()` order as "source order" — walk is **breadth-first**,
    # [EN] the order has nothing to do with where it's written. To see order you must compare
    # [EN] `node.lineno`.
    # [EN] ② `day_map_note` is not in `_compose_day`, it's in `_draw_day_map` which it calls
    # [EN] —— judging "who drew it" requires **looking two levels down**: `_compose_day` calls
    # [EN] `_draw_day_map`,
    # [EN] and the latter is what uses `_crew_ctx` + `studio.day_map_note`.
    # [EN] ③ The GUI one compares string position, and `local_view` appears once in the method
    # [EN] **docstring**
    # [EN] already (index 139) → it compared against the comment.
    # [EN] Fix the AST: check that the `lay = self._map_day` step is **before** the `local_view(...)` call.
    import ast
    import inspect
    import textwrap as _tw
    from sim.loop import RunLoop
    from gui.app_flet import NovelWorldApp

    def _calls(fn) -> list[tuple[int, str]]:
        """`[(行号, 被调函数名)]` —— **带行号**，才能比先后。
                English:
        `[(line number, called function name)]` — **with line numbers**, so ordering can be compared.
        """
        tree = ast.parse(_tw.dedent(inspect.getsource(fn)))
        out = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                out.append((int(getattr(n, 'lineno', 0)), ast.unparse(n.func)))
        return sorted(out)

    c1 = _calls(RunLoop._compose_day)
    i_compose = next((ln for ln, f in c1 if f.endswith('compose')), -1)
    i_map = next((ln for ln, f in c1 if 'draw_day_map' in f), -1)
    ok('E7 ★★ 当天地图排在**当天剧本写完之后**（顺序是要求的一部分）',
       i_compose > 0 and i_map > i_compose,
       f'第 {i_compose} 行写剧本 → 第 {i_map} 行画图')

    dm_src = inspect.getsource(RunLoop._draw_day_map)
    ok('E7b ★★ 当天地图由**剧组美术**画（`_crew_ctx` + `studio.day_map_note`）',
       'day_map_note' in dm_src and '_crew_ctx' in dm_src
       and "'art'" not in dm_src,
       [l.strip() for l in dm_src.split('\n') if 'day_map_note' in l][:1])
    ok('E7b2 ★★ 取景范围取自**当天剧本**（`places_in_day` 拿设定名去剧本里匹配）'
       '—— 不是"把分拍的场当地名"，更不是整本设定',
       'places_in_day' in dm_src and 'day_names_from_beats' not in dm_src,
       [l.strip() for l in dm_src.split('\n') if 'places_in_day' in l][:1])
    ok('E7b3 ★★ 给美术的 `places` 是**今天这几处**，不是整份设定地点表'
       '（喂全表 = 诱导它把世界总图画出来，那正是用户报的毛病）',
       'places=allowed' in dm_src and 'places=known' not in dm_src,
       [l.strip() for l in dm_src.split('\n') if 'places=' in l][:2])
    ok('E7b4 ★★ **一处也画**（今天戏就在这一处，那张图就该只有这一处；'
       '退回"附近取景"反而会把设定里的邻居拉上屏）',
       'if len(names) <= 1:' not in dm_src and 'if not names:' in dm_src,
       [l.strip() for l in dm_src.split('\n') if 'if not names' in l][:1])

    # ⚠ 这一条**必须走 AST**：`local_view` 在 docstring 里就出现过，
    #   按行文本找会找到注释上，怎么改源码都是假红。
    # [EN] ⚠ This one **must go through AST**: `local_view` appears in the docstring,
    # [EN] searching by line text will find the comment, and no source change will clear the false red.
    gtree = ast.parse(_tw.dedent(inspect.getsource(NovelWorldApp._draw_minimap)))
    g_calls = [(int(getattr(n, 'lineno', 0)), ast.unparse(n.func))
               for n in ast.walk(gtree) if isinstance(n, ast.Call)]
    ln_local = next((ln for ln, f in g_calls if 'local_view' in f), -1)
    ln_here = next((ln for ln, f in g_calls if 'here_only' in f), -1)
    # ⚠ 找的是**调用** `_day_map_of_loop()`（不是赋值读 `_map_day` ——
    #   第一版按名字找赋值，结果 ln_day 一直是 -1）。
    # [EN] ⚠ What's searched for is the **call** to `_day_map_of_loop()` (not the assignment reading
    # [EN] `_map_day` ——
    # [EN] v1 searched for the assignment by name, so ln_day stayed -1).
    ln_day = next((ln for ln, f in g_calls if 'day_map_of_loop' in f), -1)
    ok('E7c ★★ 界面小地图**优先**用当天地图；拿不到才退回"只画当前这一处"'
       '（`here_only` —— 不是按设定通路取景的 `local_view`）',
       ln_day > 0 and ln_here > ln_day and ln_local < 0,
       f'第 {ln_day} 行读当天地图 → 第 {ln_here} 行 here_only；'
       f'local_view 出现在第 {ln_local} 行（-1 = 没调用）')
    ok('E7d ★ 开新的一天会重画小地图（否则左栏还停着昨天那张）',
       "day_start" in inspect.getsource(NovelWorldApp._on_divider)
       and '_draw_minimap' in inspect.getsource(NovelWorldApp._on_divider),
       '')

    # ── E8 落盘分文件：当天地图不许覆盖美术指导 ──
    # [EN] ── E8 split files on disk: the same-day map must not overwrite the art direction ──
    from crew import studio as ST
    ok('E8 ★★ 当天地图写自己的文件（和「美术指导.md」分开 —— '
       '两者 role 都是 art，同一个文件会被天天覆盖）',
       ST.Studio.FILE_DAY_MAP != ST.Studio.ARTIFACT.get('art'),
       f'{ST.Studio.FILE_DAY_MAP} vs {ST.Studio.ARTIFACT.get("art")}')


def mask_bbox(png, rgb, tol=70) -> dict:
    """找某种独占色的 bbox（用来定位画布 / 当前位置标记）。
        English:
    Find the bbox of some exclusive color (used to locate the canvas / current-position marker).
    """
    from PIL import ImageChops
    im = VU.image_of(png)
    r, g, b = im.split()
    m = ImageChops.multiply(
        r.point(lambda v: 255 if abs(v - rgb[0]) < tol else 0),
        ImageChops.multiply(
            g.point(lambda v: 255 if abs(v - rgb[1]) < tol else 0),
            b.point(lambda v: 255 if abs(v - rgb[2]) < tol else 0)))
    n = m.histogram()[255]
    bb = m.getbbox()
    if not n or not bb:
        return {'n': 0}
    # 质心（用像素平均，不用 bbox 中心：标记是斜的/多点分布时更稳）
    # [EN] centroid (use pixel average, not bbox center: more stable when markers are slanted/multi-point)
    xs = ys = 0
    px = m.load()
    for y in range(bb[1], bb[3]):
        for x in range(bb[0], bb[2]):
            if px[x, y]:
                xs += x
                ys += y
    return {'n': n, 'x0': bb[0], 'y0': bb[1], 'x1': bb[2] - 1, 'y1': bb[3] - 1,
            'w': bb[2] - bb[0], 'h': bb[3] - bb[1],
            'cx': xs / n, 'cy': ys / n}


def ink_inside(png, box, paper_rgb, tol=26) -> int:
    """在一个矩形里数"不是纸色"的像素 = 图上画了多少东西。
        English:
    Count "non-paper-color" pixels inside a rectangle = how much is drawn on the map.
    """
    im = VU.image_of(png)
    px = im.load()
    W, H = im.size
    n = 0
    for y in range(max(0, box['y0']), min(H, box['y1'] + 1)):
        for x in range(max(0, box['x0']), min(W, box['x1'] + 1)):
            if not VU._near(px[x, y], paper_rgb, tol):
                n += 1
    return n


def _place_labels(canvas) -> set[str]:
    """画布上所有**地点标签**（`Text` 形状里的字）。

    用途：断言"画布上出现了哪些地名" —— 这是**上屏证据**，比读数据对象硬：
    `build_shapes` 可能被喂了 7 处，但没画出来的话屏幕上就没有——
    这里数的是"真的画上去的"。
    
        English:
    All **location labels** on the canvas (the characters inside `Text` shapes).
        Purpose: assert "which place names appear on the canvas" — this is **on-screen evidence**, harder than reading data objects:
        `build_shapes` may be fed 7 locations, but if they aren't drawn there's nothing on screen —
        what's counted here is "what actually got drawn".
    """
    out: set[str] = set()
    for s in (getattr(canvas, 'shapes', None) or []):
        txt = getattr(s, 'value', None)
        if isinstance(txt, str) and txt.strip():
            out.add(txt.strip())
    return out


#: 用户那本小说里属于**世界层级**的地点名（不是"人真的待着的地方"）。
#: 小地图上一次都不该出现它们 —— 除非当天的戏真的走到了那儿。
# [EN] : place names in the user's novel that belong to the **world tier** (not "places people actually
# [EN] stay").
# [EN] : they should never appear even once on the minimap —— unless the day's scene actually went
# [EN] there.
REALM_NAMES = ('雾泽', '云洲', '东馆', '西陵', '北荒', '南沼')


def _realm_labels(labels) -> list[str]:
    """标签里有没有命中那些**世界层级名**（图上用的是简称，所以按前缀判）。

    ⚠ 图上写的是简称（`Place.label()` 取前 3 字），所以「西陵」在屏幕上
      是「唐传奇」—— 拿全名做等值比较**抓不到它**（第一版就这么假绿了）。
    
        English:
    Whether the labels hit those **world-level names** (the map uses abbreviations, so judge by
    prefix).
        ⚠ The map shows abbreviations (`Place.label()` takes the first 3 characters), so 「西陵」 on screen
          is 「唐传奇」 — equality comparison against the full name **won't catch it** (the first version went falsely green this way).
    """
    out = []
    for lab in (labels or ()):
        s = str(lab).strip()
        if not s:
            continue
        if any(r.startswith(s) or s.startswith(r) for r in REALM_NAMES):
            out.append(s)
    return out


def _has_label(labels, name: str) -> bool:
    """画布上有没有某个地点的标签（**按前缀判**：图上写的是前 3 字的简称）。
        English:
    Whether the canvas has a label for some location (**judged by prefix**: the map shows the
    first-3-character abbreviation).
    """
    return any(str(l).strip().startswith(str(name).strip()[:3])
               for l in (labels or ()) if str(l).strip())


# ══════════════════════════════════════════════════════════════════════
#  G 组：**行为级** —— 真的跑一遍 `RunLoop._draw_day_map`
# [EN] Group G: **behavior level** —— actually run `RunLoop._draw_day_map` once
# ══════════════════════════════════════════════════════════════════════
#  ★★ 为什么必须有这一组：F 组全是源码/AST 判据（"接线接对了"），
#     而这一组是**真的把那一步跑一遍**、看它到底把什么交给了美术、
#     又拿回了什么。本项目的老规矩：行为级 > 源码级。
# [EN] ★★ Why this group must exist: group F is all source/AST criteria ("the wiring is correct"),
# [EN] while this group **actually runs that step** and sees what it hands to the art,
# [EN] and what it gets back. This project's old rule: behavior level > source level.
async def day_loop_checks() -> None:
    """G. `loop._draw_day_map` 真的跑一遍（打桩美术，不联网）。

    夹具直接取**用户那本小说的真实数据**（`地点.yaml` 7 条 + 第 2 次模拟的分拍）
    —— 这样"用户报的那个毛病能不能被抓住"是**可复现**的。
    
        English:
    G. `loop._draw_day_map` actually runs once (art is stubbed, no network).
        The fixture directly uses **the real data from the user's novel** (`地点.yaml`'s 7 entries + the shot breakdown of the 2nd simulation)
        — this way, "can the bug the user reported be caught" is **reproducible**.
    """
    import types
    from crew.agents import CrewNote
    from sim.loop import RunLoop

    KNOWN = ['临河茶肆', '雾泽', '云洲', '东馆', '北荒', '南沼', '西陵']
    BEATS = [{'场': '临河茶肆堂内·雨夜·柜台前', '发生': '周奉抹了把脸推门进来。'},
             {'场': '同夜·侧案旁', '发生': '丁把周奉叫到侧案边添水。'},
             {'场': '次日·茶堂', '发生': '雨停，堂里两排矮桌坐满。'},
             {'场': '茶堂檐下', '发生': '阿九蹲在檐下磨爪。'}]

    class FakeStudio:
        def __init__(self):
            self.seen: list = []
            # ★ 2026-10-08：`day_map_note` 多了 `layers`（开卷定下的三级底图里
            #   今天该用的那几层）。桩必须跟着收，否则一个 TypeError 被
            #   `_draw_day_map` 的 except 吞掉 → **表现成"美术没给出图"**，
            #   判据全红而看不出真正原因（实测踩过）。
            # [EN] ★ 2026-10-08: `day_map_note` gained `layers` (of the three-tier base map fixed at the open
            # [EN] of the book, the layers to use today). The stub must follow, otherwise a TypeError is
            # [EN] swallowed by `_draw_day_map`'s except → **it manifests as "the art produced no image"**,
            # [EN] all criteria go red and the real cause is invisible (hit this in practice).
            self.seen_layers: list = []
            self.reply = CrewNote(role='art', ok=True, title='今天 1 处',
                                  data={'地点': [{'名称': '临河茶肆', 'x': .5, 'y': .6}],
                                        '通路': [], '题记': '一夜'})

        async def day_map_note(self, ctx, *, here='', places=None, layers=None):
            self.seen.append(list(places or []))
            self.seen_layers.append(list(layers or []))
            return self.reply

    def make_loop(st: FakeStudio, seen_scene: list | None = None,
                  seen_rec: list | None = None, atlas=None):
        lp = RunLoop.__new__(RunLoop)                    # 不走 __init__（要一整个世界）
        # [EN] Don't go through __init__ (needs a whole world)
        lp.world = types.SimpleNamespace(
            scene='临河茶肆', game_day=1,
            worldview_text='【地点】' + '、'.join(KNOWN) + '\n【别的】…')
        lp.db = None
        lp.agents = []
        lp._current_day = 1
        lp._last_place = '临河茶肆'
        lp.studio = st
        # 三级底图：**默认 None**（夹具里的这本书没生成过底图）——
        # 那条路要走"退回每天现摆位"，与 G 组原本的期望一致。
        # [EN] Three-tier base map: **default None** (the book in the fixture has never generated a base map)
        # [EN] ——
        # [EN] that path must take "fall back to laying out fresh each day", consistent with group G's original
        # [EN] expectation.
        lp.atlas = atlas
        lp.runfolder = types.SimpleNamespace(root=Path(tempfile.mkdtemp(
            prefix='nws_dm_')))
        lp._push_narrative = lambda *a, **k: None        # 上屏那一步与本组无关
        # ★ 2026-10-08：`_log_day_map` 现在还会**通知界面重画一次小地图**
        #   （用户报的「小地图一直没画」）。夹具要看得见那次通知，
        #   也要看得见它**没有**往审读台账里塞一行假的"换场景"。
        # [EN] The on-screen step is irrelevant to this group
        # [EN] ★ 2026-10-08: `_log_day_map` now also **notifies the UI to redraw the minimap once**
        # [EN] (the user-reported "minimap never drawn"). The fixture must see that notification,
        # [EN] and must also see that it does **not** stuff a fake "scene change" line into the review ledger.
        lp._clock_segment = lambda: '戌时'
        lp._review_record_only = (
            (lambda *a, **k: seen_rec.append(a)) if seen_rec is not None
            else (lambda *a, **k: None))
        lp._on_scene = ((lambda payload: seen_scene.append(payload))
                        if seen_scene is not None else None)
        lp._warn_once = lambda *a, **k: None
        return lp

    ds = types.SimpleNamespace(day=1, beats=BEATS, story='雨敲在船板上，不密，却重。')

    # ── G1 给美术的 `places` = **今天这几处**（不是整份设定表）──
    # [EN] ── G1 `places` given to the art = **these spots today** (not the whole setting table) ──
    st = FakeStudio()
    lp = make_loop(st)
    await lp._draw_day_map(ds)
    ok('G1 ★★★ 真的跑一遍：交给美术的地点清单是**今天这几处**'
       '（临河茶肆一处），**不是整份设定表**（7 条里 6 条是"界"）',
       st.seen == [['临河茶肆']], str(st.seen))
    ok('G1b ★★★ 当天地图定下来之后，图上**没有**一个世界层级名'
       '（用户报的那四个一个都不进来）',
       lp.day_map is not None
       and not (set(REALM_NAMES) & {p.name for p in lp.day_map.places}),
       str([p.name for p in (lp.day_map.places if lp.day_map else [])]))
    ok('G1c 当天这张图**认了**（`loop.day_map` 有值）—— 界面就能用它',
       lp.day_map is not None and [p.name for p in lp.day_map.places] == ['临河茶肆'],
       str([p.name for p in (lp.day_map.places if lp.day_map else [])]))

    # ── G2 今天只涉及一处，**照样画**（以前直接 return，退回全书取景）──
    # [EN] ── G2 today involves only one spot, **still draw it** (previously returned directly, falling
    # [EN] back to whole-book framing) ──
    ok('G2 ★★★ 一处也画（旧代码在这里 `return`，界面就退回"附近取景"→ '
       '又把设定里的邻居拉上屏）',
       lp.day_map is not None, 'day_map 是 None（退回旧路了）')

    # ── G3 `MINIMAP_AI=false` → 不叫模型，走简化排布 ──
    # [EN] ── G3 `MINIMAP_AI=false` → don't call the model, use simplified layout ──
    CFG.set('MINIMAP_AI', 'false')
    try:
        st2 = FakeStudio()
        lp2 = make_loop(st2)
        await lp2._draw_day_map(ds)
        ok('G3 ★★ 关掉 `MINIMAP_AI`：**美术一次都没被叫**，图仍然有'
           '（走确定性排布，不联网零成本）',
           st2.seen == [] and lp2.day_map is not None
           and lp2.day_map.source == 'simple'
           and [p.name for p in lp2.day_map.places] == ['临河茶肆'],
           f'调用 {st2.seen} · source={getattr(lp2.day_map, "source", None)}')
    finally:
        CFG.set('MINIMAP_AI', 'true')

    # ── G4 美术没给出东西 → **保持 None**（界面走"只画当前一处"）──
    # [EN] ── G4 the art produced nothing → **keep None** (the UI falls back to "draw only the current
    # [EN] spot") ──
    st3 = FakeStudio()
    st3.reply = CrewNote(role='art', ok=False, why='模型没给出')
    lp3 = make_loop(st3)
    await lp3._draw_day_map(ds)
    ok('G4 ★ 美术没给出 → `day_map` 保持 `None`（界面只画当前一处，'
       '**绝不**退回全书布局）',
       lp3.day_map is None, str(lp3.day_map))

    # ── G5 剧本里真的走到了「雾泽」→ 那天就该画它（别矫枉过正）──
    # [EN] ── G5 the script really went to "雾泽" → that day it should be drawn (don't overcorrect) ──
    away = types.SimpleNamespace(
        day=2, beats=[{'场': '雾泽·鬼市', '发生': '周奉被拖进鬼市。'}], story='')
    st4 = FakeStudio()
    st4.reply = CrewNote(role='art', ok=True, title='2 处',
                         data={'地点': [{'名称': '临河茶肆', 'x': .5, 'y': .6},
                                        {'名称': '雾泽', 'x': .2, 'y': .2},
                                        {'名称': '隔壁的客栈', 'x': .9, 'y': .9}],
                               '通路': [], '题记': '鬼市'})
    lp4 = make_loop(st4)
    lp4.world.scene = '临河茶肆'
    await lp4._draw_day_map(away)
    ok('G5 ★★ 范围由**剧情**定：哪天戏真走到了「雾泽」，那天就该有它',
       '雾泽' in st4.seen[0], str(st4.seen))
    ok('G5b 越界的地名照样被挡（模型给"隔壁的客栈"进不来）',
       '隔壁的客栈' not in [p.name for p in (lp4.day_map.places
                                              if lp4.day_map else [])],
       str([p.name for p in (lp4.day_map.places if lp4.day_map else [])]))

    # ── G6 ★★★ 图画好之后**要主动通知界面重画一次**（2026-10-08 用户报的）──
    # [EN] ── G6 ★★★ after the image is done, **must actively notify the UI to redraw once** (user-reported
    # [EN] 2026-10-08) ──
    #
    #   用户原话：「**小地图一直没画 好像美术一直没参与进来 故事都开始了
    #   美术也没被调用绘制小地图**」。
    # [EN] User's exact words: "**the minimap is never drawn, seems the art never joined in, the story has
    # [EN] already started
    # [EN] and the art was never called to draw the minimap**".
    #
    #   真相（拿用户那次真机日志核过）：**美术出工了、图也落盘了**
    #   （日志里明写着「第 1 天当天地图：1 处 —— <主角所在那一处>」），
    #   只是**没人叫界面重画** ——
    #   界面重画只挂在"换场景"（`_push_scene`）上，而一天里始终是同一处时
    #   那次通知永远不来，左栏就一直停在「今天这张图还没出来」。
    # [EN] The truth (verified against the user's real-machine log that time): **the art did work, the
    # [EN] image was written to disk**
    # [EN] (the log literally says "day 1 same-day map: 1 spot —— <the spot where the protagonist is>"),
    # [EN] it's just that **nobody told the UI to redraw** ——
    # [EN] the UI redraw only hangs on "scene change" (`_push_scene`), and when it's the same spot all day
    # [EN] that notification never comes, so the left column stays at "today's map isn't out yet".
    seen_scene: list = []
    seen_rec: list = []
    st6 = FakeStudio()
    lp6 = make_loop(st6, seen_scene, seen_rec)
    await lp6._draw_day_map(ds)
    ok('G6 ★★★ 当天的图画好之后**主动通知了一次**界面重画'
       '（不通知的话，一天只有一处地点时左栏永远停在"今天这张图还没出来"）',
       len(seen_scene) >= 1 and str(seen_scene[-1].get('place')) == '临河茶肆',
       str(seen_scene))
    ok('G6b ★★ 那次通知**不往审读台账里塞"换场景"**'
       '（并没有换地方，只是图变了 —— 塞进去会污染"这一场戏在哪几处"那类判断）',
       seen_rec == [], str(seen_rec))
    # ⚠ 「关掉 MINIMAP_AI」那条路也要通知（它走的也是 `_log_day_map`）。
    # [EN] ⚠ The "turn off MINIMAP_AI" path must also notify (it also goes through `_log_day_map`).
    CFG.set('MINIMAP_AI', 'false')
    try:
        seen_scene2: list = []
        lp7 = make_loop(FakeStudio(), seen_scene2, [])
        await lp7._draw_day_map(ds)
        ok('G6c ★ 简化排布那条路（`MINIMAP_AI=false`）**同样通知**'
           '（两条路共用 `_log_day_map`，只修一条等于没修）',
           len(seen_scene2) >= 1, str(seen_scene2))
    finally:
        CFG.set('MINIMAP_AI', 'true')


async def gui_checks(page: ft.Page) -> None:
    app = G.NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.4)

    tmp = Path(tempfile.mkdtemp(prefix='nws_mapui_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    CFG.set('MINIMAP_AI', 'false')      # 探"画得对不对"，不是"模型准不准"
    # [EN] Probe "is it drawn correctly", not "is the model accurate"
    import yaml
    proj = Project.create_new(CFG.projects_dir(), '地图验证')
    RunFolder(proj.root, '第1次模拟2026-10-06-10-00').create()
    (proj.settings_dir / '人物.yaml').write_text(
        '- 名称: 主角\n  身份: 掌柜\n- 名称: 阿枝\n  身份: 伙计\n', encoding='utf-8')
    (proj.settings_dir / '地点.yaml').write_text(
        yaml.safe_dump(PLACES, allow_unicode=True), encoding='utf-8')
    (proj.settings_dir / '世界观.md').write_text(
        '# 世界观\n\n临河镇靠一条河吃饭。河从西边来，渡口在东头。\n', encoding='utf-8')
    app._activate_project(proj)
    app.show_main_screen()
    page.update()
    await asyncio.sleep(1.0)

    canvas = (app._ui_run or {}).get('map_canvas')
    ok('B1 运行界面左栏挂上了 `ft.canvas` 小地图（不是 `ft.Image`）',
       canvas is not None and isinstance(canvas, ft.canvas.Canvas),
       type(canvas).__name__ if canvas else None)
    ok('B1b 还没开演时画布上也有东西（**兜底提示**，不是一块空白）',
       len(getattr(canvas, 'shapes', []) or []) >= 2 if canvas else False,
       len(getattr(canvas, 'shapes', []) or []) if canvas else 0)
    # ★★ 2026-10-08：进界面的那一刻**不许**再把"整本小说设定的地点"画出来。
    #   用户就是在这时候看到"主角旁边围着一圈各界各域的大名字"那张图的
    #   （日志：`小地图布局：AI 排好 7 处地点（设定里共 7 处）`）。
    #   现在这一层整段拆掉 —— 画布上**一个设定地名都不该有**，
    #   只有"还不知道你在哪儿"的提示。
    # [EN] ★★ 2026-10-08: the moment you enter the UI, **must not** draw out "the whole novel's setting
    # [EN] places".
    # [EN] This is when the user saw the image with "a ring of big names of every realm and domain around
    # [EN] the protagonist"
    # [EN] (log: `minimap layout: AI laid out 7 places (7 in the setting)`).
    # [EN] Now this layer is torn out entirely —— there must be **not a single setting place name** on the
    # [EN] canvas,
    # [EN] only the hint that "we don't yet know where you are".
    _labels = _place_labels(canvas)
    ok('B1c ★★★ 进界面时画布上**没有任何设定地名**'
       '（尤其不许出现「雾泽 / 云洲 / 东馆 / 西陵」这些世界层级名 —— '
       '用户报的就是这张全书总图）',
       not _realm_labels(_labels), str(sorted(_labels)))

    # ── ★ 标记色法：把纸底与"当前地点"都染成独占色 ──
    # [EN] ── ★ Marker-color method: dye both the paper background and the "current place" an exclusive
    # [EN] color ──
    #
    # ⚠ 这里**刻意自己造一份布局**（把设定里的地点全放进去）：
    #   这一段验的是**渲染**（纸底、墨迹、当前地点标记、切场景后标记移动），
    #   与"取景范围从哪来"无关 —— 后者归 A10 / F / B9 那几组。
    #   2026-10-08 之前它用的是 `app._map_layout`（界面自己算的全书布局），
    #   那条链路已经拆掉，所以这里不再依赖界面内部状态。
    # [EN] ⚠ Here we **deliberately build our own layout** (put all the places from the setting in):
    # [EN] this section validates **rendering** (paper background, ink, current-place marker, marker moving
    # [EN] after a scene change),
    # [EN] unrelated to "where the framing comes from" —— the latter belongs to groups A10 / F / B9.
    # [EN] Before 2026-10-08 it used `app._map_layout` (the UI's own whole-book layout),
    # [EN] that chain has been torn out, so this no longer depends on UI internal state.
    RENDER_FIX = ML.normalize(
        {'地点': [{'名称': '临河茶肆', 'x': .5, 'y': .5},
                  {'名称': '城东渡口', 'x': .85, 'y': .8},
                  {'名称': '后院', 'x': .2, 'y': .25},
                  {'名称': '县衙', 'x': .15, 'y': .8},
                  {'名称': '里巷', 'x': .5, 'y': .1}]},
        list(PLACES_NAMES), source='ai')

    def paint(here: str, cast: list | None = None) -> None:
        canvas.shapes = MM.build_shapes(
            RENDER_FIX, current=here, cast=cast or [],
            cast_place=app._map_cast or None,
            width=G.MAP_W, height=G.MAP_H, title='', font=None,
            palette={'paper': PAPER_MARK, 'here': HERE_MARK})
        page.update()

    async def shot(name: str):
        page.update()
        await asyncio.sleep(0.45)
        png = await page.take_screenshot()
        (OUT / f'minimap_{name}.png').write_bytes(png)
        return png

    paper_rgb = (0, 0, 255)
    paint('临河茶肆')
    png1 = await shot('verify_here1')
    box = mask_bbox(png1, paper_rgb)
    ok('B2 ★ 画布**真的画在屏幕上**（纸底一大块独占色，≥ 1 万像素）',
       box.get('n', 0) >= 10000, box)
    # 尺寸应当接近 196×132（面板按内容撑，容一点误差）
    # [EN] The size should be close to 196×132 (the panel sizes to content, allow some tolerance)
    ok('B2b 画布尺寸就是设定的 196×132（宽高各容 12px 误差）',
       box.get('n', 0) >= 10000 and abs(box['w'] - G.MAP_W) <= 12
       and abs(box['h'] - G.MAP_H) <= 12, box)
    ok('B2c 画布落在**左栏**（x 起点在 250 以内）',
       box.get('n', 0) >= 10000 and box['x0'] < 250, box)

    ink = ink_inside(png1, box, paper_rgb)
    # ⚠ 阈值从 800 调到 300（2026-10-12）：地点改成"只有一行小字"之后，
    #   图上的墨迹就只剩**字与通路**了（字形与朱砂圈都按用户要求去掉了），
    #   一个四地点的夹具大约 500 像素。**保留一条下限仍然有意义**（"不是一块空纸"），
    #   但数值必须跟着画法走；同时补一条**更本质**的断言：标签数与地点数对得上。
    # [EN] ⚠ Threshold lowered from 800 to 300 (2026-10-12): after locations became "just one line of
    # [EN] small text", the only ink left is **text and paths** (the glyphs and the cinnabar circle were
    # [EN] removed as the user asked) -- a four-location fixture is about 500 pixels. **Keeping a floor
    # [EN] still makes sense** ("not a blank sheet"), but the number has to follow the drawing style;
    # [EN] a **more essential** assertion was added alongside: label count matches location count.
    n_lbl = sum(1 for s in (canvas.shapes or [])
                if type(s).__name__ == 'Text' and getattr(s, 'value', ''))
    ok('B3 ★ 画布上**有墨迹**（不是一块空纸：非纸色像素 ≥ 300，'
       '且写出来的标签数 ≥ 地点数）',
       ink >= 300 and n_lbl >= len(RENDER_FIX.places),
       f'{ink} 像素（占 {100 * ink / max(1, box["w"] * box["h"]):.1f}%）'
       f' · 标签 {n_lbl} 个 / 地点 {len(RENDER_FIX.places)} 个')

    m1 = mask_bbox(png1, (255, 0, 255))
    ok('B4a ★ 当前地点被画成独占色标记（**真的在屏幕上**，≥ 40 像素）',
       m1.get('n', 0) >= 40, m1)

    # ── ★★ 换一个地点 → 标记必须**移到别处** ──
    # [EN] ── ★★ change to another place → the marker must **move elsewhere** ──
    paint('县衙')
    png2 = await shot('verify_here2')
    m2 = mask_bbox(png2, (255, 0, 255))
    ok('B4b 换地点后标记仍在（≥ 40 像素）', m2.get('n', 0) >= 40, m2)
    if m1.get('n', 0) >= 40 and m2.get('n', 0) >= 40:
        dist = ((m1['cx'] - m2['cx']) ** 2 + (m1['cy'] - m2['cy']) ** 2) ** 0.5
    else:
        dist = 0.0
    ok('★★ B4c **切场景后标记真的换了位置**（两个地点的标记质心相距 > 20px）'
       '—— 这是"每次切场景重画"的硬证据',
       dist > 20, f'质心距 {dist:.1f}px  ({m1.get("cx")},{m1.get("cy")}) → '
                  f'({m2.get("cx")},{m2.get("cy")})')

    # ── B5 走真实接线：`_on_scene` → 重画 ──
    # [EN] ── B5 go through real wiring: `_on_scene` → redraw ──
    # ⚠ 这里原来先记了一个 `before = 形状总数`，B5b 拿它比"变了没有"。
    #   那条判据是弱的（见 B5b 的注释），已改成数人物点 —— 所以 `before` 不再需要。
    # [EN] ⚠ This used to record `before = total shapes`, and B5b compared "did it change".
    # [EN] That criterion was weak (see the note at B5b) and now counts character dots instead -- so
    # [EN] `before` is no longer needed.
    app._on_scene({'place': '城东渡口', 'segment': '戌时',
                   'cast': ['主角', '阿枝'], 'day': 1})
    page.update()
    await asyncio.sleep(0.4)
    ok('B5a ★ 走 `_on_scene` 这条真实接线：当前地点被记下',
       app._map_here == '城东渡口', app._map_here)
    # ⚠ 这条原来是"形状总数变了" —— 一个**弱判据**：2026-10-12 地点不再画字形与朱砂圈
    #   之后，重画前后总数恰好相等（都是 5），它就假红了，而它想验的事
    #   （"在场人物点被画上去了"）**从来不是它真正在验的**。
    #   ⇒ 改成**数人物点**：`build_shapes` 里唯一的实心圆就是人物点，
    #     所以"圆数 == 在场人数"才是这条判据的本意。
    # [EN] ⚠ This used to be "the total shape count changed" -- a **weak criterion**: after the
    # [EN] 2026-10-12 removal of location glyphs and the cinnabar circle, the total before and after a
    # [EN] redraw happens to be equal (both 5), so it went falsely red -- and what it meant to check
    # [EN] ("the present-character dots were drawn") was **never what it actually checked**.
    # [EN] ⇒ Changed to **counting the character dots**: the only filled circles in `build_shapes` are
    # [EN] the character dots, so "circle count == number of people present" is this criterion's intent.
    n_dots = sum(1 for s in (canvas.shapes or [])
                 if type(s).__name__ == 'Circle')
    n_cast = len(['主角', '阿枝'])
    ok('B5b ★★ 重画后**在场人物点真的画上去了**（实心圆数 == 在场人数）'
       '—— 地点已经不画点（用户「不要用点」），所以图上剩下的圆只有人物点',
       n_dots == n_cast, f'圆 {n_dots} 个 / 在场 {n_cast} 人')
    await shot('verify_scene')

    # ── B9 真机：画布上的地名**只能来自当天的戏**（不是全书总图）──
    # [EN] ── B9 real machine: place names on the canvas **may only come from the day's scene** (not the
    # [EN] whole-book overview map)──
    #
    #  ★★ 用户 2026-10-08：
    #    「小地图上主角所在的那一处旁边，画着一串**世界层级**的名字（各界、各域）；用户说「这些不是真实的地名」
    #     你让美术画图的时候**只根据当前发生的故事所在的地点画图**
    #     而不是根据整本小说设定画图」。
    #    A10 / F 那两组量的是数据与接线；这里量的是**真实接线跑完之后的画布**。
    # [EN] ★★ User 2026-10-08:
    # [EN] "On the minimap, beside the spot where the protagonist is, there's a string of **world-tier**
    # [EN] names (realms, domains); the user said "these aren't real place names"
    # [EN] when you have the art draw the map, **draw only based on the places of the story currently
    # [EN] happening**
    # [EN] and not based on the whole novel's setting".
    # [EN] Groups A10 / F measure data and wiring; here we measure **the canvas after the real wiring has
    # [EN] run**.
    note = (app._ui_run or {}).get('map_note')

    # ⚠ 当天的图在界面上是**每次重画都去主循环现读**的（一天之内可能换图），
    #   所以"喂一张图给它"必须**打桩那个取数口**，不能直接写 `app._map_day`
    #   —— 写了也会被 `_draw_minimap` 第一行覆盖掉（第一版就这么假红了一片）。
    # [EN] ⚠ The day's map on the UI is **re-read from the main loop on every redraw** (the map can change
    # [EN] within a day),
    # [EN] so "feed it an image" must **stub that data-source entry point**, not write `app._map_day`
    # [EN] directly.
    # [EN] —— even if written, it gets overwritten by the first line of `_draw_minimap` (the first version
    # [EN] had a whole patch of fake red just like this).
    def set_day(lay) -> None:
        app._day_map_of_loop = (lambda: lay)      # 实例属性遮蔽方法
        # [EN] instance attribute shadows the method

    # ① 还没有当天的图（现在就是这样）：只画当前一处，**一个设定地名都不许有**
    # [EN] ① there is no map for the day yet (this is the current situation): draw only the current
    # [EN] location, **not a single configured place name may appear**
    set_day(None)
    app._on_scene({'place': '城东渡口', 'cast': [], 'day': 1})
    await asyncio.sleep(0.3)
    one_n = len(getattr(canvas, 'shapes', []) or [])
    ok('B9a ★★★ 当天的图还没出来时：画布上**只有当前这一处**'
       '（不是把设定里 4 处地点一次全画上屏）',
       not _realm_labels(_place_labels(canvas)) and 0 < one_n < 12,
       f'{one_n} 个形状 · 标签 {sorted(_place_labels(canvas))}')
    ok('B9b ★★ 图注**照实说**这是兜底（"今天这张图还没出来"），'
       '不让人以为"今天就这一处"',
       note is not None and '还没出来' in str(note.value), str(getattr(note, 'value', None)))

    # ② 当天的图到了（美术按当天剧情画的）→ 画布上就该只有那几处
    # [EN] ② once the day's map arrives (drawn by art according to that day's story) → the canvas should
    # [EN] contain only those locations
    day_fix = ML.day_layout(
        {'地点': [{'名称': '临河茶肆', 'x': .5, 'y': .6},
                  {'名称': '后院', 'x': .2, 'y': .3}],
         '通路': [['临河茶肆', '后院']], '题记': '今日'},
        ['临河茶肆', '后院'], here='临河茶肆')
    set_day(day_fix)
    app._draw_minimap()
    page.update()
    await asyncio.sleep(0.3)
    labels2 = _place_labels(canvas)
    need = len(MM.build_shapes(day_fix, current=app._map_here, cast=[],
                               cast_place=app._map_cast or None,
                               width=G.MAP_W, height=G.MAP_H, title='小地图'))
    ok('B9c ★★ 当天的图到了 → 画布画的就是**它那几处**（不多画一处）',
       _has_label(labels2, '临河茶肆') and not _has_label(labels2, '城东渡口')
       and len(getattr(canvas, 'shapes', []) or []) == need,
       f'{sorted(labels2)} · 形状 {len(getattr(canvas, "shapes", []) or [])} vs {need}')
    ok('B9d ★ 图注说"今天这场戏在 N 处"（★ 不写"共 N 处" —— '
       '那会让人当成总图）',
       note is not None and '今天这场戏在' in str(note.value)
       and '共' not in str(note.value), str(getattr(note, 'value', None)))

    # ③ 像素级：单处 vs 全 4 处的墨迹差（屏幕证据，不是"数据对了就算"）
    # [EN] ③ pixel-level: ink diff between a single location vs all 4 locations (screen evidence, not "it's
    # [EN] correct because the data is right")
    #
    # ⚠ 独占色必须写成**十六进制字符串**（跟 `PAPER_MARK` 一样）：
    #   写成 `(0, 255, 0)` 这种元组，Flet 不认，画出来**一个像素都不是这个颜色**
    #   （实测两条都是 0，差点被我当成"取景没生效"）。
    # [EN] ⚠ the exclusive color must be written as a **hex string** (same as `PAPER_MARK`):
    # [EN] if written as a tuple like `(0, 255, 0)`, Flet does not recognize it, and **not a single pixel**
    # [EN] drawn will be that color
    # [EN] (measured both as 0, almost mistook it for "framing had no effect").
    INK_MARK = '#00ff00'

    def paint_layout(lay, here: str) -> None:
        canvas.shapes = MM.build_shapes(
            lay, current=here, cast=[], width=G.MAP_W, height=G.MAP_H,
            title='', font=None,
            palette={'ink': INK_MARK, 'muted': INK_MARK,
                     'paper': PAPER_MARK, 'water': INK_MARK,
                     'link': INK_MARK, 'wall': INK_MARK,
                     'here': HERE_MARK})
        page.update()

    one = ML.here_only('城东渡口')
    paint_layout(one, '城东渡口')
    png_loc = await shot('verify_local_ink')
    n_loc = mask_bbox(png_loc, (0, 255, 0)).get('n', 0)
    paint_layout(RENDER_FIX, '城东渡口')
    png_full = await shot('verify_full_ink')
    n_full = mask_bbox(png_full, (0, 255, 0)).get('n', 0)
    ok('B9e ★★ 像素级："只画当前一处"屏幕上的墨迹**明显少于**'
       '"把设定地点全画上"（用户看到的差别就是这个）',
       n_full > 0 and n_loc < n_full * 0.6,
       f'一处 {n_loc} vs 全部 {n_full} 像素')

    # ── B6 状态行照实说（三种来源各说各的）──
    # [EN] ── B6 the status line tells it as it is (each of the three sources says its own thing) ──
    app._map_here = ''
    set_day(None)
    app._draw_minimap()
    ok('B6c 还不知道在哪儿时状态行指去开卷（不是干巴巴的"待生成"）',
       note is not None and '开卷' in str(note.value), str(note.value))
    app._map_here = '城东渡口'
    set_day(None)
    app._draw_minimap()
    ok('B6a ★ 兜底时状态行**明说是兜底**（"今天这张图还没出来"）',
       note is not None and '还没出来' in str(note.value),
       str(getattr(note, 'value', None)))
    # 简化排布（`MINIMAP_AI=false` 那条路）也不能冒充 AI 画的
    # [EN] the simplified layout (the `MINIMAP_AI=false` path) also must not masquerade as AI-drawn
    set_day(ML.simple_layout(['临河茶肆', '后院']))
    app._draw_minimap()
    ok('B6a2 ★ 简化排布时明说"没调用模型"（不冒充 AI 画的）',
       note is not None and '简化' in str(note.value), str(note.value))
    set_day(day_fix)
    app._draw_minimap()
    ok('B6b ★ 美术画的那张：状态行说"由模型**按当天剧情**摆放"'
       '（不是"按设定"—— 那句话正是用户报的毛病的来源）',
       note is not None and '当天剧情' in str(note.value)
       and '按设定' not in str(note.value), str(note.value))

    # ── B8 每次切场景重画是**零成本**的（不再问模型、也不重建布局）──
    # [EN] ── B8 redrawing on every scene switch is **zero cost** (no more asking the model, no rebuilding
    # [EN] the layout) ──
    calls: list = []
    real_ask = REPLIES.ask

    async def _spy(*a, **k):
        calls.append(k.get('purpose'))
        return REPLIES.Reply(value={'地点': []}, ok=True)

    day_before = app._map_day
    try:
        REPLIES.ask = _spy
        for pl in ('临河茶肆', '城东渡口', '后院', '县衙'):
            app._on_scene({'place': pl, 'cast': [], 'day': 1})
        await asyncio.sleep(0.4)
        ok('B8 ★ 连续 4 次切场景重画**没有产生任何模型调用**',
           not calls and app._map_here == '县衙', f'调用 {calls}')
        # ★ 更强的一条：重画**不该重新算布局**（只换形状）。
        #   判"同一个对象"比"没调模型"硬：有缓存挡着时后者会被骗过去
        #   （反例法实测过这件事）。
        # [EN] ★ an even stronger one: redraw **must not recompute the layout** (only swap shapes).
        # [EN] judging "same object" is stronger than "model not called": the latter gets fooled when a cache
        # [EN] is in the way
        # [EN] (verified this with the counterexample method).
        ok('B8b ★ 重画用的是**同一张当天的图**（切场景 ≠ 重画当天的图）',
           app._map_day is day_before,
           f'{id(day_before)} → {id(app._map_day)}')
    finally:
        REPLIES.ask = real_ask

    # ── B10 ★★★ 兜底重画：`loop.day_map` 换了就补画（2026-10-08）──
    # [EN] ── B10 ★★★ fallback redraw: if `loop.day_map` changed, fill it in (2026-10-08) ──
    #
    #   用户：「**小地图一直没画 好像美术一直没参与进来**」。主循环现在会在图
    #   画好那一刻主动通知一次（`_log_day_map` → `_push_scene`，G6 钉住了）；
    #   这一组钉的是**界面自己的兜底**：那条通知万一漏了，秒表也能靠"图变了"补上。
    # [EN] User: "**the minimap has never been drawn, seems like art never got involved**". The main loop
    # [EN] now, at the moment the map
    # [EN] is drawn, proactively notifies once (`_log_day_map` → `_push_scene`, pinned by G6);
    # [EN] this group pins the **UI's own fallback**: if that notification somehow gets dropped, the
    # [EN] stopwatch can still fill it in based on "the map changed".
    ok('B10a ★★ 秒表里**真的调用了** `_sync_day_map`'
       '（按 AST 判，不看注释 —— 写了没人调等于没修）',
       _calls_in(G.NovelWorldApp._start_status_ticker, '_sync_day_map'), '')
    ok('B10b ★★ 而 `_draw_minimap` 画完会**记下"现在画上屏的是哪一张"**'
       '（不记的话兜底比不出"变了没有"，每半秒都要白重画一遍）',
       '_map_day_seen' in inspect.getsource(G.NovelWorldApp._draw_minimap)
       and '_map_day_seen' in inspect.getsource(G.NovelWorldApp._sync_day_map),
       '')

    import types as _types
    # ⚠ 上面 B9 那一段为了打桩，在**实例上**遮蔽了 `_day_map_of_loop`
    #   （`app._day_map_of_loop = lambda: lay`，见 `set_day`）。这一组要验的正是
    #   **真方法**（从 `session.loop.day_map` 取图），必须先把那层遮蔽摘掉 ——
    #   第一版没摘，兜底一直读到 B9 留下的那张**旧图**，判据假红（查了半天）。
    # [EN] ⚠ the B9 section above, for stubbing purposes, shadowed `_day_map_of_loop` **on the instance**
    # [EN] (`app._day_map_of_loop = lambda: lay`, see `set_day`). What this group verifies is exactly
    # [EN] the **real method** (fetching the map from `session.loop.day_map`), so that shadowing layer must
    # [EN] first be removed ——
    # [EN] the first version did not remove it, so the fallback kept reading the **old map** left behind by
    # [EN] B9, and the criterion falsely went red (spent ages debugging).
    app.__dict__.pop('_day_map_of_loop', None)
    prev_sess = getattr(app, 'session', None)
    day_new = ML.day_layout(
        {'地点': [{'名称': '临河茶肆', 'x': .5, 'y': .6},
                  {'名称': '后院', 'x': .2, 'y': .3}],
         '通路': [['临河茶肆', '后院']], '题记': '今'},
        ['临河茶肆', '后院'], here='临河茶肆')
    try:
        app.session = _types.SimpleNamespace(loop=_types.SimpleNamespace(
            day_map=day_new))
        shapes_before = canvas.shapes
        app._sync_day_map()
        ok('B10c ★★★ 当天的图**换了**（美术画好了）→ 兜底真的把它画上屏'
           '（画布换了一批新形状，`_map_day` 指向新图）',
           app._map_day is day_new and canvas.shapes is not shapes_before,
           f'认新图吗={app._map_day is day_new} · '
           f'画布换了吗={canvas.shapes is not shapes_before}')
        shapes_now = canvas.shapes
        app._sync_day_map()
        ok('B10d ★ 图**没变**时不去碰画布（只比一次对象身份，零成本 —— '
           '每半秒白重画一遍会让画布闪）',
           canvas.shapes is shapes_now, '')
    finally:
        app.session = prev_sess


async def main(page: ft.Page):
    try:
        await day_loop_checks()      # G 组：真跑一遍那一步（打桩，不联网）
        # [EN] Group G: actually run that step once (stubbed, no network)
    except Exception:                                        # noqa: BLE001
        import traceback
        ok('G 组跑完（`_draw_day_map` 行为级）', False,
           traceback.format_exc()[-400:])
    try:
        await gui_checks(page)
    except Exception as e:                                   # noqa: BLE001
        import traceback
        ok('B 组跑完（界面这一侧）', False,
           traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    rep = {'checks': checks,
           'passed': sum(1 for c in checks if c['ok']), 'total': len(checks)}
    rep['ok'] = rep['passed'] == rep['total']
    (OUT / 'minimap_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    for c in checks:
        cjk(c)
    print(f"\n小地图验证：{rep['passed']}/{rep['total']}")
    await shutdown(page, code=0 if rep['ok'] else 2)


if __name__ == '__main__':
    try:
        logic_checks()
        day_scope_checks()
        day_map_checks()
        # ⚠ `asyncio.get_event_loop()` 在 3.13 上只发 DeprecationWarning、
        #   **不给 loop** —— 而且它会把事件循环状态搞乱，后面 `ft.run()` 起不来
        #   （表现：脚本一声不响地结束，一条判据都没打）。用 `asyncio.run`。
        # [EN] ⚠ `asyncio.get_event_loop()` on 3.13 only emits a DeprecationWarning,
        # [EN] **does not give a loop** —— and it messes up the event loop state, so `ft.run()` later cannot
        # [EN] start
        # [EN] (symptom: the script ends silently, not a single criterion printed). Use `asyncio.run`.
        asyncio.run(ai_checks())
        ft.run(main, assets_dir=str(APP_DIR / 'assets'))
    except Exception:                                        # noqa: BLE001
        import traceback
        traceback.print_exc()
        exit_now(2)
