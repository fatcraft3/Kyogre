import os
import sys
import logging
import logging.handlers

def init_loggers():
    # d.py stuff
    dpy_logger = logging.getLogger("discord")
    dpy_logger.setLevel(logging.WARNING)
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    dpy_logger.info("dpy logging level set to debug")
    dpy_logger.addHandler(console)

    # Kyogre

    logger = logging.getLogger("kyogre")

    kyogre_format = logging.Formatter(
        '%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(kyogre_format)
    logger.setLevel(logging.INFO)
    print("log level set to Debug")

    logfile_path = 'logs/kyogre.log'
    fhandler = logging.handlers.RotatingFileHandler(
        filename=str(logfile_path), encoding='utf-8', mode='a',
        maxBytes=400000, backupCount=20)
    fhandler.setFormatter(kyogre_format)

    logger.addHandler(fhandler)

    # logger.addHandler(stdout_handler)

    return logger


def init_logger(name, path):
    logger = logging.getLogger(name)

    kyogre_format = logging.Formatter(
        '%(asctime)s: %(message)s',
        datefmt="[%m/%d %H:%M]")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(kyogre_format)
    logger.setLevel(logging.INFO)

    logfile_path = path
    fhandler = logging.handlers.RotatingFileHandler(
        filename=str(logfile_path), encoding='utf-8', mode='a',
        maxBytes=400000, backupCount=20)
    fhandler.setFormatter(kyogre_format)

    logger.addHandler(fhandler)
    return logger
