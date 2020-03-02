# flake8: noqa
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp
from vnpy.gateway.okexf import OkexfGateway
from vnpy.gateway.bitmex import BitmexGateway

from vnpy.app.market_maker.delta_one import DeltaOneApp


def main():
    """"""
    qapp = create_qapp()

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    main_engine.add_gateway(OkexfGateway)
    main_engine.add_gateway(BitmexGateway)
    main_engine.add_app(DeltaOneApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


if __name__ == "__main__":
    main()
