# Notes on the run

Research notes written after the full run of 2 November 2026. The
pre-specified design is in `analysis_plan.md`, the citations in
`literature_check.md`, the requirements and tests in `validation/`. These
notes record what was observed when the plan met the data, which parts of
the plan held, which did not, and what was changed as a result.

## Question

Whether a review of longitudinal, multi-source records can be made auditable
in the sense used in regulated settings: every flag reproducible, every
statement in a query traceable to the source values that produced it, and
the false-flag rate known, with a language model permitted to write the
query text but excluded from the decision of what is flagged. SEC XBRL
company facts were chosen as the test case because they are public, long,
drawn from three statements that must satisfy accounting identities, and
accompanied by a natural ground truth in amended filings.

## Observations on the data

* Universe: 400 companies drawn with a fixed seed from the 2,081 entities
  with at least USD 100 million of assets in both the CY2012Q4 and CY2023Q4
  frames. 18 were dropped (no company facts, or fewer than 20 reporting
  periods), 382 kept, split 191 development and 191 held out before any
  detector ran.
* 347,190 as-reported values of twenty line items; median 62 reporting
  periods per company. The as-reported value had to be defined with care:
  each later filing restates earlier periods as comparatives, frequently with
  different numbers, so the cell table takes the value from the earliest
  original filing whose own period end equals the period.
* Cell-level corrections are rare. 373 cells (161 held out) have a value in
  a 10-K/A or 10-Q/A that differs from the original by more than 0.1% and
  USD 1,000. Most amendments carry no financial data.
* The looser label (a later original filing reports a different value for
  the same period) applies to 19,168 cells, 5.5% of the table. It mixes
  reclassifications, retrospective changes and corrections and is reported
  only as a descriptive quantity.
* 98 of 382 companies filed at least one 8-K with Item 4.02, 158 filings in
  total. Company-periods in the 24 months before such a filing have an
  amended-cell rate of 5.6% against 0.01% elsewhere, so the two labels are
  consistent with each other.
* Identity violations are common in filed data. The cash flow identity
  (operating plus investing plus financing plus exchange rate effect equals
  the change in cash, within 1%) fails in a large share of filings, mainly
  because restricted cash, discontinued operations and similar items are not
  among the twenty elements. The rules flag 1.9% of held-out cells on the
  data as filed. Tolerances were kept as pre-specified.

## Pipeline as run

Seven identity rules, then a plausibility score for every tested cell: the
median of up to three candidate predictions (previous value of the same
kind; seasonal or scaled year-to-date value; a partner item of the same
period times the company's median historical ratio) divided by a robust
scale from the company's own earlier residuals. The core uses addition,
subtraction, multiplication, division, absolute value and sorting only, so
that its output bytes do not depend on the platform. Scores are converted to
conformal p-values against development companies, and Benjamini-Hochberg is
applied at targets of 5%, 10% and 20%. Four detectors are compared at
budgets of 2, 5, 10 and 20 flags per 1,000 held-out cells: flag nothing,
rules only, plausibility only, and combined (rule flags first, then by
p-value).

Each flag carries a schema-validated evidence record holding exactly the
source values and computed quantities behind it, each value with accession
number, form, filing date and retrieval date. Query text is produced by a
deterministic template or by a local language model that receives only the
record. A checker rejects any sentence containing a number, line item, date,
form or accession number absent from the record and substitutes the
template. All runs, flags, texts and rejections are appended to a
hash-chained log.

## Deviations from the plan and their causes

Two elements of the pre-specified design failed on the data. Both are listed
in the plan's deviations section; the reasoning is given here.

**Calibration on injected development data yielded no flags.** The plan
calibrated the p-values on development companies carrying the same injected
errors as the test set, on the argument that calibration data in use would
also contain errors. With 1% of cells carrying scale slips and sign flips,
every calibration set contained scores in the thousands. The smallest
attainable p-value, one over the calibration size plus one, could not pass
the step-up threshold over 164,000 tests, and no cell was flagged at any
target. Calibration was moved to clean development data, which is the inlier
calibration set of the conformal outlier-detection literature. The
pre-specified variant was retained as a single run and is reported.

**The primary comparison is degenerate.** The rules alone raise about 3,140
flags on held-out cells, more than the primary budget of 1,687. Since the
combined detector places rule flags first, it coincides with the rules-only
detector at every budget the rules can fill, and the pre-specified difference
is zero by construction. This should have been anticipated at the planning
stage. The comparison is reported as specified; the comparisons that carry
information were already among the secondary analyses.

Further changes: computed quantities in evidence records are rounded to the
cent so that the strict exact-match pass of the checker can verify the
template; the template states the scale in dollars rather than a score
multiple; the local model is `llama3.2:3b` rather than `qwen3:8b`, because
the larger model did not fit in the memory available on the development
machine alongside the pipeline and `qwen3:4b` emitted its reasoning as the
letter even with thinking disabled; the text sample is 50 flags rather than
200, because the local model needs over a minute per text on that machine.
One exploratory split of the false flags was added after the result was
seen; it is described below.

## Results

All numbers are on the 191 held-out companies: 168,777 tested cells, about
1,680 injected cells per replicate, ten replicates, 95% percentile intervals
from a bootstrap over companies with the same resamples for every detector.

**Determinism.** Two runs of the primary replicate produced byte-identical
flags and evidence files (`results/tables/determinism.csv`). CI repeats the
quick-universe run on a second Linux runner with a different Python version
and compares the hash.

**Injected errors.** Errors caught per budgeted flag:

| Budget per 1,000 | 2 | 5 | 10 | 20 |
|---|---:|---:|---:|---:|
| Rules only | 0.40 | 0.41 | 0.31 | 0.19 |
| Plausibility only | 0.59 | 0.41 | 0.28 | 0.17 |
| Combined | 0.40 | 0.41 | 0.31 | 0.22 |

At the smallest budget the plausibility ranking is ahead (+0.19, 0.15 to
0.24): its first flags are the largest deviations, whereas the first rule
flags are the largest relative identity violations, most of which in filed
data are not injected errors. At 10 per 1,000 the rules are slightly ahead
(-0.03 for plausibility, -0.05 to -0.01). At 20 per 1,000 the rules are
exhausted and appending the plausibility ranking raises recall from 0.39 to
0.44 (+0.06, 0.00 to 0.11). The sensitivity analyses move the crossover: at
a 2% error rate the plausibility layer is ahead up to 10 per 1,000, at 0.5%
the rules are ahead from 5 per 1,000. The plausibility ranking is effective
while the budget is small relative to the number of errors; the rules are
effective once the budget admits their many small violations.

Recall by type at the primary budget: sign flips 0.63, scale slips 0.39,
cross-company swaps 0.32, transpositions 0.10, copy-forwards 0.10. The
plausibility layer alone reaches 0.61 on scale slips and 0.004 on
copy-forwards, in line with the plan's expectation that a copied value is
plausible by construction. Swaps were caught more often than expected
because the swapped value also violates the receiving company's identities.

**False-flag rate.** Benjamini-Hochberg over the conformal p-values rejected
nothing at 5% and 10%: the minimum p-value per item lies between about
1/8,000 and 1/12,000, and with 164,000 tests the step-up threshold is reached
only if more than about 160 cells share that minimum. At 20% it rejected 329
cells per replicate, of which 40% (33% to 46%) were neither injected nor
later amended, twice the target. Of these 133 false flags, 26 lay in a
company-period that also held an injected cell, so about a fifth of the
excess is collateral from a wrong neighbour (a wrong value shifts its
partners' predictions; the plan excluded explaining-away). The remaining 107
lay in periods with no injected cell and are either genuine anomalies in the
filed data that were never amended or evidence that development and
held-out companies are not exchangeable; the data do not distinguish the
two. With the rules added, 79% of flags are false under this definition,
because of the prevalence of identity violations noted above.

**Real corrections.** Of 161 held-out amended cells, the combined detector
caught 9 at the primary budget (recall 0.056, 0 to 0.15) and 13 at 20 per
1,000 (0.081). Flags were 5.6 times as likely as other cells to fall on an
amended cell (0 to 15.4). In company-periods later covered by a
non-reliance 8-K the flag rate was 3.2% against 1.0% elsewhere. Flags
therefore concentrate where restatements later occurred, but most restated
values are not detectable in isolation, as the plan anticipated.

**Query text and checker.** On the first 50 flags of the combined ranking,
the template produced 581 claims (numbers, line items, dates, forms,
accession numbers), all of them in the evidence record, and passed the
strict exact-match pass as well. The local model writing from the record
alone produced 340 claims, 94.1% of them verifiable, and 20 of 50 texts were
rejected (40%, Wilson interval 27% to 54%). Writing from the raw statements
of the flagged period and the four before it, the same model produced 454
claims, 92.5% verifiable, and 18 of 50 texts were rejected (36%, 24% to
50%). Every rejection in both variants was a number absent from the record,
typically a reported value restated with the wrong scale or an arithmetic
result the model computed itself; no text named a line item, date, form or
accession number outside the record. The plan predicted a clearly higher
rejection rate for the raw-data ablation; the observed difference is small
and within the uncertainty of 50 texts. One reading is that the record's
computed quantities (differences, tolerances, predictions) prompt the model
to perform arithmetic, which it does unreliably, whereas the raw table
prompts it to quote. Of the 30 accepted record-based texts, 3 relied on a
rounded figure with a stated unit; none of the 32 accepted raw-based texts
did. After the checker, no accepted text contains a claim of the kinds it
tests for; errors of relation between correct numbers are not tested and the
accepted texts are listed in `results/text_examples.md` for reading. The
model produced every text (no generation errors) and the template was used
in place of each rejected one.

**Audit log.** 223,865 entries at the time of the tampering check and
224,059 after the text step (run contexts, every flag with the hash of its
evidence record, every text and rejection, the evaluation), chain intact at
both points. All six simulated tamperings on a copy were
detected at the first affected entry: edit, delete, insert, swap, truncate,
and edit with a recomputed hash; the untouched control passed. An
operational observation: the log directory is watched by a file
synchroniser, and reopening the file for each entry caused frequent
transient locks that slowed a run several-fold. The writer now holds one
handle per run.

**Runtime.** One replicate of the detection core on 168,777 held-out cells
takes about 51 seconds on the development machine (6 cores, 16 GB), 0.3
seconds per 1,000 cells: 31 seconds for the scores, 14 for the evidence
records, 6 for the p-values, 1 for the rules. Loading the cell table takes
34 seconds and the clean calibration 16 to 27.

## Assessment

* The engineering requirements are met: deterministic flags, evidence
  records holding exactly the inputs of a decision, text that cannot cite
  anything outside the record, and a tamper-evident log can be built into a
  research pipeline at low cost, and the validation package is generated
  from the tests.
* The statistical guarantee did not hold in this setting. Conformal
  p-values with Benjamini-Hochberg require calibration data exchangeable
  with the clean test data and p-value granularity adequate to the number of
  tests; neither condition was met, and both failure modes (no flags, or too
  many) appear in the tables. Per-filing testing, larger calibration sets and
  explaining-away of a wrong neighbour are the natural next steps; none was
  attempted after the results were seen.
* The identity rules are a strong but noisy baseline on this data: filed
  statements violate them frequently for reasons that are not errors. A
  budgeted review needs a better ordering of rule violations than relative
  violation size.
* Copy-forwards remain undetectable by any method that judges a value by
  its plausibility; catching them needs a source other than the values
  themselves.

## Transfer

Nothing in the architecture refers to accounting except the identities and
the line items, both of which are configuration. Any review of records that
accumulate over time from several sources has the same structure: quantities
that must agree within one record, a history against which new values are
judged, a bounded number of queries, and a reader entitled to see why each
query was raised. The separation is the same in every such setting: a
deterministic core that decides, a calibration step whose assumptions must be
verified rather than assumed, an evidence record as the sole input to text
generation, a checker that admits nothing outside the record, and a log that
cannot be altered without detection. What changes between settings is the
identities, the predictors, the tolerances and the readers.
