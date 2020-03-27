from typing import Dict, Callable

from .template import (
    QuotingTemplate,
    TickData,
    OrderData,
    TradeData,
    Direction,
    BarData,
)


class MarketMakingStrategy(QuotingTemplate):
    """"""

    author = "用Python的交易员"

    quoting_symbol = ""
    reference_symbol = ""

    quoting_basis = 0.0
    quoting_spread = 0.0
    quoting_size = 0.0
    max_pos = 0.0
    max_order_count = 2

    parameters = [
        "quoting_symbol",
        "reference_symbol",
        "quoting_basis",
        "quoting_spread",
        "quoting_size",
        "max_pos",
        "max_order_count"
    ]

    quoting_pos = 0.0
    reference_price = 0.0
    target_mid_price = 0.0
    target_bid_price = 0.0
    target_ask_price = 0.0

    current_bid_price = 0.0
    current_ask_price = 0.0

    variables = [
        "quoting_pos",
        "reference_price",
        "target_mid_price",
        "target_bid_price",
        "target_ask_price",
        "current_bid_price",
        "current_ask_price",
    ]

    def __init__(self, name: str, engine):
        """"""
        super().__init__(name, engine)

        self.half_spread: float = 0
        self.quoting_tick: TickData = None
        self.reference_tick: TickData = None
        self.quoting_pricetick: float = 0.0
        self.bid_orderid: str = ""
        self.ask_orderid: str = ""

    def on_init(self) -> None:
        """"""
        self.tick_callbacks: Dict[str, Callable] = {
            self.quoting_symbol: self.on_quoting_tick,
            self.reference_symbol: self.on_reference_tick
        }

        self.subscribe(self.quoting_symbol)
        self.subscribe(self.reference_symbol)

        self.inited = True
        self.write_log("策略初始化")

    def on_start(self) -> None:
        """"""
        self.half_spread = self.quoting_spread / 2

        quoting_contract = self.get_contract(self.quoting_symbol)
        if not quoting_contract:
            self.write_log(f"启动失败，找不到报价合约{self.quoting_symbol}")
            return

        self.quoting_pricetick = quoting_contract.pricetick

        if quoting_contract.net_position:
            position = self.get_position(self.quoting_symbol, Direction.NET)
            if position:
                self.quoting_pos = position.volume
        else:
            long_position = self.get_position(self.quoting_symbol, Direction.LONG)
            if long_position:
                self.quoting_pos += long_position.volume

            short_position = self.get_position(self.quoting_symbol, Direction.SHORT)
            if short_position:
                self.quoting_pos -= short_position.volume

        self.trading = True
        self.write_log("策略启动")

    def on_stop(self) -> None:
        """"""
        self.cancel_all_quoting_orders()

        self.trading = False
        self.write_log("策略停止")

    def on_timer(self) -> None:
        """"""
        self.run_quote()

    def on_tick(self, tick: TickData) -> None:
        """"""
        callback = self.tick_callbacks[tick.vt_symbol]
        callback(tick)

    def on_quoting_tick(self, tick: TickData) -> None:
        """"""
        self.quoting_tick = tick

    def on_reference_tick(self, tick: TickData) -> None:
        """"""
        self.reference_tick = tick

    def run_quote(self) -> None:
        """"""
        if not self.quoting_tick or not self.reference_tick:
            return

        requote_required = self.calcualte_quoting_price()
        if not requote_required:
            return

        if not self.trading:
            return

        if self.count_active_orders() <= self.max_order_count:
            self.cancel_old_quoting_orders()
            self.send_new_quoting_orders()
        else:
            self.cancel_all_quoting_orders()

    def cancel_all_quoting_orders(self) -> None:
        """"""
        self.cancel_all()

        self.bid_orderid = ""
        self.ask_orderid = ""
        self.reference_price = 0
        self.current_ask_price = 0
        self.current_bid_price = 0

    def calcualte_quoting_price(self) -> bool:
        """"""
        new_price = self.reference_tick.last_price
        if self.reference_price == new_price:
            return False

        # Calculate strategy target quoting price
        self.reference_price = self.reference_tick.last_price
        self.target_mid_price = self.reference_price + self.quoting_basis
        self.target_bid_price = self.target_mid_price - self.half_spread
        self.target_ask_price = self.target_mid_price + self.half_spread

        # Adjust target price to avoid taker trade
        if self.target_bid_price >= self.quoting_tick.ask_price_1:
            self.target_bid_price = self.quoting_tick.ask_price_1 - self.quoting_pricetick

        if self.target_ask_price <= self.quoting_tick.bid_price_1:
            self.target_ask_price = self.quoting_tick.bid_price_1 + self.quoting_pricetick

        self.put_event()

        return True

    def cancel_old_quoting_orders(self) -> None:
        """"""
        cancel_orderids = []

        if self.bid_orderid and self.target_bid_price != self.current_bid_price:
            cancel_orderids.append(self.bid_orderid)
            self.bid_orderid = ""

        if self.ask_orderid and self.target_ask_price != self.current_ask_price:
            cancel_orderids.append(self.ask_orderid)
            self.ask_orderid = ""

        if cancel_orderids:
            self.cancel_orders(cancel_orderids)

    def send_new_quoting_orders(self) -> None:
        """"""
        reqs = []

        if (
            self.quoting_pos < self.max_pos
            and self.target_bid_price != self.current_bid_price
        ):
            bid_req = self.create_order(
                self.quoting_symbol,
                Direction.LONG,
                self.target_bid_price,
                self.quoting_size
            )
            reqs.append(bid_req)

            self.current_bid_price = self.target_bid_price

        if (
            self.quoting_pos > -self.max_pos
            and self.target_ask_price != self.current_ask_price
        ):
            ask_req = self.create_order(
                self.quoting_symbol,
                Direction.SHORT,
                self.target_ask_price,
                self.quoting_size
            )
            reqs.append(ask_req)

            self.current_ask_price = self.target_ask_price

        self.send_orders(reqs)
        self.write_log("send order" + str(reqs))

    def on_order(self, order: OrderData) -> None:
        """"""
        if order.is_active():
            if order.direction == Direction.LONG:
                self.bid_orderid = order.vt_orderid
            else:
                self.ask_orderid = order.vt_orderid
        else:
            if order.direction == Direction.LONG:
                self.bid_orderid = ""
            else:
                self.ask_orderid = ""

    def on_trade(self, trade: TradeData) -> None:
        """"""
        if trade.vt_symbol == self.quoting_symbol:
            if trade.direction == Direction.LONG:
                self.quoting_pos += trade.volume
            else:
                self.quoting_pos -= trade.volume

            self.put_event()
