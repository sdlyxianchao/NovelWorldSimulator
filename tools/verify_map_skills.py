# -*- coding: utf-8 -*-
"""把地图知识落地成 skills 之后的判据（`verify_map_skills`）。

## 为什么这件事必须有判据

"写成文档"最容易变成**看起来很丰满、实际上已经和代码说两套话**。三处具体的风险：

1. **空壳技能**：目录建了、`SKILL.md` 只有标题，路由照样命中它，然后给出没有内容的答案。
   —— 空壳比没有更坏。
2. **文档与代码脱节**：正文写"退让 4.35px"、代码改成 6.0，没人会发现。
3. **触发关键词互相覆盖**：`地图-城市` 和 `地图-街道` 都写"街区" ⇒ 永远只命中先注册的那个，
   另一份等于不存在。

所以这里的判据不是"检查文件在不在"，而是逐个盯住这三件事：
`A` 结构与实质、`B` 覆盖、`C` 关键词不撞、`D` 引用的代码符号存在、`E` 数值与代码一致。

[EN] Criteria after landing the map knowledge as skills. ## Why criteria are required "writing docs"
easily becomes "looks rich but speaks a different language than the code". Three concrete risks:
(1) **shell skills** -- the directory exists, `SKILL.md` is only a heading, routing still hits it and
answers nothing (a shell is worse than nothing); (2) **doc/code drift** -- the text says "retreat
4.35px" while the code says 6.0 and nobody notices; (3) **colliding trigger keywords** -- if both the
city and the street pack list 街区, only the first registered one ever matches and the other might as
well not exist. So these criteria are not "does the file exist" but: `A` structure and substance,
`B` coverage, `C` no keyword collisions, `D` every cited code symbol exists, `E` numbers match code.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / 'logs'
REPORT = OUT / 'map_skills_report.json'

CHECKS: list = []


def ok(name: str, cond, note: str = '') -> bool:
    CHECKS.append({'name': name, 'ok': bool(cond), 'note': str(note)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {note}' if note else ''))
    return bool(cond)


def head(t: str) -> None:
    print(f'\n{"=" * 62}\n{t}\n{"=" * 62}')


#: 构件层必须有的 8 份（**闭集**：加一份要改这里，改的时候会想起来看判据）
# [EN] The 8 component packs that must exist (a closed set: adding one means editing this list)
NEED_COMPONENTS = ('制图规范', '室内平面', '家具', '街道与路网', '城市', '城际', '水系',
                    '甲板',
                    # 2026-10-27 第二批（用户要求把建筑/室内设计/道路/城市等信息也落地）
                    # [EN] Second batch (2026-10-27): building / interior / road / city and more
                    '建筑类型与形制', '尺度与模数', '室内设计与动线', '道路与街道工程',
                    '城市选址与形态', '材料与构造', '色彩与纹样')
#: 索引必须有的 1 份
NEED_INDEX = ('总索引',)

_SKILL_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)


def _packs() -> dict:
    """`{目录名: {'md': 路径, 'meta': 文本, 'body': 正文, 'json': 资料}}`。"""
    out = {}
    for d in sorted((ROOT / 'skills').glob('地图-*')):
        md = d / 'SKILL.md'
        if not md.is_file():
            out[d.name] = {'md': md, 'meta': '', 'body': '', 'json': None}
            continue
        txt = md.read_text(encoding='utf-8', errors='ignore')
        m = _SKILL_RE.match(txt)
        meta = m.group(1) if m else ''
        body = txt[m.end():] if m else txt
        js = None
        jp = d / '资料.json'
        if jp.is_file():
            try:
                js = json.loads(jp.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                js = None
        out[d.name] = {'md': md, 'meta': meta, 'body': body, 'json': js}
    return out


def _kw(meta: str) -> list:
    """从 frontmatter 里取 `触发关键词` 列表（YAML 太复杂的不引，这里只认 `- xxx` 形式）。"""
    out, grab = [], False
    for line in meta.splitlines():
        if line.startswith('触发关键词:'):
            grab = True
            continue
        if grab:
            s = line.strip()
            if s.startswith('- '):
                out.append(s[2:].strip().strip('"\''))
            elif s and not line.startswith(' '):
                break
    return [k for k in out if k]


def test_structure(packs: dict) -> bool:
    """A. 每份都有实质内容（不是空壳）。"""
    ok_ = True
    thin = []
    for name, p in packs.items():
        body = p['body'].strip()
        # 去掉自动生成那行注释再算长度
        body = body.replace('<!-- generated-by', '<!-- ')
        if len(body) < 400:
            thin.append((name, len(body)))
    ok_ &= ok('A1 ★★★ 每份技能的正文**不是空壳**（≥400 字；空壳比没有更坏 ——'
              '它会被路由命中，然后给出没有内容的答案）',
              not thin, str(thin))

    missing = [n for n, p in packs.items()
               if not all(k in p['meta'] for k in ('名称:', '触发关键词:', '用途:'))]
    ok_ &= ok('A2 ★★ 每份 frontmatter 都有 `名称` / `触发关键词` / `用途`'
              '（`skills.registry` 靠这三样路由）', not missing, str(missing))

    nojson = [n for n, p in packs.items() if not isinstance(p['json'], dict)]
    ok_ &= ok('A3 ★★ 每份都有 `资料.json`（给程序读的结构；只写 md 程序读不回来）',
              not nojson, str(nojson))

    # 构件档必须有"表格或编号清单"—— 那才叫规则；纯散文的文档没法照着做
    # [EN] Component packs must contain a table or a numbered list -- that is what makes it a rule
    # [EN] rather than prose you cannot follow.
    prose = []
    for name, p in packs.items():
        b = p['body']
        if not ('|' in b or re.search(r'^\s*\d+\.\s', b, re.M)):
            prose.append(name)
    ok_ &= ok('A4 ★★ 每份都有**可照着做的结构**（表格或编号清单），不是一段散文',
              not prose, str(prose))
    return ok_


def test_coverage(packs: dict) -> bool:
    """B. 构件 8 份 + 索引 1 份 + 题材覆盖 `worldstyle.ALL` 全部。"""
    from image_gen import worldstyle as WS
    ok_ = True
    names = set(packs)
    miss_c = []
    for c in NEED_COMPONENTS:
        if not any(n == f'地图-{c}' or n.startswith(f'地图-{c}') for n in names):
            miss_c.append(c)
    ok_ &= ok('B1 ★★★ **构件层 15 份齐全**（怎么画/怎么盖/多宽：制图/水系/家具/室内/街道/城市/城际/甲板'
              ' + 建筑形制/尺度模数/室内动线/道路工程/城市形态/材料/色彩）',
              not miss_c, f'缺 {miss_c}')
    ok_ &= ok('B2 ★★ 索引 1 份在（先看哪份、怎么拼）',
              any(n.startswith('地图-总索引') for n in names), str(sorted(names))[:120])

    # 题材层：每个档案都要有一份（名字前缀配对）
    miss_g = []
    for st in WS.ALL:
        short = st.名.split('（')[0].strip()
        if not any(n == f'地图-{short}' or n.startswith(f'地图-{short}') for n in names):
            miss_g.append(short)
    ok_ &= ok('B3 ★★★ **每个题材档案都有对应技能**（worldstyle 里有几个就要有几份）',
              not miss_g, f'缺 {miss_g}')
    return ok_


def test_keywords(packs: dict) -> bool:
    """C. 触发关键词不许跨技能重复（重复 = 后注册的那份等于不存在）。"""
    ok_ = True
    owner: dict = {}
    dup: dict = {}
    for name, p in packs.items():
        for k in _kw(p['meta']):
            if len(k) < 2:          # 单字关键词会把别的全命中（`skills.registry` 的规矩）
                continue
            if k in owner and owner[k] != name:
                dup.setdefault(k, [owner[k]]).append(name)
            else:
                owner[k] = name
    ok_ &= ok('C1 ★★★ 触发关键词**跨技能不重复**（重复 = 永远只命中先注册的那份）',
              not dup, str({k: v for k, v in list(dup.items())[:6]}))
    # ★ 只查**自动生成**的档：`artresearch` 落盘的那两份（中式店宅/奇幻）带了单字关键词
    #   （`堂`/`厅`/`殿`），但 `skills.registry` 已经规定"单字不参与子串匹配、只允许整词相等"，
    #   所以它们**不构成覆盖**。去改那两份等于动别人查来的资料，判据不该逼人这么干。
    # [EN] ★ Only auto-generated packs are checked: the two written by `artresearch` carry single-
    # [EN] character keywords (堂/厅/殿), but `skills.registry` already specifies that single
    # [EN] characters do not take part in substring matching (exact word only), so they do not
    # [EN] collide. Editing those two would mean touching researched material.
    short = {n: [k for k in _kw(p['meta']) if len(k) < 2]
             for n, p in packs.items()
             if 'generated-by: build_map_skills.py' in p['body']}
    short = {n: v for n, v in short.items() if v}
    ok_ &= ok('C2 ★★ 自动生成的档里没有**单字**触发关键词'
              '（单字会把"名字/文字"全命中 —— registry 里已写明；已有档的单字由 registry 过滤）',
              not short, str(short)[:160])
    ok_ &= ok('C3 ★★ 每份至少有 3 个触发关键词（少于 3 个基本路由不到）',
              all(len(_kw(p['meta'])) >= 3 for p in packs.values()),
              str({n: len(_kw(p['meta'])) for n, p in packs.items() if len(_kw(p['meta'])) < 3}))
    return ok_


_SYM_RE = re.compile(r'image_gen/([A-Za-z_][\w]*)\.py::([A-Za-z_][\w]*)')


def test_citations(packs: dict) -> bool:
    """D. 正文引用的代码符号**真的存在**（这一条才真正防"文档与代码说两套话"）。"""
    bad = []
    n_cited = 0
    for name, p in packs.items():
        for mod, sym in _SYM_RE.findall(p['body'] + '\n' + p['meta']):
            n_cited += 1
            try:
                m = importlib.import_module(f'image_gen.{mod}')
            except Exception:                                  # noqa: BLE001
                bad.append((name, f'image_gen.{mod}', '模块导入失败'))
                continue
            if not hasattr(m, sym):
                bad.append((name, f'{mod}::{sym}', '符号不存在'))
    ok_ = ok('D1 ★★★ 每份技能引用的 `image_gen.xxx::符号` **都真的存在**'
             '（文档写"退让 4.35px"而代码改成 6.0，靠这条抓不到数值漂移；'
             '但符号被删/改名一定会红）',
             not bad and n_cited >= 8, f'引用 {n_cited} 处 · 失效 {bad[:5]}')
    return ok_


def test_numbers(packs: dict) -> bool:
    """E. 写进技能的**数值**与代码一致（这条抓"文档里的数没跟着改"）。"""
    from image_gen import furniture as FR
    from image_gen import scale as SC
    from image_gen import worldstyle as WS
    ok_ = True

    # E1 家具尺寸表与代码一致
    p = packs.get('地图-家具') or {}
    js = p.get('json') or {}
    rows = {r.get('key'): r for r in (js.get('类别') or []) if isinstance(r, dict)}
    mism = []
    for sp in FR.SPECS:
        r = rows.get(sp.key)
        if not r or float(r.get('宽', -1)) != float(sp.w) or float(r.get('高', -1)) != float(sp.h):
            mism.append(sp.key)
    ok_ &= ok('E1 ★★★ 「地图-家具」里的尺寸表**与 `furniture.SPECS` 逐条一致**'
              '（不一致说明文档没跟着代码改）', not mism, str(mism))

    # E2 路宽表与 ROAD_SPEC 一致
    p2 = packs.get('地图-街道与路网') or {}
    js2 = (p2.get('json') or {}).get('分级') or {}
    bad2 = []
    for k in SC.ROAD_CLASSES:
        got = js2.get(k) or {}
        if float(got.get('外宽', -1)) != float(SC.ROAD_SPEC[k][0]) \
                or float(got.get('内宽', -1)) != float(SC.ROAD_SPEC[k][1]):
            bad2.append(k)
    ok_ &= ok('E2 ★★★ 「地图-街道与路网」里的路宽表**与 `scale.ROAD_SPEC` 一致**',
              not bad2, str(bad2))

    # E3 题材档的四个开关与 worldstyle 一致（路网/城际最容易漏搬）
    bad3 = []
    for st in WS.ALL:
        short = st.名.split('（')[0].strip()
        cand = [n for n in packs if n == f'地图-{short}' or n.startswith(f'地图-{short}')]
        if not cand:
            bad3.append((short, '缺档'))
            continue
        js3 = packs[cand[0]].get('json') or {}
        if js3.get('路网') != st.路网 or js3.get('城际') != st.城际:
            bad3.append((short, js3.get('路网'), st.路网, js3.get('城际'), st.城际))
    ok_ &= ok('E3 ★★★ 题材档的 **`路网` / `城际` 两个开关**与 `worldstyle` 一致'
              '（这两个字段改一处会漏一处 —— 本项目的老坑）',
              not bad3, str(bad3[:4]))
    return ok_


def test_domains(packs: dict) -> bool:
    """F. 题材档的"五域差异"（建筑/家具/室内/道路/城市）必须**有内容**，不是占位。

    ★★ 为什么单列一组：这一节最容易变成"五行 + 暂无" —— 那和空壳是一回事，
      只不过它藏在看起来结构完整的表格里，A1 的长度检查也未必抓得住
      （表格会把字数填满）。
    ★ 判两件事：
      ① 每个题材档都有这一节，五行都有；
      ② 每行的内容**不是**占位词（"暂无/待补/TBD/—"），且长度够（≥8 字）。
    [EN] F. A genre pack's "five domains" section (building/furniture/interior/road/city) must hold
    [EN] **content**, not placeholders. ★★ Why its own group: this section degrades into "five rows +
    [EN] TBD", which is a shell wearing a well-structured table -- and A1's length check can be fooled
    [EN] because the table pads the character count. ★ Two assertions: (1) every genre pack has the
    [EN] section with all five rows; (2) each row is not a placeholder and is at least 8 characters.
    """
    import re as _re
    ok_ = True
    PLACEHOLDER = ('暂无', '待补', 'TBD', 'todo', 'TODO', '—', '（无）', '略')
    missing, thin = [], []
    n_genre = 0
    for name, p in packs.items():
        body = p['body']
        if '## 五域差异' not in body:
            is_genre = '## 画法总纲' in body
            if is_genre:
                missing.append(name)
            continue
        n_genre += 1
        seg = body.split('## 五域差异', 1)[1]
        rows = {}
        for line in seg.splitlines():
            m = _re.match(r'\| \*\*(建筑|家具|室内|道路|城市)\*\* \|[^|]*\| ?(.*?) ?\|\s*$', line)
            if m:
                rows[m.group(1)] = m.group(2).strip()
        for dom in ('建筑', '家具', '室内', '道路', '城市'):
            val = rows.get(dom)
            if val is None or len(val) < 8 or any(val.startswith(k) for k in PLACEHOLDER):
                thin.append((name, dom, (val or '缺行')[:20]))
    ok_ &= ok('F1 ★★★ 每个题材档都有"五域差异"一节（建筑/家具/室内/道路/城市）',
              not missing, str(missing))
    ok_ &= ok('F2 ★★★ 五域每一行都**有实质内容**（≥8 字、不是"暂无/待补"这类占位）'
              '（占位表格＝穿了外衣的空壳，长度检查抓不到）',
              not thin and n_genre >= 10,
              f'{n_genre} 份题材档 · 不合规 {thin[:5]}')
    return ok_


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ok_ = True
    try:
        packs = _packs()
        head(f'地图技能：共 {len(packs)} 份')
        head('A. 结构与实质（不是空壳）')
        ok_ &= test_structure(packs)
        head('B. 覆盖（构件 8 + 索引 1 + 题材全覆盖）')
        ok_ &= test_coverage(packs)
        head('C. 触发关键词不互相覆盖')
        ok_ &= test_keywords(packs)
        head('D. 引用的代码符号真的存在')
        ok_ &= test_citations(packs)
        head('E. 写进去的数值与代码一致')
        ok_ &= test_numbers(packs)
        head('F. 题材档的五域差异（建筑/家具/室内/道路/城市）不是占位')
        ok_ &= test_domains(packs)
    except Exception:                                          # noqa: BLE001
        fatal = traceback.format_exc()
        ok('验证没有中途崩溃（有崩溃就不是全绿）', False, fatal[-300:])
        ok_ = False
        print(fatal)

    n = sum(1 for c in CHECKS if c['ok'])
    total = len(CHECKS)
    REPORT.write_text(json.dumps({'ok': bool(ok_), 'passed': n, 'total': total,
                                  'at': datetime.now().isoformat(timespec='seconds'),
                                  'checks': CHECKS}, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print(f'\n地图技能验证：{n}/{total}' + ('' if ok_ and n == total else '   ← 有失败'))
    return 0 if (ok_ and n == total) else 2


if __name__ == '__main__':
    sys.exit(main())
