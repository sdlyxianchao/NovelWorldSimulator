# -*- coding: utf-8 -*-
"""分层创作（atelier）的判据 —— 四组。

A 组：变化账本（**空转的唯一判据**）
    A1  签名只由闭集四槽构成 —— 换措辞不影响签名（同义词后门）
    A2  成对：真推进（不知→疑→知）必须**不被**判成空转
    A3  相邻章同一签名 ⇒ stall
    A4  同一签名 3 次 ⇒ repeat（1 伏笔、2 回收、3 打转）
    A5  状态倒退要报；标了 reversal 就不报
    A6  对象凭空发明（身世）⇒ ghost_obj
    A7  状态不在闭集（明白）⇒ bad_state
    A8  种类自造（微妙的心理变化）⇒ bad_kind

B 组：层级闸
    B1  L0 事件没用完 ⇒ events_unused
    B2  L0 时序倒退 ⇒ time_back
    B3  L0 每章必须指向主线 ⇒ no_spine
    B4  L1 生人说话 ⇒ ghost_cast
    B5  L1 章事件没人用 ⇒ event_uncovered
    B6  L2 落点引文造假 ⇒ bad_quote（**这是"落点"唯一防伪的查法**）
    B7  L2 落点真引文 ⇒ 全过
    B8  L2 事件编号裸奔 ⇒ event_id_leak
    B9  L3 台词变少 ⇒ speech_lost
    B10 L3 字数超 1.45× ⇒ length
    B11 L3 落点被补细节冲掉 ⇒ beat_lost

C 组：提示词与解析
    C1  四层提示词都带**闭集说明**（否则模型自己造词）
    C2  四层提示词都带**真实反例**（三章只换说法）
    C3  提示词明写"只输出 JSON"
    C4  围栏 JSON 能解析（模型十次有三次包 ```json）
    C5  解析不出来 ⇒ 空骨架（**宽松读、不宽松判**）
    C6  L0 提示词要求事件全覆盖

D 组：执行器
    D1  `better()` 方向：问题少的更优（正反各测）
    D2  问题数相同 ⇒ 不重复变化多的更优（正反各测）
    D3  桩模型一次给出合规结果 ⇒ 四层全过、unsolved 为空
    D4  **桩模型一直空转 ⇒ unsolved 非空**（不许假装过了闸）
    D5  过闸才算完：L1 没过时不许进 L2
    D6  重试提示词里带上了上一次的具体问题
    D7  每层过闸后回调（断点续跑用）
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crew import atelier as A          # noqa: E402
from crew import atelier_run as R      # noqa: E402

PASS = 0
FAIL = 0
FAILS: list[str] = []


def ok(name: str, cond: bool, note: str = '') -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  ✓ {name}' + (f'　〔{note}〕' if note else ''))
    else:
        FAIL += 1
        FAILS.append(name)
        print(f'  ✗ {name}' + (f'　〔{note}〕' if note else ''))


# ── 共用夹具 ──────────────────────────────────────────────────────

def _src() -> A.Source:
    return A.Source(
        title='望江楼', logline='阿九在望江楼认出井里的白绫',
        events=[{'id': 'E1', 'text': '井里捞出白绫', 'tick': '1', 'who': '阿九'},
                {'id': 'E2', 'text': '柳氏逼他认白绫', 'tick': '5', 'who': '柳氏'},
                {'id': 'E3', 'text': '他把壶打翻', 'tick': '9', 'who': '阿九'}],
        scenes=[{'tick': '0.5', 'place': '望江楼·前厅',
                 'present': ['阿九', '柳氏', '沈砚']}],
        lines=[{'who': '阿九', 'text': '这茶是井水泡的？'},
               {'who': '柳氏', 'text': '井里没有月亮，只有白绫。'},
               {'who': '沈砚', 'text': '茶凉了。'}])


def _ch(idx, kind, subj, obj, b, a, evs, *, who=('阿九', '柳氏'), act='承'):
    c = A.Chapter(idx=idx, act=act, title=f'第{idx}夜', spine=f'推进到{idx}',
                  place='望江楼·前厅', present=list(who), events=list(evs),
                  changes=[A.Change(kind, subj, obj, b, a, evs[0])])
    c.beats = [A.Beat('B1', list(who), '想问清井里有什么', '对方只给半句',
                      A.Change(kind, subj, obj, b, a, evs[0]), list(evs))]
    return c


def _good() -> A.Skeleton:
    sk = A.Skeleton(logline='阿九在望江楼认出井里的白绫',
                    spine=['他不知道自己是谁', '柳氏逼他认下白绫'],
                    cast={'阿九': '跑堂', '柳氏': '白衣客', '沈砚': '掌柜'},
                    props=['白绫', '井', '壶'])
    sk.chapters = [
        _ch(1, '信息', '阿九', '白绫', '不知', '疑', ['E1'], act='起'),
        _ch(2, '信息', '阿九', '白绫', '疑', '知', ['E2']),
        _ch(3, '处境', '阿九', '壶', '安', '扰', ['E3'], act='转'),
    ]
    return sk


def _with_text(sk: A.Skeleton) -> A.Skeleton:
    """给每章填上能自证落点的正文（判 L2/L3 用）。"""
    for c in sk.chapters:
        # ⚠ 必须用 `_TEXT`（229 汉字）：字数闸在 200 字以下**故意不下判断**，
        #   第一版这里又手写了一段 60 字的，于是 B10 测的是空气。
        c.draft = _TEXT
        for b in c.beats:
            b.lands = '柳氏在楼梯下立着'
    return sk


# ── A 组 ─────────────────────────────────────────────────────────

def group_a() -> None:
    print('\n── A 变化账本（空转的唯一判据）──', flush=True)
    src = _src()

    # A1 签名只由闭集四槽构成：**before 不进签名**，所以"换个起点"不算新变化
    c1 = A.Change('信息', '阿九', '白绫', '不知', '知')
    c2 = A.Change('信息', '阿九', '白绫', '疑', '知')
    ok('A1 ★★★ 签名只由「kind|subject|obj|after」构成 —— '
       '换个起点（不知→知 / 疑→知）是同一格，不许当成两个变化',
       A.signature(c1) == A.signature(c2) == '信息|阿九|白绫|知',
       A.signature(c1))

    # A2 成对：真推进不许被判空转
    sk = _good()
    ok('A2 ★★★ 成对：**真推进**（不知→疑→知→确证）必须一条都不报',
       A.gates_l0(sk, src) == [], str([p.code for p in A.gates_l0(sk, src)]))

    # A3 相邻章同一签名
    sk2 = A.Skeleton(spine=['x'], cast={'阿九': '', '柳氏': '', '沈砚': ''},
                     props=['白绫'])
    sk2.chapters = [_ch(1, '信息', '阿九', '白绫', '不知', '知', ['E1']),
                    _ch(2, '信息', '阿九', '白绫', '不知', '知', ['E2']),
                    _ch(3, '处境', '阿九', '壶', '安', '扰', ['E3'])]
    codes = [p.code for p in A.gates_l0(sk2, src)]
    ok('A3 ★★★ 相邻两章账本相同 ⇒ `stall`（这就是"三章都在问白绫"的可数形态）',
       'stall' in codes, str(codes))

    # A4 同一签名 3 次
    sk3 = A.Skeleton(spine=['x'], cast={'阿九': '', '柳氏': '', '沈砚': ''},
                     props=['白绫'])
    sk3.chapters = [_ch(1, '信息', '阿九', '白绫', '不知', '知', ['E1']),
                    _ch(2, '信息', '阿九', '白绫', '不知', '知', ['E2']),
                    _ch(3, '信息', '阿九', '白绫', '不知', '知', ['E3'])]
    codes3 = [p.code for p in A.gates_l0(sk3, src)]
    ok('A4 ★★★ 同一变化 3 次 ⇒ `repeat`（1 伏笔、2 回收、3 打转）；'
       '同时报相邻 stall 也正常',
       'repeat' in codes3, str(codes3))

    # A5 状态倒退：报；标 reversal 不报
    c = A.Chapter(idx=1, act='起', spine='x', place='前厅', events=['E1'],
                  changes=[A.Change('信息', '阿九', '白绫', '不知', '确证', 'E1')])
    c.beats = [A.Beat('B1', ['阿九'], 'w', 'o',
                      A.Change('信息', '阿九', '白绫', '不知', '确证', 'E1'), ['E1']),
               A.Beat('B2', ['阿九'], 'w', 'o',
                      A.Change('信息', '阿九', '白绫', '确证', '不知', 'E1'), ['E1'])]
    skx = A.Skeleton(spine=['x'], cast={'阿九': ''}, props=['白绫'])
    skx.chapters = [c]
    reg = [p.code for p in A.gates_l1(skx, src)]
    c.beats[1].change.reversal = True
    reg2 = [p.code for p in A.gates_l1(skx, src)]
    ok('A5 ★★★ 状态倒退（知道→又不知道）⇒ `regress`；'
       '但标了 `reversal` 的**有意反转**不报（好戏不是逻辑错）',
       'regress' in reg and 'regress' not in reg2, f'{reg} / {reg2}')

    # A6 凭空对象
    sk4 = A.Skeleton(spine=['x'], cast={'阿九': ''}, props=['白绫'])
    sk4.chapters = [_ch(1, '信息', '阿九', '身世', '不知', '知', ['E1'])]
    ok('A6 ★★★ 变化对象「身世」推演里没出现过 ⇒ `ghost_obj`'
       '（"细节全部来自本次推演"的底线）',
       'ghost_obj' in [p.code for p in A.gates_l1(sk4, src)], '')

    # A7 状态不在闭集
    sk5 = A.Skeleton(spine=['x'], cast={'阿九': ''}, props=['白绫'])
    sk5.chapters = [_ch(1, '信息', '阿九', '白绫', '不知', '明白', ['E1'])]
    ok('A7 ★★★ 状态「明白」不在闭集 ⇒ `bad_state`（闭集是抗同义词的唯一保证）',
       'bad_state' in [p.code for p in A.gates_l1(sk5, src)], '')

    # A8 种类自造
    sk6 = A.Skeleton(spine=['x'], cast={'阿九': ''}, props=['白绫'])
    sk6.chapters = [_ch(1, '微妙的心理变化', '阿九', '白绫', '不知', '知', ['E1'])]
    ok('A8 ★★★ 种类「微妙的心理变化」⇒ `bad_kind`（开放字段会被用来绕开重复检查）',
       'bad_kind' in [p.code for p in A.gates_l1(sk6, src)], '')


# ── B 组 ─────────────────────────────────────────────────────────

def group_b() -> None:
    print('\n── B 层级闸 ──', flush=True)
    src = _src()

    # B1 事件没用完
    sk = _good()
    sk.chapters = sk.chapters[:2]        # 丢掉用 E3 的第三章
    ok('B1 ★★★ 有事件没被任何一章用掉 ⇒ `events_unused`',
       'events_unused' in [p.code for p in A.gates_l0(sk, src)], '')

    # ★ 成对：**只在拍级用到**的事件也算用掉（否则"章纲没写、拍子里写了"会被误判）
    sk_b = _good()
    sk_b.chapters[0].events = ['E1']
    sk_b.chapters[1].events = ['E2']
    sk_b.chapters[2].events = ['E1']
    for b in sk_b.chapters[2].beats:
        b.events = ['E3']
    ok('B1b ★★★ 成对：**只在拍级被用到**的事件也算用掉'
       '（"章纲没列、拍子里用了"是合法的）',
       'events_unused' not in [p.code for p in A.gates_l0(sk_b, src)],
       str([p.code for p in A.gates_l0(sk_b, src)]))

    # B2 时序倒退
    sk2 = _good()
    sk2.chapters[0], sk2.chapters[2] = sk2.chapters[2], sk2.chapters[0]
    ok('B2 ★★★ 后一章用了更早的事件 ⇒ `time_back`',
       'time_back' in [p.code for p in A.gates_l0(sk2, src)], '')

    # B3 每章指向主线
    sk3 = _good()
    sk3.chapters[1].spine = ''
    ok('B3 ★★ 某章没说它推进主线哪一句 ⇒ `no_spine`',
       'no_spine' in [p.code for p in A.gates_l0(sk3, src)], '')

    # B4 生人说话
    sk4 = _good()
    sk4.chapters[0].beats[0].who = ['路人甲']
    ok('B4 ★★★ 节拍里出现不存在的人 ⇒ `ghost_cast`',
       'ghost_cast' in [p.code for p in A.gates_l1(sk4, src)], '')

    # B5 章事件没人用
    sk5 = _good()
    for b in sk5.chapters[2].beats:
        b.events = []
    ok('B5 ★★ 章分配了事件但没哪一拍用它 ⇒ `event_uncovered`',
       'event_uncovered' in [p.code for p in A.gates_l1(sk5, src)], '')

    # B6 落点引文造假
    sk6 = _with_text(_good())
    sk6.chapters[0].beats[0].lands = '她抬头望着我说，井里有东西。'
    ok('B6 ★★★ 落点引文对不上正文 ⇒ `bad_quote`'
       '（**编出来的引文一定对不上** —— 这是落点唯一防伪的查法）',
       'bad_quote' in [p.code for p in A.gates_l2(sk6, src, chapter=1)], '')

    # B7 真引文
    sk7 = _with_text(_good())
    ok('B7 ★★★ 成对：真引文 ⇒ L2 全过（不许把正常的也拦下来）',
       A.gates_l2(sk7, src, chapter=1) == [],
       str([p.code for p in A.gates_l2(sk7, src, chapter=1)]))

    # B8 事件编号裸奔
    sk8 = _with_text(_good())
    sk8.chapters[0].draft += '他想起 E1 那件事。'
    ok('B8 ★★ 正文里出现事件编号 ⇒ `event_id_leak`',
       'event_id_leak' in [p.code for p in A.gates_l2(sk8, src, chapter=1)], '')

    # B9 台词变少
    sk9 = _with_text(_good())
    sk9.chapters[0].final = sk9.chapters[0].draft.replace('“井里没有月亮。”', '')
    ok('B9 ★★★ 补细节把台词并掉 ⇒ `speech_lost`',
       'speech_lost' in [p.code for p in A.gates_l3(sk9, src, chapter=1)], '')

    # B10 字数超
    sk10 = _with_text(_good())
    sk10.chapters[0].final = sk10.chapters[0].draft * 3
    ok('B10 ★★★ 补细节把字数撑到 3 倍 ⇒ `length`',
       'length' in [p.code for p in A.gates_l3(sk10, src, chapter=1)], '')

    # B12 人名抽取必须数频次（真跑实测：只用"说/问/道前面的字"，
    #     `台后头说` `我正想问` `她只说` 全被当成人名，一次报 7~12 条全误报）
    ok('B12 ★★★ 只出现一次的"X说"**不算人名**（真跑实测：`台后头说`'
       '`我正想问` `她只说` 全被误报，把 L2 卡死）',
       A._person_names('账台旁说了一句。她只说了一个字。我正想问，灯灭了。') == [],
       str(A._person_names('账台旁说了一句。她只说了一个字。我正想问，灯灭了。')))
    ok('B12b ★★★ 成对：**反复出现**的新名字必须报出来（不然这道闸形同虚设）',
       A._person_names('王二说了一句。王二又说了一句。') == ['王二'],
       str(A._person_names('王二说了一句。王二又说了一句。')))

    # B13/B14：真跑撞出来的两条边界（都是"闸太严，把正常写法卡死"）
    sk13 = _good()
    sk13.cast['何二'] = '送炭的'          # cast 里登记名字，节拍里写"身份 + 名字"
    sk13.chapters[0].beats[0].who = ['送炭何二']
    ok('B13 ★★★ 在场人写"身份 + 名字"（送炭何二）**不算生人**'
       '（cast 里登记的是"何二"；严格相等会卡死正常节拍）',
       'ghost_cast' not in [p.code for p in A.gates_l1(sk13, src, chapter=1)], '')

    sk14 = _good()
    sk14.chapters[0].beats[0].change.obj = '井里沉下去的东西'
    codes14 = [p.code for p in A.gates_l1(sk14, src, chapter=1)]
    ok('B14 ★★★ 变化对象写成一句话（井里沉下去的东西）⇒ `obj_too_long`，'
       '而且要**明说该填什么**（「井」）',
       'obj_too_long' in codes14
       and any('井' in p.fix for p in A.gates_l1(sk14, src, chapter=1)
               if p.code == 'obj_too_long'),
       str(codes14))

    # B11 落点被冲掉
    sk11 = _with_text(_good())
    sk11.chapters[0].final = ('灯焰安稳。我把壶搁下，指节收拢。'
                              '沈砚在柜台后理账，算盘珠碰竹档嗒一声。'
                              '“井里没有月亮。”她说。')
    ok('B11 ★★★ 补完细节落点消失 ⇒ `beat_lost`（细节是重写的近亲，'
       '能把结构写没）',
       'beat_lost' in [p.code for p in A.gates_l3(sk11, src, chapter=1)], '')


# ── E 组：章间衔接（真跑实测"第 2 章把第 1 章开场又演一遍"）──────────

def group_e() -> None:
    print('\n── E 章间衔接（不许重演前一章的开场）──', flush=True)
    src = _src()
    sk = _with_text(_good())
    # 第 1 章已经演过：阿九·白绫、阿九·壶、阿九·井
    sk.chapters[0].beats = [
        A.Beat('B1', ['阿九', '柳氏'], '取壶去打水', '夜里看不清',
               A.Change('物', '阿九', '壶', '在', '移'), ['E1']),
        A.Beat('B2', ['阿九'], '看清井里有东西', '灯太暗',
               A.Change('信息', '阿九', '井', '不知', '疑'), ['E1']),
    ]
    # 第 2 章开头把"取壶 + 井里有东西"又演一遍 ⇒ 必须报
    sk.chapters[1].draft = ('掌柜让我去账台小柜把壶取了，到后院井台打新水。'
                            '我提着壶路过，看见井里有东西。'
                            + _TEXT)
    sk.chapters[1].beats = [A.Beat('B1', ['阿九'], '问锁', '她不说',
                                   A.Change('信息', '阿九', '锁', '不知', '知'),
                                   ['E2'], lands='我提着壶路过，看见井里有东西')]
    codes = [p.code for p in A.gates_l2(sk, src, chapter=2)]
    ok('E1 ★★★ 第 2 章开头重演第 1 章两拍（取壶 + 井里有东西）⇒ `replay_open`',
       'replay_open' in codes, str(codes))

    # 成对：只提一处（正常承接）不报
    # ⚠ 不能拼 `_TEXT`：那段自己也含「壶」，会凑成两个物件 ⇒ 假报。
    #   （这就是"夹具自带干扰"的典型 —— 拼接时把别处的对象一起带进来了。）
    sk.chapters[1].draft = '我从账台小柜里把壶提出来，随后问柳氏那锁的事。'
    sk.chapters[1].beats[0].lands = '我从账台小柜里把壶提出来'
    codes2 = [p.code for p in A.gates_l2(sk, src, chapter=2)]
    ok('E2 ★★★ 成对：只提一处（正常承接）**不报**'
       '（"一组"可能只是衔接，两组才是重演）',
       'replay_open' not in codes2, str(codes2))

    # 首章不查（没有前章）
    sk.chapters[0].draft = '我把壶从账台小柜里取出来，随后看见井里有东西。' + _TEXT
    ok('E3 ★★ 第 1 章不查重演（没有前章可比，查了必误报）',
       'replay_open' not in [p.code for p in A.gates_l2(sk, src, chapter=1)], '')

    # 提示词必须把"前面演过什么"给 L2
    p2 = R.prompt_l2(src, sk, sk.chapters[1])
    ok('E4 ★★★ L2 提示词里带**前章已演内容**（不给，它就会为了"接上"再演一遍）',
       '前面几章已经演到哪' in p2 and '已演' in p2, '')
    ok('E5 ★★★ 而且明写"不许重演"（不是靠模型自己领会）',
       '不许重演' in p2 and '同一场开场写两遍' in p2, '')
    ok('E6 ★★ 第一章的提示词说"这是第一章"（不许凭空造一个"前章"）',
       '这是第一章' in R.prompt_l2(src, sk, sk.chapters[0]), '')


# ── C 组 ─────────────────────────────────────────────────────────

def group_c() -> None:
    print('\n── C 提示词与解析 ──', flush=True)
    src = _src()
    sk = _good()
    ch = sk.chapters[0]
    ps = [R.prompt_l0(src), R.prompt_l1(src, sk, ch),
          R.prompt_l2(src, sk, ch), R.prompt_l3(src, sk, ch)]
    # ⚠ 只有 **L0 / L1 写账本**：L2/L3 不写 `Change`，把闭集塞进去只是噪声
    #   （第一版断言"四层都要"，红了两次才想明白该管的是谁）。
    _ledger_layers = ps[:2]
    ok('C1 ★★★ 写账本的两层（L0/L1）都带**闭集**说明'
       '（不给闭集，模型一定自己造词）',
       all('不知' in p and '确证' in p for p in _ledger_layers), '')
    ok('C2 ★★★ 这两层都带**真实反例**（三章只换说法那段）',
       all('换个说法不算推进' in p for p in _ledger_layers), '')
    ok('C3 ★★ 都明写"只输出 JSON"（否则模型会加一段解释，解析必挂）',
       all('只输出一个 JSON' in p for p in ps), '')
    ok('C2b ★★★ 不写账本的两层（L2/L3）必须带**自己的**硬约束：'
       'L2 要求"每拍落点自证"、L3 要求"台词一句都不许少"',
       '逐字照抄' in ps[2] and '台词一句都不许少' in ps[3], '')

    ok('C4 ★★ 只有事实、没有结构泄漏：L0 提示词里不含任何章节树'
       '（骨架是**生成**的，不是给的）',
       '第 1 章〔' not in R.prompt_l0(src), '')

    raw = ('好的，这是骨架：\n```json\n' + json.dumps({
        'logline': 'x', 'spine': ['a'], 'cast': {'阿九': '跑堂'},
        'props': ['白绫'], 'chapters': [{'idx': 1, 'act': '起', 'events': ['E1'],
                                         'changes': [{'kind': '信息', 'subject': '阿九',
                                                      'obj': '白绫', 'before': '不知',
                                                      'after': '疑'}]}]},
        ensure_ascii=False) + '\n```\n希望有帮助。')
    sk2 = R.parse_l0(raw)
    ok('C5 ★★★ 围栏 + 前后缀都能解析（模型十次有三次这么回）',
       len(sk2.chapters) == 1 and sk2.chapters[0].changes[0].after == '疑', '')
    ok('C6 ★★★ 解析不出来 ⇒ **空骨架**（宽松读、不宽松判：挖不出就是挖不出，'
       '交给闸去打回）',
       R.parse_l0('抱歉，我无法完成。').chapters == []
       and R.parse_l1('{}') == [], '')
    ok('C7 ★★ L0 提示词要求"每件事都要被用掉"（否则推演里的事会漏）',
       '每件事都要被用掉' in R.prompt_l0(src), '')


# ── D 组 ─────────────────────────────────────────────────────────

def _pay(kind_after: str) -> str:
    """造一个合规的 L0 返回。"""
    return json.dumps({
        'logline': '阿九在望江楼认出井里的白绫',
        'spine': ['他不知道自己是谁', '柳氏逼他认下白绫'],
        'cast': {'阿九': '跑堂', '柳氏': '白衣客', '沈砚': '掌柜'},
        'props': ['白绫', '井', '壶'],
        'chapters': [
            {'idx': 1, 'title': '第七夜', 'act': '起', 'spine': '承接"不知道"',
             'place': '望江楼·前厅', 'present': ['阿九', '柳氏'],
             'events': ['E1'],
             'changes': [{'kind': '信息', 'subject': '阿九', 'obj': '白绫',
                          'before': '不知', 'after': '疑'}]},
            {'idx': 2, 'title': '第八夜', 'act': '承', 'spine': '推进到"要认"',
             'place': '望江楼·前厅', 'present': ['阿九', '柳氏'],
             'events': ['E2'],
             'changes': [{'kind': '信息', 'subject': '阿九', 'obj': '白绫',
                          'before': '疑', 'after': kind_after}]},
            {'idx': 3, 'title': '第九夜', 'act': '转', 'spine': '推进到"失手"',
             'place': '望江楼·前厅', 'present': ['阿九', '沈砚'],
             'events': ['E3'],
             'changes': [{'kind': '处境', 'subject': '阿九', 'obj': '壶',
                          'before': '安', 'after': '扰'}]},
        ]}, ensure_ascii=False)


def _beats_payload(kind_after: str) -> str:
    return json.dumps({'chapter': 2, 'beats': [
        {'id': 'B1', 'who': ['阿九', '柳氏'], 'want': '想问清白绫',
         'obstacle': '她只说半句', 'events': ['E2'],
         'change': {'kind': '信息', 'subject': '阿九', 'obj': '白绫',
                    'before': '疑', 'after': kind_after}},
        {'id': 'B2', 'who': ['阿九'], 'want': '把壶放下',
         'obstacle': '手抖', 'events': ['E2'],
         'change': {'kind': '处境', 'subject': '阿九', 'obj': '壶',
                    'before': '安', 'after': '扰'}},
    ]}, ensure_ascii=False)


# ⚠ 这段必须 ≥200 汉字：`gates_l3` 的字数比在 200 字以下**故意不下判断**
#   （短样本文数比全是噪声）。第一版夹具只有 70 字，于是"撑到 3 倍"也判不出来 ——
#   不是代码错，是夹具没进到那道闸的工作区间。
_TEXT = ('我立在柜边擦桌子，粗布顺着木纹来回推，纹路里嵌的旧年茶渍慢慢化开。'
         '灯焰安稳，照得梁上漆色微黄。柳氏在楼梯下立着，裙角挨着阶沿，'
         '指头在袖口里捻着什么，捻一下停一下。'
         '“井里没有月亮。”她说。声音不高，正够这一屋子人听见。'
         '我把壶搁下，指节收拢，掌心留下一圈凉。'
         '灶间柴火塌了一下，细响过后又是雨声。'
         '沈砚在柜台后理账，算盘珠碰竹档嗒一声，清脆里带些沉闷的回音。'
         '我抬眼去看那盏灯，灯芯结了一小朵花，没人去剪。'
         '门外的风把纸门推得半开，又退回去。'
         '檐角铜铃晃了半下，又歇了。雨丝在窗纸上拖出长长短短的影。'
         '我把抹布擰了一遍，水落在盆里，声音很轻。')


def _text_payload(chapter: int) -> str:
    return json.dumps({'chapter': chapter, 'draft': _TEXT,
                       'lands': {'B1': '柳氏在楼梯下立着',
                                 'B2': '柳氏在楼梯下立着'}},
                      ensure_ascii=False)


def group_d() -> None:
    print('\n── D 执行器 ──', flush=True)
    src = _src()

    # D1/D2 方向：**正反各测一次**（`better` 写反过一次，取到最差那版）
    good = _good()
    bad = _good()
    for c in bad.chapters:
        c.changes = [A.Change('信息', '阿九', '白绫', '不知', '知')]
    kg = R.key_of(good, src, 'L0')
    kb = R.key_of(bad, src, 'L0')
    ok('D1 ★★★ `better()` 方向：**问题少的更优**（正反各测）',
       R.better(kg, kb) and not R.better(kb, kg), f'{kg} vs {kb}')

    # 造一对"问题数相同、不重复变化数不同"的候选：
    # 两者都漏一个事件（1 条问题），但 A 三章三个变化、B 三章只有两个变化。
    # A：三章三个变化；B：同样三章，但多一拍、多一个变化（都是 0 条问题）。
    # ⚠ 不能用"漏事件"造问题：`events_unused` 会让变化数一起变，两个变量混在一起。
    a2 = _good()
    b2 = _good()
    # ⚠ 必须加在 `changes`（章级账本）上：`coverage` 数的是章级签名，
    #   加一个"多出来的拍"不会改变章级签名数（第一版就是这么白测的）。
    # 加一拍、给一个**新的**变化（章级代表不变，但全书变化更丰富）
    b2.chapters[0].beats.append(A.Beat(
        'B2', ['柳氏'], '把白绫掩回袖里', '手抖',
        A.Change('关系', '柳氏', '白绫', '疏', '试'), ['E1']))
    ka, kb2 = R.key_of(a2, src, 'L0'), R.key_of(b2, src, 'L0')
    ok('D2 ★★★ 问题数相同时，**不重复变化多的更优**（键里第二项取负；'
       '写反过一次，取到最差那版）',
       ka[0] == kb2[0] == 0 and kb2[1] < ka[1]
       and R.better(kb2, ka) and not R.better(ka, kb2),
       f'A={ka} B={kb2}')

    # D3 桩模型一次给合规结果
    calls: list[str] = []

    # ⚠ 桩必须**按章**作答：第一版对每一章都返回"第 2 章"的节拍，
    #   于是第 1 章的事件没人用 ⇒ `event_uncovered`（是夹具错，不是代码错）。
    def _chapter_in(prompt: str) -> int:
        for k in ('第 2 章', '第 3 章', '第 1 章'):
            if k in prompt:
                return int(k[2])
        return 1

    def _evs_in(prompt: str) -> list[str]:
        import re as _re
        m = _re.search(r'本章要用掉的事件：([E\d、]+)', prompt)
        return [x for x in (m.group(1).split('、') if m else []) if x]

    async def ask_ok(prompt, tier, purpose):
        calls.append(purpose)
        if purpose == 'atelier_L0':
            return _pay('知')
        if purpose == 'atelier_L1':
            evs = _evs_in(prompt) or ['E1']
            return json.dumps({'chapter': _chapter_in(prompt), 'beats': [
                {'id': 'B1', 'who': ['阿九', '柳氏'], 'want': '想问清白绫',
                 'obstacle': '她只说半句', 'events': evs[:1],
                 'change': {'kind': '处境', 'subject': '阿九', 'obj': '壶',
                            'before': '安', 'after': '扰'}}]},
                ensure_ascii=False)
        return _text_payload(_chapter_in(prompt))

    sk, left = asyncio.run(R.compose(ask_ok, src, chapters=3, rounds=2, n_best=1))
    ok('D3 ★★★ 桩模型一次给合规结果 ⇒ 四层全过、`unsolved` 为空，'
       '而且**返回的骨架里真的有节拍和正文**'
       '（别名 bug 会让节拍写进原骨架、返回的副本里空空如也）',
       left == [] and len(sk.chapters) == 3
       and all(c.beats for c in sk.chapters)
       and all(c.draft or c.final for c in sk.chapters), f'{left}')

    # D4 桩模型一直空转 ⇒ 必须报出来
    async def ask_stall(prompt, tier, purpose):
        if purpose == 'atelier_L0':
            return json.dumps({
                'logline': 'x', 'spine': ['x'], 'cast': {'阿九': '', '柳氏': '',
                                                         '沈砚': ''},
                'props': ['白绫'],
                'chapters': [
                    {'idx': 1, 'act': '起', 'spine': 'x', 'place': '前厅',
                     'events': ['E1'], 'changes': [
                         {'kind': '信息', 'subject': '阿九', 'obj': '白绫',
                          'before': '不知', 'after': '知'}]},
                    {'idx': 2, 'act': '承', 'spine': 'x', 'place': '前厅',
                     'events': ['E2'], 'changes': [
                         {'kind': '信息', 'subject': '阿九', 'obj': '白绫',
                          'before': '不知', 'after': '知'}]},
                    {'idx': 3, 'act': '转', 'spine': 'x', 'place': '前厅',
                     'events': ['E3'], 'changes': [
                         {'kind': '信息', 'subject': '阿九', 'obj': '白绫',
                          'before': '不知', 'after': '知'}]},
                ]}, ensure_ascii=False)
        return '（我是模型，我只会换个说法）'

    sk2, left2 = asyncio.run(R.compose(ask_stall, src, chapters=3,
                                       rounds=1, n_best=1))
    ok('D4 ★★★ **桩模型一直空转 ⇒ `unsolved` 非空**'
       '（不许假装过了闸 —— 吞掉问题就等于回到"写完再挑毛病"）',
       bool(left2) and any('stall' in x or 'repeat' in x for x in left2),
       f'{left2[:2]}')

    # D5 过闸才算完：L1 没过时不许进 L2
    seq: list[str] = []

    async def ask_gate(prompt, tier, purpose):
        seq.append(purpose)
        if purpose == 'atelier_L0':
            return _pay('知')
        if purpose == 'atelier_L1':
            # ⚠ 节拍必须**覆盖本章事件**，所以这里把事件留空 ⇒
            #   每一章都 `event_uncovered` ⇒ L1 章章不过。
            #   第一版只让它"状态倒退"，而倒退是**章内比较**，
            #   第 2 章碰巧没有可比的上一拍 ⇒ 那一章居然过了、L2 被调用，
            #   判据就红得莫名其妙。（这是"夹具只拦住了一部分"的老毛病。）
            return json.dumps({'chapter': 1, 'beats': [
                {'id': 'B1', 'who': ['阿九'], 'want': '问', 'obstacle': '她不说',
                 'events': [],
                 'change': {'kind': '信息', 'subject': '阿九', 'obj': '白绫',
                            'before': '不知', 'after': '疑'}}]},
                ensure_ascii=False)
        return _text_payload(2)

    asyncio.run(R.compose(ask_gate, src, chapters=3, rounds=1, n_best=1))
    ok('D5 ★★★ L1 永远过不了闸时，**L2 一次都不该被调用**'
       '（"没问题了再继续"这句话在代码里的样子）',
       'atelier_L2' not in seq, str(sorted(set(seq))))

    # D6 重试提示词里带上一次的具体问题
    prompts: list[str] = []

    async def ask_retry(prompt, tier, purpose):
        prompts.append(prompt)
        if purpose == 'atelier_L0':
            n = sum(1 for p in prompts if p == prompt)
            return _pay('知') if n >= 2 else json.dumps({
                'logline': 'x', 'spine': ['x'], 'cast': {}, 'props': [],
                'chapters': []}, ensure_ascii=False)
        return ''

    asyncio.run(R.compose(ask_retry, src, chapters=1, rounds=2, n_best=1))
    ok('D6 ★★★ 重试提示词里带着**上一次的具体问题**'
       '（不是"请改进"那种模型看不懂的话）',
       any('上一次被打回的原因' in p and 'L0/' in p for p in prompts), '')

    # D7 每层过闸后回调
    saved: list[str] = []

    async def ask_ok2(prompt, tier, purpose):
        # 复用 D3 那个**按章作答**的桩（每章返同一份节拍会让别的章卡在 L1）
        return await ask_ok(prompt, tier, purpose)

    asyncio.run(R.compose(ask_ok2, src, chapters=3, rounds=1, n_best=1,
                          save=lambda layer, sk: saved.append(layer)))
    ok('D7 ★★ 每层过闸后都回调（断点续跑：崩了不用从头再来）',
       saved[:1] == ['L0'] and {'L1', 'L2', 'L3'} <= set(saved), str(saved))


def main() -> int:
    print('=' * 72)
    print('分层创作（atelier）判据')
    print('=' * 72)
    for fn in (group_a, group_b, group_c, group_d, group_e):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f'{fn.__name__} 执行失败（崩溃也算不通过）', False, repr(e))
    print('\n' + '=' * 72)
    print(f'  验证：{PASS}/{PASS + FAIL} 条通过')
    if FAIL:
        print('  红了：')
        for x in FAILS:
            print(f'    · {x}')
    print('=' * 72)
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
