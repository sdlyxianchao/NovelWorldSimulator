# -*- coding: utf-8 -*-
"""分层创作的**执行器**：四个阶段 + 逐层过闸 + 带教训重写。

与 `crew/atelier.py` 的分工（**别混**）
------------------------------------
| 模块 | 管什么 | 有没有模型 |
|---|---|---|
| `crew/atelier.py` | 数据模型 / 变化账本 / 四道闸 / 导图 | **零调用**，纯函数 |
| 本模块 | 四层提示词 / 解析 / 重试 / 选优 | 每层一次调用（best-of-N） |

★★★ 为什么每层都要"过闸才算完"
----------------------------
用户的要求是「每完成一个步骤都确认没有剧情空转、逻辑错误，没问题了再继续」。
这句话在代码里必须落成一句硬的：**闸返回非空 ⇒ 这一层不算完，不许进下一层。**
不许"先记下来，后面一起修" —— 那正是旧流程（写完再挑毛病）失败的原因。

★★★ 重试时给什么
----------------
给**具体哪一条不过 + 原句**，不给"请改进"。这是本项目反例法的老规矩：
"注意结构"这种话模型看不懂，`第 2 章与第 3 章的变化完全相同（信息|阿九|白绫|知）`
它看得懂。

★ 选优用确定性键：`(问题数, -不重复变化数)` —— 问题少的赢；问题一样多时，
  **变化更丰富的赢**。⚠ 方向写反过一次（`verdict.better` 曾写成 `kb < ka`，
  取到最差那版），所以这里的方向由判据正反各测一次钉住。
"""
from __future__ import annotations

import json
import logging
import re

from crew import atelier as A

_LOG = logging.getLogger(__name__)

__all__ = ['prompt_l0', 'prompt_l1', 'prompt_l2', 'prompt_l3', 'prev_summary',
           'parse_l0', 'parse_l1', 'parse_l2', 'parse_l3',
           'better', 'key_of', 'compose', 'LESSON_CAP']

#: 每层的教训记忆上限（有界，防止提示词越滚越长）。
LESSON_CAP = 6

#: 状态闭集的**人话解释** —— 模型要靠这个选值，光给代码里的元组它不知道含义。
STATE_HINT = (
    '信息：不知 → 疑 → 知 → 确证（谁知道/确认了什么）\n'
    '关系：疏 → 试 → 逼 → 破（两个人的关系被推到哪一步）\n'
    '处境：安 → 扰 → 危 → 失（一个人的处境恶化到哪一步）\n'
    '物　：在 → 移 → 失 → 毁（一件东西被挪到哪一步）'
)


# ══════════════════════════════════════════════════════════════════
# 提示词
# ══════════════════════════════════════════════════════════════════

def _facts(src: A.Source) -> str:
    L = [f'作品：{src.title or "（未命名）"}']
    if src.logline:
        L.append(f'一句话：{src.logline}')
    if src.cast:
        L.append('人物：' + '、'.join(f'{k}{"（" + v + "）" if v else ""}'
                                     for k, v in src.cast.items()))
    L.append('\n【这一夜真实发生过的事（事件）】')
    if src.events:
        for e in src.events:
            L.append(f'  {e["id"]}　{e["text"]}'
                     + (f'（{e["tick"]}，{e["who"]}）' if e.get('who') else ''))
    else:
        L.append('  （没有 event —— 只许写过程稿里出现过的动作与对话）')
    if src.scenes:
        L.append('\n【场景】')
        for s in src.scenes:
            L.append(f'  {s.get("place", "")}'
                     + (f'　在场：{"、".join(s.get("present") or ())}'
                        if s.get('present') else ''))
    if src.lines:
        L.append('\n【真实说过的台词（可以引用，不许改写）】')
        for x in src.lines[:40]:
            L.append(f'  {x.get("who") or "？"}：{x.get("text")}')
    return '\n'.join(L)


_RULES_COMMON = f'''**这一层只许用上面那些事实。** 不许发明新人物、新物件、新前情。

**变化账本（整件事的核心）**：每一步都要写清"哪一格从哪挪到哪"。
    kind　　：信息 / 关系 / 处境 / 物（四选一，不许自己造）
    subject ：人物表里的人
    obj　　 ：上面事实里出现过的**东西的名字**，2~4 字（壶 / 井 / 白绫 / 茶账）。
              不许写短语 —— 「井里沉下去的东西」不是物件，「井」才是。
    before / after：**只许从下面的闭集里选**
{STATE_HINT}

⚠ 反面例子（这样写等于没写，会被打回）：
    第 1 章：阿九知道了井里有白绫
    第 2 章：阿九晓得了井中有白绫
    第 3 章：阿九明白井底有白绫
  三章在账本上是同一条（信息|阿九|白绫|知）—— **换个说法不算推进**。
  真推进长这样：
    第 1 章：不知 → 疑（他听见井里有东西）
    第 2 章：疑 → 知（他看见捞上来的是白绫）
    第 3 章：知 → 确证（白绫上有他认得的那道口子）'''

#: 只输出 JSON 的硬性要求（模型很容易多写解释，导致解析失败）。
_JSON_ONLY = '只输出一个 JSON，不要解释、不要 markdown 代码围栏、不要前后缀。'


def prompt_l0(src: A.Source, *, want_chapters: int = 0,
              lessons: list[str] | None = None) -> str:
    """L0：把推演抽成**全书骨架**（总分结构的"总"）。"""
    n = want_chapters or max(3, min(8, len(src.events) or 3))
    tips = ''
    if lessons:
        tips = ('\n【上一次被打回的原因（必须避开）】\n'
                + '\n'.join(f'  - {x}' for x in lessons[-LESSON_CAP:]) + '\n')
    return f'''你是这部小说的作者。现在还没有正文，先做**骨架**。

{_facts(src)}

{_RULES_COMMON}
{tips}
【要你做的事】
1. 先定**全书主线**（`logline` 一句话 + `spine` 3~5 句，按先后）。
2. 再分章（{n} 章左右，按推演发生的先后），每章给：
   `act`（起/承/转/合）、`place`、`present`（在场人）、
   `events`（**这一章要用掉哪些事件编号，每件事都要被用掉且只用一次**）、
   `changes`（这一章让哪一格变了，1~2 条）、
   `spine`（这一章在主线上推进哪一句）。
3. 章的 `changes` 之间**不许重复**：相邻两章账本一模一样就是原地打转。

【输出】{_JSON_ONLY}
{{"logline":"…","spine":["…","…"],"cast":{{"阿九":"跑堂"}},
 "props":["白绫","井"],
 "chapters":[{{"idx":1,"title":"","act":"起","spine":"","place":"",
   "present":["阿九"],"events":["E1"],
   "changes":[{{"kind":"信息","subject":"阿九","obj":"白绫",
               "before":"不知","after":"疑","cause":"E1"}}]}}]}}'''


def prompt_l1(src: A.Source, sk: A.Skeleton, ch: A.Chapter,
              lessons: list[str] | None = None) -> str:
    """L1：把一章拆成**节拍**（总分结构的"分"）。"""
    tips = ''
    if lessons:
        tips = ('\n【上一次被打回的原因（必须避开）】\n'
                + '\n'.join(f'  - {x}' for x in lessons[-LESSON_CAP:]) + '\n')
    return f'''你在把**一章**拆成节拍（这一步像舞台调度：每一拍谁要什么、被什么挡住、
最后哪一格变了）。

{_facts(src)}

【全书骨架（已经定稿，不许改）】
{A.tree_text(sk)}

【要拆的这一章】
第 {ch.idx} 章〔{ch.act}〕{ch.title}　{ch.place}
  在场：{'、'.join(ch.present) or '（未指定）'}
  本章要用掉的事件：{'、'.join(ch.events) or '（无）'}
  本章要让：{'；'.join(x.one_line() for x in ch.changes) or '（未指定）'}

{_RULES_COMMON}
{tips}
【要你做的事】
把这一章拆成 3~6 拍。每一拍：
  · `want`：这个人这一拍想要什么（具体动作，不是心理）
  · `obstacle`：什么挡住了他（对方不肯 / 规矩 / 自己不敢）
  · `change`：这一拍结束时**哪一格变了**（账本，四槽填满）
  · `events`：这一拍用的是哪条事件
  · ⚠ 相邻两拍的最关键那条变化**不许一样**：后一拍必须是**新的**变化，
    只是"换个人再问一遍"不算。
  · ⚠ 同一 (kind, subject, obj) 上的状态**只许往前走**：
    他知道了就不能又变回不知道（除非这是有意的反转，那要在 `reversal` 写 true）。

【输出】{_JSON_ONLY}
{{"chapter":{ch.idx},"beats":[{{"id":"B1","who":["阿九","柳氏"],
  "want":"…","obstacle":"…","events":["E1"],
  "change":{{"kind":"信息","subject":"阿九","obj":"白绫",
             "before":"不知","after":"疑","cause":"E1"}}}}]}}'''


def prev_summary(sk: A.Skeleton, ch: A.Chapter) -> str:
    """前面几章**已经演到哪**（给 L2 做衔接用）。

    ★ 为什么非给不可（真跑实测）：不给的话，模型为了"接上"会把前一章的
      取壶、见无影、井台滑**再演一遍** —— 骨架没错、账本没错，读者却看了两遍开场。
      给了之后它知道"这些演过了"，直接从上一章停下的地方接着写。
    """
    out = []
    for p in sk.chapters:
        if int(p.idx) >= int(ch.idx):
            continue
        line = f'  第 {p.idx} 章：{p.spine or p.title}'
        acts = [b.want for b in p.beats if str(b.want or '').strip()]
        if acts:
            line += '（已演：' + '；'.join(acts[:4]) + '）'
        out.append(line)
    return chr(10).join(out)


def prompt_l2(src: A.Source, sk: A.Skeleton, ch: A.Chapter,
              lessons: list[str] | None = None) -> str:
    """L2：把节拍写成**正文草稿**。"""
    tips = ''
    if lessons:
        tips = ('\n【上一次被打回的原因（必须避开）】\n'
                + '\n'.join(f'  - {x}' for x in lessons[-LESSON_CAP:]) + '\n')
    prev = prev_summary(sk, ch)
    beats = '\n'.join(
        f'  {b.id}　{b.want}｜挡：{b.obstacle}｜'
        f'变：{b.change.subject}·{b.change.obj} {b.change.before}→{b.change.after}'
        f'（事件 {",".join(b.events) or "—"}）'
        for b in ch.beats)
    style = (src.days[0]['text'][:400] if src.days else '')
    return f'''你在写**第 {ch.idx} 章**的正文草稿。**只写这一章**，不写别的章，不写总结。

{_facts(src)}

【前面几章已经演到哪（**这些演过了，不许重演**）】
{prev or '  （这是第一章）'}

【这一章的节拍（必须全部写到，一拍都不能漏）】
{beats}

【写法】
- 视角：{sk.cast and '第一人称（当事人）' or '第三人称限知'}
- 语句干净，别抒情，别总结；情绪落在动作和物件上。
- 台词用自然普通话；人物说话要像他自己，不要人人一个腔调。
- **每个节拍写完后，把正文里落地的那个原句抄进 `lands`**（≥8 字，逐字照抄）。
  这是自证：抄不出来就说明这一拍没写成。
- ★ **接着上一章写，不许重演**：前面演过的动作（取壶、见无影、井台滑…）
  最多一句话带过。要让读者想起旧事，就让人物**提一句**，不要再演一遍 ——
  同一场开场写两遍，读者会以为翻回去重了。

{('【过程稿片段（只借语气与细节，不许照抄结构）】' + chr(10) + style) if style else ''}
{tips}
【输出】{_JSON_ONLY}
{{"chapter":{ch.idx},"draft":"…正文…",
 "lands":{{"B1":"正文里对应 B1 的那一句原话","B2":"…"}}}}'''


def prompt_l3(src: A.Source, sk: A.Skeleton, ch: A.Chapter,
              lessons: list[str] | None = None) -> str:
    """L3：在草稿上**补细节**（只改质地，不改事实与结构）。"""
    tips = ''
    if lessons:
        tips = ('\n【上一次被打回的原因（必须避开）】\n'
                + '\n'.join(f'  - {x}' for x in lessons[-LESSON_CAP:]) + '\n')
    zhang = len([c for c in ch.draft if '\u4e00' <= c <= '\u9fff'])
    beat_lines = chr(10).join(
        f'  {b.id}　{b.want}｜变：{b.change.after}' for b in ch.beats)
    return f'''这是第 {ch.idx} 章的草稿。**只补细节，不许改事实、不许改结构。**

【草稿】
{ch.draft}

【这一章的节拍（结构已经定死，补细节不许动它）】
{beat_lines}

【补什么】
- 人物细节：他手上的动作、身上物件、说话前那个停顿。
- 感官：冷、味、声音的远近（每段最多一处，不许堆）。
- 物件：只补**上面事实里出现过**的物件，不许发明新的。
【不许做什么】
- 不许把台词并进叙述（台词一句都不许少）。
- 不许把字数拉过 {round(zhang * 1.45)} 字（现在是 {zhang} 字），也不许缩到
  {round(zhang * 0.85)} 字以下。
- 不许改情节顺序，不许加新事件，不许让人物知道他不该知道的事。
- 不许把句子拆得更碎。

{tips}
【输出】{_JSON_ONLY}
{{"chapter":{ch.idx},"final":"…补完的正文…",
 "lands":{{"B1":"补完后正文里对应 B1 的那一句原话","B2":"…"}}}}'''


# ══════════════════════════════════════════════════════════════════
# 解析（**宽松读、严格判**：读的时候容忍围栏/前后缀，判的时候不许猜）
# ══════════════════════════════════════════════════════════════════

_FENCE = re.compile(r'```(?:json)?\s*(.*?)```', re.S)


def _loads(raw: str) -> dict:
    """从模型的返回里挖出第一个 JSON 对象。

    ★ 为什么不用 `json.loads(raw)`：模型十次有三次会包 ```json 围栏或加一句
      "好的，这是骨架"。**宽松读**是必要的，但**不许宽松判** ——
      挖不出来就是挖不出来，返回空字典，让闸去打回。
    """
    s = str(raw or '').strip()
    if not s:
        return {}
    m = _FENCE.search(s)
    if m:
        s = m.group(1).strip()
    for cand in (s, s[s.find('{'):s.rfind('}') + 1] if '{' in s else ''):
        if not cand:
            continue
        try:
            v = json.loads(cand)
            if isinstance(v, dict):
                return v
        except (ValueError, TypeError):
            continue
    return {}


def _chg_of(d) -> A.Change:
    if not isinstance(d, dict):
        return A.Change()
    return A.Change(kind=str(d.get('kind') or '').strip(),
                    subject=str(d.get('subject') or '').strip(),
                    obj=str(d.get('obj') or '').strip(),
                    before=str(d.get('before') or '').strip(),
                    after=str(d.get('after') or '').strip(),
                    cause=str(d.get('cause') or '').strip(),
                    tick=str(d.get('tick') or '').strip(),
                    reversal=bool(d.get('reversal')))


def parse_l0(raw: str) -> A.Skeleton:
    d = _loads(raw)
    sk = A.Skeleton(logline=str(d.get('logline') or ''),
                    spine=[str(x) for x in (d.get('spine') or ()) if str(x).strip()],
                    cast={str(k): str(v or '') for k, v in (d.get('cast') or {}).items()},
                    props=[str(x) for x in (d.get('props') or ()) if str(x).strip()])
    for i, cd in enumerate(d.get('chapters') or ()):
        if not isinstance(cd, dict):
            continue
        try:
            idx = int(cd.get('idx') or (i + 1))
        except (TypeError, ValueError):
            idx = i + 1
        sk.chapters.append(A.Chapter(
            idx=idx,
            title=str(cd.get('title') or ''),
            act=str(cd.get('act') or '承'),
            spine=str(cd.get('spine') or ''),
            place=str(cd.get('place') or ''),
            present=[str(x) for x in (cd.get('present') or ())],
            events=[str(x) for x in (cd.get('events') or ())],
            changes=[_chg_of(x) for x in (cd.get('changes') or ())]))
    return sk


def parse_l1(raw: str) -> list[A.Beat]:
    d = _loads(raw)
    out: list[A.Beat] = []
    for i, bd in enumerate(d.get('beats') or ()):
        if not isinstance(bd, dict):
            continue
        out.append(A.Beat(
            id=str(bd.get('id') or f'B{i + 1}').strip(),
            who=[str(x) for x in (bd.get('who') or ())],
            want=str(bd.get('want') or ''),
            obstacle=str(bd.get('obstacle') or ''),
            change=_chg_of(bd.get('change')),
            events=[str(x) for x in (bd.get('events') or ())],
            lands=str(bd.get('lands') or '')))
    return out


def parse_l2(raw: str) -> tuple[str, dict[str, str]]:
    d = _loads(raw)
    text = str(d.get('draft') or d.get('final') or '').strip()
    lands = {str(k): str(v) for k, v in (d.get('lands') or {}).items()}
    return text, lands


def parse_l3(raw: str) -> tuple[str, dict[str, str]]:
    return parse_l2(raw)


# ══════════════════════════════════════════════════════════════════
# 选优（确定性键）
# ══════════════════════════════════════════════════════════════════

def key_of(sk: A.Skeleton, src: A.Source, layer: str,
           *, chapter: int | None = None) -> tuple:
    """候选的排序键：**问题越少越好；问题一样多时，变化越丰富越好**。

    ⚠ 第二项取负数：变化数多的候选 key 更小（更优）。
      方向写反过一次（`verdict.better` 曾写成 `kb < ka` ⇒ 取到最差那版），
      所以这里由判据正反各测一次钉住。
    """
    probs = A.gate_all(layer, sk, src, chapter=chapter)
    cov = A.coverage(sk, src)
    # 第二项用 `unique_all`（章级 + 拍级），不是 `unique_changes`（每章只留一条代表）：
    # 后者会把"多加一拍、多一个变化"抹平，选优就退化成只看问题数。
    return (len(probs), -int(cov['unique_all']), int(cov['beats']))


def better(a, b) -> bool:
    """`a` 是否比 `b` 好。**返回 True 表示 a 更优**（方向靠判据钉）。"""
    return a < b


# ══════════════════════════════════════════════════════════════════
# 执行器
# ══════════════════════════════════════════════════════════════════

async def compose(ask, src: A.Source, *, chapters: int = 0,
                  rounds: int = 3, n_best: int = 2,
                  progress=None, save=None) -> tuple[A.Skeleton, list[str]]:
    """跑完四层。返回 `(骨架, 未解决的问题)`。

    ★ `未解决的问题` 必须**往外传**，不许吞掉：吞掉就等于"假装过了闸"。
      调用方（导出）依据它决定"标注未解决"还是"拒绝装订"。
    """
    sk = A.Skeleton()
    unsolved: list[str] = []
    mem: dict[str, list[str]] = {k: [] for k in A.LAYERS}

    def _say(msg: str) -> None:
        _LOG.info(msg)
        if progress:
            try:
                progress(msg)
            except Exception:                                    # noqa: BLE001
                pass

    # ── L0：骨架 ──
    sk, left = await _stage(
        ask, 'L0', sk, src,
        make_prompt=lambda _ch, les: prompt_l0(src, want_chapters=chapters,
                                               lessons=les),
        apply=lambda sk, raw, _ch: _merge_l0(sk, parse_l0(raw)),
        rounds=rounds, n_best=n_best, mem=mem['L0'], say=_say)
    unsolved += [f'L0 {x}' for x in left]
    if save:
        save('L0', sk)

    # ── L1 / L2 / L3：逐章 ──
    # ★★★ **一层没过，这一章后面几层不许跑**（2026-10-21 判据 D5 抓的）。
    #   第一版是无条件往下跑，等于"先记下来，后面一起修" ——
    #   那正是旧流程（写完再挑毛病）失败的原因。用户那句「没问题了再继续」
    #   在代码里就是这个 `continue`。
    #   为什么不是整本停：一章卡住不该冻住全书（那是"全有或全无"，
    #   本项目踩过的坑）。停**这一章**的后续层，其余章照常推进。
    # [EN] If a layer fails its gate, the rest of that chapter's layers never run. The first
    # [EN] version kept going and just recorded the problems -- exactly the "write everything
    # [EN] then hunt for flaws" flow that failed before. "Only continue when it's clean" is
    # [EN] this `continue`. It stops the **chapter**, not the book (all-or-nothing is its own
    # [EN] trap).
    for ch in sk.chapters:
        for layer, mk, ap in (('L1', prompt_l1, _apply_l1),
                              ('L2', prompt_l2, _apply_l2),
                              ('L3', prompt_l3, _apply_l3)):
            sk, left = await _stage(
                ask, layer, sk, src, chapter=ch.idx,
                make_prompt=lambda c, les, _mk=mk: _mk(src, sk, c, lessons=les),
                apply=lambda sk, raw, c, _ap=ap: _ap(sk, raw, c),
                rounds=rounds, n_best=n_best, mem=mem[layer], say=_say)
            if save:
                save(layer, sk)
            if left:
                unsolved += [f'{layer} 第 {ch.idx} 章 {x}' for x in left]
                _say(f'atelier：第 {ch.idx} 章卡在 {layer}，本章后续层不跑')
                break
    return sk, unsolved


async def _stage(ask, layer: str, sk: A.Skeleton, src: A.Source, *,
                 chapter: int | None = None,
                 make_prompt, apply, rounds: int, n_best: int,
                 mem: list[str], say) -> tuple[A.Skeleton, list[str]]:
    """跑一层：出候选 → 过闸 → 不过就带教训重来。**过闸才算完。**"""
    best_sk, best_key = None, None
    left: list[str] = []
    total = max(1, int(rounds))
    for r in range(total):
        cands = []
        for _ in range(max(1, int(n_best))):
            prompt = make_prompt(_chapter_of(sk, chapter), mem)
            try:
                raw = await ask(prompt, 'standard', f'atelier_{layer}')
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('atelier %s 第 %d 轮调用失败：%r', layer, r + 1, e)
                continue
            # ★★★ 必须把**副本里的那一章**交给 `apply`（2026-10-21 判据抓的）。
            #   第一版写的是 `apply(_clone(sk), raw, _chapter_of(sk, chapter))`：
            #   副本是新的，章节对象却取自**原骨架** ⇒ 节拍写进了原骨架，
            #   返回的副本里仍然没有节拍 ⇒ 闸永远判"没有节拍"、每章都卡死。
            #   这种"改 A 读 B"的别名错误读代码看不出来，只有跑一遍才露。
            # [EN] Hand `apply` the chapter **from the clone**. The first version passed a clone
            # [EN] plus a chapter taken from the *original* skeleton, so beats landed on the
            # [EN] original while the returned clone stayed empty -- the gate then always said
            # [EN] "no beats". Classic aliasing bug: invisible by reading, obvious by running.
            cand = _clone(sk)
            cand_ch = _chapter_of(cand, chapter)
            cand = apply(cand, raw, cand_ch)
            if cand is None:
                continue
            k = key_of(cand, src, layer, chapter=chapter)
            cands.append((k, cand))
        if not cands:
            left = ['模型没有返回可用结果']
            continue
        cands.sort(key=lambda x: x[0])
        k, cand = cands[0]
        if best_key is None or better(k, best_key):
            best_sk, best_key = cand, k
        probs = A.gate_all(layer, cand, src, chapter=chapter)
        if not probs:
            say(f'atelier {layer}'
                + (f' 第 {chapter} 章' if chapter else '')
                + f'：第 {r + 1} 轮过闸 ✓')
            return cand, []
        left = [p.one_line() for p in probs][:LESSON_CAP]
        mem[:] = (mem + left)[-LESSON_CAP:]
        say(f'atelier {layer}'
            + (f' 第 {chapter} 章' if chapter else '')
            + f'：第 {r + 1} 轮有 {len(probs)} 条没过（{left[0]}）')
    return (best_sk if best_sk is not None else sk), left


def _chapter_of(sk: A.Skeleton, idx: int | None) -> A.Chapter | None:
    return sk.chapter(idx) if idx is not None else None


def _merge_l0(old: A.Skeleton, new: A.Skeleton) -> A.Skeleton:
    """L0 候选合并回整份骨架：**保留已写好的草稿**（重试骨架不该丢正文）。"""
    if not new.chapters:
        return old
    for c in new.chapters:
        prev = old.chapter(c.idx)
        if prev and prev.draft:
            c.draft, c.final = prev.draft, prev.final
    return new


def _apply_l1(sk: A.Skeleton, raw: str, ch: A.Chapter | None) -> A.Skeleton | None:
    if ch is None:
        return None
    beats = parse_l1(raw)
    if not beats:
        return None
    ch.beats = beats
    return sk


def _apply_l2(sk: A.Skeleton, raw: str, ch: A.Chapter | None) -> A.Skeleton | None:
    if ch is None:
        return None
    text, lands = parse_l2(raw)
    if not text.strip():
        return None
    ch.draft = text
    for b in ch.beats:
        if b.id in lands:
            b.lands = lands[b.id]
    return sk


def _apply_l3(sk: A.Skeleton, raw: str, ch: A.Chapter | None) -> A.Skeleton | None:
    if ch is None:
        return None
    text, lands = parse_l3(raw)
    if not text.strip():
        return None
    ch.final = text
    for b in ch.beats:
        if b.id in lands:
            b.lands = lands[b.id]
    return sk


def _clone(sk: A.Skeleton) -> A.Skeleton:
    """复制一份骨架（候选之间不许互相污染）。"""
    import copy
    return copy.deepcopy(sk)
