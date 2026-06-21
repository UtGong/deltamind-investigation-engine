.PHONY: test-backend eval-local backend-dev

test-backend:
	cd backend && python -m compileall app && python -m pytest --cache-clear

backend-dev:
	cd backend && uvicorn app.main:app --reload

eval-local:
	cd backend && ./scripts/eval_local.sh
