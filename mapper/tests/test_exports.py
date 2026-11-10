import csv
import io
import json
import zipfile

from django.test import TestCase

from mapper.models import MappingDecision, PropertyProposal
from mapper.services.export_frictionless import build_frictionless_package
from mapper.services.export_quickstatements import HEADER, build_quickstatements_csv

from .helpers import decide, make_field, make_ontology, make_property, make_user


class ExportTests(TestCase):
    def setUp(self):
        self.ontology = make_ontology(make_user(), language="pt")
        good = make_field(self.ontology, "acquired", datatype="date", sample_value="1922", description="Acquisition date")
        bad = make_field(self.ontology, "title", datatype="date", sample_value="Postcard")
        gap = make_field(self.ontology, "provenance", sample_value="Gift")
        make_field(self.ontology, "untouched")

        decide(good, MappingDecision.STATUS_VALID, make_property("P580", "time"), chosen_source=MappingDecision.SOURCE_MANUAL, ai_justification="dates")
        decide(bad, MappingDecision.STATUS_VALID, make_property("P1476", "monolingualtext"))
        gap_decision = decide(gap, MappingDecision.STATUS_GAP)
        PropertyProposal.objects.create(decision=gap_decision, proposed_label="provenance note", proposed_datatype="Texto", justification="No property fits")

    def test_csv_has_only_rows_that_pass_validation(self):
        content, warnings = build_quickstatements_csv(self.ontology.id)
        rows = list(csv.reader(io.StringIO(content)))
        self.assertEqual(rows[0], HEADER)
        self.assertEqual(rows[1:], [["", "P580", "1922", "acquired"]])
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("title:"))

    def test_package_contents(self):
        package, warnings = build_frictionless_package(self.ontology.id)
        with zipfile.ZipFile(io.BytesIO(package)) as zf:
            names = zf.namelist()
            datapackage = json.loads(zf.read("datapackage.json"))
            report = zf.read("REPORT.md").decode()
            proposal_name = next(n for n in names if n.startswith("property_proposals/"))
            proposal = zf.read(proposal_name).decode()

        self.assertIn("mapping_quickstatements.csv", names)
        self.assertEqual(datapackage["resources"][0]["path"], "mapping_quickstatements.csv")
        self.assertEqual([f["name"] for f in datapackage["resources"][0]["schema"]["fields"]], HEADER)

        self.assertIn("### untouched", report)
        self.assertIn("P580", report)
        self.assertIn("dates", report)
        self.assertIn(proposal_name, report)
        self.assertIn(warnings[0], report)

        self.assertIn("|datatype\t\t= string", proposal)
        self.assertIn("No property fits ~~~~", proposal)
        self.assertIn("add the English version", proposal)
