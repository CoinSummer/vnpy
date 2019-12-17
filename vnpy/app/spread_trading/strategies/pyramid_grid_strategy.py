from math import floor, ceil

from vnpy.app.spread_trading import (
    SpreadStrategyTemplate,
    SpreadAlgoTemplate,
    SpreadData,
    OrderData,
    TradeData
)


class PyramidGridStrategy(SpreadStrategyTemplate):
    """"""

    author = "用Python的交易员"

    grid_price = 5.0
    grid_size = 1.0
    grid_start = 0.0
    pyramid_multiplier = 2.0
    max_pos = 0.0
    payup = 10
    interval = 5

    spread_pos = 0.0
    target_pos = 0.0
    current_grid = 0.0
    long_algoid = ""
    short_algoid = ""

    parameters = [
        "grid_price",
        "grid_size",
        "grid_start",
        "pyramid_multiplier",
        "max_pos",
        "payup",
        "interval"
    ]
    variables = [
        "spread_pos",
        "target_pos",
        "current_grid",
        "long_algoid",
        "short_algoid"
    ]

    def __init__(
        self,
        strategy_engine,
        strategy_name: str,
        spread: SpreadData,
        setting: dict
    ):
        """"""
        super().__init__(
            strategy_engine, strategy_name, spread, setting
        )

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

        # 清空算法号缓存
        self.long_algoid = ""
        self.short_algoid = ""

        self.put_event()

    def on_spread_data(self):
        """
        Callback when spread price is updated.
        """
        self.spread_pos = self.get_spread_pos()

        # 计算当前网格位置
        mid_price = (self.spread.bid_price + self.spread.ask_price) / 2
        self.current_grid = (mid_price - self.grid_start) / self.grid_price

        # 基于网格位置，计算上下买卖价格
        long_price = (
            floor(self.current_grid) * self.grid_price + self.grid_start
        )
        short_price = (
            ceil(self.current_grid) * self.grid_price + self.grid_start
        )

        # 倒金字塔模式计算当前目标仓位
        self.target_pos = 0
        int_grid = floor(abs(self.current_grid))
        grid_count = 0        
        target_pos = 0
        
        while grid_count < int_grid:
            grid_count += 1
            grid_pos = pow(self.pyramid_multiplier, grid_count - 1) * self.grid_size
            target_pos += grid_pos
        
        if self.current_grid > 0:
            self.target_pos = -target_pos
        else:
            self.target_pos = target_pos

        # 判断是否要启动算法
        if (
            self.spread_pos <= self.max_pos and     # 持仓没超过上限
            self.spread_pos <= self.target_pos and  # 小于等于目标仓位
            not self.long_algoid                    # 当前没有活动算法
        ):
            volume = self.max_pos - self.spread_pos     # 多头剩余可开仓位

            self.long_algoid = self.start_long_algo(
                long_price, volume, self.payup, self.interval)

        if (
            self.spread_pos >= -self.max_pos and
            self.spread_pos >= self.target_pos and
            not self.short_algoid
        ):
            volume = self.max_pos + self.spread_pos     # 空头剩余可开仓位

            self.short_algoid = self.start_short_algo(
                short_price, volume, self.payup, self.interval)

        # 更新图形界面
        self.put_event()

    def on_spread_pos(self):
        """
        Callback when spread position is updated.
        """
        self.spread_pos = self.get_spread_pos()
        self.put_event()

    def on_spread_algo(self, algo: SpreadAlgoTemplate):
        """
        Callback when algo status is updated.
        """
        # 若有算法全部成交，则清空算法编号缓存，等待下一轮挂出新的
        if not algo.is_active():
            if self.long_algoid == algo.algoid:
                self.long_algoid = ""
            elif self.short_algoid == algo.algoid:
                self.short_algoid = ""

        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback when order status is updated.
        """
        pass

    def on_trade(self, trade: TradeData):
        """
        Callback when new trade data is received.
        """
        pass
