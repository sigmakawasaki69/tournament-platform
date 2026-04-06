import logging

from django.db import IntegrityError, transaction

from tournament.models import Participant, Team

from .models import CustomUser
from .platform_services import email_delivery_ready, send_team_invitation_email


logger = logging.getLogger(__name__)


class TeamParticipantActionResult:
    def __init__(self, *, added=False, field=None, message=""):
        self.added = added
        self.field = field
        self.message = message


class TeamManagementService:
    @staticmethod
    @transaction.atomic
    def create_team_for_user(*, user, form):
        team = form.save(commit=False)
        team.captain_user = user
        if not team.captain_name:
            team.captain_name = user.username
        if not team.captain_email:
            team.captain_email = user.email
        team.save()
        return team

    @staticmethod
    @transaction.atomic
    def update_team(*, form):
        return form.save()

    @staticmethod
    def add_participant_to_team(*, request, team, form):
        participant_name = form.cleaned_data["full_name"]
        participant_email = form.cleaned_data["email"]

        if participant_email == (team.captain_email or "").lower():
            return TeamParticipantActionResult(
                field="email",
                message="Цей учасник уже є в команді.",
            )
        if team.participants.filter(email__iexact=participant_email).exists():
            return TeamParticipantActionResult(
                field="email",
                message="Цей учасник уже є в команді.",
            )
        if Team.objects.filter(captain_email__iexact=participant_email).exclude(id=team.id).exists():
            return TeamParticipantActionResult(
                field="email",
                message="Цей учасник уже зареєстрований в іншій команді.",
            )
        if Participant.objects.filter(email__iexact=participant_email).exclude(team=team).exists():
            return TeamParticipantActionResult(
                field="email",
                message="Цей учасник уже зареєстрований в іншій команді.",
            )

        try:
            linked_user = CustomUser.objects.filter(email__iexact=participant_email).first()
            if linked_user is None:
                if not email_delivery_ready():
                    return TeamParticipantActionResult(
                        field="email",
                        message=(
                            "Такого учасника не зареєстровано на платформі. "
                            "Запрошення не вдалося надіслати, бо email не налаштовано."
                        ),
                    )

                send_team_invitation_email(
                    request,
                    team=team,
                    recipient_name=participant_name,
                    recipient_email=participant_email,
                )
                return TeamParticipantActionResult(
                    field="email",
                    message=(
                        "Такого учасника не зареєстровано на платформі. "
                        "Ми надіслали йому лист із запрошенням зареєструватися."
                    ),
                )

            participant = form.save(commit=False)
            participant.team = team
            participant.save()
            return TeamParticipantActionResult(added=True)
        except IntegrityError:
            return TeamParticipantActionResult(
                field="email",
                message="Цей учасник уже є в команді.",
            )
        except Exception:
            logger.exception("Failed to handle participant team invitation flow")
            return TeamParticipantActionResult(
                field="email",
                message=(
                    "Такого учасника не зареєстровано на платформі. "
                    "Не вдалося надіслати лист-запрошення, спробуйте пізніше."
                ),
            )

    @staticmethod
    @transaction.atomic
    def delete_participant(*, participant):
        participant.delete()

    @staticmethod
    @transaction.atomic
    def delete_team(*, team):
        team.delete()

    @staticmethod
    @transaction.atomic
    def leave_team(*, team, user):
        participant = Participant.objects.get(team=team, email=user.email)
        participant.delete()
