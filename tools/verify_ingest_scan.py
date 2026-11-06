# -*- coding: utf-8 -*-
"""验证：开卷**每次都读整个文件夹**（一个文件都不能少）。

用户 2026-10-06 报：「开卷这个地方为何现在只读一个文件，我放进来了一个文件夹，
之前都读取整个文件夹，生成后续内容的」。

根因（`ingest/scanner.scan_project` 的 `cache` 参数）：

  摄取管线曾经读一份 `.ingest_cache.json`（sha256 清单）并**跳过"未变更"的文件**。
  那看着像省事的优化，实际把设定集做残了 —— 开卷要把整份素材拼成
  `full_text` / `novel_text` / `outline_text` 交给模型，少一个文件就是少一块内容。
  而且它**只在改了一部分文件时才发作**（最难查的那种）：

    · 文件一个都没改 → 过滤后剩 0 个 → 管线兜底重扫全量 → **看着是对的**；
    · 只改了一个   → 过滤后剩 1 个 → 不触发兜底 → **只读那一个** ← 用户遇到的。

  已把 `cache` 参数、`load_cache/save_cache/build_cache` 与管线里那两个调用点
  **整个删掉**。这份脚本就是防止它被"好心"加回来。

判据设计
--------
★ 全部判据都**不检查源码**（源码哨兵抓不住"条件被改成 if False"），一律走行为：

**A 纯逻辑**（零 GUI、零网络、秒级）
  A1 ★★ 文件夹里放一份**旧版残留**的 `.ingest_cache.json`（匹配除一个之外的全部文件）
        → `scan_project` 仍必须返回**全部**文件。旧实现只会返回 1 个，**必红**。
  A2   缓存**匹配全部**文件 → 仍返回全部（旧实现这里靠兜底侥幸过关，所以 A1 才是关键）。
  A3 ★ 改掉一个文件的内容后重扫 → 仍是全部。
  A4   新加一个文件后重扫 → 全部（含新的那个）。
  A5   子文件夹里的文件要**递归**读到（只扫顶层 = 静默少读）。
  A6   边界没被一起改坏：点号开头的文件、`~$` 临时文件、程序自己写的
       `AI补全设定.md`、不支持的扩展名 —— 这些**仍然要跳过**。
  A7   `.nws_classify.json`（归类修正表）仍生效：它把某个文件改成「正文」，
       扫描结果的类别要跟着变（这条是顺手给同一段代码上的保险）。
  A8   接口层面：`scan_project` **不再接受** `cache` 关键字（传了就该 TypeError）
       —— 留着那个参数就迟早有人再传进来。
  A9 ★ 管线级端到端（无 GUI）：`run_ingest` 在"带残留缓存 + 改过一个文件"的文件夹上，
       `result.items` 必须是**全部**文件，且每个文件的内容都在里面。

**B 真机**（MOCK 模式，走真实入口 `show_import_wizard` → `_do_import`）
  B1 ★ 日志里那行「N 个文件（M 个有内容）」的 N == 文件夹里真正能读的文件数
       （夹具同样带残留缓存 + 改过一个文件 → 旧实现这里会报 1）。
  B2   同意门面板上「文件：N 个」也是全量（同一个数字，两个地方都得对）。

跑法：
    .venv\\Scripts\\python.exe tools/verify_ingest_scan.py
产出：
    assets/screenshots/ingest_scan_*.png
    assets/screenshots/ingest_scan_report.json

English:
Verification: open-book **reads the entire folder every time** (not one file may be missing).
User reported on 2026-10-06: "Why does open-book now only read one file, I put in a whole
folder,
it used to read the entire folder and generate subsequent content".
Root cause (the `cache` parameter of `ingest/scanner.scan_project`):
  The ingestion pipeline used to read a `.ingest_cache.json` (sha256 manifest) and **skip "unchanged" files**.
  That looked like a convenient optimization, but it actually crippled the setting collection -- open-book needs to assemble the entire material into
  `full_text` / `novel_text` / `outline_text` for the model, and one file missing means one chunk of content missing.
  And it **only triggers when only some files are changed** (the hardest kind to debug):
    · no file changed -> 0 left after filtering -> pipeline falls back to a full rescan -> **looks correct**;
    · only one changed -> 1 left after filtering -> fallback not triggered -> **only that one is read** <- what the user hit.
  The `cache` parameter, `load_cache/save_cache/build_cache`, and the two call sites in the pipeline have been
  **deleted entirely**. This script exists to prevent it from being "helpfully" added back.
Assertion design
--------
★ All assertions **do not inspect the source code** (a source sentinel cannot catch "the
condition was changed to if False"), everything goes through behavior:
**A pure logic** (zero GUI, zero network, sub-second)
  A1 ★★ put a **stale old-version** `.ingest_cache.json` in the folder (matching all files except one)
        -> `scan_project` must still return **all** files. The old implementation would return only 1, **must fail**.
  A2   cache matches **all** files -> still returns all (the old implementation got lucky here via the fallback, so A1 is the key one).
  A3 ★ change the content of one file and rescan -> still all.
  A4   add a new file and rescan -> all (including the new one).
  A5   files in subfolders must be read **recursively** (scanning only the top level = silently reading less).
  A6   boundaries were not broken along with it: dot-prefixed files, `~$` temp files, the program's self-written
       `AI补全设定.md`, unsupported extensions -- these **must still be skipped**.
  A7   `.nws_classify.json` (classification correction table) still takes effect: it changes some file to "body text",
       the category in the scan result must change accordingly (this is a bit of insurance applied to the same piece of code while we're at it).
  A8   Interface level: `scan_project` **no longer accepts** the `cache` keyword (passing it should raise TypeError)
       —— if that parameter is kept, sooner or later someone will pass it in again.
  A9 ★ Pipeline-level end-to-end (no GUI): `run_ingest` on a folder with "leftover cache + one modified file",
       `result.items` must be **all** files, and the content of every file must be in there.
**B Real machine** (MOCK mode, going through the real entry points `show_import_wizard` →
`_do_import`)
  B1 ★ The line in the log "N files (M with content)" — N == the number of files in the folder that are actually readable
       (the fixture likewise has leftover cache + one modified file → the old implementation would report 1 here).
  B2   "Files: N" on the consent gate panel is also the full count (the same number, both places must be correct).
How to run:
    .venv\\Scripts\\python.exe tools/verify_ingest_scan.py
Output:
    assets/screenshots/ingest_scan_*.png
    assets/screenshots/ingest_scan_report.json
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

# ★★ 铁律：**会写用户文件的路径，默认就该"写不进去"**。
#   这个脚本会真的跑一遍开卷流程（点按钮、跑管线），而 `CFG.save()` 在这条路上
#   随时可能被触发 —— 一旦触发就会把 `CFG.set('MOCK_LLM','true')` 这类测试值
#   写进用户的 `.env`（这个项目为此栽过四次）。所以起手就把写盘整个重定向掉。
# [EN] ★★ Iron rule: **paths that write to user files should by default be "unwritable"**.
# [EN] This script actually runs the open-book flow once (clicking buttons, running the pipeline), and
# [EN] `CFG.save()` on this path
# [EN] can be triggered at any time -- and once triggered it will write test values like
# [EN] `CFG.set('MOCK_LLM','true')`
# [EN] into the user's `.env` (this project has been burned by this four times). So redirect the entire
# [EN] disk write from the start.
VU.redirect_env_writes()

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')          # 演示模式：零网络、零成本、可复现
# [EN] Demo mode: zero network, zero cost, reproducible
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from ingest.scanner import (  # noqa: E402
    CLASSIFY_NAME, COMPLETION_NAME, scan_project,
)

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

REPORT: dict = {}
CHECKS: list[dict] = []


def ok(name: str, cond, detail='') -> bool:
    CHECKS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:220]})
    print(('  \u2713 ' if cond else '  \u2717 ') + name
          + (f'   [{detail}]' if detail else ''))
    return bool(cond)


# ══════════════════════════════════════════════════════════════════════
#  夹具
# [EN] Fixtures
# ══════════════════════════════════════════════════════════════════════
_FILES = {
    '设定/世界观.md': '架空世界，王朝末年，漕运断绝。',
    '设定/人物-林三.md': '林三：捕快，话少。',
    '大纲.md': '三幕：起、承、合。',
    '正文/第一章.md': '第一回，更漏子。雨脚敲着檐瓦。',
    '正文/第二章.md': '第二回，夜客。灯下有人敲门。',
}


def fixture(root: Path, *, name: str = '我的小说文件夹') -> Path:
    src = root / name
    for rel, txt in _FILES.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding='utf-8')
    return src


def write_legacy_cache(src: Path, *, skip: set[str] = frozenset()) -> None:
    """写下**旧版本**会写的那种 `.ingest_cache.json`。

    `skip` 里的文件名不写进缓存 —— 等价于"这几个文件后来被改过/是新加的"。
    旧实现据此跳过其余文件；新实现压根不看这个文件。
    
        English:
    Write the kind of `.ingest_cache.json` the **old version** would write.
        Filenames in `skip` are not written to the cache —— equivalent to "these files were later modified/are newly added".
        The old implementation skips the remaining files based on this; the new implementation doesn't look at this file at all.
    """
    cache: dict[str, str] = {}
    for f in src.rglob('*'):
        if f.is_file() and f.suffix.lower() == '.md' and f.name not in skip:
            cache[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    (src / '.ingest_cache.json').write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')


def readable_count(src: Path) -> int:
    """文件夹里**真正可读**的 .md 文件数（供 B 组比对界面报出的数字）。
        English:
    The number of **actually readable** .md files in the folder (for group B to compare against the
    number reported by the UI).
    """
    return len([f for f in src.rglob('*.md') if f.is_file()
                and not f.name.startswith('.') and not f.name.startswith('~$')])


def names_of(items) -> list[str]:
    return sorted(it.name for it in items)


# ══════════════════════════════════════════════════════════════════════
#  A 组：纯逻辑
# [EN] Group A: pure logic
# ══════════════════════════════════════════════════════════════════════
def logic_checks() -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_scan_'))
    REPORT['tmp'] = str(tmp)
    try:
        all_names = sorted(Path(r).name for r in _FILES)
        n_all = len(_FILES)

        # ── A1 ★★ 旧版残留缓存（只漏一个文件）──
        # [EN] ── A1 ★★ stale cache from old version (only one file missed) ──
        src = fixture(tmp, name='a1残留缓存')
        write_legacy_cache(src, skip={'第一章.md'})
        got = names_of(scan_project(src))
        REPORT['A1'] = got
        ok('★★ A1 文件夹里有旧版残留缓存 → 仍然读到**全部**文件'
           '（旧实现只会读到 1 个）',
           got == all_names, f'{len(got)}/{n_all} {got}')

        # ── A2 缓存匹配全部 ──
        # [EN] ── A2 cache matches all ──
        src2 = fixture(tmp, name='a2缓存全中')
        write_legacy_cache(src2)
        got2 = names_of(scan_project(src2))
        REPORT['A2'] = got2
        ok('A2 缓存与全部文件一致 → 仍然读到全部（不靠"扫到 0 个再兜底"）',
           got2 == all_names, f'{len(got2)}/{n_all}')

        # ── A3 ★ 改了一个文件 ──
        # [EN] ── A3 ★ changed one file ──
        (src2 / '正文' / '第一章.md').write_text('第一回，更漏子。（改过了）',
                                                encoding='utf-8')
        got3 = names_of(scan_project(src2))
        REPORT['A3'] = got3
        ok('★ A3 只改了一个文件 → 仍然是全部（不是"只读到改过的那个"）',
           got3 == all_names, f'{len(got3)}/{n_all} {got3}')

        # ── A4 新加一个文件 ──
        # [EN] ── A4 added one file ──
        (src2 / '伏笔.md').write_text('井里那件事还没说破。', encoding='utf-8')
        got4 = names_of(scan_project(src2))
        REPORT['A4'] = got4
        ok('A4 新加一个文件 → 全部读到（新的也在里面）',
           got4 == sorted(all_names + ['伏笔.md']), f'{len(got4)} {got4}')

        # ── A5 递归子文件夹 ──
        # [EN] ── A5 recursive subfolders ──
        src5 = fixture(tmp, name='a5深层')
        deep = src5 / '设定' / '更深的' / '再深一层'
        deep.mkdir(parents=True, exist_ok=True)
        (deep / '藏起来的世界观.md').write_text('最深处的一条设定。',
                                                encoding='utf-8')
        got5 = names_of(scan_project(src5))
        REPORT['A5'] = got5
        ok('A5 子文件夹里（连套三层）的文件也读得到',
           '藏起来的世界观.md' in got5, f'{len(got5)} {got5}')

        # ── A6 边界：该跳过的仍然跳过 ──
        # [EN] ── A6 boundary: things that should be skipped are still skipped ──
        src6 = fixture(tmp, name='a6边界')
        (src6 / '.草稿.md').write_text('点号开头的，不该读。', encoding='utf-8')
        (src6 / '~$旧稿.md').write_text('Word 临时文件，不该读。', encoding='utf-8')
        (src6 / COMPLETION_NAME).write_text('程序自己写的补全文档，不该读。',
                                            encoding='utf-8')
        (src6 / '图片说明.txt').write_text('txt 是支持的，要读。', encoding='utf-8')
        (src6 / '表.xlsx').write_text('不支持的格式，不读。', encoding='utf-8')
        got6 = names_of(scan_project(src6))
        REPORT['A6'] = got6
        ok('A6a 点号开头的文件仍然跳过', '.草稿.md' not in got6, got6)
        ok('A6b `~$` 临时文件仍然跳过', '~$旧稿.md' not in got6, got6)
        ok('A6c 程序自己写的补全文档仍然跳过（别喂给模型第二遍）',
           COMPLETION_NAME not in got6, got6)
        ok('A6d 支持的类型（.txt）照读', '图片说明.txt' in got6, got6)
        ok('A6e 不支持的扩展名（.xlsx）不读', '表.xlsx' not in got6, got6)

        # ── A6.5 ★★★ `.yaml` / `.yml` 也要读（2026-10-09 修的）──
        #   为什么单列一条：**示例文件夹 `设定/地点.yaml` 一直没被读过**
        #   （`_READ_SUFFIX` 里没有 `.yaml`），而它自己的文件头写着
        #   "程序拿它判断这地方适合什么事件、给整体地图用" ——
        #   作者照着示例写，效果一个字都到不了提取器，**界面上不报任何错**。
        #   判据要钉两件事：① 真的被扫到；② 内容**真的进了 full_text 的分类**
        #   （只断言"文件在名单里"是不够的 —— 那只是名字对上）。
        # [EN] ── A6.5 ★★★ `.yaml` / `.yml` must also be read (fixed 2026-10-09) ──
        # [EN] Why a separate case: **the sample folder `设定/地点.yaml` was never read**
        # [EN] (`_READ_SUFFIX` does not include `.yaml`), and its own file header says
        # [EN] "the program uses it to decide what events fit this place, and for the overall map" --
        # [EN] the author writes following the example, yet the result never reaches the extractor at all, **no
        # [EN] error shown in the UI**.
        # [EN] The assertion must pin two things: (1) it is actually scanned; (2) the content **actually makes
        # [EN] it into the full_text classification**
        # [EN] (asserting only "the file is in the list" is not enough -- that just means the name matches).
        src65 = fixture(tmp, name='a65yaml')
        (src65 / '设定' / '地点.yaml').write_text(
            '- 名称: 老茶肆\n  说明: 两层楼，后院有口井\n', encoding='utf-8')
        (src65 / '设定' / '别处.yml').write_text(
            '- 名称: 河湾\n  说明: 渡口西边\n', encoding='utf-8')
        items65 = scan_project(src65)
        names65 = names_of(items65)
        REPORT['A65'] = {i.name: i.category for i in items65}
        ok('A65a ★★ `.yaml` 被扫到（`地点.yaml` 是画地图时地名**唯一的**来源）',
           '地点.yaml' in names65, names65)
        ok('A65b ★ `.yml` 也认（别只加一个后缀）', '别处.yml' in names65, names65)
        ok('A65c ★★ YAML 里的中文**原样读出来**（不是乱码/空）',
           any(i.name == '地点.yaml' and '老茶肆' in i.content and '后院有口井' in i.content
               for i in items65),
           str([(i.name, len(i.content)) for i in items65]))
        ok('A65d ★★ 归到「设定」类 —— 不是「杂项」'
           '（杂项照样发给模型，但不会被当成设定专门用）',
           all(i.category == '设定' for i in items65 if i.name.endswith(('.yaml', '.yml'))),
           REPORT['A65'])

        # ── A6.7 ★★★ 分章要认 `# 第一章 …`（2026-10-09 修的）──
        #   为什么单列：`tools/` 里**从来没有判据覆盖 `split_chapters`**，
        #   于是"markdown 标题拆不出来"这个 bug 活到了今天 ——
        #   而说明书 §6.4 与 `samples/` 里给的示例，正文第一行**全是** `# 第一章 …`。
        #   坏法很安静：拆不出时每个文件都返回同一个键 `"正文"`，
        #   调用方 `chapters.update(...)` 一合并就**互相覆盖**，三章只剩一章。
        # [EN] ── A6.7 ★★★ chapter splitting must recognize `# 第一章 …` (fixed 2026-10-09) ──
        # [EN] Why a separate case: in `tools/` there **has never been an assertion covering
        # [EN] `split_chapters`**,
        # [EN] so the bug "markdown headings can't be split out" survived to today --
        # [EN] and in the spec §6.4 and the examples given in `samples/`, the first line of the body is
        # [EN] **always** `# 第一章 …`.
        # [EN] The failure mode is silent: when splitting fails, every file returns the same key `"正文"`,
        # [EN] and the caller `chapters.update(...)` on merge **overwrites each other**, leaving only one of
        # [EN] three chapters.
        from ingest.progress import split_chapters
        _md3 = ('# 第一章 甲\n\n第一段。\n\n# 第二章 乙\n\n第二段。\n\n'
                '# 第三章 丙\n\n第三段。')
        _got_md = split_chapters(_md3)
        REPORT['A67'] = {'md': list(_got_md), 'plain': list(split_chapters(
            '第一章 甲\n\na\n\n第二章 乙\n\nb'))}
        ok('A67a ★★★ `# 第一章 …` 这种 markdown 标题**拆得出来**（示例就是这么写的）',
           list(_got_md) == ['第一章 甲', '第二章 乙', '第三章 丙'], REPORT['A67']['md'])
        ok('A67b ★★★ 三章**一章都不许被覆盖**（键必须各不相同 —— '
           '都返回 "正文" 时后一个会把前一个整个盖掉）',
           len(_got_md) == 3, REPORT['A67']['md'])
        ok('A67c ★★ 拆出来的键**不带井号**、正文各归各章',
           '第一章 甲' in _got_md and _got_md['第一章 甲'] == '第一段。'
           and _got_md['第三章 丙'] == '第三段。', str(_got_md))
        ok('A67d ★★ 裸标题（`第一章 甲`）**照样认**（老写法不能打翻）',
           list(split_chapters('第一章 甲\n\na\n\n第二章 乙\n\nb')) == ['第一章 甲', '第二章 乙'],
           REPORT['A67']['plain'])
        ok('A67e ★ `# Chapter 2 …`（英文版）也认',
           list(split_chapters('# Chapter 1 A\n\nx\n\n# Chapter 2 B\n\ny'))
           == ['Chapter 1 A', 'Chapter 2 B'], '')
        ok('A67f ★ 没有章节标题时退回 `{"正文": 全文}`（不变）',
           list(split_chapters('一段没标题的散文。')) == ['正文'], '')

        # ── A7 归类修正表仍生效 ──
        # [EN] ── A7 classification correction table still takes effect ──
        src7 = fixture(tmp, name='a7归类修正')
        (src7 / '杂记.md').write_text('其实这是正文的一段。', encoding='utf-8')
        before = [it.category for it in scan_project(src7) if it.name == '杂记.md']
        (src7 / CLASSIFY_NAME).write_text(
            json.dumps({'杂记.md': '正文'}, ensure_ascii=False), encoding='utf-8')
        after = [it.category for it in scan_project(src7) if it.name == '杂记.md']
        REPORT['A7'] = {'before': before, 'after': after}
        ok('A7 `.nws_classify.json`（归类修正表）仍然生效：改成「正文」就进正文',
           before == ['杂项'] and after == ['正文'], f'{before} → {after}')

        # ── A8 接口层面：不该再有 cache 参数 ──
        # [EN] ── A8 interface level: there should no longer be a cache parameter ──
        try:
            scan_project(src7, cache={})                    # type: ignore[call-arg]
            raised = False
        except TypeError:
            raised = True
        REPORT['A8_raises'] = raised
        ok('A8 `scan_project` 不再接受 `cache`（留着参数迟早又被传进来）',
           raised, 'TypeError' if raised else '居然接受了')

        # ── A9 ★ 管线级端到端 ──
        # [EN] ── A9 ★ pipeline-level end-to-end ──
        src9 = fixture(tmp, name='a9管线')
        write_legacy_cache(src9, skip={'第二章.md'})
        # 模拟"只改过第二章"：缓存里就是没有它
        # [EN] Simulate "only chapter two was changed": the cache simply does not have it
        (src9 / '正文' / '第二章.md').write_text('第二回，夜客。（改过）',
                                                encoding='utf-8')
        REPORT['A9'] = _pipeline_scan(src9)
        ok('★ A9 管线端到端：带残留缓存 + 改过一个文件，`run_ingest` 仍收下全部文件',
           REPORT['A9'].get('n_items') == n_all
           and REPORT['A9'].get('all_content') is True,
           f"{REPORT['A9'].get('n_items')}/{n_all} "
           f"names={REPORT['A9'].get('names')}")
    finally:
        REPORT['checks_A'] = [c for c in CHECKS]
        shutil.rmtree(tmp, ignore_errors=True)


def _pipeline_scan(src: Path) -> dict:
    """真的跑一遍 `run_ingest`（MOCK，零网络），看它收下了几个文件。
        English:
    Actually run `run_ingest` once (MOCK, zero network) and see how many files it accepted.
    """
    import ingest.pipeline as PL
    run_dir = src.parent / '_a9设定集'
    try:
        res = asyncio.run(PL.run_ingest(src, settings_dir=run_dir))
    except Exception as e:                                    # noqa: BLE001
        return {'error': repr(e)[:200]}
    items = list(getattr(res, 'items', []) or [])
    # 每个文件的内容都必须真的在里面（不是"数量对了内容却是空的"）
    # ⚠ `_FILES` 的键是**相对路径**，要拼回 `src` 才能读（第一版直接 read_text
    #   相对路径 → FileNotFoundError，判据自己崩了）。
    # [EN] Every file's content must actually be in there (not "the count is right but the content is
    # [EN] empty")
    # [EN] ⚠ The keys of `_FILES` are **relative paths**, they must be joined back to `src` to be read (the
    # [EN] first version called read_text directly
    # [EN] on the relative path -> FileNotFoundError, the assertion itself crashed).
    blob = '\n'.join(str(getattr(it, 'content', '') or '') for it in items)
    all_content = all(
        (src / rel).read_text(encoding='utf-8')[:6] in blob for rel in _FILES)
    return {'n_items': len(items), 'names': names_of(items),
            'all_content': all_content,
            'tier': getattr(res, 'tier', '')}


# ══════════════════════════════════════════════════════════════════════
#  B 组：真机
# [EN] Group B: real machine
# ══════════════════════════════════════════════════════════════════════
async def main(page: ft.Page):
    from gui.app_flet import NovelWorldApp
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_scanui_'))
    VU.isolate_projects_dir(tmp / 'Projects')

    async def shot(name: str, note: str) -> None:
        try:
            page.update()
            await asyncio.sleep(0.35)
            data = await page.take_screenshot()
            (OUT / name).write_bytes(data)
            REPORT.setdefault('shots', []).append({'shot': name, 'note': note})
        except Exception as e:                                # noqa: BLE001
            REPORT.setdefault('shots', []).append({'shot': name, 'error': str(e)})

    try:
        # 夹具与 A1 同型：**带旧版残留缓存，并且只改过一个文件**
        # [EN] Fixture is the same shape as A1: **with stale cache from old version, and only one file
        # [EN] changed**
        src = fixture(tmp, name='b1真机')
        write_legacy_cache(src, skip={'第二章.md'})
        want = readable_count(src)
        REPORT['B_want'] = want

        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.6)
        app._wizard_path = str(src)
        app._wizard_name = '全量读取真机'
        app._wizard_opts['ai_optimize'] = True
        app._wizard_opts['repair_source'] = False   # 那一步会停下等确认，这里不需要
        # [EN] That step will pause waiting for confirmation, not needed here
        app._do_import(page)

        st = app._ingest_state
        # 等日志里出现「N 个文件（M 个有内容）」那一行（本地扫描阶段就有）
        # [EN] Wait for the line "N 个文件（M 个有内容）" in the log (it appears already at the local scan stage)
        logs: list[str] = []
        found = ''
        for _ in range(150):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            lv = ui.get('log_list')
            if lv is None:
                continue
            logs = [str(getattr(c, 'value', '') or '')
                    for c in VU.walk(lv) if isinstance(c, ft.Text)]
            for line in logs:
                m = re.search(r'(\d+)\s*个文件', line)
                if m:
                    found = line
                    break
            if found:
                break
        REPORT['B_logs'] = logs[:12]
        REPORT['B_found_line'] = found
        m = re.search(r'(\d+)\s*个文件', found) if found else None
        got_n = int(m.group(1)) if m else -1
        ok('★ B1 真机：日志里报的文件数 == 文件夹里真正能读的文件数'
           '（旧实现这里会报 1）', got_n == want, f'日志 {got_n} / 实际 {want}')

        # ── B2 同意门面板上的数字 ──
        # [EN] ── B2 the numbers on the consent gate panel ──
        ui = st.get('ui') or {}
        for _ in range(150):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            panel = ui.get('consent_panel')
            if panel is not None and getattr(panel, 'visible', False):
                break
        facts = [str(getattr(c, 'value', '') or '')
                 for c in getattr(ui.get('consent_facts'), 'controls', [])]
        REPORT['B_facts'] = facts
        joined = ' '.join(facts)
        m2 = re.search(r'(\d+)\s*个', joined)
        got_n2 = int(m2.group(1)) if m2 else -1
        ok('B2 同意门面板上「文件：N 个」也是全量（同一数字两处都得对）',
           got_n2 == want, f'面板 {got_n2} / 实际 {want}')
        await shot('ingest_scan_consent.png', '真机：同意门面板上的文件数')

        # 收尾：不同意 → 管线中止（一条 LLM 都不发），界面回到安全状态
        # [EN] Wrap-up: decline -> pipeline aborts (not a single LLM call is sent), UI returns to a safe state
        ui = st.get('ui') or {}
        if ui.get('consent'):
            ui['consent'](False)
        await asyncio.sleep(0.8)
        REPORT['B_phase_after'] = st.get('phase')
    except Exception:                                         # noqa: BLE001
        import traceback
        REPORT['B_fatal'] = traceback.format_exc()
        ok('B1 真机：日志里报的文件数 == 文件夹里真正能读的文件数', False,
           '崩溃，见报告 B_fatal')
    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:                                     # noqa: BLE001
            pass
        REPORT['checks'] = CHECKS
        REPORT['passed'] = sum(1 for c in CHECKS if c['ok'])
        REPORT['total'] = len(CHECKS)
        (OUT / 'ingest_scan_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n开卷全量读取验证：{REPORT["passed"]}/{REPORT["total"]}')
        await shutdown(page, code=0 if REPORT['passed'] == REPORT['total'] else 2)


if __name__ == '__main__':
    try:
        logic_checks()
        ft.run(main, assets_dir=str(APP_DIR / 'assets'))
    except Exception:                                         # noqa: BLE001
        import traceback
        traceback.print_exc()
        exit_now(2)
