"""可选的 Open Health Sync 连接器。

OHS 是用户自行运行的外部服务（Go + Postgres + Docker，AGPL-3.0）。
这里只通过 HTTP 读取日汇总，不安装、不打包、不复制其代码。
普通用户不配置时，本模块不会被调用。
"""

from __future__ import annotations

__all__: list[str] = []
