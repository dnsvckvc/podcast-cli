import os
import json
import shutil
import logging

from typing import Dict


def load_config():
    """
    Load configuration from config.json file.
    Raises RuntimeError if the file is not found or is malformed.
    """
    try:
        with open("config.json") as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(
            "config.json file not found. Please provide a valid config.json."
        )
    except json.JSONDecodeError:
        raise RuntimeError("config.json is malformed. Please check the file format.")


def setup_logger():
    """
    Setup a basic logger for the application.
    Returns a logger instance.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
    )
    return logging.getLogger(__name__)


def copy_cookies(config: Dict):
    """
    Copy YouTube cookies from the specified path in config to a temporary location.
    This is necessary for authenticated requests to YouTube.
    """
    if not config["youtube"].get("cookies_path"):
        raise RuntimeError("YouTube cookies path not configured in config.json")

    cookie_src = os.path.join(os.getcwd(), config["youtube"]["cookies_path"])
    cookie_dst = os.path.join("/tmp", os.path.basename(cookie_src))
    shutil.copy(cookie_src, cookie_dst)
    config["youtube"]["cookies_path"] = cookie_dst
