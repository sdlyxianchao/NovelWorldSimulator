# -*- coding: utf-8 -*-
"""验证：**影视镜头卡**（`FILM_MODE` / `DISPLAY_FILM_CARDS`，设计稿 §10.8）
＋ **风格来源**（`NOVEL_STYLE` / `NOVEL_STYLE_CUSTOM`）与**本幕提示**
（`SCENE_START_HINT`）。

用户 2026-10-06：「继续全做完」。这五个旋钮以前**一个都没人读** ——
"以后拿去拍剧"在程序里不存在；作者在书斋挑的风格来源推演时一个字都没变。

判据分层（每层都要能红，见 `developers/mutate_film_style.py`）：
  A **镜头卡**：机位随**人数**变、拍法随**动/静**变、视角随**心声**变、
     灯光随**时辰/天气**变；`parse_card` 能拆回来。
  B **接线**：`FILM_MODE` 关着一律不产；开着就落 `分镜表.md`；
     `DISPLAY_FILM_CARDS` 只决定"写不写进正文"，**不影响分镜表**。
  C **风格来源**：`plain` 不写风格、`custom` 用手写文本（空要明说）、
     其它取值当风格名、`auto` 走风格卡；**改了要立刻生效**（缓存指纹）。
  D **本幕提示**：非空才进 prompt。
  E **落盘**：`Project.style_custom` 能写进 `.nwsproj` 也能读回来。

用法：.venv\\Scripts\\python.exe tools/verify_film_style.py
产出：assets/screenshots/film_style_report.json

English:
Verification: **film shot card** (`FILM_MODE` / `DISPLAY_FILM_CARDS`, design doc §10.8)
+ **style source** (`NOVEL_STYLE` / `NOVEL_STYLE_CUSTOM`) and **current-scene hint**
(`SCENE_START_HINT`).
User 2026-10-06: "Go ahead and finish it all." These five knobs previously had **not a single
reader** --
"later use it to shoot a drama" did not exist in the program; the style source the author picked
in the study did not change a single character during inference.
Criteria layered (each layer must be able to go red, see `developers/mutate_film_style.py`):
  A **shot card**: camera position changes with **number of people**, shooting method changes with **motion/stillness**, perspective changes with **inner voice**,
     lighting changes with **time of day/weather**; `parse_card` can parse it back.
  B **Wiring**: `FILM_MODE` off produces nothing at all; on writes `分镜表.md`;
     `DISPLAY_FILM_CARDS` only decides "whether to write into the body text", **does not affect the storyboard table**.
  C **Style source**: `plain` writes no style, `custom` uses handwritten text (empty must be stated explicitly),
     other values are treated as style names, `auto` uses the style card; **changes must take effect immediately** (cache fingerprint).
  D **Current-scene hint**: enters the prompt only if non-empty.
  E **Write to disk**: `Project.style_custom` can be written into `.nwsproj` and read back.
Usage: .venv\\Scripts\\python.exe tools/verify_film_style.py
Output: assets/screenshots/film_style_report.json
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
# ⚠ 不量像素、不弹窗、**绝不点会 `CFG.save()` 的按钮**（MEMORY 的铁律）。
# [EN] ⚠ Do not measure pixels, do not pop up dialogs, **never click a button that calls `CFG.save()`**
# [EN] (an iron rule of MEMORY).
CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


class E:
    """最小词条桩（`display/script` 那套只要 `who/kind/text`）。
        English:
    Minimal entry stub (the `display/script` set only needs `who/kind/text`).
    """

    def __init__(self, who='', kind='speak', text=''):
        self.who, self.kind, self.text = who, kind, text


def make_world(scene='临河茶肆', weather='晴', seg_day=1):
    from world.state import WorldState, GameTime
    w = WorldState()
    w.scene = scene
    w.weather = weather
    w.clock = GameTime()
    w.clock.day = seg_day
    return w


# ══════════════════════════════════════════════════════════════
#  A. 镜头卡本身
# [EN] A. The shot card itself
# ══════════════════════════════════════════════════════════════
def test_card() -> bool:
    ok = True
    from display import film as F
    w = make_world()

    def kind_of(entries):
        return F.parse_card(F.shot_card(entries, w, place='临河茶肆')).get('kind', '')

    k1 = kind_of([E('甲', 'speak', '甲说：嗯。')])
    k2 = kind_of([E('甲', 'speak', '甲说：嗯。'), E('乙', 'speak', '乙说：哦。')])
    k4 = kind_of([E(x, 'speak', f'{x}说：嗯。') for x in ('甲', '乙', '丙', '丁')])
    ok &= rec('A1 ★★ 机位随**画面里有几个人**变（1 人近景 / 2 人中景 / 4 人大全景）',
              k1 != k2 and k2 != k4 and '近景' in k1 and '中景' in k2,
              f'{k1} / {k2} / {k4}')

    m_still = F.parse_card(F.shot_card([E('甲', 'speak', '甲坐着没动')], w)).get('move')
    m_move = F.parse_card(F.shot_card([E('甲', 'speak', '甲走去门口')], w)).get('move')
    ok &= rec('A2 ★★ 拍法随**动/静**变（坐着不动=固定，走去门口=缓推）',
              '固定' in m_still and '缓推' in m_move, f'{m_still} / {m_move}')

    p_subj = F.parse_card(F.shot_card(
        [E('甲', 'aside', '甲心想：怪。')], w)).get('pov')
    p_obj = F.parse_card(F.shot_card([E('甲', 'speak', '甲说：嗯。')], w)).get('pov')
    ok &= rec('A2 ★ 视角随**有没有心声**变（心声=主观，纯对白=客观）',
              '主观' in str(p_subj) and '客观' in str(p_obj), f'{p_subj} / {p_obj}')

    w_rain = make_world(weather='雨')
    l_dry = F.parse_card(F.shot_card([E('甲')], w)).get('light', '')
    l_rain = F.parse_card(F.shot_card([E('甲')], w_rain)).get('light', '')
    ok &= rec('A3 ★ 灯光带**天气**（雨天反光）', '雨天反光' in l_rain and '雨天反光' not in l_dry,
              f'{l_dry} / {l_rain}')

    w3 = make_world()
    w3.clock.segment = lambda: '入夜'
    ok &= rec('A3 ★ 灯光带**时辰**（入夜=暖黄·单烛）',
              '暖黄' in F.parse_card(F.shot_card([E('甲')], w3)).get('light', ''),
              F.parse_card(F.shot_card([E('甲')], w3)).get('light', ''))

    card = F.shot_card([E('甲'), E('乙')], w, place='临河茶肆')
    ok &= rec('A4 ★ 卡片是设计稿那一行的形状（【镜头】+ 五段）',
              card.startswith('【镜头】')
              and all(k in card for k in ('机位：', '拍法：', '视角：', '出场：', '灯光：')),
              card)
    row = F.parse_card(card)
    ok &= rec('A4 ★ `parse_card` 能把卡片拆回结构化（分镜表要用）',
              row.get('kind') and row.get('move') and row.get('people') == ['甲', '乙'],
              str(row))
    md = F.storyboard_md([dict(row, day=1, clock='第1天·辰时', line='一句')])
    # ★ 2026-10-10：镜头表按外部调研（PenShot / Pixelle-Video）升级成**有界可校验对象**
    #   —— 原来的「机位」一栏拆成 **景别 / 角度**，并补上 **时长 / 转场** 两栏。
    #   所以这里改成判**属性**（"是表格 + 该有的列都在 + 地点在 + 带校验结论"），
    #   不再钉一行会随需求变化的表头字符串
    #   —— 钉死表头的判据会在每次正当的列变更时假红，那种红没有信息量。
    # [EN] ★ 2026-10-10: The shot table is upgraded based on external research (PenShot / Pixelle-Video)
    # [EN] into a **bounded, verifiable object**
    # [EN] -- The original "camera position" column is split into **shot size / angle**, and two columns
    # [EN] **duration / transition** are added.
    # [EN] So here it is changed to judging **attributes** ("is a table + all expected columns are present
    # [EN] + the location is present + has a verification conclusion"),
    # [EN] no longer pinning a header string that changes with requirements
    # [EN] -- A criterion that pins the header will falsely go red on every legitimate column change, and
    # [EN] that kind of red carries no information.
    _cols = ('场次（天）', '时间', '地点', '出场', '景别', '角度', '运镜',
             '视角', '时长', '转场', '灯光', '内容一句')
    ok &= rec('A4 ★ `storyboard_md` 出的是表格，且**该有的列都在**'
              '（景别/角度/运镜/时长/转场 是 2026-10-10 按调研补上的）',
              '# 分镜表' in md and md.count('|') > 20
              and all(f' {c} ' in md for c in _cols) and '临河茶肆' in md,
              md[:150])
    ok &= rec('A4 ★★ 分镜表**自带校验结论**（一份没人核过的分镜表和没有是一样的）',
              '校验' in md and '得分' in md, '')
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 接线
# [EN] B. Wiring
# ══════════════════════════════════════════════════════════════
def test_wiring() -> bool:
    ok = True
    from display import film as F
    from sim.loop import RunLoop

    tmp = Path(tempfile.mkdtemp(prefix='nws_film_'))

    class RunF:
        root = tmp

    loop = RunLoop.__new__(RunLoop)
    loop.world = make_world()
    loop.runfolder = RunF()
    loop._film_cards = []
    loop._builder = None
    loop._daily_narrative = ['甲说：嗯。']
    loop._cb_warned = set()
    loop._status = lambda *a, **k: None
    lines: list[str] = []
    loop._on_narrative = lambda text, pri, kind='': lines.append((text, kind))

    class Disp:
        async def enqueue_narrative(self, *a, **k):
            pass

    loop.display = Disp()

    saved = (CFG.raw('FILM_MODE'), CFG.raw('DISPLAY_FILM_CARDS'))
    try:
        # ① 关着一律不产
        # [EN] ① When off, produce nothing at all
        CFG.set('FILM_MODE', 'false')
        ok &= rec('B1 ★★ `FILM_MODE=false` → 既不产卡也不写分镜表（旋钮真被读）',
                  F.should_show() is False
                  and loop._film_header_of_day([]) == ''
                  and not (tmp / '分镜表.md').exists(),
                  str(list(tmp.iterdir())))

        # ② 开着 + 显示 → 正文头非空、分镜表落盘
        # [EN] ② When on + display -> body head is non-empty, storyboard table is written to disk
        CFG.set('FILM_MODE', 'true')
        CFG.set('DISPLAY_FILM_CARDS', 'true')
        hdr = loop._film_header_of_day([])
        ok &= rec('B2 ★★ `FILM_MODE=true` → 落 `分镜表.md`',
                  (tmp / '分镜表.md').exists(), str(list(tmp.iterdir())))
        ok &= rec('B2 ★★ `DISPLAY_FILM_CARDS=true` → 镜头卡**写进正文段首**',
                  hdr.startswith('【镜头】'), hdr[:80])
        ok &= rec('B2 ★ 卡也收进了 `_film_cards`（一份来源，别写三处）',
                  len(loop._film_cards) == 1, str(len(loop._film_cards)))

        # ③ 关掉显示 → 正文头变空，但**分镜表照旧**
        # [EN] ③ Turn off display -> body head becomes empty, but **the storyboard table stays the same**
        CFG.set('DISPLAY_FILM_CARDS', 'false')
        before = (tmp / '分镜表.md').read_text(encoding='utf-8')
        hdr2 = loop._film_header_of_day([])
        ok &= rec('B3 ★★ `DISPLAY_FILM_CARDS=false` → 正文不写镜头卡',
                  hdr2 == '', hdr2[:60])
        ok &= rec('B3 ★★ 但**分镜表照旧**（"屏幕显不显"和"给拍剧的人留底"是两件事）',
                  (tmp / '分镜表.md').exists()
                  and len((tmp / '分镜表.md').read_text(encoding='utf-8')) > len(before) - 1,
                  f'{len(before)} → {len((tmp / "分镜表.md").read_text(encoding="utf-8"))}')

        # ④ 幕终：分隔符必须用**上一幕**的地点（`_maybe_break_scene` 会覆盖它）
        # [EN] ④ Scene end: the separator must use the location of the **previous scene** (`_maybe_break_scene`
        # [EN] will overwrite it)
        import inspect
        src = inspect.getsource(RunLoop._tick)
        ok &= rec('B4 ★★ 幕终分隔符用的是**分幕前记下的旧地点**（原来读的是新地点）',
                  '_prev_place = self._last_place' in src
                  and 'D.scene_end(_prev_seg, _prev_place)' in src,
                  ' | '.join(l.strip() for l in src.split('\n') if '_prev_place' in l)[:150])
        ok &= rec('B4 ★ 幕终会推镜头卡（屏幕上看得到）',
                  '_emit_film_card(place=_prev_place)' in src, '')
    finally:
        CFG.set('FILM_MODE', saved[0])
        CFG.set('DISPLAY_FILM_CARDS', saved[1])
    return ok


# ══════════════════════════════════════════════════════════════
#  C/D. 风格来源与本幕提示
# [EN] C/D. Style source and current-scene hint
# ══════════════════════════════════════════════════════════════
def test_style() -> bool:
    ok = True
    saved = (CFG.raw('NOVEL_STYLE'), CFG.raw('NOVEL_STYLE_CUSTOM'),
             CFG.raw('SCENE_START_HINT'))

    def prefix(**kw):
        w = make_world()
        w.style_card = {'句长': '中短', '叙事距离': '近', 'AI腔禁词表': ['不禁', '缓缓']}
        for k, v in kw.items():
            setattr(w, k, v)
        return w.world_prefix()

    try:
        CFG.set('CONTEXT_CACHE', 'true')          # 特意开着缓存，验它会不会骗人
        # [EN] Deliberately keep the cache on, to verify whether it lies
        p = prefix(style_source='auto')
        ok &= rec('C1 ★ `auto` → 用抽出来的风格卡',
                  '[风格]' in p and '句长=中短' in p, p.replace('\n', ' | ')[:140])
        p = prefix(style_source='plain')
        ok &= rec('C1 ★★ `plain` → **一个字都不写风格**（朴素直叙）',
                  '[风格]' not in p, p.replace('\n', ' | ')[:140])
        p = prefix(style_source='custom', style_custom='像说书人那样短句、不解释。')
        ok &= rec('C1 ★★ `custom` → 用**作者手写**的风格文本',
                  '像说书人那样短句' in p, p.replace('\n', ' | ')[:140])
        p = prefix(style_source='custom', style_custom='')
        ok &= rec('C1 ★ `custom` 但没填 → **明说没填**（别装作有风格）',
                  '还没填' in p, p.replace('\n', ' | ')[:140])
        p = prefix(style_source='冷笔白描')
        ok &= rec('C1 ★ 其它取值当**风格名**用（风格卡统计仍然附在后面）',
                  '冷笔白描' in p and '句长=中短' in p, p.replace('\n', ' | ')[:140])

        # ★★ 缓存指纹要带上风格来源：改完**立刻**生效
        # [EN] ★★ The cache fingerprint must include the style source: changes take effect **immediately**
        w = make_world()
        w.style_card = {'句长': '中短'}
        w.style_source = 'plain'
        first = w.world_prefix()
        w.style_source = 'custom'
        w.style_custom = '改成说书腔。'
        ok &= rec('C2 ★★ 改了风格来源**立刻生效**（缓存指纹没漏字段）',
                  '[风格]' not in first and '说书腔' in w.world_prefix(),
                  f'{first[-40:]} → {w.world_prefix()[-40:]}')

        # D 本幕提示
        # [EN] D Current-scene hint
        p = prefix(scene_hint='这场戏先让雨下起来。')
        ok &= rec('D1 ★★ `SCENE_START_HINT` 进了 prompt（`[本幕提示]`）',
                  '[本幕提示]' in p and '先让雨下起来' in p,
                  p.replace('\n', ' | ')[:160])
        p = prefix(scene_hint='')
        ok &= rec('D1 ★ 空的时候不写这一行（不留空壳标题）',
                  '[本幕提示]' not in p, '')
    finally:
        CFG.set('NOVEL_STYLE', saved[0])
        CFG.set('NOVEL_STYLE_CUSTOM', saved[1])
        CFG.set('SCENE_START_HINT', saved[2])
    return ok


# ══════════════════════════════════════════════════════════════
#  E. 落盘（Project.style_custom）
# [EN] E. Write to disk (Project.style_custom)
# ══════════════════════════════════════════════════════════════
def test_project_roundtrip() -> bool:
    ok = True
    from store.project import Project
    tmp = Path(tempfile.mkdtemp(prefix='nws_style_'))
    try:
        p = Project.create_new(tmp, '风格测试', style='custom',
                               style_custom='短句，少形容词，不解释。')
        txt = (p.root / f'{p.name}.nwsproj').read_text(encoding='utf-8')
        ok &= rec('E1 ★★ 自定义风格**写进了项目文件**（不是只活在内存里）',
                  '风格自定义' in txt and '短句，少形容词' in txt,
                  [l for l in txt.split('\n') if '风格' in l])
        back = Project.from_nwsproj(p.root / f'{p.name}.nwsproj')
        ok &= rec('E1 ★★ 打开项目能**读回来**（跨会话不丢）',
                  back.style_custom == '短句，少形容词，不解释。'
                  and back.style == 'custom',
                  f'{back.style} / {back.style_custom}')
        ok &= rec('E1 没设过的项目读回来是空串（不是 None —— 免得调用方崩）',
                  Project.create_new(tmp, '空风格').style_custom == '', '')
    except Exception as e:                                      # noqa: BLE001
        ok &= rec('E1 项目文件往返没有抛异常', False, repr(e))
    return ok


if __name__ == '__main__':
    print('影视镜头卡 ＋ 风格来源 —— 验证', flush=True)
    ok = True
    try:
        head('A. 镜头卡（机位/拍法/视角/灯光）')
        ok &= test_card()
        head('B. 接线（FILM_MODE / DISPLAY_FILM_CARDS / 幕终）')
        ok &= test_wiring()
        head('C/D. 风格来源与本幕提示')
        ok &= test_style()
        head('E. 落盘（Project.style_custom）')
        ok &= test_project_roundtrip()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'film_style_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1200:])
    sys.exit(0 if report['ok'] else 2)
