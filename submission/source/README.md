# Sanjiv final project document source

`generate_sanjiv_submission.py` is the editable ReportLab source for the submission PDF.
It reads the repository's committed screenshots and the reviewed values in
`evidence_snapshot.json`, then creates:

- `output/pdf/Sanjiv_Final_Project_Document.pdf`
- `submission/Sanjiv_Final_Project_Document.pdf`

Run from the repository root with the bundled Codex Python runtime or any Python 3.11+
environment containing ReportLab and Pillow:

```powershell
python submission/source/generate_sanjiv_submission.py
```

The source deliberately labels local benchmarks as fixture/replay evidence, identifies the
`current_commit_sha` as the product-evidence commit rather than an ambiguous repository-head claim,
and uses only real Playwright application screenshots from `reports/e2e/screenshots/`. The submitted
demo duration is recorded as 3 min 55 sec from the submitter's confirmation. Intermediate screenshot
crops and rendered QA pages are written under `tmp/pdfs/`.

Before regenerating after repository changes, re-verify every value in `evidence_snapshot.json`
against the named reports and update the product-evidence commit intentionally.
