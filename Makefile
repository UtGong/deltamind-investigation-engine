.PHONY: test-backend eval-local backend-dev

test-backend:
	cd backend && python -m compileall app && python -m pytest --cache-clear

backend-dev:
	cd backend && uvicorn app.main:app --reload

eval-local:
	cd backend && ./scripts/eval_local.sh

learn-local:
	cd backend && python scripts/update_source_reliability_from_eval.py \
	  --predictions data/eval/predictions.jsonl \
	  --output data/eval/reports/latest_learning_report.md \
	  --json-output data/eval/reports/latest_learning_report.json

learn-local-db:
	cd backend && python scripts/update_source_reliability_from_eval.py \
	  --predictions data/eval/predictions.jsonl \
	  --output data/eval/reports/latest_learning_report.md \
	  --json-output data/eval/reports/latest_learning_report.json \
	  --topic eval:nba \
	  --claim-type unknown \
	  --write-db



export-certificate:
	cd backend && python scripts/export_trust_certificate.py \
	  --case-id $(CASE_ID) \
	  --output data/certificates/$(CASE_ID)_trust_certificate.json
