"""
Mock 高德地图数据采集器
用于在没有 AMAP_KEY 时生成示例门店数据，验证流程
"""
import random
from typing import Dict, List, Optional

from brandpulse.logger.modules.logger import get_logger

logger = get_logger(__name__)

# 示例城市、区域、商场
SAMPLE_CITIES = {
    "北京": {
        "朝阳区": ["朝阳大悦城", "三里屯太古里", "国贸商城"],
        "海淀区": ["五道口购物中心", "西直门凯德MALL"],
        "西城区": ["西单大悦城", "金融街购物中心"],
    },
    "上海": {
        "黄浦区": ["来福士广场", "新天地"],
        "静安区": ["静安大悦城", "恒隆广场"],
        "浦东新区": ["陆家嘴中心", "世纪汇广场"],
    },
    "广州": {
        "天河区": ["天河城", "正佳广场", "太古汇"],
        "越秀区": ["北京路步行街", "中华广场"],
        "海珠区": ["万达广场", "丽影广场"],
    },
}

# 每个城市生成门店数量范围
STORE_COUNT_RANGE = (3, 8)


def _generate_random_location(city: str) -> tuple:
    """生成城市内随机经纬度（粗略）"""
    city_coords = {
        "北京": (116.40, 39.90),
        "上海": (121.47, 31.23),
        "广州": (113.26, 23.13),
    }
    base_lng, base_lat = city_coords.get(city, (116.40, 39.90))
    lng = base_lng + random.uniform(-0.05, 0.05)
    lat = base_lat + random.uniform(-0.05, 0.05)
    return round(lng, 6), round(lat, 6)


def _generate_store(
    brand_id: str,
    brand_name: str,
    city: str,
    district: str,
    mall: str,
    index: int,
) -> Dict:
    """生成单个 Mock 门店"""
    lng, lat = _generate_random_location(city)
    store_id = f"{brand_id}_{city}_{district}_{mall}_{index}".replace(" ", "_")

    return {
        "store_id": store_id,
        "brand_id": brand_id,
        "store_name": f"{brand_name}({mall}店)",
        "province": city,
        "city": city,
        "district": district,
        "mall_name": mall,
        "address": f"{city}{district}{mall}1层",
        "floor": "1F",
        "longitude": lng,
        "latitude": lat,
        "store_area": random.choice([20, 30, 40, 50, 80, 120]),
        "opening_date": f"202{random.randint(0, 4)}-{random.randint(1, 12):02d}-01",
        "store_status": "营业中",
        "store_type": random.choice(["直营", "加盟"]),
        "is_our_mall": False,
        "data_source": "mock",
        "source_url": "",
    }


def collect_brand_stores(
    brand_id: str,
    brand_name: str,
    cities: Optional[List[str]] = None,
    **kwargs,
) -> List[Dict]:
    """
    生成 Mock 门店数据

    Args:
        brand_id: 品牌 ID
        brand_name: 品牌名称
        cities: 城市列表

    Returns:
        Mock 门店列表
    """
    if cities is None:
        cities = list(SAMPLE_CITIES.keys())

    all_stores = []
    for city in cities:
        if city not in SAMPLE_CITIES:
            continue

        districts = SAMPLE_CITIES[city]
        count = random.randint(*STORE_COUNT_RANGE)
        selected_locations = []

        # 随机选择商场
        all_malls = []
        for district, malls in districts.items():
            for mall in malls:
                all_malls.append((district, mall))

        selected = random.sample(
            all_malls,
            min(count, len(all_malls)),
        )

        for idx, (district, mall) in enumerate(selected):
            store = _generate_store(brand_id, brand_name, city, district, mall, idx)
            all_stores.append(store)

    logger.info(f"[Mock] {brand_id} 在 {cities} 生成 {len(all_stores)} 家门店")
    return all_stores
