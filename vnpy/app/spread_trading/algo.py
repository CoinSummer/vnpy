from typing import Any

from vnpy.trader.constant import Direction, Offset
from vnpy.trader.object import (TickData, OrderData, TradeData)
from vnpy.trader.utility import round_to

from .template import SpreadAlgoTemplate
from .base import SpreadData

import numpy as np
import heapq


class SpreadTakerAlgo(SpreadAlgoTemplate):
    """"""
    algo_name = "SpreadTaker"

    def __init__(
        self,
        algo_engine: Any,
        algoid: str,
        spread: SpreadData,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        payup: float,
        interval: int,
        lock: bool,
        spread_rate: float
    ):
        """"""
        super().__init__(
            algo_engine, algoid, spread,
            direction, offset, price, volume,
            payup, interval, lock, spread_rate
        )

        self.cancel_interval: int = 2
        self.timer_count: int = 0
        self.spread_datas = []
        self.bid_spread_datas = []
        self.ask_spread_datas = []

    def cal_std_stream(self, data):

        """绝对中位差计算上下限 过滤异常数据"""

        heap = MidFinder()
        for d in data:
            heap.insert(d)
        median = np.float64(heap.getMedian())
        b = 1.4826
        mad_base = np.abs(data - median)

        mad_heap = MidFinder()
        for x in mad_base:
            mad_heap.insert(x)
        mad = np.float64(mad_heap.getMedian())

        lower_limit = median - (1.5 * b * mad)
        upper_limit = median + (1.5 * b * mad)

        return [lower_limit, upper_limit]

    def on_tick(self, tick: TickData):
        """"""
        # Return if tick not inited
        if not self.spread.bid_volume or not self.spread.ask_volume:
            return

        # Return if there are any existing orders
        if not self.check_order_finished():
            return

        # Hedge if active leg is not fully hedged
        if not self.check_hedge_finished():
            self.hedge_passive_legs()
            return

        # Otherwise check if should take active leg
        # print(f"on tick info {self.spread.__dict__}")
        if self.spread.trading_type == "price":


            if self.direction == Direction.LONG:
                if len(self.spread_datas) > 17:
                    self.ask_spread_datas.pop(0)
                    self.ask_spread_datas.append(self.spread.ask_price)
                else:
                    self.ask_spread_datas.append(self.spread.ask_price)

                # spread_std = np.std(self.spread_datas, ddof=1)
                cal_spread_limit = self.cal_std_stream(self.ask_spread_datas)

                if self.spread.ask_price <= self.price and (cal_spread_limit[0] <= self.price <= cal_spread_limit[1]):
                    self.take_active_leg()
            else:
                if len(self.spread_datas) > 17:
                    self.bid_spread_datas.pop(0)
                    self.bid_spread_datas.append(self.spread.bid_price)
                else:
                    self.bid_spread_datas.append(self.spread.bid_price)

                # spread_std = np.std(self.spread_datas, ddof=1)
                cal_spread_limit = self.cal_std_stream(self.bid_spread_datas)

                if self.spread.bid_price >= self.price and (cal_spread_limit[0] <= self.price <= cal_spread_limit[1]):
                    self.take_active_leg()
        else:
            # print(f" 使用 rate 交易 taker")
            """使用 spread rate 计算挂单差价"""
            # print("spread rate 使用 taker")
            # print(f"spread_rate {self.spread_rate} active_ask_price {active_leg.ask_price}  spread_ask_rate {self.spread.ask_spread_rate} bid_price {active_leg.bid_price} spread_bid_rate {spread.bid_spread_rate}")

            if self.direction == Direction.LONG:

                if len(self.ask_spread_datas) > 17:
                    self.ask_spread_datas.pop(0)
                    self.ask_spread_datas.append(self.spread.ask_spread_rate)
                else:
                    self.aks_spread_datas.append(self.spread.ask_spread_rate)
                # spread_std = np.std(self.spread_datas, ddof=1)
                cal_spread_limit = self.cal_std_stream(self.ask_spread_datas)

                if self.spread.ask_spread_rate <= self.spread_rate and (cal_spread_limit[0] <= self.price <= cal_spread_limit[1]):
                    self.take_active_leg()
            else:
                if len(self.spread_datas) > 17:
                    self.bid_spread_datas.pop(0)
                    self.bid_spread_datas.append(self.spread.bid_spread_rate)
                else:
                    self.bid_spread_datas.append(self.spread.bid_spread_rate)
                # spread_std = np.std(self.spread_datas, ddof=1)
                cal_spread_limit = self.cal_std_stream(self.ask_spread_datas)

                if self.spread.bid_spread_rate >= self.spread_rate and (cal_spread_limit[0] <= self.price <= cal_spread_limit[1] ):
                    self.take_active_leg()

    def on_order(self, order: OrderData):
        """"""
        # Only care active leg order update
        if order.vt_symbol != self.spread.active_leg.vt_symbol:
            return

        # Do nothing if still any existing orders
        if not self.check_order_finished():
            return

        # Hedge passive legs if necessary
        if not self.check_hedge_finished():
            self.hedge_passive_legs()

    def on_trade(self, trade: TradeData):
        """"""
        pass

    def on_interval(self):
        """"""
        if not self.check_order_finished():
            self.cancel_all_order()

    def take_active_leg(self):
        """"""
        # Calculate spread order volume of new round trade
        spread_volume_left = self.target - self.traded

        if self.direction == Direction.LONG:
            spread_order_volume = self.spread.ask_volume
            spread_order_volume = min(spread_order_volume, spread_volume_left)
        else:
            spread_order_volume = -self.spread.bid_volume
            spread_order_volume = max(spread_order_volume, spread_volume_left)

        # Calculate active leg order volume
        leg_order_volume = self.spread.calculate_leg_volume(
            self.spread.active_leg.vt_symbol,
            spread_order_volume
        )
        # Send active leg order
        self.send_leg_order(
            self.spread.active_leg.vt_symbol,
            leg_order_volume
        )

    def hedge_passive_legs(self):
        """
        Send orders to hedge all passive legs.
        """
        # Calcualte spread volume to hedge
        active_leg = self.spread.active_leg
        active_traded = self.leg_traded[active_leg.vt_symbol]
        active_traded = round_to(active_traded, self.spread.min_volume)

        hedge_volume = self.spread.calculate_spread_volume(
            active_leg.vt_symbol,
            active_traded
        )
        # Calculate passive leg target volume and do hedge
        for leg in self.spread.passive_legs:
            passive_traded = self.leg_traded[leg.vt_symbol]
            passive_traded = round_to(passive_traded, self.spread.min_volume)

            passive_target = self.spread.calculate_leg_volume(
                leg.vt_symbol,
                hedge_volume
            )

            leg_order_volume = passive_target - passive_traded
            if leg_order_volume:
                self.send_leg_order(leg.vt_symbol, leg_order_volume)

    def send_leg_order(self, vt_symbol: str, leg_volume: float):
        """"""
        leg = self.spread.legs[vt_symbol]
        leg_tick = self.get_tick(vt_symbol)
        leg_contract = self.get_contract(vt_symbol)

        if leg_volume > 0:
            price = leg_tick.ask_price_1 + leg_contract.pricetick * self.payup
            self.send_long_order(leg.vt_symbol, price, abs(leg_volume))
        elif leg_volume < 0:
            price = leg_tick.bid_price_1 - leg_contract.pricetick * self.payup

            self.send_short_order(leg.vt_symbol, price, abs(leg_volume))


class SpreadMakerAlgo(SpreadAlgoTemplate):
    """"""
    algo_name = "SpreadMaker"

    def __init__(
        self,
        algo_engine: Any,
        algoid: str,
        spread: SpreadData,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        payup: float,
        interval: int,
        lock: bool,
        spread_rate: float

    ):
        """"""
        super().__init__(
            algo_engine, algoid, spread,
            direction, offset, price, volume,
            payup, interval, lock, spread_rate
        )

        self.cancel_interval: int = 2
        self.timer_count: int = 0

        self.active_quote_price: float = 0

        active_contract = self.get_contract(spread.active_leg.vt_symbol)
        self.active_price_tick: float = active_contract.pricetick

    def on_tick(self, tick: TickData):
        """"""
        # Return if tick not inited
        if not self.spread.bid_volume or not self.spread.ask_volume:
            return

        # Return if there are any existing orders
        if not self.check_order_finished():
            return

        # Hedge if active leg is not fully hedged
        if not self.check_hedge_finished():
            self.hedge_passive_legs()
            return

        # Check if re-quote is required
        new_quote_price = self.calculate_quote_price()

        if self.active_quote_price:
            price_change = self.active_quote_price - new_quote_price
            if abs(price_change) > (self.active_price_tick * self.payup):
                self.cancel_all_order()

            # Do not repeat sending quote orders
            return

        # Otherwise send active leg quote order
        self.quote_active_leg(new_quote_price)

    def on_order(self, order: OrderData):
        """"""
        # Only care active leg order update
        if order.vt_symbol != self.spread.active_leg.vt_symbol:
            return

        # Clear quote price record
        if not order.is_active():
            self.active_quote_price = 0

        # Do nothing if still any existing orders
        if not self.check_order_finished():
            return

        # Hedge passive legs if necessary
        if not self.check_hedge_finished():
            self.hedge_passive_legs()

    def on_trade(self, trade: TradeData):
        """"""
        pass

    def on_interval(self):
        """"""
        # Do nothing if only active leg quoting
        if self.check_hedge_finished():
            return

        # Cancel old hedge orders
        if not self.check_order_finished():
            self.cancel_all_order()

    def quote_active_leg(self, quote_price: float):
        """"""
        # Calculate spread order volume of new round trade
        spread_order_volume = self.target - self.traded

        # localize object
        spread = self.spread

        # Calculate active leg order volume
        leg_order_volume = spread.calculate_leg_volume(
            spread.active_leg.vt_symbol,
            spread_order_volume
        )

        # Send active leg order
        self.send_leg_order(
            spread.active_leg.vt_symbol,
            leg_order_volume,
            quote_price
        )

        # Record current quote price
        self.active_quote_price = quote_price

    def hedge_passive_legs(self):
        """
        Send orders to hedge all passive legs.
        """
        # Calcualte spread volume to hedge
        active_leg = self.spread.active_leg
        active_traded = self.leg_traded[active_leg.vt_symbol]
        active_traded = round_to(active_traded, self.spread.min_volume)

        hedge_volume = self.spread.calculate_spread_volume(
            active_leg.vt_symbol,
            active_traded
        )

        # Calculate passive leg target volume and do hedge
        for leg in self.spread.passive_legs:
            passive_traded = self.leg_traded[leg.vt_symbol]
            passive_traded = round_to(passive_traded, self.spread.min_volume)

            passive_target = self.spread.calculate_leg_volume(
                leg.vt_symbol,
                hedge_volume
            )

            leg_order_volume = passive_target - passive_traded
            if leg_order_volume:
                self.send_leg_order(leg.vt_symbol, leg_order_volume)

    def send_leg_order(self, vt_symbol: str, leg_volume: float, leg_price: float = 0):
        """"""
        leg = self.spread.legs[vt_symbol]
        leg_tick = self.get_tick(vt_symbol)
        leg_contract = self.get_contract(vt_symbol)

        if leg_volume > 0:
            if leg_price:
                price = leg_price
            else:
                price = leg_tick.ask_price_1 + leg_contract.pricetick * self.payup
            self.send_long_order(leg.vt_symbol, price, abs(leg_volume))
        elif leg_volume < 0:
            if leg_price:
                price = leg_price
            else:
                price = leg_tick.bid_price_1 - leg_contract.pricetick * self.payup
            self.send_short_order(leg.vt_symbol, price, abs(leg_volume))

    def calculate_quote_price(self) -> float:
        """"""
        # Localize object
        spread = self.spread
        active_leg = spread.active_leg

        # Calculate active leg quote price
        price_multiplier = spread.price_multipliers[
            spread.active_leg.vt_symbol
        ]
        if self.spread.trading_type == "price":
            # 差价使用
            if self.direction == Direction.LONG:
                if price_multiplier > 0:
                    quote_price = (self.price - spread.ask_price) / \
                        price_multiplier + active_leg.ask_price
                else:
                    quote_price = (self.price - spread.ask_price) / \
                        price_multiplier + active_leg.bid_price
            else:
                ""
                if price_multiplier > 0:
                    quote_price = (self.price - spread.bid_price) / \
                        price_multiplier + active_leg.ask_price
                else:
                    quote_price = (self.price - spread.bid_price) / \
                        price_multiplier + active_leg.bid_price
        else:
            # 差价比使用
            if self.direction == Direction.LONG:

                """使用 spread rate 计算挂单差价"""
                # print("spread rate 使用 maker")
                # print(f"spread_rate {self.spread_rate} active_ask_price {active_leg.ask_price}  spread_ask_rate { spread.ask_spread_rate} bid_price {active_leg.bid_price} spread_bid_rate {spread.bid_spread_rate}")

                if price_multiplier > 0:
                    quote_price = ((self.spread_rate/100)*active_leg.ask_price - (spread.ask_spread_rate/100)*active_leg.ask_price) / \
                                    price_multiplier + active_leg.ask_price
                    print(f"active_leg {active_leg.vt_symbol} maker ask price {quote_price} LONG")
                else:
                    quote_price = ((self.spread_rate/100)*active_leg.ask_price - (spread.ask_spread_rate/100)*active_leg.ask_price) / \
                                    price_multiplier + active_leg.bid_price
                    print(f"active_leg {active_leg.vt_symbol} maker bid price {quote_price} LONG")


            else:
                if price_multiplier > 0:

                    quote_price = ((self.spread_rate/100) * active_leg.bid_price - (spread.bid_spread_rate/100)*active_leg.bid_price) / \
                                  price_multiplier + active_leg.ask_price
                    print(f"active_leg {active_leg.vt_symbol} maker bid price {quote_price} SHORT")

                else:
                    quote_price = ((self.spread_rate/100) * active_leg.bid_price - (spread.bid_spread_rate/100)*active_leg.bid_price) / \
                                  price_multiplier + active_leg.bid_price
                    print(f"active_leg {active_leg.vt_symbol} maker bid price {quote_price} SHORT")


        # Round price to pricetick of active leg
        contract = self.get_contract(active_leg.vt_symbol)
        quote_price = round_to(quote_price, contract.pricetick)

        return quote_price

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
        if len(self.min_heap) == 0:
            return 0
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
