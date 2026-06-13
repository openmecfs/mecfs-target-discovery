"""
MCP tool: rank_targets

Chains DecodeME GWAS loci → Open Targets tractability → composite ranked list.

Scoring (explicit, not a black box):
  composite = GWAS_norm × 0.6 + OT_score × 0.3 + tractability × 0.1

  GWAS_norm       = min(1.0, max_neg_log10_p / 15)   [cap at p=10⁻¹⁵]
  OT_score        = Open Targets ME/CFS association score (0–1), or 0 if absent
  tractability    = 1.0 if sm Clinical Precedence
                    0.7 if sm Discovery Precedence or any ab precedence
                    0.3 if sm Predicted Tractable
                    0.0 otherwise
"""
from __future__ import annotations

import asyncio
import math

import httpx
from fastmcp import FastMCP

from src.connectors import decodeme as _dc
from src.connectors import open_targets as _ot
from src.models import GWASLocus, RankedTarget


def _tractability_score(ot_result) -> float:
    if ot_result is None:
        return 0.0
    for b in ot_result.tractability:
        if not b.has_precedence:
            continue
        cat = b.category.lower()
        if b.modality == "sm" and "clinical" in cat:
            return 1.0
        if b.modality == "sm" and "discovery" in cat:
            return 0.7
        if b.modality == "ab":
            return 0.7
    for b in ot_result.tractability:
        if b.has_precedence and b.modality == "sm" and "predict" in b.category.lower():
            return 0.3
    return 0.0


def _gwas_norm(loci: list[GWASLocus]) -> float:
    if not loci:
        return 0.0
    max_nlp = max(l.lead_signal.neg_log10_p for l in loci)
    return min(1.0, max_nlp / 15.0)


async def _rank_async(
    gwas_sets: list[str],
    p_threshold: float,
    include_ot: bool,
) -> list[RankedTarget]:
    gene_to_loci: dict[str, list[GWASLocus]] = {}
    gene_to_sets: dict[str, set[str]] = {}

    for gwas_set in gwas_sets:
        loci = _dc.load_loci_with_annotation(
            p_threshold=p_threshold,
            gwas_set=gwas_set,
        )
        for locus in loci:
            for gene in locus.candidate_causal_genes:
                gene_to_loci.setdefault(gene, []).append(locus)
                gene_to_sets.setdefault(gene, set()).add(gwas_set)

    all_genes = list(gene_to_loci.keys())
    ot_results: dict[str, object] = {}

    if include_ot and all_genes:
        async with httpx.AsyncClient() as client:
            tasks = {gene: asyncio.create_task(_ot.score_gene(gene, client=client)) for gene in all_genes}
            for gene, task in tasks.items():
                try:
                    ot_results[gene] = await task
                except Exception:
                    ot_results[gene] = None

    targets: list[RankedTarget] = []
    for gene, loci in gene_to_loci.items():
        ot = ot_results.get(gene)
        gwas_n = _gwas_norm(loci)
        ot_s = (ot.mecfs_association_score or 0.0) if ot else 0.0
        tract = _tractability_score(ot)
        composite = gwas_n * 0.6 + ot_s * 0.3 + tract * 0.1

        seen = set()
        provenance = []
        for l in loci:
            key = (l.provenance.source, l.provenance.evidence_type)
            if key not in seen:
                seen.add(key)
                provenance.append(l.provenance)
        if ot:
            provenance.append(ot.provenance)

        targets.append(
            RankedTarget(
                rank=0,  # filled after sort
                gene_symbol=gene,
                ensembl_id=ot.ensembl_id if ot else None,
                composite_score=round(composite, 4),
                score_breakdown={
                    "gwas_norm": round(gwas_n, 4),
                    "ot_score": round(ot_s, 4),
                    "tractability": round(tract, 4),
                },
                gwas_loci=loci,
                gwas_sets_supporting=sorted(gene_to_sets[gene]),
                open_targets=ot,
                provenance=provenance,
            )
        )

    targets.sort(key=lambda t: t.composite_score, reverse=True)
    for i, t in enumerate(targets, 1):
        t.rank = i
    return targets


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rank_targets(
        gwas_sets: list[str] | None = None,
        p_threshold: float = 5e-8,
        include_open_targets: bool = True,
        top_n: int = 20,
    ) -> dict:
        """
        Rank ME/CFS druggable treatment targets by combining DecodeME GWAS evidence
        with Open Targets tractability and disease-association scores.

        Inputs
        ------
        gwas_sets            : GWAS sets to aggregate (default: ['GWAS-1',
                               'GWAS-infectious', 'GWAS-non-infectious'])
        p_threshold          : genome-wide significance cutoff (default 5×10⁻⁸)
        include_open_targets : whether to enrich with OT tractability (default True)
        top_n                : how many ranked targets to return

        Returns
        -------
        dict with:
          ranked_targets : list of RankedTarget objects
          scoring_method : plain-English description of the composite score formula
          data_mode      : 'real_files' | 'bundled_loci_json'
          acknowledgement: required attribution text

        Scoring formula (transparent):
          composite = GWAS_norm×0.6 + OT_score×0.3 + tractability×0.1
          GWAS_norm = min(1, max_neg_log10_p / 15)
          OT_score  = Open Targets ME/CFS association (0–1)
          tractability: 1.0 sm-clinical, 0.7 sm-discovery/antibody, 0.3 sm-predicted, 0 otherwise
        """
        if gwas_sets is None:
            gwas_sets = ["GWAS-1", "GWAS-infectious", "GWAS-non-infectious"]

        targets = asyncio.run(
            _rank_async(gwas_sets, p_threshold, include_ot=include_open_targets)
        )
        targets = targets[:top_n]

        return {
            "data_mode": _dc.data_mode(),
            "gwas_sets_queried": gwas_sets,
            "p_threshold": p_threshold,
            "n_targets": len(targets),
            "ranked_targets": [t.model_dump() for t in targets],
            "scoring_method": (
                "composite = GWAS_norm×0.6 + OT_score×0.3 + tractability×0.1  |  "
                "GWAS_norm = min(1, max_neg_log10_p/15)  |  "
                "OT_score = Open Targets ME/CFS EFO_0001661 score  |  "
                "tractability: 1.0=sm-clinical, 0.7=sm-discovery/ab, 0.3=sm-predicted"
            ),
            "acknowledgement": (
                "DecodeME (NIHR/MRC MC_PC_20005) — https://osf.io/rgqs3/ ; "
                "Open Targets Platform — https://platform.opentargets.org"
            ),
        }
