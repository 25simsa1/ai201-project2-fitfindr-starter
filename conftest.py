import os
import sys

# Put the project root (where tools.py lives) on sys.path so that
# `pytest tests/` run from the repo root can do `from tools import ...`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
