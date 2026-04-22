# VibRec 前端平台 API 接入说明

这份文档面向前端平台、BFF、Node 服务、网关服务，以及会替你写接入代码的
Codex agent。目标很简单：把 VibRec 当前交付的 actor 识别能力当作一个
HTTP API 来调用。

## 1. 先记住这几个事实

- 当前正式模型：`actor_domain_generalization`
- 当前任务：二分类，输出 `human` 或 `machine`
- 推荐接口：`POST /api/v1/predict/actor/raw`
- 服务默认端口：`8000`
- 当前 API 无鉴权；如果要对外网开放，建议放在你自己的网关后面

推荐优先走服务端调用，也就是：

- 前端页面 -> 你自己的后端/BFF -> VibRec API

这样做有三个现实原因：

- 原始 DAS `block` 往往很大，浏览器直接发 JSON 负担较重
- 跨域浏览器调用需要 CORS 配置
- 认证、限流、日志、重试更适合放在你自己的服务层

如果你的前端平台必须从浏览器直接跨域调用，则部署 VibRec 时必须设置：

```bash
export VIBREC_CORS_ALLOW_ORIGINS="http://localhost:3000,https://your-frontend.example.com"
```

多个域名用英文逗号分隔。开发阶段可暂时设为 `"*"`，生产不建议这样做。

## 2. 你应该调用哪个接口

### 推荐：原始输入接口# VibRec 前端平台 API 接入说明

这份文档面向前端平台、BFF、Node 服务、网关服务，以及会替你写接入代码的
Codex agent。目标很简单：把 VibRec 当前交付的 actor 识别能力当作一个
HTTP API 来调用。

## 1. 先记住这几个事实

- 当前正式模型：`actor_domain_generalization`
- 当前任务：二分类，输出 `human` 或 `machine`
- 推荐接口：`POST /api/v1/predict/actor/raw`
- 服务默认端口：`8000`
- 当前 API 无鉴权；如果要对外网开放，建议放在你自己的网关后面

推荐优先走服务端调用，也就是：

- 前端页面 -> 你自己的后端/BFF -> VibRec API

这样做有三个现实原因：

- 原始 DAS `block` 往往很大，浏览器直接发 JSON 负担较重
- 跨域浏览器调用需要 CORS 配置
- 认证、限流、日志、重试更适合放在你自己的服务层

如果你的前端平台必须从浏览器直接跨域调用，则部署 VibRec 时必须设置：

```bash
export VIBREC_CORS_ALLOW_ORIGINS="http://localhost:3000,https://your-frontend.example.com"
```

多个域名用英文逗号分隔。开发阶段可暂时设为 `"*"`，生产不建议这样做。

## 2. 你应该调用哪个接口

### 推荐：原始输入接口

```text
POST /api/v1/predict/actor/raw
```

适用场景：

- 你手里有原始 DAS 二维矩阵
- 你有每个块的采样率和物理距离范围
- 你不想在前端或业务平台里复现模型预处理

这也是大多数平台接入应该使用的接口。

### 仅高级场景：canonical 输入接口

```text
POST /api/v1/predict/actor
```

只有当你已经在外部系统中完整复现了同一套 canonical 预处理流程时才使用。
否则不要选它，因为输入 shape 和归一化要求更严格。

## 3. 可用的基础接口

### 健康检查

```text
GET /api/v1/health
```

示例返回：

```json
{
  "status": "ok",
  "service": "vibrec-dashboard",
  "version": "0.1.0"
}
```

### 查询模型输入要求

```text
GET /api/v1/predict/actor/schema
```

这个接口可用于平台初始化时拉取当前模型的 shape、标签列表和最大上下文长度。

### 已验证的本地 smoke test 返回

以下返回来自本仓库在本机 Docker 中的实际 smoke test：

健康检查：

```json
{
  "status": "ok",
  "service": "vibrec-dashboard",
  "version": "0.1.0"
}
```

Schema：

```json
{
  "model_name": "actor_domain_generalization",
  "checkpoint_path": "/app/artifacts/multilevel_nn/actor_domain_generalization/best_actor_domain_generalization_model.pt",
  "expected_chunk_shapes": {
    "raw_view": [2, 256, 96],
    "spectral_view": [1, 48, 96],
    "feature_vector": [37]
  },
  "max_context_chunks": 8,
  "input_order": "chunks must be chronological: oldest first, current chunk last",
  "labels": ["machine", "human"],
  "feature_vectors_are_normalized_default": false
}
```

最小 raw 预测示例返回：

```json
{
  "model_name": "actor_domain_generalization",
  "label": "machine",
  "confidence": 0.8088366389274597,
  "probabilities": {
    "machine": 0.8088366389274597,
    "human": 0.19116340577602386
  },
  "context_len": 8,
  "valid_chunks": 1,
  "input_shapes": {
    "raw_seq": [8, 2, 256, 96],
    "spectral_seq": [8, 1, 48, 96],
    "feature_seq": [8, 37],
    "delta_seq": [8],
    "valid_mask": [8]
  },
  "device": "cpu"
}
```

## 4. 推荐接口的请求格式

接口：

```text
POST /api/v1/predict/actor/raw
Content-Type: application/json
```

请求体结构：

```json
{
  "chunks": [
    {
      "block": [[0.1, 0.2], [0.3, 0.4]],
      "scan_rate_hz": 2000,
      "range_start_m": 600.0,
      "range_end_m": 800.0,
      "delta_seconds": 0.0
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `chunks` | `array` | 是 | 时间上下文块数组，按时间从旧到新排列，最后一个是当前 chunk |
| `block` | `number[][]` | 是 | 原始 DAS 二维矩阵，shape 为 `[时间点, 距离列]` |
| `scan_rate_hz` | `number` | 是 | 采样率，必须大于 `0` |
| `range_start_m` | `number` | 是 | 第一列对应物理距离 |
| `range_end_m` | `number` | 是 | 最后一列对应物理距离 |
| `delta_seconds` | `number \| null` | 否 | 相对当前块的时间差，当前块通常传 `0.0`，历史块传负值 |

### 关键约束

- `chunks` 至少 `1` 个，最多 `8` 个
- 顺序必须是“最旧 -> 最新”
- `block` 必须是二维数值数组
- `block` 至少要有 `2` 行、`2` 列
- `range_end_m` 必须大于 `range_start_m`
- 物理距离范围必须完整覆盖 `600m-800m`
- `block` 的 shape 不要求固定为 `256 x 96`，服务端会自动重采样
- 如果只传 `1` 个 chunk，服务会自动补齐缺失历史

### 服务端会自动做什么

- 按 `600m-800m` 裁切/映射物理距离
- 空间重采样到 `96` 列
- 时间重采样到 `256` 步
- 生成 `raw_view`
- 生成 `spectral_view`
- 生成 `37` 维特征
- 组装最多 `8` 个上下文块
- 输出 `human` / `machine`

## 5. 推荐接口的返回格式

示例返回：

```json
{
  "model_name": "actor_domain_generalization",
  "label": "machine",
  "confidence": 0.808819591999054,
  "probabilities": {
    "machine": 0.808819591999054,
    "human": 0.19118033349514008
  },
  "context_len": 8,
  "valid_chunks": 1,
  "input_shapes": {
    "raw_seq": [8, 2, 256, 96],
    "spectral_seq": [8, 1, 48, 96],
    "feature_seq": [8, 37],
    "delta_seq": [8],
    "valid_mask": [8]
  },
  "device": "cpu"
}
```

返回字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `model_name` | `string` | 当前使用的模型名 |
| `label` | `string` | 最终分类结果，`human` 或 `machine` |
| `confidence` | `number` | 最终分类标签的置信度 |
| `probabilities` | `object` | 每个标签的概率 |
| `context_len` | `number` | 模型上下文长度，目前为 `8` |
| `valid_chunks` | `number` | 本次请求实际传入的 chunk 数 |
| `input_shapes` | `object` | 服务端整理后的模型输入 shape |
| `device` | `string` | 实际推理设备，如 `cpu` 或 `cuda` |

## 6. 错误返回和前端该怎么处理

常见状态码：

| 状态码 | 含义 | 常见原因 |
|---|---|---|
| `200` | 成功 | 推理正常 |
| `422` | 请求参数错误 | `block` 不是二维数组、shape 非法、距离范围不覆盖 `600m-800m`、chunk 数超过 `8` |
| `503` | 服务暂时不可用 | checkpoint 缺失、模型未加载成功、设备不可用，例如强制 `cuda` 但机器没有 CUDA |

前端或平台侧建议：

- `422` 直接展示“输入格式/数据范围错误”
- `503` 展示“模型服务暂时不可用”，并允许重试
- 对请求设置超时
- 保留原始请求摘要和响应，便于排查

## 7. TypeScript 接口定义

```ts
export type VibRecRawChunk = {
  block: number[][];
  scan_rate_hz: number;
  range_start_m: number;
  range_end_m: number;
  delta_seconds?: number | null;
};

export type VibRecRawPredictionRequest = {
  chunks: VibRecRawChunk[];
};

export type VibRecPredictionResponse = {
  model_name: string;
  label: "human" | "machine";
  confidence: number;
  probabilities: Record<string, number>;
  context_len: number;
  valid_chunks: number;
  input_shapes: Record<string, number[]>;
  device: string;
};
```

## 8. 浏览器/前端 `fetch` 示例

```ts
export async function predictActorRaw(
  baseUrl: string,
  payload: {
    chunks: Array<{
      block: number[][];
      scan_rate_hz: number;
      range_start_m: number;
      range_end_m: number;
      delta_seconds?: number | null;
    }>;
  }
) {
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/api/v1/predict/actor/raw`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      `VibRec request failed: ${response.status} ${JSON.stringify(data)}`
    );
  }
  return data as {
    model_name: string;
    label: "human" | "machine";
    confidence: number;
    probabilities: Record<string, number>;
    context_len: number;
    valid_chunks: number;
    input_shapes: Record<string, number[]>;
    device: string;
  };
}
```

最小调用示例：

```ts
const payload = {
  chunks: [
    {
      block: [
        [0.1, 0.2],
        [0.3, 0.4]
      ],
      scan_rate_hz: 2000,
      range_start_m: 600,
      range_end_m: 800,
      delta_seconds: 0
    }
  ]
};

const result = await predictActorRaw("http://localhost:8000", payload);
console.log(result.label, result.confidence);
```

## 9. Node/BFF 代理调用示例

如果你的前端平台本身有服务端，推荐把 VibRec 包在你自己的 API 后面。

```ts
import express from "express";

const app = express();
app.use(express.json({ limit: "20mb" }));

app.post("/api/vibrec/predict", async (req, res) => {
  const response = await fetch("http://vibrec-host:8000/api/v1/predict/actor/raw", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req.body),
  });

  const data = await response.json().catch(() => null);
  res.status(response.status).json(data);
});
```

这种方式通常比浏览器直连更稳。

## 10. 如果你非要用 canonical 接口

接口：

```text
POST /api/v1/predict/actor
```

请求体结构：

```json
{
  "chunks": [
    {
      "raw_view": [[[0.0]]],
      "spectral_view": [[[0.0]]],
      "feature_vector": [0.0],
      "delta_seconds": 0.0
    }
  ],
  "feature_vectors_are_normalized": false
}
```

当前模型要求：

- `raw_view`: `[2, 256, 96]`
- `spectral_view`: `[1, 48, 96]`
- `feature_vector`: `[37]`
- 最多 `8` 个 chunk

这个接口更容易因为 shape 或归一化不一致而失败，平台集成默认不要选它。

## 11. 给前端平台 Codex agent 的直接指令

你可以把下面这段直接交给前端平台里的 Codex agent：

```text
请将 VibRec 模型服务接入当前平台。默认使用 POST /api/v1/predict/actor/raw。
实现一个可复用的 API client，支持：
1. 调用 GET /api/v1/health 做服务可用性检查
2. 调用 GET /api/v1/predict/actor/schema 拉取模型输入约束
3. 调用 POST /api/v1/predict/actor/raw 发送 JSON 请求
4. 对 422 和 503 做明确错误处理
5. 保留 TypeScript 类型定义
6. 如果当前平台是浏览器直连，请确认后端已配置 VIBREC_CORS_ALLOW_ORIGINS；如果没有，则改为通过平台自己的服务端代理调用

请求体类型：
{
  chunks: Array<{
    block: number[][];
    scan_rate_hz: number;
    range_start_m: number;
    range_end_m: number;
    delta_seconds?: number | null;
  }>;
}

约束：
- chunks 按时间从旧到新排列
- chunks 最多 8 个
- range_start_m 到 range_end_m 必须覆盖 600m-800m
- block 必须是二维数值数组
```

## 12. 实际接入建议

- 如果只是验证连通性，先传 `1` 个 chunk
- 如果是实时流式场景，再扩展到 `2-8` 个 chunk 上下文
- 如果前端上传的原始矩阵很大，优先走后端/BFF
- 如果需要公网接入，自己在外层补鉴权、限流和审计

## 13. 前端落地流程

建议平台侧按下面顺序落地：

1. 启动时调用 `GET /api/v1/health`，只做可用性探测。
2. 初始化时调用 `GET /api/v1/predict/actor/schema`，缓存 `max_context_chunks` 和 shape 约束。
3. 业务侧准备 `1-8` 个 `chunks`，顺序必须是从旧到新。
4. 默认调用 `POST /api/v1/predict/actor/raw`，不要优先接 canonical 接口。
5. 页面展示时主要使用 `label`、`confidence`、`probabilities.machine`、`probabilities.human`。
6. 对 `422` 做数据校验提示，对 `503` 做服务不可用提示和重试。

如果你的平台有自己的后端层，建议把 VibRec API 封装成你平台内部的一个模型能力接口，再暴露给前端页面使用。


```text
POST /api/v1/predict/actor/raw
```

适用场景：

- 你手里有原始 DAS 二维矩阵
- 你有每个块的采样率和物理距离范围
- 你不想在前端或业务平台里复现模型预处理

这也是大多数平台接入应该使用的接口。

### 仅高级场景：canonical 输入接口

```text
POST /api/v1/predict/actor
```

只有当你已经在外部系统中完整复现了同一套 canonical 预处理流程时才使用。
否则不要选它，因为输入 shape 和归一化要求更严格。

## 3. 可用的基础接口

### 健康检查

```text
GET /api/v1/health
```

示例返回：

```json
{
  "status": "ok",
  "service": "vibrec-dashboard",
  "version": "0.1.0"
}
```

### 查询模型输入要求

```text
GET /api/v1/predict/actor/schema
```

这个接口可用于平台初始化时拉取当前模型的 shape、标签列表和最大上下文长度。

### 已验证的本地 smoke test 返回

以下返回来自本仓库在本机 Docker 中的实际 smoke test：

健康检查：

```json
{
  "status": "ok",
  "service": "vibrec-dashboard",
  "version": "0.1.0"
}
```

Schema：

```json
{
  "model_name": "actor_domain_generalization",
  "checkpoint_path": "/app/artifacts/multilevel_nn/actor_domain_generalization/best_actor_domain_generalization_model.pt",
  "expected_chunk_shapes": {
    "raw_view": [2, 256, 96],
    "spectral_view": [1, 48, 96],
    "feature_vector": [37]
  },
  "max_context_chunks": 8,
  "input_order": "chunks must be chronological: oldest first, current chunk last",
  "labels": ["machine", "human"],
  "feature_vectors_are_normalized_default": false
}
```

最小 raw 预测示例返回：

```json
{
  "model_name": "actor_domain_generalization",
  "label": "machine",
  "confidence": 0.8088366389274597,
  "probabilities": {
    "machine": 0.8088366389274597,
    "human": 0.19116340577602386
  },
  "context_len": 8,
  "valid_chunks": 1,
  "input_shapes": {
    "raw_seq": [8, 2, 256, 96],
    "spectral_seq": [8, 1, 48, 96],
    "feature_seq": [8, 37],
    "delta_seq": [8],
    "valid_mask": [8]
  },
  "device": "cpu"
}
```

## 4. 推荐接口的请求格式

接口：

```text
POST /api/v1/predict/actor/raw
Content-Type: application/json
```

请求体结构：

```json
{
  "chunks": [
    {
      "block": [[0.1, 0.2], [0.3, 0.4]],
      "scan_rate_hz": 2000,
      "range_start_m": 600.0,
      "range_end_m": 800.0,
      "delta_seconds": 0.0
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `chunks` | `array` | 是 | 时间上下文块数组，按时间从旧到新排列，最后一个是当前 chunk |
| `block` | `number[][]` | 是 | 原始 DAS 二维矩阵，shape 为 `[时间点, 距离列]` |
| `scan_rate_hz` | `number` | 是 | 采样率，必须大于 `0` |
| `range_start_m` | `number` | 是 | 第一列对应物理距离 |
| `range_end_m` | `number` | 是 | 最后一列对应物理距离 |
| `delta_seconds` | `number \| null` | 否 | 相对当前块的时间差，当前块通常传 `0.0`，历史块传负值 |

### 关键约束

- `chunks` 至少 `1` 个，最多 `8` 个
- 顺序必须是“最旧 -> 最新”
- `block` 必须是二维数值数组
- `block` 至少要有 `2` 行、`2` 列
- `range_end_m` 必须大于 `range_start_m`
- 物理距离范围必须完整覆盖 `600m-800m`
- `block` 的 shape 不要求固定为 `256 x 96`，服务端会自动重采样
- 如果只传 `1` 个 chunk，服务会自动补齐缺失历史

### 服务端会自动做什么

- 按 `600m-800m` 裁切/映射物理距离
- 空间重采样到 `96` 列
- 时间重采样到 `256` 步
- 生成 `raw_view`
- 生成 `spectral_view`
- 生成 `37` 维特征
- 组装最多 `8` 个上下文块
- 输出 `human` / `machine`

## 5. 推荐接口的返回格式

示例返回：

```json
{
  "model_name": "actor_domain_generalization",
  "label": "machine",
  "confidence": 0.808819591999054,
  "probabilities": {
    "machine": 0.808819591999054,
    "human": 0.19118033349514008
  },
  "context_len": 8,
  "valid_chunks": 1,
  "input_shapes": {
    "raw_seq": [8, 2, 256, 96],
    "spectral_seq": [8, 1, 48, 96],
    "feature_seq": [8, 37],
    "delta_seq": [8],
    "valid_mask": [8]
  },
  "device": "cpu"
}
```

返回字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `model_name` | `string` | 当前使用的模型名 |
| `label` | `string` | 最终分类结果，`human` 或 `machine` |
| `confidence` | `number` | 最终分类标签的置信度 |
| `probabilities` | `object` | 每个标签的概率 |
| `context_len` | `number` | 模型上下文长度，目前为 `8` |
| `valid_chunks` | `number` | 本次请求实际传入的 chunk 数 |
| `input_shapes` | `object` | 服务端整理后的模型输入 shape |
| `device` | `string` | 实际推理设备，如 `cpu` 或 `cuda` |

## 6. 错误返回和前端该怎么处理

常见状态码：

| 状态码 | 含义 | 常见原因 |
|---|---|---|
| `200` | 成功 | 推理正常 |
| `422` | 请求参数错误 | `block` 不是二维数组、shape 非法、距离范围不覆盖 `600m-800m`、chunk 数超过 `8` |
| `503` | 服务暂时不可用 | checkpoint 缺失、模型未加载成功、设备不可用，例如强制 `cuda` 但机器没有 CUDA |

前端或平台侧建议：

- `422` 直接展示“输入格式/数据范围错误”
- `503` 展示“模型服务暂时不可用”，并允许重试
- 对请求设置超时
- 保留原始请求摘要和响应，便于排查

## 7. TypeScript 接口定义

```ts
export type VibRecRawChunk = {
  block: number[][];
  scan_rate_hz: number;
  range_start_m: number;
  range_end_m: number;
  delta_seconds?: number | null;
};

export type VibRecRawPredictionRequest = {
  chunks: VibRecRawChunk[];
};

export type VibRecPredictionResponse = {
  model_name: string;
  label: "human" | "machine";
  confidence: number;
  probabilities: Record<string, number>;
  context_len: number;
  valid_chunks: number;
  input_shapes: Record<string, number[]>;
  device: string;
};
```

## 8. 浏览器/前端 `fetch` 示例

```ts
export async function predictActorRaw(
  baseUrl: string,
  payload: {
    chunks: Array<{
      block: number[][];
      scan_rate_hz: number;
      range_start_m: number;
      range_end_m: number;
      delta_seconds?: number | null;
    }>;
  }
) {
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/api/v1/predict/actor/raw`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      `VibRec request failed: ${response.status} ${JSON.stringify(data)}`
    );
  }
  return data as {
    model_name: string;
    label: "human" | "machine";
    confidence: number;
    probabilities: Record<string, number>;
    context_len: number;
    valid_chunks: number;
    input_shapes: Record<string, number[]>;
    device: string;
  };
}
```

最小调用示例：

```ts
const payload = {
  chunks: [
    {
      block: [
        [0.1, 0.2],
        [0.3, 0.4]
      ],
      scan_rate_hz: 2000,
      range_start_m: 600,
      range_end_m: 800,
      delta_seconds: 0
    }
  ]
};

const result = await predictActorRaw("http://localhost:8000", payload);
console.log(result.label, result.confidence);
```

## 9. Node/BFF 代理调用示例

如果你的前端平台本身有服务端，推荐把 VibRec 包在你自己的 API 后面。

```ts
import express from "express";

const app = express();
app.use(express.json({ limit: "20mb" }));

app.post("/api/vibrec/predict", async (req, res) => {
  const response = await fetch("http://vibrec-host:8000/api/v1/predict/actor/raw", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req.body),
  });

  const data = await response.json().catch(() => null);
  res.status(response.status).json(data);
});
```

这种方式通常比浏览器直连更稳。

## 10. 如果你非要用 canonical 接口

接口：

```text
POST /api/v1/predict/actor
```

请求体结构：

```json
{
  "chunks": [
    {
      "raw_view": [[[0.0]]],
      "spectral_view": [[[0.0]]],
      "feature_vector": [0.0],
      "delta_seconds": 0.0
    }
  ],
  "feature_vectors_are_normalized": false
}
```

当前模型要求：

- `raw_view`: `[2, 256, 96]`
- `spectral_view`: `[1, 48, 96]`
- `feature_vector`: `[37]`
- 最多 `8` 个 chunk

这个接口更容易因为 shape 或归一化不一致而失败，平台集成默认不要选它。

## 11. 给前端平台 Codex agent 的直接指令

你可以把下面这段直接交给前端平台里的 Codex agent：

```text
请将 VibRec 模型服务接入当前平台。默认使用 POST /api/v1/predict/actor/raw。
实现一个可复用的 API client，支持：
1. 调用 GET /api/v1/health 做服务可用性检查
2. 调用 GET /api/v1/predict/actor/schema 拉取模型输入约束
3. 调用 POST /api/v1/predict/actor/raw 发送 JSON 请求
4. 对 422 和 503 做明确错误处理
5. 保留 TypeScript 类型定义
6. 如果当前平台是浏览器直连，请确认后端已配置 VIBREC_CORS_ALLOW_ORIGINS；如果没有，则改为通过平台自己的服务端代理调用

请求体类型：
{
  chunks: Array<{
    block: number[][];
    scan_rate_hz: number;
    range_start_m: number;
    range_end_m: number;
    delta_seconds?: number | null;
  }>;
}

约束：
- chunks 按时间从旧到新排列
- chunks 最多 8 个
- range_start_m 到 range_end_m 必须覆盖 600m-800m
- block 必须是二维数值数组
```

## 12. 实际接入建议

- 如果只是验证连通性，先传 `1` 个 chunk
- 如果是实时流式场景，再扩展到 `2-8` 个 chunk 上下文
- 如果前端上传的原始矩阵很大，优先走后端/BFF
- 如果需要公网接入，自己在外层补鉴权、限流和审计

## 13. 前端落地流程

建议平台侧按下面顺序落地：

1. 启动时调用 `GET /api/v1/health`，只做可用性探测。
2. 初始化时调用 `GET /api/v1/predict/actor/schema`，缓存 `max_context_chunks` 和 shape 约束。
3. 业务侧准备 `1-8` 个 `chunks`，顺序必须是从旧到新。
4. 默认调用 `POST /api/v1/predict/actor/raw`，不要优先接 canonical 接口。
5. 页面展示时主要使用 `label`、`confidence`、`probabilities.machine`、`probabilities.human`。
6. 对 `422` 做数据校验提示，对 `503` 做服务不可用提示和重试。

如果你的平台有自己的后端层，建议把 VibRec API 封装成你平台内部的一个模型能力接口，再暴露给前端页面使用。

