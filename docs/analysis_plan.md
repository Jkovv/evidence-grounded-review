# Analysis plan: evidence-grounded review of financial statement records

Committed before the data were downloaded and before any detector ran. The
numeric settings are mirrored in `src/egr/config.py`. Changes made after the
results were seen are listed under *Deviations* at the end, each with its
reason.

The only contact with the data before this plan was a probe of the SEC API
field names: the `frames` endpoint for `Assets` at `CY2012Q4I` (7,851
entities) and `CY2023Q4I` (6,429 entities), of which 2,081 appear in both
with assets of at least USD 100 million, and the `submissions` and
`companyfacts` records of one company (CIK 320193), which showed that
amended filings carry the form `10-K/A` with values for already reported
periods and that 8-K filings carry their item numbers. No other company was
inspected, no detector was run and no error was injected.

## Question

Can a review of longitudinal, multi-source records be made fully auditable:
every flag reproducible, every statement traceable to source data, and the
false-flag rate controlled, without a language model ever deciding what to
flag?

**Primary (confirmatory).** On held-out companies with injected errors at a
rate of 1% of cells, at a budget of 10 flags per 1,000 tested cells, does the
combined detector (identity rules, then conformal plausibility p-values) catch
more injected errors per flag than the rules-only baseline?

**Secondary.** The same at budgets of 2, 5 and 20 flags per 1,000 cells;
recall by error type; recall of real amendments; achieved false-flag rate at
Benjamini-Hochberg targets of 5%, 10% and 20% against the target; faithfulness
of generated query text, template against language model, with and without
the checker, and with the evidence record against raw data; determinism;
audit-log integrity under tampering; runtime.

## Data

* **Source.** SEC EDGAR XBRL APIs at data.sec.gov: `companyfacts` for every
  company in the universe, `submissions` (with its continuation files) for the
  filing history, and two `frames` responses for universe selection. All
  requests send the user agent `Julia Kowalczuk j.kowalczuk326@gmail.com` and
  are spaced at least 0.15 seconds apart (under 7 per second against the
  stated maximum of 10). Every downloaded file is recorded in
  `data/manifest.json` with URL, retrieval date and SHA-256; the manifest is
  committed, the files are not.
* **Universe.** Entities present in both `frames/us-gaap/Assets/USD/CY2012Q4I`
  and `CY2023Q4I` with assets of at least USD 100 million in both, sorted by
  CIK. From these, 400 are drawn at random with the fixed seed (24 in the
  quick mode used by CI). Companies whose `companyfacts` record has fewer than
  20 reporting periods with `Assets` from original 10-K or 10-Q filings are
  dropped after download and the count is reported; they are not replaced.
* **Line items.** Twenty us-gaap elements in USD, with fallbacks tried in
  order when the first is absent for a company:

  | Statement | Item | Element (fallbacks) |
  |---|---|---|
  | balance sheet (instant) | total assets | Assets |
  | | current assets | AssetsCurrent |
  | | total liabilities | Liabilities |
  | | current liabilities | LiabilitiesCurrent |
  | | stockholders' equity | StockholdersEquity (StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest) |
  | | liabilities and equity | LiabilitiesAndStockholdersEquity |
  | | cash | CashAndCashEquivalentsAtCarryingValue (CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents) |
  | income statement (duration) | revenue | Revenues (RevenueFromContractWithCustomerExcludingAssessedTax, SalesRevenueNet, RevenueFromContractWithCustomerIncludingAssessedTax) |
  | | cost of revenue | CostOfRevenue (CostOfGoodsAndServicesSold, CostOfGoodsSold) |
  | | gross profit | GrossProfit |
  | | operating income | OperatingIncomeLoss |
  | | income tax | IncomeTaxExpenseBenefit |
  | | net income | NetIncomeLoss (ProfitLoss) |
  | cash flow (duration) | operating cash flow | NetCashProvidedByUsedInOperatingActivities |
  | | investing cash flow | NetCashProvidedByUsedInInvestingActivities |
  | | financing cash flow | NetCashProvidedByUsedInFinancingActivities |
  | | change in cash | CashAndCashEquivalentsPeriodIncreaseDecrease (CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect) |
  | | exchange rate effect | EffectOfExchangeRateOnCashAndCashEquivalents (EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents); context only, never tested |
  | | depreciation and amortisation | DepreciationDepletionAndAmortization (DepreciationAndAmortization, Depreciation) |
  | | capital expenditure | PaymentsToAcquirePropertyPlantAndEquipment |

  The fallback is chosen once per company and item: the first element with the
  most facts from original filings.
* **Reporting periods and as-reported values.** A filing is an accession
  number with form 10-K or 10-Q. Its own period end is the latest `end` among
  its `Assets` facts. For each company the reporting periods are the distinct
  own period ends of its filings; if two original filings share an own period
  end, the earlier filed one is the filing of record. The **as-reported value**
  of an item at a period is the fact from the filing of record: for instant
  items, the fact with `end` equal to the period end; for duration items, the
  fact with `end` equal to the period end and the longest duration of at most
  380 days reported in that filing (the year-to-date figure: 3, 6, 9 or 12
  months). The duration in months (rounded) is kept with the cell. Values from
  later filings that re-report the same period (comparative columns) are never
  used as the value under review.
* **Cells.** One as-reported value of one item at one reporting period of one
  company, with its accession number, form, filing date, period start (for
  durations), period end and retrieval date. The exchange rate effect is a
  context cell: it enters the cash-flow identity but is never tested, injected
  into or flagged.
* **Real errors (ground truth A, cell level).** For a cell, the *amended value*
  is the value of the same item and period in the earliest filed 10-K/A or
  10-Q/A whose own period end equals the cell's period end. A cell is
  **amended-changed** if an amended value exists and differs from the
  as-reported value by more than 0.1% of the larger absolute value and by more
  than USD 1,000 (so that rounding to thousands or millions is not a change).
  Amendments that carry no XBRL financial data (Part III amendments, exhibit
  amendments) therefore do not count, which is intended.
* **Real errors (ground truth B, company-period level).** From the submissions
  history, every 8-K whose `items` include `4.02` (non-reliance on previously
  issued financial statements) with its filing date. A company-period is
  *under non-reliance* if a 4.02 8-K was filed within 24 months after the
  period end. This is a weak, descriptive label: it does not say which values
  were wrong.
* **Revisions (descriptive only).** A cell is *revised later* if any later
  original 10-K or 10-Q reports a different value (same thresholds) for the
  same item and period. Reported as a count; not used as ground truth because
  such differences include reclassifications and changes in accounting policy.

## Split

Companies are split at random with the fixed seed, before any analysis, into
**development** (one half) and **held-out** (one half). All reported numbers
are on held-out companies. Development companies are used to calibrate the
conformal p-values, to choose nothing (no setting is tuned on the data: all
tolerances and thresholds are fixed in this plan), and for any check made
while writing the code. The split is written to `data/processed/split.parquet`
in the prepare step and its hash is recorded in the audit log.

## Error injection

* Applied to development and held-out companies alike, so that calibration
  scores come from data that contains errors as they would in use. A new
  injection is drawn for each replicate: 10 replicates (2 in quick mode).
* **Rate.** 1% of tested cells in the primary analysis. No source gives a rate
  of wrong numeric values per line item in filed XBRL (literature check,
  section 4.3); the rate is a documented assumption. Sensitivity analyses at
  0.5% and 2%.
* **Five error types in equal shares.** Cells are drawn uniformly among the
  eligible cells of each type; a cell gets at most one error; cells that are
  amended-changed are not eligible, so the two ground truths do not overlap.
  1. **Sign flip.** The value is negated. Eligible if non-zero.
  2. **Scale slip.** The value is multiplied by 1,000 or divided by 1,000 with
     equal probability (a figure entered in thousands as units or the other
     way round). Eligible if non-zero; the divided value is rounded to an
     integer.
  3. **Digit transposition.** Two adjacent digits among the first four
     significant digits of the integer value are exchanged. Eligible if at
     least two significant digits and the result differs.
  4. **Copy-forward.** The value is replaced by the company's as-reported
     value of the same item at the previous reporting period (previous period
     of the same year-to-date length for duration items). Eligible if that
     value exists and differs.
  5. **Cross-company swap.** The value is exchanged with the as-reported value
     of the same item at the same period end (same calendar quarter) of
     another company in the same split. Both cells count as errors. Eligible
     if a partner exists and the values differ.
* A type with fewer eligible cells than its share uses all of them and the
  shortfall is reported; it is not redistributed.

## Detectors

Everything in this section is deterministic: pure Python arithmetic
(addition, subtraction, multiplication, division, absolute value, comparison,
sorting, `math.fsum`), no logarithms or exponentials, no learned model, no
threads. Two runs on the same input must produce byte-identical flag files;
CI tests this on two separate Linux runners and a test compares a Windows run
with the committed Linux hash.

### Identity rules (layer 1)

Applied to each company-period on the as-reported values of that period.
Tolerance for an equality is 0.1% of the larger absolute side plus USD 1,000.
A rule flags every cell that enters it.

| Rule | Statement | Condition for a flag |
|---|---|---|
| R1 | balance sheet | total assets differ from liabilities and equity beyond tolerance |
| R2 | balance sheet | current assets exceed total assets beyond tolerance |
| R3 | balance sheet | current liabilities exceed total liabilities beyond tolerance (when total liabilities is reported) |
| R4 | balance sheet | cash exceeds current assets beyond tolerance |
| R5 | all | a value that must be non-negative is negative: total assets, current assets, total liabilities, current liabilities, liabilities and equity, cash, revenue, cost of revenue, depreciation and amortisation, capital expenditure |
| R6 | income statement | gross profit differs from revenue minus cost of revenue beyond tolerance (when all three are reported) |
| R7 | cash flow | operating plus investing plus financing cash flow plus the exchange rate effect (zero when absent) differs from the change in cash beyond 1% of the largest absolute component plus USD 1,000 |

The identity between liabilities plus equity and total assets is not a rule,
because noncontrolling interests and temporary equity sit between them in
many filings; R1 covers the exact identity.

### Plausibility score (layer 2)

For each tested cell, candidate predictions are formed from the company's own
history and from the other items of the same period:

1. the as-reported value of the same item at the previous reporting period
   (same year-to-date length for duration items, that is the same fiscal
   quarter one year earlier);
2. for instant items, the value four reporting periods earlier; for duration
   items, the previous year-to-date value of the same fiscal year scaled by
   the ratio of durations (for example the six-month figure times 9/6 as a
   prediction of the nine-month figure);
3. the partner item of the same period times the median of the ratio
   item/partner over the company's earlier periods (at least four). Partners:
   total assets and liabilities and equity (each other); current assets,
   total liabilities, equity, depreciation and amortisation, capital
   expenditure: total assets; current liabilities: total liabilities, else
   total assets; cash: current assets, else total assets; cost of revenue,
   gross profit, operating income, income tax, net income, operating,
   investing and financing cash flow: revenue; change in cash: the sum of the
   three cash flows and the exchange rate effect (ratio fixed at 1); revenue:
   total assets.

The prediction is the median of the available candidates (none: the cell is
untested and counted as such). The residual is the value minus the prediction.
The scale is the median absolute residual of the same company and item over
its earlier periods (at least four), floored at 2% of the median absolute
value of the item over those periods and at USD 1,000; with fewer than four
earlier residuals the scale is 10% of the absolute prediction, floored the
same way. The score is the absolute residual divided by the scale, rounded to
nine significant digits before any ranking.

Only earlier periods of the same company enter a cell's prediction and scale,
so the score of a period does not depend on later periods. Other items of the
same period do enter, so one wrong value can raise the scores of its partners;
no explaining-away is attempted, and the evaluation counts the resulting
flags as what they are.

### Conformal p-values and Benjamini-Hochberg

For each item, the calibration set is the scores of all tested cells of
development companies in the same replicate. The p-value of a held-out cell
with score s is (1 + number of calibration scores at least s) divided by
(number of calibration scores + 1). Benjamini-Hochberg is run once over all
held-out tested cells of a replicate at target q; the flagged cells are the
rejections. Targets: 5%, 10% (primary) and 20%. The achieved false-flag rate
is the share of flags on cells that are neither injected nor amended-changed,
with its interval from the company bootstrap.

### Detectors compared

* **Nothing.** Flags no cell. Recall 0 by construction; included so that the
  precision of every other detector is read against the base rate.
* **Rules only.** The union of R1 to R7 flags. At a budget smaller than the
  number of rule flags, flags are ordered by relative violation size (R5:
  absolute value) and cut.
* **Plausibility only.** Cells ordered by conformal p-value, ties by score.
* **Combined (primary).** Rule flags first, in their order, then the remaining
  cells by p-value.

A **budget** of b flags per 1,000 tested cells allows the first b x N/1,000
flags on N held-out tested cells of the replicate. Budgets: 2, 5, 10
(primary) and 20.

## Evidence records

Every flag carries one evidence record validated against
`src/egr/schemas/evidence.schema.json`: company (CIK and name), the rule or
the plausibility test that fired, and for every source value that entered
the decision: item, element, period start and end, value, unit, accession
number, form, filing date and retrieval date; plus the computed quantities
(prediction, residual, scale, score, p-value, tolerance, difference) that the
decision used, and nothing else. The record contains no value the detector
did not use.

## Query text

Two variants write a query for each flag in the style of an SEC comment
letter: cite the filing and period, state the observation, ask the company to
explain or revise. Neither asserts what the correct value is.

* **Template.** A deterministic sentence per rule or test, filled from the
  evidence record.
* **Language model.** Configurable backend: the Anthropic API (model
  `claude-sonnet-5-5` unless configured otherwise) or a local open model
  through an OpenAI-compatible endpoint (an Ollama server with `qwen3:8b` in
  the runs reported here). The model receives the evidence record as JSON and
  an instruction to write at most three sentences using only values, line
  items and periods in the record. Sampling at temperature 0 where the backend
  allows it; the model name, prompt hash and raw output go to the audit log.
  The model never sees anything but the evidence record and never chooses
  what is flagged.

### Faithfulness checker

Each generated text is split into sentences. A sentence passes if every
number in it (after removing currency symbols and thousands separators, and
applying any stated unit of thousand, million or billion) equals a value in
the evidence record exactly or when the record value is rounded to the same
number of significant digits as written, or is a year or a day of a period in
the record, or is a duration in months in the record; if every line item
name it mentions (matched against the twenty item labels and their listed
synonyms) is in the record; and if every date or fiscal period it mentions is
in the record. A text with any failing sentence is **rejected** and replaced
by the template; a text with no failing sentence is **accepted**.

Reported: the share of claims verified (numbers, items and periods found, over
all extracted), the rejection rate, and the residual error rate after the
checker, measured by a second, stricter pass that accepts only exact matches
and no rounding, on the accepted texts; plus a file of 50 accepted texts with
their records for reading.

### Ablation

The language model is given the raw company-period table (all twenty items
for the flagged period and the four previous periods, with accession numbers)
and the location of the flag, but not the evidence record. The same checker
is applied against the evidence record. Expected: a higher rejection rate and
a lower verified share, because the model can mention values the record does
not contain.

Sample: 200 held-out flags from the primary replicate at the primary budget
(all flags if fewer), the same flags for both variants and the ablation. In
quick mode, or when no backend is configured, the language-model parts are
skipped and the tables say so.

## Audit log

An append-only JSON lines file. Entry i contains a sequence number, a UTC
timestamp, an entry type, a payload and `prev_hash`, the SHA-256 of entry
i-1 as written; `hash` is the SHA-256 of the canonical serialisation of the
entry without `hash`. Entry 0 has a fixed genesis `prev_hash`. Entries:
run start (package version, Python version, platform, git commit, data
manifest hash, split hash, all parameters), each flag with its evidence
record hash, each generated text with variant, model, prompt hash, raw text,
accepted or rejected and the reasons, each rejection, and run end with the
hashes of the output files. `egr verify-log` recomputes the chain and
reports the first broken entry.

Tampering simulated in tests and in the evaluation: a changed payload field,
a deleted entry, an inserted entry, two swapped entries, a truncated file, and
a recomputed hash on an edited entry without recomputing the following
entries. All must be detected. A full recomputation of the chain after an
edit is not detectable from the file alone and the limitations say so.

## Evaluation

All on held-out companies. Intervals are 95% percentile intervals from a
bootstrap over held-out companies (1,000 resamples, 200 in quick mode), the
same resamples for every detector so that differences are paired, averaged
over replicates.

1. **Determinism.** Pass or fail: SHA-256 of the flags and evidence files
   identical across two runs on one machine and across two CI runners; the
   Windows development machine compared with the committed Linux hash.
2. **Injected errors.** At each budget: errors caught per flag (primary
   metric), precision, recall, recall by error type, for the four detectors,
   with the difference combined minus rules-only and its interval. One
   confirmatory comparison: combined against rules-only at 10 per 1,000,
   errors caught per flag, 1% rate. Everything else is descriptive.
3. **Real amendments.** On clean data (no injection): recall of
   amended-changed cells at each budget for each detector, and the enrichment
   of amended-changed cells among flags against their base rate. Also the
   flag rate of combined at the primary budget in company-periods under
   non-reliance against the others.
4. **False-flag rate.** Achieved against target at 5%, 10% and 20% on injected
   data, for plausibility only and for combined (rule flags are not covered by
   the guarantee and are expected to raise the rate).
5. **Faithfulness.** Verified share of claims, rejection rate, residual error
   rate after checking, for template, language model from the evidence record,
   and language model from raw data.
6. **Audit log.** Each tampering type detected or not.
7. **Runtime.** Wall-clock seconds per stage and per 1,000 cells, on the
   development machine and on CI.

## Expectations stated in advance

* Scale slips and sign flips of items that enter an identity are caught by the
  rules; those of items outside any identity only by the plausibility layer.
* Copy-forward and cross-company swaps are largely missed by both layers,
  because a copied value is by construction a plausible one; recall under 0.2
  at the primary budget is expected for both.
* Real amendments are rarely visible in a single value, so recall of
  amended-changed cells at the primary budget is expected to be low (under
  0.1); the interesting number is the enrichment.
* The achieved false-flag rate of the plausibility layer is expected at or
  under target on average, with an interval that may cross it because
  companies are not exchangeable in the strict sense.
* The checker rejects a clear share of language-model texts even from the
  evidence record (a rounded figure written differently, a line item named by
  a synonym not on the list), and most texts from raw data.

## Reporting

`results/tables/*.csv`, `results/summary.json`, `results/figures/*.png`, the
executed `notebooks/walkthrough.ipynb`, `docs/notes.md` and the README. Every
number in the README is traceable to a table. The validation package in
`docs/validation/` is regenerated by `make validation` from the tests.

## Deviations

All made after the first detection run on the SEC data was seen. None
changes the rules, the score, the split, the injection or the budgets.

1. **Calibration on clean development data, not on injected development
   data.** As written, the calibration set was the scores of development
   companies in the same replicate, injection included. In the first run this
   gave zero Benjamini-Hochberg flags at every target: the injected errors put
   scores in the thousands into every calibration set, so the smallest
   attainable p-value (about 1 in 12,000 per item) could never pass the
   step-up threshold over 164,000 tested cells. The calibration set is now the
   scores of development companies on the data as filed, with no injection,
   which is the inlier calibration set of Bates et al. 2023. It still
   contains whatever real errors the filed data hold. The pre-specified
   variant is kept as one extra run (`primary-injectedcal`) and reported in
   the false-flag table so that the zero can be seen. The injection into
   development companies is kept as planned but no longer enters any
   calculation.
2. **The primary comparison is degenerate and is reported as such.** The
   identity rules alone flag about 1.8% of held-out cells, more than the
   primary budget of 10 per 1,000 allows. Because the combined detector puts
   rule flags first, it is identical to the rules-only detector at the
   budgets of 2, 5 and 10 per 1,000, and the pre-specified difference is zero
   by construction. The difference is still computed and reported; the
   comparisons that carry information are plausibility against rules at
   every budget and combined against rules at 20 per 1,000, both already
   secondary analyses. No new detector was added after seeing the results.
3. **Computed quantities in evidence records are rounded to the cent.**
   Prediction, residual, scale, candidates and rule quantities are stored
   with two decimals so that the template can write them in full and the
   strict exact-match pass of the checker can verify them. Scores and
   p-values are stored unrounded. The decision itself uses the unrounded
   values; only the record changed.
4. **The template no longer states the score.** It states the usual spread
   (the scale) in dollars instead of "x times the usual spread", for the same
   reason: a one-decimal score cannot be matched exactly against the record.
5. **Local model endpoint.** The local model is called through Ollama's
   native chat endpoint rather than the OpenAI-compatible one named in the
   plan, because only the native endpoint can switch a model's thinking mode
   off; with thinking on, the qwen3 models spent their token budget on
   reasoning and returned empty letters. The OpenAI-compatible backend
   remains available for other servers.
6. **Rules and scores are computed for held-out companies only in a
   replicate.** Development companies are scored once, on the filed data,
   for the calibration. This changes runtime only.
7. **Local model and text sample.** The local open model is `llama3.2:3b`
   through Ollama, not `qwen3:8b`: the 8 billion parameter model did not fit
   in the memory available next to the pipeline, and `qwen3:4b` wrote its
   reasoning into the letter even with thinking switched off (the texts were
   rejected by the checker as a whole). The text sample is 50 flags rather
   than 200, because the small model needs over a minute per text on the
   development machine and the three variants run on the same flags. The
   Anthropic backend is implemented and selected with
   `EGR_LLM_BACKEND=anthropic`; it was not run here because no API key was
   available in the environment.
8. **One exploratory split of the false flags.** After the achieved
   false-flag rate came out above target, the false-flag table was given two
   more columns: the false flags that sit in a company-period holding an
   injected cell, and the false-flag rate outside such periods. The split
   says how much of the excess is collateral from a wrong neighbour (the plan
   said no explaining-away would be attempted) and how much is not. It is
   descriptive and changes no flag.
