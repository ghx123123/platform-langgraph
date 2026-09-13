from types import SimpleNamespace

from backend.classroom.integration import ClassroomIntegrationService, _extract_slide_previews, _requested_slide_count
from backend.workflows.events import EventHub


def test_stream_preview_parser_reports_all_closed_slides_for_bounded_ui_window():
    slides = ",".join(
        '{"title":"S%d","ppt_content":{"title":"S%d","bullets":["b"]}}' % (index, index)
        for index in range(1, 11)
    )
    previews = _extract_slide_previews('{"slides":[' + slides + ']}')
    assert len(previews) == 10
    # The integration layer intentionally sends only the last four cards to
    # the browser; the separate closed_slide_count remains the source of truth.
    assert [item["title"] for item in previews[-4:]] == ["S7", "S8", "S9", "S10"]


def test_generation_status_contract_is_observable_and_stable():
    service = ClassroomIntegrationService(repository=None, event_hub=EventHub())
    status = service.start_status("run-a")
    assert status["closed_slide_count"] == 0
    assert status["target_slide_count"] is None
    assert status["generation_attempt"] == 0
    assert status["generation_request_id"] == "run-a:lesson:v1"


def test_requested_slide_count_is_scoped_to_run_data():
    run = SimpleNamespace(teaching_data={"scope": {"ppt_slide_count": "10"}})
    assert _requested_slide_count(run) == 10
    assert _requested_slide_count(SimpleNamespace(teaching_data={})) is None
