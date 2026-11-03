"""Read-only cross-stack dependency license inventory (Python / Java / Node).

Emits declared-or-resolved package names, versions and license metadata only.
No network calls, no provider calls, no credential reads, no writes outside --out.

Typical use:

    # 1) resolve the Java graph once (network needed only for this step)
    cd services/api && ./mvnw -B -q dependency:list -DoutputFile=<tmp>/mvn-deps.txt

    # 2) collect metadata from what is already on disk
    uv run --project services/ai python scripts/audit-dependencies.py \
        --mvn-list <tmp>/mvn-deps.txt \
        --out docs/reviews/2026-11-03-dependency-inventory.json

The output is an inventory, not a legal approval. Platform-only wheels and
classifier artifacts that are not installed locally stay `UNKNOWN` on purpose.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POM = "{http://maven.apache.org/POM/4.0.0}"

SPDX_HINTS = (
    ("apache", "Apache-2.0"),
    ("mit", "MIT"),
    ("bsd-3", "BSD-3-Clause"),
    ("bsd 3", "BSD-3-Clause"),
    ("bsd-2", "BSD-2-Clause"),
    ("bsd 2", "BSD-2-Clause"),
    ("eclipse distribution", "EDL-1.0"),
    ("edl", "EDL-1.0"),
    ("eclipse public license v2", "EPL-2.0"),
    ("eclipse public license 2", "EPL-2.0"),
    ("epl-2.0", "EPL-2.0"),
    ("epl 2.0", "EPL-2.0"),
    ("eclipse public license v1", "EPL-1.0"),
    ("eclipse public license 1", "EPL-1.0"),
    ("lgpl", "LGPL"),
    ("gpl2 w/ cpe", "GPL-2.0-with-CPE"),
    ("mpl", "MPL-2.0"),
    ("public domain", "Public-Domain"),
    ("cc0", "CC0-1.0"),
    ("cc-by", "CC-BY-4.0"),
    ("psf", "PSF-2.0"),
    ("python", "PSF-2.0"),
    ("blueoak", "BlueOak-1.0.0"),
    ("isc", "ISC"),
    ("0bsd", "0BSD"),
)


def family(license_text: str) -> str:
    """Collapse vendor-specific license names into a reviewable family label."""
    text = (license_text or "").lower()
    if not text or text == "unknown":
        return "UNKNOWN"
    for needle, label in SPDX_HINTS:
        if needle in text:
            return label
    return "OTHER"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ python
def venv_site(project: Path) -> Path | None:
    candidates = [
        project / ".venv" / "Lib" / "site-packages",
        *sorted(project.glob(".venv/lib/python*/site-packages")),
    ]
    return next((c for c in candidates if c.is_dir()), None)


def python_section() -> dict:
    project = REPO / "services" / "ai"
    lock = project / "uv.lock"
    packages = tomllib.loads(lock.read_text(encoding="utf-8"))["package"]
    site = venv_site(project)
    installed = {}
    if site is not None:
        installed = {d.metadata["Name"].lower().replace("_", "-"): d
                     for d in md.distributions(path=[str(site)])}
    rows = []
    for pkg in packages:
        name = pkg["name"]
        dist = installed.get(name.lower().replace("_", "-"))
        row = {"name": name, "version": pkg["version"]}
        if dist is None:
            row.update(installed=False, license="UNKNOWN",
                       note="not installed on this platform; license not inspected")
        else:
            meta = dist.metadata
            expression = meta.get("License-Expression")
            legacy = (meta.get("License") or "").strip()
            classifiers = [c for c in meta.get_all("Classifier", []) if c.startswith("License ::")]
            if expression:
                value = expression
            elif legacy and len(legacy) < 80 and "\n" not in legacy:
                value = legacy
            elif classifiers:
                value = classifiers[0].replace("License :: ", "").replace(" :: ", " / ")
            else:
                value = "UNKNOWN"
            row.update(installed=True, license=value,
                       license_expression=expression,
                       license_classifiers=classifiers)
        row["family"] = family(row["license"])
        rows.append(row)
    return {
        "manifest": "services/ai/uv.lock",
        "manifest_sha256": sha256(lock),
        "collected_with_python": sys.version.split()[0],
        "package_count": len(rows),
        "packages": rows,
    }


# -------------------------------------------------------------------- java
def settings_local_repository() -> Path | None:
    settings = Path.home() / ".m2" / "settings.xml"
    if not settings.is_file():
        return None
    try:
        root = ET.parse(settings).getroot()
    except ET.ParseError:
        return None
    text = root.findtext("{http://maven.apache.org/SETTINGS/1.0.0}localRepository") or root.findtext("localRepository")
    return Path(text.strip()) if text and text.strip() else None


def pom_licenses(pom: Path, depth: int = 0) -> list[str]:
    """License names declared by a pom, following the parent chain when absent."""
    if not pom.is_file() or depth > 6:
        return []
    try:
        root = ET.parse(pom).getroot()
    except ET.ParseError:
        return []
    names = [(lic.findtext(f"{POM}name") or "").strip()
             for lic in root.findall(f"{POM}licenses/{POM}license")]
    names = [n for n in names if n]
    if names:
        return names
    parent = root.find(f"{POM}parent")
    if parent is None:
        return []
    gid = (parent.findtext(f"{POM}groupId") or "").strip()
    aid = (parent.findtext(f"{POM}artifactId") or "").strip()
    ver = (parent.findtext(f"{POM}version") or "").strip()
    if not (gid and aid and ver):
        return []
    return pom_licenses(maven_repo / Path(*gid.split(".")) / aid / ver / f"{aid}-{ver}.pom", depth + 1)


def java_section(mvn_list: Path | None) -> dict:
    if mvn_list is None or not mvn_list.is_file():
        return {"status": "SKIPPED", "reason": "--mvn-list not provided", "artifact_count": 0, "artifacts": []}
    pattern = re.compile(r"^\s{3}([\w.\-]+):([\w.\-]+):(\w+):([\w.\-.]+):([\w\-]+)")
    rows = []
    for line in mvn_list.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        group, artifact, _type, version, scope = match.groups()
        pom = maven_repo / Path(*group.split(".")) / artifact / version / f"{artifact}-{version}.pom"
        licenses = pom_licenses(pom)
        label = " / ".join(dict.fromkeys(licenses)) or "UNKNOWN"
        rows.append({
            "group": group,
            "artifact": artifact,
            "version": version,
            "scope": scope,
            "license": label,
            "family": family(label),
            "pom_present": pom.is_file(),
        })
    rows.sort(key=lambda r: (r["group"], r["artifact"], r["version"]))
    return {
        "source": str(mvn_list.name),
        "maven_repo": str(maven_repo),
        "artifact_count": len(rows),
        "artifacts": rows,
    }


# -------------------------------------------------------------------- node
def node_section() -> dict:
    lock_path = REPO / "apps" / "web" / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    rows = []
    for path, meta in lock.get("packages", {}).items():
        if not path:
            continue
        license_text = meta.get("license") or "UNKNOWN"
        rows.append({
            "name": meta.get("name") or path.split("node_modules/")[-1],
            "version": meta.get("version"),
            "dev": bool(meta.get("dev")),
            "license": license_text,
            "family": family(license_text),
        })
    rows.sort(key=lambda r: (r["name"], r["version"] or ""))
    return {
        "manifest": "apps/web/package-lock.json",
        "manifest_sha256": sha256(lock_path),
        "lockfile_version": lock.get("lockfileVersion"),
        "package_count": len(rows),
        "packages": rows,
    }


def summarize(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["family"]] = counts.get(row["family"], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mvn-list", type=Path, help="output of: mvn dependency:list -DoutputFile=...")
    parser.add_argument("--maven-repo", type=Path, help="Maven local repository (default: settings.xml or ~/.m2/repository)")
    parser.add_argument("--out", type=Path, help="write the inventory JSON here")
    args = parser.parse_args()

    global maven_repo
    maven_repo = args.maven_repo or settings_local_repository() or Path.home() / ".m2" / "repository"

    python_rows = python_section()
    java_rows = java_section(args.mvn_list)
    node_rows = node_section()
    inventory = {
        "scope": "Local read-only inventory of declared/resolved dependencies. Metadata only, not a legal approval.",
        "python": python_rows,
        "java": java_rows,
        "node": node_rows,
        "summary": {
            "python": summarize(python_rows["packages"]),
            "java": summarize(java_rows["artifacts"]),
            "node": summarize(node_rows["packages"]),
        },
    }
    text = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)
    print(f"python={python_rows['package_count']} java={java_rows['artifact_count']} node={node_rows['package_count']}",
          file=sys.stderr)
    for stack, counts in inventory["summary"].items():
        print(f"{stack}: " + ", ".join(f"{k}={v}" for k, v in counts.items()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
