"""模块安装目录搬移的回归测试。

Windows 上对“刚写入大量模型权重”的 staging 目录直接 ``os.replace`` 会返回
WinError 5；安装器改为逐文件移动。这里锁定该行为，避免以后退回目录重命名。
"""

from __future__ import annotations

from eclipse_health_backend.modules.manager import _move_tree


def test_move_tree_moves_nested_files_and_removes_source(tmp_path):
    staging = tmp_path / "staging"
    (staging / "models").mkdir(parents=True)
    (staging / "src").mkdir()
    (staging / "module.json").write_text('{"id":"example"}', encoding="utf-8")
    (staging / "models" / "weights.onnx").write_bytes(b"\x00" * (2 * 1024 * 1024))
    (staging / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    target = tmp_path / "installed"

    _move_tree(staging, target)

    assert not staging.exists()
    assert (target / "module.json").read_text(encoding="utf-8") == '{"id":"example"}'
    assert (target / "models" / "weights.onnx").stat().st_size == 2 * 1024 * 1024
    assert (target / "src" / "main.py").read_text(encoding="utf-8") == "print('ok')\n"
