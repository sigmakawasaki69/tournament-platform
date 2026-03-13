from django import forms
from .models import Tournament


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