from __future__ import annotations

from html import unescape
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, Iterable
from uuid import uuid4
import zipfile

from ..executors import ensure_report_dirs
from ..models import FunctionalRequirementNote, FunctionalScreenshot, FunctionalTask, PageSnapshot


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
FUNCTIONAL_DIR = BASE_DIR / "reports" / "functional"
AXURE_DIR = FUNCTIONAL_DIR / "axure"
FUNCTIONAL_SCREENSHOT_DIR = FUNCTIONAL_DIR / "screenshots"

def ensure_functional_dirs() -> None:
    ensure_report_dirs()
    AXURE_DIR.mkdir(parents=True, exist_ok=True)
    FUNCTIONAL_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def store_axure_file(filename: str, content: bytes) -> str:
    ensure_functional_dirs()
    suffix = Path(filename or "prototype.rp").suffix or ".rp"
    target = AXURE_DIR / f"{uuid4()}{suffix}"
    target.write_bytes(content)
    return str(target)


# 常见图片格式魔数
_IMAGE_MAGIC_BYTES: dict[bytes, tuple[str, ...]] = {
    b"\x89PNG\r\n\x1a\n": (".png",),
    b"\xff\xd8\xff": (".jpg", ".jpeg"),
    b"RIFF": (".webp",),  # WebP 以 RIFF....WEBP 开头，需要进一步判断
}


def _validate_image_content(content: bytes, suffix: str) -> None:
    """校验文件内容魔数是否匹配声明的后缀。"""
    if len(content) < 12:
        raise ValueError(f"文件内容过短 ({len(content)} bytes)，不是有效的图片文件")
    for magic, extensions in _IMAGE_MAGIC_BYTES.items():
        if content.startswith(magic):
            if suffix in extensions:
                return  # 魔数匹配
            # 魔数指向另一种格式，拒绝
            expected_exts = "/".join(extensions)
            raise ValueError(f"文件内容为 {expected_exts} 格式，但后缀名为 {suffix}")
    # WebP 额外检测：RIFF....WEBP
    if suffix == ".webp" and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return
    raise ValueError(f"无法识别的图片格式或文件内容与后缀 {suffix} 不匹配")


def store_functional_screenshot_file(filename: str, content: bytes) -> str:
    ensure_functional_dirs()
    suffix = Path(filename or "screenshot.png").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("只支持上传 PNG/JPG/WebP 截图")
    # 魔数校验
    _validate_image_content(content, suffix)
    target = FUNCTIONAL_SCREENSHOT_DIR / f"{uuid4()}{suffix}"
    target.write_bytes(content)
    return str(target)


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _plain_text(raw: str) -> str:
    attr_text = " ".join(
        item
        for item in re.findall(r"""(?:placeholder|aria-label|title|value|alt)\s*=\s*["']([^"']+)["']""", raw or "", flags=re.I)
        if item
    )
    text = unescape(f"{raw or ''} {attr_text}")
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _interesting_lines(text: str, limit: int = 220) -> str:
    chunks = re.split(r"[\r\n。；;!?！？]| {2,}", text)
    seen = set()
    lines: list[str] = []
    for chunk in chunks:
        item = chunk.strip(" \t:：,，.-")
        if len(item) < 2 or len(item) > 120:
            continue
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", item):
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(item)
        if len(lines) >= limit:
            break
    return "\n".join(lines)


def read_axure_text(axure_path: str | None) -> str:
    if not axure_path:
        return ""
    path = Path(axure_path)
    if not path.exists() or not path.is_file():
        return ""
    try:
        if zipfile.is_zipfile(path):
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
        return _interesting_lines(_plain_text(_decode_bytes(path.read_bytes())))
    except Exception as exc:
        logger.warning("Axure解析失败: %s", exc)
        return None


def _safe_page_id(index: int, name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "-", name or "").strip("-")[:60]
    return f"p{index}-{slug or 'page'}"


def _title_from_html(raw: str, fallback: str) -> str:
    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", raw, flags=re.I)
    if title_match:
        title = _plain_text(title_match.group(1))
        if title:
            return title[:120]
    heading_match = re.search(r"<h[1-3][^>]*>([\s\S]*?)</h[1-3]>", raw, flags=re.I)
    if heading_match:
        title = _plain_text(heading_match.group(1))
        if title:
            return title[:120]
    return Path(fallback).stem[:120] or fallback[:120]


def _axure_page_item(index: int, name: str, raw: str, source_type: str) -> Dict[str, Any]:
    plain = _plain_text(raw)
    text = _interesting_lines(plain, limit=160)
    title = _title_from_html(raw, name) if source_type == "html" else (Path(name).stem or f"页面{index}")[:120]
    return {
        "id": _safe_page_id(index, name),
        "title": title,
        "path": name,
        "source_type": source_type,
        "text": text,
        "text_length": len(text),
    }


def extract_axure_pages(axure_path: str | None) -> Dict[str, Any]:
    if not axure_path:
        return {"pages": [], "summary": {"page_count": 0, "quality": "缺失", "message": "未上传 Axure"}}
    path = Path(axure_path)
    if not path.exists() or not path.is_file():
        return {"pages": [], "summary": {"page_count": 0, "quality": "缺失", "message": "Axure 文件不存在"}}

    pages: list[Dict[str, Any]] = []
    try:
        if zipfile.is_zipfile(path):
            fallback_texts: list[str] = []
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
                for info in html_infos[:80]:
                    raw = _decode_bytes(archive.read(info))
                    item = _axure_page_item(len(pages) + 1, info.filename, raw, "html")
                    if item["text_length"] >= 5 or item.get("title"):
                        pages.append(item)
                if not pages:
                    total = 0
                    for info in archive.infolist():
                        if info.is_dir() or info.file_size <= 0 or info.file_size > 1024 * 1024:
                            continue
                        name = info.filename.lower()
                        if not name.endswith((".xml", ".js", ".json", ".txt")):
                            continue
                        raw = archive.read(info)
                        total += len(raw)
                        fallback_texts.append(_plain_text(_decode_bytes(raw)))
                        if total > 2 * 1024 * 1024:
                            break
                    text_value = _interesting_lines("\n".join(fallback_texts), limit=220)
                    if text_value:
                        pages.append(
                            {
                                "id": "p1-axure-fulltext",
                                "title": "Axure 全文材料",
                                "path": path.name,
                                "source_type": "rp_text",
                                "text": text_value,
                                "text_length": len(text_value),
                            }
                        )
        else:
            raw = _decode_bytes(path.read_bytes())
            source_type = "html" if path.suffix.lower() in {".html", ".htm"} else "text"
            item = _axure_page_item(1, path.name, raw, source_type)
            if item["text_length"]:
                pages.append(item)
    except Exception as exc:
        return {"pages": [], "summary": {"page_count": 0, "quality": "缺失", "message": f"Axure 页面索引解析失败：{exc}"}}

    total_text = sum(item.get("text_length", 0) for item in pages)
    if not pages:
        quality = "缺失"
        message = "没有从 Axure 中解析到可用页面内容，建议上传 Axure HTML 导出包、产品截图或补充需求"
    elif len(pages) == 1 and total_text < 300:
        quality = "不足"
        message = "只识别到少量 Axure 文本，生成测试点前建议补充截图或需求说明"
    elif any(item.get("source_type") == "html" for item in pages):
        quality = "充分" if total_text >= 600 else "不足"
        message = "已从 Axure HTML 中解析页面目录和文本"
    else:
        quality = "不足" if total_text < 800 else "充分"
        message = "已从 Axure 文件中提取文本，但无法完整还原交互结构"
    return {"pages": pages, "summary": {"page_count": len(pages), "total_text_length": total_text, "quality": quality, "message": message}}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def selected_axure_text(task: FunctionalTask) -> str:
    pages = _json_list(getattr(task, "axure_pages", "") or "")
    if not pages:
        return read_axure_text(task.axure_path)
    selected_ids = {str(item) for item in _json_list(getattr(task, "bound_axure_pages", "") or "")}
    selected = [item for item in pages if not selected_ids or str(item.get("id")) in selected_ids]
    if not selected:
        selected = pages
    parts = []
    for item in selected[:20]:
        title = item.get("title") or item.get("path") or "Axure页面"
        text_value = item.get("text") or ""
        if text_value:
            parts.append(f"Axure页面：{title}\n{text_value}")
    return "\n\n".join(parts)


def compact_requirement(
    task: FunctionalTask,
    axure_text: str,
    snapshot: PageSnapshot | None = None,
    screenshots: Iterable[FunctionalScreenshot] | None = None,
    notes: Iterable[FunctionalRequirementNote] | None = None,
) -> str:
    parts = [
        f"迭代：{task.iteration_name}",
        f"目标页面：{task.target_url}",
        f"初始需求说明：{task.requirement_text or ''}",
    ]
    context = getattr(task, "context", None) or ""
    if context.strip():
        parts.append(f"项目上下文（业务背景 / 本次迭代范围）：\n{context[:8000]}")
    material_quality = getattr(task, "material_quality", "") or ""
    if material_quality:
        parts.append(f"需求材料质量：\n{material_quality[:4000]}")
    note_text = "\n".join(
        f"- {item.create_time}: {item.note_text}" for item in (notes or []) if getattr(item, "note_text", "")
    )
    if note_text:
        parts.append(f"产品沟通后的补充需求：\n{note_text[:12000]}")
    screenshot_parts: list[str] = []
    for item in (screenshots or []):
        analysis = getattr(item, "analysis_result", "") or ""
        corrected = getattr(item, "corrected_text", "") or ""
        ocr_text = getattr(item, "ocr_text", "") or ""
        material_parts = []
        if corrected.strip():
            material_parts.append(f"人工校对后的 OCR 文本（优先使用）：\n{corrected[:12000]}")
        elif ocr_text.strip():
            material_parts.append(f"OCR 原始文本：\n{ocr_text[:12000]}")
        if analysis.strip():
            material_parts.append(f"截图结构化分析：\n{analysis[:12000]}")
        if material_parts:
            screenshot_parts.append(f"截图#{getattr(item, 'id', '')}识别材料：\n" + "\n\n".join(material_parts))
    screenshot_text = "\n\n".join(screenshot_parts)
    if screenshot_text:
        parts.append(f"产品截图识别材料：\n{screenshot_text[:20000]}")
    if axure_text:
        parts.append(f"Axure提取文本：\n{axure_text[:12000]}")
    if snapshot and snapshot.dom_summary:
        parts.append(f"页面DOM摘要：\n{snapshot.dom_summary[:12000]}")
    return "\n\n".join(parts)
