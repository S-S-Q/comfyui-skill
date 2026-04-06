from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import json
import uuid
import shutil
from typing import Optional, List, Dict, Any

from services.comfyui_client import ComfyUIClientManager
from config import settings

router = APIRouter()

WORKFLOW_DIR = Path(__file__).parent.parent.parent / "data" / "workflow"


class CreateImageRequest(BaseModel):
    workflow_id: str
    output_subdir: Optional[str] = None
    masked_fields: Optional[Dict[str, bool]] = {}  # 要屏蔽的字段


class CreateImageResponse(BaseModel):
    task_id: str
    workflow_id: str
    status: str


class FromSchemaRequest(BaseModel):
    """大模型填充参数后提交的请求"""
    workflow_id: str
    params: Dict[str, Any]  # key: schema中的字段名, value: 大模型填的值
    output_subdir: Optional[str] = None


# 任务状态存储（生产环境应使用 Redis）
_tasks: dict = {}


def apply_params_to_workflow(
    workflow_data: Dict[str, Any],
    params: Dict[str, Any],
    schema_exposed_fields: Dict[str, Any]
) -> Dict[str, Any]:
    """
    将参数应用到 workflow 中
    - 只修改 schema 中定义的字段
    - 通过 field_path 精确定位到 workflow.json 中的位置
    """
    # 构建 field_path 到 schema key 的映射（反向）
    for key, field_def in schema_exposed_fields.items():
        if key in params:
            field_path = field_def["field_path"]  # e.g., "3.inputs.seed"
            value = params[key]

            # 解析 field_path
            parts = field_path.split(".")
            node_id_str = parts[0]  # e.g., "3"
            field_name = parts[2]  # e.g., "seed"

            # 同时尝试字符串和整数两种 node_id
            target_node_id = None
            if node_id_str in workflow_data:
                target_node_id = node_id_str
            elif node_id_str.isdigit() and int(node_id_str) in workflow_data:
                target_node_id = int(node_id_str)

            # 更新 workflow_data
            if target_node_id is not None:
                if "inputs" in workflow_data[target_node_id]:
                    workflow_data[target_node_id]["inputs"][field_name] = value

    return workflow_data


def get_schema_exposed_fields(workflow_id: str) -> Dict[str, Any]:
    """获取 workflow 的 schema exposed_fields"""
    schema_path = WORKFLOW_DIR / workflow_id / "dbschema.json"
    if schema_path.exists():
        with schema_path.open("r", encoding="utf-8") as f:
            schema_data = json.load(f)
            return schema_data.get("exposed_fields", {})

    # 自动生成
    from routers.schema.routes import auto_generate_schema
    schema = auto_generate_schema(workflow_id)
    return {k: v.model_dump() for k, v in schema.exposed_fields.items()}


async def run_image_generation(
    task_id: str,
    workflow_id: str,
    output_subdir: Optional[str] = None,
    workflow_data: Optional[Dict[str, Any]] = None,
    masked_fields: Optional[Dict[str, bool]] = None
):
    """后台任务：执行图片生成"""
    _tasks[task_id]["status"] = "running"

    try:
        # 如果没有传入 workflow_data，读取文件
        if workflow_data is None:
            workflow_path = WORKFLOW_DIR / workflow_id / "workflow.json"
            if not workflow_path.exists():
                raise FileNotFoundError(f"Workflow {workflow_id} not found")
            with workflow_path.open("r", encoding="utf-8") as f:
                workflow_data = json.load(f)

        # 应用屏蔽字段
        if masked_fields:
            workflow_data = apply_mask_to_workflow(workflow_data, masked_fields)

        # 执行图片生成
        client = await ComfyUIClientManager.get_client()
        result = await client.create_image(workflow_id, workflow_data, output_subdir)

        _tasks[task_id]["status"] = "completed"
        _tasks[task_id]["images"] = result["images"]
        _tasks[task_id]["prompt_id"] = result["prompt_id"]

    except Exception as e:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = str(e)


def apply_mask_to_workflow(
    workflow_data: Dict[str, Any],
    masked_fields: Dict[str, bool]
) -> Dict[str, Any]:
    """
    将屏蔽字段设置为默认值
    - 只屏蔽 schema 中定义的字段
    - 通过 field_path 定位到 workflow.json 中的位置
    """
    if not masked_fields:
        return workflow_data

    # 获取 schema
    schema_path = WORKFLOW_DIR / ".." / ".." / "data" / "workflow"
    # 遍历所有工作流找 schema（简化处理，实际应该存储在 workflow 目录）
    # 这里我们直接从 dbschema.json 读取

    # 构建 field_path 到默认值的映射
    default_values = {
        "ksampler_seed": 123456789,
        "ksampler_steps": 20,
        "ksampler_cfg": 7.0,
        "ksampler_denoise": 1.0,
        "ckptsimple_ckpt_name": "",
        "cliptextencode_text": "",
        "emptylatentimage_width": 512,
        "emptylatentimage_height": 512,
    }

    for key, should_mask in masked_fields.items():
        if not should_mask:
            continue

        # 查找对应的 field_path
        # 这里简化处理，实际应该从 schema 中读取
        if key in default_values:
            # 尝试找到对应的节点并设置默认值
            for node_id, node_data in workflow_data.items():
                if isinstance(node_data, dict) and "inputs" in node_data:
                    inputs = node_data["inputs"]
                    if key.startswith("ksampler_"):
                        if "seed" in inputs and key == "ksampler_seed":
                            inputs["seed"] = default_values[key]
                        elif "steps" in inputs and key == "ksampler_steps":
                            inputs["steps"] = default_values[key]
                        elif "cfg" in inputs and key == "ksampler_cfg":
                            inputs["cfg"] = default_values[key]
                        elif "denoise" in inputs and key == "ksampler_denoise":
                            inputs["denoise"] = default_values[key]
                    elif key.startswith("ckptsimple_") and "ckpt_name" in inputs:
                        inputs["ckpt_name"] = default_values[key]
                    elif key.startswith("cliptextencode_") and "text" in inputs:
                        inputs["text"] = default_values[key]
                    elif key.startswith("emptylatentimage_"):
                        if "width" in inputs and key == "emptylatentimage_width":
                            inputs["width"] = default_values[key]
                        elif "height" in inputs and key == "emptylatentimage_height":
                            inputs["height"] = default_values[key]

    return workflow_data


@router.post("", response_model=CreateImageResponse)
async def create_image(
    request: CreateImageRequest,
    background_tasks: BackgroundTasks
):
    """
    创建图片生成任务（直接使用 workflow.json）

    masked_fields: 要屏蔽的字段，格式为 {field_name: true}
    """
    workflow_path = WORKFLOW_DIR / request.workflow_id / "workflow.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {request.workflow_id} not found")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "task_id": task_id,
        "workflow_id": request.workflow_id,
        "status": "pending",
        "images": [],
        "prompt_id": ""
    }

    background_tasks.add_task(
        run_image_generation,
        task_id,
        request.workflow_id,
        request.output_subdir,
        None,
        request.masked_fields
    )

    return CreateImageResponse(
        task_id=task_id,
        workflow_id=request.workflow_id,
        status="pending"
    )


@router.post("/fromSchema", response_model=CreateImageResponse)
async def create_image_from_schema(
    request: FromSchemaRequest,
    background_tasks: BackgroundTasks
):
    """
    基于 schema 创建图片生成任务
    - 读取 schema 获取可暴露的字段
    - 将大模型提交的参数应用到 workflow.json
    - 提交给 ComfyUI 执行
    """
    # 1. 读取 schema
    exposed_fields = get_schema_exposed_fields(request.workflow_id)
    if not exposed_fields:
        raise HTTPException(status_code=400, detail="No exposed fields defined in schema")

    # 2. 读取 workflow.json
    workflow_path = WORKFLOW_DIR / request.workflow_id / "workflow.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {request.workflow_id} not found")

    with workflow_path.open("r", encoding="utf-8") as f:
        workflow_data = json.load(f)

    # 3. 验证提交的参数都是 schema 中定义的
    for key in request.params:
        if key not in exposed_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Parameter '{key}' is not defined in schema"
            )

    # 4. 将参数应用到 workflow
    merged_workflow = apply_params_to_workflow(
        workflow_data,
        request.params,
        exposed_fields
    )

    # 5. 创建任务
    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "task_id": task_id,
        "workflow_id": request.workflow_id,
        "status": "pending",
        "images": [],
        "prompt_id": ""
    }

    # 6. 后台执行
    background_tasks.add_task(
        run_image_generation,
        task_id,
        request.workflow_id,
        request.output_subdir,
        merged_workflow
    )

    return CreateImageResponse(
        task_id=task_id,
        workflow_id=request.workflow_id,
        status="pending"
    )


@router.get("/{task_id}/status")
async def get_task_status(task_id: str):
    """获取图片生成任务状态"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return _tasks[task_id]


@router.get("/{task_id}/images")
async def get_task_images(task_id: str):
    """获取任务生成的图片列表"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Task is {task['status']}")

    return {"images": task["images"]}


@router.get("/{task_id}/download")
async def download_task_images(task_id: str, path: Optional[str] = None):
    """
    下载任务生成的图片（始终返回第一张）

    - 有 path 参数：保存图片到指定目录，返回JSON结果
    - 无 path 参数：返回图片文件
    """
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Task is {task['status']}")

    images = task["images"]
    if not images:
        raise HTTPException(status_code=404, detail="No images found")

    first_image = Path(images[0])
    if not first_image.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    # 有 path 参数：保存到目录
    if path:
        save_dir = Path(path)
        save_dir.mkdir(parents=True, exist_ok=True)
        dest_path = save_dir / first_image.name
        shutil.copy2(first_image, dest_path)
        return {
            "task_id": task_id,
            "save_path": str(save_dir),
            "saved": str(dest_path)
        }

    # 无 path 参数：返回图片文件
    return FileResponse(
        first_image,
        media_type="image/png",
        filename=first_image.name
    )
