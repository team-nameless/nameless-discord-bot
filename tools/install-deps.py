import os
import subprocess

sep = os.sep

subprocess.run(["pip", "install", "-U", "-r", "requirements_core.txt", "-r", "requirements_dev.txt"])
