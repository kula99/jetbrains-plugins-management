from plugins_handler import PluginsHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from log_utils import logger


def main_process(thread_count=5):
    handler = PluginsHandler()

    logger.info('===== start to update plugins =====')
    ides = handler.get_ide_versions()
    futures = []
    with ThreadPoolExecutor(max_workers=thread_count) as p:
        for ide in ides:
            futures.append(p.submit(get_plugins_list, handler, ide[0], ide[2], ide[1]))
        as_completed(futures)

    logger.info('+++++ generate update plugins xml begin +++++')
    handler.generate_all_update_plugins_xml()
    logger.info('+++++ generate update plugins xml end +++++')

    logger.info('+++++ download plugins to nexus begin +++++')
    handler.download_plugin_archive(day_offset=-60)
    logger.info('+++++ download plugins to nexus end +++++')

    logger.info('===== job finished =====')


def get_plugins_list(handler, product_code, version, build_version):
    logger.info('===== update [{} {} (Release Version: {})] plugin list begin ====='.format(product_code, version,
                                                                                            build_version))
    try:
        handler.get_supported_plugins_list(product_code, build_version)
        logger.info('download plugins list for {}-{} end'.format(product_code, build_version))
        handler.save_plugins_info(product_code, build_version)
        logger.info('save plugins info for {}-{} end'.format(product_code, build_version))
    except Exception as e:
        logger.exception('something went wrong during the update progress', e)
    logger.info(
        '===== update [{} {} (Release Version: {})] plugin list end ====='.format(product_code, version, build_version))


if __name__ == '__main__':
    main_process()
