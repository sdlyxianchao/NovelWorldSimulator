# -*- coding: utf-8 -*-
"""验证「顶级规则」：作者在设定文档里写死的硬约束，真的管住了推演。

要证的四件事，每一条都得能红：

  ① **认得出** —— 文件名带「规则/铁律/守则/法则/戒律/准则/禁忌/契约/规范」
     或被 `rule`/`constraint`/`canon` 命中时，分类成「规则」；
     而且它**优先于「设定」**（`设定/顶级规则.md` 不能落进设定类）。
     反过来也要守住：`设定/世界观.md`、`伏笔.md` 这些**不许**被误判成规则。

  ② **一字不改** —— 规则文档进设定集时是**原文照录**，不是让模型概括过的。
     这是整套机制的要害：概括会丢条件、改语气，而规则是判据。
     所以判据比的是**逐字相等**（只归一换行），不是"关键词在不在"。
     对照组：`世界观.md` 会经过 LLM 提取 → 被压到一两句话（这里是**允许**压缩的）。

  ③ **真的进了 prompt** —— 光落盘没用。`world_prefix()` 要带、角色决策要带、
     导演要带、台词（`talk`）要带；没有规则的项目**不许**凭空多出一段。

  ④ **兜底与护栏** —— 规则散写在普通设定文档里时，靠提取出的「顶级规则」条目兜底；
     两者都有时**只用原文**（否则同一件事两种措辞互相打架）；
     界面上的「AI 优化」重新冻结设定时**不许**把已有规则覆盖成空。

用法：.venv\\Scripts\\python.exe tools/verify_world_rules.py
产出：assets/screenshots/world_rules_report.json

English:
Verify "top-level rules": hard constraints the author hardcodes in the setting document really
do govern the deduction.
Four things to prove, each one must be able to go red:
     or is hit by `rule`/`constraint`/`canon`, classify it as "rules";
     and it **takes priority over "settings"** (`设定/顶级规则.md` must not fall into the settings class).
     The reverse must also hold: `设定/世界观.md`, `伏笔.md` and the like **must not** be misjudged as rules.
  ② **Not a single character changed** -- when a rule document enters the setting collection it is **transcribed verbatim**, not summarized by a model.
     This is the crux of the whole mechanism: summarization loses conditions and changes tone, and rules are the criterion.
     So the criterion compares **character-for-character equality** (only newlines normalized), not "whether the keyword is present".
     Control group: `世界观.md` goes through LLM extraction → compressed to one or two sentences (compression is **allowed** here).
  ③ **Actually gets into the prompt** -- landing on disk alone is useless. `world_prefix()` must carry it, character decisions must carry it,
     the director must carry it, dialogue (`talk`) must carry it; a project with no rules **must not** get an extra section out of nowhere.
  ④ **Fallback and guardrails** -- when rules are scattered in ordinary setting documents, fall back to the extracted "top-level rules" entries;
     when both are present **use only the original text** (otherwise the same thing in two wordings fights itself);
     when the "AI optimize" in the UI refreezes settings, **must not** overwrite existing rules into empty.
Usage: .venv\\Scripts\\python.exe tools/verify_world_rules.py
Output: assets/screenshots/world_rules_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG                                       # noqa: E402
CFG.set('MOCK_LLM', 'true')

from i18n import set_lang                                    # noqa: E402
set_lang('zh')

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


# 规则正文（故意写得像真人手笔：有标题、有引用行、有列表、有全角标点）
# [EN] Rule body text (deliberately written to look like a real person's handiwork: has headings,
# [EN] quoted lines, lists, full-width punctuation)
RULES = """\
# 顶级规则

> 这本小说的硬规矩。与情节冲突时，**以这里为准**。

## 世界铁律
- 漏刻只许校、不许改。改一次要留档、署名、画押。
- 没有鬼神。所有"怪事"最后都必须有一个说得通的人为解释。

## 写法
- 一案收干净再起一案：章末必须了结本案。
"""

WORLD = "唐，长安。城里的时辰不是看天，是听更鼓；更鼓则由司天台的漏刻定。"

CHAPTER = "早了一刻。\n\n主角把浮箭取出来的时候，天还没亮。\n\n铜壶里的水比昨日浑。"


def _fixture(root: Path, *, rules: bool = True, rules_name: str = '设定/顶级规则.md',
             ai_rules=None) -> Path:
    """造一个引用文件夹。`rules=False` 时不放规则文档（用来做反例）。
        English:
    Build a reference folder. When `rules=False`, no rule document is placed (used as a
    counterexample).
    """
    (root / '设定' / '人物').mkdir(parents=True, exist_ok=True)
    (root / '正文').mkdir(parents=True, exist_ok=True)
    (root / '设定' / '世界观.md').write_text('# 世界观\n\n' + WORLD, encoding='utf-8')
    (root / '设定' / '人物' / '主角.md').write_text(
        '# 主角\n\n司天台漏刻科博士，话少手稳。\n\n- 秘密：腕上那道旧痕的来历\n',
        encoding='utf-8')
    (root / '正文' / '第一章.md').write_text('# 第一章\n\n' + CHAPTER, encoding='utf-8')
    if rules:
        p = root / rules_name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(RULES, encoding='utf-8')
    return root


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑（不起窗口、不联网）
# [EN] A. Pure logic (no window, no network)
# ══════════════════════════════════════════════════════════════
def logic_checks(tmp: Path) -> None:
    from ingest.scanner import _classify, scan_project
    from ingest import pipeline as PL
    from ingest.extractor import _validate, _empty_skeleton

    # ── A1 分类：各种写法都要认出来 ──
    # [EN] ── A1 Classification: all kinds of spellings must be recognized ──
    yes = ['设定/顶级规则.md', '设定/规则.md', '世界规则.txt', '设定/铁律.md',
           '设定/写作守则.md', '设定/世界法则.md', '设定/戒律.md', '设定/禁忌.md',
           '设定/契约.md', '写作规范.md', 'Rules.md', 'world-rules.md',
           'constraints.md']
    bad = [f'{_classify(Path(n))} ← {n}' for n in yes
           if _classify(Path(n)) != '规则']
    ok('A1 文件名带「规则/铁律/守则/法则/戒律/禁忌/契约/规范/rule…」→ 分类为「规则」',
       not bad, bad)

    # ── A2 优先级与不误伤 ──
    # [EN] ── A2 Priority and avoiding collateral damage ──
    ok('A2 ★ `设定/顶级规则.md` 判成「规则」而不是「设定」（优先级：规则在最前）',
       _classify(Path('设定/顶级规则.md')) == '规则',
       _classify(Path('设定/顶级规则.md')))
    keep = {'设定/世界观.md': '设定', '设定/人物/主角.md': '人物',
            '大纲/故事大纲.md': '大纲', '伏笔.md': '伏笔', '正文/第一章.md': '正文',
            '杂七杂八.txt': '杂项'}
    wrong = [f'{k}→{_classify(Path(k))}（应为 {v}）' for k, v in keep.items()
             if _classify(Path(k)) != v]
    ok('A2b 加「规则」类**没有误伤**其他分类（世界观/人物/大纲/伏笔/正文/杂项）',
       not wrong, wrong)

    # ── A3 原文照录 ──
    # [EN] ── A3 Verbatim transcription ──
    src = _fixture(tmp / 'src_ok')
    got = PL.collect_rules(scan_project(src), {})
    ok('A3 ★ 规则文档**原文照录**（逐字相等，没被概括/改写）',
       got.replace('\r\n', '\n').strip() == RULES.replace('\r\n', '\n').strip(),
       f'落了 {len(got)} 字 / 源 {len(RULES)} 字')
    ok('A3b 原文的 Markdown 结构也保住了（标题与引用行都还在）',
       got.lstrip().startswith('# 顶级规则') and '> 这本小说的硬规矩' in got,
       got[:60].replace('\n', '⏎'))

    # ── A4 对照组：世界观**会**被 LLM 压缩（说明两条通道确实不同）──
    # [EN] ── A4 Control group: worldview **will** be compressed by the LLM (showing the two channels
    # [EN] really are different) ──
    ok('A4 对照：`世界观.md` 不在规则采集范围里（它走 AI 提取那条路）',
       WORLD not in got and '漏刻' in got, '')

    # ── A5 兜底：没有规则文档时用 AI 提取的条目 ──
    # [EN] ── A5 Fallback: use AI-extracted entries when there is no rule document ──
    src2 = _fixture(tmp / 'src_ai', rules=False)
    items2 = scan_project(src2)
    got2 = PL.collect_rules(items2, {'顶级规则': ['没有鬼神', '一案收干净再起一案']})
    ok('A5 没有规则文档时，用 AI 从设定里提取的「顶级规则」条目兜底',
       got2.strip() == '- 没有鬼神\n- 一案收干净再起一案', repr(got2))

    # ── A6 两者都有 → 只用原文 ──
    # [EN] ── A6 Both present → use only the original text ──
    got3 = PL.collect_rules(scan_project(src), {'顶级规则': ['这条不该出现_AI条目']})
    ok('A6 ★ 原文与 AI 条目**同时存在时只用原文**（避免同一件事两种措辞打架）',
       '这条不该出现_AI条目' not in got3 and '漏刻' in got3, got3[:80].replace('\n', '⏎'))

    # ── A7 都没有 → 空 ──
    # [EN] ── A7 Neither present → empty ──
    ok('A7 既没有规则文档、AI 也没提取到 → 空字符串（不许凭空造）',
       PL.collect_rules(items2, {}) == '' and PL.collect_rules(items2, {'顶级规则': []}) == '',
       repr(PL.collect_rules(items2, {})))

    # ── A8 提取器的归一化（模型给的形状五花八门）──
    # [EN] ── A8 Extractor normalization (models give wildly varied shapes) ──
    shapes = {
        'list': ['甲', '乙'],
        '单字符串': '只有一条',
        '带前缀符号': ['- 甲', '· 乙'],
        'dict 包着': [{'规则': '甲'}, {'内容': '乙'}],
        '参杂空值': ['甲', '', None, '  '],
    }
    vals = {k: _validate({'顶级规则': v})['顶级规则'] for k, v in shapes.items()}
    ok('A8 ★ 「顶级规则」四种畸形输入都能归一成字符串数组',
       vals['list'] == ['甲', '乙'] and vals['单字符串'] == ['只有一条']
       and vals['带前缀符号'] == ['甲', '乙'] and vals['dict 包着'] == ['甲', '乙']
       and vals['参杂空值'] == ['甲'],
       json.dumps(vals, ensure_ascii=False))
    ok('A8b 空骨架里也有这个 key（别的模块按名取用，缺了会 KeyError）',
       _empty_skeleton().get('顶级规则') == [], _empty_skeleton())

    # ── A9 装配层读得回来（两种文件形态）──
    # [EN] ── A9 Assembly layer can read it back (two file forms) ──
    from sim.setup import load_settings, F_RULES
    sd = tmp / 'settings_a'
    sd.mkdir(parents=True, exist_ok=True)
    import yaml
    (sd / F_RULES).write_text(yaml.dump(RULES, allow_unicode=True), encoding='utf-8')
    got4 = load_settings(sd).get('rules', '')
    ok('A9 `load_settings` 读得回 `顶级规则.md`（摄取冻结的 YAML 字符串形态）',
       got4.replace('\r\n', '\n').strip() == RULES.replace('\r\n', '\n').strip(),
       f'{len(got4)} 字')

    sd2 = tmp / 'settings_b'
    sd2.mkdir(parents=True, exist_ok=True)
    (sd2 / F_RULES).write_text(RULES, encoding='utf-8')      # 用户手改的普通 markdown
    # [EN] Plain markdown hand-edited by the user
    got5 = load_settings(sd2).get('rules', '')
    ok('A9b 用户把它手改成普通 markdown 也认（两种形态都读得出来）',
       got5.replace('\r\n', '\n').strip() == RULES.replace('\r\n', '\n').strip(),
       f'{len(got5)} 字')
    ok('A9c 没有这个文件时是空字符串，不抛异常',
       load_settings(tmp / '不存在').get('rules', None) == '', '')

    # ── A10 world_prefix：位置、完整性、缺席 ──
    # [EN] ── A10 world_prefix: position, completeness, absence ──
    from world.state import WorldState
    w = WorldState(worldview_text='世界观占位', rules_text=RULES)
    pre = w.world_prefix()
    ok('A10 ★ 规则进 `world_prefix()`，而且排在**最前面**（权重最高）',
       pre.startswith('[顶级规则·不可违背]'), pre[:40].replace('\n', '⏎'))
    ok('A10b 规则是**原样**进去的，不是摘要（逐字包含）',
       RULES.strip() in pre, f'prefix {len(pre)} 字')
    w2 = WorldState(worldview_text='只有世界观')
    ok('A10c 没写规则时，prefix 里**不会**出现 `[顶级规则`（不许凭空多一段）',
       '[顶级规则' not in w2.world_prefix(), w2.world_prefix()[:60])

    # ── A11 超长规则：只截不概括 ──
    # [EN] ── A11 Overly long rules: truncate only, never summarize ──
    long_rules = '第%04d条：这是一条很长的规则，用来验证超长时的处理方式。\n' % 1
    long_rules = ''.join('规则%04d条，占位内容占位内容占位内容占位内容。\n' % i
                         for i in range(200))
    w3 = WorldState(rules_text=long_rules)
    pre3 = w3.world_prefix()
    body = pre3.split('\n', 1)[1]
    ok('A11 ★ 超长规则**截断但不概括**（前 2000 字与原文逐字相同）',
       body == long_rules[:2000] and len(body) == 2000, f'{len(body)} 字')
    ok('A11b 截断有上限，不会把世界观挤出去（prefix 长度可控）',
       len(pre3) < 2200, len(pre3))

    # ── A12 Agent 的规则前缀 ──
    # [EN] ── A12 Agent's rule prefix ──
    from agent.core import Agent
    from world.state import PersonState
    a = Agent.__new__(Agent)                     # 不跑 __init__，只要它读 self.world
    # [EN] Don't run __init__, just make it read self.world
    a.world = WorldState(rules_text=RULES)
    ok('A12 Agent `_rules_line()` 带上规则（省思/计划用）',
       '[顶级规则·不可违背]' in a._rules_line() and '漏刻只许校' in a._rules_line(),
       a._rules_line()[:50].replace('\n', '⏎'))
    a.world = WorldState()
    ok('A12b 没规则时 `_rules_line()` 是空串（不留空壳标记）',
       a._rules_line() == '', repr(a._rules_line()))

    # ── A13 护栏：重新冻结不许覆盖已有规则 ──
    # [EN] ── A13 Guardrail: refreezing must not overwrite existing rules ──
    from ingest.pipeline import _freeze
    sd3 = tmp / 'settings_c'
    sd3.mkdir(parents=True, exist_ok=True)
    _freeze(sd3, {'人物': []}, {}, {}, [], {'已完成节点': []}, rules_text=RULES)
    before = (sd3 / F_RULES).read_text(encoding='utf-8')
    # 界面上的「AI 优化」会再冻结一次 —— 那次手上没有扫描结果
    # [EN] The "AI optimize" in the UI freezes once more -- that time there are no scan results on hand
    _freeze(sd3, {'人物': []}, {}, {}, [], {'已完成节点': []}, rules_text=None)
    after = (sd3 / F_RULES).read_text(encoding='utf-8')
    ok('A13 ★ 重新冻结（`rules_text=None`）**不会**把已有规则覆盖成空',
       (sd3 / F_RULES).exists() and before == after and '漏刻' in after, len(after))

    # ── A14 摄取预览把「规则」摆出来 ──
    # [EN] ── A14 Ingestion preview surfaces the "rules" ──
    from ingest.preview import CATEGORY_ORDER
    ok('A14 摄取预览的分类顺序里有「规则」（界面上看得见这一类）',
       '规则' in CATEGORY_ORDER, CATEGORY_ORDER)


# ══════════════════════════════════════════════════════════════
#  B. 真机（MOCK）：真的开卷 → 真的装配 → 真的进 prompt
# [EN] B. Real machine (MOCK): really open the book → really assemble → really get into the prompt
# ══════════════════════════════════════════════════════════════
async def live_checks(tmp: Path) -> None:
    from verify_ui_common import isolate_projects_dir
    from logger import log_dir
    from llm.router import llm
    from ingest.pipeline import run_ingest
    from store.project import Project
    from store.runfolder import RunFolder
    from sim.setup import assemble
    import agent.core as AC

    isolate_projects_dir(tmp / 'Projects')
    await llm.ensure_started(log_dir())

    async def ingest_into(pname: str, src: Path):
        proj = Project(tmp / 'Projects' / pname, pname)
        proj.root.mkdir(parents=True, exist_ok=True)
        await run_ingest(src, settings_dir=proj.settings_dir)
        return proj

    # ── B1 开卷落盘 ──
    # [EN] ── B1 Open the book and write to disk ──
    proj = await ingest_into('规则项目', _fixture(tmp / 'src_live'))
    f = proj.settings_dir / '顶级规则.md'
    ok('B1 ★ 真跑一遍开卷 → `本地设定集/顶级规则.md` 生成了', f.exists(), str(f))
    import yaml
    landed = yaml.safe_load(f.read_text(encoding='utf-8')) if f.exists() else ''
    ok('B1b 落盘的内容与源文档逐字一致（走过 LLM 那条链路也没被改写）',
       isinstance(landed, str)
       and landed.replace('\r\n', '\n').strip() == RULES.replace('\r\n', '\n').strip(),
       f'{len(landed or "")} 字')

    # ── B2 装配 ──
    # [EN] ── B2 Assembly ──
    run = RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
    loop, world, _ = assemble(proj, run)
    world.progress_nodes = []
    ok('B2 装配后 `world.rules_text` 有内容，且与源文档逐字一致',
       world.rules_text.replace('\r\n', '\n').strip() == RULES.replace('\r\n', '\n').strip(),
       f'{len(world.rules_text)} 字')

    # ── B3 prompt 里真的有（拦下真正发出去的请求）──
    # [EN] ── B3 It's really in the prompt (intercept the request actually being sent) ──
    seen: list[dict] = []
    real_chat = AC.llm.chat

    async def spy(tier, messages, **kw):
        seen.append({'purpose': kw.get('purpose', ''),
                     'text': '\n'.join(str(m.get('content', '')) for m in messages)})
        return await real_chat(tier, messages, **kw)

    AC.llm.chat = spy
    try:
        agent = loop.agents[0]
        await agent.decide()
        await agent.talk(loop.agents[-1].name, topic='更漏', max_turns=1)
        await agent.reflect()
        await loop.director._inject_event()
    finally:
        AC.llm.chat = real_chat

    def grab(purpose: str) -> str:
        return next((s['text'] for s in seen if s['purpose'] == purpose), '')

    for purpose, label in (('agent_decide', '角色决策'), ('dialogue', '台词'),
                           ('director_event', '导演事件')):
        txt = grab(purpose)
        ok(f'B3 ★ {label}的 prompt 里带上了规则原文（{purpose}）',
           '漏刻只许校' in txt and '[顶级规则' in txt,
           (txt[:160] or '（没抓到这次调用）').replace('\n', '⏎'))
    ok('B3b 规则在 prompt 里排在世界观**之前**（权重更高）',
       grab('agent_decide').find('[顶级规则') < grab('agent_decide').find('[世界观]')
       if '[世界观]' in grab('agent_decide') else '[顶级规则' in grab('agent_decide'),
       '')

    # ── B4 反例：没写规则的项目 ──
    # [EN] ── B4 Counterexample: a project with no rules written ──
    proj2 = await ingest_into('无规则项目', _fixture(tmp / 'src_plain', rules=False))
    ok('B4 没写规则的项目**不会**生成 `顶级规则.md`',
       not (proj2.settings_dir / '顶级规则.md').exists(), '')
    run2 = RunFolder(proj2.root, '第1次模拟2026-01-01-00-00').create()
    loop2, world2, _ = assemble(proj2, run2)
    world2.progress_nodes = []
    ok('B4b 装配后 `rules_text` 是空的', (world2.rules_text or '') == '',
       repr(world2.rules_text))
    seen.clear()
    AC.llm.chat = spy
    try:
        await loop2.agents[0].decide()
    finally:
        AC.llm.chat = real_chat
    ok('B4c ★ 反例：没有规则时 prompt 里**不会**出现 `[顶级规则`（不凭空多一段）',
       seen and '[顶级规则' not in seen[0]['text'],
       (seen[0]['text'][:120] if seen else '（没抓到）').replace('\n', '⏎'))


# ══════════════════════════════════════════════════════════════
async def main() -> int:
    # ⚠ 临时目录名**绝对不能含关键词**：`_classify` 是拿**完整路径**去匹配的
    #   （其他分类也是，比如 `设定/人物/主角.md` 靠"人物"那一级命中）。
    #   第一版这里用了 `prefix='nws_rules_'` —— 于是**每一个**夹具文件的路径里
    #   都有 "rule"，全被判成「规则」，A3/A5/A7/B1 一起红。
    #   那不是产品的问题，是判据自己给自己挖的坑。现在用中性名。
    # [EN] ⚠ The temp directory name **absolutely must not contain keywords**: `_classify` matches against
    # [EN] the **full path**
    # [EN] The first version used `prefix='nws_rules_'` here -- so **every** fixture file's path
    # [EN] contained "rule", all were judged as "rules", and A3/A5/A7/B1 all went red together.
    # [EN] That wasn't a product problem, it was the criterion digging its own pit. Now a neutral name is
    # [EN] used.
    tmp = Path(tempfile.mkdtemp(prefix='nws_tl_'))
    try:
        logic_checks(tmp)
        await live_checks(tmp)
    except BaseException:                                    # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()
        print(report['fatal'])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'world_rules_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n顶级规则验证：{len(report["checks"]) - len(bad)}/{len(report["checks"])}')
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    print('报告：assets/screenshots/world_rules_report.json')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
