.PHONY: install setup test run clean

# Override with: make run EXPERIMENT=initial_paper_reproduction
EXPERIMENT ?= baseline

install:
	poetry install

setup:
	bash scripts/setup.sh

test:
	poetry run pytest pipeline/tests/ -v

run: setup
	bash scripts/run_experiment.sh experiments/$(EXPERIMENT)/config.json

clean:
	rm -rf outputs/
