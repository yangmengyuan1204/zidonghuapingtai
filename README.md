# 接口 + UI 自动化测试平台

这是一个按当前需求实现的 FastAPI + SQLite 测试平台骨架，包含账号权限、接口用例、UI 用例、执行记录、Allure 兼容结果文件和静态管理界面。

## 数据库表

数据库严格使用 6 张表，不包含独立 `role` 表，也不新增需求外字段：

- `user`：`id, username, password, role, create_time`
- `project`：`id, name, desc, create_time`
- `env`：`id, project_id, env_name, base_url, global_headers, global_vars, timeout`
- `api_case`：`id, project_id, env_id, case_name, method, url, headers, params, body, assert_rule, status, create_time`
- `ui_case`：`id, project_id, case_name, page_url, steps, timeout, status, create_time`
- `test_record`：`id, case_type, case_id, result, log, screenshot, report_path, execute_time`

`user.role` 直接使用字符串：`admin` 或 `normal`。

## 权限规则

- `admin`：可管理用户、项目、环境、接口用例、UI 用例，可执行用例和查看记录/报告/截图。
- `normal`：可登录、查看用例、执行用例、查看执行记录、报告和截图。
- `normal` 无法新增、编辑、删除任何配置，后端接口也会返回 `403`。

## 启动

```bash
pip install -r requirements.txt
python -m playwright install
uvicorn app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000
```

首次启动会自动创建默认管理员：

```text
账号：admin
密码：admin123
```

## Allure

每次执行会在 `reports/allure-results` 下生成 Allure 兼容结果文件。安装 Allure CLI 后可查看：

```bash
allure serve reports/allure-results
```

## UI steps 示例

```json
[
  {"action":"goto","value":"https://example.com"},
  {"action":"input","locator":"#id","value":"123"},
  {"action":"click","locator":"button[type=submit]"},
  {"action":"text_assert","locator":"body","value":"Example"}
]
```

当前支持的 UI action：`goto`、`input`、`click`、`wait`、`wait_for_selector`、`text_assert`、`screenshot`。

## 面向测试造数的优化

接口用例支持 `{{变量名}}` 占位符，可用在 `url`、`headers`、`params`、`body`、`assert_rule.contains` 中。变量来源：

- 环境表 `global_vars`
- 单次执行或批量执行传入的运行时变量
- 平台内置变量：`{{$timestamp}}`、`{{$datetime}}`、`{{$date}}`、`{{$uuid}}`、`{{$random_int}}`、`{{$random_str}}`、`{{$random_phone}}`、`{{$random_email}}`

接口断言字段 `assert_rule` 仍然使用原字段，不新增表字段。可以同时做断言和响应提取：

```json
{
  "status_code": 201,
  "contains": "success",
  "extract": {
    "user_id": "json.data.id",
    "token": "json.data.token",
    "trace_id": "header.x-trace-id"
  }
}
```

批量执行接口：

```http
POST /api/api-cases/batch-execute
```

请求体：

```json
{
  "case_ids": [1, 2, 3],
  "variables": {
    "username": "test_{{$random_int}}"
  }
}
```

批量执行会按 `case_ids` 顺序执行，前一个接口提取出的变量会自动传给后续接口，适合“登录拿 token -> 创建主数据 -> 创建关联数据 -> 查询校验”这类测试数据准备链路。
