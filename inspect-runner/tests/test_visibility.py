"""Keep publication and the site's scored rows tied to one fixture."""
import json
import subprocess
from pathlib import Path

from ethevals.publish import publish_logs


def test_publish_and_site_use_the_same_final_rows(tmp_path):
    directory = Path(__file__).parent
    fixture = json.loads((directory / "fixtures/row-visibility.json").read_text())
    published = []
    for case in fixture["cases"]:
        root = tmp_path / case["name"]
        output = root / "results"
        (output / "logs").mkdir(parents=True)
        (output / "logs/epoch.eval").write_bytes(b"fixture")
        (root / "evals").mkdir()
        (root / "site/.catalog").mkdir(parents=True)
        (root / "site/.catalog/catalog.json").write_text(json.dumps(fixture["catalog"]))
        row = {**fixture["row"], **case["changes"]}
        (output / "rows.jsonl").write_text(json.dumps(row) + "\n")
        plan = publish_logs(output, "example/ethevals", "fixture", "a" * 40,
                            current_hashes={"concepts/units": "current"})
        assert bool(plan["assets"]) == case["publish"], case["name"]
        if plan["assets"]:
            published.append(case["name"])
    site = directory.parents[1] / "site"
    result = subprocess.run([str(site / "node_modules/.bin/tsx"), str(directory / "prove_visibility.ts"), str(tmp_path)],
                            cwd=site, text=True, capture_output=True, check=True)
    assert published == json.loads(result.stdout.splitlines()[-1]) == ["passed", "failed"]
