from django import forms
from .models import Tournament, Team, Participant, TournamentRegistration, Task


class TournamentForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        label='Дата початку'
    )
    registration_start = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        label='Початок реєстрації'
    )
    registration_end = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        label='Завершення реєстрації'
    )

    class Meta:
        model = Tournament
        fields = [
            'name',
            'description',
            'start_date',
            'registration_start',
            'registration_end',
            'max_teams',
            'status',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 5}),
            'max_teams': forms.NumberInput(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        registration_start = cleaned_data.get('registration_start')
        registration_end = cleaned_data.get('registration_end')
        start_date = cleaned_data.get('start_date')

        if registration_start and registration_end and registration_start >= registration_end:
            self.add_error('registration_end', 'Завершення реєстрації має бути пізніше за початок реєстрації.')

        if registration_end and start_date and registration_end > start_date:
            self.add_error('registration_end', 'Реєстрація має завершуватися до початку турніру.')

        return cleaned_data


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'captain_name', 'captain_email', 'school', 'telegram']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'captain_name': forms.TextInput(attrs={'class': 'form-input'}),
            'captain_email': forms.EmailInput(attrs={'class': 'form-input'}),
            'school': forms.TextInput(attrs={'class': 'form-input'}),
            'telegram': forms.TextInput(attrs={'class': 'form-input'}),
        }


class ParticipantForm(forms.ModelForm):

    class Meta:
        model = Participant
        fields = ['full_name', 'email']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
        }

class TournamentRegistrationForm(forms.ModelForm):
    class Meta:
        model = TournamentRegistration
        fields = ['team']
        widgets = {
            'team': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        tournament = kwargs.pop('tournament', None)
        super().__init__(*args, **kwargs)

        queryset = Team.objects.none()

        if user is not None:
            queryset = Team.objects.filter(
                captain_user=user
            ).order_by('name')

        if tournament is not None:
            used_team_ids = TournamentRegistration.objects.filter(
                tournament=tournament
            ).values_list('team_id', flat=True)
            queryset = queryset.exclude(id__in=used_team_ids)

        self.fields['team'].queryset = queryset


class TaskForm(forms.ModelForm):
    start_time = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        label='Час початку',
    )
    deadline = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        label='Дедлайн',
    )

    class Meta:
        model = Task
        fields = [
            'tournament',
            'title',
            'description',
            'requirements',
            'must_have',
            'start_time',
            'deadline',
            'status',
        ]
        widgets = {
            'tournament': forms.Select(attrs={'class': 'form-input'}),
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'requirements': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'must_have': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-input'}),
        }