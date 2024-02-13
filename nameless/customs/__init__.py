from .staticproperty import *
# If you are asking why this line is commented
# It is because circular import(TM)
# from .NamelessCommandTree import *
from .NamelessSingleton import *
from .NamelessSharedVariables import *

shared_variables = NamelessSharedVariables()
