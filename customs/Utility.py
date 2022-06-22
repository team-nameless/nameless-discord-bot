import logging
from typing import Optional, Tuple, Type
from urllib.parse import quote_plus as qp, urlparse

__all__ = ["Utility"]


class Utility:
    """
    List of utilities that aid the further developments of this project.
    """

    @staticmethod
    def get_db_url(
        config_cls: Optional[Type] = None,
    ) -> Tuple[str, str, str, str, str, str, Optional[int], str]:
        """
        Get the database connection URL based on the config and its components.
        :param config_cls: The class used to retrieve config. Defaults to None.
        :return: Database connection URL
        """
        dialect: str
        driver: str
        username: str
        password: str
        host: str
        port: Optional[int]
        db_name: str

        if (
            config_cls
            and hasattr(config_cls, "DATABASE")
            and (db := config_cls.DATABASE)
        ):
            dialect = db["dialect"]
            driver = db["driver"]
            username = db["username"]
            password = db["password"]
            host = db["host"]
            port = int(db["port"] if db["port"] else 0)
            db_name: str = db["db_name"]
        else:
            logging.warning("Falling back to SQLite")
            dialect = "sqlite"
            driver = ""
            username = ""
            password = ""
            at = ""
            host = ""
            port = None
            db_name = "nameless.db"

        driver: str = qp(f"+{driver}", safe="+") if driver else ""
        password: str = qp(f":{password}", safe=":") if password else ""
        at: str = qp("@", safe="@") if username and password else ""
        port_str: str = qp(f":{port}", safe=":") if port else ""

        url = f"{dialect}{driver}://{username}{password}{at}{host}{port_str}/{db_name}"
        logging.info("Using %s as database URL", url)

        return (
            url,
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
