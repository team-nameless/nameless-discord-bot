# Low-cost DI
import logging
import sys
from datetime import datetime

from ossapi import OssapiV2

import customs
from config import Config
from database import CRUD

# Database setup
crud_database = CRUD()

# Stuffs
__nameless_version__ = "0.0.1-beta"
start_time: datetime = datetime.min
osu_api_client = OssapiV2(Config.OSU["client_id"], Config.OSU["client_secret"])
osu_api_client.log = logging.getLogger()

# Logging setup
log_level: logging = logging.DEBUG if Config.LAB else logging.INFO
logging.getLogger().handlers.clear()
logging.basicConfig(level=log_level)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    customs.ColoredFormatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
)
logging.getLogger().handlers[:] = [handler]
