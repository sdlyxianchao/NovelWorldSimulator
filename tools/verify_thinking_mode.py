# -*- coding: utf-8 -*-
"""验证：**思考模式总开关**（`LLM_THINKING_MODE`，2026-10-18）。

为什么要有这一支
----------------
新版 `deepseek-flash`（滚动别名）**默认输出思考内容**：思考按输出计费，而且和正文
**抢同一个 `max_tokens`**。实测同一句"写 300 字小说"：

| | 耗时 | 输出 token | 其中思考 | 正文 |
|---|---|---|---|---|
| 默认（思考开） | 6.1s | 900（撞上限） | 900 | **0 字**，finish=length |
| `thinking:{"type":"disabled"}` | 1.9s | 217 | 0 | 256 字 |

用户机器上一次 `agent_decide` 是 out=3600–4300（正常 200–400），约合每拍 0.027 元、
一个故事日 29 元纯思考开销。以前只有写死的 `NO_THINK_PURPOSES` 能关，创作类没有旋钮。

这一支守四件事
--------------
A 配置契约：`LLM_THINKING_MODE` 存在、默认 `auto`、取值恰好三个。
B 唯一的决策函数 `resolve_no_think()`：三种模式 × 显式/默认 × 判定/创作，
  以及"写错值要退回 auto，不能静默变成一律关"。
C **两道闸没被绕过**：`off` 也不能给不认识这个参数的模型（Qwen/Claude）发 `thinking`
  —— 那是会 400 的红线。用**打点真请求**判，不判源码字符串。
D 界面：`模型与额度`页画得出这个下拉，选项显示中文；保存块真的写回 `CFG.set`。

跑法：
    .venv\\Scripts\\python.exe tools/verify_thinking_mode.py
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

import verify_ui_common as VU  # noqa: E402

# ★★★ 2026-10-22：**两层缓存都关掉**。这个脚本打桩 client、用固定消息
#   （`{"role": "user", "content": "stub"}`）调真 `llm.chat()` 来抓请求体 ——
#   而缓存命中时**根本不发请求**，抓到的 body 是 `None` ⇒ 判据"没带参数"而红；
#   更糟的是打桩拿到的**假答复会被写进跨会话共享缓存**（`router.chat` 只看
#   `MOCK_LLM`，分不清真 client 与桩），留在用户机器上。
#   同批修的还有 `verify_progress_eval`（A1 就是被自己上一次留下的缓存判红的）。
# [EN] ★★★ 2026-10-22: **turn both cache layers off**. This script stubs the client and calls the
# [EN] real `llm.chat()` with a fixed message to capture the request body -- a cache hit sends
# [EN] **nothing**, so the captured body is `None` and the criterion says "parameter missing" (red);
# [EN] worse, the stubbed reply is written into the **cross-session shared cache** (`router.chat`
# [EN] only looks at `MOCK_LLM`, it cannot tell a stub from a real client) and stays on the user's
# [EN] machine. `verify_progress_eval` was fixed the same way (A1 was red because of its own leftovers).
from config import CFG  # noqa: E402
CFG.set('LLM_DEDUP_ENABLED', 'false')
CFG.set('LLM_CACHE_ENABLED', 'false')

RESULTS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'✓' if cond else '✗'} {name}" + (f"  [{detail}]" if detail else ""), flush=True)


def section(title: str) -> None:
    print(f"\n{'─' * 70}\n  {title}\n{'─' * 70}", flush=True)


# ══════════════════════════════════════════════════════════════
#  A 配置契约
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    section("A 配置契约")
    from config import SPEC

    spec = SPEC.get("LLM_THINKING_MODE")
    ok("A1 `LLM_THINKING_MODE` 进了配置表", isinstance(spec, dict),
       repr(spec)[:60] if spec else "缺这一项")
    if not isinstance(spec, dict):
        return
    ok("A2 默认值是 `auto`（老行为，不偷偷改）",
       str(spec.get("default")) == "auto", f"default={spec.get('default')!r}")
    ok("A3 取值恰好 auto / off / always",
       set(spec.get("opt") or []) == {"auto", "off", "always"},
       f"opt={spec.get('opt')}")
    ok("A4 类型是 enum（界面才画得出下拉）",
       str(spec.get("type")) == "enum", f"type={spec.get('type')}")
    ok("A5 描述里说清了三个取值各自是什么（不是复制粘贴的空壳）",
       all(w in str(spec.get("desc") or "") for w in ("auto", "off", "always")),
       str(spec.get("desc"))[:60])


# ══════════════════════════════════════════════════════════════
#  B 唯一的决策函数
# ══════════════════════════════════════════════════════════════
def group_b() -> None:
    section("B `resolve_no_think()` 的三种模式")
    from llm.router import NO_THINK_PURPOSES, THINKING_MODES, resolve_no_think as R

    ok("B0 三种模式常量对得上配置选项",
       set(THINKING_MODES) == {"auto", "off", "always"}, str(THINKING_MODES))
    ok("B0b 判定类用途确实在 `NO_THINK_PURPOSES` 里（否则 B2 无从谈起）",
       "progress_eval" in NO_THINK_PURPOSES and "agent_decide" not in NO_THINK_PURPOSES,
       f"{len(NO_THINK_PURPOSES)} 个用途")

    ok("B1 auto：创作类（agent_decide）**不关**",
       R(purpose="agent_decide", mode="auto") is False)
    ok("B2 auto：判定类（progress_eval）**关**",
       R(purpose="progress_eval", mode="auto") is True)
    ok("B3 auto：学过要关的 (模型,用途) 仍然生效（老机制没被开关吃掉）",
       R(purpose="agent_decide", learned=True, mode="auto") is True)

    ok("B4 off：创作类也关（这就是用户要的省钱口径）",
       R(purpose="agent_decide", mode="off") is True)
    ok("B5 off 是**一律**：连显式 `no_think=False` 也关",
       R(purpose="agent_decide", explicit=False, mode="off") is True)

    ok("B6 always：判定类也不关",
       R(purpose="progress_eval", mode="always") is False)
    ok("B7 always 是**一律**：连显式 `no_think=True` 也开",
       R(purpose="progress_eval", explicit=True, mode="always") is False)

    # ★★★ 成对：auto 下调用方的显式请求必须还管用（开关不能把它吃掉）
    ok("B8 ★★ 成对：auto 下显式 `no_think=True` 仍然关",
       R(purpose="agent_decide", explicit=True, mode="auto") is True)
    ok("B8b ★★ 成对：auto 下显式 `no_think=False` 仍然开（判定类也不关）",
       R(purpose="progress_eval", explicit=False, mode="auto") is False)

    # ★★★ 写错值不能静默变成"一律关"（那会悄悄砍掉所有思考）
    ok("B9 手改 `.env` 写错（`bogus`）⇒ 退回 auto，不是一律关",
       R(purpose="agent_decide", mode="bogus") is False
       and R(purpose="progress_eval", mode="bogus") is True)
    ok("B9b 空字符串也退回 auto（不是当成 off）",
       R(purpose="agent_decide", mode="  ") is False
       and R(purpose="progress_eval", mode="  ") is True)

    # 默认值来自 CFG：不给 mode 时读配置，且读的是**当前**值（现读现用）
    import config as _cfg
    old = _cfg.CFG.s("LLM_THINKING_MODE")
    try:
        _cfg.CFG.set("LLM_THINKING_MODE", "off")
        a = R(purpose="agent_decide")
        _cfg.CFG.set("LLM_THINKING_MODE", "auto")
        b = R(purpose="agent_decide")
        ok("B10 不传 mode 时读 `CFG` 的当前值（不是把 auto 写死）",
           a is True and b is False, f"off→{a} auto→{b}")
    finally:
        _cfg.CFG.set("LLM_THINKING_MODE", old)


# ══════════════════════════════════════════════════════════════
#  C 两道闸没被绕过 —— **打点真请求**
# ══════════════════════════════════════════════════════════════
class _Resp:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }


class _Client:
    """假的 httpx 客户端：只记 `json=` 那份 body，不回真网络。"""

    def __init__(self) -> None:
        self.bodies: list[dict] = []

    async def post(self, url, json=None, headers=None, timeout=None, **kw):  # noqa: A002
        self.bodies.append(dict(json or {}))
        return _Resp()


def _capture(model: str, purpose: str, mode: str) -> dict | None:
    """跑一次真的 `llm.chat()`（网络打桩），返回发出去的 body。"""
    import config as _cfg
    from llm import models as MODELS
    from llm.router import llm

    old_mode = _cfg.CFG.s("LLM_THINKING_MODE")
    old_resolve = MODELS.resolve
    old_client, old_sem = llm._client, llm._sem
    old_ensure = llm.ensure_started
    fake = _Client()
    try:
        _cfg.CFG.set("LLM_THINKING_MODE", mode)
        MODELS.resolve = lambda **kw: MODELS.Resolved(
            key=model, label=model, model=model,
            base_url="http://stub.local/v1", api_key="stub",
            provider="openai_compatible",
            caps={"LLM_CAP_IMAGE": False, "LLM_CAP_REASONING": False,
                  "LLM_CAP_THINKING": True, "LLM_CAP_JSON_MODE": True,
                  "LLM_CAP_SYSTEM_ROLE": True},
            source="stub")
        llm._client = fake
        llm._sem = asyncio.Semaphore(2)

        async def _no_start(*a, **k):
            return None

        llm.ensure_started = _no_start
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            llm.chat("daily", [{"role": "user", "content": "stub"}],
                     purpose=purpose, max_tokens=64))
        return fake.bodies[0] if fake.bodies else None
    except Exception as e:                                  # noqa: BLE001
        print(f"   （打点失败：{type(e).__name__}: {e}）", flush=True)
        return None
    finally:
        MODELS.resolve = old_resolve
        llm._client, llm._sem = old_client, old_sem
        llm.ensure_started = old_ensure
        _cfg.CFG.set("LLM_THINKING_MODE", old_mode)


def group_c() -> None:
    section("C 参数真的进了请求；两道闸没被绕过")
    from llm.capabilities import detect_thinking_switch

    ok("C0 `detect_thinking_switch('deepseek-flash')` 认得出这个参数",
       detect_thinking_switch("deepseek-flash") is True)
    ok("C0b `detect_thinking_switch('qwen-max')` **不认**（给它发会 400）",
       detect_thinking_switch("qwen-max") is not True,
       repr(detect_thinking_switch("qwen-max")))

    b = _capture("deepseek-flash", "agent_decide", "off")
    ok("C1 ★★★ off + deepseek-flash（创作类）⇒ body 里真有 `thinking:disabled`",
       bool(b) and b.get("thinking") == {"type": "disabled"},
       f"thinking={None if not b else b.get('thinking')}")

    b = _capture("deepseek-flash", "progress_eval", "always")
    ok("C2 ★★★ always + 判定类 ⇒ body 里**没有** thinking（不再偷偷关）",
       bool(b) and "thinking" not in b,
       f"keys={sorted((b or {}).keys())}")

    b = _capture("deepseek-flash", "agent_decide", "auto")
    ok("C3 auto + 创作类 ⇒ 没有 thinking（老行为没变）",
       bool(b) and "thinking" not in b)

    b = _capture("deepseek-flash", "progress_eval", "auto")
    ok("C4 auto + 判定类 ⇒ 有 thinking（结论型照样关）",
       bool(b) and b.get("thinking") == {"type": "disabled"})

    b = _capture("qwen-max", "agent_decide", "off")
    ok("C5 ★★★ **成对**：off + 不认识该参数的模型 ⇒ 不发 thinking"
       "（省钱的开关不许替 400 那条红线做主）",
       bool(b) and "thinking" not in b,
       f"model=qwen-max thinking={None if not b else b.get('thinking')}")

    # 思考开关不能把 max_tokens 一起改坏
    b = _capture("deepseek-flash", "agent_decide", "off")
    ok("C6 关思考不影响 `max_tokens` 的取值（还是走 `_effective_max_tokens`）",
       bool(b) and int(b.get("max_tokens") or 0) >= 64,
       f"max_tokens={None if not b else b.get('max_tokens')}")


# ══════════════════════════════════════════════════════════════
#  D 界面与落盘
# ══════════════════════════════════════════════════════════════
def group_d() -> None:
    section("D 界面可改、可存")
    src = (APP / "gui" / "app_flet.py").read_text(encoding="utf-8")

    # D1/D2 用**渲染过的界面**判（不判源码字符串）—— 见 group_e
    # 这里只钉"保存块真的写回"：AST 判 `CFG.set('LLM_THINKING_MODE', ...)` 存在。
    tree = ast.parse(src)
    writes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == "set"):
            continue
        if not (isinstance(f.value, ast.Name) and f.value.id == "CFG"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) \
                and node.args[0].value == "LLM_THINKING_MODE":
            writes.append(node.lineno)
    ok("D1 ★★ 保存块里有 `CFG.set('LLM_THINKING_MODE', …)`（不是画出来的装饰）",
       bool(writes), f"行号 {writes[:4]}")

    # 成对：下拉句柄必须被**读**（`_fb.get('think_mode')`），否则写回的是空值
    # ★★★ 2026-10-18：D2 原来判的是"这行字在不在源码里" —— 写反成
    #   `is None` 照样绿（反例法第 15 组当场抓到）。改成 **AST 判条件方向**：
    #   必须存在 `if <...>.get('think_mode') **is not None**:` 且它体内有
    #   `CFG.set('LLM_THINKING_MODE', ...)`。写反、写空、挂错分支都会红。
    # [EN] ★★★ 2026-10-18: D2 used to check "is this line in the source" -- writing it backwards as
    # [EN] `is None` stayed green (mutation #15 caught it on the spot). Now it **checks the condition's
    # [EN] direction via AST**: there must be an `if <...>.get('think_mode') **is not None**:` whose
    # [EN] body calls `CFG.set('LLM_THINKING_MODE', ...)`. Backwards, empty or mis-branched all go red.
    guarded = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        cmp_ = node.test
        seg = ast.get_source_segment(src, cmp_) or ""
        if "think_mode" not in seg:
            continue
        if not isinstance(cmp_.ops[0], ast.IsNot):
            continue
        if not (isinstance(cmp_.comparators[0], ast.Constant)
                and cmp_.comparators[0].value is None):
            continue
        for inner in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if not isinstance(inner, ast.Call):
                continue
            f2 = inner.func
            if (isinstance(f2, ast.Attribute) and f2.attr == "set"
                    and isinstance(f2.value, ast.Name) and f2.value.id == "CFG"
                    and inner.args and isinstance(inner.args[0], ast.Constant)
                    and inner.args[0].value == "LLM_THINKING_MODE"):
                guarded = True
    ok("D2 ★★★ 成对：保存的是**下拉句柄**且条件方向对"
       "（`if …get('think_mode') is not None: CFG.set(…)`；写反成 `is None` ⇒ 存进去是空值）",
       guarded, "条件方向正确" if guarded else "找不到正确方向的那段判断")

    # 模型与额度页里确实构造了这个下拉
    ok("D3 「模型与额度」页构造了 `t('思考模式')` 下拉",
       "mk_dropdown(\n            t('思考模式')" in src or "t('思考模式')" in src)


def _labelled_dropdowns(root) -> dict:
    """把界面上"标签 + 下拉"的配对读出来：`{标签文字: DropdownM2}`。

    `mk_dropdown()` 返回的 Row 上挂着 `row._field = dd`，标签是
    `row.controls[0]` —— 但那**不是** `ft.Text`，是 `_label_box()` 造的
    `ft.Container(content=Text(...))`，所以必须用 `all_texts()` 取字
    （直接读 `.value` 会拿到空串，于是"页上 0 个下拉"这种假红）。
    **从画出来的控件里读**，不扫源码 —— 源码里有 `t('思考模式')`
    不代表它真的被画到了这一页上。
    """
    out: dict = {}
    for c in VU.walk(root):
        dd = getattr(c, "_field", None)
        if dd is None or not hasattr(dd, "options"):
            continue
        kids = getattr(c, "controls", None) or []
        label = ""
        if kids:
            label = "".join(VU.all_texts(kids[0])).strip()
        if label:
            out[label] = dd
    return out


def group_e() -> None:
    """真把「LLM 接入」页画出来，量下拉的**显示文字**。

    ★ 为什么不能只判源码：`ft.dropdown.Option('auto')` 只给 key 时，
      界面上显示的就是英文键。判源码会把"写了但显示英文"判成绿。
    """
    section("E 界面上真的看得见（开一个窗口量）")
    import tempfile
    import traceback

    import flet as ft
    from gui.app_flet import NovelWorldApp
    from util.flet_shutdown import shutdown

    tmp = Path(tempfile.mkdtemp(prefix="nws_thinkmode_"))

    async def _body(page: ft.Page) -> None:
        VU.isolate_projects_dir(tmp / "Projects")
        app = NovelWorldApp()
        app.main(page)
        await asyncio.sleep(1.5)
        try:
            app.show_global_settings()
        except Exception:                            # noqa: BLE001
            print("   （打开设置页失败：" + traceback.format_exc()[-200:] + "）", flush=True)
        await asyncio.sleep(1.8)
        # ⚠ 设置页是**对话框**：它的内容在 `page._dialogs` 里，`walk(page)`
        #   收不到（那是"对话框外面"那棵树）。不取这一层就会误判成"页上没有"。
        # [EN] ⚠ The settings page is a **dialog**: its content lives in `page._dialogs`, which
        # [EN] `walk(page)` does not reach (that is the tree *outside* the dialog). Missing this
        # [EN] layer would mis-report "nothing on the page".
        found: dict = {}
        for d in (VU.open_dialogs(page) or [page]):
            found.update(_labelled_dropdowns(d))
        dd = found.get("思考模式")
        ok("E1 ★★ 「思考模式」这个下拉真的画在设置页上", dd is not None,
           f"对话框里 {len(found)} 个带标签的下拉")
        if dd is None:
            return
        labels = [VU.opt_label(o) for o in (getattr(dd, "options", None) or [])]
        ok("E2 三个选项都在", len(labels) == 3, f"{labels}")
        ok("E3 ★★★ 显示的是中文，不是 auto/off/always"
           "（英文键漏到界面上就是半个界面英文）",
           bool(labels) and all(any("\u4e00" <= ch <= "\u9fff" for ch in s) for s in labels),
           f"{labels}")
        ok("E4 当前值落在三个选项里",
           str(getattr(dd, "value", "")) in ("auto", "off", "always"),
           f"value={getattr(dd, 'value', None)!r}")

    async def _main(page: ft.Page) -> None:
        code = 2
        try:
            await _body(page)
        except BaseException:                        # noqa: BLE001
            ok("E0 ★ 真机段崩了（自己留一条红）", False, traceback.format_exc()[-500:])
        finally:
            # ⚠ 汇总必须打在 `shutdown()` **之前**：那一步之后进程就没了。
            code = _finish()
            VU.safe_rmtree(tmp, ignore_errors=True)
            await shutdown(page, code=code)

    try:
        ft.run(_main, assets_dir=str(APP / "assets"))
    except SystemExit:
        raise
    except Exception:                                # noqa: BLE001
        ok("E0 界面起得来", False, traceback.format_exc()[-400:])


def _finish() -> int:
    """打汇总并给出退出码。**必须在关窗口之前调** ——
    `shutdown()` 之后进程就没了，放在后面的话一行都打不出来（第一版就是这样，
    屏幕上只剩进度，看不到 30/30 和未通过清单）。
    """
    passed = sum(1 for _n, c, _d in RESULTS if c)
    total = len(RESULTS)
    print(f"\n{'=' * 70}\n  思考模式验证：{passed}/{total}"
          f"　（{time.time() - t0_all[0]:.1f}s）\n{'=' * 70}", flush=True)
    bad = [n for n, c, _d in RESULTS if not c]
    if bad:
        print("未通过：\n  - " + "\n  - ".join(bad), flush=True)
    return 0 if not bad else 2


t0_all = [0.0]


def main() -> int:
    t0_all[0] = time.time()
    group_a()
    group_b()
    group_c()
    group_d()
    if "--no-ui" in sys.argv:
        return _finish()
    group_e()
    # `group_e()` 里的 `shutdown()` 已经顺手调过 `_finish()`；走到这儿说明
    # 它没跑起来（`ft.run` 抛了），那就自己收尾。
    return _finish()


if __name__ == "__main__":
    sys.exit(main())
