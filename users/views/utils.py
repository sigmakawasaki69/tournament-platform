import os
import io
import logging
import csv
import mimetypes
from statistics import mean
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, FileResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from tournament.models import (
    Certificate,
    CertificateTemplate,
    Submission,
    Tournament,
    TournamentRegistration,
    JuryAssignment,
)
from ..forms import AdminCreateUserForm
from tournament.forms import TournamentForm
from ..models import CustomUser
from ..policies import (
    is_admin_user,
    get_available_admin_roles,
)
from ..selectors import (
    build_admin_dashboard_data,
    build_public_tournament_rows,
    build_public_announcements,
    build_team_quick_overview,
    collect_registration_recipients,
)

logger = logging.getLogger(__name__)

def build_team_detail_context(request, team, participant_form=None):
    from tournament.forms import ParticipantForm
    submissions = team.submissions.select_related('task', 'task__tournament').all()
    roster_locked = is_team_roster_locked(team) and not request.user.is_superuser
    quick_overview = build_team_quick_overview(team)

    participants = list(team.participants.all())
    if participants:
        participant_emails = [p.email.lower() for p in participants]
        users_by_email = {}
        for u in CustomUser.objects.filter(email__in=participant_emails):
            users_by_email[u.email.lower()] = u
        for participant in participants:
            participant.linked_user = users_by_email.get(participant.email.lower())

    tournament_history = team.registrations.filter(
        status=TournamentRegistration.Status.APPROVED
    ).select_related('tournament').order_by('-tournament__start_date')

    return {
        'team': team,
        'annotated_participants': participants,
        'invitations': team.invitations.all() if (request.user.is_superuser or team.captain_user_id == request.user.id) else [],
        'participants_count': team.members_count,
        'submissions': submissions,
        'quick_overview': quick_overview,
        'tournament_history': tournament_history,
        'participant_form': participant_form or ParticipantForm(),
        'can_manage_team': request.user.is_superuser or team.captain_user_id == request.user.id,
        'can_manage_roster': request.user.is_superuser or (
            team.captain_user_id == request.user.id and not roster_locked
        ),
        'can_edit_team': request.user.is_superuser or (
            team.captain_user_id == request.user.id and not roster_locked
        ),
        'can_leave_team': (
            not request.user.is_superuser
            and team.captain_user_id != request.user.id
            and team.participants.filter(email=request.user.email).exists()
            and not roster_locked
        ),
        'roster_locked': roster_locked,
    }

def serialize_leaderboard_rows(leaderboard, my_team=None):
    my_team_id = my_team.id if my_team is not None else None
    return [
        {
            'place': row['place'],
            'team_id': row['team'].id,
            'team_name': row['team'].name,
            'captain_name': row['team'].captain_name,
            'captain_user_id': row['team'].captain_user_id,
            'overall_average': row['overall_average'],
            'best_score': row['best_score'],
            'scored_tasks': row['scored_tasks'],
            'submitted_tasks': row['submitted_tasks'],
            'is_my_team': my_team_id == row['team'].id,
        }
        for row in leaderboard
    ]

def get_certificate_template_for(tournament, certificate_type):
    tournament_template = CertificateTemplate.objects.filter(
        tournament=tournament,
        certificate_type=certificate_type,
    ).order_by('-created_at').first()
    if tournament_template is not None:
        return tournament_template
    return CertificateTemplate.objects.filter(
        tournament__isnull=True,
        certificate_type=certificate_type,
    ).order_by('-created_at').first()

def load_certificate_font(size):
    font_candidates = [
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf'),
        r'C:\Windows\Fonts\arial.ttf',
        r'C:\Windows\Fonts\calibri.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
    ]
    for font_path in font_candidates:
        if font_path and os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()

def build_certificate_pdf_response(certificate):
    template = get_certificate_template_for(
        tournament=certificate.tournament,
        certificate_type=certificate.certificate_type,
    )
    if template is None:
        raise ValidationError('Для цього типу сертифіката ще не завантажено шаблон.')

    if not template.background_image:
        raise ValidationError('Для цього шаблону сертифіката не завантажено макет (зображення).')

    try:
        source_image = Image.open(template.background_image)
    except Exception:
        raise ValidationError('Файл шаблону сертифіката не знайдено або пошкоджено. Завантажте шаблон ще раз.')

    with source_image:
        image = source_image.convert('RGB')

    width, height = image.size
    draw = ImageDraw.Draw(image)
    title_font = load_certificate_font(max(28, width // 24))
    name_font = load_certificate_font(max(34, width // 18))
    meta_font = load_certificate_font(max(18, width // 42))
    fill = '#1f2937'
    center_x = width / 2

    title = (
        'Сертифікат переможця'
        if certificate.certificate_type == Certificate.CertificateType.WINNER
        else 'Сертифікат учасника'
    )
    subtitle = certificate.tournament.name
    footer_parts = []
    if certificate.team_id:
        footer_parts.append(f'Команда: {certificate.team.name}')
    footer_parts.append(f'Дата: {timezone.localtime(certificate.issued_at).strftime("%d.%m.%Y")}')
    footer = ' | '.join(footer_parts)

    for text, font, y in [
        (title, title_font, int(height * 0.23)),
        (certificate.recipient_name, name_font, int(height * 0.43)),
        (subtitle, meta_font, int(height * 0.60)),
        (footer, meta_font, int(height * 0.72)),
    ]:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        draw.text(((center_x - text_width / 2), y), text, font=font, fill=fill)

    buffer = io.BytesIO()
    image.save(buffer, 'PDF', resolution=100.0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="certificate-{certificate.id}.pdf"'
    return response

def build_tournament_leaderboard(tournament):
    approved_registrations = TournamentRegistration.objects.filter(
        tournament=tournament,
        status=TournamentRegistration.Status.APPROVED,
    ).select_related('team', 'team__captain_user')
    submission_qs = Submission.objects.filter(
        task__tournament=tournament,
    ).select_related('team', 'task').prefetch_related(
        'jury_assignments__evaluation',
    )

    submissions_by_team_id = {}
    for submission in submission_qs:
        submissions_by_team_id.setdefault(submission.team_id, []).append(submission)

    leaderboard = []
    for registration in approved_registrations:
        team = registration.team
        submissions = submissions_by_team_id.get(team.id, [])
        submission_averages = []
        evaluations_count = 0

        for submission in submissions:
            scores = []
            for assignment in submission.jury_assignments.all():
                evaluation = getattr(assignment, 'evaluation', None)
                if evaluation is None:
                    continue
                scores.append(evaluation.total_score)
            if scores:
                submission_averages.append(mean(scores))
                evaluations_count += len(scores)

        overall_average = mean(submission_averages) if submission_averages else None
        best_score = max(submission_averages) if submission_averages else None

        leaderboard.append({
            'team': team,
            'overall_average': overall_average,
            'best_score': best_score,
            'scored_tasks': len(submission_averages),
            'submitted_tasks': len(submissions),
            'evaluations_count': evaluations_count,
        })

    leaderboard.sort(
        key=lambda row: (
            row['overall_average'] is None,
            -(row['overall_average'] or 0),
            -(row['best_score'] or 0),
            -row['scored_tasks'],
            -row['submitted_tasks'],
            row['team'].name.lower(),
        )
    )

    previous_signature = None
    place = 0
    for index, row in enumerate(leaderboard, start=1):
        signature = (
            row['overall_average'],
            row['best_score'],
            row['scored_tasks'],
            row['submitted_tasks'],
        )
        if signature != previous_signature:
            place = index
            previous_signature = signature
        row['place'] = place

    return leaderboard

def finalize_tournament_evaluation_if_ready(tournament, *, finished_by=None):
    if (
        tournament.is_finished
        and tournament.all_submissions_evaluated
        and tournament.evaluation_finished_at is None
    ):
        tournament.evaluation_finished_at = timezone.now()
        if finished_by is not None:
            tournament.evaluation_finished_by = finished_by
            tournament.save(update_fields=['evaluation_finished_at', 'evaluation_finished_by'])
        else:
            tournament.save(update_fields=['evaluation_finished_at'])
        return True
    return False

def is_tournament_edit_locked(tournament):
    return (
        not tournament.is_draft
        and tournament.registration_end is not None
        and tournament.registration_end <= timezone.now()
    )

def is_team_roster_locked(team):
    return team.registrations.filter(
        status__in=[
            TournamentRegistration.Status.PENDING,
            TournamentRegistration.Status.APPROVED,
        ],
        tournament__registration_end__isnull=False,
        tournament__registration_end__lte=timezone.now(),
    ).exists()

def user_has_registration_access(user, registration):
    return (
        registration.team.captain_user_id == user.id
        or registration.members.filter(user=user).exists()
    )

def build_admin_nav_items():
    return [
        {'url': reverse('admin_users'), 'label': 'Користувачі'},
        {'url': reverse('admin_users') + '?action=create-user', 'label': 'Створити користувача'},
        {'url': reverse('admin_active_tournaments'), 'label': 'Активні турніри'},
        {'url': reverse('admin_inactive_tournaments'), 'label': 'Неактивні турніри'},
        {'url': reverse('create_tournament'), 'label': 'Створити турнір'},
        {'url': reverse('admin_teams'), 'label': 'Команди'},
        {'url': reverse('admin_registrations'), 'label': 'Заявки'},
        {'url': reverse('admin_submissions'), 'label': 'Роботи'},
    ]

def render_admin_section(request, section, action=None, admin_create_user_form=None, tournament_form=None):
    if not is_admin_user(request.user):
        return redirect('redirect_by_role')
    if action is None:
        action = request.GET.get('action')
    context = build_admin_dashboard_data()
    context.update({
        'current_section': section,
        'admin_nav_items': build_admin_nav_items(),
        'current_action': action,
        'admin_create_user_form': admin_create_user_form or AdminCreateUserForm(
            available_roles=get_available_admin_roles(request.user),
        ),
        'role_choices': list(CustomUser.ROLE_CHOICES),
        'can_manage_admin_roles': request.user.is_superuser,
        'now': timezone.now(),
        'tournament_form': tournament_form or TournamentForm(),
    })
    return render(request, 'admin_section.html', context)

def issue_certificates_for_tournament(*, tournament, issued_by, certificate_type, registrations):
    created_count = 0
    for registration in registrations:
        for recipient in collect_registration_recipients(registration):
            _, created = Certificate.objects.get_or_create(
                tournament=tournament,
                certificate_type=certificate_type,
                recipient_email=recipient['email'],
                defaults={
                    'team': registration.team,
                    'recipient_user': recipient['user'],
                    'recipient_name': recipient['name'],
                    'issued_by': issued_by,
                },
            )
            if created:
                created_count += 1
    return created_count

def build_archive_rows_for_user(user):
    finished_tournaments = Tournament.objects.filter(
        is_draft=False,
        end_date__isnull=False,
        end_date__lt=timezone.now(),
    ).prefetch_related(
        'tasks',
        'registrations__team',
        'registrations__members',
    ).order_by('-end_date', 'name')

    rows = []
    for tournament in finished_tournaments:
        leaderboard = build_tournament_leaderboard(tournament) if tournament.evaluation_results_ready else []
        my_registration = None
        if getattr(user, 'is_authenticated', False):
            approved_registrations = TournamentRegistration.objects.filter(
                tournament=tournament,
                status=TournamentRegistration.Status.APPROVED,
            ).select_related('team').prefetch_related('members')
            my_registration = next(
                (registration for registration in approved_registrations if user_has_registration_access(user, registration)),
                None,
            )

        rows.append({
            'tournament': tournament,
            'leaderboard_preview': leaderboard[:5],
            'teams_count': len(leaderboard),
            'tasks_count': tournament.tasks.filter(is_draft=False).count(),
            'my_team': my_registration.team if my_registration is not None else None,
        })
    return rows
