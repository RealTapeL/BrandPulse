"""
抓取任务 API：
- POST /api/v1/crawl_jobs：创建任务并入队 RQ，返回 job_id
- GET  /api/v1/crawl_jobs/{job_id}：查询任务状态

TODO: worker 执行后若需持久化原始 JSON 到 data/raw，可在 queue/worker 中扩展。
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from brandpulse.collectors.jobs import CrawlJobEnqueueError, create_crawl_job as create_job
from brandpulse.db_clients.postgres_client import PostgresClient

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


@router.get("/{job_id}", response_model=CrawlJobResponse)
def get_crawl_job(job_id: str):
    """查询任务状态与结果。"""
    sql = """
        SELECT job_id, brand_id, mall, category, status, created_at, finished_at, result
        FROM crawl_jobs WHERE job_id = :id
    """
    client = PostgresClient()
    try:
        result = client.execute(sql, {"id": job_id})
        row = result.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询任务失败: {e}") from e

    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")

    return CrawlJobResponse(
        job_id=row[0],
        brand_id=row[1],
        mall=row[2],
        category=row[3],
        status=row[4],
        created_at=str(row[5]) if row[5] else None,
        finished_at=str(row[6]) if row[6] else None,
        result=row[7],
    )
