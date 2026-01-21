"""
Django admin configuration.

Clean Architecture: Frameworks & Drivers layer.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    NodeRun,
    PromptTemplate,
    Run,
    User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom user admin."""

    list_display = ("email", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_active")
    search_fields = ("email",)
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(Graph)
class GraphAdmin(admin.ModelAdmin):
    """Graph admin."""

    list_display = ("name", "owner", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("name", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(GraphVersion)
class GraphVersionAdmin(admin.ModelAdmin):
    """GraphVersion admin."""

    list_display = ("graph", "version", "checksum", "created_at")
    list_filter = ("created_at",)
    search_fields = ("graph__name",)
    readonly_fields = ("id", "checksum", "created_at")


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    """PromptTemplate admin."""

    list_display = ("title", "category", "owner", "visibility", "created_at")
    list_filter = ("category", "visibility", "created_at")
    search_fields = ("title", "description", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")


class NodeRunInline(admin.TabularInline):
    model = NodeRun
    extra = 0
    show_change_link = True
    fields = ("node_id", "node_type", "status", "attempt", "started_at", "ended_at")


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    """Run admin."""

    list_display = ("id", "owner", "graph_version", "status", "started_at", "ended_at")
    list_filter = ("status", "started_at")
    search_fields = ("owner__email",)
    readonly_fields = ("id",)
    inlines = [NodeRunInline]


@admin.register(NodeRun)
class NodeRunAdmin(admin.ModelAdmin):
    """NodeRun admin."""

    list_display = ("node_id", "node_type", "run", "status", "attempt", "started_at")
    list_filter = ("status", "node_type")
    search_fields = ("node_id", "run__id")
    readonly_fields = ("id",)
