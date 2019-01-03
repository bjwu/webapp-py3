

import asyncio, aiomysql

import logging
logging.basicConfig(level = logging.INFO)

def log(sql):
    logging.info("SQL: %s" %sql)



# 创建全局连接池，每个http请求都可以从连接池中直接获取数据库链接
# 不必频繁的打开和关闭数据库链接
async def create_pool(loop, **kw):
    logging.info('create database connection pool')
    global __pool
    __pool = await aiomysql.create_pool(
        host = kw.get('host', 'localhost'),
        port = kw.get('port', 3306),
        user = kw['user'],
        password = kw['password'],
        db = kw['db'],
        charset = kw.get('charset', 'utf-8'),
        autocommit = kw.get('autocommit', True),
        maxsize = kw.get('maxsize', 10),
        minsize = kw.get('minsize', 1),
        loop = loop
    )

# SELECT
# size: number of rows to return
async def select(sql, args, size = None):
    log(sql)
    global __pool
    with (await __pool) as conn:
        # A cursor which returns results as a dict
        cur = await conn.cursor(aiomysql.DictCursor)
        # yield from cursor.execute('SELECT * FROM t1 WHERE id=?', (5,))
        await cur.execute(sql.replace('?', '%s'), args or ())
        if size:
            rs = await cur.fetchmany(size)
        else:
            rs = await cur.fetchall()
            await cur.close()
        logging.info('rows returned: %s' %len(rs))
        return rs

# INSERT, UPDATE, DELETE
async def execute(sql, args):
    log(sql)
    with (await __pool) as conn:
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?','%s'), args)
            affected = cur.rowcount
            await cur.close()
        except BaseException as e:
            raise
        return affected

def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)

class Field(object):

    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s,%s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='bigint'):
        super().__init__(name, ddl, primary_key, default)

# 把class看成是metaclass创建出来的实例
# metaclass是类的模版，所以必须从'type'类型派生，'type'是所有类的元类
class ModelMetaclass(type):
    # __new__ 是在__init__之前被调用的特殊方法
    # __new__是用来创建对象并返回的方法
    # 这里，创建的对象是类，我们希望能够自定义它，所以我们这里改写__new__
    def __new__(cls, name, bases, attrs):
        # 排除Model类本身
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        # 获取table名称
        tableName = attrs.get('__table__', None) or name
        logging.info('found model %s (table: %s)' %(name, tableName))
        # 获取所有的Field和主键名
        mappings = dict()
        fields = []
        primaryKey = None
        # k:key, v:value
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info(' found mapping: %s ==> %s' %(k, v))
                mappings[k] = v
                if v.primary_key:
                    # 找到主健
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_field = list(map(lambda f: '`%s`' %f, fields))
        attrs['__mappings__'] = mappings
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey
        attrs['__fields__'] = fields # 除主键外的属性名
        attrs['__select__'] = 'select `%s`, %s from `%s`' %(primaryKey, ', '.join(escaped_field), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) value (%s)' %(tableName, ', '.join(escaped_field), primaryKey, create_args_string(len(escaped_field)+1))
        attrs['__update__'] = 'update `%s` set %s where `%s` =?' % (tableName, ', '.join(map(lambda f:'`%s`=?' %(mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' %(tableName, primaryKey)
        # 这里返回的对象attrs已被更新
        return type.__new__(cls, name, bases, attrs)

# 定义Model, 从dict继承，又可以像引用普通字段那样写（user.id）
class Model(dict, metaclass = ModelMetaclass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' %(key, str(value)))
                setattr(self, key, value)
        return value


# ORM
# 创建实例： user = User(id = 123, name = 'Jack')
# 存入数据库： user.insert()
# 查询所有User对象： users = User.findAll()
class User(Model):
    # 以下三个属性没有self. ，所以是类的属性，不是实例的属性
    # 所以，在类级别上定义的属性用来描述User对象和表的对应关系
    # 而实例属性必须通过__init__()来初始化
    __table__ = 'users'

    id = IntegerField(primary_key = True)
    name = StringField()









