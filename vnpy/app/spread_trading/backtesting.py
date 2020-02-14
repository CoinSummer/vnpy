from collections import defaultdict
from datetime import date, datetime
from threading import Thread
from typing import Callable, Type

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pandas import DataFrame
from queue import Queue, Empty

import heapq

from vnpy.trader.constant import (Direction, Offset, Exchange,
                                  Interval, Status)
from vnpy.trader.object import TradeData, BarData, TickData

from .template import SpreadStrategyTemplate, SpreadAlgoTemplate
from .base import SpreadData, BacktestingMode, load_bar_data, load_tick_data, EngineType


# 添加引用
from deap import creator, base, tools, algorithms
from vnpy.trader.utility import round_to
from itertools import product
from functools import lru_cache
from time import time
import multiprocessing
import random
from vnpy.trader.database import database_manager


sns.set_style("whitegrid")

# creatior base
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
creator.create("Individual", list, fitness=creator.FitnessMax)

class OptimizationSetting:
    """
    Setting for runnning optimization.
    """

    def __init__(self):
        """"""
        self.params = {}
        self.target_name = ""

    def add_parameter(
        self, name: str, start: float, end: float = None, step: float = None
    ):
        """"""
        if not end and not step:
            self.params[name] = [start]
            return

        if start >= end:
            print("参数优化起始点必须小于终止点")
            return

        if step <= 0:
            print("参数优化步进必须大于0")
            return

        value = start
        value_list = []

        while value <= end:
            value_list.append(value)
            value += step

        self.params[name] = value_list

    def set_target(self, target_name: str):
        """"""
        self.target_name = target_name

    def generate_setting(self):
        """"""
        keys = self.params.keys()
        values = self.params.values()
        products = list(product(*values))

        settings = []
        for p in products:
            setting = dict(zip(keys, p))
            settings.append(setting)

        return settings

    def generate_setting_ga(self):
        """"""
        settings_ga = []
        settings = self.generate_setting()
        for d in settings:
            param = [tuple(i) for i in d.items()]
            settings_ga.append(param)
        return settings_ga



class BacktestingEngine:
    """"""

    gateway_name = "BACKTESTING"
    # 添加回撤模块
    # engine_type = EngineType.BACKTESTING

    DISPLAY_NAME_MAP = {
        "总收益率": "total_return",
        "夏普比率": "sharpe_ratio",
        "收益回撤比": "return_drawdown_ratio",
        "日均盈亏": "daily_net_pnl"
    }
    def __init__(self):
        """"""
        self.spread: SpreadData = None

        self.start = None
        self.end = None
        self.rate = 0
        self.slippage = 0
        self.size = 1
        self.pricetick = 0
        self.capital = 1_000_000
        self.mode = BacktestingMode.BAR

        self.strategy_class: Type[SpreadStrategyTemplate] = None
        self.strategy: SpreadStrategyTemplate = None
        self.tick: TickData = None
        self.bar: BarData = None
        self.datetime = None

        self.interval = None
        self.days = 0
        self.callback = None
        self.history_data = []

        self.algo_count = 0
        self.algos = {}
        self.active_algos = {}

        self.trade_count = 0
        self.trades = {}
        self.orders = {}

        self.logs = []

        self.daily_results = {}
        self.daily_df = None

        self.inverse = False

        self.spread_datas = []
        self.queue = Queue(11)

        self.heap = MidFinder()

    def output(self, msg):
        """
        Output message of backtesting engine.
        """
        print(f"{datetime.now()}\t{msg}")

    def clear_data(self):
        """
        Clear all data of last backtesting.
        """
        self.strategy = None
        self.tick = None
        self.bar = None
        self.datetime = None

        self.algo_count = 0
        self.algos.clear()
        self.active_algos.clear()

        self.trade_count = 0
        self.trades.clear()

        self.logs.clear()
        self.daily_results.clear()

    def set_parameters(
        self,
        spread: SpreadData,
        interval: Interval,
        start: datetime,
        rate: float,
        slippage: float,
        size: float,
        pricetick: float,
        capital: int = 0,
        end: datetime = None,
        mode: BacktestingMode = BacktestingMode.BAR
    ):
        """"""
        self.spread = spread
        self.interval = Interval(interval)
        self.rate = rate
        self.slippage = slippage
        self.size = size
        self.pricetick = pricetick
        self.start = start
        self.capital = capital
        self.end = end
        self.mode = mode

    def add_strategy(self, strategy_class: type, setting: dict):
        """"""
        self.strategy_class = strategy_class

        self.strategy = strategy_class(
            self,
            strategy_class.__name__,
            self.spread,
            setting
        )

    def load_data(self):
        """"""
        self.output("开始加载历史数据")

        if not self.end:
            self.end = datetime.now()

        if self.start >= self.end:
            self.output("起始日期必须小于结束日期")
            return

        if self.mode == BacktestingMode.BAR:
            self.history_data = load_bar_data(
                self.spread,
                self.interval,
                self.start,
                self.end,
                self.pricetick
            )
        else:
            self.history_datas = load_tick_data(
                self.spread,
                self.start,
                self.end
            )

        self.output(f"历史数据加载完成，数据量：{len(self.history_data)}")

    def run_backtesting(self):
        """"""
        if self.mode == BacktestingMode.BAR:
            func = self.new_bar
        else:
            func = self.new_tick

        self.strategy.on_init()

        # Use the first [days] of history data for initializing strategy
        day_count = 0
        ix = 0

        for ix, data in enumerate(self.history_data):
            if self.datetime and data.datetime.day != self.datetime.day:
                day_count += 1
                if day_count >= self.days:
                    break

            self.datetime = data.datetime
            self.callback(data)

        self.strategy.inited = True
        self.output("策略初始化完成")

        self.strategy.on_start()
        self.strategy.trading = True
        self.output("开始回放历史数据")

        # Use the rest of history data for running backtesting
        for data in self.history_data[ix:]:
            func(data)

        self.output("历史数据回放结束")

    def calculate_result(self):
        """"""
        self.output("开始计算逐日盯市盈亏")

        if not self.trades:
            self.output("成交记录为空，无法计算")
            return

        # Add trade data into daily reuslt.
        for trade in self.trades.values():
            d = trade.datetime.date()
            daily_result = self.daily_results[d]
            daily_result.add_trade(trade)

        # Calculate daily result by iteration.
        pre_close = 0
        start_pos = 0

        for daily_result in self.daily_results.values():
            # print(f"daily reault {daily_result.__dict__}")
            daily_result.calculate_pnl(
                pre_close,
                start_pos,
                self.size,
                self.rate,
                self.slippage
            )

            pre_close = daily_result.close_price
            start_pos = daily_result.end_pos

        # Generate dataframe
        results = defaultdict(list)

        for daily_result in self.daily_results.values():
            for key, value in daily_result.__dict__.items():
                results[key].append(value)

        self.daily_df = DataFrame.from_dict(results).set_index("date")

        self.output("逐日盯市盈亏计算完成")
        return self.daily_df

    def calculate_statistics(self, df: DataFrame = None, output=True):
        """"""
        self.output("开始计算策略统计指标")

        # Check DataFrame input exterior
        if df is None:
            df = self.daily_df

        # Check for init DataFrame
        if df is None:
            # Set all statistics to 0 if no trade.
            start_date = ""
            end_date = ""
            total_days = 0
            profit_days = 0
            loss_days = 0
            end_balance = 0
            max_drawdown = 0
            max_ddpercent = 0
            max_drawdown_duration = 0
            total_net_pnl = 0
            daily_net_pnl = 0
            total_commission = 0
            daily_commission = 0
            total_slippage = 0
            daily_slippage = 0
            total_turnover = 0
            daily_turnover = 0
            total_trade_count = 0
            daily_trade_count = 0
            total_return = 0
            annual_return = 0
            daily_return = 0
            return_std = 0
            sharpe_ratio = 0
            return_drawdown_ratio = 0
        else:
            # Calculate balance related time series data
            df["balance"] = df["net_pnl"].cumsum() + self.capital
            df["return"] = np.log(df["balance"] / df["balance"].shift(1)).fillna(0)
            df["highlevel"] = (
                df["balance"].rolling(
                    min_periods=1, window=len(df), center=False).max()
            )
            df["drawdown"] = df["balance"] - df["highlevel"]
            df["ddpercent"] = df["drawdown"] / df["highlevel"] * 100

            # Calculate statistics value
            start_date = df.index[0]
            end_date = df.index[-1]

            total_days = len(df)
            profit_days = len(df[df["net_pnl"] > 0])
            loss_days = len(df[df["net_pnl"] < 0])

            end_balance = df["balance"].iloc[-1]
            max_drawdown = df["drawdown"].min()
            max_ddpercent = df["ddpercent"].min()
            max_drawdown_end = df["drawdown"].idxmin()
            max_drawdown_start = df["balance"][:max_drawdown_end].argmax()
            max_drawdown_duration = (max_drawdown_end - max_drawdown_start).days

            total_net_pnl = df["net_pnl"].sum()
            daily_net_pnl = total_net_pnl / total_days

            total_commission = df["commission"].sum()
            daily_commission = total_commission / total_days

            total_slippage = df["slippage"].sum()
            daily_slippage = total_slippage / total_days

            total_turnover = df["turnover"].sum()
            daily_turnover = total_turnover / total_days

            total_trade_count = df["trade_count"].sum()
            daily_trade_count = total_trade_count / total_days

            total_return = (end_balance / self.capital - 1) * 100
            annual_return = total_return / total_days * 240
            daily_return = df["return"].mean() * 100
            return_std = df["return"].std() * 100

            if return_std:
                sharpe_ratio = daily_return / return_std * np.sqrt(240)
            else:
                sharpe_ratio = 0

            return_drawdown_ratio = -total_return / max_ddpercent

        # Output
        if output:
            self.output("-" * 30)
            self.output(f"首个交易日：\t{start_date}")
            self.output(f"最后交易日：\t{end_date}")

            self.output(f"总交易日：\t{total_days}")
            self.output(f"盈利交易日：\t{profit_days}")
            self.output(f"亏损交易日：\t{loss_days}")

            self.output(f"起始资金：\t{self.capital:,.2f}")
            self.output(f"结束资金：\t{end_balance:,.2f}")

            self.output(f"总收益率：\t{total_return:,.2f}%")
            self.output(f"年化收益：\t{annual_return:,.2f}%")
            self.output(f"最大回撤: \t{max_drawdown:,.2f}")
            self.output(f"百分比最大回撤: {max_ddpercent:,.2f}%")
            self.output(f"最长回撤天数: \t{max_drawdown_duration}")

            self.output(f"总盈亏：\t{total_net_pnl:,.2f}")
            self.output(f"总手续费：\t{total_commission:,.2f}")
            self.output(f"总滑点：\t{total_slippage:,.2f}")
            self.output(f"总成交金额：\t{total_turnover:,.2f}")
            self.output(f"总成交笔数：\t{total_trade_count}")

            self.output(f"日均盈亏：\t{daily_net_pnl:,.2f}")
            self.output(f"日均手续费：\t{daily_commission:,.2f}")
            self.output(f"日均滑点：\t{daily_slippage:,.2f}")
            self.output(f"日均成交金额：\t{daily_turnover:,.2f}")
            self.output(f"日均成交笔数：\t{daily_trade_count}")

            self.output(f"日均收益率：\t{daily_return:,.2f}%")
            self.output(f"收益标准差：\t{return_std:,.2f}%")
            self.output(f"Sharpe Ratio：\t{sharpe_ratio:,.2f}")
            self.output(f"收益回撤比：\t{return_drawdown_ratio:,.2f}")

        statistics = {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total_days,
            "profit_days": profit_days,
            "loss_days": loss_days,
            "capital": self.capital,
            "end_balance": end_balance,
            "max_drawdown": max_drawdown,
            "max_ddpercent": max_ddpercent,
            "max_drawdown_duration": max_drawdown_duration,
            "total_net_pnl": total_net_pnl,
            "daily_net_pnl": daily_net_pnl,
            "total_commission": total_commission,
            "daily_commission": daily_commission,
            "total_slippage": total_slippage,
            "daily_slippage": daily_slippage,
            "total_turnover": total_turnover,
            "daily_turnover": daily_turnover,
            "total_trade_count": total_trade_count,
            "daily_trade_count": daily_trade_count,
            "total_return": total_return,
            "annual_return": annual_return,
            "daily_return": daily_return,
            "return_std": return_std,
            "sharpe_ratio": sharpe_ratio,
            "return_drawdown_ratio": return_drawdown_ratio,
        }

        return statistics

    def show_chart(self, df: DataFrame = None):
        """"""
        # Check DataFrame input exterior
        if df is None:
            df = self.daily_df

        # Check for init DataFrame
        if df is None:
            return

        plt.figure(figsize=(10, 16))

        balance_plot = plt.subplot(4, 1, 1)
        balance_plot.set_title("Balance")
        df["balance"].plot(legend=True)
        drawdown_plot = plt.subplot(4, 1, 2)
        drawdown_plot.set_title("Drawdown")
        drawdown_plot.fill_between(range(len(df)), df["drawdown"].values)


        pnl_plot = plt.subplot(4, 1, 3)
        pnl_plot.set_title("Daily Pnl")
        df["net_pnl"].plot(kind="bar", legend=False, grid=False, xticks=[])

        distribution_plot = plt.subplot(4, 1, 4)
        distribution_plot.set_title("Daily Pnl Distribution")
        df["net_pnl"].hist(bins=50)

        plt.show()

    def update_daily_close(self, price: float):
        """"""
        d = self.datetime.date()

        daily_result = self.daily_results.get(d, None)
        if daily_result:
            daily_result.close_price = price
        else:
            self.daily_results[d] = DailyResult(d, price)

    def new_bar(self, bar: BarData):
        """"""
        self.bar = bar
        self.datetime = bar.datetime
        self.cross_algo()

        self.strategy.on_spread_bar(bar)

        self.update_daily_close(bar.close_price)

    def new_tick(self, tick: TickData):
        """"""
        self.tick = tick
        self.datetime = tick.datetime
        self.cross_algo()

        self.spread.bid_price = tick.bid_price_1
        self.spread.bid_volume = tick.bid_volume_1
        self.spread.ask_price = tick.ask_price_1
        self.spread.ask_volume = tick.ask_volume_1

        self.strategy.on_spread_data()

        self.update_daily_close(tick.last_price)

    def cal_filter(self, arr):
        """
        计算四分位上下限 过滤异常差价波动
        return [上限， 下限]
        """
        # print(f"arr {arr} len {len(arr)}")
        if len(arr) < 2:
            return [0,0]
        # q1 = np.quantile(arr, 0.25, interpolation='lower')  # 下四分位数
        # q3 = np.quantile(arr, 0.75, interpolation='higher')  # 上四分位数

        q = np.quantile(arr, [0.25, 0.75])
        q3 = q[1]
        q1 = q[0]
        iqr = q3 - q1

        return [ (q1 - 1.5*iqr), (q3 - 1.5*iqr)] # 下限 上线

    def cal_std_stream(self, data):

        """绝对中位差计算上下限"""
        start = datetime.now()

        heap = MidFinder()
        for d in data:
            heap.insert(d)
        median = np.float64(heap.getMedian())
        end = datetime.now()

        b = 1.4826

        m_start = datetime.now()
        mad_base = np.abs(data - median)
        m_end = datetime.now()
        # print(f" abs计算用时 {round((m_end-m_start).microseconds,5)}ms")

        b_start = datetime.now()
        mad_heap = MidFinder()
        f_start = datetime.now()
        for x in mad_base:
            o_start = datetime.now()
            mad_heap.insert(x)
            o_end = datetime.now()
        f_end = datetime.now()
        mad = np.float64(mad_heap.getMedian())
        b_end = datetime.now()
        # print(f"首次中位数 {round((end-start).microseconds,5)}ms , abs 计算{round((m_end-m_start).microseconds,5)}ms, "
        #       f"二次中位数计算 {round((b_end-b_start).microseconds,5)}ms mad{mad}, 循环用时 {round((f_end-f_start).microseconds,5)}ms ")
        lower_limit = median - (1.5 * b * mad)
        upper_limit = median + (1.5 * b * mad)
        return [lower_limit, upper_limit]

    def cal_std(self, data):

        """绝对中位差计算上下限"""
        median = np.median(data)

        b = 1.4826  # 这个值应该是看需求加的，有点类似加大波动范围之类的
        # b = 1.2  # 这个值应该是看需求加的，有点类似加大波动范围之类的
        mad = b * np.median(np.abs(data - median))

        lower_limit = median - (3 * b * mad)
        upper_limit = median + (3 * b * mad)
        return [lower_limit, upper_limit]

    def cal_three_sigma(self,data):
        mean = np.mean(data)
        std = np.std(data)
        # 左右3 个标准差
        lower = mean - (3 * std)
        upper = mean + (3 * std)
        return [lower, upper]

    def cross_algo(self):
        """
        Cross limit order with last bar/tick data.
        """
        if self.mode == BacktestingMode.BAR:
            long_cross_price = self.bar.close_price
            short_cross_price = self.bar.close_price
            cross_rate = self.bar.spread_rate

        else:
            long_cross_price = self.tick.ask_price_1
            short_cross_price = self.tick.bid_price_1
            cross_rate = self.bar.spread_rate

        if len(self.spread_datas) == 17:
            self.spread_datas.pop(0)
            self.spread_datas.append(cross_rate)
            # print(self.spread_datas)
        else:
            self.spread_datas.append(cross_rate)

        # if len(self.queue.queue) == 11:
        #     self.queue.get()
        #     self.queue.put(cross_rate)
        # else:
        #     self.queue.put(cross_rate)


        # # 使用堆计算中位数
        # h_start = datetime.now()
        #
        # self.heap.insert(cross_rate)
        # d = self.heap.getMedian()
        # h_end= datetime.now()
        # if len(self.heap.max_heap) + len(self.heap.min_heap) > 100:
        #     self.heap.clear()
        # h_cost = (h_end - h_start)
        # print(f" 堆计算四分位 {d} 当前cross_rate {cross_rate}  用时 {round(h_cost.microseconds,5)}ms len{len(self.heap.max_heap) + len(self.heap.min_heap)}")

        # # 使用四分位上下限计算
        # c_start = datetime.now()
        # cal_spread_limit = self.cal_filter(self.spread_datas)
        # # cal_spread_limit = self.cal_filter(list(self.queue.queue))
        # # # cal_long_limit = self.cal_filter(self.spread_datas["long_cross_price"])
        # # # cal_short_limit = self.cal_filter(self.spread_datas["short_cross_price"])
        # # cal_spread_limit = self.cal_std(self.spread_datas)
        # c_end = datetime.now()
        # c_cost = (c_end - c_start)
        # # print(f"{self.bar.datetime}数据 {self.spread_datas} 中位差 {cal_spread_limit}  当前cross_rate {cross_rate}")
        # print(f"{self.bar.datetime}用时 {round(c_cost.microseconds, 5)}ms  四分位计算 {cal_spread_limit}  当前cross_rate {cross_rate} ")
        #

        # 使用流 中位数绝对值

        x_start = datetime.now()
        x_cal_spread_limit = self.cal_std_stream(self.spread_datas)
        x_end = datetime.now()
        x_cost = (x_end - x_start)
        # print(f"{self.bar.datetime}用时 {round(x_cost.microseconds, 5)}ms 流中位数绝对值计算 {x_cal_spread_limit}  当前cross_rate {cross_rate} ")

        # # 使用中位数绝对值偏差
        # m_start = datetime.now()
        # m_cal_spread_limit = self.cal_std(self.spread_datas)
        # m_end = datetime.now()
        # m_cost = (m_end - m_start)
        # # print(f"{self.bar.datetime}数据 {self.spread_datas} 中位差 {cal_spread_limit}  当前cross_rate {cross_rate}")
        # print(f"{self.bar.datetime}数据  中位数绝对值计算 {m_cal_spread_limit}  当前cross_rate {cross_rate} 用时 {round(m_cost.microseconds, 5)}ms")
        #
        # # 使用3 sigmal
        # s_start = datetime.now()
        # s_cal_spread_limit = self.cal_three_sigma(self.spread_datas)
        # s_end = datetime.now()
        # s_cost = s_end - s_start
        # print(f"{self.bar.datetime}数据  sigmal计算 {s_cal_spread_limit}  当前cross_rate {cross_rate} 用时 {round(s_cost.microseconds, 5)}ms")
        #
        #


        # print(f"cross algo {self.bar.__dict__}")
        for algo in list(self.active_algos.values()):
            # Check whether limit orders can be filled.
            # print(f"algo value {algo.__dict__}")
            # print(f"[algo info]  {algo.__dict__} {cross_rate} {long_cross_price}")

            if algo.spread_rate == 0:

                long_cross = (
                    algo.direction == Direction.LONG
                    and algo.price >= long_cross_price
                    and long_cross_price > 0
                    # and long_cross_price < cal_long_limit[1]
                    # and long_cross_price > cal_long_limit[0]
                )

                short_cross = (
                    algo.direction == Direction.SHORT
                    and algo.price <= short_cross_price
                    and short_cross_price > 0
                    # and short_cross_price < cal_short_limit[1]
                    # and short_cross_price > cal_short_limit[0]
                )
            else:

                # if not (cross_rate > cal_spread_limit[0] and cross_rate < cal_spread_limit[1]):
                if not (cross_rate > x_cal_spread_limit[0] and cross_rate < x_cal_spread_limit[1]):
                        continue

                long_cross = (
                        algo.direction == Direction.LONG
                        # and algo.price >= long_cross_price
                        and long_cross_price > 0
                        and algo.spread_rate >= cross_rate
                )

                # print(f"long cross {long_cross} {algo.direction} {algo.price} {long_cross_price}  {algo.spread_rate} {cross_rate}")

                short_cross = (
                        algo.direction == Direction.SHORT
                        # and algo.price <= short_cross_price
                        and short_cross_price > 0
                        and algo.spread_rate <= cross_rate
                )
                # print(f"short cross {short_cross} {algo.direction} {algo.price} {short_cross_price}  {algo.spread_rate} {cross_rate}")

            if not long_cross and not short_cross:
                continue

            # Push order udpate with status "all traded" (filled).
            algo.traded = algo.volume
            algo.status = Status.ALLTRADED
            self.strategy.update_spread_algo(algo)

            self.active_algos.pop(algo.algoid)

            # Push trade update
            self.trade_count += 1

            if long_cross:
                trade_price = long_cross_price
                pos_change = algo.volume
            else:
                trade_price = short_cross_price
                pos_change = -algo.volume

            trade = TradeData(
                symbol=self.spread.name,
                exchange=Exchange.LOCAL,
                orderid=algo.algoid,
                tradeid=str(self.trade_count),
                direction=algo.direction,
                offset=algo.offset,
                price=trade_price,
                volume=algo.volume,
                time=self.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                gateway_name=self.gateway_name,
                spread_rate=self.bar.spread_rate


            )
            trade.datetime = self.datetime

            if self.mode == BacktestingMode.BAR:
                trade.value = self.bar.value
            else:
                trade.value = trade_price

            self.spread.net_pos += pos_change
            self.strategy.on_spread_pos()

            self.trades[trade.vt_tradeid] = trade

    def load_bar(
        self, spread: SpreadData, days: int, interval: Interval, callback: Callable
    ):
        """"""
        self.days = days
        self.callback = callback

    def load_tick(self, spread: SpreadData, days: int, callback: Callable):
        """"""
        self.days = days
        self.callback = callback

    def start_algo(
        self,
        strategy: SpreadStrategyTemplate,
        spread_name: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        payup: float,
        interval: int,
        lock: bool,
        spread_rate: float,

    ) -> str:
        """"""
        self.algo_count += 1
        algoid = str(self.algo_count)

        algo = SpreadAlgoTemplate(
            self,
            algoid,
            self.spread,
            direction,
            offset,
            price,
            volume,
            payup,
            interval,
            lock,
            spread_rate
        )
        # print(f"[start_algo] {algo.spread.__dict__}")
        self.algos[algoid] = algo
        self.active_algos[algoid] = algo

        return algoid

    def stop_algo(
        self,
        strategy: SpreadStrategyTemplate,
        algoid: str
    ):
        """"""
        if algoid not in self.active_algos:
            return
        algo = self.active_algos.pop(algoid)

        algo.status = Status.CANCELLED
        self.strategy.update_spread_algo(algo)

    def send_order(
        self,
        strategy: SpreadStrategyTemplate,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        stop: bool,
        lock: bool
    ):
        """"""
        pass

    def cancel_order(self, strategy: SpreadStrategyTemplate, vt_orderid: str):
        """
        Cancel order by vt_orderid.
        """
        pass

    def write_strategy_log(self, strategy: SpreadStrategyTemplate, msg: str):
        """
        Write log message.
        """
        msg = f"{self.datetime}\t{msg}"
        self.logs.append(msg)

    def send_email(self, msg: str, strategy: SpreadStrategyTemplate = None):
        """
        Send email to default receiver.
        """
        pass

    def put_strategy_event(self, strategy: SpreadStrategyTemplate):
        """
        Put an event to update strategy status.
        """
        pass

    def write_algo_log(self, algo: SpreadAlgoTemplate, msg: str):
        """"""
        pass

    def run_optimization(self, optimization_setting: OptimizationSetting, output=True):
        """"""
        # Get optimization setting and target
        settings = optimization_setting.generate_setting()
        target_name = optimization_setting.target_name

        if not settings:
            self.output("优化参数组合为空，请检查")
            return

        if not target_name:
            self.output("优化目标未设置，请检查")
            return

        # Use multiprocessing pool for running backtesting with different setting
        pool = multiprocessing.Pool(multiprocessing.cpu_count())

        results = []
        for setting in settings:
            result = (pool.apply_async(optimize, (
                target_name,
                self.strategy_class,
                setting,
                self.spread,
                self.interval,
                self.start,
                self.rate,
                self.slippage,
                self.size,
                self.pricetick,
                self.capital,
                self.end,
                self.mode,
                # self.inverse
            )))
            results.append(result)

        pool.close()
        pool.join()

        # Sort results and output
        result_values = [result.get() for result in results]
        result_values.sort(reverse=True, key=lambda result: result[1])

        if output:
            for value in result_values:
                msg = f"参数：{value[0]}, 目标：{value[1]}"
                self.output(msg)

        return result_values

    def run_ga_optimization(self, optimization_setting: OptimizationSetting, population_size=100, ngen_size=30, output=True):
        """"""
        # Get optimization setting and target
        settings = optimization_setting.generate_setting_ga()
        target_name = optimization_setting.target_name
        if not settings:
            self.output("优化参数组合为空，请检查")
            return

        if not target_name:
            self.output("优化目标未设置，请检查")
            return

        # Define parameter generation function
        def generate_parameter():
            """"""
            return random.choice(settings)

        def mutate_individual(individual, indpb):
            """"""
            size = len(individual)
            paramlist = generate_parameter()
            for i in range(size):
                if random.random() < indpb:
                    individual[i] = paramlist[i]
            return individual,

        # Create ga object function
        global ga_target_name
        global ga_strategy_class
        global ga_setting
        global ga_vt_symbol
        global ga_interval
        global ga_start
        global ga_rate
        global ga_slippage
        global ga_size
        global ga_pricetick
        global ga_capital
        global ga_end
        global ga_mode
        global ga_inverse

        ga_target_name = target_name
        ga_strategy_class = self.strategy_class
        ga_setting = settings[0]
        # ga_vt_symbol = self.vt_symbol
        ga_vt_symbol = self.spread

        ga_interval = self.interval
        ga_start = self.start
        ga_rate = self.rate
        ga_slippage = self.slippage
        ga_size = self.size
        ga_pricetick = self.pricetick
        ga_capital = self.capital
        ga_end = self.end
        ga_mode = self.mode
        ga_inverse = self.inverse

        # Set up genetic algorithem
        toolbox = base.Toolbox()
        toolbox.register("individual", tools.initIterate, creator.Individual, generate_parameter)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("mate", tools.cxTwoPoint)
        toolbox.register("mutate", mutate_individual, indpb=1)
        toolbox.register("evaluate", ga_optimize)
        toolbox.register("select", tools.selNSGA2)

        total_size = len(settings)
        pop_size = population_size                      # number of individuals in each generation
        lambda_ = pop_size                              # number of children to produce at each generation
        mu = int(pop_size * 0.8)                        # number of individuals to select for the next generation

        cxpb = 0.95         # probability that an offspring is produced by crossover
        mutpb = 1 - cxpb    # probability that an offspring is produced by mutation
        ngen = ngen_size    # number of generation

        pop = toolbox.population(pop_size)
        hof = tools.ParetoFront()               # end result of pareto front

        stats = tools.Statistics(lambda ind: ind.fitness.values)
        np.set_printoptions(suppress=True)
        stats.register("mean", np.mean, axis=0)
        stats.register("std", np.std, axis=0)
        stats.register("min", np.min, axis=0)
        stats.register("max", np.max, axis=0)

        # Multiprocessing is not supported yet.
        # pool = multiprocessing.Pool(multiprocessing.cpu_count())
        # toolbox.register("map", pool.map)

        # Run ga optimization
        self.output(f"参数优化空间：{total_size}")
        self.output(f"每代族群总数：{pop_size}")
        self.output(f"优良筛选个数：{mu}")
        self.output(f"迭代次数：{ngen}")
        self.output(f"交叉概率：{cxpb:.0%}")
        self.output(f"突变概率：{mutpb:.0%}")

        start = time()

        algorithms.eaMuPlusLambda(
            pop,
            toolbox,
            mu,
            lambda_,
            cxpb,
            mutpb,
            ngen,
            stats,
            halloffame=hof
        )

        end = time()
        cost = int((end - start))

        self.output(f"遗传算法优化完成，耗时{cost}秒")

        # Return result list
        results = []

        for parameter_values in hof:
            s = datetime.now()

            setting = dict(parameter_values)
            target_value = ga_optimize(parameter_values)[0]
            results.append((setting, target_value, {}))
            e = datetime.now()
            print(f"ga time {e-s}")
        return results


    def start_optimization(
        self,
        class_name: str,
        vt_symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        rate: float,
        slippage: float,
        size: int,
        pricetick: float,
        capital: int,
        inverse: bool,
        optimization_setting: OptimizationSetting,
        use_ga: bool
    ):
        if self.thread:
            self.write_log("已有任务在运行中，请等待完成")
            return False

        self.write_log("-" * 40)
        self.thread = Thread(
            target=self.run_optimization,
            args=(
                class_name,
                vt_symbol,
                interval,
                start,
                end,
                rate,
                slippage,
                size,
                pricetick,
                capital,
                inverse,
                optimization_setting,
                use_ga
            )
        )
        self.thread.start()

        return True




class DailyResult:
    """"""

    def __init__(self, date: date, close_price: float):
        """"""
        self.date = date
        self.close_price = close_price
        self.pre_close = 0

        self.trades = []
        self.trade_count = 0

        self.start_pos = 0
        self.end_pos = 0

        self.turnover = 0
        self.commission = 0
        self.slippage = 0

        self.trading_pnl = 0
        self.holding_pnl = 0
        self.total_pnl = 0
        self.net_pnl = 0

    def add_trade(self, trade: TradeData):
        """"""
        self.trades.append(trade)

    def calculate_pnl(
        self,
        pre_close: float,
        start_pos: float,
        size: int,
        rate: float,
        slippage: float
    ):
        """"""
        # If no pre_close provided on the first day,
        # use value 1 to avoid zero division error
        if pre_close:
            self.pre_close = pre_close
        else:
            self.pre_close = 1

        # Holding pnl is the pnl from holding position at day start
        self.start_pos = start_pos
        self.end_pos = start_pos

        self.holding_pnl = self.start_pos * (self.close_price - self.pre_close) * size

        # Trading pnl is the pnl from new trade during the day
        self.trade_count = len(self.trades)

        for trade in self.trades:
            if trade.direction == Direction.LONG:
                pos_change = trade.volume
            else:
                pos_change = -trade.volume

            self.end_pos += pos_change

            turnover = trade.volume * size * trade.value
            self.trading_pnl += pos_change * \
                (self.close_price - trade.price) * size
            self.slippage += trade.volume * size * slippage

            self.turnover += turnover
            self.commission += turnover * rate

        # Net pnl takes account of commission and slippage cost
        self.total_pnl = self.trading_pnl + self.holding_pnl
        self.net_pnl = self.total_pnl - self.commission - self.slippage

class QuartileFinder:
    def __init__(self):
        self.min_heap = []
        self.max_heap = []
        self.count = 0

    def insert(self, num):
        """
        :type num: int
        :rtype: void
        """
        # 当前是奇数的时候，直接"最小堆" -> "最大堆"，就可以了
        # 此时"最小堆" 与 "最大堆" 的元素数组是相等的

        # 当前是偶数的时候，"最小堆" -> "最大堆"以后，最终我们要让"最小堆"多一个元素
        # 所以应该让 "最大堆" 拿出一个元素给 "最小堆"

        heapq.heappush(self.min_heap, num)
        temp = heapq.heappop(self.min_heap)
        heapq.heappush(self.max_heap, -temp)
        if self.count & 1 == 0:
            temp = -heapq.heappop(self.max_heap)
            heapq.heappush(self.min_heap, temp)
        self.count += 1
        # print(f" min {self.min_heap}")
        # print(f"max {self.max_heap}")

    def getMedian(self):
        """
        :rtype: float
        """
        if self.count & 1 == 1:
            mid = self.min_heap[0]
        else:
            mid = (self.min_heap[0] + (-self.max_heap[0])) / 2
        return mid

class MidFinder:

    def __init__(self):
        self.min_heap = []
        self.max_heap = []
        self.count = 0

    def insert(self, num):
        """
        :type num: int
        :rtype: void
        """
        # 当前是奇数的时候，直接"最小堆" -> "最大堆"，就可以了
        # 此时"最小堆" 与 "最大堆" 的元素数组是相等的

        # 当前是偶数的时候，"最小堆" -> "最大堆"以后，最终我们要让"最小堆"多一个元素
        # 所以应该让 "最大堆" 拿出一个元素给 "最小堆"

        heapq.heappush(self.min_heap, num)
        temp = heapq.heappop(self.min_heap)
        heapq.heappush(self.max_heap, -temp)
        if self.count & 1 == 0:
            temp = -heapq.heappop(self.max_heap)
            heapq.heappush(self.min_heap, temp)
        self.count += 1
        # print(f" min {self.min_heap}")
        # print(f"max {self.max_heap}")
    def get_heap_all(self):
        return self.min_heap + self.max_heap
    def get_lower_quartile(self):
        pass
    def getMedian(self):
        """
        :rtype: float
        """
        if self.count & 1 == 1:
            mid = self.min_heap[0]
        else:
            mid = (self.min_heap[0] + (-self.max_heap[0])) / 2
        #
        # if self.count & 1 == 1:
        #     mad_mid = np.abs(self.min_heap - np.float64(mid))[0]
        # else:
        #     mad_mid = ( np.abs(self.min_heap - np.float64(mid))[0] + (-np.abs(self.max_heap - np.float64(mid))[0])) / 2
        #
        #
        # print(f"cal mad_mid {mad_mid}")
        return mid

    def clear(self):
        self.min_heap = []
        self.max_heap = []
        self.count = 0


def optimize(
    target_name: str,
    strategy_class: SpreadStrategyTemplate,
    setting: dict,
    # vt_symbol: str,
    spread: SpreadData,
    interval: Interval,
    start: datetime,
    rate: float,
    slippage: float,
    size: float,
    pricetick: float,
    capital: int,
    end: datetime,
    mode: BacktestingMode,
    # inverse: bool
):
    """
    Function for running in multiprocessing.pool
    """
    engine = BacktestingEngine()

    engine.set_parameters(
        # vt_symbol=vt_symbol,
        spread=spread,
        interval=interval,
        start=start,
        rate=rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        capital=capital,
        end=end,
        mode=mode,
        # inverse=inverse
    )

    engine.add_strategy(strategy_class, setting)
    engine.load_data()
    engine.run_backtesting()
    engine.calculate_result()
    statistics = engine.calculate_statistics(output=False)

    target_value = statistics[target_name]
    return (str(setting), target_value, statistics)


@lru_cache(maxsize=1000000)
def _ga_optimize(parameter_values: tuple):
    """"""
    setting = dict(parameter_values)
    result = optimize(
        ga_target_name,
        ga_strategy_class,
        setting,
        ga_vt_symbol,
        ga_interval,
        ga_start,
        ga_rate,
        ga_slippage,
        ga_size,
        ga_pricetick,
        ga_capital,
        ga_end,
        ga_mode,
        # ga_inverse
    )
    return (result[1],)


def ga_optimize(parameter_values: list):
    """"""
    return _ga_optimize(tuple(parameter_values))





# GA related global value
ga_end = None
ga_mode = None
ga_target_name = None
ga_strategy_class = None
ga_setting = None
ga_vt_symbol = None
ga_interval = None
ga_start = None
ga_rate = None
ga_slippage = None
ga_size = None
ga_pricetick = None
ga_capital = None
