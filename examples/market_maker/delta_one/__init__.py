from pathlib import Path

from vnpy.trader.app import BaseApp

from .engine import QuotingEngine, APP_NAME


class DeltaOneApp(BaseApp):
    """"""

    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "做市报价"
    engine_class = QuotingEngine
    widget_name = "QuotingManager"
    icon_name = "do.ico"
