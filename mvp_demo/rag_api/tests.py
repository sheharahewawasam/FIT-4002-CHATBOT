"""
Tests for the audit-log path handling (SEC-1).

The property under test is narrow but important: nothing derived from a request
may cause a write outside AUDIT_LOG_ROOT. The endpoint that reaches this code
has no authentication, so the advisor name arriving here is fully attacker
controlled.
"""
import os
import tempfile
from unittest import mock

from django.test import TestCase

from rag_api import views
from rag_api.models import Advisor


class AuditLogPathTests(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="audit-test-")
        patcher = mock.patch.object(views, "AUDIT_LOG_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _files_under(self, path):
        found = []
        for dirpath, _dirnames, filenames in os.walk(path):
            found.extend(os.path.join(dirpath, f) for f in filenames)
        return found

    def test_writes_inside_root_for_a_known_advisor(self):
        # John already exists from the seed data migration.
        Advisor.objects.get_or_create(name="John")

        views.write_audit_log("John", "a question", "an answer")

        written = self._files_under(self.root)
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].startswith(self.root))
        with open(written[0], encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("a question", body)
        self.assertIn("an answer", body)
        self.assertIn("John", body)

    def test_traversal_in_the_request_writes_nothing(self):
        """The original bug: a name of '../../..' escaped the project entirely."""
        # John already exists from the seed data migration.
        Advisor.objects.get_or_create(name="John")
        sibling = os.path.join(os.path.dirname(self.root), "escaped")

        for hostile in ("../../../escaped", "../" * 6 + "escaped", "/etc/passwd", "a/b/c"):
            views.write_audit_log(hostile, "q", "a")

        self.assertEqual(self._files_under(self.root), [])
        self.assertFalse(os.path.exists(sibling))

    def test_unknown_advisor_is_skipped_not_crashed(self):
        views.write_audit_log("Mallory", "q", "a")
        self.assertEqual(self._files_under(self.root), [])

    def test_missing_user_field_is_handled(self):
        """chat_with_advisor_bot passes request.data.get('user'), which may be None."""
        views.write_audit_log(None, "q", "a")
        self.assertEqual(self._files_under(self.root), [])

    def test_hostile_advisor_name_is_still_contained(self):
        """
        Even a name that reaches the database from elsewhere (the admin, a
        fixture) must not be able to steer the path out of the root.
        """
        Advisor.objects.get_or_create(name="../../../evil")

        views.write_audit_log("../../../evil", "q", "a")

        written = self._files_under(self.root)
        self.assertEqual(len(written), 1)
        self.assertEqual(
            os.path.commonpath([os.path.realpath(self.root), os.path.realpath(written[0])]),
            os.path.realpath(self.root),
        )


class AccessFilterTests(TestCase):
    """
    build_access_filter decides which documents a query can reach, so it is the
    technical expression of the isolation promised to the client.
    """

    def test_funds_and_owner_are_combined_with_or(self):
        self.assertEqual(
            views.build_access_filter(["General"], "John"),
            {"$or": [{"fund_name": {"$in": ["General"]}}, {"owner": {"$eq": "John"}}]},
        )

    def test_owner_alone_when_no_funds_selected(self):
        self.assertEqual(
            views.build_access_filter([], "John"),
            {"owner": {"$eq": "John"}},
        )

    def test_funds_alone_when_no_owner(self):
        self.assertEqual(
            views.build_access_filter(["General"], None),
            {"fund_name": {"$in": ["General"]}},
        )

    def test_nothing_to_match_returns_none_rather_than_an_empty_filter(self):
        """
        None makes the caller refuse the query. Returning {} instead would query
        Pinecone unfiltered and expose every document in the index.
        """
        self.assertIsNone(views.build_access_filter([], None))
