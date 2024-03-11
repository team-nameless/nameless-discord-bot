from .NamelessPlayer import *
from .NamelessQueue import *
from .NamelessSharedVariables import NamelessSharedVariables
from .NamelessSingleton import *

# If you are asking why this line is commented
# It is because circular import(TM)
# from .NamelessCommandTree import *

shared_variables = NamelessSharedVariables()
