# -*- coding: utf-8 -*-
"""从母版背景 `title_bg.webp` 裁一块「淡而不花」的区域，做成启动窗口（splash）的底图。

★★★ 2026-10-24 起**已被 `tools/make_splash_art.py` 取代**（不要再跑这一支）。
    原因：用户要"参考背景图画一幅古代经典小说为题的底图"，而"从母版上裁一块最平的"
    必然裁出**一张空白的纸**（现在收起态几乎什么都没有，就是这么来的）。
    新工具拿一幅真的画、按区域限制墨量，产出**同一对文件名**（`title_bg_splash*.png`），
    所以替换成品不需要改任何代码。保留这个文件只为"想恢复旧做法"时能一键回去。
    ⚠ 两支**不要交替跑**：最后跑的那一支决定成品，而它们的设计前提是相反的。
[EN] ★★★ Superseded by `tools/make_splash_art.py` on 2026-10-24 (do not run this one any more).
[EN] The user asked for an actual painting; "crop the flattest patch of the master" necessarily
[EN] yields **blank paper** (that is why the collapsed splash was nearly empty). The new tool takes
[EN] a real painting and caps ink per region, writing the **same two filenames**, so replacing the
[EN] artwork needs no code change. Kept only so the old look can be restored in one command.
[EN] ⚠ Never alternate the two: whichever ran last decides the output, and their premises conflict.


用户 2026-10-17：「启动界面背景图你看是否可以从完整背景图里截取一部分颜色较淡的部分，
现在好像有点花」—— 于是这里不再整张缩略（缩略会把全图的细节都压进 860px 里 ⇒ 看着花），
改成**在母版上滑动候选窗口**，按「亮、素、平」三个维度打分，挑最好的一块裁下来。

怎么算「淡而不花」
------------------
对每一个候选窗口（母版上滑动）量四件事，各自归一化后加权求和：
  · `mean`  灰度均值      —— 越高越淡（想要亮）
  · `std`   灰度标准差    —— 越低越平（不要大明暗对比）
  · `sat`   HSV 饱和度均值 —— 越低越素（不要浓墨重彩）
  · `edge`  Sobel 梯度能量 —— 越低越干净（不要碎笔触/密集纹理）
另外 `share_bright`（亮度 ≥ 200 的像素占比）作为「淡」的直观佐证，只进诊断不进打分。

产出两张（tkinter 的 `PhotoImage` 只认 PNG/GIF，吃不下 WebP，所以成品必须是 PNG）：
  · `title_bg_splash.png`       860×480  收起态
  · `title_bg_splash_tall.png`  860×620  展开态（命令行输出那一小块展开后）
两张都从**同一块母版区域**取，收起态取上半、展开态取整块 ⇒ 展开时画面只是"长出"一截，
不会跳成另一张图。

English:
Crop a "pale and calm" patch out of the master `title_bg.webp` and turn it into the splash
background. The user (2026-10-17) said the splash looked "busy" (花) -- and it did, because the
old one squeezed the whole 3840x2160 artwork into 860px. So instead of shrinking everything, we
**slide a candidate window over the master** and score each patch on four axes: brightness (want
high), grayscale std (want low), saturation (want low) and Sobel energy (want low). The best patch
wins. Both outputs come from the **same** master region (collapsed = top part, expanded = the whole)
so expanding only "grows" the picture instead of swapping it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / 'assets' / 'images'
MASTER = IMG / 'title_bg.webp'

W = 860                    #: 窗口宽（与 `launcher_splash.W` 一致）
H_BASE = 480               #: 收起态高
H_EXP = 620                #: 展开态高

#: 打分权重（合计 1.0）
WEIGHTS = {'mean': 0.30, 'std': 0.26, 'sat': 0.18, 'edge': 0.26}

#: 母版上候选窗口的取样倍率：1.5 ⇒ 裁 1290×930 再缩到 860×620（留足像素，不糊）
ZOOM = 1.5

#: 朱红印章（朱文方印）像素占比超过这个千分比 ⇒ 这个窗口**直接弃用**：
#: 印章是母版的一个视觉焦点，进了 860px 的小窗会跟 Logo/名字抢眼。
#: [EN] A window whose vermilion-seal share exceeds this (per-mille) is dropped outright:
#: [EN] the seal is a focal point on the master and would fight the logo/name in a 860px window.
SEAL_MAX = 0.30


def _norm(values: list[float], want_high: bool) -> list[float]:
    """把一串值线性拉到 0..1；`want_high=False` 时翻转（越小越好）。
    English: Linearly normalise a list to 0..1, flipping it when low values are better."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5] * len(values)
    out = [(v - lo) / (hi - lo) for v in values]
    return out if want_high else [1.0 - v for v in out]


def _metrics(im: Image.Image) -> dict:
    """一个候选窗口的四项指标（+ 亮部占比，仅供诊断）。
    English: The four metrics of one candidate patch (+ bright-pixel share, diagnostics only)."""
    g = im.convert('L')
    h = im.convert('RGB').convert('HSV').split()[1]
    edge = g.filter(ImageFilter.FIND_EDGES)
    st_g = g.histogram()
    total = sum(st_g) or 1
    bright = sum(st_g[200:]) / total
    return {
        'mean': sum(i * c for i, c in enumerate(st_g)) / total,
        'std': _std_from_hist(st_g, total),
        'sat': sum(i * c for i, c in enumerate(h.histogram())) / total,
        'edge': sum(i * c for i, c in enumerate(edge.histogram())) / total,
        'bright': bright,
    }


def _std_from_hist(hist: list[int], total: int) -> float:
    mean = sum(i * c for i, c in enumerate(hist)) / total
    var = sum(((i - mean) ** 2) * c for i, c in enumerate(hist)) / total
    return var ** 0.5


def scan(master: Path, ratio: float, step: int = 96, zoom: float = ZOOM) -> list[dict]:
    """在母版上滑动窗口打分，返回按分数降序的候选列表。
    English: Slide the window over the master and score; returns candidates, best first."""
    with Image.open(master) as im0:
        im = im0.convert('RGB')
    MW, MH = im.size
    cw = int(W * zoom)
    ch = int(cw / ratio)
    if cw > MW or ch > MH:
        raise SystemExit(f'母版 {MW}×{MH} 装不下 {cw}×{ch} 的窗口')

    cands = []
    for y in range(0, MH - ch + 1, step):
        for x in range(0, MW - cw + 1, step):
            patch = im.crop((x, y, x + cw, y + ch))
            small = patch.resize((W, int(W / ratio)), Image.LANCZOS)
            m = _metrics(small)
            # 印章在缩小后会掉色 ⇒ 在**原尺寸**上按朱红像素数（r 高 / g,b 低）数，
            # 顺便把印章落在窗口里的粗略位置也记下来（诊断用）。
            # [EN] The seal loses its colour when downscaled, so count vermilion pixels at full
            # [EN] resolution and also note roughly where in the window it sits (diagnostics).
            probe = patch.resize((320, int(320 / ratio)), Image.LANCZOS)
            px = list(probe.getdata())
            hot = [k for k, (r, g, b) in enumerate(px) if r > 150 and g < 110 and b < 110]
            m['seal'] = len(hot) / len(px) * 1000
            if hot:
                w_probe, h_probe = 320, max(1, len(px) // 320)
                m['seal_at'] = (round(sum(k % w_probe for k in hot) / len(hot) / w_probe, 2),
                                round(sum(k // w_probe for k in hot) / len(hot) / h_probe, 2))
            if m['seal'] > SEAL_MAX:
                continue                     # 印章压在窗口里 ⇒ 弃用
            m['x'], m['y'], m['w'], m['h'] = x, y, cw, ch
            cands.append(m)

    keys = list(WEIGHTS)
    normed = {k: _norm([c[k] for c in cands], want_high=(k == 'mean')) for k in keys}
    for i, c in enumerate(cands):
        c['score'] = sum(WEIGHTS[k] * normed[k][i] for k in keys)
    cands.sort(key=lambda c: -c['score'])
    return cands


def build(master: Path, box: tuple[int, int, int, int], out: Path,
          size: tuple[int, int], soften: float = 0.35) -> None:
    """裁 `box` → 缩到 `size` → 轻微软化（再压一点碎笔触）→ 写 PNG。
    English: Crop `box` -> resize to `size` -> soften slightly -> write PNG."""
    with Image.open(master) as im0:
        im = im0.convert('RGB').crop(box)
    im = im.resize(size, Image.LANCZOS)
    if soften > 0:
        im = Image.blend(im, im.filter(ImageFilter.GaussianBlur(2.2)), soften)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, 'PNG', optimize=True)


def main() -> int:
    ap = argparse.ArgumentParser(description='从母版背景裁一块淡的区域做 splash 底图')
    ap.add_argument('--scan', action='store_true', help='只扫描打分、打印候选，不写图')
    ap.add_argument('--top', type=int, default=12, help='扫描时打印前 N 个候选')
    ap.add_argument('--x', type=int, default=-1, help='手工指定裁剪左上角 x（不打分）')
    ap.add_argument('--y', type=int, default=-1, help='手工指定裁剪左上角 y（不打分）')
    ap.add_argument('--zoom', type=float, default=ZOOM, help='母版上的取样倍率')
    ap.add_argument('--soften', type=float, default=0.35, help='柔化强度 0..1')
    ap.add_argument('--json', default='', help='把扫描结果写成 JSON（给判据/诊断用）')
    ap.add_argument('--apply', action='store_true', help='按最佳（或手工）窗口写出两张成品')
    args = ap.parse_args()

    # 展开态更高 ⇒ 按 _tall 的比例去扫（收起态只是它上面的一截）
    ratio = W / H_EXP
    cands = scan(MASTER, ratio, zoom=args.zoom)

    if args.json:
        Path(args.json).write_text(
            json.dumps(cands[:200], ensure_ascii=False, indent=1), encoding='utf-8')

    if args.scan:
        print(f'母版 {MASTER.name}  窗口 {int(W*args.zoom)}×{int(W*args.zoom/ratio)}  '
              f'候选 {len(cands)} 个\n')
        print(f"{'#':>3} {'score':>6} {'亮度':>6} {'std':>6} {'饱和':>6} "
              f"{'边缘':>6} {'亮部%':>6}  位置(x,y)")
        for i, c in enumerate(cands[:args.top], 1):
            print(f"{i:>3} {c['score']:6.3f} {c['mean']:6.1f} {c['std']:6.1f} "
                  f"{c['sat']:6.1f} {c['edge']:6.1f} {c['bright']*100:6.1f}  "
                  f"({c['x']},{c['y']})")
        return 0

    if args.x >= 0 and args.y >= 0:
        x, y = args.x, args.y
    else:
        x, y = cands[0]['x'], cands[0]['y']
    cw, ch = int(W * args.zoom), int(W * args.zoom / ratio)
    box = (x, y, x + cw, y + ch)
    print(f'采用窗口 {box}（母版 {MASTER.name}）')

    if not args.apply:
        print('（只打印不写图；加 --apply 才写）')
        return 0

    # 展开态：整块窗口等比缩到 860×620
    build(MASTER, box, IMG / 'title_bg_splash_tall.png', (W, H_EXP), soften=args.soften)
    # 收起态：取同一块的**上半** ⇒ 展开时只是"长出来"，不会跳图
    top_h = int(ch * (H_BASE / H_EXP))
    build(MASTER, (x, y, x + cw, y + top_h), IMG / 'title_bg_splash.png',
          (W, H_BASE), soften=args.soften)
    for name in ('title_bg_splash.png', 'title_bg_splash_tall.png'):
        p = IMG / name
        with Image.open(p) as chk:
            print(f'  ✔ {name}  {chk.size[0]}×{chk.size[1]}  {p.stat().st_size/1024:.0f} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
