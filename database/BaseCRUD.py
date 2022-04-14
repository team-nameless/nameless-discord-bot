from typing import Optional, Any

import nextcord


class BaseCRUD:
    def get_or_create_user_record(self, user: nextcord.User) -> tuple[Any, bool]:
        """
        Get an existing user record, create a new record if one doesn't exist.
        :param user: User entity of nextcord.
        :return: User record in database. True if the returned record is the new one, False otherwise.
        """
        pass

    def get_or_create_guild_record(self, guild: nextcord.Guild) -> tuple[Any, bool]:
        """
        Get an existing guild record, create a new record if one doesn't exist.
        :param guild: Guild entity of nextcord.
        :return: Guild record in database. True if the returned record is the new one, False otherwise.
        """
        pass

    def __get_user_record(self, user: nextcord.User) -> Optional[Any]:
        pass

    def __get_guild_record(self, guild: nextcord.Guild) -> Optional[Any]:
        pass

    def __create_user_record(self, user: nextcord.User) -> Any:
        pass

    def __create_guild_record(self, guild: nextcord.Guild) -> Any:
        pass

    def delete_guild_record(self, guild_record: Any) -> None:
        """
        Delete a guild record from the database.
        :param guild_record: Guild record to delete.
        """
        pass

    def delete_user_record(self, user_record: Any) -> None:
        """
        Delete a user record from the database.
        :param user_record: User record to delete.
        """
        pass

    def rollback(self) -> None:
        """
        Revert ALL changes made on current session. If you use this after save_changes(), congrats, you did nothing!
        """
        pass

    def save_changes(self) -> None:
        """
        Save changes made on current session. In some cases, this will clear the pending queue of rollback().

        "Mom, but it works in my codes!"
                    - Swyrin
        """
        pass
