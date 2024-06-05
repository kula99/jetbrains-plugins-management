import os
import time

import requests
import yaml

import server_dao


class Manager:

    def __init__(self):
        with open(''.join([os.path.split(os.path.realpath(__file__))[0], '/', 'application.yaml']), 'r') as f:
            app_conf = yaml.safe_load(f)

        self.jetbrains_data_services = app_conf['jetbrains_data_services']
        self.support_product_codes = app_conf['support_product_codes']
        self.support_earliest_build_version = app_conf['support_earliest_build_version']
        self.user_agent = app_conf['user_agent']

        self.proxies = {}
        proxy_conf = app_conf['proxy']
        if proxy_conf['enable']:
            self.proxies.update({'https': proxy_conf['address'],
                                 'http': proxy_conf['address']
                                 })

    def check_updates(self):
        headers = {'User-Agent': self.user_agent}
        payload = {
            'code': self.support_product_codes,
            'release.type': 'release',
            '_': int(round(time.time() * 1000))
        }

        response = requests.get(''.join([self.jetbrains_data_services, 'products']),
                                headers=headers, params=payload, stream=True, proxies=self.proxies)
        resp_json = response.json()

        for item in resp_json:
            releases = item['releases']
            for rel in releases:
                build_version = rel['build']
                product_code = item['intellijProductCode']
                version = rel['version']
                if build_version[:build_version.find('.')] >= self.support_earliest_build_version:
                    server_dao.update_ide_versions(product_code, build_version, version)

        # 检查自定义插件是否支持新增的IDE版本
        plugin_support_ide_info = server_dao.check_internal_plugin_support_ide_version()
        last_row = None
        update_list = []
        i = 0
        for row in plugin_support_ide_info.namedtuples().iterator():
            if ((i == 0)
                    or (last_row is not None
                        and (last_row.id != row.id or last_row.build_version != row.build_version))):
                update_list.append((row.id, row.plugin_version, row.product_code, row.build_version))

            last_row = row
            i += 1

        server_dao.add_new_support_version(update_list)


if __name__ == '__main__':
    Manager().check_updates()
