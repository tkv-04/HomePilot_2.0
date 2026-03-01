#!/usr/bin/env python3
"""
HomePilot — Privacy-First Edge AI Voice Assistant
Entry point script.

Usage:
    python run.py                    # Uses default config
    python run.py -c config.yaml     # Custom config file
    python run.py -v                 # Verbose/debug mode
"""

from homepilot.main import main

if __name__ == "__main__":
    main()
