from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from services.comfyui_client import ComfyUIClientManager

router = APIRouter()


class ModelListResponse(BaseModel):
    checkpoints: List[str] = []
    loras: List[str] = []
    vaes: List[str] = []
    upscale_models: List[str] = []
    embeddings: List[str] = []


class LoraListResponse(BaseModel):
    loras: List[str]


class CheckpointListResponse(BaseModel):
    checkpoints: List[str]


@router.get("", response_model=ModelListResponse)
async def get_all_models():
    """
    获取所有模型列表
    包括: checkpoints, loras, vaes, upscale_models, embeddings
    """
    try:
        client = await ComfyUIClientManager.get_client()
        return ModelListResponse(
            checkpoints=await client.get_checkpoint_list(),
            loras=await client.get_lora_list(),
            vaes=await client.get_vae_list(),
            upscale_models=await client.get_upscale_model_list(),
            embeddings=await client.get_embed_list()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model list: {str(e)}")


@router.get("/lora", response_model=LoraListResponse)
async def get_lora_list():
    """获取 LoRA 模型列表"""
    try:
        client = await ComfyUIClientManager.get_client()
        return LoraListResponse(loras=await client.get_lora_list())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get lora list: {str(e)}")


@router.get("/checkpoint", response_model=CheckpointListResponse)
async def get_checkpoint_list():
    """获取 Checkpoint 模型列表"""
    try:
        client = await ComfyUIClientManager.get_client()
        return CheckpointListResponse(checkpoints=await client.get_checkpoint_list())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get checkpoint list: {str(e)}")


@router.get("/vae")
async def get_vae_list():
    """获取 VAE 模型列表"""
    try:
        client = await ComfyUIClientManager.get_client()
        return {"vaes": await client.get_vae_list()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vae list: {str(e)}")


@router.get("/upscale")
async def get_upscale_model_list():
    """获取 Upscale 模型列表"""
    try:
        client = await ComfyUIClientManager.get_client()
        return {"upscale_models": await client.get_upscale_model_list()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get upscale model list: {str(e)}")


@router.get("/embedding")
async def get_embed_list():
    """获取 Embedding 模型列表"""
    try:
        client = await ComfyUIClientManager.get_client()
        return {"embeddings": await client.get_embed_list()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get embedding list: {str(e)}")
