import collections
import datetime
import os
import shutil
from pathlib import Path
from typing import Any

import requests
import requests_mock
from flask import request, jsonify
from lxml import etree
from werkzeug.utils import secure_filename

import common_utils
import factory
import plugins_handler
import server_dao
from log_utils import logger
from message import MessageEnum

app = factory.create_app()


def to_web_msg(message_enum=MessageEnum.UNAUTHORIZED, biz_content: Any = None, hint: str = None):
    ret_json = {'code': message_enum.code, 'message': message_enum.message}
    if biz_content:
        ret_json.update({'data': biz_content})
    if hint:
        ret_json.update({'hint': hint})
    return jsonify(ret_json), message_enum.status_code


@app.route('/api/plugins/upload', methods=['POST'])
def upload():
    try:
        access_token = request.args.get('access_token')
        if not access_token:
            return to_web_msg(hint='param access_token is required')

        gitee_api = app.config['gitee_api']
        with requests_mock.Mocker() as m:
            m.get(''.join([gitee_api, '/user']), json={'login': 'JetBrains'}, status_code=200)
            auth_check_resp = requests.get(''.join([gitee_api, '/user']), params={'access_token': access_token})
        if auth_check_resp.status_code == 200:
            user_info = auth_check_resp.json()
            login = user_info['login']
            if login:
                check_developer(login)
                handle_plugin_xml(login)
                return to_web_msg(MessageEnum.SUCCESS)
            else:
                return to_web_msg(MessageEnum.UNAUTHORIZED)

        else:
            return to_web_msg(hint=auth_check_resp.reason)

    except RuntimeError as e:
        return to_web_msg(MessageEnum.BAD_REQUEST, hint=str(e))

    except Exception as e:
        logger.exception('Some thing went wrong', e)
        return to_web_msg(MessageEnum.BAD_REQUEST, hint=str(e))


@app.route('/api/ticket/acquire', methods=['GET', 'POST'])
def get_tmp_ticket():
    access_token = request.args.get('access_token')
    if not access_token:
        return to_web_msg(MessageEnum.UNAUTHORIZED)

    gitee_api = app.config['gitee_api']
    with requests_mock.Mocker() as m:
        m.get(''.join([gitee_api, '/user']), json={'login': 'JetBrains'}, status_code=200)
        auth_check_resp = requests.get(''.join([gitee_api, '/user']), params={'access_token': access_token})
    status_code = auth_check_resp.status_code
    if status_code == 200:
        user_info = auth_check_resp.json()
        login = user_info['login']
        if login:
            try:
                check_developer(login)
                gvtt = server_dao.get_valid_tmp_ticket(access_token)
                if gvtt:
                    tmp_ticket = gvtt[0].ticket
                    server_dao.reset_tmp_ticket_step(tmp_ticket)
                else:
                    tmp_ticket = common_utils.generate_random_str()
                    server_dao.save_tmp_ticket(tmp_ticket, access_token, login)
                return to_web_msg(MessageEnum.SUCCESS, biz_content={'ticket': tmp_ticket})
            except RuntimeError as e:
                return to_web_msg(MessageEnum.BAD_REQUEST, hint=str(e))
            except Exception as e:
                logger.exception('Some thing went wrong', e)
                return to_web_msg(MessageEnum.BAD_REQUEST, hint=str(e))
        else:
            return to_web_msg()
    else:
        return to_web_msg(hint=auth_check_resp.reason)


@app.route('/api/plugins/spec/check', methods=['POST'])
def check_plugin_xml():
    access_token = request.args.get('access_token')
    tmp_ticket = request.args.get('ticket')
    vt_result, user_name = validate_ticket(access_token, tmp_ticket, 1)

    if not vt_result:
        return to_web_msg()

    plugin_xml = request.files['plugin_xml']
    if plugin_xml:
        try:
            plugin = etree.fromstring(plugin_xml.read(), parser=etree.XMLParser(strip_cdata=False, resolve_entities=False))
            p_id = plugin.find('id').text

            crp = server_dao.check_register_plugin(p_id)
            if crp is None:
                return to_web_msg(hint='Unregistered plugin')

            p_version = plugin.find('version').text

            cdu = server_dao.get_download_info(p_id, p_version)
            if cdu:
                return to_web_msg(MessageEnum.BAD_REQUEST, hint='Duplicate upload')

            archive_name = request.form.get('archive_name')
            if archive_name is None:
                return to_web_msg(MessageEnum.BAD_REQUEST, hint='parameter archive_name is required')

            archive_size = request.form.get('archive_size')
            if archive_size is None:
                return to_web_msg(MessageEnum.BAD_REQUEST, hint='parameter archive_size is required')

            archive_suffix = archive_name[archive_name.rfind('.'):]

            p_name = plugin.find('name').text
            p_description = plugin.find('description').text if plugin.find('description') is not None else None
            p_version = plugin.find('version').text
            p_vendor = plugin.find('vendor')
            p_vendor_name = p_vendor.text if p_vendor.text is not None else user_name
            p_vendor_email = p_vendor.attrib.get('email')
            p_vendor_url = p_vendor.attrib.get('url')
            p_change_notes = plugin.find('change-notes').text
            p_idea_version = plugin.find('idea-version')
            p_since_build = p_idea_version.attrib.get('since-build')
            p_until_build = p_idea_version.attrib.get('until-build')

            vendor_id = get_vendor_id(p_vendor_email, p_vendor_name, p_vendor_url)

            server_dao.add_new_plugin_info(p_name, p_id, p_description, p_version, p_change_notes, p_since_build,
                                           p_until_build, archive_size=archive_size,
                                           release_time=datetime.datetime.now(), vendor_id=vendor_id)
            batch_no = common_utils.generate_random_str()
            server_dao.save_batch_info(batch_no, p_id, p_version, archive_name, archive_suffix,
                                       p_since_build, p_until_build)
            server_dao.update_tmp_ticket_step(tmp_ticket, 2)

            return to_web_msg(MessageEnum.SUCCESS, biz_content={'batch_no': batch_no})
        except Exception as e:
            return to_web_msg(MessageEnum.BAD_REQUEST, hint=str(e))

    else:
        return to_web_msg(MessageEnum.BAD_REQUEST, hint='parameter plugin_xml is required')


def get_vendor_id(p_vendor_email, p_vendor_name, p_vendor_url):
    vendor_info = server_dao.get_vendor_info_by_name(p_vendor_name)
    if vendor_info is None:
        vendor_id = common_utils.generate_random_str()
        server_dao.add_vendor_info(vendor_id, p_vendor_name, p_vendor_email, p_vendor_url)
    else:
        vendor_id = vendor_info.id
    return vendor_id


def validate_ticket(access_token, tmp_ticket, last_step):
    if not access_token or not tmp_ticket:
        return False, None

    ct = server_dao.check_ticket(tmp_ticket, access_token)
    if ct is None:
        return False, None
    elif ct.step != last_step:
        logger.warning('current step is {}, but last step is {}'.format(last_step, ct.step))
        return False, None

    return True, ct.user_name


def check_developer(developer_name):
    developer_info = server_dao.get_vendor_info_by_name(developer_name)
    if not developer_info:
        raise RuntimeError('You are not a registered developer')


@app.route('/api/plugins/chunk/upload', methods=['POST'])
def upload_chunk():
    try:
        access_token = request.args.get('access_token')
        tmp_ticket = request.args.get('ticket')
        batch_no = request.args.get('batch_no')
        vt_result, user_name = validate_ticket(access_token, tmp_ticket, 2)

        if not vt_result or batch_no is None:
            return to_web_msg()

        chunk = request.files.get('chunk')
        if chunk:
            archive_name = chunk.filename
            upload_dir = app.config['upload_dir']
            save_path_str = ''.join([upload_dir, '/', tmp_ticket, '/'])
            save_path = Path(save_path_str)
            if not save_path.exists():
                save_path.mkdir(parents=True, exist_ok=True)

            saved_archive_path = ''.join([save_path_str, secure_filename(archive_name)])
            # logger.info('chunk saved to {}'.format(saved_archive_path))
            chunk.save(saved_archive_path)
            # archive_size = os.stat(saved_archive_path).st_size
            expect_md5_sum = common_utils.get_file_md5sum(saved_archive_path)
            md5_sum = request.form.get('checksum')
            if md5_sum is None or md5_sum != expect_md5_sum:
                logger.warning('expect md5sum is {}, but get {}'.format(expect_md5_sum, md5_sum))
                return to_web_msg(MessageEnum.BAD_REQUEST, hint='md5sum not match')

            chunk_order = request.form.get('order')
            server_dao.save_upload_chunk_info(batch_no, chunk_order, saved_archive_path)

            return to_web_msg(MessageEnum.SUCCESS)

        else:
            return to_web_msg(MessageEnum.BAD_REQUEST, hint='parameter chunk is required')
    except Exception as e:
        logger.exception('upload chunk failed', e)
        return to_web_msg(MessageEnum.BAD_REQUEST, hint=str(e))


@app.route('/api/plugins/chunk/merge', methods=['GET', 'POST'])
def merge_chunks():
    try:
        access_token = request.args.get('access_token')
        tmp_ticket = request.args.get('ticket')
        vt_result, user_name = validate_ticket(access_token, tmp_ticket, 2)

        if not vt_result:
            return to_web_msg()

        batch_no = request.args.get('batch_no')
        upload_batch_info = server_dao.get_upload_batch_info(batch_no)
        if upload_batch_info is None:
            return to_web_msg(MessageEnum.BAD_REQUEST)

        upload_chunk_info = server_dao.get_upload_chunk_info(batch_no)

        upload_dir = app.config['upload_dir']
        save_path_str = ''.join([upload_dir, '/', upload_batch_info.plugin_id.replace(' ', '_'), '/',
                                 upload_batch_info.plugin_version, '/'])
        save_path = Path(save_path_str)
        if not save_path.exists():
            save_path.mkdir(parents=True, exist_ok=True)

        saved_archive_path = ''.join([save_path_str, upload_batch_info.plugin_id.replace(' ', '_'), '-',
                                     upload_batch_info.plugin_version, upload_batch_info.archive_suffix])

        with open(saved_archive_path, 'wb') as merged_file:
            for chunk_info in upload_chunk_info:
                with open(chunk_info.saved_path, 'rb') as f:
                    shutil.copyfileobj(f, merged_file)

        chuck_dir = Path(''.join([upload_dir, '/', tmp_ticket, '/']))
        if chuck_dir.exists():
            logger.debug('remove temp dir {}'.format(chuck_dir))
            shutil.rmtree(chuck_dir)

        return upload_to_nexus(saved_archive_path, upload_batch_info)

    except Exception as e:
        return to_web_msg(MessageEnum.INTERNAL_ERROR, hint=str(e))


def upload_to_nexus(saved_archive_path: str, plugin_info: collections.namedtuple):
    nexus_conf = app.config['nexus']
    nexus_api = nexus_conf['api_url']
    release_repo_id = nexus_conf['release_repo_id']
    publish_user = nexus_conf['publish_user']
    publish_password = nexus_conf['publish_pass']
    payload = {
        'maven2.groupId': 'cn.potato.plugins',
        'maven2.artifactId': plugin_info.plugin_id.replace(' ', '+'),
        'maven2.version': plugin_info.plugin_version,
        # 'maven2.asset1': open(saved_archive_path, 'rb'),
        'maven2.asset1.extension': plugin_info.archive_suffix.replace('.', '')
    }
    headers = {'User-Agent': app.config['user_agent']}
    resp = requests.post(''.join([nexus_api, '/components?repository=', release_repo_id]), headers=headers,
                         data=payload, files={'maven2.asset1': open(saved_archive_path, 'rb')},
                         auth=(publish_user, publish_password))
    if resp.status_code == 204:
        # archive_size = os.stat(saved_archive_path).st_size
        md5_sum = common_utils.get_file_md5sum(saved_archive_path)

        save_upload_plugin_info(plugin_info.plugin_id, plugin_info.plugin_version, plugin_info.archive_name, md5_sum,
                                plugin_info.since_build, plugin_info.until_build)

        return to_web_msg(MessageEnum.SUCCESS)
    else:
        return to_web_msg(MessageEnum.BAD_REQUEST, hint=resp.reason)


def save_upload_plugin_info(plugin_id, version, archive_name, md5_sum, since_build, until_build):
    # 根据since_build和until_build获取支持的IDE版本
    support_ide = server_dao.get_support_ide_range(since_build, until_build)

    # 写入support_version，并将之前的版本设为非最新版本移动到历史表
    new_support_version = [(plugin_id, version, row.product_code, row.build_version)
                           for row in support_ide.namedtuples().iterator()]
    server_dao.add_new_support_version(new_support_version)

    ide_version_tuple = [(row.product_code, row.build_version) for row in support_ide.namedtuples().iterator()]
    server_dao.move_old_support_version(plugin_id, version, ide_version_tuple)
    server_dao.remove_old_support_version(plugin_id, version, ide_version_tuple)

    # 新增download_info
    server_dao.add_new_download_info(plugin_id, version, archive_name, md5_sum)

    # 更新xml
    handler = plugins_handler.PluginsHandler()
    # handler.generate_all_update_plugins_xml()
    for ide in support_ide.namedtuples().iterator():
        handler.generate_update_plugins_xml(ide.product_code, ide.build_version)


def handle_plugin_xml(user_name):
    plugin_xml = request.files['plugin_xml']
    if plugin_xml:
        plugin = etree.fromstring(plugin_xml.read(), parser=etree.XMLParser(strip_cdata=False, resolve_entities=False))
        p_id = plugin.find('id').text
        p_name = plugin.find('name').text
        p_description = plugin.find('description').text if plugin.find('description') is None else None
        p_version = plugin.find('version').text
        p_vendor = plugin.find('vendor')
        p_vendor_name = p_vendor.text if p_vendor.text else user_name
        p_vendor_email = p_vendor.attrib.get('email')
        p_vendor_url = p_vendor.attrib.get('url')
        p_change_notes = plugin.find('change-notes').text
        p_idea_version = plugin.find('idea-version')
        p_since_build = p_idea_version.attrib.get('since-build')
        p_until_build = p_idea_version.attrib.get('until-build')

        cdu = server_dao.get_download_info(p_id, p_version)
        if cdu:
            raise RuntimeError('Duplicate upload')

        # 保存插件文件
        archive_name, archive_size, md5_sum, saved_archive_path = handle_archive_file(p_id, p_version)

        vendor_id = get_vendor_id(p_vendor_email, p_vendor_name, p_vendor_url)
        # 新增插件信息
        server_dao.add_new_plugin_info(p_name, p_id, p_description, p_version, p_change_notes, p_since_build,
                                       p_until_build, archive_size=archive_size, release_time=datetime.datetime.now(),
                                       vendor_id=vendor_id)

        PluginInfo = collections.namedtuple('PluginInfo', ['plugin_id', 'plugin_version', 'archive_name',
                                                           'archive_suffix', 'since_build', 'until_build'])
        plugin_info = PluginInfo(plugin_id=p_id, plugin_version=p_version, archive_name=archive_name,
                                 archive_suffix=archive_name[archive_name.rfind('.'):],
                                 since_build=p_since_build, until_build=p_until_build)
        upload_to_nexus(saved_archive_path, plugin_info)
    else:
        raise ValueError('param plugin_xml is required')


def handle_archive_file(plugin_id, plugin_version):
    archive = request.files.get('archive')
    if archive:
        archive_name = archive.filename
        upload_dir = app.config['upload_dir']
        save_path_str = ''.join([upload_dir, '/', plugin_id.replace(' ', '_'), '/', plugin_version, '/'])
        save_path = Path(save_path_str)
        if not save_path.exists():
            save_path.mkdir(parents=True, exist_ok=True)

        archive_name = secure_filename(archive_name)
        saved_archive_path = ''.join([save_path_str, archive_name])
        archive.save(saved_archive_path)
        archive_size = os.stat(saved_archive_path).st_size
        md5_sum = common_utils.get_file_md5sum(saved_archive_path)
        return archive_name, archive_size, md5_sum, saved_archive_path
    else:
        raise ValueError('param archive is required')


if __name__ == '__main__':
    app.run(port=8080)
