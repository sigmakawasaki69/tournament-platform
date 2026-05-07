import logging
import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from tournament.models import (
    Announcement,
    Certificate,
    Evaluation,
    Team,
    TeamInvitation,
    Tournament,
    TournamentRegistration,
)
from ..models import CustomUser
from ..selectors import (
    build_notification_nav_context,
    get_primary_team_with_quick_overview,
    build_public_announcements,
    build_user_certificates_queryset,
)
from ..policies import is_participant_user
from .utils import build_tournament_leaderboard

logger = logging.getLogger(__name__)

@login_required
def profile_view(request):
    my_teams = Team.objects.filter(
        Q(captain_user=request.user) | Q(participants__email=request.user.email)
    ).select_related('captain_user').prefetch_related(
        'participants',
        'registrations__tournament',
    ).distinct()

    my_registrations = list(TournamentRegistration.objects.select_related(
        'tournament',
        'team',
        'team__captain_user',
    ).prefetch_related('team__participants', 'members').filter(
        Q(team__captain_user=request.user) | Q(members__user=request.user)
    ).distinct())

    primary_team_id = request.session.get('primary_team_id')
    active_team, _, _ = get_primary_team_with_quick_overview(request.user, primary_team_id=primary_team_id)

    involved_tournament_ids = [reg.tournament_id for reg in my_registrations]

    visible_tournaments = list(
        Tournament.objects.filter(
            Q(id__in=involved_tournament_ids) |
            Q(created_by=request.user) |
            Q(jury_users=request.user)
        ).filter(is_draft=False).distinct().order_by('-start_date')
    )

    my_registration_by_tournament_id = {}
    for reg in my_registrations:
        current = my_registration_by_tournament_id.get(reg.tournament_id)
        if current is None:
            my_registration_by_tournament_id[reg.tournament_id] = reg
            continue
        if current.status == TournamentRegistration.Status.REJECTED and reg.status != TournamentRegistration.Status.REJECTED:
            my_registration_by_tournament_id[reg.tournament_id] = reg

    tournaments_with_state = []
    for tournament in visible_tournaments:
        existing_registration = my_registration_by_tournament_id.get(tournament.id)
        active_registration = (
            existing_registration
            if existing_registration is not None
            and existing_registration.status != TournamentRegistration.Status.REJECTED
            else None
        )
        can_register = (
            is_participant_user(request.user)
            and tournament.is_registration_open
            and active_registration is None
        )
        can_open_tasks = (
            active_registration is not None
            and active_registration.status == TournamentRegistration.Status.APPROVED
            and (tournament.is_running or tournament.is_finished)
        )

        my_rank = None
        if active_registration and tournament.evaluation_results_ready:
            leaderboard = build_tournament_leaderboard(tournament)
            for row in leaderboard:
                if row['team'].id == active_registration.team_id:
                    my_rank = row['place']
                    break

        tournaments_with_state.append({
            'tournament': tournament,
            'my_registration': existing_registration,
            'my_team': active_registration.team if active_registration else None,
            'my_rank': my_rank,
            'can_register': can_register,
            'can_open_tasks': can_open_tasks,
            'can_view_leaderboard': (
                active_registration is not None
                and active_registration.status == TournamentRegistration.Status.APPROVED
                and tournament.evaluation_results_ready
            ),
        })

    announcements = build_public_announcements()
    certificates = build_user_certificates_queryset(request.user)

    jury_evaluations = None
    if request.user.role == 'jury':
        jury_evaluations = Evaluation.objects.filter(
            assignment__jury_user=request.user
        ).select_related(
            'assignment__submission__team',
            'assignment__submission__task',
            'assignment__submission__task__tournament'
        ).order_by('-evaluated_at')

    pending_invitations = TeamInvitation.objects.filter(email__iexact=request.user.email).select_related('team')

    return render(request, 'profile.html', {
        'profile_user': request.user,
        'my_teams': my_teams,
        'active_team': active_team,
        'tournaments_with_state': tournaments_with_state,
        'announcements': announcements,
        'certificates': certificates,
        'jury_evaluations': jury_evaluations,
        'pending_invitations': pending_invitations,
        **build_notification_nav_context(request.user),
    })

def public_profile(request, user_id):
    target_user = get_object_or_404(CustomUser, id=user_id)
    if request.user.is_authenticated and request.user.id == target_user.id:
        return redirect('profile')

    tournaments_created_count = Tournament.objects.filter(
        created_by=target_user, is_draft=False
    ).count()

    jury_tournaments_count = target_user.jury_tournaments.filter(is_draft=False).count()

    teams = Team.objects.filter(
        Q(captain_user=target_user) | Q(participants__email=target_user.email)
    ).select_related('captain_user').prefetch_related(
        'registrations__tournament',
        'participants',
    ).annotate(
        total_members=Count('participants', distinct=True)
    ).distinct()

    organized_tournaments = []
    if target_user.role in ['organizer', 'admin']:
        organized_tournaments = Tournament.objects.filter(
            created_by=target_user, is_draft=False
        ).order_by('-start_date')

    participated_tournaments = []
    for team in teams:
        for reg in team.registrations.all():
            if reg.status == TournamentRegistration.Status.APPROVED and not reg.tournament.is_draft:
                participated_tournaments.append({
                    'tournament': reg.tournament,
                    'team': team,
                })

    jury_evaluations_count = 0
    if target_user.role == 'jury':
        jury_evaluations_count = Evaluation.objects.filter(
            assignment__jury_user=target_user
        ).count()

    context = {
        'target_user': target_user,
        'tournaments_created_count': tournaments_created_count,
        'organized_tournaments': organized_tournaments,
        'jury_tournaments_count': jury_tournaments_count,
        'participated_tournaments': participated_tournaments,
        'jury_evaluations_count': jury_evaluations_count,
        'teams': teams,
    }
    if request.user.is_authenticated:
        context.update(build_notification_nav_context(request.user))
    return render(request, 'public_profile.html', context)

@login_required
def profile_settings(request):
    user = request.user
    success_message = None
    error_message = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'change_username':
            new_username = request.POST.get('new_username', '').strip()
            is_ajax = request.POST.get('is_ajax') == '1'
            if not new_username:
                error_message = 'Нікнейм не може бути порожнім.'
            elif len(new_username) < 3:
                error_message = 'Нікнейм повинен містити щонайменше 3 символи.'
            elif len(new_username) > 30:
                error_message = 'Нікнейм не може бути довшим за 30 символів.'
            elif CustomUser.objects.filter(username__iexact=new_username).exclude(pk=user.pk).exists():
                error_message = 'Цей нікнейм вже зайнятий.'
            else:
                user.username = new_username
                user.save(update_fields=['username'])
                success_message = 'Нікнейм успішно змінено.'

            if is_ajax:
                if error_message:
                    return JsonResponse({'status': 'error', 'message': error_message})
                return JsonResponse({'status': 'ok', 'message': success_message})

        elif action == 'change_password':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            new_password_confirm = request.POST.get('new_password_confirm', '')
            is_ajax = request.POST.get('is_ajax') == '1'

            try:
                if not user.check_password(old_password):
                    error_message = 'Поточний пароль невірний.'
                elif new_password != new_password_confirm:
                    error_message = 'Паролі не збігаються.'
                elif old_password == new_password:
                    error_message = 'Новий пароль не може збігатися з поточним.'
                else:
                    try:
                        validate_password(new_password, user)
                        user.set_password(new_password)
                        user.save()
                        update_session_auth_hash(request, user)
                        success_message = 'Пароль успішно змінено.'
                    except ValidationError as e:
                        error_message = e.messages[0]
            except Exception:
                logger.exception("Unexpected error in change_password")
                error_message = 'Виникла непередбачена помилка. Спробуйте ще раз.'

            if is_ajax:
                if error_message:
                    return JsonResponse({'status': 'error', 'message': error_message})
                return JsonResponse({'status': 'ok', 'message': success_message})

        elif action == 'change_avatar':
            avatar_file = request.FILES.get('avatar')
            is_ajax = request.POST.get('is_ajax') == '1'
            if avatar_file:
                if not avatar_file.content_type.startswith('image/'):
                    error_message = 'Завантажте файл зображення (PNG, JPG, JPEG).'
                elif avatar_file.size > 5 * 1024 * 1024:
                    error_message = 'Максимальний розмір аватарки — 5 МБ.'
                else:
                    user.avatar = avatar_file
                    user.save(update_fields=['avatar'])
                    success_message = 'Аватарку успішно оновлено.'
            else:
                error_message = 'Виберіть файл зображення.'

            if is_ajax:
                resp = {'status': 'error' if error_message else 'ok', 'message': error_message or success_message}
                if not error_message and user.avatar:
                    resp['avatar_url'] = user.avatar.url
                return JsonResponse(resp)

        elif action == 'remove_avatar':
            is_ajax = request.POST.get('is_ajax') == '1'
            if user.avatar:
                user.avatar.delete(save=False)
                user.avatar = None
                user.save(update_fields=['avatar'])
                success_message = 'Аватарку видалено.'

            if is_ajax:
                if error_message:
                    return JsonResponse({'status': 'error', 'message': error_message})
                return JsonResponse({'status': 'ok', 'message': success_message or 'Аватарку видалено.'})

    return render(request, 'profile_settings.html', {
        'profile_user': user,
        'success_message': success_message,
        'error_message': error_message,
        'telegram_bot_username': getattr(settings, 'TELEGRAM_BOT_USERNAME', 'Tournament_manager_bot'),
        'discord_bot_name': getattr(settings, 'DISCORD_BOT_NAME', 'Tournament Bot'),
        'discord_invite_url': getattr(settings, 'DISCORD_INVITE_URL', ''),
        **build_notification_nav_context(user),
    })

@login_required
def my_team_view(request):
    if not is_participant_user(request.user):
        return redirect('redirect_by_role')

    primary_team_id = request.session.get('primary_team_id')
    teams = Team.objects.filter(
        Q(captain_user=request.user) | Q(participants__email=request.user.email)
    ).distinct()

    team = None
    if primary_team_id:
        team = teams.filter(id=primary_team_id).first()
    
    if not team:
        team = teams.order_by('name').first()

    if team is not None:
        return redirect('team_detail', team_id=team.id)
    return redirect('create_team')

@csrf_exempt
def api_register_social_code(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    token = request.headers.get('X-Bot-Token')
    if token != getattr(settings, 'BOT_API_TOKEN', 'debug_token'):
         return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        provider = data.get('provider')
        social_id = data.get('social_id')
        code = data.get('code')
        
        if not all([provider, social_id, code]):
            return JsonResponse({'error': 'Missing fields'}, status=400)

        already_verified = False
        if provider == 'telegram':
            already_verified = CustomUser.objects.filter(telegram_id=social_id, is_tg_verified=True).exists()
        elif provider == 'discord':
            already_verified = CustomUser.objects.filter(discord_id=social_id, is_discord_verified=True).exists()
            
        if already_verified:
            return JsonResponse({'status': 'already_verified'})

        cache_key = f"social_verify_{provider}_{code}"
        cache.set(cache_key, social_id, timeout=300)

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def verify_social_code(request):
    if request.method != 'POST':
        return redirect('profile_settings')
    
    provider = request.POST.get('provider')
    code = request.POST.get('code', '').strip()
    
    if not provider or not code:
        messages.error(request, "Будь ласка, введіть код.")
        return redirect('profile_settings')

    cache_key = f"social_verify_{provider}_{code}"
    social_id = cache.get(cache_key)
    
    if not social_id:
        messages.error(request, "Невірний або прострочений код.")
        return redirect('profile_settings')

    user = request.user
    if provider == 'telegram':
        user.telegram_id = social_id
        user.is_tg_verified = True
    elif provider == 'discord':
        user.discord_id = social_id
        user.is_discord_verified = True
    
    try:
        user.save()
        cache.delete(cache_key)
        messages.success(request, f"Ваш {provider.capitalize()} успішно підтверджено!")
    except Exception:
        messages.error(request, "Цей акаунт вже прив'язаний до іншого користувача.")
    
    return redirect('profile_settings')
