# Security policy

## Scope

The code in this repository downloads public data from SEC EDGAR, runs
deterministic checks on it, optionally calls a language model API or a local
model server to write query text, and writes a hash-chained audit log. It does
not handle credentials beyond an optional API key read from the environment,
and it does not run a network service.

Issues in scope:

- the audit log accepting a tampered chain as valid, or the verification
  script failing to detect an edit, deletion, insertion or reordering it is
  documented to detect
- the faithfulness checker accepting a sentence with a number, line item or
  period that is not in the evidence record
- the download script sending anything other than the declared user agent, or
  exceeding the SEC access rate
- unsafe handling of the API key (for example writing it to the audit log or
  to results)

Out of scope: the accuracy of SEC data, model output quality as such, and
denial of service against the user's own machine.

## Reporting

Please report vulnerabilities by email to j.kowalczuk326@gmail.com with
"evidence-grounded-review security" in the subject. Do not open a public issue
for a vulnerability. You will get an acknowledgement within seven days and a
fix or a documented decision within thirty.

## Supported versions

Only the latest release on `main` receives fixes.
