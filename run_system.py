"""Compatibility alias for the safe system entry point.

Both ``python start.py`` and ``python run_system.py`` now use exactly the same
startup path, including DEMO EXECUTION = OFF on every process start/restart.
"""
from start import main


if __name__ == "__main__":
    main()
