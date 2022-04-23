# Low-cost DI
from datetime import datetime
import sys

from config import Config
import customs
from database import CRUD
import logging

# Database setup
crud = CRUD
crud_database = crud()
crud_database.init()

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
