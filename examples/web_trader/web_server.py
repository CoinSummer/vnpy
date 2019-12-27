import json
import base64
import datetime
from queue import Queue, Empty

from flask import Flask
from flask_sockets import Sockets
from flask_restful import Api, Resource, reqparse

from vnpy.rpc import RpcClient


# 创建RPC客户端
event_queue = Queue()

class TradingClient(RpcClient):
    """"""

    def __init__(self):
        """"""
        super().__init__()

    def callback(self, topic, data):
        """"""
        print(topic, data)
        event_queue.put((topic, data))


req_address = "tcp://localhost:2014"
sub_address = "tcp://localhost:4102"

trading_client = TradingClient()
trading_client.subscribe_topic("")
trading_client.start(req_address, sub_address)

# 载入用户名和密码
TODAY = str(datetime.datetime.now().date())
USERNAME = ""
PASSWORD = ""
TOKEN = ""

with open("web_setting.json") as f:
    setting = json.load(f)
    USERNAME = setting["username"]
    PASSWORD = setting["password"]
    buf = (TODAY + PASSWORD).encode()
    TOKEN = base64.encodebytes(buf).decode().replace("\n","")


# 创建Flask对象
app = Flask(__name__)
sockets = Sockets(app)
api = Api(app)

# 创建REST资源

def error(msg):
    return {"result_code": "error", "message": msg}

def token_error():
    return error("Invalid token.")

def success(data):
    return {"result_code": "success", "data": data}


class Token(Resource):
    """登录验证"""
    
    def __init__(self):
        """初始化"""
        self.parser = reqparse.RequestParser()
        self.parser.add_argument("username")
        self.parser.add_argument("password")
        super().__init__()
    
    def get(self):
        """查询"""
        args = self.parser.parse_args()
        username = args["username"]
        password = args["password"]
        
        if username == USERNAME and password == PASSWORD:
            return success(TOKEN)
        else:
            return error("Wrong username or password.")


class Gateway(Resource):
    """接口"""

    def __init__(self):
        """初始化"""
        self.parser = reqparse.RequestParser()    
        self.parser.add_argument("token")
        self.parser.add_argument("setting")
        self.parser.add_argument("gateway_name")
        
        super().__init__()
    
    def get(self):
        """查询"""
        args = self.parser.parse_args()
        token = args["token"]
        if token != TOKEN:
            return token_error()
        
        data = trading_client.get_all_gateway_names()
        return success(data)
    
    def post(self):
        """新增"""
        args = self.parser.parse_args()
        token = args["token"]
        if token != TOKEN:
            return token_error()

        setting = json.loads(args["setting"])
        
        trading_client.connect(
            setting,
            args["gateway_name"]
        )
        return success("")


class Spread(Resource):
    """委托"""

    def __init__(self):
        """初始化"""
        self.get_parser = reqparse.RequestParser()    
        self.get_parser.add_argument("token")
        
        self.post_parser = reqparse.RequestParser()
        self.post_parser.add_argument("token")
        self.post_parser.add_argument("name")
        self.post_parser.add_argument("leg_settings")
        self.post_parser.add_argument("active_symbol")
        self.post_parser.add_argument("min_volume")
        
        self.delete_parser = reqparse.RequestParser()
        self.delete_parser.add_argument("token")
        self.delete_parser.add_argument("name")
        
        super().__init__()
    
    def get(self):
        """查询"""
        args = self.get_parser.parse_args()
        token = args["token"]
        if token != TOKEN:
            return token_error()
        
        spreads = trading_client.get_all_spreads()
        data = [spread.name for spread in spreads]
        return success(data)
    
    def post(self):
        """新增"""
        args = self.post_parser.parse_args()
        token = args["token"]
        if token != TOKEN:
            return token_error()

        leg_settings = json.loads(args["leg_settings"])
        
        trading_client.add_spread(
            args["name"],
            leg_settings,
            args["active_symbol"],
            args["min_volume"],
            True
        )
        return success("")
    
    def delete(self):
        """删除"""
        args = self.delete_parser.parse_args()
        token = args["token"]
        if token != TOKEN:
            return token_error()
        
        trading_client.remove_spread(args["name"])

        return success("")


class Algo(Resource):
    """委托"""

    def __init__(self):
        """初始化"""
        self.post_parser = reqparse.RequestParser()
        self.post_parser.add_argument("spread_name")
        self.post_parser.add_argument("direction")
        self.post_parser.add_argument("offset")
        self.post_parser.add_argument("price")
        self.post_parser.add_argument("volume")
        self.post_parser.add_argument("payup")
        self.post_parser.add_argument("interval")
        
        self.delete_parser = reqparse.RequestParser()
        self.delete_parser.add_argument("algoid")
        
        super().__init__()
    
    def post(self):
        """新增"""
        args = self.post_parser.parse_args()
        token = args["token"]
        if token != TOKEN:
            return token_error()
        
        algoid = trading_client.start_algo(
            args["spread_name"],
            args["direction"],
            args["offset"],
            args["price"],
            args["volume"],
            args["payup"],
            args["interval"],
            False
        )
        return success(algoid)
    
    def delete(self):
        """删除"""
        args = self.delete_parser.parse_args()
        token = args["token"]
        if token != TOKEN:
            return token_error()
        
        trading_client.stop_algo(args["algoid"])

        return success("")


@sockets.route("/event")
def echo_socket(ws):
    while not ws.closed:
        try:
            topic, data = event_queue.get(timeout=1) 
            msg = json.dumps({
                "topic": topic,
                "data": data
            })
            ws.send(msg)
        except Empty:
            pass


@app.route("/")
def hello():
    return "Hello World!"


# 注册REST资源
api.add_resource(Gateway, "/gateway")
api.add_resource(Token, "/token")
api.add_resource(Spread, "/spread")
api.add_resource(Algo, "/algo")


if __name__ == "__main__":
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    
    server = pywsgi.WSGIServer(
        ("", 5000), 
        app, 
        handler_class=WebSocketHandler
    )
    server.serve_forever()