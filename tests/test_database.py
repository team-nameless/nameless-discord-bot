import discord
import pytest

from nameless import database


_crud = database.CRUD()


class TestDatabase:
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
        # Non-existence -> Created
        assert self.crud.get_user_record(self.mock_user) is None
        self.crud.create_user_record(self.mock_user)
        assert (u := self.crud.get_user_record(self.mock_user)) is not None

        # Created -> Non-existence
        self.crud.delete_user_record(u)
        assert self.crud.get_user_record(self.mock_user) is None

        # Go back: Non-existence -> Created
        self.crud.rollback()
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_guild_rollback(self):
        # Non-existence -> Created
        assert self.crud.get_guild_record(self.mock_guild) is None
        self.crud.create_guild_record(self.mock_guild)
        assert (g := self.crud.get_guild_record(self.mock_guild)) is not None

        # Created -> Non-existence
        self.crud.delete_guild_record(g)
        assert self.crud.get_guild_record(self.mock_guild) is None

        # Go back: Non-existence -> Created
        self.crud.rollback()
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_user_read_pass(self):
        self.crud.create_user_record(self.mock_user)
        assert self.crud.get_user_record(self.mock_user) is not None

    def test_guild_read_pass(self):
        self.crud.create_guild_record(self.mock_guild)
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_user_delete(self):
        # Create a fake one
        u = self.crud.create_user_record(self.mock_user)

        self.crud.delete_user_record(u)
        assert self.crud.get_user_record(self.mock_user) is None

    def test_guild_delete(self):
        # Create a fake one
        g = self.crud.create_guild_record(self.mock_guild)

        self.crud.delete_guild_record(g)
        assert self.crud.get_guild_record(self.mock_guild) is None

    def test_guild_write_once_more(self):
        self.crud.create_guild_record(self.mock_guild)
        self.crud.create_guild_record(self.mock_guild)
        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_user_write_once_more(self):
        self.crud.create_user_record(self.mock_user)
        self.crud.create_user_record(self.mock_user)
        assert self.crud.get_user_record(self.mock_user) is not None

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

    def test_get_or_create_guild_none_before(self):
        assert self.crud.get_guild_record(self.mock_guild) is None

    def test_get_or_create_user_existed_before(self):
        # Create fake user
        self.crud.create_user_record(self.mock_user)

        assert self.crud.get_user_record(self.mock_user) is not None

    def test_get_or_create_guild_existed_before(self):
        # Create fake guild
        self.crud.create_guild_record(self.mock_guild)

        assert self.crud.get_guild_record(self.mock_guild) is not None

    def test_get_or_create_dm_channel(self):
        # Guild is None -> DM channel

        with pytest.raises(ValueError):
            self.crud.get_or_create_guild_record(None)
            self.crud.create_guild_record(None)
            self.crud.get_guild_record(None)

    def test_user_delete_none(self):
        with pytest.raises(ValueError):
            self.crud.delete_user_record(None)

    def test_guild_delete_none(self):
        with pytest.raises(ValueError):
            self.crud.delete_guild_record(None)
