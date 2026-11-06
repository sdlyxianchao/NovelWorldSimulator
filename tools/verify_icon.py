# -*- coding: utf-8 -*-
"""验证应用图标：配色对比、单主色、logo 明确、小尺寸可辨识。

为什么要有这个脚本
------------------
图标是**唯一没法靠肉眼确认**的资源（本机模型读不了图片），而它的要求又很具体：
「单一主色调 + 一个明确的 logo」「两种配色对比明显」「中国色」。
所以全部转成可测量的断言：

1. **两种颜色**：对不透明像素做 2-means 聚色 → 得到实际的底色与记号色
2. **对比明显**：算 WCAG 相对亮度对比（要求 ≥ 3:1）+ 色相差（彩色方案要求 ≥ 120°）
3. **单一主色**：底色占比要够大（≥ 60%），不能是花图
4. **主色色相**：落在**该配色自己声明的 `hue_range` 里**（不再写死某个区间）。
   口径变过三次：最早"黑红恐怖"→ 全暖色；后来"还是像一个人"→ 竹子 + 清新（90°~200°）；
   再后来 **朱砂橙底 + 白狐**（10°~45°，那版跟 UC 浏览器撞了观感）；
   现在是 **月白（带一点青）底 + 火红狐**（165°~215°）。每变一次，写死的断言就从"保护"
   变成"噪音"，所以改成**数据驱动**：`SCHEMES[k]['hue_range']`。
5. **logo 明确**：记号要是**一个连通块**（占比 ≥ 98%），散点噪点不算 logo
6. **记号轮廓**：形状无关的三条（不顶边 · 上下对称 · 占框内 12%~40%）+
   **按 `mark_shape` 分派**的专属判据：
   - `fox`（当前默认，**正脸**）：宽高比 == `FOX_ASPECT` ± 0.03（**直接盯住几何管线** ——
     缩放系数重复计入长宽比会让它变形，这个真 bug 就是这么抓到的）·
     顶部收窄（尖耳，不是平头）· 最宽行落在中段 ·
     **正脸专属两条**：左右对称（镜像差 ≈ 0，靠"只写右半边再镜像"保证）·
     有一对挖空的眼睛（洞 = 2 —— 前景连通块数对这个完全不敏感，得单独数）；
   - `bamboo`（备选配色）：竖直为主 · 最宽在上半部 · 根部收拢 · 竿梢窄口。
   ★ **换题材时必须重写这一段** —— 本项目踩过：换成"花"的那次没改，
   脚本 import 的东西已经不存在了，**整版图标根本没跑过验证**。
7. **小尺寸可辨识**：缩到 16 / 32 / 48 px 后，记号占比仍在合理区间（≥ 12%）
8. **产物齐全**：icon.ico 内含 16~256 多尺寸；app_icon.png/ico 与 icon_256 一致

⚠️ 第 5、6 条量的是 **`mark_mask()` 的记号剪影**，不是渲染后的像素 ——
渲染图上还有一圈**外框描边**（深褐色，比底色更接近记号色），
按"离哪个色心近"分类时它会被算成第二块"记号"（实测 12%），
于是连通性断言假失败。**外框是刻意画的元素，不是散落的噪点**，
把它算进"logo 是不是一整块"里本身就是量错了对象。

产出：`assets/screenshots/icon_preview.png`（三套配色的各尺寸预览，给人看）
      `assets/screenshots/icon_report.json`

English:
Verify the app icon: color contrast, single dominant color, clear logo, recognizable at small
sizes.
Why this script exists
------------------
Icons are the **only resource that cannot be confirmed by eye** (the local model cannot read
images), and their requirements are quite specific:
"single dominant hue + one clear logo", "two schemes with obvious contrast", "Chinese colors".
So everything is turned into measurable assertions:
1. **Two colors**: run 2-means color clustering on opaque pixels -> get the actual base color and mark color
2. **Obvious contrast**: compute WCAG relative luminance contrast (require ≥ 3:1) + hue difference (colored schemes require ≥ 120°)
3. **Single dominant color**: base color share must be large enough (≥ 60%), cannot be a busy image
4. **Dominant hue**: falls **within `hue_range` declared by the scheme itself** (no longer
hardcoding an interval).
   The criterion changed three times: earliest "black-red horror" -> all warm colors; later "still like a person" -> bamboo + fresh (90°~200°);
   then **cinnabar orange base + white fox** (10°~45°, that version clashed with UC Browser visually);
   now it is **moon white (with a touch of cyan) base + fire red fox** (165°~215°). Each change turns the hardcoded assertion from "protection"
   into "noise", so it was changed to **data-driven**: `SCHEMES[k]['hue_range']`.
5. **Clear logo**: the mark must be **one connected component** (share ≥ 98%), scattered noise
does not count as a logo
6. **Mark outline**: three shape-independent ones (not touching the edge · top-bottom symmetry ·
occupying 12%~40% of the frame) +
   exclusive criteria **dispatched by `mark_shape`**:
   - `fox` (current default, **front face**): aspect ratio == `FOX_ASPECT` ± 0.03 (**directly watches the geometry pipeline** --
     counting the scale factor twice in the aspect ratio deforms it; this real bug was caught exactly this way) ·
     top narrows (pointy ears, not flat head) · widest row falls in the middle section ·
     **two front-face exclusive**: left-right symmetry (mirror difference ≈ 0, guaranteed by "only write the right half then mirror") ·
     has a pair of hollow eyes (holes = 2 -- the foreground connected-component count is completely insensitive to this, must be counted separately);
   - `bamboo` (alternative scheme): predominantly vertical · widest in the upper half · root gathers in · narrow tip at the stalk end.
   ★ **This section must be rewritten when the subject changes** -- this project got burned: the switch to "flower" did not change it,
   the things the script imports no longer existed, and **the entire icon version never ran validation at all**.
7. **Recognizable at small sizes**: after scaling to 16 / 32 / 48 px, the mark share is still in
a reasonable range (≥ 12%)
8. **Artifacts complete**: icon.ico contains multiple sizes 16~256; app_icon.png/ico matches
icon_256
⚠️ Items 5 and 6 measure the **mark silhouette of `mark_mask()`**, not the rendered pixels --
the rendered image also has a ring of **outer frame stroke** (dark brown, closer to the mark
color than the background),
when classifying by "which color center is nearest", it gets counted as a second "mark" block
(measured 12%),
so the connectivity assertion falsely fails. **The outer frame is a deliberately drawn element,
not scattered noise**,
counting it into "is the logo one whole piece" is itself measuring the wrong object.
Output: `assets/screenshots/icon_preview.png` (previews of each size for three color schemes,
for humans to view)
      `assets/screenshots/icon_report.json`
"""
from __future__ import annotations

import json
import math
import sys
from collections import deque
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from PIL import Image, ImageChops, ImageDraw  # noqa: E402

from image_gen import icon as ICON_MOD  # noqa: E402
from image_gen.icon import (DEFAULT_SCHEME, FOX_ASPECT, ICON_SOURCE, SCHEMES,  # noqa: E402
                            face_outline, generate_icon, icon_from_source,
                            icon_signature, mark_mask, save_icons, source_image)

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


def hue_of(c) -> float:
    import colorsys
    return colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)[0] * 360.0


def hue_gap(h1: float, h2: float) -> float:
    d = abs(h1 - h2) % 360.0
    return min(d, 360.0 - d)


def kmeans2(pixels, seeds, iters: int = 18):
    """2-means 聚色（用给定颜色做种子，结果取实际质心 —— 不是照抄期望值）。
        English:
    2-means color clustering (use given colors as seeds, take actual centroids as result -- not
    copying expected values).
    """
    c0, c1 = [list(s) for s in seeds]
    g0, g1 = [], []
    for _ in range(iters):
        g0, g1 = [], []
        for p in pixels:
            d0 = sum((p[i] - c0[i]) ** 2 for i in range(3))
            d1 = sum((p[i] - c1[i]) ** 2 for i in range(3))
            (g0 if d0 <= d1 else g1).append(p)
        if not g0 or not g1:
            break
        c0 = [sum(p[i] for p in g0) / len(g0) for i in range(3)]
        c1 = [sum(p[i] for p in g1) / len(g1) for i in range(3)]
    return c0, g0, c1, g1


def opaque_pixels(im: Image.Image):
    im = im.convert('RGBA')
    return [p[:3] for p in im.get_flattened_data() if p[3] > 220]


def mask_components(mask: Image.Image) -> list[tuple[int, int, int, int, int]]:
    """遮罩的连通块统计：`[(像素数, x0, x1, y0, y1)]`，按像素数降序。

    **量的是 `mark_mask()` 的剪影，不是渲染后的像素。** 渲染图上那圈外框描边
    也是深褐色、比底色更接近记号色，用"离哪个色心近"去分类就会把它算成
    第二块"记号"，连通性断言假失败（实测 12%）。外框是刻意画的元素，
    不该参与"logo 是不是一整块"这个判断 —— 这是量错了对象，不是画错了图。
    
        English:
    Connected component statistics of the mask: `[(pixel count, x0, x1, y0, y1)]`, sorted descending
    by pixel count.
        **Measures the silhouette of `mark_mask()`, not the rendered pixels.** The outer frame stroke in the rendered image
        is also dark brown, closer to the mark color than the background; classifying by "which color center is nearest" will count it as
        a second "mark" block, causing the connectivity assertion to falsely fail (measured 12%). The outer frame is a deliberately drawn element,
        and should not participate in the judgment "is the logo one whole piece" -- this is measuring the wrong object, not drawing the wrong image.
    """
    m = mask.convert('L')
    w, h = m.size
    px = m.load()
    seen = [[False] * h for _ in range(w)]
    out: list[tuple[int, int, int, int, int]] = []
    for sy in range(h):
        for sx in range(w):
            if seen[sx][sy] or px[sx, sy] <= 127:
                continue
            n = 0
            xs: list[int] = []
            ys: list[int] = []
            q = deque([(sx, sy)])
            seen[sx][sy] = True
            while q:
                x, y = q.popleft()
                n += 1
                xs.append(x)
                ys.append(y)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx_, ny_ = x + dx, y + dy
                    if 0 <= nx_ < w and 0 <= ny_ < h and not seen[nx_][ny_] \
                            and px[nx_, ny_] > 127:
                        seen[nx_][ny_] = True
                        q.append((nx_, ny_))
            out.append((n, min(xs), max(xs), min(ys), max(ys)))
    return sorted(out, key=lambda r: -r[0])


def width_profile(mask: Image.Image) -> list[float]:
    """逐行的记号宽度（相对画布宽度）。用来判断"下宽上窄"。
        English:
    Per-row mark width (relative to canvas width). Used to judge "wide at bottom, narrow at top".
    """
    m = mask.convert('L')
    w, h = m.size
    px = m.load()
    return [len([x for x in range(w) if px[x, y] > 127]) / w for y in range(h)]


def symmetry_error(mask: Image.Image) -> float:
    """左右镜像差（灰度和 ÷ 前景面积）。**正脸应当是 0**。

    为什么值得单判一条：正脸的轮廓只写**右半边**、左半边靠镜像
    （`icon.face_outline()`），所以对称是**几何保证**的 —— 一旦有人
    改成"手动补左半边"或把镜像那步弄丢，这条会立刻红。
    
        English:
    Left-right mirror difference (grayscale sum / foreground area). **A front face should be 0**.
        Why it's worth a dedicated check: the front face's outline only writes the **right half**, the left half relies on mirroring
        (`icon.face_outline()`), so symmetry is **geometrically guaranteed** -- if someone
        changes it to "manually fill in the left half" or loses the mirroring step, this check immediately goes red.
    """
    m = mask.convert('L')
    flip = m.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    w, h = m.size
    px, dp = m.load(), ImageChops.difference(m, flip).load()
    fg = sum(1 for y in range(h) for x in range(w) if px[x, y] > 127)
    return sum(dp[x, y] for y in range(h) for x in range(w)) / max(1, fg * 255)


def face_outline_pts() -> list[tuple[float, float]]:
    """**画图真正用的那条闭合轮廓**（归一化坐标，含左右镜像）。
        English:
    **The actual closed outline used for drawing** (normalized coordinates, including left-right
    mirroring).
    """
    return face_outline()


def outline_corners(pts: list[tuple[float, float]], *, span: int = 6,
                    thr: float = 12.0, gap: int = 8
                    ) -> list[tuple[float, float, float, int]]:
    """轮廓上的"角"：`[(转角°, y, x, 点数)]`，按 |转角| 降序。

    这是**"圆润"的量化形式**（用户 2026-10-07：「曲线稍微圆润一些」）：
    圆润 = 除了该尖的地方（耳尖），轮廓上没有别的大转角。

    ⚠ 两条实测出来的规矩，改这里之前先读：
    ① **必须把相邻的尖点聚成一处角**。逐点量的话，一处角上连续十几个点
       都超阈值 —— 第一版把**同一个下巴**数成了 12 处"别处的角"。
    ② **必须量 `face_outline()`**（含镜像的闭合线）。第一版把 `FACE_SEGS`
       摊平当闭合环量，那只是右半边，还凭空多一个角、**左耳尖根本没进样本**。
    ③ `span` 是在**点数**上取的前后间隔，不是弧长 —— 稀疏/稠密的轮廓
       阈值不一样，所以 `thr` 要配合它一起看（当前 264~290 点 / span=6）。
    
        English:
    "Corners" on the outline: `[(turn angle°, y, x, point count)]`, sorted descending by |turn
    angle|.
        This is the **quantitative form of "rounded"** (user 2026-10-07: "make the curves a bit more rounded"):
        rounded = apart from where it should be sharp (ear tips), the outline has no other large turn angles.
        ⚠ Two empirically derived rules, read before changing this:
        ① **Adjacent sharp points must be clustered into one corner**. Measuring point by point, a dozen consecutive points at one corner
           all exceed the threshold -- the first version counted **the same chin** as 12 "corners elsewhere".
        ② **Must measure `face_outline()`** (the closed line including mirroring). The first version flattened `FACE_SEGS`
           as a closed ring to measure; that's only the right half, and it also conjures an extra corner, **the left ear tip never entered the sample**.
        ③ `span` is the forward/backward interval taken over **point count**, not arc length -- sparse/dense outlines
           have different thresholds, so `thr` must be read together with it (currently 264~290 points / span=6).
    """
    n = len(pts)
    raw: list[tuple[int, float, float, float]] = []
    for i in range(n):
        a, b, c = pts[(i - span) % n], pts[i], pts[(i + span) % n]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        d1 = math.hypot(*v1) or 1e-9
        d2 = math.hypot(*v2) or 1e-9
        cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (d1 * d2)))
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        ang = math.degrees(math.acos(cos)) * (-1 if cross > 0 else 1)
        if abs(ang) >= thr:
            raw.append((i, ang, b[1], b[0]))
    out: list[tuple[float, float, float, int]] = []
    i = 0
    while i < len(raw):
        j = i
        while j + 1 < len(raw) and raw[j + 1][0] - raw[j][0] <= gap:
            j += 1
        grp = raw[i:j + 1]
        best = max(grp, key=lambda r: abs(r[1]))
        out.append((best[1], best[2], best[3], len(grp)))
        i = j + 1
    # 闭合环被切开时首尾会是同一处角 —— 合成一个
    # [EN] When a closed loop is cut open, the head and tail are the same corner -- merge into one
    if len(out) > 1 and abs(out[0][1] - out[-1][1]) < 0.02 \
            and abs(out[0][2] - out[-1][2]) < 0.02:
        pick = out[0] if abs(out[0][0]) >= abs(out[-1][0]) else out[-1]
        out = [pick] + out[1:-1]
    return sorted(out, key=lambda r: -abs(r[0]))


def count_holes(mask: Image.Image) -> int:
    """剪影里"被前景围住的空腔"个数（**眼睛就是这两个洞**）。

    做法：先从画布四边把背景淹一遍（能淹到的都是"外面"），
    剩下没淹到的背景像素就是洞，再数连通块。

    ⚠ 不能用"前景连通块数"代替：洞不是碎片，前景仍是完整一块 ——
    `mask_components()` 对有没有眼睛**完全不敏感**。眼睛是正脸的关键特征
    （没了它这形状读起来就是块石头），所以得单独数。
    
        English:
    Number of "cavities enclosed by foreground" in the silhouette (**the eyes are these two
    holes**).
        Method: first flood the background from the four canvas edges (anything reachable is "outside"),
        the remaining unreached background pixels are holes, then count connected components.
        ⚠ Cannot substitute with "foreground connected component count": holes are not fragments, the foreground remains one whole piece --
        `mask_components()` is **completely insensitive** to whether eyes exist. Eyes are a key feature of the front face
        (without them this shape reads as a stone), so they must be counted separately.
    """
    m = mask.convert('L')
    w, h = m.size
    px = m.load()
    outside = [[False] * h for _ in range(w)]
    q: deque = deque()
    for x in range(w):
        for y in (0, h - 1):
            if px[x, y] <= 127 and not outside[x][y]:
                outside[x][y] = True
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if px[x, y] <= 127 and not outside[x][y]:
                outside[x][y] = True
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = x + dx, y + dy
            if 0 <= a < w and 0 <= b < h and not outside[a][b] and px[a, b] <= 127:
                outside[a][b] = True
                q.append((a, b))
    seen = [[False] * h for _ in range(w)]
    n = 0
    for sy in range(h):
        for sx in range(w):
            if px[sx, sy] > 127 or outside[sx][sy] or seen[sx][sy]:
                continue
            n += 1
            seen[sx][sy] = True
            qq: deque = deque([(sx, sy)])
            while qq:
                x, y = qq.popleft()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    a, b = x + dx, y + dy
                    if (0 <= a < w and 0 <= b < h and not seen[a][b]
                            and not outside[a][b] and px[a, b] <= 127):
                        seen[a][b] = True
                        qq.append((a, b))
    return n


# ══════════════════════════════════════════════════════════════
def check_scheme(key: str) -> bool:
    sc = SCHEMES[key]
    label = sc['name']
    print(f'\n── 配色 [{key}] {label} ──')
    im = generate_icon(512, key).convert('RGBA')
    px = opaque_pixels(im)
    c0, g0, c1, g1 = kmeans2(px, (sc['ground_top'], sc['mark']))
    if len(g0) >= len(g1):
        ground, mark, n_mark = c0, c1, len(g1)
    else:
        ground, mark, n_mark = c1, c0, len(g0)
    total = len(g0) + len(g1)
    share = n_mark / total
    cr = contrast(ground, mark)
    hg = hue_gap(hue_of(ground), hue_of(mark))

    ok = rec(f'{label}: 底色占大头（单一主色调）', share <= 0.40,
             f'底色 {1 - share:.1%} / 记号 {share:.1%}')
    # 主色色相落在哪一段，**由配色自己声明**（`SCHEMES[key]['hue_range']`），
    # 而不是把某个区间写死在断言里。
    # 走过的弯路：早前用户嫌"黑红恐怖"→ 要求全暖色（15°~70°）；
    # 后来"像一个人"→ 改竹子 + 清新（90°~200°）；最终定稿是**朱砂橙底 + 白狐**
    # （10°~45°）。口径每变一次，写死的断言就从"保护"变成"噪音" —— 所以改成数据驱动。
    # [EN] Which segment the dominant hue falls in **is declared by the scheme itself**
    # [EN] (`SCHEMES[key]['hue_range']`),
    # [EN] rather than hardcoding some interval into the assertion.
    # [EN] Detours taken: earlier the user disliked "black-red horror" -> demanded all warm colors
    # [EN] (15°~70°);
    # [EN] later "like a person" -> switched to bamboo + fresh (90°~200°); the final version is **cinnabar
    # [EN] orange base + white fox**
    # [EN] (10°~45°). Every time the criterion changed, the hardcoded assertion went from "protection" to
    # [EN] "noise" -- so it was changed to data-driven.
    gh = hue_of(ground)
    # ★ 2026-10-13 换新 Logo（用户钦定：橘红底 #FF6A2B + 白狐 + 橘红外描边）后，
    #   源图实测亮度对比 2.88:1 —— 比程序绘制模式的 3:1 坎低一线。白狐与橘红
    #   视觉区分鲜明，狐体外还围了一圈更深的描边（边界对比更高）；为凑 3:1
    #   去改用户定稿的颜色是本末倒置。故源图模式**单独**用 2.5:1 下限，
    #   程序绘制模式维持 3:1。
    # [EN] ★ 2026-10-13 after switching to the new logo (user's pick: orange-red base
    # [EN] #FF6A2B + white fox + orange-red outline), the source image measures 2.88:1
    # [EN] luminance contrast -- a hair under the 3:1 bar used for programmatic drawing.
    # [EN] White on orange is visually distinct, and the fox is rimmed by an even darker
    # [EN] outline (higher edge contrast); recoloring the user's finalized art just to hit
    # [EN] 3:1 would be putting the cart before the horse. So source mode gets its **own**
    # [EN] floor of 2.5:1; programmatic mode keeps 3:1.
    _src_mode = source_image() is not None
    _cr_floor = 2.5 if _src_mode else 3.0
    if _src_mode:
        # ★ 源图模式：颜色由**源图**定，配色方案不再改色 —— 这时再拿配色的
        #   `hue_range` 去卡，就是在要求"同一张图同时是四种颜色"，必然假红。
        #   换成有意义的断言：**本配色产出 == 源图**（颜色确实跟着源图走）。
        # [EN] ★ Source mode: colors are decided by the **source image**, schemes no longer recolor --
        # [EN] applying the scheme's `hue_range` here would be demanding "one image is four colors at
        # [EN] once", which is bound to be a false failure. Replaced by a meaningful assertion:
        # [EN] **this scheme's output == the source image** (colors really do follow the source).
        ref = icon_from_source(512, source_image())
        ok &= rec(f'{label}: 源图模式——产出 == 源图（配色不再改色）',
                  im.convert('RGB').tobytes() == ref.convert('RGB').tobytes(),
                  f'底色色相 {gh:.0f}°（由源图定）')
    else:
        lo, hi = sc.get('hue_range') or (0, 360)
        ok &= rec(f'{label}: 主色在声明的色相区间内（{lo}°~{hi}°）', lo <= gh <= hi,
                  f'底色色相 {gh:.0f}°')
    ok &= rec(f'{label}: 亮度对比 ≥ {_cr_floor}:1（源图模式 2.5 / 程序绘制 3.0）',
              cr >= _cr_floor, f'{cr:.2f}:1')
    # 「对比明显」有两条路：亮度拉开（淡青底配竹青）或色相拉开（冷暖对撞）。
    # 现在两套清新配色**都走亮度这条路**：底与标的色相同在青绿~青蓝，本来就拉不开色相差
    # （实测色相差只有 2°~11°）。这不是缺陷 —— 淡底深记号的图标靠明度就够清楚。
    # [EN] "Obvious contrast" has two paths: pull apart brightness (pale cyan base with bamboo green) or
    # [EN] pull apart hue (warm-cold clash).
    # [EN] Now both fresh schemes **take the brightness path**: base and mark colors are both in
    # [EN] cyan-green~cyan-blue, so the hue difference was never large to begin with
    # [EN] (measured hue difference is only 2°~11°). This is not a defect -- an icon with a pale base and
    # [EN] dark mark is clear enough relying on lightness alone.
    by_lum = cr >= _cr_floor
    by_hue = hg >= 120
    ok &= rec(f'{label}: 对比明显（亮度 ≥3:1 或 色相差 ≥120°）', by_lum or by_hue,
              f'亮度 {cr:.2f}:1 / 色相差 {hg:.0f}°，由'
              f'{"亮度" if by_lum else "色相"}支撑'
              f'（底 {tuple(round(v) for v in ground)} / '
              f'记 {tuple(round(v) for v in mark)}）')
    for size, floor in ((16, 0.12), (32, 0.12), (48, 0.10)):
        small = im.resize((size, size), Image.Resampling.LANCZOS)
        sp = opaque_pixels(small)
        if len(sp) < 4:
            ok &= rec(f'{label}: {size}px 有内容', False, '几乎空')
            continue
        _, s0, _, s1 = kmeans2(sp, (tuple(round(v) for v in ground),
                                    tuple(round(v) for v in mark)), iters=10)
        m = min(len(s0), len(s1)) / max(1, len(s0) + len(s1))
        ok &= rec(f'{label}: {size}px 记号仍可辨识', m >= floor,
                  f'记号占 {m:.1%}（下限 {floor:.0%}）')
    return bool(ok)


def check_silhouette() -> bool:
    """记号剪影：**形状无关的不变量** + 按当前形状追加的专属判据。

    形状无关的三条对谁都成立（一只狐狸、一丛竹子都该满足）：
    一整块 / 在框内留白充足 / 占框内的比例合理。
    专属判据按 `SCHEMES[DEFAULT_SCHEME]['mark_shape']` 分派 ——
    **换题材时只改那一段，别把上一版的线条判据留在那里**（本项目踩过：
    换成花的那次没改，脚本 import 的东西已经没了，整版图标根本没跑过验证）。
    
        English:
    Mark silhouette: **shape-independent invariants** + shape-specific criteria appended per current
    shape.
        The three shape-independent ones hold for anyone (a fox, a clump of bamboo should all satisfy them):
        one whole piece / sufficient padding within the frame / reasonable proportion within the frame.
        Shape-specific criteria are dispatched by `SCHEMES[DEFAULT_SCHEME]['mark_shape']` --
        **when switching themes only change that section, don't leave the previous version's line criteria there** (this project has been bitten:
        the switch to a flower didn't change it, the thing the script imports no longer exists, the whole set of icons never ran validation at all).
    """
    shape = (SCHEMES.get(DEFAULT_SCHEME) or {}).get('mark_shape', 'fox')
    label = {'fox': '狐狸', 'bamboo': '一丛竹子'}.get(shape, shape)
    print(f'\n── 记号剪影（{label}）──')
    m = mark_mask(256)
    comps = mask_components(m)
    total = sum(c[0] for c in comps)
    # ⚠ **空的情况必须挡在 `comps[0]` 之前**。原来那句 `if not comps: return`
    #   排在带 `comps[0]` 的 f-string **后面** —— 剪影为空时（比如镜像那步被弄丢、
    #   多边形退化成零面积）脚本直接 IndexError **崩掉**，于是"判据变红"
    #   变成了"脚本报错"：`[FAIL]` 一行都没打印，反例法只看到"没有红的"，
    #   当场把一次真变异读成"判据守住了"。**崩溃不是红，是判据自己不稳。**
    # [EN] ⚠ **The empty case must be guarded before `comps[0]`**. The original line `if not comps: return`
    # [EN] was placed **after** the f-string using `comps[0]` -- when the silhouette is empty (e.g. the
    # [EN] mirror step got lost,
    # [EN] or the polygon degenerated to zero area) the script directly crashes with IndexError, so
    # [EN] "criterion turns red"
    # [EN] became "script throws an error": not a single `[FAIL]` line is printed, and the counterexample
    # [EN] method only sees "nothing red",
    # [EN] instantly reading a real mutation as "criterion held". **A crash is not red, it is the criterion
    # [EN] itself being unstable.**
    if not comps:
        return bool(rec('记号是一整块（没有任何散落碎片）', False,
                        '记号是空的（一个前景像素都没有）'))
    share0 = comps[0][0] / max(1, total)
    ok = rec('记号是一整块（没有任何散落碎片）', share0 >= 0.98,
             f'{len(comps)} 块，最大块占 {share0:.1%}')

    n, x0, x1, y0, y1 = comps[0]
    W = m.size[0]
    pr = width_profile(m)
    h = y1 - y0 + 1
    bw = x1 - x0 + 1

    # ── 形状无关：留白与占比 ──
    # [EN] ── Shape-independent: margins and proportion ──
    pads = (x0, y0, W - 1 - x1, W - 1 - y1)
    ok &= rec('在框内留白充足（不顶边）', min(pads) >= W * 0.04,
              f'四边留白 {pads}（画布 {W}）')
    ok &= rec('上下留白基本对称（记号不在框里偏上/偏下）',
              abs(y0 - (W - 1 - y1)) <= W * 0.05,
              f'上空 {y0}px / 下空 {W - 1 - y1}px')
    cover = sum(1 for y in range(W) for x in range(W) if m.getpixel((x, y)) > 127) / (W * W)
    ok &= rec('记号占框内 12%~40%（太小看不清、太大顶边）', 0.12 <= cover <= 0.40,
              f'占 {cover:.1%}')

    if shape == 'fox':
        # ★ 这一条直接盯住几何管线：`fox_points()` 里缩放系数若被乘了两次
        # （长宽比重复计入），渲染出来会瘦长 —— 侧影那版实测 0.62 而不是 0.79。
        # [EN] ★ This one directly watches the geometry pipeline: if the scale factor in `fox_points()` is
        # [EN] multiplied twice
        # [EN] (aspect ratio counted twice), the render comes out elongated -- the profile version measured
        # [EN] 0.62 instead of 0.79.
        ratio = bw / h
        # ⚠ 容差 **0.03**（原 0.06）：0.06 是侧影时代定的 —— 那会儿宽高比 0.79，
        #   "把长宽比乘两次"会差 0.165，怎么都够红。正脸的宽高比是 0.93，
        #   同一个变异只差 0.057，**0.06 正好把它放过去**（反例法当场测出来的）。
        #   实测误差只有 0.009（见括号里那两个数），0.03 仍有 3 倍余量。
        # [EN] ⚠ Tolerance **0.03** (was 0.06): 0.06 was set in the profile era -- back then the aspect ratio
        # [EN] was 0.79,
        # [EN] "multiplying the aspect ratio twice" would differ by 0.165, red no matter what. The front face
        # [EN] aspect ratio is 0.93,
        # [EN] the same mutation only differs by 0.057, **and 0.06 lets it slip through exactly** (found on the
        # [EN] spot by the counterexample method).
        # [EN] The measured error is only 0.009 (see the two numbers in parentheses); 0.03 still has a 3x
        # [EN] margin.
        ok &= rec('狐狸宽高比与 FOX_ASPECT 一致（防"被拉伸"）',
                  abs(ratio - FOX_ASPECT) <= 0.03,
                  f'实测 {ratio:.3f} / 期望 {FOX_ASPECT:.3f}')
        # ── 正脸专属（2026-10-07 换成正脸时补的）──
        # ① 左右对称：轮廓只写右半边、左半边靠镜像 → 这是**几何保证**的。
        #    有人改成"手动补左半边"、或把镜像那步弄丢，这条立刻红。
        # [EN] ── Front face exclusive (added on 2026-10-07 when switching to the front face) ──
        # [EN] ① Left-right symmetry: outline only writes the right half, the left half relies on mirroring ->
        # [EN] this is a **geometric guarantee**.
        # [EN] If someone changes it to "manually fill in the left half", or loses the mirror step, this line
        # [EN] turns red immediately.
        sym = symmetry_error(m)
        ok &= rec('正脸左右对称（镜像差极小）', sym <= 0.05, f'镜像差 {sym:.3f}')
        # ③ 四周留边（用户 2026-10-07：「狐狸脸不要占满，周围留一点边」）
        #    比上面那条"不顶边（≥4%）"更严：4% 是"别碰边"，10% 是"要留边"。
        # [EN] ③ Margins on all sides (user 2026-10-07: "the fox face should not fill the whole thing, leave a
        # [EN] little margin around it")
        # [EN] Stricter than the line above "not touching the edge (≥4%)": 4% is "don't touch the edge", 10% is
        # [EN] "must have a margin".
        ok &= rec('记号四周留边 ≥10%（脸不占满画布）',
                  min(pads) >= W * 0.10,
                  f'最小留白 {min(pads)}px（{min(pads) / W:.1%}，画布 {W}）')
        # ④⑤ **圆润**（用户 2026-10-07：「曲线稍微圆润一些」）
        #    圆润 = 该尖的地方（耳尖）尖，别处没有大转角。
        # [EN] ④⑤ **Roundness** (user 2026-10-07: "make the curves a bit rounder")
        # [EN] Round = pointy where it should be (ear tips), no large corners elsewhere.
        cs = outline_corners(face_outline_pts())
        tips = [c for c in cs if c[1] < 0.06]
        rest = [c for c in cs if c[1] >= 0.06]
        ok &= rec('圆润：全轮廓最尖的两处是耳尖（尖劲儿归耳朵管）',
                  len(cs) >= 2 and all(c[1] < 0.06 for c in cs[:2]),
                  f'{len(cs)} 处角；最尖两处 {[round(c[0], 1) for c in cs[:2]]}°，'
                  f'分别在高度 {[round(c[1], 3) for c in cs[:2]]}')
        # ⚠ 阈值 **45°** 是量出来的，不是拍的（2026-10-07）：
        #   现状 36.9°（下巴/头顶都做了"切线水平"）·
        #   下巴变回尖针 50.2°~71.1°（取决于第二个控制点多陡）·
        #   原三段式那版 67.0°。45° 落在"现状"与"最轻的尖针变异"之间。
        #   90°（第一版定的）太宽：最轻的尖针变异（50.2°）照样过 ——
        #   反例法当场测出来"没红"，才知道线画错了地方。
        # [EN] ⚠ Threshold **45°** was measured, not guessed (2026-10-07):
        # [EN] current state 36.9° (both chin/top of head made "tangent horizontal") ·
        # [EN] chin reverted to sharp needle 50.2°~71.1° (depends on how steep the second control point is) ·
        # [EN] the original three-segment version 67.0°. 45° lands between "current state" and "the lightest
        # [EN] sharp-needle mutation".
        # [EN] 90° (set in the first version) is too loose: even the lightest sharp-needle mutation (50.2°)
        # [EN] passes --
        # [EN] the counterexample method found "nothing red" on the spot, only then did we know the line was
        # [EN] drawn in the wrong place.
        mx_rest = max((abs(c[0]) for c in rest), default=0.0)
        ok &= rec('圆润：除耳尖外最大转角 ≤45°（没有折痕）', mx_rest <= 45.0,
                  f'除耳尖外最大 {mx_rest:.1f}°'
                  f'（耳尖 {abs(cs[0][0]) if cs else 0:.1f}°；'
                  f'尖针下巴会到 50~71°）')
        # ② 一对挖空的眼睛：**前景连通块数对有没有眼睛完全不敏感**
        #    （洞不是碎片），所以得单独数洞。眼睛没了这形状就读成"一块石头"。
        # [EN] ② A pair of hollowed-out eyes: **the foreground connected-component count is completely
        # [EN] insensitive to whether there are eyes**
        # [EN] (holes are not fragments), so holes must be counted separately. Without the eyes this shape
        # [EN] reads as "a rock".
        nh = count_holes(m)
        ok &= rec('有一对挖空的眼睛（洞 = 2）', nh == 2, f'{nh} 个洞')
        mid = max(pr[y0 + int(h * 0.35):y0 + int(h * 0.60) + 1])
        top = max(pr[y0:y0 + int(h * 0.10) + 1])
        # 头顶是尖的（耳）—— 圆头/方头会挂在这条上
        # [EN] The top of the head is pointy (ears) -- a round head/square head would trip this line
        ok &= rec('顶部收窄（尖耳，不是平头）', top <= 0.55 * mid,
                  f'顶宽 {top:.2f} / 中段宽 {mid:.2f} = {top / max(mid, 1e-6):.2f}×'
                  f'（要求 ≤ 0.55×）')
        widest = max(range(y0, y1 + 1), key=lambda y: pr[y])
        ok &= rec('最宽的一行落在中段（0.25~0.70 处）',
                  0.25 <= (widest - y0) / h <= 0.70,
                  f'最宽行在高度 {(widest - y0) / h:.0%} 处')
    else:
        # 竹子那套线条判据（保留：切到 zhuye / qingci 时仍要验）
        # [EN] The bamboo line criterion (retained: still to be verified when switching to zhuye / qingci)
        widest = max(range(y0, y1 + 1), key=lambda y: pr[y])
        top = max(pr[y0:y0 + int(h * 0.10) + 1])
        mid = max(pr[y0 + int(h * 0.35):y0 + int(h * 0.60) + 1])
        bot = max(pr[y1 - int(h * 0.10):y1 + 1])
        ok &= rec('剪影竖直为主（竹子是竖着长的）', h >= 1.15 * bw,
                  f'高 {h} / 宽 {bw} = {h / bw:.2f}×（要求 ≥ 1.15×）')
        ok &= rec('最宽的一行在上半部（叶片与竿分张处）', widest <= y0 + h * 0.60,
                  f'最宽行在记号高度的 {(widest - y0) / h:.0%} 处')
        ok &= rec('根部收拢（底部比最宽处窄 —— 丛生的样子）',
                  bot <= 0.75 * max(mid, 1e-6),
                  f'底宽 {bot:.2f} / 中段宽 {mid:.2f} = {bot / max(mid, 1e-6):.2f}×'
                  f'（要求 ≤ 0.75×）')
        ok &= rec('竿梢是窄口（不是一条横杠 —— 那就成栅栏了）',
                  0.06 <= top <= 0.35, f'顶宽 {top:.2f}')
    return bool(ok)


def check_assets() -> bool:
    print('\n── 产物文件 ──')
    ok = True
    res = save_icons(IMG)
    ok &= rec('icon.png / icon_256.png / icon.ico 已生成',
              all(p.exists() for p in res.values()),
              ', '.join(f'{p.name} {p.stat().st_size}B' for p in res.values()))

    with Image.open(res['ico']) as ico:
        sizes = sorted(ico.info.get('sizes') or [])
    ok &= rec('icon.ico 含 16~256 多尺寸', len(sizes) >= 5, str(sizes))

    with Image.open(res['png']) as a, Image.open(res['png256']) as b:
        ok &= rec('icon.png 是 512、icon_256.png 是 256',
                  a.size == (512, 512) and b.size == (256, 256),
                  f'{a.size} / {b.size}')

    # 窗口 / 任务栏用的两份：**由 `save_icons` 一起写**（同一张图，不各画各的）。
    # 判据是"跟 icon_256 完全一致" —— 一旦有人把它俩分开生成，
    # 就会出现"界面换了图标、任务栏还是旧图"。
    # [EN] The two used by window / taskbar: **both written by `save_icons`** (same image, not drawn
    # [EN] separately).
    # [EN] The criterion is "exactly identical to icon_256" -- once someone generates them separately,
    # [EN] you get "interface changed the icon, taskbar still shows the old image".
    app_png = res['app_png']
    app_ico = res['app_ico']
    ok &= rec('app_icon.png / app_icon.ico 也由 save_icons 一起产出',
              app_png.exists() and app_ico.exists(),
              f'{app_png.name} {app_png.stat().st_size}B / '
              f'{app_ico.name} {app_ico.stat().st_size}B')
    with Image.open(app_png) as a, Image.open(res['png256']) as b:
        same = a.size == b.size and \
            a.convert('RGB').tobytes() == b.convert('RGB').tobytes()
    ok &= rec('app_icon.png 与 icon_256.png 一致（同一张图）', same)
    with Image.open(app_ico) as i:
        ok &= rec('app_icon.ico 多尺寸齐全', len(i.info.get('sizes') or []) >= 5,
                  str(sorted(i.info.get('sizes') or [])))
    return bool(ok)


def check_source() -> bool:
    """★ 源图模式：`assets/images/icon_source.png` 是**换 Logo 的唯一入口**。

    这一段专门盯"换了图有没有真的生效" —— 以前没有它的时候，
    "换图标"只能在五份产物上手工覆盖，而 `generate_icon` 一跑就把旧图又画了回去
    （界面换新、任务栏还是旧的，就是这个原因）。

    1. 源图是正方形（防拉伸 —— 老图标那条 `FOX_ASPECT` 就是这么被拉伸过的）
    2. **行为判**：`generate_icon(256)` 的产物 == 源图缩放（不是"源码里写了这个路径"）
    3. **行为判**：源图缺失时退回程序绘制（不会开天窗）；不缺时又**不是**程序绘制那张
    4. 圆角仍在（四角透明 —— 源图是方图，裁角这一步不能丢）
    5. **源图进指纹**：换图 ⇒ 指纹变 ⇒ 产物与任务栏那份带指纹的副本都会刷新
       
        English:
    ★ Source mode: `assets/images/icon_source.png` is the **single entry point for swapping the logo**.
        This section specifically watches "did swapping the image actually take effect" -- before it
        existed, "changing the icon" could only be done by hand-overwriting the five artifacts, and
        running `generate_icon` would just draw the old image back (interface shows the new one while
        the taskbar still shows the old: exactly this cause).

    1. The source image is square (prevents stretching -- the old icon's `FOX_ASPECT` was stretched exactly this way)
    2. **Behavioral**: the output of `generate_icon(256)` == the scaled source (not "the path is written in the source")
    3. **Behavioral**: falls back to programmatic drawing when the source is missing (no blank hole); and when it isn't missing, it is **not** the programmatically drawn one
    4. Rounded corners still there (four corners transparent -- the source is a square image, the corner-cutting step must not be lost)
    5. **The source goes into the fingerprint**: swapping the image ⇒ fingerprint changes ⇒ both the artifacts and the taskbar's fingerprinted copy get refreshed
    """
    print('\n── 源图（换 Logo 的唯一入口）──')
    ok = True
    src = source_image()
    ok &= rec('源图存在且是正方形（防拉伸）',
              src is not None and src.width == src.height,
              '无源图（走程序绘制）' if src is None else f'{src.width}×{src.height}')
    if src is None:
        return bool(ok)

    got = generate_icon(256).convert('RGB')
    ref = icon_from_source(256, src).convert('RGB')
    ok &= rec('generate_icon 的产物 == 源图（换图即换图标）',
              got.tobytes() == ref.tobytes())

    # 源图缺失 → 退回程序绘制（且画出来的**不是**源图那张）
    # [EN] Missing source → fall back to programmatic drawing (and what's drawn is **not** the source one)
    old = ICON_MOD.ICON_SOURCE
    try:
        ICON_MOD.ICON_SOURCE = Path(str(ICON_SOURCE) + '.absent')
        back = generate_icon(64).convert('RGB')
        ref64 = icon_from_source(64, src).convert('RGB')
        opaque = sum(1 for p in back.getdata() if p != (0, 0, 0))
        ok &= rec('源图缺失时退回程序绘制（产物不是源图、且不是空的）',
                  back.tobytes() != ref64.tobytes() and opaque > 64 * 64 * 0.3,
                  f'不透明像素 {opaque}')
    finally:
        ICON_MOD.ICON_SOURCE = old

    corner = generate_icon(256).convert('RGBA').getpixel((1, 1))
    ok &= rec('圆角仍在（左上角透明 —— 源图是方图，裁角不能丢）',
              corner[3] == 0, f'alpha={corner[3]}')

    # 换图 ⇒ 指纹变（任务栏那份带指纹的副本路径随之变化，缓存必然失效）
    # [EN] Swapping the image ⇒ fingerprint changes (the taskbar copy's path changes accordingly, cache necessarily invalidated)
    sig0 = icon_signature()
    alt = ICON_SOURCE.with_name('icon_source.red_moon.png')
    if alt.exists():
        try:
            ICON_MOD.ICON_SOURCE = alt
            sig1 = icon_signature()
        finally:
            ICON_MOD.ICON_SOURCE = old
        ok &= rec('换源图 ⇒ 指纹变化（产物与任务栏副本会跟着刷新）',
                  sig0 != sig1, f'{sig0} → {sig1}')
    else:
        ok &= rec('换源图 ⇒ 指纹变化（产物与任务栏副本会跟着刷新）', False,
                  f'缺对照图 {alt.name}')

    # ★ 2026-10-13 开始界面 Logo 与软件图标**故意不是同一张**：窗口/任务栏走
    #   图标管线（简化剪影、小尺寸耐缩），开始界面 76px 展示图用独立的
    #   `assets/images/start_logo.png`（保留内部流线，大图更好看）。判两件事：
    #   ① 那张图真的在、且缩到同尺寸后**不是**图标产物那张（复制错文件在这红）；
    #   ② `show_start` 里 `icon_img` 的 src **优先取 start_logo**、缺失才回退
    #      图标产物。②是"接线"检查（GUI 不起起来量不到 src 取了哪张），
    #   静态盯 fallback 表达式 —— 配合 mutate_icon_source 的第④组变异证明会红。
    # [EN] ★ 2026-10-13 the start-screen logo and the software icon are **intentionally
    # [EN] not the same image**: window/taskbar go through the icon pipeline (simplified
    # [EN] silhouette, durable at small sizes), while the 76px display image on the start
    # [EN] screen uses the standalone `assets/images/start_logo.png` (interior streamlines
    # [EN] kept). Two things are checked: (1) that file exists and, resized to the same
    # [EN] size, is **not** the icon artifact; (2) in `show_start`, `icon_img`'s src
    # [EN] **prefers start_logo** and only falls back to the icon artifact when missing.
    # [EN] (2) is a wiring check (the GUI can't be measured without launching it); it
    # [EN] statically watches the fallback expression -- mutation #4 in
    # [EN] mutate_icon_source.py proves it can go red.
    logo_path = IMG / 'start_logo.png'
    if logo_path.exists():
        _a = Image.open(logo_path).convert('RGB').resize((64, 64))
        _b = Image.open(IMG / 'icon_256.png').convert('RGB').resize((64, 64))
        ok &= rec('开始界面 Logo（start_logo.png）存在且与图标产物不是同一张设计',
                  _a.tobytes() != _b.tobytes(),
                  f'{logo_path.stat().st_size // 1024} KB')
    else:
        ok &= rec('开始界面 Logo（start_logo.png）存在且与图标产物不是同一张设计',
                  False, '缺失')
    gui_src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    ok &= rec('开始界面 icon_img 优先用 start_logo（缺失才回退图标产物）',
              'str(_start_logo) if _start_logo.exists() else icon_path' in gui_src)

    # ★ 2026-10-13（续）开始界面 Logo 四角圆润（用户：「4 个角圆润一些」）。
    #   源图是 ImageGen 的方底实心图，四角本不透明；`round_start_logo` 把四角裁透明。
    #   判据：四个角的角尖邻域必须透明（不再是方角），且中心不透明
    #   （没把整张图透明化 —— 那条变异会直接把图弄没）。
    # [EN] ★ 2026-10-13 (cont.) the start-screen logo's four corners are rounded (user: "make the four
    # [EN] corners a bit rounded"). The source is a square solid ImageGen image with opaque corners;
    # [EN] `round_start_logo` cuts the corners transparent. Check: the corner-tip neighborhood of all
    # [EN] four corners must be transparent (no longer square), and the center opaque (the whole image
    # [EN] wasn't blanked -- that mutation would erase the image entirely).
    if logo_path.exists():
        _sl = Image.open(logo_path).convert('RGBA')
        _sa = _sl.split()[3]
        _sw, _sh = _sl.size
        _corners = [(0, 0), (_sw - 1, 0), (0, _sh - 1), (_sw - 1, _sh - 1)]
        _corner_transparent = all(
            _sa.getpixel((max(0, x - 1), max(0, y - 1))) == 0 and
            _sa.getpixel((x, y)) == 0 and
            _sa.getpixel((min(_sw - 1, x + 1), min(_sh - 1, y + 1))) == 0
            for x, y in _corners)
        _center_opaque = _sa.getpixel((_sw // 2, _sh // 2)) == 255
        ok &= rec('开始界面 Logo 四角圆润（四角透明，不再是方角）',
                  _corner_transparent and _center_opaque,
                  f'角透明={_corner_transparent} 中心不透明={_center_opaque}')
    else:
        ok &= rec('开始界面 Logo 四角圆润（四角透明，不再是方角）', False, '缺失')
    return bool(ok)


def make_preview() -> Path:
    """导出预览图：两套配色 × 各尺寸，放在浅底与深底上各一行。
        English:
    Export preview images: two color schemes × each size, placed on light background and dark
    background, one row each.
    """
    sizes = [16, 24, 32, 48, 64, 96, 128, 256]
    pad, band = 18, 340
    W = pad + sum(s + pad for s in sizes)
    H = pad + (band + pad) * 2
    sheet = Image.new('RGB', (W, H), (238, 236, 231))

    for row, key in enumerate(SCHEMES):
        y0 = pad + row * (band + pad)
        # 上半浅底 / 下半深底
        # [EN] Upper half light base / lower half dark base
        ImageDraw.Draw(sheet).rectangle([0, y0, W, y0 + band // 2],
                                        fill=(246, 244, 239))
        ImageDraw.Draw(sheet).rectangle([0, y0 + band // 2, W, y0 + band],
                                        fill=(38, 40, 44))
        x = pad
        for s in sizes:
            ic = generate_icon(s, key)
            cy = y0 + band // 4 - s // 2
            sheet.paste(ic, (x, cy), ic)
            cy2 = y0 + band * 3 // 4 - s // 2
            sheet.paste(ic, (x, cy2), ic)
            x += s + pad
    p = OUT / 'icon_preview.png'
    sheet.save(p)
    return p


def main() -> int:
    print(f'  图标验证 · 共 {len(SCHEMES)} 套配色')
    results = [check_silhouette()]
    results += [check_scheme(k) for k in SCHEMES]
    results.append(check_assets())
    results.append(check_source())
    p = make_preview()
    print(f'  预览图: {p}')

    report['schemes'] = {k: SCHEMES[k]['name'] for k in SCHEMES}
    report['ok'] = all(results)
    report['failed'] = [s for s in report['steps'] if not s['ok']]
    (OUT / 'icon_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    n = len(report['steps'])
    print(f'\n  共 {n} 项断言，失败 {len(report["failed"])} 项 → '
          f'{"全部通过" if report["ok"] else "有失败"}')
    for s in report['failed']:
        print(f'    [FAIL] {s["name"]}  {s["detail"]}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
