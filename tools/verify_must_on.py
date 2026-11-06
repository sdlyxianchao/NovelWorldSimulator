# -*- coding: utf-8 -*-
"""验证：**「必出日」这条链**（解析 → 建索引 → 选 → 渲染）。

★★ 这条链守的是 2026-10-27 修的那个真 bug：作者/模型在细节层写了「必出日」，
   可是它**静默不出场** —— 程序照跑，谁也不知道那一栏被丢了。
   旧的中文数字解析**只认单个字**（「三」认得、「十五」不认），
   而模型与作者写的偏偏常是「第十五章」⇒ 一条一条地悄悄失效。

   所以这条判据验的是"**作者写了就一定出得来**"，分四段：
     A. `parse_must_on` 各种写法都认得出（含中文数字与区间）；
     B. 认得出之后要真的**进索引**（`build_index` 不丢字段）；
     C. 进了索引之后要真的**出场**（绕过场合/在场两道闸）；
     D. 出场了还**不能被额度挤掉**（必出的排最前）；
     E. 反过来：不是必出日就**不该**出现（必出是"保证出场"不是"限制出场"）；
     F. `to_dict` / `from_dict` 往返不丢。

⚠ 夹具里的名字**一律中性**（「书一 / 店堂」这种）：本判据与
   `tools/verify_generic_project.py` 的 A 组是同一条纪律 ——
   **判据夹具里不许出现某一部真实作品的专名**。

    English:
Verification: **the "must appear" chain** (parse -> index -> select -> render).

★★ This chain guards the real bug fixed on 2026-10-27: the author/model writes a "must appear"
[EN] field in the detail layer, and it **silently never shows up** -- the program runs fine and
[EN] nobody knows that column was dropped. The old Chinese-numeral parser accepted **single
[EN] characters only** ("三" yes, "十五" no), while models and authors typically write "第十五章"
[EN] => entries quietly failed one by one.

[EN] So this criterion checks that "**if the author wrote it, it must be able to appear**", in parts:
[EN] A. `parse_must_on` recognizes every spelling (including Chinese numerals and ranges);
[EN] B. once recognized it must really **enter the index** (`build_index` must not drop the field);
[EN] C. once in the index it must really **appear** (bypassing the scene/presence gates);
[EN] D. and it must **not be squeezed out by the quota** (must-appear entries sort first);
[EN] E. conversely: on a non-must day it **should not** appear (must-appear is "guaranteed",
[EN]     not "restricted to");
[EN] F. `to_dict` / `from_dict` round-trip does not lose it.

⚠ Fixture names are **all neutral** ("书一 / 店堂" and the like): this criterion shares the
[EN] discipline of `tools/verify_generic_project.py` group A -- **no proper noun of one real work
[EN] may appear inside a criterion's fixtures**.
"""
from __future__ import annotations

import json
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
#  A. `parse_must_on`：各种写法都认得出
# [EN] A. `parse_must_on`: every spelling is recognized
# ══════════════════════════════════════════════════════════════════════
def test_parse() -> None:
    from world.layers import parse_must_on

    # ── A1 普通写法 ──
    # [EN] A1 Ordinary spellings
    cases = [
        (3, (3,)), ('3', (3,)), ('3,7', (3, 7)), ('第3天', (3,)),
        ('第3、7章', (3, 7)), ('3 7', (3, 7)), ([3, 7], (3, 7)),
        ('第 3 章', (3,)), ('章节3', (3,)), ('第3章必出', (3,)),
    ]
    bad = [f'{raw!r}→{parse_must_on(raw)}' for raw, want in cases
           if parse_must_on(raw) != want]
    ok('A1 ★ 普通写法都认得出（数字 / 中文 / 顿号 / 空格 / 列表）',
       not bad, '; '.join(bad))

    # ── A2 ★ 中文数字**不止单个字**（这就是那个真 bug）──
    # [EN] A2 ★ Chinese numerals beyond a **single character** (that is the real bug)
    cn = [('第十五章', (15,)), ('十五', (15,)), ('第3到5章', (3, 4, 5)),
          ('3-5', (3, 4, 5)), ('三到五', (3, 4, 5)), ('第十、十五章', (10, 15))]
    bad = [f'{raw!r}→{parse_must_on(raw)}（要 {want}）' for raw, want in cn
           if parse_must_on(raw) != want]
    ok('A2 ★★ 中文数字认「十五」不认「十」，区间要展开（2026-10-27 修的静默丢栏）',
       not bad, '; '.join(bad))

    # ── A3 认不出**一律当没有**（不许猜一个章号）──
    # [EN] A3 Unrecognizable **always means none** (never guess a chapter number)
    none_cases = ['', None, '看不懂', 0, True, -3, '第章']
    bad = [f'{raw!r}→{parse_must_on(raw)}' for raw in none_cases
           if parse_must_on(raw) != ()]
    ok('A3 ★ 认不出一律当没有（猜一个章号会让细节在错误的章里冒出来）',
       not bad, '; '.join(bad))


# ══════════════════════════════════════════════════════════════════════
#  B/C/D/E/F. 索引 → 出场 → 挤不掉 → 不越界 → 往返
# [EN] B/C/D/E/F. index -> appears -> not squeezed out -> no overreach -> round-trip
# ══════════════════════════════════════════════════════════════════════
def test_chain() -> None:
    from world.layers import (SettingItem, build_index, render, select)

    settings = {'detail': [
        {'名称': '缺角的紫砂壶', '内容': '掌柜那只壶，缺了一角。',
         '场合': '书一', '涉及': '掌柜', '必出日': '3'},
        {'名称': '秃了的炭条', '内容': '只写死账的那支。',
         '场合': '书一', '涉及': '阿甲'},
        {'名称': '一双新鞋', '内容': '藏着不穿的那双。',
         '场合': '山路', '涉及': '阿乙', '必出日': '7'},
    ]}
    idx = build_index(settings)

    # ── B. 必出日要真的进索引 ──
    # [EN] B. The must-appear day must really enter the index
    got = {it.name: it.must_on for it in idx}
    ok('B1 ★ `build_index` 不丢「必出日」字段（写了就进索引）',
       got.get('缺角的紫砂壶') == (3,) and got.get('一双新鞋') == (7,), str(got))

    # ── C. 场合/在场都对不上，也必须出来 ──
    # [EN] C. Even when scene and cast both mismatch, it must still appear
    v = select(idx, day=3, scene='完全不相干的地方', people=['一个无关的人'])
    names = [i.name for i in v.get('detail')]
    ok('C1 ★★ 必出日绕过场合/在场两道闸（第 3 天、地方和人全不对，也要出来）',
       '缺角的紫砂壶' in names, str(names))

    # ── D. 必出的排最前（额度挤不掉它）──
    # [EN] D. Must-appear entries sort first (the quota cannot squeeze them out)
    many = {'detail': [
        {'名称': f'杂项{i}', '内容': '一些日常小设定，用来占额度。', '场合': '书一'}
        for i in range(6)
    ] + [{'名称': '必须出现的那条', '内容': '第 3 章一定要有它。', '必出日': '3'}]}
    txt = render(select(build_index(many), day=3, scene='书一', people=['掌柜']))
    ok('D1 ★★ 必出的排最前，额度挤不掉（一堆杂项也压不住它）',
       '必须出现的那条' in txt, txt[:200])

    # ── E. 反过来：不是必出日就不该出现（必出是"保证"，不是"限制"）──
    # [EN] E. Conversely: on a non-must day it should not appear (guarantee, not restriction)
    v3 = select(idx, day=5, scene='完全不相干的地方', people=['一个无关的人'])
    n3 = [i.name for i in v3.get('detail')]
    ok('E1 ★ 非必出日不出现（必出是「保证出场」不是「限制出场」）',
       '缺角的紫砂壶' not in n3, str(n3))

    # ── F. 往返不丢 ──
    # [EN] F. Round-trip does not lose it
    back = SettingItem.from_dict(idx[0].to_dict())
    ok('F1 ★ `to_dict` / `from_dict` 往返不丢「必出日」',
       back is not None and back.must_on == (3,),
       str(back.must_on) if back else 'None')


def main() -> int:
    print('「必出日」这条链 —— 验证', flush=True)
    ok_all = True
    try:
        head('A. `parse_must_on` 各种写法')
        test_parse()
        head('B/C/D/E/F. 索引 → 出场 → 挤不掉 → 不越界 → 往返')
        test_chain()
    except Exception:                                     # noqa: BLE001
        REPORT['fatal'] = traceback.format_exc()
        ok('验证没有中途崩溃（有崩溃就不是全绿）', False, REPORT['fatal'][-300:])
        ok_all = False
    REPORT['checks'] = CHECKS
    return finish(REPORT, out_path=OUT / 'must_on_report.json')


if __name__ == '__main__':
    sys.exit(main())
