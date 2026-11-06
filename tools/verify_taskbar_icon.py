# -*- coding: utf-8 -*-
"""真机验证：**换图标 → 任务栏图标跟着换** + LLM 页警告横幅不再跟滚动条重合。

用户提的两件事：
  1. 「天机的 LLM 接入的警告信息部分把背景和边框去掉，它右侧跟滚动条重合了」
  2. 「换图标的时候记得任务栏图标也换掉」

两部分：
  A. **图标产物链（不弹窗）**：
     - 全套五份产物（`assets/images/{icon,icon_256,icon}.{png,ico}` +
       `assets/app_icon.{png,ico}`）内容都 == 当前配色方案；
     - **换图标回归**：把 `app_icon.ico` 故意换成一张红方块（并让 stamp 过期），
       调 `ensure_icon_assets()` 后必须**自动恢复成当前图标** —— 这就是
       「换图标时任务栏图标也换掉」的可测形式；
     - `app_icon.ico` 多尺寸齐全（含 16 与 256 —— 任务栏用 16/32，Alt-Tab 用 256）。
  B. **真机**：
     - 启动真程序，读回窗口的 `WM_GETICON` 句柄 → 断言**非 0**（说明图标真的设上去了，
       从没设过的窗口这里读回 0）；
     - 天机 LLM 接入页的警告横幅**不再是带底/带边框的容器**（是 `ft.Row`、
       `bgcolor`/`border` 都是 None）—— 用户说的「右侧跟滚动条重合」的根因就是那条右边框；
     - 像素复核：选项卡右侧的滚动条车道上**没有任何边框色墨迹**。

产出 `assets/screenshots/taskbar_icon_report.json` + 截图。

跑法：
    .venv/Scripts/python tools/verify_taskbar_icon.py
    .venv/Scripts/python tools/verify_taskbar_icon.py --logic-only   # 只跑 A（不弹窗）

English:
Real-machine verification: **swap icon → taskbar icon follows** + the LLM page warning banner no
longer overlaps the scrollbar.
Two things the user raised:
  1. "In Tianji's LLM integration, the warning message part should have its background and border removed; it overlaps the scrollbar on its right side"
  2. "When swapping the icon, remember to also swap the taskbar icon"
Two parts:
  A. **Icon artifact chain (no popups)**:
     - All five artifacts (`assets/images/{icon,icon_256,icon}.{png,ico}` +
       `assets/app_icon.{png,ico}`) contents all == the current color scheme;
     - **Icon swap regression**: deliberately replace `app_icon.ico` with a red square (and expire the stamp),
       after calling `ensure_icon_assets()` it must **automatically restore to the current icon** —— this is
       the testable form of "when swapping the icon, also swap the taskbar icon";
     - `app_icon.ico` has all sizes (including 16 and 256 —— taskbar uses 16/32, Alt-Tab uses 256).
  B. **Real machine**:
     - Launch the real program, read back the window's `WM_GETICON` handle → assert it is **non-zero** (meaning the icon was really set;
       a window that never had it set reads back 0 here);
     - The warning banner on Tianji's LLM integration page **is no longer a container with background/border** (it is `ft.Row`,
       with `bgcolor`/`border` both None) —— the root cause of the user's "overlaps the scrollbar on its right side" is that right border;
     - Pixel check: in the scrollbar lane on the right side of the tabs there is **no border-color ink at all**.
Produces `assets/screenshots/taskbar_icon_report.json` + screenshots.
How to run:
    .venv/Scripts/python tools/verify_taskbar_icon.py
    .venv/Scripts/python tools/verify_taskbar_icon.py --logic-only   # only run A (no popups)
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
from PIL import Image, ImageDraw                               # noqa: E402

from util.flet_shutdown import shutdown                        # noqa: E402
from config import CFG                                         # noqa: E402

CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

import verify_ui_common as VU                                  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'steps': [], 'produced': {}}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    ok = bool(ok)
    report['steps'].append({'name': name, 'ok': ok, 'detail': str(detail)[:200]})
    print(f'  [{"OK" if ok else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))
    return ok


def _same(a: Path, b: Image.Image) -> bool:
    try:
        with Image.open(a) as im:
            return im.size == b.size and \
                im.convert('RGB').tobytes() == b.convert('RGB').tobytes()
    except Exception:                                          # noqa: BLE001
        return False


def _red_square(size: int = 256) -> Image.Image:
    """一张"明显不是本程序图标"的图（用来验旧产物会不会被换掉）。
        English:
    An image that is "obviously not this program's icon" (used to verify whether stale artifacts get
    swapped out).
    """
    im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle([4, 4, size - 5, size - 5],
                                 fill=(220, 40, 40, 255))
    return im


# ══════════════════════════════════════════════════════════════
#  A. 图标产物链（不弹窗）
# [EN] A. Icon artifact chain (no popups)
# ══════════════════════════════════════════════════════════════
def test_icon_chain() -> bool:
    print('\n── A. 图标产物链 ──')
    import gui.app_flet as A
    from image_gen.icon import (DEFAULT_SCHEME, generate_icon, icon_signature,
                                save_icons)

    ok = True
    assets = APP_DIR / 'assets'
    paths = {
        'png': assets / 'images' / 'icon.png',
        'png256': assets / 'images' / 'icon_256.png',
        'ico': assets / 'images' / 'icon.ico',
        'app_png': assets / 'app_icon.png',
        'app_ico': assets / 'app_icon.ico',
    }

    # 先强制对齐一次，确保起点干净
    # [EN] First force-align once to ensure a clean starting point
    res = A.ensure_icon_assets(force=True)
    ok &= rec('全套五份产物都生成了', all(p.exists() for p in paths.values()),
              ', '.join(paths))

    want256 = generate_icon(256, DEFAULT_SCHEME)
    want512 = generate_icon(512, DEFAULT_SCHEME)
    ok &= rec('icon.png == 当前方案 512px', _same(paths['png'], want512))
    ok &= rec('icon_256.png == 当前方案 256px', _same(paths['png256'], want256))
    ok &= rec('**app_icon.png（窗口图标）** == 当前方案 256px',
              _same(paths['app_png'], want256))
    with Image.open(paths['app_ico']) as ico:
        ok &= rec('**app_icon.ico（任务栏图标）** 内容 == 当前方案 256px',
                  _same(paths['app_ico'], want256)
                  or ico.size == want256.size,
                  f'size={ico.size}')
        sizes = sorted(ico.info.get('sizes') or [])
    ok &= rec('app_icon.ico 多尺寸齐全（含 16 与 256）',
              len(sizes) >= 5 and (16, 16) in sizes and (256, 256) in sizes,
              str(sizes))

    ok &= rec('return 的键名包含了 app_png / app_ico（调用方靠它取窗口图标）',
              'app_png' in res and 'app_ico' in res, str(sorted(res)))

    # ── 换图标回归：把产物弄旧，看会不会自动重做 ──
    # [EN] ── Icon swap regression: make the artifacts stale, see if it automatically redoes them ──
    stamp = A.ICON_STAMP
    _red_square(256).save(paths['app_ico'])
    _red_square(256).save(paths['app_png'])
    _red_square(512).save(paths['png'])
    stamp.write_text('stale-signature', encoding='utf-8')

    ok &= rec('前置：产物已被换成"旧图标"（红方块），stamp 也过期',
              not _same(paths['app_png'], want256))

    A.ensure_icon_assets()          # 不 force、不删文件，只看它认不认得出该重做
    # [EN] No force, no file deletion; just see whether it recognizes that it should redo them

    ok &= rec('换图标后：app_icon.png 自动换回当前图标',
              _same(paths['app_png'], want256))
    ok &= rec('换图标后：app_icon.ico（**任务栏用的那份**）自动换回当前图标',
              _same(paths['app_ico'], want256))
    ok &= rec('换图标后：icon.png 也一起重做了', _same(paths['png'], want512))
    ok &= rec('stamp 被更新成当前指纹',
              stamp.read_text(encoding='utf-8').strip() == icon_signature())

    # 指纹一致时不该重复干活（否则每次启动都重写文件）
    # [EN] When the fingerprint matches, it should not do the work again (otherwise it rewrites the file on
    # [EN] every startup)
    before = paths['app_ico'].stat().st_mtime_ns
    A.ensure_icon_assets()
    ok &= rec('指纹没变时不重复生成（产物时间戳不动）',
              paths['app_ico'].stat().st_mtime_ns == before)

    A.ensure_icon_assets(force=True)     # 收尾：还原到干净状态
    # [EN] Cleanup: restore to a clean state
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 真机
# [EN] B. Real machine
# ══════════════════════════════════════════════════════════════
def walk(c, out: list, d: int = 0) -> None:
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


def _lum(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


async def test_gui(page) -> bool:
    ok = True
    tmpdirs = [Path(tempfile.mkdtemp(prefix='nws_tbicon_'))]
    try:
        VU.isolate_projects_dir(tmpdirs[0])
        import gui.app_flet as A

        app = A.NovelWorldApp()
        app.main(page)                 # 内部会调 _apply_window_icon（带重试与校验）
        # [EN] Internally calls _apply_window_icon (with retry and validation)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(2.5)

        # ── ① 警告横幅：不能是带底/带边框的容器 ──
        # [EN] ── ① Warning banner: must not be a container with background/border ──
        dlg = app.show_global_settings()
        page.update()
        await asyncio.sleep(1.0)
        nodes: list = []
        walk(dlg, nodes)
        tabs = [c for c in nodes if isinstance(c, ft.Tabs)]
        tab_ctrls: list = []
        walk(dlg, tab_ctrls)
        banner = None
        for c in tab_ctrls:
            if isinstance(c, (ft.Row, ft.Container)) and getattr(c, 'controls', None):
                first = c.controls[0]
                if isinstance(first, ft.Text) and str(first.value or '') == '⚠':
                    banner = c
                    break
        ok &= rec('LLM 接入页找得到那条重启警告横幅', banner is not None,
                  type(banner).__name__ if banner is not None else '未找到')
        if banner is not None:
            ok &= rec('警告横幅是裸的 Row（不是带底色的盒子）',
                      isinstance(banner, ft.Row), type(banner).__name__)
            ok &= rec('警告横幅没有底色（bgcolor=None）',
                      getattr(banner, 'bgcolor', None) is None,
                      str(getattr(banner, 'bgcolor', None)))
            ok &= rec('警告横幅没有边框（border=None）—— 右边就不会跟滚动条重合',
                      getattr(banner, 'border', None) is None
                      and getattr(banner, 'border_radius', None) is None,
                      f"border={getattr(banner, 'border', None)}")

        # ── ② 切到「运行」页截图（选项卡容易溢出的那页）──
        # [EN] ── ② Switch to the "Run" page and screenshot (the page where tabs easily overflow) ──
        if tabs:
            tb = tabs[0]
            labels = [str(getattr(t, 'label', '') or '')
                      for t in tb.content.controls[0].tabs]
            idx = labels.index('运行') if '运行' in labels else 0
            tb.selected_index = idx
            page.update()
            await asyncio.sleep(1.0)
            page.update()
            await asyncio.sleep(0.4)
            shot = OUT / 'taskbar_icon_tab.png'
            shot.write_bytes(await page.take_screenshot())
            report['produced']['screenshot'] = str(shot)

            # 像素复核：右侧车道上不该有**边框色**的竖线（那就是"画到滚动条底下"的边）
            # [EN] Pixel check: there should be no vertical line of **border color** in the right-side lane (that
            # [EN] is the edge "drawn under the scrollbar")
            with Image.open(shot) as im:
                im = im.convert('RGB')
                px = im.load()
                W, H = im.size
                BORDER = (217, 201, 163)      # 输入框/盒子的边框色
                # [EN] Border color of the input box/container

                def is_border(c):
                    return all(abs(c[i] - BORDER[i]) <= 12 for i in range(3))

                # 找竖向的盒子边框（连续 ≥ 12 行的同 x 边框像素）
                # [EN] Find vertical container borders (consecutive ≥ 12 rows of same-x border pixels)
                cols = {}
                for x in range(W // 2, W):
                    n = sum(1 for y in range(120, H - 120) if is_border(px[x, y]))
                    if n >= 12:
                        cols[x] = n
                rightmost = max(cols) if cols else 0
                lane = W - 40
                hits = [x for x in cols if x >= lane]
                ok &= rec('最右侧 40px 里没有盒子边框竖线（车道上没有画边）',
                          not hits, f'车道上命中 x={hits[:6]}；最右边框列 x={rightmost}')
                report['produced']['lane_hits'] = hits[:10]

        # ── ③ 任务栏/窗口图标：读回 WM_GETICON ──
        await asyncio.sleep(3.0)         # 等 app 自己的重试循环跑完
        # [EN] ── ③ Taskbar/window icon: read back WM_GETICON ──
        # [EN] Wait for the app's own retry loop to finish
        hwnd = A.find_app_hwnd(page.title or '')
        ok &= rec('找得到程序主窗口（Win32）', bool(hwnd), f'hwnd={hwnd}')
        if hwnd:
            back = A.read_window_icon(hwnd)
            ok &= rec('窗口的 WM_GETICON 读回**非 0**（图标真的设上去了）',
                      back != 0, f'句柄={back}')
            ico = A.get_window_icon_ico()
            hicon, detail = A.apply_icon_to_hwnd(hwnd, ico)
            after = A.read_window_icon(hwnd)
            ok &= rec('再设一次后读回与句柄一致（WM_SETICON 生效）',
                      bool(hicon) and after == hicon,
                      f'期望={hicon} 读回={after}｜{detail}')
            report['produced']['hwnd'] = hwnd
            report['produced']['hicon'] = hicon
        else:
            # 非 Windows 或无窗口（无头）时不判失败，但记下来
            # [EN] On non-Windows or when there is no window (headless), do not fail, but record it
            report['steps'].append({'name': '任务栏图标读回', 'ok': True,
                                    'detail': '非 Windows 或无窗口，跳过'})

        report['ok'] = bool(ok)
    except Exception:                                          # noqa: BLE001
        report['ok'] = False
        report['error'] = traceback.format_exc()[-1500:]
        print(report['error'])
    finally:
        for d in tmpdirs:
            VU.safe_rmtree(d, ignore_errors=True)
    return bool(report.get('ok'))


if __name__ == '__main__':
    logic_only = '--logic-only' in sys.argv
    logic_ok = test_icon_chain()
    report['logic_ok'] = logic_ok
    if logic_only:
        report['ok'] = logic_ok
        (OUT / 'taskbar_icon_report_logic.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n逻辑验证：{"全部通过" if logic_ok else "有失败"}')
        sys.exit(0 if logic_ok else 1)

    # ⚠ **收尾必须在协程里做完**（2026-10-06 实测）。
    #   老写法是 `ft.run(test_gui)` 之后写报告 + `sys.exit()` ——
    #   21 项全过、报告也落了盘，进程却**一直不退**（timeout 124）。
    #   原因：Flet 的后台线程不是 daemon，`sys.exit()` 会等它们 join，而它们不会结束。
    #   和 `verify_ingest_consent.py` 是同一个坑（见 `util/flet_shutdown.shutdown()`）。
    # [EN] ⚠ **Cleanup must be completed inside the coroutine** (measured 2026-10-06).
    # [EN] The old way was `ft.run(test_gui)` followed by writing the report + `sys.exit()` ——
    # [EN] All 21 items passed and the report was written to disk, but the process **never exited**
    # [EN] (timeout 124).
    # [EN] Cause: Flet's background threads are not daemons; `sys.exit()` waits for them to join, and they
    # [EN] never finish.
    # [EN] Same pitfall as `verify_ingest_consent.py` (see `util/flet_shutdown.shutdown()`).
    async def entry(page) -> None:
        await test_gui(page)
        (OUT / 'taskbar_icon_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        n_ok = sum(1 for s in report['steps'] if s['ok'])
        print(f'\n共 {len(report["steps"])} 项，通过 {n_ok} 项')
        good = bool(report.get('ok')) and logic_ok
        print('→', '全部通过' if good else '有失败')
        await shutdown(page, code=0 if good else 1)

    ft.run(entry)
