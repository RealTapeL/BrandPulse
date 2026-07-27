"""
通过 Superset API 自动构建 BrandPulse 招商品牌情报看板。

内容：
1. 数据集：brand_heat_daily / dp_shop_metrics / brand_distribution / stores
2. 图表：品牌热度柱状图、商场×品牌表现表、品牌分布地图、品牌分布明细表
3. Dashboard：招商品牌情报看板（热度/布局/分布）
"""
import json
import re
import sys

import requests

BASE = "http://127.0.0.1:8088"
USERNAME = "admin"
PASSWORD = "admin123"
DB_ID = 1  # BrandPulse 数据源

s = requests.Session()


def login():
    r = s.get(f"{BASE}/login/")
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
    csrf = m.group(1)
    s.post(f"{BASE}/login/", data={"username": USERNAME, "password": PASSWORD, "csrf_token": csrf})
    api_csrf = s.get(f"{BASE}/api/v1/security/csrf_token/").json()["result"]
    return api_csrf


CSRF = login()
HEADERS = {
    "X-CSRFToken": CSRF,
    "Content-Type": "application/json",
    "Referer": f"{BASE}/chart/list/",
}


def api_post(path, payload):
    r = s.post(f"{BASE}/api/v1{path}", headers=HEADERS, json=payload)
    if r.status_code not in (200, 201):
        print(f"  !! POST {path} -> {r.status_code}: {r.text[:400]}")
        return None
    return r.json().get("id") or r.json().get("result", {}).get("id")


def ensure_dataset(table_name):
    """创建数据集（已存在则复用）"""
    r = s.get(f"{BASE}/api/v1/dataset/", params={"q": json.dumps({"filters": [{"col": "table_name", "opr": "eq", "value": table_name}]})})
    results = r.json().get("result", [])
    if results:
        ds_id = results[0]["id"]
        print(f"  dataset {table_name}: 已存在 id={ds_id}")
        return ds_id
    ds_id = api_post("/dataset/", {"database": DB_ID, "schema": "public", "table_name": table_name})
    print(f"  dataset {table_name}: 新建 id={ds_id}")
    return ds_id


def simple_metric(col, agg, label, col_type="INT"):
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": col, "type": col_type},
        "aggregate": agg,
        "label": label,
        "optionName": f"metric_{col}_{agg}",
    }


def create_chart(name, ds_id, viz_type, params):
    # 查重
    r = s.get(f"{BASE}/api/v1/chart/", params={"q": json.dumps({"filters": [{"col": "slice_name", "opr": "eq", "value": name}]})})
    if r.json().get("result"):
        cid = r.json()["result"][0]["id"]
        print(f"  chart {name}: 已存在 id={cid}")
        return cid
    params = dict(params)
    params["datasource"] = f"{ds_id}__table"
    params["viz_type"] = viz_type
    payload = {
        "slice_name": name,
        "viz_type": viz_type,
        "datasource_id": ds_id,
        "datasource_type": "table",
        "params": json.dumps(params, ensure_ascii=False),
        "query_context": json.dumps({"datasource": {"id": ds_id, "type": "table"}, "force": False, "queries": [], "form_data": params, "result_format": "json", "result_type": "full"}, ensure_ascii=False),
    }
    cid = api_post("/chart/", payload)
    print(f"  chart {name}: 新建 id={cid}")
    return cid


def main():
    print("== 1. 数据集 ==")
    ds_heat = ensure_dataset("brand_heat_daily")
    ds_dp = ensure_dataset("dp_shop_metrics")
    ds_dist = ensure_dataset("brand_distribution")
    ds_stores = ensure_dataset("stores")
    if not all([ds_heat, ds_dp, ds_dist, ds_stores]):
        sys.exit("数据集创建失败")

    print("== 2. 图表 ==")
    # 图1：品牌热度（按日期的点赞/评价趋势）
    c1 = create_chart(
        "品牌热度趋势（小红书点赞 / 点评评价数）",
        ds_heat,
        "echarts_timeseries_bar",
        {
            "x_axis": "stat_date",
            "time_grain_sqla": "P1D",
            "time_range": "No filter",
            "metrics": [
                simple_metric("total_likes", "SUM", "小红书点赞总量"),
                simple_metric("dp_review_count", "SUM", "点评评价数"),
            ],
            "groupby": ["brand_id", "city"],
            "row_limit": 1000,
            "show_legend": True,
            "rich_tooltip": True,
        },
    )
    # 图2：商场×品牌表现（点评）
    c2 = create_chart(
        "商场×品牌表现（点评评价数 / 人均）",
        ds_dp,
        "table",
        {
            "query_mode": "aggregate",
            "groupby": ["place", "shop_name"],
            "metrics": [
                simple_metric("review_count", "SUM", "评价数"),
                simple_metric("avg_price", "AVG", "人均", "DECIMAL(10,2)"),
                simple_metric("score", "AVG", "评分", "DECIMAL(4,2)"),
            ],
            "order_by_cols": [],
            "row_limit": 1000,
            "time_range": "No filter",
        },
    )
    # 图3：品牌分布地图
    c3 = create_chart(
        "品牌门店分布地图",
        ds_stores,
        "deck_scatter",
        {
            "spatial": {"lonCol": "longitude", "latCol": "latitude", "type": "latlong"},
            "groupby": ["brand_id"],
            "point_size": {"type": "fix", "value": 300},
            "row_limit": 5000,
            "mapbox_style": "open_street_map",
            "viewport": {"longitude": 115.0, "latitude": 32.0, "zoom": 4, "bearing": 0, "pitch": 0},
            "time_range": "No filter",
            "js_tooltip": ["store_name", "city"],
        },
    )
    # 图4：品牌分布明细
    c4 = create_chart(
        "品牌分布明细（城市×商场门店数）",
        ds_dist,
        "table",
        {
            "query_mode": "raw",
            "all_columns": ["brand_id", "city", "mall_name", "shop_count"],
            "row_limit": 1000,
            "time_range": "No filter",
        },
    )
    charts = [c for c in [c1, c2, c3, c4] if c]
    print(f"  图表共 {len(charts)} 张: {charts}")

    print("== 3. Dashboard ==")
    # 查重
    r = s.get(f"{BASE}/api/v1/dashboard/", params={"q": json.dumps({"filters": [{"col": "dashboard_title", "opr": "eq", "value": "招商品牌情报看板"}]})})
    existing = r.json().get("result", [])
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["HEADER_ID", "ROW-1", "ROW-2"], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": "招商品牌情报看板（热度 / 布局 / 分布）"}, "parents": ["ROOT_ID", "GRID_ID"]},
        "ROW-1": {"type": "ROW", "id": "ROW-1", "children": [f"CHART-{charts[0]}", f"CHART-{charts[1]}"], "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}},
        "ROW-2": {"type": "ROW", "id": "ROW-2", "children": [f"CHART-{charts[2]}", f"CHART-{charts[3]}"], "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}},
        "DASHBOARD_NATIVE_FILTERS_SET": [],
    }
    for i, cid in enumerate(charts):
        row = "ROW-1" if i < 2 else "ROW-2"
        layout[f"CHART-{cid}"] = {
            "type": "CHART", "id": f"CHART-{cid}", "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row],
            "meta": {"width": 6, "height": 50, "chartId": cid},
        }

    if existing:
        dash_id = existing[0]["id"]
        r = s.put(f"{BASE}/api/v1/dashboard/{dash_id}", headers=HEADERS, json={
            "dashboard_title": "招商品牌情报看板",
            "position_json": json.dumps(layout, ensure_ascii=False),
            "published": True,
        })
        print(f"  dashboard 更新 id={dash_id} -> {r.status_code}")
    else:
        dash_id = api_post("/dashboard/", {
            "dashboard_title": "招商品牌情报看板",
            "slug": "brandpulse-lease-intel",
            "position_json": json.dumps(layout, ensure_ascii=False),
            "published": True,
        })
        print(f"  dashboard 新建 id={dash_id}")

    print(f"\n完成: {BASE}/superset/dashboard/{dash_id}/")


if __name__ == "__main__":
    main()
