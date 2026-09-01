import argparse

import uvicorn

from harness_metrics.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Hubble local data service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
