from filelock import FileLock

from NamelessConfig import NamelessConfig


# We print the version and update version file, then f- off.
def sanity_check():
    print(NamelessConfig.__version__)

    with FileLock('version.txt.lock'):
        with open("version.txt", "w") as version_file:
            version_file.write(NamelessConfig.__version__)


if __name__ == "__main__":
    sanity_check()
