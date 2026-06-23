#!/usr/bin/env bash
# Build a self-contained, relocatable Robin backend bundle for the current
# platform/arch, so the desktop app can run the Python agent with ZERO developer
# tooling on the user's machine --- no git, no compiler, no Command Line Tools, no
# pip-at-runtime. The result is `apps/desktop/backend.tar.gz`, shipped inside the
# signed app and extracted to ~/.robin/hermes-agent on first launch.
#
# Layout produced (extracted to ~/.robin/hermes-agent at runtime):
#   hermes-agent/            -> full Robin source (the agent core + plugins)
#   hermes-agent/venv/       -> a relocatable standalone CPython with ALL deps
#                               installed into its site-packages. The desktop
#                               runs `venv/bin/python -m robin.main dashboard`.
#
# Requires: uv (installed by the workflow). Run from the repo root.
set -euo pipefail

PYVER="${ROBIN_PY_VERSION:-3.11}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_ROOT="$REPO_ROOT/.backend-bundle"
AGENT_DIR="$BUNDLE_ROOT/hermes-agent"
VENV_DIR="$AGENT_DIR/venv"
OUT="$REPO_ROOT/apps/desktop/backend.tar.gz"

echo "[bundle] repo=$REPO_ROOT python=$PYVER"
rm -rf "$BUNDLE_ROOT"
mkdir -p "$AGENT_DIR"

# 1) Copy the Robin source the backend needs (exclude the desktop/web shells,
#    VCS, node, caches, tests, and big non-runtime assets). The Python agent
#    imports from this tree at runtime (cwd = hermes-agent).
echo "[bundle] copying source via git archive..."
# Write the archive to a FILE first (no pipe), so a failure in git vs tar is
# unambiguous and SIGPIPE/pipefail can't mask it. git archive exports exactly
# the tracked files at HEAD --- no caches/symlinks/node_modules --- identically on
# macOS and Linux. Then prune the non-backend trees.
SRC_TAR="$REPO_ROOT/_src-archive.tar"
rm -f "$SRC_TAR"
git config --global --add safe.directory "$REPO_ROOT" 2>/dev/null || true
git -C "$REPO_ROOT" archive --format=tar HEAD > "$SRC_TAR"
echo "[bundle] archive bytes: $(wc -c < "$SRC_TAR")"
tar -xf "$SRC_TAR" -C "$AGENT_DIR"
rm -f "$SRC_TAR"
( cd "$AGENT_DIR" && rm -rf apps web ui-tui website site tests docs .github \
    download paper infographic target release dist build )
test -f "$AGENT_DIR/robin/main.py" || { echo "[bundle] ERROR: source copy produced no backend"; exit 1; }
echo "[bundle] source ready"

# 2) Get a relocatable standalone CPython (python-build-standalone via uv) and
#    copy the WHOLE interpreter install into venv/ so it is self-contained
#    (its own stdlib + site-packages --- no symlink to a system python).
echo "[bundle] provisioning standalone CPython $PYVER..."
uv python install "$PYVER"
PYBIN="$(uv python find "$PYVER")"                 # .../install/bin/python3
PYHOME="$(cd "$(dirname "$PYBIN")/.." && pwd)"      # the relocatable install root
echo "[bundle] standalone python at $PYHOME"
mkdir -p "$VENV_DIR"
# copy contents of the standalone install into venv/ (bin/, lib/, include/...)
cp -R "$PYHOME"/. "$VENV_DIR"/

VENV_PY="$VENV_DIR/bin/python3"
[ -x "$VENV_PY" ] || VENV_PY="$VENV_DIR/bin/python"
# The desktop spawns venv/bin/python (no '3') --- guarantee it exists.
[ -e "$VENV_DIR/bin/python" ] || ln -sf python3 "$VENV_DIR/bin/python"
echo "[bundle] venv python: $VENV_PY"
"$VENV_PY" --version

# 3) Install the project + ALL its dependencies into the bundled interpreter's
#    site-packages. Prefer wheels; CI has a compiler for any source builds, and
#    the resulting binaries run on the user's machine (no compiler needed there).
echo "[bundle] installing dependencies..."
# The copied standalone CPython carries a PEP 668 "externally managed" marker
# (it was uv-managed). This is now OUR private interpreter to install into, so
# drop the marker, then pip install the project + all pinned deps into the
# bundled site-packages. -m robin.main also resolves modules from cwd.
rm -f "$VENV_DIR"/lib/python*/EXTERNALLY-MANAGED 2>/dev/null || true
# Install the [all] extra to match the normal install (uv sync --extra all):
# it bundles every always-needed extra (cli, pty, mcp, vision, web, cron).
# Optional backends (other providers, search, TTS, messaging) stay lazy-installed
# on first use via tools/lazy_deps.py, exactly as in a normal install -- so this
# does NOT reduce functionality.
"$VENV_PY" -m pip install --break-system-packages "${AGENT_DIR}[all]"

# 4) Smoke-test: the interpreter must import the agent entry module offline.
echo "[bundle] smoke test..."
( cd "$AGENT_DIR" && "$VENV_PY" -c "import robin.main; print('[bundle] robin import OK')" )

# 5) Mark this as a completed install so the desktop trusts it (the desktop also
#    writes its own marker, but seed one for belt-and-braces).
cat > "$AGENT_DIR/.hermes-bootstrap-complete" <<EOF
{"schemaVersion":1,"source":"bundled","completedAt":"build"}
EOF

# 6) Tarball it (deterministic-ish). This is shipped as extraResources.
echo "[bundle] packing $OUT..."
rm -f "$OUT"
tar -czf "$OUT" -C "$BUNDLE_ROOT" hermes-agent
ls -lh "$OUT"
echo "[bundle] done."
