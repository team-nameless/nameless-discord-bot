import logging
from typing import Optional, Tuple
from urllib.parse import quote_plus as qp, urlparse

from NamelessConfig import NamelessConfig


__all__ = ["Utility"]


class Utility:
    """
    Utilities that aid the further developments of this project.
    """

    @staticmethod
    def get_db_url() -> Tuple[str, str, str, str, str, str, Optional[int], str]:
        """
        Get the database connection URL based on the config and its components.
        :return: Database connection URL with components.
        """
        dialect: str
        driver: str
        username: str
        password: str
        host: str
        port: Optional[int]
        db_name: str

        if db := getattr(NamelessConfig, "DATABASE", {}):
            dialect = db.get("dialect", "sqlite")
            driver = db.get("driver", "")
            username = db.get("username", "")
            password = db.get("password", "")
            host = db.get("host", "")
            port = db.get("port")
            db_name = db.get("db_name", "nameless.db")
        else:
            logging.warning("Falling back to SQLite")
            dialect = "sqlite"
            driver = ""
            username = ""
            password = ""
            host = ""
            port = None
            db_name = "nameless.db"

        pdriver: str = qp(f"+{driver}", safe="+") if driver else ""
        ppassword: str = qp(f":{password}", safe=":") if password else ""
        at: str = qp("@", safe="@") if username and password else ""
        pport: str = qp(f":{port}", safe=":") if port else ""

        finish_url = f"{dialect}{pdriver}://{username}{ppassword}{at}{host}{pport}/{db_name}"

        return (
            finish_url,
            dialect,
            driver,
            username,
            password,
            host,
            port,
            db_name,
        )

    @staticmethod
    def is_an_url(url: str) -> bool:
        return urlparse(url).netloc != ""
