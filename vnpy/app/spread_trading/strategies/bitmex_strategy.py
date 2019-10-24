from vnpy.app.spread_trading import (
    SpreadStrategyTemplate,
    SpreadAlgoTemplate,
    SpreadData,
    OrderData,
    TradeData
)



class BitmexStrategy(SpreadStrategyTemplate):
    author = "wwdd"

    buy_price = 0.0
    sell_price = 0.0
    cover_price = 0.0
    short_price = 0.0
    max_pos = 0.0
    payup = 10
    interval = 5

    spread_pos = 0.0
    buy_algoid = ""
    sell_algoid = ""
    short_algoid = ""
    cover_algoid = ""

    parameters = [
        "buy_price",
        "sell_price",
        "cover_price",
        "short_price",
        "max_pos",
        "payup",
        "interval",
        "set_max_pos"
    ]
    variables = [
        "spread_pos",
        "buy_algoid",
        "sell_algoid",
        "short_algoid",
        "cover_algoid",
    ]

    def __init__(
            self,
            strategy_engine,
            strategy_name: str,
            spread: SpreadData,
            setting: dict
    ):
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

        self.buy_algoid = ""
        self.sell_algoid = ""
        self.short_algoid = ""
        self.cover_algoid = ""
        self.put_event()
