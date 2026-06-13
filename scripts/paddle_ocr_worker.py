import json
import os
import sys
from pathlib import Path
from typing import Any


def flatten_paddle_result(raw: Any) -> list[dict[str, Any]]:
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
    rows.sort(key=lambda item: bbox_sort_key(item.get("bbox")))
    return rows


def bbox_sort_key(bbox: Any) -> tuple[float, float]:
    try:
        points = bbox if isinstance(bbox, list) else []
        xs = [float(point[0]) for point in points if isinstance(point, (list, tuple)) and len(point) >= 2]
        ys = [float(point[1]) for point in points if isinstance(point, (list, tuple)) and len(point) >= 2]
        return (min(ys) if ys else 0.0, min(xs) if xs else 0.0)
    except Exception:
        return (0.0, 0.0)


def main() -> int:
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        request = json.loads(sys.stdin.read() or "{}")
        image_paths = [str(item) for item in request.get("images") or [] if str(item).strip()]
    except Exception as exc:
        print(json.dumps({"error": f"invalid request: {exc}", "results": []}, ensure_ascii=False))
        return 1

    cache_root = Path(request.get("cache_dir") or Path(__file__).resolve().parents[1] / ".ocr_cache").resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(cache_root)
    os.environ["USERPROFILE"] = str(cache_root)

    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        print(json.dumps({"error": f"paddleocr unavailable: {exc}", "results": []}, ensure_ascii=False))
        return 0

    try:
        ocr = PaddleOCR(use_angle_cls=True, lang=request.get("lang") or "ch", show_log=False)
    except Exception as exc:
        print(json.dumps({"error": f"paddleocr init failed: {exc}", "results": []}, ensure_ascii=False))
        return 0

    results: list[dict[str, Any]] = []
    for image_path in image_paths:
        if not Path(image_path).is_file():
            results.append({"image_path": image_path, "items": [], "error": "image file not found"})
            continue
        try:
            raw = ocr.ocr(image_path, cls=True)
            results.append({"image_path": image_path, "items": flatten_paddle_result(raw), "error": ""})
        except Exception as exc:
            results.append({"image_path": image_path, "items": [], "error": str(exc)})
    print(json.dumps({"error": "", "results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
