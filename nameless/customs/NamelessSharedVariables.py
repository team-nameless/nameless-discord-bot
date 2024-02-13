import datetime

from customs import NamelessSingleton

__all__ = ['NamelessSharedVariables']


class NamelessSharedVariables(NamelessSingleton):
    """A static, singleton class that stores shared runtime variables across nameless* infrastructures."""
    nameless_start_time: datetime.datetime
    nameless_debug_mode: bool
    loaded_modules: list[str]
    rejected_modules: list[str]

    def __init__(self):
        super().__init__()
        self.nameless_start_time = datetime.datetime.min
        self.nameless_debug_mode = False
        self.loaded_modules = []
        self.rejected_modules = []
