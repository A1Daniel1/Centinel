# ODD Task Plan — C4 Architecture Model, Deployment and HA/Cost Validation

- **Feature ID:** `arquitectura-c4`
- **Repo:** `C:\Users\User\Dev\DigitalTransformationProject`
- **Created:** 2026-09-19
- **Route:** direct inline (orchestrator authors the sources; each diagram is verified by rendering and visual inspection)
- **Parent feature:** `executive-review-II` (`odd/tasks/executive-review-II.md`)
- **TDD:** not applicable (architecture diagrams + estimates, no code under test)
- **RDD:** off (decided by default) — no review gate triggered
- **Commit policy:** no commits (not requested)

## Why this exists

The user reviewed the previous diagrams and rejected them as not being real C4. The rejection was
**substantively correct**, and the diagnosis matters more than the drawing:

| Defect | Evidence |
| --- | --- |
| **Level 3 was invalid C4** | The old "Component Diagram" mixed the pipeline's 6 components with nodes that are *not components of that container* (PostGIS, Object Storage, Broker, Observability). A real L3 shows the internals of **one** container. |
| **No Level 4** | No code-level diagram existed. |
| **No deployment diagram** | Absent entirely. |
| **Layout was a forced grid** | Coordinates were hand-shimmed to guarantee zero label overlap. That is an org chart, not a C4 layout. |
| **HA and scalability invisible** | No replicas, no load balancer, no multi-AZ, no autoscaling, no failover. The architecture *claimed* "cloud-native scalable" without showing it. |
| **Costs never validated** | The FinOps table, the Terraform spec and the actual topology disagreed with each other. |

The real ask is architectural, not cosmetic: **design HA and scalability and make them visible, then
validate what that costs.**

## Toolchain decision (user-approved)

**PlantUML + C4-PlantUML.** Chosen by the user over extending the bespoke renderer.

Validated before authoring anything:

- `plantuml.jar` **1.2026.8** (28.5 MB) — from the GitHub release, `plantuml-1.2026.8.jar`.
- **Graphviz is NOT required.** PlantUML's bundled engine renders C4 (person icons, `«person»` /
  `«system»` / `«external_system»` stereotypes, C4 palette) with no `dot` binary present. This removed
  the ~50 MB Graphviz download the plan had budgeted for.
- Location: `C:\Users\User\AppData\Local\Temp\opencode\puml\plantuml.jar` (outside the repo).
- **Trap encountered:** Maven Central's `maven-metadata.xml` `release` for `net.sourceforge.plantuml:plantuml`
  resolves to **`8059`, a 2017 build** that predates the bundled C4 stdlib. Always take PlantUML from the
  GitHub release, not Maven Central's `release` field.

## Deliverable — new folder `docs/deliverable-2/diagramas-c4/`

| ID | Artifact | Purpose |
| --- | --- | --- |
| T1 | `01-nivel1-contexto.puml` | C4 L1 — system scope, actors, external systems |
| T2 | `02-nivel2-contenedores.puml` | C4 L2 — containers, with replica counts and scaling policy |
| T3 | `03-nivel3-componentes-inferencia.puml` | C4 L3 — components **inside the Multi-Label Inference Service only** |
| T4 | `04-nivel4-codigo.puml` | C4 L4 — classes/interfaces of the inference component |
| T5 | `05-despliegue-ha.puml` | Deployment — cloud → region → VPC → 3 AZ → subnets → cluster → workload, plus DR region |
| T6 | `README.md` | Architecture decisions, HA/scalability strategy, SLOs/RPO/RTO, and the **validated cost model** |
| T7 | rendered `.png` + `.svg` per diagram | Consumable output |

## Architecture decisions to make visible (the substance)

**High availability**
- 3 availability zones for every tier; pod anti-affinity so replicas do not co-locate.
- Stateless services scaled horizontally behind an ingress/load balancer with health checks.
- Alert database: multi-AZ primary + standby with automated failover, plus read replicas for query scaling.
- Object storage: versioning + cross-region replication.
- Message broker: upgrade from single-instance Redis Streams to a **replicated, partitioned log** (replication factor 3, one broker per AZ) — the honest HA choice for bursty, replayable ingestion.
- GPU inference: multi-AZ node groups, on-demand baseline plus spot burst, autoscaled on queue depth, with degradation defined as bounded alert freshness.
- Explicit **RPO/RTO** targets, including cross-region DR.

**Scalability**
- Per-service autoscaling on the signal that actually matters: queue depth for pipeline stages, RPS/latency for the API, GPU utilisation for inference.
- Partitioning: scenes keyed by tile/region so consumers scale in parallel; PostGIS partitioned by time and territory; object storage lifecycle tiering.
- Burst absorption for satellite overpass windows.

**Cost validation**
- Re-derive the FinOps model from the *actual* HA topology (replica counts, multi-AZ databases, per-AZ NAT/ALB, broker cluster, GPU nodes).
- Report the **HA premium**: pilot (single-AZ, minimal) vs production (multi-AZ, HA) and the delta.
- Flag every number that contradicts the existing `docs/deliverable-2/executive-review-II.md`.

## Constraints

- Sources in `docs/deliverable-2/diagramas-c4/` only. Do not modify the Markdown deliverable, the XML, or `main.tex` in this phase.
- Spanish prose and labels; technology names and identifiers stay English.
- Honest labelling: any figure that is an estimate is marked as one.

## Checklist

- [ ] **T1** Context diagram rendered and visually verified
- [ ] **T2** Container diagram rendered and visually verified, HA annotations present
- [ ] **T3** Component diagram for ONE container (not a mixed view)
- [ ] **T4** Code diagram
- [ ] **T5** Deployment diagram with 3 AZ + DR
- [ ] **T6** README with HA/scalability decisions, SLOs, and the validated cost model
- [ ] **T7** Every diagram rendered to PNG **and** SVG, with zero PlantUML syntax errors

## Progress log

| Date | Event |
| --- | --- |
| 2026-09-19 | Feature opened after the user rejected the previous diagrams as non-C4. Toolchain validated: PlantUML 1.2026.8, no Graphviz needed. |
| 2026-09-19 | Authoring L1/L2/L3 first to validate C4 syntax before investing in L4 and the deployment diagram. |

## Outcome

**Status: complete.** New folder `docs/deliverable-2/diagramas-c4/` with 5 C4 diagrams (`.puml` source + `.png` + `.svg` each) and a README carrying the HA/scalability strategy and the cost validation.

### What was produced

| File | Level |
| --- | --- |
| `01-nivel1-contexto` | C4 L1 — scope, 4 actors, 4 external systems |
| `02-nivel2-contenedores` | C4 L2 — 13 containers, each annotated with replicas and autoscaling policy |
| `03-nivel3-componentes-inferencia` | C4 L3 — 11 components **inside one container** (Multi-Label Inference Service), externals outside the boundary |
| `04-nivel4-codigo` | C4 L4 — classes/interfaces, with the abstract classifier as the substitution point |
| `05-despliegue-ha` | Deployment — AWS → region → VPC → 3 AZs → workloads, plus DR region |
| `README.md` | HA strategy, SLO/RPO/RTO, scalability, cost validation, flagged inconsistencies |

### Toolchain findings

- PlantUML **1.2026.8** from the GitHub release. **Graphviz is not required** — the bundled engine renders C4 (icons, stereotypes, palette) without a `dot` binary, which removed a ~50 MB dependency from the plan.
- Maven Central's `maven-metadata.xml` `release` for PlantUML resolves to **`8059`, a 2017 build** without the bundled C4 library. Always take it from GitHub releases.

### Defects found and fixed during this phase

1. **`System_Ext_Container` does not exist** in C4-PlantUML → replaced with `Container_Ext`.
2. **File corruption — encoding.** A patch loop using `Get-Content -Raw` + `Set-Content -Encoding UTF8` in PowerShell 5.1 read UTF-8 bytes as CP1252 and rewrote them mangled, turning "Detección" into "DetecciÃ³n" in levels 1–3. Fixed by rewriting the three sources with the `write` tool. **Lesson: never round-trip non-ASCII UTF-8 through PowerShell 5.1 text cmdlets; use the file-writing tool or .NET byte APIs.**
3. **`legend` blocks do not render reliably** in these C4 diagrams (rendered as an unreadable column in the deployment diagram, and not at all in others) → explanatory prose moved to the README; only local `note`s are used, which render correctly.
4. **Deployment diagram, first attempt was wrong:** the PLANTUML legend collapsed, the 3 AZs cascaded diagonally instead of reading as parallel, PostGIS appeared outside the AZ boundary, and **S3 was nested inside the VPC** (semantically wrong — S3 is a regional service).
   - Root cause of the AZ cascade: the DB replication chain `dbA→dbB→dbC` inside the AZs forced Graphviz ranks. `together { }` did **not** fix it.
   - Fix: move the data tier out of the AZs into its own `Capa de datos gestionada` cluster (also semantically more correct — RDS Multi-AZ is a managed regional service). The three AZs then rendered in parallel, which is the whole HA message.
5. **`Deployment_Node` wrappers around single containers** added nesting without information → collapsed into `Container` entries with the infrastructure detail in the technology field.

### Cost validation — the substantive finding

**The existing cost table does not pay for the HA the architecture claims.** Production infrastructure needs **≈ +1,921 USD/month (+38 %)** over the ~5,051 declared, driven by:

| Item | Δ USD/mes |
| --- | --- |
| Read replicas ×2 (promised in §5.1, never costed) | +423 |
| Event bus → replicated log (3 MSK brokers, RF=3, one per AZ) | +290 |
| NAT Gateway per AZ ×3 | +131 |
| GPU baseline in a second AZ | +734 |
| EKS control plane (line was absent) | +73 |
| DR: warm cluster + snapshots + selective CRR | +270 |

Two of these are explicit business decisions rather than technical ones: **GPU HA** means either paying +734 or accepting bounded degradation of alert freshness during a zone failure; and replicating the full 60 TB archive cross-region would cost ≈ +1,380/month, so the design replicates derived products and a subset of scenes instead.

Also concluded: **the pilot does not need HA** (≈ +1,161/month for no benefit to the classification hypothesis), which means **the pilot does not validate HA** — that must be stated rather than implied, and validated in staging with failover drills.

Five inconsistencies in `executive-review-II.md` were recorded in the README's §6 for reconciliation. **The main deliverable was not modified in this phase** (out of the authorized scope).

### Verification performed

Every diagram was rendered and then **inspected visually by the orchestrator**, which is what caught the encoding corruption, the AZ cascade, the misplaced S3 and the unrendered legends — none of which a build exit code reveals. Render exits 0 for all five; PNG + SVG exist for each.

### Scope and housekeeping

- New files only inside `docs/deliverable-2/diagramas-c4/`.
- `executive-review-II.md` (1534 lines), the XML (35,470 bytes), `main.tex` and `README.md` untouched.
- `plantuml.jar` lives in the OS temp directory, not in the repo. No git commands were run; nothing was committed.

---

## Phase 5 — Reconciling the deliverable with the new model (T8)

**Requested by the user: "si porfa"** to reconciling `executive-review-II.md` with the new C4 model and the validated costs.

### Backup taken first

`docs/` is **entirely untracked in git**, so there was no version-control safety net. Both edited files were copied to the OS temp directory before any edit:
`executive-review-II.md.bak` (96,263 bytes) and `executive-review-II.tex.bak` (104,756 bytes).

### Converter change

`build/md2tex.py` mapped each ```mermaid block to a figure positionally and could not embed images. Added a sibling `figure` fenced-block case (content: `path | caption`) and repointed `FIGURE_NAMES` at the new model. `\graphicspath` extended with `docs/deliverable-2/diagramas-c4/`. The five diagrams are now rendered to **vector PDF** and embedded as such; the three Mermaid blocks are kept as the reproducible textual specification (and their content is not emitted to the PDF, since the converter substitutes a figure for them).

### Document changes

- §3.1 — provenance note pointing to `diagramas-c4/` as the authoritative model.
- §3.4 (**new**) — deployment diagram + availability-objectives table + the mechanisms that sustain availability + the scalability paragraph + the explicit statement that **the pilot does not validate HA**.
- §3.5 (**new**) — Level 4 code diagram.
- §5.1 — sizing table (9 CPU nodes, 3 zones, 2 read replicas), cost rows for CPU/GPU/DB/broker/network, new lines for the EKS control plane and DR, recomputed subtotals and totals, and three new leading FinOps readings.
- §5.2 — three new HA risk rows.

### The delegation caught two errors in the orchestrator's own specification

1. **The arithmetic did not close.** The specified cost rows sum to **7.111**, not the 6.972 the spec asserted: the claimed delta (+1.921) omitted the ninth CPU node (+140). Nine nodes and 6.972 are mutually exclusive. Shipped figure: **+2.060 USD/mes, +40,8 %**, totals **~3.964 / ~13.111**.
2. **The risk IDs collided.** The matrix already ran to `R-12`, so the specified `R-09`/`R-10`/`R-11` were already taken. The sequence was continued as **R-13/R-14/R-15**.

Both were correct calls and both were disclosed rather than silently approximated.

### Post-delegation corrections by the orchestrator

Three one-line contradictions the writer correctly left in place (it was out of its authorized scope) were closed:
- `cpu_node_desired_size = 8` → `9` (contradicted the 9-node sizing table).
- "Supuestos y Limitaciones" totals `~3.891 / ~11.051` → `~3.964 / ~13.111`.
- §3.1 "tres niveles de zoom" → four levels plus the deployment view.
- The two Mermaid blocks still declaring `"Redis Streams"` as the broker technology were aligned to `"Kafka · log replicado"`, matching the model and the cost table.

### Verification (parent-run)

```
converter : 1848 lines of .tex, body_blocks=180, mermaid_used=3
LaTeX     : ERRORS=0  MISSINGCHAR=0  NOTFOUND=0
figures   : all 5 included (01,02,03,05,04) — none dropped
PDF       : 36 pages, 648,789 bytes
page 28   : deployment-diagram text is selectable → the vector figure really is embedded
markdown  : 1585 lines (was 1534) · mermaid blocks 3 · XML 35,470 bytes unchanged
```

### Residual inconsistencies NOT fixed (out of this phase's scope)

- **`§3.3.2` Terraform does not provision what the cost table now pays for:** no `aws_msk` cluster and no RDS read replicas (`read_replica` → 0 occurrences). The model and the costs now assume a 3-broker replicated log and two read replicas that the IaC never creates.
- **The pilot Docker Compose still runs `redis:7.2-alpine` with `REDIS_URL`** (lines ~984, 1068–1069). Defensible only if the document states that the pilot uses a simplified broker while production uses MSK — it currently does not state that.
- Closing these requires authoring real IaC (MSK cluster, read replicas, multi-AZ parameters), not a text edit.
