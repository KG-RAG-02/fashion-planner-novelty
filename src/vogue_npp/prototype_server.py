"""Compatibility entry point; canonical server: :mod:`vogue_npp.prototype.server`."""
from .prototype.server import *  # noqa: F401,F403
from .prototype.server import main

if __name__ == "__main__":
    main()
