# Known limitations

What the validation package does not cover, and what the system does not do.
Read together with `requirements.md` and the limitations section of
`docs/paper.md`.

## Scope of the validation package

1. **Not a validated system.** The package shows the artefacts a validation
   would contain, produced by the pipeline itself. There is no independent
   verification, no user requirement specification signed by an owner, no
   installation qualification, no change control board. The traceability
   matrix links requirements to automated tests only.
2. **Tests give evidence, not proof.** A test demonstrates the requirement on
   the cases it contains. Determinism (REQ-001) is tested on synthetic data in
   the unit tests, on the SEC data by running the primary replicate twice on
   one machine, and across two CI runners on the quick universe. It is not
   tested on every possible input.
3. **The analysis plan is the specification.** Where the code and the plan
   differ, the deviations section of the plan is authoritative; the
   requirements here were written from the plan, not from the code.

## Determinism

4. The determinism requirement covers the flags and evidence files. The audit
   log contains timestamps and is different on every run by design; the
   result tables depend on the bootstrap seed and on numpy, which is pinned.
5. The flags are reproducible given the prepared cell table. The cell table
   itself depends on the SEC data at the retrieval date in the manifest; the
   SEC updates these records as filings arrive, so a later download can give
   a different table. The manifest records the checksums the results were
   produced from, and `data/download_sec.py --check` reports differences.
6. Determinism across machines rests on IEEE arithmetic for addition,
   subtraction, multiplication, division and comparison, on Python's
   correctly rounded float formatting, and on the sort order of Python's
   built-in sort. No transcendental function is used in the detection core.
   A platform where any of these differed would break the guarantee; none is
   known.

## Audit log

7. The chain detects changes made after an entry was written. It does not
   detect a full rewrite of the chain by someone who controls the file, and it
   does not detect truncation of the tail unless the expected number of
   entries is known from elsewhere (the run end entry and the results summary
   record it). Anchoring the last hash in an external system would close
   this; it is not done here.
8. The log records what the pipeline did, not what a person did with the
   output. There is no record of who read a flag or acted on it.

## Faithfulness checker

9. The checker verifies that every number, line item, date, form and
   accession number in a sentence is in the evidence record. It does not
   verify the sentence's meaning. A sentence that uses only values from the
   record but states a false relation between them (for example that a value
   increased when it decreased) passes. The file of accepted texts in
   `results/text_examples.md` exists so that this can be read.
10. The checker knows the twenty line items and their listed synonyms. A
    sentence naming an item with an unlisted phrase is not rejected for that
    phrase; a sentence naming a listed item that is not in the record is.
11. Rounded numbers with a stated unit are accepted when they match a record
    value rounded to the written digits; a number written to fewer digits
    than it has, without a unit, is also accepted when it matches a rounding.
    The strict pass reports how often accepted texts rely on this.

## Detection

12. The identity rules flag every cell that enters an identity, so a single
    wrong value produces two to five flagged cells; precision and the
    false-flag rate of the rules reflect this.
13. The plausibility score uses other items of the same period as
    predictors, so one wrong value raises the scores of its partners. No
    explaining-away is attempted.
14. The conformal guarantee needs exchangeable scores between calibration and
    test cells. Companies differ and periods are serially dependent, so the
    achieved false-flag rate is reported against the target rather than
    assumed; it is measured on injected errors plus amended cells and treats
    every other flag as false, including flags on values that may be wrong
    but were never amended.
15. Real errors are identified from amended filings with changed XBRL values
    and from 8-K Item 4.02 filings. Both miss errors that were never
    corrected, and amendments include changes that are not corrections of a
    mistake (retrospective adoption of a standard, reclassification).

## Data

16. The twenty line items are taken from standard us-gaap elements with a
    short fallback list. Companies that use extension elements or other
    standard elements for an item have that item missing; the share of cells
    scored is reported in the summary.
17. The quarterly cash-flow and income figures are year-to-date as reported;
    quarters are not differenced, so a quarter's value is checked against the
    same quarter a year earlier and against the shorter year-to-date figure of
    the same year scaled by months.
18. The universe is companies with at least USD 100 million of assets in both
    2012 and 2023. Small companies, new companies and companies that stopped
    filing are not represented.
