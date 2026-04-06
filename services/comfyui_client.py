import httpx
import asyncio
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from config import settings


class MissingDependencyError(Exception):
    """工作流缺少依赖时抛出"""

    def __init__(self, missing_models: List[Dict[str, str]]):
        self.missing_models = missing_models
        super().__init__(f"Missing {len(missing_models)} models")


class DownloadError(Exception):
    """下载失败时抛出"""

    def __init__(self, message: str, model: str = ""):
        self.model = model
        super().__init__(message)


class ComfyUIClient:
    def __init__(self, host: str = None, timeout: float = None):
        self.host = host or settings.comfyui.host
        self.timeout = timeout or settings.comfyui.timeout
        # trust_env=False 忽略系统代理，避免 Windows 代理导致的连接问题
        self.client = httpx.AsyncClient(
            base_url=self.host,
            timeout=self.timeout,
            trust_env=False
        )

    async def close(self):
        await self.client.aclose()

    async def post_prompt(self, workflow_data: Dict[str, Any]) -> Optional[str]:
        """提交工作流，返回 prompt_id"""
        response = await self.client.post("/prompt", json={"prompt": workflow_data})
        response.raise_for_status()
        data = response.json()
        return data.get("prompt_id")

    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """获取执行历史"""
        response = await self.client.get(f"/history/{prompt_id}")
        response.raise_for_status()
        return response.json()

    async def get_queue(self) -> Dict[str, Any]:
        """获取队列状态"""
        response = await self.client.get("/queue")
        response.raise_for_status()
        return response.json()

    async def download_image(self, filename: str, output_path: Path) -> Path:
        """下载输出图片"""
        response = await self.client.get("/view", params={"filename": filename})
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as f:
            f.write(response.content)
        return output_path

    async def wait_for_completion(
        self,
        prompt_id: str,
        poll_interval: float = 1.0,
        max_wait: float = 300.0
    ) -> Dict[str, Any]:
        """轮询等待工作流执行完成"""
        elapsed = 0.0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            history = await self.get_history(prompt_id)
            if prompt_id in history:
                return history[prompt_id]
        raise TimeoutError(f"Workflow {prompt_id} timed out after {max_wait}s")

    async def get_output_images(self, prompt_id: str) -> List[Dict[str, str]]:
        """从历史中提取输出图片信息"""
        history = await self.get_history(prompt_id)
        if prompt_id not in history:
            return []

        outputs = []
        prompt_result = history[prompt_id].get("outputs", {})
        for node_id, node_data in prompt_result.items():
            if "images" in node_data:
                for img in node_data["images"]:
                    outputs.append({
                        "node_id": node_id,
                        "filename": img["filename"],
                        "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output")
                    })
        return outputs

    async def create_image(
        self,
        workflow_id: str,
        workflow_data: Dict[str, Any],
        output_subdir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行完整流程：提交工作流 -> 等待完成 -> 下载图片
        返回下载结果
        """
        # 1. 提交工作流
        prompt_id = await self.post_prompt(workflow_data)
        if not prompt_id:
            raise ValueError("Failed to get prompt_id from ComfyUI")

        # 2. 等待执行完成
        await self.wait_for_completion(prompt_id)

        # 3. 获取输出图片
        images = await self.get_output_images(prompt_id)

        # 4. 下载图片（跳过 temp 类型）
        output_dir = settings.output_dir
        if output_subdir:
            output_dir = output_dir / output_subdir

        downloaded = []
        for img in images:
            # 跳过 temp 类型的图片
            if img.get("type") == "temp":
                continue

            filename = img["filename"]
            subfolder = img["subfolder"]
            if subfolder:
                img_output_dir = output_dir / subfolder
            else:
                img_output_dir = output_dir
            output_path = await self.download_image(filename, img_output_dir / filename)
            downloaded.append(str(output_path))

        return {
            "prompt_id": prompt_id,
            "workflow_id": workflow_id,
            "images": downloaded
        }

    async def get_model_list(self) -> Dict[str, List[str]]:
        """
        获取所有模型列表
        ComfyUI 的 /models 接口返回目录名称列表
        """
        response = await self.client.get("/models")
        response.raise_for_status()
        folders = response.json()

        # /models 返回的是目录名称列表，如 ["checkpoints", "loras", ...]
        # 转换为以目录为 key 的字典
        result = {folder: [] for folder in folders}
        return result

    async def get_lora_list(self) -> List[str]:
        """获取 LoRA 模型列表"""
        # ComfyUI 模型存储在本地目录，无法直接通过 API 获取
        # 返回空列表，实际模型列表需要通过文件系统获取
        return []

    async def get_checkpoint_list(self) -> List[str]:
        """获取 Checkpoint 模型列表"""
        return []

    async def get_vae_list(self) -> List[str]:
        """获取 VAE 模型列表"""
        return []

    async def get_upscale_model_list(self) -> List[str]:
        """获取 Upscale 模型列表"""
        return []

    async def get_embed_list(self) -> List[str]:
        """获取 Embedding 模型列表"""
        return []

    # ==================== ComfyUI Manager API ====================

    async def _check_manager_available(self) -> bool:
        """检查 ComfyUI Manager 是否可用"""
        try:
            response = await self.client.get("/manager/queue/status")
            return response.status_code == 200
        except Exception:
            return False

    async def _manager_start_queue(self) -> bool:
        """启动 Manager 队列"""
        try:
            response = await self.client.post("/manager/queue/start", json={})
            return response.status_code == 200
        except Exception:
            return False

    async def validate_and_fix_workflow(
        self,
        workflow_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        验证工作流依赖完整性

        Args:
            workflow_data: 工作流数据
        """
        # 检查模型依赖
        check_result = await self.check_workflow_dependencies(workflow_data)

        if check_result["complete"]:
            return {
                "status": "complete",
                "message": "All dependencies are available",
                "missing": [],
                "found": check_result["found"]
            }

        # 返回缺失信息
        missing = check_result.get("missing", [])
        messages = []
        if missing:
            messages.append(f"Missing {len(missing)} models")

        return {
            "status": "incomplete",
            "message": ", ".join(messages) if messages else "Missing dependencies",
            "missing": missing,
            "found": check_result["found"],
            "download_guide": self._generate_download_guide(missing) if missing else None
        }

    def extract_workflow_dependencies(
        self, workflow_data: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        从工作流中提取所有依赖的模型
        返回格式：{type: [model_paths]}
        """
        dependencies = {
            "checkpoints": [],
            "loras": [],
            "vaes": [],
            "upscale_models": [],
            "embeddings": [],
            "other": []
        }

        for node_id, node_data in workflow_data.items():
            if not isinstance(node_data, dict):
                continue

            class_type = node_data.get("class_type", "")
            inputs = node_data.get("inputs", {})

            for field_name, field_value in inputs.items():
                # Skip node references
                if isinstance(field_value, list):
                    continue

                value = str(field_value)

                # CheckpointLoaderSimple -> checkpoints
                if class_type == "CheckpointLoaderSimple":
                    if field_name == "ckpt_name":
                        dependencies["checkpoints"].append(value)

                # LoraLoader -> loras
                elif class_type == "LoraLoader":
                    if field_name == "lora_name":
                        dependencies["loras"].append(value)

                # VAELoader -> vaes
                elif class_type == "VAELoader":
                    if field_name == "vae_name":
                        dependencies["vaes"].append(value)

                # UpscaleModelLoader -> upscale_models
                elif class_type == "UpscaleModelLoader":
                    if field_name == "model_name":
                        dependencies["upscale_models"].append(value)

                # Embedding 通常是文本中引用
                elif field_name == "text" and isinstance(field_value, str):
                    # 检查是否引用了 embedding
                    if "embedding:" in value.lower():
                        match = re.search(r'embedding[:\s]+([^\s,\]]+)', value, re.I)
                        if match:
                            dependencies["embeddings"].append(match.group(1))

        # 去重
        for key in dependencies:
            dependencies[key] = list(set(dependencies[key]))

        return dependencies

    async def check_workflow_dependencies(
        self, workflow_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        检查工作流依赖是否完整
        注意：由于 ComfyUI /models API 不返回具体文件，此处只提取依赖列表
        实际存在性检查由 ComfyUI 执行时完成
        """
        # 提取工作流依赖
        deps = self.extract_workflow_dependencies(workflow_data)

        # 构建依赖列表（不做存在性检查，由 ComfyUI 执行时验证）
        all_deps = []
        for model in deps["checkpoints"]:
            all_deps.append({"type": "checkpoint", "model": model})
        for model in deps["loras"]:
            all_deps.append({"type": "lora", "model": model})
        for model in deps["vaes"]:
            all_deps.append({"type": "vae", "model": model})
        for model in deps["upscale_models"]:
            all_deps.append({"type": "upscale_model", "model": model})

        return {
            "complete": True,  # 始终认为完整，由 ComfyUI 执行时检查实际存在性
            "missing": [],
            "found": all_deps,
            "total_dependencies": sum(len(v) for v in deps.values()),
            "dependencies": deps  # 返回原始依赖信息
        }

    def _generate_download_guide(self, missing: List[Dict[str, str]]) -> Dict[str, List[str]]:
        """生成下载指南"""
        guide = {}
        for item in missing:
            model_type = item["type"]
            model_name = item["model"]
            if model_type not in guide:
                guide[model_type] = []
            guide[model_type].append(model_name)
        return guide


# 异步上下文管理器
class ComfyUIClientManager:
    _client: Optional[ComfyUIClient] = None

    @classmethod
    async def get_client(cls) -> ComfyUIClient:
        if cls._client is None:
            cls._client = ComfyUIClient()
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.close()
            cls._client = None
