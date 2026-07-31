"""
Agent Tool 标准接口：每个工具统一暴露 name/description/schema/execute，
便于 LLM Agent 框架（Pydantic AI / LangChain / 自研）调用。
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict

from pydantic import BaseModel, Field


class Tool(ABC):
    """Agent Tool 抽象基类。"""

    name: str
    description: str

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """返回 JSON Schema 描述输入参数（用于 LLM function calling）。"""

    @property
    @abstractmethod
    def output_schema(self) -> Dict[str, Any]:
        """返回 JSON Schema 描述输出结构。"""

    @abstractmethod
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具。

        Returns:
            { success: bool, result: Any|None, error: str|None, meta: { latency_ms: float, ... } }
        """


class FunctionTool(Tool):
    """用普通 Python 函数包装成的 Tool。"""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[[Dict[str, Any]], Dict[str, Any]],
        input_model: type[BaseModel],
    ):
        self.name = name
        self.description = description
        self._func = func
        self._input_model = input_model

    @property
    def input_schema(self) -> Dict[str, Any]:
        return self._input_model.model_json_schema()

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "result": {},
                "error": {"type": ["string", "null"]},
                "meta": {"type": "object"},
            },
        }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        validated = self._input_model.model_validate(args)
        return self._func(validated.model_dump())


class ToolInput(BaseModel):
    """通用输入校验基类（派生模型使用）。"""

    pass


__all__ = ["Tool", "FunctionTool", "ToolInput"]
