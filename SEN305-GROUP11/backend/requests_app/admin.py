from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from .models import Category, Comment, ServiceRequest, WorkOrder


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("author", "body", "is_internal", "created_at")
    readonly_fields = ("created_at",)


class DueStateFilter(admin.SimpleListFilter):
    """Overdue filter strategy (Task 1, step 4).

    'Overdue' is NOT "due_at < now" alone: a request that was resolved after
    its deadline is finished and must not keep showing up as overdue. The
    definition lives in ServiceRequestQuerySet.overdue(), so Admin, tests and
    future views all use the same rule.
    """

    title = "due state"
    parameter_name = "due_state"

    def lookups(self, request, model_admin):
        return (
            ("overdue", "Overdue (past due, still active)"),
            ("next_24h", "Due in the next 24 hours"),
            ("later", "Due later than 24 hours"),
            ("none", "No due date"),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        value = self.value()
        if value == "overdue":
            return queryset.overdue(now)
        if value == "next_24h":
            return queryset.active().filter(
                due_at__gte=now, due_at__lt=now + timedelta(hours=24)
            )
        if value == "later":
            return queryset.active().filter(due_at__gte=now + timedelta(hours=24))
        if value == "none":
            return queryset.filter(due_at__isnull=True)
        return queryset


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "title", "category", "requester", "priority", "status",
        "due_at", "overdue", "resolved_at", "created_at",
    )
    list_filter = ("status", DueStateFilter, "priority", "category")
    search_fields = (
        "title", "description", "location", "requester__username",
        "resolution_summary",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("requester", "category")
    date_hierarchy = "created_at"
    inlines = (CommentInline,)
    fieldsets = (
        (None, {
            "fields": (
                "id", "requester", "category", "title", "description",
                "location", "priority", "status",
            ),
        }),
        ("Service level", {"fields": ("due_at",)}),
        ("Resolution", {"fields": ("resolved_at", "resolution_summary")}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(boolean=True, description="Overdue")
    def overdue(self, obj):
        return obj.is_overdue


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ("service_request", "technician", "started_at", "completed_at")
    search_fields = ("service_request__title", "technician__username")
    autocomplete_fields = ("service_request", "technician")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("service_request", "author", "is_internal", "created_at")
    list_filter = ("is_internal", "created_at")
    search_fields = ("body", "service_request__title", "author__username")
