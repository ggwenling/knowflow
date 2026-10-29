"""Reproduce the KF2-003 license check; downloads wheels without installing them."""

import argparse
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
import zipfile
from zoneinfo import ZoneInfo

CANDIDATES = {"PyMuPDF": "2.0", "pypdf": "6.21.4"}
MAX_WHEEL_BYTES = 80 * 1024 * 1024


def audit(name, version):
    metadata_url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urlopen(metadata_url, timeout=20) as response:
        package = json.load(response)
    files = package["urls"]
    wheel = next(
        f for f in files
        if f["filename"].endswith("py3-none-any.whl")
        or f["filename"].endswith("cp311-abi3-manylinux_2_28_x86_64.whl")
    )
    if wheel["size"] > MAX_WHEEL_BYTES:
        raise ValueError("wheel exceeds audit limit")
    with urlopen(wheel["url"], timeout=20) as response:
        data = response.read(MAX_WHEEL_BYTES + 1)
    if len(data) > MAX_WHEEL_BYTES:
        raise ValueError("wheel exceeds audit limit")
    sha256 = hashlib.sha256(data).hexdigest()
    if sha256 != wheel["digests"]["sha256"]:
        raise ValueError("wheel digest mismatch")
    licenses = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for path in archive.namelist():
            if ".dist-info/" in path and ("COPYING" in path or path.lower().endswith(("license", "license.txt", "license.md"))):
                content = archive.read(path)
                licenses.append({"path": path, "sha256": hashlib.sha256(content).hexdigest(),
                                 "bytes": len(content)})
    if not licenses:
        raise ValueError("license file missing")
    info = package["info"]
    return {
        "name": name, "version": version, "metadata_url": metadata_url,
        "requires_python": info.get("requires_python"),
        "license_expression": info.get("license_expression"), "license_metadata": info.get("license"),
        "wheel": wheel["filename"], "wheel_url": wheel["url"], "wheel_sha256": sha256,
        "wheel_digest_verified": True, "license_files": licenses, "installed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new evidence file")
    report = {"recorded_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
              "scope": "Direct parser candidates only; not an installed service lock or transitive audit.",
              "packages": [audit(name, version) for name, version in CANDIDATES.items()]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write("\n")


if __name__ == "__main__":
    main()
