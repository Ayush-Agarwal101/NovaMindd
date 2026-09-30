#!/usr/bin/env python3
"""
scripts/run_dev.py

Start the NovaMindd API in development mode with hot-reload.

Usage:
    python scripts/run_dev.py
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Load .env if present
env_file = ROOT / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"Loaded environment from {env_file}")


def main() -> int:
    result = subprocess.run(
        [
            sys.executable, "-m", "uvicorn",
            "apps.api.main:app",
            "--host", os.environ.get("API_HOST", "0.0.0.0"),
            "--port", os.environ.get("API_PORT", "8000"),
            "--reload",
            "--reload-dir", str(ROOT / "apps"),
            "--reload-dir", str(ROOT / "core"),
        ],
        cwd=str(ROOT),
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
