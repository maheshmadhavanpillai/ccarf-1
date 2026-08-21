"""
Exercise 3: Build a Structured Data Extraction Pipeline
========================================================
Domains: Domain 4 (Prompt Engineering & Structured Output),
         Domain 5 (Context Management & Reliability)

This exercise demonstrates:
1. JSON schema design with required/optional/nullable fields and enum+detail pattern
2. Validation-retry loops with error classification
3. Few-shot examples for structural variety
4. Batch processing strategy with the Message Batches API
5. Human review routing with field-level confidence scores

Usage:
  # With API key (calls Claude):
  export ANTHROPIC_API_KEY="sk-ant-..."
  python extraction_pipeline.py

  # Demo mode (simulates the pipeline without API calls):
  python extraction_pipeline.py --demo
"""

import json
import sys
import time
import uuid
from typing import Any
from dataclasses import dataclass, field

# =============================================================================
# STEP 1: JSON Schema Design for Structured Extraction
# =============================================================================
#
# KEY CONCEPTS:
# - Required fields: must always be present in output
# - Optional/Nullable fields: use "null" when info is absent (NOT fabrication)
# - Enum + "other" pattern: known categories + escape hatch with detail string
# - The schema is passed as a tool definition, forcing structured output

EXTRACTION_TOOL = {
    "name": "extract_research_paper",
    "description": (
        "Extract structured metadata from a research paper or academic document. "
        "Return null for any field where the information is not explicitly stated "
        "in the source document. Do NOT infer, guess, or fabricate values. "
        "If a field is ambiguous, return null and note it in extraction_notes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            # --- REQUIRED FIELDS (must always be present) ---
            "title": {
                "type": "string",
                "description": "The exact title of the paper as it appears in the document"
            },
            "authors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Full author name"},
                        "affiliation": {
                            "type": ["string", "null"],
                            "description": "Author's institution. Null if not stated."
                        }
                    },
                    "required": ["name"]
                },
                "description": "List of authors in order of appearance"
            },

            # --- ENUM WITH "OTHER" + DETAIL PATTERN ---
            "document_type": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "journal_article",
                            "conference_paper",
                            "preprint",
                            "thesis",
                            "technical_report",
                            "other"
                        ],
                        "description": "Primary document classification"
                    },
                    "detail": {
                        "type": ["string", "null"],
                        "description": "Required when category is 'other'. Describes the document type."
                    }
                },
                "required": ["category"]
            },

            # --- NULLABLE FIELDS (information may be absent) ---
            "doi": {
                "type": ["string", "null"],
                "description": "Digital Object Identifier. Null if not present in document."
            },
            "publication_date": {
                "type": ["string", "null"],
                "description": "Publication date in ISO 8601 format (YYYY-MM-DD). Null if not stated."
            },
            "journal_name": {
                "type": ["string", "null"],
                "description": "Name of the journal/venue. Null if not applicable or not stated."
            },
            "abstract": {
                "type": ["string", "null"],
                "description": "The paper's abstract. Null if no abstract section exists."
            },
            "keywords": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Listed keywords. Null if no keywords section exists."
            },
            "citation_count": {
                "type": ["integer", "null"],
                "description": "Number of citations if stated in document. Null otherwise."
            },
            "funding_sources": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Funding bodies mentioned. Null if no funding section exists."
            },

            # --- FIELD-LEVEL CONFIDENCE (Step 5) ---
            "confidence_scores": {
                "type": "object",
                "properties": {
                    "title": {"type": "number", "minimum": 0, "maximum": 1},
                    "authors": {"type": "number", "minimum": 0, "maximum": 1},
                    "document_type": {"type": "number", "minimum": 0, "maximum": 1},
                    "publication_date": {"type": "number", "minimum": 0, "maximum": 1},
                    "abstract": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "description": "Confidence score (0-1) for each extracted field"
            },

            "extraction_notes": {
                "type": ["string", "null"],
                "description": "Any ambiguities, assumptions, or issues encountered during extraction"
            }
        },
        "required": ["title", "authors", "document_type", "confidence_scores"]
    }
}


# =============================================================================
# STEP 2: Validation-Retry Loop
# =============================================================================
#
# KEY CONCEPTS:
# - Validate extraction output against the schema
# - Classify errors: resolvable (format mismatch) vs unresolvable (info absent)
# - On resolvable error: retry with the error message included in prompt
# - Track retry attempts and success rates

@dataclass
class ValidationError:
    """A structured validation error."""
    field: str
    error_type: str  # "format", "missing_required", "invalid_enum", "type_mismatch"
    message: str
    is_resolvable: bool  # Can a retry fix this?


def validate_extraction(data: dict) -> list[ValidationError]:
    """
    Validates extracted data against our schema rules.
    Returns a list of validation errors (empty = valid).
    """
    errors = []

    # Check required fields
    for required_field in ["title", "authors", "document_type", "confidence_scores"]:
        if required_field not in data or data[required_field] is None:
            errors.append(ValidationError(
                field=required_field,
                error_type="missing_required",
                message=f"Required field '{required_field}' is missing or null",
                is_resolvable=True  # Model can retry and provide the field
            ))

    # Validate document_type enum
    if "document_type" in data and data["document_type"] is not None:
        dt = data["document_type"]
        valid_categories = [
            "journal_article", "conference_paper", "preprint",
            "thesis", "technical_report", "other"
        ]
        if isinstance(dt, dict):
            category = dt.get("category", "")
            if category not in valid_categories:
                errors.append(ValidationError(
                    field="document_type.category",
                    error_type="invalid_enum",
                    message=f"'{category}' is not a valid category. Must be one of: {valid_categories}",
                    is_resolvable=True  # Model can fix the enum value
                ))
            if category == "other" and not dt.get("detail"):
                errors.append(ValidationError(
                    field="document_type.detail",
                    error_type="missing_required",
                    message="When category is 'other', 'detail' field is required",
                    is_resolvable=True
                ))
        else:
            errors.append(ValidationError(
                field="document_type",
                error_type="type_mismatch",
                message="document_type must be an object with 'category' field",
                is_resolvable=True
            ))

    # Validate date format
    if "publication_date" in data and data["publication_date"] is not None:
        date_str = data["publication_date"]
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            errors.append(ValidationError(
                field="publication_date",
                error_type="format",
                message=f"Date '{date_str}' is not in ISO 8601 format (YYYY-MM-DD)",
                is_resolvable=True  # Model can reformat
            ))

    # Validate confidence scores range
    if "confidence_scores" in data and data["confidence_scores"] is not None:
        for field_name, score in data["confidence_scores"].items():
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                errors.append(ValidationError(
                    field=f"confidence_scores.{field_name}",
                    error_type="format",
                    message=f"Confidence score for '{field_name}' must be between 0 and 1, got: {score}",
                    is_resolvable=True
                ))

    # Validate authors structure
    if "authors" in data and data["authors"] is not None:
        if not isinstance(data["authors"], list):
            errors.append(ValidationError(
                field="authors",
                error_type="type_mismatch",
                message="authors must be an array",
                is_resolvable=True
            ))
        elif len(data["authors"]) == 0:
            errors.append(ValidationError(
                field="authors",
                error_type="missing_required",
                message="At least one author is required",
                is_resolvable=False  # If the document has no authors, retry won't help
            ))

    return errors


# =============================================================================
# STEP 3: Few-Shot Examples
# =============================================================================
#
# KEY CONCEPTS:
# - Few-shot examples show the model HOW to extract from varied formats
# - Cover structural variety: narrative, tabular, bibliographic
# - Show correct handling of missing data (null, not fabricated)

FEW_SHOT_EXAMPLES = [
    # Example 1: Well-structured paper with all metadata
    {
        "role": "user",
        "content": """Extract metadata from this document:

---
Title: Attention Is All You Need
Authors: Ashish Vaswani (Google Brain), Noam Shazeer (Google Brain), Niki Parmar (Google Research)
Published: 2017-06-12 in Advances in Neural Information Processing Systems (NeurIPS)
DOI: 10.48550/arXiv.1706.03762
Type: Conference Paper
Keywords: transformers, attention mechanism, sequence-to-sequence
Abstract: The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...
Funding: Google Brain, Google Research
---"""
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "title": "Attention Is All You Need",
            "authors": [
                {"name": "Ashish Vaswani", "affiliation": "Google Brain"},
                {"name": "Noam Shazeer", "affiliation": "Google Brain"},
                {"name": "Niki Parmar", "affiliation": "Google Research"}
            ],
            "document_type": {"category": "conference_paper", "detail": None},
            "doi": "10.48550/arXiv.1706.03762",
            "publication_date": "2017-06-12",
            "journal_name": "Advances in Neural Information Processing Systems (NeurIPS)",
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
            "keywords": ["transformers", "attention mechanism", "sequence-to-sequence"],
            "citation_count": None,
            "funding_sources": ["Google Brain", "Google Research"],
            "confidence_scores": {
                "title": 1.0,
                "authors": 0.95,
                "document_type": 0.95,
                "publication_date": 1.0,
                "abstract": 1.0
            },
            "extraction_notes": None
        }, indent=2)
    },

    # Example 2: Poorly structured document with MISSING fields (demonstrates null handling)
    {
        "role": "user",
        "content": """Extract metadata from this document:

---
A Brief Note on Recursive Feature Elimination

By J. Martinez

This short technical note describes an improved approach to recursive
feature elimination in high-dimensional datasets. We demonstrate a 15%
improvement in computation time while maintaining selection accuracy.

No formal publication venue. Circulated internally at DataCorp, March 2023.
---"""
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "title": "A Brief Note on Recursive Feature Elimination",
            "authors": [
                {"name": "J. Martinez", "affiliation": None}
            ],
            "document_type": {"category": "technical_report", "detail": None},
            "doi": None,
            "publication_date": "2023-03-01",
            "journal_name": None,
            "abstract": None,
            "keywords": None,
            "citation_count": None,
            "funding_sources": None,
            "confidence_scores": {
                "title": 1.0,
                "authors": 0.7,
                "document_type": 0.8,
                "publication_date": 0.6,
                "abstract": 0.3
            },
            "extraction_notes": "No formal abstract section exists. The opening paragraph describes the work but is not labeled as an abstract. Publication date is approximate (only 'March 2023' stated, day set to 01). Author affiliation inferred from 'DataCorp' mention but not explicitly attributed."
        }, indent=2)
    },

    # Example 3: Narrative format with inline citations (no structured metadata)
    {
        "role": "user",
        "content": """Extract metadata from this document:

---
In their groundbreaking 2020 work, Chen and colleagues at MIT explored the
intersection of causal inference and deep learning. The paper, which they
titled "CausalNet: Learning Causal Representations from Observational Data",
was eventually published in JMLR after a lengthy review process. The team
acknowledged support from the NSF (Grant #1234567) and DARPA.
---"""
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "title": "CausalNet: Learning Causal Representations from Observational Data",
            "authors": [
                {"name": "Chen", "affiliation": "MIT"}
            ],
            "document_type": {"category": "journal_article", "detail": None},
            "doi": None,
            "publication_date": "2020-01-01",
            "journal_name": "JMLR",
            "abstract": None,
            "keywords": None,
            "citation_count": None,
            "funding_sources": ["NSF (Grant #1234567)", "DARPA"],
            "confidence_scores": {
                "title": 0.9,
                "authors": 0.4,
                "document_type": 0.85,
                "publication_date": 0.5,
                "abstract": 1.0
            },
            "extraction_notes": "Only first author surname 'Chen' is available; 'colleagues' are unnamed. Publication date is approximate (only '2020' stated). Abstract is not present in this excerpt. Author list is likely incomplete — confidence is low."
        }, indent=2)
    }
]


# =============================================================================
# STEP 4: Batch Processing Strategy
# =============================================================================
#
# KEY CONCEPTS:
# - Message Batches API processes many documents asynchronously
# - Each request has a custom_id for tracking
# - Failed documents are identified and resubmitted with modifications
# - Oversized documents are chunked before resubmission

@dataclass
class BatchDocument:
    """A document to be processed in a batch."""
    custom_id: str
    content: str
    char_count: int = 0
    chunk_index: int | None = None  # None = not chunked

    def __post_init__(self):
        self.char_count = len(self.content)


@dataclass
class BatchResult:
    """Result of processing a single document in a batch."""
    custom_id: str
    status: str  # "succeeded", "failed", "expired"
    extraction: dict | None = None
    error_message: str | None = None
    processing_time_ms: int = 0


@dataclass
class BatchProcessingStats:
    """Statistics for a batch processing run."""
    total_documents: int = 0
    succeeded: int = 0
    failed: int = 0
    retried: int = 0
    chunked: int = 0
    total_time_seconds: float = 0.0
    sla_target_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.succeeded / self.total_documents if self.total_documents > 0 else 0

    @property
    def meets_sla(self) -> bool:
        return self.total_time_seconds <= self.sla_target_seconds


MAX_DOCUMENT_SIZE = 50000  # Characters — documents above this get chunked
CHUNK_SIZE = 40000  # Size of each chunk (with overlap)
CHUNK_OVERLAP = 2000  # Overlap between chunks for context continuity


def chunk_document(doc: BatchDocument) -> list[BatchDocument]:
    """Split an oversized document into chunks with overlap."""
    content = doc.content
    chunks = []
    start = 0
    idx = 0

    while start < len(content):
        end = min(start + CHUNK_SIZE, len(content))
        chunk_content = content[start:end]
        chunks.append(BatchDocument(
            custom_id=f"{doc.custom_id}_chunk_{idx}",
            content=chunk_content,
            chunk_index=idx
        ))
        if end >= len(content):
            break  # Last chunk — don't overlap past the end
        start = end - CHUNK_OVERLAP
        idx += 1

    return chunks


def create_batch_request(documents: list[BatchDocument]) -> list[dict]:
    """
    Creates a batch of requests for the Message Batches API.
    Each request includes the document, few-shot examples, and the extraction tool.
    """
    requests = []
    for doc in documents:
        # Build messages with few-shot examples + the target document
        messages = FEW_SHOT_EXAMPLES + [
            {"role": "user", "content": f"Extract metadata from this document:\n\n---\n{doc.content}\n---"}
        ]

        requests.append({
            "custom_id": doc.custom_id,
            "params": {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "tools": [EXTRACTION_TOOL],
                "tool_choice": {"type": "tool", "name": "extract_research_paper"},
                "messages": messages
            }
        })

    return requests


def handle_batch_failures(
    results: list[BatchResult],
    original_documents: dict[str, BatchDocument]
) -> list[BatchDocument]:
    """
    Identifies failed documents and prepares them for resubmission.
    - Oversized documents are chunked
    - Other failures are resubmitted as-is (may succeed on retry)
    """
    to_retry = []

    for result in results:
        if result.status != "succeeded":
            base_id = result.custom_id.split("_chunk_")[0]  # Handle chunked IDs
            original = original_documents.get(base_id)
            if original is None:
                continue

            if original.char_count > MAX_DOCUMENT_SIZE:
                # Chunk the oversized document
                chunks = chunk_document(original)
                to_retry.extend(chunks)
            else:
                # Retry as-is with a new ID
                to_retry.append(BatchDocument(
                    custom_id=f"{original.custom_id}_retry",
                    content=original.content
                ))

    return to_retry


# =============================================================================
# STEP 5: Human Review Routing Strategy
# =============================================================================
#
# KEY CONCEPTS:
# - Model outputs field-level confidence scores (0-1)
# - Low-confidence extractions route to human review
# - Track accuracy by document type and field
# - Configurable thresholds per field (some fields need higher confidence)

CONFIDENCE_THRESHOLDS = {
    "title": 0.8,           # Titles are usually clear
    "authors": 0.7,         # Authors can be ambiguous in narrative text
    "document_type": 0.75,  # Category is usually determinable
    "publication_date": 0.7, # Dates may be approximate
    "abstract": 0.6         # Presence/absence is usually clear
}


@dataclass
class ReviewDecision:
    """Decision on whether a field needs human review."""
    field: str
    confidence: float
    threshold: float
    needs_review: bool
    reason: str


@dataclass
class ExtractionWithRouting:
    """An extraction result with routing decisions."""
    custom_id: str
    extraction: dict
    review_decisions: list[ReviewDecision] = field(default_factory=list)
    route_to_human: bool = False
    review_reason: str = ""


def route_for_review(custom_id: str, extraction: dict) -> ExtractionWithRouting:
    """
    Analyzes confidence scores and decides if human review is needed.
    Routes to human review if ANY field falls below its threshold.
    """
    result = ExtractionWithRouting(custom_id=custom_id, extraction=extraction)
    confidence_scores = extraction.get("confidence_scores", {})

    low_confidence_fields = []

    for field_name, threshold in CONFIDENCE_THRESHOLDS.items():
        score = confidence_scores.get(field_name, 0.0)
        needs_review = score < threshold

        decision = ReviewDecision(
            field=field_name,
            confidence=score,
            threshold=threshold,
            needs_review=needs_review,
            reason=f"Score {score:.2f} < threshold {threshold}" if needs_review else "OK"
        )
        result.review_decisions.append(decision)

        if needs_review:
            low_confidence_fields.append(f"{field_name} ({score:.2f})")

    if low_confidence_fields:
        result.route_to_human = True
        result.review_reason = f"Low confidence on: {', '.join(low_confidence_fields)}"

    return result


@dataclass
class AccuracyTracker:
    """Tracks extraction accuracy by document type and field."""
    results: dict = field(default_factory=lambda: {})  # doc_type -> field -> [scores]

    def record(self, doc_type: str, confidence_scores: dict):
        if doc_type not in self.results:
            self.results[doc_type] = {}
        for field_name, score in confidence_scores.items():
            if field_name not in self.results[doc_type]:
                self.results[doc_type][field_name] = []
            self.results[doc_type][field_name].append(score)

    def get_summary(self) -> dict:
        summary = {}
        for doc_type, fields in self.results.items():
            summary[doc_type] = {}
            for field_name, scores in fields.items():
                avg = sum(scores) / len(scores) if scores else 0
                summary[doc_type][field_name] = {
                    "average_confidence": round(avg, 3),
                    "count": len(scores),
                    "below_threshold": sum(
                        1 for s in scores
                        if s < CONFIDENCE_THRESHOLDS.get(field_name, 0.7)
                    )
                }
        return summary


# =============================================================================
# The Extraction Pipeline (Real API Version)
# =============================================================================

def run_single_extraction(document: str, client=None) -> dict:
    """
    Runs extraction on a single document with validation-retry loop.
    This is the core pipeline: extract -> validate -> retry if needed.
    """
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    system_prompt = (
        "You are a precise document metadata extractor. Extract ONLY information "
        "that is explicitly stated in the source document. Return null for any "
        "field where information is not present. Never fabricate or infer values. "
        "Provide confidence scores (0-1) for each field based on how clearly the "
        "information was stated in the source."
    )

    messages = FEW_SHOT_EXAMPLES + [
        {"role": "user", "content": f"Extract metadata from this document:\n\n---\n{document}\n---"}
    ]

    max_attempts = 3
    for attempt in range(max_attempts):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "extract_research_paper"},
            messages=messages
        )

        # Extract the tool call result
        extraction = None
        for block in response.content:
            if block.type == "tool_use":
                extraction = block.input
                break

        if extraction is None:
            continue

        # Validate
        errors = validate_extraction(extraction)
        resolvable_errors = [e for e in errors if e.is_resolvable]
        unresolvable_errors = [e for e in errors if not e.is_resolvable]

        if not resolvable_errors:
            return extraction  # Valid (unresolvable errors are accepted)

        # Retry with error context
        error_descriptions = "\n".join(
            f"- {e.field}: {e.message}" for e in resolvable_errors
        )
        messages = FEW_SHOT_EXAMPLES + [
            {"role": "user", "content": f"Extract metadata from this document:\n\n---\n{document}\n---"},
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": response.content[0].id if response.content else "retry",
                 "content": json.dumps({"status": "validation_failed", "errors": error_descriptions})}
            ]},
            {"role": "user", "content": (
                f"The extraction had validation errors:\n{error_descriptions}\n\n"
                f"Please re-extract, fixing these specific issues. "
                f"This is attempt {attempt + 2}/{max_attempts}."
            )}
        ]

    return extraction  # Return best attempt even if validation still fails


# =============================================================================
# DEMO MODE
# =============================================================================

def run_demo():
    """Demonstrates the full pipeline without API calls."""
    print("\n" + "=" * 70)
    print(" EXERCISE 3: Structured Data Extraction Pipeline")
    print(" (DEMO MODE - simulated responses)")
    print("=" * 70)

    # ─── STEP 1 DEMO: Schema & Nullable Fields ───
    print("\n\n" + "─" * 60)
    print("STEP 1: JSON Schema Design & Nullable Fields")
    print("─" * 60)

    print("\n[Schema defines these field types:]")
    print("  REQUIRED:  title, authors, document_type, confidence_scores")
    print("  NULLABLE:  doi, publication_date, journal_name, abstract,")
    print("             keywords, citation_count, funding_sources")
    print("  ENUM+OTHER: document_type.category with detail string")

    # Simulate extraction from a document with missing fields
    test_doc = """
A Quick Study on Cache Invalidation Patterns
By: R. Chen
Posted on internal wiki, 2024.
"""
    print(f"\n[Processing document with missing fields:]")
    print(f"  Document: {test_doc.strip()}")

    simulated_extraction = {
        "title": "A Quick Study on Cache Invalidation Patterns",
        "authors": [{"name": "R. Chen", "affiliation": None}],
        "document_type": {"category": "other", "detail": "Internal wiki post"},
        "doi": None,
        "publication_date": "2024-01-01",
        "journal_name": None,
        "abstract": None,
        "keywords": None,
        "citation_count": None,
        "funding_sources": None,
        "confidence_scores": {
            "title": 1.0,
            "authors": 0.85,
            "document_type": 0.7,
            "publication_date": 0.5,
            "abstract": 1.0
        },
        "extraction_notes": "Publication date is approximate (only '2024' stated). Classified as 'other' since internal wiki posts don't fit standard categories."
    }

    print(f"\n[Extraction result:]")
    print(json.dumps(simulated_extraction, indent=2))
    print("\n  ✓ Nullable fields correctly returned as null (not fabricated)")
    print("  ✓ 'other' category used with detail string for wiki post")
    print("  ✓ Approximate date noted in extraction_notes")

    # ─── STEP 2 DEMO: Validation-Retry Loop ───
    print("\n\n" + "─" * 60)
    print("STEP 2: Validation-Retry Loop")
    print("─" * 60)

    # Simulate a bad extraction that needs validation
    bad_extraction = {
        "title": "Some Paper",
        "authors": [{"name": "Smith", "affiliation": None}],
        "document_type": {"category": "whitepaper", "detail": None},  # Invalid enum!
        "publication_date": "March 2023",  # Wrong format!
        "confidence_scores": {
            "title": 1.0,
            "authors": 0.9,
            "document_type": 0.8,
            "publication_date": 0.7,
            "abstract": 0.5
        }
    }

    print("\n[First extraction attempt (has errors):]")
    print(json.dumps(bad_extraction, indent=2))

    errors = validate_extraction(bad_extraction)
    print(f"\n[Validation found {len(errors)} error(s):]")
    for err in errors:
        status = "RESOLVABLE (will retry)" if err.is_resolvable else "UNRESOLVABLE (accept)"
        print(f"  • {err.field}: {err.message}")
        print(f"    → {status}")

    # Simulate the corrected extraction after retry
    corrected_extraction = {
        "title": "Some Paper",
        "authors": [{"name": "Smith", "affiliation": None}],
        "document_type": {"category": "technical_report", "detail": None},  # Fixed!
        "publication_date": "2023-03-01",  # Fixed!
        "confidence_scores": {
            "title": 1.0,
            "authors": 0.9,
            "document_type": 0.8,
            "publication_date": 0.7,
            "abstract": 0.5
        }
    }

    print(f"\n[Retry with error context included in prompt...]")
    print(f"[Second attempt (corrected):]")
    print(json.dumps(corrected_extraction, indent=2))

    errors_after = validate_extraction(corrected_extraction)
    print(f"\n[Validation after retry: {len(errors_after)} errors]")
    print("  ✓ All resolvable errors fixed on retry")

    # ─── STEP 3 DEMO: Few-Shot Examples ───
    print("\n\n" + "─" * 60)
    print("STEP 3: Few-Shot Examples for Structural Variety")
    print("─" * 60)

    print("\n[Three few-shot examples cover different structures:]")
    print()
    print("  Example 1: Well-structured paper (all fields present)")
    print("    → Demonstrates: full extraction, enum usage, high confidence")
    print()
    print("  Example 2: Minimal document (many fields absent)")
    print("    → Demonstrates: null returns, low confidence scores,")
    print("      extraction_notes explaining ambiguity")
    print()
    print("  Example 3: Narrative format (no structured metadata)")
    print("    → Demonstrates: extracting from prose, partial author info,")
    print("      approximate dates, noting incomplete data")
    print()
    print("  [These examples are prepended to every extraction request")
    print("   so the model learns the expected output patterns]")

    # ─── STEP 4 DEMO: Batch Processing ───
    print("\n\n" + "─" * 60)
    print("STEP 4: Batch Processing Strategy")
    print("─" * 60)

    # Simulate batch of documents (small placeholders for demo)
    documents = [
        BatchDocument(custom_id=f"doc_{i:03d}", content=f"Paper content {i}. " * 20)
        for i in range(100)
    ]
    # Add one oversized document
    documents[42] = BatchDocument(
        custom_id="doc_042",
        content="X" * 55000  # ~55K chars, just over the 50K limit
    )

    print(f"\n[Batch created: {len(documents)} documents]")
    print(f"  Normal documents: 99")
    print(f"  Oversized (>{MAX_DOCUMENT_SIZE:,} chars): 1 (doc_042: {documents[42].char_count:,} chars)")

    # Create batch request
    batch_requests = create_batch_request(documents[:5])  # Show first 5
    print(f"\n[Batch request structure (showing 1 of 100):]")
    print(json.dumps({
        "custom_id": batch_requests[0]["custom_id"],
        "params": {
            "model": batch_requests[0]["params"]["model"],
            "max_tokens": batch_requests[0]["params"]["max_tokens"],
            "tools": ["[EXTRACTION_TOOL]"],
            "tool_choice": batch_requests[0]["params"]["tool_choice"],
            "messages": "[few_shot_examples + document]"
        }
    }, indent=2))

    # Simulate batch results
    simulated_results = [
        BatchResult(custom_id=f"doc_{i:03d}", status="succeeded", processing_time_ms=2500)
        for i in range(100)
    ]
    # Simulate some failures
    simulated_results[42] = BatchResult(custom_id="doc_042", status="failed", error_message="Document too large")
    simulated_results[17] = BatchResult(custom_id="doc_017", status="failed", error_message="Timeout")
    simulated_results[88] = BatchResult(custom_id="doc_088", status="expired")

    succeeded = [r for r in simulated_results if r.status == "succeeded"]
    failed = [r for r in simulated_results if r.status != "succeeded"]

    print(f"\n[Batch results:]")
    print(f"  Succeeded: {len(succeeded)}")
    print(f"  Failed: {len(failed)}")
    for f in failed:
        print(f"    • {f.custom_id}: {f.status} - {f.error_message or 'expired'}")

    # Handle failures
    originals = {doc.custom_id: doc for doc in documents}
    retry_docs = handle_batch_failures(failed, originals)
    print(f"\n[Failure handling:]")
    print(f"  Documents to retry: {len(retry_docs)}")
    for doc in retry_docs:
        if doc.chunk_index is not None:
            print(f"    • {doc.custom_id} (chunk {doc.chunk_index}, {doc.char_count:,} chars)")
        else:
            print(f"    • {doc.custom_id} ({doc.char_count:,} chars)")

    # SLA calculation
    stats = BatchProcessingStats(
        total_documents=100,
        succeeded=97 + len(retry_docs),
        failed=3 - len([d for d in retry_docs if "_retry" in d.custom_id]),
        retried=len(retry_docs),
        chunked=len([d for d in retry_docs if d.chunk_index is not None]),
        total_time_seconds=245.0,  # Simulated
        sla_target_seconds=300.0   # 5-minute SLA
    )
    print(f"\n[Processing stats:]")
    print(f"  Total time: {stats.total_time_seconds}s")
    print(f"  SLA target: {stats.sla_target_seconds}s")
    print(f"  Meets SLA: {'✓ YES' if stats.meets_sla else '✗ NO'}")
    print(f"  Success rate: {stats.success_rate:.1%}")

    # ─── STEP 5 DEMO: Human Review Routing ───
    print("\n\n" + "─" * 60)
    print("STEP 5: Human Review Routing Strategy")
    print("─" * 60)

    # Simulate extractions with varying confidence
    extractions = [
        ("doc_001", {
            "title": "Clear Title",
            "confidence_scores": {"title": 0.98, "authors": 0.95, "document_type": 0.9, "publication_date": 0.85, "abstract": 0.92},
            "document_type": {"category": "journal_article", "detail": None}
        }),
        ("doc_002", {
            "title": "Ambiguous Document",
            "confidence_scores": {"title": 0.9, "authors": 0.4, "document_type": 0.6, "publication_date": 0.3, "abstract": 0.8},
            "document_type": {"category": "other", "detail": "Blog post"}
        }),
        ("doc_003", {
            "title": "Partial Info Paper",
            "confidence_scores": {"title": 1.0, "authors": 0.85, "document_type": 0.95, "publication_date": 0.9, "abstract": 0.5},
            "document_type": {"category": "preprint", "detail": None}
        }),
    ]

    print(f"\n[Confidence thresholds per field:]")
    for field_name, threshold in CONFIDENCE_THRESHOLDS.items():
        print(f"  {field_name}: {threshold}")

    print(f"\n[Routing decisions:]")
    tracker = AccuracyTracker()

    for custom_id, extraction in extractions:
        routing = route_for_review(custom_id, extraction)
        doc_type = extraction["document_type"]["category"]
        tracker.record(doc_type, extraction["confidence_scores"])

        status = "→ HUMAN REVIEW" if routing.route_to_human else "→ AUTO-APPROVED"
        print(f"\n  {custom_id} [{doc_type}]: {status}")
        if routing.route_to_human:
            print(f"    Reason: {routing.review_reason}")
        for decision in routing.review_decisions:
            marker = "⚠" if decision.needs_review else "✓"
            print(f"    {marker} {decision.field}: {decision.confidence:.2f} (threshold: {decision.threshold})")

    # Accuracy summary by document type
    print(f"\n[Accuracy by document type and field:]")
    summary = tracker.get_summary()
    print(json.dumps(summary, indent=2))

    print("\n\n" + "=" * 70)
    print(" PIPELINE COMPLETE")
    print("=" * 70)


# =============================================================================
# MAIN
# =============================================================================

def main():
    if "--demo" in sys.argv:
        run_demo()
    else:
        import anthropic
        client = anthropic.Anthropic()

        print("\n" + "=" * 70)
        print(" EXERCISE 3: Structured Data Extraction Pipeline")
        print(" (LIVE MODE - calling Claude API)")
        print("=" * 70)

        # Test with a real document
        test_document = """
Title: Scaling Language Models: Methods, Analysis & Insights from Training Gopher
Authors: Jack W. Rae, Sebastian Borgeaud, Trevor Cai, Katie Millican (DeepMind)
Published in: arXiv preprint, December 2021
DOI: 10.48550/arXiv.2112.11446
Keywords: large language models, scaling laws, natural language processing

Abstract: Natural language processing has been revolutionized by large-scale
language models. In this paper, we present an analysis of Transformer-based
language model performance across a wide range of model scales...

Acknowledgements: This work was supported by DeepMind and Alphabet Inc.
"""
        print("\n[Processing test document...]")
        result = run_single_extraction(test_document, client)
        print("\n[Extraction result:]")
        print(json.dumps(result, indent=2))

        # Validate
        errors = validate_extraction(result)
        print(f"\n[Validation: {len(errors)} errors]")
        for err in errors:
            print(f"  • {err.field}: {err.message} (resolvable: {err.is_resolvable})")

        # Route for review
        routing = route_for_review("test_doc", result)
        print(f"\n[Routing: {'HUMAN REVIEW' if routing.route_to_human else 'AUTO-APPROVED'}]")
        if routing.route_to_human:
            print(f"  Reason: {routing.review_reason}")


if __name__ == "__main__":
    main()
