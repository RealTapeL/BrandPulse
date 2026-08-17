"""自定义指标公式 API：配置、试算和 scope 快照绑定的真实计算结果。"""
import re
import math
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from brandpulse.storage.formula_repository import FormulaRepository
from brandpulse.indicators.custom_formulas import compute_custom_formulas
from brandpulse.indicators.formula_engine import FormulaEvaluationError, evaluate_formula
from brandpulse.indicators.formula_engine import validate_expression_syntax

router = APIRouter(prefix="/api/v1/formulas", tags=["formulas"])

FORBIDDEN_EXPRESSION = re.compile(r";|`|\b(import|require|eval|function|window|document|fetch|ajax|while|for)\b|=>", re.IGNORECASE)
SAFE_EXPRESSION = re.compile(r"^[\w\s+\-*/%().,<>=!&|^~?:\u4e00-\u9fff]+$")


class FormulaParam(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=128)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("参数名必须是字母、数字、下划线组成的变量名")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        try:
            float(value)
        except ValueError as exc:
            raise ValueError("参数值必须是数字") from exc
        if not math.isfinite(float(value)):
            raise ValueError("参数值必须是有限数字")
        return value.strip()


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
        try:
            validate_expression_syntax(expression)
        except FormulaEvaluationError as exc:
            raise ValueError(str(exc)) from exc
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


class FormulaUpdatePayload(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=200)
    expression: Optional[str] = Field(default=None, min_length=1, max_length=500)
    params: Optional[List[FormulaParam]] = None
    enabled: Optional[bool] = None
    remark: Optional[str] = Field(default=None, max_length=200)

    @field_validator("expression")
    @classmethod
    def validate_update_expression(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        expression = value.strip()
        if FORBIDDEN_EXPRESSION.search(expression) or not SAFE_EXPRESSION.fullmatch(expression):
            raise ValueError("表达式包含不允许的内容")
        try:
            validate_expression_syntax(expression)
        except FormulaEvaluationError as exc:
            raise ValueError(str(exc)) from exc
        return expression

    @field_validator("params")
    @classmethod
    def validate_update_params(cls, params: Optional[List[FormulaParam]]) -> Optional[List[FormulaParam]]:
        if params is None:
            return params
        keys = [param.key.strip() for param in params]
        if len(keys) != len(set(keys)):
            raise ValueError("参数名不能重复")
        return params


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
def update_formula(formula_id: str, payload: FormulaUpdatePayload):
    repo = FormulaRepository()
    current = repo.get(formula_id)
    if not current:
        raise HTTPException(status_code=404, detail="公式不存在")
    data = {
        "name": current["name"],
        "description": current.get("description") or "",
        "expression": current["expression"],
        "params": current.get("params") or [],
        "enabled": current["enabled"],
        "remark": current.get("remark") or "",
    }
    data.update(payload.model_dump(exclude_unset=True))
    data["name"] = data["name"].strip()
    data["description"] = data["description"].strip()
    data["remark"] = data["remark"].strip()
    data["params"] = [p.model_dump() if isinstance(p, FormulaParam) else p for p in data["params"]]
    try:
        formula = repo.update(formula_id, data)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="公式名称已存在") from exc
    if not formula:
        raise HTTPException(status_code=404, detail="公式不存在")
    return formula


class FormulaPreviewRequest(BaseModel):
    context: Dict[str, float] = Field(default_factory=dict)


@router.post("/{formula_id}/preview")
def preview_formula(formula_id: str, payload: FormulaPreviewRequest):
    """在显式传入上下文上试算，不写库，不作为正式招商指标。"""
    formula = FormulaRepository().get(formula_id)
    if not formula:
        raise HTTPException(status_code=404, detail="公式不存在")
    params = {}
    for item in formula.get("params") or []:
        try:
            params[item["key"]] = float(item["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"参数 {item!r} 不是数字") from exc
    try:
        value = evaluate_formula(formula["expression"], {**params, **payload.context})
    except FormulaEvaluationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"formula_id": formula_id, "value": value, "context_fields": sorted(payload.context)}


@router.post("/{formula_id}/run")
def run_formula(
    formula_id: str,
    scope_id: Optional[str] = Query(default=None, min_length=1, max_length=64),
    snapshot_id: Optional[str] = Query(default=None, min_length=1, max_length=64),
    # 兼容旧客户端参数；不再用 brand/date 聚合计算。
    stat_date: Optional[str] = Query(default=None),
):
    """按一个可信范围的 ready/published 快照计算指定公式。"""
    formula = FormulaRepository().get(formula_id)
    if not formula:
        raise HTTPException(status_code=404, detail="公式不存在")
    if not formula["enabled"]:
        raise HTTPException(status_code=409, detail="公式未启用")
    if not scope_id:
        detail = "自定义公式必须指定 scope_id，以绑定可信范围和快照"
        if stat_date:
            detail += "；stat_date 旧参数不再用于正式计算"
        raise HTTPException(status_code=422, detail=detail)
    try:
        result = compute_custom_formulas(
            scope_id=scope_id, snapshot_id=snapshot_id, formula_id=formula_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"formula_id": formula_id, **result}


@router.get("/{formula_id}/values")
def list_formula_values(
    formula_id: str,
    brand_id: Optional[str] = None,
    scope_id: Optional[str] = None,
    limit: int = 30,
):
    repo = FormulaRepository()
    if not repo.get(formula_id):
        raise HTTPException(status_code=404, detail="公式不存在")
    if scope_id:
        return {
            "mode": "snapshot",
            "values": repo.list_snapshot_evaluations(formula_id, scope_id=scope_id, limit=limit),
        }
    return {
        "mode": "legacy_brand_date",
        "warning": "未传 scope_id，返回旧 brand/date 兼容结果；该结果不能用于正式招商判断。",
        "values": repo.list_values(formula_id, brand_id=brand_id, limit=limit),
    }


@router.delete("/{formula_id}")
def delete_formula(formula_id: str):
    if not FormulaRepository().delete(formula_id):
        raise HTTPException(status_code=404, detail="公式不存在")
    return {"ok": True}
