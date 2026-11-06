# -*- coding: utf-8 -*-
"""**地图锚定**：同一处地方，在整个推演里永远是同一块位置。

用户 2026-10-26
---------------
「小地图和大地图 每次生成的感觉都有一些区别 有办法在整个小说推演过程中
  维持相同场景地图的一致性吗」

查到的三个病根（都是量出来的，不是猜的）
----------------------------------------
① **复用判据里塞了"今天的地点集合"**。`mapstore.basis_of()` 原来是
   `层//井/柜台/望江楼//望江楼` —— 今天多演一处灶房，这一串就变了 ⇒ 整张图作废
   ⇒ 重新问模型 ⇒ **同一处地点全换位置**。实测：
   `整体//井/柜台/望江楼//望江楼` 与 `整体//井/柜台/灶房/望江楼//望江楼` 判为不同。
   ⇒ 一天演几处地方本是常态，所以这个判据**几乎从不命中**。
② **没有"位置已定"这回事**。就算问出了新布局，也没有任何东西约束
   "临河茶肆昨天在左上、今天还在左上"。模型每次重排，图上自然"每次都不一样"。
③ **档位与内容不同源**。存档的档位取底图那一层的名字，而布局里 `kind` 是
   `day_layout()` 按内容重推的 —— 真数据里就有一份 `整体_望江楼.json` 而
   `kind` 写着 `室内`。存档名与内容打架 ⇒ 下次按名字读回来、渲染按 `kind` 画。

这一层解决的是 ②，并让 ① 不再是问题：**位置一旦落定，只允许新增，不允许改**。
①的判据也一并收窄（见 `mapstore.basis_of`）。

规则（一句话）
--------------
**同一 `(层, 主地点)` 下，每个地点名一旦有了坐标，此后每天都用它；
今天的布局只负责"补进没见过的地点"，已有的一处都不许动。**

为什么锚定在**项目级**而不是推演级
----------------------------------
用户要的是"在**整个**推演过程中一致"。用户嘴里的"这次推演"常常指整本书的开卷到收工
（跨 `第1次模拟…`/`第2次模拟…` 多个文件夹）。所以锚定跟着**项目**走
（`<项目>/地图/锚定.json`），与 `肖像/`、`地图/` 存档同一处 ——
换轮次继续写同一本书，茶楼还在原地。这与"存档跟着推演走"是两件不同的事，
两件都要（存档是"这一次的图"，锚定是"这处地方长什么样"）。

⚠ 铁律（与 `mapstore` / `llm.usage.record` 同一条）：**失败只记日志、绝不抛**。
  它是旁路；旁路把自己变成故障源是这类模块最常见的翻车方式。
  存不下时最坏结果 = 下次又按模型给的排（回到从前的行为），推演照跑。

English:
**Map anchoring**: the same place stays at the same spot for the whole simulation.
The user (2026-10-26): "the minimap and big map feel a bit different every time they are generated;
is there a way to keep the same scene map consistent across the whole novel simulation?"
Three measured root causes: ① the reuse fingerprint **included today's set of places**, so one extra
place invalidated the whole map and forced a fresh model call that re-arranged everything;
② **nothing recorded "this position is settled"**, so every new layout was free to move the teahouse
from the top-left to the bottom-right; ③ the archive tier and the layout's own `kind` came from two
different sources (a real file is named `整体_望江楼.json` while its `kind` says `室内`).
This layer fixes ② and makes ① moot: **once settled, positions may only be added to, never moved**.
The rule in one sentence: under the same `(layer, main place)`, every place name keeps its
coordinates forever; today's layout only contributes places never seen before.
Anchors live at the **project** level (`<project>/地图/锚定.json`) because "consistent across the whole
simulation" means across runs, not just within one. ⚠ Iron rule: **log on failure, never throw**.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from image_gen.map_layout import Layout, Place, _spare_slot

__all__ = [
    'ANCHOR_FILE', 'VERSION', 'MIN_GAP',
    'path_of', 'load', 'save',
    'layer_of', 'slot_of', 'apply', 'fill', 'summary', 'clear',
]

_LOG = __import__('logging').getLogger('nws.mapanchor')

#: 锚定文件名（在 `<项目>/地图/` 下，与 `mapstore` 的存档同目录）。
# [EN] Anchor filename (inside `<project>/地图/`, the same directory as `mapstore`'s archive).
ANCHOR_FILE = '锚定.json'

#: 格式版本。改结构就 +1；读回时版本更大就当作没有（不猜）。
# [EN] Format version; bump on structural change. A larger version on read is treated as absent.
VERSION = 1

#: 两个地点靠得比这更近就算"撞在一起"（0~1 坐标的欧氏距离）。
#: 0.10 ≈ 这块地图上肉眼能分清的最近距离；比它近，两个方块与标签会叠住。
# [EN] Two places closer than this count as colliding (Euclidean distance in 0~1 coordinates).
# [EN] 0.10 is about the closest two blocks and labels can sit without overlapping.
MIN_GAP = 0.10

#: 层名的规范说法。`day_layout` 会推出 `室内` / `局部`，底图那边还有 `整体`。
#: ⚠ 认不出的层名**原样保留**（不硬塞成某一档）：硬塞会让两本书的"局部"混在一起。
# [EN] Canonical layer names. `day_layout` derives `室内` / `局部`, and the base map also has `整体`.
# [EN] ⚠ An unrecognized layer name is **kept as-is**: forcing it into a tier would mix two books'
# [EN] "local" maps together.
LAYERS = ('整体', '局部', '室内')


def layer_of(kind: str) -> str:
    """`Layout.kind` / 底图层名 → 规范的层名。

    同一处地方在不同"层"下**本来就该长得不同**（室内是平面图、整体是方位图），
    所以锚定必须按层分开 —— 把两种图的坐标混在一份里，切层时就会跳。
    [EN] A place legitimately looks different per layer (interior floor plan vs. overall bearing
    map), so anchors must be keyed by layer. Mixing the two coordinate systems in one record makes
    the map jump whenever the layer changes.
    """
    k = str(kind or '').strip()
    return k if k else '局部'


def path_of(project) -> Path | None:
    """锚定文件的路径（**只算，不建目录**）。拿不到项目就 `None`。

    ⚠ 复用 `mapstore.dir_of` 的三种入参兼容（`Project` / `Path` / `str`）——
      地图目录**只能有一处算**：两处各算一遍，一处写成 `C:/地图/` 那种盘根，
      另一处写对，结果是"有时记得住、有时记不住"。
    [EN] The anchor file's path (**computed only, no mkdir**). None without a project.
    [EN] ⚠ Reuses `mapstore.dir_of`'s three input forms -- the map directory **must be computed in
    [EN] one place**; two copies would put one at the drive root and the other correctly, i.e.
    [EN] "sometimes it remembers, sometimes it doesn't".
    """
    try:
        from image_gen import mapstore as MS
        d = MS.dir_of(project)
        return None if d is None else d / ANCHOR_FILE
    except Exception:                                            # noqa: BLE001
        return None


def load(project) -> dict:
    """读回锚定（没有 / 坏了 / 版本更新 → 空 dict，**不抛**）。"""
    p = path_of(project)
    if p is None or not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('锚定读回失败（当作没有）：%r', e)
        return {}
    if not isinstance(data, dict):
        return {}
    if int(data.get('版本') or 0) > VERSION:
        # 更新的软件写的：不猜它能读（猜错的表现是"地图上东西跑到莫名位置"）。
        # [EN] Written by a newer build: don't guess (a wrong guess shows up as "things on the map
        # [EN] moved to bizarre positions").
        return {}
    layers = data.get('层')
    return layers if isinstance(layers, dict) else {}


def save(project, layers: dict) -> bool:
    """落盘（失败只记日志）。**先写临时文件再替换** —— 中断不会留下半截 JSON。"""
    p = path_of(project)
    if p is None or not isinstance(layers, dict):
        return False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.json.tmp')
        tmp.write_text(json.dumps({'版本': VERSION, '层': layers},
                                  ensure_ascii=False, indent=1), encoding='utf-8')
        tmp.replace(p)
        return True
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('锚定写盘失败（下次照常按模型排）：%r', e)
        return False


def slot_of(layers: dict, layer: str, place: str) -> dict:
    """取 `(层, 主地点)` 那一格（没有就空 dict，**不建**）。"""
    a = (layers or {}).get(layer_of(layer))
    if not isinstance(a, dict):
        return {}
    s = a.get(str(place or '') or '未命名')
    return s if isinstance(s, dict) else {}


# ── 纯函数：贴锚定 / 补地点 ──────────────────────────────────────────
def _record_of(p: Place) -> dict:
    """一个地点的锚定值（**只存渲染真正读的那些**）。

    ⚠ `note` 也存：它是图上的小注（"河在下方"这类），换了会让人以为换了一张图。
      `room`（陈设归哪间房）存 —— 它决定柜台画在哪个框里，变了就是"柜台跑墙外"。
    [EN] A place's anchored values (**only what rendering actually reads**). `note` is included (a
    [EN] changed note makes it look like a different map), and so is `room` (it decides which frame a
    [EN] fixture is drawn in -- a change is exactly "the counter ran outside the wall").
    """
    return {'x': round(float(p.x), 3), 'y': round(float(p.y), 3),
            'shape': str(p.shape or ''), 'size': str(p.size or ''),
            'short': str(p.short or ''), 'room': str(p.room or ''),
            'note': str(p.note or '')}


def _too_close(lay: Layout, x: float, y: float, *, skip: str = '') -> str:
    """`(x, y)` 与图上其它点撞了吗？撞了返回那个点的名字，否则空串。"""
    for p in lay.places:
        if skip and p.name == skip:
            continue
        if (p.x - x) ** 2 + (p.y - y) ** 2 < MIN_GAP ** 2:
            return p.name
    return ''


def apply(lay: Layout, layer: str = '', place: str = '',
          layers: dict | None = None) -> tuple[Layout, dict, list[str]]:
    """把锚定值贴到这张布局上，并把**新见到**的地点记进锚定。

    返回 `(布局, 更新后的锚定, 说明行)`。布局是**就地改**（调用方本来就是拿它去画）。

    | 情形 | 怎么办 |
    |---|---|
    | 这一处**锚定过** | 坐标/形状/尺寸/简称/所属房间/小注 **一律用锚定值**（模型的不算） |
    | 这一处**没锚定过**、且不撞人 | 用模型给的，记进锚定（**这就是它以后的位置**） |
    | 这一处没锚定过、但**撞到别人** | 用 `_spare_slot` 挪到空位再记（老的一处都不动） |
    | `frame` / `caption` | 非空且没锚定时记下；已锚定就用锚定的 |

    ★ 为什么"模型的不算"要这么硬：模型的坐标是**这一次**的构图，而锚定是
      **这处地方长什么样**。两者冲突时必须让"长什么样"赢 —— 不然一致性就是空话。
    ★ 为什么撞了要挪**新的**：挪老的就等于允许每次改，那正是要治的病。
      挪新的最坏结果是"今天这一处摆得不太好看"，而老的一处不少、位置不动。
    ★ 三条说明行是给日志/界面看的（"3 处沿用、1 处新定、1 处挪开"），
      不写就没法回答"为什么今天这张和昨天不一样"。
    [EN] Stamp the anchored values onto this layout and record newly seen places.
    [EN] Returns `(layout, updated anchors, explanation lines)`; the layout is modified in place.
    [EN] ★ Why "the model's value doesn't count" is this absolute: the model's coordinates are **this
    [EN] one composition**, while an anchor is **what this place looks like**. On conflict the latter
    [EN] must win, or consistency is empty talk.
    [EN] ★ Why the **newcomer** gets moved: moving an old one means allowing change every time, which
    [EN] is the disease. Moving the newcomer at worst looks clumsy today, while nothing old is lost.
    """
    lay_layers = layers if isinstance(layers, dict) else {}
    L = layer_of(layer or getattr(lay, 'kind', '') or '局部')
    K = str(place or '').strip() or str(getattr(lay, 'frame', '') or '').strip() or '未命名'
    slot = lay_layers.setdefault(L, {}).setdefault(K, {})
    kept: list[str] = []
    fresh: list[str] = []
    moved: list[str] = []

    # ① 先贴"已经锚定过"的（这一遍不做避让：老的位置就是老的位置，哪怕它们当年就更近）
    # [EN] ① First stamp the anchored ones (no collision pass here: an old position IS the old
    # [EN] position, even if two of them were already close back then).
    for p in lay.places:
        rec = slot.get(p.name)
        if not isinstance(rec, dict):
            continue
        for k in ('x', 'y', 'shape', 'size', 'short', 'room', 'note'):
            if k in rec and rec[k] not in (None, ''):
                setattr(p, k, rec[k])
        p.x, p.y = float(p.x), float(p.y)
        kept.append(p.name)

    # ② 再处理没锚定过的：撞了就挪，挪完记下来（**记的是挪完的位置**）
    # [EN] ② Then the not-yet-anchored: move on collision, then record **the moved position**.
    for p in lay.places:
        if p.name in slot:
            continue
        if _too_close(lay, p.x, p.y, skip=p.name):
            pos = _spare_slot([q for q in lay.places if q.name != p.name],
                              len(fresh))
            old = (p.x, p.y)
            p.x, p.y = float(pos['x']), float(pos['y'])
            moved.append(f'{p.name}({old[0]:.2f},{old[1]:.2f})→({p.x:.2f},{p.y:.2f})')
        slot[p.name] = _record_of(p)
        fresh.append(p.name)

    # ③ 层的标题（`frame` 是室内图上那个框上的建筑名；`caption` 是角落题记）
    # [EN] ③ The layer's titles (`frame` is the building name on the indoor frame, `caption` the
    # [EN] corner note).
    for attr in ('frame', 'caption'):
        cur = str(getattr(lay, attr, '') or '')
        anc = str(slot.get(f'_{attr}') or '')
        if anc:
            setattr(lay, attr, anc)
        elif cur:
            slot[f'_{attr}'] = cur

    why: list[str] = []
    if kept:
        why.append(f'沿用 {len(kept)} 处')
    if fresh:
        why.append(f'新定 {len(fresh)} 处（{"/".join(fresh[:3])}'
                   + ('…' if len(fresh) > 3 else '') + '）')
    if moved:
        why.append('挪开 ' + '、'.join(moved[:2]))
    return lay, lay_layers, why


def fill(lay: Layout, wanted: list[str], *, here: str = '',
         also: list[str] | None = None) -> tuple[Layout, list[str]]:
    """把**今天该有、图上还没有**的地点补进这张图（用空位，**一处老的都不动**）。

    ★ 这是"复用旧图"能成立的关键那一半：
      复用判据不再看"今天的地点集合"（那样一天一变、等于永不命中），
      改成"这一层这一处画过没有"。于是今天多出现一处地方时，
      必须能把它**补进旧图** —— 补不进来就只剩两条路：整张重排（一致性没了）
      或者装作没这一处（图上缺东西）。两条都不该走。
    ★ `also`（2026-10-26 补）：**锚定里已经有、但这次模型没给**的那些名字。
      为什么必须有：光补"今天该有的"不够 —— 模型明天可能忘了画灶房
      （它昨天画过、锚定里有），图上就"今天有明天没"。
      那和位置乱跑一样是**不一致**，而且更显眼（东西凭空消失）。
      把这些名字也补进来，再由 `apply` 把锚定坐标贴回去 ⇒ 它还在老地方。
    ★ 补进来的地点**形状按名字猜**（`_guess_shape`），不调模型：
      这一步发生在"复用"路径上，那条路径的全部意义就是**零成本**。
      猜错的最坏结果是一处方块形状不太贴切，而位置是对的。
    ⚠ `here` 本人必须在图上：它没被补进来时补一次（否则"我现在在哪"看不见）。
    [EN] Add the places **today should have but this map lacks** (using spare slots, moving nothing
    [EN] old). ★ This is the half that makes "reuse the old map" viable. ★ `also` (added 2026-10-26):
    [EN] names **already anchored but missing from what the model gave this time**. Adding only
    [EN] "what today needs" is not enough -- the model may forget to draw the kitchen it drew
    [EN] yesterday (it is in the anchors), so the map "has it today, not tomorrow", which is just as
    [EN] inconsistent as wandering positions and more visible (things vanish). Such names are added
    [EN] too, and `apply` then stamps the anchored coordinates back, so they reappear where they were.
    [EN] ★ Shapes are guessed from names (`_guess_shape`) with **no model call**: this path exists to
    [EN] be free. ⚠ `here` must be on the map; add it once if missing.
    """
    have = {p.name for p in lay.places}
    added: list[str] = []
    todo: list[str] = []
    for src in (list(wanted or []), list(also or [])):
        for n in src:
            nm = str(n).strip()
            if nm and nm not in have and nm not in todo and not nm.startswith('_'):
                todo.append(nm)
    h = str(here or '').strip()
    if h and h not in have and h not in todo:
        todo.append(h)
    for i, nm in enumerate(todo):
        pos = _spare_slot(lay.places, i)
        lay.places.append(Place(name=nm, x=float(pos['x']), y=float(pos['y']),
                                shape=_guess_shape(nm), size='中',
                                note='今日' if nm == h else ''))
        added.append(nm)
    if added:
        # 补进来的点连一条路：只把**最后补的那个**连到最近的旧点 ——
        # 全连会织成一张网，而它本来只是一处新地方。
        # [EN] Link only the most recently added to its nearest old place; connecting all of them
        # [EN] would weave a web for what is really one new place.
        try:
            new = lay.places[-1]
            olds = [p for p in lay.places if p.name != new.name]
            if olds:
                near = min(olds, key=lambda p: (p.x - new.x) ** 2 + (p.y - new.y) ** 2)
                lay.links.append({'a': near.name, 'b': new.name, 'kind': '路'})
        except Exception:                                        # noqa: BLE001
            pass
    return lay, added


def _guess_shape(name: str) -> str:
    """按名字猜形状（**只用于补进来的地点**，不覆盖任何已有地点）。

    与 `minimap._is_fixture` / `_is_room` 那一套同源判断（门/院/台/楼…），
    但这里**只输出 `Place.shape` 那几个合法值**（`屋/院/楼/门/台/桥/树…`），
    不判断"是不是陈设"。
    [EN] Guess the shape from the name (**only for added places**, never overriding an existing
    [EN] one). Same family as `minimap`'s kind checks, but only emits legal `Place.shape` values.
    """
    n = str(name or '')
    import re
    table = (
        (r'门|口|闸|关', '门'),
        (r'院|庭|场|坝', '院'),
        (r'楼|阁|塔|寺|庙|观|祠', '楼'),
        (r'台|案|柜台|摊|桌', '台'),
        (r'桥', '桥'),
        (r'树|林|柳|竹|松', '树'),
        (r'河|溪|江|湖|塘|井|池|渡', '水'),
        (r'街|路|巷|道', '路'),
    )
    for pat, shape in table:
        if re.search(pat, n):
            return shape
    return '屋'


def summary(layers: dict, layer: str, place: str) -> str:
    """一句话（给日志/界面）：`室内·望江楼：已定 6 处`。"""
    slot = slot_of(layers, layer, place)
    n = len([k for k in slot if not str(k).startswith('_')])
    return f'{layer_of(layer)}·{place or "未命名"}：已定 {n} 处'


def clear(project) -> bool:
    """清掉锚定（用户想"重新排一次"时用）。**只删这一个文件**。"""
    p = path_of(project)
    if p is None or not p.is_file():
        return False
    try:
        p.unlink()
        return True
    except OSError:
        return False
