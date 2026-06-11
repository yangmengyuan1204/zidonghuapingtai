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
    log_dir.mkdir(exist_ok=True)
    sys.stdout = (log_dir / "uvicorn.out.log").open("a", encoding="utf-8", buffering=1)
    sys.stderr = (log_dir / "uvicorn.err.log").open("a", encoding="utf-8", buffering=1)

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info", reload=args.reload)


if __name__ == "__main__":
    main()
