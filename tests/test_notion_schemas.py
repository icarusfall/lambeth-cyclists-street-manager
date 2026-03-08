"""Tests for Notion property mapping."""

from src.notion.schemas import work_to_notion_properties


class TestWorkToNotionProperties:
    def test_basic_mapping(self):
        object_data = {
            "permit_reference_number": "TEST-001",
            "work_reference_number": "WORK-001",
            "street_name": "BRIXTON ROAD",
            "area_name": "BRIXTON",
            "highway_authority": "LONDON BOROUGH OF LAMBETH",
            "promoter_organisation": "Thames Water",
            "usrn": "22500123",
            "work_category_ref": "minor",
            "traffic_management_type_ref": "road_closure",
            "work_status_ref": "in_progress",
            "proposed_start_date": "2026-03-10T00:00:00.000Z",
            "proposed_end_date": "2026-03-14T00:00:00.000Z",
            "activity_type": "Utility repair and maintenance works",
            "is_ttro_required": "Yes",
        }

        props = work_to_notion_properties(
            object_data=object_data,
            borough="Lambeth",
            cycling_impact="high",
            cycling_summary="Major disruption on key cycling corridor.",
            event_type="WORK_START",
            wgs84_coords="-0.114000,51.462000",
        )

        # Check title
        assert props["Name"]["title"][0]["text"]["content"] == "BRIXTON ROAD, BRIXTON"

        # Check selects
        assert props["Borough"]["select"]["name"] == "Lambeth"
        assert props["Work Category"]["select"]["name"] == "Minor"
        assert props["Traffic Management"]["select"]["name"] == "Road closure"
        assert props["Work Status"]["select"]["name"] == "In progress"
        assert props["Cycling Impact"]["select"]["name"] == "High"

        # Check rich text
        assert props["Permit Reference"]["rich_text"][0]["text"]["content"] == "TEST-001"
        assert props["Cycling Summary"]["rich_text"][0]["text"]["content"] == "Major disruption on key cycling corridor."

        # Check checkbox
        assert props["TTRO Required"]["checkbox"] is True

        # Check dates
        assert props["Proposed Start"]["date"]["start"] == "2026-03-10"

    def test_missing_area_name(self):
        props = work_to_notion_properties(
            object_data={"street_name": "HIGH STREET"},
            borough="Southwark",
            cycling_impact="low",
            cycling_summary=None,
            event_type="PERMIT_GRANTED",
        )
        assert props["Name"]["title"][0]["text"]["content"] == "HIGH STREET"
        assert "Cycling Summary" not in props

    def test_no_cycling_summary_omitted(self):
        props = work_to_notion_properties(
            object_data={},
            borough="Wandsworth",
            cycling_impact="minimal",
            cycling_summary=None,
            event_type="PERMIT_GRANTED",
        )
        assert "Cycling Summary" not in props
