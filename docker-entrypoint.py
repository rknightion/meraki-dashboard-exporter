#!/usr/bin/env python
"""Docker entrypoint for Meraki Dashboard Exporter."""

import sys

# Add the app directory to Python path
sys.path.insert(0, "/app")

# Import and run the main function
from meraki_dashboard_exporter.__main__ import main

if __name__ == "__main__":
    main()
