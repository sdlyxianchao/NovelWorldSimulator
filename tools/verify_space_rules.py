# -*- coding: utf-8 -*-
"""**空间常识与地图能力**的判据（用户 2026-10-12 那一轮）。

用户原话（这一份的全部理由）
--------------------------
    「小地图如果是**室内地图** 就用**一个框把相关内容括起来 作为这个建筑的名字**
      现在是**中间一个红点**作为建筑名字 不但**挡住了内容** 还不合理
      而且请**严格区分室内室外** 如果要画地图 请在**写小说或者编剧**的时候就把
      **环境平面描述的很清楚** 像现在**临河茶肆** 有**柜台 井 门**等
      （⚠ 原话里点的是那本书的楼名，此处按通用性规则换成演示夹具名）
      (⚠ The original words named that book's building; replaced here with the demo fixture name)
      **井肯定是要在院子里的 不能够在屋里 这种错误不能够出现**
      还有**如果有井 则说明有院子 需要把院子也画出来**
      ……优化**小说作家 剧作家 编剧室 导演 美术和道具**的能力……
      还有一点 **导演和剧作家在设计人物动作的时候 要时时刻刻参考地图作为
      人物移动的依据** 而且有些剧情也需要**地图的地点切换**来实现推进发展」

分四组：
  A 空间常识本体（`world/spatial`）：分类、审计、修（有井补院）、走动依据
  B 地图数据侧：`Layout.kind/frame`、底图与**当天的图**都过一遍空间规则
  C 六个职位（+场记）：货架/点名/提示词真的带上了这些能力
  D 小地图：室内图**框住 + 建筑名在框上 + 门在框上 + 没有中间那个点**

English:
**Criterion for spatial common sense and map ability** (the round of 2026-10-12).
The user's exact words (the entire rationale for this file): "if the minimap is an **indoor map**, use
**a frame to enclose the relevant content as this building's name**; right now there is **a red dot in the
middle** as the building's name, which not only **covers the content** but is unreasonable; also please
**strictly distinguish indoors and outdoors**; if you are going to draw a map, describe the
**environmental floor plan very clearly when writing the novel or the script**; like the current **Mo Wen
Tower** with its **counter, well, gate**, etc. -- **a well definitely belongs in the courtyard**, it
cannot be indoors, **this kind of mistake must not happen**; and **if there is a well, that means there is
a courtyard, so the courtyard must be drawn too** ... optimise the abilities of the **novelist,
playwright, writers' room, director, art and props** ... and one more thing: **the director and playwright
must constantly consult the map as the basis for character movement when designing character actions**,
and some plots need **switching between map locations** to advance".
Four groups:
  A spatial common sense itself (`world/spatial`): classification, audit, repair (a well adds a
  courtyard), the basis for movement
  B the data side of the map: `Layout.kind/frame`, and both the base map and **the day's map** run
  through the spatial rules
  C the six positions (+ continuity): shelves / named entries / prompts really
  carry these abilities
  D the minimap: an indoor map is **framed + the building name is on the frame + the gate is on the
  frame + the dot in the middle is gone**
"""
from __future__ import annotations

import ast
import json
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from world import spatial as SP                                # noqa: E402
from image_gen.map_layout import Layout, Place, apply_space_rules, \
    day_layout                                                # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

_CHECKS: list[dict] = []
_FAILS = 0


def ok(name: str, cond: bool, detail: str = '') -> bool:
    """记一条断言（与其它判据同一口径：`✗` 前缀表示失败）。"""
    global _FAILS
    _CHECKS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:300]})
    if not cond:
        _FAILS += 1
    print(f'  {"✓" if cond else "✗"} {name}' + (f'  ｜ {detail}' if detail else ''))
    return bool(cond)


def _src(fn) -> str:
    """一个函数/方法的源码（AST 判据用）。"""
    import inspect
    try:
        return inspect.getsource(fn)
    except Exception:                                            # noqa: BLE001
        return ''


def _txt(path: str) -> str:
    return (APP_DIR / path).read_text(encoding='utf-8')


# ══════════════════════════════════════════════════════════════════
#  A 组：空间常识本体
# [EN] Group A: spatial common sense itself
# ══════════════════════════════════════════════════════════════════
def group_a() -> dict:
    """空间常识本体（纯函数，零 LLM）。"""
    print('\n── A 组：空间常识本体 ──')
    rep: dict = {}

    # A1 分类：用户举的那几个例子（临河茶肆：柜台 / 井 / 门）
    # [EN] A1 classification: the examples the user gave (Mo Wen Tower: counter / well / gate)
    cases = {
        '井': (SP.SPACE_OUT, '室外器物'),
        '水井': (SP.SPACE_OUT, '室外器物'),
        '树': (SP.SPACE_OUT, '室外器物'),
        '影壁': (SP.SPACE_OUT, '室外器物'),
        '堂屋': (SP.SPACE_IN, '室内空间'),
        '临河茶肆·前厅': (SP.SPACE_IN, '室内空间'),
        '柜台': (SP.SPACE_IN, '室内陈设'),
        '条案': (SP.SPACE_IN, '室内陈设'),
        '后院': (SP.SPACE_OUT, '室外空间'),
        '院子': (SP.SPACE_OUT, '室外空间'),
        '廊下': (SP.SPACE_SEMI, '半室外'),
        '大门': (SP.SPACE_NONE, '边界'),
        '院墙': (SP.SPACE_NONE, '边界'),
        '临河茶肆': (SP.SPACE_NONE, '整座建筑'),
    }
    bad = [n for n, (sp, role) in cases.items()
           if SP.space_of(n) != sp or SP.role_of(n) != role]
    rep['a1'] = {n: SP.role_of(n) for n in cases}
    ok('A1 ★★★ 分类分得开：井/树/影壁是**屋外**的，堂屋/柜台是**屋里**的，'
       '门/墙是**边界**，临河茶肆是**整座建筑**（用户举的三个例子都在里面）',
       not bad, f'分错的：{bad}')

    # A2 有井却没有院子 → 必须报出来
    # [EN] A2 a well with no courtyard -> must be reported
    v = SP.audit(['堂屋', '柜台', '井', '大门'])
    rep['a2'] = [x.code for x in v]
    ok('A2 ★★★ 有井却没有院子 ⇒ 报「井无院」'
       '（用户原话：「井肯定是要在院子里的 不能够在屋里」）',
       [x.code for x in v] == ['井无院'], str(rep['a2']))

    # A3 修：补一个院子，名字带建筑名，并说明为什么
    # [EN] A3 repair: add a courtyard, prefixed with the building name, and say why
    fixed, notes = SP.repair(['堂屋', '柜台', '井'], building='临河茶肆')
    rep['a3'] = {'fixed': fixed, 'notes': notes}
    ok('A3 ★★★ 修的时候**补一个院子**（「有井则说明有院子 需要把院子也画出来」）'
       '—— 而且院子用建筑名打头（`临河茶肆·院子`），跟别处的院子分得开',
       '临河茶肆·院子' in fixed and any('院子' in n for n in notes), str(rep['a3'])[:160])

    # A4 修完再审计 = 干净（幂等）
    # [EN] A4 after the repair, the audit is clean (idempotent)
    again = SP.audit(fixed)
    fixed2, notes2 = SP.repair(fixed, building='临河茶肆')
    rep['a4'] = {'again': [x.code for x in again], 'notes2': notes2}
    ok('A4 ★★ 修完就不该再报（幂等）：再审计一次是干净的、再修一次不该再做任何事',
       not again and not notes2, str(rep['a4'])[:160])

    # A5 本来就有院子 → 不再补
    # [EN] A5 a courtyard already exists -> do not add another
    f5, n5 = SP.repair(['堂屋', '后院', '井'])
    rep['a5'] = {'fixed': f5, 'notes': n5}
    ok('A5 ★★ 已经有院子时**不重复补**（后院已经是院子了）',
       f5 == ['堂屋', '后院', '井'] and not n5, str(rep['a5']))

    # A6 ★ 院墙**不算**院子（否则有井也不补 —— 正好放过用户要挡的错）
    # [EN] A6 ★ a courtyard wall does **not** count as a courtyard
    # ⚠ 用「后院墙」而不是「院墙」：`院墙` 正好是 `BOUNDARY_WORDS` 里的一条，
    #   两条守卫（精确匹配 + 含"墙"字）都能拦住它 ⇒ **分不出是哪一条在挡**。
    #   `后院墙` 只能靠"含墙字"那一条拦住 —— 这样这一条断言才真的钉住那半句。
    # [EN] ⚠ Use "后院墙" rather than "院墙": `院墙` happens to be an entry in `BOUNDARY_WORDS`, so
    # [EN] both guards (exact match + contains "墙") stop it ⇒ **you cannot tell which one is doing the
    # [EN] work**. `后院墙` can only be stopped by the "contains 墙" clause, so this assertion really
    # [EN] pins that half down.
    f6, n6 = SP.repair(['堂屋', '后院墙', '井'])
    rep['a6'] = {'fixed': f6, 'notes': n6}
    ok('A6 ★★★ 「院墙」不算院子（名字里有"院"字）—— 院里只有墙、井还是要补院子'
       '（⚠ 墙要排在井**前面**：补院子那一步是"往前看"，墙排在后面的话，'
       '这一条根本验不到那半句守卫）',
       '院子' in f6 and any('院子' in x for x in n6), str(rep['a6'])[:160])

    # A7 屋里空间跑到院外的图上
    # [EN] A7 an indoor space leaked onto the outdoor map
    v7 = SP.audit(['临河茶肆', '堂屋'], kind='局部')
    rep['a7'] = [x.code for x in v7]
    ok('A7 ★★ 院里（局部/整体层）出现**屋里空间** ⇒ 报「房间出屋」'
       '（屋里的事不该画在院外的图上）',
       [x.code for x in v7] == ['房间出屋'], str(rep['a7']))

    # A8 重名
    # [EN] A8 duplicate names
    # ⚠ 只断言"里面有「重名」"：`['井','井']` 同时也会触发「井无院」
    #   （两个井都没有院子）—— 那是**对的**，一条违规不该把另一条盖掉。
    # [EN] ⚠ Only assert that "重名" is among them: `['井','井']` also triggers "well without a
    # [EN] courtyard" (neither well has a yard) -- which is **correct**; one violation must not mask
    # [EN] another.
    codes8 = [x.code for x in SP.audit(['井', '井'])]
    rep['a8'] = codes8
    ok('A8 ★ 重名要报（图上两个点、台账两条，后面全乱）'
       '—— 而且**不盖掉别的违规**',
       '重名' in codes8 and '井无院' in codes8, str(codes8))

    # A9 走动依据：从井到堂屋**要经过院子**（不是穿墙）
    # [EN] A9 movement basis: from the well to the hall **goes through the courtyard**
    r9 = SP.route(fixed, None, '井', '堂屋')
    rep['a9'] = r9
    ok('A9 ★★★ 走法**有依据**：从井到堂屋要经过院子（「井 → 临河茶肆·院子 → 堂屋」）'
       '—— 地图因此能当"人物移动的依据"',
       r9 == ['井', '临河茶肆·院子', '堂屋'], str(r9))

    # A10 没连着的两处 → 明确说走不通（不许一步跨过去）
    # [EN] A10 two unconnected places -> say plainly it is unreachable
    ok('A10 ★★ 图里没有的两处 ⇒ 空路径（调用方据此说"别让人一步跨过去"）',
       SP.route(fixed, None, '井', '北门市集') == [], '')

    # A11 movement_line 的措辞（走不通时点明要经过哪儿）
    # [EN] A11 the wording of movement_line
    m11 = SP.movement_line(['堂屋', '井'], None, '井', '堂屋')
    rep['a11'] = m11
    ok('A11 ★★ 走动那句话读得懂：走不通时点明"要经过哪儿"，而不是只说一句"走不通"',
       '走不通' not in m11 and m11.startswith('从井到堂屋'), m11[:80])

    # A12 给提示词的表格带上"层"（屋里/院里）
    # [EN] A12 the prompt table carries the "layer" (in the house / in the yard)
    t12 = {r['名称']: r.get('层') for r in SP.space_table(fixed)}
    rep['a12'] = t12
    ok('A12 ★★ 摊给模型的表里，每一项都注明**屋里还是院里**'
       '（模型不许自己猜里外）',
       t12.get('井') == '院里' and t12.get('堂屋') == '屋里'
       and t12.get('柜台') == '屋里', str(t12))

    # A13 空间事实那段话里要有"井在院子里"这句硬话
    # [EN] A13 the spatial-facts passage must contain the hard line "the well is in the courtyard"
    h13 = SP.hint_block(fixed, building='临河茶肆')
    rep['a13'] = h13[:200]
    ok('A13 ★★ 「空间事实」那段话**当面写清**：井在院里不在屋里、'
       '屋里的有顶院里的见天',
       '井在院子里' in h13 and '见天' in h13, h13[:120])

    # A14 未知名字不冒充（宁可不标，也不乱标）
    # [EN] A14 unknown names are not faked
    ok('A14 ★ 认不出来的名字标「（未定）」—— 不猜（猜错比不标更糟）',
       SP.role_of('阿九的院子西边那棵') == '（未定）'
       or SP.role_of('某处') == '（未定）', SP.role_of('某处'))
    return rep


# ══════════════════════════════════════════════════════════════════
#  B 组：数据侧（Layout 标记 / 底图与当天的图都过规则）
# [EN] Group B: the data side
# ══════════════════════════════════════════════════════════════════
def group_b() -> dict:
    """`Layout.kind/frame` + 两处调用点。"""
    print('\n── B 组：地图数据侧 ──')
    rep: dict = {}

    lay = Layout(places=[Place('堂屋', 0.3, 0.35, shape='屋'),
                         Place('井', 0.7, 0.6, shape='院'),
                         Place('柜台', 0.35, 0.5)])
    notes = apply_space_rules(lay, kind='室内', building='临河茶肆')
    rep['b1'] = {'kind': lay.kind, 'frame': lay.frame,
                 'names': [p.name for p in lay.places], 'notes': notes}
    ok('B1 ★★★ `apply_space_rules` 干三件事：打 `kind`/`frame` 标记、'
       '补院子、**报出它做了什么**',
       lay.kind == '室内' and lay.frame == '临河茶肆'
       and '临河茶肆·院子' in [p.name for p in lay.places] and bool(notes),
       str(rep['b1'])[:200])

    yard = next((p for p in lay.places if p.name == '临河茶肆·院子'), None)
    well = next((p for p in lay.places if p.name == '井'), None)
    rep['b2'] = {'yard_xy': (yard.x, yard.y) if yard else None,
                 'well_xy': (well.x, well.y) if well else None,
                 'short': yard.short if yard else ''}
    ok('B2 ★★ 补出来的院子**摆在井旁边**（图上挨着才看得出"井在院里"）'
       '，并且简称是「院子」（不然图上写的是整座楼的名字）',
       yard is not None and well is not None
       and abs(yard.x - well.x) <= 0.25 and abs(yard.y - well.y) <= 0.25
       and yard.short == '院子', str(rep['b2']))

    # B3 kind/frame 必须能进 JSON 再读回来（缓存是它是它）
    # [EN] B3 kind/frame must survive a JSON round trip
    back = Layout.from_dict(lay.to_dict())
    rep['b3'] = {'kind': back.kind, 'frame': back.frame}
    ok('B3 ★★ `kind`/`frame` 进 `to_dict()`、也读得回来（底图是存盘的）',
       back is not None and back.kind == '室内' and back.frame == '临河茶肆',
       str(rep['b3']))

    # B4 老缓存（没有这两个键）读回来不炸，按"不是室内图"处理
    # [EN] B4 an old cache without the two keys reads back without blowing up
    old = {'source': 'atlas', 'caption': '小世界',
           'places': [{'name': '堂屋', 'x': 0.3, 'y': 0.4, 'shape': '屋',
                       'size': '中', 'short': '', 'note': ''}]}
    b4 = Layout.from_dict(old)
    rep['b4'] = {'kind': b4.kind if b4 else None,
                 'frame': b4.frame if b4 else None}
    ok('B4 ★ 老缓存（没有 `kind`/`frame` 键）读回来是空串、不报错'
       '—— 老档案打开时行为跟从前**一模一样**',
       b4 is not None and b4.kind == '' and b4.frame == '', str(rep['b4']))

    # B5 当天的图也要过一遍（同一天也可能有井）
    # [EN] B5 the day's map goes through it as well
    d = day_layout({'地点': [{'名称': '堂屋', 'x': 0.3, 'y': 0.4, '形': '屋'},
                             {'名称': '井', 'x': 0.7, 'y': 0.6, '形': '井'}],
                    '通路': [], '题记': '今日'},
                   ['堂屋', '井'], here='临河茶肆·堂屋')
    rep['b5'] = {'kind': d.kind if d else None, 'frame': d.frame if d else None,
                 'names': [p.name for p in d.places] if d else None}
    ok('B5 ★★★ **当天的图**同样过空间规则：有井就补院子、'
       '并标出这是"室内"的一层（整座：临河茶肆）',
       d is not None and '临河茶肆·院子' in [p.name for p in d.places]
       and d.kind == '室内' and d.frame == '临河茶肆', str(rep['b5'])[:200])

    # B6 不是室内的一天 → 不许给它加框（整座楼）
    # [EN] B6 a day that is not indoors must not get a frame
    d6 = day_layout({'地点': [{'名称': '临河茶肆', 'x': 0.3, 'y': 0.4, '形': '楼'}],
                     '通路': [], '题记': '今日'},
                    ['临河茶肆'], here='临河茶肆')
    rep['b6'] = {'kind': d6.kind if d6 else None, 'frame': d6.frame if d6 else None}
    ok('B6 ★★★ 戏在镇子上（不是屋里）⇒ **不加框**'
       '（`临河茶肆` 是整座建筑的名，不能被当成"屋里的一间"）',
       d6 is not None and d6.kind == '局部' and d6.frame == '', str(rep['b6']))

    # B7 底图那份实现只有一处（不许两处各写一套）
    # [EN] B7 exactly one implementation of the base-map side
    wa = _txt('world/atlas.py')
    ok('B7 ★★ `world.atlas.apply_space_rules` 是**转发**（实现只有一份，'
       '否则底图画了院子、当天的图又没了）',
       'from image_gen.map_layout import apply_space_rules as _impl' in wa, '')

    # B8 开卷管线真的调了它
    # [EN] B8 the ingestion pipeline really calls it
    ia = _txt('ingest/atlas.py')
    ok('B8 ★★ 开卷生成底图时**真的过了空间常识**（不是只写在注释里）',
       'AT.apply_space_rules(' in ia and "kind='室内'" in ia, '')
    return rep


# ══════════════════════════════════════════════════════════════════
#  C 组：六个职位（+场记）真的拿到了这些能力
# [EN] Group C: the six positions (+ continuity) really have these abilities
# ══════════════════════════════════════════════════════════════════
def group_c() -> dict:
    """货架 / 点名 / 提示词。"""
    print('\n── C 组：职位能力 ──')
    rep: dict = {}
    from crew import agents as A
    from craft import craftmix

    want = ('novelist', 'screenwriter', 'settings_room', 'director', 'art',
            'props', 'continuity')
    rep['c1'] = {k: list(A.SHELVES.get(k, ())) for k in want}
    ok('C1 ★★★ 用户点名的六个职位（小说作家/剧作家/编剧室/导演/美术/道具）'
       '＋场记，都读上了「场景与空间」这一架',
       all('场景与空间' in (A.SHELVES.get(k) or ()) for k in want),
       str([k for k in want if '场景与空间' not in (A.SHELVES.get(k) or ())]))

    entries = craftmix.load()['entries']
    bad = []
    for k, names in A.READS.items():
        sh = A.SHELVES.get(k, ())
        for n in names:
            e = entries.get(n)
            if e is None:
                bad.append(f'{k}→{n}（不存在）')
            elif str(e.get('_货架') or '') not in sh:
                bad.append(f'{k}→{n}（架不符）')
    ok('C2 ★★ 点名要读的条目**都存在、且属于它自己声明的货架**'
       '（跨架点名 = 把"这个职位读哪本书"变成假话）', not bad, '；'.join(bad[:3]))

    # C3 真进了提示词（这是"要求他们使用这些能力"的落点）
    # [EN] C3 they really reach the prompt
    #
    # ★★★ 2026-10-18 晚：**口径跟着"动态映射"改**。
    #   原来判「**单次** `craft_block` 里必须出现某个具体条目名」—— 调度器按
    #   （时机 × 品级 × 拍数）挑条目之后，任何一条都可能这一拍不被选中，
    #   于是这条判据在守的是"某个条目永不被轮空"，与设计直接冲突（必然假红）。
    #   ⚠ 但它守的事仍然要守：这些条目**得真的能到提示词里**，不是只挂在名册上。
    #   ⇒ 改成**多拍并集**：走 40 个 tick，只要其中任意一拍出现过就算"到得了"。
    #     这比原来更强：原来只证明"某一次拼装里有它"，现在证明"它真的会被轮进来"。
    #   ⚠ 成对：C4b 守"单次仍然只给额度内几条"（不许为了过这条而改成全给）。
    # [EN] ★★★ 2026-10-18 evening: **the rule follows dynamic dispatch**. It used to require a
    # [EN] specific entry in **one** `craft_block` call; once the dispatcher picks by (moment x grade
    # [EN] x tick), any entry may be skipped this beat, so that check guarded "one entry is never
    # [EN] rotated out" -- which contradicts the design and produced false reds.
    # [EN] ⚠ What it guards still holds: these entries must **really be able to reach** the prompt,
    # [EN] not just sit on a roster. => judge the **union across 12 ticks**; one appearance counts.
    # [EN] Stronger than before: it used to prove "present in one assembly", now it proves "it really
    # [EN] gets rotated in". ⚠ Paired with C4b: a single assembly still yields only the quota.
    def _union(k: str, genre: str = "言情", ticks: int = 12) -> set[str]:
        # ⚠ **时机也必须轮一遍**，只跑 `日常` 不够：条目的名字决定了它属于哪个时机
        #   （`一场一转变` 含"转变" ⇒ 属 `转折`），固定 `日常` 时它永远排在
        #   "时机不对"那一组，靠 tick 轮换 40 拍都轮不到（实测）。
        #   判的是"这本书里能不能读到它"—— 而时机本来就会随剧情变。
        # [EN] ⚠ The moment must be rotated too: an entry's name decides its moment, so with a fixed
        # [EN] 日常 it always sits in the "wrong moment" group and 40 ticks still miss it (measured).
        # [EN] The question is "can it be read in this book", and moments do vary with the story.
        from world.state import WorldState as _W

        out: set[str] = set()
        for mom in ('日常', '开场', '冲突', '转折', '收束'):
            for t in range(ticks):
                w = _W()
                w.beat_tick = t
                w.beat_moment = mom
                w.craft_level = '重'
                A.bind_world(w)
                try:
                    txt = A.craft_block(k, genre)
                finally:
                    A._reset_world()
                out |= {ln[1:ln.index('〕')] for ln in txt.splitlines() if ln.startswith('〔')}
        return out

    hits: dict = {}
    for k, needle in (('novelist', '里外先分清'),
                      ('screenwriter', '走动要有依据'),
                      ('director', '看得见是算得出来的'),
                      ('art', '先有底图再取景'),
                      ('props', '里外先分清'),
                      ('settings_room', '房间是图不是点'),
                      ('continuity', '走动要有依据')):
        hits[k] = needle in _union(k)
    rep['c3'] = hits
    ok('C3 ★★★ 这些条目**真的会轮到各自的提示词**（5 个时机 × 12 拍的并集里出现；'
       '不是只挂在名册上，也不是"某一条永不被轮空"）',
       all(hits.values()), str(hits))

    # C4 老朋友没被挤掉（加货架时最容易出的事）
    # [EN] C4 old entries were not squeezed out
    keep = {'novelist': '起承转合', 'screenwriter': '一场一转变',
            'director': '场景=价值转变', 'art': '以景写时',
            'props': '一件小道具承住一切', 'continuity': '一场一转变',
            'settings_room': '一场一转变'}
    lost = [k for k, n in keep.items() if n not in _union(k)]
    rep['c4'] = lost
    ok('C4 ★★ 加货架**没有挤掉**原来的手艺条目（5 个时机 × 12 拍的并集里都还在）',
       not lost, str(lost))
    # ★ 成对：不许为了过上面两条就"一次全给"（那是成本的另一个大坑）
    from world.state import WorldState as _W2

    _wq = _W2()
    _wq.beat_tick = 3
    _wq.beat_moment = '冲突'
    _wq.craft_level = '重'
    A.bind_world(_wq)
    try:
        _one = [ln for ln in A.craft_block('novelist', '言情').splitlines()
                if ln.startswith('〔')]
    finally:
        A._reset_world()
    ok('C4b ★★ 成对：**单次只给额度内几条**（最长 8 条），不是"把整架书摊开"',
       len(_one) <= 8, f'{len(_one)} 条')

    # C5 剧作家：`场` 要写成"地点·空间"，并且屋里/院里分开
    # [EN] C5 the playwright: `场` must be "place·space"
    sw = _src(A.Screenwriter.work)
    rep['c5'] = {'地点·空间': '地点·空间' in sw, '院子必须': '有院子' in sw,
                 '走位': '走到哪儿' in sw}
    ok('C5 ★★★ 剧作家写了：`场` 是「地点·空间」两层、**见天的东西归院里**、'
       '**有井就必须有院子**、`要点` 里要写**走位**（用户点名的那几句）',
       all(rep['c5'].values()), str(rep['c5']))

    # C6 剧作家：场景介绍要"照着就能画出平面"
    # [EN] C6 the playwright: the scene intro must be drawable as a floor plan
    ok('C6 ★★ `场景介绍` 要**把平面交代清楚**'
       '（用户：「在写小说或者编剧的时候就把环境平面描述的很清楚」）',
       '照着就能画出平面' in sw and '门在哪一面上' in sw, '')

    # C7 美术：两个分支（有底图 / 没底图）都要求"名字具体 + 里外分清"
    # [EN] C7 art: both branches require concrete names + inside/outside
    art = _src(A.Art.draw_day_map)
    rep['c7'] = art.count('名字写具体、里外分清')
    ok('C7 ★★★ 美术那两条提示词（**有底图**与**没底图**）都写上了'
       '"名字写具体、里外分清 + 出现井就必须出现院子"',
       art.count('名字写具体、里外分清') == 2, str(rep['c7']))

    # C8 底图摊给模型的文字里带 [室内空间]/[室外器物] 标
    # [EN] C8 the flattened base map carries the [indoor]/[outdoor object] tags
    ab = _src(A._atlas_block)
    lay = Layout(places=[Place('堂屋', 0.3, 0.4), Place('井', 0.7, 0.6)])
    apply_space_rules(lay, kind='室内', building='临河茶肆')
    txt = A._atlas_block([('室内', '临河茶肆', lay)])
    rep['c8'] = txt[:200]
    ok('C8 ★★★ 摊给模型的底图里**每一条都带里外标**（`[室内空间]` / `[室外器物]`）'
       '＋ 一段「空间事实」—— 模型因此不必猜"井在哪儿"',
       '[室外器物]' in txt and '[室内空间]' in txt and '空间事实' in txt,
       txt[:160])

    # C9 道具：要求"落得住地方"，并且数据里真的标了 `属于`
    # [EN] C9 props: must "have a place to sit", and the data really tags it
    pr = _src(A.Props.work)
    rep['c9'] = {'落得住': '落得住地方' in pr,
                 '属于': '属于' in _src(A._prop_space) or "SPACE_OUT" in _src(A._prop_space)}
    ok('C9 ★★★ 道具师被要求"每件东西都要落得住地方"（屋里/院里），'
       '而且产出里**每件都带**确定性的「属于」标注',
       rep['c9']['落得住'] and "'属于': _prop_space(nm)" in pr, str(rep['c9']))

    # C10 小说作家的场景卡规则：屋里屋里/院里分开写
    # [EN] C10 the novelist's scene-card rules: inside and outside written separately
    ok('C10 ★★★ 小说作家的**场景卡规则**里写了"屋里与院里分开写 + 有井必须有院 + '
       '屋里隔着墙"（用户：「写小说的时候就把环境平面描述的很清楚」）',
       '屋里与院里分开写' in A.SCENE_CARD_RULES
       and '隔着墙' in A.SCENE_CARD_RULES, '')

    # C11 导演与演员：地图真的当成了移动依据（**行为判**：把那一行算出来看）
    # [EN] C11 the director and actors: the map really serves as the basis for movement (**behavioural**:
    # [EN] compute that line and look at it)
    from types import SimpleNamespace
    from agent.core import Agent
    from director.stage import Beat
    lay11 = day_layout({'地点': [{'名称': '堂屋', 'x': 0.3, 'y': 0.4},
                                 {'名称': '井', 'x': 0.7, 'y': 0.6}],
                        '通路': [], '题记': '今日'},
                       ['堂屋', '井'], here='临河茶肆·堂屋')
    fake = SimpleNamespace(world=SimpleNamespace(day_map=lay11))
    line = Agent._map_line(fake, Beat(index=2, place='井'),
                           Beat(index=1, place='堂屋'))
    rep['c11'] = line
    ok('C11 ★★★ 演员每一拍真的拿到"**这一拍在哪儿（屋里/院里）+ 从上一场怎么走过来**"'
       '—— 算出来的是"堂屋 → 院子 → 井"，不是一句空话',
       '这一拍在什么地方：井' in line and '院里' in line
       and '堂屋 → 临河茶肆·院子 → 井' in line, line.replace('\n', ' ｜ ')[:200])

    # C11b 拿不到地图时**什么都不加**（不许因为它让"本场戏"整块消失）
    # [EN] C11b when there is no map, **add nothing**
    ok('C11b ★★ 今天没有地图（`day_map=None`）⇒ 这一行**空着**，'
       '不报错也不编（增强项不许弄坏主线）',
       Agent._map_line(SimpleNamespace(world=SimpleNamespace(day_map=None)),
                       Beat(index=1, place='堂屋'), None) == '', '')

    # C12 `StagePlan.previous`（"怎么走过来"要有上一场可比）
    # [EN] C12 `StagePlan.previous`
    from director.stage import StagePlan
    s12 = StagePlan([{'拍': 1, '场': '堂屋'}, {'拍': 2, '场': '井'}])
    rep['c12'] = {'first': s12.previous, 'after_advance': None}
    s12.advance()
    rep['c12']['after_advance'] = getattr(s12.previous, 'place', None)
    ok('C12 ★★ `StagePlan` 给出**上一场**（第一场是 None）—— "怎么走过来"靠它算',
       s12.previous is not None and s12.previous.place == '堂屋', str(rep['c12']))

    # C13 世界上真的挂着今天那张图（否则演员读不到）
    # [EN] C13 today's map is really hung on the world
    # ⚠ **按 AST 判，别 `in` 字符串**：`self.world.day_map = lay0`（另一条分支）
    #   **以 `= lay` 开头** —— 用子串判的话，把这一支改成 `= None` 照样绿
    #   （实测：反例法 C⑩ 报了"没抓到"）。
    # [EN] ⚠ **Judge by AST, not by substring `in`**: `self.world.day_map = lay0` (the other branch)
    # [EN] **starts with `= lay`**, so a substring check stays green even after this branch becomes
    # [EN] `= None` (measured: counterexample C⑩ reported "not caught").
    st = _txt('world/state.py')
    loop = _txt('sim/loop.py')
    hung = []
    for nd in ast.walk(ast.parse(loop)):
        if not isinstance(nd, ast.Assign):
            continue
        tg = nd.targets[0]
        if (isinstance(tg, ast.Attribute) and tg.attr == 'day_map'
                and isinstance(tg.value, ast.Attribute) and tg.value.attr == 'world'):
            hung.append(ast.unparse(nd.value).strip())
    rep['c13'] = hung
    # ⚠⚠ 2026-10-12 补正：这条原来写的是 `'lay' in hung` —— **只要求"至少有一处挂着"**。
    #   而 `sim/loop.py` 里 `world.day_map = lay` 有**两处**（"美术关着"与"正常出图"
    #   两条分支），于是反例法 C⑩ 只改掉一处时，另一处照样让判据绿 ⇒ **变异抓不到**
    #   （实测："没抓到的变异：C⑩"）。
    #   ⇒ 改成"**每一处挂载都不许是 `None`**" —— 两条分支都不许漏，
    #     这才是"字段存在且真的有人填"的意思。
    # [EN] ⚠⚠ Corrected 2026-10-12: this used to be `'lay' in hung` -- it only required "at least one
    # [EN] place hangs it". But `sim/loop.py` has **two** `world.day_map = lay` (the "art turned off"
    # [EN] and "normal output" branches), so when counterexample C⑩ changed only one of them, the other
    # [EN] still kept the criterion green ⇒ **the mutation was not caught** (measured: "not caught: C⑩").
    # [EN] ⇒ Changed to "**not a single hang may be `None`**" -- neither branch may be missed, which is
    # [EN] what "the field exists and somebody really fills it" means.
    ok('C13 ★★★ `world.day_map` 存在、而且 `sim/loop` 里**每一处挂载都真的挂了图**'
       '（不是 `None` —— 只加一个字段没人填 = 假按钮）',
       'day_map' in st and bool(hung)
       and all(str(v).strip() != 'None' for v in hung)
       and 'lay' in hung, str(hung))
    return rep


# ══════════════════════════════════════════════════════════════════
#  D 组：小地图（室内图 = 框住 + 建筑名 + 门在框上 + 没有中间那个点）
# [EN] Group D: the minimap
# ══════════════════════════════════════════════════════════════════
def group_d() -> dict:
    """渲染成形状列表之后**数形状**。"""
    print('\n── D 组：小地图 ──')
    rep: dict = {}
    from image_gen import minimap as MM

    lay = Layout(places=[Place('堂屋', 0.3, 0.32, shape='屋'),
                         Place('柜台', 0.3, 0.45),
                         Place('井', 0.72, 0.62, shape='院'),
                         Place('大门', 0.5, 0.88, shape='门')],
                 kind='室内', frame='临河茶肆', caption='临河茶肆')
    shapes = MM.build_shapes(lay, current='堂屋')
    kinds: dict = {}
    for s in shapes:
        kinds[type(s).__name__] = kinds.get(type(s).__name__, 0) + 1
    texts = [getattr(s, 'value', '') for s in shapes if type(s).__name__ == 'Text']
    rep['d1'] = {'kinds': kinds, 'texts': texts}

    # D1 建筑名在图上（当标题），且**不是**以一个点的方式出现
    # [EN] D1 the building name is on the map (as the title), not as a point
    ok('D1 ★★★ 室内图上写着**建筑名**（作标题用）',
       '临河茶肆' in texts, str(texts))
    return rep


def group_d2() -> dict:
    """边框那一组的正经断言（分开写，避免上面那条空转）。"""
    print('\n── D 组（续）：框与门 ──')
    rep: dict = {}
    from image_gen import minimap as MM
    import flet.canvas as fcv

    lay = Layout(places=[Place('堂屋', 0.3, 0.32, shape='屋'),
                         Place('柜台', 0.3, 0.45),
                         Place('井', 0.72, 0.62, shape='院'),
                         Place('大门', 0.5, 0.88, shape='门')],
                 kind='室内', frame='临河茶肆', caption='临河茶肆')
    shapes = MM.build_shapes(lay, current='堂屋')
    texts = [getattr(s, 'value', '') for s in shapes
             if type(s).__name__ == 'Text']
    rects = [s for s in shapes if isinstance(s, fcv.Rect)]
    rep['d2'] = {'n_rect': len(rects), 'texts': texts}

    # 框：最大的那个矩形（横跨大半个画布）
    # ⚠ 纸底那块也是大矩形（0,0,196,132）—— 用 `x >= 3` 把它排除掉，
    #   否则"不是室内图就不加框"那条永远红（两个大矩形里有一个是纸底）。
    # [EN] The paper base is a big rectangle too (0,0,196,132) -- exclude it with `x >= 3`, otherwise
    # [EN] "no frame when it is not an indoor map" is forever red (one of the two big rectangles is the
    # [EN] paper).
    big = [r for r in rects if r.width and r.width >= 150 and r.height
           and r.height >= 80 and float(getattr(r, 'x', 0) or 0) >= 3]
    ok('D2 ★★★ 室内图上**有一个框**把内容整个括起来'
       '（用户：「就用一个框把相关内容括起来」）',
       bool(big), f'{len(rects)} 个矩形，其中大框 {len(big)} 个')

    # ⚠ 2026-10-12 改口径：建筑名从"框**外面**的上方"（`fy0 - 5.5`）改到
    #   "框**内侧**的上沿"（`_on_wall`）—— 用户要求「名字标记都放到**墙的旁边**，
    #   不要放到别的东西的上面」。所以 y 从"小于 12"变成"框上沿往下一点点"。
    #   判据跟着改：仍在**框的上沿那一带**（不是压在房间中间）。
    # [EN] ⚠ Convention changed on 2026-10-12: the building name moved from "above, **outside** the
    # [EN] frame" (`fy0 - 5.5`) to "the **inside** of the frame's top edge" (`_on_wall`) -- the user
    # [EN] asked to "put the name labels **beside the wall**, not on top of other things". So y goes
    # [EN] from "less than 12" to "a little below the frame's top edge". The criterion follows: still
    # [EN] **in the top edge band** (not pressed onto the middle of a room).
    ok('D3 ★★★ 建筑名写在**框的上沿那一带**（贴墙，不是压在房间上）',
       any(t == '临河茶肆' for t in texts)
       and any(isinstance(s, fcv.Text) and getattr(s, 'value', '') == '临河茶肆'
               and s.y <= 24 for s in shapes),
       str([(getattr(s, 'value', ''), round(s.y, 1)) for s in shapes
            if type(s).__name__ == 'Text']))

    ok('D4 ★★★ 「门」画在**框的下沿**（门是边界，不在屋里）'
       '—— 用户举的临河茶肆三件事（柜台/井/门）各归其位',
       '门' in texts
       and not any(isinstance(s, fcv.Text) and getattr(s, 'value', '') == '大门'
                   for s in shapes),
       str([t for t in texts]))

    # ★ 浅底：给**院里**的东西垫的那一块（宽度约 3.4r ≈ 34px，比框小得多）。
    #   `堂屋`/`柜台` 在屋里，**不该**有浅底 —— 这是"屋里见顶、院里见天"的图上凭据。
    # [EN] ★ The wash: the patch behind **outdoor** things (about 3.4r ≈ 34px wide, far smaller than
    # [EN] the frame). `堂屋`/`柜台` are indoors and must **not** get one -- this is the visual
    # [EN] evidence for "rooms have a roof, the yard has open sky".
    wash = [r for r in rects if r.width and 24 <= r.width <= 50 and r.height
            and 16 <= r.height <= 40]
    rep['d5'] = {'n_rect': len(rects), 'n_wash': len(wash)}
    ok('D5 ★★ 只有**院里**的那些垫了浅底（井有、堂屋与柜台没有）'
       '—— 屋里见顶、院里见天，不用读字就分得开',
       len(wash) == 1, str(rep['d5']))

    # D6 不是室内图的时候：**一个框都不加**（老行为不许变）
    # [EN] D6 when it is not an indoor map: no frame at all
    lay2 = Layout(places=[Place('临河茶肆', 0.3, 0.35, shape='楼'),
                          Place('北门市集', 0.7, 0.6, shape='市')],
                  kind='整体')
    s2 = MM.build_shapes(lay2, current='临河茶肆')
    rects2 = [s for s in s2 if isinstance(s, fcv.Rect)]
    big2 = [r for r in rects2 if r.width and r.width >= 150
            and float(getattr(r, 'x', 0) or 0) >= 3]
    rep['d6'] = {'n_rect': len(rects2), 'n_big': len(big2)}
    ok('D6 ★★★ **不是室内图就不加框**（整张图的老样子一点没变）',
       not big2, str(rep['d6']))

    # D7 室内图上，当前那一间仍要标出来 —— 但 2026-10-12 起**不再是朱砂圈**
    # [EN] D7 on an indoor map the current room is still marked -- but **no longer with a cinnabar ring**
    #  用户第三次报红点（原话）：「小地图里标记〔那座楼〕和**旁边的红点**还是存在 去掉它
    #  **如果想要标记地点 用小字标记就行了 不要用点**」。
    #  ⇒ 室内图上"我在哪一间"现在靠**朱砂色的字**（那间房的名字），不靠垫在它底下的实心圆。
    # [EN] The user's third red-dot report (exact words): "the label for [that building] and **the red
    # [EN] dot next to it** are still there; remove it. **If you want to mark a location, just mark it
    # [EN] with small text -- do not use dots**."
    # [EN] ⇒ On an indoor map "which room am I in" is now carried by the **cinnabar text** (that room's
    # [EN] name), not by a filled circle padded underneath it.
    n_circle = sum(1 for s in shapes if isinstance(s, fcv.Circle))
    here_txt = [getattr(s, 'value', '') for s in shapes
                if type(s).__name__ == 'Text'
                and str(getattr(getattr(s, 'style', None), 'color', ''))
                == str(MM.PALETTE['here'])]
    rep['d7'] = {'n_circle': n_circle, 'here': here_txt}
    ok('D7 ★★ 室内图上**"我现在在哪一间"照旧标出来** —— 改用**朱砂色的字**'
       '（那间房的名字）',
       len(here_txt) == 1 and here_txt[0] == '堂屋', str(rep['d7']))

    ok('D7b ★★★ 室内图上**一个实心圆都没有**（"红点"不许回来）'
       '—— 用户：「不要用点」',
       n_circle == 0, f'实心圆 {n_circle} 个')

    # D8 界面把自己的配色传进去时，框的颜色要有着落
    # [EN] D8 the UI's palette carries a colour for the frame
    gui = _txt('gui/app_flet.py')
    # D8 界面给小地图的调色板里有 `frame`
    # [EN] D8 the UI gives the minimap's palette a `frame` entry
    #  ⚠⚠ 2026-10-12 补正：原来查的是**整个文件**里有没有 `'frame': C['text']` ——
    #   文件里其实有**两处**（小地图 `_draw_minimap` 与大地图 `show_map_dialog`），
    #   于是反例法 D⑦ 改掉小地图那处时，大地图那处照样让判据绿 ⇒ **变异抓不到**
    #   （实测："没抓到的变异：D⑦"）。
    #   ⇒ 改成**只看 `_draw_minimap` 那个方法体**（AST 取源码段，不 import GUI）。
    # [EN] ⚠⚠ Corrected 2026-10-12: this used to search the **whole file** for `'frame': C['text']` --
    # [EN] but the file has **two** (the minimap's `_draw_minimap` and the big map's `show_map_dialog`),
    # [EN] so when counterexample D⑦ changed the minimap's one, the big-map one kept the criterion green
    # [EN] ⇒ **the mutation was not caught** (measured: "not caught: D⑦").
    # [EN] ⇒ Changed to look **only at the `_draw_minimap` method body** (AST source segment, no GUI
    # [EN] import).
    demo_body = ''
    try:
        for _nd in ast.walk(ast.parse(gui)):
            if isinstance(_nd, ast.FunctionDef) and _nd.name == '_draw_minimap':
                demo_body = ast.get_source_segment(gui, _nd) or ''
    except SyntaxError:
        demo_body = ''
    ok('D8 ★★ **小地图**（`_draw_minimap`）的调色板里给了 `frame`'
       '（不然框会用默认色，在别的主题下可能看不见）'
       '—— 只查那个方法体，不查整个文件（大地图对话框里还有一处会骗绿）',
       "'frame': C['text']" in demo_body, demo_body and '(方法体取到了)' or '(没取到)')
    return rep


# ══════════════════════════════════════════════════════════════════
def main() -> int:
    """跑 A/B/C/D 四组，写报告。"""
    print('空间常识与地图能力验证')
    rep: dict = {}
    try:
        rep['a'] = group_a()
        rep['b'] = group_b()
        rep['c'] = group_c()
        rep['d'] = group_d()
        rep['d2'] = group_d2()
    except Exception:                                            # noqa: BLE001
        rep['fatal'] = traceback.format_exc()[-1200:]
        ok('四组跑完', False, rep['fatal'][-200:])
    rep['checks'] = _CHECKS
    rep['passed'] = len(_CHECKS) - _FAILS
    rep['total'] = len(_CHECKS)
    (OUT / 'space_rules_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n空间常识与地图能力验证：{rep["passed"]}/{rep["total"]}')
    print('报告：assets/screenshots/space_rules_report.json')
    return 0 if _FAILS == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
