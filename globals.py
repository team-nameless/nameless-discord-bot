# Low-cost DI
import sys

from config import Config
import customs
from database import PostgreSqlCRUD
import logging

# Database setup
postgres = PostgreSqlCRUD
postgres_database = postgres()
postgres_database.init()

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
