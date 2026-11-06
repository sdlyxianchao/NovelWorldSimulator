# -*- coding: utf-8 -*-
"""真机判据：天机「外部创作服务」页 → **左侧三个子页签**（2026-10-23）。

用户原话：
    「天机的外部创作服务……这个Tab进去之后**在左侧变成3个tab**，分别承载3个服务，
     而不是放到一整个Tab。然后在这3个Tab上用一个**很小的图标**
     比如**停止是 `-` 启动是 `*`** 表示状态」

为什么这条必须**真起窗口**：`_side_tabs` 出现在源码里，不代表那三行真的摆上了页面
（本项目多次栽在"控件造出来了但没摆上去"）。这一支量的是**控件树**：
  · 左侧真的三行、每行真的带 `*`/`-`、名字对得上；
  · 右侧三个内容区同时存在、只显示一个；
  · 点第二行真的切页（`visible` 翻转 + 选中行换底色）。

跑法：`.venv\\Scripts\\python.exe tools/verify_svc_side_tabs.py`
报告：`assets/screenshots/svc_side_tabs_report.json`

English:
On-device assertion: Tianji's "External Creative Services" page -> **three left-hand
sub-tabs** (2026-10-23).
Why this must open a real window: `_side_tabs` in the source does not prove those three rows
were placed (this project has repeatedly hit "created but never placed"). This checks the
**control tree**: three rows with a `*`/`-` lamp each and matching names; three bodies that
all exist while only one is visible; and clicking the second row really switches pages.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import verify_ui_common as VU                                  # noqa: E402

VU.redirect_env_writes()

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def walk(c, out, depth=0):
    if c is None or depth > 40:
        return
    out.append(c)
    for attr in ('controls', 'content'):
        v = getattr(c, attr, None)
        if isinstance(v, list):
            for x in v:
                walk(x, out, depth + 1)
        elif v is not None:
            walk(v, out, depth + 1)


def _row_parts(m) -> tuple[str, str]:
    """一行 → `(灯字符, 名字)`。行结构：`mark(Container) > bar(Container) > Row[dot, name]`。"""
    bar = getattr(m, 'content', m)
    rw = getattr(bar, 'content', None)
    parts = list(getattr(rw, 'controls', []) or [])
    dot = str(getattr(parts[0], 'value', '?')) if parts else '?'
    nm = str(getattr(parts[1], 'value', '?')) if len(parts) > 1 else '?'
    return dot, nm


def _pen_dot(root) -> str:
    """从左侧页签里取 PenShot 那一行的灯字符（找不到就 `?`）。

    ⚠ 参数可以是**一个 root，也可以是 root 列表** —— 调用点两处写法不一样
      （`roots2[0]` 与 `roots2`），第一版只接受前者，第二处当场
      `AttributeError: 'list' object has no attribute 'controls'`。
      统一成"先归一化成一个 root"，调用点就不用记这件事。
    [EN] The argument may be **one root or a list of roots** -- the two call sites differ
    (`roots2[0]` vs `roots2`), and v1 only accepted the former, raising
    `AttributeError: 'list' object has no attribute 'controls'` at the second. Normalise to a
    single root so call sites do not have to remember.
    """
    if isinstance(root, list):
        root = root[0] if root else None
    if root is None:
        return '?'
    rows = list(getattr(getattr(root.controls[0], 'content', None), 'controls', []) or [])
    for m in rows:
        bar = getattr(m, 'content', m)
        parts = list(getattr(getattr(bar, 'content', None), 'controls', []) or [])
        if len(parts) > 1 and str(getattr(parts[1], 'value', '')) == 'PenShot':
            return str(getattr(parts[0], 'value', '?'))
    return '?'


async def main(page) -> None:
    import flet as ft
    from gui.app_flet import NovelWorldApp
    from util.flet_shutdown import shutdown

    app = NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(0.8)

    app.show_global_settings(tab=app.TAB_GLOBAL_EXTERNAL)
    page.update()
    await asyncio.sleep(1.5)

    # ⚠ Flet 1.0 的对话框在 `page._dialogs.controls`，**不在 `page.overlay`**
    #   （`show_dialog()` 就是往那个列表 append）。查错层会得到"结构没生效"的假红。
    # [EN] Dialogs live in `page._dialogs.controls` in Flet 1.0, **not** in `page.overlay`
    # (`show_dialog()` appends there). Checking the wrong layer gives a false red.
    allc: list = []
    dlg = getattr(page, '_dialogs', None)
    for r in (getattr(dlg, 'controls', None) or []):
        walk(r, allc)
    for c in page.controls:
        walk(c, allc)

    roots = [c for c in allc if getattr(c, '_side_tabs', False)]
    ok('X1 ★★★ 左侧竖排页签**真的挂在对话框上**（不是"控件造出来了但没摆上去"）',
       len(roots) == 1, f'找到 {len(roots)} 个')

    if not roots:
        await shutdown(page, code=2)
        return

    root = roots[0]
    left, right = root.controls[0], root.controls[1]
    rows = list(getattr(getattr(left, 'content', None), 'controls', []) or [])
    ok('X2 ★★★ 左侧**正好三行**（三个服务各一行，不是一整条长页）',
       len(rows) == 3, f'行数={len(rows)}')

    pairs = [_row_parts(m) for m in rows]
    dots = [p[0] for p in pairs]
    names = [p[1] for p in pairs]
    ok('X3 ★★★ 每行**真的带状态符**，且只可能是 `*` 或 `-`（用户点名的两个）',
       bool(pairs) and all(d in ('*', '-') for d in dots), f'灯={dots}')
    ok('X4 ★★ 三个名字对得上，且顺序稳定（MuMuAINovel / PlotPilot / PenShot）',
       names == ['MuMuAINovel', 'PlotPilot', 'PenShot'], str(names))

    # 灯的颜色与字符要**一致**：`-` 却亮着绿，会被读成"半开着"。
    # [EN] Lamp character and colour must agree: a green `-` reads as "half on".
    greens = []
    muted = []
    for m in rows:
        bar = getattr(m, 'content', m)
        parts = list(getattr(getattr(bar, 'content', None), 'controls', []) or [])
        col = str(getattr(parts[0], 'color', '')) if parts else ''
        greens.append(col)
    ok('X5 ★★★ 灯的颜色与字符**对得上**（`*` 是绿的、`-` 是淡的 —— '
       '绿色的 `-` 会被读成"半开着"，比不刷新更误导）',
       len(set(greens)) <= 2, f'颜色={greens}')

    bodies = list(getattr(right, 'controls', []) or [])
    vis = [bool(b.visible) for b in bodies]
    ok('X6 ★★★ 右侧三个内容区**同时存在**、但只显示一个'
       '（都建出来是为了保存逻辑还读得到那些控件；只显示一个是页签的本意）',
       len(bodies) == 3 and sum(vis) == 1, f'内容区={len(bodies)} visible={vis}')

    # 点第二行：内容真的切过去，选中行换底色
    root._side_pick('pp')
    page.update()
    await asyncio.sleep(0.35)
    vis2 = [bool(b.visible) for b in bodies]
    bars2 = [getattr(getattr(m, 'content', m), 'bgcolor', None) for m in rows]
    ok('X7 ★★★ 点第二行**真的切页**（内容 `visible` 翻转 + 只有一行有底色）',
       vis2 == [False, True, False] and sum(1 for b in bars2 if b) == 1,
       f'visible={vis2} 底色={bars2}')

    # 第三行也切一次：防止"只有第二行写死了"
    root._side_pick('ps')
    page.update()
    await asyncio.sleep(0.3)
    vis3 = [bool(b.visible) for b in bodies]
    ok('X8 ★★ 第三行同样能切（不是只有第二行写死能用）',
       vis3 == [False, False, True], f'visible={vis3}')

    # 三个页里各自都有「刷新状态」按钮 —— 用户点名要的。
    # [EN] Each of the three pages carries its own "refresh status" button (as asked).
    hit = []
    for b in bodies:
        texts: list = []
        walk(b, texts)
        hit.append(any(isinstance(c, ft.Text) and str(c.value or '') == t('刷新状态')
                       for c in texts))
    ok('X9 ★★★ **三个页里各有一颗「刷新状态」按钮**（用户点名）',
       all(hit), f'命中={hit}')

    # ══════════════════════════════════════════════════════════════
    #  **停机那一半**：灯必须真的变成 `-`
    # [EN] **The stopped half**: the lamp must really become `-`
    # ══════════════════════════════════════════════════════════════
    #  ★ 为什么必须有这一条（2026-10-23 实测发现的空缺）：这台机器上三座服务
    #    **都在跑**，所以上面 X3 看到的全是 `*` —— **"停机显示 `-`"那半个功能
    #    根本没被任何判据考到**（`*` 出现只证明了一半）。
    #    办法：把一座的端口指到没人听的端口，制造一个**必然失败**的探测。
    #  ⚠ 只改**进程内**配置（`verify_ui_common` 已经隔离写盘），不碰用户 `.env`；
    #    跑完必须**改回去**，否则同一进程里后面的判据看到的是坏端口。
    # [EN] ★ Why this must exist (a gap found by measurement on 2026-10-23): all three
    # services happen to be **running** on this machine, so X3 saw only `*` -- **the
    # stopped half was never exercised by any criterion**. The trick: point one service at
    # an unlistened port to force a **guaranteed-failing** probe.
    # ⚠ Only the **in-process** config is changed (`verify_ui_common` already isolates
    # writes); the user's `.env` is untouched, and it is **restored** afterwards.
    #  ★★★ 2026-10-23 晚（这一条第一次跑就红了，红得对）：
    #  原来 X11/X12 只把 **PenShot** 的端口指坏，然后断言"另外两座仍是 `*`"——
    #  这等于**指望这台机器上 MuMu 和 PlotPilot 恰好都在跑**。换个时间跑
    #  （自动拉起还没完成 / 服务被别的东西关掉）就变成 `['-','*','-']`：
    #  灯没坏，**判据在靠环境**。而且"灯永远不会亮"这个同样的缺陷，
    #  在那种环境下反而会被判成绿 —— 也就是它既会假红、也会假绿。
    #  修法按本项目的老规矩：**把混合状态自己造出来**，别指望环境。
    #    · PlotPilot → 本地起一个只回 `/health` 200 的小服务（灯**必须**是 `*`）
    #    · PenShot   → 指到没人听的端口（灯**必须**是 `-`）
    #  这样"亮的那一半"和"灭的那一半"同时被钉住，且两边都由这一条脚本保证。
    # [EN] ★★★ 2026-10-23 evening (this one went red on its first run, and rightly so):
    # X11/X12 used to break only **PenShot**'s port and then assert "the other two are still
    # `*`" -- i.e. it **depended on MuMu and PlotPilot happening to be running on this
    # machine**. Run it at another moment (autostart unfinished, services closed) and you get
    # `['-','*','-']`: the lamp is fine, **the criterion leans on the environment**. Worse,
    # the same defect ("the lamp never lights") would read green in that state -- it can be
    # falsely red *and* falsely green. Fix, per this project's rule: **construct the mixed
    # state yourself**. PlotPilot -> a local stub answering `/health` 200 (lamp **must** be
    # `*`); PenShot -> a dead port (lamp **must** be `-`). Both halves are pinned, both are
    # guaranteed by this script.
    _old_port = CFG.s('PENSHOT_PORT')
    _old_pp_port = CFG.s('PLOTPILOT_PORT')
    _stub_srv = None
    try:
        import http.server as _hs
        import threading as _th

        class _HealthOnly(_hs.BaseHTTPRequestHandler):
            def do_GET(self):                                # noqa: N802
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *_a):                      # 别刷屏
                pass

        _stub_srv = _hs.ThreadingHTTPServer(('127.0.0.1', 0), _HealthOnly)
        _stub_port = _stub_srv.server_address[1]
        _th.Thread(target=_stub_srv.serve_forever, daemon=True).start()
        CFG.set('PLOTPILOT_PORT', str(_stub_port))
        CFG.set('PENSHOT_PORT', '59991')
        from novelservices import penshot_bridge as _PS2
        from novelservices import plotpilot_bridge as _PP2
        _st = _PS2.service_status(timeout=0.8)
        _pp_st = _PP2.service_status(timeout=0.8)
        ok('X10 ★★ 改端口**真的让探测失败**（否则这一条自己就是假的 —— '
           '量的不是"灯会不会变"，而是"端口改了没反应"）',
           not _st.ok and '59991' in str(getattr(_st, 'base_url', '')),
           f'ok={_st.ok} url={getattr(_st, "base_url", "")!r}')
        ok('X10b ★★★ 假服务**真的让探测成功**（这是 X12"灯会亮"那一半的地基：'
           '没有它，X12 只能指望机器上恰好有服务在跑）',
           bool(_pp_st.ok),
           f'pp.ok={_pp_st.ok} url={getattr(_pp_st, "base_url", "")!r}')
        # 关掉当前对话框，重新开一次（让页面按新端口重新探测）
        try:
            page.pop_dialog()
        except Exception:                                    # noqa: BLE001
            pass
        page.update()
        await asyncio.sleep(0.3)
        app.show_global_settings(tab=app.TAB_GLOBAL_EXTERNAL)
        page.update()
        await asyncio.sleep(1.6)

        allc2: list = []
        dlg2 = getattr(page, '_dialogs', None)
        for r in (getattr(dlg2, 'controls', None) or []):
            walk(r, allc2)
        for c in page.controls:
            walk(c, allc2)
        roots2 = [c for c in allc2 if getattr(c, '_side_tabs', False)]
        lamps: list[tuple[str, str, str]] = []
        for rt in roots2:
            rws = list(getattr(getattr(rt.controls[0], 'content', None),
                               'controls', []) or [])
            for m in rws:
                bar = getattr(m, 'content', m)
                parts = list(getattr(getattr(bar, 'content', None),
                                     'controls', []) or [])
                lamps.append((str(getattr(parts[0], 'value', '?')),
                              str(getattr(parts[1], 'value', '?')),
                              str(getattr(parts[0], 'color', ''))) if parts
                             else ('?', '?', ''))
        pen = [x for x in lamps if x[1] == 'PenShot']
        ok('X11 ★★★ 那座不在跑的服务，灯是 **`-`** 且**不再是绿色**'
           '（绿色的 `-` 会被读成"半开着"，比不刷新更误导）',
           bool(pen) and pen[0][0] == '-' and pen[0][2] != '#4f9a6a',
           str(lamps))
        pp = [x for x in lamps if x[1] == 'PlotPilot']
        ok('X12 ★★★ 灯**会亮**：我们自己造的那座（PlotPilot，假服务在回 /health）'
           '是 `*` 且是绿的 —— 与 X11 的 `-` 同时在页上，'
           '"灯永远 `-`"这种缺陷才骗不过去',
           bool(pp) and pp[0][0] == '*' and pp[0][2] == '#4f9a6a',
           str([(x[0], x[1]) for x in lamps]))

        # 点一次「刷新状态」：灯不能被"刷新"抹回 `*`
        try:
            _bodies2 = list(getattr(roots2[0].controls[1], 'controls', []) or [])
            _hit = None
            for b in _bodies2:
                tmp: list = []
                walk(b, tmp)
                for c in tmp:
                    inner = getattr(c, 'content', None)
                    if isinstance(inner, ft.Text) and \
                            str(inner.value or '') == t('刷新状态'):
                        _hit = c
                        break
                if _hit is not None:
                    break
            if _hit is not None:
                _r = _hit.on_click(None)
                if asyncio.iscoroutine(_r):
                    await _r
                page.update()
                await asyncio.sleep(1.2)
                ok('X13 ★★★ 点「刷新状态」之后仍然是 `-`'
                   '（灯跟着**真实状态**走，不是被刷新抹回 `*`）',
                   _pen_dot(roots2) == '-', _pen_dot(roots2))
            else:
                ok('X13 ★★★ 点「刷新状态」之后仍然是 `-`', False, '没找到按钮')
        except Exception as e:                               # noqa: BLE001
            ok('X13 ★★★ 点「刷新状态」之后仍然是 `-`', False, repr(e)[:200])
    finally:
        # ⚠ **必须改回去**：同一进程里后面的判据、以及这条脚本自己的收尾都读它。
        # [EN] **Must restore**: later criteria in this process read it, and so does the
        # teardown of this very script.
        try:
            CFG.set('PENSHOT_PORT', _old_port)
        except Exception:                                    # noqa: BLE001
            pass
        # 假服务与 PlotPilot 的端口也要还回去（不然收尾时"自动拉起/状态"全打在假端口上）。
        # [EN] Restore the stub port too -- otherwise teardown probes the fake server.
        try:
            CFG.set('PLOTPILOT_PORT', _old_pp_port)
        except Exception:                                    # noqa: BLE001
            pass
        if _stub_srv is not None:
            try:
                _stub_srv.shutdown()
                _stub_srv.server_close()
            except Exception:                                # noqa: BLE001
                pass

    # ══════════════════════════════════════════════════════════════
    #  ★★★ X14 —— 用户 2026-10-23 截图的那个 bug：
    #    「✘ 没加载到 novelservices.plotpilot_bridge —— novelservices 目录被删了，
    #      或者里面缺依赖？」
    #  真凶不是目录、不是依赖：`_external_services_block()` 里 `_PP` / `_PS` 写死成
    #  `None` 且从此没人赋值 ⇒ 点「启动服务」**永远**走"没加载到"那条分支。
    #  ⚠ 上一轮 `verify_external_services` 24/24 全绿 —— 它问的是"这页里有没有 import
    #  桥"，而 import 在（在 `_svc_line()` 里），**按钮拿的不是它**。
    #  所以这一条不看源码，**真点那一下**，再念弹窗里的字：
    #    · 把 `start_service` 换成桩（不许真去起服务、不许碰用户的进程）
    #    · 点 PlotPilot 页的「启动服务」
    #    · 弹窗第一行必须是"→ PlotPilot：启动服务"，**不许**出现"没加载到"
    # [EN] ★★★ X14 -- the very bug the user screenshotted: `_PP`/`_PS` were hard-coded
    # `None` and never assigned, so "start service" always took the "not loaded" branch.
    # ⚠ `verify_external_services` was 24/24 green last round -- it asked "is the bridge
    # imported in this page" (it was, inside `_svc_line`); the button just did not get it.
    # So this one ignores the source and **really clicks**: stub `start_service` (never
    # touch the user's processes), click PlotPilot's "启动服务", and read the dialog: the
    # first line must be "→ PlotPilot：启动服务" and must **not** say "not loaded".
    try:
        from novelservices import plotpilot_bridge as _PPB
        _orig_start = _PPB.start_service
        # 桩：签名照抄（`on_line=` 关键字），立刻回一个"没真启动"的失败。
        _PPB.start_service = lambda **kw: (False, '判据桩：没有真的启动服务')
        try:
            try:
                page.pop_dialog()
            except Exception:                                # noqa: BLE001
                pass
            page.update()
            await asyncio.sleep(0.3)
            app.show_global_settings(tab=app.TAB_GLOBAL_EXTERNAL)
            page.update()
            await asyncio.sleep(1.6)

            allc4: list = []
            dlg4 = getattr(page, '_dialogs', None)
            for r in (getattr(dlg4, 'controls', None) or []):
                walk(r, allc4)
            for c in page.controls:
                walk(c, allc4)
            roots4 = [c for c in allc4 if getattr(c, '_side_tabs', False)]
            _start_btn = None
            if roots4:
                _bodies4 = list(getattr(roots4[0].controls[1], 'controls', []) or [])
                if len(_bodies4) > 1:                        # 第 2 页 = PlotPilot
                    _tmp4: list = []
                    walk(_bodies4[1], _tmp4)
                    for c in _tmp4:
                        inner = getattr(c, 'content', None)
                        if (isinstance(inner, ft.Text)
                                and str(inner.value or '') == t('启动服务')
                                and getattr(c, 'on_click', None) is not None):
                            _start_btn = c
                            break
            if _start_btn is None:
                ok('X14 ★★★ 点 PlotPilot 的「启动服务」**不会**说"没加载到"', False,
                   '没找到启动按钮')
            else:
                _r4 = _start_btn.on_click(None)
                if asyncio.iscoroutine(_r4):
                    await _r4
                page.update()
                await asyncio.sleep(1.4)
                # 念弹窗里的字（输出是逐行 push 进去的 Text）
                _lines4: list = []
                _dlg_ctl = getattr(page, '_dialogs', None)
                for r in (getattr(_dlg_ctl, 'controls', None) or []):
                    _t4: list = []
                    walk(r, _t4)
                    _lines4 += [str(c.value) for c in _t4
                                if isinstance(c, ft.Text) and c.value]
                _blob = ' | '.join(_lines4)
                ok('X14 ★★★ 点 PlotPilot 的「启动服务」**不会**说"没加载到"'
                   '（事故原样：`_PP` 写死 None ⇒ 桥明明在盘上，一点就报目录被删）',
                   ('没加载到' not in _blob
                    and 'PlotPilot：启动服务' in _blob),
                   _blob[:160])
        finally:
            _PPB.start_service = _orig_start
    except Exception as e:                                   # noqa: BLE001
        ok('X14 ★★★ 点 PlotPilot 的「启动服务」**不会**说"没加载到"', False,
           repr(e)[:200])

    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n左侧子页签验证：{good}/{n}')
    (OUT / 'svc_side_tabs_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    await shutdown(page, code=(0 if good == n else 2))


if __name__ == '__main__':
    import flet as ft
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
