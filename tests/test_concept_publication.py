from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from concept_fixtures import ConceptFixture, REPO, director


class SingleBookPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.fixture = ConceptFixture(self.base)
        self.internal = self.base / 'work' / 'concept-data'
        self.book = self.base / 'outputs' / '资产概念设计书.md'
        draft = deepcopy(self.fixture.requirement)
        draft['persistence_plan'].update(output_root=str(self.internal), design_book_path=str(self.book))
        self.req = self.fixture.approve(draft, self.fixture.snapshot, self.fixture.position)

    def materialize(self):
        return director.materialize(self.fixture.catalog, self.fixture.snapshot, self.req,
                                    self.fixture.position, self.internal)

    def test_only_book_is_public_and_machine_handoff_remains_valid(self):
        result = self.materialize()
        self.assertEqual(result['deliverables'], {'asset_concept_book': str(self.book)})
        self.assertEqual(list((self.base / 'outputs').rglob('*')), [self.book])
        handoff = Path(result['machine_handoff'])
        self.assertTrue(handoff.is_relative_to(self.internal))
        self.assertEqual(director.validate_handoff(self.req, handoff), [])
        self.assertEqual(self.book.read_bytes(), handoff.with_suffix('.md').read_bytes())
        before = {p: p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(self.materialize()['deliverables'], result['deliverables'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.base.rglob('*') if p.is_file()})

    def test_book_path_is_bound_to_persistence_confirmation(self):
        changed = deepcopy(self.req)
        changed['persistence_plan']['design_book_path'] = str(self.base / 'other.md')
        changed['integrity']['requirement_hash'] = director.requirement_hash(changed)
        errors = director.validate_requirement(changed, self.fixture.snapshot, self.fixture.position)
        self.assertIn('persistence_plan confirmation no longer matches its approved content', errors)
        self.assertNotIn('design_requirement confirmation no longer matches its approved content', errors)

    def test_reject_invalid_public_destination(self):
        for invalid in ('relative.md', str(self.base / 'book.txt'), str(self.internal / 'book.md'), None):
            with self.subTest(path=invalid):
                draft = deepcopy(self.req)
                draft['persistence_plan']['design_book_path'] = invalid
                with self.assertRaises(ValueError):
                    self.fixture.approve(draft, self.fixture.snapshot, self.fixture.position)

    def test_existing_different_book_is_preserved_before_internal_write(self):
        self.book.parent.mkdir(parents=True)
        self.book.write_text('Existing user document')
        with self.assertRaisesRegex(ValueError, 'different content'):
            self.materialize()
        self.assertEqual(self.book.read_text(), 'Existing user document')
        self.assertFalse(self.internal.exists())

    def test_book_symlink_is_not_followed(self):
        target = self.base / 'other.md'
        target.write_text('Existing target')
        self.book.parent.mkdir(parents=True)
        self.book.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.materialize()
        self.assertEqual(target.read_text(), 'Existing target')

    def test_publication_failure_can_resume_complete_internal_package(self):
        with patch.object(director.os, 'link', side_effect=OSError('public storage failure')):
            with self.assertRaisesRegex(OSError, 'public storage failure'):
                self.materialize()
        self.assertFalse(self.book.exists())
        self.assertEqual(list(self.book.parent.iterdir()), [])
        handoff = next(self.internal.rglob('requirement.json'))
        before = {p: p.read_bytes() for p in handoff.parent.iterdir()}
        self.assertEqual(set(p.name for p in before), set(director.PACKAGE_FILES))
        self.materialize()
        self.assertEqual(before, {p: p.read_bytes() for p in handoff.parent.iterdir()})
        self.assertTrue(self.book.exists())

    def test_internal_failure_publishes_nothing(self):
        with patch.object(director.os, 'rename', side_effect=OSError('internal storage failure')):
            with self.assertRaisesRegex(OSError, 'internal storage failure'):
                self.materialize()
        self.assertFalse(self.book.exists())
        self.assertEqual(list(self.internal.rglob('requirement.json')), [])
        self.materialize()
        self.assertTrue(self.book.exists())

    def test_cli_default_reports_one_deliverable_details_opt_in(self):
        requirement_path = self.fixture.write_package(self.req)
        script = REPO / 'plugins/skill-orchestrator/skills/screenplay-concept-director/scripts/concept_director.py'
        command = [sys.executable, '-B', str(script), 'materialize', '--requirement', str(requirement_path),
                   '--snapshot', str(requirement_path.parent / 'context-snapshot.json'),
                   '--position', str(requirement_path.parent / 'creative-position.json'),
                   '--catalog', str(requirement_path.parent / 'asset-catalog.json'), '--output-root', str(self.internal)]
        for flags in ([], ['--details']):
            completed = subprocess.run(command + flags, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result['deliverables'], {'asset_concept_book': str(self.book)})
            self.assertEqual('artifacts' in result, bool(flags))
            self.assertEqual('machine_handoff' in result, bool(flags))


if __name__ == '__main__':
    unittest.main()
