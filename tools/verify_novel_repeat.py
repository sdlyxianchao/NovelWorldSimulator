# -*- coding: utf-8 -*-
"""验证：**装订稿里的「复读机」被折叠**（用户 2026-10-16，「生成的小说不像人话」）。

用户原话
--------
「生成的小说不像人话啊」
「小说原文更好，后续导出的这个不好」

根因
----
`小说原文_v1.md`（作家样章）写得好；坏的是 `小说版本_v1.md`（装订稿），它来自
「每天的生活」里演员**反复念同一句口头禅**的现场（"俺某地哩"×7、"傻子账上不糊涂"×8、
"井茶入梦"×6、"先看看"×6、"楼欠因果"×4…）。`crew/agents.REPEAT_RULES` 只管
作家提示词，落不到这条确定性装订链；`_said` 护栏只认逐字重复，漏"近重复"。

修复：在导出装订链 `export/novel_version._fold_repeats` 里，把同一角色在滑动窗口内
反复念同一句（或只换几个字）的口头禅折叠成一句。属可读性正确性，不另设开关。

这一支钉住的行为（**每条都要能红**，见 `developers/mutate_novel_repeat.py`）：

  A **坏样本被折叠**：用户导出的真实坏段落（伙计丁 俺某地哩 ×7 等）→ 折叠后
     领衔口头禅各只剩 1 次，且第一句原话保留（不被误删）。
  B **好样本不过折**：每人每口头禅只说一次的正文，折叠后一字不差。
  C **幂等**：折两遍 == 折一遍（不残留、不二次误删）。
  D **不误伤无引号正文**：没引号的叙述原样返回。
  E **接线钉死**：`render_manuscript` 在 `MODE_NOVEL` 分支里真的调了 `_fold_repeats`
     （`小说原文`/逐字模式不走这里）。

跑法：.venv\\Scripts\\python.exe tools/verify_novel_repeat.py
产出：assets/screenshots/novel_repeat_report.json

English:
Verification: **the "repeat machine" in the bound volume is folded** (user 2026-10-16,
"the generated novel doesn't sound human").
User's exact words
--------
"The generated novel doesn't sound human."
"The original-text version is better; the later exported one is not."
Root cause
----
`小说原文_v1.md` (the writer's sample chapter) is good; the bad one is `小说版本_v1.md`
(the bound volume), which comes from the live show where actors **repeat the same catchphrase**
("俺某地哩"×7, "傻子账上不糊涂"×8, "井茶入梦"×6, "先看看"×6, "楼欠因果"×4…).
`crew/agents.REPEAT_RULES` only governs the writer's prompt and never reaches this deterministic
binding chain; the `_said` guardrail only recognizes verbatim repeats and misses "near-duplicates".
Fix: in the export binding chain `export/novel_version._fold_repeats`, fold a character's
catchphrase repeated within the sliding window (or with only a few chars changed) down to one.
Readability-correctness, no separate switch.
Behaviors pinned by this branch (**every one must be able to go red**, see
`developers/mutate_novel_repeat.py`):
  A **bad sample folded**: the user's real bad excerpt (伙计丁 俺某地哩 ×7 etc.) → after folding
     each lead catchphrase remains only once, and the first line is preserved (not wrongly deleted).
  B **good sample not over-folded**: a body where each character says each catchphrase only once
     is unchanged after folding.
  C **idempotent**: fold twice == fold once.
  D **does not hurt quote-less prose**: prose without quotes is returned as-is.
  E **wiring pinned**: `render_manuscript` really calls `_fold_repeats` in the `MODE_NOVEL` branch
     (`小说原文` / verbatim mode does not go through it).
Run: .venv\\Scripts\\python.exe tools/verify_novel_repeat.py
Output: assets/screenshots/novel_repeat_report.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from export.novel_version import _fold_repeats               # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ── 真实坏样本：用户导出的那段（伙计丁 俺某地哩 ×7 等） ──────────────
# [EN] Real bad sample: the user's exported passage (伙计丁 俺某地哩 ×7 etc.)
BAD = (
    '客人乙在临街楼屋里，靠着柜台。伙计丁就在门边嚷，拍着手："俺某地哩！俺要去洗脸换衣裳！"'
    '丁在柜后拨算盘，头也不抬："傻子账上不糊涂，你洗脸我记账。"'
    '这时候门影里立着个白衣女人，声气轻得像怕惊了什么："井茶入梦，白衣未改。"'
    '她顿了顿，"井茶入梦，楼欠因果未销。"\n\n'
    '客人乙脑子里忽然刺了一下。他张嘴，话比念头快："那……楼欠因果未销，我记得。"'
    '他以为自己啥都忘了，声出口自己先愣了。\n\n'
    '先生丙不知几时倚在条案边，指节敲着账页："先看看，不急，楼里因果你自己定。"'
    '丁搁笔："傻子账上不糊涂，楼欠因果早记着了。"白衣女人又念："井茶入梦，白衣在边界醒。"'
    '丁接："茶钱记着，傻子账上不糊涂。"先生丙说："先看看，今日事慢慢理。"'
    '丁重复："傻子账上不糊涂，这临街楼先看看。"\n\n'
    '伙计丁还在原地跳："俺某地哩！俺没换衣哩！"掌柜掌柜甲从里间出来，只吐一字："坐。"'
    '伙计丁没坐。先生丙翻页："先看看账页，不急。"伙计丁扭头："俺某地哩！我不看账，俺换衣裳！"'
    '客人乙瞧着他，忽然开口："我记得。换衣裳，这个我懂。"丁哼了声："傻子账上不糊涂，换衣裳账照记。"'
    '白衣女人声低了些："白衣染尘，井茶忆前因。"丁说："傻子账上不糊涂，临街楼的账跑不了。"'
    '白衣女人："井茶入梦，楼欠因果未还。"\n\n'
    '伙计丁往门外跑："俺某地哩！俺换衣裳去！"先生丙没拦："先看看旧账，不急。"'
    '丁拉凳："坐了，傻子账上不糊涂。"白衣女人望向窗外，院里那口井的凉意好像渗进来：'
    '"井茶冷透，楼欠的梦不肯醒。"先生丙说："先看看账，不急。"客人乙跟着念："先看看账……我记得。"'
    '丁点头："傻子账上不糊涂，先看看。"白衣女人："灯圈痕里，井茶入梦。"\n\n'
    '伙计丁又探回脑袋："俺某地哩！那我也要看！"客人乙说："先看看。我记得，行吧。"'
    '先生丙指尖点着残账："不急 先看看残账。"伙计丁摆手："俺某地哩！俺要换衣去！"'
    '丁："傻子账上不糊涂，残账跑不了。"白衣女人两句连来："记忆随井茶入梦，楼欠白衣因果。"'
    '"白衣裳沾了井边的梦。"伙计丁不坐了："俺某地哩！我不坐，俺去洗漱换衣裳！"'
    '先生丙最后说："不急，先看看残账。"\n\n'
    '客人乙没再接话。他盯着柜上残账，心里那个"记得"像院里井水映的月，晃着，抓不住。'
)


# ── A —— 坏样本被折叠（领衔口头禅各剩 1 次，第一句原话保留） ──────────
# [EN] A -- bad sample folded (each lead catchphrase remains once; first line preserved)
def test_bad_folded() -> None:
    folded = _fold_repeats(BAD)
    # ★ 真做了折叠（不是空转）
    # [EN] ★ actually folded (not a no-op)
    ok('A0 ★ 折叠确实发生了（台词数减少）',
       len(folded) < len(BAD), f'{len(BAD)}→{len(folded)} 字符')
    # 领衔口头禅各只剩 1 次
    # [EN] each lead catchphrase remains only once
    ok('A1 ★ 俺某地哩 从 7 次折到正好 1 次（第一句保留）',
       BAD.count('俺某地哩') == 7 and folded.count('俺某地哩') == 1,
       f'{BAD.count("俺某地哩")}→{folded.count("俺某地哩")}')
    ok('A2 ★ 楼欠因果 从 4 次折到 ≤1 次',
       BAD.count('楼欠因果') == 4 and folded.count('楼欠因果') <= 1,
       f'{BAD.count("楼欠因果")}→{folded.count("楼欠因果")}')
    ok('A3 井茶入梦 / 先看看 明显减少（不再刷屏）',
       folded.count('井茶入梦') < BAD.count('井茶入梦')
       and folded.count('先看看') < BAD.count('先看看'),
       f'井茶入梦 {BAD.count("井茶入梦")}→{folded.count("井茶入梦")}；'
       f'先看看 {BAD.count("先看看")}→{folded.count("先看看")}')
    # 第一句原话没有被误删（不是把整段清空）
    # [EN] the first line's actual words were not wrongly deleted (not blanked)
    ok('A4 第一句原话保留（"俺某地哩！俺要去洗脸换衣裳！"仍在）',
       '俺某地哩！俺要去洗脸换衣裳！' in folded, '')
    # 没留下悬空的「说话人＋冒号」残桩
    # [EN] no dangling "speaker + colon" stubs left behind
    ok('A5 无悬空归因残桩（不含 "她顿了顿" 孤立片段）',
       '她顿了顿' not in folded, '')


# ── B —— 好样本不过折（每人每口头禅只说一次的正文一字不差） ──────────
# [EN] B -- good sample not over-folded (a body where each catchphrase appears once is unchanged)
def test_good_preserved() -> None:
    good = ('伙计丁拍手："俺某地哩！俺要去洗脸换衣裳！"'
            '丁拨算盘："傻子账上不糊涂，你洗脸我记账。"'
            '白衣女人轻声："井茶入梦，白衣未改。"'
            '先生丙翻页："先看看，不急，楼里因果你自己定。"')
    out = _fold_repeats(good)
    ok('B1 ★ 好样本折叠后一字不差（不过折、不误删）',
       out == good, f'原 {len(good)} 字 / 折叠 {len(out)} 字')


# ── C —— 幂等（折两遍 == 折一遍） ───────────────────────────────────
# [EN] C -- idempotent (fold twice == fold once)
def test_idempotent() -> None:
    once = _fold_repeats(BAD)
    twice = _fold_repeats(once)
    ok('C1 ★ 幂等：折两遍 == 折一遍', twice == once,
       f'一遍 {len(once)} 字 / 两遍 {len(twice)} 字')


# ── D —— 不误伤无引号正文 ─────────────────────────────────────────
# [EN] D -- does not hurt quote-less prose
def test_no_quote_untouched() -> None:
    prose = '客人乙靠着柜台。丁拨算盘。白衣女人立在门影里。'
    ok('D1 无引号叙述原样返回', _fold_repeats(prose) == prose, '')
    ok('D2 空串不报错', _fold_repeats('') == '', '')


# ── E —— 接线钉死（render_manuscript 在 MODE_NOVEL 分支调了 _fold_repeats） ─
# [EN] E -- wiring pinned (render_manuscript calls _fold_repeats in the MODE_NOVEL branch)
def test_wiring() -> None:
    src = (APP_DIR / 'export' / 'novel_version.py').read_text(encoding='utf-8')
    ok('E1 ★ render_manuscript 在 MODE_NOVEL 分支里调了 _fold_repeats',
       'if mode == MODE_NOVEL:' in src and '_fold_repeats(body)' in src, '')
    ok('E2 ★ 折叠函数确实定义在导出模块里',
       'def _fold_repeats(text: str) -> str:' in src, '')


def main() -> int:
    print('═' * 62)
    print('  验证：装订稿里的「复读机」被折叠（2026-10-16）')
    print('═' * 62)
    try:
        print('\n【A】坏样本被折叠')
        test_bad_folded()
        print('\n【B】好样本不过折')
        test_good_preserved()
        print('\n【C】幂等')
        test_idempotent()
        print('\n【D】不误伤无引号正文')
        test_no_quote_untouched()
        print('\n【E】接线钉死')
        test_wiring()
    except Exception:                                            # noqa: BLE001
        import traceback
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'novel_repeat_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  复读机折叠验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
