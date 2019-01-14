import logging

import asyncio, json, orm, os, time, datetime
from coroweb import add_routes, add_static
from aiohttp import web
from jinja2 import Environment, FileSystemLoader

from handlers import cookie2user, COOKIE_NAME

logging.basicConfig(level = logging.INFO)


def init_jinja2(app, **kw):
    logging.info('app.py: init jinja2...')
    options = dict(
        autoescape = kw.get('autoescape', True),
        block_start_string = kw.get('block_start_string', '{%'),
        block_end_string = kw.get('block_end_string', '%}'),
        variable_start_string = kw.get('variable_start_string', '{{'),
        variable_end_string = kw.get('variable_end_string', '}}'),
        auto_reload = kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    logging.info('app.py: set jinja2 template path: %s' % path)
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filters', None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    app['__templating__'] = env

# middleware是一种拦截器，一个url在被某个函数处理前，可以经过一系列的middleware的处理
# 一个middleware可以改变url的输入，输出，甚至可以决定不继续处理而直接返回，起作用在于把通用的功能从每个url处理函数中拿出来，集中放到一个地方。例如一个记录url日志的logger
# TODO: 可以按照标准简化
async def logger_factrory(app, handler):
    async def logger(request):
        # 记录日志
        logging.info('app.py: Request: %s %s' %(request.method, request.path))
        return (await handler(request))
    return logger

###定义middle在处理URL之前，把cookie解析出来，并将登陆用户绑定到request对象上，这样，后续的URL处理函数就可以直接拿到登陆用户
async def auth_factory(app, handler):
    async def auth(request):
        logging.info('app.py: check user:%s %s' %(request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user = await cookie2user(cookie_str)
            if user:
                logging.info('app.py: set current user: %s' %user.email)
                request.__user__ = user
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            return web.HTTPFound('/signin/')
        return (await handler(request))
    return auth


async def response_factory(app, handler):
    async def response(request):
        logging.info('app.py: Response handler...')
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
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
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and t > 100 and t < 600:
                return web.Response(t, str(m))
        # default
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp
    return response

def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return '1分钟前'
    if delta < 3600:
        return '%s分钟前' % (delta // 60)
    if delta < 86400:
        return '%s小时前' % (delta // 3600)
    if delta < 604800:
        return '%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return '%s年%s月%s日' % (dt.year, dt.month, dt.day)


# 把一个generator标记为coroutine类型，然后把这个coroutine扔到Eventloop中执行
async def init(loop):
    await orm.create_pool(loop=loop, user='root', password='password', db='webapp')
    app = web.Application(loop=loop, middlewares=[logger_factrory, auth_factory, response_factory])
    init_jinja2(app, filters=dict(datetime=datetime_filter))
    add_routes(app, 'handlers')
    add_static(app)
    srv = await loop.create_server(app._make_handler(), '127.0.0.1', 9001)
    logging.info('app.py: Server started at http://127.0.0.1:9001...')
    return srv


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init(loop))
    loop.run_forever()
