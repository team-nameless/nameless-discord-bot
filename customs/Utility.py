import logging
from typing import Optional, Tuple, Type
from urllib.parse import quote_plus as qp, urlparse

import config_example

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
            host = ""
            port = None
            db_name = "nameless.db"

        pdriver: str = qp(f"+{driver}", safe="+") if driver else ""
        ppassword: str = qp(f":{password}", safe=":") if password else ""
        at: str = qp("@", safe="@") if username and password else ""
        pport: str = qp(f":{port}", safe=":") if port else ""

        vpassword: str = qp(f":{'*' * len(password)}", safe=":") if password else ""
        vport: str = qp(f":{'*' * len(str(port))}", safe=":") if port else ""
        vhost: str = "*" * len(host) if host else ""

        finish_url = (
            f"{dialect}{pdriver}://{username}{ppassword}{at}{host}{pport}/{db_name}"
        )
        secret_url = (
            f"{dialect}{pdriver}://{username}{vpassword}{at}{vhost}{vport}/{db_name}"
        )
        logging.info("Using %s as database URL", secret_url)

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

    @staticmethod
    def is_valid_config_class(config_cls: Type) -> Optional[bool]:
        """
        Validate config class.

        True if can run.
        None if can run with warnings.
        False if can not run.
        """
        try:
            current_fields = config_cls.__dict__.keys()
            important_fields = ["TOKEN", "COGS"]

            for field in important_fields:
                if field not in current_fields:
                    logging.error(
                        "Missing important field %s in %s", field, config_cls.__name__
                    )
                    return False

            available_fields = config_example.Config.__dict__.keys()

            for field in available_fields:
                if field not in current_fields:
                    logging.warning("Missing %s in %s", field, config_cls.__name__)
                    return None

            return True
        except AttributeError as err:
            logging.error("Something bad happened", exc_info=err)
            return False
