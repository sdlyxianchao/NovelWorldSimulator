# -*- coding: utf-8 -*-
"""判据：**写作注意事项里那几条缺口的落点**（2026-10-18 第二轮）。

来历
----
用户：「还有没有其他小说写作中需要注意的相关事项 请参考对应的专业论述
逐条进行检查和优化」。

检查表在 `developers/docs/写作注意事项检查表.md`：30 条专业条目，
落地 19 / 部分 7 / **缺 4**。这一支守的是本轮补上的两处：

  **A. 信息差（#8，戏剧反讽）** —— 在此之前 `secret` 只出现在本人的人格卡里，
     于是秘密只影响"他怎么说"，**完全不影响别人怎么对他**。
     修法：`PersonState.knows`（知情者）＋ `WorldState.blind_spots/leaks`
     ＋ 演员提示词只给"谁瞒着事"（不给内容）＋ 上屏闸兜底。

  **B. 手艺库轮换（不是"注意事项"，但是那张表成立的前提）** ——
     `MAX_ENTRIES=2` 本身是成本约束，但老实现**永远取映射前 2 条** ⇒
     实测 6 张类型卡共 **8 条手艺**（草蛇灰线 / 悬念引擎 / 突转与发现 /
     换地图节奏 / 黄金三章 / 伦理探讨 / 甜蜜暴击 / 期望鸿沟）写在库里却从没到过提示词。

⚠ 本支**不判"文笔好坏"**：那是主观的，且真人样本彼此差得也很大。
  判的是"这几条约束还在不在、口径有没有被写歪"。

跑法：`.venv/Scripts/python.exe tools/verify_writing_coverage.py`
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail='') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(f'  {"✓" if cond else "✗"} {name}'
          + (f'   [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _world(**people):
    from world.state import PersonState, WorldState

    w = WorldState()
    for name, kw in people.items():
        w.people[name] = PersonState(name=name, **kw)
    return w


# ══════════════════════════════════════════════════════════
#  A  信息差：谁知道什么
# ══════════════════════════════════════════════════════════
def group_a() -> None:
    w = _world(
        甲=dict(secret='三百年前的旧案', knows=['乙']),
        乙=dict(secret='那件旧事的三百年'),
        丙=dict(secret='掌柜的养女'),
    )
    ok('A1 ★★★ `blind_spots` 算得出"他不知道谁的秘密"（秘密不再是公开信息）',
       set(w.blind_spots('甲')) == {'乙', '丙'},
       str(w.blind_spots('甲')))
    # ⚠ 夹具语义：`甲 knows=['乙']` 表示"**甲的秘密，乙知道**"。
    #   所以该测的是 `blind_spots('乙')` 里**没有甲**，而**有丙**。
    #   第一版写成 `'乙' not in blind_spots('乙')`（自己在自己的列表里 —— 恒真），
    #   于是"`knows` 不认"这个变异不会红（反例法 M03 当场抓出来）。
    # [EN] Fixture semantics: `Chen forgets knows=['Mo Wen']` means "**Mo Wen knows Chen's
    # [EN] secret**", so the test is: Mo Wen's blind spots **exclude Chen** and **include
    # [EN] Xiao Liuzi**. The first version tested "Mo Wen is not in Mo Wen's list" (always true),
    # [EN] so the "knows ignored" mutation stayed green (caught by counterexample M03).
    ok('A2 ★★★ 成对：**知情者不算不知道**（`knows` 里写了他，他就该知道）',
       '甲' not in w.blind_spots('乙') and '丙' in w.blind_spots('乙'),
       str(w.blind_spots('乙')))
    ok('A3 ★★★ 返回的是**名字**不是内容（内容递过去等于当场公开所有秘密）',
       all('旧事' not in x and '养女' not in x for x in w.blind_spots('甲')),
       str(w.blind_spots('甲')))

    # ── 泄露判定 ──
    # ⚠ 夹具台词必须**含乙的秘密原文里够长的片段**（`那件旧事的三百年`）：
    #   判"泄露"靠的是与秘密文本的片段重合，改夹具时人名换了、台词也得跟着对齐。
    # [EN] The line must contain a long enough fragment of the secret itself; the leak test works by
    # [EN] fragment overlap, so renaming the cast means rewording the line too.
    ok('A4 ★★★ 说出别人的秘密 ⇒ 点得出是谁的（"那件旧事的三百年"那句）',
       w.leaks('那件旧事的三百年吧，你守得够久了', '丙') == '乙',
       repr(w.leaks('那件旧事的三百年吧，你守得够久了', '丙')))
    ok('A5 ★★★ 成对：**无关的话不许误报**（误报会让每句台词都被拦）',
       w.leaks('外头下雪了，把门关上', '丙') == '',
       repr(w.leaks('外头下雪了，把门关上', '丙')))
    ok('A6 ★★★ 成对：**知情者说了不算泄露**（他知道，说出来是正常的）',
       w.leaks('三百年前的旧案', '乙') == '',
       repr(w.leaks('三百年前的旧案', '乙')))
    ok('A7 ★★ 成对：**本人说自己**不算泄露',
       w.leaks('那件旧事的三百年我自己记得', '乙') == '',
       repr(w.leaks('那件旧事的三百年我自己记得', '乙')))

    # ── 几个真实设定里的边界（三条秘密共用"三百年"）──
    # ⚠ 这是量出来的坑：按"有没有共同片段"判，`三百年` 三条秘密都有 ⇒ 张冠李戴。
    # [EN] Measured trap: "any shared fragment" misattributes, because 三百年 appears in three
    # [EN] different secrets.
    _w2 = _world(甲=dict(secret='三百年前的旧账'), 乙=dict(secret='三百年守着一座楼'))
    # ⚠ 夹具必须**含那个共用词**：第一版用"外头下雪了"（一个字都不共），
    #   于是"按共同片段判"的变异也不会红，测的等于空。
    # [EN] The fixture must **contain the shared word**: the first version used a sentence sharing
    # [EN] nothing, so the "any shared fragment" mutation stayed green -- the test was empty.
    ok('A8 ★★★ 三条秘密共用同一个词（"三百年"）时**不许张冠李戴**'
       '（要按最长公共片段判，不能按"有没有共同片段"）',
       _w2.leaks('都过了三百年了', '甲') == '',
       repr(_w2.leaks('都过了三百年了', '甲')))
    ok('A9 ★★ 但**整句**说别人的秘密要认得出（"三百年守着一座楼"）',
       _w2.leaks('我听说有人三百年守着一座楼', '甲') == '乙',
       repr(_w2.leaks('我听说有人三百年守着一座楼', '甲')))

    # ── 设定加载 ──
    # ⚠ **判产品的语句**，不是判"源码里有这两个字"，也不是"自己写一份解析再测自己"。
    #   第一版写了个本地 `_parse()` 复制品来断言 —— 那和产品毫无关系，
    #   `knows=[]` 的变异照样绿（反例法 M06 当场抓出）。
    #   真跑 `build_world` 要整套设定集（太重），折中：**用 AST 读那一段赋值**，
    #   要求 `knows=` 的值表达式里真的出现 `知情者`。
    # [EN] Judge the **product statement**, not "the two words appear" and not "write a local parser
    # [EN] and test that" (the first version did exactly that -- unrelated to the product, so the
    # [EN] `knows=[]` mutation stayed green; caught by M06). Running `build_world` needs a whole
    # [EN] settings set (too heavy); the compromise is to read the assignment via AST and require
    # [EN] `知情者` inside the `knows=` value expression.
    _st = ast.parse(_read('sim/setup.py'))
    _knows_src = ''
    for _n in ast.walk(_st):
        if (isinstance(_n, ast.Call) and isinstance(_n.func, ast.Name)
                and _n.func.id == 'PersonState'):
            for _k in _n.keywords:
                if _k.arg == 'knows':
                    _knows_src = ast.unparse(_k.value)
    ok('A10 ★★★ 设加载**真的**把 `知情者` 读进 `knows=`（不写 = 只有他自己知道）',
       '知情者' in _knows_src, _knows_src[:80] or '（没找到 knows=）')

    # ── 上屏闸兜底 ──
    # ⚠ 第一版按"`_review_gate` 之后 2500 字"找 —— 而它的 docstring 就有两千多字，
    #   真正那句被切在外面 ⇒ 判据假红。改成**按函数体**找（AST 取整个 def）。
    # [EN] The first version searched only 2500 characters after `_review_gate`, but its docstring
    # [EN] alone is 2000+, so the real line fell outside => false red. Search the **whole function
    # [EN] body** via AST.
    # ⚠ **行为判**：真叫一次闸门，看它拦不拦。第一版判"函数体里有没有这个词"，
    #   变异成 `if False: why = leak_check(...)` 照样绿。
    # ⚠ 但整条闸门要 `CFG.b('SCRIPT_REVIEW')`、要一个 loop 实例 —— 太重。
    #   退一步：判 `_review_gate` 的**语句序列**里有没有一个"真的会执行到"的赋值
    #   （不是注释、不是 `if False` 下面）。
    # [EN] **Behaviour**: call the gate once and see whether it blocks. The first version checked
    # [EN] "the word appears in the body", which stays green under `if False: ...`. Calling the whole
    # [EN] gate needs CFG + a loop instance -- too heavy -- so instead judge the **statement
    # [EN] sequence** for a reachable assignment (not a comment, not under `if False`).
    _tree = ast.parse(_read('sim/loop.py'))
    _gate = next((n for n in ast.walk(_tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == '_review_gate'), None)
    # ⚠ **"可达"不等于"AST 里有这个赋值"**：`if False: why = leak_check(...)` 里的
    #   Assign 照样在树里 ⇒ 第一版对 M07 假绿。
    #   ⇒ 走一遍函数体，**跳过恒假分支**（`if False` / `if 0`），只在真会执行的地方找。
    # [EN] ⚠ "Reachable" is not "the assignment exists in the AST": the Assign inside
    # [EN] `if False:` is still in the tree, so the first version stayed green on M07.
    # [EN] => walk the body **skipping always-false branches**.
    def _is_false(test) -> bool:
        return isinstance(test, ast.Constant) and test.value in (False, 0, None, '')

    def _scan(stmts) -> bool:
        for st in stmts:
            if isinstance(st, ast.Assign) and 'leak_check' in ast.unparse(st.value):
                return True
            if isinstance(st, ast.If):
                if _is_false(st.test):
                    continue          # 恒假分支：不算执行得到
                if _scan(st.body):
                    return True
                if _scan(st.orelse):
                    return True
            for fld in ('body', 'orelse', 'finalbody'):
                sub = getattr(st, fld, None)
                if isinstance(sub, list) and sub and isinstance(sub[0], ast.stmt):
                    if _scan(sub):
                        return True
            for h in getattr(st, 'handlers', []) or []:
                if _scan(h.body):
                    return True
        return False

    ok('A11 ★★★ 上屏闸**真的会执行到** `leak_check`（不是写在 `if False` 底下）',
       _gate is not None and _scan(_gate.body), '')


# ══════════════════════════════════════════════════════════
#  B  信息差进提示词（真跑抓 prompt）
# ══════════════════════════════════════════════════════════
class _FakeDB:
    def retrieve_memory(self, *a, **k):
        return []

    def add_memory(self, *a, **k):
        pass

    def count_memories(self, *a, **k):
        return 0

    def get_summaries(self, *a, **k):
        return []

    def recent_events(self, *a, **k):
        return []


def _capture(*, people: dict, me: str) -> str:
    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    for name, kw in people.items():
        w.people[name] = PersonState(name=name, location='临河茶肆', **kw)
    a = Agent(w.people[me], _FakeDB(), w)
    seen: dict = {}
    real = AC.llm.chat

    async def fake_chat(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '测试'}, ensure_ascii=False), {})

    AC.llm.chat = fake_chat
    try:
        asyncio.run(a.decide())
    finally:
        AC.llm.chat = real
    return str(seen.get('prompt') or '')


def group_b() -> None:
    p = _capture(people={
        '主角': dict(identity='茶肆掌柜', secret='账上的窟窿是我填的'),
        '伙计': dict(identity='跑堂', secret='我偷了柜上的钱'),
    }, me='主角')
    ok('B1 ★★★ 真跑 `decide()` 抓到了 prompt', len(p) > 500, f'{len(p)} 字')
    ok('B2 ★★★ 发出去的 prompt 里**真有** `[这一场有人在瞒事]`',
       '[这一场有人在瞒事]' in p, '')
    ok('B3 ★★★ 而且点了名字（"伙计 各有事没说"）',
       '伙计' in p and '各有事没说' in p, '')
    ok('B4 ★★★ 明写"**不知道瞒的是什么**"＋"不许替他们说破"'
       '（给名字不给内容，这是这条的整个要点）',
       '不知道瞒的是什么' in p and '不许' in p, '')
    # ── 成对：秘密**内容**绝不许出现在别人的提示词里 ──
    ok('B5 ★★★ 成对：**秘密内容**没有进别人的提示词（"我偷了柜上的钱"不许出现）',
       '我偷了柜上的钱' not in p, '')
    # ── 成对：没人瞒事时不许啰嗦 ──
    p2 = _capture(people={'主角': dict(identity='茶肆掌柜')}, me='主角')
    ok('B6 ★★★ 成对：设定里**没有秘密**时，这一段一个字都不挂'
       '（否则每拍都有一段"有人在瞒事"，模型会当噪声）',
       '[这一场有人在瞒事]' not in p2, '')


# ══════════════════════════════════════════════════════════
#  C  手艺库轮换：71 条不许只有 12 条能到提示词
# ══════════════════════════════════════════════════════════
def group_c() -> None:
    from craft import craftmix as CM

    ok('C1 ★★★ 手艺库不是空的（否则下面几条是"没数据 ⇒ 绿"）',
       len(CM.load()['entries']) >= 50, str(len(CM.load()['entries'])))

    # 每个类型卡：把 offset 走一圈，看映射里的条目**是不是全都能轮到**
    missed: list[str] = []
    for gname, cdata in CM.load()['genres'].items():
        names = [str(x) for x in (cdata.get('playbook映射') or [])]
        if len(names) <= CM.MAX_ENTRIES:
            continue
        seen: set[str] = set()
        for off in range(len(names)):
            seen |= {n for n, _ in CM.entries_for(gname, offset=off)}
        for n in names:
            if not CM.resolve_entry(n):
                continue          # 映射名本来就查不到（另一支判据管）
            if n not in seen:
                missed.append(f'{gname}:{n}')
    ok('C2 ★★★ 每张类型卡映射里的手艺**都轮得到**'
       '（老实现永远取前 2 条 ⇒ 实测 8 条手艺一辈子进不了提示词）',
       not missed, f'轮不到 {missed}')

    ok('C3 ★★★ 成对：**一次仍然只喂 2 条**（成本约束不许被"全喂"破坏 —— '
       '每条 ≤80 token，全喂就是每拍多付 300+）',
       len(CM.entries_for('悬疑灵异', offset=1)) <= CM.MAX_ENTRIES,
       str(len(CM.entries_for('悬疑灵异', offset=1))))
    ok('C4 ★★ 成对：`offset` 相同 ⇒ 结果相同（可复现；否则每次跑都不一样，无法复查）',
       [n for n, _ in CM.entries_for('悬疑灵异', offset=2)]
       == [n for n, _ in CM.entries_for('悬疑灵异', offset=2)], '')

    # 导演那边真的传了 offset（不传就等于没改）
    eng = _read('director/engine.py')
    ok('C5 ★★★ 导演的调用点**真的传了 offset**（不传 = 轮换不生效，且外面看不出来）',
       'craftmix.brief(*self._card_name(), offset=' in eng, '')


# ══════════════════════════════════════════════════════════
#  D  检查表本身：缺口清单不许悄悄变
# ══════════════════════════════════════════════════════════
def group_d() -> None:
    doc = _read('developers/docs/写作注意事项检查表.md')
    ok('D1 ★★ 检查表存在，且列了 30 条（这是"逐条检查"的交付物本身）',
       len(doc) > 1500 and '| 30 |' in doc, f'{len(doc)} 字')
    # ★★★ 2026-10-18 晚：**缺口清零之后，这一条差点变成"为一个已被推翻的设计作证"**。
    #
    #   第一版 D2 要求"表里必须有 `❌ 缺` 的行"—— 缺口真补完之后它照样红，
    #   逼人去改判据而不是改事实（这正是本项目记过的那个坑）。
    #   但它守的那件事**仍然要守**：不许把缺口行**删掉**来假装落地。
    #
    #   ⇒ 改判**两条，成对**：
    #     ① **表的行数必须还是 30**（删行 = 躲红，当场红）；
    #     ② 每行的「判定」列要么是 `落地`，要么是 `缺`/`部分` **且正文写明还剩几条**。
    #   这样"补上"（把 ❌ 改 ✅）和"删掉"（把行去了）就被分开了。
    # [EN] ★★★ 2026-10-18 evening: once the gaps closed, this check nearly became "testifying for a
    # [EN] design that has been overturned". The first D2 required a `❌ 缺` row, so it stayed red
    # [EN] after the gaps were genuinely closed, pushing a human to edit the criterion instead of the
    # [EN] facts. But what it guards **still matters**: nobody may **delete** gap rows to fake landing.
    # [EN] => Two paired checks: ① the table must still have 30 rows (deleting a row is hiding, red);
    # [EN] ② each verdict cell is either 落地, or 缺/部分 **with the remaining count stated in prose**.
    import re as _re

    _verdict = []
    for ln in doc.splitlines():
        if not ln.startswith('|'):
            continue
        cells = [c.strip() for c in ln.strip().strip('|').split('|')]
        # 只认"编号行"：第一格是数字
        if cells and cells[0].isdigit():
            # ⚠ 判定列里有 `**落地（本轮）**` 这种加粗写法 ⇒ **先剥掉星号**再判开头。
            #   第一版没剥，10 行被当成"没落地" —— 判据自己造的假红。
            # [EN] Verdict cells like `**落地（本轮）**` carry markdown emphasis => strip the stars
            # [EN] before matching. The first version did not, so ten rows read as "not landed".
            _verdict.append((int(cells[0]), cells[-1].strip('*').strip()))
    ok('D2 ★★★ 表还是 **30 行**（把缺口行删掉来假装落地 ⇒ 当场红）',
       len(_verdict) == 30 and [i for i, _v in _verdict] == list(range(1, 31)),
       f'{len(_verdict)} 行')

    _missing = [(i, v) for i, v in _verdict if not v.startswith('落地')]
    _rows_missing = [i for i, _v in _missing]
    _m = _re.search(r'([一二三四五六七八九十\d]+)\s*条\s*(?:缺|仍未落地)', doc)
    _cn = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8}
    _n = (_cn.get(_m.group(1)) if _m and _m.group(1) in _cn
          else int(_m.group(1)) if _m and _m.group(1).isdigit() else -1)
    # ① 有缺口 ⇒ 正文必须写明剩几条，且数目对得上
    # ② 没缺口 ⇒ 正文必须写明"全部落地"（不许悄悄清零）
    # [EN] ① gaps remain => prose must state how many, and the count must match.
    # [EN] ② no gaps => prose must say "all landed" (silent clearing is not allowed).
    if _missing:
        ok('D3 ★★★ 还有缺口时，正文**写明剩几条**且数目与表对得上',
           _n == len(_rows_missing),
           f'表里 {len(_rows_missing)} 条（{_rows_missing}）/ 正文说 {_n}')
    else:
        # ⚠ 必须钉**"覆盖率"那一行**（结论行），不是"文档任意处出现这几个字"。
        #   第一版判"全文含 `30 条全部`" ⇒ 文档开头那句也满足，
        #   把结论行改成"都差不多了"照样绿（反例法 M15 抓出来的）。
        # [EN] Must pin the **"coverage" conclusion line**, not "these words appear anywhere".
        # [EN] The first version matched the opening sentence too, so rewriting the conclusion line
        # [EN] stayed green (caught by M15).
        _cov = next((ln for ln in doc.splitlines() if ln.startswith('**覆盖率')), '')
        ok('D3 ★★★ 缺口清零时，**"覆盖率"那一行**明写"30 条全部落地"'
           '（不许悄悄把 `❌` 改成 `✅` 就算完）',
           '30 条全部' in _cov and '落地' in _cov, _cov[:40])


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            ok(f'{fn.__name__} 执行失败', False, repr(e))
    bad = [c for c in CHECKS if not c[1]]
    print(f'\n写作覆盖验证：{len(CHECKS) - len(bad)}/{len(CHECKS)}', flush=True)
    if bad:
        print('有失败项：', flush=True)
        for n, _, _d in bad:
            print(f'  ✗ {n}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
