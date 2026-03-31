"""Allow running as `python -m arxiv_brew`."""

from .pipeline import main
raise SystemExit(main())
