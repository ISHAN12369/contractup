"""Download only the pinned official artifact; never execute or extract archive paths."""
import argparse
import hashlib
import urllib.request
from pathlib import Path

from evals.data import CUAD_SHA256, CUAD_URL, digest


def prepare(path: Path) -> None:
    if path.exists():
        if digest(path) != CUAD_SHA256:
            raise ValueError("Existing CUAD archive has a different checksum")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(CUAD_URL, timeout=60) as response:
        content = response.read(50 * 1024 * 1024 + 1)
    if len(content) > 50 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != CUAD_SHA256:
        raise ValueError("CUAD download failed size/checksum validation")
    path.write_bytes(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evals/.cache/cuad-data.zip"))
    args = parser.parse_args()
    prepare(args.output)
    print(f"Verified CUAD: {args.output}")
