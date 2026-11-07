"""Manifest wersji danych: processed/MANIFEST.json (zakres dat, liczba dni, sumy kontrolne plikow).

    python -m src.data.manifest                    # po python -m src.data.build
    python -m src.data.manifest --label dane-final # 1.12: zamrozenie danych (potem: git tag dane-final)

Wszystkie wyniki koncowe licza sie na wersji "dane-final". Kazdy, kto liczy wyniki, moze sprawdzic,
czy ma te sama wersje: python -m src.data.manifest --check (porownuje sumy z zapisanym manifestem).

Zamrozenie danych 1.12 (Osoba 1):
  1. wylacz harmonogram w .github/workflows/collect.yml (sekcja schedule) - od 1.12 feed jest pusty,
  2. git pull (ostatnie dane), python -m src.data.build, python -m src.data.manifest --label dane-final,
  3. git add data processed/MANIFEST.json && git commit && git tag dane-final && git push --tags.
"""

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys

import pandas as pd

from .config import DATA, PROCESSED, ROOT


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def build_manifest(label=None):
    files = {}
    for p in sorted(PROCESSED.glob("*")):
        if p.is_file() and p.name != "MANIFEST.json":
            entry = {"bytes": p.stat().st_size, "sha256": sha256(p)}
            if p.suffix == ".parquet":
                import pyarrow.parquet as pq

                entry["rows"] = pq.ParquetFile(p).metadata.num_rows
            files[p.name] = entry
    raw = sorted(DATA.glob("status/*.jsonl.gz"))
    obs = pd.read_parquet(PROCESSED / "observed_timeseries.parquet", columns=["time"])
    check = pd.read_parquet(PROCESSED / "daily_check.parquet") if (PROCESSED / "daily_check.parquet").exists() else None
    out = {
        "label": label or "robocza",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "range_utc": [obs["time"].min().isoformat(), obs["time"].max().isoformat()],
        "raw_status_files": [p.name for p in raw],
        "files": files,
    }
    if check is not None:
        full = check[check["full_day"]]
        out["days"] = {
            "all": int(len(check)), "full": int(len(full)),
            "workdays_full": int((full["day_type"] == "workday").sum()),
            "wind_down": [str(d) for d in check.loc[check["wind_down"], "local_date"]],
            "first": str(check["local_date"].min()), "last": str(check["local_date"].max()),
        }
    return out


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", help="nazwa wersji, np. dane-final")
    ap.add_argument("--check", action="store_true", help="porownaj processed/ z zapisanym MANIFEST.json")
    args = ap.parse_args(argv)
    path = PROCESSED / "MANIFEST.json"
    if args.check:
        saved = json.loads(path.read_text(encoding="utf-8"))
        bad = [n for n, e in saved["files"].items()
               if not (PROCESSED / n).exists() or sha256(PROCESSED / n) != e["sha256"]]
        print(f"Wersja {saved['label']} ({saved['created_utc']}): " +
              ("zgodna" if not bad else f"ROZNICE w {len(bad)} plikach: {', '.join(bad)}"))
        sys.exit(1 if bad else 0)
    m = build_manifest(args.label)
    path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    d = m.get("days", {})
    print(f"MANIFEST.json: wersja {m['label']}, {len(m['files'])} plikow, dni pelne {d.get('full')} "
          f"(robocze {d.get('workdays_full')}), zakres {m['range_utc'][0][:16]} - {m['range_utc'][1][:16]} UTC")


if __name__ == "__main__":
    main()
