import pytest
from app.lead_intelligence.models import LeadField
from app.lead_intelligence.merger import merge_field

def test_merge_field_unknown_to_confirmed():
    existing = LeadField(value="old", status="unknown", confidence=0.2)
    new_field = LeadField(value="new", status="confirmed", confidence=0.95)
    merged = merge_field(existing, new_field)
    assert merged.value == "new"
    assert merged.status == "confirmed"

def test_merge_field_confirmed_never_overwritten_by_lower():
    existing = LeadField(value="confirmed_val", status="confirmed", confidence=0.9)
    new_field = LeadField(value="guessed_val", status="partially_known", confidence=0.6)
    merged = merge_field(existing, new_field)
    assert merged.value == "confirmed_val"
    assert merged.status == "confirmed"

def test_merge_field_higher_confidence_overwrites():
    existing = LeadField(value="maybe", status="partially_known", confidence=0.5)
    new_field = LeadField(value="probably", status="partially_known", confidence=0.8)
    merged = merge_field(existing, new_field)
    assert merged.value == "probably"
    assert merged.confidence == 0.8
    
def test_merge_field_confirmed_overwrites_confirmed_if_higher():
    existing = LeadField(value="old_conf", status="confirmed", confidence=0.9)
    new_field = LeadField(value="new_conf", status="confirmed", confidence=0.95)
    merged = merge_field(existing, new_field)
    assert merged.value == "new_conf"
    assert merged.confidence == 0.95
    
    # But not if lower
    new_field2 = LeadField(value="newer_conf", status="confirmed", confidence=0.8)
    merged2 = merge_field(merged, new_field2)
    assert merged2.value == "new_conf"
    assert merged2.confidence == 0.95
