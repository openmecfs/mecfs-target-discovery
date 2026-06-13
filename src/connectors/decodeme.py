"""
DuckDB-backed interface to DecodeME GWAS summary statistics.

Primary mode  — downloaded files present in data/decodeme/:
  Queries gzipped summary-stats TSVs directly via DuckDB with column auto-detection.

Fallback mode — files not yet downloaded:
  Reads the bundled data/decodeme/loci.json (approximate stats from published paper).
  This lets the server start and return provenance-tagged approximate results while
  the user runs `python scripts/fetch_decodeme.py --only "DecodeME Summary Statistics"`.

Column auto-detection handles BOLT-LMM, REGENIE, METAL, and standard GWAS formats.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterator

import duckdb

from src.models import GWASLocus, GWASSignal, Provenance

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "decodeme"
LOCI_JSON = DATA_DIR / "loci.json"

_DECODEME_PROVENANCE = dict(
    source="DecodeME_GWAS_2025",
    evidence_type="GWAS",
    url="https://osf.io/rgqs3/",
    # Initial findings preprint (medRxiv, Aug 2025). Update to the peer-reviewed DOI on publication.
    doi="10.1101/2025.08.06.25333109",
    direction="risk",
)

# Canonical name → list of aliases (lower-cased)
_COL_ALIASES: dict[str, list[str]] = {
    "chr":    ["chr", "chrom", "#chrom", "chromosome"],
    "pos":    ["pos", "bp", "genpos", "position", "base_pair_location"],
    "rsid":   ["snp", "rsid", "id", "markerid", "variant_id"],
    "ref":    ["ref", "a0", "allele0", "a2", "non_effect_allele"],
    "alt":    ["alt", "a1", "allele1", "effect_allele"],
    "beta":   ["beta", "effect", "or"],
    "se":     ["se", "stderr", "standard_error"],
    "p":      ["p", "pval", "pvalue", "p_value", "p_bolt_lmm_inf", "p_bolt_lmm"],
    "log10p": ["log10p", "log10_p", "neg_log10_p", "mlog10p"],
    "eaf":    ["a1freq", "eaf", "af", "effect_allele_frequency", "freq1"],
}


def _detect_columns(header: list[str]) -> dict[str, str]:
    """
    Map canonical column names to actual column names in the file.
    Returns a dict like {'chr': 'CHR', 'pos': 'BP', 'p': 'P_BOLT_LMM_INF', ...}.
    Raises ValueError if required columns (chr, pos, p) are missing.
    """
    lower_to_actual = {c.lower(): c for c in header}
    mapping: dict[str, str] = {}
    for canonical, aliases in _COL_ALIASES.items():
        for alias in aliases:
            if alias in lower_to_actual:
                mapping[canonical] = lower_to_actual[alias]
                break
    missing = {"chr", "pos", "p"} - set(mapping)
    if missing:
        raise ValueError(f"Cannot find required columns {missing} in header: {header}")
    return mapping


def _discover_gwas_files() -> dict[str, Path]:
    """
    Scan data/decodeme/ for GWAS summary-statistics files.
    Returns {gwas_set_name: path}, e.g. {'GWAS-1': Path(...), 'GWAS-infectious': Path(...)}.
    """
    stats_dir = DATA_DIR / "DecodeME Summary Statistics"
    files: dict[str, Path] = {}
    if stats_dir.is_dir():
        for f in stats_dir.iterdir():
            if f.suffix in (".gz", ".bgz", ".tsv", ".txt", ".csv") and not f.name.startswith("."):
                # Infer set name from filename, e.g. "GWAS-1.txt.gz" → "GWAS-1"
                stem = f.name.split(".")[0]
                files[stem] = f
    return files


def _p_from_row(row: dict, col_map: dict[str, str]) -> float:
    """Extract p-value from a row, handling both raw-p and -log10(p) columns."""
    if "p" in col_map:
        return float(row[col_map["p"]])
    elif "log10p" in col_map:
        log10p = float(row[col_map["log10p"]])
        return 10 ** (-log10p)
    raise KeyError("No p-value column found")


def _neg_log10(p: float) -> float:
    if p <= 0:
        return float("inf")
    return -math.log10(p)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query_signals(
    *,
    p_threshold: float = 5e-8,
    gwas_set: str = "GWAS-1",
    chr_: str | None = None,
    pos_start: int | None = None,
    pos_end: int | None = None,
    limit: int = 500,
) -> list[GWASSignal]:
    """
    Return GWAS signals below p_threshold from the given GWAS set.

    Falls back to the bundled loci.json if no summary-stats file is found.
    """
    gwas_files = _discover_gwas_files()

    if gwas_set in gwas_files:
        return _query_from_file(
            gwas_files[gwas_set],
            gwas_set=gwas_set,
            p_threshold=p_threshold,
            chr_=chr_,
            pos_start=pos_start,
            pos_end=pos_end,
            limit=limit,
        )
    else:
        return _query_from_bundled_json(
            p_threshold=p_threshold,
            gwas_set=gwas_set,
            chr_=chr_,
            pos_start=pos_start,
            pos_end=pos_end,
        )


def _query_from_file(
    path: Path,
    *,
    gwas_set: str,
    p_threshold: float,
    chr_: str | None,
    pos_start: int | None,
    pos_end: int | None,
    limit: int,
) -> list[GWASSignal]:
    con = duckdb.connect(":memory:")
    # Peek at the header to detect columns
    peek = con.execute(
        f"SELECT * FROM read_csv_auto('{path}', sample_size=5) LIMIT 0"
    ).description
    header = [d[0] for d in peek]
    col_map = _detect_columns(header)

    # Build SELECT list with canonical aliases
    def sel(canonical: str, alias: str) -> str:
        actual = col_map.get(canonical)
        return f'"{actual}" AS {alias}' if actual else f"NULL AS {alias}"

    select_parts = [
        sel("chr", "chr"),
        sel("pos", "pos"),
        sel("rsid", "rsid"),
        sel("ref", "ref"),
        sel("alt", "alt"),
        sel("beta", "beta"),
        sel("se", "se"),
        sel("eaf", "eaf"),
    ]
    # P-value handling
    if "p" in col_map:
        select_parts.append(f'"{col_map["p"]}" AS p_value')
        p_filter_expr = f'"{col_map["p"]}" <= {p_threshold}'
    elif "log10p" in col_map:
        log_thresh = -math.log10(p_threshold)
        select_parts.append(f'POWER(10, -"{col_map["log10p"]}") AS p_value')
        p_filter_expr = f'"{col_map["log10p"]}" >= {log_thresh}'
    else:
        raise ValueError("No p-value column")

    where_clauses = [p_filter_expr]
    if chr_ is not None:
        where_clauses.append(f'"{col_map["chr"]}" = \'{chr_}\'')
    if pos_start is not None and "pos" in col_map:
        where_clauses.append(f'"{col_map["pos"]}" >= {pos_start}')
    if pos_end is not None and "pos" in col_map:
        where_clauses.append(f'"{col_map["pos"]}" <= {pos_end}')

    sql = (
        f"SELECT {', '.join(select_parts)} "
        f"FROM read_csv_auto('{path}') "
        f"WHERE {' AND '.join(where_clauses)} "
        f"ORDER BY p_value ASC LIMIT {limit}"
    )
    rows = con.execute(sql).fetchall()
    col_names = ["chr", "pos", "rsid", "ref", "alt", "beta", "se", "eaf", "p_value"]
    results = []
    for row in rows:
        d = dict(zip(col_names, row))
        p = float(d["p_value"]) if d["p_value"] is not None else float("nan")
        prov = Provenance(
            **_DECODEME_PROVENANCE,
            strength=_neg_log10(p),
            strength_label=f"p={p:.2e}",
            data_quality="exact",
        )
        results.append(
            GWASSignal(
                rsid=d["rsid"],
                chr=str(d["chr"]).lstrip("chr"),
                pos_hg38=int(d["pos"]),
                ref=d["ref"],
                alt=d["alt"],
                p_value=p,
                neg_log10_p=_neg_log10(p),
                beta=float(d["beta"]) if d["beta"] is not None else None,
                se=float(d["se"]) if d["se"] is not None else None,
                eaf=float(d["eaf"]) if d["eaf"] is not None else None,
                gwas_set=gwas_set,
                provenance=prov,
            )
        )
    return results


def _query_from_bundled_json(
    *,
    p_threshold: float,
    gwas_set: str,
    chr_: str | None,
    pos_start: int | None = None,
    pos_end: int | None = None,
) -> list[GWASSignal]:
    """Fall back to the bundled published loci when summary stats haven't been downloaded."""
    if not LOCI_JSON.exists():
        return []

    raw = json.loads(LOCI_JSON.read_text(encoding="utf-8"))
    signals: list[GWASSignal] = []
    for locus in raw.get("loci", []):
        p = locus.get("p_value")
        if p is None or p > p_threshold:
            continue
        if chr_ is not None and str(locus.get("chr")) != chr_.lstrip("chr"):
            continue
        locus_pos = locus.get("pos_hg38")
        if pos_start is not None and locus_pos is not None and locus_pos < pos_start:
            continue
        if pos_end is not None and locus_pos is not None and locus_pos > pos_end:
            continue
        prov = Provenance(
            **_DECODEME_PROVENANCE,
            strength=_neg_log10(p),
            strength_label=f"p≈{p:.1e}",
            data_quality="approximate_from_paper",
        )
        signals.append(
            GWASSignal(
                rsid=locus.get("rsid"),
                chr=str(locus["chr"]),
                pos_hg38=locus["pos_hg38"],
                ref=locus.get("ref"),
                alt=locus.get("alt"),
                p_value=p,
                neg_log10_p=_neg_log10(p),
                beta=locus.get("beta"),
                se=locus.get("se"),
                eaf=locus.get("eaf"),
                gwas_set=gwas_set + "_approx",
                provenance=prov,
            )
        )
    return sorted(signals, key=lambda s: s.p_value)


def load_loci_with_annotation(
    *,
    p_threshold: float = 5e-8,
    gwas_set: str = "GWAS-1",
    window_bp: int = 500_000,
) -> list[GWASLocus]:
    """
    Return GWASLoci: clusters of signals from the bundled annotation + matched signals.
    Uses loci.json as the annotation backbone and fills in signal data from query_signals.
    """
    if not LOCI_JSON.exists():
        return []

    raw = json.loads(LOCI_JSON.read_text(encoding="utf-8"))
    loci: list[GWASLocus] = []

    for locus_def in raw.get("loci", []):
        chr_ = str(locus_def["chr"])
        center = locus_def["pos_hg38"]
        start = center - window_bp
        end = center + window_bp

        signals = query_signals(
            p_threshold=p_threshold,
            gwas_set=gwas_set,
            chr_=chr_,
            pos_start=start,
            pos_end=end,
            limit=10,
        )

        if not signals:
            # No real signal found in window; create from bundled data if p passes threshold
            bundled_p = locus_def.get("p_value", 1.0)
            if bundled_p > p_threshold:
                continue
            prov = Provenance(
                **_DECODEME_PROVENANCE,
                strength=_neg_log10(bundled_p),
                strength_label=f"p≈{bundled_p:.1e}",
                data_quality="approximate_from_paper",
            )
            lead = GWASSignal(
                rsid=locus_def.get("rsid"),
                chr=chr_,
                pos_hg38=center,
                p_value=bundled_p,
                neg_log10_p=_neg_log10(bundled_p),
                beta=locus_def.get("beta"),
                se=locus_def.get("se"),
                eaf=locus_def.get("eaf"),
                gwas_set=gwas_set + "_approx",
                provenance=prov,
            )
        else:
            lead = signals[0]

        locus_prov = Provenance(
            **_DECODEME_PROVENANCE,
            strength=lead.neg_log10_p,
            strength_label=lead.provenance.strength_label,
            data_quality=lead.provenance.data_quality,
        )
        loci.append(
            GWASLocus(
                locus_id=locus_def["locus_id"],
                chr=chr_,
                pos_hg38_lead=lead.pos_hg38,
                nearest_gene=locus_def["nearest_gene"],
                lead_signal=lead,
                candidate_causal_genes=locus_def.get("candidate_causal_genes", []),
                locus_notes=locus_def.get("locus_notes"),
                provenance=locus_prov,
            )
        )

    return sorted(loci, key=lambda l: l.lead_signal.p_value)


def data_mode() -> str:
    """Report which data mode is active ('real_files' or 'bundled_loci_json')."""
    files = _discover_gwas_files()
    return "real_files" if files else "bundled_loci_json"
