"""OpenWhisk Python action entrypoint shim.

The OpenWhisk python runtime imports ``main`` from the action archive's top-level
module. This shim exposes the hardened handler from ``action/main.py``. The
runtime already implements the /init and /run HTTP interface; we only provide
``main(params) -> dict``.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "action"))

from main import main  # noqa: E402,F401  (re-exported for the OpenWhisk runtime)
