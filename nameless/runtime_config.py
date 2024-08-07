from datetime import datetime, timezone

is_debug: bool = False
launch_time: datetime = datetime.now(timezone.utc)

loaded_modules: list[str] = []
rejected_modules: list[str] = []
