import os
import yaml
import crypto_util

from dbpool import DBPool

pwd = os.path.dirname(__file__)
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
    db = db_conf['db']
    db_pool = DBPool(host, port, user, password, db)


def select(sql, params=()):
    with db_pool.conn() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(sql, params)
                return cursor.fetchall()
            except Exception as error:
                conn.rollback()
                raise error


def execute(sql, params=()):
    with db_pool.conn() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(sql, params)
                conn.commit()
            except Exception as error:
                conn.rollback()
                raise error


def executemany(sql, param_list=None):
    with db_pool.conn() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.executemany(sql, param_list)
                conn.commit()
            except Exception as error:
                conn.rollback()
                raise error
