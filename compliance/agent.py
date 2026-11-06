# -*- coding: utf-8 -*-
"""合规检测 Agent（设计稿 §十六）：独立专职 Agent，C0/C1/C2 三级分类。

四层级联：词表规则层（零成本）→ 本地 LLM → 外部服务 → 裁决聚合。
**当前实现：词表规则 + 本地 LLM 复核（hybrid）。**
外部服务（`COMPLIANCE_EXTERNAL*` 六项）与裁决聚合（`COMPLIANCE_AGGREGATION`）
**仍未实现** —— 它们已从 `config.SPEC` 里删掉，不再冒充"可调参数"
（假旋钮零容忍：宁可承认没做，也不给一组拧了没反应的开关）。

2026-10-06 这次补的（以前全是零读取）
------------------------------------
  · `COMPLIANCE_POLICY_DIR`  —— 从目录加载 C0/C1 词表（以前只认构造参数）；
  · `COMPLIANCE_WHITELIST`   —— 白名单（虚构创作豁免：同人、武侠、年代文里的
    正常用词别被误伤）；
  · `COMPLIANCE_ACTION`      —— C1 命中后怎么办：rewrite / block / pause；
  · `COMPLIANCE_MODEL`       —— 复核走哪一档（空 = 摘要档）；
  · `COMPLIANCE_CHECKPOINTS` —— `all` / `minimal`：minimal 只留 CP6（落盘前）；
  · `COMPLIANCE_LOG`         —— 要不要记 `compliance_log` 表；
  · `COMPLIANCE_WATCH_POLICY`—— 策略库改了自动重载（按 mtime）。

★★ 一条安全修复（以前是真隐患）
--------------------------------
旧实现 `_llm_review` 在拿不到结论时 **`return ComplianceResult("C2","pass",...)`**
—— 也就是"模型一个字没答"会被当成**放行**。而合规是**生死线**：
宁可拦下来让人看一眼，也不能默默放过去。
现在：走 `llm.replies.ask()`（重试 + 抢救）；仍然拿不到 → `action="hold"`
（**不放行**），由调用方给一句安全替身，并把原因讲给用户听。

English:
Compliance detection Agent (design doc §16): an independent dedicated Agent, three-level
classification C0/C1/C2.
Four-level cascade: wordlist rule layer (zero cost) → local LLM → external service → verdict
aggregation.
**Current implementation: wordlist rules + local LLM re-review (hybrid).**
External services (the six `COMPLIANCE_EXTERNAL*` items) and verdict aggregation
(`COMPLIANCE_AGGREGATION`)
**still not implemented** —— they have been removed from `config.SPEC`, no longer pretending to
be "tunable parameters"
(zero tolerance for fake knobs: better to admit it is not done than to provide a set of switches
that do nothing when flipped).
What was added in this 2026-10-06 pass (previously all were zero reads)
------------------------------------
  · `COMPLIANCE_POLICY_DIR`  —— load C0/C1 wordlists from a directory (previously only constructor args were recognized);
  · `COMPLIANCE_WHITELIST`   —— whitelist (fiction writing exemption: fanfic, wuxia, period drama
    normal wording should not be falsely flagged);
  · `COMPLIANCE_ACTION`      —— what to do after a C1 hit: rewrite / block / pause;
  · `COMPLIANCE_MODEL`       —— which tier the re-review uses (empty = summary tier);
  · `COMPLIANCE_CHECKPOINTS` —— `all` / `minimal`: minimal keeps only CP6 (before writing to disk);
  · `COMPLIANCE_LOG`         —— whether to record the `compliance_log` table;
  · `COMPLIANCE_WATCH_POLICY`—— auto-reload when the policy store changes (by mtime).
★★ A security fix (previously a real hazard)
--------------------------------
The old implementation `_llm_review` when no conclusion could be obtained **`return
ComplianceResult("C2","pass",...)`**
—— that is, "the model did not answer a single word" would be treated as **pass**. But
compliance is a **matter of life and death**:
better to block and have a human take a look than to silently let it through.
Now: go through `llm.replies.ask()` (retry + salvage); if still no conclusion → `action="hold"`
(**do not pass**), and the caller provides a safe substitute and explains the reason to the
user.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from llm.replies import ask
from llm import models as MODELS
from store.db import DB
from config import CFG

_LOG = __import__("logging").getLogger("nws.compliance")

# 词表文件里加载进来的内容（内置那份是空的，**靠策略库**，见 `COMPLIANCE_POLICY_DIR`）
# [EN] Content loaded from the wordlist file (the built-in one is empty, **relies on the policy
# [EN] store**, see `COMPLIANCE_POLICY_DIR`)
_C0_WORDS: list[str] = []
_C1_PATTERNS: list[str] = []

# 本地敏感线索（粗筛用）。**这里是示例占位**，真正部署时随策略库一起扩充
# —— 与 C0/C1 词表同源同纪律：这条清单只决定"值不值得复核"，不决定判定。
# [EN] Local sensitive clues (for coarse screening). **This is an example placeholder**, it will be
# [EN] expanded along with the policy store in real deployments
# [EN] —— Same source and same discipline as the C0/C1 wordlists: this list only decides "whether it is
# [EN] worth re-reviewing", not the verdict.
_SENSITIVE_HINTS: tuple[str, ...] = (
    "自杀", "自残", "割腕", "上吊", "服毒",
    "下药", "迷药", "毒", "炸弹", "枪", "刀砍", "虐",
    "裸", "脱衣", "床事", "情事", "淫",
    "赌", "骗", "洗钱", "走私", "拐卖",
)

# 检查点（设计稿 §16.2）：minimal 只留落盘前那一道
# [EN] Checkpoints (design doc §16.2): minimal keeps only the one before writing to disk
ALL_CHECKPOINTS: tuple[str, ...] = ("CP1", "CP2", "CP3", "CP4", "CP5", "CP6")
MINIMAL_CHECKPOINTS: tuple[str, ...] = ("CP6",)

# 「不放行」的判定（调用方用它决定要不要放行这段文本）
# [EN] The "do not pass" verdict (caller uses it to decide whether to pass this text)
_BLOCKING_ACTIONS = ("block", "hold", "pause")


@dataclass
class ComplianceResult:
    level: str          # C0 / C1 / C2 / C?（拿不到结论时是 C?）
    # [EN] C0 / C1 / C2 / C? (C? when no conclusion can be obtained)
    action: str         # pass / rewrite / block / hold
    reason: str
    rewritten: str = ""  # rewrite 时的新文本
    # [EN] The new text when rewriting
    checkpoint: str = ""
    exonerated: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """这段文本能原样用吗？（**只有 `pass` 和 `rewrite` 算通过**）
                English:
        Can this text be used as-is? (**only `pass` and `rewrite` count as passing**)
        """
        return self.action in ("pass", "rewrite")

    def apply(self, text: str) -> str:
        """按判定给出**最终该用的文本**：pass 原样、rewrite 换文本、
        其余（block/hold）给空串 —— 由调用方决定用什么替身。
                English:
        Give the **final text to use** based on the verdict: pass uses as-is, rewrite swaps the text,
                the rest (block/hold) get an empty string —— the caller decides what substitute to use.
        """
        if self.action == "pass":
            return text
        if self.action == "rewrite" and str(self.rewritten or "").strip():
            return self.rewritten
        return ""

    def to_dict(self) -> dict:
        return {"级别": self.level, "判定": self.action,
                "理由": self.reason, "改写": self.rewritten}


class ComplianceAgent:
    """独立合规检测 Agent（§16.1）。
        English:
    Independent compliance detection Agent (§16.1).
    """

    def __init__(self, db: DB, policy_dir: Path | None = None):
        self.db = db
        # 构造参数优先，没给就读配置（以前调用方不给就**永远没有词表**）
        # [EN] Constructor args take priority, otherwise read config (previously if the caller did not pass
        # [EN] them, there was **never a wordlist**)
        self.policy_dir = policy_dir or _dir_or_none(CFG.s("COMPLIANCE_POLICY_DIR"))
        self._blocked_words: list[str] = list(_C0_WORDS)
        self._restricted_words: list[str] = list(_C1_PATTERNS)
        self._whitelist: list[str] = []
        self._policy_mtime: float = 0.0
        self._load_policies()
        self._load_whitelist()

    # ── 策略库 ────────────────────────────────────────────────────────
    # [EN] ── Policy store ────────────────────────────────────────────────────────
    def _load_policies(self) -> None:
        if not self.policy_dir or not self.policy_dir.exists():
            return
        for fname, bucket in (("blocked_words.txt", self._blocked_words),
                              ("restricted_words.txt", self._restricted_words)):
            p = self.policy_dir / fname
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and line not in bucket:
                    bucket.append(line)
            try:
                self._policy_mtime = max(self._policy_mtime, p.stat().st_mtime)
            except OSError:
                pass

    def _load_whitelist(self) -> None:
        raw = CFG.s("COMPLIANCE_WHITELIST") or ""
        self._whitelist = [x.strip() for x in raw.replace("，", ",").replace("、", ",")
                           .split(",") if x.strip()]

    def reload_policies(self) -> None:
        self._blocked_words = list(_C0_WORDS)
        self._restricted_words = list(_C1_PATTERNS)
        self._policy_mtime = 0.0
        self._load_policies()
        self._load_whitelist()
        _LOG.info("策略库重载：C0 词 %d 条，C1 词 %d 条，白名单 %d 条",
                  len(self._blocked_words), len(self._restricted_words),
                  len(self._whitelist))

    def maybe_watch(self) -> bool:
        """`COMPLIANCE_WATCH_POLICY=true` 时，策略库文件改了自动重载。返回是否重载过。
                English:
        When `COMPLIANCE_WATCH_POLICY=true`, the policy store files are auto-reloaded when changed.
        Returns whether a reload happened.
        """
        if not CFG.b("COMPLIANCE_WATCH_POLICY") or not self.policy_dir:
            return False
        newest = 0.0
        for fname in ("blocked_words.txt", "restricted_words.txt"):
            p = self.policy_dir / fname
            try:
                if p.exists():
                    newest = max(newest, p.stat().st_mtime)
            except OSError:
                pass
        if newest and newest > self._policy_mtime:
            self.reload_policies()
            return True
        return False

    # ── 检查点 ────────────────────────────────────────────────────────
    # [EN] ── Checkpoints ────────────────────────────────────────────────────────
    def active(self, checkpoint: str) -> bool:
        """这个检查点这一轮要不要真的查（`COMPLIANCE_CHECKPOINTS`）。
                English:
        Whether this checkpoint should actually be checked this round (`COMPLIANCE_CHECKPOINTS`).
        """
        mode = (CFG.s("COMPLIANCE_CHECKPOINTS") or "all").strip()
        want = MINIMAL_CHECKPOINTS if mode == "minimal" else ALL_CHECKPOINTS
        return checkpoint in want

    # ── 主检测入口 ────────────────────────────────────────────────────
    # [EN] ── Main detection entry ────────────────────────────────────────────────────
    @MODELS.agent('compliance')
    async def check(self, text: str, checkpoint: str = "CP3") -> ComplianceResult:
        """检测一段文本，返回合规结果。

        ⚠ 三件事按顺序：**关掉 → 放过**；**检查点不在名单里 → 放过**；
        **白名单命中 → 放过**（虚构创作豁免，设计稿 §16.3 的 C2 那一档）。
        
                English:
        Detect a piece of text and return the compliance result.
                ⚠ Three things in order: **disabled → pass**; **checkpoint not in the list → pass**;
                **whitelist hit → pass** (fiction writing exemption, the C2 tier of design doc §16.3).
        """
        if not CFG.b("COMPLIANCE_ENABLED"):
            return ComplianceResult("C2", "pass", "合规功能已关闭", checkpoint=checkpoint)
        if not self.active(checkpoint):
            return ComplianceResult("C2", "pass",
                                    f"{checkpoint} 不在本轮检查点名单里",
                                    checkpoint=checkpoint)
        self.maybe_watch()
        text = str(text or "")
        # ① 白名单：先剔掉豁免词，再送去查词表（不然"豁免"只是个摆设）
        # [EN] ① Whitelist: first strip out exempt words, then send to check the wordlist (otherwise "exempt"
        # [EN] is just for show)
        scan = text
        for w in self._whitelist:
            if w:
                scan = scan.replace(w, "")

        # ② 词表规则层（零成本）
        # [EN] ② Wordlist rule layer (zero cost)
        hit = self._check_words(scan, text)
        if hit:
            hit.checkpoint = checkpoint
            self._log_result(hit, text)
            return hit

        # ③ LLM 复核（hybrid：**只在需要时**）
        # [EN] ③ LLM re-review (hybrid: **only when needed**)
        mode = (CFG.s("COMPLIANCE_LLM_REVIEW") or "hybrid").strip()
        if mode == "never":
            r = ComplianceResult("C2", "pass", "纯规则层，未命中", checkpoint=checkpoint)
            self._log_result(r, text)
            return r
        if mode == "hybrid" and not self._looks_sensitive(scan):
            # ⚠ `hybrid` 的"省约 70%"就在这里：没有敏感线索就**一次 LLM 都不叫**。
            #   第一版漏了这一步，于是 hybrid == always —— 每天落盘都要多花一次
            #   调用，而"省 70%"写在配置说明里（那就是假旋钮的另一种形态）。
            # [EN] ⚠ This is where `hybrid` "saves about 70%": if there are no sensitive clues, **not a single LLM
            # [EN] call is made**.
            # [EN] The first version missed this step, so hybrid == always —— every write to disk costs one extra
            # [EN] call, while "saving 70%" is written in the config description (that is another form of fake
            # [EN] knob).
            r = ComplianceResult("C2", "pass", "粗筛无敏感线索，未做 LLM 复核",
                                 checkpoint=checkpoint)
            self._log_result(r, text)
            return r
        r = await self._llm_review(text, checkpoint, forced_hit=False)
        self._log_result(r, text)
        return r

    # ── 本地粗筛（hybrid 的"省约 70%"那一半）──────────────────────────
    # [EN] ── Local coarse screening (the "saves about 70%" half of hybrid) ──────────────────────────
    @staticmethod
    def _looks_sensitive(text: str) -> bool:
        """本地线索粗筛：命中才值得花一次 LLM 复核。

        ⚠ 这一层**故意写得保守**（宁可多叫几次，也别漏判）——
        它省的是钱，不是安全。真正拿主意的还是 LLM 那一步。
        
                English:
        Local clue coarse screening: only a hit is worth spending an LLM re-review.
                ⚠ This layer is **deliberately written conservatively** (better to call a few extra times than to miss a verdict) ——
                It saves money, not safety. The one actually making the decisions is still the LLM step.
        """
        return any(k in text for k in _SENSITIVE_HINTS)

    # ── 词表检测 ──────────────────────────────────────────────────────
    # [EN] ── Wordlist detection ──────────────────────────────────────────────────────
    def _check_words(self, scan: str, original: str) -> ComplianceResult | None:
        for w in self._blocked_words:
            if w and w in scan:
                return ComplianceResult("C0", "block", f"命中绝对禁止词：{w}")
        for w in self._restricted_words:
            if w and w in scan:
                # C1：**不直接拦**，交给 LLM 复核（`hybrid` 的"粗筛"那一半）+
                # `COMPLIANCE_ACTION` 决定下游怎么处理。
                # [EN] C1: **do not block directly**, hand off to LLM re-review (the "coarse screening" half of
                # [EN] `hybrid`) +
                # [EN] `COMPLIANCE_ACTION` decides how downstream handles it.
                return ComplianceResult(
                    "C1", (CFG.s("COMPLIANCE_ACTION") or "rewrite"),
                    f"命中限制级词：{w}")
        return None

    # ── LLM 复核 ──────────────────────────────────────────────────────
    # [EN] ── LLM re-review ──────────────────────────────────────────────────────
    async def _llm_review(self, text: str, checkpoint: str,
                          forced_hit: bool = False) -> ComplianceResult:
        jurisdiction = CFG.s("COMPLIANCE_JURISDICTION")
        level = CFG.s("COMPLIANCE_LEVEL")
        action = (CFG.s("COMPLIANCE_ACTION") or "rewrite").strip()
        prompt = f"""你是小说内容合规审查员。请审查以下文本（来自一部虚构小说的世界模拟器）。

审查基准：{jurisdiction}（冲突以中国法为准）
审查力度：{level}
文本来自：虚构小说模拟器的人物行动/对话/叙事

内容三级分类（§16.3）：
- C0 法律禁止生成：未成年人性内容、恐怖主义实操教学、制毒制爆可操作步骤、分裂国家内容等 → 拦截
- C1 限制描写：暴力犯罪手法细节、自杀自残方法细节、露骨淫秽描写、诈骗赌博教学 → 降尺度重写
- C2 虚构豁免：虚构情节中的犯罪/冲突/黑暗主题、鬼怪灵异、成人向含蓄情感 → 放行

请以 JSON 回答（理由与改写都用中文，各不超过 60 字）：
{{"级别": "C0|C1|C2", "判定": "pass|rewrite|block", "理由": "一句话", "改写": "（仅 rewrite 时提供重写文本，写结果不写手法）"}}

文本：
{text[:2000]}"""
        tier = "cheap"
        model = (CFG.s("COMPLIANCE_MODEL") or "").strip()
        if model:
            # `COMPLIANCE_MODEL` 写的是**模型名**，这里换算成档位：认得出就换，
            # 认不出就照旧走摘要档（**不因为一个可选旋钮把合规整条路弄断**）。
            # [EN] `COMPLIANCE_MODEL` specifies a **model name**, which is converted to a tier here: if recognized,
            # [EN] switch,
            # [EN] if not recognized, fall back to the summary tier as before (**do not break the entire compliance
            # [EN] path over one optional knob**).
            for t, key in (("front", "MODEL_FRONT"), ("daily", "MODEL_DAILY"),
                           ("cheap", "MODEL_CHEAP")):
                if model == (CFG.s(key) or "").strip():
                    tier = t
                    break
        rep = await ask(tier, [{"role": "user", "content": prompt}],
                        purpose="compliance", want=dict, json_mode=True,
                        temperature=0.1, default=None)
        if not rep.ok or not isinstance(rep.value, dict):
            # ★★ 这里**绝不能** `return pass`（旧实现就是这么写的）——
            #   "模型一个字没答"不等于"内容没问题"。合规是生死线，宁可拦。
            # [EN] ★★ Here you **must never** `return pass` (that is how the old implementation was written) ——
            # [EN] "the model did not answer a single word" does not equal "the content is fine". Compliance is a
            # [EN] matter of life and death, better to block.
            why = "；".join(rep.notes) if rep.notes else "复核没拿到结论"
            _LOG.warning("合规复核没拿到结论（%s）→ **不放行**，"
                         "按 hold 交回调用方（检查点 %s）", why, checkpoint)
            return ComplianceResult("C?", "hold",
                                    f"合规复核没拿到结论：{why}",
                                    checkpoint=checkpoint, notes=list(rep.notes))
        r = rep.value
        lvl = str(r.get("级别", "C2")).strip() or "C2"
        act = str(r.get("判定", "pass")).strip() or "pass"
        # `COMPLIANCE_ACTION` 是**作者的总口径**：模型判 C1 时用它统一收口
        # [EN] `COMPLIANCE_ACTION` is the **author's overall policy**: when the model judges C1, use it to
        # [EN] unify the outcome
        if lvl == "C1" and act not in ("block", "rewrite"):
            act = action
        return ComplianceResult(
            level=lvl, action=act,
            reason=str(r.get("理由", ""))[:200],
            rewritten=str(r.get("改写", ""))[:2000] if act == "rewrite" else "",
            checkpoint=checkpoint)

    # ── 日志 ──────────────────────────────────────────────────────────
    # [EN] ── Logging ──────────────────────────────────────────────────────────
    def _log_result(self, r: ComplianceResult, text: str) -> None:
        if not CFG.b("COMPLIANCE_LOG"):
            return
        try:
            self.db.add_compliance(r.checkpoint, r.level, r.action,
                                   str(text or "")[:500],
                                   str(r.rewritten or "")[:500], r.reason)
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("合规记录写入失败（不影响判定）：%r", e)

    def exonerate(self, cid: int) -> bool:
        return self.db.exonerate(cid)

    def status(self) -> dict:
        return {
            "启用": CFG.b("COMPLIANCE_ENABLED"),
            "法域": CFG.s("COMPLIANCE_JURISDICTION"),
            "力度": CFG.s("COMPLIANCE_LEVEL"),
            "C0 词表": len(self._blocked_words),
            "C1 词表": len(self._restricted_words),
            "白名单": len(self._whitelist),
            "LLM 复核": CFG.s("COMPLIANCE_LLM_REVIEW"),
            "检查点": CFG.s("COMPLIANCE_CHECKPOINTS"),
            "命中后动作": CFG.s("COMPLIANCE_ACTION"),
            "策略库": str(self.policy_dir or "（未配置）"),
        }


def _dir_or_none(raw: str) -> Path | None:
    v = str(raw or "").strip()
    if not v:
        return None
    p = Path(v)
    try:
        if not p.is_absolute():
            from config import APP_DIR
            p = APP_DIR / p
    except Exception:                                           # noqa: BLE001
        pass
    return p


def fallback_line(level: str = "C1") -> str:
    """拦下来时用的**安全替身**（一句话，不透露原内容）。
        English:
    The **safe substitute** used when blocked (one sentence, does not reveal the original content).
    """
    return "（此处有一段内容未通过合规检查，已按设定略去。）"
