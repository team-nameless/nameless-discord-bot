import discord
import pytest

from nameless.database import CRUD


class TestDatabase:
    @pytest.fixture(autouse=True)
    def fixture(self):
        CRUD.init()

        self.mock_user = discord.Object(id=1)  # pylint: disable=W0201
        self.mock_guild = discord.Object(id=2)  # pylint: disable=W0201

        yield

        # Post-testing cleanup
        if u := CRUD.get_user_record(self.mock_user):
            CRUD.delete_user_record(u)
            

        if g := CRUD.get_guild_record(self.mock_guild):
            CRUD.delete_guild_record(g)
            

    def test_user_rollback(self):
        # Non-existence -> Created
        assert CRUD.get_user_record(self.mock_user) is None
        CRUD.create_user_record(self.mock_user)
        assert (u := CRUD.get_user_record(self.mock_user)) is not None

        # Created -> Non-existence
        CRUD.delete_user_record(u)
        assert CRUD.get_user_record(self.mock_user) is None

        # Go back: Non-existence -> Created
        CRUD.rollback()
        assert CRUD.get_user_record(self.mock_user) is not None

    def test_guild_rollback(self):
        # Non-existence -> Created
        assert CRUD.get_guild_record(self.mock_guild) is None
        CRUD.create_guild_record(self.mock_guild)
        assert (g := CRUD.get_guild_record(self.mock_guild)) is not None

        # Created -> Non-existence
        CRUD.delete_guild_record(g)
        assert CRUD.get_guild_record(self.mock_guild) is None

        # Go back: Non-existence -> Created
        CRUD.rollback()
        assert CRUD.get_guild_record(self.mock_guild) is not None

    def test_user_read_pass(self):
        CRUD.create_user_record(self.mock_user)
        assert CRUD.get_user_record(self.mock_user) is not None

    def test_guild_read_pass(self):
        CRUD.create_guild_record(self.mock_guild)
        assert CRUD.get_guild_record(self.mock_guild) is not None

    def test_user_delete(self):
        # Create a fake one
        u = CRUD.create_user_record(self.mock_user)

        CRUD.delete_user_record(u)
        assert CRUD.get_user_record(self.mock_user) is None

    def test_guild_delete(self):
        # Create a fake one
        g = CRUD.create_guild_record(self.mock_guild)

        CRUD.delete_guild_record(g)
        assert CRUD.get_guild_record(self.mock_guild) is None

    def test_guild_write_once_more(self):
        CRUD.create_guild_record(self.mock_guild)
        CRUD.create_guild_record(self.mock_guild)
        assert CRUD.get_guild_record(self.mock_guild) is not None

    def test_user_write_once_more(self):
        CRUD.create_user_record(self.mock_user)
        CRUD.create_user_record(self.mock_user)
        assert CRUD.get_user_record(self.mock_user) is not None

    def test_get_or_create_user(self):
        assert CRUD.get_user_record(self.mock_user) is None
        CRUD.get_or_create_user_record(self.mock_user)
        assert CRUD.get_user_record(self.mock_user) is not None

    def test_get_or_create_guild(self):
        assert CRUD.get_guild_record(self.mock_guild) is None
        CRUD.get_or_create_guild_record(self.mock_guild)
        assert CRUD.get_guild_record(self.mock_guild) is not None

    def test_get_or_create_user_none_before(self):
        assert CRUD.get_user_record(self.mock_user) is None

    def test_get_or_create_guild_none_before(self):
        assert CRUD.get_guild_record(self.mock_guild) is None

    def test_get_or_create_user_existed_before(self):
        # Create fake user
        CRUD.create_user_record(self.mock_user)

        assert CRUD.get_user_record(self.mock_user) is not None

    def test_get_or_create_guild_existed_before(self):
        # Create fake guild
        CRUD.create_guild_record(self.mock_guild)

        assert CRUD.get_guild_record(self.mock_guild) is not None

    def test_get_or_create_dm_channel(self):
        # Guild is None -> DM channel

        with pytest.raises(ValueError):
            CRUD.get_or_create_guild_record(None)
            CRUD.create_guild_record(None)
            CRUD.get_guild_record(None)

    def test_user_delete_none(self):
        with pytest.raises(ValueError):
            CRUD.delete_user_record(None)

    def test_guild_delete_none(self):
        with pytest.raises(ValueError):
            CRUD.delete_guild_record(None)
