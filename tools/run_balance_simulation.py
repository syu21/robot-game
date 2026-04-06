#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.balance_simulator import export_matchup_matrix, simulate_all_matchups, simulate_series
from services.balance_templates import (
    BALANCE_FAMILY_LABELS,
    BALANCE_FAMILY_ORDER,
    get_balance_template_catalog,
    get_balance_templates_for_family,
)


def _pair_family_key(raw_value):
    value = str(raw_value or "").strip().lower()
    aliases = {
        "tank": "tank",
        "fortress": "tank",
        "stable": "stable",
        "accuracy": "accuracy",
        "sniper": "accuracy",
        "crit": "crit",
        "critical": "crit",
        "burst": "burst",
        "explosive": "burst",
        "berserk": "berserk",
        "desperate": "berserk",
        "balance": "balance",
    }
    if value not in aliases:
        raise SystemExit(f"unknown family: {raw_value}")
    return aliases[value]


def _write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _write_pair_csv(path, row):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    columns = [
        "a_family",
        "a_family_label",
        "a_template_key",
        "a_template_label",
        "b_family",
        "b_family_label",
        "b_template_key",
        "b_template_label",
        "total_trials",
        "a_win_rate",
        "b_win_rate",
        "draw_rate",
        "avg_turns",
        "a_first_strike_rate",
        "b_first_strike_rate",
        "avg_damage_dealt_a",
        "avg_damage_dealt_b",
        "avg_damage_taken_a",
        "avg_damage_taken_b",
        "crit_rate_a",
        "crit_rate_b",
        "miss_rate_a",
        "miss_rate_b",
        "timeout_rate",
        "berserk_trigger_rate_a",
        "berserk_trigger_rate_b",
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerow({key: row.get(key) for key in columns})


def _print_pair_result(result):
    print(f"{result['a_template_label']} vs {result['b_template_label']}")
    print(f"総試行数: {result['total_trials']}")
    print(f"A勝率: {result['a_win_rate']:.3f}")
    print(f"B勝率: {result['b_win_rate']:.3f}")
    print(f"引き分け率: {result['draw_rate']:.3f}")
    print(f"平均ターン数: {result['avg_turns']:.2f}")
    print(f"先手率A: {result['a_first_strike_rate']:.3f}")
    print(f"先手率B: {result['b_first_strike_rate']:.3f}")
    print(f"平均与ダメA: {result['avg_damage_dealt_a']:.2f}")
    print(f"平均与ダメB: {result['avg_damage_dealt_b']:.2f}")
    print(f"会心率A: {result['crit_rate_a']:.3f}")
    print(f"会心率B: {result['crit_rate_b']:.3f}")
    print(f"MISS率A: {result['miss_rate_a']:.3f}")
    print(f"MISS率B: {result['miss_rate_b']:.3f}")
    print(f"8ターン切れ率: {result['timeout_rate']:.3f}")
    print(f"背水発動率A: {result['berserk_trigger_rate_a']:.3f}")
    print(f"背水発動率B: {result['berserk_trigger_rate_b']:.3f}")
    print(f"seed再現性: {result['seed_check']['verified']}")


def _print_matrix(report):
    family_order = list(report.get("family_order") or [])
    header = ["type"] + [BALANCE_FAMILY_LABELS.get(key, key) for key in family_order]
    widths = [max(len(item), 8) for item in header]
    print(" | ".join(header[idx].ljust(widths[idx]) for idx in range(len(header))))
    print("-+-".join("-" * width for width in widths))
    matrix = report.get("family_matrix") or {}
    for row_key in family_order:
        row = [BALANCE_FAMILY_LABELS.get(row_key, row_key)]
        for col_key in family_order:
            cell = ((matrix.get(row_key) or {}).get(col_key) or {})
            row.append(f"{float(cell.get('a_win_rate') or 0.0):.3f}")
        print(" | ".join(row[idx].ljust(widths[idx]) for idx in range(len(row))))


def _print_summary(report):
    summary = report.get("summary") or {}
    if summary.get("danger_matchups"):
        print("\n危険対面:")
        for row in summary["danger_matchups"][:10]:
            print(
                f"- {row['a_family_label']} > {row['b_family_label']}: "
                f"{float(row['a_win_rate']):.3f}"
            )
    if summary.get("dead_families"):
        print("\n死んでいる型候補:")
        for row in summary["dead_families"]:
            print(f"- {row['family_label']}: {float(row['overall_win_rate']):.3f}")
    if summary.get("omni_candidates"):
        print("\n万能型候補:")
        for row in summary["omni_candidates"]:
            print(f"- {row['family_label']}: {float(row['overall_win_rate']):.3f}")


def main():
    parser = argparse.ArgumentParser(description="Run balance simulations for Robolabo battle templates.")
    parser.add_argument("--n", type=int, default=1000, help="number of matches per template pair")
    parser.add_argument("--seed", type=int, default=1000, help="base seed for reproducible runs")
    parser.add_argument("--pair", nargs=2, metavar=("A", "B"), help="run one family pair only, e.g. tank burst")
    parser.add_argument("--export", choices=("csv", "json"), help="export format")
    parser.add_argument("--output", help="path for export output")
    args = parser.parse_args()

    catalog = get_balance_template_catalog()
    if args.pair:
        family_a = _pair_family_key(args.pair[0])
        family_b = _pair_family_key(args.pair[1])
        rows = []
        pair_seed = int(args.seed)
        for a_variant in get_balance_templates_for_family(family_a):
            for b_variant in get_balance_templates_for_family(family_b):
                rows.append(
                    simulate_series(
                        a_variant,
                        b_variant,
                        n=args.n,
                        seed_base=pair_seed,
                    )
                )
                pair_seed += 100000
        for row in rows:
            _print_pair_result(row)
            print("")
        if args.export == "json":
            payload = json.dumps(rows, ensure_ascii=False, indent=2)
            if args.output:
                _write_text(args.output, payload)
            else:
                print(payload)
        elif args.export == "csv":
            path = args.output or os.path.join("tmp", f"balance_pair_{family_a}_{family_b}.csv")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=sorted(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            print(f"exported: {path}")
        return

    report = simulate_all_matchups(catalog, n=args.n, seed_base=args.seed)
    _print_matrix(report)
    _print_summary(report)
    if args.export == "json":
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            _write_text(args.output, payload)
            print(f"exported: {args.output}")
        else:
            print(payload)
    elif args.export == "csv":
        csv_text = export_matchup_matrix(report, format="csv")
        if args.output:
            _write_text(args.output, csv_text)
            print(f"exported: {args.output}")
        else:
            print("\n" + csv_text)


if __name__ == "__main__":
    main()
