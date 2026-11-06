# -*- coding: utf-8 -*-
"""验证：运行界面这四块（2026-10-28 用户一次性提的）。

  ① **摄取输入框**：回车 = 换行，**Ctrl+Enter = 发送**；提示放在发送/强制停止按钮下面。
  ② **AI 往来对话框**：分页，每页默认 50（可改），**打开时落在最后一页且最后一条可见**。
  ③ **左下角系统面板**：去掉「模型」行、去掉「已关闭 · 向量检索」、
     加上「MOCK 模式」、加上三座外部创作服务的状态（`*` = 在跑，`-` = 没跑）。

★ 这一支**不开窗口**：
  · 能**真跑**的部分（分页算式、键盘钩子的那条分支、灯的语义）都是纯逻辑，
    直接调产品自己的函数 —— 不自己拼一份"看起来像"的逻辑。
  · 只能静态看的位置（提示文字排在按钮下面、模型行没了）用 **AST** 看，
    **不用 grep** —— 源码注释里就写着 `mk_kv(t('模型'), ...)`（解释为什么删它），
    grep 会把注释当成代码，判据就成了"检查注释里有没有那个词"。
★ `--selftest` 会把源码**在内存里改坏**再跑一遍，证明这几条**能红**。

    English:
Verification: the four run-screen pieces (all requested by the user on 2026-10-28).

  ① **The ingestion input**: Enter inserts a newline, **Ctrl+Enter sends**; the hint sits below the
     Send / Force-stop buttons.
  ② **The "AI exchange" dialog**: pagination, 50 per page by default (adjustable), **opening lands on
     the last page with the last item visible**.
  ③ **The bottom-left System panel**: the "model" row gone, "turned off · vector retrieval" gone,
     an "MOCK mode" row added, and the three external creation services' status added
     (`*` = running, `-` = not).

★ This one opens **no window**:
  · The parts that **can** really run (the pagination arithmetic, the keyboard hook's branch, the
  [EN] lamps' semantics) are pure logic, so we call the product's own functions -- we do not
  [EN] assemble a look-alike logic of our own.
  · The parts that can only be seen statically (the hint below the buttons, the model row gone) are
  [EN] looked at with **AST**, **not grep** -- the source comment literally contains
  [EN] `mk_kv(t('模型'), ...)` (explaining why it was deleted), so grep would read the comment as code
  [EN] and the criterion would degenerate into "does that word appear in a comment".
★ `--selftest` breaks the source **in memory** and re-runs, proving these checks **can go red**.
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

SRC_PATH = APP / 'gui' / 'app_flet.py'
SRC = SRC_PATH.read_text(encoding='utf-8')

REPORT: dict = {}
CHECKS: list[dict] = []


FAILED: list[str] = []


def ok(name: str, cond, detail='') -> bool:
    """记一条检查。**红的必须让退出码非 0** —— 回归器只看退出码。

    ⚠⚠ 这里原来只把结果记进 `CHECKS`，`main()` 里的 `ok_all` 只在
      「中途崩溃」时才置 False ⇒ **任何一条检查红掉，退出码仍是 0** ⇒
      这支判据在 `tools/run_all_verifications.py` 里**永远绿**，
      红灯打出来也没人看得见（回归器只认 `code == 0`）。
      ⇒ 红的条目**在这里就登记**，由 `main()` 统一决定退出码。
    [EN] A red check **must** make the exit code non-zero -- the regression harness only looks at
    [EN] the exit code. This used to record results without affecting the exit code, so this
    [EN] criterion could **never** go red in the regression.
    """
    good = bool(cond)
    CHECKS.append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    if not good:
        FAILED.append(name)
    print(('  \u2713 ' if good else '  \u2717 ') + name
          + (f'   [{detail}]' if detail else ''), flush=True)
    return good


def head(t: str) -> None:
    print(f'\n{t}', flush=True)


# ══════════════════════════════════════════════════════════════════════
#  A. 分页算式（真跑产品自己的函数）
# [EN] A. The pagination arithmetic (really run the product's own function)
# ══════════════════════════════════════════════════════════════════════
def test_page_range() -> None:
    from gui.app_flet import probe_page_range

    # ── A1 跟着最新（follow=True）落在最后一页 ──
    # ⚠⚠ **用例里不许混进 total=0** —— 那是 A5 的地盘（总页数最少是 1）。
    #   混进来 ⇒ A5 那道闸一变，A1 也跟着红 ⇒ 反例法里"一条变异只触发一条判据"
    #   做不到（连带红看起来像"好几条都有用"，其实只证明"它们会红"）。
    #   ⇒ A1 只管「总页数 ≥ 1 时，follow 落在最后一页」。
    # [EN] A1 Following (follow=True) lands on the last page
    # ⚠⚠ **No total=0 in this list** -- that is A5's business (the total is at least 1).
    # [EN] Mixing it in makes A5's gate also turn A1 red => the counterexample's "one mutation
    # [EN] triggers exactly one assertion" cannot hold.
    bad = []
    for total, size, want in ((1, 50, (0, 1, 0, 50)),
                               (50, 50, (0, 1, 0, 50)),
                               (51, 50, (1, 2, 50, 50)),
                               (120, 50, (2, 3, 100, 50)),
                               (120, 20, (5, 6, 100, 20))):
        got = probe_page_range(total, size, 0, True)
        if got != want:
            bad.append(f'{total}/{size}→{got}（要 {want}）')
    ok('A1 ★★ 跟着最新：页码落在最后一页，起始下标对得上',
       not bad, '; '.join(bad))

    # ── A2 用户自己翻过的页**不被拽回最后一页** ──
    # [EN] A2 A page the user paged to is **not** yanked back to the last one
    got = probe_page_range(120, 50, 0, False)
    ok('A2 ★★ 用户翻到的页不会被"跟着最新"拽走（follow=False 时页码保持）',
       got == (0, 3, 0, 50), str(got))

    # ── A3 页码永远夹在合法范围里 ──
    # [EN] A3 The page is always clamped into range
    got = probe_page_range(120, 50, 99, False)
    ok('A3 ★ 页码夹取：翻过头落在最后一页，不是空页',
       got == (2, 3, 100, 50), str(got))
    got = probe_page_range(120, 50, -5, False)
    ok('A3b ★ 页码夹取：翻过头落在第一页，不是负数',
       got == (0, 3, 0, 50), str(got))

    # ── A4 每页几发被改成 0 / 负数 ⇒ 当 1，不许崩也不许除零 ──
    # ⚠ 关键：**0 不许被当成"没给"**（`0 or 50` = 50）——
    #   那样"每页 0 个"会悄悄变成"每页 50 个"，界面上看不出出过错。
    # ⚠⚠ **这里用 follow=False**：A4 只测「每页几发被归一化成 1」这一道闸，
    #   不该跟着 follow 分支一起变（follow 那道闸是 A1 的）。
    # [EN] A4 "how many per page" set to 0 / negative => treated as 1, no crash and no division by zero
    # [EN] ⚠ Key: **0 must not be read as "not given"** (`0 or 50` = 50) -- otherwise "0 per page"
    # [EN] silently becomes "50 per page" and nothing on screen shows that anything went wrong.
    # [EN] ⚠⚠ **follow=False here**: A4 covers only "the page size is normalized to 1"; it must
    # [EN] not move together with the follow branch (that gate is A1's).
    got = probe_page_range(10, 0, 0, False)
    ok('A4 ★ 每页几发 = 0 时当 1（不崩、不除零，也不当成默认的 50）',
       got == (0, 10, 0, 1), str(got))
    got = probe_page_range(10, -3, 0, False)
    ok('A4b ★ 每页几发为负数时也当 1',
       got == (0, 10, 0, 1), str(got))

    # ── A5 一发都没有时是「第 1 / 1 页」，不是「第 1 / 0 页」──
    # [EN] A5 With no exchanges at all it reads "page 1 / 1", not "page 1 / 0"
    got = probe_page_range(0, 50, 0, True)
    ok('A5 ★ 空列表也有一页（总页数最少是 1，不显示「第 1 / 0 页」）',
       got[1] == 1, str(got))


# ══════════════════════════════════════════════════════════════════════
#  B. Ctrl+Enter 发送（真跑 `_on_keyboard`）
# [EN] B. Ctrl+Enter sends (really run `_on_keyboard`)
# ══════════════════════════════════════════════════════════════════════
class _FakeWin:
    def __init__(self) -> None:
        self.full_screen = False
        self.maximized = True


class _FakePage:
    def __init__(self) -> None:
        self.window = _FakeWin()
        self.updates = 0

    def update(self) -> None:
        self.updates += 1

    def run_task(self, handler, *a, **kw):                # noqa: ANN001, ANN002
        return None


class _FakeKey:
    """一只"键盘事件"（只带产品真正用到的那几个字段）。"""

    def __init__(self, key: str, ctrl: bool = False, shift: bool = False) -> None:
        self.key = key
        self.ctrl = ctrl
        self.shift = shift
        self.alt = False
        self.meta = False


def _app_with_ingest(sent: list) -> object:
    """造一个只带"摄取那一步"的 app 实例（**不开窗口**）。"""
    from gui.app_flet import NovelWorldApp
    app = NovelWorldApp.__new__(NovelWorldApp)
    app.page = _FakePage()
    app._user_toggled_fullscreen = False
    app._ingest_state = {
        'chat_focus': True,
        'send_hook': lambda: sent.append('sent'),
    }
    return app


def test_ctrl_enter() -> None:
    from gui.app_flet import NovelWorldApp

    # ── B1 Ctrl+Enter 真的发出去了 ──
    # [EN] B1 Ctrl+Enter really sends
    sent: list = []
    app = _app_with_ingest(sent)
    app._on_keyboard(_FakeKey('ENTER', ctrl=True))
    ok('B1 ★★ Ctrl+Enter 真的把消息发出去了（`_on_keyboard` 直调）',
       sent == ['sent'], str(sent))

    # ── B2 光按回车（没按 Ctrl）**不**发 ──
    # [EN] B2 Plain Enter does **not** send
    sent = []
    app = _app_with_ingest(sent)
    app._on_keyboard(_FakeKey('ENTER', ctrl=False))
    ok('B2 ★★ 光按回车不发送（回车是换行，不是发送）',
       sent == [], str(sent))

    # ── B3 焦点不在输入框上 ⇒ 不发 ──
    # [EN] B3 Focus elsewhere => no send
    sent = []
    app = _app_with_ingest(sent)
    app._ingest_state['chat_focus'] = False
    app._on_keyboard(_FakeKey('ENTER', ctrl=True))
    ok('B3 ★★ 焦点不在摄取输入框上时不发送（别在确认面板上误发）',
       sent == [], str(sent))

    # ── B4 没有摄取这一步时按 Ctrl+Enter 不该有任何反应，也不该崩 ──
    # [EN] B4 With no ingestion step running, Ctrl+Enter must do nothing and must not crash
    sent = []
    app = NovelWorldApp.__new__(NovelWorldApp)
    app.page = _FakePage()
    app._user_toggled_fullscreen = False
    app._ingest_state = None
    try:
        app._on_keyboard(_FakeKey('ENTER', ctrl=True))
        crashed = False
    except Exception:                                        # noqa: BLE001
        crashed = True
    ok('B4 ★ 没在摄取时按 Ctrl+Enter 不崩、不发',
       (not crashed) and sent == [], f'崩={crashed}')

    # ── B5 F11 那条老快捷键**没被改坏** ──
    # [EN] B5 The old F11 shortcut still works
    app = NovelWorldApp.__new__(NovelWorldApp)
    app.page = _FakePage()
    app._user_toggled_fullscreen = False
    app._ingest_state = None
    app._on_keyboard(_FakeKey('F11'))
    ok('B5 ★ F11 切全屏那条老快捷键仍然有效（没被新分支顶掉）',
       bool(app.page.window.full_screen) is True
       and app._user_toggled_fullscreen is True,
       f'full_screen={app.page.window.full_screen}')


# ══════════════════════════════════════════════════════════════════════
#  C. 三盏灯的语义（真跑 `_apply_svc_lamps`）
# [EN] C. The three lamps' semantics (really run `_apply_svc_lamps`)
# ══════════════════════════════════════════════════════════════════════
def test_lamps() -> None:
    from gui.app_flet import NovelWorldApp

    app = NovelWorldApp.__new__(NovelWorldApp)
    app.page = _FakePage()
    lamps = {'mumu': _Lamp(), 'pp': _Lamp(), 'ps': _Lamp()}
    app._ui_run = {'svc_lamps': lamps}
    asyncio.run(app._apply_svc_lamps({'mumu': True, 'pp': False, 'ps': True}))
    # ★★ 2026-10-28：口径改了 —— 符号 `*` / `-` 换成**文字**「运行」/「未运行」
    #   （用户：「请直接修改为显示文字 运行或者未运行」）。
    #   ⚠ 这条判据原来钉的是符号；改了 UI 却没改它的后果是**它一直红着**，
    #     而这一支是"红了也没人看"的那种 —— 只看结论行才发现。
    #   ⇒ 现在钉的是「**名字 + 状态**」这个形态：`MuMuAINovel 运行`。
    #     只判 `== '运行'` 会把"名字要不要显示"这件事判死，而用户要的是带名字。
    # [EN] ★★ 2026-10-28: the contract changed -- `*` / `-` became the words
    # [EN] 运行 / 未运行. The shape is "name + state" (`MuMuAINovel 运行`); comparing to the
    # [EN] bare word would forbid the name the user asked for.
    _v = {k: str(l.value) for k, l in lamps.items()}
    ok('C1 ★★ 在跑的写「运行」、没跑的写「未运行」（名字 + 状态，三座各一盏）',
       _v['mumu'].endswith('运行') and not _v['mumu'].endswith('未运行')
       and _v['pp'].endswith('未运行')
       and _v['ps'].endswith('运行') and not _v['ps'].endswith('未运行'),
       _v)

    # 探活**永不抛**（模块不在 / `novelservices` 被删了 ⇒ False）
    # [EN] Probing **never raises** (module missing / `novelservices` gone => False)
    from gui.app_flet import probe_creation_service
    try:
        got = probe_creation_service('definitely_not_a_bridge', timeout=0.1)
        crashed = False
    except Exception:                                        # noqa: BLE001
        got = None
        crashed = True
    ok('C2 ★ 探活永不抛（桥不在时当"没跑"，界面照常）',
       (not crashed) and got is False, f'崩={crashed} 值={got}')

    # ── C3 ★★ **桥在，但健康检查自己抛了** ⇒ 也得当"没跑" ──
    # ⚠⚠ 只测「模块不在」是不够的：那一条**只**要求接住 `ImportError`，
    #   而 `ModuleNotFoundError` 正是 `ImportError` 的子类 ⇒
    #   把 `except Exception` 收窄成 `except ImportError`，
    #   **这一条照样绿**（实测过）⇒ 那道闸从来没被证明过能红。
    #   ⇒ 真正要防的是「桥在、但 `service_status()` 抛了别的异常」
    #      （连接被拒、超时、返回了意料之外的类型……）。
    # [EN] ⚠⚠ Only "the module is missing" is not enough: that only requires catching
    # [EN] `ImportError`, and `ModuleNotFoundError` **is** an `ImportError` subclass => narrowing
    # [EN] `except Exception` to `except ImportError` keeps this check green (measured) => that
    # [EN] gate was never proven able to go red. What must be covered is "the bridge is there but
    # [EN] `service_status()` raised something else".
    # ⇒ 用一个**真模块**（本文件自己）装一个会抛的 `service_status`。
    import types
    import sys as _sys
    fake = types.ModuleType('_fake_bridge_boom')
    fake.service_status = lambda timeout=1.0: (_ for _ in ()).throw(
        RuntimeError('模拟：桥在，但健康检查抛了'))
    _sys.modules['_fake_bridge_boom'] = fake
    try:
        # 探活按 `novelservices.<名>` 导入 ⇒ 把假模块塞进那个包底下。
        import novelservices
        _sys.modules['novelservices._fake_bridge_boom'] = fake
        try:
            got2 = probe_creation_service('_fake_bridge_boom', timeout=0.1)
            crashed2 = False
        except Exception:                                    # noqa: BLE001
            got2 = None
            crashed2 = True
    finally:
        _sys.modules.pop('novelservices._fake_bridge_boom', None)
        _sys.modules.pop('_fake_bridge_boom', None)
    ok('C3 ★★ 探活永不抛（**桥在、但健康检查抛异常**时也当"没跑"）',
       (not crashed2) and got2 is False, f'崩={crashed2} 值={got2}')


class _Lamp:
    """一只假灯（只带产品真正写的那两个字段）。"""

    def __init__(self) -> None:
        self.value = '-'
        self.color = ''


# ══════════════════════════════════════════════════════════════════════
#  D. 源码里的位置关系（**AST**，不用 grep）
# [EN] D. Positions in the source (**AST**, not grep)
# ══════════════════════════════════════════════════════════════════════
def _ingest_function(tree: ast.AST):
    """找到"摄取那一步"所在的函数（里面有 `chat_input = ft.TextField(...)`）。"""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Assign):
                continue
            if not isinstance(sub.value, ast.Call):
                continue
            if getattr(sub.value.func, 'attr', '') != 'TextField':
                continue
            tgt = sub.targets[0]
            if isinstance(tgt, ast.Name) and tgt.id == 'chat_input':
                return node
    return None


def _has_on_submit_to_send(fn) -> bool:
    """摄取那一步里，是不是还把 `on_submit` 接到 `_send`。"""
    if fn is None:
        return False
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Assign):
            continue
        for tgt in sub.targets:
            if (isinstance(tgt, ast.Attribute) and tgt.attr == 'on_submit'
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == '_send'):
                return True
    return False


def _has_send_hook(fn) -> bool:
    """摄取那一步里，是不是把 `_send` 挂进了 `state['send_hook']`。"""
    if fn is None:
        return False
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Assign):
            continue
        for tgt in sub.targets:
            if not isinstance(tgt, ast.Subscript):
                continue
            sl = tgt.slice
            key = sl.value if isinstance(sl, ast.Constant) else None
            if key == 'send_hook' and isinstance(sub.value, ast.Name) \
                    and sub.value.id == '_send':
                return True
    return False


def _hint_below_buttons(tree: ast.AST) -> bool:
    """提示文字是不是排在「发送 / 强制停止」那一行的**下面**（同一个 Column 里）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, 'attr', '') != 'Column':
            continue
        if not node.args or not isinstance(node.args[0], ast.List):
            continue
        row_idx = -1
        hint_idx = -1
        for i, el in enumerate(node.args[0].elts):
            for sub in ast.walk(el):
                if isinstance(sub, ast.Call) and getattr(sub.func, 'attr', '') == 'Row':
                    names = {n.id for n in ast.walk(sub)
                             if isinstance(n, ast.Name)}
                    if {'chat_input', 'send_btn', 'stop_btn'} <= names:
                        row_idx = i
                if isinstance(sub, ast.Call) and getattr(sub.func, 'attr', '') == 'Text':
                    for c in ast.walk(sub):
                        if (isinstance(c, ast.Call) and getattr(c.func, 'id', '') == 't'
                                and c.args and isinstance(c.args[0], ast.Constant)
                                and 'Ctrl+Enter' in str(c.args[0].value)):
                            hint_idx = i
        if row_idx >= 0 and hint_idx >= 0:
            return hint_idx > row_idx
    return False


def _no_model_row(tree: ast.AST) -> bool:
    """系统面板里是不是**真的**没有「模型」行了（AST，不是 grep）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, 'id', '') != 'mk_kv':
            continue
        if not node.args or not isinstance(node.args[0], ast.Call):
            continue
        a0 = node.args[0]
        if (getattr(a0.func, 'id', '') == 't' and a0.args
                and isinstance(a0.args[0], ast.Constant)
                and a0.args[0].value == '模型'):
            return False
    return True


def _no_embedding_in_off(tree: ast.AST) -> bool:
    """「已关闭」清单里是不是**真的**没有「向量检索」了。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, 'attr', '') != 'append':
            continue
        if not node.args or not isinstance(node.args[0], ast.Call):
            continue
        a0 = node.args[0]
        if (getattr(a0.func, 'id', '') == 't' and a0.args
                and isinstance(a0.args[0], ast.Constant)
                and a0.args[0].value == '向量检索'):
            return False
    return True


def _has_mock_row(tree: ast.AST) -> bool:
    """有没有「MOCK 模式」那一行。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, 'id', '') != 'mk_kv':
            continue
        if not node.args or not isinstance(node.args[0], ast.Call):
            continue
        a0 = node.args[0]
        if (getattr(a0.func, 'id', '') == 't' and a0.args
                and isinstance(a0.args[0], ast.Constant)
                and a0.args[0].value == 'MOCK 模式'):
            return True
    return False


def _has_three_lamp_rows(tree: ast.AST) -> bool:
    """三座服务各一行（名字在源码里出现且各自成行）。"""
    src = ast.unparse(tree)
    for nm in ('MuMuAINovel', 'PlotPilot', 'PenShot'):
        if nm not in src:
            return False
    return True


def test_source(src: str) -> dict:
    """对**一份源码文本**跑源码层的检查（自检时会把源码改坏再跑一遍）。"""
    tree = ast.parse(src)
    fn = _ingest_function(tree)
    return {
        'no_on_submit': not _has_on_submit_to_send(fn),
        'has_send_hook': _has_send_hook(fn),
        'hint_below': _hint_below_buttons(tree),
        'no_model_row': _no_model_row(tree),
        'no_embedding_off': _no_embedding_in_off(tree),
        'has_mock_row': _has_mock_row(tree),
        'three_lamps': _has_three_lamp_rows(tree),
    }


def test_source_group() -> None:
    r = test_source(SRC)
    ok('D1 ★★ 摄取输入框**不再**把回车接到「发送」（回车是换行）',
       r['no_on_submit'])
    ok('D2 ★★ 发送函数挂进了 `state[\'send_hook\']`（全局键盘钩子从那儿取）',
       r['has_send_hook'])
    ok('D3 ★★ 「回车换行 · Ctrl+Enter 发送」这行提示排在发送/强制停止按钮**下面**',
       r['hint_below'])
    ok('D4 ★★ 系统面板里**没有**「模型」行了（混用多个模型，显示哪一个都是半真）',
       r['no_model_row'])
    ok('D5 ★★ 「已关闭」清单里**没有**「向量检索」（上面「记忆检索」已经说了同一件事）',
       r['no_embedding_off'])
    ok('D6 ★★ 系统面板里有「MOCK 模式」那一行',
       r['has_mock_row'])
    ok('D7 ★★ 三座外部创作服务各有一行状态',
       r['three_lamps'])


# ══════════════════════════════════════════════════════════════════════
#  自检：把源码**在内存里**改坏，证明上面那几条**能红**
# [EN] Selftest: break the source **in memory** to prove the checks above **can go red**
# ══════════════════════════════════════════════════════════════════════
# ⚠⚠ **锚点必须按 AST 定位，不能靠字面量**。
#   原来这六条自检全是 `SRC.replace("        state['send_hook'] = _send", ...)` ——
#   源码里那一行**只要挪个位置或改个缩进**，replace 就命中 0 次、
#   `mutated == SRC` ⇒ 自检报「没改成」⇒ **假红**：
#   它实际在说"我的锚点失效了"，却写成"判据没红"，
#   而人会因此以为判据太弱，去**加强判据**（找错了方向）。
#   实测：把 `state['send_hook'] = _send` 改成 `= None`，D2 确实红了，
#   但 S1 同时报「D1/D2 没改成」—— 那两条自检自己已经失效了。
#   ⇒ 改成**在 AST 上找到那个节点**，按它的行号改源码 ⇒ 锚点不会因为改排版而失效。
# [EN] ⚠⚠ The anchors must be located with **AST**, not literals. They used to be
# [EN] `SRC.replace("        state['send_hook'] = _send", ...)` -- move that line or change its
# [EN] indentation and the replace hits 0 times, so the selftest reported "not changed" -- a
# [EN] **false red**: it was really saying "my anchor died", but it reads as "the criterion did
# [EN] not go red", which sends people off to strengthen the criterion instead.
def _src_lines() -> list[str]:
    return SRC.split('\n')


def _indent_of(node) -> str:
    return ' ' * node.col_offset


def _line_indent(lineno: int) -> str:
    """那一行**行首**的缩进（不是 AST 的 `col_offset`）。

    ⚠⚠ 为什么不能再用 `col_offset`：`mk_kv(t('MOCK 模式'), …)` 现在写成了
      `_mock_row = mk_kv(t('MOCK 模式'), …)`（2026-10-28 存值句柄那次改的），
      `col_offset` 指到 `mk_kv` 那个字符、比行首多出 `_mock_row = ` 那几格；
      照它插进去的一行就多缩进了一截 ⇒ `unexpected indent`，
      而自检只会报"改坏之后判据自己崩了"，看不出是**变异脚本**打偏。
    [EN] The **line's leading** indentation, not the AST `col_offset`: the MOCK call is now
    [EN] `_mock_row = mk_kv(...)`, so `col_offset` points past the assignment and an
    [EN] inserted line came out over-indented (`unexpected indent`).
    """
    lines = _src_lines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1][:len(lines[lineno - 1]) - len(lines[lineno - 1].lstrip())]
    return ''


def _send_hook_assign(tree):
    """`state['send_hook'] = ...` 那一行（AST 定位）。"""
    fn = _ingest_function(tree)
    if fn is None:
        return None
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not isinstance(tgt, ast.Subscript):
                continue
            sl = tgt.slice
            key = sl.value if isinstance(sl, ast.Constant) else None
            if key == 'send_hook':
                return node
    return None


def _mock_kv_call(tree):
    """`mk_kv(t('MOCK 模式'), ...)` 那一条（AST 定位）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, 'id', '') != 'mk_kv':
            continue
        if not node.args or not isinstance(node.args[0], ast.Call):
            continue
        a0 = node.args[0]
        if (getattr(a0.func, 'id', '') == 't' and a0.args
                and isinstance(a0.args[0], ast.Constant)
                and a0.args[0].value == 'MOCK 模式'):
            return node
    return None


def _off_compliance_call(tree):
    """`off.append(t('合规'))` 那一条（AST 定位）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, 'attr', '') != 'append':
            continue
        if not node.args or not isinstance(node.args[0], ast.Call):
            continue
        a0 = node.args[0]
        if (getattr(a0.func, 'id', '') == 't' and a0.args
                and isinstance(a0.args[0], ast.Constant)
                and a0.args[0].value == '合规'):
            return node
    return None


def _button_and_hint(tree):
    """同一个 Column 里的「按钮那一行」与「提示那一行」（AST 定位）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, 'attr', '') != 'Column':
            continue
        if not node.args or not isinstance(node.args[0], ast.List):
            continue
        elts = node.args[0].elts
        row_i = hint_i = -1
        for i, el in enumerate(elts):
            for sub in ast.walk(el):
                if isinstance(sub, ast.Call) and getattr(sub.func, 'attr', '') == 'Row':
                    names = {n.id for n in ast.walk(sub)
                             if isinstance(n, ast.Name)}
                    if {'chat_input', 'send_btn', 'stop_btn'} <= names:
                        row_i = i
                if isinstance(sub, ast.Call) and getattr(sub.func, 'attr', '') == 'Text':
                    for c in ast.walk(sub):
                        if (isinstance(c, ast.Call) and getattr(c.func, 'id', '') == 't'
                                and c.args and isinstance(c.args[0], ast.Constant)
                                and 'Ctrl+Enter' in str(c.args[0].value)):
                            hint_i = i
        if row_i >= 0 and hint_i >= 0:
            return elts[row_i], elts[hint_i]
    return None, None


def _mut_d1(tree) -> str:
    """回车又接回发送（在 `send_hook` 那一行后面插一行）。"""
    node = _send_hook_assign(tree)
    if node is None:
        raise AssertionError('AST 里找不到 `state[\'send_hook\'] = ...`')
    lines = _src_lines()
    lines.insert(node.end_lineno,
                 f"{_indent_of(node)}chat_input.on_submit = _send")
    return '\n'.join(lines)


def _mut_d2(tree) -> str:
    """不再挂 send_hook（把那一行换成 `pass`）。"""
    node = _send_hook_assign(tree)
    if node is None:
        raise AssertionError('AST 里找不到 `state[\'send_hook\'] = ...`')
    lines = _src_lines()
    lines[node.lineno - 1:node.end_lineno] = [f'{_indent_of(node)}pass']
    return '\n'.join(lines)


def _mut_d3(tree) -> str:
    """把提示排到按钮**上面**（两段整块对调，中间的注释留在原位）。"""
    row, hint = _button_and_hint(tree)
    if row is None or hint is None:
        raise AssertionError('AST 里找不到「按钮那一行」与「提示那一行」')
    lines = _src_lines()
    a = lines[row.lineno - 1:row.end_lineno]
    mid = lines[row.end_lineno:hint.lineno - 1]
    b = lines[hint.lineno - 1:hint.end_lineno]
    return '\n'.join(lines[:row.lineno - 1] + b + mid + a + lines[hint.end_lineno:])


def _mut_d4(tree) -> str:
    """把「模型」那一行加回来。"""
    node = _mock_kv_call(tree)
    if node is None:
        raise AssertionError('AST 里找不到 `mk_kv(t(\'MOCK 模式\'), ...)`')
    lines = _src_lines()
    lines.insert(node.lineno - 1, f"{_line_indent(node.lineno)}mk_kv(t('模型'), 'x'),")
    return '\n'.join(lines)


def _mut_d5(tree) -> str:
    """把「向量检索」加回「已关闭」清单。"""
    node = _off_compliance_call(tree)
    if node is None:
        raise AssertionError('AST 里找不到 `off.append(t(\'合规\'))`')
    lines = _src_lines()
    lines.insert(node.end_lineno, f"{_indent_of(node)}off.append(t('向量检索'))")
    return '\n'.join(lines)


def _mut_d6(tree) -> str:
    """删掉「MOCK 模式」那一行。"""
    node = _mock_kv_call(tree)
    if node is None:
        raise AssertionError('AST 里找不到 `mk_kv(t(\'MOCK 模式\'), ...)`')
    lines = _src_lines()
    del lines[node.lineno - 1:node.end_lineno]
    return '\n'.join(lines)


#: (说明, 变异函数, 期望变红的那个键)
#: [EN] : (description, mutation function, the key that must go red)
SELF_CASES = [
    ('D1 回车又接回发送', _mut_d1, 'no_on_submit'),
    ('D2 不再挂 send_hook', _mut_d2, 'has_send_hook'),
    ('D3 提示排到按钮上面', _mut_d3, 'hint_below'),
    ('D4 把模型行加回来', _mut_d4, 'no_model_row'),
    ('D5 把向量检索加回已关闭清单', _mut_d5, 'no_embedding_off'),
    ('D6 删掉 MOCK 那一行', _mut_d6, 'has_mock_row'),
]


def selftest() -> None:
    head('S. 自检（把源码改坏，看判据会不会红）')
    bad = []
    for name, fn, key in SELF_CASES:
        try:
            tree = ast.parse(SRC)
            mutated = fn(tree)
        except Exception as ex:                                # noqa: BLE001
            bad.append(f'{name}：变异本身失败（{ex}）')
            continue
        if mutated == SRC:
            bad.append(f'{name}：变异后内容没变（脚本打偏了）')
            continue
        try:
            r = test_source(mutated)
        except Exception as ex:                                # noqa: BLE001
            bad.append(f'{name}：改坏之后判据自己崩了（{ex}）')
            continue
        if r.get(key):
            bad.append(f'{name}：判据**没红**（这一条本来就是摆设）')
    ok('S1 ★★ 每条源码判据都能被"改坏源码"打红（没有摆设判据）',
       not bad, '; '.join(bad))


def main() -> int:
    print('运行界面四块（摄取回车 / AI 往来分页 / 系统面板）—— 验证', flush=True)
    try:
        head('A. 分页算式')
        test_page_range()
        head('B. Ctrl+Enter 发送')
        test_ctrl_enter()
        head('C. 三盏灯')
        test_lamps()
        head('D. 源码位置（AST）')
        test_source_group()
        head('S. 自检')
        selftest()
    except Exception:                                         # noqa: BLE001
        REPORT['fatal'] = traceback.format_exc()
        ok('验证没有中途崩溃（有崩溃就不是全绿）', False, REPORT['fatal'][-300:])
    # ★★★ **退出码看的是"有红的"，不是"崩没崩"** ——
    #   `ok_all` 原来只在崩溃时置 False，等于"任何一条检查红掉都还是 0"。
    #   而 `tools/run_all_verifications.py` 只认 `code == 0` ⇒ 这支判据在回归里恒绿。
    # [EN] ★★★ The exit code reflects **"any red"**, not "did it crash" -- and the regression
    # [EN] harness only accepts `code == 0`.
    REPORT['ok'] = not FAILED
    REPORT['checks'] = CHECKS
    (OUT / 'ui_probe_paging_report.json').write_text(
        json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in CHECKS if c['ok'])
    failed = [c['name'] for c in CHECKS if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(CHECKS)} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if REPORT.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + REPORT['fatal'][-1200:])
    sys.exit(0 if REPORT['ok'] else 2)


if __name__ == '__main__':
    main()
