""" Startup file for Google Cloud deployment or local webserver"""
import os

from openhouse.argument_parser import parse
from openhouse.idmaintainer import IdMaintainer
from openhouse.googlecloud_idmaintainer import GoogleCloudIdMaintainer
from openhouse.web_hunter import WebHunter
from openhouse.config import Config
from openhouse.logging import configure_logging

from openhouse.web import app

# load config
args = parse()
config_handle = args.config
if config_handle is not None:
    config = Config(config_handle.name)
else:
    config = Config()

if __name__ == '__main__':
    # Use the SQLite DB file if we are running locally
    id_watch = IdMaintainer(f'{config.database_location()}/processed_ids.db')
else:
    # Load the driver manager from local cache (if chrome_driver_install.py has been run
    os.environ['WDM_LOCAL'] = '1'
    # Use Google Cloud DB if we run on the cloud
    id_watch = GoogleCloudIdMaintainer(config)

configure_logging(config)

# initialize search plugins for config
config.init_searchers()

hunter = WebHunter(config, id_watch)

app.config["HUNTER"] = hunter
if config.has_website_config():
    app.secret_key = config.website_session_key()
    app.config["DOMAIN"] = config.website_domain()
    app.config["BOT_NAME"] = config.website_bot_name()
else:
    app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(32).hex())
notifiers = config.notifiers()
if "telegram" in notifiers:
    app.config["BOT_TOKEN"] = config.telegram_bot_token()
if "mattermost" in notifiers:
    app.config["MM_WEBHOOK_URL"] = config.mattermost_webhook_url()

if __name__ == '__main__':
    try:
        website_config = config['website']
    except (KeyError, TypeError):
        website_config = {}
        
    listen = website_config.get('listen', {})
    host = listen.get('host', '127.0.0.1')
    port = listen.get('port', '8080')
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug_mode)
