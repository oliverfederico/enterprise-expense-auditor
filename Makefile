.PHONY: install test audit eval clean

install:
	uv sync --dev

test:
	uv run pytest -v

audit:
	uv run python -m expense_auditor.cli

eval:
	uv run python -m evaluation.run_eval

clean:
	rm -rf __pycache__ .pytest_cache .coverage htmlcov .mypy_cache
