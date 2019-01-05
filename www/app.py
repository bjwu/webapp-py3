import logging

import asyncio
from aiohttp import web

logging.basicConfig(level = logging.INFO)

def index(request):
    return web.Response(body = b'<h1>Awesome</h1>', content_type='text/html')



# 把一个generator标记为coroutine类型，然后把这个coroutine扔到Eventloop中执行
async def init(loop):
    app = web.Application(loop = loop)
    app.router.add_route('GET', '/', index)
    srv = await loop.create_server(app._make_handler(), '127.0.0.1', 9001)
    logging.info('server started at http://127.0.0.1:9001...')
    return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
