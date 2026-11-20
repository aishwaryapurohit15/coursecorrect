"""Helpers to load the simulated dataset through the agent into the store."""
import json
from concurrent.futures import ThreadPoolExecutor

from .agent import process
from .config import DATASET_PATH
from . import store


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text())


def run_dataset(con, backend: str, ids=None, workers: int = 8, progress=None) -> list[tuple[dict, dict]]:
    ds = load_dataset()
    roster = ds["roster"]
    refls = [r for r in ds["reflections"] if ids is None or r["id"] in ids]
    w = 1 if backend == "offline" else workers
    done = []

    def one(r):
        return r, process({**r, "source": "simulated"}, backend, roster)

    with ThreadPoolExecutor(max_workers=w) as ex:
        for i, (r, res) in enumerate(ex.map(one, refls)):
            store.save(con, {**r, "source": "simulated"}, res)
            done.append((r, res))
            if progress:
                progress((i + 1) / len(refls))
    store.audit(con, "admin", "load_dataset", f"{len(done)} reflections via {backend}")
    return done
