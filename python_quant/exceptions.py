"""MyFinances 量化回测自定义异常层次。

所有自定义异常继承自 :class:`QuantBaseError`，同时也继承自
Python 内置异常基类，确保向后兼容。
"""

from __future__ import annotations


class QuantBaseError(Exception):
    """量化回测模块所有异常的基类。"""


class ConfigValidationError(QuantBaseError, ValueError):
    """配置参数校验失败时抛出。

    继承 ``ValueError`` 以保持向后兼容。
    """


class DataValidationError(QuantBaseError, ValueError):
    """数据加载或数据质量校验失败时抛出。

    继承 ``ValueError`` 以保持向后兼容。
    """


class DataNotFoundError(QuantBaseError, FileNotFoundError):
    """数据文件不存在时抛出。

    继承 ``FileNotFoundError`` 以保持向后兼容。
    """


class BacktestRuntimeError(QuantBaseError, RuntimeError):
    """回测运行过程中遇到不可恢复错误时抛出。

    继承 ``RuntimeError`` 以保持向后兼容。
    """


class InsufficientDataError(QuantBaseError, ValueError):
    """回测所需数据不足时抛出（例如历史长度不足，数据缺失）。

    继承 ``ValueError`` 以保持向后兼容。
    """
