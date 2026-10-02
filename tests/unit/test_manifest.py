"""Unit tests for `exquisite.manifest`."""

import pytest

from exquisite import manifest


def write_pair(tmp_path, rows: str, documents: int):
    csv_path = tmp_path / "corpus.csv"
    csv_path.write_text(rows)
    (tmp_path / "corpus.yaml").write_text(
        f"database: corpus\ndocuments: {documents}\n"
    )

    return csv_path


class TestFromMetadata:
    def test_an_identifier_without_a_source_is_unrecorded(self):
        metadata = {"document_identifier": "ISO 9001", "sha256": "abc"}

        doc = manifest.from_metadata("file:///a.pdf", metadata)

        assert doc.identifier_source == manifest.UNRECORDED
        assert doc.identifier_certainty is None
        assert doc.sha256 == "abc"

    def test_an_inferred_identifier_keeps_its_source_and_certainty(self):
        metadata = {
            "document_identifier": "NIST SP 800-61",
            "identifier_source": "llm",
            "identifier_certainty": 5,
        }

        doc = manifest.from_metadata("file:///a.pdf", metadata)

        assert (doc.identifier_source, doc.identifier_certainty) == ("llm", 5)

    def test_a_source_without_an_identifier_is_dropped(self):
        # `identify` stores a block even for documents it could not identify.
        metadata = {"identifier_source": "llm", "identifier_certainty": 0}

        doc = manifest.from_metadata("file:///a.pdf", metadata)

        assert (doc.document_identifier, doc.identifier_source) == ("", "")
        assert doc.identifier_certainty is None


class TestTrustedIdentifier:
    @pytest.mark.parametrize(
        "source, certainty, trusted",
        [
            ("unrecorded", None, False),
            ("override", 0, True),
            ("llm", 5, True),
            ("llm", 4, True),
            ("llm", 3, False),
            ("llm", None, False),
            ("", None, False),
        ],
    )
    def test_trusts_override_and_high_certainty_only(
        self, source, certainty, trusted
    ):
        doc = manifest.Document(
            uri="u",
            document_identifier="ISO 9001",
            identifier_source=source,
            identifier_certainty=certainty,
        )

        result = doc.trusted_identifier

        assert result is trusted

    def test_no_identifier_is_never_trusted(self):
        doc = manifest.Document(uri="u", identifier_source="override")

        result = doc.trusted_identifier

        assert result is False


class TestIdentifierEvidence:
    @pytest.mark.parametrize(
        "source, certainty, expected",
        [
            ("llm", 5, "llm certainty 5"),
            ("unrecorded", None, "unrecorded"),
            ("", None, "source unknown"),
        ],
    )
    def test_says_where_the_identifier_came_from(
        self, source, certainty, expected
    ):
        doc = manifest.Document(
            uri="u",
            document_identifier="X 1",
            identifier_source=source,
            identifier_certainty=certainty,
        )

        result = doc.identifier_evidence

        assert result == expected


class TestLoad:
    def test_reads_the_provenance_columns(self, tmp_path):
        path = write_pair(
            tmp_path,
            '"uri","sha256","source_url","document_identifier",'
            '"identifier_source","identifier_certainty"\n'
            '"file:///a.pdf","h","","NIST SP 800-61","llm","4"\n',
            documents=1,
        )

        corpus = manifest.load(path)

        doc = corpus.documents[0]
        assert (doc.identifier_source, doc.identifier_certainty) == ("llm", 4)

    def test_a_manifest_predating_the_columns_still_loads(self, tmp_path):
        path = write_pair(
            tmp_path,
            '"uri","sha256","source_url","document_identifier"\n'
            '"file:///a.pdf","h","","NIST SP 800-61"\n',
            documents=1,
        )

        corpus = manifest.load(path)

        doc = corpus.documents[0]
        assert doc.document_identifier == "NIST SP 800-61"
        assert doc.trusted_identifier is False


class TestWrite:
    def test_round_trips_the_provenance_columns(self, tmp_path):
        docs = [
            manifest.Document(
                uri="file:///a.pdf",
                sha256="h",
                document_identifier="NIST SP 800-61",
                identifier_source="llm",
                identifier_certainty=5,
            ),
            manifest.Document(uri="file:///b.pdf", source_url="https://x/b"),
        ]
        path = tmp_path / "corpus.csv"
        (tmp_path / "corpus.yaml").write_text("documents: 2\n")

        manifest.write(path, docs)

        assert manifest.load(path).documents == docs


@pytest.mark.parametrize(
    "value, expected",
    [(None, None), ("", None), ("x", None), (["4"], None), ("4", 4), (5, 5)],
)
def test_certainty_reads_what_it_can(value, expected):
    result = manifest._certainty(value)

    assert result == expected


def test_no_identifier_has_no_evidence():
    doc = manifest.Document(uri="u", identifier_source="llm")

    result = doc.identifier_evidence

    assert result == ""


class TestIdentity:
    def test_an_attachment_is_named_and_kept_apart_from_its_parent(self):
        doc = manifest.Document(
            uri="file:///d/iec.pdf#attachment=Annex%20A.pdf", sha256="h"
        )

        durable = doc.durable()

        assert doc.attachment == doc.name == "Annex A.pdf"
        assert durable == {
            "name": "Annex A.pdf",
            "sha256": "h",
            "source_url": None,
            "attachment": "Annex A.pdf",
        }

    def test_a_whole_document_is_named_by_its_decoded_basename(self):
        doc = manifest.Document(
            uri="file:///d/iso%209001.pdf", source_url="https://x/iso"
        )

        durable = doc.durable()

        assert doc.attachment == ""
        assert durable == {
            "name": "iso 9001.pdf",
            "sha256": None,
            "source_url": "https://x/iso",
        }


ATTACHED = "file:///d/b.pdf#attachment=a.pdf"


@pytest.fixture
def indexed():
    """Copies, an attachment sharing its parent's hash, and gaps."""
    return manifest.Corpus(
        database="std",
        documents=[
            manifest.Document(
                uri="file:///d/a.pdf", sha256="h", source_url="u"
            ),
            manifest.Document(
                uri="file:///e/a.pdf", sha256="h", source_url="u"
            ),
            manifest.Document(uri="file:///d/b.pdf", sha256="k"),
            manifest.Document(uri=ATTACHED, sha256="k"),
            manifest.Document(
                uri="file:///d/c.pdf", document_identifier="ISO 9001"
            ),
        ],
        about={"substrate": {"embeddings": {"name": "e"}}},
    )


class TestCorpus:
    def test_by_sha256_keeps_copies_together_and_attachments_apart(
        self, indexed
    ):
        found = indexed.by_sha256()

        assert {key: [d.uri for d in docs] for key, docs in found.items()} == {
            ("h", ""): ["file:///d/a.pdf", "file:///e/a.pdf"],
            ("k", ""): ["file:///d/b.pdf"],
            ("k", "a.pdf"): [ATTACHED],
        }

    def test_by_source_url_skips_documents_without_one(self, indexed):
        found = indexed.by_source_url()

        assert list(found) == [("u", "")]
        assert len(found[("u", "")]) == 2

    def test_by_identifier_uses_the_collapsed_key(self, indexed):
        found = indexed.by_identifier()

        assert {key: [d.uri for d in docs] for key, docs in found.items()} == {
            "iso9001": ["file:///d/c.pdf"]
        }

    @pytest.mark.parametrize(
        "about, expected",
        [({"substrate": {"chunk_size": 256}}, {"chunk_size": 256}), ({}, {})],
    )
    def test_substrate_defaults_to_empty(self, about, expected):
        corpus = manifest.Corpus(database="std", about=about)

        result = corpus.substrate

        assert result == expected


class TestLoadRefusals:
    def test_a_table_without_its_sidecar(self, tmp_path):
        path = tmp_path / "corpus.csv"
        path.write_text('"uri"\n')

        with pytest.raises(manifest.MissingSidecar) as raised:
            manifest.load(path)

        assert str(raised.value) == (
            "corpus.csv has no sidecar corpus.yaml; the two are a pair, so "
            "regenerate both rather than reading the table alone"
        )

    def test_a_row_count_the_sidecar_disagrees_with(self, tmp_path):
        path = write_pair(tmp_path, '"uri"\n"file:///a.pdf"\n', documents=2)

        with pytest.raises(manifest.RowCountMismatch) as raised:
            manifest.load(path)

        assert (raised.value.rows, raised.value.declared) == (1, 2)

    def test_the_database_defaults_to_the_stem(self, tmp_path):
        path = tmp_path / "std.csv"
        path.write_text('"uri"\n')
        (tmp_path / "std.yaml").write_text("")

        corpus = manifest.load(path)

        assert (corpus.database, corpus.documents) == ("std", [])


class TestResolve:
    @pytest.mark.parametrize(
        "wanted, uris, how",
        [
            (
                {"sha256": "h"},
                ["file:///d/a.pdf", "file:///e/a.pdf"],
                "sha256",
            ),
            (
                {"source_url": "u"},
                ["file:///d/a.pdf", "file:///e/a.pdf"],
                "source_url",
            ),
            (
                {"sha256": "new", "source_url": "u"},
                ["file:///d/a.pdf", "file:///e/a.pdf"],
                "changed",
            ),
            ({"sha256": "k", "attachment": "a.pdf"}, [ATTACHED], "sha256"),
            ({"name": "a.pdf"}, [], "no durable identifier recorded"),
            ({"sha256": "gone"}, [], "not in this ingestion"),
        ],
    )
    def test_says_how_it_found_what(self, indexed, wanted, uris, how):
        documents, found_how = manifest.resolve(indexed, wanted)

        assert [doc.uri for doc in documents] == uris
        assert found_how == how
