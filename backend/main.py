from __future__ import annotations

import uvicorn

__all__ = ["main"]


def main() -> None:
    uvicorn.run(
        "api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
