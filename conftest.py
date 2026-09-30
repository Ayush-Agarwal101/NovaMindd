"""
NovaMindd — pytest configuration

Sets up sys.path so all packages resolve without installation.
"""
import sys
from pathlib import Path

# Make project root importable
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
