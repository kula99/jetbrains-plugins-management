import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests
import yaml
from deprecated import deprecated
from lxml import etree

import downloader as dl
import server_dao
from common_utils import generate_random_str, get_file_md5sum
from log_utils import logger


class PluginsHandler:

    def __init__(self):
        app_dir = os.path.split(os.path.realpath(__file__))[0]
        self.work_dir = app_dir
        # self.plugins_db = ''.join([os.path.dirname(__file__), '/', 'plugins.db'])
        self.plugins_store_dir = None

        self.proxies = None
        self.logger = logger

        with open(''.join([app_dir, '/', 'application.yaml']), 'r') as f:
            app_conf = yaml.safe_load(f)

        self.jetbrains_plugins_site = app_conf['jetbrains_plugins_site']
        self.repo_url = app_conf['repo_url']
        self.nexus_repo_url = app_conf['nexus']['repo_url']
        self.intellij_public = app_conf['nexus']['intellij_public']
        self.intellij_releases = app_conf['nexus']['intellij_releases']
        self.user_agent = app_conf['user_agent']
        if app_conf['work_dir']:
            self.work_dir = app_conf['work_dir']

        self.init_path()

        proxy_conf = app_conf['proxy']
        if proxy_conf['enable']:
            self.proxies = {'https': proxy_conf['address'],
                            'http': proxy_conf['address'],
                            }

    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.init_path()

    def init_path(self):
        self.plugins_store_dir = ''.join([self.work_dir, '/plugins/'])

    def get_supported_plugins_list(self, product_code, build_version):
        """
        查询所有支持指定IDE版本的插件信息，并将查询结果xml保存到本地
        :return: None
        """
        headers = {
            'User-Agent': self.user_agent
        }

        idea_version = ''.join([product_code, '-', build_version])
        payload = {'build': idea_version}
        dl.download_file(''.join([self.jetbrains_plugins_site, 'plugins/list/']), store_dir=self.work_dir,
                         file_name=''.join(['/plugins_list_', idea_version, '.xml']), overwrite=True,
                         headers=headers, params=payload, proxies=self.proxies)

    def save_plugins_info(self, product_code, build_version):
        """
        解析下载的插件xml文件，将插件信息保存至数据库
        :return: None
        """
        idea_version = ''.join([product_code, '-', build_version])
        plugins_list = ''.join([self.work_dir, '/plugins_list_', idea_version, '.xml'])
        tree = etree.parse(plugins_list, etree.XMLParser(strip_cdata=False, resolve_entities=False))
        root = tree.getroot()
        for node_idea_plugin in root.iter('idea-plugin'):
            node_name_text = node_idea_plugin.find('name').text
            node_id_text = node_idea_plugin.find('id').text
            node_description_text = node_idea_plugin.find('description').text
            node_version_text = node_idea_plugin.find('version').text
            node_change_notes_text = node_idea_plugin.find('change-notes').text
            node_idea_version = node_idea_plugin.find('idea-version')
            attr_idea_version = node_idea_version.attrib
            attr_since_build = attr_idea_version.get('since-build')
            attr_until_build = attr_idea_version.get('until-build')
            node_vendor = node_idea_plugin.find('vendor')
            node_rating_text = node_idea_plugin.find('rating').text
            attr_archive_size = node_idea_plugin.attrib.get('size')
            attr_release_time = node_idea_plugin.attrib.get('date')
            nodes_tags = node_idea_plugin.findall('tags')
            tags_content = ''
            for tag in nodes_tags:
                tags_content = ''.join([tags_content, tag.text, ','])

            if len(tags_content) > 0:
                tags_content = tags_content[:-1]

            server_dao.add_new_plugin_base_info(node_name_text, node_id_text, node_description_text)

            vendor_id = None
            if node_vendor is not None:
                node_vendor_text = node_vendor.text
                attr_vendor_email = node_vendor.attrib.get('email')
                if node_vendor_text is None:
                    node_vendor_text = attr_vendor_email
                attr_vendor_url = node_vendor.attrib.get('url')

                query_vendor_info = server_dao.check_vendor_info(node_vendor_text, attr_vendor_email, attr_vendor_url)

                if query_vendor_info:
                    vendor_id = query_vendor_info.id
                    if query_vendor_info.name != node_vendor_text or query_vendor_info.email != attr_vendor_email or \
                            query_vendor_info.url != attr_vendor_url:
                        server_dao.update_vendor_info(vendor_id, node_vendor_text, attr_vendor_email, attr_vendor_url)
                else:
                    vendor_id = generate_random_str()
                    server_dao.add_vendor_info(vendor_id, node_vendor_text, attr_vendor_email, attr_vendor_url)

            server_dao.add_new_plugin_version_info(node_id_text, node_version_text, node_change_notes_text,
                                                   attr_since_build, attr_until_build, node_rating_text,
                                                   attr_archive_size, datetime.fromtimestamp(int(attr_release_time)/1000),
                                                   tags_content, vendor_id)

            server_dao.move_old_support_version(node_id_text, re.sub(r'(%s=[-+]).*', '', node_version_text),
                                                [(product_code, build_version)])

            server_dao.remove_old_ide_support_version(node_id_text,
                                                      re.sub(r'(%s=[-+]).*', '', node_version_text),
                                                      product_code, build_version)

            server_dao.add_new_support_version([(node_id_text, node_version_text, product_code, build_version)])

    def generate_update_plugins_xml(self, product_code, build_version, is_download=False):
        """
        生成updatePlugins.xml文件，并下载对应版本的插件
        :return:
        """
        root = etree.Element('plugins')

        query_result = server_dao.get_latest_plugins_by_ide(product_code, build_version)
        if is_download:
            for row in query_result.namedtuples().iterator():
                logger.debug('name = {}, id = {}'.format(row.name, row.id))

                download_info = server_dao.get_download_info(row.id, row.version)
                if download_info:
                    logger.info('[{}][{}] has been downloaded, skip'.format(row.id, row.version))
                    self.generate_node_info(download_info.archive_name, root, row, mode='local')
                    continue

                logger.info('begin to download [{}][{}]'.format(row.id, row.version))
                plugin_archive_name, file_md5sum = self.download_plugin(row.id, row.version)
                # 下载成功再写入xml文件
                if plugin_archive_name:
                    logger.info('download [{}][{}] finished, save info'.format(row.id, row.version))
                    server_dao.add_new_download_info(row.id, row.version, plugin_archive_name, file_md5sum)

                    self.generate_node_info(plugin_archive_name, root, row, mode='local')
        else:
            for row in query_result.namedtuples().iterator():
                self.generate_node_info(row.name, root, row)

        self.write_xml(product_code, build_version, root)

        # plugins_dir = Path(self.plugins_store_dir)
        # if not plugins_dir.exists():
        #     plugins_dir.mkdir(parents=True, exist_ok=True)
        #
        # update_plugins_xml = ''.join([self.plugins_store_dir, 'updatePlugins', '-',
        #                               product_code, '-', build_version, '.xml'])
        # with open(update_plugins_xml, mode='wb') as f:
        #     f.write(etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8'))

    @deprecated
    def download_plugin(self, plugin_id, version):
        """
        下载插件
        :param plugin_id: 插件id
        :param version: 插件版本
        :return: 插件包的名称和md5值
        """
        plugin_update_archive = None
        file_md5sum = None

        headers = {
            'User-Agent': self.user_agent
        }

        payload = {'pluginId': plugin_id, 'version': version}

        plugins_dir_str = ''.join([self.plugins_store_dir, plugin_id.replace(' ', '_'), '/', version, '/'])
        plugins_dir = Path(plugins_dir_str)
        if not plugins_dir.exists():
            plugins_dir.mkdir(parents=True, exist_ok=True)
        try:
            real_location, plugin_file_path = dl.download_file(
                ''.join([self.jetbrains_plugins_site, 'plugin/download']),
                headers=headers, params=payload, proxies=self.proxies, store_dir=plugins_dir_str)

            plugin_update_archive = plugin_file_path[plugin_file_path.rfind('/') + 1:]
            file_md5sum = get_file_md5sum(plugin_file_path)

            self.download_extra_file('.blockmap.zip', real_location=real_location,
                                     headers=headers, plugin_file_path=plugin_file_path)
            self.download_extra_file('.hash.json', real_location=real_location,
                                     headers=headers, plugin_file_path=plugin_file_path)

        except Exception as e:
            self.logger.exception('[{}][{}] download failed'.format(plugin_id, version), e)
            shutil.rmtree(plugins_dir)
            plugin_update_archive = None
            file_md5sum = None

        return plugin_update_archive, file_md5sum

    def download_extra_file(self, extra_suffix, real_location, headers, plugin_file_path):
        """
        下载附加文件，如blockmap和hash json文件
        :param extra_suffix: 附加文件后缀名称
        :param real_location: 插件实际的下载地址
        :param headers: 请求头
        :param plugin_file_path: 插件本地保存绝对路径
        :return:
        """
        extra_file_path = ''.join([plugin_file_path, extra_suffix])
        if not Path(extra_file_path).exists():
            extra_url = ''.join([real_location[:real_location.find('?')], extra_suffix,
                                 real_location[real_location.find('?'):]])
            plugin_store_dir = plugin_file_path[:plugin_file_path.rfind('/') + 1]
            dl.download_file(extra_url, headers=headers, proxies=self.proxies, store_dir=plugin_store_dir)

    def generate_node_info(self, plugin_archive_name, root, plugin_info, mode='nexus'):
        node_plugin = etree.SubElement(root, 'plugin')
        node_plugin.set('id', plugin_info.id)
        if mode == 'nexus':
            node_plugin.set('url', self.format_nexus_url(plugin_info))
        else:
            node_plugin.set('url', ''.join([self.repo_url, plugin_info.id.replace(' ', '_'), '/',
                                            plugin_info.version, '/', plugin_archive_name]))
        node_plugin.set('version', plugin_info.version)
        node_idea_version = etree.SubElement(node_plugin, 'idea-version')
        node_idea_version.set('since-build', plugin_info.since_build)
        if plugin_info.until_build:
            node_idea_version.set('until-build', plugin_info.until_build)
        node_name = etree.SubElement(node_plugin, 'name')
        node_name.text = plugin_info.name
        node_description = etree.SubElement(node_plugin, 'description')
        node_description.text = etree.CDATA(plugin_info.description) if plugin_info.description else None
        node_change_notes = etree.SubElement(node_plugin, 'change-notes')
        node_change_notes.text = etree.CDATA(plugin_info.change_notes) if plugin_info.change_notes else None
        node_rating = etree.SubElement(node_plugin, 'rating')
        node_rating.text = plugin_info.rating
        node_vendor = etree.SubElement(node_plugin, 'vendor')
        node_vendor.text = plugin_info.vendor_name
        if plugin_info.email:
            node_vendor.set('email', plugin_info.email)
        if plugin_info.url:
            node_vendor.set('url', plugin_info.url)

    def format_nexus_url(self, plugin_info):
        return ''.join([self.nexus_repo_url,
                        self.intellij_releases if plugin_info.dev_type == 'internal' else self.intellij_public,
                        plugin_info.id.replace(' ', '+'), '/',
                        plugin_info.version, '/', plugin_info.id.replace(' ', '+'), '-',
                        plugin_info.version, plugin_info.archive_suffix])

    @staticmethod
    def get_ide_versions():
        return server_dao.get_ide_versions()

    def get_plugin_detail(self, plugin_xml_id):
        headers = {
            'User-Agent': self.user_agent
        }

        payload = {'pluginId': plugin_xml_id}
        response = requests.get(''.join([self.jetbrains_plugins_site, 'plugins/list']),
                                headers=headers, params=payload, stream=True, proxies=self.proxies)
        return response

    def get_plugin_file_suffix(self, plugin_xml_id, version):
        headers = {
            'User-Agent': self.user_agent
        }
        payload = {'pluginId': plugin_xml_id, 'version': version}
        response = requests.head(''.join([self.jetbrains_plugins_site, 'plugin/download']),
                                 headers=headers, params=payload, proxies=self.proxies)
        if response.status_code in (301, 302):
            pattern = re.compile(r'\.(?<=\.)[^.]*(?=\?)')
            return pattern.search(response.headers['Location']).group()
        else:
            return None

    def generate_all_update_plugins_xml(self):
        # 检查每个待同步的插件是否已经知道其后缀名(archive_suffix是新增字段，历史数据没有值，需要对历史数据做处理)
        plugins_without_suffix = server_dao.query_plugins_without_suffix()
        for row in plugins_without_suffix.namedtuples().iterator():
            try:
                suffix = self.get_plugin_file_suffix(row.id, row.version)

                if not row.plugin_id:  # row.plugin_id为download_info.id字段，为空表示该表没有此记录
                    server_dao.add_new_download_info(row.id, row.version,
                                                     ''.join([row.id, '-', row.version, suffix]), suffix)
                else:
                    server_dao.update_plugin_file_suffix(row.id, row.version, suffix)
            except Exception as e:
                logger.exception('check plugin suffix failed', e)

        # 按IDE版本排序获取其可用的插件
        plugins_for_xml = server_dao.query_plugins_for_update_xml()
        root = etree.Element('plugins')
        last_product_code = None
        last_build_version = None

        for row in plugins_for_xml.namedtuples().iterator():
            if not last_product_code:
                last_product_code = row.product_code
            if not last_build_version:
                last_build_version = row.build_version

            if last_build_version != row.build_version:
                self.write_xml(last_product_code, last_build_version, root)
                root = etree.Element('plugins')

            self.generate_node_info(row.name, root, row)

            last_product_code = row.product_code
            last_build_version = row.build_version

        if last_product_code and last_build_version:
            self.write_xml(last_product_code, last_build_version, root)

    def write_xml(self, product_code, build_version, root_node):
        plugins_dir = Path(self.plugins_store_dir)

        if not plugins_dir.exists():
            plugins_dir.mkdir(parents=True, exist_ok=True)
        update_plugins_xml = ''.join([self.plugins_store_dir, 'updatePlugins', '-',
                                      product_code, '-', build_version, '.xml'])
        with open(update_plugins_xml, mode='wb') as f:
            f.write(etree.tostring(root_node, pretty_print=True, xml_declaration=True, encoding='utf-8'))

    def download_plugin_archive(self, day_offset: int = 0):
        plugins_info = server_dao.get_recent_released_plugins(day_offset)

        with ThreadPoolExecutor(max_workers=5) as p:
            for row in plugins_info.namedtuples().iterator():
                url = self.format_nexus_url(row)
                logger.info('start to download [{} {}] asynchronously'.format(row.id, row.version))
                p.submit(dl.download_temp_file, url, self.work_dir)

    @staticmethod
    def update_sync_status(product_code, build_version, status):
        server_dao.update_sync_status(product_code, build_version, status)


# class PluginInfo:
#     name = None
#     id = None
#     description = None
#     version = None
#     change_notes = None
#     since_build = None
#     until_build = None
#     rating = None
#     archive_size = None
#     release_time = None
#     latest_version = 1
#     vendor_name = None
#     vendor_email = None
#     vendor_url = None
#     vendor_dev_type = None
#     archive_suffix = None
