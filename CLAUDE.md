# CLAUDE.md — project context for Claude Code

This file is auto-loaded by Claude Code. It carries the context from the planning phase
so every coding session stays aligned. Full reasoning lives in `PLAN.md` — read it first.

## What we're building

`mecfs-target-discovery`: an open-source **MCP server (one server, many tools)** + thin UI
that helps ME/CFS researchers identify the most plausible **druggable treatment targets**
to test next. Output = ranked, transparent, cited candidate targets, each with a suggested
validation experiment.

**One-line ethos:** Data over text. Targets over summaries.

## Core principles (do not violate)

1. **Genetics-first.** DecodeME GWAS loci are the trustworthy backbone. Structured
   databases (Open Targets, ChEMBL, GTEx, Reactome) are the data layer.
2. **Provenance-first.** Every claim/edge traces to a source with evidence type + strength.
   No black boxes. No edge without provenance.
3. **Reproducible + deterministic.** Cache source data; pin versions; snapshot-test.
4. **Literature extraction is enrichment, never the source of truth.** No naive
   vote-counting over papers.
5. **Composable.** Each tool works standalone *and* chains into the full pipeline.

## Architecture

One repo → one MCP server → many tools. Tools are files under `src/tools/`, registered in
`src/server.py`. See `PLAN.md §5` for the directory layout and `§7` for the tool list.

- MCP SDK / FastMCP (Python)
- `httpx` connectors in `src/connectors/`; `pydantic` typed evidence records
- Evidence graph: DuckDB + `networkx` to start (Neo4j only if it becomes a product)
- `pytest`, including snapshot tests against known biology

## Data sources

v1 (public): DecodeME summary stats, Open Targets (GraphQL), ChEMBL, GWAS Catalog,
eQTL Catalogue/GTEx, Reactome/KEGG/GO/STRING/UniProt, and `github.com/ohlab/BioMapAI`
(wrap as a tool). Do NOT make v1 depend on controlled-access data (mapMECFS, RECOVER,
UK Biobank) — those come later.

## Current status

- ✅ Plan finalized (`PLAN.md`).
- ✅ `openmecfs` GitHub org + `mecfs-target-discovery` repo created.
- ✅ DecodeME data access resolved: **summary statistics are openly available on OSF
  (node `rgqs3`), no DMTA/affiliation needed.** Downloader: `scripts/fetch_decodeme.py`.
  (Individual-level genotypes/samples remain controlled — not needed for v1.)
- ✅ **Weeks 1–2 scaffold complete:**
  - `pyproject.toml` + package installed (`pip install -e ".[dev]"`)
  - `src/models.py` — provenance-carrying Pydantic models (`Provenance`, `GWASLocus`,
    `GWASSignal`, `OpenTargetsResult`, `RankedTarget`)
  - `src/connectors/decodeme.py` — DuckDB-backed GWAS loader; falls back gracefully to
    bundled `data/decodeme/loci.json` when summary stats not yet downloaded
  - `src/connectors/open_targets.py` — async GraphQL connector with file cache
  - `src/tools/query_decodeme.py` + `src/tools/rank_targets.py` — MCP tools registered
  - `src/server.py` — FastMCP server entry point
  - `tests/` — 16 tests, all passing
- ⬜ **Next:**
  1. Download real summary stats:
     ```
     python scripts/fetch_decodeme.py --only "DecodeME Summary Statistics"
     ```
  2. Smoke-test `rank_targets` against real data (DuckDB path + Open Targets live query).
  3. Weeks 3–4: `map_variants_to_genes` (eQTL colocalization) + `score_druggability`.

## How to work in this repo

- Start a session with: "Read PLAN.md and CLAUDE.md, then let's continue from Current status."
- Use plan mode for architecture decisions before writing code.
- Keep `Current status` above up to date as milestones complete.

## Don't build (anti-traps)

Generic chatbot, symptom tracker, data warehouse, custom foundation models, agent swarms,
full omics harmonization, patient-facing features, or subtypes without measurable biology +
a validation experiment. See `PLAN.md §10`.
