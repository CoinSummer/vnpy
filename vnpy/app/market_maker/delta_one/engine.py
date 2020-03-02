import os
import importlib
import traceback
from pathlib import Path
from typing import Dict, Set, List, Type, Optional
from collections import defaultdict

from vnpy.event import EventEngine, Event
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.utility import load_json, save_json
from vnpy.trader.event import (
    EVENT_TICK, EVENT_TIMER, EVENT_ORDER, EVENT_TRADE
)
from vnpy.trader.object import (
    SubscribeRequest, OrderRequest, CancelRequest,
    ContractData, OrderData, TradeData, PositionData,
    TickData, LogData
)
from vnpy.trader.constant import (
    Direction, Offset, OrderType
)

from .template import QuotingTemplate


APP_NAME = "DeltaOne"

EVENT_DO_STRATEGY = "eMmStrategy"
EVENT_DO_LOG = "eMmLog"


class QuotingEngine(BaseEngine):
    """"""

    setting_filename = "market_maker_setting.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """Constructor"""
        super().__init__(main_engine, event_engine, APP_NAME)

        self.inited = False

        self.classes: Dict[str, Type[QuotingTemplate]] = {}
        self.strategies: Dict[str, QuotingTemplate] = {}

        self.tick_strategy_map: Dict[str, Set[QuotingTemplate]] = defaultdict(set)
        self.order_strategy_map: Dict[str, QuotingTemplate] = {}

    def init_engine(self) -> bool:
        """"""
        if self.inited:
            return False

        self.load_strategy_class()
        self.load_strategy_setting()
        self.register_event()

        self.write_log("DeltaOne报价引擎初始化成功")
        return True

    def register_event(self) -> None:
        """"""
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self.event_engine.register(EVENT_ORDER, self.process_order_event)
        self.event_engine.register(EVENT_TRADE, self.process_trade_event)

    def process_tick_event(self, event: Event) -> None:
        """"""
        tick: TickData = event.data
        strategies = self.tick_strategy_map[tick.vt_symbol]

        for strategy in strategies:
            if strategy.inited:
                strategy.on_tick(tick)

    def process_timer_event(self, event: Event) -> None:
        """"""
        for strategy in self.strategies.values():
            if strategy.inited:
                strategy.on_timer()

    def process_trade_event(self, event: Event) -> None:
        """"""
        trade: TradeData = event.data
        strategy = self.order_strategy_map.get(trade.vt_orderid, None)

        if strategy:
            if strategy.inited:
                strategy.on_trade(trade)

    def process_order_event(self, event: Event) -> None:
        """"""
        order: OrderData = event.data
        strategy = self.order_strategy_map.get(order.vt_orderid, None)

        if strategy:
            if strategy.inited:
                strategy.update_order(order)
                strategy.on_order(order)

    def subscribe(self, strategy: QuotingTemplate, vt_symbol: str) -> bool:
        """"""
        # Get contract
        contract = self.main_engine.get_contract(vt_symbol)
        if not contract:
            return False

        # Subscribe market data update
        req = SubscribeRequest(contract.symbol, contract.exchange)
        self.main_engine.subscribe(req, contract.gateway_name)

        # Add tick strategy relationship map
        self.tick_strategy_map[vt_symbol].add(strategy)

        return True

    def get_contract(self, vt_symbol: str) -> Optional[ContractData]:
        """"""
        return self.main_engine.get_contract(vt_symbol)

    def get_tick(self, vt_symbol: str) -> Optional[TickData]:
        """"""
        return self.main_engine.get_tick(vt_symbol)

    def get_position(self, vt_symbol: str, direction: Direction) -> Optional[PositionData]:
        """"""
        vt_positionid = f"{vt_symbol}.{direction.value}"
        return self.main_engine.get_position(vt_positionid)

    def send_order(
        self,
        strategy: QuotingTemplate,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ) -> str:
        """"""
        contract: ContractData = self.main_engine.get_contract(vt_symbol)
        if not contract:
            return ""

        req = OrderRequest(
            contract.symbol,
            contract.exchange,
            direction,
            OrderType.LIMIT,
            volume,
            price,
            offset
        )

        vt_orderid = self.main_engine.send_order(req, contract.gateway_name)
        self.order_strategy_map[vt_orderid] = strategy

        return vt_orderid

    def cancel_order(self, vt_orderid: str) -> None:
        """"""
        order: OrderData = self.main_engine.get_order(vt_orderid)
        if not order:
            return

        req: CancelRequest = order.create_cancel_request()
        self.main_engine.cancel_order(req, order.gateway_name)

    def send_orders(self, strategy: QuotingTemplate, reqs: List[OrderRequest]) -> List[str]:
        """"""
        if not reqs:
            return []

        contract: ContractData = self.main_engine.get_contract(reqs[0].vt_symbol)
        vt_orderids = self.main_engine.send_orders(reqs, contract.gateway_name)

        for vt_orderid in vt_orderids:
            self.order_strategy_map[vt_orderid] = strategy

        return vt_orderids

    def cancel_orders(self, vt_orderids: List[str]) -> None:
        """"""
        reqs: List[CancelRequest] = []

        for vt_orderid in vt_orderids:
            order: OrderData = self.main_engine.get_order(vt_orderid)

            if order:
                req = order.create_cancel_request()
                reqs.append(req)

        self.main_engine.cancel_orders(reqs, order.gateway_name)

    def put_event(self, strategy: QuotingTemplate) -> None:
        """"""
        data = {
            "strategy_name": strategy.name,
            "author": strategy.author,
            "class_name": strategy.__class__.__name__,
            "parameters": strategy.get_parameters(),
            "variables": strategy.get_variables()
        }

        event = Event(EVENT_DO_STRATEGY, data)
        self.event_engine.put(event)

    def write_log(self, msg: str, strategy: Optional[QuotingTemplate] = None) -> None:
        """"""
        log = LogData(msg=msg, gateway_name=APP_NAME)
        event = Event(EVENT_DO_LOG, log)
        self.event_engine.put(event)

    def init_strategy(self, name: str) -> bool:
        """"""
        strategy = self.strategies.get(name, None)
        if not strategy:
            self.write_log(f"找不到策略{name}")
            return False

        if strategy.inited:
            self.write_log(f"{name}策略已完成初始化")
            return False

        strategy.on_init()
        self.put_event(strategy)
        return True

    def start_strategy(self, name: str) -> bool:
        """"""
        strategy = self.strategies.get(name, None)
        if not strategy:
            self.write_log(f"找不到策略{name}")
            return False

        if not strategy.inited:
            self.write_log(f"{name}策略尚未初始化")
            return False

        if strategy.trading:
            self.write_log(f"{name}策略已启动")
            return False

        strategy.on_start()
        self.put_event(strategy)
        return True

    def stop_strategy(self, name: str) -> bool:
        """"""
        strategy = self.strategies.get(name, None)
        if not strategy:
            self.write_log(f"找不到策略{name}")
            return False

        if not strategy.trading:
            self.write_log(f"{name}策略尚未启动")
            return False

        strategy.on_stop()
        self.put_event(strategy)
        return True

    def edit_strategy(self, name: str, parameters: dict) -> None:
        """"""
        strategy = self.strategies[name]
        strategy.update_parameters(parameters)

        self.save_strategy_setting()
        self.put_event(strategy)

    def load_strategy_class(self) -> None:
        """
        Load strategy class from source code.
        """
        path = Path.cwd().joinpath("strategies")
        self.load_strategy_class_from_folder(path, "strategies")

        from .strategy import MarketMakingStrategy
        self.classes[MarketMakingStrategy.__name__] = MarketMakingStrategy

    def load_strategy_class_from_folder(self, path: Path, module_name: str = "") -> None:
        """
        Load strategy class from certain folder.
        """
        for dirpath, dirnames, filenames in os.walk(str(path)):
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue

                strategy_module_name = ".".join([module_name, filename.replace(".py", "")])
                self.load_strategy_class_from_module(strategy_module_name)

    def load_strategy_class_from_module(self, module_name: str) -> None:
        """
        Load strategy class from module file.
        """
        try:
            module = importlib.import_module(module_name)

            for name in dir(module):
                value = getattr(module, name)
                if (
                    isinstance(value, type)
                    and issubclass(value, QuotingTemplate)
                    and value is not QuotingTemplate
                ):
                    self.classes[value.__name__] = value
        except Exception:
            msg = f"策略文件{module_name}加载失败，触发异常：\n{traceback.format_exc()}"
            self.write_log(msg)

    def load_strategy_setting(self) -> None:
        """"""
        strategy_setting = load_json(self.setting_filename)

        for name, setting in strategy_setting.items():
            self.add_strategy(
                setting["class_name"],
                name,
                setting["parameters"]
            )

    def save_strategy_setting(self) -> None:
        """"""
        strategy_setting = {}

        for name, strategy in self.strategies.items():
            strategy_setting[name] = {
                "class_name": strategy.__class__.__name__,
                "parameters": strategy.get_parameters()
            }

        save_json(self.setting_filename, strategy_setting)

    def add_strategy(self, class_name: str, name: str, parameters: dict) -> bool:
        """"""
        if class_name not in self.classes:
            self.write_log(f"添加策略失败，找不到策略类{class_name}")
            return False

        if name in self.strategies:
            self.write_log(f"添加策略失败，已存在同名策略{name}")
            return False

        strategy_class = self.classes.get(class_name, None)
        strategy = strategy_class(name, self)
        strategy.update_parameters(parameters)
        self.strategies[name] = strategy

        self.put_event(strategy)

        return True

    def remove_strategy(self, name: str) -> bool:
        """"""
        if name not in self.strategies:
            self.write_log(f"移除策略失败，找不到策略{name}")
            return False

        strategy = self.strategies[name]
        if strategy.trading:
            self.write_log(f"移除策略失败，请先停止策略{name}")
            return False

        strategy.inited = False

        # Remove from symbol strategy map
        for strategies in self.tick_strategy_map.values():
            if strategy in strategies:
                strategies.remove(strategy)

        # Remove from strategies
        self.strategies.pop(name)

        return True

    def get_all_strategy_class_names(self) -> List[str]:
        """"""
        return list(self.classes.keys())

    def get_strategy_class_parameters(self, class_name: str) -> Dict:
        """
        Get default parameters of a strategy class.
        """
        strategy_class = self.classes[class_name]

        parameters = {}
        for name in strategy_class.parameters:
            parameters[name] = getattr(strategy_class, name)

        return parameters

    def get_strategy_parameters(self, strategy_name: str) -> Dict:
        """
        Get parameters of a strategy.
        """
        strategy = self.strategies[strategy_name]
        return strategy.get_parameters()
