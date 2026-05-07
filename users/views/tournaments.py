import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from tournament.models import (
    BannerTemplate,
    Submission,
    Task,
    Tournament,
    TournamentRegistration,
)
from tournament.forms import (
    SubmissionForm,
    TaskForm,
    TournamentForm,
    TournamentRegistrationForm,
)
from tournament.services import RegistrationService, TournamentLifecycleService
from tournament.submission_formats import (
    TASK_SUBMISSION_PRESETS,
    task_submission_field_type_choices,
)
from ..policies import (
    is_admin_user,
    is_participant_user,
    can_manage_tournaments,
    can_manage_tournament_instance,
    can_export_tournament_results,
    get_dashboard_url_for_user,
    get_post_redirect,
)
from ..selectors import build_notification_nav_context
from .utils import (
    build_tournament_leaderboard,
    finalize_tournament_evaluation_if_ready,
    is_tournament_edit_locked,
    serialize_leaderboard_rows,
)

logger = logging.getLogger(__name__)

def public_tournament_detail(request, tournament_id):
    tournament = get_object_or_404(
        Tournament.objects.prefetch_related('tasks', 'schedule_items', 'jury_users').select_related('created_by'),
        id=tournament_id,
        is_draft=False,
    )
    leaderboard = build_tournament_leaderboard(tournament) if tournament.evaluation_results_ready else []
    existing_registration = None
    viewer_can_register = (
        request.user.is_authenticated
        and request.user.role == 'participant'
        and not request.user.is_superuser
    )

    if request.user.is_authenticated:
        existing_registration = TournamentRegistration.objects.filter(
            Q(tournament=tournament) & 
            (Q(team__captain_user=request.user) | Q(members__user=request.user))
        ).select_related('team').prefetch_related('members').order_by('-created_at').first()

    if tournament.is_registration_open and (viewer_can_register or not request.user.is_authenticated):
        if request.method == 'POST' and viewer_can_register:
             # Full registration logic moved to specific view, but keeping skeletal redirect here if needed
             pass

    current_path = reverse('public_tournament_detail', args=[tournament.id])
    return render(request, 'public_tournament_detail.html', {
        'tournament': tournament,
        'tasks': tournament.tasks.filter(is_draft=False),
        'leaderboard_preview': leaderboard[:5],
        'leaderboard_total': len(leaderboard),
        'show_public_leaderboard': tournament.evaluation_results_ready,
        'existing_registration': existing_registration,
        'viewer_can_register': viewer_can_register,
        'register_url': f"{reverse('register')}?next={current_path}",
        'login_url': f"{reverse('login')}?next={current_path}",
        'jury_users': tournament.jury_users.all(),
    })

@login_required
def create_tournament(request):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')

    dashboard_url = reverse('admin_active_tournaments') if is_admin_user(request.user) else get_dashboard_url_for_user(request.user)
    if request.method == 'POST':
        form = TournamentForm(request.POST, request.FILES)
        if form.is_valid():
            form.instance.created_by = request.user
            form.save()
            return redirect(dashboard_url)
    else:
        form = TournamentForm()

    return render(request, 'create_tournament.html', {
        'form': form,
        'mode': 'create',
        'dashboard_url': dashboard_url,
        'banner_templates': BannerTemplate.objects.all(),
    })

@login_required
def edit_tournament(request, tournament_id):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')

    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not can_manage_tournament_instance(request.user, tournament):
        return redirect('redirect_by_role')
    if is_tournament_edit_locked(tournament) and not request.user.is_superuser:
        return redirect(get_dashboard_url_for_user(request.user))

    if request.method == 'POST':
        form = TournamentForm(request.POST, request.FILES, instance=tournament)
        if form.is_valid():
            form.save()
            return redirect(reverse('admin_active_tournaments') if is_admin_user(request.user) else get_dashboard_url_for_user(request.user))
    else:
        form = TournamentForm(instance=tournament)

    return render(request, 'create_tournament.html', {
        'form': form,
        'mode': 'edit',
        'tournament': tournament,
        'tasks': tournament.tasks.all(),
        'dashboard_url': reverse('admin_active_tournaments') if is_admin_user(request.user) else get_dashboard_url_for_user(request.user),
        'banner_templates': BannerTemplate.objects.all(),
    })

@login_required
def delete_tournament(request, tournament_id):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect(get_dashboard_url_for_user(request.user))

    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not can_manage_tournament_instance(request.user, tournament):
        return redirect('redirect_by_role')
    tournament.delete()
    fallback = reverse('admin_active_tournaments') if is_admin_user(request.user) else get_dashboard_url_for_user(request.user)
    return redirect(get_post_redirect(request, fallback))

@login_required
def start_tournament_now(request, tournament_id):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect(get_dashboard_url_for_user(request.user))

    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not can_manage_tournament_instance(request.user, tournament):
        return redirect('redirect_by_role')

    tournament = TournamentLifecycleService.start_now(tournament=tournament)
    finalize_tournament_evaluation_if_ready(tournament, finished_by=request.user)
    return redirect(get_post_redirect(request, get_dashboard_url_for_user(request.user)))

@login_required
def finish_tournament_now(request, tournament_id):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect(get_dashboard_url_for_user(request.user))

    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not can_manage_tournament_instance(request.user, tournament):
        return redirect('redirect_by_role')

    TournamentLifecycleService.finish_now(tournament=tournament)
    return redirect(get_post_redirect(request, get_dashboard_url_for_user(request.user)))

@login_required
def finish_evaluation_now(request, tournament_id):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect(get_dashboard_url_for_user(request.user))

    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not can_manage_tournament_instance(request.user, tournament):
        return redirect('redirect_by_role')
    if not tournament.is_finished:
        return redirect(get_post_redirect(request, get_dashboard_url_for_user(request.user)))

    TournamentLifecycleService.finish_evaluation(tournament=tournament, finished_by=request.user)
    return redirect(get_post_redirect(request, get_dashboard_url_for_user(request.user)))

@login_required
def create_task(request, tournament_id=None):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')

    tournament = None
    if tournament_id is not None:
        tournament = get_object_or_404(Tournament, id=tournament_id)
        if not can_manage_tournament_instance(request.user, tournament):
            return redirect('redirect_by_role')
        if is_tournament_edit_locked(tournament) and not request.user.is_superuser:
            return redirect(get_dashboard_url_for_user(request.user))

    if request.method == 'POST':
        form = TaskForm(request.POST, tournament=tournament)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            task.save()
            return redirect('edit_tournament', tournament_id=task.tournament_id)
    else:
        form = TaskForm(tournament=tournament)

    return render(request, 'create_task.html', {
        'form': form,
        'mode': 'create',
        'tournament': tournament,
        'task_submission_presets': TASK_SUBMISSION_PRESETS,
        'task_submission_field_types': task_submission_field_type_choices(),
        'back_url': reverse('edit_tournament', args=[tournament.id]) if tournament else reverse('admin_active_tournaments'),
    })

@login_required
def edit_task(request, task_id):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')

    task = get_object_or_404(Task, id=task_id)
    if not can_manage_tournament_instance(request.user, task.tournament):
        return redirect('redirect_by_role')
    if is_tournament_edit_locked(task.tournament) and not request.user.is_superuser:
        return redirect(get_dashboard_url_for_user(request.user))

    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            return redirect('edit_tournament', tournament_id=task.tournament_id)
    else:
        form = TaskForm(instance=task)

    return render(request, 'create_task.html', {
        'form': form,
        'mode': 'edit',
        'task': task,
        'tournament': task.tournament,
        'task_submission_presets': TASK_SUBMISSION_PRESETS,
        'task_submission_field_types': task_submission_field_type_choices(),
        'back_url': reverse('edit_tournament', args=[task.tournament_id]),
    })

@login_required
def delete_task(request, task_id):
    if not can_manage_tournaments(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect(get_dashboard_url_for_user(request.user))

    task = get_object_or_404(Task, id=task_id)
    if not can_manage_tournament_instance(request.user, task.tournament):
        return redirect('redirect_by_role')
    task.delete()
    fallback = reverse('admin_active_tournaments') if is_admin_user(request.user) else get_dashboard_url_for_user(request.user)
    return redirect(get_post_redirect(request, fallback))

@login_required
def tournament_tasks(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, is_draft=False)
    if not (tournament.is_running or tournament.is_finished):
        return redirect('participant_dashboard')

    my_registration = TournamentRegistration.objects.filter(
        Q(tournament=tournament) & (Q(team__captain_user=request.user) | Q(members__user=request.user)),
        status=TournamentRegistration.Status.APPROVED
    ).select_related('team').first()
    
    if not my_registration and not request.user.is_superuser:
        return redirect('participant_dashboard')

    tasks = Task.objects.filter(tournament=tournament, is_draft=False)
    leaderboard = build_tournament_leaderboard(tournament) if tournament.evaluation_results_ready else []
    my_team = my_registration.team if my_registration else None
    my_rank = None
    if my_team and tournament.evaluation_results_ready:
        for row in leaderboard:
            if row['team'].id == my_team.id:
                my_rank = row['place']
                break

    return render(request, 'tournament_tasks.html', {
        'tournament': tournament,
        'tasks': tasks,
        'leaderboard_preview': leaderboard[:5],
        'leaderboard_total': len(leaderboard),
        'my_team': my_team,
        'my_rank': my_rank,
        'show_official_solutions': tournament.is_finished,
        'show_leaderboard': tournament.evaluation_results_ready,
    })

@login_required
def tournament_leaderboard(request, tournament_id):
    tournament = get_object_or_404(Tournament.objects.prefetch_related('schedule_items'), id=tournament_id, is_draft=False)
    if not tournament.evaluation_results_ready and not request.user.is_superuser:
        return redirect('tournament_tasks', tournament_id=tournament.id)

    my_registration = TournamentRegistration.objects.filter(
        Q(tournament=tournament) & (Q(team__captain_user=request.user) | Q(members__user=request.user)),
        status=TournamentRegistration.Status.APPROVED
    ).select_related('team').first()
    
    if my_registration is None and not request.user.is_superuser:
        return redirect('participant_dashboard')

    leaderboard = build_tournament_leaderboard(tournament)
    my_team = my_registration.team if my_registration else None
    if request.GET.get('format') == 'json':
        return JsonResponse({
            'tournament': tournament.name,
            'updated_at': timezone.localtime(timezone.now()).strftime('%H:%M:%S'),
            'rows': serialize_leaderboard_rows(leaderboard, my_team=my_team),
        })

    return render(request, 'tournament_leaderboard.html', {
        'tournament': tournament,
        'leaderboard': leaderboard,
        'my_team': my_team,
        'can_export_results': can_export_tournament_results(request.user, tournament) and tournament.evaluation_results_ready,
    })

@login_required
def submit_solution(request, task_id):
    task = get_object_or_404(Task.objects.select_related('tournament'), id=task_id, is_draft=False)
    tournament = task.tournament
    if not (tournament.is_running or tournament.is_finished):
        return redirect('participant_dashboard')
    if not task.is_submission_open:
        return redirect('tournament_tasks', tournament_id=tournament.id)

    my_registration = TournamentRegistration.objects.filter(
        Q(tournament=tournament) & (Q(team__captain_user=request.user) | Q(members__user=request.user)),
        status=TournamentRegistration.Status.APPROVED
    ).select_related('team').first()
    
    team = my_registration.team if my_registration else None
    if not team:
        return redirect('participant_dashboard')

    submission = Submission.objects.filter(team=team, task=task).first()
    if request.method == 'POST':
        form = SubmissionForm(request.POST, request.FILES, instance=submission, task=task)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.team = team
            submission.task = task
            submission.save()
            messages.success(request, f'Рішення до завдання "{task.title}" успішно надіслано!')
            return redirect('team_detail', team_id=team.id)
    else:
        form = SubmissionForm(instance=submission, task=task)

    return render(request, 'submit_solution.html', {
        'task': task, 'team': team, 'form': form, 'submission': submission,
    })
