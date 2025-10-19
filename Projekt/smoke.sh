#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:5000}"

echo "-> Checking session (should be 401)"
curl -s -o /dev/null -w "%{http_code}\n" "$BASE_URL/api/internal/check_session"

echo "-> Trying login (adjust credentials in payload)"
LOGIN_RESP=$(curl -s -i -c cookies.txt -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin"}' \
  "$BASE_URL/api/internal/login")
echo "$LOGIN_RESP"

echo "-> Fetching sklad categories (requires role)"
curl -s -b cookies.txt "$BASE_URL/api/kancelaria/raw/getCategories" | jq .

echo "Done."
