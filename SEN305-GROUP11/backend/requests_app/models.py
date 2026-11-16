import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class ServiceRequestQuerySet(models.QuerySet):
    """Reusable, chainable queries so Admin, services and tests share one
    definition of 'active', 'overdue' and 'due before'."""

    def active(self):
        return self.filter(status__in=ServiceRequest.ACTIVE_STATUSES)

    def due_before(self, moment):
        # Strictly earlier than `moment`. Rows with due_at NULL never match.
        return self.filter(due_at__lt=moment)

    def overdue(self, now=None):
        # Overdue = past its due date AND still being worked on.
        # Uses the (status, due_at) index added in migration 0002.
        return self.active().due_before(now or timezone.now())


class ServiceRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    ACTIVE_STATUSES = (Status.OPEN, Status.ASSIGNED, Status.IN_PROGRESS)
    COMPLETED_STATUSES = (Status.RESOLVED, Status.CLOSED)

    objects = ServiceRequestQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="service_requests",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="service_requests",
    )
    title = models.CharField(max_length=160)
    description = models.TextField()
    location = models.CharField(max_length=160)
    priority = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    # Lab 3 in-lab exercise, Task 1: service-level due date (nullable: a
    # request may have no agreed deadline).
    due_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Service-level deadline. Leave empty when no deadline applies.",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Lab 3 in-lab exercise, Task 2: what was done. Blank is allowed for
    # active requests; clean() makes it mandatory for RESOLVED/CLOSED.
    resolution_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("category", "status"), name="req_cat_status_idx"),
            models.Index(fields=("priority", "created_at"), name="req_priority_date_idx"),
            # Task 1: supports WHERE status = / IN (...) AND due_at < ...
            models.Index(fields=("status", "due_at"), name="req_status_due_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(priority__gte=1, priority__lte=5),
                name="request_priority_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    @property
    def is_overdue(self):
        """True when past due_at and still active (not resolved/closed)."""
        return (
            self.due_at is not None
            and self.status in self.ACTIVE_STATUSES
            and self.due_at < timezone.now()
        )

    def clean(self):
        """Task 2 domain rule: a RESOLVED or CLOSED request must record when
        it was resolved and a non-empty resolution summary.

        Lives on the model so it runs for full_clean(), ModelForms, Django
        Admin and any service that calls full_clean() -- not only in Admin.
        """
        super().clean()
        if self.status in self.COMPLETED_STATUSES:
            errors = {}
            if self.resolved_at is None:
                errors["resolved_at"] = (
                    "A resolved or closed request must have a resolved_at timestamp."
                )
            if not (self.resolution_summary or "").strip():
                errors["resolution_summary"] = (
                    "A resolved or closed request requires a resolution summary."
                )
            if errors:
                raise ValidationError(errors)


class WorkOrder(models.Model):
    service_request = models.OneToOneField(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name="work_order",
    )
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_work_orders",
    )
    work_notes = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Work order for {self.service_request.title}"


class Comment(models.Model):
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="service_request_comments",
    )
    body = models.TextField()
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Comment by {self.author} on {self.service_request.title}"
