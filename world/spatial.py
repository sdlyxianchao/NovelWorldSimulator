# -*- coding: utf-8 -*-
"""**空间常识**：什么地方是屋里的、什么是屋外的，以及由此而来的硬规矩。

用户 2026-10-12 的原话（这一段就是本模块的全部规格）
----------------------------------------------------
    「请**严格区分室内室外** 如果要画地图 请在写小说或者编剧的时候就把环境
      平面描述的很清楚 像现在**临河茶肆** 有**柜台 井 门**等 **井肯定是要在
      （⚠ 原话里点的是那本书的楼名；按 `verify_generic_project` 的通用性规则，
        这里一律换成程序自带的演示夹具名。）
      [EN] (⚠ The original words named that book's own building; per `verify_generic_project`'s
      [EN] genericity rule it is replaced here with the program's own demo fixture name.)
      院子里的** 不能够在屋里 **这种错误不能够出现**
      还有**如果有井 则说明有院子 需要把院子也画出来**」

## 为什么需要它

在这之前，"屋里/屋外"这件事**只存在于模型的语感里**：底图那一层
（`world/atlas.py` 的 `室内` 层）拿到的是一串**平铺的名字** ——
`堂屋 / 后院 / 侧案 / 井 / 柜台 / 大门`。程序**不区分**它们：

  · 井（必须在院子里）与堂屋（在屋里）**长得一样**，都被画成图上的一个点；
  · 模型给什么就画什么，"堂屋边上那口井"这种错**没有任何地方拦得住**；
  · 更根本的：**有井就意味着有院子**，而院子常常根本不在那串名字里。

所以本模块把这份常识**变成代码**（纯函数、零 LLM、零依赖），三处都用得上：

| 谁 | 用哪个函数 | 干什么 |
|---|---|---|
| 底图生成（`world/atlas.py`） | `repair()` | 出图前过一遍：缺院子补院子，脏数据挡住 |
| 小地图渲染（`image_gen/minimap.py`） | `space_of()` | 室内图上按"屋里/院里"分组着色、外围框住 |
| 剧本/导演/演员提示词 | `hint_block()` / `route()` | 把"这一处长什么样、从哪儿到哪儿怎么走"**当面写清** |

## 一条硬规矩

> **屋外的东西不许画进屋里；有井就有院，院子必须一起画。**

这不是风格问题，是**可核对**的事实问题：井要见天下雨（水脉、打水的动线），
院墙把内外隔开（谁进得来、谁被挡在外面），这些**决定了戏怎么演**
（"后院打水时听见墙外有人" —— 没有院墙这句话就不成立）。

English:
**Spatial common sense**: what is indoors and what is outdoors, and the hard rules that
follow from it.
The user's exact words on 2026-10-12 (this passage is the entire spec for this module)
----------------------------------------------------
    "Please **strictly distinguish indoors and outdoors**. If you are going to draw a map, describe the
      environmental floor plan very clearly when writing the novel or the script. Like the current
      **Mo Wen Tower**, it has a **counter, a well, a gate**, etc. **A well definitely belongs in the
      courtyard**, it can't be indoors. **This kind of mistake must not happen.**
      Also, **if there is a well, that means there is a courtyard, and the courtyard must be drawn too**."
## Why this is needed
Before this, "indoors/outdoors" **existed only in the model's intuition**: the base-map layer
(the `室内` layer of `world/atlas.py`) received a flat list of names --
`堂屋 / 后院 / 侧案 / 井 / 柜台 / 大门`. The program **did not distinguish them**:
  · a well (must be in the courtyard) and the main hall (indoors) **looked the same**, both drawn as a point;
  · whatever the model gave got drawn, and "that well next to the main hall" was **stopped by nothing**;
  · more fundamentally: **a well implies a courtyard**, and the courtyard was often not in that list at all.
So this module turns that common sense **into code** (pure functions, zero LLM, zero deps), used in
three places:
| Who | Which function | For what |
|---|---|---|
| Base-map generation (`world/atlas.py`) | `repair()` | One pass before drawing: add the missing courtyard, block dirty data |
| Minimap rendering (`image_gen/minimap.py`) | `space_of()` | On the indoor map, colour by "in the house / in the yard" and frame the whole building |
| Script/director/actor prompts | `hint_block()` / `route()` | State plainly "what this place looks like, how to walk from A to B" |
## One hard rule
> **Outdoor things must not be drawn indoors; a well implies a courtyard, and the courtyard must be
> drawn together with it.**
This is not a matter of style but of **verifiable** fact: a well needs open sky and rain (water
veins, the path of drawing water), the courtyard wall separates inside from outside (who can get in,
who is kept out), and those **decide how the scene plays** ("fetching water in the back yard and
hearing someone beyond the wall" —— without the wall that line does not hold).
"""
from __future__ import annotations

from dataclasses import dataclass

# ── 三类空间 + 两类东西 + 边界 ──────────────────────────────────────
# [EN] ── Three kinds of space + two kinds of things + boundary ──────────────────────────────────────
SPACE_IN = '室内'
SPACE_OUT = '室外'
SPACE_SEMI = '半室外'
SPACE_NONE = '—'

#: 定**空间**的词（名字里带这些字 → 它是一个"地方"，不是一件东西）。
#: ⚠ 顺序有讲究：长词排前面，`堂屋` 必须比 `屋` 先命中（不然"堂屋"会被当成普通屋）。
# [EN] : Words that define **space** (a name containing these is a "place", not a thing).
# [EN] : ⚠ Order matters: longer words first; `堂屋` must match before `屋` (otherwise the hall is taken
# [EN] : for a generic room).
ROOM_WORDS = (
    '堂屋', '正厅', '前厅', '后厅', '中堂', '客厅', '花厅', '暖阁', '书房', '卧房',
    '卧屋', '账房', '帐房', '柜房', '厢房', '东厢', '西厢', '耳房', '后厨', '厨房',
    '灶间', '柴房', '库房', '仓房', '马厩', '门房', '侧室', '内室', '佛堂', '禅房',
    '客房', '雅间', '包间', '偏房', '廊房', '房', '屋', '厅', '堂', '室',
    '阁', '斋', '轩',
)
#: ⚠ **`楼` `馆` `铺` `店` `肆` 故意不收在里面**（2026-10-12 实测踩到）：
#:   它们是**整座建筑/一整处地方**的名（`临河茶肆`、`临河茶肆`、`北门市集`），
#:   把它们当"屋里空间"的后果很实在 —— 一处地点会被误判成"今天在屋里演"，
#:   于是当天的图上**给一整座楼加了框**，而那天其实只是在镇上走。
#:   房间才是屋里空间；**建筑是框**，见 `is_building`。
# [EN] ⚠ **`楼` `馆` `铺` `店` `肆` are deliberately not included here** (measured 2026-10-12):
# [EN]   they are the names of **whole buildings / whole places** (`临河茶肆`, `临河茶肆`,
# [EN]   `北门市集`), and treating them as "indoor space" has a concrete consequence -- a place gets
# [EN]   misjudged as "today plays indoors", so the day's map **frames an entire building** while the day
# [EN]   was actually spent walking around town.
# [EN]   Rooms are indoor space; **a building is a frame**, see `is_building`.

#: 院/园/场一类**屋外**空间。
# [EN] : Courtyard/garden/yard-type **outdoor** space.
YARD_WORDS = (
    '后院', '前院', '中院', '跨院', '偏院', '外院', '内院', '庭院', '院落', '院子',
    '天井', '花园', '后园', '菜园', '果园', '场院', '打谷场', '晒场', '校场', '空场',
    '院', '庭', '园', '场', '坪',
)

#: 半开敞（有顶但不封闭）—— 廊下、檐下、月台、亭子。
# [EN] : Semi-open (roofed but not enclosed) -- under the veranda, under the eaves, the terrace, a
# [EN] : pavilion.
SEMI_WORDS = (
    '廊下', '檐下', '廊', '檐', '月台', '台阶', '石阶', '亭', '凉亭', '抱厦', '过道',
)

#: **必须在屋外**的东西（天然物 / 院子里的设施）。
#: ★ 用户点名的就是第一组：井。
# [EN] : Things that **must be outdoors** (natural objects / courtyard fixtures).
# [EN] : ★ The first group is exactly what the user named: wells.
OUTDOOR_OBJECT_WORDS = (
    '井', '泉', '池塘', '池子', '水缸', '树', '竹', '花坛', '花圃', '菜畦', '菜地',
    '假山', '石桌', '石凳', '石台', '影壁', '照壁', '石碑', '旗杆', '晾架', '牲口棚',
    '柴垛', '草垛', '水车', '磨盘',
)

#: **屋里**的陈设（有顶才放得住）。
# [EN] : Fixtures that are **indoors** (they need a roof).
INDOOR_FIXTURE_WORDS = (
    '柜台', '账台', '帐台', '案台', '条案', '神龛', '佛龛', '香案', '供桌', '书案',
    '屏风', '博古架', '货架', '木床', '炕', '灶台', '风箱', '酒坛', '酒旗', '茶灶',
    # ★ 2026-10-15：用户报「侧案 / 柜格」跑到墙外面 —— 这两样（及一众柜、案类陈设）
    #   没在词表里，于是 `space_of` 把它们判成 `—`（不是室内陈设），渲染层就不知道
    #   该把它们塞进哪间房、只能落在原位（往往就在墙外）。补进来后它们会被归为室内陈设，
    #   由 `plan_audit.solve()` 落进所属房间（见 `verify_plan_geometry` N4）。
    #   ⚠ **不收裸「柜」字**：`柜房` 是房间（`ROOM_WORDS` 里有），收了裸「柜」会把「柜房」
    #     误判成陈设；下面这些词都带「格 / 子 / 柜名」后缀，不会误中房间名。
    '侧案', '案子', '书柜', '衣柜', '酒柜', '碗柜', '药柜', '橱柜', '柜子', '矮柜',
    '立柜', '柜格', '多宝格', '条几', '八仙桌', '圆桌',
)

#: **边界**上的东西（门 / 墙 / 阶）—— 内外之分就靠它们。
# [EN] : Things on the **boundary** (gate / wall / steps) -- these are exactly what separates inside
# [EN] : from outside.
BOUNDARY_WORDS = (
    '大门', '后门', '角门', '侧门', '门楼', '门房', '院墙', '围墙', '照壁', '影壁',
    '门口', '门槛', '门', '墙',
)

#: 通路（连接两处，不占地方）。
# [EN] : Paths (connecting two points, not occupying space).
WAY_WORDS = ('路', '巷', '街', '桥', '渡', '埠', '径', '甬道', '夹道')

#: 判"这一处是不是**整座建筑**"的词（用它给整座楼画框）。
# [EN] : Words for judging "is this **the whole building**" (used to frame the entire building).
BUILDING_WORDS = ('楼', '宅', '府', '院', '庄', '店', '铺', '馆', '肆', '寺', '观',
                  '庙', '仓', '市')


@dataclass(frozen=True)
class Violation:
    """一条**空间常识**上的错误（可核对、可修）。"""

    code: str        # 机器用的稳定标识（判据按它断言）
    where: str       # 哪个名字
    why: str         # 为什么错
    fix: str         # 怎么修（人看得懂的那句）
    # [EN] `code` = stable machine id (criteria assert on it) / `where` = which name / `why` = why it is wrong / `fix` = how to fix it (human-readable)

    def line(self) -> str:
        """一行中文说明（日志/台账用）。"""
        return f'[{self.code}] {self.where}：{self.why} → {self.fix}'


def _hit(name: str, words: tuple[str, ...]) -> str:
    """名字里第一个命中的词（没有 → 空串）。

    ⚠ 用**子串**判，不用正则：中文标点不在 `\\u4e00-\\u9fff` 里，
      正则那套在本项目栽过（见 `world/atlas.py` 文件头的老账）。
    [EN] The first matching word in the name (empty string if none).
    [EN] ⚠ Substring matching, not regex: Chinese punctuation is not inside `\u4e00-\u9fff`, and the
    [EN] regex approach has burned this project before (see the old debt noted in `world/atlas.py`).
    """
    s = str(name or '')
    for w in words:
        if w and w in s:
            return w
    return ''


def is_outdoor_object(name: str) -> bool:
    """这是不是**必须在屋外**的东西（井、树、影壁…）。
        English:
    Is this something that **must be outdoors** (a well, a tree, a spirit wall...).
    """
    return bool(_hit(name, OUTDOOR_OBJECT_WORDS))


def is_indoor_fixture(name: str) -> bool:
    """这是不是**屋里**的陈设（柜台、条案、神龛…）。
        English:
    Is this an **indoor** fixture (a counter, a long table, a shrine...).
    """
    return bool(_hit(name, INDOOR_FIXTURE_WORDS))


def is_yard(name: str) -> bool:
    """这是不是一个**院子/园子/场**（屋外空间）。
        English:
    Is this a **courtyard/garden/yard** (outdoor space).
    """
    s = str(name or '')
    if is_outdoor_object(s):
        return False
    # ⚠ **墙不是院子**（2026-10-12 实测）：`院墙`/`围墙` 里都有"院"字，
    #   只按字面判会把它当成院子，于是"有院墙"会被读成"已经有院子了"，
    #   有井的那一处就**不会被补院子** —— 正好是用户要挡的那个错。
    # [EN] ⚠ **A wall is not a courtyard** (measured 2026-10-12): `院墙`/`围墙` both contain "院", and
    # [EN] judging literally would take them for courtyards, so "there is a courtyard wall" reads as
    # [EN] "there is already a courtyard" and the place with a well **would not get one added** --
    # [EN] exactly the error the user wants blocked.
    if s in BOUNDARY_WORDS or '墙' in s:
        return False
    return bool(_hit(s, YARD_WORDS))


def is_room(name: str) -> bool:
    """这是不是一个**屋里**的空间（堂屋、厢房、后厨…）。
        English:
    Is this an **indoor** space (main hall, side room, kitchen...).
    """
    s = str(name or '')
    if is_yard(s) or is_outdoor_object(s) or is_indoor_fixture(s):
        return False
    if _hit(s, SEMI_WORDS):
        return False
    return bool(_hit(s, ROOM_WORDS))


def is_boundary(name: str) -> bool:
    """这是不是**边界**上的东西（门 / 墙 / 阶）—— 内外之分靠它。
        English:
    Is this something on the **boundary** (gate / wall / steps) -- it is what separates inside from
    outside.
    """
    return bool(_hit(name, BOUNDARY_WORDS))


def is_way(name: str) -> bool:
    """这是不是一条**通路**（路/巷/桥/渡）。
        English:
    Is this a **path** (road/lane/bridge/ferry).
    """
    return bool(_hit(name, WAY_WORDS))


def is_building(name: str) -> bool:
    """这是不是**一整座建筑/一整处地方**（`临河茶肆`、`临河茶肆`）—— 它该被**框住**，
    而不是当成屋里的一间。

    ★ 这是"建筑"与"房间"的分界：**房间在框里，建筑就是那个框**。
    [EN] Is this **a whole building / a whole place** (`临河茶肆`, `临河茶肆`) -- it should be **framed**,
    [EN] not treated as a room in the house.
    [EN] ★ This is the line between "building" and "room": **rooms are inside the frame, the building is
    [EN] the frame**.
    """
    s = str(name or '').strip()
    if not s:
        return False
    if is_room(s) or is_yard(s) or is_outdoor_object(s) or is_indoor_fixture(s):
        return False
    # ⚠ 排除的是**纯边界名**（`大门`/`院墙`/`门口`），**不是"名字里带门字"**：
    #   `北门市集` 是个集市（一整处地方），它只是**开在北门**。
    # [EN] What is excluded is **a pure boundary name** (`大门`/`院墙`/`门口`), **not "a name containing
    # [EN] the word gate"**: `北门市集` is a market (a whole place) that merely **opens at the north
    # [EN] gate**.
    if s in BOUNDARY_WORDS or _hit(s, SEMI_WORDS) or is_way(s):
        return False
    return bool(_hit(s, BUILDING_WORDS))


def space_of(name: str) -> str:
    """这个名字属于**哪一类空间**（不是空间就返回 `SPACE_NONE`）。

    判序（**先具体、后笼统**，别调换）：
      ① 屋外器物（井/树）→ `室外`
      ② 院子/园子/场 → `室外`
      ③ 屋里陈设（柜台/条案）→ `室内`
      ④ 半开敞（廊/檐/亭）→ `半室外`
      ⑤ 房间（堂屋/厢房）→ `室内`
      ⑥ 其余 → `—`

        English:
    Which **kind of space** this name is (returns `SPACE_NONE` if it is not a space).
        Order (**specific before general**, do not reorder):
          ① outdoor object (well/tree) -> `室外`
          ② courtyard/garden/yard -> `室外`
          ③ indoor fixture (counter/long table) -> `室内`
          ④ semi-open (veranda/eaves/pavilion) -> `半室外`
          ⑤ room (main hall/side room) -> `室内`
          ⑥ otherwise -> `—`
    """
    s = str(name or '').strip()
    if not s:
        return SPACE_NONE
    if is_outdoor_object(s):
        return SPACE_OUT
    if is_yard(s):
        return SPACE_OUT
    if is_indoor_fixture(s):
        return SPACE_IN
    if _hit(s, SEMI_WORDS):
        return SPACE_SEMI
    if is_room(s):
        return SPACE_IN
    return SPACE_NONE


def role_of(name: str) -> str:
    """给提示词用的一句话标签：`室内空间` / `室外空间` / `半室外` / `室内陈设` /
    `室外器物` / `边界` / `通路` / `（未定）`。

        English:
    A one-line label for prompts: `indoor space` / `outdoor space` / `semi-outdoor` / `indoor fixture`
    / `outdoor object` / `boundary` / `path` / `(undecided)`.
    """
    s = str(name or '').strip()
    if not s:
        return '（未定）'
    if is_outdoor_object(s):
        return '室外器物'
    if is_yard(s):
        return '室外空间'
    if is_indoor_fixture(s):
        return '室内陈设'
    if _hit(s, SEMI_WORDS):
        return '半室外'
    if is_room(s):
        return '室内空间'
    if is_building(s):
        return '整座建筑'
    if is_boundary(s):
        return '边界'
    if is_way(s):
        return '通路'
    return '（未定）'


# ══════════════════════════════════════════════════════════════════
#  审计与修复
# [EN] Audit and repair
# ══════════════════════════════════════════════════════════════════
def audit(names: list[str], *, kind: str = SPACE_IN) -> list[Violation]:
    """这一份空间清单**违反了哪几条常识**（空列表 = 干净）。

    `kind` 是这份清单**画在哪一层**（`室内` / `局部` / `整体`）：

    | 码 | 什么情况 | 为什么错 |
    |---|---|---|
    | `井无院` | 有井（或别的屋外器物）却**没有院子** | 有井必有院；院子不画出来，井就成了"屋里的井" |
    | `器物入屋` | 名字本身就是"屋里 + 屋外物"（`堂屋·井`） | 井要见天，屋里打不出水 |
    | `房间出屋` | `局部`/`整体` 层里出现**屋里空间**（堂屋/厢房） | 那是院子外头的地图，屋里的事不该画上去 |
    | `重名` | 同一个名字出现两次 | 图上两个点、台账两条，后面全乱 |

        English:
    Which common-sense rules this space list **violates** (empty list = clean).
        `kind` is **which layer this list is drawn on** (`室内` / `局部` / `整体`):
        | Code | Situation | Why it is wrong |
        |---|---|---|
        | `井无院` | A well (or another outdoor object) but **no courtyard** | A well implies a courtyard; without drawing it, the well becomes "a well indoors" |
        | `器物入屋` | The name itself is "indoor + outdoor object" (`堂屋·井`) | A well needs open sky; no water can be drawn indoors |
        | `房间出屋` | An **indoor space** (main hall / side room) appears in the `局部`/`整体` layer | That is the map outside the courtyard; indoor matters do not belong on it |
        | `重名` | The same name appears twice | Two dots on the map, two ledger entries, everything after that is chaos |
    """
    out: list[Violation] = []
    clean = [str(x).strip() for x in (names or []) if str(x).strip()]

    # ① 重名
    # [EN] ① Duplicate names
    seen: set[str] = set()
    for n in clean:
        if n in seen:
            out.append(Violation('重名', n, '同一个名字出现了两次',
                                 '去掉重复的那一条'))
        seen.add(n)

    # ② 名字自相矛盾：屋里空间 + 屋外器物
    # [EN] ② Self-contradictory name: indoor space + outdoor object
    for n in clean:
        if is_outdoor_object(n) and is_room(n.replace(_hit(n, OUTDOOR_OBJECT_WORDS), '')):
            out.append(Violation('器物入屋', n,
                                 f'{_hit(n, OUTDOOR_OBJECT_WORDS)}是要见天的东西，'
                                 '不能在屋里',
                                 '把它挪到院子里（或补一个院子）'))

    yards = [n for n in clean if is_yard(n)]
    outdoor = [n for n in clean if is_outdoor_object(n)]

    # ③ 有井（屋外器物）却没有院子 —— 用户点名的那一条
    # [EN] ③ A well (outdoor object) but no courtyard -- the rule the user named
    if outdoor and not yards:
        out.append(Violation(
            '井无院', '、'.join(outdoor[:3]),
            f'{outdoor[0]}是屋外的东西，可这份清单里一个院子都没有',
            f'补一个院子（`院`），把{outdoor[0]}归到院子里'))

    # ④ 屋里空间跑到了屋外的图上
    # [EN] ④ Indoor space leaked onto the outdoor map
    if str(kind) in ('局部', '整体'):
        rooms = [n for n in clean if is_room(n)]
        if rooms:
            out.append(Violation(
                '房间出屋', '、'.join(rooms[:3]),
                '这是院外的地图，屋里的事不该画上来',
                '屋里那几间挪到「室内」那一层；这一层只留院外的'))
    return out


def repair(names: list[str], *, kind: str = SPACE_IN,
           building: str = '') -> tuple[list[str], list[str]]:
    """按常识**修**这份清单（返回 `(修好的清单, 做了什么)`）。

    修的三件事（都**只加不减**，不动作者写的地名）：

      1. **补院子**：有屋外器物（井/树）却没有院子 → 在它前面插一个院子。
         名字优先用 `{建筑}·院子`，没给建筑就叫 `院子`。
      2. **去重**：同名只留第一条。
      3. **挪层**：`局部`/`整体` 层里的屋里空间**原样留着**（调用方决定用不用），
         只记一条说明 —— 层归位是 `world/atlas.py` 的事，本模块不越权。

    ⚠ 顺序：**院子插在第一个屋外器物之前**，这样小地图分组时它们挨着，
      "院里的井"这件事在图上就看得见。

        English:
    **Repair** this list per common sense (returns `(fixed list, what was done)`).
        Three things (all **additive only** -- the author's place names are never removed):
          1. **Add the courtyard**: outdoor objects (well/tree) but no courtyard -> insert a courtyard
             before it. Prefer `{building}·院子`, or plain `院子` when no building was given.
          2. **Deduplicate**: the same name keeps only its first occurrence.
          3. **Move layers**: indoor spaces inside the `局部`/`整体` layer are **left as they are** (the
             caller decides); only a note is recorded -- layer reassignment belongs to `world/atlas.py`,
             and this module does not overstep.
        ⚠ Order: **the courtyard is inserted before the first outdoor object**, so the minimap groups
          them together and "the well in the courtyard" is visible on the map.
    """
    fixed: list[str] = []
    notes: list[str] = []
    b = str(building or '').strip()

    seen: set[str] = set()
    for n in (str(x).strip() for x in (names or [])):
        if not n:
            continue
        if n in seen:
            notes.append(f'去掉重名：{n}')
            continue
        # ★ 第一个屋外器物之前，先把院子补上
        # [EN] ★ Before the first outdoor object, add the courtyard first
        if is_outdoor_object(n) and not any(is_yard(x) for x in fixed):
            yard = f'{b}·院子' if b else '院子'
            if yard not in seen:
                fixed.append(yard)
                seen.add(yard)
                notes.append(f'补了「{yard}」：有{_hit(n, OUTDOOR_OBJECT_WORDS)}'
                             f'（{n}）就说明有院子')
        fixed.append(n)
        seen.add(n)

    for v in audit(fixed, kind=kind):
        if v.code == '房间出屋':
            notes.append(f'（记一笔，不越权改层）{v.line()}')
    return fixed, notes


def space_table(names: list[str], *, kind: str = SPACE_IN) -> list[dict]:
    """给提示词用的小表：`[{'名称', '属于', '层'}]`。

    `层` 只在 `室内` 这一层里才有意义：院子里 / 屋里 / 半开敞。
    [EN] A small table for prompts: `[{'name', 'role', 'layer'}]`.
    [EN] `layer` only matters on the `室内` layer: in the courtyard / in the house / semi-open.
    """
    out: list[dict] = []
    for n in (str(x).strip() for x in (names or [])):
        if not n:
            continue
        row = {'名称': n, '属于': role_of(n)}
        if str(kind) == SPACE_IN:
            sp = space_of(n)
            if sp == SPACE_OUT:
                row['层'] = '院里'
            elif sp == SPACE_IN:
                row['层'] = '屋里'
            elif sp == SPACE_SEMI:
                row['层'] = '半开敞'
        out.append(row)
    return out


def hint_block(names: list[str], *, kind: str = SPACE_IN, building: str = '',
               links: list | None = None) -> str:
    """把这一处的**空间事实**拼成一段给模型看的文字（空串 = 没什么可说）。

    这是"写小说/编剧的时候就把环境平面描述清楚"那条要求的**数据侧**：
    把已知的空间事实**逐条摊在它面前**，它就不必（也不许）自己猜"井在哪儿"。

        English:
    Assemble this place's **spatial facts** into a passage for the model (empty string = nothing to
    say).
        This is the **data side** of the requirement "describe the environmental floor plan clearly when
        writing the novel/script": lay out the known spatial facts **item by item in front of it**, so
        it neither has to (nor may) guess "where the well is".
    """
    rows = space_table(names, kind=kind)
    if not rows:
        return ''
    lines: list[str] = []
    if str(building or '').strip():
        lines.append(f'- {building}（整座）')
    for r in rows:
        tail = f"（{r.get('层')}）" if r.get('层') else ''
        lines.append(f"  · {r['名称']}：{r['属于']}{tail}")
    for lk in (links or [])[:16]:
        try:
            a, b = str(lk.get('a') or ''), str(lk.get('b') or '')
        except AttributeError:
            continue
        if a and b:
            lines.append(f"  · 走法：{a} → {b}")
    has_well = any(is_outdoor_object(x) for x in names)
    has_yard = any(is_yard(x) for x in names)
    if has_well and has_yard:
        lines.append('- **井在院子里，不在屋里**；院子在院墙以内，见天。')
    roof = [x for x in names if space_of(x) == SPACE_IN]
    if roof and has_yard:
        lines.append('- 屋里的（' + '、'.join(roof[:4]) + '）**有顶**；'
                     '院子里的（' + '、'.join(
                         [x for x in names if space_of(x) == SPACE_OUT][:4])
                     + '）**见天**。别把这两边的东西混着写。')
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════
#  走动：地图是人物移动的**依据**
# [EN] Walking: the map is the **basis** for character movement
# ══════════════════════════════════════════════════════════════════
def adjacency(names: list[str], links: list | None) -> dict[str, list[str]]:
    """由通路表 + 空间常识算出的**邻接表**（双向）。

    两条来源，合起来用：

    1. **明写的通路**（`links`，如「大堂 ↔ 后院」）—— 地图上真的画了线；
    2. **同属一个院子的默认连通**：院里的东西之间走得通（同一个院子是开放空间），
       屋里的房间之间**默认走不通**（隔着墙，得经过门/廊）—— 这是常识，
       不是设定，所以不需要作者一条条写。

    ⚠ 第 2 条只**加边**，不改作者写的边；作者写"这两间走不通"时（`links` 里没有）
      它仍然会连上 —— 所以真要断开，得在通路表里明确写"隔墙"那类说明
      （本函数不认识"隔墙"，见 `route()` 的第三条返回）。

        English:
    The **adjacency table** (bidirectional) computed from the path table + spatial common sense.
        Two sources, used together:
        1. **Explicit paths** (`links`, e.g. "main hall <-> back yard") -- lines actually drawn on the map;
        2. **Default connectivity within one courtyard**: things in the same courtyard are reachable
           (a courtyard is open space), while rooms **are not** mutually reachable by default (a wall
           is in between; you must pass a door/veranda) -- this is common sense, not a setting, so the
           author need not write it.
        ⚠ Source 2 only **adds** edges; it never changes the author's. If the author intends "these two
          rooms are not connected" (absent from `links`), it will still connect them -- so to really
          break it, write an explicit note in the path table (this function does not understand "a wall
          in between"; see the third return of `route()`).
    """
    clean = [str(x).strip() for x in (names or []) if str(x).strip()]
    adj: dict[str, list[str]] = {n: [] for n in clean}

    def _link(a: str, b: str) -> None:
        if a not in adj or b not in adj or a == b:
            return
        if b not in adj[a]:
            adj[a].append(b)
        if a not in adj[b]:
            adj[b].append(a)

    for lk in (links or []):
        try:
            a, b = str(lk.get('a') or '').strip(), str(lk.get('b') or '').strip()
        except AttributeError:
            continue
        _link(a, b)

    yards = [n for n in clean if is_yard(n)]
    edges = [n for n in clean if is_boundary(n)]
    if yards:
        # 有院子：**一切都通到院子**（院子是开放空间，屋门开向它）。
        # ★ 这一条同时给出了"屋里两间怎么走"：**经过院子**，不是穿墙。
        # [EN] With a courtyard: **everything connects to the courtyard** (the courtyard is open space;
        # [EN] doors open onto it).
        # [EN] ★ This also answers "how do you get from one room to the other": **through the courtyard**,
        # [EN] not through a wall.
        for n in clean:
            if is_outdoor_object(n) or is_boundary(n) or is_room(n) \
                    or is_indoor_fixture(n) or _hit(n, SEMI_WORDS):
                _link(n, yards[0])
    elif edges:
        # 没院子：屋外器物与屋里空间都只和**边界（门口）**连着 —— 门外就是外面。
        # [EN] No courtyard: outdoor objects and indoor spaces connect only to the **boundary (the gate)**
        # [EN] -- beyond the gate is outside.
        for n in clean:
            if is_outdoor_object(n) or is_room(n) or is_indoor_fixture(n):
                _link(n, edges[0])
    return adj


def route(names: list[str], links: list | None, a: str, b: str) -> list[str]:
    """从 `a` 走到 `b` 的**一条路**（含首尾；走不通/不认识 → 空列表）。

    地图之所以能当"人物移动的依据"，靠的就是这个：**走法是有依据的**，
    不是"他从屋里出来就到了街上"。导演派活、演员动作都该引它。

        English:
    **One path** from `a` to `b` (inclusive; empty list if unreachable or unknown).
        This is exactly why the map can serve as "the basis for character movement": **the way to walk
        is grounded**, not "he came out of the house and was on the street". The director assigning work
        and the actors acting should both cite it.
    """
    s, t = str(a or '').strip(), str(b or '').strip()
    adj = adjacency(names, links)
    if s not in adj or t not in adj or s == t:
        return [] if s != t else [s]
    prev: dict[str, str] = {s: ''}
    q = [s]
    while q:
        cur = q.pop(0)
        if cur == t:
            break
        for nx in adj.get(cur, []):
            if nx not in prev:
                prev[nx] = cur
                q.append(nx)
    if t not in prev:
        return []
    out: list[str] = []
    cur = t
    while cur:
        out.append(cur)
        cur = prev[cur]
    return list(reversed(out))


def movement_line(names: list[str], links: list | None, a: str, b: str) -> str:
    """`从 X 到 Y 怎么走` 的一句话（走不通就说清"必须经过院子/门外"）。

        English:
    One line for "how to walk from X to Y" (when unreachable, say plainly "you must pass the courtyard
    / the gate").
    """
    a, b = str(a or '').strip(), str(b or '').strip()
    if not a or not b:
        return ''
    p = route(names, links, a, b)
    if p:
        return f'从{a}到{b}：' + ' → '.join(p) if len(p) > 1 else f'{a}就是{b}'
    yards = [n for n in names if is_yard(n)]
    via = f'（要经过{yards[0]}）' if yards else ''
    return f'从{a}到{b}：地图上这两处没连着{via} —— 别让人一步跨过去'
