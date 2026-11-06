# -*- coding: utf-8 -*-
"""真机验证：对话图片四种方式（关闭 / ASCII 画 / PNG 矢量图 / 全彩文生图）。

校验四层：

1. **项目文件往返** —— 这一档设置存在 `.nwsproj` 的 `[项目] 对话图片=`，
   写进去、读回来都对（它是项目级设置，落在全局 `.env` 里就是错的）。
2. **四种模式各产各的** —— off 不出；ascii 出 `.txt` 字符画；png 出插画且
   画面"不糊"（色数/主色占比/亮度都在合理区间）；ai 在没配模型时**降级为 png**
   （用户的文章不能因为图片服务不通用不了）。
3. **上下文真的影响画面** —— 渡口/雨 与 后院/晴 画出来必须不一样；
   同一场景重复调用只画一次（推演一天会触发几十次，重画就白费）。
4. **界面与渲染** —— 书斋「图片」页里有这个下拉，四个选项名就是四个词
   （**不带序号**），说明小字随选择变；保存后 `.nwsproj` 真的落盘；
   中栏遇到 `.txt` 字符画要用**等宽文本**渲染（`ft.Image` 加载不了 .txt）。

产出：assets/screenshots/image_mode_*.png / image_mode_report.json

English:
Real machine verification: four ways of conversation images (off / ASCII art / PNG vector image
/ full-color text-to-image).
Four layers of verification:
1. **Project file round-trip** —— this option is stored in the `.nwsproj` as `[项目] 对话图片=`,
   writing it in and reading it back are both correct (it is a project-level setting; landing in the global `.env` would be wrong).
2. **Each of the four modes produces its own output** —— off produces nothing; ascii produces `.txt` character art; png produces an illustration and
   the image is "not blurry" (color count / dominant color ratio / brightness are all in reasonable ranges); ai **degrades to png** when no model is configured
   (the user's article must not become unusable just because the image service is unavailable).
3. **Context actually affects the image** —— ferry/rain and backyard/sunny must be drawn differently;
   repeated calls for the same scene draw only once (a day of simulation triggers dozens of times; redrawing would be wasted).
4. **UI and rendering** —— the study's "图片" page has this dropdown, and the four option names
are exactly the four words
   (**without index numbers**), the description small text changes with the selection; after saving, the `.nwsproj` is actually written to disk;
   when the center column encounters `.txt` character art it must render with **monospaced text** (`ft.Image` cannot load .txt).
Output: assets/screenshots/image_mode_*.png / image_mode_report.json
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import tempfile
import traceback
from collections import Counter
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                     # noqa: E402
from util.flet_shutdown import shutdown, exit_now      # noqa: E402
from config import CFG                                 # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('OUTPUT_FORMAT', 'script')
import verify_ui_common as VU
# ⚠ 本脚本会点到「保存」，而 `CFG.save()` 会把测试值写进用户真实 `.env`。
# 2026-10-06 的 `verify_model_probe` 就是这么把用户的 `LLM_BASE_URL` /
# `LLM_API_KEY` / `DEFAULT_PROJECTS_DIR` 覆盖掉的。全程禁用写盘。
# [EN] ⚠ This script clicks "Save", and `CFG.save()` writes test values into the user's real `.env`.
# [EN] This is exactly how `verify_model_probe` on 2026-10-06 overwrote the user's `LLM_BASE_URL` /
# [EN] `LLM_API_KEY` / `DEFAULT_PROJECTS_DIR`. Disable disk writes throughout.
VU.redirect_env_writes()                          # noqa: E402

from image_gen.hook import (MODE_LABELS, MODE_NOTES, MODES,   # noqa: E402
                            effective_mode, make_image_hook)
from i18n import t                                     # noqa: E402
from store.project import Project                      # noqa: E402
from store.runfolder import RunFolder                  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
report: dict = {'steps': [], 'produced': {}}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    print(f'  {"[OK]  " if ok else "[FAIL]"} {name}'
          + (f'  — {detail}' if detail else ''), flush=True)
    return bool(ok)


def head(t: str) -> None:
    print(f'\n── {t} ──', flush=True)


def file_hash(p) -> str:
    return hashlib.md5(Path(p).read_bytes()).hexdigest()[:10]


def image_stats(p) -> dict:
    """画面"糊不糊"：色数 / 主色占比 / 平均亮度。
        English:
    Whether the image is "blurry": color count / dominant color ratio / average brightness.
    """
    from PIL import Image
    im = Image.open(p).convert('RGB')
    small = im.resize((160, 90))
    c = Counter(small.get_flattened_data())
    px = list(im.convert('L').resize((160, 90)).get_flattened_data())
    return {'size': im.size, 'colors': len(c),
            'top_share': round(c.most_common(1)[0][1] / (160 * 90), 3),
            'brightness': round(sum(px) / len(px), 1)}


# ══════════════════════════════════════════════════════════════
#  逻辑：项目文件 / 四模式 / 上下文 / 去重
# [EN] Logic: project file / four modes / context / dedup
# ══════════════════════════════════════════════════════════════
def test_logic(tmp: Path) -> bool:
    ok = True
    proj = Project.create_new(tmp, '插图验证')
    run = RunFolder(proj.root, '第1次模拟2026-10-05-20-00').create()

    # ── ① 项目文件往返 ──
    # [EN] ── ① Project file round-trip ──
    proj.image_mode = 'ascii'
    proj.write_nwsproj()
    raw = proj.nwsproj_path.read_text(encoding='utf-8')
    back = Project.from_nwsproj(proj.nwsproj_path)
    ok &= rec('项目文件里有「对话图片」这一行',
              '对话图片=ascii' in raw,
              next((ln for ln in raw.splitlines() if '对话图片' in ln), ''))
    ok &= rec('写进 .nwsproj 后能原样读回来', back.image_mode == 'ascii',
              f'读到 {back.image_mode!r}')
    ok &= rec('这一档不在 .env 里（项目级设置就该落项目文件）',
              'IMAGE_MODE' not in Path(APP_DIR / '.env.example').read_text(
                  encoding='utf-8'))

    # ── ② 四种模式各产各的 ──
    # [EN] ── ② Each of the four modes produces its own output ──
    ctx_dock = {'place': '城东渡口', 'weather': '雨', 'time_label': '戌时 19:30',
                'cast': 2}
    got: dict[str, str | None] = {}
    for mode in MODES:
        proj.image_mode = mode
        hook = make_image_hook(proj, run)
        p = hook('scene', f'场景{mode}', dict(ctx_dock, place=f'城东渡口{mode}'))
        got[mode] = p
        report['produced'][mode] = (Path(p).name if p else None)
    ok &= rec('关闭：不出图', got['off'] is None, '返回 None')
    ok &= rec('ASCII 画：出 .txt 字符画',
              bool(got['ascii']) and str(got['ascii']).endswith('.txt'),
              Path(got['ascii']).name if got['ascii'] else '没产出')
    art = Path(got['ascii']).read_text(encoding='utf-8')
    ok &= rec('字符画里有场景说明（地点/时段/天气）且画了东西',
              '城东渡口' in art and '戌时' in art and len(art.splitlines()) >= 8,
              f'{len(art.splitlines())} 行 / {len(art)} 字')
    ok &= rec('PNG 矢量图：出 .png 且画面不糊',
              bool(got['png']) and str(got['png']).endswith('.png')
              and image_stats(got['png'])['colors'] > 400
              and image_stats(got['png'])['top_share'] < 0.55,
              str(image_stats(got['png'])) if got['png'] else '没产出')
    ok &= rec('全彩文生图：没配模型时降级为 PNG（不报错、有图）',
              bool(got['ai']) and str(got['ai']).endswith('.png'),
              Path(got['ai']).name if got['ai'] else '没产出')

    # ── ③ 上下文真的影响画面 ──
    # [EN] ── ③ Context actually affects the image ──
    proj.image_mode = 'png'
    hook = make_image_hook(proj, run)
    a = hook('scene', '渡口A', {'place': '城东渡口', 'weather': '雨',
                                'time_label': '戌时 19:30', 'cast': 3})
    b = hook('scene', '渡口B', {'place': '后院 · 井台', 'weather': '晴',
                                'time_label': '午时 12:00', 'cast': 0})
    ok &= rec('不同地点/天气/时段画出来不一样',
              file_hash(a) != file_hash(b),
              f'{Path(a).name} {file_hash(a)} vs {Path(b).name} {file_hash(b)}')
    same = hook('scene', '渡口A', {'place': '城东渡口', 'weather': '雨',
                                   'time_label': '戌时 19:30', 'cast': 3})
    ok &= rec('同一场景重复调用只画一次（不重复出图）',
              file_hash(same) == file_hash(a), Path(same).name)
    # ── ③ 肖像：**不再本地画**，只认开卷时生成好的项目级文生图 ──
    # 用户明确要求："肖像全部用文生图"，且"只在开卷时生成一次"。
    # 所以这里要断言两件事：没生成过 → 返回 None（**绝不兜底本地画**）；
    # 生成过 → 返回项目里那张（跨轮复用）。详情见 `verify_portraits.py`。
    # [EN] ── ③ Portraits: **no longer drawn locally**, only accept the project-level text-to-image
    # [EN] generated at open time ──
    # [EN] The user explicitly requested: "all portraits use text-to-image", and "generate only once at
    # [EN] open time".
    # [EN] So two things must be asserted here: not generated yet -> return None (**never fall back to
    # [EN] local drawing**);
    # [EN] generated -> return the one in the project (reused across turns). See `verify_portraits.py` for
    # [EN] details.
    from image_gen.portraits import portrait_dir, portrait_path
    ok &= rec('没生成过肖像时：不出图（不再本地画凑数）',
              hook('portrait', '主角', {'personality': '沉稳'}) is None,
              '返回 None（正文里这一段就不插肖像）')
    pd = portrait_dir(proj)
    pd.mkdir(parents=True, exist_ok=True)
    from PIL import Image as _I
    _I.new('RGB', (32, 32), (180, 120, 90)).save(portrait_path(proj, '主角'))
    pth = hook('portrait', '主角', {'personality': '沉稳'})
    ok &= rec('开卷时生成过肖像：直接用项目里那张（跨轮复用）',
              bool(pth) and Path(pth) == portrait_path(proj, '主角'),
              Path(pth).name if pth else '没返回')

    # ── ④ 回退链 ──
    # [EN] ── ④ Fallback chain ──
    fresh = Project(tmp / '没设过的项目', '没设过')
    old_env = CFG.s('SCRIPT_IMAGES')
    CFG.set('SCRIPT_IMAGES', 'off')
    off_ok = effective_mode(fresh) == 'off'
    CFG.set('SCRIPT_IMAGES', 'both')
    png_ok = effective_mode(fresh) == 'png'
    CFG.set('SCRIPT_IMAGES', old_env)
    ok &= rec('项目没设过时：尊重全局 SCRIPT_IMAGES=off', off_ok)
    ok &= rec('项目没设过时：默认走 PNG 矢量图（零成本）', png_ok)

    # ── ⑤ 界面用的名字与说明（不带序号）──
    # [EN] ── ⑤ Names and descriptions used by the UI (without index numbers) ──
    ok &= rec('四个选项名就是四个词，不带序号',
              [MODE_LABELS[m] for m in MODES]
              == ['关闭', 'ASCII 画', 'PNG 矢量图', '全彩文生图'],
              str([MODE_LABELS[m] for m in MODES]))
    ok &= rec('每个选项都有说明，且说明里说的是代价/长相',
              len(MODE_NOTES) == 4 and all(len(v) >= 6 for v in MODE_NOTES.values()),
              ' | '.join(f'{MODE_LABELS[m]}：{MODE_NOTES[m][:14]}…' for m in MODES))
    ok &= rec('变量名（off/ascii/png/ai）不出现在界面文案里',
              not any(k in MODE_LABELS[m] for m in MODES
                      for k in ('off', 'ascii', 'png', 'ai')),
              str(list(MODE_LABELS.values())))
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  真机：书斋下拉 + 保存落盘 + 中栏渲染字符画
# [EN] Real machine: study dropdown + save to disk + center column renders character art
# ══════════════════════════════════════════════════════════════
def _mk_project_with_ascii(tmp: Path) -> Path:
    """造一个项目：图片方式=ASCII 画，最近一天里带一张字符画。
        English:
    Create a project: image mode = ASCII art, with one piece of character art within the most recent
    day.
    """
    from display import script as S
    proj = Project.create_new(tmp, '插图预览')
    run = RunFolder(proj.root, '第1次模拟2026-10-05-20-00').create()
    proj.image_mode = 'ascii'
    proj.write_nwsproj()

    art = run.root / '插画' / '场景_城东渡口.txt'
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text('〔城东渡口 · 戌时 19:30 · 雨〕\n'
                   '        /\\   /\\        ~~~ ~~~\n'
                   '   ^[##]  _[##]   (=)  ~~~~\n'
                   '     o/     \\o\n', encoding='utf-8')

    sc = S.SceneScript(time_label='戌时 19:30', place='城东渡口 · 码头',
                       weather='雨', day=1, cast=['主角', '来人'])
    sc.add(S.narration('雨点砸在船板上，篷顶一片响。'))
    sc.add(S.image(str(art), '城东渡口', kind_hint='scene'))
    sc.add(S.dialogue('来人', '沈掌柜，码头上的货，今夜得挪。', to='主角'))
    sc.add(S.action('主角', '把手里的灯举高了些'))
    run.flush_daily_script(1, [sc], calendar_str='第1天·戌时', weather='雨',
                           cast=['主角', '来人'], tension='0.42→0.58')
    return proj.root


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


async def test_gui(page: ft.Page) -> bool:
    ok = True
    tmp = None
    try:
        VU.patch_flat_background()
        from gui.app_flet import NovelWorldApp

        tmp = Path(tempfile.mkdtemp(prefix='nws_imgmode_'))
        proj_root = _mk_project_with_ascii(tmp)
        proj = Project(proj_root, '插图预览')

        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(2.0)

        async def shot(name: str) -> bytes:
            page.update()
            await asyncio.sleep(0.5)
            data = await page.take_screenshot()
            (OUT / name).write_bytes(data)
            return data

        # ── 书斋：图片页里那个下拉 ──
        # [EN] ── Study: that dropdown in the image page ──
        app.current_project = proj
        dlg = app.show_project_settings()
        page.update()
        await asyncio.sleep(0.7)
        nodes: list = []
        walk(dlg, nodes)
        dropdowns = [c for c in nodes if isinstance(c, ft.DropdownM2)]
        labels = []
        for dd in dropdowns:
            labels += [getattr(o, 'label', '') or getattr(o, 'text', '')
                       for o in (dd.options or [])]
        report['gui_dropdown_labels'] = labels
        ok &= rec('书斋里有「对话图片」下拉，且四个选项名齐全',
                  all(n in labels for n in ('关闭', 'ASCII 画', 'PNG 矢量图',
                                            '全彩文生图')), str(labels))
        ok &= rec('选项名里没有序号（1. 2. 3. 4.）',
                  not any(str(x).strip()[:2] in ('1.', '2.', '3.', '4.')
                          for x in labels), str(labels))
        texts = [str(getattr(c, 'value', '')) for c in nodes
                 if isinstance(c, ft.Text)]
        # ★ 别写死关键词（说明文案一改就假失败）—— 直接比对**当前档位那句原文**。
        #   这比"包含某某词"更强：它证明小字跟着选择走，而不是贴了一句固定话。
        # [EN] ★ Don't hardcode keywords (the description text changing makes it falsely fail) —— directly
        # [EN] compare **the original text of the current option**.
        # [EN] This is stronger than "contains some word": it proves the small text follows the selection,
        # [EN] rather than being a fixed sentence pasted in.
        cur = effective_mode(app.current_project)
        ok &= rec('选项说明显示在下方小字里（且就是当前选中项那句）',
                  t(MODE_NOTES[cur]) in texts,
                  t(MODE_NOTES[cur])[:40])
        await shot('image_mode_shuzhai.png')

        # 切到「关闭」再保存 → 项目文件要真的变
        # [EN] Switch to "off" and save -> the project file must actually change
        img_dd = None
        for dd in dropdowns:
            opts = [getattr(o, 'label', '') or getattr(o, 'text', '') for o in (dd.options or [])]
            if 'ASCII 画' in opts:
                img_dd = dd
                break
        ok &= rec('找到「对话图片」下拉本体', img_dd is not None)
        if img_dd is not None:
            img_dd.value = 'off'
            page.update()
            await asyncio.sleep(0.3)
            for c in nodes:
                if isinstance(c, ft.Button) or c.__class__.__name__ in (
                        'FilledButton', 'TextButton'):
                    pass
            # 直接走保存路径（按钮回调就是 app 里那个闭包，这里用它的公开行为：
            # 改 value 后调用对话框的保存按钮）
            # 注意：Flet 1.0 的按钮文字在 **`content`**，而且往往是 `ft.Text`
            # 而不是字符串（`str(ft.Text)` 里没有文字）—— 要取出 `.value`。
            # [EN] Go directly through the save path (the button callback is that closure in the app; here we use
            # [EN] its public behavior:
            # [EN] change value then call the dialog's save button)
            # [EN] Note: in Flet 1.0 the button text is in **`content`**, and is often `ft.Text`
            # [EN] rather than a string (there is no text inside `str(ft.Text)`) —— you must extract `.value`.
            def _btn_label(ctrl) -> str:
                ct = getattr(ctrl, 'content', None)
                if isinstance(ct, ft.Text):
                    return str(ct.value or '')
                return str(ct or '')

            saved = False
            for c in nodes:
                if c.__class__.__name__ in ('FilledButton', 'TextButton'):
                    if '保存' in _btn_label(c) and getattr(c, 'on_click', None):
                        c.on_click(None)
                        saved = True
                        break
            ok &= rec('点了保存按钮', saved,
                      '、'.join(_btn_label(c) for c in nodes
                                if c.__class__.__name__ in ('FilledButton',
                                                            'TextButton')))
            await asyncio.sleep(0.6)
            raw = proj.nwsproj_path.read_text(encoding='utf-8')
            ok &= rec('保存后 .nwsproj 真的写了「对话图片=off」',
                      '对话图片=off' in raw,
                      next((ln for ln in raw.splitlines() if '对话图片' in ln), ''))

        # ── 中栏：.txt 字符画要用等宽文本，不是 ft.Image ──
        # [EN] ── Center column: .txt character art must use monospaced text, not ft.Image ──
        proj.image_mode = 'ascii'
        app._activate_project(proj)
        app.show_main_screen()
        page.update()
        await asyncio.sleep(1.0)
        out: list = []
        for c in page.controls:
            walk(c, out)
        images = [c for c in out if isinstance(c, ft.Image)]
        texts = [str(getattr(c, 'value', '')) for c in out
                 if isinstance(c, ft.Text)]
        joined = '\n'.join(texts)
        ok &= rec('字符画用等宽字体渲染成文本（不是 ft.Image）',
                  '[##]' in joined and not any(
                      str(getattr(i, 'src', '')).endswith('.txt') for i in images),
                  f'Image 控件 {len(images)} 个')
        ok &= rec('字符画旁边的图说也在（地点）', '城东渡口' in joined)
        await shot('image_mode_main.png')

        report['ok'] = bool(ok)
    except Exception:
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        if tmp is not None:
            VU.safe_rmtree(tmp, ignore_errors=True)
        (OUT / 'image_mode_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        passed = sum(1 for s in report['steps'] if s['ok'])
        failed = [s['name'] for s in report['steps'] if not s['ok']]
        print(f'\n{"=" * 62}\n通过 {passed}/{len(report["steps"])} 项'
              + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)),
              flush=True)
        if report.get('fatal'):
            print('\n⚠ 验证中途崩溃：\n' + report['fatal'][-1200:], flush=True)
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be applied **before closing the window**: `page.window.destroy()` raises
        # [EN] CancelledError
        # [EN] cancelling this coroutine, so the `exit_now(...)` on the line after `await shutdown(page)`
        # [EN] **never executes** (exit code is always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


if __name__ == '__main__':
    print('对话图片四种方式 · 验证', flush=True)
    tmpdir = Path(tempfile.mkdtemp(prefix='nws_imgmode_logic_'))
    logic_ok = True
    head('1. 项目文件 / 四种模式 / 上下文 / 回退链')
    try:
        logic_ok = test_logic(tmpdir)
    except Exception:
        report['fatal'] = traceback.format_exc()
        print(report['fatal'][-1200:])
        logic_ok = False
    finally:
        VU.safe_rmtree(tmpdir, ignore_errors=True)
    report['logic_ok'] = bool(logic_ok)
    if '--logic-only' in sys.argv:
        report['ok'] = bool(logic_ok)
        (OUT / 'image_mode_report_logic.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        passed = sum(1 for s in report['steps'] if s['ok'])
        print(f'\n{"=" * 62}\n（仅逻辑）通过 {passed}/{len(report["steps"])} 项')
        sys.exit(0 if logic_ok else 2)
    head('2. 真机 GUI（书斋下拉 + 保存落盘 + 中栏字符画）')
    ft.run(test_gui)
