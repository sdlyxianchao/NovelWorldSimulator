# -*- coding: utf-8 -*-
"""验证：卫生分里的「视角漂移」不许再冤枉**心里的话**（2026-10-20）。

起因（用户这一轮拿到的数）
--------------------------
`snow_v18` 卫生 92.1，比 `snow_v17` 的 97.5 掉了 5.4 分，唯一罚项是
「第三人称作品里叙述层出现『我』×18」。看着像这一版写坏了。

查下去是**计量器自己报错**：成品小说里共 13 个「我」，**全部在台词引号里**，
引号外一个都没有 —— 真 First-person POV 泄漏是 0。那 18 个来自 transcript 里
这种条目：`驹子心想：我借着酒劲才敢开口，他会怎么回应我呢？`
**第三人称小说里人物心里自称"我"是对的**，那不叫视角漂移。

修法：`metrics.compute` 里量 first-person 的那一层，把 `aside` 跟 `dialogue`
一样排除掉 —— **人物心里的话不是叙述者的嗓子**。

这一支护四件事（两条机能 + 两条"不许靠蒙着眼得 0"）：
  A1 心里的话里满篇「我」 ⇒ 一次都不许罚（不误伤）；
  A2 同样的「我」放进**叙述层** ⇒ 必须罚（不许修完就抓不到）；
  A3 口径真在源码里（`ast` 去读那个排除集合，不是只看"源码含字符串"）；
  A4 真跑 v18 上：**成品引号外确实没有「我」** 且 **罚项确实是 0** ——
    两条必须同时成立，否则就是"把眼睛蒙上了才算干净"。

跑法：`.venv/Scripts/python.exe tools/verify_hygiene_pov.py`
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

import config as CFG                                            # noqa: E402

CFG.redirect_env_writes() if hasattr(CFG, 'redirect_env_writes') else None
try:
    CFG.CFG.set('MOCK_LLM', 'true')
except Exception:                                               # noqa: BLE001
    pass

CHECKS: list[tuple[str, bool, str]] = []
MET = APP / 'novel_bench' / 'bench' / 'metrics.py'
RESULTS = APP / 'novel_bench' / 'results'

#  台词引号有两种写法（弯的 “” 和直的 ""），两边都要认。
QUOTED = re.compile(r'[\u201c\u201d"\'][^\u201c\u201d"\']*[\u201c\u201d"\']')


def ok(name: str, cond, detail: str = '') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'   [{detail}]' if detail else ''),
          flush=True)
    return bool(cond)


# ── 合成素材：够 `compute` 跑起来就行 ───────────────────────────
def _case_dir(tmp: Path, *, first_person_in: str) -> Path:
    """做一份最小的 case：只有 transcript.jsonl + novel.md。

    `first_person_in` = 把「我」放在**哪一种**条目里：
      'aside' —— 心里的话（应该放假）
      'narration' —— 叙述层（应该挨罚）
    """
    tmp.mkdir(parents=True, exist_ok=True)
    clean = ['（ hallway 廊下的灯暗了一截。）',
             '（ 纸门外的雪落得没有声音。）',
             '（ 火钵里的炭塌下去一小块。）',
             '（ 檐外的水声断断续续。）',
             '（ 他把酒壶放回原处。）']
    dirty = ['驹子心想：我借着酒劲才敢开口，他会怎么回应我呢？',
             '驹子心想：我这是怎么了，怎么就这么忍不住呢。',
             '驹子心想：我坐这么近，他连眼皮都不抬。',
             '岛村心想：我倒要看看她能待多久。',
             '驹子心想：这话一出口，我脸上先热了。',
             '叶子心想：我就站在这里，不进去也好。',
             '驹子心想：我写的那些，他会看一看吗。',
             '岛村心想：我也不催她，由她去说。',
             '驹子心想：我怕她听见的偏偏还是我这句话。',
             '叶子心想：我替他说一句也好。']
    rows: list[dict] = []
    for t in clean:
        rows.append({'kind': 'narration', 'text': t})
    for t in dirty:
        rows.append({'kind': first_person_in, 'text': t})
    for i in range(30):
        rows.append({'kind': 'dialogue',
                     'text': f'他说了第 {i} 句话，声音不高，也没有人接话。'})
    rows.append({'kind': 'scene', 'text': '温泉旅馆的房间，夜里，雪。'})

    (tmp / 'transcript.jsonl').write_text(
        '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n',
        encoding='utf-8')

    # ⚠ novel.md 必须 >= 200 字才会被当成成品（见 `load_result_text`），
    #   否则 `compute` 走 transcript 分支，A1/A2 就量不到我们想量的东西。
    body = []
    for t in clean:
        body.append(t.strip('（） '))
    for i in range(40):
        body.append(f'她抬眼看了看第 {i} 次纸上晃动的光，又把话咽了回去。')
    (tmp / 'novel.md').write_text('## 第 1 天 · 子时\n\n' + '\n'.join(body) + '\n',
                                  encoding='utf-8')
    return tmp


def _run(case_dir: Path) -> dict:
    from novel_bench.bench import metrics as M
    work = SimpleNamespace(
        id='povx', category='近代', people_names=['驹子', '岛村', '叶子'],
        people_aliases=lambda: {'驹子': ['驹子姐'], '岛村': [], '叶子': []},
        style=lambda: {'pov': '第三人称限知', 'taboos': [], 'era': 'modern'})
    case = SimpleNamespace(id='pov-01', present=['驹子', '岛村', '叶子'])
    return M.compute(work, case, case_dir)


# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    import tempfile
    print('    · 合成「我」在**心里的话**里', flush=True)
    with tempfile.TemporaryDirectory() as td:
        d = _case_dir(Path(td) / 'c1', first_person_in='aside')
        m = _run(d)
    fp = int(m.get('first_person_marks') or 0)
    drift = float((m.get('penalties') or {}).get('视角漂移') or 0.0)
    ok('A1 ★★ 心里的话里满篇「我」 ⇒ 一次都不许罚（不误伤）',
       fp == 0 and drift == 0.0,
       f'first_person_marks={fp} 视角漂移={drift}')
    ok('A1b 条目真的进了量表（不是"空文本 ⇒ 0"）',
       int(m.get('entries') or 0) >= 40, f'entries={m.get("entries")}')

    print('    · 同样的「我」放进**叙述层**', flush=True)
    with tempfile.TemporaryDirectory() as td:
        d = _case_dir(Path(td) / 'c2', first_person_in='narration')
        m = _run(d)
    fp2 = int(m.get('first_person_marks') or 0)
    drift2 = float((m.get('penalties') or {}).get('视角漂移') or 0.0)
    ok('A2 ★★ 同样的「我」落在叙述层 ⇒ 必须罚（修完不许抓不到）',
       fp2 >= 10 and drift2 > 0.0,
       f'first_person_marks={fp2} 视角漂移={drift2}')


def group_b() -> None:
    """口径真写在代码里 —— 用 `ast` 读那个排除集合，不是"源码含字符串"。

    ⚠ 老规矩：字符串 search 会把**注释里的话**也算进去（注释里就有 "aside"）。
      所以必须找到真的 `Compare`（`kind not in (...)`）再去取其中 Tuple 常量。
    """
    tree = ast.parse(MET.read_text(encoding='utf-8'), filename=str(MET))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and node.ops:
            for cmp_ in node.comparators:
                if (isinstance(cmp_, (ast.Tuple, ast.List))
                        and len(cmp_.elts) >= 4):
                    vals = [e.value for e in cmp_.elts
                            if isinstance(e, ast.Constant)
                            and isinstance(e.value, str)]
                    if {'dialogue', 'speak', 'line'} <= set(vals):
                        found = vals
    ok('A3 ★★ `ast` 找到了量 first-person 的那个排除集合（found %s）' % found,
       bool(found), '没找到 ⇒ 源码改过形状，这条守不住了')
    ok('A3b 排除集合里有 `aside`（心里的话跟台词一样不算叙述层）',
       'aside' in found, f'实际={found}')


def group_c() -> None:
    """A4 —— 不许靠"蒙着眼"得 0：真跑数据是双盲对照。"""
    d = RESULTS / 'snow_v18' / 'cases' / 'ykg-01'
    if not d.is_dir():
        ok('A4 缺真跑 snow_v18（跳过）', True, 'no data')
        return
    novel = (d / 'novel.md').read_text(encoding='utf-8')
    masked = QUOTED.sub(lambda m: '　' * len(m.group(0)), novel)
    outside = masked.count('我')
    ok('A4a ★★ 成品小说**引号外**一个「我」都没有（"0 分"不是蒙出来的）',
       outside == 0, f'引号外 {outside} 个 / 全文 {novel.count("我")} 个')

    from novel_bench.bench import dataset as DS         # noqa: E402
    works = {w.id: w for w in DS.load_all()}
    pair = None
    for w in works.values():
        for c in w.cases:
            if c.id == 'ykg-01':
                pair = (w, c)
    if not pair:
        ok('A4b 找不到 ykg-01 这个用例（跳过）', True, 'no case')
        return
    from novel_bench.bench import metrics as M  # noqa: E402
    m = M.compute(pair[0], pair[1], d)
    drift = float((m.get('penalties') or {}).get('视角漂移') or 0.0)
    ok('A4b ★★ 真跑 v18 的「视角漂移」按新口径确实是 0',
       drift == 0.0, f'视角漂移={drift} 卫生={m.get("hygiene_score")}')


def group_d() -> None:
    """A5 —— 第一人称作品本来就不该走这一栏（别把这当补救机会）。"""
    import tempfile
    from novel_bench.bench import metrics as M
    with tempfile.TemporaryDirectory() as td:
        d = _case_dir(Path(td) / 'c3', first_person_in='narration')
        try:
            m = _run(d)
            ok('A5a 合成用例跑得通', bool(m.get('penalties')), 'ok')
        except Exception as e:                                  # noqa: BLE001
            ok('A5a 合成用例跑得通', False, repr(e))
            return
    # 把 pov 换成第一人称 ⇒ 这一栏必须是 0（不是"抓了又放行"）
    work = SimpleNamespace(
        id='povx', category='近代', people_names=['驹子'],
        people_aliases=lambda: {'驹子': []},
        style=lambda: {'pov': '第一人称', 'taboos': [], 'era': 'modern'})
    case = SimpleNamespace(id='pov-01', present=['驹子'])
    with tempfile.TemporaryDirectory() as td:
        d = _case_dir(Path(td) / 'c4', first_person_in='narration')
        m = M.compute(work, case, d)
    ok('A5b ★★ 第一人称作品不罚「视角漂移」（口径方向不许反）',
       float((m.get('penalties') or {}).get('视角漂移') or 0.0) == 0.0,
       f'视角漂移={(m.get("penalties") or {}).get("视角漂移")}')


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d):
        print(f'\n── {fn.__name__} ──', flush=True)
        try:
            fn()
        except Exception as e:                                  # noqa: BLE001
            import traceback
            ok(f'{fn.__name__} 执行失败', False,
               traceback.format_exc()[-300:])
    bad = [c for c in CHECKS if not c[1]]
    print(f'\n视角漂移口径验证：{len(CHECKS) - len(bad)}/{len(CHECKS)}', flush=True)
    for n, _, _d in bad:
        print(f'  ✗ {n}', flush=True)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
