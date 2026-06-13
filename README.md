# mecfs-target-discovery

> Open-source toolkit that helps ME/CFS researchers decide **what to test next** —
> ranked, transparent, fully-cited candidate treatment targets, each with a suggested
> validation experiment.
>
> **Data over text. Targets over summaries.**

## What it does

Starting from the **DecodeME** GWAS findings, this toolkit maps genetic signals to the
genes and pathways most likely to be *causal*, checks which are **druggable** and whether
drugs already exist for them, and produces a ranked, provenance-backed shortlist of
candidate treatment targets — each paired with an experiment that would validate or
falsify it.

It is delivered as a single **MCP server** exposing many composable tools, so researchers
can call it directly inside the AI assistant they already use (Claude, Cursor, etc.), plus
a thin web UI for non-technical users.

## What it is not

Not a paper summarizer, RAG chatbot, data warehouse, black-box recommender, or
patient-facing app.

## Status

Early development. See [`PLAN.md`](./PLAN.md) for the full plan and
[`CLAUDE.md`](./CLAUDE.md) for developer context.

## Principles

- **Genetics-first** — anchored on DecodeME; structured databases (Open Targets, ChEMBL,
  GTEx, Reactome) as the data layer.
- **Provenance-first** — every claim traces to a source. No black boxes.
- **Reproducible** — deterministic, cached, version-pinned.
- **Composable** — each tool works standalone and chains into the full pipeline.

## Data sources

Public (v1): DecodeME summary statistics, Open Targets, ChEMBL, GWAS Catalog,
eQTL Catalogue / GTEx, Reactome / KEGG / GO / STRING / UniProt, and
[BioMapAI / DeepMECFS](https://github.com/ohlab/BioMapAI).

## Contributing

This project aims to become a community standard for ME/CFS target discovery.
Researchers, contributors, and validation partners are welcome — see `PLAN.md`.

## License

TBD (MIT recommended for maximum adoption).
