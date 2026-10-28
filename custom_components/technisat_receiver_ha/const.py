"""Constants for TechniSat Receiver HA."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "technisat_receiver_ha"

CONF_PIN: Final = "pin"
CONF_SERIAL: Final = "serial"
CONF_MODEL: Final = "model"
CONF_SW_VERSION: Final = "sw_version"
CONF_HW_VERSION: Final = "hw_version"
CONF_MAC: Final = "mac"
CONF_STATUS_ENTITY: Final = "status_entity"
CONF_POWER_THRESHOLD: Final = "power_threshold"

DEFAULT_PIN: Final = "0000"
DEFAULT_POWER_THRESHOLD: Final = 9.0  # watts; "on" if a power sensor reads more

SCAN_INTERVAL_SECONDS: Final = 30

KEY_STANDBY: Final = 11  # toggles between operation and standby

# Remote key names -> protocol key codes.
#
# The codes come from the publicly documented protocol
# (https://github.com/feuster/TechniSatAPI). Only "standby" and "menu" were
# verified on a DIGIT ISIO STC+ so far; the others are expected to work but
# have not been tested individually. A plain number (0-127) is also accepted
# by ``remote.send_command`` and sent as-is.
KEYS: Final[dict[str, int]] = {
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "standby": 11,
    "mute": 12,
    "list": 14,
    "vol_up": 15,
    "vol_down": 16,
    "help": 17,
    "prog_up": 18,
    "prog_down": 19,
    "back": 20,
    "audio": 21,
    "epg": 23,
    "teletext": 25,
    "off": 26,
    "tv_sat": 28,
    "info": 29,
    "up": 30,
    "down": 31,
    "menu": 32,
    "tv_radio": 33,
    "left": 34,
    "right": 35,
    "ok": 36,
    "red": 37,
    "green": 38,
    "yellow": 39,
    "blue": 40,
    "option": 41,
    "sleep": 42,
    "record": 43,
    "rewind": 49,
    "stop": 50,
    "play_pause": 51,
    "forward": 52,
    "subtitle": 61,
    "page_up": 63,
    "page_down": 64,
    "pvr": 65,
    "timer": 67,
}

VERIFIED_KEYS: Final = frozenset({"standby", "menu"})
