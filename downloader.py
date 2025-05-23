import cgi
import copy
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

DEFAULT_SECTION_SIZE = 5 * 1024 * 1024
DEFAULT_TIMEOUT = 300


def download_file(url, params=None, store_dir=os.path.dirname(__file__), file_name='unnamed', overwrite=False, **kwargs):
    """
    下载文件
    :param url: 请求地址
    :param params: 请求参数
    :param store_dir: 文件保存目录
    :param file_name: 保存的文件名
    :param overwrite: 是否覆盖已有文件
    :keyword headers: 请求头
    :keyword proxies: 代理
    :return: 实际的地址（可能产生重定向），保存的文件绝对路径
    """
    file_store_path = None
    response = requests.head(url, params=params, timeout=DEFAULT_TIMEOUT, **kwargs)
    if response.status_code in (301, 302):
        redirect_location = response.headers.get('Location')
        if redirect_location.startswith('https') or redirect_location.startswith('http'):
            url = redirect_location
        else:
            pattern = re.compile('(https?://)[^/]+')
            domain = pattern.search(url).group()
            url = ''.join([domain, redirect_location])
        return download_file(url, params=params, store_dir=store_dir, file_name=file_name,
                             overwrite=overwrite, **kwargs)

    elif response.status_code == 200:
        file_name = extract_file_name(file_name, response, url)

        file_store_path = ''.join([store_dir, file_name])
        if overwrite or not Path(file_store_path).exists():
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > DEFAULT_SECTION_SIZE:
                multi_thread_download(url, file_size=int(content_length), file_path=file_store_path,
                                      params=params, **kwargs)
            else:
                simple_download(url, file_path=file_store_path, params=params, overwrite=overwrite, **kwargs)

    return url, file_store_path


def extract_file_name(file_name, response, url):
    """
    提取文件名
    :param file_name: 缺省文件名，如果从响应中取不到文件名则默认用这个
    :param response: 请求响应
    :param url: 请求url
    :return: 文件名
    """
    content_type = response.headers['Content-Type']
    if content_type in ('application/zip', 'application/java-archive'):
        _, params = cgi.parse_header(response.headers['Content-Disposition'])
        file_name = params['filename']
    elif content_type in ('application/octet-stream', 'text/plain; charset=UTF-8', 'text/xml; charset=UTF-8'):
        pattern = re.compile('[^/]+(?!.*/)')
        search_result = pattern.search(url[:url.find('?')])
        if search_result:
            file_name = search_result.group()
    return file_name


def multi_thread_download(url, file_size=0, file_path='.', params=None, thread_count=5, **kwargs):
    """
    多线程下载文件
    :param url: 请求地址
    :param file_size: 文件大小
    :param file_path: 文件存储绝对路径
    :param params: 请求参数
    :param thread_count: 线程数，默认5
    :return:
    """
    with open(file_path, 'wb') as f:
        f.truncate()

    futures = []
    with ThreadPoolExecutor(max_workers=thread_count) as p:
        for start_pos, end_pos in calc_range(file_size):
            futures.append(p.submit(range_download, url, file_path, params, start_pos, end_pos, **kwargs))

        as_completed(futures)


def calc_range(file_size, chunk=DEFAULT_SECTION_SIZE):
    """
    计算分段数
    :param file_size: 文件大小
    :param chunk: 分段大小
    :return: 分段后的数组
    """
    arr = list(range(0, file_size, chunk))
    result = []
    for i in range(len(arr) - 1):
        start_pos, end_pos = arr[i], arr[i + 1] - 1
        result.append([start_pos, end_pos])
    start_pos, end_pos = arr[len(arr) - 1], file_size
    result.append([start_pos, end_pos])
    return result


def range_download(url, file_path='.', params=None, start_pos=0, end_pos=0, **kwargs):
    """
    分段下载
    :param url: 请求地址
    :param file_path: 文件存储绝对路径
    :param params: 请求参数
    :param start_pos: 分段开始位置
    :param end_pos: 分段结束位置
    :return: 无
    """
    range_kwargs = {}
    if kwargs:
        range_kwargs = copy.deepcopy(kwargs)
    range_kwargs['headers'].update({'Range': 'bytes={}-{}'.format(start_pos, end_pos)})
    simple_download(url, file_path=file_path, params=params, start_pos=start_pos, **range_kwargs)


def simple_download(url, file_path='.', params=None, start_pos=0, overwrite=False, **kwargs):
    """
    单线程下载
    :param url: 请求地址
    :param file_path: 文件存储绝对路径
    :param params: 请求参数
    :param start_pos: 分段开始位置，单线程默认为0
    :param overwrite: 如果目标文件已经存在，是否覆盖原文件
    :return: 无
    """
    if overwrite or not Path(file_path).exists():
        with open(file_path, 'wb') as f:
            f.truncate()

    response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT, **kwargs)
    with open(file_path, 'rb+') as f:
        if start_pos > 0:
            f.seek(start_pos)
        for chunk in response.iter_content(chunk_size=512 * 1024):
            if chunk:
                f.write(chunk)


def download_temp_file(url, tmp_dir=None, **kwargs):
    response = requests.get(url, stream=True, timeout=DEFAULT_TIMEOUT, **kwargs)
    if response.status_code == 200:
        with tempfile.NamedTemporaryFile(delete=True, dir=tmp_dir) as temp_file:
            for chunk in response.iter_content(chunk_size=512 * 1024):
                if chunk:
                    temp_file.write(chunk)
            temp_file.flush()

            # os.remove(temp_file.name)
