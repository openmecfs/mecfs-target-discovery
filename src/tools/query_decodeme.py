"""
MCP tool: query_decodeme

Returns genome-wide significant GWAS signals from the DecodeME summary statistics,
annotated with candidate causal genes.

Falls back to bundled loci.json (approximate, from published paper) if summary
statistics have not been downloaded yet — with data_quality flagged accordingly.
"""
from __future__ import annotations

from fastmcp import FastMCP

from src.connectors import decodeme as _dc
from src.models import GWASLocus, GWASSignal


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def query_decodeme(
        gene: str | None = None,
        locus_id: str | None = None,
        gwas_set: str = "GWAS-1",
        p_threshold: float = 5e-8,
        top_n: int = 50,
    ) -> dict:
        """
        Query DecodeME GWAS summary statistics for ME/CFS-associated genetic signals.

        Inputs
        ------
        gene        : filter to loci where this gene is a candidate causal gene
                      (e.g. "BTN2A2", "OLFM4")
        locus_id    : filter to a specific named locus (e.g. "6q13_BTN2A2")
        gwas_set    : which GWAS set to query — one of:
                        GWAS-1 (all cases, primary),
                        GWAS-2 (replication),
                        GWAS-infectious (cases with infectious onset),
                        GWAS-non-infectious,
                        GWAS-female, GWAS-male
        p_threshold : genome-wide significance cutoff (default 5×10⁻⁸)
        top_n       : max results to return

        Returns
        -------
        dict with keys:
          data_mode      : 'real_files' | 'bundled_loci_json'
          gwas_set       : name of GWAS set queried
          loci           : list of GWASLocus objects (serialised)
          acknowledgement: required attribution text
        """
        mode = _dc.data_mode()
        loci = _dc.load_loci_with_annotation(
            p_threshold=p_threshold,
            gwas_set=gwas_set,
        )

        # Apply filters
        if gene:
            gene_upper = gene.upper()
            loci = [
                l for l in loci
                if gene_upper in (g.upper() for g in l.candidate_causal_genes)
                or gene_upper == l.nearest_gene.upper()
            ]
        if locus_id:
            loci = [l for l in loci if l.locus_id == locus_id]

        loci = loci[:top_n]

        return {
            "data_mode": mode,
            "gwas_set": gwas_set,
            "p_threshold": p_threshold,
            "n_loci": len(loci),
            "loci": [l.model_dump() for l in loci],
            "acknowledgement": (
                "DecodeME is funded by NIHR and MRC (grant MC_PC_20005). "
                "Data: https://osf.io/rgqs3/"
            ),
            "_note": (
                "data_mode='bundled_loci_json' means summary statistics are not yet "
                "downloaded. Run: python scripts/fetch_decodeme.py "
                '--only "DecodeME Summary Statistics"'
            ) if mode == "bundled_loci_json" else None,
        }
