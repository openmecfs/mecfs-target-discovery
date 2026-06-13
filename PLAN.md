# mecfs-target-discovery — Project Plan

> An open-source toolkit that helps ME/CFS researchers decide **what to test next** —
> ranked, transparent, fully-cited candidate treatment targets, each with a suggested
> validation experiment. **Data over text. Targets over summaries.**

---

## 1. North star

Help ME/CFS (and overlapping Long COVID) researchers identify the most plausible,
**druggable** treatment targets worth testing next — and show *why*, with traceable
evidence.

Every feature decision passes one test:

> Does this make it easier to identify a **mechanism**, a **drug target**, or a
> **subgroup for a trial**? If not, don't build it.

## 2. What it is / is not

**It is:**
- An open-source **MCP server** (one server, many tools) + a thin UI.
- **Genetics-first**: anchored on the DecodeME GWAS loci as the trustworthy backbone.
- A **provenance-first** system — every claim traces to a source.

**It is not:**
- A paper summarizer or RAG chatbot.
- An omics-harmonization / data-warehouse platform (that's "infrastructure hell" for v1).
- A black-box recommender (nobody trusts or adopts those).
- A patient-facing app, symptom tracker, or "AI doctor."

## 3. Success metric

A serious ME/CFS researcher trusts the ranked target list enough to **act on it** —
and ideally runs one suggested experiment.

Success is **rigor, transparency, and reproducibility**, *not* "novel for novelty's
sake." The field already drowns in untested hypotheses; the scarce commodity is
trustworthy prioritization.

## 4. Why this niche (landscape)

- **DecodeME** (2025) gave the field its first solid causal anchor — 8 genome-wide
  significant loci (immune + nervous system; near *BTN2A2*, *OLFM4*, *RABGAP1L*, plus a
  chronic-pain locus). Genetically-supported targets succeed in trials at ~2x the base
  rate. **Almost nobody has mined these for drug targets yet.**
- **BioMapAI / DeepMECFS** (Unutmaz lab, `github.com/ohlab/BioMapAI`) is open source but
  is a specific multi-omics *classifier* + pretrained models — not a reusable
  cross-evidence target-discovery toolkit. **Wrap it, don't rebuild it.**
- **mapMECFS / searchMECFS** are data/biospecimen portals, not AI tools.
- No open, composable ME/CFS mechanism-to-target toolkit exists. **Green field.**

## 5. Architecture

**One repo → one MCP server → many tools.** Tools are *not* separate repos.

```
mecfs-target-discovery/
├── src/
│   ├── server.py                      # MCP server — registers ALL tools
│   ├── tools/                         # one file per tool (see §7)
│   ├── connectors/                    # API wrappers (Open Targets, ChEMBL, GTEx, …)
│   ├── graph/                         # the shared evidence graph (the core asset)
│   └── ui/                            # thin web UI / notebook
├── data/                             # cached source data, snapshots
├── tests/
├── PLAN.md
├── CLAUDE.md
└── README.md
```

**Two interfaces, same tools:**
1. The **MCP server** — so any researcher already using Claude/Cursor calls the tools
   inside their own workflow (this is the leverage: meet them where they are).
2. A **thin web/notebook UI** for non-technical researchers.

**Suggested stack** (developer's call — these are defaults):
- Python; official MCP SDK or FastMCP.
- `httpx` for connectors; `pydantic` for typed evidence records.
- **Evidence graph**: start simple — DuckDB + `networkx`. Move to Neo4j only if/when the
  graph itself becomes a product. Don't over-engineer the store in v1.
- Deterministic + cached (reproducibility is a feature, not a nicety).
- `pytest`; snapshot tests against known biology.

**Provenance model:** every edge in the graph carries `source`, `evidence_type`,
`direction_of_effect`, `strength/score`, and a citable reference. No edge without
provenance.

## 6. Data sources

**v1 — all public, no controlled access required:**
- **DecodeME summary statistics** — the anchor. **Openly available on OSF
  (`osf.io/rgqs3`)** — no DMTA, no institutional affiliation needed. Ships as multiple
  stratified sets: `GWAS-1`, `GWAS-2`, `GWAS-infectious`, `GWAS-non-infectious`,
  `GWAS-female`, `GWAS-male` (the infectious vs non-infectious split is a built-in
  subtype contrast worth exploiting).
  - *Prior art / reference:* `github.com/paolomaccallini-hub/DecodeME` — an R pipeline
    that replicates the preprint's fine-mapping + variant→gene (VEP/GTEx/ABC). Use to
    cross-check our (Python) implementation, not to clone.
- **Open Targets** (GraphQL API) — target–disease evidence + tractability/druggability.
- **ChEMBL** (API) — bioactive molecules, targets, existing drugs.
- **GWAS Catalog**, **eQTL Catalogue / GTEx** — variant→gene mapping & colocalization.
- **Reactome / KEGG / GO / STRING / UniProt** — pathways & molecular relationships.
- **BioMapAI / DeepMECFS** (`github.com/ohlab/BioMapAI`) — wrap as a tool; interop + credibility.

**DecodeME OSF access — VERIFIED PUBLIC (no auth/DMTA/affiliation).**
Confirmed via the OSF API (`api.osf.io/v2/nodes/rgqs3/files/osfstorage/`) returning the
full listing with no token. Node `rgqs3` root contains:
- `DecodeME Summary Statistics/` — the GWAS stats (the anchor)
- `Non-DecodeME-FMS-GWAS/` — fibromyalgia GWAS (disease comparator)
- `UK Biobank - Samms and Ponting/` — related UKB analyses
- `DecodeME Questionnaires/` + questionnaire PDF — phenotype definitions
- `DecodeME-GWAS-Analysis-Plan-v1.pdf`, `regressionResults.pdf` — methods/results

Fetch with `scripts/fetch_decodeme.py` (stdlib-only OSF downloader; `--list` to preview,
`--only "DecodeME Summary Statistics"` to grab just the stats). Writes `data/decodeme/`
+ `manifest.csv`. **Acknowledgement required** in any output: DecodeME is funded by NIHR
& MRC (grant MC_PC_20005) — see the publications policy.

**Later — controlled access, do NOT make v1 depend on these:**
- **DecodeME individual-level genotypes + biosamples** — managed access only: requires an
  eligible **institution** (academic or commercial) whose legal dept signs a DMTA with
  Edinburgh, an organisational email, funding confirmation, PPI plan, quarterly DAC review.
  An independent applicant with a personal email is **not eligible**. Only needed for
  per-participant work; v1 (summary-stats analysis) does not require it. Pursue via an
  academic collaborator as lead applicant if/when needed.
- **mapMECFS** (DUA + NIH approval) — multi-omics datasets.
- **RECOVER** Long COVID (BioData Catalyst / dbGaP).
- **UK Biobank**, **All of Us** — CFS-coded cases.

## 7. v1 tools (inside the one MCP server)

| Tool | Input | Output |
|------|-------|--------|
| `query_decodeme` | trait / locus / gene | GWAS signals + stats + provenance |
| `map_variants_to_genes` | variant(s) | candidate causal genes via colocalization (eQTL/GTEx) |
| `run_mendelian_randomization` | exposure/outcome (where instruments exist) | causal estimate + caveats |
| `score_druggability` | gene/target | Open Targets tractability + target–disease evidence |
| `lookup_drugs` | target/pathway | existing approved/investigational drugs, ongoing trials (ChEMBL + trials) |
| `score_convergence` | mechanism | **transparent** multi-stream evidence score (explicit method, NOT naive vote-counting) |
| `suggest_experiment` | candidate target/hypothesis | what to measure, in which subgroup, which assay, what would confirm/falsify |
| `query_deepmecfs` (wrap) | omics input | predictions from the existing BioMapAI models |

Each tool is independently usable **and** composable into a full
"DecodeME loci → causal genes → druggable targets → existing drugs → experiment" chain.

## 8. 12-week build plan

- **Weeks 1–2 — Scaffold + first signal.** Repo + MCP server skeleton; run
  `scripts/fetch_decodeme.py` to pull the OSF summary stats into `data/decodeme/`; load into
  DuckDB behind `query_decodeme`; Open Targets connector. Start with `GWAS-1` + the
  infectious/non-infectious split. *Milestone:* a ranked gene/target list from the real
  summary statistics (not a stub).
- **Weeks 3–4 — Causal mapping.** `map_variants_to_genes` (colocalization w/ eQTL/GTEx);
  `score_druggability`. *Milestone:* targets ranked by causal + tractability evidence.
- **Weeks 5–6 — Drugs + graph.** `lookup_drugs` (ChEMBL + ongoing trials); build the
  provenance-carrying evidence graph. *Milestone:* "target → existing drug → trial status."
- **Weeks 7–8 — Convergence + interop.** `score_convergence` (transparent method);
  wrap DeepMECFS. *Milestone:* mechanisms scored across independent evidence streams.
- **Weeks 9–10 — Experiments + UI.** `suggest_experiment`; thin UI; citations everywhere.
  *Milestone:* end-to-end demo answering a real researcher question.
- **Weeks 11–12 — Validate + ship.** Sanity-check outputs against known biology; package
  the MCP for one-line install; docs; researcher demo. *Milestone:* a researcher says
  "this is useful."

## 9. Parallel track — collaborators (start week 1, not week 12)

Computational findings are worthless without wet-lab validation. Line up **one champion**
early who will validate outputs and ideally run a suggested experiment:
- **Unutmaz lab / Jackson Laboratory** (closest to this stack; BioMapAI authors)
- **Hanson lab / Cornell**
- **Open Medicine Foundation** (Davis, Xiao) and **Solve M.E.**
- **The DecodeME team** (Ponting, Edinburgh)

Also post early in **Science for ME (s4me.info)** — methods get scrutinized hard there.

## 10. Anti-traps (read before building)

- **Don't let literature-extraction become the load-bearing layer.** Structured/genetic
  data is the backbone; paper-claim NLP is noisy enrichment added later, never the source
  of truth. (Vote-counting over biased small studies launders bias into false confidence.)
- **Don't depend on controlled-access data for v1.**
- **Don't invent subtypes** without measurable biology + a validation experiment.
- **Mind the anchor mismatch:** DecodeME genetics is disease-level, *not* PEM-specific.
  PEM is a later phenotype lens, not the v1 anchor.
- **Don't build:** generic chatbot, symptom tracker, data warehouse, custom foundation
  models, agent swarms, full omics harmonization. All year-plus traps.

## 11. Naming / repo

- **GitHub org:** `openmecfs` (the umbrella / the "toolkit"). Create the org, not under
  the personal `jspruance` account — credibility, governance, clean namespace.
- **Flagship repo:** `mecfs-target-discovery` = one installable MCP server (+ UI, data, tests).
- **Website:** openmecfs.org as the project home. Keep the flagship tool's own identity
  distinct enough to avoid confusion with **Open Medicine Foundation (OMF)** — a key ally,
  not a name to collide with.
