# -*- coding: utf-8 -*-
"""**演员的四层设置**（2026-10-11）。

用户原话：
    「演员Agent在系统层面是没有具体角色的 但是在项目层面是有具体角色的
      演员Agent在系统全局设置（天问）中如何设置和在项目级别如何设置
      你要仔细思考下怎么配置」

答案（也是本判据的分组依据）——按"换什么它才变"分四层：

| 层 | 存在哪 | 放什么 | 换什么它才变 | 界面入口 |
|---|---|---|---|---|
| ① 系统·职位 | `agents/actor.md` | 演员**这个工种**怎么干活 | 换软件版本 | 天机·剧组 Agents |
| ② 系统·类型库 | `actors/archetypes.yaml` | **预写好的各种演员**怎么说话 | 换软件版本 | 天机·剧组 Agents →「演员类型库」 |
| ③ 项目·剧组 | `<项目>/agents/actor.md` | 这**一部戏**的演法基调 | 换书 | 项目·剧组 Agents |
| ④ 项目·**角色** | `<项目>/设定集/人物.yaml` | **张三这个人**演成什么样 | 换人 | 项目·剧组 Agents →「角色设置」 |

★★★ 一条**硬约束**（架构级，不是偏好）：
  **④ 绝不能写进 ①②③ 任何一份 md** —— 一份 md 是**全组通读**的，
  把"张三高冷、李四热情"写进去 = 让每个角色读到别人的设定（串台）。
  D 组 + `mutate_actor_layers` 都盯着它。

四组：
  A 数据层：写类型库**不毁注释**、写角色卡**不动别人**（行级编辑）
  B 提示词：给作者的话**不进**提示词、给模型的话**进**、四层都在
  C 界面接线：两个入口真的接了、且各自只在**该出现的层**出现
  D 真机：两个对话框真能打开、真有内容、真能存下去

跑法：`.venv\\Scripts\\python.exe tools\\verify_actor_layers.py`
产出：`assets/screenshots/actor_layers_report.json`

English:
**The actor's four-layer settings** (2026-10-11).
The user's exact words:
    "The actor Agent has no specific role at the system level, but at the project level it does have a specific role
      How should the actor Agent be configured in the system global settings (Tianwen) and how at the project level
      you need to think carefully about how to configure it"
Answer (which is also the basis for this criterion's grouping) —— divided into four layers by
"what has to change for it to change":
| Layer | Where it lives | What goes in | What has to change for it to change | UI entry |
|---|---|---|---|---|
| ① System · Position | `agents/actor.md` | How actors **as a job type** work | Change software version | Tianji · Crew Agents |
| ② System · Type library | `actors/archetypes.yaml` | How **the various pre-written actors** speak | Change software version | Tianji · Crew Agents → "Actor Type Library" |
| ③ Project · Crew | `<project>/agents/actor.md` | The acting tone for **this one show** | Change book | Project · Crew Agents |
| ④ Project · **Character** | `<project>/设定集/人物.yaml` | How **this person Zhang San** is acted | Change person | Project · Crew Agents → "Character Settings" |
★★★ A **hard constraint** (architecture-level, not a preference):
  **④ must never be written into any md of ①②③** —— a single md is **read by the whole group**,
  writing "Zhang San is aloof, Li Si is warm" into it = letting every character read others' settings (crosstalk).
  Group D + `mutate_actor_layers` both watch for it.
Four groups:
  A Data layer: writing the type library **does not destroy comments**, writing character cards **does not touch others** (line-level editing)
  B Prompt: words for the author **do not enter** the prompt, words for the model **do enter**, all four layers present
  C UI wiring: the two entries are really wired, and each appears only in the **layer where it should appear**
  D Real machine: both dialogs really open, really have content, can really be saved
How to run: `.venv\\Scripts\\python.exe tools\\verify_actor_layers.py`
Output: `assets/screenshots/actor_layers_report.json`
"""
from __future__ import annotations

import asyncio
import io
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import flet as ft                                     # noqa: E402

import verify_ui_common as VU                         # noqa: E402
from util.flet_shutdown import shutdown               # noqa: E402

from config import CFG                                # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')
VU.redirect_env_writes()

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}

_JPEG = None                                          # 占位，别删（见下 Pixel 段）
# [EN] Placeholder, do not delete (see the Pixel section below)


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'\n        {str(detail)[:220]}' if (detail and not cond) else ''))
    return bool(cond)


def read(rel: str) -> str:
    p = APP / rel
    return p.read_text(encoding='utf-8', errors='replace') if p.is_file() else ''


def between(text: str, start: str, end: str = '') -> str:
    i = text.find(start)
    if i < 0:
        return ''
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j if j > 0 else len(text)]


def _tmp_types_copy(tmp: Path) -> Path:
    """把**真的**类型库复制一份到临时目录，改的是副本（绝不碰产品文件）。
        English:
    Copy the **real** type library to a temporary directory, and edit the copy (never touch product
    files).
    """
    d = tmp / 'actors'
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(APP / 'actors' / 'archetypes.yaml', d / 'archetypes.yaml')
    return d / 'archetypes.yaml'


# ══════════════════════════════════════════════════════════════════
#  A 数据层
# [EN] A Data layer
# ══════════════════════════════════════════════════════════════════
def data_checks(tmp: Path) -> None:
    print('\n── A 数据层：写库不毁东西 ──')
    from actors import casting as C

    # ── 类型库 ──
    # [EN] ── Type library ──
    p = _tmp_types_copy(tmp)
    real_path = C._types_path
    C._types_path = lambda: p                          # 临时接管（判据不动产品文件）
    # [EN] Temporary takeover (criteria do not touch product files)
    try:
        names = C.type_names()
        ok('A1 ★★ 类型名**不含**非类型的顶层键（`名称:`/`来源:`/`适用:`…）'
           '—— 混进来界面就会把它们当"演员类型"列出来',
           bool(names) and not ({'名称', '来源', '适用', '匹配表', '年龄表',
                                 '_DEFAULT'} & set(names)), names[:6])
        raw0 = p.read_text(encoding='utf-8')
        comments0 = [ln for ln in raw0.splitlines() if ln.startswith('#')]
        others0 = C._type_block('老年·疯癫')
        target = names[3] if len(names) > 3 else names[0]
        okk, why = C.save_type(target, {'骨架': '改过的骨架。\n第二行。',
                                       '变奏': ['甲', '乙', '丙']})
        raw1 = p.read_text(encoding='utf-8')
        comments1 = [ln for ln in raw1.splitlines() if ln.startswith('#')]
        ok('A2 ★★★ 改一型之后，**文件头那一大段设计注释逐字不变**'
           '（整块替换的全部意义就在这儿 —— `yaml.safe_dump` 会把它抹掉）',
           okk and comments0 == comments1 and len(comments0) > 30,
           f'改前 {len(comments0)} 行 / 改后 {len(comments1)} 行')
        ok('A2b ★★★ 而且**别的类型一个字节都没动**',
           C._type_block('老年·疯癫') == others0, '')
        ok('A2c ★★ 改的那一型真的读得到新值',
           C.entry(target).get('骨架', '').strip().startswith('改过的骨架')
           and len(C.variants(target)) == 3,
           f'{C.entry(target).get("骨架")!r:.40} / {C.variants(target)}')
        ok('A2d ★★ 写之前留了备份（作者能自己捞回来）',
           (p.parent / (p.name + '.bak')).is_file(), '')
        name_new = '测试·自建型'
        okk2, why2 = C.save_type(name_new, {'骨架': '一个自建的类型。',
                                            '句长': '短', '变奏': ['一', '二', '三']},
                                 create=True)
        ok('A3 ★★ 能**新建**一型（作者可以加自己需要的那一类演员）',
           okk2 and name_new in C.type_names(), why2)
        okk3, _w3 = C.save_type(name_new, {}, create=True)
        ok('A3b ★ 已存在的类型**不许**用"新建"再盖一遍（返回失败 + 说明）',
           not okk3, '')
        okk4, _w4 = C.save_type('不存在的型·xyz', {'骨架': 'x'}, create=False)
        ok('A3c ★ 改一个不存在的类型 → 失败（不静默新建）', not okk4, '')
    finally:
        C._types_path = real_path
        C.load(force=True)

    # ── 角色卡（人物表）──
    # [EN] ── Character cards (person table) ──
    sd = tmp / 'proj' / '设定集'
    sd.mkdir(parents=True, exist_ok=True)
    f = sd / C.PEOPLE_FILE
    f.write_text(
        '# 作者手写的注释\n'
        '- 姓名: 甲\n  身份: 长子\n  性格: 沉稳\n  自定义字段: 别动我\n'
        '\n'
        '- 姓名: 乙\n  身份: 次女\n  性格: 爽利\n'
        '\n'
        '- 姓名: 丙\n  身份: 老仆\n  性格: 唠叨\n', encoding='utf-8')
    ok('A4 ★★ 读得到人物表（且 `card_fields` 认英文别名）',
       [c['姓名'] for c in C.load_cards(sd)] == ['甲', '乙', '丙'],
       str([c['姓名'] for c in C.load_cards(sd)]))
    f.write_text(f.read_text(encoding='utf-8').replace(
        '- 姓名: 乙\n', '- 姓名: 乙\n  archetype: 青年·高冷\n'), encoding='utf-8')
    ok('A4b ★★ 人物卡里手写的英文别名 `archetype:` 也认（否则"我写了它却说没有"）',
       C.card_fields(C.load_cards(sd)[1])['演员类型'] == '青年·高冷',
       str(C.card_fields(C.load_cards(sd)[1])))

    #  ⚠ `other_before` **必须在这里取**（A4b 往"乙"里插了一行之后）——
    #    第一版在 A4b 之前就取了，于是 A5 拿"插过行的乙"去比"没插过的快照"，
    #    当场假红（判据自己的时序错，不是产品的错）。
    # [EN] ⚠ `other_before` **must be taken here** (after A4b inserts a line into "B") ——
    # [EN] The first version took it before A4b, so A5 compared "B with the inserted line" against "a
    # [EN] snapshot without the insertion",
    # [EN] and went false-red on the spot (the criterion's own timing was wrong, not the product's fault).
    other_before = f.read_text(encoding='utf-8').split('- 姓名: 乙')[1]
    okk5, why5 = C.write_card(sd, '甲', {
        '演员类型': '青年·高冷', '变奏': '冷在防（怕被看穿）',
        '选角': '对账房才多说两句', '打破类型': '他其实话很多'})
    raw = f.read_text(encoding='utf-8')
    ok('A5 ★★★ 写一个角色是**行级编辑**：别的角色逐字不动',
       okk5 and raw.split('- 姓名: 乙')[1] == other_before, why5)
    ok('A5b ★★★ 作者手写的注释也在（整文件 `yaml.dump` 会把它抹掉）',
       '# 作者手写的注释' in raw, '')
    ok('A5c ★★ 别的字段（`自定义字段:`）没被动',
       '自定义字段: 别动我' in raw, '')
    ok('A5d ★★ 写完读得回来（往返一致）',
       C.card_fields(C.load_cards(sd)[0]) == {
           '演员类型': '青年·高冷', '变奏': '冷在防（怕被看穿）',
           '选角': '对账房才多说两句', '打破类型': '他其实话很多'},
       str(C.card_fields(C.load_cards(sd)[0])))
    ok('A5e ★★ 写前留了备份', (sd / (C.PEOPLE_FILE + '.bak')).is_file(), '')
    C.write_card(sd, '甲', {'演员类型': '青年·高冷', '变奏': '',
                            '选角': '', '打破类型': ''})
    raw2 = f.read_text(encoding='utf-8')
    seg = raw2.split('- 姓名: 乙')[0]
    ok('A6 ★★ **清空 = 删掉那一行**（不留 `变奏:` 这种空壳）',
       '演员类型: 青年·高冷' in seg and '变奏:' not in seg
       and '选角:' not in seg and '打破类型:' not in seg, seg)
    okk6, _w6 = C.write_card(sd, '不存在的人', {'演员类型': 'x'})
    ok('A6b ★★ 写一个不在表里的人 → 失败并说明（不新建一条）',
       not okk6 and '不存在的人' not in f.read_text(encoding='utf-8'), '')
    f.write_text('# 只有注释没有人物\n', encoding='utf-8')
    ok('A6c ★ 人物表是空的（只有注释）→ 写入失败，**且注释没被弄坏**',
       not C.write_card(sd, '甲', {'演员类型': 'x'})[0]
       and '# 只有注释没有人物' in f.read_text(encoding='utf-8')
       and C.load_cards(sd) == [], '')


# ══════════════════════════════════════════════════════════════════
#  B 提示词（四层各就各位 / 给作者的话不进提示词）
# [EN] B Prompt (four layers each in place / words for the author do not enter the prompt)
# ══════════════════════════════════════════════════════════════════
async def prompt_checks(tmp: Path) -> None:
    print('\n── B 提示词：谁进、谁不进 ──')
    from actors import casting as C
    from crew import catalog as CAT
    from sim import directive as D

    # ── ① 职位层：给作者的话（HTML 注释）**不进**提示词 ──
    # [EN] ── ① Position layer: words for the author (HTML comments) do **not** enter the prompt ──
    blk = CAT.prompt_block('actor')
    ok('B1 ★★★ 给**作者**看的那段说明（`<!-- ... -->`）**不进提示词**'
       '—— 它是"别把角色写在这里"这种话，对模型毫无意义，还会被当成约束',
       '<!--' not in blk and '具体**角色**不要写进' not in blk, blk[:120])
    ok('B1b ★★★ 而给**模型**的那段正文**在**（"你不是一个固定的人"）',
       '你不是一个固定的人' in blk, '')
    ok('B1c ★★ 剥注释也不会把正文剥空（还有本职位的身份/职责/边界）',
       '你是本剧组的' in blk and '职责：' in blk and len(blk) > 80, '')

    # ── ①b **盘上那份 md 的正文真的生效**（2026-10-11 修的一个真 bug）──
    # [EN] ── ①b **the body text of that md on disk actually takes effect** (a real bug fixed on
    # [EN] 2026-10-11) ──
    #
    #  ★ 这条判据是**为一个真 bug 立的碑**：`catalog._MUTABLE` 原来漏了 `'prompt'`
    #    （它是 md 的**正文**，不属于 frontmatter 的 `FIELD_KEYS`），于是
    #    `_apply()` 读盘时把 prompt 塞进 fields、`merged_with()` 又把 it 静默过滤掉
    #    ⇒ **`agents/*.md` 的正文从来没生效过**：在「天机 · 剧组 Agents」里改
    #      系统提示词、或用记事本改 md，都是白改（用的是内存里那份默认的）。
    #    变体 `M20` 会把这个 bug 重新种回去。
    # [EN] ★ This criterion is **a monument erected for a real bug**: `catalog._MUTABLE` originally missed
    # [EN] `'prompt'`
    # [EN] (it is the **body** of the md, not part of frontmatter's `FIELD_KEYS`), so
    # [EN] when `_apply()` read from disk it stuffed prompt into fields, and `merged_with()` then silently
    # [EN] filtered it out
    # [EN] ⇒ **the body of `agents/*.md` never took effect**: editing in "Tianji · Crew Agents"
    # [EN] the system prompt, or editing the md with Notepad, was all for nothing (it used the in-memory
    # [EN] default copy).
    # [EN] Variant `M20` will re-plant this bug.
    CAT.set_soft_dir(tmp / 'agentsA7')
    try:
        CAT.seed_soft()
        f1 = tmp / 'agentsA7' / 'novelist.md'
        raw1 = f1.read_text(encoding='utf-8')
        f1.write_text(raw1.replace('职责：', '【哨兵】职责：'), encoding='utf-8')
        blk1 = CAT.prompt_block('novelist')
        ok('A7 ★★★ 在盘上 md 里改**正文** → 真的进了提示词'
           '（改系统提示词这件事不能是假按钮）',
           '【哨兵】' in blk1, blk1[:90])
        ok('A7b ★★★ 而"给作者看的说明"（HTML 注释）照旧**不进**提示词',
           '<!--' not in blk1 and '这一段注释不会发给模型' not in blk1, '')
        # 项目层**只改了名字**时，软件层的真正文**不许**被占位符顶掉
        # [EN] When the project layer **only changed the name**, the software layer's real body text **must
        # [EN] not** be displaced by the placeholder
        proj2 = tmp / 'projA7'
        CAT.save_project(proj2, 'novelist', name='主笔')
        s2 = CAT.get('novelist', project=proj2)
        ok('A7c ★★★ 项目层**只改了名字**时，软件层的正文**不被占位符顶掉**'
           '（稀疏写入那份文件里躺着"banner + （还没写系统提示词）"）',
           '【哨兵】' in (s2.prompt or '') or '你是本剧组的' in (s2.prompt or ''),
           repr((s2.prompt or '')[:70]))
    finally:
        CAT.set_soft_dir(None)

    # ── ② 类型库层：在最终提示词里，且排在角色定制**之前** ──
    # [EN] ── ② Type library layer: in the final prompt, and ordered **before** character customization ──
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU
    proj = make_project(tmp / '演员四层')
    run = RunFolder(proj.root, '第1次模拟2026-10-11-10-00').create()
    _loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)
    name = next(iter(world.people))
    ps = world.people[name]
    ps.archetype = '青年·高冷'
    ps.variant = '冷在防（怕被看穿，对熟人话就多）'
    ps.casting_note = '对账房才多说两句'
    ps.break_type = '他其实话很多'
    from agent.core import Agent
    ag = Agent(ps, db, world)
    static = ag._persona_static_only()
    i_pre = static.find('你这一类演员')
    i_cus = static.find('在这个本子里')
    i_arb = static.find('以角色为准')
    ok('B2 ★★★ 类型库那一层**真的进了**人格式（`〔你这一类演员 · 青年·高冷〕`）',
       i_pre > 0 and '青年·高冷' in static, static[:160])
    ok('B2b ★★★ 角色定制那一层也在，而且排在类型**之后**'
       '（越靠后越具体、越该压过前面）',
       i_cus > i_pre > 0, f'类型@{i_pre} 角色@{i_cus}')
    ok('B2c ★★★ 仲裁规则**在最后**（读完两层立刻读到"冲突时以角色为准"）',
       i_arb > i_cus > 0, f'仲裁@{i_arb}')

    # ── ③ 四层同框：抓**真发出去的 messages** ──
    # [EN] ── ③ Four layers in one frame: capture the **messages actually sent out** ──
    import llm.router as R
    seen: list = []
    _orig = R.llm.chat

    async def fake(tier, messages, **kw):
        if kw.get('purpose') == 'agent_decide':
            seen.append([dict(m) for m in messages])
        return await _orig(tier, messages, **kw)
    R.llm.chat = fake
    D.attach(world, '这三天先埋一个误会')
    try:
        await ag.decide('')
    finally:
        R.llm.chat = _orig
    txt = ' '.join(str(m.get('content') or '') for m in (seen[-1] if seen else []))
    ok('B3 ★★★ **四层在同一个提示词里同框**：'
       '①职位（你不是一个固定的人）②类型库（你这一类演员）'
       '③项目角色（身份/选角细读）④作者建议（作者对这一轮的走向要求）',
       bool(seen) and all(k in txt for k in
                          ('你不是一个固定的人', '你这一类演员',
                           '在这个本子里', '作者对这一轮的走向要求')),
       f'采到 {len(seen)} 次；长度 {len(txt)}')
    ok('B3b ★★★ 而给作者的那段说明**不在**真发出去的提示词里（端到端再证一次）',
       '<!--' not in txt and '具体**角色**不要写进' not in txt, '')

    # ── ④ 改写人物卡 → 下一轮装配真的变了（④ 层生效）──
    # [EN] ── ④ Rewrite character card → the next assembly round really changes (layer ④ takes effect) ──
    from actors import casting as C2
    C2.write_card(proj.settings_dir, name, {'演员类型': '老年·疯癫', '变奏': '',
                                            '选角': '', '打破类型': ''})
    run2 = RunFolder(proj.root, '第2次模拟2026-10-11-11-00').create()
    _l2, world2, _d2 = SU.assemble(proj, run2, image_hook=lambda *a, **k: None)
    ok('B4 ★★★ 在**角色卡**上写的演员类型，下一轮装配真的照它选角'
       '（④ 层不是摆着看的）',
       getattr(world2.people.get(name), 'archetype', '') == '老年·疯癫',
       str(getattr(world2.people.get(name), 'archetype', '')))


# ══════════════════════════════════════════════════════════════════
#  C 界面接线（源码）
# [EN] C UI wiring (source)
# ══════════════════════════════════════════════════════════════════
def wiring_checks() -> None:
    print('\n── C 界面接线 ──')
    g = read('gui/app_flet.py')
    tab = between(g, 'def _agents_tab(', 'def _agent_pager(')
    ok('C1 ★★★ 天机页签上有**「演员类型库」**入口，而且真的调它',
       "mk_btn(t('演员类型库')" in tab
       and 'self._actor_types_dialog()' in tab, '')
    ok('C1b ★★ 类型库那个对话框**真的读写** `casting`（不是只读的展示窗）',
       'CASTING.type_names()' in between(g, 'def _actor_types_dialog(', 'def _actor_type_editor(')
       and 'CASTING.save_type(' in between(g, 'def _actor_type_editor(',
                                           'def _casting_dialog('),
       '')
    ok('C2 ★★★ **只有项目页签**给演员挂「角色设置」'
       '（天机里没有"这本书"可谈，给了就是假按钮）',
       "project is not None and s.key == 'actor'" in tab, '')
    ok('C2b ★★★ 角色设置真的落到 **④ 角色层**（`write_card` → 人物表）',
       'CASTING.write_card(' in between(g, 'def _casting_editor(',
                                       'def _agent_delete('), '')
    ok('C3 ★★★ 两处都写明了分工（"具体角色不要写在这里"）'
       '—— 这是防串台的**第一道**（第二道是架构本身）',
       '具体角色不要写在这里' in tab
       and '具体角色' in between(g, 'def _casting_dialog(', 'def _casting_editor('),
       '')
    ok('C3b ★★ 角色设置里说明了**下一轮**起生效（本轮设定集已冻结）',
       '下一轮' in between(g, 'def _casting_dialog(', 'def _casting_editor('), '')
    # 架构级硬约束：角色**不许**从 md 那条路进提示词
    # [EN] Architecture-level hard constraint: characters **must not** enter the prompt via the md path
    ok('C4 ★★★ 角色层的字段只从 `casting` 那一条路进提示词'
       '（`_persona_static_only` 用 `_cast_block`；不是从 prompt_block）',
       'self._cast_block()' in read('agent/core.py')
       and 'CASTING.prompt_block(c, card)' in read('agent/core.py'), '')
    i = read('i18n.py')
    ok('C5 ★★ 新文案中英都有', "'演员类型库':" in i and "'角色设置 · {n}':" in i, '')


# ══════════════════════════════════════════════════════════════════
#  D 真机
# [EN] D Real machine
# ══════════════════════════════════════════════════════════════════
async def gui_checks(page, tmp: Path) -> None:
    print('\n── D 真机：两个入口真能开、真有内容 ──')
    VU.isolate_projects_dir(tmp / 'Projects')
    # 用量台账指到临时库（真起界面会记账）
    # [EN] Point the usage ledger at a temporary DB (launching the real UI will record to it)
    from llm import usage as _U
    _U.db_path = lambda: tmp / 'usage.db'
    from verify_run_control import make_project
    from gui.app_flet import NovelWorldApp
    from actors import casting as C

    proj = make_project(tmp / '真机角色项目')
    C.write_card(proj.settings_dir, '主角', {'演员类型': '青年·高冷', '变奏': '',
                                            '选角': '', '打破类型': ''})
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    await asyncio.sleep(1.8)
    app.current_project = proj

    def _btn(root, icon=None, text=None, tip=None):
        """按文字 / 图标 / tooltip 找控件。

        ⚠ 加了 `tip`：`mk_icon_btn` 造的那个小图标按钮，它的 tooltip 是
          **一句话**（"角色设置 —— …"）—— 按图标名找要依赖 Flet 的
          `Icon.name` 恰好等于 `ft.Icons.XXX`（能成立，但脆）。
          按 tooltip 找是**按人看得见的字**找，稳得多。
        
                English:
        Find controls by text / icon / tooltip.
                ⚠ Added `tip`: the small icon button created by `mk_icon_btn`; its tooltip is
                  **a single sentence** ("Role settings -- ...") -- finding it by icon name requires Flet's
                  `Icon.name` to be exactly equal to `ft.Icons.XXX` (this holds, but it's brittle).
                  Finding by tooltip is finding by **what a human can see**, which is far more robust.
        """
        for c in VU.walk(root):
            if getattr(c, 'on_click', None) is None:
                continue
            if text is not None and VU.text_of(c) == text:
                return c
            if tip is not None and tip in str(getattr(c, 'tooltip', '') or ''):
                return c
            if icon is not None:
                for x in VU.walk(c):
                    if isinstance(x, ft.Icon) and getattr(x, 'name', '') == icon:
                        return c
        return None

    def _titles() -> list:
        out = []
        for d in VU.open_dialogs(page):
            # ⚠ `ft.Text` 是控件不是 dict —— 第一版写了 `x.get('value')`，
            #   当场 `AttributeError`（整个真机组崩成一条红）。
            #   读控件的字一律走 `VU.ctrl_text`（它连 `spans` 一起收）。
            # [EN] ⚠ `ft.Text` is a control, not a dict —— the first version wrote `x.get('value')`,
            # [EN] and got an `AttributeError` on the spot (the whole real-machine group crashed into one red
            # [EN] line).
            # [EN] Always read control text via `VU.ctrl_text` (it collects `spans` as well).
            out += [VU.ctrl_text(x) for x in VU.walk(d)
                    if isinstance(x, ft.Text) and VU.ctrl_text(x)]
        return out

    # ── ① 天机页签 → 演员类型库 ──
    # [EN] ── ① Tianji tab → actor type library ──
    soft = app._agents_tab(project=None, allow_new=True)
    page.update()
    await asyncio.sleep(0.6)
    btn = _btn(ft.Column(soft), text=app_t('演员类型库'))
    ok('D1 ★★★ 天机页签上**找得到**「演员类型库」按钮', btn is not None, '')
    if btn is not None:
        n0 = len(VU.open_dialogs(page))
        btn.on_click(None)
        page.update()
        await asyncio.sleep(1.2)
        ok('D1b ★★★ 点它**真的弹出**类型库对话框',
           len(VU.open_dialogs(page)) > n0, f'层数 {n0} → {len(VU.open_dialogs(page))}')
        t = _titles()
        ok('D1c ★★ 库里列着真实的类型（含「青年·高冷」这种）',
           any('青年·高冷' in x for x in t), str(t[:6]))
        ok('D1d ★★ 而且写明"这是系统层 / 不管演谁"（分工说清）',
           any('系统层' in x for x in t) and any('不管演谁' in x for x in t),
           str([x for x in t if '演' in x][:4]))
        # 点一个类型 → 编辑框
        # [EN] Click a type → edit box
        row = None
        for c in VU.walk(VU.open_dialogs(page)[-1]):
            if getattr(c, 'on_click', None) is not None and isinstance(
                    getattr(c, 'content', None), ft.Row):
                if any('青年·高冷' == str(x) for x in VU.all_texts(c)):
                    row = c
                    break
        ok('D1e ★★ 找得到某一型那一行（下面两条靠它）', row is not None, '')
        if row is not None:
            row.on_click(None)
            page.update()
            await asyncio.sleep(1.0)
            t2 = _titles()
            ok('D1f ★★ 点开一型 → 编辑框里带着**那一型的真实内容**'
               '（句长/语速/变奏轴）',
               any('句长' in x or '句子长短' in x for x in t2)
               and any('变奏' in x for x in t2)
               and any('不习惯解释' in x for x in t2), str(t2[:8]))
            page.pop_dialog()
            await asyncio.sleep(0.4)
        page.pop_dialog()
        await asyncio.sleep(0.4)

    # ── ② 项目页签 → 角色设置 ──
    # [EN] ── ② Project tab → character settings ──
    pt = app._agents_tab(project=proj, allow_new=False)
    page.update()
    await asyncio.sleep(0.8)

    def _next_page(root):
        """点一次「下一页」（**演员排在第 9 位，每页 5 条 ⇒ 它在第 2 页**）。

        ⚠ 第一版直接在**第 1 页**上找演员那一行，当然找不到 ——
          而判据报的是"没有「角色设置」按钮"，看着像产品没接上
          （假红里最费时间的那种：方向都被带偏了）。
        
                English:
        Click "Next page" once (**actor is at position 9, 5 per page ⇒ it's on page 2**).
                ⚠ The first version looked for the actor row directly on **page 1**, so of course it wasn't found --
                  and the assertion reported "no 'Role settings' button", which looked like the product wasn't wired up
                  (the most time-wasting kind of false red: even the direction gets misled).
        """
        for c in VU.walk(root):
            if (getattr(c, 'on_click', None) is not None
                    and VU.text_of(c) == app_t('下一页')
                    and not getattr(c, 'disabled', False)):
                c.on_click(None)
                return True
        return False

    root_tab = ft.Column(pt)
    if _next_page(root_tab):
        page.update()
        await asyncio.sleep(0.9)
    #  ⚠ **别再调一次 `_agents_tab`**：它开头就是 `state = {'page': 0, ...}`
    #    —— 重调一次会把页码打回第 1 页，演员又不见了
    #    （第一版就是这么写的：翻了页、又亲手翻回去，然后判"没有按钮"）。
    #    同一次调用里 `body` 是同一个对象，翻页已经刷新过它的 `controls`。
    # [EN] ⚠ **Do not call `_agents_tab` again**: it starts with `state = {'page': 0, ...}`
    # [EN] —— calling it again resets the page number to page 1, and the actors disappear again
    # [EN] (the first version was written exactly like this: turned the page, then turned it back by hand,
    # [EN] then judged "no button").
    # [EN] Within the same call `body` is the same object; turning the page has already refreshed its
    # [EN] `controls`.
    gbtn = _btn(root_tab, tip=app_t('角色设置'))
    ok('D2 ★★★ 项目页签的**演员那一行**有「角色设置」按钮（👥）', gbtn is not None, '')
    ok('D2b ★★★ 而**天机**页签里没有这个按钮（那一层没有"这本书"）',
       _btn(ft.Column(soft), tip=app_t('角色设置')) is None, '')
    if gbtn is not None:
        n1 = len(VU.open_dialogs(page))
        gbtn.on_click(None)
        page.update()
        await asyncio.sleep(1.2)
        ok('D2c ★★★ 点它弹出角色设置', len(VU.open_dialogs(page)) > n1, '')
        if len(VU.open_dialogs(page)) <= n1:      # 弹不出来就别往下走（免得 IndexError 吞掉整组）
        # [EN] If it fails to pop up, do not continue (lest IndexError swallow the whole group)
            ok('D2d ★★★ 里面列着**这本书的真实角色**（主角/柳氏/阿福）', False,
               '上一条没过，跳过')
            ok('D2e ★★ 并且显示"已经配好的那一型"（主角 → 青年·高冷）', False,
               '上一条没过，跳过')
            ok('D2f ★★ 写明**一人一份**、与类型库的分工、下一轮生效', False,
               '上一条没过，跳过')
            ok('D2g ★★ 找得到某个角色那一行', False, '上一条没过，跳过')
            return
        t3 = _titles()
        ok('D2d ★★★ 里面列着**这本书的真实角色**（主角/柳氏/阿福）',
           all(any(n in x for x in t3) for n in ('主角', '柳氏', '阿福')),
           str([x for x in t3 if x in ('主角', '柳氏', '阿福', '演员类型')][:6]))
        ok('D2e ★★ 并且显示"已经配好的那一型"（主角 → 青年·高冷）',
           any('青年·高冷' in x for x in t3), str([x for x in t3 if '演员' in x][:4]))
        ok('D2f ★★ 写明**一人一份**、与类型库的分工、下一轮生效',
           any('一人一份' in x for x in t3)
           and any('以这里的角色为准' in x or '下一轮' in x for x in t3), '')
        row2 = None
        # ★★★ 2026-10-14 修（**锚点过期**，两处一起）：
        #   ① 原来要求某一格的字**精确等于** `'主角'`，而角色行的职位格现在写的是
        #      「**演员·主角**」—— 2026-10-13「演员按出场人物摊行」那轮把
        #      `_name_show` 改成了 `t('演员·{n}', n=_char)`（见 `_agent_row`）；
        #      界面明明列着三个角色（D2d 用**包含**匹配，一直是绿的），
        #      只有这里因为比整串而红。
        #   ② 更要紧的：**"那一行"的形状变了**。原来名字格是
        #      `Container(on_click=…, content=Row)`，2026-10-13/14 两轮之后它成了
        #      下面这个样子（名字格外面套紧约束 Container，里面是弹出菜单）——
        #      `DataCell(Container(width=…, content=ft.PopupMenuButton(content=Text, items=[…])))`
        #      所以「点开这个角色」的动作搬到了**菜单项**上（`items[0].on_click`）。
        #      继续按 Container 找，是"守着一件已经不存在的东西"。
        # [EN] ★★★ Fixed 2026-10-14 (**stale anchor**, two things at once):
        # [EN] ① it required a cell's text to be **exactly** `'主角'`, but a character row's position
        # [EN]   cell now reads "**演员·主角**" -- the 2026-10-13 round changed `_name_show` to
        # [EN]   `t('演员·{n}', n=_char)` (see `_agent_row`); the UI clearly lists three characters
        # [EN]   (D2d uses a **contains** match and has always been green), and only this one went red
        # [EN]   for comparing whole strings.
        # [EN] ② More importantly, **the shape of "that row" changed**. The name cell used to be
        # [EN]   `Container(on_click=..., content=Row)`; after two rounds (2026-10-13/14) it became
        # [EN]   `DataCell(Container(width=..., content=ft.PopupMenuButton(content=Text, items=[...])))`
        # [EN]   -- "open this character" moved onto the **menu item** (`items[0].on_click`).
        # [EN]   Searching for a Container is "guarding something that no longer exists".
        # ⚠ 2026-10-14：**遍历所有打开的对话框**，不是 `[-1]` ——
        #   含角色的那一层不是"最上面那一层"（`_titles()` 一直是这么读的，
        #   所以 D2d 绿而这条红：一个读全集、一个只读栈顶）。
        # ⚠ 同一天第二处修正：原来还要求 `c.content` **是 `ft.Row`**，
        #   而实测那一行（`Container(on_click=…, texts=3)`）的 content 不是 Row
        #   ⇒ 那个条件是**多余的**，把正确的那一行筛掉了。
        #   现在只认两条：**可点** + **那一格里含这个名字**；同一层里可能有
        #   好几层 Container 都"包含"它，取**最内层**（文本最少）的那个。
        # [EN] ⚠ 2026-10-14: **walk every open dialog**, not `[-1]` -- the layer holding the
        # [EN] characters is not "the topmost one" (`_titles()` has always read it this way, which is
        # [EN] why D2d is green while this one is red: one reads the whole set, the other only the top
        # [EN] of the stack).
        # [EN] ⚠ Second fix the same day: it also required `c.content` to **be an `ft.Row`**, but the
        # [EN] real row (`Container(on_click=..., texts=3)`) does not have a Row content => that
        # [EN] condition was **superfluous** and filtered out the correct row. Now only two things
        # [EN] count: **clickable** + **contains this name in that cell**; several nested Containers
        # [EN] may "contain" it, so take the **innermost** one (fewest texts).
        _cands: list = []
        for _d in VU.open_dialogs(page):
            for c in VU.walk(_d):
                _tx = VU.all_texts(c)
                if (getattr(c, 'on_click', None) is not None
                        and any('主角' in str(x) for x in _tx)):
                    _cands.append((len(_tx), c))
        row2 = min(_cands, key=lambda t: t[0])[1] if _cands else None
        ok('D2g ★★ 找得到某个角色那一行', row2 is not None, '')
        if row2 is not None:
            pass_marker = True
            # 「点开这个角色」：两种形状都认 ——
            #   · 角色设置对话框里那一行是 `Container(on_click=lambda e, _c=card: _open(_c))`；
            #   · 剧组表名字格那边是 `PopupMenuButton(items=[…])`（点它的**菜单项**）。
            #   ⚠ 第一版**只写了菜单那条路、没有 else** ⇒ row2 是 Container 时
            #     一个都不点、编辑器自然不开，D2h 就红了（"判据点了但没点到"）。
            # [EN] "Open this character": accept both shapes --
            # [EN] · the row inside the role-settings dialog is
            # [EN]   `Container(on_click=lambda e, _c=card: _open(_c))`;
            # [EN] · the name cell in the crew table is `PopupMenuButton(items=[...])` (click its
            # [EN]   **menu item**).
            # [EN] ⚠ The first version wrote **only the menu path with no else** => when row2 is a
            # [EN] Container nothing was clicked, the editor never opened, and D2h went red
            # [EN] ("the criterion clicked, but not on anything").
            _items = list(getattr(row2, 'items', None) or [])
            if _items and getattr(_items[0], 'on_click', None):
                _items[0].on_click(None)
            elif getattr(row2, 'on_click', None) is not None:
                row2.on_click(None)
            page.update()
            await asyncio.sleep(1.0)
            t4 = _titles()
            ok('D2h ★★★ 点开一个角色 → 编辑框里有**四个字段**'
               '（演员类型 / 这一份的变奏 / 选角细读 / 打破类型）',
               any('演员类型' in x for x in t4)
               and any('这一份的变奏' in x for x in t4)
               and any('这一份怎么演' in x for x in t4)
               and any('打破类型' in x for x in t4), str(t4[:10]))
            ok('D2i ★★ 而且带出这个人**当前的**值（主角 → 青年·高冷）',
               any('青年·高冷' in x for x in t4), '')
            page.pop_dialog()
            await asyncio.sleep(0.4)
        page.pop_dialog()
        await asyncio.sleep(0.4)

    # ── ③ 不为空白：截一张图，量对话框区域不是白的 ──
    # [EN] ── ③ Not blank: take a screenshot, measure that the dialog area is not white ──
    raw = await page.take_screenshot()
    if raw:
        from PIL import Image
        from collections import Counter
        im = Image.open(io.BytesIO(raw)).convert('RGB')
        w, h = im.size
        cut = im.crop((0, int(h * 0.1), w, int(h * 0.9)))
        buf = cut.tobytes()
        c = Counter(zip(buf[0::3], buf[1::3], buf[2::3]))
        top, n = c.most_common(1)[0]
        share = n / (cut.size[0] * cut.size[1])
        ok('D3 ★★ 屏幕不是一片空白（主色占比 < 92%，说明界面真的画出来了）',
           share < 0.92 and len(c) > 200, f'色数 {len(c)} 主色占比 {share:.1%}')
        (OUT / 'actor_layers.png').write_bytes(raw)
        ok('D4 截图落盘（给人看的那一份）',
           (OUT / 'actor_layers.png').is_file(), '')


def app_t(s: str) -> str:
    """走产品自己的 `t()`（判据里别手抄中文 —— 那样英文界面下会找不着）。
        English:
    Use the product's own `t()` (don't hand-copy Chinese in assertions -- it won't be found under an
    English UI).
    """
    from i18n import t
    return t(s)


def _finish() -> int:
    out = OUT / 'actor_layers_report.json'
    out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n演员的四层设置验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}')
    return 0 if not bad else 2


async def main(page: ft.Page) -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_actlay_'))
    code = 1
    try:
        # ⚠ 顺序与写法：`prompt_checks` 是 **async** 的（它要 `await decide()`）——
        #   在这一层用 `asyncio.run` 会与 ft.run 的事件循环撞车
        # [EN] ⚠ Order and style: `prompt_checks` is **async** (it needs to `await decide()`) ——
        # [EN] using `asyncio.run` at this layer will collide with ft.run's event loop
        #   （`RuntimeError: asyncio.run() cannot be called from a running event loop`）。
        for name, fn in (('数据层', lambda: data_checks(tmp)),
                         ('提示词', lambda: prompt_checks(tmp)),
                         ('界面接线', wiring_checks)):
            try:
                r = fn()
                if asyncio.iscoroutine(r):
                    await r
            except Exception:                                    # noqa: BLE001
                REPORT['checks'].append({'name': f'{name} 组崩了（自己留一条红）',
                                         'ok': False,
                                         'detail': traceback.format_exc()[-900:]})
        if page is not None:
            try:
                await gui_checks(page, tmp)
            except Exception:                                    # noqa: BLE001
                REPORT['checks'].append(
                    {'name': '真机组崩了（自己留一条红）', 'ok': False,
                     'detail': traceback.format_exc()[-900:]})
        code = _finish()
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)
        if page is not None:
            await shutdown(page, code=code)


if __name__ == '__main__':
    ft.run(main, assets_dir=str(APP / 'assets'))
