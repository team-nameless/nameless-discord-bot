__all__ = ["staticproperty"]


class staticproperty(property):
    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()  # pyright ignore
