"""MyFinances 量化回测枚举类型定义。

将散落在配置校验和业务逻辑中的裸字符串统一为 StrEnum，
提升类型安全性和 IDE 自动补全体验。
"""

from __future__ import annotations

from enum import StrEnum


class SelectionMode(StrEnum):
    """选股方向。"""

    TOP = "top"
    BOTTOM = "bottom"


class ScoreSource(StrEnum):
    """评分来源。"""

    AUTO = "auto"
    BUILTIN = "builtin"
    EXTERNAL = "external"


class AllocationModel(StrEnum):
    """仓位分配模型。"""

    EQUAL_WEIGHT = "equal_weight"
    SCORE_WEIGHTED = "score_weighted"
    MAX_SHARPE = "max_sharpe"
    MIN_VARIANCE = "min_variance"


class ExecutionStyle(StrEnum):
    """成交执行风格。"""

    MARKET = "market"
    TWAP = "twap"


class PriceField(StrEnum):
    """回测估值价格字段。"""

    CLOSE = "close"
    ADJUSTED_CLOSE = "adjusted_close"


class ExecutionPriceField(StrEnum):
    """成交价格字段。"""

    CLOSE = "close"
    ADJUSTED_CLOSE = "adjusted_close"
    OPEN = "open"
    VWAP = "vwap"


class OrderSide(StrEnum):
    """订单方向。"""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatusEnum(StrEnum):
    """订单状态。"""

    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
