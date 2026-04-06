from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, List, Dict, Any
import shutil
import uuid
import asyncio

from services.llm_client import get_llm_client
from config import settings

router = APIRouter()

TEMP_DIR = Path(__file__).parent.parent.parent / "temp"
EVAL_TASKS: Dict[str, Dict[str, Any]] = {}  # 存储评估任务状态

# 支持的图片扩展名
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


class EvaluateRequest(BaseModel):
    """图片打分请求"""
    image_url: Optional[str] = None  # 外部图片 URL（可选）
    prompt: Optional[str] = None  # 额外的评价提示


class EvaluateResponse(BaseModel):
    """图片打分响应"""
    score: float
    comment: str
    model: str
    image_path: Optional[str] = None


@router.post("", response_model=EvaluateResponse)
async def evaluate_image(
    file: UploadFile = File(...),
    prompt: Optional[str] = None
):
    """
    对图片进行打分和评价
    - 支持上传图片文件
    - 调用大模型 API 进行评分
    - 返回评分和大模型的评价
    """
    # 保存上传的图片到临时目录
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    file_ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    temp_path = TEMP_DIR / f"{uuid.uuid4().hex}.{file_ext}"

    with temp_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # 调用大模型进行评价
        llm_client = get_llm_client()
        result = await llm_client.evaluate_image(
            image_path=str(temp_path),
            prompt=prompt
        )

        return EvaluateResponse(
            score=result["score"],
            comment=result["comment"],
            model=result["model"],
            image_path=str(temp_path)
        )

    except Exception as e:
        # 清理临时文件
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.post("/url", response_model=EvaluateResponse)
async def evaluate_image_from_url(
    image_url: str,
    prompt: Optional[str] = None
):
    """
    对图片进行打分和评价（通过 URL）
    - 下载外部图片
    - 调用大模型 API 进行评分
    """
    import httpx

    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # 下载图片
    file_ext = image_url.split(".")[-1] if "." in image_url else "png"
    temp_path = TEMP_DIR / f"{uuid.uuid4().hex}.{file_ext}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(image_url)
            response.raise_for_status()

            with temp_path.open("wb") as f:
                f.write(response.content)

        # 调用大模型进行评价
        llm_client = get_llm_client()
        result = await llm_client.evaluate_image(
            image_path=str(temp_path),
            prompt=prompt
        )

        return EvaluateResponse(
            score=result["score"],
            comment=result["comment"],
            model=result["model"],
            image_path=str(temp_path)
        )

    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/{task_id}/cleanup")
async def cleanup_temp_image(task_id: str):
    """清理临时图片文件"""
    # 这个接口用于删除之前评价时留下的临时文件
    # task_id 在这里实际是文件路径的简化标识
    # 为安全起见，我们不在 API 中直接暴露文件删除功能
    return {"message": "Cleanup not implemented via API"}


# ==================== 批量图片评分接口 ====================

class BatchEvaluateRequest(BaseModel):
    """批量图片评分请求"""
    folder_path: str  # 文件夹路径
    recursive: bool = False  # 是否递归扫描子文件夹


class BatchEvaluateResponse(BaseModel):
    """批量图片评分响应"""
    task_id: str
    status: str
    total_images: int = 0


async def _evaluate_single_image(
    image_path: Path,
    llm_client,
    semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    """评估单张图片（带并发限制）"""
    async with semaphore:
        try:
            result = await llm_client.evaluate_image(str(image_path))
            return {
                "image": str(image_path),
                "score": result["score"],
                "comment": result["comment"],
                "status": "success"
            }
        except Exception as e:
            return {
                "image": str(image_path),
                "score": 0,
                "comment": f"评估失败: {str(e)}",
                "status": "failed"
            }


def _find_images_in_folder(folder_path: Path, recursive: bool) -> List[Path]:
    """查找文件夹中的所有图片"""
    images = []
    if recursive:
        for ext in IMAGE_EXTENSIONS:
            images.extend(folder_path.rglob(f"*{ext}"))
            images.extend(folder_path.rglob(f"*{ext.upper()}"))
    else:
        for ext in IMAGE_EXTENSIONS:
            images.extend(folder_path.glob(f"*{ext}"))
            images.extend(folder_path.glob(f"*{ext.upper()}"))
    return sorted(set(images))


async def _run_batch_evaluation(task_id: str, folder_path: str, recursive: bool):
    """后台任务：批量评估图片"""
    EVAL_TASKS[task_id]["status"] = "running"

    try:
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"文件夹不存在: {folder_path}")
        if not folder.is_dir():
            raise NotADirectoryError(f"路径不是文件夹: {folder_path}")

        # 查找所有图片
        images = _find_images_in_folder(folder, recursive)
        total = len(images)
        EVAL_TASKS[task_id]["total_images"] = total

        if total == 0:
            EVAL_TASKS[task_id]["status"] = "completed"
            EVAL_TASKS[task_id]["message"] = "未找到图片文件"
            return

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(3)

        # 获取 LLM 客户端
        llm_client = get_llm_client()

        # 并发评估所有图片
        tasks = [
            _evaluate_single_image(img, llm_client, semaphore)
            for img in images
        ]
        results = await asyncio.gather(*tasks)

        # 更新进度
        EVAL_TASKS[task_id]["completed"] = total
        EVAL_TASKS[task_id]["results"] = results

        # 为每张图片生成 .txt 文件
        for result in results:
            if result["status"] == "success":
                image_path = Path(result["image"])
                txt_path = image_path.with_suffix(".txt")
                try:
                    with txt_path.open("w", encoding="utf-8") as f:
                        f.write(f"Score: {result['score']:.1f}/10\n")
                        f.write(f"Comment: {result['comment']}\n")
                    result["txt_file"] = str(txt_path)
                except Exception as e:
                    result["txt_file"] = f"创建失败: {str(e)}"

        EVAL_TASKS[task_id]["status"] = "completed"
        EVAL_TASKS[task_id]["message"] = f"完成，共评估 {total} 张图片"

    except Exception as e:
        EVAL_TASKS[task_id]["status"] = "failed"
        EVAL_TASKS[task_id]["error"] = str(e)


@router.post("/batch", response_model=BatchEvaluateResponse)
async def batch_evaluate_images(
    request: BatchEvaluateRequest,
    background_tasks: BackgroundTasks
):
    """
    批量对文件夹中的图片进行评分

    - 扫描文件夹中的所有图片
    - 对每张图片进行 AI 评分
    - 生成对应的 .txt 文件（文件名与图片相同）
    - 返回任务 ID，可通过接口查询进度
    """
    folder = Path(request.folder_path)
    if not folder.exists():
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {request.folder_path}")
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不是文件夹: {request.folder_path}")

    # 快速扫描图片数量
    images = _find_images_in_folder(folder, request.recursive)

    # 创建任务
    task_id = str(uuid.uuid4())[:8]
    EVAL_TASKS[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "folder_path": str(folder),
        "recursive": request.recursive,
        "total_images": len(images),
        "completed": 0,
        "results": [],
        "message": ""
    }

    # 启动后台任务
    background_tasks.add_task(
        _run_batch_evaluation,
        task_id,
        request.folder_path,
        request.recursive
    )

    return BatchEvaluateResponse(
        task_id=task_id,
        status="pending",
        total_images=len(images)
    )


@router.get("/batch/{task_id}/status")
async def get_batch_evaluate_status(task_id: str):
    """
    查询批量评分任务状态

    返回任务进度、已完成数量、评估结果等
    """
    if task_id not in EVAL_TASKS:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = EVAL_TASKS[task_id]
    return {
        "task_id": task_id,
        "status": task["status"],
        "folder_path": task["folder_path"],
        "total_images": task["total_images"],
        "completed": task.get("completed", 0),
        "progress": f"{task.get('completed', 0)}/{task['total_images']}",
        "message": task.get("message", ""),
        "error": task.get("error", None),
        "results": task.get("results", []) if task["status"] == "completed" else []
    }


@router.get("/batch/{task_id}/results")
async def get_batch_evaluate_results(task_id: str):
    """
    获取批量评分任务的所有结果（仅在任务完成后可用）
    """
    if task_id not in EVAL_TASKS:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = EVAL_TASKS[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"任务尚未完成，当前状态: {task['status']}")

    return {
        "task_id": task_id,
        "total_images": task["total_images"],
        "results": task.get("results", [])
    }


@router.delete("/batch/{task_id}")
async def cancel_batch_evaluate(task_id: str):
    """取消批量评分任务（仅在运行中时可取消）"""
    if task_id not in EVAL_TASKS:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = EVAL_TASKS[task_id]
    if task["status"] == "running":
        task["status"] = "cancelled"
        return {"message": "任务已取消", "task_id": task_id}
    elif task["status"] in ("completed", "failed"):
        # 清理已完成的任务
        del EVAL_TASKS[task_id]
        return {"message": "任务已清理", "task_id": task_id}
    else:
        raise HTTPException(status_code=400, detail=f"任务状态为 {task['status']}，无法取消")
