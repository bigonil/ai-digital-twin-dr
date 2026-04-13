#!/usr/bin/env bash
# start.sh — Launch the AI Digital Twin DR platform from WSL2 / Linux
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
header() { echo -e "\n${CYAN}==> $*${NC}"; }
ok()     { echo -e "    ${GREEN}[OK]${NC} $*"; }
warn()   { echo -e "    ${YELLOW}[WARN]${NC} $*"; }
fail()   { echo -e "    ${RED}[FAIL]${NC} $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# ── 1. WSL2 /mnt/ performance warning ────────────────────────────────────────
header "Checking filesystem"
if [[ "$PROJECT_ROOT" == /mnt/* ]]; then
    warn "Project is on a Windows-mounted drive ($PROJECT_ROOT)."
    warn "Bind-mounts from /mnt/* are significantly slower than the native Linux FS."
    warn "Recommended: clone the repo inside WSL2 home directory"
    warn "  git clone <repo> ~/ai-digital-twin-dr && cd ~/ai-digital-twin-dr"
    echo ""
    read -rp "Continue anyway? [y/N]: " confirm
    [[ "${confirm,,}" == "y" ]] || exit 0
fi
ok "Filesystem OK"

# ── 2. check Docker ───────────────────────────────────────────────────────────
header "Checking Docker"
command -v docker &>/dev/null || fail "docker not found. Install Docker Desktop with WSL integration."
docker info &>/dev/null || fail "Docker daemon not running. Start Docker Desktop or: sudo service docker start"
ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

# ── 3. pick docker compose command ───────────────────────────────────────────
if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    ok "docker compose $(docker compose version --short)"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
    warn "Using legacy docker-compose v1 — consider upgrading to Docker Compose v2"
else
    fail "Neither 'docker compose' nor 'docker-compose' found."
fi

# ── 4. check .env ─────────────────────────────────────────────────────────────
header "Checking configuration"
[[ -f "$PROJECT_ROOT/.env" ]] || fail ".env not found. Run: cp .env.example .env"
ok ".env found"

# ── 5. check Ollama ───────────────────────────────────────────────────────────
header "Checking Ollama (host)"
OLLAMA_REACHABLE=false
if curl -sf --max-time 3 "http://localhost:11434" &>/dev/null; then
    ok "Ollama reachable at http://localhost:11434"
    OLLAMA_REACHABLE=true
else
    # WSL2: try Windows host IP from resolv.conf
    WIN_HOST=$(grep nameserver /etc/resolv.conf 2>/dev/null | awk '{print $2}' | head -1 || true)
    if [[ -n "$WIN_HOST" ]] && curl -sf --max-time 3 "http://$WIN_HOST:11434" &>/dev/null; then
        ok "Ollama reachable at http://$WIN_HOST:11434 (Windows host)"
        OLLAMA_REACHABLE=true
    fi
fi
if [[ "$OLLAMA_REACHABLE" == "false" ]]; then
    warn "Ollama not reachable. Embedding/LLM features will fail."
    warn "  ollama serve  &&  ollama pull nomic-embed-text  &&  ollama pull llama3"
fi

# ── 6. build and start ────────────────────────────────────────────────────────
header "Starting services (first run downloads images — may take several minutes)"
$COMPOSE_CMD up -d --build

# ── 7. wait for backend health ────────────────────────────────────────────────
header "Waiting for backend to be healthy"
MAX_WAIT=120; WAITED=0
until curl -sf --max-time 3 "http://localhost:8000/health" &>/dev/null; do
    sleep 5; WAITED=$((WAITED + 5))
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        warn "Backend health check timed out. Run: docker compose logs backend"
        break
    fi
    echo "    ... waiting ($WAITED / ${MAX_WAIT}s)"
done
[[ $WAITED -lt $MAX_WAIT ]] && ok "Backend is healthy"

# ── 8. print URLs ─────────────────────────────────────────────────────────────
header "Services are up!"
echo ""
echo -e "  Frontend (3D Dashboard) : ${CYAN}http://localhost:3000${NC}"
echo -e "  Backend API (FastAPI)   : ${CYAN}http://localhost:8000${NC}"
echo -e "  API Docs (Swagger)      : ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  Neo4j Browser           : ${CYAN}http://localhost:7474${NC}"
echo -e "  VictoriaMetrics         : ${CYAN}http://localhost:8428${NC}"
echo -e "  Qdrant Dashboard        : ${CYAN}http://localhost:6333/dashboard${NC}"
echo ""
echo -e "  Ingest sample data : bash scripts/ingest.sh"
echo -e "  Stop all services  : docker compose down"
echo ""
