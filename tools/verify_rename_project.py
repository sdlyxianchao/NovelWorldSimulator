# -*- coding: utf-8 -*-
"""验证：**书斋里可以改项目的显示名 —— 文件夹不动，相关引用跟着走**。

用户 2026-10-29 的原话：

    「我想可以在书斋 就是当前项目设置里修改项目的名字 并且修改相关引用
      但是不改文件夹名字」

## 为什么"只改名字"也要立判据

项目的名字活在**三处**，动错一处就是真事故：

  1. `.nwsproj` 里的 `名称=` —— **事实来源**（`from_nwsproj` 读它）；
  2. 项目文件自己的文件名（`<safe_name(名称)>.nwsproj`）—— **最危险的一处**：
     改名后若不删旧文件，`scan_projects`（`rglob('*.nwsproj')`）会把同一个
     文件夹扫成**两本书**（旧名的、新名的），拾卷里凭空多一本，用户往哪本
     写设定都是赌运气；
  3. 文件夹名（`root`）—— **用户点名不许动**：存档、设定集、导出稿全挂在
     文件夹上，搬文件夹才是会丢东西的那个操作。

## 判据分层

  A **模型层（真盘）**：`Project.rename()` —— 改名成功 / 旧文件清理 /
    扫描不重复 / 文件夹与内容原封不动 / 空名拒绝 / 撞名拒绝（含
    `safe_name` 等价的变体）/ 同名空操作 / 写失败回退内存名。
  B **接线（AST）**：书斋建出了名字框、排在第 0 页；`save()` 里改名
    **最先**处理且失败就中止（不许"其他设置存了、名字没存"的半拉子）；
    成功后日志名与「上次打开的书」跟着走；窗口标题刷新。

⚠ 全程在 `%TEMP%` 里造真项目，**不碰** `Projects/`。书名一律用
  「书一/书二」这类中性名（真实作品专名不许出现在判据夹具里）。

English:
Verification: **the display name can be changed in the Study -- the folder stays put, references
follow** (user, 2026-10-29). The name lives in three places, and getting any of them wrong is a
real accident: the `.nwsproj` `名称=` (source of truth), the project file's own filename (most
dangerous: leaving the old file behind makes `scan_projects` see TWO books in one folder), and
the folder name (the user explicitly forbids touching it -- saves/settings/exports all hang off
the folder). Layers: A model (real disk: success, old-file cleanup, no duplicate scan, folder
untouched, empty/collision refusals incl. `safe_name` equivalents, no-op, write-failure revert);
B wiring (AST: name box on tab 0, rename handled first in `save()` and aborts on failure, log
and last-project records follow, window title refreshes).
"""
from __future__ import annotations

import inspect
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from store.project import Project, scan_projects                  # noqa: E402
from tools.verify_exit import finish                              # noqa: E402

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


def _mkbook(root: Path, name: str) -> Project:
    return Project.create_new(root, name)


def _setup(tmp: Path) -> tuple[Path, Project, Project, Project]:
    """临时项目根 + 三本书（书一 / 书二 / 书_二），书一里放点内容。

    ⚠ 第三本故意叫「书_二」：`safe_name('书/二') == '书_二'` ——
      A9 那条"等价撞名"要有这个对象才测得到。
    [EN] A third book is deliberately named 「书_二」 because
    [EN] `safe_name('书/二') == '书_二'` -- the equivalence-collision test needs it.
    """
    pdir = tmp / '项目'
    pdir.mkdir(parents=True, exist_ok=True)
    p1 = _mkbook(pdir, '书一')
    p2 = _mkbook(pdir, '书二')
    p3 = _mkbook(pdir, '书_二')
    # 给书一放"真东西"：一轮存档 + 设定集里一个文件 —— 改名后必须原封不动
    run = p1.root / '第1次模拟2026-10-29-00-00'
    run.mkdir(parents=True, exist_ok=True)
    (run / '当天故事.md').write_text('第 1 天', encoding='utf-8')
    (p1.settings_dir / '世界观.md').write_text('设定正文', encoding='utf-8')
    return pdir, p1, p2, p3


# ══════════════════════════════════════════════════════════════════════
#  A. 模型层：Project.rename()
# ══════════════════════════════════════════════════════════════════════
def test_rename(tmp: Path) -> None:
    head('A. Project.rename() —— 改显示名，文件夹不动（真盘）')
    pdir, p1, p2, p_dup = _setup(tmp)
    root_before = p1.root
    run_before = sorted(str(x.relative_to(p1.root))
                        for x in p1.root.rglob('*') if x.is_file())

    ok_r, why_r = p1.rename('夜航书', other_projects=[p2, p_dup])
    ok('A1 ★★★ 改名成功（返回 True、说明为空）', ok_r and why_r == '',
       f'ok={ok_r} why={why_r!r}')
    ok('A2 ★★★ 文件夹一个字没动（用户点名"不改文件夹名字"）',
       p1.root == root_before and p1.root.name == '书一',
       f'root={p1.root}')

    ok('A3 ★★★ 旧的项目文件已删（否则 scan_projects 会扫出两本"同一本书"）',
       not (root_before / '书一.nwsproj').exists()
       and (root_before / '夜航书.nwsproj').exists(),
       sorted(x.name for x in root_before.glob('*.nwsproj')))

    pool = scan_projects(pdir)
    names = sorted(p.name for p in pool)
    ok('A4 ★★★ 扫描结果不重复、且是新名（书一已不在）',
       '书一' not in names and '夜航书' in names and '书二' in names
       and '书_二' in names and len([n for n in names if n == '夜航书']) == 1,
       names)
    got = next(p for p in pool if p.root == root_before)
    ok('A5 读回来的就是改名后的那份（`from_nwsproj` 走 `名称=`）',
       got.name == '夜航书' and got.root == root_before,
       [(p.name, p.root) for p in pool])

    files_after = sorted(str(x.relative_to(p1.root))
                         for x in p1.root.rglob('*') if x.is_file())
    ok('A6 ★★★ 存档、设定集一个不少（只是多了新 .nwsproj、少了旧 .nwsproj）',
       [f for f in files_after if not f.endswith('.nwsproj')]
       == [f for f in run_before if not f.endswith('.nwsproj')],
       f'before={run_before} after={files_after}')

    ok_r2, why2 = p1.rename('', other_projects=[p2, p_dup])
    ok('A7 空名拒绝、名字不变', not ok_r2 and p1.name == '夜航书',
       f'ok={ok_r2} name={p1.name}')

    ok_r3, why3 = p1.rename('书二', other_projects=[p2, p_dup])
    ok('A8 ★ 撞名拒绝（拾卷里已经有这本了）', not ok_r3 and p1.name == '夜航书',
       f'ok={ok_r3} why={why3!r} name={p1.name}')

    # 「书/二」落盘 = 「书_二」（safe_name 把 / 换成 _）—— 那本书已经存在，
    # 显示名不同、落盘同一个文件名，放行就是内容互相覆盖。
    # [EN] 「书/二」 lands as 「书_二」 on disk (safe_name turns / into _) --
    # [EN] that book already exists; different display name, same disk filename.
    ok_r4, why4 = p1.rename('书/二', other_projects=[p2, p_dup])
    ok('A9 `safe_name` 等价的撞名也拒绝（落盘是同一个文件名，内容会互相覆盖）',
       not ok_r4 and p1.name == '夜航书', f'ok={ok_r4} why={why4!r} name={p1.name}')

    ok_r5, why5 = p1.rename('夜航书', other_projects=[p2, p_dup])
    ok('A10 同名 = 空操作，按成功处理（界面不必为"没改"报错）',
       ok_r5 and why5 == '', f'ok={ok_r5} why={why5!r}')

    # 写失败：内存名必须回退（旧文件原封不动）—— 不能"内存改了盘没改"
    p3 = _mkbook(tmp / '项目F', '书三')
    orig = p3.write_nwsproj

    def _boom():
        raise OSError('模拟写失败')
    p3.write_nwsproj = _boom
    ok_r6, why6 = p3.rename('书三改', other_projects=[])
    p3.write_nwsproj = orig
    ok('A11 ★★★ 写项目文件失败 → 返回失败、内存名回退（不出现"内存新盘上旧"）',
       not ok_r6 and p3.name == '书三',
       f'ok={ok_r6} name={p3.name} why={why6!r}')
    ok('A12 失败后盘上还是原来的那份（书三.nwsproj 还在）',
       (p3.root / '书三.nwsproj').exists(),
       sorted(x.name for x in p3.root.glob('*.nwsproj')))


# ══════════════════════════════════════════════════════════════════════
#  B. 接线（AST）：书斋把名字框建出来、save() 先改名后存别的
# ══════════════════════════════════════════════════════════════════════
def test_wiring() -> None:
    head('B. 书斋接线（AST）')
    import gui.app_flet as AF
    src = inspect.getsource(AF.NovelWorldApp.show_project_settings)
    src_save = src[src.find('def save('):]

    ok('B1 名字框建出来了（`mk_field(t("项目名称")…)`，初值就是当前名）',
       'name_field = mk_field(t("项目名称"), proj.name' in src, src[:0])
    ok('B2 ★ 名字框排在第 0 页（类型风格）里、故事类型前面',
       'name_field, genre_dropdown' in src,
       src[src.find('(t("类型风格")'):src.find('(t("类型风格")') + 120])
    ok('B3 ★★★ save() 里改名**最先**处理（在其他字段读取之前）',
       0 <= src_save.find('proj.rename(') < src_save.find("img_dd"),
       f'rename@{src_save.find("proj.rename(")} img_dd@{src_save.find("img_dd")}')
    ok('B4 ★★★ 改名失败 → 整次保存中止（不许"其他设置存了、名字没存"）',
       'if not ok_r:' in src_save
       and src_save.find('return') < src_save.find("mode = field_value(img_dd)"),
       src_save[:300])
    ok('B5 ★ 改名成功后相关引用跟着走：日志名 + 「上次打开的书」记录',
       'set_project_log(new_name)' in src_save and 'save_last_project(proj)' in src_save)
    ok('B6 窗口标题在保存收尾时刷新（改名后任务栏立刻对上）',
       src_save.find('self._sync_window_title()') > src_save.find('self._after_settings_closed()'),
       f"sync@{src_save.find('self._sync_window_title()')} "
       f"after@{src_save.find('self._after_settings_closed()')}")


def main() -> int:
    print('书斋改项目名（文件夹不动，引用跟着走）—— 验证', flush=True)
    with tempfile.TemporaryDirectory(prefix='nws_rename_project_') as td:
        tmp = Path(td)
        try:
            test_rename(tmp)
            test_wiring()
        except Exception:                                         # noqa: BLE001
            REPORT['fatal'] = traceback.format_exc()
            ok('验证本身没有中途崩溃（有崩溃就不是全绿）', False,
               REPORT['fatal'][-300:])
    REPORT['checks'] = CHECKS
    return finish(REPORT, out_path=OUT / 'rename_project_report.json',
                  label='项目改名断言')


if __name__ == '__main__':
    sys.exit(main())
