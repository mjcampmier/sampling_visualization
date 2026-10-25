"""Convenience launcher for the Sensor Placement Lab.

The app is a Streamlit app, so the canonical way to run it is:

    streamlit run app.py

This file just lets you hit the green "Run" button in PyCharm and have the
same thing happen (it shells out to `streamlit run app.py`).
"""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    app = Path(__file__).with_name("app.py")
    sys.exit(subprocess.call(
        [sys.executable, "-m", "streamlit", "run", str(app)]
    ))
