import hashlib
import os
import random
import re
import shutil
import string
from pathlib import Path

import requests
import yaml
from lxml import etree

import db_operator
import downloader as dl
from log_utils import logger


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


class PluginsHandler:

    def __init__(self):
        self.work_dir = os.path.dirname(__file__)
        self.plugins_db = ''.join([os.path.dirname(__file__), '/', 'plugins.db'])
        self.plugins_store_dir = None

        self.proxies = None
        self.logger = logger

        with open(''.join([os.path.dirname(__file__), '/', 'application.yaml']), 'r') as f:
            app_conf = yaml.safe_load(f)

        self.jetbrains_plugins_site = app_conf['jetbrains_plugins_site']
        self.repo_url = app_conf['repo_url']
        self.nexus_repo_url = app_conf['nexus_repo_url']
        self.user_agent = app_conf['user_agent']
        if app_conf['work_dir']:
            self.work_dir = app_conf['work_dir']

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

            add_new_plugin_base_info = '''
                insert into plugins_base_info(name, id, description) values(%s, %s, %s)
                on duplicate key update name = %s, description = %s
            '''
            db_operator.execute(add_new_plugin_base_info, (node_name_text, node_id_text, node_description_text,
                                                           node_name_text, node_description_text))

            vendor_id = None
            if node_vendor is not None:
                node_vendor_text = node_vendor.text
                attr_vendor_email = node_vendor.attrib.get('email')
                if node_vendor_text is None:
                    node_vendor_text = attr_vendor_email
                attr_vendor_url = node_vendor.attrib.get('url')

                check_vendor_info = '''
                    select id, name, email, url 
                      from vendor_info
                     where (name = %s or name is null)
                       and (email = %s or email is null)
                       and (url = %s or url is null)
                '''
                query_vendor_info = db_operator.select(check_vendor_info,
                                                       (node_vendor_text, attr_vendor_email, attr_vendor_url))

                if query_vendor_info:
                    exist_vendor_info = query_vendor_info[0]
                    vendor_id = exist_vendor_info[0]
                    if exist_vendor_info[1] != node_vendor_text or exist_vendor_info[2] != attr_vendor_email or \
                            exist_vendor_info[3] != attr_vendor_url:
                        update_vendor_info = '''
                            update vendor_info
                               set name = %s, email = %s, url = %s, update_time = now()
                             where id = %s
                        '''
                        db_operator.execute(update_vendor_info, (exist_vendor_info[1], exist_vendor_info[2],
                                                                 exist_vendor_info[3], vendor_id))
                else:
                    vendor_id = generate_random_str()
                    add_vendor_info = '''
                        insert into vendor_info(id, name, email, url) values (%s, %s, %s, %s)
                    '''
                    db_operator.execute(add_vendor_info,
                                        (vendor_id, node_vendor_text, attr_vendor_email, attr_vendor_url))

            add_new_plugin = '''
                insert into plugins_version_info(id, version, change_notes, since_build, until_build, 
                                                 rating, archive_size, release_time, tags, vendor_id)
                select %s, %s, %s, %s, %s, %s, %s, from_unixtime(%s/1000, '%%Y-%%m-%%d %%H:%%i:%%s'), %s, %s
                 where not exists (select 1 from plugins_version_info where id = %s and version = %s)
            '''
            db_operator.execute(add_new_plugin, (node_id_text, node_version_text, node_change_notes_text,
                                                 attr_since_build, attr_until_build, node_rating_text, attr_archive_size,
                                                 attr_release_time, tags_content, vendor_id, node_id_text, node_version_text))

            move_old_support_version = '''
                insert ignore into support_version_history(id, version, product_code, build_version)
                select id, version, product_code, build_version from support_version
                 where id = %s and version_compare(version, %s) > 0
                   and product_code = %s and build_version = %s
            '''
            db_operator.execute(move_old_support_version, (node_id_text, re.sub(r'(%s=[-+]).*', '', node_version_text),
                                                           product_code, build_version))

            remove_old_support_version = '''
                delete from support_version
                 where id = %s and version_compare(version, %s) > 0
                   and product_code = %s and build_version = %s
            '''
            db_operator.execute(remove_old_support_version, (node_id_text, re.sub(r'(%s=[-+]).*', '', node_version_text),
                                                             product_code, build_version))

            add_support_version = '''
                insert ignore into support_version(id, version, product_code, build_version)
                values(%s, %s, %s, %s)
            '''
            db_operator.execute(add_support_version, (node_id_text, node_version_text, product_code, build_version))

    def generate_update_plugins_xml(self, product_code, build_version):
        """
        生成updatePlugins.xml文件，并下载对应版本的插件
        :return:
        """
        root = etree.Element('plugins')

        get_latest_plugins = '''
            select a.name, a.id, a.description, a.version, a.change_notes, a.since_build, a.until_build, a.rating
              from plugins_info a, white_list b, support_version c
             where a.id = b.plugin_id
               and a.id = c.id
               and a.version = c.version
               and c.product_code = %s
               and c.build_version = %s
               and c.latest_version = 1
        '''

        # query_result = conn.execute(get_latest_plugins, (product_code, build_version))
        query_result = db_operator.select(get_latest_plugins, (product_code, build_version))
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
                select id, version, archive_name, md5 from download_info where id = %s and version = %s
            '''

            # query_result_di = conn.execute(query_download_info, (plugin_info.id, plugin_info.version))
            query_result_di = db_operator.select(query_download_info, (plugin_info.id, plugin_info.version))
            if query_result_di:
                # print('{} {} has been downloaded, skip'.format(plugin_info.id, plugin_info.version))
                self.logger.info('[{}][{}] has been downloaded, skip'.format(plugin_info.id, plugin_info.version))
                download_info = query_result_di[0]
                self.generate_node_info(download_info[2], root, plugin_info)
                continue

            self.logger.info('begin to download [{}][{}]'.format(plugin_info.id, plugin_info.version))
            plugin_archive_name, file_md5sum = self.download_plugin(plugin_info.id, plugin_info.version)
            # 下载成功再写入xml文件
            if plugin_archive_name:
                self.logger.info('download [{}][{}] finished, save info'.format(plugin_info.id, plugin_info.version))
                record_download_file_md5sum = '''
                    insert into download_info(id, version, archive_name, md5) values(%s, %s, %s, %s)
                '''
                db_operator.execute(record_download_file_md5sum,
                                    (plugin_info.id, plugin_info.version, plugin_archive_name, file_md5sum))

                self.generate_node_info(plugin_archive_name, root, plugin_info)

        self.write_xml(product_code,build_version, root)

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

    def generate_node_info(self, plugin_archive_name, root, plugin_info, mode='local'):
        node_plugin = etree.SubElement(root, 'plugin')
        node_plugin.set('id', plugin_info.id)
        if mode == 'nexus':
            node_plugin.set('url', ''.join([self.nexus_repo_url, plugin_info.id.replace(' ', '+'), '/',
                            plugin_info.version, '/', plugin_info.id.replace(' ', '+'), '_',
                            plugin_info.version, plugin_info.archive_suffix]))
        else:
            node_plugin.set('url', ''.join([self.repo_url, plugin_info.id.replace(' ', '_'), '/',
                                            plugin_info.version, '/', plugin_archive_name]))
        # node_plugin.set('url', ''.join([self.repo_url, plugin_info.id.replace(' ', '_'), '/',
        #                                 plugin_info.version, '/', plugin_archive_name]))
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
        if plugin_info.vendor_email:
            node_vendor.set('email', plugin_info.vendor_email)
        if plugin_info.vendor_url:
            node_vendor.set('url', plugin_info.vendor_url)

    @staticmethod
    def get_ide_versions():
        query_ide_versions = '''
            select product_code, build_version, version from ide_version 
             order by product_code, build_version desc
        '''
        ide_versions = db_operator.select(query_ide_versions)

        return ide_versions

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
        query_plugins_without_suffix = '''
        select x.id, x.version, y.id plugin_id
          from (select distinct a.id, a.version
                  from support_version a, white_list b
                 where a.id = b.plugin_id) x
          left join download_info y
            on x.id = y.id
           and x.version = y.version
         where y.archive_suffix is null
        '''

        plugins_without_suffix = db_operator.select(query_plugins_without_suffix)
        for row in plugins_without_suffix:
            suffix = self.get_plugin_file_suffix(row[0], row[1])

            if not row[2]:  # row[2]为download_info.id字段，为空表示该表没有此记录
                record_plugin_file_suffix = '''
                    insert into download_info(id, version, archive_name, archive_suffix) values(%s, %s, %s, %s)
                '''
                db_operator.execute(record_plugin_file_suffix,
                                    (row[0], row[1], ''.join([row[0], '-', row[1], suffix]), suffix))
            else:
                update_plugin_file_suffix = '''
                    update download_info set archive_suffix = %s, update_time = now() where id = %s and version = %s
                '''
                db_operator.execute(update_plugin_file_suffix, (suffix, row[0], row[1]))

        # 按IDE版本排序获取其可用的插件
        query_plugins_for_xml = '''
            select b.name, b.id, b.description, c.version, c.change_notes, c.since_build, c.until_build,
                   c.rating, e.archive_suffix, d.product_code, d.build_version, f.name, f.email, f.url
              from white_list a, plugins_base_info b, plugins_version_info c, support_version d, download_info e, vendor_info f
             where a.plugin_id = b.id
               and a.plugin_id = c.id
               and a.plugin_id = d.id
               and c.version = d.version
               and a.plugin_id = e.id
               and d.version = e.version
               and c.vendor_id = f.id
             order by d.product_code, d.build_version desc
        '''
        plugins_for_xml = db_operator.select(query_plugins_for_xml)
        root = etree.Element('plugins')
        last_product_code = None
        last_build_version = None

        for i in range(len(plugins_for_xml)):
            row = plugins_for_xml[i]
            plugin_info = PluginInfo()
            plugin_info.name = row[0]
            plugin_info.id = row[1]
            plugin_info.description = row[2]
            plugin_info.version = row[3]
            plugin_info.change_notes = row[4]
            plugin_info.since_build = row[5]
            plugin_info.until_build = row[6]
            plugin_info.rating = row[7]
            plugin_info.archive_suffix = row[8]
            plugin_info.vendor_name = row[11]
            plugin_info.vendor_email = row[12]
            plugin_info.vendor_url = row[13]

            if not last_product_code:
                last_product_code = row[9]
            if not last_build_version:
                last_build_version = row[10]

            if last_build_version != row[0]:
                self.write_xml(last_product_code, last_build_version, root)
                root = etree.Element('plugins')

            self.generate_node_info(plugin_info.name, root, plugin_info, 'nexus')

            if i == len(plugins_for_xml) - 1:
                self.write_xml(row[9], row[10], root)

            last_product_code = row[9]
            last_build_version = row[10]
            i += 1

    def write_xml(self, product_code, build_version, root_node):
        plugins_dir = Path(self.plugins_store_dir)

        if not plugins_dir.exists():
            plugins_dir.mkdir(parents=True, exist_ok=True)
        update_plugins_xml = ''.join([self.plugins_store_dir, 'updatePlugins', '-',
                                      product_code, '-', build_version, '.xml'])
        with open(update_plugins_xml, mode='wb') as f:
            f.write(etree.tostring(root_node, pretty_print=True, xml_declaration=True, encoding='utf-8'))


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
    vendor_name = None
    vendor_email = None
    vendor_url = None
