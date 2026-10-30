"""Installed Linux environment metadata, linked to lock hashes; no license approval claim."""
import hashlib
import importlib.metadata as md
import json
from pathlib import Path
import tomllib

root = Path(__file__).resolve().parents[1]
lock = root / 'uv.lock'
packages = tomllib.loads(lock.read_text())['package']
rows = []
for package in packages:
    row = {'name': package['name'], 'version': package['version'], 'installed': False}
    try:
        dist = md.distribution(package['name'])
        row.update(installed=True, license_expression=dist.metadata.get('License-Expression'),
                   license_metadata=dist.metadata.get('License'),
                   license_classifiers=[x for x in dist.metadata.get_all('Classifier', []) if x.startswith('License ::')])
        row['license_files'] = []
        for file in dist.files or []:
            if any(part.lower() in ('licenses', 'license', 'copying') or part.lower().startswith(('license.', 'copying.')) for part in file.parts):
                path = dist.locate_file(file)
                if path.is_file():
                    row['license_files'].append({'path': str(file), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    except md.PackageNotFoundError:
        row['unknown_reason'] = 'Not installed on this platform; license not inspected.'
    rows.append(row)
report = {'scope': 'Installed Linux CPython 3.12 runtime + dev metadata, not legal approval. Wheel/sdist hashes in uv.lock; platform-only packages not installed remain unreviewed.',
          'lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
          'build_backend': 'uv_build==0.12.23 (isolated build dependency; not installed metadata)',
          'packages': rows}
(root / 'docs/evidence/dependency-licenses.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('license metadata packages:',len(rows))
