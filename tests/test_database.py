import discord
import pytest

from nameless import database


_crud = database.CRUD()


class TestSQLAlchemyDatabase:
    @pytest.fixture(autouse=True)
    def fixture(self):
        self.crud = _crud  # pylint: disable=W0201
        self.mock_user = discord.Object(id=1)  # pylint: disable=W0201
        self.mock_guild = discord.Object(id=2)  # pylint: disable=W0201

        yield

        # Post-testing cleanup
        if u := self.crud.get_user_record(self.mock_user):
            self.crud.delete_user_record(u)
            self.crud.save_changes()

        if g := self.crud.get_guild_record(self.mock_guild):
            self.crud.delete_guild_record(g)
            self.crud.save_changes()

    def test_user_rollback(self):
        self.crud.create_user_record(self.mock_user)
        assert (u := self.crud.get_user_record(self.mock_user)) is not None
        self.crud.delete_user_record(u)
        assert self.crud.get_user_record(self.mock_user) is None
        self.crud.rollback()
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_guild_rollback(self):
        self.crud.create_guild_record(self.mock_guild)
        assert (g := self.crud.get_guild_record(self.mock_guild)) is not None
        self.crud.delete_guild_record(g)
        assert self.crud.get_guild_record(self.mock_guild) is None
        self.crud.rollback()
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_user_read_pass(self):
        self.crud.create_user_record(self.mock_user)
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_guild_read_pass(self):
        self.crud.create_guild_record(self.mock_guild)
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_user_read_fail(self):
        assert self.crud.get_user_record(self.mock_user) is None

    def test_guild_read_fail(self):
        assert self.crud.get_guild_record(self.mock_guild) is None

    def test_user_delete(self):
        self.crud.create_user_record(self.mock_user)
        assert (u := self.crud.get_user_record(self.mock_user)) is not None
        self.crud.delete_user_record(u)
        assert self.crud.get_user_record(self.mock_user) is None

    def test_guild_delete(self):
        self.crud.create_guild_record(self.mock_guild)
        assert (g := self.crud.get_guild_record(self.mock_guild)) is not None
        self.crud.delete_guild_record(g)
        assert self.crud.get_guild_record(self.mock_guild) is None

    def test_guild_write_once(self):
        self.crud.create_guild_record(self.mock_guild)
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_guild_write_once_more(self):
        self.crud.create_guild_record(self.mock_guild)
        self.crud.create_guild_record(self.mock_guild)
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_user_write_once(self):
        self.crud.create_user_record(self.mock_user)
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_user_write_once_more(self):
        self.crud.create_user_record(self.mock_user)
        self.crud.create_user_record(self.mock_user)
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_props(self):
        assert self.crud.session is not None
        assert self.crud.dirty is not None
        assert self.crud.db_url == "sqlite:///nameless.db"
        assert self.crud.new is not None

    def test_get_or_create_user(self):
        assert self.crud.get_user_record(self.mock_user) is None
        self.crud.get_or_create_user_record(self.mock_user)
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_get_or_create_guild(self):
        assert self.crud.get_guild_record(self.mock_guild) is None
        self.crud.get_or_create_guild_record(self.mock_guild)
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_get_or_create_user_none_before(self):
        assert self.crud.get_user_record(self.mock_user) is None
        _, is_new = self.crud.get_or_create_user_record(self.mock_user)
        assert is_new
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_get_or_create_guild_none_before(self):
        assert self.crud.get_guild_record(self.mock_guild) is None
        _, is_new = self.crud.get_or_create_guild_record(self.mock_guild)
        assert is_new
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_get_or_create_user_existed_before(self):
        self.crud.create_user_record(self.mock_user)
        assert self.crud.get_user_record(self.mock_user) is not None
        _, is_new = self.crud.get_or_create_user_record(self.mock_user)
        assert not is_new
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_get_or_create_guild_existed_before(self):
        self.crud.create_guild_record(self.mock_guild)
        assert self.crud.get_guild_record(self.mock_guild) is not None
        _, is_new = self.crud.get_or_create_guild_record(self.mock_guild)
        assert not is_new
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_get_or_create_dm_channel(self):
        self.crud.create_guild_record(None)
        assert self.crud.get_guild_record(None) is None
        _, is_new = self.crud.get_or_create_guild_record(None)
        assert is_new
        assert self.crud.get_guild_record(None) is None

    def test_user_delete_none(self):
        with pytest.raises(ValueError):
            self.crud.delete_user_record(None)

    def test_guild_delete_none(self):
        with pytest.raises(ValueError):
            self.crud.delete_guild_record(None)
