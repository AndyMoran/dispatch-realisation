"""Contract-source discovery helpers. No network."""
from src.ingest.contract_sources import date_fields


def test_date_fields_by_type_and_name():
    fields = [{"id": "_id", "type": "int"},
              {"id": "auctionUnit", "type": "text"},
              {"id": "deliveryStart", "type": "text"},
              {"id": "EFA Date", "type": "text"},
              {"id": "cleared", "type": "timestamp"},
              {"id": "clearedVolume", "type": "numeric"}]
    assert date_fields(fields) == ["deliveryStart", "EFA Date", "cleared"]
