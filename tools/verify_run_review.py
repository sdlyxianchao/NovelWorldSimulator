# -*- coding: utf-8 -*-
"""判据：**推演评估体系真的能评**（`developers/skills/run-review/`）。

用户 2026-10-10 原话：「你看下你是否有一套完整的评估体系 我可以运行一段时间的
推演 然后给你 让你根据推演结果来优化软件 没有的话你做一套 skill 放到
developers\\skills 里并且在 developers\\docs 里说清楚怎么用」。

★ 回答这个问题时要诚实：
  · **代码那一半早就有** —— `tools/run_all_verifications.py`（110 支）+ 反例法。
  · **产物那一半没有** —— 没有任何脚本能从"跑完的一轮存档"里读出
    "哪里不对、该动哪个模块"。这一支判的就是新做的那一半。

覆盖
----
  A. 能跑起来 —— 合成两轮存档，报告与 JSON 都出得来、字段齐
  B. 真的能发现问题 —— 空天 / 缺 `运行小结.md` 必须被报成 S1
  C. **不许假警报** —— 一轮完整且像样的存档，不该有 S1
  D. 三条硬约束 —— **不调模型** / 缺东西就写"缺" / 报告里不打总分
  E. 扫描器自检

跑法：`.venv/Scripts/python.exe tools/verify_run_review.py`
报告：`assets/screenshots/run_review_report.json`

English:
Criterion: **the deduction review system can actually review**
(`developers/skills/run-review/`).
User 2026-10-10 exact words: "Check whether you have a complete review system. I can run
deductions for a while
then give them to you so you optimize the software based on the deduction results. If not, make
a skill and put it in
developers\\skills and explain clearly in developers\\docs how to use it".
★ Be honest when answering this question:
  · **The code half has long existed** —— `tools/run_all_verifications.py` (110 checks) + counterexample method.
  · **The artifact half does not exist** —— no script can read from "a completed round of archive"
    "what is wrong, which module should be changed". This check judges exactly that newly made half.
Coverage
----
  A. Can run —— synthesize two rounds of archives, both report and JSON come out, fields complete
  B. Can actually find problems —— empty sky / missing `运行小结.md` must be reported as S1
  C. **No false alarms allowed** —— a complete and decent round of archive should have no S1
  D. Three hard constraints —— **no model calls** / when something is missing write "missing" / no total score in the report
  E. Scanner self-check
How to run: `.venv/Scripts/python.exe tools/verify_run_review.py`
Report: `assets/screenshots/run_review_report.json`
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

SCRIPT = APP / 'developers' / 'skills' / 'run-review' / 'scripts' / 'review_run.py'
REPORT: dict = {'checks': [], 'notes': []}

#: 一段"像人写的"正文：句长有起伏、有对白、用词不重复
# [EN] : A passage of "human-like" prose: varied sentence length, dialogue, no repeated wording
GOOD = (
    '掌柜把灯挑亮了些。「这账，前儿个就对不上了。」\n\n'
    '他说这话时没看她。院外的雨还在下，檐角滴水，一声，又一声。'
    '门槛上的水印深了一寸。\n\n'
    '「进来罢。」她没回头。那人还是站着，像一个等了很久的人。\n\n'
    '灯芯爆了一下。案上的帐簿翻到第七页，字迹是别人的。\n'
)


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    return bool(cond)


def code_only(block: str) -> str:
    return '\n'.join(ln for ln in block.splitlines()
                     if not ln.strip().startswith('#'))


def _mk_run(root: Path, name: str, days: list[int], *, full: bool = True,
            empty_days: list[int] | None = None) -> Path:
    d = root / name
    (d / '每天的生活' / '原文').mkdir(parents=True)
    for sub in ('导出', '故事文档', '关键事件', '本地设定集'):
        (d / sub).mkdir(parents=True)
    (d / '任务介绍.md').write_text('# 任务介绍\n\n- **项目**：验证书\n',
                                  encoding='utf-8')
    if full:
        (d / '运行小结.md').write_text('# 运行小结\n\n演完了。\n', encoding='utf-8')
    for day in days:
        body = '' if (empty_days and day in empty_days) else GOOD
        (d / '每天的生活' / f'第{day:03d}天.md').write_text(
            f'# 第 {day} 天 · 第{day}天·辰时 · 晴\n\n## 辰时 08:00\n\n'
            + (body or '（空）\n'), encoding='utf-8')
        if body:
            (d / '每天的生活' / '原文' / f'第{day:03d}天.md').write_text(
                body, encoding='utf-8')
        (d / '每天的生活' / f'第{day:03d}天.json').write_text(json.dumps(
            [{'time_label': '辰时 08:00', 'place': '临河茶肆',
              'cast': ['掌柜', '阿九']},
             {'time_label': '酉时 18:00', 'place': '后院', 'cast': ['掌柜']}],
            ensure_ascii=False), encoding='utf-8')
    sqlite3.connect(d / 'state.db').close()
    return d


def _run(target: Path, out: Path) -> tuple[int, dict, str]:
    import subprocess
    r = subprocess.run([sys.executable, str(SCRIPT), str(target),
                        '--out', str(out)],
                       cwd=str(APP), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=300)
    md = ''
    js: dict = {}
    mds = sorted(out.glob('推演评估_*.md'))
    jss = sorted(out.glob('推演评估_*.json'))
    if mds:
        md = mds[-1].read_text(encoding='utf-8')
    if jss:
        js = json.loads(jss[-1].read_text(encoding='utf-8'))
    return r.returncode, js, md


def test_works() -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_rv_'))
    proj = tmp / '验证书'
    _mk_run(proj, '第1次模拟2026-10-10-10-00', [1, 2, 3])
    _mk_run(proj, '第2次模拟2026-10-10-11-00', [4], full=False, empty_days=[4])
    out = tmp / 'out'
    code, js, md = _run(proj, out)
    REPORT['notes'].append(f'脚本退出码 {code}')
    ok('A1 ★★★ 评估脚本跑得起来，报告与 JSON 都生成了',
       code == 0 and bool(md) and bool(js), f'md={len(md)} 字 / json={bool(js)}')
    runs = js.get('runs') or []
    ok('A1b ★★ 两轮都评到了', len(runs) == 2, f'{len(runs)} 轮')
    if runs:
        need = {'run', '天数', '故事时间', '每日', '文风指标', '去AI味',
                '产物', '场景与人物', '嫌疑清单'}
        miss = sorted(need - set(runs[0]))
        ok('A1c ★★ 每轮的 JSON 字段齐（下一轮优化直接读它）', not miss, str(miss))
        REPORT['runs'] = [{k: r.get(k) for k in ('run', '天数', '故事时间')}
                          for r in runs]
        REPORT['run_keys'] = sorted(set().union(*(set(r) for r in runs)))


def test_finds_problems() -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_rv2_'))
    proj = tmp / '验证书'
    _mk_run(proj, '第1次模拟2026-10-10-12-00', [1], full=False, empty_days=[1])
    _out = tmp / 'out'
    _code, js, md = _run(proj, _out)
    r = (js.get('runs') or [{}])[0]
    items = r.get('嫌疑清单') or []
    texts = ' '.join(f'{x["what"]} {x["why"]}' for x in items)

    ok('B1 ★★★ **缺「运行小结.md」**被报出来（那是"这一轮没正常收工"的信号）',
       '运行小结' in texts, texts[:120])
    ok('B2 ★★★ **空天**被报成 S1（一天几乎没有字，等于白跑）',
       any(x['level'] == 'S1' and '空' in x['what'] for x in items),
       str([x['what'] for x in items][:5]))
    ok('B3 ★★ 每条都带**去哪查**（没有"去找找看"这种废话）',
       all(x.get('where') for x in items), str(items[:1]))
    ok('B4 ★★ 报告正文里也印了嫌疑清单（给人看的那一份）',
       '嫌疑清单' in md and 'S1' in md, '')


def test_no_false_alarm() -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_rv3_'))
    proj = tmp / '验证书'
    _mk_run(proj, '第1次模拟2026-10-10-13-00', [1, 2, 3, 4, 5, 6])
    _out = tmp / 'out'
    _code, js, _md = _run(proj, _out)
    r = (js.get('runs') or [{}])[0]
    s1 = [x['what'] for x in (r.get('嫌疑清单') or []) if x['level'] == 'S1']
    ok('C1 ★★★ 一轮**完整**的存档不该报 S1（**报告一响就没人看**：'
       '假警报是评估体系最常见的死法）',
       not s1, str(s1))


def test_hard_rules() -> None:
    src = SCRIPT.read_text(encoding='utf-8')
    body = code_only(src)
    ok('D1 ★★★ **一次模型调用都没有**（用户点名："这些信息不使用 LLM 动态生成的"）'
       '—— 源码里不许出现调用模型的入口',
       not re.search(r'\b(ask|chat|complete)\s*\(', body)
       and 'from llm.replies' not in body and 'llm.router' not in body,
       '')
    ok('D2 ★★ 缺东西**如实写"缺"**，不拿 0 或估算值填（`present` 里就是布尔）',
       "L.append(f'| `{k}` | {\"✓\" if v else \"**缺**\"} |')" in src, '')
    # ⚠ 判**产出物里有没有那个字段**，不判"源码里有没有这几个字" ——
    #   这个脚本的模块说明里就写着"不打总分"，全文搜会撞上自己的注释（假红）。
    # [EN] ⚠ Judge **whether that field is in the artifact**, not whether "those characters are in the
    # [EN] source code" ——
    # [EN] This script's module docstring literally says "no total score", a full-text search will hit its
    # [EN] own comment (false red).
    keys = REPORT.get('run_keys') or []
    ok('D3 ★★ 报告里**不打总分** —— 一个标量总分会让"四处轻微越界"压过'
       '"一处严重越界"，本项目为此吃过亏。这里只给分级的嫌疑清单'
       '（判的是 JSON 里的字段，不是源码里的字）',
       bool(keys) and not [k for k in keys
                           if k in ('总分', '得分', '分数') or 'score' in k.lower()],
       str(keys))
    ok('D4 ★★ 分级只有 S1/S2/S3 三档（不是 1~10 分那种），'
       '每条必带 `where`（去哪查）',
       all(f"'{lv}'" in src for lv in ('S1', 'S2', 'S3'))
       and 'where: str' in src, '')
    ok('D5 ★★ 成本缺账只在"**同一本书别的轮有账**"时才报 —— '
       '否则每一轮都会多一条"没有成本记录"，把用户练成不看这一栏',
       'cost_scope_has_records' in body, '')


def test_scanner() -> None:
    ok('E1 ★★ 判据自己找得到脚本（路径写错的话上面全是假绿）',
       SCRIPT.is_file(), str(SCRIPT))
    r = REPORT['runs'][0] if REPORT.get('runs') else {}
    ok('E1b ★★ 而脚本确实读到了东西（`天数` 不是 0）', r.get('天数', 0) > 0,
       str(r))


def main() -> int:
    for name, fn in (('能跑起来', test_works), ('能发现问题', test_finds_problems),
                     ('不假警报', test_no_false_alarm), ('硬约束', test_hard_rules),
                     ('扫描器自检', test_scanner)):
        try:
            fn()
        except Exception:                                       # noqa: BLE001
            REPORT['checks'].append({'name': f'{name} 组崩了', 'ok': False,
                                     'detail': traceback.format_exc()[-900:]})
    out = APP / 'assets' / 'screenshots' / 'run_review_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n推演评估体系验证：{n - len(bad)}/{n}')
    for c in REPORT['checks']:
        print(f'  {"✓" if c["ok"] else "✗"} {c["name"]}'
              + (f' | {c["detail"][:130]}' if c['detail'] else ''))
    print('报告 ->', out.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
