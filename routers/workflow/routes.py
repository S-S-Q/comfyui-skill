from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import shutil
import json
from typing import List, Dict, Any, Optional

from services.comfyui_client import ComfyUIClientManager

router = APIRouter()

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "data"
WORKFLOW_DIR = BASE_DATA_DIR / "workflow"


def auto_generate_schema_from_data(workflow_data: Dict[str, Any], workflow_id: str) -> Dict[str, Any]:
    """从 workflow_data 自动生成 schema（支持新旧两种格式）"""
    exposed_fields = {}
    node_counter = {}

    # 兼容新旧两种格式
    # 新格式：{"nodes": [{id, type, inputs: [{name, type, link}], ...}]}
    # 旧格式：{"3": {"class_type": "KSampler", "inputs": {...}}, ...}
    if "nodes" in workflow_data and isinstance(workflow_data["nodes"], list):
        # 新格式
        for node in workflow_data["nodes"]:
            node_id = str(node.get("id", ""))
            class_type = node.get("type", "Unknown")
            inputs = node.get("inputs", [])

            if class_type not in node_counter:
                node_counter[class_type] = 0
            node_counter[class_type] += 1
            suffix = node_counter[class_type] if node_counter[class_type] > 1 else ""

            for inp in inputs:
                if isinstance(inp, dict):
                    field_name = inp.get("name", "")
                    field_value = inp.get("default", None)
                    if field_value is None:
                        continue

                    key = f"{class_type.lower()}_{suffix}_{field_name}" if suffix else f"{class_type.lower()}_{field_name}"
                    key = key.replace("loader", "").replace("checkpoint", "ckpt")

                    if isinstance(field_value, bool):
                        field_type = "boolean"
                    elif isinstance(field_value, int):
                        field_type = "integer"
                    elif isinstance(field_value, float):
                        field_type = "float"
                    else:
                        field_type = "string"

                    # checkpoint模型选择字段不允许屏蔽
                    maskable = True
                    if class_type == "CheckpointLoaderSimple" and field_name == "ckpt_name":
                        maskable = False

                    exposed_fields[key] = {
                        "field_path": f"{node_id}.inputs.{field_name}",
                        "type": field_type,
                        "label": f"{class_type} - {field_name}",
                        "required": False,
                        "default": field_value,
                        "min": None,
                        "max": None,
                        "options": None,
                        "maskable": maskable
                    }
    else:
        # 旧格式
        for node_id, node_data in workflow_data.items():
            if not isinstance(node_data, dict):
                continue

            inputs = node_data.get("inputs", {})
            if not inputs:
                continue

            class_type = node_data.get("class_type", "Unknown")
            meta = node_data.get("_meta", {})
            title = meta.get("title", class_type)

            if class_type not in node_counter:
                node_counter[class_type] = 0
            node_counter[class_type] += 1
            suffix = node_counter[class_type] if node_counter[class_type] > 1 else ""

            for field_name, field_value in inputs.items():
                if isinstance(field_value, list):
                    continue

                key = f"{class_type.lower()}_{suffix}_{field_name}" if suffix else f"{class_type.lower()}_{field_name}"
                key = key.replace("loader", "").replace("checkpoint", "ckpt")

                if isinstance(field_value, bool):
                    field_type = "boolean"
                elif isinstance(field_value, int):
                    field_type = "integer"
                elif isinstance(field_value, float):
                    field_type = "float"
                else:
                    field_type = "string"

                # checkpoint模型选择字段不允许屏蔽
                maskable = True
                if class_type == "CheckpointLoaderSimple" and field_name == "ckpt_name":
                    maskable = False

                exposed_fields[key] = {
                    "field_path": f"{node_id}.inputs.{field_name}",
                    "type": field_type,
                    "label": f"{title} - {field_name}",
                    "required": False,
                    "default": field_value,
                    "min": None,
                    "max": None,
                    "options": None,
                    "maskable": maskable
                }

    return {
        "workflow_id": workflow_id,
        "exposed_fields": exposed_fields
    }


class ValidateResponse(BaseModel):
    """验证结果响应"""
    workflow_id: str
    status: str  # "complete" or "incomplete"
    message: str
    missing: List[Dict[str, str]] = []
    found: List[Dict[str, str]] = []
    download_guide: Optional[Dict[str, List[str]]] = None


@router.get("/list")
async def list_workflows():
    """列出所有 workflow_id"""
    if not WORKFLOW_DIR.exists():
        return {"workflows": []}
    workflows = [
        d.name for d in WORKFLOW_DIR.iterdir()
        if d.is_dir() and (d / "workflow.json").exists()
    ]
    return {"workflows": workflows}


@router.post("/validate", response_model=ValidateResponse)
async def validate_workflow(workflow_id: str):
    """
    验证工作流依赖是否完整

    Args:
        workflow_id: 工作流 ID
    """
    workflow_path = WORKFLOW_DIR / workflow_id / "workflow.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    with workflow_path.open() as f:
        workflow_data = json.load(f)

    try:
        client = await ComfyUIClientManager.get_client()
        result = await client.validate_and_fix_workflow(workflow_data)

        return ValidateResponse(
            workflow_id=workflow_id,
            status=result["status"],
            message=result["message"],
            missing=result.get("missing", []),
            found=result.get("found", []),
            download_guide=result.get("download_guide")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/validate/raw")
async def validate_workflow_raw(file: UploadFile = File(...)):
    """
    直接上传 workflow.json 进行验证

    Args:
        file: workflow.json 文件
    """
    try:
        content = await file.read()
        workflow_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON workflow file")

    try:
        client = await ComfyUIClientManager.get_client()
        result = await client.validate_and_fix_workflow(workflow_data)

        return {
            "status": result["status"],
            "message": result["message"],
            "missing": result.get("missing", []),
            "found": result.get("found", []),
            "download_guide": result.get("download_guide")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.get("/{workflow_id}/dependencies")
async def get_workflow_dependencies(workflow_id: str):
    """
    获取工作流依赖的模型列表
    不检查本地是否存在，只返回工作流需要哪些模型
    """
    workflow_path = WORKFLOW_DIR / workflow_id / "workflow.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    with workflow_path.open() as f:
        workflow_data = json.load(f)

    client = await ComfyUIClientManager.get_client()
    dependencies = client.extract_workflow_dependencies(workflow_data)

    return {
        "workflow_id": workflow_id,
        "dependencies": dependencies
    }


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    """获取指定 workflow 的 workflow.json"""
    workflow_path = WORKFLOW_DIR / workflow_id / "workflow.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return FileResponse(workflow_path)


@router.post("/update")
async def update_workflow(workflow_id: str, file: UploadFile = File(...)):
    """上传/更新 workflow.json 文件"""
    workflow_path = WORKFLOW_DIR / workflow_id
    workflow_path.mkdir(parents=True, exist_ok=True)

    file_path = workflow_path / "workflow.json"
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"message": "Workflow updated", "workflow_id": workflow_id, "file": file.filename}


@router.post("/{workflow_id}/upload")
async def upload_workflow_file(workflow_id: str, file: UploadFile = File(...)):
    """上传 workflow.json 文件到指定工作流（自动生成 schema）"""
    workflow_path = WORKFLOW_DIR / workflow_id
    workflow_path.mkdir(parents=True, exist_ok=True)

    # 验证是 JSON 文件
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Only JSON files are allowed")

    file_path = workflow_path / "workflow.json"
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 自动生成 schema
    try:
        with file_path.open("r", encoding="utf-8") as f:
            workflow_data = json.load(f)
        schema = auto_generate_schema_from_data(workflow_data, workflow_id)
        schema_path = workflow_path / "dbschema.json"
        with schema_path.open("w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        schema_generated = True
    except Exception as e:
        schema_generated = False

    return {
        "message": "Workflow uploaded",
        "workflow_id": workflow_id,
        "schema_auto_generated": schema_generated
    }


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """删除工作流"""
    import shutil

    workflow_path = WORKFLOW_DIR / workflow_id
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    # 删除工作流目录
    shutil.rmtree(workflow_path)

    return {"message": "Workflow deleted", "workflow_id": workflow_id}


@router.get("/{workflow_id}/mask")
async def get_workflow_mask(workflow_id: str):
    """获取工作流的屏蔽字段配置"""
    workflow_path = WORKFLOW_DIR / workflow_id
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    mask_path = workflow_path / "mask.json"
    if not mask_path.exists():
        return {"workflow_id": workflow_id, "masked_fields": {}}

    with mask_path.open() as f:
        mask_data = json.load(f)

    return {"workflow_id": workflow_id, "masked_fields": mask_data}


@router.post("/{workflow_id}/mask")
async def save_workflow_mask(workflow_id: str, mask_data: Dict[str, Any]):
    """保存工作流的屏蔽字段配置"""
    workflow_path = WORKFLOW_DIR / workflow_id
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    mask_path = workflow_path / "mask.json"
    with mask_path.open("w") as f:
        json.dump(mask_data.get("masked_fields", {}), f, indent=2)

    return {"message": "Mask saved", "workflow_id": workflow_id}
