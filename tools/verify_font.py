# -*- coding: utf-8 -*-
"""真机验证：随程序附带的**默认字体（思源宋体）**真的被用上了（不是静默退回系统字体）。

随附字体是 **SIL OFL 1.1**（可商用、可随程序分发）。
  2026-10-06 用户先选了霞鹜文楷；2026-10-11 因为「门写得跟普通写法不同」
  换成**思源宋体**做默认（霞鹜文楷仍随包提供、可在「天机 · 界面外观」里选回）。
"注册了 `page.fonts`"与"屏幕上真的换过来了"是两回事 —— 本项目的老规矩：
**控件树里对 ≠ 屏幕上看得见**。所以最后一组判据走像素。

★★ 判据怎么选（这一版是**第三版**，前两版都错在这儿）：
  · 第一版用**中文串的墨迹高度** —— 汉字是全角 1em，**换什么字体宽度都一样**，
    高度只差 1px，判不出任何东西（当场假红）；
  · 第二版用**拉丁串的宽度** —— 霞鹜 565 / 雅黑 555（PIL，30px），
    而 Flutter 渲染与 PIL 有 1~2% 的系统偏差，量出来 555 到底是霞鹜还是雅黑
    **说不清**（模棱两可的判据等于没有判据）；
  · 现在改成**认字形**：把截图里的墨迹裁出来，与 PIL 用三个候选字体渲染的
    同一段文字归一化后逐像素比，**平均绝对差最小的那个就是它**。
    每个候选之间差得很开（实测 24 vs 54 vs 64），不会再模棱两可。

判据：
  A 组（静态）
    A1 字体文件在 `assets/fonts/` 且 magic 是 TrueType
    A2 `bundled_font_files()` 给出「族名 → 相对 assets 的路径」，文件存在
    A3 `UI_FONT == FONT_FAMILY`（文件在 → 用它）
    A4 界面/标题/正文里**没有系统宋体残留**（`font_family='SimSun'` 应为 0 处）
    A5 等宽场景（日志/代码）仍是等宽字体（换楷体会毁掉对齐）
    A6 `start_gui()` **显式**给了 `assets_dir`（不靠"从哪启动"推断）
  B 组（真机 + 像素）
    B1 `page.fonts` 里注册了族名
    B2 主题的 `font_family` 就是 `UI_FONT`
    B3 ★★ 字形辨认：被测那行的墨迹**最像思源宋体**
    B4 ★ 阳性对照：同一次截图里，`SimSun` 行最像 SimSun、雅黑行最像雅黑
       —— 先证明尺子能认字，再拿它认目标

跑法：.venv\\Scripts\\python.exe tools/verify_font.py
产出：assets/screenshots/font_report.json / font_ui.png

English:
Real-device verification: the **LXGW WenKai** shipped with the program is actually being used
(not silently falling back to a system font).
User selected LXGW WenKai on 2026-10-06 (SIL OFL 1.1, commercial use allowed, can be distributed
with the program).
"Registered in `page.fonts`" and "actually swapped on screen" are two different things — this
project's old rule:
**matching in the widget tree ≠ visible on screen**. So the last group of criteria goes by
pixels.
★★ How the criteria were chosen (this is **version three**; the first two versions both got it
wrong here):
  · Version one used the **ink height of a Chinese string** — Chinese characters are full-width 1em, **the width is the same no matter the font**,
    the height differs by only 1px, so nothing can be distinguished (falsely red on the spot);
  · Version two used the **width of a Latin string** — LXGW 565 / YaHei 555 (PIL, 30px),
    but Flutter rendering has a 1~2% systematic deviation from PIL, so measuring 555 — is it LXGW or YaHei?
    **can't be said** (an ambiguous criterion equals no criterion);
  · Now changed to **glyph recognition**: crop the ink from the screenshot, and compare it pixel-by-pixel after normalization
    against the same text rendered by PIL with each of three candidate fonts, **the one with the smallest mean absolute difference is it**.
    The candidates differ widely from each other (measured 24 vs 54 vs 64), so it won't be ambiguous again.
Criteria:
  Group A (static)
    A1 The font file is in `assets/fonts/` and its magic is TrueType
    A2 `bundled_font_files()` gives "family name → path relative to assets", and the file exists
    A3 `UI_FONT == FONT_FAMILY` (file present → use it)
    A4 There is **no residual system SimSun** in the UI/title/body (`font_family='SimSun'` should appear 0 times)
    A5 Monospace scenarios (logs/code) still use a monospace font (switching to Kai would ruin alignment)
    A6 `start_gui()` **explicitly** provides `assets_dir` (does not rely on inferring "where it was started from")
  Group B (real device + pixels)
    B1 The family name is registered in `page.fonts`
    B2 The theme's `font_family` is exactly `UI_FONT`
    B3 ★★ Glyph recognition: the ink of the line with `font_family='MyWenKai'` **most resembles LXGW WenKai**
    B4 ★ Positive control: in the same screenshot, the `SimSun` line most resembles SimSun, and the YaHei line most resembles YaHei
       — first prove the ruler can recognize characters, then use it to recognize the target
How to run: .venv\\Scripts\\python.exe tools/verify_font.py
Output: assets/screenshots/font_report.json / font_ui.png
"""
from __future__ import annotations

import asyncio
import json
import sys
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

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
VU.redirect_env_writes()

ASSETS = APP_DIR / 'assets'
# 拉丁串（**不是**中文串 —— 汉字全角等宽，量不出字体差异，见文件头）
# [EN] Latin string (**not** a Chinese string — Chinese characters are full-width monospace, so font
# [EN] differences can't be measured; see file header)
LAT = 'Hamburgefonstiv 0123456789 abcdefg'
SIZE = 30
SLOTS = [('对照 SimSun', '#ff00ff', 'SimSun'),
         ('被测（随附字体）', '#00ffff', G.FONT_FAMILY),
         ('对照 雅黑', '#00ff00', 'Microsoft YaHei')]
# ⚠ 2026-10-11：默认字体从**霞鹜文楷**换成了**思源宋体**（用户报"门写得跟普通
#   写法不同"）。这条判据靠"三段候选里最像谁"认字，所以候选表必须跟着换 ——
#   旧表里没有思源宋体，被测那行会被认成别人，判据假红。
# [EN] ⚠ 2026-10-11: the default font changed from **LXGW WenKai** to **Noto Serif SC** (the user
# [EN] reported "门 is written differently from the normal form"). This criterion identifies a font by
# [EN] "which of three candidates it most resembles", so the candidate table must follow -- the old
# [EN] table had no Noto Serif SC, the tested line would be recognized as someone else, falsely red.
CANDIDATES = {
    '思源宋体': str(ASSETS / 'fonts' / G.FONT_REGULAR),
    '霞鹜文楷': str(ASSETS / 'fonts' / 'LXGWWenKai-Regular.ttf'),
    'SimSun': 'C:/Windows/Fonts/simsun.ttc',
    '微软雅黑': 'C:/Windows/Fonts/msyh.ttc',
}

checks: list = []


def ok(name: str, cond, detail='') -> bool:
    checks.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:220]})
    return bool(cond)


def static_checks() -> None:
    f = G.FONT_DIR / G.FONT_REGULAR
    magic = f.read_bytes()[:4] if f.exists() else b''
    ok('A1 字体文件在 assets/fonts/ 且是 TrueType（magic 00 01 00 00）',
       f.exists() and magic in (b'\x00\x01\x00\x00', b'OTTO'),
       f'{f.name} {f.stat().st_size if f.exists() else "-"} 字节 {magic!r}')

    reg = G.bundled_font_files()
    rel_ok = bool(reg) and all(
        not Path(v).is_absolute() and (G.FONT_DIR.parent / v).exists()
        for v in reg.values())
    ok('A2 `bundled_font_files()` 给「族名 → 相对 assets 的路径」且文件存在',
       rel_ok, reg)
    # ★★ 2026-10-14 改：原来期望 `UI_FONT == FONT_FAMILY`（随附**宋体**），
    #   可 `UI_FONT` 现在由 `CFG.s('UI_FONT')` 解析 ⇒ 读的是**用户环境里的
    #   `.env`**。用户在「天机 · 界面外观」里选了楷体（`UI_FONT=kai`），
    #   于是这条在**他自己的机器上**永远红（同一天 `verify_font_settings` 的
    #   B1a 是一个根因）。
    #   这条判据的本意是"**字体文件在 → 界面用的就是随附字体**（不是系统字体）"，
    #   那就按本意判：UI_FONT 必须落在**三份随附族名**里。
    #   `FONT_FAMILY` 仍留着（它是"默认那一份"的名字，由 A1 那条纯逻辑判据守）。
    # [EN] ★★ Changed 2026-10-14: it used to expect `UI_FONT == FONT_FAMILY` (the bundled
    # [EN] **serif**), but `UI_FONT` is now resolved from `CFG.s('UI_FONT')` => it reads the **user
    # [EN] environment's `.env`**. The user picked the Kai font in "Tianji · UI appearance"
    # [EN] (`UI_FONT=kai`), so on **his own machine** this line is forever red (same root cause as
    # [EN] B1a of `verify_font_settings` the same day).
    # [EN] This criterion's intent is "**font files present -> the UI uses the bundled font** (not a
    # [EN] system font)", so judge by that intent: `UI_FONT` must fall within the **three bundled
    # [EN] family names**. `FONT_FAMILY` stays (it is the name of the "default one", guarded by the
    # [EN] pure-logic A1 criterion).
    _fams = {v[0] for v in G.BUNDLED_FONTS.values()}
    ok('A3 字体在 → `UI_FONT` 就是随附字体的族名（三份里挑中的那一份，不是系统字体）',
       G.UI_FONT in _fams, f'{G.UI_FONT} / 随附 {sorted(_fams)}')

    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    ok("A4 界面/标题/正文里**没有系统宋体残留**（应为 0 处）",
       "font_family='SimSun'" not in src,
       str(src.count("font_family='SimSun'")))
    ok('A5 等宽场景（日志/代码）仍是等宽字体（换楷体会毁掉对齐）',
       src.count("font_family='Consolas'") >= 2,
       str(src.count("font_family='Consolas'")))
    ok('A6 `start_gui()` **显式**给了 `assets_dir`（不靠"从哪启动"推断）',
       'assets_dir=' in src and 'ft.run(app.main' in src,
       [l.strip()[:80] for l in src.split('\n') if 'ft.run(' in l][:2])


def mask_rgb(png, rgb):
    from PIL import ImageChops
    im = VU.image_of(png)
    r, g, b = im.split()
    return ImageChops.multiply(
        r.point(lambda v: 255 if abs(v - rgb[0]) < 60 else 0),
        ImageChops.multiply(
            g.point(lambda v: 255 if abs(v - rgb[1]) < 60 else 0),
            b.point(lambda v: 255 if abs(v - rgb[2]) < 60 else 0)))


def normalize(mask, size=(560, 40)):
    bb = mask.getbbox()
    return mask.crop(bb).resize(size) if bb else None


def mad(a, b) -> float:
    pa, pb = a.load(), b.load()
    w, h = a.size
    s = 0
    for y in range(h):
        for x in range(w):
            s += abs(pa[x, y] - pb[x, y])
    return round(s / (w * h), 2)


def render_reference(path: str):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('L', (1600, 120), 0)
    ImageDraw.Draw(img).text((20, 30), LAT, fill=255,
                             font=ImageFont.truetype(path, SIZE))
    return img


async def main(page: ft.Page):
    app = G.NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.2)

    fonts = dict(getattr(page, 'fonts', None) or {})
    ok('B1 `page.fonts` 里注册了随附字体的族名', G.FONT_FAMILY in fonts, fonts)
    ok('B2 主题的 `font_family` 就是 `UI_FONT`',
       str(getattr(getattr(page, 'theme', None), 'font_family', '')) == G.UI_FONT,
       getattr(getattr(page, 'theme', None), 'font_family', None))

    # ── B3/B4 字形辨认 ──
    # [EN] ── B3/B4 glyph recognition ──
    page.controls.clear()
    page.add(ft.Container(content=ft.Column([
        ft.Text(LAT, size=SIZE, color=rgb, font_family=fam)
        for _n, rgb, fam in SLOTS], spacing=26), padding=40))
    page.update()
    await asyncio.sleep(2.0)
    try:
        png = await page.take_screenshot()
        (OUT / 'font_ui.png').write_bytes(png)
        refs = {n: normalize(render_reference(p)) for n, p in CANDIDATES.items()}
        rows: dict = {}
        for key, rgb, fam in SLOTS:
            tri = tuple(int(rgb[i:i + 2], 16) for i in (1, 3, 5))
            m = normalize(mask_rgb(png, tri))
            if m is None:
                rows[key] = {'error': '没抠到墨迹'}
                continue
            diffs = {n: mad(m, r) for n, r in refs.items() if r}
            rows[key] = {'family': fam, 'diffs': diffs,
                         'looks_like': min(diffs, key=diffs.get)}
        report = {'rows': rows,
                  'lxgw': rows.get('被测（随附字体）', {}),
                  'ctrl_simsun': rows.get('对照 SimSun', {}),
                  'ctrl_yahei': rows.get('对照 雅黑', {})}

        ok('B4a ★ 阳性对照：同框里的 SimSun 行被认成 SimSun',
           report['ctrl_simsun'].get('looks_like') == 'SimSun',
           report['ctrl_simsun'])
        ok('B4b ★ 阳性对照：同框里的雅黑行被认成微软雅黑',
           report['ctrl_yahei'].get('looks_like') == '微软雅黑',
           report['ctrl_yahei'])
        ok('★★ B3 被测那行的墨迹**最像思源宋体**'
           '（= 随附的默认字体真的画在屏幕上了）',
           report['lxgw'].get('looks_like') == '思源宋体',
           report['lxgw'])
    except Exception as e:                                   # noqa: BLE001
        ok('B4a ★ 阳性对照：同框里的 SimSun 行被认成 SimSun', False, repr(e))

    rep = {'checks': checks,
           'passed': sum(1 for x in checks if x['ok']), 'total': len(checks)}
    rep['ok'] = rep['passed'] == rep['total']
    (OUT / 'font_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    for c in checks:
        print(('  ✓ ' if c['ok'] else '  ✗ ') + c['name'] + (
            f"   [{c['detail']}]" if not c['ok'] else ''))
    print(f"\n字体验证：{rep['passed']}/{rep['total']}")
    await shutdown(page, code=0 if rep['ok'] else 2)


if __name__ == '__main__':
    try:
        static_checks()
        # ⚠ 显式给 assets_dir：这个脚本在 `tools/` 下跑，默认解析会去找
        #   `tools/assets`（不存在）→ assets 变 None → 字体静默失效、判据假红。
        # [EN] ⚠ Explicitly provide assets_dir: this script runs under `tools/`, and default resolution will
        # [EN] look for
        # [EN] `tools/assets` (which doesn't exist) → assets becomes None → font silently fails, criteria
        # [EN] falsely red.
        ft.run(main, assets_dir=str(ASSETS))
    except Exception:                                        # noqa: BLE001
        exit_now(2)
