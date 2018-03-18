#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ ='Mosan'

'''
web application的运行脚本
'''

import asyncio, json, time, os
import logging;logging.basicConfig(level=logging.INFO)
import orm
from datetime import datetime
from aiohttp import web
from handlers import cookie2user, COOKIE_NAME
from config import configs
from coroweb import add_routes, add_static
from jinja2 import Environment, FileSystemLoader

#初始化jinja2模板引擎：虽然暂时并未模板化前端代码，但是后端处理请求时需要其来设置路径
#（暂时）先直接复制
def init_jinja2(app, **kw): # 初始化jinja2引擎函数
    logging.info('init jinja2...') #logging库信息显示方法info
    options = dict( #定义选项字典;kw.get方法的功能是若有则获取，没有则按第二个参数生成
        autoescape = kw.get('autoescape', True), #获取自动撤离参数
        block_start_string = kw.get('block_start_string', '{%'), #获取块起始字符串
        block_end_string = kw.get('block_end_string', '%}'), #获取块结束字符串
        variable_start_string = kw.get('variable_start_string', '{{'), #获取变量起始字符串
        variable_end_string = kw.get('variable_end_string', '}}'), #获取变量结束字符串
        auto_reload = kw.get('auto_reload', True) #获取自动重载参数
    )
    path = kw.get('path', None) #获取路径参数
    if path is None: #若路径为空
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates') #重新加入路径
    logging.info('set jinja2 template path: %s' % path) #显示登录信息：设置引擎模板路径
    env = Environment(loader=FileSystemLoader(path), **options) #jinja2库函数FileSystemLoader传入路径参数，再传入Environment库函数生成环境实例
    filters = kw.get('filters', None) #获取过滤器参数
    if filters is not None: #若过滤器为非空
        for name, f in filters.items(): #环境实例加入过滤参数
            env.filters[name] = f
    app['__templating__'] = env #将app的内部参数templating设置为env实例

#定义实现middleware拦截器功能的方法

#记录url日志
@asyncio.coroutine
def logger_factory(app, handler):
    #记录日志
    @asyncio.coroutine
    def logger(request): #为何写成这样的形式
        logging.info("handle the request %s and %s" % (request.method, request.path))
    #继续处理
        return (yield from handler(request))
    return logger

#定义response拦截器，将返回的数据转化为web.Response,以满足aiohttp的方法
@asyncio.coroutine
def response_factory(app, handler):
    @asyncio.coroutine
    def response(request):
        logging.info("Response handler...")
        r = yield from handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[:9])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, bytes):
            resp = web.Reponse(body=r)
            resp.content_type = 'application/octet=stream'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:
                resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                r['__user__'] = request.__user__
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        #若直接是数字则是错误码，直接返回
        if isinstance(r, int):
            if r >= 100 and r < 600:
                return web.Response(r)
        #若是元组，则是错误原因和错误码的组合
        if isinstance(r, tuple):
            if len(r) == 2:
                t, m = r
                if isinstance(t, int) and t >=100 and t < 600:
                    return web.Response(t, str(m))
        #否则默认返回原始数据
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8' #表示将文件格式设置为纯文本形式，不会进行解释
        return resp
    return response



#定义用户认证拦截器
@asyncio.coroutine
def auth_factory(app, handler):
    @asyncio.coroutine
    def auth(request):
        logging.info("check user:%s %s" % (request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user = yield from cookie2user(cookie_str) #涉及数据IO用协程操作
            if user:
                logging.info("set current user: %s" % user.email)
                request.__user__ = user
        #检查是否为管理员
        #确定为用户后继续处理请求
        return (yield from handler(request))
    return auth
#定义数据处理拦截器
#copy
@asyncio.coroutine
def data_factory(app, handler): #数据工厂协程
    @asyncio.coroutine
    def parse_data(request): #解析数据协程
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = yield from request.json()
                logging.info('request json: %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = yield from request.post()
                logging.info('request form: %s' % str(request.__data__))
        return (yield from handler(request))
    return parse_data

#定义日期时间过滤器：提供给jinja2模板
#（暂时）直接copy
def datetime_filter(t): #日期时间过滤函数
    delta = int(time.time() - t) #获取时间间隔
    if delta < 60: 
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)

#启动过程封装
@asyncio.coroutine
def init(loop):
    yield from orm.create_pool(loop=loop, **configs.db)
    app = web.Application(loop=loop, middlewares=[logger_factory, auth_factory, response_factory])
    init_jinja2(app, filters=dict(datetime=datetime_filter)) #直接copy
    add_routes(app, 'handlers')
    add_static(app)
    srv = yield from loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    logging.info("Started server at http://127.0.0.1:9000")
    return srv

#启动
loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
#test
