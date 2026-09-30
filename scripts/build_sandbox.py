#!/usr/bin/env python3
"""
scripts/build_sandbox.py

Build the NovaMindd sandbox Docker image.
Run this before any code execution tests or agent workflows.

Usage:
    python scripts/build_sandbox.py
"""
import subprocess
import sys
from pathlib import Path

SANDBOX_DIR = Path(__file__).parent.parent / "sandbox" / "images"
IMAGE_TAG = "novamindd-sandbox:latest"


def main() -> int:
    print(f"Building sandbox image: {IMAGE_TAG}")
    print(f"Context: {SANDBOX_DIR}")

    result = subprocess.run(
        ["docker", "build", "-t", IMAGE_TAG, str(SANDBOX_DIR)],
        capture_output=False,
    )
    if result.returncode != 0:
        print("ERROR: Sandbox image build failed.", file=sys.stderr)
        return result.returncode

    print(f"Sandbox image built successfully: {IMAGE_TAG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
