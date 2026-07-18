# Problem Goods Cross-Node Candidates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Japan-site problem-goods script discover creatable purchase records across order lifecycle nodes without a fixed node whitelist.

**Architecture:** Read `data.order_detail[].order_purchase[]` from `/order.detail` as the canonical candidate source. If it fails or contains no purchases, query both `/purchase.purchaseList` and `/follow.followList`, normalize their rows to the existing candidate contract, and deduplicate by `order_purchase_id`; `/problem.store` remains the final business authority.

**Tech Stack:** Python 3.11, requests, pytest, existing FastAPI data-script runtime

## Global Constraints

- Tests must run with `.venv\Scripts\python.exe`.
- Modify only `app/data_scripts/problem_goods.py` and `tests/test_problem_goods_script.py`.
- Do not modify databases, configuration, frontend behavior, other data scripts, or the problem-goods processing state machine.
- Candidate inspection must remain read-only.
- Preserve the existing candidate response fields and `max_submit_num = max(0, possible_num - storage_num)` rule.
- Preserve unrelated working-tree changes and stage only files from this feature.

---

## File Structure

- `app/data_scripts/problem_goods.py`: owns candidate payload normalization, source querying, fallback, diagnostics, and deduplication.
- `tests/test_problem_goods_script.py`: owns parser and gateway-level regression tests for cross-node candidate discovery.

### Task 1: Normalize order-detail and follow-list candidate payloads

**Files:**
- Modify: `app/data_scripts/problem_goods.py:368-430`
- Test: `tests/test_problem_goods_script.py:200-237`

**Interfaces:**
- Consumes: backend payload dictionaries from `/order.detail`, `/purchase.purchaseList`, and `/follow.followList`.
- Produces: `order_purchase_candidates(order_data: Dict[str, Any]) -> list[Dict[str, Any]]` with the existing candidate fields.

- [ ] **Step 1: Add failing parser tests for order detail, follow list, and unavailable quantity**

Add these tests beside `test_purchase_list_candidates_use_unstored_quantity_and_confirmed_values`:

```python
def test_order_detail_candidates_include_nested_purchases_across_nodes():
    payload = {
        "success": True,
        "data": {
            "order_sn": "2026071816165891-300001",
            "order_detail": [
                {
                    "id": 14052981,
                    "sorting": 1,
                    "confirm_num": 1,
                    "confirm_price": "10.00",
                    "confirm_freight": "2.00",
                    "order_purchase": [
                        {
                            "id": 15328208,
                            "order_detail_id": 14052981,
                            "purchase_no": "20260718161716",
                            "possible_num": 1,
                            "storage_num": 0,
                            "status": 40,
                            "statusName": "核查中",
                        }
                    ],
                }
            ],
        },
    }

    rows = order_purchase_candidates(payload)

    assert rows == [
        {
            "order_purchase_id": 15328208,
            "order_detail_id": 14052981,
            "sorting": 1,
            "purchase_no": "20260718161716",
            "goods_name": None,
            "sku_id": None,
            "purchase_status": 40,
            "possible_num": 1,
            "storage_num": 0,
            "max_submit_num": 1,
            "can_submit": True,
            "price": "10.00",
            "freight": "2.00",
            "confirm_num": 1,
            "confirm_price": "10.00",
            "confirm_freight": "2.00",
            "pre_num": 1,
            "pre_price": "10.00",
            "pre_freight": "2.00",
            "option": [],
        }
    ]


def test_follow_list_candidates_accept_flat_child_fields():
    payload = {
        "success": True,
        "data": {
            "data": [
                {
                    "order_sn": "2026071816165891-300001",
                    "purchase_no": "20260718161716",
                    "list": [
                        {
                            "order_purchase_id": 15328209,
                            "order_detail_id": 14052982,
                            "sorting": 2,
                            "possible_num": 1,
                            "storage_num": 0,
                            "confirm_num": 1,
                            "confirm_price": "11.00",
                            "confirm_freight": "3.00",
                        }
                    ],
                }
            ]
        },
    }

    rows = order_purchase_candidates(payload)

    assert len(rows) == 1
    assert rows[0]["order_purchase_id"] == 15328209
    assert rows[0]["order_detail_id"] == 14052982
    assert rows[0]["sorting"] == 2
    assert rows[0]["purchase_no"] == "20260718161716"
    assert rows[0]["max_submit_num"] == 1


def test_candidates_mark_fully_stored_purchase_unavailable():
    payload = {
        "data": {
            "order_detail": [
                {
                    "id": 14052983,
                    "sorting": 3,
                    "order_purchase": [
                        {
                            "id": 15328210,
                            "order_detail_id": 14052983,
                            "possible_num": 1,
                            "storage_num": 1,
                        }
                    ],
                }
            ]
        }
    }

    rows = order_purchase_candidates(payload)

    assert rows[0]["max_submit_num"] == 0
    assert rows[0]["can_submit"] is False
```

- [ ] **Step 2: Run the parser tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_problem_goods_script.py -v -k "order_detail_candidates or follow_list_candidates or fully_stored_purchase"
```

Expected: the order-detail and follow-list tests fail because the parser does not unwrap `payload["data"]` or accept `list` children and flat fields.

- [ ] **Step 3: Extend the parser with minimal source-shape compatibility**

At the beginning of `order_purchase_candidates`, unwrap a dictionary `data` envelope. Accept `list` and `items` as purchase collections, and copy parent identifiers into each child before normalization:

```python
def order_purchase_candidates(order_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    nested_data = order_data.get("data")
    if isinstance(nested_data, dict):
        order_data = nested_data

    pairs: list[tuple[Dict[str, Any], Dict[str, Any]]] = []
    for order in _nested_list(order_data):
        if not isinstance(order, dict):
            continue
        purchases = (
            order.get("order_purchase")
            or order.get("order_purchases")
            or order.get("list")
            or order.get("items")
            or []
        )
        if isinstance(purchases, dict):
            purchases = [purchases]
        for raw_purchase in purchases if isinstance(purchases, list) else []:
            if not isinstance(raw_purchase, dict):
                continue
            purchase = dict(raw_purchase)
            purchase.setdefault("purchase_no", order.get("purchase_no"))
            purchase.setdefault("order_sn", order.get("order_sn"))
            detail = purchase.get("order_detail") if isinstance(purchase.get("order_detail"), dict) else {}
            pairs.append((detail, purchase))

    details = order_data.get("order_detail") or order_data.get("order_details") or []
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        purchases = detail.get("order_purchase") or detail.get("order_purchases") or []
        if isinstance(purchases, dict):
            purchases = [purchases]
        for raw_purchase in purchases if isinstance(purchases, list) else []:
            if not isinstance(raw_purchase, dict):
                continue
            purchase = dict(raw_purchase)
            purchase.setdefault("order_detail_id", detail.get("id"))
            pairs.append((detail, purchase))

    candidates: list[Dict[str, Any]] = []
    seen: set[int] = set()
    for detail, purchase in pairs:
        purchase_id = int(purchase.get("id") or purchase.get("order_purchase_id") or 0)
        detail_id = int(detail.get("id") or purchase.get("order_detail_id") or 0)
        if not purchase_id or not detail_id or purchase_id in seen:
            continue
        seen.add(purchase_id)
        possible_num = int(purchase.get("possible_num") or 0)
        storage_num = int(purchase.get("storage_num") or 0)
        max_submit_num = max(0, possible_num - storage_num)
        price = purchase.get("price") if purchase.get("price") not in (None, "") else detail.get("confirm_price")
        freight = purchase.get("freight") if purchase.get("freight") not in (None, "") else detail.get("confirm_freight")
        confirm_num = detail.get("confirm_num") if detail.get("confirm_num") not in (None, "") else purchase.get("confirm_num")
        confirm_price = detail.get("confirm_price") if detail.get("confirm_price") not in (None, "") else purchase.get("confirm_price")
        confirm_freight = detail.get("confirm_freight") if detail.get("confirm_freight") not in (None, "") else purchase.get("confirm_freight")
        candidates.append(
            {
                "order_purchase_id": purchase_id,
                "order_detail_id": detail_id,
                "sorting": detail.get("sorting") if detail.get("sorting") not in (None, "") else purchase.get("sorting"),
                "purchase_no": purchase.get("purchase_no"),
                "goods_name": detail.get("goods_name") or detail.get("goods_title") or detail.get("title") or purchase.get("goods_name"),
                "sku_id": detail.get("sku_id") or purchase.get("sku_id"),
                "purchase_status": purchase.get("status"),
                "possible_num": possible_num,
                "storage_num": storage_num,
                "max_submit_num": max_submit_num,
                "can_submit": max_submit_num > 0,
                "price": price if price not in (None, "") else confirm_price,
                "freight": freight if freight not in (None, "") else confirm_freight,
                "confirm_num": confirm_num,
                "confirm_price": confirm_price,
                "confirm_freight": confirm_freight,
                "pre_num": confirm_num if confirm_num not in (None, "") else possible_num,
                "pre_price": confirm_price if confirm_price not in (None, "") else price,
                "pre_freight": confirm_freight if confirm_freight not in (None, "") else freight,
                "option": detail.get("option") or purchase.get("option") or [],
            }
        )
    return candidates
```

- [ ] **Step 4: Run all parser tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_problem_goods_script.py -v -k "candidate"
```

Expected: PASS.

- [ ] **Step 5: Commit the parser compatibility change**

Before staging, run `git status --short` and `git diff --stat`, report the two relevant files and preserve every unrelated change. Then run:

```powershell
git add -- app/data_scripts/problem_goods.py tests/test_problem_goods_script.py
git commit -m "fix: parse problem goods candidates across nodes"
```

### Task 2: Add canonical lookup, read-only fallbacks, and deduplication

**Files:**
- Modify: `app/data_scripts/problem_goods.py:453-577`
- Test: `tests/test_problem_goods_script.py`

**Interfaces:**
- Consumes: `ProblemGoodsGateway._admin_request(...)`, configured API paths, and `order_purchase_candidates(...)` from Task 1.
- Produces: `ProblemGoodsGateway.list_purchase_candidates(order_sn: str) -> list[Dict[str, Any]]`; no caller changes.

- [ ] **Step 1: Add failing gateway tests**

Add a gateway factory and tests:

```python
def _candidate_gateway(monkeypatch, responses):
    gateway = object.__new__(ProblemGoodsGateway)
    gateway.variables = {"customer_id": "300001"}
    gateway.log = {}
    gateway._path = lambda key, default: default

    def request(path, fields, action, mutation):
        response = responses[path]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(gateway, "_admin_request", request)
    return gateway


def _order_detail_payload(purchase_id=15328208, sorting=1):
    return {
        "success": True,
        "data": {
            "order_detail": [
                {
                    "id": 14052980 + sorting,
                    "sorting": sorting,
                    "confirm_num": 1,
                    "order_purchase": [
                        {
                            "id": purchase_id,
                            "order_detail_id": 14052980 + sorting,
                            "possible_num": 1,
                            "storage_num": 0,
                        }
                    ],
                }
            ]
        },
    }


def test_gateway_prefers_order_detail_candidates(monkeypatch):
    gateway = _candidate_gateway(
        monkeypatch,
        {"/order.detail": _order_detail_payload()},
    )

    rows = gateway.list_purchase_candidates("2026071816165891-300001")

    assert [row["order_purchase_id"] for row in rows] == [15328208]
    assert gateway.log["candidate_sources"]["order_detail"]["count"] == 1


def test_gateway_merges_and_deduplicates_fallback_sources(monkeypatch):
    duplicate = _order_detail_payload()["data"]["order_detail"][0]["order_purchase"][0]
    gateway = _candidate_gateway(
        monkeypatch,
        {
            "/order.detail": {"success": True, "data": {"order_detail": []}},
            "/purchase.purchaseList": {
                "success": True,
                "data": {"data": [{"order_purchase": [duplicate]}]},
            },
            "/follow.followList": {
                "success": True,
                "data": {
                    "data": [
                        {
                            "order_sn": "2026071816165891-300001",
                            "list": [
                                {**duplicate, "order_purchase_id": duplicate["id"]},
                                {
                                    "order_purchase_id": 15328209,
                                    "order_detail_id": 14052982,
                                    "sorting": 2,
                                    "possible_num": 1,
                                    "storage_num": 0,
                                },
                            ],
                        }
                    ]
                },
            },
        },
    )

    rows = gateway.list_purchase_candidates("2026071816165891-300001")

    assert [row["order_purchase_id"] for row in rows] == [15328208, 15328209]


def test_gateway_returns_empty_when_one_source_succeeds_empty(monkeypatch):
    error = ProblemGoodsError("temporary failure")
    gateway = _candidate_gateway(
        monkeypatch,
        {
            "/order.detail": {"success": True, "data": {"order_detail": []}},
            "/purchase.purchaseList": error,
            "/follow.followList": error,
        },
    )

    assert gateway.list_purchase_candidates("2026071816165891-300001") == []


def test_gateway_raises_when_all_candidate_sources_fail(monkeypatch):
    error = ProblemGoodsError("temporary failure")
    gateway = _candidate_gateway(
        monkeypatch,
        {
            "/order.detail": error,
            "/purchase.purchaseList": error,
            "/follow.followList": error,
        },
    )

    with pytest.raises(ProblemGoodsError, match="候选采购记录查询失败"):
        gateway.list_purchase_candidates("2026071816165891-300001")
```

- [ ] **Step 2: Run gateway tests and verify they fail**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_problem_goods_script.py -v -k "gateway_"
```

Expected: FAIL because `list_purchase_candidates` only calls `/purchase.purchaseList`.

- [ ] **Step 3: Add a deterministic deduplication helper**

Add immediately after `order_purchase_candidates`:

```python
def merge_purchase_candidates(*groups: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    merged: Dict[int, Dict[str, Any]] = {}
    for group in groups:
        for candidate in group:
            purchase_id = int(candidate.get("order_purchase_id") or 0)
            if not purchase_id:
                continue
            current = merged.get(purchase_id)
            if current is None:
                merged[purchase_id] = dict(candidate)
                continue
            for key, value in candidate.items():
                if current.get(key) in (None, "", []) and value not in (None, "", []):
                    current[key] = value
    return list(merged.values())
```

- [ ] **Step 4: Replace the single-source gateway lookup**

Replace `ProblemGoodsGateway.list_purchase_candidates` with canonical lookup followed by two read-only fallbacks:

```python
    def list_purchase_candidates(self, order_sn: str) -> list[Dict[str, Any]]:
        source_log: Dict[str, Dict[str, Any]] = {}
        successful_sources = 0

        def query(source: str, path_key: str, default_path: str, fields: Dict[str, Any]) -> list[Dict[str, Any]]:
            nonlocal successful_sources
            try:
                payload = self._admin_request(
                    self._path(path_key, default_path),
                    fields,
                    f"查询问题产品候选（{source}）",
                    mutation=False,
                )
                if not _api_success(payload):
                    raise ProblemGoodsApiError(f"查询问题产品候选（{source}）", payload)
                successful_sources += 1
                rows = order_purchase_candidates(payload)
                source_log[source] = {"success": True, "count": len(rows)}
                return rows
            except ProblemGoodsError as exc:
                source_log[source] = {"success": False, "error": str(exc)}
                return []

        order_detail_rows = query(
            "order_detail",
            "admin_order_detail",
            "/order.detail",
            {"order_sn": order_sn},
        )
        if order_detail_rows:
            self.log["candidate_sources"] = source_log
            return order_detail_rows

        purchase_rows = query(
            "purchase_list",
            "admin_purchase_list",
            "/purchase.purchaseList",
            {
                "page": 1,
                "pageSize": 100,
                "status": "全部",
                "dateStart": "",
                "dateEnd": "",
                "user_id": "",
                "order_sn": order_sn,
                "g_id": "",
                "is_urgent": "",
                "overdue": "",
            },
        )
        follow_rows = query(
            "follow_list",
            "admin_follow_list",
            "/follow.followList",
            {
                "page": 1,
                "pageSize": 100,
                "status": "0",
                "dateStart": "",
                "dateEnd": "",
                "user_id": "",
                "order_sn": order_sn,
                "express_no": "",
                "purchase_no": "",
                "order_part": "",
                "realname": "",
            },
        )
        self.log["candidate_sources"] = source_log
        if not successful_sources:
            raise ProblemGoodsError("候选采购记录查询失败")
        return merge_purchase_candidates(purchase_rows, follow_rows)
```

Do not call `/problem.store` during inspection. Existing create execution remains unchanged.

- [ ] **Step 5: Run gateway and parser tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_problem_goods_script.py -v -k "gateway_ or candidate"
```

Expected: PASS.

- [ ] **Step 6: Run the complete problem-goods test module**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_problem_goods_script.py -v
```

Expected: PASS.

- [ ] **Step 7: Perform read-only acceptance verification for the reported order**

Use `.venv\Scripts\python.exe` to load environment ID 1, merge project variables with `data_script_variables`, and call `inspect_problem_goods` for `2026071816165891-300001`. Print only candidate IDs and quantities; do not print credentials or raw configuration.

Expected:

```text
candidate_ids=[15328208, 15328209, 15328210, 15328211]
max_submit_nums=[1, 1, 1, 1]
```

- [ ] **Step 8: Verify scope and commit**

Run:

```powershell
git status --short
git diff --stat -- app/data_scripts/problem_goods.py tests/test_problem_goods_script.py
git diff --check -- app/data_scripts/problem_goods.py tests/test_problem_goods_script.py
```

Report that only these two files belong to the implementation and that all other working-tree changes remain untouched. Then run:

```powershell
git add -- app/data_scripts/problem_goods.py tests/test_problem_goods_script.py
git commit -m "fix: find problem goods candidates across nodes"
```

Do not push.
