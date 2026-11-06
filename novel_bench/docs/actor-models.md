# 演员用什么模型（2026-10-18 调研）

> 起因：用户问「有什么演员专用大模型吗」。
> 查下去先发现一件更要紧的事：**演员现在跑的模型不是你以为的那个。**

---

## 1. 先说实测：演员用的是 `hy3`，不是 `deepseek-flash`

`.env` 里写着 `MODEL_DAILY=deepseek-flash`，但 `agents/actor.md` 的 frontmatter 里有 `model: hy3`
——**职位文件优先于全局兜底**（`llm/models.resolve()` 的 `src=agent` 就是证据）。

```python
resolve('actor')  ->  model=hy3  src=agent
```

`logs/llm_calls.jsonl` 里按用途统计（共 1237 次调用，10-17 15:26 起）：

| 用途 | 模型 | 次数 |
|---|---|---|
| `agent_decide`（演员做决策） | **hy3** | 397 |
| `day_script`（编剧） | **hy3** | 59 |
| `crew_day_novel`（小说作家） | **hy3** | 23 |
| 其余（评委、开场等） | deepseek-flash | 470 |

**一次 deepseek-flash 都没演过戏。**

### 1.1 连带结论：上一轮「思考模式 A/B」是空跑，作废

`hy3` 默认思考（应答里 `reasoning_tokens` 几乎等于全部输出）。
`detect_thinking_switch('hy3')` 返回 `False` —— 因为那张表**只认 deepseek 系的名字**
—— 所以程序从来不给它发 `thinking: {"type": "disabled"}`。

⇒ `--think-mode off` 对演员**一个字节都没发出去**。`ab-off3` vs `ab-auto3` 那个
38 → 50 的差距是**单例随机噪声**，不是思考开关的效果。
⇒ 「不该关思考」这个结论**没有证据支持**——既不能说它对，也不能说它错。

### 1.2 但实测：hy3 **能**关，是程序拦住了

用同一个提示、同一个 `max_tokens=300`，直接打 hy3 的接口：

| 参数 | 输出 token | 其中思考 | 正文 |
|---|---|---|---|
| 默认 | 25 | 22 | 「可用」 |
| `thinking: {"type": "disabled"}` | **2** | **0** | 「可用」 |
| `enable_thinking: false` | 23 | 20 | 「可用」（**无效**） |
| `reasoning_effort: "none"` | **2** | **0** | 「可用」（有效） |

⇒ 开关是有效的，`detect_thinking_switch()` 那张**按模型名写死的白名单**把它挡在外面。
这是**能力检测的漏洞**，不是模型不支持。

代价有多大：`agent_decide` 的输出 token 中位数 **2967**、最大 **23307**，
其中绝大部分是思考。按输出计价的话，这是本项目**最大的一笔可省开销**。

⚠ 但**不能直接关**：思考在承担空间动线、谁知道什么这类一致性
（`ops1` 里验算器抓到过「黛玉年龄写成六岁」「凤姐走位不成立」，那是真硬伤）。
要先用 `novel_bench` 做一次**真正的** A/B，再决定。

---

## 2. 确实有「演员专用」模型，分三类

### 2.1 厂商的「角色扮演专用」API（最省事，OpenAI 兼容）

| 模型 | 谁做的 | 上下文 | 参考价（元/百万 token 输入·输出） | 备注 |
|---|---|---|---|---|
| **Doubao Seed Character** | 字节 · 火山方舟 | 131K–256K | 约 ¥0.8 / ¥2.0 | 明确为「角色对话、人设稳定」优化；OpenAI 兼容，改 `base_url` + `model` 即可 |
| **CharGLM-4** | 智谱 | **8K** | 按官网 | 「角色扮演专用」定位很清楚，但 **8K 装不下群像 + 前情**，本项目基本用不了 |
| **MiniMax-M2-her** | MiniMax | 长 | 按官网 | 见下方榜单：**目前公开数据里最强的一个** |
| `venice/venice-role-play-uncensored` | Venice | 128K | $0.5 / $2.0 | 英文取向，中文弱；内容尺度宽松 |

### 2.2 开源社区微调（要自己部署，中文普遍弱）

这些是 `SillyTavern` 圈的事实标准，全部基于 Llama / Mistral / Qwen 微调：

- **Sao10K/L3.1-70B-Euryale-v2.2** —— 公认综合最强，但 70B 要有卡
- **TheDrummer/Cydonia-24B** —— 24B 档的性价比之选
- **Mistral-Nemo-12B 系**（Pantheon-RP / NemoRemix / Lumimaid） —— 12B / 10GB 显存
- **MN-Violet-Lotus-12B** —— 情绪细节强
- **MythoMax-L2-13B** —— 老经典，长文连贯性好

⚠ 全部以英文语料为主，写中文民国/明清白话会掉链子。本项目**不建议**走这条。

### 2.3 通用旗舰（不是「专用」，但榜单上就是它们高）

---

## 3. 榜单：专用 vs 通用，谁真的强

唯一一个公开、可复现、**长程 + 人类校准**的中文可用基准是 MiniMax 发布的
`MiniMaxAI/role-play-bench`（HuggingFace，2026）：每场 100 轮、每场景 3 次采样、
按 20 轮切块让 LLM 评判，并与人类偏好对齐。

| 排名 | 模型 | 总分 | 世界一致性 | 故事推进 | 交互偏好 |
|---|---|---|---|---|---|
| 1 | **MiniMax-M2-her** | **84.65** | 80.55 | 79.97 | 97.51 |
| 2 | doubao-1.5-pro | 80.64 | 72.83 | 81.73 | 95.18 |
| 3 | gpt-5.1 | 80.63 | 76.62 | 72.21 | 97.05 |
| 4 | claude-opus-4.5（高思考） | 76.62 | 67.23 | 82.10 | 89.90 |
| 5 | gemini-3-pro | 75.60 | 62.72 | 83.87 | 93.08 |
| 10 | **deepseek-v3.2** | **60.27** | 45.81 | 66.64 | 82.83 |

三条读法：

1. **「专用」确实赢**：`MiniMax-M2-her` 比 gpt-5.1 高 4 分，主要赢在「世界一致性」
   （80.55 vs 76.62）—— 恰好是本项目最痛的那一项（空间、称谓、谁知道什么）。
2. **deepseek 系在角色扮演上是榜尾**（60.27，世界一致性只有 45.81）。
   这跟它在本项目里的表现对得上：动作重演、称谓混用、场外人物出场。
3. **这份榜单是 MiniMax 自己发的**，自家模型排第一要打折看；但它的评测协议是公开的，
   而且第二三名（doubao / gpt-5.1）与第三方的观察大致吻合（OpenRouter 的角色扮演流量里
   DeepSeek 系靠便宜取胜，不靠质量）。

⚠ 另有一类「角色扮演榜」把 Qwen3.5-27B 排第一（benchlm.ai），它的口径是
「人格一致性 ≈ 穿衣服的指令遵循」。**别用它选演员**：它量的是「听不听话」，
不量「写出来的像不像小说」。

---

## 4. 但「专用」有三个错位，接之前必须想清楚

本项目和这些模型的训练目标是**不一样**的：

| 它们的假设 | 本项目实际要的 |
|---|---|
| 有一个**用户在跟一个角色聊天**，输出自然语言 | **N 个 NPC 同时在场上互相演**，输出**结构化 JSON 决策**（`agent_decide`） |
| 优化「连贯、有情绪、记关系」 | 优化「**信息边界**」（谁知道什么）、**空间动线**、**时代称谓** |
| 上下文里是角色卡 + 聊天记录 | 上下文是**设定集 + 前情 + 在场名单 + 上一拍动作**（几万字） |
| 中文现代口语 | 明清白话 / 民国北平话 / 川端式留白 |

所以我的判断是：

- **`Doubao Seed Character` 值得先试**：便宜（¥0.8/¥2，和 flash 同档）、中文、OpenAI 兼容、
  上下文够。风险是它可能不会老实输出 JSON —— 需要在提示词里压，或者用它的
  function calling。
- **`MiniMax-M2-her` 只能当对照**（2026-10-18 核实）：它**不在 MiniMax 开放平台**，
  只能走 OpenRouter（`minimax/minimax-m2-her`），且最大输出仅 **2048**、不保证 JSON、
  可用率约 **79%** ⇒ 只能做 actor、当不了主力。详见 `docs/minimax-apply.md`。
- **`CharGLM-4` 直接排除**：8K 上下文装不下本项目任何一次决策。
- **开源微调全部排除**：中文文言/白话不是它们的训练分布。

---

## 5. 怎么验证（不要凭榜单拍板）

申请入口与接入步骤单独写在 **`docs/minimax-apply.md`**（含三条硬限制：66K 上下文 /
2048 最大输出 / 不支持 `response_format`）。`llm_models.json` 里已预置 `minimax-m2-her`
条目，Key 填进去即可。

改一行就能换演员模型，不用改代码：

```
agents/actor.md  ->  model: hy3  改成  model: doubao-character
```

前提是先在「天机 · LLM 接入」里登记这个模型（base_url / key / 价格），
`llm_models.json` 的 `key` 与 `agents/*.md` 的 `model:` 对齐。

然后用现成的两把尺子量：

```bash
# 同一批用例、同样的拍数，只换演员模型
NB_KEEP_PROJECTS=true python novel_bench/bench/cli.py run --case ykg-01 --ticks 6 --run-id model-doubao
python novel_bench/bench/cli.py judge --run novel_bench/results/model-doubao
python novel_bench/bench/cli.py compare --a novel_bench/results/ops1 --b novel_bench/results/model-doubao
```

看三个数，别只看总分：

1. **`character` 维度**（人物成形，权重 0.20）—— 这是换演员模型的**唯一直接目标**；
2. `offstage_leak`（场外人物）与 `present_by_alias` —— 信息边界有没有变好；
3. `meta.json.seconds` 与 `logs/llm_calls.jsonl` 的 `out` 总和 —— 贵多少、慢多少。

⚠ 至少跑 **3 例**。单例的角色扮演分波动可达 ±5，n=1 定不了。

---

## 6. 一句话结论

**有**，而且比现在用的 `hy3` 更对路：`Doubao Seed Character` 是国内能直接接的
「角色扮演专用」API，`MiniMax-M2-her` 是公开榜单第一。

但**别期待换个模型就解决所有问题**：人物走形有一半是提示词与材料组织的问题
（上一轮已确认：场内名单没递给作家、称谓当专名用），换模型之前那些得先修，
否则换了也量不出差别。

另外有一件**比换模型更便宜的事**先做：`detect_thinking_switch()` 认不出 `hy3`，
导致每拍白花几千 token 在思考上。修它 + 跑一次真正的 A/B，能先回答
「思考值不值这些钱」——如果值，再谈换模型；如果不值，省下的钱够换更好的模型。
