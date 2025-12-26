import asyncio
import contextlib
import logging
import os
import re
import signal
from pathlib import Path

import aiohttp

from nameless.config import nameless_config

CWD = Path(__file__).parent
LAVALINK_URL = "https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar"
LAVALINK_BIN = CWD / "bin" / "Lavalink.jar"
LAVALINK_CONFIG = CWD / "bin" / "application.yml"

proc: asyncio.subprocess.Process | None = None
task: asyncio.Task[None] | None = None
monitor_tasks: list[asyncio.Task[None]] = []
stop_event = asyncio.Event()

OAUTH_PATTERN = re.compile(r"YoutubeOauth2Handler\s+[-:]\s+(?P<message>.*)", re.IGNORECASE)
OAUTH_CODE_PATTERN = re.compile(r"\b[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{4}\b")


async def _monitor_lavalink_output(stream: asyncio.StreamReader) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break

        try:
            decoded = line.decode("utf-8").strip()
            match = OAUTH_PATTERN.search(decoded)
            if match:
                message = match.group("message").lower()
                if (
                    "code" in message and re.search(OAUTH_CODE_PATTERN, message)
                ) or "refreshed successfully" in message:
                    logging.warning("Lavalink YouTube OAuth2: %s", message)
                elif "token retrieved successfully" in message:
                    logging.info("Lavalink YouTube OAuth2: %s", message)
                    logging.info(
                        "Lavalink YouTube OAuth2 setup complete. You may now close the browser window.",
                    )
                    logging.info(
                        "Remember to save your OAuth2 credentials in .env to avoid reauthorization on restart."
                    )
                else:
                    logging.info("Lavalink YouTube OAuth2: %s", message)
        except Exception as e:
            logging.debug("Failed to parse Lavalink output: %s", e)


async def check_plugin_version(auto_update: bool = False) -> bool:
    """
    Check for latest version of Lavalink plugin.

    The youtube-source plugin to be specific
    """
    target = "dev.lavalink.youtube:youtube-plugin:"
    with LAVALINK_CONFIG.open("r", encoding="utf-8") as f:
        config = f.read()
    start_index = config.find(target) + 36
    end_index = config.find('"', start_index)
    version = config[start_index:end_index]

    if not version:
        logging.error("Failed to check Lavalink plugin version. Version not found.")
        return True  # Assume true to not block startup

    async with (
        aiohttp.ClientSession() as session,
        session.get("https://api.github.com/repos/lavalink-devs/youtube-source/releases/latest") as git_req,
    ):
        if git_req.status != 200:
            logging.error("Failed to check Lavalink plugin version. Request failed.")
            return True  # Assume true to not block startup
        latest_version: str = (await git_req.json()).get("tag_name", "0.0.0")

    if version == latest_version:
        return True

    logging.warning(
        "youtube-source plugin version is outdated. Current: %s, Latest: %s",
        version,
        latest_version,
    )

    if auto_update:
        new_config = config.replace(target + version, target + latest_version)
        await asyncio.to_thread(LAVALINK_CONFIG.write_text, new_config, "utf-8")
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
            git_req = await session.get("https://api.github.com/repos/lavalink-devs/Lavalink/releases/latest")
        latest_version: str = (await git_req.json()).get("tag_name", "0.0.0")
        if git_req.status != 200:
            logging.error("Failed to check Lavalink plugin version. Request failed.")
            return True  # Assume true to not block startup

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
    global proc
    while not stop_event.is_set():
        proc = await asyncio.create_subprocess_exec(
            "java",
            "-jar",
            "Lavalink.jar",
            cwd=CWD / "bin",
            stdout=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        if not os.getenv("YOUTUBE_REFRESH_TOKEN"):
            monitor_tasks.clear()
            if proc.stdout and proc.stderr:
                monitor_tasks.append(asyncio.create_task(_monitor_lavalink_output(proc.stdout)))
                monitor_tasks.append(asyncio.create_task(_monitor_lavalink_output(proc.stderr)))

        await proc.wait()
        if nameless_config.runtime.is_shutting_down or stop_event.is_set():
            break

        logging.warning("Lavalink server stopped. Restarting in 5 seconds...")
        await asyncio.sleep(5)


async def stop():
    """Stop the Lavalink server."""
    global proc, task

    stop_event.set()
    with contextlib.suppress(ProcessLookupError, ConnectionResetError, ConnectionRefusedError):
        if proc and proc.returncode is None:
            if os.name != "nt":
                proc.send_signal(signal.SIGINT)
            else:
                proc.send_signal(signal.CTRL_C_EVENT)
            await proc.wait()
            proc = None

    for monitor_task in monitor_tasks:
        if not monitor_task.done():
            monitor_task.cancel()
    monitor_tasks.clear()

    if task and not task.done():
        task.cancel()
        task = None


def check_file():
    """Check if the Lavalink.jar file exists."""
    try:
        return LAVALINK_BIN.exists()
    except FileNotFoundError:
        return False


async def download_lavalink():
    """Download Lavalink.jar from the official repo."""
    LAVALINK_BIN.parent.mkdir(parents=True, exist_ok=True)
    async with (
        aiohttp.ClientSession() as session,
        session.get(LAVALINK_URL, allow_redirects=True) as resp,
    ):
        resp.raise_for_status()
        data = await resp.read()
        LAVALINK_BIN.write_bytes(data)


async def main(loop: asyncio.AbstractEventLoop | None, auto_update: bool = False):
    """Start the Lavalink server."""
    global task

    loop = loop or asyncio.get_event_loop()

    if not check_file():
        logging.warning("Lavalink.jar not found Downloading...")
        await download_lavalink()
    elif not await check_lavalink_version():
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
