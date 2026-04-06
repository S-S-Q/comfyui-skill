from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import json
import shutil
from typing import Optional, Dict, Any, List

router = APIRouter()

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "data"
WORKFLOW_DIR = BASE_DATA_DIR / "workflow"


class FieldDefinition(BaseModel):
    field_path: str  # e.g., "3.inputs.seed"
    type: str  # string, integer, float, boolean
    label: str  # 中文标签
    required: bool = False
    default: Optional[Any] = None
    min: Optional[float] = None
    max: Optional[float] = None
    options: Optional[List[str]] = None  # for enum-like fields


class SchemaDefinition(BaseModel):
    workflow_id: str
    exposed_fields: Dict[str, FieldDefinition]


class SchemaRequest(BaseModel):
    exposed_fields: Dict[str, FieldDefinition]


def auto_generate_schema(workflow_id: str) -> SchemaDefinition:
    """自动从 workflow.json 生成 schema"""
    workflow_path = WORKFLOW_DIR / workflow_id / "workflow.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    with workflow_path.open("r", encoding="utf-8") as f:
        workflow_data = json.load(f)

    exposed_fields = {}
    node_counter = {}

    for node_id, node_data in workflow_data.items():
        if not isinstance(node_data, dict):
            continue

        inputs = node_data.get("inputs", {})
        if not inputs:
            continue

        class_type = node_data.get("class_type", "Unknown")
        meta = node_data.get("_meta", {})
        title = meta.get("title", class_type)

        # 获取该类型节点的序号
        if class_type not in node_counter:
            node_counter[class_type] = 0
        node_counter[class_type] += 1
        suffix = node_counter[class_type] if node_counter[class_type] > 1 else ""

        for field_name, field_value in inputs.items():
            # 跳过节点引用类型的字段 (list 格式通常是引用)
            if isinstance(field_value, list):
                continue

            # 生成 key 名称
            key = f"{class_type.lower()}_{suffix}_{field_name}" if suffix else f"{class_type.lower()}_{field_name}"
            # 简化 key（去掉 Loader 这样的词）
            key = key.replace("loader", "").replace("checkpoint", "ckpt")

            # 判断类型
            if isinstance(field_value, bool):
                field_type = "boolean"
            elif isinstance(field_value, int):
                field_type = "integer"
            elif isinstance(field_value, float):
                field_type = "float"
            else:
                field_type = "string"

            exposed_fields[key] = FieldDefinition(
                field_path=f"{node_id}.inputs.{field_name}",
                type=field_type,
                label=f"{title} - {field_name}",
                default=field_value
            )

    return SchemaDefinition(
        workflow_id=workflow_id,
        exposed_fields=exposed_fields
    )


@router.get("/{workflow_id}", response_model=SchemaDefinition)
async def get_schema(workflow_id: str):
    """
    获取 workflow 的 schema
    - 如果 dbschema.json 存在，返回用户定义的 schema
    - 否则自动从 workflow.json 生成
    """
    schema_path = WORKFLOW_DIR / workflow_id / "dbschema.json"

    if schema_path.exists():
        with schema_path.open("r", encoding="utf-8") as f:
            return SchemaDefinition(**json.load(f))

    # 自动生成
    return auto_generate_schema(workflow_id)


@router.post("/{workflow_id}", response_model=SchemaDefinition)
async def update_schema(workflow_id: str, request: SchemaRequest):
    """创建/更新 workflow 的 schema"""
    # 验证 workflow.json 存在
    workflow_path = WORKFLOW_DIR / workflow_id / "workflow.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    schema_path = WORKFLOW_DIR / workflow_id / "dbschema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)

    schema_data = SchemaDefinition(
        workflow_id=workflow_id,
        exposed_fields=request.exposed_fields
    )

    with schema_path.open("w", encoding="utf-8") as f:
        json.dump(schema_data.model_dump(), f, indent=2, ensure_ascii=False)

    return schema_data


@router.delete("/{workflow_id}")
async def delete_schema(workflow_id: str):
    """删除自定义 schema，恢复自动生成"""
    schema_path = WORKFLOW_DIR / workflow_id / "dbschema.json"
    if schema_path.exists():
        schema_path.unlink()
    return {"message": "Schema deleted, will use auto-generated next time"}
