__all__ = ['NamelessSingleton']


class NamelessSingleton(object):
    _shared_state = {}

    def __new__(cls, *args, **kwargs):
        obj = super(NamelessSingleton, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls._shared_state
        return obj
