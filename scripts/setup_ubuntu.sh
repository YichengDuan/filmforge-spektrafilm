#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$FILMFORGE_ROOT"
mkdir -p .deps/packages .deps/root logs
python3 scripts/fetch_upstreams.py
# Downloads only: never sudo, apt install, driver changes, or remote installers.
if [[ ! -s .deps/packages.sha256 ]] || ! sha256sum --check --status .deps/packages.sha256; then
  mapfile -t packages < .deps/package-versions.txt
  (cd .deps/packages && apt-get download "${packages[@]}")
fi
for package in .deps/packages/*.deb; do dpkg-deb -x "$package" .deps/root; done
[[ -x .venv/bin/python ]] || uv venv --python 3.13.7 .venv
if [[ -s requirements.lock ]]; then
  uv pip sync --python .venv/bin/python requirements.lock
else
  uv pip install --python .venv/bin/python -e 'upstream/spektrafilm[dev]'
fi
uv pip freeze --python .venv/bin/python | sed 's|^-e .*upstream/spektrafilm$|-e ./upstream/spektrafilm|' > requirements.lock
sha256sum .deps/packages/*.deb > .deps/packages.sha256
for name in spektrafilm spektrafilm-ofx openfx; do printf '%s ' "$name"; git -C "upstream/$name" rev-parse HEAD; done > upstream/COMMITS.txt
