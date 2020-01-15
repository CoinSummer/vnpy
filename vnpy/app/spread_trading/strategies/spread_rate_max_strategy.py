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

class SpreadRateMaxStrategy(SpreadStrategyTemplate):
    """
    在每月固定时间执行策略
    只远期开空，近期开多
    符合平仓条件后，平空 平多
    策略启动时需要将trading_type 设置为 rate
    其他策略默认使用price 交易
    移除 buy sell cover ... price 参数
    
    spread_rate 参数仅作为回测时使用, 与SpreadData中 spread_rate 搭配使用
    tick event 中添加 ask_spread_rate bid_spread_rate 作为 algo 策略中判断使用
    """

    author = "wwdd"

    max_pos = 100.0
    trade_pos = 10.0
    payup = 10.0
    interval = 5
    start_days = 3  # 每月第x天开始执行策略
    end_days = 1     # 每月最后一个周五前x天执行平仓策略
    test_type = 1  # 1 = 回测  2=实盘

    short_rate = 1.3
    cover_rate = 0.4

    end_date = ""

    spread_pos = 0.0
    buy_algoid = ""
    sell_algoid = ""
    short_algoid = ""
    cover_algoid = ""

    parameters = [
        "max_pos",
        "trade_pos",
        "payup",
        "interval",
        "start_days",
        "end_days",
        "end_date",
        "short_rate",
        "cover_rate",
        "test_type",

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
        self.active_ask_price = self.spread.active_leg.ask_price
        self.bg = BarGenerator(self.on_spread_bar, 1, self.on_10min_bar)

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

    def on_spread_tick(self, tick: TickData):
        """
        Callback when new spread tick data is generated.
        """
        self.bg.update_tick(tick)
        # print(f"on_spread tick {self.bg.__dict__}")

    def on_10min_bar(self, bar: BarData):
        self.spread_pos = self.get_spread_pos()

        if not self.end_date:
            print("无截止日期参数  break")
            return

        if self.test_type == 1:
            time_now = bar.datetime
            print(f"in bar date")
        else:
            time_now = datetime.now()
            print(f"in time_now")

        date_parse = datetime.strptime(self.end_date, '%Y-%m-%d')

        self.active_ask_price = self.spread.active_leg.ask_price
        print(self.active_ask_price)

        """计算short_price 价格  使用 self.short_rate * active_legs.price"""
        if (time_now <= (date_parse - timedelta(days=self.end_days))):
            # 当在开单区间内执行正常逻辑
            # No position
            if not self.spread_pos:
                self.stop_close_algos()
                if not self.short_algoid:
                    print(f"short_price {self.active_ask_price * (self.short_rate / 100)}")
                    self.short_algoid = self.start_short_algo(
                        self.active_ask_price * (self.short_rate / 100), self.trade_pos, self.payup, self.interval,
                        self.short_rate
                    )
            elif self.spread_pos < 0 and abs(self.max_pos) >= abs(self.spread_pos):
                # 有仓位没到最大值
                self.stop_close_algos()
                if not self.short_algoid:
                    print(f"short_price {self.active_ask_price * (self.short_rate / 100)}")
                    self.short_algoid = self.start_short_algo(
                        self.active_ask_price * (self.short_rate / 100), self.trade_pos, self.payup, self.interval,
                        self.short_rate
                    )
            # Short position 只做收敛
            elif self.spread_pos < 0 and abs(self.max_pos) <= abs(self.spread_pos):
                self.stop_open_algos()
                # Start cover close algo
                print( self.max_pos, self.spread_pos, abs(self.max_pos) >= abs(self.spread_pos))
                print(f"cover_price {self.active_ask_price, self.cover_rate} {self.active_ask_price * (self.cover_rate / 100)}")
                """计算cover_price 使用self.cover_rate * active_leg.price"""
                if not self.cover_algoid:
                    self.cover_algoid = self.start_long_algo(
                        self.active_ask_price * (self.cover_rate / 100), abs(
                            self.spread_pos), self.payup, self.interval, self.cover_rate
                    )

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
                            self.spread_pos), self.payup, self.interval,  self.cover_rate
                    )
                    # if self.cover_algoid:
                    #     print(f" 强制平仓时间 {time_now}")

            elif self.spread_pos == 0:
                self.stop_open_algos()
                self.stop_close_algos()
                # print(f"仅ing平仓 无 仓位  {time_now} ")
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
        # print(f"algo is active() {algo.__dict__} {algo.is_active()}")
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
