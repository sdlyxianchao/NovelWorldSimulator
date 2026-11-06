# -*- coding: utf-8 -*-
"""重新生成美术资源。

背景图现在来自**文生图**（实景：无锡鼋头渚春季），原图放在
`assets/images/bg/`，本脚本负责把它处理成界面用的两张。

用法：
    python make_art.py                      # 从 bg/ 里的原图构建背景 + 生成图标
    python make_art.py --bg                 # 只构建背景
    python make_art.py --icon               # 只生成图标
    python make_art.py --from 原图.png      # 指定原图（默认取 bg/ 里最大的那张）
    python make_art.py --res 2560x1440      # 指定输出分辨率（默认 3840x2160）
    python make_art.py --watercolor         # 本地淡彩水彩（不联网，出图 429 时的兜底）
    python make_art.py --reproc             # 强制重跑旧的程序化绘制（最后的兜底）

背景产物（assets/images/）：
    title_bg.webp        母版（16:9，默认 3840×2160）→ 开始界面（清晰高清）
    title_bg_soft.webp   运行界面用（同样清晰高清；压暗交给天机 BG_DIM 纸色滤镜层）

换背景图的流程：把新的文生图原图丢进 assets/images/bg/（旧的原图删掉或移走），
再跑一次本脚本。

English:
Regenerate art assets.
The background image now comes from **text-to-image** (real scene: Wuxi Yuantouzhu in spring).
The original image is placed in
`assets/images/bg/`; this script is responsible for processing it into the two used by the UI.
Usage:
    python make_art.py                      # build background from originals in bg/ + generate icons
    python make_art.py --bg                 # build background only
    python make_art.py --icon               # generate icons only
    python make_art.py --from original.png  # specify the original image (defaults to the largest one in bg/)
    python make_art.py --res 2560x1440      # specify output resolution (default 3840x2160)
    python make_art.py --watercolor         # local light-color watercolor (no network, fallback when generation returns 429)
    python make_art.py --reproc             # force rerun of old procedural drawing (last-resort fallback)
Background outputs (assets/images/):
    title_bg.webp        master (16:9, default 3840×2160) → start screen (crisp HD)
    title_bg_soft.webp   runtime screen (also crisp HD; dimming is done at runtime by the 天机 BG_DIM paper-colored scrim)
Procedure for changing the background image: drop the new text-to-image original into
assets/images/bg/ (delete or move away the old original),
then run this script once more.
"""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

OUT_DIR = APP_DIR / 'assets' / 'images'


def _parse_res(args: list) -> tuple[int, int]:
    for i, a in enumerate(args):
        if a == '--res' and i + 1 < len(args):
            try:
                w, h = args[i + 1].lower().split('x')
                return int(w), int(h)
            except Exception:
                pass
    return 3840, 2160


def _parse_from(args: list):
    for i, a in enumerate(args):
        if a == '--from' and i + 1 < len(args):
            return Path(args[i + 1])
    return None


def main():
    args = sys.argv[1:]
    only_bg = '--bg' in args
    only_icon = '--icon' in args
    only_start = '--start-logo' in args
    do_bg = only_bg or not only_icon
    do_icon = only_icon or not only_bg
    width, height = _parse_res(args)

    # 只圆角开始界面 Logo（不碰图标管线、不碰背景）。
    # [EN] Only round the start-screen logo (touches neither the icon pipeline nor the background).
    if only_start:
        from image_gen.round_start_logo import round_start_logo
        try:
            print(f'开始界面 Logo 加圆角：{round_start_logo()}')
        except FileNotFoundError as e:
            print(f'  [X] {e}')
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if do_bg:
        src = _parse_from(args)
        if '--watercolor' in args:
            # 本地淡彩水彩（不联网）—— 出图服务 429 时的兜底路线。
            # 详情见 image_gen/watercolor.py 顶部注释。
            # [EN] Local light-color watercolor (no network) —— fallback route when image generation service
            # [EN] returns 429.
            # [EN] See the top comments of image_gen/watercolor.py for details.
            from image_gen.watercolor import build as wc_build
            print(f'[本地水彩] 绘制淡彩背景（{width}×{height}）…')
            res = wc_build(OUT_DIR, width, height,
                           progress=lambda m: print('  ' + m))
            for k, v in res.items():
                print(f'  {k}: {v}')
        elif '--reproc' in args:
            from image_gen.background import save_backgrounds
            print(f'[兜底路线] 程序化绘制背景（{width}×{height}）…')
            res = save_backgrounds(OUT_DIR, width, height,
                                   progress=lambda m: print('  ' + m))
            print(f'背景共 {len(res)} 个文件 → {OUT_DIR}')
        else:
            from image_gen.background import build_from_source, find_ai_source
            use = src or find_ai_source()
            if use is None:
                print('  没有找到文生图原图。请把原图放进 '
                      'assets/images/bg/，或用 --from 指定路径。')
                print('  （旧路线：python make_art.py --reproc）')
                return
            print(f'从文生图原图构建背景（{width}×{height}）…')
            res = build_from_source(use, OUT_DIR, (width, height),
                                    progress=lambda m: print('  ' + m))
            if not res:
                print('  [X] 构建失败')
                return
            print(f'背景 → {OUT_DIR}')

    if do_icon:
        # `save_icons` 现在**一次写全五份**：界面用的三份 +
        # 窗口/任务栏用的 `assets/app_icon.png` / `.ico`。
        # 别再在这里单独补 app_icon —— 两处各画各的迟早不同步
        # （换配色后界面变了、任务栏还是旧图，就是这么来的）。
        # [EN] `save_icons` now writes all five at once: the three for the UI +
        # [EN] `assets/app_icon.png` / `.ico` for the window/taskbar.
        # [EN] Don't add app_icon separately here anymore —— drawing separately in two places will inevitably
        # [EN] fall out of sync
        # [EN] (after changing the color scheme the UI changed but the taskbar still had the old image; that's
        # [EN] where this comes from).
        from image_gen.icon import save_icons
        print('生成图标…')
        for k, v in save_icons(OUT_DIR).items():
            print(f'  图标[{k}]: {v}')

        # 开始界面 Logo 独立圆角（不在 icon 管线里，见 `image_gen/round_start_logo.py`）。
        # 放在图标生成之后：背景/图标重跑时，这块展示图的圆角不会被漏掉又变回方角。
        # [EN] The start-screen logo gets its own rounded corners (not in the icon pipeline; see
        # [EN] `image_gen/round_start_logo.py`). Placed after icon generation: when the background/icons are
        # [EN] regenerated, this display image's rounding won't be missed and revert to square.
        from image_gen.round_start_logo import round_start_logo
        try:
            print(f'  开始界面 Logo 已加圆角：{round_start_logo()}')
        except FileNotFoundError as e:
            print(f'  [跳过] 开始界面 Logo 圆角：{e}')

    print('完成。')


if __name__ == '__main__':
    main()
