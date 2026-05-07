import logging
from statistics import mean
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from tournament.models import (
    Participant,
    Team,
    TeamInvitation,
    Tournament,
    TournamentRegistration,
)
from tournament.forms import (
    ParticipantForm,
    TeamForm,
    TournamentRegistrationForm,
)
from tournament.services import RegistrationService
from ..models import CustomUser
from ..policies import (
    is_participant_user,
    get_safe_redirect,
    get_dashboard_url_for_user,
    get_post_redirect,
)
from ..selectors import build_notification_nav_context
from ..team_services import TeamManagementService
from .utils import (
    build_team_detail_context,
    is_team_roster_locked,
    is_admin_user,
)

logger = logging.getLogger(__name__)

@login_required
def participant_dashboard(request):
    from .profile import profile_view
    return profile_view(request)

@login_required
def create_team(request):
    if not is_participant_user(request.user):
        return redirect('profile')

    next_url = request.GET.get('next') or request.POST.get('next')
    if request.method == 'POST':
        form = TeamForm(request.POST)
        if form.is_valid():
            team = TeamManagementService.create_team_for_user(user=request.user, form=form)
            messages.success(request, f'Команду "{team.name}" успішно створено!')
            return redirect(get_safe_redirect(request, next_url, reverse('participant_dashboard')))
    else:
        form = TeamForm(initial={'captain_name': request.user.username, 'captain_email': request.user.email})

    return render(request, 'create_team.html', {'form': form, 'next_url': next_url, 'mode': 'create'})

@login_required
def register_team_for_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, is_draft=False)
    if not is_participant_user(request.user):
        return render(request, 'register_team_for_tournament.html', {'tournament': tournament, 'not_a_participant': True})

    if not tournament.is_registration_open:
        return redirect('public_tournament_detail', tournament_id=tournament.id)

    already_registered = TournamentRegistration.objects.filter(
        Q(tournament=tournament) & (Q(team__captain_user=request.user) | Q(members__user=request.user)),
        status__in=[TournamentRegistration.Status.PENDING, TournamentRegistration.Status.APPROVED],
    ).exists()
    if already_registered:
        return render(request, 'register_team_for_tournament.html', {'tournament': tournament, 'already_registered': True})

    if tournament.max_teams and TournamentRegistration.objects.filter(
        tournament=tournament,
        status__in=[TournamentRegistration.Status.PENDING, TournamentRegistration.Status.APPROVED],
    ).count() >= tournament.max_teams:
        messages.error(request, 'На жаль, ліміт команд на цей турнір уже вичерпано.')
        return redirect('public_tournament_detail', tournament_id=tournament.id)

    if request.method == 'POST':
        form = TournamentRegistrationForm(request.POST, user=request.user, tournament=tournament)
        if form.is_valid():
            try:
                RegistrationService.submit_registration(
                    request=request,
                    tournament=tournament,
                    registered_by=request.user,
                    captain_user=request.user,
                    team_data=form.cleaned_team_data(),
                    form_answers=form.cleaned_form_answers(),
                    roster=form.cleaned_participants(),
                )
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Вашу заявку успішно надіслано!'})
                messages.success(request, 'Вашу заявку успішно надіслано!')
                return redirect('participant_dashboard')
            except ValidationError as exc:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': str(exc)})
                form.add_error(None, exc)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors.as_json()})
            messages.error(request, 'Помилка заповнення форми.')
    else:
        form = TournamentRegistrationForm(user=request.user, tournament=tournament)

    return render(request, 'register_team_for_tournament.html', {'form': form, 'tournament': tournament})

@login_required
def tournament_registration_options(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, is_draft=False)
    if not is_participant_user(request.user) or not tournament.is_registration_open:
        return redirect('public_tournament_detail', tournament_id=tournament.id)

    existing_registration = TournamentRegistration.objects.filter(
        Q(tournament=tournament) & (Q(team__captain_user=request.user) | Q(members__user=request.user)),
        status__in=[TournamentRegistration.Status.PENDING, TournamentRegistration.Status.APPROVED],
    ).exists()
    if existing_registration:
        return redirect('public_tournament_detail', tournament_id=tournament.id)

    captain_teams = Team.objects.filter(captain_user=request.user)
    return render(request, 'tournament_registration_options.html', {
        'tournament': tournament, 'has_existing_teams': captain_teams.exists(), 'captain_teams': captain_teams,
    })

@login_required
def register_existing_team(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, is_draft=False)
    if not is_participant_user(request.user) or not tournament.is_registration_open:
        return redirect('public_tournament_detail', tournament_id=tournament.id)
        
    captain_teams = Team.objects.filter(captain_user=request.user)
    if not captain_teams.exists():
        return redirect('tournament_registration_options', tournament_id=tournament.id)
        
    if request.method == 'POST':
        team_id = request.POST.get('team_id')
        team = get_object_or_404(captain_teams, id=team_id)
        errors = []
        members_count = team.members_count
        
        if tournament.min_team_members and members_count < tournament.min_team_members:
            errors.append(f"У команді замало людей. Потрібно щонайменше: {tournament.min_team_members}.")
        if tournament.max_team_members and members_count > tournament.max_team_members:
            errors.append(f"У команді забагато людей. Максимум: {tournament.max_team_members}.")
            
        if TournamentRegistration.objects.filter(tournament=tournament, team=team, status__in=[TournamentRegistration.Status.PENDING, TournamentRegistration.Status.APPROVED]).exists():
            errors.append("Ця команда вже зареєстрована.")

        if not errors:
            try:
                RegistrationService.submit_registration(
                    request=request, tournament=tournament, registered_by=request.user, captain_user=request.user,
                    team_data={
                        'name': team.name, 'captain_name': team.captain_name, 'captain_email': team.captain_email,
                        'school': team.school, 'preferred_contact_method': team.preferred_contact_method,
                        'preferred_contact_value': team.preferred_contact_value,
                    },
                    form_answers={}, roster=list(team.participants.values('full_name', 'email')), team=team,
                )
                messages.success(request, f'Команду "{team.name}" успішно зареєстровано!')
                return redirect('participant_dashboard')
            except ValidationError as exc:
                errors.append(str(exc))
        
        return render(request, 'register_existing_team.html', {
            'tournament': tournament, 'captain_teams': captain_teams, 'selected_team_id': int(team_id), 'errors': errors
        })

    return render(request, 'register_existing_team.html', {'tournament': tournament, 'captain_teams': captain_teams})

@login_required
def team_detail(request, team_id):
    team_queryset = Team.objects.select_related('captain_user').prefetch_related('registrations__tournament')
    if request.user.is_superuser:
        team = get_object_or_404(team_queryset, id=team_id)
    elif team_queryset.filter(id=team_id, captain_user=request.user).exists():
        team = get_object_or_404(team_queryset, id=team_id, captain_user=request.user)
    else:
        team = get_object_or_404(team_queryset, id=team_id, participants__email=request.user.email)

    return render(request, 'team_detail.html', build_team_detail_context(request, team))

@login_required
def edit_team(request, team_id):
    team_lookup = {'id': team_id}
    if not request.user.is_superuser:
        team_lookup['captain_user'] = request.user
    team = get_object_or_404(Team, **team_lookup)
    if is_team_roster_locked(team) and not request.user.is_superuser:
        return redirect('team_detail', team_id=team.id)

    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            TeamManagementService.update_team(form=form)
            messages.success(request, f'Дані команди "{team.name}" успішно оновлено!')
            return redirect('team_detail', team_id=team.id)
    else:
        form = TeamForm(instance=team)

    return render(request, 'create_team.html', {'form': form, 'next_url': reverse('team_detail', args=[team.id]), 'mode': 'edit'})

@login_required
def team_participants(request, team_id):
    team_queryset = Team.objects.select_related('captain_user').prefetch_related('participants')
    if request.user.is_superuser:
        team = get_object_or_404(team_queryset, id=team_id)
    elif team_queryset.filter(id=team_id, captain_user=request.user).exists():
        team = get_object_or_404(team_queryset, id=team_id, captain_user=request.user)
    else:
        team = get_object_or_404(team_queryset, id=team_id, participants__email=request.user.email)

    participants = list(team.participants.all().order_by('full_name'))
    if participants:
        participant_emails = [p.email.lower() for p in participants]
        users_by_email = {u.email.lower(): u for u in CustomUser.objects.filter(email__in=participant_emails)}
        for participant in participants:
            participant.linked_user = users_by_email.get(participant.email.lower())

    roster_locked = is_team_roster_locked(team) and not request.user.is_superuser
    return render(request, 'team_participants.html', {
        'team': team, 'participants': participants, 'can_manage_team': request.user.is_superuser or team.captain_user_id == request.user.id,
        'can_manage_roster': request.user.is_superuser or (team.captain_user_id == request.user.id and not roster_locked),
        'can_leave_team': not request.user.is_superuser and team.captain_user_id != request.user.id and team.participants.filter(email=request.user.email).exists() and not roster_locked,
        'roster_locked': roster_locked,
    })

@login_required
def add_participant(request, team_id):
    team_lookup = {'id': team_id}
    if not request.user.is_superuser:
        team_lookup['captain_user'] = request.user
    team = get_object_or_404(Team, **team_lookup)
    if is_team_roster_locked(team) and not request.user.is_superuser:
        return redirect('team_detail', team_id=team.id)

    if request.method == 'POST':
        form = ParticipantForm(request.POST)
        if form.is_valid():
            result = TeamManagementService.add_participant_to_team(request=request, team=team, form=form)
            if result.added or result.invited:
                messages.success(request, result.message or f'Учасника успішно додано!')
                return redirect('team_detail', team_id=team.id)
            form.add_error(result.field or 'email', result.message)
    else:
        form = ParticipantForm()

    return render(request, 'team_detail.html', build_team_detail_context(request, team, participant_form=form))

def confirm_invitation_view(request, token):
    invitation = get_object_or_404(TeamInvitation.objects.select_related('team'), token=token)
    team = invitation.team
    if is_team_roster_locked(team) and not request.user.is_superuser:
        messages.error(request, "Ростер команди заблоковано.")
        return redirect('home')

    if Participant.objects.filter(team=team, email__iexact=invitation.email).exists():
        invitation.delete()
        return redirect('team_detail', team_id=team.id)

    with transaction.atomic():
        Participant.objects.get_or_create(team=team, email=invitation.email, defaults={'full_name': invitation.full_name})
        invitation.delete()

    messages.success(request, f"Ви приєдналися до команди \"{team.name}\"!")
    return redirect('team_detail', team_id=team.id)

@login_required
def delete_participant(request, team_id, participant_id):
    team_lookup = {'id': team_id}
    if not request.user.is_superuser:
        team_lookup['captain_user'] = request.user
    team = get_object_or_404(Team, **team_lookup)
    if is_team_roster_locked(team) and not request.user.is_superuser:
        return redirect('team_detail', team_id=team.id)
    participant = get_object_or_404(Participant, id=participant_id, team=team)

    if request.method == 'POST':
        TeamManagementService.delete_participant(participant=participant)
        messages.success(request, f'Учасника {participant.full_name} видалено.')
    return redirect('team_detail', team_id=team.id)

@login_required
def delete_team(request, team_id):
    team_lookup = {'id': team_id}
    if not request.user.is_superuser:
        team_lookup['captain_user'] = request.user
    team = get_object_or_404(Team, **team_lookup)
    if is_team_roster_locked(team) and not request.user.is_superuser:
        return redirect('team_detail', team_id=team.id)

    if request.method == 'POST':
        TeamManagementService.delete_team(team=team)
        messages.success(request, f'Команду успішно видалено.')
        fallback = reverse('admin_teams') if is_admin_user(request.user) else reverse('participant_dashboard')
        return redirect(get_post_redirect(request, fallback))

    return render(request, 'delete_team_confirm.html', {'team': team})

@login_required
def leave_team(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    if is_team_roster_locked(team) and not request.user.is_superuser:
        return redirect('team_detail', team_id=team.id)
    get_object_or_404(Participant, team=team, email=request.user.email)

    if request.method == 'POST':
        TeamManagementService.leave_team(team=team, user=request.user)
        messages.success(request, f'Ви вийшли з команди.')
    return redirect('participant_dashboard')

@login_required
def team_results(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    if not request.user.is_superuser:
        is_member = team.captain_user_id == request.user.id or team.participants.filter(email=request.user.email).exists()
        if not is_member:
            return redirect('participant_dashboard')

    submissions = team.submissions.select_related('task', 'task__tournament').prefetch_related('jury_assignments__jury_user', 'jury_assignments__evaluation')
    result_rows = []
    collected_scores = []
    for submission in submissions:
        row_evaluations = []
        for assignment in submission.jury_assignments.all():
            evaluation = getattr(assignment, 'evaluation', None)
            if evaluation:
                row_evaluations.append({
                    'jury_name': assignment.jury_user.username, 'total': evaluation.total_score,
                    'comment': evaluation.comment, 'evaluated_at': evaluation.evaluated_at,
                    'backend': evaluation.score_backend, 'frontend': evaluation.score_frontend,
                    'functionality': evaluation.score_functionality, 'ux': evaluation.score_ux,
                })

        average_score = mean(item['total'] for item in row_evaluations) if row_evaluations else None
        if average_score is not None:
            collected_scores.append(average_score)

        result_rows.append({'submission': submission, 'evaluations': row_evaluations, 'average_score': average_score, 'evaluations_count': len(row_evaluations)})

    summary = {
        'submitted_count': submissions.count(), 'evaluated_count': sum(1 for row in result_rows if row['evaluations_count']),
        'overall_average': mean(collected_scores) if collected_scores else None, 'best_score': max(collected_scores) if collected_scores else None,
    }

    return render(request, 'team_results.html', {'team': team, 'result_rows': result_rows, 'summary': summary})
