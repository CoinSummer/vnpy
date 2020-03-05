from time import sleep

from vnpy.event import EventEngine, Event
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp
from vnpy.trader.event import EVENT_LOG
# from vnpy.gateway.ctp import CtpGateway
from vnpy.gateway.okexs import OkexsGateway
from vnpy.gateway.okexf import OkexfGateway
from vnpy.gateway.bitmex import BitmexGateway
from vnpy.gateway.coinbase import CoinbaseGateway

from vnpy.app.rpc_service import RpcServiceApp
from vnpy.app.rpc_service.engine import EVENT_RPC_LOG

import os
import shutil
import zmq.auth


def generate_certificates(base_dir):
    ''' Generate client and server CURVE certificate files'''
    keys_dir = os.path.join(base_dir, 'certificates')
    print(f"jaslfjas  {base_dir}")
    if os.path.exists(keys_dir):
        shutil.rmtree(keys_dir)
    os.mkdir(keys_dir)

    # create new keys in certificates dir
    server_public_file, server_secret_file = zmq.auth.create_certificates(keys_dir, "server")
    client_public_file, client_secret_file = zmq.auth.create_certificates(keys_dir, "client")

    # generate_certificates(os.path.dirname('__file__'))



def main_ui():
    """"""
    qapp = create_qapp()

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)

    # main_engine.add_gateway(CtpGateway)
    main_engine.add_gateway(OkexsGateway)

    main_engine.add_app(RpcServiceApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


def process_log_event(event: Event):
    """"""
    log = event.data
    msg = f"{log.time}\t{log.msg}"
    print(msg)


def main_terminal():
    """"""
    event_engine = EventEngine()
    event_engine.register(EVENT_LOG, process_log_event)
    event_engine.register(EVENT_RPC_LOG, process_log_event)

    main_engine = MainEngine(event_engine)
    # main_engine.add_gateway(CtpGateway)
    main_engine.add_gateway(OkexsGateway)
    main_engine.add_gateway(OkexfGateway)

    main_engine.add_gateway(BitmexGateway)
    main_engine.add_gateway(CoinbaseGateway)


    rpc_engine = main_engine.add_app(RpcServiceApp)

    # setting = {
    #     "用户名": "",
    #     "密码": "",
    #     "经纪商代码": "9999",
    #     "交易服务器": "180.168.146.187:10101",
    #     "行情服务器": "180.168.146.187:10111",
    #     "产品名称": "simnow_client_test",
    #     "授权编码": "0000000000000000",
    #     "产品信息": ""
    # }
    #

    setting_ok = {
    "API Key": "af4f2405-4aec-46d8-b927-bba8a347ba0f",
    "Secret Key": "EA6700794BAF7E7CCABF40AF290E88EC",
    "Passphrase": "abc123",
    "会话数": 3,
    "代理地址": "",
    "代理端口": ""
    }

    setting={
        "ID": "EYKKKXqZwaKbeBUFJsVDvkk3",
        "Secret": "1dCBbIYa5TrMi6ObD8zY6eAiEpnxRDLH4P_djGtAh_vfh7ky",
        "会话数": 3,
        "服务器": "REAL",
        "代理地址": "",
        "代理端口": ""
    }

    setting_coinbase = {
        "ID": "a792bf1dc1b1c42f4e811864e238e3c9",
        "Secret": "wYGDTZmjHRMFLDG78avZ6aTBckIkNcNi/QQJCjO0gyEtcs+ijT05YTxuZ7nksohd90YkKtZYMPNZiVo3uVMCHQ==",
        "passphrase": "k1an4a5r26",
        "会话数": 3,
        "server": "SANDBOX",
        "proxy_host": "",
        "proxy_port": ""
    }
    # main_engine.connect(setting_ok, "OKEXS")
    # # main_engine.connect(setting_ok, "OKEXF")
    #
    # main_engine.connect(setting_coinbase, "COINBASE")
    # main_engine.connect(setting, "BITMEX")

    # b_dir = os.path.split(os.path.abspath(__file__))[0]
    # print(f'bdir {b_dir} {os.getcwd()} {os.path.abspath(os.path.join(os.path.dirname(__file__),"../../.."))}')
    # print(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),"../../.."))
    keys_dir = os.path.join(base_dir, 'certificates')
    # print(f"路径 {keys_dir}  {os.path.dirname(os.path.realpath('__file__'))} {os.getcwd()} {os.path.exists(keys_dir)}")
    if not os.path.exists(keys_dir):
        generate_certificates(base_dir)
        print("生成认证文件")

    sleep(10)

    print(keys_dir)
    load_file = os.path.join(keys_dir, "certificates/server.key_secret")
    rep_address = "tcp://127.0.0.1:2014"
    pub_address = "tcp://127.0.0.1:4102"
    rpc_engine.start(rep_address, pub_address, load_file)

    while True:
        sleep(1)


if __name__ == "__main__":
    # Run in GUI mode
    # main_ui()

    # Run in CLI mode
    main_terminal()
