"""内部经营数据导入与经营指标 API。"""
from datetime import date
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from brandpulse.operations.excel_importer import build_template, parse_workbook
from brandpulse.storage.monitoring_repository import MonitoringScopeRepository
from brandpulse.storage.operations_repository import OperationsRepository

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


@router.get("/template")
def download_operations_template():
    """下载不带示例销售数据的标准 POS 导入模板。"""
    return StreamingResponse(
        BytesIO(build_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="BrandPulse_POS_import_template.xlsx"'},
    )


def _read_upload(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=415, detail="仅支持 .xlsx 或 .xlsm 文件")
    try:
        return file.file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"读取 Excel 失败: {exc}") from exc


@router.post("/preview")
def preview_operations(file: UploadFile = File(...)):
    try:
        rows, errors = parse_workbook(_read_upload(file))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"total": len(rows) + len(errors), "valid": len(rows), "errors": errors, "rows": rows[:50]}


@router.post("/import")
def import_operations(file: UploadFile = File(...)):
    try:
        rows, errors = parse_workbook(_read_upload(file))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if errors:
        raise HTTPException(status_code=422, detail={"message": "文件存在校验错误，未导入任何数据", "errors": errors})
    saved = OperationsRepository().upsert_many(rows)
    return {"saved": saved, "source": file.filename}


@router.get("/readiness")
def operations_readiness(scope_id: str = Query(..., min_length=1, max_length=64)):
    """检查品牌、门店、项目映射和真实经营数据是否足以生成销售指标。"""
    scope = MonitoringScopeRepository().get(scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="监测项目不存在")
    return OperationsRepository().mapping_readiness(scope)


@router.get("/metrics/sales-trend")
def sales_trend(
    scope_id: Optional[str] = Query(default=None, max_length=64),
    brand_id: Optional[str] = Query(default=None, max_length=64),
    store_id: Optional[str] = Query(default=None, max_length=64),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
):
    """返回真实经营数据的销售趋势和坪效，不存在数据时返回空 series。"""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date 不能晚于 end_date")
    if scope_id and not MonitoringScopeRepository().get(scope_id):
        raise HTTPException(status_code=404, detail="监测项目不存在")
    rows = OperationsRepository().sales_trend(
        scope_id=scope_id,
        brand_id=brand_id,
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
    )
    series = []
    for row in rows:
        series.append({
            "date": str(row["record_date"]),
            "store_count": int(row["store_count"] or 0),
            "sales_amount": float(row["sales_amount"] or 0),
            "order_count": int(row["order_count"] or 0),
            "customer_flow": int(row["customer_flow"] or 0),
            "customer_price": float(row["customer_price"]) if row["customer_price"] is not None else None,
            "sales_per_sqm": float(row["sales_per_sqm"]) if row["sales_per_sqm"] is not None else None,
        })
    return {
        "series": series,
        "meta": {
            "scope_id": scope_id,
            "brand_id": brand_id,
            "store_id": store_id,
            "count": len(series),
            "source": "store_operations",
        },
    }
