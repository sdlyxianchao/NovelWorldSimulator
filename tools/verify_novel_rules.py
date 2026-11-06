# -*- coding: utf-8 -*-
"""判据：**规则表本身没有烂掉**（2026-10-19 第八轮整理）。

背景
----
`crew/novel_rules.py` 把最近几轮"改了什么、为什么这么改、试错过什么"记成了
一张机器可读的表。但**登记表最大的风险是它自己说谎**：

  · 代码搬家了，`landing` 指向的文件没了；
  · 判据改名了（`G13` → `H2`），表里还写着旧的；
  · 反例法删了，表里还宣称"已经验过"；
  · 欠账（有判据、没反例法）一条条加，加到最后"看起来都闭环了"。

所以这张表要配一份**对账**：把表里每一条声明都拿到仓库里核一遍。
这就是本文件。它不判"文笔好不好"，只判"你写下的那张表还算不算数"。

四组
----
A 结构：id 唯一、可数形状不许空、层合法、`checks` 非空则要么有 `mutations`
        要么显式登记 `pending`。
B 对账：`landing` / `evidence` 文件真的在；`checks` 的 ID 真的在那个
        `verify_*.py` 里；`mutations` 的编号真的在那个 `mutate_*.py` 里。
C 欠账：条数 ≤ `PENDING_MAX`，且每一条都写了"为什么还没配"。
D 文档：`developers/docs/小说质量规则.md` 与本表生成的内容**逐字节一致**
        （防止有人手改那份 md，也防止表改了文档没跟上）。

生成文档
--------
    .venv\\Scripts\\python.exe tools\\verify_novel_rules.py --write-doc

[EN] Criterion: **the rule table has not rotted**. `crew/novel_rules.py` records what each round
[EN] of fixes learned. The risk of any registry is that it starts lying: files move, criterion IDs
[EN] get renamed, mutations get deleted, debts accumulate until everything "looks closed". This
[EN] file checks every claim in the table against the repo. It does not judge prose quality, only
[EN] whether the table still holds. Four groups: structure, cross-check, debts, doc sync.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from crew import novel_rules as NR                                # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []
DOC = APP / 'developers' / 'docs' / '小说质量规则.md'


def ok(name: str, cond, detail='') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'   [{detail}]' if detail else ''),
          flush=True)
    return bool(cond)


def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


# ══════════════════════════════════════════════════════════════
#  A  结构
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    rules = NR.RULES
    ok('A0 ★ 读到了规则表（否则下面全是"没数据 ⇒ 绿"）',
       len(rules) >= 15, f'{len(rules)} 条')

    ids = [r.id for r in rules]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    ok('A1 ★★★ id 唯一且形如 `R\\d\\d`', not dup and all(
        re.fullmatch(r'R\d\d', x) for x in ids), f'{len(ids)} 条，重复：{dup or "无"}')

    empty_cnt = [r.id for r in rules if not str(r.countable).strip()]
    ok('A2 ★★★ **每一条都写了"可数形状"**（写不出怎么数的，就不是规则，是感想 —— '
       '本项目反复栽在这上面）', not empty_cnt, f'空：{empty_cnt or "无"}')

    empty_title = [r.id for r in rules if not r.title.strip() or not r.symptom.strip()]
    ok('A3 ★★ 每条都有标题和**现象**（现象必须是用户原话或具体数字）',
       not empty_title, f'空：{empty_title or "无"}')

    bad_layer = [r.id for r in rules if r.layer not in {k for k, _z, _d in NR.LAYERS}]
    ok('A4 ★★ 层级合法（只许 measure / criterion / fixture / mutation / product）',
       not bad_layer, f'非法：{bad_layer or "无"}')

    no_land = [r.id for r in rules if not r.landing and not r.evidence]
    ok('A5 ★★★ 每条至少有一个落点或探针（**只写在文档里的规则没人执行**）',
       not no_land, f'空：{no_land or "无"}')

    # ★★★ 这一条是本文件的核心结构判据
    naked = [r.id for r in rules if r.checks and not r.mutations and not r.pending]
    ok('A6 ★★★ 有判据的必须配反例法，**配不上就在 `pending` 里明写欠账**'
       '（不许假装闭环）', not naked, f'假装闭环：{naked or "无"}')

    # ⚠ 变异编号**三种写法都要收**：`M12`、`P01`（`mutate_mutation_anchors` 用 P 区分
    #   "变异的是反例法自己"）、`⑯`（`mutate_novel_fullness` 用中文圈号）。
    #   原来只认 `M\d+` ⇒ 那份文件里的变异一条都引不了，只能当欠账 ——
    #   而它们**本来就是配好的**，那等于把自己做好的事记成没做。
    # [EN] Mutation markers come in **two styles**: `M12` and the circled numbers (`⑯`) used by
    # [EN] `mutate_novel_fullness`. Accepting only `M\d+` made that file's mutations un-referenceable,
    # [EN] i.e. recording finished work as a debt.
    bad_fmt = []
    for r in rules:
        for c in r.checks:
            if not re.fullmatch(r'verify_[a-z0-9_]+:[A-Z]\d+[a-z]?', c):
                bad_fmt.append(f'{r.id}/checks/{c}')
        for m in r.mutations:
            if not re.fullmatch(r'mutate_[a-z0-9_]+:([MPG]\d+|[①-⑳])', m):
                bad_fmt.append(f'{r.id}/mut/{m}')
    ok('A7 ★★ 引用格式统一（`verify_xxx:ID` / `mutate_xxx:M12`）—— '
       '格式错了 B 组就核不到，会变成"看着有、其实没对账"', not bad_fmt,
       f'{bad_fmt or "无"}')


# ══════════════════════════════════════════════════════════════
#  B  对账（把表里的每一条声明拿到仓库里核）
# ══════════════════════════════════════════════════════════════
def _check_ids(script: str) -> set[str]:
    """某个 `tools/verify_*.py` 里出现过的判据 ID。"""
    # ⚠ 必须同时认 `ok('A1 …')` 与 `ok(f'A1 …')`：带插值的判据名是 f-string，
    #   只匹配单引号会把它们全漏掉 —— 于是"表里引用了真实判据"被判成不存在。
    # [EN] Accept both `ok('A1 …')` and `ok(f'A1 …')`: interpolated names are f-strings, and
    # [EN] matching only plain quotes reports real criteria as missing.
    return set(re.findall(r"ok\(\s*f?'([A-Z]\d+[a-z]?)", _read(f'tools/{script}.py')))


def _has_mutation(script: str, marker: str) -> bool:
    """这个变异编号**真的在那个反例法文件里**吗。

    判法：marker 前后不能粘着字母数字 —— 否则 `M1` 会误配 `M12`、`M2` 会误配 `M20`。
    （这一条要是松了，B4 就成了"文件里随便有个数字就绿"。）
    [EN] Does this mutation marker really exist in that counterexample file? The marker must not be
    [EN] glued to letters or digits, otherwise `M1` would match `M12`.
    """
    return bool(re.search(rf'(?<![A-Za-z0-9]){re.escape(marker)}(?![0-9])',
                          _read(f'developers/{script}.py')))


def group_b() -> None:
    rules = NR.RULES

    miss_land = []
    for r in rules:
        for rel in r.landing:
            if not (APP / rel).exists():
                miss_land.append(f'{r.id}→{rel}')
    ok('B1 ★★★ `landing` 指的代码文件都还在（搬家了要一起改表）',
       not miss_land, f'{miss_land or "全部命中"}')

    miss_ev = []
    for r in rules:
        for rel in r.evidence:
            if not (APP / rel).exists():
                miss_ev.append(f'{r.id}→{rel}')
    ok('B2 ★★ `evidence` 指的探针脚本都还在', not miss_ev, f'{miss_ev or "全部命中"}')

    # ⚠ 判据 ID 必须**真的在那个脚本里**。这一条会随重构自然变红 ——
    #   那正是它存在的意义（不许"表里写着 H2，代码里叫 G13"）。
    # [EN] The criterion ID must really exist in that script. It goes red by itself when things
    # [EN] get renamed -- which is the point: the table must not claim IDs that no longer exist.
    cache: dict[str, set[str]] = {}
    miss_chk = []
    for r in rules:
        for ref in r.checks:
            script, _, cid = ref.partition(':')
            if script not in cache:
                cache[script] = _check_ids(script)
            if cid not in cache[script]:
                miss_chk.append(f'{r.id}→{ref}')
    ok('B3 ★★★ 引用的判据 ID **真的在对应脚本里**（改名/删除要一起改表，'
       '否则表在说谎）', not miss_chk, f'{miss_chk or "全部命中"}')

    miss_mut = []
    for r in rules:
        for ref in r.mutations:
            script, _, mid = ref.partition(':')
            if not _has_mutation(script, mid):
                miss_mut.append(f'{r.id}→{ref}')
    ok('B4 ★★★ 引用的变异编号**真的在对应反例法里**（删了变异还宣称"验过"= 假闭环）',
       not miss_mut, f'{miss_mut or "全部命中"}')

    total_chk = sum(len(r.checks) for r in rules)
    ok('B5 ★ 对账规模（防止"表被清空了所以全绿"）',
       total_chk >= 25 and sum(len(r.mutations) for r in rules) >= 20,
       f'{len(rules)} 条规则 / {total_chk} 处判据引用 / '
       f'{sum(len(r.mutations) for r in rules)} 处变异引用')


# ══════════════════════════════════════════════════════════════
#  C  欠账
# ══════════════════════════════════════════════════════════════
def group_c() -> None:
    pend = NR.pending_rules()
    ok(f'C1 ★★★ 欠账（有判据、没反例法）条数 ≤ {NR.PENDING_MAX} —— '
       '**加一条新的就必须先还一条旧的**',
       len(pend) <= NR.PENDING_MAX,
       f'{len(pend)} 条：{[r.id for r in pend]}')

    no_reason = [r.id for r in pend if '还没配' not in r.note and '没配' not in r.note]
    ok('C2 ★★ 每一条欠账都写清了**为什么还没配**'
       '（空着的欠账会变成永久欠账）', not no_reason, f'{no_reason or "都写了"}')

    ok('C3 ★★★ 欠账不许**同时**宣称有变异（那是自相矛盾）',
       all(not r.mutations for r in pend),
       f'{[(r.id, r.mutations) for r in pend if r.mutations] or "无"}')

    # ⚠ 成对：闭环的那 16 条必须真的两样都有 —— 否则"关门"这条就成了空话。
    # [EN] Paired check: the closed rules must really have both, otherwise "closure" is empty talk.
    closed = [r for r in NR.RULES if r.checks and not r.pending]
    ok('C4 ★★★ 成对：已闭环的每一条都**同时**有判据和反例法',
       closed and all(r.mutations for r in closed),
       f'{len(closed)} 条闭环，缺变异的：'
       f'{[r.id for r in closed if not r.mutations] or "无"}')


# ══════════════════════════════════════════════════════════════
#  D  文档同步
# ══════════════════════════════════════════════════════════════
def render_doc() -> str:
    """把规则表渲染成 markdown。**唯一来源是表**，这份函数不读任何别的文件。"""
    lines: list[str] = []
    ap = lines.append
    ap('# 小说质量规则')
    ap('')
    ap('> ⚠ **本文件由 `tools/verify_novel_rules.py --write-doc` 从 '
       '`crew/novel_rules.py` 生成，不要手改。**')
    ap('> 改规则请改那张表；判据 D 组会逐字节比对，手改会红。')
    ap('')
    ap('这份表是「最近几轮修复到底学到了什么」的唯一登记处。每一条都是被真实产物'
       '打出来、又被反例法验过的东西 —— 不是设计意图，是**踩过的坑的编号**。')
    ap('')
    _closed = len([r for r in NR.RULES if r.checks and not r.pending])
    _pend = len(NR.pending_rules())
    ap(f'共 **{len(NR.RULES)}** 条，分三类：')
    ap('')
    ap(f'- **已闭环 {_closed} 条**：有判据、也有反例法证明判据真会红；')
    if _pend:
        ap(f'- **欠账 {_pend} 条**：有判据、还没配反例法（见文末欠账清单，只许减不许增）；')
    else:
        ap('- **欠账 0 条**：`checks` 有而 `mutations` 空的规则**不存在** —— '
           '这条判据（A6）会当场红；')
    ap(f'- **工艺 {len(NR.RULES) - _closed - _pend} 条**：量测与反例法手法，'
       '**没法写成判据**（"先去量"这件事本身不可自动化），靠人执行。')
    ap('')
    ap('## 怎么用')
    ap('')
    ap('| 你想干什么 | 先看哪一条 |')
    ap('|---|---|')
    ap('| 用户又报"读起来不对" | R01（先量）、R02（字面量判不了语义） |')
    ap('| 想加一条提示词约束 | R04（prompt ≠ 生效）、R12（必须同时给上限）、R23（例子会被抄） |')
    ap('| 写判据 | R05（钉生产路径）、R06（取数源）、R07（别用计数判某处） |')
    ap('| 写夹具 | R08（字段对齐）、R09（走到生效那步）、R10（幅度超阈值） |')
    ap('| 反例法没红 | R14（先怀疑脚本）、R13（锚点换行） |')
    ap('| 两个判据互相打架 | R16（分职责，别回滚） |')
    ap('| 人物说话像散装 | R02、R21（派活）、R22（目标漂移）、R20（态度台阶） |')
    ap('| 时序乱 | R18（材料里没时间）、R19（两类词的台词口径） |')
    ap('| 句子太长或太碎 | R01、R11（门槛按真人分布）、R15（主语切换） |')
    ap('')
    ap('---')
    ap('')
    for key, zh, desc in NR.LAYERS:
        rs = NR.by_layer(key)
        if not rs:
            continue
        ap(f'## {zh} · {desc}')
        ap('')
        ap('| # | 规则 | 落点 |')
        ap('|---|---|---|')
        for r in rs:
            where = '、'.join(f'`{x}`' for x in (r.landing or r.evidence)[:2])
            ap(f'| {r.id} | {r.title} | {where} |')
        ap('')
        for r in rs:
            ap(f'### {r.id} {r.title}')
            ap('')
            ap(f'**现象**　{r.symptom}')
            ap('')
            ap(f'**可数形状**　{r.countable}')
            ap('')
            ap(f'**怎么改**　{r.fix}')
            ap('')
            if r.wrong:
                ap(f'**试过但错的解法**　{r.wrong}')
                ap('')
            if r.landing:
                ap('**落点**　' + '、'.join(f'`{x}`' for x in r.landing))
                ap('')
            if r.evidence:
                ap('**探针**　' + '、'.join(f'`{x}`' for x in r.evidence))
                ap('')
            if r.checks:
                ap('**判据**　' + '、'.join(f'`{x}`' for x in r.checks))
                ap('')
            if r.mutations:
                ap('**反例法**　' + '、'.join(f'`{x}`' for x in r.mutations))
                ap('')
            if r.pending:
                ap('**状态**　⚠ 欠账：有判据、还没配反例法')
                ap('')
            if r.note:
                ap(f'**备注**　{r.note}')
                ap('')
        ap('')
    pend = NR.pending_rules()
    ap('---')
    ap('')
    ap('## 欠账清单')
    ap('')
    if pend:
        ap(f'上限 **{NR.PENDING_MAX}** 条，现 **{len(pend)}** 条。'
           '想加一条新的欠账，先还一条旧的。')
        ap('')
        ap('| # | 规则 | 欠什么 |')
        ap('|---|---|---|')
        for r in pend:
            ap(f'| {r.id} | {r.title} | {r.note or "（没写）"} |')
    else:
        ap('**现在是零欠账。** 2026-10-19 第九轮把原来那六条全还了：')
        ap('')
        ap('| # | 原来欠什么 | 怎么还的 |')
        ap('|---|---|---|')
        for row in (
            ('R06', '判"每幕一行幕头"的取数源，没配变异',
             '`mutate_novel_fullness` ⑯（不写幕头）/ ⑱（时间倒序）'),
            ('R08', '夹具字段没对齐，没配变异',
             '⑰（幕头不写钟点）—— 补上 `time_label` 之后它立刻能红'),
            ('R12', '"给上限"没有变异，且判据本身是假绿',
             '`mutate_prose_flow` M24；顺手把 B3 改成判**真正给出的上限**'),
            ('R18', '"材料里没有时间"没有变异',
             '⑯ / ⑰ / M13（钟点当句首泛滥），三个变异掐三种可能'),
            ('R19', '两类词的台词口径，没配变异',
             'M25 / M26；顺手修掉 J5 的假绿夹具（两句台词没超过配额 2）'),
            ('R23', '"例子会被抄"连判据都没有',
             '新增 A8 / A9 + 改掉方向反了的 C4 + M27'),
        ):
            ap(f'| {row[0]} | {row[1]} | {row[2]} |')
    ap('')
    return '\n'.join(lines) + '\n'


def group_d() -> None:
    want = render_doc()
    have = ''
    if DOC.exists():
        have = DOC.read_text(encoding='utf-8', errors='strict')
    ok('D0 ★★ 文档 `developers/docs/小说质量规则.md` 存在'
       '（没有就 `--write-doc` 生成）', bool(have), str(DOC.relative_to(APP)))
    ok('D1 ★★★ 文档与规则表**逐字节一致**（手改 md 会红；改表不改文档也会红）',
       bool(have) and have == want,
       f'{len(have)} vs {len(want)} 字' if have else '（没有文档）')
    ok('D2 ★★ 文档里**列出全部规则编号**（渲染漏了谁，谁就没人看）',
       all(r.id in want for r in NR.RULES), '')


def main() -> int:
    if '--write-doc' in sys.argv:
        DOC.parent.mkdir(parents=True, exist_ok=True)
        DOC.write_text(render_doc(), encoding='utf-8')
        print(f'已生成 {DOC.relative_to(APP)}（{len(NR.RULES)} 条规则，'
              f'{len(NR.pending_rules())} 条欠账）', flush=True)
        return 0

    print('═' * 62)
    print('  小说质量规则 · 表还算不算数')
    print('═' * 62)
    print('\n【A】结构：可数形状 / 落点 / 闭环声明')
    group_a()
    print('\n【B】对账：表里的每个引用拿到仓库里核')
    group_b()
    print('\n【C】欠账：不许假装闭环')
    group_c()
    print('\n【D】文档：与表逐字节一致')
    group_d()

    bad = [(n, d) for n, c, d in CHECKS if not c]
    print('\n' + '═' * 62)
    print(f'  验证：{len(CHECKS) - len(bad)}/{len(CHECKS)} 条通过'
          + (f'，{len(bad)} 条红' if bad else ''))
    if bad:
        for n, d in bad:
            print('  ✗ ' + n + (f'   [{d}]' if d else ''))
    print('═' * 62)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
