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
        db = NamelessConfig.DATABASE
        
        dialect: str = db.DIALECT
        driver: str = db.DRIVER
        username: str = db.USERNAME
        password: str = db.PASSWORD
        host: str = db.HOST
        port: Optional[int] = db.PORT
        db_name: str = db.NAME

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
