# ComfyUI API 文档

本文档描述本项目提供的所有 HTTP API 接口。

- **Base URL**: `http://localhost:8000`
- **API 前缀**: `/api/v1`

## 目录

1. [健康检查](#1-健康检查)
2. [Workflow 管理](#2-workflow-管理)
3. [Schema 管理](#3-schema-管理)
4. [图片生成](#4-图片生成)
5. [模型列表](#5-模型列表)
6. [图片评价](#6-图片评价)
7. [批量图片评分](#7-批量图片评分)

---

## 1. 健康检查

### GET /health

检查服务健康状态。

**响应示例：**
```json
{
  "status": "healthy"
}
```

### GET /

根路径，返回服务信息。

**响应示例：**
```json
{
  "message": "Welcome to API",
  "version": "1.0.0"
}
```

---

## 2. Workflow 管理

### GET /api/v1/data/workflow/list

列出所有已注册的 workflow。

**响应示例：**
```json
{
  "workflows": ["b", "example_workflow"]
}
```

---

### GET /api/v1/data/workflow/{workflow_id}

获取指定 workflow 的 workflow.json 文件。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**响应：** `workflow.json` 文件内容

---

### POST /api/v1/data/workflow/update

上传/更新 workflow.json 文件。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**表单参数：**
- `file`: workflow.json 文件

**响应示例：**
```json
{
  "message": "Workflow updated",
  "workflow_id": "my_workflow",
  "file": "workflow.json"
}
```

---

### POST /api/v1/data/workflow/{workflow_id}/upload

上传 workflow.json 文件到指定工作流。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**表单参数：**
- `file`: workflow.json 文件（必须是 .json 文件）

**响应示例：**
```json
{
  "message": "Workflow uploaded",
  "workflow_id": "my_workflow"
}
```

---

### DELETE /api/v1/data/workflow/{workflow_id}

删除指定工作流。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**响应示例：**
```json
{
  "message": "Workflow deleted",
  "workflow_id": "my_workflow"
}
```

---

### GET /api/v1/data/workflow/{workflow_id}/mask

获取工作流的屏蔽字段配置。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**响应示例：**
```json
{
  "workflow_id": "b",
  "masked_fields": {
    "ksampler_seed": true,
    "ksampler_steps": true
  }
}
```

---

### POST /api/v1/data/workflow/{workflow_id}/mask

保存工作流的屏蔽字段配置。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**请求体：**
```json
{
  "masked_fields": {
    "ksampler_seed": true,
    "ksampler_steps": false
  }
}
```

**响应示例：**
```json
{
  "message": "Mask saved",
  "workflow_id": "b"
}
```

---

### GET /api/v1/data/workflow/{workflow_id}/dependencies

获取工作流依赖的模型列表（不检查本地是否存在）。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**响应示例：**
```json
{
  "workflow_id": "b",
  "dependencies": {
    "checkpoints": ["model.safetensors"],
    "loras": ["lora1.safetensors", "lora2.safetensors"],
    "vaes": [],
    "upscale_models": ["4x-UltraSharp.pth"],
    "embeddings": [],
    "other": []
  }
}
```

---

### POST /api/v1/data/workflow/validate

验证工作流依赖是否完整。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**响应示例：**
```json
{
  "workflow_id": "b",
  "status": "complete",
  "message": "All dependencies are available",
  "missing": [],
  "found": [
    {"type": "checkpoint", "model": "noobaiXLNAIXL_vPred10Version.safetensors"},
    {"type": "lora", "model": "xl_more_art-full_v1.safetensors"}
  ]
}
```

**注意：** 由于 ComfyUI API 不返回具体的模型文件列表，依赖检查仅提取工作流中引用的模型，实际存在性由 ComfyUI 执行时验证。

---

### POST /api/v1/data/workflow/validate/raw

直接上传 workflow.json 进行验证（不保存到文件）。

**表单参数：**
- `file`: workflow.json 文件

**响应格式：** 同 `/validate`

---

## 3. Schema 管理

### GET /api/v1/data/schema/{workflow_id}

获取 workflow 的 schema（暴露给大模型的参数定义）。

- 如果 `dbschema.json` 存在，返回用户定义的 schema
- 否则自动从 `workflow.json` 生成

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**响应示例：**
```json
{
  "workflow_id": "b",
  "exposed_fields": {
    "cliptextencode_text": {
      "field_path": "6.inputs.text",
      "type": "string",
      "label": "CLIP文本编码 - text",
      "required": false,
      "default": "fox boy, furry..."
    },
    "lora_2_lora_name": {
      "field_path": "39.inputs.lora_name",
      "type": "string",
      "label": "加载LoRA - lora_name"
    }
  }
}
```

---

### POST /api/v1/data/schema/{workflow_id}

创建/更新 workflow 的自定义 schema。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**请求体：**
```json
{
  "exposed_fields": {
    "positive_prompt": {
      "field_path": "6.inputs.text",
      "type": "string",
      "label": "正向提示词",
      "required": true,
      "default": ""
    }
  }
}
```

---

### DELETE /api/v1/data/schema/{workflow_id}

删除自定义 schema，恢复自动生成模式。

**路径参数：**
- `workflow_id`: Workflow 唯一标识

**响应示例：**
```json
{
  "message": "Schema deleted, will use auto-generated next time"
}
```

---

## 4. 图片生成

### POST /api/v1/createImage

创建图片生成任务（直接使用 workflow.json）。

**请求体：**
```json
{
  "workflow_id": "example_workflow",
  "output_subdir": "my_images"
}
```

**响应示例：**
```json
{
  "task_id": "abc12345",
  "workflow_id": "example_workflow",
  "status": "pending"
}
```

---

### POST /api/v1/createImage/fromSchema

基于 schema 创建图片生成任务（大模型填充参数后调用）。

**请求体：**
```json
{
  "workflow_id": "b",
  "params": {
    "cliptextencode_text": "a beautiful landscape",
    "lora_2_lora_name": "anime_lora.safetensors",
    "lora_2_strength_model": 0.8
  },
  "output_subdir": "generated"
}
```

**响应示例：**
```json
{
  "task_id": "def67890",
  "workflow_id": "b",
  "status": "pending"
}
```

---

### GET /api/v1/createImage/{task_id}/status

获取图片生成任务状态。

**路径参数：**
- `task_id`: 任务 ID

**响应示例：**
```json
{
  "task_id": "abc12345",
  "workflow_id": "example_workflow",
  "status": "completed",
  "images": ["output/abc123.png"],
  "prompt_id": "prompt_xyz"
}
```

**任务状态：** `pending` | `running` | `completed` | `failed`

---

### GET /api/v1/createImage/{task_id}/images

获取任务生成的图片列表。

**路径参数：**
- `task_id`: 任务 ID

**响应示例：**
```json
{
  "images": [
    "output/my_images/abc123.png"
  ]
}
```

---

### GET /api/v1/createImage/{task_id}/download

下载任务生成的图片。

**路径参数：**
- `task_id`: 任务 ID

**响应：** 图片文件

---

## 5. 模型列表

### GET /api/v1/models

获取所有模型列表。

**响应示例：**
```json
{
  "checkpoints": ["model1.safetensors", "model2.safetensors"],
  "loras": ["lora1.safetensors", "lora2.safetensors"],
  "vaes": ["vae1.pt"],
  "upscale_models": ["4x-UltraSharp.pth"],
  "embeddings": ["EasyNegative.pt"]
}
```

---

### GET /api/v1/models/lora

获取 LoRA 模型列表。

**响应示例：**
```json
{
  "loras": ["lora1.safetensors", "lora2.safetensors"]
}
```

---

### GET /api/v1/models/checkpoint

获取 Checkpoint 模型列表。

**响应示例：**
```json
{
  "checkpoints": ["model1.safetensors", "model2.safetensors"]
}
```

---

### GET /api/v1/models/vae

获取 VAE 模型列表。

**响应示例：**
```json
{
  "vaes": ["vae1.pt"]
}
```

---

### GET /api/v1/models/upscale

获取 Upscale 模型列表。

**响应示例：**
```json
{
  "upscale_models": ["4x-UltraSharp.pth"]
}
```

---

### GET /api/v1/models/embedding

获取 Embedding 模型列表。

**响应示例：**
```json
{
  "embeddings": ["EasyNegative.pt"]
}
```

---

## 6. 图片评价

### POST /api/v1/evaluate

上传图片进行打分和评价（调用大模型 API）。

**表单参数：**
- `file`: 图片文件
- `prompt` (optional): 额外的评价提示

**响应示例：**
```json
{
  "score": 8.5,
  "comment": "图片质量优秀，构图合理，色彩鲜艳。",
  "model": "MiniMax-M2.7",
  "image_path": "temp/abc123.png"
}
```

---

### POST /api/v1/evaluate/url

通过图片 URL 进行打分和评价。

**查询参数：**
- `image_url`: 图片 URL
- `prompt` (optional): 额外的评价提示

**响应示例：**
```json
{
  "score": 7.5,
  "comment": "图片质量良好，但构图可以进一步优化。",
  "model": "MiniMax-M2.7",
  "image_path": "temp/def456.png"
}
```

---

## 7. 批量图片评分

### POST /api/v1/evaluate/batch

批量对文件夹中的图片进行评分（异步任务）。

**请求体：**
```json
{
  "folder_path": "F:/images/output",
  "recursive": false
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `folder_path` | string | 是 | 图片文件夹路径 |
| `recursive` | boolean | 否 | 是否递归扫描子文件夹（默认 false） |

**响应示例：**
```json
{
  "task_id": "0a3ef6fe",
  "status": "pending",
  "total_images": 4
}
```

**支持的图片格式：** `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.gif`

---

### GET /api/v1/evaluate/batch/{task_id}/status

查询批量评分任务状态。

**路径参数：**
- `task_id`: 任务 ID

**响应示例（进行中）：**
```json
{
  "task_id": "0a3ef6fe",
  "status": "running",
  "folder_path": "F:\\images\\output",
  "total_images": 4,
  "completed": 2,
  "progress": "2/4",
  "message": "",
  "error": null,
  "results": []
}
```

**响应示例（已完成）：**
```json
{
  "task_id": "0a3ef6fe",
  "status": "completed",
  "folder_path": "F:\\images\\output",
  "total_images": 4,
  "completed": 4,
  "progress": "4/4",
  "message": "完成，共评估 4 张图片",
  "error": null,
  "results": [
    {
      "image": "F:\\images\\output\\test.png",
      "score": 8,
      "comment": "图片质量优秀...",
      "status": "success",
      "txt_file": "F:\\images\\output\\test.txt"
    }
  ]
}
```

**任务状态：** `pending` | `running` | `completed` | `failed` | `cancelled`

---

### GET /api/v1/evaluate/batch/{task_id}/results

获取批量评分任务的所有结果（仅任务完成后可用）。

**路径参数：**
- `task_id`: 任务 ID

**响应示例：**
```json
{
  "task_id": "0a3ef6fe",
  "total_images": 4,
  "results": [
    {
      "image": "F:\\images\\output\\test1.png",
      "score": 9,
      "comment": "构图简洁对称，色彩鲜明...",
      "status": "success",
      "txt_file": "F:\\images\\output\\test1.txt"
    },
    {
      "image": "F:\\images\\output\\test2.png",
      "score": 0,
      "comment": "评估失败: xxx",
      "status": "failed",
      "txt_file": null
    }
  ]
}
```

---

### DELETE /api/v1/evaluate/batch/{task_id}

取消或清理批量评分任务。

**路径参数：**
- `task_id`: 任务 ID

**响应示例：**
```json
{
  "message": "任务已清理",
  "task_id": "0a3ef6fe"
}
```

---

**生成的评分文件格式：**
```
Score: 9/10
Comment: 图片质量优秀，构图合理...
```

每个图片会生成一个同名的 `.txt` 文件，与图片位于同一目录下。

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_NAME` | MyAPI | 应用名称 |
| `APP_VERSION` | 1.0.0 | 应用版本 |
| `HOST` | 0.0.0.0 | 监听地址 |
| `PORT` | 8000 | 监听端口 |
| `ALLOWED_ORIGINS` | http://localhost:3000 | CORS 允许的源 |
| `COMFYUI_HOST` | http://127.0.0.1:8188 | ComfyUI 服务地址 |
| `COMFYUI_TIMEOUT` | 60.0 | ComfyUI 请求超时(秒) |
| `LLM_API_BASE` | https://api.minimaxi.com/v1 | 大模型 API 地址 |
| `LLM_API_KEY` | - | 大模型 API Key |
| `LLM_MODEL` | MiniMax-M2.7 | 大模型名称 |
| `LLM_TIMEOUT` | 120.0 | 大模型请求超时(秒) |
