from datetime import datetime
from typing import List

is_debug: bool = False
launch_time: datetime = datetime.now()

loaded_modules: List[str] = []
rejected_modules: List[str] = []
