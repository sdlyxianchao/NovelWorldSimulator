# -*- coding: utf-8 -*-
"""验证：**场景切换 → 存一张大地图 → 导出按场景插图**（用户 2026-10-22 一次点名四件事）。

用户原话
--------
「场景切换的时候需要重新绘制地图 且场景切换在剧作家写作 导演导戏过程中知道
 且场景切换应该是一个明确的动作并引发地图重绘」
「所有地图（小地图和大地图）都需要按照场景保存下来」
「后续导出小说的时候每个场景都需要插入大地图并带有简单描述」

判据分四组
----------
  S **换场就存图**：调产品自己的 `_save_scene_plate`，图与清单真的落盘；
    清单字段齐全；同一天同一场**覆盖**不追加；
    `record=False`（只是"当天的图画好了"的重画通知）**不存图**
  T **图画得出来**：SVG 是**合法 XML**、形状与文字真在里面、
    所有文字落在画布内（不是"存了一个空文件"
    —— 那种错在导出里只表现为"图是空白的"，没人会去查）
  U **取图口径与界面一致**：当天地图里有这一处就用它；
    没有就退"只画这一处"，而且描述里**必须说明是简化排布**
  V **导出按场景插图**：可读稿里有 `../场景地图/…` 图片行与一句描述；
    没有存档时**不许**插一个空块；两档（可读稿/素材册）插图一致
    （否则"只删不加"的子集判据会红，而它红得对）
  W **新地点登记**：剧作家写的「河岸柳树下」会被登记（否则换场被静默拒绝，
    地图永远是开头那一张 —— 用户第 3 问就是这个）；「门外」「对面」这类场面话
    不登记；本轮上限 12 个

跑法：
    .venv\\Scripts\\python.exe tools\\verify_scene_maps.py
产出：assets/screenshots/scene_maps_report.json

English:
Verification: **scene change -> save one big map -> insert per scene on export** (four things the
user named on 2026-10-22 at once).
Groups: S a scene change really saves the image and the manifest (same day + index overwrites,
`record=False` does not save); T the image is real (well-formed XML, shapes and text inside the
canvas, all text within bounds); U the layout choice matches the UI (day map when it contains the
place, otherwise "only this place" and the description **says it is a simplified layout**);
V the export carries one image line and one description per scene, inserts nothing when there is no
archive, and both volumes get the same block; W a playwright-written place like "riverbank under the
willow" is registered (otherwise the switch is silently refused and the map never changes) while
stage talk like "outside the door" is not, capped at 12 per round.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

import json as _json                                            # noqa: E402

from image_gen import map_layout as ML                          # noqa: E402
from image_gen import scenemap as SM                            # noqa: E402
from sim import loop as LP                                      # noqa: E402

report: dict = {'checks': []}
_checks: list = []


def ok(name: str, cond, detail='') -> bool:
    _checks.append((name, bool(cond), str(detail)))
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _project_layout():
    """拿一份**真实存档**的布局（主地点 + 室内外 + 8 条通路）。

    ★ 用真实存档而不是手搓夹具：手搓的布局不会带 `walls`/`links` 这些细节，
      于是"图例里有没有通路""房间墙画没画"这类判据就成了自欺。
    """
    # ⚠ 2026-10-26：**不写死某本书的目录名**。判据要的是"一份真实存档的布局"，
    #   不是"那一本书的布局" —— 用通配取到第一份就是同一件事，而且换台机器/改了书名
    #   也不会因为路径不存在而整支跳过（跳过 = 这条判据静默失效）。
    # [EN] ⚠ Do not hardcode one book's directory name. The criterion wants "the layout of a
    # [EN] real archive", not "that book's layout" -- taking the first match is the same thing,
    # [EN] and it survives a rename instead of silently skipping the whole check.
    # ⚠ 2026-10-26 再修一次：原来 glob 的是 `*/地图/*.json`（**只一层**）。
    #   而 2026-10-26 那次地图改造把旧锚定归档进了 `地图/_旧锚定（…）/` 子目录，
    #   于是这份"真实存档"取不到了 ⇒ 前提判据变红，整组少跑一大截（9/10）。
    #   ⇒ 用 `rglob` 把子目录一起找。归档与否不该影响判据能不能拿到真数据。
    # [EN] ⚠ Fixed again 2026-10-26: the glob was `*/地图/*.json` (**one level only**), and the map
    # [EN] rework that day archived the old anchors into a `地图/_旧锚定（…）/` subdirectory, so the
    # [EN] "real archive" could not be found => the precondition went red and a big chunk of the
    # [EN] group never ran (9/10). => `rglob` includes subdirectories; archiving must not decide
    # [EN] whether a criterion gets real data.
    # ⚠ 2026-10-27 第三次修：整支判据曾经**只认一个根目录**
    #   （`C:/小说世界AI模拟/项目`）。那个目录是用户自己的，随时可能被清空/搬走 ——
    #   实测 2026-10-27 它就是空的 ⇒ "拿得到真实存档"这条前提变红 ⇒ 整组少跑一截。
    #   ★ 判据要的是"**一份**真实存档"，不是"**那一处**的存档"
    #     ⇒ 列几个**都是真跑出来的**候选根，取第一份能解析的即可。
    #   [EN] ⚠ Third fix, 2026-10-27: the check used to accept **one single root**
    #   [EN] (`C:/小说世界AI模拟/项目`). That directory belongs to the user and can be emptied or
    #   [EN] moved at any time -- on 2026-10-27 it was in fact empty, so the "real archive
    #   [EN] available" precondition went red and a chunk of the group never ran.
    #   [EN] ★ What the check wants is "**a** real archive", not "the archive in **that** place"
    #   [EN] => list several candidate roots that are all genuinely produced by real runs and take
    #   [EN] the first one that parses.
    _APP = Path(__file__).resolve().parent.parent
    _ROOTS = (
        Path('C:/小说世界AI模拟/项目'),                              # 用户自己的项目（优先）
        _APP / 'novel_bench' / 'results' / '.work' / 'projects',    # 回归真跑出来的存档
        _APP / 'assets' / 'screenshots' / '场景地图样例',            # 随发行包带的样例
    )
    cands: list[Path] = []
    for r in _ROOTS:
        try:
            if not r.exists():
                continue
            cands += sorted(r.rglob('地图/**/*.json'))
            cands += sorted(r.rglob('场景地图/*.json'))
        except OSError:                                          # noqa: PERF203
            continue
    for f in cands:
        try:
            raw = _json.loads(f.read_text(encoding='utf-8'))
            lay = ML.Layout.from_dict(raw['布局'])
        except Exception:                                       # noqa: BLE001
            continue
        if getattr(lay, 'places', None):
            return lay
    return None


#: **主地点名从真实布局里取**（`note` 标着「（这里）」的那一处）。
#: ★ 2026-10-26：以前这里写死了一个楼名。那是**某本书的专名**，既违反
#:   "程序必须通用"，也会在读不到那本存档时让整支判据静默失效（找不到就叫不到取景）。
#:   现在改成"用手里这份布局的主地点"—— 判据问的是"取景用的是不是当天地图里那一处"，
#:   跟那处叫什么名字无关。
# [EN] **The main place name comes from the real layout** (the entry whose `note` says "here").
# [EN] ★ 2026-10-26: this used to hardcode a building name. That is **one specific book's proper
# [EN] noun** (the program must stay generic), and when that archive is missing the whole check
# [EN] silently goes quiet. Now it uses the main place of whatever layout it has -- the question is
# [EN] "does the plate use the place that is on today's map", not what that place is called.


#: 本次跑的"主地点"（`main()` 里按真实布局算出来，见 `_main_place`）
PLACE = '主地点'


def _main_place(lay) -> str:
    places = list(getattr(lay, 'places', None) or [])
    for pl in places:
        if '（这里）' in str(getattr(pl, 'note', '') or ''):
            return str(pl.name)
    return str(places[0].name) if places else '主地点'


class _World:
    game_day = 1
    scene_desc = '雾还没散，河岸的泥地被踩得稀烂，柳枝垂到水面上。'


class _Run:
    def __init__(self, root: Path, project_dir: Path | None = None):
        self.root = root
        # ★ 2026-10-22：`_persist_place` 走的是 `runfolder.project_dir`（项目的设定集在
        #   `<project>/设定集/`，不是运行文件夹里的 `本地设定集`）。
        # [EN] ★ 2026-10-22: `_persist_place` uses `runfolder.project_dir` (the project's settings
        # [EN] live in `<project>/设定集/`, not the run folder's `本地设定集`).
        self.project_dir = project_dir


class _Loop:
    # 借**产品自己**的那几个方法（判据要测的就是产品，不是复制品）
    _save_scene_plate = LP.RunLoop._save_scene_plate
    _register_place = LP.RunLoop._register_place
    # ★ 2026-10-22：`_register_place` 现在会写盘（`PLACE_PERSIST`），
    #   所以夹具也必须有这个方法 —— 不借过来就是 `AttributeError`，
    #   而那种崩会被 `except` 吞成"没登记"（看着像产品坏了）。
    # [EN] ★ 2026-10-22: `_register_place` now writes to disk (`PLACE_PERSIST`), so the fixture needs
    # [EN] this method too -- without it an `AttributeError` gets swallowed as "not registered",
    # [EN] which looks like a product bug.
    _persist_place = LP.RunLoop._persist_place
    _PLACE_STOPWORDS = LP.RunLoop._PLACE_STOPWORDS

    def __init__(self, runfolder: Path, day_map=None, place_names=None,
                 project_dir: Path | None = None):
        self.runfolder = _Run(runfolder, project_dir)
        self.day_map = day_map
        self.world = _World()
        self.world.place_names = list(place_names or [])

    def _push_narrative(self, *_a, **_kw):                      # 假实现：只吞掉
        return None

    def _warn_once(self, *_a, **_kw):
        return None


def group_s(tmp: Path, lay) -> None:
    print('\n【S】换场就存一张场景图 + 清单', flush=True)
    lo = _Loop(tmp / 's', day_map=lay)
    lo._save_scene_plate(PLACE, '辰时 08:00')
    lo._save_scene_plate('河岸柳树下', '巳时 10:20')
    d = SM.dir_of(lo.runfolder)
    svgs = sorted(d.glob('*.svg')) if d else []
    rows = SM.load_manifest(lo.runfolder)
    ok('S1 ★★★ 换一次场就落一张图 + 清单加一行（用户：「按场景保存下来」）',
       len(svgs) == 2 and len(rows) == 2,
       f'图 {[p.name for p in svgs]} · 清单 {len(rows)} 行')
    need = {'天', '场次', '地点', '时辰', '图', '描述'}
    ok('S2 ★★ 清单每行字段齐全（天/场次/地点/时辰/图/描述）—— 导出全靠它',
       bool(rows) and all(need <= set(r) for r in rows),
       f'缺={[sorted(need - set(r)) for r in rows][:2]}')
    ok('S3 ★★ 图名带**补零**的天与场次（`第001天_第01场_…`，字典序=时间序）',
       [p.name for p in svgs] == [SM.plate_name(1, 1, PLACE),
                                  SM.plate_name(1, 2, '河岸柳树下')],
       str([p.name for p in svgs]))

    # 同一天同一场再记一次 → 覆盖，不追加
    lo._scene_no = 1
    lo._save_scene_plate(PLACE, '辰时 08:00')
    ok('S4 ★★ 同一天同一场再存一次**覆盖**（不追加）—— 否则一天会记出十几个"场景"',
       len(SM.load_manifest(lo.runfolder)) == 2,
       f'{len(SM.load_manifest(lo.runfolder))} 行')

    # record=False（"当天的图画好了"的重画通知）**不许**存图
    src = (APP / 'sim' / 'loop.py').read_text(encoding='utf-8')
    seg = src[src.index('    def _push_scene('):]
    seg = seg[:seg.index('\n    def ', 10)]
    _inside_record = seg[seg.index('if record:'):seg.index('if not self._on_scene')]
    # 行为级：`record=False` 调一次 `_push_scene`，**不许**多出一张图
    # [EN] Behaviour level: call `_push_scene` with `record=False`; **no extra image may appear**.
    lo5 = _Loop(tmp / 's5', day_map=lay)
    lo5._save_scene_plate = LP.RunLoop._save_scene_plate.__get__(lo5, type(lo5))
    lo5._push_scene = LP.RunLoop._push_scene.__get__(lo5, type(lo5))
    lo5._review_record_only = lambda *a, **k: None
    lo5._on_scene = None
    lo5._scene_no = 0
    lo5._push_scene(place=PLACE, segment='辰时', record=False)
    n_after = len(SM.load_manifest(lo5.runfolder))
    ok('S5b ★★★ 只当"重画通知"（`record=False`）时**不存图** —— '
       '否则同一场会在导出里出现两次',
       n_after == 0, f'存了 {n_after} 张')

    ok('S5 ★★★ 存图挂在 `record=True` 那个分支里（`record=False` 只是重画通知，'
       '在那里存图会把同一场记两遍）—— **判产品源码**',
       '_save_scene_plate' in _inside_record,
       f'该分支里出现 `_save_scene_plate`={"_save_scene_plate" in _inside_record}')


def group_t(tmp: Path, lay) -> None:
    print('\n【T】图画得出来（不是空文件）', flush=True)
    lo = _Loop(tmp / 't', day_map=lay)
    lo._save_scene_plate(PLACE, '辰时 08:00')
    f = SM.dir_of(lo.runfolder) / SM.plate_name(1, 1, PLACE)
    txt = f.read_text(encoding='utf-8') if f.is_file() else ''
    try:
        root = ET.fromstring(txt)
        parsed = True
    except Exception:                                           # noqa: BLE001
        root = None
        parsed = False
    ns = '{http://www.w3.org/2000/svg}'
    texts = root.findall(f'.//{ns}text') if root is not None else []
    shapes = ([e for e in root.iter() if e.tag in (f'{ns}rect', f'{ns}line',
                                                   f'{ns}path', f'{ns}circle',
                                                   f'{ns}ellipse')]
              if root is not None else [])
    ok('T1 ★★★ 场景图是**合法 SVG/XML**（解析得开），不是半截文件',
       parsed and txt.endswith('</svg>'), f'{len(txt)} 字节')

    ok('T2 ★★★ 图里**真的有**形状与文字（≥30 个形状、≥8 条文字）'
       '—— 空壳在导出里只表现成"图是空白的"，没人会去查',
       len(shapes) >= 30 and len(texts) >= 8,
       f'形状 {len(shapes)} · 文字 {len(texts)}')

    # 每一条文字都要落在画布内（越界 = 被裁掉，而 SVG 不会报错，只会"看不见"）
    out = []
    for t in texts:
        try:
            x, y = float(t.get('x')), float(t.get('y'))
        except (TypeError, ValueError):
            continue
        if not (0 <= x <= LP.PLATE_W and 0 <= y <= LP.PLATE_H):
            out.append((x, y, (t.text or '')[:8]))
    ok('T3 ★★★ 所有文字都在画布内（越界的字会被裁掉、**且不报错**，只是看不见）',
       not out, str(out[:3]))

    names = ' '.join((t.text or '') for t in texts)
    ok('T4 ★★ 图上写着**地点**与**比例尺**（大地图该有的基本信息）',
       PLACE in names and '比例尺' in names, names[:60])


def group_u(tmp: Path, lay) -> None:
    print('\n【U】取图口径与界面一致 + 描述照实说', flush=True)
    # ① 当天地图里**有**这一处
    lo1 = _Loop(tmp / 'u1', day_map=lay)
    lo1._save_scene_plate(PLACE, '辰时 08:00')
    r1 = SM.load_manifest(lo1.runfolder)
    ok('U1 ★★ 当天地图里有这一处 → 用当天地图取景（多处更有信息量）',
       bool(r1) and r1[0]['来源'].startswith('当天地图'),
       str(r1[0]['来源']) if r1 else '（没记）')
    # ② 当天地图里**没有**这一处
    lo2 = _Loop(tmp / 'u2', day_map=lay)
    lo2._save_scene_plate('河岸柳树下', '巳时 10:20')
    r2 = SM.load_manifest(lo2.runfolder)
    ok('U2 ★★★ 当天地图里没有这一处 → 退"只画这一处"，'
       '而且描述里**明说是简化排布**（不许让人以为那是量过的实测图）',
       bool(r2) and '简化排布' in r2[0]['来源'],
       str(r2[0]['来源']) if r2 else '（没记）')
    ok('U3 ★★ 描述里**只写这一场看见什么**（时辰/地点另有字段，不重复堆在一句里）',
       bool(r2) and '河岸柳树下' not in r2[0]['描述'],
       str(r2[0]['描述']) if r2 else '')


def group_v(tmp: Path, lay) -> None:
    print('\n【V】导出按场景插图', flush=True)
    # 造一个最小运行文件夹：一天的正文 + 两张场景图
    from store.runfolder import RunFolder
    run = RunFolder(tmp / 'v', '第1次模拟')
    run.root.mkdir(parents=True, exist_ok=True)
    lo = _Loop(run.root, day_map=lay)
    lo._save_scene_plate(PLACE, '辰时 08:00')
    lo._save_scene_plate('河岸柳树下', '巳时 10:20')
    (run.root / '每天的生活').mkdir(parents=True, exist_ok=True)
    (run.root / '每天的生活' / '第001天.md').write_text(
        '# 第 1 天 · 辰时 · 晴\n\n阿九在灶间喝了碗粥，随后往河岸去。\n',
        encoding='utf-8')

    from export import novel_version as NV
    body = NV.scene_plate_block(run, 1)
    joined = '\n'.join(body)
    ok('V1 ★★★ 导出的场景图版里**每个场景一段**：`![地图 …]` + 一句描述',
       joined.count('../场景地图/') == 2 and joined.count('> ') >= 2,
       f'图片行 {joined.count("![")} · 描述行 {joined.count("> ")}')
    ok('V2 ★★ 图片路径是**相对**的（`../场景地图/…`）—— 整个运行文件夹搬走后图不能断',
       '../场景地图/' in joined and str(run.root) not in joined, '')

    novel = NV.render_manuscript(run, mode=NV.MODE_NOVEL)['body']
    ref = NV.render_manuscript(run, mode=NV.MODE_REFERENCE)['body']
    ok('V3 ★★★ 两档（可读稿/素材册）插图**一致**'
       '（"只删不加"的子集判据才能成立）',
       novel.count('../场景地图/') == ref.count('../场景地图/') == 2,
       f'可读稿 {novel.count("../场景地图/")} · 素材册 {ref.count("../场景地图/")}')

    # 没有存档时**不许**插空块
    run2 = RunFolder(tmp / 'v2', '第1次模拟')
    run2.root.mkdir(parents=True, exist_ok=True)
    ok('V4 ★★★ 没有场景图存档时**一条都不插**（不编一张图、不留空块）',
       NV.scene_plate_block(run2, 1) == [], '')


def group_w(tmp: Path) -> None:
    print('\n【W】新地点登记（这就是"府城/大柳树"能不能出图的前提）', flush=True)
    lo = _Loop(tmp / 'w', place_names=[PLACE])
    got = lo._register_place('河岸柳树下·夜')
    ok('W1 ★★★ 剧作家写的「河岸柳树下·夜」→ 登记成「河岸柳树下」'
       '（不登记的话换场被静默拒绝、地图永远是开头那一张）',
       got == '河岸柳树下' and '河岸柳树下' in lo.world.place_names, got)
    bad = [w for w in ('门外', '对面', '屋里', '原处')
           if lo._register_place(w)]
    ok('W2 ★★★ 场面话**不登记**（「门外」「对面」「屋里」「原处」）——'
       ' 它们一旦成为场景名，一场戏会被切得七零八落（有前科）',
       not bad, str(bad))
    long_name = lo._register_place('他站在河岸上看水的那块地方')
    ok('W3 ★★ 太长的（>8 字）不登记 —— 多半是一句话，不是地名', long_name == '',
       long_name)
    lo2 = _Loop(tmp / 'w2', place_names=[PLACE])
    for i in range(14):
        lo2._register_place(f'地方{i}')
    ok('W4 ★★ 本轮最多登记 12 个（失控时宁可停，也别把地点表灌满）',
       len([n for n in lo2.world.place_names if n != PLACE]) == 12,
       str(len(lo2.world.place_names) - 1))

    # ══════════════════════════════════════════════════════════════
    #  W6~W9 ★★★ 「改成长期用」：真的写进 `<项目>/设定集/地点.yaml`
    #
    #  用户 2026-10-22：「改成长期用」。不写盘的话，下一轮开卷重新装配，
    #  这个地点又变成不认识 —— 换场被静默拒绝、地图又卡在开头那一张。
    #
    #  ⚠ 这是**动用户的创作文件**，所以四条都要判，缺一条都可能伤到人：
    #    ① 追加成功、**原内容逐字保留**（作者手写的注释、引号、空行都在）；
    #    ② 写之前留了**备份**；
    #    ③ 同一个名字**不重复追加**；
    #    ④ 文件结构不是"- 名称:"那种列表时，**一个字节都不动**（宁可这轮临时用）。
    # [EN] W6~W9 "make it permanent": really append to `<project>/设定集/地点.yaml`.
    # [EN] ⚠ This touches the author's creative file, so all four are judged: ① appended and the
    # [EN] original text **preserved verbatim** (hand-written comments, quotes, blank lines);
    # [EN] ② a **backup** was written first; ③ the same name is **not appended twice**; ④ when the
    # [EN] file is not a "- 名称:" block sequence, **not a single byte changes**.
    # ══════════════════════════════════════════════════════════════
    _orig = ('# 作者手写的注释：这一行必须留着\n'
             '- 名称: ' + PLACE + '\n'
             '  说明: 茶楼，日市夜市，掌柜擦壶话少\n'
             "  方位: ''\n"
             '  内里:\n'
             '  - 后厨\n'
             '  - 天井\n')
    proj = tmp / 'w_persist'
    (proj / '设定集').mkdir(parents=True, exist_ok=True)
    pfile = proj / '设定集' / '地点.yaml'
    pfile.write_text(_orig, encoding='utf-8')
    lo6 = _Loop(tmp / 'w6', day_map=None, place_names=[PLACE], project_dir=proj)
    # ⚠⚠ 这里必须走**用户路径** `_register_place`，不能直接调 `_persist_place`：
    #   反例法那一刀打的是 `_register_place` 里那句 `if CFG.b('PLACE_PERSIST')`
    #   —— 直接调 `_persist_place` 等于绕过变异点，那一刀会"白跑"
    #   （实测：第一版就是这样，W6 照绿）。
    #   判据要测**用户看到的行为**（"登记了新地点，下次开卷还认它"），
    #   而不是某个内部函数有没有被调到。
    # [EN] ⚠⚠ This must go through the **user-facing path** `_register_place`, not call
    # [EN] `_persist_place` directly: the counterexample mutates the `if CFG.b('PLACE_PERSIST')` line
    # [EN] inside `_register_place`, so calling `_persist_place` bypasses the mutation point and that
    # [EN] knife becomes a no-op (measured: the first version did exactly this and W6 stayed green).
    # [EN] Judge the **behaviour the user sees** ("registered a new place; the next book-opening still
    # [EN] knows it"), not "was some internal function called".
    try:
        from config import CFG as _CFG6
        _CFG6.set('PLACE_PERSIST', 'true')
    except Exception:                                   # noqa: BLE001
        pass
    got6 = lo6._register_place('河岸柳树下')
    after6 = pfile.read_text(encoding='utf-8') if pfile.is_file() else ''
    ok('W6 ★★★ 新地点**真的写进了设定集**，而且**原内容逐字保留**'
       '（作者手写的注释/引号/空行一个字都不许动）—— 用户：「改成长期用」',
       got6 and _orig.rstrip('\n') in after6
       and after6.count('- 名称:') == 2 and '# 作者手写的注释' in after6,
       f'写入={got6} · 条数={after6.count("- 名称:")}')

    baks = list(pfile.parent.glob('*.bak-新地点-*'))
    ok('W7 ★★★ 写进设定集**之前留了备份**（这是作者的创作文件，不能裸写）',
       bool(baks), str([b.name for b in baks][:2]))

    n_before = after6.count('- 名称:')
    lo6._persist_place('河岸柳树下')
    n_after = pfile.read_text(encoding='utf-8').count('- 名称:')
    ok('W8 ★★ 同一个名字**不重复追加**（同一轮多次换场到那里只留一条）',
       n_after == n_before, f'{n_before} → {n_after}')

    # ④ 结构不是列表 ⇒ 一个字节都不动
    proj2 = tmp / 'w_bad'
    (proj2 / '设定集').mkdir(parents=True, exist_ok=True)
    pfile2 = proj2 / '设定集' / '地点.yaml'
    _bad = PLACE + ':\n  说明: 作者写成了字典\n'
    pfile2.write_text(_bad, encoding='utf-8')
    lo7 = _Loop(tmp / 'w7', project_dir=proj2)
    got7 = lo7._persist_place('河岸柳树下')
    ok('W9 ★★★ 设定集不是「- 名称:」那种列表结构时**一个字节都不动**'
       '（宁可这一轮临时用，也不许把作者的文件改坏）',
       not got7 and pfile2.read_text(encoding='utf-8') == _bad,
       f'返回={got7} · 文件未变={pfile2.read_text(encoding="utf-8") == _bad}')

    # ⚠ 这一条**不能读源码**：`_known_places()` 的说明文字里就写着 `world.place_names`，
    #   把实现改成不并入（`for x in []`）也照样"文本里有那几个字" ⇒ 恒绿。
    #   实测过：第一版就是读源码，反例法打上去 **一条都没红**。
    #   ⇒ 改成**行为级**：造一个只认识主地点的 world，登记一个新地点，看白名单里有没有它。
    # [EN] ⚠ This must **not read the source**: the docstring of `_known_places()` itself mentions
    # [EN] `world.place_names`, so an implementation that does not merge (`for x in []`) still "has
    # [EN] those words" => permanently green. Measured: the first version read the source and the
    # [EN] counterexample turned **nothing** red. => Behaviour level: build a world that knows only
    # [EN] Mowen Tower, register a new place, and see whether the whitelist contains it.
    lo3 = _Loop(tmp / 'w3', place_names=[PLACE])
    lo3.world.worldview_text = '【地点】' + PLACE
    lo3._known_places = LP.RunLoop._known_places.__get__(lo3, type(lo3))
    lo3._register_place('河岸柳树下')
    names = lo3._known_places()
    ok('W5 ★★★ 取景白名单 `_known_places()` **真的并进了新登记的地点**'
       '（换场与取景用同一份名单 —— 两份必然漂；判行为，不判源码文本）',
       '河岸柳树下' in names, str(names[:4]))


def main() -> int:
    global PLACE
    lay = _project_layout()
    ok('前提：拿得到一份**真实存档**的布局（判据用真数据，不用手搓夹具）',
       lay is not None, '' if lay is None else f'{len(getattr(lay, "places", []) or [])} 处')
    PLACE = _main_place(lay) if lay is not None else '主地点'
    tmp = Path(tempfile.mkdtemp(prefix='nws_scene_maps_'))
    try:
        if lay is not None:
            group_s(tmp, lay)
            group_t(tmp, lay)
            group_u(tmp, lay)
            group_v(tmp, lay)
        group_w(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [c for c in report['checks'] if not c['ok']]
    out = APP / 'assets' / 'screenshots' / 'scene_maps_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  场景地图验证：{len(report["checks"]) - len(bad)}/{len(report["checks"])}'
          + ('' if not bad else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
