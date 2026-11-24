import tomllib

import pytest

from ethevals.harbor_tasks import lint_task
from test_jobs import task_folder


@pytest.mark.parametrize("pillar", ["build", "act"])
@pytest.mark.parametrize("tags,error", [
    ("", "must declare a metadata.checks table"),
    ('checks = "gate"\n', "must declare a metadata.checks table"),
    ("[metadata.checks]\n", "missing check tags: test_transfer"),
    ('[metadata.checks]\ntest_transfer = "bonus"\n', "must be tagged gate or judgment"),
    ('[metadata.checks]\ntest_transfer = ["gate"]\n', "must be tagged gate or judgment"),
    ('[metadata.checks]\ntest_transfer = "gate"\ntest_old = "judgment"\n', "unknown check tags: test_old"),
    ('[metadata.checks]\ntest_transfer = "gate"\n" " = "judgment"\n', "needs nonempty check names"),
])
def test_lint_rejects_bad_forge_tags(tmp_path, pillar, tags, error):
    task = task_folder(tmp_path, pillar=pillar)
    (task / "tests/Transfer.t.sol").write_text("function test_transfer() public {}\n")
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace("[metadata.checks]\n", tags))

    with pytest.raises(ValueError, match=error):
        lint_task(task)


def test_lint_accepts_a_custom_check_alongside_forge_tests(tmp_path):
    task = task_folder(tmp_path, pillar="build")
    (task / "tests/Transfer.t.sol").write_text("function test_transfer() public {}\n")
    (task / "tests/receipt.py").write_text('import rewardkit as rk\nrk.file_exists("receipt.txt", name="receipt")\n')
    settings = task / "task.toml"
    settings.write_text(settings.read_text() + 'test_transfer = "gate"\nreceipt = "judgment"\n')

    lint_task(task)


@pytest.mark.parametrize("name", ["compile", "answered", "no_answer", "report_written"])
def test_lint_rejects_a_tag_for_an_entry_check(tmp_path, name):
    task = task_folder(tmp_path, pillar="build")
    settings = task / "task.toml"
    settings.write_text(settings.read_text() + f'{name} = "gate"\n')

    with pytest.raises(ValueError, match=f"entry check '{name}' cannot have a tag"):
        lint_task(task)


def test_lint_rejects_a_duplicate_tag(tmp_path):
    task = task_folder(tmp_path, pillar="act")
    settings = task / "task.toml"
    settings.write_text(settings.read_text() + 'transfer = "gate"\ntransfer = "judgment"\n')

    with pytest.raises(tomllib.TOMLDecodeError):
        lint_task(task)


def test_lint_rejects_check_tags_on_concepts_tasks(tmp_path):
    task = task_folder(tmp_path)
    settings = task / "task.toml"
    settings.write_text(settings.read_text() + "\n[metadata.checks]\n")

    with pytest.raises(ValueError, match="Concepts tasks cannot declare metadata.checks"):
        lint_task(task)


@pytest.mark.parametrize("pillar", ["concepts", "build"])
def test_lint_rejects_an_unknown_metadata_key(tmp_path, pillar):
    task = task_folder(tmp_path, pillar=pillar)
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace("[metadata]\n", '[metadata]\ndifficulty = "hard"\n'))

    with pytest.raises(ValueError, match="unknown metadata keys: difficulty"):
        lint_task(task)
