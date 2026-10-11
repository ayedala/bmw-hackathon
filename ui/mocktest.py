"""Compatibility entry point for the guided decision website."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("agent.py")), run_name="__main__")
