import hashlib
import re
import string
import random


def get_file_md5sum(file):
    m = hashlib.md5()
    with open(file, 'rb') as f:
        while True:
            file_data = f.read(2048)
            if not file_data:
                break

            m.update(file_data)
    return m.hexdigest()


def generate_random_str(length=32):
    """
    生成一个指定长度的随机字符串，其中
    string.digits=[0-9]
    string.ascii_letters=[a-z][A-Z]
    """
    str_list = [random.choice(string.digits + string.ascii_letters) for _ in range(length)]
    random_str = ''.join(str_list)
    return random_str


def log2sql(log: str):
    datetime_pattern = r'(\d{4}-\d{1,2}-d{1,2}\s\d{1,2}:\d{1,2}:\d{1,2})'
    # datetime_repl = lambda x: '"{}"'.format(x.group())
    result = []
    for s in log.strip().split('\n'):
        sql, params = eval(s)
        for param in params:
            if isinstance(param, int):
                sql = sql.replace('%s', str(param), 1)
            else:
                sql = sql.replace('%s', '\'{}\''.format(str(param)), 1)
        sql = sql.replace("None", "NULL")
        sql = re.sub(pattern=datetime_pattern, repl=lambda x: '"{}"'.format(x.group()), string=sql)
        result.append(sql)
    return result
