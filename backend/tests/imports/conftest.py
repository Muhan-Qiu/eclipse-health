"""导入链路测试夹具。

复用 ``tests/conftest.py`` 的临时 ``EH_DATA_DIR`` 与 ``client``；
若 B2-01 尚未在 ``app.py`` 挂载 imports router，这里直接挂到 ``/api/v1``。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from import_helpers import SAMPLES_DIR


@pytest.fixture()
def samples_dir() -> Path:
    return SAMPLES_DIR
