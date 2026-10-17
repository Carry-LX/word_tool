"""Exercise real simultaneous Windows JSON readers and an atomic writer."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from demo_runtime import PROJECT_DIR, read_json, write_json

TARGET = PROJECT_DIR / "outputs/web_demo_validation/state_contention.json"
ITERATIONS = 250


def main():
    write_json(TARGET, {"sequence": -1, "payload": "节点结果" * 1000})
    stop = threading.Event()
    def read_many():
        count = 0
        while not stop.is_set():
            value = read_json(TARGET)
            assert isinstance(value["sequence"], int) and value["payload"] == "节点结果" * 1000
            count += 1
        return count
    with ThreadPoolExecutor(max_workers=4) as pool:
        readers = [pool.submit(read_many) for _ in range(4)]
        try:
            for sequence in range(ITERATIONS):
                write_json(TARGET, {"sequence": sequence, "payload": "节点结果" * 1000})
        finally:
            stop.set()
        counts = [reader.result() for reader in readers]
    assert read_json(TARGET)["sequence"] == ITERATIONS - 1
    result = {"status": "pass", "writes": ITERATIONS, "concurrent_reads": sum(counts)}
    write_json(TARGET.parent / "state_io_check.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
