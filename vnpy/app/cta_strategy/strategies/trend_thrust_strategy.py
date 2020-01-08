from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)

from vnpy.trader.constant import Interval


class TrendThrustStrategy(CtaTemplate):
    """"""
    author = "用Python的交易员"

    thrust_up = 0.52
    thrust_down = 0.4
    atr_window = 10
    risk_level = 5000
    long_trailing = 10.5
    short_trailing = 11.5

    day_open = 0
    day_high = 0
    day_low = 0
    day_range = 0
    atr_value = 0
    trading_size = 0
    long_entry = 0
    short_entry = 0
    intra_trade_high = 0
    intra_trade_low = 0
    long_stop = 0
    short_stop = 0
    last_bar = None
    entry_time = 0 # 报错添加
    parameters = [
        "thrust_up", "thrust_down", "atr_window", "risk_level",
        "long_trailing", "short_trailing", "entry_time"
    ]
    variables = [
        "day_open", "day_high", "day_low", "day_range", "atr_value",
        "trading_size", "long_entry", "short_entry", "long_stop",
        "short_stop"
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(TrendThrustStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )

        self.bg = BarGenerator(
            self.on_bar, 1, self.on_hour_bar, interval=Interval.HOUR)
        self.am = ArrayManager()

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        self.load_bar(10)

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

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        self.bg.update_bar(bar)

    def on_hour_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        # Cancel all previous order
        self.cancel_all()

        # Update the array manager
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        # Return directly if first bar
        if not self.last_bar:
            self.last_bar = bar
            return

        # New day
        if self.last_bar.datetime.date() != bar.datetime.date():
            if self.day_high:
                self.day_range = self.day_high - self.day_low

                up_range = self.thrust_up * self.day_range
                self.long_entry = bar.open_price + up_range

                down_range = self.thrust_down * self.day_range
                self.short_entry = bar.open_price - down_range

            self.day_open = bar.open_price
            self.day_high = bar.high_price
            self.day_low = bar.low_price
        # Same day
        else:
            self.day_high = max(self.day_high, bar.high_price)
            self.day_low = min(self.day_low, bar.low_price)

            self.long_entry = max(self.long_entry, self.day_high)
            self.short_entry = min(self.short_entry, self.day_low)

        # Update last bar buffer
        self.last_bar = bar

        # Holding no position
        if self.pos == 0:
            self.atr_value = self.am.atr(self.atr_window)
            self.trading_size = max(
                int(self.risk_level / self.atr_value), 1)

            self.intra_trade_low = bar.low_price
            self.intra_trade_high = bar.high_price

            if bar.close_price > self.day_open:
                self.buy(self.long_entry, self.trading_size, stop=True)
            else:
                self.short(self.short_entry, self.trading_size, stop=True)
        # Holding long position
        elif self.pos > 0:
            self.intra_trade_high = max(
                self.intra_trade_high, bar.high_price)
            self.long_stop = self.intra_trade_high * \
                (1 - self.long_trailing / 100)

            self.sell(self.short_entry, self.trading_size, stop=True)
        # Holding short position
        elif self.pos < 0:
            self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
            self.short_stop = self.intra_trade_low * \
                (1 + self.short_trailing / 100)

            self.cover(self.long_entry, self.trading_size, stop=True)

        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        pass

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
