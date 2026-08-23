"""Local submission history archive (append-only JSON Lines).

Responsibilities (implemented in later milestones):
- single-file append-only submissions.jsonl under ~/.algocoach/
- every record is self-sufficient: qid, frontendQuestionId, submission_id,
  lang, timestamp, status (including "unknown"), runtime/memory with
  percentiles, WA comparison, CE/RE summary, difficulty, tags[]
- submission_id covers all three write paths and doubles as the dedup key for
  site imports
- accepted status derived from the latest verdict per qid; an incremental
  qid -> latest verdict index is maintained in-process (thread-safe)
"""
