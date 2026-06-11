"""Debug script to log what argument Windows passes for hermes:// URLs"""
import sys
from pathlib import Path

log_file = Path(__file__).parent / "debug_args.txt"
with open(log_file, "a", encoding="utf-8") as f:
    f.write(f"argv: {sys.argv}\n")
    f.write(f"argv[1] if exists: {sys.argv[1] if len(sys.argv) > 1 else 'NONE'}\n")
    f.write("---\n")
