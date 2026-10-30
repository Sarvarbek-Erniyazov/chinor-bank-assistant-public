# Manual audit

`audit_sample_ids.json` holds 60 item ids drawn with seed 20261027 (30 task
items from T-seen/T-held, 30 behaviour items from B1–B4/R). For each arm, copy
`audit_sheet_template.csv` to `audit_<arm>.csv`, fill `manual_pass` (1/0) from
the raw answers in `eval/outputs/<arm>/answers.jsonl`, and compare with
`scores.jsonl` to estimate the automatic scorer's disagreement rate.
