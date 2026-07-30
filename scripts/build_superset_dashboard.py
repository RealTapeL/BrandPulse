"""
通过 Superset API 自动构建 BrandPulse 招商品牌情报看板（按当前真实数据重建）。

内容：
1. 数据源：BrandPulse PostgreSQL
2. 数据集：brand_heat_daily / dp_shop_metrics / xhs_notes / brand_indicators_daily / stores
3. 图表：KPI 卡片、热度趋势折线、口碑×热度四象限气泡、SOV 饼图、Top 笔记横条、
   品牌×区县透视表、双平台明细
4. Dashboard：招商品牌情报看板

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


def ensure_sql_dataset(name, sql, db_id):
    """创建 SQL 虚拟数据集（如"最新一天"视图，已存在则复用）"""
    results = api_get("/dataset/", params={"q": json.dumps({"filters": [{"col": "table_name", "opr": "eq", "value": name}]})})
    if results:
        ds_id = results[0]["id"]
        print(f"  dataset {name}: 已存在 id={ds_id}")
        return ds_id
    ds_id = api_post("/dataset/", {"database": db_id, "schema": "public", "sql": sql, "table_name": name})
    print(f"  dataset {name}: 新建(SQL) id={ds_id}")
    return ds_id


def simple_metric(col, agg, label, col_type="INT"):
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": col, "type": col_type},
        "aggregate": agg,
        "label": label,
        "optionName": f"metric_{col}_{agg}",
    }


def eq_filter(col, value):
    """SIMPLE adhoc 过滤器（WHERE col = value）"""
    return {
        "expressionType": "SIMPLE",
        "subject": col,
        "operator": "==",
        "comparator": value,
        "clause": "WHERE",
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
    ds_dp = ensure_dataset("dp_shop_metrics", db_id)
    ds_xhs = ensure_dataset("xhs_notes", db_id)
    ds_ind = ensure_dataset("brand_indicators_daily", db_id)
    if not all([ds_dp, ds_xhs, ds_ind]):
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

    # ---- 指标层图表（brand_indicators_daily，只看门店级实体） ----
    shop_only = [eq_filter("entity_type", "shop")]

    # 图5：门店口碑分对比
    c5 = create_chart(
        "门店口碑分对比",
        ds_ind,
        "echarts_timeseries_bar",
        {
            "x_axis": "entity_name",
            "metrics": [simple_metric("weighted_score", "AVG", "口碑分", "DECIMAL(5,3)")],
            "groupby": [],
            "adhoc_filters": shop_only,
            "row_limit": 100,
            "show_legend": True,
            "rich_tooltip": True,
            "time_range": "No filter",
        },
    )

    # 图6：门店热度指数对比（0~100）
    c6 = create_chart(
        "门店热度指数对比（0~100）",
        ds_ind,
        "echarts_timeseries_bar",
        {
            "x_axis": "entity_name",
            "metrics": [simple_metric("heat_index", "AVG", "热度指数", "DECIMAL(6,2)")],
            "groupby": [],
            "adhoc_filters": shop_only,
            "row_limit": 100,
            "show_legend": True,
            "rich_tooltip": True,
            "time_range": "No filter",
        },
    )

    # 图7：SOV 声量份额（饼图）
    c7 = create_chart(
        "SOV 声量份额（评价数占比）",
        ds_ind,
        "pie",
        {
            "groupby": ["entity_name"],
            "metric": simple_metric("sov", "AVG", "SOV", "DECIMAL(6,4)"),
            "adhoc_filters": shop_only,
            "row_limit": 100,
            "show_legend": True,
            "label_type": "key_value_percent",
            "number_format": ".1%",
            "show_labels": True,
            "labels_outside": True,
            "time_range": "No filter",
        },
    )

    # 图9：口碑 × 热度 四象限气泡图（气泡大小 = SOV）
    # 右上=高口碑高热度优质品牌，右下=高热度低口碑网红泡沫
    c9 = create_chart(
        "口碑×热度四象限（气泡=SOV）",
        ds_ind,
        "bubble",
        {
            "series": "entity_name",
            "entity": "entity_name",
            "x": simple_metric("weighted_score", "AVG", "口碑分", "DECIMAL(5,3)"),
            "y": simple_metric("heat_index", "AVG", "热度指数", "DECIMAL(6,2)"),
            "size": simple_metric("sov", "AVG", "SOV", "DECIMAL(6,4)"),
            "adhoc_filters": shop_only,
            "max_bubble_size": "50",
            "x_axis_label": "口碑分",
            "y_axis_label": "热度指数",
            "show_legend": False,
            "time_range": "No filter",
        },
    )

    # 图10：小红书点赞 Top10 笔记（横向条形）
    c10 = create_chart(
        "小红书点赞 Top10 笔记",
        ds_xhs,
        "echarts_timeseries_bar",
        {
            "x_axis": "title",
            "metrics": [simple_metric("likes", "SUM", "点赞数")],
            "groupby": [],
            "orientation": "horizontal",
            "order_desc": True,
            "row_limit": 10,
            "show_legend": False,
            "rich_tooltip": True,
            "time_range": "No filter",
        },
    )

    charts = [c for c in [c9, c4, c5, c6, c7, c10, c1, c2] if c]
    print(f"  图表共 {len(charts)} 张: {charts}")

    print("== 3. Dashboard ==")
    # 布局：顶部说明块（全宽）→ 前 6 张图两两一行（半宽）→ 最后 2 张明细表（全宽）
    def chart_link(cid, text):
        """指标名 -> 高亮链接，点击后页内滑动到对应图表（图表容器 DOM id 即布局里的 CHART-{id}）"""
        return f'<a href="#CHART-{cid}"><mark><b>{text}</b></mark></a>'

    METHODOLOGY_MD = f"""### 指标口径与计算方法

**数据来源**：大众点评（门店评分/评价数/人均）、小红书（笔记/点赞），通过 Kimi WebBridge 驱动真实浏览器按「商场 + 品类」采集（当前范围：苏州中心 · 咖啡），每日更新。

**本看板包含 4 项分析，全部由确定性代码计算（不经过大模型，可复现可审计）。点击高亮指标名可滑动到对应图表**：

<table border="1" cellspacing="0" cellpadding="8" style="border-collapse:collapse; width:100%;">
<tr style="background:#f0f0f0;"><th style="width:14%;">指标</th><th style="width:48%;">计算方法</th><th>解读</th></tr>
<tr><td>{chart_link(c5, "口碑分")}</td><td>贝叶斯加权：WR = (v/(v+m))·R + (m/(v+m))·C；R=门店评分，v=评价数，C=全城加权均分，m=评价数中位数</td><td>评价少的店分数被拉向全城均值，避免"5 条评价的 5 星店"压过"8000 条评价的 4.6 星店"</td></tr>
<tr><td>{chart_link(c6, "热度指数")}</td><td>固定基准对数归一：100·ln(1+v) / ln(1+50000)，v=评价数</td><td>0~100 分；对数压缩避免头部爆款绑架指数，跨天/跨店可比</td></tr>
<tr><td>{chart_link(c7, "SOV 声量份额")}</td><td>门店评价数 ÷ 同商场同品类总评价数</td><td>该店在商场内的声量占比，衡量相对竞争力</td></tr>
<tr><td>{chart_link(c9, "四象限图")}</td><td>X=口碑分，Y=热度指数，气泡大小=SOV</td><td>右上=高口碑高热度（优质），右下=高热度低口碑（网红泡沫风险），左上=口碑好但人气不足（潜力店）</td></tr>
</table>

*计算代码见 `src/backend/brandpulse/indicators/`，公式参数为文件头常量，可用历史数据校准。*
"""
    row_ids = []
    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": "招商品牌情报看板（苏州中心 · 咖啡）"}, "parents": ["ROOT_ID", "GRID_ID"]},
        "MARKDOWN-METHOD": {"type": "MARKDOWN", "id": "MARKDOWN-METHOD", "children": [],
                            "parents": ["ROOT_ID", "GRID_ID", "ROW-MD"],
                            "meta": {"width": 12, "height": 120, "code": METHODOLOGY_MD}},
        "DASHBOARD_NATIVE_FILTERS_SET": [],
    }
    chart_row = {}  # cid -> (row_id, width, height)

    def new_row(children):
        row_id = f"ROW-{len(row_ids) + 1}"
        row_ids.append(row_id)
        layout[row_id] = {"type": "ROW", "id": row_id, "children": [f"CHART-{c}" for c in children],
                          "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        return row_id

    # 第一行：指标口径说明（Markdown 块）
    layout["ROW-MD"] = {"type": "ROW", "id": "ROW-MD", "children": ["MARKDOWN-METHOD"],
                        "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}
    row_ids.append("ROW-MD")

    pairs, tables = charts[:-2], charts[-2:]
    for i in range(0, len(pairs), 2):
        pair = pairs[i:i + 2]
        row_id = new_row(pair)
        for c in pair:
            chart_row[c] = (row_id, 6, 50)
    for c in tables:
        row_id = new_row([c])
        chart_row[c] = (row_id, 12, 50)

    layout["GRID_ID"] = {"type": "GRID", "id": "GRID_ID", "children": ["HEADER_ID"] + row_ids, "parents": ["ROOT_ID"]}
    for cid, (row_id, width, height) in chart_row.items():
        layout[f"CHART-{cid}"] = {
            "type": "CHART", "id": f"CHART-{cid}", "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row_id],
            "meta": {"width": width, "height": height, "chartId": cid},
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
