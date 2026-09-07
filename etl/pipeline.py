#!/usr/bin/env python3
"""
ETL Pipeline — Excel → PostgreSQL (star schema)
Usage: python pipeline.py <path_to_excel_file>
"""

import sys
import time

from config import DATABASE_URL
from etl.extract import extract
from etl.transform import transform
from etl.load import load


def run(filepath: str) -> None:
    start = time.time()

    print(f"[extract] Reading {filepath}")
    frames = extract(filepath)
    for name, df in frames.items():
        print(f"  {name}: {len(df):,} rows")

    print("[transform] Cleaning data and building dimensions")
    frames, dimensions = transform(frames)
    for name, df in dimensions.items():
        print(f"  {name}: {len(df):,} members")

    print("[load] Writing to PostgreSQL")
    counts = load(frames, dimensions, DATABASE_URL)
    print("  Dimensions:")
    for name in dimensions:
        tbl = name  # dim_entity etc.
        print(f"    {tbl}: {counts.get(tbl, '?'):,} rows")
    print("  Facts:")
    for tbl in ["fact_financials", "raw_outputs", "fact_employee"]:
        print(f"    {tbl}: {counts.get(tbl, '?'):,} rows")

    elapsed = time.time() - start
    print(f"[done] Completed in {elapsed:.1f}s")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pipeline.py <path_to_excel_file>")
        sys.exit(1)
    run(sys.argv[1])
