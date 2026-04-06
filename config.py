from pydantic_settings import BaseSettings
from typing import List, Optional
from pathlib import Path


class ComfyUISettings(BaseSettings):
    """ComfyUI 相关配置"""
    host: str = "http://127.0.0.1:8188"
    timeout: float = 60.0

    class Config:
        env_prefix = "COMFYUI_"


class LLMSettings(BaseSettings):
    """大模型 API 配置"""
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: str = ""
    model: str = "qwen3.6-plus"
    timeout: float = 120.0

    class Config:
        env_prefix = "LLM_"


class Settings(BaseSettings):
    app_name: str = "MyAPI"
    app_version: str = "1.0.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    allowed_origins: List[str] = ["http://localhost:3000"]

    # ComfyUI 配置
    comfyui: ComfyUISettings = ComfyUISettings()

    # 大模型配置
    llm: LLMSettings = LLMSettings()

    # 图片输出目录
    output_dir: Path = Path(__file__).parent / "output"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
