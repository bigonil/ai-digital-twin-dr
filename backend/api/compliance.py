"""Compliance & Testing API — RTO/RPO audit, compliance reports."""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from models.features import ComplianceReport, NodeComplianceResult, ComplianceStatus
from settings import Settings

router = APIRouter()


async def _run_compliance_audit(request: Request) -> ComplianceReport:
    """
    Run compliance audit on all nodes.

    For each node, simulate disaster (depth=3), extract worst_case_rto/rpo,
    compare against thresholds from settings, assign status.
    """
    settings = Settings()

    rto_threshold = settings.dr_rto_threshold_minutes  # 60
    rpo_threshold = settings.dr_rpo_threshold_minutes  # 15

    # Fetch all infrastructure nodes (exclude Document nodes)
    all_nodes = await request.app.state.neo4j.run(
        "MATCH (n:InfraNode) RETURN n.id AS id, n.name AS name, n.type AS type, "
        "n.rto_minutes AS rto_minutes, n.rpo_minutes AS rpo_minutes"
    )

    results = []
    pass_count = fail_count = warning_count = skipped_count = 0

    for node in all_nodes:
        node_id = node["id"]
        node_name = node.get("name", node_id)
        node_type = node.get("type", "unknown")
        rto_minutes = node.get("rto_minutes")
        rpo_minutes = node.get("rpo_minutes")

        # Run simulation to get worst-case times
        affected = await request.app.state.neo4j.simulate_disaster(node_id, depth=3)

        worst_case_rto = None
        worst_case_rpo = None
        blast_radius_size = len(affected)

        if affected:
            rtos = [a.get("rto_minutes") for a in affected if a.get("rto_minutes")]
            rpos = [a.get("rpo_minutes") for a in affected if a.get("rpo_minutes")]
            worst_case_rto = max(rtos) if rtos else None
            worst_case_rpo = max(rpos) if rpos else None

        # Determine RTO status
        if rto_minutes is None:
            rto_status = ComplianceStatus.skipped
        elif worst_case_rto and worst_case_rto > rto_threshold:
            rto_status = ComplianceStatus.fail
        elif worst_case_rto and worst_case_rto > rto_threshold * 0.8:
            rto_status = ComplianceStatus.warning
        else:
            rto_status = ComplianceStatus.pass_

        # Determine RPO status
        if rpo_minutes is None:
            rpo_status = ComplianceStatus.skipped
        elif worst_case_rpo and worst_case_rpo > rpo_threshold:
            rpo_status = ComplianceStatus.fail
        elif worst_case_rpo and worst_case_rpo > rpo_threshold * 0.8:
            rpo_status = ComplianceStatus.warning
        else:
            rpo_status = ComplianceStatus.pass_

        # Count results
        if rto_status == ComplianceStatus.pass_ and rpo_status == ComplianceStatus.pass_:
            pass_count += 1
        elif rto_status == ComplianceStatus.fail or rpo_status == ComplianceStatus.fail:
            fail_count += 1
        elif rto_status == ComplianceStatus.warning or rpo_status == ComplianceStatus.warning:
            warning_count += 1
        else:
            skipped_count += 1

        result = NodeComplianceResult(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            rto_minutes=rto_minutes,
            rpo_minutes=rpo_minutes,
            rto_threshold=rto_threshold,
            rpo_threshold=rpo_threshold,
            rto_status=rto_status,
            rpo_status=rpo_status,
            blast_radius_size=blast_radius_size,
            worst_case_rto=worst_case_rto,
            worst_case_rpo=worst_case_rpo,
        )
        results.append(result)

    report = ComplianceReport(
        generated_at=datetime.utcnow().isoformat(),
        rto_threshold_minutes=rto_threshold,
        rpo_threshold_minutes=rpo_threshold,
        total_nodes=len(all_nodes),
        pass_count=pass_count,
        fail_count=fail_count,
        warning_count=warning_count,
        skipped_count=skipped_count,
        results=results,
    )

    return report


@router.post("/run", response_model=ComplianceReport)
async def run_compliance_audit(request: Request):
    """
    Run full compliance audit and cache result.
    """
    report = await _run_compliance_audit(request)
    request.app.state.last_compliance_report = report
    return report


@router.get("/report", response_model=ComplianceReport)
async def get_compliance_report(request: Request):
    """
    Return cached compliance report or 404.
    """
    if not request.app.state.last_compliance_report:
        raise HTTPException(status_code=404, detail="No compliance report generated yet. Run /api/compliance/run first.")
    return request.app.state.last_compliance_report


@router.get("/export")
async def export_compliance_report(request: Request):
    """
    Export cached compliance report as JSON download.
    """
    if not request.app.state.last_compliance_report:
        raise HTTPException(status_code=404, detail="No compliance report generated yet.")

    report = request.app.state.last_compliance_report
    return {
        "filename": f"compliance_report_{report.generated_at[:10]}.json",
        "data": report.model_dump(),
    }
