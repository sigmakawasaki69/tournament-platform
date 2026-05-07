from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from tournament.models import School, Tournament
from ..policies import is_admin_user, is_organizer_user
from ..selectors import (
    build_notification_nav_context,
    build_public_tournament_rows,
    build_public_announcements,
    get_primary_team_with_quick_overview,
    build_user_message_items,
    build_user_certificates_queryset,
)
from .utils import build_tournament_leaderboard, build_archive_rows_for_user

def home(request):
    tournament_rows = build_public_tournament_rows(leaderboard_builder=build_tournament_leaderboard)
    announcements = build_public_announcements()
    notification_context = build_notification_nav_context(request.user)
    primary_team_id = request.session.get('primary_team_id')
    home_team, home_team_quick_overview, my_teams = get_primary_team_with_quick_overview(request.user, primary_team_id=primary_team_id)
    filter_status = request.GET.get('status', 'all')
    filter_options = {'all', 'registration', 'running', 'finished', 'scheduled'}
    if filter_status not in filter_options:
        filter_status = 'all'

    for row in tournament_rows:
        tournament = row['tournament']
        if tournament.is_registration_open:
            row['filter_bucket'] = 'registration'
        elif tournament.is_running:
            row['filter_bucket'] = 'running'
        elif tournament.is_finished:
            row['filter_bucket'] = 'finished'
        else:
            row['filter_bucket'] = 'scheduled'

    featured_tournaments = [row for row in tournament_rows if row['tournament'].is_registration_open]
    active_tournaments = [row for row in tournament_rows if row['tournament'].is_running]
    finished_tournaments = [row for row in tournament_rows if row['tournament'].is_finished]
    upcoming_tournaments = [
        row for row in tournament_rows
        if (
            not row['tournament'].is_registration_open
            and not row['tournament'].is_running
            and not row['tournament'].is_finished
        )
    ]

    if filter_status == 'registration':
        filtered_tournament_rows = featured_tournaments
    elif filter_status == 'running':
        filtered_tournament_rows = active_tournaments
    elif filter_status == 'finished':
        filtered_tournament_rows = finished_tournaments
    elif filter_status == 'scheduled':
        filtered_tournament_rows = upcoming_tournaments
    else:
        filtered_tournament_rows = tournament_rows

    news_rows = []
    for row in tournament_rows[:4]:
        tournament = row['tournament']
        if tournament.is_registration_open:
            text_key = 'news.status.registration_open'
            text_default = 'Відкрита реєстрація. Можна подавати заявки.'
        elif tournament.is_running:
            text_key = 'news.status.running'
            text_default = 'Турнір уже триває.'
        elif tournament.is_finished and tournament.evaluation_results_ready:
            text_key = 'news.status.finished_evaluated'
            text_default = 'Турнір завершено, оцінювання закрито. Підсумковий лідерборд уже доступний.'
        elif tournament.is_finished:
            text_key = 'news.status.finished_evaluating'
            text_default = 'Турнір завершено. Оцінювання ще триває.'
        else:
            text_key = 'news.status.scheduled'
            text_default = 'Турнір заплановано. Слідкуйте за датами старту.'
        news_rows.append({'tournament': tournament, 'text': text_default, 'text_key': text_key})

    return render(request, 'home.html', {
        'tournament_rows': tournament_rows,
        'filtered_tournament_rows': filtered_tournament_rows,
        'filter_status': filter_status,
        'filter_choices': [
            {'value': 'all', 'label': 'Усі'},
            {'value': 'registration', 'label': 'Реєстрація'},
            {'value': 'running', 'label': 'Тривають'},
            {'value': 'finished', 'label': 'Завершені'},
            {'value': 'scheduled', 'label': 'Майбутні'},
        ],
        'featured_tournaments': featured_tournaments[:3],
        'active_tournaments': active_tournaments[:3],
        'finished_tournaments': finished_tournaments[:3],
        'upcoming_tournaments': upcoming_tournaments[:3],
        'news_rows': news_rows,
        'announcements': announcements,
        'home_team': home_team,
        'home_team_quick_overview': home_team_quick_overview,
        'my_teams': my_teams,
        **notification_context,
    })

def archive_view(request):
    archive_rows = build_archive_rows_for_user(request.user)
    context = {
        'archive_rows': archive_rows,
    }
    context.update(build_notification_nav_context(request.user))
    return render(request, 'archive.html', context)

def redirect_by_role(request):
    user = request.user
    if is_admin_user(user) or is_organizer_user(user):
        return redirect('home')
    if user.role == 'jury':
        return redirect('jury_dashboard')
    return redirect('home')

@login_required
def messages_view(request):
    message_items = build_user_message_items(request.user)
    filter_category = request.GET.get('category', 'all')
    filter_choices = [
        {'value': 'all', 'label': 'Усі'},
        {'value': 'personal', 'label': 'Особисті'},
        {'value': 'general', 'label': 'Загальні'},
        {'value': 'tournament', 'label': 'Турнірні'},
    ]
    valid_filter_values = {choice['value'] for choice in filter_choices}
    if filter_category not in valid_filter_values:
        filter_category = 'all'
    now = timezone.now()
    request.user.announcements_seen_at = now
    request.user.save(update_fields=['announcements_seen_at'])
    return render(request, 'messages.html', {
        'message_items': message_items,
        'filter_category': filter_category,
        'filter_choices': filter_choices,
        **build_notification_nav_context(request.user),
    })

@login_required
def certificates_view(request):
    certificates = build_user_certificates_queryset(request.user)
    now = timezone.now()
    request.user.certificates_seen_at = now
    request.user.save(update_fields=['certificates_seen_at'])
    return render(request, 'certificates.html', {
        'certificates': certificates,
        **build_notification_nav_context(request.user),
    })

def school_autocomplete(request):
    query = request.GET.get('q', '').strip().lower()
    if len(query) < 2:
        return JsonResponse([], safe=False)
    
    abbreviations = {
        'хл': 'харківський ліцей',
        'хг': 'харківська гімназія',
        'зош': 'школа',
        'нвк': 'нвк',
        'ззсо': 'ззсо',
        'гімн': 'гімназія',
        'ліц': 'ліцей',
    }
    
    words = query.split()
    search_variants = [words]
    
    if any(w in abbreviations for w in words):
        expanded = []
        for w in words:
            if w in abbreviations:
                expanded.extend(abbreviations[w].split())
            else:
                expanded.append(w)
        search_variants.append(expanded)

    def search_in_db(word_list, mode='AND'):
        if not word_list:
            return []
        
        q_objs = Q()
        if mode == 'AND':
            first = True
            for w in word_list:
                if len(w) < 2: continue
                condition = Q(name__icontains=w) | Q(short_name__icontains=w)
                if first:
                    q_objs = condition
                    first = False
                else:
                    q_objs &= condition
        else: # OR mode
            for w in word_list:
                if len(w) < 3: continue
                q_objs |= (Q(name__icontains=w) | Q(short_name__icontains=w))
        
        if not q_objs:
            return []
            
        return list(School.objects.filter(q_objs).distinct().order_by('name')[:15])

    results = []
    for variant in search_variants:
        results = search_in_db(variant, mode='AND')
        if results:
            break
            
    if not results and len(query) > 4:
        typo_variant = [w[1:] if len(w) > 4 else w for w in words]
        results = search_in_db(typo_variant, mode='AND')

    if not results and len(words) > 1:
        results = search_in_db(words, mode='OR')

    formatted_results = [str(school) for school in results]
    return JsonResponse(formatted_results, safe=False)

def contact_autocomplete(request):
    return JsonResponse([], safe=False)

@login_required
def set_primary_team(request):
    if request.method == 'POST':
        team_id = request.POST.get('team_id')
        if team_id:
            request.session['primary_team_id'] = team_id
            messages.success(request, 'Активну команду змінено.')
    return redirect(request.META.get('HTTP_REFERER', reverse('profile')))
