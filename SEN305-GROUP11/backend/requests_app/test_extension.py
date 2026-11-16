"""Tests for the Lab 3 in-lab exercise (migration 0002).

The original tests stay untouched in requests_app/tests.py. This module only
adds tests for: due_at + index (Task 1), the resolution rule (Task 2), the
Admin changes, and migration discipline.
"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, ServiceRequest

S = ServiceRequest.Status


class ExtensionTestBase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.requester = user_model.objects.create_user(username="requester")
        self.category = Category.objects.create(name="Electrical")
        self.now = timezone.now()

    def build(self, **overrides):
        """Unsaved instance, so full_clean() can be tested in isolation."""
        values = {
            "requester": self.requester,
            "category": self.category,
            "title": "Faulty socket",
            "description": "Socket does not supply power.",
            "location": "Software Engineering Lab",
            "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest(**values)

    def make(self, **overrides):
        item = self.build(**overrides)
        item.full_clean()
        item.save()
        return item


# --------------------------------------------------------------------------
# Task 1 - due_at and its index
# --------------------------------------------------------------------------
class DueDateTests(ExtensionTestBase):
    def test_due_at_is_nullable_and_optional(self):
        field = ServiceRequest._meta.get_field("due_at")
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        item = self.make()
        item.refresh_from_db()
        self.assertIsNone(item.due_at)

    def test_status_due_index_exists_in_mysql(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor, ServiceRequest._meta.db_table
            )
        self.assertIn("req_status_due_idx", constraints)
        index = constraints["req_status_due_idx"]
        self.assertTrue(index["index"])
        self.assertEqual(index["columns"], ["status", "due_at"])

    def test_two_requests_query_those_due_before_chosen_time(self):
        soon = self.make(title="Due soon", due_at=self.now + timedelta(days=1))
        later = self.make(title="Due later", due_at=self.now + timedelta(days=5))
        no_deadline = self.make(title="No deadline")

        chosen = self.now + timedelta(days=3)
        found = set(ServiceRequest.objects.due_before(chosen))

        self.assertEqual(found, {soon})
        self.assertNotIn(later, found)
        self.assertNotIn(no_deadline, found)  # NULL due_at never matches

    def test_overdue_means_past_due_and_still_active(self):
        yesterday = self.now - timedelta(days=1)
        overdue_open = self.make(title="Overdue open", due_at=yesterday)
        overdue_in_progress = self.make(
            title="Overdue in progress", due_at=yesterday, status=S.IN_PROGRESS
        )
        finished_late = self.make(
            title="Finished late", due_at=yesterday, status=S.RESOLVED,
            resolved_at=self.now, resolution_summary="Fixed after deadline.",
        )
        not_due_yet = self.make(title="Not due", due_at=self.now + timedelta(days=1))
        no_deadline = self.make(title="No deadline")

        overdue = set(ServiceRequest.objects.overdue(self.now))

        self.assertEqual(overdue, {overdue_open, overdue_in_progress})
        self.assertTrue(overdue_open.is_overdue)
        self.assertFalse(finished_late.is_overdue)
        self.assertFalse(not_due_yet.is_overdue)
        self.assertFalse(no_deadline.is_overdue)


# --------------------------------------------------------------------------
# Task 2 - resolution_summary and the RESOLVED/CLOSED rule
# --------------------------------------------------------------------------
class ResolutionRuleTests(ExtensionTestBase):
    def test_resolution_summary_defaults_to_empty_string(self):
        self.assertEqual(self.make().resolution_summary, "")

    def test_resolved_without_resolved_at_and_summary_reports_both_fields(self):
        item = self.build(status=S.RESOLVED)
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertEqual(
            set(ctx.exception.message_dict), {"resolved_at", "resolution_summary"}
        )

    def test_resolved_without_summary_is_rejected(self):
        item = self.build(status=S.RESOLVED, resolved_at=self.now)
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertEqual(set(ctx.exception.message_dict), {"resolution_summary"})

    def test_whitespace_only_summary_is_rejected(self):
        item = self.build(
            status=S.RESOLVED, resolved_at=self.now, resolution_summary="   \n\t "
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_resolved_without_resolved_at_is_rejected(self):
        item = self.build(status=S.RESOLVED, resolution_summary="Replaced socket.")
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertEqual(set(ctx.exception.message_dict), {"resolved_at"})

    def test_closed_is_subject_to_the_same_rule(self):
        with self.assertRaises(ValidationError) as ctx:
            self.build(status=S.CLOSED).full_clean()
        self.assertEqual(
            set(ctx.exception.message_dict), {"resolved_at", "resolution_summary"}
        )
        # ...and passes once both are supplied.
        self.build(
            status=S.CLOSED, resolved_at=self.now, resolution_summary="Closed after fix."
        ).full_clean()

    def test_valid_resolved_record_passes_full_clean(self):
        item = self.build(
            status=S.RESOLVED, resolved_at=self.now, resolution_summary="Replaced socket."
        )
        item.full_clean()  # must not raise

    def test_rule_does_not_apply_to_active_statuses(self):
        for status in (S.OPEN, S.ASSIGNED, S.IN_PROGRESS):
            with self.subTest(status=status):
                self.build(status=status).full_clean()  # blank summary is fine

    def test_invalid_record_is_not_saved_when_validated_first(self):
        item = self.build(title="Must not persist", status=S.RESOLVED)
        with self.assertRaises(ValidationError):
            item.full_clean()
        self.assertFalse(ServiceRequest.objects.filter(title="Must not persist").exists())


# --------------------------------------------------------------------------
# Admin - due date and resolution data visible, searchable, filterable
# --------------------------------------------------------------------------
class AdminTests(ExtensionTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = get_user_model().objects.create_superuser(
            username="labadmin", password="pass12345", email="a@example.com"
        )
        self.client.force_login(self.admin_user)
        yesterday = self.now - timedelta(days=1)
        self.overdue = self.make(title="ZZ-overdue-item", due_at=yesterday)
        self.finished_late = self.make(
            title="ZZ-finished-late-item", due_at=yesterday, status=S.RESOLVED,
            resolved_at=self.now, resolution_summary="Rewired the distribution board.",
        )
        self.future = self.make(title="ZZ-future-item", due_at=self.now + timedelta(days=3))
        self.undated = self.make(title="ZZ-undated-item")
        self.changelist = reverse("admin:requests_app_servicerequest_changelist")

    def titles_for(self, query=""):
        response = self.client.get(self.changelist + query)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        return {
            item.title
            for item in (self.overdue, self.finished_late, self.future, self.undated)
            if item.title in content
        }

    def test_changelist_shows_due_at_and_overdue_columns(self):
        response = self.client.get(self.changelist)
        self.assertContains(response, "column-due_at")
        self.assertContains(response, "column-overdue")
        self.assertContains(response, "column-resolved_at")

    def test_overdue_filter_excludes_resolved_future_and_undated(self):
        self.assertEqual(self.titles_for("?due_state=overdue"), {self.overdue.title})

    def test_none_filter_lists_requests_without_due_date(self):
        self.assertEqual(self.titles_for("?due_state=none"), {self.undated.title})

    def test_next_24h_and_later_filters(self):
        soon = self.make(title="ZZ-soon-item", due_at=self.now + timedelta(hours=2))
        self.assertIn(soon.title, self.client.get(self.changelist + "?due_state=next_24h").content.decode())
        self.assertNotIn(self.future.title, self.client.get(self.changelist + "?due_state=next_24h").content.decode())
        self.assertEqual(self.titles_for("?due_state=later"), {self.future.title})

    def test_search_finds_request_by_resolution_summary(self):
        self.assertEqual(self.titles_for("?q=distribution+board"), {self.finished_late.title})

    def test_admin_form_enforces_the_model_rule(self):
        """The rule is on the model, so Admin gets it for free."""
        before = ServiceRequest.objects.count()
        data = {
            "requester": self.requester.pk, "category": self.category.pk,
            "title": "Admin invalid resolve", "description": "d", "location": "Lab",
            "priority": 3, "status": S.RESOLVED, "due_at_0": "", "due_at_1": "",
            "resolved_at_0": "", "resolved_at_1": "", "resolution_summary": "",
            "comments-TOTAL_FORMS": 0, "comments-INITIAL_FORMS": 0,
            "comments-MIN_NUM_FORMS": 0, "comments-MAX_NUM_FORMS": 1000,
        }
        add_url = reverse("admin:requests_app_servicerequest_add")
        response = self.client.post(add_url, data)
        self.assertEqual(response.status_code, 200)  # form redisplayed with errors
        self.assertContains(response, "requires a resolution summary")
        self.assertContains(response, "must have a resolved_at timestamp")
        self.assertEqual(ServiceRequest.objects.count(), before)

        data.update(
            resolved_at_0=self.now.strftime("%Y-%m-%d"),
            resolved_at_1=self.now.strftime("%H:%M:%S"),
            resolution_summary="Replaced the breaker.",
        )
        response = self.client.post(add_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ServiceRequest.objects.count(), before + 1)


# --------------------------------------------------------------------------
# Migration discipline
# --------------------------------------------------------------------------
class MigrationDisciplineTests(TestCase):
    def test_no_model_change_is_missing_a_migration(self):
        # makemigrations --check exits with status 1 when a migration is missing.
        call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())

    def test_0002_is_the_leaf_and_depends_on_0001(self):
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        self.assertEqual(
            loader.graph.leaf_nodes("requests_app"),
            [("requests_app", "0002_add_due_at_and_resolution_summary")],
        )
        migration = loader.get_migration(
            "requests_app", "0002_add_due_at_and_resolution_summary"
        )
        self.assertIn(("requests_app", "0001_initial"), migration.dependencies)

    def test_0001_was_not_edited_to_contain_the_new_columns(self):
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        initial = loader.get_migration("requests_app", "0001_initial")
        for operation in initial.operations:
            fields = getattr(operation, "fields", [])
            names = {name for name, _ in fields}
            self.assertNotIn("due_at", names)
            self.assertNotIn("resolution_summary", names)
