Return exactly one JSON object with these fields:

{
  "summary": "one concise root-cause hypothesis, or why evidence is insufficient",
  "cited_ids": ["literal trace IDs, span IDs, or metric names copied from the evidence"],
  "suggested_fix": "one concise remediation recommendation",
  "insufficient_evidence": false
}

Rules:
- Every value in cited_ids must be copied literally from the evidence bundle.
- Cite both a span or trace ID and a metric name when the evidence supports it.
- Set insufficient_evidence to true if the evidence does not support a specific hypothesis.
- Do not wrap the JSON in Markdown.
