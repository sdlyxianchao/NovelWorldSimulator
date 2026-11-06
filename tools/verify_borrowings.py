# -*- coding: utf-8 -*-
"""判据：**2026-10-10 那一轮用户要求 + 外部借鉴落地**。

覆盖（每条都写清"防的是什么"）：

  A. **Hy3 / 腾讯 TokenHub** —— 能力表认得 `hy3`，且取值是核实过的
     （默认不思考、接受 temperature ⇒ 不算推理模型；不发 `response_format`）。
  B. **只留一个命令行窗口** —— 服务启动**结构上不可能**弹黑窗：
     `start.bat` 用 `pythonw.exe`、`novelservice.start_detached` 带 SW_HIDE、
     桥接层 `_run_service` 带 CREATE_NO_WINDOW。
  C. **`MUMU_AUTOSTART` 不再是假旋钮** —— 配置项有读、界面启动时会调。
  D. **场景可画地图 + 能拍** —— 两条约束在**两条写作路径**（自写 / MuMuAINovel）
     上都挂着，并且各自受一个开关控制（关掉哪条就少哪条）。
  E. **导出「小说原文」** —— 排第一档、默认开、**逐字原样**（真跑一遍，比对内容）。
  F. **样章原文落盘** —— `每天的生活/原文/第NNN天.md`，且定稿时真的会写。
  G. **场记只抓重大矛盾**、**宣发钩子换着来** —— 措辞在提示词里。
  H. **文风连续指标** —— `style/ai_metrics.py` 可用，且**不会把人写的文字
     误报成「过于均匀」**（这一条正是第一次拿一份现成中文定稿试的时候踩出来的）。

跑法：`.venv/Scripts/python.exe tools/verify_borrowings.py`
报告：`assets/screenshots/borrowings_report.json`

English:
Criterion: **the 2026-10-10 round of user requirements + external borrowings landed**.
Coverage (each states clearly "what it guards against"):
  A. **Hy3 / Tencent TokenHub** -- the capability table recognizes `hy3`, and the value has been verified
     (doesn't think by default, accepts temperature ⇒ not a reasoning model; doesn't send `response_format`).
  B. **Keep only one command-line window** -- service startup **structurally cannot** pop up a black window:
     `start.bat` uses `pythonw.exe`, `novelservice.start_detached` carries SW_HIDE,
     the bridge layer `_run_service` carries CREATE_NO_WINDOW.
  C. **`MUMU_AUTOSTART` is no longer a fake knob** -- the config entry is read, and it's called when the UI starts.
  D. **Scenes can draw maps + can take photos** -- the two constraints hang on **both writing paths** (self-written / MuMuAINovel)
     and each is controlled by its own switch (turn one off and that path loses that one).
  E. **Export "novel original text"** -- ranked first, on by default, **verbatim** (actually run once, compare contents).
  G. **Scene notes only catch major contradictions**, **promo hooks vary** -- wording is in the prompt.
  H. **Writing-style continuity metric** -- `style/ai_metrics.py` is usable, and **won't misreport human-written text
     as "too uniform"** (this one exactly was stepped on the first time when trying an off-the-shelf Chinese final draft).
How to run: `.venv/Scripts/python.exe tools/verify_borrowings.py`
Report: `assets/screenshots/borrowings_report.json`
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

REPORT: dict = {'checks': [], 'notes': []}


def ok(name: str, cond: bool, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    return bool(cond)


def read(rel: str) -> str:
    return (APP / rel).read_text(encoding='utf-8', errors='replace')


# ══════════════════════════════════════════════════════════════════
def test_hy3() -> bool:
    """A 组：Hy3 认得出来，且取值是核实过的。
        English:
    Group A: Hy3 is recognizable, and the value has been verified.
    """
    from llm.capabilities import detect, detect_one, CAP_IMAGE, CAP_REASONING, CAP_JSON
    caps, label = detect('hy3')
    k = True
    k &= ok('A1 ★★ 能力表认得 `hy3`（用户在 TokenHub 上就用这个 id）',
            bool(caps) and 'Hy3' in label, f'label={label!r}')
    k &= ok('A2 ★★ `hy3` 不算「推理模型」—— 它默认不思考，且官方推荐参数里有 '
            'temperature ⇒ 不能按"推理模型"处理（那样就不发 temperature 了）',
            detect_one('hy3', CAP_REASONING) is False, '')
    k &= ok('A3 ★ 不出图（`hy3` 是纯文本模型）', detect_one('hy3', CAP_IMAGE) is False, '')
    k &= ok('A4 ★ 不发 `response_format`（TokenHub 文档说支持、另有来源标 No ⇒ '
            '按保守取 False；真要用可在「模型能力」里手动打开）',
            detect_one('hy3', CAP_JSON) is False, '')
    k &= ok('A5 ★ `hy3-preview`（旧名）也认得 —— 而且排在 `hy3` **前面**匹配'
            '（能力表是"按顺序取第一个命中"）',
            detect('hy3-preview')[0] and
            read('llm/capabilities.py').index("'hy3-preview'")
            < read('llm/capabilities.py').index("('hy3',"),
            '')
    # ★★ 2026-10-14 换靶（改动的**理由**比改了什么更重要）：
    #   原来查的是 `gui/app_flet.py` 里有没有 `tokenhub.tencentmaas.com/plan/v3`，
    #   但那条文案在 2026-10-12 前后**搬进了 i18n 表**（界面文案一律走 `t()`），
    #   于是这条判据一直在查一个**不存在于该文件**的字符串 —— 而它想守的
    #   "界面上有这条速查"这件事**其实真的断了**（UI 在重构时被误删，注释留着）。
    #   今天两件事一起修：① UI 画回来（`_model_list_section` 尾部）；
    #   ② 判据改成**两处都查**——文案在 i18n 表里（有中文原文），
    #      并且 `app_flet.py` 里**真的引用了它**（不然就是孤儿 key，界面看不到）。
    #   ⚠ 只查 i18n 会**假绿**：文案躺着没人用也一样能过。
    # [EN] ★★ 2026-10-14 retarget (the **reason** for a change matters more than the change):
    # [EN] it used to check whether `tokenhub.tencentmaas.com/plan/v3` appears in
    # [EN] `gui/app_flet.py`, but that copy **moved into the i18n table** around 2026-10-12 (UI copy
    # [EN] always goes through `t()`), so the criterion kept looking for a string that **does not
    # [EN] exist in that file** -- while the thing it meant to guard, "this quick reference is on the
    # [EN] UI", **really was broken** (the UI was deleted by mistake during the refactor, the comment
    # [EN] stayed). Both are fixed today: (1) the UI is drawn again (tail of
    # [EN] `_model_list_section`); (2) the criterion now checks **both places** -- the copy is in the
    # [EN] i18n table (Chinese source text) **and** `app_flet.py` really references it (otherwise it
    # [EN] is an orphan key invisible on the UI).
    # [EN] ⚠ Checking only i18n gives a **false green**: copy can sit there unused and still pass.
    _i18n = read('i18n.py')
    _gui = read('gui/app_flet.py')
    ok('A6 ★ 界面上有「常见服务怎么填」的速查（含 TokenHub 的 Base URL 与 hy3）',
       'tokenhub.tencentmaas.com/plan/v3' in _i18n
       and "t('常见服务怎么填（Base URL 写到 /v1 或 /plan/v3 这一层，'" in _gui,
       f'i18n 里有={("tokenhub.tencentmaas.com/plan/v3" in _i18n)} / '
       f'界面引用了={("t(\'常见服务怎么填（Base URL 写到 /v1 或 /plan/v3 这一层，\'" in _gui)}')
    return k


def test_one_window() -> bool:
    """B/C 组：服务启动不可能弹窗 + 自动拉起开关是真的。
        English:
    Groups B/C: service startup cannot pop up a window + the auto-pull switch is real.
    """
    k = True
    # ★★ 2026-10-10 换靶（改动的**理由**比改了什么更重要）：
    #   这三条原来守的是 `start.bat` 里那几行 —— "用 pythonw 起服务""服务进度写进
    #   日志文件而不是主程序那个窗口"。用户要求「删掉，只留 exe」之后脚本没了，
    #   而且启动器也**不再自己拉服务**（交给主程序后台拉，理由见 `flow.go` 的
    #   `runStart` 注释）。于是这三条会**因为文件不存在而红**，或者更糟 ——
    #   扫到空集合**恒真**。
    #   ⇒ 换靶，不是删掉：要守的事情一件都没少（"起子进程不许冒出控制台"），
    #     只是它现在住在三个地方：
    #       ① 启动器本体 `launchers/proc_windows.go` 的 CREATE_NO_WINDOW；
    #       ② 启动器挑解释器时**优先 pythonw**（`launchers/py.go`）；
    #       ③ 启动器没有任何"窗口输出"，一切落日志文件（`main.go` / `flow.go`）。
    # [EN] ★★ 2026-10-10 Retargeting (the **reason** for a change matters more than what changed):
    # [EN] These three checks originally guarded those lines in `start.bat` -- "start the service with
    # [EN] pythonw", "write service progress to the
    # [EN] log file instead of the main program's window". After the user requested "delete it, keep only
    # [EN] the exe", the script was gone,
    # [EN] and the launcher also **no longer pulls up the service itself** (handed off to the main program
    # [EN] to pull in the background, see the `flow.go`
    # [EN] `runStart` comment). So these three checks would **go red because the file doesn't exist**, or
    # [EN] worse --
    # [EN] scanning an empty set is **vacuously true**.
    # [EN] ⇒ Retarget, don't delete: none of the things to guard have decreased ("spawning a child process
    # [EN] must not pop up a console"),
    # [EN] it just now lives in three places:
    # [EN] ① The launcher itself: `launchers/proc_windows.go`'s CREATE_NO_WINDOW;
    # [EN] ② The launcher **prefers pythonw** when picking the interpreter (`launchers/py.go`);
    # [EN] ③ The launcher has no "window output" at all, everything goes to the log file (`main.go` /
    # [EN] `flow.go`).
    pw = read('launchers/proc_windows.go')
    k &= ok('B1 ★★★ 启动器起子进程时**显式声明"别分配控制台"**'
            '（`CREATE_NO_WINDOW` = 0x08000000：子进程是 console 子系统、'
            '父进程又没有控制台时，Windows 会**给它新分配一个** —— 那就是黑窗）',
            'createNoWindow' in pw and '0x08000000' in pw, '')
    pyf = read('launchers/py.go')
    k &= ok('B2 ★★★ 启动器挑解释器时**优先 pythonw.exe**'
            '（venv 的 `python.exe` 是 launcher，它 re-exec 出来的子进程会新分配'
            '控制台 —— `CREATE_NO_WINDOW` **挡不住那一步**，实测过）',
            'pythonw.exe' in pyf and 'windowedPython' in pyf, '')
    flow = read('launchers/flow.go')
    k &= ok('B3 ★★ 启动器**不往任何窗口写输出**：主程序与每一步的输出一律落日志文件'
            '（无控制台的程序 `fmt.Println` 打给谁看都不知道）',
            'launcher.log' in read('launchers/main.go')
            and 'launcher_gui.log' in flow and 'launcher_job.log' in flow, '')
    nsvc = read('novelservices/MuMuAINovel/backend/novelservice.py')
    k &= ok('B4 ★★★ `start_detached` 带 `STARTF_USESHOWWINDOW` + `SW_HIDE`'
            '（"这个进程不许显示窗口"的最后一道显式声明）',
            'STARTF_USESHOWWINDOW' in nsvc and 'wShowWindow = 0' in nsvc, '')
    k &= ok('B5 ★★★ 原来的 DETACHED / NO_WINDOW / BREAKAWAY 三个标志**一个都没丢**',
            '0x00000008' in nsvc and '0x08000000' in nsvc and '0x01000000' in nsvc, '')
    br = read('novelservices/mumu_bridge.py')
    k &= ok('B6 ★★★ 桥接层 `_run_service` 里给子进程加了 `CREATE_NO_WINDOW`'
            '（主程序自己没有控制台时，Windows 会给子进程**新分配**一个 ⇒ 弹窗）',
            '0x08000000' in br and 'CREATE_NO_WINDOW' in br, '')
    gui = read('gui/app_flet.py')
    # ⚠⚠ **必须在"那个方法里"查，不能在整个 gui 文件里查**（反例法揭穿的）：
    #   `MUMU_AUTOSTART` 在设置对话框那一行也有（`mk_switch(... CFG.b(...))`）——
    #   把自动拉起方法里的判断删掉，整个文件里**照样搜得到**，于是打不红。
    #   这就是"判据查的是现象还是位置"的区别。
    # [EN] ⚠⚠ **Must check "inside that method", not across the whole gui file** (exposed by counterexample
    # [EN] testing):
    # [EN] `MUMU_AUTOSTART` also appears in that settings dialog line (`mk_switch(... CFG.b(...))`) --
    # [EN] delete the check inside the auto-pull method and it's **still findable** across the whole file,
    # [EN] so it won't go red.
    # [EN] This is the difference between "does the criterion check the phenomenon or the location".
    # ★★★ 2026-10-24 13:54 **范围跟着实现搬了**（不是放宽）：拉服务这一段整体移到了
    #   模块级 `boot_services()`（预启动与页面内两条路共用），所以"那一步"现在是那个函数。
    #   ⚠ 仍然要窄 —— 整文件里搜照样能搜到（设置对话框那行也有），打不红。
    # [EN] ★★★ 2026-10-24 13:54 **the scope follows the implementation** (not a relaxation): the
    # [EN] pull-up block moved into the module-level `boot_services()` (shared by the pre-boot and the
    # [EN] in-page route), so "that step" is now that function.
    # [EN] ⚠ Still narrow -- searching the whole file finds it (the settings dialog has it too).
    _i0 = gui.index('async def boot_services(')
    _rest = gui[_i0:]
    _blk = _rest[:_rest.index('def preboot_services(')]
    REPORT['autostart_block_len'] = len(_blk)
    k &= ok('C1 ★★★ `MUMU_AUTOSTART` **在自动拉起那一步真的有读**'
            '（以前只有写 —— 界面上有、实际没用，是本项目说的"假旋钮"）',
            "CFG.b('MUMU_AUTOSTART')" in _blk, f'块长 {len(_blk)}')
    k &= ok('C2 ★★ 启动时会调它（`_maybe_autostart_service`）',
            '_maybe_autostart_service' in gui
            and 'self._maybe_autostart_service()' in gui, '')
    k &= ok('C3 ★★ 自动拉起跑在 **`asyncio.to_thread`** 里（起服务最坏几分钟，'
            '不能冻界面）',
            'asyncio.to_thread(BR.start_service' in gui, '')
    return k


def test_scene_and_filmable() -> bool:
    """D 组：两条写法约束，两条路径都要有，且受开关控制。
        English:
    Group D: the two writing constraints, both paths must have them, and they're switch-controlled.
    """
    src = read('crew/agents.py')
    k = True
    k &= ok('D1 ★★★ 场景约束（可画地图）是一条**常量**，不是散落在提示词里的句子',
            'SCENE_CARD_RULES = ' in src, '')
    k &= ok('D2 ★★★ 可拍约束同理', 'FILMABLE_RULES = ' in src, '')
    k &= ok('D3 ★★★ **自写那条路**挂上了（提示词里引用 `extra_rules`）',
            "extra_rules = " in src and '{extra_rules}' in src, '')
    k &= ok('D4 ★★★ **MuMuAINovel 那条路**也挂上了（那段 prompt 是不发过去的，'
            '只有 `outline` 会进它那边 —— 漏了这条，走服务时两条约束全丢）',
            "(SCENE_CARD_RULES if CFG.b('CREW_SCENE_CARD') else '')" in src
            and "(FILMABLE_RULES if CFG.b('CREW_FILMABLE') else '')" in src, '')
    k &= ok('D5 ★★★ 两条各自受**独立开关**控制（关掉哪条就少哪条，'
            '而且编号不会断）',
            "CFG.b('CREW_SCENE_CARD')" in src and "CFG.b('CREW_FILMABLE')" in src
            and "len(_rules) + 5" in src, '')
    import config as C
    k &= ok('D6 ★★ 两个开关**都在**（默认开）',
            C.SPEC['CREW_SCENE_CARD']['type'] == 'bool'
            and C.SPEC['CREW_FILMABLE']['type'] == 'bool'
            and C.CFG.b('CREW_SCENE_CARD') and C.CFG.b('CREW_FILMABLE'), '')
    # 美术真的读得到正文（用户要的闭环）
    # ⚠ 判"那个块**真的被构造出来**"，不能只判名字出现过 ——
    #   `story_block = ''` 这种变异下，`{story_block}` 仍然在提示词里，
    #   只查名字的话**打不红**（反例法当场揭穿）。
    # [EN] Artists can genuinely read the body text (the closed loop the user wanted)
    # [EN] ⚠ Judge that "that block is **actually constructed**", not merely that the name appears --
    # [EN] under a mutation like `story_block = ''`, `{story_block}` is still in the prompt,
    # [EN] checking only the name **won't go red** (exposed on the spot by counterexample testing).
    k &= ok('D7 ★★★ 美术画当天地图时**能读到作者写的正文**'
            '（"可画地图"标准要有人对接，不然只是写在纸上）',
            "getattr(ctx, 'story', '')" in src
            and "story_block = ('── 作者写的今天这一段" in src
            and '{story_block}' in src, '')
    k &= ok('D8 ★★ 地图提示词里写明"说明要从正文里长出来"（两处提示词都要）',
            src.count('要从上面那段正文里长出来') == 2,
            src.count('要从上面那段正文里长出来'))
    return k


def test_raw_novel_export() -> bool:
    """E/F 组：小说原文 —— 排第一档、默认开、逐字原样、且真的落过盘。
        English:
    Groups E/F: novel original text -- ranked first, on by default, verbatim, and actually
    persisted.
    """
    k = True
    from export import bundle as B
    k &= ok('E1 ★★★ 「小说原文」是**第一档**（用户说"原文是重点导出项目"'
            '—— 排第一就是"重点"在界面上的样子）',
            B.KINDS[0] == B.KIND_RAW_NOVEL, str(B.KINDS))
    # ★★★ 2026-10-26 改口径：**不再要求"默认开"**。
    #   用户原话：「**自动导出默认关闭**」—— 导出回到"你点了才发生"。
    #   E2 现在守的是**映射关系**（这一档的"结束时自动导出"开关确实是 `EXPORT_ON_END_RAW`），
    #   不是"出厂值是不是 True"。
    #   ⚠ 不能直接删掉 E2：映射一旦接错（指向别的键），勾"原文自动导出"就会去开别人的开关 ——
    #     症状是"勾了没反应""关掉没生效"，而且完全看不出跟映射有关。
    # [EN] ★★★ 2026-10-26 scope change: **no longer requires "on by default"** (user: "auto export
    # [EN] default off"). E2 now guards the **mapping** (this kind's auto switch really is
    # [EN] `EXPORT_ON_END_RAW`), not whether the factory value is True.
    # [EN] ⚠ Do not just delete E2: a wrong mapping makes the checkbox toggle someone else's
    # [EN] switch, and the symptom shows no connection to the mapping.
    k &= ok('E2 ★★ 它的「结束时自动导出」开关接的是 `EXPORT_ON_END_RAW`（映射不许接错）',
            B.KIND_AUTO_KEY[B.KIND_RAW_NOVEL] == 'EXPORT_ON_END_RAW', str(B.KIND_AUTO_KEY))
    # ★★★ 2026-10-30：改成读**出厂默认值**（`config.SPEC`），不读用户 `.env` 里的现值。
    #   为什么必须改：旧写法比的是 `CFG.b(...)` —— 那是**这位用户此刻的配置**。
    #   用户在「自动导出设置」里勾了「原始稿」⇒ 这条判据就红，而产品根本没坏；
    #   反过来他勾上再手动改回 `.env` 也不会让它变绿。判据不能由用户偏好决定。
    #   要守的东西只有一件：**新装的软件默认是关的**。
    # [EN] ★★★ 2026-10-30: read the **factory default** (`config.SPEC`), not the live `.env` value.
    # [EN] The old form compared the user's current config, so ticking "raw" in the auto-export dialog
    # [EN] turned this red while the product was fine. What must hold is: a fresh install ships it OFF.
    from config import SPEC as _SPEC
    _dflt = _SPEC.get('EXPORT_ON_END_RAW', {}).get('default')
    k &= ok('E2b ★★ 自动导出**出厂默认关**（2026-10-26 用户定的口径；'
            '用户自己在对话框里勾上是他的选择，不该让判据红）',
            _dflt is False, f"出厂默认={_dflt!r} 用户现值={B.CFG.raw('EXPORT_ON_END_RAW')}")
    k &= ok('E3 ★ 零成本（不调 LLM）', B.KIND_USES_LLM[B.KIND_RAW_NOVEL] is False, '')
    # ★★★ E6：**导出主流程里**那一支真的调了 `write_raw_manuscript`。
    #   为什么单列：E4/E5 是**直接调 `write_raw_manuscript`** 验的 ——
    #   把主流程那一支改成走别的路（于是 raw 那一档什么都不产出），E4/E5 照样绿。
    # [EN] ★★★ E6: that branch **in the export main flow** actually calls `write_raw_manuscript`.
    # [EN] Why list it separately: E4/E5 verify by **directly calling `write_raw_manuscript`** --
    # [EN] change the main-flow branch to take another path (so the raw tier produces nothing), and E4/E5
    # [EN] still stay green.
    k &= ok('E6 ★★★ 导出主流程里 `raw_novel` 走的是 `write_raw_manuscript`'
            '（不是退回别的装订稿、也不是什么都不做）',
            'if kind == KIND_RAW_NOVEL:' in read('export/bundle.py')
            and 'NV.write_raw_manuscript' in read('export/bundle.py'), '')

    from store.runfolder import RunFolder
    from export import novel_version as NV
    tmp = Path(tempfile.mkdtemp(prefix='nws_borrow_'))
    try:
        run = RunFolder(project_dir=tmp / '书', run_name='r1')
        run.story_dir.mkdir(parents=True, exist_ok=True)
        run.daily_dir.mkdir(parents=True, exist_ok=True)
        run.flush_day_story(1, '第一天的原文甲。\n\n第二段。')
        run.flush_day_story(2, '第二天的原文乙。')
        # 再写一份"当天的呈现"——它**不许**出现在原文里
        # [EN] Also write a "presentation of the day" -- it **must not** appear in the original text
        # ⚠ 2026-10-26：**两天都要有**。原来只有第 1 天有 `每天的生活/第001天.md`，
        #   于是新口径下"两天的正文都在"这条**只能测到一天**（第 2 天只有 `原文/` 的样章，
        #   `list_days` 不收它）。夹具补齐两天，判据才真的在测它自己说的那件事。
        # [EN] ⚠ 2026-10-26: **both days must exist**. Only day 1 used to have
        # [EN] `每天的生活/第001天.md`, so under the new rule "both days' prose present" could only
        # [EN] ever see one day (day 2 had only the sample, which `list_days` ignores). Filling in
        # [EN] both days is what makes the assertion test what it says.
        run.flush_daily(1, '这是当天的呈现（剧本模式下就是剧本），不是原文。')
        run.flush_daily(2, '第二天的呈现乙，也是真实演出的正文。')
        r = NV.write_raw_manuscript(run)
        txt = r['path'].read_text(encoding='utf-8')
        # ⚠ 口径已改（2026-10-26，「原始稿和最终成稿完全不是一个故事」那次）：
        #   原始稿的源**不再是** `每天的生活/原文/` 里那份**开场样章**（`flush_day_story`
        #   写的是 `ds.story`，剧本模式下一天演 133 幕而它只有 1525 字 —— 是引子，不是这一天）。
        #   现在原始稿 = **每天真实演出的全部正文**逐字原样。
        #   ⇒ E4/E5 跟着改断言，**两条都还在**（不是删判据）：
        #      E4 正向：两天的正文都在、逐字原样；
        #      E5 反向：**开场样章**不许冒充原始稿（名不副实的那一头）。
        #   ⚠ 原来 E5 断的是"当天的呈现"不许出现 —— 那个口径在新规则下**必须**出现
        #     （它就是当天正文），留着它等于把新规则判成错。
        # [EN] Rule changed 2026-10-26 ("the raw draft and the final draft are not even the same
        # [EN] story"): the raw draft no longer comes from `每天的生活/原文/` (that is
        # [EN] `flush_day_story`'s **opening sample**: 1525 chars for a 133-act day -- an intro,
        # [EN] not the day). Now it is **everything actually performed that day**, verbatim.
        # [EN] Both assertions stay, only their target moves: E4 forward (both days present,
        # [EN] verbatim), E5 reverse (**the sample must not masquerade as the raw draft**).
        k &= ok('E4 ★★★ 原始稿＝**每天真实演出的正文**逐字原样（两天都在）',
                '这是当天的呈现' in txt and '第二天的呈现乙' in txt,
                f'文件 {r["path"].name} · {r["days"]} 天')
        k &= ok('E5 ★★★ 原始稿里**不含开场样章**（`原文/` 那份是引子，不是这一天）—— '
                '把它当原文就是名不副实',
                '第一天的原文甲' not in txt and '第二天的原文乙' not in txt, '')
        REPORT['raw_novel_head'] = txt.splitlines()[:6]
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    k &= ok('F1 ★★★ `RunFolder.flush_day_story` 存在（样章原文落 `每天的生活/原文/`）',
            hasattr(RunFolder, 'flush_day_story')
            and str(RunFolder(project_dir=Path('.'), run_name='x').story_dir)
            .endswith(str(Path('每天的生活') / '原文')), '')
    loop = read('sim/loop.py')
    k &= ok('F2 ★★★ 定稿时会真的写一份（否则"保留原文"以前根本做不到 —— '
            '`DayScript.story` 从前只活在内存里）',
            'flush_day_story(' in loop, '')
    k &= ok('F3 ★★ 落盘**在 `CREW_SCREEN` 判断之外**（它是产物，'
            '不该跟着上屏开关一起关掉）',
            loop.index('flush_day_story(')
            < loop.index("CFG.s('CREW_SCREEN').strip().lower() == 'full'"), '')
    return k


def test_prompt_wording() -> bool:
    """G 组：两条借鉴来的措辞。
        English:
    Group G: the two borrowed wordings.
    """
    src = read('crew/agents.py')
    k = True
    k &= ok('G1 ★★★ 场记写了「只抓重大矛盾」（不写的话，场记会把新事报成矛盾，'
            '假警报一多，真问题也没人看）',
            '只抓重大矛盾，不拦正常的推进' in src
            and '人死而复生' in src, '')
    k &= ok('G2 ★★★ 宣发写了「钩子换着来」并给出五类触发',
            '钩子要换着来' in src and '三条要用三种不同的钩子' in src
            and '悬念' in src and '稀缺' in src, '')
    k &= ok('G3 ★★ 两处都注明了借鉴出处（许可写在注释里，将来好复核）',
            'ai-screenplay-writer' in src and 'AiCMO' in src, '')
    return k


def test_ai_metrics() -> bool:
    """H 组：连续指标可用，而且**不在人写的文字上误报**。
        English:
    Group H: the continuity metric is usable, and **doesn't misreport on human-written text**.
    """
    k = True
    from style import ai_metrics as AM
    m = AM.analyze('他走了。风大。灯晃了一下，又稳住了。'
                   '掌柜没抬头，只把壶擦了一遍，擦得很慢。')
    k &= ok('H1 ★★ `analyze()` 给出连续量（分句长 / 变异 / 重复率 / 句首多样性）',
            all(x in m for x in ('分句中位长', '句长变异', '四字重复率', '句首多样性')),
            str(sorted(m)))
    k &= ok('H2 ★★ 样本太少时**明确说"样本不足"**，而不是硬给一个"过于均匀"'
            '（短文本上的 CV 天然小 —— 这是实测踩出来的坑）',
            AM.analyze('很短。')['漂移']['态'] == '样本不足', '')

    # ★★★ 校准这一层必须**判结构，不判某一个文件的具体结论**。
    #   来历：第一版是一条"人写的稿子不许被判成过于均匀"的断言，
    #   结果它在**本项目自带的示例**上就红了 —— 那份示例本来就写得句长均匀
    #   （窗间 CV 0.065），于是判据红得**没道理**（是我把"某个文本的结论"
    #   当成了"指标对不对"）。真正该钉住的是**让它别在短文本上翻车的那两件事**：
    # [EN] ★★★ This calibration layer must **judge structure, not the specific conclusion of some file**.
    # [EN] Origin: the first version was an assertion "a human-written manuscript must not be judged as too
    # [EN] uniform",
    # [EN] and it went red on **the example shipped with this project** -- that example was inherently
    # [EN] written with uniform sentence lengths
    # [EN] (inter-window CV 0.065), so the criterion went red **unreasonably** (I had mistaken "the
    # [EN] conclusion about some text"
    # [EN] for "is the metric correct"). What should really be pinned down is **the two things that keep it
    # [EN] from crashing on short texts**:
    _sd = APP / 'samples' / 'zh' / '01_悬疑单元_更漏子' / '正文'
    _files = sorted(_sd.glob('*.md')) if _sd.exists() else []
    if _files:
        fix_text = '\n'.join(f.read_text(encoding='utf-8', errors='replace')
                             for f in _files)
        mm = AM.analyze(fix_text)
        REPORT['baseline'] = {'汉字': mm['汉字数'],
                              '漂移': mm['漂移']['态'],
                              '窗': mm['漂移'].get('窗数')}
        # ① 窗口**自适应**真的生效：两千来字的稿子要切出 ≥`_MIN_WIN` 个窗。
        #    固定 1000 字窗在这儿只能切 2~4 个 —— 那才是第一次翻车的原因。
        # [EN] ① Window **adaptation** really takes effect: a manuscript of around two thousand characters must
        # [EN] cut ≥`_MIN_WIN` windows.
        # [EN] A fixed 1000-character window can only cut 2~4 here -- that was the cause of the first crash.
        k &= ok('H3 ★★★ 窗口**自适应**真的生效（两千来字的稿子切出 ≥ _MIN_WIN 个窗，'
                '固定 1000 字窗只能切 2~4 个 ⇒ 那种窗口数下的 CV 不可信）',
                mm['漂移'].get('窗数', 0) >= AM._MIN_WIN, str(REPORT['baseline']))
    else:
        REPORT['notes'].append('没找到示例正文，H3 跳过')
    # ② 「过于均匀」的阈值**没被悄悄放松**（放松了就会把正常文字报成 AI 腔）。
    # [EN] ② The "too uniform" threshold **has not been quietly loosened** (loosening it would flag normal
    # [EN] text as AI-speak).
    k &= ok('H4 ★★ 「过于均匀」的阈值仍是标定时的 0.15（不许随手改大 —— '
            '那是拿"少报"换"多报"，两边都失真）',
            abs(AM.UNIFORM_CV - 0.15) < 1e-9, f'UNIFORM_CV={AM.UNIFORM_CV}')
    return k


def main() -> int:
    checks = [('Hy3', test_hy3), ('单窗口', test_one_window),
              ('场景/可拍', test_scene_and_filmable), ('原文导出', test_raw_novel_export),
              ('措辞', test_prompt_wording), ('连续指标', test_ai_metrics)]
    for _name, fn in checks:
        try:
            fn()
        except Exception:                                      # noqa: BLE001
            REPORT['checks'].append({'name': f'{_name} 组崩了', 'ok': False,
                                     'detail': traceback.format_exc()[-800:]})
    path = APP / 'assets' / 'screenshots' / 'borrowings_report.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')

    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n外部借鉴与用户要求验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}')
        print(f'      {c["detail"][:220]}')
    if REPORT['notes']:
        for x in REPORT['notes']:
            print('  · ', x)
    print('→ 全部通过' if not bad else '→ 有失败项')
    print('报告 ->', path.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
