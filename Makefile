PYTHON ?= python
EVAL_ARGS ?=

.PHONY: eval eval-data eval-test
eval-data:
	$(PYTHON) -m evals.prepare

eval: eval-data
	$(PYTHON) -m evals.run $(EVAL_ARGS)

eval-test:
	$(PYTHON) -m pytest -q evals/tests
