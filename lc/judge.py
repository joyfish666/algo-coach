"""Run/Submit judging pipeline.

Responsibilities (implemented in later milestones):
- save-before-judge: editor code is written to solution.<ext> before judging so
  disk content always matches what was judged
- run mode via remote interpret_solution (not entering submission history);
  submit mode via formal submission with polling (120s total timeout,
  PENDING/STARTED intermediate states handled)
- rich result parsing: status, runtime/memory percentiles, WA case diff,
  CE details, RE stack
- archive enrichment with difficulty/tags/lang from problems.json at judge time;
  on timeout one extra submissionDetail lookup by submission_id, then an
  archived record with status "unknown" (traceable, never faked success)
- non-idempotent requests are never auto-retried
"""
