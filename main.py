import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9527

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    uvicorn.run("app.main:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=False)


if __name__ == "__main__":
    main()
