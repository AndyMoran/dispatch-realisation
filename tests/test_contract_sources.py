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


def test_tokens_drop_generic_words():
    from src.ingest.contract_sources import tokens
    assert tokens("Pillswood Battery Storage Ltd") == {"pillswood"}


def test_candidates_rank_by_name_then_party():
    from src.ingest.contract_sources import candidates
    fleet = [{"elexonBmUnit": "T_PILLW-1", "bmUnitName": "Pillswood BESS", "leadPartyName": "Harmony"},
             {"elexonBmUnit": "T_OTHER-1", "bmUnitName": "Other Site", "leadPartyName": "Harmony"},
             {"elexonBmUnit": "T_NONE-1", "bmUnitName": "Unrelated", "leadPartyName": "Zeta"}]
    c = candidates({"unit": "PILLSWOOD-1", "party": "Harmony Energy"}, fleet,
                   ["bmUnitName", "elexonBmUnit"], "leadPartyName")
    assert c[0][1] == "T_PILLW-1" and c[0][0] > c[1][0]
    assert all(b != "T_NONE-1" for _, b in c)
