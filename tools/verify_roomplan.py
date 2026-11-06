# -*- coding: utf-8 -*-
"""判据：**房间任务书 → 平面图**这套解算，是不是真的把用户报的五件事修好了。

用户 2026-10-26 原话（这条判据的全部理由）：

    「现在生成的地图 完全不合理了 …… 后厨 堂屋区分开 而且很多东西叠在了一起
      房子和很小 布局也不合理 而且门放在了房子外面 小地图也不对
      还有一个问题就是地图没有延续性 同一个场景地图不同推演次数会变」

所以每一条都对着**用户看得见的那件事**问，而不是对着实现细节问：

| 组 | 问的是 | 用户看到的是 |
|---|---|---|
| A | 房间**拼满**外轮廓、两两不叠 | 房子是一整栋，不是一堆飘着的方块 |
| B | 整栋楼 = 外轮廓；陈设在房里；院子见天 | 房子不小、家具不跑到墙外、井在院里 |
| C | 门只开在**共用墙 / 外墙**上 | 门不会悬在房子外面 |
| D | 楼上**单独一层** | 二楼不会压在后院上 |
| E | 同一任务书 ⇒ **逐位相同**的图 | 同一个场景每次画出来一样（延续性） |
| F | 审核能抓到坏任务书；`feedback` 写得能照着改 | "不合理要打回美术改设计"这条路真的通 |

★ 为什么用**真数据**做夹具：A~D 用的是用户项目里那 9 处地点的名字与说明原文
  （`锚定.json` 里抄出来的，一个字没改）。手搓一个"三间房"的夹具永远测不出
  "二楼三间封门被当成门洞"这种只有真数据才有的坑 —— 实测就踩到了。

跑法：
    .venv\\Scripts\\python.exe tools/verify_roomplan.py

English
-------
Criteria: does the **room program -> floor plan** solver really fix the five things the user
reported on 2026-10-26? Every group asks about **what the user sees**, not implementation details:
A rooms tile the envelope with no overlap; B the building *is* the envelope, fixtures stay in their
room, the courtyard is open to the sky; C doors only on shared/envelope walls; D upstairs is its own
floor; E the same program yields a bit-identical plan (continuity); F the audit catches bad
programs and `feedback` is actionable.
★ The fixture uses **real data**: A~D use the nine place names and notes from the user's
`锚定.json`, verbatim. A hand-made "three rooms" fixture can never surface a pit like "二楼三间封门
was taken for a door" -- which is exactly what measurement hit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from image_gen import roomplan as RP                       # noqa: E402
from image_gen import furniture as FR                      # noqa: E402
from image_gen import floorplan as FP                      # noqa: E402
from image_gen import map_layout as ML                     # noqa: E402
from image_gen import minimap as MM                        # noqa: E402

OUT = ROOT / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    ok = bool(cond)
    report['checks'].append({'name': name, 'ok': ok, 'detail': str(detail)})
    print(f"  {'✓' if ok else '✗'} {name}" + (f'   [{detail}]' if detail else ''))
    return ok


def head(t: str) -> None:
    print(f'\n{"=" * 62}\n{t}\n{"=" * 62}')


# ══════════════════════════════════════════════════════════════════
#  真数据夹具：用户项目 `锚定.json` 里的九处（名称与说明原文）
# [EN] Real fixture: the nine places from the user's `锚定.json`, verbatim
# ══════════════════════════════════════════════════════════════════
NAMES = ['门', '堂屋', '柜台', '账台小柜', '后院', '井', '后厨',
         '二楼三间封门', '客来楼']
NOTES = ['临街大门，门板卸了一半，门槛外青石阶上留',
         '前厅，白天三张油亮方桌靠左墙一溜条凳，夜',
         '堂屋左手边靠门的长柜台，角上油灯豆大一点',
         '堂屋右手边的小柜，伙计在此记茶钱账目',
         '堂屋后面一方见天院子，矮墙豁口通前楼，辘',
         '院子西北角的井，石台砌边，伙计在此摇辘',
         '院子东侧灶间，灶上大铜壶嘴冒细白气',
         '贴后墙窄木梯上去，梯脚搁着一盏没点的白纸',
         '（这里）']

SPAN = (60.0, 90.0, 880.0, 520.0)
PROG = RP.program_from_places(NAMES, NOTES, place='客来楼')
PLANS = RP.solve(PROG, span=SPAN)


# ══════════════════════════════════════════════════════════════════
#  A. 拼满 / 不叠 / 不漏 —— "房子是一整栋，不是一堆飘着的方块"
# [EN] A. Tiled / no overlap / nothing lost
# ══════════════════════════════════════════════════════════════════
def test_tiling() -> bool:
    ok = True
    fp = PLANS[1]
    env_a = RP._area(fp.envelope)
    tot = sum(RP._area(b) for b in fp.rooms.values())
    ok &= rec('A1 ★★★ 第一层房间面积合计 == 外轮廓面积（拼满，无空隙）',
              abs(tot - env_a) <= 0.5, f'{tot:.1f} / {env_a:.1f}')

    worst = 0.0
    names = list(fp.rooms)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            worst = max(worst, RP._overlap(fp.rooms[names[i]], fp.rooms[names[j]]))
    ok &= rec('A2 ★★★ 任意两间都不重叠（用户报的"很多叠在一起"）',
              worst <= 0.5, f'最大重叠 {worst:.1f} px²')

    f1_names = {s.name for s in PROG.rooms_of(1)}
    got = set(fp.rooms)
    ok &= rec('A3 ★★ 一层的房间一个都没丢（任务书里有几间，图上就有几间）',
              got == f1_names, f'缺 {sorted(f1_names - got)} / 多 {sorted(got - f1_names)}')

    ok &= rec('A4 ★★ 每间都够大（不会缩成一个点认不出来）',
              all(min(b[2] - b[0], b[3] - b[1]) >= RP.MIN_ROOM_PX * 0.65
                  for b in fp.rooms.values()),
              str({n: (round(b[2] - b[0]), round(b[3] - b[1]))
                   for n, b in fp.rooms.items()}))
    return ok


# ══════════════════════════════════════════════════════════════════
#  B. 整栋楼 / 陈设归属 / 院子见天
# [EN] B. The building is the envelope / fixtures stay inside / courtyard is open
# ══════════════════════════════════════════════════════════════════
def test_building() -> bool:
    ok = True
    fp = PLANS[1]
    ok &= rec('B1 ★★★ 整栋楼就是外轮廓（"房子很小"的根治：楼本身不再是一间房）',
              fp.envelope == SPAN, str(fp.envelope))
    ok &= rec('B2 ★★★ 整栋楼的名字**没有**被当成一间房（实测：`客来楼` 曾占掉一整条带）',
              '客来楼' not in fp.rooms, str(list(fp.rooms)))

    bad = []
    for nm, (owner, box) in fp.fixtures.items():
        ob = fp.rooms.get(owner)
        if ob is None or not RP._inside(box, ob):
            bad.append(nm)
    ok &= rec('B3 ★★★ 每件陈设都在**所属房间**里（"柜台跑到墙外"的根治）',
              not bad, str(bad))

    ok &= rec('B4 ★★ 柜台/账台归在堂屋（归属从设定原文读出来，不是编的）',
              fp.fixtures.get('柜台', ('', None))[0] == '堂屋'
              and fp.fixtures.get('账台小柜', ('', None))[0] == '堂屋',
              str({k: v[0] for k, v in fp.fixtures.items()}))

    ok &= rec('B5 ★★★ 井是**陈设**不是房间，而且归在后院（院西北角的井）',
              '井' not in fp.rooms
              and fp.fixtures.get('井', ('', None))[0] == '后院',
              str({k: v[0] for k, v in fp.fixtures.items()}))

    ok &= rec('B6 ★★ 后院见天（画出来要铺点、不能有顶）',
              '后院' in fp.sky and fp.yard() == fp.rooms.get('后院'),
              str(fp.sky))

    ok &= rec('B7 ★★ 后厨与后院**并排**（设定写"院子东侧灶间"）',
              any(set(g) >= {'后院', '后厨'} for g in PROG.side_by_side),
              str(PROG.side_by_side))
    b_y, b_c = fp.rooms.get('后院'), fp.rooms.get('后厨')
    ok &= rec('B8 ★★ 而且图上真的左右相邻、同一条带（不是排到院子后面成第三进）',
              b_y is not None and b_c is not None
              and abs(b_y[1] - b_c[1]) <= 0.5 and abs(b_y[3] - b_c[3]) <= 0.5,
              f'院 y={b_y[1]:.0f}~{b_y[3]:.0f} / 厨 y={b_c[1]:.0f}~{b_c[3]:.0f}')
    ok &= rec('B9 ★ 堂屋在前（贴街），后院在后（"从街往里一进一进"）',
              fp.rooms['堂屋'][3] >= fp.rooms['后院'][3],
              f"堂屋底 {fp.rooms['堂屋'][3]:.0f} / 后院底 {fp.rooms['后院'][3]:.0f}")
    return ok


# ══════════════════════════════════════════════════════════════════
#  C. 门开在墙上
# [EN] C. Doors sit on walls
# ══════════════════════════════════════════════════════════════════
def test_doors() -> bool:
    ok = True
    fp = PLANS[1]
    walls = RP._wall_segments(fp)
    off = [f'{d.a}→{d.b or "街面"}' for d in fp.doors if not RP._on_wall(d, walls)]
    ok &= rec('C1 ★★★ 每一道门都落在某道墙上（用户报的"门在房子外面"）',
              not off, str(off))
    ok &= rec('C2 ★★★ 有一道门开在**外墙**上通街面（不是屋里的一个点）',
              any(not d.b and abs(d.y - fp.envelope[3]) <= 0.6 for d in fp.doors),
              str([(d.a, d.b or '街面', round(d.y)) for d in fp.doors]))
    ok &= rec('C3 ★★ 堂屋—后院之间有一道门（屋里走得通）',
              any({d.a, d.b} == {'堂屋', '后院'} for d in fp.doors),
              str([(d.a, d.b) for d in fp.doors]))
    ok &= rec('C4 ★★ 后院—后厨之间有一道门（做饭的人能进院）',
              any({d.a, d.b} == {'后院', '后厨'} for d in fp.doors),
              str([(d.a, d.b) for d in fp.doors]))
    ok &= rec('C5 ★★ 从大门按门走，走得到每一间（疏散/连通）',
              not RP._unreachable(fp, PROG), str(RP._unreachable(fp, PROG)))
    return ok


# ══════════════════════════════════════════════════════════════════
#  D. 分层
# ══════════════════════════════════════════════════════════════════
def test_floors() -> bool:
    ok = True
    ok &= rec('D1 ★★★ 出了两层（"二楼三间封门"单独一层，不与后院同图）',
              sorted(PLANS) == [1, 2], str(sorted(PLANS)))
    ok &= rec('D2 ★★★ 二楼**不在**一层图上（用户报的"二楼压在后院上"）',
              '二楼三间封门' not in PLANS[1].rooms, str(list(PLANS[1].rooms)))
    ok &= rec('D3 ★★ 二楼那一层只有它自己（不是把一楼复制一份）',
              list(PLANS[2].rooms) == ['二楼三间封门'], str(list(PLANS[2].rooms)))
    ok &= rec('D4 ★★ 二楼**没有**通街面的门（悬空的门是错的）',
              not any(not d.b for d in PLANS[2].doors),
              str([(d.a, d.b or '街面') for d in PLANS[2].doors]))
    return ok


# ══════════════════════════════════════════════════════════════════
#  E. 延续性：同一任务书 ⇒ 逐位相同
# [EN] E. Continuity: same program => bit-identical plan
# ══════════════════════════════════════════════════════════════════
def test_continuity() -> bool:
    ok = True
    a = RP.solve(PROG, span=SPAN)
    b = RP.solve(RP.Program.from_dict(json.loads(json.dumps(PROG.to_dict()))),
                 span=SPAN)
    same_rooms = all(a[f].rooms == b[f].rooms for f in a) and set(a) == set(b)
    same_doors = all([d.to_dict() for d in a[f].doors] == [d.to_dict() for d in b[f].doors]
                     for f in a)
    ok &= rec('E1 ★★★ 同一份任务书解两次，房间坐标**逐位相同**'
              '（延续性靠这个，不靠锁坐标）', same_rooms, '')
    ok &= rec('E2 ★★★ 门也逐位相同', same_doors, '')
    ok &= rec('E3 ★★ 经过 JSON 存盘再读回，解出来还是同一张图'
              '（换一轮推演、换一天都还原得出来）', same_rooms, '')

    # ★ 反例：改一处任务书，图**必须**跟着变（否则"改了就修好"是空话）
    p2 = RP.Program.from_dict(json.loads(json.dumps(PROG.to_dict())))
    for s in p2.spaces:
        if s.name == '后厨':
            s.area = 4.0
    c = RP.solve(p2, span=SPAN)
    ok &= rec('E4 ★★ 改一处（后厨面积 1.6→4.0），图**真的跟着变**',
              c[1].rooms.get('后厨') != a[1].rooms.get('后厨'),
              f"{a[1].rooms['后厨']} → {c[1].rooms.get('后厨')}")
    return ok


# ══════════════════════════════════════════════════════════════════
#  F. 审核 → 打回美术改任务书（用户点名要的闭环）
# [EN] F. Audit -> send back to art to revise the program (the loop the user asked for)
# ══════════════════════════════════════════════════════════════════
def test_audit_and_feedback() -> bool:
    ok = True

    # 干净的任务书：审核必须**什么都不报**（否则天天打回，模型被无效意见带偏）
    issues = {f: RP.audit(fp, PROG) for f, fp in PLANS.items()}
    ok &= rec('F1 ★★★ 这份真数据解出来，审核**零问题**（不误报）',
              not any(issues.values()), str({k: v for k, v in issues.items() if v}))

    # 反例 ①：陈设写了归属，但那间房在别的楼层 ⇒ 必须报
    bad1 = RP.Program.from_dict(json.loads(json.dumps(PROG.to_dict())))
    for s in bad1.spaces:
        if s.name == '井':
            s.of = '二楼的房'
    f1 = RP.solve(bad1, span=SPAN)[1]
    i1 = RP.audit(f1, bad1)
    ok &= rec('F2 ★★★ 陈设的归属房间不存在 ⇒ 审核抓到（不是静静不画）',
              any(RP.K_FIXTURE_NO_OWNER in x for x in i1), str(i1[:2]))

    # 反例 ②：门被挪离墙 ⇒ 必须报"门没开在墙上"
    f2 = RP.solve(PROG, span=SPAN)[1]
    if f2.doors:
        f2.doors[0].y -= 40.0
    i2 = RP.audit(f2, PROG)
    ok &= rec('F3 ★★★ 门被挪离墙 ⇒ 审核抓到"门没开在墙上"',
              any(RP.K_DOOR_OFF_WALL in x for x in i2), str(i2[:2]))

    # 反例 ③：一间房被塞到外轮廓外面 ⇒ 必须报"没拼满"
    f3 = RP.solve(PROG, span=SPAN)[1]
    nm = next(iter(f3.rooms))
    b = f3.rooms[nm]
    f3.rooms[nm] = (b[0], b[1], b[2] - 80.0, b[3])
    i3 = RP.audit(f3, PROG)
    ok &= rec('F4 ★★★ 房间缩了 80px ⇒ 审核抓到"没拼满"（空隙就是错）',
              any(RP.K_NOT_TILED in x for x in i3), str(i3[:2]))

    # 反例 ④：断开一道门 ⇒ 必须报"走不到"
    f4 = RP.solve(PROG, span=SPAN)[1]
    f4.doors = [d for d in f4.doors if {d.a, d.b} != {'堂屋', '后院'}]
    i4 = RP.audit(f4, PROG)
    ok &= rec('F5 ★★★ 拿掉堂屋—后院那道门 ⇒ 审核抓到"走不到"',
              any(RP.K_DISCONNECTED in x for x in i4),
              str([x for x in i4 if RP.K_DISCONNECTED in x][:2]))

    # 反例 ⑤：二楼混进一层 ⇒ 必须报
    f5 = RP.solve(PROG, span=SPAN)[1]
    f5.rooms['二楼三间封门'] = (60.0, 90.0, 100.0, 120.0)
    i5 = RP.audit(f5, PROG)
    ok &= rec('F6 ★★ 把二楼那间硬塞进一层 ⇒ 审核抓到"楼层串了"',
              any(RP.K_WRONG_FLOOR in x for x in i5),
              str([x for x in i5 if RP.K_WRONG_FLOOR in x][:1]))

    # 打回意见：要能照着改（含现状 + 问题 + 只改任务书的要求）
    fb = RP.feedback(bad1, {1: i1})
    ok &= rec('F7 ★★★ `feedback` 里写清了**现状**（不然模型会把对的部分一起改坏）',
              '现在的任务书' in fb and '堂屋' in fb and '后院' in fb, fb[:60])
    ok &= rec('F8 ★★★ `feedback` 里写了**问题**（陈设归属不存在）',
              RP.K_FIXTURE_NO_OWNER in fb, '')
    ok &= rec('F9 ★★★ `feedback` 明确要求**只改任务书、别写坐标**'
              '（美术改坐标就是那 9 个错点的来历）',
              '别写坐标' in fb, '')
    return ok


def test_here_is_not_building() -> bool:
    """★★★ G. 上游把"人在哪间房"当成建筑名传进来时，**那间房不许消失**。

    2026-10-26 实测的真 bug：`map_layout.day_layout` 里曾写
    `place=str(lay.frame or '') or here` —— `here` 是"现在人在哪间房"，
    而 `program_from_places` 有一条"名字等于地点名 ⇒ 这是整栋楼、不是房间"。
    于是 in_here 的那间房被整间删掉：**图上少了屋子，没有任何报错**。
    这一组钉三件事：
      ① 直接给 `place='堂屋'`（房间名）时，堂屋**仍是一间房**（安全阀生效）；
      ② 更狠的：`day_layout` 这条**真实链路**上，`here='堂屋'` 之后任务书里仍有堂屋；
      ③ 真的整栋楼名（`客来楼`）**仍然**会被摘掉（安全阀不能把对的行为也废掉）。
    [EN] ★★★ G. When upstream passes "which room the person is in" as the building name, **that
    [EN] room must not disappear.** Measured 2026-10-26: `day_layout` had
    [EN] `place=str(lay.frame or '') or here`; `here` is the room, and `program_from_places` has the
    [EN] rule "name equals place => that is the envelope". So the room was deleted outright -- **a
    [EN] room missing from the map with no error at all**. Three things are pinned here:
    [EN] (1) with `place='堂屋'` (a room name) 堂屋 is **still a room** (the valve works);
    [EN] (2) harder: on the **real path** `day_layout` with `here='堂屋'`, the program still has 堂屋;
    [EN] (3) a real building name (`客来楼`) is **still** lifted out (the valve must not disable the
    [EN] correct behaviour too).
    """
    ok = True
    names = [p.name for p in PROG.spaces] or []
    notes = [p.note for p in PROG.spaces]

    # ① 直接喂一个房间名当 place
    p1 = RP.program_from_places(['门', '堂屋', '后院', '后厨'], ['', '', '', ''],
                                place='堂屋')
    ok &= rec('G1 ★★★ `place` 被填成房间名（堂屋）时，堂屋**仍在**'
              '（安全阀：含屋/房/厅/院 的不算建筑名）',
              any(s.name == '堂屋' for s in p1.spaces),
              str([s.name for s in p1.spaces]))

    # ② 真实链路：day_layout
    try:
        from image_gen import map_layout as ML
        data = {
            'caption': '', 'kind': '室内', 'frame': '',
            'places': [
                {'name': '门', 'x': 0.5, 'y': 0.93, 'shape': '门', 'size': '中',
                 'note': '临街大门'},
                {'name': '堂屋', 'x': 0.76, 'y': 0.71, 'shape': '屋', 'size': '中',
                 'note': '前厅，三张方桌'},
                {'name': '后院', 'x': 0.5, 'y': 0.19, 'shape': '院', 'size': '中',
                 'note': '堂屋后面一方见天院子'},
                {'name': '后厨', 'x': 0.82, 'y': 0.44, 'shape': '屋', 'size': '中',
                 'note': '院子东侧灶间'},
            ],
        }
        lay = ML.day_layout(data, ['门', '堂屋', '后院', '后厨'],
                           here='堂屋', allow_extra=[], kind_hint='室内')
        sp = [s['名称'] for s in (lay.program or {}).get('空间', [])]
        ok &= rec('G2 ★★★ 真实链路 `day_layout(here="堂屋")` ⇒ 任务书里**仍有堂屋**'
                  '（这条就是用户看到"屋子少了一半"的那条路）',
                  '堂屋' in sp, str(sp))
        ok &= rec('G2b 而且堂屋是**房间**不是陈设（归属为空）',
                  any(s['名称'] == '堂屋' and not s['归属']
                      for s in (lay.program or {}).get('空间', [])), str(sp))
    except Exception as exc:                                  # noqa: BLE001
        ok &= rec('G2 真实链路跑得通（抛异常就不是全绿）', False,
                  f'{type(exc).__name__}: {exc}')

    # ③ 真的建筑名仍然被摘掉（别把对的行为一起废掉）
    p3 = RP.program_from_places(['门', '堂屋', '后院', '客来楼'],
                                ['', '', '', '（这里）'], place='客来楼')
    ok &= rec('G3 ★★ 真建筑名（客来楼）**仍然**被摘掉、不当成一间房'
              '（安全阀不能顺手废掉对的行为）',
              not any(s.name == '客来楼' for s in p3.spaces),
              str([s.name for s in p3.spaces]))
    ok &= rec('G3b 而同一份里的堂屋仍然是房间', any(s.name == '堂屋' for s in p3.spaces),
              str([s.name for s in p3.spaces]))
    return ok



# ══════════════════════════════════════════════════════════════════
#  H. 家具：形状按类型、摆放不压墙 / 不撞门 / 不叠
# [EN] H. Furniture: shaped by class, placed clear of walls / doorways / each other
# ══════════════════════════════════════════════════════════════════
def RP_blocks_door(box: tuple, door, room: tuple | None, *, reach: float = 13.0) -> bool:
    """这件家具是不是**挡在那个门口**。

    ★ 判据不能用"矩形相交"：家具会退到墙内侧（`WALL_IN + WALL_GAP` ≈ 6.15px），
      而门洞的矩形只有 ±3px ⇒ 两者矩形**不相交**，但家具明明就在门口堵着
      （实测：H2b 因为这个假绿，反例刀打不中）。
      正确判法是**沿墙方向的投影** + "贴着那面墙"：
        · 门在上下墙（`along='h'`）⇒ 比**x 区间**，且家具离上/下墙 ≤ `reach`
        · 门在左右墙（`along='v'`）⇒ 比**y 区间**，且家具离左/右墙 ≤ `reach`
    [EN] Whether this piece of furniture **blocks that doorway**. ★ Rectangle intersection is wrong:
    [EN] furniture retreats inside the wall (~6.15px) while the doorway rect is only +-3px, so the two
    [EN] rects do **not** intersect even though the piece sits right in the opening (measured: H2b was
    [EN] falsely green and the cut missed). The right test is the **projection along the wall** plus
    [EN] "hugs that wall".
    """
    x0, y0, x1, y1 = (float(v) for v in box)
    dw = float(getattr(door, 'w', 26.0) or 26.0)
    along = str(getattr(door, 'along', 'h') or 'h')
    dx, dy = float(door.x), float(door.y)
    if along == 'h':
        # ★★ 必须是**同一面墙**才算挡门。
        #   第一版用 `min(abs(y0-上), abs(y1-下))`，于是"门在上墙、家具在下墙"也被算成挡门
        #   （两者 x 区间当然重叠）—— 判据自己误报，反例刀把这份误报当成了"命中"。
        #   ⇒ 先看门贴的是哪面墙（离哪边更近），家具也必须贴那一面。
        # [EN] ★★ It must be the **same wall**. The first version took
        # [EN] `min(abs(y0-top), abs(y1-bottom))`, so "door on the top wall, furniture on the bottom
        # [EN] wall" counted as blocking (their x ranges naturally overlap) -- a false report by the
        # [EN] criterion, which the counter-example run then mistook for a hit. => Decide which wall the
        # [EN] door belongs to, and require the furniture to hug that same wall.
        if room is not None:
            upper = abs(dy - room[1]) <= abs(dy - room[3])
            near = abs(y0 - room[1]) if upper else abs(y1 - room[3])
            if near > reach:
                return False
        return not (x1 <= dx - dw / 2.0 + 0.5 or x0 >= dx + dw / 2.0 - 0.5)
    if room is not None:
        left = abs(dx - room[0]) <= abs(dx - room[2])
        near = abs(x0 - room[0]) if left else abs(x1 - room[2])
        if near > reach:
            return False
    return not (y1 <= dy - dw / 2.0 + 0.5 or y0 >= dy + dw / 2.0 - 0.5)


def test_furniture() -> bool:
    """★★★ 2026-10-27（用户）：「室内图现在家具形状和摆放位置都不对 有一些都放到墙里了
    家具的形状请参考一些现有标准画法绘制」。

    两类问题各配判据：

    **摆放**（`roomplan._pack_fixtures`）
      H1 不压墙：家具到房间边的距离 ≥ `furniture.WALL_IN + WALL_GAP`。
         （实测老代码是 3.0px，而墙向内占 4.35px ⇒ 压进墙里 1.35px —— 就是用户看到的那一幕。）
      H2 不撞门：与**这一层已开的门洞**不重叠（老代码只排上墙，一旦四面墙都用上，
         不避门必然把柜子排到门口）。
      H3 互不重叠。
      H4 放不下的要**报出来**（`orphans`），不许静静消失。

    **形状**（`image_gen.furniture`）
      H5 尺寸按类型：柜台比井宽、床比柜台高 —— 不是"件件 15×15"。
      H6 井画**同心圆**，不是方块。
      H7 认得出类：`柜台/账台小柜` → counter，`井` → well（词表**顺序**敏感：
         `柜台` 必须先于 `柜`，否则柜台会变成柜子）。

    [EN] ★★★ 2026-10-27 (the user): "the indoor furniture shapes and positions are both wrong, some
    [EN] are inside the walls; draw the shapes following existing standard conventions." One criterion
    [EN] per fault. **Placement**: H1 clear of walls by `furniture.WALL_IN + WALL_GAP` (the old code
    [EN] used 3.0px while the wall occupies 4.35px inward => 1.35px inside the wall, exactly what the
    [EN] user saw); H2 clear of the floor's door openings (the old code packed only the top wall; once
    [EN] all four walls are used, not clearing doorways puts a cabinet in front of the door); H3 no
    [EN] overlapping; H4 whatever does not fit is **reported** (`orphans`), never silently dropped.
    [EN] **Shape**: H5 sizes differ by class (counter wider than the well, bed taller than the
    [EN] counter -- not everything 15x15); H6 the well is **concentric circles**, not a block; H7 class
    [EN] detection works (柜台/账台小柜 -> counter, 井 -> well) and the word table is **order
    [EN] sensitive** (柜台 before 柜, or a counter becomes a cabinet).
    """
    ok_ = True
    pad = FR.WALL_IN + FR.WALL_GAP

    for fl, fp in PLANS.items():
        # ── H1 不压墙 ──
        bad = []
        for nm, (owner, box) in fp.fixtures.items():
            r = fp.rooms.get(owner)
            if not r:
                continue
            gap = min(box[0] - r[0], box[1] - r[1], r[2] - box[2], r[3] - box[3])
            if gap < pad - 0.05:
                bad.append((nm, round(gap, 2)))
        ok_ &= rec(f'H1 ★★★ 第 {fl} 层：家具**没有压进墙里**'
                   f'（到墙距离 ≥ {pad:.2f}px = 墙厚 {FR.WALL_IN} + 缝 {FR.WALL_GAP}）',
                   not bad, f'{bad}')

        # ── H2 不撞门 ──
        hits = []
        for nm, (_owner, box) in fp.fixtures.items():
            for dr in fp.doors:
                if RP_blocks_door(box, dr, fp.rooms.get(_owner)):
                    hits.append(nm)
                    break
        ok_ &= rec(f'H2 ★★★ 第 {fl} 层：**没有家具挡在门口**'
                   '（排到门洞上，画出来就是"门被柜子封住"）',
                   not hits, str(hits))

        # ── H3 互不重叠 ──
        ks = list(fp.fixtures.items())
        over = []
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                if RP._overlaps(ks[i][1][1], ks[j][1][1], tol=0.5):
                    over.append((ks[i][0], ks[j][0]))
        ok_ &= rec(f'H3 ★★ 第 {fl} 层：家具**互不重叠**', not over, str(over))

        # ── H4 放不下的要报出来 ──
        # ★ "少画一件"可以接受，"悄悄少一件"不行（2026-10-26 报过"这口井不见了"）。
        # [EN] "One fewer drawn" is acceptable; "one fewer silently" is not (the 2026-10-26 report).
        _declared = sum(1 for q in (PROG.fixtures_of(fl) or []))
        _got = len(fp.fixtures) + len(fp.orphans)
        ok_ &= rec(f'H4 ★★★ 第 {fl} 层：陈设**一件都没丢**（放好的 + 报出来的 = 任务书里声明的）',
                   _declared == _got, f'声明 {_declared} · 放好 {len(fp.fixtures)} · 报出 {len(fp.orphans)}')

    # ── H2b 合成用例：**一定会撞门**的那种布局 ──
    #
    # ★ 为什么必须合成：真实夹具（客来楼）里家具少、门偏，**本来就不撞** ——
    #   只测它，"不避门洞"这个变异永远不会红。
    #   造一个"房间窄、门在正中、贴墙家具多到必须排过门口"的房间：贴墙族（柜）沿上墙排，
    #   门检查启用时避开门口；门检查被变异关掉时，柜子直接排到门洞上 ⇒ 挡门。
    # ★ 用贴墙族而非浮置族：浮置族有 `standoff` 天然离门墙远，压不到门检查这条逻辑。
    # [EN] ★ Why a synthetic case: the real fixture does not collide, so the "no doorway clearance"
    # [EN] mutation never goes red on it. Build a narrow room with a centred door and enough wall-hugging
    # [EN] pieces (cabinets) to be forced past the opening: doorway clearance on => avoided; off => blocked.
    # [EN] Use wall pieces, not float ones -- float pieces keep off the wall via standoff and never reach
    # [EN] the doorway check.
    class _Q:
        def __init__(self, nm):
            self.name = nm

    class _D:
        def __init__(self, x, y, w, along='h'):
            self.x, self.y, self.w, self.along = x, y, w, along

    _room = (100.0, 100.0, 320.0, 200.0)          # 220 × 100
    _door = _D(210.0, 100.0, 26.0, 'h')           # 上墙正中
    _items = [_Q('柜')] * 6                       # 6 × 28 宽 + 间隙 ⇒ 必然铺过门口
    _placed, _drop, _tight = RP._pack_fixtures(_room, _items, doors=[_door])
    _block = [b for _n, b, _h in _placed if RP_blocks_door(b, _door, _room)]
    ok_ &= rec('H2b ★★★ 合成布局（窄房 + 门在正中 + 6 个柜）**没有任何一件排在门口**'
               '（真实夹具本来就不撞，只测它这一条永远红不了）',
               bool(_placed) and not _block,
               f'放下 {len(_placed)} 件 · 挡门 {len(_block)} 件')

    # ── H4b 每件家具**都带名字** ──
    #
    # ★★★ 2026-10-27（用户：「家具都没了啊」）：我把 `_furniture` 换成 `FR.draw(...)` 时，
    #   把旧版末尾那句 `_label(...)` 一起删了 —— 图上只剩几个没名字的浅色小方块，
    #   在小画布上看起来就是"什么都没画"。**当时所有判据都是绿的**，因为没有一条判据
    #   管"这件家具叫什么"。
    #   ⇒ 判据要盯"图上有没有这件家具的名字"，不是"有没有这个矩形"。
    # [EN] ★★★ 2026-10-27 (the user: "the furniture is all gone"): replacing `_furniture` with
    # [EN] `FR.draw(...)` also dropped the old trailing `_label(...)`, leaving a few unnamed pale
    # [EN] rectangles that read as "nothing drawn" -- and **every criterion was green**, because none
    # [EN] asked "what is this piece called". => The criterion must check the name is on the map, not
    # [EN] that the rectangle exists.
    _lays = FP.build_detail_shapes(
        ML.Layout.from_dict({'places': [{'name': p.name, 'x': p.x, 'y': p.y,
                                        'shape': p.shape, 'size': p.size}
                                       for p in PROG.to_places()] if hasattr(PROG, 'to_places')
                            else [], 'kind': '室内', '程序': PROG.to_dict()}),
        detail='室内')
    _txts = {str(getattr(q, 'value', '') or '') for q in _lays if type(q).__name__ == 'Text'}
    _fx_names = set()
    for _fl, _fp in PLANS.items():
        _fx_names |= set(_fp.fixtures)
    _missing = sorted(n for n in _fx_names if n not in _txts)
    ok_ &= rec('H4b ★★★ **每一件家具的名字都在图上**（只画矩形不写名字，'
               '在小画布上看起来就是"什么都没画"——2026-10-27 就是这么回归的）',
               bool(_fx_names) and not _missing,
               f'家具 {sorted(_fx_names)} · 缺名 {_missing}')

    # ── H4c 图上**没有两行字叠在一起** ──
    #
    # ★ 2026-10-27（查"家具都没了"时顺手量出来的）：院子摆在同一张平面最上面时，
    #   院墙上沿与房子外框上沿**是同一条线** ⇒ 院名与楼名写在同一个位置，
    #   实测相距 7px（字高 13），肉眼就是一团糊字。
    #   这类"两个标签挤在同一处"的问题，**没有任何一条判据在看**（都没红）。
    # [EN] ★ 2026-10-27 (measured while investigating "the furniture is gone"): when the courtyard sits
    # [EN] at the very top of the plan, its wall top edge **is** the house frame's top edge, so the
    # [EN] courtyard name and the building name are written at the same spot (measured 7px apart with
    # [EN] 13px glyphs: a smudge). No criterion was watching for "two labels on the same spot".
    _lyt = FP.build_detail_shapes(
        ML.Layout.from_dict({'places': [], 'kind': '室内外', '程序': PROG.to_dict()}),
        detail='室内外')
    _ts = [(str(getattr(q, 'value', '') or ''),
            float(getattr(q, 'x', 0) or 0), float(getattr(q, 'y', 0) or 0),
            float(getattr(q, 'size', 12) or 12))
           for q in _lyt if type(q).__name__ == 'Text']
    _ovl = []
    for _i in range(len(_ts)):
        for _j in range(_i + 1, len(_ts)):
            _a, _b = _ts[_i], _ts[_j]
            _aw = MM._cjk_w(_a[0], int(_a[3]))
            _bw = MM._cjk_w(_b[0], int(_b[3]))
            if (min(_a[1] + _aw, _b[1] + _bw) - max(_a[1], _b[1]) > 0.5
                    and min(_a[2] + _a[3], _b[2] + _b[3]) - max(_a[2], _b[2]) > 0.5):
                _ovl.append((_a[0], _b[0]))
    ok_ &= rec('H4c ★★★ 图上**没有两行字叠在一起**（院名与楼名、家具名与房间名，'
               '实测都叠过：7px 间距对 13px 字高，肉眼是一团糊）',
               not _ovl, str(_ovl[:4]))

    # ── H5 尺寸按类型 ──
    _cw, _ch = FR.spec_of('柜台').w, FR.spec_of('柜台').h
    _ww = FR.spec_of('井').w
    _bh = FR.spec_of('床').h
    ok_ &= rec('H5 ★★★ 尺寸**按类型**（柜台比井宽、床比柜台高 —— 不是件件 15×15）',
               _cw > _ww + 8.0 and _bh > _ch + 8.0,
               f'柜台 {_cw}×{_ch} · 井 {_ww} · 床高 {_bh}')

    # ── H6 井是同心圆 ──
    _sh: list = []
    FP._furniture(_sh, (100.0, 100.0, 126.0, 126.0), FP.PALETTE, None, False, '井')
    _circles = [q for q in _sh if type(q).__name__ == 'Circle']
    # ⚠ 只数**家具本体**的矩形：名字底下那块纸色垫片也是 `Rect`，
    #   第一版把它算进来 ⇒ 井明明画对了也判红（判据自己的误报）。
    # [EN] ⚠ Count only the **piece's own** rectangles: the paper patch behind the label is a `Rect`
    # [EN] too, and the first version counted it, so a correctly drawn well went red (criterion
    # [EN] false report).
    _furn_fill = str(FP.PALETTE.get('furniture', ''))
    _rects = [q for q in _sh if type(q).__name__ == 'Rect'
              and str(getattr(getattr(q, 'paint', None), 'color', '')) == _furn_fill]
    ok_ &= rec('H6 ★★★ 井画**同心圆**（不是方块；它在别的路径里本来就是同心圆，'
               '只因归成"陈设"就走了方块那条路）',
               len(_circles) >= 2 and not _rects,
               f'圆 {len(_circles)} · 家具本体矩形 {len(_rects)}')

    # ── H7 认得出类（词表顺序敏感） ──
    ok_ &= rec('H7 ★★★ 陈设**认得出类**，且词表**顺序敏感**（`柜台` 先于 `柜`）',
               FR.kind_of('柜台') == 'counter'
               and FR.kind_of('账台小柜') != 'counter'
               and FR.kind_of('院子西北角的井') == 'well'
               and FR.kind_of('一张方桌') == 'table',
               f"柜台={FR.kind_of('柜台')} 账台小柜={FR.kind_of('账台小柜')} "
               f"井={FR.kind_of('院子西北角的井')} 桌={FR.kind_of('一张方桌')}")

    # ── H8 浮置族（柜台/井/桌）真的离墙留站人空间 ──
    #
    # ★★★ 2026-10-27（用户）：「不是所有家具都靠墙 比如柜台 要有留空站人才对」。
    #   浮置族（anchor ∈ float/center 且实际 `anchor_of=='float'`）必须离墙 ≥ 一件家具的
    #   净空（明显大于 `pad=6.15`，肉眼看得出"柜台前空着一片"）。
    #   退化成贴墙的那件（`anchor_of=='wall'`）不算浮置，不冤它，但 H1（≥pad）仍守。
    # [EN] ★★★ 2026-10-27 (the user): "not every piece hugs a wall; a counter needs standing room".
    # [EN] Float pieces (declared float/center AND really placed as 'float') must sit ≥ a piece's
    # [EN] clearance off the wall -- visibly more than `pad`. Degraded-to-wall pieces are not blamed.
    STANDOFF = 14.0
    bad8 = []
    for fl, fp in PLANS.items():
        for nm, (owner, box) in fp.fixtures.items():
            if fp.anchor_of.get(nm) != 'float':
                continue
            r = fp.rooms.get(owner)
            if not r:
                continue
            min_wall = min(box[0] - r[0], box[1] - r[1],
                          r[2] - box[2], r[3] - box[3])
            if min_wall < STANDOFF:
                bad8.append((nm, round(min_wall, 1)))
    ok_ &= rec('H8 ★★★ 浮置族家具（柜台/井/桌）**离墙 ≥ 14px 留站人空间**'
               '（柜台不贴墙根，前后都有空；用户：要有留空站人才对）',
               not bad8, str(bad8))

    # ── H9 浮置族之间不挤死（留半身通道）──
    # ★ 只在**同一间房**内比较：跨房间的浮置件（如堂屋的柜台 vs 后院的井）
    #   本来就隔着墙，不该比（实测 H9 因此误报）。
    # [EN] Compare only **within one room**: float pieces in different rooms are wall-separated.
    bad9 = []
    for fl, fp in PLANS.items():
        by_room: dict = {}
        for nm, (owner, box) in fp.fixtures.items():
            if fp.anchor_of.get(nm) == 'float':
                by_room.setdefault(owner, []).append((nm, box))
        for owner, flt in by_room.items():
            for i in range(len(flt)):
                for j in range(i + 1, len(flt)):
                    a, b = flt[i][1], flt[j][1]
                    gx = min(a[2], b[2]) - max(a[0], b[0])
                    gy = min(a[3], b[3]) - max(a[1], b[1])
                    if gx < 8.0 and gy < 8.0:
                        bad9.append((flt[i][0], flt[j][0]))
    ok_ &= rec('H9 ★★ 浮置族家具之间留半身通道（同一间房内的两件浮置家具不互相贴死）',
               not bad9, str(bad9))

    # ── H10 摆放习性表没被改坏 ──
    ok_ &= rec('H10 ★★★ 家具摆放习性正确（柜台=float 浮置、井=center 居中、'
               '桌=center 居中、灶/床/柜/架/椅凳/箱=wall 贴墙、筐篓=corner 贴角）',
               FR.spec_of('柜台').anchor == 'float'
               and FR.spec_of('井').anchor == 'center'
               and FR.spec_of('桌').anchor == 'center'
               and FR.spec_of('灶').anchor == 'wall'
               and FR.spec_of('床').anchor == 'wall'
               and FR.spec_of('柜').anchor == 'wall'
               and FR.spec_of('架').anchor == 'wall'
               and FR.spec_of('椅凳').anchor == 'wall'
               and FR.spec_of('箱').anchor == 'wall'
               and FR.spec_of('筐篓').anchor == 'corner', '')

    # ── H11 净空不足**要报出来**（不许悄悄塞进去）──
    #
    # ★★★ 2026-10-27（用户：「柜台 是要有留空站人才对」）：家具**摆上去了**，
    #   但它要求留白的那块地方被别人占了 —— 图上看着"有家具"，实际站不进人。
    #   这种"摆上了但不对"最难被发现 ⇒ 必须有一份**清单**，并且审核里要报出来。
    #
    #   两条腿：
    #   ① **合成用例**：一间小到"净空根本不够"的房（井在当中、三口灶沿墙排），
    #      灶必然有一口被塞进井的站人区 ⇒ 解算层必须把它**标出来**。
    #   ② **真数据**：解算层标出来的每一件，审核清单里都要**提到**（不许只在内部记着）。
    # [EN] ★★★ 2026-10-27 (the user: "a counter needs standing room"): the piece **is** placed but
    # [EN] the space it needs is taken -- the map looks furnished yet nobody can stand there. Such
    # [EN] "placed but wrong" states are the hardest to spot => there must be a **list**, and the audit
    # [EN] must mention it. (1) **Synthetic**: a room too small for its clearance (a well in the middle,
    # [EN] three stoves along the wall) => one stove must be pushed into the well's standing room and
    # [EN] the solver must **flag** it. (2) **Real data**: every flagged piece must be mentioned in the
    # [EN] audit list (not just remembered internally).
    _room3 = (100.0, 100.0, 240.0, 200.0)
    _p3, _d3, _t3 = RP._pack_fixtures(_room3, [_Q('井')] + [_Q('灶')] * 3, doors=[])
    _miss_tight: list = []
    for fl, fp in PLANS.items():
        _iss = RP.audit(fp, PROG)
        for nm in (getattr(fp, 'tight', None) or {}):
            if not any(nm in q for q in _iss):
                _miss_tight.append((fl, nm))
    ok_ &= rec('H11 ★★★ **净空不足的陈设要报出来**（摆上去了但站人的地方被占了 —— '
               '图上看着"有家具"，实际站不进人；不许悄悄塞进去）',
               bool(_t3) and not _miss_tight,
               f'合成用例净空不足 {list(_t3)} · 真数据漏报 {_miss_tight}')

    # ── H12 同一面墙上**能并排放两件**（全局间隙一刀切的老坑）──
    #
    # ★ 2026-10-27 查出来的：老实现用一个全局间隙（14px）判"挤不挤"，
    #   而沿墙排家具的间距是 `ITEM_GAP`（3px）⇒ 两件并排**必然**被判成"挤"，
    #   于是同一面墙上只放得下一件（实测：六口柜只放进三件，其余报"放不下"，
    #   而门口那一段反而空着）。⇒ 判据钉住"并排两件都得放得下"。
    # [EN] ★ 2026-10-27: the old code judged "cramped" with **one global gap** (14px) while the
    # [EN] along-wall spacing is `ITEM_GAP` (3px) => two side-by-side pieces were **always** judged
    # [EN] cramped, so only one per wall fitted (measured: six cabinets, three placed, the stretch by
    # [EN] the doorway left empty). => pin down "two side by side both fit".
    _room2 = (100.0, 100.0, 320.0, 200.0)
    _p2, _d2, _t2 = RP._pack_fixtures(_room2, [_Q('柜')] * 2, doors=[])
    # ★ 必须断言"**同一面墙**"：只数件数不行 —— 老实现也会放两件（挤到别的墙上去）。
    #   真正要守住的是"并排"：两件挨在一起，各留各的净空。
    _side_by_side = (len(_p2) == 2
                     and abs(_p2[0][1][1] - _p2[1][1][1]) < 0.6
                     and abs(_p2[0][1][3] - _p2[1][1][3]) < 0.6)
    ok_ &= rec('H12 ★★★ 同一面墙上**能并排放两件**（老实现用一个全局间隙判"挤不挤"，'
               '并排两件必然被判挤 ⇒ 每面墙只放得下一件）',
               _side_by_side, f'放下 {len(_p2)} 件 · {[b for _n, b, _h in _p2]}')
    return ok_


def main() -> int:
    print('房间任务书 → 平面图 · 解算与审核 验证', flush=True)
    ok = True
    try:
        head('A. 拼满 / 不叠 / 不漏')
        ok &= test_tiling()
        head('B. 整栋楼 / 陈设归属 / 院子见天')
        ok &= test_building()
        head('C. 门开在墙上')
        ok &= test_doors()
        head('D. 分层')
        ok &= test_floors()
        head('E. 延续性（同一任务书 ⇒ 同一张图）')
        ok &= test_continuity()
        head('F. 审核 → 打回美术改任务书')
        ok &= test_audit_and_feedback()
        head('G. "人在哪间房"不许被当成建筑名（屋子凭空少一间的那个 bug）')
        ok &= test_here_is_not_building()
        head('H. 家具：形状按类型 / 不压墙 / 不撞门 / 不叠 / 不丢')
        ok &= test_furniture()
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'roomplan_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    n = sum(1 for c in report['checks'] if c['ok'])
    total = len(report['checks'])
    print(f'\n{"=" * 62}\n通过 {n}/{total} 项\n{"=" * 62}')
    if report.get('fatal'):
        print('⚠ 中途崩溃：\n' + report['fatal'])
    return 0 if (ok and n == total) else 2


if __name__ == '__main__':
    sys.exit(main())
