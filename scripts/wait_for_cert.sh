#!/usr/bin/env bash
# Wait until www.fct-cf.ca serves a certificate that verifies, checking every 30 minutes.
# TLS handshake only (no HTTP request). Gives up after 14 days. Exit 0 = valid, 1 = gave up.
host=www.fct-cf.ca
for i in $(seq 1 672); do
  ts=$(date -u +%FT%TZ)
  end=$(echo | timeout 20 openssl s_client -connect $host:443 -servername $host 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null)
  if echo | timeout 20 openssl s_client -connect $host:443 -servername $host 2>/dev/null | openssl x509 -noout -checkend 0 >/dev/null 2>&1 \
     && (cd /c/projects/bench-time && uv run --no-sync python -c "
import socket, ssl
ctx = ssl.create_default_context()
with socket.create_connection(('$host', 443), timeout=20) as s, ctx.wrap_socket(s, server_hostname='$host'):
    pass
") >/dev/null 2>&1; then
    echo "$ts check $i: VALID ($end)"; exit 0
  fi
  echo "$ts check $i: still invalid ($end)"
  sleep 1800
done
echo "gave up after 14 days"; exit 1
