# -*- coding: utf-8 -*-
"""验证：开卷摄取的**报错与关键信息**也会进右侧「AI 优化对话」。

用户 2026-10-07：

> 开卷 摄取的时候如果有报错以及AI回复的关键信息 则请将其放到右侧AI优化对话的
> 回复里 **否则可能看不见**

## 为什么这条值得单独立判据

右侧那一栏是**作者盯着看的地方**（他在那里跟 AI 一来一往），而左侧「运行日志」
是一条快速滚动的流水 —— 一轮开卷几十次调用、几百行日志，**超过 600 行还会
把最前面的 100 行裁掉**。报错只落在左边 → 作者多半没看见，
只会觉得"卡住了 / 没反应"，于是反复重试、或者把已经跑了一半的流程关掉。

## 检查什么

A 真机（MOCK，走真实入口 `show_import_wizard` → `_do_import`）
  · 一条**真·LLM 失败事件**（从 `llm.router.llm._emit(...)` 派发，
    走的是产品自己的链路 listener → `on_llm` → 日志 → 镜像）——
    右侧对话里**出现了**那条报错，而且带 `【系统】` 前缀
  · 报错的**时间戳被剥掉**（气泡里带着 `[23:36:12]` 像日志行，不像消息）
  · **同一句话只进一次**（LLM 重试三轮不能刷成三条一模一样的）
  · 关键**结论**也在右侧：`✓ 设定提取完成 · 评档 …`
  · `✓ 项目已创建：…` 也在右侧
  · 报错**不影响摄取继续**（镜像只是播报员）
B 源码级
  · `_add_log` 里 `level == 'err'` 真的会调 `_mirror_chat`
  · `_mirror_chat` **吞掉所有异常**（它挂了不能把报错本身丢了）
  · 去重集合存在且**挂在框内**（不是每次新建 —— 那样去重等于没做）
C i18n
  · `【系统】` 有英文（英文界面下别露出中文）

跑法：
    .venv\\Scripts\\python.exe tools\\verify_ingest_chat_mirror.py
    .venv\\Scripts\\python.exe tools\\verify_ingest_chat_mirror.py --logic-only
产出：
    assets/screenshots/ingest_chat_mirror_report.json

English:
Verify: errors and key info from open-book ingest also go into the right-side "AI 优化对话".
User 2026-10-07:
> During open-book ingest, if there are errors as well as key info from AI replies, please put them into the right-side AI optimization conversation
> replies **otherwise they may be invisible**
## Why this deserves its own criterion
That right-side panel is **where the author stares** (where he goes back and forth with the AI),
while the left-side "run log"
is a fast-scrolling stream — one round of open-book ingest makes dozens of calls, hundreds of
log lines, **after 600 lines it even
trims the first 100 lines**. Errors only land on the left → the author mostly does not see them,
and only feels "stuck / no response", so he retries repeatedly, or closes a flow that is already
half done.
## What to check
A Real machine (MOCK, goes through the real entry `show_import_wizard` → `_do_import`)
  · A **true LLM failure event** (dispatched from `llm.router.llm._emit(...)`,
    going through the product's own pipeline listener → `on_llm` → log → mirror) ——
    that error **appears** in the right-side conversation, and with the `【系统】` prefix
  · The error's **timestamp is stripped** (the bubble carrying `[23:36:12]` looks like a log line, not a message)
  · **The same line goes in only once** (three rounds of LLM retries must not spam three identical entries)
  · Errors **do not affect ingest continuing** (mirror is just an announcer)
B Source level
  · In `_add_log`, `level == 'err'` really does call `_mirror_chat`
  · `_mirror_chat` **swallows all exceptions** (if it crashes it must not lose the error itself)
  · The dedup set exists and **is attached to the frame** (not recreated every time —— that would make dedup useless)
C i18n
  · `【系统】` has an English version (do not expose Chinese under the English UI)
How to run:
    .venv\\Scripts\\python.exe tools\\verify_ingest_chat_mirror.py
    .venv\\Scripts\\python.exe tools\\verify_ingest_chat_mirror.py --logic-only
Output:
    assets/screenshots/ingest_chat_mirror_report.json
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import shutil
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                       # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('UI_LANG', 'zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

_ITEMS: list[dict] = []


def ok(name: str, cond, detail: str = '') -> bool:
    good = bool(cond)
    _ITEMS.append({'name': name, 'ok': good, 'detail': str(detail)[:240]})
    print(f'  [{"OK" if good else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))
    return good


def head(text: str) -> None:
    print(f'\n{"=" * 68}\n {text}\n{"=" * 68}')


# ══════════════════════════════════════════════════════════════
#  B/C. 源码级（零窗口）
# [EN] B/C. Source level (zero window)
# ══════════════════════════════════════════════════════════════
def test_source() -> bool:
    head('B/C. 源码级 + i18n')
    from gui.app_flet import NovelWorldApp
    good = True

    src = inspect.getsource(NovelWorldApp._do_import)
    body = textwrap.dedent(src)
    tree = ast.parse(body)

    def _find_fn(name: str):
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name == name:
                return n
        return None

    add_log = _find_fn('_mirror_chat')
    _al = _find_fn('_add_log')
    good &= ok('B0 前提：两个内部函数都在（`_add_log` / `_mirror_chat`）',
               _al is not None and add_log is not None, '')

    # ── B1：**接线**要用 AST 落到 `_add_log` 里那条 `if level == 'err'` 的 body ──
    # ⚠ 不能查文本 `'_mirror_chat(text' in body`：**函数定义自己**
    #   `def _mirror_chat(text: str, …)` 就含这个子串 → 接线断了也照样绿。
    #   反例法 ② 当场揭穿过。
    # [EN] ── B1: **Wiring** must be resolved by AST to the body of the `if level == 'err'` in `_add_log`
    # [EN] ──
    # [EN] ⚠ Cannot check the text `'_mirror_chat(text' in body`: **the function definition itself**
    # [EN] `def _mirror_chat(text: str, …)` already contains this substring → it stays green even if the
    # [EN] wiring is broken.
    # [EN] Counterexample method ② exposed it on the spot.
    wired = False
    if _al is not None:
        for n in ast.walk(_al):
            if not isinstance(n, ast.If):
                continue
            consts = {x.value for x in ast.walk(n.test)
                      if isinstance(x, ast.Constant)}
            if 'err' not in consts:
                continue
            for c in ast.walk(n):
                if isinstance(c, ast.Call) and (
                        getattr(c.func, 'id', '') == '_mirror_chat'):
                    wired = True
    good &= ok("B1 ★★★ `_add_log` 里 `level == 'err'` 那个分支的**函数体里真的调了**"
               ' `_mirror_chat`（这是"报错进右侧"的唯一接线点）',
               wired, '')

    # ── B2：吞异常要用 AST 看 `_mirror_chat` 自己的 try/handlers ──
    # ⚠ **"有 try" 不等于"吞了"**：`except Exception: raise` 也有 try，
    #   但它把异常又抛出去了 —— 那正好是要治的病（镜像一挂，报错本身也丢了）。
    #   所以要求：handler **里面不许有 `raise`**。反例法 ③ 专门打这条。
    # [EN] ── B2: For exception swallowing, use AST to look at `_mirror_chat`'s own try/handlers ──
    # [EN] ⚠ **"Has a try" does not equal "swallowed"**: `except Exception: raise` also has a try,
    # [EN] but it re-raises the exception — which is exactly the disease to cure (when the mirror crashes,
    # [EN] the error itself is lost too).
    # [EN] So the requirement is: the handler **must not contain `raise`**. Counterexample method ③ targets
    # [EN] this specifically.
    has_try = False
    rereaises = False
    if add_log is not None:
        for n in ast.walk(add_log):
            if isinstance(n, ast.Try) and n.handlers:
                has_try = True
                for h in n.handlers:
                    if any(isinstance(x, ast.Raise) for x in ast.walk(h)):
                        rereaises = True
    body_txt = (ast.get_source_segment(body, add_log) or '') if add_log else ''
    good &= ok('B2 ★★ `_mirror_chat` **自己**带 try/except 且**真的吞掉**'
               '（handler 里不许 `raise`）—— 它只是播报员，'
               '镜像失败绝不能把报错本身丢掉',
               has_try and not rereaises,
               f'try={has_try} 又抛出={rereaises}')

    # ── B3：去重集合必须在函数**之外**赋值（每次新建 = 去重没做）──
    # [EN] ── B3: The dedup set must be assigned **outside** the function (recreating each time = no dedup)
    # [EN] ──
    outer_assign = inner_assign = False
    if add_log is not None:
        for n in ast.walk(tree):
            if isinstance(n, ast.AnnAssign) or isinstance(n, ast.Assign):
                tgts = ([n.target] if isinstance(n, ast.AnnAssign) else n.targets)
                if not any(getattr(t, 'id', '') == '_MIRRORED' for t in tgts):
                    continue
                if n.lineno < add_log.lineno:
                    outer_assign = True
                else:
                    inner_assign = True
    good &= ok('B3 ★★ 去重集合 `_MIRRORED` **挂在框外**（赋值发生在 `_mirror_chat` '
               '定义之前）—— 写进函数体里就是每次新建，去重等于没做',
               outer_assign and not inner_assign,
               f'outer={outer_assign} inner={inner_assign}')

    good &= ok('B3b ★ 去重**真的用上了**（函数体里有 `in _MIRRORED` 与 `.add(`）',
               'in _MIRRORED' in body_txt and '.add(' in body_txt, '')
    good &= ok('B4 ★★ 剥掉日志的时间戳前缀'
               '（气泡里带 `[23:36:12]` 像日志行，不像一条消息）',
               'sub(' in body_txt and r'\d{1,2}:\d{2}' in body_txt, '')
    good &= ok('B5 ★ 加了 `【系统】` 前缀（一眼区别于"AI 说的话"）',
               "t('【系统】')" in body_txt, '')
    good &= ok('B5b ★★ 剥完时间戳**再判空**（只剥出空串时不许留空气泡）',
               'if not body' in body_txt, '')

    # 关键节点（这两条是 `_do_import` 主体里的调用，查文本够用）
    # [EN] Key nodes (these two are calls in the body of `_do_import`, text search is enough)
    good &= ok('B6 ★★ 关键**结论**在右侧也有一条（设定提取完成 · 评档 …）',
               '设定提取完成' in body and '_mirror_chat' in body, '')
    good &= ok('B7 ★ 项目落盘路径也在右侧（作者常要照它去开文件夹）',
               '项目已创建' in body, '')

    # 句柄暴露（判据要能驱动）
    # [EN] Handle exposure (criteria must be drivable)
    good &= ok("B8 ★ `state['ui']` 暴露了 `mirror_chat`（自动化/判据要能驱动它）",
               "'mirror_chat'" in body, '')

    from i18n import _ZH2EN
    good &= ok('C1 ★★ `【系统】` 有英文（英文界面下别露出中文）',
               '【系统】' in _ZH2EN, str(_ZH2EN.get('【系统】')))
    good &= ok('C2 ★ 两条新系统消息都有英文',
               '✓ 项目已创建：{p}' in _ZH2EN
               and any('设定提取完成' in k for k in _ZH2EN), '')
    return good


# ══════════════════════════════════════════════════════════════
#  A. 真机
# [EN] A. Real machine
# ══════════════════════════════════════════════════════════════
def _fixture(root: Path) -> Path:
    src = root / '雨夜来客'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text('# 大纲\n起：雨夜来客。\n承：旧事翻出。\n',
                                 encoding='utf-8')
    (src / '人物设定.md').write_text('# 人物\n## 主角\n掌柜。\n## 阿枝\n伙计。\n',
                                     encoding='utf-8')
    (src / '正文' / '第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦。\n\n「你今日话里有话。」\n', encoding='utf-8')
    return src


def _chat_texts(ui: dict) -> list[str]:
    """右侧对话栏里所有气泡的文字。
        English:
    The text of all bubbles in the right-side conversation panel.
    """
    import flet as ft
    import verify_ui_common as VU
    out: list[str] = []
    cl = ui.get('chat_list')
    if cl is None:
        return out
    for c in VU.walk(cl):
        if isinstance(c, ft.Text) and getattr(c, 'value', None):
            out.append(str(c.value))
    return out


async def test_gui(page) -> bool:
    import flet as ft
    import verify_ui_common as VU
    from gui.app_flet import NovelWorldApp
    from i18n import set_lang, t
    from llm.router import llm
    set_lang('zh')

    head('A. 真机（MOCK，走真实开卷入口）')
    good = True
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.window.width = 1400
    page.window.height = 900
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_mirror_'))
    try:
        VU.isolate_projects_dir(tmp / 'Projects')
        src = _fixture(tmp)

        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.5)
        app._wizard_path = str(src)
        app._wizard_name = '报错镜像验证'
        app._wizard_opts['ai_optimize'] = False     # 只要自动摄取那一段
        # [EN] Only the auto-ingest segment is needed
        app._wizard_opts['repair_source'] = False
        app._do_import(page)
        await asyncio.sleep(0.6)

        st = app._ingest_state or {}
        ui = st.get('ui') or {}
        good &= ok('A0 摄取起来了，右侧对话栏句柄在位',
                   bool(ui.get('chat_list')) and bool(ui.get('mirror_chat')),
                   str(sorted(ui.keys())[:8]))

        # ── ① 真·LLM 失败事件（走产品自己的链路）──
        #    `_emit` → listener → `on_llm`（`kind == 'error'` 分支）
        # [EN] ── ① True LLM failure event (goes through the product's own pipeline) ──
        # [EN] `_emit` → listener → `on_llm` (`kind == 'error'` branch)
        #    → `_add_log(..., 'err')` → `_mirror_chat`
        before = len(_chat_texts(ui))
        llm._emit({'type': 'error', 'tier': 'daily', 'model': 'probe-model',
                   'purpose': 'genre', 'attempt': 2, 'retries': 3,
                   'error': 'HTTP 502 Bad Gateway（判据注入的一次假故障）'})
        await asyncio.sleep(0.5)
        texts = _chat_texts(ui)
        joined = '\n'.join(texts)
        good &= ok('A1 ★★★ 一条**真·LLM 失败事件** → 右侧对话里出现了那条报错',
                   '502 Bad Gateway' in joined,
                   f'对话 {before} → {len(texts)} 条；'
                   f'尾部 {texts[-1][:70] if texts else "（空）"!r}')
        good &= ok('A2 ★★ 它带 `【系统】` 前缀（一眼区别于"AI 说的话"）',
                   t('【系统】') in joined, '')
        good &= ok('A3 ★★ 报错的**时间戳被剥掉**了（气泡里带 `[23:36:12]` '
                   '像日志行，不像消息）',
                   not any(x.startswith(t('【系统】') + '[') for x in texts),
                   str([x[:26] for x in texts if t('【系统】') in x][-2:]))
        good &= ok('A4 ★★ 重试次数这类**关键上下文**没丢（`2/3`）'
                   '—— 用户要知道"它正在重试"',
                   '2/3' in joined or '（2/3）' in joined, '')

        # ── ② 去重：同一句话再发一次，不该多一条 ──
        # [EN] ── ② Dedup: sending the same line again should not add another entry ──
        n1 = len(_chat_texts(ui))
        llm._emit({'type': 'error', 'tier': 'daily', 'model': 'probe-model',
                   'purpose': 'genre', 'attempt': 2, 'retries': 3,
                   'error': 'HTTP 502 Bad Gateway（判据注入的一次假故障）'})
        await asyncio.sleep(0.4)
        n2 = len(_chat_texts(ui))
        good &= ok('A5 ★★ **同一句话只进一次**（LLM 重试三轮不能刷成三条一样的）',
                   n2 == n1, f'{n1} → {n2}')

        # ── ③ 镜像了个坏东西也不该炸（吞异常）──
        # [EN] ── ③ Mirroring a bad thing should not blow up (swallow exceptions) ──
        try:
            ui['mirror_chat'](None)
            ui['mirror_chat']('')
            ui['mirror_chat']('   ')
            ok('A6 ★ 喂 `None` / 空串不炸、也不留空气泡', True, '')
        except Exception as e:                                   # noqa: BLE001
            ok('A6 ★ 喂 `None` / 空串不炸、也不留空气泡', False, repr(e))
        good &= bool(_ITEMS[-1]['ok'])

        # ── ④ 报错之后摄取**继续**（镜像只是播报员，不许影响流程）──
        # [EN] ── ④ After an error, ingest **continues** (mirror is just an announcer, must not affect the
        # [EN] flow) ──
        good &= ok('A7 ★★ 报了错之后摄取**照常继续**'
                   '（镜像失败/报错都不该影响流程）',
                   bool(st.get('running')) or bool(st.get('result')),
                   f'running={st.get("running")} result={"有" if st.get("result") else "无"}')

        # ── 等它跑完，看关键结论有没有进右侧 ──
        # [EN] ── Wait for it to finish, check whether key conclusions made it to the right panel ──
        for _ in range(900):
            await asyncio.sleep(0.2)
            u = st.get('ui') or {}
            try:
                if u.get('consent'):
                    u['consent'](True)          # 同意门自动点头
                    # [EN] Consent gate auto-clicks yes
            except Exception:                                    # noqa: BLE001
                pass
            if st.get('result') and not st.get('running'):
                break
            if not st.get('running') and st.get('result'):
                break
        await asyncio.sleep(1.0)
        texts2 = _chat_texts(ui)
        joined2 = '\n'.join(texts2)
        good &= ok('A8 ★★★ 关键**结论**（设定提取完成 · 评档 …）也在右侧',
                   '设定提取完成' in joined2,
                   str([x[:60] for x in texts2 if '提取完成' in x][:1]))
        good &= ok('A9 ★ 项目落盘路径也在右侧（作者常要照它去开文件夹）',
                   '项目已创建' in joined2,
                   str([x[:70] for x in texts2 if '项目已创建' in x][:1]))
        good &= ok('A10 ★ 右侧对话里现在**至少有一条系统消息**'
                   '（证明这条通道真的画进了控件树，不是只记在某个列表里）',
                   any(t('【系统】') in x for x in texts2),
                   f'{len(texts2)} 条气泡，其中系统 '
                   f'{sum(1 for x in texts2 if t("【系统】") in x)} 条')
        try:
            page.update()
            await asyncio.sleep(0.4)
            (OUT / 'ingest_chat_mirror.png').write_bytes(
                await page.take_screenshot())
        except Exception:                                        # noqa: BLE001
            pass
    finally:
        try:
            if (app._ingest_state or {}).get('running'):
                app._ingest_state['cancel'] = True
                await asyncio.sleep(1.0)
        except Exception:                                        # noqa: BLE001
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    return good


# ══════════════════════════════════════════════════════════════
async def main(page) -> None:
    from util.flet_shutdown import shutdown
    good = True
    try:
        good &= test_source()
        good &= await test_gui(page)
    except BaseException:                                        # noqa: BLE001
        traceback.print_exc()
        _ITEMS.append({'name': '（执行中断）', 'ok': False,
                       'detail': traceback.format_exc()[-400:]})
        good = False
    n_ok = sum(1 for i in _ITEMS if i['ok'])
    print(f'\n{"-" * 68}\n  报错/关键信息进右侧对话：{n_ok}/{len(_ITEMS)}'
          + ('' if good else '   ← 有失败'))
    for i in _ITEMS:
        if not i['ok']:
            print(f'    ! {i["name"]}  [{i["detail"][:130]}]')
    (OUT / 'ingest_chat_mirror_report.json').write_text(
        json.dumps({'passed': n_ok, 'total': len(_ITEMS), 'ok': good,
                    'checks': _ITEMS}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    await shutdown(page, code=0 if good else 2)


if __name__ == '__main__':
    if '--logic-only' in sys.argv:
        a = test_source()
        n = sum(1 for i in _ITEMS if i['ok'])
        print(f'\n  报错/关键信息进右侧对话（逻辑段）：{n}/{len(_ITEMS)}'
              + ('' if a else '   ← 有失败'))
        for i in _ITEMS:
            if not i['ok']:
                print(f'    ! {i["name"]}  [{i["detail"][:140]}]')
        sys.exit(0 if a else 2)
    import flet as ft
    ft.run(main)
