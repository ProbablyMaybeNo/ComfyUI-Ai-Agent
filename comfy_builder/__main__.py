"""ComfyUI AI Builder — CLI entry point."""

import sys
from .cli import main

sys.exit(main() or 0)
