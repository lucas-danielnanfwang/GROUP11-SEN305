"""Evidence generator for the Lab 3 in-lab exercise (Tasks 1-3).

Run:  python manage.py lab3_exercise            (seed + print evidence)
      python manage.py lab3_exercise --reset    (delete the synthetic rows)

Only SYNTHETIC laboratory data is created: every title starts with "SYNTH"
and every row belongs to the user "synthetic_requester". Re-running the
command is safe (it never duplicates rows).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from requests_app.models import Category, ServiceRequest

PREFIX = "SYNTH"
REQUESTER = "synthetic_requester"
S = ServiceRequest.Status


def banner(text):
    print("\n" + "=" * 78 + f"\n{text}\n" + "=" * 78)


class Command(BaseCommand):
    help = "Seed synthetic data and print the evidence for Lab 3 Tasks 1-3."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete synthetic requests and exit.")

    # ------------------------------------------------------------------ main
    def handle(self, *args, **options):
        user, _ = get_user_model().objects.get_or_create(username=REQUESTER)
        if options["reset"]:
            deleted, _ = ServiceRequest.objects.filter(title__startswith=PREFIX).delete()
            self.stdout.write(f"Deleted {deleted} synthetic row(s).")
            return

        electrical, _ = Category.objects.get_or_create(
            name="Electrical", defaults={"description": "Electrical faults and maintenance"})
        ict, _ = Category.objects.get_or_create(
            name="ICT Support", defaults={"description": "Computers, networks and software"})

        self.task1_due_dates(user, electrical)
        self.task2_resolution_rule(user, electrical)
        self.task3_query_analysis(user, electrical, ict)

    # ---------------------------------------------------------------- task 1
    def task1_due_dates(self, user, category):
        banner("TASK 1 step 5 - two requests with different due dates")
        now = timezone.now()
        specs = [
            (f"{PREFIX} due-soon socket fault", now + timedelta(days=1)),
            (f"{PREFIX} due-later projector fault", now + timedelta(days=5)),
        ]
        for title, due in specs:
            obj, created = ServiceRequest.objects.get_or_create(
                title=title,
                defaults=dict(requester=user, category=category,
                              description="Synthetic laboratory record.",
                              location="Software Engineering Lab", priority=3),
            )
            # Re-anchor the due date on every run so the demo is repeatable.
            obj.due_at = due
            obj.full_clean()
            obj.save()
            print(f"{'created' if created else 'updated'}: {obj.title!r} due_at={obj.due_at:%Y-%m-%d %H:%M}")

        chosen = now + timedelta(days=3)
        qs = ServiceRequest.objects.filter(title__startswith=PREFIX).due_before(chosen)
        print(f"\nChosen time = now + 3 days = {chosen:%Y-%m-%d %H:%M} UTC")
        print("Query: ServiceRequest.objects.due_before(chosen)")
        print("SQL  :", qs.query)
        print("Result:", [r.title for r in qs])
        assert [r.title for r in qs] == [specs[0][0]], "only the earlier request may match"

        active_before = ServiceRequest.objects.active().filter(
            title__startswith=PREFIX, due_at__lt=chosen).order_by()
        print("\nIndex check for  WHERE status IN (active) AND due_at < chosen:")
        print("SQL  :", active_before.query)
        print(active_before.explain())

    # ---------------------------------------------------------------- task 2
    def task2_resolution_rule(self, user, category):
        banner("TASK 2 steps 7-8 - resolution rule proved with full_clean()")
        base = dict(requester=user, category=category, title=f"{PREFIX} rule probe",
                    description="Synthetic laboratory record.", location="Lab", priority=2)
        cases = [
            ("RESOLVED, no resolved_at, no summary", dict(status=S.RESOLVED)),
            ("RESOLVED, resolved_at set, summary missing",
             dict(status=S.RESOLVED, resolved_at=timezone.now())),
            ("RESOLVED, resolved_at set, summary only spaces",
             dict(status=S.RESOLVED, resolved_at=timezone.now(), resolution_summary="   ")),
            ("CLOSED, summary set, resolved_at missing",
             dict(status=S.CLOSED, resolution_summary="Replaced the faulty socket.")),
            ("RESOLVED, resolved_at + summary present",
             dict(status=S.RESOLVED, resolved_at=timezone.now(),
                  resolution_summary="Replaced the faulty socket.")),
            ("OPEN, blank summary (rule does not apply)", dict(status=S.OPEN)),
        ]
        for label, extra in cases:
            probe = ServiceRequest(**base, **extra)      # never saved
            try:
                probe.full_clean()
                print(f"PASS  {label:<52} -> valid")
            except ValidationError as exc:
                print(f"FAIL  {label:<52} -> {exc.message_dict}")
        print("\n(No probe was saved: ", ServiceRequest.objects.filter(title=f"{PREFIX} rule probe").count(), "rows.)")

    # ---------------------------------------------------------------- task 3
    @transaction.atomic
    def task3_query_analysis(self, user, electrical, ict):
        banner("TASK 3 - synthetic data and query analysis")
        # 2 categories x 3 statuses x 2 rows = 12 rows, mixed priorities.
        plan = []
        for cat in (electrical, ict):
            for status in (S.OPEN, S.ASSIGNED, S.RESOLVED):
                for n, prio in enumerate((1, 4) if cat == electrical else (2, 5), start=1):
                    plan.append((cat, status, prio, n))
        created = 0
        for cat, status, prio, n in plan:
            title = f"{PREFIX} {cat.name} {status.label} #{n}"
            if ServiceRequest.objects.filter(title=title).exists():
                continue
            extra = {}
            if status == S.RESOLVED:
                extra = dict(resolved_at=timezone.now(),
                             resolution_summary="Synthetic fix applied and verified.")
            obj = ServiceRequest(requester=user, category=cat, title=title,
                                 description="Synthetic laboratory record.",
                                 location="Software Engineering Lab",
                                 priority=prio, status=status, **extra)
            obj.full_clean()
            obj.save()
            created += 1
        print(f"Seeded {created} new synthetic rows (12 planned).")
        total = ServiceRequest.objects.filter(title__startswith=PREFIX).count()
        print(f"Synthetic rows in table: {total}  |  all rows in table: {ServiceRequest.objects.count()}")

        qs = (ServiceRequest.objects
              .filter(category=electrical, status__in=[S.OPEN, S.ASSIGNED])
              .order_by("priority", "created_at"))
        print("\nQuery: open OR assigned, category=Electrical, ORDER BY priority, created_at")
        print("\nqueryset.query:\n", qs.query)
        print("\nresult rows (priority, status, title):")
        for r in qs:
            print(f"  {r.priority}  {r.status:<9} {r.title}")
        print("\nqueryset.explain():")
        print(qs.explain())
