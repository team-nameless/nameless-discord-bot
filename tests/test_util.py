from nameless.commons import Utility


class FakeConfig:
    DATABASE = {
        "dialect": "postgresql",
        "driver": "psycopg2",
        "username": "nameless",
        "password": "NamelessOutOfBetaWhen",
        "host": "localhost",
        "port": 12345,
        "db_name": "dame_dane",
    }


class PartialConfig:
    TOKEN = ""
    COGS = []
    PREFIXES = []


class TestUtility:
    def test_get_db_url_default(self):
        (
            url,
            dialect,
            driver,
            username,
            password,
            host,
            port,
            db_name,
        ) = Utility.get_db_url()
        assert url == "sqlite:///nameless.db"
        assert dialect == "sqlite"
        assert driver == ""
        assert username == ""
        assert password == ""
        assert host == ""
        assert port is None
        assert db_name == "nameless.db"

    def test_get_db_url_fake_cls(self):
        (
            url,
            dialect,
            driver,
            username,
            password,
            host,
            port,
            db_name,
        ) = Utility.get_db_url(FakeConfig)
        assert (
            url
            == "postgresql+psycopg2://nameless:NamelessOutOfBetaWhen@localhost:12345/dame_dane"
        )
        assert dialect == "postgresql"
        assert driver == "psycopg2"
        assert username == "nameless"
        assert password == "NamelessOutOfBetaWhen"
        assert host == "localhost"
        assert port == 12345
        assert db_name == "dame_dane"

    def test_url_check_true(self):
        assert Utility.is_an_url("http://example.com")
        assert Utility.is_an_url("https://discord.com")
        assert Utility.is_an_url("osump://696969")
        assert Utility.is_an_url("//example.com")

    def test_url_check_false(self):
        assert not Utility.is_an_url("bao.moe")
        assert not Utility.is_an_url("discord.com")
        assert not Utility.is_an_url("m.me")
