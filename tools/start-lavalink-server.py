import os
import re
import subprocess

from packaging import version

pattern = r"\"(\d+\.\d+).*\""
sep = os.sep
lavalink_run_cmd = ["java", "-jar", f".{sep}ext{sep}lavalink_server{sep}Lavalink.jar"]

java_version = ""

try:
    java_version = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT).decode()
except FileNotFoundError:
    raise FileNotFoundError("Java is not installed") from None

java_version = re.search(pattern, java_version).groups()[0]
java_version = version.parse(java_version)

if java_version.major < 17:
    raise NotImplementedError("Lavalink server requires Java version 17 or higher.")

try:
    lavalink_version = subprocess.check_output([*lavalink_run_cmd, "--version"], stderr=subprocess.STDOUT).decode()
except FileNotFoundError:
    raise FileNotFoundError("Lavalink is not installed") from None

# We only need the first line
lavalink_version = lavalink_version.split("\n")[1].replace("Version:        ", "")
lavalink_version = version.parse(lavalink_version)

if lavalink_version.major < 4:
    raise NotImplementedError("nameless requires Lavalink version 4 or higher.")

print("Java version", java_version)
print("Lavalink version", lavalink_version)

subprocess.run(lavalink_run_cmd)
