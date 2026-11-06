# -*- coding: utf-8 -*-
"""把 tools/ 下所有 `verify_*.py` 跑一遍，记**退出码**和结论行。

（`measure_*.py` 那两支量测工具已挪去 `developers/`，不再自动跑 —— 它们是
改尺寸时手动用的"尺子"，不是断言集。）

⚠ 为什么现在能信退出码了：2026-10-06 修掉了「`await shutdown(page)` 之后的
`exit_now()` 是死代码」这个坑（见 `util/flet_shutdown.shutdown()`）。
在这之前所有脚本**退出码恒为 0**，靠 `&&` 串起来的下游全是假绿。

★★ 并行跑（2026-10-06 加）
--------------------------
65 支脚本串行要跑 11 分钟，其中大部分时间是在**等**（等 Flutter 客户端起来、
等 `asyncio.sleep` 的那几拍）。这些脚本互相独立（各自 `isolate_projects_dir()`
到临时目录），所以可以分组并行。

**分组是白名单，不是自动判断**：每支脚本必须**显式**出现在一个组里，
新加脚本忘了登记 → 直接报错退出（不静默塞进某个组 —— 那是"测试悄悄变慢/变脆"
的经典来源）。三组：

  · `LOGIC` —— 纯逻辑，不起 Flet 窗口。快、且**互不打扰**，可以开很宽。
  · `GUI`   —— 真机 Flet 窗口。每个实例要起一个 Flutter 客户端，并发受限。
  · `ALONE` —— **必须独占**（并行会互相干扰），严格一次一支。见下面那段。

⚠ **为什么 `ALONE` 是必须的**（实测，别再试）：
  · `verify_taskbar_icon`：用 `find_app_hwnd(title)` → `FindWindowW(None, title)`
    **按窗口标题**找自己的窗口。并行时多个实例标题一样 → 找到**别人**的窗口，
    读到别人的图标 → 判据随机变红（`find_app_hwnd` 还有一层"枚举所有可见窗口、
    按标题关键词兜底"，一样认不出是谁）。
  · `verify_icon` / `verify_taskbar_icon`：会**故意重写**共享产物
    `assets/images/icon*` + `assets/{app_icon.png,app_icon.ico}`
    （它们就是要验"换了图标之后产物会不会跟着换"）→ 两个实例抢同一批文件。

★★ **并行之后结论还可信吗？** —— 这是这套东西唯一真正要回答的问题。
所以有两个保障：
  1. **`--recheck`（默认开）**：并行阶段**失败**的脚本，会**串行**再跑一遍。
     两次都红 = 真红；串行绿 = **并行不稳**，报告里单列出来。
     一次失败就当"产品坏了"是错的，一次通过就当"没事"也是错的。
  2. `developers/probe_parallel.py`：同一批脚本串行/并行各跑一遍，
     逐支比对退出码与结论行。改分组、改并发之后拿它复核。

用法：
    .venv\\Scripts\\python.exe tools/run_all_verifications.py            # 并行（默认）
    .venv\\Scripts\\python.exe tools/run_all_verifications.py --serial    # 回到一次一支
    .venv\\Scripts\\python.exe tools/run_all_verifications.py --jobs 8    # 调大真机并发
    .venv\\Scripts\\python.exe tools/run_all_verifications.py --groups    # 只列分组
    .venv\\Scripts\\python.exe tools/run_all_verifications.py --only verify_minimap,verify_font
产出：assets/screenshots/all_verifications.txt（逐行：退出码 + 脚本 + 结论）

English:
Run every `verify_*.py` under tools/, recording the **exit code** and the conclusion line.
(The two measurement tools `measure_*.py` have been moved to `developers/` and no longer run
automatically -- they are
the "rulers" used manually when changing dimensions, not an assertion set.)
⚠ Why the exit codes can be trusted now: on 2026-10-06 the pitfall of "`exit_now()` after
`await shutdown(page)` is dead code" was fixed (see `util/flet_shutdown.shutdown()`).
Before that, all scripts had **exit code always 0**, and everything downstream chained with `&&`
was falsely green.
★★ Parallel execution (added 2026-10-06)
--------------------------
65 scripts take 11 minutes to run serially, most of which is **waiting** (waiting for the
Flutter client to start,
waiting for those few beats of `asyncio.sleep`). These scripts are mutually independent (each
`isolate_projects_dir()`
into a temp directory), so they can be grouped and run in parallel.
**Grouping is a whitelist, not automatic detection**: every script must **explicitly** appear in
a group,
and a newly added script that was forgotten → errors out immediately (no silently stuffing it
into some group -- that is a classic source
of "tests quietly getting slower/ more brittle"). Three groups:
  · `LOGIC` -- pure logic, no Flet window. Fast, and **mutually non-interfering**, can be run very wide.
  · `GUI`   -- real-machine Flet window. Each instance starts a Flutter client, concurrency is limited.
  · `ALONE` -- **must be exclusive** (parallel runs interfere with each other), strictly one at a time. See the section below.
⚠ **Why `ALONE` is required** (measured, don't try again):
  · `verify_taskbar_icon`: uses `find_app_hwnd(title)` → `FindWindowW(None, title)`
    to find its own window **by window title**. When parallel, multiple instances have the same title → finds **someone else's** window,
    reads someone else's icon → the criterion randomly turns red (`find_app_hwnd` also has a layer of "enumerate all visible windows,
    fall back by title keyword", which likewise can't tell who is who).
  · `verify_icon` / `verify_taskbar_icon`: will **deliberately rewrite** the shared artifacts
    `assets/images/icon*` + `assets/{app_icon.png,app_icon.ico}`
    (they are precisely verifying "after changing the icon, do the artifacts change accordingly") → two instances fight over the same batch of files.
★★ **Are the conclusions still trustworthy after parallelizing?** -- this is the only question
this whole thing really has to answer.
So there are two safeguards:
  1. **`--recheck` (on by default)**: scripts that **failed** in the parallel phase are run again **serially**.
     Red both times = truly red; green serially = **parallel unstable**, listed separately in the report.
     Treating one failure as "the product is broken" is wrong, and treating one pass as "fine" is also wrong.
  2. `developers/probe_parallel.py`: run the same batch of scripts serially and in parallel,
     comparing exit codes and conclusion lines script by script. Use it to re-check after changing groups or concurrency.
Usage:
    .venv\\Scripts\\python.exe tools/run_all_verifications.py            # parallel (default)
    .venv\\Scripts\\python.exe tools/run_all_verifications.py --serial    # back to one at a time
    .venv\\Scripts\\python.exe tools/run_all_verifications.py --jobs 8    # raise real-machine concurrency
    .venv\\Scripts\\python.exe tools/run_all_verifications.py --groups    # list groups only
    .venv\\Scripts\\python.exe tools/run_all_verifications.py --only verify_minimap,verify_font
Output: assets/screenshots/all_verifications.txt (line by line: exit code + script + conclusion)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PY = APP / '.venv' / 'Scripts' / 'python.exe'
OUT = APP / 'assets' / 'screenshots' / 'all_verifications.txt'

sys.path.insert(0, str(APP))
#: 结束**整棵**进程树（连 `flet.exe` 客户端一起）与清理孤儿客户端。
#: 详见 `util/flet_shutdown.py` —— 那里记着"为什么要 /T"。
# [EN] : Terminate the **whole** process tree (including the `flet.exe` client) and sweep orphan
# [EN] clients. See `util/flet_shutdown.py` for "why /T".
from util.flet_shutdown import kill_pid_tree as _kill_tree          # noqa: E402
from util.flet_shutdown import sweep_orphan_clients                 # noqa: E402

#: 反例法残留标记的**唯一判法**（见 `_mutation_leftovers` 的说明）——
#: `tools/` 自身入 `sys.path` 之后才 import，不依赖启动时的工作目录
#: （`audit_code.py` 用 `exec_module` 加载本文件时，sys.path[0] 未必是 tools）。
# [EN] The **single criterion** for leftover mutation markers (see `_mutation_leftovers`) --
# [EN] imported after putting `tools/` itself on `sys.path`, so it does not depend on the
# [EN] launch working directory (`audit_code.py` loads this file via `exec_module`, where
# [EN] sys.path[0] is not necessarily tools).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_mutation_anchors import mutation_leftovers as _mutation_left   # noqa: E402

#: 单飞锁：同时只允许一份全量回归（`.gitignore` 无关，在 logs/ 里，不打包）。
#: 内容 `{"pid": …, "started": …}`；持有者已死则自动接管（见 `acquire_run_lock`）。
# [EN] Single-flight lock: only one full regression at a time (lives in logs/, not packaged).
# [EN] Content `{"pid": …, "started": …}`; taken over automatically if the holder is dead.
RUN_LOCK = APP / 'logs' / '.regression.lock'

#: 锁超过这个小时数就算陈旧（防 PID 复用把锁永久占住）。
# [EN] : A lock older than this many hours is stale (guards against PID reuse locking it forever).
LOCK_STALE_HOURS = 12

#: **公共工具**，不是断言集 ⇒ 不跑、也不进分组表。
#:   · `verify_ui_common` —— GUI 判据共用的量测工具。
#:   · `verify_exit` —— **退出码统一出口**（`finish()` / `failed_checks()`），
#:     给各判据把"红了"变成"退出码非 0"用。
#: ⚠ 这两个是**库**，磁盘上确实有 `verify_*.py`，所以对表时要排掉 ——
#:   否则"磁盘上有、但没登记分组"会一直报它们。
#:   ⚠ 用**集合**而不是单字符串 —— 第二个公共库加进来时，
#:   只改一个字符串就会漏掉 ⇒ 又变成"同一件事两处实现"。
# [EN] **Shared utilities**, not assertion sets => neither run nor enter the group table.
# [EN]   · `verify_ui_common` -- measurement utility shared by the GUI criteria.
# [EN]   · `verify_exit` -- **the single exit-code outlet** (`finish()` / `failed_checks()`), used by
# [EN]     criteria to turn "red" into "non-zero exit code".
# [EN] ⚠ Both of these are **libraries** and really do exist on disk as `verify_*.py`, so the
# [EN] cross-check must exclude them -- otherwise "on disk but not registered in any group" keeps
# [EN] reporting them.
# [EN]   ⚠ A **set**, not a single string -- when the second utility is added, changing only one
# [EN]   string would miss it => "the same thing implemented in two places" again.
HELPERS = {'verify_ui_common', 'verify_exit'}

# ══════════════════════════════════════════════════════════════════════
#  分组表（**白名单**：新脚本必须登记，否则报错退出）
# [EN] Group table (**whitelist**: new scripts must be registered, otherwise error and exit)
# ══════════════════════════════════════════════════════════════════════
# 分组只影响**调度**（谁和谁可以同时跑），不影响任何判据本身。
# 一支脚本放错组最多让套件变慢或变脆，不会让错误的东西变绿 ——
# 但"变脆"会浪费下一次排查，所以还是放对。
# [EN] Groups only affect **scheduling** (who can run concurrently with whom), not any criterion
# [EN] itself.
# [EN] A script placed in the wrong group at most makes the suite slower or more fragile, it will not
# [EN] make wrong things turn green ——
# [EN] but "fragile" wastes the next investigation, so still place it correctly.

LOGIC: list[str] = [
    # ★ 2026-10-18 审计：这两支登记在 GUI 组，但**既不开窗也不起 GUI 进程**
    #   （纯静态/文件操作）⇒ 白占真机名额，排进串行的 GUI 组白等。
    # [EN] ★ 2026-10-18 audit: registered under GUI but **neither opens a window nor starts a
    # [EN] GUI process** (pure static / file work) => wasted a serial GUI slot.
    'verify_booklab_sources',
    'verify_borrowings',
    'verify_background', 'verify_backstage', 'verify_branch', 'verify_compliance',
    'verify_config_sweep', 'verify_context', 'verify_craft', 'verify_dispatch',
    'verify_film_style', 'verify_generic_project', 'verify_hooks',
    # ★ 2026-10-21：群演挂靠主线（R62/R63）。纯状态 + 打桩 ask，不起窗口、毫秒级。
    # [EN] ★ 2026-10-21: extras anchored to the main line (R62/R63). Pure state + stubbed ask,
    # [EN] no window, millisecond-level.
    'verify_extras_anchor',
    'verify_installer', 'verify_llm_truncation', 'verify_mcp_skills',
    # == 反例法的**锚点自检**（2026-10-19 第十轮）：静态核对 597 条可摘出的锚点
    #   命中没有、基线只许减、产品源码里有没有残留变异标记。纯 AST + 读文件，
    #   不起窗口、毫秒级 => LOGIC 组。
    #   ! 它同时是**全量回归自己的门禁**：它的 E 组判
    #     "`run_all_verifications` 里那份同类检测还在"，两份必须都在。
    # [EN] == The counterexample method's **anchor self-check** (2026-10-19, round 10):
    # [EN] statically checks the 597 extractable anchors, the baseline may only shrink,
    # [EN] and whether product source still carries mutation markers. Pure AST + file reads,
    # [EN] no window, millisecond-level => LOGIC group.
    # [EN] ! It is also the full regression's own gate: its group E checks that the
    # [EN]   sibling check inside `run_all_verifications` still exists; both must be there.
    'verify_mutation_anchors',
    'verify_progress_eval', 'verify_run_pacing', 'verify_samples',
    # ★ 2026-10-24/25：整理稿这条路的三件事（用户两条诉求的同一条线）。
    #   · `verify_day_novel_stop`：段循环问不问停止、停下交不交稿、段进度进不进栈。
    #     纯打桩 `ask`，**不起窗口** ⇒ LOGIC。
    #   · `verify_style_rounds`：Reflexion 只对实病多跑轮（文风类只改第一轮）。
    #     假步骤 + 假 Score，零 LLM、毫秒级 ⇒ LOGIC。
    #   ⚠ 前两支当初**漏登记了**，正是"新脚本必须显式登记"这条最容易踩的地方：
    #     漏了不是"少跑一支"，是整轮回归直接报"磁盘上有、但没登记分组"而退出。
    # [EN] ★ 2026-10-24/25: three things on the organizer path (one thread of two user requests).
    # [EN] `verify_day_novel_stop` stubs `ask` and opens no window => LOGIC. `verify_style_rounds`
    # [EN] uses fake steps and fake scores, zero LLM, millisecond-level => LOGIC.
    # [EN] ⚠ These were **left unregistered** at first -- exactly the trap of "new scripts must be
    # [EN] registered explicitly": missing one does not mean "one fewer script runs", it makes the
    # [EN] whole regression exit with "on disk but not in any group".
    'verify_day_novel_stop',
    'verify_style_rounds',
    # ★★ 2026-10-27：章节标题识别 —— 全项目**唯一**那份实现（`util/chapters.py`）。
    #   为什么单列一支：这一版修的真 bug 是"正文里单独成行的一句台词（`第二回正了。`）
    #   被当成章节标题" ⇒ 章节边界整体错位 ⇒ **前情提要按错的章节对齐**。
    #   而 `util/chapters.py` 是本轮**新抽**的模块（原先有三份实现，各写各的）。
    #   纯逻辑（纯正则 + 纯函数）、零 LLM、零网络、不起窗口、毫秒级 ⇒ LOGIC。
    #   ⚠ 它的反例法 `developers/mutate_chapter_split.py`（10 处变异）由
    #     `verify_mutation_anchors.py` 自动扫到（`mutate_*.py` 通配），不用单独登记。
    # [EN] ★★ 2026-10-27: chapter-heading recognition -- the **single** implementation for the whole
    # [EN] project (`util/chapters.py`).
    # [EN] Why a separate script: the real bug fixed here was "a standalone line of prose
    # [EN] (`第二回正了。`) taken for a chapter heading" => every chapter boundary shifted => **the recap
    # [EN] aligned to the wrong chapters**.
    # [EN] And `util/chapters.py` is a module **extracted this round** (there used to be three
    # [EN] separate implementations, each written on its own).
    # [EN] Pure logic (regexes + functions), zero LLM, zero network, no window, millisecond-level
    # [EN] => LOGIC.
    # [EN] ⚠ Its counterexample script `developers/mutate_chapter_split.py` (10 mutations) is picked up
    # [EN] automatically by `verify_mutation_anchors.py` (the `mutate_*.py` glob); no separate
    # [EN] registration needed.
    'verify_chapter_split',
    # ★★ 2026-10-27：**风格控制**（`util/style_kit.py`）—— 那八个旋钮**不再是死的**。
    #   用户报「界面上的旋钮怎么调都不影响稿子」之后补的：
    #   旋钮读进 `WorldState` 之后**没有任何消费者**（只影响界面上那行摘要）。
    #   这一组判据钉住：每个旋钮**动了就发声**且两端不同、每一句**能数能查**、
    #   幽默的**六步链**与范例占位、三处**默认值不许漂**、三路**真的接进提示词**。
    #   ⚠ `util/style_kit.py` 的注释白纸黑字写着「判据 `verify_style_control.py`
    #     会核对这两处」—— 而那个脚本**当时并不存在**（典型的文档漂移）。
    #   纯逻辑（纯函数 + 假 world + AST/源码查），零 LLM、零网络、不起窗口 ⇒ LOGIC。
    # [EN] ★★ 2026-10-27: **style control** (`util/style_kit.py`) -- those eight knobs **are no
    # [EN] longer dead**.
    # [EN] Added after the user reported "turning the knobs doesn't change the prose": the knobs were
    # [EN] read into `WorldState` and then **nothing consumed them** (they only affected that summary
    # [EN] line in the UI).
    # [EN] This group pins: every knob **speaks when moved** and differs at both ends, every sentence
    # [EN] is countable, the humor **six-step chain** and its bracketed examples, the three **defaults
    # [EN] must not drift**, and the three prompt paths **really receive it**.
    # [EN] ⚠ `util/style_kit.py`'s comment says "criterion `verify_style_control.py` checks these two"
    # [EN] -- and that script **did not exist** (a textbook documentation drift).
    # [EN] Pure logic (pure functions + a fake world + source inspection), zero LLM, zero network, no
    # [EN] window => LOGIC.
    'verify_style_control',
    # ★ 2026-10-25：「某个模型服务没钱了」这条通道 —— 纯逻辑（HTTP 替身 + 假主循环），
    #   零网络、零花费、不起窗口 ⇒ LOGIC。
    # [EN] ★ 2026-10-25: the "a model provider ran out of money" channel -- pure logic (HTTP stand-in
    # [EN] + fake main loop), no network, no cost, no window => LOGIC.
    'verify_llm_credit',
    # ★★ 2026-10-25：**分组白名单自己先坏了**（不只是本轮新脚本）。
    #   用户说「继续」之后跑 `--groups` 才看见：磁盘上有 11 支、一支都没登记 ⇒
    #   整轮全量回归**一启动就报错退出**，也就是说它已经很久没真正跑完过。
    #   ⇒ 按"开不开窗口"重新归位（判据本身一条没动）：
    #     · 不开窗口、纯 AST/纯逻辑/纯打桩 ⇒ LOGIC
    #     · 真开 Flet 窗口或真起进程 ⇒ GUI
    #     · 要独占桌面或要计时 ⇒ ALONE
    # [EN] ★★ 2026-10-25: the **whitelist itself was broken**, not just this round's new scripts.
    # [EN] Running `--groups` showed 11 scripts on disk with no group at all => the whole regression
    # [EN] **exited with an error on startup**, i.e. it had not really completed in a long time.
    # [EN] Re-sorted by "does it open a window" (no criterion was touched):
    # [EN] no window / pure AST / pure stubs => LOGIC; real Flet window or real process => GUI;
    # [EN] needs the desktop exclusively or measures timing => ALONE.
    'verify_atelier',
    'verify_bench_parity',
    'verify_progress_split',
    # ★★★ 2026-10-26：**写作层按情节单元写**（详的写足、略的一句带过）。
    #   纯函数 + 打桩 `ask` 抓提示词 + 就地反例（把三处实现各改坏一次），
    #   零网络、零花费、不起窗口 ⇒ LOGIC。
    # [EN] ★★★ 2026-10-26: **writing by plot unit** (thick where it matters, one line where it
    # [EN] does not). Pure functions + a stubbed `ask` to capture the prompt + in-place
    # [EN] counterexamples; no network, no cost, no window => LOGIC.
    'verify_writer_units',
    # ★★★ 2026-10-26：**剧情总览**（右侧剧情面板的主入口：从上往下的流程图 + 跑马灯切推演）。
    #   纯函数 + 裸造 Flet 控件（不起窗口、不调模型）⇒ LOGIC。
    #   ⚠ 名字刻意**不叫** `verify_story_flow`：那个已被"中栏故事体"占着，
    #     同名不同事会让看全量结果的人以为流程图这条也被守住了。
    # [EN] ★★★ 2026-10-26: **story overview** (the Plot panel's main entry: a top-down flowchart
    # [EN] plus a carousel across runs). Pure functions and bare Flet controls (no window, no model)
    # [EN] => LOGIC. ⚠ Deliberately **not** named `verify_story_flow`, which belongs to the middle
    # [EN] column's prose rendering; one name for two things would make a green line look like the
    # [EN] chart is guarded too.
    'verify_plot_overview',
    # ★★★ 2026-10-26：**i18n 覆盖率**（`tools/i18n_check.py`）。
    #   它一直在磁盘上，但**从没被登记过**，默认还只查 `gui/app_flet.py` ⇒
    #   回收站面板整页七十多条没登记英文，工具查得出来、一次都没查过。
    #   纯 AST + 查表，毫秒级、不起窗口 ⇒ LOGIC。
    #   ⚠ 它跟 `verify_ui_english` 不是重复：那支量的是"**真的打开了**的界面"，
    #     这一支量的是"源码里**写了**的每一条" —— 没被打开过的窗口只有这一支守得住。
    # [EN] ★★★ 2026-10-26: **i18n coverage** (`tools/i18n_check.py`).
    # [EN] It has been on disk all along but was **never registered**, and it defaulted to checking
    # [EN] only `gui/app_flet.py` => the whole recycle-bin pane had 70-odd untranslated strings that
    # [EN] the tool could find and never once did.
    # [EN] Pure AST plus a dict lookup, millisecond-level, no window => LOGIC.
    # [EN] ⚠ Not a duplicate of `verify_ui_english`: that one measures the screens **actually
    # [EN] opened**, this one measures **every string written in the source** — a window nobody opens
    # [EN] is guarded only by this one.
    'verify_i18n_coverage',
    # ★★★ 2026-10-26：**地图锚定**（用户：「小地图和大地图 每次生成的感觉都有一些区别
    #   有办法在整个小说推演过程中维持相同场景地图的一致性吗」）。
    #   纯函数 + `RunLoop.__new__` 假 runfolder，零模型、零网络、不起窗口 ⇒ LOGIC。
    #   ⚠ 它刻意**走产品那条路**（`RunLoop._day_map_anchor`）：自己拼 API 的话，
    #     "先补后贴"这个顺序在产品里写反了也照样绿。
    # [EN] ★★★ 2026-10-26: **map anchoring** (the user: "the minimap and big map feel a bit
    # [EN] different every time; can we keep scene maps consistent across the whole simulation?").
    # [EN] Pure functions plus a fake runfolder via `RunLoop.__new__`; no model, no network, no
    # [EN] window => LOGIC. ⚠ It deliberately goes through **the product's own path**
    # [EN] (`RunLoop._day_map_anchor`): stitching the API by hand would stay green even if the
    # [EN] "fill then stamp" order were reversed in the product.
    'verify_map_anchor',
    # ★★★ 2026-10-26：**日界按拍预算 · 故事时间按跨度**（用户选的方案 A）。
    #   纯函数 + `RunLoop.__new__` 假 world，零网络、零花费、不起窗口 ⇒ LOGIC。
    #   ⚠ 它刻意**不真跑**：真跑一轮在 mock 下也要 4.5 秒/拍（外部创作服务 mock 管不到），
    #     而这一组要验的是判定函数，毫秒级就够 —— 真跑那半在 `verify_run_pacing` C2。
    # [EN] ★★★ 2026-10-26: **the day ends when the beat budget runs out; story time follows the
    # [EN] span** (the user's choice A). Pure functions plus a fake world via `RunLoop.__new__`; no
    # [EN] network, no cost, no window => LOGIC. ⚠ It deliberately does **not** really run: one real
    # [EN] round takes 4.5 s per beat even under mock (the external creation services ignore mock),
    # [EN] and what this group checks are decision functions -- milliseconds suffice. The real run
    # [EN] half lives in `verify_run_pacing` C2.
    'verify_beat_time',
    # ★★★ 2026-10-30：**详细程度档位 + 书斋「运行」覆盖全局**（用户点名）。
    #   纯本地：档位表 / 覆盖层 / `.nwsproj` 往返 / AST 接线 / 真控件联动（无窗口、
    #   零网络、零花费）⇒ LOGIC。
    # [EN] ★★★ 2026-10-30: **the detail-level ladder + Study · Run overriding the global**
    # [EN] (user request). Purely local: ladder table, override layer, `.nwsproj` round trip,
    # [EN] AST wiring, and real-widget linkage (no window, no network, no cost) => LOGIC.
    'verify_detail_level',
    'verify_reflexion',
    'verify_run_panel_hints',
    'verify_scene_maps',
    # ★ 2026-10-27：**删一本小说要连它名下的存档一起**（用户："前者是包含后者的"）。
    #   纯数据层（临时目录里真造书与存档，`store/trash` 的搬/恢复/永久删除），
    #   零网络、零花费、不起窗口 ⇒ LOGIC。
    # [EN] ★ 2026-10-27: **deleting a book must take its saves with it** (user: "the former
    # [EN] contains the latter"). Pure data layer (builds real books and runs in a temp dir, then
    # moves / restores / purges through `store/trash`); no network, no cost, no window => LOGIC.
    'verify_trash_cascade',
    'verify_length_plan',
    # ★ 2026-10-27：**设定提取窗口**装的是该装的东西。实测事故：36 个文件 94,118 字
    #   全量拼进 12000 字窗口、掐头留尾之后，世界观 / 七张人物卡 / 伏笔 / 地点 **一份没剩**。
    #   纯本地（临时目录 + `ingest.scanner` 扫 + 拼窗口），不联网不花钱 ⇒ LOGIC。
    # [EN] ★ 2026-10-27: the **setting extraction window** holds what it should. Measured incident:
    # [EN] 36 files / 94,118 chars all concatenated into a 12,000-char window; after cutting head and
    # [EN] keeping tail, **not one** of the worldview / seven character cards / foreshadowing /
    # [EN] locations survived.
    # [EN] Purely local (temp dir + `ingest.scanner` + window assembly), no network, no cost => LOGIC.
    'verify_extract_window',
    # ★★★ 2026-10-27：**站表链**（大纲 → 切片 → 建节点 → 拆站 → 装配 → 推演）。
    #   实测事故：作者写 8 站 32 章，程序落盘 9 站 35 章，第 8 站的判据被换成别的、
    #   **结局三选一整个丢失**。纯本地（样例大纲文本 + 真跑解析层与装配层），
    #   零网络、零花费、不起窗口 ⇒ LOGIC。
    #   ⚠ H 组顺带守着"**抽出模块级函数不许把类方法吞掉**"（本轮真事故）。
    # [EN] ★★★ 2026-10-27: the **station-table chain** (outline -> slice -> build nodes -> split ->
    # [EN] assembly -> run). Measured incident: the author wrote 8 stations / 32 chapters, the program
    # [EN] persisted 9 / 35, station 8's criterion was replaced, and **the three ending options
    # [EN] vanished entirely**. Purely local (sample outline text + really running the parsing and
    # [EN] assembly layers); no network, no cost, no window => LOGIC.
    # [EN] ⚠ Group H also guards "**extracting a module-level function must not swallow class
    # [EN] methods**" (this round's real incident).
    'verify_station_plan',
    # ★★★ 2026-10-27：**提取条数配额**（设定集写了 30 条细节 / 15 条关系，
    #   开卷后只剩 8 / 8，而且"客人讲究"与"忌讳"两整类一条都没有）。
    #   纯本地（读提示词文本 + `extractor._validate` 打桩喂数），零网络零花费 ⇒ LOGIC。
    # [EN] ★★★ 2026-10-27: the **extraction item quotas** (the settings wrote 30 details / 15
    # [EN] relations; only 8 / 8 survived ingestion, and of the "guest customs" and "taboos"
    # [EN] categories **not one** item did). Purely local (reads the prompt text + feeds stubs to
    # [EN] `extractor._validate`); no network, no cost => LOGIC.
    'verify_extract_quota',
    # ★★★ 2026-10-27：**「必出日」这条链**（细节层写了「第 N 章必须有它」）。
    #   实测事故：中文数字解析**只认单个字**（「三」认得、「十五」不认），而模型
    #   与作者写的偏偏常是「第十五章」⇒ 那一栏**静默丢掉**，表现成"程序照跑、
    #   就是没出"。这一支钉住四段：解析认得出 → 进索引 → 绕过场合/在场两道闸 →
    #   挤不掉（排最前），反过来非必出日**不许**出现。
    #   纯函数 + 假 setting 字典，零网络、零花费、不起窗口 ⇒ LOGIC。
    #   ⚠ 2026-10-28 由一次性探针 `_probe_must_on.py` **转正**：它测的正是用户报的
    #     B 项（"细节层指定章次必出"）那条完整链路，删了就没了。
    #   ⚠ 夹具名字**一律中性**（「书一 / 店堂」）：判据夹具里不许出现某一部真实
    #     作品的专名（与 `verify_generic_project` A 组同一条纪律）。
    # [EN] ★★★ 2026-10-27: **the "must appear" chain** (the detail layer's "chapter N must have
    # [EN] this"). Measured incident: the Chinese-numeral parser accepted **single characters only**
    # [EN] ("三" yes, "十五" no) while models and authors typically write "第十五章" => that column
    # [EN] was **silently dropped**, showing up as "the program runs fine, it just never appears".
    # [EN] This one pins four stages: parser recognizes -> enters the index -> bypasses the
    # [EN] scene/presence gates -> cannot be squeezed out (sorts first); conversely, on a non-must
    # [EN] day it **must not** appear. Pure functions plus a fake settings dict; no network, no cost,
    # [EN] no window => LOGIC.
    # [EN] ⚠ Promoted on 2026-10-28 from the throwaway probe `_probe_must_on.py`: it tests exactly
    # [EN] item B the user reported (the detail layer's specified-chapter must appear), and deleting
    # [EN] it would lose that coverage.
    # [EN] ⚠ Fixture names are **all neutral** ("书一 / 店堂"): no proper noun of one real work may
    # [EN] appear inside a criterion's fixtures (same discipline as `verify_generic_project` group A).
    'verify_must_on',
    # ★★ 2026-10-28：运行界面这四块（用户一次性提的）。
    #   ① 摄取输入框：**回车 = 换行**、**Ctrl+Enter = 发送**，提示排在发送/强制停止**下面**；
    #   ② 「AI 往来」对话框：**分页**（默认 50/页、可改），打开时落在**最后一页且最后一条可见**；
    #   ③ 左下角系统面板：去掉「模型」行、去掉「已关闭 · 向量检索」、
    #      加上「MOCK 模式」、加上三座外部创作服务的状态（`*` 在跑 / `-` 没跑）。
    #   纯逻辑 + **真跑产品自己的函数**（分页算式、`_on_keyboard` 的 Ctrl+Enter 分支、
    #   `_apply_svc_lamps` 的灯语义），源码位置关系用 **AST** 看（**不用 grep** ——
    #   源码注释里就写着被删掉的那行代码，grep 会把注释当代码）。
    #   零网络、零花费、不起窗口 ⇒ LOGIC。
    # [EN] ★★ 2026-10-28: the four run-screen pieces (all requested by the user at once).
    # [EN] (1) The ingestion input: **Enter = newline**, **Ctrl+Enter sends**, the hint below the
    # [EN] Send / Force-stop buttons; (2) the "AI exchange" dialog: **pagination** (50/page by default,
    # [EN] adjustable), opening lands on the **last page with the last item visible**; (3) the
    # [EN] bottom-left System panel: the "model" row gone, "turned off · vector retrieval" gone, an
    # [EN] "MOCK mode" row added, and the three external creation services' status added
    # [EN] (`*` running / `-` not).
    # [EN] Pure logic, **really running the product's own functions** (the pagination arithmetic, the
    # [EN] Ctrl+Enter branch of `_on_keyboard`, the lamps' semantics in `_apply_svc_lamps`), and AST
    # [EN] for the source positions (**not grep** -- the source comment literally contains the deleted
    # [EN] line, and grep would read the comment as code).
    # [EN] No network, no cost, no window => LOGIC.
    'verify_ui_probe_paging',
    # ★★★ `verify_svc_users`（2026-10-28 新增）：**多实例共享一组创作服务时谁收尸**。
    #   起因：三个服务都绑固定端口 ⇒ 第二个实例只会收到「已经在运行，不重复启动」
    #   ⇒ **全程只有一组服务**。于是"主窗口退出 ⇒ 服务跟着退出"在多实例下必须是
    #   **最后一个关的人收尸**；而原来那套（`launcher.pid` 比"是不是我"）只防住了
    #   **先关的**那个，没防住**后关的**那个 —— 后者才是把正在用的服务掐掉的那一次。
    #   ⚠ 这个病**不会自己冒出来**（单开一个窗口一切正常）⇒ 只有这条判据在测它。
    #   ⚠ 它**不真起服务、不真停服务**（三家桥全部打桩），也不开窗口 ⇒ LOGIC。
    # [EN] ★★★ `verify_svc_users` (added 2026-10-28): **who reaps the services when
    # [EN] several instances share one set**. All three bind a fixed port => a second
    # [EN] instance only gets "already running" => **only one set ever runs**. So
    # [EN] "window closes => services exit" must become **whoever closes last reaps**,
    # [EN] and the old `launcher.pid` check guarded **the first to close** but not
    # [EN] **the last to close** -- the latter cuts off the service still in use.
    # [EN] ⚠ The illness never surfaces on its own (one window looks fine) => only
    # [EN] this criterion tests it. No real start/stop (bridges stubbed), no window.
    'verify_svc_users',
    # ★★★ 2026-10-28：**说话指纹**（作者转来的一份退稿复盘：编辑只圈了三段对话，
    #   批注「你这两个人说话，像在互相念说明书」；他的判法=**遮住人名，听不出谁在说
    #   就是机器写的**）。三条链一起守：设定集字段 → 人格状态 → 开口前那一段；
    #   副词盖章式对话标签的检测/配额/清理（**台词一个字都不许被吃**）；
    #   演员与写作两层的三条纪律（能不说就不说 / 遮名 / 别答完整）。
    #   ⚠ 它的 D 组（对照某本书的设定集）要 `--project` 才跑，回归里跑的是 A/B/C ——
    #     判据夹具里**不许出现真实作品专名**（`verify_generic_project` 会抓）。
    #   ⚠ 真跑产品代码 + 纯正则检测器，零模型、零网络、不起窗口 ⇒ LOGIC。
    # [EN] ★★★ `verify_speech_fp` (added 2026-10-28): the **speech fingerprint** chain.
    # [EN] An editor circled three passages: "your two characters talk like they are reading
    # [EN] spec sheets to each other"; his test -- **cover the names**.
    # [EN] Three links guarded together: card field -> persona state -> the block right before
    # [EN] speaking; the adverb-stamped tag detector/quota/cleanup (**not one character of
    # [EN] dialogue may be eaten**); and the three disciplines in the actor and writing prompts.
    # [EN] ⚠ Its D group needs `--project`; the regression runs A/B/C because fixtures must not
    # [EN] contain a real work's proper nouns (`verify_generic_project` checks that).
    'verify_speech_fp',
    # ⚠ `verify_exit_codes` **不在这里** —— 它会把每支纯逻辑判据**改坏一处再真跑一遍**
    #   ⇒ 既慢（几分钟）、又改的是**判据自己的源码**（别的脚本正在读就串味）
    #   ⇒ 已挪进 `ALONE`。
    # [EN] ⚠ `verify_exit_codes` **is not here** -- it breaks one assertion per pure-logic criterion
    # [EN] and re-runs it => both slow (minutes) and it edits **criterion sources themselves**
    # [EN] (cross-contaminates whatever else is reading them) => already moved into `ALONE`.
    # ⚠ `verify_sim_depth` **不在这里** —— 它测的是**耗时**（并发 vs 串行
    #   省下多少），而耗时在并行回归里根本不可测，已挪进 `ALONE`。
    # [EN] ⚠ `verify_sim_depth` **is not here** —— it measures **time cost** (concurrent vs serial
    # [EN] how much is saved), and time cost is simply unmeasurable in parallel regression, already moved
    # [EN] into `ALONE`.
    'verify_script_bilingual', 'verify_sim_prompt',
    'verify_world_rules',
    # ★ 开始菜单的**彩色图标素材**（2026-10-10）：只读磁盘上的 16 张 PNG + 源码里
    #   那八个 `img:` 槽位对不对得上，**不起窗口** ⇒ LOGIC 组。
    #   渲染那半在 `verify_resume_menu`（GUI 组）。
    # [EN] ★ Start menu's **colorful icon assets** (2026-10-10): only reads the 16 PNGs on disk + whether
    # [EN] the
    # [EN] eight `img:` slots in the source match up, **does not open a window** ⇒ LOGIC group.
    # [EN] The rendering half is in `verify_resume_menu` (GUI group).
    'verify_menu_icons',
    # ★ 配色键（2026-10-10）：AST 查 `C[...]`/`INKC[...]` 的字面量键在不在。
    #   用户报的「选示例失败: 'ink'」就是 `C['ink']`（`ink` 只在 `INKC` 里）。
    #   纯静态、毫秒级、不起窗口 ⇒ LOGIC 组。
    # [EN] ★ Color keys (2026-10-10): AST checks whether the literal keys of `C[...]`/`INKC[...]` exist.
    # [EN] The user-reported "select example failed: 'ink'" is `C['ink']` (`ink` only exists in `INKC`).
    # [EN] Purely static, millisecond-level, does not open a window ⇒ LOGIC group.
    'verify_color_keys',
    # ★★ 四平台发布包（2026-10-11，用户问「start/setup/uninstall 为何没有其他平台的
    #    版本」）：A 组纯逻辑（魔数识别、三张平台表自洽、linux 运行时全覆盖）；
    #    B 组**真打四个包**再逐个读魔数核对（不启 GUI）⇒ LOGIC 组。
    #    ⚠ 它每跑一遍要往临时目录拷近 1GB 再删掉（四个包），所以是 LOGIC 组里
    #      最重的一支；`--a-only` 可以只跑逻辑那半（给反例法用）。
    # [EN] ★★ Four-platform release packages (2026-10-11, the user asked "why don't
    # [EN] start/setup/uninstall have versions for other platforms"): group A is pure logic (magic
    # [EN] identification, the three platform tables being self-consistent, full linux runtime
    # [EN] coverage); group B **really builds four packages** and then reads each one's magic to check
    # [EN] (no GUI) ⇒ LOGIC group.
    # [EN] ⚠ Each run copies nearly 1GB into a temp directory and deletes it again (four packages), so
    # [EN] this is the heaviest item in the LOGIC group; `--a-only` runs just the logic half (used by
    # [EN] the reverse experiments).
    'verify_release_platforms',
    # ★★ 发布**脚本**（打包 / 推送）的四条不变量（2026-11-06，用户：「检查下生成脚本和
    #    发布脚本 … 注意不要带任何API Key，gitee默认用中文版README Github默认用英文版」）。
    #    A 组读 `publish/publish.ps1` 源码：双工作区 / 双 README / 排除清单 / **带路径的排除项
    #    必须完整路径**（相对写法被 robocopy 静默忽略，286MB 截图里带真 Key 就是这么漏的）/
    #    真值全文搜 / 凭据不写 .git/config / 退出码看 want* / auto_init=false。
    #    B 组真跑 `publish/readme_variant.py`（门面是谁、语言条指哪儿、坏链会红）。
    #    C 组真跑一次 `-DryRun`（不联网、不碰 git、不写文件）。
    #    ⚠ 反例法：`developers/mutate_publish_scripts.py`（8 刀，8/8 能红）。
    # [EN] ★★ The publish **scripts**' four invariants. Group A reads `publish/publish.ps1`
    # [EN] (two workspaces, two READMEs, exclude list, **path-style excludes must be absolute** --
    # [EN] relative ones are silently ignored by robocopy, which is how a real API key rode along
    # [EN] inside 286 MB of screenshots; real-value full-text search; no credentials in
    # [EN] `.git/config`; exit code looks at want*; auto_init=false). Group B really runs
    # [EN] `readme_variant.py`; group C really runs `-DryRun` (offline, no git, no writes).
    # [EN] ⚠ Mutation test: `developers/mutate_publish_scripts.py` (7 knives, 7/7 red).
    'verify_publish_scripts',
    # ★★ 用量对话框的**栏宽 / 默认最大化 / 第 4 栏横向滚动**（2026-10-11，用户：
    #    「第 1 2 3 列适当收窄 第 4 列放大 尽量保证显示所有信息 如果不行 第4列加横向滚动条
    #     整体LLM窗口默认最大化」）。
    #    A 组要**量像素**（给四栏边框涂标记色、逐栏取 x 范围）⇒ 必须真开窗口；
    #    B 组还要**把窗口改小再开一次**（放不下的那个分支）⇒ 更得是真机。
    #    ⚠ 它会**改动窗口尺寸**（1060×720），跑完再还原成最大化。
    # [EN] ★★ The usage dialog's **column widths / maximized by default / column 4's horizontal
    # [EN] scrolling** (2026-10-11, user: "narrow columns 1 2 3, widen column 4, try to show all the
    # [EN] information, and if that doesn't work add a horizontal scrollbar to column 4; make the whole
    # [EN] LLM window maximized by default").
    # [EN] Group A must **measure pixels** (paint the four borders with marker colors, take each one's x
    # [EN] range) ⇒ a real window is required; group B also has to **shrink the window and reopen**
    # [EN] (the doesn't-fit branch) ⇒ even more so.
    # [EN] ⚠ It **changes the window size** (1060x720) and restores it to maximized at the end.
    # ★ Flet API（2026-10-10）：把源码里每条 `ft.x.y` 拿去真的 `getattr` 走一遍。
    #   抓的是"不存在的 Flet 属性"（`ft.padding.all` / `ft.border.all`）——
    #   「用量统计」就是因为它们**一次都没打开成功过**。纯静态 ⇒ LOGIC 组。
    # [EN] ★ Flet API (2026-10-10): take every `ft.x.y` in the source and actually run `getattr` over it.
    # [EN] What is caught is "nonexistent Flet attributes" (`ft.padding.all` / `ft.border.all`) ——
    # [EN] "usage statistics" is because they **never opened successfully even once**. Purely static ⇒
    # [EN] LOGIC group.
    'verify_ft_api',
    'verify_day_plan',
    # ★ 场次编排（2026-10-11，作者报"东一句一句、场景乱跳"之后补的）：
    #   纯逻辑 A 组 + 一次真调 `RunLoop._maybe_close_beat` 的 B 组，
    #   都不起窗口 ⇒ LOGIC 组。
    # [EN] ★ Stage scheduling (added 2026-10-11 after the author reported "all over the place, scenes
    # [EN] jumping around"): pure-logic group A + group B that really calls
    # [EN] `RunLoop._maybe_close_beat`, neither opens a window ⇒ LOGIC group.
    'verify_scene_beat',
    # 设定分层 + 编剧室（2026-10-07）：纯逻辑 + 一次 MOCK 端到端，不起窗口
    # [EN] Setting layering + writers' room (2026-10-07): pure logic + one MOCK end-to-end, does not open a
    # [EN] window
    'verify_setting_layers',
    # ★ 总体协调引擎（2026-10-15）：运行窗口底部 AI 对话输入框 = 协调引擎入口。
    #   纯逻辑（Coordinator 行为判 + 强制关键词降级）＋ AST 查 UI 接线 + config 默认显示，
    #   不起窗口 ⇒ LOGIC 组。
    # [EN] ★ Overall Coordinator (2026-10-15): the run window's bottom AI box = Coordinator entry.
    # [EN] Pure logic (Coordinator behavior + forced keyword fallback) + AST UI-wiring + config default,
    # [EN] no window ⇒ LOGIC group.
    'verify_coordinator',
    # ★ 岔路口面板（2026-10-07）：真机段（要开窗口、量像素）→ 归 **GUI** 组；
    #   逻辑段（自定义走向 / 互斥 / 倒计时默认值）随它一起跑，`--logic-only` 也支持。
    # 演示模式完整性（2026-10-07）：产品用到的每个 purpose 都要有假回复
    # [EN] ★ Fork-road panel (2026-10-07): real-machine segment (needs to open a window, measure pixels) →
    # [EN] belongs to **GUI** group;
    # [EN] the logic segment (custom direction / mutual exclusion / countdown default value) runs along
    # [EN] with it, `--logic-only` also supported.
    # [EN] Demo mode completeness (2026-10-07): every purpose used by the product must have a fake reply
    'verify_mock',
    # 《设定写作指导.md》与代码的一致性（2026-10-07）：防文档漂移
    # [EN] Consistency between "Setting Writing Guide.md" and the code (2026-10-07): guards against
    # [EN] documentation drift
    'verify_setting_guide',
    # 对话衔接（2026-10-07）：人物听得见别人说的话、被点名的先答
    # [EN] Dialogue coherence (2026-10-07): characters can hear what others say, and the addressed one
    # [EN] answers first
    'verify_dialogue_thread',
    # 重复台词（2026-10-07）：说了一样的话 → 先问是不是非说不可
    # [EN] Repeated lines (2026-10-07): said the same thing → first ask whether it must be said
    'verify_dialogue_repeat',
    # 测试夹具指向 samples/（2026-10-07 规矩）：夹具里的人名/地名/台词都要有出处
    # [EN] Test fixtures point to samples/ (2026-10-07 rule): names/places/lines in fixtures must have a
    # [EN] source
    'verify_sample_fixture',
    # 真模型下"正文被思考吃光"的两道防线（2026-10-07）：结论型用途关思考 + 自愈
    # [EN] Two lines of defense for "main text devoured by thinking" under real models (2026-10-07):
    # [EN] disable thinking for conclusion-type purposes + self-heal
    'verify_llm_budget',
    # 去 AI 库与全链路审计（2026-10-07）
    # [EN] De-AI library and full-chain audit (2026-10-07)
    'verify_deai',
    # 剧组扩充 · 今日简介 · 今日总结 · 盯戏回档 · 播报分级（2026-10-07）
    # [EN] Cast expansion · today's synopsis · today's summary · watch-play rollback · broadcast tiering
    # [EN] (2026-10-07)
    'verify_studio_v2',
    # ★ 剧组流程审计（2026-10-07 第二轮）：接线（谁说自己在干活却从没出工）、
    #   类型卡别名、工艺按职位点名、造型/声音的下游、一场一转变、导演大纲。
    #   纯逻辑（跑一天 MOCK，不起窗口）。
    # [EN] ★ Cast process audit (2026-10-07 second round): wiring (who claims to be working but never
    # [EN] showed up),
    # [EN] type card aliases, craft called out by position, downstream of styling/voice, one transition per
    # [EN] scene, director outline.
    # [EN] Pure logic (run one day of MOCK, does not open a window).
    'verify_crew_flow',
    # ★ 选角与项目档（2026-10-07 第四轮）：演员类型库（每型变奏/忌讳、默认型
    #   存在、匹配表无死词）· 两层提示词与仲裁规则 · 同型分流 ·
    #   项目档按书生成并压在默认手艺之后 · **行为级**：抓真发出去的 messages
    #   看两层与"话该怎么说"是否真到了演员面前。
    # [EN] ★ Casting and project archives (2026-10-07 fourth round): actor type library (variations/taboos
    # [EN] per type, default type
    # [EN] exists, matching table has no dead words) · two-layer prompts and arbitration rules · same-type
    # [EN] triage ·
    # [EN] project archives generated per book and pressed after the default craft · **behavior-level**:
    # [EN] capture the messages actually sent
    # [EN] to see whether the two layers and "how the words should be said" actually reach the actor.
    'verify_casting',
    # ★ 认知模式（2026-10-07 第七轮）：思维链 / 反思链 / 组合 ——
    #   模式表（每个 Agent 用哪种、NONE 说得出为什么）· 骨架挂的手艺必须是
    #   该职位读得到的 · **行为级**：抓真发出去的 prompt 看骨架与思考字段 ·
    #   台词自省真改写 / 正常台词不多花调用 · 关掉开关**逐字退回** · 反假按钮。
    #   纯逻辑（打桩 llm.chat / ask，不起窗口）。
    # [EN] ★ Cognitive modes (2026-10-07 seventh round): chain-of-thought / reflection chain / combination
    # [EN] ——
    # [EN] mode table (which one each Agent uses, NONE can state why) · the craft hung on the skeleton must
    # [EN] be
    # [EN] readable by that position · **behavior-level**: capture the actually sent prompt to see the
    # [EN] skeleton and thinking fields ·
    # [EN] line self-reflection really rewrites / normal lines do not spend extra calls · turning the
    # [EN] switch off **reverts verbatim** · anti-fake button.
    # [EN] Pure logic (stub llm.chat / ask, does not open a window).
    'verify_cognition',
    # ★ 提示词前缀稳定性（2026-10-07 第八轮）：前缀缓存能不能命中全看这一条。
    #   A 拆分等价（拆前缀不许改口径）· B 稳定段真的稳定（换场景/换在场/走一天）·
    #   C **行为级**：拦 `llm.context.pack`，量产品**自己声明**的固定层逐拍是否逐字相同 ·
    #   D 契约：裁到最低预算后规则/世界观/人格仍在（§2.4「固定前缀永不裁」）。
    #   纯逻辑（打桩 chat + pack，不起窗口）。
    # [EN] ★ Prompt prefix stability (2026-10-07 eighth round): whether the prefix cache can hit depends
    # [EN] entirely on this.
    # [EN] A split equivalence (splitting the prefix must not change the wording) · B stable segment really
    # [EN] stable (switch scene/switch present/run one day) ·
    # [EN] C **behavior-level**: intercept `llm.context.pack`, measure whether the fixed layer
    # [EN] **self-declared** by the product is verbatim identical beat by beat ·
    # [EN] D contract: after trimming to the lowest budget, rules/worldview/persona still remain (§2.4
    # [EN] "fixed prefix is never trimmed").
    # [EN] Pure logic (stub chat + pack, does not open a window).
    'verify_prefix_cache',
    # ★ 开演前的卡片 + 停止按钮（2026-10-07 第八轮）：**第一天必须开场**
    #   （`game_day != _current_day` 两者初值都是 1 → 第一天整块开场从不执行，
    #   用户报的"今日简介/场景介绍卡片都没了"就是它）· 今日任务卡 ·
    #   停止的即时反馈与提前收手 · 收尾不重复。纯逻辑（真跑 run()，不起窗口）。
    # [EN] ★ Pre-show card + stop button (2026-10-07 eighth round): **the first day must open the show**
    # [EN] (`game_day != _current_day` both initial values are 1 → the whole first-day opening block never
    # [EN] executes,
    # [EN] the user-reported "today's synopsis/scene intro cards are all gone" is it) · today's task card ·
    # [EN] immediate feedback of stop and stopping early · ending does not repeat. Pure logic (really run
    # [EN] run(), does not open a window).
    'verify_day_start',
    # ★ 空正文自愈（2026-10-07 第十四轮）：用户「⚠ 正文为空（撞到 max_tokens=2400…）
    #   **这一直在报错** 这个要怎么修复」。真日志：自愈触发 101 次、失败 0 次 ——
    #   **每次都救回来了**，但界面在"第一发失败"时就报红字，而"救回来了"一个字不说
    #   （还白烧了 101 次调用）。判据：自愈条件（只有该救才救）· **行为级**（把
    #   `_real_call` 换成假实现真调 `llm.chat()`：救回 / 标 `auto_retry` / 学会 /
    #   第二发只发一发）· 界面不许把注定要被重试的那一发当错误报 · 救回要说出来。
    #   纯逻辑（不联网、不起窗口）。
    # [EN] ★ Empty main text self-heal (2026-10-07 fourteenth round): user "⚠ main text empty (hit
    # [EN] max_tokens=2400…)
    # [EN] **this keeps erroring** how to fix this". Real logs: self-heal triggered 101 times, failed 0
    # [EN] times ——
    # [EN] **every time it was saved**, but the UI shows red text at "first shot failed", while "saved"
    # [EN] says not a word
    # [EN] (and 101 calls were burned for nothing). Criteria: self-heal condition (only save when it should
    # [EN] be saved) · **behavior-level** (replace
    # [EN] `_real_call` with a fake implementation and really call `llm.chat()`: saved / marked
    # [EN] `auto_retry` / learned /
    # [EN] second shot sends only one shot) · the UI must not report the shot doomed to be retried as an
    # [EN] error · saving must be spoken.
    # [EN] Pure logic (no network, does not open a window).
    'verify_empty_body_retry',
    # ★★★ **思考模式总开关**（2026-10-18，`LLM_THINKING_MODE`）：
    #   新版 `deepseek-flash` 默认输出思考内容，而思考按输出计费、还和正文抢
    #   同一份 `max_tokens`（实测一句"写 300 字"能想掉 900 额度、正文 0 字）。
    #   归 LOGIC：A/B 是纯逻辑，C 用**假 client 打点真请求**看 `thinking` 有没有
    #   进 body（不发网络）。E 组（界面真的画出来）要开窗口，**只在完整跑时执行** ——
    #   反例法改 GUI 时会自动跑完整判据。
    # [EN] ★★★ **Thinking-mode master switch** (2026-10-18, `LLM_THINKING_MODE`): the new
    # [EN] `deepseek-flash` emits thinking by default, billed as output and competing with the body
    # [EN] for the same `max_tokens` (measured: one "write 300 characters" prompt can spend 900 tokens
    # [EN] thinking and return **zero** characters). LOGIC group: A/B are pure logic, C stubs the client
    # [EN] and inspects the real request body (no network). Group E needs a window and only runs in a
    # [EN] full pass; the mutation script asks for the full run when it touches the GUI.
    # ★★★ **基准工具自检**（2026-10-18）：2026-10-18 两次把校验代码插进
    #   `find_case()`（作用域里没有 `issues`），而 `check` 从不调那个函数 ⇒
    #   **校验从来没执行、`check` 一直报绿**。这一支专门守"校验器会不会红"。
    # [EN] ★★★ **Benchmark self-check** (2026-10-18): twice that day validation code was inserted
    # [EN] into `find_case()` (no `issues` in that scope) and `check` never calls it, so **the checks
    # [EN] never ran and `check` stayed falsely green**. This entry guards "does the validator go red".
    'verify_bench_tool',
    # ★★★ **三项优化**（2026-10-18）：创意增量（编剧岔口）/ 人物成形（内心与称谓）/
    #   戏能立住（验算按硬伤 vs 建议分级）。第 3 组用**假 ask 打点真函数**判行为。
    # [EN] ★★★ **Three optimisations** (2026-10-18): novelty (the screenplay's fork), character
    # [EN] formation (inner voice and forms of address), and scene viability (verdict severity split).
    # [EN] Group 3 stubs `ask` and calls the real function, judging behaviour.
    'verify_story_quality_ops',
    # ★ **起笔 · 续跑起点**（2026-10-08）：用户原话
    #   「运行窗口**起笔** 加一个逻辑 点击之后如果检查发现一天的时间还没结束
    #    （之前在一天没结束的时候点的停止）则提示从某一天某个时间继续，
    #     如果一天已经结束了，则开启新一天」。
    #   全流程**无界面**（判据里没有真机段：它验的是"判得准、接得上、不丢稿子"，
    #   三件事都在纯逻辑层能证完），所以归**逻辑组**。
    # [EN] ★ **Start writing · resume starting point** (2026-10-08): user's original words
    # [EN] "Run window **start writing** add a logic: after clicking, if the check finds that one day's
    # [EN] time has not yet ended
    # [EN] (previously clicked stop while the day had not ended) then prompt to continue from a certain day
    # [EN] at a certain time,
    # [EN] if the day has already ended, then start a new day".
    # [EN] Whole flow **no UI** (criteria have no real-machine segment: it verifies "judges accurately,
    # [EN] connects seamlessly, does not lose drafts",
    # [EN] all three things can be proven at the pure logic layer), so belongs to **logic group**.
    'verify_start_point',
    # ★★★ 2026-10-31：**同一条时间线上不许有两个天数**（用户：「运行窗口左上角时间和
    #   对话窗口的时间对不上，左上角说是第4天但是运行窗口是第2天刚结束，正准备第三天」）。
    #   查出来两条线：左上角读 `world.game_day`（故事钟），幕头/落盘/停点读
    #   `loop._current_day`（写作天）；而续跑时写作天被写死成 1、停点 `day` 又被
    #   当成故事天去建时钟（时间倒退一天）。纯本地：起点接线 / 停点两栏 / 取数顺序 /
    #   建时钟 / `plan()` / AST 接线 / 反例，无窗口、零网络 ⇒ LOGIC。
    # [EN] ★★★ 2026-10-31: **one timeline must not carry two day numbers** (user: "the top-left
    # [EN] clock and the dialogue window disagree -- top-left says day 4 while the run window says
    # [EN] day 2 just ended, about to start day 3"). Two counters were found: the top-left reads
    # [EN] `world.game_day` (story clock), while the header / persisted files / stop point read
    # [EN] `loop._current_day` (writing day); and on resume the writing day was hard-coded to 1 while
    # [EN] the stop point's `day` was used to build the clock as if it were the story day (time moved
    # [EN] backwards a day). Purely local: start-day wiring, two stop-point fields, resolution order,
    # [EN] clock building, `plan()`, AST wiring, mutation -- no window, no network => LOGIC.
    'verify_day_consistency',
    # ★★★ **存档为空（或全删了）也必须能起笔**（2026-10-28）—— 用户原话：
    #   「一个小说 如果我开卷成功了 然后我又把所有存档都删除了，我关闭软件再进去
    #    就无法进行推理了。按道理第一次推演不应该跟存档有关，确切的说它就应该在
    #    存档为空的前提下可以开始才对」。
    #   真凶是两件事被写成一件：开始界面三颗按钮按**"这一次运行里有没有打开过书"**
    #   （`current_project is not None`）判，重启后恒为 `None` ⇒ 全灰、小字写着
    #   「先开卷导入小说」；`_on_new_round` 也是同一句早退。
    #   ⇒ 判据只该有一条：**盘上有没有书**（`start_menu_state` 纯函数），
    #     外加"记住上次打开的那本书并在启动时接回来"（`_restore_last_project`，
    #     必须排在 `show_start_screen()` 之前）与"没有当前书时当场给路"（`_need_project`）。
    #   A/B/D 全是纯逻辑（纯函数、临时目录里造真项目），C 是 AST 源码级 ⇒ **逻辑组**，
    #   不起窗口。⚠ 它会在 `%TEMP%` 下真建项目目录，**不碰** `Projects/` 与真实 `.ui_state`。
    # [EN] ★★★ **Starting must work with an empty (or fully deleted) save folder** (2026-10-28) --
    # [EN] the user's words: "opened a volume, deleted all saves, restarted, and could no longer
    # [EN] derive; the first derivation should not depend on saves". Two things had been coded as
    # [EN] one: the three start-screen buttons were gated on "was a book opened **this run**"
    # [EN] (`current_project is not None`), always None after a restart, and `_on_new_round` returned
    # [EN] early on the same condition. => The only criterion is **whether books exist on disk**
    # [EN] (`start_menu_state`, pure), plus "remember the last book and reconnect it at startup"
    # [EN] (`_restore_last_project`, before `show_start_screen()`) and "give a way out when no
    # [EN] current book" (`_need_project`). Groups A/B/D are pure logic (real projects in a temp dir),
    # [EN] C is AST-level => **logic group**, no window. ⚠ Creates real project folders under
    # [EN] `%TEMP%`, **never** touching `Projects/` or the real `.ui_state`.
    'verify_empty_archive',
    # ★★★ **书斋里改项目的显示名（文件夹不动，引用跟着走）**（2026-10-29）：
    #   用户原话「在书斋（当前项目设置）里修改项目的名字 并且修改相关引用
    #   但是不改文件夹名字」。名字活在三处：`.nwsproj` 的 `名称=`（事实来源）、
    #   项目文件自己的文件名（**最危险** —— 改名后旧文件不删，`scan_projects`
    #   会把同一个文件夹扫成两本书）、文件夹名（用户点名不许动 —— 存档/设定集/
    #   导出稿全挂在上面）。A 组真盘测 `Project.rename()`（成功/旧文件清理/
    #   扫描不重复/内容原封不动/空名与撞名拒绝/写失败回退），B 组 AST 钉书斋
    #   接线（名字框在第 0 页、save() 先改名且失败即中止、日志与上次书记录
    #   跟走、窗口标题刷新）。全在 `%TEMP%` 造真项目 ⇒ **逻辑组**。
    # [EN] ★★★ **Renaming the project's display name in the Study (folder untouched, references
    # [EN] follow)** (2026-10-29). The name lives in three places: the `.nwsproj` `名称=` (source of
    # [EN] truth), the project file's own filename (**most dangerous** -- leaving the old file behind
    # [EN] makes `scan_projects` see two books in one folder), and the folder name (the user forbids
    # [EN] touching it). Group A exercises `Project.rename()` on real temp-disk projects; group B pins
    # [EN] the Study wiring via AST. **Logic group** (temp dirs only).
    'verify_rename_project',
    # ★★★ **「推演结果」对话框（导出按钮改版）**（2026-10-29）：
    #   用户原话「修改导出按钮为推演结果按钮……多个Tab 原始稿/最终改写稿/
    #   原始稿加细节/运行报告/写作指导（左侧2个子页：LLM润色稿和写作指导）；
    #   最后3个默认空/不更新，点「生成/更新」才调 LLM；前三者打开就有；
    #   导出收进右上角；结束时自动导出独立成设置框」。四条分界线：
    #   ① 零成本三档走**直装订**（预览里绝不许出现 MuMu 重写/成书复查 ——
    #     打开对话框偷偷烧钱是最不能接受的）；② token 三份默认**只读**，
    #   按钮字「生成/更新」跟着内容走；③ 导出收右上角（`include_auto=False`）；
    #   ④ 自动导出设置复用 `_auto_switch_handler`。A 组真盘测
    #   `NV.latest_file`/`latest_polished` + 零成本装订，B 组 AST 钉接线。
    #   全在 `%TEMP%` + MOCK_LLM ⇒ **逻辑组**。
    # [EN] ★★★ **The "Derivation Results" dialog (export button redesign)** (2026-10-29):
    # [EN] five tabs; the token-spending three default to read-only with a Generate/Update
    # [EN] button; the zero-cost three bind on open (never MuMu/checkup in a preview);
    # [EN] Export moves to the top right; auto-export settings split into their own dialog.
    # [EN] Groups A (real temp runs) + B (AST) ⇒ **logic group**.
    'verify_results_dialog',
    # ★★ **空间常识与地图能力**（2026-10-12）：用户「小地图如果是室内地图 就用一个框
    #   把相关内容括起来 作为这个建筑的名字」「请严格区分室内室外……井肯定是要在
    #   院子里的」「如果有井 则说明有院子 需要把院子也画出来」「优化小说作家
    #   剧作家 编剧室 导演 美术和道具的能力」「导演和剧作家在设计人物动作的时候
    #   要时时刻刻参考地图作为人物移动的依据」。
    #   四组断言**全在纯逻辑层**（分类/审计/修复/走法都是纯函数；小地图那一组是把
    #   形状列表建出来数形状；职位那一组读提示词与货架），**不起窗口** ⇒ 归逻辑组。
    # [EN] ★★ **Spatial common sense and map ability** (2026-10-12): the user's items "if the minimap is
    # [EN] an indoor map, use a frame to enclose the relevant content as this building's name", "strictly
    # [EN] distinguish indoors and outdoors ... a well definitely belongs in the courtyard", "if there is
    # [EN] a well, that means there is a courtyard, so the courtyard must be drawn too", "optimise the
    # [EN] abilities of the novelist / playwright / writers' room / director / art / props", and "the
    # [EN] director and playwright must constantly consult the map as the basis for character movement".
    # [EN] All four groups sit **at the pure logic layer** (classification/audit/repair/routing are pure
    # [EN] functions; the minimap group builds the shape list and counts shapes; the positions group reads
    # [EN] prompts and shelves), **no window** ⇒ logic group.
    'verify_space_rules',
    # ★★★ 地图的**细致程度分档 + 室内画墙 + 大地图对话框 + 本地复用**（2026-10-12）：
    #   用户「现在的小地图中间都有一个红点 这个去掉 看不见其他元素了」+
    #   「如果是室内地图 则请把墙画出来」+「室内和室外结合的地图…把室内墙和室外墙
    #   都画出来」+「很大的地图 比如街道图…只需要把建筑标记出来」+
    #   「这个小地图可以点…打开一个大地图对话框（比较大的大小，跟对话列表的部分
    #   一样大）…左上角带基本信息 包括地点 时间 图例 比例尺…右上角有关闭按钮」+
    #   「所有的地图保存在本地如果后续场景能够复用的话则直接复用」。
    #   A~E 五组全是纯逻辑（**不起窗口**：分档是纯函数、小地图数形状、大地图数形状、
    #   存档读写真落盘）⇒ **逻辑组**。
    #   ⚠ 它真建临时项目、真落一份地图存档，但全在 `tempfile.mkdtemp` 下 ⇒ 不脏 Projects。
    # [EN] ★★★ The map's **level-of-detail tiering + walls drawn indoors + the big-map dialog +
    # [EN] local reuse** (2026-10-12): the user's "every minimap now has a red dot in the middle;
    # [EN] remove it, it hides the other elements" + "if it is an indoor map, then please draw the
    # [EN] walls" + "a map combining indoors and outdoors ... draw both the indoor walls and the
    # [EN] outdoor walls" + "a very large map, e.g. a street map ... you only need to mark out the
    # [EN] buildings" + "this minimap can be clicked ... a big map dialog opens (a fairly large size,
    # [EN] the same size as the conversation-list part) ... basic information in its top-left,
    # [EN] including location, time, legend, scale bar ... a close button in the top-right" + "all
    # [EN] maps are saved locally, and if a later scene can reuse one, just reuse it".
    # [EN] Groups A-E are all pure logic (**no window**: tiering is a pure function, the minimap
    # [EN] counts shapes, the big map counts shapes, the archive really reads and writes) ⇒ **logic
    # [EN] group**.
    # [EN] ⚠ It really creates a temp project and really writes a map archive, but all under
    # [EN] `tempfile.mkdtemp` ⇒ it does not dirty the user's Projects.
    'verify_roomplan',
    'verify_mapscale',
    'verify_map_detail',
    # 地图知识落地成 skills 之后的三件事（2026-10-27）：① 不是空壳 ② 触发关键词不互相覆盖
    # ③ **正文引用的 `image_gen.xxx::符号` 真的存在** + 写进去的数值与代码一致。
    # 纯文件 + import 检查，不起窗口 ⇒ 逻辑组。
    # [EN] After landing the map knowledge as skills (2026-10-27): not shells, no colliding trigger
    # [EN] keywords, and every cited `image_gen.xxx::symbol` really exists (plus numbers match the
    # [EN] code). Files and imports only, no window => logic group.
    'verify_map_skills',
    # ★★★ **台词要像活人说的**（2026-10-12，用户点名）：用户原话的意思是
    #   「真人对话…会有犹豫…不是每一句话都有回应…说话速度不会太快…每个人都会根据
    #    自己的性格决定自己的说话习惯；而很多 AI 生成的对白**没有卡顿、很快、
    #    从不犹豫**，还**很容易吼**」⇒ 要在"剧本生成 / 小说编写 / 演员表演"三条线上改。
    #   判据验五件事：六条手艺**都有人读**（不是货架摆设）· 三条线**真的接上了**
    #   （含演员那份"外置模板 + 内置 `_tail`"两份文本同步）· 审读清单从五件加到六件 ·
    #   去 AI 清单里多了「喊叫滥用」（且在**软提示**不在硬词表）· 开关真管用。
    #   五件事全在纯逻辑层能证完（读货架、取手艺块、AST 查挂载点、跑审计），
    #   **不起窗口** ⇒ 逻辑组。
    #   ⚠ 它只读文件与模块，不写任何用户目录（配置写入被 `redirect_env_writes` 转走）。
    # [EN] ★★★ **Dialogue must sound like a live person says it** (2026-10-12, named by the user): the
    # [EN] user's meaning was "real conversation ... has hesitation ... not every sentence gets a
    # [EN] response ... speaking speed is not too fast ... everyone's speech habits follow their own
    # [EN] character; whereas much AI-generated dialogue has **no stumbles, is fast, never hesitates**,
    # [EN] and **shouts easily**" ⇒ fix it across the three lines "script generation / novel writing /
    # [EN] actor performance".
    # [EN] The criteria verify five things: the six craft entries are **all read by someone** (not
    # [EN] shelf decoration) · the three lines are **really wired up** (including the actor's two
    # [EN] texts -- external template + built-in `_tail` -- in sync) · the review checklist grows from
    # [EN] five items to six · the de-AI list gains "shouting abuse" (in the **soft hints**, not the
    # [EN] hard word list) · the switch really works.
    # [EN] All five are provable at the pure logic level (read the shelf, fetch the craft block, AST
    # [EN] the mount points, run the audit), **no window** ⇒ logic group.
    # [EN] ⚠ It only reads files and modules; it writes no user directory (config writes are redirected
    # [EN] by `redirect_env_writes`).
    'verify_live_speech',
    # ★★★ **语言审校真的查语域（自然标准普通话）并给改写**（2026-10-15，P1）：
    #   两层提示词（软件层 .md + `crew/agents.py` 任务 f-string）都含语域硬约束，
    #   且行为上塞半文白台词真能渲染出「改写为：…」。纯逻辑（读盘 + AST + MOCK 行为），
    #   **不起窗口** ⇒ 逻辑组。
    # [EN] ★★★ **The Language Polisher really checks register (natural standard Mandarin) and gives a
    # [EN] rewrite** (2026-10-15, P1): both prompt layers carry the register hard-constraint, and
    # [EN] behaviourally a half-classical line really renders "改写为：…". Pure logic (read disk + AST
    # [EN] + MOCK behaviour), **no window** ⇒ logic group.
    'verify_polisher_register',
    # ★★★ **分镜师（P2）+ 视觉参考图（P3）真实接入 pipeline**（2026-10-15）：
    #   两位在 MEMBERS / ROSTER 登记、各有一份软件层 .md；`compose` 在剧本定稿后
    #   真的调 `studio.call('storyboard'/'visref')` 并把分镜写回 `ds.shots`、带开关守卫；
    #   两个 `work` 行为上真能产出。纯逻辑（读盘 + AST + MOCK / 打桩 image_gen），
    #   **不起窗口** ⇒ 逻辑组。
    # [EN] ★★★ **Storyboard (P2) + Visual Reference (P3) really wired into the pipeline** (2026-10-15):
    # [EN] both registered in MEMBERS/ROSTER with a software-layer .md; `compose` really calls
    # [EN] `studio.call('storyboard'/'visref')` after the script is finalized and writes shots back to
    # [EN] `ds.shots`, guarded by switches; both `work` methods really produce. Pure logic ⇒ logic group.
    'verify_storyboard',
    # ★★★ **地图几何 + 美术的 Reflection 环**（2026-10-12，用户点名七件事）：
    #   「这个大地图**柜台跑到墙外面了**」·「左上角的图例**有些字在方框外面**」·
    #   「**比例尺把字盖住了** **比例尺你放到左下角吧**」·
    #   「左上角的图例**不要带方框了** 但是要注意**地图部分不要跟图例重合**」·
    #   「**房子的一部分和院子的一部分重合里** **美术Agent绘制地图的时候要用
    #     Reflection的机制 绘制之后去审核 如果有问题则修复问题重新绘制 直到没问题**」·
    #   「大地图右上角**2 个关闭按钮** **留外面的一个就行 红底的关闭按钮去掉**」·
    #   「不管是大地图还是小地图 **建筑的名字标记都放到墙的旁边** 不要放到别的东西的上面」。
    #   判据九组：审核查得出 · 修复真的修好（**Reflection 的核心**）· 渲染层几何 ·
    #   只加不减 · 图例与比例尺 · 只有一个关闭按钮 · 名字贴墙 · 美术挂了 Reflection ·
    #   口径唯一（产品与判据共用同一份几何）。
    #   九组全是纯逻辑（读形状、跑解算、AST 查接线、monkeypatch 验兜底），
    #   **不起窗口** ⇒ 逻辑组。
    #   ⚠ 它只读文件与模块，不写任何用户目录（monkeypatch 在 `finally` 里还原）。
    # [EN] ★★★ **Map geometry + the art dept's Reflection loop** (2026-10-12, seven things the user
    # [EN] named): "on this big map **the counter has run outside the wall**" · "in the top-left legend
    # [EN] **some text is outside the box**" · "**the scale bar covers the text** -- **put the scale
    # [EN] bar in the bottom-left**" · "the top-left legend **should not have a box**, but note that
    # [EN] **the map part must not overlap the legend**" · "**part of the house and part of the
    # [EN] courtyard overlap**; **when the art Agent draws the map it should use the Reflection
    # [EN] mechanism: after drawing, go and audit it; if there is a problem, fix it, redraw, until
    # [EN] there is no problem**" · "there are **2 close buttons in the big map's top-right**; **keep
    # [EN] just the outer one -- remove the red-background one**" · "whether it's the big map or the
    # [EN] minimap, **put the building's name label beside the wall**, not on top of other things".
    # [EN] Nine groups of criteria: the auditor finds it · the repair really fixes it (**the heart of
    # [EN] Reflection**) · render-layer geometry · only add never remove · legend and scale bar · only
    # [EN] one close button · names hug the wall · the art dept is wired to Reflection · one definition
    # [EN] (product and criteria share the same geometry).
    # [EN] All nine are pure logic (read shapes, run the solver, AST the wiring, monkeypatch the
    # [EN] fallback), **no window** ⇒ logic group.
    # [EN] ⚠ It only reads files and modules; it writes no user directory (the monkeypatch is restored
    # [EN] in `finally`).
    'verify_plan_geometry',
    # ★ **三级底图**（2026-10-08）：用户「在开卷的时候把一些整体地图 局部地图
    #   (房屋附近 房屋内部) 提前画好，需要的时候基于这些地图让美术加细节」。
    #   判据验的是"判得准、存得下、读得回、取景对、拿不到就降级"——
    #   五件事全在纯逻辑层能证完（MOCK + 打桩），**不起窗口**，所以归逻辑组。
    # [EN] ★ **Three-level base map** (2026-10-08): user "when opening the book, draw some overall maps,
    # [EN] local maps
    # [EN] (near the house, inside the house) in advance, and when needed have the art add details based on
    # [EN] these maps".
    # [EN] Criteria verify "judges accurately, stores it, reads it back, framing is correct, degrade when
    # [EN] unavailable" ——
    # [EN] all five things can be proven at the pure logic layer (MOCK + stubbing), **does not open a
    # [EN] window**, so belongs to logic group.
    'verify_map_atlas',
    # ★ 说明书里的命令（参数 + 示例，2026-10-08）：用户原话
    #   「使用说明里的**命令** 把每个命令的**参数也加上** 并且每个命令**加上示例**」。
    #   全是**文件读写**（读源码抽参数 / 读说明书看表格行与示例行），
    #   一个窗口都不起 —— 所以归逻辑组。
    # [EN] ★ Commands in the manual (parameters + examples, 2026-10-08): user's original words
    # [EN] "for the **commands** in the usage instructions, **also add the parameters** of each command,
    # [EN] and **add an example** for each command".
    # [EN] All are **file reads/writes** (read source to extract parameters / read manual to see table rows
    # [EN] and example rows),
    # [EN] not a single window is opened —— so belongs to logic group.
    'verify_manual_commands',
    # ★ 文档布局：**开发向文档进 `developers/docs/`、用户文档留根目录**（2026-10-10）：
    #   用户原话「这里的一些md（包括子文件夹）如不是代码需要的以及确实给用户用的，
    #   别的用于给开发者用的，**都放到 developers 里并进行整理**」。
    #   判据只读文件系统 + import 发布脚本收集排除集，**不起窗口** —— 归逻辑组。
    #   ★ 里面最要紧的一条是 C5：**用户文档链接得到的东西，发布包里必须有**
    #   （这一条正是本轮那个真 bug 的根：README 链《配置分类》，而发布脚本把它排除了）。
    # [EN] ★ Documentation layout: **developer-facing docs go into `developers/docs/`, user docs stay in
    # [EN] the root directory** (2026-10-10):
    # [EN] User's exact words: "Some of the md here (including subfolders), if not needed by the code and
    # [EN] actually meant for users,
    # [EN] while others are meant for developers, **put them all into developers and organize them**".
    # [EN] The criterion only reads the filesystem + imports the release script to collect the exclusion
    # [EN] set, **does not open a window** -- belongs to the logic group.
    # [EN] ★ The most important one among them is C5: **whatever is reachable via user doc links must be
    # [EN] present in the release package**
    # [EN] (this is exactly the root of this round's real bug: the README links to《配置分类》, but the release
    # [EN] script excludes it).
    'verify_doc_layout',
    # ★ 外部借鉴落地（2026-10-10）：用户原话
    #   「所有外部调研的 Agent，你都根据学习的结果优化修改本地对应 Agent 了吗？
    #    **没有的话就实现下**，注意修改完一轮之后需要进行评过」。
    #   判据验五类调研的借鉴点是否**真的接进了对应 Agent**（不是"常量存在"）：
    #   画风圣经/空镜/两路权重、景别闭集/相邻景别硬规则/节拍配方/量化闸门、
    #   场记一致性契约/伏笔账、记忆不可信史料/防串台/反思形状、可拍性硬规则、
    #   连续指标接进审计/中文分句/按句截断。
    #   全在纯逻辑层（假世界 + 假数据），**不起窗口** —— 归逻辑组。
    # [EN] ★ External borrowing put into practice (2026-10-10): user's exact words
    # [EN] "For all external-research Agents, did you optimize and modify the corresponding local Agents
    # [EN] based on what you learned?
    'verify_agent_upgrades',
    # ★ LLM 用量统计（2026-10-10）：用户原话
    #   「现在有大量的模块用到 LLM，我希望在运行界面的合适位置加一个链接，
    #    点进去之后可以看到当前项目以及软件整体最近一段时间来的 LLM Token
    #    使用情况（Token 量以及费用）……最好这些信息**不使用 LLM 动态生成**的，
    #    而且**不要在本地保存 md 等信息**，默认统计信息**存入数据库**……
    #    还希望可以支持**导出报告**，最好是导出 **xlsx** 格式……
    #    第一个 Sheet 一定是**总体信息**」。
    #   判据验：落库/四种划分聚合/项目隔离/Agent 分层、xlsx 多 Sheet 中英双语、
    #   "不调模型""不落 md"两条硬约束、以及**接线**（Ledger.add / setup / studio
    #   三处，都在那个块里查）。全在纯逻辑层（临时库 + 临时文件），归逻辑组。
    # [EN] ★ LLM usage statistics (2026-10-10): user's original words
    # [EN] "Now a large number of modules use LLM. I want to add a link at an appropriate place on the
    # [EN] running interface,
    # [EN] and after clicking into it, one can see the LLM Token
    # [EN] usage of the current project and the software as a whole over a recent period (Token count and
    # [EN] cost)... it is best that this information is **not dynamically generated using LLM**,
    # [EN] and **do not save md and other information locally**; by default the statistics **are stored in
    # [EN] the database**...
    # [EN] It is also hoped that **exporting reports** can be supported, preferably exporting in **xlsx**
    # [EN] format...
    # [EN] The first Sheet must be **overall information**".
    # [EN] Verification criteria: persistence to database / aggregation across four divisions / project
    # [EN] isolation / Agent tiering, xlsx multi-Sheet Chinese-English bilingual,
    # [EN] the two hard constraints of "no model calls" and "no md persistence", as well as the **wiring**
    # [EN] (Ledger.add / setup / studio
    # [EN] three places, all checked in that block). All in the pure logic layer (temporary database +
    # [EN] temporary files), assigned to the logic group.
    'verify_usage_stats',
    # ★ 本轮三支（2026-10-10）：全部是纯逻辑/纯源码层，不弹窗、不用模型。
    #   `verify_tabs_fit` 用 PIL + 随附字体量页签宽度（不需要真机）；
    #   `verify_save_sort` 造临时存档目录读跨度；
    #   `verify_exit_guard` 里那两段"子进程真跑"是**本判据存在的理由** ——
    #   它要把"有未完成的 to_thread 时解释器不退"这件事当场跑出来。
    #   对应反例法：`developers/mutate_ui_20261010.py`（21 组）。
    # [EN] ★ Three branches this round (2026-10-10): all are pure logic / pure source layer, no popups, no
    # [EN] model.
    # [EN] `verify_tabs_fit` uses PIL + bundled fonts to measure tab width (no need for a real machine);
    # [EN] `verify_save_sort` creates a temporary save directory to read the span;
    # [EN] the two "subprocess truly runs" sections in `verify_exit_guard` are **the reason this criterion
    # [EN] exists** ——
    # [EN] it needs to run out on the spot the fact that "the interpreter does not exit when there are
    # [EN] unfinished to_thread tasks".
    # [EN] Corresponding counterexample method: `developers/mutate_ui_20261010.py` (21 groups).
    'verify_tabs_fit',
    'verify_save_sort',
    'verify_exit_guard',
    # ★ 推演评估体系（2026-10-10）：用户问「你是否有一套完整的评估体系」。
    #   代码那一半早就有（本文件 + 反例法）；**产物那一半是新的** ——
    #   从跑完的一轮存档里读出"哪里不对、该动哪个模块"。
    #   放在 LOGIC 组：全程读盘 + 本地统计，**一次模型调用都没有**，
    #   也不弹窗（合成存档写在临时目录里）。
    # [EN] ★ Deduction evaluation system (2026-10-10): the user asked "Do you have a complete evaluation
    # [EN] system".
    # [EN] The code half has long existed (this file + counterexample method); **the artifact half is new**
    # [EN] ——
    # [EN] from a completed round's save, read out "what is wrong, which module should be changed".
    # [EN] Placed in the LOGIC group: reads disk throughout + local statistics, **not a single model
    # [EN] call**,
    # [EN] and no popups either (synthetic saves are written in a temporary directory).
    'verify_run_review',
    # ★ **起笔对话框：前情提要 + 作者走向建议**（2026-10-11）：用户原话
    #   「我希望在起笔的时候，可以有一个地方加上用户自己对于故事接下来走向的建议。
    #    我觉得可以在提笔的前情提要的下面……**而且请确保这里的前情提要和后续
    #    运行窗口对话显示的时候给的前情提要一样**」。
    #   判据 A 组**装配一个真的 `RunLoop`** 去比 `_recap_text()`（逐字）——
    #   这条要求只有真机/真装配能证；B 组抓**真发出去的 messages** 看建议进没进提示词。
    #   归逻辑组：全程 MOCK、不开窗口（界面那半在 `verify_author_note_ui`）。
    # [EN] ★ **Start-writing dialog: recap + author direction suggestions** (2026-10-11): user's original
    # [EN] words
    # [EN] "I hope that when starting to write, there can be a place to add the user's own suggestions for
    # [EN] where the story should go next.
    # [EN] I think it can be below the recap when starting to write... **and please ensure that the recap
    # [EN] here is the same as
    # [EN] the recap given when the subsequent running window dialog is displayed**".
    # [EN] Criterion group A **assembles a real `RunLoop`** to compare `_recap_text()` (verbatim) ——
    # [EN] this requirement can only be proven by a real machine / real assembly; group B captures **the
    # [EN] messages actually sent** to see whether the suggestion entered the prompt.
    # [EN] Assigned to the logic group: MOCK throughout, no window opened (the UI half is in
    # [EN] `verify_author_note_ui`).
    'verify_author_note',
    # ★ **Python SDK**（2026-10-11）：用户要求"整理成 Python SDK API，用脚本控制
    #   完整流程（推演项目 / 推演存档 / 日常操作 / 全局设置 / 项目设置 / 报告导出）"。
    #   这一支**真建书 → 真开卷 → 真推演 3 拍 → 真导出 → 真存档 → 真删**，
    #   全部在 `tempfile.mkdtemp` + MOCK 里做（判据 K4/K5 跑完还要比对
    #   用户 `.env` 的 sha1 与真实 `Projects/` 的条目数，**自证没碰你的东西**）。
    #   归逻辑组：SDK 整个包**不 import flet**（判据 A3 钉着），全程无窗口。
    #   ⚠ 它比一般逻辑判据慢（约 40 秒：开卷 + 真跑 3 拍 + 6 条 CLI 子进程）。
    # [EN] ★ **Python SDK** (2026-10-11): the user requested "organize into a Python SDK API, use scripts
    # [EN] to control
    # [EN] the complete flow (deduction project / deduction save / daily operations / global settings /
    # [EN] project settings / report export)".
    # [EN] This branch **truly creates a book -> truly opens a volume -> truly deduces 3 beats -> truly
    # [EN] exports -> truly saves -> truly deletes**,
    # [EN] all done inside `tempfile.mkdtemp` + MOCK (after criteria K4/K5 finish running, it also compares
    # [EN] the sha1 of the user's `.env` and the entry count of the real `Projects/`, **self-proving it did
    # [EN] not touch your stuff**).
    # [EN] Assigned to the logic group: the entire SDK package **does not import flet** (criterion A3 pins
    # [EN] this down), no window throughout.
    # [EN] ⚠ It is slower than ordinary logic criteria (about 40 seconds: opening a volume + truly running
    # [EN] 3 beats + 6 CLI subprocesses).
    'verify_sdk',
    # ★ **注释双语化**（2026-10-11）：用户要求"遍历所有的代码，把注释都改成中英文"。
    #   `tools/bilingualize_comments.py` 把中文注释与 docstring 补上 `# [EN]` 英文，
    #   这一支查的是**完成度与安全**：每一条含中文的注释后面都有译文 ·
    #   译文行本身不含中文 · **AST 指纹**证明代码结构一字未变
    #   （抹掉 docstring 正文后整棵树逐字相同）。
    #   ⚠ 它是**完成度判据**：哪天有人加了新的中文注释却没跑双语化，它会红 ——
    #     那正是它的用处（提醒补译文）。纯静态（只读文件、不调模型）⇒ LOGIC 组。
    # [EN] ★ **Bilingualization of comments** (2026-10-11): the user requested "traverse all the code,
    # [EN] change all comments to Chinese and English".
    # [EN] `tools/bilingualize_comments.py` adds `# [EN]` English to Chinese comments and docstrings,
    # [EN] this branch checks **completeness and safety**: every comment containing Chinese has a
    # [EN] translation after it ·
    # [EN] the translation line itself contains no Chinese · the **AST fingerprint** proves the code
    # [EN] structure is unchanged word for word
    # [EN] (after erasing the docstring body, the whole tree is verbatim identical).
    # [EN] ⚠ It is a **completeness criterion**: if someday someone adds a new Chinese comment but does not
    # [EN] run bilingualization, it will turn red ——
    # [EN] that is exactly its use (reminding to add the translation). Purely static (only reads files, no
    # [EN] model calls).
    # ⚠⚠ 2026-10-12：它**不能再登记在 LOGIC 组里** —— 同一支脚本同时出现在 LOGIC 与
    #    `ALONE` 里会让分组自检直接报"同一支脚本被登记了多次"、**整个回归跑不起来**
    #    （自检是 fail-fast 的）。它现在只登记在 `ALONE`（原因见那一段：并行时
    #    别的脚本会改写产品文件，而它逐字读全项目比对指纹）。
    # [EN] ⚠⚠ 2026-10-12: it **must no longer be registered in LOGIC** -- appearing in both LOGIC
    # [EN] and `ALONE` makes the group self-check report "the same script is registered more than
    # [EN] once" and **blocks the whole regression run** (the check is fail-fast). It is now only in
    # [EN] `ALONE` (see that passage: in parallel, other scripts rewrite product files while it reads
    # [EN] every file in the project and compares fingerprints).
    # ★ `.env` 的第四道保险丝（2026-10-11）：**不起窗口**，只起子进程 → **LOGIC 组**。
    #   它守的是「任何验证脚本都写不进用户的 `.env`」—— 包括"手工单跑"那种情况
    #   （回归器不给 `NWS_ENV_SINK` 时，靠"进程自己认得出是验证脚本"兜底）。
    # [EN] ★ The fourth fuse for `.env` (2026-10-11): **no window**, only subprocesses → **LOGIC group**.
    # [EN] It guards "no verification script can write into the user's `.env`" -- including the
    # [EN] "standalone run" case (when the regressor provides no `NWS_ENV_SINK`, the fallback is "the
    # [EN] process recognizes it is a verification script itself").
    'verify_env_safety',
    # ★★★ 推演产出要**像小说，不能只有对话**（2026-10-14，用户点名）：
    #   「我看现在的推演结果 是大量的对话 正常小说的话应该有任务的各种动作
    #     大量的环境 故事情节 人物做的事情 心理活动 等等不同的内容的…
    #     不应该只有对话」。
    #   它**纯逻辑**（不起窗口、不起真 LLM —— 用假 world/agent + monkeypatch
    #   `llm.chat`），几秒跑完，所以归 **LOGIC 组**。
    #   钉的是四层：① 动作要有描写（`Action.detail` 两条路都认）；
    #   ② 心理活动（任何动词带 `内心` 都要产 `ASIDE`）；
    #   ③ 环境（新增"与有没有人在动无关"的通路 + 按故事分钟节流 + 能关）；
    #   ④ 输入层（看得见的动作要进「场上刚发生」，否则下一拍人人都只接别人的**话**）；
    #   外加 ⑤ 对话配比（`talk()` 不再硬凑满轮数）与 ⑥ 提示词两份都改了。
    # [EN] ★★★ The deduction output must **read like a novel, not only dialogue** (2026-10-14, named
    # [EN] by the user): "I see the deduction output is mostly dialogue; a normal novel should have
    # [EN] the characters' various actions, a lot of environment, plot, things the characters do,
    # [EN] inner activity and so on ... it should not be only dialogue".
    # [EN] It is **pure logic** (no window, no real LLM -- fake world/agent plus a monkeypatched
    # [EN] `llm.chat`), finishes in seconds, so it belongs to the **LOGIC group**.
    # [EN] It pins four layers: (1) actions must carry a description (`Action.detail` recognized on
    # [EN] both paths); (2) inner activity (any verb carrying `内心` must produce an `ASIDE`);
    # [EN] (3) environment (a new path "independent of whether anyone is moving" + throttled by story
    # [EN] minutes + switchable off); (4) the input layer (visible actions must enter "just happened
    # [EN] on stage", otherwise on the next beat everyone only picks up the other's **words**);
    # [EN] plus (5) the dialogue ratio (`talk()` no longer padded to the full turn count) and
    # [EN] (6) both prompt copies changed.
    'verify_story_richness',
    # ★ 2026-10-17：补登记六支**漏进分组表**的脚本（回归器自检是 fail-fast 的，
    #   磁盘上有、表里没有 → 整个回归一支都不跑）。六支全部**不起窗口**
    #   （无 `ft.run(`、无 `isolate_projects_dir`），与 `verify_borrowings` 同型，
    #   所以都归 **LOGIC 组**。
    # [EN] ★ 2026-10-17: registering six scripts that were **missing from the group table**
    # [EN] (the regressor's self-check is fail-fast: on disk but not in the table → the whole
    # [EN] regression runs nothing). All six start **no window**
    # [EN] (no `ft.run(`, no `isolate_projects_dir`), same shape as `verify_borrowings`,
    # [EN] so they all go to the **LOGIC group**.
    'verify_crew_onduty',
    'verify_label_place',
    'verify_minimap_lod',
    'verify_mumu_export',
    'verify_novel_repeat',
    # ★★★ **导出内容完整性**（2026-10-17 用户点名）：
    #   「为何发生给你了很多事情 最后导出的内容非常少？剧情部分呢？人物对话呢？
    #     导出的应该是一个经过润色的完整的小说才对」。
    #   这一支守的是"一天的戏**不许在链路上被丢掉**"：
    #     ① `_day_lines()` 不能因为 `_daily_narrative` 有几行就**不展开 30 幕剧本**
    #        （实测：材料只有 5 行 ⇒ 整理稿 900 字 ⇒ 导出 1,185 字）；
    #     ② 整理要**分块**写全（4 万字一次喂，模型会挑几段写）；
    #     ③ 输出预算**跟材料长度走**（老用户 `.env` 里的 2600 会把稿子卡死）；
    #     ④ 导出**不许被 900 字的残稿顶掉 4 万字**。
    #   **纯逻辑**（假 world/agent，一次模型都不调），几秒跑完 ⇒ **LOGIC 组**。
    # [EN] ★★★ **Export content completeness** (named by the user 2026-10-17): "why is the exported
    # [EN] content so little? Where is the plot? Where is the dialogue? The export should be a polished,
    # [EN] complete novel." This guards "a day's drama must not be dropped along the pipeline":
    # [EN]   1. `_day_lines()` must not **skip the 30 scenes** just because `_daily_narrative` has a few
    # [EN]      lines (measured: 5 lines of material => 900-character draft => 1,185-character export);
    # [EN]   2. organizing must **chunk** and write it all (40k at once and the model picks a few);
    # [EN]   3. the output budget must **follow the material length** (a stale 2600 in the user's
    # [EN]      `.env` caps the draft);
    # [EN]   4. the export must **not let a 900-character draft displace 40k characters**.
    # [EN] **Pure logic** (fake world/agent, not a single model call), seconds to run => **LOGIC group**.
    'verify_novel_fullness',
    'verify_external_services',
    # ★★★ **判据不许把夹具项目写进用户的真实项目目录**（2026-10-17）：
    #   `isolate_projects_dir()` 返回的是**换之前的老值**，而"想拿新目录"的自然写法
    #   `Path(iso(base)) / '名字'` 拼出来是**用户真实项目目录 + 夹具名** ⇒
    #   每跑一次就往「拾卷」列表里塞一个测试项目，靠收尾 `safe_rmtree` 删，被 Kill 就留下
    #   （用户机上确实还躺着「字体设置验证」「面板跳转验证」）。一次扫出 **8 处**。
    #   纯逻辑（AST 扫描 + 行为对照），秒级 ⇒ LOGIC 组。
    # [EN] ★★★ **Criteria must not write fixture projects into the user's real project directory**
    # [EN] (2026-10-17): `isolate_projects_dir()` returns the **old value**, so the natural-looking
    # [EN] `Path(iso(base)) / 'name'` builds **the user's real directory + the fixture name** => every run
    # [EN] pushes a test project into the "拾卷" list, removed only by the teardown `safe_rmtree`, and
    # [EN] left behind on a kill (two are still sitting on the user's machine). Found **8 places** at
    # [EN] once. Pure logic (AST scan + behaviour contrast), seconds => LOGIC group.
    'verify_projects_isolation',
    # ★★★ **判据跑完/被杀之后不许在桌面上留 Flet 窗口**（2026-10-17 用户报）：
    #   「有大量的flet working的窗口没退出」。现场是两份全量回归同时跑、各自卡在一支
    #   真机判据上，`flet.exe` 变成孤儿卡在「Working...」加载页。
    #   守三件事：① 超时要**杀整棵进程树**（旧写法只杀直接子进程，`flet.exe` 是孙进程）；
    #   ② 卡住的脚本要**自己退**（看门狗，别指望被外面杀）；③ 回归**单飞**（不许同时跑两份）。
    #   还顺带守"开跑前把上次的孤儿收掉"，以及清理时**不许碰用户自己开着的窗口**。
    #   纯逻辑（起一两个短命子进程、注入假进程表），十几秒 ⇒ LOGIC 组。
    # [EN] ★★★ **No Flet window may be left on the desktop after a criterion finishes / is killed**
    # [EN] (reported by the user 2026-10-17): "a pile of flet working windows that never exit". The
    # [EN] scene was two full regressions running at once, each stuck on a real-machine criterion,
    # [EN] with orphaned `flet.exe` clients stuck on the "Working..." page.
    # [EN] It guards three things: (1) the timeout must **kill the whole process tree** (the old form
    # [EN] only killed the direct child; `flet.exe` is a grandchild); (2) a stuck script must **exit by
    # [EN] itself** (watchdog, don't rely on being killed); (3) the regression is **single-flight**.
    # [EN] It also guards "sweep the previous run's orphans before starting" and "never touch the
    # [EN] user's own open windows while sweeping".
    # [EN] Pure logic (a couple of short-lived child processes, injected process table), ~15s => LOGIC.
    'verify_orphan_windows',
    # ★★★ **同一个人不许连着几拍重演同一段动作**（2026-10-17 真跑量出来的）：
    #   「用一个真实项目以及 samples 里的示例项目全部走一遍推演」时，悬疑类头三拍
    #   里主角把"拎桶进屋 → 倒水 → 手指划过铜标尺 → 水面高了一截"演了三遍
    #   （相似度 87% / 83%），另一本里配角"靠墙根蹭墨盒"两拍重复（65%）。
    #   根因：`[刚才]` 只给 6 条，一拍七个人各说一句就把他自己的动作挤出窗口，
    #   下一拍他手上只剩"我的目标"，只好把刚做过的事再做一遍。
    #   纯逻辑（造 recent_lines + AST 查语句），秒级 ⇒ LOGIC 组。
    # [EN] ★★★ **The same person must not replay the same action across consecutive beats**
    # [EN] (measured on real runs 2026-10-17): while running Mowen Tower plus the bundled samples,
    # [EN] the mystery sample had Shen Yan perform "carry the bucket in -> pour -> finger along the
    # [EN] scale -> water a notch high" three beats in a row (87% / 83% similar), and Mowen Tower had
    # [EN] Zhu Bi rub his ink box twice (65%). Root cause: `[刚才]` only yields 6 entries and seven
    # [EN] people speaking one line each pushes his own action out, so next beat he only has "my goal"
    # [EN] and redoes what he just did. Pure logic (built `recent_lines` + AST), seconds => LOGIC.
    'verify_action_replay',
    # ★★★ **防复读 / 上一拍说的话 / 雪国的教训**（2026-10-18 用户点名）：
    #   「speak 的问题修复，复读的问题修复，雪国的教训也想办法修复」。
    #   ① `kind` 表与生产侧不一致（产品写 `act`，取数只认 `action`）⇒ 防重演整版没生效，
    #      而 2026-10-17 那支判据自己造夹具 ⇒ 全绿；
    #   ② 台词从没被喂回去（`ltxz-01`：6 次决策 4 次同一句）；
    #   ③ 环境句把「底噪+事件声+静默」捆成一条 ⇒ 底噪/静默每拍重复；
    #   ④ 台词去重只认一字不差；
    #   ⑤ 《雪国》五条缺陷 → 三条落到产品（点题式叙述 / 台词整句 / 没有落点）。
    #   纯逻辑（造缓冲、扫生产侧 kind、打桩），秒级 ⇒ LOGIC 组。
    # [EN] ★★★ **Anti-repetition / what you said last beat / the Snow Country lessons** (2026-10-18):
    # [EN] (1) the `kind` table disagreed with the producer (`act` vs `action`) so anti-replay never
    # [EN] ran while the old criterion built its own fixture and stayed green; (2) dialogue was never
    # [EN] fed back (4 of 6 decisions identical); (3) ambient candidates bundled bed+event+silence so
    # [EN] two of them repeated every beat; (4) dialogue dedup only caught verbatim repeats;
    # [EN] (5) Snow Country's five defects reduce to three product causes. Pure logic, seconds => LOGIC.
    'verify_repetition_guards',
    # ★★★ **剧本审读承担「语义级重复」与「越界」**（2026-10-18 用户点名）：
    #   「剧本审读承担语义级别重复和越界判定这条路你彻底实施下去」。
    #   文本层的逐字重复已有三处护栏；剩下的是**语义重复**（相似度 0.3–0.6，
    #   `near_same` 抓不到）与**硬约束越界**（人物红线 / 世界铁律被踩），
    #   这两件只有"读懂意思"才判得出 ⇒ 搬到上屏之前的审读。
    #   分工：程序挑候选（零成本召回）、模型判真假（理解），
    #   处置：改写优先；**重复改不动就放行**（删掉会留空白）；整拍全拦 ⇒ 全部放行。
    #   纯逻辑（造台账、打桩抓 prompt、假 builder），秒级 ⇒ LOGIC 组。
    # [EN] ★★★ **Script review takes on "semantic repetition" and "out of bounds"** (2026-10-18):
    # [EN] verbatim repetition already has three guards; what remains is semantic repetition
    # [EN] (similarity 0.3-0.6, invisible to `near_same`) and hard-constraint violations (character
    # [EN] red lines / world iron rules), both judgeable only by *understanding* => moved to the
    # [EN] pre-screen review. Split: the program proposes candidates, the model judges; disposition:
    # [EN] rewrite first, **let repetition through when it cannot be rewritten** (blocking leaves a
    # [EN] blank), never empty a whole beat. Pure logic, seconds => LOGIC.
    'verify_review_semantic',
    'verify_prose_rhythm',
    'verify_dialogue_cohesion',
    'verify_writing_coverage',
    # ★★★ **手艺调度**（2026-10-18 晚）：用户「71 条手艺也全部落地 且根据需要动态映射
    #   四个缺口也修复 总表里的不存在的手艺库内容全部补全 都进入提示词 都有判定依据
    #   都进行判定 都在合理的实际动态的映射到不同类型且在合适的时候进行调用」。
    #   改造前实测：**81 条里 24 条从来没到过任何人的提示词**（`_craft_for` 第 ③ 步按
    #   yaml 文件顺序补满），而且"这一拍是开场还是收束"对读什么毫无影响。
    #   现在按（职位 × 类型 × 时机 × 品级 × 拍数）动态挑；品级由**导演**判。
    #   真跑 `decide()` 抓 prompt（#4 需求 / #10 距离 / #7 余波都要真的在里面），
    #   秒级到十几秒（有一条跨进程比对）⇒ LOGIC 组。
    # [EN] ★★★ **Craft dispatch** (2026-10-18 evening): measured before the change, **24 of 81
    # [EN] entries never reached any prompt** and "is this beat an opening or a closing" had zero
    # [EN] effect. Now picked by (role x genre x moment x grade x tick); the grade is judged by the
    # [EN] director. Really runs `decide()` and captures the prompt. Seconds => LOGIC.
    'verify_craft_dispatch',
    # ★★★ **用量缺口 + 跨进程共享缓存**（2026-10-19 用户点名）。
    #   ① 查出来三处"花钱但一分账都不记"的：embedding / 图片生成 / 模型探测 ——
    #      它们都用**自己建的 httpx**，绕过了 `router.Ledger`（全项目唯一汇合点）。
    #   ② 三个外挂服务**仍然是空的**（独立进程 + 独立 venv），这一条**如实判"没采到"**，
    #      不假装有（静默降级是明令禁止的）。
    #   ③ 共享缓存 `llm/cache.py`：一个 sqlite 文件，主程序与三外挂可用同一张表；
    #      判据里有一条**起子进程写、父进程读** —— 那才叫跨进程，同进程 put/get 证明不了。
    #   纯逻辑（起一个 180s 超时的子进程），十几秒 ⇒ LOGIC。
    # [EN] ★★★ **Usage gaps + cross-process shared cache** (named by the user 2026-10-19).
    # [EN] ① Three places spent money with zero bookkeeping: embedding / image generation /
    # [EN] model probing -- all use **their own httpx**, bypassing `router.Ledger`. ② The three
    # [EN] external services are **still empty** (separate processes + venvs); this check reports
    # [EN] that **honestly**. ③ Shared cache `llm/cache.py`: one sqlite file usable by the main
    # [EN] program and all three extras; one check **writes in a child process and reads in the
    # [EN] parent** -- same-process put/get proves nothing. Pure logic => LOGIC.
    'verify_usage_and_cache',
    # ★★★ **自由度**（2026-10-19 用户把定位从「AI 写作工具」改成「推演工具」）。
    #   它守的是一对方向相反的约束：高自由度时**剧本/分拍表真的消失**，
    #   而**文笔那三块（说话人隔离 / 去 AI 清单 / 思维链）一块都不许少** ——
    #   只判前一半的判据，在"全松"的实现下照样绿。
    #   纯逻辑 + 拦 `llm.chat`（不真发请求）⇒ LOGIC。
    # [EN] ★★★ **Freedom** (the user repositioned from "AI writing tool" to "simulation tool" on
    # [EN] 2026-10-19). It guards a pair of opposite constraints: at high freedom the script and beat
    # [EN] sheet really disappear, while the three prose blocks must not lose a single one -- a check
    # [EN] that judged only the first half would stay green under a "loosen everything" implementation.
    # [EN] Pure logic + intercepting `llm.chat` => LOGIC.
    'verify_agent_freedom',
    # ★★★ **世界法则**（2026-10-19 用户：「把'导演'从编剧改成世界法则」）。
    #   守"事件类型由压力算出来，不是模型挑出来的"：四个压力各算得出、
    #   模型答别的类型会被覆盖、全低就不出事、重生成支路也改不了类型。
    #   拦 `llm.chat`，不真发请求 ⇒ 纯逻辑。
    # [EN] ★★★ **World law** (user, 2026-10-19: "turn the director from a screenwriter into world
    # [EN] law"). Guards "the event type is computed from pressure, not chosen by the model".
    'verify_world_law',
    # ★★★ **整理稿的句法与承接**（2026-10-19 用户：「每一句都恨不得交代一个事情…
    #   酒还温着 / 你 / 可能是叶子 / 你觉得我是什么样的人 之间没有任何关系」）。
    #   四轮探针把"句子短"否掉了（与真人持平），真正可数的是**局部**：
    #   某些段落整段是报告句、台词并排不说话。守四件事：提示词要求"并句不是逐条翻译"、
    #   台词要回前一句、心里话要有主、**平铺段自检重写真的接在生产路径上**。
    #   拦 `ask`，不真发请求 ⇒ 纯逻辑。
    # [EN] ★★★ **The organized draft's syntax and continuity** (2026-10-19). Four probes
    # [EN] disproved "sentences are too short"; the countable problem is local. Guards four
    # [EN] things: merge (not per-line translation), replies must answer the previous line,
    # [EN] inner voice must have an owner, and the flat-paragraph self-rewrite is really wired.
    'verify_prose_flow',
    # ★★★ **规则表还算不算数**（2026-10-19 第八轮整理）。
    #   最近七轮的修复被登记进 `crew/novel_rules.py`（23 条），本判据把表里
    #   每一条声明拿到仓库里核：落点文件还在、判据 ID 真在对应脚本里、
    #   变异编号真在反例法里、欠账条数没涨、文档与表逐字节一致。
    #   ⇒ 它守的不是"文笔"，是"**我们记下的那张表没有开始说谎**"。
    #   ⚠ 这比它看起来重要：登记表一旦烂掉，下一轮就会照着一张错的表改代码。
    # [EN] ★★★ **Is the rule table still true?** The seven rounds of fixes are registered in
    # [EN] `crew/novel_rules.py` (23 rules), and this check verifies every claim in it against the
    # [EN] repo: landing files still exist, criterion IDs really live in those scripts, mutation IDs
    # [EN] really live in the counterexample files, the debt count has not grown, and the generated
    # [EN] doc matches the table byte for byte. It guards "the table has not started lying".
    'verify_novel_rules',
    # ★★★ **卫生分不许冤枉心里的话**（2026-10-20）。
    #   `snow_v18` 被报「第三人称作品里叙述层出现『我』×18」白扣 7.9 分，
    #   查下去全是 `驹子心想：我…` 这种条目 —— 心里自称"我"本来就是对的。
    #   这一支守两件事：**不放过真漂移**（「我」落进叙述层还得罚）、
    #   **不冤枉心里的话**（`aside` 与 `dialogue` 一样排除）。
    #   ⚠ 顺带防一种"修法"：为了消掉误报把整栏关掉 —— M2 专门盯这个。
    # [EN] ★★★ **The hygiene score must not punish inner speech** (2026-10-20). snow_v18 was
    # [EN] docked 7.9 points for "18 first-person marks in a third-person work"; every hit was
    # [EN] an entry like "驹子心想：我…" -- thinking "I" is correct. Guards both directions:
    # [EN] real drift (first person in the narration layer) is still punished, and `aside` is
    # [EN] excluded like `dialogue`. Counterexample M2 also blocks the lazy "just disable the
    # [EN] whole column" fix.
    'verify_hygiene_pov',
    # ★★★ **界面自由度**（用户：「要在界面说清楚不同设置值的作用」）。
    #   核心不是"文案里有没有某个词"，而是**拿 freedom.py 真跑一遍去核文案** ——
    #   三处真相（freedom 常量 / config.desc / 界面文案）必须一致。
    # [EN] ★★★ **Freedom UI** ("make the effect of each value clear in the UI"). The core is not
    # [EN] "does the text contain a word" but **running freedom.py to check the text**: three
    # [EN] sources of truth must agree.
    'verify_freedom_ui',
    # ★★★ **文本质量**的四条底线（2026-10-17 用户点名）：
    #   「你在从头走一遍推理模拟 评价下各个阶段的输入输出质量（跟真人小说相比）
    #     看下是否有不是Bug但是有质量问题的情况 有的话优化」。
    #   功能都对、但读起来不像小说，用 `developers/probe_stage_quality.py` 量出来四件事：
    #   ① 环境白描 11 条只有 1 种（91% 逐字重复）；② 元标记 10 处混进正文；
    #   ③ 剧本写"傍晚"而时钟 08:00；④ 整理稿比开演前的样章还差（导出用的正是它）。
    #   顺带挖出一个真 bug：PlotPilot 的 `save_service_env` 写错地方 + 少 self ⇒
    #   用户点的模型**从来没进过服务的 .env**。
    #   纯逻辑（打桩抓 prompt、假 sink），秒级 ⇒ LOGIC 组。
    # [EN] ★★★ **Four baselines of text quality** (named by the user 2026-10-17): "walk through the
    # [EN] simulation from the start and rate the input/output quality of each stage (against a real
    # [EN] novel); find things that are not bugs but quality problems, and optimize them." Everything
    # [EN] worked and it still didn't read like a novel; `probe_stage_quality.py` measured four things:
    # [EN] (1) 11 ambient lines with 1 distinct; (2) 10 metadata markers in the prose; (3) the script
    # [EN] says "dusk" while the clock is 08:00; (4) the organized draft reads worse than the pre-show
    # [EN] sample (which is what the export used). Also found a real bug on the way: PlotPilot's
    # [EN] `save_service_env` wrote to the wrong place and missed `self` => the model the user picked
    # [EN] **never reached the service's .env**. Pure logic (stub the prompt, fake sink), seconds =>
    # [EN] LOGIC group.
    'verify_text_quality',
]

GUI: list[str] = [
    # ★ 2026-10-18 审计：这两支原来登记在 LOGIC，但源码里有 `ft.run(`（真开窗口），
    #   并行跑 LOGIC 组时会抢桌面 —— `verify_usage_layout` 自己的注释就写着
    #   "必须真开窗口"，登记却反着来（注释与代码不一致时先信行为）。
    # [EN] ★ 2026-10-18 audit: these two were registered under LOGIC but contain `ft.run(`
    # [EN] (a real window), so they grab the desktop while the LOGIC group runs in parallel --
    # [EN] `verify_usage_layout`'s own comment says "a real window is required".
    'verify_usage_layout',
    'verify_thinking_mode',
    # ★ 2026-10-24：「点状态条看这一发 AI 往来」—— **真开一个 Flet 窗口**去点那颗胶囊，
    #   所以必须在 GUI 组（并行跑会抢桌面）。A/B/C 组是纯逻辑，D/E 组才开窗。
    # [EN] ★ 2026-10-24: "click the status pill to see this LLM exchange" -- it **really opens a
    # [EN] Flet window** and clicks the pill, so it belongs in GUI (parallel runs would grab the
    # [EN] desktop). Groups A/B/C are pure logic; only D/E open a window.
    'verify_llm_probe',
    # ★★ 2026-10-25：同样漏登记的三支（理由见 LOGIC 组那一段注释）。
    # [EN] ★★ Three more that were likewise unregistered (reason in the LOGIC group note).
    'verify_crew_live',
    'verify_pick_volume_tree',
    # ★ 2026-10-31：拾卷两栏的「全选」（用户：「拾卷里 2个Tab的小说和存档都加上全选功能」）。
    #   归 GUI 组：整条链都在点击回调里（全选 → 级联锁 → 按钮文字 → 三档图标），
    #   数据层一条都不会动 ⇒ 只有真点一下才测得到。
    # [EN] ★ 2026-10-31: "select all" in both Pick-a-Volume columns. GUI group: the whole chain
    # [EN] lives in callbacks, so only a real click can test it.
    'verify_pick_all',
    # ★★ 2026-10-31：托盘图标 + 「关窗到底做什么」（用户：「加一个任务栏右下角图标……」）。
    #   归 GUI 组：D 组要**真开窗口**，再从外面读 `IsWindowVisible` 判"藏住了 / 叫回来了"——
    #   读 `page.window.visible` 是自欺（那是我们发出去的请求值）。
    # [EN] ★★ 2026-10-31: tray icon + "what closing really does". GUI group: group D opens a
    # [EN] real window and reads `IsWindowVisible` from outside; reading
    # [EN] `page.window.visible` would be self-deception (it is the request, not the fact).
    'verify_tray',
    # ★★ 2026-11-01：「天机 · 花费与优化」那一页（用户：「这个报告是否可以在天机里
    #   有一个Tab…智能分析…深度优化」）。归 GUI 组：C 组要**真开窗口**切到那一页、
    #   点一次「刷新」、再回读它自己那份日志有没有落行 —— 这三件在纯逻辑里验不到。
    # [EN] ★★ 2026-11-01: the "Cost & Tuning" tab. GUI group: group C opens a real window,
    # [EN] switches to that page, clicks Refresh once and re-reads its own log -- none of that
    # [EN] can be proven by pure logic.
    'verify_cost_tab',
    'verify_recycle_bin',
    'verify_svc_side_tabs',
    # ★★ **剧组 Agents 设置**（2026-10-11）：用户点名的三件事 ——
    #   ① 软件层 `agents/*.md` + README（英中对照）+ **项目层覆盖**；
    #   ② 天机/书斋各一个「剧组 Agents」页签（列表 / 编辑对话框 / 分页默认 5 /
    #      只在天机允许新建删除）；③ 开卷那一步 + AI 推断。
    #   归 GUI 组：真机段要**真开两个对话框**、真开编辑框、量截图色数
    #   （"控件树里有"≠"屏幕上看得见"）。
    #   ⚠ 它把**软件层 agents 目录**和**项目根**都指到临时目录
    # [EN] ★★ **Crew Agents settings** (2026-10-11): the three things the user named ——
    # [EN] ① software layer `agents/*.md` + README (English-Chinese side by side) + **project layer
    # [EN] override**;
    # [EN] ② one "Crew Agents" tab each in Tianji / Shuzhai (list / edit dialog / pagination default 5 /
    # [EN] only Tianji allows creating and deleting); ③ the volume-opening step + AI inference.
    # [EN] Assigned to the GUI group: the real machine section must **truly open two dialogs**, truly open
    # [EN] the edit box, measure screenshot color count
    # [EN] ("present in the control tree" ≠ "visible on the screen").
    # [EN] ⚠ It points both the **software layer agents directory** and the **project root** to a temporary
    # [EN] directory
    #     （`catalog.set_soft_dir` + `VU.isolate_projects_dir`）——
    #     绝不碰用户真的 `agents/` 与 `Projects/`。
    # [EN] and absolutely does not touch the user's real `agents/` and `Projects/`.
    # ★★ **模型登记表 / 每个 Agent 指定模型 / 推荐表**（2026-10-12）：
    #   用户点名的那一轮 —— ① 一个程序里配多个模型（每条自带地址与密钥）；
    #   ② 「AI模型配置」页 = 原来的两个 LLM 页合并；③ 所有 Agent 都有「模型」选项，
    #   打开就有推荐；④ novelservices 作为特殊 Agent 纳入管理。
    #   归 GUI 组：真机段要真开那一页、真新增一条、真点「剧组 Agents」。
    #   ⚠ 它给 `redirect_env_writes()` + 把**模型登记表**指到临时文件
    #     （那是用户数据；不隔离的话 `verify_ui_english` 会把用户起的
    #      中文模型名当成漏译 —— 实测过）。
    # [EN] ★★ **Model registry / per-Agent model / recommendation table** (2026-10-12).
    # [EN] ⚠ It gives `redirect_env_writes()` + points the **model registry** at a temp file
    # [EN] (that is user data; without isolation `verify_ui_english` treats a user's Chinese model
    # [EN] name as a missing translation -- measured).
    # ★★ **多模型费用统计 / 缓存命中 / 同题复用 / 降费**（2026-10-12 晚）：
    #   用户原话：「现在用AI的地方越来越多 话费太快 …… 如果多模型 则 LLM用量需要统计不同
    #   模型的费用 第二 你去学一下 看有什么办法优化AI Llm使用 尽量降低费用」。
    #   归 GUI 组：真机段要真开「AI模型配置」页看省钱块、真开模型编辑框看单价三项。
    #   ⚠ 它把**模型登记表**指到临时文件（那是用户数据），并给 `redirect_env_writes()`。
    # [EN] ★★ **multi-model cost accounting / cache hits / same-question reuse / cost reduction**
    # [EN] (2026-10-12 evening). Real-machine section opens the "AI Model Config" page for the saving
    # [EN] block and the model editor for the three unit-price fields.
    # [EN] ⚠ It points the **model registry** at a temp file (that is user data) and gives
    # [EN] `redirect_env_writes()`.
    'verify_cost_model',
    'verify_llm_models',
    'verify_agent_catalog',
    # ★ 用量报表的**栏头筛选菜单**（2026-10-11，用户："把筛选放到每个列的表头上"）：
    #   归 GUI 组 —— 它要**真开对话框**、真点菜单项，并把菜单按钮涂标记色量像素
    #   （"菜单画出来了没有"这件事，读源码和读控件树都答不了）。
    #   ⚠ 它给 `llm.usage.db_path` 打桩到临时库 + 隔离项目根 —— 不碰用户真实的账。
    # [EN] ★ Usage report's **column header filter menu** (2026-10-11, user: "put the filter on each
    # [EN] column's header"):
    # [EN] Assigned to the GUI group —— it must **truly open the dialog**, truly click the menu item, and
    # [EN] paint the menu button with a marker color to measure pixels
    # [EN] ("whether the menu has been drawn" is something neither reading source code nor reading the
    # [EN] control tree can answer).
    # [EN] ⚠ It stubs `llm.usage.db_path` to a temporary database + isolates the project root —— does not
    # [EN] touch the user's real ledger.
    'verify_usage_filters',
    # ★ 起笔对话框的**前情提要 + 作者走向建议**（2026-10-11，真机那一半）：
    #   要真开对话框、按标记色量像素（建议框**真的在前情提要下面**这件事
    #   只有位置量得出来），还要**真点一次「开始推演」**走通
    #   "对话框 → `_pending_directive` → `assemble` → 这一轮的 world"这条链。
    #   ⚠ 它给 `VU.redirect_env_writes()`（开跑会 `CFG.save()`）+ 隔离项目根。
    # [EN] The chain: dialog → `_pending_directive` → `assemble` → this round's world.
    # [EN] ⚠ It gives `VU.redirect_env_writes()` (running will call `CFG.save()`) + isolated project root.
    'verify_author_note_ui',
    # ★ **「起笔 · 本轮推演」那六项**（2026-10-11）：
    #   「这一轮要不要带关键剧情 / 大概发生几件事 / 没事要不要跳过时间 /
    #     本轮出场人物 / 固定场景 / 篇幅目标」。
    #   归 GUI 组：真机段要**真开起笔对话框**、按标签找到那几个控件、改值、
    #   真点一次「开始推演」，再核对配置里落的就是界面上的值。
    #   ⚠ 它给 `VU.redirect_env_writes()`（开工那一步会 `CFG.save()`）+ 隔离项目根。
    # [EN] ★ **"Start Writing · This Round's Inference" those six items** (2026-10-11):
    # [EN] "Whether this round should carry key plot / roughly how many things happen / whether to skip
    # [EN] time when nothing happens /
    # [EN] characters appearing this round / fixed scenes / length target".
    # [EN] Belongs to the GUI group: the real-machine segment requires **actually opening the Start Writing
    # [EN] dialog**, locating those controls by label, changing values,
    # [EN] and actually clicking "Start Inference" once, then verifying that what lands in the config is
    # [EN] exactly what was on the UI.
    # [EN] ⚠ It gives `VU.redirect_env_writes()` (the start step will call `CFG.save()`) + isolated project
    # [EN] root.
    'verify_round_controls',
    # ★ **演员的四层设置**（2026-10-11）：用户原话
    #   「演员Agent在系统层面是没有具体角色的 但是在项目层面是有具体角色的
    #    演员Agent在系统全局设置（天机）中如何设置和在项目级别如何设置」。
    #   判据按"换什么它才变"分层验：①系统职位 ②系统类型库 ③项目剧组 ④项目角色；
    #   其中 A7 是**为一个真 bug 立的碑**（`catalog._MUTABLE` 漏了 `'prompt'`
    #   ⇒ `agents/*.md` 的正文从来没生效过，改系统提示词是白改）。
    #   归 GUI 组：真有真机段（两个对话框要真开、真点、真存）。
    # [EN] ★ **The actor's four-layer settings** (2026-10-11): user's exact words
    # [EN] "The actor Agent has no specific role at the system level, but has a specific role at the
    # [EN] project level.
    # [EN] How is the actor Agent configured in the system global settings (Tianji) and how is it
    # [EN] configured at the project level?"
    # [EN] The criteria are verified in layers by "what changes it": ①system position ②system type library
    # [EN] ③project troupe ④project role;
    # [EN] Among them A7 is **a monument erected for a real bug** (`catalog._MUTABLE` was missing
    # [EN] `'prompt'`
    # [EN] ⇒ the body text of `agents/*.md` never took effect; changing the system prompt was a waste of
    # [EN] effort).
    # [EN] Belongs to the GUI group: there are real real-machine segments (two dialogs must be actually
    # [EN] opened, actually clicked, actually saved).
    'verify_actor_layers',
    # ★ 启动器（2026-10-10）：三个 exe 的**格式 / 平台 / 无控制台 / 服务随主窗口退出**。
    #   归 GUI 组：它要**真跑 exe**（起子进程、验证桌面上不冒控制台窗口），
    #   还要弹一次 tkinter 进度窗 —— 两件都是「必须真机」的事。
    # [EN] ★ Launcher (2026-10-10): the three exes' **format / platform / no console / service exits with
    # [EN] the main window**.
    # [EN] Belongs to the GUI group: it must **actually run the exe** (spawn a subprocess, verify no
    # [EN] console window pops up on the desktop),
    # [EN] and also pop up a tkinter progress window once — both are "must be real-machine" matters.
    'verify_launchers',
    'verify_dialog_close', 'verify_dialogue_log', 'verify_export', 'verify_font',
    'verify_help_book', 'verify_help_qa', 'verify_help_search', 'verify_help_toc',
    'verify_image_mode', 'verify_ingest_consent', 'verify_ingest_scan',
    'verify_ingest_status', 'verify_ingest_ui',
    # ★ 开卷重复拦截（2026-10-07）：这本已经开过卷时不许一声不吭又开一遍。
    #   真机段要走**真实入口**（向导 → `_do_import` → 提示框 → 真的开跑一次
    #   ingest），"点下去到底有没有开跑"只有真机能证，所以归 GUI 组。
    # [EN] ★ Duplicate open-volume interception (2026-10-07): when this book has already been opened, it
    # [EN] must not silently open it again.
    # [EN] The real-machine segment must go through the **real entry point** (wizard → `_do_import` →
    # [EN] prompt box → actually run once
    # [EN] ingest); "did clicking it actually start a run" can only be proven on a real machine, so it
    # [EN] belongs to the GUI group.
    'verify_ingest_duplicate',
    # ★ 报错/关键信息进右侧对话（2026-10-07 第十二轮）：用户「开卷摄取的时候
    #   如果有报错以及AI回复的关键信息 则请将其放到右侧AI优化对话的回复里
    #   否则可能看不见」。真机段要真的开一轮摄取、并从 `llm._emit` 注入一次
    #   真失败事件去看右侧气泡，所以归 GUI 组。
    # [EN] ★ Errors/key info go into the right-side conversation (2026-10-07 round twelve): user "when
    # [EN] opening-volume ingest,
    # [EN] if there are errors as well as key info from the AI reply, then please put them into the replies
    # [EN] of the right-side AI optimization conversation,
    # [EN] otherwise they may be invisible". The real-machine segment must actually run an ingest round,
    # [EN] and inject a
    # [EN] real failure event from `llm._emit` to look at the right-side bubble, so it belongs to the GUI
    # [EN] group.
    'verify_ingest_chat_mirror', 'verify_llm_caps',
    'verify_llm_first_run', 'verify_main_flags', 'verify_main_screen',
    'verify_manual_images', 'verify_md_render', 'verify_minimap',
    # ★ 编辑框保存后**关两层**（2026-10-14，用户：剧组 Agents / AI模型配置 的编辑框
    #   点了保存要退出当前对话框）：真机量 `open_dialogs` 层数 ⇒ 归 GUI 组。
    #   ⚠ 之前漏登记了（文件在盘上、组表里没有）→ 整套回归一启动就报错退出；
    #     这里补上。
    # [EN] ★ Editor closes BOTH layers on Save (2026-10-14): real-machine `open_dialogs` count ⇒
    # [EN] GUI group. Was previously unregistered (file on disk, missing from the table) → the whole
    # [EN] regression errored out at startup; added here.
    'verify_save_close',
    # ★★ 左下角「系统」面板里 token 用量是**活的** + 「导演 · 未启动」那一行去掉
    #   （2026-10-12）：用户「左下角的系统的Token预算左侧的数字要实时更新
    #   然后导演这一样可以先去掉 没有特别的意义」。
    #   A/B 两组是纯逻辑（可以 `--logic-only` 快跑，反例法就靠它），
    #   但 C/D 两组要**真起窗口**（屏幕上那一格到底有没有跟着账本走、
    #   「导演 · 未启动」在不在），所以整支归 GUI 组。
    #   ⚠ 它往**内存账本**里塞假账（不落库）、项目落在系统临时区
    #     ⇒ 不脏用户的 `usage.db` 与 Projects。
    # [EN] ★★ The token usage in the bottom-left "System" panel is **live** + the row
    # [EN] "导演 · 未启动" is gone (2026-10-12): user "the number to the left of Token budget in the
    # [EN] bottom-left system panel must update in real time; and the director row can go for now, it
    # [EN] has no particular meaning".
    # [EN] Groups A/B are pure logic (runnable fast with `--logic-only`, which the counterexample
    # [EN] method relies on), but groups C/D need a **real window** (does that cell on screen follow
    # [EN] the ledger, is "导演 · 未启动" present), so the whole script belongs to the GUI group.
    # [EN] ⚠ It pushes fake entries into the **in-memory ledger** (not persisted) and puts the project
    # [EN] in the system temp area ⇒ it does not dirty the user's `usage.db` or Projects.
    'verify_budget_live',
    # ★ 对话框"真打开" + 高度受控（2026-10-10）：每个**不需要夹具**的对话框
    #   都要真的开得开，而且 `content.height` 不能是 None（`mk_dialog` 从 content
    #   读尺寸，读不到就被 `expand=True` 拉满屏 —— 用户报的「网址对话框太高了」）。
    #   要起窗口 ⇒ GUI 组。
    # [EN] ★ Dialogs "actually open" + height is controlled (2026-10-10): every dialog that **does not need
    # [EN] a fixture**
    # [EN] must actually be openable, and `content.height` must not be None (`mk_dialog` reads the size
    # [EN] from content,
    # [EN] and if it can't read it, it gets stretched full-screen by `expand=True` — the "URL dialog is too
    # [EN] tall" the user reported).
    # [EN] It needs to create a window ⇒ GUI group.
    'verify_dialog_heights',
    # ★★ 拾卷「删除小说」确认框：**高度** + **手打书名那个框默认就得看得见**
    #   （2026-10-14，用户点名的这一条）：
    #     「拾卷的删除小说对话框 高度稍微高一些 把输入小说名字的文本框默认漏出来」
    #   改之前它是**一个像素都看不见**的（不是"有点挤"）：内容区声明 280 只渲染出
    #   186，五行说明自然高 222 ⇒ 滚 35px，而手打框排在最后一行。用户看到的是
    #   "确认按钮是灰的、可输入框在哪" —— 整个框像卡住了。
    #   这条必须**真机**（要真点垃圾桶弹出那个框、真读控件树、真截图数像素），
    #   所以归 GUI 组。
    # [EN] ★★ Pickup's "delete novel" confirmation: **height** + **the type-the-name box must be
    # [EN] visible by default** (2026-10-14, the item the user named):
    # [EN] "make the delete-novel dialog in Pickup a bit taller, so the text box for typing the novel
    # [EN] name shows by default".
    # [EN] Before the fix it was **not visible at all** (not merely "cramped"): the content area
    # [EN] declares 280 but renders only 186, the five explanation lines are naturally 222 => it
    # [EN] scrolls 35px, and the type box is the last row. What the user saw was "the confirm button
    # [EN] is grey but where's the input?" -- the whole dialog looked stuck.
    # [EN] This must be **real machine** (really click the trash can, really read the control tree,
    # [EN] really screenshot and count pixels), so it goes to the GUI group.
    'verify_confirm_dialog',
    # ★ 用量对话框的「×」与「删掉一个项目」（2026-10-10）：用户原话
    #   「LLM用量对话框右上角加一个关闭按钮 最左边一列的内容允许删除」。
    #   要真开窗口、真点回调（"×"在不在**标题那一行**、点垃圾桶**先不先问**、
    #   点确认之后库里和界面上那一行是不是都没了），所以归 GUI 组。
    #   它把台账库指到临时文件（`U.db_path` 临时改指向）⇒ **不碰用户的 usage.db**。
    # [EN] ★ The usage dialog's "×" and "delete a project" (2026-10-10): user's exact words
    # [EN] "Add a close button at the top right of the LLM usage dialog; the contents of the leftmost
    # [EN] column should be deletable".
    # [EN] It needs to actually open a window and actually click callbacks (whether "×" is on the **title
    # [EN] row**, whether clicking the trash can **asks first** or not,
    # [EN] whether after confirming, that row disappears from both the database and the UI), so it belongs
    # [EN] to the GUI group.
    # [EN] It points the ledger DB to a temp file (`U.db_path` temporarily redirected) ⇒ **does not touch
    # [EN] the user's usage.db**.
    'verify_usage_delete',
    'verify_model_probe', 'verify_opacity', 'verify_optimize_review',
    'verify_output_lang', 'verify_portraits', 'verify_repair_writeback',
    'verify_resume_manage', 'verify_run_control',
    # ★★ **起笔的启动守卫**（2026-10-12）：用户「连续点了两次起笔，结果就同时有两个
    #   推演过程在进行」+「点了起笔之后感觉没反应了一段时间」+「引入超时机制……
    #   两个里只留一个，而不是两个都用」。
    #   它**要起窗口**（走真实点击路径，把装配打桩成"慢的 / 卡住的 / 失败的"三种），
    #   所以归真机组，不归逻辑组。
    # [EN] ★★ **The launch guard for start-writing** (2026-10-12): user "I clicked start-writing twice
    # [EN] and two simulations ended up running at the same time" + "after clicking nothing happened for a
    # [EN] while" + "introduce a timeout ... keep one of the two, not both".
    # [EN] It **opens a window** (real click path, with assembly stubbed into three shapes: slow / stuck /
    # [EN] failing), so it belongs to the real-machine group, not the logic group.
    'verify_start_guard',
    # ★ `verify_resume_menu`（拾卷菜单）又回到这儿了：它当时被挪进 `ALONE`
    #   是因为"清共享目录"，而现在改用**私有临时目录**、不清任何共享的东西
    #   （详见 `ALONE` 字典末尾那段注释）。
    # [EN] ★ `verify_resume_menu` (resume-volume menu) is back here again: it was moved into `ALONE`
    # [EN] at the time because of "clearing the shared directory", but now it uses a **private temp
    # [EN] directory** and does not clear anything shared
    # [EN] (see the comment at the end of the `ALONE` dict for details).
    'verify_resume_menu', 'verify_run_modes', 'verify_run_status_bar',
    'verify_script_output', 'verify_scrollbars', 'verify_start_sync',
    # ⚠ `verify_story_depth` **不在这里** —— 它真起一轮推演读中栏控件树，
    #   并行不稳（回归器自己报过），已经挪进 `ALONE`。
    # [EN] ⚠ `verify_story_depth` **is not here** — it actually starts an inference round and reads the
    # [EN] center-column widget tree,
    # [EN] which is unstable under parallelism (the regressor itself reported this), so it has been moved
    # [EN] into `ALONE`.
    'verify_story_flow', 'verify_style_help',
    # 剧组（2026-10-07）：真机段要起界面（右栏「剧组」面板），所以归 GUI
    # [EN] Troupe (2026-10-07): the real-machine segment must bring up the UI (the "Troupe" panel in the
    # [EN] right column), so it belongs to GUI
    'verify_crew',
    # ★ 排练 · 中栏白名单 · 剧组状态小消息 · 当天这一章（2026-10-07 第三轮）：
    #   真机段要起界面并读**中栏控件树**（"中栏里到底出现了什么"只在这一层
    #   量得到），所以归 GUI 组。
    # [EN] ★ Rehearsal · center-column whitelist · troupe status small messages · today's chapter
    # [EN] (2026-10-07 round three):
    # [EN] the real-machine segment must bring up the UI and read the **center-column widget tree** ("what
    # [EN] actually appears in the center column" can only be
    # [EN] measured at this layer), so it belongs to the GUI group.
    'verify_crew_stage',
    # ★ 剧组面板「谁在干活」高亮（2026-10-08）：用户原话
    #   「右侧的剧组成员 谁在干活请高亮显示 等不干活了再恢复普通样式」。
    #   逻辑段验"出工状态真被播报、且是在 await 之前报的、收工报的是真状态"；
    #   **真机段要起窗口、真的叫一次出工、再量屏幕上的暖金像素**
    #   （"高亮到底画出来没有、干完有没有真的复原"只有像素能证），所以归 GUI 组。
    # [EN] ★ Troupe panel "who is working" highlight (2026-10-08): user's exact words
    # [EN] "For the troupe members on the right, please highlight whoever is working, and restore the
    # [EN] normal style once they stop working".
    # [EN] The logic segment verifies "the working state is really broadcast, and it is reported before
    # [EN] await, and the stop-work report is the real state";
    # [EN] **the real-machine segment must bring up the window, actually call the start-work once, and then
    # [EN] measure the warm gold pixels on the screen**
    # [EN] ("whether the highlight is actually drawn, and whether it truly restores after finishing" can
    # [EN] only be proven by pixels), so it belongs to the GUI group.
    'verify_crew_highlight',
    # ★★★ 右栏「在场人物」「剧情」两块**真的有内容**（2026-10-17，用户点名）：
    #   「运行窗口右上角的在场任务和剧情现在一直没有任何信息显示
    #     把现在剧组这个Panel里的各个具体的演员 谁在表演的 全部移动到在场任务这里
    #     …剧情这个panel你也要加上」。
    #   归 GUI 组：真机段要**真起窗口**、在控件树里量"这两个面板真的挂在界面上"、
    #   并改真 `world.tension` 看面板跟着变 ——
    #   "句柄存了却没挂上去"这一种，只读源码查不出来（`E1` 就是守它的）。
    #   ⚠ 它给 `redirect_env_writes()` + 隔离项目根 + `MOCK_LLM=true`。
    # [EN] ★★★ The right column's "On-stage Characters" and "Plot" blocks **really have content**
    # [EN] (2026-10-17, named by the user): "the On-stage Tasks and Plot panels at the top right of the
    # [EN] run window never show any information now; move all the specific actors in the current Cast
    # [EN] panel over to On-stage Tasks ... the Plot panel needs content too".
    # [EN] Assigned to the GUI group: the real-machine section must **truly bring up the window**,
    # [EN] measure in the widget tree that "these two panels are really mounted on the screen", and change
    # [EN] the real `world.tension` to see the panel follow ——
    # [EN] the "handle stored but never mounted" kind cannot be found by reading source (`E1` guards it).
    # [EN] ⚠ It gives `redirect_env_writes()` + isolates the project root + `MOCK_LLM=true`.
    'verify_run_side_panels',
    # ★★★ 「剧组」那一栏**一屏能显示全部 Agent**（2026-10-17 用户点名）：
    #   「右侧的剧组这部分有办法调整下布局 让它所有Agents一次性显示出来吗？」
    #   归 GUI 组：真机段要**真起窗口**、量右栏的 `max_scroll_extent == 0`
    #   （用户诉求本身就是"不用滚"），再截图数屏幕上画出了几行、每行多高 ——
    #   "一屏放下没有"只读源码答不了。
    #   ⚠ 它给 `redirect_env_writes()` + 隔离项目根 + `MOCK_LLM=true`。
    #   ⚠ 判据里的 19 行 / 1129 高是**默认剧团 + 最大化窗口**的数字；用户把窗口
    #     拉小或自己加职位时，这组数字会跟着变，届时改这里的两处期望值。
    # [EN] ★★★ The "Cast" column **can show every Agent in one screen** (named by the user 2026-10-17):
    # [EN] "Is there a way to adjust the layout of the Cast section on the right so that all Agents are
    # [EN] displayed at once?"
    # [EN] Assigned to the GUI group: the real-machine section must **truly bring up the window** and
    # [EN] measure the right column's `max_scroll_extent == 0` (the user's request *is* "no scrolling"),
    # [EN] then screenshot and count how many rows were drawn and how tall each is --
    # [EN] "does it fit in one screen" cannot be answered by reading source.
    # [EN] ⚠ It gives `redirect_env_writes()` + isolates the project root + `MOCK_LLM=true`.
    # [EN] ⚠ The 19 rows / 1129 height in the criteria are **default troupe + maximized window** numbers;
    # [EN] if the user shrinks the window or adds positions these change, and those two expectations
    # [EN] must be updated here.
    'verify_crew_density',
    # ★★★ **「每 N 天停一次」真的成立**（2026-10-17 用户点名）：
    #   「一天暂停一次改成3天暂停一次，总共循环10天」。
    #   `STORY_DAY_EVERY_DAYS`（几天一次）与 `CHECKPOINT_PAUSE`（到点停不停）是**两个**设置，
    #   而后者此前**只存在于 `.env`**、界面上没有任何入口 ⇒ 改间隔不会真的停。
    #   这一支守三件事：① 开关在界面上（真控件、初值同源、保存写回）；
    #   ② `_tick` 里两个配置各司其职（**钉 `story_day` 那一支**，不是 open 的同款写法）；
    #   ③ 用户拍板的搭配（倍率 2 / 一拍 80 / 每 3 天 / 共 10 天）没被悄悄改回去。
    #   ⚠ 真机段会**点保存**（`redirect_env_writes()` + 关掉三个 `*_AUTOSTART`，
    #     否则会把三座外部服务真的拉起来）。
    # [EN] ★★★ **"Pause once every N days" really holds** (named by the user 2026-10-17):
    # [EN] "change from pausing once a day to once every 3 days, 10 days in total".
    # [EN] `STORY_DAY_EVERY_DAYS` (every how many days) and `CHECKPOINT_PAUSE` (stop or not) are **two**
    # [EN] settings, and the latter previously **existed only in `.env`** with no UI at all => changing the
    # [EN] interval never actually paused. This guards three things: (1) the switch is on screen (a real
    # [EN] control, value from CFG, written back on save); (2) in `_tick` the two settings do their own
    # [EN] jobs (**pinned to the `story_day` branch**, not the lookalike in `open`); (3) the combination the
    # [EN] user settled on (ratio 2 / beat 80 / every 3 days / 10 days) has not been quietly changed back.
    # [EN] ⚠ The real-machine section **clicks Save** (`redirect_env_writes()` plus switching off the three
    # [EN] `*_AUTOSTART`, otherwise it would really launch the three external services).
    'verify_pause_interval',
    # ★ **剧本审读**（2026-10-08）：用户原话
    #   「你看是否有**独立的Agent** 而不是导演在盯着演员说的每一句话 没有就做一个
    #    **在演员真的说出来之前**，把新生成的话放到已经出现的话里过一遍…
    #    **不是就不要放出来**」。
    #   逻辑段验“闸门挂在哪一行、什么时候放行、什么时候拦”（AST + 真跑一拍）；
    #   **真机段要起窗口**（天机「运行」页那五个控件、剧组面板里那一行）
    #   —— “有没有地方改、面板上有没有这个人”只能在控件树里量，所以归 GUI 组。
    # [EN] ★ **Script review** (2026-10-08): user's exact words
    # [EN] "See whether there is an **independent Agent** rather than the director watching every sentence
    # [EN] the actor says. If not, make one
    # [EN] **before the actor actually says it**, run the newly generated line through the lines that have
    # [EN] already appeared...
    # [EN] **if not, then don't let it out**".
    # [EN] The logic segment verifies "which line the gate is hung on, when it lets through, when it
    # [EN] blocks" (AST + actually running one beat);
    # [EN] **the real-machine segment must bring up the window** (the five controls on Tianji's "Run" page,
    # [EN] that row in the troupe panel)
    # [EN] —— "is there anywhere to change it, is this person on the panel" can only be measured in the
    # [EN] widget tree, so it belongs to the GUI group.
    'verify_script_review',
    # ★ 定时落盘 + 左下角那颗「自动落盘」小胶囊（2026-10-08）：用户原话    #   「我点暂停的时候以及平时也有可能随时关闭软件 所以后台还需要一个定时器
    #    实现定时落盘 比如没30秒落盘一次（…在状态标签的右边加一个状态条…）」。
    #   逻辑段验落盘内容/滚动覆盖/失败不抛/间隔现读/0=真关；
    #   **真机段要起窗口量那两颗胶囊的像素与位置**（"偏蓝底、绿字、在右边、
    #    字号一致"只有像素与控件属性证得了），所以归 GUI 组。
    # [EN] ★ Timed flush to disk + that little "auto flush" capsule at the bottom left (2026-10-08): user's
    # [EN] exact words # "when I click pause, and also normally I might close the software at any time, so
    # [EN] the backend also needs a timer
    # [EN] to implement timed flush to disk, e.g. flush once every 30 seconds (...add a status bar to the
    # [EN] right of the status label...)".
    # [EN] The logic segment verifies flush content/rolling overwrite/failure does not throw/interval is
    # [EN] read live/0 = truly off;
    # [EN] **the real-machine segment must bring up the window and measure the pixels and positions of
    # [EN] those two capsules** ("bluish background, green text, on the right,
    # [EN] consistent font size" can only be proven by pixels and widget properties), so it belongs to the
    # [EN] GUI group.
    'verify_autosave',
    # ★ **日志查看对话框**（2026-10-08）：用户原话
    #   「在主界面右上角找个合适的位置放一个按钮 叫做日志按钮，点了之后可以在
    #    一个新的对话框（较大）查看整个后台运行过程中的详细日志（动态刷新，
    #    基于日志文件且尽可能丰富，而且需要有一定的格式，且支持使用关键字搜索）
    #    最好分页（分页可以每一个的日志量多一些，比如200条1页，500条1页）」。
    #   六条（入口 / 基于日志文件 / 格式 / 搜索 / 分页 / 动态刷新）**都要真机**：
    #   "点开有没有、渲染成什么颜色、翻页换不换内容、新行会不会自己冒出来"
    #   只有起真窗口才量得到，所以归 GUI 组。
    # [EN] ★ **Log viewer dialog** (2026-10-08): user's exact words
    # [EN] "Find a suitable spot at the top right of the main UI and put a button called Log button; after
    # [EN] clicking it you can, in
    # [EN] a new dialog (larger), view the detailed logs of the entire backend runtime (dynamic refresh,
    # [EN] based on the log file and as rich as possible, and it needs a certain format, and supports
    # [EN] keyword search)
    # [EN] preferably paginated (pagination can have a larger amount per page, e.g. 200 entries per page,
    # [EN] 500 entries per page)".
    # [EN] Six items (entry / based on log file / format / search / pagination / dynamic refresh) **all
    # [EN] require a real machine**:
    # [EN] "does it show when opened, what color is it rendered as, does paging change the content, do new
    # [EN] lines appear by themselves"
    # [EN] can only be measured by bringing up a real window, so it belongs to the GUI group.
    'verify_log_dialog',
    # ★ 开卷打磨 Agent（2026-10-07）：沙盒 / 工具 / 历史 / 自省 / 动态生成工具
    #   在逻辑段；**真机段要真的走一遍开卷**（向导 → 同意门 → AI 对话 → 收工），
    #   量"项目侧与引用侧写的是不是同一份文本" —— 那一层只有真机能证，所以归 GUI 组。
    # [EN] ★ Start Writing polishing Agent (2026-10-07): sandbox / tools / history / introspection /
    # [EN] dynamically generated tools
    # [EN] are in the logic segment; **the real-machine segment must actually walk through Start Writing
    # [EN] once** (wizard → consent gate → AI conversation → finish work),
    # [EN] The criterion "whether the project side and the reference side write the same text" — that layer
    # [EN] can only be proven on a real machine, so it goes to the GUI group.
    'verify_polish_agent',
    # ★ 拆书（2026-10-07 第六轮）：逻辑段验方法论 / 分层取样 / 四道工序 / 技能包 /
    #   **按类型匹配**（同题材两种叫法要配上）/ 三人小组拿完整版；
    #   **真机段要真的打开开始菜单与拆书对话框**（"四个问题在不在"只有真机能证），
    #   所以归 GUI 组。
    # [EN] ★ Book splitting (2026-10-07 round six): logical-segment verification methodology / layered
    # [EN] sampling / four process steps / skill pack /
    # [EN] **Match by type** (two names for the same genre must match) / the three-person team gets the
    # [EN] full version;
    # [EN] **The real-machine segment must actually open the start menu and the book-splitting dialog**
    # [EN] ("are the four questions there" can only be proven on a real machine),
    # [EN] so it goes to the GUI group.
    'verify_booklab',
    # ★ 拆书的**三种输入 + 只拆一段**，以及**各职位按需取用技能包**（2026-10-10）。
    #   用户原话：「拆书 我希望同时支持传入文件（PDF docx md html txt等文档格式）
    #   或者包含这些类型文件的文件夹 或者一个网址 里面是书籍的索引网页……
    #   拆书不需要全拆 最后支持拆哪些页（按照1-10,15-21这样输入，或者前多少页，
    #   或者哪些章节）」＋「拆书功能落地之后 你还得修改相关Agent，
    #   让他们在需要的时候选择合适的SKILL用起来」。
    #   归 LOGIC：纯逻辑 + 一个**本地** HTTP 服务（127.0.0.1，随机端口），
    #   不联网、不弹窗。反例法：`developers/mutate_booklab_sources.py`（34 组）。
    # [EN] ★ Book splitting's **three kinds of input + split only one segment**, and **each role takes
    # [EN] skill packs on demand** (2026-10-10).
    # [EN] User's original words: "Book splitting I hope to support passing in files (PDF docx md html txt
    # [EN] and other document formats)
    # [EN] or a folder containing files of these types, or a URL, inside which is a book index page...
    # [EN] Book splitting does not need to split everything; in the end support choosing which pages to
    # [EN] split (input like 1-10,15-21, or the first N pages,
    # [EN] or which chapters)" + "after the book-splitting feature lands, you also have to modify the
    # [EN] related Agents,
    # [EN] so that they pick and use the appropriate SKILL when needed".
    # [EN] Goes to LOGIC: pure logic + one **local** HTTP service (127.0.0.1, random port),
    # [EN] no network, no popups. Counterexample method: `developers/mutate_booklab_sources.py` (34
    # [EN] groups).
    # ★ 岔路口面板（2026-10-07 第十一轮）：单选候选 / 自定义走向 / 5 分钟倒计时 /
    #   顶部故事发展。真机段要起界面并**量像素**（单选钮与那个文本框
    #   "画出来没有"只有像素能证），所以归 GUI 组。
    # [EN] ★ Fork-in-the-road panel (2026-10-07 round eleven): single-choice candidates / custom direction
    # [EN] / 5-minute countdown /
    # [EN] story development at the top. The real-machine segment must bring up the UI and **measure
    # [EN] pixels** (the radio buttons and that text box
    # [EN] "whether it was drawn or not" can only be proven by pixels), so it goes to the GUI group.
    'verify_branch_dialog',
    # ★ 开卷 AI 优化的**轮数上限**与**强制停止**（2026-10-08）：用户原话
    #   「开卷 AI 优化 要有轮数上限且有地方配置 而且可以点击某个按钮强制停止」。
    #   逻辑段验"这一项真的是配置项、产品真的读它、上限判定是 >=、出口没被一起关"；
    #   **真机段必须真跑一遍开卷**（进 AI 优化阶段 → 打断正在跑的那一轮 →
    #   跑到上限 → 收工），"点下去到底有没有打断"只有真机能证，所以归 GUI 组。
    # [EN] ★ Open-book AI optimization's **round cap** and **force stop** (2026-10-08): user's original
    # [EN] words
    # [EN] "Open-book AI optimization must have a round cap and a place to configure it, and there must be
    # [EN] a button that can be clicked to force stop".
    # [EN] The logical segment verifies "this item really is a config item, the product really reads it,
    # [EN] the cap check is >=, the exit was not closed along with it";
    # [EN] **the real-machine segment must actually run one open-book round** (enter the AI optimization
    # [EN] stage → interrupt the currently running round →
    # [EN] run to the cap → finish up); "whether clicking actually interrupts" can only be proven on a real
    # [EN] machine, so it goes to the GUI group.
    'verify_ingest_rounds',
    # ★ 「作者说『修复4个问题 / 所有问题 不要问我』要听得懂」（2026-10-12 凌晨）：
    #   用户原话「我说修复4个问题 但是它不知道我什么意思 而且反复让我修改
    #   我让它修复所有自查问题 不要问我 也不行 必须一轮一问」。
    #   A 组是**纯解析**（零 LLM 零 IO），B 组用替身模型验"硬拦 + 编号下达"，
    #   C 组**真跑一遍摄取**到 AI 优化阶段、把这句话打进去、看对话栏有没有回应
    #   —— 所以归 GUI 组。
    # [EN] ★ "The author saying 'fix the 4 problems / all problems, don't ask me' must be understood"
    # [EN] (2026-10-12 early morning): the user's words were "I said fix the 4 problems but it doesn't
    # [EN] understand what I mean, and it keeps making me revise; I told it to fix all the self-check
    # [EN] problems and don't ask me, that doesn't work either -- it insists on one question per round".
    # [EN] Group A is **pure parsing** (no LLM, no IO), group B uses a stand-in model to verify the
    # [EN] "hard block + numbered hand-down", and group C **actually runs ingestion** to the
    # [EN] AI-refinement stage, types that sentence in, and checks whether the chat pane responds --
    # [EN] so it goes to the GUI group.
    'verify_polish_intent',
    # ★ 窗口图标归属（2026-10-07 第十二轮）：用户报「explorer.exe 的图标也被
    #   替换了」—— 查出 `find_app_hwnd` 的兜底会命中**别人的窗口**，而下游
    #   `SetClassLongPtrW` 改的是**窗口类**图标（波及那个进程所有同类窗口）。
    #   判据要**起真窗口**（量 `find_app_hwnd` 是否还找得到自己的窗口、
    #   全机窗口里被接受的有没有别人），所以归 GUI 组。
    # [EN] ★ Window icon attribution (2026-10-07 round twelve): the user reported "explorer.exe's icon was
    # [EN] also
    # [EN] replaced" — found that the fallback of `find_app_hwnd` hits **someone else's window**, and
    # [EN] downstream
    # [EN] `SetClassLongPtrW` changes the **window class** icon (affecting all windows of the same class in
    # [EN] that process).
    # [EN] The criterion must **bring up a real window** (measure whether `find_app_hwnd` can still find
    # [EN] its own window,
    # [EN] and whether any accepted one among all machine windows belongs to someone else), so it goes to
    # [EN] the GUI group.
    'verify_window_icon_target',
    # ★ 左栏「风格控制」那几条（2026-10-08）：用户原话
    #   「左下角的**风格控制**部分 每个参数的数值**不显示出来** 正常应该是
    #     **中间线条显示类似进度条的样式** 右侧横线是**数值 5/10** 这样的
    #     **当值 最大值**的形式」。
    #   逻辑段验填值规则 / 坏值降级 / 清单与配置表逐项对齐；
    #   **真机段要起窗口**（量屏幕上那 7 个「N/10」、量进度条的标记色像素、
    #    还要**真开跑一轮**验证"改配置后它自己会跟上"），所以归 GUI 组。
    # [EN] ★ The "style control" items in the left column (2026-10-08): user's original words
    # [EN] "The **style control** section at the bottom left: each parameter's value **is not displayed**;
    # [EN] normally it should be
    # [EN] **the middle line shows a progress-bar-like style**, the right horizontal line is **a value like
    # [EN] 5/10** in the form
    # [EN] **current value / max value**".
    # [EN] The logical segment verifies the value-filling rules / bad-value downgrade / item-by-item
    # [EN] alignment between the list and the config table;
    # [EN] **the real-machine segment must bring up the window** (measure those 7 "N/10" on screen, measure
    # [EN] the marker-color pixels of the progress bars,
    # [EN] and **actually run one round** to verify "after changing the config it catches up by itself"),
    # [EN] so it goes to the GUI group.
    'verify_style_bar',
    # ★ 天机的「常规」页签（2026-10-08）：用户原话
    #   「全局设置里在 **LLM 接入左边加一个常规 Tab**，里面包含一些常规设置项，
    #    比如**把日志的设置项移动到这里**，再新增一个**项目根目录**配置项
    #    放到这里（放到开始，确认必须重启才起作用）」。
    #   逻辑段验页签顺序 / `TAB_LLM` 指得对不对 / 日志块搬过来了 / 项的性质；
    #   **真机段要起窗口 + 点保存**（"改完是不是立刻生效"只有真机能证：
    #    判据真的把根从空目录换到有书的目录，再看界面上的字有没有跟着变），
    #   所以归 GUI 组。
    # ★ 2026-10-10：Hy3 / 单窗口 / 场景可画地图+能拍 / 原文导出 / 外部借鉴措辞 / 连续指标
    # [EN] ★ Tianji's "General" tab (2026-10-08): user's original words
    # [EN] "In global settings, **add a General Tab to the left of LLM access**, containing some general
    # [EN] settings items,
    # [EN] for example **move the log settings items here**, and add a new **project root directory**
    # [EN] config item
    # [EN] placed here (place it at the start; confirm it only takes effect after a restart)".
    # [EN] The logical segment verifies the tab order / whether `TAB_LLM` points to the right thing /
    # [EN] whether the log block was moved over / the nature of the items;
    # [EN] **the real-machine segment must bring up the window + click save** ("does the change take effect
    # [EN] immediately" can only be proven on a real machine:
    # [EN] the criterion really switches the root from an empty directory to a directory with books, then
    # [EN] checks whether the text on the UI changes accordingly),
    # [EN] so it goes to the GUI group.
    # [EN] ★ 2026-10-10: Hy3 / single window / scene can draw a map + can shoot / original text export /
    # [EN] external borrowing wording / continuous metrics
    'verify_regular_tab',
    # ★ 创作服务（MuMuAINovel）接入（2026-10-09）：用户原话
    #   「你看下小说作家Agent是否可以调用 MuMuAINovel 来写小说」
    #   「让 MuMuAINovel 的相关配置也进入到天机…一定要注明来自 MuMuAINovel，
    #     并且在合适的地方写上对方的项目地址」。
    #   逻辑段验 SPEC 旋钮 / 页签 / 保存分支 / 桥接层分层与写盘保险丝 / 目录形态；
    #   **真机段要起窗口**（打开天机看那一页在不在、写没写出处与地址，
    #    还要真的点一次保存看两个 `.env` 有没有各归各位）；
    #   D 组是**真调那个外部服务写一章**（服务没起就如实报 SKIP），
    #    所以归 GUI 组。
    # [EN] ★ Creation service (MuMuAINovel) integration (2026-10-09): user's original words
    # [EN] "See whether the novelist Agent can call MuMuAINovel to write novels"
    # [EN] "Let MuMuAINovel's related config also go into Tianji... be sure to note that it comes from
    # [EN] MuMuAINovel,
    # [EN] and write the other party's project address in an appropriate place".
    # [EN] The logical segment verifies the SPEC knobs / tabs / save branches / bridging-layer layering and
    # [EN] disk-write fuse / directory shape;
    # [EN] **the real-machine segment must bring up the window** (open Tianji and see whether that page is
    # [EN] there, whether the source and address were written out,
    # [EN] and also actually click save once to see whether the two `.env` files each go to their proper
    # [EN] place);
    # [EN] group D is **actually calling that external service to write one chapter** (if the service is
    # [EN] not up, report SKIP truthfully),
    # [EN] so it goes to the GUI group.
    'verify_mumu_service',
    # ★ 全局消息**跨启动保留**（2026-10-09）：用户原话
    #   「系统消息应该是跨启动保留，除非我主动删除，否则不能够上次运行
    #     过程中的消息关闭再启动就没了」。
    #   要起窗口（真发一条消息 → 换一个新实例当"重启" → 看还在不在），
    #   所以归 GUI 组。
    # [EN] ★ Global messages **persist across launches** (2026-10-09): user's original words
    # [EN] "System messages should persist across launches; unless I actively delete them, they cannot be
    # [EN] gone after closing and restarting
    # [EN] from the messages during the previous run".
    # [EN] Must bring up the window (really send a message → swap in a new instance as a "restart" → see
    # [EN] whether it is still there),
    # [EN] so it goes to the GUI group.
    'verify_msg_persist',
    # ★ 帮助面板**左栏滚动条**（2026-10-09）：用户原话
    #   「帮助窗口左边的下拉滚动条又没了」。要起窗口 + 像素取证
    #   （量面板有没有被裁、条有没有真画出来），所以归 GUI 组。
    # [EN] ★ Help panel **left-column scrollbar** (2026-10-09): user's original words
    # [EN] "The drop-down scrollbar on the left side of the help window is gone again". Must bring up the
    # [EN] window + gather pixel evidence
    # [EN] (measure whether the panel is clipped, whether the bar is really drawn), so it goes to the GUI
    # [EN] group.
    'verify_help_scrollbar',
    'verify_ui_english', 'verify_window_max', 'verify_wizard_choices',
    'verify_wizard_name',
    # ★ 界面字体 / 界面字号 / 命令行开关（2026-10-11，用户点名的三件事）：
    #   A 组是纯逻辑（默认字体解析、选项过滤、缩放从基准算、SPEC 默认值），
    #   B 组要**真开窗口**：查主题字体、开「天机 · 界面外观」页签、
    #   按标记色量「发送」按钮真的画在下半屏、量 130% 时墨迹真的变宽。
    #   ⇒ GUI 组。
    # [EN] ★ UI font / UI font size / command-bar switch (2026-10-11, three things the user named):
    # [EN] group A is pure logic (default font resolution, option filtering, scaling from the base,
    # [EN] SPEC default); group B must **open a real window**: check the theme font, open the
    # [EN] "Tianji · UI appearance" tab, use the marker color to measure that the "Send" button really is
    # [EN] painted in the lower half, and measure that the ink really gets wider at 130%. ⇒ GUI group.
    'verify_font_settings',
    # ★ 叙事窗口的分页与时间戳（2026-10-11）：真启窗口 → **GUI 组**。
    # [EN] ★ Narrative-window paging and timestamps (2026-10-11): really opens a window → **GUI group**.
    'verify_narr_window',
    # ★ 运行页面板搬家 + 点标题跳设置（2026-10-11）：真启窗口量栏位顺序、
    #   真开书斋拖滑杆 → 所以是 **GUI 组**（并行会抢窗口）。
    # [EN] ★ Run-page panel relocation + title-click jumps to settings (2026-10-11): it really opens a
    # [EN] window to measure the column order and really opens the study to drag a slider → **GUI group**
    # [EN] (running in parallel would fight over the window).
    'verify_run_panel_nav',
    # ★ 开卷向导第 4 步（剧组 Agents）的车道（2026-10-11）：要真开窗口量像素
    #   → **GUI 组**（并行会抢窗口）。
    # [EN] ★ The lane of wizard step 4 (Crew Agents) (2026-10-11): it really opens a window to
    # [EN] measure pixels → **GUI group** (running in parallel would fight over the window).
    'verify_wizard_agent_lane',
]

# 必须独占：并行会互相干扰。原因逐条写在这里，别只写"不并行"。
# [EN] Must be exclusive: parallel runs interfere with each other. The reasons are written one by one
# [EN] here; don't just write "not parallel".
ALONE: dict[str, str] = {
    'verify_splash_boot':
        # ★ 2026-10-25 补登记。它**真的把整个程序启动一遍**（6 处 `ft.run`）、
        #   并且量的是**启动耗时**（splash 拉起三家服务要多久才放人进开始界面）。
        #   并行时既抢桌面、又让"秒数"这个量本身失去意义 ⇒ 必须独占。
        #   **不是"放宽判据"，这支本来就要求独占。**
        # [EN] ★ Registered 2026-10-25. It **actually boots the whole app** (6 `ft.run` calls) and
        # [EN] measures **startup time** (how long the splash takes to bring up three services before
        # [EN] letting the user in). In parallel it both grabs the desktop and makes the "seconds"
        # [EN] measurement meaningless => it inherently requires exclusivity.
        '会真的把整个程序启动一遍，而且量的是启动耗时 —— 并行既抢桌面、又让秒数失去意义',
    'verify_agent_colwidth':
        # ★ 2026-10-14 新增（剧组表列宽那一轮）。它为了量"窄屏下也不横滚"会
        #   **真的把窗口缩到 1180×760 再放回去** —— 并行时别的真机脚本量到的
        #   就是被它改过的窗口几何（`book_geometry` / `tianji_geometry` 都从
        #   `page` 推），那一批判据会集体假红。
        #   另外它还要**往程序目录 `.ui_state/` 写列宽文件**（持久化那条），
        #   与别的脚本共用那一份也会串味。**不是"放宽判据"，这支本来就要求独占。**
        # [EN] ★ Added 2026-10-14 (the crew-table column-width round). To measure "no h-scroll on a
        # [EN] narrow screen either" it **really shrinks the window to 1180x760 and puts it back** --
        # [EN] in parallel, other real-machine scripts measure the window geometry it just changed
        # [EN] (`book_geometry` / `tianji_geometry` are both derived from `page`), and that whole batch
        # [EN] of criteria false-reds together. It also **writes the column-width file into the program
        # [EN] directory `.ui_state/`** (the persistence item), which would cross-contaminate with
        # [EN] other scripts sharing that one copy. **This is not "loosening a criterion"; this one
        # [EN] inherently requires exclusivity.**
        '会真的缩放窗口（1180×760）再放回，且往程序目录 `.ui_state/` 写列宽文件'
        ' —— 并行时别的脚本量到的是被它改过的窗口几何',
    'verify_bilingual':
        # 2026-10-12 回归器报的「并行红、串行绿」（15/16 → 16/16）。
        # 它要**逐字读全项目 450+ 个 py 文件**并与 `.bak-bilingual` 比 AST 指纹，
        # 而并行的其它脚本（探针 / 反例法）会**当场改写产品文件再还原** ——
        # 正好在读的中间，指纹就"不一致"了（B2 也会数到半写完的注释块）。
        # 单跑 16/16 稳定绿。**不是"放宽判据"，是这支本来就要求独占。**
        # [EN] 2026-10-12 the regressor reported "red in parallel, green in serial" (15/16 -> 16/16).
        # [EN] It **reads 450+ py files across the project verbatim** and compares AST fingerprints with
        # [EN] `.bak-bilingual`, while other parallel scripts (probes / counterexample methods) **rewrite
        # [EN] product files in place and then restore them** -- right in the middle of that read the
        # [EN] fingerprints "mismatch" (and B2 counts half-written comment blocks).
        # [EN] Running it alone is a stable 16/16. **This is not loosening a criterion; this script
        # [EN] inherently requires exclusivity.**
        '逐字读全项目 450+ 个 py 文件并与 `.bak-bilingual` 比 AST 指纹，'
        '而并行的其它脚本（探针 / 反例法）会当场改写产品文件再还原 —— '
        '正好在读的中间，指纹就"不一致"了（单跑 16/16 稳定绿）',
    'verify_taskbar_icon':
        '按窗口标题 FindWindowW 找自己的 hwnd（并行时找到别人的窗口）'
        '＋故意重写共享图标产物',
    'verify_icon':
        '故意重写共享图标产物 assets/images/icon* 与 assets/app_icon.*',
    'verify_run_output_style':
        # 2026-10-07 回归器自己报的「并行红、串行绿」。它会**真起一轮推演**，
        # 然后往中栏推分隔符、按形状找它、涂色量像素 —— 并行时有别的真机脚本
        # 在抢 Flet 客户端与 CPU，中栏的控件树会在量之前被推演改掉（B3 那条）。
        # 单跑 33/33 稳定绿。**不是"放宽判据"，是这支本来就要求独占。**
        # [EN] 2026-10-07 the regressor itself reported "red in parallel, green in serial". It **really starts
        # [EN] one round of deduction**,
        # [EN] then pushes a separator into the middle column, finds it by shape, colors it and measures pixels
        # [EN] — during parallel runs there are other real-machine scripts
        # [EN] competing for the Flet client and CPU, and the middle column's widget tree gets changed by the
        # [EN] deduction before measurement (the B3 item).
        # [EN] Run alone, 33/33 stable green. **This is not "loosening the criterion"; this one inherently
        # [EN] requires exclusivity.**
        '真起一轮推演，量中栏控件的实时状态（并行时会被推演本身改掉）',
    'verify_story_depth':
        # 2026-10-07 回归器自己报的「并行红、串行绿」（2026-10-07 那一轮起出现，
        # 单跑连跑三次都是 53/53）。它同样**真起一轮推演**读中栏的控件树 ——
        # 与 `verify_run_output_style` 同一类：并行时中栏会在量之前被推演改掉。
        # ⚠ 它比 `run_output_style` 更敏感一点：2026-10-07 起中栏多了
        #   **阶段小消息与工作状态**（`▸ 剧组排练` / `· 美术 已交活`），
        #   条目数比过去多，时序窗口更窄。
        # [EN] 2026-10-07 the regressor itself reported "red in parallel, green in serial" (appeared starting
        # [EN] from the 2026-10-07 round;
        # [EN] run alone three times in a row all 53/53). It likewise **really starts one round of deduction**
        # [EN] to read the middle column's widget tree —
        # [EN] same category as `verify_run_output_style`: during parallel runs the middle column gets changed
        # [EN] by the deduction before measurement.
        # [EN] ⚠ It is a bit more sensitive than `run_output_style`: starting 2026-10-07 the middle column has
        # [EN] more
        # [EN] the item count is larger than before, and the timing window is narrower.
        '真起一轮推演读中栏控件树（并行时会被推演本身改掉）',
    # ⚠ `verify_resume_menu` **曾经**在这一组里，理由与现状都记在这儿 ——
    #   免得下次有人看到它"不独占也能跑"又把它挪回去（或者反过来，
    #   看到它红了却不知道为什么）：
    # [EN] ⚠ `verify_resume_menu` **used to** be in this group; the reason and current state are recorded
    # [EN] here ——
    # [EN] so that next time someone sees it "runs fine without exclusivity" they won't move it back (or
    # [EN] conversely,
    # [EN] see it red and not know why):
    #
    #   · 那时它借 `assets/screenshots/_proj` 当隔离目录，并且**一上来就清整层**；
    #     而那一层是几个脚本共用（`verify_opacity` / `verify_run_modes` 的夹具
    #     也在里面）→「清一个共享目录」天生不能并发，所以挪进 ALONE。
    #   · 但独占**也没治好**：并行阶段那些进程可能还占着文件，`safe_rmtree`
    #     的"删不掉就算了"把失败吞了 → `_proj` 留残留 → `scan_projects` 扫到 →
    #     「没项目时拾卷该灰掉」假红（2026-10-08 回归连红两次）。
    #   · 真正的修法是**换场地**：它现在用自己的私有临时目录
    #     （`tempfile.mkdtemp('nws_resumemenu_')`），不再清任何共享的东西
    #     → 独占的理由消失，已移回 GUI 组。
    # [EN] · Back then it borrowed `assets/screenshots/_proj` as an isolated directory, and **wiped the
    # [EN] whole level right from the start**;
    # [EN] and that level was shared by several scripts (the fixtures for `verify_opacity` /
    # [EN] `verify_run_modes`
    # [EN] were also in there) → "wiping a shared directory" inherently cannot be concurrent, so it was
    # [EN] moved into ALONE.
    # [EN] · But exclusivity **didn't cure it either**: during the parallel phase those processes might
    # [EN] still hold the files, and `safe_rmtree`
    # [EN] 's "if it can't be deleted, so be it" swallowed the failure → `_proj` leftovers →
    # [EN] `scan_projects` picks them up →
    # [EN] "the volume should grey out when there are no projects" false red (2026-10-08 regression went
    # [EN] red twice in a row).
    # [EN] · The real fix is **changing venue**: it now uses its own private temp directory
    # [EN] (`tempfile.mkdtemp('nws_resumemenu_')`), no longer wiping anything shared
    # [EN] → the reason for exclusivity disappears, moved back to the GUI group.
    'verify_sim_depth':
        # 2026-10-08 回归器报「并行红、串行绿」（36/37 → 37/37）。
        # ⚠ **不是判据烂，是这一支天生要求独占**：它测的东西就是**耗时** ——
        #   "两个 agent 并发决策比串行省下多少"。负载对耗时的**绝对值**影响很大，
        #   而它已经尽力了：脚本自己那段注释写着，原来的绝对阈值
        #   （`concurrent < 0.55`）在并行回归里被调度开销吃掉 0.19s 裕度后红过，
        #   后来改成**差分**（省下 ≈ 一次调用的时间）+ 把夹具延时抬到 0.60s，
        #   就是为了抗噪。2026-10-08 又红，是因为这一轮往 GUI 组加了两个真机
        #   判据（`verify_style_bar` / `verify_regular_tab`），并行负载更高了 ——
        #   0.60s 的信号又被噪声盖住。
        #   再往下压噪声只能继续抬延时，那是拿"测试跑得更慢"换"判据更准"，
        #   不如直接让它独占：它只跑 5 秒。
        # [EN] 2026-10-08 the regressor reported "red in parallel, green in serial" (36/37 → 37/37).
        # [EN] ⚠ **It's not that the criterion is bad, it's that this branch inherently requires exclusivity**:
        # [EN] what it tests is precisely **time cost** ——
        # [EN] "how much two agents deciding concurrently save versus serial". Load heavily affects the
        # [EN] **absolute value** of the time cost,
        # [EN] and it already tried its best: the script's own comment says the original absolute threshold
        # [EN] (`concurrent < 0.55`) went red in the parallel regression after scheduling overhead ate 0.19s of
        # [EN] margin,
        # [EN] later changed to a **differential** (saving ≈ one call's time) + raised the fixture delay to
        # [EN] 0.60s,
        # [EN] precisely to resist noise. 2026-10-08 it went red again, because this round two real-device
        # [EN] criteria were added to the GUI group
        # [EN] (`verify_style_bar` / `verify_regular_tab`), the parallel load is higher ——
        # [EN] the 0.60s signal was again buried by noise.
        # [EN] Pushing noise down further can only keep raising the delay, which trades "tests run slower" for
        # [EN] "criterion more accurate",
        # [EN] better to just let it be exclusive: it only runs 5 seconds.
        '真跑推演并**按墙钟计时**（耗时在并行高负载下不可测）',
    'verify_exit_codes':
        # ★★★ 2026-10-28 新增。**每支判据红了都真的会红**。
        #   起因：回归器**只看退出码** ⇒ 一支判据哪怕断言红成一片，只要退出码是 0，
        #   它在回归里就是**绿的**（「红灯打出来也没人看得见」⇒ 那条覆盖从没被证明过）。
        #   ⚠ 这个病**不会自己暴露**（判据绿、回归绿、报告写「N/N 通过」）⇒
        #     只有**故意把某条断言改坏**再真跑，才看得出它会不会红。
        #   实测当场抓出 7 支恒绿（含两支是我自己上一轮写的）。
        #   ⚠ 它会把每支纯逻辑判据**改坏一处再真跑一遍** ⇒ **很慢**（几分钟），
        #     而且它**改的是判据自己的源码** ⇒ **别和别的东西同时跑**
        #     （并行时正在读判据源码的脚本会读到半写完的文件）。
        #   ⇒ 放 ALONE 组（要独占），不放 LOGIC（会把整轮回归拖成一倍以上）。
        # [EN] ★★★ Added 2026-10-28. **Every criterion really goes red when it should**.
        #   Origin: the harness **only looks at the exit code** => a criterion that prints red all over
        #   but exits 0 is **always green** in the regression ("the red light was printed but nobody saw
        #   it" => that coverage was never proven).
        #   ⚠ The illness **never surfaces on its own** (criterion green, regression green, report writes
        #   "N/N passed") =>
        #     only by **deliberately breaking one assertion** and really re-running can you tell.
        #   Measured: caught 7 always-green criteria on the spot (two of them written by me the round
        #   before).
        #   ⚠ It **breaks one assertion per pure-logic criterion and really re-runs it** => **slow**
        #   (minutes), and it **edits criterion sources themselves** => **don't run it alongside anything
        #   else** (a script reading criterion sources in parallel would read a half-written file).
        #   => ALONE group (exclusive), not LOGIC (it would more than double a full regression pass).
        '把每支纯逻辑判据改坏一处再真跑一遍，看退出码 —— 改的是判据自己的源码，不能并行',
}

# 并发上限。32 核机器实测：真机 6 路约 3.5x，再加收益就钝了
# （瓶颈是每个 Flet 客户端的启动，不是 CPU）。
# [EN] Concurrency cap. Measured on a 32-core machine: 6 real-device lanes give about 3.5x, further
# [EN] gains taper off
# [EN] (the bottleneck is each Flet client's startup, not CPU).
DEFAULT_GUI_JOBS = 6
DEFAULT_LOGIC_JOBS = 8
TIMEOUT = 900

# ★★ 每个脚本一个**自己的日志目录**（理由见 `logger.log_dir()` 那段：
#   日志名精确到分钟 → 同分钟启动的多个进程会写同一个文件 →
#   "往日志里数条目"的判据（`verify_dialogue_log` B 组）当场错乱）。
#   放在 `logs/_parallel/` 下而不是临时目录，是为了**失败时还能去翻日志**。
#   ⚠ 这个目录会随跑的次数累积；它只是日志，随手删掉即可（没有任何东西依赖它）。
# [EN] ★★ Each script gets its **own log directory** (reason in the `logger.log_dir()` section:
# [EN] log names are precise to the minute → multiple processes started in the same minute write the
# [EN] same file →
# [EN] the criterion "count entries in the log" (`verify_dialogue_log` group B) gets scrambled on the
# [EN] spot).
# [EN] Placed under `logs/_parallel/` rather than a temp directory, so that **you can still go dig
# [EN] through the logs on failure**.
# [EN] ⚠ This directory accumulates with each run; it's just logs, delete it freely (nothing depends on
# [EN] it).
PARALLEL_LOG_ROOT = APP / 'logs' / '_parallel'

# ★★ **写不进用户的 `.env`**（`config.env_sink_path()` 读这个变量）。
# [EN] ★★ **Cannot write to the user's `.env`** (`config.env_sink_path()` reads this variable).
#
#   有些脚本会设测试值（`MOCK_LLM=true`、`DEFAULT_PROJECTS_DIR` 指临时目录…）
#   再触发 `CFG.save()`。串行跑时它们靠"备份/还原"勉强兜住；**一并行就必然漏** ——
#   实测就是这么中招的（并行跑完整套之后 `.env` 里躺着 `MOCK_LLM=true`、
#   `DEFAULT_PROJECTS_DIR=<某脚本的临时目录>`、`BEAT_SECONDS=2`）：
#   A 脚本的 `save()` 落在 B 脚本**备份与还原之间**，B 还原回来的干净内容又被覆盖。
# [EN] Some scripts set test values (`MOCK_LLM=true`, `DEFAULT_PROJECTS_DIR` pointing at a temp
# [EN] directory…)
# [EN] then trigger `CFG.save()`. In serial runs they barely manage via "backup/restore"; **in parallel
# [EN] it inevitably leaks** ——
# [EN] that's exactly how it got hit in practice (after a full parallel run `.env` was sitting with
# [EN] `MOCK_LLM=true`,
# [EN] `DEFAULT_PROJECTS_DIR=<some script's temp directory>`, `BEAT_SECONDS=2`):
# [EN] Script A's `save()` lands **between** script B's backup and restore, and B's clean restored
# [EN] content gets overwritten.
#
#   项目铁律是「会写用户文件的路径，默认就该**写不进去**」——
#   所以不靠脚本自觉，由回归器给每个子进程设这个环境变量，指向一个临时文件。
# [EN] The project's iron rule is "paths that write user files should **not be writable** by default"
# [EN] ——
# [EN] so it doesn't rely on scripts' self-discipline; the regressor sets this environment variable for
# [EN] each subprocess, pointing at a temp file.
#
# ★★ 2026-10-08 挪出 `logs/`（用户问「日志能不能打包发给别的工具」时查出来的）：
# [EN] ★★ 2026-10-08 moved out of `logs/` (found when the user asked "can the logs be zipped up and
# [EN] sent to another tool"):
#
#   原先它落在 `logs/_parallel_env/.env`。后果很实在：sink 文件是子进程 `CFG.save()`
#   写下的**一整份配置**，其中包含明文 `LLM_API_KEY` —— 于是**日志目录里躺着一把真密钥**。
#   `.gitignore` 挡住了 git，挡不住"把 logs 打包发给外部工具看"。用户那一刻的心智
#   模型是"logs/ 里都是日志，可以发"，这个模型**应该成立**。
# [EN] previously it landed at `logs/_parallel_env/.env`. The consequence was very real: the sink file
# [EN] is a **full copy of the config**
# [EN] written by the subprocess's `CFG.save()`, which includes the plaintext `LLM_API_KEY` —— so **a
# [EN] real key was sitting in the log directory**.
# [EN] `.gitignore` blocks git, but doesn't block "zip up logs and send to an external tool". The
# [EN] user's mental
# [EN] model at that moment was "everything in logs/ is logs, safe to send", and this model **should
# [EN] hold**.
#
#   单支脚本自己用的 `verify_ui_common.redirect_env_writes()` 从一开始就写在系统临时
#   目录（`tempfile.mkdtemp`），只有回归器这一处落在项目里 —— 现在统一。
# [EN] The `verify_ui_common.redirect_env_writes()` used by individual scripts was written from the
# [EN] start into the system temp
# [EN] directory (`tempfile.mkdtemp`); only this one place in the regressor landed inside the project
# [EN] —— now unified.
ENV_SINK = Path(tempfile.gettempdir()) / 'nws_parallel_env' / '.env'

#: 日志目录下**绝不该出现**的文件（扫到就说明某条路径又把密钥写进"可打包目录"了）。
# [EN] : files that **must never appear** under the log directory (scanning one out means some path
# [EN] wrote a key into a "zip-and-send directory" again).
SECRET_FILES_IN_LOGS = ('.env', '.env.local', 'credentials', 'secrets')


def purge_secrets_from_logs() -> list[str]:
    """回归收尾：把误落进 `logs/` 的敏感文件扫出来删掉。

    ★ 为什么要有这道：`ENV_SINK` 那个坑（密钥躺进日志目录）是**第 6 次**栽在
      "以为没人会往这儿写"上。与其等下一次，不如每次跑完**主动扫一遍** ——
      扫到就删，并且**大声说出来**（删掉的东西不吭声，下一次就没人知道曾经有过）。
    
        English:
    Regression wrap-up: scan out and delete sensitive files that mistakenly landed in `logs/`.
        ★ Why this step must exist: the `ENV_SINK` pitfall (secrets lying in the log directory) is the **6th** time we've been burned by
          "thinking nobody would write here". Rather than wait for next time, **actively scan** after every run --
          delete anything found, and **say it out loud** (deleted things being silent means next time nobody will know there ever was one).
    """
    removed: list[str] = []
    try:
        for p in APP.joinpath('logs').rglob('*'):
            if p.is_file() and p.name in SECRET_FILES_IN_LOGS:
                p.unlink()
                removed.append(str(p.relative_to(APP)))
    except OSError:
        pass
    return removed


def conclusion(stdout: str) -> str:
    for ln in reversed(stdout.splitlines()):
        s = ln.strip()
        if '验证：' in s or '通过' in s and '/' in s:
            return s[:80]
    return '(无结论行)'


def run_one(name: str, tag: str, lock: threading.Lock) -> dict:
    t0 = time.time()
    # 给这支脚本一个**只属于它**的日志目录（详见 `logger.log_dir()`）。
    # [EN] Give this script a log directory that belongs **only to it** (see `logger.log_dir()` for
    # [EN] details).
    env = dict(os.environ)
    env['NWS_LOG_DIR'] = str(PARALLEL_LOG_ROOT / name)
    # ★★★ **判据自己的硬超时**（2026-10-17 加）：比起"被回归器杀"，
    #   它自己先退一步 —— 关掉自己的 flet 客户端再退出，不留孤儿窗口。
    #   值取 `TIMEOUT - 60`：让脚本**先**自杀，回归器那道才是真的兜底。
    #   详见 `tools/verify_ui_common._arm_import_watchdog`。
    # [EN] ★★★ **The criterion's own hard timeout** (added 2026-10-17): it steps down before being
    # [EN] killed by the harness -- closes its own flet client and exits, leaving no orphan window.
    # [EN] Value is `TIMEOUT - 60`: the script kills itself **first**, the harness's kill is the real
    # [EN] backstop. See `tools/verify_ui_common._arm_import_watchdog`.
    env['NWS_VERIFY_WATCHDOG'] = str(max(30, TIMEOUT - 60))
    # 保险丝：**它怎么 save() 都写不到用户的 .env**（详见 `ENV_SINK` 那段）。
    # [EN] Fuse: **no matter how it save()s, it can't write to the user's .env** (see the `ENV_SINK`
    # [EN] section for details).
    env['NWS_ENV_SINK'] = str(ENV_SINK)
    # ★★ 消息另给**每支脚本一份**（2026-10-09 加）。不能复用上面那个共享 sink：
    #   `.env` sink 是**只写**的保险丝，谁也读它；而消息文件**启动时要读回来** ——
    #   共用一个文件，每支判据就会读到**别的判据留下的消息**（实测两处假红：
    #   `verify_ui_english` 在英文界面里读出中文消息；`verify_regular_tab`
    #   找不到自己那四条回执）。所以按脚本名各给一份，路径落在它自己的日志目录下。
    # [EN] ★★ Messages are given **a separate copy per script** (added 2026-10-09). Cannot reuse the shared
    # [EN] sink above:
    # [EN] the `.env` sink is a **write-only** fuse, nobody reads it; while the message file **must be read
    # [EN] back at startup** ——
    # [EN] sharing one file means each criterion reads **messages left by other criteria** (two false reds
    # [EN] measured:
    # [EN] `verify_ui_english` read Chinese messages in the English UI; `verify_regular_tab`
    # [EN] couldn't find its own four receipts). So give each one by script name, path landing under its
    # [EN] own log directory.
    env['NWS_MSG_SINK'] = str(PARALLEL_LOG_ROOT / name / 'messages.jsonl')
    # ★★★ 超时**必须杀整棵进程树**（2026-10-17 修）：
    #   旧写法是 `subprocess.run(..., timeout=TIMEOUT)` —— 超时后它只杀**直接子进程**
    #   （`python tools/verify_x.py`），而脚本自己拉起的 `flet.exe` 客户端是**孙进程**，
    #   于是变成永久孤儿，卡在「Working...」加载页上。用户报的
    #   「有大量的 flet working 窗口没退出」正是它：当时桌面上挂着两个跑了一小时半的
    #   全量回归，各自卡在一支真机判据上。
    #   ⇒ 改成 Popen + `kill_pid_tree()`（Windows `taskkill /T /F`），连客户端一起收。
    #   另外**每跑完一支都扫一遍孤儿客户端**：`finally` 里那句
    #   `sweep_orphan_clients()` 只认"父进程已死"的，不会碰用户自己开着的程序。
    # [EN] ★★★ On timeout we **must kill the whole process tree** (fixed 2026-10-17):
    # [EN] the old `subprocess.run(..., timeout=TIMEOUT)` only killed the **direct child**
    # [EN] (`python tools/verify_x.py`), while the `flet.exe` client the script launched is a
    # [EN] **grandchild** -- it became a permanent orphan stuck on the "Working..." page. That is
    # [EN] exactly the user's report ("a pile of flet working windows that never exit"): two full
    # [EN] regressions had run for 1.5 hours, each stuck on one real-machine criterion.
    # [EN] => Popen + `kill_pid_tree()` (Windows `taskkill /T /F`) collects the client too.
    # [EN] Also **sweep orphan clients after every script**: the `sweep_orphan_clients()` in
    # [EN] `finally` only recognises "parent already dead" ones and never touches the user's own app.
    p = subprocess.Popen([str(PY), f'tools/{name}.py'], cwd=str(APP), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding='utf-8', errors='replace')
    try:
        out, _ = p.communicate(timeout=TIMEOUT)
        code = p.returncode
    except subprocess.TimeoutExpired:
        _kill_tree(p.pid)
        try:
            out, _ = p.communicate(timeout=20)
        except Exception:                  # noqa: BLE001
            out = ''
        code = -9
        out = (out or '') + f'\n(超时 {TIMEOUT}s，已结束整棵进程树)'
    finally:
        sweep_orphan_clients()
    dt = int(time.time() - t0)
    res = {'name': name, 'group': tag, 'exit': code, 'secs': dt,
           'verdict': conclusion(out or '')}
    with lock:
        ok = code == 0
        print(f"{'OK  ' if ok else 'FAIL'} {tag:4s} exit={code:<3} "
              f"{name:26s} {dt:4d}s  {res['verdict']}", flush=True)
    return res


def declared() -> tuple[list[str], list[str]]:
    """把分组表与磁盘上的脚本对表，返回 `(要跑的名单, 问题清单)`。
        English:
    Cross-check the group table against the scripts on disk, returning `(list to run, list of
    problems)`.
    """
    on_disk = {p.stem for p in (APP / 'tools').glob('verify_*.py')}
    on_disk -= HELPERS
    listed = list(LOGIC) + list(GUI) + list(ALONE)
    problems: list[str] = []
    dup = sorted({n for n in listed if listed.count(n) > 1})
    if dup:
        problems.append(f'同一支脚本被登记了多次：{dup}')
    missing = sorted(on_disk - set(listed))
    if missing:
        problems.append('**磁盘上有、但没登记分组**（请加进 LOGIC / GUI / ALONE）：'
                        f'{missing}')
    extra = sorted(set(listed) - on_disk)
    if extra:
        problems.append(f'登记了、但磁盘上没有（改名了？）：{extra}')
    # ★★ **残留的变异**：反例法改产品源码 → 跑判据 → 还原。还原靠 `finally`，
    #   而 `finally` **挡不住进程被杀**（实测：一次超时截断把
    #   `pass  # 变异：造型不交给演员` 留在 `sim/loop.py` 里半小时，
    #   期间所有判据都在量一个**错的产品** —— 而且它们照样"全绿"）。
    #   两件事一起做：反例法自己存 `_inflight` 备份（能还原），
    #   这里**拦一道**（漏掉一个都别想跑完）。
    # [EN] ★★ **Leftover mutations**: reverse-injection-method modifies product source → run criteria →
    # [EN] restore. Restoration relies on `finally`,
    # [EN] and `finally` **can't stop the process from being killed** (measured: one timeout truncation
    # [EN] left
    # [EN] `pass  # mutation: styling not handed to the actor` in `sim/loop.py` for half an hour,
    # [EN] during which all criteria were measuring a **wrong product** —— and they still came out "all
    # [EN] green").
    # [EN] Do both things together: the reverse-injection-method stores its own `_inflight` backup (can
    # [EN] restore),
    # [EN] and here **we block one pass** (miss one and none of them get to finish the run).
    leftovers = _mutation_leftovers()
    if leftovers:
        problems.append('**产品源码里残留着变异标记**（上次反例法没跑完？'
                        '先跑 `developers/mutate_crew_*.py` 让它自己还原）：'
                        + str(leftovers))
    return listed, problems


#: 反例法留下的标记（那些脚本里每条变异都带这个字眼）。
#: 判法不在这里，在 `tools/verify_mutation_anchors.py::mutation_leftovers`（唯一实现）。
# [EN] : the marker left by the reverse-injection-method (every mutation in those scripts carries this
# [EN] word). The criterion lives in `tools/verify_mutation_anchors.py` (single implementation).


def _mutation_leftovers() -> list[str]:
    """扫产品源码里有没有反例法留下的 `# 变异：` 标记。
        English:
    Scan product source for `# 变异:` markers left by the counterexample method.

    == **判法只有一份**，就在 `tools/verify_mutation_anchors.py::mutation_leftovers` ——
       这里**直接 import 那一份**，不另写一遍。
       2026-10-19 之前这里自己写了一份「文件里含 `变异：` 就算残留」，而
       `crew/novel_rules.py` 里**讲这条规则的说明文字**本身就带这四个字
       => 每次全量回归还没开跑就被自己拦下（假红）。
       专用工具那一版试过三版才对：tokenize 只认真正的 COMMENT token，
       字符串字面量里的 `# 变异：` 不算（novel_rules 的 symptom= 正是那种）。
    [EN] == There is **one criterion only**, in `tools/verify_mutation_anchors.py` --
    [EN] import it here rather than writing a second copy. The copy that used to live here
    [EN] ("file contains the marker == leftover") blocked every full regression before it
    [EN] started, because the rule documentation in `crew/novel_rules.py` *mentions* the
    [EN] marker. The canonical version took three attempts: `tokenize` accepts only real
    [EN] COMMENT tokens; a `# 变异:` inside a string literal does not count.
    """
    return _mutation_left()


def suspicious() -> list[str]:
    """分组与源码特征的**可疑**之处 —— 只提示，不拦（下单的是人，不是正则）。

    ⚠ 这里的"含 `ft.run(`"只是个**提示**，不是判据：分组表才是权威。
    反过来也提醒一声：把起窗口的脚本扔进 LOGIC 组不会让错误变绿，
    但会让"并行到底会不会互扰"这件事更难查。
    
        English:
    **Suspicious** points between grouping and source features -- hint only, don't block (it's a
    human ordering, not a regex).
        ⚠ The "contains `ft.run(`" here is only a **hint**, not a criterion: the group table is the authority.
        Conversely, a reminder: throwing a window-starting script into the LOGIC group won't turn errors green,
        but it will make "does parallelism actually interfere" harder to investigate.
    """
    out: list[str] = []
    for n in LOGIC:
        p = APP / 'tools' / f'{n}.py'
        if p.exists() and 'ft.run(' in p.read_text(encoding='utf-8', errors='ignore'):
            out.append(f'{n}：登记在 LOGIC，但源码里有 `ft.run(`（真机？）')
    for n in GUI:
        p = APP / 'tools' / f'{n}.py'
        if p.exists() and 'ft.run(' not in p.read_text(encoding='utf-8', errors='ignore'):
            out.append(f'{n}：登记在 GUI，但源码里没有 `ft.run(`（纯逻辑？）')
    return out


def _pid_alive(pid: int) -> bool:
    """这个 PID 还活着吗（Windows 用一次进程列表查询；其他平台 `os.kill(pid, 0)`）。

        English:
    Is this PID still alive (one process-list query on Windows; `os.kill(pid, 0)` elsewhere).
    """
    if pid <= 0:
        return False
    if sys.platform == 'win32':
        # 复用 `flet_shutdown` 那份列表：它查的正是 python.exe / pythonw.exe / flet.exe，
        # 而占着这把锁的一定是 python.exe。
        # [EN] Reuse the list from `flet_shutdown`: it queries python.exe / pythonw.exe / flet.exe,
        # [EN] and whoever holds this lock is a python.exe.
        from util.flet_shutdown import _win_list_procs
        return any(p['pid'] == pid for p in _win_list_procs())
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_run_lock() -> str | None:
    """拿"同时只跑一份全量回归"的锁。返回 `None` = 拿到了；否则是给人看的拒绝理由。

    ★ 陈旧锁（持有者已死 / 上次被杀）**自动接管** —— 否则一次崩溃就永久锁死，
      那比"能同时跑两份"更糟。
    ★ 不用 `os.kill(pid, 0)` 判活（Windows 上语义不可靠），走进程列表。

        English:
    Acquire the "only one full regression at a time" lock. `None` = acquired; otherwise a
    human-readable refusal reason.
        ★ A stale lock (holder dead / last run killed) is **taken over automatically** -- otherwise one
          crash locks it forever, which is worse than "two runs at once".
        ★ Liveness is judged from the process list, not `os.kill(pid, 0)` (unreliable on Windows).
    """
    RUN_LOCK.parent.mkdir(parents=True, exist_ok=True)
    if RUN_LOCK.exists():
        try:
            old = json.loads(RUN_LOCK.read_text(encoding='utf-8') or '{}')
        except Exception:                  # noqa: BLE001
            old = {}
        pid = int(old.get('pid') or 0)
        # ★ 陈旧判定两条：
        #   ① 持有者进程不在了；
        #   ② 锁文件比 `LOCK_STALE_HOURS` 还老 —— 防 **PID 被复用**（昨天的锁里那个号
        #      今天恰好分给了一个活着的进程 ⇒ 永远拿不到锁）。一次全量回归不可能跑十几小时。
        # [EN] Two staleness tests: (1) the holder is gone; (2) the lock is older than
        # [EN] `LOCK_STALE_HOURS` -- guards against **PID reuse** (yesterday's pid happens to belong to
        # [EN] a live process today => the lock can never be acquired). A regression never runs that long.
        fresh = True
        try:
            import datetime as _dt
            t = _dt.datetime.strptime(str(old.get('started') or ''), '%Y-%m-%d %H:%M:%S')
            fresh = (_dt.datetime.now() - t).total_seconds() < LOCK_STALE_HOURS * 3600
        except Exception:                  # noqa: BLE001 —— 时间读不出来就当它新鲜，宁可拒
            fresh = True
        if pid and _pid_alive(pid) and fresh:
            return (f'已经有一份全量回归在跑（PID {pid}，起于 {old.get("started") or "?"}）。\n'
                    f'  同时跑两份会互相抢 `.env` sink / 端口，而且各自卡住时桌面上会留一堆\n'
                    f'  「Working...」的 Flet 窗口（2026-10-17 用户报的就是这个）。\n'
                    f'  要跑就先停掉它；确认它已死则删掉 {RUN_LOCK}。')
        # 陈旧锁：接管
        try:
            RUN_LOCK.unlink()
        except OSError:
            pass
    try:
        fd = os.open(str(RUN_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return f'拿锁失败：{RUN_LOCK} 刚刚被另一个进程建出来（请稍后重试）。'
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump({'pid': os.getpid(),
                   'started': time.strftime('%Y-%m-%d %H:%M:%S')}, f)
    return None


def release_run_lock() -> None:
    """放锁（只删自己那把）。"""
    try:
        old = json.loads(RUN_LOCK.read_text(encoding='utf-8') or '{}')
        if int(old.get('pid') or 0) == os.getpid():
            RUN_LOCK.unlink()
    except Exception:                      # noqa: BLE001
        pass


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--serial', action='store_true',
                    help='一次一支（排查"并行干扰"时用）')
    ap.add_argument('--jobs', type=int, default=0, help='真机并发（= --gui-jobs）')
    ap.add_argument('--gui-jobs', type=int, default=0)
    ap.add_argument('--logic-jobs', type=int, default=0)
    ap.add_argument('--only', default='', help='只跑这几支（逗号分隔）')
    # ★ `--skip`（2026-10-11 加）：用户明确说过「看下如果没问题就**不要再测试安装和卸载**」——
    #   有了它就能跑全量而把 `verify_installer` 摘出去，不必手写一长串 `--only`。
    # [EN] ★ `--skip` (added 2026-10-11): the user explicitly said "if it looks fine, don't keep
    # [EN] testing install and uninstall" -- with this you can run everything while excluding
    # [EN] `verify_installer`, instead of hand-writing a long `--only` list.
    ap.add_argument('--skip', default='', help='跳过这几支（逗号分隔）')
    ap.add_argument('--no-recheck', action='store_true',
                    help='不要"并行红的串行复跑一遍"')
    ap.add_argument('--groups', action='store_true', help='只列分组，不跑')
    # ★ `--logic-only`（2026-10-28 加）：只跑 LOGIC 组。
    #   起因：LOGIC 组是"改一行代码就想立刻知道有没有弄坏别处"的那一支，
    #   平时回归都带它；但 GUI 组要起真机窗口、ALONE 组要独占，
    #   **跑一次全量要好几分钟**，而只想看 LOGIC 时得手写一长串 `--only`。
    #   ⇒ 收成正式参数，别再留一个 `_run_logic_only.py` 一次性脚本：
    #   **同一件事两处实现 = 迟早有一处忘了跟着最新**。
    # [EN] ★ `--logic-only` (added 2026-10-28): run only the LOGIC group.
    # [EN] LOGIC is the group you want after every small edit; GUI needs real windows and
    # [EN] ALONE must run exclusively, so a full pass takes minutes.
    ap.add_argument('--logic-only', action='store_true',
                    help='只跑 LOGIC 组（纯逻辑，跳过真机窗口与独占组）')
    args = ap.parse_args()

    listed, problems = declared()
    if problems:
        print('✗ 分组表有问题，先修 `tools/run_all_verifications.py` 顶部：')
        for p in problems:
            print('   -', p)
        return 3
    for w in suspicious():
        print(f'⚠ 分组可疑：{w}', flush=True)

    only = {s.strip() for s in args.only.split(',') if s.strip()}
    skip = {s.strip() for s in args.skip.split(',') if s.strip()}
    logic = [n for n in LOGIC if (not only or n in only) and n not in skip]
    if args.logic_only:
        # 只跑 LOGIC ⇒ GUI 与 ALONE 都不列（不是"跑一遍再跳过"，是压根不进队列）。
        gui: list[str] = []
        alone: list[str] = []
    else:
        gui = [n for n in GUI if (not only or n in only) and n not in skip]
        alone = [n for n in ALONE if (not only or n in only) and n not in skip]
    total = len(logic) + len(gui) + len(alone)

    if args.groups:
        print(f'LOGIC（{len(LOGIC)} 支，纯逻辑）：')
        for n in LOGIC:
            print('   ', n)
        print(f'\nGUI（{len(GUI)} 支，真机窗口）：')
        for n in GUI:
            print('   ', n)
        print(f'\nALONE（{len(ALONE)} 支，必须独占）：')
        for n, why in ALONE.items():
            print(f'    {n}  —— {why}')
        return 0

    # ★★★ **单飞**（2026-10-17 加）：同时只允许一份全量回归。
    #   起因很实在：我连开了三份（20:52 / 21:34 / 22:14），它们各自卡在一支真机判据上，
    #   桌面上于是挂着好几个 flet 窗口、并且互相抢 `.env` sink 与端口 ——
    #   而"卡住"这件事在日志里只表现为"没有新行"，从外面看不出来。
    #   拒绝时**把占用的 PID 与启动时间说出来**，省得以为是脚本自己坏了。
    # [EN] ★★★ **Single-flight** (added 2026-10-17): only one full regression at a time.
    # [EN] The real reason: I launched three (20:52 / 21:34 / 22:14); each got stuck on one
    # [EN] real-machine criterion, so several flet windows hung on the desktop while they fought over
    # [EN] the `.env` sink and ports -- and "stuck" only looks like "no new lines in the log" from
    # [EN] the outside.
    # [EN] When refusing, **say which PID and when it started**, so nobody thinks the script broke.
    why_busy = acquire_run_lock()
    if why_busy:
        print(f'✗ {why_busy}', flush=True)
        return 3
    try:
        return _run_all(args, logic, gui, alone, total)
    finally:
        release_run_lock()


def _run_all(args, logic: list[str], gui: list[str],
             alone: dict, total: int) -> int:
    """真正的跑批（`main()` 拿到单飞锁之后调它）。"""
    gui_jobs = args.jobs or args.gui_jobs or DEFAULT_GUI_JOBS
    logic_jobs = args.logic_jobs or DEFAULT_LOGIC_JOBS
    if args.serial:
        gui_jobs = logic_jobs = 1
    # 并发不该超过脚本数（免得开一堆空 worker）
    # [EN] Concurrency should not exceed the script count (to avoid spawning a bunch of idle workers)
    gui_jobs = max(1, min(gui_jobs, len(gui) or 1))
    logic_jobs = max(1, min(logic_jobs, len(logic) or 1))

    lock = threading.Lock()
    results: dict[str, dict] = {}
    t_all = time.time()

    def _run(group: list[str], tag: str, jobs: int) -> float:
        if not group:
            return 0.0
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            for r in ex.map(lambda n: run_one(n, tag, lock), group):
                results[r['name']] = r
        return time.time() - t0

    print(f'并行回归：{total} 支（逻辑 {len(logic)}@{logic_jobs}｜'
          f'真机 {len(gui)}@{gui_jobs}｜独占 {len(alone)}）\n', flush=True)

    # 开跑前先清一遍**上次留下的孤儿窗口**（父进程已死的 flet.exe）。
    # 用户自己开着的程序父进程还活着，这里一个都不会碰。
    # [EN] Sweep orphan windows left by the previous run (flet.exe whose parent is gone).
    # [EN] The user's own running app has a live parent; nothing of theirs is touched here.
    stale = sweep_orphan_clients()
    if stale:
        print(f'🧹 开跑前清掉 {len(stale)} 个孤儿 Flet 窗口：{stale}', flush=True)

    # ⚠ 顺序有意义：`ALONE` 必须**等前面全跑完**再开始，
    #   否则"独占"就名不副实（它的干扰源正是别的实例）。
    # [EN] ⚠ Order matters: `ALONE` must **wait for all prior runs to finish** before starting,
    # [EN] otherwise "exclusive" is a misnomer (its interference source is precisely the other instances).
    t_logic = _run(logic, '逻辑', logic_jobs)
    t_gui = _run(gui, '真机', gui_jobs)
    t_alone = _run(alone, '独占', 1)
    wall = time.time() - t_all

    # ── 并行红的，串行复跑一遍（分清真红 / 并行不稳）──
    # [EN] ── For parallel reds, rerun serially once (to distinguish true red / parallel flakiness) ──
    flaky: list[str] = []
    if not args.no_recheck and not args.serial:
        reds = [n for n, r in results.items() if r['exit'] != 0]
        if reds:
            print(f'\n串行复跑 {len(reds)} 支并行红的（分清真红 / 并行不稳）…',
                  flush=True)
            for n in reds:
                r = run_one(n, '复跑', lock)
                if r['exit'] == 0:
                    flaky.append(n)
                    results[n]['flaky'] = True
                    print(f'   ⚠ {n}：并行红、串行绿 → **并行不稳**，'
                          f'应加进 ALONE', flush=True)
                else:
                    results[n]['flaky'] = False

    # ── 收尾：把误落进 logs/ 的敏感文件扫掉（详见 `purge_secrets_from_logs`）──
    # [EN] ── Wrap-up: sweep away sensitive files that mistakenly landed in logs/ (see
    # [EN] `purge_secrets_from_logs` for details) ──
    purged = purge_secrets_from_logs()

    # ── 写报告（**按名字排序**，跟串行版本能直接 diff）──
    # [EN] ── Write report (**sorted by name**, directly diffable against the serial version) ──
    rows: list[str] = []
    bad: list[str] = []
    for name in sorted(results):
        r = results[name]
        tag = 'OK  ' if r['exit'] == 0 else 'FAIL'
        mark = '  ⚠并行不稳' if r.get('flaky') else ''
        rows.append(f"{tag} exit={r['exit']:<3} {name:26s} {r['secs']:4d}s  "
                    f"{r['verdict']}{mark}")
        if r['exit'] != 0:
            bad.append(name)
    serial_sum = sum(r['secs'] for r in results.values())
    speed = serial_sum / max(0.1, wall)
    header = [
        f'# 并行回归：{total} 支 | 逻辑 {len(logic)}@{logic_jobs} '
        f'真机 {len(gui)}@{gui_jobs} 独占 {len(alone)}',
        f'# 墙钟 {wall:.0f}s（各步耗时相加 {serial_sum}s，约 {speed:.1f}x）｜'
        f'逻辑 {t_logic:.0f}s / 真机 {t_gui:.0f}s / 独占 {t_alone:.0f}s',
        '',
    ]
    foot = ['', f'共 {total} 个脚本；失败：{bad if bad else "无"}']
    if flaky:
        # ⚠ 分开说：**没进 ALONE 的**才是"该加组"；**已经在 ALONE 里**还颠的，
        #   再喊"请加进 ALONE"就是误导（2026-10-08 实测：verify_story_depth 早在
        #   ALONE，却被这条提示支使着又去查了一遍分组）。
        # [EN] ⚠ Say it separately: only those **not in ALONE** are "should be added to a group"; those
        # [EN] **already in ALONE** that still flake,
        # [EN] telling them again "please add to ALONE" is misleading (2026-10-08 measured: verify_story_depth
        # [EN] was long since
        # [EN] in ALONE, yet this hint sent someone off to re-check the grouping again).
        not_alone = [n for n in flaky if n not in ALONE]
        in_alone = [n for n in flaky if n in ALONE]
        if not_alone:
            foot.append(f'⚠ 并行不稳（并行红、串行绿）：{not_alone} —— 请把它们加进 ALONE 组')
        if in_alone:
            foot.append(f'⚠ 已在 ALONE 组、却仍偶发（并行红、串行绿）：{in_alone}'
                        ' —— 不是分组问题，是**跑完前面 90 多支之后的负载/时序抖动**；'
                        '先单跑几次看能否复现，**别急着放宽判据**。')
    lines = header + rows + foot
    OUT.parent.mkdir(parents=True, exist_ok=True)
    io.open(OUT, 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n' + '\n'.join(foot), flush=True)
    if purged:
        print(f'🧹 已从 logs/ 清掉敏感文件（绝不该躺在可打包目录里）：{purged}',
              flush=True)
    print(f'墙钟 {wall:.0f}s（各步相加 {serial_sum}s，约 {speed:.1f}x）', flush=True)

    # 退出码：真红 = 1；**并行不稳也算非零** —— 一个每次答案不一样的套件
    # 本身就是坏的（修法很明确：加进 ALONE 组），不能当"没事"放过去。
    # [EN] Exit code: true red = 1; **parallel flakiness also counts as non-zero** —— a suite whose answer
    # [EN] differs every time
    # [EN] It is itself broken (the fix is clear: add it to the ALONE group), so it can't be let slide as
    # [EN] "fine".
    return 0 if not bad and not flaky else 1


if __name__ == '__main__':
    raise SystemExit(main())
