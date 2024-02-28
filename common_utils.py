import hashlib
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
