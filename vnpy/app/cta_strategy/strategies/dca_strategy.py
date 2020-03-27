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
from datetime import time




class DcaStrategy(CtaTemplate):
    """定投策略"""
    author = "wwdd"

    # 每期定投金额
    pay = 1000

    # 定投时间 每日 每周  每月  固定日期 固定星期几


    parameters = ["pay"]
    variables = ["tick_count", "test_all_done"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(DcaStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )


        self.bg = BarGenerator(self.on_bar)


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
        # print(bar)

        d = bar.datetime.date()
        week_t = d.weekday()
        if week_t == 4 or week_t == 6 :
            # print((self.pay/7/bar.close_price))
            self.buy(bar.close_price, (self.pay/7/bar.close_price))
        self.put_event()



    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        # self.put_event()
        pass

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        # self.put_event()
        pass

