from config import Config
from urllib.parse import quote_plus


class Utility:
    """
    List of utilities that aid the further developments of this project.
    """
    @staticmethod
    def get_db_url() -> str:
        """
        Get the PostgreSQL database connection URL based on the config.py content.

        :return: PostgreSQL database connection URL
        """
        postgres = Config.POSTGRES
        username: str = postgres["username"]
        password = postgres["password"]
        host: str = postgres["host"]
        port: int = postgres["port"]
        db_name: str = postgres["db_name"]
        real_password: str = "" if password == "" else f":{password}"
        return f"postgresql+psycopg2://{username}{quote_plus(real_password, safe=':')}@{host}:{port}/{db_name}"
