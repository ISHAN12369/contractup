"""Offline-first evaluation of the existing ContractIQ application components."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "contractiq-backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
