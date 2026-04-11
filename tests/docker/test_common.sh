#!/usr/bin/env bash
# Shared end-to-end test logic for portname check on non-Debian distros.
# Sourced by test_arch.sh and test_fedora.sh after deps are installed.
#
# Requires:
#   - portname installed and on PATH
#   - PORTNAME_SKIP_RESTART=1 (already exported by the calling script)
#   - Running as root (standard inside Docker containers)

set -euo pipefail

PATHS_DIR="/usr/share/alsa-card-profile/mixer/paths"
CUSTOM_NAME="Portname Docker Test"
PASS=0
FAIL=0

pass() { echo "  PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $*"; FAIL=$((FAIL + 1)); }

# ── Find a usable route ────────────────────────────────────────────────────────

echo ""
echo "=== Locating a test route ==="

ROUTE=""
for f in "$PATHS_DIR"/analog-output-*.conf "$PATHS_DIR"/analog-input-*.conf; do
    [ -f "$f" ] || continue
    if grep -qE "^\s*(description|description-key)\s*=" "$f" 2>/dev/null; then
        ROUTE=$(basename "$f" .conf)
        break
    fi
done

if [ -z "$ROUTE" ]; then
    echo "ERROR: No suitable .conf file found in $PATHS_DIR"
    echo "       Make sure alsa-card-profiles is installed."
    exit 1
fi

CONF="$PATHS_DIR/$ROUTE.conf"
ORIG="$CONF.orig"
echo "  Using route: $ROUTE"
echo "  Conf file:   $CONF"

# ── Clean up any leftover state from a previous run ───────────────────────────

if [ -f "$ORIG" ]; then
    cp "$ORIG" "$CONF"
    rm -f "$ORIG"
fi
rm -f /var/lib/portname/state.json

# ── Step 1: rename ─────────────────────────────────────────────────────────────

echo ""
echo "=== Step 1: rename ==="
portname rename "$ROUTE" "$CUSTOM_NAME"

if grep -q "description = $CUSTOM_NAME" "$CONF"; then
    pass "'$CONF' contains 'description = $CUSTOM_NAME'"
else
    fail "rename did not write custom name to '$CONF'"
fi

if [ -f "$ORIG" ]; then
    pass "backup '$ORIG' was created"
else
    fail "backup '$ORIG' is missing after rename"
fi

if [ -f /var/lib/portname/state.json ]; then
    pass "state.json written"
else
    fail "state.json not created"
fi

# ── Step 2: simulate a package-manager upgrade clobbering the file ────────────

echo ""
echo "=== Step 2: simulate upgrade clobber ==="
cp "$ORIG" "$CONF"

if ! grep -q "description = $CUSTOM_NAME" "$CONF"; then
    pass "'$CONF' now has original content (clobber simulated)"
else
    fail "clobber simulation did not overwrite the custom name"
fi

# ── Step 3: portname check re-applies the rename ──────────────────────────────

echo ""
echo "=== Step 3: portname check ==="
OUTPUT=$(portname check)
echo "  Output: $OUTPUT"

if grep -q "description = $CUSTOM_NAME" "$CONF"; then
    pass "check re-applied '$CUSTOM_NAME' to '$CONF'"
else
    fail "check did not re-apply custom name"
fi

if echo "$OUTPUT" | grep -qi "Re-applied"; then
    pass "check output reported a re-applied rename"
else
    fail "check output did not mention re-applied rename (got: $OUTPUT)"
fi

# ── Step 4: revert and verify ─────────────────────────────────────────────────

echo ""
echo "=== Step 4: revert ==="
portname revert --all

if [ -f "$CONF" ]; then
    pass "'$CONF' exists after revert"
else
    fail "'$CONF' missing after revert"
fi

if [ ! -f "$ORIG" ]; then
    pass "backup '$ORIG' removed after revert"
else
    fail "backup '$ORIG' still present after revert"
fi

if ! grep -q "description = $CUSTOM_NAME" "$CONF"; then
    pass "custom name no longer present in '$CONF'"
else
    fail "custom name still present in '$CONF' after revert"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
