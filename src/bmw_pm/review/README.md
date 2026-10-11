# Product manager review

`service.py` exposes approve, reject, challenge, defer and edit operations. Every decision requires a rationale, actor and request ID. Edits create new requirement revisions. The database checks the expected revision and applies the decision with its audit event transactionally.

The editable fields are title, customer outcome, use conditions and assumptions. Evidence links, score inputs and policy weights cannot currently be edited here. Challenges are recorded; an automatic re-research loop is not implemented.

A PM edit currently carries forward score inputs because evidence links and scope stay unchanged. Review that assumption when an outcome edit changes meaning; the cleanup report recommends invalidating evidence review and reassessing affected criteria. Actor selection is a prototype role, not authenticated enterprise identity.

See [PM workflow and audit](../../../docs/HUMAN_REVIEW_AND_AUDIT.md).
