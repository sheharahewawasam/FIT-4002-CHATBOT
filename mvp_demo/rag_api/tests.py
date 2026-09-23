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
from django.contrib.auth.models import User

from rag_api.models import Advisor, Document, Fund


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


class QueryCacheIsolationTests(TestCase):
    """
    The in-memory answer cache is part of the access boundary.

    Its key was once the question text alone, so two advisers asking the same
    question shared one answer regardless of which funds each could see. An
    adviser received documents from funds they had no access to, without the
    access filter ever being consulted.
    """

    def _key(self, question, user, funds):
        # Mirrors the key built in chat_with_advisor_bot.
        import json
        return json.dumps(
            {"q": question.strip().lower(), "user": user, "funds": sorted(funds)},
            sort_keys=True,
        )

    def test_same_question_different_advisers_do_not_share_a_cache_entry(self):
        question = "What is the deed date for this fund?"
        john = self._key(question, "John", ["Summers Family Super Fund", "General"])
        emily = self._key(question, "Emily", ["Ausis Super Fund", "General"])
        self.assertNotEqual(john, emily)

    def test_same_adviser_different_funds_do_not_share_a_cache_entry(self):
        question = "What is the deed date for this fund?"
        a = self._key(question, "John", ["Summers Family Super Fund"])
        b = self._key(question, "John", ["Sample Superannuation Fund"])
        self.assertNotEqual(a, b)

    def test_identical_asker_and_scope_still_hits_the_cache(self):
        question = "What is the deed date for this fund?"
        a = self._key(question, "John", ["General", "Summers Family Super Fund"])
        b = self._key("  What is the DEED date for this fund?  ",
                      "John", ["Summers Family Super Fund", "General"])
        self.assertEqual(a, b)


class AuthenticationRequiredTests(TestCase):
    """
    Every endpoint except the three sign-in ones must refuse an anonymous caller.

    DRF is closed by default in settings.py, so this is really a test that the
    default is in force - a view added later with its own decorators could
    quietly opt out of it.
    """

    def test_anonymous_is_refused_everywhere(self):
        self.assertEqual(self.client.get("/users/").status_code, 403)
        self.assertEqual(self.client.get("/api/documents/").status_code, 403)
        self.assertEqual(self.client.get("/api/documents/1/").status_code, 403)
        self.assertEqual(
            self.client.post("/api/chat/", {"query": "hello"},
                             content_type="application/json").status_code, 403)

    def test_the_sign_in_endpoints_are_reachable_anonymously(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["authenticated"])

    def test_wrong_password_does_not_say_whether_the_user_exists(self):
        # A name the seed migration did not already take.
        User.objects.create_user(username="realperson", password="right")
        missing = self.client.post("/api/auth/login/",
                                   {"username": "nobody", "password": "x"},
                                   content_type="application/json")
        wrong = self.client.post("/api/auth/login/",
                                 {"username": "realperson", "password": "wrong"},
                                 content_type="application/json")
        self.assertEqual(missing.status_code, wrong.status_code)
        self.assertEqual(missing.json()["error"], wrong.json()["error"])

    def test_an_auth_user_with_no_advisor_record_cannot_sign_in(self):
        User.objects.create_user(username="stranger", password="pw")
        response = self.client.post("/api/auth/login/",
                                    {"username": "stranger", "password": "pw"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 403)


class FundAuthorisationTests(TestCase):
    """
    The fund list in the request body must never widen what an advisor can read.

    This was a live hole: build_access_filter was handed the body's fund list
    directly, so an advisor granted one fund received another fund's trust deeds
    by naming them. Authenticating the caller alone would not have fixed it -
    the escalation works just as well from a signed-in session.
    """

    def setUp(self):
        self.ausis = Fund.objects.create(name="Ausis Test Fund")
        self.general = Fund.objects.create(name="General Test")
        self.darto = Fund.objects.create(name="Darto Test Fund")

        self.emily = Advisor.objects.create(name="EmilyTest")
        self.emily.funds.set([self.ausis, self.general])

    def test_a_fund_they_do_not_hold_is_dropped(self):
        self.assertEqual(
            views.permitted_funds(self.emily, ["Darto Test Fund"]), [])

    def test_a_mixed_request_keeps_only_what_they_hold(self):
        self.assertEqual(
            views.permitted_funds(self.emily, ["Ausis Test Fund", "Darto Test Fund"]),
            ["Ausis Test Fund"])

    def test_asking_for_nothing_gives_their_whole_grant(self):
        self.assertEqual(
            views.permitted_funds(self.emily, []),
            ["Ausis Test Fund", "General Test"])

    def test_an_unknown_fund_name_is_dropped_rather_than_erroring(self):
        # Erroring would confirm which fund names exist.
        self.assertEqual(views.permitted_funds(self.emily, ["No Such Fund"]), [])

    def test_dropping_every_fund_does_not_leave_an_unfiltered_query(self):
        """
        With no fund left, the filter must still be owner-scoped or None -
        never absent, which would query the whole index.
        """
        allowed = views.permitted_funds(self.emily, ["Darto Test Fund"])
        access_filter = views.build_access_filter(allowed, self.emily.name)
        self.assertEqual(access_filter, {"owner": {"$eq": "EmilyTest"}})
        self.assertIsNone(views.build_access_filter(allowed, None))


class DocumentOwnershipTests(TestCase):
    """A document must not be readable by anyone but its owner."""

    def setUp(self):
        self.owner = Advisor.objects.create(
            name="OwnerTest", user=User.objects.create_user("ownertest", password="pw"))
        self.other = Advisor.objects.create(
            name="OtherTest", user=User.objects.create_user("othertest", password="pw"))
        self.doc = Document.objects.create(
            owner=self.owner, original_filename="private.pdf",
            stored_path="/tmp/private.pdf", status=Document.READY)

    def test_the_owner_can_read_their_document(self):
        self.client.force_login(self.owner.user)
        response = self.client.get(f"/api/documents/{self.doc.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document"]["filename"], "private.pdf")

    def test_another_advisor_gets_not_found_rather_than_the_document(self):
        """
        This used to fetch on the primary key alone, so counting upwards
        revealed everyone's filenames, funds and ingestion progress.
        """
        self.client.force_login(self.other.user)
        response = self.client.get(f"/api/documents/{self.doc.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_another_advisor_cannot_delete_it(self):
        self.client.force_login(self.other.user)
        response = self.client.delete(f"/api/documents/{self.doc.pk}/delete/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Document.objects.filter(pk=self.doc.pk).exists())

    def test_a_listing_shows_only_the_callers_own_documents(self):
        self.client.force_login(self.other.user)
        response = self.client.get("/api/documents/")
        self.assertEqual(response.json()["documents"], [])
