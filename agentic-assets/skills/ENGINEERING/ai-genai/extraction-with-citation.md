---
name: extraction-with-citation
description: Extract structured context fields from inbound source documents with atomic-claim decomposition, per-claim groundedness, and per-field confidence — every value cites a source span or is TBD, never fabricated.
origin: ECC
---

# Extraction-with-Citation

Use this skill whenever an agent turns unstructured inbound source material (docs,
transcripts, product pages, SME notes) into structured project-context fields (a
glossary, personas, regulatory constraints, workflows, integration facts). It is the
governing discipline behind any inbound ingestion pipeline: extraction is not free
generation — it is claim-by-claim, citation-by-citation, and it surfaces a gap as
"unknown" rather than filling it in.

## When to Activate

- Turning a source document (or a batch of them) into structured context fields
- Building or reviewing an inbound ingestion/mapping step for any project
- Deciding whether an agent-produced field value is trustworthy enough to bind
- Authoring or auditing a `sources.md`-style provenance record

## The Never-Fabricate Rule

**"The sources don't say" is a valid, grounded output. An invented claim is not.**

State this rule explicitly wherever this skill is applied: every field an
extraction step produces is either (a) traceable to an actual span of source text,
or (b) explicitly marked unknown/TBD. There is no third option. A plausible-sounding
value with no source span behind it is a fabrication, full stop — even if it later
turns out to be true. Groundedness is judged against the evidence actually
available at extraction time, never against the extractor's own prior knowledge or
guesswork.

## The Four Load-Bearing Elements

### 1. Atomic-Claim Decomposition

Break a source document into the smallest independently-checkable claims before
doing anything else with it. A paragraph asserting three separate facts is three
claims, not one — bundling them makes partial confidence and partial citation
impossible to express. Each claim gets its own:

- a single target field (e.g. "the primary persona", "the applicable regulatory
  standard", "one workflow step")
- a single value
- a single confidence score
- a single citing source span

```python
@dataclass
class Claim:
    field: str          # the structured field this claim targets
    value: str          # the atomic value asserted
    source_id: str       # which pulled document this came from
    locator: str         # where within that source (path, section, line)
    span: str            # the literal source text this claim is grounded in
    confidence: float    # 0.0-1.0, this claim's groundedness
```

Never merge two claims to raise a low individual confidence into a higher combined
one — that is confidence-laundering, not decomposition.

### 2. Per-Claim Groundedness vs. Source Spans

A claim's confidence is a judgment about how directly its `span` supports its
`value` — not about how useful, complete, or desirable the value would be if true.
Three groundedness bands, ordered from strongest to weakest evidence:

| Band | What the span shows | Typical action downstream |
|---|---|---|
| High | The span states the value directly and unambiguously | Write the field |
| Medium (gray) | The span implies or partially supports the value | Write the field, flag it for human review |
| Low / none | No span supports the value at all | Never write — surface TBD |

A claim with no supporting span is not a low-confidence claim to be written
cautiously — it is not a claim at all. The extractor must not manufacture one to
fill a field that "should" have a value (e.g. an expected persona, an expected
regulatory citation). A structurally-expected-but-unevidenced field surfaces as an
explicit TBD entry, never an invented placeholder value dressed up as real content.

### 3. Per-Field Confidence Routing

Every field a mapping step writes carries the confidence of its best supporting
claim, and that confidence deterministically routes what happens next. Use a small,
fixed number of named threshold constants — not per-field tuning — so the routing
stays auditable:

```python
CONFIDENCE_HIGH = 0.85   # write cleanly, no flag
CONFIDENCE_LOW = 0.55    # below this: never write, always TBD

def route(confidence: float) -> str:
    if confidence >= CONFIDENCE_HIGH:
        return "written"
    if confidence >= CONFIDENCE_LOW:
        return "written-and-flagged"   # a human should double-check this one
    return "tbd"                        # never written
```

Conservative by design: when in doubt, the routing favors TBD or a flagged write
over a silent, unflagged write. A field with multiple candidate claims takes its
best (highest-confidence) supporting claim — never an average that could smuggle a
weak claim into a stronger-looking score.

### 4. The Source-Span → `sources.md` Row → Context-Field Chain

Every written (or flagged) field must be traceable end-to-end, in one direction,
with no broken links:

```
source span (in a pulled document)
    -> one sources.md row  (Fact | Source | Type | Confidence | Date)
        -> the one context field the row supports
```

- The `Source` cell of a non-TBD row always resolves back to an actual pulled
  document's coordinates (which document, where in it) — never a free-text
  description that can't be re-checked.
- A field with no supporting row is not written; a row with no resolvable source is
  not "confirmed" — the chain either holds completely or the field is TBD.
- An unconfirmed/unknown fact still gets its own row (Confidence = TBD) — it is
  never silently dropped from the record, and never given an invented Source or
  Type to make the table look more complete than the evidence supports.

## Worked Example

Source span: *"The system supports two operator roles: a configuration owner and a
read-only reviewer."*

```
Claim(field="personas", value="configuration owner", confidence=0.92, ...)
Claim(field="personas", value="read-only reviewer",  confidence=0.92, ...)
Claim(field="approval-workflow", value=?, confidence=0.0, ...)   # no span at all
```

Result: both persona claims route to "written" (>= CONFIDENCE_HIGH), each with its
own `sources.md` row citing the exact span. The approval-workflow field, for which
the source material says nothing, is emitted as an explicit TBD row and a TBD field
— not an inferred "probably has a single-approver workflow" guess.

## Anti-Patterns to Avoid

- Filling a schema-shaped gap (a persona slot, a regulatory-standard slot) with a
  plausible invented value because the schema "expects" one
- Averaging or combining multiple low-confidence claims into one higher-confidence
  write
- Writing a field first and back-filling a citation for it afterward
- Omitting an unconfirmed fact from the provenance record instead of giving it an
  explicit TBD row
- A `Source` cell that is prose ("the vendor's site") instead of a resolvable
  coordinate back to an actually-pulled document

## When to Use

- Any inbound ingestion/mapping step that turns source material into structured,
  potentially safety- or compliance-relevant project context
- Building or reviewing the provenance record (`sources.md`-style) that accompanies
  such a step
- Reviewing agent-produced context fields before they are trusted as binding input
  to a downstream regulated or safety-relevant stage
