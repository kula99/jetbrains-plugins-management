import yaml
import logging.config
import os


def get_simple_logger():
    with open(''.join([os.path.dirname(__file__), '/', 'logging.yaml']), 'r') as f:
        log_conf = yaml.safe_load(f)

    logging.config.dictConfig(log_conf)
    return logging.getLogger('simple')
