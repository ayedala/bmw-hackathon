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
| D14 | Keep original source data, identity mapping and raw model responses local and Git ignored | Protective repository default; user authorized only locally redacted excerpts for bounded OpenAI API runs | Privacy review or changed authorization |
| D15 | Public-source research and model evaluation are not integrated into the decision path | A standalone YouTube research module exists, but no verified imported fact or human-labelled model metric is recorded | Scoped source integration and evaluation artifacts |
| D16 | More than 12 hours remained in the 24-hour window when the next sprint was planned | User response on 10 October 2026; elapsed time continues | Updated deadline or schedule |
| D17 | No separate teammate coding path was reported for the next engine sprint | User response; a standalone YouTube module subsequently appeared on `main`, so integration ownership is unconfirmed | Team assignment or new branch/work arrives |
| D18 | Locally redacted customer excerpts may be sent to the OpenAI API for bounded extraction/evaluation | User explicitly selected this option; original text and redaction mapping stay local | Data-owner restrictions or changed authorization |
| D19 | A BMW PM is available for policy and requirement review | User response; no weights, card judgments or approvals have been received yet | Actual review session and recorded decisions |

## Questions for BMW/team, without blocking coding

1. What do Source A–D represent, and is expertise/ownership independently verified?
2. Is a feedback ID a response, person, vehicle or interview episode? Can sources overlap?
3. What are the dates, sampling frames, original languages and translations of the feedback?
4. What are the survey scale endpoints, sample sizes and weighting methods? Are any values illustrative/synthetic?
5. Does sales “EU/Europe” include GB, NO and other non-EU countries? Are 2024/2025 observed or illustrative, and how is 2030 derived?
6. Does `BEVE` explicitly denote BEV? Are powertrain-level sales available?
7. What strategy, target launch, engineering boundaries and competitor cohort should the first PM policy use?
8. What additional data-owner restrictions apply beyond the user's authorization for locally redacted API excerpts, and which BMW PM judgments may be recorded or presented as official approval?

Proceed using the explicit unknown states described in the contracts. Ask for answers when useful, but do not stall deterministic ingestion, fixtures or the first working path.

## Architecture decision record template

For a consequential implementation change record: context; decision; alternatives; evidence/trade-off; scope and reversibility; verification; unresolved assumptions; date and owner. Do not create a new ADR for routine naming choices. Preserve earlier decisions when superseding them rather than rewriting project history.
