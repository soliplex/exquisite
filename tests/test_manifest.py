"""Unit tests for `exquisite.manifest`."""

import pytest

from exquisite import manifest


def write_pair(tmp_path, rows: str, documents: int):
    csv_path = tmp_path / "corpus.csv"
    csv_path.write_text(rows)
    (tmp_path / "corpus.yaml").write_text(f"database: corpus\ndocuments: {documents}\n")

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
    def test_trusts_override_and_high_certainty_only(self, source, certainty, trusted):
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
    def test_says_where_the_identifier_came_from(self, source, certainty, expected):
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
