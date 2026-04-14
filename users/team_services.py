import logging
import secrets

from django.db import IntegrityError, transaction

from tournament.models import Participant, Team, TeamInvitation

from .models import CustomUser
from .platform_services import email_delivery_ready, send_team_invitation_email


logger = logging.getLogger(__name__)


class TeamParticipantActionResult:
    def __init__(self, *, added=False, invited=False, field=None, message=""):
        self.added = added
        self.invited = invited
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
        participant_email = form.cleaned_data["email"].strip().lower()

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
        if team.invitations.filter(email__iexact=participant_email).exists():
            return TeamParticipantActionResult(
                field="email",
                message="Запрошення цьому учаснику вже надіслано.",
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

        if not email_delivery_ready():
            return TeamParticipantActionResult(
                field="email",
                message="Наразі неможливо надіслати запрошення, бо поштова служба не налаштована.",
            )

        try:
            with transaction.atomic():
                invitation = TeamInvitation.objects.create(
                    team=team,
                    full_name=participant_name,
                    email=participant_email,
                    token=secrets.token_urlsafe(32),
                )
                send_team_invitation_email(request, invitation=invitation)

            return TeamParticipantActionResult(
                invited=True,
                message=(
                    f"Запрошення надіслано на {participant_email}. "
                    "Учасник буде доданий до команди після підтвердження через пошту."
                ),
            )
        except IntegrityError:
            return TeamParticipantActionResult(
                field="email",
                message="Запрошення цьому учаснику вже надіслано.",
            )
        except Exception:
            logger.exception("Failed to handle participant team invitation flow")
            return TeamParticipantActionResult(
                field="email",
                message="Не вдалося надіслати лист-запрошення, спробуйте пізніше.",
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
