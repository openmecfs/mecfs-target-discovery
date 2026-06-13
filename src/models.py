"""Shared provenance-carrying data models for the ME/CFS target-discovery MCP server."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Provenance(BaseModel):
    """Every edge / claim must carry one of these. No provenance = no edge."""

    source: str
    """Human-readable source ID, e.g. 'DecodeME_GWAS_2024', 'OpenTargets_v24.09'."""

    evidence_type: Literal[
        "GWAS", "eQTL", "drug_target", "pathway", "literature", "clinical_trial", "database"
    ]
    url: str | None = None
    pmid: str | None = None
    doi: str | None = None

    strength: float
    """
    For GWAS: -log10(p).
    For database scores: 0–1 association score.
    Always a higher-is-stronger float.
    """
    strength_label: str
    """Human-readable version, e.g. 'p=4.1×10⁻⁹' or 'score=0.82'."""

    direction: Literal["risk", "protective", "neutral", "unknown"] = "unknown"
    data_quality: Literal["exact", "approximate_from_paper", "inferred"] = "exact"

    @model_validator(mode="after")
    def _strength_finite(self) -> Provenance:
        if not math.isfinite(self.strength):
            raise ValueError(f"Provenance.strength must be finite, got {self.strength!r}")
        return self


class GWASSignal(BaseModel):
    """A single variant-level association from a GWAS summary statistics file."""

    rsid: str | None = None
    chr: str
    pos_hg38: int
    ref: str | None = None
    alt: str | None = None
    p_value: float
    neg_log10_p: float
    beta: float | None = None
    se: float | None = None
    eaf: float | None = None
    gwas_set: str
    """Which DecodeME GWAS set this came from: 'GWAS-1', 'GWAS-infectious', etc."""
    provenance: Provenance


class GWASLocus(BaseModel):
    """A genomic locus: lead signal + candidate causal genes."""

    locus_id: str
    chr: str
    pos_hg38_lead: int
    nearest_gene: str
    lead_signal: GWASSignal
    candidate_causal_genes: list[str] = Field(default_factory=list)
    locus_notes: str | None = None
    provenance: Provenance


class TractabilityBucket(BaseModel):
    modality: Literal["sm", "ab", "pr", "other"]
    """Modality: small molecule, antibody, PROTAC, other."""
    category: str
    """e.g. 'Clinical precedence', 'Discovery precedence', 'Predicted tractable'."""
    has_precedence: bool


class OpenTargetsResult(BaseModel):
    ensembl_id: str
    gene_symbol: str
    mecfs_association_score: float | None = None
    """Open Targets overall score for disease EFO_0001661 (0–1)."""
    tractability: list[TractabilityBucket] = Field(default_factory=list)
    known_drug_names: list[str] = Field(default_factory=list)
    provenance: Provenance


class RankedTarget(BaseModel):
    rank: int
    gene_symbol: str
    ensembl_id: str | None = None

    composite_score: float
    """
    Composite = GWAS_norm×0.6 + OT_score×0.3 + tractability×0.1.
    Fully transparent — see score_breakdown for components.
    """
    score_breakdown: dict[str, float]
    """{'gwas_norm': …, 'ot_score': …, 'tractability': …}"""

    gwas_loci: list[GWASLocus]
    gwas_sets_supporting: list[str] = Field(default_factory=list)
    open_targets: OpenTargetsResult | None = None
    suggested_validation: str | None = None
    provenance: list[Provenance]
