"""Global defaults, quality knobs and shared regular expressions.

Centralising these here keeps the feature modules free of magic numbers and
gives the front-ends (CLI/GUI/web) a single place to read or tweak defaults.
"""

import re

# -------------------------------
# Global defaults / "quality knobs"
# -------------------------------

DEFAULT_CRF = 19                  # CPU (libx264): lower = better quality, bigger files
DEFAULT_X264_PRESET = "slow"      # CPU preset: ultrafast..placebo; "slow" is good archival default

# Whether operations write log files under the app data logs directory.
# Default off so the GUI never holds an open file handle (which locks the file on
# Windows). When the CLI runs it is turned on so historical log files are kept.
# The web UI exposes a settings toggle. Even when enabled, the file handle is
# closed as soon as the operation finishes so logs can be cleared while the app
# is open.
FILE_LOGGING_ENABLED = False

NVENC_CQ_TARGET = 19              # Roughly similar to CRF 18-19 visually for SD
NVENC_AQ_STRENGTH = 8             # 1-15; higher = more aggressive adaptive quantization

MIN_VALID_DURATION_SECONDS = 0.5  # Minimum duration to consider an MP4 "complete"

DUTCH_MONTHS = [
    None,
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
]

RE_DATE = re.compile(r"clip-(\d{4})-(\d{2})-(\d{2})", re.IGNORECASE)
RE_TIME = re.compile(r"\s(\d{2})[;:](\d{2})[;:](\d{2})")

# DVD title-set VOBs are named VTS_<set>_<part>.VOB, e.g. VTS_01_1.VOB.
# Part 0 (VTS_xx_0.VOB) is the title-set menu; parts 1..N hold the actual video,
# split into ~1 GB chunks that must be joined in order.
RE_VTS_VOB = re.compile(r"^VTS_(\d+)_(\d+)\.vob$", re.IGNORECASE)

# Default minimum joined size (MB) for a DVD title set to be converted. DVDs
# carry many tiny title sets (FBI warnings, menus, transitions); this skips
# that junk while keeping real titles. Pass --min-mb 0 to convert everything.
DEFAULT_VTS_MIN_MB = 50
