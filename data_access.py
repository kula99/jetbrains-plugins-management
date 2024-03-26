import logging
import os
import re

import yaml
from peewee import *
from playhouse.pool import PooledMySQLDatabase
from playhouse.shortcuts import ThreadSafeDatabaseMetadata

import crypto_util

pwd = os.path.split(os.path.realpath(__file__))[0]
with open(''.join([pwd, '/', 'application.yaml']), 'r') as f:
    app_conf = yaml.safe_load(f)
    db_conf = app_conf['database']
    host = db_conf['host']

    port = db_conf['port']
    user = db_conf['user']
    password = db_conf['password']
    if str.startswith(password, '{RSA}'):
        sys_pub_key = db_conf['sys_pub_key']
        app_pri_key = db_conf['app_pri_key']
        password = crypto_util.decrypt(''.join([pwd, '/', sys_pub_key]), ''.join([pwd, '/', app_pri_key]),
                                       bytes.fromhex(password[len('{RSA}'):]))
    database = db_conf['db']
    db = PooledMySQLDatabase(database,
                             max_connections=32,
                             host=host,
                             port=port,
                             user=user,
                             password=password,
                             charset='utf8mb4')

    peewee_conf = app_conf['peewee']
    log_sql = peewee_conf['log_sql']
    if log_sql:
        logger = logging.getLogger('peewee')
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(module)s(%(lineno)d) - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)


def camel_to_snake(camel_str):
    if not re.search(r'[a-z]', camel_str) or not re.search(r'[A-Z]', camel_str):
        return camel_str

    snake_str = re.sub(r'(?<!^)(?=[A-Z])', '_', camel_str).lower()
    return snake_str


def make_table_name(model):
    """
    根据类名转换为表名，类名为驼峰式，表名为下划线
    :param model:
    :return:
    """
    model_name = model.__name__
    return camel_to_snake(model_name)


class BaseModel(Model):
    create_time = DateTimeField(constraints=[SQL("DEFAULT current_timestamp()")])
    update_time = DateTimeField(constraints=[SQL("DEFAULT current_timestamp()")])

    class Meta:
        database = db
        model_metadata_class = ThreadSafeDatabaseMetadata
        table_function = make_table_name


class DownloadInfo(BaseModel):
    id = CharField()
    version = CharField()
    archive_name = CharField(null=True)
    md5 = CharField(null=True)
    archive_suffix = CharField(null=True)

    class Meta:
        indexes = (
            (('id', 'version'), True),
        )
        primary_key = CompositeKey('id', 'version')


class IdeVersion(BaseModel):
    product_code = CharField()
    build_version = CharField()
    version = CharField(null=True)
    last_sync_status = CharField(null=True)
    last_sync_time = DateTimeField(null=True)

    class Meta:
        indexes = (
            (('build_version', 'product_code'), True),
        )
        primary_key = CompositeKey('build_version', 'product_code')


class PluginsBaseInfo(BaseModel):
    name = CharField()
    id = CharField(primary_key=True)
    description = TextField(null=True)


class PluginsVersionInfo(BaseModel):
    id = CharField()
    version = CharField()
    change_notes = TextField(null=True)
    since_build = CharField(null=True)
    until_build = CharField(null=True)
    rating = CharField(null=True)
    archive_size = IntegerField(null=True)
    release_time = DateTimeField(null=True)
    tags = CharField(null=True)
    vendor_id = CharField(null=True)

    class Meta:
        indexes = (
            (('id', 'version'), True),
        )
        primary_key = CompositeKey('id', 'version')


class SupportVersion(BaseModel):
    id = CharField()
    version = CharField()
    product_code = CharField()
    build_version = CharField()
    latest_version = IntegerField(constraints=[SQL("DEFAULT 1")], null=True)

    class Meta:
        indexes = (
            (('id', 'version', 'build_version', 'product_code'), True),
        )
        primary_key = CompositeKey('build_version', 'id', 'product_code', 'version')


class SupportVersionHistory(SupportVersion):
    latest_version = IntegerField(constraints=[SQL("DEFAULT 0")], null=True)


class TmpTicket(BaseModel):
    ticket = CharField(primary_key=True)
    access_token = CharField()
    user_name = CharField(null=True)
    step = IntegerField(constraints=[SQL("DEFAULT 0")])


class VendorInfo(BaseModel):
    id = CharField(primary_key=True)
    name = CharField()
    email = CharField(null=True)
    url = CharField(null=True)
    dev_type = CharField(null=True)


class WhiteList(BaseModel):
    plugin_id = CharField(primary_key=True)
    enabled = CharField(constraints=[SQL("DEFAULT '1'")])


class UploadBatchInfo(BaseModel):
    batch_no = CharField(primary_key=True)
    plugin_id = CharField()
    plugin_version = CharField()
    archive_name = CharField(null=True)
    archive_suffix = CharField(null=True)
    since_build = CharField(null=True)
    until_build = CharField(null=True)


class UploadChunkInfo(BaseModel):
    batch_no = CharField()
    chunk_order = IntegerField(constraints=[SQL("DEFAULT 1")])
    saved_path = CharField()

    class Meta:
        primary_key = CompositeKey('batch_no', 'chunk_order')
