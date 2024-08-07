from datetime import datetime

is_debug: bool = False
launch_time: datetime = datetime.now()

loaded_modules: list[str] = []
rejected_modules: list[str] = []
