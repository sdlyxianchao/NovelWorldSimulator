# -*- coding: utf-8 -*-
"""判据：**反例法自己的锚点还打不打得中**（2026-10-19 第十轮）。

为什么需要它
------------
用户的原话：「`mutate_novel_fullness.py` 之前是坏死的……这类'反例法自己坏了'
不会有人发现，只有真去跑才暴露。」

这句话是对的，而且比它说的更严重。反例法的工作方式是
`assert src.count(旧串) == 1` 然后 `replace`：

  · 锚点还在 ⇒ 变异生效 ⇒ 判据变红 ⇒ 这条反例法**有用**；
  · 锚点被搬走/重写 ⇒ `count == 0` ⇒ **变异什么都没做** ⇒ 判据当然还是绿的
    ⇒ 人看到的是"没红"，只会以为判据太弱，**回头去加强判据**。
    ⇒ 真正的病（反例法失效）被伪装成"判据不够严"，永远不会被找到。

实测：597 条可静态核对的锚点里 **56 条已经打死（9.4%）**。而 128 个反例法脚本里
只有 65 个带锚点自检，其余 63 个**连"锚点没命中就停"这一步都没有** ——
它们会静默地把"什么都没做"当成"变异没让判据变红"。

判什么
------
A 覆盖：能静态核对的锚点有多少条、核对不了的多少条（不许靠"扫不到"蒙混）。
B 基线外：**清单以外的锚点必须全部命中**（这一条抓的是"以后谁重构搬走了锚点"）。
C 基线内：清单里的失效条目**只许减不许增**；已经修好的必须从清单删掉
        （否则清单会变成永久垃圾池，谁也不会回去看）。
D 基线本身：格式合法、条目在文件里真的还存在（防止清单里全是过期条目）。

基线文件：`developers/_anchor_baseline.txt`
生成/更新：

    .venv\\Scripts\\python.exe tools\\verify_mutation_anchors.py --write-baseline

⚠ **只能往里删，不能往里加。** 要加一条，先修掉一条 —— 与规则表欠账同一条纪律。

[EN] Criterion: **do the counterexamples' own anchors still hit?** A counterexample works by
[EN] `assert src.count(old) == 1` then replace. If the anchor was moved or rewritten, `count == 0`,
[EN] the mutation does **nothing**, and the criterion stays green -- so the symptom looks like
[EN] "the criterion is too weak" and people go strengthen the criterion instead. The real illness
[EN] (a dead counterexample) disguises itself as a weak check and is never found. Measured: 56 of
[EN] 597 statically checkable anchors are already dead (9.4%), and 63 of 128 counterexample scripts
[EN] have no anchor self-check at all. Groups: coverage, anchors outside the baseline must hit,
[EN] baseline entries may only decrease (a repaired one must be deleted from the list), and the
[EN] baseline itself must stay valid.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
DEV = APP / 'developers'
BASELINE = DEV / '_anchor_baseline.txt'

#: 哪些模块级变量算"变异列表"。
# ⚠ `KNIVES` 是 2026-10-27 加的：站表链与提取配额那两支反例法用的是这个名字，
#   而**更早就有的 `mutate_extract_window.py` 也用它** —— 没登记 ⇒ 那 13 条锚点
#   从来没被这道自检核过（"刀表换了个名字就整组消失"，与"页面没登记"同一个坑）。
# [EN] `KNIVES` added 2026-10-27: the station-chain and extraction-quota mutation scripts use that
# name, and **the older `mutate_extract_window.py` uses it too** -- unregistered meant its 13
# anchors were never checked (a knife table vanishing because it was renamed: the same trap as an
# unregistered page).
LIST_NAMES = ('MUT', 'MUTS', 'MUTATIONS', 'CASES', 'SUB', 'SUITES', 'KNIVES')

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond, detail='') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'   [{detail}]' if detail else ''),
          flush=True)
    return bool(cond)


def const_str(n: ast.AST) -> str | None:
    """纯字面量字符串（含 `'a' + 'b'` 拼接）的取值；动态拼的返回 None。"""
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        a, b = const_str(n.left), const_str(n.right)
        return a + b if a is not None and b is not None else None
    return None


def looks_path(s: str | None) -> bool:
    if not s or len(s) > 120 or '\n' in s:
        return False
    low = s.lower()
    return (any(low.endswith(x) for x in ('.py', '.md', '.txt', '.json', '.yaml', '.yml'))
            or ('/' in s and all(ord(c) < 128 for c in s)))


def scan() -> tuple[list[tuple[str, str, str, str]], int, list[str], list[str]]:
    """扫全部反例法。

    返回 `(失效清单, 命中的条数, 无法核对的说明, 语法错误的脚本)`。
    失效清单元素：`(脚本名, 键, 相对路径, 原因)`，键形如 `MUT[4]`。

    ⚠ **命中的条数必须一起返回**：第一版只返回失效，于是"可核对多少条"
      算成 `失效 + 摘不出` —— 活的一条都没算进去，实测显示"可核对 56 条"，
      而真实是 541 条（覆盖率判据当场假红，还把人往错的方向推）。
    [EN] Return the hit count too: the first version returned only failures, so "how many were
    [EN] checked" came out as `failures + unparseable` -- zero live ones counted, reported as 56
    [EN] while the truth was 541 (the coverage criterion went false red and pointed the wrong way).
    """
    stale: list[tuple[str, str, str, str]] = []
    alive = 0
    unknown: list[str] = []
    broken: list[str] = []
    for p in sorted(DEV.glob('mutate_*.py')):
        if p.name in ('repair_anchors.py',):
            continue
        try:
            mod = ast.parse(p.read_text(encoding='utf-8'))
        except SyntaxError as e:
            broken.append(f'{p.name}:{e.lineno}')
            continue
        for n in mod.body:
            if not isinstance(n, (ast.Assign, ast.AnnAssign)):
                continue
            v = n.value
            tgt = n.targets[0] if isinstance(n, ast.Assign) else n.target
            if not (isinstance(v, (ast.List, ast.Tuple)) and isinstance(tgt, ast.Name)):
                continue
            if not tgt.id.upper().startswith(LIST_NAMES):
                continue
            for i, el in enumerate(v.elts, 1):
                key = f'{tgt.id}[{i}]'
                if not isinstance(el, ast.Tuple) or len(el.elts) < 4:
                    unknown.append(f'{p.stem}#{key}')
                    continue
                rel = const_str(el.elts[1])
                old = const_str(el.elts[2])
                if not looks_path(rel) or old is None or not old:
                    unknown.append(f'{p.stem}#{key}')
                    continue
                f = APP / str(rel)
                if not f.exists():
                    stale.append((p.stem, key, str(rel), '目标文件不存在'))
                    continue
                body = f.read_text(encoding='utf-8', errors='replace')
                if body.count(str(old)) == 0:
                    stale.append((p.stem, key, str(rel), '锚点命中 0 次'))
                else:
                    alive += 1
    return stale, alive, unknown, broken


def key_of(row: tuple[str, str, str, str]) -> str:
    return f'{row[0]}#{row[1]}|{row[2]}'


def read_baseline() -> dict[str, str]:
    """`键 -> 原因`（键 = `脚本#变量[序号]|路径`）。"""
    out: dict[str, str] = {}
    try:
        text = BASELINE.read_text(encoding='utf-8')
    except OSError:
        return out
    for ln in text.split('\n'):
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        # ⚠ 一条是 **三段**：`脚本#变量[序号]|路径|原因`。
        #   第一版用 `partition('|')` 只切出第一段当键，而 `key_of()` 给的是
        #   `脚本#变量[序号]|路径` ⇒ **一条都对不上**，于是"基线内全部失效"
        #   被判成"基线外全部失效"，C1/D2 同时假红。（自查：56 vs 56 却报 56 条新失效。）
        # [EN] Each line has **three** fields. `partition('|')` kept only the first as the key while
        # [EN] `key_of()` produces `script#key|path`, so nothing matched and every baseline entry
        # [EN] looked "outside the baseline" (false red on both C1 and D2).
        parts = [x.strip() for x in s.split('|')]
        if len(parts) < 2:
            continue
        k = parts[0] + '|' + parts[1]
        out[k] = parts[2] if len(parts) > 2 else ''
    return out


def group_a(stale, alive, unknown, broken) -> None:
    ok('A0 ★★ 扫到了反例法脚本（否则下面全是"没数据 ⇒ 绿"）',
       len(list(DEV.glob('mutate_*.py'))) >= 60,
       f'{len(list(DEV.glob("mutate_*.py")))} 个脚本')
    ok('A1 ★★★ 没有语法错误的反例法脚本'
       '（一个语法错误 = 这个文件的全部变异都跑不了，而它不会主动报）',
       not broken, f'{broken or "无"}')
    # ★★★ 覆盖率的口径（第一版判"核对率 >= 25%"，当场红 —— 而那是对的）：
    #   1050 条锚点是用 `chr(10)` / f-string / 变量拼出来的，**静态摘不出来**。
    #   这类只能靠真跑（`developers/mutate_*.py` 的锚点自检）。
    #   ⇒ 这里不假装全覆盖，只判两件事：**真的在核的数量够多**、
    #     并且**核对率没有被悄悄做低**（比如有人把锚点全改成动态拼的来躲这条）。
    # [EN] Coverage must be stated honestly: 1050 anchors are built with `chr(10)` / f-strings /
    # [EN] variables and cannot be extracted statically -- those rely on the scripts' own anchor
    # [EN] self-check. So this does not claim full coverage; it judges that enough anchors are
    # [EN] really checked, and that the checked ratio has not been quietly lowered.
    checked = alive + len(stale)
    total = checked + len(unknown)
    ok('A2 ★★★ 真的在核的锚点够多（≥ 500 条）'
       '（其余 1000+ 条是动态拼的，摘不出来 —— 这类靠脚本自己的锚点自检，判据不假装全覆盖）',
       checked >= 500,
       f'可核对 {checked} 条（活 {alive} / 失效 {len(stale)}）/ 摘不出 {len(unknown)} 条')

    # 成对：核对率不许被人为做低（把锚点改成动态拼的就能躲过 B1）
    # [EN] Paired: the checked ratio must not be lowered by rewriting anchors into dynamic strings.
    ok('A3 ★★★ 成对：**核对率没有被人为做低**（≥ 25%；把锚点改成动态拼的就能躲过 B1）',
       checked >= total * 0.25,
       f'{100 * checked / max(1, total):.0f}%')


def group_b(stale, base: dict[str, str]) -> set[str]:
    """基线外的失效必须为零；返回基线外的失效键集合。"""
    outside = [r for r in stale if key_of(r) not in base]
    ok('B1 ★★★ **基线以外的锚点全部命中** —— 这一条抓的是"以后谁重构搬走了锚点"'
       '（锚点一死，变异什么都不做，而人只会以为判据太弱）',
       not outside,
       f'{len(outside)} 条新失效：{[key_of(r) for r in outside][:4]}' if outside
       else f'{len(stale) - len(outside)} 条失效全在基线内')
    return {key_of(r) for r in outside}


def group_c(stale, base: dict[str, str]) -> None:
    live_keys = {key_of(r) for r in stale}

    fixed = [k for k in base if k not in live_keys]
    ok('C1 ★★★ **基线里已经修好的必须删掉**（否则清单会变成永久垃圾池，谁也不会回去看）',
       not fixed, f'{len(fixed)} 条已修好但仍列着：{fixed[:3]}' if fixed else '清单与现状一致')

    # ⚠ 这一条挡住"悄悄往清单里塞新条目"：条目数只许减。
    #   要加一条，先修掉一条 —— 与规则表欠账同一条纪律。
    # [EN] This blocks quietly adding entries: the count may only go down.
    ok(f'C2 ★★★ 基线条目数**只许减不许增**（现 {len(base)} 条）',
       len(base) <= BASE_CAP,
       f'{len(base)} / 上限 {BASE_CAP}')

    no_reason = [k for k, why in base.items() if not why]
    ok('C3 ★★ 每条失效都写了原因（空着的欠账会变成永久欠账）',
       not no_reason, f'{no_reason[:3] or "都写了"}')

    # 成对：清单里的条目必须**仍然真的失效**。已经活的在 C1 里抓了；
    # 这里抓"清单里写了但文件里根本没有这条变异"（重编号/删条目后留下的幽灵）。
    ghost = [k for k in base if k not in live_keys
             and not (APP / k.split('|', 1)[-1]).exists()]
    ok('C4 ★★ 清单里没有"幽灵条目"（脚本或路径已经不存在）',
       not ghost, f'{ghost[:3] or "无"}')


#: 基线条目上限。**冻结在建立基线当天的实际值（56），只许减。**
#: 想加一条：先把那条锚点修好（`developers/repair_anchors.py` 能自动修一部分），
#: 或者确认那条变异要防的东西已经不存在、直接把变异删掉。
#: ⚠ 这个数字**写死，不跟着当前基线条数走** —— 否则"只许减"就退化成"只要不变就算过"。
# [EN] Cap on baseline entries, hard-coded at the value when the baseline was created. **Do not**
# [EN] derive it from the current file, or "may only decrease" degrades into "unchanged is fine".
BASE_CAP = 56

def group_d(stale, base: dict[str, str]) -> None:
    ok('D1 ★★ 基线文件存在（没有就先 `--write-baseline`）', BASELINE.exists(),
       str(BASELINE.relative_to(APP)))
    ok('D2 ★★★ 基线里的条目**都在本次扫描里真的存在**（不是过期清单）',
       all(k in {key_of(r) for r in stale} for k in base) or not base,
       f'{len(base)} 条')
    ok('D3 ★★ 基线口径：**只许减**。修好一条就删一条，别留着当免责单',
       True, f'现 {len(base)} 条')


#: 反例法在自己改的那一行后面留的标记。**它出现在产品源码里 = 上一次没跑完。**
#: 实测（2026-10-19）：`sim/loop.py:6651` 残留过 `out.append(ln)   # 变异：不去重` ——
#: 也就是说紧接着跑的那次真跑（`snow_v10`）**用的是变异版代码**，而没有任何人知道。
#: ⚠ 现有的检测在 `tools/run_all_verifications.py::_mutation_leftovers`，
#:   但它**只在全量回归里跑** —— 单跑一个 mutate 脚本、被 SIGTERM 打断，没人会去看。
# [EN] The marker a counterexample leaves on the line it changed. Seeing it in product source means
# [EN] the last run did not finish. Measured: `sim/loop.py:6651` kept `# 变异：不去重` for a while --
# [EN] so the very next real run used mutated code and nobody knew. The existing check lives in
# [EN] `run_all_verifications` and only runs there.
_MUT_MARK = '变异：'
_MUT_SKIP_DIRS = {'__pycache__', '.venv', '.git', 'tools', 'tests', 'developers',
                  'logs', 'novel_bench', 'exports'}


def mutation_leftovers() -> list[str]:
    """产品源码里残留的变异标记：`['sim/loop.py:6651']`。空列表 = 干净。"""
    out: list[str] = []
    for p in APP.rglob('*.py'):
        if any(x in p.parts for x in _MUT_SKIP_DIRS):
            continue
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if _MUT_MARK not in text:
            continue
        # ★★★ 判法：**用 `tokenize` 只认真正的 COMMENT token**（2026-10-19，试了三版）。
        #
        #   为什么不能用"切 `#`"：
        #     第一版判"行里有 `变异：`" ⇒ 把 `novel_rules.py` 里那句
        #       fix='…跑完 `grep -rn "变异："` 查残留。'
        #     判成残留（那是**说明文字**）。
        #     第二版判"`#` 之后且 `#` 前有代码" ⇒ 又把
        #       symptom='…残留过 `out.append(ln)   # 变异：不去重`；'
        #     判成残留（`#` 在**字符串字面量里**，根本不是注释）。
        #   ⇒ 只有 tokenize 分得清"注释"和"字符串里的井号"。**这是唯一的正确判法。**
        # [EN] Use `tokenize` and accept only real COMMENT tokens (three attempts on 2026-10-19).
        # [EN] Splitting on `#` does not work: v1 flagged a doc string that merely *mentions* the
        # [EN] marker; v2 flagged a string literal containing `# 变异：`. Only tokenize can tell a
        # [EN] comment from a hash inside a string. This is the only correct way.
        import io as _io
        import tokenize as _tok

        try:
            toks = list(_tok.generate_tokens(_io.StringIO(text).readline))
        except (_tok.TokenError, IndentationError, SyntaxError):
            continue
        for t in toks:
            if t.type == _tok.COMMENT and _MUT_MARK in t.string:
                out.append(f'{p.relative_to(APP).as_posix()}:{t.start[0]}')
    return sorted(out)


def group_e() -> None:
    left = mutation_leftovers()
    ok('E1 ★★★ **产品源码里没有残留的变异标记**'
       '（有 = 上一次反例法没跑完，而**紧接着那次真跑用的是变异版代码**）',
       not left, f'{left or "干净"}')
    ok('E2 ★★ 而且 `run_all_verifications` 里那份同类检测**还在**'
       '（两处都在才叫双保险；删掉一处就只剩这一处）',
       '_mutation_leftovers' in (APP / 'tools' / 'run_all_verifications.py')
       .read_text(encoding='utf-8', errors='replace'), '')


def write_baseline(stale) -> None:
    lines = [
        '# 反例法锚点失效清单（`tools/verify_mutation_anchors.py` 读这里）',
        '#',
        '# 格式：脚本#变量[序号]|目标路径|原因',
        '#',
        '# ⚠ **只许删，不许加。** 修好一条就从这里删掉（判据 C1 会核对）。',
        '# 新失效会被判据 B1 当场抓住 —— 这份清单不是免责单，是待办单。',
        '#',
        '# 建立于 2026-10-19：597 条可静态核对的锚点里 56 条已失效（9.4%）。',
        '# 绝大多数是历史重构（`gui/app_flet.py` 反复重写、`sim/loop.py` 多次搬家）',
        '# 导致代码真的变了 —— 不是缩进漂移，`developers/repair_anchors.py` 也修不了。',
        '# 处理方式二选一：①按新代码改锚点；②那条变异要防的东西已经不存在 ⇒ 删掉变异。',
        '',
    ]
    for script, key, rel, why in sorted(stale):
        lines.append(f'{script}#{key}|{rel}|{why}')
    BASELINE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'已写入 {BASELINE.relative_to(APP)}：{len(stale)} 条')


def main() -> int:
    if '--write-baseline' in sys.argv:
        stale, _alive, _unknown, _broken = scan()
        write_baseline(stale)
        return 0

    print('═' * 62)
    print('  反例法锚点健康 · 它们自己会不会已经死了')
    print('═' * 62)
    stale, alive, unknown, broken = scan()
    base = read_baseline()

    print('\n【A】覆盖与语法')
    group_a(stale, alive, unknown, broken)
    print('\n【B】基线以外的锚点必须命中')
    group_b(stale, base)
    print('\n【C】基线只许减')
    group_c(stale, base)
    print('\n【D】基线本身')
    group_d(stale, base)
    print('\n【E】产品源码里有没有残留的变异标记')
    group_e()

    bad = [x for x in CHECKS if not x[1]]
    print('\n' + '═' * 62)
    print(f'  验证：{len(CHECKS) - len(bad)}/{len(CHECKS)} 条通过'
          + (f'，{len(bad)} 条红' if bad else '')
          + f'；锚点失效 {len(stale)} 条（基线 {len(base)}）')
    if bad:
        for n, _c, d in bad:
            print('  ✗ ' + n + (f'   [{d}]' if d else ''))
    print('═' * 62)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
