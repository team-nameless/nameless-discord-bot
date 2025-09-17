import asyncio
import logging
import signal
from pathlib import Path

import aiohttp

if __name__ == "__main__":
    nameless_config = {"runtime": {"is_shutting_down": False}}
else:
    from nameless.config import nameless_config

CWD = Path(__file__).parent
LAVALINK_URL = (
    "https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar"
)
LAVALINK_BIN = CWD / "bin" / "Lavalink.jar"
LAVALINK_CONFIG = CWD / "bin" / "application.yml"

proc: asyncio.subprocess.Process | None = None
task: asyncio.Task[None] | None = None
stop_event = asyncio.Event()


async def check_plugin_version(auto_update: bool = False) -> bool:
    """
    Check for latest version of Lavalink plugin.

    The youtube-source plugin to be specific
    """
    target = "dev.lavalink.youtube:youtube-plugin:"

    with open(LAVALINK_CONFIG) as f:
        config = f.read()
        start_index = config.find(target) + 36
        end_index = config.find('"', start_index)
        version = config[start_index:end_index]

        if not version:
            logging.error("Failed to check Lavalink plugin version. Version not found.")
            return False

        async with aiohttp.ClientSession() as session:
            git_req = await session.get(
                "https://api.github.com/repos/lavalink-devs/youtube-source/releases/latest"
            )
        if git_req.status != 200:
            logging.error("Failed to check Lavalink plugin version. Request failed.")
            return False

        latest_version: str = (await git_req.json()).get("tag_name", "0.0.0")  # pyright: ignore[reportAny]

        if version == latest_version:
            return True

        logging.warning(
            "youtube-source plugin version is outdated. Current: %s, Latest: %s",
            version,
            latest_version,
        )

        if auto_update:
            with open(LAVALINK_CONFIG, "w") as f:
                f.write(config.replace(target + version, target + latest_version))
            logging.info("Updated youtube-source plugin to version %s", latest_version)
            return True

        return False


async def check_lavalink_version() -> bool:
    """Check for latest version of Lavalink.

    Returns
    -------
        bool: True if the version is the latest, False otherwise
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "java", "-jar", "Lavalink.jar", "-v", cwd=CWD / "bin", stdout=-1, stderr=-1
        )
        status_code = await proc.wait()
        if status_code != 0:
            logging.error("Failed to check Lavalink version.")
            return False

        stdout = proc.stdout
        if not stdout:
            logging.error("Failed to check Lavalink version. stdout somehow empty.")
            return False

        version = ""
        r = await stdout.read()
        r_decode = r.decode("utf-8")
        for line in r_decode.splitlines():
            if "Version: " in line:
                version = line.split("Version: ")[1].strip()

        if not version:
            logging.error("Failed to check Lavalink version. Version not found.")
            return False
        async with aiohttp.ClientSession() as session:
            git_req = await session.get(
                "https://api.github.com/repos/lavalink-devs/Lavalink/releases/latest"
            )
        latest_version: str = (await git_req.json()).get("tag_name", "0.0.0")  # pyright: ignore[reportAny]
        if git_req.status != 200:
            logging.error("Failed to check Lavalink plugin version. Request failed.")
            return False

        if version == latest_version:
            return True

        logging.warning(
            "Lavalink version is outdated. Current: %s, Latest: %s",
            version,
            latest_version,
        )
        return False

    except FileNotFoundError:
        return False

    except Exception as e:
        logging.error(
            "An error occurred while checking Lavalink version [%s]: %s",
            e.__class__.__name__,
            e,
        )
        return False


async def start():
    """Start the Lavalink server from /bin folder."""
    global proc, stop_event
    while True:
        proc = await asyncio.create_subprocess_exec(
            "java", "-jar", "Lavalink.jar", cwd=CWD / "bin", stdout=-3
        )
        await proc.wait()
        if nameless_config["runtime"]["is_shutting_down"]:
            stop_event.set()
            break

        logging.warning("Lavalink server stopped. Restarting in 5 seconds...")
        await asyncio.sleep(5)


async def stop():
    """Stop the Lavalink server."""
    global proc, task, stop_event

    if proc:
        proc.send_signal(signal.CTRL_C_EVENT)
        await proc.wait()
        proc = None

    if task:
        await stop_event.wait()
        task.cancel()
        task = None


def check_file():
    """Check if the Lavalink.jar file exists."""
    try:
        with open(LAVALINK_BIN):
            return True
    except FileNotFoundError:
        return False


async def download_lavalink():
    """Download Lavalink.jar from the official repo."""
    LAVALINK_BIN.parent.mkdir(parents=True, exist_ok=True)
    async with (
        aiohttp.ClientSession() as session,
        session.get(LAVALINK_URL, allow_redirects=True) as resp,
    ):
        with open(LAVALINK_BIN, "wb") as f:
            f.write(await resp.read())


async def main(loop: asyncio.AbstractEventLoop | None, auto_update: bool = False):
    """Start the Lavalink server."""
    global task

    loop = loop or asyncio.get_event_loop()

    if not check_file():
        logging.warning("Lavalink.jar not found Downloading...")
        await download_lavalink()
    else:
        if not await check_lavalink_version():
            if auto_update:
                logging.info("Updating Lavalink...")
                await download_lavalink()
                logging.info("Lavalink updated.")
            else:
                logging.warning("Please update Lavalink to the latest version.")

    await check_plugin_version(auto_update)

    task = loop.create_task(start())


if __name__ == "__main__":
    asyncio.run(main(None, auto_update=True))
