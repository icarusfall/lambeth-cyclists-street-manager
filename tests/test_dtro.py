"""Tests for D-TRO integration — classifier, detail extraction, schema mapping."""

import pytest

from src.dtro.pipeline import classify_traffic_order_impact, extract_dtro_details
from src.db.schemas import traffic_order_to_db_row


# --- Sample D-TRO records (based on real data) ---

LAMBETH_ROAD_CLOSURE = {
    "id": "d268d055-66c1-40cd-ab07-31237c6974d1",
    "schemaVersion": "3.4.0",
    "data": {
        "source": {
            "section": "All sections",
            "troName": "License (Other) on Landor Road",
            "madeDate": "2025-09-26",
            "provision": [
                {
                    "reference": "145873525/41545549",
                    "regulation": [
                        {
                            "timeZone": "Europe/London",
                            "condition": [
                                {
                                    "timeValidity": {
                                        "end": "2025-10-07T23:59:59",
                                        "start": "2025-09-26T08:00:00",
                                    }
                                }
                            ],
                            "isDynamic": True,
                            "generalRegulation": {
                                "regulationType": "miscRoadClosure"
                            },
                        }
                    ],
                    "actionType": "new",
                    "regulatedPlace": [
                        {
                            "type": "regulationLocation",
                            "description": "Bedford Road",
                            "linearGeometry": {
                                "linestring": "SRID=27700;LINESTRING (530025.73 175704.5, 530051.73 175697.5)",
                            },
                        },
                        {
                            "type": "diversionRoute",
                            "description": "Stockwell Road",
                            "linearGeometry": {
                                "linestring": "SRID=27700;LINESTRING (530723.16 176118.54, 530032.16 175665.54)",
                            },
                        },
                    ],
                    "provisionDescription": "Road closure",
                }
            ],
            "reference": "145873525",
            "actionType": "new",
            "traCreator": 5660,
            "traAffected": [5660],
            "currentTraOwner": 5660,
            "comingIntoForceDate": "2025-09-26",
        }
    },
    "traName": "LONDON BOROUGH OF LAMBETH",
}

CYCLE_LANE_CLOSURE = {
    "id": "934f0e79-197f-492c-b257-647bdb02d457",
    "schemaVersion": "3.4.0",
    "data": {
        "source": {
            "troName": "License (Other) on Cosser Street",
            "madeDate": "2025-10-24",
            "provision": [
                {
                    "regulation": [
                        {
                            "condition": [
                                {
                                    "timeValidity": {
                                        "end": "2025-10-28T17:27:57",
                                        "start": "2025-10-24T08:43:50",
                                    }
                                }
                            ],
                            "generalRegulation": {
                                "regulationType": "miscCycleLaneClosure"
                            },
                        }
                    ],
                    "regulatedPlace": [
                        {
                            "type": "regulationLocation",
                            "description": "Cosser Street",
                        }
                    ],
                    "provisionDescription": "Cycle lane closure",
                }
            ],
            "reference": "145999001",
            "actionType": "new",
            "traCreator": 5660,
            "currentTraOwner": 5660,
            "comingIntoForceDate": "2025-10-24",
        }
    },
    "traName": "LONDON BOROUGH OF LAMBETH",
}

LEWISHAM_PARKING = {
    "id": "abc123-parking",
    "schemaVersion": "3.4.0",
    "data": {
        "source": {
            "troName": "The Lewisham (Parking) Order 2025",
            "madeDate": "2025-10-27",
            "provision": [
                {
                    "regulation": [
                        {
                            "generalRegulation": {
                                "regulationType": "kerbsideNoWaiting"
                            }
                        }
                    ],
                    "regulatedPlace": [
                        {
                            "type": "regulationLocation",
                            "description": "CRESSINGHAM ROAD - side of road: south",
                            "linearGeometry": {
                                "linestring": "SRID=27700;LINESTRING (538389.37 175831.89, 538382.97 175830.95)",
                            },
                        }
                    ],
                    "provisionDescription": "No waiting at any time",
                },
                {
                    "regulation": [
                        {
                            "generalRegulation": {
                                "regulationType": "kerbsideParkingPlace"
                            }
                        }
                    ],
                    "regulatedPlace": [],
                    "provisionDescription": "Parking places",
                },
            ],
            "reference": "LEW-2025-001",
            "actionType": "new",
            "traCreator": 5690,
            "currentTraOwner": 5690,
            "comingIntoForceDate": "2025-10-27",
        }
    },
    "traName": "LONDON BOROUGH OF LEWISHAM",
}


class TestClassifier:
    """Test cycling impact classification for traffic orders."""

    def test_road_closure_is_negative(self):
        assert classify_traffic_order_impact(["miscRoadClosure"], "new") == "Negative"

    def test_cycle_lane_closure_is_negative(self):
        assert classify_traffic_order_impact(["miscCycleLaneClosure"], "new") == "Negative"

    def test_one_way_is_negative(self):
        assert classify_traffic_order_impact(["miscOneWay"], "new") == "Negative"

    def test_new_cycle_lane_is_positive(self):
        assert classify_traffic_order_impact(["cycleLane"], "new") == "Positive"

    def test_parking_only_is_neutral(self):
        assert classify_traffic_order_impact(
            ["kerbsideNoWaiting", "kerbsideParkingPlace"], "new"
        ) == "Neutral"

    def test_loading_is_needs_review(self):
        assert classify_traffic_order_impact(["kerbsideLoadingPlace"], "new") == "Needs Review"

    def test_speed_limit_is_needs_review(self):
        assert classify_traffic_order_impact(["speedLimit"], "new") == "Needs Review"

    def test_mixed_with_road_closure_is_negative(self):
        # Road closure + parking = negative (road closure dominates)
        assert classify_traffic_order_impact(
            ["miscRoadClosure", "kerbsideNoWaiting"], "new"
        ) == "Negative"

    def test_unknown_regulation_is_needs_review(self):
        assert classify_traffic_order_impact(["somethingNew"], "new") == "Needs Review"

    def test_empty_regulations_is_needs_review(self):
        assert classify_traffic_order_impact([], "new") == "Needs Review"


class TestExtractDetails:
    """Test extraction of key fields from full D-TRO records."""

    def test_basic_fields(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        assert details["dtro_id"] == "d268d055-66c1-40cd-ab07-31237c6974d1"
        assert details["tro_name"] == "License (Other) on Landor Road"
        assert details["reference"] == "145873525"
        assert details["tra_name"] == "LONDON BOROUGH OF LAMBETH"
        assert details["tra_code"] == 5660
        assert details["action_type"] == "new"
        assert details["made_date"] == "2025-09-26"
        assert details["effective_date"] == "2025-09-26"
        assert details["schema_version"] == "3.4.0"

    def test_regulation_types_extracted(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        assert details["regulation_types"] == ["miscRoadClosure"]

    def test_multiple_regulation_types(self):
        details = extract_dtro_details(LEWISHAM_PARKING)
        assert "kerbsideNoWaiting" in details["regulation_types"]
        assert "kerbsideParkingPlace" in details["regulation_types"]

    def test_street_names_from_regulation_locations(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        # Should include Bedford Road (regulationLocation) but NOT Stockwell Road (diversionRoute)
        assert "Bedford Road" in details["street_names"]
        assert "Stockwell Road" not in details["street_names"]

    def test_street_name_cleaning(self):
        details = extract_dtro_details(LEWISHAM_PARKING)
        # "CRESSINGHAM ROAD - side of road: south" should be cleaned
        assert "CRESSINGHAM ROAD" in details["street_names"]
        assert "side of road" not in str(details["street_names"])

    def test_coordinates_from_bng_linestring(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        assert details["coordinates"] is not None
        lon, lat = details["coordinates"].split(",")
        # Bedford Road, Lambeth — should be roughly -0.12, 51.47
        assert -0.15 < float(lon) < -0.10
        assert 51.45 < float(lat) < 51.48

    def test_time_validity_extracted(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        assert details["regulation_start"] == "2025-09-26T08:00:00"
        assert details["regulation_end"] == "2025-10-07T23:59:59"

    def test_provision_description(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        assert details["provision_description"] == "Road closure"

    def test_no_coordinates_when_no_geometry(self):
        details = extract_dtro_details(CYCLE_LANE_CLOSURE)
        assert details["coordinates"] is None


class TestDbRowProperties:
    """Test database row mapping for traffic orders."""

    def test_basic_properties(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        row = traffic_order_to_db_row(
            details=details,
            borough="Lambeth",
            cycling_impact="Negative",
            cycling_summary="Road closure on Bedford Road affects cycling access.",
        )
        assert row["name"] == "License (Other) on Landor Road"
        assert row["dtro_id"] == "d268d055-66c1-40cd-ab07-31237c6974d1"
        assert row["borough"] == "Lambeth"
        assert row["cycling_impact"] == "Negative"
        assert row["cycling_summary"] == "Road closure on Bedford Road affects cycling access."
        assert row["action_type"] == "New"

    def test_regulation_type_list(self):
        details = extract_dtro_details(LEWISHAM_PARKING)
        row = traffic_order_to_db_row(
            details=details, borough="Lewisham", cycling_impact="Neutral",
        )
        assert "kerbsideNoWaiting" in row["regulation_type"]
        assert "kerbsideParkingPlace" in row["regulation_type"]

    def test_dates(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        row = traffic_order_to_db_row(
            details=details, borough="Lambeth", cycling_impact="Negative",
        )
        assert row["made_date"] == "2025-09-26"
        assert row["effective_date"] == "2025-09-26"
        assert row["end_date"] == "2025-10-07"

    def test_coordinates_included(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        row = traffic_order_to_db_row(
            details=details, borough="Lambeth", cycling_impact="Negative",
        )
        assert row["lon"] is not None
        assert row["lat"] is not None

    def test_no_summary_when_none(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        row = traffic_order_to_db_row(
            details=details, borough="Lambeth", cycling_impact="Negative",
        )
        assert row["cycling_summary"] is None

    def test_street_name_populated(self):
        details = extract_dtro_details(LAMBETH_ROAD_CLOSURE)
        row = traffic_order_to_db_row(
            details=details, borough="Lambeth", cycling_impact="Negative",
        )
        assert "Bedford Road" in row["street_name"]
