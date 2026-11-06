# -*- coding: utf-8 -*-
"""地图的**本地存档与复用**（用户 2026-10-12 点名的那件事）。

用户原话
--------
「所有的地图**保存在本地**，如果后续场景**能够复用的话则直接复用**」。

为什么需要它（不是"加个缓存"那么轻）
------------------------------------
地图在这个项目里有**两条**生成路径，成本差着一个数量级：

  · **算出来的**（`image_gen/minimap.py` / `image_gen/floorplan.py`）——
    拿一份 `Layout` 画矢量形状，**零 LLM、瞬时**；
  · **问出来的**（`crew/agents.day_map_note()` 等）—— 要调模型读当天剧情，
    **一次真金白银的调用**。

用户要的是：**同一处地方、同一种细致的图，画过就存下来**；
下次（换了一天、换了一轮、甚至换了本书重开）要画同一张图时，
**直接读回来**，不要再问一次模型。

所以这里存的是**地图的规格**（`Layout` 的 JSON），不是位图：
  · 规格是"这张图长什么样"的**唯一真相**，渲染器是纯函数 —— 同一份规格
    永远画出同一张图（小地图与大地图只是**比例不同**，不是两份数据）；
  · 位图存下来就过期了（改配色、改字号都要重画一遍），而规格不会。

存在哪
------
`<项目>/地图/`（**项目级** —— 跨轮复用靠的就是这个位置，
与 `<项目>/肖像/` 同一套路数；`world/atlas.py` 里那个 `BITMAP_DIRNAME`
就是这个目录名）。

文件名 = `<细致程度>_<地点名>.json`（`safe_name()` 过一遍，免得地点名里
带个 `/` 就写不出来了）。

⚠ 一条铁律（与 `llm/usage.record()` 同一条）：**失败只记日志、绝不抛**。
  存档是**旁路** —— 旁路把自己变成故障源是这类模块最常见的翻车方式
  （磁盘满 / 文件被占）。存不下时推演照跑，只是下次还得重画。

English:
**Local archive and reuse of maps** (the matter the user named on 2026-10-12).
The user's exact words
--------
"all maps are **saved locally**; if a later scene **can reuse** one, just reuse it".
Why this is needed (it is not as light as "add a cache")
------------------------------------
Maps in this project have **two** generation paths, an order of magnitude apart in cost:
  · **computed** (`image_gen/minimap.py` / `image_gen/floorplan.py`) -- take a `Layout` and draw
    vector shapes, **zero LLM, instantaneous**;
  · **asked for** (`crew/agents.day_map_note()` etc.) -- calls the model to read the day's plot,
    **one real paid call**.
What the user wants: **the same place with the same level of detail, once drawn, is kept**; next
time (another day, another round, even reopening another book) when the same map is needed,
**read it back directly** instead of asking the model again.
So what is stored here is the map's **spec** (the `Layout` JSON), not a bitmap:
  · the spec is the **single source of truth** for "what this map looks like", and the renderer is a
    pure function -- one spec always draws one map (the minimap and the big map differ only in
    **scale**, not in data);
  · a stored bitmap goes stale (change a colour or a font size and it must be redrawn), a spec does
    not.
Where it lives
------
`<project>/地图/` (**project level** -- this location is what enables cross-round reuse, the same
approach as `<project>/肖像/`; the `BITMAP_DIRNAME` in `world/atlas.py` is this directory name).
Filename = `<level of detail>_<place name>.json` (run through `safe_name()` so a `/` in a place
name doesn't make it unwritable).
⚠ One iron rule (the same as `llm/usage.record()`): **on failure, log only, never throw**.
  Archiving is a **bypass** -- a bypass turning itself into a failure source is the most common way
  this kind of module crashes (disk full / file locked). When it cannot be written the simulation
  runs on; it just has to redraw next time.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from logger import get_logger

_LOG = get_logger('nws.mapstore')

#: 项目里存地图的目录名（与 `world.atlas.BITMAP_DIRNAME` **同一个**）。
# [EN] : the map directory name inside a project (**the same one** as `world.atlas.BITMAP_DIRNAME`).
DIRNAME = '地图'

#: 存档的格式版本。**改了存档结构就要 +1** —— 读回时版本对不上就当作废，
#: 而不是硬套（硬套的表现是"地图上少了几样东西"，且**不报错**）。
# [EN] : archive format version. **Bump it whenever the archive structure changes** -- on read-back a
# [EN] version mismatch is treated as stale rather than forced through (forcing shows up as "a few
# [EN] things missing from the map", and **does not error**).
VERSION = 1


def dir_of(project) -> Path | None:
    """项目的地图目录（**只算路径，不建目录**）。拿不到项目就 None。

    ★ `project` **三种都认**：`Project` 对象（取 `.root`）、`Path`、字符串。
      为什么必须都认：调用方有两拨 —— 界面拿的是 `Project`，
      主循环手上只有 `runfolder.project_dir`（一个 `Path`）。
      只认一种的话，另一拨会静默地**存不下来**（`dir_of` 返回 None，
      `save()` 直接返回 False，而它本来就是"失败只记日志"）。

    ⚠⚠ **`Path` 也有 `.root` 属性**（`Path('C:/a/b').root` = `'C:\\'`）——
      所以 `getattr(project, 'root', project)` 这种"兼容写法"**必须在前面
      先判 `isinstance`**，否则传进来一个 `Path`，拿到的是**盘根**，
      存档会写到 `C:/地图/` 去（真实踩到：判据 E6b 当场发现上一轮的文件还在，
      因为写到了盘根而不是临时目录）。这个坑在本项目**踩过第二次**了
      （第一次是 `crew/catalog` 写到了 `C:/agents`）。
    [EN] The project's map directory (**path only, does not create it**). None if no project.
    [EN] ★ `project` **accepts three forms**: a `Project` object (takes `.root`), a `Path`, or a
    [EN] string.
    [EN] Why all three: there are two kinds of caller -- the UI holds a `Project`, while the main loop
    [EN] only has `runfolder.project_dir` (a `Path`). Recognizing only one means the other silently
    [EN] **cannot save** (`dir_of` returns None and `save()` returns False, and by design it "only
    [EN] logs on failure").
    [EN] ⚠⚠ **`Path` also has a `.root` attribute** (`Path('C:/a/b').root` = `'C:\\'`) -- so that
    [EN] "compatible" form `getattr(project, 'root', project)` **must be preceded by an `isinstance`
    [EN] check**, otherwise a `Path` argument yields the **drive root** and the archive lands in
    [EN] `C:/地图/` (actually hit: criterion E6b found the previous round's file still there because it
    [EN] had been written to the drive root instead of the temp directory). This trap has now been hit
    [EN] **twice** in this project (the first time `crew/catalog` wrote to `C:/agents`).
    """
    # ⚠ 顺序不能反：`Path` 有 `.root`，必须先认出来（见上面那一段）。
    # [EN] ⚠ Order matters: `Path` has `.root`, so it must be recognized first (see the note above).
    if isinstance(project, (str, Path)):
        root = project
    elif hasattr(project, '__fspath__') and not hasattr(project, 'root'):
        root = project
    else:
        root = getattr(project, 'root', None)
    if root is None:
        return None
    try:
        if not isinstance(root, (str, Path)) and not hasattr(root, '__fspath__'):
            return None
        return Path(root) / DIRNAME
    except Exception:                                            # noqa: BLE001
        return None


def key_of(detail: str, name: str) -> str:
    """存档的文件名：`<细致程度>_<地点名>.json`。

    ⚠ 地点名要过 `safe_name()`：地图上的名字来自设定（作者手写），
      里面完全可能出现 `/`、`:`、`*` 这类**在 Windows 上非法**的字符 ——
      不过这一关就是"存不下来"，而且**不报错**（写盘失败被吞掉）。
    [EN] The archive's filename: `<level of detail>_<place name>.json`.
    [EN] ⚠ The place name must pass through `safe_name()`: names on the map come from the settings
    [EN] (hand-written by the author) and may well contain `/`, `:`, `*` and the like, which are
    [EN] **illegal on Windows** -- skipping this means "it just won't save", and **without erroring**
    [EN] (the write failure is swallowed).
    """
    from util.io import safe_name
    d = safe_name(str(detail or 'map').strip()) or 'map'
    n = safe_name(str(name or '未命名').strip()) or '未命名'
    return f'{d}_{n}.json'


def signature_of(layout) -> str:
    """这份布局的**指纹**：名字 + 摆位 + 是哪一层。

    ★ 它回答的是"**画出来的东西是不是同一张**"。
    [EN] This layout's **fingerprint**: names + placement + which layer.
    [EN] ★ It answers "**is the drawn result the same picture**".
    """
    try:
        return f'{getattr(layout, "kind", "")}|' + str(layout.signature())
    except Exception:                                            # noqa: BLE001
        return ''


def basis_of(detail: str, names: list | None = None, here: str = '') -> str:
    """**复用判据的指纹**：`层//主地点`。**只有这两样**。

    ★★★ 2026-10-26 收窄（用户：「小地图和大地图 每次生成的感觉都有一些区别
      有办法在整个小说推演过程中维持相同场景地图的一致性吗」）：
      原来这一串里还拼着「今天的**地点集合**」，形如
      `整体//井/柜台/望江楼//望江楼`。问题是：**故事一天演几处地方本是常态**，
      今天多演一处灶房、明天少演一处院子，这串就变 ⇒ 整张图作废 ⇒ 重新问模型
      ⇒ 同一处地点**全换位置**。实测：
      `整体//井/柜台/望江楼//望江楼` 与 `整体//井/柜台/灶房/望江楼//望江楼` 判为不同。
      ⇒ 这个判据在实际推演里**几乎从不命中**，用户看到的就是"每次都不一样"。

    ★ 现在判的是"**这一层这一处画过没有**"：
      · 同一层、同一处主地点 ⇒ 就是**同一张地方**，复用；
      · 今天多出来的地点 ⇒ 由 `image_gen.mapanchor.fill()` **补进旧图**
        （动的只有新来的那几处，老的一处都不动）；
      · 换了层（从楼里走到城里）或换了主地点 ⇒ 自然不复用，该重画。
      一致性靠的是 `mapanchor` 那一层（位置一旦落定永不改），不是靠这个判据。

    ⚠ 参数 `names` / `here` **保留但不再参与**：调用点有七八处，改签名要让它们全动，
      而它们本来也判断不了"这处地方长什么样"。留着是给以后的判据看的。
    [EN] **The reuse fingerprint**: `layer//main place`. **Only those two.**
    [EN] ★★★ Narrowed on 2026-10-26 (the user: "the minimap and big map feel a bit different every
    [EN] time; can we keep scene maps consistent across the whole simulation?"). It used to include
    [EN] **today's set of places**, so one extra place (a kitchen today, one fewer courtyard
    [EN] tomorrow -- utterly normal) changed the string, invalidated the map, forced a new model call
    [EN] and **moved everything**. Measured: `整体//井/柜台/望江楼//望江楼` vs
    [EN] `整体//井/柜台/灶房/望江楼//望江楼` compare as different. In practice it **almost never
    [EN] matched**, which is exactly the "different every time" the user saw.
    [EN] ★ It now asks "**has this place been drawn at this level**": same layer + same main place =>
    [EN] the same place, reuse it. Places new today are **added to the old map**
    [EN] (`image_gen.mapanchor.fill()`), moving only the newcomers. A different layer or main place
    [EN] naturally misses and should be redrawn. Consistency is guaranteed by the `mapanchor` layer
    [EN] (a settled position never moves), not by this fingerprint.
    [EN] ⚠ `names` / `here` are **kept but no longer used**: there are seven or eight call sites, and
    [EN] they could never answer "what does this place look like" anyway.
    """
    d = str(detail or '').strip()
    k = str(here or '').strip() or '未命名'
    return f'{d}//{k}'


def _basis_legacy_prefix(basis: str) -> str:
    """旧格式 `层//地点集合//这里` → `层//这里`（用来认出**旧存档**）。

    ★ 为什么需要：判据一收窄，盘上那些按旧格式写的存档就全部"对不上" ⇒ 全部重画一张。
      重画本身没错（那些图本来也不一致），但**能让它认的旧档就该认** ——
      两份图其实是同一处地方，白白多花一次模型调用。
    ⚠ 只做"旧的前缀匹配"，**不做模糊匹配**：把不同的地方认成同一处，
      比多问一次模型糟得多（画出来的是别的地方，而且不报错）。
    [EN] Old-format `layer//place set//here` -> `layer//here`, used to recognize **old archives**.
    [EN] ★ Why: narrowing the fingerprint makes every archive written in the old format "mismatch",
    [EN] hence a redraw. The redraw is fine (those maps were inconsistent anyway), but an archive we
    [EN] **can** recognize should be recognized rather than spending another model call.
    [EN] ⚠ Prefix matching only, never fuzzy: mistaking one place for another is far worse than one
    [EN] extra call (you get a map of somewhere else, and nothing errors).
    """
    b = str(basis or '')
    parts = b.split('//')
    if len(parts) == 3:
        return f'{parts[0]}//{parts[2]}'
    return ''


def load(project, detail: str, name: str, *,
         basis: str = '', expect: str = '') -> object | None:
    """读回一张存过的地图；没有 / 坏了 / 对不上就 `None`（**不抛**）。

    `basis` 非空 → 存档里的**依据指纹**必须一致才复用（"后续场景能够复用"的判据，
    在**问模型之前**就该判的那一道）。
    `expect` 非空 → 存档里的**布局指纹**也要一致（"画出来的是不是同一张"）。
    两个都传空 = 只看 `(细致程度, 地点名)` 这个键，不比对内容。
    [EN] Read back a saved map; None if missing / broken / mismatched (**no throw**).
    [EN] `basis` non-empty -> the archived **basis fingerprint** must match (the criterion for "a
    [EN] later scene can reuse it", the check that must happen **before asking the model**).
    [EN] `expect` non-empty -> the archived **layout fingerprint** must match too ("is the drawn
    [EN] result the same picture").
    [EN] Both empty = key only (`(level of detail, place name)`), content not compared.
    """
    d = dir_of(project)
    if d is None:
        return None
    try:
        p = d / key_of(detail, name)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('版本') != VERSION:
            return None
        if basis and str(data.get('依据') or '') != basis:
            # ★ 2026-10-26：旧格式（`层//地点集合//这里`）只要**前缀对得上**就认 ——
            #   见 `_basis_legacy_prefix` 的说明。认下来省一次模型调用，
            #   而且它是**同一处地方**的图，位置由 `mapanchor` 统一，不会因为
            #   "当年多画了灶房"而互相矛盾。
            # [EN] ★ 2026-10-26: an old-format archive is accepted when its **prefix** matches --
            # [EN] see `_basis_legacy_prefix`. That saves a model call, and it is the map of the
            # [EN] **same place**; positions are unified by `mapanchor`, so no contradiction arises
            # [EN] from "it happened to include the kitchen back then".
            if _basis_legacy_prefix(str(data.get('依据') or '')) != basis:
                return None
        if expect and str(data.get('指纹') or '') != expect:
            return None
        from image_gen.map_layout import Layout
        lay = Layout.from_dict(data.get('布局'))
        if lay is None or not lay.places:
            return None
        return lay
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('地图存档读回失败（当作没有）：%r', e)
        return None


def save(project, detail: str, name: str, layout, *, basis: str = '') -> bool:
    """把一张地图存起来。**失败只记日志、绝不抛**（旁路不该变成故障源）。
        English:
    Save one map. **On failure, log only, never throw** (a bypass must not become a failure source).
    """
    d = dir_of(project)
    if d is None or layout is None or not getattr(layout, 'places', None):
        return False
    try:
        from util.io import atomic_write_text
        p = d / key_of(detail, name)
        atomic_write_text(p, json.dumps({
            '版本': VERSION,
            '细致程度': str(detail or ''),
            '地点': str(name or ''),
            '指纹': signature_of(layout),
            '依据': str(basis or ''),
            '存于': time.strftime('%Y-%m-%d %H:%M:%S'),
            '布局': layout.to_dict(),
        }, ensure_ascii=False, indent=1))
        _LOG.info('地图存档：%s（%d 处）', p.name, len(layout.places))
        return True
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('地图存档写盘失败（下次重画即可）：%r', e)
        return False


def saved(project) -> list[dict]:
    """已经存了哪些地图（给界面/判据看）。读不到就空表。
        English:
    Which maps are already saved (for the UI / criteria). Empty list if unreadable.
    """
    d = dir_of(project)
    out: list[dict] = []
    if d is None or not d.exists():
        return out
    for p in sorted(d.glob('*.json')):
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('版本') != VERSION:
                continue
            lay = data.get('布局') or {}
            out.append({'文件': p.name,
                        '细致程度': str(data.get('细致程度') or ''),
                        '地点': str(data.get('地点') or ''),
                        '处数': len(lay.get('places') or []),
                        '存于': str(data.get('存于') or '')})
        except Exception:                                        # noqa: BLE001
            continue
    return out


def reuse(project, detail: str, name: str, basis: str) -> object | None:
    """**复用入口**（在**问模型之前**调）：同一局面存过 → 直接给回那一张。

    调用方的用法（一句话）：**要算/要问一张图之前先问它**；
    给回了就用它画（零成本），没给回就去算，算完再 `save(..., basis=...)`。
    [EN] **The reuse entry point** (called **before asking the model**): if the same situation is
    [EN] archived -> hand that one back directly.
    [EN] How a caller uses it (in one sentence): **ask it before computing/asking for a map**; if it
    [EN] gives something back, draw with that (zero cost); if not, compute, then
    [EN] `save(..., basis=...)`.
    """
    return load(project, detail, name, basis=basis)


def reuse_layout(project, layout, detail: str, name: str) -> object | None:
    """**按画出来的东西**复用：同一份布局存过就给回（对话框/重画那条路用它）。
    [EN] **Reuse by what is drawn**: if the same layout is archived, hand it back (used by the
    [EN] dialog / redraw path).
    """
    if layout is None:
        return None
    return load(project, detail, name, expect=signature_of(layout))
