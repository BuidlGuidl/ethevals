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
    (folder / "scorer" / "target.yaml").write_text('target: "1000000000000000000"\n')
    output = tmp_path / "export"
    result = subprocess.run(
        [sys.executable, "-m", "ethevals.cli", "catalog", "--evals", str(folder), "--output", str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((output / "catalog.json").read_text()) == [{
        "id": "concepts/units",
        "hash": "a1d1e1a5ef44c9e62560659297fd0c1771b030d190cc2b30ab14a5eeaab47d68",
        "pillar": "concepts", "type": "quiz", "motivation": "Check units.",
        "prompt": "How many wei?", "modes": ["vanilla", "internet"], "choices": None,
    }]
