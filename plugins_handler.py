import hashlib
import os
import sqlite3
from pathlib import Path

import requests
import yaml
from lxml import etree

import downloader as dl
import log_utils


def get_file_md5sum(file):
    m = hashlib.md5()
    with open(file, 'rb') as f:
        while True:
            file_data = f.read(2048)
            if not file_data:
                break

            m.update(file_data)
    return m.hexdigest()


class PluginsHandler:

    def __init__(self):
        self.work_dir = os.path.dirname(__file__)
        self.plugins_db = ''.join([os.path.dirname(__file__), '/', 'plugins.db'])
        self.plugins_store_dir = None
        # self.update_plugins_xml = None

        self.proxies = None
        self.logger = log_utils.get_simple_logger()

        with open(''.join([os.path.dirname(__file__), '/', 'application.yaml']), 'r') as f:
            app_conf = yaml.safe_load(f)

        default_conf = app_conf['default']
        self.jetbrains_plugins_site = default_conf['jetbrains_plugins_site']
        self.repo_url = default_conf['repo_url']
        self.user_agent = default_conf['user_agent']
        if default_conf['work_dir']:
            self.work_dir = default_conf['work_dir']

        self.init_path()

        proxy_conf = app_conf['proxy']
        if proxy_conf['enable']:
            self.proxies = {'http': proxy_conf['address'],
                            'https': proxy_conf['address']
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
        解析下载的插件xml文件，将插件信息保存至本地sqlite
        :return: None
        """
        conn = sqlite3.connect(self.plugins_db)
        idea_version = ''.join([product_code, '-', build_version])
        plugins_list = ''.join([self.work_dir, '/plugins_list_', idea_version, '.xml'])
        tree = etree.parse(plugins_list, etree.XMLParser(strip_cdata=False))
        root = tree.getroot()
        for node_idea_plugin in root.iter('idea-plugin'):
            node_name = node_idea_plugin.find('name').text
            node_id = node_idea_plugin.find('id').text
            node_description = node_idea_plugin.find('description').text
            node_version = node_idea_plugin.find('version').text
            node_change_notes = node_idea_plugin.find('change-notes').text
            node_idea_version = node_idea_plugin.find('idea-version')
            attr_idea_version = node_idea_version.attrib
            attr_since_build = attr_idea_version.get('since-build')
            attr_until_build = attr_idea_version.get('until-build')
            node_rating = node_idea_plugin.find('rating').text
            attr_archive_size = node_idea_plugin.attrib.get('size')
            attr_release_time = node_idea_plugin.attrib.get('date')
            nodes_tags = node_idea_plugin.findall('tags')
            tags_content = ''
            for tag in nodes_tags:
                tags_content = ''.join([tags_content, tag.text, ','])

            if len(tags_content) > 0:
                tags_content = tags_content[:-1]

            add_new_plugin = '''
                insert into plugins_info(name, id, description, version, change_notes, since_build, until_build, 
                                         rating, archive_size, release_time, tags)
                select ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime(?/1000, 'unixepoch', 'localtime'), ?
                 where not exists (select 1 from plugins_info where id = ? and version = ?)
            '''
            conn.execute(add_new_plugin, (node_name, node_id, node_description, node_version, node_change_notes,
                                          attr_since_build, attr_until_build, node_rating, attr_archive_size,
                                          attr_release_time, tags_content, node_id, node_version))

            update_old_support_version = '''
                update support_version set latest_version = 0, update_time = datetime('now', 'localtime')
                 where id = ? and version < ? and product_code = ? and build_version =? and latest_version = 1
            '''
            conn.execute(update_old_support_version, (node_id, node_version, product_code, build_version))

            add_support_version = '''
                insert or ignore into support_version(id, version, product_code, build_version)
                values(?, ?, ?, ?)
            '''

            conn.execute(add_support_version, (node_id, node_version, product_code, build_version))

        conn.commit()
        conn.close()

    def generate_update_plugins_xml(self, product_code, build_version):
        """
        生成updatePlugins.xml文件，并下载对应版本的插件
        :return:
        """
        conn = sqlite3.connect(self.plugins_db)

        root = etree.Element('plugins')

        get_latest_plugins = '''
            select a.name, a.id, a.description, a.version, a.change_notes, a.since_build, a.until_build, a.rating
              from plugins_info a, white_list b, support_version c
             where a.id = b.plugin_id
               and a.id = c.id
               and a.version = c.version
               and c.product_code = ?
               and c.build_version = ?
               and c.latest_version = 1
        '''

        query_result = conn.execute(get_latest_plugins, (product_code, build_version))
        for row in query_result:
            plugin_info = PluginInfo()
            plugin_info.name = row[0]
            plugin_info.id = row[1]
            plugin_info.description = row[2]
            plugin_info.version = row[3]
            plugin_info.change_notes = row[4]
            plugin_info.since_build = row[5]
            plugin_info.until_build = row[6]
            plugin_info.rating = row[7]
            self.logger.debug('name = {}, id = {}'.format(plugin_info.name, plugin_info.id))

            query_download_info = '''
                select id, version, archive_name, md5 from download_info where id = ? and version = ?
            '''

            query_result_di = conn.execute(query_download_info, (plugin_info.id, plugin_info.version))
            download_info = query_result_di.fetchone()
            if download_info:
                # print('{} {} has been downloaded, skip'.format(plugin_info.id, plugin_info.version))
                self.logger.info('[{}][{}] has been downloaded, skip'.format(plugin_info.id, plugin_info.version))
                self.generate_node_info(download_info[2], root, plugin_info)
                continue

            self.logger.info('begin to download [{}][{}]'.format(plugin_info.id, plugin_info.version))
            plugin_archive_name, file_md5sum = self.download_plugin(plugin_info.id, plugin_info.version)
            # 下载成功再写入xml文件
            if plugin_archive_name:
                self.logger.info('download [{}][{}] finished, save info'.format(plugin_info.id, plugin_info.version))
                record_download_file_md5sum = '''
                    insert into download_info(id, version, archive_name, md5) values(?, ?, ?, ?)
                '''
                conn.execute(record_download_file_md5sum,
                             (plugin_info.id, plugin_info.version, plugin_archive_name, file_md5sum))

                self.generate_node_info(plugin_archive_name, root, plugin_info)

        conn.commit()
        conn.close()

        plugins_dir = Path(self.plugins_store_dir)
        if not plugins_dir.exists():
            plugins_dir.mkdir(parents=True, exist_ok=True)

        update_plugins_xml = ''.join([self.plugins_store_dir, 'updatePlugins', '-',
                                      product_code, '-', build_version, '.xml'])
        with open(update_plugins_xml, mode='wb') as f:
            f.write(etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8'))

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

        try:
            plugins_dir_str = ''.join([self.plugins_store_dir, plugin_id.replace(' ', '_'), '/', version, '/'])
            plugins_dir = Path(plugins_dir_str)
            if not Path(plugins_dir_str).exists():
                plugins_dir.mkdir(parents=True, exist_ok=True)

            real_location, plugin_file_path = dl.download_file(
                ''.join([self.jetbrains_plugins_site, 'plugin/download']),
                headers=headers, params=payload, proxies=self.proxies, store_dir=plugins_dir_str)

            plugin_update_archive = plugin_file_path[plugin_file_path.rfind('/') + 1:]
            file_md5sum = get_file_md5sum(plugin_file_path)

            self.download_extra_file('.blockmap.zip', real_location=real_location,
                                     headers=headers, plugin_file_path=plugin_file_path)
            self.download_extra_file('.hash.json', real_location=real_location,
                                     headers=headers, plugin_file_path=plugin_file_path)

        except Exception:
            self.logger.error('[{}][{}] download failed'.format(plugin_id, version), exc_info=True)

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

    def generate_node_info(self, plugin_archive_name, root, plugin_info):
        node_plugin = etree.SubElement(root, 'plugin')
        node_plugin.set('id', plugin_info.id)
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
        node_description.text = etree.CDATA(plugin_info.description)
        node_change_notes = etree.SubElement(node_plugin, 'change-notes')
        node_change_notes.text = etree.CDATA(plugin_info.change_notes)
        node_rating = etree.SubElement(node_plugin, 'rating')
        node_rating.text = plugin_info.rating

    def get_ide_versions(self):
        conn = sqlite3.connect(self.plugins_db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        query_ide_versions = '''
            select product_code, build_version, version from ide_version 
             order by product_code, build_version desc
        '''
        cur.execute(query_ide_versions)

        ide_versions = cur.fetchall()
        cur.close()
        conn.close()

        return ide_versions

    def get_plugin_detail(self, plugin_xml_id):
        headers = {
            'User-Agent': self.user_agent
        }

        payload = {'pluginId': plugin_xml_id}
        response = requests.get(''.join([self.jetbrains_plugins_site, 'plugins/list']),
                                headers=headers, params=payload, stream=True, proxies=self.proxies)
        return response


class PluginInfo:
    name = None
    id = None
    description = None
    version = None
    change_notes = None
    since_build = None
    until_build = None
    rating = None
    archive_size = None
    release_time = None
    latest_version = 1
