__all__ = ["NamelessSingleton"]


class NamelessSingleton:
    _shared_state = {}

    def __new__(cls):
        obj = super().__new__(cls)
        obj.__dict__ = cls._shared_state
        return obj
