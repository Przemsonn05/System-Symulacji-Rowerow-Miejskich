import argparse
import json
from pathlib import Path

from .engine import run_simulation
from .experiments import run_experiments
from .inputs import load_inputs, prepare_inputs


def main():
    parser = argparse.ArgumentParser(description="Veturilo DES: przygotowanie danych, pojedynczy przebieg, H3")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--out", default="results/inputs")
    prepare.add_argument("--processed", default="processed")
    prepare.add_argument("--day", default="2026-11-03")
    prepare.add_argument("--example", action="store_true")
    prepare.add_argument("--approximate-roads", action="store_true")
    single = commands.add_parser("run")
    single.add_argument("--inputs", default="results/inputs")
    single.add_argument("--scenario", choices=["none", "operator", "threshold"], default="threshold")
    single.add_argument("--trucks", type=int, default=2)
    single.add_argument("--seed", type=int, default=1000)
    single.add_argument("--hours", type=float, default=24)
    single.add_argument("--out", default="results/single")
    experiment = commands.add_parser("experiment")
    experiment.add_argument("--inputs", default="results/inputs")
    experiment.add_argument("--out", default="results/h3")
    experiment.add_argument("--replications", type=int, default=30)
    experiment.add_argument("--jobs", type=int, default=2)
    experiment.add_argument("--seed-start", type=int, default=1000)
    experiment.add_argument("--hours", type=float, default=24)
    args = parser.parse_args()
    if args.command == "prepare":
        params = prepare_inputs(args.out, args.day, args.processed, args.example, not args.approximate_roads)
        print(f"Prepared {len(params.stations)} stations in {Path(args.out).resolve()}")
    elif args.command == "run":
        params = load_inputs(args.inputs, duration_min=args.hours * 60, n_trucks=args.trucks, output_dir=args.out)
        result = run_simulation(params, args.scenario, args.seed)
        print(json.dumps(result.kpis, indent=2))
    else:
        params = load_inputs(args.inputs, duration_min=args.hours * 60)
        run_experiments(params, args.out, args.replications, args.jobs, args.seed_start)
        print(f"Results: {(Path(args.out) / 'REPORT.md').resolve()}")


if __name__ == "__main__":
    main()
