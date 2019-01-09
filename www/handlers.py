#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'WU Bijia'


import re, time, json, logging, hashlib, base64, asyncio
from coroweb import get, post
from models import User, Comment, Blog

@get('/')
async def index():
    users = await User.findAll()
    return {
        '__template__': 'test.html',
        'users': users
    }