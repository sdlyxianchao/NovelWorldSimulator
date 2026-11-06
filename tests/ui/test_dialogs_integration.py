# -*- coding: utf-8 -*-
"""UI 实时集成测试：真实运行 Flet 应用并触发所有交互。

关键点：
- 在会话挂载后再触发交互（模拟真实点击时序）
- 通过 page.on_error 捕获运行期错误
- 校验对话框确实进入 page.overlay 且 open=True
- 校验「浏览」按钮的处理器是协程（否则 Flet 会静默吞掉、按钮失效）

用法：
    python tests/ui/test_dialogs_integration.py

English:
UI live integration test: actually run the Flet app and trigger all interactions.
Key points:
- Trigger interactions after the session is mounted (simulate real click timing)
- Capture runtime errors via page.on_error
- Verify the dialog actually enters page.overlay with open=True
- Verify the "Browse" button handler is a coroutine (otherwise Flet silently swallows it and the button stops working)
Usage:
    python tests/ui/test_dialogs_integration.py
"""
import sys
import os
import asyncio
import inspect
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))     # verify_ui_common（隔离项目根用）
# [EN] verify_ui_common (isolates project root)
os.environ['MOCK_LLM'] = 'true'

from util.flet_shutdown import shutdown, exit_now  # noqa: E402

RESULT_FILE = APP_DIR / 'logs' / 'ui_test_result.txt'

runtime_errors = []
results = []


def _record(name, ok, detail=""):
    results.append((name, ok, detail))


def _write_results():
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULT_FILE, 'w', encoding='utf-8') as f:
        for name, ok, detail in results:
            f.write(f"{'OK' if ok else 'ERR'}\t{name}\n")
            if detail:
                f.write(f"    {detail}\n")
        if runtime_errors:
            f.write("\n=== 运行期错误 ===\n")
            for err in runtime_errors:
                f.write(f"{err}\n")

    print("\n" + "=" * 60)
    print("UI 实时集成测试结果")
    print("=" * 60)
    for name, ok, detail in results:
        print(f"{'✓' if ok else '✗'} {name}")
        if detail:
            print(f"    {detail}")
    if runtime_errors:
        print("\n运行期错误:")
        for err in runtime_errors:
            print(f"  {err}")
    print("=" * 60)


def main():
    import tempfile

    import flet as ft

    import verify_ui_common as VU
    from config import CFG
    from store.project import Project

    from gui.app_flet import NovelWorldApp

    # 项目根隔离到临时目录：本测试会造项目、也会开「拾卷」，
    # 不隔离就会去扫/写用户真实的 Projects 目录（历史遗留的 `UI测试项目` 就是从这来的）。
    # [EN] Isolate the project root to a temp dir: this test creates projects and also opens "拾卷",
    # [EN] without isolation it would scan/write the user's real Projects directory (the legacy `UI测试项目`
    # [EN] came from here).
    _tmp = Path(tempfile.mkdtemp(prefix='nws_dlgtest_'))
    tmp_projects = _tmp / 'Projects'
    VU.isolate_projects_dir(tmp_projects)

    def run(page: ft.Page):
        app = NovelWorldApp()

        def on_error(e):
            msg = getattr(e, "data", None) or str(e)
            runtime_errors.append(str(msg))
            print(f"[运行期错误] {msg}")

        page.on_error = on_error

        try:
            app.main(page)
            _record("应用初始化", True)
        except Exception as e:
            _record("应用初始化", False, f"{e}\n{traceback.format_exc()}")
            _write_results()
            # run() 是同步函数，没法 await 关窗；exit_now 内部会按父进程 PID
            # 收掉本进程拉起的 flet 客户端，保证不漏 "Working..." 孤儿窗口
            # [EN] run() is a sync function, can't await window close; exit_now internally uses the parent process
            # [EN] PID
            # [EN] to reap the flet client this process spawned, ensuring no orphan "Working..." windows are left
            # [EN] behind
            exit_now(1)

        def close_all():
            try:
                while page.pop_dialog() is not None:
                    pass
            except Exception:
                pass

        async def click_all():
            await asyncio.sleep(1.0)

            # ── 开始界面菜单（同步处理器）──
            # [EN] ── Start screen menu (sync handlers) ──
            sync_handlers = [
                ("菜单-开卷", app._on_new_story),
                ("菜单-拾卷", app._on_old_story),
                ("菜单-天机", app._on_global_settings),
                ("菜单-书斋", app._on_project_settings),
            ]
            for name, handler in sync_handlers:
                close_all()
                before = len(runtime_errors)
                try:
                    handler(None)
                    await asyncio.sleep(0.5)
                    page.update()
                    await asyncio.sleep(0.3)
                    ok = len(runtime_errors) == before
                    _record(name, ok,
                            "" if ok else f"产生 {len(runtime_errors) - before} 个运行期错误")
                except Exception as e:
                    _record(name, False, f"{e}\n{traceback.format_exc()}")

            # ── 各对话框：构造 + 校验进入对话框栈且 open ──
            # **项目根先隔离 + 造一个夹具**：
            # ① 「拾卷」在没有项目时**根本不弹框**（只发一条提示），
            #    所以不造夹具这条必挂；
            # ② 以前它扫的是用户**真实**的 Projects 目录 —— 靠里面残留的夹具
            #    才一直绿着，用户清干净后立刻变成 FAIL；顺带还往用户目录里
            #    留下一个 `UI测试项目`（那正是用户列表里那个空文件夹的来源）。
            # [EN] ── Each dialog: construct + verify it enters the dialog stack and is open ──
            VU.isolate_projects_dir(tmp_projects)
            fixture_proj = Project.create_new(Path(CFG.projects_dir()), 'UI测试项目')

            dialog_cases = [
                ("开卷向导", lambda: app.show_import_wizard()),
                ("拾卷对话框", lambda: app.show_projects_dialog()),
                ("天机对话框", lambda: app.show_global_settings()),
            ]
            for name, opener in dialog_cases:
                close_all()
                before = len(runtime_errors)
                try:
                    dlg = opener()
                    await asyncio.sleep(0.5)
                    page.update()
                    await asyncio.sleep(0.3)
                    problems = []
                    if dlg is None:
                        problems.append("返回 None")
                    else:
                        if getattr(dlg, 'open', None) is not True:
                            problems.append(f"open={getattr(dlg, 'open', None)}")
                        if not _in_dialog_stack(page, dlg):
                            problems.append("未进入对话框栈")
                    if len(runtime_errors) != before:
                        problems.append(f"运行期错误 +{len(runtime_errors) - before}")
                    _record(f"{name}-显示", not problems, "；".join(problems))
                except Exception as e:
                    _record(f"{name}-显示", False, f"{e}\n{traceback.format_exc()}")

            # ── 书斋：需要项目（用上面那个夹具，不再动用户目录）──
            # [EN] ── Study: needs project (use the fixture above, no longer touch the user directory) ──
            close_all()
            try:
                app.current_project = fixture_proj
                dlg = app.show_project_settings()
                await asyncio.sleep(0.5)
                page.update()
                problems = []
                if dlg is None:
                    problems.append("返回 None")
                else:
                    if getattr(dlg, 'open', None) is not True:
                        problems.append(f"open={getattr(dlg, 'open', None)}")
                    if not _in_dialog_stack(page, dlg):
                        problems.append("未进入对话框栈")
                _record("书斋对话框-显示", not problems, "；".join(problems))
            except Exception as e:
                _record("书斋对话框-显示", False, f"{e}\n{traceback.format_exc()}")

            # ── 校验「浏览」按钮处理器是协程 ──
            # [EN] ── Verify the "Browse" button handler is a coroutine ──
            close_all()
            try:
                dlg = app.show_import_wizard()
                await asyncio.sleep(0.4)
                btn = _find_control(dlg, ft.FilledButton, text_contains="浏览")
                if btn is None:
                    _record("浏览按钮-存在", False, "未找到浏览按钮")
                else:
                    is_async = inspect.iscoroutinefunction(btn.on_click)
                    _record("浏览按钮-异步处理器", is_async,
                            "" if is_async else "on_click 不是协程函数，FilePicker 不会打开")
            except Exception as e:
                _record("浏览按钮-异步处理器", False, f"{e}\n{traceback.format_exc()}")

            close_all()

            # ── 主界面 ──
            # [EN] ── Main UI ──
            try:
                app.show_main_screen()
                await asyncio.sleep(0.5)
                page.update()
                _record("主界面", True)
            except Exception as e:
                _record("主界面", False, f"{e}\n{traceback.format_exc()}")

            await asyncio.sleep(0.4)
            _write_results()
            ok = (not runtime_errors) and all(r[1] for r in results)
            # 必须先把 Flet 客户端窗口关掉再退出，否则会漏一个卡在
            # "Working..." 加载页上的孤儿窗口（详见 util/flet_shutdown.py）
            # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
            #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
            #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
            # [EN] The Flet client window must be closed first before exiting, otherwise an orphan window stuck on
            # [EN] the "Working..." loading page will be leaked (see util/flet_shutdown.py)
            # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
            # [EN] CancelledError
            # [EN] which cancels this coroutine; the `exit_now(...)` on the line after `await shutdown(page)`
            # [EN] **never executes** (exit code is always 0 = false green). See `util/flet_shutdown.shutdown()`.
            await shutdown(page, code=0 if ok else 1)

        page.run_task(click_all)

    try:
        ft.run(run)
    except Exception as e:
        _record("Flet 启动", False, f"{e}\n{traceback.format_exc()}")
        _write_results()
        return 1
    return 0


def _in_dialog_stack(page, dlg) -> bool:
    """检查对话框是否在页面的对话框栈中。
        English:
    Check whether the dialog is in the page's dialog stack.
    """
    stack = getattr(page, '_dialogs', None)
    if stack is None:
        return False
    return dlg in getattr(stack, 'controls', [])


def _control_text(node) -> str:
    """提取控件上的文本（兼容 Flet 1.0：Text 用 value，按钮文本在 content 里）。
        English:
    Extract the text on a control (Flet 1.0 compatible: Text uses value, button text is in content).
    """
    parts = []
    for attr in ('text', 'label', 'title', 'value'):
        v = getattr(node, attr, None)
        if isinstance(v, str):
            parts.append(v)
    content = getattr(node, 'content', None)
    if isinstance(content, str):
        parts.append(content)
    return " ".join(parts)


def _find_control(root, cls, text_contains=None):
    """在控件树中查找符合条件的控件。
        English:
    Find controls matching the criteria in the control tree.
    """
    if root is None:
        return None
    if isinstance(root, cls):
        txt = _control_text(root)
        if text_contains is None or text_contains in txt:
            return root
    # 若控件本身是按钮，还要看它的 content 子节点文本
    # [EN] If the control itself is a button, also check the text of its content child node
    if isinstance(root, cls) and text_contains is not None:
        sub = getattr(root, 'content', None)
        if sub is not None and not isinstance(sub, str):
            if text_contains in _control_text(sub):
                return root
    for attr in ('controls', 'tabs', 'actions'):
        children = getattr(root, attr, None)
        if isinstance(children, list):
            for child in children:
                found = _find_control(child, cls, text_contains)
                if found:
                    return found
    content = getattr(root, 'content', None)
    if content is not None and not isinstance(content, str):
        found = _find_control(content, cls, text_contains)
        if found:
            return found
    return None


if __name__ == '__main__':
    sys.exit(main())
