"""The ontology export (spec 3.7): valid Turtle, no dangling references, and a committed copy in
docs/ontology that matches the generator."""

from pathlib import Path

import pytest
import rdflib
from rdflib.namespace import RDF, SKOS

from cometric.cli import main
from cometric.core import models, ontology
from cometric.core.packs import available_packs, load_pack

DOCS = Path(__file__).resolve().parents[1] / "docs" / "ontology"
CM = rdflib.Namespace(ontology.CORE_NS)
CMV = rdflib.Namespace(ontology.VOCAB_NS)


@pytest.fixture(scope="module")
def graph() -> rdflib.Graph:
    return rdflib.Graph().parse(data=ontology.to_turtle(), format="turtle")


def test_every_pack_concept_rule_claim_and_source_is_typed(graph):
    for pid in available_packs():
        p = load_pack(pid)
        ns = rdflib.Namespace(ontology.pack_ns(pid))
        for c in p.concepts():
            assert (ns[c["id"]], RDF.type, SKOS.Concept) in graph
        for r in p.rules:
            assert (ns[r["id"]], RDF.type, CM.Rule) in graph
        for c in p.claims:
            assert (ns[c["id"]], RDF.type, CM.Claim) in graph
        for s in p.sources:
            assert (ns[s["id"]], RDF.type, CM.Source) in graph


def test_no_dangling_references(graph):
    typed = set(graph.subjects(RDF.type, None))
    dangling = {
        str(x)
        for s, p, o in graph
        for x in (p, o)
        if isinstance(x, rdflib.URIRef)
        and str(x).startswith(ontology.BASE)
        and str(x) != ontology.BASE
        and x not in typed
    }
    assert not dangling


def test_core_model_covers_every_field():
    model = ontology.core_model()
    for cls in ontology.ROOTS:
        assert cls.__name__ in model
    for name, fields in model.items():
        cls = getattr(models, name)
        assert len(fields) == len(cls.model_fields)
        assert ontology.class_note(name)
    for owner, field in ontology.REFERENCES:
        assert field in getattr(models, owner).model_fields, (owner, field)


def test_fields_are_properties_with_ranges(graph):
    assert (CM["FeeComponent.billing_basis"], rdflib.RDFS.range, CMV.BillingBasis) in graph
    assert (CM["FeeComponent.service_id"], rdflib.RDFS.range, CM.Service) in graph
    assert (CM["Tier.from"], rdflib.RDFS.range, rdflib.XSD.decimal) in graph
    assert (CMV["BillingBasis.OUTPUT"], RDF.type, SKOS.Concept) in graph


def test_ids_resolve_through_the_referring_packs_chain(graph):
    # alsp and consulting both define IMPLEMENTATION; each pack's references stay in its own chain.
    alsp = rdflib.Namespace(ontology.pack_ns("alsp"))
    consulting = rdflib.Namespace(ontology.pack_ns("consulting"))
    assert (alsp.IMPLEMENTATION, RDF.type, SKOS.Concept) in graph
    assert (consulting.IMPLEMENTATION, RDF.type, SKOS.Concept) in graph


def test_readme_example_query(graph):
    rows = list(
        graph.query(
            f"""
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            PREFIX cm: <{ontology.CORE_NS}>
            PREFIX cmv: <{ontology.VOCAB_NS}>
            SELECT ?id ?label ?evidence WHERE {{
              ?c skos:notation ?id ; skos:prefLabel ?label ;
                 cm:billingBasis cmv:BillingBasis.OUTPUT ; cm:evidenceClass ?evidence .
            }} ORDER BY ?id"""
        )
    )
    assert rows


def test_cli_writes_the_files(tmp_path, capsys):
    assert main(["ontology", "--out", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(ontology.ontology_files())


@pytest.mark.skipif(not DOCS.exists(), reason="docs/ontology is not in this checkout")
def test_committed_copy_is_current():
    files = ontology.ontology_files()
    assert sorted(p.name for p in DOCS.iterdir()) == sorted(files)
    stale = [name for name, text in files.items() if (DOCS / name).read_text() != text]
    assert not stale, f"regenerate with: uv run cometric ontology --out docs/ontology ({stale})"
