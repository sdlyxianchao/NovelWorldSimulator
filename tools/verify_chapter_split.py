# -*- coding: utf-8 -*-
"""验证：**章节标题识别**（`util/chapters.py`）＋ **正文按章号排序**。

★★ 这两件事是 2026-10-27 重写**某部真实作品的样章**时**撞出来的**，不是凭空加的：

  ① 章节识别：老正则是 `第.{1,5}[章回节]` —— 中间那个 `.{1,5}` **允许任意字符**，
     于是正文里单独成行的一句台词

         第二回正了。

     会被当成**章节标题**。后果不是"多认一章"这么轻：**它把这一行之后的所有
     正文都切成了"第二章"**，而真正的章节标题还在前面 ⇒ 章节边界整个错位
     ⇒ **前情提要按错的章节对齐**。而且坏得很安静（拆不出来时每个文件都返回
     同一个键 `"正文"`，一合并就互相覆盖）。

  ② 正文排序：以前正文按**文件系统顺序**拼，于是「文风样本＝前 4000 字」会
     **跳章** —— Windows/NTFS 下 `rglob` 返回「第一章 → 第三章 → 第二章」
     （同一前缀的汉字按码位排：一 U+4E00 < 三 U+4E09 < 二 U+4E8C），
     实测「第一章 开门」后面紧跟的是「第三章 灯让」的开头。

判据分层（每层都要能红，见 `developers/mutate_chapter_split.py`）：
  A **章节标记**：能认 `第N章` / `第 N 回` / `Chapter N` / `第N节` / `第N卷`；
     键里**不带** markdown 井号；拆不出时退回 `{"正文": 全文}`。
  B ★★★ **正文句子不许被当成章节标题**（本次修的那个 bug）。
  C **分隔符**：标记后面要有分隔符（空格 / 冒号 / 间隔号…）或整行到头；
     严格档认不出时**退回宽松档**（分隔符可省）。
  D **章号**：`chapter_no` 认章号；认不出返回 0（不猜）。
  E ★★★ **全项目只有一份实现**（不许再有 `第.{1,5}[章回节]` 这类松正则）。
  F ★★ **正文按章号排序**：喂给模型的章节顺序是章号序，不是文件系统序。
  G **中文数字解析**：`两三` 判非法（各写各的那两套本来答案不一样）。

用法：.venv\\Scripts\\python.exe tools/verify_chapter_split.py
产出：assets/screenshots/chapter_split_report.json

English:
Verification: **chapter-heading recognition** (`util/chapters.py`) + **body text sorted by
chapter number**.
★★ Both came out of rewriting the sample chapters of **one real book** on 2026-10-27, not out of
thin air:
  (i) the old pattern `第.{1,5}[章回节]` **allowed arbitrary characters** in the middle, so a
      standalone line of prose such as "第二回正了。" was taken for a chapter heading --
      **everything after that line became "chapter 2"**, so the chapter boundaries shifted and the
      recap aligned against the wrong chapters.
  (ii) body text used to be concatenated in **file-system order**, so the "style sample = first
      4000 chars" **skipped chapters** (on Windows/NTFS `rglob` returns "chapter 1 -> chapter 3 ->
      chapter 2").
Criteria layered (each layer must be able to go red, see `developers/mutate_chapter_split.py`):
  A **Chapter markers**: `第N章` / `第 N 回` / `Chapter N` / `第N节` / `第N卷`; the keys carry **no**
     markdown hash; when nothing can be split it falls back to `{"正文": full text}`.
  B ★★★ **A sentence in the body must not be taken for a chapter heading** (the bug fixed here).
  C **Separator**: a separator must follow the marker (space / colon / middle dot ...) or the
     marker is the whole line; strict mode falls back to loose mode when it recognises nothing.
  D **Chapter number**: `chapter_no` reads it; unrecognisable returns 0 (never guess).
  E ★★★ **One implementation in the whole project** (no loose `第.{1,5}[章回节]` left).
  F ★★ **Body text sorted by chapter number**: the order handed to the model is the chapter order,
     not the file-system order.
  G **Chinese numerals**: "两三" is invalid (the two copies disagreed on it).
Usage: .venv\\Scripts\\python.exe tools/verify_chapter_split.py
Output: assets/screenshots/chapter_split_report.json
"""
from __future__ import annotations

import ast
import json
import re
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

REPORT: dict = {}
CHECKS: list[dict] = []


#: 退出码统一出口（2026-10-28 新建）。⚠ 这一支原来 `ok_all` **只在"中途崩溃"时**才置 False，
#:   `ok()` 从不改它 ⇒ **任何一条断言红掉，退出码仍是 0** ⇒
#:   它在 `tools/run_all_verifications.py` 里**恒绿**：红灯打出来也没人看得见
#:   ⇒ 那条覆盖**从来没被证明过**。
#:   （2026-10-28 实测：把第一处 `ok()` 的条件改成 `False`，退出码仍是 0。）
#: [EN] ⚠ The exit code now goes through the shared outlet `tools/verify_exit.py`; before that this
#: [EN] criterion was **always green** in the regression (measured: forcing an assertion to
#: [EN] `False` still exited 0).
from tools.verify_exit import finish   # noqa: E402


def ok(name: str, cond, detail='') -> bool:
    CHECKS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:300]})
    print(('  \u2713 ' if cond else '  \u2717 ') + name
          + (f'   [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def head(t: str) -> None:
    print(f'\n{t}', flush=True)


# ══════════════════════════════════════════════════════════════════════
#  A/B/C/D：章节标记、正文不许被当章头、分隔符、章号
# [EN] A/B/C/D: markers, prose must not become a heading, separator, chapter number
# ══════════════════════════════════════════════════════════════════════
def test_markers() -> None:
    from util.chapters import chapter_no, cn_to_int, find_chapter_marks, split_chapters

    # ── A1 各种写法都认 ──
    cases = [
        ('# 第一章 早了一刻', ['第一章 早了一刻']),
        ('第一章 早了一刻', ['第一章 早了一刻']),
        ('# Chapter 1 A', ['Chapter 1 A']),
        ('## 第1章 开门', ['第1章 开门']),
        ('# 第一节 起步', ['第一节 起步']),
        ('# 第一卷 开端', ['第一卷 开端']),
    ]
    got = []
    for text, want in cases:
        g = list(split_chapters(text + '\n\n正文。\n'))
        got.append((text, g, want))
    REPORT['A1'] = [[g[0], g[1]] for g in got]
    ok('A1 各种章节写法都拆得出来（`第N章`/`第 N 回`/`Chapter N`/`第N节`/`第N卷`/带不带井号）',
       all(g[1] == g[2] for g in got),
       '；'.join(f'{g[0][:14]}→{g[1]}' for g in got))

    # ── A2 键里不带井号，正文各归各章 ──
    _md = ('# 第一章 甲\n\n第一段。\n\n# 第二章 乙\n\n第二段。\n\n# 第三章 丙\n\n第三段。')
    _ch = split_chapters(_md)
    REPORT['A2'] = list(_ch)
    ok('A2 ★★ 键里**不带井号**，正文各归各章（三章一章都不许少）',
       list(_ch) == ['第一章 甲', '第二章 乙', '第三章 丙']
       and _ch.get('第一章 甲') == '第一段。' and _ch.get('第三章 丙') == '第三段。',
       str(list(_ch)))

    # ── A3 拆不出时退回 `{"正文": 全文}` ──
    _none = split_chapters('一段没标题的散文。')
    REPORT['A3'] = list(_none)
    ok('A3 拆不出章节时退回 `{"正文": 全文}`（老行为不变）',
       list(_none) == ['正文'] and _none['正文'] == '一段没标题的散文。', str(list(_none)))

    # ── B ★★★ 本次修的 bug：正文句子不许被当成章节标题 ──
    _prose = ('# 第二章 · 上灯\n\n第二天晌午，我上柜台去送茶。\n\n'
              '第二回正了。\n\n他还站着。\n')
    _b1 = list(split_chapters(_prose))
    REPORT['B1'] = _b1
    ok('B1 ★★★ 正文里单独成行的一句（「第二回正了。」）**不许**被当成章节标题'
       '（老正则会把它当章头 ⇒ 这一行之后全被切成"第二章"）',
       _b1 == ['第二章 · 上灯'], str(_b1))

    _prose2 = '描了三回。第一回太粗，第二回断了，第三回勉强连上了。\n'
    _b2 = list(split_chapters(_prose2))
    REPORT['B2'] = _b2
    ok('B2 ★★★ 一整句里好几个「第X回」也不许被当成章头',
       _b2 == ['正文'], str(_b2))

    _prose3 = '第三年灯节，下了一夜雨。\n\n第四年灯节，没下雨。\n'
    _b3 = list(split_chapters(_prose3))
    REPORT['B3'] = _b3
    ok('B3 「第X年」不是章节单位，不许被当成章头',
       _b3 == ['正文'], str(_b3))

    # 关键：**正文不许被切开**（不只是"章头数对"）
    _both = ('# 第一章 甲\n\n第一段。\n\n第二回正了。\n\n第二段。\n\n'
             '# 第二章 乙\n\n第三段。')
    _b4 = split_chapters(_both)
    REPORT['B4'] = {k: v for k, v in _b4.items()}
    ok('B4 ★★★ 章节边界不许被正文句子挪走'
       '（"第二回正了。"在第一章中间时，它仍属第一章）',
       list(_b4) == ['第一章 甲', '第二章 乙']
       and '第二回正了。' in _b4.get('第一章 甲', ''), str(list(_b4)))

    # ── C1 分隔符形式 ──
    _c1 = list(split_chapters('# 第一章 · 开门\n\n正文。\n\n# 第二章：上灯\n\n正文。\n'))
    REPORT['C1'] = _c1
    ok('C1 分隔符形式都认（间隔号 `·` / 冒号 `：`）',
       _c1 == ['第一章 · 开门', '第二章：上灯'], str(_c1))

    # ── C2 严格档认不出 → 退回宽松档 ──
    _c2 = list(split_chapters('第一章开门\n\n正文。\n'))
    REPORT['C2'] = _c2
    ok('C2 ★ 严格档认不出时**退回宽松档**（「第一章开门」没有分隔符，也要能拆出来）'
       '（宁可多拆，不可整篇一章）',
       _c2 == ['第一章开门'], str(_c2))

    # ── C3 严格档与宽松档是**两档**，不是一档 ──
    _strict = find_chapter_marks('# 第一章 甲\n\n正文。\n', strict=True)
    _loose = find_chapter_marks('# 第一章 甲\n\n正文。\n', strict=False)
    REPORT['C3'] = {'strict': [m.title for m in _strict],
                    'loose': [m.title for m in _loose]}
    ok('C3 两档都在（严格档要分隔符、宽松档可省；宽松档另认 `【…】`）',
       len(_strict) == 1 and len(_loose) == 1
       and len(find_chapter_marks('【井底】\n\n正文。\n', strict=False,
                                  allow_bracket=True)) == 1,
       str(REPORT['C3']))

    # ── B5 ★★★ 标记 + 分隔符 + **一句话** 也不许被当成章头 ──
    #   ⚠ 这条是给"余文不许含句读"那道闸**单独**用的：
    #   B1 那条只靠"分隔符"就挡得住（标记后面是汉字，不是分隔符），
    #   所以拆掉"余文"这条闸时 B1 仍然是绿的 —— 没有 B5 就测不到那道闸。
    _b5 = list(split_chapters(
        '# 第二章 · 上灯\n\n正文。\n\n第二回 正了。\n\n再来一句。\n'))
    REPORT['B5'] = _b5
    ok('B5 ★★★ 标记 + 分隔符 + **一句话**（「第二回 正了。」）也不许被当成章头'
       '（"标题余文不许含句读"那道闸 —— B1 只靠"分隔符"挡，测不到这一道）',
       _b5 == ['第二章 · 上灯'], str(_b5))

    # ── C4 ★★ 严格档**不认**没有分隔符的写法（宽松档认） ──
    _c4_strict = find_chapter_marks('第一章开门\n\n正文。\n', strict=True,
                                     fallback=False)
    _c4_loose = find_chapter_marks('第一章开门\n\n正文。\n', strict=False)
    REPORT['C4'] = {'strict': len(_c4_strict), 'loose': len(_c4_loose)}
    ok('C4 ★★ 严格档**不认**「第一章开门」（标记后面没有分隔符），宽松档认'
       '（"分隔符"那道闸 —— 与 B5 那道闸**各自独立**，各自都要能红）',
       len(_c4_strict) == 0 and len(_c4_loose) == 1, str(REPORT['C4']))

    # ── D 章号 ──
    _nos = (chapter_no('第一章 · 开门'), chapter_no('第12章 早了一刻'),
            chapter_no('第1章 开门'), chapter_no('Chapter 3 Something'),
            chapter_no('（全文）'), chapter_no(''))
    REPORT['D'] = list(_nos)
    ok('D ★★ `chapter_no` 认章号（第一章·开门→1 / 第12章→12 / Chapter 3→3 / 认不出→0 / 空→0）',
       _nos == (1, 12, 1, 3, 0, 0), str(_nos))

    # ── G 中文数字 ──
    _cn = (cn_to_int('三'), cn_to_int('十'), cn_to_int('十五'), cn_to_int('二十三'),
           cn_to_int('一百零八'), cn_to_int('12'), cn_to_int('两三'), cn_to_int('井底'),
           cn_to_int(''))
    REPORT['G'] = list(_cn)
    ok('G ★★ 中文数字解析（三/十/十五/二十三/一百零八/12 认得；'
       '**「两三」判非法**、认不出的返回 None）',
       _cn == (3, 10, 15, 23, 108, 12, None, None, None), str(_cn))


# ══════════════════════════════════════════════════════════════════════
#  E：全项目只有一份实现
# [EN] E: one implementation in the whole project
# ══════════════════════════════════════════════════════════════════════
def test_single_impl() -> None:
    from util.chapters import split_chapters
    from ingest.progress import split_chapters as prog_split

    ok('E0a `ingest.progress.split_chapters` 与 `util.chapters.split_chapters` 是**同一个函数**'
       '（不是两份拷贝）',
       prog_split is split_chapters, f'{prog_split!r}')

    # 只扫**产品代码**（`tools/` `developers/` `tests/` 里出现那个写法是正常的：
    # 判据脚本自己会写它、变异脚本必须写它、备份文件里留着旧代码也是正常的）。
    PRODUCT_DIRS = ('ingest', 'booklab', 'world', 'util', 'crew', 'sim', 'gui',
                    'director', 'polish', 'craft', 'export', 'agents', 'actors',
                    'store', 'display', 'image_gen', 'llm', 'mcp', 'research',
                    'skills', 'novel_bench', 'packages', 'launchers', 'compliance')
    loose: list[str] = []
    for d in PRODUCT_DIRS:
        base = APP / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob('*.py')):
            if '.bak' in p.name or '__pycache__' in p.parts:
                continue
            try:
                src = p.read_text(encoding='utf-8', errors='ignore')
                tree = ast.parse(src)
            except Exception:                                # noqa: BLE001
                continue
            # 文档字符串不算（那只是历史记录）
            docs: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)):
                    d = ast.get_docstring(node, clean=False)
                    if d:
                        docs.add(d)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and node.value not in docs
                        and re.search(r'第\.\{1,\d\}', node.value)):
                    loose.append(str(p.relative_to(APP)))
                    break
    REPORT['E'] = loose
    ok('E0b ★★★ 「章节标记」**产品代码里只有一份实现**'
       '（不许再有 `第.{1,5}[章回节]` 这类松正则 —— 它就是这次那个 bug 的源头）',
       not loose, str(loose[:6]))

    # ── E1 ★★★ 装饰器与函数定义之间不许夹东西 ──
    #   ★ 这是本轮**真踩到**的坑（2026-10-27）：抽 `assemble_body_chapters()` 时，
    #   新函数被插在 `@MODELS.agent('ingest')` 与 `async def run_ingest(` **中间**，
    #   ⇒ **装饰器挂到了新函数上，`run_ingest` 反而没了装饰器**。
    #   症状极隐蔽：新函数变成协程（调用它得到 coroutine，解包直接 TypeError），
    #   而 `run_ingest` 悄悄退化成"没登记的 agent"。
    #   ⇒ 静态判：**装饰器与 `def` 之间最多隔一行空行**，不许夹注释/别的定义。
    gaps: list[str] = []
    for d in PRODUCT_DIRS:
        base = APP / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob('*.py')):
            if '.bak' in p.name or '__pycache__' in p.parts:
                continue
            try:
                tree = ast.parse(p.read_text(encoding='utf-8', errors='ignore'))
            except Exception:                                # noqa: BLE001
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for dec in node.decorator_list:
                    end = getattr(dec, 'end_lineno', dec.lineno) or dec.lineno
                    if node.lineno - end > 1:
                        gaps.append(f'{p.relative_to(APP)}:{dec.lineno}'
                                    f' → {node.name}（中间夹了 {node.lineno - end - 1} 行）')
                    # agent 装饰器只能贴在 **async** 函数上：
                    #   贴到同步函数上，装饰器会把它包成协程 ⇒ 调用它得到 coroutine，
                    #   而**真正该被装饰的那个函数反而没被登记**。
                    if 'agent(' in (ast.get_source_segment(
                            p.read_text(encoding='utf-8', errors='ignore'), dec) or ''):
                        if not isinstance(node, ast.AsyncFunctionDef):
                            gaps.append(f'{p.relative_to(APP)}:{dec.lineno}'
                                        f' → {node.name}（agent 装饰器贴在**同步**函数上）')
    REPORT['E1'] = gaps
    ok('E1 ★★★ 装饰器与函数定义之间**不许夹东西**；agent 装饰器只许贴在 **async** 函数上'
       '（本轮真踩到：抽函数时把 `@MODELS.agent(...)` 截走，'
       '`run_ingest` 悄悄退化成"没登记的 agent"）',
       not gaps, str(gaps[:4]))


# ══════════════════════════════════════════════════════════════════════
#  F：正文按章号排序
# [EN] F: body text sorted by chapter number
# ══════════════════════════════════════════════════════════════════════
def test_ordering() -> None:
    from ingest.pipeline import assemble_body_chapters

    class _It:
        def __init__(self, name: str, content: str) -> None:
            self.name = name
            self.content = content
            self.category = '正文'

    # 故意按 **Windows 文件系统顺序** 给：一 → 三 → 二
    items = [
        _It('第一章 开门.md', '# 第一章 · 开门\n\n甲。\n'),
        _It('第三章 灶上.md', '# 第三章 · 灶上\n\n丙。\n'),
        _It('第二章 上灯.md', '# 第二章 · 上灯\n\n乙。\n'),
    ]
    chapters, novel_text = assemble_body_chapters(items)
    REPORT['F'] = {'keys': list(chapters), 'text': novel_text}
    ok('F1 ★★ 正文通道的章节**按章号排序**'
       '（Windows 文件系统顺序是 一→三→二，排序后必须 一→二→三）',
       list(chapters) == ['第一章 · 开门', '第二章 · 上灯', '第三章 · 灶上'],
       str(list(chapters)))

    ok('F2 ★★ 拼出来的正文也是章号序（甲→乙→丙），不是文件系统序（甲→丙→乙）',
       novel_text.index('甲') < novel_text.index('乙') < novel_text.index('丙'),
       repr(novel_text[:40]))

    # 文风样本取前 N 字 ⇒ 必须落在**连续的**章节上（不许跳章）
    ok('F3 ★★ 文风样本取前 N 字必须落在**连续的**章节上（旧实现会跳到第三章）',
       novel_text.startswith('甲') and novel_text[:4] == '甲。\n乙',
       repr(novel_text[:12]))

    # 一个正文文件都没有 ⇒ 返回空（以前 `novel_text` 只在 `if chapters:` 里赋值 ⇒ NameError）
    ch0, nt0 = assemble_body_chapters([])
    REPORT['F0'] = {'chapters': ch0, 'text': nt0}
    ok('F4 ★★ 一个正文文件都没有时返回空（不是崩）'
       '（以前 `novel_text` 只在 `if chapters:` 分支里赋值 ⇒ 这里 NameError）',
       ch0 == {} and nt0 == '', f'{ch0} / {nt0!r}')

    # 拆不出章节的文件**不许互相覆盖**
    # ⚠ 必须用**同名**的两个文件（不同名的本来就不会撞，测不到那个 `while` 循环）。
    #   真会撞的场景：两个不同子目录里各有一个 `第一章.md`，而都拆不出章节。
    items2 = [
        _It('第一章.md', '没有章节标题的一段。\n'),
        _It('第一章.md', '也没有章节标题的另一段。\n'),
    ]
    ch2, nt2 = assemble_body_chapters(items2)
    REPORT['F5'] = {'keys': list(ch2), 'text': nt2}
    ok('F5 ★★ 拆不出章节的两个文件**不许互相盖掉**'
       '（以前都用同一个键 `"正文"` ⇒ 后一个把前一个整个盖掉，实测三章只剩一章）',
       len(ch2) == 2 and '没有章节标题的一段' in nt2 and '也没有章节标题的另一段' in nt2,
       str(list(ch2)))


def main() -> int:
    print('章节标题识别 ＋ 正文按章号排序 —— 验证', flush=True)
    ok_all = True
    try:
        head('A/B/C/D/G. 章节标记、正文不许被当章头、分隔符、章号、中文数字')
        test_markers()
        head('E. 全项目只有一份实现')
        test_single_impl()
        head('F. 正文按章号排序')
        test_ordering()
    except Exception:                                     # noqa: BLE001
        REPORT['fatal'] = traceback.format_exc()
        ok('验证没有中途崩溃（有崩溃就不是全绿）', False, REPORT['fatal'][-300:])
        ok_all = False
    REPORT['checks'] = CHECKS
    return finish(REPORT, out_path=OUT / 'chapter_split_report.json')


if __name__ == '__main__':
    sys.exit(main())
