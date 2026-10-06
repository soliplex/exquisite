"""Build the pieces of a data repository on disk, for tests."""

import yaml

from exquisite import manifest


def question_set(root, name, references, *, uuids=None, suffix=".yaml"):
    """Write ``questions/<name><suffix>`` with one case per reference."""
    uuids = uuids or [f"uuid-{i}" for i in range(len(references))]
    cases = [
        {"inputs": f"question {i}", "metadata": {"uuid": uuid, **reference}}
        for i, (uuid, reference) in enumerate(
            zip(uuids, [_metadata(text) for text in references], strict=True)
        )
    ]
    path = root / "questions" / f"{name}{suffix}"
    path.write_text(yaml.dump({"cases": cases}))

    return path


def _metadata(reference):
    return {} if reference is None else {"reference": reference}


def ingestion(root, corpus, stem, documents, **about):
    """Write a manifest pair under ``corpus/<corpus>/ingestion/``."""
    base = root / "corpus" / corpus / "ingestion"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{stem}.csv"
    manifest.write(path, documents)
    sidecar = {"database": stem, "documents": len(documents), **about}
    (base / f"{stem}.yaml").write_text(yaml.safe_dump(sidecar))

    return path


def worksheet(root, corpus, name, text):
    """Write ``corpus/<corpus>/worksheet/<name>.yaml``."""
    base = root / "corpus" / corpus / "worksheet"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{name}.yaml"
    path.write_text(text)

    return path
