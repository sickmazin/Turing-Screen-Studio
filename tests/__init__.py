"""Tests use a throw-away data folder, never the real one in %APPDATA%. Run: python -m unittest discover -s tests -t ."""
import os
import tempfile

os.environ["TSS_DATA"] = tempfile.mkdtemp(prefix="tss-test-")
