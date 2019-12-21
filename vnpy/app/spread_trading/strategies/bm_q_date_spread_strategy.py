from vnpy.app.spread_trading import (
    SpreadStrategyTemplate,
    SpreadAlgoTemplate,
    SpreadData,
    OrderData,
    TradeData,
    TickData,
    BarData

)
from vnpy.trader.utility import BarGenerator, ArrayManager

from datetime import datetime, timedelta, date
import calendar

class BmQDateSpreadStrategy(SpreadStrategyTemplate):
    """
    在每月固定时间执行策略
    只远期开空，近期开多
    符合平仓条件后，平空 平多
    """

    author = "wwdd"

    buy_price = 50
    sell_price = 150
    cover_price = 50
    short_price = 150
    max_pos = 100.0
    payup = 10
    interval = 5
    start_days = 3  # 每月第x天开始执行策略
    end_days = 1     # 每月最后一个周五前x天执行平仓策略
    test_type = 1  # 1 = 回测  2=实盘

    end_date = None

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
        "stard_days",
        "end_days",
        "test_type",
        "end_date"

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
        """"""
        super().__init__(
            strategy_engine, strategy_name, spread, setting
        )
        self.bg = BarGenerator(self.on_spread_bar, 10, self.on_10min_bar)

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

        self.buy_algoid = ""
        self.sell_algoid = ""
        self.short_algoid = ""
        self.cover_algoid = ""
        self.put_event()

    def on_spread_data(self):
        """
        Callback when spread price is updated.
        """
        tick = self.get_spread_tick()
        self.on_spread_tick(tick)

    def on_10min_bar(self, bar: BarData):
        self.spread_pos = self.get_spread_pos()

        if not self.end_date:
            print("无截止日期参数  break")
            return

        if self.test_type == 1:
            time_now = bar.datetime
        else:
            time_now = datetime.now()

        date_parse = datetime.strptime(self.end_date, '%Y-%m-%d')
        # print(date_parse)
        # print(date_parse, time_now, (time_now <= (date_parse - timedelta(days=self.end_days))), bar.close_price, date_parse - timedelta(days=self.end_days))
        print(bar.close_price, bar.datetime)
        if (time_now <= (date_parse - timedelta(days = self.end_days))):
            # 当在开单区间内执行正常逻辑
            # No position
            if not self.spread_pos:
                self.stop_close_algos()
                if not self.short_algoid:
                    self.short_algoid = self.start_short_algo(
                        self.short_price, self.max_pos, self.payup, self.interval
                    )
                    if self.short_algoid:
                        print(f" 正常开仓时间 {time_now}")

            # Short position
            elif self.spread_pos < 0:
                self.stop_open_algos()
                # Start cover close algo
                if not self.cover_algoid:
                    self.cover_algoid = self.start_long_algo(
                        self.cover_price, abs(
                            self.spread_pos), self.payup, self.interval
                    )
                    if self.cover_algoid:
                        print(f" 正常平仓时间 {time_now}")
        else:
            if self.spread_pos < 0:
                # 当超出策略执行时间，且有仓位时。 仅仅平仓。
                self.stop_open_algos()
                self.stop_close_algos()
                # print(f"强制平仓  当前仓位{self.spread_pos}")
                if not self.cover_algoid:
                    # print(f" 强制平仓时间 {time_now} {bar.close_price}")
                    self.cover_algoid = self.start_long_algo(
                        bar.close_price, abs(
                            self.spread_pos), self.payup, self.interval
                    )
                    if self.cover_algoid:
                        print(f" 强制平仓时间 {time_now}")

            elif self.spread_pos == 0:
                self.stop_open_algos()
                self.stop_close_algos()
                print(f"仅ing平仓 无 仓位  {time_now} ")
                pass

        self.put_event()

    def on_spread_bar(self, bar: BarData):
        """
        Callback when spread price is updated.
        """
        self.bg.update_bar(bar)


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
        if not algo.is_active():
            if self.buy_algoid == algo.algoid:
                self.buy_algoid = ""
            elif self.sell_algoid == algo.algoid:
                self.sell_algoid = ""
            elif self.short_algoid == algo.algoid:
                self.short_algoid = ""
            else:
                self.cover_algoid = ""

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

    def stop_open_algos(self):
        """"""
        if self.buy_algoid:
            self.stop_algo(self.buy_algoid)

        if self.short_algoid:
            self.stop_algo(self.short_algoid)

    def stop_close_algos(self):
        """"""
        if self.sell_algoid:
            self.stop_algo(self.sell_algoid)

        if self.cover_algoid:
            self.stop_algo(self.cover_algoid)

    def running_calender_day(self, date_now, start_d, end_d):

        """
        判断合约运行时间
        每月前n 天不启动策略
        每月最后周五前 n 天执行平仓
        """
        # date_now = datetime.now()
        # 当月运行策略时间区间
        # print(f"date_now {date_now}")
        year = date_now.date().year
        month = date_now.date().month
        start_date = datetime(year, month, start_d)
        end_day = max(week[calendar.FRIDAY]
                      for week in calendar.monthcalendar(year, month))

        end_date = datetime(year, month, (end_day - end_d))

        # print('{:4d}-{:02d}-{:02d}'.format(year, month, end_day))
        return [start_date, end_date, datetime(year, month, end_day)]

    def running_calender_hour(self):
        pass