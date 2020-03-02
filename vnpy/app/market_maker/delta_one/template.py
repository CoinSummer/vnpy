from typing import Set, List, Dict, Optional, TYPE_CHECKING

from vnpy.trader.object import (
    TickData, OrderData, TradeData, ContractData,
    PositionData, OrderRequest, BarData
)
from vnpy.trader.constant import (
    Direction, Offset, OrderType
)
from vnpy.trader.utility import virtual

if TYPE_CHECKING:
    from .engine import QuotingEngine


class QuotingTemplate:
    """"""

    author = ""
    parameters: List[str] = []
    variables: List[str] = []

    def __init__(self, name: str, engine: "QuotingEngine"):
        """"""
        self.name: str = name
        self.engine: "QuotingEngine" = engine

        self.active_orderids: Set[str] = set()

        self.inited: bool = False
        self.trading: bool = False

        self.variables.insert(0, "inited")
        self.variables.insert(1, "trading")

    def update_parameters(self, parameters: Dict) -> None:
        """"""
        for key in self.parameters:
            if key in parameters:
                value = parameters[key]
                setattr(self, key, value)

    def update_order(self, order: OrderData) -> None:
        """"""
        if order.is_active():
            self.active_orderids.add(order.vt_orderid)
        elif order.vt_orderid in self.active_orderids:
            self.active_orderids.remove(order.vt_orderid)

    def get_data(self, keys: List[str]) -> Dict:
        """"""
        data = {key: getattr(self, key) for key in keys}
        return data

    def get_parameters(self):
        """"""
        return self.get_data(self.parameters)

    def get_variables(self):
        """"""
        return self.get_data(self.variables)

    @virtual
    def on_init(self) -> None:
        """"""
        pass

    @virtual
    def on_start(self) -> None:
        """"""
        pass

    @virtual
    def on_stop(self) -> None:
        """"""
        pass

    @virtual
    def on_timer(self) -> None:
        """"""
        pass

    @virtual
    def on_tick(self, tick: TickData) -> None:
        """"""
        pass

    @virtual
    def on_order(self, order: OrderData) -> None:
        """"""
        pass

    @virtual
    def on_trade(self, trade: TradeData) -> None:
        """"""
        pass

    def subscribe(self, vt_symbol: str) -> bool:
        """"""
        return self.engine.subscribe(self, vt_symbol)

    def get_contract(self, vt_symbol: str) -> Optional[ContractData]:
        """"""
        return self.engine.get_contract(vt_symbol)

    def get_tick(self, vt_symbol: str) -> Optional[TickData]:
        """"""
        return self.engine.get_tick(vt_symbol)

    def get_position(self, vt_symbol: str, direction: Direction) -> Optional[PositionData]:
        """"""
        return self.engine.get_position(vt_symbol, direction)

    def count_active_orders(self):
        """"""
        return len(self.active_orderids)

    def send_order(
        self,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
    ) -> str:
        return self.engine.send_order(self, vt_symbol, direction, offset, price, volume)

    def buy(self, vt_symbol: str, price: float, volume: float) -> str:
        """"""
        vt_orderid = self.send_order(
            vt_symbol, Direction.LONG, Offset.OPEN, price, volume
        )
        return vt_orderid

    def sell(self, vt_symbol: str, price: float, volume: float) -> str:
        """"""
        vt_orderid = self.send_order(
            vt_symbol, Direction.SHORT, Offset.CLOSE, price, volume
        )
        return vt_orderid

    def short(self, vt_symbol: str, price: float, volume: float) -> str:
        """"""
        vt_orderid = self.send_order(
            vt_symbol, Direction.SHORT, Offset.OPEN, price, volume
        )
        return vt_orderid

    def cover(self, vt_symbol: str, price: float, volume: float) -> str:
        """"""
        vt_orderid = self.send_order(
            vt_symbol, Direction.LONG, Offset.CLOSE, price, volume
        )
        return vt_orderid

    def cancel_order(self, vt_orderid: str) -> None:
        """"""
        self.engine.cancel_order(vt_orderid)

    def create_order(
        self,
        vt_symbol: str,
        direction: Direction,
        price: float,
        volume: float,
        offset: Offset = Offset.NONE
    ) -> OrderRequest:
        """"""
        contract = self.get_contract(vt_symbol)

        req = OrderRequest(
            contract.symbol,
            contract.exchange,
            direction,
            OrderType.LIMIT,
            volume,
            price,
            offset
        )

        return req

    def send_orders(self, reqs: List[OrderRequest]) -> List[str]:
        """"""
        self.engine.send_orders(self, reqs)

    def cancel_orders(self, vt_orderids: List[str]) -> None:
        """"""
        self.engine.cancel_orders(vt_orderids)

    def cancel_all(self) -> None:
        """"""
        for vt_orderid in self.active_orderids:
            self.cancel_order(vt_orderid)

    def put_event(self) -> None:
        """"""
        self.engine.put_event(self)

    def write_log(self, msg: str) -> None:
        """"""
        self.engine.write_log(msg, self)
