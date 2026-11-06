# -*- coding: utf-8 -*-
"""验证：**创作服务（MuMuAINovel）接入**（2026-10-09）。

用户这一轮的四件事，这一支判据全覆盖：

  1. 小说作家**可以**调用 MuMuAINovel 来写（开关式 + 自动回退），
     而不是只能自己写；
  2. 「其他 Agent 能不能也沾它的光」—— 查过了，结论写进 `服务说明.md`，
     接进来的是 `polish()`（**上游还差一个提示词模板，尚未可用**，见 C 组）；
  3. MuMuAINovel 的相关配置**进了天机**，且**注明来自 MuMuAINovel + 写出上游地址**；
  4. MuMuAINovel 里本项目不用的部分**已清掉**（前端/打包/CI），
     目录**拍平**（`repo/backend` → `backend`）。

判据分层（每层都要能红，见 `developers/mutate_mumu_service.py`）：

  A **源码级**：SPEC 键 / 页签表 / 保存分支 / 桥接层分层与保险丝 / 目录形态
  B **真机**：打开天机 → 页签在、写得明出处、必配项都在；改一项 → 保存 → 真的落盘
  C **降级**：服务没起时**不许抛异常**（设置要能打开、写小说要能回退）
  D **端到端**（**服务真在跑才跑**，否则如实报 SKIP）

用法：.venv\\Scripts\\python.exe tools/verify_mumu_service.py
产出：assets/screenshots/mumu_service_report.json

English:
Verification: **Creative Service (MuMuAINovel) integration** (2026-10-09).
The user's four items this round are fully covered by this branch's criteria:
  1. The novel writer **can** call MuMuAINovel to write (switch-style + automatic fallback),
     instead of only being able to write by itself;
  2. "Can other Agents also benefit from it" -- checked, conclusion written into `服务说明.md`,
     what was integrated is `polish()` (**upstream is still missing a prompt template, not yet usable**, see group C);
  3. MuMuAINovel's related config **has entered Tianji**, and **notes that it comes from MuMuAINovel + writes out the upstream address**;
  4. The parts of MuMuAINovel not used by this project **have been removed** (frontend/packaging/CI),
     the directory is **flattened** (`repo/backend` -> `backend`).
Criteria layers (each layer must be able to go red, see `developers/mutate_mumu_service.py`):
  A **Source-level**: SPEC keys / tab table / save branches / bridge layer layering and fuses / directory shape
  B **Real machine**: open Tianji -> tabs present, sources written clearly, all required items present; change one item -> save -> actually persisted to disk
  C **Degradation**: when the service is not up, **must not throw exceptions** (settings must be openable, novel writing must be able to fall back)
  D **End-to-end** (**only runs when the service is really running**, otherwise report SKIP truthfully)
Usage: .venv\\Scripts\\python.exe tools/verify_mumu_service.py
Output: assets/screenshots/mumu_service_report.json
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown                        # noqa: E402

from config import CFG, SPEC                                   # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('SHOW_OPENING', 'false')
# ⚠ 起界面就会走 `app.main()` → 能力校验 → `CFG.save()`；**从头到尾**禁写真实 .env
# [EN] ⚠ Launching the UI runs `app.main()` → capability check → `CFG.save()`; writing the real .env is
# [EN] forbidden **from start to finish**
VU.redirect_env_writes()

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from gui.app_flet import NovelWorldApp                         # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': [], 'skipped': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


def skip(name: str, why: str) -> None:
    report['skipped'].append({'name': name, 'why': str(why)[:200]})
    print(f'SKIP  {name}   [{why}]')


GROUP = '创作服务 · MuMuAINovel'   # 2026-10-10 随页签改名
# [EN] 2026-10-10 renamed along with the tab
MUMU_KEYS = ('MUMU_ENABLED', 'MUMU_FOR_NOVELIST', 'MUMU_AUTOSTART',
             'MUMU_TIMEOUT_SECONDS', 'MUMU_TARGET_WORDS',
             'MUMU_ENABLE_ANALYSIS', 'MUMU_ANALYSIS_MODEL', 'MUMU_SKILL_KEY')
UPSTREAM = 'https://github.com/xiamuceer-j/MuMuAINovel'


# ══════════════════════════════════════════════════════════════════
#  A. 源码级
# [EN] A. Source level
# ══════════════════════════════════════════════════════════════════
def test_source() -> bool:
    ok_ = True
    import gui.app_flet as GF
    src = inspect.getsource(GF)

    # ── A1 SPEC ──
    missing = [k for k in MUMU_KEYS if k not in SPEC]
    ok_ &= ok('A1 ★★ 8 个 MuMuAINovel 旋钮都在 SPEC 里（有配置项）',
              not missing, f'缺：{missing}')
    wrong_group = [k for k in MUMU_KEYS
                   if k in SPEC and SPEC[k].get('group') != GROUP]
    ok_ &= ok('A1b ★★ 它们**归在同一个组**（天机里才有一页装它们）',
              not wrong_group, f'组不对：{wrong_group}')
    # **每一个都必须被产品源码读到过** —— 与 `verify_config_sweep` 的 D1 同一条纪律：
    # 挂着拧不动的旋钮就是负债。
    # [EN] **Every one of them must be read by product source code** — same discipline as D1 of
    # [EN] `verify_config_sweep`:
    # [EN] A knob that's mounted but won't turn is a liability.
    zero = [k for k in MUMU_KEYS if f"'{k}'" not in src]
    ok_ &= ok('A1c ★★★ 8 个旋钮**每一个都被界面读过/写过**（不许有假旋钮）',
              not zero, f'界面里没用到：{zero}')

    # ── A2 重启标记 ──
    # [EN] ── A2 restart flag ──
    restart = sorted(k for k in MUMU_KEYS if SPEC[k].get('restart'))
    ok_ &= ok('A2 ★★ 只有 `MUMU_AUTOSTART` 标了 restart（它在启动时才读一次；'
              '其余五项都是"每次现读"，标了会骗人）',
              restart == ['MUMU_AUTOSTART'], f'实际：{restart}')
    # 登记了 friendly label，否则那句"要重启"会露出配置键名
    # [EN] A friendly label is registered, otherwise that "needs restart" message leaks the config key name
    ok_ &= ok('A2b ★ 重启提示里有它的中文名（不至于露出 `MUMU_AUTOSTART`）',
              "'MUMU_AUTOSTART':" in src and '自动拉起创作服务' in src, '')

    # ── A3 页签 ──
    # ★★ 2026-10-10 用户改名并重排：「创作服务」→「创作服务LLM设定」，
    #    **移到「AI模型配置」右边**（它不再是"排最后"的那个增强项页签）。
    # [EN] ── A3 tabs ──
    # [EN] **moved to the right of "AI模型配置"** (it's no longer the "last" enhancement tab).
    # ★★ 2026-10-12：**页签撤掉了** —— 「创作服务」整块搬进了「AI模型配置」
    #   （用户原话：「你把现在的两个LLM设置合并到一起」）。所以判据从
    #   "有那个页签"改成"那一块在合并后的页里"。
    # [EN] ★★ 2026-10-12: the **tab was removed** -- the whole "Creation Service" block moved into
    # [EN] "AI Model Config" (user's words: "merge the current two LLM settings into one"). So the
    # [EN] criterion changes from "that tab exists" to "that block is inside the merged page".
    # ★★ 2026-10-12（第二轮）：MuMuAINovel **拆成独立页签**了（用户：
    #   「MuMuAINovel还是拆分成一个单独的配置Tab里 就叫做外部小说服务配置」）。
    #   判据跟着改口径：从"那一块在「AI模型配置」页里"改成"**它是自己的一页**，
    #   而且位置在「AI模型配置」右边"。
    # ★★ 2026-10-16：MuMuAINovel 并入「外部创作服务」（与 PlotPilot + PenShot 同页），
    #   原独立「外部小说服务配置」页删除；本判据改为查「外部创作服务」页 +
    #   `_external_services_block` 内部调用 `_mumu_block`。
    # [EN] ★★ 2026-10-12 (round two): MuMuAINovel is now **its own tab** (user: "still split it into
    # [EN] its own configuration tab, called External Novel Service Configuration"). The criterion
    # [EN] changes accordingly: from "that block is inside 'AI Model Config'" to "it **is its own page**,
    # [EN] positioned to the right of 'AI Model Config'".
    # ⚠⚠ 2026-10-23 **改口径**：这一页现在把三个服务拆成**左侧三个子页签**，
    #   MuMu 那一段由 `*_mumu_block(),` 展开改成了 `_mumu_items = _mumu_block()`
    #   （先取列表、去掉页首标题、再交给 `_side_tabs`）⇒ 老锚点必然红。
    #   **意图没变**（MuMu 的配置仍然并进这一页），所以换个形式守：
    #     ① 这一页还是独立一页（`_external_services_block` 在 tab_defs 里）；
    #     ② 它**确实调用了** `_mumu_block()`（不再是展开语法，就查调用）；
    #     ③ 调用结果**确实交给了左侧页签**（`('mumu', ...` 那一条）——
    #        只判 ② 会漏掉"取了却没用"，那才是真的丢内容。
    # [EN] ⚠⚠ 2026-10-23 **changed the yardstick**: this page now splits the three services
    # into **left-hand sub-tabs**, and the MuMu segment moved from `*_mumu_block(),` to
    # `_mumu_items = _mumu_block()` (take the list, drop the heading, hand it to `_side_tabs`)
    # => the old anchor necessarily goes red. The **intent is unchanged** (MuMu's config is
    # still folded into this page), so re-express it: (1) it is still its own page;
    # (2) it **really calls** `_mumu_block()`; (3) the result **really goes to the left tabs**
    # (`('mumu', ...`). Judging only (2) would miss "taken but unused" -- which is the real
    # way content gets lost.
    _ext_seg = ''
    _ei = src.find('def _external_services_block(')
    if _ei >= 0:
        _ej = src.find('        # ★★ 2026-10-12：模型登记表这一块', _ei)
        _ext_seg = src[_ei:_ej if _ej > _ei else _ei + 40000]
    ok_ &= ok('A3 ★★ 「外部创作服务」是**独立的一页**，且内部并入 MuMuAINovel'
              '（调 `_mumu_block()` 并把结果交给左侧页签）',
              ('(t("外部创作服务"), _external_services_block()),' in src
               and '_mumu_block()' in _ext_seg
               and "('mumu', t('MuMuAINovel')" in _ext_seg),
              f"调用={'_mumu_block()' in _ext_seg} "
              f"交给页签={chr(40) + chr(39) + 'mumu' + chr(39) in _ext_seg}")
    i_llm = src.find('(t("AI模型配置"), [')
    i_mumu = src.find('(t("外部创作服务"), _external_services_block()),')
    i_appear = src.find('(t("界面外观"), _opacity_block())')
    # ⚠ 位置只比**顺序**（llm < mumu < appear）：这时"紧挨"已经不是要求了
    #   —— 用户要的是"拆成单独一页"，它后面跟哪一页都行。
    # [EN] ⚠ Position compares **order only** (llm < mumu < appear): adjacency is no longer the
    # [EN] requirement -- the user wants "its own page", and whatever follows is fine.
    ok_ &= ok('A3b ★★★ 它排在「AI模型配置」**右边**（两者都是配服务，挨着放）',
              i_llm > 0 and i_mumu > i_llm and i_appear > i_mumu,
              f'llm@{i_llm} mumu@{i_mumu} appear@{i_appear}')
    # ⚠ 判"没有那个页签"要查**页签定义行**（`(t("创作服务LLM设定"),`），
    #   不能查"源码里出现过这七个字" —— 注释里也会提到它（"原来那一页撤掉了"），
    #   查全文的话**把页签加回去它也不会红**（第一版就是这么写的）。
    # [EN] ⚠ To judge "that tab is gone", check the **tab definition line**
    # [EN] (`(t("创作服务LLM设定"),`), not "those characters appear in the source" -- comments mention
    # [EN] it too ("the former page was removed"), so a whole-file check would **stay green even if the
    # [EN] tab were added back** (the first version did exactly that).
    _no_old_tab = all(
        f'(t("{_q}创作服务LLM设定{_q}")' not in src for _q in ('', "'", '"'))
    ok_ &= ok('A3c ★★ 天问里**不再**有独立的「创作服务LLM设定」页签定义行',
              _no_old_tab, '')

    # ── A4 出处与上游地址（用户硬要求：注明来源 + 写出项目地址）──
    # [EN] ── A4 origin and upstream address (user hard requirement: cite the source + write out the
    # [EN] project address) ──
    ok_ &= ok('A4 ★★★ 页面上写明**来自 MuMuAINovel**（用户点名要求）',
              '来自 MuMuAINovel（外部写小说服务）' in src, '')
    # ⚠ 不能只查"整个源码里出现过这个 URL" —— 注释里也有一份，
    #   把界面上那个 `ft.Text` 抹掉，源码里照样找得到（反例法当场揭穿）。
    #   要查的是**它在一个 `ft.Text(...)` 里**（= 真的画得出来）。
    # [EN] ⚠ Can't just check "this URL appears somewhere in the source" — it also appears in a comment,
    # [EN] erase that `ft.Text` from the UI and it's still findable in the source (counterexample method
    # [EN] exposes it on the spot).
    # [EN] What must be checked is that **it's inside an `ft.Text(...)`** (= it actually gets drawn).
    ok_ &= ok('A4b ★★★ 页面上**画出了**上游项目地址（写成 `ft.Text`，用户点名要求）',
              f'ft.Text("{UPSTREAM}"' in src.replace("'", '"'), '')
    ok_ &= ok('A4c ★ 也标了许可与本地说明的位置',
              'GPL-3.0' in src and 'novelservices/MuMuAINovel/服务说明.md' in src, '')

    # ── A5 保存分支：本程序那几项真的写进 CFG ──
    # [EN] ── A5 save branches: this program's items actually get written into CFG ──
    not_saved = [k for k in MUMU_KEYS if f"CFG.set('{k}'" not in src
                 and f'CFG.set("{k}"' not in src]
    ok_ &= ok('A5 ★★★ 保存时 8 个旋钮**每一项都写回配置**（改了要算数）',
              not not_saved, f'没写回：{not_saved}')

    # ── A6 服务自己的 .env 走桥接层写 ──
    # [EN] ── A6 the service's own .env goes through the bridge layer to be written ──
    ok_ &= ok('A6 ★★ 保存时把服务自己的参数交给 `save_service_env()`'
              '（写的是**它的** backend/.env，不是本程序的 .env）',
              'save_service_env(' in src, '')

    # ── A7 桥接层 ──
    # [EN] ── A7 bridge layer ──
    from novelservices import mumu_bridge as BR
    for fn in ('service_status', 'generate_chapter', 'polish', 'save_service_env',
               'read_service_env', 'ensure_project'):
        ok_ &= ok(f'A7 桥接层有 `{fn}()`', callable(getattr(BR, fn, None)), '')
    # ★ 分层：服务层**不该认识 `CFG`** —— 认识了就两头绑死，
    #   那个模块也就不能再在"没有本程序配置"的场合单独跑（比如包装成命令行）。
    # [EN] ★ Layering: the service layer **must not know about `CFG`** — if it does, both ends are bound
    # [EN] tight,
    # [EN] and that module can no longer run standalone in situations "without this program's config" (e.g.
    # [EN] wrapped as a command line).
    bsrc = Path(BR.__file__).read_text(encoding='utf-8')
    #   ⚠ 判据就是**"全文不许出现 CFG"**。第一版写成
    # [EN] ⚠ The criterion is **"the full text must not contain CFG"**. The first version was written as
    #   `'CFG' not in bsrc.replace('from config import CFG', '')` ——
    #   那句 replace 在原文件里**本来就是空操作**，等于自己给自己留了个后门：
    #   反例法往文件里加一行 `from config import CFG` 时，它照样绿。
    # [EN] that replace is **a no-op to begin with** in the original file, effectively leaving itself a
    # [EN] backdoor:
    # [EN] when the counterexample method adds a line `from config import CFG` to the file, it still passes
    # [EN] green.
    ok_ &= ok('A7b ★★ 桥接层**不许出现 `CFG`**（服务层与配置层解耦；'
              '胶水只在 `crew/agents.py` 一处）',
              'CFG' not in bsrc, '')
    ok_ &= ok('A7c ★★ 桥接层的服务端写盘**带 sink 保险丝**'
              '（验证脚本点保存不会写用户的服务配置）',
              'NWS_ENV_SINK' in bsrc and 'redirect_save' in bsrc, '')

    # ── A8 小说作家接了它，而且是开关式 + 回退 ──
    # [EN] ── A8 the novel writer hooked it up, and it's switch-based + fallback ──
    import crew.agents as CA
    asrc = inspect.getsource(CA)
    ok_ &= ok('A8 ★★★ 小说作家真的接上了（不是只加了个配置项）',
              '_mumu_sample' in asrc and 'mumu_bridge' in asrc, '')
    ok_ &= ok('A8b ★★★ 它是**开关式**：默认关时完全不走桥接',
              "CFG.b('MUMU_ENABLED')" in asrc, '')
    ok_ &= ok('A8c ★★★ 失败**自动回退**到自写路径（不许把这一天的戏弄丢）',
              '回退自写' in asrc and '_with_degrade' in asrc, '')
    ok_ &= ok('A8d ★★ 「收工整理稿」**不走它**（那一步要求"今天没发生的'
              '一个字都不许加"，自由写作做不对）',
              '_transcribe' in asrc and 'if str(transcribe or \'\').strip():' in asrc, '')
    ok_ &= ok('A8e ★★ 跑在**子线程**里（最长 15 分钟的等待不许冻住界面）',
              'asyncio.to_thread' in asrc, '')

    # ── A9 目录形态（清理 + 拍平）──
    # [EN] ── A9 directory shape (cleanup + flatten) ──
    mroot = Path(BR.MUMU_DIR)
    ok_ &= ok('A9 ★★★ `repo/` 那一层没了（拍平成 `backend/`）',
              (mroot / 'backend').is_dir() and not (mroot / 'repo').exists(), '')
    ok_ &= ok('A9b ★★★ 本项目不用的部分清掉了（前端 / 打包 / CI / Termux）',
              not any((mroot / p).exists() for p in (
                  'backend/../frontend', 'frontend', 'images', 'Dockerfile',
                  'docker-compose.yml', '.github', 'install-termux.sh')),
              '')
    # ★ 上游要求保留的（GPL 分发义务）：许可与上游 README 不能删
    # [EN] ★ what upstream requires to be kept (GPL distribution obligation): the license and upstream
    # [EN] README must not be deleted
    ok_ &= ok('A9c ★★★ 上游的 **LICENSE 与 README 原件都还在**'
              '（GPL-3.0 分发要带许可；删了就是合规问题）',
              (mroot / 'LICENSE').is_file()
              and (mroot / 'README_上游原版.md').is_file(), '')
    ok_ &= ok('A9d ★★ git 检出**还活着**（`git pull` 还能取上游新版）',
              (mroot / '.git').is_dir(), '')

    # ── A10 启动器指向新路径 ──
    #  ★ 2026-10-10 改判：这一段原来扫的是 `start.sh` / `setup.bat` … 6 个脚本，
    #    而且写了 `if not p.exists(): continue`。用户要求「删掉，只留 exe」之后
    #    那 6 个文件全没了 ⇒ **这个循环一次都不跑、A10 变成恒真** ——
    #    正是本项目最忌讳的"看着绿、其实什么也没看"。
    #    现在改成扫**启动器的源码**，并且把"到底查到了几个文件"也断言上：
    #    查不到就该红，不许悄悄通过。
    # [EN] ── A10 launcher points to the new path ──
    # [EN] ★ 2026-10-10 revised ruling: this section originally scanned `start.sh` / `setup.bat` … 6
    # [EN] scripts,
    # [EN] and had `if not p.exists(): continue`. After the user asked to "delete them, keep only the exe"
    # [EN] those 6 files were all gone ⇒ **this loop never runs even once, A10 becomes vacuously true** —
    # [EN] exactly the "looks green, but actually looked at nothing" that this project dreads most.
    # [EN] Now it scans the **launcher's source code**, and also asserts "how many files were actually
    # [EN] found":
    # [EN] if it finds none it should go red, no quietly passing.
    _lc = APP_DIR / 'launchers'
    _files = sorted(_lc.glob('*.go')) if _lc.is_dir() else []
    _txt = '\n'.join(p.read_text(encoding='utf-8') for p in _files).replace('\\', '/')
    ok_ &= ok('A10 ★★ 启动器指向 `novelservices/MuMuAINovel/backend`'
              '（不是旧的 repo/backend）—— 而且**真的查到了启动器源码**',
              bool(_files) and 'MuMuAINovel/backend' in _txt
              and 'MuMuAINovel/repo' not in _txt,
              f'查了 {len(_files)} 个 .go 文件')
    return ok_


# ══════════════════════════════════════════════════════════════════
#  B/C. 真机
# [EN] B/C. Real machine
# ══════════════════════════════════════════════════════════════════
async def test_ui(page: ft.Page) -> bool:
    ok_ = True
    app = NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(0.8)
    # ── B1 打开天机，看页签 ──
    # [EN] ── B1 open Tianji, look at the tabs ──
    dlg = app.show_global_settings()
    page.update()
    await asyncio.sleep(0.8)
    tabs_ctl = next((c for c in VU.walk(dlg) if isinstance(c, ft.Tabs)), None)
    ok_ &= ok('B1 天机里能取到选项卡控件', tabs_ctl is not None, '')
    # ⚠ 标签要**从 `ft.TabBar.tabs` 取**，不能拿 `VU.walk(tabs_ctl)` 找 `ft.Tab`
    #   —— 实测那样找出来是空表（`ft.Tab` 不在 walk 得到的控件树里）。
    # [EN] ⚠ labels must be **taken from `ft.TabBar.tabs`**, not found via `VU.walk(tabs_ctl)` looking for
    # [EN] `ft.Tab`
    # [EN] —— in practice that finds an empty table (`ft.Tab` isn't in the control tree that walk returns).
    labels: list[str] = []
    if tabs_ctl is not None:
        bar = next((c for c in VU.walk(tabs_ctl) if isinstance(c, ft.TabBar)), None)
        labels = [str(getattr(x, 'label', '') or '')
                  for x in (getattr(bar, 'tabs', None) or [])]
    report['tab_labels'] = labels
    ok_ &= ok('B1b ★★ 页签里有「AI模型配置」（两个 LLM 页签已合并）',
              t('AI模型配置') in labels, f'实际：{labels}')
    ok_ &= ok('B1c ★★ 页签里**没有**独立的「创作服务LLM设定」',
              all('创作服务LLM设定' not in x for x in labels),
              f'实际：{labels}')

    # ── B2 切到那一页，看内容 ──
    # [EN] ── B2 switch to that page, look at the content ──
    if tabs_ctl is not None and t('AI模型配置') in labels:
        tabs_ctl.selected_index = labels.index(t('AI模型配置'))
        page.update()
        await asyncio.sleep(0.6)
        # ⚠ 在 `dlg` 里找，不在 `page` 里（对话框是独立一层）
        # [EN] ⚠ look inside `dlg`, not inside `page` (the dialog is a separate layer)
        texts = VU.all_texts(dlg)
        texts += [str(getattr(c, 'label', '') or '') for c in VU.walk(dlg)
                  if isinstance(c, ft.Switch)]
        joined = '\n'.join(texts)
        report['svc_texts'] = [x for x in texts if x][:40]
        # 用户的两条硬要求：注明来源 + 写出项目地址
        # [EN] The user's two hard requirements: cite the source + write out the project address
        ok_ &= ok('B2 ★★★ 页面上写着**来自 MuMuAINovel**',
                  '来自 MuMuAINovel' in joined, '')
        ok_ &= ok('B2b ★★★ 页面上写着**上游项目地址**', UPSTREAM in joined, '')
        # 必配项（用户点名"必须要配置的，比如 LLM 模型"）
        # [EN] Required items (the user named them: "things that must be configured, e.g. the LLM model")
        need = [t('启用创作服务（总开关）'), t('小说作家用它写样章'),
                t('接口地址'), t('API Key'), t('默认生成模型'), t('服务端口')]
        miss = [x for x in need if x not in joined]
        ok_ &= ok('B2c ★★★ 必配项都在（总开关 / 用它写样章 / 接口 / Key / 模型 / 端口）',
                  not miss, f'缺：{miss}')
        if page.enable_screenshots:
            (OUT / 'mumu_service_zh.png').write_bytes(await page.take_screenshot())

    # ── C1 服务没起时**不许抛**（设置要打得开、写小说要能回退）──
    # [EN] ── C1 when the service isn't up it **must not throw** (settings must open, novel writing must be
    # [EN] able to fall back) ──
    from novelservices import mumu_bridge as BR
    st = BR.service_status(timeout=1.5)
    report['service_ok'] = {'ok': st.ok, 'reason': st.reason,
                            'base_url': st.base_url}
    ok_ &= ok('C1 ★★★ `service_status()` **永不抛异常**（返回对象带原因就行）',
              hasattr(st, 'ok') and isinstance(st.ok, bool), '')
    ok_ &= ok('C1b ★★★ 它给的失败原因**能读**（不是空串）', bool(st.reason or st.ok),
              f'reason={st.reason!r}')

    # ★★ 「服务不可用要能回退」这件事**不能靠"现在服务碰巧没起"来验** ——
    #    开发机上服务往往正开着，于是这条判据会**假绿**（第一版就是这样：
    #    服务在跑 → 真生成出一章 → `ok=True`，而判据写的是"应当失败"）。
    #    改成**指向一个必然没人听的端口**（9 = discard），
    #    这样无论真服务在不在，走的都是"连不上 → 回退"那条路。
    # [EN] ★★ "service unavailable must be able to fall back" **cannot be verified by relying on "the
    # [EN] service happens to not be up right now"** ——
    # [EN] on a dev machine the service is often running, so this criterion **falsely goes green** (the
    # [EN] first version was like this:
    # [EN] service running → actually generated a chapter → `ok=True`, while the criterion said "should
    # [EN] fail").
    # [EN] Changed to **point at a port that surely nobody is listening on** (9 = discard),
    # [EN] so whether or not the real service is up, it always takes the "can't connect → fall back" path.
    _real_url = BR.service_url
    BR.service_url = lambda: 'http://127.0.0.1:9'
    try:
        r = BR.generate_chapter(BR.ChapterTask(
            project_key='验证', novel_dir=None, title='x', outline='y'))
        ok_ &= ok('C1c ★★★ 服务不可用时 `generate_chapter` **返回失败对象而不是抛**'
                  '（调用方才能回退）',
                  r.ok is False and bool(r.reason), f'ok={r.ok} reason={r.reason!r}')
        ok_ &= ok('C1d ★★ 失败原因里**看得出是哪一环**（不是一句"失败了"）',
                  any(w in r.reason for w in ('没在跑', '连不上', '服务')), r.reason)
        rp = BR.polish('他走了。')
        ok_ &= ok('C1d2 ★★ 去味接口同样**只返回失败、不抛**',
                  rp.ok is False and bool(rp.reason), f'{rp.reason!r}')
    finally:
        BR.service_url = _real_url
    ok_ &= ok('C1e ★ 细纲为空时立刻拒绝（空细纲写出来的必然跑题）',
              BR.generate_chapter(BR.ChapterTask(
                  project_key='验证', novel_dir=None, title='x',
                  outline='   ')).reason.find('细纲') >= 0, '')

    # ── C2 小说作家：开关关着时**不走桥接** ──
    # [EN] ── C2 novel writer: when the switch is off it **does not go through the bridge** ──
    old_enabled = CFG.raw('MUMU_ENABLED')
    CFG.set('MUMU_ENABLED', 'false')
    ok_ &= ok('C2 ★★★ 总开关关着 → 小说作家不走 MuMuAINovel',
              CA_enabled_for('novelist') is False, '')
    CFG.set('MUMU_ENABLED', 'true')
    CFG.set('MUMU_FOR_NOVELIST', 'false')
    ok_ &= ok('C2b ★★ 总开关开着、作家这一项关着 → 还是不走它',
              CA_enabled_for('novelist') is False, '')
    CFG.set('MUMU_FOR_NOVELIST', 'true')
    ok_ &= ok('C2c ★★ 两项都开着 → 走它',
              CA_enabled_for('novelist') is True, '')
    # ③ 回退：服务不在跑时，走它也是**回退**，不是崩
    # [EN] ③ fallback: when the service isn't running, going through it is also a **fallback**, not a crash
    CFG.set('MUMU_ENABLED', old_enabled or 'false')

    # ── C3 ★★★ 写盘保险丝**行为**（不是"代码里有没有那个字符串"）──
    #   做法：真的设一次 `NWS_ENV_SINK`，看它写去了哪儿。
    #   只查源码里出现过 `NWS_ENV_SINK` 是不够的 —— 把读取那一行删掉，
    #   它照样能在源码里"找得到"（反例法当场揭穿）。
    # [EN] ── C3 ★★★ write-to-disk fuse **behavior** (not "is that string present in the code") ──
    # [EN] Approach: actually set `NWS_ENV_SINK` once, see where it wrote to.
    # [EN] Just checking that `NWS_ENV_SINK` appears in the source isn't enough —— delete the line that
    # [EN] reads it,
    # [EN] and it can still be "found" in the source (the counterexample method exposes it on the spot).
    import tempfile as _tf
    _sink_dir = Path(_tf.mkdtemp(prefix='nws_mumu_sink_'))
    _sink_env = _sink_dir / '.env'
    _old_sink = os.environ.get('NWS_ENV_SINK')
    os.environ['NWS_ENV_SINK'] = str(_sink_env)
    try:
        _err = BR.save_service_env({'APP_PORT': '18001'})
        _mumu_file = _sink_env.with_suffix('.mumu')
        _wrote = _mumu_file.read_text(encoding='utf-8') if _mumu_file.exists() else ''
        ok_ &= ok('C3 ★★★ 设了 `NWS_ENV_SINK` 就**写在那个 sink 里**'
                  '（回归期间不碰用户的服务配置）',
                  _err is None and 'APP_PORT=18001' in _wrote,
                  f'err={_err!r}｜{_mumu_file}')
        ok_ &= ok('C3b ★★★ 而**真实**的 backend/.env 里没有这次写的东西',
                  'APP_PORT=18001' not in
                  Path(BR.BACKEND_ENV).read_text(encoding='utf-8', errors='replace'),
                  '')
    finally:
        if _old_sink is None:
            os.environ.pop('NWS_ENV_SINK', None)
        else:
            os.environ['NWS_ENV_SINK'] = _old_sink

    # ── B3 改一项 → 保存 → 真的落盘（重定向到 sink，不碰用户文件）──
    # ★★★ 这一段**不许有"找不到就算了"的嵌套 `if`**（2026-10-09 反例法抓出来的）：
    #   第一版把"找字段 / 找保存按钮 / 点保存"逐层嵌在 `if xxx is not None:` 里 ——
    #   于是**只要有一层找不到，整段断言就一条都不记**，判据静默变弱，
    #   而反例法里那两条（"不写服务自己的 .env" / "丢掉写盘保险丝"）**谁也打不红**。
    #   ⇒ 每一步找不到都**记一条失败**，让它明确地红。
    # [EN] ── B3 change one item → save → actually lands on disk (redirect to sink, don't touch the user's
    # [EN] files) ──
    # [EN] ★★★ this section **must not have "if not found then skip" nested `if`s** (caught by the
    # [EN] counterexample method on 2026-10-09):
    # [EN] the first version nested "find field / find save button / click save" layer by layer in `if xxx
    # [EN] is not None:` ——
    # [EN] so **as long as any one layer isn't found, the entire assertion block records nothing**, the
    # [EN] criterion silently weakens,
    # [EN] and those two in the counterexample method ("don't write the service's own .env" / "drop the
    # [EN] write-to-disk fuse") **can't be turned red by anyone**.
    # [EN] ⇒ every step that isn't found must **record a failure**, so it goes explicitly red.
    # ★★ 2026-10-12：页签合并了 —— 前置改成"有「AI模型配置」这一页"。
    # [EN] ★★ 2026-10-12: the tabs merged -- the precondition becomes "the 'AI Model Config' page
    # [EN] exists".
    ok_ &= ok('B3 前置：天机里有「AI模型配置」页签（否则下面几条没法验）',
              tabs_ctl is not None and t('AI模型配置') in labels,
              f'labels={labels}')

    async def _reopen():
        dlg_ = app.show_global_settings()
        page.update()
        await asyncio.sleep(0.6)
        tb = next((c for c in VU.walk(dlg_) if isinstance(c, ft.Tabs)), None)
        if tb is not None and t('AI模型配置') in labels:
            tb.selected_index = labels.index(t('AI模型配置'))
            page.update()
            await asyncio.sleep(0.4)
        return dlg_

    def _find_field(root, label: str):
        """按**行里那个标签文本**找输入框行。

        ⚠ 不能按 `row._field.label` 找 —— `mk_field()` 造的是
        「左侧一个 `_label_box` + 右侧一个 `ft.TextField`」，
        **`TextField` 自己根本没有 `label`**（实测 `getattr(..., 'label', '')`
        恒为 `''`）。按 `.label` 找会**一条都匹配不上**，然后被外层
        `if ... is not None` 静默吞掉 —— 判据看着有、其实从没跑过。
        
                English:
        Find the input box row by **the label text in the row**.
                ⚠ Cannot find it by `row._field.label` -- what `mk_field()` creates is
                "a `_label_box` on the left + an `ft.TextField` on the right",
                **the `TextField` itself has no `label` at all** (in practice `getattr(..., 'label', '')`
                is always `''`). Finding by `.label` will **not match a single one**, and then gets silently
                swallowed by the outer `if ... is not None` -- the criterion looks present, but actually never ran.
        """
        for c in VU.walk(root):
            if not (isinstance(c, ft.Row) and hasattr(c, '_field')):
                continue
            if any(isinstance(x, ft.Text) and str(x.value or '') == label
                   for x in VU.walk(c)):
                return c
        return None

    def _find_save_btn(root):
        return next((c for c in VU.walk(root)
                     if type(c).__name__ in ('FilledButton', 'TextButton',
                                             'OutlinedButton')
                     and '保存' in VU.text_of(c)), None)

    old_words = CFG.raw('MUMU_TARGET_WORDS')
    dlg2 = await _reopen()
    fld2 = _find_field(dlg2, t('目标字数'))
    ok_ &= ok('B3a 前置：找得到「目标字数」输入框', fld2 is not None, '')
    btn = _find_save_btn(dlg2)
    ok_ &= ok('B3b 前置：找得到天机的「保存」按钮', btn is not None,
              f'候选={[VU.text_of(c)[:12] for c in VU.walk(dlg2) if type(c).__name__ in ("FilledButton", "TextButton", "OutlinedButton")][:8]}')
    if fld2 is not None and btn is not None:
        fld2._field.value = '4321'
        # ⚠ 处理函数**可能是同步的**（`save` 就是）—— 直接 `await` 会抛
        # [EN] ⚠ the handler **may be synchronous** (`save` is) —— directly `await`ing it will throw
        #   `TypeError: object NoneType can't be used in 'await' expression`。
        _r = btn.on_click(None)
        if hasattr(_r, '__await__'):
            await _r
        page.update()
        await asyncio.sleep(1.0)
        sink = Path(sys.modules['config'].Config.redirect_save)
        wrote = sink.read_text(encoding='utf-8') if sink.exists() else ''
        report['sink_head'] = wrote[:200]
        ok_ &= ok('B3 ★★★ 在天机里改「目标字数」→ 保存 → **配置真的落盘**',
                  'MUMU_TARGET_WORDS=4321' in wrote, f'sink={sink}')
        ok_ &= ok('B3b2 ★★★ 用户的真实 `.env` **一个字节都没被碰**（整段重定向）',
                  APP_DIR.joinpath('.env').read_text(
                      encoding='utf-8', errors='replace')
                  .find('MUMU_TARGET_WORDS=4321') < 0, '')
        # ★★★ B3c/B3d：「天机 → **服务自己的** .env」这条链真的走了吗。
        #   只查"代码里调了 `save_service_env`"是不够的（源码级看不出有没有真写）——
        #   这里查**写盘结果**：桥接层在重定向期间会写到旁边一个 `*.mumu`。
        # ⚠ **sink 的判定要跟桥接层一致**：桥接层的 `_sink_path()` 优先看
        #   `NWS_ENV_SINK`（**父进程**设的），其次才看 `Config.redirect_save`
        #   （本进程设的）。回归器是个父进程，它会设 `NWS_ENV_SINK` ——
        #   所以单跑时命中后者、在回归里命中前者。第一版只看 `redirect_save`，
        #   于是在**回归里**它读的是一个永远不存在的路径 ⇒ B3c 假红
        #   （单跑全绿、回归一跑就红，正是这种"环境不同口径就不同"的典型）。
        # [EN] ★★★ B3c/B3d: does the chain "Tianji → **the service's own** .env" really get exercised.
        # [EN] Just checking "the code calls `save_service_env`" isn't enough (source level can't tell whether
        # [EN] it really wrote) ——
        # [EN] here we check the **write-to-disk result**: during redirection the bridge layer writes to a
        # [EN] sibling `*.mumu`.
        # [EN] ⚠ **the sink decision must match the bridge layer**: the bridge layer's `_sink_path()` prefers
        # [EN] `NWS_ENV_SINK` (**set by the parent process**), and only then looks at `Config.redirect_save`
        # [EN] (set by this process). The regressor is a parent process, and it sets `NWS_ENV_SINK` ——
        # [EN] so when run standalone it hits the latter, and in the regression it hits the former. The first
        # [EN] version only looked at `redirect_save`,
        # [EN] so **in the regression** it reads a path that never exists ⇒ B3c falsely goes red
        # [EN] (A single run is all green, but a regression run goes red - exactly the typical case of
        # [EN] "different environments give different results").
        _cands = []
        _env_sink = (os.environ.get('NWS_ENV_SINK') or '').strip()
        if _env_sink:
            _cands.append(Path(_env_sink).expanduser().with_suffix('.mumu'))
        _rs = sys.modules['config'].Config.redirect_save
        if _rs is not None:
            _cands.append(Path(str(_rs)).with_suffix('.mumu'))
        msink_txt = ''
        mumu_sink = None
        for _c in _cands:
            if _c.exists():
                msink_txt = _c.read_text(encoding='utf-8')
                mumu_sink = _c
                break
        if mumu_sink is None:
            mumu_sink = _cands[0] if _cands else Path('(无 sink)')
        report['mumu_sink'] = {'path': str(mumu_sink),
                               'candidates': [str(x) for x in _cands],
                               'exists': mumu_sink.exists(),
                               'head': msink_txt[:300]}
        ok_ &= ok('B3c ★★★ 「天机 → MuMuAINovel 自己的 .env」这条链**真的写盘了**'
                  '（不是只在代码里调了个函数）',
                  'APP_PORT=' in msink_txt and 'DEFAULT_MODEL=' in msink_txt,
                  f'{mumu_sink}')
        ok_ &= ok('B3d ★★★ 它自己的 `backend/.env` **没被碰**（走 `*.mumu` sink）',
                  'MUMU_TARGET_WORDS=4321' not in
                  Path(BR.BACKEND_ENV).read_text(encoding='utf-8', errors='replace'),
                  '')
        CFG.set('MUMU_TARGET_WORDS', old_words)

    return ok_


def CA_enabled_for(key: str) -> bool:
    from crew.agents import _mumu_enabled_for
    return _mumu_enabled_for(key)


# ══════════════════════════════════════════════════════════════════
#  D. 端到端（服务真在跑才跑）
# [EN] D. End-to-end (only runs when the service is really running)
# ══════════════════════════════════════════════════════════════════
def test_e2e() -> bool:
    from novelservices import mumu_bridge as BR
    # ⚠ 反例法要跑**十几次**本脚本，每次真调一次 LLM 太贵也太慢 ——
    #   `developers/mutate_mumu_service.py` 会用这个开关把 D 组跳过
    #   （D 组验的是"桥真的通"，与那些源码级变异无关）。
    # [EN] ⚠ The counterexample method has to run this script **a dozen-plus times**, and a real LLM call
    # [EN] each time is too expensive and too slow --
    # [EN] `developers/mutate_mumu_service.py` uses this switch to skip group D
    # [EN] (Group D verifies that "the bridge really works", and is unrelated to those source-level
    # [EN] mutations).
    if (os.environ.get('NWS_MUMU_VERIFY_NO_E2E') or '').strip() in ('1', 'true', 'yes'):
        skip('D 端到端（真写一章）', '按 NWS_MUMU_VERIFY_NO_E2E 跳过（反例法用）')
        return True
    st = BR.service_status(timeout=3)
    if not st.ok:
        skip('D 端到端（真写一章）', f'写小说服务没在跑：{st.reason}')
        return True
    ok_ = True
    # ⚠ 夹具目录要用**固定**的，不能用 `mkdtemp` —— 映射缓存（`.mumu_project.json`）
    #   就在这个目录里，目录每次都换 = 每次都当成"新书" → **每次跑判据都往
    #   服务库里新建一个项目**（第一版就是这么写的，实测库里堆了 3 个同名项目）。
    # [EN] ⚠ The fixture directory must be **fixed**, `mkdtemp` cannot be used -- the mapping cache
    # [EN] (`.mumu_project.json`)
    # [EN] lives in this directory; if the directory changes every time = every time it is treated as a
    # [EN] "new book" -> **every criterion run creates a new project in the
    # [EN] service library** (the first version was written this way, and in practice the library piled up
    # [EN] 3 projects with the same name).
    tmp = OUT / '_mumu_verify_fixture'
    tmp.mkdir(parents=True, exist_ok=True)
    task = BR.ChapterTask(
        project_key='判据自检（可删）', novel_dir=tmp, title='第 1 天',
        outline='第 1 天。老张在镇上支起茶摊。整个上午只来一个挑担的老人，'
                '喝了一碗茶，留下三枚铜钱就走了。老张发现铜钱上有一层水锈，'
                '而今天并没有下雨。本章必须出现：茶摊、铜钱、水锈。',
        characters=['老张'], genre='市井志怪', target_words=500,
        model='deepseek-chat', enable_analysis=False, timeout=300)
    r = BR.generate_chapter(task)
    report['e2e'] = {'ok': r.ok, 'reason': r.reason,
                     'chars': len(r.text), 'elapsed': round(r.elapsed, 1),
                     'chapter': r.chapter_number}
    ok_ &= ok('D1 ★★★ 端到端：把细纲交给它，**真的拿回一章正文**',
              r.ok and len(r.text) > 100, f'{r.reason}｜{len(r.text)} 字')
    if r.ok:
        miss = [k for k in ('茶摊', '铜钱', '水锈') if k not in r.text]
        ok_ &= ok('D2 ★★ 细纲里的硬性条目**真的写进去了**',
                  not miss, f'缺：{miss}')
        ok_ &= ok('D3 ★ 回归了"第X章 标题"这类元信息（不该混进正文）',
                  not r.text.lstrip().startswith('第'), r.text[:24])
    return ok_


# ══════════════════════════════════════════════════════════════════
#  跑起来
# [EN] Run it
# ══════════════════════════════════════════════════════════════════
def _fail_list() -> list:
    return [c for c in report['checks'] if not c['ok']]


def finish() -> int:
    rep = OUT / 'mumu_service_report.json'
    rep.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    total = len(report['checks'])
    bad = _fail_list()
    print('\n' + '=' * 62)
    print(f'创作服务（MuMuAINovel）验证：{total} 项断言，失败 {len(bad)} 项'
          f'，跳过 {len(report["skipped"])} 项')
    for c in bad:
        print(f'  ✗ {c["name"]}   [{c["detail"]}]')
    if report.get('fatal'):
        print(report['fatal'][-1200:])
    print('→ 全部通过' if (not bad and not report.get('fatal')) else '→ 有失败项')
    return 0 if (not bad and not report.get('fatal')) else 1


async def entry(page: ft.Page) -> None:
    """真机那一半。**Page 必须由 Flet 给**（自己 `ft.Page()` 会要 session，
    实测 `TypeError: Page.__init__() missing 1 required positional argument: 'sess'`）——
    所以整个脚本按 `ft.run(entry)` 起。
        English:
    The real-machine half. **Page must be supplied by Flet** (calling `ft.Page()` yourself will
    require a session,
        in practice `TypeError: Page.__init__() missing 1 required positional argument: 'sess'`) --
        so the whole script starts via `ft.run(entry)`.
    """
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix='nws_mumu_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    page.enable_screenshots = True
    try:
        report['ui_ok'] = await test_ui(page)
    except BaseException:                                      # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()[-1800:]
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)
        await shutdown(page, code=finish())


def main() -> int:
    # ① 不需要界面的那一半，先跑（快、且失败信息清楚）
    # [EN] ① The half that does not need the UI runs first (fast, and failure info is clear)
    test_source()
    test_e2e()
    # ② 真机那一半交给 Flet（`ft.run` 会自己把 Page 建好）
    # [EN] ② The real-machine half is handed to Flet (`ft.run` builds the Page itself)
    ft.run(entry)
    return finish()


if __name__ == '__main__':
    sys.exit(main())
