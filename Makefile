.PHONY: install setup test run clean

# Override with: make run EXPERIMENT=initial_paper_reproduction
EXPERIMENT ?= baseline

install:
	poetry install

setup:
	bash scripts/setup.sh

test:
	poetry run pytest capy_core/tests/ -v

run: setup
	bash scripts/run_experiment.sh experiment_code/$(EXPERIMENT)/config.json

clean:
	rm -rf data/shared/outputs/
