"""
Axure .rp 文件解析 → 功能测试用例生成

用法:
    python scripts/axure_to_cases.py --rp-file <path> --project-id <id>

功能:
    1. 解析 .rp 文件（zip），提取 HTML/XML 中的需求文本
    2. 在数据库中新建 CaseGenerationTask（绑定到指定项目）
    3. 将提取的文本写入 RequirementNote
    4. 调用平台的 AI/规则引擎生成功能测试用例
    5. 输出 JSON 结果

依赖:
    pip install sqlalchemy requests
"""

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

# ── 项目路径引导 ─────────────────────────────────────────────
# 脚本在 scripts/ 目录下，项目根是父目录
_BASE_DIR = Path(__file__).resolve().parent.parent
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

# ── import 项目模块 ───────────────────────────────────────────
from app.database import SessionLocal
from app.models import (
    CaseGenerationCase,
    CaseGenerationRequirementNote,
    CaseGenerationTask,
    Project,
    AiConfig,
)
from app.functional_testing import (
    generate_functional_cases,
    _decode_bytes,
    _plain_text,
    _interesting_lines,
)


# ── 文本可读性检测 ────────────────────────────────────────


def is_text_readable(text: str) -> bool:
    """检测提取的文本是否可读（有足够的中文字符或真实英文词汇）。"""
    if not text or len(text.strip()) < 20:
        return False
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    # 中文项目核心指标：中文字符 >= 10 才算可读
    if chinese >= 10:
        return True
    # 英文兜底：至少 15 个长度 >= 4 的唯一字母序列，且包含元音字母（过滤掉纯 hex/乱码）
    words = set(re.findall(r"[A-Za-z]{4,}", text))
    vowel_words = {w for w in words if re.search(r"[aeiouAEIOU]", w)}
    if len(vowel_words) >= 15:
        return True
    return False


# ── 文本提取（复用项目逻辑，但直接操作文件） ───────────────────


def extract_axure_text(axure_path: str) -> str:
    """从 .rp 文件中提取有意义的文本。"""
    path = Path(axure_path)
    if not path.exists() or not path.is_file():
        return ""

    if not zipfile.is_zipfile(path):
        # 非 zip 文件，当作纯文本或 HTML 处理
        raw = path.read_bytes()
        text = _interesting_lines(_plain_text(_decode_bytes(raw)))
        if not is_text_readable(text):
            return ""
        return text

    texts: list[str] = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.file_size <= 0:
                continue
            if info.file_size > 1024 * 1024:
                continue
            name = info.filename.lower()
            if not name.endswith((".xml", ".html", ".htm", ".js", ".txt", ".json")):
                continue
            raw = archive.read(info)
            total += len(raw)
            texts.append(_plain_text(_decode_bytes(raw)))
            if total > 2 * 1024 * 1024:
                break

    return _interesting_lines("\n".join(texts))


def extract_axure_pages_text(axure_path: str) -> list[dict[str, Any]]:
    """按页面 HTML 文件提取，返回 [{id, title, text}] 列表。"""
    path = Path(axure_path)
    if not path.exists() or not path.is_file():
        return []

    pages: list[dict[str, Any]] = []
    if not zipfile.is_zipfile(path):
        raw = path.read_bytes()
        text = _interesting_lines(_plain_text(_decode_bytes(raw)))
        if text and is_text_readable(text):
            pages.append({
                "id": "p1-main",
                "title": path.stem,
                "text": text,
            })
        return pages

    with zipfile.ZipFile(path) as archive:
        html_infos = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and info.file_size > 0
            and info.file_size <= 1024 * 1024
            and info.filename.lower().endswith((".html", ".htm"))
            and "__macosx" not in info.filename.lower()
        ]
        for idx, info in enumerate(html_infos[:80], start=1):
            raw = _decode_bytes(archive.read(info))
            plain = _plain_text(raw)
            text = _interesting_lines(plain, limit=160)

            # 推断页面标题
            title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", raw, re.I)
            title = ""
            if title_match:
                title = _plain_text(title_match.group(1))[:120]
            if not title:
                heading_match = re.search(r"<h[1-3][^>]*>([\s\S]*?)</h[1-3]>", raw, re.I)
                if heading_match:
                    title = _plain_text(heading_match.group(1))[:120]
            if not title:
                title = Path(info.filename).stem[:120]

            if text or title:
                slug = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "-", title)[:60]
                pages.append({
                    "id": f"p{idx}-{slug or 'page'}",
                    "title": title,
                    "text": text,
                })

        # 如果没有 HTML 页面，回退到全文提取
        if not pages:
            full_text = extract_axure_text(axure_path)
            if full_text:
                pages.append({
                    "id": "p1-axure-fulltext",
                    "title": path.stem,
                    "text": full_text,
                })

    return pages


# ── 数据库操作 ────────────────────────────────────────────────


def get_latest_ai_config(db) -> AiConfig | None:
    """获取最新的 AI 配置。"""
    return (
        db.query(AiConfig)
        .order_by(AiConfig.id.desc())
        .first()
    )


def ensure_project_exists(db, project_id: int) -> None:
    """确保项目存在，否则报错。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        print(json.dumps({"error": f"项目 ID {project_id} 不存在"}, ensure_ascii=False))
        sys.exit(1)


def create_axure_task(db, project_id: int, rp_filename: str) -> CaseGenerationTask:
    """创建 Axure 用例生成任务。"""
    file_stem = Path(rp_filename).stem[:80]
    task = CaseGenerationTask(
        project_id=project_id,
        task_name=f"Axure生成-{file_stem}",
        target_name=file_stem,
        target_url="",
        requirement_text="",
        context="",
        status="draft",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def add_requirement_note(db, task: CaseGenerationTask, axure_text: str, pages: list[dict]) -> None:
    """将提取的 Axure 文本写入需求说明。"""
    if not axure_text:
        return

    target_cases = max(40, min(len(pages) * 2, 100)) if pages else 30
    lines = [
        f"【Axure 原型分析】\n文件：{Path(task.target_name).stem}\n",
        f"该原型共 {len(pages)} 个页面/视图，请生成至少 {target_cases} 条功能测试用例（当前仅生成了部分，远远不够），"
        f"每个页面模块必须覆盖：正常流程、异常场景、边界条件，"
        f"跨页面流程（增删改查、状态流转、权限验证）必须单独列出，"
        f"不允许合并或遗漏。如不明确可写入 questions_for_product。\n",
    ]

    if pages:
        lines.append(f"共识别 {len(pages)} 个页面：\n")
        for p in pages:
            title = p.get("title", "未命名页面")
            lines.append(f"\n--- 页面：{title} ---")
            text = p.get("text", "")
            if text:
                lines.append(text[:2000])  # 单页面不超过 2000 字
    else:
        lines.append("\n--- 提取文本 ---")
        lines.append(axure_text[:8000])

    note_text = "\n".join(lines)
    note = CaseGenerationRequirementNote(
        task_id=task.id,
        note_text=note_text,
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(note)
    db.commit()


def generate_cases_for_task(db, task: CaseGenerationTask) -> dict[str, Any]:
    """调用平台用例生成引擎。"""
    config = get_latest_ai_config(db)

    # 构造 task proxy（复用平台逻辑，inline 避免循环导入）
    target = task.target_url or task.target_name or ""
    task_proxy = SimpleNamespace(
        id=task.id,
        project_id=task.project_id,
        iteration_name=task.task_name,
        target_url=target,
        requirement_text=task.requirement_text or "",
        context=task.context or "",
        status=task.status,
    )
    generated = generate_functional_cases(
        task_proxy,
        "",  # axure_text 已经作为 note 传入，此处传空
        None,  # snapshot
        config,
        [],  # screenshots
        [],  # notes — generate_functional_cases 内部会从 DB 读取
    )

    # 删除旧的、非保护的用例
    for old_case in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).all():
        db.delete(old_case)
    db.flush()

    batch = uuid4().hex[:12]
    created = 0
    cases_output = []
    for item in generated.items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        case = CaseGenerationCase(
            task_id=task.id,
            title=title[:200],
            precondition=item.get("precondition", ""),
            steps=item.get("steps", ""),
            expected=item.get("expected", ""),
            priority=item.get("priority", "P1"),
            source_refs="",
            generation_batch=batch,
            manual_edited=0,
            test_result="untested",
            source_missing=0,
            remark="",
            create_time=datetime.now(),
            update_time=None,
        )
        db.add(case)
        created += 1
        cases_output.append({
            "title": title[:200],
            "precondition": item.get("precondition", ""),
            "steps": item.get("steps", ""),
            "expected": item.get("expected", ""),
            "priority": item.get("priority", "P1"),
        })

    task.status = "cases_generated"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(task)

    return {
        "source": generated.source,
        "warning": generated.warning,
        "created": created,
        "generation_batch": batch,
        "cases": cases_output,
        "task_id": task.id,
        "task_name": task.task_name,
    }


# ── 主入口 ────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Axure .rp 文件解析并生成功能测试用例")
    parser.add_argument("--rp-file", required=True, help="Axure .rp 文件路径")
    parser.add_argument("--project-id", required=True, type=int, help="项目 ID")
    args = parser.parse_args()

    rp_path = Path(args.rp_file)
    if not rp_path.exists():
        result = {"error": f"文件不存在: {args.rp_file}"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # 1. 解析 Axure 文件
    axure_text = extract_axure_text(str(rp_path))
    pages = extract_axure_pages_text(str(rp_path))

    if not axure_text and not pages:
        result = {
            "error": (
                f"从文件中提取的内容不可读（二进制格式）。\n"
                f"请用 Axure 打开后导出为 HTML（文件 → 导出 → HTML），"
                f"然后将导出的 HTML 包（zip）传入。\n"
                f"路径: {args.rp_file}"
            ),
            "pages_found": len(pages),
        }
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # 2. 连接数据库
    db = SessionLocal()
    try:
        ensure_project_exists(db, args.project_id)

        # 3. 创建任务
        task = create_axure_task(db, args.project_id, rp_path.name)

        # 4. 写入需求说明
        add_requirement_note(db, task, axure_text, pages)

        # 5. 生成用例
        output = generate_cases_for_task(db, task)
        output["project_id"] = args.project_id
        output["rp_file"] = str(rp_path)
        output["pages_found"] = len(pages)

        # 输出 JSON
        print(json.dumps(output, ensure_ascii=False, indent=2))

    except Exception as exc:
        db.rollback()
        result = {"error": f"生成失败: {exc}"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
