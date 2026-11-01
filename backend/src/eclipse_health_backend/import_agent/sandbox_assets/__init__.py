"""沙箱子进程资产：``runner.py`` 与 ``eh_import_helpers``。

这里不是普通可导入模块：主进程把本目录路径传给子进程，由 ``runpy`` 执行
``runner.py``。新增 ``__init__.py`` 只是为了让构建工具把这两个文件打进 wheel。
"""

from __future__ import annotations
