"""教练模式（G4）：只读上下文汇总 + Open-Meteo 天气。

这里刻意不导入评分/记忆模块：G2/G3 尚未就绪时，教练上下文仍然可以
独立启动并只返回已有的部分。
"""

from .weather import clear_weather_cache, get_weather

__all__ = ["clear_weather_cache", "get_weather"]
