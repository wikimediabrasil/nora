from types import SimpleNamespace
from unittest import mock

import requests
from django.test import TestCase, override_settings

from mapper.models import MappingDecision, Ontology, PropertyProposal, WikidataProperty
from mapper.services import wikidata_api, review, validation, wikidata_mcp

from .helpers import WIKIDATA_API, decide, make_field, make_ontology, make_property, make_user


def api_response(payload):
    response = mock.Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


ENTITY_P580 = {"entities": {"P580": {
    "labels": {"pt": {"value": "data de início"}},
    "descriptions": {"pt": {"value": "quando algo começou"}},
    "datatype": "time",
}}}


class WikidataApiTests(TestCase):
    @mock.patch("mapper.services.wikidata_api.requests.get")
    def test_search_properties_returns_entities_in_order(self, get):
        get.side_effect = [
            api_response({"query": {"search": [{"title": "Property:P580"}]}}),
            api_response(ENTITY_P580),
        ]
        result = wikidata_api.search_properties("data", "pt", WIKIDATA_API)
        self.assertEqual(result, [{"pid": "P580", "label": "data de início", "description": "quando algo começou", "datatype": "time"}])

    @mock.patch("mapper.services.wikidata_api.requests.get")
    def test_search_without_hits_skips_entity_call(self, get):
        get.return_value = api_response({"query": {"search": []}})
        self.assertEqual(wikidata_api.search_properties("nothing", "pt", WIKIDATA_API), [])
        self.assertEqual(get.call_count, 1)

    @mock.patch("mapper.services.wikidata_api.requests.get")
    def test_store_property_creates_then_updates(self, get):
        get.return_value = api_response(ENTITY_P580)
        wikidata_api.store_property("P580", "pt", WIKIDATA_API)
        wikidata_api.store_property("P580", "pt", WIKIDATA_API)
        self.assertEqual(WikidataProperty.objects.filter(pid="P580").count(), 1)

    @mock.patch("mapper.services.wikidata_api.requests.get")
    def test_store_property_returns_none_when_missing(self, get):
        get.return_value = api_response({"entities": {"P999999": {"missing": ""}}})
        self.assertIsNone(wikidata_api.store_property("P999999", "pt", WIKIDATA_API))


class WikidataMcpTests(TestCase):
    @override_settings(USE_WD_MCP=False)
    def test_disabled_raises(self):
        with self.assertRaises(RuntimeError):
            wikidata_mcp.find_candidates_mcp("date", "en")

    @override_settings(USE_WD_MCP=True)
    def test_parses_structured_content(self):
        result = SimpleNamespace(structured_content={"result": "P580: start time — when it began\nnot a line\nP582: end time"}, content=[])
        with mock.patch.object(wikidata_mcp, "_call_tool_async", mock.AsyncMock(return_value=result)):
            candidates = wikidata_mcp.find_candidates_mcp("date", "en")
        self.assertEqual(candidates, [
            {"pid": "P580", "label": "start time", "description": "when it began"},
            {"pid": "P582", "label": "end time", "description": ""},
        ])

    @override_settings(USE_WD_MCP=True)
    def test_falls_back_to_text_blocks_and_limits(self):
        lines = "\n".join(f"P{n}: label {n}" for n in range(10))
        result = SimpleNamespace(structured_content=None, content=[SimpleNamespace(text=lines)])
        with mock.patch.object(wikidata_mcp, "_call_tool_async", mock.AsyncMock(return_value=result)):
            self.assertEqual(len(wikidata_mcp.find_candidates_mcp("x", "en", top_n=3)), 3)


class WikidataMcpClientTests(TestCase):
    """Covers the MCP session itself, with the transport and session replaced by fakes."""

    @override_settings(USE_WD_MCP=True, WD_MCP_URL="https://mcp.example/mcp/")
    def test_opens_session_and_calls_search_properties(self):
        session = mock.AsyncMock()
        session.call_tool.return_value = SimpleNamespace(structured_content={"result": "P580: start time"}, content=[])

        transport = mock.MagicMock()
        transport.__aenter__.return_value = ("read", "write")
        client_session = mock.MagicMock()
        client_session.__aenter__.return_value = session

        with mock.patch.object(wikidata_mcp, "streamable_http_client", return_value=transport) as http_client, \
                mock.patch.object(wikidata_mcp, "ClientSession", return_value=client_session) as session_class:
            candidates = wikidata_mcp.find_candidates_mcp("date", "pt")

        http_client.assert_called_once_with("https://mcp.example/mcp/")
        session_class.assert_called_once_with("read", "write")
        session.initialize.assert_awaited_once()
        session.call_tool.assert_awaited_once_with(
            "search_properties", {"query": "date", "lang": "pt", "include_external_ids": False}
        )
        self.assertEqual(candidates, [{"pid": "P580", "label": "start time", "description": ""}])


class ReviewQueueTests(TestCase):
    def setUp(self):
        self.ontology = make_ontology(make_user())
        self.first, self.second, self.third = (make_field(self.ontology, name) for name in ("a", "b", "c"))

    def test_next_pending_skips_done_fields(self):
        decide(self.first, MappingDecision.STATUS_INVALID)
        self.assertEqual(review.next_pending_field(self.ontology), self.second)

    def test_ambiguous_fields_stay_in_the_queue(self):
        decide(self.first, MappingDecision.STATUS_AMBIGUOUS)
        self.assertEqual(review.next_pending_field(self.ontology), self.first)

    def test_skip_moves_forward_and_wraps_around(self):
        self.assertEqual(review.next_pending_field(self.ontology, after_id=self.first.id), self.second)
        self.assertEqual(review.next_pending_field(self.ontology, after_id=self.third.id), self.first)

    def test_none_when_everything_is_done(self):
        for field in (self.first, self.second, self.third):
            decide(field, MappingDecision.STATUS_INVALID)
        self.assertIsNone(review.next_pending_field(self.ontology))

    def test_progress(self):
        decide(self.first, MappingDecision.STATUS_INVALID)
        self.assertEqual(review.get_progress(self.ontology), (1, 3, 33))
        self.assertEqual(review.get_progress(make_ontology(self.ontology.created_by, title="empty")), (0, 0, 0))


class MergeCandidatesTests(TestCase):
    def test_consensus_first_and_sources_marked(self):
        merged = review.merge_candidates(
            [{"pid": "P1", "label": "one"}, {"pid": "P2", "label": "two"}],
            [{"pid": "P2", "label": "two", "description": "from mcp"}, {"pid": "P3", "label": "three"}],
        )
        self.assertEqual([c["pid"] for c in merged], ["P2", "P1", "P3"])
        self.assertEqual(merged[0]["source"], MappingDecision.SOURCE_CONSENSUS)
        self.assertEqual(merged[0]["description"], "from mcp")
        self.assertEqual(merged[1]["source"], MappingDecision.SOURCE_WIKIDATA_SEARCH)
        self.assertEqual(merged[2]["source"], MappingDecision.SOURCE_WIKIDATA_MCP)


class BuildReviewContextTests(TestCase):
    def setUp(self):
        self.ontology = make_ontology(make_user())
        self.field = make_field(self.ontology)

    @override_settings(USE_WD_MCP=False)
    @mock.patch("mapper.services.review.wikidata_api")
    def test_first_candidate_becomes_the_suggestion(self, api):
        api.search_properties.return_value = [{"pid": "P580", "label": "start"}]
        api.store_property.return_value = make_property()
        context = review.build_review_context(self.ontology, self.field)
        self.assertEqual(context["decision"].suggested_property.pid, "P580")
        self.assertIsNone(context["search_error"])

    @override_settings(USE_WD_MCP=False)
    @mock.patch("mapper.services.review.wikidata_api.search_properties", side_effect=requests.ConnectionError)
    def test_search_error_is_reported(self, _search):
        self.assertIsNotNone(review.build_review_context(self.ontology, self.field)["search_error"])

    @override_settings(USE_WD_MCP=True)
    @mock.patch("mapper.services.review.wikidata_api.search_properties", return_value=[])
    @mock.patch("mapper.services.review.wikidata_mcp.find_candidates_mcp", side_effect=RuntimeError("down"))
    def test_mcp_error_is_reported(self, _mcp, _search):
        self.assertEqual(review.build_review_context(self.ontology, self.field)["mcp_error"], "down")

    @override_settings(USE_WD_MCP=True)
    @mock.patch("mapper.services.review.wikidata_api.search_properties", return_value=[])
    @mock.patch("mapper.services.review.wikidata_mcp.find_candidates_mcp")
    def test_mcp_is_not_used_for_wikibase(self, mcp, _search):
        self.ontology.deployment_mode = Ontology.DeploymentMode.WIKIBASE
        self.ontology.wikibase_api_endpoint = "https://my.wikibase.cloud/w/api.php"
        self.ontology.save()
        review.build_review_context(self.ontology, self.field)
        mcp.assert_not_called()


@mock.patch("mapper.services.review.wikidata_api.store_property")
class RecordAiSuggestionTests(TestCase):
    def setUp(self):
        self.field = make_field(make_ontology(make_user()))

    def test_valid_answer_is_saved_with_clamped_confidence(self, store):
        store.return_value = make_property()
        self.assertTrue(review.record_ai_suggestion(self.field, {"pid": " p580 ", "confidence": "7", "justification": "x" * 3000}))
        decision = MappingDecision.objects.get(ontology_field=self.field)
        self.assertEqual(decision.suggested_property.pid, "P580")
        self.assertEqual(decision.ai_confidence, 1.0)
        self.assertEqual(len(decision.ai_justification), 2000)

    def test_invalid_pid_is_rejected(self, store):
        self.assertFalse(review.record_ai_suggestion(self.field, {"pid": "Q42"}))
        store.assert_not_called()

    def test_invalid_confidence_becomes_none(self, store):
        store.return_value = make_property()
        review.record_ai_suggestion(self.field, {"pid": "P580", "confidence": "high"})
        self.assertIsNone(MappingDecision.objects.get(ontology_field=self.field).ai_confidence)

    def test_network_error_returns_false(self, store):
        store.side_effect = requests.ConnectionError
        self.assertFalse(review.record_ai_suggestion(self.field, {"pid": "P580"}))


@mock.patch("mapper.services.review.wikidata_api.store_property")
class RecordDecisionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.field = make_field(make_ontology(self.user))
        self.prop = make_property()

    def decision(self):
        return MappingDecision.objects.get(ontology_field=self.field)

    def test_unknown_status_is_rejected(self, store):
        self.assertFalse(review.record_decision(self.field, {"status": "nonsense"}, self.user))

    def test_valid_with_chosen_pid_and_source(self, store):
        store.return_value = self.prop
        review.record_decision(self.field, {"status": "valid", "chosen_pid": "P580", "source": "consensus"}, self.user)
        decision = self.decision()
        self.assertEqual(decision.chosen_property, self.prop)
        self.assertEqual(decision.chosen_source, MappingDecision.SOURCE_CONSENSUS)
        self.assertEqual(decision.reviewed_by, self.user)

    def test_valid_falls_back_to_suggestion_and_drops_unknown_source(self, store):
        store.return_value = self.prop
        decide(self.field, MappingDecision.STATUS_PENDING, suggested_property=self.prop)
        review.record_decision(self.field, {"status": "valid", "source": "forged"}, self.user)
        store.assert_called_once_with("P580", "pt", WIKIDATA_API)
        self.assertEqual(self.decision().chosen_source, "")

    def test_manual_search_with_pid_becomes_valid(self, store):
        store.return_value = self.prop
        review.record_decision(self.field, {"status": "manual_search", "manual_pid": "p580"}, self.user)
        decision = self.decision()
        self.assertEqual(decision.status, MappingDecision.STATUS_VALID)
        self.assertEqual(decision.chosen_source, MappingDecision.SOURCE_MANUAL)

    def test_manual_search_without_pid_stays_manual(self, store):
        review.record_decision(self.field, {"status": "manual_search"}, self.user)
        self.assertEqual(self.decision().status, MappingDecision.STATUS_MANUAL)

    def test_network_error_puts_field_back_to_pending(self, store):
        store.side_effect = requests.ConnectionError
        review.record_decision(self.field, {"status": "valid", "chosen_pid": "P580"}, self.user)
        self.assertEqual(self.decision().status, MappingDecision.STATUS_PENDING)

    def test_gap_creates_proposal_and_other_status_removes_it(self, store):
        review.record_decision(self.field, {"status": "gap", "proposed_label": "acquisition date", "proposed_datatype": "time", "justification": "none fits"}, self.user)
        self.assertEqual(PropertyProposal.objects.get().justification, "none fits")
        review.record_decision(self.field, {"status": "invalid"}, self.user)
        self.assertFalse(PropertyProposal.objects.exists())


class ValidationTests(TestCase):
    def setUp(self):
        self.ontology = make_ontology(make_user())

    def check(self, field_datatype="", sample="", prop=None, status=MappingDecision.STATUS_VALID):
        field = make_field(self.ontology, f"f{MappingDecision.objects.count()}", datatype=field_datatype, sample_value=sample)
        return validation.validate_decision(decide(field, status, prop))

    def test_non_valid_decisions_pass(self):
        self.assertTrue(self.check(status=MappingDecision.STATUS_GAP).valid)

    def test_valid_without_property_fails(self):
        self.assertFalse(self.check().valid)

    def test_compatible_datatype_passes(self):
        self.assertTrue(self.check("Data", "1922", make_property(datatype="time")).valid)

    def test_incompatible_datatype_fails(self):
        result = self.check("date", "1922", make_property(datatype="string"))
        self.assertFalse(result.valid)
        self.assertIn("Incompatible datatype", result.errors[0])

    def test_unknown_source_datatype_is_not_checked(self):
        self.assertTrue(self.check("whatever", "", make_property(datatype="string")).valid)

    def test_allowed_values_constraint(self):
        prop = make_property(constraints={"allowed_values": ["a", "b"]})
        self.assertTrue(self.check(sample="a", prop=prop).valid)
        self.assertFalse(self.check(sample="z", prop=prop).valid)

    def test_format_constraint(self):
        prop = make_property(constraints={"format_regex": r"\d{4}"})
        self.assertTrue(self.check(sample="1922", prop=prop).valid)
        self.assertFalse(self.check(sample="19-22", prop=prop).valid)