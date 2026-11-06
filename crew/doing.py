"""**当前正在做什么** —— 一个只有一处写入、任何地方都能读的小登记处。

★★★ 为什么要有它（2026-10-21 用户点名）：
  「每个阶段都要给出**正在做什么**；运行界面下面的**状态条要一直显示当前正在做什么
    以及做了多久**。」

  在这之前，"当前在做什么"这件事**没有任何地方持有**：
    · `Studio.stage()` 只在**做完之后**报一条「▸ 剧组排练 · 3.2s」——
      做的那几十秒里屏幕上什么都不动，用户分不出"在干活"和"卡死了"；
    · `Studio.call()` 报「某人 出工中」到中栏，但那条会被后面的叙事顶上去，
      而且状态条读不到它；
    · 状态条原来只有「运行中 · 第 3 天 · 已 120 秒」——那个"120 秒"是**状态持续时长**，
      不是"当前这步做了多久"。

  ⇒ 所以有一个**跨层可读**的当前动作，界面每 0.5 秒读一次拼进状态条。

★★★ 为什么是**栈**而不是一个变量（这条是实测逼出来的）：
  阶段是**嵌套**的 —— 「一天结束后讨论」（`day_review`）里面还要逐个跑
  场记 / 宣发 / 语言审校 / 复盘。如果用一个变量：

    · 内层 `call` 结束时把它清掉 ⇒ 外层还在跑，状态条**空了**（用户以为停了）；
    · 或者内层不清 ⇒ 外层结束时清的是内层的标签，状态条写着**已经做完的事**。

  栈天然对：**永远显示最内层**（最具体的那个动作），内层退出自动回落到外层。
  `pop(tok)` 按**令牌**弹，不按"弹栈顶" —— 乱序退出（异常路径）也不会弹错人。

★★★ 三条纪律（判据盯着）：
  1. **只有两个写入口**（`Studio.stage` / `Studio.call`）——多处各写一份，
     迟早出现"界面上写着在做 A、其实在跑 B"。
  2. **读不到就是空**（`snapshot()` 返回空 label）——不许编一个"正在思考"糊上去。
  3. **异常绝不影响推演**：这里只是展示，任何一处抛出去都会把真实的工作弄挂。

⚠ 为什么是模块级而不是挂在 `Studio` 上：状态条来自 `Session`，而 `Session` 在
  "装配中/启动中"那几步里还拿不到 studio（`session.loop` 可能还没建完）。
  模块级没有这个时序问题，也让判据能直接调。

    English:
    **What is happening right now** -- a tiny registry with one writer and any number of readers.

    ★★★ Why it exists (named by the user 2026-10-21): "every stage must say **what it is doing**;
    the status bar under the run screen must always show what is being done **and for how long**."

    Before this, nothing held "what is happening now": `Studio.stage()` reported only *after*
    finishing, so during those tens of seconds the screen showed nothing and the user could not tell
    "working" from "hung"; `Studio.call()` pushed "someone working" into the middle column where later
    narrative buries it, and the status bar could not read it; the status bar itself only showed
    "running · day 3 · 120s", where 120 s is the **status duration**, not the duration of this step.

    ★★★ Why a **stack** rather than one variable (forced by measurement): stages **nest** --
    "end-of-day discussion" runs continuity / publicity / language review / retrospective inside it.
    With a single variable, either the inner `call` clears it on exit (the outer is still running and
    the status bar goes **blank**, so the user thinks it stopped), or the inner leaves it (the outer's
    exit then clears the inner's label and the bar shows something already finished). A stack is
    naturally right: **always show the innermost** (most specific) action, and fall back to the outer
    when the inner exits. `pop(tok)` pops **by token**, not "by top" -- so out-of-order exits on
    exception paths cannot pop the wrong one.

    ★★★ Three rules (criteria watch them): 1) **two writing entry points** (`Studio.stage` /
    `Studio.call`); 2) **unreadable means empty** -- never fabricate "thinking..."; 3) **exceptions
    must never affect the simulation**.

    ⚠ Module-level rather than on `Studio`: the status bar comes from `Session`, and during
    "assembling/starting" the session may not have a studio yet.
"""
from __future__ import annotations

import itertools
import time

from i18n import t

#: **阶段 key → 中文名**。这是唯一一份（`display.story_render.stage_line`
#: 与状态条都从这里取）——两处各写一份，迟早出现"日志里叫这个名字、
#: 屏幕上叫那个名字"。
#:
#: ⚠ `t()` 必须在**调用时**求值（不能做成模块级常量），界面语言运行时可切。
# [EN] **stage key -> Chinese name**. The single copy: both `display.story_render.stage_line`
# [EN] and the status bar read it here.
_STAGE_LABELS: dict[str, str] = {
    'prep': '开拍前准备',
    'novelist': '作者写小说',
    'screenwriter': '剧作者写剧本',
    'rehearsal': '剧组排练',
    'rewrite': '带意见重新修改',
    'shooting': '开演',
    'pause': '临时暂停',
    'resume': '继续',
    'stopping': '收尾（落盘 + 总结）',
    'setting_room': '剧组重新修改设定细节',
    'day_map': '美术画当天地图',
    'day_review': '一天结束后讨论',
    'wrap_meeting': '总结会',
    'novelize': '整理当天这一章',
    'export': '导出',
}

#: 栈：每项 `{'tok', 'label', 't0'}`。
# [EN] The stack: each entry is `{'tok', 'label', 't0'}`.
_STACK: list[dict] = []
_TOK = itertools.count(1)


def stage_label(key: str) -> str:
    """阶段的中文名（认不出的 key **原样显示**，不猜、不编一个好听的名字）。

        English:
    The Chinese name of a stage. Unrecognized keys are **shown as-is** -- never guess, never invent a
    nice-sounding name.
    """
    k = str(key or '')
    zh = _STAGE_LABELS.get(k, '')
    return t(zh) if zh else k


def role_label(name: str, duty: str = '') -> str:
    """「场记 · 连戏检查」这种一行标签（角色名 + 职责的**第一截**）。

    为什么要截：`duty` 是完整一句话（"读当天样章，点名哪几句 AI 味重、该怎么改…"），
    状态条是**单行**，整句进去只会被省略号吃掉后半截，反而看不出在做什么。
    截到第一个标点或 14 字 —— 那是"这一位此刻在干什么"的最短可读形式。

        English:
    A one-line label like "场记 · 连戏检查" (role name + the **first clause** of its duty).
    Why cut: `duty` is a full sentence ("read today's sample, name which lines are AI-flavoured...")
    while the status bar is a **single line**; the whole sentence just gets eaten by an ellipsis and
    hides what is happening. Cut at the first punctuation mark or 14 chars -- the shortest readable
    form of "what this one is doing right now".
    """
    nm = str(name or '').strip()
    d = str(duty or '').strip()
    for i, ch in enumerate(d):
        if ch in '：；，。、·—-（(':
            d = d[:i]
            break
    # ⚠ 长度上限 **10 字**，而且**要断在词上**（2026-10-21 实测）：
    #   硬截 10 字会把「写当天这一章的原著样章」截成「写当天这一章的原著样」——
    #   最后那个「样」字孤零零挂着，比截短本身更难看。
    #   ⇒ 先断标点；还太长就断在「的」之前（「写当天这一章」）；
    #     连「的」都没有才硬截。
    # [EN] Cap at **10 chars**, but **cut on a word boundary** (measured 2026-10-21): a hard cut
    # [EN] turns 'write this day's original sample chapter' into 'write this day's original sam',
    # [EN] leaving a lone character dangling -- uglier than being short.
    # [EN] ⇒ cut at punctuation; still too long, cut before the possessive particle; only hard-cut
    # [EN] when there is none.
    if len(d) > 10:
        _k = d.find('的')
        d = d[:_k] if 2 < _k <= 10 else d[:10]
    if nm and d:
        return f'{nm} · {d}'
    return nm or d


def push(label: str) -> int:
    """**进入**一件事（压栈），返回令牌 —— 退出时用 `pop(令牌)` 弹掉自己。

    ⚠ 空标签不入栈（不占位）：入栈空标签会让 `snapshot()` 返回空，
      等于把外层的"正在做什么"盖成空白。
    [EN] **Enter** an activity (push) and return a token -- `pop(token)` on exit.
    ⚠ An empty label is not pushed: it would make `snapshot()` empty and blank out the outer action.
    """
    try:
        txt = str(label or '').strip()
        if not txt:
            return 0
        tok = next(_TOK)
        _STACK.append({'tok': tok, 'label': txt, 't0': time.monotonic()})
        return tok
    except Exception:                                            # noqa: BLE001
        return 0


def pop(tok: int = 0) -> None:
    """**退出**一件事。传了令牌就按令牌移除（乱序退出也不会弹错人）。

    ⚠ 不抛：`pop` 挂在 `finally` 里，抛出去会盖掉真正的异常。
    [EN] **Leave** an activity. With a token it is removed by token (out-of-order exits included).
    ⚠ Never raises: `pop` lives in `finally` and would mask the real exception.
    """
    try:
        if not _STACK:
            return
        if not tok:
            _STACK.pop()
            return
        for i in range(len(_STACK) - 1, -1, -1):
            if _STACK[i].get('tok') == tok:
                del _STACK[i]
                return
    except Exception:                                            # noqa: BLE001
        pass


def set_doing(label: str) -> None:
    """**重置**成"现在只有这一件事"（清空栈再压一条）。

    用于没有嵌套的场合（`stage_now` 那种瞬时阶段、以及外层换幕）。
    ⚠ 它会**清掉外层**的登记 —— 所以只能在"确定没有外层还在跑"的地方用；
      嵌套场合一律 `push/pop`。
    [EN] **Reset** to "this one thing only" (clear the stack, push one).
    ⚠ It **wipes** outer entries -- only use where nothing outer is still running; nest with
    `push/pop`.
    """
    try:
        _STACK.clear()
        txt = str(label or '').strip()
        if txt:
            _STACK.append({'tok': next(_TOK), 'label': txt, 't0': time.monotonic()})
    except Exception:                                            # noqa: BLE001
        pass


def reset() -> None:
    """整轮开始/结束时清空（防止异常路径留下的旧标签一直挂着）。"""
    try:
        _STACK.clear()
    except Exception:                                            # noqa: BLE001
        pass


def snapshot() -> dict:
    """给界面/探针读的一帧：`{'label': str, 'secs': float, 'depth': int}`。

    显示**最内层**（最具体的那个动作），秒数从它压栈那一刻算起 ——
    这正是用户要的"当前正在做什么**以及做了多久**"。
    [EN] One frame for the UI/probe: the **innermost** (most specific) action and its duration,
    measured from when it was pushed -- exactly "what is being done **and for how long**".
    """
    try:
        if not _STACK:
            return {'label': '', 'secs': 0.0, 'depth': 0}
        top = _STACK[-1]
        return {'label': str(top.get('label') or ''),
                'secs': max(0.0, time.monotonic() - float(top.get('t0') or 0.0)),
                'depth': len(_STACK)}
    except Exception:                                            # noqa: BLE001
        return {'label': '', 'secs': 0.0, 'depth': 0}
