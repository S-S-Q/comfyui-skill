import httpx
import base64
import json
from typing import Optional, Dict, Any, List
from config import settings


class LLMClient:
    """大模型 API 客户端"""

    def __init__(
        self,
        api_base: str = None,
        api_key: str = None,
        model: str = None,
        timeout: float = None
    ):
        self.api_base = api_base or settings.llm.api_base
        self.api_key = api_key or settings.llm.api_key
        self.model = model or settings.llm.model
        self.timeout = timeout or settings.llm.timeout

        self.client = httpx.AsyncClient(
            base_url=self.api_base,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=self.timeout,
            trust_env=False
        )

    async def close(self):
        await self.client.aclose()

    async def image_to_base64(self, image_path: str) -> str:
        """将图片转换为 base64 字符串"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def evaluate_image(
        self,
        image_path: str,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        调用大模型对图片进行评分和评价

        Args:
            image_path: 图片路径
            prompt: 可选的额外提示词

        Returns:
            {
                "score": 8.5,
                "comment": "图片质量不错，构图合理...",
                "model": "gpt-4o"
            }
        """
        # 将图片转为 base64
        image_base64 = await self.image_to_base64(image_path)

        # 构建提示词
        system_prompt = """你是一位专业的图片质量评估专家。请对图片进行评分和评价。

评分标准（1-10分）：
- 9-10分：优秀，专业水准
- 7-8分：良好，质量不错
- 5-6分：一般，有明显改进空间
- 3-4分：较差，存在较大问题
- 1-2分：很差，基本无法使用

请返回JSON格式：
{
    "score": 评分数字(1-10),
    "comment": "简短的评价，最多100字"
}"""

        user_prompt = f"请评估这张图片的质量：\n\n{prompt or '请从构图、清晰度、色彩、细节等方面进行评估。'}"

        # 调用 OpenAI Vision 兼容 API
        response = await self.client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]}
                ],
                "max_tokens": 500
            }
        )

        response.raise_for_status()
        result = response.json()

        # 解析响应
        content = result["choices"][0]["message"]["content"]

        # 提取 JSON
        try:
            # 尝试直接解析 JSON
            evaluation = json.loads(content)
        except json.JSONDecodeError:
            # 如果失败，尝试提取 ```json ... ```
            import re
            match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                evaluation = json.loads(match.group(1))
            else:
                # 如果还是失败，返回原始内容
                evaluation = {
                    "score": 0,
                    "comment": content[:200]
                }

        return {
            "score": evaluation.get("score", 0),
            "comment": evaluation.get("comment", ""),
            "model": self.model
        }


# 单例模式
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


async def close_llm_client():
    global _llm_client
    if _llm_client is not None:
        await _llm_client.close()
        _llm_client = None
