import datetime
import operator
from functools import reduce
from peewee import NodeList

from data_access import *


def check_register_plugin(plugin_id: str):
    return WhiteList.get_or_none((WhiteList.plugin_id == plugin_id) & (WhiteList.enabled == 1))


def get_download_info(plugin_id: str, version: str):
    return DownloadInfo.get_or_none((DownloadInfo.id == plugin_id) & (DownloadInfo.version == version))


def check_ticket(ticket: str, access_token: str):
    return TmpTicket.get_or_none((TmpTicket.ticket == ticket)
                                 & (TmpTicket.access_token == access_token)
                                 & (fn.TIMESTAMPDIFF(SQL('SECOND'), TmpTicket.create_time, fn.NOW()) < 120)
                                 )


def get_valid_tmp_ticket(access_token: str):
    return (TmpTicket
            .select(TmpTicket.ticket)
            .where((TmpTicket.access_token == access_token)
                   & (fn.TIMESTAMPDIFF(SQL('SECOND'), TmpTicket.create_time, fn.NOW()) < 20))
            .order_by(TmpTicket.create_time.desc())
            .limit(1))


def save_tmp_ticket(ticket: str, access_token: str, user_name: str):
    TmpTicket.create(ticket=ticket, access_token=access_token, user_name=user_name)


def reset_tmp_ticket_step(ticket: str, step: int = 1):
    (TmpTicket
     .update(step=step, update_time=datetime.datetime.now())
     .where((TmpTicket.ticket == ticket) & (TmpTicket.step != step))
     .execute())


def update_tmp_ticket_step(ticket: str, step: int):
    TmpTicket.update(step=step).where(TmpTicket.ticket == ticket).execute()


def get_support_ide_range(since_build: str, until_build: str = None):
    return (IdeVersion.select(IdeVersion.product_code, IdeVersion.build_version, IdeVersion.version)
            .where((fn.version_compare(IdeVersion.build_version, since_build) <= 0)
                   & (fn.ISNULL(until_build) | (fn.version_compare(IdeVersion.build_version, until_build) > 0)))
            .order_by(IdeVersion.build_version.desc()))


def get_ide_versions():
    return IdeVersion.select().order_by(IdeVersion.product_code, IdeVersion.build_version.desc())


def add_new_support_version(new_data: list):
    (SupportVersion
     .insert_many(new_data, fields=[SupportVersion.id, SupportVersion.version,
                                    SupportVersion.product_code, SupportVersion.build_version])
     .on_conflict_ignore()
     .execute())


def update_old_support_version(plugin_id: str, plugin_version: str, ide_info: list):
    (SupportVersion
     .update(latest_version='0')
     .where((SupportVersion.id == plugin_id)
            & (fn.version_compare(SupportVersion.version, plugin_version) > 0)
            & (SupportVersion.latest_version == '1')
            & Tuple(SupportVersion.product_code, SupportVersion.build_version).in_(ide_info)
            )
     .execute())


def move_old_support_version(plugin_id: str, plugin_version: str, ide_info: list):
    (SupportVersionHistory
     .insert_from(
        SupportVersion
        .select(SupportVersion.id, SupportVersion.version,
                SupportVersion.product_code, SupportVersion.build_version)
        .where((SupportVersion.id == plugin_id)
               & (fn.version_compare(SupportVersion.version, plugin_version) > 0)
               # & (SupportVersion.latest_version == '1')
               & Tuple(SupportVersion.product_code, SupportVersion.build_version).in_(ide_info)
               ),
        fields=[SupportVersionHistory.id, SupportVersionHistory.version,
                SupportVersionHistory.product_code, SupportVersionHistory.build_version]
     )
     .on_conflict_ignore()
     .execute()
     )


def remove_old_support_version(plugin_id: str, plugin_version: str, ide_info: list):
    (SupportVersion
     .delete()
     .where((SupportVersion.id == plugin_id)
            & (fn.version_compare(SupportVersion.version, plugin_version) > 0)
            # & (SupportVersion.latest_version == '1')
            & Tuple(SupportVersion.product_code, SupportVersion.build_version).in_(ide_info)
            )
     .execute())


def remove_old_ide_support_version(plugin_id: str, plugin_version: str, product_code: str, build_version: str):
    (SupportVersion
     .delete()
     .where((SupportVersion.id == plugin_id)
            & (fn.version_compare(SupportVersion.version, plugin_version) > 0)
            # & (SupportVersion.latest_version == '1')
            & (SupportVersion.product_code == product_code)
            & (SupportVersion.build_version == build_version))
     .execute())


def add_new_plugin_base_info(name: str, plugin_id: str, description: str):
    (PluginsBaseInfo
     .insert(name=name, id=plugin_id, description=description)
     .on_conflict(update={PluginsBaseInfo.name: name, PluginsBaseInfo.description: description})
     .execute())


def add_new_plugin_version_info(plugin_id: str, version: str, change_notes: str, since_build, until_build, rating=0,
                                archive_size=0, release_time=None, tags=None, vendor_id=None):
    (PluginsVersionInfo
     .insert(id=plugin_id, version=version, change_notes=change_notes, since_build=since_build, until_build=until_build,
             rating=rating, archive_size=archive_size, release_time=release_time, tags=tags, vendor_id=vendor_id)
     .on_conflict_ignore()
     .execute())


def add_new_plugin_info(name, plugin_id, description, version, change_notes, since_build, until_build, rating=0,
                        archive_size=0, release_time=None, tags=None, vendor_id=None):
    add_new_plugin_base_info(name, plugin_id, description)
    add_new_plugin_version_info(plugin_id, version, change_notes, since_build, until_build, rating, archive_size,
                                release_time, tags, vendor_id)


def add_new_download_info(plugin_id, version, archive_name, md5):
    (DownloadInfo
     .insert(id=plugin_id, version=version, archive_name=archive_name, md5=md5,
             archive_suffix=archive_name[archive_name.rindex('.'):])
     .on_conflict_ignore()
     .execute())


def get_vendor_info_by_name(name):
    return VendorInfo.get_or_none(VendorInfo.name == name)


def add_vendor_info(v_id, name, email, url, dev_type: str = None):
    VendorInfo.create(id=v_id, name=name, email=email, url=url, dev_type=dev_type)


def check_vendor_info(name, email, url):
    return VendorInfo.get_or_none((VendorInfo.name == name)
                                  & ((VendorInfo.email == email) | fn.ISNULL(email))
                                  & ((VendorInfo.url == url) | fn.ISNULL(url)))


def update_vendor_info(v_id, name, email, url):
    (VendorInfo
     .update(name=name, email=email, url=url, update_time=datetime.datetime.now())
     .where(VendorInfo.id == v_id)
     .execute())


def get_upload_batch_info(batch_no):
    return UploadBatchInfo.get_or_none(batch_no=batch_no)


def get_upload_chunk_info(batch_no):
    return UploadChunkInfo.select().where(UploadChunkInfo.batch_no == batch_no)


def update_plugin_archive_size(plugin_id, version, archive_size):
    (PluginsVersionInfo
     .update(archive_size=archive_size, update_time=datetime.datetime.now())
     .where((PluginsVersionInfo.id == plugin_id) & (PluginsVersionInfo.version == version)))


def get_plugin_version_info(plugin_id, version):
    return (PluginsVersionInfo
            .get_or_none((PluginsVersionInfo.id == plugin_id) & (PluginsVersionInfo.version == version)))


def save_batch_info(batch_no, plugin_id, plugin_version, archive_name=None, archive_suffix=None, since_build=None, until_build=None):
    UploadBatchInfo.create(batch_no=batch_no, plugin_id=plugin_id, plugin_version=plugin_version,
                           archive_name=archive_name, archive_suffix=archive_suffix,
                           since_build=since_build, until_build=until_build)


def save_upload_chunk_info(batch_no, chunk_order, saved_path):
    UploadChunkInfo.create(batch_no=batch_no, chunk_order=chunk_order, saved_path=saved_path)
    # UploadChunkInfo.insert(batch_no=batch_no, chunk_order=chunk_order, saved_path=saved_path).execute()


def get_white_list():
    return WhiteList.select().where(WhiteList.enabled == '1')


def query_plugins_for_update_xml():
    # t_a = WhiteList.alias()
    t_b = PluginsBaseInfo.alias()
    t_c = PluginsVersionInfo.alias()
    t_d = SupportVersion.alias()
    t_e = DownloadInfo.alias()
    t_f = VendorInfo.alias()
    return (WhiteList
            .select(t_b.name, t_b.id, t_b.description, t_c.version, t_c.change_notes, t_c.since_build, t_c.until_build,
                    t_c.rating, t_e.archive_suffix, t_d.product_code, t_d.build_version, t_f.name.alias('vendor_name'),
                    t_f.email, t_f.url, t_f.dev_type)
            .join(t_b, on=(WhiteList.plugin_id == t_b.id))
            .join(t_c, on=(t_b.id == t_c.id))
            .join(t_d, on=((t_c.id == t_d.id) & (t_c.version == t_d.version)))
            .switch(WhiteList)
            .join(t_e, on=(WhiteList.plugin_id == t_e.id))
            .switch(t_c)
            .join(t_f, on=(t_c.vendor_id == t_f.id))
            .where((WhiteList.enabled == 1)
                   & (t_d.version == t_e.version)
                   )
            .order_by(t_d.product_code, t_d.build_version.desc()))


def get_recent_released_plugins(day_offset: int = 0):
    t_b = PluginsVersionInfo.alias()
    t_c = DownloadInfo.alias()
    t_d = VendorInfo.alias()
    return (WhiteList
            .select(t_b.id, t_b.version, t_b.since_build, t_b.archive_size, t_b.release_time, t_c.archive_suffix,
                    t_d.dev_type)
            .join(t_b, on=((WhiteList.plugin_id == t_b.id)
                           & (t_b.update_time >= fn.DATE_ADD(fn.CURDATE(),
                                                             NodeList((SQL('INTERVAL'), day_offset, SQL('DAY'))))
                              )
                           ))
            .join(t_c, on=((t_b.id == t_c.id) & (t_b.version == t_c.version)))
            .switch(t_b)
            .join(t_d, on=(t_b.vendor_id == t_d.id))
            .where(WhiteList.enabled == 1))


def query_plugins_without_suffix():
    sub_q = (SupportVersion
             .select(SupportVersion.id, SupportVersion.version)
             .join(WhiteList, on=((SupportVersion.id == WhiteList.plugin_id) & (WhiteList.enabled == 1)))
             .distinct())

    return (sub_q
            .select_from(sub_q.c.id, sub_q.c.version, DownloadInfo.id.alias('plugin_id'))
            .join(DownloadInfo, JOIN.LEFT_OUTER, on=((sub_q.c.id == DownloadInfo.id)
                                                     & (sub_q.c.version == DownloadInfo.version)))
            .where(DownloadInfo.archive_suffix.is_null(True))
            )


def update_plugin_file_suffix(plugin_id: str, version: str, suffix: str):
    (DownloadInfo
     .update(archive_suffix=suffix)
     .where((DownloadInfo.id == plugin_id) & (DownloadInfo.version == version))
     .execute())


def get_latest_plugins_by_ide(product_code: str, build_version: str):
    t_b = PluginsBaseInfo.alias()
    t_c = PluginsVersionInfo.alias()
    t_d = SupportVersion.alias()
    t_e = VendorInfo.alias()
    t_f = DownloadInfo.alias()
    return (WhiteList
            .select(t_b.name, t_b.id, t_b.description, t_c.version, t_c.change_notes, t_c.since_build, t_c.until_build,
                    t_c.rating, t_e.name.alias('vendor_name'), t_e.email, t_e.url, t_e.dev_type, t_f.archive_suffix)
            .join(t_b, on=(WhiteList.plugin_id == t_b.id))
            .join(t_c, on=(t_b.id == t_c.id))
            .join(t_d, on=((t_c.id == t_d.id) & (t_c.version == t_d.version)))
            .switch(t_c)
            .join(t_e, on=(t_c.vendor_id == t_e.id))
            .switch(t_d)
            .join(t_f, on=((t_d.id == t_f.id) & (t_d.version == t_f.version)))
            .where((WhiteList.enabled == 1)
                   & (t_d.product_code == product_code)
                   & (t_d.build_version == build_version)
                   & (t_d.latest_version == 1))
            )


def get_old_support_version(plugin_id: str, plugin_version: str, ide_info: list):
    return (SupportVersion
            .select()
            .where((SupportVersion.id == plugin_id)
                   & (fn.version_compare(SupportVersion.version, plugin_version) > 0)
                   # & Tuple(SupportVersion.product_code, SupportVersion.build_version).in_(ide_info)
                   & (reduce(operator.or_, [(SupportVersion.product_code == item.product_code)
                                            & (SupportVersion.build_version == item.build_version)
                                            for item in ide_info]))
                   ))


def update_sync_status(product_code: str, build_version: str, status: str):
    (IdeVersion
     .update(last_sync_status=status, last_sync_time=datetime.datetime.now())
     .where((IdeVersion.product_code == product_code) & (IdeVersion.build_version == build_version))
     .execute())


def update_ide_versions(product_code: str, build_version: str, version: str):
    (IdeVersion
     .insert(product_code=product_code, build_version=build_version, version=version)
     .on_conflict_ignore()
     .execute())
