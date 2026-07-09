from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from .materials import FUNCTIONAL_SCREENSHOT_DIR, ensure_functional_dirs


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
PADDLE_OCR_WORKER = BASE_DIR / "scripts" / "paddle_ocr_worker.py"

def _flatten_paddle_result(raw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    blocks = raw if isinstance(raw, list) else []
    for block in blocks:
        items = block if isinstance(block, list) else []
        for item in items:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            box = item[0]
            text_info = item[1]
            if not isinstance(text_info, (list, tuple)) or len(text_info) < 2:
                continue
            text = str(text_info[0] or "").strip()
            if not text:
                continue
            try:
                confidence = float(text_info[1])
            except (TypeError, ValueError):
                confidence = 0.0
            rows.append({"text": text, "confidence": confidence, "bbox": box})
    rows.sort(key=lambda item: _bbox_sort_key(item.get("bbox")))
    return rows


def _bbox_sort_key(bbox: Any) -> tuple[float, float]:
    try:
        points = bbox if isinstance(bbox, list) else []
        xs = [float(point[0]) for point in points if isinstance(point, (list, tuple)) and len(point) >= 2]
        ys = [float(point[1]) for point in points if isinstance(point, (list, tuple)) and len(point) >= 2]
        return (min(ys) if ys else 0.0, min(xs) if xs else 0.0)
    except Exception:
        return (0.0, 0.0)


def _image_size(image_path: str) -> dict[str, int]:
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            width, height = img.size
        return {"width": int(width), "height": int(height)}
    except Exception:
        return {"width": 0, "height": 0}


def _preprocess_image_variants_for_ocr(image_path: str) -> list[str]:
    """Create several OCR candidates and keep the original as a fallback."""
    variants = [image_path]
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        source = Path(image_path)
        with Image.open(source) as img:
            img = img.convert("RGB")
            width, height = img.size
            scale = 2 if width and height and max(width, height) < 2200 else 1
            if scale > 1:
                img = img.resize((width * scale, height * scale))

            enhanced = ImageEnhance.Contrast(img).enhance(1.45)
            enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.25)
            enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
            enhanced_path = FUNCTIONAL_SCREENSHOT_DIR / f"ocr-enhanced-{source.stem}.png"
            enhanced.save(enhanced_path)
            variants.append(str(enhanced_path))

            gray = ImageOps.grayscale(enhanced)
            gray_path = FUNCTIONAL_SCREENSHOT_DIR / f"ocr-gray-{source.stem}.png"
            gray.save(gray_path)
            variants.append(str(gray_path))

            threshold = gray.point(lambda value: 255 if value > 172 else 0)
            threshold_path = FUNCTIONAL_SCREENSHOT_DIR / f"ocr-threshold-{source.stem}.png"
            threshold.save(threshold_path)
            variants.append(str(threshold_path))
    except Exception:
        pass
    result: list[str] = []
    for item in variants:
        if item not in result:
            result.append(item)
    return result


def _preprocess_image_for_ocr(image_path: str) -> str:
    return _preprocess_image_variants_for_ocr(image_path)[-1]


def _ocr_python_candidates() -> list[str]:
    candidates: list[str] = []
    for value in [os.getenv("OCR_PYTHON"), os.getenv("PADDLE_OCR_PYTHON")]:
        if value and value not in candidates:
            candidates.append(value)
    for path in [
        BASE_DIR / ".venv_ocr" / "Scripts" / "python.exe",
        BASE_DIR / ".venv_ocr" / "bin" / "python",
    ]:
        if path.exists():
            candidates.append(str(path))
    return candidates


def _compact_ocr_error(error: Any, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(error or "")).strip()
    if not text:
        return ""
    lower = text.lower()
    if "numpy" in lower and ("c-extensions failed" in lower or "_multiarray_umath" in lower):
        return "OCR 运行环境的 NumPy/PaddleOCR 与当前 Python 不兼容，请重建 .venv_ocr，或把 OCR_PYTHON 指向可正常导入 paddleocr 的 Python 3.11/3.12 环境。"
    if "no module named 'paddleocr'" in lower or "no module named paddleocr" in lower:
        return "OCR 运行环境未安装 PaddleOCR，请安装 paddleocr，或把 OCR_PYTHON 指向已安装 PaddleOCR 的 Python 环境。"
    if "paddleocr unavailable" in lower:
        return "OCR 运行环境无法导入 PaddleOCR，请检查 .venv_ocr 或 OCR_PYTHON 配置。"
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _join_ocr_errors(errors: list[str]) -> str:
    compacted: list[str] = []
    for item in errors:
        message = _compact_ocr_error(item)
        if message and message not in compacted:
            compacted.append(message)
    return "；".join(compacted)


def _run_external_paddle_ocr(image_paths: list[str]) -> tuple[list[dict[str, Any]], str]:
    if not PADDLE_OCR_WORKER.exists():
        return [], "OCR 子进程脚本不存在"
    payload_paths = [Path(item).as_posix() for item in image_paths]
    request = json.dumps(
        {"images": payload_paths, "lang": "ch", "cache_dir": (BASE_DIR / ".ocr_cache").as_posix()},
        ensure_ascii=False,
    )
    errors: list[str] = []
    for python_path in _ocr_python_candidates():
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                [python_path, str(PADDLE_OCR_WORKER)],
                input=request,
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=180,
            )
        except Exception as exc:
            errors.append(f"{python_path}: {exc}")
            continue
        if completed.stderr.strip():
            logger.warning("OCR 子进程 stderr 输出 [%s]: %s", python_path, completed.stderr.strip()[:500])
        if completed.returncode != 0 and not completed.stdout.strip():
            errors.append(f"{python_path}: {completed.stderr.strip()[:500]}")
            continue
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            errors.append(f"{python_path}: OCR 输出不是合法 JSON")
            continue
        if payload.get("error"):
            errors.append(f"{python_path}: {payload.get('error')}")
        results = payload.get("results") if isinstance(payload, dict) else []
        if isinstance(results, list) and results:
            return results, _join_ocr_errors(errors)
    if errors:
        return [], _join_ocr_errors(errors)
    return [], "未配置 OCR_PYTHON，也未找到 .venv_ocr；请使用 Python 3.11/3.12 安装 PaddleOCR 运行时"


def _ocr_score(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    texts = [str(item.get("text") or "").strip() for item in items if str(item.get("text") or "").strip()]
    confidence_values = [float(item.get("confidence") or 0) for item in items]
    avg_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    char_count = sum(len(text) for text in texts)
    unique_count = len({text.lower() for text in texts})
    return avg_confidence * 1000 + min(char_count, 3000) / 3 + unique_count * 4


def _run_ocr_candidates(image_paths: list[str]) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    local_error = ""
    try:
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        for image_path in image_paths:
            try:
                results.append({"image_path": image_path, "items": _flatten_paddle_result(ocr.ocr(image_path, cls=True)), "error": ""})
            except Exception as exc:
                results.append({"image_path": image_path, "items": [], "error": _compact_ocr_error(exc)})
    except Exception as exc:
        local_error = _compact_ocr_error(exc)
        results, external_error = _run_external_paddle_ocr(image_paths)
        external_has_result = any((item.get("items") if isinstance(item, dict) else []) for item in results)
        if external_has_result:
            local_error = external_error or ""
        elif external_error:
            local_error = _join_ocr_errors([local_error, external_error])

    candidates: list[dict[str, Any]] = []
    best: dict[str, Any] = {"items": [], "image_path": image_paths[0] if image_paths else "", "score": 0}
    for result in results:
        items = result.get("items") if isinstance(result, dict) else []
        items = items if isinstance(items, list) else []
        score = _ocr_score(items)
        candidate = {
            "image_path": result.get("image_path"),
            "text_count": len(items),
            "score": round(score, 3),
            "error": _compact_ocr_error(result.get("error") or ""),
        }
        candidates.append(candidate)
        if score > float(best.get("score") or 0):
            best = {"items": items, "image_path": result.get("image_path") or "", "score": score}
    return best.get("items") or [], local_error, candidates


def _opencv_regions(image_path: str) -> list[dict[str, Any]]:
    """Detect coarse rectangular controls. This is evidence only, not a source of truth."""
    try:
        import cv2

        image = cv2.imread(image_path)
        if image is None:
            return []
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regions: list[dict[str, Any]] = []
        height, width = gray.shape[:2]
        min_area = max(120, int(width * height * 0.00015))
        for contour in contours[:500]:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < min_area or w < 20 or h < 10:
                continue
            if w > width * 0.98 and h > height * 0.98:
                continue
            kind = "input_or_button" if 18 <= h <= 90 else "panel_or_table"
            regions.append({"x": x, "y": y, "width": w, "height": h, "type": kind})
        regions.sort(key=lambda item: (item["y"], item["x"]))
        return regions[:80]
    except Exception:
        return []


def extract_screenshot_material(image_path: str) -> dict[str, Any]:
    """
    Convert a screenshot into text-first evidence for DeepSeek.

    DeepSeek is used as a text reasoning model only; it never receives the raw image.
    PaddleOCR is optional. If it is not installed, callers still receive a
    structured payload and can continue with DOM/manual confirmation.
    """
    ensure_functional_dirs()
    original = Path(image_path)
    if not original.exists() or not original.is_file():
        return {
            "analysis_source": "ocr_unavailable",
            "ocr_available": False,
            "ocr_error": "截图文件不存在",
            "image_path": image_path,
            "image_size": {"width": 0, "height": 0},
            "ocr_items": [],
            "ocr_text": "",
            "regions": [],
            "ocr_confidence": 0,
            "low_confidence_items": [],
            "needs_manual_confirm": True,
        }

    variants = _preprocess_image_variants_for_ocr(str(original))
    ocr_items, ocr_error, ocr_candidates = _run_ocr_candidates(variants)
    processed = ""
    if ocr_candidates:
        best_candidate = max(ocr_candidates, key=lambda item: float(item.get("score") or 0))
        processed = str(best_candidate.get("image_path") or "")
    if not processed:
        processed = variants[-1] if variants else str(original)

    confidence_values = [float(item.get("confidence") or 0) for item in ocr_items]
    avg_confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0
    low_confidence = [
        item for item in ocr_items if float(item.get("confidence") or 0) < 0.72
    ][:30]
    ocr_text = "\n".join(str(item.get("text") or "") for item in ocr_items if item.get("text"))
    return {
        "analysis_source": "ocr_material",
        "ocr_available": bool(ocr_items),
        "ocr_error": _compact_ocr_error(ocr_error),
        "image_path": str(original),
        "preprocessed_image_path": processed,
        "preprocessed_candidates": variants,
        "image_size": _image_size(str(original)),
        "ocr_items": ocr_items[:200],
        "ocr_text": ocr_text,
        "ocr_confidence": avg_confidence,
        "low_confidence_items": low_confidence,
        "ocr_candidates": ocr_candidates,
        "regions": _opencv_regions(processed),
        "needs_manual_confirm": (not ocr_items) or avg_confidence < 0.72 or bool(low_confidence),
    }
