# -*- coding: utf-8 -*-
"""真机验证：运行会话（设计稿 §七）—— 装配、起停、启动故事对话框。

为什么单独一个脚本
------------------
「运行界面能暂停/停止」这件事以前**根本不成立**：`RunLoop` 没接进 GUI，
按钮只能是灰的。所以这里要验的不是"按钮画出来了"，而是**链路真的通了**：
设定集 → 装配世界 → 起会话 → 叙事出现在中栏 → 暂停真的冻结 → 停止真的收尾。

两部分：
  A. 逻辑：装配层（含失败路径）、会话状态机、**暂停中停止**、收尾落盘与导出、
     以及一条回归断言（`RunLoop.run` 别再被实例属性遮住）。
  B. 真机：运行界面三个按钮 → 启动故事对话框 → **走真实点击路径**开跑
     → 中栏真的出现叙事 → 暂停（按钮变「继续」）→ 停止 → 产物落盘 → 截图。

产出 `assets/screenshots/run_*.png` + `run_control_report.json`。

跑法：
    .venv/Scripts/python tools/verify_run_control.py               # 全部
    .venv/Scripts/python tools/verify_run_control.py --logic-only   # 只跑逻辑

English:
Real-machine verification: run session (design doc §7) -- assembly, start/stop, start story
dialog.
Why a separate script
------------------
"The run UI can pause/stop" was previously **simply not true**: `RunLoop` was not wired into the
GUI,
the buttons could only be gray. So what's verified here is not "the buttons are drawn" but
**that the chain really works**:
settings -> assemble world -> start session -> narrative appears in middle column -> pause
really freezes -> stop really wraps up.
Two parts:
  A. Logic: assembly layer (including failure paths), session state machine, **stop while paused**, wrap-up persist and export,
     plus a regression assertion (`RunLoop.run` must not be shadowed by an instance attribute again).
  B. Real machine: three buttons on the run UI -> start story dialog -> **go through the real click path** to start
     -> narrative really appears in middle column -> pause (button changes to "继续") -> stop -> artifacts persisted -> screenshot.
Produces `assets/screenshots/run_*.png` + `run_control_report.json`.
How to run:
    .venv/Scripts/python tools/verify_run_control.py               # all
    .venv/Scripts/python tools/verify_run_control.py --logic-only   # logic only
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
#: **判据自己**等收尾的上限（秒）。★ 2026-10-26：以前借产品的 `WRAP_WAIT_SECONDS`，
#: 而那个键**产品源码一次都没读过**（`config_sweep` D1 抓到的假旋钮，已从 SPEC 删掉）。
#: 判据的等待上限是**判据的东西**，不该挂在产品配置上 —— 那会让"用户能调"变成一句空话。
#: 为什么是 900 秒：收尾要跑 场记→宣发→审校→复盘→整理→导出 一串调用，真机几十秒到几分钟；
#: 以前写死 20 秒，于是把"收尾正常但要跑两分钟"误判成"停止坏了"。
# [EN] **The criterion's own** wrap-up wait limit (seconds). ★ 2026-10-26: it used to borrow the
# [EN] product's `WRAP_WAIT_SECONDS`, which the product **never read** (a fake knob caught by
# [EN] `config_sweep` D1 and deleted from SPEC). A criterion's patience is the criterion's own
# [EN] business; hanging it on product config makes "the user can tune it" an empty promise.
WRAP_WAIT_LIMIT = 900
sys.path.insert(0, str(APP_DIR))

import flet as ft                                     # noqa: E402
from util.flet_shutdown import shutdown, exit_now      # noqa: E402

from config import CFG                                 # noqa: E402
CFG.set('MOCK_LLM', 'true')
# ★ 每轮开场（§3.6.1）：本脚本验的是**运行会话本身**（起停 / 暂停 / 落盘），
#   不需要开场那张卡来凑热闹，关掉它让日志干净些。
#   ⚠ 2026-10-06 起开场**不再弹框、也不再等点击** —— 改成"推一张卡进中栏，
#   然后直接开跑"。所以这里关它只是为了聚焦；开场那条路另有脚本
#   （`tools/verify_story_depth.py`）全程验。
# [EN] ★ Opening of each round (Section 3.6.1): this script verifies the **run session itself**
# [EN] (start/stop / pause / persistence),
# [EN] no need for the opening card to join in; turn it off to keep logs clean.
# [EN] ⚠ As of 2026-10-06 the opening **no longer pops a dialog and no longer waits for a click** --
# [EN] changed to "push a card into the middle column,
# [EN] then start running directly". So turning it off here is just for focus; the opening path has its
# [EN] own script
# [EN] (`tools/verify_story_depth.py`) that verifies it end to end.
CFG.set('SHOW_OPENING', 'false')
# ★★★ 2026-10-22：**外部创作服务必须关掉**（否则这个判据量的是别人的网络，不是我们的运行控制）。
#   实测：本机 `.env` 是 `MUMU_ENABLED=true / MUMU_AUTOSTART=true / MUMU_TIMEOUT_SECONDS=900`，
#   而 `MOCK_LLM=true` **管不到它** —— 写样章那一步走的是 `novelservices/mumu_bridge`
#   （同步 HTTP，超时 900 秒）。于是：
#     · 开场从 4 秒变成 **60 秒以上**（日志实测 `阶段「novelist」用时 60.5s`），
#       而存档点那几条判据只等 20 秒 ⇒ 等不到 ⇒ **红**；
#     · 整个脚本有一次跑满 **15 分钟被 timeout 杀掉**（exit=124），判据根本没跑完；
#     · 结果还随"外部服务今天在不在/快不快"变化 ⇒ 同一份代码时而 36/40、时而别的。
#   存档点判据要的是"日界到了会怎样"，与谁写的样章毫无关系 —— 那就必须让它走内部稿。
#   （这条与 `_session_flow` 里"节拍/时间倍率都在测试里定死，不读用户 .env"是同一条纪律。）
# [EN] ★★★ 2026-10-22: **the external creation service must be off**, otherwise this criterion
# [EN] measures someone else's network instead of our run control. Measured: this machine's `.env`
# [EN] has `MUMU_ENABLED=true / MUMU_AUTOSTART=true / MUMU_TIMEOUT_SECONDS=900`, and `MOCK_LLM=true`
# [EN] **does not cover it** -- the sample-chapter step goes through `novelservices/mumu_bridge`
# [EN] (synchronous HTTP, 900s timeout). So: the opening goes from 4s to **over 60s**
# [EN] (log: `阶段「novelist」用时 60.5s`) while the checkpoint checks wait only 20s => red; one run
# [EN] even hit the **15-minute timeout** (exit=124) and never finished; and results drift with
# [EN] "is the external service up and fast today" => same code, different score. The checkpoint
# [EN] criteria are about "what happens at the day boundary", nothing to do with who writes the
# [EN] sample chapter -- so the internal draft must be used.
CFG.set('MUMU_ENABLED', 'false')
CFG.set('MUMU_AUTOSTART', 'false')
# ★★★ 2026-10-22（第二次，同一个病换了个服务）：**三个外部创作服务全关**。
#   关掉 MuMu 之后脚本还是不结束 —— faulthandler 抓到的栈是：
#     `crew/agents.py:2383 _penshot_storyboard` → `novelservices/penshot_bridge.py:995
#      generate_storyboard` → `urllib.request.urlopen`（**同步、无超时**）
#   它跑在 `asyncio.to_thread` 里，主循环只能干等；`PENSHOT_TIMEOUT_SECONDS=900`
#   ⇒ **收尾要等 15 分钟**，而 `ses.wait()` 的预算也是 900 秒 ⇒ 整个脚本被外层
#   `timeout 900` 杀掉（`exit=124`，判据一条都没跑完）。
#   ⚠ 这不是"判据太慢"：`PENSHOT_ENABLED=true` 是**用户 .env** 的值，而这一组测的是
#     起停/暂停/落盘 —— 让第三方服务的可用性决定判据红绿，本身就违反了"测试自足"。
#   ⚠ 也提醒产品侧：外部服务不通时，"点停止"确实会等满它的超时（见本轮报告）。
# [EN] ★★★ 2026-10-22 (second time, same disease, different service): **all three external
# [EN] creation services off**. After disabling MuMu the script still never finished -- the
# [EN] faulthandler stack was: `crew/agents.py:2383 _penshot_storyboard` ->
# [EN] `novelservices/penshot_bridge.py:995 generate_storyboard` -> `urllib.request.urlopen`
# [EN] (**synchronous, no timeout**), running inside `asyncio.to_thread` while the main loop can only
# [EN] wait; `PENSHOT_TIMEOUT_SECONDS=900` => **wrap-up waits 15 minutes**, and `ses.wait()`'s budget is
# [EN] also 900s => the whole script is killed by the outer `timeout 900` (`exit=124`, not a single
# [EN] criterion finished). ⚠ This is not "the criteria are slow": `PENSHOT_ENABLED=true` is the
# [EN] **user's .env**, and this group tests start/stop/pause/persist -- letting a third-party service's
# [EN] availability decide red/green violates "tests must be self-sufficient".
CFG.set('PENSHOT_ENABLED', 'false')
CFG.set('PLOTPILOT_ENABLED', 'false')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

import yaml                                            # noqa: E402

from store.project import Project                      # noqa: E402
from store.runfolder import RunFolder                  # noqa: E402

OUTDIR = APP_DIR / 'assets' / 'screenshots'
OUTDIR.mkdir(parents=True, exist_ok=True)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'
LOGIC_ONLY = '--logic-only' in sys.argv
ENV_PATH = APP_DIR / '.env'

report: dict = {}
_checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = '') -> bool:
    _checks.append((name, bool(ok), detail))
    return bool(ok)


# 清理统一走 `verify_ui_common.safe_rmtree`：本机的 safe-delete 守卫会在
# 单次删除超过 50 个文件时直接 SystemExit(1)，而 `ignore_errors=True` 拦不住
# （SystemExit 是 BaseException 不是 OSError）—— 那会让脚本在「写报告之前」
# 就被杀掉，留下上一次的旧报告，看起来像测试通过了。
# [EN] Cleanup uniformly goes through `verify_ui_common.safe_rmtree`: the local safe-delete guard will
# [EN] directly SystemExit(1)
# [EN] when a single delete exceeds 50 files, and `ignore_errors=True` can't catch it
# [EN] (SystemExit is BaseException, not OSError) -- that would kill the script "before writing the
# [EN] report",
# [EN] leaving the old report from last time, making it look like the tests passed.
from verify_ui_common import safe_rmtree  # noqa: E402


# ══════════════════════════════════════════════════════════════
#  造一个带设定集的项目
# [EN] Create a project with a story bible
# ══════════════════════════════════════════════════════════════
def make_project(root: Path, *, chars: int = 3, nodes: int = 0) -> Project:
    """造项目 + 冻结设定集（格式照抄 `ingest/pipeline._freeze`）。

    `nodes=0` 表示**不给进度表** —— 这样 `is_at_end()` 恒为 False，
    会话不会自己跑到终点，正好用来测「运行中/暂停中停止」。
    
        English:
    Create project + freeze settings (format copied from `ingest/pipeline._freeze`).
        `nodes=0` means **no progress table is given** -- so `is_at_end()` is always False,
        the session won't run to its own end, which is exactly what's needed to test "stop during running/paused".
    """
    proj = Project(root, root.name)
    sd = proj.settings_dir
    sd.mkdir(parents=True, exist_ok=True)

    people = [("主角", "沈家长子", "沉稳内敛，话少", "且慢"),
              ("柳氏", "主角之妻", "爽利，管账", "你莫急"),
              ("阿福", "沈家老仆", "忠厚爱唠叨", "唉")]
    yaml_text = "".join(
        f"- 姓名: {n}\n  身份: {i}\n  性格: {p}\n  口癖: {c}\n"
        f"  目标: 把事办成\n  秘密: 压着一件旧事\n"
        for n, i, p, c in people[:chars])
    (sd / '人物.yaml').write_text(yaml_text, encoding='utf-8')

    # 摄取冻结时 世界观/剧情走向 是 yaml.dump 出来的字符串，这里照真实格式写
    # [EN] At ingest-freeze time, worldview/plot direction are strings produced by yaml.dump; write them
    # [EN] here in the real format
    (sd / '世界观.md').write_text(
        yaml.dump("临河小城，常年落雨，人情密、口风紧。", allow_unicode=True),
        encoding='utf-8')
    (sd / '剧情走向.md').write_text(
        yaml.dump("第一幕：货船延误。第二幕：旧案浮出。", allow_unicode=True),
        encoding='utf-8')

    if nodes:
        node_list = [{"id": f"N{i + 1:02d}", "名称": f"节点{i + 1}",
                      "概要": f"第 {i + 1} 段要发生的事", "完成判据": "场面推进",
                      "状态": "未开始"} for i in range(nodes)]
        (sd / '故事进度.yaml').write_text(
            yaml.dump({"节点": node_list}, allow_unicode=True), encoding='utf-8')
    return proj


# ══════════════════════════════════════════════════════════════
#  A. 逻辑验证
# [EN] A. Logic verification
# ══════════════════════════════════════════════════════════════
def run_logic(tmp: Path) -> None:
    # noqa: F401 —— settings_summary 在真机部分不用，但这里要用
    # [EN] noqa: F401 -- settings_summary is unused in the real-machine part, but is needed here
    from sim.setup import SetupError, assemble, build_world, load_settings, settings_summary  # noqa: F401
    from sim.session import RunSession

    # ★★★ 2026-10-22：**这条判据自己先自证"不依赖外部服务"**。
    #   为什么值得单列一条：这组断言曾在同一份代码上时而 36/40、时而跑满 15 分钟被杀，
    #   查下来全是因为它继承了用户 `.env` 里的 `MUMU_ENABLED/PENSHOT_ENABLED=true`
    #   —— 第三方服务慢/不在，判据就红或卡死，而"起停/暂停"根本没坏。
    #   判据把前提写成断言，下次有人删掉那几行 `CFG.set(...)` 会**当场红**，
    #   而不是等到某天外部服务出问题时，才把"判据不可靠"误当成"产品坏了"。
    # [EN] ★★★ 2026-10-22: **this criterion first proves it does not depend on external services**.
    # [EN] Why it deserves its own line: this group used to flip between 36/40 and a 15-minute kill on
    # [EN] identical code, purely because it inherited `MUMU_ENABLED/PENSHOT_ENABLED=true` from the
    # [EN] user's `.env` -- a slow/absent third-party made it red or hang while start/stop was fine.
    # [EN] Writing the precondition as an assertion makes a future deletion of those `CFG.set(...)`
    # [EN] lines go **red on the spot**, instead of someone later mistaking "unreliable criteria" for
    # [EN] "broken product".
    check('测试自足：三个外部创作服务在本判据里**都是关的**'
          '（否则"起停"判据会被第三方服务的快慢决定红绿）',
          not CFG.b('MUMU_ENABLED') and not CFG.b('PENSHOT_ENABLED')
          and not CFG.b('PLOTPILOT_ENABLED'),
          f"mumu={CFG.b('MUMU_ENABLED')} penshot={CFG.b('PENSHOT_ENABLED')} "
          f"plotpilot={CFG.b('PLOTPILOT_ENABLED')}")

    # ── 1. 装配：从设定集建出世界 ──
    # [EN] -- 1. Assembly: build the world from the story bible --
    proj = make_project(tmp / '装配验证')
    run = RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
    s = load_settings(proj.settings_dir)
    check('装配：读到 3 位人物', len(s['people']) == 3, str(len(s['people'])))
    check('装配：世界观不是空', len(s['worldview']) > 5, s['worldview'][:30])
    check('装配：剧情参考线不是空', len(s['plot']) > 5, s['plot'][:30])
    check('装配：摘要可读', '人物 3 位' in settings_summary(s), settings_summary(s))

    w = build_world(s)
    check('装配：WorldState 建出人物', set(w.people) == {'主角', '柳氏', '阿福'},
          str(list(w.people)))
    check('装配：人物字段映射正确',
          w.people['主角'].identity == '沈家长子'
          and w.people['主角'].catchphrase == '且慢',
          f"{w.people['主角'].identity} / {w.people['主角'].catchphrase}")
    check('装配：总世界观拼进了 prompt 前缀（含地点/伏笔段）',
          '【世界观】' in w.worldview_text and '【剧情参考线】' in w.worldview_text)
    check('装配：风格控制取自 CFG', 0 <= w.angst_level <= 1, str(w.angst_level))

    loop, world, db = assemble(proj, run)
    check('装配：RunLoop 建出前台 agents', len(loop.agents) == 3, str(len(loop.agents)))
    check('装配：director 就位', type(loop.director).__name__ == 'DirectorEngine')
    check('装配：DB 落在运行文件夹里', Path(db.path) == run.db_path, str(db.path))

    # ── 2. 回归：`run()` 方法不能再被实例属性遮住 ──
    # 以前 `self.run = run` 把方法覆盖了，`await loop.run()` 报
    # `'RunFolder' object is not callable`。循环从没跑过所以一直没露头。
    # [EN] -- 2. Regression: the `run()` method must no longer be shadowed by an instance attribute --
    # [EN] Previously `self.run = run` overwrote the method, and `await loop.run()` raised
    # [EN] `'RunFolder' object is not callable`. The loop never ran so it never surfaced.
    check('回归：装配后 loop.run 仍是可调用的协程方法',
          inspect.iscoroutinefunction(loop.run),
          f'type={type(loop.run).__name__}')
    check('回归：运行文件夹挂在 loop.runfolder 上',
          getattr(loop, 'runfolder', None) is run)

    # ── 3. 装配失败要走 SetupError（界面能转成人话）──
    # [EN] -- 3. Assembly failure must go through SetupError (the UI can turn it into plain language) --
    empty = tmp / '空设定集项目'
    (empty / '设定集').mkdir(parents=True, exist_ok=True)
    ep = Project(empty, '空设定集项目')
    erun = RunFolder(ep.root, '第1次模拟2026-01-01-00-00').create()
    try:
        assemble(ep, erun)
        check('装配：空设定集该抛 SetupError', False, '没有抛异常')
    except SetupError as e:
        check('装配：空设定集抛 SetupError', True, str(e)[:40])
    except Exception as e:                                  # noqa: BLE001
        check('装配：空设定集抛 SetupError', False, f'抛了 {type(e).__name__}')

    # ── 4. 会话状态机（含暂停中停止）──
    # [EN] -- 4. Session state machine (including stop during pause) --
    async def _session_flow():
        # ⚠ **测试自足**：节拍 / 时间倍率 / **运行模式与日界间隔**都在这里定死，
        #   不读用户的 `.env`。
        #   （踩过：这套断言假设 0.8 秒内就能跑出一拍，而 `.env` 里
        #    一拍 15 故事秒 —— 一旦有人改过 .env，它就莫名其妙地红了。）
        #   ★ 2026-10-10 又补了两个：这一组测的是「用户点暂停」这条链，
        #     不该被**主循环自己的日界暂停**（`STORY_DAY_EVERY_DAYS`）搅进来 ——
        #     用户的 `.env` 里它是 1（每 1 天停一次），续跑时**第一拍就会停**，
        #     于是 `status` 是 paused 而不是 running，红的却是"暂停没生效"这条，
        #     看着像产品坏了。定死 `RUN_MODE=open`（这条路没有日界暂停）
        #     之后，这一组只测它自己要测的那件事。
        #   ⚠ 存在 `_save` 里、`try/finally` 还原 —— 不能把用户的 `.env` 改跑偏。
        # [EN] ⚠ **Test self-sufficiency**: beat / time multiplier / **run mode and day-boundary interval** are
        # [EN] all pinned down here,
        # [EN] not read from the user's `.env`.
        # [EN] (Been burned: this set of assertions assumes a beat can be produced within 0.8 seconds, while
        # [EN] `.env` had
        # [EN] 15 story-seconds per beat -- once someone changed .env, it would inexplicably go red.)
        # [EN] ★ 2026-10-10 added two more: this group tests the "user clicks pause" chain,
        # [EN] and should not be disturbed by the **main loop's own day-boundary pause**
        # [EN] (`STORY_DAY_EVERY_DAYS`) --
        # [EN] in the user's `.env` it is 1 (pause every 1 day), and on resume **it will pause on the very
        # [EN] first beat**,
        # [EN] so `status` is paused instead of running, yet the red one is the "pause didn't take effect"
        # [EN] assertion,
        # [EN] making it look like the product is broken. After pinning `RUN_MODE=open` (this path has no
        # [EN] day-boundary pause),
        # [EN] this group only tests the one thing it's meant to test.
        # [EN] ⚠ Stored in `_save`, restored in `try/finally` -- must not push the user's `.env` off track.
        # ★ 2026-10-26：**自动导出那几项也要自己钉住**。
        #   这条判据断言的是「收尾会走自动导出这条链」，而 2026-10-26 起
        #   `EXPORT_ON_END_*` 出厂默认全关（用户："自动导出默认关闭"）⇒ 它长期红，
        #   而红的原因跟"收尾有没有接上导出"毫无关系。
        #   ⇒ 测的是**链路**，就把开关**显式打开**再测；出厂默认值由
        #     `verify_export` 的「四个开关出厂默认全关」那条单独盯，两件事分开。
        # [EN] ★ 2026-10-26: **pin the auto-export switches here too.** This check asserts "wrap-up
        # [EN] runs the auto-export chain", and since 2026-10-26 `EXPORT_ON_END_*` all default to off
        # [EN] (user: "auto export off by default") => it was permanently red for a reason unrelated to
        # [EN] the chain. The chain is what's under test, so switch them on explicitly; the **factory
        # [EN] default** is guarded separately by `verify_export`'s "all four off by default".
        _save_flow = {k: CFG.raw(k) for k in
                      ('RUN_MODE', 'STORY_DAY_EVERY_DAYS',
                       'EXPORT_ON_END_RAW', 'EXPORT_ON_END_REFERENCE', 'EXPORT_ON_END_NOVEL')}
        CFG.set('RUN_MODE', 'open')
        CFG.set('STORY_DAY_EVERY_DAYS', '0')
        CFG.set('BEAT_SECONDS', '1')
        CFG.set('TIME_RATIO', '1')
        CFG.set('EXPORT_ON_END_RAW', 'true')
        CFG.set('EXPORT_ON_END_REFERENCE', 'true')
        CFG.set('EXPORT_ON_END_NOVEL', 'true')
        try:
            return await _session_flow_body(tmp)
        finally:
            for k, v in _save_flow.items():
                if v is not None:
                    CFG.set(k, str(v))

    async def _session_flow_body(tmp: Path):
        _ = tmp
        p2 = make_project(tmp / '会话验证')
        r2 = RunFolder(p2.root, '第1次模拟2026-01-01-00-00').create()
        lp, wd, _ = assemble(p2, r2)
        wd.progress_nodes = []          # 没有进度表 → 不会「到达终点」，能稳定测停止
        # [EN] No progress table -> won't "reach the endpoint", so stop can be tested stably
        seen, lines = [], []
        ses = RunSession(lp, wd, r2,
                         on_narrative=lambda tx, pr, **kw: lines.append(tx),
                         on_state=lambda st, rs: seen.append(st))
        out = {'seen': seen, 'lines': lines, 'run': r2}
        out['status0'] = ses.status
        out['alive0'] = ses.is_alive
        out['started'] = ses.start()
        out['start_again'] = ses.start()            # 重复启动应被拒
        # [EN] Repeated start should be rejected
        # ★★★ 等到**真的跑了第一拍**再往下走（2026-10-17 修，两版才对）：
        #   这里原先是 `await asyncio.sleep(0.8)`，隐含假设"0.8 秒内能跑出一拍"。
        #   而"开场"（`_open_day`：编剧室定框架 → 写样章 → 改剧本 → 验算）
        #   实测要 **3.5 秒** ⇒ 0.8 秒时 `_tick_no` 还是 0 ⇒ 停止时 `_finish()`
        #   走的是"这一天还没跑过一拍，跳过落盘"那条分支
        #   ⇒ 下面「收尾把最后一天落了盘」**恒红**（实测连跑三次都红，
        #   把 `.env` 改回旧值也红 —— 与拍长、与配置无关，是这条判据自己过时了）。
        #   ⚠ **第二版也不能用"有叙事"当条件**：开场本身就会推几条叙事
        #     （编剧室那几句），于是轮询 0.5 秒就 break、第一拍仍然没跑
        #     （实测 `ticks_today=0 tick_no=0`，树里只有 `每天的生活/原文/`）。
        #     要等的是计数本身：`_tick_no >= 1`（"跑过几拍"的唯一真相）。
        # [EN] ★★★ Wait until **the first beat has really run** before continuing (fixed 2026-10-17,
        # [EN] took two versions):
        # [EN] this used to be `await asyncio.sleep(0.8)`, implicitly assuming "one beat within 0.8s".
        # [EN] But the "opening" (`_open_day`: writers' room -> sample chapter -> script revision ->
        # [EN] verification) measures **3.5 seconds** => at 0.8s `_tick_no` is still 0 => on stop,
        # [EN] `_finish()` takes the "no beat has run today, skip persisting" branch => the
        # [EN] "wrap-up persisted the final day" check is **always red** (three runs in a row, and still
        # [EN] red with `.env` restored -- unrelated to beat length or config; the criterion was stale).
        # [EN] ⚠ **The second version must not use "there is narrative" either**: the opening itself pushes
        # [EN] a few narrative lines (the writers' room), so polling broke after 0.5s with the first beat
        # [EN] still not run (measured `ticks_today=0 tick_no=0`, and the tree only had `每天的生活/原文/`).
        # [EN] What to wait for is the counter itself: `_tick_no >= 1` (the single truth of "how many
        # [EN] beats have run").
        for _ in range(120):
            if int(getattr(lp, '_tick_no', 0) or 0) >= 1:
                break
            await asyncio.sleep(0.25)
        out['running'] = ses.status
        out['n_running'] = len(lines)

        ses.pause()
        await asyncio.sleep(0.4)
        n1 = len(lines)
        await asyncio.sleep(0.5)
        out['paused'] = ses.status
        out['frozen'] = (len(lines) == n1)
        out['n_pause'] = n1

        ses.resume()
        await asyncio.sleep(0.4)
        out['resumed'] = ses.status

        ses.pause()
        await asyncio.sleep(0.2)
        out['stop_ret'] = ses.stop()                # ★ 暂停中停止
        # [EN] ★ Stop during pause
        # ★★★ 2026-10-21（用户：「你把收尾时间放长」）：
        #   这里原来写死 **20 秒**。收尾要跑 场记→宣发→审校→复盘→整理→导出 一串调用，
        #   真机下每次几十秒到几分钟 ⇒ 20 秒必然超时，于是把「收尾正常但要跑两分钟」
        #   误判成「停止坏了」。改成读 （默认 900 秒）。
        #   ⚠ 这不是放宽标准：真卡死时它照样超时。
        #   ⚠ 也不要指望调大这个数去掩盖「点停止后还在写样章」—— 那是另一件事，已修。
        # [EN] ★★★ 2026-10-21 (user: "make the wrap-up time longer"): this used to be a hard-coded
        # [EN] **20 seconds**. Wrap-up runs continuity -> publicity -> polish -> review -> organize ->
        # [EN] export, each taking tens of seconds to minutes on a real machine => 20 s always times
        # [EN] out, misreporting "wrap-up is fine but takes two minutes" as "stop is broken". It now
        # [EN] reads  (default 900).
        # [EN] ⚠ This is not loosening: a genuine hang still times out.
        # [EN] ⚠ Do not use a bigger number to hide "still writing the sample chapter after stop" --
        # [EN] that was a separate bug and it is fixed.
        out['waited'] = await ses.wait(WRAP_WAIT_LIMIT)
        out['final'] = ses.status
        out['final_reason'] = ses.reason
        out['alive_end'] = ses.is_alive
        out['stop_again'] = ses.stop()              # 已结束再停应被拒
        # [EN] Stopping again after finish should be rejected
        out['daily'] = sorted(p.name for p in r2.daily_dir.glob('*.md'))
        # ★ 2026-10-17：这条长期红，而同一份日志里明明有「第 1 天落盘（剧本）」。
        #   把**整棵树的 .md** 一起记下来，用事实分清是"写到别处了"还是"根本没写"。
        # [EN] ★ 2026-10-17: this one has been red for a while, yet the same log clearly shows
        # [EN] "day 1 persisted (script)". Record **every .md in the tree** to tell, from the facts,
        # [EN] whether it went somewhere else or was never written.
        out['tree_md'] = sorted(str(p.relative_to(r2.root)) for p in r2.root.rglob('*.md'))
        out['daily_dir'] = str(r2.daily_dir)
        out['ticks_today'] = int(getattr(lp, '_ticks_today', -1) or 0)
        out['tick_no'] = int(getattr(lp, '_tick_no', -1) or 0)
        out['exports'] = sorted(p.name for p in r2.export_dir.glob('*.md'))
        return out

    r = asyncio.run(_session_flow())
    check('会话：初始为 idle 且不算活着',
          r['status0'] == 'idle' and r['alive0'] is False, r['status0'])
    check('会话：start() 成功', r['started'] is True)
    check('会话：重复 start() 被拒（不重复起）', r['start_again'] is False)
    check('会话：进入 running', r['running'] == 'running', r['running'])
    check('会话：跑起来真的产出了叙事', r['n_running'] > 0, f"{r['n_running']} 条")
    check('会话：暂停生效', r['paused'] == 'paused', r['paused'])
    check('会话：暂停后叙事冻结（不再增长）', r['frozen'] is True,
          f"{r['n_pause']} 条后停止增长")
    check('会话：继续回到 running', r['resumed'] == 'running', r['resumed'])
    check('会话：★ 暂停中 stop() 被接受（返回 True）', r['stop_ret'] is True)
    check('会话：暂停中 stop() 真的收尾完成', r['waited'] is True)
    check('会话：最终状态是 stopped 且原因「手动停止」',
          r['final'] == 'stopped' and r['final_reason'] == '手动停止',
          f"{r['final']} / {r['final_reason']}")
    check('会话：结束后 is_alive=False，再 stop() 被拒',
          r['alive_end'] is False and r['stop_again'] is False)
    check('会话：收尾把最后一天落了盘', len(r['daily']) >= 1,
          f"daily={r['daily']}｜dir={r.get('daily_dir')}｜"
          f"ticks_today={r.get('ticks_today')} tick_no={r.get('tick_no')}｜"
          f"树里的 md={r.get('tree_md')}")
    # ⚠ 档名**跟着 `_STEM` 走**，不再硬编码中文（这套名字 2026-10-25/26 改过四轮，
    #   硬编码一处就得改一处，漏改的症状是"判据红了但功能是好的"）。
    # [EN] The kind name comes from `_STEM` instead of being hardcoded -- these names were renamed
    # [EN] four times across 2026-10-25/26, and a hardcoded copy turns red while the feature is fine.
    try:
        from export import novel_version as _NV
        _novel_stem = _NV._STEM[_NV.MODE_NOVEL]
    except Exception:                                            # noqa: BLE001
        _novel_stem = '最终改写稿'
    check('会话：收尾触发了自动导出（零成本那两项）',
          any(n.startswith(_novel_stem + '_v') for n in r['exports']), str(r['exports']))
    check('会话：状态轨迹合理（running→paused→running→paused→stopped）',
          r['seen'][0] == 'running' and 'paused' in r['seen']
          and r['seen'][-1] == 'stopped', str(r['seen']))

    # ── 5. ★★★ 主循环**自己**开的暂停，必须让界面知道（2026-10-10 真机 bug）──
    # [EN] -- 5. ★★★ The main loop's **own** pause must be visible to the UI (2026-10-10 real-machine bug)
    # [EN] --
    #
    # 用户原话：「核对故事进度进行了 2000 多秒 你看下是怎么回事」。
    # [EN] User's exact words: "Checking story progress ran for over 2000 seconds, look into what's going
    # [EN] on".
    #
    # 真相：`story_day` 的**日界检查点**在 23:06:55 把主循环停住了，
    # 23:40:34 用户才手点暂停 —— 中间 **33 分 39 秒零 LLM 调用**
    # （`llm_calls.jsonl` 末条就停在 23:06:55），它只是在等人点「继续」。
    # [EN] The truth: `story_day`'s **day-boundary checkpoint** stopped the main loop at 23:06:55,
    # [EN] and the user only manually clicked pause at 23:40:34 -- in between, **33 minutes 39 seconds with
    # [EN] zero LLM calls**
    # [EN] (`llm_calls.jsonl`'s last entry stops at 23:06:55); it was just waiting for someone to click
    # [EN] "Continue".
    #
    # 而屏幕上写着「正在核对故事进度 · 已 2019 秒」：`_status('evaluating')`
    # 是那一拍上报的**最后一个细粒度状态**（`self.pause()` 停在它后面，
    # `_status('idle')` 根本没机会执行）；更要紧的是**主循环的 `self.pause()`
    # 不经过会话层** —— `session.status` 一直停在 `running`，于是界面不会把
    # 按钮换成「▶ 继续」、也不会把状态条写成「已暂停」（那句判断在
    # `gui/app_flet._status_view` 里排在最前面，走不到）。
    # [EN] Yet the screen said "Checking story progress · 2019 seconds elapsed": `_status('evaluating')`
    # [EN] was the **last fine-grained status** reported by that beat (`self.pause()` stops right after it,
    # [EN] `_status('idle')` never gets a chance to run); more importantly, **the main loop's
    # [EN] `self.pause()`
    # [EN] does not go through the session layer** -- `session.status` stays at `running`, so the UI won't
    # [EN] switch
    # [EN] the button to "▶ Continue", nor write the status bar as "Paused" (that check is at the very top
    # [EN] of `gui/app_flet._status_view`, and is never reached).
    #
    # 这一段验四件事：① 开跑不再白停一次；② 主循环自己停 → 会话状态跟着变；
    #   ③ 中栏说清为什么停；④ 点「继续」真的放得走（不是死等）。
    # [EN] This section verifies four things: (1) starting no longer idly stops once; (2) the main loop
    # [EN] stopping itself -> session state follows;
    # [EN] (3) the middle column states clearly why it stopped; (4) clicking "Continue" really lets it
    # [EN] proceed (not a dead wait).
    async def _self_pause_flow():
        """日界存档点：**默认不打断** + 打开开关就弹提问（2026-10-11 重写）。

        ⚠ 这一组 2026-10-10 写的时候验的是"它停了要说清"，而 2026-10-11
          用户又提了一条：「1.尽可能想办法不要让用户干预」+「这个时候实在
          推演中的 我没点暂停」—— 于是默认行为**从"停下等确认"改成"不打断"**。
          判据必须跟着改，否则它会替一个已经不存在的设计作证。
        
                English:
        Day-boundary checkpoint: **default does not interrupt** + turning on the switch pops a question
        (rewritten 2026-10-11).
                ⚠ When this group was written on 2026-10-10, what it verified was "if it stops, it must say so clearly", but on 2026-10-11
                  the user raised another point: "1. Try as much as possible not to require user intervention" + "at this time it really
                  was mid-simulation, I didn't click pause" -- so the default behavior **changed from "stop and wait for confirmation" to "do not interrupt"**.
                  The criterion must change accordingly, otherwise it will testify for a design that no longer exists.
        """
        _save = {k: CFG.raw(k) for k in ('RUN_MODE', 'STORY_DAY_EVERY_DAYS',
                                        'BEAT_SECONDS', 'TIME_RATIO',
                                        'CHECKPOINT_PAUSE')}
        # ⚠ **测试自足**：节拍/时间倍率/开关都在这里定死，不读用户的 `.env`
        #   （与上面 `_session_flow` 同一条纪律）。
        # [EN] ⚠ **Test self-sufficiency**: beat / time multiplier / switches are all pinned down here, not
        # [EN] read from the user's `.env`
        # [EN] (same discipline as `_session_flow` above).
        CFG.set('RUN_MODE', 'story_day')
        CFG.set('STORY_DAY_EVERY_DAYS', '1')
        CFG.set('BEAT_SECONDS', '1')
        CFG.set('TIME_RATIO', '1')
        try:
            out: dict = {}
            # ── ① 默认（`CHECKPOINT_PAUSE=false`）：跨日界**不停** ──
            # [EN] -- (1) Default (`CHECKPOINT_PAUSE=false`): does NOT stop across the day boundary --
            CFG.set('CHECKPOINT_PAUSE', 'false')
            p3 = make_project(tmp / '存档点·默认不停')
            r3 = RunFolder(p3.root, '第1次模拟2026-01-01-00-00').create()
            lp3, wd3, _ = assemble(p3, r3)
            wd3.progress_nodes = []           # 无进度表 → 不会判终点
            # [EN] No progress table -> won't judge the endpoint
            lines3: list[str] = []
            seen3: list[str] = []
            asked3: list[dict] = []
            # ⚠ **必须注册**：不注册的话"默认这条路走错了分支、去弹了问题"
            #   在夹具上完全看不出来 —— `_ask` 找不到回调就默默返回 None，
            #   表现和"没弹"一模一样（变异实测：那条变异漏掉了）。
            # [EN] ⚠ **Must register**: without registering, "the default path takes the wrong branch and pops the
            # [EN] question"
            # [EN] is completely invisible on the fixture -- `_ask` silently returns None when it can't find the
            # [EN] callback,
            # [EN] behaving exactly like "no popup" (mutation-tested: that mutation was missed).
            lp3.on_ask(lambda q: asked3.append(dict(q)))
            ses3 = RunSession(lp3, wd3, r3,
                              on_narrative=lambda tx, pr, **kw: lines3.append(tx),
                              on_state=lambda st, rs: seen3.append(st))
            out['day'] = wd3.game_day
            ses3.start()
            # ★★★ **不能**用固定 `sleep(1.5)` 赌"开场跑完了"（2026-10-17 修）：
            #   开场（编剧室 → 样章 → 改剧本 → 验算）实测 3.5–6.1 秒（MOCK 下也会抖），
            #   而"把日界标记对到当前日"那句是在开场之后才执行的 ⇒ 1.5 秒读到的是
            #   `标记=None` ⇒ 这条判据**时而红时而绿**（实测：上一轮 40/40 全绿，
            #   下一轮同一份代码就红在这一条）。判据要么等它真的写完，要么就是在掷骰子。
            # [EN] ★★★ **No fixed `sleep(1.5)` gambling on "the opening has finished"** (fixed 2026-10-17):
            # [EN] the opening (writers' room -> sample chapter -> script revision -> verification) measures
            # [EN] 3.5-6.1 seconds even in MOCK, and "align the day-boundary marker to the current day" runs
            # [EN] only after it => at 1.5s the value read is `None` => the criterion is **sometimes red,
            # [EN] sometimes green** (measured: 40/40 green one round, red on this same line in the next
            # [EN] with identical code). A criterion must wait for the write, or it is a dice roll.
            for _ in range(80):               # 最多 20 秒
                if getattr(lp3, '_last_story_day_pause', None) is not None:
                    break
                await asyncio.sleep(0.25)
            # `run()` 一开跑就该把日界标记对到**当前这一天** —— 不对的话
            # "开跑第一拍"必然满足"标记为空 ⇒ 停"，于是**一按开始就卡住**
            # （真机上就是这么开始的：23:01 点开始，23:06 就停了）。
            # [EN] `run()` should, as soon as it starts, align the day-boundary marker to **the current day** --
            # [EN] otherwise
            # [EN] "the first beat after start" necessarily satisfies "marker empty => stop", so **it gets stuck
            # [EN] the moment you press start**
            # [EN] (that's how it started on the real machine: pressed start at 23:01, stopped at 23:06).
            out['mark'] = getattr(lp3, '_last_story_day_pause', None)
            out['before'] = ses3.status
            out['pause_lines_before'] = [x for x in lines3 if '已按设置存档' in x]
            # 把标记挪回"上一天"，下一拍就真的跨过日界
            # [EN] Move the marker back to "the previous day", and the next beat really crosses the day boundary
            lp3._last_story_day_pause = wd3.game_day - 1
            for _ in range(40):               # 最多 20 秒
            # [EN] at most 20 seconds
                await asyncio.sleep(0.5)
                if any('已按设置存档' in x for x in lines3):
                    break
            out['after_cross'] = ses3.status
            out['seen_after_cross'] = list(seen3)
            out['asked'] = list(asked3)
            out['checkpoint_lines'] = [x for x in lines3 if '已按设置存档' in x]
            out['kept_going'] = len(lines3)
            ses3.stop()
            out['waited'] = await ses3.wait(40)

            # ── ② 打开开关（`CHECKPOINT_PAUSE=true`）：弹提问，答「停在这儿」才停 ──
            # [EN] -- (2) Turn the switch on (`CHECKPOINT_PAUSE=true`): pops the question, stops only after
            # [EN] answering "stop here" --
            CFG.set('CHECKPOINT_PAUSE', 'true')
            p4 = make_project(tmp / '存档点·停下等确认')
            r4 = RunFolder(p4.root, '第1次模拟2026-01-01-00-00').create()
            lp4, wd4, _ = assemble(p4, r4)
            wd4.progress_nodes = []
            asked4: list[dict] = []
            lines4: list[str] = []
            seen4: list[str] = []
            lp4.on_ask(lambda q: (asked4.append(dict(q)), lp4.answer_ask('hold')))
            ses4 = RunSession(lp4, wd4, r4,
                              on_narrative=lambda tx, pr, **kw: lines4.append(tx),
                              on_state=lambda st, rs: seen4.append(st))
            ses4.start()
            await asyncio.sleep(1.2)
            lp4._last_story_day_pause = wd4.game_day - 1
            for _ in range(40):
                await asyncio.sleep(0.5)
                if ses4.status == 'paused':
                    break
            out['on_ask_kinds'] = [q.get('kind') for q in asked4]
            # ⚠ **先把"停住那一刻"的状态采下来，再点继续** —— 反了的话
            #   `paused_by_ask` 采到的是 resume 之后的 `running`，
            #   那条断言会红（我第一版就是这个顺序，自己把自己判红了）。
            # [EN] ⚠ **First capture the state at the moment of "stopping", then click continue** -- reversed, and
            # [EN] `paused_by_ask` captures the post-resume `running`,
            # [EN] and that assertion goes red (my first version had this order and judged itself red).
            out['paused_by_ask'] = ses4.status
            out['paused_seen'] = list(seen4)
            out['hold_lines'] = [x for x in lines4 if '存档点' in x]
            # ★ 「停过之后要记账」的靶子：点「继续」之后**同一天不该再问第二遍**。
            #   不记账的话下一拍照样满足"第 N 天 % every == 0"，于是又问一次 ——
            #   作者看到的是"刚点继续，同一个问题又弹出来"（死等）。
            # [EN] ★ Target for "must account after stopping": after clicking "Continue", **the same day must not
            # [EN] ask a second time**.
            # [EN] Without accounting, the next beat still satisfies "day N % every == 0", so it asks again --
            # [EN] what the author sees is "just clicked continue, and the same question pops up again" (dead
            # [EN] wait).
            n_before = len(asked4)
            ses4.resume()
            await asyncio.sleep(2.5)
            out['reasked_same_day'] = len(asked4) - n_before
            out['after_resume_state'] = ses4.status
            ses4.stop()
            out['waited2'] = await ses4.wait(40)
            return out
        finally:
            for k, v in _save.items():
                if v is not None:
                    CFG.set(k, str(v))

    async def _ask_cancel_flow():
        """**取消 → 暂停 → 点继续重新弹 → 答完放行**（用户 2026-10-11 点名要的）。

        直接拿一个真 `RunLoop` 只测 `_ask` 这一件事（不起完整推演，快且准）。
        
                English:
        **Cancel -> pause -> clicking continue re-prompts -> answer and release** (explicitly requested
        by the user on 2026-10-11).
                Directly use a real `RunLoop` to test only this one thing `_ask` (without starting the full reasoning, fast and accurate).
        """
        p = make_project(tmp / '问答·取消与重弹')
        r = RunFolder(p.root, '第1次模拟2026-01-01-00-00').create()
        lp, wd, _ = assemble(p, r)
        wd.progress_nodes = []
        asked: list[dict] = []
        lp.on_ask(lambda q: asked.append(dict(q)))
        lp._running = True
        out: dict = {}
        task = asyncio.ensure_future(lp._ask(
            kind='intervention', title='导演想介入', why='要不要听它的？',
            options=[{'id': 'accept', '标题': '听导演的', '后果': ''},
                     {'id': 'skip', '标题': '这次不用', '后果': ''}],
            allow_custom=True))
        await asyncio.sleep(0.4)
        out['asked_once'] = len(asked)
        out['pending'] = lp._ask_pending is not None
        # 取消 ⇒ 暂停，**题留着**，`_ask` **继续等**（不能一取消就返回）
        # [EN] Cancel => pause, **question stays**, `_ask` **keeps waiting** (must not return on cancel)
        lp.cancel_ask()
        await asyncio.sleep(0.4)
        out['cancelled_paused'] = lp.paused
        out['kept_pending'] = lp._ask_pending is not None
        out['still_waiting'] = not task.done()
        # 点「继续」⇒ **题重新弹出来**
        # [EN] Click "Continue" => **question pops up again**
        lp.resume()
        await asyncio.sleep(0.4)
        out['reopened'] = len(asked) > out['asked_once']
        out['resumed_unpaused'] = not lp.paused
        # 答完 ⇒ 这一拍才往下走
        # [EN] Answer => only then does this beat proceed
        lp.answer_ask('skip')
        try:
            ans = await asyncio.wait_for(asyncio.shield(task), 5)
        except asyncio.TimeoutError:
            ans = None
            task.cancel()
        out['answer'] = ans
        out['done'] = task.done()
        out['pending_cleared'] = lp._ask_pending is None
        return out

    # ⚠ 名字别撞：`_self_pause_flow` **自己内部**另有一个局部 `r4`
    #   （它的 `RunFolder`）。外面这个结果给 `r5` —— 撞了会 KeyError，
    #   而我第一版就是这么写的（32/32 "全绿"是把异常吞在 `__main__` 的
    #   `except BaseException` 里，报告却是上一次的）。
    # [EN] ⚠ Don't collide names: `_self_pause_flow` **internally** has another local `r4`
    # [EN] (its `RunFolder`). The outer result is given to `r5` -- a collision will KeyError,
    # [EN] and that's how I wrote the first version (32/32 "all green" was because exceptions were
    # [EN] swallowed in `__main__`'s
    # [EN] `except BaseException`, and the report was from the previous run).
    r3 = asyncio.run(_self_pause_flow())
    r5 = asyncio.run(_ask_cancel_flow())
    report['self_pause'] = r3
    report['ask_cancel'] = r5

    # ── 默认那条：**不该打断** ──
    # ⚠ 这条断言**必须三件事一起判**（只有 `mark == day` 会被掩盖）：
    #   变异实测过 —— 不初始化标记时，**第一拍的暂停自己会把标记写回当前日**，
    #   于是"只看标记"当场变绿（判据成了装饰品）。
    # [EN] -- The default path: **should not interrupt** --
    # [EN] ⚠ This assertion **must judge three things together** (only checking `mark == day` will be
    # [EN] masked):
    # [EN] Mutation-tested -- without initializing the mark, **the first beat's pause writes the mark back
    # [EN] to the current day itself**,
    # [EN] so "mark only" goes green immediately (the criterion becomes mere decoration).
    check('★★★ 存档点：`run()` 开跑时把日界标记对到当前日 —— '
          '**开跑第一拍不该白停一次**（真机上就是"一按开始就停了"：'
          '23:01 点开始，23:06 就停住了，而作者以为它在核对进度）',
          r3['mark'] == r3['day'] and r3['before'] == 'running'
          and not r3['pause_lines_before'],
          f"标记={r3['mark']}/第{r3['day']}天 · 状态={r3['before']} · "
          f"日界说明={r3['pause_lines_before']}")
    # ⚠ 观测量是**会话状态**，不是"中栏有没有那句话" —— 默认这条路
    #   恰恰**应该**有那句话（见下一条）。我第一版把两者混在一起，
    #   于是"排除说明行"反而把正确实现判红了。
    # [EN] ⚠ The observable is **session state**, not "whether that sentence is in the middle column" --
    # [EN] the default path
    # [EN] precisely **should** have that sentence (see next item). I conflated the two in the first
    # [EN] version,
    # [EN] so "excluding the explanation line" actually flagged the correct implementation as failed.
    check('★★★ 存档点：默认**不打断推演**（用户 2026-10-11：'
          '"尽可能想办法不要让用户干预"；真机上那条凭空冒出来的「临时暂停」'
          '就是它自己停的）',
          r3['after_cross'] == 'running' and 'paused' not in r3['seen_after_cross']
          and not r3['asked'] and r3['kept_going'] > 0,
          f"跨日界后状态={r3['after_cross']} / 轨迹={r3['seen_after_cross']} / "
          f"弹了 {r3['asked']} / 叙事 {r3['kept_going']} 条")
    # ⚠ 这条**不能**写成 `... or after_cross == 'running'` —— 那样它恒真，
    #   是装饰品（我第一版就这么写的）。它要量的就是"中栏有没有那一句"。
    # [EN] ⚠ This **cannot** be written as `... or after_cross == 'running'` -- that would make it always
    # [EN] true,
    # [EN] mere decoration (that's how I wrote the first version). What it must measure is "whether that
    # [EN] sentence is in the middle column".
    check('★★ 存档点：默认**不打断，但要说一句"存档了"**'
          '（不打断 ≠ 不吭声 —— 作者得知道"到日界了、稿子存过了"）',
          len(r3['checkpoint_lines']) >= 1,
          str(r3['checkpoint_lines'][:1]))

    # ── 打开开关那条：走**提问对话框**，不是裸暂停 ──
    # [EN] -- The switch-on path: goes through the **question dialog**, not a bare pause --
    check('★★★ 存档点：`CHECKPOINT_PAUSE=true` 时**弹提问**（不是裸暂停）',
          r3['on_ask_kinds'] == ['checkpoint'],
          str(r3['on_ask_kinds']))
    check('★★★ 存档点：答「停在这儿」真的停下，且**会话状态跟着变 paused**'
          '（这样界面才会把按钮换成「继续」、状态条写「已暂停」）',
          r3['paused_by_ask'] == 'paused' and 'paused' in r3['paused_seen'],
          f"{r3['paused_by_ask']} / 轨迹 {r3['paused_seen']}")
    check('★ 存档点：停下来时中栏说清了是"存档点"这件事',
          any('存档点' in x for x in r3['hold_lines']),
          str(r3['hold_lines'][:1]))
    check('★★ 存档点：停下来之后**记了账** —— 点「继续」同一天不再问第二遍'
          '（不记账的话下一拍又问一次 = 死等）',
          r3['reasked_same_day'] == 0 and r3['after_resume_state'] == 'running',
          f"又问 {r3['reasked_same_day']} 次 / 状态 {r3['after_resume_state']}")

    # ── 用户点名的"取消 → 暂停 → 点继续重新弹" ──
    # [EN] -- The user-named "cancel -> pause -> click continue to re-pop" --
    check('★★★ 取消：点「取消」⇒ **推演暂停**（用户点名的那半条）',
          r5['cancelled_paused'] is True, str(r5['cancelled_paused']))
    check('★★★ 取消：**题不能丢**（丢了就再也弹不回来）',
          r5['kept_pending'] is True and r5['still_waiting'] is True,
          f"pending={r5['kept_pending']} / 还在等={r5['still_waiting']}")
    check('★★★ 点「继续」⇒ **对话框重新弹出来**（用户点名的另半条）',
          r5['reopened'] is True and r5['resumed_unpaused'] is True,
          f"重弹={r5['reopened']} / 继续后未暂停={r5['resumed_unpaused']}")
    check('★★ 答完之后这一拍才往下走（题目清干净）',
          r5['answer'] == {'id': 'skip', 'custom': ''} and r5['pending_cleared'],
          f"答案={r5['answer']} / 题清干净={r5['pending_cleared']}")

    # 报告要能 JSON 序列化 —— 把 RunFolder 这类活对象摘掉
    # [EN] The report must be JSON-serializable -- strip out live objects like RunFolder
    report['logic'] = {k: v for k, v in r.items() if k not in ('lines', 'run')}
    report['ok'] = all(ok for _, ok, _ in _checks)


# ══════════════════════════════════════════════════════════════
#  B. 真机验证
# [EN] B. Real-machine verification
# ══════════════════════════════════════════════════════════════
def walk(node, out: list) -> None:
    """遍历控件树（遇到 str 就停，它们是按钮的裸文字）。
        English:
    Walk the control tree (stop at str, they are the button's bare text).
    """
    if node is None or isinstance(node, str):
        return
    out.append(node)
    for attr in ('controls', 'content', 'actions', 'title'):
        v = getattr(node, attr, None)
        if isinstance(v, list):
            for c in v:
                walk(c, out)
        elif v is not None:
            walk(v, out)


def all_texts(page, extra_roots: list | None = None) -> list[str]:
    nodes: list = []
    for c in page.controls:
        walk(c, nodes)
    for root in (extra_roots or []):
        walk(root, nodes)
    vals: list[str] = []
    for c in nodes:
        if isinstance(c, ft.Text) and c.value:
            vals.append(str(c.value))
        if isinstance(c, (ft.TextField, ft.Dropdown, ft.DropdownM2)):
            for a in ('value', 'hint_text', 'label'):
                x = getattr(c, a, None)
                if x:
                    vals.append(str(x))
        v = getattr(c, 'content', None)
        if isinstance(v, str) and v.strip():
            vals.append(v)          # Flet 1.0：按钮文字可能是裸字符串
            # [EN] Flet 1.0: button text may be a bare string
    return vals


def find_btn(root, needle: str):
    """在控件树里按文字找按钮（按钮文字在 `content`）。
        English:
    Find buttons by text in the control tree (button text is in `content`).
    """
    nodes: list = []
    walk(root, nodes)
    for c in nodes:
        ct = getattr(c, 'content', None)
        text = ct.value if isinstance(ct, ft.Text) else (ct if isinstance(ct, str) else '')
        if text and needle in text and hasattr(c, 'on_click') and c.on_click:
            return c
    return None


async def main(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp, set_btn_text     # noqa: F401
    from i18n import set_lang
    from sim.session import PAUSED, RUNNING, STOPPED
    set_lang(_lang)

    env_backup = ENV_PATH.read_text(encoding='utf-8') if ENV_PATH.exists() else None

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    # 项目根临时改到系统临时区：真机测试会真建项目、真跑一轮、真落盘，
    # 不能让这些产物落在**用户的 Projects 里**（现在环境对删除管得很紧，
    # 删不掉就会留下一个假项目挂在「拾卷」列表里）。CFG 在 finally 里随 .env 还原。
    # [EN] Temporarily move project root to system temp area: real-machine tests really create projects,
    # [EN] really run a round, really persist to disk,
    # [EN] these artifacts must not land in **the user's Projects** (the environment is currently very
    # [EN] strict about deletion,
    # [EN] if it can't be deleted, a fake project will be left hanging in the "拾卷" list). CFG is restored
    # [EN] with .env in finally.
    tmp_projects = Path(tempfile.mkdtemp(prefix='nws_runctrl_proj_'))
    CFG.set('DEFAULT_PROJECTS_DIR', str(tmp_projects))
    proj_root = tmp_projects / '运行控制验证'
    try:
        proj_root.mkdir(parents=True, exist_ok=True)
        proj = make_project(proj_root, chars=3, nodes=0)
        proj.write_nwsproj()
        app.current_project = proj

        # ── 1. 运行界面三个按钮 ──
        # [EN] -- 1. Three buttons on the run UI --
        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.8)
        texts = all_texts(page)
        report['main_texts'] = [x for x in texts if x.strip()][:40]
        ui = app._ui_run
        check('真机：有「起　笔」按钮', ui is not None
              and find_btn(page, '起　笔') is not None)
        check('真机：有「暂停」按钮', find_btn(page, '暂停') is not None)
        check('真机：有「停止」按钮', find_btn(page, '停止') is not None)
        check('真机：未运行时暂停按钮是禁用的',
              ui.get('btn_pause') is not None and ui['btn_pause'].disabled is True)
        check('真机：未运行时停止按钮是禁用的',
              ui.get('btn_stop') is not None and ui['btn_stop'].disabled is True)
        check('真机：状态行显示「未运行」',
              ui.get('status') is not None and '未运行' in str(ui['status'].value),
              str(ui.get('status').value if ui.get('status') else ''))
        (OUTDIR / f'run_before{SUFFIX}.png').write_bytes(await page.take_screenshot())

        # ── 2. 启动故事对话框 ──
        # [EN] -- 2. Start story dialog --
        dlg = app.show_start_story_dialog()
        page.update()
        await asyncio.sleep(0.7)
        dtexts = all_texts(page, extra_roots=[dlg] if dlg else None)
        report['dialog_texts'] = dtexts
        for token in ('启动故事', '这一轮载入', '运行边界', '风格控制',
                      '导演与预算', '本轮上限天数', '开始推演'):
            check(f'真机：启动故事对话框含「{token}」',
                  any(token in x for x in dtexts))
        (OUTDIR / f'run_dialog{SUFFIX}.png').write_bytes(await page.take_screenshot())

        # ── 3. 走真实点击路径：点「开始推演」──
        # [EN] ── 3. Use the real click path: click "Start Simulation" ──
        btn_begin = find_btn(dlg, '开始推演')
        check('真机：找得到「开始推演」按钮', btn_begin is not None)
        if btn_begin is not None:
            btn_begin.on_click(None)
            for _ in range(80):                    # 等装配 + 起跑
            # [EN] Wait for assembly + startup
                await asyncio.sleep(0.1)
                if app.session is not None and app.session.is_alive:
                    break
            await asyncio.sleep(1.6)

        ses = app.session
        check('真机：会话已建立并进入运行中',
              ses is not None and ses.status == RUNNING,
              ses.status if ses else 'None')
        check('真机：真的新建了运行文件夹',
              ses is not None and ses.run.root.exists()
              and ses.run.root.name.startswith('第'),
              ses.run.root.name if ses else '')
        check('真机：装配出了前台人物',
              ses is not None and len(ses.loop.agents) == 3,
              str(len(ses.loop.agents)) if ses else '')
        check('真机：中栏收到实时叙事', len(app._live_lines) > 0,
              f'{len(app._live_lines)} 条')
        # ⚠ `_live_lines` 现在是三元组 (priority, text, kind) ——
        #   按两个解包会 ValueError（2026-10-06 加了词条类型之后踩到，
        #   整段真机验证因此静默失败、只剩 47/47 全绿的假象）。
        # [EN] ⚠ `_live_lines` is now a triple (priority, text, kind) --
        # [EN] unpacking as two will ValueError (hit this after adding entry types on 2026-10-06,
        # [EN] the entire real-machine verification therefore silently failed, leaving only the illusion of
        # [EN] 47/47 all green).
        report['live_sample'] = [it[1] for it in app._live_lines[:5]]
        check('真机：叙事区控件真的挂在界面上',
              app._ui_run.get('narrative') is not None
              and len(app._ui_run['narrative'].controls) > 0)
        check('真机：暂停按钮已变为可用',
              app._ui_run['btn_pause'].disabled is False)
        check('真机：状态行显示运行中/已暂停',
              '运行中' in str(app._ui_run['status'].value)
              or '已暂停' in str(app._ui_run['status'].value),
              str(app._ui_run['status'].value))

        page.update()
        await asyncio.sleep(0.4)
        (OUTDIR / f'run_running{SUFFIX}.png').write_bytes(await page.take_screenshot())

        # ── 4. 暂停 → 按钮变「继续」──
        # [EN] -- 4. Pause -> button changes to "继续" --
        app._on_pause_toggle()
        await asyncio.sleep(0.6)
        check('真机：暂停后状态为 paused', ses.status == PAUSED, ses.status)
        pause_btn = app._ui_run['btn_pause']
        check('真机：暂停按钮文字变成「继续」',
              '继续' in (pause_btn.content.value if isinstance(pause_btn.content, ft.Text)
                         else str(pause_btn.content)),
              str(getattr(pause_btn.content, 'value', pause_btn.content)))
        check('真机：状态行显示「已暂停」',
              '已暂停' in str(app._ui_run['status'].value),
              str(app._ui_run['status'].value))
        page.update()
        await asyncio.sleep(0.3)
        (OUTDIR / f'run_paused{SUFFIX}.png').write_bytes(await page.take_screenshot())

        # ── 5. 停止 → 收尾 ──
        # [EN] -- 5. Stop -> wrap up --
        app._on_stop_run()
        # ★★★ 等多久要**按配置算**，不能写死 15 秒（2026-10-17 修）：
        #   "停止"不能在 `await agent_decide` 中途打断，只能等这一拍回来。
        #   一拍最长要等 `BEAT_SECONDS / TIME_RATIO` 真实秒 ——
        #   用户把节拍调成 80 故事秒 / 倍率 2 = **40 真实秒** 之后，
        #   写死的 15 秒必然超时 ⇒ 「停止后状态为 stopped」等三条**假红**
        #   （旧配置 10/4 = 2.5 秒时正好够，所以一直没暴露）。
        #   这里取 `一拍真实秒 × 2 + 10`（留一次收尾落盘 + 导出的余量）。
        # [EN] ★★★ How long to wait must be **derived from config**, not hard-coded 15s (fixed
        # [EN] 2026-10-17): "stop" cannot interrupt `await agent_decide` midway; it can only wait for
        # [EN] the current beat. One beat waits up to `BEAT_SECONDS / TIME_RATIO` real seconds -- the
        # [EN] user set 80 story-seconds / ratio 2 = **40 real seconds**, so a hard-coded 15s must
        # [EN] time out => three **false reds** (with the old 10/4 = 2.5s it was just enough, which is
        # [EN] why this never showed up). Use `beat real seconds x 2 + 10` (one wrap-up persist +
        # [EN] export of headroom).
        # ★★★ 2026-10-21（用户：「你把收尾时间放长」）：原来这里是 `min(120, ...)` ——
        #   **120 秒硬上限**，而且时长还是按**拍长**推的。
        #   两处都不对：
        #     ① 收尾时长跟拍长没关系 —— 收尾是 场记→宣发→审校→复盘→整理→导出 一串调用，
        #        一拍多长不影响它；
        #     ② 120 秒不够。真机下收尾常常超过两分钟，于是
        #        「停止后状态为 stopped / 原因 / 按钮禁用」三条一直红着 ——
        #        而同一次跑里，桩跑那段收尾明明正常完成、落了盘、还导出了稿子。
        #        也就是说：**红的是判据等得太短，不是产品坏了**。
        #   ⇒ 直接读 `WRAP_WAIT_SECONDS`（默认 900），下界 120。
        #   ⚠ 这不是放宽：真卡死时 900 秒照样超时。
        # [EN] ★★★ 2026-10-21 (user: "make the wrap-up time longer"): this used to be a **hard 120 s
        # [EN] cap**, and the duration was derived from the **beat length** -- both wrong:
        # [EN] ① wrap-up duration has nothing to do with beat length (it is continuity -> publicity ->
        # [EN]    polish -> review -> organize -> export);
        # [EN] ② 120 s is not enough. On a real machine wrap-up often exceeds two minutes, so three
        # [EN]    checks ("status stopped / reason / buttons disabled") stayed red -- while in the same
        # [EN]    run the stubbed section completed wrap-up, persisted the day and even exported.
        # [EN]    In other words: **the criterion waited too little, the product was fine.**
        # [EN] => Read `WRAP_WAIT_SECONDS` (default 900), floor 120.
        # [EN] ⚠ Not a loosening: a genuine hang still times out at 900 s.
        _stop_wait = int(max(120, CFG.i('WRAP_WAIT_SECONDS')) * 10)
        for _ in range(_stop_wait):                # 等收尾（补落盘 + 自动导出）
        # [EN] Wait for wrap-up (supplementary persist + auto export)
            await asyncio.sleep(0.1)
            if ses.status == STOPPED:
                break
        await asyncio.sleep(0.5)
        check('真机：停止后状态为 stopped', ses.status == STOPPED, ses.status)
        check('真机：停止原因记为「手动停止」', ses.reason == '手动停止', ses.reason)
        check('真机：停止后两个按钮回到禁用',
              app._ui_run['btn_pause'].disabled is True
              and app._ui_run['btn_stop'].disabled is True)
        daily = sorted(p.name for p in ses.run.daily_dir.glob('*.md'))
        report['daily'] = daily
        check('真机：停止时把最后一天补落了盘', len(daily) >= 1, str(daily))
        page.update()
        await asyncio.sleep(0.3)
        (OUTDIR / f'run_stopped{SUFFIX}.png').write_bytes(await page.take_screenshot())

        report['ok'] = all(ok for _, ok, _ in _checks)
    except Exception:
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        # 对话框里点「开始推演」会 CFG.save()，把测试用的 MOCK_LLM 等写进 .env。
        # 验证完必须还原，否则会悄悄改掉用户的配置。
        # [EN] Clicking "开始推演" in the dialog calls CFG.save(), writing the test's MOCK_LLM etc. into .env.
        # [EN] Must restore after verification, otherwise it will silently change the user's config.
        try:
            if env_backup is not None:
                ENV_PATH.write_text(env_backup, encoding='utf-8')
                report['env_restored'] = True
        except Exception as e:                              # noqa: BLE001
            report['env_restore_error'] = str(e)
        try:
            safe_rmtree(tmp_projects)
            report['cleaned'] = str(tmp_projects)
        except BaseException as e:                          # noqa: BLE001
            report['cleanup_error'] = str(e)
        report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
        (OUTDIR / f'run_control_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        failed = [n for n, o, _ in _checks if not o]
        print('=' * 62)
        print(f'运行控制验证：{len(_checks) - len(failed)} / {len(_checks)} 通过')
        for n in failed:
            print('   ✗', n)
        print('=' * 62)
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` throws
        # [EN] CancelledError
        # [EN] cancelling this coroutine, so the line `exit_now(...)` written after `await shutdown(page)`
        # [EN] **never executed** (exit code always 0 = fake green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


if __name__ == '__main__':
    # 逻辑验证的临时目录也放系统临时区（理由同真机那段）
    # [EN] Logic verification's temp directory also goes in system temp area (same reason as the
    # [EN] real-machine section)
    tmpdir = Path(tempfile.mkdtemp(prefix='nws_runctrl_tmp_'))
    try:
        run_logic(tmpdir)
    except BaseException as e:              # 含 shim 的 SystemExit，不能只接 Exception
    # [EN] SystemExit with a shim, can't just catch Exception
        report['logic_fatal'] = traceback.format_exc()
        print('逻辑验证异常：', e)
    finally:
        safe_rmtree(tmpdir)

    if LOGIC_ONLY:
        report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
        (OUTDIR / f'run_control_logic_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        failed = [n for n, o, _ in _checks if not o]
        print('=' * 62)
        print(f'运行控制验证（仅逻辑）：{len(_checks) - len(failed)} / {len(_checks)} 通过')
        for n in failed:
            print('   ✗', n)
        print('=' * 62)
        exit_now(0 if not failed else 2)
    else:
        try:
            ft.run(main)
        except Exception:
            report['fatal'] = traceback.format_exc()
            report['ok'] = False
            report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
            (OUTDIR / f'run_control_report{SUFFIX}.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            exit_now(2)
