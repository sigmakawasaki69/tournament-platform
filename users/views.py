from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .forms import RegisterForm, LoginForm
from .models import CustomUser

from tournament.models import (
    Tournament,
    Team,
    Participant,
    Task,
    Submission,
    JuryAssignment,
    Evaluation,
)
from tournament.forms import TournamentForm


def home(request):
    if request.user.is_authenticated:
        return redirect('redirect_by_role')
    return redirect('login')


def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            if user.role == 'participant':
                user.is_approved = True
            else:
                user.is_approved = False

            user.save()
            return redirect('login')
    else:
        form = RegisterForm()

    return render(request, 'register.html', {
        'form': form,
    })


def login_view(request):
    message = ''

    if request.user.is_authenticated:
        return redirect('redirect_by_role')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            if not user.is_approved and not user.is_superuser:
                message = 'Ваш акаунт ще не схвалений адміністратором.'
            else:
                login(request, user)
                return redirect('redirect_by_role')
        else:
            message = 'Неправильний логін або пароль.'
    else:
        form = LoginForm()

    return render(request, 'login.html', {
        'form': form,
        'message': message
    })


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def redirect_by_role(request):
    user = request.user

    if user.is_superuser or user.role == 'admin':
        return redirect('admin_dashboard')
    elif user.role == 'jury':
        return redirect('jury_dashboard')
    else:
        return redirect('participant_dashboard')


@login_required
def admin_dashboard(request):
    if not (request.user.is_superuser or request.user.role == 'admin'):
        return redirect('redirect_by_role')

    pending_users = CustomUser.objects.filter(is_approved=False).exclude(role='participant')
    approved_users = CustomUser.objects.filter(is_approved=True)

    tournaments = Tournament.objects.all()
    teams = Team.objects.select_related('tournament').all()
    participants = Participant.objects.select_related('team').all()
    tasks = Task.objects.select_related('tournament').all()
    submissions = Submission.objects.select_related('team', 'task').all()
    jury_assignments = JuryAssignment.objects.select_related('jury_user', 'submission').all()
    evaluations = Evaluation.objects.select_related('assignment').all()

    context = {
        'pending_users': pending_users,
        'approved_users': approved_users,
        'tournaments': tournaments,
        'teams': teams,
        'participants': participants,
        'tasks': tasks,
        'submissions': submissions,
        'jury_assignments': jury_assignments,
        'evaluations': evaluations,
    }

    return render(request, 'admin_dashboard.html', context)


@login_required
def approve_user(request, user_id):
    if not (request.user.is_superuser or request.user.role == 'admin'):
        return redirect('redirect_by_role')

    user = get_object_or_404(CustomUser, id=user_id)

    if user.id == request.user.id and not request.user.is_superuser:
        return redirect('admin_dashboard')

    user.is_approved = True
    user.save()
    return redirect('admin_dashboard')


@login_required
def create_tournament(request):
    if not (request.user.is_superuser or request.user.role == 'admin'):
        return redirect('redirect_by_role')

    if request.method == 'POST':
        form = TournamentForm(request.POST)
        if form.is_valid():
            tournament = form.save(commit=False)
            tournament.created_by = request.user
            tournament.save()
            return redirect('admin_dashboard')
    else:
        form = TournamentForm()

    return render(request, 'create_tournament.html', {'form': form})


@login_required
def jury_dashboard(request):
    if request.user.role != 'jury' and not request.user.is_superuser:
        return redirect('redirect_by_role')

    return render(request, 'jury_dashboard.html')


@login_required
def participant_dashboard(request):
    if request.user.role != 'participant' and not request.user.is_superuser:
        return redirect('redirect_by_role')

    return render(request, 'participant_dashboard.html')