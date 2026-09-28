import json
import subprocess
import sys


def test_catalog_exports_a_loaded_eval(tmp_path):
    folder = tmp_path / "concepts" / "units"
    (folder / "workspace").mkdir(parents=True)
    (folder / "scorer").mkdir()
    (folder / "eval.yaml").write_text(
        "type: quiz\nmotivation: Check units.\nprompt: How many wei?\n"
        "modes: [vanilla, internet]\nchoices: null\n"
    )
    (folder / "workspace" / "note.txt").write_text("public")
    (folder / "scorer" / "scorer.yaml").write_text('kind: target\ntarget: "1000000000000000000"\n')
    output = tmp_path / "export"
    result = subprocess.run(
        [sys.executable, "-m", "ethevals.cli", "catalog", "--evals", str(folder), "--output", str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((output / "catalog.json").read_text()) == [{
        "id": "concepts/units",
        "hash": "c5f85234d93dac71e7b7e805df2c924d8687da707ceb43026e429d1bdc498d57",
        "pillar": "concepts", "type": "quiz", "motivation": "Check units.",
        "prompt": "How many wei?", "modes": ["vanilla", "internet"], "choices": None,
    }]
