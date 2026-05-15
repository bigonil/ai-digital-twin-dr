"""
Cross-region and cross-AZ latency lookup table.
Used by BFS to add realistic geographic overhead between nodes in different regions/AZs.
"""

# Approximate P50 RTT (ms) between AWS regions
# Symmetric: lookup uses sorted tuple as key
_INTER_REGION_LATENCY_MS: dict[tuple[str, str], int] = {
    ("us-east-1", "us-east-2"): 12,
    ("us-east-1", "us-west-1"): 65,
    ("us-east-1", "us-west-2"): 70,
    ("us-east-1", "eu-west-1"): 80,
    ("us-east-1", "eu-west-2"): 85,
    ("us-east-1", "eu-central-1"): 95,
    ("us-east-1", "ap-southeast-1"): 230,
    ("us-east-1", "ap-northeast-1"): 175,
    ("us-east-1", "ap-south-1"): 185,
    ("us-east-1", "sa-east-1"): 120,
    ("us-west-2", "eu-west-1"): 135,
    ("us-west-2", "ap-southeast-1"): 165,
    ("us-west-2", "ap-northeast-1"): 130,
    ("eu-west-1", "eu-central-1"): 25,
    ("eu-west-1", "ap-southeast-1"): 175,
    ("eu-west-1", "ap-northeast-1"): 215,
    ("ap-southeast-1", "ap-northeast-1"): 75,
    ("ap-southeast-1", "ap-south-1"): 45,
}

# Cross-AZ overhead within the same region (~2ms per hop)
_INTER_AZ_LATENCY_MS = 2


def get_cross_region_latency_ms(region_a: str | None, region_b: str | None) -> int:
    """
    Return additional latency (ms) for crossing region boundaries.
    Returns 0 if regions are the same or unknown.
    """
    if not region_a or not region_b or region_a == region_b:
        return 0
    key = tuple(sorted([region_a, region_b]))
    return _INTER_REGION_LATENCY_MS.get(key, 150)  # default 150ms for unknown pairs


def get_cross_az_latency_ms(az_a: str | None, az_b: str | None) -> int:
    """
    Return additional latency for crossing AZ boundaries within the same region.
    Returns 0 if AZs are the same or unknown.
    """
    if not az_a or not az_b or az_a == az_b:
        return 0
    return _INTER_AZ_LATENCY_MS


def get_geo_overhead_ms(
    source_region: str | None,
    source_az: str | None,
    target_region: str | None,
    target_az: str | None,
) -> int:
    """
    Total geographic latency overhead between two nodes.
    Adds cross-region (if regions differ) or cross-AZ (if same region, different AZ).
    """
    if source_region != target_region:
        return get_cross_region_latency_ms(source_region, target_region)
    return get_cross_az_latency_ms(source_az, target_az)
