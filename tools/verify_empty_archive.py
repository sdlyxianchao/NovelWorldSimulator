# -*- coding: utf-8 -*-
"""验证：**存档为空（或者全被删掉）也必须能起笔** —— 关掉软件再进来也一样。

用户 2026-10-28 报的原话：

    「一个小说 如果我开卷成功了 然后我又把所有存档都删除了，我关闭软件再进去
      就无法进行推理了。按道理第一次推演不应该跟存档有关，确切的说它就应该在
      存档为空的前提下可以开始才对」

## 这是两个独立的东西被写成了一个

  · **"这本书开过卷"** —— 盘上的事实（`Projects/<书名>/` 与 `.nwsproj` 还在），
    关软件、重启、删存档都不该改变它；
  · **"这一轮跑到哪儿了"** —— 存档里的事实（`停点.json`），删了就该是"从头开始"。

  旧代码把「起　笔」的可用性写成了 `has_run = self.current_project is not None`，
  也就是**"这一次运行里有没有打开过"**。于是：
    - 刚开完卷（`current_project` 有值）→ 能起笔 ✅
    - **重启之后**（`current_project` 恒为 `None`）→ 三颗按钮一起变灰，
      小字写着「先开卷导入小说」 ❌ —— 用户明明已经开过卷了。

  更糟的是点下去也回不来：`_on_new_round` 第一句就是 `if current_project is None:
  return`，只弹一句「先开一卷」，等于让用户把书**重开一遍**。

## 修法（本判据钉的就是这三条）

  A. **判据只有一条：盘上有没有书**（`start_menu_state`，纯函数）。
     有书就能按 —— 存档在不在、这一轮跑没跑过，与"能不能起笔"无关。
  B. **记住上次打开的是哪本书**（`.ui_state/last_project.json`），启动时**接回来**
     （`_restore_last_project`），而且必须排在 `show_start_screen()` **之前** ——
     按钮的可用性是在建界面那一刻算好的，排后面等于又画一遍灰按钮。
  C. **没有"当前书"时当场给出路**（`_need_project`）：盘上只有一本就直接用它，
     多本就弹拾卷让他挑，一本都没有才说"先开卷"。

## 判据分层

  A **纯函数**：四种组合（有当前 / 有书没打开 / 多本 / 没书）+ 坏输入
  B **记录落盘**：存了能读回；书被删 / 不是书 / 文件坏了 → 当没记过；写不进去不抛
  C **接线（AST/源码）**：谁记、谁接、接在哪一步、三个入口都走 `_need_project`
  D **行为**：只有一本 → 自动用；多本 → 弹拾卷；一本没有 → 提示；空存档 → fresh

用法：.venv\\Scripts\\python.exe tools/verify_empty_archive.py
产出：assets/screenshots/empty_archive_report.json

English:
Verification: **an empty save folder (or all saves deleted) must still allow starting a round**,
including after quitting and reopening the app.
The user's report on 2026-10-28: "For a novel, if I successfully opened a volume and then deleted
all the saves, closing the app and coming back in means I cannot derive any more. Logically the
first derivation should not depend on saves; it should be able to start with an empty save folder."
Two independent things had been coded as one:
  · "this book was opened" -- a fact on disk (`Projects/<name>/` and `.nwsproj` still exist);
    quitting, restarting or deleting saves must not change it;
  · "how far this round got" -- a fact inside a save (`停点.json`); deleted means "from the start".
The old code gated "起　笔" on `has_run = self.current_project is not None`, i.e. "was a book opened
during *this* run", so a restart (where it is always None) greyed all three buttons out and said
"open a volume first", and `_on_new_round` returned immediately for the same reason.
The fix (exactly what this criterion pins):
  A. one criterion only: **are there books on disk** (`start_menu_state`, a pure function);
  B. **remember which book was open** (`.ui_state/last_project.json`) and reconnect it at startup
     (`_restore_last_project`), **before** `show_start_screen()` -- availability is computed while
     building the screen;
  C. with no current book, **give a way out on the spot** (`_need_project`): exactly one book -> use
     it; several -> open Pick-a-Volume; none -> say "open a volume first".
Layers: A pure function / B record on disk / C wiring / D behaviour.
"""
from __future__ import annotations

import inspect
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from store.project import Project, scan_projects                  # noqa: E402
from tools.verify_exit import finish                             # noqa: E402

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
    """在 `root` 下造一本**真的**书（目录 + .nwsproj），一次推演都没有。

    ⚠ 刻意用真 `Project.create_new` 而不是假的鸭子对象：这条 bug 的现场就是
      "盘上的书是真的、当前项目是 None"，用假对象测不到 `scan_projects` 那一环。
    [EN] Create a **real** book under `root` (folder + .nwsproj) with zero rounds.
    [EN] ⚠ Deliberately the real `Project.create_new` instead of a duck-typed fake: the bug's
    [EN] scene is "the book on disk is real, the current project is None", and a fake would skip
    [EN] `scan_projects`.
    """
    return Project.create_new(root, name)


# ══════════════════════════════════════════════════════════════════════
#  A. 纯函数：按钮该不该亮
# ══════════════════════════════════════════════════════════════════════
def test_menu_state() -> None:
    import gui.app_flet as AF

    head('A. 开始界面三颗按钮的可用性（纯函数）')
    s = AF.start_menu_state(has_current=True, n_books=0)
    ok('A1 已打开一本书 → 三颗全亮（on）',
       all(v == AF.START_ON for v in s.values()), s)

    s = AF.start_menu_state(has_current=False, n_books=1)
    ok('A2 ★★★ 没打开、但盘上有 1 本书 → 三颗都是 pick'
       '（用户报的正是这条：删了存档、重启后「起笔」不该变灰）',
       all(v == AF.START_PICK for v in s.values()), s)

    s = AF.start_menu_state(has_current=False, n_books=3)
    ok('A2b 多本书同样 pick（点下去让他挑一本，而不是灰掉）',
       all(v == AF.START_PICK for v in s.values()), s)

    s = AF.start_menu_state(has_current=False, n_books=0)
    ok('A3 一本书都没有 → 三颗都灰（off）—— 这才是真的"先开卷"',
       all(v == AF.START_OFF for v in s.values()), s)

    bad = [None, -3, 0, 'x', 1.0]
    hurts = []
    for v in bad:
        try:
            r = AF.start_menu_state(has_current=False, n_books=v)
            if not isinstance(r, dict) or set(r) != {'start', 'study', 'resume'}:
                hurts.append((v, r))
        except Exception as e:                                    # noqa: BLE001
            hurts.append((v, repr(e)))
    ok('A4 坏输入（None / 负数 / 字符串 / 浮点）不抛、且仍给出三档',
       not hurts, hurts)

    s = AF.start_menu_state(has_current=True, n_books=0)
    ok('A5 有当前书时**不看**盘上有没有书（删光了也照样亮 —— 手里这本就是能跑的）',
       all(v == AF.START_ON for v in s.values()), s)

    # ★ 2026-10-28 晚（用户：「如果已开卷，在开始界面就需要显示项目名字」）：
    #   名字从哪来 —— 重启后 `current_project` 是 None，只靠它名字**根本不会出现**。
    #   用三个不同的哨兵对象比"是不是同一个"，比不比名字更能说明"报的是哪一本"。
    # [EN] ★ 2026-10-28 (user: "if a volume is already opened, the start screen must show the
    # [EN] project name"): where the name comes from -- after a restart `current_project` is None,
    # [EN] so relying on it alone means **no name at all**. Three distinct sentinel objects, compared
    # [EN] by identity, prove *which* book is reported.
    cur, other, last = object(), object(), object()
    name_cases = [
        ('手里这本优先', (cur, [other], last), cur),
        ('★ 重启后（current=None）报**上次打开**那本', (None, [cur, other], last), last),
        ('没有记录、盘上只有一本 → 就是它', (None, [cur], None), cur),
        ('多本且没记录 → 报不出来（这时"接着上次那本"是假话）', (None, [cur, other], None), None),
        ('一本书都没有 → 报不出来', (None, [], None), None),
    ]
    wrong = [(n, repr(r)) for n, args, want in name_cases
             for r in [AF.start_shown_project(*args)] if r is not want]
    ok('A6 ★★★ 开始界面报哪本书：手里这本 → 上次打开 → 只有一本就是它；'
       '多本无记录才报不出来',
       not wrong, wrong)

    hurts = []
    for args in ((None, None, None), (None, 'x', None),
                 (None, [None], None), (None, [], last)):
        try:
            AF.start_shown_project(*args)
        except Exception as e:                                    # noqa: BLE001
            hurts.append((args, repr(e)))
    ok('A7 坏输入（`projects` 是 None / 字符串 / 空列表）不抛', not hurts, hurts)


# ══════════════════════════════════════════════════════════════════════
#  B. 「上次打开的是哪本书」这条记录
# ══════════════════════════════════════════════════════════════════════
def test_last_project(tmp: Path) -> None:
    import gui.app_flet as AF

    head('B. 「上次打开的书」的落盘与读回')
    pdir = tmp / '项目'
    pdir.mkdir(parents=True, exist_ok=True)
    a = _mkbook(pdir, '书一')
    b = _mkbook(pdir, '书二')
    rec = tmp / 'ui' / 'last_project.json'

    saved = AF.save_last_project(a, path=rec)
    ok('B1 记一次能写进盘（目录会自动建出来）',
       bool(saved) and rec.is_file(), f'saved={saved} exists={rec.is_file()}')

    got = AF.load_last_project(scan_projects(pdir), path=rec)
    ok('B2 ★★ 读回来就是**同一本**（按路径比，不按名字 —— 同名不同目录的书是两本）',
       got is not None and Path(got.root) == Path(a.root),
       got and got.root)

    # ── 书被删掉（用户常规操作）→ 当"没记过"，不许跑到一本不存在的书上 ──
    rec.write_text(json.dumps({'name': b.name, 'root': str(b.root)},
                              ensure_ascii=False), encoding='utf-8')
    shutil.rmtree(b.root)
    got = AF.load_last_project(scan_projects(pdir), path=rec)
    ok('B3 ★★★ 记录里的书**已经被删** → 返回 None（重启不该指着一本没了的书）',
       got is None, got and got.root)

    # ── 目录还在，但已经不是"一本书"（没有 .nwsproj）──
    shell = tmp / '空壳'
    shell.mkdir()
    rec.write_text(json.dumps({'name': '空壳', 'root': str(shell)},
                              ensure_ascii=False), encoding='utf-8')
    got = AF.load_last_project(scan_projects(pdir), path=rec)
    ok('B4 ★★ 路径存在但**不是书**（没有 .nwsproj）→ None'
       '（光看目录存在会被空壳 / 手建文件夹骗过）',
       got is None, got and got.root)

    # ── 文件坏了 ──
    rec.write_text('{这不是 json', encoding='utf-8')
    got = AF.load_last_project(scan_projects(pdir), path=rec)
    ok('B5 记录文件坏了 → 当没记过（不抛）', got is None, got)

    # ── 写不进去：path 指一个目录 ──
    # ⚠ 这一段**故意制造一次失败**，而 `save_last_project` 会 `log_exception` ——
    #   那会把一段 traceback 打到 stderr。体检器（`verify_exit_codes`）判"崩没崩"
    #   用的正是「stderr 里有 Traceback 且退出码非 0」⇒ 会把这支判据**误判成崩溃**
    #   （实测：它报 `第 122 行 · 脚本崩了`，而 122 行是 A1，风马牛不相及）。
    #   所以这里把日志口临时换成空桩：我们测的是"返回 False、不抛"，日志不是被测对象。
    # [EN] ⚠ This block **deliberately causes a failure**, and `save_last_project` calls
    # [EN] `log_exception`, which dumps a traceback to stderr. The exit-code checker decides
    # [EN] "crashed" by "Traceback in stderr AND non-zero exit" => it would misjudge this
    # [EN] criterion as a crash. So swap the log sink for a no-op here: what is under test is
    # [EN] "returns False, does not raise"; logging is not the subject.
    _old_log = AF.log_exception
    AF.log_exception = lambda *a, **k: None
    threw = None
    try:
        res = AF.save_last_project(a, path=tmp)      # tmp 是目录 ⇒ write_text 必然失败
    except Exception as e:                                        # noqa: BLE001
        threw = repr(e)
        res = None
    finally:
        AF.log_exception = _old_log
    ok('B6 ★★ 写不进去时**返回 False、不抛**（写不了只是下次要手点拾卷，'
       '不该把启动 / 开卷弄挂）',
       threw is None and res is False, f'threw={threw} res={res}')


def _method_call_order(src: str, names: list[str]) -> dict:
    """在**方法源码里**找 `self.<name>(...)` 的调用行号（按 AST，不看注释）。

    ⚠ 为什么不能用 `src.find('show_start_screen()')`：方法里的**注释**完全可能
      提到这句话（本次修改就写了一段"必须排在 `show_start_screen()` 之前"的说明），
      字符串搜索会命中注释 ⇒ 判出一条根本没发生的顺序。这个项目已经记过
      「自查文档 vs 代码先查三样」，其中一条就是**被注释骗**。
    [EN] Line numbers of `self.<name>(...)` calls inside a method's source (by AST, not by text).
    [EN] ⚠ Why not `src.find('show_start_screen()')`: comments inside the method may well mention
    [EN] that very call (this change writes "must run before `show_start_screen()`"), and a text
    [EN] search would hit the comment and report an order that never happened.
    """
    import ast
    import textwrap
    pos: dict = {}
    try:
        tree = ast.parse(textwrap.dedent(src))
    except Exception:                                             # noqa: BLE001
        return pos
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in names:
            pos.setdefault(f.attr, node.lineno)
    return pos


# ══════════════════════════════════════════════════════════════════════
#  C. 接线（源码 / AST）
# ══════════════════════════════════════════════════════════════════════
def test_wiring() -> None:
    import gui.app_flet as AF

    head('C. 接线：谁记、谁接、接在哪一步')
    src_act = inspect.getsource(AF.NovelWorldApp._activate_project)
    ok('C1 「打开一本书」时**真的记下来**（`_activate_project` 调 `save_last_project`）',
       'save_last_project' in src_act,
       src_act[-300:])

    src_main = inspect.getsource(AF.NovelWorldApp.main)
    order = _method_call_order(src_main, ['_restore_last_project',
                                          'show_start_screen'])
    i_restore = order.get('_restore_last_project', -1)
    i_show = order.get('show_start_screen', -1)
    ok('C2 ★★★ 启动时接回上次的书，而且**排在 `show_start_screen()` 之前**'
       '（排后面等于又画一遍灰按钮 —— 可用性是建界面那一刻算好的）',
       i_restore > 0 and i_show > 0 and i_restore < i_show,
       f'restore@{i_restore} show@{i_show} (AST 行号)')

    src_restore = inspect.getsource(AF.NovelWorldApp._restore_last_project)
    ok('C3 接回的动作真的**设成当前项目**（走 `_activate_project`，'
       '不是只读一下就算了）',
       '_activate_project' in src_restore and 'load_last_project' in src_restore,
       src_restore[:300])

    ents = {'起笔': '_on_new_round', '书斋': '_on_project_settings',
            '回卷': '_on_resume_story'}
    missing = [k for k, fn in ents.items()
               if '_need_project' not in inspect.getsource(getattr(AF.NovelWorldApp, fn))]
    ok('C4 ★★★ 三个入口在"没有当前书"时都走 `_need_project`（当场给路），'
       '不再直接弹一句"先开一卷"就 return',
       not missing, missing)

    src_need = inspect.getsource(AF.NovelWorldApp._need_project)
    ok('C5 `_need_project` 三档齐全：有书直接用 / 只有一本**自动打开** / 多本弹拾卷',
       '_activate_project' in src_need and 'show_projects_dialog' in src_need
       and 'len(pool) == 1' in src_need,
       src_need[:400])

    src_start = inspect.getsource(AF.NovelWorldApp.show_start_screen)
    ok('C6 ★★★ 菜单项的可用性**不再用 `has_run`** 判（改用 `menu_state`）'
       '—— 这条是防回退的：改回 `has_run` 就意味着重启后又变灰',
       'start_menu_state(' in src_start
       and 'self._on_new_round, has_run' not in src_start
       and "menu_state['start'] != START_OFF" in src_start,
       'has_run 仍被当作起笔的开关' if 'self._on_new_round, has_run' in src_start else '')

    ok('C7 ★★ 项目名条按 `pick` 分开说（盘上有书但没打开时不能再写'
       '「尚未开卷 —— 从「开　卷」开始」，那句话会让用户以为要重开一遍）',
       "menu_state['start'] == START_PICK" in src_start
       and '已开卷 · 点' in src_start,
       '项目名条仍是单分支')

    # ★ 2026-10-28 晚（用户：「已开卷就要在开始界面显示项目名字，字号跟软件标题一样」）：
    #   C7 只守住"别再说错话"，**没守住"名字必须显示出来"** —— 而重启后
    #   `current_project` 是 None，光靠它名字根本不会出现。这三条守的就是这件事。
    # [EN] ★ 2026-10-28 (user: "with a volume opened, the start screen must show the project
    # [EN] name -- same size as the app title"): C7 only guards "don't say the wrong thing",
    # [EN] **not "the name must actually appear"** -- and after a restart `current_project` is
    # [EN] None, so relying on it alone shows no name at all. These three guard that.
    ok('C8 ★★★ 盘上有书就报得出名字：`current_project` → 上次打开的那本 → 只有一本就是它'
       '（少了后两级，重启后开始界面就没有名字）',
       'load_last_project(projects)' in src_start
       and 'shown_proj' in src_start,
       'show_start_screen 里没有取"上次那本"的退路')

    _fs = inspect.getsource(AF).split('\n')
    _title_sz = [ln for ln in _fs if '小 说 世 界 A I 模 拟' in ln]
    _name_sz = [ln for ln in _fs if "INKC['gold']" in ln and 'shown_proj.name' in ln]
    # ★ 2026-10-28 深夜（用户看了实效果改口「字太大了 改小百分之三十」）：项目名
    #   不再与标题同号，但仍**由标题字号派生**（`PROJ_NAME_FS = round(APP_TITLE_FS*0.7)`）
    #   —— 两条底线：①名字行不许出现裸数字字号；②派生式必须真从 `APP_TITLE_FS` 算出
    #   （另写 `PROJ_NAME_FS = 27` 这种死数，将来动标题它就不跟了）。
    # [EN] ★ 2026-10-28 night (user, after seeing the result: "too big, reduce by 30%"): the
    # [EN] project name is no longer title-sized, but must still be **derived from the title
    # [EN] size** -- bottom lines: (1) no bare numeric size on the name line; (2) the derived
    # [EN] constant must genuinely compute from `APP_TITLE_FS` (a hardcoded `PROJ_NAME_FS = 27`
    # [EN] would stop following once the title size changes).
    ok('C9 ★★★ 项目名字号**由标题字号派生**（`PROJ_NAME_FS` 从 `APP_TITLE_FS` 算出，'
       '名字行不写死数字）—— 先同号后缩 30%，改口径不改变"单一来源"这条底线',
       any('SZ(APP_TITLE_FS)' in ln for ln in _title_sz)
       and any('SZ(PROJ_NAME_FS)' in ln for ln in _name_sz)
       and 'PROJ_NAME_FS = round(APP_TITLE_FS * 0.7)' in '\n'.join(_fs),
       f'标题行={_title_sz[:1]} 名字行={_name_sz[:1]}')

    ok('C10 ★★ 项目名排在日志条（全局消息条 `_message_bar`）**上面**'
       '（用户点名的位置）',
       src_start.find('project_chip,') >= 0
       and src_start.find('_message_bar') > src_start.find('project_chip,'),
       '项目名条不在消息条之前')


# ══════════════════════════════════════════════════════════════════════
#  D. 行为：没有当前书时真的给得出路；空存档真的能起笔
# ══════════════════════════════════════════════════════════════════════
def _bare_app():
    """一个**不跑 `__init__`** 的实例（只测 `_need_project` 的分支，不碰界面）。"""
    import gui.app_flet as AF
    app = object.__new__(AF.NovelWorldApp)
    app.current_project = None
    app.seen = {}

    def _snack(*a, **k):
        app.seen['snack'] = (a, k)

    def _pick(*a, **k):
        app.seen['pick'] = True

    def _act(p):
        app.seen['act'] = p

    app._show_snack = _snack
    app.show_projects_dialog = _pick
    app._activate_project = _act
    return app


def test_need_project(tmp: Path) -> None:
    import gui.app_flet as AF

    head('D. 没有当前书时的三条出路')
    pdir = tmp / '项目D'
    pdir.mkdir(parents=True, exist_ok=True)
    one = _mkbook(pdir, '书一')

    old = AF.scan_projects
    try:
        AF.scan_projects = lambda d: [one]
        app = _bare_app()
        got = app._need_project('开始推演一轮')
        ok('D1 ★★★ 盘上**只有一本** → 自动打开它并继续（不逼用户去拾卷）',
           got is one and app.seen.get('act') is one,
           f'got={got and got.name} seen={sorted(app.seen)}')

        two = _mkbook(pdir, '书二')
        AF.scan_projects = lambda d: [one, two]
        app = _bare_app()
        got = app._need_project('开始推演一轮')
        ok('D2 盘上**有多本** → 弹「拾卷」让他挑，并说清"选完再…"'
           '（不许替他猜哪一本）',
           got is None and app.seen.get('pick') is True
           and 'snack' in app.seen,
           f'got={got} seen={sorted(app.seen)}')

        AF.scan_projects = lambda d: []
        app = _bare_app()
        got = app._need_project('开始推演一轮')
        ok('D3 一本都没有 → 才提示"先去开卷"（而且不弹拾卷：那是个空列表）',
           got is None and 'snack' in app.seen and 'pick' not in app.seen,
           f'got={got} seen={sorted(app.seen)}')
    finally:
        AF.scan_projects = old


def test_empty_saves(tmp: Path) -> None:
    from sim import resume as RESUME

    head('D4. 空存档 = 第一次推演（用户那句"应该能在存档为空的前提下开始"）')
    pdir = tmp / '项目E'
    pdir.mkdir(parents=True, exist_ok=True)
    p = _mkbook(pdir, '书一')

    ok('D4a 刚开卷、一次都没跑 → `list_runs()` 是空的', p.list_runs() == [],
       p.list_runs())

    idx = p.next_run_index()
    ok('D4b ★★★ 空存档下建的是「第 1 次模拟」（不是 IndexError、不是第 0 次）',
       idx == 1, idx)

    plan = RESUME.plan(p)
    ok('D4c ★★★ 空存档 → 从第 1 天从头开始（`fresh`），不是报错也不是卡住',
       str(plan.get('kind')) == 'fresh', plan)

    clock = RESUME.start_clock_of(plan)
    ok('D4d 而且起点时钟是"第 1 天 · 默认开场时刻"（不硬编一个假停点）',
       clock is None or getattr(clock, 'day', 1) == 1,
       clock)


def main() -> int:
    print('存档为空也必须能起笔（重启之后也一样）—— 验证', flush=True)
    with tempfile.TemporaryDirectory(prefix='nws_empty_archive_') as td:
        tmp = Path(td)
        try:
            test_menu_state()
            test_last_project(tmp)
            test_wiring()
            test_need_project(tmp)
            test_empty_saves(tmp)
        except Exception:                                         # noqa: BLE001
            REPORT['fatal'] = traceback.format_exc()
            ok('验证本身没有中途崩溃（有崩溃就不是全绿）', False,
               REPORT['fatal'][-300:])
    REPORT['checks'] = CHECKS
    return finish(REPORT, out_path=OUT / 'empty_archive_report.json',
                  label='空存档起笔断言')


if __name__ == '__main__':
    sys.exit(main())
