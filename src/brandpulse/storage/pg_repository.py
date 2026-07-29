"""
PostgreSQL 数据仓储层
"""
from typing import Dict, List, Optional

from sqlalchemy import text

from brandpulse.db_clients.postgres_client import PostgresClient
from brandpulse.logger.logger import get_logger

logger = get_logger(__name__)


class BrandRepository:
    """品牌数据仓储"""

    def __init__(self):
        self.client = PostgresClient()

    def list_brands(self, is_active: Optional[bool] = None) -> List[Dict]:
        """查询品牌列表"""
        sql = "SELECT * FROM brands"
        params = {}
        if is_active is not None:
            sql += " WHERE is_active = :is_active"
            params["is_active"] = is_active
        sql += " ORDER BY brand_id"

        with self.client.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.mappings().all()
            return [dict(row) for row in rows]

    def get_brand(self, brand_id: str) -> Optional[Dict]:
        """根据 ID 查询品牌"""
        sql = "SELECT * FROM brands WHERE brand_id = :brand_id"
        with self.client.engine.connect() as conn:
            result = conn.execute(text(sql), {"brand_id": brand_id})
            row = result.mappings().first()
            return dict(row) if row else None

    def upsert_brand(self, brand: Dict) -> bool:
        """插入或更新品牌"""
        sql = """
        INSERT INTO brands (
            brand_id, brand_name_cn, brand_name_en, category_id, tier, brand_level,
            business_model, founding_year, headquarters, company_name, company_id,
            positioning, target_customer, avg_price_min, avg_price_max,
            standard_area_min, standard_area_max, store_count_national,
            store_count_city, expansion_status, official_website, wechat_official,
            logo_url, search_keywords, data_source, is_active
        ) VALUES (
            :brand_id, :brand_name_cn, :brand_name_en, :category_id, :tier, :brand_level,
            :business_model, :founding_year, :headquarters, :company_name, :company_id,
            :positioning, :target_customer, :avg_price_min, :avg_price_max,
            :standard_area_min, :standard_area_max, :store_count_national,
            :store_count_city, :expansion_status, :official_website, :wechat_official,
            :logo_url, :search_keywords, :data_source, COALESCE(:is_active, TRUE)
        )
        ON CONFLICT (brand_id) DO UPDATE SET
            brand_name_cn = EXCLUDED.brand_name_cn,
            brand_name_en = EXCLUDED.brand_name_en,
            category_id = EXCLUDED.category_id,
            tier = EXCLUDED.tier,
            brand_level = EXCLUDED.brand_level,
            business_model = EXCLUDED.business_model,
            founding_year = EXCLUDED.founding_year,
            headquarters = EXCLUDED.headquarters,
            company_name = EXCLUDED.company_name,
            company_id = EXCLUDED.company_id,
            positioning = EXCLUDED.positioning,
            target_customer = EXCLUDED.target_customer,
            avg_price_min = EXCLUDED.avg_price_min,
            avg_price_max = EXCLUDED.avg_price_max,
            standard_area_min = EXCLUDED.standard_area_min,
            standard_area_max = EXCLUDED.standard_area_max,
            store_count_national = EXCLUDED.store_count_national,
            store_count_city = EXCLUDED.store_count_city,
            expansion_status = EXCLUDED.expansion_status,
            official_website = EXCLUDED.official_website,
            wechat_official = EXCLUDED.wechat_official,
            logo_url = EXCLUDED.logo_url,
            search_keywords = EXCLUDED.search_keywords,
            data_source = EXCLUDED.data_source,
            is_active = EXCLUDED.is_active,
            updated_at = CURRENT_TIMESTAMP
        """
        try:
            with self.client.engine.connect() as conn:
                conn.execute(text(sql), brand)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存品牌 {brand.get('brand_id')} 失败: {e}")
            return False


class StoreRepository:
    """门店数据仓储"""

    def __init__(self):
        self.client = PostgresClient()

    def list_stores(
        self,
        brand_id: Optional[str] = None,
        city: Optional[str] = None,
        is_our_mall: Optional[bool] = None,
    ) -> List[Dict]:
        """查询门店列表"""
        sql = "SELECT * FROM stores WHERE 1=1"
        params = {}

        if brand_id:
            sql += " AND brand_id = :brand_id"
            params["brand_id"] = brand_id
        if city:
            sql += " AND city = :city"
            params["city"] = city
        if is_our_mall is not None:
            sql += " AND is_our_mall = :is_our_mall"
            params["is_our_mall"] = is_our_mall

        sql += " ORDER BY brand_id, city, district"

        with self.client.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.mappings().all()
            return [dict(row) for row in rows]

    def upsert_store(self, store: Dict) -> bool:
        """插入或更新门店"""
        # 确保所有字段都存在，缺失的补 None
        store = {
            "store_id": store.get("store_id"),
            "brand_id": store.get("brand_id"),
            "store_name": store.get("store_name"),
            "province": store.get("province"),
            "city": store.get("city"),
            "district": store.get("district"),
            "mall_name": store.get("mall_name"),
            "address": store.get("address"),
            "floor": store.get("floor"),
            "longitude": store.get("longitude"),
            "latitude": store.get("latitude"),
            "store_area": store.get("store_area"),
            "opening_date": store.get("opening_date"),
            "closing_date": store.get("closing_date"),
            "store_status": store.get("store_status"),
            "store_type": store.get("store_type"),
            "is_our_mall": store.get("is_our_mall"),
            "is_main_store": store.get("is_main_store"),
            "data_source": store.get("data_source"),
            "source_url": store.get("source_url"),
        }

        sql = """
        INSERT INTO stores (
            store_id, brand_id, store_name, province, city, district, mall_name,
            address, floor, longitude, latitude, store_area, opening_date,
            closing_date, store_status, store_type, is_our_mall, is_main_store,
            data_source, source_url
        ) VALUES (
            :store_id, :brand_id, :store_name, :province, :city, :district, :mall_name,
            :address, :floor, :longitude, :latitude, :store_area, :opening_date,
            :closing_date, :store_status, :store_type, COALESCE(:is_our_mall, FALSE),
            COALESCE(:is_main_store, FALSE), :data_source, :source_url
        )
        ON CONFLICT (store_id) DO UPDATE SET
            store_name = EXCLUDED.store_name,
            province = EXCLUDED.province,
            city = EXCLUDED.city,
            district = EXCLUDED.district,
            mall_name = EXCLUDED.mall_name,
            address = EXCLUDED.address,
            floor = EXCLUDED.floor,
            longitude = EXCLUDED.longitude,
            latitude = EXCLUDED.latitude,
            store_area = EXCLUDED.store_area,
            opening_date = EXCLUDED.opening_date,
            closing_date = EXCLUDED.closing_date,
            store_status = EXCLUDED.store_status,
            store_type = EXCLUDED.store_type,
            is_our_mall = EXCLUDED.is_our_mall,
            is_main_store = EXCLUDED.is_main_store,
            data_source = EXCLUDED.data_source,
            source_url = EXCLUDED.source_url,
            updated_at = CURRENT_TIMESTAMP
        """
        try:
            with self.client.engine.connect() as conn:
                conn.execute(text(sql), store)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存门店 {store.get('store_id')} 失败: {e}")
            return False

    def batch_upsert_stores(self, stores: List[Dict]) -> int:
        """批量保存门店"""
        success_count = 0
        for store in stores:
            if self.upsert_store(store):
                success_count += 1
        logger.info(f"批量保存门店完成: {success_count}/{len(stores)}")
        return success_count


class RelationshipRepository:
    """品牌关系数据仓储"""

    def __init__(self):
        self.client = PostgresClient()

    def list_relationships(
        self,
        relation_type: Optional[str] = None,
    ) -> List[Dict]:
        """查询品牌关系列表"""
        sql = "SELECT * FROM brand_relationships WHERE 1=1"
        params = {}
        if relation_type:
            sql += " AND relation_type = :relation_type"
            params["relation_type"] = relation_type
        sql += " ORDER BY brand_id, related_brand_id"

        with self.client.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.mappings().all()
            return [dict(row) for row in rows]

    def upsert_relationship(self, relation: Dict) -> bool:
        """插入或更新品牌关系"""
        sql = """
        INSERT INTO brand_relationships (
            relation_id, brand_id, related_brand_id, relation_type,
            confidence_score, description, data_source
        ) VALUES (
            :relation_id, :brand_id, :related_brand_id, :relation_type,
            :confidence_score, :description, :data_source
        )
        ON CONFLICT (relation_id) DO UPDATE SET
            relation_type = EXCLUDED.relation_type,
            confidence_score = EXCLUDED.confidence_score,
            description = EXCLUDED.description,
            data_source = EXCLUDED.data_source,
            created_at = CURRENT_TIMESTAMP
        """
        try:
            with self.client.engine.connect() as conn:
                conn.execute(text(sql), relation)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存关系 {relation.get('relation_id')} 失败: {e}")
            return False


class MetricsRepository:
    """品牌指标数据仓储"""

    def __init__(self):
        self.client = PostgresClient()

    def list_metrics(
        self,
        brand_id: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> List[Dict]:
        """查询指标列表"""
        sql = "SELECT * FROM brand_metrics WHERE 1=1"
        params = {}
        if brand_id:
            sql += " AND brand_id = :brand_id"
            params["brand_id"] = brand_id
        if platform:
            sql += " AND platform = :platform"
            params["platform"] = platform
        sql += " ORDER BY metric_date DESC, brand_id"

        with self.client.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.mappings().all()
            return [dict(row) for row in rows]

    def upsert_metric(self, metric: Dict) -> bool:
        """插入或更新品牌指标"""
        sql = """
        INSERT INTO brand_metrics (
            metric_id, brand_id, metric_date, platform,
            overall_score, review_count, avg_price, city_count,
            data_source
        ) VALUES (
            :metric_id, :brand_id, :metric_date, :platform,
            :overall_score, :review_count, :avg_price, :city_count,
            :data_source
        )
        ON CONFLICT (metric_id) DO UPDATE SET
            metric_date = EXCLUDED.metric_date,
            platform = EXCLUDED.platform,
            overall_score = EXCLUDED.overall_score,
            review_count = EXCLUDED.review_count,
            avg_price = EXCLUDED.avg_price,
            city_count = EXCLUDED.city_count,
            data_source = EXCLUDED.data_source,
            created_at = CURRENT_TIMESTAMP
        """
        try:
            with self.client.engine.connect() as conn:
                conn.execute(text(sql), metric)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"保存指标 {metric.get('metric_id')} 失败: {e}")
            return False
