# Doubao Seed Character 怎么开通（2026-10-18 实测）

> **好消息：你不需要注册新账号。** 火山方舟的 Key 已经在用了，Base URL 也通。
> 缺的只有一步：**在控制台把这个模型"开通"一下。**

---

## 1. 我直接拿你的 Key 试了三个 model id

用 `llm_models.json` 里已有的火山方舟 Key（账号 `2106728126`）实测：

| 试的 model id | 结果 | 说明 |
|---|---|---|
| `doubao-seed-2-1-lite-260915`（已登记的那个） | ✅ 调通，out=41 | **Key 本身是好的** |
| **`doubao-seed-character-260628`** | ❌ `ModelNotOpen` | **模型存在**，只是没开通 |
| **`doubao-seed-character-251128`** | ❌ `ModelNotOpen` | 同上（旧版本） |
| `doubao-seed-character-251015` | ❌ `InvalidEndpointOrModel.NotFound` | 这个 id 不存在 |
| `doubao-seed-character` | ❌ `InvalidEndpointOrModel.NotFound` | 不带日期不行 |

**`ModelNotOpen` 和 `NotFound` 是两种完全不同的错**：
- `NotFound` = 这个模型名根本不对，别再猜了
- `ModelNotOpen` = **名字对、模型在，你的账号没开通** ← 你现在就是这一种

⇒ 结论：**只差一步开通，不用注册、不用申请审批、不用等。**

---

## 2. 开通步骤（约 2 分钟）

### 2.1 打开「开通管理」

<https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement>

（这是火山方舟控制台 · 华北北京 · 开通管理。如果你所在的 region 不同，把 URL 里的
`cn-beijing` 换成你的 region。）

### 2.2 找到「豆包 · 角色类」或搜 `Seed Character`

列表里按模型类型分组，找 **Doubao 系列** 下的 `doubao-seed-character-260628`。
（260628 = 2026-06-28 版，属于 Seed 2.1 系列；`251128` 是 2025-11-28 的旧版，**选新的**。）

### 2.3 点「开通」

- 一般是**即时生效**，不需要审核
- 开通后**按量计费**，不订阅不扣费，调多少算多少
- 如果提示需要实名认证 / 余额，按提示补（你的账号已经在用别的豆包模型，应该都有）

### 2.4 再试一次

开通完回来跑这个（**30 秒**，不用改任何配置）：

```bash
cd "C:/Users/chao/OneDrive/桌面/小说世界AI模拟/NovelWorldSimulator"
./.venv/Scripts/python.exe - <<'EOF'
import json, urllib.request
from pathlib import Path
m = [x for x in json.loads(Path('llm_models.json').read_text(encoding='utf-8'))['models']
     if x['key'] == 'doubao-lite-2-1'][0]
body = json.dumps({
    "model": "doubao-seed-character-260628",
    "messages": [{"role": "user", "content": "只回复两个字：可用"}],
    "max_tokens": 64,
}).encode()
req = urllib.request.Request(m['base_url'].rstrip('/') + '/chat/completions', data=body,
    headers={'Content-Type': 'application/json',
             'Authorization': 'Bearer ' + m['api_key']}, method='POST')
r = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
print('model:', r.get('model'))
print('usage:', r.get('usage'))
print('content:', r['choices'][0]['message'].get('content'))
EOF
```

看到 `model: doubao-seed-character-260628` 就通了。

---

## 3. 两个 Key 你要分清楚

火山方舟有**两种鉴权方式**，`llm_models.json` 里现在用的是第一种：

| 方式 | 形态 | 说明 |
|---|---|---|
| **API Key**（你现在用的） | `ark-xxxx...`（46 字符） | 全账号通用，开通了哪些模型就能调哪些 |
| **Endpoint ID（推理接入点）** | `ep-2024xxxx-xxxxx` | 给某个模型单独建一个接入点，`model` 填 `ep-...` |

⚠ **用 API Key 时，开通了模型就能直接填模型名**（`doubao-seed-character-260628`），
不用建接入点。如果控制台只给你 Endpoint ID，那就在 `model` 里填 `ep-...` 那串。

---

## 4. 这个模型的实际规格

| 项 | 值 |
|---|---|
| model id | `doubao-seed-character-260628` |
| 上下文 | **256K** |
| 最大输出 | **256K** |
| 输入价 | 约 **¥0.8 / 百万**（$0.119） |
| 输出价 | 约 **¥2.0 / 百万**（$0.297） |
| function calling | **✅ 支持** |
| 结构化输出（JSON） | **✅ 支持** ← 这是 M2-her 没有的，对 `agent_decide` 关键 |
| 多模态 | 支持图片/视频输入 |
| 定位 | 泛娱乐角色对话，"人设稳定性强"，官方说增强了**格式遵循**与工具调用 |

对比一下就知道为什么它比 M2-her 靠谱：

| | Seed Character | MiniMax-M2-her |
|---|---|---|
| 上下文 | **256K** | 66K |
| 最大输出 | **256K** | **2048** ⚠ |
| 强制 JSON | **✅** | ❌ |
| 可用率 | 官方 SLA 99.95% | 实测 79% |
| 价格（输出/百万） | **¥2.0** | ¥8.4 |
| 现在能不能用 | 开通即可（2 分钟） | 要走 OpenRouter 注册 |

---

## 5. 一个必须提前知道的事：豆包也默认思考

我顺手测了你现在用的 `doubao-seed-2-1-lite-260915`：

```
out=41  reason=40   ← 41 个输出 token 里 40 个是思考
```

**豆包系列和 `hy3` 一样默认思考。** 所以换成 Seed Character 之后：

1. 它的 `max_tokens` 要留足（不能像 flash 那样给 400）
2. 要测 `thinking:{"type":"disabled"}` 对它有没有效
3. 如果关不掉，每拍的成本会按"思考 + 正文"算

⚠ 这跟 `hy3` 那条是同一个病根：`detect_thinking_switch()` 那张表只认 deepseek 系名字，
新模型接进来一律判"不支持关思考"。**开通之后先测这一条，再决定主力用谁。**

---

## 5.5 已经切好了（2026-10-18），但中间踩了一个坑

### 改了什么

| 文件 | 改动 |
|---|---|
| `agents/actor.md` | `model: hy3` → `model: doubao-character` |
| `llm_models.json` | 新增 `doubao-character` 条目（`doubao-seed-character-251128`，复用火山 Key），`api_key` 沿用 |
| `llm_models.json` 的 `caps` | `LLM_CAP_JSON_MODE: false`（见下面第 ② 条） |
| `llm/capabilities.py` | `MAX_OUTPUT_TOKENS` 加豆包两行（见下面第 ① 条） |
| `tools/verify_llm_caps.py` | 新增 D 组 5 条判据 |
| `developers/mutate_output_caps.py` | 反例法 6/6 |

### ① 坑一：`max_tokens` 被发了 819200，整发 400

第一次切过去跑 1 拍，**整拍空掉**：

```
「祥子」决策失败，本轮降级为 wait：Client error '400 Bad Request'
第 1 天落盘（剧本）：{'幕数': 1, '对白': 0, '动作': 0, '旁白': 0}
```

真因不是模型、不是提示词：`MAX_OUTPUT_TOKENS` 表里**没有豆包条目** ⇒
`max_output_tokens()` 返回 `None` ⇒ 调用方退回 `LLM_MAX_TOKENS_FALLBACK` = **819200**
（那是为 `hy3` 设的，`hy3` 实测确实收）。豆包的天花板是 **32768**。

⚠ 这个 bug 的形状很坏：**短请求一测就通**（我前面那些测试全绿），
只有真跑起来才炸，而炸的方式是"人物不出声"，不像报错。

实测天花板（逐档试到被拒）：

| 模型 | 可接受的最大 `max_tokens` |
|---|---|
| `doubao-seed-character-251128` | **32768**（65536 起 400） |
| `doubao-seed-2-1-lite-260915` | 131072（262144 起 400） |

### ② 坑二：`response_format` 它不支持

能力表按"豆包"这一族判，`CAP_JSON_MODE=True`，而 `agent_decide` 带 `json_mode=True`
⇒ 会发 `response_format: {"type": "json_object"}` ⇒ 这个模型 **400**：

```
InvalidParameter: The parameter `response_format.type` ... `json_object` is not supported
```

⇒ 在该条目的 `caps` 里显式关掉。实测它**不加这个参数也能输出干净 JSON**
（`{"内心":"…","动作":[…],"台词":"…"}`，无围栏）。

### ③ 好消息：它默认**不思考**

| | `hy3` | `doubao-seed-character-251128` |
|---|---|---|
| 默认思考 | ✅（`reason=22/25`） | ❌ **`reason=0`** |
| `agent_decide` 输出 | 中位 **2967** token | **42** token |
| 单发延迟 | 20–48s | **1.5s** |

按输出价算，这一项省得比换模型本身还多。

### ④ 代价：写得更"薄"

同样的提示，`hy3` 写"祥子把水桶往井台边一放，低头紧了紧腰带"，
豆包写"在一旁默默听着"。**信息密度明显低一档**。

这是 1v1 陪聊模型做结构化表演的通病。要不要留它，得用 `novel_bench` 的
`character` 维度量，不能凭感觉。见下面第 6 节。

---

## 6. 开通之后怎么切演员

**先别急着改**。按这个顺序：

```bash
# ① 先测它能不能关思考（改 max_tokens 看思考占比）
# ② 再跑 3 例对照，别一上来就 6 例
NB_KEEP_PROJECTS=true ./.venv/Scripts/python.exe novel_bench/bench/cli.py run \
    --case hlm-01 --case lz-01 --case ykg-01 --ticks 6 --run-id model-char
```

`agents/actor.md` 改 `model:` 的时机，是等 ①② 都验过之后。

---

## 7. 一句话

**不用申请，只要开通。** 打开
<https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement>，
搜 `doubao-seed-character-260628`，点开通，2 分钟完事。

你的 Key 已经是好的（`doubao-seed-2-1-lite-260915` 实测调通），
模型 id 也已经确认（`260628` 存在、`251015` 不存在），剩下就这一个按钮。
