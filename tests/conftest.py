import os

ENV_DEFAULTS = {
    "BASE_URL": "https://nextcloud.example.test",
    "BOT_TOKEN": "123:test",
    "MYSQL_DB": "test",
    "MYSQL_PASS": "test",
    "MYSQL_USER": "test",
    "NEXTCLOUD_PASS": "test",
    "NEXTCLOUD_USER": "test",
    "WEB_APP_URL": "https://nextcloud.example.test",
}

for name, value in ENV_DEFAULTS.items():
    os.environ.setdefault(name, value)
