from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class SourceSnapshotTest(unittest.TestCase):
    def test_reads_nested_source_without_dependencies_or_external_links(self):
        script = Path(__file__).with_name("source_snapshot.py")
        spec = spec_from_file_location("savings_source_snapshot", script)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            (project / "src/savings").mkdir(parents=True)
            (project / "src/savings/deposit.ts").write_text("export const deposit = 'switch, then supply'\n")
            (project / "package.json").write_text('{"name":"page"}\n')
            for name in ("node_modules/wallet", "dist", ".git"):
                (project / name).mkdir(parents=True)
                (project / name / "ignored.js").write_text("not project source\n")
            outside = root / "outside.ts"
            outside.write_text("outside the project\n")
            (project / "src/external.ts").symlink_to(outside)

            self.assertEqual(module.snapshot(project), (
                '--- package.json ---\n{"name":"page"}\n\n\n'
                "--- src/savings/deposit.ts ---\nexport const deposit = 'switch, then supply'\n\n"
            ))


if __name__ == "__main__":
    unittest.main()
