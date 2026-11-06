# MiniMax-M2-her 到底在哪（2026-10-18 核实）

> **更正**：我之前说"在 platform.minimaxi.com 申请就能用"是**错的**。
> 查了官方文档与 release notes 后确认：**M2-her 不在 MiniMax 开放平台上，一行都调不到。**

---

## 1. 核实结果：官方平台没有这个模型

`platform.minimaxi.com`（国内站）与 `platform.minimax.io`（国际站）的
**Chat Completions API 文档里，`model` 的可用值枚举完全一致**，都没有 M2-her：

```
MiniMax-M3.1-Flash-Preview, MiniMax-M3,
MiniMax-M2.7, MiniMax-M2.7-highspeed,
MiniMax-M2.5, MiniMax-M2.5-highspeed,
MiniMax-M2.1, MiniMax-M2.1-highspeed,
MiniMax-M2
```

再看两处旁证：

- **官方 release notes**（`platform.minimax.cn/docs/release-notes/models`）从
  2025-01 的 `MiniMax-Text-01` 一路列到 2026-06 的 `MiniMax-M3`，
  **中间没有任何一条 M2-her**。
- **官网首页导航**只列 `M3 / M2.7 / M2.5 / H3 / Speech 2.8 / Music 3.0`，也没有 M2-her。

⇒ 你找不到不是你看漏了，**它确实不在那里**。

### 它到哪去了

M2-her 是**星野（Xingye）/ Talkie 的基座模型**（官方公告原话：`M2-her 作为支持我们 AI
互动产品（即星野）的基座模型`）。这类"产品基座"通常只对内部或单一渠道开放——
目前公开可调的唯一通道是 **OpenRouter**。

有些第三方站（如 aibot-box）写着"API 地址 platform.minimaxi.com/docs/api-reference/text-chat"，
那是**照抄了 MiniMax 的通用文档链接**，不代表这个模型在那上面。

---

## 2. 唯一可用通道：OpenRouter

| 项 | 值 |
|---|---|
| model id | `minimax/minimax-m2-her` |
| base_url | `https://openrouter.ai/api/v1` |
| Key 形态 | `sk-or-v1-...`（OpenRouter 自己的账号，不是 MiniMax 的） |
| 输入价 | $0.30 / 百万 token（约 ¥2.1） |
| 输出价 | $1.20 / 百万 token（约 ¥8.4） |
| 上下文 | **66K** |
| **最大输出** | **2048 token**（⚠ OpenRouter 侧的限制，MiniMax 文档给其它 M2.x 是 6.4K/20 万） |
| tools / function calling | **不支持** |
| `response_format`（强制 JSON） | **不支持** |
| 3 天可用率 | **79.49%**（uptime 100%，但 availability 只有 79.49% —— 意思是"能连上，但约五次有一次不出结果"） |
| 主力用户 | Janitor AI、SillyTavern（就是那批 1v1 陪聊产品） |

注册：<https://openrouter.ai/> → 右上 Sign in → 充值（信用卡 / 加密货币，**不支持支付宝**）→
<https://openrouter.ai/keys> 创建 Key。

⚠ 本机有 HTTP 代理（`127.0.0.1:61594`），OpenRouter 可能需要代理才通；MiniMax 国内站不需要。

---

## 3. 四条硬限制，逐条对上本项目

| 限制 | 对本项目的实际影响 |
|---|---|
| **最大输出 2048** | `crew_day_novel`（整章整理，动辄 2000+ 字）和 `day_script`（分拍台本）**直接装不下** ⇒ **只能做 `actor`**。<br>而 `agent_decide` 正常输出 200–400 token，正好够；但它现在跑在 hy3 上输出中位 **2967**（多数是思考），若 M2-her 也思考，2048 会**撞上限、正文被截** |
| **上下文 66K** | `agent_decide` 输入 6.5K 起，群像戏更大。够用但不宽裕 |
| **不支持 `response_format`** | `agent_decide` 靠解析 JSON 拿决策。没有强制 JSON ⇒ 只能靠提示词压，**解析失败率上升** |
| **可用率 ~79%** | 一个故事日 1080 拍，按 79% 算平均**每五拍失败一次**。本项目已有重试（`RETRIES`），但重试也要 30–60 秒/次 |

### 还有一条藏在官方文档里的坏消息

MiniMax 文档写明：

> **M2.x 模型：thinking 无法关闭，传入 `disabled` 会被接收但不生效。**

M2-her 是 M2 系衍生 ⇒ **就算能调，也很可能关不掉思考**。
这正是 `hy3` 现在的问题（输出中位 2967 token 里大部分是思考）。

⚠ 这条要看实测（OpenRouter 可能做了自己的处理），但**先按"关不掉"预期**。

---

## 4. 那还要不要试

**试，但只做一件事：拿它当 `actor` 的对照，跑 3 例就停。**

理由：它是目前唯一公开可调的"角色扮演专用"模型，`character` 维度有没有真提升，
只有跑过才知道。但四条限制叠起来（不能做作家/编剧、JSON 不保证、可用率 79%），
**不适合长期当主力**。

预期落点：`character` 可能涨，`canon` 可能跌（JSON 解析失败 ⇒ 决策丢失 ⇒ 那一拍空转）。
报告里 `hy3` 那批的 `idle_beats` 和 `offstage_leak` 就是对照组。

---

## 5. 更实际的两条路（我的建议）

### ① `Doubao Seed Character`（火山方舟）—— 最省事

你的 `llm_models.json` 里**已经有一个火山方舟条目**（`doubao-lite-2-1`），
`base_url` 与账号都通了，换个 model 名即可：

| 项 | 值 |
|---|---|
| 上下文 | **131K–256K**（比 66K 宽得多） |
| 价格 | **¥0.8 / ¥2.0**（比 M2-her 便宜一半以上） |
| function calling | **支持** |
| 官方定位 | "角色对话、人设稳定" |

`model` 参数大概是 `doubao-seed-character-...` 这种带日期的形式，
在火山方舟控制台「开通管理」里能看到确切 id。

### ② 先把 `hy3` 的思考关掉 —— 零成本，且我已经验证可行

前面实测：`hy3` 对 `thinking:{"type":"disabled"}` 有效（out 从 25 → 2，思考从 22 → 0）。
现在的问题**不是模型不支持，是 `detect_thinking_switch()` 那张按模型名写死的白名单不认它**。

`agent_decide` 输出中位 **2967** token、最大 **23307**，绝大部分是思考。
按 hy3 的价算，这是本项目最大的一笔可省开销。修这个检测函数 + 跑一次真正的 A/B，
**比换模型便宜得多，而且能直接回答"思考值不值这些钱"**。

---

## 6. 一句话

**M2-her 不在 MiniMax 开放平台**（官方模型枚举与 release notes 都没有），
只能走 OpenRouter，而且最大输出只有 2048、不保证 JSON、可用率约 79% ——
能试，但当不了主力。

想真正提升演员质量，性价比排序是：
**① 修 `detect_thinking_switch` 让 hy3 能关思考（零成本，已验证可行）→
② 试 `Doubao Seed Character`（已有账号，¥0.8/¥2，上下文 131K）→
③ 才轮到 M2-her（仅作对照，3 例就停）。**
