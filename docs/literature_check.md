# Literature and standards check: evidence-grounded review

Searched on 2026-11-02, before any code in this repository was written. The aim
was to find (1) what regulated settings expect of a computerised review system,
so that the architecture can be mapped to those expectations, (2) established
statistical and evaluation methods to reuse, and (3) prior work on error and
anomaly detection in financial statements, so that the README claims only what
is new.

## How the citations were verified

* Every DOI below was resolved on 2026-11-02 against its Crossref record
  (`api.crossref.org/works/<doi>`, polite pool). Authors, title, journal,
  volume, issue and pages are copied from that record. Where Crossref holds the
  abstract, what is said about the paper is taken from it; where it does not
  (Beneish 1999, Dechow et al. 2011, Debreceny et al. 2010, Maynez et al. 2020,
  the EMNLP and NAACL proceedings), only the bibliographic record and the title
  are relied on and the description is kept general.
* The Crossref record of the first edition of Vovk, Gammerman and Shafer (DOI
  10.1007/b106715) has no author field; the authors were confirmed from the
  Crossref record of the second edition (DOI 10.1007/978-3-031-06649-8).
* Regulatory and standards documents were read from the issuing body: the
  text of 21 CFR 11.10 (via the Legal Information Institute mirror, as
  ecfr.gov redirected automated requests), the FDA guidance pages, the ISPE
  GAMP 5 page, the text of Public Law 107-204 on govinfo.gov, the SEC filing
  review page, the SEC EDGAR API page and the SEC webmaster FAQ.
* Searches: Crossref bibliographic queries and web searches for *XBRL filing
  errors*, *restatement causes*, *conformal p-values false discovery rate*,
  *attribution evaluation generated text*, *SEC comment letter process* and
  *computer software assurance final guidance*.

## 1. Audit trails and validation in regulated settings

What regulators and industry guidance expect of a computerised system that
produces records that someone relies on. None of these documents applies to a
public research repository; they are used as the design target.

| Source | What it requires or recommends | Design element here |
|---|---|---|
| 21 CFR Part 11, section 11.10 (current text) | (a) validation "for accuracy, reliability, consistent intended performance" and the ability to discern invalid or altered records; (b) accurate and complete copies in human readable and electronic form; (c) protection of records for accurate and ready retrieval; (e) "secure, computer-generated, time-stamped audit trails" where record changes "shall not obscure previously recorded information"; (k)(2) revision and change control that keeps "an audit trail that documents time-sequenced development and modification" | determinism test and validation package (a); JSON evidence records and audit log that are both machine readable and printable (b); append-only, hash-chained audit log with a verification script (e); git history and CHANGELOG (k) |
| FDA, *Part 11, Electronic Records; Electronic Signatures: Scope and Application*, guidance for industry, September 2003 | narrows enforcement to a risk-based reading: FDA does not enforce the Part 11 validation and audit-trail provisions as such, but predicate rules still apply, validation should follow "a documented, risk-based approach", and audit trails are recommended where users create, modify or delete regulated records | the validation package states requirements and risks first, then tests |
| FDA, *Computer Software Assurance for Production and Quality Management System Software*, final guidance February 2026 (superseding the final guidance of 24 September 2025, docket FDA-2022-D-0795; draft September 2022) | a risk-based approach to establishing confidence in software used in production or the quality system: identify where more rigour is warranted and apply assurance activities in proportion | the traceability matrix states, per requirement, which test gives the assurance and how strong it is (unit, integration, cross-machine) |
| ISPE, *GAMP 5: A Risk-Based Approach to Compliant GxP Computerized Systems*, second edition, July 2022 | a specification-and-verification lifecycle that is not limited to linear development, use of supplier documentation and tools, critical thinking by subject matter experts, and appendices on artificial intelligence and machine learning, cloud and open source | numbered requirements, specification before implementation (analysis plan committed first), tests traced to requirements, known limitations |
| Sarbanes-Oxley Act of 2002, Public Law 107-204, 30 July 2002 | section 302(a)(4): the signing officers "are responsible for establishing and maintaining internal controls" and must have evaluated and reported on their effectiveness; section 404(a): each annual report must contain an internal control report with management's assessment of "the internal control structure and procedures of the issuer for financial reporting"; 404(b): the auditor "shall attest to, and report on" that assessment; section 408: periodic review of each issuer's filings by the Commission | the setting: a review of financial reporting records where every flag must be explainable to an officer or auditor; the controlled false-flag rate is what makes a review step usable as a control |

Established practice: audit trails that are secure, time-stamped and do not
obscure earlier entries; validation organised as requirements, risk assessment,
tests and traceability; change control. What is done here is to build a
research pipeline so that it produces those artefacts by construction, and to
say in `docs/validation/` what is and is not covered, without claiming that
the repository is a validated system.

## 2. Statistical error control

| Work | What it establishes | Used here |
|---|---|---|
| Benjamini and Hochberg 1995 | the false discovery rate and the step-up procedure that controls it under independence (later extended to positive dependence) | the flagging rule: flags are the Benjamini-Hochberg rejections at a configurable target rate |
| Vovk, Gammerman and Shafer 2005 (second edition 2022) | conformal prediction: distribution-free validity of p-values computed by ranking a nonconformity score among exchangeable calibration scores | the p-value of each cell is the rank of its plausibility score among calibration scores from development companies |
| Bates, Candès, Lei, Romano and Sesia 2023 | conformal p-values for outlier detection are marginally valid but mutually dependent; they are shown to be positively dependent, which gives exact false discovery rate control with Benjamini-Hochberg; a conditionally valid variant is also given | the combination "conformal p-values plus Benjamini-Hochberg" and the expectation that the achieved false-flag rate on held-out companies should sit at or under the target |
| Angelopoulos and Bates 2023 | an introduction to conformal prediction with the split (inductive) construction used here | the split construction: scores from development companies calibrate, held-out companies are tested |

Established practice: all of it. What is new here is only the application to
line items of financial statements with a detector that never uses a learned
black box, and the reporting of the achieved rate on companies that played no
part in calibration.

The guarantee is about exchangeability between calibration and test scores.
Companies differ, periods are serially dependent, and injected errors are not
drawn from the calibration distribution, so the guarantee covers the
false-flag rate on clean cells only to the degree that held-out clean cells
are exchangeable with development clean cells. The analysis plan states this
and the results report the achieved rate rather than assuming it.

## 3. Faithfulness and attribution of generated text

| Work | What it does | Used here |
|---|---|---|
| Maynez, Narayan, Bohnet and McDonald 2020 | separates faithfulness (consistency with the source) from factuality (truth in the world) for abstractive summaries and studies hallucination in them | the checker tests faithfulness to the evidence record, not truth about the company |
| Ji et al. 2023 | a survey of hallucination in natural language generation, with the distinction between intrinsic (contradicting the source) and extrinsic (not verifiable from the source) hallucination | both kinds are counted as failures: a number that contradicts the evidence and a number that is not in it |
| Rashkin et al. 2023 | attributable to identified sources (AIS): a sentence is attributable if, according to a reader, "according to the source, s" holds | the unit of checking is the sentence, and a sentence is accepted only if every number, line item and period in it is in the evidence record |
| Honovich et al. 2022, TRUE | re-evaluates factual consistency metrics across tasks against human judgements, treating consistency as binary | a binary accept or reject per sentence, with the rejection rate reported |
| Min et al. 2023, FActScore | breaks a generation into atomic facts and scores the share supported by a knowledge source | the share of claims (numbers, line items, periods) verified against the evidence record is reported as the faithfulness score |

Established practice: sentence-level and claim-level verification against a
source. What is different here is that the source is a small structured
record, so verification is exact string and number matching rather than a
learned entailment model, and that a failed sentence is replaced by a
deterministic template rather than reported as a score. The cost of this is
that it only works when the evidence record contains everything a sentence
may say; the ablation in which the model sees raw data instead of the record
is designed to show what happens when it does not.

## 4. Anomaly detection in financial statements, restatements and XBRL data quality

### 4.1 Misstatement and fraud prediction

| Work | What it does | Relation to this repository |
|---|---|---|
| Beneish 1999 | the M-score: a probit model of earnings manipulation from eight financial ratios | a company-year classifier of manipulation; this repository flags individual values, not companies |
| Dechow, Ge, Larson and Sloan 2011 | the F-score: a model predicting material misstatements from accrual quality, performance, non-financial and market variables, on SEC enforcement releases | the same: company-year prediction of misstatement; used here as the reference point for what "detection" usually means in this literature |
| Cecchini, Aytug, Koehler and Pathak 2010 | support vector machines with a financial kernel on basic financial data; 80% of fraudulent and 90.6% of non-fraudulent companies correctly labelled on a holdout set | company-level, black-box scoring |
| Perols 2011 | compares six statistical and machine learning classifiers for financial statement fraud; logistic regression and support vector machines perform well relative to the others | company-level |
| Bao, Ke, Li, Yu and Zhang 2020 | ensemble learning on raw accounting numbers rather than ratios; introduces a ranking metric for fraud prediction; outperforms the Dechow et al. and Cecchini et al. benchmarks | company-level; the use of raw line items rather than ratios is shared |

These models answer "is this company-year likely misstated". This repository
answers "which recorded value in this filing does not fit the rest of the
record", which is a different task with a different unit of analysis, and
does so without a learned classifier.

### 4.2 Restatements as ground truth

| Work | Relevance |
|---|---|
| Hennes, Leone and Miller 2008 | proposes a procedure for classifying restatements as errors (unintentional) or irregularities (intentional); most irregularities are followed by fraud-related lawsuits, errors are not; the market reaction is -14% for irregularities and -2% for errors | the amended filings used as ground truth here are a mix of both; the evaluation does not distinguish them |
| Plumlee and Yohn 2010 | from restating companies' own disclosures, restatements are most often attributed to "basic internal company errors unrelated to any specific characteristic of the accounting standards" | supports the premise that a share of restatements are the kind of error a value-level check could in principle catch |
| SEC Form 8-K, Item 4.02 | a registrant must file an 8-K when it concludes that previously issued financial statements should no longer be relied upon | the company-level restatement signal taken from the EDGAR submissions metadata |

Amended periodic reports (10-K/A, 10-Q/A) are filed for many reasons other
than correcting numbers (adding Part III information, exhibits, signatures).
Only amendments in which an XBRL value for an already reported line item and
period differs from the original count as a real correction here; the rest
are ignored.

### 4.3 XBRL data quality

| Work | What it reports | Used here |
|---|---|---|
| Debreceny, Farewell, Piechocki, Felden and Gräning 2010 | early evidence on data quality problems in XBRL filings to the SEC | the motivation for checking accounting identities on XBRL values |
| Bartley, Chen and Taylor 2011 | errors in the SEC voluntary filing program filings compared with the corresponding 10-Ks, with a reduction over time | the premise that filed XBRL values can differ from the statements |
| Debreceny, Farewell, Piechocki, Felden, Gräning and d'Eri 2011 | 40% of extensions in filings between April 2009 and June 2010 were unnecessary | the reason to use a small fixed set of standard elements and to accept missing values rather than extensions |
| Du, Vasarhelyi and Zheng 2013 | 4,532 filings containing 4,260 errors identified by XBRL Cloud, with the number of errors per filing decreasing as a company files more often | the only per-filing error count found; it counts validation errors of every kind, not wrong values, so it bounds rather than sets the injection rate |
| Chychyla and Kogan 2015 | 30 line items of about 5,000 companies, October 2011 to September 2012: Compustat values differ significantly from 10-K values, with the amount and magnitude depending on the item, industry and size | the reason to work from the filed values rather than a standardised database, and a reminder that the filed values are themselves not error free |

No paper found gives a rate of wrong numeric values per line item in filed
XBRL. The injection rate used here (1% of cells, with 0.5% and 2% as
sensitivity analyses) is therefore a documented assumption, chosen so that
the injected errors are rarer than the validation errors counted by Du et al.
(about 0.94 per filing of some hundreds of facts) and comparable to entry
error rates used in neighbouring work on transcribed records. The error types
(sign flip, scale slip, digit transposition, copy-forward, cross-company swap)
are the mechanical errors described in the XBRL data quality literature and in
the data entry literature; their shares are equal because no source gives
their relative frequency in filings.

### 4.4 Continuous auditing and general anomaly detection

| Work | Relevance |
|---|---|
| Kogan, Alles, Vasarhelyi and Wu 2014 | a continuous data-level auditing framework in which a first layer monitors deterministic business process rules and a second layer does analytical monitoring, with a distinction between exceptions (rule violations) and anomalies (statistical) | the same two layers are used here: identity rules first, plausibility models second, reported separately |
| Chandola, Banerjee and Kumar 2009 | survey of anomaly detection: point, contextual and collective anomalies, and the role of the context in which a value is judged | a value here is a contextual anomaly: judged against the company's own history and the other statements of the same filing |

## 5. The SEC comment-letter process as a model for query text

* SEC Division of Corporation Finance, *Filing Review Process*: the Division
  selectively reviews filings; under section 408 of the Sarbanes-Oxley Act it
  must review each reporting company "at least once every three years"; staff
  issue comments where a company "can significantly enhance its compliance",
  comments may request supplemental information or revised disclosure,
  companies respond in a letter and amend where appropriate, and letters are
  posted on EDGAR "no sooner than 20 business days" after the review ends.
* Cassell, Dreher and Myers 2013: the probability of receiving a 10-K comment
  letter, the extent of comments and the cost of remediation are associated
  with the section 408 factors and with low profitability, complexity, small
  auditors and governance weaknesses; comments on accounting issues cost more
  to remediate.
* Johnston and Petacchi 2017: comment letters as regulatory oversight of
  financial reporting.
* Dechow, Lawrence and Ryans 2016: insider sales before the public release of
  revenue recognition comment letters; letters are downloaded infrequently
  after release.
* Bozanic, Dietrich and Johnson 2017: comment letters and subsequent firm
  disclosure.

What is taken from this: the form of a query. A comment letter cites the
filing, the line item and the period, states what the staff observed and asks
the company to explain or revise. It does not assert what the correct number
is. The query text generated here follows that form, and both the template
and the language-model variant are constrained to the observation and the
request.

## 6. Tamper-evident logs

| Work | What it establishes | Used here |
|---|---|---|
| Haber and Stornetta 1991 | linking time-stamps of documents into a chain so that a document cannot be back-dated without redoing the chain | each log entry carries the hash of the previous entry |
| Schneier and Kelsey 1999 | secure audit logs on an untrusted machine: an attacker who gains control after the fact cannot read or undetectably alter earlier entries | the verification script detects edits, deletions, insertions and reordering of entries written before the tampering; it does not protect against an attacker who rewrites the whole chain, which the limitations say |

## 7. Data source

* SEC EDGAR APIs (data.sec.gov): `companyfacts` returns "all the company
  concepts data for a company into a single API call"; `frames` "aggregates one
  fact for each reporting entity that is last filed" for a calendar period;
  `submissions` gives the filing history with form types. No authentication.
* SEC webmaster FAQ: "our current maximum access rate is 10 requests per
  second" and "Please declare your user agent in request headers" in the form
  `Sample Company Name AdminContact@<sample company domain>.com`. The download
  script sends such a header and stays well under the rate.
* SEC Financial Statement Data Sets page: the data are presented "as filed",
  the SEC "cannot guarantee the accuracy of the data sets", and they are not a
  substitute for the filings. The same holds for the API used here.

## 8. What is established and what is new

Established, and reused without change: Benjamini-Hochberg; split conformal
p-values and their combination with Benjamini-Hochberg (Bates et al. 2023);
the two-layer rules-then-analytics structure of continuous auditing (Kogan et
al. 2014); sentence- and claim-level attribution evaluation (Rashkin et al.
2023, Min et al. 2023); hash-chained logs (Haber and Stornetta 1991); the
expectations on audit trails and validation (Part 11, GAMP 5, CSA).

Not found in the literature searched, and therefore what this repository
contributes:

1. A value-level review of filed financial statement line items in which a
   language model writes query text but never decides what to flag, with the
   decision made by deterministic rules and conformal p-values.
2. Evidence records as the only input to the language model, with a checker
   that rejects any sentence whose numbers, line items or periods are not in
   the record, and a measurement of how often that happens with the record
   against raw data.
3. A determinism requirement tested across runs and machines, and an
   append-only audit log, built into a research pipeline from the start, with
   a validation package that traces each requirement to tests.
4. An evaluation of all of this on held-out companies against real amended
   filings and against injected errors, with the false-flag rate reported
   against its target.

None of these is a new method. The claim is about the combination and its
measurement.

## References

Angelopoulos, A. N. and Bates, S. (2023). Conformal Prediction: A Gentle
Introduction. *Foundations and Trends in Machine Learning*, 16(4), 494-591.
https://doi.org/10.1561/2200000101

Bao, Y., Ke, B., Li, B., Yu, Y. J. and Zhang, J. (2020). Detecting Accounting
Fraud in Publicly Traded U.S. Firms Using a Machine Learning Approach.
*Journal of Accounting Research*, 58(1), 199-235.
https://doi.org/10.1111/1475-679X.12292

Bartley, J., Chen, A. Y. S. and Taylor, E. Z. (2011). A Comparison of XBRL
Filings to Corporate 10-Ks: Evidence from the Voluntary Filing Program.
*Accounting Horizons*, 25(2), 227-245. https://doi.org/10.2308/acch-10028

Bates, S., Candès, E., Lei, L., Romano, Y. and Sesia, M. (2023). Testing for
outliers with conformal p-values. *The Annals of Statistics*, 51(1), 149-178.
https://doi.org/10.1214/22-AOS2244

Beneish, M. D. (1999). The Detection of Earnings Manipulation. *Financial
Analysts Journal*, 55(5), 24-36. https://doi.org/10.2469/faj.v55.n5.2296

Benjamini, Y. and Hochberg, Y. (1995). Controlling the False Discovery Rate: A
Practical and Powerful Approach to Multiple Testing. *Journal of the Royal
Statistical Society Series B*, 57(1), 289-300.
https://doi.org/10.1111/j.2517-6161.1995.tb02031.x

Bozanic, Z., Dietrich, J. R. and Johnson, B. A. (2017). SEC comment letters and
firm disclosure. *Journal of Accounting and Public Policy*, 36(5), 337-357.
https://doi.org/10.1016/j.jaccpubpol.2017.07.004

Cassell, C. A., Dreher, L. M. and Myers, L. A. (2013). Reviewing the SEC's
Review Process: 10-K Comment Letters and the Cost of Remediation. *The
Accounting Review*, 88(6), 1875-1908. https://doi.org/10.2308/accr-50538

Cecchini, M., Aytug, H., Koehler, G. J. and Pathak, P. (2010). Detecting
Management Fraud in Public Companies. *Management Science*, 56(7), 1146-1160.
https://doi.org/10.1287/mnsc.1100.1174

Chandola, V., Banerjee, A. and Kumar, V. (2009). Anomaly detection: A survey.
*ACM Computing Surveys*, 41(3), 1-58. https://doi.org/10.1145/1541880.1541882

Chychyla, R. and Kogan, A. (2015). Using XBRL to Conduct a Large-Scale Study of
Discrepancies between the Accounting Numbers in Compustat and SEC 10-K Filings.
*Journal of Information Systems*, 29(1), 37-72.
https://doi.org/10.2308/isys-50922

Debreceny, R., Farewell, S., Piechocki, M., Felden, C. and Gräning, A. (2010).
Does it add up? Early evidence on the data quality of XBRL filings to the SEC.
*Journal of Accounting and Public Policy*, 29(3), 296-306.
https://doi.org/10.1016/j.jaccpubpol.2010.04.001

Debreceny, R. S., Farewell, S. M., Piechocki, M., Felden, C., Gräning, A. and
d'Eri, A. (2011). Flex or Break? Extensions in XBRL Disclosures to the SEC.
*Accounting Horizons*, 25(4), 631-657. https://doi.org/10.2308/acch-50068

Dechow, P. M., Ge, W., Larson, C. R. and Sloan, R. G. (2011). Predicting
Material Accounting Misstatements. *Contemporary Accounting Research*, 28(1),
17-82. https://doi.org/10.1111/j.1911-3846.2010.01041.x

Dechow, P. M., Lawrence, A. and Ryans, J. P. (2016). SEC Comment Letters and
Insider Sales. *The Accounting Review*, 91(2), 401-439.
https://doi.org/10.2308/accr-51232

Du, H., Vasarhelyi, M. A. and Zheng, X. (2013). XBRL Mandate: Thousands of
Filing Errors and So What? *Journal of Information Systems*, 27(1), 61-78.
https://doi.org/10.2308/isys-50399

Haber, S. and Stornetta, W. S. (1991). How to time-stamp a digital document.
*Journal of Cryptology*, 3(2), 99-111. https://doi.org/10.1007/BF00196791

Hennes, K. M., Leone, A. J. and Miller, B. P. (2008). The Importance of
Distinguishing Errors from Irregularities in Restatement Research: The Case of
Restatements and CEO/CFO Turnover. *The Accounting Review*, 83(6), 1487-1519.
https://doi.org/10.2308/accr.2008.83.6.1487

Honovich, O., Aharoni, R., Herzig, J., Taitelbaum, H., Kukliansy, D., Cohen,
V., Scialom, T., Szpektor, I., Hassidim, A. and Matias, Y. (2022). TRUE:
Re-evaluating Factual Consistency Evaluation. *Proceedings of the 2022
Conference of the North American Chapter of the Association for Computational
Linguistics: Human Language Technologies*, 3905-3920.
https://doi.org/10.18653/v1/2022.naacl-main.287

Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., Ishii, E., Bang, Y. J.,
Madotto, A. and Fung, P. (2023). Survey of Hallucination in Natural Language
Generation. *ACM Computing Surveys*, 55(12), 1-38.
https://doi.org/10.1145/3571730

Johnston, R. and Petacchi, R. (2017). Regulatory Oversight of Financial
Reporting: Securities and Exchange Commission Comment Letters. *Contemporary
Accounting Research*, 34(2), 1128-1155. https://doi.org/10.1111/1911-3846.12297

Kogan, A., Alles, M. G., Vasarhelyi, M. A. and Wu, J. (2014). Design and
Evaluation of a Continuous Data Level Auditing System. *Auditing: A Journal of
Practice and Theory*, 33(4), 221-245. https://doi.org/10.2308/ajpt-50844

Maynez, J., Narayan, S., Bohnet, B. and McDonald, R. (2020). On Faithfulness
and Factuality in Abstractive Summarization. *Proceedings of the 58th Annual
Meeting of the Association for Computational Linguistics*, 1906-1919.
https://doi.org/10.18653/v1/2020.acl-main.173

Min, S., Krishna, K., Lyu, X., Lewis, M., Yih, W., Koh, P. W., Iyyer, M.,
Zettlemoyer, L. and Hajishirzi, H. (2023). FActScore: Fine-grained Atomic
Evaluation of Factual Precision in Long Form Text Generation. *Proceedings of
the 2023 Conference on Empirical Methods in Natural Language Processing*,
12076-12100. https://doi.org/10.18653/v1/2023.emnlp-main.741

Perols, J. (2011). Financial Statement Fraud Detection: An Analysis of
Statistical and Machine Learning Algorithms. *Auditing: A Journal of Practice
and Theory*, 30(2), 19-50. https://doi.org/10.2308/ajpt-50009

Plumlee, M. and Yohn, T. L. (2010). An Analysis of the Underlying Causes
Attributed to Restatements. *Accounting Horizons*, 24(1), 41-64.
https://doi.org/10.2308/acch.2010.24.1.41

Rashkin, H., Nikolaev, V., Lamm, M., Aroyo, L., Collins, M., Das, D., Petrov,
S., Tomar, G. S., Turc, I. and Reitter, D. (2023). Measuring Attribution in
Natural Language Generation Models. *Computational Linguistics*, 49(4),
777-840. https://doi.org/10.1162/coli_a_00486

Schneier, B. and Kelsey, J. (1999). Secure audit logs to support computer
forensics. *ACM Transactions on Information and System Security*, 2(2),
159-176. https://doi.org/10.1145/317087.317089

Vovk, V., Gammerman, A. and Shafer, G. (2005). *Algorithmic Learning in a
Random World*. Springer. https://doi.org/10.1007/b106715 (second edition 2022,
https://doi.org/10.1007/978-3-031-06649-8)

Regulatory and standards documents (no DOI):

* 21 CFR Part 11, Electronic Records; Electronic Signatures, section 11.10,
  current eCFR text. https://www.ecfr.gov/current/title-21/part-11
* FDA (2003). Part 11, Electronic Records; Electronic Signatures: Scope and
  Application. Guidance for Industry.
  https://www.fda.gov/regulatory-information/search-fda-guidance-documents/part-11-electronic-records-electronic-signatures-scope-and-application
* FDA (2026). Computer Software Assurance for Production and Quality
  Management System Software. Final guidance, February 2026, docket
  FDA-2022-D-0795.
  https://www.fda.gov/regulatory-information/search-fda-guidance-documents/computer-software-assurance-production-and-quality-management-system-software
* ISPE (2022). GAMP 5: A Risk-Based Approach to Compliant GxP Computerized
  Systems, second edition.
  https://ispe.org/publications/guidance-documents/gamp-5-guide-2nd-edition
* Sarbanes-Oxley Act of 2002, Public Law 107-204, 116 Stat. 745.
  https://www.govinfo.gov/content/pkg/PLAW-107publ204/html/PLAW-107publ204.htm
* SEC, Division of Corporation Finance, Filing Review Process.
  https://www.sec.gov/divisions/corpfin/cffilingreview.htm
* SEC, EDGAR Application Programming Interfaces.
  https://www.sec.gov/search-filings/edgar-application-programming-interfaces
* SEC, Webmaster Frequently Asked Questions (access rate and user agent).
  https://www.sec.gov/about/webmaster-frequently-asked-questions
* SEC, Financial Statement Data Sets.
  https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets
* SEC, Form 8-K, Item 4.02. https://www.sec.gov/files/form8-k.pdf
