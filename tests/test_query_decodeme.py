"""
Tests for the query_decodeme tool and DecodeME connector.

These tests run against the bundled loci.json (no download required).
When real summary-statistics files are present, the same tests also exercise the
DuckDB path via integration tests (marked with pytest.mark.integration).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from src.connectors import decodeme as _dc
from src.models import GWASLocus, GWASSignal, Provenance


# ---------------------------------------------------------------------------
# Bundled loci.json — always-on tests (no download needed)
# ---------------------------------------------------------------------------

class TestBundledLociJson:
    def test_loci_json_exists(self, loci_json_path):
        assert loci_json_path.exists(), "data/decodeme/loci.json must exist"

    def test_loci_json_valid(self, loci_json_path):
        raw = json.loads(loci_json_path.read_text(encoding="utf-8"))
        assert "_meta" in raw
        assert "loci" in raw
        assert len(raw["loci"]) >= 1

    def test_all_loci_have_required_fields(self, loci_json_path):
        raw = json.loads(loci_json_path.read_text(encoding="utf-8"))
        required = {"locus_id", "chr", "pos_hg38", "nearest_gene", "candidate_causal_genes", "p_value"}
        for locus in raw["loci"]:
            missing = required - set(locus.keys())
            assert not missing, f"Locus {locus.get('locus_id')} missing fields: {missing}"

    def test_known_genes_present(self, loci_json_path):
        """DecodeME paper identified these genes — they must be in the bundled data."""
        raw = json.loads(loci_json_path.read_text(encoding="utf-8"))
        all_candidate_genes = set()
        for locus in raw["loci"]:
            all_candidate_genes.update(locus.get("candidate_causal_genes", []))

        for gene in ("BTN2A2", "OLFM4", "RABGAP1L"):
            assert gene in all_candidate_genes, (
                f"Gene {gene} not found in bundled loci.json — "
                "this is a known DecodeME genome-wide significant hit"
            )

    def test_p_values_genome_wide_significant(self, loci_json_path):
        """All bundled loci should be genome-wide significant (p < 5×10⁻⁸)."""
        raw = json.loads(loci_json_path.read_text(encoding="utf-8"))
        for locus in raw["loci"]:
            p = locus["p_value"]
            assert p < 5e-8, (
                f"Locus {locus['locus_id']} p={p} is not genome-wide significant"
            )


# ---------------------------------------------------------------------------
# DecodeME connector — bundled-mode
# ---------------------------------------------------------------------------

class TestDecodeMEConnectorBundled:
    def test_data_mode_without_files(self, tmp_path, monkeypatch):
        """When no GWAS files are present, mode should be 'bundled_loci_json'."""
        monkeypatch.setattr(_dc, "DATA_DIR", tmp_path)
        assert _dc.data_mode() == "bundled_loci_json"

    def test_query_signals_bundled_returns_list(self):
        signals = _dc._query_from_bundled_json(p_threshold=5e-8, gwas_set="GWAS-1", chr_=None)
        assert isinstance(signals, list)
        assert len(signals) >= 1

    def test_query_signals_bundled_all_significant(self):
        signals = _dc._query_from_bundled_json(p_threshold=5e-8, gwas_set="GWAS-1", chr_=None)
        for s in signals:
            assert s.p_value < 5e-8

    def test_query_signals_bundled_provenance(self):
        signals = _dc._query_from_bundled_json(p_threshold=5e-8, gwas_set="GWAS-1", chr_=None)
        for s in signals:
            assert s.provenance.source == "DecodeME_GWAS_2025"
            assert s.provenance.evidence_type == "GWAS"
            assert s.provenance.data_quality == "approximate_from_paper"
            assert s.provenance.strength > 0
            assert math.isfinite(s.provenance.strength)

    def test_query_signals_bundled_neg_log10p_consistent(self):
        signals = _dc._query_from_bundled_json(p_threshold=5e-8, gwas_set="GWAS-1", chr_=None)
        for s in signals:
            expected_nlp = -math.log10(s.p_value)
            assert abs(s.neg_log10_p - expected_nlp) < 1e-9

    def test_load_loci_with_annotation_bundled(self):
        loci = _dc.load_loci_with_annotation(p_threshold=5e-8, gwas_set="GWAS-1")
        assert isinstance(loci, list)
        assert len(loci) >= 1
        for locus in loci:
            assert isinstance(locus, GWASLocus)
            assert locus.candidate_causal_genes
            assert locus.lead_signal.p_value < 5e-8

    def test_loci_sorted_by_pvalue(self):
        loci = _dc.load_loci_with_annotation(p_threshold=5e-8, gwas_set="GWAS-1")
        p_values = [l.lead_signal.p_value for l in loci]
        assert p_values == sorted(p_values)

    def test_gene_filter_btna2a(self):
        """Filtering by BTN2A2 should return the 6q13 locus."""
        loci = _dc.load_loci_with_annotation(p_threshold=5e-8, gwas_set="GWAS-1")
        btn2a2_loci = [l for l in loci if "BTN2A2" in l.candidate_causal_genes]
        assert len(btn2a2_loci) >= 1, "BTN2A2 should appear in at least one locus"


# ---------------------------------------------------------------------------
# Provenance model validation
# ---------------------------------------------------------------------------

class TestProvenanceModel:
    def test_provenance_rejects_infinite_strength(self):
        with pytest.raises(Exception):
            Provenance(
                source="test",
                evidence_type="GWAS",
                strength=float("inf"),
                strength_label="inf",
            )

    def test_provenance_rejects_nan_strength(self):
        with pytest.raises(Exception):
            Provenance(
                source="test",
                evidence_type="GWAS",
                strength=float("nan"),
                strength_label="nan",
            )

    def test_provenance_valid(self):
        prov = Provenance(
            source="DecodeME_GWAS_2025",
            evidence_type="GWAS",
            url="https://osf.io/rgqs3/",
            strength=8.39,
            strength_label="p=4.1e-09",
        )
        assert prov.source == "DecodeME_GWAS_2025"
        assert prov.data_quality == "exact"
