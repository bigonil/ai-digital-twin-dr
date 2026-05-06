#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Seed RTO/RPO values from neo4j_schema.py into Neo4j database.

.DESCRIPTION
    Updates all infrastructure nodes in Neo4j with their default RTO and RPO values
    based on resource type mappings defined in neo4j_schema.py

.EXAMPLE
    .\seed-rto-rpo.ps1
#>

param(
    [string]$ContainerName = "dt-backend",
    [string]$Neo4jUri = "neo4j://localhost:7687",
    [string]$Neo4jUser = "neo4j",
    [string]$Neo4jPassword = "password"
)

Write-Host "🌱 Seeding RTO/RPO values into Neo4j..." -ForegroundColor Cyan

# Python script to seed RTO/RPO values
$pythonScript = @'
import asyncio
from db.neo4j_client import neo4j_client
from parsers.infra import RTO_RPO_MAP

async def seed_rto_rpo():
    """Seed RTO/RPO values into Neo4j from RTO_RPO_MAP"""

    try:
        await neo4j_client.connect()

        updated_count = 0

        async with neo4j_client._driver.session() as session:
            for resource_type, (rto, rpo) in RTO_RPO_MAP.items():
                # Update all nodes of this resource type
                result = await session.run(
                    """
                    MATCH (n:InfraNode {type: $type})
                    SET n.rto_minutes = $rto, n.rpo_minutes = $rpo
                    RETURN count(n) as updated
                    """,
                    {"type": resource_type, "rto": rto, "rpo": rpo}
                )

                # Count updated nodes
                record = await result.single()
                if record:
                    count = record.get("updated", 0)
                    updated_count += count
                    if count > 0:
                        print(f"  ✓ {resource_type}: {count} nodes updated (RTO={rto}min, RPO={rpo}min)")

        print(f"\n✅ Seeding complete! Updated {updated_count} total nodes")

    except Exception as e:
        print(f"❌ Error during seeding: {str(e)}")
        raise
    finally:
        await neo4j_client.close()

asyncio.run(seed_rto_rpo())
'@

# Execute Python script in the backend container
try {
    Write-Host "  Running seeding script in container '$ContainerName'..." -ForegroundColor Gray

    # Check if container is running
    $containerStatus = docker ps -q -f name=$ContainerName
    if (-not $containerStatus) {
        Write-Host "❌ Container '$ContainerName' is not running" -ForegroundColor Red
        Write-Host "   Start it with: docker compose up -d" -ForegroundColor Yellow
        exit 1
    }

    # Execute the Python script
    docker exec -w /app $ContainerName python -c $pythonScript

    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✨ RTO/RPO seeding successful!" -ForegroundColor Green
    } else {
        Write-Host "`n❌ Seeding failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit 1
    }

} catch {
    Write-Host "❌ Error executing seeding script: $_" -ForegroundColor Red
    exit 1
}
