# -*- coding: utf-8 -*-
"""**定时落盘**：不等到收工、也不等日界，每隔 N 秒把"现在跑到哪儿了"写到盘上。

用户 2026-10-08 的原话：
    「我点暂停的时候以及平时也有可能随时关闭软件 所以后台还需要一个定时器
      实现定时落盘 比如没30秒落盘一次」

## 为什么需要它（先说清"不落盘会丢什么"）

主循环只在**日界**才把一天落盘（`RunLoop._end_day` → `flush_daily*`）。
于是一天里下面两种事都会**白跑**：

  · **点暂停**（或者程序放着不动）—— 当天已经演了大半，`每天的生活/第003天.md`
    还停在"还没写"；
  · **随时关掉窗口**（用户原话）—— 更直接：进程没了，那大半天的戏**只在内存里**。

★ 所以这里落的是**一份"中途稿"**：把当前这一天**已经演出来的**东西按现在的样子
  写下来，**滚动覆盖同一份文件**（不是每 30 秒攒一个新档 —— 那会把盘塞满）。

## 落什么、落在哪

★★★ 2026-10-23 起，**一次落盘写两组东西**（用户：「电脑突然关机……下一次打开
拾卷里的存档可以拿到最近的记录，最多损失 30 秒」）：

| 写什么 | 落在哪 | 谁读它 |
|---|---|---|
| ① 当天正文（含 `⏳ 定时落盘` 标记） | `每天的生活/第NNN天.md` + `.json` | 拾卷的"最近剧情"、**续跑**（`read_daily_script`） |
| ② 停点 | `停点.json` | **下一次「起笔」**（决定从哪天哪一刻继续） |
| ③ 给人看的中途快照 | `自动落盘/进度.md` + `.json` | 只有人 |

改之前只有 ③。于是"断电后能拿到最近记录"是**做不到**的 —— `每天的生活/` 停在
上一次日界、`停点.json` 停在上一次收工，整轮白跑。①② 由 `RunLoop.persist_partial()`
写（`flush_progress` 的第一件事），**顺序不能反**：先保住能续跑的，再写给人看的。

```
<运行文件夹>/自动落盘/
├── 进度.md      人读的：第几天 / 故事时间 / 天气 / 场景 / 在场人物 + 今天已演的词条
└── 进度.json    程序读的：同上，结构化（给探针与判据用）
```

⚠ **落点刻意不在 `每天的生活/`**：那个目录是"正式产物"（一天一个文件、日界写，
拾卷/导出都认它）。中途稿混进去，会出现"这一天的文件已经在了，但其实只演了一半"
—— 那比没落盘更坏（导出的稿子会短一块，而没人看得出来）。
所以另开一个目录，文件名叫 `进度.md`，开头第一行就写明**这是中途稿**。

⚠ **但 ①② 必须落在 `每天的生活/` 与包根** —— 那是"能不能续跑"的唯一来源，
  `read_daily_script()` 只认那个路径。为了不让它冒充正式稿，`flush_daily_script`
  的 `partial_at` 参数会在头部写一行 `> ⏳ **定时落盘 · <时间>**`；
  日界 / 收工那条路**不传**它，于是正式稿没有这一行。

## 谁在什么时候调

| 什么时候 | 谁调 | 为什么 |
|---|---|---|
| 每 `AUTOSAVE_SECONDS` 秒 | `AutoSaver.run()`（本模块的定时器） | 用户要的那条 |
| **起笔之后立刻** | `_start_autosave()` 里一次 `flush_now('start')` | ★ 用户 2026-10-23：「**起笔之后就要有存档**」—— 否则开跑后头一个间隔里断电，连"这一轮演过"都不知道 |
| 点**暂停** | `AutoSaver.flush_now()`（界面调） | 用户明确点名的那一刻 |
| **关窗口** | `page.on_disconnect` → `flush_now()`（界面调） | 用户原话「随时关闭软件」 |
| 收工/停止前 | 同上（界面在 `_await_stop` 里调） | 尽量别丢最后一段 |

## 三条纪律

1. **吞掉所有异常**。落盘是"保险"，保险坏了不能把车弄停 —— 一次磁盘抖动
   （OneDrive 同步锁文件是本机的常事）不该让推演中断。
2. **不碰项目文件夹**。只写运行文件夹（本项目铁律，见 `store/runfolder.py`）。
3. **纯同步的一小段**，由调用方丢进线程（`asyncio.to_thread`）——
   写盘几十毫秒，放在事件循环里会卡住那一拍的推演。

English:
**Timed auto-save**: without waiting for wrap-up or the day boundary, every N seconds write
"where we are now" to disk.
The user's exact words on 2026-10-08:
    "When I click pause, and also at other times, I might close the software at any moment, so the backend also needs a timer
      to implement timed saving, e.g. save once every 30 seconds"
## Why it's needed (first make clear "what is lost without saving")
The main loop only saves a day's data at the **day boundary** (`RunLoop._end_day` →
`flush_daily*`).
So during a day, the following two things both **go to waste**:
  · **Clicking pause** (or leaving the program idle) -- most of the day has already played out, but `每天的生活/第003天.md`
    is still stuck at "not yet written";
  · **Closing the window at any time** (the user's own words) -- even more direct: the process is gone, and that half-day of drama **exists only in memory**.
★ So what's saved here is a **"mid-progress draft"**: the current day's **already-played-out**
content is written down
  in its current form, **rolling over the same file** (not accumulating a new file every 30 seconds -- that would fill up the disk).
## What is saved, and where
```
├── 进度.md for humans: day number / story time / weather / scene / present characters + today's
already-played entries
└── 进度.json    for the program: same as above, structured (used by probes and criteria)
```
⚠ **The save location is deliberately NOT in `每天的生活/`**: that directory is the "official output"
(one file per day, written at the day boundary;
picking up volumes / exporting all recognize it). If mid-progress drafts were mixed in, we'd get
"this day's file already exists, but only half of it has actually played out"
-- which is worse than not saving at all (the exported draft would be short a chunk, and nobody
could tell).
So open another directory, name the file `进度.md`, and make the first line state clearly that
**this is an in-progress draft**.
## Who calls it and when
| When | Who calls | Why |
|---|---|---|
| Every `AUTOSAVE_SECONDS` seconds | `AutoSaver.run()` (the timer in this module) | the one the user asked for |
| Click **Pause** | `AutoSaver.flush_now()` (called by the UI) | the exact moment the user named |
| **Close window** | `page.on_disconnect` -> `flush_now()` (called by the UI) | the user's own words "close the software at any time" |
| Before wrapping up/stopping | same as above (the UI calls it in `_await_stop`) | try not to lose the last segment |
## Three rules
1. **Swallow all exceptions**. Persisting to disk is "insurance"; broken insurance must not stop the car -- a single disk hiccup
   (OneDrive locking the file during sync is routine on this machine) must not interrupt the simulation.
2. **Do not touch the project folder**. Only write to the run folder (an ironclad rule of this project, see `store/runfolder.py`).
3. **A small purely synchronous block**, handed off to a thread by the caller (`asyncio.to_thread`) --
   writing to disk takes tens of milliseconds; putting it in the event loop would stall that beat of the simulation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from config import CFG
from logger import get_logger
from util.io import atomic_write_text
from util.text import now_str

_LOG = get_logger('nws.autosave')

#: 自动落盘的目录名（在运行文件夹里）
# [EN] : Directory name for auto-save (inside the run folder)
DIR_NAME = '自动落盘'
FILE_MD = '进度.md'
FILE_JSON = '进度.json'

#: 「**刚落盘**」这个提示在状态条上停留多少秒（用户：「如果干了应该给一个提示」）。
#: 太短会刷不出来（界面那半秒刷一次），太长会一直占着，看不见倒计时。
# [EN] : How many seconds the "**just saved**" hint stays on the status bar (user: "if it did
# [EN] something, it should give a hint").
# [EN] : Too short and it won't render (the UI refreshes every half second), too long and it occupies
# [EN] the space, hiding the countdown.
JUST_SAVED_SECONDS = 3.0


# ══════════════════════════════════════════════════════════════════════
#  取料：从主循环手里把"现在跑到哪儿了"拼出来
# [EN] Fetch: assemble "where we are now" from the main loop
# ══════════════════════════════════════════════════════════════════════
def _today_lines(loop: Any) -> list[str]:
    """今天**已经演出来**的那些行（剧本体；没有就退回叙事行）。

    ⚠ 两种情况都要管（`_day_lines` 那条老注释里写着同样的理由）：
      剧本模式下内容在 `builder.scenes` 里（`_daily_narrative` 往往是空的），
      普通模式下就在 `_daily_narrative` 里。
    
        English:
    The lines **already performed** today (script body; fall back to narrative lines if none).
        ⚠ Both cases must be handled (the same reasoning is written in that old comment in `_day_lines`):
          in script mode the content is in `builder.scenes` (`_daily_narrative` is often empty),
          in normal mode it is in `_daily_narrative`.
    """
    out: list[str] = []
    try:
        from display import script_render as SR
        groups: list = []
        b = getattr(loop, '_builder', None)
        if b is not None:
            groups = list(getattr(b, 'scenes', None) or [])
            cur = getattr(b, 'current', None)
            if cur is not None and cur not in groups:
                groups.append(cur)
        for sc in groups:
            for e in (getattr(sc, 'entries', None) or []):
                one = SR.one_line(e)
                if one:
                    out.append(one)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('自动落盘：取当天的剧本词条失败（退回叙事行）：%r', e)
    if not out:
        out = [str(x) for x in (getattr(loop, '_daily_narrative', None) or [])
               if str(x).strip()]
    return out


def snapshot(loop: Any) -> dict:
    """把"此刻的进度"取成一份纯数据（**不写盘**，便于判据直接断言）。

    取不到的东西一律留空/0 —— 自动落盘**绝不能因为某个字段拿不到就整份不落**。
    
        English:
    Take "the current progress" as a pure data snapshot (**without writing to disk**, so criteria
    can assert on it directly).
        Anything that cannot be fetched is left empty/0 -- autosave **must never skip the whole save just because some field cannot be fetched**.
    """
    w = getattr(loop, 'world', None)
    day = 0
    try:
        day = int(getattr(loop, '_current_day', 0)
                  or getattr(w, 'game_day', 0) or 0)
    except Exception:                                            # noqa: BLE001
        day = 0
    cal = ''
    for getter in (lambda: w.clock_display(), lambda: w.clock.segment()):
        try:
            cal = str(getter() or '')
        except Exception:                                        # noqa: BLE001
            cal = ''
        if cal:
            break
    lines = _today_lines(loop)

    def _safe(fn, default):
        try:
            return fn()
        except Exception:                                        # noqa: BLE001
            return default

    return {
        'at': now_str('%Y-%m-%d %H:%M:%S'),
        'day': day,
        'calendar': cal,
        'weather': str(_safe(lambda: w.weather, '') or ''),
        'scene': str(_safe(lambda: w.scene, '') or ''),
        'on_stage': list(_safe(lambda: w.on_stage_names(), []) or []),
        'tension': float(_safe(lambda: w.tension, 0.0) or 0.0),
        'lines': len(lines),
        'chars': sum(len(x) for x in lines),
    }


def render_md(snap: dict, lines: list[str]) -> str:
    """中途稿正文。**第一行就说清"这是中途稿"** —— 别让它冒充正式产物。
        English:
    In-progress draft body. **The first line must make clear that "this is an in-progress draft"**
    -- do not let it masquerade as a formal artifact.
    """
    head = [
        f"# 第 {snap.get('day', 0)} 天 · 自动落盘的中途稿",
        '',
        '> 这是**自动落盘**写下的中途稿（滚动覆盖同一份文件）。'
        + ('**这一份同时已经把"能续跑"的两样也写好了**'
           '（`每天的生活/` 里那一天的正文 + `停点.json`）—— 断电后下次起笔'
           '会接着这里演，最多损失一个落盘间隔。'
           if snap.get('recoverable') else
           '⚠ **但这一次"能续跑"的那两样没写成**（见日志）—— '
           '断电后可能退回上一次收工的位置。'),
        f"> 写下时间：{snap.get('at', '')}",
        '',
        f"- 故事时间：{snap.get('calendar', '') or '（未定）'}",
        f"- 天气：{snap.get('weather', '') or '（未定）'}",
        f"- 场景：{snap.get('scene', '') or '（未定）'}",
        f"- 在场：{'、'.join(snap.get('on_stage') or []) or '（无人）'}",
        f"- 张力：{snap.get('tension', 0.0)}",
        f"- 今天已演：{snap.get('lines', 0)} 条 · 约 {snap.get('chars', 0)} 字",
        '',
        '---',
        '',
    ]
    body = '\n'.join(lines) if lines else '（今天还没演到有内容的一拍）'
    return '\n'.join(head) + body + '\n'


# ══════════════════════════════════════════════════════════════════════
#  落盘
# [EN] Save to disk
# ══════════════════════════════════════════════════════════════════════
def _run_root(run_folder: Any) -> Path:
    r"""把 `RunFolder` 或它的 `Path` 都归一成"运行文件夹根"。

    ★★ **这里有个真陷阱，判据抓到的**（`verify_autosave` 的 B4）：

    ```
    root = Path(getattr(run_folder, 'root', run_folder))     # ← 错！
    ```

    `pathlib.Path` **自带 `.root` 属性**（`PurePath.root`，返回路径的根部件，
    Windows 上就是反斜杠）。于是传一个 `Path` 进来时，`getattr` 命中的不是
    "我要的那个根"，而是 pathlib 自己的 `.root` —— `root` 变成盘根，
    紧接着 `out = root / '自动落盘'` 就写到了**当前盘根目录下**，
    而且一声不响（`mkdir(parents=True, exist_ok=True)` 会把它建出来）。

    `verify_autosave` 的 B4（"写不进去时该返回失败"）就是这么把它抓出来的。

    ⚠ 实现已提到 `util/runpath.run_root()`（同一个坑在 `sim/resume.py`
      又被踩了一次，所以只留**一处**实现）。这个薄封装留着只是为了
      让老判据/老变异脚本的锚点继续指得到。
    
        English:
    Normalize either a `RunFolder` or its `Path` to the "run folder root".
        ★★ **There is a real trap here, caught by the criteria** (B4 of `verify_autosave`):
        ```
        root = Path(getattr(run_folder, 'root', run_folder))     # ← wrong!
        ```
        `pathlib.Path` **has its own `.root` attribute** (`PurePath.root`, which returns the root component of the path,
        i.e. the backslash on Windows). So when a `Path` is passed in, what `getattr` hits is not
        "the root I want", but pathlib's own `.root` -- `root` becomes the drive root,
        and then `out = root / '自动落盘'` writes to **the current drive root**,
        and does so silently (`mkdir(parents=True, exist_ok=True)` will create it).
        This is exactly how B4 of `verify_autosave` ("should return failure when it cannot write") caught it.
        ⚠ The implementation has been moved to `util/runpath.run_root()` (the same trap was
          stepped on again in `sim/resume.py`, so only **one** implementation is kept). This thin wrapper is kept only so that
          old criteria/old mutation scripts' anchors can still find it.
    """
    from util.runpath import run_root
    return run_root(run_folder)


def flush_progress(loop: Any, run_folder: Any, *, every: int = 0,
                   reason: str = 'timer') -> dict:
    """**把此刻的进度写下来**（滚动覆盖同一份文件）。返回一份结果供播报/断言用。

    `run_folder` 传 `RunFolder` 或它的 `Path` 都行（见 `_run_root` ——
    那里记着"`Path.root` 会把路径吃掉"这个坑）。
    `reason` 只是给日志/JSON 留个痕（`timer` / `pause` / `close` / `stop`）——
    "这次落盘是谁催的"在排查"为什么没落"时是第一条线索。

    失败**不抛异常**（返回 `{'ok': False, 'error': ...}`）：
    落盘是保险，保险坏了不该把推演弄停。

    ★★★ 2026-10-23（用户：「电脑突然关机……下一次打开拾卷里的存档可以拿到最近的记录，
      最多损失 30 秒」）：**先写"能续跑的那两份"，再写这份给人看的中途稿。**

      改之前这里只写 `自动落盘/进度.md` / `进度.json` —— 那是**只有人能看**的，
      拾卷不读它、续跑不读它。于是断电之后：`每天的生活/` 是上一次日界的，
      `停点.json` 是上一次收工的 ⇒ **整轮白跑**。
      现在第一件事是 `loop.persist_partial(reason)`：把当天正文写进
      `每天的生活/`（带 `⏳ 定时落盘` 标记）、把停点更新到此刻。

      ⚠ **顺序不能反**：先保住"可恢复的状态"，再写"给人看的快照"。
        反过来的话，中途稿写成功了、而正文/停点那一步失败，用户会看到
        "进度.md 是新的"却续不上 —— 那比两份都旧更难查。

        English:
    **Write the current progress down** (rolling overwrite of the same file). Return a result for
    broadcasting/asserting.
        `run_folder` may be either a `RunFolder` or its `Path` (see `_run_root` --
        it records the trap that "`Path.root` eats the path").
        `reason` just leaves a trace for logs/JSON (`timer` / `pause` / `close` / `stop`) --
        "who prompted this save" is the first clue when investigating "why it did not save".
        Failure **does not raise** (returns `{'ok': False, 'error': ...}`):
        saving is insurance; broken insurance must not stop the simulation.
        ★★★ 2026-10-23 (user: "the computer suddenly shuts down... next time I open the save in 拾卷 I
        want the latest record, losing at most 30 seconds"): **first write the two files that make
        resuming possible, then this human-readable snapshot.**
        Before this change only `自动落盘/进度.md` / `进度.json` were written -- readable by humans only;
        拾卷 does not read them and resuming does not read them. So after a power cut
        `每天的生活/` held the last day boundary and `停点.json` the last wrap-up => **the whole round
        was lost**. Now the first thing done is `loop.persist_partial(reason)`: the day's body goes into
        `每天的生活/` (marked `⏳ 定时落盘`) and the stop point is moved to this moment.
        ⚠ **The order must not be reversed**: secure the recoverable state first, then the snapshot. If
        reversed and the body/stop-point step fails while the snapshot succeeds, the user sees a fresh
        `进度.md` yet cannot resume -- harder to diagnose than both being stale.
    """
    partial: dict = {}
    try:
        # ★ 第一步：可恢复的那两份（当天正文 + 停点）。缺这一句，下面写什么都救不回来。
        # [EN] ★ Step one: the two recoverable files (the day's body + the stop point). Without this,
        # [EN] nothing written below can save the round.
        fn = getattr(loop, 'persist_partial', None)
        if callable(fn):
            partial = fn(reason) or {}
        else:
            # 老调用方 / 判据里的假 loop：没有那个方法就退回"只写中途稿"，
            # **但要在结果里说出来** —— 不然"落了盘"会被读成"能续跑"。
            # [EN] Old callers / fake loops in criteria: without that method fall back to
            # [EN] "snapshot only", **but say so in the result** -- otherwise "saved" is read as
            # [EN] "resumable".
            partial = {'ok': False, 'error': 'no-persist_partial'}
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('中途落盘（可续跑那两份）失败（继续写中途稿）：%r', e)
        partial = {'ok': False, 'error': repr(e)}
    try:
        out = _run_root(run_folder) / DIR_NAME
        out.mkdir(parents=True, exist_ok=True)
        snap = snapshot(loop)
        lines = _today_lines(loop)
        snap['every'] = int(every or 0)
        snap['reason'] = str(reason or '')
        # ★ 记下"可续跑那两份写成了没有" —— 界面上那句「已落盘」对用户的意义
        #   正是"断电也能接上"，所以这个布尔值必须跟着结果走，不能只在日志里。
        # [EN] ★ Record whether the two resumable files were written -- that is exactly what "saved"
        # [EN] means to the user (survives a power cut), so this boolean must travel with the result.
        snap['recoverable'] = bool(partial.get('ok'))
        atomic_write_text(out / FILE_MD, render_md(snap, lines))
        atomic_write_text(out / FILE_JSON,
                          json.dumps({**snap, 'ok': True},
                                     ensure_ascii=False, indent=2))
        _LOG.info('自动落盘（%s）：第 %d 天 · %d 条 · 约 %d 字 · 可续跑=%s',
                  reason, snap['day'], snap['lines'], snap['chars'],
                  '是' if snap['recoverable'] else '否')
        return {'ok': True, 'dir': str(out), 'partial': partial, **snap}
    except Exception as e:                                        # noqa: BLE001
        _LOG.warning('自动落盘失败（不影响推演）：%r', e)
        return {'ok': False, 'error': repr(e), 'reason': str(reason or ''),
                'partial': partial}


# ══════════════════════════════════════════════════════════════════════
#  定时器
# [EN] Timer
# ══════════════════════════════════════════════════════════════════════
class AutoSaver:
    """**后台的定时落盘器**：每 `interval` 秒落一次，直到被 `stop()`。

    ★ 它**不依赖推演在跑** —— 暂停时照样落（那正是用户点名的场景之一：
      "我点暂停的时候"）。所以它比的是**墙钟**，不是"第几拍"。

    ★ **间隔每次现读配置**（不在建实例时读死）：用户在天机里把 30 改成 60，
      不必重开一轮 —— 下一拍生效。`0` = 关闭（此时 `run()` 直接返回，
      界面那行小字会写"已关闭"）。

    用法（界面侧）::

        saver = AutoSaver(target=lambda: self.session)
        saver.start(page)          # 起一个后台任务
        ...
        saver.flush_now('pause')   # 暂停/退出时立刻来一次
        saver.stop()               # 收工时收掉
    
        English:
    **The background periodic saver**: saves once every `interval` seconds until `stop()` is called.
        ★ It **does not depend on the simulation running** -- it still saves while paused (that is exactly one of the scenarios the user named:
          "when I click pause"). So it compares **wall clock**, not "which beat".
        ★ **The interval is read from config each time** (not frozen at instance creation): if the user changes 30 to 60 in 天机,
          there is no need to restart a round -- it takes effect on the next beat. `0` = disabled (then `run()` returns immediately,
          and the small line of text in the UI will say "disabled").
        Usage (UI side)::
            saver = AutoSaver(target=lambda: self.session)
            saver.start(page)          # start a background task
            ...
            saver.flush_now('pause')   # flush immediately on pause/exit
            saver.stop()               # tear down on shutdown
    """

    def __init__(self, *, target: Callable[[], Any],
                 on_tick: Callable[[dict], None] | None = None,
                 interval_getter: Callable[[], int] | None = None,
                 sleeper: Callable[[float], Any] | None = None):
        #: 每次要落盘时问它"现在这一轮是什么"（返回 `RunSession` 或 None）。
        #: ⚠ 用**取值函数**而不是直接存一个会话对象：一轮跑完换了会话之后，
        #:   这个定时器不该跟着作废（否则第二轮起就不再落盘了 —— 那种
        #:   "第一轮好使、第二轮不落"的毛病最难查）。
        # [EN] : Each time we need to save, ask it "what is the current round" (returns `RunSession` or None).
        # [EN] : ⚠ Use a **getter function** instead of storing a session object directly: after a round
        # [EN] finishes and the session is swapped,
        # [EN] : this timer should not become invalid along with it (otherwise it stops saving from round two
        # [EN] onward -- that
        # [EN] :   "works in round one, doesn't save in round two" kind of bug is the hardest to track down).
        self._target = target
        self._on_tick = on_tick
        self._interval_getter = interval_getter or (lambda: CFG.i('AUTOSAVE_SECONDS'))
        #: 注入睡眠函数只为**判据能压时间**（真实实现用 `asyncio.sleep`）。
        # [EN] : Inject the sleep function only so **the criteria can compress time** (the real implementation
        # [EN] uses `asyncio.sleep`).
        self._sleep = sleeper
        self._task: Any = None
        self._stopped = False
        #: 最近一次的结果（界面那行小字与判据都读它）。
        # [EN] : The most recent result (both the small text line in the UI and the criteria read it).
        self.last: dict = {}
        self.count = 0                      #: 落过多少次（判据用它证明"真的在落"）
        #: **最近一次成功落盘的墙钟时刻**（`time.time()`）。界面那半句
        #: "上次 N 秒前"就是拿它算的。
        # [EN] : How many times we've saved (the criteria use it to prove "it really is saving")
        # [EN] : **Wall-clock time of the most recent successful save** (`time.time()`). The UI's half-sentence
        # [EN] : "last N seconds ago" is computed from it.
        #:
        #: ★★ 为什么要存在**这里**而不是存在界面上（2026-10-08 修的真 bug）：
        #:   界面原来只在"自己主动调 `flush_now`"时记这个时刻 —— 而**定时器
        #:   自己落的那一次从不经过界面**（`run()` 里 `flush_now('timer')`，
        #:   界面根本没被通知），于是那半句「N 秒前」永远不出现，屏幕上一直
        #:   是「自动落盘 · 每 30 秒」。用户看到的就是「**没看到它干没干**」。
        #:   落盘这件事的事实来源在**落盘器**身上，界面只该来读。
        # [EN] : ★★ Why it must live **here** and not in the UI (a real bug fixed on 2026-10-08):
        # [EN] : The UI originally only recorded this moment when "it actively called `flush_now`" -- but **the
        # [EN] timer's
        # [EN] :   own save never goes through the UI** (in `run()`, `flush_now('timer')`,
        # [EN] : the UI was never notified), so that half-sentence "N seconds ago" never appears, and the
        # [EN] screen always
        # [EN] : shows "auto-save · every 30 seconds". What the user sees is "**can't tell if it did
        # [EN] anything**".
        # [EN] :   The source of truth for saving is the **saver**; the UI should only read.
        self.last_at: float = 0.0
        #: **下一次该落盘的时刻**（`time.monotonic()`，单调钟，不受改系统时间影响）。
        #: `None` = 没在计时（关掉了 / 还没起 / 已收）。界面用它显示**倒计时**。
        # [EN] : **Time of the next save** (`time.monotonic()`, monotonic clock, unaffected by system time
        # [EN] changes).
        # [EN] : `None` = not timing (turned off / not started / stopped). The UI uses it to show the
        # [EN] **countdown**.
        self._next_at: float | None = None

    # ── 间隔 ──
    # [EN] ── Interval ──
    def interval(self) -> int:
        """当前生效的间隔（秒）。`0` = 关掉。取不到就退回 30。
                English:
        Current effective interval (seconds). `0` = disabled. Falls back to 30 if unavailable.
        """
        try:
            v = int(self._interval_getter() or 0)
        except Exception:                                        # noqa: BLE001
            return 30
        return max(0, v)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._stopped

    @property
    def secs_to_next(self) -> float | None:
        """**还有多少秒落盘**（倒计时）。`None` = 现在没有倒计时可报。

        `0.0` 也是合法值（正好到点、马上要落），所以调用方要判 `is None`
        而不是判真假 —— 判假会把"正好到点"当成"没在计时"。
        
                English:
        **Seconds until next flush** (countdown). `None` = no countdown to report right now.
                `0.0` is also a valid value (exactly due, about to flush), so callers must check `is None`
                rather than truthiness -- a falsy check would treat "exactly due" as "not counting".
        """
        if self.interval() <= 0 or self._next_at is None:
            return None
        return max(0.0, self._next_at - time.monotonic())

    # ── 立即落一次（暂停 / 关窗口 / 收工前）──
    # [EN] ── Save once immediately (pause / close window / before wrapping up) ──
    def flush_now(self, reason: str = 'manual') -> dict:
        """**同步**落一次。失败不抛（见 `flush_progress`）。
                English:
        **Synchronous** single flush. Does not raise on failure (see `flush_progress`).
        """
        ses = None
        try:
            ses = self._target()
        except Exception as e:                                    # noqa: BLE001
            _LOG.warning('自动落盘：取会话失败：%r', e)
            return {'ok': False, 'error': repr(e)}
        loop = getattr(ses, 'loop', None)
        run = getattr(ses, 'run', None)
        if loop is None or run is None:
            # 没有在跑的轮次 —— 没什么可落的，**不是错误**（别刷日志）。
            # [EN] No round is running -- nothing to save, **not an error** (don't spam the log).
            return {'ok': False, 'error': 'no-session', 'reason': reason}
        res = flush_progress(loop, run, every=self.interval(), reason=reason)
        if res.get('ok'):
            self.count += 1
            self.last = res
            # ★ 记下**墙钟**时刻（界面拿它算"N 秒前"/"刚落盘"），
            #   定时器那条路也走这里，所以界面上终于看得到"它真的干了"。
            # [EN] ★ Record the **wall-clock** time (the UI uses it to compute "N seconds ago"/"just saved"),
            # [EN] The timer path also goes through here, so the UI can finally see "it really did something".
            self.last_at = time.time()
            if self._on_tick is not None:
                try:
                    self._on_tick(res)
                except Exception:                                # noqa: BLE001
                    pass
        return res

    # ── 定时循环 ──
    # [EN] ── Timer loop ──
    async def run(self) -> None:
        """定时循环体。由 `start()` 丢进后台任务；也可以直接 await（判据用）。
                English:
        Timer loop body. Launched into a background task by `start()`; can also be awaited directly (for
        tests).
        """
        import asyncio
        sleep = self._sleep or asyncio.sleep
        try:
            while not self._stopped:
                iv = self.interval()
                if iv <= 0:
                    # 关掉了：**别忙等**。睡一个较长的固定档再回来看一眼配置 ——
                    # 用户可能在天机里把它重新打开（那时不必重开一轮）。
                    self._next_at = None          # 关着 = 没有倒计时可报
                    # [EN] Turned off: **don't busy-wait**. Sleep for a longer fixed interval, then check the config again
                    # [EN] --
                    # [EN] The user might re-enable it in Tianji (no need to restart a round for that).
                    # [EN] Off = no countdown to report
                    await sleep(5.0)
                    continue
                # ★ 先把"下一次什么时候落"定下来**再睡**（界面靠它显示倒计时）。
                #   放在 sleep 之后才算的话，界面上那半句会在睡醒那一刻才出现。
                # [EN] ★ First pin down "when the next save happens" **before sleeping** (the UI relies on it to show
                # [EN] the countdown).
                # [EN] If it were only computed after sleep, that half-sentence in the UI would only appear the moment
                # [EN] we wake up.
                self._next_at = time.monotonic() + float(iv)
                await sleep(float(iv))
                if self._stopped:
                    break
                res = self.flush_now('timer')
                if res.get('ok') and self._on_tick is not None:
                    try:
                        self._on_tick(res)
                    except Exception:                            # noqa: BLE001
                        pass
        except Exception as e:                                    # noqa: BLE001
            # 定时器自己挂掉绝不该影响推演；记一条就退（不再重启，免得刷屏）
            # [EN] The timer itself crashing must never affect the simulation; log one line and exit (no restart,
            # [EN] to avoid log spam)
            _LOG.warning('自动落盘定时器退出（不影响推演）：%r', e)
        finally:
            # 无论怎么退出（正常停 / 被 cancel / 挂了）都别再报倒计时 ——
            # 留着一个不走的倒计时比没有更坏（又是"数字不动 = 是不是坏了"）。
            # [EN] However it exits (normal stop / cancelled / crashed), stop reporting the countdown --
            # [EN] Leaving a frozen countdown is worse than having none (again, "number not moving = is it
            # [EN] broken?").
            self._next_at = None

    def start(self, page: Any = None) -> Any:
        """起后台任务。已经起着就什么都不做（重复调用安全）。
                English:
        Start the background task. No-op if already running (safe to call repeatedly).
        """
        import asyncio
        if self.running:
            return self._task
        self._stopped = False
        try:
            if page is not None:
                self._task = page.run_task(self.run)
            else:
                self._task = asyncio.ensure_future(self.run())
        except Exception as e:                                    # noqa: BLE001
            _LOG.warning('自动落盘定时器起不来（不影响推演）：%r', e)
            self._task = None
        return self._task

    def stop(self) -> None:
        """收掉定时器。**幂等**（收工与关窗口可能都调）。
                English:
        Tear down the timer. **Idempotent** (may be called by both shutdown and window close).
        """
        self._stopped = True
        t = self._task
        self._task = None
        if t is not None:
            try:
                t.cancel()
            except Exception:                                    # noqa: BLE001
                pass

    def label(self, *, ago: float | None = None, to_next: float | None = None,
              just_saved: bool | None = None) -> str:
        """状态条上那句话（**只在这一层拼给人看的字**）。

        用户 2026-10-08 的两条要求都在这一句里：
          · 「**自动落盘没有倒计时**」→ 前半句 `还有 N 秒`；
          · 「也没看到它干没干（**如果干了应该给一个提示**）」→ 落过之后
            变成 `✓ 刚落盘（第 k 次）` 闪几秒，平时那半句 `上次 M 秒前`
            也在走（那就是"它真的在干"的凭据）。

        三个参数都是**覆盖值**（给判据压时间用）；不给就按落盘器自己的状态算
        —— 界面上那次调用只需要 `saver.label()` 一个词。
        `ago` = 距上次落盘多少秒；`to_next` = 距下次落盘多少秒。
        
                English:
        The sentence on the status bar (**user-facing text assembled only at this layer**).
                Both of the user's 2026-10-08 requests are in this one sentence:
                  · "**Auto-save has no countdown**" -> the first half is `N seconds left`;
                  · "and I can't see whether it did anything (**if it did, it should give a hint**)" -> after a flush
                    it becomes `✓ just flushed (k-th time)` flashing for a few seconds, while the usual `last flush M seconds ago`
                    keeps ticking (that is the evidence that "it's really working").
                All three parameters are **override values** (used by tests to compress time); if not given, they are computed from the saver's own state
                -- the single UI call site only needs `saver.label()`.
                `ago` = seconds since last flush; `to_next` = seconds until next flush.
        """
        from i18n import t
        iv = self.interval()
        if iv <= 0:
            return t('自动落盘 · 已关闭')
        if ago is None and self.last_at:
            ago = max(0.0, time.time() - self.last_at)
        if to_next is None:
            to_next = self.secs_to_next
        if just_saved is None:
            just_saved = bool(self.last_at
                              and (time.time() - self.last_at) < JUST_SAVED_SECONDS)
        if just_saved:
            # ⚠ 这一档**刻意不写倒计时**：小胶囊只有一百多像素宽，同时塞
            #   「第几次 + 还有几秒」会被省略号吃掉尾巴。闪这三秒只讲一件事：
            #   **刚落了**；三秒之后倒计时自己回来。
            # [EN] ⚠ This interval **deliberately does not show a countdown**: the little capsule is only a
            # [EN] hundred-odd pixels wide, and
            # [EN] "which round + how many seconds left" at the same time would get its tail eaten by the ellipsis.
            # [EN] These three flashing seconds say only one thing:
            # [EN] **just saved**; three seconds later the countdown comes back on its own.
            return t('自动落盘 · ✓ 刚落盘（第 {k} 次）', k=int(self.count))
        if to_next is None:
            # 没有倒计时（定时器还没起 / 已经收了）—— 退回只说间隔那一种写法。
            # [EN] No countdown (timer not started / already stopped) -- fall back to the interval-only wording.
            if ago is None:
                return t('自动落盘 · 每 {n} 秒', n=iv)
            return t('自动落盘 · 每 {n} 秒（{s} 秒前）', n=iv, s=max(0, int(ago)))
        if ago is None:
            return t('自动落盘 · 还有 {n} 秒（还没落过）', n=int(to_next))
        return t('自动落盘 · 还有 {n} 秒（上次 {s} 秒前）',
                 n=int(to_next), s=max(0, int(ago)))
