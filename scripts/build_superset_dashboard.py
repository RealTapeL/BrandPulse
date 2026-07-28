"""
通过 Superset API 自动构建 BrandPulse 招商品牌情报看板（按当前真实数据重建）。

内容：
1. 数据源：BrandPulse PostgreSQL
2. 数据集：brand_heat_daily / dp_shop_metrics / xhs_notes
3. 图表：平台热度汇总、门店评分对比、大众点评门店明细、小红书笔记明细
4. Dashboard：招商品牌情报看板（热度 / 点评 / 小红书）

注意：每次运行会先删除同名旧看板和全部旧图表再重建。
stores / brand_distribution 目前无数据，跑高德门店采集后可再加回地图图表。

运行前提：
- Superset 已在本机运行（http://192.168.0.109:8088）
- 已执行 superset db upgrade / superset fab create-admin / superset init
"""
import json
import re
import sys

import requests

BASE = "http://127.0.0.1:8088"
USERNAME = "admin"
PASSWORD = "admin123"
DATABASE_NAME = "BrandPulse PostgreSQL"
SQLALCHEMY_URI = "postgresql://brandpulse:brandpulse123@localhost:5432/brandpulse"

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


def api_delete(path):
    r = s.delete(f"{BASE}/api/v1{path}", headers=HEADERS)
    if r.status_code not in (200, 202):
        print(f"  !! DELETE {path} -> {r.status_code}: {r.text[:200]}")


def api_get(path, params=None):
    r = s.get(f"{BASE}/api/v1{path}", headers=HEADERS, params=params or {})
    if r.status_code != 200:
        print(f"  !! GET {path} -> {r.status_code}: {r.text[:400]}")
        return None
    return r.json().get("result")


def ensure_database():
    """创建 PostgreSQL 数据源（已存在则复用）"""
    results = api_get("/database/", params={"q": json.dumps({"filters": [{"col": "database_name", "opr": "eq", "value": DATABASE_NAME}]})})
    if results:
        db_id = results[0]["id"]
        print(f"  database {DATABASE_NAME}: 已存在 id={db_id}")
        return db_id
    db_id = api_post("/database/", {
        "database_name": DATABASE_NAME,
        "sqlalchemy_uri": SQLALCHEMY_URI,
        "expose_in_sqllab": True,
    })
    print(f"  database {DATABASE_NAME}: 新建 id={db_id}")
    return db_id


def ensure_dataset(table_name, db_id):
    """创建数据集（已存在则复用）"""
    results = api_get("/dataset/", params={"q": json.dumps({"filters": [{"col": "table_name", "opr": "eq", "value": table_name}]})})
    if results:
        ds_id = results[0]["id"]
        print(f"  dataset {table_name}: 已存在 id={ds_id}")
        return ds_id
    ds_id = api_post("/dataset/", {"database": db_id, "schema": "public", "table_name": table_name})
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
    results = api_get("/chart/", params={"q": json.dumps({"filters": [{"col": "slice_name", "opr": "eq", "value": name}]})})
    if results:
        cid = results[0]["id"]
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
    print("== 0. 数据源 ==")
    db_id = ensure_database()
    if not db_id:
        sys.exit("数据源创建失败")

    print("== 1. 数据集 ==")
    ds_heat = ensure_dataset("brand_heat_daily", db_id)
    ds_dp = ensure_dataset("dp_shop_metrics", db_id)
    ds_xhs = ensure_dataset("xhs_notes", db_id)
    if not all([ds_heat, ds_dp, ds_xhs]):
        sys.exit("数据集创建失败")

    print("== 2. 图表 ==")
    # 清理旧图表与旧看板，按当前真实数据重建
    for dash in (api_get("/dashboard/", params={"q": json.dumps({"filters": [{"col": "dashboard_title", "opr": "eq", "value": "招商品牌情报看板"}]})}) or []):
        api_delete(f"/dashboard/{dash['id']}")
        print(f"  删除旧 dashboard id={dash['id']}")
    old_charts = api_get("/chart/", params={"q": json.dumps({"columns": ["id", "slice_name"], "page_size": 100})}) or []
    for ch in old_charts:
        api_delete(f"/chart/{ch['id']}")
    if old_charts:
        print(f"  删除旧图表 {len(old_charts)} 张")

    # 图1：大众点评门店明细（原始记录表）
    c1 = create_chart(
        "大众点评门店明细（评分 / 评价数 / 人均）",
        ds_dp,
        "table",
        {
            "query_mode": "raw",
            "all_columns": ["shop_name", "place", "score", "review_count", "avg_price", "business_area", "crawl_date"],
            "row_limit": 1000,
            "time_range": "No filter",
        },
    )

    # 图2：小红书笔记明细（原始记录表）
    c2 = create_chart(
        "小红书笔记明细（标题 / 作者 / 点赞）",
        ds_xhs,
        "table",
        {
            "query_mode": "raw",
            "all_columns": ["title", "author_name", "likes", "mall_name", "keyword", "publish_time", "crawl_date"],
            "row_limit": 1000,
            "time_range": "No filter",
        },
    )

    # 图3：平台热度汇总（brand_heat_daily 按平台聚合）
    c3 = create_chart(
        "平台热度汇总（提及量 / 点赞 / 点评评价数）",
        ds_heat,
        "echarts_timeseries_bar",
        {
            "x_axis": "platform",
            "metrics": [
                simple_metric("mentions", "SUM", "提及量"),
                simple_metric("total_likes", "SUM", "点赞总量"),
                simple_metric("dp_review_count", "SUM", "点评评价数"),
                simple_metric("dp_shop_count", "SUM", "点评门店数"),
            ],
            "groupby": [],
            "row_limit": 100,
            "show_legend": True,
            "rich_tooltip": True,
            "time_range": "No filter",
        },
    )

    # 图4：门店评分对比（点评）
    c4 = create_chart(
        "门店评分对比（评分 / 人均）",
        ds_dp,
        "echarts_timeseries_bar",
        {
            "x_axis": "shop_name",
            "metrics": [
                simple_metric("score", "AVG", "评分", "DECIMAL(4,2)"),
                simple_metric("avg_price", "AVG", "人均", "DECIMAL(10,2)"),
            ],
            "groupby": [],
            "row_limit": 100,
            "show_legend": True,
            "rich_tooltip": True,
            "time_range": "No filter",
        },
    )

    charts = [c for c in [c3, c4, c1, c2] if c]
    print(f"  图表共 {len(charts)} 张: {charts}")

    print("== 3. Dashboard ==")
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["HEADER_ID", "ROW-1", "ROW-2", "ROW-3"], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": "招商品牌情报看板（热度 / 点评 / 小红书）"}, "parents": ["ROOT_ID", "GRID_ID"]},
        "ROW-1": {"type": "ROW", "id": "ROW-1", "children": [f"CHART-{charts[0]}", f"CHART-{charts[1]}"], "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}},
        "ROW-2": {"type": "ROW", "id": "ROW-2", "children": [f"CHART-{charts[2]}"], "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}},
        "ROW-3": {"type": "ROW", "id": "ROW-3", "children": [f"CHART-{charts[3]}"], "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}},
        "DASHBOARD_NATIVE_FILTERS_SET": [],
    }
    for i, cid in enumerate(charts):
        row = "ROW-1" if i < 2 else ("ROW-2" if i < 3 else "ROW-3")
        width = 6 if i < 2 else 12
        layout[f"CHART-{cid}"] = {
            "type": "CHART", "id": f"CHART-{cid}", "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row],
            "meta": {"width": width, "height": 50, "chartId": cid},
        }

    dash_id = api_post("/dashboard/", {
        "dashboard_title": "招商品牌情报看板",
        "slug": "brandpulse-lease-intel",
        "position_json": json.dumps(layout, ensure_ascii=False),
        "published": True,
    })
    print(f"  dashboard 新建 id={dash_id}")

    # Superset REST API 不维护看板-图表关联（dashboard_slices），
    # 需要直接写入元数据库，否则看板显示"没有与此组件关联的图表定义"
    import psycopg2
    conn = psycopg2.connect(
        host="localhost", port=5432, dbname="superset_meta",
        user="brandpulse", password="brandpulse123",
    )
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dashboard_slices WHERE dashboard_id = %s", (dash_id,))
        cur.executemany(
            "INSERT INTO dashboard_slices (dashboard_id, slice_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            [(dash_id, cid) for cid in charts],
        )
    conn.close()
    print(f"  看板-图表关联已写入: {charts}")

    print(f"\n完成: {BASE}/superset/dashboard/{dash_id}/")


if __name__ == "__main__":
    main()
