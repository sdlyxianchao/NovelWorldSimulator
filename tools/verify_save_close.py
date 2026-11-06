# -*- coding: utf-8 -*-
"""判据：「剧组 Agents / AI模型配置」的编辑框**保存后要关两层**（2026-10-14 用户）。

用户原话：
  「天问 剧组Agents 的Agent编辑 点了保存应该退出当前对话框」
  「AI模型配置 加了新模型 点了保存字后也应该退出当前对话框」

**问题在哪**：编辑框是**叠**在天问/书斋设置对话框之上的（共 2 层）。
`pop_dialog()` 每次只弹最上面那层，所以原本只 pop 一次 = 只关编辑框，
设置对话框**还在屏幕上**，用户感觉"没退出"。修法是 `_save` 末尾 pop **两次**。

**判据**：用真机 + 夹具，模拟两条路径（`_agent_editor` / `_model_editor`），
保存后量 `VU.open_dialogs(page)` 的**层数**，期望 **0**（两层都关了）。
[EN] Criteria: "the Crew Agents / AI model config editor dialog should close BOTH layers on Save"
[EN] (2026-10-14 user). See the bug notes above. The check measures `VU.open_dialogs(page)` count
[EN] after clicking Save; expected **0** (both layers closed).

★ 判据纪律（working memory 第十六节）：期望写**绝对字面量** 0，不 import 产品的常量。
  [EN] Discipline: expectations are absolute literals (0), never product constants.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))
# ★★★ 2026-10-22：**`gui/` 也要进 sys.path** —— `_render` 里写的是 `import app_flet as AF`
#   （裸模块名，不是 `gui.app_flet`），而 `gui/` 不在搜索路径上 ⇒ 一进 `_render` 就
#   `ModuleNotFoundError`，整段真机一条都没跑。更糟的是收尾把 `total == 0` 打印成
#   "全部通过"（0 条断言、0 条失败），于是这条判据长期是**假绿**。
# [EN] ★★★ 2026-10-22: **`gui/` must be on `sys.path`** -- `_render` does `import app_flet as AF`
# [EN] (bare module name, not `gui.app_flet`), and `gui/` was not searched, so `_render` died with
# [EN] ModuleNotFoundError and not a single real-device assertion ran. Worse, the summary printed
# [EN] "all passed" for `total == 0`. This criterion was silently green the whole time.
sys.path.insert(0, str(APP / 'gui'))

import flet as ft                                      # noqa: E402

import verify_ui_common as VU                          # noqa: E402
# ★ 2026-10-22：判据造的数据必须只写进临时登记表（`MODELS.use_path`），不许碰用户真实文件。
# [EN] Data a criterion creates must go into a temp registry only (`MODELS.use_path`).
from llm import models as MODELS                        # noqa: E402
from crew import catalog as CAT                         # noqa: E402


# ══════════════════════════════════════════════════════════
#  B 节：真机 —— 保存后 `open_dialogs` 层数
# [EN] Section B: real machine -- `open_dialogs` count after clicking Save
# ══════════════════════════════════════════════════════════


def _btn_label(c) -> str:
    """按钮上显示的那行字。**Flet 1.0 里不在 `.text` 上**，而在 `.content` 那个 `Text` 里。

    ★★★ 2026-10-22：这条判据原来写的是 `isinstance(c, ft.ElevatedButton) and c.text == '保存'`，
      而产品从 `mk_btn()` 造出来的是 `ft.FilledButton(content=ft.Text(label))` ——
      控件类型和文字位置**两处都不对**，于是"保存"按钮永远找不到，B1/B2/B5 全部走
      "没找到 ⇒ 算红"那条分支。判据不是没本事，是它在找一个不存在的形状。
    [EN] The text shown on a button. **In Flet 1.0 it is not on `.text`** but on the `Text` inside
    [EN] `.content`. The old code checked `isinstance(c, ft.ElevatedButton) and c.text == '保存'`,
    [EN] while the product builds `ft.FilledButton(content=ft.Text(label))` -- both the type and the
    [EN] text location were wrong, so the button was never found.
    """
    txt = getattr(c, 'text', None)
    if txt:
        return str(txt)
    inner = getattr(c, 'content', None)
    val = getattr(inner, 'value', None)
    return str(val) if val else ''


def _find_btn(node, label: str):
    """在控件树里找"写着 `label` 的按钮"。认三种按钮类型（产品现在用 FilledButton）。"""
    # ⚠ 2026-10-22：**Flet 1.0 里没有 `ft.ElevatedButton`**（写它会在属性查找时直接抛
    #   `AttributeError`）。而且不能"写死这几个类名"——类名一变，判据就崩在执行途中，
    #   收尾还以为自己跑完了。这里按**名字**收集现有的按钮类，缺了就只是少认一种。
    # [EN] ⚠ 2026-10-22: **Flet 1.0 has no `ft.ElevatedButton`** (referencing it raises
    # [EN] AttributeError immediately). And hard-coding the class names is fragile: when a name
    # [EN] disappears the criterion crashes mid-run while the summary thinks it finished. Collect
    # [EN] the button classes **by name**, so a missing one merely narrows the search.
    kinds = tuple(getattr(ft, n) for n in
                  ("FilledButton", "TextButton", "ElevatedButton", "OutlinedButton")
                  if hasattr(ft, n))
    for c in VU.walk(node):
        if isinstance(c, kinds) and _btn_label(c) == label:
            return c
    return None




def _real_dialogs(page) -> list:
    """**真对话框**（去掉 SnackBar）—— "保存后该关几层"只能按这个数。

    ★★★ 2026-10-22 实测的坑：`_save` 在关对话框之前会
      `_post_message(..., snack=True)` → `page.show_dialog(ft.SnackBar(...))`，
      而 **SnackBar 也是 DialogControl，会压进同一个栈**。于是：
        · 改之前（"连 pop 两次"）：剩下的是**设置对话框**（用户说"点了保存对话框还在"）；
        · 改之后（按目标关到 0 层）：剩下的是**提示条**「已保存」。
      两者都是"1 层" —— 拿 `len(open_dialogs())` 判，**改前改后一模一样**，
      判据分辨不出"关对了"还是"关错了"。所以必须只数真对话框。

        English:
    **Real dialogs** (SnackBars excluded) -- the only thing "how many layers should close" may
    count. ★★★ Measured 2026-10-22: `_save` calls `_post_message(..., snack=True)` ->
    `show_dialog(ft.SnackBar(...))` **before** closing dialogs, and a SnackBar is a DialogControl
    that joins the same stack. Before the fix the leftover was the **settings dialog** (the user's
    "I hit Save and it is still there"); after the fix the leftover is the **toast**. Both measure
    "1 layer", so counting `open_dialogs()` cannot tell "closed correctly" from "closed wrongly".
    """
    return [d for d in VU.open_dialogs(page) if not isinstance(d, ft.SnackBar)]


PASS = 0
FAIL = 0
#: `_render` **跑到了最后一行**才置 True（见 `main()` 里那段说明）。
# [EN] Set True only when `_render` **reaches its last line** (see the note in `main()`).
DONE = False
def ok(label: str, passed: bool, why: str = '') -> bool:
    global PASS, FAIL
    if passed:
        PASS += 1
        print(f'  [OK]   {label}' + (f'  — {why}' if why else ''))
    else:
        FAIL += 1
        print(f'  [FAIL] {label}' + (f'  — {why}' if why else ''))
    return passed


def _verdict() -> tuple[int, list[str]]:
    """结论与退出码的**唯一出口**（`_render` 收尾与 `main` 都走它，不各写一份）。

    ★ "一条断言都没跑"和"中途抛了异常"都**不算通过**：这支判据曾经因为
      `import app_flet` 失败而一条都没跑，收尾照样打印"0 断言 0 失败 → 全部通过"，
      长期假绿。与"脚本崩了 ≠ 判据抓到了"是同一条规矩。

    为什么收尾要在 `_render` 里就出结论
    ------------------------------------
    `_render` 返回只是"这个会话的协程跑完了"，**窗口还开着** ⇒ `ft.run()` 永远不返回，
    `main()` 里那段结论**永远走不到**。2026-10-30 实测：`DONE = True` 之后卡了 90 秒
    一动不动、没有任何输出，只能从外面杀掉 —— 于是这支判据在本机一直表现为
    "跑到一半被 SIGTERM"。⇒ 结论在 `_render` 里打印并 `shutdown(page, code=...)`。

        English:
    The **single exit point** for the verdict and the exit code (used by both `_render`'s tail and
    `main()`, never duplicated).
        ★ "zero assertions" and "raised halfway" are both **not a pass**: this criterion once ran zero
          assertions (import failure) and still printed "0 assertions, 0 failures => all passed".
        Why the verdict must be produced inside `_render`
        ------------------------------------
        Returning from `_render` only finishes *this session's coroutine*; the **window is still
        open**, so `ft.run()` never returns and the summary in `main()` is unreachable. Measured
        2026-10-30: it sat for 90 s after `DONE = True` with no output and had to be killed from
        outside -- so on this machine the criterion always looked like "killed by SIGTERM".
        => print the verdict inside `_render` and `shutdown(page, code=...)`.
    """
    total = PASS + FAIL
    if total == 0 or not DONE:
        return 2, ['',
                   '  ✗ 没跑完（一条断言都没跑，或中途抛了异常）→ 不算通过'
                   f'  [断言 {total} 条，跑完标记 {DONE}]']
    return (0 if FAIL == 0 else 1), [
        '',
        f'  共 {total} 项断言，失败 {FAIL} 项 → {"全部通过" if FAIL == 0 else "有红"}']


async def _render(page: ft.Page):
    """起真机 + 夹具 + 两条保存路径各跑一次。"""
    import app_flet as AF
    from store.project import Project    # ⚠ 2026-10-22：`store/__init__.py` 不导出 Project
    from config import CFG

    app = AF.NovelWorldApp()
    app.main(page)                                    # 同步调用（working memory 第十五节）
    await asyncio.sleep(1.8)

    # ── B1：剧组 Agents 编辑框保存后**关两层** ──
    print('\n── B1. 剧组 Agents 编辑框：保存后关两层 ──')
    # 先叠一层"天问/书斋设置"，再叠 Agent 编辑（模拟真实路径：设置 → 剧组 Agents → 编辑）
    # [EN] First stack "Tianji/书斋 settings", then the agent editor (mirrors the real path:
    # [EN] settings -> Crew Agents -> edit).
    app.show_global_settings()
    await asyncio.sleep(0.9)
    before = len(VU.open_dialogs(page))
    # ⚠ 2026-10-22：这里原来判 `before >= 2`，可**编辑框此刻还没打开** ——
    #   设置对话框本身就只叠 1 层，于是这条恒红。它想证明的是"设置开着"，
    #   那就写"设置开着"；"两层"由下面 `mid >= 2` 那条负责。
    # [EN] ⚠ 2026-10-22: this used to require `before >= 2`, but the **editor is not open yet** --
    # [EN] the settings dialog itself is one layer, so the check was permanently red. It wants to
    # [EN] prove "settings is open"; "two layers" is what `mid >= 2` below is for.
    ok('B1_pre 设置对话框已经开了一层（编辑框还没叠）',
       before >= 1, f'实测 {before} 层')

    # 找一个内置 spec 来编辑（不依赖具体 slug —— 内置列表里第一个）
    # ⚠ 2026-10-22：`all_specs()` / `load()` 都已经不在 `crew.catalog` 里了，
    #   现在是 `effective(project=None)`（软件层那 17+ 条）。
    # [EN] ⚠ 2026-10-22: `all_specs()` / `load()` are gone from `crew.catalog`; it is now
    # [EN] `effective(project=None)` (the 17+ software-layer entries).
    specs = CAT.effective(project=None)
    if not specs:
        ok('B1 保存后 0 层（关两层）', False, 'CAT 里一个 spec 都没有')
    else:
        spec = specs[0]
        app._agent_editor(spec, project=None, allow_new=False,
                          on_done=lambda: None)
        await asyncio.sleep(0.7)
        mid = len(VU.open_dialogs(page))
        ok('B1_pre 编辑框叠上后确实是 ≥2 层',
           mid >= 2, f'实测 {mid} 层')
        # 找"保存"按钮点一下
        top = (VU.open_dialogs(page) or [page])[-1]
        save_btn = _find_btn(top, '保存')
        if save_btn is None:
            ok('B1_pre 找得到「保存」按钮', False,
               '（没找到 ⇒ 这一节跑不了，B1 算红）')
        else:
            save_btn.on_click(None)
            await asyncio.sleep(0.9)
            after = len(_real_dialogs(page))
            ok('B1 ★★★ 保存后**0 层真对话框**（编辑框 + 设置对话框都关了，'
               '用户原话「退出当前对话框」）',
               after == 0, f'实测 {after} 层真对话框'
               f'（另有 {len(VU.open_dialogs(page)) - after} 条提示条）')
            # ★★★ 2026-10-22：**"关得干净"不能是"把提示条也关掉"** ——
            #   用户要知道这一下保存成功了。所以单列一条：保存后必须**还看得到**
            #   「已保存」那条提示。否则有人为了把层数压到 0 顺手把 snack 也关了，
            #   B1 照样绿，而用户失去了反馈。
            # [EN] ★★★ 2026-10-22: **"closes cleanly" must not mean "kills the toast"** -- the user
            # [EN] needs to know the save worked. A separate assertion: the "saved" toast must still
            # [EN] be on screen. Otherwise someone could silence the snack to force the count to 0,
            # [EN] B1 would stay green, and the user would lose the feedback.
            _toast = [d for d in VU.open_dialogs(page) if isinstance(d, ft.SnackBar)]
            ok('B1b ★★ 而且**提示条还在**（"已保存"要看得见 —— 不许为了关干净把反馈也关掉）',
               bool(_toast), f'{len(_toast)} 条')

    # ── B2：AI 模型配置新建模型保存后**关两层** ──
    print('\n── B2. AI 模型配置新建模型：保存后关两层 ──')
    # 先把栈清干净（B1 万一没收完，这里从 0 开始更可控）
    # [EN] Clear the stack first (in case B1 left residue; start from 0 for determinism).
    while VU.open_dialogs(page):
        page.pop_dialog()
        await asyncio.sleep(0.2)
    app.show_global_settings()
    await asyncio.sleep(0.9)
    before2 = len(VU.open_dialogs(page))
    ok('B2_pre 设置对话框叠上后 1 层', before2 == 1, f'实测 {before2} 层')

    # ★★★ 2026-10-22 **这场事故的根因**：
    #   这一段原来直接把 `{'entries': []}` 交给产品，产品拿它当"当前登记表"，
    #   点保存时**以空表 + 新条目写回** ⇒ 用户真实的 `llm_models.json`（4 条模型，
    #   其中两条的密钥**只存在于那个文件里**）被覆盖成只剩一条 `probe-model-x`。
    #   ⇒ 两条硬规矩，缺一不可：
    #     ① 用 `MODELS.use_path()` 把登记表临时换到临时目录；
    #     ② `with` 必须**包住"打开 + 点保存"整段** —— 只包打开那一下是不够的，
    #        因为写盘发生在保存回调里，那时 with 早已退出、路径又指回真实文件。
    #        （第一版就是这么写的，等于什么都没隔离。）
    # [EN] ★★★ 2026-10-22 **the root cause of the incident**: this section handed
    #   `{'entries': []}` to the product, which treated it as "the current registry" and wrote back
    #   "empty table + new entry" on Save => the user's real `llm_models.json` (4 models, two of whose
    #   keys existed **only in that file**) became a single `probe-model-x`.
    #   => Two hard rules, both required: ① swap the registry with `MODELS.use_path()`;
    #   ② the `with` must **wrap "open + click Save" as a whole** -- wrapping only the open call is
    #   useless, because the write happens inside the Save callback, when `with` has already exited
    #   and the path points back at the real file. (The first version did exactly that.)
    # ⚠ 这里必须用**工程根目录下的那个文件**，不能用 `MODELS.path()`：
    #   `verify_ui_common` 一 import 就把登记表钉到临时副本了（默认保护），
    #   拿 `MODELS.path()` 会拿到副本 —— 那条判据就变成"副本没动"，等于自我安慰。
    #   要判的就是**用户真正的那个文件**有没有被动过。
    # [EN] Must be the file **in the project root**, not `MODELS.path()`: importing
    #   `verify_ui_common` already pins the registry to a temp copy (protection by default), so
    #   `MODELS.path()` would be the copy -- that assertion would then only say "the copy is
    #   untouched", which is self-comfort. The point is whether **the user's real file** changed.
    _real_models = APP / 'llm_models.json'
    _real_hash = (hashlib.sha256(_real_models.read_bytes()).hexdigest()
                  if _real_models.is_file() else '')
    # ⚠ `tmp` 是 `main()` 里的局部变量，`_render` **看不到它**（第一版写成 `tmp / ...`
    #   直接 `NameError`，整段 B2 崩掉）。这里自己开一个临时目录。
    # [EN] `tmp` belongs to `main()` and is **not visible** in `_render` (the first version wrote
    #   `tmp / ...` and raised NameError, killing all of B2). Open a temp dir here.
    _tmp_dir = Path(tempfile.mkdtemp(prefix='nws_close_models_'))
    _tmp_models = _tmp_dir / 'probe_llm_models.json'

    with MODELS.use_path(_tmp_models):
        app._model_editor(page, None, {'entries': []}, on_done=lambda: None,
                          prefill_name='probe-model-x')
        await asyncio.sleep(0.7)
        mid2 = len(VU.open_dialogs(page))
        ok('B2_pre 模型编辑框叠上后 ≥2 层', mid2 >= 2, f'实测 {mid2} 层')

        top2 = (VU.open_dialogs(page) or [page])[-1]
        save_btn2 = _find_btn(top2, '保存')
        if save_btn2 is None:
            ok('B2 保存后 0 层（关两层）', False,
               '（没找到「保存」按钮 ⇒ 这一节跑不了，B2 算红）')
        else:
            save_btn2.on_click(None)
            await asyncio.sleep(0.9)
            after2 = len(_real_dialogs(page))
            ok('B2 ★★★ 保存后**0 层**（模型编辑 + 设置对话框都关了，'
               '用户原话「加了新模型 点了保存字后也应该退出当前对话框」）',
               after2 == 0, f'实测 {after2} 层')

    # ★★★ 2026-10-22：**光判"关了几层"不够，还要判"有没有写到用户那边去"**。
    #   上一版只判层数 ⇒ 保存把真实登记表覆盖了也照样全绿（事故当天它就是这么绿的）。
    # [EN] ★★★ 2026-10-22: **counting closed layers is not enough; also judge whether it wrote into the
    #   user's file.** The previous version only counted layers, so wiping the real registry still passed
    #   -- which is exactly what happened on the day of the incident.
    _now_hash = (hashlib.sha256(_real_models.read_bytes()).hexdigest()
                 if _real_models.is_file() else '')
    ok('B2b ★★★ 判据造的数据**只写进临时登记表**；用户真实的 `llm_models.json` 一个字节没动',
       _tmp_models.is_file() and _now_hash == _real_hash,
       f'临时表已写={_tmp_models.is_file()} · 真实表哈希未变={_now_hash == _real_hash}'
       f'（{_real_models.name}）')

    # ── B3：取消按钮**只关一层**（成对判据 —— 防"一刀切"把取消也改成关两层）──
    print('\n── B3. 取消按钮只关一层（成对：别一刀切）──')
    while VU.open_dialogs(page):
        page.pop_dialog()
        await asyncio.sleep(0.2)
    app.show_global_settings()
    await asyncio.sleep(0.9)
    app._agent_editor(specs[0], project=None, allow_new=False,
                      on_done=lambda: None)
    await asyncio.sleep(0.7)
    top3 = (VU.open_dialogs(page) or [page])[-1]
    cancel_btn = None
    for c in VU.walk(top3):
        if c is not None and _btn_label(c) == '取消':
            cancel_btn = c
            break
    if cancel_btn is None:
        ok('B3 取消只关一层', False, '（没找到「取消」按钮）')
    else:
        cancel_btn.on_click(None)
        await asyncio.sleep(0.9)
        after3 = len(_real_dialogs(page))
        ok('B3 ★★ 取消只关一层（设置对话框还在，用户可以继续改别的）',
           after3 == 1, f'实测 {after3} 层（期望 1）')

    # ── B4：演员类型编辑框保存后**关两层**（_actor_type_editor）──
    print('\n── B4. 演员类型编辑框：保存后关两层 ──')
    while VU.open_dialogs(page):
        page.pop_dialog()
        await asyncio.sleep(0.2)
    app.show_global_settings()
    await asyncio.sleep(0.9)
    # 找一个演员类型来编辑（不依赖具体名字 —— 取第一个）
    from actors import casting as CASTING
    type_names = CASTING.type_names()
    if not type_names:
        ok('B4 保存后 0 层（关两层）', False, 'CASTING.type_names() 为空')
    else:
        app._actor_type_editor(type_names[0], create=False,
                               on_done=lambda: None)
        await asyncio.sleep(0.7)
        mid4 = len(VU.open_dialogs(page))
        ok('B4_pre 演员类型编辑框叠上后 ≥2 层', mid4 >= 2, f'实测 {mid4} 层')
        top4 = (VU.open_dialogs(page) or [page])[-1]
        save_btn4 = _find_btn(top4, '保存')
        if save_btn4 is None:
            ok('B4 保存后 0 层（关两层）', False,
               '（没找到「保存」按钮 ⇒ 这一节跑不了，B4 算红）')
        else:
            save_btn4.on_click(None)
            await asyncio.sleep(0.9)
            after4 = len(_real_dialogs(page))
            ok('B4 ★★★ 保存后**0 层**（演员类型编辑 + 设置对话框都关了，'
               '用户原话「别的对话框如果有保存按钮的…修复下」）',
               after4 == 0, f'实测 {after4} 层')

    # ── B5：角色编辑框保存后**关三层**（_casting_editor，叠 3 层）──
    print('\n── B5. 角色编辑框：保存后关三层 ──')
    while VU.open_dialogs(page):
        page.pop_dialog()
        await asyncio.sleep(0.2)
    # 这条路径要叠 3 层：设置 → 角色设置 → 角色编辑。需要一个项目 + 一个人物。
    # 复用 B 节开头造的夹具（`tmp/'Projects'` 里那个 project）。
    # [EN] This path stacks 3 layers: settings -> role settings -> role editor. Needs a project + one
    # [EN] person. Reuses the fixture made at the top of section B.
    from store.project import Project, scan_projects
    # ⚠ 2026-10-22：这里原来写 `Project.scan(...)` —— **没有这个方法**（扫目录的是模块级
    #   `scan_projects`），而且"复用 B 节开头造的夹具"这句注释也是假的：B 节压根没造项目。
    #   于是 `projs` 永远为空，B5 永远红在"这一节跑不了"。判据要**自己造数据**。
    # [EN] ⚠ 2026-10-22: this used to call `Project.scan(...)`, which **does not exist** (the module
    # [EN] level `scan_projects` does that), and "reuse the fixture from the top of section B" was
    # [EN] false -- section B never created a project. So `projs` was always empty and B5 was always
    # [EN] red with "this section cannot run". Criteria must **create their own data**.
    projs = scan_projects(Path(CFG.projects_dir()))
    if not projs:
        try:
            Project.create_new(Path(CFG.projects_dir()), '存档关闭验证书')
            projs = scan_projects(Path(CFG.projects_dir()))
        except Exception as _ex:                             # noqa: BLE001
            print(f'  造项目失败：{_ex!r}', flush=True)
    if not projs:
        ok('B5 保存后 0 层（关三层）', False,
           '（没项目 ⇒ 这一节跑不了，B5 算红）')
    else:
        proj = projs[0]
        app.show_project_settings()
        await asyncio.sleep(0.9)
        # 写一个人物（判据自己造数据 —— working memory 第十五节）
        # ⚠ 2026-10-22：**格式必须是"列表"**（`- 姓名: xxx`）。原来写的是"以姓名为 key 的字典"，
        #   而 `casting.load_cards` 只认列表 ⇒ 读出来是空表 ⇒ `focus` 匹配不到人 ⇒
        #   角色编辑框根本没叠上去（B5 长期卡在"实测 2 层"）。判据的夹具必须长得像真实数据。
        # [EN] ⚠ 2026-10-22: the format must be a **list** (`- 姓名: xxx`). It used to be a dict keyed by
        # [EN] name, which `casting.load_cards` does not read => empty roster => `focus` matched nobody
        # [EN] => the role editor never stacked (B5 stuck at "2 layers"). Fixtures must look like real data.
        people_yaml = proj.settings_dir / '人物.yaml'
        if not people_yaml.exists():
            try:
                people_yaml.parent.mkdir(parents=True, exist_ok=True)
                people_yaml.write_text(
                    '- 姓名: 探针人物\n  演员类型: 演员\n  变奏: 0\n  选角: ""\n  打破类型: false\n',
                    encoding='utf-8')
            except Exception:                              # noqa: BLE001
                pass
        app._casting_dialog(proj, focus='探针人物')
        await asyncio.sleep(0.9)
        mid5 = len(VU.open_dialogs(page))
        ok('B5_pre 角色编辑框叠上后 ≥3 层', mid5 >= 3, f'实测 {mid5} 层')
        top5 = (VU.open_dialogs(page) or [page])[-1]
        save_btn5 = _find_btn(top5, '保存')
        if save_btn5 is None:
            ok('B5 保存后 0 层（关三层）', False,
               '（没找到「保存」按钮 ⇒ 这一节跑不了，B5 算红）')
        else:
            save_btn5.on_click(None)
            await asyncio.sleep(0.9)
            after5 = len(_real_dialogs(page))
            ok('B5 ★★★ 保存后**0 层**（角色编辑 + 角色设置 + 项目设置都关了，'
               '用户原话「别的对话框如果有保存按钮的…修复下」）',
               after5 == 0, f'实测 {after5} 层')

    # 清场，免得影响后面
    while VU.open_dialogs(page):
        page.pop_dialog()
        await asyncio.sleep(0.1)
    # ★ 跑到了这里才算"整段跑完"（中途抛异常时 flet 会吞掉异常，收尾只能靠这个标记分辨）。
    # [EN] Only reaching here counts as "ran to the end"; flet swallows mid-run exceptions, so the
    # [EN] summary can only tell by this flag.
    global DONE
    DONE = True

    # ★★★ 2026-10-30：**必须自己关窗退出**（`await shutdown(page, code=...)`）。
    #   到这里只说明"本会话的协程跑完了"，窗口还开着 ⇒ `ft.run()` 一直等，
    #   `main()` 的结论永远走不到。实测卡在 `DONE = True` 之后 90 秒无输出。
    #   ⚠ 退出码必须在**关窗之前**落实（`window.destroy()` 会抛 CancelledError，
    #     写在它后面的一切都不会执行 —— 见 `util.flet_shutdown.shutdown` 的注释）。
    # [EN] ★★★ 2026-10-30: **close the window and exit here** (`await shutdown(page, code=...)`).
    # [EN] Reaching this line only means "this session's coroutine finished"; the window is still
    # [EN] open, so `ft.run()` waits forever and the summary in `main()` is never reached
    # [EN] (measured: 90 s of silence after `DONE = True`).
    # [EN] ⚠ The exit code must be committed **before** the window closes (`window.destroy()` raises
    # [EN] CancelledError; anything after it never runs).
    _code, _lines = _verdict()
    print('\n'.join(_lines))
    from util.flet_shutdown import shutdown
    await shutdown(page, code=_code)


def main() -> int:
    # ★★★ 2026-10-22：**三个外部创作服务必须在这里关掉**。
    #   本机 `.env` 里它们是开的，而判据一开界面，产品就会"自动拉起"它们
    #   （实测一次跑了 7 分钟，日志里 PlotPilot / MuMuAINovel / PenShot 各拉一遍）。
    #   这与 `verify_run_control` 那次被 timeout 杀是同一个坑：**判据不许读用户的 `.env`**。
    # [EN] ★★★ 2026-10-22: **switch the three external services off here.** The local `.env` has them
    # [EN] on, so as soon as the UI starts the product "auto-starts" them (measured: 7 minutes, with
    # [EN] PlotPilot / MuMuAINovel / PenShot each launched). Same trap as `verify_run_control` being
    # [EN] killed by timeout: **criteria must not read the user's `.env`**.
    from config import CFG                                    # noqa: PLC0415
    for _k in ('MUMU_ENABLED', 'MUMU_AUTOSTART', 'PENSHOT_ENABLED', 'PENSHOT_AUTOSTART',
               'PLOTPILOT_ENABLED', 'PLOTPILOT_AUTOSTART'):
        CFG.set(_k, 'false')
    with tempfile.TemporaryDirectory(prefix='nws_save_close_') as tmp_s:
        tmp = Path(tmp_s)
        VU.isolate_projects_dir(tmp / 'Projects')
        CAT.set_soft_dir(tmp / 'agents')

        print('起真机 …', flush=True)
        try:
            ft.run(_render)
        except Exception as ex:                              # noqa: BLE001
            print(f'真机跑挂了：{ex!r}')
            return 2

    # ★★★ 2026-10-22：`_render` 里抛的异常**不会**传出来 —— flet 在
    #   `on_session_created` 里自己 catch 并只打印一行 `Unhandled error`，于是 `ft.run()`
    #   正常返回、`main` 的 try 什么也没抓到，收尾看到"跑了 2 条、0 条失败"就报"全部通过"。
    #   （实测：`ft.ElevatedButton` 那个 AttributeError 就是这样被吞掉的。）
    #   ⇒ 让 `_render` 在**最后**设一个标记；没有标记 = 中途断了 = 不算通过。
    # [EN] ★★★ 2026-10-22: exceptions raised inside `_render` **never reach** the caller -- flet
    # [EN] catches them in `on_session_created` and only prints "Unhandled error", so `ft.run()`
    # [EN] returns normally and the summary reports "all passed" for the few assertions that ran
    # [EN] (measured: the `ft.ElevatedButton` AttributeError was swallowed exactly like that).
    # [EN] => `_render` sets a flag **at the very end**; no flag means it broke mid-way.
    # ★★ 2026-10-30：结论与退出码**统一走 `_verdict()`**（`_render` 收尾已经打过一遍；
    #   正常路径上 `shutdown(code=...)` 会先 `os._exit`，走不到这里 —— 这一份是
    #   "退出没成功"时的兜底。⚠ 不要在这旁边再抄一份判据文本，两处必然漂。）
    # [EN] ★★ 2026-10-30: the verdict and exit code go through `_verdict()` only (the tail of
    # [EN] `_render` already printed it; on the normal path `shutdown(code=...)` `os._exit`s first,
    # [EN] so this is the fallback when the exit did not take. Never copy the wording here.)
    # ★★★ 2026-10-22：**一条断言都没跑 = 不通过**，不是"全部通过"。
    #   这条判据曾经因为 `import app_flet` 失败（`gui/` 不在 sys.path）而一条都没跑，
    #   收尾照样打印"共 0 项断言，失败 0 项 → 全部通过"，于是长期假绿。
    #   与"脚本崩了 ≠ 判据抓到了"是同一条规矩：空跑不能算绿。
    # [EN] ★★★ 2026-10-22: **zero assertions is not a pass.** This script once died before running a
    # [EN] single assertion (`import app_flet` failed because `gui/` was not on `sys.path`) and still
    # [EN] printed "0 assertions, 0 failures => all passed", so it was silently green for a long time.
    # [EN] Same rule as "a crash is not a catch": running nothing cannot count as green.
    code, lines = _verdict()
    print('\n'.join(lines))
    return code


if __name__ == '__main__':
    sys.exit(main())
