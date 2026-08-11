from pathlib import Path

from experiments.experiment_orchestration import run_experiment

if __name__ == "__main__":
    run_experiment(Path(__file__).parent / "config.json")
