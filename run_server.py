from pathlib import Path
import argparse
import sys


BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    sys.stdout = (log_dir / "uvicorn.out.log").open("a", encoding="utf-8", buffering=1)
    sys.stderr = (log_dir / "uvicorn.err.log").open("a", encoding="utf-8", buffering=1)

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
