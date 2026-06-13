"""
Open Targets Platform GraphQL connector.

Queries target tractability and ME/CFS disease-association scores.
Results are cached under data/cache/open_targets/ as JSON files.

ME/CFS EFO code: EFO_0001661 (chronic fatigue syndrome)
  Also try EFO_0007540 (myalgic encephalomyelitis/chronic fatigue syndrome) if needed.

GraphQL endpoint: https://api.platform.opentargets.org/api/v4/graphql
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import httpx

from src.models import OpenTargetsResult, Provenance, TractabilityBucket

_GQL_ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"
_MECFS_EFO = "EFO_0001661"
_OT_VERSION = "24.09"  # update when bumping

PROJECT_ROOT = Path(__file__).parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "open_targets"

_OT_PROVENANCE = dict(
    source=f"OpenTargets_v{_OT_VERSION}",
    evidence_type="database",
    url="https://platform.opentargets.org",
    direction="neutral",
    data_quality="exact",
)

# Minimal, schema-verified query: tractability only.
# TODO: reintroduce known drugs + ME/CFS disease-association once their current
# OT v4 schema shape is confirmed (knownDrugs and associatedDiseases args changed).
# Disease association is available via get_mecfs_associations() (disease->targets path).
_TRACTABILITY_QUERY = """
query GeneInfo($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    tractability {
      label
      modality
      value
    }
  }
}
"""

_SEARCH_QUERY = """
query SearchTarget($symbol: String!) {
  search(queryString: $symbol, entityNames: ["target"]) {
    hits {
      id
      name
      entity
    }
  }
}
"""

_MECFS_TARGETS_QUERY = """
query MECFSAssociatedTargets($efoId: String!, $size: Int!) {
  disease(efoId: $efoId) {
    id
    name
    associatedTargets(page: { index: 0, size: $size }) {
      rows {
        target {
          id
          approvedSymbol
        }
        score
        datatypeScores {
          id
          score
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _cache_read(key: str) -> dict | None:
    p = _cache_path(key)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _cache_write(key: str, data: dict) -> None:
    _cache_path(key).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# GraphQL client
# ---------------------------------------------------------------------------

async def _gql(client: httpx.AsyncClient, query: str, variables: dict) -> dict:
    resp = await client.post(
        _GQL_ENDPOINT,
        json={"query": query, "variables": variables},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code >= 400:
        # Surface OT's actual error body — it names the offending field/argument.
        raise ValueError(
            f"Open Targets HTTP {resp.status_code}: {resp.text[:1500]}"
        )
    body = resp.json()
    if "errors" in body:
        raise ValueError(f"Open Targets GraphQL error: {body['errors']}")
    return body.get("data", {})


# ---------------------------------------------------------------------------
# Symbol → Ensembl ID resolution
# ---------------------------------------------------------------------------

async def resolve_ensembl_id(client: httpx.AsyncClient, symbol: str) -> str | None:
    """Look up Ensembl ID for a gene symbol via Open Targets search."""
    cache_key = f"ensembl_{symbol.upper()}"
    if cached := _cache_read(cache_key):
        return cached.get("ensembl_id")

    data = await _gql(client, _SEARCH_QUERY, {"symbol": symbol})
    hits = data.get("search", {}).get("hits", [])
    for hit in hits:
        if hit.get("entity") == "target" and hit.get("name", "").upper() == symbol.upper():
            ensembl_id = hit["id"]
            _cache_write(cache_key, {"ensembl_id": ensembl_id})
            return ensembl_id
    return None


# ---------------------------------------------------------------------------
# Per-gene tractability + ME/CFS score
# ---------------------------------------------------------------------------

def _parse_tractability(buckets: list[dict]) -> list[TractabilityBucket]:
    result: list[TractabilityBucket] = []
    for b in buckets:
        modality_raw = (
            (b.get("modality") or "other").strip().lower().replace(" ", "").replace("_", "")
        )
        if modality_raw in ("sm", "smallmolecule"):
            modality = "sm"
        elif modality_raw in ("ab", "antibody"):
            modality = "ab"
        elif modality_raw in ("pr", "protac"):
            modality = "pr"
        else:
            modality = "other"
        result.append(
            TractabilityBucket(
                modality=modality,
                category=b.get("label", "unknown"),
                has_precedence=bool(b.get("value")),
            )
        )
    return result


async def get_gene_info(client: httpx.AsyncClient, ensembl_id: str) -> dict[str, Any]:
    """Return raw Open Targets data for a gene (cached)."""
    cache_key = f"gene_{ensembl_id}"
    if cached := _cache_read(cache_key):
        return cached

    data = await _gql(client, _TRACTABILITY_QUERY, {"ensemblId": ensembl_id})
    target_data = data.get("target") or {}
    _cache_write(cache_key, target_data)
    return target_data


async def score_gene(
    symbol: str,
    *,
    client: httpx.AsyncClient | None = None,
    ensembl_id: str | None = None,
) -> OpenTargetsResult | None:
    """
    Return OpenTargetsResult for a gene symbol (or ensembl_id if known).
    Returns None if the gene cannot be resolved.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()

    try:
        if ensembl_id is None:
            ensembl_id = await resolve_ensembl_id(client, symbol)
        if ensembl_id is None:
            return None

        raw = await get_gene_info(client, ensembl_id)
        if not raw:
            return None

        tractability = _parse_tractability(raw.get("tractability") or [])

        # ME/CFS association score
        mecfs_score: float | None = None
        assoc_rows = (raw.get("associatedDiseases") or {}).get("rows") or []
        if assoc_rows:
            mecfs_score = float(assoc_rows[0]["score"])

        # Known drugs
        known_drugs: list[str] = []
        for row in (raw.get("knownDrugs") or {}).get("rows") or []:
            drug_name = row.get("drug", {}).get("name")
            if drug_name:
                known_drugs.append(drug_name)

        score_val = mecfs_score if mecfs_score is not None else 0.0
        prov = Provenance(
            **_OT_PROVENANCE,
            strength=score_val,
            strength_label=f"OT_score={score_val:.3f}",
        )
        return OpenTargetsResult(
            ensembl_id=ensembl_id,
            gene_symbol=raw.get("approvedSymbol") or symbol,
            mecfs_association_score=mecfs_score,
            tractability=tractability,
            known_drug_names=list(dict.fromkeys(known_drugs)),
            provenance=prov,
        )
    finally:
        if own_client:
            await client.aclose()


# ---------------------------------------------------------------------------
# Batch disease associations (all ME/CFS targets from OT)
# ---------------------------------------------------------------------------

async def get_mecfs_associations(
    *,
    size: int = 100,
    client: httpx.AsyncClient | None = None,
) -> dict[str, float]:
    """
    Return {ensembl_id: ot_score} for the top `size` ME/CFS associated targets.
    Cached. Used by rank_targets to pre-fill OT scores efficiently.
    """
    cache_key = f"mecfs_associations_{_MECFS_EFO}_{size}"
    if cached := _cache_read(cache_key):
        return cached

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()

    try:
        data = await _gql(client, _MECFS_TARGETS_QUERY, {"efoId": _MECFS_EFO, "size": size})
        rows = (data.get("disease") or {}).get("associatedTargets", {}).get("rows") or []
        result = {row["target"]["id"]: float(row["score"]) for row in rows}
        _cache_write(cache_key, result)
        return result
    finally:
        if own_client:
            await client.aclose()
