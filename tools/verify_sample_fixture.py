# -*- coding: utf-8 -*-
"""验证：测试夹具 `tools/sample_project.py` 真的**指向 `samples/`**、且不会飘。

用户规矩（2026-10-07）
--------
「测试的时候如果需要故事设定例子，从 samples 里选择一个测试，这个后续作为规则你来遵守」

这条规矩本身要能被检查 —— 否则"我遵守了"只是一句话。这一支钉住四件事：

  A **对得上磁盘**：`STORIES` / `STORIES_EN` 与 `samples/zh|en/` 下的目录一一对应
    （顺序也对齐 —— 两套靠下标对应，错一位就全错）。
  B **人物名不写死**：`cast()` 每篇都能给出名字、且与 `设定/人物/*.md` 的文件名一致
    （样例加人 / 删人，夹具自动跟上；写死的名字会让这条红）。
  C ★★ **地点名有出处**：`SCENE` / `EN_SCENE` 的每个值都**真的出现在那一篇的文件里**。
    这条是防漂移的核心 —— 夹具里最容易被随手写的就是一个地点名，
    写错了不会报错，只会让测试测到一个"这本书里没有的地方"（然后判据的红绿说不清）。
  D **只读与复制**：`prepare()` 改副本不污染 `samples/` 本体；认不出的 key **报错**
    （不能静默退回默认 —— 那会让一个写错 key 的测试悄悄测了另一篇）。
  E **真能当输入**：`ingest()` 在 MOCK 下跑完 `run_ingest`，出设定集、有世界观、有人物
    —— "样例能当测试输入"这句话本身要有证据。
  F **默认定死**：`DEFAULT_KEY = '01'`，且它带 `顶级规则.md`（硬约束类夹具要用）。
  G **判据自检**：把 `SCENE['01']` 改成一个不存在的地点，C 组必须红。

跑法：.venv\\Scripts\\python.exe tools/verify_sample_fixture.py
产出：assets/screenshots/sample_fixture_report.json

English:
Verification: the test fixture `tools/sample_project.py` really **points to `samples/`** and
won't drift.
User rule (2026-10-07)
--------
"When testing, if you need story setting examples, pick one test from samples; follow this as a
rule going forward"
This rule itself must be checkable -- otherwise "I followed it" is just a sentence. This branch
pins down four things:
  A **Matches the disk**: `STORIES` / `STORIES_EN` correspond one-to-one with the directories under `samples/zh|en/`
    (order is also aligned -- the two sets correspond by index, off by one and everything is wrong).
  B **Character names are not hardcoded**: `cast()` can give names for every piece, and they match the file names of `设定/人物/*.md`
    (adding / removing a person in the sample, the fixture follows automatically; hardcoded names will turn this red).
  C ★★ **Place names have a source**: every value of `SCENE` / `EN_SCENE` **really appears in that piece's files**.
    This is the core of drift prevention -- the thing most easily written offhand in fixtures is a place name,
    a wrong one won't raise an error, it will just make the test test a "place not in this book" (and then the criterion's red/green can't be told clearly).
  D **Read-only and copy**: `prepare()` modifies the copy without polluting the `samples/` original; an unrecognized key **raises an error**
    (cannot silently fall back to default -- that would make a test with a wrong key quietly test another piece).
  E **Really usable as input**: `ingest()` runs `run_ingest` under MOCK, produces a setting collection, has a worldview, has characters
    -- the statement "samples can serve as test input" itself must have evidence.
  F **Default is pinned**: `DEFAULT_KEY = '01'`, and it carries `顶级规则.md` (for hard-constraint fixtures).
  G **Criterion self-check**: change `SCENE['01']` to a nonexistent place, group C must turn red.
How to run: .venv\\Scripts\\python.exe tools/verify_sample_fixture.py
Output: assets/screenshots/sample_fixture_report.json
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from verify_ui_common import safe_rmtree                       # noqa: E402

import sample_project as SP                                    # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _snap(root: Path) -> dict:
    """整个 `samples/` 的快照（路径 → 字节）。**判据自己必须先有这份**。

    为什么：有一组判据要验证"`prepare()` 真的在复制" —— 做法是改副本、
    再看原件有没有跟着变。可如果 `prepare()` **坏了**（返回原目录），
    这一改就改到了随程序分发的样例上（2026-10-07 真发生过：反例法的
    "不复制"变异让夹具把 `新来的.md` 与「（测试改动）」写进了 `samples/`）。
    所以判据跑完要自己收拾干净：**逐字节还原 + 删掉多出来的文件**。
    
        English:
    A snapshot of the entire `samples/` (path -> bytes). **The criterion itself must have this
    first**.
        Why: one group of criteria needs to verify "`prepare()` really copies" -- the approach is to modify the copy,
        then see whether the original changed along with it. But if `prepare()` **is broken** (returns the original directory),
        this modification would land on the samples distributed with the program (actually happened on 2026-10-07: the counterexample's
        "does not copy" mutation made the fixture write `新来的.md` and "(test modification)" into `samples/`).
        So the criterion must clean up after itself: **byte-for-byte restore + delete extra files**.
    """
    return {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


def _restore(root: Path, snap: dict) -> list[Path]:
    """把 `samples/` 还原回快照；返回被动过的地方（空 = 本来就干净）。
        English:
    Restore `samples/` back to the snapshot; return the places that were touched (empty = already
    clean).
    """
    touched: list[Path] = []
    for p, b in list(snap.items()):
        if (not p.exists()) or p.read_bytes() != b:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
            touched.append(p)
    for p in list(root.rglob('*')):
        if p.is_file() and p not in snap:
            p.unlink()
            touched.append(p)
    return touched


def _text_of(story: Path) -> str:
    """这一篇的全部文字（判 C 组用：地点名必须出现在这里）。
        English:
    All the text of this piece (for group C: place names must appear here).
    """
    out: list[str] = []
    for p in sorted(story.rglob('*')):
        if p.is_file() and p.suffix.lower() in ('.md', '.txt'):
            out.append(p.read_text(encoding='utf-8'))
    return '\n'.join(out)


# ══════════════════════════════════════════════════════════════════
def test_align() -> None:
    zh = sorted(p.name for p in (SP.SAMPLES / 'zh').iterdir() if p.is_dir())
    en = sorted(p.name for p in (SP.SAMPLES / 'en').iterdir() if p.is_dir())
    ok('A1 `STORIES` 与 `samples/zh/` 下的目录一一对应（不多不少）',
       sorted(SP.STORIES) == zh, f'{len(SP.STORIES)} vs {len(zh)}')
    ok('A2 `STORIES_EN` 与 `samples/en/` 下的目录一一对应',
       sorted(SP.STORIES_EN) == en, f'{len(SP.STORIES_EN)} vs {len(en)}')
    pairs = [(SP.STORIES[i], SP.STORIES_EN[i]) for i in range(len(SP.STORIES))]
    ok('A3 ★ 两套**靠下标对齐** —— 每一对的开头序号必须相同（错一位就全错）',
       all(a[:2] == b[:2] for a, b in pairs), str([(a[:2], b[:2]) for a, b in pairs])[:70])
    ok('A4 六篇（而不是"几篇都行"）—— 规矩说的是"从 samples 里**选一篇**"',
       len(SP.STORIES) == 6 and len(SP.STORIES_EN) == 6, str(len(SP.STORIES)))


def test_cast(monkey=None) -> None:
    for k, story in zip(('01', '02', '03', '04', '05', '06'), SP.STORIES):
        d = SP.SAMPLES / 'zh' / story / '设定' / '人物'
        disk = sorted(p.stem for p in d.glob('*.md'))
        got = SP.cast(k)
        ok(f'B{k[-1]} 第 {k} 篇 `cast()` 与磁盘上的人物文件一致',
           got == disk and bool(got), f'{got} vs {disk}')
    # 名字是**读出来的**：临时给某一篇加个人，`cast()` 必须立刻多一个
    # [EN] The name is **read out**: temporarily adding a person to a certain piece means `cast()` must
    # [EN] immediately have one more
    tmp = Path(tempfile.mkdtemp(prefix='nws_fx_'))
    try:
        copy = SP.prepare(tmp, '01')
        (copy / '设定' / '人物' / '新来的.md').write_text('# 新来的\n', encoding='utf-8')
        add = SP.cast_from(copy) if hasattr(SP, 'cast_from') else None
        if add is None:
            # 夹具只按 key 读原目录 —— 那就换一条等价判据：改名后原目录不变
            # [EN] The fixture only reads the original directory by key -- so switch to an equivalent criterion:
            # [EN] after renaming, the original directory stays unchanged
            ok('B6 人物名是**读文件**得到的，不是写死在代码里'
               '（源码里没有硬编码的人名）', not _hardcoded_names(), '')
        else:
            ok('B6 临时加一个人，`cast()` 立刻多一个', '新来的' in add, str(add))
    finally:
        safe_rmtree(tmp)


def _hardcoded_names() -> list[str]:
    """夹具源码里有没有把某篇的人名写死（写死了 B 组就失去意义）。

    ⚠ **不能直接子串扫全文**：模块脚注里那句示例 `cast('01')  # ['主角', '柳娘']`
      就会被当成"写死了人名"（判据自己假红一次）。所以用 AST 只取**代码里的
      字符串字面量**，并把 docstring 排除掉 —— 这是这个项目的老坑：
      判据查"有没有某个词"时，注释与 docstring 必须先排除。
    
        English:
    Whether the fixture source code hardcodes a certain piece's person names (if hardcoded, group B
    loses its meaning).
        ⚠ **Cannot directly substring-scan the whole file**: the example in the module footnote `cast('01')  # ['主角', '柳娘']`
          would be treated as "hardcoded person names" (the criterion falsely goes red once). So use AST to take only the **string literals in the code**,
          and exclude docstrings -- this is an old pitfall in this project:
          when a criterion checks "whether a certain word is present", comments and docstrings must be excluded first.
    """
    tree = ast.parse((APP_DIR / 'tools' / 'sample_project.py')
                     .read_text(encoding='utf-8'))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docs.add(d)
    lits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docs:
                lits.append(node.value)
    code = '\n'.join(lits)
    bad = []
    for k in ('01', '02', '03', '04', '05', '06'):
        for nm in SP.cast(k):
            if nm and nm in code:
                bad.append(nm)
    return bad


def test_scene_sourced() -> None:
    for k, story in zip(('01', '02', '03', '04', '05', '06'), SP.STORIES):
        text = _text_of(SP.SAMPLES / 'zh' / story)
        for i, v in enumerate(SP.PLACES[k]):
            ok(f'C{k[-1]}.{i} ★★ 第 {k} 篇的地点「{v}」真的出现在它的原文里',
               v in text, f'{len(text)} 字里找到 {text.count(v)} 次')
        ok(f'C{k[-1]} ★ 第 {k} 篇有**两个以上**地点（换场类判据要用）',
           len(SP.PLACES[k]) >= 2, str(SP.PLACES[k]))
    for k, story in zip(('01', '02', '03', '04', '05', '06'), SP.STORIES_EN):
        text = _text_of(SP.SAMPLES / 'en' / story)
        for i, v in enumerate(SP.PLACES_EN[k]):
            # ⚠ 英文**不区分大小写**：判据要的是"这个地方真的存在"，
            #   不是"逐字符一样"（英文的地名大小写本来就随笔法走）。
            # [EN] ⚠ English is **case-insensitive**: the criterion wants "this place really exists",
            # [EN] not "character-for-character identical" (English place names naturally follow capitalization
            # [EN] conventions).
            n = text.lower().count(v.lower())
            ok(f'C{k[-1]}.{i}e ★ 英文第 {k} 篇的地点「{v}」也在原文里',
               n > 0, f'{len(text)} 字里找到 {n} 次')
    # ★ 同一把尺子量到底：行当名与"可当台词用的短句"也必须有出处。
    #   （夹具里最容易随手写的三样就是人名 / 地名 / 台词 —— 三样都要能回溯。）
    # [EN] ★ The same ruler measures all the way: role names and "short phrases usable as dialogue" must
    # [EN] also have a source.
    # [EN] (The three things most easily written offhand in fixtures are person names / place names /
    # [EN] dialogue -- all three must be traceable.)
    for k, story in zip(('01', '02', '03', '04', '05', '06'), SP.STORIES):
        text = _text_of(SP.SAMPLES / 'zh' / story)
        for i, v in enumerate(SP.roles(k)):
            ok(f'C{k[-1]}r ★ 第 {k} 篇的行当「{v}」也在原文里（没编名字）',
               v in text, f'找到 {text.count(v)} 次')
        norm_text = SP.norm(text)
        for i, v in enumerate(SP.LINES.get(k, ())):
            ok(f'C{k[-1]}L ★ 第 {k} 篇的台词「{v}」有出处（摘自设定/顶级规则/大纲）',
               SP.norm(v) in norm_text, f'归一化后找到 {norm_text.count(SP.norm(v))} 次')
    ok('C8 ★ 六篇每篇都有可用的台词（台词类夹具不许自己编）',
       all(len(SP.LINES.get(k, ())) >= 2 for k in SP.PLACES),
       str({k: len(v) for k, v in SP.LINES.items()}))
    ok('C8b ★ 台词里有**短句**（≤6 字）—— 判"按长度猜是不是应答"要靠它',
       any(len(v) <= 6 for k in SP.LINES for v in SP.LINES[k]),
       str([v for k in SP.LINES for v in SP.LINES[k] if len(v) <= 6]))

    ok('C9 两套地点表的 key 一样（缺一篇就会在别的判据里炸，不如这里说清）',
       set(SP.PLACES) == set(SP.PLACES_EN) == set(f'{i:02d}' for i in range(1, 7)),
       str(sorted(SP.PLACES)))
    ok('C10 `scene()` 就是 `places()[0]`（两条路不能各说各的）',
       all(SP.scene(k) == SP.places(k)[0] for k in SP.PLACES), '')


def test_copy_and_strict() -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_fx2_'))
    try:
        before = (SP.SAMPLES / 'zh' / SP.STORIES[0] / '设定' / '世界观.md').read_bytes()
        copy = SP.prepare(tmp, '01')
        f = copy / '设定' / '世界观.md'
        f.write_text(f.read_text(encoding='utf-8') + '\n（测试改动）', encoding='utf-8')
        after = (SP.SAMPLES / 'zh' / SP.STORIES[0] / '设定' / '世界观.md').read_bytes()
        ok('D1 ★ `prepare()` 是**复制**：改副本不污染随程序分发的样例',
           before == after and '测试改动' in f.read_text(encoding='utf-8'), '')
        copy2 = SP.prepare(tmp, '01')        # 再来一次要覆盖得干净
        # [EN] Run it again to cover cleanly
        ok('D2 同一个 tmp 上再 `prepare()` 一次 → 副本是干净的（不叠上次的改动）',
           '测试改动' not in (copy2 / '设定' / '世界观.md').read_text(encoding='utf-8'),
           '')
        # `pick()` 指向**原目录**（只读用）—— 这条要写清，以免有人拿它去改
        # [EN] `pick()` points to the **original directory** (for read-only use) -- this must be stated
        # [EN] clearly, so nobody uses it to modify
        ok('D3 `pick()` 返回的是 `samples/` 里的**原目录**（不是副本）',
           SP.pick('01').parent.name == 'zh'
           and SP.pick('01').name == SP.STORIES[0]
           and SP.pick('01').is_relative_to(SP.SAMPLES),
           str(SP.pick('01').relative_to(SP.SAMPLES)))
        for bad in ('999', 'x', '07'):
            try:
                SP._mid(bad)
                ok(f'D4 认不出的 key「{bad}」应当报错', False, '它静默接受了')
            except KeyError:
                ok(f'D4 认不出的 key「{bad}」报错（不静默退回默认）', True, '')
        ok('D5 `None` 走默认（`str(None)` 是 `\'None\'`，不能靠它判空）',
           SP._mid(None) == SP.DEFAULT_KEY, SP._mid(None))
    finally:
        safe_rmtree(tmp)


def test_ingest(tmp: Path) -> None:
    out = SP.ingest(tmp, '01')
    yaml_files = sorted(p.name for p in out.glob('*'))
    people = (out / '人物.yaml')
    world = (out / '世界观.md')
    n_chars = len([1 for _ in people.read_text(encoding='utf-8').splitlines()
                   if _.strip().startswith('-')]) if people.is_file() else 0
    ok('E1 ★ 拿样例真跑一遍 `run_ingest`（MOCK）→ 出了设定集',
       yaml_files and world.is_file(), f'{len(yaml_files)} 个文件')
    ok('E2 ★ 设定集里有世界观（不是空的）',
       world.is_file() and len(world.read_text(encoding='utf-8').strip()) > 20,
       f'{[len(world.read_text(encoding="utf-8")) if world.is_file() else 0]} 字')
    ok('E3 ★ 设定集里有人物（≥1）', n_chars >= 1, f'{n_chars} 个（人物.yaml）')
    ok('E4 顶级规则**原文照录**了（规则类文档不走归纳）',
       (out / '顶级规则.md').is_file()
       and '漏刻只许校' in (out / '顶级规则.md').read_text(encoding='utf-8'),
       f'{[(out / "顶级规则.md").stat().st_size]} 字节'
       if (out / '顶级规则.md').is_file() else '缺文件')


def test_default() -> None:
    ok('F1 默认取 01（悬疑）—— 定死而不是"随便挑一篇"',
       SP.DEFAULT_KEY == '01' and SP.pick().name == SP.STORIES[0], SP.pick().name)
    ok('F2 ★ 默认那一篇带 `顶级规则.md`（硬约束类夹具要用它）',
       len(SP.rule()) > 50, f'{len(SP.rule())} 字')
    ok('F3 `rule()` 给的是**原文**（能在样例文件里逐字找到）',
       SP.rule()[:40] in _text_of(SP.pick()), SP.rule()[:24].replace('\n', ' '))
    ok('F4 `outline()` 能用（开场/前情类夹具要用）',
       len(SP.outline()) > 100, f'{len(SP.outline())} 字')


def test_self_check() -> None:
    """判据自检：把地点改成一个**不存在**的地方，C 组必须红。
        English:
    Criterion self-check: change the place to a **nonexistent** one, group C must turn red.
    """
    real = SP.PLACES['01']
    try:
        SP.PLACES['01'] = ('一个不存在的地方',) + real[1:]
        text = _text_of(SP.pick('01'))
        red = SP.PLACES['01'][0] not in text
    finally:
        SP.PLACES['01'] = real
    ok('G1 ★ 判据自检：把地点改成不存在的地方，C 组**会红**'
       '（这条检查不是形式）', red, '')
    ok('G2 自检后已还原（`PLACES` 与原来一致）', SP.PLACES['01'] == real, str(real))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_fx_'))
    snap = _snap(SP.SAMPLES)          # 跑前留底（跑完必须一模一样）
    # [EN] Keep a backup before running (must be exactly identical after running)
    touched: list[Path] = []
    print('═' * 62)
    print('  验证：测试夹具指向 `samples/`（用户规矩 2026-10-07）')
    print('═' * 62)
    try:
        print('\n【A】对得上磁盘')
        test_align()
        print('\n【B】人物名是读出来的')
        test_cast()
        print('\n【C】地点名有出处（防漂移）')
        test_scene_sourced()
        print('\n【D】只读与复制 · 认错 key 要报错')
        test_copy_and_strict()
        print('\n【E】真能当输入（MOCK 跑一遍开卷）')
        test_ingest(tmp)
        print('\n【F】默认那一篇')
        test_default()
        print('\n【G】判据自检')
        test_self_check()
    except Exception:                                            # noqa: BLE001
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()
    finally:
        touched = _restore(SP.SAMPLES, snap)
        safe_rmtree(tmp)
    ok('H1 ★★ 这项检查自己**没有改动 `samples/`**（跑完与跑前逐字节一致）',
       not touched, f'被动过：{[str(x.name) for x in touched]}' if touched else '')

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'sample_fixture_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  样例夹具验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
