"""
OmniView IQ — Feature 2 Live Tester Page
=========================================
"""

import sys
from pathlib import Path

# Ensure dashboard root is on path
dashboard_dir = Path(__file__).resolve().parent.parent
if str(dashboard_dir) not in sys.path:
    sys.path.insert(0, str(dashboard_dir))

# Execute the live tester dashboard
import omniview.dashboard.live_tester

