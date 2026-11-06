# -*- coding: utf-8 -*-
"""验证：**「推演结果」对话框 —— 导出按钮改版**（2026-10-29）。

用户原话：

    「我希望修改导出按钮为推演结果按钮 然后进入之后界面改成 多个Tab
      分别是原始稿 最终改写稿 原始稿加细节 运行报告
      写作指导(再分成左侧2个Tab，分别是LLM润色稿和写作指导）
      其中最后3个 打开默认是空的或者不更新（如果之前生成过一次）
      要手动点一个按钮来生成或更新（是一个按钮 如果没有内容 按钮上的字是生成，
      如果有内容 按钮上的字是更新）点了之后才会调用LLM去操作
      前三者因为不需要调用LLM 所以应该是打开对话框就有的
      然后现在的导出内容放到这个对话框的右上角一个单独的导出按钮里
      按了之后是目前的内容去掉 3 结束时自动导出这部分
      目前的3 结束时自动导出这部分 在新对话框右上角加一个单独的设置按钮
      叫做自动导出设置」

## 四条用户划的分界线（判据各钉一条）

  1. **零成本三档打开就有**：`KIND_USES_LLM` 里 raw/novel/reference 本来就是
     False —— 预览走 `NV.write_raw_manuscript` / `NV.write_manuscript`（直装订），
     **绝不**走 MuMu 重写 / 成书复查（那是要花 token 的导出增强档，预览偷偷烧钱
     是最不能接受的）；
  2. **要花 token 的三份默认不跑**：打开只**读**盘上的旧文件（报告/指导走
     `run_summary_path` / `outline_path` 固定入口，润色稿走 `latest_polished`），
     没有就是空的 —— 点「生成/更新」才调模型，按钮的字跟着有没有内容走；
  3. **导出收进右上角**：`show_export_dialog(include_auto=False)` —— 同一组
     「结束时自动导出」开关不再摆两处；
  4. **自动导出设置独立成框**：五个开关、`_auto_switch_handler` 同一条落盘路。

## 判据分层

  A **模型层（真盘）**：`NV.latest_file` / `NV.latest_polished`（空目录 → None、
    版本取最高、润色稿按 mtime 取最新）+ 零成本装订真的不调模型就出稿。
  B **接线（AST）**：按钮改名 / 五个页签 / 左侧双子页 / 默认只读 /
    生成与更新按钮 / 右上角两入口 / include_auto 闸 / 防并发 / partial 口径。

⚠ 全程在 `%TEMP%` 造真运行文件夹（复用 `verify_export.make_run`），
  **不碰** `Projects/`；`MOCK_LLM=true`，零网络。
English:
Verification: **the "Derivation Results" dialog -- the export button redesign** (2026-10-29).
Four boundaries the user drew, each pinned by a criterion group: (1) the zero-cost three drafts
are there on open -- bound via the direct NV writers, never MuMu/checkup; (2) the token-spending
three are read-only on open (fixed entries / latest_polished) and only run on an explicit
"Generate/Update" whose label follows content; (3) Export moves to the top right with
`include_auto=False`; (4) auto-export settings become their own dialog.
Layers: A model (real temp-disk runs, MOCK_LLM) / B wiring (AST).
"""
from __future__ import annotations

import inspect
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

os.environ.setdefault('MOCK_LLM', 'true')          # 零网络承诺

from export import novel_version as NV            # noqa: E402
from tools.verify_exit import finish              # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
CHECKS: list[dict] = []
REPORT: dict = {}


def ok(name: str, cond, detail='') -> bool:
    CHECKS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + ('' if cond else f'\n      → {str(detail)[:240]}'), flush=True)
    return bool(cond)


def head(txt: str) -> None:
    print(f'\n── {txt} ' + '─' * max(0, 56 - len(txt)), flush=True)


# ══════════════════════════════════════════════════════════════════════
#  A. 模型层：latest_file / latest_polished + 零成本装订
# ══════════════════════════════════════════════════════════════════════
def test_model(tmp: Path) -> None:
    from tools.verify_export import make_run

    head('A. latest_file / latest_polished（真盘）')
    run = make_run(tmp / '第1次模拟2026-01-01-00-00', days=2, with_logs=False,
                   with_image=False)

    ok('A1 空目录 → 三个模式都报 None（打开对话框 = 空页签，不是崩）',
       all(NV.latest_file(run, m) is None
           for m in (NV.MODE_RAW, NV.MODE_NOVEL, NV.MODE_REFERENCE))
       and NV.latest_polished(run) is None,
       [NV.latest_file(run, m) for m in
        (NV.MODE_RAW, NV.MODE_NOVEL, NV.MODE_REFERENCE)])

    r1 = NV.write_raw_manuscript(run)
    ok('A2 ★ 零成本装订真的出稿（`write_raw_manuscript`，不调模型）',
       r1['path'].exists() and r1['days'] == 2 and r1['chars'] > 0, r1)
    ok('A3 `latest_file` 现在读得到它',
       NV.latest_file(run, NV.MODE_RAW) == r1['path'],
       NV.latest_file(run, NV.MODE_RAW))

    r2 = NV.write_manuscript(run, mode=NV.MODE_NOVEL)
    ok('A4 ★ 最终改写稿直装订也出稿（不走 MuMu / 不复查 ⇒ 零 LLM）',
       r2['path'].exists() and r2['days'] == 2, r2)

    # 版本取**最高**：手造一份 v2，latest_file 必须指它
    v2 = run.export_dir / '原始稿_v2_第1-2天.md'
    shutil.copyfile(r1['path'], v2)
    got = NV.latest_file(run, NV.MODE_RAW)
    ok('A5 ★★ `latest_file` 取版本号最高的那份（v2 盖过 v1）',
       got == v2, f'got={got}')

    # 润色稿：两份同版（润色 / 润色2），按 mtime 取最新
    p1 = run.export_dir / '最终改写稿_v1_第1-2天_润色.md'
    p1.write_text('润色一', encoding='utf-8')
    time.sleep(0.02)
    p2 = run.export_dir / '最终改写稿_v1_第1-2天_润色2.md'
    p2.write_text('润色二', encoding='utf-8')
    got2 = NV.latest_polished(run)
    ok('A6 ★★ `latest_polished` 同版多份按 mtime 取最新',
       got2 == p2, f'got={got2}')

    from export.bundle import KINDS, KIND_USES_LLM
    ok('A7 ★★★ 零成本口径还在表里（raw/novel/reference = False；'
       'report/guide = True）—— "前三者打开就有"靠的就是这张表',
       [KIND_USES_LLM[k] for k in KINDS] == [False, False, False, True, True],
       {k: KIND_USES_LLM[k] for k in KINDS})


# ══════════════════════════════════════════════════════════════════════
#  B. 接线（AST）
# ══════════════════════════════════════════════════════════════════════
def test_wiring() -> None:
    head('B. 接线（AST）')
    import gui.app_flet as AF

    src_results = inspect.getsource(AF.NovelWorldApp.show_results_dialog)
    src_export = inspect.getsource(AF.NovelWorldApp.show_export_dialog)
    src_auto = inspect.getsource(AF.NovelWorldApp.show_auto_export_settings)
    src_all = inspect.getsource(AF.NovelWorldApp)
    # 运行页头部那一段（按钮所在）—— 找「推演结果」按钮的定义行
    btn_line = [ln for ln in src_all.split('\n') if '推演结果' in ln and 'FilledButton' in ln]

    ok('B1 ★★★ 运行页按钮改成「推演结果」且接 `show_results_dialog`',
       any('show_results_dialog' in ln for ln in btn_line)
       and '📊 推演结果' in src_all
       and '📤 导出' not in btn_line and len(btn_line) == 1,
       btn_line[:1])

    ok('B2 ★ 五个页签都在：原始稿 / 最终改写稿 / 原始稿加细节 / 运行报告 / 写作指导',
       all(lbl in src_results for lbl in
           ("t('原始稿')", "t('最终改写稿')", "t('原始稿加细节')",
            "t('运行报告')", "t('写作指导')")))

    ok('B3 ★★ 写作指导大页签里是**左侧两个子页**（LLM润色稿 / 写作指导，可切换）',
       "'LLM润色稿'" in src_results and '_pick_sub' in src_results
       and "'polish'" in src_results and "'guide'" in src_results
       and '_paint_sub' in src_results)

    ok('B4 ★★★ 零成本三档走直装订（`write_raw_manuscript` / `write_manuscript`），'
       '且预览**绝不**偷偷调 MuMu 重写 / 成书复查',
       'NV.write_raw_manuscript' in src_results
       and 'NV.write_manuscript' in src_results
       and 'write_manuscript_mumu' not in src_results
       and 'checkup_before_bind' not in src_results,
       '预览里出现 MuMu/复查 = 打开对话框就烧钱')

    ok('B5 ★★★ 要花 token 的三份**默认只读**：打开只读盘上的旧文件',
       'run.run_summary_path' in src_results and 'run.outline_path' in src_results
       and 'NV.latest_polished(run)' in src_results
       # 打开路径上不许直接调生成协程（只允许按钮经 page.run_task 进去）
       and src_results.count('page.run_task') == 1
       and 'page.run_task(_gen)' in src_results)

    ok('B6 ★★★ 按钮的字跟着内容走：没有 → 「生成」，有 → 「更新」',
       "set_btn_text(st['btn'], t('生成') if p is None else t('更新'))" in src_results,
       src_results[src_results.find('set_btn_text(st'):
                   src_results.find('set_btn_text(st') + 80])

    ok('B7 ★★ 右上角两个独立入口：导出（`include_auto=False`）+ 自动导出设置',
       'self.show_export_dialog(\n                include_auto=False)' in src_results
       and 'self.show_auto_export_settings' in src_results
       and "t('自动导出设置')" in src_results)

    ok('B8 ★★ 导出对话框支持 `include_auto`，③ 段被它闸住',
       'include_auto: bool = True' in src_export
       and 'if include_auto:' in src_export
       and "*auto_rows," in src_export)

    ok('B9 ★ 生成前查并发（`B.inflight(run)`）—— 收工自动导出在跑时不许再生成',
       'B.inflight(run)' in src_results)

    ok('B10 ★ 报告/指导按"推演还在跑"注半截稿（与导出同一口径）',
       "getattr(self, 'session', None)" in src_results
       and '_partial' in src_results)

    ok('B11 ★ 自动导出设置框复用 `_auto_switch_handler`（不另写落盘逻辑）',
       '_auto_switch_handler' in src_auto and 'KIND_AUTO_KEY' in src_auto)

    ok('B12 句柄留给验证脚本（`_results_ui`）',
       'self._results_ui' in src_results)

    ok('B13 ★★★ 对话框尺寸**从运行界面中栏反推**（宽≈中栏、高=3/4），'
       '不许写死 600×640',
       '_h_chrome' in src_results and '_v_chrome' in src_results
       and 'RUN_RIGHT_W' in src_results and 'HEADER_H' in src_results
       and '0.75' in src_results
       and 'width=DLG_W, height=640' not in src_results,
       '老写法 `width=DLG_W, height=640` 必须消失；尺寸要跟着窗口走')
    ok('B14 ★ 小窗封底：算出来的尺寸不小于 600×640（`max(..., DLG_W)` / `max(..., 640)`）',
       'max(int(_pw - _h_chrome), DLG_W)' in src_results
       and 'max(int((_ph - _v_chrome) * 0.75), 640)' in src_results)

    # ── B15/B16：2026-10-29 用户的两条观感要求 ──────────────────────
    #   ① 「运行报告和写作指导的生成按钮让他们更明显一些」
    #   ② 「写作指导的 LLM润色稿 / 写作指导 这 2 个 Tab 放到最上面，
    #      不要加圆形边框，就普通边框，要那种连起来的 Tab 按钮效果」
    src_gen = inspect.getsource(AF.mk_gen_btn)
    ok('B15 ★★★ 「生成 / 更新」用 `mk_gen_btn`（实心赭金 + 加粗 + 高 38），'
       '不再是灰扑扑的 `mk_btn(primary=False)` TextButton',
       'mk_gen_btn(t(\'生成\')' in src_results
       and 'mk_btn(t(\'生成\'), on_click=None, primary=False)' not in src_results,
       '老写法是 TextButton：纸色底 + 默认字色，和旁边说明文字分不出来')
    ok('B15b `mk_gen_btn` 本身：FilledButton + 赭金底 + 纸白字 + 加粗 + 比 BTN_H 高',
       'ft.FilledButton' in src_gen and "bgcolor=C['gold']" in src_gen
       and "color=C['paper_hi']" in src_gen
       and 'ft.FontWeight.BOLD' in src_gen
       and 'GEN_BTN_H' in src_gen and 'GEN_BTN_H = 38' in inspect.getsource(AF),
       src_gen[:80].replace('\n', ' '))
    ok('B16 ★★★ 两个子页签在**最上面**、方角、连成一条（不是左侧竖排 + 竖分隔线）',
       'ft.VerticalDivider' not in src_results
       and 'sub_btns' not in src_results
       and 'spacing=0, vertical_alignment=ft.CrossAxisAlignment.END' in src_results
       # 方角：不许出现 `border_radius=` 这个实参（注释里提到这个词没关系）
       and 'border_radius=' not in src_results
       # 相邻共用一条竖线：只有头一个补左边线
       and "left=_TAB_EDGE if k == 'polish' else None" in src_results
       # 选中的不画下边线 ⇒ 和下面稿子连成一片
       and 'bottom=None if sel else _TAB_EDGE' in src_results,
       '竖排 + `ft.VerticalDivider` = 老样子；`border_radius` 出现 = 又变圆角')
    ok('B16b 页签条右侧那条横线拉到边（`ft.Container(expand=True)` + 只画下边线）',
       'height=SUB_TAB_H - 1' in src_results
       and 'border=ft.Border(bottom=_TAB_EDGE)' in src_results)
    ok('B16c 页签仍可切换（`_pick_sub` / `_paint_sub` / `sub_pages[...].visible`）',
       '_pick_sub(key)' in src_results and '_paint_sub()' in src_results
       and "v.visible = (_sub['cur'] == k)" in src_results)
    ok('B16d ★★★ 页签条下面**直接就是内容**（整个页签页就是内容框），'
       '不再套一只带边框的方盒',
       # 内容列裸着 expand，不带 border/padding 包装
       "ft.Column(list(sub_pages.values()), spacing=0, expand=True)" in src_results
       and "border=ft.Border(left=_TAB_EDGE, right=_TAB_EDGE" not in src_results
       and "padding=ft.Padding(10, 8, 10, 8), bgcolor=C['panel']" not in src_results,
       '稿子外面多一只方盒 = 生成按钮被框在里面')


def main() -> int:
    print('「推演结果」对话框（导出按钮改版）—— 验证', flush=True)
    with tempfile.TemporaryDirectory(prefix='nws_results_dialog_') as td:
        tmp = Path(td)
        try:
            test_model(tmp)
            test_wiring()
        except Exception:                                         # noqa: BLE001
            REPORT['fatal'] = traceback.format_exc()
            ok('验证本身没有中途崩溃（有崩溃就不是全绿）', False,
               REPORT['fatal'][-300:])
    REPORT['checks'] = CHECKS
    return finish(REPORT, out_path=OUT / 'results_dialog_report.json',
                  label='推演结果断言')


if __name__ == '__main__':
    sys.exit(main())
