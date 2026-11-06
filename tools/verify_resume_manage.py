# -*- coding: utf-8 -*-
"""真机验证：拾卷能**删存档 / 删小说**、卡片**水平沾满**、文字**按 Markdown 渲染**、
两边**都有滚动条**（v1.35）。

用户原话（2026-10-05）：
「拾卷里我希望有删除存档以及删除小说的功能，而不是一直增加；另外拾卷里左侧的卡片
我希望一直水平沾满这个表格；而且里面如果有文字的话请把 Markdown 正确渲染；
右侧的内容也是要正确渲染 markdown；而且**过程请带下拉条**。」

所以判据分两半：

**A 纯逻辑**（不起界面，快）——
  · `md_excerpt()` **不切坏格式**：表格要么整张留、要么整张丢，绝不半截；
  · 丢本机绝对路径行（`〔图〕…C:\\…`，`ft.Markdown` 只认相对路径，留着就是一行乱码）；
  · `human_size()` 说人话；
  · **删除护栏**：项目根之外 / 没有 `.nwsproj` / 不是存档目录 → **必须拒绝**。
  · ★★ 2026-10-07 加 **D 组**：**`state.db` 开着时也搬得走**。
    用户报「最后一个存档无法删除」—— 现场 `已删除备份/` 里有 4 个同名存档备份，
    后 3 个只剩 7 个文件（`shutil.move` 回退成"复制+删除"的指纹）。
    根因是推演用的 sqlite 就在运行文件夹里、而连接一直没关：
    Windows 上句柄开着 → 目录改不了名 → 复制进备份、源删不掉。
    这一组用**真的装配出来的 DB**（不是替身）走完整删除链路。
    这四条是"删错了"和"拒得对"的分界线，比"能删掉"更值钱。

**B 真机**（开界面）——
  · 拾卷打开后左右两栏的 `scroll` 都是 `ADAPTIVE`（桌面下常显的滚动条）；
  · 卡片真的**水平占满**（像素：把左栏涂青、第一张卡涂品红，量两者的相对位置，
    要求卡片宽度 ≥ 可视宽的 85%，且右边留出的**车道 ≥ 8px** —— 车道窄了
    滚动条就会压在最右边那列字上）；
  · 卡片摘要与右侧详情里**真的有 `ft.Markdown`**（不是纯文本）；
  · 点卡片 → 详情换成 Markdown 正文；点 🗑 → 弹**确认框**（写清了名字/路径/文件数）；
  · 确认 → 目录**真的从磁盘上消失**、列表刷新、消息框里有回执；
  · 删整本小说 → 项目文件夹消失，剩下还有项目时**拾卷自己重新弹出来**。

跑法：
    .venv\\Scripts\\python.exe tools/verify_resume_manage.py
产出：
    assets/screenshots/resume_manage_*.png
    assets/screenshots/resume_manage_report.json

English:
Real-machine verification: Shijuan can **delete saves / delete novels**, the card is
**horizontally filled**, text is **rendered as Markdown**,
and **both sides have scrollbars** (v1.35).
User's exact words (2026-10-05):
"I want Shijuan to have the ability to delete saves and delete novels, instead of just adding
forever; also the left-side card in Shijuan
I want it to always be horizontally filled across this table; and if there is text inside,
please render Markdown correctly;
the right-side content must also render markdown correctly; and **the process should have a
dropdown bar**."
So the criteria are split into two halves:
**A pure logic** (no GUI started, fast) ——
  · `md_excerpt()` **must not break formatting**: a table is either kept whole or dropped whole, never half;
  · drop local absolute-path lines (`〔图〕…C:\\…`, `ft.Markdown` only recognizes relative paths, keeping them is one line of garbage);
  · `human_size()` speaks plainly;
  · **deletion guardrails**: outside the project root / no `.nwsproj` / not a save directory → **must refuse**.
  · ★★ 2026-10-07 add **group D**: **it can still be moved while `state.db` is open**.
    User reported "the last save cannot be deleted" —— on site, `已删除备份/` had 4 same-named save backups,
    the last 3 had only 7 files left (the fingerprint of `shutil.move` falling back to "copy + delete").
    Root cause is that the sqlite used for the scenario lives in the running folder, and the connection was never closed:
    on Windows with the handle open → the directory cannot be renamed → copied into the backup, the source cannot be deleted.
    This group uses a **really assembled DB** (not a stand-in) to walk the complete deletion chain.
    These four entries are the dividing line between "deleted wrongly" and "refused correctly", worth more than "can delete".
**B real machine** (GUI started) ——
  · after Shijuan opens, the `scroll` of both left and right columns is `ADAPTIVE` (scrollbars always visible on desktop);
  · the card really **fills horizontally** (pixels: paint the left column cyan, the first card magenta, measure their relative positions,
    require card width ≥ 85% of visible width, and the **gutter ≥ 8px** left on the right —— if the gutter is narrow
    the scrollbar will press onto the text in the rightmost column);
  · the card summary and right-side detail really contain `ft.Markdown` (not plain text);
  · click a card → the detail switches to the Markdown body; click 🗑 → a **confirmation dialog** pops up (with name/path/file count spelled out);
  · confirm → the directory **really disappears from disk**, the list refreshes, and there is an receipt in the message box;
  · delete a whole novel → the project folder disappears, and if projects remain, **Shijuan pops itself back up**.
How to run:
    .venv\\Scripts\\python.exe tools/verify_resume_manage.py
Output:
    assets/screenshots/resume_manage_*.png
    assets/screenshots/resume_manage_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402
from PIL import Image  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

from gui.app_flet import (NovelWorldApp, md_excerpt,  # noqa: E402
                          SAVE_GUTTER, SAVE_COL_W, DLG_W)
from i18n import set_lang, t  # noqa: E402
from store.project import (Project, archive_project_dir, archive_run_dir,  # noqa: E402
                           folder_stats, human_size, trash_dir_for)

MAGENTA = (0xff, 0x00, 0xff)
CYAN = (0x00, 0xff, 0xff)

# 带表格 + 粗体 + 本机绝对路径的日档样本 —— 专门用来试"截断会不会切坏格式"
# [EN] Daily archive sample with table + bold + local absolute path -- specifically used to test
# [EN] "whether truncation breaks formatting"
DAILY_MD = """# 第 1 天 · 第1天·辰时 · 晴
> 在场：主角、柳娘  张力：0.30

## 辰时 08:01
**场景** 茶肆

〔图〕茶肆  C:\\Users\\someone\\Projects\\某书\\插画\\场景_茶肆.png

▸ 出场 主角（已在场）
※ 主角 · 茶肆掌柜，话少。

〔同时〕
- 主角｜擦柜台
- 柳娘｜推门进来

| 人物 | 动作 | 张力 |
|------|------|------|
| 主角 | 擦柜台 | 0.30 |
| 柳娘 | 推门 | 0.45 |

后面还有很长很长的一段叙事，用来把摘要撑过 budget，
好看看截断的时候会不会把上面的表格切成半张。
再补一句，再补一句，再补一句，再补一句，再补一句。
"""


def count_color(png: Path, rgb, tol: int = 30) -> list:
    """返回命中该颜色的像素坐标（步长 2，够用且快）。
        English:
    Return the pixel coordinates that hit that color (step 2, sufficient and fast).
    """
    im = Image.open(png).convert('RGB')
    px = im.load()
    W, H = im.size
    hits = []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            c = px[x, y]
            if all(abs(c[i] - rgb[i]) <= tol for i in range(3)):
                hits.append((x, y))
    return hits


async def main(page: ft.Page):
    VU.patch_flat_background()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_rm_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    items: list = []
    report: dict = {}

    def ok(name: str, cond, detail: str = '') -> bool:
        items.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
        if not cond:
            print(f'FAIL  {name}   [{detail}]')
        return bool(cond)

    async def shot(fname: str) -> Path:
        page.update()
        await asyncio.sleep(0.6)
        p = OUT / fname
        p.write_bytes(await page.take_screenshot())
        return p

    projects_root_ref: list = []      # 真机那段要拿它算「已删除备份」在哪
    # [EN] The real-device section needs it to compute where the "deleted backup" is

    def make_run(proj: Project, folder: str) -> Path:
        """造一轮存档（带 任务介绍 / 每天的生活 / 运行小结，都是真 Markdown）。
                English:
        Generate one round of saves (with mission briefing / daily life / run summary, all real
        Markdown).
        """
        run = proj.root / folder
        (run / '每天的生活').mkdir(parents=True, exist_ok=True)
        (run / '每天的生活' / '第001天.md').write_text(DAILY_MD, encoding='utf-8')
        (run / '运行小结.md').write_text(
            '# 运行小结\n\n- **轮次**：第 1 次\n- **用时**：8 秒\n\n一切正常。\n',
            encoding='utf-8')
        (run / '任务介绍.md').write_text(
            '# 任务介绍\n\n- **项目**：拾卷验证\n- **类型**：玄幻修仙\n',
            encoding='utf-8')
        return run

    try:
        # ══════════ A. 纯逻辑：md_excerpt / human_size / 删除护栏 ══════════
        # [EN] ══════════ A. Pure logic: md_excerpt / human_size / delete guardrails ══════════
        ex = md_excerpt(DAILY_MD, 260)
        # 末尾那个 `…` 是 md_excerpt 自己加的省略标记，不算"抄错的原文"
        # [EN] The trailing `…` is the ellipsis marker added by md_excerpt itself, not part of the "mis-copied
        # [EN] original text"
        kept_lines = [ln for ln in ex.splitlines()
                      if ln.strip() and ln.strip() != '…']
        ok('A：摘要不切在行中间（留下的每一行都能在原文里逐字找到）',
           all(ln in DAILY_MD for ln in kept_lines), repr(ex[-40:]))
        body = [ln for ln in ex.splitlines() if ln.strip()]
        tbl = [ln for ln in body if ln.strip().startswith('|')]
        ok('A：表格要么整张留、要么整张丢（不留半截表格）',
           len(tbl) == 0 or len(tbl) >= 3, f'表格行 {len(tbl)} 行')
        ok('A：摘要丢掉了 `〔图〕` 那行（本机绝对路径，Markdown 渲染不出来）',
           '〔图〕' not in ex, repr(ex[:60]))
        ok('A：超长时有省略号', ex.rstrip().endswith('…'), repr(ex[-8:]))
        ex2 = md_excerpt(DAILY_MD, 110, skip_leading_heads=True)
        ok('A：skip_leading_heads 跳掉日档开头的大标题与引言',
           not ex2.lstrip().startswith(('#', '>')) and '**场景**' in ex2,
           repr(ex2[:40]))
        ok('A：卡片用的摘要比详情短（小地方别塞长文）',
           len(md_excerpt(DAILY_MD, 110, skip_leading_heads=True))
           < len(md_excerpt(DAILY_MD, 1500)), '')
        ok('A：短文本原样返回、不加省略号',
           md_excerpt('一句话。', 200) == '一句话。', md_excerpt('一句话。', 200))
        ok('A：空文本不炸', md_excerpt('', 200) == '' and md_excerpt(None, 200) == '')

        ok('A：human_size 说人话', human_size(0) == '0 B'
           and human_size(2048).endswith('KB') and human_size(5 * 1024 ** 2).endswith('MB'),
           f'{human_size(0)} / {human_size(2048)} / {human_size(5 * 1024 ** 2)}')

        set_lang('en')
        miss_en = [k for k in ('确认删除', '删除这个存档', '删除这本小说',
                               '删掉这一轮存档？', '删掉整本小说？', '没能删掉：{why}')
                   if t(k) == k]
        set_lang('zh')
        ok('A：删除流程的文案中英都有', not miss_en, str(miss_en))

        projects_root_ref.append(CFG.projects_dir())
        proj_a = Project.create_new(CFG.projects_dir(), '拾卷验证')
        proj_b = Project.create_new(CFG.projects_dir(), '待删项目')
        for i, folder in enumerate(('第1次模拟2026-01-01-00-00',
                                    '第2次模拟2026-01-02-00-00',
                                    '第3次模拟2026-01-03-00-00',
                                    '第4次模拟2026-01-04-00-00'), 1):
            make_run(proj_a, folder)
        run_b = make_run(proj_b, '第1次模拟2026-01-05-00-00')

        n_files, size_b = folder_stats(proj_a.root)
        ok('A：folder_stats 数得出文件数与体积（确认框靠它说清"删掉的是多少东西"）',
           n_files >= 8 and size_b > 0, f'{n_files} 个文件 / {human_size(size_b)}')

        # —— 护栏：这四条必须**拒绝** ——
        # [EN] -- Guardrails: these four must be **rejected** --
        roots = CFG.projects_dir()
        bad1, why1 = archive_project_dir(roots, roots)               # 项目根自己
        # [EN] The project root itself
        ok('A：拒绝删项目根自己（不是"删了才知道"）', not bad1 and roots.exists(), why1)
        outside = tmp / 'outside'
        outside.mkdir(parents=True, exist_ok=True)
        bad2, why2 = archive_project_dir(outside, roots)             # 项目根之外
        # [EN] Outside the project root
        ok('A：拒绝删项目根之外的目录', not bad2 and outside.exists(), why2)
        nofile = roots / '不是项目'
        nofile.mkdir(parents=True, exist_ok=True)
        bad3, why3 = archive_project_dir(nofile, roots)              # 没有 .nwsproj
        # [EN] No .nwsproj
        ok('A：认不出的目录（没有 .nwsproj）拒绝删', not bad3 and nofile.exists(), why3)
        bad4, why4 = archive_run_dir(proj_a.settings_dir, proj_a.root)   # 名字不像存档
        # [EN] Name doesn't look like an archive
        ok('A：名字不像存档的目录拒绝删（别删掉 设定集/）',
           not bad4 and proj_a.root.exists(), why4)
        bad5, why5 = archive_run_dir(proj_b.root / '第1次模拟2026-01-05-00-00', proj_a.root)
        ok('A：不是该项目的直接子目录 → 拒绝', not bad5, why5)

        # —— 窗口标题带着「界面源码最后改动时间」——
        # 用户多次对着一个几小时前启动的旧窗口说"还是没修好"：模块只在启动时
        # 加载一次，改 `.py` 不重启毫无变化，而他没法分辨眼前窗口的新旧。
        # [EN] -- Window title carries "UI source last-modified time" --
        # [EN] Users repeatedly tell an old window launched hours ago "still not fixed": the module only loads
        # [EN] at startup
        # [EN] And reloads once; editing `.py` without restarting changes nothing, and they can't tell whether
        # [EN] the window in front of them is old or new.
        import config as _cfg
        title = str(getattr(page, 'title', '') or '')
        stamp = _cfg.ui_build_stamp()
        ok('A：窗口标题里带「界面构建时间」（用来分辨窗口新旧）',
           bool(stamp) and stamp in title, f'title={title!r} stamp={stamp!r}')
        ok('A：构建时间取自界面源码的 mtime（自动算，不靠人记着改版本号）',
           stamp == _cfg.window_title().split('界面 ')[-1].strip()
           if '界面 ' in _cfg.window_title() else False, _cfg.window_title())

        # —— 「删除」其实是**移到「已删除备份」**（v1.36 的事故之后改成这样）——
        #    用户在新功能上线 5 分钟后删掉了自己整本书（那时是 rmtree、不进回收站、
        #    永久没了）。判据：① 搬得走；② 备份目录在**项目根之外**
        #    （放里面会被 `scan_projects` 的 rglob 又扫出来）；③ 原件真没了；④ 搬得回来。
        # [EN] -- "Delete" is actually **move to "deleted backup"** (changed to this after the v1.36 incident)
        # [EN] --
        # [EN] A user deleted their entire book 5 minutes after the new feature launched (at that time it was
        # [EN] rmtree, didn't go to recycle bin,
        # [EN] permanently gone). Criteria: ① it can be moved away; ② the backup directory is **outside the
        # [EN] project root**
        # [EN] (putting it inside would get it scanned again by `scan_projects`'s rglob); ③ the original is
        # [EN] really gone; ④ it can be moved back.
        probe_run = proj_a.root / '第2次模拟2026-01-02-00-00'
        moved, back = archive_run_dir(probe_run, proj_a.root, roots)
        ok('A：删存档 = 移进「已删除备份」（不是 rmtree）',
           moved and Path(back).exists() and Path(back).is_dir(), f'{back}')
        ok('A：备份目录在**项目根之外**（放里面会被 scan_projects 又扫出来）',
           not str(trash_dir_for(roots)).startswith(str(roots.resolve())),
           str(trash_dir_for(roots)))
        ok('A：搬走之后原件真的不在项目里了', not probe_run.exists(), str(probe_run))
        ok('A：搬进去的东西**还在磁盘上**',
           any((Path(back) / '每天的生活').glob('*.md')), back)
        import shutil as _sh
        _sh.move(back, str(probe_run))          # 搬回来，后面真机那段还要用这 4 轮
        # [EN] Move it back; the real-device section later still needs these 4 rounds
        ok('A：从备份里搬回来（可逆）', probe_run.exists(), str(probe_run))

        # ══════════ B. 真机（三栏：① 小说 / ② 存档 / ③ 存档内容）══════════
        # [EN] ══════════ B. Real device (three columns: ① novel / ② archive / ③ archive content) ══════════
        app._activate_project(proj_a)
        dlg = app.show_projects_dialog()
        page.update()
        await asyncio.sleep(0.9)
        ok('B：拾卷真的打开了',
           dlg is not None and bool(getattr(dlg, 'open', False)))

        texts = VU.all_texts(dlg)
        joined = ' | '.join(texts)
        # ① 三栏都在，而且**每栏都有一句说明**（三栏都窄，不写清就是三个认不出来的框）
        # [EN] ① All three columns present, and **each column has a caption** (all three columns are narrow;
        # [EN] without clear labels they're just three unrecognizable boxes)
        for ttl in ('① 小说', '② 存档', '③ 存档内容'):
            ok(f'B：有「{ttl}」这一栏（栏头）', any(ttl in x for x in texts), joined[:80])
        ok('B：① 栏写着"点一本，中间那栏就换成它的存档"',
           any('点一本' in x for x in texts), '')
        # ★★ 2026-10-10 改判（原判据钉的是栏头那句"最新的在最上面"）：
        #   那一轮给 ② 栏加了**排序单选框**（开始/结束 × 正序/倒序 四档，
        #   默认"结束时间倒序"）—— 于是"按什么排"不再由栏头那句**静态说明**
        #   承担，而是**由控件说了算**（悬停每个选项能看到它按什么排）。
        #   ⇒ 判据跟着改成"排序控件真的在界面上"：
        #     ① 有「排序」这个标签（`ft.Text`，`all_texts` 收得到）；
        #     ② 控件树里真的有 4 个 `ft.Radio`，值就是那四档。
        #     ⚠ `all_texts` 只收 `ft.Text`，**收不到 `ft.Radio.label`**（那是个
        #       str 字段），所以第 ② 条必须自己 walk 控件树 —— 只查标签会
        #       变成"有标题没控件"也绿（典型的弱判据）。
        # [EN] ★★ 2026-10-10 criteria change (the original criteria pinned the column header line "newest on
        # [EN] top"):
        # [EN] That round added a **sort radio group** to column ② (start/end × ascending/descending, four
        # [EN] options,
        # [EN] default "end time descending") -- so "sorted by what" is no longer carried by that **static
        # [EN] caption**
        # [EN] in the column header, but **decided by the control** (hovering each option shows what it sorts
        # [EN] by).
        # [EN] ⇒ The criteria changed accordingly to "the sort control really exists on the UI":
        # [EN] ① There's a "sort" label (`ft.Text`, receivable by `all_texts`);
        # [EN] ② The control tree really has 4 `ft.Radio`, with values exactly those four options.
        # [EN] ⚠ `all_texts` only collects `ft.Text`, **cannot receive `ft.Radio.label`** (that's a
        # [EN] str field), so item ② must walk the control tree itself -- checking only labels would
        # [EN] turn into "has title, no control" passing too (a typical weak criterion).
        _radios = [c for c in VU.walk(dlg)
                   if c.__class__.__name__ == 'Radio']
        _vals = {str(getattr(r, 'value', '') or '') for r in _radios}
        ok('B：② 栏说明还在（"点一条看右边"）',
           any('点一条看右边' in x for x in texts), '')
        ok('B：② 栏有**排序控件** —— 「排序」标签 + 4 个单选框'
           '（开始/结束 × 正序/倒序），顺序由控件说了算',
           any('排序' in x for x in texts)
           and _vals >= {'start_asc', 'start_desc', 'end_asc', 'end_desc'},
           f'标签={any("排序" in x for x in texts)} 单选框={sorted(_vals)}')
        ok('B：③ 栏写着"元信息、最近剧情、运行小结"',
           any('最近剧情' in x and '运行小结' in x for x in texts), '')
        # 顶部那个项目下拉框**没了**（用户要求换成列表）
        # [EN] The project dropdown at the top is **gone** (user asked to replace it with a list)
        ok('B：顶部那个"选择小说"下拉框已经删掉',
           not any('选择小说' in x for x in texts), '')

        novels = _novel_cards(dlg)
        ok('B：① 栏每本小说一张卡（卡数 == 项目数）',
           len(novels) == 2, f'{len(novels)} 张 / 2 本')
        nt = ' | '.join(VU.all_texts(novels[0])) if novels else ''
        ok('B：小说卡上**只有标题 + 创建时间**（用户点名"不需要太多东西"）',
           '创建 ' in nt and '轮存档' not in nt and '还没跑过' not in nt, nt[:80])
        ok('B：每本小说右边都有一个删除按钮（删整本的入口**在列表上**）',
           len([c for c in novels if _trash_of(c) is not None]) == len(novels),
           f'{len(novels)} 张卡')
        # ★ 2026-10-08 用户要求：「每个标签上加一个文件夹，放到删除按钮的**上面**
        #   （删除按钮放到第2行，文件夹按钮放到第一行最右边，两者稍微有点距离）」
        # [EN] ★ 2026-10-08 user request: "add a folder to each tab, placed **above** the delete button
        # [EN] (put the delete button on row 2, the folder button on the far right of row 1, with a bit of
        # [EN] spacing between them)"
        ok('B：每张小说卡上**都有一个「打开文件夹」按钮**（2026-10-08 新增）',
           len([c for c in novels if _folder_of(c) is not None]) == len(novels),
           f'{len(novels)} 张卡')
        # 「在上面」= 卡片里文件夹按钮所在的**行**排在删除按钮**前面**
        # （按控件树深度优先序比：行内顺序就是上下顺序）
        # [EN] "Above" = the **row** containing the folder button in the card comes **before** the delete
        # [EN] button
        # [EN] (compares by control-tree depth-first order: in-row order is vertical order)
        _card0 = novels[0]
        _order = list(VU.walk(_card0))
        _fb, _tb = _folder_of(_card0), _trash_of(_card0)
        ok('B：文件夹按钮排在删除按钮**上面**（第一行 / 第二行）',
           _fb is not None and _tb is not None
           and _order.index(_fb) < _order.index(_tb), '')
        # 点它 = 打开项目文件夹（**打桩**，不然真机跑起来会弹出资源管理器窗口）
        # [EN] Clicking it = open the project folder (**stubbed**, otherwise running on a real machine would
        # [EN] pop up an Explorer window)
        _opened: list = []
        _real_open = app._open_path
        try:
            app._open_path = lambda p: _opened.append(str(p))
            _folder_of(novels[0]).on_click(None)
            page.update()
            await asyncio.sleep(0.3)
            _want = str(getattr(novels[0], '_proj', None).root)
        finally:
            app._open_path = _real_open
        ok('B：点「打开文件夹」打开的是**那本小说自己的**项目文件夹'
           '（不是别本的、也不是项目根目录）',
           len(_opened) == 1 and _opened[0] == _want, str(_opened[:1]))
        ok('B：点「打开文件夹」**不会**弹删除确认框（两个按钮各管各的）',
           not any('删掉整本小说？' in x
                   for d in VU.open_dialogs(page) for x in VU.all_texts(d)), '')
        # 底部按钮行不该再有「删除这本小说」
        # [EN] The bottom button row should no longer have "delete this novel"
        bottom = [VU.text_of(c).strip() for c in VU.walk(dlg)
                  if type(c).__name__ in ('FilledButton', 'TextButton')]
        ok('B：底部的「删除这本小说」已经挪走（底部只留打开/关闭）',
           '删除这本小说' not in bottom and '打开选中项目' in bottom, str(bottom))

        # 默认选中的是"第一本"；要验的是 proj_a → 点它
        # [EN] The default selection is "the first book"; what to verify is proj_a → click it
        target_novel = next((c for c in novels
                             if getattr(c, '_proj', None) is not None
                             and c._proj.name == proj_a.name), novels[0])
        _body_of(target_novel).on_click(None)
        page.update()
        await asyncio.sleep(0.8)
        ok('B：点左栏那本书 → 中栏换成它的存档',
           len(_save_cards(dlg)) == len(proj_a.list_runs()),
           f'{len(_save_cards(dlg))} 张存档卡 / {len(proj_a.list_runs())} 轮')

        # 切书之后右栏**不能**被清成占位符
        # [EN] After switching books, the right column **must not** be cleared into a placeholder
        ph = t('（先在中间选一条存档）')
        ok('B：切书后 ③ 栏不是空态（而是最新那一轮的详情）',
           not any(ph in str(x) for x in VU.all_texts(dlg)), '')

        save_list = _find_list_view(dlg)
        # ★ 判据按**本意**写，别钉实现细节（2026-10-07 修）：
        #   原来断言 `scroll is ft.ScrollMode.ADAPTIVE` —— 那是**框架滚动条**的模式，
        #   而本项目是**自绘**细条（`mk_scroll_bar`）；为了让框架不再多画一根，
        #   套条时会把 `scroll` 改成 `HIDDEN`（用户报的"一粗一细两根条"）。
        #   于是这条断言因为一个**与它本意无关**的实现细节变红。
        #   本意是三条：① 这一栏能滚；② 车道留出来了（条不压字）；③ 条是自绘的那根。
        # [EN] ★ Write criteria by **intent**, don't pin implementation details (fixed 2026-10-07):
        # [EN] The original asserted `scroll is ft.ScrollMode.ADAPTIVE` -- that's the **framework scrollbar**'s
        # [EN] mode,
        # [EN] but this project uses a **self-drawn** thin bar (`mk_scroll_bar`); to keep the framework from
        # [EN] drawing another one,
        # [EN] when nesting the bar, `scroll` is set to `HIDDEN` (the "one thick one thin bar" the user
        # [EN] reported).
        # [EN] So this assertion turned red because of an implementation detail **unrelated to its intent**.
        # [EN] The intent is threefold: ① this column can scroll; ② the lane is reserved (the bar doesn't
        # [EN] overlap text); ③ the bar is the self-drawn one.
        _lane = getattr(getattr(save_list, 'padding', None), 'right', 0) or 0
        _thumb = None
        for _c in VU.walk(dlg):
            if isinstance(_c, ft.Stack) and len(getattr(_c, 'controls', []) or []) == 2 \
                    and isinstance(_c.controls[0], ft.ListView) \
                    and getattr(_c.controls[1], 'width', None) == 4:
                _thumb = _c.controls[1]
                break
        ok('B：② 栏能滚动 + 车道留出来了 + 挂着自绘细条',
           save_list is not None
           and getattr(save_list, 'scroll', None) is not None      # ① 能滚
           and _lane >= SAVE_GUTTER                                # ② 车道
           and _thumb is not None,                                 # ③ 自绘条
           # [EN] ① Can scroll
           # [EN] ② Lane
           # [EN] ③ Self-drawn bar
           f'scroll={getattr(save_list, "scroll", None)} 车道={_lane} '
           f'bar={"有" if _thumb is not None else "无"}')

        cards = _save_cards(dlg)
        runs = proj_a.list_runs()
        ok('B：每一轮存档都有一张卡', len(cards) == len(runs),
           f'{len(cards)} 张 / {len(runs)} 轮')
        ok('B：卡片里的摘要按 Markdown 渲染',
           all(any(isinstance(x, ft.Markdown) for x in VU.walk(c)) for c in cards),
           '')
        md_val = next((m.value for m in VU.walk(cards[0]) if isinstance(m, ft.Markdown)), '')
        ok('B：卡片摘要丢掉了 `〔图〕` 那行（本机绝对路径渲染不出来）',
           '〔图〕' not in md_val and bool(md_val), repr(md_val[:40]))
        ok('B：每张存档卡都有一个删除按钮（图标按钮）',
           all(_trash_of(c) is not None for c in cards), '')
        # 删除按钮必须是正文那个可点容器的**兄弟**（点它不该顺带切详情）
        # [EN] The delete button must be a **sibling** of the body's clickable container (clicking it shouldn't
        # [EN] also switch details)
        body_node = _body_of(cards[0])
        nested = [c for c in VU.walk(body_node)
                  if any(isinstance(x, ft.Icon) for x in VU.walk(c))
                  and getattr(c, 'on_click', None) is not None]
        ok('B：🗑 不在正文那个可点容器里（点删除不会顺带切详情）',
           not nested, f'嵌在正文里的图标按钮 {len(nested)} 个')

        # ── 像素：卡片水平沾满 + 车道（标记色法，只动颜色不动几何）──
        # [EN] -- Pixels: card fills horizontally + lane (marker-color method, only changes color not geometry)
        # [EN] --
        save_panel = next((c for c in VU.walk(dlg)
                           if isinstance(c, ft.Container)
                           and isinstance(getattr(c, 'content', None), ft.Column)
                           and isinstance(getattr(c, 'width', None), int)
                           and c.width == SAVE_COL_W), None)
        save_panel.bgcolor = '#00ffff'
        cards[0].bgcolor = '#ff00ff'
        png = await shot('resume_manage_lane.png')
        save_panel.bgcolor = C_HOVER
        cards[0].bgcolor = C_PANEL
        page.update()
        mag = count_color(png, MAGENTA)
        cyan = count_color(png, CYAN)
        report['px_magenta'] = len(mag)
        report['px_cyan'] = len(cyan)
        if mag and cyan:
            mx0, mx1 = min(x for x, _ in mag), max(x for x, _ in mag)
            cx0, cx1 = min(x for x, _ in cyan), max(x for x, _ in cyan)
            fill = (mx1 - mx0) / max(1, (cx1 - cx0))
            lane = cx1 - mx1
            report.update({'card_span': [mx0, mx1], 'panel_span': [cx0, cx1],
                           'fill_ratio': round(fill, 3), 'lane_px': lane})
            ok('B：卡片水平沾满中栏（≥ 85% 可视宽）', fill >= 0.85,
               f'{mx1 - mx0}px / {cx1 - cx0}px = {fill:.2f}')
            ok('B：卡片右边留出了滚动条车道（≥ 8px）', lane >= 8, f'{lane}px')
            ok('B：卡片左端贴着栏的左内沿', abs(mx0 - cx0) <= 14,
               f'卡 x0={mx0} / 栏 x0={cx0}')
        else:
            ok('B：标记色法量到了卡片与中栏', False, f'{len(mag)} / {len(cyan)}')

        # ── 像素：**删除图标真的画在红底里**（用户报的"垃圾桶没在红色背景里"）──
        #    判据：找出屏幕上每一块朱砂（🗑 的红底），它的 bbox **里面**必须有
        #    浅色像素（纸白的图标字形）。字形跑到红底外面时，块内就是纯红。
        # [EN] -- Pixels: **delete icon is really drawn inside the red background** (the user-reported "trash
        # [EN] can not in the red background") --
        # [EN] Criterion: find every block of cinnabar on screen (the 🗑 red background); its bbox **must**
        # [EN] contain
        # [EN] light pixels (the paper-white icon glyph). When the glyph goes outside the red background, the
        # [EN] block is pure red inside.
        png2 = await shot('resume_manage_trash_icon.png')
        blocks, glyph_ok = _trash_icon_blocks(png2)
        report['trash_blocks'] = blocks
        ok('B：像素：每个删除图标都是"红底 **+ 红底里有字形**"',
           blocks >= 3 and glyph_ok == blocks,
           f'{blocks} 个红底，其中 {glyph_ok} 个里面有字形')

        # ── 点存档卡 → ③ 栏换成它的详情 ──
        # [EN] -- Click archive card → column ③ switches to its details --
        _body_of(cards[1]).on_click(None)
        page.update()
        await asyncio.sleep(0.6)
        det = [c for c in VU.walk(dlg)
               if isinstance(c, ft.ListView) and len(c.controls) > 3]
        ok('B：点存档卡 → ③ 栏换成详情', bool(det), str(len(det)))
        d_md = [m for c in det for m in VU.walk(c) if isinstance(m, ft.Markdown)]
        ok('B：③ 栏是 Markdown 正文（最近剧情 / 运行小结）', len(d_md) >= 2,
           f'{len(d_md)} 段')
        dj = ' '.join(m.value for m in d_md)
        ok('B：③ 栏里是真正文（不是"暂无…"占位）',
           '茶肆' in dj and '（暂无' not in dj, repr(dj[:50]))
        ok('B：③ 栏里的表格还在（整段喂给 Markdown）', '| 人物 |' in dj, repr(dj[-50:]))
        await shot('resume_manage_detail.png')

        # ── 删存档：确认框 → 搬进「已删除备份」 ──
        # [EN] -- Delete archive: confirmation dialog → move into "deleted backup" --
        n0 = len(VU.open_dialogs(page))
        # ⚠ 2026-10-26：点**最后一张**（叶子）。夹具这 4 轮没有 `来源.json`，血统是按序号
        #   **推断**出来的 ⇒ 第 1 轮是根，删它必然带走 3 个后代（`TRASH.descendants`，
        #   那是树语义的设计，确认框也写明了"下面还衍生着 3 轮"）。原来点 `cards[0]`
        #   再断言"少了一轮"，等于要求产品违背它自己的树语义。
        # [EN] ⚠ 2026-10-26: click the **last** card (a leaf). These 4 fixture rounds have no
        # [EN] `来源.json`, so lineage is **inferred** from the index => round 1 is the root and
        # [EN] deleting it necessarily takes 3 descendants (`TRASH.descendants`; that is tree
        # [EN] semantics by design, and the confirmation says "3 more below"). Clicking `cards[0]`
        # [EN] and then asserting "one round fewer" asked the product to contradict itself.
        _trash_of(cards[-1]).on_click(None)
        page.update()
        await asyncio.sleep(0.7)
        # ⚠ 2026-10-26 修：标题**两种都合法** —— 那一轮下面有子节点时，产品写的是
        #   「删掉这一轮和它下面的 3 轮？」（`_ask_delete_save` 里按 `kids` 二选一）。
        #   判据只认「删掉这一轮存档？」⇒ 一旦点到的恰好是有子节点的那一轮就
        #   `cdlgs` 为空 ⇒ 下一行 `cdlgs[-1]` 直接 IndexError，**整支判据崩在这里**，
        #   后面 C/D/E 全没跑（这正是记录了三个月的"56/60 已知红"）。
        #   判据要问的是"点 🗑 有没有弹确认框"，不是"标题恰好是哪一句"。
        # [EN] ⚠ Fixed 2026-10-26: **both titles are legal** -- when that round has children the
        # [EN] product writes "delete this round and the N below it?" (`_ask_delete_save` picks by
        # [EN] `kids`). The criterion accepted only one title => clicking a round that happens to
        # [EN] have children left `cdlgs` empty => the next line `cdlgs[-1]` raised IndexError and
        # [EN] **the whole criterion died there**, so C/D/E never ran (that was the long-recorded
        # [EN] "56/60 known-red"). What it must ask is "did clicking 🗑 open a confirmation?",
        # [EN] not "which exact sentence is the title".
        cdlgs = [d for d in VU.open_dialogs(page)
                 if any(x.startswith('删掉这一轮') for x in VU.all_texts(d))]
        ok('B：点 🗑 弹出确认框（不是直接删）', bool(cdlgs),
           f'{n0} → {len(VU.open_dialogs(page))}')
        if not cdlgs:
            # 崩在这里会让后面三组全不跑（"静默跳过"比红更坏）⇒ 明确报一条
            ok('B：确认框居然没弹出来（后面的删除判据无从谈起）', False,
               ' '.join(VU.all_texts(VU.open_dialogs(page)[-1]))[:120]
               if VU.open_dialogs(page) else '没有对话框')
        ctxt = VU.all_texts(cdlgs[-1]) if cdlgs else []
        cjoin = ' | '.join(ctxt)
        # ★ 2026-10-26：确认框的措辞按**现在**的实现量（原来钉的是 `路径：` / `备份目录：` /
        #   `搬回来` —— 那一版文案在改成"移到回收站"之后就没了，判据红的是它自己）。
        #   现在这一屏要说清三件事：**删的是哪一轮** / **多大** / **去了哪、能不能找回**。
        # [EN] ★ 2026-10-26: measure the confirmation against the **current** wording (the old one
        # [EN] pinned `路径：` / `备份目录：` / `搬回来`, which vanished when the flow became "move to
        # [EN] the recycle bin"). The screen owes three facts: **which round** / **how big** /
        # [EN] **where it goes and whether it can be recovered**.
        ok('B：确认框写出了**哪一轮**（存档名）',
           any('次模拟' in x for x in ctxt), cjoin[:90])
        ok('B：确认框写出了**多大**（文件数 + 体积）',
           any('个文件' in x for x in ctxt)
           and any(x.endswith('B') or ' KB' in x or ' MB' in x for x in ctxt), cjoin[:120])
        ok('B：确认框说明了**去哪儿 + 能不能找回**（回收站 / 找回）',
           any('回收站' in x for x in ctxt)
           and any(('找回' in x) or ('恢复' in x) for x in ctxt), cjoin[:120])
        ok('B：确认按钮是朱砂色', bool(cdlgs) and any(
            type(c).__name__ == 'FilledButton'
            and VU.text_of(c).strip() == '确认删除'
            and str(getattr(c, 'bgcolor', '')).lower() in ('#c02c22', 'c02c22')
            for c in VU.walk(cdlgs[-1])))
        await shot('resume_manage_confirm.png')

        before_runs = len(proj_a.list_runs())
        confirm_btn = next(c for c in VU.walk(cdlgs[-1])
                           if type(c).__name__ == 'FilledButton'
                           and VU.text_of(c).strip() == '确认删除')
        confirm_btn.on_click(None)
        page.update()
        await asyncio.sleep(1.2)
        after_runs = len(proj_a.list_runs())
        ok('B：确认后项目里真的少了一轮', after_runs == before_runs - 1,
           f'{before_runs} → {after_runs}')
        trashed = [p for p in trash_dir_for(projects_root_ref[0]).glob('*_存档_*')
                   if p.suffix != '.json']      # 旁注不算备份（见下面 D 组的说明）
        ok('B：那一轮在「已删除备份」里（不是被抹掉）', bool(trashed),
           str([p.name for p in trashed][:2]))
        ok('B：删完确认框收掉、拾卷还在（三栏就地刷新）',
           len(VU.open_dialogs(page)) == 1 and len(_save_cards(dlg)) == after_runs,
           f'{len(VU.open_dialogs(page))} 个对话框 / {len(_save_cards(dlg))} 张卡')
        msgs = [m['text'] for m in getattr(app, '_messages', [])]
        ok('B：消息框里有回执，并写明**搬到哪了**',
           any(('已把' in x and '存档' in x and ('回收站' in x or '已删除备份' in x))
               for x in msgs), str(msgs[-1:]))

        # ── 删整本：入口在左栏那本书上 + 手打书名 ──
        # [EN] -- Delete whole book: entry on that book in the left column + type the book name manually --
        novels = _novel_cards(dlg)
        nb = next(c for c in novels
                  if getattr(c, '_proj', None) is not None and c._proj.name == proj_b.name)
        _trash_of(nb).on_click(None)
        page.update()
        await asyncio.sleep(0.7)
        pcd = [d for d in VU.open_dialogs(page)
               if any('删掉整本小说？' in x for x in VU.all_texts(d))]
        ok('B：左栏书上的 🗑 弹出"删整本"的确认框', bool(pcd),
           str(len(VU.open_dialogs(page))))
        pjoin = ' | '.join(VU.all_texts(pcd[-1])) if pcd else ''
        ok('B：确认框点明了「设定集、肖像、存档一起删」',
           '设定集' in pjoin and '存档' in pjoin, pjoin[:100])
        # ★★ 2026-10-26 判据反转（产品被用户明确改过，判据没跟上）：
        #   2026-10-21 用户原话「后续修改之后，拾卷里删除小说 不需要输入名字 会被提示
        #   是否删除 并且告知会被移动到回收站」⇒ 现在**故意没有**手打输入框，删整本走
        #   「是/否 + 说明会进回收站」，因为回收站可以整本恢复（"弄错了不痛"就不该再加闸）。
        #   原来的三条判据（要手打 / 有输入框 / 没打时按钮是灰的）在这一版**必然全红**，
        #   而且方向反了 —— 它们会把用户要求去掉的那道闸当成必须存在的。
        #   ⇒ 改成钉**新契约**：① 不要求手打（没有输入框）；② 说清会进回收站、可恢复。
        # [EN] ★★ 2026-10-26 the criteria are **inverted** (the product was changed on the user's
        # [EN] explicit request; the criteria were not). On 2026-10-21 the user said: "after this
        # [EN] change, deleting a novel in Pick a Volume needs no name, just a yes/no prompt saying
        # [EN] it moves to the recycle bin." So the type-to-confirm box is **intentionally gone**
        # [EN] (the recycle bin restores a whole book, and a gate against "this hurts" is just extra
        # [EN] clicks once "this does not hurt"). The three old criteria (must type / has a field /
        # [EN] button greyed out) are **necessarily red** here and point the wrong way -- they would
        # [EN] demand a gate the user asked to remove. => Pin the **new** contract instead:
        # [EN] (1) no typing required (no text field); (2) it says the book goes to the bin and can
        # [EN] be recovered.
        pconfirm = next(c for c in VU.walk(pcd[-1])
                        if type(c).__name__ == 'FilledButton'
                        and VU.text_of(c).strip() == '确认删除')
        tf = next((c for c in VU.walk(pcd[-1]) if isinstance(c, ft.TextField)), None)
        ok('B：★ 删整本**不再要求手打书名**（用户 2026-10-21 明确要去掉那道闸）',
           tf is None, f'输入框={tf is not None}')
        ok('B：★ 确认框说清"会移到回收站、可以恢复"（去掉闸的**前提**）',
           '回收站' in pjoin and ('恢复' in pjoin or '找回' in pjoin), pjoin[:120])
        ok('B：★ 不手打也能点确认（不是"看着能点、点了没反应"）',
           not pconfirm.disabled)
        await shot('resume_manage_confirm_novel.png')
        pconfirm.on_click(None)
        page.update()
        await asyncio.sleep(1.2)
        ok('B：项目文件夹真的从项目目录里消失了', not proj_b.root.exists(),
           str(proj_b.root))
        pj = list(trash_dir_for(projects_root_ref[0]).glob('*_小说_*'))
        ok('B：整本书在「已删除备份」里（含它的 .nwsproj）',
           bool(pj) and any(x.glob('*.nwsproj') for x in pj),
           str([p.name for p in pj][:2]))
        ok('B：删完拾卷还开着，① 栏只剩一本',
           len(VU.open_dialogs(page)) == 1 and len(_novel_cards(dlg)) == 1,
           f'{len(VU.open_dialogs(page))} 个 / {len(_novel_cards(dlg))} 本')
        left = [p.name for p in _scan()]
        ok('B：列表里已经没有那本被删的书', '待删项目' not in left, str(left))

        # ══════════ D. ★★ 删存档不再被 state.db 卡住（2026-10-07 用户报的）══════════
        # [EN] ══════════ D. ★★ Deleting an archive no longer gets stuck on state.db (reported by user
        # [EN] 2026-10-07) ══════════
        #
        # 现场证据（用户真实目录）：`已删除备份/` 里有 4 个**同名**存档备份，
        # 第 1 个是完整的、后 3 个只剩 7 个文件 —— 那是 `shutil.move` 回退成
        # 「复制 + 删除」的指纹：复制成功了、删除卡在 `state.db` 上。
        # 根因：推演用的 sqlite 就在运行文件夹里，而 `RunLoop` 拿着那个连接
        # **一直没关**；Windows 上只要有句柄开着，整个目录就改不了名。
        # 所以这里必须用**真的装配出来的 DB**（不是替身），否则测不出来。
        # [EN] On-site evidence (user's real directory): `已删除备份/` contains 4 archive backups with the **same
        # [EN] name**,
        # [EN] the 1st is complete, the last 3 have only 7 files left -- that's the fingerprint of
        # [EN] `shutil.move` falling back to
        # [EN] "copy + delete": the copy succeeded, the delete got stuck on `state.db`.
        # [EN] Root cause: the sqlite used for simulation is right in the run folder, and `RunLoop` holds that
        # [EN] connection
        # [EN] **never closed**; on Windows, as long as a handle is open, the whole directory can't be renamed.
        # [EN] So here we must use a **really assembled DB** (not a stand-in), otherwise it can't be tested.
        print('\n── D. 删存档：state.db 开着也搬得走 ──')
        from store.runfolder import RunFolder
        from sim.session import RunSession
        from verify_run_control import make_project as _mk_proj

        dproj = _mk_proj(tmp / 'ProjectsD' / '锁验证')
        CFG.projects_dir()                    # 触发一次目录解析（建目录）
        # 让这本书出现在拾卷里：搬进当前 projects_root
        # [EN] Trigger one directory parse (create directory)
        # [EN] Make this book appear in 拾卷: move it into the current projects_root
        import shutil as _sh
        dst = projects_root_ref[0] / dproj.root.name
        _sh.copytree(dproj.root, dst)
        dproj = Project(dst, dproj.name)
        # ⚠ 必须补一个 `.nwsproj`：`scan_projects()` 是按 `rglob('*.nwsproj')`
        #   认项目的，没有它这本书在拾卷里根本不会出现（`Project.create_new`
        #   会写，`verify_run_control.make_project` 不写）。
        # [EN] ⚠ Must add a `.nwsproj`: `scan_projects()` recognizes projects by `rglob('*.nwsproj')`,
        # [EN] without it this book won't appear in 拾卷 at all (`Project.create_new`
        # [EN] writes it, `verify_run_control.make_project` doesn't).
        dproj.write_nwsproj()

        drun = RunFolder(dproj.root, '第1次模拟2026-10-07-00-01').create()
        (drun.root / '每天的生活').mkdir(exist_ok=True)
        (drun.root / '每天的生活' / '第001天.md').write_text(
            '# 第 1 天\n\n雨还在下。\n', encoding='utf-8')
        from sim.setup import assemble as _assemble
        _loop, _world, _db = _assemble(dproj, drun)
        ok('D：装配真的开了一个 sqlite 连接（夹具可信）',
           _db is not None and (drun.root / 'state.db').exists(), '')

        # ── ★ 被占用时：**拒绝，而且一个字都不许动** ──
        # [EN] -- ★ When occupied: **reject, and don't move a single character** --
        #
        # 这条是这一组里最要紧的一条。旧实现用 `shutil.move`，它在改不了名时
        # 会回退成「先复制、再删源」：复制成功、rmtree 卡在 state.db 上 ——
        # **源目录被删掉一半**，而用户只看到一句"搬不动"。
        # 实测本机：源目录从 9 项掉到 1 项（真的丢东西）。
        # [EN] This is the most important item in this group. The old implementation used `shutil.move`, which
        # [EN] when it can't rename
        # [EN] falls back to "copy first, then delete source": the copy succeeds, rmtree gets stuck on state.db
        # [EN] --
        # [EN] **Half of the source directory was deleted**, yet the user only sees a single line saying "can't
        # [EN] move it".
        # [EN] Measured on this machine: the source directory dropped from 9 entries to 1 (data really is
        # [EN] lost).
        n_before = len(list(drun.root.rglob('*')))
        ok_lock, why_lock = archive_run_dir(drun.root, dproj.root,
                                           projects_root_ref[0])
        n_after = len(list(drun.root.rglob('*')))
        ok('D：★ 文件被占用时 → **拒绝**（不假装删掉了）',
           not ok_lock, why_lock[:60])
        ok('D：★★ 拒绝时**源目录一个字都没少**（旧实现会毁掉一半，这是真丢数据）',
           n_after == n_before and n_after > 3, f'{n_before} → {n_after} 项')
        ok('D：★ 拒绝时**不留假备份**（半成品备份比没有更坏）',
           not list(trash_dir_for(projects_root_ref[0]).glob(
               f'*_存档_{drun.root.name}*')),
           str([p.name for p in trash_dir_for(
               projects_root_ref[0]).glob('*_存档_*')]))
        ok('D：拒绝的原因是一句**能照着做的话**（写明被占用 + 怎么处理）',
           '占用' in why_lock and ('停止' in why_lock or '重开' in why_lock),
           why_lock[:80])

        class _FakeLoop:
            """只会"一直跑"的替身主循环 —— 用来试"还在跑就拒绝删"。
                        English:
            A stand-in main loop that only "keeps running" -- used to test "reject delete while still
            running".
            """

            def __init__(self, db):
                self.db = db
                self._stop = False

            async def run(self, max_ticks: int = 0):
                while not self._stop:
                    await asyncio.sleep(0.05)
                return '手动停止'

            def stop(self):
                self._stop = True

        _fake = _FakeLoop(_db)
        dses = RunSession(_fake, _world, drun)
        app.session = dses
        dses.start()                          # 真会话：状态=运行中
        # [EN] Real session: status = running
        await asyncio.sleep(0.2)
        why = app._release_run_files(drun.root)
        ok('D：★ 这一轮**还在跑**时，拒绝删并说清"先停止"（不许把正在写的目录搬走）',
           bool(why) and '停止' in why, why)
        ok('D：拒绝之后那一轮**原封不动**',
           drun.root.exists() and (drun.root / 'state.db').exists(), '')

        # 停下来（模拟"跑完/手动停止"之后用户去删）
        # [EN] Stop it (simulate "finished/manually stopped", then the user goes to delete)
        _fake.stop()
        await asyncio.sleep(0.4)
        dses.wait(3)
        ok('D：会话已结束（`is_alive` 为假）—— 这才是用户点"删"时的常态',
           not dses.is_alive, dses.status)

        dlg2 = app.show_projects_dialog()
        page.update()
        await asyncio.sleep(0.9)
        # 拾卷默认开的是**第一本**书（`_load_novels(projects[0])`）——
        # 得先点一下我们这本，② 栏才会换成它的存档。
        # [EN] Shijuan opens the **first** book by default (`_load_novels(projects[0])`) ——
        # [EN] You have to click our book first, and only then will column ② switch to its save.
        ncard = next((c for c in _novel_cards(dlg2)
                      if getattr(c, '_proj', None) is not None
                      and c._proj.name == dproj.name), None)
        ok('D：拾卷里找得到这本书', ncard is not None,
           str([getattr(c, '_proj', None) and c._proj.name
                for c in _novel_cards(dlg2)]))
        if ncard is not None:
            _card_body(ncard).on_click(None)
            page.update()
            await asyncio.sleep(0.7)
        dcards = _save_cards(dlg2)
        target = next((c for c in dcards
                       if getattr(c, '_run', None) is not None
                       and Path(c._run) == drun.root), None)
        ok('D：拾卷里找得到这一轮存档卡', target is not None,
           f'{len(dcards)} 张卡')
        if target is not None:
            _trash_of(target).on_click(None)
            page.update()
            await asyncio.sleep(0.7)
            dc = [d for d in VU.open_dialogs(page)
                  if any('删掉这一轮存档？' in x for x in VU.all_texts(d))]
            dbtn = next((c for c in VU.walk(dc[-1])
                         if type(c).__name__ == 'FilledButton'
                         and VU.text_of(c).strip() == '确认删除'), None)
            ok('D：弹出确认框', dbtn is not None, '')
            if dbtn is not None:
                dbtn.on_click(None)
                page.update()
                await asyncio.sleep(1.4)
                ok('D：★★ state.db 开着也**删掉了**（用户报的"无法删除"）',
                   not drun.root.exists(), str(drun.root))
                # 备份必须是**完整**的 —— 半成品备份（copytree 成功 + rmtree
                # 失败留下的）比没有更坏：它长得像一份真备份。
                # [EN] The backup must be **complete** —— a half-finished backup (copytree succeeded + rmtree
                # [EN] left over from a failure) is worse than none: it looks like a real backup.
                # ⚠ 2026-10-21 起每份备份旁边还有一份 `.json` 旁注（书名/删除时间/父存档），
                #   所以这里必须**排除 .json**，否则"份数"永远是 2 倍（判据自己数错）。
                # [EN] ⚠ Since 2026-10-21 each backup has a `.json` sidecar next to it (book name /
                # [EN] deletion time / parent round), so **exclude .json** here or the count is always
                # [EN] doubled (the criterion miscounts).
                dtrash = [p for p in trash_dir_for(projects_root_ref[0]).glob(
                    '*_存档_*') if drun.root.name in p.name and p.suffix != '.json']
                has_daily = bool(dtrash) and (dtrash[-1] / '每天的生活').exists()
                ok('D：★ 备份是**完整的**（含 `每天的生活/`），不是半成品',
                   has_daily, str([p.name for p in dtrash]))
                ok('D：这一次只留下一份备份（失败重试不会攒垃圾）',
                   len(dtrash) == 1, f'{len(dtrash)} 份')
                dmsgs = [m['text'] for m in getattr(app, '_messages', [])]
                ok('D：消息框给了回执（写明搬到哪了）',
                   any(('已把' in x and '存档' in x and '回收站' in x) for x in dmsgs),
                   str(dmsgs[-1:]))

        # ══════════ E. ★★★ 勾选残留 / "书没了"（2026-10-26 用户报的崩溃）══════════
        # [EN] ══════════ E. ★★★ Stale ticks / "the book is gone" (crash reported 2026-10-26) ══════════
        #
        # 用户原话：「我选中多个存档 但是此时不删除存档而是直接删除小说 结果存档的选中状态
        #   还在 后续运行界面也崩溃了」。现场日志（`logs/launcher_gui.log`）逐字是：
        #     Unhandled error in 'on_click' handler
        #     File "gui/app_flet.py", line 17180, in <lambda>
        #       multi_run = _multi_btn('runs', lambda e: _ask_delete_saves_multi(shown['proj']))
        #     File "gui/app_flet.py", line 16896, in _ask_delete_saves_multi
        #       if x not in seen and (proj.root / x).is_dir():
        #     AttributeError: 'NoneType' object has no attribute 'root'
        # 根因：勾存的是**名字**，书删掉之后名字还在 `sel` 里、栏头还写着「删除选中（3）」，
        #   而 `shown['proj']` 已经是 `None` ⇒ 一点就炸。
        # 这一组把**整条状态链**钉死（不是只钉"不抛异常"）：
        #   ① 换书必须清勾（否则会在**另一本书**里删掉同名、而用户没勾过的存档 ——
        #      这是比崩溃更坏的隐患，所以两本书故意用**同名**存档目录）；
        #   ② 删掉当前这本 ⇒ 勾清零、按钮文字复原；
        #   ③ 删掉最后一本 ⇒ 两栏的勾与按钮全归零；
        #   ④ 此时点「删除选中」：**不抛**、**不弹确认框**、**说清书去哪儿了**。
        # [EN] User's words: "I ticked several saves, but then deleted the novel instead of the
        # [EN] saves; the save ticks stayed, and the run screen crashed afterwards." The on-site log
        # [EN] (verbatim above) ends in `AttributeError: 'NoneType' object has no attribute 'root'`
        # [EN] because ticks are **names**: the book is gone, the names are still in `sel`, the header
        # [EN] still reads "delete selected (3)", while `shown['proj']` is already `None`.
        # [EN] This group pins the **whole state chain**, not just "it does not raise":
        # [EN] ① changing the book must clear ticks (otherwise it deletes same-named saves in
        # [EN]    **another** book the user never ticked -- worse than a crash, hence the two books
        # [EN]    deliberately share save folder names);
        # [EN] ② deleting the current book => ticks zeroed and labels restored;
        # [EN] ③ deleting the last book => both columns' ticks and labels zeroed;
        # [EN] ④ clicking "delete selected" then: **no raise**, **no confirm dialog**, and a message
        # [EN]    saying where the book went.
        def _check_of(card):
            """卡片最前面那个**自绘复选框**（20×22，内容是一个 `ft.Icon`）。
                English:
            The **self-drawn checkbox** at the head of a card (20x22, content is one `ft.Icon`).
            """
            for c in VU.walk(card):
                if (isinstance(c, ft.Container) and getattr(c, 'on_click', None)
                        and isinstance(getattr(c, 'content', None), ft.Icon)
                        and c.width == 20 and c.height == 22):
                    return c
            return None

        def _multi_btns(ctrl):
            """栏头那两个「删除选中」按钮（返回 `[(容器, 文字控件), …]`）。
                English: The two "delete selected" header buttons as `[(container, label), ...]`.
            """
            out = []
            for c in VU.walk(ctrl):
                if not (isinstance(c, ft.Container) and getattr(c, 'on_click', None)):
                    continue
                for x in VU.walk(c):
                    if isinstance(x, ft.Text) and (x.value or '').startswith('删除选中'):
                        out.append((c, x))
                        break
            return out

        # 两本书、**存档目录同名**（这是要害：跨书残留会删到另一本里"同名但没勾过"的存档）
        proj_e1 = Project.create_new(CFG.projects_dir(), '勾选甲')
        proj_e2 = Project.create_new(CFG.projects_dir(), '勾选乙')
        for proj in (proj_e1, proj_e2):
            for i, folder in enumerate(('第1次模拟2026-02-01-00-00',
                                        '第2次模拟2026-02-02-00-00'), 1):
                make_run(proj, folder)
        dlg_e = app.show_projects_dialog()
        page.update()
        await asyncio.sleep(0.9)

        async def _delete_book_now(name: str) -> None:
            """从拾卷里删掉一整本（点卡片上的 🗑 → 确认）。

            ⚠ 2026-10-26：**不用手打书名**（那一步 2026-10-21 被用户要求去掉了），
              所以这里只点"确认删除"。
            [EN] Delete one whole book from Pick a Volume (trash icon on the card -> confirm).
            [EN] ⚠ 2026-10-26: **no typing the title** (removed at the user's request 2026-10-21),
            [EN] so this only clicks "confirm".
            """
            card = next((c for c in _novel_cards(dlg_e)
                         if getattr(c, '_proj', None) is not None
                         and c._proj.name == name), None)
            if card is None:
                return
            _trash_of(card).on_click(None)
            page.update()
            await asyncio.sleep(0.6)
            cds = [d for d in VU.open_dialogs(page)
                   if any('删掉整本小说？' in x for x in VU.all_texts(d))]
            if cds:
                b = next((c for c in VU.walk(cds[-1])
                          if type(c).__name__ == 'FilledButton'
                          and VU.text_of(c).strip() == t('确认删除')), None)
                if b is not None:
                    b.on_click(None)
            page.update()
            await asyncio.sleep(1.2)

        def _pick_book(name: str) -> None:
            card = next((c for c in _novel_cards(dlg_e)
                         if getattr(c, '_proj', None) is not None
                         and c._proj.name == name), None)
            if card is not None:
                _body_of(card).on_click(None)

        # ★ 先把前面几组留下的项目清掉（D 组会留一本"锁验证"）。
        #   不清的话，删到最后**左栏并不空** ⇒ `shown['proj']` 不是 `None`，
        #   就走不到用户现场那条路（"书没了但勾还在"），这一组等于没测。
        #   ⚠ 必须在 `_delete_book_now` **定义之后**调用 —— 原来写在定义前面，
        #     只要真有一条残留要删就 `UnboundLocalError`，而它发生在 try 块中段：
        #     后面整组一条不跑，汇总行却照样打印"89/89"（**判据自己撒的谎**）。
        # [EN] ★ Clear the books left over from earlier groups (D leaves one behind). Otherwise the
        # [EN] column is **not** empty at the end, `shown['proj']` is not `None`, and the path the
        # [EN] user actually hit ("book gone, tick still there") is never taken.
        # [EN] ⚠ Must run **after** `_delete_book_now` is defined -- it used to sit before, so any
        # [EN] real leftover raised UnboundLocalError mid-`try`: the rest of the group never ran
        # [EN] while the summary line still printed "89/89" (**the criterion lying to itself**).
        for _leftover in [p.name for p in _scan()
                          if p.name not in (proj_e1.name, proj_e2.name)]:
            await _delete_book_now(_leftover)

        _pick_book(proj_e1.name)
        page.update()
        await asyncio.sleep(0.6)

        sc = _save_cards(dlg_e)
        ok('E：起点：中栏是「勾选甲」的两轮', len(sc) == 2, f'{len(sc)} 张存档卡')
        for c in sc[:2]:
            chk = _check_of(c)
            if chk is not None:
                chk.on_click(None)
        page.update()
        await asyncio.sleep(0.3)
        labels = [x.value for _b, x in _multi_btns(dlg_e)]
        ok('E：勾两轮存档 → 栏头按钮变成「删除选中（2）」',
           any('（2）' in (v or '') for v in labels), str(labels))

        # ① 换书必须清勾（否则会在**另一本**书里删掉同名、用户没勾过的存档）
        # [EN] ① Changing the book must clear the ticks (else it deletes same-named saves in
        # [EN] **another** book that the user never ticked)
        _pick_book(proj_e2.name)
        page.update()
        await asyncio.sleep(0.6)
        labels = [x.value for _b, x in _multi_btns(dlg_e)]
        ok('E：★★ 换到另一本书 → 勾**被清掉**、按钮不再带数字'
           '（不清就会删掉另一本里同名但没人勾过的存档）',
           labels and all('（' not in (v or '') for v in labels), str(labels))
        ok('E：换书后中栏真的换成了另一本的两轮', len(_save_cards(dlg_e)) == 2,
           f'{len(_save_cards(dlg_e))} 张')

        # ② 删掉当前这本书（书没了，勾不能还亮着）
        # [EN] ② Delete the current book (a gone book must not leave a lit tick)
        _pick_book(proj_e1.name)
        page.update()
        await asyncio.sleep(0.5)
        for c in _save_cards(dlg_e)[:2]:
            chk = _check_of(c)
            if chk is not None:
                chk.on_click(None)
        page.update()
        await asyncio.sleep(0.3)
        ok('E：再勾一轮存档 → 按钮回到「删除选中（2）」',
           any('（2）' in (x.value or '') for _b, x in _multi_btns(dlg_e)),
           str([x.value for _b, x in _multi_btns(dlg_e)]))

        nb_e = next((c for c in _novel_cards(dlg_e)
                     if getattr(c, '_proj', None) is not None
                     and c._proj.name == proj_e1.name), None)
        _trash_of(nb_e).on_click(None)
        page.update()
        await asyncio.sleep(0.6)
        pcd_e = [d for d in VU.open_dialogs(page)
                 if any('删掉整本小说？' in x for x in VU.all_texts(d))]
        ok('E：左栏垃圾桶弹出"删整本"确认框（否则后面两条无从谈起）', bool(pcd_e), '')
        if pcd_e:
            btn = next((c for c in VU.walk(pcd_e[-1])
                        if type(c).__name__ == 'FilledButton'
                        and VU.text_of(c).strip() == t('确认删除')), None)
            if btn is not None:
                btn.on_click(None)
        page.update()
        await asyncio.sleep(1.2)
        ok('E：★★ 删掉当前这本书之后，存档栏的勾**被清掉**、按钮不带数字',
           all('（' not in (x.value or '') for _b, x in _multi_btns(dlg_e)),
           str([x.value for _b, x in _multi_btns(dlg_e)]))

        # ③ 删掉最后一本（复现用户现场：左栏空了，但勾还在）
        # [EN] ③ Delete the last book (reproducing the user's scene: the column is empty, ticks remain)
        #
        # ⚠ **不能靠"再走一遍 dlg_e 的控件树"来断言**：删掉最后一本时，对话框会
        #   自动切到「回收站」页签（`nav['trash']()`），而 `_switch` 是
        #   `pane_box.content = _build_trash_pane()` —— **拾卷那一页整块脱离控件树**，
        #   但它的控件对象与闭包还在（用户就是切回「拾卷」页签、点那个旧按钮时崩的）。
        #   ⇒ 处理办法跟用户的操作一样：**先抓住那两个按钮对象**，删完之后看它们的
        #     `label.value`（`_sel_refresh` 改的是同一个对象），点也点这些对象。
        # [EN] ⚠ **Do not assert by walking dlg_e's tree again**: deleting the last book makes the
        # [EN] dialog switch to the recycle-bin tab, and `_switch` replaces `pane_box.content` --
        # [EN] the Pick-a-Volume page **leaves the control tree** while its controls and closures
        # [EN] live on (that is precisely how the user crashed: switch back to the pick tab, click
        # [EN] the old button). So do what the user does: **grab the two buttons first**, then read
        # [EN] their `label.value` afterwards (`_sel_refresh` mutates the same object) and click those.
        btns_e = _multi_btns(dlg_e)
        ok('E：栏头那两个「删除选中」按钮找得到（后面几条的前提）',
           len(btns_e) == 2, f'{len(btns_e)} 个')
        ok('E：★ 此刻（刚删掉当前那本）按钮已经不带数字 —— 后面就盯着这两个对象看',
           all('（' not in (x.value or '') for _b, x in btns_e),
           str([x.value for _b, x in btns_e]))

        # 把 B 段留下的那本也删掉，只留最后一本 —— 用户现场是"删掉**最后一本**"
        # [EN] Also delete the book left over from group B so only one remains -- the user's scene
        # [EN] was "deleting the **last** book"
        await _delete_book_now('拾卷验证')
        ok('E：删掉一本不是"当前显示"的书，勾也不会串（仍不带数字）',
           all('（' not in (x.value or '') for _b, x in btns_e),
           str([x.value for _b, x in btns_e]))

        # 再勾一次（用户现场：勾着的时候把**最后一本**也删了）
        for c in _save_cards(dlg_e)[:1]:
            chk = _check_of(c)
            if chk is not None:
                chk.on_click(None)
        page.update()
        await asyncio.sleep(0.3)
        # ⚠ 勾 1 张卡可能让按钮显示"（2）"：这两轮在夹具里被**推断**成父子，
        #   勾父节点会级联勾上并锁住子节点（`_run_toggle`，用户 2026-10-21 点名要的语义）。
        #   这条要问的是"勾选还能用"，不是"数字恰好是 1"。
        # [EN] ⚠ Ticking one card may show "(2)": the two fixture rounds are **inferred** parent and
        # [EN] child, and ticking a parent cascades onto the child (`_run_toggle`, requested by the
        # [EN] user 2026-10-21). The question is "do ticks still work", not "the number is exactly 1".
        ok('E：删掉一本书之后，剩下那本照样能勾（勾选功能没被"清空"搞坏）',
           any(any(ch.isdigit() for ch in (x.value or '')) for _b, x in btns_e),
           str([x.value for _b, x in btns_e]))

        await _delete_book_now(proj_e2.name)
        ok('E：两本书都真的从盘上没了（这一栏空了，复现用户现场）',
           not _scan(), str([p.name for p in _scan()]))

        labels = [x.value for _b, x in btns_e]
        ok('E：★★★ 一栏空了之后，两个「删除选中」都**不带数字**（勾确实清零了）',
           len(labels) == 2 and all('（' not in (v or '') for v in labels), str(labels))

        # ④ 点它：**不抛 / 不弹确认框 / 说清书去哪儿了**
        # [EN] ④ Click it: **no raise / no confirm dialog / says where the book went**
        raised, popped = '', []
        for cont, lbl in btns_e:
            before = {id(d) for d in VU.open_dialogs(page)}
            try:
                cont.on_click(None)
            except Exception as exc:                          # noqa: BLE001
                raised = f'{lbl.value}: {type(exc).__name__}: {exc}'
            page.update()
            await asyncio.sleep(0.4)
            for d in VU.open_dialogs(page):
                if id(d) in before:
                    continue
                txt = ' / '.join(VU.all_texts(d))
                # 只有"删掉选中的…"这种**删除确认框**才算空头框；别的（比如提示条）不算
                if '删掉选中的' in txt:
                    popped.append(f'{lbl.value} → {txt[:60]}')
        ok('E：★★★ 点「删除选中」**不再抛异常**（用户现场就是这里 AttributeError）',
           not raised, raised or '没抛')
        ok('E：★★ 也不会弹出"删掉选中的 N 轮"这种空头确认框',
           not popped, str(popped))
        emsgs = [m['text'] for m in getattr(app, '_messages', [])]
        ok('E：★ 而且说清了"勾选已清空 / 书去回收站找回"（不是静静没反应）',
           any('勾选已清空' in x or '不在拾卷里' in x for x in emsgs[-8:]), str(emsgs[-2:]))

        report['ok'] = all(i['ok'] for i in items)
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        report['items'] = items
        report['n_ok'] = sum(1 for i in items if i['ok'])
        report['n_all'] = len(items)
        (OUT / 'resume_manage_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        for it in items:
            print(f"{'OK  ' if it['ok'] else 'FAIL'}  {it['name']}"
                  + (f"   [{it['detail']}]" if it['detail'] else ''))
        if report.get('fatal'):
            # ⚠ 必须**写在同一行**：崩溃时 `n_ok`/`n_all` 里只有崩之前那几组，
            #   打印成「89/89」会让人以为全绿（本项目反复栽在"判据自己说谎"上）。
            # [EN] ⚠ It must be **on the same line**: when it crashes, `n_ok`/`n_all` only cover
            # [EN] the groups that ran, so printing "89/89" reads as all-green (this project keeps
            # [EN] tripping over "the criterion lies to itself").
            print(f"\n拾卷管理验证：{report['n_ok']}/{report['n_all']}  "
                  f"⚠ 中途崩溃 —— 后面几组一条都没跑")
            print(report['fatal'])
        else:
            print(f"\n拾卷管理验证：{report['n_ok']}/{report['n_all']}")
        try:
            VU.safe_rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
        # [EN] CancelledError
        # [EN] and cancel this coroutine, on the line `exit_now(...)` after `await shutdown(page)`
        # [EN] **never executed** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
        # ★★ 2026-10-26 实测：**`await shutdown(...)` 本身也可能一行都不执行**。
        #   现象：判据打印「拾卷管理验证：89/89」（全绿），进程退出码却是 **2**
        #   （= 被回归总表记成红）。根因还是 `destroy()` 取消当前协程 ——
        #   一旦本协程处于 cancelling 状态，**在 `finally` 里 await 任何东西都会立刻抛
        #   `CancelledError`**，于是 `shutdown()` 连第一句都没跑到，退出码由 Flet 自己给。
        #   ⇒ 在它后面补一句**同步**的 `os._exit`（`finally` 一定会执行，而 `os._exit`
        #     不需要 await）。正常路径上 `shutdown` 已经退掉了，这句永远走不到。
        #   ⚠ 判据"全绿却返回失败码"是**假红**，和"失败却返回 0"一样坏：都会让人不信回归表。
        # [EN] ★★ Measured 2026-10-26: **`await shutdown(...)` itself may not run a single line**.
        # [EN] Symptom: the criterion prints "89/89" (all green) yet the process exits with **2**
        # [EN] (recorded as red by the regression table). Same root cause: `destroy()` cancels this
        # [EN] coroutine -- once it is cancelling, **awaiting anything inside `finally` raises
        # [EN] CancelledError immediately**, so `shutdown()` never reaches its first line and Flet
        # [EN] picks the exit code. => Add a **synchronous** `os._exit` behind it (`finally` always
        # [EN] runs and `os._exit` needs no await). On the normal path `shutdown` already exited.
        # [EN] ⚠ "All green but a failure exit code" is a false red, as bad as the opposite.
        import os as _os
        try:
            await shutdown(page, code=0 if report.get('ok') else 2)
        finally:
            _os._exit(0 if report.get('ok') else 2)



def _trash_icon_blocks(png: Path, tol: int = 30) -> tuple:
    """数屏幕上"朱砂红底"的块，以及其中**红底里有浅色字形**的块数。

    用户报过「删除的垃圾桶图标没在红色背景里」—— 那是 emoji 溢出按钮背景。
    换成 `mk_icon_btn()`（自己画底 + 居中 `ft.Icon`）之后，判据就是这条：
    **每一块小红底里面都必须有浅色像素**（纸白的图标字形）。
    字形跑到外面时，块内就是纯红 —— 量得出来。
    
        English:
    Count the "vermilion red background" blobs on screen, and among them the number of blobs that
    **have a light glyph inside the red background**.
        User reported "the delete trash-can icon is not inside the red background" —— that was the emoji overflowing the button background.
        After switching to `mk_icon_btn()` (custom-drawn background + centered `ft.Icon`), the criterion is this:
        **Every small red block must contain light-colored pixels** (the paper-white icon glyph).
        When the glyph goes outside, the block is pure red -- measurable.
    """
    from PIL import Image as _I
    im = _I.open(str(png)).convert('RGB')
    px = im.load()
    W, H = im.size
    red, light = set(), set()
    for y in range(H):
        for x in range(W):
            c = px[x, y]
            if all(abs(c[i] - (0xc0, 0x2c, 0x22)[i]) <= tol for i in range(3)):
                red.add((x, y))
            elif c[1] > 100 and c[2] > 90:
                # 「非纯红」= 绿/蓝通道明显高于朱砂底（192,44,34）——
                # 图标的字形（含抗锯齿的粉边）都落在这个范围里
                # [EN] "Non-pure red" = green/blue channels clearly higher than the vermilion base (192,44,34) ——
                # [EN] the icon's glyph (including antialiased pink edges) all falls in this range
                light.add((x, y))
    # 把红点按 8 邻接聚成块
    # [EN] cluster red pixels into blobs by 8-connectivity
    blocks, seen = [], set()
    for p0 in red:
        if p0 in seen:
            continue
        stack, grp = [p0], []
        seen.add(p0)
        while stack:
            cx, cy = stack.pop()
            grp.append((cx, cy))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (cx + dx, cy + dy)
                    if q in red and q not in seen:
                        seen.add(q)
                        stack.append(q)
        blocks.append(grp)
    icons = [g for g in blocks
             if len(g) >= 120
             and (max(x for x, _ in g) - min(x for x, _ in g)) <= 60
             and (max(y for _, y in g) - min(y for _, y in g)) <= 40]
    with_glyph = 0
    for g in icons:
        x0, x1 = min(x for x, _ in g), max(x for x, _ in g)
        y0, y1 = min(y for _, y in g), max(y for _, y in g)
        # ⚠ 两点：① 判"字形"要看**非纯红**（图标是细线，抗锯齿后是粉色，
        #   不是接近白）；② 统计范围**向内缩 4px**，否则圆角那几像素的底色
        #   会被当成字形（`probe_trash_icon.py` 的反例组实测会数出 20）。
        # [EN] ⚠ Two points: ① judging the "glyph" must look at **non-pure red** (the icon is a thin line, pink
        # [EN] after antialiasing,
        # [EN] not near white); ② the statistics range must be **shrunk inward by 4px**, otherwise the few
        # [EN] pixels of background at the rounded corners
        # [EN] get counted as glyph (measured on the counterexample set of `probe_trash_icon.py` it counts 20).
        n = sum(1 for x, y in light
                if x0 + 4 <= x <= x1 - 4 and y0 + 4 <= y <= y1 - 4)
        if n >= 15:
            with_glyph += 1
    return len(icons), with_glyph


def _body_of(card):
    """卡片里"点开看内容"那个可点容器（含 `ft.Text` 的那个）。
        English:
    The clickable container in the card for "tap to view content" (the one containing `ft.Text`).
    """
    for c in VU.walk(card):
        if getattr(c, 'on_click', None) is None:
            continue
        if any(isinstance(x, ft.Text) for x in VU.walk(c)):
            return c
    return None


def _icon_btn_of(card, icon):
    """卡片里**按图标名**找那个图标按钮。

    ⚠ 2026-10-08：小说卡上**多了「打开文件夹」那个按钮**（用户要求，
    排在删除按钮上面）。原来这里写的是"第一个含 `ft.Icon` 的可点控件"——
    它现在会先撞上**文件夹按钮**，于是判据点到了"打开文件夹"上
    （真机跑起来会**弹出资源管理器窗口**，而且删除确认框永远等不到）。
    所以必须**按图标名**找，不能靠"是不是第一个"。
    
        English:
    Find that icon button in the card **by icon name**.
        ⚠ 2026-10-08: The novel card now has **an extra "Open Folder" button** (user request,
        placed above the delete button). This used to say "the first clickable control containing `ft.Icon`" --
        now it hits the **folder button** first, so the criterion clicks on "Open Folder"
        (on a real device this **pops up an explorer window**, and the delete confirmation dialog never arrives).
        So we must find it **by icon name**, not by "is it the first one".
    """
    # ⚠ 取 `x.icon`（枚举值），**不是** `x.name` —— Flet 1.0 的 `ft.Icon`
    #   没有 `.name`（实测 `AttributeError`，整支判据当场崩掉、只跑完前 33 条）。
    # [EN] ⚠ Take `x.icon` (the enum value), **not** `x.name` —— Flet 1.0's `ft.Icon`
    # [EN] has no `.name` (measured `AttributeError`, the whole criterion crashes on the spot, only the
    # [EN] first 33 entries finish).
    #
    # ⚠⚠ 还要取**最小的那个匹配控件**（子树控件数最少）。为什么：
    #   卡片里**"点整行切选中"的那个正文容器**（`body`）也有 `on_click`，
    #   而它**把两个按钮都装在里面** → 直接返回第一个匹配项会拿到 `body`，
    #   于是判据"点删除"实际点到 `body` 上（什么都不会发生，
    #   删除确认框永远等不到），"点文件夹"同理 —— 表现为**判据全红**，
    #   而产品其实是对的。按钮的特征就是"子树很小"，所以按子树大小取最小。
    # [EN] ⚠⚠ Also take the **smallest matching control** (fewest controls in its subtree). Why:
    # [EN] the **body container in the card that "clicking the whole row toggles selection"** (`body`) also
    # [EN] has `on_click`,
    # [EN] and it **contains both buttons** → returning the first match directly gets you `body`,
    # [EN] so the criterion "click delete" actually clicks on `body` (nothing will happen,
    # [EN] the delete confirmation dialog is never reached), "click folder" likewise —— it shows up as
    # [EN] **all criteria red**,
    # [EN] while the product is actually correct. A button's characteristic is "small subtree", so take the
    # [EN] smallest by subtree size.
    cands: list[tuple[int, Any]] = []
    for c in VU.walk(card):
        if getattr(c, 'on_click', None) is None:
            continue
        sub = list(VU.walk(c))
        if any(isinstance(x, ft.Icon) and getattr(x, 'icon', None) == icon
               for x in sub):
            cands.append((len(sub), c))
    return min(cands, key=lambda t: t[0])[1] if cands else None


def _trash_of(card):
    """卡片里那个**删除**图标按钮。
        English:
    The **delete** icon button in the card.
    """
    return _icon_btn_of(card, ft.Icons.DELETE_OUTLINE)


def _folder_of(card):
    """卡片里那个**打开文件夹**图标按钮（2026-10-08 新增）。
        English:
    The **open folder** icon button in the card (added 2026-10-08).
    """
    return _icon_btn_of(card, ft.Icons.FOLDER_OPEN_OUTLINED)


def _card_body(card):
    """卡片里那个"点它切换选中"的正文容器（**不是**任何图标按钮）。

    ⚠ 判法变过（2026-10-08）：原来写的是"可点、而且里面**没有** `ft.Icon`"。
    小说卡上加了「打开文件夹」按钮之后，**两个图标按钮都装进了正文容器里**
    → 正文容器自己就含 `ft.Icon` 了 → 这条判法返回 `None`，
    调用处 `_card_body(ncard).on_click(None)` 直接 `AttributeError`
    （整支判据跑到最后一步崩掉）。

    现在的判法：**可点、里面有文字（`ft.Text`）、且子树最大**的那个。
      · 正文容器一定有文字（书名 / 时间 / 摘要）；
      · 图标按钮里**没有文字**（只有一个 `ft.Icon`）→ 天然排除；
      · "子树最大"= 最外层那个正文容器（不是里面某一行）。
    
        English:
    The body container in the card that "tap it toggles selection" (**not** any icon button).
        ⚠ The criterion changed (2026-10-08): it used to say "clickable, and contains **no** `ft.Icon`.
        After the "Open Folder" button was added to the novel card, **both icon buttons got nested inside the body container**
        -> the body container itself now contains `ft.Icon` -> this criterion returns `None`,
        and the call site `_card_body(ncard).on_click(None)` throws `AttributeError` directly
        (the whole criterion crashes at the last step).
        Current criterion: **the clickable one that contains text (`ft.Text`) and has the largest subtree**.
          · The body container always has text (title / time / summary);
          · Icon buttons have **no text** (only one `ft.Icon`) -> naturally excluded;
          · "Largest subtree" = the outermost body container (not some row inside it).
    """
    cands: list[tuple[int, Any]] = []
    for c in VU.walk(card):
        if getattr(c, 'on_click', None) is None:
            continue
        sub = list(VU.walk(c))
        if any(isinstance(x, ft.Text) for x in sub):
            cands.append((len(sub), c))
    return max(cands, key=lambda t: t[0])[1] if cands else None


def _novel_cards(dlg):
    return [c for c in VU.walk(dlg)
            if isinstance(c, ft.Container) and hasattr(c, '_proj')]


def _save_cards(dlg):
    return [c for c in VU.walk(dlg)
            if isinstance(c, ft.Container) and hasattr(c, '_run')]


def _find_dropdown(dlg):
    """找对话框里那个项目下拉框。**按"是不是下拉框"找**，别按标签文字 ——
    标签是 `t()` 过的（中文「选择小说」、英文「Novel」）。
        English:
    Find the project dropdown in the dialog. **Find it by "is it a dropdown"**, not by label text --
    """
    for _label, row in VU.labelled_fields(dlg).items():
        f = getattr(row, '_field', None)
        if f is not None and getattr(f, 'options', None):
            return f
    return None


def _find_list_view(dlg):
    """找左侧那个存档列表（`ListView` 里套着带 `_run` 的卡片）。
        English:
    Find the save list on the left (a `ListView` containing cards with `_run`).
    """
    for c in VU.walk(dlg):
        if not isinstance(c, ft.ListView):
            continue
        if any(hasattr(x, '_run') for x in (c.controls or [])):
            return c
    return next((c for c in VU.walk(dlg) if isinstance(c, ft.ListView)), None)


def _scan():
    from store.project import scan_projects
    return scan_projects(CFG.projects_dir())


OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

# 卡片/左栏的**原色**（涂完要还原 —— 只动颜色不动几何）
# [EN] The **original colors** of the card/left column (restore after painting —— only touch colors,
# [EN] not geometry)
from gui.app_flet import C, with_alpha, panel_alpha, DANGER  # noqa: E402
C_PANEL = C['panel']
C_HOVER = with_alpha(C['hover'], panel_alpha())
DANGER_COLOR = DANGER

# 运行前的静态自检（不起界面）
# [EN] Static self-check before running (no GUI started)
if __name__ == '__main__':
    set_lang('zh')
    ft.run(main)
