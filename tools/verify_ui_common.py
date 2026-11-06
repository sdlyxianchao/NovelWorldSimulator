# -*- coding: utf-8 -*-
"""真机验证的公共工具：纯色背景 + 精确合成色 + 像素量测。

为什么需要「纯色背景」
----------------------
面板现在是半透明的（`UI_OPACITY` 可调），屏幕上的实际颜色是

    alpha × 面板色 + (1 - alpha) × 背景色

背景是一张水墨图，同一块面板在不同位置颜色都不同 —— 于是
「找某一种颜色的连续段」这类量测会直接失效。曾经就因此把
「叙事区改成半透明」误判成「布局坏了」（间距从 9px 跳到 561px）。

这里给验证脚本一张**纯色背景**，合成色就能精确算出来，量测重新变确定。
只用于**布局类**量测（间距、边界）。

要验证「背景真的透出来了」必须用**真背景图** —— 见 `tools/verify_opacity.py`。

关键点：合成用的 alpha **直接从界面自己的颜色表里读**（`C['panel']` 已经是
`#AARRGGBB`），不在测试里另抄一份透明度逻辑，避免「测试和实现对不上」。

English:
Common tool for real-device verification: solid color background + exact composited color +
pixel measurement.
Why "solid color background" is needed
----------------------
The panel is now semi-transparent (`UI_OPACITY` adjustable), so the actual on-screen color is
    alpha × panel color + (1 - alpha) × background color
The background is an ink-wash image, so the same panel has a different color at different
positions -- thus
measurements like "find the continuous segment of a certain color" directly fail. This once
caused
"making the narrative area semi-transparent" to be misjudged as "layout is broken" (spacing
jumped from 9px to 561px).
Here we give the verification script a **solid color background**, so the composited color can
be computed exactly and measurement becomes deterministic again.
Only used for **layout-type** measurements (spacing, boundaries).
To verify "the background really shows through", you must use a **real background image** -- see
`tools/verify_opacity.py`.
Key point: the alpha used for compositing is **read directly from the UI's own color table**
(`C['panel']` is already
`#AARRGGBB`), do not copy another transparency logic in the test, to avoid "test and
implementation not matching".
"""
from __future__ import annotations

import atexit
import hashlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

# ══════════════════════════════════════════════════════════════════════
#  整支脚本的硬超时（2026-10-17 加）
# [EN] Hard timeout for the whole script (added 2026-10-17)
# ══════════════════════════════════════════════════════════════════════
# 用户报的现象：「有大量的 flet working 窗口没退出」。
#
# 真机判据跑起来会拉起 `flet.exe` 客户端。脚本**卡在某个 await 上不动**时
# （收尾那一步永远到不了），窗口就一直开着 —— 桌面上一堆「Working...」。
# 回归器虽然 900 秒后会杀掉子进程，但那时窗口已经挂了十几分钟，
# 而且 `subprocess.run` 只杀直接子进程，`flet.exe` 是孙进程、会成为永久孤儿。
#
# 这里在 **import 时**按环境变量装一道硬超时：超过 `NWS_VERIFY_WATCHDOG` 秒
# 就自己关掉客户端并退出（退出码 3 = "跑不完"，不是"判据红"）。
# 由 `tools/run_all_verifications.py` 统一给值（默认 `TIMEOUT - 60`）。
# 90 支真机判据都 import 本模块 ⇒ 不必逐支改。
#
# ★ 不设环境变量时**什么都不做**（单独跑、调试时不希望被掐）。
# ★ 用 daemon 线程：正常退出时它跟着走，不会反过来拖住进程。
# [EN] The user reported: "a pile of flet working windows that never exit".
# [EN] A real-machine criterion launches the `flet.exe` client. When the script **gets stuck on
# [EN] some await** (never reaches the teardown), the window stays open -- the desktop fills with
# [EN] "Working..." windows. The regression harness does kill the child after 900s, but by then the
# [EN] window has been hanging for a quarter of an hour, and `subprocess.run` only kills the direct
# [EN] child; `flet.exe` is a grandchild and becomes a permanent orphan.
# [EN] So arm a hard timeout **at import** from the environment variable: past
# [EN] `NWS_VERIFY_WATCHDOG` seconds it closes its own clients and exits (code 3 = "did not finish",
# [EN] not "criterion red"). The harness supplies the value (default `TIMEOUT - 60`).
# [EN] All 90 real-machine criteria import this module => no per-script edits.
# [EN] ★ With no env var set it does **nothing** (standalone runs / debugging should not be cut off).
# [EN] ★ Daemon thread: it goes away with a normal exit and cannot itself drag out the exit.
def _arm_import_watchdog() -> None:
    """按 `NWS_VERIFY_WATCHDOG` 装硬超时；没设就什么都不做。"""
    import os
    raw = (os.environ.get('NWS_VERIFY_WATCHDOG') or '').strip()
    if not raw:
        return
    try:
        secs = float(raw)
    except ValueError:
        return
    if secs <= 0:
        return
    try:
        from util.flet_shutdown import arm_lifetime_watchdog
        arm_lifetime_watchdog(secs, code=3)
    except Exception:                      # noqa: BLE001 —— 兜底保护，装不上也别让判据起不来
        pass


_arm_import_watchdog()


def safe_rmtree(path: Path, **_kwargs) -> None:
    """删临时目录，**逐个顶层子项**删，且绝不因删除失败而中断调用方。

    `**_kwargs` 是为了能直接替换 `shutil.rmtree(p, ignore_errors=True)`
    这类调用（多余参数忽略），省得逐处改签名。

    为什么不能用 `shutil.rmtree(path, ignore_errors=True)`：本机环境的
    safe-delete 守卫在单次操作删除超过 50 个文件时会直接 `SystemExit(1)`
    （非交互环境没法确认），而且这个 `ignore_errors=True` **拦不住它** ——
    `SystemExit` 是 `BaseException`，不是 `OSError`。

    后果很实在：验证脚本的 `finally` 里写完 `rmtree` 才写 JSON 报告、
    才 `shutdown(page)`，被这么一杀就变成「报告是上一次的旧文件 + 窗口不关」，
    而且看起来像「测试通过了」（旧报告 `ok=True`）。

    这里改成逐项删（每次远低于阈值），并用 `except BaseException` 兜底：
    **删不掉就算了**，临时目录残留远不如"报告没写出来"严重。

    更好的做法是把临时目录直接建在系统临时区（`tempfile.mkdtemp`），
    顺带避免在用户 `Projects/` 里留下假项目 —— 见 `tools/verify_run_control.py`。
    
        English:
    Delete the temp directory, deleting **each top-level child item**, and never interrupt the
    caller due to a deletion failure.
        `**_kwargs` is so that calls like `shutil.rmtree(p, ignore_errors=True)` can be replaced directly
        (extra arguments ignored), saving the trouble of changing the signature at every call site.
        Why not use `shutil.rmtree(path, ignore_errors=True)`: on this machine, the
        safe-delete guard will directly `SystemExit(1)` when a single operation deletes more than 50 files
        (cannot confirm in a non-interactive environment), and this `ignore_errors=True` **cannot stop it** --
        `SystemExit` is a `BaseException`, not an `OSError`.
        The consequence is very real: the verification script's `finally` writes `rmtree` before writing the JSON report,
        and only then `shutdown(page)`; being killed like this turns into "the report is the old file from last time + the window doesn't close",
        and it looks like "the test passed" (old report `ok=True`).
        Here it is changed to delete item by item (each time far below the threshold), with `except BaseException` as a fallback:
        **if it can't be deleted, so be it**; a leftover temp directory is far less serious than "the report not being written".
        A better approach is to create the temp directory directly in the system temp area (`tempfile.mkdtemp`),
        which also avoids leaving fake projects in the user's `Projects/` -- see `tools/verify_run_control.py`.
    """
    if not path.exists():
        return
    for child in list(path.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink()
        except BaseException:                               # noqa: BLE001
            pass
    try:
        path.rmdir()
    except BaseException:                                   # noqa: BLE001
        pass

# 纯色背景：深灰蓝。跟纸色差得远，合成前后的颜色都好区分
# [EN] Solid color background: dark gray-blue. Far enough from the paper color that both before and
# [EN] after compositing the colors are easy to distinguish.
FLAT_BG = (46, 62, 74)
_FLAT_NAME = '_verify_flat_bg.png'


def flat_bg_path() -> Path:
    """生成（或复用）一张纯色背景图。
        English:
    Generate (or reuse) a solid color background image.
    """
    out = APP_DIR / 'assets' / 'screenshots' / _FLAT_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        Image.new('RGB', (256, 144), FLAT_BG).save(out)
    return out


def patch_flat_background():
    """把 `gui.app_flet.get_bg` 换成返回纯色背景。

    必须在构建任何界面**之前**调用（开始界面自己会取背景图）。
    `get_or_generate_bg()` 内部调用 `get_bg`，所以只补一个就够。

    返回被替换掉的函数，便于测试结束时还原。
    
        English:
    Replace `gui.app_flet.get_bg` to return a solid color background.
        Must be called **before** building any UI (the start screen fetches its own background image).
        `get_or_generate_bg()` internally calls `get_bg`, so patching just one is enough.
        Returns the replaced function, for restoring at the end of the test.
    """
    import gui.app_flet as G
    flat = str(flat_bg_path())
    original = G.get_bg
    G.get_bg = lambda *a, **k: flat
    return original


def hex_rgb(s: str) -> tuple[int, int, int]:
    """`#RRGGBB` / `#AARRGGBB` → (r, g, b)；同时返回自带 alpha 的部分。
        English:
    `#RRGGBB` / `#AARRGGBB` → (r, g, b); also returns the alpha part if present.
    """
    c = str(s).lstrip('#')
    if len(c) == 8:
        c = c[2:]
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def hex_alpha(s: str) -> float:
    """取颜色自带的 alpha（8 位色）；6 位色视为完全不透明。
        English:
    Take the color's own alpha (8-digit color); 6-digit colors are treated as fully opaque.
    """
    c = str(s).lstrip('#')
    if len(c) == 8:
        return int(c[0:2], 16) / 255.0
    return 1.0


def composite(color: str, bg: tuple = FLAT_BG) -> tuple[int, int, int]:
    """把（可能半透明的）界面颜色合成到纯色背景上，得到屏幕上应有的颜色。
        English:
    Composite the (possibly translucent) UI color onto a solid background to get the on-screen
    color.
    """
    r, g, b = hex_rgb(color)
    a = hex_alpha(color)
    return tuple(round(a * c + (1 - a) * bg[i]) for i, c in enumerate((r, g, b)))


def panel_rgb() -> tuple[int, int, int]:
    """运行界面各面板（含叙事/输出区）在屏幕上的合成色。
        English:
    On-screen composited color of each panel of the running UI (including the narrative/output
    area).
    """
    from gui.app_flet import C
    return composite(C['panel_glass'])


def field_rgb() -> tuple[int, int, int]:
    """输入框/下拉在屏幕上的合成色（另有 85% 下限，所以和面板不同）。
        English:
    On-screen composited color of input boxes/dropdowns (there is also an 85% lower bound, so unlike
    the panels).
    """
    from gui.app_flet import C
    return composite(C['input_bg'])


def image_of(png) -> Image.Image:
    """接受三种输入：截图字节、图片路径、已打开的 PIL Image。
        English:
    Accepts three kinds of input: screenshot bytes, image path, or an already-open PIL Image.
    """
    if isinstance(png, Image.Image):
        return png if png.mode == 'RGB' else png.convert('RGB')
    if isinstance(png, (bytes, bytearray)):
        return Image.open(io.BytesIO(png)).convert('RGB')
    return Image.open(png).convert('RGB')


def _near(p, rgb, tol) -> bool:
    return all(abs(p[i] - rgb[i]) <= tol for i in range(3))


def find_runs_v(im: Image.Image, rgb, x: int, tol: int = 8,
                y_from: int = 0, y_to: int | None = None) -> list[tuple[int, int]]:
    """在某一列上找颜色连续段（y 方向）。
        English:
    Find a contiguous color segment along a column (y direction).
    """
    W, H = im.size
    x = min(max(x, 0), W - 1)
    y_to = H if y_to is None else min(y_to, H)
    runs, cur = [], None
    for y in range(max(0, y_from), y_to):
        if _near(im.getpixel((x, y)), rgb, tol):
            if cur is None:
                cur = y
        elif cur is not None:
            runs.append((cur, y - 1))
            cur = None
    if cur is not None:
        runs.append((cur, y_to - 1))
    return [r for r in runs if r[1] - r[0] > 3]


def find_runs_h(im: Image.Image, rgb, y: int, tol: int = 8) -> list[tuple[int, int]]:
    """在同一行上找颜色连续段（x 方向）。
        English:
    Find a contiguous color segment along a row (x direction).
    """
    W, H = im.size
    y = min(max(y, 0), H - 1)
    runs, cur = [], None
    for x in range(W):
        if _near(im.getpixel((x, y)), rgb, tol):
            if cur is None:
                cur = x
        elif cur is not None:
            runs.append((cur, x - 1))
            cur = None
    if cur is not None:
        runs.append((cur, W - 1))
    return [r for r in runs if r[1] - r[0] > 3]


def bright_runs_v(png, x: int, thr: int = 150, min_len: int = 4,
                  tol_px: int = 6) -> list:
    """某一列上「亮面」的连续段（合并被描边切开的相邻段）。

    **为什么需要它**：半透明面板是**可以嵌套**的 —— 中栏的卡片底色
    （输入框纸色 85%）叠在叙事区面板上，合成出来的颜色**既不等于**
    `panel_rgb()` 也**不等于** `field_rgb()`（实测是 (245,244,238)）。
    所以"按颜色找面"在多层面板里必然失手。

    改成按**亮度**找：界面上的纸面/卡片都是亮的，背景（`FLAT_BG` 或彩墨图）
    是暗的，一条亮度阈值就把"面"和"空"分开了，与嵌套层数无关。
    
        English:
    Contiguous segment of "bright surface" along a column (merging adjacent segments split by an
    outline).
        **Why it is needed**: translucent panels **can be nested** —— the middle column's card base
        (input box paper color 85%) stacked on the narrative area panel composites to a color that is **neither equal to**
        `panel_rgb()` **nor** `field_rgb()` (measured as (245,244,238)).
        So "find surfaces by color" inevitably fails in multi-layer panels.
        Change to finding by **brightness**: paper surfaces/cards in the UI are all bright, the background (`FLAT_BG` or the ink-wash image)
        is dark, and a single brightness threshold separates "surface" from "empty", independent of nesting depth.
    """
    im = image_of(png)
    W, H = im.size
    x = min(max(x, 0), W - 1)
    g = im.convert('L')
    # ★ 取 `x` 左右各 2 列（共 5 列）的**中位数**，不是单列像素。
    #   单列取样有个隐蔽的坑：那一列**撞上一行深色文字**就被压断，
    #   于是"一个面"被切成两段。实测（2026-10-06）拍说明书插图时，
    #   英文界面下 x=W/2 正好撞上一行字 → 面被切成 (0,264)+(276,939)，
    #   裁出来的中栏图只有 211px 高，而中文 770px（同内容差 3.6 倍，
    #   查了半天才发现是量测工具的锅，不是界面的锅）。
    #   取中位数而不是"多数投票"：5 列里 2 列被文字压暗也仍取到亮值。
    # [EN] ★ Take the median of `x` plus 2 columns on each side (5 columns total), not a single column of
    # [EN] pixels.
    # [EN] Single-column sampling has a hidden pitfall: if that column happens to hit a row of dark text,
    # [EN] it gets cut off,
    # [EN] so "one face" is split into two segments. Measured (2026-10-06) when photographing manual
    # [EN] illustrations,
    # [EN] under the English UI, x=W/2 happened to hit a line of text -> the face was split into
    # [EN] (0,264)+(276,939),
    # [EN] the cropped middle-column image was only 211px tall, while the Chinese one was 770px (same
    # [EN] content differs by 3.6x,
    # [EN] took a long time to figure out it was the measurement tool's fault, not the UI's).
    # [EN] Take the median rather than "majority vote": even if 2 of the 5 columns are darkened by text, a
    # [EN] bright value is still obtained.
    xs = [min(max(x + dx, 0), W - 1) for dx in (-2, -1, 0, 1, 2)]
    runs: list = []
    cur = None
    for y in range(H):
        vals = sorted(g.getpixel((xx, y)) for xx in xs)
        if vals[len(vals) // 2] >= thr:
            if cur is None:
                cur = y
        elif cur is not None:
            runs.append((cur, y - 1))
            cur = None
    if cur is not None:
        runs.append((cur, H - 1))
    runs = [r for r in runs if r[1] - r[0] + 1 >= min_len]
    merged: list = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= tol_px:
            merged[-1] = (merged[-1][0], max(merged[-1][1], r[1]))
        else:
            merged.append(r)
    return merged


def accent_bars(png, rgb, *, x_from: int = 0, x_to: int | None = None,
                tol: int = 40, min_len: int = 20) -> list:
    """找「同色竖条」，返回 `[(x, y0, y1)]`（按长度降序）。

    卡片靠**左侧竖色条**区分类型（赭金=一幕 / 靛青=同时 / 朱砂=事件）。
    这个函数就是**在屏幕上**确认那些竖条真的画出来了 —— 控件树里有，
    不等于渲染出来有（描边色不带 alpha，所以颜色是准的，不必合成）。

    `min_len` 顺手把正文里的彩色小字滤掉：一行 16px 的字凑不出 20px 的竖条。
    
        English:
    Find "same-color vertical bars", returning `[(x, y0, y1)]` (sorted descending by length).
        Cards are distinguished by type via a **left-side vertical color bar** (ochre-gold = one act / indigo = simultaneous / cinnabar = event).
        This function **confirms on screen** that those vertical bars are actually drawn —— existing in the widget tree
        does not mean being rendered (outline colors carry no alpha, so the colors are exact and no compositing is needed).
    `min_len` conveniently filters out small colored text in the body: a line of 16px text cannot
    form a 20px vertical bar.
        Locate "the largest panel of the given color", returning (x0, y0, x1, y1).
    """
    im = image_of(png)
    W, H = im.size
    x_to = W if x_to is None else min(x_to, W)
    cols: list = []
    for x in range(max(0, x_from), x_to):
        n = 0
        for y in range(H):
            if _near(im.getpixel((x, y)), rgb, tol):
                n += 1
        if n >= min_len:
            cols.append(x)
    groups: list = []
    for x in cols:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])
    out: list = []
    for g in groups:
        x = g[len(g) // 2]
        runs, cur = [], None
        for y in range(H):
            if _near(im.getpixel((x, y)), rgb, tol):
                if cur is None:
                    cur = y
            elif cur is not None:
                runs.append((cur, y - 1))
                cur = None
        if cur is not None:
            runs.append((cur, H - 1))
        for y0, y1 in runs:
            if y1 - y0 + 1 >= min_len:
                out.append((x, y0, y1))
    return sorted(out, key=lambda r: -(r[2] - r[1]))


def panel_bbox(png, rgb, tol: int = 8, y_from: int = 0, y_to: int | None = None,
               min_h: int = 8):
    """定位「最大的一块该颜色面板」，返回 (x0, y0, x1, y1)。

    做法：先在中线那一列找最长的连续段拿到 y 范围，再在它的中点那一行
    找最长的连续段拿到 x 范围。够用且不依赖任何坐标常量。

    `y_from`/`y_to` 限制搜索的纵向范围，`min_h` 过滤太薄的条带 ——
    界面上常有好几块颜色相近的面板（标题块 / 菜单卡 / 对话框纸面），
    不限制范围就会定位到错的那一块（踩过：把开始界面的标题块当成了对话框纸面）。
    
        English:
    Approach: first find the longest contiguous segment in the center column to get the y range,
    then in the row at its midpoint
        find the longest contiguous segment to get the x range. Sufficient and independent of any coordinate constants.
    `y_from`/`y_to` restrict the vertical search range, `min_h` filters out strips that are too thin
    ——
        the UI often has several panels with similar colors (title block / menu card / dialog paper surface),
        and without restricting the range it will locate the wrong one (been there: took the start screen's title block for the dialog paper surface).
        Number of vertical blank pixels between "the upper panel" and "the lower panel" in the middle column.
    """
    im = image_of(png)
    W, _ = im.size
    vruns = find_runs_v(im, rgb, W // 2, tol, y_from=y_from, y_to=y_to)
    vruns = [r for r in vruns if r[1] - r[0] >= min_h]
    if not vruns:
        return None
    y0, y1 = max(vruns, key=lambda r: r[1] - r[0])
    hruns = find_runs_h(im, rgb, (y0 + y1) // 2, tol)
    if not hruns:
        return None
    x0, x1 = max(hruns, key=lambda r: r[1] - r[0])
    return (x0, y0, x1, y1)


def vertical_gap_between(png, top_rgb, bottom_rgb, tol: int = 8,
                         y_from: int = 0) -> tuple[int, dict]:
    """中栏上「上面那块面板」与「下面那块面板」之间的垂直空白像素数。

    返回 (间距, 细节)。间距为 -1 表示没找到（量测失效，不是布局坏了）。
    
        English:
    Returns (gap, detail). A gap of -1 means not found (measurement failed, not that the layout is
    broken).
        Brightness statistics of the panel surface.
    """
    im = image_of(png)
    W, _ = im.size
    x = W // 2
    top = find_runs_v(im, top_rgb, x, tol, y_from=y_from)
    bot = find_runs_v(im, bottom_rgb, x, tol, y_from=y_from)
    detail = {'x': x,
              'top_runs': top,
              'bottom_runs': bot,
              'top_rgb': tuple(top_rgb),
              'bottom_rgb': tuple(bottom_rgb)}
    if not top or not bot:
        detail['why'] = 'one of the colours was not found'
        return -1, detail
    t = max(top, key=lambda r: r[1] - r[0])          # 叙事区 = 最长的那段
    b = bot[0]                                       # 命令栏 = 第一段
    if b[0] < t[1]:                                  # 顺序不对，取命令栏里最靠下的
    # [EN] Narrative area = the longest segment
    # [EN] Command bar = the first segment
    # [EN] Order is wrong, take the bottom-most one in the command bar
        b = max(bot, key=lambda r: r[0])
    detail['narrative_run'] = t
    detail['cmd_run'] = b
    return b[0] - t[1] - 1, detail


# ── 透明度量测（用真背景图时）──
# [EN] ── Opacity measurement (when using a real background image) ──
def surface_stats(im: Image.Image, bbox, keep_ratio: float = 0.65) -> dict:
    """面板表面的亮度统计。

    只统计**较亮**的那部分像素（用亮度分位数自动卡阈值），
    把文字、图标这类深色内容排除掉 —— 否则「表面是否均匀」会被文字干扰。
    
        English:
    Only statistics over the **brighter** pixels (threshold set automatically via a brightness
    quantile),
        excluding dark content such as text and icons —— otherwise "is the surface uniform" would be disturbed by text.
        Pixel difference of the same panel at two opacities (measuring "how much background bleeds in").
    """
    x0, y0, x1, y1 = bbox
    px = [im.getpixel((x, y)) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    if not px:
        return {'n': 0, 'mean': 0.0, 'std': 0.0}
    lums = sorted(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in px)
    cut = lums[max(0, int(len(lums) * (1 - keep_ratio)))]
    keep = [p for p in px
            if (0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]) >= cut]
    n = len(keep)
    mean = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in keep) / n
    var = sum(((0.299 * r + 0.587 * g + 0.114 * b) - mean) ** 2
              for r, g, b in keep) / n
    return {'n': n, 'mean': mean, 'std': var ** 0.5,
            'cut': cut}


def region_diff(im_a: Image.Image, im_b: Image.Image, bbox) -> dict:
    """同一块面板在两种不透明度下的像素差（衡量「背景掺进来多少」）。

    返回 diff 的均值与标准差：
    - mean 大 = 面板颜色整体变了（背景确实掺进来了）
    - std 大 = 变化不均匀、带着背景的花纹（不是被均匀涂了一层灰）
    
        English:
    Returns the mean and standard deviation of the diff:
        - large mean = panel color changed overall (background really did bleed in)
        - large std = the change is non-uniform, carrying the background's patterns (not a uniform gray wash)
        Temporarily point the **project root directory** to `base` (returns the original value, which the caller can restore during teardown).
    """
    x0, y0, x1, y1 = bbox
    diffs = []
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            a = im_a.getpixel((x, y))
            b = im_b.getpixel((x, y))
            diffs.append(sum(abs(a[i] - b[i]) for i in range(3)) / 3.0)
    if not diffs:
        return {'n': 0, 'mean': 0.0, 'std': 0.0}
    n = len(diffs)
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / n
    return {'n': n, 'mean': mean, 'std': var ** 0.5}


def find_caret(card):
    """在控件树里找**展开三角**（`content` 是右/下箭头的 `ft.Icon`，且挂了 `on_click`）。

    ★ 为什么放在公共模块：拾卷的验证与回收站的验证都要用它，而两个脚本**互不 import**
      （一个崩了不该拖死另一个）。放这里，两边各调一次，实现只有一份。
    ⚠ `ft.Icon` 的字段是 **`icon`**，不是 `name`（Flet 1.0 改名）—— 产品代码正是
      因为写了 `.name` 才"点了永远打不开"，所以判据这里也必须读 `icon`。

        English:
    Find the **expand caret** in a control tree (`content` is a right/down `ft.Icon` with an
    `on_click`).
    ★ Why it lives here: both the Pick-a-Volume check and the recycle-bin check need it, and the two
      scripts **do not import each other** (one crashing must not take the other down). One copy.
    ⚠ `ft.Icon`'s field is **`icon`**, not `name` -- the product failed to expand exactly because it
      wrote `.name`, so the criterion must read `icon` too.
    """
    import flet as _ft
    hit = [None]

    def _walk(c, depth=0):
        if depth > 20 or c is None or hit[0] is not None:
            return
        inner = getattr(c, 'content', None)
        if isinstance(inner, _ft.Icon) and getattr(inner, 'icon', None) in (
                _ft.Icons.KEYBOARD_ARROW_RIGHT, _ft.Icons.KEYBOARD_ARROW_DOWN):
            if getattr(c, 'on_click', None) is not None:
                hit[0] = c
                return
        kids = getattr(c, 'controls', None)
        if isinstance(kids, list):
            for x in kids:
                _walk(x, depth + 1)
        if inner is not None and not isinstance(inner, (str, int, float)):
            _walk(inner, depth + 1)

    _walk(card)
    return hit[0]


# ══════════════════════════════════════════════════════════════════════
#  判据**绝对不许**改动用户的真实配置（2026-10-22 事故后加）
# [EN] Criteria must **never** modify the user's real config (added after the 2026-10-22 incident)
# ══════════════════════════════════════════════════════════════════════
# 事故经过（真的发生在这台机器上）：
#   `verify_save_close` 的 B2 用 `{'entries': []}` 打开「AI 模型配置 → 新建模型」并**点了一下保存**。
#   产品把"空表 + 新条目"写回 `llm_models.json` ⇒ 用户真实的 4 条模型（其中两条的密钥
#   **只存在于那个文件里**，`.env` 里没有）被覆盖成一条夹具 `probe-model-x`。
#   用户第二天打开程序：**一个模型都没有了**。
#
# ★ 为什么"每个判据自己记得隔离"不够：要靠人记得的东西一定会漏（项目目录隔离
#   `isolate_projects_dir` 早就有了，模型登记表却一直没有对应的东西）。
#   ⇒ 这里在 **import 时**就钉住，90 支真机判据全都不用改：
#     · 把真实登记表**复制**到临时目录再钉过去 —— 判据读到的内容与真实一致（行为不变），
#       但任何写都只写副本；
#     · 再挂一道 `atexit` 护栏：跑完比对 `.env` / `llm_models.json` / `agents/*.md` 的哈希，
#       变了就**大声报**（只报不回滚 —— 自动回滚会把用户的正当改动一起冲掉）。
# [EN] What happened (on this machine): `verify_save_close`'s B2 opened "AI model config -> new model"
# [EN] with `{'entries': []}` and **clicked Save once**. The product wrote back "empty table + new
# [EN] entry" into `llm_models.json` => the user's real 4 models (two of whose keys existed **only
# [EN] inside that file**) became one fixture entry `probe-model-x`. Next day: **no models at all**.
# [EN] ★ Why "each criterion remembering to isolate" is not enough: anything that relies on people
# [EN] remembering will be forgotten (project-dir isolation `isolate_projects_dir` existed for ages;
# [EN] there was never an equivalent for the model registry). => Pin it **at import time** so all 90
# [EN] real-device criteria are covered without edits: **copy** the real registry to a temp dir and
# [EN] pin there (reads match reality, writes hit only the copy), plus an `atexit` guard that compares
# [EN] `.env` / `llm_models.json` / `agents/*.md` hashes and **shouts** if they changed (report only,
# [EN] never roll back -- auto-rollback would clobber the user's legitimate edits).
def _hash(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ''
    except OSError:
        return ''


def _user_config_files() -> list[Path]:
    out = [APP_DIR / '.env', APP_DIR / 'llm_models.json']
    agents = APP_DIR / 'agents'
    if agents.is_dir():
        out += sorted(agents.glob('*.md'))
    return out


def _pin_model_registry() -> None:
    """把模型登记表钉到临时副本上（import 即生效，进程结束才失效）。"""
    try:
        from llm import models as _M
    except Exception:                                     # noqa: BLE001
        return
    real = _M.path()
    try:
        tmpdir = Path(tempfile.mkdtemp(prefix='nws_home_models_'))
        copy = tmpdir / real.name
        if real.is_file():
            shutil.copy2(real, copy)          # ★ 复制而不是留空：判据读到的内容要与真实一致
        _M.pin_path(copy)
    except Exception:                                     # noqa: BLE001
        return


_pin_model_registry()
_CONFIG_BEFORE = {str(p): _hash(p) for p in _user_config_files()}


def _user_config_guard() -> None:
    """收尾比对：判据有没有动过用户的真实配置。**只报不改。**"""
    changed = []
    for path_s, before in _CONFIG_BEFORE.items():
        now = _hash(Path(path_s))
        if now != before:
            changed.append(Path(path_s).name)
    if changed:
        print('\n  ★★★ 判据动过用户的真实配置（应当隔离！）：'
              f'{[c for c in changed][:6]}', flush=True)


atexit.register(_user_config_guard)


def isolate_projects_dir(base) -> str:
    """把**项目根目录**临时指到 `base`（返回原值，调用方收尾时可以还原）。

    为什么必须隔离 —— 两个理由，都是踩出来的：

    1. **会污染用户的真实项目列表。** 验证脚本都要造项目，默认落在
       `CFG.projects_dir()`（用户真实目录）。本机的批量删除守卫经常拦住
       收尾的 `rmtree`，于是"界面排查临时""导出验证"这类夹具会一直留在
       用户的「拾卷」列表里 —— 本机就攒了 8 个。
    2. **让断言依赖环境。** `verify_resume_menu.py` 有一条
       「一个项目都没有时「拾卷」该灰掉」—— 用户自己建过项目之后，
       这条会**假失败**（本机的 2 个残留项目就是这么把它搞挂的）。

    `CFG.set` 只改内存（`save()` 才写盘），所以这个改动不会落到 `.env`。
    
        English:
    Why isolation is mandatory —— two reasons, both learned the hard way:
    1. **It pollutes the user's real project list.** Verification scripts all create projects, which
    by default land in
        `CFG.projects_dir()` (the user's real directory). The local bulk-delete guard often blocks the
           teardown `rmtree`, so fixtures like "UI triage temp" and "export verification" stay forever in
           the user's "Shijuan" list —— 8 have accumulated on this machine.
           2. **It makes assertions environment-dependent.** `verify_resume_menu.py` has a case
        "'Shijuan' should be grayed out when there are no projects" —— after the user has created their own projects,
           this **falsely fails** (the local 2 leftover projects are exactly what broke it).
    `CFG.set` only changes memory (`save()` writes to disk), so this change will not land in `.env`.
    """
    from pathlib import Path as _P
    from config import CFG
    old = CFG.s('DEFAULT_PROJECTS_DIR') or ''
    _P(base).mkdir(parents=True, exist_ok=True)
    CFG.set('DEFAULT_PROJECTS_DIR', str(_P(base)))
    return old


# ══════════════════════════════════════════════════════════════
#  摄取对话框「AI 优化对话」栏：气泡有没有被右边缘裁掉
# [EN] Ingest dialog "AI optimize conversation" column: whether the bubble is clipped by the right edge
# ══════════════════════════════════════════════════════════════
GOLD = (0xc9, 0xa2, 0x4e)      # 对话框内层描金线
PANE_BORDER = (0xd9, 0xc9, 0xa3)   # 面板淡金边（`C['border']`）
AI_BG = (0xf2, 0xec, 0xe0)     # AI 气泡底色
USER_BG = (0xe8, 0xee, 0xf6)   # 用户气泡底色
# [EN] Dialog inner gold stroke line
# [EN] Panel light gold border (`C['border']`)
# [EN] AI bubble background color
# [EN] User bubble background color


def _c_near(c, t, tol) -> bool:
    return all(abs(c[i] - t[i]) <= tol for i in range(3))


def chat_pane_clip(png, *, band=(0.32, 0.72)) -> dict:
    """量「AI 优化对话」那栏的文字有没有越过面板右边界。

    为什么需要它（2026-10-05 用户报的 bug）
    --------------------------------------
    `_add_chat` 里气泡是 `ft.Row([bubble, Container(expand=True)])` 的**非 flex** 子控件
    —— Row 会给非 flex 子控件**无限宽**约束，于是气泡里的 `Text` 不换行，
    整段横向涨到面板外被裁掉：屏幕上就是「软件给我的字和我打的回复
    都看不见，像被右边吞掉了」。

    **这个 bug 有个很好的像素特征**：被裁时气泡底色一直铺到面板右边界、
    把那条淡金竖线盖住 → 竖线探测少一根；而且栏内墨迹的最右 x ≥ 面板右边界。
    所以判据就用这两个量：`lane = 面板右边界 − 墨迹最右 x`，`lane >= 6` 才算好。

    ⚠ 量测范围**必须夹在面板自己的上下边界之内**：对话框的纸边（
    `paper_frame` 的外墨线）也是一条暗线，跟着一起扫就会得到
    「墨迹贴着右边」的假阳性（第一版就踩了：改动前后都算出 lane=-7）。

    返回 dict（`verdict` = 'OK' / 'CLIPPED'，其余字段用于打表核对）：
        pane_right  面板应有的右边界 x（由左边框 + 对话框内缩反推，不怕被盖住）
        borders     探到的淡金竖线 x（正常 4 根；右边界被气泡盖住时只有 3 根）
        ai_bg        AI 气泡底色的横向范围
        user_bg      用户气泡底色的横向范围
        ink_max      右栏墨迹最右 x
        ink_rows     右栏归并出的文字行数（换行了才会 > 消息条数）
        lane         pane_right − ink_max
    
        English:
    Measure whether the text in the "AI 优化对话" column crosses the panel's right boundary.
        Why it's needed (bug reported by user on 2026-10-05)
        --------------------------------------
        In `_add_chat`, the bubble is a **non-flex** child of `ft.Row([bubble, Container(expand=True)])`
        — Row gives non-flex children an **unbounded width** constraint, so the `Text` inside the bubble doesn't wrap,
        the whole paragraph stretches horizontally past the panel and gets clipped: on screen it looks like "the text the software gives me and the reply I typed
        are both invisible, like they're swallowed by the right edge".
        **This bug has a very good pixel signature**: when clipped, the bubble's background color extends all the way to the panel's right boundary,
        covering that pale gold vertical line → one fewer vertical line detected; and the rightmost x of the ink in the column is ≥ the panel's right boundary.
        So the criterion uses these two quantities: `lane = panel right boundary − rightmost ink x`, and only `lane >= 6` counts as good.
        ⚠ The measurement range **must be clamped within the panel's own top and bottom boundaries**: the dialog's paper edge (
        the outer ink line of `paper_frame`) is also a dark line, and scanning it together yields
        a false positive of "ink pressed against the right edge" (the first version fell into this: both before and after the change it computed lane=-7).
        Returns a dict (`verdict` = 'OK' / 'CLIPPED', remaining fields used for tabulation and cross-checking):
            pane_right  the panel's expected right boundary x (inferred from left border + dialog inset, not afraid of being covered)
            borders     detected pale gold vertical line x positions (normally 4; only 3 when the right boundary is covered by a bubble)
            ai_bg       horizontal extent of the AI bubble's background color
            user_bg     horizontal extent of the user bubble's background color
            ink_max     rightmost x of ink in the right column
            ink_rows    number of text lines merged out of the right column (only > message count when wrapping occurred)
            lane        pane_right − ink_max
    """
    im = Image.open(png).convert('RGB')
    W, H = im.size
    px = im.load()

    def col_cov(x, rgb, y0, y1, tol=6):
        return sum(1 for y in range(y0, y1) if _c_near(px[x, y], rgb, tol)) \
            / max(1, y1 - y0)

    # 对话框内层描金线（取屏幕中段做覆盖率，对话框在哪儿都稳）
    # [EN] Dialog inner gold stroke line (use the middle section of the screen for coverage, stable no
    # [EN] matter where the dialog is)
    gy0, gy1 = int(H * 0.2), int(H * 0.8)
    gold_cols = [x for x in range(W) if col_cov(x, GOLD, gy0, gy1, 30) > 0.5]
    g_l, g_r = (min(gold_cols), max(gold_cols)) if gold_cols else (0, W - 1)

    y0, y1 = int(H * band[0]), int(H * band[1])
    raw = [x for x in range(g_l + 2, g_r - 1)
           if col_cov(x, PANE_BORDER, y0, y1) > 0.6]
    groups: list[list[int]] = []
    for x in raw:
        if groups and x - groups[-1][-1] <= 3:
            groups[-1].append(x)
        else:
            groups.append([x])
    borders = [int(sum(g) / len(g)) for g in groups]
    if not borders:
        return {'size': [W, H], 'gold': [g_l, g_r], 'borders': [],
                'pane_w': None, 'pane_right': g_r - 17, 'ai_bg': None,
                'user_bg': None, 'ink_max': 0, 'ink_rows': 0, 'lane': 0,
                'verdict': 'NO_PANE'}

    inset = borders[0] - g_l
    pane_w = (borders[1] - borders[0]) if len(borders) >= 4 else None
    pane_right = borders[-1] if len(borders) >= 4 else (g_r - inset)
    pane_left = borders[-2] if len(borders) >= 4 else (pane_right - pane_w if pane_w
                                                       else borders[-1])

    # 面板的上下边界：拿左边框那条线自己的纵向连续段（夹住纸边那条横线）
    # [EN] Panel top and bottom boundaries: take the vertical continuous segment of the left border line
    # [EN] itself (the horizontal line that pinches the paper edge)
    ys_border = [y for y in range(H) if _c_near(px[borders[0], y], PANE_BORDER, 8)]
    runs: list[list[int]] = []
    for y in ys_border:
        if runs and y - runs[-1][-1] <= 2:
            runs[-1].append(y)
        else:
            runs.append([y])
    runs = [r for r in runs if len(r) > 40]
    pane_top, pane_bot = (min(runs[0]), max(runs[-1])) if runs else (y0, y1)
    # 再往里收：气泡的底色本身也可能贴边，量的是"字"不是"框"
    # [EN] Go further inward: the bubble's background color itself may also hug the edge; what is measured
    # [EN] is "text", not "frame"
    vy0, vy1 = pane_top + 6, pane_bot - 6

    def bg_extent(rgb, tol=5):
        xs = [x for x in range(pane_left, pane_right + 1)
              for y in range(vy0, vy1) if _c_near(px[x, y], rgb, tol)]
        return (min(xs), max(xs)) if xs else None

    ys: list[int] = []
    ink_max = pane_left
    for y in range(vy0, vy1):
        ink = [x for x in range(pane_left + 8, pane_right - 1) if sum(px[x, y]) < 380]
        if ink:
            ys.append(y)
            ink_max = max(ink_max, max(ink))
    rows, cur = 0, None
    for y in ys:
        if cur is None or y - cur > 3:
            rows += 1
        cur = y

    return {'size': [W, H], 'gold': [g_l, g_r], 'borders': borders,
            'pane_w': pane_w, 'pane_right': pane_right, 'pane_left': pane_left,
            'pane_top': pane_top, 'pane_bot': pane_bot,
            'ai_bg': bg_extent(AI_BG), 'user_bg': bg_extent(USER_BG),
            'ink_max': ink_max, 'ink_rows': rows,
            'lane': pane_right - ink_max,
            'verdict': 'OK' if (pane_right - ink_max) >= 6 else 'CLIPPED'}


def chat_tail_bubbles(png, rect: dict, *, tol: int = 6) -> dict:
    """量面板**最下面**一个 AI 气泡 / 一个用户气泡的横向范围。

    用来回答一个纯外观问题：短消息的气泡是"贴着字长"还是"撑满整栏"。
    排气泡用的是 `ft.Column`（横向约束有界 → Text 会换行），
    `horizontal_alignment` 决定靠左/靠右；如果短气泡也撑满，说明
    Flet 把 Column 的横向对齐当成了 stretch，得改回 flex 权重方案。
    
        English:
    Measure the horizontal extent of the **bottommost** AI bubble / user bubble in the panel.
        Used to answer a purely visual question: does a short message's bubble "hug the text length" or "fill the whole column".
        The bubble row uses `ft.Column` (bounded horizontal constraint → Text wraps),
        `horizontal_alignment` determines left/right alignment; if a short bubble also fills the column, it means
        Flet treats Column's horizontal alignment as stretch, and we need to revert to the flex weight scheme.
    """
    im = Image.open(png).convert('RGB')
    px = im.load()
    y0, y1 = rect['pane_top'] + 6, rect['pane_bot'] - 6
    x0, x1 = rect['pane_left'] + 2, rect['pane_right'] - 1

    def blocks(rgb):
        rows = []
        for y in range(y0, y1):
            xs = [x for x in range(x0, x1) if _c_near(px[x, y], rgb, tol)]
            if xs:
                rows.append((y, min(xs), max(xs)))
        out = []
        for y, a, b in rows:
            if out and y - out[-1][-1][0] <= 2:
                out[-1].append((y, a, b))
            else:
                out.append([(y, a, b)])
        return [{'y': [g[0][0], g[-1][0]],
                 'x': [min(r[1] for r in g), max(r[2] for r in g)],
                 'w': max(r[2] for r in g) - min(r[1] for r in g)}
                for g in out]

    ai, us = blocks(AI_BG), blocks(USER_BG)
    return {'ai_last': ai[-1] if ai else None,
            'user_last': us[-1] if us else None,
            'ai_n': len(ai), 'user_n': len(us),
            'pane_w': rect['pane_right'] - rect['pane_left']}


# ══════════════════════════════════════════════════════════════
#  控件树遍历 / 对话框取控件（多份验证脚本共用，别各写一份）
# [EN] Widget tree traversal / dialog widget fetching (shared by multiple verification scripts, don't
# [EN] each write one)
# ══════════════════════════════════════════════════════════════
def walk(ctrl):
    """深度遍历控件树（Flet 的树分散在 controls / content / actions / title 上）。

    ★★ 2026-10-12 补 `DataTable` / `Tabs` / `Switch` / `Checkbox` 这几处 ——
      不补的话**判据会假红**，而且是"屏幕上明明有、判据说没有"那种最难查的：
        · `DataTable`：表的单元格在 `columns[i].label` 与 `rows[i].cells[j].content`
          上，**都不在 `controls` 里** ⇒ 模型列表、推荐表、用量报表第 4 栏
          全都不进这棵树。本轮 `verify_llm_models` 的 D6 就是这么红的
          （"推荐表里没有『创作服务』"，而屏幕上那一行就在那儿）。
        · `Tabs`：页签正文在 `tabs[i].content`（不是 `controls`），
          页签名在 `tabs[i].label`。
        · `Switch` / `Checkbox`：显示文字在 `.label`，不是子 `Text`。
      所以这里**一处补齐**，全项目的遍历一起受益（本文件的老规矩：
      一份实现，多处调用）。

        English:
    Deeply traverse the control tree (Flet's tree is spread across controls / content / actions /
    title).
        ★★ 2026-10-12 added `DataTable` / `Tabs` / `Switch` / `Checkbox` -- without them criteria
          **go falsely red**, and in the worst way: "it is visibly on screen but the criterion says it
          is not".
          · `DataTable`: cells live on `columns[i].label` and `rows[i].cells[j].content`, **neither in
            `controls`** ⇒ the model list, the recommendation table and column 4 of the usage report
            all stay out of this tree. `verify_llm_models`' D6 went red exactly like that this round
            ("the recommendation table has no 'Creation Service'" while that row is right there).
          · `Tabs`: page bodies live in `tabs[i].content` (not `controls`), tab names in `tabs[i].label`.
          · `Switch` / `Checkbox`: the display text is in `.label`, not a child `Text`.
        So **one fix here** benefits every traversal in the project (this file's old rule: one
        implementation, called from many places).
    """
    yield ctrl
    for ch in (getattr(ctrl, 'controls', None) or []):
        yield from walk(ch)
    for ch in (getattr(ctrl, 'actions', None) or []):
        yield from walk(ch)
    ch = getattr(ctrl, 'content', None)
    if ch is not None and not isinstance(ch, str):
        yield from walk(ch)
    for ch in (getattr(ctrl, 'tabs', None) or []):
        yield from walk(ch)
    for col in (getattr(ctrl, 'columns', None) or []):
        lbl = getattr(col, 'label', None)
        if lbl is not None:
            yield from walk(lbl)
    for row in (getattr(ctrl, 'rows', None) or []):
        for cell in (getattr(row, 'cells', None) or []):
            inner = getattr(cell, 'content', None)
            if inner is not None:
                yield from walk(inner)


def tab_panels(dlg) -> dict:
    """`{页签名: 那一页的面板控件}` —— **唯一**能分清页签的量法。

    ★★★ 2026-10-13 实测（`developers/_probe_tabstruct.py`）：
      `walk(dlg)` / `all_texts(dlg)` / 数 `DataTable` 都会把**所有页签**的内容
      一起收进来 ⇒ 拿它们判"某一页上有什么"**永远为真**。
      实测过的翻车现场：`verify_llm_models` 的 D5「页上有推荐表」——
      那张表被搬到另一个页签之后，判据**照样绿**（因为整个对话框的文字都算在内）。
      真正的分页结构（Flet 1.0）：
        · `ft.TabBarView`（**`walk` 到得了**）的 `controls[i]` = 第 i 页的**面板**；
        · 页签名在 `ft.TabBar.tabs[i].label`；
        · ⚠ `ft.Tabs.tabs` 是**空的**（页签不在它上面），别再往那儿找。

        English:
    `{tab name: that tab's panel control}` -- the **only** way to tell tabs apart.
        ★★★ Measured 2026-10-13 (`developers/_probe_tabstruct.py`): `walk(dlg)` / `all_texts(dlg)` /
        counting `DataTable`s all pull in **every tab's** content => using them to judge "what's on this
        one page" is **always true**. A real crash site: `verify_llm_models`' D5 ("the page has the
        recommendation table") -- after that table moved to another tab the criterion **stayed green**
        (because the whole dialog's text counted). The real per-tab structure (Flet 1.0):
          · `ft.TabBarView` (**reachable** by `walk`), whose `controls[i]` is tab i's **panel**;
          · tab names live on `ft.TabBar.tabs[i].label`;
          · ⚠ `ft.Tabs.tabs` is **empty** (tabs are not attached there), so don't look for them there.
    """
    import flet as ft
    bar = next((c for c in walk(dlg) if isinstance(c, ft.TabBar)), None)
    view = next((c for c in walk(dlg)
                 if type(c).__name__ == 'TabBarView'), None)
    names = [str(getattr(x, 'label', '') or '')
             for x in (getattr(bar, 'tabs', None) or [])]
    ctrls = list(getattr(view, 'controls', None) or [])
    return {n: ctrls[i] for i, n in enumerate(names) if i < len(ctrls)}


def ctrl_text(c) -> str:
    """一个控件的文字：**`.value` 与 `spans` 都要收**。

    ★★★ 2026-10-10：`mk_hint` / `mk_text` 改成把 `**粗体**` 渲染成
      `ft.TextSpan`（真粗体，而不是字面星号 —— 见 `app_flet.md_spans`）之后，
      那些文案的**字不再挂在 `.value` 上**了。
      原来只读 `.value` 的判据于是把它们**当成空字符串** ⇒ 连着两支假红：
        · `verify_resume_manage` 89/91（确认框里那两句说明）
        · `verify_style_help` 23/24（"顺序就是上面八项"那行对照）
      ⇒ **"读控件的字"只有这一个入口**，判据别各自读 `.value`。

    ⚠ 两处都收而不是二选一：Flet 里 `value` 与 `spans` 谁优先由渲染决定，
      而这里要的是"这个控件上写着什么"，拼起来最不容易漏。
    
        English:
    A control's text: **both `.value` and `spans` must be collected**.
        ★★★ 2026-10-10: after `mk_hint` / `mk_text` were changed to render `**粗体**` as
          `ft.TextSpan` (real bold, not literal asterisks — see `app_flet.md_spans`),
          those texts' **characters are no longer attached to `.value`**.
          The original criteria that only read `.value` therefore treat them **as empty strings** ⇒ two false reds in a row:
            · `verify_resume_manage` 89/91 (those two explanation sentences in the confirmation box)
            · `verify_style_help` 23/24 (the "the order is the eight items above" line comparison)
          ⇒ **there is only one entry point for "reading a control's text"**; criteria should not each read `.value` on their own.
        ⚠ Collect both places rather than choosing one: in Flet, which of `value` and `spans` takes priority is decided by rendering,
          and what's wanted here is "what is written on this control", so concatenating them is least likely to miss anything.
    """
    v = str(getattr(c, 'value', '') or '')
    spans = getattr(c, 'spans', None) or []
    sp = ''.join(str(getattr(s, 'text', '') or '') for s in spans)
    return v + sp


def text_of(ctrl) -> str:
    """控件的文字：`content` 可能是 str（`ft.Button('文字')`），也可能是 Text。
        English:
    A control's text: `content` may be a str (`ft.Button('文字')`), or a Text.
    """
    v = getattr(ctrl, 'content', '')
    if isinstance(v, str):
        return v
    return ctrl_text(v)


def all_texts(ctrl) -> list:
    """树里所有 `ft.Text` 的字（**含 `spans` 里的**，见 `ctrl_text`）。
        English:
    The text of all `ft.Text` in the tree (**including those in `spans`**, see `ctrl_text`).
    """
    import flet as ft
    out: list = []
    for c in walk(ctrl):
        if isinstance(c, ft.Text):
            out.append(ctrl_text(c))
        elif isinstance(c, (ft.Switch, ft.Checkbox)):
            # ★ 开关/勾选框的显示文字在 `.label` 上（不是子 `Text`）。
            # [EN] ★ A switch/checkbox keeps its display text in `.label` (not a child `Text`).
            lbl = getattr(c, 'label', None)
            if lbl:
                out.append(str(lbl))
        elif isinstance(c, ft.Tab):
            lbl = getattr(c, 'label', None)
            if lbl:
                out.append(str(lbl))
    return out


def log_cells(controls) -> list:
    """把一份"日志列表"的 children 变成文本行 —— **别直接读 `.value`**。

    摄取对话框的「运行日志」从 v1.39 起**不只有 `Text`**：阶段之间还插了
    「横线 + 空行」两个 `Container`（用户在 2026-10-06 要求的）。
    老写法 `[c.value for c in log_list.controls]` 当场 `AttributeError`，
    而且**报错发生在主协程里、`ft.run` 还开着窗口**，脚本就那么挂着直到被杀
    （`verify_ingest_consent` 连挂两次，8 分钟没有任何输出，看着像"跑得慢"）。
    所以统一走这里：`Text` → 它的字，分隔线 → `[分隔线]`，空行 → `[空行]`。
    
        English:
    Turn the children of a "log list" into text lines — **do not read `.value` directly**.
        The intake dialog's "运行日志" since v1.39 is **no longer only `Text`**: between stages it also inserts
        two `Container`s of "horizontal line + blank line" (requested by the user on 2026-10-06).
        The old form `[c.value for c in log_list.controls]` raises `AttributeError` on the spot,
        and **the error occurs in the main coroutine with `ft.run` still holding the window open**, so the script just hangs until killed
        (`verify_ingest_consent` hung twice in a row, no output for 8 minutes, looking like "running slowly").
        So route everything through here: `Text` → its text, separator line → `[分隔线]`, blank line → `[空行]`.
    """
    import flet as ft
    out: list = []
    for c in (controls or []):
        if isinstance(c, ft.Text):
            out.append(str(getattr(c, 'value', '') or ''))
        elif isinstance(c, ft.Container):
            if getattr(c, 'height', None) == 1 and getattr(c, 'bgcolor', None):
                out.append('[分隔线]')
            else:
                out.append('[空行]')
        else:
            out.append(f'[{type(c).__name__}]')
    return out


def count_separators(controls) -> int:
    """日志里有多少条"阶段分隔线"（`Container(height=1)` + 有底色）。
        English:
    How many "stage separator lines" there are in the log (`Container(height=1)` + has a background
    color).
    """
    import flet as ft
    return sum(1 for c in (controls or [])
               if isinstance(c, ft.Container) and getattr(c, 'height', None) == 1
               and getattr(c, 'bgcolor', None))


def labelled_fields(dlg) -> dict:
    """对话框里「左侧标签 + 控件」的行：{标签文字: Row（`._field` 挂控件）}。
        English:
    The rows of "left label + control" in the dialog: {label text: Row (control attached at
    `._field`)}.
    """
    out = {}
    for c in walk(dlg):
        if not hasattr(c, '_field'):
            continue
        first = (c.controls or [None])[0]
        label = getattr(getattr(first, 'content', first), 'value', None)
        if isinstance(label, str):
            out[label.strip()] = c
    return out


def open_dialogs(page) -> list:
    """当前**打开着**的对话框（`page._dialogs` 里还留着关掉的旧帧）。
        English:
    The currently **open** dialog (`page._dialogs` still retains closed old frames).
    """
    return [d for d in (getattr(page._dialogs, 'controls', None) or [])
            if bool(getattr(d, 'open', False))]


def opt_label(o) -> str:
    """下拉选项的显示名：`content`（`mk_dropdown` 补的）优先，退回 `text`。
        English:
    The display name of a dropdown option: `content` (added by `mk_dropdown`) takes priority,
    falling back to `text`.
    """
    return str(getattr(o, 'text', '') or
               getattr(getattr(o, 'content', None), 'value', '') or '')


def find_help_dot(ctrl, min_size: int = 12, max_size: int = 26) -> object:
    """找「小节标题旁边的小 `?`」。

    它是 `mk_help_dot()` 造的：一个 width==height、里面只有 `Text('?')`、
    带 `on_click` 的 Container。**按特征找，不按下标找** —— 下标会随布局变。
    
        English:
    Find "the small `?` next to a section title".
        It is created by `mk_help_dot()`: a Container with width==height, containing only `Text('?')`,
        and with `on_click`. **Find by characteristic, not by index** — indices change with layout.
    """
    import flet as ft
    for c in walk(ctrl):
        if not isinstance(c, ft.Container) or c.on_click is None:
            continue
        w, h = getattr(c, 'width', None), getattr(c, 'height', None)
        if not (isinstance(w, (int, float)) and isinstance(h, (int, float))):
            continue
        if not (min_size <= w <= max_size and abs(w - h) <= 2):
            continue
        inner = getattr(c, 'content', None)
        if isinstance(inner, ft.Text) and str(inner.value).strip() == '?':
            return c
    return None


# ══════════════════════════════════════════════════════════════
#  像素：找「输入框」（半透明界面里按亮度找，别按颜色硬比）
# [EN] Pixels: find the "input box" (in a semi-transparent UI, find by brightness, don't hard-compare
# [EN] by color)
# ══════════════════════════════════════════════════════════════
BOX_LIGHT = 690    # 输入框底色比对话框纸面亮得多（实测 251,248,241 vs 229,224,213）
# [EN] Input box background is much brighter than the dialog paper (measured 251,248,241 vs
# [EN] 229,224,213)


def measure_input_boxes(png, min_run: int = 120, light: int = BOX_LIGHT) -> list:
    """量截图里所有输入框矩形 + 框内墨迹。

    逐行取**每一条**长亮段（允许 ≤8px 的空隙，好让框里的字把底色断开的小段
    接回来），再把"行"按**横向重叠 ≥0.6** 归并成矩形。两个坑：
      · 圆角那几行边界会缩进十几像素、字会把底色切成几段 —— 按 x 边界归并
        会把一个框切成四五个碎片（第一版量出 49 个"框"）；
      · 一行里所有亮段都要留：帮助面板左目录(238px)与右正文(876px)是并排两块，
        只记"最宽的那段"会把目录整个丢掉。

    返回 [{y0,y1,x0,x1, ink_w, ink_n}] 按 y 排序。`ink_w` 是**去掉最右侧 40px**
    （下拉箭头也是深色）之后的墨迹宽度。
    
        English:
    Measure all input box rectangles + ink inside the boxes in the screenshot.
        Take **every** long bright segment line by line (allow gaps ≤8px, so the small segments where text in the box breaks up the background color
        接回来), then merge "rows" into rectangles by **horizontal overlap >= 0.6**. Two pitfalls:
          · The rounded-corner rows have boundaries that shrink in by a dozen-ish pixels, and the text cuts the background color into several segments -- merging by x boundary
            would split one box into four or five fragments (the first version measured 49 "boxes");
          · All bright segments in a row must be kept: the help panel's left directory (238px) and right body (876px) are two side-by-side blocks,
            recording only the "widest segment" would drop the entire directory.
        Return [{y0,y1,x0,x1, ink_w, ink_n}] sorted by y. `ink_w` is the ink width **after removing the rightmost 40px**
        (the dropdown arrow is also dark).
    """
    from PIL import Image as _Image
    im = _Image.open(str(png)).convert('RGB')
    W, H = im.size
    px = im.load()

    rows: list = []
    for y in range(H):
        cur: list = []
        for x in range(W):
            if sum(px[x, y]) > light:
                if cur and x - cur[-1] > 8:
                    rows.append((y, cur[0], cur[-1]))
                    cur = []
                cur.append(x)
            elif cur:
                rows.append((y, cur[0], cur[-1]))
                cur = []
        if cur:
            rows.append((y, cur[0], cur[-1]))
    rows = [(y, a, b) for y, a, b in rows if b - a >= min_run]

    rects: list = []
    for y, x0, x1 in rows:
        for r in rects:
            lo, hi = max(r['x0'], x0), min(r['x1'], x1)
            overlap = max(0, hi - lo) / max(1, min(r['x1'] - r['x0'], x1 - x0))
            if r['y1'] >= y - 2 and overlap >= 0.6:
                r['y1'] = y
                r['x0'] = min(r['x0'], x0)
                r['x1'] = max(r['x1'], x1)
                break
        else:
            rects.append({'y0': y, 'y1': y, 'x0': x0, 'x1': x1})

    rects = [r for r in rects if r['y1'] - r['y0'] >= 12]
    for r in rects:
        ink = []
        for y in range(r['y0'], r['y1'] + 1):
            for x in range(r['x0'] + 4, max(r['x0'] + 5, r['x1'] - 40)):
                if sum(px[x, y]) < 430:
                    ink.append(x)
        r['ink_w'] = (max(ink) - min(ink)) if ink else 0
        r['ink_n'] = len(ink)
    return sorted(rects, key=lambda r: r['y0'])


# ★★★ 2026-10-31：宣纸提亮之后，**亮度阈值这把尺废了**。
#   `BOX_LIGHT=690` 是按老配色校的（当时对话框纸面 229,224,213=666，比输入框
#   251,248,241=740 暗得多 ⇒ "亮的都是框"）。后来纸面整体提亮：面板 #fdfaf2=745、
#   渐变 #fffdf6(754)→#f7eeda(703) —— **整张对话框都高于 690**，而输入框
#   #fffdf7=755 与纸面渐变**区间重叠** ⇒ 无论阈值取多少，都只能量出"整页巨框"。
#   实测（verify_help_book 2026-10-31）：书斋整页量出 1 个 1733×1076 的巨框。
#   下面两把新尺**不看亮度**，跟配色提亮无关：
#     · `measure_boxes_by_border` —— 输入框那一圈 `border`（#d9c9a3≈581）落在
#       纸面（703+）与墨字（~123）之间的**空带**里，一行里边框色像素足够多就是框边；
#     · `measure_ink_columns` —— 墨迹（~123）与纸面隔得远，按"每列暗像素数"
#       聚出**有内容的竖条**（帮助页左目录/右正文那类断言用）。
# [EN] ★★★ 2026-10-31: after the rice-paper palette was brightened, **brightness thresholds
#   stopped working** (see the numbers above: the whole dialog is above 690, and the input
#   colour overlaps the paper gradient). The two measures below do not look at brightness:
#     · `measure_boxes_by_border` -- the box border (#d9c9a3 ≈ 581) sits in a band between
#       paper (703+) and ink (~123);
#     · `measure_ink_columns` -- ink columns (dark pixels per column) cluster into content
#       strips (for "left TOC + right body" style assertions).
def measure_boxes_by_border(png, *, lo: int = 500, hi: int = 660,
                            min_band: int = 60, dark: int = 430) -> list:
    """按**边框色带**找输入框，返回 [{y0,y1,x0,x1,ink_w,ink_n}]（按 y 排序）。

    判法：一行里的边框色像素 ≥`min_band` ⇒ 这一行是某条框边；相邻（≤2px）的
    框边行归并成"边"；两条"边"纵向相距 14~60px、横向重叠 ≥0.8 ⇒ 配成一个框。
    `ink_w/ink_n` 只数**框内左侧**（去掉最右 40px 的下拉箭头）的暗像素，
    与 `measure_input_boxes` 同一口径：老 bug 的空框 ink=0。
    ⚠ 框必须**上下边都量到**才配对 —— 上边被标签文字打断时会漏掉那一格
      （宁可少配、不可错配；数量断言的门槛要按这个口径定）。

        English:
    Find input boxes by their **border colour band**; returns [{y0,y1,x0,x1,ink_w,ink_n}]
    sorted by y. A row with >= `min_band` border-coloured pixels is a box edge; adjacent
    (<=2px) edge rows merge into an "edge"; two edges 14~60px apart with >=0.8 horizontal
    overlap pair up into a box. `ink_w/ink_n` count dark pixels inside the box's **left**
    part (rightmost 40px = the dropdown arrow excluded), same convention as
    `measure_input_boxes`: an old-bug empty box has ink 0.
    ⚠ A box pairs only when **both** edges are found -- a top edge broken by label text
      drops that cell (prefer missing over mismatched; set count thresholds accordingly).
    """
    from PIL import Image as _Image
    im = _Image.open(str(png)).convert('RGB')
    W, H = im.size
    px = im.load()

    def _band_xs(y: int) -> list:
        return [x for x in range(2, W - 2) if lo <= sum(px[x, y]) <= hi]

    # 1) 边框行 → "边"（相邻行归并）
    edges: list = []
    cur: dict | None = None
    for y in range(0, H):
        xs = _band_xs(y)
        if len(xs) >= min_band:
            _ov_ok = False
            if cur is not None:
                _lo = min(cur['x1'], xs[-1]) - max(cur['x0'], xs[0])
                _den = max(1, min(cur['x1'] - cur['x0'], xs[-1] - xs[0]))
                _ov_ok = (y - cur['y1'] <= 2 and _lo > 0.6 * _den)
            if _ov_ok:
                cur['y1'] = y
                cur['x0'] = min(cur['x0'], xs[0])
                cur['x1'] = max(cur['x1'], xs[-1])
            else:
                cur = {'y0': y, 'y1': y, 'x0': xs[0], 'x1': xs[-1]}
                edges.append(cur)
        else:
            cur = None

    # 2) 边配对成框（上边 + 下方最近的一条叠得上的边）
    used: set = set()
    boxes: list = []
    for i, top in enumerate(edges):
        if i in used:
            continue
        for j in range(i + 1, len(edges)):
            if j in used:
                continue
            bot = edges[j]
            gapv = bot['y0'] - top['y1']
            lo_o = max(top['x0'], bot['x0'])
            hi_o = min(top['x1'], bot['x1'])
            ov = (hi_o - lo_o) / max(1, min(top['x1'] - top['x0'],
                                            bot['x1'] - bot['x0']))
            if 14 <= gapv <= 60 and ov >= 0.8:
                used.update((i, j))
                boxes.append({'y0': top['y0'], 'y1': bot['y1'],
                              'x0': min(top['x0'], bot['x0']),
                              'x1': max(top['x1'], bot['x1'])})
                break

    # 3) 框内墨迹（口径同 measure_input_boxes：去掉最右 40px 的箭头）
    for b in boxes:
        ink = []
        for y in range(b['y0'] + 2, b['y1'] - 1):
            for x in range(b['x0'] + 4, max(b['x0'] + 5, b['x1'] - 40)):
                if sum(px[x, y]) < dark:
                    ink.append(x)
        b['ink_w'] = (max(ink) - min(ink)) if ink else 0
        b['ink_n'] = len(ink)
    return sorted(boxes, key=lambda b: b['y0'])


def measure_ink_columns(png, *, y0: int = 70, y1: int | None = None,
                        dark: int = 450, min_w: int = 60, gap: int = 40,
                        step: int = 2, x0: int = 20, x1: int | None = None) -> list:
    """按**墨迹列剖面**找"哪几竖条有内容"，返回 [(x0, x1)]（按 x 排序）。

    每列数暗像素（sum < `dark`，隔 `step` 行采样），列有墨(≥3)连成段、
    空档 >`gap` 才断开、段宽 ≥`min_w` 才算。`y0/y1` 用来**抠掉窗口深色边框**：
    那条边横贯整行，会把所有列连成一段（实测 2026-10-31）。
    `x0/x1` 同理抠掉左右两条竖边（默认各留 20px）。

        English:
    Find vertical strips with content via an **ink column profile**; returns [(x0, x1)]
    sorted by x. Per column, count dark pixels (sampled every `step` rows); consecutive
    inky columns form a segment, gaps > `gap` split, segments narrower than `min_w` drop.
    `y0/y1` cut the window's dark frame away (it spans every row and glues all columns
    into one segment); `x0/x1` likewise trim the left/right frame strips (20px each).
    """
    from PIL import Image as _Image
    im = _Image.open(str(png)).convert('RGB')
    W, H = im.size
    px = im.load()
    y1 = H - 40 if y1 is None else y1
    x1 = W - 20 if x1 is None else x1
    col = [0] * W
    for x in range(max(0, x0), min(W, x1)):
        n = 0
        for y in range(max(0, y0), min(y1, H), step):
            if sum(px[x, y]) < dark:
                n += 1
        col[x] = n
    segs: list = []
    cur: list | None = None
    for x in range(max(0, x0), min(W, x1)):
        if col[x] >= 3:
            if cur is None:
                cur = [x, x]
            else:
                cur[1] = x
        elif cur is not None:
            if x - cur[1] > gap:
                if cur[1] - cur[0] >= min_w:
                    segs.append((cur[0], cur[1]))
                cur = None
    if cur is not None and cur[1] - cur[0] >= min_w:
        segs.append((cur[0], cur[1]))
    return segs


# ══════════════════════════════════════════════════════════════
#  对话框定位 / 面板切分（说明书截图与验证共用一份，别各写一份）
# [EN] Dialog positioning / panel splitting (shared by manual screenshot and verification, don't each
# [EN] write one)
# ══════════════════════════════════════════════════════════════
def longest_run(flags: list, max_gap: int = 2) -> int:
    """最长"连续段"长度（允许 ≤max_gap 的小断口）。
        English:
    Longest "continuous segment" length (allowing small gaps <= max_gap).
    """
    best = cur = gap = 0
    start = None
    for i, v in enumerate(flags):
        if v:
            if start is None:
                start, cur, gap = i, 1, 0
            else:
                gap = 0
                cur = i - start + 1
        elif start is not None:
            gap += 1
            if gap > max_gap:
                best = max(best, cur)
                start = cur = gap = 0
    return max(best, cur)


def _rgb_near(c, t, tol=34) -> bool:
    return all(abs(c[i] - t[i]) <= tol for i in range(3))


DIALOG_GOLD = (0xc9, 0xa2, 0x4e)      # 对话框内层描金线
PANEL_BORDER_RGB = (0xd9, 0xc9, 0xa3)  # 面板淡金边框
# [EN] Dialog inner gold stroke line
# [EN] Panel light gold border


def dialog_bbox(png, *, min_row_run: int = 240, min_col_run: int = 110,
                diag: dict | None = None):
    """用对话框**内层描金外框**定位，返回 (x0, y0, x1, y1)；找不到返回 None。

    ⚠ **别用"覆盖率"找**（踩过）：按"金线占屏幕高度的比例 > 0.5"筛，
    矮对话框会被整批筛掉 —— 摄取框 540px 高，在 1129px 的屏幕里覆盖率只有 0.48，
    于是向导/摄取/同意/帮助/导出五张图**静默退回整屏**，缩到 1200 宽后正文里看不清字。
    改成"**最长连续段**"：金线是 1px 细线，量它的长度与对话框尺寸无关。
    
        English:
    Locate using the dialog's **inner gilded outer frame**, return (x0, y0, x1, y1); return None if
    not found.
        ⚠ **Do not search by "coverage ratio"** (been there): filtering by "gilded line's proportion of screen height > 0.5",
        short dialogs get filtered out entirely -- the ingest box is 540px tall, giving a coverage of only 0.48 on a 1129px screen,
        so the five images wizard/ingest/consent/help/export **silently fall back to full screen**, and after scaling to 1200 wide the text in the body is illegible.
        Change to "**longest continuous segment**": the gilded line is a 1px thin line, measuring its length is independent of dialog size.
    """
    im = image_of(png)
    px = im.load()
    W, H = im.size

    row_runs = [(y, n) for y in range(H)
                for n in [longest_run([_rgb_near(px[x, y], DIALOG_GOLD)
                                       for x in range(W)])]
                if n >= min_row_run]
    if len(row_runs) < 2:
        if diag is not None:
            diag['row_runs'] = []
        return None
    ty, by = row_runs[0][0], row_runs[-1][0]
    if by - ty < 130:
        return None

    col_runs = [(x, n) for x in range(W)
                for n in [longest_run([_rgb_near(px[x, y], DIALOG_GOLD)
                                       for y in range(ty, by + 1)])]
                if n >= min_col_run]
    if diag is not None:
        diag['row_runs'] = row_runs[:6]
        diag['col_runs'] = col_runs[:6]
    if len(col_runs) < 2:
        return None
    x0, x1 = col_runs[0][0], col_runs[-1][0]
    if x1 - x0 < 260:
        return None
    return (x0, ty, x1, by)


def panel_bands(png, x0: int, x1: int, y_from: int = 40,
                border=PANEL_BORDER_RGB) -> list:
    """在一段横向区间里按**面板边框**切出一摞上下排列的面板 → [(y0,y1), …]。

    用途：把「左栏的风格控制面板」「右栏的剧情面板」单独抠出来。整栏是
    236×1100 的细长条，塞进说明书里字就没法看了。
    
        English:
    Within a horizontal interval, cut out a stack of vertically arranged panels by **panel border**
    -> [(y0,y1), ...].
        Purpose: extract the "left column's style control panel" and "right column's story panel" separately. A whole column is
        a 236x1100 thin strip; crammed into documentation the text becomes unreadable.
    """
    im = image_of(png)
    px = im.load()
    W, H = im.size
    x0, x1 = max(0, x0), min(W, x1)
    span = max(1, len(range(x0, x1, 2)))
    edges: list = []
    for y in range(y_from, H):
        cov = sum(1 for x in range(x0, x1, 2)
                  if _rgb_near(px[x, y], border, 26)) / span
        if cov > 0.6:
            if edges and y - edges[-1][-1] <= 2:
                edges[-1].append(y)
            else:
                edges.append([y])
    ys = [int(sum(g) / len(g)) for g in edges]
    return [(a, b) for a, b in zip(ys, ys[1:]) if b - a >= 60]


def distinct_colors(png, x0: int, x1: int, y0: int, y1: int, step: int = 1) -> int:
    """一块区域里有多少种颜色。

    用来判"图到底画出来没有"：真截图（照片级渐变）会有**几千种**颜色，
    纯纸面 + 文字只有几十种；`image_error_content` 的灰字也是几十种。
    
        English:
    How many colors are in a region.
        Used to determine "whether the image was actually drawn": a real screenshot (photo-grade gradients) has **thousands** of colors,
        while pure paper + text has only dozens; the gray text of `image_error_content` is also only dozens.
    """
    im = image_of(png)
    px = im.load()
    W, H = im.size
    seen = set()
    for y in range(max(0, y0), min(H, y1), step):
        for x in range(max(0, x0), min(W, x1), step):
            seen.add(px[x, y])
    return len(seen)


def disable_source_repair(app) -> None:
    """让**开卷流程跳过**「AI 补全并回写引用文件夹」那一步。

    为什么每个驱动完整开卷的脚本都要调它
    ------------------------------------
    那一步是**默认开**的（用户要的就是"AI 主动修复"），而且它会停下来弹一个清单
    面板等作者点「同意修复并回写 / 跳过」—— 不关掉的话，任何"跑到开卷结束"的
    脚本都会**挂在那儿等一个永远不会到来的点击**（表现是脚本没有输出、看着像
    跑得很慢，实际上是死等）。

    专门验证这一步的脚本（`tools/verify_repair_writeback.py`）**不要调它** ——
    那里要走的正是默认路径。

    ⚠ 关的是**向导选项**（跟用户在向导第 3 步取消勾选是同一件事），
      不是给程序开后门：`_do_import` 里读的就是这个字典。
    
        English:
    Make the **open-book flow skip** the step "AI completes and writes back to the referenced
    folder".
        Why every script that drives a full open-book flow must call it
        ------------------------------------
        That step is **on by default** (what the user wants is "AI actively repairs"), and it will stop and pop up a list
        panel waiting for the author to click "Agree to repair and write back / Skip" -- if not turned off, any script that "runs to the end of the open-book flow"
        will **hang there waiting for a click that will never come** (the symptom is the script produces no output and looks like it's
        running very slowly, but it's actually dead-waiting).
        The script that specifically verifies this step (`tools/verify_repair_writeback.py`) **must not call it** --
        that one needs to walk exactly the default path.
        ⚠ What's turned off is the **wizard option** (the same thing as the user unchecking it in step 3 of the wizard),
          not opening a back door for the program: what `_do_import` reads is exactly this dict.
    """
    try:
        app._wizard_opts['repair_source'] = False
    except Exception:                                        # noqa: BLE001
        pass


def redirect_env_writes() -> None:
    """**整个脚本**都不许写真实 `.env`（进程结束自动失效，不用还原）。

    与 `env_guard()` 的区别：那个是"把某一段包起来"，这个是"从头到尾都别写"。
    给那些**一启动 GUI 就会跑能力校验**（`app.main()` → `CFG.save()`）的脚本用 ——
    那种情况下"只包住点保存那一下"根本不够。

    ⚠ 不要给「验证 `.env` 真的被写回」的脚本用（`verify_llm_caps` 有一项就是查这个）。
    
        English:
    **The entire script** must not write the real `.env` (it auto-expires when the process ends, no
    need to restore).
        Difference from `env_guard()`: that one is "wrap a certain section", this one is "never write from start to finish".
        For those scripts that **run capability validation as soon as the GUI starts** (`app.main()` -> `CFG.save()`) --
        in that case "wrapping only the save click" is not enough at all.
        ⚠ Do not use it for scripts that "verify `.env` is really written back" (`verify_llm_caps` has an item checking exactly this).
    """
    import config as _cfg
    import tempfile
    _cfg.Config.redirect_save = (
        Path(tempfile.mkdtemp(prefix='nws_envsink_')) / '.env')


def env_guard():
    """开跑类验证脚本的护身符：**点「开始推演」/「保存」会 `CFG.save()`**，
    把脚本里 `CFG.set('MOCK_LLM', 'true')` 这类测试值**写进用户的 .env**。

    ⚠ 2026-10-06 实测踩到：新加的两个脚本点了那个按钮又没还原，
    用户的 `.env` 被改成 `MOCK_LLM=true`（他本来在跑真机）、`BEAT_SECONDS=2`。
    `verify_run_control` 早就有这套备份/还原，只是没抽出来共用。

    ★★ 2026-10-06 二次加固（又踩了一次，这次是 `verify_model_probe`）：
    它把用户的 `LLM_BASE_URL` / `LLM_API_KEY` / `DEFAULT_PROJECTS_DIR`
    一起写成了测试值 —— 因为那个脚本**漏了**包 `env_guard()`。
    **"记得还原"这种约定挡不住第四次**，所以这里不再只做备份/还原，
    而是**把写盘整个重定向掉**（`config.Config.redirect_save`）：
    守卫期间 `CFG.save()` 写的是一个临时文件，**用户真实 `.env`
    一个字节都不会被碰** —— 脚本崩了、嵌套了、忘了还原都不会出事。
    备份/还原**保留**作为第二道防线（万一有人绕开 `Config.save` 直接写文件）。

    用法（把**点了那个按钮**的部分包起来）：

        with env_guard():
            btn.on_click(None)
            ...
    
        English:
    The amulet for run-type verification scripts: **clicking "Start simulation" / "Save" will
    `CFG.save()`**,
        writing test values like `CFG.set('MOCK_LLM', 'true')` in the script **into the user's .env**.
        ⚠ Actually hit this on 2026-10-06: two newly added scripts clicked that button and didn't restore,
        and the user's `.env` was changed to `MOCK_LLM=true` (he was originally running on the real machine) and `BEAT_SECONDS=2`.
        `verify_run_control` already had this backup/restore set long ago, it just wasn't extracted for shared use.
        ★★ 2026-10-06 second hardening (stepped on it again, this time `verify_model_probe`):
        it wrote the user's `LLM_BASE_URL` / `LLM_API_KEY` / `DEFAULT_PROJECTS_DIR`
        all to test values -- because that script **missed** wrapping `env_guard()`.
        **A convention like "remember to restore" can't hold back a fourth time**, so here we no longer just do backup/restore,
        but **redirect the entire write-to-disk** (`config.Config.redirect_save`):
        during the guard, what `CFG.save()` writes is a temporary file, and **not a single byte of the user's real `.env`
        will be touched** -- even if the script crashes, nests, or forgets to restore, nothing goes wrong.
        Backup/restore is **kept** as a second line of defense (in case someone bypasses `Config.save` and writes the file directly).
        Usage (wrap the part that **clicks that button**):
            with env_guard():
                btn.on_click(None)
                ...
    """
    from contextlib import contextmanager

    @contextmanager
    def _g():
        import config as _cfg
        root = Path(__file__).resolve().parent.parent
        p = root / '.env'
        backup = None
        try:
            backup = p.read_text(encoding='utf-8') if p.exists() else None
        except OSError:
            backup = None
        # ★ 第一道防线：把写盘重定向到临时文件（用户文件从此"写不进去"）
        # [EN] ★ First line of defense: redirect writes to disk to a temp file (user files can no longer "be
        # [EN] written to")
        import tempfile
        sink = Path(tempfile.mkdtemp(prefix='nws_envguard_')) / '.env'
        prev = getattr(_cfg.Config, 'redirect_save', None)
        _cfg.Config.redirect_save = sink
        try:
            yield
        finally:
            _cfg.Config.redirect_save = prev
            # 第二道防线：万一有人绕过 `Config.save` 直接写了文件，还原回来
            # [EN] Second line of defense: in case someone bypasses `Config.save` and writes the file directly,
            # [EN] restore it back
            if backup is not None:
                try:
                    if p.read_text(encoding='utf-8') != backup:
                        p.write_text(backup, encoding='utf-8', newline='')
                except OSError:
                    pass
    return _g()


# ══════════════════════════════════════════════════════════════════════
#  剧组 Agents 的**分页那一行**（2026-10-11）
# [EN] The **pagination row** of the Crew Agents list (2026-10-11)
# ══════════════════════════════════════════════════════════════════════
#
#  这一段抽出来是因为它**有两处调用**：开卷向导第 4 步、以及
#  「书斋 / 天机 · 剧组 Agents」页。两份判据各抄一遍探针，迟早会出现
#  "一处改了、另一处还按老结构找" —— 本项目为这种事吃过好几次亏。
# [EN] This block was extracted because it has **two call sites**: wizard step 4, and the
# [EN] "Study / Tianji · Crew Agents" page. Copying the probe into two criteria would eventually produce
# [EN] "one was updated while the other still looks for the old structure" -- a lesson this project has
# [EN] learned several times.

def find_pager_row(root):
    """「上一页 / 页码 / 下一页 / 每页」那一行（`ft.Row`，4 个子控件、含一个下拉）。

    ⚠ 认法是**结构**（4 个孩子 + 里面有 `DropdownM2`），不是"第几个 Row"：
      控件树里 Row 很多，按序号认一定会在别人加一行之后找错。
    [EN] The "prev / page number / next / per page" row (an `ft.Row` with 4 children including a
    [EN] dropdown).
    [EN] ⚠ Identified **structurally** (4 children + contains a `DropdownM2`), not as "the nth Row":
    [EN] there are many Rows in the tree, and indexing would surely break once someone adds a row.
    """
    import flet as ft
    best = None
    for row in walk(root):
        if not isinstance(row, ft.Row):
            continue
        kids = list(getattr(row, 'controls', None) or [])
        if len(kids) != 4:
            continue
        if not any(isinstance(k, ft.DropdownM2) for k in walk(row)):
            continue
        best = row
    return best


def dropdown_option_text(o) -> str:
    """下拉选项的**显示文字**：`text` 优先，回退 `content`。

    ★ 为什么两种都认：`ft.DropdownM2` **渲染的是 `content`**（见 `gui.app_flet._norm_options`），
      而 `text` 是"这项该显示什么"的可读记录。选项若写成 `Option(key=str(v))`
      （只给一个位置参数），`text` 就是空串 —— 只读 `text` 的判据会误判成
      "界面上什么都没有"，而屏幕上明明显示着。
    ⚠ **不要只看 `key`**：`key` 是**存盘值**，界面上可能显示的是另一套人话
      （`'story_day'` vs 「定期暂停」）—— 判据要守的是"用户看得见什么"。
    [EN] A dropdown option's **display text**: `text` first, falling back to `content`.
    [EN] ★ Why accept both: `ft.DropdownM2` **renders `content`** (see `gui.app_flet._norm_options`),
    [EN] while `text` is the readable record of "what this item should display". If an option is written as
    [EN] `Option(key=str(v))` (a single positional argument), `text` is an empty string -- a criterion
    [EN] reading only `text` would misjudge it as "nothing on screen" while the screen plainly shows a
    [EN] value.
    [EN] ⚠ **Do not look at `key` alone**: `key` is the **stored value**, and the UI may show a different
    [EN] human-readable string (`'story_day'` vs a localized label) -- what a criterion guards is "what the
    [EN] user sees".
    """
    t_ = str(getattr(o, 'text', '') or '')
    if t_:
        return t_
    cont = getattr(o, 'content', None)
    if cont is None:
        return ''
    return str(getattr(cont, 'text', '') or cont)


def pager_row_parts(root) -> dict:
    """分页那一行的零件：`{'row', 'prev', 'next', 'label', 'dropdown', 'options'}`。

    `label` 是「每页」那个下拉**左边那格**的文字（说明这个控件是干什么的）。
    [EN] The parts of the pagination row: `{'row', 'prev', 'next', 'label', 'dropdown', 'options'}`.
    [EN] `label` is the text of the cell **left of** the "per page" dropdown (explaining what the control
    [EN] is for).
    """
    row = find_pager_row(root)
    out = {'row': row, 'prev': None, 'next': None,
           'label': '', 'dropdown': None, 'options': []}
    if row is None:
        return out
    for k in (getattr(row, 'controls', None) or []):
        txt = text_of(k)
        if '上一页' in txt or 'Previous' in txt:
            out['prev'] = k
        elif '下一页' in txt or 'Next' in txt:
            out['next'] = k
        if hasattr(k, '_field'):
            out['dropdown'] = k._field
            out['options'] = [dropdown_option_text(o)
                              for o in (getattr(k._field, 'options', None) or [])]
            kids = list(getattr(k, 'controls', None) or [])
            if kids:
                out['label'] = text_of(kids[0])
    return out
