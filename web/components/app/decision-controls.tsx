"use client";

import { useMemo, useState } from "react";

import { ConfidenceBadge, PriorityBadge } from "@/components/app/badges";
import { EvidenceList, type EvidenceListEntry } from "@/components/app/evidence-list";
import { SubHeading } from "@/components/app/layout-parts";
import { FactorEditor, ScoreDiff, factorLabel, FACTOR_KEYS } from "@/components/app/score";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/input";
import type { PriorityFactors, RequirementRevision } from "@/lib/domain/contracts";
import { balanceOf, confidenceOf, priorityOf, type Balance, type Confidence, type DecisionStatus } from "@/lib/domain/derive";
import type { RequirementBundle } from "@/lib/domain/model";
import { priorityScore } from "@/lib/domain/scoring";
import { useStore } from "@/lib/store";

type DialogKind = "approve" | "reject" | "defer" | "edit" | "rate" | "challenge" | null;

export interface ChallengePreset {
  statement: string;
  changes: Partial<PriorityFactors>;
}

/** Suggested challenges per requirement; the PM can edit or ignore them. */
export const CHALLENGE_PRESETS: Record<string, ChallengePreset[]> = {
  "REQ-CTL-01": [
    {
      statement: "Is this a missing-controls problem, or would better voice discoverability resolve most of it?",
      changes: { uncertainty: 3 },
    },
  ],
  "REQ-TRP-03": [
    {
      statement: "Do customers need more battery or faster charging, or does better trip planning solve the long-trip problem?",
      changes: { impact: 2 },
    },
  ],
  "REQ-ADS-05": [
    {
      statement: "Is this an interface comprehension problem or a functional defect that needs engineering investigation first?",
      changes: { uncertainty: 4 },
    },
  ],
  "REQ-CON-02": [
    {
      statement: "Is the false success state an app problem or a vehicle-connectivity problem?",
      changes: { evidence: 1 },
    },
  ],
};

interface Props {
  bundle: RequirementBundle;
  revision: RequirementRevision;
  factors: PriorityFactors;
  basis: "saved" | "seed";
  status: DecisionStatus;
  confidence: Confidence;
  balance: Balance;
  supporting: EvidenceListEntry[];
  opposing: EvidenceListEntry[];
  inScope: boolean;
}

export function DecisionControls(props: Props) {
  const { revision, status, basis, factors, inScope } = props;
  const [open, setOpen] = useState<DialogKind>(null);

  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="text-2xs font-medium uppercase tracking-wide text-slate-500">PM decision</div>
        <span className="text-2xs text-slate-500">r{revision.revision} · US · G60</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        <Button variant="primary" className="col-span-2" onClick={() => setOpen("approve")} disabled={status === "approved" || !inScope}>
          {status === "approved" ? "Approved" : "Approve"}
        </Button>
        <Button onClick={() => setOpen("challenge")} disabled={!inScope}>
          Challenge
        </Button>
        <Button onClick={() => setOpen("rate")} disabled={!inScope}>
          Rate priority
        </Button>
        <Button onClick={() => setOpen("edit")}>Edit</Button>
        <Button onClick={() => setOpen("defer")} disabled={status === "deferred"}>
          Defer
        </Button>
        <Button variant="destructive" className="col-span-2" onClick={() => setOpen("reject")} disabled={status === "rejected"}>
          Reject
        </Button>
      </div>
      {!inScope && <p className="mt-2 text-2xs text-slate-500">Decisions are recorded in the proposal&apos;s US scope. Switch the market to United States.</p>}
      {inScope && basis === "seed" && status !== "approved" && (
        <p className="mt-2 text-2xs text-amber-700">Priority is still an illustrative seed. Rate it before approving.</p>
      )}
      {inScope && factors.uncertainty >= 2 && status !== "approved" && basis === "saved" && (
        <p className="mt-2 text-2xs text-slate-500">Uncertainty is rated {factors.uncertainty}/4 — approval requires acknowledging it.</p>
      )}

      <ApproveDialog {...props} open={open === "approve"} onClose={() => setOpen(null)} />
      <ReasonDialog kind="reject" displayId={props.bundle.display_id} open={open === "reject"} onClose={() => setOpen(null)} />
      <ReasonDialog kind="defer" displayId={props.bundle.display_id} open={open === "defer"} onClose={() => setOpen(null)} />
      <EditDialog bundle={props.bundle} revision={revision} open={open === "edit"} onClose={() => setOpen(null)} />
      <RateDialog {...props} open={open === "rate"} onClose={() => setOpen(null)} />
      <ChallengeDialog {...props} open={open === "challenge"} onClose={() => setOpen(null)} />
    </div>
  );
}

function ReviewerField({ id }: { id: string }) {
  const { actorId, setActorId } = useStore();
  return (
    <div>
      <Label htmlFor={id}>Reviewer ID</Label>
      <Input id={id} value={actorId} onChange={(e) => setActorId(e.target.value)} className="mt-1" placeholder="e.g. q123456" />
    </div>
  );
}

function ApproveDialog({ bundle, factors, basis, confidence, open, onClose }: Props & { open: boolean; onClose: () => void }) {
  const { recordDecision, actorId } = useStore();
  const [rationale, setRationale] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const valid = rationale.trim().length >= 10 && acknowledged && actorId.trim().length >= 2 && basis === "saved";

  const submit = async () => {
    await recordDecision(
      bundle.display_id,
      "approve",
      `${rationale.trim()} Uncertainty acknowledged (${factors.uncertainty}/4); approval covers the customer outcome for concept testing, not a hardware commitment.`,
    );
    setRationale("");
    setAcknowledged(false);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={`Approve ${bundle.display_id}`}
        description="Commits this exact revision and its saved priority assessment. A later edit creates a new revision that needs its own approval."
        footer={
          <>
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button variant="primary" disabled={!valid} onClick={submit}>
              Approve revision
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {basis === "seed" && (
            <p className="rounded-sm bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
              The priority is still an illustrative seed rating. Save a PM priority assessment first (Rate priority) — an approval must reference a declared judgement.
            </p>
          )}
          {confidence === "Low" && (
            <p className="rounded-sm bg-amber-50 px-2 py-1.5 text-xs text-amber-800">Evidence confidence is low. Consider a challenge or deferral until more independent evidence exists.</p>
          )}
          <ReviewerField id="approve-reviewer" />
          <div>
            <Label htmlFor="approve-rationale">Rationale</Label>
            <Textarea id="approve-rationale" value={rationale} onChange={(e) => setRationale(e.target.value)} className="mt-1" placeholder="Why this outcome should shape the successor." />
          </div>
          <label className="flex items-start gap-2 rounded-sm border border-slate-200 p-2 text-xs text-zinc-800">
            <input type="checkbox" className="mt-0.5 size-3.5 accent-brand" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
            <span>
              I acknowledge the remaining uncertainty (rated {factors.uncertainty}/4), the unreviewed evidence links and the unknown engineering feasibility.
            </span>
          </label>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ReasonDialog({ kind, displayId, open, onClose }: { kind: "reject" | "defer"; displayId: string; open: boolean; onClose: () => void }) {
  const { recordDecision } = useStore();
  const [reason, setReason] = useState("");
  const [trigger, setTrigger] = useState("");
  const valid = reason.trim().length >= 10 && (kind === "reject" || trigger.trim().length >= 3);
  const submit = async () => {
    await recordDecision(displayId, kind, kind === "defer" ? `${reason.trim()} Review trigger: ${trigger.trim()}.` : reason.trim());
    setReason("");
    setTrigger("");
    onClose();
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={kind === "reject" ? `Reject ${displayId}?` : `Defer ${displayId}`}
        description={
          kind === "reject"
            ? "The requirement and its evidence stay available, and the decision is recorded in the audit trail."
            : "Deferral keeps the requirement open with a named missing input and a review trigger."
        }
        footer={
          <>
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button variant={kind === "reject" ? "destructive" : "primary"} disabled={!valid} onClick={submit}>
              {kind === "reject" ? "Reject requirement" : "Defer"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReviewerField id={`${kind}-reviewer`} />
          <div>
            <Label htmlFor={`${kind}-reason`}>{kind === "reject" ? "Reason" : "Missing input"}</Label>
            <Textarea id={`${kind}-reason`} value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1" />
          </div>
          {kind === "defer" && (
            <div>
              <Label htmlFor="defer-trigger">Review trigger</Label>
              <Input id="defer-trigger" value={trigger} onChange={(e) => setTrigger(e.target.value)} className="mt-1" placeholder="e.g. US usability study, concept gate" />
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EditDialog({ bundle, revision, open, onClose }: { bundle: RequirementBundle; revision: RequirementRevision; open: boolean; onClose: () => void }) {
  const { editRequirement } = useStore();
  const [title, setTitle] = useState(revision.title);
  const [outcome, setOutcome] = useState(revision.customer_outcome);
  const [target, setTarget] = useState(revision.acceptance_proposal.target === null ? "" : String(revision.acceptance_proposal.target));
  const [unit, setUnit] = useState(revision.acceptance_proposal.unit ?? "");
  const [rationale, setRationale] = useState("");
  const initialTarget = revision.acceptance_proposal.target === null ? "" : String(revision.acceptance_proposal.target);
  const changed = title !== revision.title || outcome !== revision.customer_outcome || target !== initialTarget || unit !== (revision.acceptance_proposal.unit ?? "");
  const valid = changed && rationale.trim().length >= 10 && title.trim().length > 5 && outcome.trim().length > 10;

  const reset = () => {
    setTitle(revision.title);
    setOutcome(revision.customer_outcome);
    setTarget(initialTarget);
    setUnit(revision.acceptance_proposal.unit ?? "");
    setRationale("");
  };

  const submit = async () => {
    await editRequirement(
      bundle.display_id,
      {
        title: title.trim(),
        customer_outcome: outcome.trim(),
        acceptance_proposal: { ...revision.acceptance_proposal, target: target.trim() === "" ? null : target.trim(), unit: unit.trim() === "" ? null : unit.trim() },
      },
      rationale.trim(),
    );
    setRationale("");
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? reset() : onClose())}>
      <DialogContent
        title={`Edit ${bundle.display_id}`}
        description={`Creates revision r${revision.revision + 1}. The saved priority and any approval of r${revision.revision} do not carry over.`}
        className="w-[min(640px,calc(100vw-32px))]"
        footer={
          <>
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button variant="primary" disabled={!valid} onClick={submit}>
              Save as r{revision.revision + 1}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <Label htmlFor="edit-title">Requirement</Label>
            <Input id="edit-title" value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1" />
          </div>
          <div>
            <Label htmlFor="edit-outcome">Customer outcome</Label>
            <Textarea id="edit-outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)} className="mt-1 min-h-[96px]" />
          </div>
          <div className="grid grid-cols-[1fr_120px] gap-2">
            <div>
              <Label htmlFor="edit-target">Acceptance target</Label>
              <Input id="edit-target" value={target} onChange={(e) => setTarget(e.target.value)} className="mt-1" placeholder="Set only after a baseline exists" />
            </div>
            <div>
              <Label htmlFor="edit-unit">Unit</Label>
              <Input id="edit-unit" value={unit} onChange={(e) => setUnit(e.target.value)} className="mt-1" />
            </div>
          </div>
          <div>
            <Label htmlFor="edit-rationale">Reason for change</Label>
            <Textarea id="edit-rationale" value={rationale} onChange={(e) => setRationale(e.target.value)} className="mt-1" />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RateDialog({ bundle, factors, open, onClose }: Props & { open: boolean; onClose: () => void }) {
  const { saveAssessment, policy } = useStore();
  const [draft, setDraft] = useState<PriorityFactors>(factors);
  const [rationale, setRationale] = useState("");
  const before = priorityScore(factors, policy);
  const after = priorityScore(draft, policy);
  const valid = rationale.trim().length >= 10;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (o) {
          setDraft(factors);
          setRationale("");
        } else onClose();
      }}
    >
      <DialogContent
        title={`Rate priority · ${bundle.display_id}`}
        description="Declare your PM judgement on each factor. The score impact is shown before anything is saved; every assessment is kept."
        className="w-[min(680px,calc(100vw-32px))]"
        footer={
          <>
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button
              variant="primary"
              disabled={!valid}
              onClick={async () => {
                await saveAssessment(bundle.display_id, draft, rationale.trim());
                onClose();
              }}
            >
              Save priority assessment
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <FactorEditor factors={draft} original={factors} onChange={setDraft} />
          <div className="flex items-center justify-between rounded-sm bg-slate-50 px-3 py-2">
            <span className="text-xs text-slate-600">CRPS under current weights</span>
            <ScoreDiff before={before} after={after} />
          </div>
          <ReviewerField id="rate-reviewer" />
          <div>
            <Label htmlFor="rate-rationale">Rationale (required)</Label>
            <Textarea id="rate-rationale" value={rationale} onChange={(e) => setRationale(e.target.value)} className="mt-1" />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ChallengeDialog({ bundle, revision, factors, balance, confidence, supporting, opposing, open, onClose }: Props & { open: boolean; onClose: () => void }) {
  const { submitChallenge, policy } = useStore();
  const [statement, setStatement] = useState("");
  const [draft, setDraft] = useState<PriorityFactors>(factors);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const presets = CHALLENGE_PRESETS[bundle.display_id] ?? [];

  const balanceAfter = useMemo(
    () =>
      balanceOf([
        ...supporting.filter((e) => !excluded.has(e.evidence.id)).map((e) => ({ stance: "supports" as const, evidence: e.evidence })),
        ...opposing.filter((e) => !excluded.has(e.evidence.id)).map((e) => ({ stance: "contradicts" as const, evidence: e.evidence })),
      ]),
    [supporting, opposing, excluded],
  );
  const before = priorityScore(factors, policy);
  const after = priorityScore(draft, policy);
  const confidenceAfter = confidenceOf(draft, { ...balanceAfter, neutral: balance.neutral });
  const gaps = [
    bundle.proposal.validation,
    ...(balanceAfter.independent_sources < 4 ? [`Only ${balanceAfter.independent_sources} independent sources remain after exclusions.`] : []),
    "Engineering feasibility and cost are not supplied.",
  ];
  const changed = FACTOR_KEYS.some((k) => draft[k] !== factors[k]) || excluded.size > 0;
  const valid = statement.trim().length >= 10;

  const toggle = (id: string) =>
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const reset = () => {
    setStatement("");
    setDraft(factors);
    setExcluded(new Set());
  };

  const submit = async () => {
    await submitChallenge({
      display_id: bundle.display_id,
      requirement_revision: revision.revision,
      statement: statement.trim(),
      factors_before: factors,
      factors_after: draft,
      excluded_evidence_ids: [...excluded],
      gaps,
      confidence_before: confidence,
      confidence_after: confidenceAfter,
    });
    reset();
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? reset() : onClose())}>
      <DialogContent
        title={`Challenge ${bundle.display_id}`}
        description="State the doubt, weigh both sides, adjust what changes. The challenge, any exclusions and the new priority assessment go to the audit trail."
        className="top-[4vh] max-h-[92vh] w-[min(1080px,calc(100vw-32px))]"
        footer={
          <>
            <span className="mr-auto text-2xs text-slate-500">
              Recorded against r{revision.revision} · {changed ? "creates a new priority assessment" : "no factor change — recorded as a challenge only"}
            </span>
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button variant="primary" disabled={!valid} onClick={submit}>
              Record challenge
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="challenge-statement">Challenge statement</Label>
            <Textarea
              id="challenge-statement"
              value={statement}
              onChange={(e) => setStatement(e.target.value)}
              className="mt-1 min-h-[52px]"
              placeholder="What do you doubt about this requirement or its priority?"
            />
            {presets.length > 0 && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-2xs text-slate-500">
                Suggested:
                {presets.map((p) => (
                  <button
                    key={p.statement}
                    type="button"
                    onClick={() => {
                      setStatement(p.statement);
                      setDraft({ ...factors, ...p.changes });
                    }}
                    className="rounded-sm border border-slate-200 px-1.5 py-0.5 text-left text-zinc-700 hover:border-brand-line hover:bg-brand-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/35"
                  >
                    {p.statement}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <span className="font-medium text-zinc-900">Contrary view in the proposal: </span>
            {bundle.proposal.contrary}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <SubHeading count={supporting.length}>Supporting evidence</SubHeading>
              <EvidenceList entries={supporting} initial={5} empty="No supporting evidence is linked." selectable={{ selected: excluded, onToggle: toggle, label: "Exclude" }} />
            </div>
            <div>
              <SubHeading count={opposing.length}>Opposing evidence</SubHeading>
              <EvidenceList
                entries={opposing}
                initial={5}
                tone="contradict"
                empty="No contradicting evidence is linked. Absence of counter-evidence is itself a gap."
                selectable={{ selected: excluded, onToggle: toggle, label: "Exclude" }}
              />
            </div>
          </div>
          <p className="-mt-2 text-2xs text-slate-500">Tick a record to exclude it from this challenge (e.g. not applicable to the US successor scope).</p>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div>
              <SubHeading>Factor ratings</SubHeading>
              <FactorEditor factors={draft} original={factors} onChange={setDraft} />
              <SubHeading>Evidence gaps</SubHeading>
              <ul className="list-disc space-y-0.5 pl-4 text-xs text-slate-600">
                {gaps.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </div>
            <div className="self-start rounded-md border border-slate-200 p-3">
              <SubHeading>Result</SubHeading>
              <dl className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">CRPS</dt>
                  <dd>
                    <ScoreDiff before={before} after={after} />
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">Priority</dt>
                  <dd className="flex items-center gap-1.5">
                    <PriorityBadge priority={priorityOf(before, factors)} />
                    <span aria-hidden className="text-slate-400">→</span>
                    <PriorityBadge priority={priorityOf(after, draft)} />
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">Confidence</dt>
                  <dd className="flex items-center gap-1.5">
                    <ConfidenceBadge confidence={confidence} />
                    <span aria-hidden className="text-slate-400">→</span>
                    <ConfidenceBadge confidence={confidenceAfter} />
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-slate-500">Evidence balance</dt>
                  <dd className="tabular-nums text-zinc-800">
                    {balanceAfter.supporting} / <span className="text-amber-700">{balanceAfter.contradicting}</span> · {balanceAfter.independent_sources} sources
                  </dd>
                </div>
              </dl>
              {FACTOR_KEYS.filter((k) => draft[k] !== factors[k]).length > 0 && (
                <p className="mt-2 text-2xs text-slate-500">
                  Changed: {FACTOR_KEYS.filter((k) => draft[k] !== factors[k]).map((k) => `${factorLabel(k)} ${factors[k]}→${draft[k]}`).join(", ")}
                </p>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
