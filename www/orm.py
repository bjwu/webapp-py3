

import aiomysql

import logging
logging.basicConfig(level = logging.INFO)

def log(sql):
    logging.info("orm.py: SQL: %s" %sql)

__pool = None

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
        charset = kw.get('charset', 'utf8'),
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
        logging.info('orm.py: rows returned: %s' %len(rs))
        return rs

# INSERT, UPDATE, DELETE
async def execute(sql, args):
    log(sql)
    global __pool
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

# 表示一列
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

class BooleanField(Field):

    def __init__(self, name=None, default=False, ddl='boolean'):
        super().__init__(name, ddl, False, default)

class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0, ddl='real'):
        super().__init__(name, ddl, primary_key, default)

class TextField(Field):

    def __init__(self, name=None, default=None, ddl='text'):
        super().__init__(name, ddl, False, default)


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
        logging.info('orm.py: found model %s (table: %s)' %(name, tableName))
        # 获取所有的Field和主键名
        mappings = dict()
        fields = []
        primaryKey = None
        # k:key, v:value
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('orm.py: found mapping: %s ==> %s' %(k, v))
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
        attrs['__select__'] = 'select %s, %s from %s' %(primaryKey, ', '.join(escaped_field), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) value (%s)' %(tableName, ', '.join(escaped_field), primaryKey, create_args_string(len(escaped_field)+1))
        attrs['__update__'] = 'update `%s` set %s where `%s` =?' % (tableName, ', '.join(map(lambda f:'`%s`=?' %(mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' %(tableName, primaryKey)
        # 这里返回的对象attrs已被更新
        return type.__new__(cls, name, bases, attrs)

# 定义Model, 从dict继承，又可以像引用普通字段那样写（user.id/ __getattr__）
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
                logging.debug('orm.py: using default value for %s: %s' %(key, str(value)))
                setattr(self, key, value)
        return value

    # @classmethod,可以直接用类名寻找方法
    @classmethod
    async def find(cls, pk):
        'find object by primary key'
        rs = await select('%s where `%s`=?' %(cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        ### cls指代该类，而该类是个dict
        return cls(**rs[0])

    # TODO: can add more kw key
    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        'find all object'
        sql = '%s' %cls.__select__
        if where:
            sql += ' where %s' %where
        if args is None:
            args = []
        orderBy = kw.get(' orderBy', None)
        if orderBy:
            sql += 'order by %s' %orderBy
        rs = await select(sql, args)
        if len(rs) == 0:
            return None
        return [cls(**r) for r in rs]

    async def update(self):
        'update object'
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('orm.py: failed to update: affected rows: %s' % rows)

    async def remove(self):
        'remove object'
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('orm.py: failed to delete record: affected rows: %s' % rows)

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('orm.py: failed to insert record: affected rows: %s' % rows)


