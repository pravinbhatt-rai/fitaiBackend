import logging
import sys


def _build_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        log.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        log.addHandler(handler)
        log.propagate = False
    return log


logger = _build_logger("fitai")


def get_logger(name: str) -> logging.Logger:
    return _build_logger(name)
