"""Capture analyzer/source identity at intake, before screenplay analysis."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path


def analyzer_hash(root: Path) -> str:
    digest = hashlib.sha256()
    files = 0
    for path in sorted(root.resolve().rglob('*')):
        relative = path.relative_to(root.resolve())
        if not path.is_file() or '__pycache__' in relative.parts or path.suffix in {'.pyc', '.pyo'} or relative.parts[0] == 'tests':
            continue
        digest.update(str(relative).encode('utf-8') + b'\0' + path.read_bytes() + b'\0')
        files += 1
    if not files:
        raise ValueError('Analyzer has no files')
    return digest.hexdigest()


def capture(source_hash: str, source_path: str | None, original_source_path: str | None = None) -> dict:
    provenance = {
        'analyzer_hash': analyzer_hash(Path(__file__).resolve().parents[1]),
        'source_hash': source_hash,
        'source_path': str(Path(source_path).resolve()) if source_path else None,
        'captured_at': datetime.now(timezone.utc).isoformat(),
    }
    if original_source_path:
        original = Path(original_source_path).resolve()
        provenance['original_source_path'] = str(original)
        provenance['original_source_hash'] = hashlib.sha256(original.read_bytes()).hexdigest()
    return provenance
