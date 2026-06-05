from datetime import datetime
import json
import sqlite3


DB_PATH = "auto_test_platform.db"
BASE_URL = "https://jpapi.rakumart.cn"


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def upsert_api_case(cur, project_id, env_id, case_name, method, url, headers, body, assert_rule):
    row = cur.execute("select id from api_case where case_name = ?", (case_name,)).fetchone()
    payload = (
        project_id,
        env_id,
        method,
        url,
        dumps(headers),
        "{}",
        dumps(body),
        dumps(assert_rule),
        "active",
    )
    if row:
        cur.execute(
            """
            update api_case
            set project_id = ?, env_id = ?, method = ?, url = ?, headers = ?, params = ?,
                body = ?, assert_rule = ?, status = ?
            where id = ?
            """,
            (*payload, row[0]),
        )
        return row[0]
    cur.execute(
        """
        insert into api_case
            (project_id, env_id, case_name, method, url, headers, params, body, assert_rule, status, create_time)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (*payload[:2], case_name, *payload[2:], datetime.now()),
    )
    return cur.lastrowid


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    project = cur.execute("select id from project order by id limit 1").fetchone()
    if not project:
        cur.execute("insert into project (name, desc, create_time) values (?, ?, ?)", ("默认项目", "", datetime.now()))
        project_id = cur.lastrowid
    else:
        project_id = project[0]

    env = cur.execute("select id from env where env_name = ?", ("test-登录",)).fetchone()
    if env:
        env_id = env[0]
        cur.execute(
            "update env set project_id = ?, base_url = ?, global_headers = ?, global_vars = ?, timeout = ? where id = ?",
            (project_id, BASE_URL, "{}", dumps({"api": BASE_URL}), 30, env_id),
        )
    else:
        cur.execute(
            "insert into env (project_id, env_name, base_url, global_headers, global_vars, timeout) values (?, ?, ?, ?, ?, ?)",
            (project_id, "test-登录", BASE_URL, "{}", dumps({"api": BASE_URL}), 30),
        )
        env_id = cur.lastrowid

    multipart = {"Content-Type": "multipart/form-data"}
    token_headers = {
        "Content-Type": "multipart/form-data",
        "Authorization": "Bearer {{userToken}}",
        "userToken": "{{userToken}}",
        "ClientToken": "{{userToken}}",
        "gkToken": "{{userToken}}",
        "token": "{{userToken}}",
        "X-Requested-With": "XMLHttpRequest",
        "Lang": "zh-CN",
    }

    upsert_api_case(
        cur,
        project_id,
        env_id,
        "搜索商品",
        "POST",
        "/mobile/searchGoods",
        multipart,
        {"keywords": "{{keyword}}", "shop_type": "{{shop_type}}", "page": "1", "pageSize": "20"},
        {
            "status_code": 200,
            "extract": {
                "goods_id": "json.data.result.result.0.goodsId",
                "goods_shop_type": "json.data.result.result.0.shopType",
                "goods_title": "json.data.result.result.0.titleC",
                "goods_price": "json.data.result.result.0.goodsPrice",
                "goods_pic": "json.data.result.result.0.imgUrl",
            },
        },
    )
    upsert_api_case(
        cur,
        project_id,
        env_id,
        "商品详情",
        "POST",
        "/mobile/goodsParticulars",
        multipart,
        {"shop_type": "{{goods_shop_type}}", "goods_id": "{{goods_id}}"},
        {
            "status_code": 200,
            "extract": {
                "cart_goods_id": "json.data.goodsId",
                "cart_title": "json.data.titleC",
                "cart_price": "json.data.goodsInfo.priceRanges.0.priceMin",
                "cart_pic": "json.data.images.0",
                "cart_sku_id": "json.data.goodsInfo.goodsInventory.0.valueC.0.skuId",
                "cart_spec_id": "json.data.goodsInfo.goodsInventory.0.valueC.0.specId",
                "cart_shop_id": "json.data.shopId",
                "cart_shop_name": "json.data.shopName",
                "cart_from_platform": "json.data.fromPlatform",
            },
        },
    )
    upsert_api_case(
        cur,
        project_id,
        env_id,
        "加入购物车",
        "POST",
        "/mobile/cart.goodsToCart",
        token_headers,
        {
            "to_cart[0][goods_id]": "{{cart_goods_id}}",
            "to_cart[0][goods_title]": "{{cart_title}}",
            "to_cart[0][price]": "{{cart_price}}",
            "to_cart[0][num]": "1",
            "to_cart[0][pic]": "{{cart_pic}}",
            "to_cart[0][detail]": "[]",
            "to_cart[0][sku_id]": "{{cart_sku_id}}",
            "to_cart[0][spec_id]": "{{cart_spec_id}}",
            "to_cart[0][shop_id]": "{{cart_shop_id}}",
            "to_cart[0][shop_name]": "{{cart_shop_name}}",
            "to_cart[0][from_platform]": "{{cart_from_platform}}",
            "to_cart[0][price_ranges]": "[]",
            "userToken": "{{userToken}}",
            "token": "{{userToken}}",
            "ClientToken": "{{userToken}}",
            "token_id": "{{token_id}}",
            "operation_id": "{{operation_id}}",
            "client_tool": "2",
        },
        {"status_code": 200},
    )

    conn.commit()
    print(dumps({"project_id": project_id, "env_id": env_id, "seeded": ["搜索商品", "商品详情", "加入购物车"]}))


if __name__ == "__main__":
    main()
