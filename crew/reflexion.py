# -*- coding: utf-8 -*-
"""**Reflexion 引擎** —— 把"改稿"从一次性动作变成"试 → 验 → 写教训 → 再试"的闭环。

★★★ 为什么重做这一层（2026-10-20）
==================================
原来的多轮检查是：跑 8 个 `_fix_*` → 数总数 → 总数降了就留、没降就停。
它的四个结构性缺陷都不是"某一步写得不好"，而是**架构里缺东西**：

1. **没有验收方**：每一步 `_fix_*` 自己判"我写得行不行"（拿长度比、拿台词数比），
   阈值散在 8 个函数里、各写一套 —— 于是"修好了 A 却改坏 B"这种跨类退化
   **没有任何一处能看见**。实测：太碎 0→2、平铺 2→3。
2. **失败不产生知识**：被拒的那次尝试直接丢掉，下一轮从零开始瞎试。
3. **一轮只有一个候选**：被闸拦下就放弃（白花钱），没有"换个写法再来"。
4. **收敛判据是单标量**：`issue_total` 求和，把"两类互换"看成"没变化"。

这一层按公开的 Reflexion 范式补齐（Shinn 等，NeurIPS 2023；2025–2026 的生产变体）：
**Actor（写）／ Evaluator（确定性打分）／ Self-Reflector（写教训）／ Episodic Memory
（教训进下一次的上下文）**，外加 best-of-N 与 Pareto archive。

四条落地纪律（都是这个项目已经付过学费的）
------------------------------------------
· ★ **Evaluator 必须是确定性的**（`crew.verdict`）。研究结论很硬：
  LLM 判官会偏向自己的输出（rubric 明确时误判自己合格的概率高 50%），
  在分布外输入上退化到接近抛硬币。**可争辩的判定，优化压力一定会找到缝**。
  ⇒ 判官降级为顾问（`verbalize`），判定权归代码。
· ★ **反思必须挂在具体信号上**。评估信号不具体，反思就变成空话
  （"下次写得更好点"）。所以每条 lesson 都带：哪一类、几处、**原文哪一句**。
· ★ **教训库要有界**（`Memory(cap=…)`）。Reflexion 的老毛病是记忆越堆越长，
  最后把上下文吃光。这里只留最近 N 条 + 按类别去重。
· ★ **必须有止损**：轮数上限、连续无进度的 patience、以及"每步都跳过就停"。
  论文里叫 stop conditions，工程上叫"别烧钱烧到天亮"。

与"逐点打补丁"的区别
--------------------
加一类新毛病 = 在 `crew/repair_recipes.py` 登记一个 Recipe（检测器 + 修法 + 不变量）
+ 在 `prose_flow.prose_issue_count` 数它。**不改这个文件、不改 `_checkup` 的流程**。
这就是"用架构解决"和"一件事修一次"的差别。

[EN] Reflexion engine: actor / deterministic evaluator / self-reflector / bounded
[EN] episodic memory, plus best-of-N and a Pareto archive. The evaluator is code, not
[EN] an LLM -- judges favour their own output and degrade to chance out of
[EN] distribution. Every lesson carries class, count and the offending sentence, so
[EN] reflections stay actionable instead of turning into "try harder".
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from crew import verdict as V

_LOG = logging.getLogger(__name__)

#: 教训库上限。**有界**是这个范式能长期跑的前提：无界记忆最后会占满上下文，
#: 而且旧教训会跟当前稿子无关（稿子已经改过了）。
MEMORY_CAP = 24

#: 给模型看的那段反思最长多少字。太长会挤掉正文本身（提示词预算有限），
#: 太短又只剩"注意质量"这种废话。240 字 ≈ 3~5 条具体教训。
BRIEF_MAX = 240


# ─────────────────────────── 教训与记忆 ───────────────────────────

@dataclass
class Lesson:
    """一条**可执行**的教训。四个字段缺一个就会退化成空话：

    · `label`  哪一类（"平铺段"）—— 不知道哪一类，下一轮不知道该防什么；
    · `why`    具体差异（"憋气段 0→2 改多了"）—— 没有数字，模型只会说"我会注意"；
    · `span`   出问题的那句原文（≤60 字）—— 没有锚点，它不知道该看哪儿；
    · `advice` 下一轮怎么改 —— 这是**动词**，不是形容词。
    """
    label: str
    why: str
    advice: str
    span: str = ''
    level: str = 'reject'
    trial: int = 0

    def one_line(self) -> str:
        s = f'[{self.label}] {self.why} ⇒ {self.advice}'
        if self.span:
            s += f'（原句：{self.span}）'
        return s


class Memory:
    """有界的教训库。可以只在内存里，也可以落盘（导出关口要跨天沿用）。"""

    def __init__(self, cap: int = 0):
        if not cap:
            # 默认读配置（`PROSE_REFLECT_MEMORY`）；读不到就用模块常量。
            try:
                from config import CFG
                cap = int(CFG.i('PROSE_REFLECT_MEMORY'))
            except Exception:                                    # noqa: BLE001
                cap = MEMORY_CAP
        self.cap = max(4, int(cap))
        self.items: list[Lesson] = []

    # ── 写 ──
    def add(self, lesson: Lesson) -> None:
        """按「类别 + 主要差异」去重：同一个坑记 20 遍只会把上下文挤满，
        读者（模型）也读不出"这是反复出现的问题"。"""
        key = (lesson.label, lesson.why.split('（')[0])
        self.items = [x for x in self.items
                      if (x.label, x.why.split('（')[0]) != key]
        self.items.append(lesson)
        if len(self.items) > self.cap:
            self.items = self.items[-self.cap:]

    def clear(self) -> None:
        self.items = []

    # ── 读 ──
    def __len__(self) -> int:
        return len(self.items)

    def of(self, label: str = '') -> list[Lesson]:
        return [x for x in self.items if not label or x.label == label]

    def brief(self, limit: int = BRIEF_MAX) -> str:
        """拼成给模型看的一段。**只给"下次别做什么"，不给"这次哪里差"** ——
        模型看不到旧稿，说旧稿的问题它没法用。

        空库返回空串（这一点很重要：调用方据此决定"要不要在提示词里加这一段"，
        也保证没反思时提示词与旧版**逐字一致**）。
        """
        if not self.items:
            return ''
        lines: list[str] = []
        for x in self.items:
            lines.append(x.one_line())
        text = '\n'.join(lines)
        if len(text) > limit:
            # 从**最早的**开始砍 —— 最近一次踩的坑最相关。
            while lines and len('\n'.join(lines)) > limit:
                lines.pop(0)
            text = '\n'.join(lines)
        return text

    # ── 落盘（导出关口跨天沿用、也给人查） ──
    def save(self, path: str | Path) -> bool:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('\n'.join(json.dumps(asdict(x), ensure_ascii=False)
                                   for x in self.items) + ('\n' if self.items else ''),
                         encoding='utf-8')
            return True
        except OSError as e:
            _LOG.debug('教训库落盘失败（不影响改稿）：%r', e)
            return False

    def load(self, path: str | Path) -> int:
        try:
            raw = Path(path).read_text(encoding='utf-8')
        except OSError:
            return 0
        n = 0
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                self.add(Lesson(label=str(d.get('label') or ''),
                                why=str(d.get('why') or ''),
                                advice=str(d.get('advice') or ''),
                                span=str(d.get('span') or ''),
                                level=str(d.get('level') or 'reject'),
                                trial=int(d.get('trial') or 0)))
                n += 1
            except (ValueError, TypeError):
                continue
        return n


# ─────────────────────────── 反思（Self-Reflector） ───────────────────────────

#: label → 检测器。用来把"这一类改多了"落到**具体那一句**上。
_SPAN_OF = {
    '憋气段': 'long_span_issues',
    '平铺段': 'flat_span_issues',
    '重复': 'repeat_issues',
    '拥挤段': 'crowded_paragraph_issues',
    '元叙述': 'meta_narration_issues',
    '感知自洽': 'percept_issues',
    '问答悬空': 'qa_drift_issues',
    '道具循环': 'prop_cycle_issues',
}


def first_span(text: str, label: str, width: int = 60) -> str:
    """取这一类毛病的**第一处原文**（给教训做锚点）。取不到就返回空串。

    ⚠ 任何异常都要吞掉：反思是加分项，不许因为它读不出 span 把整轮改稿搞崩。
    """
    fn_name = _SPAN_OF.get(label)
    if not fn_name:
        return ''
    try:
        from crew import prose_flow as PF
        found = getattr(PF, fn_name)(text)
    except Exception:                                            # noqa: BLE001
        return ''
    if not found:
        return ''
    item = found[0]
    try:
        if isinstance(item, tuple):                  # (start, end)
            s, e = int(item[0]), int(item[1])
        elif isinstance(item, dict):
            s = int(item.get('start', 0))
            e = int(item.get('end', s + width))
        else:
            return ''
        frag = str(text)[s:e].replace('\n', ' ').strip()
        return frag[:width]
    except (TypeError, ValueError, IndexError):
        return ''


def _advice(label: str, d: V.Decision) -> str:
    """把判定翻成**一个动作**。这是"具体"与"空话"的分界线。"""
    if d.violated:
        return '这次改动动了不该动的东西 —— 重写时事实、台词、篇幅都保持原样，只换写法'
    if d.suspect:
        return '不许靠删段达标 —— 毛病要修掉，但那几件事必须还在'
    if d.up:
        worst = '、'.join(f'{k}多 {d.new.counts.get(k, 0) - d.old.counts.get(k, 0)} 处'
                          for k in d.up)
        return (f'上一轮把{worst} —— 这次只改被点名的那几处，'
                f'别的句子一个字都别动')
    if label in ('平铺段', '憋气段'):
        return '长短要掺着：整段都是短句、或整段都是长句，一样不合格'
    if label == '重复':
        return '留下最先的那一次，后面重复的换成「对面新的反应」，别再问一遍'
    if label == '拥挤段':
        return '只在说话人换了的地方分段，同一件事别切成好几段'
    return '换一个改法，别再重复上一次的做法'


async def verbalize(lessons: list[Lesson], *, call=None, tag: str = '') -> str:
    """**可选的**语言反思：把若干条教训压成一段给模型看的提醒。

    为什么不默认调模型：`lessons` 已经是**结构化的具体信号**（类别 + 数字 + 原句），
    模板拼出来就够用了。多一次调用换来的边际收益很小，而成本是确定的。
    这与 2026 年那套实践一致 —— **有硬信号就用硬信号，自评只当补充**。

    `call` 形如 `async (prompt) -> str`。给了就让它"只许归纳、不许新增"；
    给了但失败/返回空 ⇒ **静默退回模板**（反思不许成为新的故障点）。
    """
    if not lessons:
        return ''
    template = '\n'.join(x.one_line() for x in lessons)
    if call is None:
        return template
    prompt = (
        '下面是一个小说改写助手最近几次**被退回**的记录。请把它归纳成不超过 120 字的'
        '提醒，留给它下一轮改写时看。\n'
        '硬性要求：\n'
        '1. 只许归纳下面已有的内容，**不许新增任何没写到的类别、数字或人物**；\n'
        '2. 写成"要做/不要做"的动作句，不要评价、不要鼓励；\n'
        '3. 只输出这段提醒本身，不要开场白。\n\n' + template
    )
    try:
        out = await call(prompt)
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('语言反思失败（用模板）：%r', e)
        return template
    out = str(out or '').strip()
    # ★ 长度与"非空"两道闸：模型偶尔会回一句"好的，我明白了"——那等于没反思。
    if len(out) < 12 or len(out) > 400:
        return template
    return out


# ─────────────────────────── 主循环 ───────────────────────────

@dataclass
class Result:
    """一轮 Reflexion 的结果。`text` 是**archive 里最好的那一版**，不一定是最后跑出来的。"""
    text: str
    trials: int = 0
    accepted: int = 0
    tradeoffs: int = 0
    rejected: int = 0
    stop: str = ''
    best_trial: int = 0
    best_weighted: float = 0.0
    best_total: int = 0
    start_total: int = 0
    decisions: list = field(default_factory=list)
    memory: Memory | None = None
    start_weighted: float = 0.0

    @property
    def improved(self) -> bool:
        """**加权**降了才算有进步（只看总数会把"两类互换"看成没变）。"""
        return self.best_weighted < self.start_weighted

    def summary(self) -> str:
        return (f'毛病 {self.start_total}→{self.best_total} 处'
                f'（加权 {self.best_weighted}）· {self.trials} 轮 · '
                f'收 {self.accepted} / 候选 {self.tradeoffs} / 拒 {self.rejected} · '
                f'停因：{self.stop}')


def _regressed(before: V.Score, after: V.Score) -> set[str]:
    """这一轮被"自己的步骤"改多了的类 —— 下一轮跳过它（R48 的老规则，保留）。"""
    return {k for k in set(before.counts) | set(after.counts)
            if int(after.counts.get(k, 0)) > int(before.counts.get(k, 0))}


def _should_skip(label: str, score: V.Score, regressed: set[str],
                 stalled: set[str] | None = None) -> str:
    """这一轮该不该跳过某一步。返回原因（空串 = 该跑）。

    · 这一类已经是 0 ⇒ 没什么可修，重跑只会添乱；
    · 这一类上一轮被自己改多了 ⇒ 它在反复判自己的产物（`平铺 2→3→6` 的根因）；
    · **这一类连着两轮一个数都没动**（`stalled`，2026-10-24 加）⇒ 它修不动，
      再跑一遍只会再烧一次调用；
    · **`元叙述` 永不跳过** —— 它是确定性剥离，不会写进新东西。

    ★★★ 为什么要加 `stalled`（2026-10-24，望江楼那轮 49 分钟的整理稿）：
      日志里这两处报得**一字不差**，连着 8 次（22:32 → 22:39）：
        整理稿里同一个写法用超了 2 处：细节复读「墙那张」3 次（上限 2）；
                                      细节复读「塞进」3 次（上限 2）
      而 `patience`（连续几轮"加权总分"没降就停）**一直没触发** —— 因为别的类
      还在降分，加权总分每轮都更低一点点，于是整轮判"有进步"，继续跑满 5 轮。
      ⇒ 总分降 ≠ 每一类都在降。要按**类**记"它上一轮有没有动"，
        连续两轮同一个数字就认输（记一笔教训，下一轮跳过它）。

    ⚠ 判据是"**计数完全没变**"，不是"还大于 0"：某类从 3 降到 2 是要继续修的
      （说明改法有效）；从 3 到 3 才叫修不动。
    ⚠ 只跳一轮不够：模型有抖动（同一句话两轮可能一轮改掉一轮没改），
      所以"连续两轮没变"才算 stalled —— 一轮没变先给它一次机会。
    [EN] Whether this round should skip a step. Empty string = run it.
    [EN] · the class is already 0 => nothing to fix, rerunning only adds noise;
    [EN] · the class was inflated by its own step last round => it is re-judging its own output;
    [EN] · **the class has not moved for two rounds** (`stalled`, added 2026-10-24) => it cannot be
    [EN]   fixed; another pass only burns another call;
    [EN] · **`元叙述` never skips** -- it is a deterministic strip and writes nothing new.
    [EN] ★★★ Why `stalled` (2026-10-24, the 49-minute organizer run): two findings were reported
    [EN] **verbatim identically eight times in a row** (22:32 -> 22:39), while `patience` (stop when
    [EN] the **weighted total** fails to drop) never fired -- other classes were still dropping, so the
    [EN] weighted total fell a little every round and every round counted as progress; it ran all five.
    [EN] => A falling total does not mean every class is falling. Track **per class** whether it moved;
    [EN] two rounds at the same number means give up (record a lesson, skip it next round).
    [EN] ⚠ The test is "**the count did not change**", not "still above 0": 3 -> 2 deserves another
    [EN] pass (the fix works); 3 -> 3 does not.
    [EN] ⚠ One stalled round is not enough: the model jitters (the same line may be fixed one round
    [EN] and not the next), so **two consecutive unchanged rounds** qualifies.
    """
    if label == '元叙述':
        return ''
    if int(score.counts.get(label, 0)) == 0:
        return '这一类已经是 0'
    if label in regressed:
        return '上一轮被这一步改多了'
    if stalled and label in stalled:
        return '连着两轮一个数都没动（修不动，先跳过）'
    return ''


async def reflect(text: str, steps: list, *, trials: int = 3,
                   patience: int = 1, n_best: int = 1,
                   memory: Memory | None = None,
                   tag: str = '正文', log=_LOG,
                   style_rounds: int = 0,
                   style_labels: set[str] | None = None,
                   on_round=None) -> Result:
    """跑一轮 Reflexion。

    参数
    ----
    steps     `[(async (text) -> text, label), ...]`，顺序由调用方定
              （`crew/repair_recipes.py` 里有唯一登记处）。
    trials    最多几轮。
    patience  连续几轮"加权没降"就停。默认 1 —— 每一轮现在已经过验收层，
              没降就是真的没降（旧版给 2 是因为单标量会抖动；多目标更稳）。
    n_best    每个 step 生成几个候选（verifier-guided best-of-N）。
              默认 1；导出关口用 2。⚠ 成本是线性的，别随手调大。
    memory    跨轮/跨天的教训库（导出关口会一直传同一个）。
    style_rounds  ★★★ **文风类最多改到第几轮**（2026-10-25 加；0 = 不限，即老行为）。
              为什么要有它：望江楼那轮整理稿 49 分钟、93 次调用，其中 50 次
              `crew_day_novel` 是 Reflexion 在**整段重写**，触发它的多是
              「细节复读」「憋气」「平铺」—— 全是文风类。而本项目自己的规则写着
              "文风类不触发退回，只有实病才触发"：规则在，这条路径却没照做。
              文风类删掉之后读者**不损失任何东西**（真人比模型重复更多），
              为它一轮轮重写整段，只会"越改越平、越改越挤"（日志里"太挤"12→21→37）。
              ⇒ 文风类**第一轮照改**（活还得做），之后不再为它多跑整段重写；
                实病（元叙述/感知自洽/问答悬空/拥挤）照旧改到为止。
    style_labels 哪些 label 算文风类（由 `repair_recipes.style_labels()` 提供）。
              ⚠ 传空集 = 没有文风类 ⇒ `style_rounds` 不起作用。
    on_round   ★ 2026-10-28 加：**细粒度进度回调**
              `(round_no, trials, label, step_i, n_steps)` —— 每进一个修复步骤就调一次。
              为什么要有它：这一层是导出里**唯一一段几十秒到几分钟没有动静**的地方
              （实测 3 天导出里 96 秒全花在这：5 轮 × 每轮多步，每步一次模型调用），
              而在此之前调用方只知道"检查开始了"和"检查结束了" ⇒ 界面进度条一动不动
              ⇒ 用户判定"导出卡死了"（今天的真事）。回调异常一律吞掉 ——
              界面有误不该弄挂这次检查。
    [EN] on_round: fine-grained progress callback (round/step), added 2026-10-28 so the UI can
    [EN] show movement during the long silent stretch. Callback errors are swallowed.

    [EN] style_rounds: how many rounds **style** classes may run (0 = unlimited, the old
    [EN] behaviour). Measured on the 49-minute organizer run: 50 of 93 calls were Reflexion
    [EN] **rewriting whole chunks**, mostly triggered by repetition / breathless / flat -- all
    [EN] style classes, while this project's own rule says style classes must not trigger a
    [EN] rewrite. Removing a style "defect" costs the reader nothing, and chasing it round after
    [EN] round only makes prose flatter and paragraphs denser (log: crowding 12 -> 21 -> 37).
    [EN] => style classes are still fixed in round 1, just never granted extra rounds.
    """
    mem = memory if memory is not None else Memory()
    cur = str(text or '')
    if not cur.strip():
        return Result(text=cur, stop='空文本', memory=mem)
    if not steps:
        return Result(text=cur, stop='没有可跑的步骤', memory=mem)

    start = V.Score.of(cur)
    # archive 的元素是 (Score, text, trial, label)
    archive: list[tuple[V.Score, str, int, str]] = [(start, cur, 0, '原文')]
    res = Result(text=cur, start_total=start.total, best_total=start.total,
                 best_weighted=start.weighted, start_weighted=start.weighted,
                 memory=mem)
    flat = 0
    regressed: set[str] = set()
    # ★ 2026-10-24：**按类**记"这个数连着几轮没动"，到 2 才跳过（理由见 `_should_skip`）。
    #   ⚠ 用**连续次数**而不是"与上一轮相同就跳"：一轮没动可能只是模型抖动
    #     （同一句话两轮里一轮改掉、一轮没改），先给它一次机会。
    #     第一版写成"相同即 stall"，实测 A 类只跑了 1 轮就再没机会 —— 太早认输。
    #   `prev_counts` = 上一轮结束时的计数；`streak` = 每类连着没动的轮数。
    # [EN] ★ 2026-10-24: track **how many consecutive rounds a class has not moved**, skip at 2
    # [EN] (reason in `_should_skip`). ⚠ A **streak**, not "same as last round => skip": one flat round
    # [EN] may just be model jitter, so give it one more chance. The first version skipped on the first
    # [EN] match and measured A running only once -- giving up too early.
    prev_counts: dict[str, int] = dict(start.counts)
    streak: dict[str, int] = {}
    stalled: set[str] = set()
    log.info('反思（%s）：起点 %d 处（加权 %.1f），最多 %d 轮、每步 %d 个候选',
             tag, start.total, start.weighted, trials, max(1, int(n_best)))

    # ★★★ 文风类只改到第 `style_rounds` 轮（0 = 不限）。
    #   ⚠ 判"跳过"必须按**轮次**、不用 `stalled`：stalled 要等它两轮不动，
    #     而文风类往往是"每轮都动一点、但永远到不了 0"—— 那正是最烧钱的形状。
    # [EN] Style classes only run through round `style_rounds` (0 = unlimited).
    # [EN] ⚠ Keyed on the round number, not `stalled`: `stalled` waits for two unmoving rounds,
    # [EN] while style classes typically move a little every round yet never reach zero --
    # [EN] exactly the expensive shape.
    _style = {str(x) for x in (style_labels or ())}
    _style_rounds = max(0, int(style_rounds or 0))

    def _say_round(_t: int, _label: str, _i: int, _n: int) -> None:
        """把「第几轮 · 第几步」交给调用方（2026-10-28 加，见 `on_round` 的注释）。"""
        if on_round is None:
            return
        try:
            on_round(int(_t), max(1, int(trials)), str(_label), int(_i), max(1, int(_n)))
        except Exception:                                    # noqa: BLE001
            pass                       # 界面 / 调用方的错不许弄挂这次检查

    for t in range(1, max(1, int(trials)) + 1):
        before = V.Score.of(cur)
        if before.total == 0:
            res.stop = '开跑前就已经干净'
            break
        ran = 0
        _style_held: set[str] = set()
        for _si, item in enumerate(steps):
            _say_round(t, (item[1] if len(item) > 1 else ''), _si, len(steps))
            # 兼容两种形态：`(fn, label)` 与 `(fn, label, 每步候选数)`。
            # 每步候选数由 `repair_recipes` 按 kind 定（确定性动作给 1，改写给 2）。
            step, label = item[0], item[1]
            n_this = int(item[2]) if len(item) > 2 else max(1, int(n_best))
            if _style_rounds and t > _style_rounds and label in _style:
                _style_held.add(label)
                continue
            reason = _should_skip(label, before, regressed, stalled)
            if reason:
                log.debug('反思（%s）第 %d 轮：跳过 %s（%s）', tag, t, label, reason)
                continue
            ran += 1
            best_cand: tuple[V.Score, str] | None = None
            for _ in range(max(1, n_this)):
                try:
                    cand = await step(cur)
                except Exception as e:                           # noqa: BLE001
                    log.warning('反思（%s）第 %d 轮：%s 失败（保留原文）：%r',
                                tag, t, label, e)
                    continue
                cand = str(cand or '')
                if not cand.strip() or cand.strip() == cur.strip():
                    continue
                sc = V.Score.of(cand)
                if best_cand is None or V.better((sc, cand), best_cand):
                    best_cand = (sc, cand)
            if best_cand is None:
                res.rejected += 1
                d = V.Decision('reject', '这一步没交出新东西', label=label,
                               old=before, new=before)
                res.decisions.append(d)
                mem.add(Lesson(label=label, why=d.why,
                               advice='这个改法在这里不起作用，换一个方向',
                               span=first_span(cur, label), trial=t))
                continue
            cand = best_cand[1]
            d = V.compare(cur, cand, label=label, old_score=before)
            d.label = label
            res.decisions.append(d)
            if d.ok:
                archive.append((best_cand[0], cand, t, label))
            if d.applied:
                cur = cand
                res.accepted += 1
                log.info('反思（%s）第 %d 轮 · %s：%s', tag, t, label, d.why)
            elif d.level == 'tradeoff':
                res.tradeoffs += 1
                log.info('反思（%s）第 %d 轮 · %s：%s', tag, t, label, d.why)
                mem.add(Lesson(label=label, why=d.why,
                               advice=_advice(label, d),
                               span=first_span(cand, label), level='tradeoff', trial=t))
            else:
                res.rejected += 1
                log.info('反思（%s）第 %d 轮 · %s：%s', tag, t, label, d.why)
                mem.add(Lesson(label=label, why=d.why, advice=_advice(label, d),
                               span=first_span(cur, label), trial=t))

        after = V.Score.of(cur)
        res.trials = t
        # ★ 每一轮都把"当前正文"放进 archive —— 它是经过验收层的，比原文不会更差
        archive.append((after, cur, t, '本轮结束'))
        regressed = _regressed(before, after)
        if regressed:
            log.info('反思（%s）第 %d 轮：这些类被改多了（下一轮跳过）：%s',
                     tag, t, '、'.join(sorted(regressed)))
        # ★★★ 2026-10-24：**连续两轮同一个数字 ⇒ 认输**（按类判，不按总分）。
        #   ⚠ 用 `after.counts` 与 `prev_counts` 比，比完再把 `prev_counts` 推到本轮 ——
        #     顺序反了就成了"本轮跟本轮比"，永远相等、全部跳过。
        #   ⚠ 计数变**多**的那一类走 `regressed`（另一条更严的规则），这里不重复记。
        # [EN] ★★★ 2026-10-24: **two identical rounds => give up** (per class, not on the total).
        # [EN] ⚠ Compare `after.counts` with `prev_counts`, then advance `prev_counts` -- the reverse
        # [EN] order compares this round with itself, which is always equal and would skip everything.
        # [EN] ⚠ A class whose count **grew** is handled by `regressed` (a stricter rule); not repeated
        # [EN] here.
        now_counts = {k: int(v) for k, v in (after.counts or {}).items()}
        for k, v in now_counts.items():
            if v > 0 and k in prev_counts and v == prev_counts[k]:
                streak[k] = streak.get(k, 0) + 1
            else:
                streak[k] = 0            # 动了（降了/清了/变了）就重新给机会
        newly = {k for k, n in streak.items() if n >= 2} - stalled
        if newly:
            log.info('反思（%s）第 %d 轮：这些类连着两轮没动（下一轮跳过）：%s',
                     tag, t, '、'.join(sorted(newly)))
        stalled = {k for k, n in streak.items() if n >= 2}
        prev_counts = now_counts
        if after.total == 0:
            res.stop = f'第 {t} 轮清干净了'
            break
        if after.weighted >= before.weighted:
            flat += 1
            if flat >= max(1, int(patience)):
                res.stop = f'连续 {flat} 轮没有改善'
                break
        else:
            flat = 0
        if ran == 0:
            if _style_held:
                # 说清是哪一半没在改：只剩文风类没干净，而它们按规则不再多跑一轮。
                # [EN] Say which half stopped: only style classes remain, and by rule they get no
                # [EN] extra rounds.
                res.stop = ('实病这边没有还能改的步了'
                            '（文风类只改第 %d 轮，剩下的：%s）'
                            % (_style_rounds, '、'.join(sorted(_style_held))))
            else:
                res.stop = '所有步骤都被跳过（没有还有指望的）'
            break
        if t == max(1, int(trials)):
            res.stop = f'到轮数上限 {trials}'

    # ★★★ **取 archive 里最好的那一版**，不是"最后跑出来的那一版"。
    #   这一条修的是老代码的一个真缺陷：`if after < best` 在**同分**时保留原文，
    #   于是"第 1 轮修好了两处、第 2 轮同分"会把第 1 轮整份丢掉 —— 等于白跑。
    best = archive[0]
    for item in archive[1:]:
        if V.better((item[0], item[1]), (best[0], best[1])):
            best = item
    res.text = best[1]
    res.best_trial = best[2]
    res.best_weighted = best[0].weighted
    res.best_total = best[0].total
    if best[2] and best[1] != cur:
        log.info('反思（%s）：取第 %d 轮那一版（%d 处 / 加权 %.1f），'
                 '比最后的 %d 处更好', tag, best[2], best[0].total,
                 best[0].weighted, V.Score.of(cur).total)
    log.info('反思（%s）：%s', tag, res.summary())
    return res


def record_path(root: str | Path, name: str = '教训.jsonl') -> Path:
    """教训库的默认落点。放在运行文件夹里，**跟稿子在一起** ——
    下次导出/复盘时能回答"当时为什么这么改"。"""
    return Path(root) / '反思' / name


def stamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


__all__ = ['Lesson', 'Memory', 'Result', 'reflect', 'verbalize',
           'first_span', 'record_path', 'stamp', 'MEMORY_CAP', 'BRIEF_MAX']
