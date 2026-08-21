# Exercise 3: Structured Data Extraction Pipeline — Detailed Explanation

## Domains Reinforced
- **Domain 4:** Prompt Engineering & Structured Output
- **Domain 5:** Context Management & Reliability

---

## Step 1: JSON Schema Design for Structured Extraction

### What it does
Defines an extraction tool with a JSON schema that forces Claude to return structured data. The schema encodes what's required, what's optional, what's nullable, and how to handle unknown categories.

### The Schema Hierarchy

```
extract_research_paper (tool)
│
├── REQUIRED (must always be present):
│   ├── title: string
│   ├── authors: array of {name, affiliation?}
│   ├── document_type: {category (enum), detail?}
│   └── confidence_scores: object
│
├── NULLABLE (null when info is absent — NOT fabricated):
│   ├── doi: string | null
│   ├── publication_date: string | null (ISO 8601)
│   ├── journal_name: string | null
│   ├── abstract: string | null
│   ├── keywords: array | null
│   ├── citation_count: integer | null
│   └── funding_sources: array | null
│
└── META:
    └── extraction_notes: string | null
```

### Key Schema Patterns

#### Pattern 1: Nullable Fields (Preventing Hallucination)

```json
"doi": {
  "type": ["string", "null"],
  "description": "Digital Object Identifier. Null if not present in document."
}
```

**Why this matters:** Without explicit null support, models tend to fabricate plausible-looking DOIs. The `["string", "null"]` type union + the description "Null if not present" creates a strong signal that null is the correct answer when info is missing.

#### Pattern 2: Enum with "Other" + Detail String

```json
"document_type": {
  "type": "object",
  "properties": {
    "category": {
      "type": "string",
      "enum": ["journal_article", "conference_paper", "preprint", "thesis", "technical_report", "other"]
    },
    "detail": {
      "type": ["string", "null"],
      "description": "Required when category is 'other'. Describes the document type."
    }
  }
}
```

**Why this pattern:** 
- The enum provides known categories for clean downstream processing
- "other" is the escape hatch when the document doesn't fit known categories
- The detail string captures what "other" actually means (e.g., "blog post", "wiki page")
- This prevents the model from forcing a bad fit just to use an enum value

#### Pattern 3: tool_choice for Forced Structured Output

```python
response = client.messages.create(
    tools=[EXTRACTION_TOOL],
    tool_choice={"type": "tool", "name": "extract_research_paper"},
    ...
)
```

**`tool_choice: {"type": "tool", "name": "..."}`** forces Claude to call this specific tool — it CANNOT respond with plain text. This guarantees structured output every time.

### Exam Insight

The key tradeoff: strict schemas catch more errors but may cause more retries. Loose schemas are more permissive but produce messier data. Design schemas that are **strict on structure** (types, required fields) but **permissive on content** (allow null, allow "other").

---

## Step 2: Validation-Retry Loop

### What it does
After extraction, validates the output against schema rules. If validation fails, classifies errors as **resolvable** (can be fixed on retry) vs **unresolvable** (fundamental data absence), and retries only resolvable errors.

### The Flow

```
Document → Claude → Extraction
                        │
                        ▼
                  Validate Output
                        │
               ┌────────┴────────┐
               │                 │
         All valid?          Errors found
               │                 │
               ▼            ┌────┴────┐
          Return result     │         │
                       Resolvable  Unresolvable
                            │         │
                            ▼         ▼
                    Retry with     Accept as-is
                    error context  (can't be fixed)
                            │
                            ▼
                    Include in prompt:
                    - Original document
                    - Failed extraction
                    - Specific error messages
                            │
                            ▼
                    Claude retries (up to 3x)
```

### Error Classification

| Error Type | Example | Resolvable? | Why? |
|-----------|---------|-------------|------|
| `format` | Date "March 2023" instead of "2023-03-01" | YES | Model can reformat |
| `invalid_enum` | "whitepaper" not in enum list | YES | Model can pick correct enum |
| `missing_required` | Required field is null | YES | Model may have skipped it |
| `type_mismatch` | String where array expected | YES | Model can restructure |
| Missing data (no authors in doc) | Empty authors array | NO | Can't extract what doesn't exist |

### The Retry Prompt Strategy

On retry, we include:
1. **The original document** (so Claude can re-read it)
2. **The failed extraction** (so Claude sees what it produced)
3. **Specific validation errors** (so Claude knows exactly what to fix)

```python
f"The extraction had validation errors:\n{error_descriptions}\n\n"
f"Please re-extract, fixing these specific issues. "
f"This is attempt {attempt + 2}/{max_attempts}."
```

This is much more effective than just saying "try again" because it gives the model precise feedback on what went wrong.

### Exam Insight

Validation-retry loops are a **reliability pattern**. Key design decisions:
- **Max retries** (we use 3) — prevents infinite loops on genuinely bad documents
- **Error classification** — don't waste retries on unresolvable issues
- **Specific error feedback** — helps the model fix the exact problem
- **Track which errors resolve** — this data informs schema refinement over time

---

## Step 3: Few-Shot Examples

### What it does
Provides 3 example extractions that teach Claude HOW to handle different document structures. These examples are prepended to every extraction request.

### The Three Examples Cover Structural Variety

| Example | Structure | Key Teaching Point |
|---------|-----------|-------------------|
| 1. Well-structured paper | All metadata explicit, labeled sections | Shows: complete extraction, high confidence |
| 2. Minimal document | Few labeled fields, informal format | Shows: null for missing data, low confidence, extraction_notes |
| 3. Narrative format | No structured metadata, prose only | Shows: extracting from text, partial info, approximations |

### Why These Specific Examples

```
User concern: "What if the model invents data that's not there?"
→ Example 2 shows null returns for absent fields

User concern: "What about documents without structured metadata?"
→ Example 3 shows extraction from narrative prose

User concern: "When should confidence be low?"
→ Examples 2 and 3 show low scores with explanations
```

### Few-Shot Design Principles

1. **Cover the hard cases** — easy cases don't need examples. Show the model how to handle ambiguity, missing data, and unusual formats.

2. **Show correct null handling** — multiple examples with null fields teaches the model that null is the RIGHT answer, not a failure.

3. **Demonstrate extraction_notes** — shows the model WHEN and HOW to note ambiguity rather than silently guessing.

4. **Vary confidence scores** — shows that 0.4 is acceptable (honest) and 1.0 is not always appropriate.

### Where Examples Go in the Message Array

```python
messages = [
    # Few-shot example 1 (user)
    {"role": "user", "content": "Extract metadata from: [well-structured paper]"},
    # Few-shot example 1 (assistant - the ideal output)
    {"role": "assistant", "content": "[complete extraction JSON]"},
    # Few-shot example 2 (user)
    {"role": "user", "content": "Extract metadata from: [minimal document]"},
    # Few-shot example 2 (assistant)
    {"role": "assistant", "content": "[extraction with nulls]"},
    # Few-shot example 3
    ...
    # THE ACTUAL REQUEST (last)
    {"role": "user", "content": "Extract metadata from: [target document]"}
]
```

### Exam Insight

Few-shot examples are the strongest lever for controlling output format and handling edge cases. They're more effective than descriptions alone because they show the model the exact output structure. But they consume tokens — use 2-4 well-chosen examples, not 20.

---

## Step 4: Batch Processing Strategy

### What it does
Processes 100+ documents using the Message Batches API — an asynchronous API that handles many requests in parallel, with failure handling and SLA tracking.

### The Batch API Flow

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│ Create Batch │────▶│  Anthropic API   │────▶│ Poll Results │
│ (100 docs)   │     │  processes async │     │ by custom_id │
└──────────────┘     └─────────────────┘     └──────┬───────┘
                                                     │
                              ┌───────────────────────┤
                              │                       │
                         Succeeded (97)          Failed (3)
                              │                       │
                              ▼                       ▼
                         Store results          Failure handling:
                                                • Oversized → chunk
                                                • Timeout → retry
                                                • Expired → retry
                                                     │
                                                     ▼
                                              Resubmit batch
```

### Batch Request Structure

Each document in the batch is a complete, independent API request:

```json
{
  "custom_id": "doc_042",           ← Track which document this is
  "params": {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 4096,
    "tools": [EXTRACTION_TOOL],
    "tool_choice": {"type": "tool", "name": "extract_research_paper"},
    "messages": [few_shot_examples + document]
  }
}
```

**`custom_id`** is critical — it's how you match results back to source documents. Use a meaningful ID (filename, database PK, etc.).

### Failure Handling Strategy

| Failure Type | Detection | Recovery |
|-------------|-----------|----------|
| Document too large | Size check or API error | Chunk into smaller pieces with overlap |
| Timeout | API timeout status | Retry as-is (likely transient) |
| Expired | Batch expiry | Retry as-is |
| Validation failure | Post-processing check | Retry with error feedback |

### Document Chunking

When a document exceeds the size limit:

```
Original (55K chars):
┌─────────────────────────────────────────────────────────┐
│ ← ─ ─ ─ ─ ─ ─ ─ ─ ─ 55,000 chars ─ ─ ─ ─ ─ ─ ─ ─ → │
└─────────────────────────────────────────────────────────┘

Chunked (40K + overlap):
┌────────────────────────────────────┐
│ Chunk 0 (40,000 chars)             │
└──────────────────────────────┬─────┘
                         ┌─────┴─────────────────┐
                         │ Chunk 1 (17,000 chars) │
                         │ ←2K overlap→           │
                         └───────────────────────┘
```

The 2K overlap ensures that entities spanning a chunk boundary appear fully in at least one chunk.

### SLA Calculation

```python
@property
def meets_sla(self) -> bool:
    return self.total_time_seconds <= self.sla_target_seconds
```

In production, you'd track:
- **Wall-clock time** (total batch processing time)
- **Per-document latency** (for identifying slow outliers)
- **Retry overhead** (what percentage of time is spent on retries)
- **Throughput** (documents/minute)

### Exam Insight

The Message Batches API is the right tool when:
- You have many independent documents to process
- Real-time latency isn't required (batch is async)
- You need to track success/failure per document
- Cost matters (batch pricing is lower than real-time)

Key architectural decisions:
- **custom_id design** — must be unique and meaningful for failure tracking
- **Chunking strategy** — overlap prevents information loss at boundaries
- **Retry budget** — don't retry indefinitely; have a failure threshold
- **SLA monitoring** — track whether you're meeting time commitments

---

## Step 5: Human Review Routing Strategy

### What it does
Uses field-level confidence scores to decide which extractions need human review. Tracks accuracy by document type and field to identify systematic weaknesses.

### The Routing Decision Flow

```
Extraction result
       │
       ▼
┌──────────────────┐
│ For each field:  │
│ confidence score │
│   vs threshold   │
└────────┬─────────┘
         │
    ALL above threshold?
         │
    ┌────┴────┐
   YES       NO
    │         │
    ▼         ▼
AUTO-APPROVE  HUMAN REVIEW
(high conf)   (low conf fields flagged)
```

### Confidence Thresholds (Per-Field)

```python
CONFIDENCE_THRESHOLDS = {
    "title": 0.8,            # Titles are usually clear — high bar
    "authors": 0.7,          # Often ambiguous — lower bar
    "document_type": 0.75,   # Usually determinable
    "publication_date": 0.7,  # May be approximate
    "abstract": 0.6          # Presence/absence is usually clear — low bar
}
```

**Why different thresholds per field:**
- Some fields are almost always clearly stated (title) — set a high bar
- Some fields are inherently ambiguous (authors in narrative text) — set a lower bar
- The thresholds reflect real-world extraction difficulty

### The Review Decision Object

```python
@dataclass
class ReviewDecision:
    field: str          # Which field
    confidence: float   # Model's self-assessed confidence
    threshold: float    # Our minimum acceptable confidence
    needs_review: bool  # confidence < threshold
    reason: str         # Human-readable explanation
```

### Accuracy Tracking by Document Type

The `AccuracyTracker` aggregates confidence scores to reveal patterns:

```json
{
  "journal_article": {
    "title": {"average_confidence": 0.98, "below_threshold": 0},
    "authors": {"average_confidence": 0.95, "below_threshold": 0}
  },
  "other": {
    "title": {"average_confidence": 0.90, "below_threshold": 0},
    "authors": {"average_confidence": 0.40, "below_threshold": 1}  ← Problem!
  }
}
```

This reveals: "author extraction is unreliable for non-standard document types" — actionable insight for improving the pipeline.

### Routing in Practice

| Scenario | Routing | Why |
|----------|---------|-----|
| Well-structured journal paper | AUTO-APPROVE | All fields above threshold |
| Blog post with unclear authorship | HUMAN REVIEW | authors: 0.40 < 0.70 |
| Preprint without abstract | HUMAN REVIEW | abstract: 0.50 < 0.60 |

### Exam Insight

Human review routing is about **cost optimization**:
- Human review is expensive but accurate
- Auto-approval is cheap but may have errors
- The threshold is the knob: lower = more auto-approve (cheaper, less accurate), higher = more review (expensive, more accurate)

Key design decisions:
1. **Per-field thresholds** — not all fields are equally important or equally hard
2. **Route on ANY low-confidence field** — a single uncertain field may invalidate the whole extraction
3. **Track accuracy by document type** — identifies where to invest in better prompts/examples
4. **Model self-reports confidence** — this works because Claude is reasonably calibrated (scores correlate with actual accuracy)

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                  EXTRACTION PIPELINE                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ INPUT: Documents (varied formats)                        │     │
│  └─────────────────────────────┬───────────────────────────┘     │
│                                │                                  │
│                                ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ STEP 3: Few-Shot Examples (prepended to every request)   │     │
│  │ • Well-structured paper (all fields)                     │     │
│  │ • Minimal doc (null handling)                            │     │
│  │ • Narrative format (extraction from prose)               │     │
│  └─────────────────────────────┬───────────────────────────┘     │
│                                │                                  │
│                                ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ STEP 1: JSON Schema (tool definition)                    │     │
│  │ • Required fields (always present)                       │     │
│  │ • Nullable fields (null when absent)                     │     │
│  │ • Enum + "other" pattern                                 │     │
│  │ • tool_choice forces structured output                   │     │
│  └─────────────────────────────┬───────────────────────────┘     │
│                                │                                  │
│                                ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ STEP 4: Batch Processing (for scale)                     │     │
│  │ • Message Batches API (async, cost-effective)            │     │
│  │ • custom_id for tracking                                 │     │
│  │ • Chunking for oversized documents                       │     │
│  │ • SLA monitoring                                         │     │
│  └─────────────────────────────┬───────────────────────────┘     │
│                                │                                  │
│                                ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ STEP 2: Validation-Retry Loop                            │     │
│  │ • Validate against schema                                │     │
│  │ • Classify errors (resolvable vs unresolvable)           │     │
│  │ • Retry with error context (up to 3x)                    │     │
│  │ • Track success rates                                    │     │
│  └─────────────────────────────┬───────────────────────────┘     │
│                                │                                  │
│                                ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │ STEP 5: Human Review Routing                             │     │
│  │ • Field-level confidence scores                          │     │
│  │ • Per-field thresholds                                   │     │
│  │ • Route low-confidence to human review                   │     │
│  │ • Track accuracy by document type                        │     │
│  └─────────────────────────────┬───────────────────────────┘     │
│                                │                                  │
│                    ┌───────────┴───────────┐                     │
│                    │                       │                      │
│                    ▼                       ▼                      │
│            AUTO-APPROVED            HUMAN REVIEW QUEUE            │
│            (high confidence)        (low confidence fields)       │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Takeaways for the Exam

1. **`tool_choice: {"type": "tool", "name": "..."}`** forces structured output — Claude MUST call the specified tool, guaranteeing JSON output conforming to the schema.

2. **Nullable fields prevent hallucination** — `["string", "null"]` type unions combined with "Null if not present" descriptions create strong signals that null is the correct answer.

3. **Enum + "other" + detail** is the standard pattern for semi-open categories — provides clean enum values for known cases and an escape hatch for unknown ones.

4. **Validation-retry is a reliability loop** — classify errors as resolvable vs unresolvable. Only retry resolvable ones. Include the specific error in the retry prompt.

5. **Few-shot examples > descriptions for format control** — 2-4 well-chosen examples covering hard cases (missing data, narrative format, ambiguity) are more effective than lengthy descriptions.

6. **Message Batches API for scale** — asynchronous, cheaper, tracks by custom_id. Use when you have many independent documents and don't need real-time results.

7. **Chunking with overlap** prevents information loss at boundaries — 5-10% overlap is typical.

8. **Human review routing is a cost/accuracy tradeoff** — per-field thresholds let you tune this balance. Track accuracy by document type to find systematic weaknesses.

9. **Confidence calibration matters** — the routing strategy only works if the model's confidence scores correlate with actual accuracy. Claude is reasonably well-calibrated for this.

10. **SLA monitoring** — always track whether batch processing meets time commitments. Include retry overhead in calculations.
