"""**剧组正在想什么** —— 每个职位一份「实时房间」（2026-10-23，用户点名）。

用户原话：「所有非演员Agent的各个剧组Agent的消息在最前面加上展开收起来三角号 `>`
和展开后向下 表示在执行的消息 我点开这个按钮以后应该是 **LLM 的思考过程流式返回**。
已经完成的消息(比如 xx 已交工)这种我点击展开是 **这一步的执行结果**」。

所以这个模块只干一件事：为「正在出工的那一位」留一个**可以被界面反复读取**的
缓冲区，里面装

| 装什么 | 谁写 | 什么时候 |
|---|---|---|
| `thinking` | `llm/router` 的流式增量（`delta` 事件，`reasoning_content` 优先） | token 一个个到的时候 |
| `body` | `crew/studio.call` 收工时的 `note.body` | 交活时 |
| `state` | `running` → `done`（或 `error`） | 出工开始 / 结束 |

★ 为什么需要**独立的房间**，而不是让界面直接订阅 LLM 事件：
  一次出工内部可能有**好几发** LLM 调用（重试、多段），界面订阅到的是
  「一发请求的增量」，而用户要看的是「**这一位**这一步在想什么」。
  两者之间差一个"归属"：归属由 `ContextVar`（`_CUR`）给出 ——
  `Studio.call` 在 `await member.run()` 外面设一次，这一位内部的**所有**调用
  （含并行子任务，`ContextVar` 会各自继承）都落进同一个房间。

★ 为什么归属要放 ContextVar 而不是"当前是谁"的全局变量：
  剧组能并行出工（`asyncio.gather`），全局变量会被后开始的那位盖掉 ——
  症状是「美术的思考出现在场记的展开框里」，而且**只在并行时才复现**。
  项目里 `llm/usage` 与 `llm/models` 用的是同一套办法（`set_ctx` / `use`），
  这里跟它们保持一致。

★ 房间**有上限**：思考内容封顶 `MAX_THINKING` 字（超出掐头留尾）。
  推理模型一次能吐 6000+ 字，一天几十次出工 ⇒ 不封顶就是内存慢慢涨。
  掐头而不是掐尾：**结论在最后**，前面那截是"重新读题"。

English:
**What the crew is thinking right now** -- one "live room" per role (named by the user
2026-10-23).
The user's words: "put a collapsible triangle `>` in front of every message of every
non-actor crew agent, head down when expanded, for the messages that are *executing*;
clicking it should show **the LLM's thinking streaming in**. For finished messages (like
'xx handed in the work'), clicking shows **this step's result**".
So this module does exactly one thing: keep a **re-readable buffer** for "whoever is
working right now".
★ Why a dedicated room instead of letting the UI subscribe to LLM events directly:
  one crew call may contain **several** LLM requests (retries, sub-sections); the UI sees
  "deltas of one request" while the user wants "what **this role** is thinking in this
  step". The gap is *attribution*, and attribution comes from a `ContextVar` (`_CUR`):
  `Studio.call` sets it around `await member.run()`, so **all** calls inside that role
  (including parallel subtasks, which inherit the ContextVar) land in the same room.
★ Why a ContextVar rather than a "who is current" global: the crew can work in parallel
  (`asyncio.gather`) and a global would be overwritten by whoever starts later -- the
  symptom being "the art director's thinking appears in the continuity clerk's box", and
  it would only reproduce under parallelism. `llm/usage` and `llm/models` use the same
  mechanism (`set_ctx` / `use`); this follows them.
★ Rooms are **bounded**: thinking is capped at `MAX_THINKING` characters (keep the tail,
  drop the head). A reasoning model can emit 6000+ characters per call and there are
  dozens of calls a day, so without a cap memory creeps up. Drop the head, not the tail:
  **the conclusion is at the end**, the beginning is just re-reading the question.
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger('nws.crew.live')

#: 思考内容的上限（字）。超出后掐头留尾 —— 两个理由见模块 docstring。
#: [EN] Cap on thinking text (characters). Beyond it the head is dropped -- reasons above.
MAX_THINKING = 60_000

#: `state` 的三个取值（界面与判据都认这三个字，别改写法）。
#: [EN] The three `state` values (UI and criteria both read these exact words).
RUNNING = 'running'
DONE = 'done'
ERROR = 'error'

#: 当前正在出工的那一位（`Studio.call` 设，`llm/router` 的流式增量读）。
#: 默认空串 = 没有人在出工 ⇒ 增量**不落任何房间**（不报错、不新建）。
#: [EN] Whoever is working right now (set by `Studio.call`, read by the streaming deltas
#: in `llm/router`). Default empty = nobody working => deltas land nowhere (no error, no
#: new room).
_CUR: contextvars.ContextVar[str] = contextvars.ContextVar('nws_crew_live', default='')


@dataclass
class Room:
    """一位职位的实时房间。**所有写操作都在锁里**（见 `_LOCK`）。"""

    key: str
    name: str = ''
    duty: str = ''
    state: str = RUNNING
    thinking: str = ''
    body: str = ''
    why: str = ''
    ok: bool = True
    secs: float = 0.0
    t0: float = field(default_factory=time.monotonic)
    #: 每次有内容变化就 +1。界面靠它判断"有没有新东西"，不必逐字比对。
    #: [EN] Increments on every content change; the UI uses it to tell "is there anything
    #: new" without diffing the text.
    seq: int = 0
    #: 只用来做"这一位这一趟"的编号：同一位一天出工几十次，界面靠它认出
    #: 「现在这条消息还是不是当初那个房间」。
    #: [EN] Identifies "this particular shift": one role works dozens of times a day and the
    #: UI uses it to tell whether a message still belongs to the room it was built for.
    run_id: int = 0

    def snap(self) -> dict[str, Any]:
        return {
            'key': self.key, 'name': self.name or self.key, 'duty': self.duty,
            'state': self.state, 'thinking': self.thinking, 'body': self.body,
            'why': self.why, 'ok': self.ok, 'secs': self.secs,
            'seq': self.seq, 'run_id': self.run_id,
            'elapsed': round(time.monotonic() - self.t0, 1),
        }


_ROOMS: dict[str, Room] = {}
_LOCK = threading.Lock()
#: 全局自增的趟次号（见 `Room.run_id`）。
#: [EN] Globally increasing shift counter (see `Room.run_id`).
_SEQ = [0]


def _truncate(text: str) -> str:
    """超上限就**掐头留尾**（结论在最后）。"""
    if len(text) <= MAX_THINKING:
        return text
    return text[-MAX_THINKING:]


def reset() -> None:
    """新一轮开始 / 收工时清空**全部**房间。

    ⚠ 不清的话，上一轮那位"出工时想的东西"会被下一轮同名角色的展开框读到 ——
      而它看上去完全正常（有字、有格式），只是**不是这一轮的**。
    [EN] Clear **all** rooms at the start/end of a round. Without it, the previous round's
    thinking shows up in the next round's expander for the same role -- and it looks
    perfectly normal, just not from this round.
    """
    with _LOCK:
        _ROOMS.clear()


def current() -> str:
    """现在正在出工的那一位（空串 = 没人）。"""
    return _CUR.get()


def enter(key: str):
    """把 `key` 压成"当前出工者"，返回令牌（交给 `leave` 弹）。"""
    return _CUR.set(str(key or ''))


def leave(token) -> None:
    """按令牌弹回（**不按栈顶**：并行/异常路径上退出顺序会乱）。"""
    try:
        _CUR.reset(token)
    except (ValueError, LookupError):
        pass


def begin(key: str, name: str = '', duty: str = '') -> dict[str, Any]:
    """某位**开始出工**：新建（或重置）它的房间，返回快照。"""
    with _LOCK:
        _SEQ[0] += 1
        room = Room(key=str(key or ''), name=str(name or ''), duty=str(duty or ''),
                    run_id=_SEQ[0])
        _ROOMS[room.key] = room
        return room.snap()


def feed(key: str, chunk: str, kind: str = 'thinking') -> None:
    """往房间追加一段增量。`kind`：`thinking`（思考）/ `content`（正文）。

    ⚠ 没有房间 **就丢掉**，不新建：出工之外的调用（判据、天机里的测试按钮、
      探针）也会发 LLM 请求，若给它们建房间，界面上会凭空多出"某位在想什么"。
    [EN] Append one delta to the room. `kind`: thinking / content.
    If there is no room, **drop it** -- calls outside a shift (criteria, the test button in
    settings, probes) also make LLM requests; creating rooms for them would make the UI pop
    up "someone is thinking" out of nowhere.
    """
    if not chunk:
        return
    with _LOCK:
        room = _ROOMS.get(str(key or ''))
        if room is None:
            return
        if kind == 'content':
            # 正文增量**不进 thinking**：用户要的是"思考过程"，混进正文会让它
            # 变成"整段输出"，而那恰恰是他不想在展开框里看到的东西（正文另有其处）。
            # [EN] Content deltas do **not** go into `thinking`: the user asked for the
            # thinking process; mixing content in would turn the box into "the whole
            # output", which is exactly what does not belong there (the body has its own
            # place).
            return
        room.thinking = _truncate(room.thinking + str(chunk))
        room.seq += 1


def finish(key: str, *, body: str = '', ok: bool = True, secs: float = 0.0,
           why: str = '', state: str = '') -> None:
    """某位**收工**：定格状态、装进产出。"""
    with _LOCK:
        room = _ROOMS.get(str(key or ''))
        if room is None:
            return
        room.state = str(state or (DONE if ok else ERROR))
        room.body = str(body or '')
        room.ok = bool(ok)
        room.secs = round(float(secs or 0.0), 2)
        room.why = str(why or '')
        room.seq += 1


def snapshot(key: str) -> dict[str, Any]:
    """读一位的房间快照。没有房间就返回 `state=''`（界面据此"没有可展开的东西"）。"""
    with _LOCK:
        room = _ROOMS.get(str(key or ''))
        if room is None:
            return {'key': str(key or ''), 'state': '', 'thinking': '',
                    'body': '', 'seq': 0, 'name': str(key or '')}
        return room.snap()


def rooms() -> dict[str, dict[str, Any]]:
    """全部房间的快照（判据与"这一轮都谁想什么"的复盘用）。"""
    with _LOCK:
        return {k: r.snap() for k, r in _ROOMS.items()}


# ══════════════════════════════════════════════════════════════════
#  LLM 事件 → 房间（**唯一的接线处**）
# [EN] LLM events -> rooms (**the only wiring point**)
# ══════════════════════════════════════════════════════════════════
_INSTALLED = [False]


def on_llm_event(event: dict) -> None:
    """`llm/router` 的监听器：把 `delta` 事件灌进**当前出工者**的房间。

    ⚠ 必须**立刻返回**（`add_listener` 的约定）：这里只做字符串拼接，
      不做 I/O、不 `await`。
    ⚠ 只在 `type == 'delta'` 时动：`request` / `response` / `error` 那三种
      与房间无关（`response` 的全文太粗，拿来当"思考"是假的）。
    [EN] The `llm/router` listener: pour `delta` events into the **current worker's** room.
    Must **return immediately** (the `add_listener` contract): only string concatenation
    here, no I/O, no `await`. Only acts on `type == 'delta'`; the other three are unrelated
    to rooms (a whole `response` is too coarse to pass off as "thinking").
    """
    try:
        if event.get('type') != 'delta':
            return
        key = _CUR.get()
        if not key:
            return
        feed(key, str(event.get('text') or ''),
             kind=str(event.get('stream') or 'thinking'))
    except Exception:                                        # noqa: BLE001
        pass


def install() -> bool:
    """把 `on_llm_event` 挂到 LLM 上（幂等）。返回"这次是不是新挂的"。

    ⚠ **必须挂到单例 `llm`（实例）上，不是 `LLM`（类）**：`add_listener` 是
      实例方法，挂到类上会 `TypeError: missing 1 required positional argument`
      —— 而这里第一版就是 `R.LLM`，异常被下面的 `except` 吞掉，
      表现是**安装"成功"、展开框永远是空的**。所以失败必须留痕，不许静默。
    [EN] Attach `on_llm_event` to the LLM (idempotent). Returns whether it was newly
    attached.
    ⚠ **Must attach to the singleton `llm` (instance), not `LLM` (the class)**:
    `add_listener` is an instance method; attaching to the class raises `TypeError:
    missing 1 required positional argument` -- and the first version here used `R.LLM`,
    the exception was swallowed by the `except` below, and the symptom was "installed
    fine, the expander is forever empty". So failure must leave a trace, never be silent.
    """
    if _INSTALLED[0]:
        return False
    try:
        from llm import router as R
        R.llm.add_listener(on_llm_event)
    except Exception as e:                                   # noqa: BLE001
        _LOG.warning('剧组实时房间没挂上 LLM 监听（展开框会看不到思考过程）：%r', e)
        return False
    _INSTALLED[0] = True
    return True


def uninstall() -> None:
    """摘掉监听器（判据收尾用，免得 resid 影响下一条断言）。"""
    try:
        from llm import router as R
        R.llm.remove_listener(on_llm_event)
    except Exception as e:                                   # noqa: BLE001
        _LOG.warning('摘掉剧组实时房间的监听失败：%r', e)
    _INSTALLED[0] = False


__all__ = ['Room', 'RUNNING', 'DONE', 'ERROR', 'MAX_THINKING',
           'begin', 'feed', 'finish', 'snapshot', 'rooms', 'reset',
           'current', 'enter', 'leave', 'install', 'uninstall', 'on_llm_event']
