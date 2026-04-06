# ComfyUI API Service

基于 FastAPI 的 ComfyUI 工作流管理服务，支持图片生成、批量评估等功能。

## 功能特性

- **工作流管理** - 上传、删除、验证 ComfyUI 工作流
- **图片生成** - 通过 API 触发工作流生成图片
- **批量评估** - 对文件夹中的图片进行 AI 评分
- **Schema 管理** - 自动生成/手动配置工作流参数 Schema
- **模型列表** - 获取 ComfyUI 可用模型列表

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的配置
```

主要配置项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `COMFYUI_HOST` | http://127.0.0.1:8188 | ComfyUI 服务地址 |
| `LLM_API_KEY` | - | 大模型 API Key |
| `LLM_MODEL` | qwen3.6-plus | 大模型名称 |

### 3. 启动服务

```bash
python main.py
# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000
```

服务地址：http://localhost:8000

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- API 文档: http://localhost:8000/api/v1

详细接口说明见 [API.md](API.md)

## 核心接口

### 工作流管理

```bash
# 列出所有工作流
curl http://localhost:8000/api/v1/data/workflow/list

# 上传工作流（自动生成 schema）
curl -X POST http://localhost:8000/api/v1/data/workflow/{id}/upload \
  -F "file=@workflow.json"

# 验证工作流依赖
curl -X POST http://localhost:8000/api/v1/data/workflow/validate?workflow_id={id}
```

### 图片生成

```bash
# 提交图片生成任务
curl -X POST http://localhost:8000/api/v1/createImage \
  -H "Content-Type: application/json" \
  -d '{"workflow_id": "my_workflow"}'

# 查询任务状态
curl http://localhost:8000/api/v1/createImage/{task_id}/status

# 下载图片
curl http://localhost:8000/api/v1/createImage/{task_id}/download
curl "http://localhost:8000/api/v1/createImage/{task_id}/download?path=/tmp/imgs"
```

### 批量图片评估

```bash
# 提交评估任务
curl -X POST http://localhost:8000/api/v1/evaluate/batch \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "F:/output", "recursive": false}'

# 查询评估状态
curl http://localhost:8000/api/v1/evaluate/batch/{task_id}/status

# 获取评估结果
curl http://localhost:8000/api/v1/evaluate/batch/{task_id}/results
```

## 项目结构

```
.
├── main.py              # FastAPI 入口
├── config.py            # 配置管理
├── routers/             # API 路由
│   ├── workflow/        # 工作流管理
│   ├── schema/          # Schema 管理
│   ├── createImage/     # 图片生成
│   ├── evaluate/        # 图片评估
│   └── models/          # 模型列表
├── services/            # 业务服务
│   ├── comfyui_client.py   # ComfyUI API 客户端
│   └── llm_client.py       # 大模型 API 客户端
├── data/                # 数据目录
│   └── workflow/        # 工作流文件
│       └── {id}/
│           ├── workflow.json
│           └── dbschema.json
└── output/              # 图片输出目录
```

## SKILL 文件

Agent 使用的 Skill 定义：

- [SKILL - comfyui-createImage](SKILL - 副本.md) - 图片生成
- [SKILL - ImageEval](SKILL - ImageEval.md) - 图片评估

## License

MIT
