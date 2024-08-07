from datetime import UTC, datetime

is_debug: bool = False
launch_time: datetime = datetime.now(UTC)

loaded_modules: list[str] = []
rejected_modules: list[str] = []
