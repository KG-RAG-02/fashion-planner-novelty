"""Compatibility entry point; canonical module: :mod:`vogue_npp.sources.hm.hm_data`."""
from .sources.hm.hm_data import *  # noqa: F401,F403
from .sources.hm.hm_data import main

if __name__ == "__main__":
    raise SystemExit(main())
