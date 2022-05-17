# Low-cost DI
import logging
import sys
from datetime import datetime

import customs
from config import Config
from database import CRUD

# Database setup
crud_database = CRUD()

# Logging setup
log_level: logging = logging.DEBUG if Config.LAB else logging.INFO
logging.getLogger().handlers.clear()

logging.basicConfig(level=log_level)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    customs.ColoredFormatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
)
logging.getLogger().handlers[:] = [handler]

start_time: datetime = datetime.min
