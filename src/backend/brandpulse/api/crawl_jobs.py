"""
抓取任务 API：
- POST /api/v1/crawl_jobs：创建任务并入队 RQ，返回 job_id
- GET  /api/v1/crawl_jobs/{job_id}：查询任务状态

原始结果由采集 worker 按来源和批次写入标准化表及文件快照，任务状态只保存
可追溯摘要，不在 API 进程中重复处理采集数据。
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from brandpulse.collectors.jobs import CrawlJobEnqueueError, create_crawl_job as create_job
from brandpulse.storage.crawl_job_repository import CrawlJobRepository

router = APIRouter(prefix="/api/v1/crawl_jobs", tags=["crawl_jobs"])


class CrawlJobCreate(BaseModel):
    brand_id: str = Field(..., description="品牌 ID")
    mall: str = Field(..., description="商场名，如 苏州中心")
    category: str = Field(..., description="品类，如 咖啡")
    cities: Optional[List[str]] = Field(default=["苏州"], description="城市列表，默认 [苏州]")


class CrawlJobResponse(BaseModel):
    job_id: str
    brand_id: str
    mall: str
    category: str
    status: str
    rq_job_id: Optional[str] = None
    started_at: Optional[str] = None
    attempt_count: int = 0
    created_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[str] = None


@router.post("", response_model=dict)
def create_crawl_job(payload: CrawlJobCreate):
    """创建并 enqueue 抓取任务。"""
    try:
        return create_job(
            brand_id=payload.brand_id,
            mall=payload.mall,
            category=payload.category,
            cities=payload.cities or ["苏州"],
        )
    except CrawlJobEnqueueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建任务失败: {exc}") from exc


@router.get("", response_model=dict)
def list_crawl_jobs(
    brand_id: Optional[str] = Query(default=None, max_length=32),
    status: Optional[str] = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """查询持久化采集任务，页面刷新后仍能恢复真实状态。"""
    repository = CrawlJobRepository()
    repository.recover_stale_pending()
    return repository.list(
        brand_id=brand_id, status=status, limit=size, offset=(page - 1) * size
    )


@router.get("/{job_id}", response_model=CrawlJobResponse)
def get_crawl_job(job_id: str):
    """查询任务状态与结果。"""
    repository = CrawlJobRepository()
    repository.recover_stale_pending()
    row = repository.get(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return CrawlJobResponse(**{key: row.get(key) for key in CrawlJobResponse.model_fields})
