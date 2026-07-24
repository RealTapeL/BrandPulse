"""生成分类字典表(category_dict)的种子数据SQL

依据: docs/品牌分类体系.drawio
层级: level=1 业态, level=2 品类, level=3 细分
"""

categories = [
    # 零售业态
    ("RETAIL", "零售业态", "", "", 1, "购物中心零售业态"),
    ("RETAIL_FASHION", "零售业态", "服装鞋帽", "", 2, "服装鞋帽品类"),
    ("RETAIL_FASHION_FAST", "零售业态", "服装鞋帽", "快时尚", 3, "优衣库 / ZARA / H&M / MUJI"),
    ("RETAIL_FASHION_SPORT", "零售业态", "服装鞋帽", "运动休闲", 3, "Nike / Adidas / 李宁 / 安踏"),
    ("RETAIL_FASHION_LUXURY", "零售业态", "服装鞋帽", "国际精品", 3, "LV / Gucci / Hermès"),
    ("RETAIL_FASHION_PRELUX", "零售业态", "服装鞋帽", "轻奢", 3, "Coach / MK / Tory Burch"),
    ("RETAIL_FASHION_WOMEN", "零售业态", "服装鞋帽", "女装", 3, "ONLY / VERO MODA / 歌莉娅"),
    ("RETAIL_FASHION_MEN", "零售业态", "服装鞋帽", "男装", 3, "海澜之家 / 太平鸟 / GXG"),
    ("RETAIL_FASHION_KIDS", "零售业态", "服装鞋帽", "童装", 3, "巴拉巴拉 / 安踏儿童"),
    ("RETAIL_FASHION_LINGERIE", "零售业态", "服装鞋帽", "内衣/家居服", 3, "曼妮芬 / 蕉内 / ubras"),
    ("RETAIL_JEWELRY", "零售业态", "珠宝配饰", "", 2, "珠宝配饰品类"),
    ("RETAIL_JEWELRY_GOLD", "零售业态", "珠宝配饰", "黄金珠宝", 3, "周大福 / 周生生 / 老凤祥"),
    ("RETAIL_JEWELRY_FASHION", "零售业态", "珠宝配饰", "时尚饰品", 3, "施华洛世奇 / 潘多拉 / APM"),
    ("RETAIL_JEWELRY_WATCH", "零售业态", "珠宝配饰", "眼镜/手表", 3, "JINS / 宝岛 / LOHO"),
    ("RETAIL_BEAUTY", "零售业态", "美妆护肤", "", 2, "美妆护肤品类"),
    ("RETAIL_BEAUTY_HIGH", "零售业态", "美妆护肤", "高端护肤", 3, "Chanel / Dior / SK-II"),
    ("RETAIL_BEAUTY_MASS", "零售业态", "美妆护肤", "大众护肤", 3, "欧莱雅 / 玉兰油 / 珀莱雅"),
    ("RETAIL_BEAUTY_MAKEUP", "零售业态", "美妆护肤", "彩妆香氛", 3, "MAC / 完美日记 / 花西子"),
    ("RETAIL_BEAUTY_COLLECTION", "零售业态", "美妆护肤", "美妆集合店", 3, "丝芙兰 / 屈臣氏 / 妍丽"),
    ("RETAIL_DIGITAL", "零售业态", "数码电子", "", 2, "数码电子品类"),
    ("RETAIL_DIGITAL_PHONE", "零售业态", "数码电子", "手机数码", 3, "Apple / 华为 / 小米"),
    ("RETAIL_DIGITAL_APPLIANCE", "零售业态", "数码电子", "家电生活电器", 3, "戴森 / 索尼 / 松下"),
    ("RETAIL_DIGITAL_WEARABLE", "零售业态", "数码电子", "智能穿戴", 3, "华为 / 小米 / Apple Watch"),
    ("RETAIL_HOME", "零售业态", "生活家居", "", 2, "生活家居品类"),
    ("RETAIL_HOME_FURNITURE", "零售业态", "生活家居", "家具家居", 3, "宜家 / 无印良品 / NITORI"),
    ("RETAIL_HOME_DAILY", "零售业态", "生活家居", "日用百货", 3, "名创优品 / KKV / NOME"),
    ("RETAIL_HOME_TEXTILE", "零售业态", "生活家居", "家纺用品", 3, "罗莱 / 富安娜 / 水星"),
    ("RETAIL_SUPERMARKET", "零售业态", "超市/便利店", "", 2, "超市/便利店品类"),
    ("RETAIL_SUPERMARKET_PREMIUM", "零售业态", "超市/便利店", "精品超市", 3, "Ole' / City Super / G-Super"),
    ("RETAIL_SUPERMARKET_GENERAL", "零售业态", "超市/便利店", "综合超市", 3, "永辉 / 大润发 / 沃尔玛"),
    ("RETAIL_SUPERMARKET_CONVENIENCE", "零售业态", "超市/便利店", "便利店", 3, "7-11 / 全家 / 罗森"),

    # 餐饮业态
    ("FB", "餐饮业态", "", "", 1, "购物中心餐饮业态"),
    ("FB_DINING", "餐饮业态", "正餐", "", 2, "正餐品类"),
    ("FB_DINING_CHINESE", "餐饮业态", "正餐", "中式正餐", 3, "海底捞 / 西贝 / 外婆家"),
    ("FB_DINING_WESTERN", "餐饮业态", "正餐", "西式正餐", 3, "必胜客 / 西提 / 蓝蛙"),
    ("FB_DINING_JAPANKOREA", "餐饮业态", "正餐", "日韩式", 3, "太二 / 九锅一堂 / 姜虎东"),
    ("FB_DINING_HOTPOT", "餐饮业态", "正餐", "火锅", 3, "海底捞 / 小龙坎 / 呷哺呷哺"),
    ("FB_DINING_BBQ", "餐饮业态", "正餐", "烧烤/地方特色", 3, "很久以前 / 南京大牌档"),
    ("FB_FASTFOOD", "餐饮业态", "快餐/轻食", "", 2, "快餐/轻食品类"),
    ("FB_FASTFOOD_CHINESE", "餐饮业态", "快餐/轻食", "中式快餐", 3, "老乡鸡 / 真功夫 / 大米先生"),
    ("FB_FASTFOOD_WESTERN", "餐饮业态", "快餐/轻食", "西式快餐", 3, "肯德基 / 麦当劳 / 汉堡王"),
    ("FB_FASTFOOD_LIGHT", "餐饮业态", "快餐/轻食", "轻食/健康餐", 3, "Wagas / Gaga / 超级碗"),
    ("FB_LEISURE", "餐饮业态", "休闲餐饮", "", 2, "休闲餐饮品类"),
    ("FB_CAFE", "餐饮业态", "休闲餐饮", "咖啡", 3, "星巴克 / 瑞幸 / Manner"),
    ("FB_TEA", "餐饮业态", "休闲餐饮", "茶饮", 3, "喜茶 / 奈雪 / 茶百道"),
    ("FB_BAKERY", "餐饮业态", "休闲餐饮", "烘焙甜品", 3, "面包新语 / 好利来 / 哈根达斯"),
    ("FB_FOODCOURT", "餐饮业态", "美食广场", "", 2, "美食广场品类"),
    ("FB_FOODCOURT_FOODCOURT", "餐饮业态", "美食广场", "美食广场", 3, "大食代 / 食通天 / 档口集合"),

    # 儿童业态
    ("KIDS", "儿童业态", "", "", 1, "购物中心儿童业态"),
    ("KIDS_RETAIL", "儿童业态", "儿童零售", "", 2, "儿童零售品类"),
    ("KIDS_RETAIL_APPAREL", "儿童业态", "儿童零售", "童装童鞋", 3, "巴拉巴拉 / 安奈儿"),
    ("KIDS_RETAIL_TOYS", "儿童业态", "儿童零售", "玩具用品", 3, "孩子王 / 玩具反斗城"),
    ("KIDS_ENTERTAINMENT", "儿童业态", "儿童娱乐", "", 2, "儿童娱乐品类"),
    ("KIDS_ENTERTAINMENT_PLAY", "儿童业态", "儿童娱乐", "游乐园", 3, "Meland / 卡通尼 / 乐高中心"),
    ("KIDS_EDUCATION", "儿童业态", "儿童教育", "", 2, "儿童教育品类"),
    ("KIDS_EDUCATION_TRAINING", "儿童业态", "儿童教育", "早教/培训", 3, "金宝贝 / 美吉姆 / 新东方"),

    # 休闲娱乐
    ("ENT", "休闲娱乐", "", "", 1, "购物中心休闲娱乐业态"),
    ("ENT_CINEMA", "休闲娱乐", "影院剧院", "", 2, "影院剧院品类"),
    ("ENT_CINEMA_MOVIE", "休闲娱乐", "影院剧院", "影院", 3, "万达影城 / CGV / 百老汇"),
    ("ENT_NIGHTLIFE", "休闲娱乐", "夜生活娱乐", "", 2, "夜生活娱乐品类"),
    ("ENT_NIGHTLIFE_KTV", "休闲娱乐", "夜生活娱乐", "KTV/酒吧/Livehouse", 3, "纯K / 星聚会 / Helens"),
    ("ENT_SPORTS", "休闲娱乐", "游艺健身", "", 2, "游艺健身品类"),
    ("ENT_SPORTS_GAME", "休闲娱乐", "游艺健身", "电玩游艺", 3, "大玩家 / 风云再起"),
    ("ENT_SPORTS_FITNESS", "休闲娱乐", "游艺健身", "健身运动", 3, "威尔仕 / 乐刻 / 超级猩猩"),
    ("ENT_SPORTS_ICE", "休闲娱乐", "游艺健身", "冰雪运动", 3, "全明星 / 世纪星"),
    ("ENT_CULTURE", "休闲娱乐", "文创空间", "", 2, "文创空间品类"),
    ("ENT_CULTURE_BOOKSTORE", "休闲娱乐", "文创空间", "书店/文创", 3, "西西弗 / 言几又 / 诚品"),

    # 生活服务
    ("SVC", "生活服务", "", "", 1, "购物中心生活服务业态"),
    ("SVC_BEAUTY", "生活服务", "美业健康", "", 2, "美业健康品类"),
    ("SVC_BEAUTY_HAIR", "生活服务", "美业健康", "美容美发", 3, "丝域 / TONI&GUY"),
    ("SVC_BEAUTY_NAIL", "生活服务", "美业健康", "美甲/SPA", 3, "美甲/SPA"),
    ("SVC_MEDICAL", "生活服务", "医疗健康", "", 2, "医疗健康品类"),
    ("SVC_MEDICAL_PHARMACY", "生活服务", "医疗健康", "药店", 3, "海王星辰 / 老百姓"),
    ("SVC_MEDICAL_CLINIC", "生活服务", "医疗健康", "诊所/口腔/体检", 3, "诊所/口腔/体检"),
    ("SVC_CONVENIENCE", "生活服务", "便民服务", "", 2, "便民服务业品类"),
    ("SVC_CONVENIENCE_FINANCE", "生活服务", "便民服务", "金融服务", 3, "银行 / 证券网点"),
    ("SVC_CONVENIENCE_LIFE", "生活服务", "便民服务", "生活服务", 3, "洗衣 / 宠物 / 照相"),
    ("SVC_EDUCATION", "生活服务", "成人教育", "", 2, "成人教育品类"),
    ("SVC_EDUCATION_TRAINING", "生活服务", "成人教育", "培训教育", 3, "语言 / 考证 / 兴趣"),

    # 体验业态
    ("EXP", "体验业态", "", "", 1, "购物中心体验业态"),
    ("EXP_AUTOMOTIVE", "体验业态", "新能源汽车", "", 2, "新能源汽车品类"),
    ("EXP_AUTOMOTIVE_SHOWROOM", "体验业态", "新能源汽车", "汽车展厅", 3, "特斯拉 / 蔚来 / 理想 / 小鹏"),
    ("EXP_IMMERSIVE", "体验业态", "沉浸式娱乐", "", 2, "沉浸式娱乐品类"),
    ("EXP_IMMERSIVE_GAME", "体验业态", "沉浸式娱乐", "剧本杀/密室/VR/沉浸展", 3, "剧本杀 / 密室 / VR体验 / 沉浸展"),
    ("EXP_CULTURE", "体验业态", "文化艺术", "", 2, "文化艺术品类"),
    ("EXP_CULTURE_ART", "体验业态", "文化艺术", "艺术空间/展览/快闪/文创市集", 3, "艺术空间 / 展览 / 快闪 / 文创市集"),
]


def sql_str(value: str) -> str:
    if not value:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def generate_sql():
    lines = ["-- 分类字典表种子数据（自动生成）\n"]
    lines.append("INSERT INTO category_dict (category_id, category_l1, category_l2, category_l3, level, description) VALUES")
    values = []
    for cat in categories:
        cid, l1, l2, l3, level, desc = cat
        l2_sql = sql_str(l2)
        l3_sql = sql_str(l3)
        desc_sql = sql_str(desc)
        values.append(f"    ('{cid}', '{l1}', {l2_sql}, {l3_sql}, {level}, {desc_sql})")
    lines.append(",\n".join(values) + "\n")
    lines.append("ON CONFLICT (category_id) DO NOTHING;\n")
    return "\n".join(lines)


if __name__ == "__main__":
    sql = generate_sql()
    with open("scripts/seed_categories.sql", "w", encoding="utf-8") as f:
        f.write(sql)
    print("已生成 scripts/seed_categories.sql")
