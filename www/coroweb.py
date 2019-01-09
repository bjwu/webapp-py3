

import functools, logging, os
import asyncio, inspect
from aiohttp import web
from urllib import parse
from apis import APIError


# 把一个函数映射为一个URL处理函数
def get(path):
    '''
    Define decorator @get('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator

def post(path):
    '''
    Define decorator @post('/post')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator

'''
下面五个函数是判断handler函数的参数
'''
def get_required_kw_args(fn):
    args = []
    # inspect.signature(fn)：返回所有形参
    # inspect.signature(fn)：返回所有形参的字典{形参名称：形参类别}
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)

def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
        return tuple(args)

def has_named_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True

def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True

def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD ):
            raise ValueError('coroweb.py: Request parameter must be the last named parameter in function: %s%s' %(fn.__name__, str(sig)))
        return found

class RequestHandler(object):
    '''
    Define request Handler class for different requests
    '''
    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_arg(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    ### A request handler must be a coroutine that accepts a Request instance as its only parameter and returns a Response instance
    async def __call__(self, request):
        kw = None
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('coroweb.py: Missing Content-type.')
                ct = request.content_type
                if ct.startwith('application/json'):
                    # Read request body decoded as json.
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('coroweb.py: JSON body must be object')
                    kw = params
                elif ct.startwith('application/x-www-form-urlencoded') or ct.startwith('multipart/form-data'):
                    # A coroutine that reads POST parameters from request body.
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest('coroweb.py: Unsupported Content-Type: %s' %ct)
            if request.method == 'GET':
                # he query string in the URL, e.g., id=10
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            # Read-only property with AbstractMatchInfo instance for result of route resolving.
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                for k, v in request.match_info.items():
                    if k in kw:
                        logging.warning('coroweb.py: Dupilicate arg name in named arg and kw args: %s' %k)
                    kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest('coroweb.py: Missing argument: %s' % name)
        logging.info('coroweb.py: call with args: %s' % str(kw))
        try:
            r = await self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, date=e.date, message=e.message)

def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))

def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('coroweb.py: @get or @post not defined in %s.' %str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info('coroweb.py: Add route %s %s => %s(%s)' %(method, path, fn.__name__, ','.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, fn))

def add_routes(app, module_name):
    #  返回字符串中最后一个"."的位置；如没有，则返回-1
    n = module_name.rfind('.')
    if n == (-1):
        # 用于动态导入模块，用于其下的模块会经常变化时
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n+1:]
        mod = getattr(__import__(module_name[:n], globals(),locals(),[name]),name)
    # dir()：返回该模块所有属性，方法列表
    for attr in dir(mod):
        # 排除掉所有属性
        if attr.startswith('__'):
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            # 排除'handler'模块里 import 的函数
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)



