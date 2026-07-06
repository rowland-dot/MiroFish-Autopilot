"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM客户端"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        reasoning_effort: Optional[str] = None,
        extra_body: Optional[Dict] = None
    ) -> str:
        """
        发送聊天请求

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            reasoning_effort: 推理力度（'low'/'medium'/'high'）。推理型模型（如
                MiniMax-M3）默认会输出大量思考token，可能挤占 max_tokens 导致输出
                被截断；对结构化/JSON 输出降低推理力度可避免截断并降低成本。

        Returns:
            模型响应文本
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        if extra_body:
            kwargs["extra_body"] = extra_body

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 16384,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON（对推理型模型做了健壮性处理）

        推理型模型（如 MiniMax-M3）的思考token长度不确定，可能挤占 max_tokens 导致
        大型 JSON 被截断、解析失败（500）。为此三重防护：
          1. reasoning_effort='low' 降低推理量（思考在 <think> 中会被剥离）；
          2. 给足 max_tokens 作为余量（仅为上限，按实际用量计费）；
          3. 解析失败时自动重试（模型非确定性，重试通常即可得到完整JSON）。

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数上限（余量，避免大型JSON被截断）
            max_retries: 解析失败时的最大尝试次数

        Returns:
            解析后的JSON对象
        """
        last_cleaned = ""
        for _ in range(max(1, max_retries)):
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                reasoning_effort="low"
            )
            # 清理 markdown 代码块标记
            cleaned = response.strip()
            cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\n?```\s*$', '', cleaned)
            cleaned = cleaned.strip()
            last_cleaned = cleaned
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue  # 截断/非确定性输出 → 重试

        raise ValueError(f"LLM返回的JSON格式无效（{max_retries}次尝试后）: {last_cleaned}")

