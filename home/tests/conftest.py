import os
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOME / "world"))
os.environ.pop("METIS_HOME_HA", None)          # the tests are the simulated home's
