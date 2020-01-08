# flake8: noqa
from time import sleep

from vnpy.event import EventEngine, Event
from vnpy.rpc import RpcServer
from vnpy.trader.engine import MainEngine
from vnpy.trader.event import EVENT_LOG
from vnpy.gateway.bitmex import BitmexGateway
from vnpy.app.spread_trading import SpreadTradingApp, SpreadEngine
from vnpy.app.spread_trading.base import (
    EVENT_SPREAD_DATA, EVENT_SPREAD_POS, EVENT_SPREAD_LOG,
    EVENT_SPREAD_ALGO, EVENT_SPREAD_STRATEGY
)
from vnpy.trader.ui import create_qapp, MainWindow

class SpreadTradingServer(RpcServer):

    def __init__(self, spread_engine: SpreadEngine):
        """"""
        super().__init__()

        self.spread_engine = spread_engine
        self.event_engine = spread_engine.event_engine
        self.main_engine = spread_engine.main_engine

        self.register_functions()
        self.register_event()

    def register_functions(self):
        """"""
        self.register(self.main_engine.get_all_gateway_names)
        self.register(self.main_engine.connect)

        self.register(self.spread_engine.add_spread)
        self.register(self.spread_engine.remove_spread)
        self.register(self.spread_engine.get_all_spreads)
        self.register(self.spread_engine.start_algo)
        self.register(self.spread_engine.stop_algo)

    def register_event(self):
        """"""
        self.event_engine.register(EVENT_LOG, self.process_log_event)

        self.event_engine.register(EVENT_SPREAD_DATA, self.process_spread_event)
        self.event_engine.register(EVENT_SPREAD_POS, self.process_spread_event)
        self.event_engine.register(EVENT_SPREAD_LOG, self.process_log_event)
        self.event_engine.register(EVENT_SPREAD_ALGO, self.process_algo_event)
        self.event_engine.register(EVENT_SPREAD_STRATEGY, self.process_strategy_event)

    def process_spread_event(self, event: Event):
        """"""
        spread = event.data

        data = {
            "name": spread.name,
            "bid_price": spread.bid_price,
            "ask_price": spread.ask_price,
            "bid_volume": spread.bid_volume,
            "ask_volume": spread.ask_volume,
            "price_formula": spread.price_formula,
            "trading_formula": spread.trading_formula
        }
        
        self.publish(EVENT_SPREAD_DATA, data)

    def process_log_event(self, event: Event):
        """"""
        log = event.data

        data = {
            "msg": log.msg,
            "time": str(log.time)
        }
        print(data)

        self.publish(EVENT_SPREAD_LOG, data)

    def process_algo_event(self, event: Event):
        """"""
        algo = event.data

        data = {
            "algoid": algo.algoid,
            "spread_name": algo.spread_name,
            "offset": algo.offset.value,
            "direction": algo.direction.value,
            "price": algo.price,
            "volume": algo.volume,
            "payup": algo.payup,
            "interval": algo.interval,
            "status": algo.status.value,
            "traded_volume": algo.traded_volume
        }

        self.publish(EVENT_SPREAD_ALGO, data)

    def process_strategy_event(self, event: Event):
        """"""
        self.publish(EVENT_SPREAD_STRATEGY, event.data)


def main():
    """"""
    qapp = create_qapp()

    # 引擎初始化
    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(BitmexGateway)
    
    spread_engine = main_engine.add_app(SpreadTradingApp)
    trading_server = SpreadTradingServer(spread_engine)

    # 启动RPC服务
    rep_address = "tcp://*:2014"
    pub_address = "tcp://*:4102"
    trading_server.start(rep_address, pub_address)

    # 启动价差引擎
    spread_engine.start()

    # 创建主窗口
    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec_()

    #while True:
    #    sleep(1)


if __name__ == "__main__":
    main()
