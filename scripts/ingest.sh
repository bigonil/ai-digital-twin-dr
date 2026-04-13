#!/usr/bin/env bash
# ingest.sh — Ingest sample Terraform + docs into the Digital Twin graph.
set -euo pipefail

BASE="http://localhost:8000"
GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'

call_api() {
    local method="$1" path="$2" body="${3:-}"
    local args=(-s -o /dev/null -w "%{http_code}" -X "$method" "$BASE$path" -H "Content-Type: application/json")
    [[ -n "$body" ]] && args+=(-d "$body")
    local code
    code=$(curl "${args[@]}")
    if [[ "$code" =~ ^2 ]]; then
        echo -e "  ${GREEN}[OK]${NC} $method $path -> HTTP $code"
    else
        echo -e "  ${RED}[FAIL]${NC} $method $path -> HTTP $code"
    fi
}

echo -e "\n${CYAN}==> Ingesting Terraform (Phase 1)${NC}"
call_api POST /api/graph/ingest/terraform '{"directory":"/data/terraform/sample"}'

echo -e "\n${CYAN}==> Ingesting documentation (Phase 3)${NC}"
call_api POST /api/graph/ingest/docs '{"directory":"/data/docs"}'

echo -e "\n${CYAN}==> Graph node count${NC}"
COUNT=$(curl -sf "$BASE/api/graph/nodes" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "unknown")
echo -e "  Total nodes: ${GREEN}$COUNT${NC}"

echo -e "\nDone. Open http://localhost:3000 to explore the graph.\n"
