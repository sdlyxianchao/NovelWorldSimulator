# -*- coding: utf-8 -*-
"""判据：**注释双语化**的完整性与安全性。
Verifier: the bilingual-comment pass is complete and did not break anything.

它证明三件事（three things this proves）
-----------------------------------------
1. **完整** —— 源码里**每一条含中文的注释**后面都跟着一条 `# [EN]` 英文行
   （哪个文件缺了几条，会点名报出来）；
2. **干净** —— `# [EN]` 那行本身**不含中文**（模型偶尔会把中文原样吐回来，
   写进"英文行"里就成了半吊子）；
3. **没弄坏代码** —— 全项目 `ast.parse` 通过，而且**代码行一条没变**
   （拿 `.bak-bilingual` 与现文件逐行比对：除注释行外必须完全一致）。

★ 第 3 条是这一支最要紧的：注释双语化动的是**全项目 450+ 个源文件**，
  "写回把代码改坏了"是这场操作唯一真正危险的地方。所以判据必须有
  **代码行级别的对照**（不是"能 import 就算数"）。

产物：`assets/screenshots/bilingual_report.json`

Criterion: the completeness and safety of **comment bilingualization**.
Verifier: the bilingual-comment pass is complete and did not break anything.
It proves three things (three things this proves)
-----------------------------------------
1. **Complete** — **every comment containing Chinese** in the source is followed by a `# [EN]` English line
   (which files are missing how many will be called out by name);
2. **Clean** — the `# [EN]` line itself **contains no Chinese** (the model occasionally spits the Chinese back verbatim,
   and once that gets written into the "English line" it becomes half-baked);
3. **Did not break the code** — the whole project passes `ast.parse`, and **not a single code line changed**
   (compare `.bak-bilingual` with the current file line by line: everything except comment lines must be exactly identical).
★ Item 3 is the most critical for this branch: comment bilingualization touches **450+ source
files across the whole project**,
  and "the write-back broke the code" is the only truly dangerous part of this operation. So the criterion must include
  **a code-line-level comparison** (not "it can import so it counts").
Artifact: `assets/screenshots/bilingual_report.json`

English:
Criterion: the completeness and safety of **comment bilingualization**.
Verifier: the bilingual-comment pass is complete and did not break anything.
It proves three things (three things this proves)
-----------------------------------------
1. **Complete** — **every comment containing Chinese** in the source is followed by a `# [EN]` English line
   (which files are missing how many will be called out by name);
2. **Clean** — the `# [EN]` line itself **contains no Chinese** (the model occasionally spits the Chinese back verbatim,
   and once that gets written into the "English line" it becomes half-baked);
3. **Did not break the code** — the whole project passes `ast.parse`, and **not a single code line changed**
   (compare `.bak-bilingual` with the current file line by line: everything except comment lines must be exactly identical).
★ Item 3 is the most critical for this branch: comment bilingualization touches **450+ source
files across the whole project**,
  and "the write-back broke the code" is the only truly dangerous part of this operation. So the criterion must include
  **a code-line-level comparison** (not "it can import so it counts").
Artifact: `assets/screenshots/bilingual_report.json`
Criterion: the completeness and safety of **comment bilingualization**.
Verifier: the bilingual-comment pass is complete and did not break anything.
It proves three things (three things this proves)
-----------------------------------------
1. **Complete** — **every comment containing Chinese** in the source is followed by a `# [EN]` English line
   (which files are missing how many will be called out by name);
2. **Clean** — the `# [EN]` line itself **contains no Chinese** (the model occasionally spits the Chinese back verbatim,
   and once that gets written into the "English line" it becomes half-baked);
3. **Did not break the code** — the whole project passes `ast.parse`, and **not a single code line changed**
   (compare `.bak-bilingual` with the current file line by line: everything except comment lines must be exactly identical).
★ Item 3 is the most critical for this branch: comment bilingualization touches **450+ source
files across the whole project**,
  and "the write-back broke the code" is the only truly dangerous part of this operation. So the criterion must include
  **a code-line-level comparison** (not "it can import so it counts").
Artifact: `assets/screenshots/bilingual_report.json`
"""

from __future__ import annotations

import ast
import io
import json
import re
import sys
import tokenize
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "tools"))

OUT = APP / "assets" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "bilingual_report.json"

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
EN_MARK = "# [EN] "

CHECKS: list[dict] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    CHECKS.append({"name": name, "ok": bool(cond), "detail": str(detail)[:700]})
    print(("  ✓ " if cond else "  ✗ ") + name
          + (f"   [{detail}]" if detail and not cond else ""))
    return bool(cond)


def section(t: str) -> None:
    print(f"\n── {t} " + "─" * max(0, 56 - len(t)))


def _iter() -> list[Path]:
    """与工具同一份扫描口径（**从工具里 import**，避免两处各写一份）。
    Same scan as the tool — imported, not re-implemented.
    
    Same scan scope as the tool (**imported from the tool**, to avoid writing it twice in two
    places).
        Same scan as the tool — imported, not re-implemented.
    
        English:
    Same scan scope as the tool (**imported from the tool**, to avoid writing it twice in two
    places).
        Same scan as the tool — imported, not re-implemented.
        Same scan scope as the tool (**imported from the tool**, to avoid writing it twice in two
        places).
            Same scan as the tool — imported, not re-implemented.
    """
    from bilingualize_comments import SKIP_PARTS, SKIP_PREFIX, iter_files
    out = []
    for p in iter_files():
        rel = p.relative_to(APP).as_posix()
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if rel.startswith(SKIP_PREFIX):
            continue
        out.append(p)
    return out


def scan_file(p: Path) -> tuple[int, int, list[int], list[int]]:
    """一个文件的 `(含中文注释行数, 已带译文的行数, 缺译文的行号, 英文行里混中文的行号)`。
    Per file: chinese comment count, translated count, missing rows, dirty rows.
    
    A file's `(count of comment lines containing Chinese, count of lines already carrying
    translations, line numbers missing translations, line numbers where the English line is mixed
    with Chinese)`.
        Per file: chinese comment count, translated count, missing rows, dirty rows.
    
        English:
    A file's `(count of comment lines containing Chinese, count of lines already carrying
    translations, line numbers missing translations, line numbers where the English line is mixed
    with Chinese)`.
        Per file: chinese comment count, translated count, missing rows, dirty rows.
        A file's `(count of comment lines containing Chinese, count of lines already carrying
        translations, line numbers missing translations, line numbers where the English line is mixed
        with Chinese)`.
            Per file: chinese comment count, translated count, missing rows, dirty rows.
    """
    try:
        src = p.read_text(encoding="utf-8")
    except OSError:
        return 0, 0, [], []
    lines = src.split("\n")
    n_cn = n_en = 0
    missing: list[int] = []
    dirty: list[int] = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception:                                       # noqa: BLE001
        return 0, 0, [], []
    #  ★★ **按"注释块"判，不按"行"判** —— 双语化产出的是**块级**形态：
    #    一整段中文之后跟一整段 `# [EN]`。所以块内**中间**那几行中文注释
    #    后面**不会**紧跟译文（只有**块尾**才有）。
    #    第一版按行判 ⇒ 长块里除最后一行外全被算成"缺译文"
    #    （实测报出 9109 条假缺）。
    # [EN] ★★ **Judge by "comment block", not by "line"** -- bilingualization produces a **block-level**
    # [EN] form:
    # [EN] A whole Chinese paragraph is followed by a whole `# [EN]` paragraph. So the Chinese comment
    # [EN] lines in the **middle** of a block
    # [EN] are **not** immediately followed by a translation (only the **block end** has one).
    # [EN] The first version judged by line => in a long block, all but the last line were counted as
    # [EN] "missing translation"
    # [EN] (measured: 9109 false missing reports).
    #    Per *block*, not per line: with block-level bilingual output, only the
    #    LAST line of a Chinese comment block is followed by the `# [EN]` run.
    seq: list[tuple[int, bool, bool]] = []          # (row, is_en, has_cn)
    for t in toks:
        if t.type != tokenize.COMMENT:
            continue
        row = t.start[0] - 1
        if row >= len(lines):
            continue
        raw = t.string
        body = raw.lstrip("#").strip()
        if not body:
            continue
        is_en = raw.startswith(EN_MARK)
        if is_en:
            #  ⚠ "英文行里混中文"的判据要跟 `_usable()` **同口径**：允许
            #    **少量**中文专有名词（`第N次模拟` 这类），只拒"基本还是中文"。
            #    第一版要求"绝对不含中文"⇒ 与工具的收稿口径打架，两边各红一次。
            # [EN] ⚠ The criterion for "English lines mixed with Chinese" must use the **same standard** as
            # [EN] `_usable()`: allow
            # [EN] **a small amount** of Chinese proper nouns (like `第N次模拟`), and only reject "basically still
            # [EN] Chinese".
            # [EN] The first version required "absolutely no Chinese" => it clashed with the tool's acceptance
            # [EN] standard, and both sides went red once.
            _cn = len(CJK.findall(body))
            _en = len(re.findall(r"[A-Za-z]{2,}", body))
            #  与 `_usable()` **同口径**：只有"整行几乎全是中文"才算没译好。
            #  （本项目大量注释是「短句 + 中文示例」，译文里带专有名词是正常的。）
            # [EN] Same criteria as `_usable()`: only "almost the entire line is Chinese" counts as not translated
            # [EN] well.
            # [EN] (Many comments in this project are "short sentence + Chinese example"; it is normal for
            # [EN] translations to contain proper nouns.)
            if _cn >= 8 and _en <= 2:
                dirty.append(row + 1)          # 整行还是中文 → 不算译好
                # [EN] Still Chinese -> not counted as translated
            seq.append((row, True, False))
            continue
        seq.append((row, False, bool(CJK.search(body))))

    i = 0
    while i < len(seq):
        row, is_en, has_cn = seq[i]
        if is_en or not has_cn:
            i += 1
            continue
        # 从这一行开始，取**连续**的中文注释行 = 一块
        # [EN] Starting from this line, take **consecutive** Chinese comment lines = one block
        j = i
        while (j + 1 < len(seq) and seq[j + 1][2] and not seq[j + 1][1]
               and seq[j + 1][0] == seq[j][0] + 1):
            j += 1
        n_cn += (j - i + 1)
        # 块尾的**下一条注释**必须是 `# [EN]`，而且必须**紧跟**（行号连续）
        # [EN] The **next comment** after the block end must be `# [EN]`, and must **immediately follow**
        # [EN] (consecutive line numbers)
        nxt = seq[j + 1] if j + 1 < len(seq) else None
        if nxt is not None and nxt[1] and nxt[0] == seq[j][0] + 1:
            n_en += 1
        else:
            missing.append(seq[j][0] + 1)
        i = j + 1
    return n_cn, n_en, missing, dirty


#: ★ **双语化之后又被手工改过**的文件 —— C2/C3 都要放行它们。
#: 它们就是"给工具加幂等 / 加反斜杠转义 / 改判据口径"这件事本身，
#: 指纹与 docstring 当然和备份不同；那不是"工具改坏了代码"。
#: （**显式列出 + 写明理由**，而不是把判据放宽到"随便"。）
# [EN] : ★ **Files that were manually edited after bilingualization** -- both C2/C3 must let them pass.
# [EN] : They are exactly the "add idempotency / add backslash escaping / change criterion standard"
# [EN] work itself,
# [EN] : the fingerprint and docstring naturally differ from the backup; that is not "the tool broke
# [EN] the code".
# [EN] : (**explicitly listed + reason stated**, rather than loosening the criterion to "anything
# [EN] goes".)
MANUAL_EDIT = {
    "tools/bilingualize_comments.py",     # 工具本身（幂等/转义/口径都是后加的）
    "tools/verify_bilingual.py",          # 这一支自己
    "tools/verify_generic_project.py",    # 清"专有名词"时它也被改（黑名单词是它的数据）
    "tools/verify_sdk.py",                # 双语化之后删了一行死代码
    "developers/sdk/nws/aio.py",          # 示例里的书名换成了占位名
    # [EN] The tool itself (idempotency/escaping/conventions were all added later)
    # [EN] This branch itself
    # [EN] When cleaning "proper nouns" it also gets modified (the blacklist words are its data)
    # [EN] After bilingualization, a line of dead code was deleted
    # [EN] The book title in the example was replaced with a placeholder name
    "developers/sdk/nws/cli.py",
    "developers/sdk/nws/mumu.py",
    "developers/sdk/nws/usage.py",
    "make_art.py",                     # 2026-10-13 加 start_logo 圆角步骤（代码+注释均主动改动）
    # ── 2026-10-11（界面字体与字号 · 命令行开关 · 版本 0.2.0）──
    #   这一轮**故意改了这些文件的代码**：新增三个配置项（`UI_FONT` /
    #   `UI_FONT_SCALE` / `HIDE_COMMAND_BAR`）、默认字体换成思源宋体、
    #   整个界面的字号收进 `apply_font_settings()` 按比例缩放、发布脚本补三类
    #   本机过程产物到排除清单。所以 C2/C3 的指纹与备份必然不同 ——
    #   这不是"双语化工具改坏了代码"。
    #   逐个文件为什么被改：
    #     · `config.py` —— 三个新配置项 + 版本号 0.2.0；
    #     · `gui/app_flet.py` —— 字体/字号/命令行开关 + `SZ()` 缩放；
    #     · `i18n.py` —— 新文案的中英对照；
    #     · `tools/make_release.py` —— 排除清单补 `usage.db` / `*.bak-bilingual` /
    # [EN] ── 2026-10-11 (UI font and font size · CLI flag · version 0.2.0) ──
    # [EN] This round **deliberately changed the code of these files**: added three new config items
    # [EN] (`UI_FONT` /
    # [EN] `UI_FONT_SCALE` / `HIDE_COMMAND_BAR`), switched the default font to Source Han Serif,
    # [EN] scaled all UI font sizes proportionally inside `apply_font_settings()`, and added three
    # [EN] categories of
    # [EN] local process artifacts to the release script's exclusion list. So C2/C3 fingerprints and
    # [EN] backups will necessarily differ ——
    # [EN] this is not "the bilingualization tool broke the code".
    # [EN] Why each file was changed:
    # [EN] · `config.py` —— three new config items + version number 0.2.0;
    # [EN] · `gui/app_flet.py` —— font/font size/command bar flag + `SZ()` scaling;
    # [EN] · `i18n.py` —— Chinese-English pairs for the new strings;
    # [EN] · `tools/make_release.py` —— added `usage.db` / `*.bak-bilingual` /
    #       `.bilingual_done.json`；
    #     · `tools/platform_install.py` —— 版本号同步 0.2.0；
    #     · `tools/verify_font.py` —— 字形辨认的候选表要跟上新默认字体；
    #     · `tools/verify_opacity.py` —— 界面外观页多了一根滑杆，改成按区间认不透明度滑杆；
    #     · `tools/run_all_verifications.py` —— 新判据登记进分组 + 加 `--skip`；
    # [EN] · `tools/platform_install.py` —— version number synced to 0.2.0;
    # [EN] · `tools/verify_font.py` —— the candidate table for glyph recognition must keep up with the new
    # [EN] default font;
    # [EN] · `tools/verify_opacity.py` —— the UI appearance page has one more slider, changed to
    # [EN] recognizing the opacity slider by range;
    # [EN] · `tools/run_all_verifications.py` —— new criteria registered into groups + added `--skip`;
    #     · `tools/verify_main_screen.py` / `verify_main_flags.py` / `verify_script_output.py`
    #       —— 命令行默认不显示了，而这三支测的是"叙事区与命令栏之间没有空白"，
    #       所以显式把它打开（判据含义不变），并加上 `.env` 写保护。
    # [EN] —— the command line is hidden by default, and these three tests check that "there is no blank
    # [EN] space between the narrative area and the command bar",
    # [EN] so explicitly turn it on (criterion meaning unchanged), and add `.env` write protection.
    "config.py",
    "gui/app_flet.py",
    "i18n.py",
    "tools/make_release.py",
    "tools/platform_install.py",
    "tools/verify_font.py",
    "tools/verify_opacity.py",
    "tools/run_all_verifications.py",
    "tools/verify_main_screen.py",
    "tools/verify_main_flags.py",
    "tools/verify_script_output.py",
    # ── 2026-10-11（叙事窗口：分页 + 每条的时间戳）──
    #   这一轮又**故意改了** `gui/app_flet.py` 与 `config.py` 的代码：中栏两处
    #   "偷偷丢内容"的老写法（`[-200:]` 与 `del col.controls[:100]`）换成按页渲染、
    #   加了翻页条与 `NARR_TIMESTAMP` / `NARR_PAGE_ENTRIES` 两个配置项、
    #   `_live_lines` 的元素从三元组扩成四元组（尾部加时间戳）。
    #   所以 C2/C3 的指纹必然不同 —— 那当然不是"双语化工具改坏了代码"。
    # [EN] ── 2026-10-11 (narrative window: paging + per-entry timestamps) ──
    # [EN] This round again **deliberately changed** the code in `gui/app_flet.py` and `config.py`: the
    # [EN] two old "silently drop content" spots in the middle column (`[-200:]` and
    # [EN] `del col.controls[:100]`) became page rendering, a pager bar plus the two config keys
    # [EN] `NARR_TIMESTAMP` / `NARR_PAGE_ENTRIES` were added, and `_live_lines` elements grew from a
    # [EN] 3-tuple to a 4-tuple (timestamp appended at the tail). So the C2/C3 fingerprints necessarily
    # [EN] differ -- that is of course not "the bilingualization tool broke the code".
    # ── 2026-10-11（用量窗口栏宽 / 默认最大化 / 第 4 栏横向滚动）──
    #   这一轮**故意改了这两个文件的代码**：用量对话框的四栏宽度（`_pane` 的
    #   `expand`/`width` 只能给一个）、默认最大化改按**客户区**算、第 4 栏加了
    #   横向滚动区 + 自绘横条 + 开局主动量一次；另把 `verify_usage_filters` 的 C3
    #   从"跨度占屏宽百分比"改成"簇的个数与间距"。所以 C2/C3 的指纹必然不同。
    # [EN] ── 2026-10-11 (usage window column widths / maximized by default / column 4's horizontal
    # [EN] scrolling) ──
    # [EN] This round **deliberately changed the code in these two files**: the usage dialog's four
    # [EN] column widths (`_pane` may take only one of `expand`/`width`), the default maximization now
    # [EN] computed from the **client area**, and column 4 gained a horizontal scroll area + a
    # [EN] self-drawn bar + an up-front measurement; also, C3 in `verify_usage_filters` changed from
    # [EN] "span as a percentage of screen width" to "number of clusters and their gaps". So the C2/C3
    # [EN] fingerprints necessarily differ.
    "gui/usage_dialog.py",
    "tools/verify_usage_filters.py",
    # ★ 顺带（2026-10-11）：`verify_usage_stats` 的 G3（钉的是旧算式
    #   `size * 0.94`）与 G4（裸 `ask(` 用子串检查）都在这一轮改了口径，
    #   理由逐条写在各自那段注释里。
    # [EN] ★ Also (2026-10-11): G3 in `verify_usage_stats` (which pinned the old formula
    # [EN] `size * 0.94`) and G4 (a bare `ask(` checked as a substring) both changed convention this
    # [EN] round; the reasons are written one by one in their own comment blocks.
    "tools/verify_usage_stats.py",
    # ★ `developers/mutate_usage_layout.py`：**反例法脚本**（不是产品代码）。
    #   它在双语化之后又加了两条变异（M8 治 C3 的新口径、M9 治 G4 的词边界），
    #   于是与 `.bak-bilingual` 的指纹不同 —— 那当然不是"工具改坏了代码"。
    # [EN] ★ `developers/mutate_usage_layout.py`: a **reverse-experiment script** (not product code).
    # [EN] It gained two more mutations after bilingualization (M8 for C3's new convention, M9 for G4's
    # [EN] word boundary), so its fingerprint differs from `.bak-bilingual` -- that is of course not "the
    # [EN] tool broke the code".
    "developers/mutate_usage_layout.py",
    # ★ `tools/verify_llm_caps.py`：这一轮把 ④ 段那条判据从**按下标切片**
    #   （`app._messages[n_before:]`）改成**数条数 + 轮询等异步保存**，
    #   理由写在 `_restart_msgs` 的 docstring 里（固定睡 0.8s 在机器忙时不够，
    #   于是"保存后多了一条提示"假红，而产品明明发了）。
    # [EN] ★ `tools/verify_llm_caps.py`: this round changed the criterion in section 4 from an
    # [EN] **index slice** (`app._messages[n_before:]`) to **counting + polling for the async save**,
    # [EN] with the reasoning in `_restart_msgs`'s docstring (a fixed 0.8s sleep isn't enough when the
    # [EN] machine is busy, so "one more hint after saving" went falsely red even though the product
    # [EN] did post it).
    "tools/verify_llm_caps.py",
    # ★ `developers/shoot_usage_dialog.py`：**开发期截图脚本**。这一轮给它补了
    #   `assets_dir`（原来不传 ⇒ 拍出来的图是系统字体，跟真实界面不一样）
    #   并加了"窄窗口"那张（第 4 栏横条的底片）。
    # [EN] ★ `developers/shoot_usage_dialog.py`: a **development-time screenshot script**. This round it
    # [EN] gained `assets_dir` (it wasn't passed ⇒ captured images used a system font, unlike the real
    # [EN] UI) and a "narrow window" shot (the negative for column 4's horizontal bar).
    "developers/shoot_usage_dialog.py",
    # ── 2026-10-11（场次编排：剧作家的分拍表下达 + 按拍收场 / 换场）──
    #   这一轮按作者的报障补了"一场戏接一场戏"那一层，**故意改了**这五个文件的
    #   代码：`sim/loop.py`（收场、换场、按拍记账）、`agent/core.py`（「本场」
    #   段的下达）、`crew/agents.py`（剧作家多写四栏：主题/出场/要点/道具/情绪）、
    #   `director/day_plan.py`（分拍表的文本化 + 验算加一条自问）、
    #   `world/state.py`（两个新字段：`stage_plan` / `stage_index`）。
    #   所以 C2/C3 的指纹必然不同 —— 那当然不是"双语化工具改坏了代码"。
    # [EN] ── 2026-10-11 (stage scheduling: the playwright's beat sheet handed down + wrap-up /
    # [EN] scene change by beat) ──
    # [EN] This round added the "one scene after another" layer for the author's reported problem and
    # [EN] **deliberately changed the code in these five files**: `sim/loop.py` (wrap-up, scene
    # [EN] change, per-beat ledger), `agent/core.py` (handing down the "this scene" block),
    # [EN] `crew/agents.py` (the playwright writes four more columns: 主题/出场/要点/道具/情绪),
    # [EN] `director/day_plan.py` (turning the beat sheet into text + one more self-question at
    # [EN] verification), `world/state.py` (two new fields: `stage_plan` / `stage_index`).
    # [EN] So the C2/C3 fingerprints necessarily differ -- that is of course not "the bilingualization
    # [EN] tool broke the code".
    "sim/loop.py",
    "agent/core.py",
    "crew/agents.py",
    "director/day_plan.py",
    "world/state.py",
    # ── 2026-10-11（运行页面板搬家 / 点标题跳设置）──
    #   运行页那一轮**加了时间戳**（`_live_lines` 从三元组变四元组），这两个判据里
    #   按三元解包的写法会当场 `ValueError`，所以**改了它们的代码**（改成下标访问）。
    #   指纹与 `.bak-bilingual` 必然不同 —— 那不是"双语化工具改坏了代码"。
    # [EN] ── 2026-10-11 (run-page panel relocation / title-click jumps to settings) ──
    # [EN] That round **added a timestamp** to the run page (`_live_lines` went from a 3-tuple to a
    # [EN] 4-tuple), and the 3-way unpacking in these two criteria would raise `ValueError` on the spot, so
    # [EN] **their code was changed** (switched to index access). The fingerprints necessarily differ from
    # [EN] `.bak-bilingual` -- that is not "the bilingualization tool broke the code".
    "tools/verify_story_depth.py",
    "tools/verify_run_output_style.py",
    # 运行页面板那一轮**改了判据**的三支（改了判据就得有变异证明——
    # 三条变异 M17/M18/M19 分别落在它们身上，所以代码与 `.bak-bilingual` 不同）。
    # [EN] The three criteria **changed** during the run-page panel round (a changed criterion needs a
    # [EN] mutation proof -- mutations M17/M18/M19 land on them respectively, so their code differs from
    # [EN] `.bak-bilingual`).
    "developers/mutate_run_panel_nav.py",
    "tools/verify_crew_highlight.py",
    "tools/verify_regular_tab.py",
    # ── 2026-10-11（向导第 4 步车道 + `.env` 第四道保险丝）──
    #   这一轮改了这些**产品代码与判据**，指纹/文档数当然与备份不同：
    #     · `config.py` —— `env_sink_path()` 加"进程自己认得出是验证脚本"的兜底
    #       （第四条保险丝），并补 `import sys`；
    #     · `gui/app_flet.py` —— 向导第 4 步各元素补 `width=SET_W`、
    #       分页那一行改窄 + 「每页」下拉改成"标签写用途 + 选项纯数字"；
    #     · `i18n.py` —— 新增 `每页` 的译文；
    #     · `tools/verify_ui_common.py` —— 抽出"分页那一行"的公共探针（3 个新函数）；
    #     · `tools/verify_agent_catalog.py` —— D2b 口径改了（见那段注释）；
    #     · `tools/verify_help_book.py` —— 补 `VU.redirect_env_writes()`；
    #     · `tools/run_all_verifications.py` —— 两支新判据登记进分组。
    # [EN] ── 2026-10-11 (wizard step 4's lane + the fourth `.env` fuse) ──
    # [EN] This round changed these **product files and criteria**, so fingerprints/doc counts naturally
    # [EN] differ from the backups:
    # [EN] · `config.py` -- `env_sink_path()` gained the "the process recognizes it is a verification
    # [EN] script" fallback (the fourth fuse) plus `import sys`;
    # [EN] · `gui/app_flet.py` -- wizard step 4's elements gained `width=SET_W`, the pagination row was
    # [EN] narrowed, and the "per page" dropdown became "label says what it is + bare-number options";
    # [EN] · `i18n.py` -- added the translation for "每页";
    # [EN] · `tools/verify_ui_common.py` -- extracted the shared probe for "the pagination row" (3 new
    # [EN] functions);
    # [EN] · `tools/verify_agent_catalog.py` -- D2b's convention changed (see that note);
    # [EN] · `tools/verify_help_book.py` -- added `VU.redirect_env_writes()`;
    # [EN] · `tools/run_all_verifications.py` -- two new criteria registered into groups.
    "config.py",
    "tools/verify_ui_common.py",
    "tools/verify_agent_catalog.py",
    "tools/verify_help_book.py",
    # ★ 本轮**新建**的两支（`verify_env_safety` / `mutate_env_safety`）：
    #   双语化工具给它们生成了 `.bak-bilingual`，之后我又改了内容
    #   （A3 的口径、反例法的锚点、K5 的注释等）⇒ 指纹当然不同。
    # [EN] ★ The two criteria **created** this round (`verify_env_safety` / `mutate_env_safety`): the
    # [EN] bilingualization tool produced `.bak-bilingual` for them, and I changed the content afterwards
    # [EN] (A3's convention, the reverse experiments' anchors, K5's notes, etc.) ⇒ fingerprints differ.
    "tools/verify_env_safety.py",
    "developers/mutate_env_safety.py",
    # ── 2026-10-11 深夜（开卷向导第 4 步"刚好贴着滚动条" + 标题钉住 + 摄取输入框三行）──
    #   这一轮**故意改了**这些产品代码与判据（理由逐条写在各处注释里），
    #   所以 C2/C3 的指纹与 docstring 数必然和 `.bak-bilingual` 不同 ——
    #   那不是"双语化工具改坏了代码"：
    #     · `gui/app_flet.py` —— `_wizard_body(head=…)`（标题钉在滚动区外）、
    #       五步的标题各自拆成 `head`、`WIZ_W`(580) 取代 `SET_W`(520)、
    #       `mk_scroll_bar` 的条宽改走 `SCROLL_BAR_W`、摄取对话框的聊天输入框
    #       改成三行（`CHAT_INPUT_LINES`）+ 那一行显式居中；
    #     · `tools/verify_wizard_agent_lane.py` —— 重写（A/B/C 三组）；
    #     · `tools/verify_ingest_rounds.py` —— 新增 A16/A17/A18 与真机 B4/B4b/B4c；
    #     · `developers/probe_wizard_agents_lane.py` —— 重写（加"滚一次看标题动不动"）；
    #     · `developers/mutate_ingest_rounds.py` —— 新增 ⑫/⑫b/⑬/⑭，并修复两条
    #       被**双语化**插了 `# [EN]` 行之后**再也对不上**的老锚点（⑤/⑦）。
    # [EN] ── 2026-10-11 late night (wizard step 4 "just touching the scrollbar" + pinned title +
    # [EN] the ingest input's three lines) ──
    # [EN] This round **deliberately changed** these product files and criteria (each reason is written
    # [EN] in its own comment), so the C2/C3 fingerprints and docstring counts necessarily differ from
    # [EN] `.bak-bilingual` -- that is not "the bilingualization tool broke the code":
    # [EN] · `gui/app_flet.py` -- `_wizard_body(head=...)` (title pinned outside the scroll area), all
    # [EN] five steps' titles split out into `head`, `WIZ_W` (580) replacing `SET_W` (520),
    # [EN] `mk_scroll_bar`'s bar width going through `SCROLL_BAR_W`, and the ingest dialog's chat input
    # [EN] becoming three lines (`CHAT_INPUT_LINES`) with that row explicitly centred;
    # [EN] · `tools/verify_wizard_agent_lane.py` -- rewritten (groups A/B/C);
    # [EN] · `tools/verify_ingest_rounds.py` -- added A16/A17/A18 plus real-machine B4/B4b/B4c;
    # [EN] · `developers/probe_wizard_agents_lane.py` -- rewritten (adds "scroll once and see whether the
    # [EN] title moves");
    # [EN] · `developers/mutate_ingest_rounds.py` -- added ⑫/⑫b/⑬/⑭ and repaired two old anchors
    # [EN] (⑤/⑦) that **no longer matched** after bilingualization inserted `# [EN]` lines.
    "tools/verify_wizard_agent_lane.py",
    "tools/verify_ingest_rounds.py",
    "developers/probe_wizard_agents_lane.py",
    "developers/mutate_ingest_rounds.py",
    # ── 2026-10-12 凌晨（"听懂作者的指令" + 剧组页签车道 + 起笔建议框）──
    #   这一轮**故意改了/新建了**这些产品代码与判据，指纹/docstring 数必然与
    #   `.bak-bilingual` 不同 —— 那不是"双语化工具改坏了代码"：
    #     · `polish/intent.py` —— **新建**：把"修复4个问题/所有问题不要问我/
    #       至少3轮别问我/处理 1 2"解析成结构化意图（纯函数）；
    #     · `polish/agent.py` —— 意图接进 Agent：编号清单下达、免打扰**硬拦**、
    #       轮数递减、`turn.notes` 回给作者；
    #     · `gui/app_flet.py` —— 把那句"我懂你的意思了"打进对话栏；剧组列表行
    #       改 `width=SET_W`；起笔建议框的占位提示改灰 + 缩短；
    #     · `i18n.py` —— 上面那些新文案的中英对照；
    #     · 这两份**新建**的判据与反例法：`tools/verify_polish_intent.py`
    #       与 `developers/mutate_polish_intent.py`；
    #     · `tools/verify_agent_catalog.py` —— 新增 D7/D7b（像素量"列表行不压滚动条"）；
    #     · `tools/verify_round_controls.py` —— 新增 F3b/F3c（占位提示灰、不长）；
    #     · `developers/mutate_wizard_agent_lane.py` —— 老锚点跟着 `WIZ_W` 改名，
    #       并补上"旧口径"的期望标签（M4~M7）。
    # [EN] ── 2026-10-12 early morning ("understand the author's instruction" + crew tab lane +
    # [EN] start-writing suggestion box) ──
    # [EN] This round **deliberately changed/created** these product files and criteria, so the
    # [EN] fingerprints/docstring counts necessarily differ from `.bak-bilingual` -- that is not "the
    # [EN] bilingualization tool broke the code":
    # [EN] · `polish/intent.py` -- **new**: parses "fix the 4 problems / all problems don't ask me /
    # [EN] don't ask me for at least 3 rounds / process 1 2" into a structured intent (pure functions);
    # [EN] · `polish/agent.py` -- the intent is wired into the Agent: the numbered list is handed down,
    # [EN] do-not-disturb becomes a **hard block**, the round count decrements, `turn.notes` goes back to
    # [EN] the author;
    # [EN] · `gui/app_flet.py` -- prints that "I understood that" line into the chat pane; the crew list
    # [EN] row becomes `width=SET_W`; the start-writing suggestion box's placeholder becomes grey and
    # [EN] shorter;
    # [EN] · `i18n.py` -- Chinese/English pairs for those new strings;
    # [EN] · `tools/verify_polish_intent.py` / `developers/mutate_polish_intent.py` -- the **new**
    # [EN] criterion and counterexample harness;
    # [EN] · `tools/verify_agent_catalog.py` -- added D7/D7b (pixel-measuring "the list row must not
    # [EN] press the scrollbar");
    # [EN] · `tools/verify_round_controls.py` -- added F3b/F3c (the placeholder is grey and not long);
    # [EN] · `developers/mutate_wizard_agent_lane.py` -- old anchors renamed along with `WIZ_W`, plus the
    # [EN] expected labels of the old conventions (M4~M7).
    "polish/intent.py",
    "polish/agent.py",
    "tools/verify_polish_intent.py",
    "developers/mutate_polish_intent.py",
    "developers/probe_crew_tab_lane.py",
    "developers/mutate_wizard_agent_lane.py",
    "tools/verify_round_controls.py",
    # ── 2026-10-12（语言审校的出口与下游）──
    #   用户问：「每天最后的语言审校**为何都是放到一个 md**，而不是输出出来」，
    #   并拍板两件事：**并进今日总结** + **把下游（下一天的剧作者）接上**。
    #   这一轮**故意改了**这些产品代码与判据（理由逐条写在各自那段注释里）：
    #     · `crew/studio.py` —— `call(extra_section=…)`（把附加段落合进正文，
    #       四处一次到位：md / 中栏 / 台账 / 日志）、`polish_section()`、
    #       `polish_brief()`，`wrap()` 把语言审校并进复盘那一份；
    #     · `director/day_plan.py` —— `brief` 里补上"昨天语言审校点出的问题"；
    #     · `sim/loop.py` —— 那条小消息的指向随复盘开关走；**并补上漏掉的
    #       `from i18n import t`**（本模块一直在用 `t()` 却没导入，见那段注释）；
    #     · `i18n.py` —— 新文案 + 修正一条 key（少了一个 `★`，英文界面下静默退回中文）；
    #     · `tools/verify_crew_flow.py` —— 新增 F 组；另删掉夹具里那颗
    #       "第二次调用就炸"的 `asyncio.get_event_loop()` 定时炸弹；
    #     · `tools/verify_studio_v2.py` —— A7 从**字符串哨兵**改成 **AST 判**；
    #     · `developers/mutate_crew_flow.py` —— 新增 ⑫~⑰，并修 ②/⑥ 两条老锚点。
    # [EN] ── 2026-10-12 (the language review's outlet and downstream) ──
    # [EN] The user asked: "why is the day's final language review **always put into an md** instead of
    # [EN] being output", and decided two things: **merge into today's summary** + **wire up the
    # [EN] downstream (next day's screenwriter)**.
    # [EN] This round **deliberately changed** these product files and criteria (each reason is written in
    # [EN] its own comment):
    # [EN] · `crew/studio.py` -- `call(extra_section=...)` (merges an extra block into the body, hitting
    # [EN] all four places at once: md / middle column / ledger / log), `polish_section()`,
    # [EN] `polish_brief()`, and `wrap()` merging the language review into the retrospective's note;
    # [EN] · `director/day_plan.py` -- `brief` gains "what yesterday's language review flagged";
    # [EN] · `sim/loop.py` -- that small message's pointer follows the retrospective switch; **plus the
    # [EN] missing `from i18n import t`** (this module always used `t()` without importing it, see that
    # [EN] note);
    # [EN] · `i18n.py` -- new strings + a corrected key (missing one `★`, which silently fell back to
    # [EN] Chinese in the English UI);
    # [EN] · `tools/verify_crew_flow.py` -- new group F; also removed that "blows up on the second call"
    # [EN] `asyncio.get_event_loop()` time bomb in the fixture;
    # [EN] · `tools/verify_studio_v2.py` -- A7 changed from a **string sentinel** to an **AST check**;
    # [EN] · `developers/mutate_crew_flow.py` -- added ⑫~⑰ and fixed two old anchors (②/⑥).
    "crew/studio.py",
    "sim/loop.py",
    "director/day_plan.py",
    "tools/verify_crew_flow.py",
    "tools/verify_studio_v2.py",
    "developers/mutate_crew_flow.py",
    # ★ `developers/mutate_agent_catalog.py` / `mutate_round_controls.py`：
    #   反例法脚本（不是产品代码）。它们是在**上一轮**（2026-10-12 凌晨那一批）
    #   被改的（各加了几条变异），当时漏登记了 —— 这一轮跑到 C2 才现形。
    #   ⚠ 教训：**新增/改动一支反例法也要登记**，别只登记产品代码 ——
    #     漏了的话它会一直挂在 C2 的不一致名单里，下一轮的人会以为是新问题。
    # [EN] ★ `developers/mutate_agent_catalog.py` / `mutate_round_controls.py`: counterexample scripts
    # [EN] (not product code). They were changed in the **previous** round (the early-2026-10-12 batch,
    # [EN] each gaining a few mutations) and went unregistered then -- only surfacing in C2 this round.
    # [EN] ⚠ Lesson: **adding or changing a counterexample harness must be registered too**, not just
    # [EN] product code -- otherwise it sits in C2's mismatch list forever and the next person reads it as
    # [EN] a new problem.
    "developers/mutate_agent_catalog.py",
    "developers/mutate_round_controls.py",
    # ── 2026-10-12（起笔的启动守卫：连点两次 / 超时 / 只留一个）──
    #   用户报：「连续点了两次起笔，结果就同时有两个推演过程在进行」+
    #   「点了起笔之后感觉没反应了一段时间」+「引入超时机制……两个里只留一个」。
    #   这一轮**故意改了**底下这些（理由逐条写在各自那段注释里）：
    #     · `gui/app_flet.py` —— 启动守卫（`_launch_arm` / `_launch_watch` /
    #       这三支：`_launch_cancel` / `_launch_release` / `_launch_discard_run`）、
    #       点完立刻切运行页、装配丢进 `asyncio.to_thread`、**主线程建 db**、
    #       两处令牌校验、`_begin_run` 那处对号、状态行两条口径、按钮变灰；
    #     · `sim/setup.py` —— `assemble(..., db=None)`：允许调用方把
    #       **在主线程建好**的连接递进来（SQLite 连接不许跨线程用）；
    #     · `config.py` —— 新旋钮 `LAUNCH_TIMEOUT_S`（起笔装配超时）；
    #     · `tools/verify_start_point.py` —— A6d 改成"认得出
    #       `to_thread(assemble, …)` 这种递参形状"（只放宽形状，不放宽要求）；
    #     · `tools/run_all_verifications.py` —— 新判据登记进回归器。
    # ⚠ `tools/verify_start_guard.py` / `developers/mutate_start_guard.py` 是**新建**的，
    #   没有 `.bak-bilingual`，C2/C3 本来就不会比它们 —— 不必登记。
    # [EN] ── 2026-10-12 (the launch guard for start-writing: double click / timeout / keep only one) ──
    # [EN] The user reported: "I clicked start-writing twice in a row and two simulations ended up running
    # [EN] at the same time" + "after clicking start-writing nothing happened for a while" + "introduce a
    # [EN] timeout mechanism ... keep only one of the two".
    # [EN] This round **deliberately changed** the following (each reason is in its own comment):
    # [EN] · `gui/app_flet.py` -- the launch guard (`_launch_arm` / `_launch_watch` / `_launch_cancel` /
    # [EN] `_launch_release` / `_launch_discard_run`), switching to the run screen on click, assembly moved
    # [EN] into `asyncio.to_thread`, **the DB created on the main thread**, two token checks, the one in
    # [EN] `_begin_run`, the two status-line conventions, greying out buttons;
    # [EN] · `sim/setup.py` -- `assemble(..., db=None)`: lets the caller hand in a connection **created on
    # [EN] the main thread** (a SQLite connection may not cross threads);
    # [EN] · `config.py` -- the new knob `LAUNCH_TIMEOUT_S` (start-writing assembly timeout);
    # [EN] · `tools/verify_start_point.py` -- A6d now recognises the
    # [EN] `to_thread(assemble, ...)` argument-passing shape (shape relaxed, requirement not);
    # [EN] · `tools/run_all_verifications.py` -- the new criterion registered with the regression runner.
    # [EN] ⚠ `tools/verify_start_guard.py` / `developers/mutate_start_guard.py` are **new** and have no
    # [EN] `.bak-bilingual`, so C2/C3 never compare them -- no need to register.
    "sim/setup.py",
    "tools/verify_start_point.py",
    "tools/run_all_verifications.py",
    # ══════════════════════════════════════════════════════════════
    #  2026-10-12（第二轮）：空间常识与地图能力
    # [EN] 2026-10-12 (second round): spatial common sense and map ability
    # ══════════════════════════════════════════════════════════════
    #  用户「小地图如果是室内地图 就用一个框把相关内容括起来 作为这个建筑的名字」
    #  「请严格区分室内室外……井肯定是要在院子里的」「如果有井 则说明有院子」
    #  「优化小说作家 剧作家 编剧室 导演 美术和道具的能力」
    #  「导演和剧作家在设计人物动作的时候 要时时刻刻参考地图作为人物移动的依据」。
    #  这一轮**故意改了**下面这些（每条理由都写在各自的注释里）：
    #   · `world/spatial.py`（新）—— 空间常识本体：分类 / 审计 / 修（有井补院）/
    #     走法（`route`）；
    #   · `image_gen/map_layout.py` —— `Layout.kind/frame`（室内层要"框住 + 标题"）、
    #     `apply_space_rules()`（**唯一实现**）、`day_layout` 过一遍空间规则、
    #     `Place.label()` 取 `·` 后半截；
    #   · `image_gen/minimap.py` —— 室内图**画框 + 建筑名写在框上 + 门在框上 +
    #     院里的东西垫浅底**，整座楼不再画成一个点；
    #   · `world/atlas.py` —— `apply_space_rules` 改成转发（实现只有一份）；
    #   · `ingest/atlas.py` —— 底图落库前过一遍空间常识、给三层打 `kind` 标记；
    #   · `crew/agents.py` —— 新货架「场景与空间」+ 七个职位的货架/点名/额度、
    #     剧作家（`场`＝地点·空间、走位、平面）、美术（两个分支都要求里外分清）、
    #     道具（落得住地方 + `属于` 标注）、小说作家（场景卡里外分开）、
    #     `_atlas_block` 带 `[室内空间]`/`[室外器物]` 标 + 空间事实段；
    #   · `agent/core.py` —— `_stage_line` 补「地图事实」那一行（`_map_line`）；
    #   · `director/stage.py` —— `StagePlan.previous`（算"从上一场怎么走过来"）；
    #   · `sim/loop.py` —— 把当天的图挂到 `world.day_map`；
    #   · `world/state.py` —— `World.day_map` 字段；
    #   · `gui/app_flet.py` —— 小地图调色板补 `frame`（框的颜色有着落）。
    #  ⚠ `tools/verify_space_rules.py` / `developers/mutate_space_rules.py` 是**新建**的，
    #    没有 `.bak-bilingual`，C2/C3 不比较它们 —— 不用登记。
    # [EN] The user's items: "if the minimap is an indoor map, use a frame to enclose the relevant
    # [EN] content as this building's name", "strictly distinguish indoors and outdoors ... a well
    # [EN] definitely belongs in the courtyard", "if there is a well, that means there is a courtyard",
    # [EN] "optimise the abilities of the novelist / playwright / writers' room / director / art /
    # [EN] props", "the director and playwright must constantly consult the map as the basis for
    # [EN] character movement".
    # [EN] This round **deliberately changed** the following (each reason is in its own comment):
    # [EN] · `world/spatial.py` (new) -- spatial common sense itself: classification / audit / repair
    # [EN]   (a well adds a courtyard) / routing (`route`);
    # [EN] · `image_gen/map_layout.py` -- `Layout.kind/frame`, `apply_space_rules()` (**the only
    # [EN]   implementation**), `day_layout` running the spatial rules, `Place.label()` taking the part
    # [EN]   after `·`;
    # [EN] · `image_gen/minimap.py` -- an indoor map gets **a frame + the building name on the frame +
    # [EN]   the gate on the frame + a wash behind outdoor things**, and the whole building is no longer
    # [EN]   drawn as a point;
    # [EN] · `world/atlas.py` -- `apply_space_rules` became a forwarder (exactly one implementation);
    # [EN] · `ingest/atlas.py` -- spatial common sense before storing the base map, and `kind` tags on
    # [EN]   the three layers;
    # [EN] · `crew/agents.py` -- the new shelf "scene and space" + shelves/entries/quota for seven
    # [EN]   positions, the playwright (`场` = place·space, blocking, floor plan), art (both branches
    # [EN]   require inside/outside), props (must have a place to sit + an `属于` tag), the novelist
    # [EN]   (scene card splits inside/outside), `_atlas_block` carrying `[indoor space]` /
    # [EN]   `[outdoor object]` tags + a spatial-facts passage;
    # [EN] · `agent/core.py` -- `_stage_line` gained the "map facts" line (`_map_line`);
    # [EN] · `director/stage.py` -- `StagePlan.previous` (to compute "how to walk from the previous
    # [EN]   scene");
    # [EN] · `sim/loop.py` -- hang the day's map on `world.day_map`;
    # [EN] · `world/state.py` -- the `World.day_map` field;
    # [EN] · `gui/app_flet.py` -- the minimap palette gained `frame`.
    # [EN] ⚠ `tools/verify_space_rules.py` / `developers/mutate_space_rules.py` are **new** and have no
    # [EN] `.bak-bilingual`, so C2/C3 never compare them -- no need to register.
    "world/spatial.py",
    "image_gen/map_layout.py",
    "image_gen/minimap.py",
    "world/atlas.py",
    "ingest/atlas.py",
    "crew/agents.py",
    "agent/core.py",
    "director/stage.py",
    "sim/loop.py",
    "world/state.py",
    "gui/app_flet.py",
    # ══════════════════════════════════════════════════════════════
    #  2026-10-12（第三轮）：Token 预算实时更新 + 去掉「导演 · 未启动」那一行
    # [EN] 2026-10-12 (third round): live Token budget + removing the "Director · not started" row
    # ══════════════════════════════════════════════════════════════
    #  用户原话：「左下角的系统的Token预算左侧的数字要实时更新 然后导演这一样
    #  可以先去掉 没有特别的意义」。这一轮**故意改了**下面这些（理由写在各自注释里）：
    #   · `gui/app_flet.py` —— 「系统」面板那一行不再硬编码 `0 / 上限`，
    #     改读进程内账本（与"预算耗尽"判定同源）、挂上 0.5 秒的秒表、
    #     新增 `_budget_used` / `_budget_line` / `_budget_color` / `_refresh_sys_panel`；
    #     并去掉「导演 · 未启动」那一行；
    #   · `i18n.py` —— 删掉「导演 · 未启动」的词条（代码里再没有 `t()` 用它）；
    #   · `tools/verify_main_flags.py` —— 四个场景里对「导演 · 未启动」的断言跟着改
    #     （开着时不许出现那行 / 关掉时的「已关闭：导演」照旧）；
    #   · `tools/verify_scene_beat.py` —— A9 的替身补绑 `_map_line`（上一轮 `_stage_line`
    #     新增了这一步，替身少绑一个方法 ⇒ 整块返回空串 ⇒ A9 假红）；
    #   · `tools/verify_day_start.py` —— C3 改成**按分支判**（"没在跑"那一支先说再退），
    #     并新增 C3b 钉住"取消启动"那一支也得说话（原来按"第一个 return"判，
    #     被上一轮新加的合法分支挤掉了）。
    #  ⚠ `tools/verify_budget_live.py` / `developers/mutate_budget_live.py` 是**新建**的，
    #    没有 `.bak-bilingual`，C2/C3 不比较它们 —— 不用登记。
    # [EN] The user's words: "the number to the left of Token budget in the bottom-left system panel
    # [EN] must update in real time; and the director one can go for now, it has no particular meaning".
    # [EN] This round **deliberately changed** the following (reasons in their own comments):
    # [EN] · `gui/app_flet.py` -- that row in the "System" panel is no longer a hardcoded `0 / cap`; it
    # [EN]   reads the in-process ledger (same source as the "budget exhausted" decision), rides the
    # [EN]   0.5-second stopwatch, and gains `_budget_used` / `_budget_line` / `_budget_color` /
    # [EN]   `_refresh_sys_panel`; the "导演 · 未启动" row is removed;
    # [EN] · `i18n.py` -- dropped the "导演 · 未启动" entry (no `t()` uses it any more);
    # [EN] · `tools/verify_main_flags.py` -- the assertions about "导演 · 未启动" in all four scenarios
    # [EN]   changed accordingly (the row must not appear while the director is on; the "已关闭：导演"
    # [EN]   while it is off stays as it was);
    # [EN] · `tools/verify_scene_beat.py` -- A9's stand-in now binds `_map_line` too (the previous round
    # [EN]   added that step to `_stage_line`; the stand-in was one method short ⇒ the whole block
    # [EN]   returned an empty string ⇒ A9 went falsely red);
    # [EN] · `tools/verify_day_start.py` -- C3 now checks **per branch** (the "not running" branch must
    # [EN]   speak before returning), plus a new C3b pinning that the "cancel launch" branch speaks too
    # [EN]   (it used to judge by "the first return", which the previous round's legitimate new branch
    # [EN]   pushed aside).
    # [EN] ⚠ `tools/verify_budget_live.py` / `developers/mutate_budget_live.py` are **new** and have no
    # [EN] `.bak-bilingual`, so C2/C3 never compare them -- no need to register.
    "tools/verify_scene_beat.py",
    "tools/verify_day_start.py",
    # ── 2026-10-12（第三轮 · 尾）：地图分档/画墙/大地图/本地复用 ──
    #   `tools/verify_ui_english.py` —— 这一轮给它加了一条**窄口径的路径放行**：
    #   `设定集/小世界地图.yaml` 是**盘上真有的那个文件名**（`world/atlas.py`
    #   的 `FILE`），小地图那行说明里指的就是它，英文界面下不该把它改写成别的
    #   （同"运行文件夹名""自动落盘/进度.md""剧本审读.md"那几条的先例）。
    #   所以它的 AST 与 `.bak-bilingual` 必然不同 —— 那不是"双语化工具改坏了代码"。
    # [EN] ── 2026-10-12 (third round, tail): map tiering / walls / big map / local reuse ──
    # [EN] `tools/verify_ui_english.py` -- this round gave it a **narrow path allowance**:
    # [EN] `设定集/小世界地图.yaml` is **the filename that really exists on disk** (`world/atlas.py`'s
    # [EN] `FILE`), and the explanatory line under the minimap refers to exactly it; rewriting it under
    # [EN] an English UI would be wrong (the same precedent as "run folder name",
    # [EN] "自动落盘/进度.md" and "剧本审读.md").
    # [EN] So its AST necessarily differs from `.bak-bilingual` -- that is not "the bilingualization
    # [EN] tool broke the code".
    "tools/verify_ui_english.py",
    # ── 2026-10-12（第五轮 · 台词要像活人说的）──
    #   这一轮**故意改了这几个文件的代码**（理由逐条写在各自的注释里）：
    #     · `style/deai.py` —— 软提示多了一类「喊叫滥用」（音量词）；
    #     · `crew/cognition.py` —— 演员的思维链多一步（"该用什么声音说"，
    #       排在**最后** = 开口前最后一个念头）、审读的思维链多一步（"有活人的样子吗"）、
    #       顺带把"判五件事"的注释改成六件；
    #     · `tools/verify_cognition.py` —— A6 从"演员骨架正好四条"改成
    #       "四条老的**一条不少** + 音量那条排在**最后**"（骨架加了一条，旧断言会假红）。
    #   ⚠ 新写的 `tools/verify_live_speech.py` / `developers/mutate_live_speech.py`
    #     没有 `.bak-bilingual`，C2/C3 根本不比它们 —— 不用登记。
    # [EN] ⚠ The newly written files have no `.bak-bilingual`, so C2/C3 never compare them.
    # [EN] ── 2026-10-12 (fifth round, tail): dialogue must sound like a live person says it ──
    # [EN] This round **deliberately changed the code of these files** (reasons in their own comments):
    # [EN] · `style/deai.py` -- the soft hints gain a "shouting abuse" category (volume words);
    # [EN] · `crew/cognition.py` -- the actor's thinking chain gains one step ("what voice to use",
    # [EN]   placed **last** = the last thought before speaking), the review's chain gains one step
    # [EN]   ("does this look like live people"), and the "judges five things" comment becomes six;
    # [EN] · `tools/verify_cognition.py` -- A6 changes from "the actor's skeleton is exactly four" to
    # [EN]   "the four old ones are **all still there** + the volume one comes **last**" (the skeleton
    # [EN]   gained one entry, so the old assertion would go falsely red).
    # [EN] ⚠ The newly written `tools/verify_live_speech.py` / `developers/mutate_live_speech.py` have no
    # [EN] `.bak-bilingual`, so C2/C3 never compare them -- no need to register.
    "style/deai.py",
    "crew/cognition.py",
    "tools/verify_cognition.py",
    # ── 2026-10-12（第六轮 · 尾）：小地图**地点不再用点标记** ──
    #   用户第三次报红点：「小地图里标记〔那座楼〕和**旁边的红点**还是存在 去掉它
    #   **如果想要标记地点 用小字标记就行了 不要用点**」。这一轮**故意改了**：
    #     · `tools/verify_minimap.py` —— A7b/A7c 换成 A7b/A7c/A7d（钉"图上没有实心圆"
    #       与"当前地点靠**字色**区分"）；B3 的像素下限跟着新画法从 800 调到 300
    #       并补了"标签数 ≥ 地点数"；B5b 从"形状总数变了"（**弱判据**，去掉字形后
    #       前后相等就假红）改成"**实心圆数 == 在场人数**"；随手删掉不再需要的 `before`。
    #     · `developers/mutate_minimap.py` —— 加 `_lines_around()`（对付"同一句逐字
    #       重复两遍"的锚点）、修 3 条已失效/不唯一的锚点、加 2 条针对新行为的变异。
    # [EN] ── 2026-10-12 (sixth round, tail): locations on the minimap are **no longer marked with
    # [EN] dots** ──
    # [EN] The user's third red-dot report: "the label for [that building] and **the red dot next to
    # [EN] it** are still there; remove it. **If you want to mark a location, just mark it with small
    # [EN] text -- do not use dots**." This round **deliberately changed**:
    # [EN] · `tools/verify_minimap.py` -- A7b/A7c became A7b/A7c/A7d (pinning "no filled circles on the
    # [EN]   map" and "the current location is distinguished by **text colour**"); B3's pixel floor
    # [EN]   follows the new drawing style (800 -> 300) and gained "label count >= location count";
    # [EN]   B5b changed from "the total shape count changed" (a **weak criterion** that goes falsely
    # [EN]   red once the glyphs are gone and the totals match) to "**filled circles == people
    # [EN]   present**"; the now-unneeded `before` was dropped.
    # [EN] · `developers/mutate_minimap.py` -- added `_lines_around()` (for anchors where the same
    # [EN]   sentence is repeated verbatim twice), fixed 3 dead/non-unique anchors, and added 2
    # [EN]   mutations for the new behaviour.
    "tools/verify_minimap.py",
    "developers/mutate_minimap.py",
    # ── 2026-10-12（第七轮 · 尾）：大地图的几何 + 美术的 Reflection 环 ──
    #   这一轮**故意改了**这些判据与产品文件（理由都写在各处注释里），
    #   所以 C2/C3 的指纹与 `.bak-bilingual` 必然不同 ——
    #   那不是"双语化工具改坏了代码"：
    #     · `tools/verify_space_rules.py` —— D3 改口径（建筑名从"框外面"改到"框内上沿"，
    #       用户要求"名字放到墙的旁边"）；
    #     · `tools/verify_map_detail.py` —— D3 改成"不再圈方框、但仍然占位"、
    #       D6 改成"图上不再叠关闭按钮"（都是用户第二轮/第四轮的新要求）；
    #     · `tools/verify_ui_english.py` —— 图例文案变了（不再有方框那一句）；
    #     · `image_gen/floorplan.py` / `image_gen/minimap.py` —— 几何与标签的改动。
    # [EN] ── 2026-10-12 (seventh round, tail): the big map's geometry + the art dept's Reflection loop ──
    # [EN] This round **deliberately changed** these criteria and product files (reasons in their own
    # [EN] comments), so the C2/C3 fingerprints necessarily differ from `.bak-bilingual` -- that is not
    # [EN] "the bilingualization tool broke the code":
    # [EN] · `tools/verify_space_rules.py` -- D3 changed convention (the building name went from
    # [EN]   "outside the frame" to "the inside of the frame's top edge", as the user asked: "put the
    # [EN]   name labels beside the wall");
    # [EN] · `tools/verify_map_detail.py` -- D3 became "no box any more, but still reserves space" and
    # [EN]   D6 became "the close button is no longer overlaid" (both new requests from the user's
    # [EN]   second and fourth rounds);
    # [EN] · `tools/verify_ui_english.py` -- the legend wording changed (no more box sentence);
    # [EN] · `image_gen/floorplan.py` / `image_gen/minimap.py` -- geometry and label changes.
    # [EN] ⚠ The newly written `tools/verify_plan_geometry.py` / `developers/mutate_plan_geometry.py` /
    # [EN]   `developers/probe_floorplan_geometry.py` / `image_gen/plan_audit.py` have no
    # [EN]   `.bak-bilingual`, so C2/C3 never compare them -- no need to register.
    "tools/verify_space_rules.py",
    "tools/verify_map_detail.py",

    # ── 2026-10-12 傍晚（多模型 + 每个 Agent 指定模型 + 推荐表）──
    #   用户原话：「只用一种模型不足以较好完成任务，Deepseek小说能力不足」→
    #   把天问的两个 LLM 页合并成"可配多个模型"的一页、每个 Agent 加模型选项、
    #   novelservices 作为特殊 Agent 纳入管理。这一轮**故意改了**这些产品代码与判据
    #   （理由逐条写在各自那段注释里），指纹/docstring 数必然与 `.bak-bilingual`
    #   不同 —— 那不是"双语化工具改坏了代码"：
    #     · `llm/models.py` / `llm/recommend.py` —— **新建**（登记表 / 推荐表）；
    #     · `llm/router.py` —— 地址与密钥改成**逐发**按解析结果传（多服务商）；
    #     · `crew/roster.py` / `crew/catalog.py` —— `kind` + `model` 字段 + 5 个新条目；
    #     · `crew/studio.py` 与 6 个模块 —— 出工/服务时用 `MODELS.use()` 切模型；
    #     · `gui/app_flet.py` —— 合并后的「AI模型配置」页 + Agents 的「模型」组；
    #     · `i18n.py` / `config.py` —— 新文案与 `LLM_DEFAULT_MODEL`；
    #     · `tools/verify_llm_models.py` —— **新建**判据；其余几支判据跟着页签合并改。
    # [EN] -- 2026-10-12 evening (several models + per-Agent model + recommendation table) --
    # [EN] These product files and criteria were **deliberately changed**, so fingerprints and
    # [EN] docstring counts necessarily differ from `.bak-bilingual` -- that is not "the
    # [EN] bilingualization tool broke the code".
    "config.py",
    "llm/router.py",
    "crew/roster.py",
    "crew/catalog.py",
    "crew/studio.py",
    "crew/agents.py",
    "agent/core.py",
    "sim/backstage.py",
    "sim/loop.py",
    "sim/opening.py",
    "director/engine.py",
    "compliance/agent.py",
    "ingest/pipeline.py",
    "ingest/repair.py",
    "ingest/optimize.py",
    "gui/app_flet.py",
    "i18n.py",
    "tools/verify_regular_tab.py",
    "tools/verify_agent_catalog.py",
    "tools/verify_tabs_fit.py",
    "tools/verify_mumu_service.py",
    "tools/verify_llm_caps.py",
    "tools/verify_llm_first_run.py",
    "tools/verify_ui_english.py",
    "tools/run_all_verifications.py",


    # ── 2026-10-12 夜（多模型费用统计 / 缓存命中 / 同题复用 / 降费）──
    #   用户原话：「现在用AI的地方越来越多 话费太快 …… 如果多模型 则 LLM用量需要
    #   统计不同模型的费用 第二 你去学一下 看有什么办法优化AI Llm使用 尽量降低费用」。
    #   这一轮**故意改了**这些产品代码（理由写在各自那段注释里），指纹与 docstring
    #   数必然与 `.bak-bilingual` 不同 —— 那不是"双语化工具改坏了代码"：
    #     · `llm/tokens.py` —— 价格表改三段式（命中/未命中/输出）+ 覆盖主要模型 + 峰谷，
    #       行内中文注释一并改成英文（行内中文会各自成块，块尾接不上 `# [EN]`）；
    #     · `llm/models.py` / `llm/usage.py` —— 登记表加单价字段 / 台账加 `cache_tok` 列
    #       与补列迁移、WAL；
    #     · `llm/router.py` —— 读缓存命中字段、按模型解析单价、接同题复用；
    #     · `gui/app_flet.py` / `gui/usage_dialog.py` —— 单价输入、省钱四招块、缓存列；
    #     · `config.py` / `i18n.py` —— 新配置项与文案；
    #     · 两支判据跟着改口径（`verify_progress_eval` 的假客户端要收 `headers`、
    #       回归器登记新判据）。
    # [EN] -- 2026-10-12 evening (multi-model cost accounting / cache hits / same-question
    # [EN] reuse / cost reduction) --
    # [EN] These product files were **deliberately changed** this round, so fingerprints and
    # [EN] docstring counts necessarily differ from `.bak-bilingual` -- that is not "the
    # [EN] bilingualization tool broke the code".
    "llm/tokens.py",
    "llm/models.py",
    "llm/usage.py",
    "llm/router.py",
    "config.py",
    "gui/app_flet.py",
    "gui/usage_dialog.py",
    "i18n.py",
    "tools/run_all_verifications.py",
    "tools/verify_progress_eval.py",
    #   ⚠ `verify_empty_body_retry` 的假 `_real_call` 补了 `res` / `caps` 两个形参
    #     （`_real_call` 现在会传它们）—— 不改就是 `TypeError`，整支判据崩。
    # [EN]   ⚠ The fake `_real_call` in `verify_empty_body_retry` gained `res` / `caps`
    # [EN]   (the real one now passes them); without it a `TypeError` takes down the whole
    # [EN]   criterion.
    "tools/verify_empty_body_retry.py",
    # ── 2026-10-12 夜（天机界面重构：放大 / Table / 拆 Tab / 左对齐）──
    #   用户逐条点名的一轮界面改动。改动都写在各自那段注释里，指纹与
    #   docstring 数必然与 `.bak-bilingual` 不同 —— 那不是"双语化工具改坏了代码"：
    #     · `gui/app_flet.py` —— 栅格宽度改成运行时（`grid_width()`）、帮助与天机
    #       按窗口放大、模型列表与推荐表改 DataTable、省钱块只留标题、
    #       「通用参数」拆到各模型、MuMuAINovel 拆成独立页签、能力区左对齐；
    #     · `llm/models.py` —— 模型条目加 `timeout`/`retries` + 三档解释文案；
    #     · `llm/router.py` —— 超时/重试改成优先取每一条模型自己的；
    #     · `i18n.py` —— 新文案；
    #     · 几支判据跟着改口径（页签 6→7、下标整体 +1、字体判据改用常量、
    #       mumu 判据改成"独立成页"、成本判据加 G 段）。
    # [EN] -- 2026-10-12 evening (Tianji UI rework: enlarge / Table / split Tab / left align) --
    # [EN] The changes are documented in their own comment blocks; fingerprints and docstring
    # [EN] counts necessarily differ from `.bak-bilingual` -- that is not "the bilingualization
    # [EN] tool broke the code".
    "gui/app_flet.py",
    "llm/models.py",
    "llm/router.py",
    "i18n.py",
    "tools/verify_tabs_fit.py",
    "tools/verify_regular_tab.py",
    "tools/verify_mumu_service.py",
    "tools/verify_font_settings.py",
    "tools/verify_ingest_rounds.py",
    "tools/verify_cost_model.py",
    # ── 2026-10-13（天机界面优化：页签改名）──
    #   ⚠ 这一条**只因 docstring 被改**：「模型与LLM」改名「AI模型配置」时，
    #     `tools/verify_llm_models.py` 的**模块 docstring 正文**（D 段那一行）
    #     里的旧页名也被一起换掉了 —— 那是**正文中间**，不是追加，
    #     于是 C3（"docstring 只被追加、没被改写"）当场红。
    #     其它几个判据脚本同样改了名，但它们改的都在**代码里的字符串**，
    #     docstring 没动 ⇒ 不在这一份名单里也不需要。
    # [EN] ── 2026-10-13 (Tianji UI polish: tab renamed) ──
    # [EN] ⚠ This one is here **only because its docstring changed**: when "Models & LLM" was renamed
    # [EN] to "AI Model Config", the old page name inside `tools/verify_llm_models.py`'s **module
    # [EN] docstring body** (the line in section D) was replaced too -- that is the **middle** of the
    # [EN] body, not an append, so C3 ("docstrings are only appended to, never rewritten") went red on
    # [EN] the spot. The other criterion scripts were renamed as well, but their changes are in
    # [EN] **string literals in the code** with the docstring untouched => they neither belong in this
    # [EN] list nor need to.
    "tools/verify_llm_models.py",
    # ── 2026-10-13（Logo 定稿：图标管线吃简化剪影，开始界面单独用带流线版）──
    #   这一轮**故意改了这两个文件的代码/注释**，C2/C3 指纹与备份必然不同：
    #     · `image_gen/icon.py` —— 源图模式时代的合法手改（docstring 增补）+
    #       本轮把两处 `#: [EN]` 前缀改成判据认的 `# [EN] `（B2 口径：
    #       EN_MARK = "# [EN] "，`#:` 开头不算译文）；
    #     · `tools/verify_icon.py` —— 判据同步新 Logo：源图模式对比下限单独
    #       定 2.5:1（实测 2.88，程序绘制维持 3:1）、新增 start_logo 两条
    #       （存在且 != 图标产物 / show_start 接线优先 start_logo）。
    # [EN] ── 2026-10-13 (logo finalized: icon pipeline takes the simplified silhouette, the start
    # [EN] screen uses the streamline version separately) ──
    # [EN] This round **deliberately changed the code/comments of these two files**, so C2/C3
    # [EN] fingerprints necessarily differ from the backups:
    # [EN] · `image_gen/icon.py` -- legitimate manual edits from the source-mode era (docstring
    # [EN] additions) + this round changed two `#: [EN]` prefixes into the checker-recognized
    # [EN] `# [EN] ` (B2 convention: EN_MARK = "# [EN] "; a `#:` prefix doesn't count as a translation);
    # [EN] · `tools/verify_icon.py` -- criteria synced to the new logo: source mode got its own
    # [EN] contrast floor of 2.5:1 (measured 2.88; programmatic mode keeps 3:1), plus two new
    # [EN] start_logo checks (exists and != icon artifact / show_start wiring prefers start_logo).
    "image_gen/icon.py",
    "tools/verify_icon.py",
    # ★ 2026-10-13（背景图：婴宁印章 + 开始界面轻模糊）──
    #   这一轮改了 `image_gen/background.py`（build_from_source 加 `_add_name_seal` + 开始界面轻模糊）
    #   与 `tools/verify_background.py`（新增 check_seal 守印章），都属预期改动，指纹/文档数自然不同。
    # [EN] ★ 2026-10-13 (background: 婴宁 seal + lighter start-screen blur) ──
    # [EN] This round changed `image_gen/background.py` (build_from_source gained `_add_name_seal` + a
    # [EN] lighter start-screen blur) and `tools/verify_background.py` (new check_seal guards the seal);
    # [EN] both are expected changes, so fingerprints / doc counts naturally differ.
    "image_gen/background.py",
    "tools/verify_background.py",
    # ── 2026-10-13（本会话尾）：背景去模糊重生成 + 运行时 BG_DIM 滤镜 ──
    #   这一轮把"模糊"从图片里拿掉（重生成高清母版/柔化版，不再烤高斯模糊，
    #   印章保留），并改天机·外观加一个**运行时**纸色滤镜（`BG_DIM`，只管开始/运行
    #   界面、不碰对话框）；另建/改三支配对的反例法脚本。下面这些文件要么是
    #   产品代码的预期改动、要么是**新建的反例法脚本**（没有 `.bak-bilingual`，
    #   C2/C3 本来就不比它们），登记以防下一轮双语化之后再手改时 C2 误报：
    #     · `developers/mutate_background_seal.py` —— 改了变异锚点（`build_from_source`
    #       重构后 `_add_name_seal` 只在两行赋值，原 `pass` 变异会让变量未定义）；
    #     · `developers/mutate_background_blur.py` —— **新建**：锚定"不再烤模糊"，
    #       变异体把母版/柔化版烤回高斯模糊来证伪；
    #     · `developers/mutate_bg_filter.py` —— **新建**：锚定运行时滤镜
    #       `opacity=bg_dim())`，变异体 `opacity=0.0` 证伪。
    # [EN] ── 2026-10-13 (end of session): background de-blur regen + runtime BG_DIM filter ──
    # [EN] This round removed blur from the image (regenerated the master/soft versions in high
    # [EN] res, no baked Gaussian blur, seal kept) and added a **runtime** paper-colour filter to
    # [EN] Tianji's appearance (`BG_DIM`, only the start/run screens, not dialogs); plus created/
    # [EN] changed three paired reverse-experiment scripts. The files below are either expected
    # [EN] product-code changes or **new** counterexample scripts (with no `.bak-bilingual`, so C2/
    # [EN] C3 never compare them); register them so a later manual edit after bilingualization
    # [EN] doesn't trip C2 by mistake:
    # [EN] · `developers/mutate_background_seal.py` -- changed the mutation anchor (after the
    # [EN]   `build_from_source` refactor, `_add_name_seal` is assigned on only two lines; the old
    # [EN]   `pass` mutation would leave the variable undefined);
    # [EN] · `developers/mutate_background_blur.py` -- **new**: pins "no baked blur", the mutation
    # [EN]   bakes Gaussian blur back to disprove it;
    # [EN] · `developers/mutate_bg_filter.py` -- **new**: pins the runtime filter `opacity=bg_dim())`,
    # [EN]   the mutation `opacity=0.0` disproves it.
    "developers/mutate_background_seal.py",
    "developers/mutate_background_blur.py",
    "developers/mutate_bg_filter.py",
    # ★ 顺带补登三个**更早的轮次漏登记**的手改（均非本回合改动，已逐个 diff
    #   确认是「人改的合法改动」而非「双语化工具改坏代码」）：
    #     · `tools/verify_help_scrollbar.py` —— D2 判据重写：条的可见性改按
    #       **当前数字现算**（`_avail_now`/`_content_now`/`_want_bar`），不再一次定死；
    #     · `tools/verify_help_search.py` —— TOC 宽度查找改读对话框上的
    #       `_recap_toc_w`（回落 `HELP_TOC_W`）；
    #     · `tools/verify_usage_layout.py` —— 多了一句 `DBG` 打印（排查"点击后协程
    #       CancelledError"这件已知未决问题留下的，保留作调试用）。
    # [EN] ★ Also registering three **missed** manual edits from earlier rounds (none from this
    # [EN] round; each diffed to confirm it is a legitimate human edit, not bilingualization-tool
    # [EN] corruption):
    # [EN] · `tools/verify_help_scrollbar.py` -- D2 criterion rewritten: the bar's visibility is now
    # [EN]   computed from **current numbers** (`_avail_now`/`_content_now`/`_want_bar`), no longer
    # [EN]   fixed once;
    # [EN] · `tools/verify_help_search.py` -- the TOC width lookup now reads `_recap_toc_w` off the
    # [EN]   dialog (falling back to `HELP_TOC_W`);
    # [EN] · `tools/verify_usage_layout.py` -- an extra `DBG` print (left over while tracing the known
    # [EN]   "CancelledError after click" issue; kept as a debugging aid).
    "tools/verify_help_scrollbar.py",
    "tools/verify_help_search.py",
    "tools/verify_usage_layout.py",
    #  ★ 2026-10-14 补登记三处**早先轮次漏登**的合法手工改动（逐条 diff 核过，
    #    都不是双语化工具写坏的）：
    #    · `developers/check_release.py` / `tools/verify_release_platforms.py` ——
    #      发版时把版本号从 `0.2.0` 改成 `0.3.0`（含注释里的示例路径与
    #      `ver == '0.3.0'` 那处判断）。**发版必然要动**，但没人登记过。
    #    · `llm/capabilities.py` —— docstring 末尾多了一段英文说明（早期
    #      双语化留下的 `English:` 段落，不是 `# [EN]` 那种规范形态）。
    #      ⚠ 它同时挂在 **C3**（docstring 只许追加、不许改写）名下，也是
    #      **既有**问题，不是本轮引入。
    # [EN] ★ 2026-10-14 registering three **earlier-round, unregistered** legitimate manual edits
    # [EN] (each diffed to confirm it is a legitimate human edit, not bilingualization-tool
    # [EN] corruption):
    # [EN] · `developers/check_release.py` / `tools/verify_release_platforms.py` -- the release
    # [EN]   bumped the version from `0.2.0` to `0.3.0` (including the example path in a comment
    # [EN]   and the `ver == '0.3.0'` check). **Releasing always touches this**, yet nobody
    # [EN]   registered it.
    # [EN] · `llm/capabilities.py` -- the docstring gained an English paragraph at the end (the
    # [EN]   early bilingualization `English:` style, not the canonical `# [EN]` form).
    # [EN]   ⚠ It also sits under **C3** ("docstrings may only be appended, not rewritten"), which
    # [EN]   is likewise **pre-existing**, not introduced this round.
    "developers/check_release.py",
    "tools/verify_release_platforms.py",
    "llm/capabilities.py",
    # ── 2026-10-14（三批改动，逐条给理由）──
    #  ⚠ 这一天改的文件里，产品代码只动了**几行错名字**与**一处恢复**，
    #    但 C2 的尺子是"A/B 一字未变"，所以凡动过的都要登记。
    #  · `research/manual_qa.py` —— 检索加**第三道闸门**（标题至少要命中一个
    #    查询词）：用户问「今天天气怎么样」也被端出三节《主界面详解》，
    #    根因是二连切词把「今天天气」切出「今天/天气」，正文里刚好都有。
    #    （`tools/verify_help_qa.py` 的 A3/A7 钉着；33/35 → 35/35。）
    #  · `tools/verify_booklab.py` / `tools/verify_booklab_sources.py` —— 上一轮
    #    「开始拆搬到底部动作栏」改的（新增 G10/H3b/H3c 三条位置判据；
    #    sources 那两处切片**终点**跟着搬：原来锚在那行 `out.append(...)` 上，
    #    而它被删掉了）。**上一轮漏登记，这一轮补上。**
    # [EN] ── 2026-10-14 (three batches, one reason each) ──
    # [EN] ⚠ Of the files changed that day, the product code only touched **a few wrong names**
    # [EN] and **one restoration**, but C2's ruler is "A/B identical byte for byte", so anything
    # [EN] touched must be registered.
    # [EN] · `research/manual_qa.py` -- retrieval gained a **third gate** (the title must hit at
    # [EN]   least one query term): asking "今天天气怎么样" (what's the weather) still served up
    # [EN]   three sections of "Main Interface Explained", because bigram tokenization splits
    # [EN]   「今天天气」 into 「今天/天气」 and the body happens to contain both.
    # [EN]   (Pinned by A3/A7 of `tools/verify_help_qa.py`; 33/35 -> 35/35.)
    # [EN] · `tools/verify_booklab.py` / `tools/verify_booklab_sources.py` -- changed in the
    # [EN]   previous round ("move Start to the bottom action bar": added the three position
    # [EN]   criteria G10/H3b/H3c; the two slice **end** anchors in sources moved along, because
    # [EN]   they anchored on that `out.append(...)` line, which was deleted). **Missed last
    # [EN]   round, registered now.**
    "research/manual_qa.py",
    "tools/verify_booklab.py",
    "tools/verify_booklab_sources.py",
    #  · `gui/app_flet.py` —— 2026-10-14 共四处（三处修 + 一处恢复）：
    #    ① `save()` 里的 `field_value(base_url)` / `field_value(api_key)` —— 那两个
    #       名字**整个模块都不存在**（真名 `url_f` / `key_f` 且是 `_model_editor`
    #       的局部）⇒ 第一次配模型时一按保存就 `NameError`；
    #    ② `_make_polish_agent` 的 `on_event` 用了 `_do_import` 的局部闭包 `_now()`
    #       ⇒ 一开打磨就炸（旁边那条注释正在警告这件事，只是这行忘了改）；
    #    ③ `_intro_round` 的降级分支用了不在作用域里的 `add_log`（应为 `_add_log`）
    #       ⇒ "降级要吭声"那句提示自己抛异常；
    #    ④ **画回**被误删的「常见服务速查」（`_model_list_section` 尾部）。
    # [EN] · `gui/app_flet.py` -- four places in all on 2026-10-14 (three fixes + one
    # [EN]   restoration):
    # [EN]   ① `field_value(base_url)` / `field_value(api_key)` in `save()` -- those names
    # [EN]      **do not exist anywhere in the module** (the real ones are `url_f` / `key_f`,
    # [EN]      locals of `_model_editor`) => pressing save the first time you configure a model
    # [EN]      raises `NameError`;
    # [EN]   ② `on_event` in `_make_polish_agent` used `_now()`, a local closure of `_do_import`
    # [EN]      => it blows up the moment polishing starts (the comment right beside it warns about
    # [EN]      this; the line just never got changed);
    # [EN]   ③ the degradation branch in `_intro_round` used `add_log`, which is not in scope
    # [EN]      (should be `_add_log`) => the very hint that says "degradation must speak up"
    # [EN]      raised;
    # [EN]   ④ **drew back** the mistakenly deleted "common services quick reference" (tail of
    # [EN]      `_model_list_section`).
    "gui/app_flet.py",
    #  · `llm/usage.py` —— `detail()` 里 `({_unk()})`：`_unk` 既不在作用域、
    #    又是在**调用一个字符串**（`_unlabeled_sql()` 返回 SQL 片段）⇒
    #    在用量窗口点「未标注」那一档看明细必炸。
    # [EN] · `llm/usage.py` -- `({_unk()})` inside `detail()`: `_unk` is neither in scope nor
    # [EN]   callable (it is a string; `_unlabeled_sql()` returns an SQL fragment) => clicking the
    # [EN]   "unlabeled" bucket in the usage window to view details always raised.
    "llm/usage.py",
    #  · `tools/verify_font.py` / `tools/verify_font_settings.py` —— 把
    #    "UI_FONT == 随附宋体"换成"UI_FONT 是**随附字体之一**"：原来那条读的是
    #    **用户 `.env`**（用户自己把界面字体选成了楷体 `UI_FONT=kai`），
    #    于是判据在**他自己的机器上**永远红。"默认 auto → 宋体"由纯逻辑
    #    A1（`verify_font_settings`）钉住，不依赖 `.env`。
    # [EN] · `tools/verify_font.py` / `tools/verify_font_settings.py` -- swapped
    # [EN]   "UI_FONT == bundled serif" for "UI_FONT is **one of the bundled fonts**": the old
    # [EN]   one read the **user's `.env`** (the user had picked the Kai font, `UI_FONT=kai`), so
    # [EN]   the criterion was forever red **on his own machine**. "default auto -> serif" is
    # [EN]   pinned by the pure-logic A1 in `verify_font_settings`, independent of `.env`.
    "tools/verify_font.py",
    "tools/verify_font_settings.py",
    #  · `tools/verify_style_help.py` —— 收尾那句 `c.content.controls[-1]` 遇到
    #    空 Row 会 `IndexError`，而它抛在**收尾段** ⇒ 「23/23 全绿却 exit=2」
    #    （"判据自己崩了"被当成"判据变红"）。加一句非空判断。
    # [EN] · `tools/verify_style_help.py` -- the wrap-up line `c.content.controls[-1]` raised
    # [EN]   `IndexError` on an empty Row, and it throws in the **wrap-up** section => "23/23 all
    # [EN]   green yet exit=2" ("the criterion crashed" read as "the criterion went red"). Added a
    # [EN]   non-empty check.
    "tools/verify_style_help.py",
    #  · `tools/verify_borrowings.py` —— A6 换靶（原文案已搬进 i18n；只查 i18n 会
    #    **假绿**，所以改成"i18n 有 + 产品真的引用了它"两处都查）。
    # [EN] · `tools/verify_borrowings.py` -- A6 retargeted (the copy moved into i18n; checking
    # [EN]   i18n alone is a **false green**, so it now checks both "i18n has it" and "the product
    # [EN]   really references it").
    "tools/verify_borrowings.py",
    #  · `tools/run_all_verifications.py` —— 新判据 `verify_confirm_dialog` 登记进 GUI 组。
    # [EN] · `tools/run_all_verifications.py` -- the new `verify_confirm_dialog` registered into
    # [EN]   the GUI group.
    "tools/run_all_verifications.py",
    #  · 2026-10-14 下半场（"25 支判据能修就修"那一轮）改的判据与反例法：
    #    `tools/verify_actor_layers.py`（D2g 换锚点：读**所有**对话框、去掉
    #      `content is Row` 的死条件、两种点击形状都点）、
    #    `tools/verify_manual_images.py`（体积改**去重**口径）、
    #    `tools/verify_run_status_bar.py`（停止改**轮询**等收尾）、
    #    `developers/mutate_actor_layers.py`（M15/M18 锚点指向旧结构 ⇒ 换锚）、
    #    `developers/mutate_borrowings.py`（删掉从未定义的 `BAT` + 新补第 ⑭ 条）。
    # [EN] · Changed later on 2026-10-14 (the "fix the 25 criteria" round), criteria and
    # [EN] counterexample harnesses:
    # [EN]   `tools/verify_actor_layers.py` (D2g anchor swap: read **all** dialogs, drop the dead
    # [EN]     `content is Row` condition, click both shapes),
    # [EN]   `tools/verify_manual_images.py` (size switched to a **de-duplicated** caliber),
    # [EN]   `tools/verify_run_status_bar.py` (stop now **polls** for the wrap-up),
    # [EN]   `developers/mutate_actor_layers.py` (M15/M18 anchors pointed at the old structure =>
    # [EN]     re-anchored),
    # [EN]   `developers/mutate_borrowings.py` (removed the never-defined `BAT` + added a ⑭).
    "tools/verify_actor_layers.py",
    "tools/verify_manual_images.py",
    "tools/verify_run_status_bar.py",
    "developers/mutate_actor_layers.py",
    "developers/mutate_borrowings.py",
}


def main() -> int:
    files = _iter()
    try:
        section("A 扫描面（与工具同一份口径）")
        ok("A1 找得到要处理的文件（>300 个）", len(files) > 300, f"{len(files)} 个")
        try:
            from bilingualize_comments import SKIP_PREFIX
            skip_up = [p for p in APP.rglob("*.py")
                       if p.relative_to(APP).as_posix().startswith(SKIP_PREFIX)]
            ok("A2 **上游 MuMuAINovel 的 backend 被排除**（改了会污染它的 git 检出）",
               bool(skip_up) and not any(
                   p.relative_to(APP).as_posix().startswith(SKIP_PREFIX)
                   for p in files),
               f"仓库里有 {len(skip_up)} 个上游文件，扫描面里 0 个")
        except Exception as e:                              # noqa: BLE001
            ok("A2 上游目录被排除", False, str(e)[:90])

        section("B 完整性与干净度")
        tot_cn = tot_en = tot_missing = tot_dirty = 0
        worst: list[tuple[str, int]] = []
        dirty_files: list[str] = []
        for p in files:
            cn, en, miss, dirty = scan_file(p)
            tot_cn += cn
            tot_en += en
            tot_missing += len(miss)
            tot_dirty += len(dirty)
            if miss:
                worst.append((p.relative_to(APP).as_posix(), len(miss)))
            if dirty:
                dirty_files.append(p.relative_to(APP).as_posix())
        worst.sort(key=lambda x: -x[1])
        ok("B1 扫描面的**中文注释行数**统计得出来（>10000 行量级）",
           tot_cn > 5000, f"{tot_cn} 行含中文的注释 · 译了 {tot_en} 个块")
        ok("B2 ★★ **每一个含中文的注释块，块尾都跟着 `# [EN]`**（完成度 100%）",
           tot_missing == 0,
           f"还差 {tot_missing} 块 · 最缺的几个："
           + "、".join(f"{n}({c})" for n, c in worst[:6]))
        ok("B3 ★ `# [EN]` 行**本身不含中文**（不写半吊子译文）",
           tot_dirty == 0, f"{tot_dirty} 行 · 例：{dirty_files[:4]}")
        ok("B4 ★ 是**块级**的（中文行数明显多于已译块数 —— 说明是一整段中文配一整段英文，"
           "不是逐行交错）",
           tot_en > 0 and tot_cn > tot_en,
           f"{tot_cn} 行中文 / {tot_en} 个块")

        section("C 没弄坏代码（这一支最要紧的）")
        bad_parse: list[str] = []
        for p in files:
            try:
                # ⚠ 必须 `utf-8-sig`：`utf-8` 会把 **UTF-8 BOM** 读成一个真的
                #   `\ufeff` 字符塞在源码第一位，`ast.parse` 于是报
                #   "invalid non-printable character U+FEFF" —— 而那个文件
                #   **Python 解释器是能正常导入的**（PEP 263 允许 BOM）。
                #   ⇒ 这曾经让 C1 一直红在 4 个 PlotPilot 文件上，看起来像
                #     "那几份代码坏了"，实际是**判据读文件的方式不对**。
                # [EN] ⚠ Must use `utf-8-sig`: plain `utf-8` turns a **UTF-8 BOM** into a real
                # [EN] `\ufeff` character at offset 0, and `ast.parse` then reports
                # [EN] "invalid non-printable character U+FEFF" — while the file **imports fine**
                # [EN] (PEP 263 allows a BOM). This kept C1 red on four PlotPilot files and looked
                # [EN] like broken code when it was the criterion reading the file wrong.
                ast.parse(p.read_text(encoding="utf-8-sig"))
            except Exception as e:                          # noqa: BLE001
                bad_parse.append(f"{p.relative_to(APP).as_posix()}: {e}")
        ok("C1 全项目 `ast.parse` 通过（450+ 个文件）",
           not bad_parse, "；".join(bad_parse[:4]))

        # ★★ **AST 指纹对照**：把 docstring 的内容抹掉之后，整棵树必须一模一样。
        #    （"代码行逐行比"在这里**不适用** —— 多行 docstring 的中间行
        #     在"行"的视角下看起来就是代码。第一版就是这么误报的。）
        #    `ast.dump` 默认不含行号，所以"插了几行译文"不影响这个比较。
        # [EN] ★★ **AST fingerprint comparison**: after erasing the docstring contents, the entire tree must be
        # [EN] identical.
        # [EN] (Comparing "code lines line by line" does **not** apply here — the middle lines of a multi-line
        # [EN] docstring
        # [EN] look like code from the "line" perspective. The first version had this false positive.)
        # [EN] `ast.dump` does not include line numbers by default, so "inserting a few translation lines" does
        # [EN] not affect this comparison.
        def fingerprint(path: Path) -> str:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                         ast.AsyncFunctionDef)):
                    continue
                b = node.body
                if (b and isinstance(b[0], ast.Expr)
                        and isinstance(b[0].value, ast.Constant)
                        and isinstance(b[0].value.value, str)):
                    b[0].value.value = "<doc>"      # 只抹掉 docstring 的正文
                    # [EN] Only erase the docstring body
            return ast.dump(tree)

        cmp_files = cmp_same = 0
        cmp_bad: list[str] = []
        for p in files:
            bak = p.with_suffix(p.suffix + ".bak-bilingual")
            if not bak.is_file():
                continue
            rel = p.relative_to(APP).as_posix()
            if rel in MANUAL_EDIT:
                continue
            cmp_files += 1
            try:
                if fingerprint(bak) == fingerprint(p):
                    cmp_same += 1
                else:
                    cmp_bad.append(rel)
            except Exception as e:                          # noqa: BLE001
                cmp_bad.append(f"{rel}({type(e).__name__})")
        ok("C2 ★★ **代码结构一字未变**（AST 指纹：抹掉 docstring 正文后逐字相同）",
           cmp_files > 0 and not cmp_bad,
           f"比了 {cmp_files} 个有备份的文件 · 不一致：{cmp_bad[:5]}")

        # ★ C3：docstring 是**只追加**的 —— 现文件的 docstring 必须**以备份的
        #   docstring 开头**（一个字符都没被改写、更没有被重复追加）。
        #   这条比 C2 更细：C2 只看"结构"，C3 看"内容有没有被改/被重复追加"。
        #   （实测价值：它证明了幂等判据真的生效 —— 3438 个 docstring 全过。）
        # [EN] ★ C3: docstrings are **append-only** -- the current file's docstring must **start with** the
        # [EN] backup's
        # [EN] docstring** (not a single character rewritten, and certainly not repeatedly appended).
        # [EN] This is finer than C2: C2 only checks "structure", C3 checks "whether the content was modified /
        # [EN] repeatedly appended".
        # [EN] (measured value: it proves the idempotency criterion really works -- all 3438 docstrings pass.)
        d_bad: list[str] = []
        d_n = 0
        for p in files:
            bak = p.with_suffix(p.suffix + ".bak-bilingual")
            if not bak.is_file():
                continue
            if p.relative_to(APP).as_posix() in MANUAL_EDIT:
                continue
            try:
                tb = ast.parse(bak.read_text(encoding="utf-8"))
                tc = ast.parse(p.read_text(encoding="utf-8"))
            except Exception:                               # noqa: BLE001
                continue

            def _docs(t):
                out = []
                for n in ast.walk(t):
                    if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                      ast.AsyncFunctionDef)):
                        dd = ast.get_docstring(n, clean=False)
                        if dd:
                            out.append(dd)
                return out

            a, b = _docs(tb), _docs(tc)
            if len(a) != len(b):
                d_bad.append(f"{p.relative_to(APP).as_posix()}(doc 数 {len(a)}→{len(b)})")
                continue
            for x, y in zip(a, b):
                d_n += 1
                if y.strip() and not y.strip().startswith(x.strip()):
                    d_bad.append(p.relative_to(APP).as_posix())
                    break
        ok("C3 ★★ docstring **只被追加、没被改写**（现文以备份原文开头，"
           "也不会被重复追加英文段）",
           d_n > 1000 and not d_bad,
           f"比了 {d_n} 个 docstring · 有问题：{d_bad[:5]}")

        section("D 工具自身的正确性")
        try:
            import tempfile
            from bilingualize_comments import collect, render

            with tempfile.TemporaryDirectory(prefix="nws_bi_") as d:
                f = Path(d) / "t.py"
                #  ⚠ 两块注释**中间要隔一行代码**：它们挨着的话会被并成**一块**
                #    （块级双语就是按"连续行"分块的），于是 `len(items)==2` 不成立
                #    —— 第一版夹具就是挨着的，判据假红。
                # [EN] ⚠ The two comment blocks **must be separated by one line of code**: if they are adjacent they
                # [EN] will be merged into **one block**
                # [EN] (block-level bilingualization splits blocks by "consecutive lines"), so `len(items)==2` does not
                # [EN] hold
                # [EN] -- the first version's fixture was adjacent, and the criterion falsely went red.
                f.write_text('x = "中文 # 这不是注释"\n'
                             '# 第一块注释，含中文\n'
                             'z = 1\n'
                             'y = 2  # 行尾注释，也含中文\n', encoding="utf-8")
                lines, items = collect(f)
                ok("D1 字符串里的 `#` **不会被当成注释**（用 tokenize，不用正则）"
                   "，且隔开的两处算两块",
                   len(items) == 2, f"收到 {len(items)} 块")
                ok("D2 **行尾注释**也被收到（它的行号是那行代码）",
                   any(u.rows and u.rows[0] == 3
                       and any("行尾注释" in x for x in u.texts) for u in items),
                   [(u.rows, u.texts[:1]) for u in items])
                # ② 写回：**原行一个字不动**，译文整块插在**块尾之后**
                # [EN] ② Write back: **the original line is not touched at all**, the translation block is inserted
                # [EN] right **after the block end**
                new = render(lines, items, [["EN one"], ["EN two"]])
                nl = new.split("\n")
                ok("D3 写回时原行不动、译文插在**块尾之后**（块级双语）",
                   nl[0] == 'x = "中文 # 这不是注释"'
                   and nl[1] == "# 第一块注释，含中文"
                   and nl[2].strip() == f"{EN_MARK}EN one".strip()
                   and nl[3] == "z = 1", nl[:5])
                # ③ 幂等：带 `# [EN]` 的行不会再被翻
                # [EN] ③ Idempotency: lines with `# [EN]` will not be translated again
                f.write_text(new, encoding="utf-8")
                _l2, items2 = collect(f)
                ok("D4 **幂等**：已经带 `# [EN]` 的块不会被再翻一遍",
                   len(items2) == 0, f"第二次收到 {len(items2)} 块（应为 0）")
                # ④ 译文里还带中文 → 不用它（宁缺勿滥）
                # [EN] ④ If the translation still contains Chinese -> do not use it (better to omit than to be lax)
                # ④ 译文"整行几乎全是中文" → 不用它（宁缺勿滥）。
                #    ⚠ 夹具要**够长**：新口径是"cn ≥ 8 且英文词 ≤ 2"才拒，
                #      `还是中文`（4 个字）会**通过**，判据就成了恒真。
                # [EN] ④ Translation "almost the entire line is Chinese" -> don't use it (better to leave it out than
                # [EN] pad it).
                # [EN] ⚠ Fixtures must be **long enough**: the new criterion is "cn ≥ 8 and English words ≤ 2" to
                # [EN] reject,
                # [EN] `还是中文` (4 characters) would **pass**, making the criterion vacuously true.
                new2 = render(lines, items, [
                    ["这是一整段完全用中文写成的说明，一个英文单词都没有"],
                    ["EN two"]])
                ok("D5 ★ 译文若**整行几乎全是中文**，就不用它（宁缺勿滥）",
                   "一个英文单词都没有" not in new2, "")
                # ⑤ ★ docstring **幂等**：已经"中文 + 英文"的 docstring 不会再追加
                # [EN] ⑤ ★ docstring **idempotency**: a docstring that already has "Chinese + English" will not be
                # [EN] appended again
                f2 = Path(d) / "d.py"
                #  ⚠ 夹具里**必须带 `EN_SECTION` 标记行** —— 幂等就是认它的
                #    （第一版夹具没写标记，那条判据当然红）。
                # [EN] ⚠ The fixture **must contain an `EN_SECTION` marker line** -- idempotency relies on it
                # [EN] (The first version of the fixture didn't have the marker written, so that criterion of course
                # [EN] came up red).
                f2.write_text('def f():\n'
                              '    """中文说明第一行。\n'
                              '    中文说明第二行。\n\n'
                              '    English:\n'
                              '    An English paragraph already here.\n'
                              '    And a second English line.\n'
                              '    """\n', encoding="utf-8")
                _l3, items3 = collect(f2)
                ok("D6 ★ docstring **幂等**：已经是「中文 + 英文」的不会再追加一段"
                   "（注释块有 `# [EN]` 前缀天然幂等，docstring 只能靠这条判据）",
                   not [u for u in items3 if u.kind == "doc"],
                   [u.kind for u in items3])
                # ⑥ ★★ 反斜杠转义：译文里有 `\U`/`\N` 时**不能把文件写坏**
                # [EN] ⑥ ★★ Backslash escaping: when the translation contains `\U`/`\N`, the file **must not be
                # [EN] corrupted**
                f3 = Path(d) / "b.py"
                f3.write_text('def g():\n'
                              '    """中文说明。"""\n', encoding="utf-8")
                _l4, items4 = collect(f3)
                new3 = render(_l4, items4, [["Path C:\\Users\\x is here"]])
                try:
                    ast.parse(new3)
                    _ok3 = True
                except SyntaxError as e:
                    _ok3 = False
                    print("     转义后仍语法错：", e)
                ok("D7 ★★ 译文里的**反斜杠会被转义**（`\\U` 不会变成非法 Unicode 转义 "
                   "—— 实测这一条坏过 2 个文件）", _ok3, new3[:120])
        except Exception:                                   # noqa: BLE001
            ok("D 工具自身的行为判据", False, traceback.format_exc()[-300:])

    except BaseException:                                   # noqa: BLE001
        CHECKS.append({"name": "★ 判据运行中出现未捕获异常", "ok": False,
                       "detail": traceback.format_exc()[-800:]})
        traceback.print_exc()

    n_ok = sum(1 for c in CHECKS if c["ok"])
    REPORT.write_text(json.dumps(
        {"verifier": "verify_bilingual", "ok": n_ok == len(CHECKS),
         "passed": n_ok, "total": len(CHECKS), "checks": CHECKS},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n验证：{n_ok}/{len(CHECKS)}")
    for c in CHECKS:
        if not c["ok"]:
            print("  ✗", c["name"], "|", c["detail"][:200])
    return 0 if n_ok == len(CHECKS) else 2


if __name__ == "__main__":
    sys.exit(main())
