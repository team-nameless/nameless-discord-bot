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
base_logging_level: logging = logging.INFO
logging.getLogger().handlers.clear()

if Config.LAB:
    base_logging_level = logging.DEBUG

logging.basicConfig(level=base_logging_level)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    customs.ColoredFormatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
)
logging.getLogger().handlers[:] = [handler]

# Global vars
start_time: datetime = datetime.min
