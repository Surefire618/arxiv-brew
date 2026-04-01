"""Exit code contract for all arxiv-brew CLI commands.

Exit codes:
    0  SUCCESS          — ran successfully, results produced
    1  NO_MATCHES       — ran successfully, but no papers matched filters
    2  CONFIG_ERROR     — missing/invalid config, profile, or keyword DB
    3  NETWORK_ERROR    — failed to reach arxiv.org or API
    4  PARSE_ERROR      — malformed input file (bad JSON, unreadable XML)
"""

SUCCESS = 0
NO_MATCHES = 1
CONFIG_ERROR = 2
NETWORK_ERROR = 3
PARSE_ERROR = 4
