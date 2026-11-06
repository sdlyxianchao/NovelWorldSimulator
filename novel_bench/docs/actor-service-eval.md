# 外部"演员模拟服务"评估（2026-10-18）

> 用户在 2026-10-18 问："之前提到的用外部开源评价好的演员模拟服务来优化现在演员功能的你做了吗"
>
> **诚实回答：调研做了，实现没做。** 2026-10-17 的调研结论停在"等用户拍板"，
> 之后没再推进。本文档把当时的结论、为什么停、以及**现在能怎么验证**写清楚。

---

## 1. 现在是什么状态

| 事项 | 状态 |
|---|---|
| 调研"能不能接外部演员服务" | ✅ 做过（2026-10-17，见 `memory/2026-10-17.md`） |
| 起过任何一个候选服务 | ❌ 没起过，活跃度/安装难度/是否有"杀邻居进程"的坑**全都未知** |
| 改过演员的模型来源 | ❌ 没改 |
| 用评测量化"换模型有没有用" | ❌ 当时**没有评测工具**，做不了；现在有了 |

**为什么当时停了**：调研得出的结论是"先别接"。理由见下。

---

## 2. 当时的结论：三条错位

### ① 交互型 vs 对戏型

角色扮演类服务（Talemate、Elma-Roleplay、SillyTavern 系）都预设
**"有一个用户在跟角色聊天"**。而这个项目**没有用户** —— 是 N 个 NPC 互相演。

适配时要把"用户发言"换成"上一拍剧情"，每个演员映射成一个角色，每拍给每个在场角色
各发一次生成。**这不是接个 API，是改写它们的会话模型。**

### ② 它们不自带模型

Talemate 底下要接 KoboldCpp / oobabooga / LMStudio / Ollama / OpenAI；
Elma 同样要接后端。

⇒ **如果底下接的还是现在的 `hy3`，台词不会变好，只是多绕一层编排。**

### ③ 会架空现有的四层提示词

外接服务有自己的提示词体系（角色卡 / lorebook / 预设），
等于放弃项目攒的 P0 固定层 + 半固定层 + 动态层 + 尾段那套手艺
（`agent/core.py` 四层 + `prompts/agent_decide_tail.txt` 3000 字）。

⇒ 接之前必须回答：**它凭什么比现有四层强？**

---

## 3. 真正决定台词质量的是什么（当时的判断，现在可验证）

> **让台词变好的是模型本身，不是外面套的编排层。**

这条判断在项目里是**一行改动**就能试的：

```
agents/actor.md 的 frontmatter
---
tier: daily
model: hy3        ← 换这里
---
```

路由已经支持（`llm/models.resolve()`：`agent` → `tier` → 默认 → 第一条），
所以改一行就生效，不需要动代码。

**现在可以用 `novel_bench` 量化它**：
同一个用例、同样的拍数，只换 `actor.md` 的 `model`，比 `character` 维度。

---

## 4. 候选清单（当时选的，未实测）

| 类别 | 候选 | 备注 |
|---|---|---|
| 完整应用（最贴 MuMuAINovel 形态） | **Talemate**（`aleph23/talemate`） | 自称"strong narration + consistent world and game state tracking"；多 agent 分工；world state 管理就是"人设一致性"；提示词 Jinja2 可改；有 Dockerfile |
| 完整应用 | **Elma-Roleplay**（`Elma-Eimy/Elma-Roleplay`，中文） | 结构化 XML 响应契约，**支持多角色台词与旁白混合**（最贴"一场戏多人对戏"）；Graph RAG 记忆；有 `/compile_prompt` 可观测 |
| 前端编排器（**不是服务**，先排除） | SillyTavern / Agnai / RisuAI | 自己不生成，必须接后端模型 |
| 评测基准（**不是服务**，只借思路） | TRACE Bench | 把角色卡拆成固定检查表逐条核状态 —— 这个思路可以**自己实现**，不用接服务 |
| TTS（用户明确不要） | CosyVoice / GPT-SoVITS | 声音不在本期范围 |

---

## 5. 我的建议：先做三件不需要外接的事

按性价比排序，都能用现有工具量化：

### 5.1 换演员模型（一行，最便宜）

`agents/actor.md` 的 `model:` 从 `hy3` 换成更强的（如 `deepseek-v4-pro`），
跑同一批用例比 `character` 分。

- 若 `character` 明显上升 ⇒ **台词质量主要受模型限制**，外接编排层的边际收益很低，
  这条路先不用走。
- 若基本不动 ⇒ 说明瓶颈在**提示词或人设供给**，那外接服务（世界状态管理）才有意义。

### 5.2 人设一致性检查表（照 TRACE 的思路自己实现）

项目**完全没有**这个能力：

- 现有防漂移只有选角两层 + `ARBITRATION`；
- `_persona_key` 只做缓存判等，**不校验一致性**；
- `ConsistencyContract` 是**场记**那条线，不管演员。

而 `PersonState` 已经有 identity / personality / catchphrase / secret / goal / redline
—— **天然就是一张检查表**。做法：每拍结束后抽 1 个角色，核"这一拍有没有违反红线/
秘密有没有说漏/口癖在不在"，超限就记进台账。

### 5.3 记忆与上下文（不接服务也能修）

2026-10-17 调研查到的现有瓶颈（都还没修）：

| 瓶颈 | 位置 | 修法 |
|---|---|---|
| 记忆只喂 5 条 | `core.py` `memories[:5]`（配置默认 8，被截断） | 一行 |
| 无语义检索 | `store/db.py` 用 CJK 二元组 + Jaccard | 只换检索那一段，不必换整套 |
| 温度硬编码 0.7 | `core.py`，`config.py` 里没有温度开关 | 加配置项 |
| 上下文超预算先裁记忆 | `llm/context.py` `trim_dynamic` | 裁错地方了 |

---

## 6. 如果确实要外接，需要的步骤

1. **先起一次** Talemate（Docker）或 Elma，确认能跑、能调 API；
   ⚠ 特别注意有没有 PlotPilot 那种"按关键字 `uvicorn` 清进程"的行为
   （`novelservices/` 里踩过，会误杀 PenShot）。
2. 写 `novelservices/xxx_bridge.py`（模板现成：`BridgeStatus/BridgeResult/Task` +
   `service_url/service_status/start_service/stop_service/generate_*/describe`）。
3. `config.py` 加 `XXX_ENABLED` / `XXX_AUTOSTART`(必须是 `restart=True`) / `XXX_TIMEOUT_SECONDS`
   —— ⚠ `AUTOSTART` 键必须**独立整行的字面量**（`mutate_borrowings` 按整行替换）。
4. `agent/core.py` 的 `decide()` 里加"先调外部、失败回退"的结构
   （现在**没有**这个结构，要新写）。
5. 用 `novel_bench` 跑 A/B：`character` + `canon` 两个维度，同一个用例、同样拍数。

**纪律**（`novelservices/__init__.py` 三条）：可有可无 / 不写死盘符 / 桥是纯标准库。
服务缺席时**不许**改主程序退出码、启动时不许弹窗。

---

## 7. 待办

- [ ] 5.1 换演员模型 A/B（等当前这批模拟跑完，避免混版本）
- [ ] 5.2 人设一致性检查表（照 TRACE 思路，自己做）
- [ ] 起一次 Talemate，只确认"能不能跑通"，不做集成
