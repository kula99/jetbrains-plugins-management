from dbutils.pooled_db import PooledDB
import pymysql


class DBPool:
    def __init__(self, host, port, user, password, db, charset='utf8mb4', min_cached=0, max_cached=0, max_shared=0,
                 max_connections=0):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db = db
        self.charset = charset
        self.min_cached = min_cached if min_cached > 0 else 0
        self.max_cached = max_cached if max_cached > 0 else 0
        self.max_shared = max_shared if max_shared > 0 else 0
        self.max_connections = max_connections if max_connections > 0 else 0

        self.pool = PooledDB(creator=pymysql,
                             mincached=self.min_cached,
                             maxcached=self.max_cached,
                             maxshared=self.max_shared,
                             maxconnections=self.max_connections,
                             host=self.host,
                             port=self.port,
                             user=self.user,
                             password=self.password,
                             db=self.db,
                             charset=self.charset)

    def conn(self):
        return self.pool.connection()
