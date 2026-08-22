#!/bin/sh
# Runs from /docker-entrypoint.d/ at nginx container start: writes the
# runtime config the SPA reads before booting. Empty API_URL means
# same-origin requests through this image's nginx proxy.
set -e
cat > /usr/share/nginx/html/config.js <<EOF
window.__MEDISENSE_CONFIG__ = { API_URL: "${API_URL:-}" };
EOF
echo "runtime-config: API_URL='${API_URL:-}'"
