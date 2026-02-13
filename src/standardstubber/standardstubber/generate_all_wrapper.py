"""
wrapper for generate_all to make it runnable as a module.

this module re-exports the main function from generate_all.py
so it can be invoked via `uv run generate-all`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# add parent directory to path so we can import generate_all
_parent = Path(__file__).parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from generate_all import main as _main


def main() -> int:
    """wrapper for generate_all.main()."""
    return _main()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
