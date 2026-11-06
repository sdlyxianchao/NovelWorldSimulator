"""bench 与产品侧**口径对账**：两处实现，同一个定义。

★ 为什么需要这一份
    `novel_bench/` 刻意独立于主程序（不 import `crew/`），所以指标只能各写一份。
    但"同一件事两处实现"是万恶之源 —— 两边一旦漂开，bench 说"变好了"、
    产品侧判据说"更差了"，永远吵不完。
    ⇒ 这里不合并实现（独立性是有意的），而是**自动对账**：
      在同一批文本上跑两边的函数，数字不一致就红。

★ 什么时候会用到它
    任何一边改了阈值、改了切句方式、改了类别词表 —— 跑一次就知道有没有漂。

用法：
    ./.venv/Scripts/python.exe tools/verify_bench_parity.py
"""
from __future__ import annotations

import io
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from crew import prose_flow as PF                            # noqa: E402
from novel_bench.bench import metrics as BM                  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = '') -> None:
    CHECKS.append((name, bool(cond), detail))
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'   [{detail}]' if detail else ''),
          flush=True)


def corpus() -> list[tuple[str, str]]:
    """对账用的文本：真人 18 章 + 各版真跑（覆盖"干净"和"有病"两种）。"""
    out: list[tuple[str, str]] = []
    base = APP / 'samples' / 'zh'
    for d in sorted(base.iterdir()):
        body = d / '正文'
        if not (d.is_dir() and body.exists()):
            continue
        for f in sorted(body.glob('*.md')):
            out.append((f'human/{f.stem}', io.open(f, encoding='utf-8').read()))
    runs = APP / 'novel_bench' / 'results'
    for rid in ('snow_v18', 'snow_v19', 'snow_v20', 'snow_v21', 'snow_v22',
                'snow_v23', 'snow_v24'):
        p = runs / rid / 'cases' / 'ykg-01' / 'novel.md'
        if p.exists():
            out.append((rid, io.open(p, encoding='utf-8').read()))
    return out


def main() -> int:
    print('\n── 阈值常量 ──', flush=True)
    pairs = (('道具循环阈值', PF.PROP_CYCLE_MIN, BM.PROP_CYCLE_MIN),
             ('太碎阈值（逗号/句）', PF.FLAT_CLAUSE_RATIO, BM.FLAT_CLAUSE_RATIO),
             ('长句下限', PF.LONG_MIN, BM.LONG_MIN),
             ('超长句上限', PF.SENTENCE_MAX, BM.SENTENCE_MAX),
             ('段落最少句数', PF.RUN_MIN, BM.RUN_MIN),
             ('段落最少字数', PF.SPAN_MIN_CHARS, BM.SPAN_MIN_CHARS))
    for name, a, b in pairs:
        ok(f'P1 {name}：产品侧 {a} == bench {b}', a == b, f'{a} vs {b}')

    print('\n── 类别词表 ──', flush=True)
    ok('P2 器皿词表一致（同一件东西才不会一边认一边不认）',
       tuple(PF._PROP_VESSEL) == tuple(BM.PROP_VESSEL),
       f'{len(PF._PROP_VESSEL)} vs {len(BM.PROP_VESSEL)}')
    ok('P3 可消耗物词表一致', tuple(PF._PROP_STUFF) == tuple(BM.PROP_STUFF),
       f'{len(PF._PROP_STUFF)} vs {len(BM.PROP_STUFF)}')

    print('\n── 逐篇对账（真人 18 章 + 7 版真跑）──', flush=True)
    texts = corpus()
    bad_prop: list[str] = []
    bad_flat: list[str] = []
    bad_long: list[str] = []
    for name, t in texts:
        p_prop = max([x['n'] for x in PF.prop_cycle_issues(t)] or [0])
        b_prop, _who = BM.prop_cycle_max(t)
        # ⚠ 产品侧只报"≥阈值"的，bench 报**原始最大值** —— 两者语义不同，不能直接相等。
        #   对账口径：产品侧有报 ⇒ bench 必须也 ≥ 阈值；产品侧没报 ⇒ bench 必须 < 阈值。
        # [EN] The product reports only cases at/above the threshold while bench reports the
        # [EN] raw maximum, so compare **"是否有病"**, not the numbers directly.
        if (p_prop > 0) != (b_prop >= BM.PROP_CYCLE_MIN):
            bad_prop.append(f'{name}(产品{p_prop}/bench{b_prop})')
        p_flat = len(PF.flat_span_issues(t))
        b_flat = BM.flat_span_count(t)
        if p_flat != b_flat:
            bad_flat.append(f'{name}({p_flat}/{b_flat})')
        p_long = len(PF.long_span_issues(t))
        b_long = BM.long_span_count(t)
        if p_long != b_long:
            bad_long.append(f'{name}({p_long}/{b_long})')
    ok('P4 「道具循环」判病结论一致（产品侧报了 ⟺ bench ≥ 阈值）',
       not bad_prop, '、'.join(bad_prop[:4]))
    ok('P5 「太碎」段数逐篇相等', not bad_flat, '、'.join(bad_flat[:4]))
    ok('P6 「太长」段数逐篇相等', not bad_long, '、'.join(bad_long[:4]))

    print('\n── 安全侧：真人身上必须零命中 ──', flush=True)
    hum = [(n, t) for n, t in texts if n.startswith('human/')]
    ok('P7 真人 18 章：太碎段 = **0**（这条判据不许杀真人）',
       all(BM.flat_span_count(t) == 0 for _n, t in hum),
       f'{len(hum)} 篇')
    ok('P8 真人 18 章：道具循环判病 = **0**',
       all(BM.prop_cycle_max(t)[0] < BM.PROP_CYCLE_MIN for _n, t in hum), '')
    ok('P9 真人 18 章：引号**不算混用**（真人全部用 ASCII 引号，那是正常写法）',
       all(not (BM.quote_mixed(t)[0] and BM.quote_mixed(t)[1]) for _n, t in hum),
       '这条差点写成"英文引号即病"')
    ok('P10 真人 18 章：`normalize_quotes` **一个字符都不动**',
       all(PF.normalize_quotes(t) == t for _n, t in hum), '')

    print('\n── 引号口径 ──', flush=True)

    def _mixed(t: str) -> bool:
        """混用 = **两种都有**。⚠ 不能写 `any(quote_mixed(t))` ——
        返回的是 `(ascii_n, zh_n)`，`any((1, 0))` 因为 1 是真值就返回 True，
        「单一 ASCII」也会被判成混用（第一版就是这么红的）。"""
        a, b = BM.quote_mixed(t)
        return bool(a and b)

    ok('P11 单一 ASCII（真人同款）⇒ 不判混用、也不改',
       (not _mixed('他说"走。"她说"嗯。"'))
       and PF.normalize_quotes('他说"走。"') == '他说"走。"', '')
    ok('P12 混用 ⇒ 判混用，且 `normalize_quotes` 统一成中文',
       _mixed('他说"走。"她说“嗯。”')
       and PF.normalize_quotes('他说"走。"她说“嗯。”') == '他说“走。”她说“嗯。”', '')
    ok('P13 单一中文 ⇒ 不判混用、不改',
       (not _mixed('他说“走。”'))
       and PF.normalize_quotes('他说“走。”') == '他说“走。”', '')

    bad = [c for c in CHECKS if not c[1]]
    print(f'\nbench ↔ 产品侧 口径对账：{len(CHECKS) - len(bad)}/{len(CHECKS)}', flush=True)
    for n, _c, _d in bad:
        print(f'  ✗ {n}', flush=True)
    return 0 if not bad else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:                                            # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
