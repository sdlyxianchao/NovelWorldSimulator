# -*- coding: utf-8 -*-
"""验证：天机里的**「常规」页签**（2026-10-08）。

用户原话：

    「全局设置里在**LLM 接入左边加一个常规 Tab**，里面包含一些常规设置项，
      比如说**现在就把日志的设置项移动到这里**，再新增一个**项目根目录**配置项
      放到这里（放到开始，**确认必须重启才起作用**）」

拆成四件可验的事：

  ① **页签顺序**：`常规` 排在**第一个**（= 「LLM 接入」的左边）。
     ⚠ 这件小事的代价不小：`selected_index` 与"还没配 LLM → 点「去配置」"
     那一跳**都按序号**，加了页签不改它们，点「去配置」会落到「常规」页上
     （用户想填 Key，看到的却是项目根目录），而且**不报错、不崩**。
     所以判据里钉了 `TAB_LLM` 这个**唯一来源**，并**照页签表核**它指得对不对。
  ② **日志那一块搬过来了**（不是复制一份：原「日志」页签必须**消失**，
     否则同一个设置在两个地方各有一份输入框）。
  ③ **项目根目录**：界面上有输入框 + 「浏览…」，保存时真的写进
     `DEFAULT_PROJECTS_DIR`，放在这一页的**最前面**。
  ④ ★★★ **它到底要不要重启** —— 这是用户明确点出来要确认的一条。
     实测结论：**不用**。`CFG.projects_dir()` 每次现读（`scan_projects` /
     `Project.create_new` 都现调它），改完回到开始界面书列表就换了。
     所以界面与本文都如实写"不用重启"，并且判据**用真机证一遍**：
     改配置 → 保存 → 开始界面上的书名真的换成了新目录里那本。
     （反过来说：如果把这条判据写成"必须重启才生效"，那是在**验一个假结论**。）

判据两层：A 组源码级（页签表 / 控件归属 / 配置项性质），
B 组真机（打开天机看页签与内容 + 改根目录 → 保存 → 书列表真的换了）。

用法：.venv\\Scripts\\python.exe tools/verify_regular_tab.py
产出：assets/screenshots/regular_tab_*.png / regular_tab_report.json

English:
User's exact words:
    "In global settings, **add a 常规 Tab to the left of LLM 接入**, containing some general settings items,
      for example **move the log settings items here now**, and add a new **项目根目录** config item
      put it here (put it at the beginning, **confirm it must require a restart to take effect**)"
Split into four verifiable things:
  ① **Tab order**: `常规` comes **first** (= to the left of "LLM 接入").
     ⚠ This small thing has a nontrivial cost: `selected_index` and the "no LLM configured yet -> click 去配置"
     jump **both go by index**; if you add a tab without changing them, clicking 去配置 lands on the 常规 page
     (the user wants to enter a Key but sees the project root directory), and **it doesn't error, doesn't crash**.
     So the criterion pins down `TAB_LLM` as the **single source of truth**, and **checks against the tab table** whether it points to the right thing.
  ② **The log block has been moved over** (not copied: the original 日志 tab must **disappear**,
     otherwise the same setting has an input box in two places).
     `DEFAULT_PROJECTS_DIR`, placed at the **very front** of this page.
  ④ ★★★ **Whether it needs a restart** — this is the item the user explicitly called out to confirm.
     Measured conclusion: **no**. `CFG.projects_dir()` is read fresh each time (`scan_projects` /
     `Project.create_new` both call it fresh), after the change you return to the start screen and the book list has already changed.
     So both the UI and this document truthfully write "no restart needed", and the criterion **verifies it on a real machine**:
     change config -> save -> the book name on the start screen really becomes the one in the new directory.
     (Conversely: if this criterion were written as "requires a restart to take effect", that would be **verifying a false conclusion**.)
Two layers of criteria: group A source-level (tab table / control ownership / config item
nature),
group B real machine (open 天机 to see the tabs and contents + change the root directory -> save
-> the book list really changes).
Usage: .venv\\Scripts\\python.exe tools/verify_regular_tab.py
Output: assets/screenshots/regular_tab_*.png / regular_tab_report.json
"""
from __future__ import annotations

import asyncio
import ast
import inspect
import json
import re
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown                        # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('SHOW_OPENING', 'false')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from gui.app_flet import NovelWorldApp                         # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def _src() -> str:
    return textwrap.dedent(inspect.getsource(NovelWorldApp.show_global_settings))


def _full() -> str:
    """整个界面的源码文本。

    ⚠ 为什么另开一个：日志那一块与「项目根目录」都写在**内层函数**
    `_regular_block()` 里，而 `inspect.getsource(show_global_settings)`
    **取不到内层函数的函数体** —— 第一版拿它去找「日志设置」，
    结果 `-1`（找不到），判据假红三条。
    
        English:
    The source text of the entire UI.
        ⚠ Why open a separate one: the log block and "项目根目录" are both written inside the **inner function**
        `_regular_block()`, and `inspect.getsource(show_global_settings)`
        **cannot get the function body of the inner function** — the first version used it to look for "日志设置",
        resulting in `-1` (not found), and the criterion falsely flagged three red lines.
    """
    return (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')


def tab_titles() -> list[str]:
    """从 `show_global_settings` 的源码里解析出**页签顺序**（照产品的事实）。

    ⚠ 不能靠"猜第几个"：这是判据的**基准**，必须来自产品源码本身。
    
        English:
    Parse the **tab order** out of the source of `show_global_settings` (according to the product's
    facts).
        ⚠ Can't rely on "guessing which index": this is the **baseline** of the criterion, it must come from the product source itself.
    """
    tree = ast.parse(_src())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(x, 'id', None) == 'tab_defs' for x in node.targets):
            out: list[str] = []
            for elt in node.value.elts:
                arg = (getattr(elt.elts[0], 'args', None) or [None])[0]
                if isinstance(arg, ast.Constant):
                    out.append(arg.value)
            return out
    return []


def logic_checks() -> None:
    """A 组：源码级（页签表 / 控件归属 / 配置项性质）。
        English:
    Group A: source-level (tab table / control ownership / config item nature).
    """
    titles = tab_titles()
    report['tabs'] = titles

    # ── A1 ★★★ 页签顺序 ──
    # ★★ 2026-10-10 用户改名并重排：「LLM 接入」→「AI模型配置」、
    #    「创作服务」→「创作服务LLM设定」并**移到推演服务右边**。
    # [EN] ── A1 ★★★ Tab order ──
    # ★★ 2026-10-12：两个 LLM 页签**合并**成「AI模型配置」，随后 MuMuAINovel
    #   **拆出**成「外部小说服务配置」（插在第 3 位）。
    # ★★ 2026-10-16：MuMuAINovel 并入「外部创作服务」（含 PlotPilot + PenShot），
    #   该合并页上移到第 3 位；原独立「外部小说服务配置」页删除，总页数 8 → 7。
    # [EN] ★★ 2026-10-12: the two LLM tabs **merged** into "AI Model Config", then MuMuAINovel was
    # [EN] **split out** into "External novel service" (3rd).
    # [EN] ★★ 2026-10-16: MuMuAINovel folded into "External Creative Services" (PlotPilot + PenShot);
    # [EN] the merged page moved up to 3rd; standalone "External novel service" removed, 8 → 7 tabs.
    # ★★ 2026-11-01：「花费与优化」插在「AI模型配置」右边（第 3 位），总页数 7 → 8。
    #    插中间 ⇒ 后面五页下标整体 +1，`TAB_GLOBAL_*` 一次改齐（漏改不报错，只"点错页"）。
    # [EN] ★★ 2026-11-01: "Cost & Tuning" inserted right after "AI Model Config" (3rd), 7 → 8 tabs.
    ok('A1 ★★★ 页签顺序对：① 常规 ② AI模型配置 ③ 花费与优化 ④ 外部创作服务 '
       '⑤ 界面外观 ⑥ 运行 ⑦ 导演与合规 ⑧ 剧组 Agents',
       titles[:8] == ['常规', 'AI模型配置', '花费与优化', '外部创作服务',
                      '界面外观', '运行', '导演与合规', '剧组 Agents'],
       str(titles))

    # ── A2 ★★ 「常规」排在最左边（第一个）──
    # [EN] ── A2 ★★ "常规" is leftmost (first) ──
    ok('A2 ★★ 「常规」排在第一个（它装着"程序装在哪、日志写哪儿"）',
       bool(titles) and titles[0] == '常规', str(titles[:2]))

    # ── A2b ★★★ 「创作服务LLM设定」**紧挨在**「AI模型配置」右边 ──
    #   用户 2026-10-10 原话：「创作服务改名叫做创作服务LLM设定
    #   **移动到AI模型配置的右边**」。为什么要单列：把它排回最后
    #   在界面上**看不出任何毛病**（页签都在、内容也都对），只有"位置不对"。
    # [EN] **move it to the right of AI模型配置**". Why call this out separately: moving it back to last
    # [EN] shows **no visible problem** in the UI (all tabs present, content correct), only "wrong
    # [EN] position".
    # ★★ 2026-10-12：页签合并了 —— 判据从"创作服务紧挨在右边"改成
    #   "那一页真的只叫一个名字，且不再有独立的创作服务页签"。
    # [EN] ★★ 2026-10-12: the tabs merged -- the criterion changes from "creation service right next
    # [EN] to it" to "that page has a single name and there is no separate creation-service tab".
    ok('A2b ★★★ 「AI模型配置」是合并后的唯一 LLM 页（不再有独立的创作服务页签）',
       'AI模型配置' in titles and all('创作服务LLM设定' not in x for x in titles)
       and (titles.count('AI模型配置') == 1),
       f'{titles}')

    # ── A3 ★★★ `TAB_LLM` 与页签表一致（防"页签顺序变了忘了改常量"）──
    # ★★★ 2026-10-09 **重写这条判据**（原来是错的，而且正是它让错的东西一直绿）：
    #   老写法：`1 <= i <= len(titles) and titles[i - 1] == 'LLM 接入'`
    #   —— 它把"`selected_index` 是 1 起算"这个**被测对象的口径**又假设了一遍。
    #   实测那个假设是**错的**：Flet 的 `Tabs.selected_index` 默认值就是 0、
    #   且文档写明支持 `-1` 指最后一个页签（Python 序列语义），
    #   校验式是 `-length <= i < length`。
    #   ⇒ 老判据配上 `TAB_LLM = 2` 时两边**一起错**：常量指着「界面外观」
    #     （点「去配置」落在界面外观页），而这条判据照样绿 ——
    #     **判据里不许对被测口径做二次换算。** 现在直接比下标。
    # [EN] ── A3 ★★★ `TAB_LLM` matches the tab table (guards against "tab order changed but forgot to
    # [EN] update constant") ──
    # [EN] ★★★ 2026-10-09 **rewrote this criterion** (the old one was wrong, and it was exactly what kept
    # [EN] the wrong thing green):
    # [EN] Old form: `1 <= i <= len(titles) and titles[i - 1] == 'LLM 接入'`
    # [EN] —— it assumed once more the **subject-under-test's convention** that "`selected_index` is
    # [EN] 1-based".
    # [EN] That assumption is measured to be **wrong**: Flet's `Tabs.selected_index` default value is 0,
    # [EN] and the docs state it supports `-1` for the last tab (Python sequence semantics),
    # [EN] the validation expression is `-length <= i < length`.
    # [EN] ⇒ The old criterion paired with `TAB_LLM = 2` makes **both wrong together**: the constant points [EN] at 「界面外观」
    # [EN] **A criterion must not re-convert the subject's convention.** Now compare indices directly.
    i = NovelWorldApp.TAB_LLM
    ok('A3 ★★★ `TAB_LLM` 真的指着「AI模型配置」那一页'
       '（"还没配 LLM"那几跳靠它；**0 起算**，直接比下标）',
       bool(titles) and i == titles.index('AI模型配置'),
       f'TAB_LLM={i}｜页签={titles}｜AI模型配置在下标 '
       f'{titles.index("AI模型配置") if "AI模型配置" in titles else "?"}')

    # ── A3b ★★★ 天机**默认**落在「常规」（2026-10-31 用户点名的口径）──
    # 用户原话：「天机打开应该默认是 常规Tab 而不是AI模型配置」。
    # ★ 这条为什么必须单列：默认值是 `TAB_GENERAL` 还是 `TAB_LLM`，
    #   两个页签**都能正常打开**、都不报错 —— 只有"开错了页"这一个症状。
    #   老 A3 把"默认值取 TAB_LLM"写进了说明里，正是它让这件事一直没人管。
    # ⚠ 口径是"常量指得对" + "`selected_index` 的默认分支用的是这个常量"，
    #   两条都要：常量对了但代码里仍写 `else self.TAB_LLM`，照样落错页。
    # [EN] ── A3b ★★★ Tianji **defaults** to "General" (the convention the user named on 2026-10-31) ──
    # [EN] User's words: "Tianji should open on the General tab, not AI model config".
    # [EN] ★ Why a separate line: whether the default is `TAB_GENERAL` or `TAB_LLM`, **both tabs open
    # [EN] fine** and nothing raises -- the only symptom is "it opened the wrong page". The old A3 had
    # [EN] "default = TAB_LLM" written into its own note, which is exactly why nobody looked at it.
    # [EN] ⚠ Two things, both required: the constant points right, AND the `selected_index` default
    # [EN] branch actually uses it (a right constant with `else self.TAB_LLM` still lands wrong).
    g = NovelWorldApp.TAB_GENERAL
    _full_src = Path(APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    _sel = [ln.strip() for ln in _full_src.split('\n')
            if 'tab if tab is not None else' in ln]
    ok('A3b ★★★ `TAB_GENERAL` 指着「常规」，且 `selected_index` 的默认分支用的是它'
       '（用 TAB_LLM 当默认 ⇒ 从菜单点天机先看到模型配置，且不报错）',
       bool(titles) and g == titles.index('常规') and bool(_sel)
       and all('TAB_GENERAL' in ln for ln in _sel)
       and not any('TAB_LLM' in ln for ln in _sel),
       f'TAB_GENERAL={g}｜常规在下标 {titles.index("常规") if "常规" in titles else "?"}'
       f'｜默认分支={_sel}')

    # ── A4 ★★★ 「去配置」那一跳取的是常量，不是字面量 ──
    # 为什么单列一条：`_go()` 里写死 `tab=1` 时，页签一变**就成了"落到常规页"**，
    # 而这类错误没有任何运行时报错（只是"打开的页不对"）。
    # [EN] ── A4 ★★★ The "去配置" jump takes the constant, not a literal ──
    # [EN] Why call this out separately: when `_go()` hardcodes `tab=1`, a tab change **makes it "land on
    # [EN] the 常规 page"**,
    # [EN] and this kind of error raises no runtime error (just "the page opened is wrong").
    full = Path(APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    # ⚠ 这条判据第一版是 `'self.TAB_LLM)' in 去空格后的全文` —— **恒真**，
    #   因为 `selected_index` 那一行也含同一个串。反例法当场打出来：
    #   把 `_go()` 改回 `tab=1` 时它**照样绿**（"没抓到"）。
    #   改成**按行精确查**：所有 `show_global_settings(tab=…)` 的实参
    #   都必须是 `TAB_LLM`（不许出现数字字面量）。
    # ⚠ 只数**代码行**，注释里提到的那几处不算（`_regular_block` 的注释里
    #   就写着旧的 `tab=2` 示例 —— 不过滤会把注释当成调用点）。
    # [EN] ⚠ The first version of this criterion was `'self.TAB_LLM)' in whitespace-stripped full text` ——
    # [EN] **always true**,
    # [EN] because the `selected_index` line also contains the same substring. Counterexample method calls
    # [EN] it out on the spot:
    # [EN] when `_go()` is reverted to `tab=1` it **still goes green** ("didn't catch it").
    # [EN] Changed to **exact line-wise search**: all `show_global_settings(tab=…)` arguments
    # [EN] must be `TAB_LLM` (no numeric literals allowed).
    # [EN] ⚠ Only count **code lines**; the mentions in comments don't count (in `_regular_block`'s comment
    # [EN] there's an old `tab=2` example —— not filtering would treat the comment as a call site).
    _calls = [ln.strip() for ln in full.split('\n')
              if 'show_global_settings(tab=' in ln
              and not ln.lstrip().startswith('#')
              and not ln.lstrip().startswith('—')]
    # ★★ 2026-10-11 收紧口径（原口径是"每一处的实参都必须是 `TAB_LLM`"）：
    #   运行页那一轮加了"点面板标题跳设置"，那里传的是**变量** `tab`
    #   （由 `_settings_target()` 按"在跑/没在跑"算出来，见 `_open_settings_at`）——
    #   那是**合法**的传参，而老口径会把 `self.show_global_settings(tab=tab, agent=agent)`
    #   判成错（A4 当场红）。
    #   这条判据真正要防的是**写死数字**（`tab=1`）—— 页签一插就悄悄落到隔壁页。
    #   ⇒ 改成"实参不许是**数字字面量**"，并**另加一条** A4b 钉住"去配置那一跳
    #     仍然用常量"（否则放宽之后连那一处写死也抓不住了）。
    # [EN] ★★ Tightened the convention on 2026-10-11 (the old convention was "every argument must be
    # [EN] `TAB_LLM`"): the run page gained "click a panel title to jump to settings", which passes a
    # [EN] **variable** `tab` (computed by `_settings_target()` from "running / not running", see
    # [EN] `_open_settings_at`) -- that is a **legitimate** argument, and the old convention flagged
    # [EN] `self.show_global_settings(tab=tab, agent=agent)` as an error (A4 went red on the spot).
    # [EN] What this criterion really guards against is **hardcoded numbers** (`tab=1`) -- inserting a tab
    # [EN] then silently lands on the neighbouring page. ⇒ Changed to "the argument must not be a
    # [EN] **numeric literal**", plus a new A4b pinning that "the 'go configure' jump still uses the
    # [EN] constant" (otherwise, once loosened, even that hardcoding would slip through).
    _lit = [ln for ln in _calls if re.search(r'tab=\s*-?\d', ln)]
    ok('A4 ★★★ `show_global_settings(tab=…)` 的实参**不是写死的数字**'
       '（写死就会悄悄落到「常规」页上，且不报错）',
       bool(_calls) and not _lit, f'字面量={_lit}｜全部={_calls[:3]}')
    ok('A4b ★★ 「还没配 LLM」那一处的 `tab=` 取的是 `TAB_LLM` 常量'
       '（放宽 A4 之后必须有这一条兜底，否则那处写死也抓不住）',
       any('tab=self.TAB_LLM' in ln for ln in _calls),
       str(_calls[:3]))

    # ── A5 ★★ 日志那一块**搬**过来了（原页签不许留）──
    # [EN] ── A5 ★★ The log block **moved** over (the original tab must not keep it) ──
    ok('A5 ★★ 原「日志」页签**不再存在**（是搬过来，不是复制一份 ——'
       '同一个设置有两处输入框会各说各话）',
       '日志' not in titles, str(titles))
    body = _src()
    full = _full()
    # 「常规」页的内容是 `_regular_block()` 造出来的 —— 先钉住第一个页签
    # 真的调它（结构判据），再去块里找控件（内容判据）。
    # [EN] The content of the "常规" page is built by `_regular_block()` —— first pin that the first tab
    # [EN] really calls it (structural criterion), then search the block for controls (content criterion).
    _first_invoc = '(t("' + '常规' + '"), _regular_block())'
    ok('A5a ★★ 第一个页签的内容是 `_regular_block()`'
       '（不是别处拼的 —— 顺序与内容必须同源）',
       _first_invoc in full, '')
    # ⚠ 引号要兼容：源码里写的是双引号（`mk_section(t("日志设置"))`），
    #   判据第一版只找单引号 → 找不到 → 假红两条（A5b / A6b）。
    # [EN] ⚠ Quotes must be compatible: the source writes double quotes (`mk_section(t("日志设置"))`),
    # [EN] the first version of the criterion only searched single quotes → couldn't find it → two false
    # [EN] reds (A5b / A6b).
    _flat = full.replace("'", '"')
    ok('A5b ★★ 日志那几项现在挂在「常规」页里（同一块里）',
       all(x in _flat for x in (f'mk_section(t("日志设置"))', 'log_level',
                                'debug_switch', 'log_dir_field'))
       and '_regular_block' in full, '日志设置块在 _regular_block 里')

    # ── A6 ★★ 项目根目录控件 + 写在**最前面** ──
    # [EN] ── A6 ★★ Project root directory control + written **at the very front** ──
    ok('A6 ★★ 「项目根目录」有输入框与「浏览…」（不是一行灰字）',
       'proj_root_field' in body and 'pick_proj_root' in body
       and 'mk_btn(t("浏览…"), pick_proj_root' in body, '')
    _i_root = _flat.find('mk_section(t("项目根目录"))')
    _i_log = _flat.find('mk_section(t("日志设置"))')
    ok('A6b ★★ 项目根目录排在**日志前面**（用户："放到开始"）',
       0 <= _i_root < _i_log, f'root@{_i_root} log@{_i_log}')

    # ── A7 ★★★ 保存时真的把它写进配置 ──
    # [EN] ── A7 ★★★ On save it's really written to the config ──
    ok('A7 ★★★ 保存时写 `DEFAULT_PROJECTS_DIR`',
       "CFG.set('DEFAULT_PROJECTS_DIR', field_value(proj_root_field))" in body, '')

    # ── A8 ★★★ 「要不要重启」：如实标注（不贴假的"要重启"标签）──
    # 用户要求"确认必须重启才起作用"。实测**不用重启**（见 B4 的真机证据），
    # 所以这里要钉住"没有给它贴 restart 标签" —— 贴了就是骗人：
    # 用户会以为"现在改了没用"，而根目录其实已经切过去了。
    # [EN] ── A8 ★★★ "Whether a restart is needed": label truthfully (don't slap a fake "restart required"
    # [EN] tag) ──
    # [EN] The user requires "confirm it only takes effect after a restart". Measured: **no restart
    # [EN] needed** (see B4's real-machine evidence),
    # [EN] so here we must pin "no restart tag was applied to it" —— applying one is lying:
    # [EN] the user would think "changing it now does nothing", while the root directory has actually
    # [EN] already switched.
    import config as C
    spec = C.SPEC['DEFAULT_PROJECTS_DIR']
    ok('A8 ★★★ `DEFAULT_PROJECTS_DIR` **没有**标 `restart=True`'
       '（实测不用重启：`projects_dir()` 每次现读 —— 标了会让人以为"改了没用"）',
       not spec.get('restart'), f"restart={spec.get('restart')}")
    ok('A8b ★★ 而 `LOG_DIR` 仍然标着 `restart=True`（日志器只在启动时建一次）'
       '—— 同一页里两种性质并存，标注必须各自正确',
       bool(C.SPEC['LOG_DIR'].get('restart')),
       f"restart={C.SPEC['LOG_DIR'].get('restart')}")
    # 界面提示里如实写着"不用重启"，且说明了"当前那本不会跟着搬"
    # [EN] The UI hint truthfully says "no restart needed", and explains "the currently open book won't
    # [EN] move along with it"
    ok('A8c ★★ 界面上**如实**写着"改完不用重启"以及"当前那本不会跟着搬"',
       '改完不用重启' in full and '不会跟着搬' in full, '')

    # ── A9 ★★ 保存时清掉重复检查的缓存（不清就一直拿旧根去比）──
    # [EN] ── A9 ★★ On save, clear the duplicate-check cache (otherwise it keeps comparing against the old
    # [EN] root) ──
    ok('A9 ★★ 保存时把 `_dup_cache` 清掉'
       '（它是按**旧根**扫的；不清会拿旧目录去判"这本开过卷没有"）',
       '_dup_cache = None' in full, '')

    # ── A10 提示文案不再张冠李戴 ──
    # ⚠ 只在**字符串字面量**里找，不看注释：源码里那段注释本身就在解释
    #   "为什么不再写 LLM 配置"，里面带着这几个字 —— 拿全文找会假红
    #   （第一版就是这么红的）。
    # [EN] ── A10 The hint text no longer misattributes ──
    # [EN] ⚠ Only search in **string literals**, not comments: that comment in the source is itself
    # [EN] explaining
    # [EN] "why the LLM config is no longer written", and contains these words —— searching the full text
    # [EN] gives a false red
    # [EN] (which is exactly how the first version went red).
    import re as _re
    _lits = _re.findall(r'''t\(\s*['\"]([^'\"]*重启程序才会生效[^'\"]*)['\"]''', full)
    ok('A10 ★ 「需要重启」的提示不再写死「LLM 配置」'
       '（这一页现在还装日志目录，说成 LLM 是张冠李戴）',
       bool(_lits) and all('LLM' not in x for x in _lits), str(_lits[:2]))


async def gui_checks(page: ft.Page, app, tmp: Path) -> None:
    """B 组：真机（页签 + 内容 + 改根目录真的立刻生效）。
        English:
    Group B: real machine (tabs + contents + changing the root directory really takes effect
    immediately).
    """
    from store.project import Project

    root_a = tmp / '根甲'
    root_b = tmp / '根乙'

    # ── B1 打开天机：页签顺序 + 默认落在 LLM 接入 ──
    # [EN] ── B1 Open 天机: tab order + defaults to landing on LLM 接入 ──
    dlg = app.show_global_settings()
    page.update()
    await asyncio.sleep(1.0)
    tabs_ctl = next((c for c in VU.walk(dlg) if isinstance(c, ft.Tabs)), None)
    ok('B1 天机对话框里找得到 `ft.Tabs`', tabs_ctl is not None,
       type(tabs_ctl).__name__)
    if tabs_ctl is None:
        return
    bar = next((c for c in VU.walk(tabs_ctl) if isinstance(c, ft.TabBar)), None)
    labels = [str(getattr(x, 'label', '') or '') for x in
              (getattr(bar, 'tabs', None) or [])]
    report['tab_labels'] = labels
    ok('B1b ★★ 屏幕上前四个页签是「常规」「AI模型配置」「花费与优化」'
       '「外部创作服务」（2026-10-16：MuMuAINovel 并入外部创作服务并上移；'
       '2026-11-01：在「AI模型配置」右边插入「花费与优化」）',
       labels[:4] == [t('常规'), t('AI模型配置'), t('花费与优化'), t('外部创作服务')],
       str(labels))
    # ★★★ 2026-10-31 口径反了（用户：「天机打开应该默认是 常规Tab 而不是AI模型配置」）。
    #   老判据钉的是"默认 = AI模型配置"，正是它让"每次点天机都先看到模型配置"
    #   一直绿着。**改口径不是删判据**：这条防的东西一字没变 ——
    #   "默认值写错页、而且不报错"。只是正确的那一页换成了「常规」。
    # ⚠ 同时钉住 `TAB_GENERAL` 与页签表一致：默认值若又写回一个字面量，
    #   页签一插就会悄悄落到隔壁页（2026-10-08 那次就是这么错的）。
    # [EN] ★★★ 2026-10-31 the convention flipped (user: "Tianji should open on the General tab, not
    # [EN] AI model config"). The old criterion pinned "default = AI model config", which is exactly
    # [EN] what kept "every visit lands on model config first" green. **Changing a convention is not
    # [EN] deleting a criterion**: what it guards -- "the default points at the wrong page, silently" --
    # [EN] is unchanged; only the correct page changed.
    ok('B1c ★★★ 默认落在「常规」页'
       '（`selected_index` == TAB_GENERAL == 它在页签表里的下标）',
       int(getattr(tabs_ctl, 'selected_index', 0) or 0) == NovelWorldApp.TAB_GENERAL
       and NovelWorldApp.TAB_GENERAL == labels.index(t('常规')),
       f'selected_index={getattr(tabs_ctl, "selected_index", None)}｜'
       f'TAB_GENERAL={NovelWorldApp.TAB_GENERAL}｜页签={labels}')

    # ── B2 切到「常规」页，看内容 ──
    # ⚠ `selected_index` 是 **0 起算**（见 A3 那段）。以前这里写 `+1`，
    #   于是"切到常规"其实切的是「LLM 接入」—— 之所以没露馅，是因为
    #   `VU.all_texts(dlg)` 会把 `TabBarView` 的**所有**子页正文都收进来，
    #   选哪一页它都看得到。**内容断言认不出选中的是哪一页**，
    #   所以要靠 A3/B1c 那两条比下标的判据把关。
    # [EN] ── B2 Switch to the "常规" page, look at the content ──
    # [EN] ⚠ `selected_index` is **0-based** (see the A3 section). Previously this wrote `+1`,
    # [EN] so "switch to 常规" actually switched to 「LLM 接入」—— the reason it didn't show is that
    # [EN] `VU.all_texts(dlg)` collects the body text of **all** child pages of `TabBarView`,
    # [EN] so whichever page is selected it sees it. **Content assertions can't tell which page is
    # [EN] selected**,
    # [EN] so it relies on the two index-comparison criteria A3/B1c to guard it.
    tabs_ctl.selected_index = labels.index(t('常规'))
    page.update()
    await asyncio.sleep(0.6)
    # ⚠ **在 `dlg` 里找，不在 `page` 里**：`show_dialog` 打开的对话框是
    #   独立的一层，`page.controls` 仍是**底下那个界面**（开始界面）。
    #   第一版读 `page`，读到的全是开始界面的六项菜单，
    #   于是"常规页里有没有项目根目录"三条全假红。
    # [EN] ⚠ **Search in `dlg`, not in `page`**: the dialog opened by `show_dialog` is
    # [EN] an independent layer, and `page.controls` is still **the interface underneath** (the start
    # [EN] screen).
    # [EN] The first version read `page`, and what it read was entirely the start screen's six-item menu,
    # [EN] so all three "is there a project root directory on the 常规 page" checks went false red.
    texts = VU.all_texts(dlg)
    # ⚠ 开关（`ft.Switch`）的标签存在 `.label` 上，**不是**子 `ft.Text`
    #   —— `all_texts` 只收 `ft.Text`，所以「调试模式」读不到（实测少一条）。
    # [EN] ⚠ A switch (`ft.Switch`)'s label is stored on `.label`, **not** as a child `ft.Text`
    # [EN] —— `all_texts` only collects `ft.Text`, so 「调试模式」 can't be read (measured: one item short).
    texts += [str(getattr(c, 'label', '') or '') for c in VU.walk(dlg)
              if isinstance(c, ft.Switch)]
    joined = '\n'.join(texts)
    report['regular_texts'] = [x for x in texts if x][:40]
    ok('B2 ★★ 「常规」页里有「项目根目录」（用户点名要新增的那一项）',
       t('项目根目录') in joined, '')
    ok('B2b ★★ 也有日志那一块（日志级别 / 调试模式 / 日志目录 ——'
       '用户要求把日志的设置项移到这里）',
       all(x in joined for x in (t('日志设置'), t('日志级别'),
                                 t('调试模式'), t('日志目录'))), '')
    ok('B2c ★ 也有「浏览…」按钮（能挑目录，不是手打路径）',
       '浏览…' in joined, '')
    if page.enable_screenshots:
        (OUT / 'regular_tab_zh.png').write_bytes(await page.take_screenshot())

    # ── B3 ★★★ 改项目根目录 → 保存 → **界面真的跟着换**（证明"不用重启"）──
    # ⚠ 怎么"看见"根目录变了：开始界面上**不显示书名**（只有一个六项菜单），
    #   项目数只体现在「拾卷」那行小字上 ——
    #   `t('打开以前的故事') if n else t('还没有做过的故事')`。
    #   所以夹具要造成**一个有书、一个没书**：这样"换了根"在屏幕上是**可见的**，
    #   而不是"两个根都有书 → 看不出差别"（第一版就是这么写的，判据恒假红）。
    proj_b = Project.create_new(root_b, '乙根的书')       # 乙有书
    # [EN] ── B3 ★★★ Change project root directory → save → **the UI really switches** (proving "no restart
    # [EN] needed") ──
    # [EN] ⚠ How to "see" the root directory change: the start screen **doesn't show book names** (only a
    # [EN] six-item menu),
    # [EN] the project count only shows in the small text on the 「拾卷」 line ——
    # [EN] So the fixture must be made **one with books, one without books**: this way "root changed" is
    # [EN] **visible** on screen,
    # [EN] rather than "both roots have books → no difference visible" (which is how the first version was
    # [EN] written, criterion always false red).
    # [EN] B has books
    report['roots'] = {'a': str(root_a), 'b': str(root_b),
                       'b_book': proj_b.name}

    CFG.set('DEFAULT_PROJECTS_DIR', str(root_a))          # 甲：空的
    # [EN] A: empty
    app._dup_cache = None
    app.show_start_screen()
    page.update()
    await asyncio.sleep(1.0)
    before = '\n'.join(VU.all_texts(page))
    report['before_has'] = {'还没有做过的故事': '还没有做过的故事' in before,
                            '打开以前的故事': '打开以前的故事' in before}
    ok('B3a 前置（夹具）：根设成**空目录**甲之后，开始界面写「还没有做过的故事」',
       '还没有做过的故事' in before, str(report['before_has']))

    # 打开天机 → 把「项目根目录」改成「乙」（有书那个）→ 点保存
    # [EN] Open Tianji → change "project root directory" to "B" (the one with the book) → click save
    page.pop_dialog()
    page.update()
    dlg2 = app.show_global_settings()
    page.update()
    await asyncio.sleep(0.8)
    # ★★★ 2026-10-23：**记下此刻已有多少条消息**，等下只看"这次操作新增的那些"。
    #   ⚠ 原来 B3e 取的是 `app._messages[:4]`（最早的 4 条），它假设"回执一定在
    #     最前面"。而 `_messages` 是 append（旧的在前），这就等于假设**进这个对话框
    #     之前没有任何消息** —— 一旦前面已经攒了几条（比如能力校验的提示），
    #     回执被挤到第 5 条之后，判据就红，而**功能是好的**。
    #     `_messages` 前面有几条取决于用户配了几个模型、有没有三档不一致的警告，
    #     所以这条例本就**只在"前面没消息"时才成立**。
    #   ⇒ 正确口径：判"这次点保存**新增**的消息里有没有回执"。
    # [EN] ★★★ 2026-10-23: **record how many messages exist right now**; below, look only
    # at what this operation **added**. ⚠ B3e used `app._messages[:4]` (the earliest four),
    # assuming "the receipt is always first". Since `_messages` appends (oldest first), that
    # assumes **no messages existed before this dialog** -- once a few are already there
    # (e.g. capability notices), the receipt slides past index 4 and the criterion goes red
    # while **the feature is fine**. How many exist depends on how many models the user
    # configured, so the rule only ever held in the "nothing before it" case.
    # => Correct rule: judge "is there a receipt among the messages **this save added**".
    _msg_n0 = len(app._messages)
    field = next((c for c in VU.walk(dlg2)
                  if isinstance(c, ft.Row) and hasattr(c, '_field')
                  and str(getattr(c._field, 'label', '') or '') == t('项目根目录')),
                 None)
    if field is None:
        # 有的实现对 label 的存放方式不同 —— 退回"按当前值找"（值现在是甲）
        # [EN] Some implementations store the label differently —— fall back to "find by current value" (value
        # [EN] is A now)
        field = next((c for c in VU.walk(dlg2)
                      if isinstance(c, ft.Row) and hasattr(c, '_field')
                      and str(c._field.value or '') == str(root_a)), None)
    ok('B3b 找得到「项目根目录」输入框', field is not None, '')
    if field is not None:
        field._field.value = str(root_b)
        page.update()
        await asyncio.sleep(0.3)
        saved = False
        for c in VU.walk(dlg2):
            # ⚠ 用 `VU.text_of`：按钮的文字可能在 `content`（str）里，
            #   也可能在 `content.value`（Text）里 —— 自己判容易漏
            #   （第一版自己判，`保存` 没找到，保存那一路全红）。
            # [EN] ⚠ Use `VU.text_of`: a button's text may be in `content` (str),
            # [EN] or in `content.value` (Text) —— judging it yourself easily misses
            # [EN] (First version judged it itself; `保存` was not found, the whole save path was all red).
            if type(c).__name__ in ('FilledButton', 'TextButton', 'ElevatedButton'):
                if t('保存') in VU.text_of(c) and getattr(c, 'on_click', None):
                    c.on_click(None)
                    saved = True
                    break
        ok('B3c 点了「保存」', saved, '')

    await asyncio.sleep(1.2)
    ok('B3d ★★★ 保存后 `CFG.projects_dir()` 就是新目录（不用重启）',
       CFG.projects_dir() == root_b, f'{CFG.projects_dir()} / 期望 {root_b}')
    ok('B3f ★★ 重复检查的缓存被清掉了（否则向导会拿旧根去比对）',
       getattr(app, '_dup_cache', None) is None,
       type(getattr(app, '_dup_cache', None)).__name__)

    after = '\n'.join(VU.all_texts(page))
    report['after_has'] = {'还没有做过的故事': '还没有做过的故事' in after,
                           '打开以前的故事': '打开以前的故事' in after}
    ok('B3g ★★★ **界面真的当场换了**：「拾卷」那行小字从'
       '「还没有做过的故事」变成「打开以前的故事」'
       '（新根里有一本书 —— 这就是"改完立刻生效、不用重启"的证据）',
       '打开以前的故事' in after and '还没有做过的故事' not in after,
       str(report['after_has']))
    _new = app._messages[_msg_n0:]
    msgs = ' / '.join(m['text'] for m in _new)
    report['msgs'] = msgs
    report['msgs_added'] = len(_new)
    ok('B3e ★ 还给了一条回执（说清改成了哪个目录）'
       '（只判**这次保存新增**的消息，不假设"回执是最早的那几条"）',
       str(root_b) in msgs or '不用重启' in msgs or '已经生效' in msgs
       or bool(getattr(app, '_snack_text', '')), msgs[:200])
    if page.enable_screenshots:
        (OUT / 'regular_tab_proot.png').write_bytes(await page.take_screenshot())

    # 收尾：把根还原成默认（这条判据动了全局配置，改完要还回去）
    # [EN] Cleanup: restore the root to the default (this criterion touched the global config, must put it
    # [EN] back after the change)
    CFG.set('DEFAULT_PROJECTS_DIR', '')
    VU.safe_rmtree(root_a, ignore_errors=True)
    VU.safe_rmtree(root_b, ignore_errors=True)


async def entry(page: ft.Page) -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_regular_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    # 这条判据会点「保存」→ `CFG.save()`，必须整段重定向掉（别写用户的 .env）
    # [EN] This criterion clicks "保存" -> `CFG.save()`, the whole thing must be redirected (don't write the
    # [EN] user's .env)
    VU.redirect_env_writes()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.8)
    try:
        logic_checks()
        await gui_checks(page, app, tmp)
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)
    await shutdown(page, code=finish())


def finish() -> int:
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'regular_tab_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"\n常规页签验证：{len(report['checks']) - len(bad)}/"
          f"{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1200:])
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    ft.run(entry)
    sys.exit(finish())
