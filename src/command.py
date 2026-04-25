from enum import Enum,IntEnum

class COMMAND(int,Enum):
    DISCOVER = 1
    ACTIVE   = 2
    MESSAGE  = 3
    FILE     = 4
    FOLDER   = 5
