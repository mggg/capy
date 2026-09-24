.PHONY: install setup test run clean

install:
	poetry install

setup:
	bash scripts/setup.sh

test:
	poetry run pytest capy_core/tests/ -v

run: setup
	bash scripts/reproduce.sh

clean:
	rm -rf data/shared/outputs/
