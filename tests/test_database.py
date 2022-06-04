import pytest
import database
import discord

# By default, SQLite is used.
crud = database.CRUD()


class TestSQLAlchemyDatabase:
    @pytest.fixture(autouse=True)
    def fixture(self):
        global crud

        self.crud = crud
        self.mock_user = discord.Object(id=1)
        self.mock_guild = discord.Object(id=2)

        # Post-testing cleanup
        if u := self.crud.get_user_record(self.mock_user):
            self.crud.delete_user_record(u)
            self.crud.save_changes()

        if g := self.crud.get_guild_record(self.mock_guild):
            self.crud.delete_guild_record(g)
            self.crud.save_changes()

    @pytest.mark.order(1)
    def test_user_rollback(self):
        self.crud.create_user_record(self.mock_user)
        assert (u := self.crud.get_user_record(self.mock_user)) is not None
        self.crud.delete_user_record(u)
        assert self.crud.get_user_record(self.mock_user) is None
        self.crud.rollback()
        assert self.crud.get_user_record(self.mock_user) is not None

    @pytest.mark.order(2)
    def test_guild_rollback(self):
        self.crud.create_guild_record(self.mock_guild)
        assert (g := self.crud.get_guild_record(self.mock_guild)) is not None
        self.crud.delete_guild_record(g)
        assert self.crud.get_guild_record(self.mock_guild) is None
        self.crud.rollback()
        assert self.crud.get_guild_record(self.mock_guild) is not None

    @pytest.mark.order(3)
    def test_user_read_pass(self):
        self.crud.create_user_record(self.mock_user)
        assert self.crud.get_user_record(self.mock_user) is not None

    @pytest.mark.order(4)
    def test_guild_read_pass(self):
        self.crud.create_guild_record(self.mock_guild)
        assert self.crud.get_guild_record(self.mock_guild) is not None

    @pytest.mark.order(5)
    def test_user_read_fail(self):
        assert self.crud.get_user_record(self.mock_user) is None

    @pytest.mark.order(6)
    def test_guild_read_fail(self):
        assert self.crud.get_guild_record(self.mock_guild) is None

    @pytest.mark.order(7)
    def test_user_delete(self):
        self.crud.create_user_record(self.mock_user)
        assert (u := self.crud.get_user_record(self.mock_user)) is not None
        self.crud.delete_user_record(u)
        assert self.crud.get_user_record(self.mock_user) is None

    @pytest.mark.order(8)
    def test_guild_delete(self):
        self.crud.create_guild_record(self.mock_guild)
        assert (g := self.crud.get_guild_record(self.mock_guild)) is not None
        self.crud.delete_guild_record(g)
        assert self.crud.get_guild_record(self.mock_user) is None
