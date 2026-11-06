# -*- coding: utf-8 -*-
"""真机验证：界面透明度（UI_OPACITY）真的让背景图透出来。

★ 2026-10-13 用户点名把**方向反过来**了（原话：「100%应该是完全透明，
最低才是不透明」），所以这一支的语义整个倒了一遍：

    `UI_OPACITY` = **透明度**（数字越大越透），
    内部 `ui_opacity()` = **面板底色的不透明度** = `1 − 透明度`，夹在 `OPACITY_MIN` 之上。

要验的是什么
------------
1. **语义方向**：0% → 完全不透；70% → 底色只剩 30%；100% → 仍是 30%（可读性下限兜住）
2. **运行界面的叙事/输出区**：透明度升上去后，背景渗进来
3. **开始界面**（菜单卡）
4. **★ 对话框（天机）**：**不受影响**（用户：「这个不应该影响对话框，
   只影响初始界面和运行界面就行了」）—— 这一条是**反向断言**：
   两种透明度下对话框纸面必须**几乎一模一样**
5. **天机里的滑块**：存在、范围对、保存后值写进 .env
6. **★ 只有两个入口带透明度**（`show_start_screen` / `show_main_screen` 被
   `screen_surface` 包住）：进去时表面色带 alpha、**出来就还原**

怎么量「背景真的透出来了」
--------------------------
用**真背景图**（不是纯色），对同一块面板比较两种不透明度下的截图：

    mean|Δ|   面板整体颜色变了多少（背景掺进来了）
    std|Δ|    变化是否跟着背景花纹走（不是被均匀涂了一层灰）
    表面 std  面板表面在低透明度下是否变得不均匀（＝背后有花纹）

同一块面板在两种设置下**区域坐标完全一致**，所以差异只可能来自透明度本身。

注意：`tools/verify_ui_common.py` 里那个「纯色背景」是给**布局**量测用的，
不能用来验这件事 —— 纯色背景下透出来的还是同一个颜色，什么都验不出。

产出：assets/screenshots/opacity_*.png + opacity_report.json

English:
Real-machine verification: UI transparency (UI_OPACITY) really lets the background image show
through.
★ 2026-10-13 the user asked to **reverse the direction** ("100% should be fully transparent,
the minimum should be opaque"), so the semantics of this branch were flipped wholesale:
    `UI_OPACITY` = **transparency** (bigger number = more transparent),
    internal `ui_opacity()` = **the panel base color's opacity** = `1 - transparency`, clamped
    above `OPACITY_MIN`.
What to verify
------------
1. **Direction**: 0% -> fully opaque; 70% -> base color down to 30%; 100% -> still 30% (held by
   the readability floor)
2. **Run screen's narrative/output area**: when transparency goes up, the background bleeds in
3. **Start screen** (menu cards)
4. **★ Dialog** (天机): **unaffected** (user: "this must not affect dialogs, only the start and
   run screens") -- this one is a **reverse assertion**: the dialog's paper must be **nearly
   identical** at the two transparencies
5. **Slider in 天机**: exists, range correct, value written to .env after save
6. **★ Only two entry points carry transparency** (`show_start_screen` / `show_main_screen` are
   wrapped by `screen_surface`): surface colors get alpha on the way in and are **restored on the
   way out**
How to measure "the background really shows through"
--------------------------
Use the **real background image** (not a solid color); for the same panel, compare screenshots
at two opacities:
    mean|Δ|   how much the panel's overall color changed (background mixed in)
    std|Δ|    whether the change follows the background pattern (not a uniform gray coating)
    表面 std  whether the panel surface becomes non-uniform at low opacity (= pattern behind it)
The same panel at the two settings has **exactly identical region coordinates**, so the
difference can only come from opacity itself.
Note: the "solid color background" in `tools/verify_ui_common.py` is for **layout** measurement,
and cannot be used to verify this — with a solid color background, what shows through is still
the same color, nothing can be verified.
Output: assets/screenshots/opacity_*.png + opacity_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402

import config as CFG_MOD                                 # noqa: E402
from config import CFG                                    # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

import gui.app_flet as AF                                    # noqa: E402
from gui.app_flet import (  # noqa: E402
    NovelWorldApp, C, INKC, DEFAULT_OPACITY, OPACITY_MIN, FIELD_OPACITY_MIN,
    DLG_W, DLG_H, ui_opacity, ui_transparency, field_alpha, apply_ui_opacity,
)
from store.project import Project  # noqa: E402
from i18n import set_lang  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

# ★ 2026-10-13：数字语义翻过来了 —— **越大越透**。
#   HIGH 是对照组（0% = 完全不透，纯色基准），LOW 是实验组（70% = 到底的最透）。
#   ⚠ 期望一律写**绝对字面量**（0.70 / 0.30 / 1.00），不写 `1 - OPACITY_MIN/100`
#     那种"从产品 import 的常量再算一遍" —— 变异 `OPACITY_MIN` 时判据的期望
#     跟着一起动 ⇒ 自证假绿（2026-10-13 那轮 5 条变异不红全是这个原因）。
# [EN] ★ 2026-10-13: the number's meaning flipped -- **bigger = more transparent**. HIGH is the
# [EN] control group (0% = fully opaque, solid baseline), LOW the experimental one (70% = the most
# [EN] transparent it gets).
# [EN] ⚠ Expectations are always **absolute literals** (0.70 / 0.30 / 1.00), never "recomputed from
# [EN] an imported product constant" like `1 - OPACITY_MIN/100` -- mutating `OPACITY_MIN` would move
# [EN] the expectation too => self-confirming fake-green (that was the root cause of all 5
# [EN] non-redding mutations in the 2026-10-13 round).
HIGH = 0            # 完全不透（对照组）
LOW = 70            # 最透（实验组）
# [EN] Fully opaque (control group)
# [EN] Most transparent (experimental group)

# 阈值：先跑一遍看实际数字再定稿，宁可说清「为什么是这个数」
DIFF_MEAN_MIN = 8.0     # mean|Δ| 下限
DIFF_STD_MIN = 3.0      # std|Δ| 下限：变化要带着背景花纹，不是均匀一层
STD_RATIO_MIN = 1.8     # 表面 std 的放大倍数（低透明度 / 完全不透）
SAME_MEAN_MAX = 1.5     # 「必须一模一样」那条：mean|Δ| 上限（噪声级）
# [EN] Amplification factor for surface std (low opacity / fully opaque)
# [EN] The "must be identical" one: mean|Δ| upper bound (noise level)
# [EN] Thresholds: run once first to see the actual numbers before finalizing; better to clearly
# [EN] explain "why this number"
# [EN] mean|Δ| lower bound
# [EN] std|Δ| lower bound: the change must carry the background pattern, not a uniform layer
# [EN] Amplification factor for surface std (low opacity / fully opaque)

report: dict = {'steps': [], 'high': HIGH, 'low': LOW}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(f'  {"[OK]  " if ok else "[FAIL]"} {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return ok


def set_opacity(v: int) -> None:
    CFG.set('UI_OPACITY', v)
    apply_ui_opacity()


def pure(color: str) -> tuple[int, int, int]:
    """颜色的纯色值（不带 alpha）。全不透明时屏幕上就是这个颜色。
        English:
    The solid-color value of the color (without alpha). When fully opaque, this is the color on
    screen.
    """
    return VU.hex_rgb(color)


def region_mean(im, bbox) -> tuple[float, float, float]:
    x0, y0, x1, y1 = bbox
    px = [im.getpixel((x, y)) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    n = max(1, len(px))
    return tuple(sum(p[i] for p in px) / n for i in range(3))


def colour_dist(a, b) -> float:
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


# ══════════════════════════════════════════════════════════════
#  1. 夹紧规则（纯配置层，不用渲染）
# [EN] 1. Clamping rules (pure config layer, no rendering needed)
# ══════════════════════════════════════════════════════════════
def check_clamp() -> bool:
    """★ 2026-10-13：整个第 1 节按**新语义**重写（数字越大越透）。

    ⚠ 期望全是**绝对字面量**（1.00 / 0.70 / 0.60 / 0.30），不用
      `OPACITY_MIN` 去算 —— 变异 `OPACITY_MIN` 时两边一起动 ⇒ 自证假绿。

        English:
    ★ 2026-10-13: the whole section 1 was rewritten for the **new semantics** (bigger number =
    more transparent).
        ⚠ The expectations are all **absolute literals** (1.00 / 0.70 / 0.60 / 0.30), not computed
        from `OPACITY_MIN` -- mutating `OPACITY_MIN` would move both sides => self-confirming
        fake-green.
    """
    print('\n── 1. 语义方向与下限 ──')
    ok = True
    set_opacity(0)
    ok &= rec('★★ 透明度   0% → 面板底色 **1.00**（完全不透，背景一点不透出）'
              ' —— 用户：「最低才是不透明」',
              abs(ui_opacity() - 1.00) < 1e-6,
              f'实际 {ui_opacity():.2f} / 期望 1.00')
    set_opacity(30)
    ok &= rec('★★ 透明度  30% → 面板底色 **0.70**（数字 = 透掉多少）',
              abs(ui_opacity() - 0.70) < 1e-6,
              f'实际 {ui_opacity():.2f} / 期望 0.70')
    set_opacity(70)
    ok &= rec('★★ 透明度  70% → 面板底色 **0.30**（正好到可读性那条底线）',
              abs(ui_opacity() - 0.30) < 1e-6,
              f'实际 {ui_opacity():.2f} / 期望 0.30')
    set_opacity(100)
    ok &= rec('★★★ 透明度 100% → 面板底色仍是 **0.30**（不是 0！）'
              ' —— 用户原话「100%应该是完全透明」，但拍板保留了'
              f' {OPACITY_MIN}% 的可读性下限：再透字就糊进背景花纹',
              abs(ui_opacity() - 0.30) < 1e-6,
              f'实际 {ui_opacity():.2f} / 期望 0.30（夹在可读性下限上）')
    # 成对：不是"越大越透"而是"越大越实"的话，上面四条里至少一条会红；
    #   但只验四点还可能被"恰好对上"糊弄过去，所以再钉**单调性**。
    # [EN] Paired: if it were "bigger = more solid" instead of "bigger = more transparent", at least
    # [EN] one of the four above would go red; but four points can still be faked by coincidence, so
    # [EN] pin down **monotonicity** as well.
    seq = [0, 20, 40, 60, 80, 100]
    vals = []
    for v in seq:
        set_opacity(v)
        vals.append(round(ui_opacity(), 4))
    ok &= rec('★★ 单调：透明度越大，面板底色**只减不增**（不是随手凑的四个点）',
              all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
              and vals[0] > vals[-1],
              f'透明度{seq} → 底色{vals}')
    # ★ 界面上给作者看的那个数（滑杆上的 xx%）必须**原样**是 UI_OPACITY，
    #   不能跟着绕成 100−x —— 作者拖到 30，界面就得显示 30%。
    # [EN] ★ The number shown to the author (the xx% on the slider) must be **exactly** UI_OPACITY,
    # [EN] not flipped into 100-x -- drag it to 30 and the UI must show 30%.
    set_opacity(30)
    ok &= rec('★★ 界面上给作者看的「透明度」= `UI_OPACITY` 原值（30 → 30，不是 70）',
              ui_transparency() == 30,
              f'ui_transparency()={ui_transparency()} / 期望 30')
    set_opacity(70)
    ok &= rec(f'输入框另有 {FIELD_OPACITY_MIN}% 下限（面板只剩 30% 时输入框仍可读）',
              abs(field_alpha() - FIELD_OPACITY_MIN / 100) < 1e-6,
              f'field_alpha={field_alpha():.2f} / panel={ui_opacity():.2f}')
    # ⚠ `set_opacity()` 走的是 `apply_ui_opacity()` 的**默认值**，而默认值从 2026-10-13
    #   起是 `screen=False`（故意的安全默认，见 `apply_ui_opacity` 的说明）⇒ 面板此刻
    #   是不透明的。想看"带 alpha"那一版必须**显式**要一次。
    # [EN] ⚠ `set_opacity()` goes through `apply_ui_opacity()`'s **default**, and since 2026-10-13
    # [EN] that default is `screen=False` (a deliberate safe default, see `apply_ui_opacity`) => the
    # [EN] panel is opaque right now. To see the alpha-carrying version you must **ask for it
    # [EN] explicitly**.
    apply_ui_opacity(screen=True)
    _a_panel_t = VU.hex_alpha(C['panel'])
    _a_text_t = VU.hex_alpha(C['text'])
    apply_ui_opacity(screen=False)
    _a_panel_f = VU.hex_alpha(C['panel'])
    ok &= rec('颜色自带 alpha 可解析（合成色可计算）',
              _a_panel_t < 1.0 and _a_panel_f == 1.0,
              f"screen=True 时 panel alpha={_a_panel_t}；"
              f'screen=False 时 panel alpha={_a_panel_f}')
    # ★ 文字色与描边**永不带 alpha**：半透明的字伤可读性（见 `apply_ui_opacity`）
    # [EN] ★ Text and stroke colors **never** carry alpha: semi-transparent text hurts readability
    # [EN] (see `apply_ui_opacity`)
    ok &= rec('★ 文字色**永远不透明**（半透明的字伤可读性，界面外观怎么调都不该变）',
              _a_text_t == 1.0,
              f'screen=True 时 text alpha={_a_text_t} / 期望 1.0')
    return bool(ok)


async def shot(page, name: str) -> bytes:
    page.update()
    await asyncio.sleep(0.5)
    data = await page.take_screenshot()
    (OUT / name).write_bytes(data)
    return data


def compare_region(label: str, im_high, im_low, bbox, *,
                   ratio_min: float = STD_RATIO_MIN) -> bool:
    """同一块区域在两种不透明度下的差异。
        English:
    The difference of the same region at two opacities.
    """
    hi = VU.surface_stats(im_high, bbox)
    lo = VU.surface_stats(im_low, bbox)
    d = VU.region_diff(im_high, im_low, bbox)
    ratio = (lo['std'] / hi['std']) if hi['std'] > 0.01 else float('inf')
    report.setdefault('regions', {})[label] = {
        'bbox': list(bbox),
        'surface_std_high': round(hi['std'], 2),
        'surface_std_low': round(lo['std'], 2),
        'surface_mean_high': round(hi['mean'], 1),
        'surface_mean_low': round(lo['mean'], 1),
        'std_ratio': None if ratio == float('inf') else round(ratio, 2),
        'diff_mean': round(d['mean'], 2),
        'diff_std': round(d['std'], 2),
    }
    ok = rec(f'{label}：面板颜色确实变了（背景掺进来）',
             d['mean'] >= DIFF_MEAN_MIN,
             f"mean|Δ|={d['mean']:.1f}（下限 {DIFF_MEAN_MIN}）")
    ok &= rec(f'{label}：变化跟着背景花纹走（不是均匀一层灰）',
              d['std'] >= DIFF_STD_MIN,
              f"std|Δ|={d['std']:.1f}（下限 {DIFF_STD_MIN}）")
    ok &= rec(f'{label}：表面在低透明度下变得不均匀',
              ratio >= ratio_min,
              f'表面 std {hi["std"]:.2f} → {lo["std"]:.2f}'
              f'（{ratio:.2f}×，下限 {ratio_min}×）')
    return bool(ok)


def assert_region_same(label: str, im_a, im_b, bbox, *,
                       mean_max: float = SAME_MEAN_MAX) -> bool:
    """★ 反向断言：同一块区域在两种设置下**几乎一模一样**。

    给「对话框不受透明度影响」用的（用户 2026-10-13：「这个不应该影响对话框」）。
    为什么不能沿用 `compare_region` 那一套"差异越大越好"的判据：
    它是**反的** —— 这里要的恰恰是"**没有差异**"。
    ⚠ 阈值不能写 0：截图有抗锯齿与 PNG 量化的噪声，实测完全不变时
      mean|Δ| 也有 0.x 级抖动；取 1.5 既吃得住噪声，又比"少了一个 alpha"
      造成的色差小一个数量级（面板底色 30% vs 100% 的差是几十）。

        English:
    ★ Reverse assertion: the same region is **nearly identical** at the two settings.
        For "dialogs are unaffected by transparency" (user 2026-10-13: "this must not affect
        dialogs"). Why the `compare_region` "bigger difference is better" logic can't be reused:
        it is **inverted** -- what's wanted here is precisely "**no difference**".
        ⚠ The threshold can't be 0: screenshots carry antialiasing and PNG quantization noise, so
        even a totally unchanged region jitters at the 0.x level in mean|Δ|; 1.5 both absorbs that
        noise and stays an order of magnitude below the color delta caused by "one missing alpha"
        (a panel base at 30% vs 100% differs by tens).
    """
    d = VU.region_diff(im_a, im_b, bbox)
    report.setdefault('regions', {})[label] = {
        'bbox': list(bbox), 'kind': 'must-be-identical',
        'diff_mean': round(d['mean'], 2), 'diff_std': round(d['std'], 2),
    }
    return bool(rec(f'{label}：两种透明度下**几乎一模一样**（对话框不受这个设置影响）',
                    d['mean'] <= mean_max,
                    f"mean|Δ|={d['mean']:.2f}（上限 {mean_max}；"
                    f'若受影响会是几十）'))


def walk(c, out, d=0):
    if c is None or d > 40:
        return
    out.append(c)
    for a in ('controls', 'content', 'actions', 'title'):
        v = getattr(c, a, None)
        if isinstance(v, list):
            for x in v:
                walk(x, out, d + 1)
        elif v is not None and hasattr(v, '__class__'):
            walk(v, out, d + 1)


def find_slider(root, *, lo=None, hi=None):
    """界面外观页里的**不透明度**滑块。

    ⚠ 不能拿"第一个 Slider"当它：2026-10-11 起同一页还多了一根
      **界面字号**滑杆（`min=80 max=150`），而它排在前面 —— 抓错了就会
      把 `value=46` 设到一个 `min=80` 的滑杆上，Flet 直接报错（整支脚本崩）。
      判据改成**按区间认**（不透明度 `OPACITY_MIN..100`）。

        English:
    The **opacity** slider on the Appearance tab.
        ⚠ Cannot take "the first Slider": since 2026-10-11 that page also has a
        **UI font-size** slider (`min=80 max=150`) sitting in front of it —— picking the wrong one
        sets `value=46` on a slider whose `min=80`, and Flet raises (the whole script crashes).
        The criterion is now **identified by range** (opacity `OPACITY_MIN..100`).
    """
    seen: list = []
    walk(root, seen)
    sliders = [c for c in seen if isinstance(c, ft.Slider)]
    if lo is not None or hi is not None:
        pick = [c for c in sliders
                if (lo is None or getattr(c, 'min', None) == lo)
                and (hi is None or getattr(c, 'max', None) == hi)]
        if pick:
            return pick[0]
    return sliders[0] if sliders else None


# ══════════════════════════════════════════════════════════════
async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    ok = check_clamp()
    # ⚠⚠ 与 `verify_run_modes` 同一个坑（它在那边已详细写明）：
    #   `isolate_projects_dir()` 返回**旧的**项目根，不是隔离目录。
    #   原来这么写会把夹具建进**用户真实的 Projects/**（实测污染过）。
    # ★ 改成**私有临时目录**（2026-10-08）：原来放在共享的 `_proj/透明度验证`
    #   下面，跑完若删不干净（Windows 上文件被占时 `safe_rmtree` 会静默放弃），
    #   残留会**污染别的脚本**（`verify_resume_menu` 因此假红过两次）。
    #   自己的场地自己用，谁也不用管谁。
    # [EN] ⚠⚠ Same pitfall as `verify_run_modes` (documented in detail there):
    # [EN] `isolate_projects_dir()` returns the **old** project root, not the isolated directory.
    # [EN] Written the old way, the fixtures would be created inside the user's **real Projects/** (has
    # [EN] actually polluted it before).
    # [EN] ★ Changed to a **private temp directory** (2026-10-08): previously placed under the shared [EN] `_proj/透明度验证`
    # [EN] directory; if not cleanly deleted after the run (on Windows `safe_rmtree` silently gives up when
    # [EN] files are locked),
    # [EN] the residue **pollutes other scripts** (`verify_resume_menu` false-redded twice because of
    # [EN] this).
    # [EN] Use your own yard, don't bother anyone else's.
    _iso = Path(tempfile.mkdtemp(prefix='nws_opacity_'))
    VU.isolate_projects_dir(_iso)
    proj_root = _iso / '透明度验证'
    try:
        # ── 2. 运行界面 ──
        # [EN] ── 2. Run screen ──
        print('\n── 2. 运行界面：叙事/输出区 ──')
        proj_root.mkdir(parents=True, exist_ok=True)
        for sub in ('设定集', '优化后设定', '完整设定集导出'):
            (proj_root / sub).mkdir(exist_ok=True)
        proj = Project(proj_root, '透明度验证')
        proj.write_nwsproj()
        app.current_project = proj

        set_opacity(HIGH)
        app.show_main_screen()
        im_hi = VU.image_of(await shot(page, 'opacity_1_main_op0.png'))
        panel_col = pure(C['panel_glass'])
        bbox = VU.panel_bbox(im_hi, panel_col, y_from=48)
        ok &= rec('全不透明时能定位到叙事/输出区', bbox is not None, str(bbox))
        if bbox:
            # 叙事区必须和侧栏面板同色（而不是输入框那种更实的纸）
            # [EN] The narrative area must be the same color as the sidebar panel (not the more solid paper of the
            # [EN] input box)
            m = region_mean(im_hi, bbox)
            d_panel = colour_dist(m, panel_col)
            d_field = colour_dist(m, pure(C['input_bg']))
            ok &= rec('叙事/输出区与侧栏面板用同一种半透明纸',
                      d_panel < d_field,
                      f'区域内均色 {tuple(round(v) for v in m)}；'
                      f'到面板色距离 {d_panel:.1f} < 到输入框色距离 {d_field:.1f}')

            set_opacity(LOW)
            app.show_main_screen()
            im_lo = VU.image_of(await shot(page, 'opacity_2_main_op70.png'))
            ok &= compare_region('运行界面·叙事/输出区', im_hi, im_lo, bbox)

        # ── 3. 开始界面 ──
        # [EN] ── 3. Start screen ──
        print('\n── 3. 开始界面：菜单卡 ──')
        app.current_project = None
        set_opacity(HIGH)
        app.show_start_screen()
        im_s_hi = VU.image_of(await shot(page, 'opacity_3_start_op0.png'))
        s_bbox = VU.panel_bbox(im_s_hi, pure(INKC['card']))
        ok &= rec('全不透明时能定位到开始界面菜单卡', s_bbox is not None, str(s_bbox))
        if s_bbox:
            set_opacity(LOW)
            app.show_start_screen()
            im_s_lo = VU.image_of(await shot(page, 'opacity_4_start_op70.png'))
            ok &= compare_region('开始界面·菜单卡', im_s_hi, im_s_lo, s_bbox)

        # ── 4. 对话框（天机）—— ★ 反向断言：**不受影响** ──
        #   ★★ 2026-10-13 用户点名：「这个不应该影响对话框，只影响初始界面和
        #     运行界面就行了」。
        #     这一节原来验的是"对话框纸面也跟着变"（旧的、错误的行为），
        #     现在整套反过来：两种透明度下对话框纸面必须**几乎一模一样**。
        #     为什么这条必须留着（不能简单删掉）：只验"运行界面会变"的话，
        #     把 `screen_surface` 的 `finally` 还原去掉 ⇒ 对话框跟着半透明，
        #     而上面第 2/3 节**照样全绿** —— 只有这条反向断言会红。
        # [EN] ── 4. Dialog (天机) -- ★ reverse assertion: **unaffected** ──
        # [EN] ★★ Named by the user on 2026-10-13: "this must not affect dialogs, only the start and
        # [EN] run screens".
        # [EN] This section used to verify "the dialog paper changes too" (the old, wrong behavior);
        # [EN] now it is inverted wholesale: the dialog paper must be **nearly identical** at the two
        # [EN] transparencies.
        # [EN] Why keep it (rather than just deleting it): verifying only "the run screen changes"
        # [EN] would let removing the `finally` restore in `screen_surface` pass -- dialogs would go
        # [EN] semi-transparent while sections 2/3 above **still all pass** -- only this reverse
        # [EN] assertion goes red.
        print('\n── 4. 对话框：天机纸面（**必须不受影响**）──')
        set_opacity(HIGH)
        app.show_global_settings()
        im_d_hi = VU.image_of(await shot(page, 'opacity_5_dialog_op0.png'))
        page.pop_dialog()
        await asyncio.sleep(0.3)
        # 纸册是**渐变**（左上受光 → 右下偏暖），单一颜色定位不准（试过，找不到）。
        # 所以用对话框自己的宽高常量推出一个确定的内框：对话框居中，
        # 取 70%×60% 的中央区域 —— 一定落在纸面里，又不碰到边缘的描金线。
        # [EN] The paper scroll is a **gradient** (lit from top-left → warmer toward bottom-right); a single
        # [EN] color can't locate it accurately (tried, couldn't find it).
        # [EN] So derive a definite inner rect from the dialog's own width/height constants: the dialog is
        # [EN] centered,
        # [EN] take the central 70%×60% region — guaranteed to fall on the paper, yet not touch the gilded
        # [EN] border at the edges.
        W, H = im_d_hi.size
        bw, bh = int(DLG_W * 0.70), int(DLG_H * 0.60)
        d_bbox = (W // 2 - bw // 2, H // 2 - bh // 2,
                  W // 2 + bw // 2, H // 2 + bh // 2)
        # 反向校验：这一块在全不透明时必须是「亮纸」而不是被遮罩压暗的背景
        # [EN] Reverse check: this block, when fully opaque, must be "bright paper" and not background dimmed
        # [EN] by the mask
        d_mean = region_mean(im_d_hi, d_bbox)
        d_lum = 0.299 * d_mean[0] + 0.587 * d_mean[1] + 0.114 * d_mean[2]
        ok &= rec('定位到的对话框区域确实是纸面（全不透明时足够亮）', d_lum > 200,
                  f'区域内均色 {tuple(round(v) for v in d_mean)} 亮度 {d_lum:.0f}')
        if d_lum > 200:
            set_opacity(LOW)
            app.show_global_settings()
            im_d_lo = VU.image_of(await shot(page, 'opacity_6_dialog_op70.png'))
            ok &= assert_region_same('对话框·天机纸面', im_d_hi, im_d_lo, d_bbox)
        while VU.open_dialogs(page):          # 清干净再进第 5 节（叠层会让下面抓错对话框）
            # [EN] Clean up before entering section 5 (stacked layers make the next step grab the
            # [EN] wrong dialog)
            page.pop_dialog()
        await asyncio.sleep(0.3)

        # ── 5. 天机里的滑块 + 保存（**写的是临时 .env，不碰用户的**）──
        # [EN] ── 5. Slider in 天机 + save (**writes a temp .env, doesn't touch the user's**) ──
        #
        # ★★ 2026-10-06 改：原来是"备份真 `.env` → 点保存 → 读真 `.env` 断言 → 还原"。
        #    那条路有两个毛病：
        #      ① **本身就在写用户的配置文件**（虽然还原了，但"备份/还原"这种约定
        #         在本项目已经栽过 5 次：只要中间有个异常/漏还原，用户的配置就没了）；
        #      ② 并行回归时它**必红** —— 回归器给子进程设了 `NWS_ENV_SINK`
        #         （见 `config.env_sink_path()`），保存会写到别处，
        #         这里读真 `.env` 自然读不到 `UI_OPACITY=46`。
        #    现在改成**把写盘路径重定向到一个临时文件**（`Config.redirect_save`，
        #    优先级高于 `NWS_ENV_SINK`）：断言读那个临时文件 ——
        #    照样验了"点保存真的落盘"，却**一个字节都不碰用户的 .env**。
        # [EN] ★★ Changed 2026-10-06: previously it was "back up the real `.env` → click save → read the real
        # [EN] `.env` to assert → restore".
        # [EN] That path had two flaws:
        # [EN] ① **It itself writes the user's config file** (though it restores, the "backup/restore"
        # [EN] convention
        # [EN] has already bitten this project 5 times: if any exception occurs or a restore is missed mid-way,
        # [EN] the user's config is gone);
        # [EN] ② Under parallel regression it **always false-reds** — the regressor sets `NWS_ENV_SINK` for the
        # [EN] child process
        # [EN] (see `config.env_sink_path()`), so the save writes elsewhere,
        # [EN] and reading the real `.env` here naturally won't find `UI_OPACITY=46`.
        # [EN] Now changed to **redirect the write path to a temp file** (`Config.redirect_save`,
        # [EN] which takes priority over `NWS_ENV_SINK`): the assertion reads that temp file —
        # [EN] still verifies "clicking save really persists", yet **doesn't touch a single byte of the user's
        # [EN] .env**.
        print('\n── 5. 天机滑块与保存 ──')
        set_opacity(DEFAULT_OPACITY)
        tmp_env = Path(tempfile.mkdtemp(prefix='nws_opacity_env_')) / '.env'
        prev_redirect = CFG_MOD.Config.redirect_save
        CFG_MOD.Config.redirect_save = tmp_env
        try:
            dlg = app.show_global_settings()
            page.update()
            await asyncio.sleep(0.4)
            # ★ 2026-10-13：范围从 `OPACITY_MIN..100` 改成 **0..100**（数字 = 透掉多少，
            #   0 就是完全不透）。期望写**绝对字面量 0**，不写 `OPACITY_MIN`。
            # [EN] ★ 2026-10-13: the range changed from `OPACITY_MIN..100` to **0..100** (the number
            # [EN] = how much is let through, 0 being fully opaque). The expectation is the
            # [EN] **absolute literal 0**, not `OPACITY_MIN`.
            slider = find_slider(dlg, lo=0, hi=100)
            ok &= rec('天机里有透明度滑块', slider is not None)
            if slider is not None:
                lo = getattr(slider, 'min', None)
                hi_ = getattr(slider, 'max', None)
                ok &= rec('★★ 滑块范围是 **0..100**（不再是 30..100）'
                          ' —— 新版「透明度」从 0（完全不透）到 100（最透）',
                          lo is not None and hi_ is not None
                          and float(lo) == 0 and float(hi_) == 100,
                          f'min={lo} max={hi_}（期望 0 / 100）')
                slider.value = 46
                page.update()
                await asyncio.sleep(0.2)
                handler = getattr(dlg.actions[0], 'on_click', None)
                if callable(handler):
                    handler(None)          # save() 不使用事件参数
                    # [EN] save() does not use the event argument
                    await asyncio.sleep(0.7)
                written = CFG.s('UI_OPACITY')
                env_txt = (tmp_env.read_text(encoding='utf-8', errors='replace')
                           if tmp_env.exists() else '')
                ok &= rec('保存后不透明度写进配置并落盘',
                          written == '46' and 'UI_OPACITY=46' in env_txt,
                          f'CFG={written}；落盘文件含 UI_OPACITY=46：'
                          f'{"UI_OPACITY=46" in env_txt}（写到 {tmp_env.parent.name}，'
                          f'不碰用户 .env）')
                # ★ 新语义：拖到 46 ⇒ 透掉 46% ⇒ 面板底色 **0.54**（不是 0.46）。
                #   期望写绝对字面量 0.54 —— 这一条直接把"方向"钉死：
                #   要是哪天又拧回去（拿 46 当底色），这里立刻红。
                # [EN] ★ New semantics: dragged to 46 => 46% let through => panel base **0.54** (not
                # [EN] 0.46). The expectation is the absolute literal 0.54 -- this nails the
                # [EN] direction down: if it ever gets flipped back (treating 46 as the base color),
                # [EN] this goes red immediately.
                ok &= rec('保存后立即生效（无需重启）：透明度 46% → 面板底色 **0.54**',
                          abs(ui_opacity() - 0.54) < 1e-6, f'{ui_opacity():.2f} / 期望 0.54')
        finally:
            CFG_MOD.Config.redirect_save = prev_redirect
            set_opacity(DEFAULT_OPACITY)

        # ── 6. ★ 只有「开始界面 / 运行界面」带透明度（对话框不受影响）──
        # [EN] ── 6. ★ Only the start / run screens carry transparency (dialogs unaffected) ──
        #
        # 为什么这一节必须存在：`screen_surface` 是**装饰器**，装饰器写错
        #   （比如漏 `@`、或者 `finally` 写成 `try` 里）在源码上**看不出来** ——
        #   上面第 4 节只是"结果上看对话框没变"，而这里验的是**机制**：
        #   进 `show_main_screen()` 时表面色带 alpha、**出来就还原**。
        #   ⚠ 用 spy 抓**调用序列**，不是"源码里有没有 @screen_surface" ——
        #     后者会被注释里的一句话骗过去（本项目已栽过）。
        # [EN] Why this section must exist: `screen_surface` is a **decorator**, and a mis-written
        # [EN] decorator (a missing `@`, or `finally` placed inside `try`) is **invisible in the
        # [EN] source** -- section 4 above only checks the *outcome* (the dialog didn't change),
        # [EN] while this checks the **mechanism**: surface colors carry alpha on the way into
        # [EN] `show_main_screen()` and are **restored on the way out**.
        # [EN] ⚠ Use a spy to capture the **call sequence**, not "is there an @screen_surface in the
        # [EN] source" -- the latter is fooled by a sentence in a comment (this project has been
        # [EN] bitten by that already).
        print('\n── 6. 只有开始/运行界面带透明度（机制）──')

        def _spy_sequence(fn, *a, **kw) -> list:
            """跑一次界面构建，记录 `apply_ui_opacity` 的**调用序列**与每次调用后
            面板底色的真实 alpha。

                English:
            Run one screen build, recording the **call sequence** of `apply_ui_opacity` and the
            panel's real alpha after each call.
            """
            seen: list = []
            _orig = AF.apply_ui_opacity

            def _spied(screen: bool = True):
                r = _orig(screen)
                seen.append(('screen' if screen else 'dialog',
                             round(VU.hex_alpha(AF.C['panel']), 3)))
                return r

            AF.apply_ui_opacity = _spied
            try:
                fn(*a, **kw)
            finally:
                AF.apply_ui_opacity = _orig
            return seen

        set_opacity(70)
        _seq_main = _spy_sequence(app.show_main_screen)
        ok &= rec('★★ 运行界面构建时，`apply_ui_opacity(screen=True)` 被调过'
                  '（机制：不是碰巧没变）',
                  any(k == 'screen' for k, _ in _seq_main),
                  f'调用序列 {_seq_main}')
        ok &= rec('★★★ 构建**结束后**表面色已还原成不透明（alpha == 1.0）'
                  ' —— 这就是"对话框不受影响"的机制；漏了这条还原，'
                  '之后所有对话框都会半透明',
                  any(k == 'dialog' and abs(v - 1.0) < 1e-6
                      for k, v in _seq_main),
                  f'调用序列 {_seq_main}（最后应出现 dialog/1.0）')
        ok &= rec('★★ 而且构建**期间**面板底色确实是 0.30（透明真的生效了）',
                  any(k == 'screen' and abs(v - 0.30) < 0.02
                      for k, v in _seq_main),
                  f'调用序列 {_seq_main}（screen 那次应约 0.30）')
        # 成对：把 `apply_ui_opacity(screen=False)` 单独调一次，面板必须回到 1.0
        #   —— 否则"还原"只是恰好没被调用。
        # [EN] Paired: call `apply_ui_opacity(screen=False)` once on its own, the panel must return
        # [EN] to 1.0 -- otherwise the "restore" merely happened not to be called.
        apply_ui_opacity(screen=True)
        _a_screen = VU.hex_alpha(C['panel'])
        apply_ui_opacity(screen=False)
        _a_dialog = VU.hex_alpha(C['panel'])
        ok &= rec('★ 成对：`screen=True` 时面板带 alpha、`screen=False` 时**完全不透明**',
                  abs(_a_screen - 0.30) < 0.02 and abs(_a_dialog - 1.0) < 1e-6,
                  f'screen=True → {_a_screen}（期望 0.30）；'
                  f'screen=False → {_a_dialog}（期望 1.0）')
        # 收尾：还原成"对话框态"，免得污染后面（其实脚本到此为止，但要留个干净场）
        # [EN] Clean up: restore the "dialog state" so we don't pollute what follows (the script
        # [EN] ends here, but leave a clean ground anyway)
        set_opacity(DEFAULT_OPACITY)
        _seq_start = _spy_sequence(app.show_start_screen)
        ok &= rec('★★ 开始界面同样：`screen=True` 进去、以 `dialog`(1.0) 收尾',
                  any(k == 'screen' for k, _ in _seq_start)
                  and any(k == 'dialog' and abs(v - 1.0) < 1e-6
                          for k, v in _seq_start),
                  f'调用序列 {_seq_start}')

        report['ok'] = bool(ok)
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        try:
            if proj_root.exists():
                # ⚠ 删 `_iso`（整层 `_proj/透明度验证`），不是只删 `proj_root`：
                #   只删里面那层会留下一个空壳目录，而 `scan_projects` 扫的是
                #   `_proj/*/`（**别的脚本**共用这一层）—— 残留会变成
                #   "拾卷里凭空多出一本书"（2026-08-08 那次假红的根因）。
                # [EN] ⚠ Delete `_iso` (the whole `_proj/透明度验证` layer), not just `proj_root`:
                # [EN] Deleting only the inner layer leaves an empty shell directory, and `scan_projects` scans
                # [EN] `_proj/*/` (**shared by other scripts**) — the residue becomes
                # [EN] "a book appearing out of nowhere in the retrieval" (the root cause of the 2026-08-08 false-red).
                VU.safe_rmtree(_iso, ignore_errors=True)
        except Exception:
            pass
        (OUT / 'opacity_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        failed = [s for s in report['steps'] if not s['ok']]
        print(f'\n  共 {len(report["steps"])} 项断言，失败 {len(failed)} 项 → '
              f'{"全部通过" if report["ok"] else "有失败"}')
        for s in failed:
            print(f'    [FAIL] {s["name"]}  {s["detail"]}')
        print(f'  报告: {OUT / "opacity_report.json"}')
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` raises
        # [EN] CancelledError
        # [EN] which cancels this coroutine; writing `exit_now(...)` on the line after `await shutdown(page)`
        # [EN] **has never executed** (exit code always 0 = false-green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    ft.run(main)
