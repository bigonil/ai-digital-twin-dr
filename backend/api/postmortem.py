"""Incident Postmortem API — prediction accuracy analysis."""
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, status
import structlog
from api.dependencies import limiter
from models.features import PostmortemIncidentInput, PostmortemReport

log = structlog.get_logger()
router = APIRouter()


def _generate_recommendations(false_negatives: list[str], actual_failed: list[str]) -> list[str]:
    """Generate recommendations based on false negatives."""
    recs = []

    if false_negatives:
        recs.append(f"Add missing dependencies for nodes: {', '.join(false_negatives[:5])}")
        recs.append("Review disaster simulation model assumptions against incident timeline")

    if len(actual_failed) > 5:
        recs.append("Consider reducing simulation depth or prioritizing critical path dependencies")

    if not recs:
        recs.append("Model predictions are accurate. Continue monitoring for validation.")

    return recs


@router.post("/reports", response_model=PostmortemReport)
@limiter.limit("60/minute")
async def create_postmortem_report(body: PostmortemIncidentInput, request: Request):
    """
    Create postmortem report by comparing predicted vs actual incident.
    """
    try:
        neo4j = request.app.state.neo4j

        # Get predicted nodes (from reference simulation if provided)
        predicted_nodes = set()

        if body.reference_simulation_node_id:
            predicted_rows = await neo4j.simulate_disaster(
                body.reference_simulation_node_id, body.reference_simulation_depth
            )
            predicted_nodes = {r["id"] for r in predicted_rows}

        # Get actual nodes
        actual_nodes = set(body.actually_failed_node_ids)

        # Compute confusion matrix
        true_positives = list(predicted_nodes & actual_nodes)
        false_positives = list(predicted_nodes - actual_nodes)
        false_negatives = list(actual_nodes - predicted_nodes)

        # Compute precision and recall
        precision = (
            len(true_positives) / (len(true_positives) + len(false_positives))
            if (len(true_positives) + len(false_positives)) > 0
            else 0.0
        )

        recall = (
            len(true_positives) / (len(true_positives) + len(false_negatives))
            if (len(true_positives) + len(false_negatives)) > 0
            else 0.0
        )

        # Compute accuracy score (F1-like composite)
        accuracy_score = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        # Compute RTO delta
        rto_delta = body.actual_rto_minutes - (body.reference_simulation_node_id and 60 or 0)  # TODO: get predicted RTO
        if body.reference_simulation_node_id:
            # In real scenario, would fetch predicted RTO from simulation result
            rto_delta = body.actual_rto_minutes - 60  # Placeholder

        # Generate recommendations
        recommendations = _generate_recommendations(false_negatives, body.actually_failed_node_ids)

        # Create report
        report_id = str(uuid4())
        report = PostmortemReport(
            report_id=report_id,
            title=body.title,
            occurred_at=body.occurred_at,
            origin_node_id=body.actual_origin_node_id,
            prediction_accuracy={
                "predicted_node_ids": list(predicted_nodes),
                "actual_node_ids": body.actually_failed_node_ids,
                "true_positives": true_positives,
                "false_positives": false_positives,
                "false_negatives": false_negatives,
                "precision": precision,
                "recall": recall,
                "rto_delta_minutes": rto_delta,
                "accuracy_score": accuracy_score,
            },
            simulation_used=None,  # Could store reference simulation here
            recommendations=recommendations,
            created_at=datetime.utcnow().isoformat(),
        )

        # Store in app state
        request.app.state.postmortem_reports[report_id] = report
        log.info("postmortem_report_created", report_id=report_id, title=body.title)

        return report
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("postmortem_create_error", error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create postmortem report"
        )


@router.get("/reports")
async def list_postmortem_reports(request: Request):
    """
    List all postmortem reports, most recent first.
    """
    try:
        reports = request.app.state.postmortem_reports.values()
        sorted_reports = sorted(reports, key=lambda r: r.created_at, reverse=True)
        log.info("postmortem_list_success", count=len(sorted_reports))
        return [r.model_dump() for r in sorted_reports]
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("postmortem_list_error", error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list postmortem reports"
        )


@router.get("/reports/{report_id}", response_model=PostmortemReport)
async def get_postmortem_report(report_id: str, request: Request):
    """
    Get a specific postmortem report or 404.
    """
    try:
        report = request.app.state.postmortem_reports.get(report_id)
        if not report:
            log.warning("postmortem_report_not_found", report_id=report_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report {report_id!r} not found"
            )
        log.info("postmortem_report_retrieved", report_id=report_id)
        return report
    except HTTPException:
        raise
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        log.error("postmortem_get_error", report_id=report_id, error=str(exc), request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve postmortem report"
        )
