# -*- coding: utf-8 -*-
"""**剧情卡住**：判定与分级处置 —— 在推演层做，不在文本层做。

★★★ 为什么必须换到这一层
========================
2026-10-20 夜，围绕望江楼那篇"剧情在原地打转"试过三条路，**全部失败**，
而且失败的方式各不相同 —— 记在这里免得下一轮再走：

| 试过的层 | 可数的量 | 为什么不行 |
|---|---|---|
| 句子层（`global_checks.echo_phrase`） | 3~6 字短语在几句台词里出现 | **真人 4 篇命中、最高比例 0.88，望江楼只有 0.44** —— 真人比真跑更像病 |
| 派活文本（`director.engine.assignment_shared`） | 两件派活共享几个二元组 | 共享 **3** 可能是真推进（"拿准主意"→"定下并传令"），共享 **7** 可能只是换词（"因紫砂壶浮起旧忆"→"从所持壶上浮起旧忆"）⇒ **字面相似度不是"重复"的量** |
| 日志四元组（本文件第一版） | 空间/人物/目标/事件类型 | 日志只记场景级的 3–7 拍，粒度太粗，最长停滞全 ≤2，**分不开** |

三次失败的共同点：都在问"**这两句话/这两件活像不像**"。
而真正的问题不是"像不像"，是"**世界有没有变**"。

★★★ 所以这一层只做一件事：给每一拍算一个**状态指纹**
====================================================
    空间 + 在场人物 + 每人手上那件事 + 这一段在谈什么

四样**全部逐字相同** ⇒ 这一拍世界什么都没变 ⇒ 下一拍必然重复上一拍。
它数的是"**世界那四样有没有变**"，不是"两句话像不像"。但要说清边界：
  · 目标**换了内容**（"弄清"→"说出"）⇒ 指纹变 ⇒ 算它动了（那是真推进）；
  · 目标**换成同义说法**（"弄清"→"搞明白"）⇒ 指纹**不许变** ⇒ 仍算没动
    （由 `_goal_key` 归并；不归并的话换个说法就能骗过指纹，实测过）；
  · 话题/在场人/空间任何一样变了 ⇒ 算它动了（那才是真推进）。

**这正是"有意复现"与"卡住"的分界线**：
  · 有意复现（闪回、回忆、重演）**至少会换一样** —— 换空间（回到那年）、
    换在场人（换成当年的证人）、换话题（"后来我才知道"）。
    作者真要复现，一定会给读者一个"这是另一层时间"的信号，那个信号就是指纹的变化。
  · 卡住是**四样全不动**，只有字数在涨。

⚠ 这一层**不判"该不该复现"**，只在"连续 N 拍什么都不变"时**换一个变量**。
  换变量不是改内容、不是删句子 —— 它只改**推演的输入**
  （这一拍该发生哪类事 / 谁该动），所以它不违反"事实一个字不许改"。

分级处置（三档，越往后越硬）
----------------------------
| 连拍数 | 档 | 做什么 | 为什么是这一档 |
|---|---|---|---|
| ≥3 | `vary` | **下一拍换事件类型**（不许连着用同一类） | 最轻的干预：只换"哪类事"，不动人、不动地方 |
| ≥5 | `shift` | **换人**：写 `watch_note` 让某一拍必须有一个人进场或离场 | 人换了，他带进来的信息就变了 |
| ≥8 | `settle` | 走**已有的**僵局结算通道（`request_settle`） | 项目 2026-10-19 就建好了，这里只是把它接到"状态不动"这个信号上 |

⚠ 三档都用**已有的**设施，不新造机制。新造的东西没人维护（这个项目的原话）。

[EN] Where the stall is judged: on **world state**, not on text. Three attempts at the
[EN] text layer all failed (measured; see the table above) because they all asked "do these
[EN] two lines look alike", while the real question is "did the world change". So each beat
[EN] gets a fingerprint of scene + cast + per-person mission + topic: if none of the four
[EN] moved, the next beat can only repeat this one. Deliberate re-enactment always moves at
[EN] least one of them (scene / cast / topic) -- that is what separates it from being stuck.
[EN] Escalation reuses existing machinery: vary the event type (3), shift the cast (5),
[EN] settle (8).
"""
from __future__ import annotations

import hashlib
import logging
import re

_LOG = logging.getLogger(__name__)

#: 三档阈值。**数字是量出来的，不是拍的**：
#:   · 3 —— 两拍不动可以是一次呼吸（人沉默一回合是正常的）；**连续三拍**不动，
#:     读者已经能感觉到"他们又来了"；
#:   · 5 —— 五拍是一整场戏的长度（实测每场 6~8 拍），整场没动就是一场废戏；
#:   · 8 —— 超过一场，必须结算（这正是 `STALL_BREAK_BEATS` 默认 3 的那条通道，
#:     这里用更长的阈值，因为它测的是"世界状态"，比"没人动"更严）。
# [EN] Thresholds are measured: two identical beats can be one breath; three in a row and
# [EN] the reader already notices. Five is a whole scene (measured 6-8 beats/scene).
VARY_AT = 3
SHIFT_AT = 5
SETTLE_AT = 8

#: 指纹只取这几样。**不要往里加"情绪""张力"这类连续量** ——
#: 它们每一拍都在微小变化，加进去指纹永远在变，这条判据就废了。
_FIELDS = 3


def _norm(text: str) -> str:
    """归一：去掉空白与标点，只留汉字与字母数字。

    ⚠ 不能只 strip()：派活文本里"让阿九，因紫砂壶…"与"让阿九因紫砂壶…"
      只差一个逗号，**必须算同一件** —— 否则换个标点就骗过指纹。
    """
    return re.sub(r'[\s\u3000，。、；：！？,.;:!?「」“”"\'（）()]', '',
                  str(text or ''))


#: ★★★ **目标归一**（2026-10-20 深夜补，实测发现指纹在这里漏了同义词）。
#:
#: 指纹的"每人手上那件事"用的是**派活文本**，而派活是模型写的 ——
#: 同一个目标换个说法（"弄清白绫的来历" / "搞明白那条白绫是从哪来的"），
#: 字面不同 ⇒ 指纹不同 ⇒ 被算成"世界动了"，**于是卡住反而更难被发现**。
#: 实测：这一对说法给出的指纹不同，"同义改写"被误判成推进。
#:
#: 只归并三样，**不碰对象**（对象变了就是真推进）：
#:   · 目标动词族（弄清/搞明白/查明 …）—— 同一个意思
#:   · "来历"这一类对象同义（从哪来/哪儿来/出处 …）
#:   · 追问族（盘问/逼问/追问 …）
#: 另加两条**通用**清理：指示词+量词（那只壶 → 壶）、结构助词"的"。
#: ⚠ 不许把"说出/承认"并进"弄清"：那是两件不同的事（一个是查到，一个是交出去）。
#: [EN] Goal normalisation. The mission slot uses **free text written by the model**, so the
#: [EN] same goal re-worded produced a different fingerprint and counted as progress --
#: [EN] measured, and it makes a stall *harder* to catch. Only verb families and
#: [EN] "where-it-came-from" synonyms are merged; the object itself is never touched.
_GOAL_SYN = (
    (re.compile(r'搞明白|搞懂|搞清|弄明白|弄清楚|弄懂|查明|查清|问清|打听'), '弄清'),
    (re.compile(r'从哪来|哪儿来|哪里来|从何处来|怎么来的|打哪来'), '来历'),
    (re.compile(r'盘问|逼问|追问|追着问|再问一遍'), '追问'),
)
#: 指示词 + 量词（"那只壶"/"那条白绫" 与 "壶"/"白绫" 指同一件东西）
_DEM_MEASURE = re.compile(
    r'(?:这|那)(?:一)?(?:条|只|个|把|张|支|件|块|盏|壶|杯|碗|根|枚|片|位|名)')


def _goal_key(mission: str) -> str:
    """把"派活文本"收成一个**对同义改写不敏感**的键。"""
    out = _norm(mission)
    for rx, canon in _GOAL_SYN:
        out = rx.sub(canon, out)
    out = _DEM_MEASURE.sub('', out)
    # "是"只当系动词出现（"是从哪来的"），去掉不改目标的意思。
    return out.replace('的', '').replace('是', '')


def _missions(world) -> tuple[str, ...]:
    """每人手上那件事，**并上"还没办成"这个状态**。

    ⚠ 带上 `mission_stuck` 是有意的：同一件事办了很久（`mission_stuck` 在涨）
      说明**他在原地磨**，也属于"世界没动"。只看任务文本会漏掉这种。
    """
    out = []
    for name in sorted((getattr(world, 'people', None) or {})):
        ps = world.people.get(name)
        try:
            if str(getattr(ps, 'status', '') or '') == '死亡':
                continue
            if not ps.is_active():
                continue
        except Exception:                                        # noqa: BLE001
            continue
        # ★ 用 `_goal_key` 而不是 `_norm`：否则"换个说法"会被算成"推进"。
        mission = _goal_key(getattr(ps, 'mission', '') or '')
        # ⚠ 磨了 3 轮以上才计入，前两轮不算（那是正常推进的耗时）
        grind = int(getattr(ps, 'mission_stuck', 0) or 0) // 3
        out.append(f'{name}={mission}~{grind}')
    return tuple(out)


def fingerprint(world) -> str:
    """这一拍世界状态的指纹（12 位十六进制）。**纯函数，零模型调用。**

    四样：场景 / 在场人物 / 每人手上那件事 / 这一段在谈什么。
    取 `topic` 而不取"最近台词"：台词每句都不同，取它等于指纹永远在变。
    `topic` 是**这一段在讨论的那件事**（`director.supervisor` 算出来的引文），
    它不变 = 还在同一个话题上打转。
    """
    parts = [
        _norm(getattr(world, 'scene', '') or ''),
        '|'.join(sorted(_on_stage(world))),
        '|'.join(_missions(world)),
        _norm(getattr(world, 'topic', '') or '')[:40],
    ]
    raw = '\u0001'.join(parts)
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]


def _on_stage(world) -> list[str]:
    try:
        return [str(x) for x in (world.on_stage_names() or ())]
    except Exception:                                            # noqa: BLE001
        return []


def note(world) -> int:
    """**每拍末调一次**：更新指纹与连拍数，返回"连续几拍没变"。

    返回 0 表示这一拍世界动了（或第一次算）。
    ⚠ 任何异常都吞掉并返回 0 —— 它是**观察器**，不许影响推演本身。
    """
    try:
        cur = fingerprint(world)
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('状态指纹算不出来（当这一拍动了）：%r', e)
        return 0
    prev = str(getattr(world, 'beat_fingerprint', '') or '')
    # ★ 计数的语义 = **"连续几拍（含本拍）世界完全一样"**，不是"与上一拍相同的次数"。
    #   第一版写成"+1 次"，于是 `VARY_AT=3` 实际要到**第 4 拍**才触发，
    #   而日志会说"连续 3 拍"—— 数字与话差一拍，读日志的人会算不出来。
    #   ⇒ 首拍记 1；与上一拍相同则 +1；不同则归 1。
    # [EN] The counter means "how many beats in a row (this one included) look identical",
    # [EN] not "how many times it matched the previous beat". Off by one otherwise.
    if prev and prev == cur:
        n = int(getattr(world, 'stall_beats', 0) or 0) + 1
    else:
        n = 1
    try:
        world.beat_fingerprint = cur
        world.stall_beats = n
    except Exception:                                            # noqa: BLE001
        pass
    # ★ 到第 2 拍就报一次（`info`）：这是"**机制活着、在数**"的唯一可见证据。
    #   只报 3/5/8 的话，一次"世界一直在变"的跑和一次"机制根本没跑"的跑
    #   在日志上**完全一样** —— 那就没法判断它有没有在工作。
    #   第 2 拍是自然的观察点：它说明"已经连着两拍一样了，但还没到处置档"。
    # [EN] Report at the second beat too: otherwise "the world changed every beat" and
    # [EN] "the mechanism never ran" look identical in the log.
    if n == 2:
        _LOG.info('状态停滞：连续 %d 拍世界没有变化（还没到处置档，先记下）', n)
    elif n and n in (VARY_AT, SHIFT_AT, SETTLE_AT):
        _LOG.info('状态停滞：连续 %d 拍世界没有任何变化（空间/在场人/手上事/话题全同）'
                  ' ⇒ 按档位处置：%s', n, level(n))
    return n


def level(n: int) -> str:
    """连拍数 → 档位名（空串 = 还没到任何一档）。"""
    if n >= SETTLE_AT:
        return 'settle'
    if n >= SHIFT_AT:
        return 'shift'
    if n >= VARY_AT:
        return 'vary'
    return ''


def why(n: int) -> str:
    """给人看的一句话（进日志 / 反思记录）。"""
    if n >= SETTLE_AT:
        return (f'连续 {n} 拍世界没变（超过一整场戏）—— 这一段不是"慢"，是**没有发生任何事**；'
                '走僵局结算：给这个悬置强制一个结果')
    if n >= SHIFT_AT:
        return (f'连续 {n} 拍世界没变 —— 该换人了：让一个人进场或离场，'
                '他带来的信息会让这一场重新有方向')
    if n >= VARY_AT:
        return (f'连续 {n} 拍世界没变 —— 下一拍不要再用同一类事'
                '（连着三次"又有人上门"读者会合上书）')
    return ''


def pick_type(pressures, last_type: str = '', *, exclude_recent: int = 1) -> str:
    """从四条压力里挑一条 ⇒ 事件类型，**但尽量避开上一拍用过的那个**。

    这就是 `vary` 档的处置本体。三个约束按顺序：
      ① 全低 ⇒ 返回空串（这一拍本来就该安静，不许硬凑）；
      ② 最大那条**与上一拍同类型**且还有别的够门槛的 ⇒ **换次大**的那条；
      ③ 换完之后仍然全低 ⇒ 返回空串。

    ★★★ 为什么不改 `Pressures.top()` 本身：那是十几轮真跑调出来的
      （`MIN_PRESSURE` 门槛、"全低返回空"这些边界都有实测依据）。
      在这里包一层"去重"，出问题时**一眼能看出是去重造成的**
      （日志会写"换了次大"），而不是所有跑的事件分布一起变。
    ⚠ `exclude_recent` 只是"尽量"：如果只有一类够门槛，仍然用它 ——
      **宁可连着同类，也不能凭空造出一个低压力的事**（那会让推演不可解释）。
    [EN] Pick an event type from the four pressures, avoiding the previous beat's type when
    [EN] another candidate clears the threshold. Wrapping (rather than editing `top()`) keeps
    [EN] the change attributable: the log says "switched to the runner-up".
    """
    try:
        if pressures is None:
            return ''
        d = pressures.as_dict() if hasattr(pressures, 'as_dict') else dict(pressures)
        from director.pressure import MIN_PRESSURE, PRESSURE_EVENT
    except Exception:                                            # noqa: BLE001
        return ''
    ranked = sorted(d.items(), key=lambda kv: -float(kv[1] or 0))
    if not ranked:
        return ''
    top_key, top_val = ranked[0]
    if float(top_val or 0) < MIN_PRESSURE:
        return ''
    if last_type and PRESSURE_EVENT.get(top_key) == last_type and exclude_recent:
        for k, v in ranked[1:]:
            if float(v or 0) < MIN_PRESSURE:
                break
            if PRESSURE_EVENT.get(k) != last_type:
                _LOG.info('状态停滞：这一拍原本还是「%s」，换次大的「%s」（%.2f → %.2f）',
                          last_type, PRESSURE_EVENT.get(k), float(top_val), float(v))
                return PRESSURE_EVENT.get(k, '')
    return PRESSURE_EVENT.get(top_key, '')


def shift_hint(world, n: int) -> str:
    """`shift` 档的处置：给下一拍写一条"必须换人"的导演提示。

    写进 `world.watch_note`（**已有的**跨拍传参通道，`agent/core` 读完即清），
    不新造字段、不直接改提示词。
    """
    if n < SHIFT_AT:
        return ''
    on = _on_stage(world)
    off = []
    try:
        off = [x for x in (world.off_stage_names() or ()) if x not in on]
    except Exception:                                            # noqa: BLE001
        pass
    who = '、'.join(off[:3]) if off else '一个还没有进过这场戏的人'
    return (f'这一场已经连着 {n} 拍没有任何变化（同一个人、同一件事、同一个话题）。'
            f'**下一拍必须有一个人进出**：让在场的一个离开，或者让{who}进来。'
            '换人不许只为打断而打断 —— 进来的人要带着一件在场的人还不知道的事。')


def note_and_hint(world) -> tuple[int, str]:
    """`note()` + 到 `shift` 档时顺带写好提示。返回 `(连拍数, 档位)`。"""
    n = note(world)
    if level(n) == 'shift' or level(n) == 'settle':
        hint = shift_hint(world, n)
        if hint:
            try:
                world.watch_note = hint
            except Exception:                                    # noqa: BLE001
                pass
    return n, level(n)


__all__ = ['fingerprint', 'note', 'level', 'why', 'pick_type', 'shift_hint',
           'note_and_hint', 'VARY_AT', 'SHIFT_AT', 'SETTLE_AT']
