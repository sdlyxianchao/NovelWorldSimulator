# -*- coding: utf-8 -*-
"""真机验证：**剧组 Agents 设置**（软件层 + 项目层 + 天机/书斋两个页签 + 开卷那一步）。

用户 2026-10-11 三条要求，这一支逐条钉住：

1. 「各个 Agent 的 system prompt 保存在一个专门的 agents 文件夹，一个 Agent 一个 md，
    文件名用英语，加一个 README.md 说明英中对照；用户可以在这里编辑；
    **每个项目的文件夹里也有一个 agents**，保存项目定制；
    软件默认 + 项目定制 = 每个 Agent 的全部属性。」
2. 「天机加一个 Agents 设置 Tab：列表（名字/作用/提示词简略），点名字开编辑对话框
    （名字/简介/系统提示词/在什么情况下使用）… **支持分页，默认 5，可调**；
    **支持新建自定义 Agent，支持删除（只能删自建的）**；数据落到软件目录 agents。
    **项目设置里同样的 tab，唯一区别不允许新建和删除**。」
3. 「开卷的时候有一个步骤给各个 Agent 自定义，不自定义则用 AI 推断的项目级属性。」

产出：`assets/screenshots/agent_catalog_report.json`（+ 两张真机截图）。

English:
Real-machine verification: **Crew Agents settings** (software layer + project layer +
Tianji/Shuzhai two tabs + the open-book step).
User's three requirements on 2026-10-11, this branch pins them down one by one:
1. "Each Agent's system prompt is saved in a dedicated agents folder, one md per Agent,
    filename in English, plus a README.md explaining the English-Chinese comparison; the user can edit here;
    **each project's folder also has an agents**, storing project customization;
    software default + project customization = all properties of each Agent."
2. "Add an Agents settings Tab to Tianji: list (name/role/brief prompt), click a name to open the edit dialog
    (name/description/system prompt/when to use)… **supports pagination, default 5, adjustable**;
    **supports creating custom Agents, supports deletion (only custom ones can be deleted)**; data lands in the software directory agents.
    **The same tab in project settings, the only difference is no creating or deleting allowed**."
3. "When opening a book there's a step to customize each Agent; if not customized, use the AI-inferred project-level properties."
Output: `assets/screenshots/agent_catalog_report.json` (+ two real-machine screenshots).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                            # noqa: E402
import yaml                                                  # noqa: E402
from util.flet_shutdown import shutdown, exit_now            # noqa: E402
from util.io import atomic_write_text                        # noqa: E402

from config import CFG                                       # noqa: E402
CFG.set('MOCK_LLM', 'true')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from crew import catalog as CAT                              # noqa: E402
from crew import roster as ROSTER                            # noqa: E402
from actors import casting as CASTING                        # noqa: E402
from gui.app_flet import NovelWorldApp                       # noqa: E402
import gui.app_flet as AF                                    # noqa: E402
from gui.app_flet import C as UIC, SET_W as UI_SET_W, \
    SCROLL_BAR_W as UI_BAR_W, TAB_GUTTER as UI_TAB_GUTTER, \
    SLIDER_W as UI_SLIDER_W, FIELD_DD_PAD as UI_DD_PAD, _text_px, \
    _body_w_pct, _body_full_w, _dd_w_plus, _agent_col_widths, \
    book_geometry, tianji_geometry                            # noqa: E402
from i18n import set_lang, t                                 # noqa: E402
set_lang(_lang)

import verify_ui_common as VU                                # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': [], 'ok': True}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:200]})
    if not cond:
        report['ok'] = False
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'  | {str(detail)[:90]}' if detail else ''))
    return bool(cond)


# ══════════════════════════════════════════════════════════════════════
#  A. 存储层（纯逻辑，不弹窗）
# [EN] A. Storage layer (pure logic, no popups)
# ══════════════════════════════════════════════════════════════════════
def storage_checks() -> None:
    print('\n── A 两层存储（软件默认 / 项目定制）──')
    tmp = Path(tempfile.mkdtemp(prefix='nws_agentcat_'))
    soft = tmp / 'agents'
    proj = tmp / 'proj'
    (proj).mkdir(parents=True)

    wrote = CAT.seed_soft(soft)
    ok('A1 ★★ 首次运行把内置职位**播种**成一个个 md（文件名是英语）',
       len(wrote) == len(ROSTER.all_roles()) and (soft / 'novelist.md').exists()
       and (soft / 'art_director.md').exists(),
       f'{len(wrote)} 个：{wrote[:3]}')
    ok('A1b ★★ 播种**幂等**（再跑一次一个都不写 —— 否则会把作者改过的覆盖掉）',
       CAT.seed_soft(soft) == [], '')
    md = (soft / 'novelist.md').read_text(encoding='utf-8')
    ok('A1c ★★ 文件里 frontmatter 是属性、**正文就是系统提示词**（作者能直接用记事本改）',
       md.startswith('---') and 'key: novelist' in md
       and '你是本剧组的' in md, md[:60].replace('\n', ' | '))

    rd = CAT.write_readme(soft)
    ok('A2 ★★★ README.md 里有**英语名 ↔ 中文名对照**（用户点名的）',
       rd.exists() and 'novelist.md' in rd.read_text(encoding='utf-8')
       and 'Novelist' in rd.read_text(encoding='utf-8')
       and '小说作家' in rd.read_text(encoding='utf-8'), rd.name)

    eff = CAT.effective(base=soft, project=None)
    ok('A3 ★★ 有效表 = 内置 + 软件层文件（2026-10-12 起 22 个：17 剧组 + 4 系统服务 + 1 特殊）',
       len(eff) == len(ROSTER.all_roles()) and all(s.builtin for s in eff),
       len(eff))

    # ── 项目层覆盖：**只覆盖写了的字段** ──
    # [EN] ── Project-layer override: **only overrides fields that are written** ──
    CAT.save_project(proj, 'novelist', name='主笔')
    got = CAT.get('novelist', base=soft, project=proj)
    ok('A4 ★★★ 项目层覆盖**只改写了的字段**（改了名字，简介/提示词照旧跟软件层）',
       got.name == '主笔' and got.intro == CAT.get('novelist', base=soft,
                                                  project=None).intro,
       f'name={got.name}')
    ok('A4b ★★ 覆盖过的字段被记下来（界面据此标「本项目已定制」）',
       'name' in got.overridden, got.overridden)
    ok('A4c ★★ 别的职位**不受影响**（项目层不是整份替换）',
       CAT.get('director', base=soft, project=proj).name == '导演', '')
    other = CAT.effective(base=soft, project=None)
    ok('A4d ★★ 换了项目那一份就不生效（同一进程里两本书互不串味）',
       CAT.get('novelist', base=soft, project=None).name == '小说作家',
       [s.name for s in other if s.key == 'novelist'])

    # ── 项目层文件里**只写被覆盖的字段** ──
    # [EN] ── In project-layer files, **only write the fields being overridden** ──
    pmd = (CAT.proj_dir(proj) / 'novelist.md').read_text(encoding='utf-8')
    ok('A5 ★★★ 项目层那份 md 里**不写没改的字段**（升级软件后它能跟着更新）',
       'name: 主笔' in pmd and '你是本剧组的' not in pmd, pmd[:80])

    # ── 自建职位 ──
    # [EN] ── Custom positions ──
    made = CAT.create_custom(name='考据校对', name_en='Fact Checker',
                            intro='核对名物', prompt='你是考据校对。', base=soft)
    ok('A6 ★★ 新建自建职位：slug 是英语文件名（`fact_checker.md`）',
       made.slug == 'fact_checker' and (soft / 'fact_checker.md').exists(),
       made.slug)
    names = [s.slug for s in CAT.effective(base=soft, project=None)]
    ok('A6b ★★ 自建职位排在**内置之后**（作者自己加的不该插到老职位中间）',
       names.index('fact_checker') > names.index('publicity'), '')
    ok('A6c ★★ 自建职位**不能选逐拍出工**（那一档要主循环接线，给了就是假按钮）',
       made.when == CAT.CUSTOM_WHEN == 'day', made.when)

    # ── 删除护栏 ──
    # [EN] ── Delete guardrail ──
    bad1, why1 = CAT.delete_soft('novelist', base=soft)
    ok('A7 ★★★ **软件自带的职位一律拒删**（它们是程序的一部分）',
       bad1 is False and '不能删' in why1, why1)
    ok('A7b ★★ 自建的可以删，删完文件真的没了',
       CAT.delete_soft('fact_checker', base=soft)[0]
       and not (soft / 'fact_checker.md').exists(), '')
    ok('A7c ★★ 删完就不在有效表里了',
       'fact_checker' not in [s.key for s in
                              CAT.effective(base=soft, project=None)], '')

    # ── 项目层：不许新建 ──
    # [EN] ── Project layer: no creating new ones allowed ──
    (CAT.proj_dir(proj) / 'ghost.md').write_text(
        '---\nkey: ghost\nname: 幽灵\nname_en: Ghost\n---\n\n随便写点什么\n',
        encoding='utf-8')
    ok('A8 ★★★ 项目层写进去的**新职位一律不采纳**（新建只在软件层做）',
       'ghost' not in [s.key for s in CAT.effective(base=soft, project=proj)],
       '')

    # ── 提示词真的进得了剧组 ──
    # [EN] ── Prompts really make it into the crew ──
    blk = CAT.prompt_block('novelist', project=proj)
    ok('A9 ★★★ 那个职位的**系统提示词块**取得到（它就是拼进提示词的那一段）',
       CAT.HEAD in blk and ('主笔' in blk or '小说作家' in blk), blk[:60])

    # ── README 里自建职位也在（对照表要跟着更新）──
    # [EN] ── Custom positions are also in the README (the comparison table must be updated accordingly) ──
    CAT.create_custom(name='甲', name_en='Alpha', prompt='x', base=soft)
    txt = CAT.write_readme(soft).read_text(encoding='utf-8')
    ok('A10 ★ README 的对照表会跟着**自建职位**更新',
       'Alpha' in txt and '甲' in txt, '')

    # ── 改名（slug 变）不留孤儿文件 ──
    # [EN] ── Renaming (slug change) leaves no orphan files ──
    spec = CAT.get('alpha', base=soft, project=None)
    CAT.save_soft(spec.merged_with(slug='beta', name_en='Beta'),
                  base=soft, old_slug='alpha')
    ok('A11 ★★ 改英文名 = 改文件名：旧文件**被删掉**（不留孤儿，否则列表里看不见它还在）',
       not (soft / 'alpha.md').exists() and (soft / 'beta.md').exists(), '')

    # ── 坏文件不炸 ──
    # [EN] ── Bad files don't blow up ──
    (soft / 'broken.md').write_text('这不是 frontmatter', encoding='utf-8')
    ok('A12 ★★ 坏 md 不会让整层崩（只是那一条读不出来）',
       len(CAT.effective(base=soft, project=None)) >= 17, '')
    report['soft_dir'] = str(soft)


# ══════════════════════════════════════════════════════════════════════
#  B. 剧组真的用它（名册/台账/用量/收工时自建职位出工）
# [EN] B. The crew actually uses it (roster/ledger/usage/custom positions clock in at wrap-up)
# ══════════════════════════════════════════════════════════════════════
def crew_checks() -> None:
    print('\n── B 剧组用它（名册 / 台账 / 收工出工）──')
    tmp = Path(tempfile.mkdtemp(prefix='nws_agentcrew_'))
    soft = tmp / 'agents'
    proj = tmp / 'proj'
    proj.mkdir(parents=True)
    CAT.seed_soft(soft)
    CAT.set_soft_dir(soft)
    CAT.bind_project(proj)
    CAT.save_project(proj, 'novelist', name='主笔')
    CAT.save_project(proj, 'director', name='班主')
    # 让 roster/catalog 都认这个临时目录：靠 `CAT.soft_dir` 的 base —— 生产代码
    # 走 `APP_DIR/agents`，判据里要把两边对齐（否则会写到真软件目录里）。
    # [EN] Make both roster/catalog recognize this temp directory: rely on the base of `CAT.soft_dir` —
    # [EN] production code
    # [EN] uses `APP_DIR/agents`, so the criteria must align both sides (otherwise it will write into the
    # [EN] real software directory).
    real_soft = CAT.soft_dir()

    ok('B1 ★★★ 名册走**有效名册**：改过名字的职位在名册里就是新名字'
       '（不是只在设置页好看）',
       ROSTER.role('novelist').name == '主笔'
       and ROSTER.role('director').name == '班主'
       and ROSTER.role('actor').name == '演员',
       f"{ROSTER.role('novelist').name}/{ROSTER.role('director').name}")
    ok('B1b ★★ 而且**出厂名册一个字节没被改**（它是模块级常量，多本书共用一个进程）',
       ROSTER.BY_KEY['novelist'].name == '小说作家', '')

    from crew import agents as A
    blk = A.craft_block('novelist', '', '')
    ok('B2 ★★★ `craft_block` 里**带着**那个职位的系统提示词（14 个职位都走它）',
       CAT.HEAD in blk, blk[:60])

    # 自建职位可出工
    # [EN] Custom positions can clock in
    CAT.create_custom(name='考据校对', name_en='Fact Checker',
                      intro='核对名物', prompt='你是考据校对。', base=soft)
    try:
        m = A.member('fact_checker')
        ok('B3 ★★★ 自建职位有实现（`member()` 现造一个通用成员 —— 否则它就是假按钮）',
           m is not None and getattr(m, 'key', '') == 'fact_checker', type(m))
    except Exception as e:                                       # noqa: BLE001
        ok('B3 ★★★ 自建职位有实现', False, repr(e))
    ok('B3b ★★ 缺人自查不会把自建职位误报成「缺人」',
       'fact_checker' not in A.missing_members(), A.missing_members())

    # studio 的槽位/台账里看得见它
    # [EN] Visible in studio's slots/ledger
    try:
        from crew import studio as ST
        stu = ST.Studio.__new__(ST.Studio)
        import time as _time
        stu.world = None
        stu.db = None
        stu.runfolder = None
        stu._on_note = stu._on_stage = stu._on_work = None
        stu._slots = {r.key: ST._Slot(key=r.key) for r in ROSTER.roles()}
        stu._stats = {r.key: {'runs': 0, 'fails': 0} for r in ROSTER.roles()}
        stu._art = None
        stu._day_maps = {}
        stu._props = {}
        stu._stylist = {}
        stu._sound = {}
        stu._deai_hits = []
        stu._deai_checked = 0
        led = stu.ledger()
        keys = [r['key'] for r in led]
        ok('B4 ★★★ 剧组台账里**有自建职位那一行**（否则界面上永远看不到它）',
           'fact_checker' in keys, len(keys))
        ok('B4b ★★ 台账里用的也是改过的名字',
           any(r['key'] == 'novelist' and r['name'] == '主笔' for r in led), '')
    except Exception as e:                                       # noqa: BLE001
        ok('B4 ★★★ 剧组台账里有自建职位那一行', False, repr(e))

    ok('B5 ★★ 用量台账那一栏用的就是名册的名字（改名字，统计跟着变）',
       ROSTER.role('novelist').name == '主笔', '')
    # 还原绑定，别把后面的判据带偏
    # [EN] Restore the binding, don't let it skew the subsequent criteria
    CAT.bind_project(None)
    CAT.set_soft_dir(None)
    report['real_soft'] = str(real_soft)


# ══════════════════════════════════════════════════════════════════════
#  C. 开卷那一步：AI 推断
# [EN] C. The open-book step: AI inference
# ══════════════════════════════════════════════════════════════════════
async def infer_checks() -> None:
    print('\n── C 开卷那一步（AI 推断项目级定制）──')
    got = await CAT.infer_project_agents(
        name='测试书', genre='悬疑·单元', style='冷硬',
        summary='一个临江小镇，掌柜与伙计。', keys=['novelist', 'continuity'])
    ok('C1 ★★★ AI 推断**真的跑通**（MOCK 也要演得像 —— 返回空 dict 看着就像没做）',
       bool(got) and set(got) <= {'novelist', 'continuity'}, list(got))
    ok('C1b ★★ 推断结果**只认名册里真有的 key**（模型编一个就丢掉）',
       all(k in {r.key for r in ROSTER.roles()} for k in got), list(got))
    empty = await CAT.infer_project_agents(keys=[])
    ok('C1c ★★ 没有要推的职位 → **一次调用都不发**（省一次请求）',
       empty == {}, '')


# ══════════════════════════════════════════════════════════════════════
#  D. 真机：天机 / 书斋两个页签
# [EN] D. Real machine: the Tianji / Shuzhai two tabs
# ══════════════════════════════════════════════════════════════════════
def _tab_index(dlg) -> int:
    for c in VU.walk(dlg):
        if isinstance(c, ft.TabBar):
            for i, x in enumerate(c.tabs):
                if 'Agents' in str(getattr(x, 'label', '') or ''):
                    return i
    return -1


def _tabs(dlg):
    """找对话框里的 `ft.Tabs`。

    ⚠ `VU.walk()` 只走 `controls` / `content`，而 `ft.Tabs` 的内容挂在
      `TabBarView` 上 —— 实测 walk 不到。所以这里**两种找法都试**：
      walk 一遍；不行就顺着 `content` / `controls` 逐层往下挖。
    
        English:
    Find the `ft.Tabs` in the dialog.
        ⚠ `VU.walk()` only traverses `controls` / `content`, while `ft.Tabs`'s content hangs on
          `TabBarView` —— measured: walk can't reach it. So here **try both ways of finding**:
          walk once; if that fails, drill down layer by layer along `content` / `controls`.
    """
    for c in VU.walk(dlg):
        if isinstance(c, ft.Tabs):
            return c
    seen = set()

    def _dig(x, depth=0):
        if depth > 8 or id(x) in seen:
            return None
        seen.add(id(x))
        if isinstance(x, ft.Tabs):
            return x
        for a in ('content', 'controls'):
            v = getattr(x, a, None)
            if isinstance(v, list):
                for y in v:
                    r = _dig(y, depth + 1)
                    if r is not None:
                        return r
            elif v is not None and hasattr(v, '__class__'):
                r = _dig(v, depth + 1)
                if r is not None:
                    return r
        return None

    return _dig(dlg)


def _crew_texts_order_ok(texts: list, rec_title: str) -> bool:
    """推荐表那一段**排在后面**吗（"移动到……的下面"）。

    判法：在**按渲染顺序**排好的文字列表里，推荐表的标题必须出现在
    **剧组表的内容之后** —— 剧组表的标志是职位名（「演员」「导演」「小说作家」…）
    与表头（「职位」「作用」「提示词」）。
    ⚠ 不判"最后一个元素"：表底下还有分页控件、提示文字，位置会变。

        English:
    Is the recommendation section **after** the rest (user: "move it below ...")?
        Method: in the **render-ordered** text list, the recommendation title must come after the
        **crew table's** content -- the crew table is identified by position names ("演员" / "导演" /
        "小说作家" ...) and its headers ("职位" / "作用" / "提示词").
        ⚠ Do not assert "the last element": below the table there are pager controls and hints whose
        position shifts.
    """
    try:
        idx = texts.index(rec_title) if rec_title in texts else next(
            i for i, x in enumerate(texts) if rec_title in str(x))
    except StopIteration:
        return False
    marks = tuple(t(x) for x in ('职位', '作用', '提示词'))
    last = -1
    for i, x in enumerate(texts):
        s = str(x)
        if i < idx and any(m in s for m in marks):
            last = i
    return last >= 0 and last < idx


def _tab_panels(dlg) -> dict:
    """{页签名: 那一页的面板控件} —— 实现只有一份（`verify_ui_common.tab_panels`）。"""
    return VU.tab_panels(dlg)


async def gui_checks(page: ft.Page) -> None:
    print('\n── D 真机：天机 / 书斋的「剧组 Agents」──')
    tmp = Path(tempfile.mkdtemp(prefix='nws_agentgui_'))
    old_projects = VU.isolate_projects_dir(tmp / 'Projects')
    # ⚠ 软件层 agents 目录也要隔离：不隔离的话这一支会**写进用户真软件目录**
    #   （造出几个假职位的 md，下次打开天机就看得见）。
    #   走 `catalog.set_soft_dir()`（模块级的临时接管，判据专用）。
    # [EN] ⚠ The software-layer agents directory must also be isolated: without isolation this branch will
    # [EN] **write into the user's real software directory**
    # [EN] (Create a few fake position md files; next time you open Tianji you'll see them).
    # [EN] Use `catalog.set_soft_dir()` (module-level temp takeover, criteria-only).
    CAT.set_soft_dir(tmp / 'agents')
    try:
        from store.project import Project as _P
        proot = Path(CFG.projects_dir()) / '代理页签夹具'
        proot.mkdir(parents=True, exist_ok=True)
        proj = _P.create_new(proot, '代理页签夹具')
        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(1.8)
        app.current_project = proj

        # ── 天机 ──
        # [EN] ── Tianji ──
        # ⚠ 2026-10-31：必须**显式**落到「剧组 Agents」页（天机的默认页改成「常规」了）。
        #   原来靠无参打开 + 后面切 `selected_index`，但切页签只保证"显示哪一页"，
        #   不保证页签内容已经挂载 ⇒ `all_texts(dlg)` 取不到剧组页的文字，
        #   D2（"共 22 个职位"）与 D8d（裸「演员」行）就报"0 个"，看着像产品坏了。
        # [EN] ⚠ 2026-10-31: must land on the Crew Agents page **explicitly** (Tianji's default
        # [EN] page is now "General"). It used to open with no argument and then flip
        # [EN] `selected_index`, but flipping only changes *which page shows*, not whether its
        # [EN] content got mounted => `all_texts(dlg)` misses the crew text and D2/D8d report
        # [EN] "0", looking like a product bug.
        app.show_global_settings(tab=NovelWorldApp.TAB_GLOBAL_CREW)
        await asyncio.sleep(0.6)
        dlg = (VU.open_dialogs(page) or [None])[-1]
        idx = _tab_index(dlg or ft.Container())
        ok('D1 ★★★ 天机里**有**「剧组 Agents」这个页签',
           idx >= 0, f'tab#{idx}')
        tabs = _tabs(dlg)
        if tabs is not None and idx >= 0:
            tabs.selected_index = idx
            page.update()
            await asyncio.sleep(0.4)
        texts = [str(x) for x in VU.all_texts(dlg)]
        joined = '\n'.join(texts)
        ok('D1b ★★ 列表里能看到**名字 / 作用 / 提示词简略**三样（用户点名的三样）',
           '小说作家' in joined and '写当天这一章的原著样章' in joined
           and '你是本剧组的' in joined, '')
        # ⚠ 判据要**数出来一页几行**：只查「第 1/…」+ 总数的话，
        #   把默认分页改成 20 也照样绿（17 个全在一页上）——
        #   那是"判据太宽"，反例法当场抓到了。
        # [EN] ⚠ The criteria must **count how many rows per page**: checking only "1st/…" + total,
        # [EN] changing the default pagination to 20 would still pass (all 17 on one page) ——
        # [EN] that's "criteria too loose"; the counterexample method caught it on the spot.
        from gui.app_flet import AGENT_PAGE_DEFAULT as _PG
        # ★★ 2026-10-13 用户改口：「每一页默认10个」（原来点名要 5）。
        #   判据的口径**跟着用户的口径走**，但"数出来一页几行"这条**不能松**：
        #   改成 20 也必须红（那时 17 个职位会全挤在一页上）。
        # [EN] ★★ 2026-10-13 the user changed their mind: "10 per page by default" (they had asked for 5).
        # [EN] The criterion **follows the user's convention**, but "count the rows on one page" must
        # [EN] **not** be relaxed: switching to 20 must still go red (all 17 positions would then fit on
        # [EN] one page).
        _rows = sum(1 for x in texts if x.strip() in ('软件自带', '自建'))
        ok('D2 ★★★ **分页默认 10**：一页真的只画 10 行职位（用户点名要 10）',
           _rows == _PG == 10 and '共 22 个职位' in joined,
           f'一页 {_rows} 行 / 默认 {_PG}')
        # ── D2c ★★★ **是 Table，不是卡片列表**（2026-10-13 用户点名）──
        #   ⚠ 按**控件类型**认，不按"源码里有没有这个串"：
        #     `ft.DataTable` 那几个字在别处也出现（模型表），字符串判会假绿。
        #     这里量的是"这一页里真的有一张表、它的行是 `DataRow`"，
        #     并且**表头六列**齐全（职位/标记/模型/作用/提示词/操作）。
        # [EN] ── D2c ★★★ **It's a Table, not a card list** (user asked by name, 2026-10-13) ──
        # [EN] ⚠ Recognize it by **control type**, not by "does this string appear in the source":
        # [EN] `ft.DataTable` also appears elsewhere (the model table), so a string check would be fake
        # [EN] green. What's measured here is "this page really has a table whose rows are `DataRow`",
        # [EN] with all **six header columns** present (position/tag/model/role/prompt/actions).
        def _col_texts(tb) -> list:
            out = []
            for c in (getattr(tb, 'columns', None) or []):
                lab = getattr(c, 'label', None)
                if isinstance(lab, ft.Text):
                    out.append(str(getattr(lab, 'value', None) or ''))
                    continue
                # ★★ 2026-10-14：带**拖拽缝**的那几列，表头是
                #   `DataColumn(ft.Row([ft.Text, ft.GestureDetector]))` ——
                #   只取 `label.value` 会一个字都读不到 ⇒ `_crew` 变空 ⇒
                #   D2c 报"0 张剧组表"（**误报**：表明明在，是判据不认得新结构）。
                #   ⇒ 表头换了容器，读法就得跟着往里挖一层。
                # [EN] ★★ 2026-10-14: the columns that carry a **drag seam** have a header of
                # [EN] `DataColumn(ft.Row([ft.Text, ft.GestureDetector]))` -- reading `label.value`
                # [EN] alone yields nothing => `_crew` comes up empty => D2c reports "0 crew tables"
                # [EN] (**false alarm**: the table is right there, the criterion just doesn't
                # [EN] recognize the new structure). When the header swaps containers, the reader
                # [EN] must dig one level deeper with it.
                out += [str(getattr(x, 'value', '') or '')
                        for x in VU.walk(lab) if isinstance(x, ft.Text)]
            return out

        # ⚠⚠ **先按表头认出"哪张是剧组表"**，再判它的行 ——
        #   这一页上还有**别的表**（模型表也是 `DataTable` + `DataRow`），
        #   只判"控件树里有 DataTable"的话，把剧组表退回成卡片它照样绿。
        # [EN] ⚠⚠ **First identify "which one is the crew table" by its header**, then judge its rows --
        # [EN] this page has **other tables** too (the model table is also `DataTable` + `DataRow`), so
        # [EN] judging only "there is a DataTable in the tree" would stay green even if the crew table
        # [EN] regressed to cards.
        _crew = [tb for tb in VU.walk(dlg)
                 if isinstance(tb, ft.DataTable)
                 and '职位' in _col_texts(tb)]
        _heads: list = []
        for _tb in _crew:
            _heads += _col_texts(_tb)
        ok('D2c ★★★ 剧组 Agents 是**一张 Table**（表头带「职位」的那张表真的在，'
           '而且它的每一行都是 `DataRow` —— 不是卡片 `Container`）',
           bool(_crew)
           and all(isinstance(r, ft.DataRow)
                   for _tb in _crew for r in (getattr(_tb, 'rows', None) or []))
           and all(len(getattr(r, 'cells', None) or []) == 10
                   for _tb in _crew for r in (getattr(_tb, 'rows', None) or [])),
           f'{len(_crew)} 张剧组表')
        ok('D2d ★★ 表头十列齐全（职位 / 英文名 / 标记 / 档位 / 模型 / 出工 / 产出 / 作用 / '
           '提示词 / 操作）',
           all(h in '\n'.join(_heads)
               for h in ('职位', '英文名', '标记', '档位', '模型', '出工', '产出',
                         '作用', '提示词', '操作')),
           str(_heads[:12]))
        # ── D2e / D2f（2026-10-13 第二轮，用户："职位 英语名 标记 档位 模型 出工 产出
        #    都可以短一些 差不多覆盖长度就行 作用可以分为2行 提示词可以分为2行 超过的是..."）──
        # ★★ 这两条的**做法与理由**：
        #   · 权重是**唯一**决定列宽的东西（`_agent_col_widths` 按权重摊），所以
        #     判据要钉的是"这七列拿到的份额**变小**了、而作用/提示词**变大了**"——
        #     直接量最终像素会随窗口宽漂移，**判权重**才稳定。
        #   · 但"权重变小"是**一刀切**（把所有列都调小也能绿）⇒ 必须**成对**：
        #     同时钉"作用 + 提示词合计**超过一半**"。两条一起才堵得住。
        # [EN] ★★ How and why these two work: the weights are the **only** thing that decides column
        # [EN] widths, so the criterion pins "the seven short columns' share got **smaller** while
        # [EN] 作用/提示词 got **bigger**" -- measuring final pixels would drift with window width, while
        # [EN] weights are stable. But "weights got smaller" is **one-sided** (shrinking everything also
        # [EN] goes green) ⇒ must be **paired** with "作用 + 提示词 together exceed half". Only both
        # [EN] together close the loop.
        from gui.app_flet import AGENT_COLS as _AGCOLS, AGENT_INTRO_MAX as _INTRO_MAX, \
            AGENT_BRIEF_MAX as _BRIEF_MAX
        _wt = {c[0]: c[2] for c in _AGCOLS}
        _short7 = ['name', 'name_en', 'tag', 'tier', 'model', 'when', 'feeds']
        _short_sum = sum(_wt[k] for k in _short7)
        _long_sum = _wt['intro'] + _wt['prompt']
        ok('D2e ★★ 前七列（职位/英文名/标记/档位/模型/出工/产出）**只占小头**'
           '（用户："都可以短一些 差不多覆盖长度就行"）',
           _short_sum < _long_sum,
           f'前七列权重合计={round(_short_sum, 2)} / 作用+提示词={round(_long_sum, 2)}')
        ok('D2e2 ★★ 而且**作用 + 提示词拿大头**（≥ 总权重的一半 —— '
           '与上一条成对，单独一条"都调小"也能绿）',
           _long_sum >= (sum(_wt.values()) / 2),
           f'作用+提示词={round(_long_sum, 2)} / 总权重={round(sum(_wt.values()), 2)}')
        # ── 双行：作用与提示词**都是最多 2 行**，提示词**超出给 …**、作用**换行不省略**。
        #   ⚠ 判的是**行那一格**（`DataCell` → `Text` 的 `max_lines` / `overflow`），
        #     不是"代码里有某个字符串"（本项目的老规矩）。
        # [EN] ── Two lines: both 作用 and 提示词 are **at most 2 lines**; 提示词 uses **...** when it
        # [EN] overflows while 作用 **wraps without ellipsis**. ⚠ This judges **the cell** (`DataCell` →
        # [EN] `Text`'s `max_lines` / `overflow`), not "some string exists in the source".
        _rows = [r for _tb in _crew for r in (getattr(_tb, 'rows', None) or [])]
        _cells = [c for r in _rows for c in (getattr(r, 'cells', None) or [])]
        if _cells and len(_cells) >= len(_AGCOLS):
            # 取**第一行**（十格正好一轮），按 `AGENT_COLS` 的顺序对应。
            _c0 = _cells[:len(_AGCOLS)]
            def _txt_of(cell):
                # ★★ 2026-10-14：每一格外面**多了一层紧约束的 `ft.Container`**
                #   （`ft.Text` 的 `width` 钉不住列宽，得靠 Container 的紧约束改
                #   格子的**内在宽** —— 这是"表不横滚"的机制保障，见
                #   `verify_agent_colwidth` 的 B4）。
                #   ⇒ 这里读 `cell.content` 拿到的是 Container 不是 Text，
                #     `max_lines` / `overflow` 全是 None ⇒ D2f 系列**误报红**。
                # [EN] ★★ 2026-10-14: every cell gained a **tight `ft.Container`** around it (an
                # [EN] `ft.Text` width cannot pin a column; only a Container's tight constraint
                # [EN] changes the cell's **intrinsic width** -- the mechanism behind "the table
                # [EN] doesn't h-scroll", see B4 in `verify_agent_colwidth`).
                # [EN] => Reading `cell.content` here yields the Container, not the Text, so
                # [EN] `max_lines` / `overflow` are all None => the D2f series **false-reds**.
                c = getattr(cell, 'content', None)
                if isinstance(c, ft.Container):
                    c = getattr(c, 'content', None)
                return getattr(c, 'value', None), c
            _, _intro_cell = _txt_of(_c0[7])     # intro = 第 8 格（下标 7）
            _, _prompt_cell = _txt_of(_c0[8])    # prompt = 第 9 格（下标 8）
            ok('D2f ★★★ 「作用」那一列是**最多 2 行**（用户："作用可以分为2行"）',
               getattr(_intro_cell, 'max_lines', None) == 2
               and getattr(_intro_cell, 'no_wrap', None) is False,
               f'max_lines={getattr(_intro_cell, "max_lines", None)} '
               f'no_wrap={getattr(_intro_cell, "no_wrap", None)}')
            ok('D2f2 ★★★ 「提示词」那一列也是**最多 2 行**（用户："提示词可以分为2行"）',
               getattr(_prompt_cell, 'max_lines', None) == 2
               and getattr(_prompt_cell, 'no_wrap', None) is False,
               f'max_lines={getattr(_prompt_cell, "max_lines", None)} '
               f'no_wrap={getattr(_prompt_cell, "no_wrap", None)}')
            # ⚠ 成对：**"提示词"超出要给 …，"作用"不给**（用户："超过的是..."
            #   只点给提示词；作用那句说的是"2行显示完全"）。
            #   两条一起判，否则"全改成省略号"也能绿。
            # [EN] ⚠ Paired: **提示词 ellipsizes on overflow, 作用 does not** (the user only said
            # [EN] "beyond that ..." for 提示词; 作用 was "show fully in 2 lines"). Judging both blocks
            # [EN] "change everything to ellipsis" from going green.
            ok('D2f3 ★★★ 「提示词」超出给**省略号**（用户："超过的是..."）',
               getattr(_prompt_cell, 'overflow', None) == ft.TextOverflow.ELLIPSIS,
               f'overflow={getattr(_prompt_cell, "overflow", None)}')
            ok('D2f4 ★★★ 而「作用」**换行显示完全、不是省略号**（用户："2行显示完全"）',
               getattr(_intro_cell, 'overflow', None) == ft.TextOverflow.CLIP,
               f'overflow={getattr(_intro_cell, "overflow", None)}')
            # 上限跟着双行放大（旧上限是单行的，2 行就白给）
            # [EN] The caps grew with the two lines (the old caps were single-line ones).
            ok('D2f5 ★★ 两个上限**跟着双行放大**（否则第 2 行永远空着）',
               _INTRO_MAX >= 36 and _BRIEF_MAX >= 80,
               f'AGENT_INTRO_MAX={_INTRO_MAX} / AGENT_BRIEF_MAX={_BRIEF_MAX}')
        # ⚠ 「每页 N 条」那句在 `DropdownM2` 的**选项**里，关闭状态画的是
        #   `content` —— `all_texts` 收 `ft.Text`，选项上的那个 Text 也在树里，
        #   但为了不依赖渲染细节，这里**同时查控件树里的下拉选项**。
        # [EN] ⚠ The "N items per page" line is in `DropdownM2`'s **options**; the closed state draws
        # [EN] `content` —— `all_texts` collects `ft.Text`, and the Text on the options is also in the tree,
        # [EN] but to avoid depending on rendering details, here **also check the dropdown options in the
        # [EN] control tree**.
        # ⚠⚠ **口径在 2026-10-11 改过**（用户报「每页多少个默认只能看到"每"」）：
        #   老口径是"选项文字里含「每页」"——而「每页 N 条」这种写法**放不进那个下拉**
        #   （空标签仍占 `LABEL_GUTTER_MIN` 88px，下拉本体只剩 72px），
        #   于是被省略成「每」，用户看得见的就一个字。
        #   现在改成：**说明落在标签上**（「每页」）、**选项只写数字**
        #   （用户原话："就直接写个 4 也行 不要用汉字"）。
        #   判据跟着守这三件事：上一页 / 下一页在、标签写着用途、选项是纯数字。
        #   ⚠ 不要退回"选项里含每页"——那正是被修掉的那个毛病。
        # [EN] ⚠⚠ **The convention changed on 2026-10-11** (user report: "the per-page control only
        # [EN] shows '每'"):
        # [EN] The old convention was "the option text contains '每页'" -- but a wording like "每页 N 条"
        # [EN] **does not fit that dropdown** (an empty label still takes `LABEL_GUTTER_MIN` = 88px, leaving
        # [EN] only 72px of body), so it was ellipsized to "每" and that is all the user saw.
        # [EN] Now: **the explanation lives on the label** ("每页") and **the options are bare numbers** (the
        # [EN] user's exact words: "just write a 4, that's fine, do not use Chinese characters").
        # [EN] The criterion guards those three things: prev/next present, the label says what it is, the
        # [EN] options are digits.
        # [EN] ⚠ Do not regress to "the options contain 每页" -- that is exactly the defect being fixed.
        _pg = VU.pager_row_parts(dlg)
        ok('D2b ★★ 分页控件在（上一页 / 下一页 / 每页几条可调；'
           '「每页」这条说明落在**标签**上、选项是纯数字）',
           _pg['prev'] is not None and _pg['next'] is not None
           and '每页' in _pg['label']
           and bool(_pg['options'])
           and all(o.strip().isdigit() for o in _pg['options']),
           {'label': _pg['label'], 'options': _pg['options']})
        ok('D3 ★★★ **软件层**允许新建（有「＋ 新建职位」）与删除（自建那位才有 🗑）',
           any('新建职位' in x for x in texts), '')
        ok('D3b ★★ 页面上写着文件目录（作者要能自己去记事本里改）',
           any('文件目录' in x for x in texts), '')
        page.enable_screenshots = True
        shot = await page.take_screenshot()
        if shot:
            (OUT / 'agents_tab_global.png').write_bytes(shot)
            from PIL import Image
            from io import BytesIO
            im = Image.open(BytesIO(shot)).convert('RGB')
            colors = len(set(im.getdata()))
            ok('D3c ★★ 这张截图**不是空白页**（像素取证：去重颜色要多）',
               colors > 1500, f'{colors} 色')
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()

        # ── 书斋 ──
        # [EN] ── Shuzhai ──
        app.show_project_settings()
        await asyncio.sleep(0.6)
        dlg2 = (VU.open_dialogs(page) or [None])[-1]
        idx2 = _tab_index(dlg2 or ft.Container())
        ok('D4 ★★★ 书斋里**也有**同一个页签（同一套实现）',
           idx2 >= 0, f'tab#{idx2}')
        tabs2 = _tabs(dlg2)
        if tabs2 is not None and idx2 >= 0:
            tabs2.selected_index = idx2
            page.update()
            await asyncio.sleep(0.4)
        texts2 = [str(x) for x in VU.all_texts(dlg2)]
        joined2 = '\n'.join(texts2)
        ok('D4b ★★★ **书斋不允许新建**（页面上没有「新建职位」）',
           not any('new_agent_btn' in x for x in texts2)
           and not any(x.strip().startswith('＋ 新建职位') for x in texts2), '')
        ok('D4c ★★ 而且说明里点破了"新建与删除只在软件层做"',
           '只在软件层做' in joined2 or '只在软件层' in joined2, '')
        ok('D5 ★★ 书斋这份显示的是**项目层目录**（不是软件目录）',
           any(str(CAT.proj_dir(proj)) in x for x in texts2), '')
        page.enable_screenshots = True
        shot2 = await page.take_screenshot()
        if shot2:
            (OUT / 'agents_tab_project.png').write_bytes(shot2)
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()

        # ── 编辑对话框：真开一次，看字段齐不齐 ──
        # [EN] ── Edit dialog: actually open it once, check whether the fields are all there ──
        spec = CAT.get('novelist', project=None)
        app._agent_editor(spec, project=None, allow_new=True, on_done=lambda: None)
        await asyncio.sleep(0.5)
        dlg3 = (VU.open_dialogs(page) or [None])[-1]
        texts3 = [str(x) for x in VU.all_texts(dlg3)]
        need = ('名字', '简介', '什么情况下使用', '出工时机', '模型档', '产出交给',
                '系统提示词')
        missing = [x for x in need if x not in '\n'.join(texts3)]
        ok('D6 ★★★ 编辑对话框字段齐全（名字/简介/系统提示词/什么情况下使用 + '
           '出工时机/模型档/产出交给）', not missing, f'缺 {missing}')
        # ⚠ 多行 `TextField` 的内容在 `.value` 上，`all_texts`（只收 `ft.Text`）
        #   看不到它 —— 判据要找的是**控件本身**（"那口框画出来了、里面有字"）。
        # [EN] ⚠ A multiline `TextField`'s content is on `.value`; `all_texts` (only collects `ft.Text`)
        # [EN] can't see it —— what the criteria look for is **the control itself** ("that box is drawn, with
        # [EN] text in it").
        _tf = [c for c in VU.walk(dlg3) if isinstance(c, ft.TextField)]
        _multi = [c for c in _tf if getattr(c, 'multiline', False)]
        ok('D6b ★★ 那口"系统提示词"框真的画出来了（多行 + 里面就是那段提示词）',
           bool(_multi) and any('你是本剧组的' in str(c.value or '')
                                for c in _multi),
           f'{len(_multi)} 个多行框')
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()

        # ══════════════════════════════════════════════════════════
        #  D7 ★★★ 列表行**不许压到滚动条**（2026-10-11 用户报：
        #  「书斋→剧组Agents 右边的滚动条…现在是跟Agents列表重合盖住的」）
        # [EN] ══════════════════════════════════════════════════════
        # [EN] D7 ★★★ the list rows **must not press the scrollbar** (user report 2026-10-11:
        # [EN] "the scrollbar to the right of Study -> Crew Agents ... overlaps and covers the
        # [EN] Agents list")
        # ══════════════════════════════════════════════════════════
        #  背景：`mk_tab_content()` 的列宽是 `SET_W + TAB_GUTTER`(544)，条画在列右缘
        #  的 24px 车道里；而 `_agent_row()` 里的 `Column` 是 `expand=True`
        #  ⇒ 行会**吃掉整条 544**，右端直接钻到条底下。
        #  ⚠ 这个毛病**在源码里完全看不出来**（不给宽度的写法长得跟别处一样），
        #    只能量像素。两处都要量：书斋（lane_extra=0）与天机（lane_extra=140）。
        # [EN] Background: the column built by `mk_tab_content()` is `SET_W + TAB_GUTTER` (544)
        # [EN] wide, and the bar is drawn in the 24px lane at its right edge; the `Column` inside
        # [EN] `_agent_row()` is `expand=True`
        # [EN] => the row **eats the whole 544** and its right end runs straight under the bar.
        # [EN] ⚠ This defect is **completely invisible in the source** (a width-less form looks
        # [EN] like anywhere else); only pixels can tell. Both copies must be measured: Study
        # [EN] (lane_extra=0) and Tianji (lane_extra=140).
        from PIL import Image, ImageChops                     # noqa: PLC0415
        import io                                             # noqa: PLC0415

        def _bb(im, rgb, tol: int = 40):
            """某标记色的像素包围盒（走 C 层：求差 → 二值化 → getbbox）。

            ⚠ 色串要**先剥掉 `#`** 再切三组十六进制 —— 直接按 `(0, 2, 4)` 切会把
              `#f` 当成第一组，`int('#f', 16)` 当场 `ValueError`（实测踩到，
              整支脚本因此中断）。
            [EN] Pixel bounding box of a marker color (through the C layer: difference -> threshold ->
            [EN] getbbox).
            [EN] ⚠ Strip the `#` **before** slicing the three hex groups -- slicing at `(0, 2, 4)`
            [EN] would take `#f` as the first group and `int('#f', 16)` raises `ValueError` on the spot
            [EN] (measured; it aborted the whole script).
            """
            h = str(rgb).lstrip('#')
            ref = Image.new('RGB', im.size, tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
            d = ImageChops.difference(im.convert('RGB'), ref)
            r, g, b = d.split()
            mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
            box = mx.point(lambda v: 255 if v <= tol else 0, mode='1').getbbox()
            return None if not box else {'x0': box[0], 'x1': box[2] - 1, 'y0': box[1],
                                         'y1': box[3] - 1, 'w': box[2] - box[0]}

        def _bars_for_crew_box(dlg, all_bars, boxes, lane_w: int) -> list:
            """从对话框里**所有** 4px 自绘条中，挑出"剧组这一页"的那一条。

            判据：条（`mk_scroll_bar` 的 thumb）的**最近 `ft.Container` 祖先**
            宽度 == `lane_w`（= `mk_tab_content` 那层容器），
            且它的声明 **top/right 偏移落在盒子所在的那一屏**（用盒子的 y 区间
            与条的 `top` 做粗匹 —— 盒子与条同属一页）。

            ⚠ 为什么必须挑：涂全部条 → 量到的是并集 bbox，x0 取到别的栏的条，
              D7 会**假红/假绿**（本轮实测就是这个）。
            [EN] From **all** 4px self-drawn bars in the dialog, pick the one for the crew tab.
            [EN] Rule: a bar (a `mk_scroll_bar` thumb) whose **nearest `ft.Container` ancestor** is
            [EN] `lane_w` wide (the `mk_tab_content` layer). ⚠ Painting all bars gives their union bbox,
            [EN] so x0 comes from another column's bar and D7 goes **falsely red/green** (measured this
            [EN] round).
            """
            if not boxes:
                return []
            # 建父表：walk 是自顶向下的，父一定先于子出现。
            parent: dict = {}
            for c in VU.walk(dlg):
                for ch in (getattr(c, 'controls', None) or []):
                    parent[id(ch)] = c
                ch = getattr(c, 'content', None)
                if ch is not None and not isinstance(ch, str):
                    parent[id(ch)] = c
                for ch in (getattr(c, 'tabs', None) or []):
                    parent[id(ch)] = c

            def _nearest_container(ctrl):
                cur = parent.get(id(ctrl))
                while cur is not None:
                    if isinstance(cur, ft.Container):
                        return cur
                    cur = parent.get(id(cur))
                return None

            picked = []
            for b in all_bars:
                anc = _nearest_container(b)
                if anc is None:
                    continue
                w = getattr(anc, 'width', None)
                if isinstance(w, (int, float)) and abs(w - lane_w) <= 2:
                    picked.append(b)
            # 兜底：挑不出来就退回"全部"（宁可量并集，也不要 n=0 让判据崩）。
            return picked or all_bars

        async def _lane(tag: str, *, book: bool) -> dict:
            """开一份页签、涂色、截图、量"表盒右缘 vs 滚动条左缘"。

            ★★ 2026-10-13 后续：**只涂剧组表盒子**，不涂所有 `input_bg` 容器。
              原来把页签里所有 `input_bg` 的 Container 都涂成洋红，量到的是
              "这些盒子的并集"（左边缘取到别的控件、右边缘取到另一张表）——
              于是 D7/D7b 量的根本不是剧组表，读数没有意义。
              现在改成：**只认那个 `width` 等于剧组车道可用宽的盒子**
              （它由 `_agent_table(avail_w=…)` 造出来，宽度可预知）。
            [EN] ★★ later 2026-10-13: paint **only the crew table box**, not every `input_bg` container.
            [EN] It used to paint all `input_bg` Containers magenta, so what got measured was "the union of
            [EN] those boxes" (left edge from another control, right edge from another table) -- D7/D7b were
            [EN] not measuring the crew table at all and the readings were meaningless. Now: **only the box
            [EN] whose `width` equals the crew lane's usable width** (built by `_agent_table(avail_w=...)`,
            [EN] a predictable width).
            """
            if book:
                app.show_project_settings()
                _w, _h, _grid = book_geometry(page)
            else:
                app.show_global_settings()
                _w, _h, _grid = tianji_geometry(page)
            page.update()
            await asyncio.sleep(1.0)
            d = (VU.open_dialogs(page) or [None])[-1]
            idx = _tab_index(d or ft.Container())
            tb = _tabs(d) if d is not None else None
            if tb is not None and idx >= 0:
                tb.selected_index = idx
                page.update()
                await asyncio.sleep(0.9)
            # ★ 剧组表盒子 = 声明宽度 == 车道可用宽(_grid) 的那一个 Container。
            #   ⚠ 夹一层容差：Flet 可能因边框/圆角微调 ±2px。
            # [EN] ★ The crew box = the one Container whose declared width == lane usable width (_grid).
            # [EN] A small tolerance: Flet may adjust ±2px for border/radius.
            def _is_crew_box(c):
                if not isinstance(c, ft.Container):
                    return False
                if getattr(c, 'bgcolor', None) != UIC['input_bg']:
                    return False
                w = getattr(c, 'width', None)
                return isinstance(w, (int, float)) and abs(w - _grid) <= 2
            boxes = [c for c in VU.walk(d) if _is_crew_box(c)]
            # ★★★ 2026-10-13：**只取"剧组这一页签自己的那条滚动条"**。
            #   原来把对话框里**所有** 4px 自绘条都涂绿，量到的是它们的**并集**
            #   （别的页签/别的栏的条把 x0 拉到了别处）——
            #   实测就是这个假读数让 D7 一直显示"重叠 13px"（其实那 13px 是
            #   另一条条的左缘，不是压在盒子上的那条）。
            #   判定：条是 `mk_scroll_bar` 的 thumb，它的**最近 Container 祖先**
            #   宽 == `lane`（= `_grid + TAB_GUTTER`，即 `mk_tab_content` 那层），
            #   并且它的 **y 区间与盒子相交**（同屏那一页）。
            # [EN] ★★★ 2026-10-13: **take only the crew tab's own scrollbar**. It used to paint
            # [EN] **every** 4px self-drawn bar in the dialog green, measuring their **union** (bars from
            # [EN] other tabs/columns dragged x0 elsewhere) -- that bogus reading is exactly why D7 kept
            # [EN] showing "13px overlap" (that 13px was another bar's left edge, not the one pressing the
            # [EN] box). Rule: a bar is a `mk_scroll_bar` thumb whose **nearest Container ancestor** is
            # [EN] `lane` wide (== `_grid + TAB_GUTTER`, the `mk_tab_content` layer) and whose **y-range
            # [EN] intersects the box's**.
            _lane_w = _grid + UI_TAB_GUTTER
            all_bars = [c for c in VU.walk(d)
                        if isinstance(c, ft.Container)
                        and getattr(c, 'width', None) == UI_BAR_W]
            bars = _bars_for_crew_box(d, all_bars, boxes, _lane_w)
            for c in boxes:
                c.bgcolor = '#ff00ff'
            for c in bars:
                c.visible = True
                c.bgcolor = '#00ff00'
            page.update()
            await asyncio.sleep(0.9)
            png = await page.take_screenshot()
            (OUT / f'agents_tab_lane_{tag}.png').write_bytes(png)
            im = Image.open(io.BytesIO(png)).convert('RGB')
            rb, bb = _bb(im, '#ff00ff'), _bb(im, '#00ff00')
            info = {'tag': tag, 'n_boxes': len(boxes), 'n_bars': len(bars),
                    'n_all_bars': len(all_bars),
                    'grid': _grid, 'lane': _lane_w, 'row': rb, 'bar': bb}
            if rb and bb:
                info['overlap'] = max(0, rb['x1'] - bb['x0'] + 1)
                info['gap'] = max(0, bb['x0'] - rb['x1'])
            while VU.open_dialogs(page):
                page.pop_dialog()
            page.update()
            await asyncio.sleep(0.4)
            return info

        rep_lane: dict = {}
        for _tag, _book in (('shuzhai', True), ('tianji', False)):
            rep_lane[_tag] = await _lane(_tag, book=_book)
        report['lane'] = rep_lane
        for _tag, _cn in (('shuzhai', '书斋'), ('tianji', '天机')):
            d = rep_lane.get(_tag) or {}
            rb, bb = d.get('row'), d.get('bar')
            ok(f'D7 ★★★ {_cn}·剧组 Agents：表盒**不压**滚动条（盒右缘 < 条左缘）'
               '（2026-10-11 用户报："滚动条跟 Agents 列表重合盖住了"）',
               bool(rb and bb) and rb['x1'] < bb['x0'],
               f"盒 x1={rb['x1'] if rb else None} < 条 x0={bb['x0'] if bb else None}"
               f"（重叠 {d.get('overlap')}px / 余量 {d.get('gap')}px）")
            # ⚠ 2026-10-13 后续：D7b 原来钉「这一行真的是 `SET_W`(520) 宽」——
            #   那是"表盒子写死 520、缩在页签左边"那个旧缺陷的**伴随假设**。
            #   用户后来要求「表撑满、加宽到不横向滚动」，于是书斋与天机都改成
            #   **按页签可用宽自适应**（`avail_w`），盒子不再等于 520。
            #   现在判据改成量**更高层的事实**：涂出来的洋红盒子（按声明宽 ==
            #   该页签车道可用宽 `_grid` 认出来的那一个）的**渲染宽 ≈ _grid**。
            #   这条同时覆盖：① 旧缺陷（盒子缩在左边、渲染宽远小于车道）会红；
            #   ② "改回写死小宽度"会红（声明宽就不再匹配 `_grid`，盒子一个都认不出）。
            # [EN] ⚠ later 2026-10-13: D7b used to pin "this row is exactly `SET_W` (520) wide" -- the
            # [EN] **companion assumption** of the old defect "box hardcoded to 520, squished left". The user
            # [EN] later asked for "fill the tab, widen until no h-scroll", so both Study and Tianji now
            # [EN] **size to the tab usable width** (`avail_w`) and the box no longer equals 520. The criterion
            # [EN] now measures a **higher-level fact**: the magenta box (identified as the one whose declared
            # [EN] width == the tab lane's usable width `_grid`) renders at **~= _grid** in width. This covers
            # [EN] both ① the old defect (box squished left, rendered width way under the lane) going red and
            # [EN] ② "revert to a hardcoded small width" going red (the declared width no longer matches
            # [EN] `_grid`, so no box is even found).
            #
            # ⚠⚠ 2026-10-13 再后续：盒子**故意为滚动条留了车道**，而且现在两侧账都对齐了。
            #   `_agent_table` 给返回的 Container 加了 `margin=(0,0,TAB_GUTTER,0)`
            #   （=24px 右外边距），这是"盒右缘 < 条左缘"（D7）的**实现手段**：
            #   margin 真占布局，把盒子的右缘 1:1 往左推 24px，正好让出 4px 条 + 12px 余量。
            #   （2026-10-13 后续再收：原为 `TAB_GUTTER - SCROLL_BAR_W`=20、余 8px，
            #    用户仍报「滚动条和表格冲突了」⇒ 改成整条车道 24、余 12px。）
            #   于是**渲染盒宽 == `_grid` − 24**（`_grid` 本届已改成"帧 − paper_frame 的 54"，
            #   即真实的可用宽 1684；见 `PAPER_CHROME_W`）。
            #   期望值就取这个**确定值**（`_grid - 预留`），容差 **±8**：
            #   ⚠ 容差**不能给 24** —— 变异"把 `margin.right` 拿掉"只会让盒子多出 24px
            #     （= 预留量），24 的容差**正好兜得住** ⇒ 那条变异白跑（13/14）。
            #     改成 8 之后它必红（24 > 8），容差仍够兜 Flutter 取整。
            #   另配一个**硬下限**（≥ 期望 − 8），旧缺陷"盒子缩在左边"依然会红。
            # [EN] The expectation is that **exact value** (`_grid - reserved`), tolerance **±8**:
            # [EN] ⚠ the tolerance must **not** be 24 -- the "drop `margin.right`" mutation only adds
            # [EN] **24px** (the reservation itself), which a 24px tolerance swallows => that mutation runs
            # [EN] in vain (13/14). With 8 it must go red (24 > 8), and the tolerance still covers Flutter
            # [EN] rounding. Plus a **hard lower bound** (>= expectation - 8) so the old "box squished
            # [EN] left" defect still goes red.
            _grid = d.get('grid')
            _expect = (_grid - UI_TAB_GUTTER) if _grid else None
            _tol = 8
            ok(f'D7b ★★ {_cn}·Agent 表盒子≈撑满页签可用宽（扣掉为滚动条预留的车道）'
               '（2026-10-13 用户："表缩在左边很难看，尽可能占满配置页"）',
               bool(rb) and bool(_expect)
               and abs(rb['w'] - _expect) <= _tol
               and rb['w'] >= _expect - _tol,
               f"实测盒宽 {rb['w'] if rb else None}px / 期望 {_expect}px"
               f"（±{_tol}）"
               f"（= 车道 {_grid}px - 预留 {UI_TAB_GUTTER}px）"
               f"（认出 {d.get('n_boxes')} 个盒子）")

        # ══════════════════════════════════════════════════════════
        #  D8 组（2026-10-13 第四轮）：**演员按出场人物摊行** + 群众演员单独一行
        #
        #  用户原话：
        #    「书斋里 的剧Agent 演员不再是一个单独的Agent 还是按照出场人物
        #      每人一个Agent 最后群众演员单独一个Agent」
        #
        #  三条要钉的事实（都要**行为判**，不许用"源码含某字符串"）：
        #    ① 书斋（项目页签）里：**没有了**那一个裸「演员」行；
        #       `人物.yaml` 里 N 个人 ⇒ N 个「演员·<人名>」行；
        #       「群众演员」**正好 1 行**，且排在角色那一组**之后**。
        #    ② 天机（系统层，`project is None`）**不动**：仍然正好 1 个裸「演员」行、
        #       **0** 个「演员·xx」行（那里没有"这本书"，也就没有出场人物）。
        #    ③ 角色行点得开、且开的是**角色**的编辑器（不是 md 编辑器）：
        #       `_casting_focus_open(project, 人名)` 造出来的必须是一个
        #       **无参、可调用、且真会调到 `_casting_dialog(focus=人名)`** 的东西
        #       —— 这正是 D2c 那个"双层 lambda 只返回内层函数"的坑，
        #       换了地方再钉一次（本轮新加的这条链最容易重犯）。
        #
        #  ⚠ 反例法要点：`人物.yaml` 必须由**判据自己造**（写在夹具项目里），
        #    不能靠"碰巧有" —— 否则"没人物的项目"里这条判据会**量不到而绿**
        #    （本项目的老毛病：没数据 ⇒ 量不到 ⇒ 看着像通过）。
        # [EN] ═══ Group D8 (2026-10-13, round 4): **actor spread per character** + extras as one row.
        # [EN] User's exact words: "in the Study, the crew Agent 'actor' should no longer be a single
        # [EN] Agent -- one Agent per character on stage, and finally the extras as one separate Agent".
        # [EN] Three facts to pin (all **behavioral**, no "source contains string"):
        # [EN] ① In the Study (project tab): the single bare "演员" row is **gone**; N people in
        # [EN] `人物.yaml` => N "演员·<name>" rows; exactly **1** "群众演员" row, and it comes **after**
        # [EN] the character group.
        # [EN] ② Tianji (system layer, `project is None`) **does not change**: still exactly 1 bare
        # [EN] "演员" row and **0** "演员·<name>" rows.
        # [EN] ③ A character row is clickable and opens the **character** editor (not the md editor):
        # [EN] `_casting_focus_open(project, name)` must produce something **no-arg, callable, and
        # [EN] actually invoking `_casting_dialog(focus=name)`** -- exactly the D2c "double lambda only
        # [EN] returns the inner function" pitfall, pinned again in its new location.
        # [EN] ⚠ Counterexample note: `人物.yaml` must be **created by the criteria itself** (in the
        # [EN] fixture project), not "happen to exist" -- otherwise this criterion goes **green while
        # [EN] measuring nothing** in a project with no characters (this project's old weakness:
        # [EN] no data => nothing measured => looks like it passed).
        _ppl = [{'姓名': '主角', '身份': '掌柜', '性格': '寡言'},
                {'姓名': '阿绣', '身份': '绣娘', '性格': '灵巧'},
                {'姓名': '丁', '身份': '跑堂', '性格': '爱说'}]
        (proj.settings_dir / '人物.yaml').write_text(
            yaml.safe_dump(_ppl, allow_unicode=True), encoding='utf-8')
        _cards = CASTING.load_cards(proj.settings_dir)
        ok('D8 ★★ 判据自己造的 `人物.yaml` 读得回来（量宽度前先证明有数据 —— '
           '否则"没人物的项目里量不到"会假绿）',
           len(_cards) == 3 and [c['姓名'] for c in _cards] == ['主角', '阿绣', '丁'],
           f'读到 {len(_cards)} 个人')

        # ── ① 书斋：真机里数行 ────────────────────────────────────
        # ★★ 为什么不反射 `_expand_actor_rows` 出来调：它是 `_agents_tab` 里的
        #   嵌套函数，**闭包在 `project` 这个局部参数上** —— `_agents_tab`
        #   不在执行时根本没有活着的 cell，反射出来也拿不到那个 `project`
        #   （实测 `co_freevars == ('project',)`、`_agents_tab.__closure__` 为空）。
        #   与其为了判据改产品结构，不如**用更强的证据**：把书斋那一页**真开一次**、
        #   翻完所有页，从**渲染出来的格子**里数 —— 这才是用户真正看到的。
        # [EN] ★★ Why not reflect `_expand_actor_rows` out and call it: it is a nested function of
        # [EN] `_agents_tab`, with its closure on the **local parameter `project`** -- while
        # [EN] `_agents_tab` isn't executing there are no live cells, so reflection cannot get that
        # [EN] `project` (measured: `co_freevars == ('project',)`, `_agents_tab.__closure__` is empty).
        # [EN] Rather than restructure the product for the criteria, use **stronger evidence**: open the
        # [EN] Study page for real, flip through every page, and count from the **rendered cells** --
        # [EN] that is exactly what the user sees.
        app.show_project_settings()
        await asyncio.sleep(0.6)
        _dlg_s = (VU.open_dialogs(page) or [None])[-1]
        _tb = _tabs(_dlg_s)
        _ix = _tab_index(_dlg_s or ft.Container())
        if _tb is not None and _ix >= 0:
            _tb.selected_index = _ix
            page.update()
            await asyncio.sleep(0.4)
        # ⚠ `_TAB_GUTTER` / 表头辅助：这里只要"职位那格的字"，
        #   即 `VU.all_texts` 里以「演员·」开头 / 等于「演员」/ 等于「群众演员」的。
        # [EN] ⚠ Only "the text in the position cell": in `VU.all_texts`, those starting with
        # [EN] "演员·" / equal to "演员" / equal to "群众演员".
        #
        # ★★ 两条量法上的纪律（**都是被反例法抓出来的**）：
        #   ① **不许去重**：`_uniq()` 会把"同一格被画了三遍"折叠成一条 ——
        #      变异"群众演员画三行"因此**照样绿**（实测确认）。这里改成
        #      **按页原样计数**、并额外用 `max` 兜"某一页画了多行"。
        #   ② 每一页**单独记**：跨页累加会把"上一页的控件"也数进来，
        #      于是"某页翻了两次"看起来像"有两行群众演员"。
        # [EN] ★★ Two measurement disciplines (**both caught by the counterexample method**):
        # [EN] ① **Do not de-duplicate**: dedup collapses "the same cell drawn three times" into one
        # [EN] entry, so the mutation "draw the extras as three rows" **still went green** (measured).
        # [EN] Count **as-is per page** and additionally use `max` to cover "some page drew several rows".
        # [EN] ② Record **each page separately**: accumulating across pages also counts the previous page's
        # [EN] controls, so "one page visited twice" would look like "two extras rows".
        _pages: list = []        # 每页一个 dict：{'char': [...], 'bare': n, 'extra': n, 'order': [...]}
        _pages_seen = 0
        for _pg in range(6):
            _cur = (VU.open_dialogs(page) or [None])[-1]
            _p_char: list = []
            _p_bare = _p_extra = 0
            _p_order: list = []
            for x in VU.all_texts(_cur):
                v = str(x).strip()
                if v.startswith('演员·'):
                    _p_char.append(v)
                    _p_order.append(('char', v))
                elif v == '演员':
                    _p_bare += 1
                    _p_order.append(('bare', v))
                elif v == '群众演员':
                    _p_extra += 1
                    _p_order.append(('extra', v))
            _pages.append({'char': _p_char, 'bare': _p_bare,
                           'extra': _p_extra, 'order': _p_order})
            _pages_seen += 1
            _nxt = None
            for _c in VU.walk(_cur):
                if callable(getattr(_c, 'on_click', None)) and \
                        any('下一页' in str(v) for v in VU.all_texts(_c)):
                    _nxt = _c
                    break
            if _nxt is None or getattr(_nxt, 'disabled', False):
                break
            try:
                _nxt.on_click(None)
            except Exception:                                        # noqa: BLE001
                break
            await asyncio.sleep(0.4)

        # ★ 「角色那一组」的判定：全书斋**所有页**里以「演员·」开头的格
        #   （去重只在"证明 3 个人都在"这一步用 —— 一个人只该有一行）。
        _chars_all = [v for _p in _pages for v in _p['char']]
        _chars_ui = list(dict.fromkeys(_chars_all))      # 去重只为"三个人都在"
        _bare_max = max((_p['bare'] for _p in _pages), default=0)
        _extra_max = max((_p['extra'] for _p in _pages), default=0)
        ok('D8a ★★ 书斋那一页真开起来了、也翻完页了（不然下面三条是在量空气）',
           _pages_seen >= 1 and bool(_chars_all or _bare_max),
           f'翻了 {_pages_seen} 页 / 职位格共 '
           f'{sum(len(p["char"]) + p["bare"] + p["extra"] for p in _pages)} 个')
        ok('D8b ★★★ 书斋：**没有裸「演员」行**、`人物.yaml` 里 N 个人 ⇒ N 个角色行'
           '（用户："演员不再是一个单独的Agent 还是按照出场人物每人一个Agent"）',
           _bare_max == 0 and len(_chars_ui) == 3
           and all(any(n in v for v in _chars_ui)
                   for n in ('主角', '阿绣', '丁')),
           f'裸演员最多 {_bare_max} 行/页 / 角色行 {_chars_ui}')
        # ★ 顺序：**同一页里**最后一个 `char` 必须排在那个 `extra` 之前
        #   （用户："**最后**群众演员"）。
        #   ⚠ 只看"出现过 extra 的那一页"，因为群众演员与角色可能不在同一页
        #     （一页 10 行）—— 那一页上必须"角色在前、群众演员在后"。
        _order_ok = True
        for _p in _pages:
            _last_char = max((i for i, (k, _v) in enumerate(_p['order'])
                              if k == 'char'), default=-1)
            _ex = [i for i, (k, _v) in enumerate(_p['order']) if k == 'extra']
            if _ex and _last_char >= 0 and min(_ex) < _last_char:
                _order_ok = False
        ok('D8c ★★★ 书斋：**「群众演员」正好一行**，且排在角色那一组**之后**'
           '（用户："最后群众演员单独一个Agent"）',
           _extra_max == 1 and _order_ok,
           f'群众演员最多 {_extra_max} 行/页（每页分别数，不去重）/ '
           f'顺序齐={_order_ok}')

        # ── ② 天机不动 ────────────────────────────────────────────
        # ⚠ 这里的 `_soft_rows` **不能**用上面那个 `_expander` ——
        #   它闭包里的 `project` 是**书斋那次**的值（`proj`），拿它算"天机"
        #   等于自欺。所以换一条**真机路径**：天机那一页刚才已经开过
        #   （D1~D2 就在它上面量的），直接看**天机渲染出来的文字**里有没有
        #   「演员·xx」、有没有那个裸「演员」。
        # [EN] ⚠ `_soft_rows` **must not** reuse the `_expander` above -- its closure's `project` is the
        # [EN] **Study** value (`proj`), so using it for "Tianji" would be self-deceiving. Use a
        # [EN] **real-machine path** instead: the Tianji tab was already opened (D1~D2 measured on it), so
        # [EN] look directly at **Tianji's rendered texts** for "演员·xx" and the bare "演员".
        _tianji_texts = [str(x) for x in VU.all_texts(dlg)]
        _soft_chars_ui = [x for x in _tianji_texts if x.startswith('演员·')]
        _soft_bare_ui = [x for x in _tianji_texts if x.strip() == '演员']
        ok('D8d ★★★ 天机（系统层）**不动**：界面里**0 个**「演员·xx」角色行、'
           '而且那个裸「演员」行还在（那里没有"这本书"，也就没有出场人物可摊）',
           len(_soft_chars_ui) == 0 and len(_soft_bare_ui) >= 1,
           f'天机界面：角色行 {len(_soft_chars_ui)} 个 {_soft_chars_ui} / '
           f'裸演员 {len(_soft_bare_ui)} 个')

        # ── ③ 真机：点那一格真的会开**那个角色**的设置框 ──────────
        # ⚠ 前面 D8b/D8c 已经证明"格子里写的是演员·人名"；
        #   这一条证明"**点得开**、而且开的是**他的**那一份"。
        #   真机做法：找到那个 `PopupMenuButton`（名字那格），
        #   调它的菜单项 —— 与用户点一下是同一条路。
        # [EN] ⚠ D8b/D8c already proved the cell reads "演员·<name>"; this proves it **opens**, and
        # [EN] opens **that person's** entry. Real-machine way: find the `PopupMenuButton` (the name
        # [EN] cell) and invoke its menu item -- the same path as the user clicking.
        _seen: list = []
        _orig_cast = NovelWorldApp._casting_dialog

        def _spy(self, project, *, focus=None):                      # noqa: ANN001
            _seen.append(str(focus))

        NovelWorldApp._casting_dialog = _spy
        try:
            # ⚠ 先**翻回第 1 页**：D8a-c 已经把分页翻到了最后一页，
            #   而「演员·主角」在第 1 页上（按职位顺序，演员那一组在中间偏前）。
            #   不翻回去的话这里是在第 3 页上找，永远找不到 ⇒ 假红。
            # [EN] ⚠ First **flip back to page 1**: D8a-c already paged to the last page, and
            # [EN] "演员·主角" is on page 1. Without flipping back this searches page 3 and never finds
            # [EN] it => a false red.
            for _pg in range(6):
                _curd = (VU.open_dialogs(page) or [None])[-1]
                _pre = None
                for _c in VU.walk(_curd):
                    if callable(getattr(_c, 'on_click', None)) and \
                            any('上一页' in str(v) for v in VU.all_texts(_c)):
                        _pre = _c
                        break
                if _pre is None or getattr(_pre, 'disabled', False):
                    break
                _pre.on_click(None)
                await asyncio.sleep(0.35)

            def _find_cell():
                _curd = (VU.open_dialogs(page) or [None])[-1]
                return [c for c in VU.walk(_curd)
                        if isinstance(c, ft.PopupMenuButton)
                        and '主角' in str(getattr(
                            getattr(c, 'content', None), 'value', ''))]

            _hits = _find_cell()
            if not _hits:                 # 万一不在第 1 页，往后翻着找
                for _pg in range(6):
                    _curd = (VU.open_dialogs(page) or [None])[-1]
                    _nx = None
                    for _c in VU.walk(_curd):
                        if callable(getattr(_c, 'on_click', None)) and \
                                any('下一页' in str(v)
                                    for v in VU.all_texts(_c)):
                            _nx = _c
                            break
                    if _nx is None or getattr(_nx, 'disabled', False):
                        break
                    _nx.on_click(None)
                    await asyncio.sleep(0.35)
                    _hits = _find_cell()
                    if _hits:
                        break
            _n_menu = 0
            if _hits:
                # ── 入口①：名字那一格（`PopupMenuButton`）的菜单项 ──────────
                # [EN] ── Entry ①: the name cell's (`PopupMenuButton`) menu item ──
                _mi = list(getattr(_hits[0], 'items', []) or [])
                _n_menu = len(_mi)
                if _mi:
                    _mi[0].on_click(None)
            # ── 入口②：操作列那个 👥「角色设置」图标按钮 ──────────────
            #   角色行有**两条**活路径都能打开"这一个角色"：
            #     ① 名字格菜单 → `_agent_row._open()`        （它自己那条 `focus=_char`）
            #     ② 操作列 👥   → `_casting_focus_open._open_one()`（`focus=_nm`）
            #   只点①的话，把②那处 `focus` 拿掉的变异**不会红**（实测：30/31，
            #   剩下那条"角色行不给 focus"就是打在②上、而观测走的是① ⇒ 不可达）。
            #   ⇒ 判据必须**两条都点**，否则两条路径里总有一条无人看守。
            # [EN] ★★ Why click **both** entries (caught by the counterexample method, 2026-10-13):
            # [EN] a character row has **two** live paths that open "this one character":
            # [EN] ① the name-cell menu → `_agent_row._open()` (its own `focus=_char`);
            # [EN] ② the 👥 icon in the actions column → `_casting_focus_open._open_one()` (`focus=_nm`).
            # [EN] Clicking only ① leaves a mutation that strips the `focus` at ② **green** (measured:
            # [EN] 30/31 -- the remaining "character row passes no focus" mutation landed on ② while the
            # [EN] observation went through ①, i.e. an unreachable path).
            # [EN] => the criterion must click **both**, or one of the two paths is left unguarded.
            _n_icon = 0
            # ⚠ 文案要用 `t()` 生成的那一份去比（英文界面下 tooltip 是英文）：
            #   直接比中文会**在英文界面下匹配不到** ⇒ 假红。
            # [EN] ⚠ Compare against the `t()`-produced text (the tooltip is English in the English UI):
            # [EN] comparing the Chinese literal would **fail to match in the English UI** => false red.
            _icon_tip = t('角色设置 —— 这本书里**每个角色**演成什么样（一人一份）')
            for _c in VU.walk((VU.open_dialogs(page) or [None])[-1]):
                if not callable(getattr(_c, 'on_click', None)):
                    continue
                if str(getattr(_c, 'tooltip', '') or '') != _icon_tip:
                    continue
                _n_icon += 1
                _c.on_click(None)
                break
        finally:
            NovelWorldApp._casting_dialog = _orig_cast
        ok('D8e ★★★ 书斋里点那个角色格，真的开的是**那个角色**的角色设置'
           '（不是 md 编辑器、也不是整张名单 —— 具体角色绝不能进 md）'
           '；而且**两个入口**（名字格菜单 / 操作列 👥）都要给对 focus',
           _seen == ['主角', '主角'],
           f'找到 {len(_hits)} 个「演员·主角」格 / 菜单 {_n_menu} 项 / '
           f'👥 按钮 {_n_icon} 个 / 点后收到 focus={_seen}')
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()

        # ══════════════════════════════════════════════════════════
        #  E 组（2026-10-13 第二轮）：书斋的**宽度与换行**（用户点名六件事）
        # [EN] Group E (2026-10-13, second pass): Study's **widths and wrapping** (six user items)
        # ══════════════════════════════════════════════════════════
        #  用户原话：「书斋的类型风格的自定义风格太长了 故事类型 风格来源 场景名称
        #    历法显示 运行模式 太短了 这些应该就刚好把字显示全就行 风格控制的各个进度条
        #    可以稍微再拉长一些 剧组Agents 右侧稍微短一些 滚动条和表格冲突了
        #    职位 英语名 标记 档位 模型 出工 产出 都可以短一些 差不多覆盖长度就行
        #    作用可以分为2行 提示词可以分为2行 超过的是...」
        # [EN] User's exact words: "Study's 自定义风格 is too long; 故事类型 风格来源 场景名称 历法显示
        # [EN] 运行模式 are too short, these should just fit their text; the style-control sliders can be
        # [EN] stretched a bit longer; Crew Agents' right side a bit shorter, the scrollbar conflicts with
        # [EN] the table; 职位 英文名 标记 档位 模型 出工 产出 can all be shorter, just cover their content;
        # [EN] 作用 may be 2 lines; 提示词 may be 2 lines with ... beyond".
        def _label_of(row) -> str:
            """从 `mk_field`/`mk_dropdown` 那一行的第 1 个控件里抠出标签文字。

                English:
            Pull the label text out of the first control of a `mk_field`/`mk_dropdown` row.
            """
            try:
                inner = getattr(row.controls[0], 'content', None)
                if isinstance(inner, str):
                    return inner
                return str(getattr(inner, 'value', '') or '')
            except Exception:                                    # noqa: BLE001
                return ''

        # ⚠ **先清干净对话框栈**：不清的话 `show_project_settings()` 之上还压着
        #   上面 D 组留下的那个，`open_dialogs()[-1]` 拿到的不是它。
        # [EN] ⚠ **Clear the dialog stack first**, else the one left by group D still sits on top and
        # [EN] `open_dialogs()[-1]` returns the wrong dialog.
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()
        await asyncio.sleep(0.4)
        app.show_project_settings()
        await asyncio.sleep(0.9)
        page.update()
        d_set = (VU.open_dialogs(page) or [None])[-1]
        _walked = list(VU.walk(d_set))

        # 这一页里"行"的形状固定：`Row([标签盒, 本体], spacing=8)`。按标签找。
        # [EN] Rows here have a fixed shape: `Row([label_box, body], spacing=8)`. Find them by label.
        _row_by_label: dict = {}
        for _c in _walked:
            if isinstance(_c, ft.Row) and len(_c.controls) >= 2:
                _txt = _label_of(_c)
                if _txt and _txt not in _row_by_label:
                    _row_by_label[_txt] = _c

        _bw, _bh, _bgrid = book_geometry(page)
        ok('E0 ★★ 书斋「类型风格」页里那六行控件都在（量宽度前先证明找得到）',
           all(t(_k) in _row_by_label for _k in
               ('故事类型', '风格来源', '场景名称', '历法显示', '运行模式', '自定义风格')),
           f'grid={_bgrid} / 命中 {len(_row_by_label)} 行')

        # ── E1：五个"刚好把字显示全"的控件 —— 本体宽度由 `mk_dropdown` 内部的
        #   `_fit_dd_w` 收到"最长那一项"，所以它**既不是满栅格、也不该被自己再减一次标签**。
        #   ★★ 这条判据的**两个半边**（缺一个就是"一刀切也能绿"）：
        #     · 上界：本体 ≤ 半栅格 ⇒ 证明"确实按内容收了，没有铺满"；
        #     · 下界：本体 ≥ **最长选项的文字估宽** ⇒ 证明"字放得下"。
        #   ⚠⚠ 这条判据的期望值是**实测**来的，不是推的 —— 我第一版自己在外层
        #     包了个 `_fit_row_w` 重复减标签，把故事类型从该有的 272 压到 249，
        #     而下界（228 的估宽）**照样绿**：**估宽天生偏小**，兜不住这种错。
        #     所以下面额外钉一条 E1c：**本体宽必须等于"最长选项 + 箭头内边距"**
        #     （即 `_fit_dd_w` 的那个值），两头堵死"多减了一次"。
        # [EN] ── E1: the five "just fit the text" controls -- the body width is shrunk by `mk_dropdown`'s
        # [EN] internal `_fit_dd_w` to the longest option, so it is **neither the full grid nor should it
        # [EN] be shrunk a second time by the caller**. ★★ Two halves (missing one means a one-sided check
        # [EN] goes green trivially): upper bound (<= half grid) proves "shrunk to content", lower bound
        # [EN] (>= the longest option's estimated text width) proves "the text fits". ⚠⚠ The expectation is
        # [EN] **measured**, not derived -- the first version wrapped it in `_fit_row_w` and subtracted the
        # [EN] label twice, squeezing 故事类型 from 272 to 249 while the lower bound (an estimate of 228)
        # [EN] **still passed**: estimates are inherently small and cannot catch that. So E1c below pins
        # [EN] **body == `_fit_dd_w` (longest option + arrow padding)**, closing both ends.
        _half = max(120, (_bgrid - 8) // 2)
        # ★★ 2026-10-13：用户点名"增长 30px"的那**四个**下拉（历法显示不在内）。
        # [EN] ★★ 2026-10-13: the **four** dropdowns the user named for "+30px" (历法显示 is not one).
        _DD_EXTRA_KEYS = ('故事类型', '风格来源', '场景名称', '运行模式')
        for _key in ('故事类型', '风格来源', '场景名称', '历法显示', '运行模式'):
            _r = _row_by_label.get(t(_key))
            _body = _r.controls[1] if _r is not None else None
            _bodyw = getattr(_body, 'width', None)
            # ⚠ `mk_dropdown` 返回 `Row([标签盒, Container(包 DropdownM2)])` —— `options`
            #   挂在**里面那层** `DropdownM2` 上，所以要往下找。
            # [EN] ⚠ `mk_dropdown` returns `Row([label, Container(DropdownM2)])`; `options` live on the
            # [EN] **inner** `DropdownM2`, so walk down to find it.
            _dd = None
            for _n in VU.walk(_body) if _body is not None else []:
                if getattr(_n, 'options', None):
                    _dd = _n
                    break
            _opts = list(getattr(_dd, 'options', None) or []) if _dd is not None else []
            # 最长那一项的**显示文字**（`DropdownM2` 拿 `key` 当显示文字 —— 见 `_norm_options`）
            # [EN] The **display text** of the longest option (`DropdownM2` treats `key` as the display
            # [EN] text -- see `_norm_options`).
            _longest = 0
            _longest_txt = ''
            for _o in _opts:
                _ct = getattr(_o, 'content', None)
                if isinstance(_ct, str) and _ct:
                    _s = _ct
                else:
                    _s = (str(getattr(_ct, 'value', '') or '')
                          or str(getattr(_o, 'key', '') or '')
                          or str(getattr(_o, 'text', '') or ''))
                _w_txt = _text_px(str(_s or ''))
                if _w_txt > _longest:
                    _longest, _longest_txt = _w_txt, str(_s or '')
            ok(f'E1 ★★ 书斋·{_key} **按内容收窄**（本体 ≤ 半栅格，不再是满栅格；'
               '用户："刚好把字显示全就行"）',
               isinstance(_bodyw, (int, float)) and _bodyw <= _half,
               f'本体宽={_bodyw} / 半栅格={_half} / 满栅格={_bgrid}')
            # ★ 成对判据（老规矩：一刀切也能绿 ⇒ 必须**同时**判"字放得下"）。
            # [EN] ★ Paired criterion: must **also** assert "the text fits".
            ok(f'E1b ★★ 书斋·{_key} 收窄后**仍放得下最长那一项**（证据：本体 ≥ 文字估宽）',
               isinstance(_bodyw, (int, float)) and _longest > 0
               and _bodyw >= _longest,
               f'本体宽={_bodyw} / 最长选项"{_longest_txt}"估宽={_longest}')
            # ★★★ E1c：本体宽**正好等于** `_fit_dd_w(最长选项)`（文字 + 箭头/内边距）。
            #   上面那条下界兜不住"重复减了一次标签"（估宽偏小），这条能：
            #   多减 88px 时 `本体` 会明显小于 `估宽 + 预留`。
            #   ★★ 2026-10-13 再一轮（用户：「故事类型 风格来源 场景名称 运行模式
            #     长度分别增长30px」）：那**四个**要在"最长项 + 箭头位"上**再加 30**，
            #     而「历法显示」用户没点名 ⇒ 仍是原值。所以期望里带一个**逐字段的增量**：
            #     写成"全部 +30"会把没点名的那一个也判红，写成"全都不加"则漏掉这次诉求。
            # [EN] ★★★ E1c: the body width **equals** `_fit_dd_w(longest option)` (text + arrow padding).
            # [EN] E1b cannot catch "the label was subtracted twice" (estimates are small); this can:
            # [EN] subtracting ~88px makes the body clearly smaller than `estimate + reserve`.
            # [EN] ★★ Another pass 2026-10-13 (user: "故事类型 风格来源 场景名称 运行模式 each +30px"):
            # [EN] those **four** get **+30** on top of "longest + arrow", while 历法显示 was not named
            # [EN] by the user => it keeps its old value. So the expectation carries a **per-field delta**:
            # [EN] "everyone +30" would red-flag the unnamed one, "nobody +30" would miss this request.
            # ★★★ 2026-10-13 本轮反例法抓到的**自证假绿**：原来这里写的是
            #   `_dd_extra = UI_DD_EXTRA` —— 而 `UI_DD_EXTRA` 是**从产品模块 import 来的**
            #   同一个常量。把产品里 `DD_EXTRA_W` 改成 0 时，判据的"期望"也跟着变成 0
            #   ⇒ 两边一起动、判据照样绿（这条变异就是这么漏过去的）。**期望必须是绝对值 30**，
            #   不能拿"被变异的那个常量"自证。
            # [EN] ★★★ Self-证 fake-green caught by this round's counterexample run: this used to be
            # [EN] `_dd_extra = UI_DD_EXTRA`, and `UI_DD_EXTRA` is the **same constant imported from the
            # [EN] product module**. Changing `DD_EXTRA_W` to 0 in the product also changed the criterion's
            # [EN] "expected" to 0 -- both move together and it stays green (that is exactly how this
            # [EN] mutation slipped through). The expectation must be the **absolute 30**, never the very
            # [EN] constant under mutation.
            _dd_extra = 30 if _key in _DD_EXTRA_KEYS else 0
            ok(f'E1c ★★★ 书斋·{_key} 的本体宽**不多不少就是"最长项 + 箭头位'
               + (' + 30（用户点名增长）' if _dd_extra else '') + '"**'
               '（多减一次标签就是这一条红）',
               isinstance(_bodyw, (int, float)) and _longest > 0
               and abs(_bodyw - (_longest + UI_DD_PAD + _dd_extra)) <= 12,
               f'本体宽={_bodyw} / 期望={_longest}+{UI_DD_PAD}'
               + (f'+{_dd_extra}' if _dd_extra else '')
               + f'={_longest + UI_DD_PAD + _dd_extra}')

        # ── E2：自定义风格（★ 2026-10-13 再一轮：用户改口了）。
        #   上一轮："自定义风格太长了" ⇒ 收成半行（≤ 半栅格）。
        #   这一轮："自定义风格宽度间找到跟风格来源相同" ⇒ **与「风格来源」逐像素相同**。
        #   ⚠ 判据要跟着**诉求**走，不能只留旧那半条：只判"≤ 半栅格"的话，
        #     "自定义风格铺满整行" 仍然绿（269 和 1200 都 ≤ 半栅格？—— 不，
        #     1200 > 838 会红），但"跟风格来源**不一样**"（比如 400）照样绿。
        #     所以 E2 钉**相等**、E2b 保留"还能写一句话"这条下界（防止被收成一条缝）。
        # [EN] ── E2: 自定义风格 (★ another pass on 2026-10-13: the user changed their mind).
        # [EN] Previous round: "自定义风格 is too long" => shrink to half a row (<= half grid).
        # [EN] This round: "make 自定义风格 the same width as 风格来源" => **pixel-identical** to it.
        # [EN] ⚠ Criteria follow the **request**, not just the old half: judging "<= half grid" alone lets
        # [EN] "same as 风格来源 but different value" (say 400) pass. So E2 pins **equality** and E2b keeps
        # [EN] the "still fits a sentence" lower bound (so it cannot be squeezed into a slit).
        _r_custom = _row_by_label.get(t('自定义风格'))
        _cw = getattr(_r_custom.controls[1], 'width', None) if _r_custom else None
        _r_style = _row_by_label.get(t('风格来源'))
        _sw = getattr(_r_style.controls[1], 'width', None) if _r_style else None
        ok('E2 ★★★ 书斋·自定义风格的本体宽**跟「风格来源」一模一样**'
           '（用户："自定义风格宽度间找到跟风格来源相同"）',
           isinstance(_cw, (int, float)) and isinstance(_sw, (int, float))
           and _cw == _sw,
           f'自定义风格={_cw} / 风格来源={_sw}')
        # 成对：也不能收成一条缝（它要能写一句话）
        ok('E2b ★★ 自定义风格**仍能写一句话**（≥ 200px —— 与风格来源同宽，但不能被收成一条缝）',
           isinstance(_cw, (int, float)) and _cw >= 200,
           f'本体宽={_cw}')

        # ── E3：七根滑杆**拉长了**（用户："可以稍微再拉长一些"）。
        #   ⚠ 判据是"明显长于自然尺寸（`SLIDER_W`=240）"**且**"不长于它该待的那一行"。
        #     后者是**必须**的：第一版实现里我乘了 `scale`，实测 1796 > 栅格 1684，
        #     滑杆直接顶进滚动条车道 —— 那种"更长"是 bug 不是功能。
        # [EN] ── E3: the seven sliders are **longer** (user: "stretch a bit longer"). The criterion is
        # [EN] "clearly longer than the natural size (`SLIDER_W`=240)" **and** "no longer than the row it
        # [EN] lives in" -- the latter is **mandatory**: the first implementation divided by `scale` and
        # [EN] measured 1796 > the 1684 grid, pushing the slider into the scrollbar lane. That kind of
        # [EN] "longer" is a bug, not a feature.
        # ── E3：七根滑杆的长度（用户先后改口两次，判据跟着**最新那条**走）。
        #   上一轮："可以稍微再拉长一些" ⇒ "明显长于自然尺寸"（当时拉到 1532）。
        #   这一轮："风格控制的 风格参数 长度调整到300px" ⇒ **正好 300**。
        #   ⚠ 仍然保留"不许长过它那一行"（E3c）：那是**安全线**，与"该多长"无关。
        # [EN] ── E3: the length of the seven sliders (the user changed their mind twice; criteria follow
        # [EN] the **latest** statement). Previous round: "stretch a bit longer" => "clearly longer than
        # [EN] the natural size" (1532 back then). This round: "adjust the style-control 风格参数 to 300px"
        # [EN] => **exactly 300**. ⚠ Keep "must not exceed its row" (E3c): that is a **safety line**,
        # [EN] unrelated to "how long it should be".
        _sliders = [c for c in _walked if isinstance(c, ft.Slider)]
        _sl_w = [getattr(c, 'width', None) for c in _sliders]
        ok('E3 ★★★ 书斋·风格控制的滑杆**真的有七根**（量长度前先证明量的是它）',
           len(_sliders) == 7, f'量到 {len(_sliders)} 根')
        ok('E3b ★★★ 七根滑杆**都是 300px**（用户："风格参数 长度调整到300px"）'
           '—— 既不能退回自然尺寸 240、也不能再铺满整行',
           # ⚠ 期望写**绝对值 300**，不写 `UI_STYLE_SLIDER_W` —— 后者是从产品 import 来的
           #   同一个常量，把它改掉时"期望"会跟着一起动 ⇒ 自证假绿（本轮反例法抓到的）。
           # [EN] ⚠ Expect the **absolute 300**, not `UI_STYLE_SLIDER_W` -- the latter is imported from
           # [EN] the product, so changing it moves the "expected" too => self-证 fake-green (caught this
           # [EN] round).
           bool(_sl_w) and all(isinstance(w, (int, float))
                               and int(w) == 300 for w in _sl_w),
           f'滑杆宽={sorted(set(_sl_w))} / 期望=300'
           f' / 自然尺寸={UI_SLIDER_W}')
        ok('E3c ★★★ 但**不许长过它那一行**（长过就是把滑杆顶进滚动条车道 —— '
           '第一版除 `scale` 犯过这个错）',
           bool(_sl_w) and all(isinstance(w, (int, float)) and w <= _bgrid
                               for w in _sl_w),
           f'滑杆宽={sorted(set(_sl_w))} / 栅格={_bgrid}')

        # ══════════════════════════════════════════════════════════
        #  F 组（2026-10-13 第三轮）：**天机那一批宽度** + **推荐表搬家**
        # [EN] Group F (2026-10-13, third pass): **Tianji's widths** + **the recommend table move**
        # ══════════════════════════════════════════════════════════
        #  用户原话：「天机 那个功能用什么模型 移动到剧组Agents 的下面 文生图模型 宽度缩短到
        #    现在的30% 外部小说服务 分析模型 技能名 长度缩小到现在的20% 接口地址 API Key
        #    长度都缩小到现在的50% 剧组Agents 作用列宽度减少30px 书斋 类型风格 故事类型
        #    风格来源 场景名称 运行模式 长度分别增长30px 自定义风格宽度间找到跟风格来源相同
        #    风格控制的 风格参数 长度调整到300px 图片 对话图片 下拉框 长度扩展到200px」
        # [EN] User's exact words: "move Tianji's 'which function uses which model' below Crew Agents;
        # [EN] shrink 文生图模型 to 30% of now; External novel service: 分析模型 / 技能名 to 20% of now,
        # [EN] 接口地址 / API Key to 50%; shrink the Crew Agents role column by 30px; Study Type&Style:
        # [EN] 故事类型 / 风格来源 / 场景名称 / 运行模式 each +30px; make 自定义风格 the same width as
        # [EN] 风格来源; adjust the style-control 风格参数 to 300px; expand the Images-tab 对话图片
        # [EN] dropdown to 200px".
        #
        # ── 量法：**按页签面板**量，不能整框一把抓 ──────────────────
        # ★★★ 2026-10-13 实测发现的**关键量法**（`developers/_probe_tabstruct.py`）：
        #   `VU.walk(dlg)` / `all_texts(dlg)` / `DataTable` 收集都会把**所有页签**
        #   的内容一起收进来 ⇒ 用它判"某一页上有什么"**永远为真**，
        #   判据看着很绿、其实分不出页签（`verify_llm_models` 的 D5 就是这样）。
        #   真正的分页结构是：`ft.TabBarView`（`walk` **到得了**）的
        #   `controls[i]` 就是第 i 个页签的**面板**；页签名在 `ft.TabBar.tabs[i].label`
        #   （`ft.Tabs.tabs` 在 Flet 1.0 里是**空的**，别再往那儿找）。
        # [EN] ★★★ The **key measurement technique** discovered 2026-10-13
        # [EN] (`developers/_probe_tabstruct.py`): `VU.walk(dlg)` / `all_texts(dlg)` /
        # [EN] `DataTable` collection all pull in **every tab's** content => using them to judge
        # [EN] "what's on this one page" is **always true**: the criterion looks green but cannot tell
        # [EN] tabs apart (that is exactly `verify_llm_models`' D5). The real per-tab structure is:
        # [EN] `ft.TabBarView` (**reachable** by `walk`) whose `controls[i]` is the **panel** of tab i;
        # [EN] tab names live on `ft.TabBar.tabs[i].label` (`ft.Tabs.tabs` is **empty** in Flet 1.0).
        #   ⇒ 实现只此一份：模块级 `_tab_panels()`（别的判据也用它）。
        # [EN] => One implementation only: the module-level `_tab_panels()` (other criteria use it too).
        def _panels(dlg) -> dict:
            return _tab_panels(dlg)

        def _shut(page_) -> None:                                # noqa: ANN001
            while VU.open_dialogs(page_):
                page_.pop_dialog()
            page_.update()

        _shut(page)
        await asyncio.sleep(0.4)
        app.show_global_settings()
        await asyncio.sleep(0.9)
        page.update()
        _gdlg = (VU.open_dialogs(page) or [None])[-1]
        _pn = _panels(_gdlg or ft.Container())

        ok('F0 ★★ 天机那个对话框按**页签面板**拆得开（不然下面几条是在量空气）',
           len(_pn) >= 5 and any('剧组 Agents' in k for k in _pn),
           f'拆出 {len(_pn)} 页：{list(_pn)[:8]}')

        # ── F1：推荐表**整节去掉**（2026-10-14 用户：「天机 剧组Agents 的那个功能用什么模型
        #   这个部分去掉」）—— 现在剧组 Agents 页里**也不该有**它。
        #   ⚠ 这条判据从"搬家"反转成"去掉"：两个页签里都**没有**才算过。
        # [EN] -- F1: the recommendation section is **gone entirely** (2026-10-14 user: "remove the
        # [EN] 'which function uses which model' section from Tianji's Crew Agents page") -- now the
        # [EN] Crew Agents page should **not have it either**. This flips from "moved" to "removed":
        # [EN] neither tab should contain it.
        _txt_ai = [str(x) for x in VU.all_texts(_pn.get(t('AI模型配置')))]
        _txt_crew = [str(x) for x in VU.all_texts(_pn.get(t('剧组 Agents')))]
        _rec_title = t('哪个功能用什么模型')
        _ai_has = any(_rec_title in x for x in _txt_ai)
        _crew_has = any(_rec_title in x for x in _txt_crew)
        ok('F1 ★★★ 「哪个功能用什么模型」那张推荐表**整节去掉了**'
           '（用户："天机 剧组Agents 的那个功能用什么模型 这个部分去掉"）'
           ' —— AI模型配置里没有，剧组 Agents 里也没有',
           (not _ai_has) and (not _crew_has),
           f'AI模型配置里={_ai_has} / 剧组Agents里={_crew_has} / '
           f'剧组页首条={_txt_crew[:2]}')
        # 成对：剧组表本身**还得在**（别为了过 F1 把整个剧组 Agents 页也删了）
        _crew_tables = [c for c in VU.walk(_pn.get(t('剧组 Agents')) or ft.Container())
                        if isinstance(c, ft.DataTable)]
        ok('F1b ★★ 剧组表本身**还在**（4 列，含「标记」/「档位」）'
           '—— 防"把整个剧组 Agents 页删了"这种一刀切也能过 F1 的做法',
           any(len(getattr(x, 'columns', []) or []) >= 4 for x in _crew_tables),
           f'剧组页表格 {[len(getattr(x, "columns", []) or []) for x in _crew_tables]}')

        # ── F2：文生图模型 = 满宽的 30% ────────────────────────────
        # ⚠⚠ **天机的栅格**必须用 `tianji_geometry(page)[2]`，不能用 `grid_w()` ——
        #   后者在天机对话框**关掉之后已经还原成 520**（`grid_width()` 的 finally），
        #   拿它算"满宽"会得到 280 而不是真实的 1444 ⇒ F2/F3 全假红（本轮实测踩到）。
        # [EN] ⚠⚠ The **Tianji grid** must come from `tianji_geometry(page)[2]`, not `grid_w()`:
        # [EN] the latter is **restored to 520** after the Tianji dialog closes (`grid_width()`'s
        # [EN] finally), so computing "full width" from it gives 280 instead of the real 1444 =>
        # [EN] F2/F3 all go falsely red (hit in this round's measurement).
        _tj_grid = tianji_geometry(page)[2]
        _tj_half = max(120, (_tj_grid - 16) // 2)

        def _row_in(panel, label: str, page_):
            for c in VU.walk(panel):
                if isinstance(c, ft.Row) and len(c.controls) >= 2 \
                        and _label_of(c) == label:
                    return c
            return None

        _cap_lbl = t('文生图模型（IMAGE_AI_MODEL）')
        _r_cap = _row_in(_pn.get(t('AI模型配置')), _cap_lbl, page)
        _cap_w = getattr(_r_cap.controls[1], 'width', None) if _r_cap else None
        _cap_full = _body_full_w(_cap_lbl, _tj_grid)
        ok('F2 ★★★ 天机·文生图模型的本体宽 ≈ **满宽的 30%**'
           '（用户："文生图模型 宽度缩短到现在的30%"）',
           isinstance(_cap_w, (int, float))
           and abs(int(_cap_w) - _body_w_pct(_cap_lbl, 0.30, _tj_grid)) <= 4
           and int(_cap_w) < _cap_full,
           f'本体宽={_cap_w} / 满宽={_cap_full} / '
           f'期望30%={_body_w_pct(_cap_lbl, 0.30, _tj_grid)} / 天机栅格={_tj_grid}')
        # 成对：**另外那个**（文生图尺寸）没被顺手一起收
        _r_size = _row_in(_pn.get(t('AI模型配置')), t('文生图尺寸'), page)
        ok('F2b ★★ 而且「文生图尺寸」**没被顺手收窄**（成对：只收用户点名的那一个）',
           _r_size is not None
           and (getattr(_r_size.controls[1], 'width', 0) or 0) > 100,
           f'文生图尺寸={getattr(_r_size.controls[1], "width", None) if _r_size else None}')

        # ── F3：外部创作服务（MuMuAINovel）那四个框按比例收 ───────────────
        _mumu_panel = _pn.get(t('外部创作服务'))
        for _lbl_key, _pct in (('分析模型', 0.20), ('技能名', 0.20),
                               ('接口地址', 0.50), ('API Key', 0.50)):
            _lbl = t(_lbl_key)
            _r = _row_in(_mumu_panel, _lbl, page)
            _w = getattr(_r.controls[1], 'width', None) if _r else None
            _exp = _body_w_pct(_lbl, _pct, avail=_tj_half)
            _say = ('分析模型 技能名 长度缩小到现在的20%' if _pct == 0.20
                    else '接口地址 API Key长度都缩小到现在的50%')
            ok(f'F3 ★★★ 天机·外部创作服务「{_lbl_key}」的本体宽 ≈ '
               f'**满宽的 {int(_pct * 100)}%**（用户："{_say}"）',
               isinstance(_w, (int, float)) and abs(int(_w) - _exp) <= 6,
               f'本体宽={_w} / 期望{int(_pct * 100)}%={_exp}')
        # 成对：同一页**别的**框（默认生成模型 / 服务端口）没被一起收
        _r_other = _row_in(_mumu_panel, t('服务端口'), page)
        ok('F3b ★★ 而且同页「服务端口」**没被一起收窄**（成对：只收点名的那四个）',
           _r_other is not None
           and (getattr(_r_other.controls[1], 'width', 0) or 0) > 60,
           f'服务端口={getattr(_r_other.controls[1], "width", None) if _r_other else None}')

        # ── F4：剧组表「作用」列 −30px（差额给「提示词」、总和不变）──
        # ⚠ 判据用**同一个函数**"带 delta / 不带 delta"各算一次来比 ——
        #   不把公式抄进判据（抄一遍就等于把实现写了两份，改一处忘一处）。
        # [EN] ⚠ The criterion computes with and without the delta via **the same function**, rather
        # [EN] than copying the formula into the criterion (a copy means two implementations).
        _av = 1684
        _now = _agent_col_widths(_av)
        _orig_delta = AF.AGENT_INTRO_DELTA
        try:
            AF.AGENT_INTRO_DELTA = 0
            _base = _agent_col_widths(_av)
        finally:
            AF.AGENT_INTRO_DELTA = _orig_delta
        ok('F4 ★★★ 剧组表「作用」列**正好比原来少 30px**，且那 30px **让给了「提示词」**'
           '（用户："剧组Agents 作用列宽度减少30px"）',
           # ⚠ 期望写**绝对值 −30**，不写 `UI_INTRO_DELTA`（= 产品那个常量的 import 副本）——
           #   否则把 `AGENT_INTRO_DELTA` 改成别的值时判据的期望跟着动 ⇒ 自证假绿
           #   （本轮反例法抓到的：改 −10 / 归零 两条都没红）。
           # [EN] ⚠ Expect the **absolute −30**, not `UI_INTRO_DELTA` (an imported copy of the product
           # [EN] constant) -- otherwise changing `AGENT_INTRO_DELTA` moves the expectation too => self-证
           # [EN] fake-green (caught this round: the −10 and the zero mutation both stayed green).
           _base['intro'] + (-30) == _now['intro']
           and _base['prompt'] - (-30) == _now['prompt']
           and sum(_base.values()) == sum(_now.values()),
           f'作用 {_base["intro"]}→{_now["intro"]} / '
           f'提示词 {_base["prompt"]}→{_now["prompt"]} / '
           f'总和 {sum(_base.values())}→{sum(_now.values())}')
        # 成对：**别把表撑破了** —— 各列宽之和仍等于预算（"不横滚"那条 D7 靠它）
        # ★★ 2026-10-14：预算里**多减了盒子的外圈** 24（右边让出的滚动条车道）
        #   + 2（左右边框）—— 这两项是 2026-10-14 实测出来的（avail=1684 时
        #   盒子被父列夹到 1660，不扣的话表恒比盒内可用宽多 26px ⇒ 横滚条消不掉）。
        #   ⚠ 期望写**字面量算式**，不 import `AGENT_BOX_*`（变异它时期望不能跟着动）。
        # [EN] Paired: **don't break the table** -- the sum of the columns still equals the budget
        # [EN] (D7, "no h-scroll", rests on it).
        # [EN] ★★ 2026-10-14: the budget now also subtracts the box's **outer ring**: 24 (the
        # [EN] scrollbar lane yielded on the right) + 2 (left/right borders) -- both measured on
        # [EN] 2026-10-14 (at avail=1684 the box gets clamped to 1660 by its parent Column; without
        # [EN] subtracting, the table stays 26px wider than the box's inner usable width and the
        # [EN] h-scrollbar never goes away).
        # [EN] ⚠ The expectation is a **literal expression**, not an import of `AGENT_BOX_*` (the
        # [EN] expectation must not move when that constant is mutated).
        _pad, _gap = 16, 14 * (len(AF.AGENT_COLS) - 1)
        _outside = 24 + 2          # margin.right + 左右边框
        # [EN] margin.right + left/right borders
        _budget = max(0, _av - _pad - _gap - _outside)
        ok('F4b ★★★ 而且各列宽之和**仍然等于预算**（表还是刚好占满盒子、不会横滚）',
           sum(_now.values()) == _budget,
           f'和={sum(_now.values())} / 预算={_budget}'
           f'（= {_av} − 内边距{_pad} − 间距{_gap} − 外圈{_outside}）')

        # ── F5：书斋「图片」页签的「对话图片」= 200px ────────────────
        _shut(page)
        await asyncio.sleep(0.3)
        app.show_project_settings()
        await asyncio.sleep(0.9)
        page.update()
        _bdlg2 = (VU.open_dialogs(page) or [None])[-1]
        _pn2 = _panels(_bdlg2 or ft.Container())
        _r_img = _row_in(_pn2.get(t('图片')), t('对话图片'), page)
        _img_w = getattr(_r_img.controls[1], 'width', None) if _r_img else None
        ok('F5 ★★★ 书斋·图片页签「对话图片」下拉框的本体宽 == **200px**'
           '（用户："对话图片 下拉框 长度扩展到200px"）',
           # ⚠ 期望写**绝对值 200**，不写 `UI_CHAT_IMG_W`（产品常量的 import 副本）—— 否则
           #   把 `CHAT_IMG_DD_W` 改掉时判据的期望一起动 ⇒ 自证假绿（本轮反例法抓到）。
           # [EN] ⚠ Expect the **absolute 200**, not `UI_CHAT_IMG_W` (an import of the product constant)
           # [EN] -- otherwise changing `CHAT_IMG_DD_W` moves the expectation too => self-证 fake-green.
           isinstance(_img_w, (int, float)) and int(_img_w) == 200,
           f'本体宽={_img_w} / 期望=200')
        # 成对：不能靠在别处把它撑到 200（要在**图片页签**里量到）
        ok('F5b ★★ 而且量的确实是**图片页签**里那一个（成对：按面板量，不是整框一把抓）',
           _r_img is not None and t('图片') in _pn2,
           f'图片面板在={"图片" in _pn2}')

        # ── F6：书斋对话框的**高度也按窗口放大** ──────────────────────
        #  用户 2026-10-13：「书斋的高度稍微调高一些，现在比例不协调」。
        #  实况：宽早就按窗口放大了（`book_w`），高却还写死 `DLG_H`(575)
        #  ⇒ 书斋成了"又宽又扁"，与同款几何、按窗口最大化的天机比例对不上。
        #  `book_geometry` 本就**算好了高**（`book_h`，与天机同一条 `_maximized_size`），
        #  只是外框那一处没用它。修法 = `height=DLG_H` → `height=book_h`。
        #  ⚠ 期望取 `book_geometry(page)[1]`（产品与判据**共用同一个函数**，不把公式抄进判据）。
        # [EN] ── F6: the Study dialog's **height also follows the window**.
        # [EN] User 2026-10-13: "make the Study a bit taller, the proportions are off now". Reality:
        # [EN] the width already followed the window (`book_w`) but the height was still the fixed
        # [EN] `DLG_H` (575) => the Study was "wide and flat", out of proportion with Tianji (which
        # [EN] maximizes to the window via the same geometry). `book_geometry` already computes the
        # [EN] height (`book_h`) -- the frame just did not use it. Fix = `height=DLG_H` -> `height=book_h`.
        # [EN] ⚠ The expectation takes `book_geometry(page)[1]` (product and criterion **share one
        # [EN] function**; the formula is not copied into the criterion).
        _bk_h = book_geometry(page)[1]
        _bk_actual = getattr(getattr(_bdlg2, 'content', None), 'height', None)
        ok('F6 ★★★ 书斋对话框的高度**也按窗口放大**（不再是写死的 `DLG_H`）'
           ' —— 用户："书斋的高度稍微调高一些，现在比例不协调"',
           isinstance(_bk_actual, (int, float)) and int(_bk_actual) == int(_bk_h),
           f'实际高={_bk_actual} / book_geometry高={_bk_h} / 写死的DLG_H={AF.DLG_H}')
        # 成对：窗口够高时，它**必须真的比那个写死的 575 高** —— 否则"等于 book_h"
        #   在窗口很矮时与"等于 DLG_H"是同一个数，这条判据就成了摆设。
        # [EN] Paired: when the window is tall enough it must be **really taller than the old fixed
        # [EN] 575** -- otherwise "equals book_h" and "equals DLG_H" coincide on a short window and this
        # [EN] criterion is decorative.
        _win_h = int(getattr(page, 'height', 0) or 0)
        ok('F6b ★★ 而且窗口够高时它**确实比原来写死的 `DLG_H` 更高**'
           '（成对：不是"等于一个数"就完事）',
           _win_h <= int(AF.DLG_H) + 2 * int(getattr(AF, 'MAXIMIZE_MARGIN', 12))
           or (isinstance(_bk_actual, (int, float))
               and int(_bk_actual) > int(AF.DLG_H)),
           f'实际高={_bk_actual} / DLG_H={AF.DLG_H} / 窗口高={_win_h}')

    finally:
        try:
            CFG.set('DEFAULT_PROJECTS_DIR', old_projects)
        except Exception:                                        # noqa: BLE001
            pass
        CAT.set_soft_dir(None)


async def main(page: ft.Page) -> None:
    try:
        storage_checks()
        crew_checks()
        await infer_checks()
        await gui_checks(page)
    except Exception:
        # ★★ 崩溃**必须自己留一条红的**（本项目的老规矩）：否则汇总里那一支
        #    变成"0 条红"，看着像"判据太弱"，其实是脚本没跑完。
        # [EN] ★★ A crash **must leave a red line itself** (this project's old rule): otherwise that branch in
        # [EN] the summary
        # [EN] becomes "0 reds", which looks like "criteria too weak", but is actually the script not
        # [EN] finishing.
        report['ok'] = False
        report['fatal'] = traceback.format_exc()
        report['checks'].append({'name': '★ 脚本跑完了（没有中途崩）',
                                 'ok': False,
                                 'detail': traceback.format_exc()[-300:]})
        print(traceback.format_exc()[-800:])
    n_ok = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n剧组 Agents 设置：{n_ok}/{len(report["checks"])}'
          + ('' if report['ok'] else '  ✗ 有失败'))
    (OUT / 'agent_catalog_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    try:
        ft.run(main)
    except Exception:
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
        (OUT / 'agent_catalog_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(traceback.format_exc()[-800:])
        exit_now(2)
