import os
import yaml
from flask import Flask


def create_app():
    app = Flask(__name__)
    pwd = os.path.split(os.path.realpath(__file__))[0]

    with open(''.join([pwd, '/', 'application.yaml']), 'r') as f:
        app_conf = yaml.safe_load(f)
        app.config.update(app_conf)
        app.config['MAX_CONTENT_LENGTH'] = app_conf['max_content_length']

    return app
