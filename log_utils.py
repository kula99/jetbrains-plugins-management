from loguru import logger

logger.remove()  # remove the default stream handler that print the logs to the console
logger.add('./logs/plugins_sync.log',
           backtrace=True,
           enqueue=True,
           rotation='1 day',
           retention='7 days',
           delay=True,
           level='INFO')
