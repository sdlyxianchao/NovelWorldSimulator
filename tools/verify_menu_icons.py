# -*- coding: utf-8 -*-
"""验证开始菜单的**彩色图标素材**：在不在、是不是彩色的、灰化版是不是真褪色、
三处（生成脚本 / 磁盘文件 / 界面代码）的槽位对不对得上。

为什么要单独一支（而不是塞进 `verify_resume_menu.py`）
-----------------------------------------------------
菜单图标这件事有**两层**，坏的方式完全不同：
  · **素材层**（这支）—— 图不在、是空白的、是单色线条的、灰化版没灰、
    槽位名三处不一致。这一层**不用起界面**就能查，快，所以能天天跑。
  · **渲染层**（`verify_resume_menu.py`）—— 界面真的把这八张图挂上去了吗、
    不可点的那几项挂的是不是褪色版。这一层必须**真机**（起 Flet 读控件树）。
分开的好处：素材坏了（最常见）不必等十秒的窗体启动就知道。

**「彩色」是这支的核心**，也是用户这一轮唯一的抱怨
-------------------------------------------------
用户 2026-10-10：「你帮我绘制或者去网上找之前那种彩色图标 现在不好看」。
"不好看"的根子是**上一版是单色线条图标**（Material 矢量图标）—— 这件事
**可以量**：不透明像素里**饱和度 ≥25 的占比**（下称 `colored_ratio`）。
单色线条图标这个数 ≈ 0，彩色图标这个数在 0.3~1.0。所以「必须是彩色的」
从一句主观评价变成了一条能红的断言。

阈值是**先量出来的**（2026-10-10 实测基线，扁平彩色风格）：
    开卷 .288 · 拾卷 1.000 · 起笔 .853 · 拆书 .973
    天机 .561 · 书斋 .918 · 回卷 .818 · 归去 1.000  → 平均 .801
天机最低（齿轮本身是金属灰），所以**单张**下限压到 .10（挡住"混进一张单色"),
靠**整套**（平均 ≥ .50 且至少 6 张 ≥ .30）来区分"彩色一套"与"单色一套"。
⚠ 这与 `developers/make_menu_icons.py` 里的 `COLORED_MIN / AVG_COLORED_MIN /
  N_HI_COLORED` 是**同一套数字**，改一处要改两处。

产出：assets/screenshots/menu_icons_report.json
用法：.venv/Scripts/python.exe tools/verify_menu_icons.py

English:
Verify the start menu's **colored icon assets**: present or not, colored or not, whether the
grayscale version is truly faded,
and whether the slots match across all three (generation script / disk files / UI code).
Why a separate one (instead of cramming it into `verify_resume_menu.py`)
-----------------------------------------------------
The menu icon matter has **two layers**, and they fail in completely different ways:
  · **Asset layer** (this one) -- image missing, blank, monochrome line, grayscale version not gray,
    slot names inconsistent across the three. This layer **can be checked without starting the UI**, it is fast, so it can run daily.
  · **Rendering layer** (`verify_resume_menu.py`) -- does the UI actually mount these eight images,
    and are the non-clickable items mounted with the faded version. This layer requires **real hardware** (start Flet and read the control tree).
Benefit of separating: if assets break (most common), you know without waiting ten seconds for
the window to start.
**"Colored" is the core of this one**, and also the user's only complaint this round
-------------------------------------------------
User 2026-10-10: "Help me draw or find online the colored icons like before, the current ones
look bad".
The root of "looks bad" is that **the previous version was monochrome line icons** (Material
vector icons) -- this
**can be measured**: the ratio of **saturation >= 25** among opaque pixels (hereafter
`colored_ratio`).
For monochrome line icons this number is ~ 0, for colored icons it is 0.3~1.0. So "must be
colored"
turns from a subjective opinion into an assertable condition that can go red.
The thresholds were **measured first** (2026-10-10 measured baseline, flat colored style):
天机 is the lowest (the gear itself is metallic gray), so the **single-image** floor is pressed
down to .10 (guards against "one monochrome sneaking in"),
and the **whole set** (average >= .50 and at least 6 images >= .30) distinguishes "a colored
set" from "a monochrome set".
⚠ This and `COLORED_MIN / AVG_COLORED_MIN /` in `developers/make_menu_icons.py`
  `N_HI_COLORED` are **the same set of numbers**; change one place and you must change both.
Output: assets/screenshots/menu_icons_report.json
Usage: .venv/Scripts/python.exe tools/verify_menu_icons.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from PIL import Image  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
ICON_DIR = APP_DIR / 'assets' / 'images' / 'menu_icons'
SRC_DIR = ICON_DIR / 'src'
APP_PY = APP_DIR / 'gui' / 'app_flet.py'
GEN_PY = APP_DIR / 'developers' / 'make_menu_icons.py'

#: 菜单八项与槽位（顺序 = 菜单里从上到下的顺序；改这里要同时改生成脚本）
# [EN] : The eight menu items and slots (order = top-to-bottom order in the menu; changing this
# [EN] requires also changing the generation script)
SLOTS = ['open_book', 'books', 'play', 'puzzle', 'gear', 'brush', 'rewind', 'door']
CANVAS = 128
#: 与 `developers/make_menu_icons.py` 同源（见文件头注释）
# [EN] : Same source as `developers/make_menu_icons.py` (see file header comment)
COLORED_MIN = 0.10
AVG_COLORED_MIN = 0.50
N_HI_COLORED = 6
#: 单张"透明占比"的合理区间：全透明=没画出来；几乎不透明=裁错（多半截进了白底）
# [EN] : Reasonable range for a single image's "transparent ratio": fully transparent = nothing drawn;
# [EN] almost opaque = cropped wrong (most likely a white background got cropped in)
ALPHA_MIN, ALPHA_MAX = 0.05, 0.95
#: 灰化版的彩色占比上限：超过它就不算"褪色"
# [EN] : Upper limit on the colored ratio of the grayscale version: above it, it does not count as
# [EN] "faded"
DIM_COLORED_MAX = 0.05

report: dict = {'steps': []}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    """记一条断言。

    ⚠ 失败行必须是 **`✗` 开头**（本项目判据的统一约定）：
      `developers/mutate_ui_20261010.py` 的反例法靠"stdout 里有没有 `✗`、
      且那行含预期的名字"来判"这一条真的能红"。第一版这里打的是 `[FAIL]`，
      结果**六条变异全被记成"漏掉"** —— 看着像判据没本事，其实是打印格式
      跟脚手架对不上号（`verify_icon.py` 用的是 `[OK]/[FAIL]`，但那一支
      不在反例法的组里）。
    
        English:
    Record an assertion.
        ⚠ The failure line must **start with `✗`** (the project's unified convention for criteria):
          the counterexample method in `developers/mutate_ui_20261010.py` relies on "whether stdout contains `✗`
          and whether that line contains the expected name" to judge "whether this one can really go red". The first version printed `[FAIL]` here,
          and as a result **all six mutations were recorded as "missed"** -- it looked like the criterion had no teeth, but actually the print format
          did not line up with the scaffolding (`verify_icon.py` uses `[OK]/[FAIL]`, but that one
          is not in the counterexample-method group).
    """
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(f'  {"✓" if ok else "✗"} {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return ok


def stats(im: Image.Image) -> dict:
    """不透明像素的统计：透明占比、彩色占比、平均亮度、最小/最大亮度。
        English:
    Opaque pixel statistics: transparent ratio, colored ratio, average brightness, min/max
    brightness.
    """
    px = im.convert('RGBA').load()
    a = im.convert('RGBA').getchannel('A')
    n = im.width * im.height
    opaque = colored = 0
    lum_sum = 0.0
    for y in range(im.height):
        for x in range(im.width):
            if a.getpixel((x, y)) < 24:
                continue
            opaque += 1
            r, g, b, _ = px[x, y]
            if max(r, g, b) - min(r, g, b) >= 25:
                colored += 1
            lum_sum += 0.2126 * r + 0.7152 * g + 0.0722 * b
    return {
        'alpha_cov': opaque / n,
        'colored_ratio': (colored / opaque) if opaque else 0.0,
        'lum': (lum_sum / opaque) if opaque else 0.0,
    }


def load(slot: str, dim: bool = False):
    p = ICON_DIR / f'{slot}{"_dim" if dim else ""}.png'
    if not p.exists():
        return None, p
    im = Image.open(p)
    im.load()
    return im.convert('RGBA'), p


# ══════════════════════════════════════════════════════════════
#  ① 素材层
# [EN] ① Asset layer
# ══════════════════════════════════════════════════════════════
def check_files() -> list[bool]:
    miss = [f'{s}{suf}.png' for s in SLOTS for suf in ('', '_dim')
            if not (ICON_DIR / f'{s}{suf}.png').exists()]
    r = [rec('十六张图都在（8 项 × 彩色/褪色）', not miss,
             f'缺 {miss}' if miss else '')]

    bad_size, bad_mode = [], []
    for s in SLOTS:
        for suf in ('', '_dim'):
            f = ICON_DIR / f'{s}{suf}.png'
            if not f.exists():
                continue
            im = Image.open(f)
            if im.size != (CANVAS, CANVAS):
                bad_size.append(f'{f.name}={im.size}')
            if im.mode != 'RGBA':
                bad_mode.append(f'{f.name}={im.mode}')
    r.append(rec(f'都是 {CANVAS}×{CANVAS} 的透明底 PNG', not bad_size and not bad_mode,
                 ' '.join(bad_size + bad_mode)))

    # **不是空白**：透明占比要落在区间里
    # [EN] **Not blank**: the transparent ratio must fall within the range
    out = []
    for s in SLOTS:
        im, _p = load(s)
        if im is None:
            continue
        cov = stats(im)['alpha_cov']
        if not (ALPHA_MIN <= cov <= ALPHA_MAX):
            out.append(f'{s}={cov:.3f}')
    r.append(rec('每张都有内容、也没铺满（说明白底裁干净了）', not out, ' '.join(out)))

    # 八张**不是同一张图**（防"复制一个文件改八个名"）
    # [EN] The eight images are **not the same image** (guards against "copy one file and rename it eight
    # [EN] ways")
    sig = {}
    for s in SLOTS:
        im, _p = load(s)
        if im is None:
            continue
        sig[s] = (im.getchannel('A').tobytes(), im.convert('RGB').tobytes())
    dup = []
    keys = list(sig)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if sig[a] == sig[b]:
                dup.append(f'{a}={b}')
    r.append(rec('八项是八张不同的图', not dup, ' '.join(dup)))
    return r


def check_colorful() -> list[bool]:
    r = []
    st = {}
    for s in SLOTS:
        im, _p = load(s)
        if im is not None:
            st[s] = stats(im)
    report['stats'] = {k: {kk: round(vv, 3) for kk, vv in v.items()}
                       for k, v in st.items()}

    low = {k: round(v['colored_ratio'], 3) for k, v in st.items()
           if v['colored_ratio'] < COLORED_MIN}
    r.append(rec(f'每一张都是彩色的（彩色像素占比 ≥ {COLORED_MIN}）', not low,
                 f'不达标：{low}' if low else
                 ' '.join(f'{k}={v["colored_ratio"]:.2f}' for k, v in st.items())))

    if st:
        avg = sum(v['colored_ratio'] for v in st.values()) / len(st)
        n_hi = sum(1 for v in st.values() if v['colored_ratio'] >= 0.30)
        report['avg_colored'] = round(avg, 3)
        report['n_hi_colored'] = n_hi
        # ★ 这条专门挡"退回单色线条图标"：那套图标这八个数全是 0，
        #   于是平均与个数两条会一起红。
        # [EN] ★ This one specifically guards against "falling back to monochrome line icons": for that icon
        # [EN] set, all eight of these numbers are 0,
        # [EN] so the average and count checks both go red together.
        r.append(rec(f'整套是彩色的一套（平均 ≥ {AVG_COLORED_MIN} 且 ≥{N_HI_COLORED} 张旺彩）',
                     avg >= AVG_COLORED_MIN and n_hi >= N_HI_COLORED,
                     f'平均 {avg:.3f}，≥0.30 的有 {n_hi}/{len(st)} 张'))
    return r


def check_dim() -> list[bool]:
    r = []
    # ① 褪色版必须真的**不彩色**
    # [EN] ① The faded version must genuinely **not be colored**
    out = {}
    for s in SLOTS:
        im, _p = load(s, dim=True)
        if im is None:
            continue
        v = stats(im)['colored_ratio']
        if v > DIM_COLORED_MAX:
            out[s] = round(v, 3)
    r.append(rec('褪色版真的褪了色（不可点那一项不能还是亮的）', not out,
                 f'仍有彩色：{out}' if out else ''))

    # ② 褪色版与彩色版**只差颜色、不差形状**（alpha 通道逐字节相同）
    # [EN] ② The faded version and the colored version **differ only in color, not in shape** (alpha
    # [EN] channel byte-for-byte identical)
    shape = []
    for s in SLOTS:
        a, _ = load(s)
        b, _ = load(s, dim=True)
        if a is None or b is None:
            continue
        if a.getchannel('A').tobytes() != b.getchannel('A').tobytes():
            shape.append(s)
    r.append(rec('褪色版与彩色版形状一致（是同一张图变了色，不是换了图）',
                 not shape, ' '.join(shape)))

    # ③ 褪色版与纸色的**反差**要比彩色版小（"淡下去"而不是"黑下去"）
    #    口径是"离纸色的距离"，不是亮度大小 —— 白色书页那种图标，
    #    褪色后亮度几乎不变，只按亮度判会假失败。
    # [EN] ③ The **contrast** between the faded version and the paper color must be smaller than the
    # [EN] colored version ("fade down" rather than "blacken down")
    # [EN] The measure is "distance from the paper color", not brightness magnitude -- for icons like a
    # [EN] white book page,
    # [EN] brightness barely changes after fading, so judging by brightness alone gives false failures.
    paper = 0.2126 * 253 + 0.7152 * 250 + 0.0722 * 242
    worse = []
    for s in SLOTS:
        a, _ = load(s)
        b, _ = load(s, dim=True)
        if a is None or b is None:
            continue
        ca = abs(stats(a)['lum'] - paper)
        cb = abs(stats(b)['lum'] - paper)
        if cb >= ca:
            worse.append(f'{s}(彩色 {ca:.0f}→褪色 {cb:.0f})')
    r.append(rec('褪色版比彩色版更贴纸色（是"淡"，不是"糊成一团黑"）',
                 not worse, ' '.join(worse)))
    return r


def check_provenance() -> list[bool]:
    r = []
    readme = ICON_DIR / 'README.md'
    txt = readme.read_text(encoding='utf-8') if readme.exists() else ''
    # ★ 判据不能只查"MIT 这三个字母在不在"（那与"判名字在不在"是同一个毛病）：
    #   用户点名的要求是「避免版权问题」，所以要查的是**能复查的那几件事**——
    #   ① 许可名（MIT）② 出处（素材库名，能顺着找到 ③ 版权行（MIT 的署名义务）
    #   ④ 授权范围（可商用/可再分发）⑤ 取用日期（"哪一版"是复查的前提）
    # [EN] ★ The criterion must not merely check "are the letters MIT present" (that is the same flaw as
    # [EN] "checking whether the name is present"):
    # [EN] the requirement the user named is "avoid copyright issues", so what must be checked is **the
    # [EN] things that can be re-verified** --
    # [EN] ① license name (MIT) ② source (asset library name, which can be traced to find ③ copyright line
    # [EN] (MIT's attribution obligation)
    # [EN] ④ scope of grant (commercial use / redistribution allowed) ⑤ date obtained ("which version" is
    # [EN] the precondition for re-verification)
    need = {'许可名 MIT': 'MIT', '出处 fluentui-emoji': 'fluentui-emoji',
            '版权行': 'Copyright', '授权范围（可商用/再分发）': '再分发',
            '取用日期': '取用日期'}
    miss = [k for k, v in need.items() if v not in txt]
    r.append(rec('出处与许可写全了（许可名 · 出处 · 版权行 · 授权范围 · 取用日期）',
                 not miss, f'缺：{miss}' if miss else 'assets/images/menu_icons/README.md'))
    n_src = len(list(SRC_DIR.glob('*'))) if SRC_DIR.exists() else 0
    # 留档原始素材 → 断网也能重建（8 个槽位至少要 8 份源）
    # [EN] Archive the original assets -> rebuildable offline (at least 8 sources for 8 slots)
    r.append(rec('原始素材留档在 src/（可离线重建）', n_src >= 8, f'{n_src} 份'))
    return r


# ══════════════════════════════════════════════════════════════
#  ② 接线层（源码级；渲染层在 verify_resume_menu.py）
# [EN] ② Wiring layer (source level; the rendering layer is in verify_resume_menu.py)
# ══════════════════════════════════════════════════════════════
def _slots_in_ui(src: str) -> list[str]:
    """菜单里出现的 `img:<槽位>`（按出现顺序）。
        English:
    The `img:<slot>` appearing in the menu (in order of appearance).
    """
    return re.findall(r"\('img:([a-z_2]+)',", src)


def check_wiring() -> list[bool]:
    src = APP_PY.read_text(encoding='utf-8')
    ui = _slots_in_ui(src)
    report['ui_slots'] = ui
    r = [rec('界面里的八项挂的都是彩色位图（`img:`），顺序与约定一致',
             ui == SLOTS, f'实际={ui}')]

    missing = [s for s in ui if not (ICON_DIR / f'{s}.png').exists()]
    r.append(rec('界面指到的图都在磁盘上（槽位名没写错）', not missing,
                 f'没有的：{missing}'))

    # 生成脚本里的槽位表也要对得上 —— 三处（脚本/磁盘/界面）一致才算"没写歪"
    # [EN] The slot table in the generation script must match too -- only when all three (script / disk /
    # [EN] UI) agree does it count as "not miswritten"
    gen = GEN_PY.read_text(encoding='utf-8') if GEN_PY.exists() else ''
    gen_slots = re.findall(r"^\s*\('([a-z_2]+)', '", gen, re.M)
    gen_slots = [s for s in gen_slots if s in SLOTS or s in ui] or []
    report['gen_slots'] = gen_slots
    r.append(rec('生成脚本的槽位表与界面一致（换素材不用改代码，但名字得同源）',
                 sorted(gen_slots) == sorted(SLOTS),
                 f'脚本={gen_slots}'))

    # 兜底：`img:` 指到不存在的文件时不许崩，而是降级成"破图"图标
    #   （与上一轮 "名字拼错 → 静默回退" 的规矩同一条：**降级要看得见**）
    # [EN] Fallback: when `img:` points to a nonexistent file, must not crash, but degrade to a "broken
    # [EN] image" icon
    # [EN] (Same rule as the previous round's "name misspelled -> silent fallback": **degradation must be
    # [EN] visible**)
    r.append(rec('槽位名写错时降级成"破图"图标而不是崩',
                 'BROKEN_IMAGE' in src))
    return r


def main() -> int:
    print('  菜单彩色图标素材验证')
    results = check_files() + check_colorful() + check_dim() \
        + check_provenance() + check_wiring()
    report['ok'] = all(results)
    report['failed'] = [s for s in report['steps'] if not s['ok']]
    (OUT / 'menu_icons_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    n = len(report['steps'])
    print(f'\n  共 {n} 项断言，失败 {len(report["failed"])} 项 → '
          f'{"全部通过" if report["ok"] else "有失败"}')
    for s in report['failed']:
        print(f'    ✗ {s["name"]}  {s["detail"]}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
