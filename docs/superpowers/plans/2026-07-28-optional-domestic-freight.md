# Optional Domestic Freight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the implicit domestic-freight value 5 and submit freight only when the confirmed contract explicitly contains it.

**Architecture:** Keep intent/contract ownership in the agent service and request-shaping ownership in `order_support.py`. Missing freight remains absent end-to-end; explicit zero and positive values are normalized and preserved.

**Tech Stack:** Python 3.11, FastAPI, pytest.

## Global Constraints

- Preserve all existing Vue and agent integration changes.
- Do not change unrelated fee fields or existing script interfaces.
- Use `.venv\Scripts\python.exe` for tests.

---

### Task 1: Lock the Optional-Freight Contract

**Files:**
- Modify: `tests/test_data_factory_agent.py`
- Modify: `app/services/data_factory_agent.py`

**Interfaces:**
- Consumes: `DEFAULT_VARIABLES` and `_normalize_goal(...)`.
- Produces: new-order goals without implicit `confirm_freight` or `offer_freight`.

- [ ] Add a failing test proving a new goal with no freight request contains neither field.
- [ ] Add assertions proving explicit `"0"` and explicit positive values remain available.
- [ ] Run the focused test and verify it fails because `DEFAULT_VARIABLES` contains `"5"`.
- [ ] Remove only the two freight defaults.
- [ ] Run the focused tests and verify they pass.

### Task 2: Omit Missing Freight From Order Requests

**Files:**
- Modify: `tests/test_data_factory_agent.py`
- Modify: `app/data_scripts/order_support.py`

**Interfaces:**
- Consumes: `_build_confirm_data(order_data, variables, item_quantity)` and `_prepare_offer_data(order_data, variables, item_quantity)`.
- Produces: request dictionaries where freight keys exist only for explicit values.

- [ ] Add failing tests proving missing freight keys are absent from confirm and offer details.
- [ ] Add tests proving explicit numeric zero and positive freight are preserved.
- [ ] Run the focused tests and verify the old `"5"` fallback causes failure.
- [ ] Replace fallback selection with presence-aware selection and conditionally write freight keys.
- [ ] Compute `offer_total` with zero internally when freight is absent.
- [ ] Run focused tests, related agent tests, Python compilation, and `git diff --check`.
