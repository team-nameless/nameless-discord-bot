import logging


__all__ = ["ColoredFormatter"]


# https://github.com/Rapptz/discord.py/blob/1ba290d8c6884daa8a8548ab203fb12bd736576d/discord/client.py#L127-L168
# I liked the design
class ColoredFormatter(logging.Formatter):
    LEVELS = [
        (logging.INFO, "\x1b[34;1m"),
        (logging.DEBUG, "\x1b[40;1m"),
        (logging.WARNING, "\x1b[33;1m"),
        (logging.ERROR, "\x1b[31m"),
        (logging.CRITICAL, "\x1b[1m"),
    ]

    FORMATS = {
        level: logging.Formatter(
            f"\x1b[30;1m%(asctime)s\x1b[0m {colour}%(levelname)-8s\x1b[0m \x1b[35m%(name)s\x1b[0m %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        for level, colour in LEVELS
    }

    def format(self, record):
        formatter = self.FORMATS.get(record.levelno, self.FORMATS[logging.DEBUG])

        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f"\x1b[31m{text}\x1b[0m"

        output = formatter.format(record)

        # Remove the cache layer
        record.exc_text = None
        return output
