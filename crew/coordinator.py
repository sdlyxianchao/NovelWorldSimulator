# -*- coding: utf-8 -*-
"""总体协调引擎（Coordinator）：运行窗口底部输入框的总入口。

## 它是干嘛的

用户在这个框里用自然语言说话（"让导演今天多写点感情戏""整体节奏放慢一点"
"让王二这一拍别那么冲动"）。协调引擎把这句话**解析**成一类操作，立刻改写
对应 Agent 的**实时行为指令**，并让它在**下一拍推演就生效**——不用重启。

支持的三类操作（即用户授权的范围）：

| 类别 | target | 落到哪 |
|---|---|---|
| 某个剧组职位（14 个职位之一） | 职位 key | `craft_block` 末尾第 ⑥ 段 |
| 某个在场人物 | 演员名 | `Agent.decide` 半固定层第 ⑧ 段 |
| 全局故事走向 / 整体风格 | （无） | 同时进上面两处（对所有人都生效） |

做不了的操作（比如"把模型换成 XXX""导出 PDF"）→ 明确告诉用户：我做不了，
请去「天机」里手动操作。

## 为什么是「单例 + 注入点每次现读」

- 剧组**唯一**注入口 `crew/agents.craft_block` 末尾、演员**唯一**半固定层
  `agent/core.Agent.decide` 第 ⑦ 段之后，都**每次调用现读**本单例的指令
  （惰性 import，不缓存）。所以协调引擎改了指令，下一拍就生效。
- 指令按「职位 key / 演员名」分桶，外加一条全局指令（对所有职位与演员都生效）。

## 解析策略：LLM 优先 + 关键词降级

1. 先用 `llm.replies.ask('cheap', …)` 把自然语言解析成结构化指令
   （`{type, target, instruction}`）；
2. 没配模型 / 解析失败 / 不在已知范围 → 降级成关键词匹配（职位显示名、演员名、
   全局词）；
3. 都认不出 → 当成「做不了」回报，绝不假装成功。

★ 整个 `handle()` **绝不抛异常**：任何一步出错都变成「做不了」回报，
  免得运行窗口的输入框一卡就把推演线程带崩。

        English:
    Overall Coordinator engine: the entry point behind the run-window bottom input box.
    See module header (Chinese) for the full design. In short: parse natural language from the
    user into one of three operation classes (a crew position / an on-stage actor / the global
    story direction), write the real-time directive immediately, and have it take effect on the
    next beat. Unsupported operations are reported honestly. `handle()` never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from i18n import t

_LOG = logging.getLogger("nws.crew.coordinator")

# 「全局故事走向」类的关键词（命中即归到 global，不走具体职位/人物）。
# [EN] Keywords that signify "global story direction" (route to global, not a specific role/actor).
_GLOBAL_KEYWORDS = (
    '全局', '整体', '总体', '故事走向', '走向', '总基调', '整体风格', '全剧',
    '整本书', '通篇', '基调',
)

# 「做不了」时给用户的去处提示（告诉 TA 去哪手动操作）。
# [EN] Where to point the user when the engine can't do something.
_DO_IT_YOURSELF = t('我做不了这件事，请去「天机」里手动操作（或在「起笔」对话框里写明这一轮的意图）。')


def _resp(ok: bool, applied: list[str], unsupported: list[str], summary: str) -> dict:
    """统一回包。
        English:
    Uniform response packet.
    """
    return {
        'ok': bool(ok),
        'applied': list(applied),
        'unsupported': list(unsupported),
        'summary': summary or '',
    }


class Coordinator:
    """单例：持有三类实时指令，提供「解析 → 写入 → 读取」接口。

        English:
    Singleton holding the three kinds of real-time directives, with parse / write / read APIs.
    """

    _inst: "Coordinator | None" = None

    def __init__(self) -> None:
        # 职位 key -> 指令文本
        # [EN] position key -> directive text
        self._crew: dict[str, str] = {}
        # 演员名 -> 指令文本
        # [EN] actor name -> directive text
        self._actors: dict[str, str] = {}
        # 全局指令（对所有职位与演员都生效）
        # [EN] global directive (effective for everyone)
        self._global: str = ''

    @classmethod
    def instance(cls) -> "Coordinator":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    # ── 读取接口（注入点调用，每次现读）──────────────────────────────
    # [EN] ── Read APIs (called by injection points, fresh every read) ──
    def crew_directive(self, key: str) -> str:
        """某职位该读的指令：全局 + 职位专属。空串 = 无。

                English:
            The directive this position should read: global + position-specific. Empty = none.
        """
        parts = [self._global, self._crew.get(str(key or ''), '')]
        return '\n'.join(p for p in parts if p).strip()

    def actor_directive(self, name: str) -> str:
        """某演员该读的指令：全局 + 演员专属。空串 = 无。

                English:
            The directive this actor should read: global + actor-specific. Empty = none.
        """
        parts = [self._global, self._actors.get(str(name or ''), '')]
        return '\n'.join(p for p in parts if p).strip()

    def global_directive(self) -> str:
        """全局故事走向指令（空串 = 无）。
                English:
            Global story-direction directive (empty = none).
        """
        return self._global

    # ── 写接口 ──────────────────────────────────────────────────────
    # [EN] ── Write APIs ──
    def set_crew(self, key: str, text: str) -> None:
        key = str(key or '').strip()
        text = (text or '').strip()
        if text:
            self._crew[key] = text
        else:
            self._crew.pop(key, None)

    def set_actor(self, name: str, text: str) -> None:
        name = str(name or '').strip()
        text = (text or '').strip()
        if text:
            self._actors[name] = text
        else:
            self._actors.pop(name, None)

    def set_global(self, text: str) -> None:
        self._global = (text or '').strip()

    def clear_all(self) -> None:
        """清空全部指令（测试用，或用户说"复位"时）。
                English:
            Clear all directives (for tests, or when the user says "reset").
        """
        self._crew.clear()
        self._actors.clear()
        self._global = ''

    # ── 解析 + 应用 ────────────────────────────────────────────────
    # [EN] ── Parse + apply ──
    async def handle(self, text: str,
                     on_stage_names: Iterable[str] | None = None) -> dict:
        """分析一句自然语言，落到一类操作上并立即生效。

        返回 dict：`{ok, applied, unsupported, summary}`。永不抛异常。

        - `applied`：已生效的操作说明列表
        - `unsupported`：做不了 / 不支持的操作说明列表
        - `summary`：给人看的一句话总结

                English:
            Analyze one natural-language sentence, route to an operation class, apply immediately.
            Returns `{ok, applied, unsupported, summary}`. Never raises.
        """
        raw = (text or '').strip()
        if not raw:
            return _resp(False, [], [], t('没收到任何内容'))
        on_stage = set(on_stage_names or [])
        try:
            parsed = await self._parse_llm(raw, on_stage)
            if parsed is None:
                parsed = self._parse_keyword(raw, on_stage)
            if parsed is None:
                return _resp(False, [], [_DO_IT_YOURSELF],
                             t('暂时做不到：{x}', x=raw[:40]))
            applied, unsupported = self._apply(parsed, on_stage)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('协调引擎处理失败（按做不了回报）：%r', e)
            return _resp(False, [], [t('处理时出错了：{e}', e=str(e))],
                         t('处理失败'))
        if not applied and not unsupported:
            unsupported = [_DO_IT_YOURSELF]
        summary = '；'.join(applied) if applied else '；'.join(unsupported)
        return _resp(bool(applied), applied, unsupported, summary)

    async def _parse_llm(self, raw: str, on_stage: set[str]) -> dict | None:
        """用 LLM 把自然语言解析成 `{type, target, instruction}`。失败返回 None。
                English:
            Use the LLM to parse natural language into `{type, target, instruction}`.
            Returns None on failure.
        """
        try:
            from llm.replies import ask
            from crew import roster as R
        except Exception:                                        # noqa: BLE001
            return None
        try:
            crew_roles = [r for r in R.roles() if r.kind == 'crew']
        except Exception:                                        # noqa: BLE001
            return None
        if not crew_roles:
            return None
        lines = '\n'.join(f'- {r.key}：{r.name}（{r.duty}）' for r in crew_roles)
        on_stage_list = '、'.join(sorted(on_stage)) if on_stage else t('（当前没有在场人物信息）')
        prompt = (
            "你是小说推演系统的协调引擎。用户用自然语言给剧组下指令。"
            "请把指令归类，并抽取出「目标」和「要它怎么做」。\n"
            f"可用的剧组职位（key：显示名）：\n{lines}\n"
            f"当前在场人物：{on_stage_list}\n\n"
            "归类规则：\n"
            "1) 针对某个剧组职位 → type=\"crew\"，target=该职位 key；\n"
            "2) 针对某个在场人物 → type=\"actor\"，target=该人物名；\n"
            "3) 针对整体故事走向 / 全局风格 → type=\"global\"，target=\"\"。\n\n"
            "只输出一个 JSON 对象，不要任何解释、不要 Markdown 代码块：\n"
            '{"type":"crew|actor|global","target":"<职位key 或 人物名，global 时留空>",'
            '"instruction":"<要给该 Agent 的具体行为指令，一句话，中文>"}'
            f"\n\n用户指令：{raw}"
        )
        try:
            rep = await ask(
                'cheap',
                [{'role': 'user', 'content': prompt}],
                purpose='coordinator', want=dict, max_tokens=600,
                temperature=0.1, json_mode=True, default=None,
            )
        except Exception:                                        # noqa: BLE001
            return None
        if not rep.ok or not isinstance(rep.value, dict):
            return None
        v = rep.value
        typ = str(v.get('type') or '').strip().lower()
        target = str(v.get('target') or '').strip()
        instr = str(v.get('instruction') or '').strip()
        if typ not in ('crew', 'actor', 'global') or not instr:
            return None
        if typ == 'crew':
            keys = {r.key for r in crew_roles}
            if target not in keys:
                # 也允许用显示名匹配
                for r in crew_roles:
                    if target == r.name:
                        target = r.key
                        break
                else:
                    return None
        return {'type': typ, 'target': target, 'instruction': instr}

    def _parse_keyword(self, raw: str, on_stage: set[str]) -> dict | None:
        """降级：关键词匹配。失败返回 None。
                English:
            Fallback: keyword matching. Returns None on failure.
        """
        # 1) 全局故事走向
        if any(k in raw for k in _GLOBAL_KEYWORDS):
            return {'type': 'global', 'target': '', 'instruction': raw}
        # 2) 在场人物（名字出现在指令里，长名优先）
        for nm in sorted(on_stage, key=len, reverse=True):
            if nm and nm in raw:
                return {'type': 'actor', 'target': nm, 'instruction': raw}
        # 3) 剧组职位（显示名或 key 命中）
        try:
            from crew import roster as R
            crew_roles = [r for r in R.roles() if r.kind == 'crew']
        except Exception:                                        # noqa: BLE001
            return None
        for r in crew_roles:
            if r.name in raw or r.key in raw:
                return {'type': 'crew', 'target': r.key, 'instruction': raw}
        return None

    def _apply(self, parsed: dict, on_stage: set[str]) -> tuple[list[str], list[str]]:
        """把解析结果落到指令表里。返回 (applied, unsupported)。
                English:
            Apply the parsed result to the directive tables. Returns (applied, unsupported).
        """
        applied: list[str] = []
        unsupported: list[str] = []
        typ = parsed['type']
        target = parsed['target']
        instr = parsed['instruction']
        if typ == 'global':
            self.set_global(instr)
            applied.append(t('已更新全局故事走向（对所有 Agent 生效）'))
        elif typ == 'crew':
            self.set_crew(target, instr)
            nm = target
            try:
                from crew import roster as R
                for r in R.roles():
                    if r.key == target:
                        nm = r.name
                        break
            except Exception:                                    # noqa: BLE001
                pass
            applied.append(t('已更新「{n}」的行为指令', n=nm))
        elif typ == 'actor':
            if on_stage and target not in on_stage:
                unsupported.append(
                    t('「{n}」当前不在场，没法给 TA 下实时指令（TA 不在这一拍里）',
                      n=target))
            elif not on_stage:
                # 没拿到在场名单（拿不到就当成"未知"），还是存一份，
                # 等 TA 在场时下一拍生效。
                self.set_actor(target, instr)
                applied.append(
                    t('已记下「{n}」的指令（下次 TA 在场时生效）', n=target))
            else:
                self.set_actor(target, instr)
                applied.append(t('已更新「{n}」的实时行为指令', n=target))
        return applied, unsupported
