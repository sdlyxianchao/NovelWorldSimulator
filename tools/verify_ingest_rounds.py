# -*- coding: utf-8 -*-
"""真机验证：开卷「AI 优化」的**轮数上限**与**强制停止**。

用户 2026-10-08 的原话：
    「开卷 AI 优化 要有轮数上限且有地方配置 而且可以点击某个按钮强制停止」

三件事，三组判据：

  A **轮数上限真的是配置项，不是写死的数**（源码级 / AST）
      · `POLISH_MAX_ROUNDS` 在 SPEC 里（int / 默认 10 / 上下限合理）；
      · **产品源码真的读它**（防"假旋钮"）；
      · 天机 ·「运行」→「开卷打磨」里真的有三个输入框，保存真的写回去；
      · 上限判定用的是 `>=`（差一就等于少给一轮）。
  B **强制停止真的能打断正在跑的那一轮**（真机）
      · 还没进 AI 优化阶段时它是灰的（不该乱接这一手）；
      · 进了就能点；点下去**正在跑的那个任务真的被取消**、对话栏出现
        「这一轮被你停掉了」、输入框还能接着用；
      · 它**不是**「取消摄取」—— 停完这一轮，整趟摄取还活着。
  C **到上限之后的行为**（真机）
      · 输入框 / 发送变灰，但 **「完成优化并进入」必须是亮的**（出口不能一起关）；
      · 右侧对话栏里也有那条说明（用户原话：只落左侧日志"可能看不见"）；
      · 到上限之后硬塞进来的指令**不执行**（上限不能是摆设）；
      · 点「完成优化并进入」仍然能收工进运行界面。

跑法：
    .venv\\Scripts\\python.exe tools/verify_ingest_rounds.py
    .venv\\Scripts\\python.exe tools/verify_ingest_rounds.py --logic-only   # 只跑 A 组
产出：
    assets/screenshots/ingest_rounds_*.png
    assets/screenshots/ingest_rounds_report.json

English:
Real-machine verification: the **round limit** and **force stop** of Kaijuan 「AI 优化」.
The user's exact words on 2026-10-08:
Three things, three groups of criteria:
  A **The round limit really is a config item, not a hardcoded number** (source level / AST)
      · `POLISH_MAX_ROUNDS` is in SPEC (int / default 10 / sane bounds);
      · **The product source really reads it** (guards against "fake knobs");
      · In Tianji · 「运行」→「开卷打磨」 there really are three input fields, and save really writes back;
      · The limit check uses `>=` (off by one equals one round short).
  B **Force stop really can interrupt the round currently running** (real machine)
      · Before entering the AI optimization stage it is grey (must not be wired up prematurely);
      · Once inside it can be clicked; clicking it **really cancels the task currently running**, the chat panel shows
      · It is **not** 「取消摄取」 — after stopping this round, the whole ingest run is still alive.
  C **Behavior after hitting the limit** (real machine)
      · The input field / send button grey out, but **「完成优化并进入」 must stay lit** (the exit must not close with them);
      · The same note also appears in the right-hand chat panel (user's exact words: only landing in the left log "may be invisible");
      · Commands forced in after the limit **are not executed** (the limit cannot be decoration);
How to run:
    .venv\\Scripts\\python.exe tools/verify_ingest_rounds.py
    .venv\\Scripts\\python.exe tools/verify_ingest_rounds.py --logic-only   # only run group A
Output:
    assets/screenshots/ingest_rounds_*.png
    assets/screenshots/ingest_rounds_report.json
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                       # noqa: E402
import verify_ui_common as VU                            # noqa: E402
from util.flet_shutdown import shutdown                  # noqa: E402

from config import CFG                                   # noqa: E402
CFG.set('MOCK_LLM', 'true')                              # 零网络、零成本、可复现
# [EN] Zero network, zero cost, reproducible
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from gui.app_flet import NovelWorldApp                   # noqa: E402
import gui.app_flet as G                                 # noqa: E402
from i18n import set_lang, t                             # noqa: E402
set_lang(_lang)

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
GUI = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'

#: B4/B4b 用的两个标记色（调色板里没有这两个纯色；只动颜色、不动几何）。
# [EN] The two marker colors used by B4/B4b (neither pure color is in the palette; only colors change,
# [EN] no geometry).
MARK_IN = '#ff00ff'      # 输入框底
# [EN] Input box background
MARK_TXT = '#00ffff'     # 按钮文字
# [EN] Button text
MARK_PANE = '#ffff00'    # 上面那两栏纸卡（防止"垫高输入框"是靠"压扁两栏"换来的）
# [EN] The two paper cards above (guards against "making the input taller" being paid for by "squashing
# [EN] the two columns")


def hex_rgb(s: str) -> tuple:
    """`#rrggbb` → `(r, g, b)`。
        English:
    `#rrggbb` -> `(r, g, b)`.
    """
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))

checks: list = []
report: dict = {}


def ok(name: str, cond, detail: str = '') -> bool:
    checks.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(('✓ ' if cond else '! ') + name + ('' if cond else f'  ← {str(detail)[:220]}'),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  A 组：轮数上限是**真的配置项**（AST —— 不是"源码里出现过就算"）
# [EN] Group A: The round limit is a **real config item** (AST — not "it appeared in the source so it
# [EN] counts")
# ══════════════════════════════════════════════════════════════════
def _ast() -> ast.AST:
    return ast.parse(GUI)


def _calls(node, name: str) -> list:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if (getattr(f, 'attr', None) or getattr(f, 'id', None)) == name:
                out.append(n)
    return out


def _const_strs(call) -> list:
    return [a.value for a in call.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def _t_key(call) -> str:
    """`mk_btn(t('…'), …)` / `mk_field(t('…'), …)` 里的那个中文 key。
        English:
    The Chinese key inside `mk_btn(t('...'), ...)` / `mk_field(t('...'), ...)`.
    """
    if not call.args:
        return ''
    a = call.args[0]
    if isinstance(a, ast.Call) and getattr(a.func, 'id', None) == 't' and a.args:
        if isinstance(a.args[0], ast.Constant) and isinstance(a.args[0].value, str):
            return a.args[0].value
    return ''


def _unparse(n) -> str:
    try:
        return ast.unparse(n)
    except Exception:                                        # noqa: BLE001
        return ''


def group_a() -> None:
    print('\n' + '=' * 62 + '\nA 组 · 轮数上限是配置项（AST / 源码级）', flush=True)

    from config import SPEC
    spec = SPEC.get('POLISH_MAX_ROUNDS')
    ok('A1 `POLISH_MAX_ROUNDS` 在 SPEC 里，且是 int',
       isinstance(spec, dict) and spec.get('type') == 'int', str(spec)[:120])
    ok('A2 默认 10 轮，上下限合理（1 ≤ min < default ≤ max）',
       bool(spec) and spec.get('default') == 10
       and 1 <= spec.get('min', 0) < 10 <= spec.get('max', 0),
       f"default={spec.get('default')} min={spec.get('min')} max={spec.get('max')}")
    ok('A3 读出来就是 .env 里那个值（CFG.i 走通）',
       int(CFG.i('POLISH_MAX_ROUNDS') or 0) > 0,
       f"CFG.i('POLISH_MAX_ROUNDS') = {CFG.i('POLISH_MAX_ROUNDS')!r}")

    tree = _ast()
    # ★ 防"假旋钮"：SPEC 里有、界面上有，但**产品源码从来不读**。
    # [EN] ★ Guard against "fake knobs": present in SPEC, present in the UI, but **never read by the
    # [EN] product source**.
    reads = [c for c in _calls(tree, 'i') if _const_strs(c)[:1] == ['POLISH_MAX_ROUNDS']]
    ok('A4 ★★ 产品源码真的**读**它（不是假旋钮）',
       bool(reads), f'CFG.i(\'POLISH_MAX_ROUNDS\') 出现 {len(reads)} 次')
    writes = [c for c in _calls(tree, 'set') if _const_strs(c)[:1] == ['POLISH_MAX_ROUNDS']]
    ok('A5 ★★ 天机保存时真的**写**它（改完能存进 .env）',
       bool(writes), f'CFG.set(\'POLISH_MAX_ROUNDS\') 出现 {len(writes)} 次')

    fields = [_t_key(c) for c in _calls(tree, 'mk_field')]
    ok('A6 天机里有一个输入框叫「优化轮数」（有地方配置）',
       '优化轮数' in fields, str([x for x in fields if '轮' in x or '步' in x or '工具' in x]))
    ok('A7 另外两个上限（每轮步数 / 工具次数）也一起露出来了',
       '每轮步数' in fields and '工具次数' in fields, str(fields[-6:]))
    ok('A8 天机里那一小节的标题是「开卷打磨」',
       any(_t_key(c) == '开卷打磨' for c in _calls(tree, 'mk_section')), '')

    # 按钮接线：`mk_btn(t('⏹ 强制停止'), on_click=lambda e: _stop_ai())`
    # [EN] Button wiring: `mk_btn(t('⏹ Force stop'), on_click=lambda e: _stop_ai())`
    stop_calls = [c for c in _calls(tree, 'mk_btn') if _t_key(c) == '⏹ 强制停止']
    wired = False
    for c in stop_calls:
        for kw in c.keywords:
            if kw.arg != 'on_click':
                continue
            body = kw.value.body if isinstance(kw.value, ast.Lambda) else kw.value
            if '_stop_ai' in _unparse(body):
                wired = True
    ok('A9 ★★ 「⏹ 强制停止」按钮真的接在 `_stop_ai` 上（不是空按钮）',
       bool(stop_calls) and wired, f'按钮 {len(stop_calls)} 个，接线={wired}')

    ui_keys = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            for k in n.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    ui_keys.add(k.value)
    ok('A10 `state[\'ui\']` 暴露了 stop / stop_btn（自动化与判据能驱动它）',
       {'stop', 'stop_btn'} <= ui_keys, str(sorted(x for x in ui_keys if 'stop' in x)))

    # ★ 上限判据必须是 `>=`：写成 `>` 就等于偷偷多给一轮。
    # [EN] ★ The limit check must be `>=`: writing `>` silently grants one extra round.
    ge = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and n.ops and isinstance(n.ops[0], ast.GtE):
            left, right = _unparse(n.left), _unparse(n.comparators[0])
            if "state['exchange']" in left and 'max_rounds' in right:
                ge.append(f'{left} {right}')
    ok('A11 ★★ 上限判定用 `>=`（写成 `>` 就会多跑一轮）',
       bool(ge), str(ge))

    # 到上限时要**留出口**：`_lock_input` 里 finish_btn 必须是 False（亮着）
    # [EN] At the limit there must be **an exit**: in `_lock_input`, finish_btn must be False (lit).
    lock = next((n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == '_lock_input'), None)
    kept = False
    if lock is not None:
        for a in ast.walk(lock):
            if isinstance(a, ast.Assign) and len(a.targets) == 1:
                tg = a.targets[0]
                if (isinstance(tg, ast.Attribute) and tg.attr == 'disabled'
                        and 'finish_btn' in _unparse(tg.value)
                        and isinstance(a.value, ast.Constant) and a.value.value is False):
                    kept = True
    ok('A12 ★★ 到上限时**输入锁、但「完成优化并进入」仍然亮着**',
       kept, '没找到 finish_btn.disabled = False')

    env_ex = (APP_DIR / '.env.example').read_text(encoding='utf-8')
    ok('A13 `.env.example` 里有这一项（公开配置，手改也有据可依）',
       'POLISH_MAX_ROUNDS=' in env_ex, '')
    env_real = (APP_DIR / '.env').read_text(encoding='utf-8')
    ok('A14 `.env` 里也有（默认值 10，用户能直接看见并改）',
       'POLISH_MAX_ROUNDS=10' in env_real, '')

    # ★ 只查 `t('…')` 的字面量（AST），不查整份源码 —— 源码里那句**注释**
    #   本来就在讲"以前写错过什么"，拿整份文本查会把注释也算进去（第一版就假红）。
    # ⚠ 特征串要挑准：光查「项目与运行」会误命中「正在创建项目与运行文件夹…」
    #   （那是另一个意思的词组）。旧文案的特征是**同时**出现页签名与变量名。
    # [EN] ★ Only check literals of `t('...')` (AST), do not check the whole source — the **comment** in
    # [EN] the source
    # [EN] is already talking about "what was written wrong before"; searching the whole text would count
    # [EN] the comment too (the first version gave a false red).
    # [EN] (that is a phrase with a different meaning). The old copy's feature is the page-tab name and the
    # [EN] variable name appearing **simultaneously**.
    t_texts = []
    for c in _calls(tree, 't'):
        t_texts.extend(x for x in _const_strs(c) if x)
    bad_ref = [x for x in t_texts if 'POLISH_AGENT' in x or '「项目与运行」' in x]
    ok('A15 界面上那句指向不存在的页签的提示已经改掉'
       '（原来写「天机 · 项目与运行 → POLISH_AGENT」，天机根本没有这一页）',
       not bad_ref, str(bad_ref[:2]))
    ok('A15b 而且换成了**真的存在**的那一节'
       '（向导里指的是天机 ·「运行」→「开卷打磨」）',
       any('开卷打磨' in x for x in t_texts), '')

    # ══════════════════════════════════════════════════════════
    #  A16/A17/A18 ★★ 聊天输入框**三行高** + 右侧按钮**居中到中间行**
    #  用户 2026-10-11：「你看下快卷(开卷)摄取的步骤 **最下面那个聊天输入的框**
    #  我希望可以高度高一些 **比如3行**，然后对应的 **右侧的发送/强制停止的按钮**
    #  **移动到中间行**」。两条都用 AST 判（不看字符串）：
    #    · A17 输入框那句 `ft.TextField(...)` 必须带 `multiline=True`、
    #      `min_lines` / `max_lines` 都等于 `CHAT_INPUT_LINES`，而且**不许写 `height`**。
    #      ⚠ 为什么不许写 `height`：实测（2026-10-11）本版 Flet 的
    #        `TextField.height` **根本不起作用** —— 写 `height=72` 加三行也只画 62px、
    #        只写 `height=72` 画 45px。行数只能靠 `min_lines`/`max_lines`；
    #        留着那个 `height` 是**谎话**，后来按它算版面的人会算错。
    #    · A18 装它的那个 `ft.Row` 显式写着 `vertical_alignment=CENTER`。
    #      ⚠ 这条只是**防将来默认值变**：实测本版 Flet 的 `Row`
    #        `vertical_alignment` **默认就是 CENTER**（与 Flutter 的 START 相反）。
    #        真正证明"按钮落在中间行"的是真机那条 B4b（量中心距）。
    # [EN] ══════════════════════════════════════════════════════
    # [EN] A16/A17/A18 ★★ The chat input is **three lines tall** + the right-hand buttons are
    # [EN] **centred onto the middle line**
    # [EN] User 2026-10-11: "look at the ingestion step of opening a book -- **the chat input at the
    # [EN] bottom**, I'd like it taller, **say 3 lines**, and the **Send / Force-stop buttons on its
    # [EN] right** should **move to the middle line**". Both are judged with AST (no string greps):
    # [EN] · A17 the `ft.TextField(...)` must carry `multiline=True`, `min_lines` / `max_lines` equal to
    # [EN] `CHAT_INPUT_LINES`, and **must not write `height`**.
    # [EN] ⚠ Why no `height`: measured (2026-10-11), `TextField.height` **has no effect at all** in this
    # [EN] version of Flet -- `height=72` with three lines still paints 62px, and `height=72` alone
    # [EN] paints 45px. The line count can only come from `min_lines`/`max_lines`; keeping that `height`
    # [EN] would be a **lie** and whoever computes the layout from it later would get it wrong.
    # [EN] · A18 the `ft.Row` holding it explicitly writes `vertical_alignment=CENTER`.
    # [EN] ⚠ This is only a **guard against the default changing**: measured, `Row.vertical_alignment`
    # [EN] **already defaults to CENTER** in this Flet (opposite of Flutter's START). What really proves
    # [EN] "the buttons land on the middle line" is the real-machine B4b (measuring the centre distance).
    # [EN] ══════════════════════════════════════════════════════    # [EN] ══════════════════════════════════════════════════════
    # [EN] A16/A17 ★★ The chat input is **three lines tall** + the right-hand buttons are **centred onto
    # [EN] the middle line**
    # [EN] User 2026-10-11: "look at the ingestion step of opening a book -- **the chat input at the
    # [EN] bottom**, I'd like it taller, **say 3 lines**, and the **Send / Force-stop buttons on its
    # [EN] right** should move **up or down onto the middle line**".
    # [EN] Both are judged with AST (no string greps):
    # [EN] · The `ft.TextField(...)` for the input must carry `multiline=True`,
    # [EN] `min_lines` / `max_lines` = `CHAT_INPUT_LINES`, and `height = SET_H * CHAT_INPUT_LINES`;
    # [EN] ⚠ The height **must be written as the arithmetic "lines x SET_H"**, not the literal 72 --
    # [EN] `SET_H` is recomputed by `apply_font_settings()` from the font-size setting, and hardcoding
    # [EN] 72 would turn "three lines" into "two and a half" (text clipped) as soon as the font grows.
    # [EN] · The `ft.Row([chat_input, send_btn, stop_btn])` holding it must have
    # [EN] `vertical_alignment=ft.CrossAxisAlignment.CENTER` (the default is START = top-aligned, which
    # [EN] would glue the buttons to the input's first line).
    # ══════════════════════════════════════════════════════════
    lines_val = -1
    for n in ast.walk(tree):
        if (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id == 'CHAT_INPUT_LINES'
                and isinstance(n.value, ast.Constant)):
            lines_val = int(n.value.value)
    ok('A16 ★★ 聊天输入框的行数是**一个具名常量**、值为 3'
       '（写死 3 会在别处再抄一遍，改的地方一多就会不一致）',
       lines_val == 3, f'CHAT_INPUT_LINES={lines_val}')

    tf_kw: dict = {}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id == 'chat_input'
                and isinstance(n.value, ast.Call)):
            for kw in n.value.keywords:
                if kw.arg in ('multiline', 'min_lines', 'max_lines', 'height'):
                    tf_kw[kw.arg] = _unparse(kw.value)
    ok('A17 ★★ 输入框：`multiline=True` + `min_lines`/`max_lines` 都等于那个常量、'
       '而且**不写 `height`**'
       '（⚠ 实测：本版 Flet 的 `TextField.height` 不起作用 —— 写 72 也只画 62，'
       '行数只能靠 `min_lines`/`max_lines`；写了 `height` 是**谎话**，'
       '将来按它算版面的人会算错）',
       tf_kw.get('multiline') == 'True'
       and tf_kw.get('min_lines') == 'CHAT_INPUT_LINES'
       and tf_kw.get('max_lines') == 'CHAT_INPUT_LINES'
       and 'height' not in tf_kw,
       str(tf_kw))

    row_center = False
    for c in _calls(tree, 'Row'):
        if not any('chat_input' in _unparse(x) for x in c.args):
            continue
        for kw in c.keywords:
            if kw.arg == 'vertical_alignment' and 'CENTER' in _unparse(kw.value):
                row_center = True
        break
    # ⚠ 这条是**防默认值变**的守卫，不是"居中靠它"：实测本版 Flet 的 `Row`
    #   `vertical_alignment` **默认就是 CENTER**（与 Flutter 的 START 相反）。
    #   真正的行为判据是 B4b（量按钮文字中心与输入框中心的距离）——
    #   变异 ⑬ 把这里写成 `START`，**B4b 会红**，这一条也会红。
    # [EN] ⚠ This is a guard **against the default changing**, not "centring depends on it": measured,
    # [EN] this Flet's `Row.vertical_alignment` **already defaults to CENTER** (opposite of Flutter's
    # [EN] START). The real behavioural criterion is B4b (measuring the distance between the button text
    # [EN] centre and the input centre) -- mutant ⑬ writes `START` here and **B4b goes red**, as does this
    # [EN] one.
    ok('A18 ★★ 那一行**显式写着垂直居中**（真居中靠的是"输入框比按钮高" + '
       'Flet 的默认值；这里写出来是防将来默认值改成 START）',
       row_center, 'Row(chat_input, send_btn, stop_btn) 上没找到 CENTER')


I18N_KEYS = [
    '⏹ 强制停止', '开卷打磨', '优化轮数', '每轮步数', '工具次数', '打磨中', '开场体检',
    '⏹ 已强制停止（这一轮作废，已改的设定保留）',
    '⏹ 已达轮数上限（{n} 轮）—— 等你收工',
    '⏹ 这一轮被你停掉了（已经改好的设定保留，可以继续说下一句）。',
    'AI 正在处理：{what}（想停就点「⏹ 强制停止」）',
    '[{ts}] ⏹ 你按了「强制停止」—— 正在打断这一轮 AI…',
    '[{ts}] ⏹ 你按了「强制停止」—— 优化到此为止，开始收尾',
    '[{ts}] ⏹ 第 {n} 轮已强制停止（改动的部分保留）',
    '[{ts}] ⏹ 已到 AI 优化轮数上限（{n} 轮）—— 不再收新指令，请点「完成优化并进入」',
    '[{ts}] 已到轮数上限（{n} 轮）—— 这条指令没有执行',
]


def group_i18n() -> None:
    print('\n' + '=' * 62 + '\nC 组 · i18n（英文界面下不许露出中文）', flush=True)
    set_lang('en')
    missing = [k for k in I18N_KEYS if t(k, n=1, ts='00:00:00', what='x') == k]
    set_lang(_lang)
    ok('C1 ★ 本轮新加的 16 条文案都有英文', not missing, str(missing))


# ══════════════════════════════════════════════════════════════════
#  B 组：真机
# [EN] Group B: real machine
# ══════════════════════════════════════════════════════════════════
def make_fixture(root: Path) -> Path:
    src = root / '轮数与叫停'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text(
        '# 大纲\n\n起：雨夜来客打破平静。\n承：旧事被翻出。\n转：最可信的人露出破绽。\n合：有人离开。\n',
        encoding='utf-8')
    (src / '人物设定.md').write_text(
        '# 人物\n\n## 主角\n掌柜，沉默寡言。\n\n## 阿枝\n伙计，嘴上不饶人。\n', encoding='utf-8')
    (src / '正文' / '第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。\n\n'
        '「你今日话里有话。」\n\n「话就是话，哪来的里外。」\n' * 8, encoding='utf-8')
    return src


def chat_texts(chat) -> list:
    """右侧对话栏里所有气泡的字（气泡 = Column → Container → Text）。
        English:
    The text of every bubble in the right-hand chat panel (bubble = Column → Container → Text).
    """
    out: list = []
    for row in (getattr(chat, 'controls', None) or []):
        for c in (getattr(row, 'controls', None) or []):
            if isinstance(c, ft.Container):
                inner = c.content
                out.append(str(getattr(inner, 'value', inner) or ''))
    return out


async def wait_until(pred, timeout: float = 40.0, step: float = 0.1) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:                                    # noqa: BLE001
            pass
        await asyncio.sleep(step)
    return False


async def shot(page, name: str, note: str) -> None:
    try:
        page.update()
        await asyncio.sleep(0.35)
        data = await page.take_screenshot()
        fname = name.replace('.png', f'{SUFFIX}.png')
        (OUT / fname).write_bytes(data)
        report.setdefault('shots', []).append({'shot': fname, 'note': note})
    except Exception as e:                                   # noqa: BLE001
        report.setdefault('shots', []).append({'shot': name, 'error': str(e)})


def marker_bbox(png: bytes, rgb: tuple, tol: int = 40) -> dict | None:
    """某个标记色的像素包围盒（`None` = 一个点都没量到）。

    ⚠ **走 C 层**（`ImageChops` 求差 + `point` 二值化 + `getbbox`）：
      逐像素的 Python 双重循环在 1280×900 上要十几秒，本支要量两次。
    [EN] Pixel bounding box of a marker color (`None` = not a single point measured).
    [EN] ⚠ **Go through the C layer** (`ImageChops` difference + `point` threshold + `getbbox`): a
    [EN] pixel-by-pixel Python loop takes a dozen seconds on 1280x900, and this branch measures twice.
    """
    import io
    from PIL import Image, ImageChops
    im = Image.open(io.BytesIO(png)).convert('RGB')
    ref = Image.new('RGB', im.size, tuple(int(v) for v in rgb))
    d = ImageChops.difference(im, ref)
    r, g, b = d.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    bb = mx.point(lambda v: 255 if v <= tol else 0, mode='1').getbbox()
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    return {'x0': x0, 'y0': y0, 'x1': x1 - 1, 'y1': y1 - 1,
            'w': x1 - x0, 'h': y1 - y0, 'cy': (y0 + y1 - 1) / 2.0}


def count_magenta(png: bytes) -> int:
    """数"品红像素"（标记色法）。用 `point` + `ImageChops` 做，不逐像素循环 ——
    `getdata()` 已被 Pillow 标成弃用，2 百万像素的 Python 循环也慢。
        English:
    Count "magenta pixels" (marker-color method). Use `point` + `ImageChops`, not a per-pixel loop —
        `getdata()` has been marked deprecated by Pillow, and a Python loop over 2 million pixels is also slow.
    """
    import io
    from PIL import Image, ImageChops
    im = Image.open(io.BytesIO(png)).convert('RGB')
    r, g, b = im.split()
    m = ImageChops.multiply(
        ImageChops.multiply(r.point(lambda v: 255 if v > 225 else 0),
                            b.point(lambda v: 255 if v > 225 else 0)),
        g.point(lambda v: 255 if v < 70 else 0))
    return int(m.histogram()[255])


async def test_gui(page: ft.Page) -> None:                   # noqa: C901
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_rounds_'))
    VU.isolate_projects_dir(tmp / 'Projects')

    # ── B0 天机 ·「运行」→「开卷打磨」：三个数真的在界面上 ──
    # [EN] ── B0 Tianji · "Run" → "Open-book polishing": the three numbers really are on the interface ──
    print('\n' + '=' * 62 + '\nB 组 · 真机', flush=True)
    # ⚠ 2026-10-12：改用常量（页序一变，写死的 3 就点到别的页了）。
    # [EN] ⚠ 2026-10-12: use the constant (a page-order change makes a hardcoded 3 land
    # [EN] elsewhere).
    app.show_global_settings(tab=NovelWorldApp.TAB_GLOBAL_RUN)
    # [EN] 3 = the 「运行」 page
    page.update()
    await asyncio.sleep(0.8)
    dlg = VU.open_dialogs(page)[-1] if VU.open_dialogs(page) else None
    lf = VU.labelled_fields(dlg) if dlg is not None else {}
    ok('B0 天机「运行」页里有「优化轮数」输入框',
       '优化轮数' in lf, str(list(lf)[-8:]))
    got = None
    if '优化轮数' in lf:
        got = str(getattr(lf['优化轮数']._field, 'value', ''))
    ok('B0b 框里显示的就是 `.env` 里那个值（不是空、也不是别的数）',
       got is not None and got.strip() == str(CFG.i('POLISH_MAX_ROUNDS')),
       f'框里={got!r} 配置={CFG.i("POLISH_MAX_ROUNDS")!r}')
    ok('B0c 另外两个上限也在同一页',
       '每轮步数' in lf and '工具次数' in lf, str(list(lf)[-8:]))
    await shot(page, 'ingest_rounds_0_settings.png', '天机 · 运行 · 开卷打磨')
    for _ in range(len(VU.open_dialogs(page))):
        try:
            page.pop_dialog()
        except Exception:                                    # noqa: BLE001
            pass
    page.update()
    await asyncio.sleep(0.4)

    # ── 开卷：夹具很小，MOCK 下几秒就跑完 ──
    # [EN] ── Kaijuan: the fixture is tiny, under MOCK it finishes in a few seconds ──
    src = make_fixture(tmp)
    VU.disable_source_repair(app)            # 那一步会停下等点击，脚本里跳过
    # [EN] That step stops and waits for a click; skip it in the script.
    app.show_import_wizard()
    page.update()
    await asyncio.sleep(0.5)
    app._wizard_path = str(src)
    app._wizard_name = '轮数与叫停'
    app._wizard_opts['ai_optimize'] = True
    VU.disable_source_repair(app)

    # ★ 轮数上限设成 **2**（脚本级；`redirect_env_writes` 保证不落盘）。
    #   ⚠ 必须设在 `_do_import` **之前** —— 它是在那一刻读进 `state['max_rounds']` 的。
    # [EN] ★ Set the round limit to **2** (script level; `redirect_env_writes` ensures it is not written to
    # [EN] disk).
    # [EN] ⚠ Must be set **before** `_do_import` — it reads into `state['max_rounds']` at that moment.
    CFG.set('POLISH_MAX_ROUNDS', '2')
    app._do_import(page)
    st = app._ingest_state
    ui = (st or {}).get('ui') or {}

    ok('B1 自动摄取阶段：「⏹ 强制停止」是灰的（这一手不该乱接）',
       ui.get('stop_btn') is not None and bool(ui['stop_btn'].disabled),
       f"disabled={getattr(ui.get('stop_btn'), 'disabled', None)}")

    # ── 同意门（夹具含正文，必然出现）──
    # [EN] ── Consent gate (the fixture contains the body text, so it always appears) ──
    await wait_until(lambda: bool(ui.get('consent_panel')) and ui['consent_panel'].visible, 30)
    for b in (ui.get('consent_boxes') or []):
        b.value = True
        if getattr(b, 'on_change', None):
            b.on_change(None)
    if ui.get('consent'):
        ui['consent'](True)

    entered = await wait_until(lambda: st.get('phase') == 'chat', 90)
    ok('B2 摄取跑到了 AI 优化阶段', entered, f"phase={st.get('phase')!r}")
    ui = st.get('ui') or {}
    ok('B2b 进 AI 优化阶段后「⏹ 强制停止」变成可点',
       bool(ui.get('stop_btn')) and not ui['stop_btn'].disabled,
       f"disabled={getattr(ui.get('stop_btn'), 'disabled', None)}")
    ok('B2c 输入框 / 发送也解锁了（能下指令）',
       not ui['chat_input'].disabled and not ui['send_btn'].disabled, '')

    # ── 像素取证：「⏹ 强制停止」**真的画出来了**（树里有 ≠ 看得见）──
    # [EN] ── Pixel evidence: 「⏹ Force stop」 is **actually drawn** (being in the tree ≠ being visible) ──
    await asyncio.sleep(0.5)
    before = await page.take_screenshot()
    n_before = count_magenta(before)
    mark = ui.get('stop_btn')
    old_color = None
    try:
        if mark is not None and isinstance(getattr(mark, 'content', None), ft.Text):
            old_color = mark.content.color
            mark.content.color = '#ff00ff'          # 只动颜色，不动几何
            # [EN] Only change color, not geometry.
            page.update()
            await asyncio.sleep(0.4)
            after = await page.take_screenshot()
            n_after = count_magenta(after)
        else:
            n_after = -1
    finally:
        if mark is not None and old_color is not None:
            mark.content.color = old_color
            page.update()
    ok('B3 ★★ 那个按钮**屏幕上真的画出来了**（标记色法：品红像素 > 30）',
       n_after - n_before > 30, f'未标记 {n_before} → 标记后 {n_after}')
    await shot(page, 'ingest_rounds_1_chat.png', 'AI 优化阶段：输入框 + 发送 + ⏹ 强制停止')

    # ── B4/B4b ★★ 输入框**三行高**、右侧按钮**落在中间那一行**（2026-10-11 用户要求）──
    #   ⚠ 两件都必须**量像素**：
    #     · "高了三行"是画出来的高度，不是 `height=` 那个数 —— Flet 会按
    #       `min_lines` / 主题内边距再算一遍，属性写了 72、屏幕上画成 40 也有可能；
    #     · "按钮在中间行"靠的是**按钮文字的中心 y** 与**输入框的中心 y** 对不对得上
    #       （只看 `vertical_alignment` 属性是"钉代码形状"，不是行为）。
    #   ⚠ 标记色：输入框涂品红、按钮文字涂青（调色板里都没有这两个纯色）。
    # [EN] ── B4/B4b ★★ The input is **three lines tall** and the right-hand buttons **land on the
    # [EN] middle line** (user request 2026-10-11) ──
    # [EN] ⚠ Both must be **measured in pixels**:
    # [EN] · "three lines tall" is the painted height, not the `height=` number -- Flet recomputes from
    # [EN] `min_lines` / theme padding, so a property of 72 could still paint as 40;
    # [EN] · "the button is on the middle line" depends on whether the **text centre of the button**
    # [EN] lines up with the **centre of the input** (checking `vertical_alignment` alone pins the shape
    # [EN] of the code, not the behaviour).
    # [EN] ⚠ Marker colors: magenta for the input box, cyan for the button text (neither pure color is in
    # [EN] the palette).
    m_in, m_stop = ui.get('chat_input'), ui.get('stop_btn')
    # 上面那两栏纸卡也涂一下：**"把输入框垫高"不能靠"把两栏压没"来实现** ——
    # 外层 `body` 的高度是**写死的** `ING_H`，多出来的高度必须从别处让。
    # [EN] Also paint the two paper cards above: **"making the input taller" must not be achieved by
    # [EN] "squeezing the two columns away"** -- the outer `body` height is the **hardcoded** `ING_H`, so
    # [EN] the extra height has to come from somewhere.
    pane_cards = [c for c in VU.walk(ui.get('panes'))
                  if isinstance(c, ft.Container)
                  and getattr(c, 'bgcolor', None) == G.C['input_bg']]
    in_box: dict = {}
    old_in_bg = getattr(m_in, 'bgcolor', None)
    old_tx = None
    old_pane = []
    try:
        if m_in is not None:
            m_in.bgcolor = MARK_IN
        for c in pane_cards:
            old_pane.append((c, c.bgcolor))
            c.bgcolor = MARK_PANE
        if m_stop is not None and isinstance(getattr(m_stop, 'content', None), ft.Text):
            old_tx = m_stop.content.color
            m_stop.content.color = MARK_TXT
        page.update()
        await asyncio.sleep(0.5)
        png = await page.take_screenshot()
        in_box = marker_bbox(png, hex_rgb(MARK_IN)) or {}
        btn_box = marker_bbox(png, hex_rgb(MARK_TXT)) or {}
        pane_box = marker_bbox(png, hex_rgb(MARK_PANE)) or {}
    finally:
        if m_in is not None and old_in_bg is not None:
            m_in.bgcolor = old_in_bg
        for c, col in old_pane:
            c.bgcolor = col
        if m_stop is not None and old_tx is not None and isinstance(
                getattr(m_stop, 'content', None), ft.Text):
            m_stop.content.color = old_tx
        page.update()
    # ⚠ `SET_H` 要**现读 `G.SET_H`**：它会被 `apply_font_settings()` 按字号设置
    #   重算，`from … import SET_H` 拿的是导入那一刻的旧值。
    # [EN] ⚠ `SET_H` must be read **live from `G.SET_H`**: it is recomputed by `apply_font_settings()`
    # [EN] from the font-size setting, so `from ... import SET_H` would capture a stale value.
    one_line = int(G.SET_H)
    report['chat_box'] = {'box_h': in_box.get('h'), 'one_line': one_line,
                          'box_cy': in_box.get('cy'), 'btn_cy': btn_box.get('cy'),
                          'pane_h': pane_box.get('h'), 'pane_y1': pane_box.get('y1'),
                          'box_y0': in_box.get('y0')}
    # ⚠ **尺子写宽一点是故意的**：量到的是"画出来的高度"，而一行到底多少像素由
    #   字体与 Flutter 的行距决定（本机实测：单行框 ≈ `SET_H` = 24px，
    #   三行框 = 62px —— 62 < 72，因为内边距与边框**只算一次**）。
    #   ⇒ 判的是"**明显不止一行、而且大约三行**"（2.4 ~ 3.6 倍单行高）；
    #     写死 72 会把正确实现判红（第一版就是这样）。
    # [EN] ⚠ **The band is deliberately wide**: what is measured is the *painted* height, and how many
    # [EN] pixels a line is depends on the font and Flutter's line spacing (measured here: a single-line
    # [EN] box ≈ `SET_H` = 24px, a three-line box = 62px -- 62 < 72 because padding and border are
    # [EN] counted **once**). ⇒ What is judged is "**clearly not one line, and about three**"
    # [EN] (2.4x to 3.6x the single-line height); pinning 72 would fail a correct implementation (that is
    # [EN] exactly what the first version did).
    ok('B4 ★★ 输入框**屏幕上真的有三行高**（标记色量高：≈ 3 × 单行高，2.4~3.6 倍）'
       '—— 属性写了什么不等于画出来是多少',
       bool(in_box) and 2.4 * one_line <= in_box['h'] <= 3.6 * one_line,
       f"实测高 {in_box.get('h')}px｜单行 {one_line}px｜比值 "
       f"{round(in_box['h'] / one_line, 2) if in_box.get('h') else '-'}｜"
       f"输入框 y0={in_box.get('y0')}")
    ok('B4c ★ 上面那两栏**没有被压没**（纸卡高 ≥ 120px，'
       '且它整条在输入框上方：垫高输入框的高度是从别处让出来的）',
       bool(pane_box) and pane_box['h'] >= 120
       and (not in_box or pane_box['y1'] < in_box['y0']),
       f"纸卡高 {pane_box.get('h')}px · y1={pane_box.get('y1')} · "
       f"输入框 y0={in_box.get('y0')}")
    ok('B4b ★★ 右侧按钮**落在输入框的中间那一行**'
       '（按钮文字中心 y 与输入框中心 y 相差 ≤ 8px）',
       bool(in_box) and bool(btn_box)
       and abs(in_box['cy'] - btn_box['cy']) <= 8,
       f"输入框中心 y={in_box.get('cy')}｜按钮文字中心 y={btn_box.get('cy')}")

    # ══ 强制停止：把 `PolishAgent.ask` 换成"要跑很久"的实现，
    #    这样"打断正在跑的那一轮"才有东西可打断（MOCK 是毫秒级的）。
    # [EN] ══ Force stop: replace `PolishAgent.ask` with an implementation that "takes a long time",
    # [EN] so that "interrupting the round currently running" has something to interrupt (MOCK is
    # [EN] millisecond-level).
    from polish.agent import PolishAgent
    fired = {'cancelled': False, 'entered': False}
    _orig_ask = PolishAgent.ask

    async def _slow_ask(self, instruction):
        fired['entered'] = True
        try:
            await asyncio.sleep(60)          # 用户想打断的就是这一刻
            # [EN] The moment the user wants to interrupt is exactly this one.
            return await _orig_ask(self, instruction)
        except asyncio.CancelledError:
            fired['cancelled'] = True
            raise

    PolishAgent.ask = _slow_ask
    try:
        ui['chat_input'].value = '把主角的秘密改成和那口井有关。'
        ui['send'](None)
        live = await wait_until(lambda: st.get('round_task') is not None, 10)
        ok('B4 一轮真的跑起来了（`state[\'round_task\']` 有活的句柄，'
           '而且慢版 `ask` 真的进去了）',
           live and not st['round_task'].done() and fired['entered'],
           f"live={live} entered={fired['entered']}")
        await asyncio.sleep(0.4)
        ui['stop_btn'].on_click(None)        # ★ 走**真实点击路径**
        # [EN] ★ Go through the **real click path**.
        gone = await wait_until(lambda: st.get('round_task') is None, 15)
        ok('B5 ★★★ 点「⏹ 强制停止」—— 那一轮的任务真的被取消了',
           fired['cancelled'], f'cancelled={fired["cancelled"]}')
        ok('B5b 停止后句柄清空（不会留一个假的"正在跑"）', gone, '')
        await asyncio.sleep(0.8)
        bubbles = chat_texts(ui['chat_list'])
        ok('B5c ★★ 对话栏里明说了「这一轮被你停掉了」（不是静默消失）',
           any('被你停掉了' in b for b in bubbles), str(bubbles[-2:]))
        logs = VU.log_cells(ui['log_list'].controls)
        ok('B5d 左侧日志里也有「已强制停止」那条',
           any('已强制停止' in str(x) for x in logs), str([x for x in logs if '停止' in str(x)][-2:]))
        ok('B5e ★★ 停的是**这一轮**、不是整趟摄取 —— 停在 AI 优化阶段，还能接着说',
           st.get('phase') == 'chat' and st.get('running') is not False
           and not ui['chat_input'].disabled, f"phase={st.get('phase')!r}")
        ok('B5f 被停的那一轮也计入轮次（钱花了就得算）',
           int(st.get('exchange') or 0) == 1, f"exchange={st.get('exchange')}")
    finally:
        PolishAgent.ask = _orig_ask

    await shot(page, 'ingest_rounds_2_stopped.png', '强制停止之后：留在原处，还能继续下指令')

    # ══ 轮数上限：cap=2，已经用掉 1 轮 → 再发一条就该到顶
    # [EN] ══ Round limit: cap=2, 1 round already used → sending one more should hit the ceiling.
    ui['chat_input'].value = '再给主角补一条口癖。'
    ui['send'](None)
    hit = await wait_until(lambda: bool(st.get('rounds_full')), 60)
    ok('B6 ★★★ 跑到上限（2 轮）就停住了', hit, f"exchange={st.get('exchange')}")
    ok('B6b 轮次正好是上限那个数（不多跑一轮）',
       int(st.get('exchange') or 0) == 2, f"exchange={st.get('exchange')}")
    ok('B6c 到上限：输入框与发送都变灰（不再收新指令）',
       bool(ui['chat_input'].disabled) and bool(ui['send_btn'].disabled), '')
    ok('B6d ★★★ 但「完成优化并进入」**仍然是亮的**（出口不能一起关）',
       not ui['finish_btn'].disabled, f"finish_btn.disabled={ui['finish_btn'].disabled}")
    logs = VU.log_cells(ui['log_list'].controls)
    ok('B6e 左侧日志点明了「已到 AI 优化轮数上限」',
       any('轮数上限' in str(x) for x in logs), str([x for x in logs if '上限' in str(x)][-1:]))
    logs_join = '\n'.join(str(x) for x in logs)
    bubbles = chat_texts(ui['chat_list'])
    ok('B6f ★★ 右侧对话栏里也有那条说明（用户原话：只落左侧"可能看不见"）',
       any('轮数上限' in b for b in bubbles), str(bubbles[-2:]))

    # ══ 上限不是摆设：硬塞一条（绕开灰掉的按钮，直接调发送）
    # [EN] ══ The limit is not decoration: force one in (bypass the greyed-out button, call send directly).
    ui['chat_input'].value = '这条应该不执行。'
    ui['send'](None)
    await asyncio.sleep(1.5)
    ok('B7 ★★ 到上限之后塞进来的指令**真的不执行**',
       int(st.get('exchange') or 0) == 2,
       f"exchange={st.get('exchange')}")
    logs = VU.log_cells(ui['log_list'].controls)
    ok('B7b 而且说清了"这条指令没有执行"',
       any('这条指令没有执行' in str(x) for x in logs), '')

    # ══ 收工：上限不许把出口堵死
    # [EN] ══ Wrap up: the limit must not seal off the exit.
    ui['finish_btn'].on_click(None)
    done = await wait_until(lambda: getattr(app, '_view', '') == 'main', 90)
    ok('B8 ★★ 点「完成优化并进入」仍然走得通（进了运行界面）',
       done and app.current_project is not None, f"view={app._view!r}")
    proj = app.current_project
    # ⚠ 任务简介写在**运行文件夹**里（`RunFolder.write_task_intro`），
    #   不是项目根 —— 第一版就按项目根找，什么都没找到（detail 空白）。
    # [EN] ⚠ The task intro is written in the **run folder** (`RunFolder.write_task_intro`),
    # [EN] not the project root — the first version looked in the project root and found nothing (detail
    # [EN] was blank).
    intro = next(iter(sorted(proj.root.rglob('任务介绍.md'))), None) if proj else None
    body = intro.read_text(encoding='utf-8') if (intro and intro.is_file()) else ''
    # 行长得像 `- **AI 优化轮次**：2` —— 别写 `split(...)[-1].startswith('2')`，
    # 中间还隔着 `**：`（第一版就这么假红了一次）。
    # [EN] The line looks like `- **AI 优化轮次**：2` — do not write `split(...)[-1].startswith('2')`,
    # [EN] there is still `**：` in between (the first version went false red once this way).
    import re as _re
    m = _re.search(r'AI 优化轮次\*{0,2}\s*[：:]\s*(\d+)', body)
    ok('B8b 轮次记进了本轮的任务简介（`AI 优化轮次` = 2，与上限一致）',
       bool(m) and m.group(1) == '2', f'{m.group(1) if m else None} · {intro}')
    await shot(page, 'ingest_rounds_3_main.png', '收工进了运行界面')

    ok('B9 `.env` 一个字节都没被这个脚本改过（`redirect_env_writes` 全程生效）',
       env_md5_ok(), f'{report.get("env_md5_before")} → {env_md5()}')


def env_md5() -> str:
    import hashlib
    p = APP_DIR / '.env'
    return hashlib.md5(p.read_bytes()).hexdigest()[:12] if p.is_file() else '(无 .env)'


def env_md5_ok() -> bool:
    return report.get('env_md5_before') == env_md5()


async def entry(page: ft.Page) -> None:
    report['env_md5_before'] = env_md5()      # 跑之前记一笔，最后核验没被写过
    # [EN] Record a note before running; verify at the end that it was never written.
    try:
        await test_gui(page)
    except BaseException:                                    # noqa: BLE001
        # ⚠ 崩溃**必须自己留一条红的** —— 否则报告里"全绿"与"脚本崩了"长得一样。
        # [EN] ⚠ On crash, **you must leave a red of your own** — otherwise "all green" and "script crashed"
        # [EN] look the same in the report.
        ok('（真机段执行中断）', False, traceback.format_exc()[:600])
    report['checks'] = checks
    report['ok'] = all(c['ok'] for c in checks) and bool(checks)
    report['passed'] = sum(1 for c in checks if c['ok'])
    report['total'] = len(checks)
    (OUT / f'ingest_rounds_report{SUFFIX}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n{report["passed"]}/{report["total"]} 通过 · ok={report["ok"]}', flush=True)
    await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    VU.redirect_env_writes()      # 全程不许写真实 .env（含 app.main 里的 CFG.save）
    # [EN] Never write the real .env at any point (including CFG.save in app.main).
    group_a()
    group_i18n()
    if '--logic-only' in sys.argv:
        report['checks'] = checks
        report['ok'] = all(c['ok'] for c in checks) and bool(checks)
        report['passed'] = sum(1 for c in checks if c['ok'])
        report['total'] = len(checks)
        report['logic_only'] = True
        (OUT / 'ingest_rounds_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n（--logic-only）{report["passed"]}/{report["total"]} 通过 '
              f'· ok={report["ok"]}', flush=True)
        raise SystemExit(0 if report['ok'] else 2)
    import flet as _ft
    _ft.run(entry)
