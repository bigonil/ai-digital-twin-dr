#!/bin/bash
# Demo script for the 4 new features: Compliance, What-If, Chaos, Postmortem
# Run this after docker compose is up and data is ingested

BASE_URL="http://localhost:8001"
DEMO_DELAY=2  # seconds between demo steps

echo "═══════════════════════════════════════════════════════════"
echo "  Digital Twin DR Platform — Features Demo"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper function to print section headers
section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Helper function to print info
info() {
    echo -e "${GREEN}ℹ${NC} $1"
}

# Helper function to print errors
error() {
    echo -e "${RED}✗${NC} $1"
}

# Helper function to print success
success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Check if server is running
check_server() {
    if ! curl -s "$BASE_URL/health" > /dev/null; then
        error "Backend not running at $BASE_URL"
        echo "Start with: docker compose up -d"
        exit 1
    fi
    success "Backend is running"
}

# Get first node from topology
get_first_node() {
    curl -s "$BASE_URL/api/graph/topology" | python3 -c "import sys, json; print(json.load(sys.stdin)['nodes'][0]['id'])"
}

section "1. COMPLIANCE AUDIT"

info "Running compliance audit on all nodes..."
sleep $DEMO_DELAY

COMPLIANCE=$(curl -s -X POST "$BASE_URL/api/compliance/run" -H "Content-Type: application/json")
PASS_COUNT=$(echo $COMPLIANCE | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('pass_count', 0))")
FAIL_COUNT=$(echo $COMPLIANCE | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('fail_count', 0))")
WARN_COUNT=$(echo $COMPLIANCE | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('warning_count', 0))")

success "Compliance audit completed"
echo "  📊 Results:"
echo "     ✓ Pass: $PASS_COUNT nodes"
echo "     ⚠ Warning: $WARN_COUNT nodes"
echo "     ✗ Fail: $FAIL_COUNT nodes"
echo ""
info "Retrieving cached report..."
sleep $DEMO_DELAY

REPORT=$(curl -s "$BASE_URL/api/compliance/report")
GENERATED_AT=$(echo $REPORT | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('generated_at', 'N/A')[:10])")
success "Report cached at: $GENERATED_AT"

echo ""
info "Exporting as JSON..."
curl -s "$BASE_URL/api/compliance/export" > /tmp/compliance-report.json
success "Exported to: /tmp/compliance-report.json"

section "2. WHAT-IF ANALYSIS"

ORIGIN_NODE=$(get_first_node)
info "Simulating adding a virtual replica database..."
sleep $DEMO_DELAY

WHATIF_PAYLOAD=$(cat <<EOF
{
  "origin_node_id": "$ORIGIN_NODE",
  "depth": 3,
  "virtual_nodes": [
    {
      "id": "virtual-replica-db",
      "name": "Replica Database",
      "type": "database",
      "rto_minutes": 30,
      "is_redundant": true
    }
  ],
  "virtual_edges": [
    {
      "source": "virtual-replica-db",
      "target": "$ORIGIN_NODE",
      "type": "DEPENDS_ON"
    }
  ]
}
EOF
)

WHATIF=$(curl -s -X POST "$BASE_URL/api/whatif/simulate" \
  -H "Content-Type: application/json" \
  -d "$WHATIF_PAYLOAD")

BLAST_RADIUS_DELTA=$(echo $WHATIF | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('blast_radius_delta', 0))")
RTO_DELTA=$(echo $WHATIF | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('rto_delta_minutes', 0))")

success "What-If simulation completed"
echo "  📊 Results:"
echo "     Blast Radius Change: $BLAST_RADIUS_DELTA nodes"
echo "     RTO Change: ${RTO_DELTA}m"
echo "     Virtual Nodes Added: 1"
echo "     Virtual Edges Added: 1"

section "3. CHAOS ENGINEERING"

info "Creating chaos experiment (CPU exhaustion)..."
sleep $DEMO_DELAY

CHAOS_PAYLOAD=$(cat <<EOF
{
  "node_id": "$ORIGIN_NODE",
  "scenario": "cpu_hog",
  "depth": 3,
  "notes": "Testing CPU exhaustion scenario"
}
EOF
)

CHAOS=$(curl -s -X POST "$BASE_URL/api/chaos/experiments" \
  -H "Content-Type: application/json" \
  -d "$CHAOS_PAYLOAD")

EXPERIMENT_ID=$(echo $CHAOS | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('experiment_id', 'N/A'))")
AFFECTED=$(echo $CHAOS | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('simulation', {}).get('total_affected', 0))")

success "Experiment created: $EXPERIMENT_ID"
echo "  📊 Predicted Impact:"
echo "     Affected Nodes: $AFFECTED"

echo ""
info "Recording actual results from lab test..."
sleep $DEMO_DELAY

ACTUALS_PAYLOAD=$(cat <<EOF
{
  "actual_rto_minutes": 25,
  "actual_blast_radius": ["$ORIGIN_NODE"],
  "notes": "CPU hit 85%, failover triggered early"
}
EOF
)

RESULT=$(curl -s -X POST "$BASE_URL/api/chaos/experiments/$EXPERIMENT_ID/actuals" \
  -H "Content-Type: application/json" \
  -d "$ACTUALS_PAYLOAD")

RESILIENCE=$(echo $RESULT | python3 -c "import sys, json; d=json.load(sys.stdin); r=d.get('resilience_score', 0); print(f'{r*100:.0f}%')")

success "Actual results recorded"
echo "  📊 Resilience Score: $RESILIENCE"

section "4. POSTMORTEM ANALYSIS"

info "Analyzing a real incident..."
sleep $DEMO_DELAY

INCIDENT_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
POSTMORTEM_PAYLOAD=$(cat <<EOF
{
  "title": "Database Primary Failover — Demo Incident",
  "occurred_at": "$INCIDENT_DATE",
  "actual_origin_node_id": "$ORIGIN_NODE",
  "actually_failed_node_ids": ["$ORIGIN_NODE"],
  "actual_rto_minutes": 30,
  "actual_rpo_minutes": 5,
  "reference_simulation_node_id": "$ORIGIN_NODE",
  "reference_simulation_depth": 3
}
EOF
)

POSTMORTEM=$(curl -s -X POST "$BASE_URL/api/postmortem/reports" \
  -H "Content-Type: application/json" \
  -d "$POSTMORTEM_PAYLOAD")

REPORT_ID=$(echo $POSTMORTEM | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('report_id', 'N/A'))")
ACCURACY=$(echo $POSTMORTEM | python3 -c "import sys, json; d=json.load(sys.stdin); a=d.get('prediction_accuracy', {}).get('accuracy_score', 0); print(f'{a*100:.1f}%')")
PRECISION=$(echo $POSTMORTEM | python3 -c "import sys, json; d=json.load(sys.stdin); p=d.get('prediction_accuracy', {}).get('precision', 0); print(f'{p*100:.0f}%')")
RECALL=$(echo $POSTMORTEM | python3 -c "import sys, json; d=json.load(sys.stdin); r=d.get('prediction_accuracy', {}).get('recall', 0); print(f'{r*100:.0f}%')")

success "Postmortem report created: $REPORT_ID"
echo "  📊 Prediction Accuracy:"
echo "     Overall: $ACCURACY"
echo "     Precision: $PRECISION"
echo "     Recall: $RECALL"

section "SUMMARY"

echo -e "${GREEN}All 4 features demonstrated successfully!${NC}"
echo ""
echo "📖 See the features guide for detailed workflows:"
echo "   file:///docs/FEATURES.md"
echo ""
echo "🌐 Visit the dashboard:"
echo "   http://localhost:3001"
echo ""
echo "📚 API Documentation:"
echo "   http://localhost:8001/docs"
echo ""
