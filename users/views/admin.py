import logging
import csv
import os
import mimetypes
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotAllowed, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from tournament.models import (
    Announcement,
    Certificate,
    CertificateTemplate,
    Tournament,
    TournamentRegistration,
)
from tournament.forms import (
    AnnouncementForm,
    CertificateTemplateForm,
)
from ..models import CustomUser
from ..forms import AdminCreateUserForm
from tournament.forms import TournamentForm
from ..policies import (
    is_admin_user,
    is_organizer_user,
    can_manage_users,
    can_review_registrations,
    can_manage_registration_instance,
    can_export_tournament_results,
    get_available_admin_roles,
    get_dashboard_url_for_user,
    get_post_redirect,
)
from ..selectors import (
    build_notification_nav_context,
    collect_registration_recipients,
)
from .utils import (
    render_admin_section,
    build_tournament_leaderboard,
    issue_certificates_for_tournament,
    build_certificate_pdf_response,
)

logger = logging.getLogger(__name__)

@login_required
def admin_dashboard(request):
    return redirect('admin_users')

@login_required
def admin_users(request):
    return render_admin_section(request, 'users')

@login_required
def admin_all_tournaments(request):
    return render_admin_section(request, 'all_tournaments')

@login_required
def admin_active_tournaments(request):
    return render_admin_section(request, 'active_tournaments')

@login_required
def admin_inactive_tournaments(request):
    return render_admin_section(request, 'inactive_tournaments')

@login_required
def admin_teams(request):
    return render_admin_section(request, 'teams')

@login_required
def admin_registrations(request):
    return render_admin_section(request, 'registrations')

@login_required
def admin_submissions(request):
    return render_admin_section(request, 'submissions')

@login_required
def admin_announcements(request):
    if not is_admin_user(request.user):
        return redirect('redirect_by_role')

    tournament_queryset = Tournament.objects.order_by('-start_date', 'name')
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, tournament_queryset=tournament_queryset)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.created_by = request.user
            
            if form.cleaned_data.get('send_internal', True):
                announcement.save()
            
            if form.cleaned_data.get('send_email', False):
                from django.contrib.auth import get_user_model
                from ..platform_services import send_platform_email
                import threading
                User = get_user_model()
                
                if announcement.tournament:
                    emails = set()
                    regs = TournamentRegistration.objects.filter(tournament=announcement.tournament).select_related('team__captain_user')
                    for reg in regs:
                        if reg.team and reg.team.captain_user and reg.team.captain_user.email:
                            emails.add(reg.team.captain_user.email)
                    for jury in announcement.tournament.jury_users.all():
                        if jury.email:
                            emails.add(jury.email)
                else:
                    emails = set(User.objects.exclude(email='').values_list('email', flat=True))
                
                def send_bulk_emails(email_set, subj, msg):
                    for e in email_set:
                        try:
                            send_platform_email(e, subj, msg)
                        except Exception:
                            pass
                            
                threading.Thread(target=send_bulk_emails, args=(emails, announcement.title, announcement.message)).start()

            return redirect('admin_announcements')
    else:
        form = AnnouncementForm(tournament_queryset=tournament_queryset)

    announcements = Announcement.objects.select_related('created_by', 'tournament').all()
    return render(request, 'admin_announcements.html', {
        'form': form,
        'announcements': announcements,
    })

@login_required
def delete_announcement(request, announcement_id):
    if not is_admin_user(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    announcement = get_object_or_404(Announcement, id=announcement_id)
    announcement.delete()
    return redirect('admin_announcements')

@login_required
def admin_certificates(request):
    if not is_admin_user(request.user):
        return redirect('redirect_by_role')

    tournament_queryset = Tournament.objects.order_by('-start_date', 'name')
    if request.method == 'POST':
        template_form = CertificateTemplateForm(
            request.POST,
            request.FILES,
            tournament_queryset=tournament_queryset,
        )
        if template_form.is_valid():
            try:
                template = template_form.save(commit=False)
                template.uploaded_by = request.user
                template.save()
            except Exception:
                logger.exception("Failed to upload certificate template", extra={"user_id": request.user.id})
                messages.error(
                    request,
                    'Не вдалося завантажити шаблон сертифіката. Перевірте формат файлу та спробуйте ще раз.',
                )
            else:
                messages.success(request, 'Шаблон сертифіката успішно завантажено.')
                return redirect('admin_certificates')
    else:
        template_form = CertificateTemplateForm(tournament_queryset=tournament_queryset)

    finished_tournaments = Tournament.objects.filter(
        is_draft=False,
        end_date__isnull=False,
        end_date__lt=timezone.now(),
    ).prefetch_related(
        'registrations__team',
        'registrations__members',
        'registrations__team__participants',
    ).order_by('-end_date', 'name')
    certificates = Certificate.objects.select_related(
        'tournament',
        'team',
        'issued_by',
        'recipient_user',
    ).all()
    certificate_templates = CertificateTemplate.objects.select_related(
        'tournament',
        'uploaded_by',
    ).all()
    return render(request, 'admin_certificates.html', {
        'finished_tournaments': finished_tournaments,
        'certificates': certificates,
        'certificate_templates': certificate_templates,
        'template_form': template_form,
    })

@login_required
def create_user_by_admin(request):
    if not is_admin_user(request.user):
        return redirect('redirect_by_role')
    if request.method == 'GET':
        return redirect(reverse('admin_users') + '?action=create-user')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['GET', 'POST'])

    form = AdminCreateUserForm(request.POST, available_roles=get_available_admin_roles(request.user))
    if form.is_valid():
        user = form.save(commit=False)
        user.is_approved = user.role == 'participant'
        user.save()
        fallback = reverse('admin_users') if is_admin_user(request.user) else get_dashboard_url_for_user(request.user)
        return redirect(get_post_redirect(request, fallback))
    return render_admin_section(
        request,
        'users',
        action='create-user',
        admin_create_user_form=form,
    )

@login_required
def approve_user(request, user_id):
    if not can_manage_users(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    user = get_object_or_404(CustomUser, id=user_id)
    if user.id == request.user.id:
        return redirect(reverse('admin_users'))

    user.is_approved = True
    user.save(update_fields=['is_approved'])
    return redirect(get_post_redirect(request, reverse('admin_users')))

@login_required
def update_user_role(request, user_id):
    if not can_manage_users(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect(reverse('admin_users'))

    user = get_object_or_404(CustomUser, id=user_id)
    new_role = request.POST.get('role')
    if user.id == request.user.id:
        return redirect(reverse('admin_users'))
    allowed_roles = get_available_admin_roles(request.user)
    if new_role not in allowed_roles:
        return redirect(reverse('admin_users'))

    if (user.role == 'admin' or user.is_superuser) and not request.user.is_superuser:
        messages.error(request, "Тільки суперкористувач може змінювати роль адміністраторів.")
        return redirect(reverse('admin_users'))

    user.role = new_role
    if new_role == 'participant':
        user.is_approved = True
    user.save(update_fields=['role', 'is_approved'])
    return redirect(get_post_redirect(request, reverse('admin_users')))

@login_required
def delete_user(request, user_id):
    if not can_manage_users(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect(reverse('admin_users'))

    user = get_object_or_404(CustomUser, id=user_id)
    if user.id == request.user.id:
        return redirect(reverse('admin_users'))

    if (user.role == 'admin' or user.is_superuser) and not request.user.is_superuser:
        messages.error(request, "Тільки суперкористувач може видаляти адміністраторів.")
        return redirect(reverse('admin_users'))

    user.delete()
    return redirect(get_post_redirect(request, reverse('admin_users')))

@login_required
def approve_registration(request, registration_id):
    if not can_review_registrations(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    registration = get_object_or_404(TournamentRegistration, id=registration_id)
    if not can_manage_registration_instance(request.user, registration):
        return redirect('redirect_by_role')
    registration.status = TournamentRegistration.Status.APPROVED
    registration.save(update_fields=['status'])
    
    try:
        from ..platform_services import send_registration_status_email
        send_registration_status_email(request, registration=registration)
    except Exception:
        logger.exception("Failed to send approval email")

    fallback = reverse('admin_registrations') if is_admin_user(request.user) else get_dashboard_url_for_user(request.user)
    return redirect(get_post_redirect(request, fallback))

@login_required
def reject_registration(request, registration_id):
    if not can_review_registrations(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    registration = get_object_or_404(TournamentRegistration, id=registration_id)
    if not can_manage_registration_instance(request.user, registration):
        return redirect('redirect_by_role')
    registration.status = TournamentRegistration.Status.REJECTED
    registration.save(update_fields=['status'])

    try:
        from ..platform_services import send_registration_status_email
        send_registration_status_email(request, registration=registration)
    except Exception:
        logger.exception("Failed to send rejection email")

    fallback = reverse('admin_registrations') if is_admin_user(request.user) else get_dashboard_url_for_user(request.user)
    return redirect(get_post_redirect(request, fallback))

@login_required
def issue_participant_certificates(request, tournament_id):
    if not is_admin_user(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect('admin_certificates')

    tournament = get_object_or_404(Tournament, id=tournament_id, is_draft=False)
    registrations = TournamentRegistration.objects.filter(
        tournament=tournament,
        status=TournamentRegistration.Status.APPROVED,
    ).select_related('team', 'team__captain_user').prefetch_related('members', 'team__participants')
    created_count = issue_certificates_for_tournament(
        tournament=tournament,
        issued_by=request.user,
        certificate_type=Certificate.CertificateType.PARTICIPANT,
        registrations=registrations,
    )
    if created_count:
        messages.success(request, f'Згенеровано сертифікати учасників: {created_count}.')
    else:
        messages.info(request, 'Усі сертифікати учасників для цього турніру вже створені.')
    return redirect(get_post_redirect(request, reverse('admin_certificates')))

@login_required
def issue_winner_certificates(request, tournament_id):
    if not is_admin_user(request.user):
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect('admin_certificates')

    tournament = get_object_or_404(Tournament, id=tournament_id, is_draft=False)
    leaderboard = build_tournament_leaderboard(tournament)
    if leaderboard:
        winner_team = leaderboard[0]['team']
        registrations = TournamentRegistration.objects.filter(
            tournament=tournament,
            team=winner_team,
            status=TournamentRegistration.Status.APPROVED,
        ).select_related('team', 'team__captain_user').prefetch_related('members', 'team__participants')
        created_count = issue_certificates_for_tournament(
            tournament=tournament,
            issued_by=request.user,
            certificate_type=Certificate.CertificateType.WINNER,
            registrations=registrations,
        )
        if created_count:
            messages.success(request, f'Згенеровано сертифікати переможців: {created_count}.')
        else:
            messages.info(request, 'Сертифікати переможців уже створені.')
    else:
        messages.warning(request, 'Немає результатів, за якими можна визначити переможця.')
    return redirect(get_post_redirect(request, reverse('admin_certificates')))

@login_required
def preview_certificate_template(request, template_id):
    if not is_admin_user(request.user):
        return redirect('redirect_by_role')

    template = get_object_or_404(
        CertificateTemplate.objects.select_related('tournament', 'uploaded_by'),
        id=template_id,
    )

    try:
        template.background_image.open("rb")
    except Exception:
        logger.exception("Failed to open certificate template preview", extra={"template_id": template.id})
        messages.error(request, 'Не вдалося відкрити макет сертифіката. Перевірте, чи файл шаблону ще доступний.')
        return redirect(reverse('admin_certificates'))

    filename = os.path.basename(template.background_image.name or "certificate-template")
    content_type, _ = mimetypes.guess_type(filename)
    response = FileResponse(
        template.background_image.file,
        content_type=content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response

@login_required
def download_certificate_pdf(request, certificate_id):
    certificate = get_object_or_404(
        Certificate.objects.select_related('tournament', 'team', 'recipient_user', 'issued_by'),
        id=certificate_id,
    )
    can_download = (
        is_admin_user(request.user)
        or certificate.tournament.created_by_id == request.user.id
        or certificate.issued_by_id == request.user.id
        or certificate.recipient_user_id == request.user.id
        or certificate.recipient_email.lower() == (request.user.email or '').lower()
    )
    if not can_download:
        return redirect('redirect_by_role')

    try:
        return build_certificate_pdf_response(certificate)
    except Exception:
        logger.exception("Failed to build certificate PDF", extra={"certificate_id": certificate.id})
        messages.error(request, 'Не вдалося згенерувати PDF сертифіката. Перевірте шаблон зображення і спробуйте ще раз.')
        fallback = reverse('admin_certificates') if is_admin_user(request.user) else reverse('profile')
        return redirect(fallback)

@login_required
def export_tournament_results_csv(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, is_draft=False)
    if not can_export_tournament_results(request.user, tournament) or not tournament.evaluation_results_ready:
        return redirect('redirect_by_role')

    leaderboard = build_tournament_leaderboard(tournament)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="tournament-results-{tournament.id}.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow([
        'Місце', 'Команда', 'Контактна особа', 'Середній бал', 'Кращий бал', 'Оцінених задач', 'Поданих робіт',
    ])
    for row in leaderboard:
        writer.writerow([
            row['place'],
            row['team'].name,
            row['team'].captain_name,
            '' if row['overall_average'] is None else f"{row['overall_average']:.1f}",
            '' if row['best_score'] is None else f"{row['best_score']:.1f}",
            row['scored_tasks'],
            row['submitted_tasks'],
        ])
    return response

@login_required
def organizer_dashboard(request):
    if not is_organizer_user(request.user):
        return redirect('redirect_by_role')

    tournaments = Tournament.objects.filter(created_by=request.user).prefetch_related('tasks', 'jury_users')
    registrations = TournamentRegistration.objects.filter(
        tournament__created_by=request.user,
    ).select_related('tournament', 'team', 'registered_by').prefetch_related('members')
    return render(request, 'organizer_dashboard.html', {
        'tournaments': tournaments.order_by('-start_date', 'name'),
        'registrations': registrations.order_by('-created_at'),
        **build_notification_nav_context(request.user),
    })
