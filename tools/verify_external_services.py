# -*- coding: utf-8 -*-
"""判据：PlotPilot / PenShot 两个**外部创作服务**的接线真接上了，且默认不拦流程。

来历（2026-10-16 / 2026-10-17）
---------------------------
用户要「给编剧/导演这两个外部服务在天机里加一个单独的配置 Tab」，
并要「本程序能通过 REST API 真正调用它们」。桥（`novelservices/plotpilot_bridge.py`
· `penshot_bridge.py`）已写好；这一支守的是**剧组那条链真的把它们接起来**：

  ① 配置开关默认关（`PLOTPILOT_ENABLED` / `PENSHOT_ENABLED` 都是 False）——
     没开的时候，剧作者/分镜师**一字不变**走内部自写（开关式 + 失败回退）。
  ② 开了之后，`_plotpilot_enabled_for('screenwriter')` / `_penshot_enabled_for(...)`
     真的返回 True（每次现读配置）；而且 PenShot 只对 `director` / `storyboard`
     生效，不对 `screenwriter` 生效（key 白名单）。
  ③ 天机多了一个「外部创作服务」页签，且它的构建函数**真的引用**了
     `plotpilot_bridge` 与 `penshot_bridge`（不是空壳）。
  ④ 两个桥在没起服务时**优雅降级**（`service_status()` 返回 `BridgeStatus`、
     `ok` 是布尔、绝不抛异常冻界面）。

判据怎么量
----------
直接跑代码（不靠"源码里有某字符串"那种弱判据）：现读配置 → 调 glue 函数
→ 看返回值；页签/引用用 `inspect.getsource` + 真读 `TAB_TIPS`；桥降级用真调用。

跑法：`.venv\\Scripts\\python.exe tools/verify_external_services.py`
报告：`assets/screenshots/external_services_report.json`

English:
Assertion: the PlotPilot / PenShot **external creation services** are really wired in,
and by default they do not block the flow.
Origin (2026-10-16 / 2026-10-17)
---------------------------
The user wanted "a separate config Tab in Tianji for these two external services
(playwright / director)", and "the program must be able to really call them via REST API".
The bridges are written; this branch guards that **the crew chain really wires them in**:
  ① config switches default off; ② when on, the glue functions really return True and
     PenShot's key whitelist holds; ③ the Tianji tab exists and its builder really
     references both bridges; ④ the bridges degrade gracefully when not running.

⚠ 2026-10-17 改名说明：导演/分镜引擎的上游从 CutAI（只接 Groq）换成
  PenShot（OpenAI 兼容）。判据里的函数名 / 配置键 / 桥名全部跟着换，
  CutAI 的目录与桥已删除。
[EN] ⚠ 2026-10-17 rename: the director/storyboard engine upstream changed from
  CutAI (Groq-only) to PenShot (OpenAI-compatible). All function names / config keys /
  bridge names in these criteria follow suit; CutAI's directory and bridge are deleted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
REPORT: dict = {'checks': [], 'notes': []}
OUT = APP / 'assets' / 'screenshots' / 'external_services_report.json'


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:300]})
    return bool(cond)


def main() -> int:
    from config import CFG
    from crew import agents as A
    import gui.app_flet as UI
    import novelservices.plotpilot_bridge as P
    import novelservices.penshot_bridge as S

    # ── ① glue 函数都接上了 ──
    # [EN] ── ① the glue functions are all wired in ──
    ok('P0 ★★ 剧组里四个接线函数都在（_plotpilot_enabled_for / _penshot_enabled_for / '
       '_plotpilot_plan / _penshot_storyboard）',
       all(hasattr(A, n) for n in ('_plotpilot_enabled_for', '_penshot_enabled_for',
                                   '_plotpilot_plan', '_penshot_storyboard')),
       [n for n in ('_plotpilot_enabled_for', '_penshot_enabled_for',
                    '_plotpilot_plan', '_penshot_storyboard') if not hasattr(A, n)])

    # ── ② 默认关：ENABLED=False 时，两个 enabled_for 都返回 False（不拦内部自写）──
    # [EN] ── ② default off: when ENABLED is False, both enabled_for return False ──
    CFG.set('PLOTPILOT_ENABLED', False)
    CFG.set('PENSHOT_ENABLED', False)
    ok('P1 ★★ 顶层开关关着时，PlotPilot / PenShot 都不接管（剧作者/分镜师走内部自写）',
       (A._plotpilot_enabled_for('screenwriter') is False
        and A._penshot_enabled_for('storyboard') is False
        and A._penshot_enabled_for('director') is False),
       f"pp={A._plotpilot_enabled_for('screenwriter')} "
       f"ps_storyboard={A._penshot_enabled_for('storyboard')}")

    # ── ③ 开了 PlotPilot：enabled_for 真返回 True ──
    # [EN] ── ③ PlotPilot on: enabled_for really returns True ──
    CFG.set('PLOTPILOT_ENABLED', True)
    CFG.set('PLOTPILOT_FOR_SCREENWRITER', True)
    pp_on = A._plotpilot_enabled_for('screenwriter')
    ok('P2 ★★ 开了 PlotPilot（ENABLED + FOR_SCREENWRITER）时，'
       '_plotpilot_enabled_for(\'screenwriter\') 返回 True',
       pp_on is True, f'pp_on={pp_on}')

    # ── ④ 开了 PenShot：对 director / storyboard 生效，不对 screenwriter 生效 ──
    # [EN] ── ④ PenShot on: works for director / storyboard, not for screenwriter ──
    CFG.set('PENSHOT_ENABLED', True)
    CFG.set('PENSHOT_FOR_DIRECTOR', True)
    ps_sb = A._penshot_enabled_for('storyboard')
    ps_dir = A._penshot_enabled_for('director')
    ps_sw = A._penshot_enabled_for('screenwriter')
    ok('P3 ★★ 开了 PenShot（ENABLED + FOR_DIRECTOR）时，'
       '_penshot_enabled_for 对 storyboard / director 返回 True',
       ps_sb is True and ps_dir is True, f'sb={ps_sb} dir={ps_dir}')
    ok('P4 ★★ PenShot 的 key 白名单生效：不对 screenwriter 返回 True'
       '（它只给导演/分镜师，不抢剧作者的活）',
       ps_sw is False, f'screenwriter={ps_sw}')

    # 还原（顺手把开关复位，避免影响同进程后续）
    # [EN] restore switches (so a later import in the same process is clean)
    CFG.set('PLOTPILOT_ENABLED', False)
    CFG.set('PENSHOT_ENABLED', False)

    # ── ⑤ 天机多了「外部创作服务」页签，且构建函数真引用两个桥 ──
    # [EN] ── ⑤ Tianji gained the "External Creation Services" tab, and its builder really
    # [EN] references both bridges ──
    # ⚠ `TAB_TIPS` 是 `show_global_settings` 里的局部变量（不是模块属性），
    #   所以直接读源码取真相；页签接线那行也在源码里查（不给模块属性留念想）。
    # [EN] ⚠ `TAB_TIPS` is a local inside `show_global_settings` (not a module attr), so
    # [EN] read the source for the truth; the tab-wiring line is also checked in source.
    src = (APP / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    tip_present = '**外部创作服务**（MuMuAINovel + PlotPilot + PenShot）' in src
    tab_wired = '(t("外部创作服务"), _external_services_block()),' in src
    ok('T1 ★★ 天机有「外部创作服务」页签（含 MuMuAINovel + PlotPilot + PenShot；'
       'TAB_TIPS 里那句悬停解释在、且 tab_defs 里接了 `_external_services_block`）',
       tip_present and tab_wired,
       f'tip_present={tip_present} tab_wired={tab_wired}')
    # ⚠ 锚点必须**整行 + 行尾换行**：`…as _PP` 是 `…as _PPB`（保存段那个导入）
    #   的前缀，用裸子串判会被"另一处 import"喂绿（2026-10-17 反例法当场抓到：
    #   变异把 block 里的 import 换成不存在的桩，判据仍然全绿）。
    # [EN] ⚠ Anchors must be **whole lines with the trailing newline**: `...as _PP` is a
    # [EN] prefix of `...as _PPB` (the import in the save section); judging with bare
    # [EN] substrings gets fed green by that other import (caught on the spot by the
    # [EN] counterexample harness on 2026-10-17).
    # ★★★ 2026-10-23 **改口径**（这一轮把三个服务拆成左侧子页签时动的）：
    #   原来这条钉的是 `_external_services_block()` **内部的两行 import**。
    #   重构之后桥的引用挪到了 `_probe_svc()`（统一探测）与 `_svc_line()` 里 ——
    #   页签构建函数**不再直接 import 它们**，于是老锚点必然红。
    #   ⚠ 这正是"判据守的设计被改掉了"那一类：**不是产品漏了，是判据还钉着实现形式**。
    #   但它守的**意图**是对的（"不是空壳"），所以不能删，要换个形式守：
    #     ① 桥**确实被 import**（在 `_probe_svc` 里，按 key 分别取）；
    #     ② 那段页签代码**确实调用了**那个探测函数（不是各自写死一句"没启动"）。
    #   只留 ① 会漏掉"探了但没用"，只留 ② 会漏掉"用了但没探"，两条都要。
    # [EN] ★★★ 2026-10-23 **changed the yardstick** (this round split the three services
    # into left-hand sub-tabs): this used to pin the **two import lines inside**
    # `_external_services_block()`. After the refactor the bridge references moved into
    # `_probe_svc()` (the unified probe) and `_svc_line()`, so the builder no longer imports
    # them directly and the old anchor necessarily goes red.
    # ⚠ This is exactly the "the criterion guards a design that was changed" class: **the
    # product did not regress, the criterion still pins an implementation detail**. Its
    # **intent** ("not an empty shell") is still right, so do not delete it -- re-express it:
    # (1) the bridges **really are imported** (inside `_probe_svc`, per key); (2) that page's
    # code **really calls** the probe (rather than hard-coding "not started" per block).
    # Only (1) would miss "probed but unused"; only (2) would miss "used but never probed".
    _probe_seg = ''
    _pi = src.find('def _load_bridge(')
    if _pi >= 0:
        _pj = src.find('def _probe_svc(', _pi)
        _probe_seg = src[_pi:_pj if _pj > 0 else _pi + 2500]
    _pp_imported = ('plotpilot_bridge' in _probe_seg)
    _ps_imported = ('penshot_bridge' in _probe_seg)
    _mumu_imported = ('mumu_bridge' in _probe_seg)
    ok('T2 ★★ 该页签**真的用到** plotpilot_bridge 与 penshot_bridge'
       '（不是空壳 —— 统一探测函数里按 key 分别 import，且页签代码真的调它）',
       _pp_imported and _ps_imported and _mumu_imported
       and '_probe_svc(' in src
       and ('_svc_ok[_k] = _probe_svc(_k)' in src
            or '_probe_svc, k)' in src),
       f'PP={_pp_imported} PS={_ps_imported} MUMU={_mumu_imported}')

    # ══════════════════════════════════════════════════════════
    #  ★★★ 2026-10-23 事故（用户截图：「✘ 没加载到 novelservices.plotpilot_bridge ——
    #      novelservices 目录被删了，或者里面缺依赖？」）：
    #  `_PP` / `_PS` 在 `_external_services_block()` 里**写死成 None 且从此没人赋值**，
    #  于是"启动服务/停止服务"**永远**走 `bridge is None` 那条分支、永远报"没加载到"，
    #  而 `novelservices/plotpilot_bridge.py` 好端端在盘上、`import` 一行就过。
    #  ⚠ 上面那条 T2 **当时是全绿的** —— 它问的是"这个页签里有没有 import 桥"，
    #  而 import 确实在（在 `_svc_line()` 里），只是**按钮拿的不是那个模块**。
    #  这就是"判据守的是形式（字出现），不是行为（谁被交给了按钮）"。
    #  ⇒ 加这条，直接问 **AST**：赋给 `_PP` / `_PS` 的表达式是不是**真的取模块**，
    #  以及点击时有没有"再取一次"的兜底。
    # [EN] ★★★ 2026-10-23 incident: `_PP` / `_PS` were hard-coded `None` and never assigned,
    # so start/stop **always** took the `bridge is None` branch, while the bridge file existed
    # and imported fine. ⚠ T2 above was **all green** at the time: it asked "is the bridge
    # imported in this page", and it was (inside `_svc_line`) -- only the button did not get
    # that module. So ask the **AST** instead: is what is assigned to `_PP` really a module
    # fetch, and does the click handler re-fetch as a fallback?
    import ast as _ast

    def _fn_node(name: str):
        for _n in _ast.walk(_ast.parse(src)):
            if isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and _n.name == name:
                return _n
        return None

    _pp_from_loader = False
    _ps_from_loader = False
    _esb = _fn_node('_external_services_block')
    if _esb is not None:
        for _n in _ast.walk(_esb):
            if not isinstance(_n, _ast.Assign):
                continue
            # 目标名（`_PP = …` 与 `_PP, _ = …` 两种写法都要认）。
            _names: list[str] = []
            for _t in _n.targets:
                if isinstance(_t, _ast.Name):
                    _names.append(_t.id)
                elif isinstance(_t, _ast.Tuple):
                    _names += [e.id for e in _t.elts if isinstance(e, _ast.Name)]
            # 右值：元组取第一项（`_PP, _ = _load_bridge('pp')`）。
            _call = (_n.value.elts[0] if isinstance(_n.value, _ast.Tuple)
                     and _n.value.elts else _n.value)
            _is_loader = (isinstance(_call, _ast.Call)
                          and isinstance(_call.func, _ast.Name)
                          and _call.func.id == '_load_bridge'
                          and bool(_call.args)
                          and isinstance(_call.args[0], _ast.Constant))
            _key = _call.args[0].value if _is_loader else ''
            # ⚠ 写死 `None`（事故原样）在这里必然 `_is_loader=False` ⇒ 判红。
            if '_PP' in _names:
                _pp_from_loader = _is_loader and _key == 'pp'
            if '_PS' in _names:
                _ps_from_loader = _is_loader and _key == 'ps'
    _refetch = "_b, _ = _load_bridge(svc_key)" in src
    ok('T2b ★★★ 启停按钮**真的拿到了桥模块**（`_PP`/`_PS` 由 `_load_bridge` 取，'
       '不是写死 None —— 否则点「启动服务」永远报"没加载到"，而文件其实在）'
       '，且点击时还会**再取一次**（依赖刚装好后重试能成功）',
       _pp_from_loader and _ps_from_loader and _refetch,
       f'PP={_pp_from_loader} PS={_ps_from_loader} refetch={_refetch}')

    # ── ⑥ 桥在没起服务时优雅降级 ──
    # [EN] ── ⑥ bridges degrade gracefully when not running ──
    # ⚠ 两个桥**各自**有自己的 `BridgeStatus` 类（不是一个共享的），所以各自按自己的类判。
    # [EN] ⚠ Each bridge has **its own** `BridgeStatus` class (not a shared one), so judge each
    # [EN] by its own class.
    try:
        ps = P.service_status()
        ss = S.service_status()
        degrade_ok = (isinstance(ps, P.BridgeStatus) and isinstance(ss, S.BridgeStatus)
                      and isinstance(ps.ok, bool) and isinstance(ss.ok, bool))
        detail = (f'pp.ok={ps.ok} ps.ok={ss.ok}')
    except Exception as _e:                                # noqa: BLE001
        degrade_ok = False
        detail = f'抛异常了：{_e!r}'
    ok('B1 ★★ 两个桥 `service_status()` 优雅降级（返回各自的 BridgeStatus、ok 是布尔、'
       '绝不抛异常冻界面）',
       degrade_ok, detail)

    # ── B2：PlotPilot 的 start_service 必须**非阻塞**（Popen），且跳过它自带的孤儿清理 ──
    # [EN] ── B2: PlotPilot's start_service must be **non-blocking** (Popen) and skip its own orphan sweep ──
    #
    # ★ 2026-10-17（实测踩的）：原来是 `subprocess.run(uvicorn …)` ——
    #   ① **不 detach**：成功那一刻函数**永不返回**（等到超时报"启动超过 N 秒"，
    #      把明明活着的服务判成失败）；② 失败时只看 stdout，uvicorn 的报错在 stderr。
    #   而它自带的"清理残留进程"按关键字 `uvicorn` 匹配 —— 会把**正在跑的 PenShot 杀掉**
    #   （实测连杀三个，表现为"两个服务只能活一个"，不报错）。
    #   ⇒ 用 **AST** 判（不判字符串，注释骗不过）：函数体里有 `subprocess.Popen`、
    #   没有 `subprocess.run`；且设置 `PLOTPILOT_SKIP_ORPHAN_CLEANUP`。
    # [EN] ★ 2026-10-17 (measured): it used `subprocess.run(uvicorn …)` --
    # [EN] ① **not detached**: the moment it succeeds the function **never returns** (times out and
    # [EN] judges a perfectly alive service as failed); ② on failure only stdout was read while
    # [EN] uvicorn writes errors to stderr. And its built-in "orphan sweep" matches by the keyword
    # [EN] `uvicorn` -- it **kills a running PenShot** (three processes, no error reported).
    # [EN] ⇒ **AST** check (not strings; comments can't fool it): `subprocess.Popen` present,
    # [EN] `subprocess.run` absent, and `PLOTPILOT_SKIP_ORPHAN_CLEANUP` set.
    import ast as _ast
    try:
        _src = (APP / 'novelservices' / 'plotpilot_bridge.py').read_text(encoding='utf-8')
        _tree = _ast.parse(_src)
        _fn = next((n for n in _ast.walk(_tree)
                    if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                    and n.name == 'start_service'), None)
        _exprs: set[str] = set()
        _consts: set[str] = set()
        if _fn is not None:
            for _n in _ast.walk(_fn):
                if isinstance(_n, _ast.Call):
                    try:
                        _exprs.add(_ast.unparse(_n.func))
                    except Exception:                      # noqa: BLE001
                        pass
                if isinstance(_n, _ast.Constant) and isinstance(_n.value, str):
                    _consts.add(_n.value)
        _popen = 'subprocess.Popen' in _exprs
        _run = 'subprocess.run' in _exprs
        _skip = any('PLOTPILOT_SKIP_ORPHAN_CLEANUP' in c for c in _consts)
        ok('B2 ★★★ PlotPilot 的 `start_service` 是**非阻塞**的（`Popen` 不是 `run`）'
           '且跳过它自带的孤儿清理（那段按 `uvicorn` 关键字匹配，会把正在跑的 PenShot 杀掉）',
           _popen and not _run and _skip,
           f'Popen={_popen} run={_run} skip_env={_skip}')
    except Exception as _e:                                # noqa: BLE001
        ok('B2 ★★★ PlotPilot 的 `start_service` 是**非阻塞**的（`Popen` 不是 `run`）'
           '且跳过它自带的孤儿清理', False, f'读不了源码：{_e!r}')

    # ── T3：起停按钮必须**弹窗显示全套输出**（2026-10-17 用户报"点了没反应"）──
    # [EN] ── T3: Start/Stop must **open a dialog showing the full output** ──
    #
    # 旧实现的两个成因（都在源码里看得出来，用 AST 判、注释骗不过）：
    #   ① 桥没加载上时 `_BR is None` ⇒ **静默 return**，用户点什么都没发生；
    #   ② 输出只发到对话框背后的「消息」框 ⇒ 被天机盖住 = 看不到。
    # 判据：`show_global_settings` 里的两个起停处理器（`_svc_act` / `_ext_act`）**都**
    # 调用了 `_svc_output_dialog(...)` 并且 `page.show_dialog(dlg)`。
    # [EN] The two causes of the old code (both visible in the source; AST-checked so comments
    # [EN] can't fool it): ① silent `return` when the bridge failed to load; ② output only went
    # [EN] to the Messages box behind the dialog. Criterion: both handlers in
    # [EN] `show_global_settings` (`_svc_act` / `_ext_act`) call `_svc_output_dialog(...)` and
    # [EN] `page.show_dialog(dlg)`.
    try:
        import ast as _ast2
        _src2 = (APP / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
        _tree2 = _ast2.parse(_src2)

        def _calls_in(fn) -> set[str]:
            out: set[str] = set()
            for _n in _ast2.walk(fn):
                if isinstance(_n, _ast2.Call):
                    try:
                        out.add(_ast2.unparse(_n.func))
                    except Exception:                  # noqa: BLE001
                        pass
            return out

        _sgs = next((n for n in _ast2.walk(_tree2)
                     if isinstance(n, _ast2.FunctionDef)
                     and n.name == 'show_global_settings'), None)
        _acts = ([n for n in _ast2.walk(_sgs)
                  if isinstance(n, _ast2.FunctionDef)
                  and n.name in ('_svc_act', '_ext_act')]
                 if _sgs is not None else [])
        _missing = []
        for _a in _acts:
            _c = _calls_in(_a)
            if not any('_svc_output_dialog' in x for x in _c):
                _missing.append(_a.name + ' 没调用 _svc_output_dialog')
            if not any('page.show_dialog' in x for x in _c):
                _missing.append(_a.name + ' 没 page.show_dialog(dlg)')
        ok('T3 ★★★ 点「启动/停止服务」会**弹窗显示全套命令行输出**'
           '（`_svc_act` / `_ext_act` 都接上 `_svc_output_dialog` + `page.show_dialog`）'
           '—— 旧实现是"模块没加载就静默 return、输出发到对话框背后"，用户点了像没反应',
           len(_acts) >= 2 and not _missing,
           f'找到 {len(_acts)} 个处理器' + (f'；问题：{_missing}' if _missing else '；都接上了'))
    except Exception as _e:                                # noqa: BLE001
        ok('T3 ★★★ 点「启动/停止服务」会**弹窗显示全套命令行输出**', False,
           f'读不了源码：{_e!r}')

    # ══════════════════════════════════════════════════════════════════
    #  S. 天机那一页的**状态行会自己刷新**（2026-10-22 用户："我在天机里看到的是都没启动"）
    #
    #  ★ 事故形态：状态是**构建页面时读一次**、塞进静态 `mk_hint`，之后永不刷新。
    #    程序刚启动那几十秒服务还在拉起，用户这时打开天机 → 看到一张过期快照，
    #    而且**它永远不会变**，于是"都没启动"成了他看到的唯一事实。
    #
    #  ★ 这里判三件事，缺一不可：
    #    ① 状态是**可变控件**（`ft.Text` 存在里、能改），不是 `mk_hint(...)` 里的死字符串；
    #    ② 有一个**能反复调**的刷新函数，而且 `_svc_act` 结束后会调它；
    #    ③ 页面打开后会**自己轮询**（有终点）。
    #   ⚠ 只判"文案里有『正在拉起』"是假绿 —— 死字符串里也能写那几个字。
    #  [EN] S. Tianji's **status line refreshes itself**. The incident: the status was read once at
    #  [EN] build time and baked into a static `mk_hint`, so a user opening Tianji during the boot
    #  [EN] window saw a stale snapshot that **never changed**. Three things are judged, all required:
    #  [EN] ① it is a **mutable control** (a `ft.Text` that can be reassigned), not a dead string inside
    #  [EN] `mk_hint(...)`; ② a **repeatable** refresh function exists and `_svc_act` calls it when done;
    #  [EN] ③ the page **polls by itself** after opening (and terminates).
    #  [EN] ⚠ Judging only "the copy contains 'starting'" is fake-green -- a dead string can contain it.
    # ══════════════════════════════════════════════════════════════════
    try:
        _gui = (APP / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    except OSError:
        _gui = ''

    def _seg(a: str, b: str) -> str:
        i = _gui.find(a)
        if i < 0:
            return ''
        j = _gui.find(b, i + len(a))
        return _gui[i:j if j > 0 else len(_gui)]

    # ⚠⚠ 2026-10-22 第一版**太松**（反例法当场照出来）：它只查"控件被创建 + 被赋值"，
    #   而变异只要把页面里那一行换成 `mk_hint(...)` 死字符串，控件**照样被创建**
    #   （只是没被摆进页面）⇒ 判据照绿。**"控件存在"≠"控件在页面上"**。
    #   ⇒ 再加一条：`_svc_status_txt,` 必须作为**独立一行**出现在页面列表里。
    # [EN] ⚠⚠ The first version was **too loose** (the counterexample run exposed it immediately): it
    #   only checked "control created + assigned", while the mutation just swaps the page entry for a
    #   dead `mk_hint(...)` string -- the control is **still created** (just never placed) => green.
    #   **"Control exists" is not "control is on the page"**. So also require `_svc_status_txt,` to
    #   appear as a **line of its own** in the page list.
    _txt_lines = [ln.strip() for ln in _gui.splitlines()]
    ok('S1 ★★★ 服务状态是**可变控件**、而且**真的被摆进了页面**'
       '（不是 `mk_hint(...)` 里的死字符串，也不是建了却没放上去）',
       '_svc_status_txt = ft.Text(' in _gui
       and '_svc_status_txt.value =' in _gui
       and '_svc_status_txt,' in _txt_lines,
       f'控件行在页面里={"_svc_status_txt," in _txt_lines}')

    ok('S2 ★★★ 有一个**能反复调**的刷新函数（`_refresh_svc_status`），'
       '而不是"读一次就完"',
       'def _refresh_svc_status()' in _gui
       and '_svc_status_txt.update()' in _gui,
       '')

    ok('S3 ★★★ 「启动/停止服务」结束之后**会刷新状态行**'
       '（否则服务真起来了、上面还写着"还没启动" ⇒ 像按钮坏了）',
       '_refresh_svc_status()' in _seg('def _svc_act', '_svc_actions ='),
       '')

    ok('S4 ★★★ 页面打开后会**自己轮询**状态（服务是另一个进程起的，没有事件可听，'
       '只能问；而且用户打开天机的时机恰好是"正在拉起"那几十秒）',
       'def _poll_svc_status' in _gui
       and 'page.run_task(_poll_svc_status)' in _gui,
       '')

    # ⚠ 轮询**必须有终点**：设置页留下一个永不结束的定时器是另一种病。
    _poll = _seg('async def _poll_svc_status', 'def _svc_') or _seg('async def _poll_svc_status', 'return [')
    ok('S4b ★★ 轮询**有终点**（`for ... range(N)`，跑到就收工，不是 `while True`）',
       'while True' not in _poll and 'range(' in _poll, '')

    ok('S5 ★★ 状态行能分清**三种**（运行 / 正在拉起 / 没起）—— '
       '只说"没启动"会让用户以为要自己动手，而在拉起中他应该等几十秒',
       '◐ 正在拉起' in _gui and '○ 还没启动' in _gui and '● 正在运行' in _gui,
       '')

    # ══════════════════════════════════════════════════════════════════
    #  U 组：**左侧三个子页签**（2026-10-23，用户点名）—— 逻辑层
    # [EN] Group U: **three left-hand sub-tabs** (named by the user) -- logic layer
    # ══════════════════════════════════════════════════════════════════
    #  用户：「这个Tab进去之后**在左侧变成3个tab**，分别承载3个服务，
    #  而不是放到一整个Tab。然后在这3个左侧Tab上用一个**很小的图标**
    #  比如停止是 `-` 启动是 `*` 表示状态」。
    #
    #  ⚠ 这一组只判**接线与口径**（源码 + 行为）。"三个页签长什么样、点得动吗"
    #    是控件树的事，在 `tools/verify_svc_side_tabs.py` 里真起窗口量 ——
    #    两件事分开，是因为本脚本是**同步**跑的，塞不进 `ft.run`。
    #  [EN] This group judges **wiring and semantics only** (source + behaviour). "What the
    #  three tabs look like and whether they are clickable" is a control-tree fact, measured
    #  by actually opening a window in `tools/verify_svc_side_tabs.py` -- split because this
    #  script runs synchronously and cannot host `ft.run`.
    print('\n── U 左侧三个子页签（逻辑层）──')

    ok('U1 ★★★ 这一页自己带布局（打了 `_tab_ready` 标记），**不再被 `mk_tab_content` 二次包裹**'
       '（否则变成"固定宽度里塞一个更宽的 Row"：右边被裁、滚动条压内容）',
       '_side._tab_ready = True' in src
       and 'def _wrap_tab_content(' in src
       and "getattr(controls, '_tab_ready', False)" in src,
       '')

    ok('U2 ★★★ 三个服务**各自一段**装进左侧页签（不是一条长页面）',
       "('mumu', t('MuMuAINovel')" in src
       and "('pp', t('PlotPilot')" in src
       and "('ps', t('PenShot')" in src,
       '')

    ok('U3 ★★★ 状态符就是用户点名的两个：**停止 `-`、启动 `*`**',
       "'*' if _svc_ok.get(key) else '-'" in src,
       '')

    ok('U4 ★★★ PlotPilot 与 PenShot **都有「刷新状态」按钮**'
       '（用户点名；MuMu 那一页早就有，三块长得不一样会让人以为这两块不能刷）',
       "mk_btn(t('刷新状态')" in src and src.count("mk_btn(t('刷新状态')") >= 3,
       f"出现 {src.count(chr(39)+'刷新状态'):d} 处")

    ok('U5 ★★★ 那颗按钮刷的是**三座一起**（小灯 + 三页的状态文字），'
       '不是只刷自己那一行（否则用户得点三次）',
       'async def _refresh_all_svc' in src
       and '_paint_dots()' in src
       and 'await _probe_all()' in src,
       '')

    _poll_seg = _seg('async def _poll_svc_status', 'def _sv(')
    ok('U6 ★★★ 页面打开后**自己轮询**，且轮的是三座、不是只看 MuMu 一行'
       '（否则会出现"灯是 `-`、里面写着正在运行"—— 那种矛盾不报错）',
       'await _refresh_all_svc()' in _poll_seg,
       '')

    ok('U7 ★★★ 探测走**线程池**（`service_status` 是阻塞 urllib，三座串联 ≈ 3 秒卡界面；'
       '点一次"刷新"整窗不动，比状态过期更糟）',
       'asyncio.to_thread(_probe_svc' in src,
       '')

    # U8 **口径一致性**：三个服务的"有没有在跑"必须只来自**同一份缓存**
    #   ⚠ 各探各的会出现"灯 `*`、页里写着还没启动" —— 而那种矛盾**不报错**。
    # [EN] U8 **Single source of truth**: "is it running" for all three must come from
    # **one cache**. ⚠ Probing separately yields "lamp `*`, body says not started" -- a
    # contradiction that **raises nothing**.
    _line_seg = _seg('def _svc_line(', 'def _refresh_pp_status(')
    ok('U8 ★★★ 三处的"在不在"读的是**同一份探测结果**（`_svc_ok`），'
       '谁都不自己再探一次（各探各的会出现"灯亮着、里面写着没启动"）',
       '_svc_ok.get(key)' in _line_seg and 'service_status(' not in _line_seg,
       f'自己探测={("service_status(" in _line_seg)}')

    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n外部创作服务验证：{n - len(bad)}/{n}')
    for c in REPORT['checks']:
        print(f'  {"✓" if c["ok"] else "✗"} {c["name"]}'
              + (f' | {c["detail"][:120]}' if c['detail'] else ''))
    print('报告 ->', OUT.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
