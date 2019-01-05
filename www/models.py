

import time, uuid

from orm import Model, StringField, BooleanField, FloatField, TextField

# 生成id
def next_id():
    return '%015d%s000' % (int(time.time()*1000), uuid.uuid4().hex)

# ORM
# 创建实例： user = User(id = 123, name = 'Jack')
# 存入数据库： user.insert()
# 查询所有User对象： users = User.findAll()
class User(Model):
    # 以下三个属性没有self. ，所以是类的属性，不是实例的属性
    # 所以，在类级别上定义的属性用来描述User对象和表的对应关系
    # 而实例属性必须通过__init__()来初始化
    # 由于可以传入关键字参数，所以不冲突
    __table__ = 'users'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    email = StringField(ddl='varchar(50)')
    passwd = StringField(ddl='varchar(50)')
    admin = BooleanField()
    name = StringField(ddl='varchar(50)')
    image = StringField(ddl='varchar(500)')
    # 用time而不用datetime， 防止时区转换问题
    created_at = FloatField(default=time.time)


class Blog(Model):
    __table__ = 'blogs'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    name = StringField(ddl='varchar(50)')
    summary = StringField(ddl='varchar(50)')
    content = TextField()
    created_at = FloatField(default=time.time)

class Comment(Model):
    __table__ = 'comment'

    id = StringField(primary_key=True, default=next_id, ddl='varchar(50)')
    blog_id = StringField(ddl='varchar(50)')
    user_id = StringField(ddl='varchar(50)')
    user_name = StringField(ddl='varchar(50)')
    user_image = StringField(ddl='varchar(500)')
    content = TextField()
    created_at = FloatField(default=time.time)


