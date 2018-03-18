#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ ='Mosan'

'''
REST风格的API处理函数
'''

import asyncio, time, hashlib, re, json, base64, time, logging
import markdown2
from aiohttp import web
from config import configs
from models import User, next_id
from coroweb import get, post
from apis import Page, APIValueError, APIResourceNotFoundError
from models import User, next_id
from apis import Page, APIValueError, APIResourceNotFoundError, APIError

#设置cookie参数
COOKIE_NAME = 'jxzjsession' #copy;已修改
_COOKIE_KEY = configs.session.secret

#设置注册，登录邮箱/密码格式
#邮箱格式:copy
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
#密码格式：只能是数字或者小写字母，最大长度40
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$') #定义密码输入格式

#获取当前页面
def get_page_index(page_str):
    page = 1
    try:
        page = int(page_str)
    except ValueError as e:
        pass 
    if page < 1:
        page =1
    return page

#由user建立cookie字符串
def user2cookie(user, max_age):
    #按照id-expire-sha1的格式生成cookie字符串
    expire = str(int(time.time() + max_age))
    #由id，密码，存活时间，cookie键生成哈希加密初始字符串
    S = '%s-%s-%s-%s' %(user.id, user.passwd, expire, _COOKIE_KEY)
    L = [user.id, expire, hashlib.sha1(S.encode('utf-8')).hexdigest()] #已修改
    return '-'.join(L)


#解析cookie且当有效时加载user
@asyncio.coroutine
def cookie2user(cookie_str):
    try:
        if not cookie_str:
            return None
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expire, sha1 = L
        if int(expire) < time.time():
            return None
        user = yield from User.find(uid)
        if not user:
            return None
        S = '%s-%s-%s-%s' % (user.id, user.passwd, expire, _COOKIE_KEY)
        if sha1 != hashlib.sha1(S.encode('utf-8')).hexdigest(): #已修改
            return None
            logging.info("invalid sha1")
        user.passwd = '*****'
        return user
    except Exception as e:
        logging.exception(e)
        return None
   
#开始定义API
#GET型方法
#获取主页面
@get("/")
def index():
    return {
        '__template__': 'index.html'
    }

#获取登录页
@get('/login')
def login():
    return {
        '__template__': 'login.html'
    }

#获取注册页
@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }

#退出登录
@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info("user signed out")
    return {'__template__': 'index.html'}

#POST方法
#登录验证
@post('/api/authenticate')
def authenticate(*, email, passwd):
    #假设邮箱和密码值是有效的，直接检查用户是否存在
    users = yield from User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIError('email', '邮箱不存在')
    user = users[0]
    # 检查密码
    sha1_passwd = '%s:%s' %(user.id, passwd)
    s = hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest()
    if s != user.passwd:
        raise APIError('passwd', '密码错误')
    # 认证成功，设置cookie并返回用户信息
    r = web.Response()
    r.content_type = 'application/json'
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400) ,max_age=86400, httponly=True) #86400s即24小时
    user.passwd = '*****'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

    

#注册
@post('/api/users') #已修改
def api_register_user(*, email, name, passwd):
#注：直接copy的
    if not name or not name.strip(): 
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = yield from User.findAll('email=?', [email]) #中断去数据库检查是否已注册
    if len(users) > 0:
        raise APIError('register:failed', 'email', '该邮箱已被注册')
    uid = next_id() #如检验成功生成新用户的id
    sha1_passwd = '%s:%s' % (uid, passwd) #结合id对用户密码加密
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())#填写数据库的user表
    yield from user.save() #中断调用协程进行保存
    '''
    暂时未能实现
    # 注册成功跳转登录页
    return "重定向失败" 
    '''
    # make session cookie:
    r = web.Response()
    #r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r #123
