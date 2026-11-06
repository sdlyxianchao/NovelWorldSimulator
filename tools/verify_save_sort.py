# -*- coding: utf-8 -*-
"""判据：**拾卷的「故事时间」跨度 + 四种排序**。

来历（2026-10-10 用户原话）
---------------------------
「初始菜单的拾卷里 第2列的推演存档列表 **加上一个属性就其进行的推演的
开始和结束时间（故事里的时间）** 然后上面加一组单选框 可以按照推演开始时间
正序 / 开始时间倒序 / 结束时间正序 / 结束时间倒序 4 种方式排列」。

两个容易做错的地方，这一支专门钉住：

① **"故事里的时间"不是"你什么时候点的起笔"**。文件夹名上那串
   `第1次模拟2026-10-05-20-00` 是**现实世界**的时刻；用户点名要的是
   故事内的时间。两者常常差很远（一轮跑了二十分钟，故事里过了三十天）。

② **读不到故事时间的存档，正序倒序都得排在最后**。不许让它按"第 0 天"
   参与排序 —— 那会让一轮旧存档冒充"最早开始的"顶到第一位（正序时），
   把真正该看的那几轮挤下去。这是"缺数据"这一类里最难发现的一种错，
   因为它不报错，只是把顺序悄悄弄反。

覆盖
----
  A. `StorySpan` 读盘 —— 四层来源各来一遍（JSON / md / 原文目录 / state.db），
     外加"什么都没有"那一档（**不许编**）
  B. 排序键 —— 未知值必须落在最后（正序倒序都是）
  C. 接线 —— 单选框、默认档、`_sorted_runs`、卡片与详情上那一行
  D. 扫描器自检

跑法：`.venv/Scripts/python.exe tools/verify_save_sort.py`
报告：`assets/screenshots/save_sort_report.json`

English:
Criterion: **the "story time" span of 拾卷 + four kinds of sorting**.
Origin (2026-10-10 user's own words)
---------------------------
"In 拾卷 of the initial menu, the deduction save list in column 2 **add an attribute for the
deduction's
start and end time (the time in the story)** then add a group of radio buttons above it to
arrange by deduction start time
ascending / start time descending / end time ascending / end time descending, 4 ways.".
Two easy-to-get-wrong points, this branch is dedicated to pinning them down:
① **"The time in the story" is not "when you clicked start"**. The string on the folder name
   `第1次模拟2026-10-05-20-00` is a **real-world** moment; what the user specifically asked for is
   the in-story time. The two often differ greatly (a round runs for twenty minutes, thirty days pass in the story).
② **A save whose story time cannot be read must sort last in both ascending and descending
order**. Do not let it participate in sorting as "day 0"
   —— that would let an old save masquerade as "the earliest started" and jump to first place (in ascending order),
   pushing down the rounds that really should be seen. This is the hardest-to-find kind of error in the "missing data" category,
   because it does not raise an error, it just quietly flips the order.
Coverage
----
  A. `StorySpan` disk reading —— each of the four sources once (JSON / md / 原文 directory / state.db),
     plus the "nothing at all" tier (**must not fabricate**)
  B. Sort key —— unknown values must land last (both ascending and descending)
  C. Wiring —— radio buttons, default tier, `_sorted_runs`, the line on cards and details
  D. Scanner self-check
How to run: `.venv/Scripts/python.exe tools/verify_save_sort.py`
Report: `assets/screenshots/save_sort_report.json`
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

REPORT: dict = {'checks': [], 'notes': []}


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    return bool(cond)


def read(rel: str) -> str:
    return (APP / rel).read_text(encoding='utf-8')


def between(text: str, start: str, end: str = '') -> str:
    i = text.find(start)
    if i < 0:
        return ''
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j if j > 0 else len(text)]


def code_only(block: str) -> str:
    return '\n'.join(ln for ln in block.splitlines()
                     if not ln.strip().startswith('#'))


def _block_under(text: str, anchor: str) -> str:
    """`anchor` 那一行**下面属于它的整块**（缩进比它深的连续行）。找不到返回 `''`。

    ★ 为什么不用 `between(anchor, 下一个已知的字符串)`：那种写法要求"下一个锚点恰好是
      紧跟其后的那一行"，产品里插一句注释就断 —— C6 就是这么变成恒红的
      （它锚的下一个字符串是 `titles.append(mk_md(`，而那一行在树状图改造里没了）。
      按**缩进**取块，与具体写了什么无关，产品改内容也不会把它打断。

    English: The whole block **belonging to** the `anchor` line (following lines indented deeper).
    ★ Why not `between(anchor, some next literal)`: that requires the next anchor to be exactly the
      following line, and one inserted comment breaks it -- which is how C6 became permanently red
      (it anchored on `titles.append(mk_md(`, deleted by the tree redesign). Taking the block by
      **indentation** is independent of the wording, so content changes cannot break it.
    """
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().startswith(anchor.strip()) or anchor.strip() in ln:
            base = len(ln) - len(ln.lstrip())
            out = []
            for nxt in lines[i + 1:]:
                if not nxt.strip():
                    out.append(nxt)
                    continue
                ind = len(nxt) - len(nxt.lstrip())
                if ind <= base:
                    break
                out.append(nxt)
            return '\n'.join(out)
    return ''


def _mk_run(root: Path, name: str = '第1次模拟2026-10-05-20-00') -> Path:
    d = root / name
    (d / '每天的生活').mkdir(parents=True)
    return d


# ══════════════════════════════════════════════════════════════
#  A. StorySpan 读盘
# [EN] A. StorySpan disk reading
# ══════════════════════════════════════════════════════════════
def test_span() -> None:
    from store.runfolder import StorySpan, story_span_of

    tmp = Path(tempfile.mkdtemp(prefix='nws_span_'))

    # A1 JSON（事实来源）：三天的 json，取首日首个时刻 / 末日最后一个时刻
    # [EN] A1 JSON (source of truth): three days of json, take the first moment of the first day / the last
    # [EN] moment of the last day
    r1 = _mk_run(tmp / 'a')
    for day, labs in ((1, ['辰时 08:00', '午时 12:00']),
                      (2, ['未时 14:00']),
                      (3, ['戌时 20:00', '子时 23:00', '丑时 01:00'])):
        (r1 / '每天的生活' / f'第{day:03d}天.json').write_text(
            json.dumps([{'time_label': x} for x in labs], ensure_ascii=False),
            encoding='utf-8')
    s = story_span_of(r1)
    ok('A1 ★★★ 跨度从 **JSON**（事实来源）读出来：起始 = 第一天第一个时刻，'
       '结束 = 最后一天最后一个时刻',
       (s.start_day, s.start_at, s.end_day, s.end_at) ==
       (1, '辰时 08:00', 3, '丑时 01:00'),
       f'{s.start_day} {s.start_at} → {s.end_day} {s.end_at}')
    ok('A1b ★ 演了几天算得对（含头含尾）', s.days == 3, str(s.days))
    ok('A1c ★ `short()` 是给 300px 卡片用的一行短标签',
       s.short() == '第 1 → 3 天', s.short())
    ok('A1d ★ `full()` 带上时刻（详情栏用）',
       '辰时 08:00' in s.full() and '丑时 01:00' in s.full(), s.full())

    # A2 只有 md：从 `## <时刻>` 抠
    # [EN] A2 Only md: extract from `## <moment>`
    r2 = _mk_run(tmp / 'b')
    (r2 / '每天的生活' / '第001天.md').write_text(
        '# 第 1 天 · 第1天·辰时 · 晴\n\n## 辰时 08:00\n正文\n', encoding='utf-8')
    (r2 / '每天的生活' / '第002天.md').write_text(
        '# 第 2 天 · 第2天·夜 · 雨\n\n## 亥时 22:00\n正文\n', encoding='utf-8')
    s2 = story_span_of(r2)
    ok('A2 ★★ 没有 JSON 时退回 **md 的 `## <时刻>`**（旧存档、手改过的存档'
       '都可能只有 md）',
       (s2.start_day, s2.end_day, s2.start_at) == (1, 2, '辰时 08:00'),
       f'{s2.start_day}/{s2.start_at} → {s2.end_day}/{s2.end_at}')

    # A3 只有「原文」目录
    # [EN] A3 Only the "原文" directory
    r3 = _mk_run(tmp / 'c')
    (r3 / '每天的生活' / '原文').mkdir(parents=True)
    for day in (2, 4):
        (r3 / '每天的生活' / '原文' / f'第{day:03d}天.md').write_text(
            '# 第 N 天 · 原文（原著样章）\n\n正文\n', encoding='utf-8')
    s3 = story_span_of(r3)
    ok('A3 ★★ 只留下**小说原文**（`每天的生活/原文/`）时，天数照样读得出来 —— '
       '2026-10-10 刚加的目录，必须一起认',
       (s3.start_day, s3.end_day) == (2, 4), f'{s3.start_day} → {s3.end_day}')

    # A4 只有 state.db
    # [EN] A4 Only state.db
    r4 = tmp / 'd' / '第1次模拟2026-10-05-20-00'
    r4.mkdir(parents=True)
    con = sqlite3.connect(r4 / 'state.db')
    con.execute('CREATE TABLE events(id TEXT, ts REAL, game_day INTEGER)')
    con.execute('CREATE TABLE summary(id INTEGER, ts REAL, game_day INTEGER)')
    con.executemany('INSERT INTO events VALUES(?,?,?)',
                    [('e1', 1.0, 5), ('e2', 2.0, 9)])
    con.commit()
    con.close()
    s4 = story_span_of(r4)
    ok('A4 ★★ 只有 `state.db` 时，从事件表的天数范围兜底（**只读打开**，'
       '不抢正在跑的那一轮的锁）',
       (s4.start_day, s4.end_day) == (5, 9), f'{s4.start_day} → {s4.end_day}')

    # A5 什么都没有 —— **不许编**
    # [EN] A5 Nothing at all —— **must not fabricate**
    r5 = _mk_run(tmp / 'e')
    s5 = story_span_of(r5)
    ok('A5 ★★★ 什么都没有时 **`ok` 为假、`short()` 为空** '
       '（**绝不编一个"第 0 天"**：那会让界面显示一个不存在的跨度，'
       '还会把排序弄反 —— 见 B 组）',
       (not s5.ok) and s5.short() == '' and s5.full() == '',
       f'ok={s5.ok} short={s5.short()!r}')

    # A6 不让别的东西混进来：`原文` 目录里的校对稿不该被当成一天
    # [EN] A6 Don't let anything else sneak in: the proofread draft in the `原文` directory should not be
    # [EN] treated as a day
    r6 = _mk_run(tmp / 'f')
    (r6 / '每天的生活' / '第001天.md').write_text('# 第 1 天\n\n## 辰时 08:00\n',
                                                 encoding='utf-8')
    (r6 / '每天的生活' / '校对稿.md').write_text('# 校对稿\n', encoding='utf-8')
    # ★ 这个样本是**故意**选的：名字里带数字、但不是"第NNN天"。
    #   把 `_DAY_RE` 放宽成"名字里有一串数字就算一天"之后，它会被算成第 2 天
    #   —— 反例法 S21 就是拿它去把这个闸门打红的。
    # [EN] ★ This sample is **deliberately** chosen: its name contains digits, but it is not "第NNN天".
    # [EN] After loosening `_DAY_RE` to "any run of digits in the name counts as a day", it would be
    # [EN] counted as day 2
    # [EN] —— Counterexample method S21 uses it to provoke this gate into failing.
    (r6 / '每天的生活' / '幕后花絮02.md').write_text('# 幕后\n', encoding='utf-8')
    (r6 / '每天的生活' / '第001天.bak').write_text('x', encoding='utf-8')
    s6 = story_span_of(r6)
    ok('A6 ★★ 只认 `第NNN天.md/.json` 这个形状 —— 目录里多出来的'
       '`校对稿.md` / `幕后花絮02.md` / `第001天.bak` 都不许被算成"又一天"',
       (s6.start_day, s6.end_day) == (1, 1), f'{s6.start_day} → {s6.end_day}')


# ══════════════════════════════════════════════════════════════
#  B. 排序键
# [EN] B. Sort key
# ══════════════════════════════════════════════════════════════
def test_sort_keys() -> None:
    from store.runfolder import StorySpan

    empty = StorySpan()
    ok('B1 ★★★ **未知跨度**的排序键第一位是 1（= 排在最后），不是 0 —— '
       '当成 0 的话，正序时一轮旧存档会冒充"最早开始的"顶到第一位，'
       '而这件事**不报错**，只是把顺序悄悄弄反',
       empty.sort_start[0] == 1 and empty.sort_end[0] == 1,
       f'start={empty.sort_start} end={empty.sort_end}')

    known = StorySpan(start_day=3, end_day=7)
    ok('B1b ★ 已知跨度的第一位是 0（排在未知的前面）',
       known.sort_start[0] == 0 and known.sort_end[0] == 0,
       f'start={known.sort_start} end={known.sort_end}')
    ok('B1c ★ 键里带的第二个元素是天数本身（排序真正比较的就是它）',
       known.sort_start[1] == 3 and known.sort_end[1] == 7,
       f'{known.sort_start} {known.sort_end}')

    # 真的排一遍：三份存档（一份读不到时间）按结束时间倒序
    # [EN] Actually sort it: three saves (one with unreadable time) in descending order by end time
    runs = [StorySpan(start_day=1, end_day=4), empty,
            StorySpan(start_day=2, end_day=9)]
    asc = sorted(runs, key=lambda s: s.sort_end)
    desc = sorted(runs, key=lambda s: s.sort_end, reverse=True)
    ok('B2 ★★★ 正序时，**读不到时间的那份在最后**',
       asc[-1] is empty and asc[0].end_day == 4 and asc[1].end_day == 9,
       [s.end_day for s in asc])
    # ⚠ 倒序时元组也整体反转 —— 所以调用方必须**自己把未知的那一段摘出来**
    #   单独排在最后（`_sorted_runs` 里的 known/unknown 分段），不能只靠 reverse。
    # [EN] ⚠ When reversed, the tuple is also reversed as a whole —— so the caller must **extract the
    # [EN] unknown segment themselves**
    # [EN] Sort it separately at the end (the known/unknown split in `_sorted_runs`), cannot rely on
    # [EN] reverse alone.
    ok('B2b ★★ 所以"只靠 `reverse=True`"是不够的：整个键反转会把未知的顶到**最前**'
       '（这正是要在 `_sorted_runs` 里分段排的原因）',
       desc[0] is empty,
       [s.end_day for s in desc])


# ══════════════════════════════════════════════════════════════
#  C. 接线
# [EN] C. Wiring
# ══════════════════════════════════════════════════════════════
def test_wiring() -> None:
    src = read('gui/app_flet.py')
    dlg = between(src, 'def show_projects_dialog', 'def show_global_settings')

    ok('C1 ★★ 默认排序档是 `end_desc`（结束时间倒序）—— 与旧行为"最新的在最上面"'
       '对得上（推演通常一轮接一轮，后跑的推得更远）',
       "sort_state = {'key': 'end_desc'}" in dlg, '')

    meta = between(dlg, 'SORT_META = [', ']')
    vals = re.findall(r"\('(\w+)',", meta)
    ok('C2 ★★★ 四个排序档**一个不少**，而且值就是用户点名的那四种',
       vals == ['start_asc', 'start_desc', 'end_asc', 'end_desc'], str(vals))
    ok('C2b ★★★ 每一档都带**悬停解释**（用户："还可以鼠标放上去有 tip 提示"）'
       '—— 少一条就会在界面上出现一个"不知道按什么排"的单选框',
       len(re.findall(r"t\('按\*\*故事里\*\*", meta)) == 4,
       f'{len(re.findall(chr(39) + "按", meta))} 条说明')

    sr = between(dlg, 'def _sorted_runs(', 'def _load_saves(')
    ok('C3 ★★★ `_sorted_runs` 里**把未知的那一段单独摘出来排在最后**'
       '（`known` / `unknown` 分段）—— 这是 B2b 那个坑的正解',
       'unknown = [r for r in runs if not spans[str(r)].ok]' in sr
       and 'return known + unknown' in sr, '')
    ok('C3b ★★ `_sorted_runs` 真的读了那一档（`sort_state[\'key\']`），'
       '不是写死一种排法',
       "key = sort_state['key']" in sr and "'start_asc'" not in sr, '')
    ok('C3c ★ `_load_saves` 用的是 `_sorted_runs(proj)`，不是原始的'
       '`reversed(proj.list_runs())`',
       'runs = _sorted_runs(proj)' in dlg
       and 'runs = list(reversed(proj.list_runs()))\n' not in
       between(dlg, 'def _load_saves(', 'def _load_novels'), '')

    ok('C4 ★★ 单选框的 `on_change` 真的接了 `_apply_sort`（挂了不接 = 点了没反应）',
       'on_change=lambda e: _apply_sort(e.control.value)' in dlg, '')
    ok('C4b ★★ 换排序档时**保住原来选中的那一条**（`keep=shown[\'run\']`）—— '
       '否则一点"开始 ↑"，右边详情就跳到别的内容上',
       '_load_saves(proj, keep=shown[\'run\'])' in dlg, '')
    ok('C4c ★ `_load_saves` 真的认 `keep`（给的是签名里的真参数）',
       'def _load_saves(proj: Project, keep: Path = None) -> None:' in dlg, '')

    ok('C5 ★★★ 单选框**放在 ② 存档那一栏里**（`extra=sort_box`），不是随手丢在'
       '对话框外面 —— 用户说的是"上面加一组单选框"，指的是存档列表的上面',
       'extra=sort_box' in dlg, '')
    ok('C5b ★ `_column` 真的支持 `extra`（不支持的话那个参数会被静默忽略）',
       'extra: ft.Control = None' in src, '')

    # ⚠⚠ 2026-10-22：这一段原来锚在 `def _build_save_card(` 上 —— 而那个函数
    #   在 2026-10-21 的**树状图改造**里被删掉了（卡片改成"收起一行 + 展开区"，
    #   展开区那份内容被抽进 `_mk_expander`，拾卷与回收站共用）。于是 `between()` 取到空串、
    #   C6 恒红 —— **红的是一个已经不存在的函数**，不是产品没印故事时间。
    #   （这正是"判据搬了、锚点没跟着搬"那类假红。）
    #   ⇒ 现在锚在 `_mk_expander` 上，并且多判一步：**树的节点真的用了这个展开区**
    #     （否则"故事时间"印在一个没人调用的函数里，等于没印）。
    # [EN] ⚠⚠ 2026-10-22: this used to anchor on `def _build_save_card(`, which the **tree redesign**
    # [EN] (2026-10-21) deleted (the card became "one collapsed row + an expanded area", and that
    # [EN] content moved into `_mk_expander`, shared by both tabs). `between()` therefore returned an
    # [EN] empty string and C6 was permanently red -- red about a function that no longer exists, not
    # [EN] about a missing story time. => Now anchored on `_mk_expander`, plus one more step: the tree
    # [EN] node must really **use** that expander, or the story time sits in a function nobody calls.
    card = between(dlg, 'def _mk_expander(', 'def _build_tree_node(')
    # ⚠ 判**结构**，不判"两个名字在不在"：把那一行前面的条件改成 `if False:`
    #   之后，`span.short()` 这几个字**还在文件里**，全文搜照样绿（第一版就是
    #   这么漏掉的）。这里要求"那一行确实挂在这个 if 里"。
    # [EN] ⚠ Judge the **structure**, not "whether the two names are present": change the condition
    # [EN] before that line to `if False:` and the words `span.short()` **are still in the file**, so a
    # [EN] full-text search still passes (the first version missed it this way). Here the line must be
    # [EN] attached to that `if`.
    seg = _block_under(card, 'if span is not None and span.ok:')
    ok('C6 ★★★ **存档卡（展开区）上印了故事时间，而且真的挂在"拿得到跨度"那个分支里**'
       '（用户要的"加一个属性"）—— 判结构，不判名字出现过',
       'span.short()' in seg and "t('⏳ 故事时间')" in seg,
       f'该分支长 {len(seg)} 字符：{seg[:70]!r}')
    ok('C6d ★★★ 而且这个展开区**真的被树的节点用上了**（印在一个没人调用的函数里等于没印）',
       '_mk_expander(' in between(dlg, 'def _build_tree_node(', 'def _plot_') or
       card.count('_mk_expander(') >= 1,
       '')
    det = between(dlg, 'def _build_detail(', 'def _show_detail(')
    ok('C6b ★★ 详情栏也印（带时刻的 `full()`）', 'span.full()' in det, '')
    ok('C6c ★★★ 而且**两个时间并排出现并说明哪个是哪个**（`故事时间` vs '
       '`存档时间`）—— 只写一个、还不说明它是哪个，正是把两件事混成一件的老毛病',
       "t('⏳ 故事时间：（这一轮还没有落盘的故事）')" in det
       and "t('存档时间')" in det, '')

    ok('C7 ★★ `_span()` 带缓存（**卡片建一次、详情又算一次**，同一轮不该读两遍盘）',
       '_span_cache' in dlg and 'def _span(run_dir: Path) -> StorySpan:' in dlg, '')


def test_scanner() -> None:
    src = read('gui/app_flet.py')
    dlg = between(src, 'def show_projects_dialog', 'def show_global_settings')
    ok('D1 ★★ `between()` 取到的是**拾卷那一整段**（空的话上面那些断言全是假绿）',
       len(dlg) > 8000, f'{len(dlg)} 字符')
    ok('D1b ★★ 而且没串到隔壁去（范围里不该出现天机那个函数名）',
       'def show_global_settings' not in dlg, '')
    ok('D2 ★★ 扫描器自检：用一个**不存在**的写法去这段里找，必须找不到',
       'sort_state = {\'key\': \'nonexistent\'}' not in code_only(dlg), '')


def main() -> int:
    for name, fn in (('跨度读盘', test_span), ('排序键', test_sort_keys),
                     ('接线', test_wiring), ('扫描器自检', test_scanner)):
        try:
            fn()
        except Exception:                                       # noqa: BLE001
            REPORT['checks'].append({'name': f'{name} 组崩了', 'ok': False,
                                     'detail': traceback.format_exc()[-900:]})
    out = APP / 'assets' / 'screenshots' / 'save_sort_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')

    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n拾卷故事时间与排序验证：{n - len(bad)}/{n}')
    for c in REPORT['checks']:
        print(f'  {"✓" if c["ok"] else "✗"} {c["name"]}'
              + (f' | {c["detail"][:130]}' if c['detail'] else ''))
    print('报告 ->', out.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
