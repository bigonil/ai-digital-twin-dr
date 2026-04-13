#Requires -Version 5.1
<#
.SYNOPSIS
    Ingest sample Terraform + docs into the Digital Twin graph.
.DESCRIPTION
    Calls the backend API to trigger parsers. Requires services to be running.
#>

$Base = "http://localhost:8000"

function Invoke-Api($method, $path, $body = $null) {
    $params = @{
        Method          = $method
        Uri             = "$Base$path"
        Headers         = @{ "Content-Type" = "application/json" }
        UseBasicParsing = $true
        TimeoutSec      = 60
    }
    if ($body) { $params.Body = ($body | ConvertTo-Json -Depth 5) }
    try {
        $r = Invoke-WebRequest @params -ErrorAction Stop
        Write-Host "  [OK] $method $path  -> HTTP $($r.StatusCode)" -ForegroundColor Green
        return $r.Content | ConvertFrom-Json
    } catch {
        Write-Host "  [FAIL] $method $path  -> $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`n==> Ingesting Terraform (Phase 1)" -ForegroundColor Cyan
Invoke-Api "POST" "/api/graph/ingest/terraform" @{ directory = "/data/terraform/sample" }

Write-Host "`n==> Ingesting documentation (Phase 3)" -ForegroundColor Cyan
Invoke-Api "POST" "/api/graph/ingest/docs" @{ directory = "/data/docs" }

Write-Host "`n==> Graph node summary" -ForegroundColor Cyan
$nodes = Invoke-Api "GET" "/api/graph/nodes"
if ($nodes) { Write-Host "  Total nodes: $($nodes.Count)" -ForegroundColor White }

Write-Host "`nDone. Open http://localhost:3000 to explore the graph.`n" -ForegroundColor Green
