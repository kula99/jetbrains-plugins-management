from plugins_handler import PluginsHandler
import log_utils

if __name__ == '__main__':
    logger = log_utils.get_simple_logger()
    handler = PluginsHandler()

    logger.info('===== start to update plugins =====')
    ides = handler.get_ide_versions()
    for ide in ides:
        if not ide[0] or not ide[1]:
            logger.info('product_code or build_version not provided, skip')
            continue

        logger.info('===== update [{} {} (Release Version: {})] plugin list begin ====='.format(ide[0], ide[2], ide[1]))
        try:
            handler.get_supported_plugins_list(ide[0], ide[1])
            handler.save_plugins_info(ide[0], ide[1])
            handler.generate_update_plugins_xml(ide[0], ide[1])
        except Exception:
            logger.error('something went wrong during the update progress', exc_info=True)
        logger.info('===== update [{} {} (Release Version: {})] plugin list end ====='.format(ide[0], ide[2], ide[1]))

    logger.info('===== job finished =====')
