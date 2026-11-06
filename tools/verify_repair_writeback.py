# -*- coding: utf-8 -*-
"""验证：开卷时 AI 自行修复并**回写引用文件夹**，且项目开始后不再动它。

用户需求（2026-10-06）
---------------------
「开卷的时候，AI 找出来的问题如果可以自己修复的，需要 AI 主动修复并回写引用
文件夹里的文档，但是**后续项目开始了就不要去动引用文件夹了**。」

⚠ 这是**全程序唯一会写用户原始素材**的地方，所以 A 组（纯逻辑）里一半的断言
  测的是「**不许写**」：越界、非文本后缀、隐藏文件、阶段不对、项目已存在 ——
  那些比"能写进去"值钱得多。写坏别人的原稿是不可逆的。

产出：`assets/screenshots/repair_*.png` + `assets/screenshots/repair_report.json`

用法：
    .venv/Scripts/python.exe tools/verify_repair_writeback.py
    .venv/Scripts/python.exe tools/verify_repair_writeback.py --logic-only

English:
Verify: during open-book, the AI self-repairs and **writes back to the referenced folder**, and
does not touch it again after the project starts.
User requirement (2026-10-06)
---------------------
"When opening a book, if the problems the AI finds can be fixed by itself, the AI should
proactively fix them and write back to the referenced
folder's documents, but **once the subsequent project has started, do not touch the referenced
folder anymore**."
⚠ This is the **only place in the entire program that writes to the user's original material**,
so half of the assertions in Group A (pure logic)
  test "**must not write**": out of bounds, non-text suffix, hidden files, wrong phase, project already exists —
  those are far more valuable than "can write in". Damaging someone's original manuscript is irreversible.
Output: `assets/screenshots/repair_*.png` + `assets/screenshots/repair_report.json`
Usage:
    .venv/Scripts/python.exe tools/verify_repair_writeback.py
    .venv/Scripts/python.exe tools/verify_repair_writeback.py --logic-only
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft                                     # noqa: E402
from util.flet_shutdown import shutdown                # noqa: E402

from config import CFG                                 # noqa: E402
CFG.set('MOCK_LLM', 'true')                            # 零成本、零网络、可复现
# [EN] Zero cost, zero network, reproducible
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from i18n import set_lang, t                           # noqa: E402
set_lang(_lang)

from ingest import repair as R                         # noqa: E402
from ingest.scanner import scan_project, COMPLETION_NAME, CLASSIFY_NAME  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'
ONLY_LOGIC = '--logic-only' in sys.argv

report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:300]})
    return bool(cond)


def snapshot(root: Path) -> dict:
    """引用文件夹的指纹：每个**用户文档**的相对路径 → 内容哈希。

    ⚠ 排除 `.` 开头的文件：程序自己会往引用文件夹里写 `.nws_classify.json`
    （归类修正表）；**旧版本还写过 `.ingest_cache.json`（扫描缓存，已废）**，
    用户的老文件夹里可能还留着这个文件 —— 它现在没人读了，但比对"文件夹内容
    变没变"时仍要把它排除，否则会误判成"多了一个文件"。
      （`ingest/pipeline.py` 里一直就有），它出现跟"回写"没关系 —— 不排除的话
      「跳过时一个字节都没变」那条会**假红**（第一版就中了）。
    
        English:
    Fingerprint of the referenced folder: relative path of each **user document** → content hash.
        ⚠ Exclude files starting with `.`: the program itself writes `.nws_classify.json` into the referenced folder
        (classification correction table); **older versions also wrote `.ingest_cache.json` (scan cache, deprecated)**,
        the user's old folder may still contain this file -- nothing reads it now, but when comparing "did folder contents
        change" it must still be excluded, otherwise it would be misjudged as "an extra file".
          (`ingest/pipeline.py` always had this), its presence has nothing to do with "write-back" -- if not excluded,
          the "nothing changed at all when skipped" check would **falsely fail** (the first version hit this).
    """
    out = {}
    for p in sorted(Path(root).rglob('*')):
        if not p.is_file() or p.name.startswith('.'):
            continue
        out[str(p.relative_to(root)).replace('\\', '/')] = \
            hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


def make_source(root: Path, *, encode_txt: bool = True) -> Path:
    """造一个"有可修问题"的引用文件夹（A、B 组共用同一套形状）。
        English:
    Build a referenced folder with "fixable problems" (groups A and B share the same shape).
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / '人物.md').write_text(
        '# 人物\n\n- 主角：掌柜，沉默寡言\n- 阿枝：伙计，嘴上不饶人\n', encoding='utf-8')
    (root / '设定.md').write_text('# 设定\n\n一座常年落雨的临河小城。\n', encoding='utf-8')
    (root / '正文-第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。\n'
        '「你今日话里有话。」\n\n「话就是话，哪来的里外。」\n' * 6, encoding='utf-8')
    # 一个**不是 UTF-8** 的文件 + 一个**名字里没有类别词**的文件（同一个文件两罪）
    # [EN] One file that is **not UTF-8** + one file with **no category word in its name** (two offenses in
    # [EN] the same file)
    (root / '稿子.txt').write_text('雨夜来客，灯下无言。旧事压在青石板底下。\n',
                                   encoding='utf-16')
    return root


SETTINGS_GAPPY = {
    '人物': [{'姓名': '主角', '身份': '掌柜', '简介': '沉默寡言', '性格': '',
              '口癖': '', '秘密': '', '目标': '', '红线': ''}],
    '世界观': '一座小城。',
    '地点': [{'名称': '临河茶肆', '说明': '对话场所'}],
    '关系': [], '伏笔': [], '剧情参考线': '',
}


# ══════════════════════════════════════════════════════════════
#  A 组：纯逻辑（不弹窗）
# [EN] Group A: pure logic (no dialogs)
# ══════════════════════════════════════════════════════════════
async def logic_checks() -> None:
    from verify_ui_common import safe_rmtree
    tmp = Path(tempfile.mkdtemp(prefix='nws_repair_logic_'))
    try:
        # ── A1 清单：该命中的都命中 ──
        # [EN] ── A1 Checklist: everything that should hit does hit ──
        src = make_source(tmp / 'src')
        items = scan_project(src)
        issues = R.scan_issues(items, SETTINGS_GAPPY, tier='青铜', src_root=src)
        keys = {i.key for i in issues}
        kinds = {i.kind for i in issues}
        ok('A1 四类缺口 + 人物字段 + 编码 + 归类都进清单',
           {'gap:foreshadow', 'gap:secret', 'gap:outline', 'gap:world',
            'field:people', 'classify:odd'} <= keys
           and R.KIND_ENCODING in kinds
           and any(k.startswith('encoding:') for k in keys),
           f'keys={sorted(keys)}')
        ok('A1b 每条清单都有标题与做法（界面直接显示这两行）',
           all(i.title and i.plan for i in issues),
           [f'{i.key}:{i.title}' for i in issues if not (i.title and i.plan)])

        # ── A2 「AI 造不出来」的缺口**不许**进清单 ──
        #    （⚠ 关键词要挑准：plan 文案里本来就有「AI 读**正文**…」，用 '正文' 会假红）
        # [EN] ── A2 Gaps that "AI can't produce" must **not** enter the checklist ──
        # [EN] (⚠ Keywords must be chosen precisely: the plan text already contains "AI reads the **body**...",
        # [EN] using '正文' will produce a false red)
        bare = {'人物': [{'姓名': '甲'}], '世界观': 'x', '地点': [], '关系': [],
                '伏笔': [], '剧情参考线': ''}
        iss2 = R.scan_issues(items, bare, tier='青铜', src_root=src)
        blob = ' '.join(i.title + i.plan for i in iss2)
        ok('A2 不列「人物不足 2 个」「没有正文」这类 AI 造不出来的缺口',
           '有姓名的人物' not in blob and '至少 1 章' not in blob,
           blob[:160])

        # ── A3 落点选择：有对应文档就补进它，没有就新建 ──
        # [EN] ── A3 Target selection: if a corresponding document exists, append to it; otherwise create a new
        # [EN] one ──
        f = next(i for i in issues if i.key == 'gap:world')
        ok('A3 世界观缺口落到已存在的「设定.md」', f.target.endswith('设定.md'),
           f.target)
        (src / '伏笔.md').write_text('# 伏笔\n\n- F01 井响\n', encoding='utf-8')
        items3 = scan_project(src)
        iss3 = R.scan_issues(items3, SETTINGS_GAPPY, src_root=src)
        f3 = next(i for i in iss3 if i.key == 'gap:foreshadow')
        ok('A3b 伏笔缺口落到新出现的「伏笔.md」', f3.target.endswith('伏笔.md'),
           f3.target)
        (src / '伏笔.md').unlink()
        items4 = scan_project(src)
        iss4 = R.scan_issues(items4, SETTINGS_GAPPY, src_root=src)
        f4 = next(i for i in iss4 if i.key == 'gap:foreshadow')
        ok('A3c 没有对应文档 → 落点是新增的补全文档',
           f4.target == '' and f4.target_label(src) == COMPLETION_NAME,
           f'{f4.target!r} / {f4.target_label(src)}')

        # ── A4 人物空缺字段合并成一条，payload 记得住是谁缺什么 ──
        # [EN] ── A4 Missing character fields are merged into a single entry; the payload remembers who is
        # [EN] missing what ──
        fp = next(i for i in issues if i.key == 'field:people')
        vac = fp.payload.get('vacant') or {}
        ok('A4 人物空缺字段合并成一条且名单正确',
           list(vac) == ['主角'] and set(vac['主角']) == {'性格', '口癖', '目标', '红线'},
           vac)

        # ── A5 编码判定 ──
        # [EN] ── A5 Encoding determination ──
        ok('A5 UTF-8 文件判为"不需要转码"',
           R._bad_encoding(src / '人物.md') == '', R._bad_encoding(src / '人物.md'))
        ok('A5b UTF-16 文件判出编码', R._bad_encoding(src / '稿子.txt') != '',
           R._bad_encoding(src / '稿子.txt'))

        # ── A6 归类清单里的路径是相对路径（给作者看的）──
        # [EN] ── A6 Paths in the classification checklist are relative paths (for the author to read) ──
        cl = next(i for i in issues if i.key == 'classify:odd')
        ok('A6 归类清单用相对路径', cl.payload['files'] == ['稿子.txt'],
           cl.payload.get('files'))

        # ══ 以下全在测「不许写」 ══
        # [EN] ══ Everything below tests "must not write" ══
        def fresh(name: str = 'guard') -> Path:
            p = tmp / name
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True)
            (p / '人物.md').write_text('原来的内容\n', encoding='utf-8')
            return p

        # ── A7 阶段不对 → 拒绝 ──
        # [EN] ── A7 Wrong phase → reject ──
        g1 = fresh('g1')
        rep = R.write_back(g1, phase='runtime', appends=[(g1 / '人物.md', 'X')])
        ok('A7 非开卷阶段一律拒绝写引用文件夹',
           (not rep.ok) and (g1 / '人物.md').read_text(encoding='utf-8') == '原来的内容\n',
           rep.why)

        # ── A8 项目已存在 → 拒绝（这就是"项目开始了就别动它"）──
        # [EN] ── A8 Project already exists → reject (this is "once the project has started, don't touch it")
        # [EN] ──
        g2 = fresh('g2')
        proj = tmp / 'proj2'
        proj.mkdir(exist_ok=True)
        (proj / 'x.nwsproj').write_text('[项目]\n名称=x\n', encoding='utf-8')
        rep = R.write_back(g2, phase=R.PHASE_INGEST,
                           appends=[(g2 / '人物.md', 'X')], project_root=proj)
        ok('A8 项目已创建（.nwsproj 在）→ 拒绝再动引用文件夹',
           (not rep.ok) and (g2 / '人物.md').read_text(encoding='utf-8') == '原来的内容\n',
           rep.why)

        # ── A9 引用文件夹不存在 → 拒绝（不是异常）──
        # [EN] ── A9 Referenced folder does not exist → reject (not an exception) ──
        rep = R.write_back(tmp / '不存在的目录', phase=R.PHASE_INGEST)
        ok('A9 引用文件夹不存在 → 干净地拒绝', not rep.ok, rep.why)

        # ── A10 越界：引用文件夹之外的目标 ──
        # [EN] ── A10 Out of bounds: targets outside the referenced folder ──
        g3 = fresh('g3')
        outside = tmp / 'outside.md'
        outside.write_text('外面的东西\n', encoding='utf-8')
        rep = R.write_back(g3, phase=R.PHASE_INGEST,
                           appends=[(outside, 'X'), (g3 / '人物.md', '　\n补一句\n')])
        ok('A10 越界目标被跳过，且**外面那个文件一个字节都没变**',
           outside.read_text(encoding='utf-8') == '外面的东西\n'
           and any('不在引用文件夹' in w for _, w in rep.skipped)
           and rep.appended == ['人物.md'],
           rep.skipped)

        # ── A11 只改 .md / .txt ──
        # [EN] ── A11 Only modify .md / .txt ──
        g4 = fresh('g4')
        (g4 / '笔记.json').write_text('{"a":1}', encoding='utf-8')
        (g4 / '草稿.docx').write_bytes(b'PK\x03\x04fake')
        rep = R.write_back(g4, phase=R.PHASE_INGEST, appends=[
            (g4 / '笔记.json', 'X'), (g4 / '草稿.docx', 'X')])
        ok('A11 只改 .md/.txt：json / docx 被拒且原样',
           len(rep.skipped) == 2 and rep.changed == 0
           and (g4 / '笔记.json').read_text(encoding='utf-8') == '{"a":1}',
           rep.skipped)

        # ── A12 不动隐藏文件 ──
        # [EN] ── A12 Do not touch hidden files ──
        g5 = fresh('g5')
        (g5 / '.秘密.md').write_text('藏起来的\n', encoding='utf-8')
        rep = R.write_back(g5, phase=R.PHASE_INGEST, appends=[(g5 / '.秘密.md', 'X')])
        ok('A12 隐藏文件不碰',
           any('隐藏' in w for _, w in rep.skipped)
           and (g5 / '.秘密.md').read_text(encoding='utf-8') == '藏起来的\n',
           rep.skipped)

        # ── A13 只追加：原文逐字保留、且在最前面 ──
        # [EN] ── A13 Append only: original text preserved verbatim, and placed at the very front ──
        g6 = fresh('g6')
        before = (g6 / '人物.md').read_text(encoding='utf-8')
        rep = R.write_back(g6, phase=R.PHASE_INGEST,
                           appends=[(g6 / '人物.md', '## AI 补全\n\n- 补一句\n')])
        after = (g6 / '人物.md').read_text(encoding='utf-8')
        ok('A13 原有内容一字不动、且排在补全之前',
           after.startswith(before) and before in after and rep.appended == ['人物.md'],
           after[:60].replace('\n', '⏎'))

        # ── A14 备份：留的是**改之前**的样子 ──
        # [EN] ── A14 Backup: what is kept is the **pre-modification** state ──
        bak = g6 / '人物.md.bak'
        ok('A14 改之前先留 .bak，内容 == 改前',
           bak.exists() and bak.read_text(encoding='utf-8') == before,
           rep.backups)
        ok('A14b 已在跳过/拒绝名单里的文件不产生备份',
           not (g4 / '笔记.json.bak').exists() and not (g5 / '.秘密.md.bak').exists())

        # ── A15 .bak 已存在时不覆盖（保留最早那份，最能救命）──
        # [EN] ── A15 Do not overwrite when .bak already exists (keep the earliest one, it saves the most
        # [EN] lives) ──
        g7 = fresh('g7')
        (g7 / '人物.md.bak').write_text('很久以前的版本\n', encoding='utf-8')
        R.write_back(g7, phase=R.PHASE_INGEST, appends=[(g7 / '人物.md', 'X2\n')])
        ok('A15 已有 .bak 时不覆盖它',
           (g7 / '人物.md.bak').read_text(encoding='utf-8') == '很久以前的版本\n')

        # ── A16 没有目标文档时**新建**补全文档 ──
        # [EN] ── A16 **Create** a completion document when there is no target document ──
        g8 = fresh('g8')
        rep = R.write_back(g8, phase=R.PHASE_INGEST,
                           appends=[(g8 / COMPLETION_NAME, '## AI 补全\n\n- x\n')])
        ok('A16 找不到落点就新建补全文档',
           (g8 / COMPLETION_NAME).exists() and rep.created == [COMPLETION_NAME],
           rep.created)

        # ── A17 转码：内容不变，字节变 UTF-8 ──
        # [EN] ── A17 Transcode: content unchanged, bytes become UTF-8 ──
        g9 = fresh('g9')
        (g9 / '稿子.txt').write_text('雨夜来客，灯下无言。\n', encoding='utf-16')
        raw16 = (g9 / '稿子.txt').read_bytes()
        rep = R.write_back(g9, phase=R.PHASE_INGEST, convert=[g9 / '稿子.txt'])
        raw8 = (g9 / '稿子.txt').read_bytes()
        ok('A17 非 UTF-8 转成 UTF-8，正文一字不变',
           rep.converted == ['稿子.txt']
           and (g9 / '稿子.txt').read_text(encoding='utf-8') == '雨夜来客，灯下无言。\n'
           and raw8 != raw16
           and (g9 / '稿子.txt.bak').read_bytes() == raw16,
           f'{len(raw16)}B → {len(raw8)}B')

        # ── A18 归类表落盘 + **真的生效**（下次扫描按修正后的类别读）──
        # [EN] ── A18 Classification table persisted + **actually takes effect** (next scan reads by the
        # [EN] corrected category) ──
        g10 = fresh('g10')
        (g10 / '稿子.txt').write_text('雨夜来客。\n', encoding='utf-8')
        c0 = [i.category for i in scan_project(g10) if i.name == '稿子.txt'][0]
        rep = R.write_back(g10, phase=R.PHASE_INGEST, classify={'稿子.txt': '正文'})
        c1 = [i.category for i in scan_project(g10) if i.name == '稿子.txt'][0]
        ok('A18 归类修正写进表里，且下次扫描真的按它分类',
           c0 == '杂项' and c1 == '正文' and rep.classify == {'稿子.txt': '正文'}
           and (g10 / CLASSIFY_NAME).exists(),
           f'{c0} → {c1}')

        # ── A19 程序自己写的补全文档**不进扫描**（否则自己喂自己）──
        # [EN] ── A19 Completion documents written by the program itself **do not enter the scan** (otherwise
        # [EN] it feeds itself) ──
        g11 = fresh('g11')
        (g11 / COMPLETION_NAME).write_text('## AI 补全\n\n这是程序写的。\n',
                                           encoding='utf-8')
        names = [i.name for i in scan_project(g11)]
        ok('A19 补全文档不被当成素材再读一遍', COMPLETION_NAME not in names, names)

        # ── A20 并进设定：**只填空，不覆盖** ──
        # [EN] ── A20 Merge into settings: **fill blanks only, do not overwrite** ──
        st = {'人物': [{'姓名': '甲', '身份': '掌柜', '性格': '', '口癖': '「罢了。」'}],
              '世界观': '原有世界观（作者亲手写的，够长了，不该被覆盖）。' * 2,
              '伏笔': [{'编号': 'F9', '内容': '原有的'}], '剧情参考线': ''}
        reps = {'人物字段': [{'姓名': '甲', '补': {'身份': '不该覆盖', '性格': '沉默',
                                                  '目标': '守住铺子'}}],
                '伏笔': [{'编号': 'F1', '内容': '井响'}],
                '大纲': '起承转合',
                '世界观': 'AI 写的世界观'}
        st2, notes = R.merge_into_settings(st, reps)
        a = st2['人物'][0]
        ok('A20 并进设定只填空：已有的身份/口癖/世界观/伏笔都不被覆盖',
           a['身份'] == '掌柜' and a['口癖'] == '「罢了。」' and a['性格'] == '沉默'
           and a['目标'] == '守住铺子'
           and st2['世界观'] == st['世界观']
           and st2['伏笔'][0]['编号'] == 'F9'
           and st2['剧情参考线'] == '起承转合',
           f'identity={a["身份"]} world_head={st2["世界观"][:12]}')

        # ── A21 渲染分桶：同一份补全，伏笔进伏笔文件、人物字段进人物文件 ──
        # [EN] ── A21 Render bucketing: the same completion, foreshadowing goes into the foreshadowing file,
        # [EN] character fields into the character file ──
        blk_f = R.render_appendix(reps, issues=[], src_root=src,
                                  want_keys={'gap:foreshadow'})
        blk_p = R.render_appendix(reps, issues=[], src_root=src,
                                  want_keys={'field:people'})
        ok('A21 补全按落点分桶渲染（不把人物字段塞进伏笔文件）',
           'F1' in blk_f and '沉默' not in blk_f and '沉默' in blk_p and 'F1' not in blk_p,
           f'f={blk_f[:40]!r} p={blk_p[:40]!r}')
        ok('A21b 没有任何可写内容时渲染结果为空（不写空壳）',
           R.render_appendix({}, issues=[], src_root=src, want_keys={'gap:foreshadow'}) == '')

        # ── A22 端到端（打桩模型，零网络）──
        # [EN] ── A22 End-to-end (stub model, zero network) ──
        g12 = fresh('g12')
        src12 = make_source(tmp / 'src12')
        items12 = scan_project(src12)
        iss12 = R.scan_issues(items12, SETTINGS_GAPPY, tier='青铜', src_root=src12)
        before_人物 = (src12 / '人物.md').read_text(encoding='utf-8')
        before_设定 = (src12 / '设定.md').read_text(encoding='utf-8')
        calls = {'n': 0}
        real_build = R.build_repairs

        async def fake_build(issues, items, settings, **kw):
            calls['n'] += 1
            return {'人物字段': [{'姓名': '主角', '补': {'性格': '沉默寡言',
                                                     '目标': '把旧事掩过去'}}],
                    '伏笔': [{'编号': 'F1', '内容': '后院那口井夜里会响',
                              '埋设': '开篇', '预计回收': '中段'}],
                    '大纲': '起：雨夜来客；承：旧事翻出；转：破绽；合：各归其位。',
                    '世界观': '临河小城，常年落雨，人情密、口风紧。',
                    '归类': {'稿子.txt': '正文'}}

        R.build_repairs = fake_build
        try:
            st3, rep3, notes3 = await R.run_repairs(
                iss12, items12, SETTINGS_GAPPY, src_root=src12, phase=R.PHASE_INGEST,
                name='夹具', tier='青铜')
        finally:
            R.build_repairs = real_build
        ok('A22 端到端：模型只调一次，产物齐全', calls['n'] == 1 and rep3.ok
           and rep3.changed > 0, f'calls={calls["n"]} changed={rep3.changed}')
        ok('A22b 人物字段补进「人物.md」，原文仍是它的前缀',
           (src12 / '人物.md').read_text(encoding='utf-8').startswith(before_人物)
           and '沉默寡言' in (src12 / '人物.md').read_text(encoding='utf-8'),
           rep3.appended)
        ok('A22c 世界观补进「设定.md」', (src12 / '设定.md').read_text(
            encoding='utf-8').startswith(before_设定)
           and (src12 / '设定.md.bak').read_text(encoding='utf-8') == before_设定,
           rep3.appended)
        ok('A22d 归类说明落到新增的补全文档里',
           (src12 / COMPLETION_NAME).exists(), rep3.created)
        ok('A22e 稿子.txt 转成 UTF-8 且留了 .bak',
           rep3.converted == ['稿子.txt'] and (src12 / '稿子.txt.bak').exists(),
           rep3.converted)
        ok('A22f 整件事只写引用文件夹内部（外面没有新文件）',
           not (tmp / 'src12.md').exists())

        # ── A23 清单为空时**连模型都不调** ──
        #    夹具要"干净得彻底"：EMPTY_FIELDS 里那几项都得有值，否则会命中
        #    「人物空缺字段」那条（第一版就漏了 身份/性格/目标/红线，白红一次）。
        # [EN] ── A23 When the checklist is empty, **do not even call the model** ──
        # [EN] Fixtures must be "thoroughly clean": every item in EMPTY_FIELDS must have a value, otherwise it
        # [EN] will hit
        g13 = fresh('g13')
        clean_items = scan_project(g13)
        clean_settings = {'人物': [{'姓名': '甲', '身份': '掌柜', '性格': '沉默寡言',
                                    '口癖': '「罢了。」', '目标': '守住铺子',
                                    '红线': '不主动伤人', '秘密': '替人顶过一件事'}],
                          # ⚠ 世界观要写到 40 字以上 —— 短于 WORLD_MIN_CHARS 会命中
                          #   「世界观太短」那条（夹具不干净 = 判据假红）
                          # [EN] ⚠ Worldbuilding must be written to 40+ characters — shorter than WORLD_MIN_CHARS will hit
                          # [EN] The "worldbuilding too short" entry (dirty fixture = false red criterion)
                          '世界观': '一座常年落雨的临河小城，人情密、口风紧，'
                                    '旧事压在青石板底下，谁提谁犯忌；'
                                    '镇上有沈、顾两姓，积怨已深。',
                          '伏笔': [{'编号': 'F1', '内容': '井响'}],
                          '剧情参考线': '起承转合'}
        iss13 = R.scan_issues(clean_items, clean_settings, src_root=g13)
        calls_before = calls['n']
        snap13 = snapshot(g13)
        R.build_repairs = fake_build
        try:
            _st, rep13, _n = await R.run_repairs(
                iss13, clean_items, clean_settings, src_root=g13)
        finally:
            R.build_repairs = real_build
        ok('A23 没有问题清单时什么都不做、也不花钱（一次模型调用都不发）',
           iss13 == [] and (not rep13.ok) and calls['n'] == calls_before
           and snapshot(g13) == snap13,
            f'issues={len(iss13)} calls {calls_before}→{calls["n"]} why={rep13.why}')
    finally:
        safe_rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
#  B 组：真机
# [EN] Group B: real machine
# ══════════════════════════════════════════════════════════════
async def gui_checks(page: ft.Page, app) -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_repair_gui_'))
    from gui.app_flet import ING_W, C

    def shot(name: str) -> Path:
        return OUT / name.replace('.png', f'{SUFFIX}.png')

    async def take(name: str, note: str = '') -> bytes:
        page.update()
        await asyncio.sleep(0.4)
        data = await page.take_screenshot()
        shot(name).write_bytes(data)
        report.setdefault('shots', []).append({'file': name, 'note': note})
        return data

    async def run_once(src: Path, pname: str, *, agree: bool, tag: str) -> dict:
        """走一次真实开卷；agree=False 走「跳过」，True 走「同意修复并回写」。

        `tag` 只用来命名截图（英文，跨平台稳）；`pname` 才是真实项目名。
        
                English:
        Run a real open-book session once; agree=False goes through "skip", True goes through "agree to
        fix and write back".
                `tag` is only used to name screenshots (English, cross-platform stable); `pname` is the real project name.
        """
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.5)
        app._wizard_path = str(src)
        app._wizard_name = pname
        app._wizard_opts['ai_optimize'] = True
        app._wizard_opts['repair_source'] = True       # ← 用**默认路径**（不关掉）
        # [EN] ← Use the **default path** (do not disable)
        app._do_import(page)
        st = app._ingest_state

        # ① 同意门（脚本要替作者点同意，否则连 AI 都到不了）
        # [EN] ① Consent gate (the script must click consent on the author's behalf, otherwise even the AI
        # [EN] cannot be reached)
        for _ in range(150):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            if getattr(ui.get('consent_panel'), 'visible', False):
                break
        ui = st.get('ui') or {}
        for b in list(ui.get('consent_boxes') or []):
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        if ui.get('consent'):
            ui['consent'](True)

        # ② AI 优化阶段 → 自己点「完成优化并进入」（把控制权交回后台）
        # [EN] ② AI optimization phase → click "complete optimization and enter" yourself (hand control back to
        # [EN] the backend)
        for _ in range(400):
            await asyncio.sleep(0.1)
            if st.get('phase') == 'chat':
                break
        await asyncio.sleep(0.6)
        ui = st.get('ui') or {}
        if ui.get('finish'):
            ui['finish'](None)

        # ③ 等修复清单面板出现
        # [EN] ③ Wait for the repair checklist panel to appear
        seen = False
        for _ in range(300):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            if getattr(ui.get('repair_panel'), 'visible', False):
                seen = True
                break
        ui = st.get('ui') or {}
        info = {'panel_seen': seen,
                'rows': len(getattr(ui.get('repair_list'), 'controls', []) or []),
                'cb_disabled_before': bool(getattr(ui.get('repair_btn'), 'disabled', True))}
        if seen:
            # 清单文字 + 落点（结构判据）
            # [EN] Checklist text + targets (structural criterion)
            texts = [str(getattr(c, 'value', '') or '')
                     for c in (getattr(ui.get('repair_list'), 'controls', []) or [])
                     if isinstance(c, ft.Text)]
            info['texts'] = texts
            info['title'] = str(getattr(ui.get('repair_title'), 'value', '') or '')
            # 像素判据：把清单第一行的字涂成品红，证明它**真的画在屏幕上**
            # [EN] Pixel criterion: paint the text of the first checklist line magenta, proving it is **actually
            # [EN] drawn on screen**
            first = next((c for c in (ui['repair_list'].controls or [])
                          if isinstance(c, ft.Text)), None)
            if first is not None:
                old = first.color
                first.color = '#ff00ff'
                page.update()
                await asyncio.sleep(0.4)
                png = await page.take_screenshot()
                shot(f'repair_{tag}_marker.png').write_bytes(png)
                n_magenta = 0
                import io as _io
                from PIL import Image
                im = Image.open(_io.BytesIO(png)).convert('RGB')
                px = im.load()
                for y in range(im.height):
                    for x in range(im.width):
                        c = px[x, y]
                        if c[0] > 200 and c[1] < 80 and c[2] > 200:
                            n_magenta += 1
                info['marker_px'] = n_magenta
                first.color = old
                page.update()
            # 勾选框：不勾时按钮是灰的，勾上才亮（真的走 on_change）
            # [EN] Checkbox: the button is gray when unchecked and lights up when checked (actually goes through
            # [EN] on_change)
            cb = ui.get('repair_cb')
            if cb is not None:
                cb.value = True
                if getattr(cb, 'on_change', None):
                    cb.on_change(None)
                info['cb_disabled_after'] = bool(
                    getattr(ui.get('repair_btn'), 'disabled', True))
            await take(f'repair_{tag}_panel.png', '修复清单面板')
            (ui.get('repair') or (lambda x: None))(agree)

        # ④ 等流程结束（进主界面）
        # [EN] ④ Wait for the flow to end (enter the main interface)
        for _ in range(400):
            await asyncio.sleep(0.1)
            if app._view == 'main' and st.get('phase') == 'finishing':
                break
            if not st.get('running'):
                break
        await asyncio.sleep(1.0)
        info['sealed'] = bool(st.get('sealed'))
        info['view'] = app._view
        return info

    try:
        # ── B1 向导第 3 步有这项、且默认勾选 ──
        # [EN] ── B1 Step 3 of the wizard has this item, and it is checked by default ──
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.5)
        # 走到第 3 步（直接切步骤比点按钮稳）
        # [EN] Go to step 3 (switching steps directly is more stable than clicking buttons)
        step3 = app._wizard_step3_ai(page)
        labels = [str(getattr(c, 'label', '') or '')
                  for c in step3['content'] if isinstance(c, ft.Checkbox)]
        opts = [bool(getattr(c, 'value', False)) for c in step3['content']
                if isinstance(c, ft.Checkbox)]
        repair_label = next((x for x in labels if '引用文件夹' in x), '')
        ok('B1 向导第 3 步有「补全并回写引用文件夹」选项且默认勾选',
           bool(repair_label) and app._wizard_opts.get('repair_source') is True,
           f'labels={labels}')
        try:
            page.pop_dialog()
        except Exception:                                    # noqa: BLE001
            pass
        await asyncio.sleep(0.3)

        # ── B2 跳过：引用文件夹一个字节都不许变 ──
        # [EN] ── B2 Skip: not a single byte of the referenced folder may change ──
        src_skip = make_source(tmp / 'src_skip')
        before_skip = snapshot(src_skip)
        info_skip = await run_once(src_skip, '跳过夹具', agree=False, tag='skip')
        after_skip = snapshot(src_skip)
        report['skip_run'] = {'info': info_skip, 'before': before_skip,
                              'after': after_skip}
        ok('B2 真机出现修复清单面板（默认开着这一步）',
           info_skip['panel_seen'] and info_skip['rows'] > 0, info_skip)
        ok('B2b 按钮初始是灰的，勾选后解锁',
           info_skip['cb_disabled_before'] and not info_skip.get('cb_disabled_after', True),
           info_skip)
        ok('B2c 清单第一行**真的画在屏幕上**（涂成品红后量到像素）',
           info_skip.get('marker_px', 0) > 20, info_skip.get('marker_px'))
        ok('B2d 清单里写明了每条落到哪个文件',
           any('→' in x for x in info_skip.get('texts', [])),
           info_skip.get('texts'))
        ok('B2e 选了「跳过」→ 引用文件夹**一个字节都没变**',
           before_skip == after_skip,
           {k: (before_skip.get(k), after_skip.get(k))
            for k in set(before_skip) | set(after_skip)
            if before_skip.get(k) != after_skip.get(k)})

        # ── B3 同意：真的写回 ──
        # [EN] ── B3 Consent: actually written back ──
        src_go = make_source(tmp / 'src_go')
        before_go = snapshot(src_go)
        # ⚠ 只收**本来就是 UTF-8 的**文档：夹具里那个 `稿子.txt` 是 UTF-16，
        #   用 utf-8 读出来是乱码，拿它当"原文"比 startswith 必然假红
        #   （它由下面 A17/B3b 的转码断言单独管）。
        # [EN] ⚠ Only collect documents that **are originally UTF-8**: the `稿子.txt` in the fixture is UTF-16,
        # [EN] reading it as utf-8 yields garbage, and comparing it as "original" with startswith will
        # [EN] inevitably produce a false red
        # [EN] (It is governed separately by the transcode assertions in A17/B3b below).
        before_text = {}
        for k in before_go:
            if not k.lower().endswith(('.md', '.txt')):
                continue
            try:
                before_text[k] = (src_go / k).read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
        info_go = await run_once(src_go, '回写夹具', agree=True, tag='go')
        after_go = snapshot(src_go)
        report['go_run'] = {'info': info_go, 'before': before_go, 'after': after_go}
        ok('B3 点「同意修复并回写」→ 引用文件夹真的被改了',
           after_go != before_go, sorted(set(after_go) - set(before_go)))
        ok('B3b 补全写进去了（原文件只追加 / 或新建补全文档）',
           any(k in after_go for k in (COMPLETION_NAME, '设定.md'))
           and any(k.endswith('.bak') for k in after_go),
           sorted(after_go))
        ok('B3c 归类修正表落盘（下次扫描会按它分类）',
           (src_go / CLASSIFY_NAME).exists(), sorted(after_go))
        # 「原文没丢」按**每个文件自己的改前内容**判：改后必须以原文开头
        # （写「自己跟自己比」那种判据是恒真的，等于没判）
        # [EN] "Original not lost" is judged by **each file's own pre-modification content**: after
        # [EN] modification it must start with the original
        # [EN] (A criterion like "compare it with itself" is always true, equivalent to no criterion)
        lost = [k for k, txt in before_text.items()
                if not (src_go / k).exists()
                or not (src_go / k).read_text(encoding='utf-8', errors='replace')
                .startswith(txt)]
        ok('B3d 原有文件内容没丢（改后仍以原文开头）',
           not lost and bool(before_text), lost)
        ok('B3e 项目已创建，熔断合上（state.sealed）',
           info_go.get('sealed') and info_go.get('view') == 'main', info_go.get('view'))

        # ── B4 项目开始之后：同一进程里再想写引用文件夹也必须被拦 ──
        # [EN] ── B4 After the project starts: any further attempt to write to the referenced folder in the
        # [EN] same process must also be blocked ──
        proj_root = CFG.projects_dir() / '回写夹具'
        rep_after = R.write_back(src_go, phase=R.PHASE_INGEST,
                                 appends=[(src_go / '人物.md', '　\n事后偷偷加一句\n')],
                                 project_root=proj_root)
        ok('B4 项目开始后再调写入口 → 被拒绝（引用文件夹冻结）',
           (not rep_after.ok) and snapshot(src_go) == after_go, rep_after.why)
    finally:
        from verify_ui_common import safe_rmtree
        safe_rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
async def entry(page: ft.Page) -> None:
    from verify_ui_common import isolate_projects_dir, safe_rmtree
    from gui.app_flet import NovelWorldApp

    # A 组先跑：它不需要窗口，早点把问题暴露出来
    # [EN] Run Group A first: it does not need a window, and exposes problems earlier
    await logic_checks()

    if ONLY_LOGIC:
        return

    tmp = Path(tempfile.mkdtemp(prefix='nws_repair_proj_'))
    isolate_projects_dir(tmp / 'Projects')

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)
    try:
        await gui_checks(page, app)
    finally:
        safe_rmtree(tmp, ignore_errors=True)


def a_only_entry() -> None:
    """`--logic-only`：不起窗口（不弹窗、不拉 flet 客户端，收尾也就没有那些坑）。
        English:
    `--logic-only`: do not open a window (no popup, no flet client, so none of those pitfalls at
    cleanup).
    """
    try:
        asyncio.run(logic_checks())
    except BaseException:                                    # noqa: BLE001
        report['fatal'] = traceback.format_exc()


def write_report(code: int) -> None:
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / f'repair_writeback_report{SUFFIX}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"断言 {len(report['checks']) - len(bad)}/{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1500:])
    print('ok:', report['ok'])


if __name__ == '__main__':
    if ONLY_LOGIC:
        a_only_entry()
        write_report(0)
        raise SystemExit(0 if report['ok'] else 2)

    async def main(page: ft.Page) -> None:
        try:
            await entry(page)
        except BaseException:                                # noqa: BLE001
            report['fatal'] = traceback.format_exc()
        finally:
            write_report(0)
            # ⚠ 退出码必须在**关窗之前**落实（`destroy()` 会抛 CancelledError
            #   取消本协程，写在它后面的 `exit_now` 从来没执行过 —— 退出码恒为 0）。
            # [EN] ⚠ The exit code must be set **before closing the window** (`destroy()` will throw CancelledError
            # [EN] and cancel this coroutine; the `exit_now` written after it never executes — the exit code is
            # [EN] always 0).
            await shutdown(page, code=0 if report['ok'] else 2)

    ft.run(main)
