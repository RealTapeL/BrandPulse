"""
商场营运数据仓储层

对应 docs/品牌热度布局分布_数据表设计.drawio：
- malls              维度表：商场主数据
- xhs_notes          原始表：小红书笔记
- dp_shop_metrics    原始表：大众点评门店指标
- brand_heat_daily   聚合表：品牌×城市×商场×日期×平台 热度

爬虫只写原始表；aggregate_heat_daily 负责把原始数据汇总进聚合表。
"""
import hashlib
from typing import Dict, List, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


def make_mall_id(city: str, mall_name: str) -> str:
    """由 城市+商场名 生成稳定 mall_id"""
    digest = hashlib.md5(f"{city}|{mall_name}".encode("utf-8")).hexdigest()[:12]
    return f"M_{digest}"


class MallRepository:
    """商场维度表仓储"""

    def __init__(self):
        self.client = PostgresClient()

    def upsert_mall(self, mall: Dict) -> bool:
        """插入或更新商场"""
        sql = """
        INSERT INTO malls (
            mall_id, mall_name, city, district, business_area,
            address, longitude, latitude, is_our_mall, data_source
        ) VALUES (
            :mall_id, :mall_name, :city, :district, :business_area,
            :address, :longitude, :latitude, :is_our_mall, :data_source
        )
        ON CONFLICT (mall_id) DO UPDATE SET
            mall_name = EXCLUDED.mall_name,
            city = EXCLUDED.city,
            district = EXCLUDED.district,
            business_area = EXCLUDED.business_area,
            address = EXCLUDED.address,
            longitude = EXCLUDED.longitude,
            latitude = EXCLUDED.latitude,
            is_our_mall = EXCLUDED.is_our_mall,
            updated_at = CURRENT_TIMESTAMP
        """
        try:
            with self.client.engine.connect() as conn:
                conn.execute(text(sql), mall)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存商场 {mall.get('mall_name')} 失败: {e}")
            return False


class XhsNoteRepository:
    """小红书原始笔记仓储"""

    def __init__(self):
        self.client = PostgresClient()

    def upsert_note(self, note: Dict, lineage: Optional[Dict] = None) -> bool:
        """插入或更新单条笔记（按 note_id 幂等）"""
        sql = """
        INSERT INTO xhs_notes (
            note_id, brand_id, city, mall_name, title, author_name,
            likes, publish_time, note_url, keyword, crawl_date
        ) VALUES (
            :note_id, :brand_id, :city, :mall_name, :title, :author_name,
            :likes, :publish_time, :note_url, :keyword, :crawl_date
        )
        ON CONFLICT (note_id) DO UPDATE SET
            brand_id = EXCLUDED.brand_id,
            city = EXCLUDED.city,
            mall_name = EXCLUDED.mall_name,
            title = EXCLUDED.title,
            author_name = EXCLUDED.author_name,
            likes = EXCLUDED.likes,
            publish_time = EXCLUDED.publish_time,
            note_url = EXCLUDED.note_url,
            keyword = EXCLUDED.keyword,
            crawl_date = EXCLUDED.crawl_date
        """
        try:
            with self.client.engine.begin() as conn:
                conn.execute(text(sql), note)
                if lineage:
                    from brandpulse.storage.raw_lineage_repository import RawLineageRepository

                    RawLineageRepository.record(conn, **lineage)
            return True
        except Exception as e:
            logger.error(f"保存小红书笔记 {note.get('note_id')} 失败: {e}")
            return False


class DpShopMetricRepository:
    """大众点评门店指标仓储"""

    def __init__(self):
        self.client = PostgresClient()

    def upsert_shop_metric(self, shop: Dict, lineage: Optional[Dict] = None) -> bool:
        """插入或更新门店指标（按 店名+城市+采集日期 幂等）"""
        sql = """
        INSERT INTO dp_shop_metrics (
            shop_name, city, crawl_date, brand_id, place,
            score, review_count, avg_price, business_area, shop_text, source_url
        ) VALUES (
            :shop_name, :city, :crawl_date, :brand_id, :place,
            :score, :review_count, :avg_price, :business_area, :shop_text, :source_url
        )
        ON CONFLICT (shop_name, city, crawl_date, brand_id, place) DO UPDATE SET
            brand_id = EXCLUDED.brand_id,
            place = EXCLUDED.place,
            score = EXCLUDED.score,
            review_count = EXCLUDED.review_count,
            avg_price = EXCLUDED.avg_price,
            business_area = EXCLUDED.business_area,
            shop_text = EXCLUDED.shop_text,
            source_url = EXCLUDED.source_url
        """
        try:
            with self.client.engine.begin() as conn:
                conn.execute(text(sql), shop)
                if lineage:
                    from brandpulse.storage.raw_lineage_repository import RawLineageRepository

                    RawLineageRepository.record(conn, **lineage)
            return True
        except Exception as e:
            logger.error(f"保存点评门店 {shop.get('shop_name')} 失败: {e}")
            return False


class BrandHeatRepository:
    """品牌热度聚合表仓储"""

    def __init__(self):
        self.client = PostgresClient()

    def aggregate_for_brand_city(
        self,
        brand_id: str,
        city: str,
        stat_date: str,
        mall_name: str = "",
        platform: str = "all",
    ) -> Dict[str, int]:
        """
        从原始表汇总 品牌×城市×日期 的热度指标。

        按 platform 区分输出行：
        - xiaohongshu: mentions / total_likes / avg_likes / max_likes
        - dianping:    dp_review_count / dp_shop_count / dp_avg_price

        platform 参数控制只聚合哪个平台（"xiaohongshu" / "dianping" / "all"），
        避免采集单一平台时产生另一平台的空行。
        """
        results = {"xiaohongshu": 0, "dianping": 0}

        # 小红书侧聚合
        xhs_sql = """
        INSERT INTO brand_heat_daily (
            stat_date, brand_id, city, mall_name, platform,
            mentions, total_likes, avg_likes, max_likes
        )
        SELECT
            :stat_date, :brand_id, :city, :mall_name, 'xiaohongshu',
            COUNT(*),
            COALESCE(SUM(likes), 0),
            ROUND(AVG(likes)::numeric, 2),
            COALESCE(MAX(likes), 0)
        FROM xhs_notes
        WHERE brand_id = :brand_id AND city = :city AND crawl_date = :stat_date
          AND (:mall_name = '' OR COALESCE(mall_name, '') = :mall_name)
        ON CONFLICT (stat_date, brand_id, city, mall_name, platform) DO UPDATE SET
            mentions = EXCLUDED.mentions,
            total_likes = EXCLUDED.total_likes,
            avg_likes = EXCLUDED.avg_likes,
            max_likes = EXCLUDED.max_likes,
            updated_at = CURRENT_TIMESTAMP
        """
        # 点评侧聚合
        dp_sql = """
        INSERT INTO brand_heat_daily (
            stat_date, brand_id, city, mall_name, platform,
            dp_review_count, dp_shop_count, dp_avg_price
        )
        SELECT
            :stat_date, :brand_id, :city, :mall_name, 'dianping',
            COALESCE(SUM(review_count), 0),
            COUNT(*),
            ROUND(AVG(avg_price)::numeric, 2)
        FROM dp_shop_metrics
        WHERE brand_id = :brand_id AND city = :city AND crawl_date = :stat_date
          AND (:mall_name = '' OR COALESCE(place, '') = :mall_name)
        ON CONFLICT (stat_date, brand_id, city, mall_name, platform) DO UPDATE SET
            dp_review_count = EXCLUDED.dp_review_count,
            dp_shop_count = EXCLUDED.dp_shop_count,
            dp_avg_price = EXCLUDED.dp_avg_price,
            updated_at = CURRENT_TIMESTAMP
        """

        params = {
            "stat_date": stat_date,
            "brand_id": brand_id,
            "city": city,
            "mall_name": mall_name,
        }
        try:
            with self.client.engine.connect() as conn:
                if platform in ("all", "xiaohongshu"):
                    conn.execute(text(xhs_sql), params)
                    results["xiaohongshu"] = 1
                if platform in ("all", "dianping"):
                    conn.execute(text(dp_sql), params)
                    results["dianping"] = 1
                conn.commit()
        except Exception as e:
            logger.error(f"聚合品牌热度失败 {brand_id}/{city}/{stat_date}: {e}")
        return results

    def list_heat(
        self,
        brand_id: Optional[str] = None,
        city: Optional[str] = None,
        stat_date: Optional[str] = None,
    ) -> List[Dict]:
        """查询热度聚合数据"""
        sql = "SELECT * FROM brand_heat_daily WHERE 1=1"
        params = {}
        if brand_id:
            sql += " AND brand_id = :brand_id"
            params["brand_id"] = brand_id
        if city:
            sql += " AND city = :city"
            params["city"] = city
        if stat_date:
            sql += " AND stat_date = :stat_date"
            params["stat_date"] = stat_date
        sql += " ORDER BY stat_date DESC, brand_id, city"

        with self.client.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            return [dict(row) for row in result.mappings().all()]
