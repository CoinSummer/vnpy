#!/usr/bin/env python
#-*- coding:utf-8 -*-
"""
File Name:
Author: wudi
Mail: programmerwudi@gmail.com
Created Time: 2020-02-05 16:14:52
"""

from vnpy.event import Event
from vnpy.event import EventEngine
from vnpy.gateway.rpc import RpcGateway
from vnpy.trader.event import (
    EVENT_TICK,
    EVENT_TRADE,
    EVENT_ORDER,
    EVENT_POSITION,
    EVENT_ACCOUNT,
    EVENT_LOG
)

from vnpy.trader.object import (
    PositionData
)

# setting = {
#    "主动请求地址": "tcp://47.91.89.143:2014",
#    "推送订阅地址": "tcp://47.91.89.143:4102"
# }
#
setting = {
        "主动请求地址": "tcp://127.0.0.1:2014",
        "推送订阅地址":"tcp://127.0.0.1:4102"
        }

def process_log_event(event: Event):
    log = event.data
    msg = f"{log.time}\t{log.msg}"
    print(msg)

def process_event(event: Event):
    print(f" t evnet {event.data}")

def main():
    event_engine = EventEngine()
    # event_engine.register(EVENT_LOG, process_log_event)
    event_engine.register(EVENT_POSITION, process_event)
    event_engine.register(EVENT_ACCOUNT, process_event)
    # event_engine.register(EVENT_ORDER, process_event)
    # event_engine.register(EVENT_TRADE, process_event)

    event_engine.start()
    gate = RpcGateway(event_engine)

    gate.connect(setting)
if __name__ == "__main__":
    main()
