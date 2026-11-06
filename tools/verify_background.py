# -*- coding: utf-8 -*-
"""验证背景图管线：文生图原图 → 界面用高清图，以及运行时纸色滤镜的**可读性**与**接线**。

为什么要有这个脚本
------------------
背景图换成了文生图，但「图好不好看」本机验不了（模型读不了图片）。
能验、也必须验的是**工程部分**：

1. **管线真的能跑**：原图 → 裁 16:9 → 放大到 3840×2160 → 轻锐化
   （没有原图时用一张替身源图自检，全程写临时目录，不动正式资源）
2. **两张背景都清晰（模糊不再烤进图片）**：用「高通 std 不低于源图 60%、两张互差 ≤20%」
   量出来，保证有人把高斯模糊烤回去会被抓到
3. **文字在「清晰背景 + 运行时纸色滤镜 + 面板」三层合成后仍然可读**：背景 → 滤镜 → 面板
   合成后按 `BG_DIM`+`UI_OPACITY` 算正文色 WCAG 对比度（要求中位数 ≥ 4.5:1）
4. **成品就位**：`title_bg.webp` / `title_bg_soft.webp` 存在、是 16:9、3840×2160、
   且都是 WebP（不再用 PNG）
5. **运行时背景滤镜接线**：`BG_DIM` 配置存在、`bg_dim()`/`make_bg_scrim()` 行为正确、
   开始与运行界面的 Stack 都接了纸色滤镜层（对话框不在 Stack 里，不受影响）

产出：assets/screenshots/background_report.json

English:
Verify the background image pipeline: text-to-image source image → UI image, and the
**readability** of the softened version.
Why this script exists
------------------
The background image was switched to text-to-image, but "whether the image looks good" cannot be
verified on this machine (the model cannot read images).
What can be verified, and must be verified, is the **engineering part**:
1. **The pipeline actually runs**: source image → crop to 16:9 → upscale to 3840×2160 → light sharpen
   (when there is no source image, use a stand-in source image for self-check, write everything to a temp directory, do not touch official assets)
2. **Both backgrounds are CLEAR (blur is no longer baked in)**: measured with "high-pass std not below 60% of the source, the two within 20% of each other",
   so if someone bakes Gaussian blur back in, it is caught
3. **Text remains readable after compositing the CLEAR background + runtime paper scrim + panel**: composite background → scrim → panel,
   then compute the WCAG contrast of the body text color by `BG_DIM`+`UI_OPACITY` (require median ≥ 4.5:1)
4. **Final products are in place**: `title_bg.webp` / `title_bg_soft.webp` exist, are 16:9,
   3840×2160,
   and are both WebP (no longer PNG)
5. **Runtime background scrim wiring**: `BG_DIM` config exists, `bg_dim()`/`make_bg_scrim()` behave correctly,
   and both the start and run screen Stacks are wired with the paper scrim (dialogs are not in the Stack, so unaffected)
Output: assets/screenshots/background_report.json
"""
from __future__ import annotations

import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

import verify_ui_common as VU

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from PIL import Image, ImageChops, ImageDraw, ImageFilter  # noqa: E402

from image_gen import background as BG  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
IMG = APP_DIR / 'assets' / 'images'

report: dict = {'steps': []}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(f'  {"[OK]  " if ok else "[FAIL]"} {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return ok


def rel_lum(c) -> float:
    def f(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(c1, c2) -> float:
    a, b = rel_lum(c1), rel_lum(c2)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def hex_rgb(c) -> list[int]:
    """#RRGGBB 或 #AARRGGBB → [r, g, b]（兼容 apply_ui_opacity 写回的 8 位色）。
        English:
    #RRGGBB or #AARRGGBB -> [r, g, b] (tolerant of the 8-digit color written back by apply_ui_opacity).
    """
    h = str(c).lstrip('#')
    if len(h) == 8:
        h = h[2:]
    if len(h) != 6:
        return [0, 0, 0]
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def highpass_std(im: Image.Image, size: int = 320) -> float:
    """高通残差的标准差 —— 衡量「画面有多少细节」。柔化后应当明显下降。
        English:
    Standard deviation of the high-pass residual —— measures "how much detail the image has". It
    should drop noticeably after softening.
    """
    g = im.convert('L').resize((size, size), Image.Resampling.BILINEAR)
    res = ImageChops.difference(g, g.filter(ImageFilter.GaussianBlur(1.5)))
    px = list(res.get_flattened_data())
    n = len(px)
    mean = sum(px) / n
    return (sum((p - mean) ** 2 for p in px) / n) ** 0.5


def mean_lum(im: Image.Image, size: int = 200) -> float:
    small = im.convert('RGB').resize((size, size), Image.Resampling.BILINEAR)
    px = list(small.get_flattened_data())
    return sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in px) / len(px)


def make_standin(path: Path) -> Path:
    """造一张「像风景照」的替身源图：上蓝天、中远山、下水面 + 一些高频细节。

    用它自检管线的裁切/放大/柔化数学。有真的文生图原图时不会走到这里。
    
        English:
    Create a stand-in source image that "looks like a landscape photo": blue sky on top, distant
    mountains in the middle, water below + some high-frequency detail.
        Use it to self-check the pipeline's crop/upscale/soften math. When a real text-to-image source image exists, this will not be reached.
    """
    w, h = 1536, 1024
    im = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / (h - 1)
        if t < 0.55:
            c = (185 + int(35 * t), 220, 235)
        elif t < 0.72:
            c = (120, 160, 150)
        else:
            c = (150, 195, 200)
        d.line([(0, y), (w, y)], fill=c)
    for i in range(160):        # 「樱花」高频点，用来验证柔化确实压掉了细节
    # [EN] "Cherry blossom" high-frequency points, used to verify that softening really suppresses detail.
        r = random.Random(i)
        x, y = r.randint(0, w), r.randint(0, int(h * 0.45))
        rr = r.randint(3, 12)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(242, 220, 226))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


# ══════════════════════════════════════════════════════════════
def check_source() -> bool:
    print('\n── 1. 文生图原图 ──')
    src = BG.find_ai_source()
    report['source'] = str(src) if src else None
    if src is None:
        print('    （还没有原图：assets/images/bg/ 是空的）')
        print('     → 生成命令：见 assets/images/bg/README.md')
        report['source_ready'] = False
        return True          # 没有原图不是「管线坏了」
        # [EN] No source image does not mean "the pipeline is broken".
    with Image.open(src) as im:
        report['source_size'] = list(im.size)
        rec('原图可读', True, f'{src.name}  {im.size[0]}×{im.size[1]}')
    report['source_ready'] = True
    return True


def check_pipeline() -> bool:
    print('\n── 2. 管线自检（替身源图，写临时目录）──')
    src = BG.find_ai_source()
    tmp = Path(tempfile.mkdtemp())
    ok = True
    try:
        if src is None:
            src = make_standin(tmp / 'standin.png')
            note = '替身源图 1536×1024'
        else:
            note = f'真实原图 {Image.open(src).size}'
        res = BG.build_from_source(src, tmp, (3840, 2160))
        ok &= rec('build_from_source 能产出母版与柔化版',
                  bool(res.get('master')) and bool(res.get('soft')), note)
        with Image.open(res['master']) as m, Image.open(res['soft']) as s:
            ok &= rec('母版是 16:9 的 3840×2160',
                      m.size == (3840, 2160),
                      f'{m.size[0]}×{m.size[1]}（比例 {m.size[0]/m.size[1]:.4f}）')
            ok &= rec('柔化版与母版同尺寸', s.size == m.size, str(s.size))
            ok &= rec('两张都是 WebP（不再用 PNG）',
                      m.format == 'WEBP' and s.format == 'WEBP',
                      f'{m.format} / {s.format}')

            # ── 2. 两张背景都「清晰」：模糊**不再烤进图片** ──
            # 用源图自身的清晰度为基准，断言两张成品都没有被烤模糊（一旦有人
            # 又把高斯模糊烤回去，细节就会掉到源图的 60% 以下，这里立刻抓到）。
            # [EN] ── 2. Both backgrounds are CLEAR: blur is no longer baked in ──
            # [EN] Use the source image's own sharpness as the baseline; assert neither product is blurred
            # [EN] (if someone bakes Gaussian blur back in, detail drops below 60% of the source and this catches it).
            base_ref = BG.make_master(src, (3840, 2160), sharpen=0.40)
            hp_base = highpass_std(base_ref)
            hp_m, hp_s = highpass_std(m), highpass_std(s)
            lum_m, lum_s = mean_lum(m), mean_lum(s)
            report['master'] = {'highpass_std': round(hp_m, 2),
                                'mean_lum': round(lum_m, 1),
                                'bytes': res['master'].stat().st_size}
            report['soft'] = {'highpass_std': round(hp_s, 2),
                              'mean_lum': round(lum_s, 1),
                              'bytes': res['soft'].stat().st_size}
            ok &= rec('母版未烤模糊（细节 ≥ 源图 60%）',
                      hp_m >= 0.6 * hp_base,
                      f'源图 hp={hp_base:.1f}，母版 hp={hp_m:.1f}')
            ok &= rec('柔化版未烤模糊（细节 ≥ 源图 60%）',
                      hp_s >= 0.6 * hp_base,
                      f'源图 hp={hp_base:.1f}，柔化版 hp={hp_s:.1f}')
            ok &= rec('两张背景清晰度一致（互差 ≤ 20%）',
                      abs(hp_s - hp_m) / max(hp_m, hp_s) <= 0.20,
                      f'{hp_m:.1f} vs {hp_s:.1f}')

            # ── 3. 文字可读性：清晰背景 + 纸色滤镜(BG_DIM) + 面板半透明(UI_OPACITY) 合成后 ──
            # 压暗现在交给运行时纸色滤镜层（make_bg_scrim），所以从 背景 → 滤镜 → 面板
            # 三层合成后再量正文对比度。这样证明：背景保持高清，但运行时滤镜 + 面板
            # 仍然保证文字可读。
            # [EN] ── 3. Text readability: after CLEAR background + paper scrim (BG_DIM) +
            # [EN] semi-transparent panel (UI_OPACITY) compositing ──
            # [EN] Dimming is now done at runtime by the paper scrim (make_bg_scrim), so we composite
            # [EN] background -> scrim -> panel and then measure body-text contrast. This proves the background
            # [EN] stays HD, yet the runtime scrim + panel still keep text readable.
            from gui.app_flet import C, ui_opacity, bg_dim, _BASE_INKC
            panel = C['panel']
            pc = hex_rgb(panel)
            a = ui_opacity()
            scrim_a = bg_dim()
            pr = hex_rgb(_BASE_INKC['paper'])
            text = C['text']
            tc = hex_rgb(text)
            small = s.convert('RGB').resize((120, 68), Image.Resampling.BILINEAR)
            cs = []
            for bg in small.get_flattened_data():
                after_scrim = tuple(round(scrim_a * pr[i] + (1 - scrim_a) * bg[i])
                                     for i in range(3))
                comp = tuple(round(a * pc[i] + (1 - a) * after_scrim[i])
                             for i in range(3))
                cs.append(contrast(comp, tuple(tc)))
            cs.sort()
            med = cs[len(cs) // 2]
            lo = cs[0]
            report['text_contrast'] = {'opacity': a, 'bg_dim': scrim_a,
                                        'median': round(med, 2), 'min': round(lo, 2)}
            ok &= rec('清晰背景 + 运行时纸色滤镜下正文仍可读（中位对比度 ≥ 4.5:1）',
                      med >= 4.5,
                      f'中位 {med:.2f}:1，最低 {lo:.2f}:1'
                      f'（面板不透明度 {a:.0%}，背景滤镜 {scrim_a:.0%}）')
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)
    return bool(ok)


def check_assets() -> bool:
    print('\n── 4. 成品资源 ──')
    ok = True
    for name in (BG.MASTER_NAME, BG.SOFT_NAME):
        p = IMG / name
        if not p.exists():
            ok &= rec(f'{name} 就位', False, '缺失')
            continue
        with Image.open(p) as im:
            good = im.size == (3840, 2160) and im.format == 'WEBP'
            size_mb = p.stat().st_size / 1048576
            ok &= rec(f'{name} 就位（16:9 · 3840×2160 · WebP）', good,
                      f'{im.size[0]}×{im.size[1]} {im.format} {size_mb:.2f} MB')
    # ★★★ 2026-10-17 修：这条原来是 `IMG.glob('title_bg*.png')` 一网打尽 ——
    #   把**启动窗口 splash 的底图**（`title_bg_splash.png` / `_splash_tall.png`）
    #   也当成"残留"了。那两张是**产品资产**：`tools/launcher_splash.py::_load_images`
    #   真的读它们（`tk.PhotoImage(file=tall)`），`developers/mutate_launchers.py`
    #   第 ⑳ 组还专门拿它们做变异对象。⇒ 只排除 splash 那两张，
    #   **主界面的 `title_bg*.png` 残留照样要抓**（成对，不是把条件放宽）。
    # [EN] ★★★ Fixed 2026-10-17: this used to be a blanket `IMG.glob('title_bg*.png')` --
    # [EN] which treated the **launcher splash backdrops** (`title_bg_splash.png` / `_splash_tall.png`)
    # [EN] as leftovers. Those two are **product assets**: `tools/launcher_splash.py::_load_images`
    # [EN] really reads them (`tk.PhotoImage(file=tall)`), and `developers/mutate_launchers.py` group 20
    # [EN] uses them as mutation targets. => Exclude only those two; leftover `title_bg*.png` for the
    # [EN] main screen must still be caught (paired, not a blanket relaxation).
    _splash_png = ('title_bg_splash.png', 'title_bg_splash_tall.png')
    leftovers = sorted(p.name for p in IMG.glob('title_bg*.png')
                       if p.name not in _splash_png)
    ok &= rec('没有残留的旧 PNG 背景（背景不再用 PNG）', not leftovers,
              '残留: ' + ', '.join(leftovers) if leftovers else '')
    return bool(ok)


def check_seal() -> bool:
    """两张背景都应在某个角盖一枚「婴宁」朱文印章。

    用「朱红像素（r 高、g 低、b 低）集中在某个角的方块」来量：印章是实色方印，
    红像素既多、又聚成近正方块；散点红花（g 偏高）不会命中。
    [EN] Both backgrounds should have a "婴宁" vermilion seal stamped in some corner.
    [EN] Measured by "vermilion pixels (high r, low g, low b) clustered into a near-square block in a
    [EN] corner": the seal is a solid square, so its red pixels are many and form a near-square blob;
    [EN] scattered red flowers (high g) won't match.
    """
    print('\n── 5. 「婴宁」印章 ──')
    ok = True
    for name in (BG.MASTER_NAME, BG.SOFT_NAME):
        p = IMG / name
        if not p.exists():
            ok &= rec(f'{name} 含朱红印章', False, '文件缺失')
            continue
        with Image.open(p) as im:
            W, H = im.size
            px = im.load()
            corners = {'tl': (0, 0, W // 2, H // 2),
                       'tr': (W // 2, 0, W, H // 2),
                       'bl': (0, H // 2, W // 2, H),
                       'br': (W // 2, H // 2, W, H)}
            best_k, best_c, best_box = None, 0, None
            for k, (x0, y0, x1, y1) in corners.items():
                xs, ys = [], []
                for y in range(y0 + 8, y1, 8):
                    for x in range(x0 + 8, x1, 8):
                        r, g, b = px[x, y]
                        if r > 140 and g < 110 and b < 100:
                            xs.append(x); ys.append(y)
                if len(xs) > best_c:
                    best_c, best_k = len(xs), k
                    best_box = (min(xs), min(ys), max(xs), max(ys)) if xs else None
            if best_box is None:
                ok &= rec(f'{name} 在某个角含朱红印章（婴宁）', False,
                          '没有任何角检出朱红像素')
                continue
            bbw = best_box[2] - best_box[0]
            bbh = best_box[3] - best_box[1]
            aspect = (bbw / bbh) if bbh else 0
            # ★ 2026-10-14 用户：「基于原图进行题字与印章排版」—— 现在是**竖排组合**
            #   （引首章 + 竖排「笑矣乎」题字 + 2 枚名号章），红像素聚成**竖长条**
            #   （aspect ≈ 0.34）而不是"近正方块"。判据跟着设计走：
            #   aspect 0.5~2.0 → **0.2~5.0**（允许竖长/横长的组合）。
            #   ⚠ "红像素 ≥50" 仍保留（防散点红花误中）。
            # [EN] ★ 2026-10-14 user: "compose the title and seals based on the original painting" --
            # [EN] it's now a **vertical combo** (leading seal + vertical "笑矣乎" title + 2 name
            # [EN] seals); red pixels cluster as a **vertical bar** (aspect ≈ 0.34), not a "near
            # [EN] square". The criterion follows the design: aspect 0.5~2.0 -> **0.2~5.0** (allow
            # [EN] vertical / horizontal combos). ⚠ "red pixels >= 50" is kept (guards against
            # [EN] scattered red flowers).
            good = best_c >= 50 and 0.2 <= aspect <= 5.0
            ok &= rec(f'{name} 在某个角含朱红印章（婴宁）', good,
                      f'最红角={best_k} 红像素≈{best_c} 方块长宽比≈{aspect:.2f}')
    return bool(ok)


def check_filter() -> bool:
    """运行时背景滤镜（BG_DIM + 纸色滤镜层）的接线验证。

    这是用户要求的新能力：背景图本身保持高清（见 check_pipeline），
    压暗交给运行时纸色滤镜层，滤镜浓度在天机「界面外观 → 背景滤镜」里用 BG_DIM 调。
    对话框是独立模态层、不在界面 Stack 里，因此**不受影响**（用户原话：
    「不透明度不要管对话框，只管初始画面和运行画面」）。
    [EN] Runtime background scrim (BG_DIM + paper-colored scrim) wiring verification.
    [EN] This is the new capability the user asked for: the background image stays HD (see check_pipeline),
    [EN] dimming is done at runtime by a paper-colored scrim layer, whose density is tuned by BG_DIM in
    [EN] Tianji's "Appearance -> Background scrim". Dialogs are a separate modal layer, not in the screen Stack,
    [EN] so they are **unaffected** (the user's words: "the opacity must not touch dialogs, only the start/run screens").
    """
    print('\n── 6. 运行时背景滤镜（BG_DIM + 纸色滤镜层）──')
    ok = True
    import ast as _ast
    from config import CFG, SPEC

    spec = SPEC.get('BG_DIM')
    ok &= rec('BG_DIM 配置存在且为 int（界面组）',
              bool(spec) and spec.get('type') == 'int' and spec.get('group') == '界面',
              str(spec.get('default')) if spec else '缺失')
    ok &= rec('BG_DIM 默认值 35、范围 0~70',
              bool(spec) and spec.get('default') == 35
              and spec.get('min') == 0 and spec.get('max') == 70,
              (f"default={spec.get('default')} min={spec.get('min')} "
               f"max={spec.get('max')}") if spec else '')

    from gui.app_flet import (bg_dim, make_bg_scrim, BG_DIM_DEFAULT,
                              BG_DIM_MAX, _BASE_INKC)
    # bg_dim 读 BG_DIM 并夹紧到 0~1
    # [EN] bg_dim reads BG_DIM and clamps to 0~1
    exp = max(0, min(BG_DIM_MAX, int(CFG.i('BG_DIM') or BG_DIM_DEFAULT))) / 100.0
    got = bg_dim()
    ok &= rec('bg_dim() 读 BG_DIM 并夹紧到 0~1',
              abs(got - exp) < 1e-9, f'bg_dim={got:.3f} 期望={exp:.3f}')

    # make_bg_scrim 返回纸色滤镜层：颜色 = 宣纸底色、不透明度 = bg_dim()
    # [EN] make_bg_scrim returns the paper-colored scrim: color = paper base, opacity = bg_dim()
    scrim = make_bg_scrim()
    paper_hex = _BASE_INKC['paper']
    ok &= rec('make_bg_scrim 返回纸色滤镜层（颜色 = 宣纸底色）',
              getattr(scrim, 'bgcolor', None) == paper_hex,
              f'bgcolor={getattr(scrim, "bgcolor", None)} 期望={paper_hex}')
    ok &= rec('make_bg_scrim 不透明度 = bg_dim()',
              abs((getattr(scrim, 'opacity', None) or -1) - got) < 1e-9,
              f'opacity={getattr(scrim, "opacity", None)} 期望={got:.3f}')

    # 接线：app_flet.py 里开始界面与运行界面的 Stack 都应调用 make_bg_scrim()。
    # 用 AST 数调用次数（≥2 表示两张界面都接了线）。
    # [EN] Wiring: in app_flet.py both the start screen and run screen Stacks should call make_bg_scrim().
    # [EN] Count call sites via AST (>=2 means both screens are wired).
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    tree = _ast.parse(src)
    n_calls = sum(1 for node in _ast.walk(tree)
                  if isinstance(node, _ast.Call)
                  and isinstance(node.func, _ast.Name)
                  and node.func.id == 'make_bg_scrim')
    ok &= rec('make_bg_scrim 在开始/运行界面都接了线（≥2 处调用）',
              n_calls >= 2, f'调用次数={n_calls}')
    return bool(ok)


def main() -> int:
    print('  背景图管线验证')
    src_ok = check_source()
    pipe_ok = check_pipeline()
    assets_ok = check_assets()
    seal_ok = check_seal()
    filter_ok = check_filter()
    report['ok'] = bool(src_ok and pipe_ok and assets_ok and seal_ok and filter_ok)
    report['failed'] = [s for s in report['steps'] if not s['ok']]
    (OUT / 'background_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    n = len(report['steps'])
    print(f'\n  共 {n} 项断言，失败 {len(report["failed"])} 项 → '
          f'{"全部通过" if report["ok"] else "有失败"}')
    if not report.get('source_ready'):
        print('  注意：还没接入文生图原图，当前界面用的是旧背景。')
        print('        原图放进 assets/images/bg/ 后跑 python make_art.py 即可。')
    for s in report['failed']:
        print(f'    [FAIL] {s["name"]}  {s["detail"]}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
