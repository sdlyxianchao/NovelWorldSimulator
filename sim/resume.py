# -*- coding: utf-8 -*-
"""**停点**：这一轮停在哪儿；下一轮从哪儿接着演。

用户 2026-10-08 的原话（这段就是本模块的全部规格）：

    「运行窗口**起笔** 加一个逻辑 点击之后如果检查发现**一天的时间还没结束**
      （之前在一天没结束的时候点的停止）则**提示从某一天某个时间继续**，
      如果一天已经结束了，则**开启新一天**」

## 为什么不靠猜

一开始想从 `每天的生活/第NNN天.md` 反推"那一天演完没有" —— **推不出来**：
`RunLoop._finish()` 在收尾时会**补落当天**（不带这一步，最后一天就白跑了），
所以"第 3 天的文件在"既可能是"演完了"，也可能是"演到一半被停、收尾补的"。

所以改成**让主循环在收尾那一刻自己写下来**（`write_stop_point`，见
`RunLoop._finish`）—— 那一刻它手上正好有全部判据：

| 收尾时 | 说明 | `day_done` |
|---|---|---|
| `_ticks_today > 0` | 这一天**演了一半**就被停了（用户点名的那种） | `False` |
| `_ticks_today == 0` | 这一天**还没开演**（上一次跨天已经收过工了） | `True` |

落点：`<运行文件夹>/停点.json`。每轮一份、**滚动覆盖**（同一轮里收尾只写一次）。

## 三种情况（`plan()` 的 `kind`）

| kind | 什么时候 | 这一轮从哪开始 |
|---|---|---|
| `fresh` | 这本书还没跑过（或上一轮没留下停点） | 第 1 天 08:00（`GAME_START_TIME`） |
| `resume` | 上一轮**第 D 天演了一半**就停 | **第 D 天 · 当时那个时辰**，而且第 D 天的正文**接着写**（不覆盖） |
| `next_day` | 上一轮**第 D 天已经演完** | **第 D+1 天 08:00**（开新的一天） |

★ 本模块**只做判定与取数**：怎么写（`write_stop_point` 由主循环调）、
  怎么把起点接上（`sim/setup.py` 的 `build_world(start_clock=…)`）、
  怎么把半截正文接起来（`assemble(resume_scenes=…)` → `SceneBuilder(initial_scenes=…)`）
  —— 各归各处。这里不碰界面、不碰推演。

⚠ **一个必须说清的范围**：接上的是**故事时间**与**当天的正文**。
  世界状态（张力 / 伏笔 / 群演 / 人物记忆）仍然是**新一轮重新装配**的
  ——"完整读档继续"是 `拾卷` 那条路的事。界面上的提示只讲接上了什么，
  **不暗示接上了别的**（本项目对"夸大其词"零容忍）。

English:
**Stop point**: where this round stopped; where the next round resumes.
The user's exact words on 2026-10-08 (this passage is the entire spec for this module):
    "The run window's **起笔**: add logic so that when clicked, if the check finds **a day's time hasn't ended**
      (previously stopped before the day ended), then **prompt to continue from a certain day and time**;
      if the day has already ended, then **start a new day**"
## Why not rely on guessing
At first we wanted to infer "whether that day finished" from `每天的生活/第NNN天.md` -- **it can't be
inferred**:
`RunLoop._finish()` **appends the current day** when wrapping up (without this step, the last
day would be run for nothing),
so "day 3's file exists" could mean either "finished" or "stopped halfway and patched in at
wrap-up".
So instead we **let the main loop write it down at the wrap-up moment** (`write_stop_point`, see
`RunLoop._finish`) -- at that moment it happens to have all the criteria:
| At wrap-up | Explanation | `day_done` |
|---|---|---|
| `_ticks_today > 0` | This day was stopped **half-performed** (the case the user called out) | `False` |
| `_ticks_today == 0` | This day **hasn't started yet** (the last cross-day already wrapped up) | `True` |
Path: `<run folder>/stop_point.json`. One per round, **rolling overwrite** (written only once at
wrap-up within the same round).
## Three cases (`plan()`'s `kind`)
| kind | when | where this round starts |
|---|---|---|
| `fresh` | This book hasn't been run yet (or the previous round left no stop point) | Day 1 08:00 (`GAME_START_TIME`) |
| `resume` | The previous round stopped **partway through Day D** | **Day D, that same shichen**, and Day D's script **continues** (no overwrite) |
| `next_day` | The previous round **finished Day D** | **Day D+1 08:00** (start a new day) |
★ This module **only does decision and data retrieval**: how to write (`write_stop_point` is
called by the main loop),
  how to hook up the start point (`build_world(start_clock=…)` in `sim/setup.py`),
  how to splice the half-finished script (`assemble(resume_scenes=…)` -> `SceneBuilder(initial_scenes=…)`)
  — each in its own place. No touching the UI, no touching the simulation here.
⚠ **One scope that must be made clear**: what gets hooked up is **story time** and **that day's
script**.
  World state (tension / foreshadowing / extras / character memory) is still **re-assembled fresh each round**
  — "fully load a save and continue" is the job of the `拾卷` path. UI hints only say what was hooked up,
  **not implying anything else was hooked up** (this project has zero tolerance for "exaggeration").
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from logger import get_logger
from util.io import atomic_write_text
from util.runpath import run_root
from util.text import now_str

_LOG = get_logger('nws.resume')

#: 停点文件名（在运行文件夹里）
# [EN] : Stop point filename (in the run folder)
FILE = '停点.json'


# ══════════════════════════════════════════════════════════════════════
#  写：由主循环在收尾那一刻调（那一刻它手上才有准数）
# [EN] Write: called by the main loop at the finishing moment (only then does it have accurate figures)
# ══════════════════════════════════════════════════════════════════════
def write_stop_point(run: Any, *, day: int, minutes: int, calendar: str = '',
                     day_done: bool, ticks_today: int = 0,
                     scene: str = '', reason: str = '',
                     shichen: str = '',
                     partial_day: int | None = None,
                     story_day: int = 0) -> dict:
    """把"停在哪儿"写进 `<运行文件夹>/停点.json`。返回写下的那份。

    **失败不抛**（返回 `{'ok': False, ...}`）：这是给下一轮看的便条，
    写不出来最坏就是下一轮当"第一次"处理 —— 绝不能因此影响收尾。

    参数都是从主循环那一刻的世界里取的，本函数**不做任何推断**
    （`day_done` 是调用方算好传进来的，见模块说明里那张表）。
    
        English:
    Write "where it stopped" to `<run folder>/stop_point.json`. Return the copy that was written.
        **Failure does not raise** (returns `{'ok': False, ...}`): this is a note for the next round,
        and the worst case of not being able to write it is that the next round treats it as "the first time" — it must never affect wrap-up.
        Parameters are all taken from the world at that moment in the main loop; this function **does no inference whatsoever**
        (`day_done` is computed by the caller and passed in, see the table in the module docstring).
    """
    data = {
        'at': now_str('%Y-%m-%d %H:%M:%S'),
        'day': int(day or 0),
        'minutes': int(minutes or 0),
        #: 原样的时钟显示（如 `第3天·戌时`）—— 照实留一份，便于核对。
        # [EN] : The raw clock display (e.g. `第3天·戌时`) -- keep a copy verbatim for verification.
        'calendar': str(calendar or ''),
        #: ★ **纯时辰**（如 `戌时`）。提示文案要拼「第 3 天 · 戌时」，
        #  用上面那个整串会变成「第 3 天 · 第3天·戌时」（重复一遍天数）。
        # [EN] : ★ **Pure shichen** (e.g. `戌时`). The hint text must be composed as "Day 3 · 戌时",
        # [EN] using the whole string above would become "Day 3 · 第3天·戌时" (the day count repeated).
        'shichen': str(shichen or ''),
        'day_done': bool(day_done),
        'ticks_today': int(ticks_today or 0),
        #: ★★★ **故事天**（2026-10-31）。`day` 是**写作天**（第几份稿），
        #   两者会分叉：一次"站末补时间"可以把故事钟推过午夜，而写作天只 +1。
        #   续跑**建世界时钟**必须用这一栏；用 `day` 会让时间倒退（实测：停点
        #   `day=3` 而 `calendar` 已经写着 `第4天·辰时`，续跑一开演就退回第 3 天）。
        #   老停点没有这一栏 ⇒ 读的时候从 `calendar` 里解析（见 `story_day_of`）。
        # [EN] ★★★ **Story day** (2026-10-31). `day` is the **writing day** (which draft); the two
        #   diverge because a station-gap jump can push the story clock past midnight while the
        #   writing day only advances by one. Resuming **builds the world clock** from this field;
        #   using `day` moves time backwards (measured: the stop point said `day=3` while `calendar`
        #   already read "day 4 · chen hour", and resuming fell back to day 3).
        #   Old stop points lack this field => parse it out of `calendar` (see `story_day_of`).
        'story_day': int(story_day or 0),
        'scene': str(scene or ''),
        'reason': str(reason or ''),
        #: `day_done=False` 时：**哪一天的正文是半截的**（续跑要接着写它）。
        #: 显式记下来而不是让下一轮自己推 —— 推的话又回到"猜"了。
        # [EN] : When `day_done=False`: **which day's prose is half-finished** (continuation must append to
        # [EN] it).
        # [EN] : Record it explicitly rather than letting the next round infer it -- inferring goes back to
        # [EN] "guessing".
        'partial_day': (int(partial_day) if partial_day else None),
    }
    try:
        # ⚠ 用 `run_root()`，**不要**写 `Path(getattr(run, "root", run))`
        #   —— `Path.root` 会把运行文件夹吃掉、写到盘根去（那个坑
        #   在 `sim/autosave.py` 与这里各踩过一次，实现已收到一处）。
        # [EN] ⚠ Use `run_root()`, **do not** write `Path(getattr(run, "root", run))`
        # [EN] -- `Path.root` will swallow the run folder and write to the drive root (that pitfall
        # [EN] was stepped on once each in `sim/autosave.py` and here; already consolidated into one place).
        root = run_root(run)
        atomic_write_text(root / FILE,
                          json.dumps(data, ensure_ascii=False, indent=2))
        # ⚠ 拼**纯时辰**（`shichen`）而不是 `calendar` 整串 —— 后者本身已含
        #   "第N天"，再冠一个"第 N 天"就念成"第 3 天 第3天·戌时"（重复一遍）。
        #   提示文案当年踩过同一个坑，日志这里一并收掉。
        # [EN] ⚠ Compose the **pure shichen** (`shichen`) rather than the whole `calendar` string -- the latter
        # [EN] already contains
        # [EN] The prompt text stepped on this same pitfall back then; the log here is folded in as well.
        _LOG.info('停点：第 %d 天 %s（%s）· 今天跑了 %d 拍 · %s',
                  data['day'], data['shichen'] or '（时辰未定）',
                  '这一天演完了' if data['day_done'] else '这一天还没演完',
                  data['ticks_today'], data['scene'] or '（地点未定）')
        return {'ok': True, **data}
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('停点写入失败（不影响收尾）：%r', e)
        return {'ok': False, 'error': repr(e)}


# ══════════════════════════════════════════════════════════════════════
#  读
# [EN] Read
# ══════════════════════════════════════════════════════════════════════
def read_stop_point(run: Any) -> dict | None:
    """读一份停点。**读不到/坏了都返回 `None`**（调用方当"没有上一轮"处理）。
        English:
    Read a stop point. **Returns `None` whether unreadable or corrupted** (caller treats it as "no
    previous round").
    """
    if run is None:
        return None
    try:
        root = run_root(run)          # ⚠ 同上：`Path.root` 陷阱
        # [EN] ⚠ Same as above: the `Path.root` trap
        p = root / FILE
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not int(data.get('day') or 0):
            return None
        return data
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('停点读取失败（当没有上一轮处理）：%r', e)
        return None


def latest_run(proj: Any) -> Any | None:
    """项目里**最近一次**运行文件夹（`RunFolder`）。没有就 `None`。

    ⚠ 与 `gui/app_flet._latest_run_folder()` 同一件事，但那边是界面的私有方法
    （返回给导出用），这里要独立取一次 —— 依赖界面会让无头脚本用不了。
    
        English:
    The project's **most recent** run folder (`RunFolder`). `None` if there is none.
        ⚠ Same thing as `gui/app_flet._latest_run_folder()`, but that one is a private method of the UI
        (returned for export), and here we must fetch it independently — depending on the UI would make headless scripts unusable.
    """
    try:
        runs = proj.list_runs()
    except Exception:                                            # noqa: BLE001
        return None
    if not runs:
        return None
    try:
        from store.runfolder import RunFolder
        return RunFolder(runs[-1].parent, runs[-1].name)
    except Exception:                                            # noqa: BLE001
        return None


# ══════════════════════════════════════════════════════════════════════
#  判定：下一轮从哪儿开始（界面「起笔」读这一份）
# [EN] Decision: where the next round starts (the UI "起笔" reads this)
# ══════════════════════════════════════════════════════════════════════
#: `plan()['kind']` 的三种取值（写在这里，别的模块要比较就引它）
# [EN] : The three values of `plan()['kind']` (written here; other modules should reference it when
# [EN] comparing)
FRESH = 'fresh'
RESUME = 'resume'
NEXT_DAY = 'next_day'


def _cal_of(stop: dict) -> str:
    """停点里"那一刻"的**纯时辰**（如 `戌时`）。

    ★ 为什么不能直接用 `stop['calendar']`：那个是 `world.clock_display()` 的**原样整串**
      （`第3天·戌时`），而提示文案是 `第 {n} 天 · {时辰}` 这样拼的 ——
      直接用会拼出「第 3 天 · 第3天·戌时」（天数讲两遍）。
      （真机探针 `developers/probe_start_point.py` 当场打出来的就是这个。）
    
        English:
    The **pure shichen** of "that moment" in the stop point (e.g. `戌时`).
        ★ Why not just use `stop['calendar']`: that is the **verbatim whole string** from `world.clock_display()`
          (This is exactly what the on-device probe `developers/probe_start_point.py` prints out on the spot.)
    """
    return str((stop or {}).get('shichen') or (stop or {}).get('calendar') or '')


def story_day_of(stop: dict | None) -> int:
    """停点那一格的**故事天**（续跑建世界时钟用）。

    ★★★ 2026-10-31：`stop['day']` 是**写作天**（第几份稿），不是故事天。
      两者会分叉 —— 一次"站末补时间"能把故事钟推过午夜，写作天只 +1。
      实测（`第一部_聊斋夜客` 第2次模拟的停点）：`day=3`，而 `calendar` 已经是
      `第4天·辰时`。以前 `start_clock_of()` 拿 `day` 建时钟 ⇒ **续跑时间倒退一天**。
    ⚠ 老停点没有 `story_day` 一栏（2026-10-31 之前写的）⇒ 从 `calendar` 里解析
      「第N天」；连 `calendar` 都没有（更老的格式）才退回 `day`。
      解析顺序**不能反**：先读显式字段，再解析字符串，最后才猜。

        English:
    The **story day** recorded in the stop point (used to build the world clock on resume).
        ★★★ 2026-10-31: `stop['day']` is the **writing day** (which draft), not the story day.
        The two diverge -- one "station gap" jump can push the story clock past midnight while the
        writing day only advances by one. Measured (stop point of the 2nd run of
        `第一部_聊斋夜客`): `day=3` while `calendar` already read "day 4 · chen hour". The old
        `start_clock_of()` built the clock from `day`, so **resuming moved time backwards a day**.
        ⚠ Old stop points have no `story_day` field (written before 2026-10-31) => parse "第N天"
        out of `calendar`; only when `calendar` is absent too fall back to `day`.
        Order must not be reversed: explicit field, then parse, then guess last.
    """
    stop = stop or {}
    try:
        explicit = int(stop.get('story_day') or 0)
    except Exception:                                            # noqa: BLE001
        explicit = 0
    if explicit > 0:
        return explicit
    m = re.search(r'第\s*(\d+)\s*天', str(stop.get('calendar') or ''))
    if m:
        return max(1, int(m.group(1)))
    return max(1, int(stop.get('day') or 1))


def plan(proj: Any, *, start_hour: int = 8) -> dict:
    """这一轮该从哪儿开始。返回一份**纯数据**（界面自己拼句子）。

    ```
    {'kind': 'fresh'|'resume'|'next_day',
     'day': 3,                # 这一轮从第几天起
     'minutes': 1230,         # 当天第几分钟（8*60 = 08:00）
     'calendar': '戌时',      # 上一轮停下的时辰（给人看）
     'partial_day': 3,        # 要接着写的半截天（`resume` 才有，否则 None）
     'run': Path(...),        # 上一轮的运行文件夹（续跑要读那天的正文）
     'stop': {...},           # 原始停点（没有则 None）
     }
    ```

    `start_hour` = "新的一天从几点起"（与 `GAME_START_TIME` 同义，默认 8 点）。
    
        English:
    Where this round should start. Returns **pure data** (the UI assembles the sentence itself).
        ```
        {'kind': 'fresh'|'resume'|'next_day',
         'day': 3,                # which day this round starts from
         'minutes': 1230,         # minute of the day (8*60 = 08:00)
         'calendar': '戌时',      # the shichen the previous round stopped at (for humans)
         'partial_day': 3,        # the half-finished day to continue writing (only `resume` has it, otherwise None)
         'run': Path(...),        # the previous round's run folder (continuing needs to read that day's script)
         'stop': {...},           # the raw stop point (None if absent)
         }
        ```
        `start_hour` = "what hour a new day starts at" (synonymous with `GAME_START_TIME`, defaults to 8 o'clock).
    """
    run = None
    stop = None
    # ★ 整段套 try：查停点失败（目录炸了、盘符拔了…）**不能把「起笔」顶住** ——
    #   退回"从头开始"最坏也就是多演一遍第 1 天，而点不动的按钮是死路。
    #   （反例法⑫把 `read_stop_point` 改成会抛，当场证明少了这一层整个就崩。）
    # [EN] ⚠ Wrap the whole thing in try: a failed stop-point lookup (directory blew up, drive
    # [EN] unplugged...) **must not block "起笔"** --
    # [EN] falling back to "start from the beginning" is at worst replaying day 1 once, whereas a dead
    # [EN] button is a dead end.
    # [EN] (Counterexample method ⑫ changed `read_stop_point` to throw, proving on the spot that without
    # [EN] this layer everything collapses.)
    try:
        run = latest_run(proj)
        if run is not None:
            stop = read_stop_point(run)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('查上一轮停点失败（这一轮按从头开始）：%r', e)
    if not stop:
        return {'kind': FRESH, 'day': 1, 'story_day': 1,
                'minutes': int(start_hour) * 60,
                'calendar': '', 'partial_day': None, 'run': None, 'stop': None}

    day = max(1, int(stop.get('day') or 1))
    # ★★★ 2026-10-31：`day`（写作天，稿子编号）与 `story_day`（故事钟）**分开带走**。
    #   · 落盘/幕头/界面 → `day`
    #   · 建世界时钟     → `story_day`（拿 `day` 会倒退，见 `story_day_of`）
    story_day = story_day_of(stop)
    if stop.get('day_done'):
        # 上一天已经收工 —— 开**新的一天**（停点里那个 day 就是"还没开演的那天"）
        # [EN] The previous day already wrapped up -- start a **new day** (the day in the stop point is "the
        # [EN] day not yet started")
        return {'kind': NEXT_DAY, 'day': day, 'story_day': story_day,
                'minutes': int(start_hour) * 60,
                'calendar': _cal_of(stop),
                'partial_day': None, 'run': run, 'stop': stop}
    # 这一天演了一半 —— **从停下的那一刻接着演**
    # [EN] This day is half-performed -- **resume from the exact moment it stopped**
    partial = stop.get('partial_day')
    return {'kind': RESUME, 'day': day, 'story_day': story_day,
            'minutes': max(0, int(stop.get('minutes') or 0)),
            'calendar': _cal_of(stop),
            'partial_day': int(partial or day), 'run': run, 'stop': stop}


def start_clock_of(p: dict):
    """把 `plan()` 的结果翻成 `GameTime`（`sim/setup.build_world` 要的那个）。

    ⚠ 返回 `None` 表示"用默认起点"（第 1 天 08:00 / `GAME_START_TIME`）——
      `fresh` 就是这样，让既有的配置项继续说话，别在这里把它顶掉。
    
        English:
    Translate `plan()`'s result into `GameTime` (the one `sim/setup.build_world` wants).
        ⚠ Returning `None` means "use the default start point" (Day 1 08:00 / `GAME_START_TIME`) —
          that is exactly the `fresh` case; let the existing config option keep speaking, don't override it here.
    """
    if not p or p.get('kind') == FRESH:
        return None
    try:
        from util.timefmt import GameTime
        # ★ 2026-10-31：建时钟用**故事天**（`story_day`），不是写作天 `day`。
        #   两者分叉时用 `day` 会让续跑的时间**倒退**（实测：停点 day=3、calendar 第4天，
        #   续跑一开演就退回第 3 天辰时）。
        # [EN] ★ 2026-10-31: build the clock from the **story day** (`story_day`), not the writing
        # [EN] day `day`. When the two diverge, using `day` makes resumed time move **backwards**
        # [EN] (measured: stop point said day 3 while calendar read day 4).
        return GameTime(day=max(1, int(p.get('story_day') or p.get('day') or 1)),
                        minutes=max(0, int(p.get('minutes') or 0)))
    except Exception:                                            # noqa: BLE001
        return None


def load_resume_scenes(p: dict) -> list:
    """续跑时把**那一天的半截正文**读回来（读不到就返回空表 = 不合并）。

    ★ 为什么要它：上一轮被停时，收尾**补落**过一份当天的稿子
      （`_finish` → `_end_day`）。这一轮接着写同一天，如果不把那份读回来，
      `flush_daily_script` 会**整个覆盖**它 —— 那一天前半段就没了。
      项目铁律里最不能碰的一条就是"不许静默丢内容"。

    ⚠ 读回来的幕只是**当天的起点**：新一轮从它后面接着长。
      `_known_cast` 也要按它填（见 `SceneBuilder(initial_scenes=…)`），
      否则续跑第一拍会把每个人再"入画"介绍一遍。
    
        English:
    On continuation, read back **that day's half-finished script** (returns an empty list if
    unreadable = no merge).
        ★ Why it's needed: when the previous round was stopped, wrap-up **made a supplementary write** of that day's draft
          (`_finish` -> `_end_day`). If this round continues the same day without reading that copy back,
          `flush_daily_script` will **overwrite it entirely** — the first half of that day is gone.
          The one project iron rule that must never be broken is "no silently dropping content".
        ⚠ What is read back is only the **starting point of that day**: the new round grows on from after it.
          `_known_cast` must also be filled accordingly (see `SceneBuilder(initial_scenes=…)`),
          Otherwise, resuming the first beat will introduce each person by "entering the scene" all over again.
    """
    if not p or p.get('kind') != RESUME:
        return []
    day = int(p.get('partial_day') or p.get('day') or 0)
    run = p.get('run')
    if not day or run is None:
        return []
    try:
        scenes = list(run.read_daily_script(day) or [])
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('续跑：读回第 %d 天的半截正文失败（这一天从新的一幕起）：%r',
                     day, e)
        return []
    if scenes:
        _LOG.info('续跑：第 %d 天已有 %d 幕，接着写（不覆盖）', day, len(scenes))
    return scenes


# ══════════════════════════════════════════════════════════════════════
#  上次演到哪儿（续跑时**屏幕上要接着看的那些字**，2026-10-11）
# [EN] Where it last got to (the text that **should continue on screen** when resuming, 2026-10-11)
# ══════════════════════════════════════════════════════════════════════
#
# 用户报的两个问题（一次说完，它们同一个根）：
# [EN] Two problems the user reported (stated at once; they share the same root):
#
#   「我每次运行 即使我是打开的某个存档 再次点击起笔，前情提要都一样
#     是不是推演进度没有被记录」
#   「运行界面 对话显示窗口也应该带着之前的记录 继续输出
#     现在是会清空 然后重新开始的样子」
# [EN] "Every time I run, even if I open a certain save, when I click 起笔 again the recap is always the
# [EN] same"
# [EN] "Is the simulation progress not being recorded?"
# [EN] "The run UI conversation display window should also carry the previous records and keep
# [EN] outputting
# [EN] right now it clears and then restarts"
#
# 查下来的实情：**进度是记着的**（`停点.json` 里 `day/minutes/ticks_today`
# 都在，续跑也确实从那一刻接上了）。缺的是**屏幕上那两块料**：
# [EN] What the investigation found: **progress IS recorded** (in `停点.json` the
# [EN] `day/minutes/ticks_today`
# [EN] are all there, and continuation really does pick up from that moment). What's missing is **those
# [EN] two blocks on screen**:
#
#   ① 中栏：`_start_round` 里一句 `self._live_lines = []` 把屏幕清了；
#   ② 前情提要：本轮是**新开的一轮**，`state.db` 是新的空库 ⇒
#      `recap_text()` 读不到摘要、读不到事件，一路退到设定集的
#      `_opening_context`（"这个世界是什么样"）——
#      于是**每一轮都是同一句开场白**，看起来就像"什么都没记住"。
# [EN] ① Middle column: in `_start_round` a single `self._live_lines = []` clears the screen;
# [EN] ② Recap: this round is a **newly started round**, `state.db` is a fresh empty DB ⇒
# [EN] `recap_text()` can't read a summary, can't read events, falls all the way back to the setting
# [EN] collection's
# [EN] `_opening_context` ("what this world is like") --
# [EN] so **every round has the same opening line**, looking like "nothing was remembered".
#
# 所以这里补两个"读上一轮"的取数口。**只读，不写**（与模块开头那条
# "本模块只做判定与取数"一致）。
# [EN] So here we add two "read the previous round" data-access ports. **Read only, no write**
# [EN] (consistent with the module header's
# [EN] "this module only does decision-making and data access").

#: 上次那段正文取多长（字符）。太长会把中栏淹掉，太短又看不出"演到哪了"。
#  3000 字 ≈ 一般的一小场戏，一屏多一点。
# [EN] : How long to take the previous prose segment (chars). Too long floods the middle column; too
# [EN] short and you can't tell "how far it got".
# [EN] 3000 chars ≈ a typical small scene, a bit more than one screen.
PREV_CHARS = 3000


def _prev_run_dir(p: dict):
    """上一轮的运行文件夹（`plan()` 的结果里带着）。拿不到就 None。
        English:
    The run folder from the previous round (carried in the result of `plan()`). If unavailable,
    None.
    """
    run = (p or {}).get('run')
    root = getattr(run, 'root', None)
    return root if root is not None else None


def _read_text(path) -> str:
    try:
        return str(path.read_text(encoding='utf-8', errors='replace') or '')
    except Exception:                                            # noqa: BLE001
        return ''


def load_prev_prose(p: dict, *, limit: int = PREV_CHARS,
                    notice: bool = True) -> str:
    """上一轮**演到哪儿**的正文（末尾 `limit` 字）。读不到返回空串。

    取数优先级（**正式稿优先**，它是收工/跨天写下的完整那一份）：
      ① `<上一轮>/每天的生活/第NNN天.md` —— 正式稿
      ② `<上一轮>/自动落盘/进度.md`      —— 中途稿（还没收工就停了）

    ⚠ 取**末尾**而不是开头：故事的"最近"在后面 —— 续跑的人要知道
      "刚才演到哪儿"，而不是"这一天开头是什么"。
    ⚠ 文件里的人话部分是**正文**；这里**不试图解析结构**（不抽台词、不重建
      分幕）—— 屏幕要的是"带着之前的记录继续看"，给原文最不失真。
      真正要做数据合并的是 `load_resume_scenes()`（那条走结构化路径）。
    `notice=False` ⇒ 截断时**不加**那句"更早部分见文件"
      （给 `resume_recap` 用：那句话是给中栏历史卡看的，混进前情提要里很怪）。
    
        English:
    The body text of **how far the previous round played** (the trailing `limit` characters). If
    unreadable, return an empty string.
        Fetch priority (**the formal draft takes priority**, since it is the complete one written at wrap-up / across days):
        ⚠ Take the **tail** rather than the beginning: the story's "most recent" part is at the back —— the one resuming needs to know
          "where it just played up to", not "what the start of this day was".
        ⚠ The human-readable part of the file is the **body text**; here we **do not attempt to parse structure** (no extracting dialogue, no rebuilding
          scenes) —— what the screen wants is "continue watching with the previous record", so giving the raw text is the least lossy.
          What actually needs data merging is `load_resume_scenes()` (that one goes the structured path).
        `notice=False` ⇒ when truncating, do **not** add the line "see file for earlier parts"
          (used for `resume_recap`: that line is for the middle-column history card, and it looks weird mixed into the recap).
    """
    root = _prev_run_dir(p)
    if root is None:
        return ''
    day = int((p or {}).get('partial_day') or (p or {}).get('day') or 0)
    cands: list = []
    try:
        daily = root / '每天的生活'
        if day:
            cands.append(daily / f'第{day:03d}天.md')
        if daily.exists():
            cands.extend(sorted(daily.glob('第*.md'), reverse=True)[:1])
        cands.append(root / '自动落盘' / '进度.md')
    except Exception:                                            # noqa: BLE001
        return ''
    for c in cands:
        try:
            if not c.exists():
                continue
        except Exception:                                        # noqa: BLE001
            continue
        text = _read_text(c).strip()
        if not text:
            continue
        if len(text) > limit:
            # 从**段落边界**切（切在半句上，看着像坏了）
            # [EN] Cut at **paragraph boundaries** (cutting mid-sentence looks broken)
            head = text[-limit:]
            cut = head.find('\n')
            if 0 <= cut < 400:
                head = head[cut + 1:]
            text = (('…（上面这一段的更早部分见文件）\n' if notice else '')
                    + head)
        return text
    return ''


#: 只该进"给人读的正文"的行首 —— 别的行（`▸ 出场` / `· 动作` / `## 辰时` /
#  `**场景**` / `〔图〕`）是**剧本的结构标记**，不是正文。
#  ⚠ 前情提要是**一句话**，混进"▸ 出场 <某人>（入画）"读起来就是坏的。
# [EN] : Only line starts that should enter "prose for human reading" -- other lines (`▸ 出场` / `· 动作` /
# [EN] `## 辰时` /
# [EN] `**场景**` / `〔图〕`) are **script structural markers**, not prose.
# [EN] ⚠ The recap is **one sentence**; mixing in "▸ 出场 <someone>（入画）" reads as broken.
_PLAIN_SKIP = ('▸', '·', '〔', '#', '**', '>', '---')


def plain_prose(text: str, *, limit: int = 0) -> str:
    """把剧本体的正文洗成**一句话式**的纯文字（抹掉结构标记与 markdown 记号）。

    `limit > 0` ⇒ 只留**末尾** limit 字（故事的"最近"在后面）。
    
        English:
    Wash the body text of the script into **one-sentence-style** plain text (erase structural
    markers and markdown notation).
        `limit > 0` ⇒ keep only the **trailing** limit characters (the story's "most recent" part is at the back).
    """
    out: list[str] = []
    for ln in str(text or '').splitlines():
        s = ln.strip()
        if not s or s.startswith(_PLAIN_SKIP):
            continue
        s = s.lstrip('#').strip().lstrip('>').strip()
        s = s.replace('**', '').replace('　', ' ').strip()
        if not s:
            continue
        out.append(s)
    joined = ' '.join(out).strip()
    if limit > 0 and len(joined) > limit:
        joined = joined[-limit:]
    return joined


def resume_recap(p: dict) -> str:
    """续跑时的「上一回说到」——**本轮开头的前情提要该说的话**。

    ⚠ 为什么不能用 `recap_text()` 自己那套：它读的是**本轮**的 db，
      而本轮 db 是新的（空）⇒ 它只能退到设定集的开场白。
      那正是用户看到的"每次前情提要都一样"。

    这里给的是**上一轮的位置 + 上一轮正文的最后一小段**：
      「上一回演到 第 1 天 · 辰时（<某个地点>），说到：
        ……（末尾两百字）」

    读不到正文就**只给位置**（那也远好过一句设定集开场白）；连位置都没有
    就返回空串（调用方照旧走老路）。
    
        English:
    The "last time on..." for resuming —— **what the recap at the start of this round should say**.
        ⚠ Why we can't use `recap_text()`'s own approach: it reads the db of **this round**,
          and this round's db is new (empty) ⇒ it can only fall back to the setting collection's opening.
          That is exactly the "every recap is the same" the user sees.
        What is given here is **the previous round's position + the last small chunk of the previous round's body text**:
          "Last time it played up to Day 1 · Chen hour (<some location>), saying:
            ...(last two hundred characters)"
        If the body text is unreadable, **give only the position** (that is still far better than a setting-collection opening line); if even the position is
        unavailable, return an empty string (the caller proceeds along the old path as before).
    """
    from i18n import t
    if not p or p.get('kind') == FRESH:
        return ''
    stop = p.get('stop') if isinstance(p.get('stop'), dict) else {}
    day = int((p or {}).get('day') or 1)
    cal = str((p or {}).get('shichen') or (p or {}).get('calendar') or '')
    scene = str((p or {}).get('scene') or stop.get('scene') or '')
    where = f'{t("第 {n} 天", n=day)}'
    if cal:
        where += f' · {cal}'
    if scene:
        where += f'（{scene}）'
    prose = plain_prose(load_prev_prose(p, limit=400, notice=False), limit=240)
    if prose:
        # ⚠ **prose 不能进 `t(...)` 的 format** —— 正文里万一有 `{`/`}`，
        #   `.format()` 会抛（而 `t()` 把异常吞掉，返回来的是**没替换占位符**
        #   的原样模板："上一回演到 {where}，说到：…"，看着像译文坏了）。
        #   所以模板先单独 format 好，再拼正文。
        # [EN] ⚠ **prose must not enter `t(...)`'s format** -- if the prose happens to contain `{`/`}`
        # [EN] `.format()` will throw (and `t()` swallows the exception, returning the **unsubstituted
        # [EN] placeholder**
        # [EN] So format the template separately first, then concatenate the prose.
        return t('上一回演到 {where}，说到：', where=where) + prose
    return t('上一回演到 {where}。', where=where)


def start_recap(p: dict, *, worldview_text: str = '') -> str:
    """**本轮开头屏幕上会念的那句前情提要** —— 「起笔」对话框与运行窗口**同一份**。

    用户 2026-10-11：
    「我希望在起笔的时候，可以有一个地方加上用户自己对于故事接下来走向的建议。
      我觉得可以在提笔的前情提要的下面（我不确定现在的提笔对话框带不带前情提要，
      如果没加记得加上，然后在下面加上您对接下来剧情发展的建议这个文本框）
      **而且请确保这里的前情提要和后续运行窗口对话显示的时候给的前情提要一样**。」

    `RunLoop._recap_text()` 的取数顺序是**两段**：

    | 情形 | 它取什么 | 本函数怎么对上 |
    |---|---|---|
    | 续跑 / 开新的一天（`resume` / `next_day`） | `self._resume_recap`，也就是 `resume_recap(plan)` | **同一个函数、同一份 plan** ⇒ 逐字相同 |
    | 这本书还没跑过（`fresh`） | `DAYPLAN.recap_text(db, world)` —— 本轮 db 是**空库**、`world.game_day` 是 1，于是只能落到 ③ `_opening_context(world)` | 传 `worldview_text` 进来，走**同一个** `DAYPLAN.opening_context()` ⇒ 逐字相同 |

    `worldview_text` 由调用方给（对话框用 `sim.setup.worldview_text_of(项目设定集)`，
    与装配时 `build_world` 拼的**是同一个函数**）。给不出（读不到设定集）⇒
    只有 fresh 那一路会因此为空 —— 那也**照实为空**，不编一句顶上。

    ⚠ fresh 那一格有个前提要写清楚：装配出来的 world 的 `game_day` 必须是 1。
      本项目 `GAME_START_TIME` 默认就是第 1 天 08:00，而"这本书没跑过"时
      `plan()` 也明写 `day=1` —— 两边一致，所以成立。哪天起点被改成"第 3 天开演"，
      这里要跟着改（判据 A4 就是拿真装配出来的 loop 对答案，改坏了会当场红）。
    
        English:
    **The recap line that will be read aloud on screen at the start of this round** —— the "start
    writing" dialog and the run window share **the same one**.
        User 2026-10-11:
        "I hope that when starting to write, there can be a place to add the user's own suggestions for where the story should go next.
          I think it could go below the recap in the start-writing dialog (I'm not sure whether the current start-writing dialog has a recap;
          if not, remember to add one, and then below it add this text box for your suggestions on the next plot developments)
          **And please make sure the recap here is the same as the recap shown in the subsequent run window dialogue**."
        The fetch order of `RunLoop._recap_text()` is **two segments**:
        | Case | What it fetches | How this function matches up |
        |---|---|---|
        | Resuming / starting a new day (`resume` / `next_day`) | `self._resume_recap`, i.e. `resume_recap(plan)` | **Same function, same plan** ⇒ word-for-word identical |
        | This book has never been run (`fresh`) | `DAYPLAN.recap_text(db, world)` —— this round's db is an **empty database**, `world.game_day` is 1, so it can only fall to ③ `_opening_context(world)` | Pass `worldview_text` in and go through the **same** `DAYPLAN.opening_context()` ⇒ word-for-word identical |
        `worldview_text` is supplied by the caller (the dialog uses `sim.setup.worldview_text_of(project setting collection)`,
        which is **the same function** used when `build_world` assembles it). If it can't be supplied (setting collection unreadable) ⇒
        only the fresh path will be empty because of this —— and then it is **honestly empty**, don't make up a line to fill in.
        ⚠ The fresh cell has a precondition to state clearly: the assembled world's `game_day` must be 1.
          This project's `GAME_START_TIME` defaults to Day 1 08:00, and when "this book has never been run"
          `plan()` also explicitly states `day=1` —— both sides agree, so it holds. If someday the start point is changed to "start playing on Day 3",
          this must be changed accordingly (criterion A4 checks the answer against a genuinely assembled loop; breaking it will go red on the spot).
    """
    from director import day_plan as _DAYPLAN
    if not p:
        return ''
    if str((p or {}).get('kind') or '') != FRESH:
        return resume_recap(p)
    return _DAYPLAN.opening_context(worldview_text)


# ══════════════════════════════════════════════════════════════════════
#  一句话文案（**只在这一层拼**，界面与无头脚本共用同一份说法）
# [EN] One-line text (**composed only at this layer**; UI and headless scripts share the same wording)
# ══════════════════════════════════════════════════════════════════════
def describe(p: dict) -> tuple[str, str]:
    """`(一句话, 细节)`。`一句话`说这一轮从哪开始，`细节`给依据。

    ⚠ 三种 kind 各有各的说法，**不许含糊**（"接着演"和"开新的一天"是两件事，
      含糊成一件事，用户就不知道上次到底演完没有 —— 那正是他问的）。
    
        English:
    `(one sentence, details)`. `one sentence` says where this round starts, `details` gives the
    basis.
        ⚠ The three kinds each have their own wording, **no vagueness allowed** ("continue playing" and "start a new day" are two different things,
          blur them into one and the user won't know whether last time actually finished playing —— and that is exactly what he asked).
    """
    from i18n import t
    k = (p or {}).get('kind')
    day = int((p or {}).get('day') or 1)
    cal = str((p or {}).get('shichen') or (p or {}).get('calendar') or '')
    if k == RESUME:
        when = f'{t("第 {n} 天", n=day)} · {cal}' if cal else t('第 {n} 天', n=day)
        return (t('接着上次演 —— 从 {when} 起', when=when),
                t('上次是在这一天**演到一半**停的（不是收工）—— '
                  '这一轮从那个时间继续，这一天的稿子接着写、'
                  '前半段不会丢。'))
    if k == NEXT_DAY:
        return (t('开新的一天 —— 第 {n} 天', n=day),
                t('上一次已经把**上一天演完了**（收工落盘过）—— '
                  '所以这一轮从新的一天开始。'))
    return (t('从头开始 —— 第 1 天'), t('这本书还没有跑过（上一轮没留下停点）。'))
