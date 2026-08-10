"""内部经营数据 Excel 导入 API。"""
from fastapi import APIRouter, File, HTTPException, UploadFile

from brandpulse.operations.excel_importer import parse_workbook
from brandpulse.storage.operations_repository import OperationsRepository

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


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
