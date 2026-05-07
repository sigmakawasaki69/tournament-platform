from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from tournament.models import JuryAssignment, Submission, Tournament
from tournament.forms import EvaluationForm
from ..selectors import build_notification_nav_context
from .utils import finalize_tournament_evaluation_if_ready

@login_required
def jury_dashboard(request):
    if request.user.role != 'jury' and not request.user.is_superuser:
        return redirect('redirect_by_role')

    tournaments = Tournament.objects.filter(is_draft=False).prefetch_related(
        'tasks__submissions__team',
    ).order_by('-start_date')
    if not request.user.is_superuser:
        tournaments = tournaments.filter(jury_users=request.user)

    tournament_rows = []
    for tournament in tournaments:
        submissions = Submission.objects.filter(task__tournament=tournament).select_related('team', 'task')
        tournament_rows.append({
            'tournament': tournament,
            'teams_count': submissions.values('team_id').distinct().count(),
            'submissions_count': submissions.count(),
        })

    return render(request, 'jury_dashboard.html', {
        'tournament_rows': tournament_rows,
        **build_notification_nav_context(request.user),
    })

@login_required
def jury_tournament_detail(request, tournament_id):
    if request.user.role != 'jury' and not request.user.is_superuser:
        return redirect('redirect_by_role')

    tournament = get_object_or_404(Tournament, id=tournament_id, is_draft=False)
    if not request.user.is_superuser and not tournament.jury_users.filter(id=request.user.id).exists():
        return redirect('jury_dashboard')
        
    submissions = Submission.objects.filter(
        task__tournament=tournament,
    ).select_related('team', 'task').prefetch_related(
        'jury_assignments__jury_user',
        'jury_assignments__evaluation',
    ).order_by('team__name', 'task__title')

    pending_team_map = {}
    evaluated_team_map = {}
    for submission in submissions:
        assignment = JuryAssignment.objects.filter(jury_user=request.user, submission=submission).first()
        evaluation = getattr(assignment, 'evaluation', None) if assignment else None
        target_map = evaluated_team_map if evaluation else pending_team_map
        team_bucket = target_map.setdefault(submission.team_id, {'team': submission.team, 'submissions': []})
        team_bucket['submissions'].append({
            'submission': submission,
            'my_evaluation': evaluation,
            'evaluation_form': EvaluationForm(instance=evaluation, prefix=f'eval-{submission.id}'),
        })

    return render(request, 'jury_tournament_detail.html', {
        'tournament': tournament,
        'pending_team_rows': list(pending_team_map.values()),
        'evaluated_team_rows': list(evaluated_team_map.values()),
        **build_notification_nav_context(request.user),
    })

@login_required
def submit_evaluation(request, submission_id):
    if request.user.role != 'jury' and not request.user.is_superuser:
        return redirect('redirect_by_role')
    if request.method != 'POST':
        return redirect('jury_dashboard')

    submission = get_object_or_404(Submission.objects.select_related('task', 'task__tournament'), id=submission_id)
    if not request.user.is_superuser and not submission.task.tournament.jury_users.filter(id=request.user.id).exists():
        return redirect('jury_dashboard')
        
    assignment, _ = JuryAssignment.objects.get_or_create(jury_user=request.user, submission=submission)
    evaluation = getattr(assignment, 'evaluation', None)
    form = EvaluationForm(request.POST, instance=evaluation, prefix=f'eval-{submission.id}')
    if form.is_valid():
        saved_evaluation = form.save(commit=False)
        saved_evaluation.assignment = assignment
        saved_evaluation.save()
        finalize_tournament_evaluation_if_ready(submission.task.tournament, finished_by=request.user)

    return redirect('jury_tournament_detail', tournament_id=submission.task.tournament_id)
