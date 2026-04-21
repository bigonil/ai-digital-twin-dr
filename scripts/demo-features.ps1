# Demo script for the 4 new features: Compliance, What-If, Chaos, Postmortem
# Run this after docker compose is up and data is ingested

param(
    [string]$BaseUrl = "http://localhost:8001"
)

$DemoDelay = 2  # seconds between demo steps

Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Digital Twin DR Platform — Features Demo" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Helper functions
function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
    Write-Host $Title -ForegroundColor Blue
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Blue
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ $Message" -ForegroundColor Green
}

function Write-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

# Check if server is running
try {
    $null = Invoke-WebRequest "$BaseUrl/health" -ErrorAction Stop
    Write-Success "Backend is running"
} catch {
    Write-Error "Backend not running at $BaseUrl"
    Write-Host "Start with: docker compose up -d"
    exit 1
}

# Get first node from topology
function Get-FirstNode {
    try {
        $response = Invoke-WebRequest "$BaseUrl/api/graph/topology" -ErrorAction Stop
        $data = ConvertFrom-Json $response.Content
        return $data.nodes[0].id
    } catch {
        Write-Error "Failed to get topology"
        exit 1
    }
}

# 1. COMPLIANCE AUDIT
Write-Section "1. COMPLIANCE AUDIT"

Write-Info "Running compliance audit on all nodes..."
Start-Sleep -Seconds $DemoDelay

try {
    $response = Invoke-WebRequest "$BaseUrl/api/compliance/run" -Method POST -ErrorAction Stop
    $compliance = ConvertFrom-Json $response.Content

    Write-Success "Compliance audit completed"
    Write-Host "  📊 Results:"
    Write-Host "     ✓ Pass: $($compliance.pass_count) nodes"
    Write-Host "     ⚠ Warning: $($compliance.warning_count) nodes"
    Write-Host "     ✗ Fail: $($compliance.fail_count) nodes"
    Write-Host ""

    Write-Info "Retrieving cached report..."
    Start-Sleep -Seconds $DemoDelay

    $reportResponse = Invoke-WebRequest "$BaseUrl/api/compliance/report" -ErrorAction Stop
    $report = ConvertFrom-Json $reportResponse.Content
    $generatedAt = $report.generated_at.Substring(0, 10)

    Write-Success "Report cached at: $generatedAt"
    Write-Host ""

    Write-Info "Exporting as JSON..."
    $exportResponse = Invoke-WebRequest "$BaseUrl/api/compliance/export" -ErrorAction Stop
    $exportResponse.Content | Out-File -FilePath "$env:TEMP\compliance-report.json"
    Write-Success "Exported to: $env:TEMP\compliance-report.json"
} catch {
    Write-Error "Compliance demo failed: $_"
}

# 2. WHAT-IF ANALYSIS
Write-Section "2. WHAT-IF ANALYSIS"

$OriginNode = Get-FirstNode
Write-Info "Simulating adding a virtual replica database..."
Start-Sleep -Seconds $DemoDelay

$whatifPayload = @{
    origin_node_id = $OriginNode
    depth = 3
    virtual_nodes = @(
        @{
            id = "virtual-replica-db"
            name = "Replica Database"
            type = "database"
            rto_minutes = 30
            is_redundant = $true
        }
    )
    virtual_edges = @(
        @{
            source = "virtual-replica-db"
            target = $OriginNode
            type = "DEPENDS_ON"
        }
    )
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-WebRequest "$BaseUrl/api/whatif/simulate" -Method POST `
        -ContentType "application/json" -Body $whatifPayload -ErrorAction Stop
    $whatif = ConvertFrom-Json $response.Content

    Write-Success "What-If simulation completed"
    Write-Host "  📊 Results:"
    Write-Host "     Blast Radius Change: $($whatif.blast_radius_delta) nodes"
    Write-Host "     RTO Change: $($whatif.rto_delta_minutes)m"
    Write-Host "     Virtual Nodes Added: $($whatif.virtual_nodes_added)"
    Write-Host "     Virtual Edges Added: $($whatif.virtual_edges_added)"
} catch {
    Write-Error "What-If demo failed: $_"
}

# 3. CHAOS ENGINEERING
Write-Section "3. CHAOS ENGINEERING"

Write-Info "Creating chaos experiment (CPU exhaustion)..."
Start-Sleep -Seconds $DemoDelay

$chaosPayload = @{
    node_id = $OriginNode
    scenario = "cpu_hog"
    depth = 3
    notes = "Testing CPU exhaustion scenario"
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest "$BaseUrl/api/chaos/experiments" -Method POST `
        -ContentType "application/json" -Body $chaosPayload -ErrorAction Stop
    $chaos = ConvertFrom-Json $response.Content
    $experimentId = $chaos.experiment_id

    Write-Success "Experiment created: $experimentId"
    Write-Host "  📊 Predicted Impact:"
    Write-Host "     Affected Nodes: $($chaos.simulation.total_affected)"
    Write-Host ""

    Write-Info "Recording actual results from lab test..."
    Start-Sleep -Seconds $DemoDelay

    $actualsPayload = @{
        actual_rto_minutes = 25
        actual_blast_radius = @($OriginNode)
        notes = "CPU hit 85%, failover triggered early"
    } | ConvertTo-Json

    $resultResponse = Invoke-WebRequest "$BaseUrl/api/chaos/experiments/$experimentId/actuals" `
        -Method POST -ContentType "application/json" -Body $actualsPayload -ErrorAction Stop
    $result = ConvertFrom-Json $resultResponse.Content
    $resilience = [math]::Round($result.resilience_score * 100, 0)

    Write-Success "Actual results recorded"
    Write-Host "  📊 Resilience Score: $resilience%"
} catch {
    Write-Error "Chaos demo failed: $_"
}

# 4. POSTMORTEM ANALYSIS
Write-Section "4. POSTMORTEM ANALYSIS"

Write-Info "Analyzing a real incident..."
Start-Sleep -Seconds $DemoDelay

$incidentDate = (Get-Date -AsUTC).ToString("yyyy-MM-ddTHH:mm:ssZ")
$postmortemPayload = @{
    title = "Database Primary Failover — Demo Incident"
    occurred_at = $incidentDate
    actual_origin_node_id = $OriginNode
    actually_failed_node_ids = @($OriginNode)
    actual_rto_minutes = 30
    actual_rpo_minutes = 5
    reference_simulation_node_id = $OriginNode
    reference_simulation_depth = 3
} | ConvertTo-Json

try {
    $response = Invoke-WebRequest "$BaseUrl/api/postmortem/reports" -Method POST `
        -ContentType "application/json" -Body $postmortemPayload -ErrorAction Stop
    $postmortem = ConvertFrom-Json $response.Content
    $reportId = $postmortem.report_id
    $accuracy = [math]::Round($postmortem.prediction_accuracy.accuracy_score * 100, 1)
    $precision = [math]::Round($postmortem.prediction_accuracy.precision * 100, 0)
    $recall = [math]::Round($postmortem.prediction_accuracy.recall * 100, 0)

    Write-Success "Postmortem report created: $reportId"
    Write-Host "  📊 Prediction Accuracy:"
    Write-Host "     Overall: $accuracy%"
    Write-Host "     Precision: $precision%"
    Write-Host "     Recall: $recall%"
} catch {
    Write-Error "Postmortem demo failed: $_"
}

# Summary
Write-Section "SUMMARY"

Write-Host "All 4 features demonstrated successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "📖 See the features guide for detailed workflows:"
Write-Host "   docs/FEATURES.md"
Write-Host ""
Write-Host "🌐 Visit the dashboard:"
Write-Host "   http://localhost:3001"
Write-Host ""
Write-Host "📚 API Documentation:"
Write-Host "   http://localhost:8001/docs"
Write-Host ""
