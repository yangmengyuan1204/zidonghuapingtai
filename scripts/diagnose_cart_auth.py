import json
import requests


BASE_URL = "https://jpapi.rakumart.cn"
ACCOUNT = "12345678990"
PASSWORD = "123456"
CLIENT_TOOL = "2"
KEYWORD = "鞋子"


def form_files(data):
    return {key: (None, "" if value is None else str(value)) for key, value in data.items()}


def pick_stock(detail_payload):
    inventory = ((detail_payload.get("data") or {}).get("goodsInfo") or {}).get("goodsInventory") or []
    for item in inventory:
        if not isinstance(item, dict):
            continue
        values = item.get("valueC") or item.get("valueT") or []
        for value in values:
            if not isinstance(value, dict):
                continue
            try:
                amount = int(value.get("amountOnSale") or 0)
            except (TypeError, ValueError):
                amount = 0
            if amount > 0:
                return value, item
    return {}, {}


def detail_specs(detail_payload, stock_parent):
    specs = ((detail_payload.get("data") or {}).get("goodsInfo") or {}).get("specification") or []
    stock_text = f"{stock_parent.get('keyC', '')} {stock_parent.get('keyT', '')}" if isinstance(stock_parent, dict) else ""
    picked = []
    for item in specs[:2]:
        if not isinstance(item, dict):
            continue
        values = item.get("valueC") or item.get("valueT") or []
        selected = values[0] if isinstance(values, list) and values else {}
        for candidate in values if isinstance(values, list) else []:
            if isinstance(candidate, dict) and str(candidate.get("name") or "") in stock_text:
                selected = candidate
                break
        picked.append(
            {
                "key": item.get("keyC") or item.get("keyT") or "",
                "value": selected.get("name") if isinstance(selected, dict) else "",
            }
        )
    return json.dumps(picked, ensure_ascii=False)


def build_cart_payload(detail_payload):
    data = detail_payload.get("data") or {}
    goods_info = data.get("goodsInfo") or {}
    stock, stock_parent = pick_stock(detail_payload)
    price_ranges = goods_info.get("priceRanges") or []
    first_price = price_ranges[0] if isinstance(price_ranges, list) and price_ranges else {}
    images = data.get("images") or []
    price = stock.get("price") or first_price.get("priceMin") or first_price.get("priceMax") or "0"
    return {
        "to_cart[0][goods_id]": data.get("goodsId") or "",
        "to_cart[0][goods_title]": data.get("titleC") or data.get("titleT") or "",
        "to_cart[0][price]": price,
        "to_cart[0][num]": 1,
        "to_cart[0][pic]": images[0] if isinstance(images, list) and images else "",
        "to_cart[0][detail]": detail_specs(detail_payload, stock_parent),
        "to_cart[0][sku_id]": stock.get("skuId") or "",
        "to_cart[0][spec_id]": stock.get("specId") or "",
        "to_cart[0][shop_id]": data.get("shopId") or "",
        "to_cart[0][shop_name]": data.get("shopName") or "",
        "to_cart[0][from_platform]": data.get("fromPlatform") or "",
        "to_cart[0][price_ranges]": json.dumps(price_ranges, ensure_ascii=False),
    }


def main():
    session = requests.Session()
    login_resp = session.post(
        f"{BASE_URL}/mobile/userLogin",
        files=form_files({"account": ACCOUNT, "password": PASSWORD, "client_tool": CLIENT_TOOL}),
        timeout=20,
    )
    login_payload = login_resp.json()
    token = ((login_payload.get("data") or {}).get("userToken")) or ""
    print("login:", login_resp.status_code, login_payload.get("success"), login_payload.get("code"), "token_len=", len(token))

    search_resp = session.post(
        f"{BASE_URL}/mobile/searchGoods",
        files=form_files({"keywords": KEYWORD, "shop_type": "1688", "page": 1, "pageSize": 20}),
        timeout=20,
    )
    search_payload = search_resp.json()
    items = (((search_payload.get("data") or {}).get("result") or {}).get("result")) or []
    if not items:
        raise RuntimeError("search returned no items")
    detail_payload = {}
    selected_goods_id = None
    selected_shop_type = None
    for goods in items:
        goods_id = goods.get("goodsId")
        goods_shop_type = goods.get("shopType") or "1688"
        detail_resp = session.post(
            f"{BASE_URL}/mobile/goodsParticulars",
            files=form_files({"shop_type": goods_shop_type, "goods_id": goods_id}),
            timeout=20,
        )
        payload = detail_resp.json()
        if payload.get("success") is True:
            detail_payload = payload
            selected_goods_id = goods_id
            selected_shop_type = goods_shop_type
            print("search:", search_resp.status_code, search_payload.get("success"), "goods_id=", goods_id, "shop_type=", goods_shop_type)
            print("detail:", detail_resp.status_code, payload.get("success"), payload.get("code"))
            break
    if not detail_payload:
        print("detail: no successful item found")
        return

    cart_payload = build_cart_payload(detail_payload)
    user_info = (login_payload.get("data") or {}).get("userInfo") or {}
    token_id = user_info.get("token_id")
    operation_id = user_info.get("operation_id")
    y_id = user_info.get("y_id")
    variants = [
        ("none", {}, {}),
        ("authorization_bearer", {"Authorization": f"Bearer {token}"}, {}),
        ("authorization_raw", {"Authorization": token}, {}),
        ("userToken_header", {"userToken": token}, {}),
        ("usertoken_header", {"usertoken": token}, {}),
        ("token_header", {"token": token}, {}),
        ("all_headers", {"Authorization": f"Bearer {token}", "userToken": token, "UserToken": token, "User-Token": token, "token": token}, {}),
        ("token_in_body", {}, {"token": token}),
        ("userToken_in_body", {}, {"userToken": token}),
        ("token_and_headers", {"userToken": token, "token": token}, {"token": token, "userToken": token}),
        (
            "header_with_identity",
            {
                "Authorization": f"Bearer {token}",
                "userToken": token,
                "client_tool": CLIENT_TOOL,
                "token_id": str(token_id or ""),
                "operation_id": str(operation_id or ""),
                "y_id": str(y_id or ""),
            },
            {},
        ),
        (
            "body_with_identity",
            {},
            {
                "userToken": token,
                "token_id": str(token_id or ""),
                "operation_id": str(operation_id or ""),
                "y_id": str(y_id or ""),
                "client_tool": CLIENT_TOOL,
            },
        ),
        (
            "query_with_token",
            {"Authorization": f"Bearer {token}"},
            {},
        ),
    ]

    for name, headers, extra_form in variants:
        params = {}
        if name == "query_with_token":
            params = {"userToken": token, "token": token, "operation_id": operation_id or "", "token_id": token_id or ""}
        response = session.post(
            f"{BASE_URL}/mobile/cart.goodsToCart",
            files=form_files({**cart_payload, **extra_form}),
            headers=headers,
            params=params,
            timeout=20,
        )
        payload = response.json()
        print(
            name,
            "=>",
            response.status_code,
            payload.get("success"),
            payload.get("code"),
            payload.get("msg"),
        )


if __name__ == "__main__":
    main()
