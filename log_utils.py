import os

from loguru import logger

logger.remove()  # remove the default stream handler that print the logs to the console
logger.add('{}/logs/plugins_sync.log'.format(os.path.split(os.path.realpath(__file__))[0]),
           backtrace=True,
           enqueue=True,
           rotation='00:00',
           retention='7 days',
           delay=True,
           level='INFO')
