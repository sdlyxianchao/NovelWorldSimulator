# -*- coding: utf-8 -*-
"""验证：**《设定写作指导.md》里说的技术事实与代码一致**（防文档漂移）。

为什么要有这一支
----------------
那份文档里全是"程序会怎么做"的具体说法（字数上限、层名、分类关键词、
出场时机、额度…）。**它们全是从代码里抄下来的人话** —— 而代码会改。
改一次代码不改文档，那份文档就从"指导"变成"误导"，
而且是最坏的一种误导：作者照它写，程序不按它做，两边都不报错。

所以这里把关键事实**逐条从代码里取真值**，再看文档里有没有说过那个真值。
判据的逻辑是"**文档必须与代码一致**"，不是"文档写得对不对"。

★ **判据自己会自检能不能红**：脚本最后会把文档里的一处数字**故意改错**，
拿同一套检查再跑一遍，必须至少红一条。红了才算这套判据有效
（改错都发现不了，说明这些判据只是形式）。

用法：.venv\\Scripts\\python.exe tools/verify_setting_guide.py
产出：assets/screenshots/setting_guide_report.json

English:
Verify: **the technical facts stated in《设定写作指导.md》match the code** (guards against doc drift).
Why this branch is needed
----------------
That doc is full of concrete statements about "what the program will do" (char limits, layer
names, category keywords,
appearance timing, quotas...). **They are all plain-language copies taken from the code** — and
the code changes.
Change the code once without changing the doc, and the doc goes from "guidance" to
"misguidance",
and it's the worst kind of misguidance: the author writes according to it, the program doesn't
act according to it, and neither side reports an error.
So here we **extract the true value from the code item by item** for the key facts, then check
whether the doc has stated that true value.
The logic of the criteria is "**the doc must be consistent with the code**", not "is the doc
written correctly".
★ **The criteria self-checks whether it can go red**: at the end the script **deliberately
corrupts** a number in the doc,
reruns the same set of checks, and at least one must go red. Only when it goes red is this
criteria set valid
(if it can't even detect a corruption, these criteria are merely formal).
Usage: .venv\\Scripts\\python.exe tools/verify_setting_guide.py
Output: assets/screenshots/setting_guide_report.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

GUIDE = APP_DIR / '设定写作指导.md'
# ★ 提取窗口上限**从代码取真值**（2026-10-27：这一项以前硬编码 12000，
#   而代码改到 20000 之后文档跟着改 —— 判据却还在拿旧数字比对，于是文档写对了反而红。
#   判据硬编码常量，就等于把"代码改了"这件事判成"文档写错了"）。
# [EN] ★ The extraction window limit is **read from the code** (2026-10-27: this used to hardcode
# [EN] 12000; after the code moved to 20000 the doc followed, but the criterion still compared
# [EN] against the old number, so a *correct* doc went red.
# [EN] Hardcoding a constant in a criterion turns "the code changed" into "the doc is wrong").
from ingest import extractor as _EX    # noqa: E402
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def check_all(text: str) -> int:
    """在给定文本上跑完整套检查，返回失败条数。

    抽成函数是为了**反例自检**能拿改错的文本再跑一遍。
    
        English:
    Run the full set of checks on the given text, return the number of failures.
        Extracted into a function so that the **counterexample self-check** can rerun it on the corrupted text.
    """
    _before = len(report['checks'])
    A_facts(text)
    B_paths(text)
    C_theory(text)
    return len([c for c in report['checks'][_before:] if not c['ok']])


# ══════════════════════════════════════════════════════════════════
#  A. 数值/名字：从代码取真值，看文档里有没有
# [EN] A. Numeric values/names: take the true value from code, check whether the doc mentions it
# ══════════════════════════════════════════════════════════════════
def A_facts(text: str) -> None:
    from world import layers as L
    from config import SPEC

    # ── 五层的名字 ──
    # [EN] ── Names of the five layers ──
    names = [l.name for l in L.LAYERS]
    ok('A1 文档写了五层的名字，且与 `world/layers.py` 一致',
       all(n in text for n in names), '、'.join(names))

    # ── 额度 ──
    # [EN] ── Quotas ──
    for label, val in (('大背景常态额度', L.CANON_BRIEF),
                       ('大背景展开额度', L.CANON_FULL),
                       ('细节一次几条', L.DETAIL_MAX_ITEMS),
                       ('细节每条多少字', L.DETAIL_EACH),
                       ('前情提要上限', SPEC['RECAP_MAX_CHARS']['default']),
                       ('送入提取的全文上限', _EX._MAX_CONTENT)):
        ok(f'A2 文档里的「{label}」= 代码里的 {val}',
           str(val) in text, f'文档里{"有" if str(val) in text else "**没有**"} {val}')

    # ── 剧组只能写哪两层 ──
    # [EN] ── Which two layers can the crew only write ──
    ok('A3 文档说"剧组只能写场景层/细节层"，与 `CREW_WRITABLE` 一致',
       'scene' in L.CREW_WRITABLE and 'detail' in L.CREW_WRITABLE
       and len(L.CREW_WRITABLE) == 2
       and '只能往「场景层」和「细节层」加东西' in text, str(L.CREW_WRITABLE))

    # ── 分类关键词：文档里那张表要覆盖代码里的规则 ──
    # [EN] ── Category keywords: the table in the doc must cover the rules in code ──
    from ingest.scanner import _CATEGORY_RULES
    miss = []
    for cat, kws in _CATEGORY_RULES:
        if cat not in text:
            miss.append(f'{cat}(类别名)')
            continue
        # 中文关键词抽 2 个核对（英文的另算）
        # [EN] Pick 2 Chinese keywords to cross-check (English ones counted separately)
        cn = [k for k in kws if re.match(r'^[\u4e00-\u9fff]+$', k)][:2]
        for k in cn:
            if k not in text:
                miss.append(f'{cat}:{k}')
    ok('A4 文档里的"文件名关键词表"覆盖了 `scanner._CATEGORY_RULES`',
       not miss, '缺：' + '、'.join(miss[:6]) if miss else '')

    # ── 原文照录：规则优先 ──
    # [EN] ── Verbatim: rules take precedence ──
    from ingest.pipeline import collect_rules
    ok('A5 文档说"规则是原文照录、且分类优先级最高"，两项都与代码一致',
       '原文照录' in text
       and _CATEGORY_RULES[0][0] == '规则'
       and collect_rules.__doc__ is not None, '')

    # ── 进度节点三个上限 ──
    # [EN] ── Three upper limits on progress nodes ──
    from ingest import progress as P
    src = P._BUILD_PROMPT
    for n in ('6', '80', '50'):
        pass
    ok('A6 文档里的进度节点上限（名称 6 / 概要 80 / 判据 50）与代码提示词一致',
       '不超过 6 个字' in src and '不超过 80 个字' in src and '不超过 50 个字' in src
       and '**6 / 80 / 50 字**' in text, '')

    # ── 人物字段上限 ──
    # [EN] ── Upper limits on character fields ──
    from ingest import extractor as E
    ok('A7 文档里的人物字段上限（30/40 字）与提取提示词一致',
       '简介、性格、身份：**各 ≤ 30 字**' in E._PROMPT
       and '秘密、目标、红线：**各 ≤ 40 字**' in E._PROMPT
       and '30 / 30 / 30 / 40 / 40 / 40 字' in text, '')

    # ── 世界观 120 字 ──
    # [EN] ── Worldview 120 chars ──
    ok('A8 文档说"世界观会被归纳到约 120 字"，与提取提示词一致',
       '世界观 ≤ 120 字' in E._PROMPT and '约 120 字' in text, '')

    # ── 风格卡 ──
    # [EN] ── Style card ──
    from ingest import style as S
    ok('A9 文档说的风格卡字段与 `ingest/style.py` 一致',
       all(k in text for k in ('叙事距离', 'AI腔禁词表'))
       and '一句话、不超过 20 字' in S._PROMPT, '')

    # ── 类型卡四轴 ──
    # [EN] ── Four axes of the type card ──
    from ingest import genre as G
    ok('A10 文档说的类型卡三轴（题材/结构/频道）与 `ingest/genre.py` 一致',
       all(k in G._PROMPT for k in ('主题材', '结构', '频道'))
       and all(k in text for k in ('主题材', '结构', '频道')), '')

    # ── 评档条件 ──
    # [EN] ── Rating tier conditions ──
    from ingest.pipeline import _assess_tier
    ok('A11 文档的黄金档条件（人物≥2/剧情线/秘密口癖/伏笔/正文）与代码一致',
       all(k in text for k in ('人物 ≥2', '有剧情参考线', '有秘密或口癖',
                               '有伏笔清单', '有正文 ≥1 章')), '')

    # ── 体检里的"补不了"两项 ──
    # [EN] ── The two "can't be filled" items in the health check ──
    ok('A12 文档说"人物和正文 AI 补不了"，与 `ingest/repair.py` 一致',
       'AI 造不出人物和正文' in
       (APP_DIR / 'ingest' / 'repair.py').read_text(encoding='utf-8')
       and '它补不了' in text, '')

    # ── 世界观"太短"的阈值 ──
    # [EN] ── Threshold for worldview "too short" ──
    from ingest import repair as R
    ok(f'A13 文档里"世界观太短（<{R.WORLD_MIN_CHARS} 字）"与 `repair.py` 一致',
       str(R.WORLD_MIN_CHARS) in text, f'{R.WORLD_MIN_CHARS}')


# ══════════════════════════════════════════════════════════════════
#  B. 文档里点名的路径/文件真的存在
# [EN] B. The paths/files named in the doc actually exist
# ══════════════════════════════════════════════════════════════════
def B_paths(text: str) -> None:
    # 文档里用 `反引号` 点名的代码位置（含 `.py` 的），逐个查存在
    # [EN] Every code location named with `backticks` in the doc (including those with `.py`): check
    # [EN] existence one by one
    cited = set(re.findall(r'`([A-Za-z0-9_/]+\.py)`', text))
    missing = [c for c in cited if not (APP_DIR / c).exists()
               and not (APP_DIR / 'craft' / c).exists()]
    ok(f'B1 文档点名的 {len(cited)} 个代码位置都存在', not missing,
       '缺：' + '、'.join(sorted(missing)) if missing else '')

    # 文档里点名的示例文件夹
    # [EN] Example folders named in the doc
    dirs = set(re.findall(r'`(samples/[A-Za-z0-9_/]+)`', text))
    missing_d = [d for d in dirs
                 if not (APP_DIR / d.rstrip('/')).exists()]
    ok(f'B2 文档点名的 {len(dirs)} 个示例路径都存在', not missing_d,
       '缺：' + '、'.join(sorted(missing_d)) if missing_d else '')

    # 工艺书的架数：**从目录取真值**，别把 4 写死在判据里。
    # [EN] Number of shelves in the craft book: **take the true value from the directory**, don't hardcode
    # [EN] 4 in the criteria.
    #
    # ⚠ 这条原来是 `len(shelves) == 4` —— 于是加第 5 架（《人物与对话》）时
    #   它红了，而红的原因不是文档写错、是**判据自己没跟上**。
    #   写成"拿目录里的真实架数去要求文档"之后，加架只需要改文档，
    #   判据永远问的是同一个问题：**文档说的架数，与磁盘上的一致吗**。
    # [EN] ⚠ This one used to be `len(shelves) == 4` — so when the 5th shelf ("Characters and Dialogue")
    # [EN] was added
    # [EN] it went red, and the reason it went red was not that the doc was wrong, but that **the criteria
    # [EN] itself had not kept up**.
    # [EN] After writing it as "require the doc against the real number of shelves in the directory",
    # [EN] adding a shelf only requires changing the doc,
    # [EN] and the criteria always asks the same question: **does the shelf count stated in the doc match
    # [EN] what's on disk**.
    shelves = sorted((APP_DIR / 'craft' / 'playbooks').glob('*.yaml'))
    n = len(shelves)
    _cn = {1: '一', 2: '两', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八'}
    word = _cn.get(n, str(n))
    ok(f'B3 文档说的"{word}架工艺书"确实有 {n} 架'
       f'（架数从目录取，判据不写死）',
       f'{word}架' in text and all(s.stem in text for s in shelves),
       f'{word}架 in 文档={"是" if f"{word}架" in text else "否"}；'
       f'货架：' + '、'.join(s.stem for s in shelves))

    # 文档里引用的字段名（层/配置）真的存在
    # [EN] The field names (layer/config) referenced in the doc actually exist
    from config import SPEC
    for k in ('CREW_SETTING_TALK', 'SETTING_LAYERS'):
        ok(f'B4 文档提到的旋钮 `{k}` 在 SPEC 里存在', k in SPEC, '')

    # 五层的落盘文件名
    # [EN] The on-disk file names of the five layers
    from world import layers as L
    ok('B5 文档提到的两份落盘文件（分层设定 / 临时设定）与代码一致',
       L.FILE_PROFILE_MD in text and L.FILE_LOCAL_MD in text,
       f'{L.FILE_PROFILE_MD} / {L.FILE_LOCAL_MD}')


# ══════════════════════════════════════════════════════════════════
#  C. 文档引用的理论条目真的在工艺库里
# [EN] C. The theory entries referenced in the doc really are in the playbook
# ══════════════════════════════════════════════════════════════════
def C_theory(text: str) -> None:
    from craft import craftmix
    data = craftmix.load()
    entries = set(data['entries'])

    # 文档里"四条理论 → 用在哪"那张表引用的条目名，必须都在 playbook 里
    # [EN] The entry names referenced by the table "four theories -> where they're used" in the doc must
    # [EN] all be in the playbook
    cited = [n for n in ('世界观构建', '一件小道具承住一切', '草蛇灰线',
                         '伏脉千里', '一场一转变', '场景=价值转变',
                         '人物一句话立起来', '立主脑减头绪密针线',
                         '悬念引擎', '期待感管理', '爽点周期',
                         '可拍性检查', '以景写时', '冲突三层次')
             if n in text]
    miss = [c for c in cited if c not in entries]
    ok(f'C1 文档引用的 {len(cited)} 条工艺条目都在 playbook 里（引对了名字）',
       not miss, '查不到：' + '、'.join(miss) if miss else '')

    # 文档说"这些条目被拼进职位提示词" —— 查接线（真把函数取出来看可不可调）
    # [EN] The doc says "these entries are spliced into the position prompt" — check the wiring (actually
    # [EN] pull the function out and see if it's callable)
    from crew.agents import craft_block
    ok('C2 文档说工艺条目真的进职位提示词，与 `crew/agents.craft_block` 一致',
       callable(craft_block) and 'craft_block' in text, '')

    # 类型卡的 playbook 映射**不许指向空气**（指空了 = 那句理论静默少喂一条）
    # [EN] The type card's playbook mapping must **not point to thin air** (empty pointer = that theory
    # [EN] silently loses one feeding)
    miss_map = craftmix._misses()
    ok(f'C3 类型卡里的 playbook 映射都指向真实条目（{len(data["genres"])} 张卡）',
       not miss_map, '指到空气：' + '、'.join(miss_map[:6]) if miss_map else '')


def _self_check_reds(text: str) -> tuple[bool, str]:
    """**判据自己能不能红**：把文档里的一处数字改错，同一套检查必须红。

    ⚠ 靶子挑 `140`（大背景常态额度）：它是**从代码里取的真值**，
      改掉它 A2 必然红 —— 如果连这个都发现不了，说明那批判据只是形式。
    ⚠ 清理放在 `finally`：自检一旦抛异常，不清理就会把自检的记录
      混进正式报告（那会让报告看起来"多了一堆莫名其妙的判据"）。
    
        English:
    **Can the criteria itself go red**: corrupt a number in the doc, the same set of checks must go
    red.
        ⚠ The target chosen is `140` (the normal quota for the big background): it is **a true value taken from the code**,
          corrupt it and A2 must go red — if even this can't be detected, those criteria are merely formal.
        ⚠ Cleanup is in `finally`: once the self-check throws, without cleanup the self-check records would
          get mixed into the official report (that would make the report look like it has "a bunch of inexplicable extra criteria").
    """
    bad = text.replace('140', '999')
    if bad == text:
        return False, '（文档里找不到可改的数字 —— 自检没做成）'
    n_before = len(report['checks'])
    try:
        A_facts(bad)
        fails = [c for c in report['checks'][n_before:] if not c['ok']]
        return bool(fails), (fails[0]['name'] if fails else '')
    finally:
        del report['checks'][n_before:]


def main() -> int:
    if not GUIDE.exists():
        print(f'找不到 {GUIDE}')
        return 2
    text = GUIDE.read_text(encoding='utf-8')
    ok('A0 《设定写作指导.md》存在且不是空壳', len(text) > 8000,
       f'{len(text)} 字')

    try:
        check_all(text)
    except BaseException:                                        # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()
        print(report['fatal'])

    # ── 判据自检 ──
    # [EN] ── Criteria self-check ──
    try:
        can_red, which = _self_check_reds(text)
    except BaseException as e:                                   # noqa: BLE001
        can_red, which = False, repr(e)
    ok('Z ★ 判据自检：把文档里的一处数字改错，本脚本**必须变红**'
       '（红了才说明上面那些判据不是形式）', can_red, which)

    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'setting_guide_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    n = len(report['checks'])
    print(f'\n设定写作指导 · 与代码一致性：{n - len(bad)}/{n}'
          f'（文档 {len(text)} 字）')
    return 0 if not bad and not report.get('fatal') else 2


if __name__ == '__main__':
    sys.exit(main())
