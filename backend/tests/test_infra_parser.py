import pytest
from parsers.infra import _detect_provider, _node_id, _extract_region, _extract_az, _find_references
from models.graph import CloudProvider

def test_detect_provider():
    assert _detect_provider("aws_instance") == CloudProvider.aws
    assert _detect_provider("google_compute_instance") == CloudProvider.gcp
    assert _detect_provider("azurerm_resource_group") == CloudProvider.azure
    assert _detect_provider("unknown_resource") == CloudProvider.unknown
    assert _detect_provider("random") == CloudProvider.unknown

def test_node_id():
    rtype = "aws_instance"
    rname = "web"
    nid = _node_id(rtype, rname)
    assert len(nid) > 0
    assert nid.endswith(f"_{rname}")
    # Deterministic
    assert nid == _node_id(rtype, rname)
    # Different for different name
    assert nid != _node_id(rtype, "db")

def test_extract_region():
    assert _extract_region({"region": "us-east-1"}) == "us-east-1"
    assert _extract_region({"location": "West US"}) == "West US"
    assert _extract_region({"region": "us-east-1", "location": "ignored"}) == "us-east-1"
    assert _extract_region({}) is None

def test_extract_az():
    assert _extract_az({"availability_zone": "us-east-1a"}) == "us-east-1a"
    assert _extract_az({"zone": "us-central1-a"}) == "us-central1-a"
    assert _extract_az({}) is None

def test_find_references():
    current_id = "node1"
    config = {
        "vpc_id": "${aws_vpc.main.id}",
        "subnet_ids": ["${aws_subnet.frontend.id}", "${aws_subnet.backend.id}"],
        "tags": {
            "Name": "web-server",
            "Environment": "${var.env}" # Currently picked up as a resource ref
        },
        "nested": {
            "ref": "${aws_security_group.allow_all.id}"
        }
    }

    # We need to know what _node_id will produce for these resources to assert
    ref1 = _node_id("aws_vpc", "main")
    ref2 = _node_id("aws_subnet", "frontend")
    ref3 = _node_id("aws_subnet", "backend")
    ref4 = _node_id("aws_security_group", "allow_all")
    ref_var = _node_id("var", "env")

    refs = _find_references(config, current_id)

    assert ref1 in refs
    assert ref2 in refs
    assert ref3 in refs
    assert ref4 in refs
    assert ref_var in refs
    assert len(refs) == 5

def test_find_references_avoids_self_reference():
    # If the reference matches current_id, it should be ignored
    rtype = "aws_instance"
    rname = "web"
    node_id = _node_id(rtype, rname)

    config = {
        "self_ref": f"${{{rtype}.{rname}.id}}"
    }

    refs = _find_references(config, node_id)
    assert len(refs) == 0
