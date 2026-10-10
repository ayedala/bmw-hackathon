# Decision and assumption register

Prepared 10 October 2026. “Proposed” means the team may revise the choice; it is not a BMW instruction.

| ID | Decision/assumption | Status and reason | Revisit trigger |
|---|---|---|---|
| D01 | Build in 24 hours | Confirmed directly by user | User changes deadline |
| D02 | Emphasize argued decisions, accuracy and performance over UI | Confirmed by user, relaying BMW feedback | New judging rubric |
| D03 | Start with G60; preserve G68 regional distinction | Proposed from supplied volume and data variety | PM chooses another product scope |
| D04 | Python + SQLite + Streamlit | Proposed low-integration-cost local stack | Team has a preferred existing codebase |
| D05 | Customer outcomes first; optional engineering acceptance extension | Reconciles brief with user request | PM supplies technical deliverable requirements |
| D06 | No A–D expertise or verified-owner scores | Required by observed absence of provenance | Organizer provides source definitions |
| D07 | `BEVE` → `BEV` alias, raw preserved | Proposed semantic normalization, unconfirmed | Data dictionary received |
| D08 | Sales `EU` means an unresolved Europe reporting scope | Observed label ambiguity | Organizer confirms region membership |
| D09 | 2030 values are supplied future scenarios | Required by future year, methodology unknown | Forecast definitions received |
| D10 | Equal-weight exploratory policy only until elicitation | Proposed bootstrap, visibly unapproved | PM supplies anchor/swing preferences |
| D11 | Feasibility/cost unknown unless reviewed evidence exists | Required by missing engineering inputs | Engineering information received |
| D12 | No time trends from undated comments | Required by missing feedback timestamps | Timestamped source supplied |
| D13 | Cache validated output for honest replay | Proposed reliability and reproducibility measure | Operational deployment |
| D14 | Keep source data local and Git ignored | Protective repository default | Explicit authorized sharing requirements |
| D15 | Automated scraper and model evaluation not yet implemented | Current preparation status | Verified implementation and measured runs |

## Questions for BMW/team, without blocking coding

1. What do Source A–D represent, and is expertise/ownership independently verified?
2. Is a feedback ID a response, person, vehicle or interview episode? Can sources overlap?
3. What are the dates, sampling frames, original languages and translations of the feedback?
4. What are the survey scale endpoints, sample sizes and weighting methods? Are any values illustrative/synthetic?
5. Does sales “EU/Europe” include GB, NO and other non-EU countries? Are 2024/2025 observed or illustrative, and how is 2030 derived?
6. Does `BEVE` explicitly denote BEV? Are powertrain-level sales available?
7. What strategy, target launch, engineering boundaries and competitor cohort should the first PM policy use?
8. What data/model hosting restrictions apply to customer text, and who can evaluate/approve the demo requirements?

Proceed using the explicit unknown states described in the contracts. Ask for answers when useful, but do not stall deterministic ingestion, fixtures or the first working path.

## Architecture decision record template

For a consequential implementation change record: context; decision; alternatives; evidence/trade-off; scope and reversibility; verification; unresolved assumptions; date and owner. Do not create a new ADR for routine naming choices. Preserve earlier decisions when superseding them rather than rewriting project history.
