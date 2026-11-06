# -*- coding: utf-8 -*-
"""开卷时生成**三级底图**（见 `world/atlas.py`）。

用户 2026-10-08：

    「是否可以在**开卷的时候**把一些**整体地图 局部地图**(房屋附近 房屋内部
      以及别的需要的地图)**提前画好** 需要的时候**基于这些地图让美术加细节**」

## 两件事，两个入口

| 入口 | 干什么 | 什么时候 | 贵不贵 |
|---|---|---|---|
| `build_vector()` | 三层**矢量**底图（方位 / 周边 / 室内）—— 走 LLM 出结构规格 | `run_ingest` 的 `freeze` 之后，**同步 await** | 便宜（1+N 次文本调用） |
| `build_bitmaps()` | 每层一张**位图氛围底画** —— 走文生图 | GUI 侧（与「肖像」同一处、同一套进度），**同步阻塞**、丢线程 | 贵（每张一次出图） |

★ 为什么位图不放在 `run_ingest` 里：位图生成是**同步阻塞**的 HTTP 出图，
  一笔几秒到几十秒。放在摄取管线里会把进度条卡住、日志也刷不出来 ——
  现成的做法在 GUI 侧（`gui/app_flet._ensure_portraits`：线程里跑、主协程掏日志）。
  两件图（肖像 / 地图底画）性质一样，就都归那儿。

## ⚠ 三条硬规矩

1. **名字必须来自设定**。整体层的地点名只能取 `地点.yaml`；局部/室内层的名字
   要么来自该地点的说明（"两层，后院有口井" → 有"后院"和"井"），
   要么是该类建筑**必然有的**（茶楼有堂、有门）。**编造一个剧情里没有的地方
   就是编**，这个项目最忌讳这个 —— 校验复用 `map_layout.normalize()` 的白名单。
2. **拿不到就降级，不抛**。任何一层失败都只是"少一层"，推演照跑
   （退回原来的"每天现画"）。底图不是生死线。
3. **依据没变就不重画**。重开卷（或 AI 优化后又冻结一次）时，若 `地点.yaml`
   的名字表没变，直接复用已有底图 —— 用户改一句说明不该让整本书的地图重画一遍。

English:
On opening the book, generate the **three-level base map** (see `world/atlas.py`).
User 2026-10-08:
    "Could we, **when opening the book**, get some **overall map / partial map** (near a house, inside a house
      and other needed maps) **drawn ahead of time**, and when needed **have the artist add detail based on these maps**"
## Two things, two entry points
| Entry | What it does | When | Expensive? |
|---|---|---|---|
| `build_vector()` | Three-layer **vector** base map (方位 / 周边 / 室内) -- goes through the LLM to produce a structural spec | after `run_ingest`'s `freeze`, **synchronously await** | cheap (1+N text calls) |
| `build_bitmaps()` | One **bitmap atmosphere base art** per layer -- goes through text-to-image | GUI side (same place as "portrait", same progress set), **synchronous blocking**, offloaded to a thread | expensive (one image call per image) |
★ Why bitmaps aren't in `run_ingest`: bitmap generation is **synchronous blocking** HTTP image
generation,
  a few seconds to dozens of seconds per image. Putting it in the ingest pipeline would stall the progress bar and the logs wouldn't flush either --
  the ready-made approach is on the GUI side (`gui/app_flet._ensure_portraits`: runs in a thread, drains logs in the main coroutine).
  The two images (portrait / map base art) are the same in nature, so both go there.
## ⚠ Three hard rules
1. **Names must come from the setting**. Overall-layer place names can only be taken from `地点.yaml`; partial/interior-layer names
   either come from that location's description ("two floors, a well in the backyard" -> there's "backyard" and "well"),
   or are **necessarily present** for that building type (a teahouse has a hall, a door). **Inventing a place not in the story
   is fabrication**, and this project's biggest taboo is exactly that -- validation reuses `map_layout.normalize()`'s whitelist.
2. **If you can't get it, degrade, don't throw**. Any layer failing just means "one layer fewer", the reasoning still runs
   (falling back to the original "draw on the day"). The base map is not a life-or-death matter.
3. **If the basis hasn't changed, don't redraw**. On reopening the book (or after AI optimization then freezing once more), if `地点.yaml`'s
   name list hasn't changed, directly reuse the existing base map -- the user editing one description shouldn't cause the whole book's map to be redrawn.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from image_gen.map_layout import Layout, normalize
from llm.router import llm
from util.jsonio import extract_json
from util.text import now_str
from world import atlas as AT

_LOG = logging.getLogger('nws.atlas')

#: LLM 用途名（路由与 `NO_THINK_PURPOSES` 都按它分档）。
#: 二者都是**结论型**产出（一份小 JSON）—— 让模型"想"只会把额度烧在思考上。
# [EN] : LLM purpose name (routing and `NO_THINK_PURPOSES` are both classified by it).
# [EN] : Both are **conclusion-type** outputs (a small JSON) -- making the model "think" only burns
# [EN] quota on thinking.
PURPOSE_OVERVIEW = 'atlas_overview'
PURPOSE_PLACE = 'atlas_place'

#: 一次最多为几处地点画局部/室内。
#: `地点.yaml` 的提取上限本来就有 5 条（见 `ingest/extractor` 的"更短"提示），
#: 这里留 8 是给手改过设定集的人兜个底 —— 超了就只画前几个，并如实说。
# [EN] : Max number of locations to draw partial/interior maps for at once.
# [EN] : `地点.yaml`'s extraction limit is already 5 entries (see `ingest/extractor`'s "shorter" hint),
# [EN] : Leaving 8 here is a fallback for people who hand-edited the setting book -- if exceeded, only
# [EN] draw the first few, and say so honestly.
MAX_PLACES = 8

#: 每层的说明字段上限（图上要写的字，太长会糊）
# [EN] : Per-layer description field limit (text to draw on the map; too long gets blurry)
_NOTE_MAX = 16


def _shape_hint() -> str:
    from image_gen.map_layout import SHAPES
    return ' '.join(SHAPES)


# ══════════════════════════════════════════════════════════════════
#  提示词
# [EN] Prompts
# ══════════════════════════════════════════════════════════════════
_OVERVIEW_PROMPT = """你是一部剧的**美术**。这本书里"故事发生的那一小片地方"如下。
请把这些地方的**相对方位**摆出来 —— 这是一张**全书通用的底图**，之后每天的
小地图都会从它里面取景。

── 这些地方（**这份清单就是这张图的全部内容**）──
{places}

── 硬要求 ──
1. `名称` **必须**从上面逐字取，清单以外的名字**一个也不许出现** ——
   不要画各国、各界、各域这类世界观里的大地方，也不要画设定里没有的地方。
2. 读得出方位关系就按方位排（"城东渡口"在东边、河在中间）；
   读不出就按它们**在故事里先后出场**的顺序从左到右排开。
3. `x` / `y` 是 0~1 的相对位置（左上角是原点，x 向右、y 向下）。
4. `形` 从这些里挑一个：{shapes}
5. `通路` 只连**真的挨着、走得过去**的两处（`[["甲","乙"]]`）；说不清就留空数组。
6. 只输出 JSON，不要 ``` 围栏：

{{"题记": "两个字的题记（地名或河名）",
  "地点": [{{"名称": "…", "x": 0.4, "y": 0.6, "形": "楼", "说明": "一句话"}}],
  "通路": [["甲", "乙"]]}}"""

_PLACE_PROMPT = """你是一部剧的**美术**。请为下面**这一处地方**画两张底图：

① **周边**（把这一处放大看，它外面挨着什么）：河、桥、街、邻舍，
   **以及这一带别的地方**（"茶肆旁边就是渡口"这种关系要看得出来）；
② **内部**（房屋里面）：堂屋、后院、侧案、井、柜台这一级的**房间与院落**。

── 这一处地方 ──
{name}：{brief}

── 这一带还有哪些地方（**它们属于「周边」，不属于「内部」**）──
{others}

── 硬要求 ──
1. **不许发明设定里没有的东西**。名字只能来自：
   · 上面「这一处地方」的说明里**提到过的**（说明里有"后院有口井"，就写"后院"和"井"）；
   · 或者这类建筑**必然有的**最少几个（茶楼有"堂"、有"门"；院子有"院门"）；
   · 「周边」还可以写上「这一带还有哪些地方」里列的那些。
2. **「内部」里一个地名都不许出现** —— 屋里没有"某某渡口"，只有房间、
   院落、器物。写地名就是错的。
3. 「周边」和「内部」各自**独立排布**，都用 0~1 的相对坐标（x 向右、y 向下）。
   画「周边」时把**这一处自己**放在正中（名字逐字用「{name}」）。
4. 「内部」按这个房子**合理的格局**排：进门是堂，堂后是院，院的角落是井 ——
   让人一眼看出"从哪儿走到哪儿"。
5. `形` 从这些里挑一个：{shapes}
6. `通路` 连**真的能走过去**的两处（`[["堂屋","后院"]]`）。
7. 只输出 JSON，不要 ``` 围栏：

{{"周边": {{"地点": [{{"名称": "{name}", "x": 0.5, "y": 0.5, "形": "楼", "说明": "这一处自己"}},
          {{"名称": "河岸", "x": 0.2, "y": 0.8, "形": "渡", "说明": "一句话"}}],
          "通路": [["{name}", "河岸"]]}},
  "内部": {{"地点": [{{"名称": "堂屋", "x": 0.5, "y": 0.4, "形": "屋", "说明": "一句话"}}],
          "通路": [["堂屋", "后院"]]}}}}"""


def _fmt_places(settings: dict) -> str:
    """地点清单：**把作者写的 `方位` / `内里` 一起带上**（见 `AT.place_detail`）。

    不带的话，作者在设定里写的"有间柴房"到不了提示词 ——
    底图就只能按常识推，表现成"我写了怎么没有"。
    
        English:
    Location list: **carry along the author-written `方位` / `内里`** (see `AT.place_detail`).
        Otherwise, the "there's a woodshed" the author wrote in the setting never reaches the prompt --
        the base map can only be inferred by common sense, showing up as "I wrote it, why isn't it there".
    """
    lines: list[str] = []
    for n in AT.place_names(settings):
        d = AT.place_detail(settings, n)
        lines.append(f'- {n}：{d}' if d else f'- {n}')
    return '\n'.join(lines) or '（设定里没有地点 —— 那就没法画底图）'


# ══════════════════════════════════════════════════════════════════
#  生成：矢量三层
# [EN] Generation: vector three layers
# ══════════════════════════════════════════════════════════════════
def _spare(places: dict[str, Any], i: int, kind: str) -> dict:
    """兜底位置：模型漏画某处时，给它一个**确定性**的位置（宁可不精确也不能少）。

    与 `map_layout._spare_slot` 同一套思路（那里是给地图用的），这里按"层"分开：
    室内层排成一条走廊（纵向），局部层排成环形。
    
        English:
    Fallback position: when the model misses drawing something, give it a **deterministic** position
    (better imprecise than missing).
        Same idea as `map_layout._spare_slot` (that one is for maps), here split by "layer":
        the interior layer is laid out as a corridor (vertical), the partial layer as a ring.
    """
    if kind == '室内':
        return {'x': 0.5, 'y': round(0.25 + 0.13 * (i % 5), 3)}
    ang = (i * 2.399) % 6.283                       # 黄金角，散得开
    # [EN] Golden angle, spreads out well
    import math
    return {'x': round(0.5 + 0.3 * math.cos(ang), 3),
            'y': round(0.5 + 0.3 * math.sin(ang), 3)}


async def _ask(prompt: str, *, purpose: str, tokens: int) -> dict | None:
    """问一次模型，拿回 dict（拿不到就 None —— 调用方降级）。
        English:
    Ask the model once, get back a dict (None if not obtainable -- the caller degrades).
    """
    try:
        raw, meta = await llm.chat('cheap', [{'role': 'user', 'content': prompt}],
                                   purpose=purpose, json_mode=True,
                                   max_tokens=tokens, temperature=0.3,
                                   return_meta=True)
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning('底图生成失败（%s）：%r', purpose, e)
        return None
    data = extract_json(raw or '', {})
    if not isinstance(data, dict) or not data:
        # 撞上限被截断是常见原因 —— 说清是"截断了"还是"答非所问"
        # [EN] Hitting the limit and getting truncated is a common cause -- state clearly whether it's
        # [EN] "truncated" or "answered off-topic"
        _LOG.warning('底图生成没有可用 JSON（%s）：truncated=%s 输出 %s 字',
                     purpose, meta.get('truncated'), len(raw or ''))
        return None
    return data


async def build_vector(settings_dir: Path | str, settings: dict, *,
                       tokens: int = 1800,
                       on_note: Callable[[str], None] | None = None,
                       ) -> AT.Atlas | None:
    """生成三层**矢量**底图并落盘；返回 `Atlas`（一处地点都没有时返回 None）。

    `on_note(msg)` 用来把"哪一层没成、为什么"讲给用户听 ——
    **静默少一层**是这里最坏的失败形态（界面上只是图变简了，没人知道为什么）。
    
        English:
    Generate the three-layer **vector** base map and write it to disk; return `Atlas` (return None
    when there are no locations at all).
        `on_note(msg)` is used to tell the user "which layer failed and why" --
        **Silently missing a layer** is the worst failure mode here (the UI just shows a simpler diagram, and nobody knows why).
    """
    def note(msg: str) -> None:
        _LOG.info('%s', msg)
        if on_note:
            try:
                on_note(msg)
            except Exception:                                   # noqa: BLE001
                pass

    names = AT.place_names(settings)
    if not names:
        note('设定里没有地点 —— 跳过底图生成（小地图仍按每天剧情现画）')
        return None

    at = AT.Atlas(name='小世界地图', made_at=now_str('%Y-%m-%d %H:%M:%S'),
                  basis=list(names),
                  # 指纹把**说明**也算进去：用户手改说明之后底图要跟着变
                  # [EN] The fingerprint includes **descriptions** too: after the user hand-edits a description, the base
                  # [EN] map must change accordingly
                  fingerprint=AT.fingerprint_of(
                      names, [AT.place_brief(settings, n) for n in names]))

    # ── L1 整体 ───────────────────────────────────────────────
    # [EN] -- L1 overall --------------------------------------------------
    data = await _ask(_OVERVIEW_PROMPT.format(places=_fmt_places(settings),
                                              shapes=_shape_hint()),
                      purpose=PURPOSE_OVERVIEW, tokens=tokens)
    if data:
        lay = normalize(data, names, source='atlas')
        # 漏画的补齐（`normalize` 的 pad 只管在**已有**集合里补，
        # 它按 `names` 补 —— 所以这里不用自己再补一遍，只报个数）
        # [EN] Fill in missing drawings (`normalize`'s pad only fills within the **existing** set,
        # [EN] it fills by `names` -- so no need to fill again here, just report the count)
        if lay and lay.places:
            lay.caption = lay.caption or '小世界'
            lay.kind = '整体'
            at.overview = lay
            got = {p.name for p in lay.places}
            miss = [n for n in names if n not in got]
            note(f'底图 · 整体：{len(lay.places)} 处'
                 + (f'（{"/".join(miss)} 按设定补了位置）' if miss else ''))
        else:
            note('底图 · 整体：模型给的名字一个都不在设定里 —— 这一层不要了')
    else:
        note('底图 · 整体：没拿到（继续画局部与室内）')

    # ── L2 局部 + L3 室内（每处一次）──────────────────────────
    # [EN] -- L2 partial + L3 interior (once per location) ------------------
    todo = names[:MAX_PLACES]
    if len(names) > MAX_PLACES:
        note(f'地点有 {len(names)} 处，只给前 {MAX_PLACES} 处画局部/室内'
             f'（其余走整体图）')
    ok_local, ok_indoor = 0, 0
    for i, n in enumerate(todo):
        others = '、'.join(x for x in names if x != n) or '（没有别处）'
        d = await _ask(_PLACE_PROMPT.format(
            name=n, brief=AT.place_detail(settings, n) or '（设定里没写说明）',
            others=others, shapes=_shape_hint()),
            purpose=PURPOSE_PLACE, tokens=tokens)
        if not d:
            note(f'底图 · {n}：周边与室内都没拿到')
            continue
        # ⚠ 这里的第二参数传**空表**：房间名（堂屋/后院）本来就不在 `地点.yaml` 里，
        #   传 `names` 会把它们**全过滤掉**（第一版就这么写，室内层永远是空的）。
        #   白名单在这里的形态是下面的"内部不许出现地名"那步。
        # [EN] ⚠ The second argument here passes an **empty list**: room names (堂屋/后院) aren't in `地点.yaml` to
        # [EN] begin with,
        # [EN] passing `names` would **filter them all out** (the first version did exactly this; the interior
        # [EN] layer was always empty).
        # [EN] The whitelist takes the form of the next step, "no place names allowed inside".
        lay_l = normalize(d.get('周边') or d.get('local') or {}, [], source='atlas')
        lay_i = normalize(d.get('内部') or d.get('indoor') or {}, [], source='atlas')
        # ★ 「内部」里剔掉**地名**：屋里没有"某某渡口"，只有房间与器物。
        #   ⚠ 只对「内部」做，**不对「周边」做** —— 放大某一处看，旁边挨着别的地方
        #     本来就该画出来（"茶肆旁边就是渡口"正是周边层要表达的关系）。
        #     第一版把这条也用在周边上，于是周边层永远空着（实测：局部 0 处）。
        #   ⚠ **不排除"它自己那处的名字"**（第一版写了 `p.name != n`，那是个洞）：
        #     室内层里冒出"临河茶肆"这个**地名**同样是错的（屋里只有房间），
        #     而这正是模型最容易干的事（把地点名当房间名抄进来）。
        #     这条是被打桩判据 B2f 抓出来的（让模型故意犯错，才看得出来）。
        # [EN] ★ Strip **place names** from "inside": there's no "so-and-so ferry" inside a house, only rooms
        # [EN] and objects.
        # [EN] ⚠ Only do this for "inside", **not for "surroundings"** -- zoom into one place and it's adjacent
        # [EN] to another place
        # [EN] which should be drawn anyway ("the teahouse is right next to the ferry" is exactly the relation
        # [EN] the surroundings layer expresses).
        # [EN] The first version applied this to surroundings too, so the surroundings layer was always empty
        # [EN] (measured: 0 partial locations).
        # [EN] ⚠ **Do not exclude "its own location's name"** (the first version wrote `p.name != n`, that was
        # [EN] a hole):
        # [EN] having the **place name** "临河茶肆" appear in the interior layer is equally wrong (inside there are
        # [EN] only rooms),
        # [EN] and this is exactly what the model tends to do (copying the location name in as a room name).
        # [EN] This one was caught by stub criterion B2f (only by making the model deliberately err can you see
        # [EN] it).
        bad = [p.name for p in lay_i.places if p.name in set(names)]
        if bad:
            lay_i.places = [p for p in lay_i.places if p.name not in set(bad)]
            note(f'底图 · {n} 的室内里混进了地名（{"/".join(bad[:3])}）—— 已剔除')
        for tag, lay in (('周边', lay_l), ('内部', lay_i)):
            if not lay or not lay.places:
                continue
            for p in lay.places:
                p.note = (p.note or '')[:_NOTE_MAX]
            # ★★ **空间常识过一遍**（用户 2026-10-12）：
            #   · 室内层打上 `kind='室内'` 与 `frame=<这一处>`（小地图据此把整座楼
            #     **框起来**，不再在中间点一个挡住内容的红点）；
            #   · 有井（或别的屋外器物）却没有院子 → **补一个院子**摆在井旁边；
            #   · 修不掉的（重名/器物入屋/房间出屋）**如实报出来**，别沉默。
            #   ⚠ 这一段**不碰名字以外的任何东西**（位置/字形都留着），
            #     所以"没违规"的那些层出来的图与从前一模一样。
            # [EN] ★★ **Run spatial common sense over it** (user 2026-10-12):
            # [EN]   · tag the indoor layer with `kind='室内'` and `frame=<this place>` (the minimap then
            # [EN]   **frames** the whole building instead of dotting a red point that covers the content);
            # [EN]   · a well (or another outdoor object) but no courtyard -> **add a courtyard** beside
            # [EN]   the well;
            # [EN]   · whatever cannot be repaired (duplicate name / object indoors / room outdoors) is
            # [EN]   **reported honestly**, never silenced.
            # [EN] ⚠ This step **touches nothing but names** (positions and glyphs are left alone), so a
            # [EN] layer with no violations renders exactly as before.
            _sp = AT.apply_space_rules(lay, kind=tag if tag == '周边' else '室内',
                                       building=n)
            for _line in _sp:
                note(f'底图 · {n} · 空间常识：{_line}')
            if tag == '周边':
                at.local[n] = lay
                ok_local += 1
            else:
                at.indoor[n] = lay
                ok_indoor += 1
        if n in at.local or n in at.indoor:
            note(f'底图 · {n}：周边 {len(at.local.get(n).places) if n in at.local else 0} 处'
                 f' / 室内 {len(at.indoor.get(n).places) if n in at.indoor else 0} 处')
        else:
            note(f'底图 · {n}：周边与室内都是空的')
        await asyncio.sleep(0)              # 让出事件循环（长循环别把界面顶住）
        # [EN] Yield the event loop (long loops shouldn't block the UI)

    if not at.has_any():
        note('底图一层都没生成出来 —— 保留"每天现画"的老做法')
        return None

    note(f'底图完成：整体 {"有" if at.overview else "无"} · '
         f'局部 {ok_local} 处 · 室内 {ok_indoor} 处')
    AT.save(settings_dir, at)
    return at


# ══════════════════════════════════════════════════════════════════
#  生成：位图氛围底画（可选、贵、同步阻塞 → 由 GUI 丢线程）
# [EN] Generation: bitmap atmosphere base art (optional, expensive, synchronous blocking -> offloaded
# [EN] to a thread by the GUI)
# ══════════════════════════════════════════════════════════════════
def bitmap_dir(project) -> Path:
    """位图底画目录：`<项目>/地图/`（项目级 —— 跨轮复用靠的就是这个位置）。
        English:
    Bitmap base-art directory: `<project>/地图/` (project-level -- this is the location that enables
    reuse across rounds).
    """
    return Path(project.root) / AT.BITMAP_DIRNAME


def bitmap_path(project, layer: str, place: str = '') -> Path:
    """某层位图的路径。名字里带层与地点，一眼看得懂。
        English:
    Path to a certain layer's bitmap. The name contains the layer and location, understandable at a
    glance.
    """
    stem = f'{layer}' + (f'_{place}' if place else '')
    return bitmap_dir(project) / f'{stem}.png'


def build_bitmaps(project, atlas: AT.Atlas | None, *,
                  on_progress: Callable[[str], None] | None = None,
                  ) -> list[dict]:
    """给三层各出一张**位图氛围底画**；返回 `[{层, 地点, 文件}, …]`。

    ★ 只出**整体**一张 + 每处的**局部**一张。理由：室内层太细，
      位图在这个尺度上看不出东西（而那正是矢量室内层擅长的），
      一张图的钱不如省下来 —— 这是刻意的取舍得，不是漏了。

    走的是 `image_gen.ai.generate_ai_image()`，**同步阻塞**；任何一张失败都只是
    少一张（`generate_ai_image` 自己返回 None），不影响矢量底图。
    
        English:
    Produce one **bitmap ambience base art** for each of the three layers; returns `[{层, 地点, 文件},
    …]`.
        ★ Only produce one **overall** image + one **local** image per location. Reason: interior layers are too fine-grained,
          and bitmaps at this scale can't show anything (which is exactly what vector interior layers excel at),
          the cost of an image is better saved -- this is a deliberate trade-off, not an oversight.
        Uses `image_gen.ai.generate_ai_image()`, **synchronous blocking**; any single failure just means
        one fewer image (`generate_ai_image` returns None itself), and does not affect the vector base map.
    """
    def say(msg: str) -> None:
        _LOG.info('%s', msg)
        if on_progress:
            try:
                on_progress(msg)
            except Exception:                                   # noqa: BLE001
                pass

    if atlas is None or not atlas.has_any():
        return []
    try:
        from image_gen.ai import ai_available, generate_ai_image
    except Exception as e:                                      # noqa: BLE001
        say(f'位图底画跳过（模块不可用）：{e!r}')
        return []
    ok, why = ai_available()
    if not ok:
        say(f'位图底画跳过：{why}')
        return []

    out: list[dict] = []
    jobs: list[tuple[str, str]] = []
    if atlas.overview is not None:
        jobs.append(('整体', ''))
    jobs += [('局部', n) for n in list(atlas.local)[:AT.MAX_PLACES]]

    for layer, place in jobs:
        label = f'{layer}{"·" + place if place else ""}'
        say(f'正在画地图底图：{label}')
        subj = (f'一幅俯视的旧时小地方地图（{place}一带）' if place
                else '一幅俯视的旧时城镇地图，标出几处主要地点的相对方位')
        if layer == '整体' and atlas.overview is not None:
            subj += '，图上只有这些地方：' + '、'.join(
                p.name for p in atlas.overview.places[:8])
        p = generate_ai_image(subj, bitmap_path(project, layer, place))
        if p is None:
            say(f'地图底图没画成：{label}')
            continue
        out.append({'层': layer, '地点': place,
                    '文件': str(p.relative_to(Path(project.root)))})
    if out:
        say(f'地图底图完成：{len(out)} 张')
    return out
