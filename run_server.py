from pathlib import Path
import argparse
import site
import sys


BASE_DIR = Path(__file__).resolve().parent
VENV_SITE = BASE_DIR / ".venv" / "Lib" / "site-packages"
if VENV_SITE.exists():
    site.addsitedir(str(VENV_SITE))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Auto-reload when Python files change.")
    args = parser.parse_args()

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # 将日志重定向到文件，失败时仅警告不退出
    try:
        sys.stdout = (log_dir / "uvicorn.out.log").open("a", encoding="utf-8", buffering=1)
        sys.stderr = (log_dir / "uvicorn.err.log").open("a", encoding="utf-8", buffering=1)
    except OSError as exc:
        print(f"警告: 无法打开日志文件，将使用控制台输出: {exc}")

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info", reload=args.reload)


if __name__ == "__main__":
    main()
