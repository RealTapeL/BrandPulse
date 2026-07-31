"""自定义指标公式 API。

公式的执行不在当前范围内；服务端验证用于防止未来接入执行器时遗留危险表达式。
"""
import re
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from brandpulse.storage.formula_repository import FormulaRepository

router = APIRouter(prefix="/api/v1/formulas", tags=["formulas"])

FORBIDDEN_EXPRESSION = re.compile(r";|`|\b(import|require|eval|function|window|document|fetch|ajax|while|for)\b|=>", re.IGNORECASE)
SAFE_EXPRESSION = re.compile(r"^[\w\s+\-*/%().,<>=!&|^~?:\u4e00-\u9fff]+$")


class FormulaParam(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=128)


class FormulaPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=200)
    expression: str = Field(..., min_length=1, max_length=500)
    params: List[FormulaParam] = Field(default_factory=list)
    enabled: bool = True
    remark: str = Field(default="", max_length=200)

    @field_validator("expression")
    @classmethod
    def validate_expression(cls, value: str) -> str:
        expression = value.strip()
        if FORBIDDEN_EXPRESSION.search(expression) or not SAFE_EXPRESSION.fullmatch(expression):
            raise ValueError("表达式包含不允许的内容")
        return expression

    @field_validator("params")
    @classmethod
    def validate_params(cls, params: List[FormulaParam]) -> List[FormulaParam]:
        keys = [param.key.strip() for param in params]
        if len(keys) != len(set(keys)):
            raise ValueError("参数名不能重复")
        return params

    def repository_data(self) -> dict:
        return {
            "name": self.name.strip(),
            "description": self.description.strip(),
            "expression": self.expression,
            "params": [param.model_dump() for param in self.params],
            "enabled": self.enabled,
            "remark": self.remark.strip(),
        }


@router.get("")
def list_formulas():
    return {"formulas": FormulaRepository().list()}


@router.post("")
def create_formula(payload: FormulaPayload):
    try:
        return FormulaRepository().create(payload.repository_data())
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="公式名称已存在") from exc


@router.put("/{formula_id}")
def update_formula(formula_id: str, payload: FormulaPayload):
    try:
        formula = FormulaRepository().update(formula_id, payload.repository_data())
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="公式名称已存在") from exc
    if not formula:
        raise HTTPException(status_code=404, detail="公式不存在")
    return formula


@router.delete("/{formula_id}")
def delete_formula(formula_id: str):
    if not FormulaRepository().delete(formula_id):
        raise HTTPException(status_code=404, detail="公式不存在")
    return {"ok": True}
