from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings

from mapper.models import MappingDecision, MappingDecisionHistory, Ontology, PropertyProposal

from .helpers import decide, make_field, make_ontology, make_property, make_user


# ======================================================================================================================
# PERMISSION
# ======================================================================================================================
class OntologyPermissionTests(TestCase):
    def setUp(self):
        self.owner = make_user("Owner")
        self.listed = make_user("Listed")
        self.other = make_user("Other")
        self.admin = make_user("Admin", is_superuser=True)

    def ontology(self, visibility):
        return make_ontology(self.owner, title=visibility, visibility=visibility, authorized_usernames=["Listed"])

    def test_anonymous_cannot_view(self):
        self.assertFalse(self.ontology(Ontology.Visibility.PUBLIC).can_view(AnonymousUser()))

    def test_public_is_visible_to_any_logged_user(self):
        self.assertTrue(self.ontology(Ontology.Visibility.PUBLIC).can_view(self.other))

    def test_restricted_is_visible_only_to_listed_users(self):
        ontology = self.ontology(Ontology.Visibility.RESTRICTED)
        self.assertTrue(ontology.can_view(self.listed))
        self.assertFalse(ontology.can_view(self.other))

    def test_private_is_visible_only_to_owner_and_superuser(self):
        ontology = self.ontology(Ontology.Visibility.PRIVATE)
        self.assertTrue(ontology.can_view(self.owner))
        self.assertTrue(ontology.can_view(self.admin))
        self.assertFalse(ontology.can_view(self.listed))

    def test_only_owner_and_superuser_can_edit(self):
        ontology = self.ontology(Ontology.Visibility.PUBLIC)
        self.assertTrue(ontology.can_edit(self.owner))
        self.assertTrue(ontology.can_edit(self.admin))
        self.assertFalse(ontology.can_edit(self.listed))


# ======================================================================================================================
# API
# ======================================================================================================================
class OntologyApiUrlTests(TestCase):
    def setUp(self):
        self.owner = make_user()

    @override_settings(WIKIDATA_API_ENDPOINT="https://wikidata.example/w/api.php")
    def test_wikidata_mode_uses_default_endpoint(self):
        self.assertEqual(make_ontology(self.owner).api_url, "https://wikidata.example/w/api.php")

    def test_wikibase_mode_uses_own_endpoint(self):
        ontology = make_ontology(
            self.owner,
            deployment_mode=Ontology.DeploymentMode.WIKIBASE,
            wikibase_api_endpoint="https://my.wikibase.cloud/w/api.php",
        )
        self.assertEqual(ontology.api_url, "https://my.wikibase.cloud/w/api.php")


# ======================================================================================================================
# DECISION
# ======================================================================================================================
class MappingDecisionHistoryTests(TestCase):
    def test_history_is_recorded_on_every_update_but_not_on_creation(self):
        field = make_field(make_ontology(make_user()))
        decision = MappingDecision.objects.create(ontology_field=field)
        self.assertEqual(decision.history.count(), 0)

        decide(field, MappingDecision.STATUS_VALID, make_property())
        decide(field, MappingDecision.STATUS_INVALID)

        statuses = list(MappingDecisionHistory.objects.order_by("id").values_list("status", flat=True))
        self.assertEqual(statuses, [MappingDecision.STATUS_VALID, MappingDecision.STATUS_INVALID])


class StrTests(TestCase):
    def test_str_methods(self):
        ontology = make_ontology(make_user())
        field = make_field(ontology)
        prop = make_property()
        decision = decide(field, MappingDecision.STATUS_GAP)
        proposal = PropertyProposal.objects.create(decision=decision, proposed_label="acquisition date", proposed_datatype="time")

        self.assertEqual(str(ontology), "Postcards (Museu Paulista)")
        self.assertEqual(str(field), "Postcards :: data_aquisicao")
        self.assertIn("P580", str(prop))
        self.assertIn("data_aquisicao", str(decision))
        self.assertIn("acquisition date", str(proposal))
