from django.contrib import admin
from django.utils.html import format_html

from .models import (
    School,
    BannerTemplate,
    Tournament,
    Team,
    Participant,
    TournamentRegistration,
    Task,
    Submission,
    JuryAssignment,
    Evaluation,
)

from users.policies import (
    is_super_admin,
    is_admin_user,
    is_organizer_user,
    is_participant_user,
    is_organizer_user as is_organizer,
    is_jury_user as is_jury,
)

# Helper utilities -----------------------------------------------------------

def can_view_tournament(user, obj):
    if is_super_admin(user) or is_admin_user(user):
        return True
    if is_organizer_user(user) and obj.created_by_id == user.id:
        return True
    if is_jury(user) and obj.jury_users.filter(id=user.id).exists():
        return True
    return False

# Admin registrations -------------------------------------------------------

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "city")
    search_fields = ("name", "short_name", "city")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Schools are globally visible for admins; participants see none.
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        return qs.none()

    def has_module_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_change_permission(self, request, obj=None):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_add_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user) or is_admin_user(request.user)

@admin.register(BannerTemplate)
class BannerTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        return qs.none()

    def has_module_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_change_permission(self, request, obj=None):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_add_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user) or is_admin_user(request.user)

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "lifecycle_status",
        "created_by",
        "is_draft",
        "start_date",
        "end_date",
    )
    list_filter = ("is_draft",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        if is_organizer_user(request.user):
            return qs.filter(created_by=request.user)
        # Jury sees only tournaments they are assigned to
        if is_jury(request.user):
            return qs.filter(jury_users=request.user)
        return qs.none()

    def has_module_permission(self, request):
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_jury(request.user)
        )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return self.has_module_permission(request)
        return can_view_tournament(request.user, obj)

    def has_change_permission(self, request, obj=None):
        if obj is None:
            # Creating a new tournament – only admins/organizers may add
            return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)
        return can_view_tournament(request.user, obj)

    def has_delete_permission(self, request, obj=None):
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_add_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "captain_user", "members_count", "tournament_list")
    search_fields = ("name", "captain_name", "captain_email")
    readonly_fields = ("created_at",)

    def tournament_list(self, obj):
        # Show tournaments the team is registered for (distinct)
        tournaments = Tournament.objects.filter(registrations__team=obj).distinct()
        return ", ".join(t.name for t in tournaments)
    tournament_list.short_description = "Турніри"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        if is_organizer_user(request.user):
            # Teams that belong to tournaments created by the organizer
            return qs.filter(registrations__tournament__created_by=request.user).distinct()
        if is_participant_user(request.user):
            return qs.filter(
                models.Q(captain_user=request.user) |
                models.Q(participants__email=request.user.email)
            ).distinct()
        return qs.none()

    def has_module_permission(self, request):
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_participant_user(request.user)
        )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return self.has_module_permission(request)
        return obj in self.get_queryset(request)

    def has_change_permission(self, request, obj=None):
        # Only admins or the captain can edit a team
        if obj is None:
            return False
        if is_super_admin(request.user) or is_admin_user(request.user):
            return True
        return obj.captain_user_id == request.user.id

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def has_add_permission(self, request):
        # Participants can create their own team via the UI; admins/organizers also allowed
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_participant_user(request.user)
        )

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "team")
    search_fields = ("full_name", "email")
    readonly_fields = ("team",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        if is_organizer_user(request.user):
            return qs.filter(team__registrations__tournament__created_by=request.user).distinct()
        if is_participant_user(request.user):
            return qs.filter(
                models.Q(team__captain_user=request.user) |
                models.Q(email=request.user.email)
            ).distinct()
        return qs.none()

    def has_module_permission(self, request):
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_participant_user(request.user)
        )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return self.has_module_permission(request)
        return obj in self.get_queryset(request)

    def has_change_permission(self, request, obj=None):
        # Participants cannot edit other participants; only admins/organizers can.
        if obj is None:
            return False
        return is_super_admin(request.user) or is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def has_add_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

@admin.register(TournamentRegistration)
class TournamentRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "team",
        "tournament",
        "registered_by",
        "status",
        "created_at",
    )
    list_filter = ("status", "tournament__is_draft")
    search_fields = ("team__name", "tournament__name", "registered_by__username")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        if is_organizer_user(request.user):
            return qs.filter(tournament__created_by=request.user)
        if is_jury(request.user):
            # Jury can view registrations of tournaments they are assigned to
            return qs.filter(tournament__jury_users=request.user)
        if is_participant_user(request.user):
            # Participant sees own registrations
            return qs.filter(
                models.Q(team__captain_user=request.user) |
                models.Q(team__participants__email=request.user.email)
            ).distinct()
        return qs.none()

    def has_module_permission(self, request):
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_jury(request.user)
            or is_participant_user(request.user)
        )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return self.has_module_permission(request)
        return obj in self.get_queryset(request)

    def has_change_permission(self, request, obj=None):
        # Only admins/organizers can modify registrations.
        if obj is None:
            return False
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def has_add_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "tournament", "is_draft", "effective_start", "effective_deadline")
    list_filter = ("is_draft", "tournament__is_draft")
    search_fields = ("title", "tournament__name")
    readonly_fields = ("created_by",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        if is_organizer_user(request.user):
            return qs.filter(tournament__created_by=request.user)
        if is_participant_user(request.user):
            # Participants see tasks of tournaments they are registered for
            return qs.filter(tournament__registrations__team__participants__email=request.user.email).distinct()
        return qs.none()

    def has_module_permission(self, request):
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_participant_user(request.user)
        )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return self.has_module_permission(request)
        return obj in self.get_queryset(request)

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)
        return obj.tournament.created_by_id == request.user.id or is_super_admin(request.user) or is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def has_add_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "team",
        "task",
        "submitted_at",
        "is_final",
    )
    list_filter = ("is_final", "task__tournament__is_draft")
    search_fields = ("team__name", "task__title")
    readonly_fields = ("submitted_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        if is_organizer_user(request.user):
            return qs.filter(task__tournament__created_by=request.user)
        if is_jury(request.user):
            return qs.filter(jury_assignments__jury_user=request.user).distinct()
        if is_participant_user(request.user):
            return qs.filter(team__captain_user=request.user).distinct()
        return qs.none()

    def has_module_permission(self, request):
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_jury(request.user)
            or is_participant_user(request.user)
        )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return self.has_module_permission(request)
        return obj in self.get_queryset(request)

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)
        # Participants can edit their own submissions before deadline
        if is_participant_user(request.user) and obj.team.captain_user_id == request.user.id:
            return obj.task.is_submission_open
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def has_add_permission(self, request):
        # Adding submissions is handled through the UI; admin may add directly.
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

@admin.register(JuryAssignment)
class JuryAssignmentAdmin(admin.ModelAdmin):
    list_display = ("jury_user", "submission", "assignment_link")
    readonly_fields = ("jury_user", "submission")

    def assignment_link(self, obj):
        url = reverse("admin:{0}_{1}_change".format(obj._meta.app_label, obj._meta.model_name), args=[obj.id])
        return format_html('<a href="{}">Edit</a>', url)
    assignment_link.short_description = "Link"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        if is_organizer_user(request.user):
            return qs.filter(submission__task__tournament__created_by=request.user)
        if is_jury(request.user):
            return qs.filter(jury_user=request.user)
        return qs.none()

    def has_module_permission(self, request):
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_jury(request.user)
        )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return self.has_module_permission(request)
        return obj in self.get_queryset(request)

    def has_change_permission(self, request, obj=None):
        # Only admins/organizers may edit assignments.
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

    def has_add_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = (
        "assignment",
        "total_score",
        "evaluated_at",
    )
    readonly_fields = ("assignment", "evaluated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_super_admin(request.user) or is_admin_user(request.user):
            return qs
        if is_organizer_user(request.user):
            return qs.filter(assignment__submission__task__tournament__created_by=request.user)
        if is_jury(request.user):
            return qs.filter(assignment__jury_user=request.user)
        return qs.none()

    def has_module_permission(self, request):
        return (
            is_super_admin(request.user)
            or is_admin_user(request.user)
            or is_organizer_user(request.user)
            or is_jury(request.user)
        )

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return self.has_module_permission(request)
        return obj in self.get_queryset(request)

    def has_change_permission(self, request, obj=None):
        # Only admins/organizers may edit evaluations.
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

    def has_add_permission(self, request):
        return is_super_admin(request.user) or is_admin_user(request.user) or is_organizer_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)
