__all__ = ["staticproperty"]


class staticproperty(property):
    def __get__(self, cls, owner):  # type: ignore
        return classmethod(self.fget).__get__(None, owner)()
