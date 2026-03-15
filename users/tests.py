from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tournament.models import Evaluation, Participant, Submission, Task, Team, Tournament, TournamentRegistration


User = get_user_model()


class TournamentPlatformViewTests(TestCase):
    def setUp(self):
        self.captain = User.objects.create_user(
            username="captain",
            password="secret123",
            role="captain",
            is_approved=True,
            email="captain@example.com",
        )
        self.jury_user = User.objects.create_user(
            username="jury1",
            password="secret123",
            role="jury",
            is_approved=True,
            email="jury@example.com",
        )
        self.participant_user = User.objects.create_user(
            username="member1",
            password="secret123",
            role="participant",
            is_approved=True,
            email="member@example.com",
        )
        self.admin_user = User.objects.create_superuser(
            username="admin",
            password="secret123",
            email="admin@example.com",
        )
        self.client.force_login(self.captain)

    def create_tournament(self, **overrides):
        now = timezone.now()
        defaults = {
            "name": "Spring Cup",
            "description": "Test tournament",
            "start_date": now + timedelta(days=1),
            "end_date": now + timedelta(days=2),
            "registration_start": now - timedelta(days=1),
            "registration_end": now + timedelta(hours=12),
            "is_draft": False,
            "created_by": self.admin_user,
        }
        defaults.update(overrides)
        return Tournament.objects.create(**defaults)

    def test_participant_dashboard_shows_running_tournaments(self):
        tournament = self.create_tournament(
            name="Running Cup",
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(hours=3),
            registration_end=timezone.now() - timedelta(hours=2),
        )
        Task.objects.create(
            tournament=tournament,
            title="Live task",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        team = Team.objects.create(
            name="My Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        TournamentRegistration.objects.create(
            tournament=tournament,
            team=team,
            registered_by=self.captain,
            status=TournamentRegistration.Status.APPROVED,
        )

        response = self.client.get(reverse("participant_dashboard"))

        tournaments = response.context["tournaments_with_state"]
        self.assertEqual(len(tournaments), 1)
        self.assertTrue(tournaments[0]["can_open_tasks"])

    def test_register_team_for_tournament_respects_max_teams(self):
        tournament = self.create_tournament(max_teams=1)
        existing_team = Team.objects.create(
            name="Busy Team",
            captain_user=self.admin_user,
            captain_name="Admin Captain",
            captain_email="admin-captain@example.com",
        )
        TournamentRegistration.objects.create(
            tournament=tournament,
            team=existing_team,
            registered_by=self.admin_user,
            status=TournamentRegistration.Status.APPROVED,
        )

        my_team = Team.objects.create(
            name="My Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )

        response = self.client.post(
            reverse("register_team_for_tournament", args=[tournament.id]),
            {"team": my_team.id},
        )

        self.assertRedirects(response, reverse("participant_dashboard"))
        self.assertFalse(
            TournamentRegistration.objects.filter(
                tournament=tournament,
                team=my_team,
            ).exists()
        )

    def test_submit_solution_requires_approved_registration(self):
        tournament = self.create_tournament(
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(days=1),
            registration_end=timezone.now() - timedelta(hours=2),
        )
        team = Team.objects.create(
            name="Pending Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        TournamentRegistration.objects.create(
            tournament=tournament,
            team=team,
            registered_by=self.captain,
            status=TournamentRegistration.Status.PENDING,
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Build app",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )

        response = self.client.post(
            reverse("submit_solution", args=[task.id]),
            {
                "github_link": "https://github.com/example/repo",
                "video_link": "https://example.com/video",
            },
        )

        self.assertRedirects(response, reverse("participant_dashboard"))
        self.assertFalse(task.submissions.exists())

    def test_submit_solution_saves_all_fields(self):
        tournament = self.create_tournament(
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(days=1),
            registration_end=timezone.now() - timedelta(hours=2),
        )
        team = Team.objects.create(
            name="Approved Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        TournamentRegistration.objects.create(
            tournament=tournament,
            team=team,
            registered_by=self.captain,
            status=TournamentRegistration.Status.APPROVED,
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Build app",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )

        response = self.client.post(
            reverse("submit_solution", args=[task.id]),
            {
                "github_link": "https://github.com/example/repo",
                "video_link": "https://example.com/video",
                "live_demo": "https://example.com/demo",
                "description": "My final solution",
                "is_final": "on",
            },
        )

        self.assertRedirects(response, reverse("team_detail", args=[team.id]))
        submission = Submission.objects.get(team=team, task=task)
        self.assertEqual(submission.live_demo, "https://example.com/demo")
        self.assertEqual(submission.description, "My final solution")
        self.assertTrue(submission.is_final)

    def test_superuser_can_open_team_detail(self):
        team = Team.objects.create(
            name="Team A",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("team_detail", args=[team.id]))

        self.assertEqual(response.status_code, 200)

    def test_admin_can_open_contextual_create_task_page(self):
        tournament = self.create_tournament()
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("create_tournament_task", args=[tournament.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tournament.name)

    def test_admin_can_approve_registration(self):
        tournament = self.create_tournament()
        team = Team.objects.create(
            name="Approval Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        registration = TournamentRegistration.objects.create(
            tournament=tournament,
            team=team,
            registered_by=self.captain,
            status=TournamentRegistration.Status.PENDING,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("approve_registration", args=[registration.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))
        registration.refresh_from_db()
        self.assertEqual(registration.status, TournamentRegistration.Status.APPROVED)

    def test_admin_can_change_user_role(self):
        jury_candidate = User.objects.create_user(
            username="student1",
            password="secret123",
            role="participant",
            is_approved=True,
            email="student1@example.com",
        )
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("update_user_role", args=[jury_candidate.id]),
            {"role": "jury"},
        )

        self.assertRedirects(response, reverse("admin_dashboard"))
        jury_candidate.refresh_from_db()
        self.assertEqual(jury_candidate.role, "jury")

    def test_admin_can_delete_user(self):
        removable_user = User.objects.create_user(
            username="captain2",
            password="secret123",
            role="captain",
            is_approved=True,
            email="captain2@example.com",
        )
        self.client.force_login(self.admin_user)

        response = self.client.post(reverse("delete_user", args=[removable_user.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))
        self.assertFalse(User.objects.filter(id=removable_user.id).exists())

    def test_admin_can_delete_tournament(self):
        tournament = self.create_tournament()
        self.client.force_login(self.admin_user)

        response = self.client.post(reverse("delete_tournament", args=[tournament.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))
        self.assertFalse(Tournament.objects.filter(id=tournament.id).exists())

    def test_admin_can_delete_task(self):
        tournament = self.create_tournament()
        task = Task.objects.create(
            tournament=tournament,
            title="Delete me",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        self.client.force_login(self.admin_user)

        response = self.client.post(reverse("delete_task", args=[task.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))
        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_admin_cannot_edit_started_tournament(self):
        tournament = self.create_tournament(
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(hours=3),
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("edit_tournament", args=[tournament.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_captain_sees_published_tournament_before_registration_starts(self):
        tournament = self.create_tournament(
            registration_start=timezone.now() + timedelta(days=1),
            registration_end=timezone.now() + timedelta(days=2),
            start_date=timezone.now() + timedelta(days=3),
            end_date=timezone.now() + timedelta(days=4),
            is_draft=False,
        )

        response = self.client.get(reverse("participant_dashboard"))

        tournaments = response.context["tournaments_with_state"]
        self.assertEqual(len(tournaments), 1)
        self.assertEqual(tournaments[0]["tournament"].id, tournament.id)
        self.assertFalse(tournaments[0]["can_register"])

    def test_admin_cannot_create_task_for_started_tournament(self):
        tournament = self.create_tournament(
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(hours=3),
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("create_tournament_task", args=[tournament.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_admin_cannot_edit_task_after_tournament_start(self):
        tournament = self.create_tournament(
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(hours=3),
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Locked task",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("edit_task", args=[task.id]))

        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_jury_dashboard_shows_tournaments_with_submissions(self):
        tournament = self.create_tournament()
        team = Team.objects.create(
            name="Jury Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Demo task",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        Submission.objects.create(
            team=team,
            task=task,
            github_link="https://github.com/example/repo",
            video_link="https://example.com/video",
        )
        self.client.force_login(self.jury_user)

        response = self.client.get(reverse("jury_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, tournament.name)

    def test_jury_can_open_tournament_detail_with_team_submissions(self):
        tournament = self.create_tournament()
        team = Team.objects.create(
            name="Folder Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Folder task",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        Submission.objects.create(
            team=team,
            task=task,
            github_link="https://github.com/example/repo",
            video_link="https://example.com/video",
            description="Submission for jury",
        )
        self.client.force_login(self.jury_user)

        response = self.client.get(reverse("jury_tournament_detail", args=[tournament.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, team.name)
        self.assertContains(response, task.title)

    def test_jury_can_submit_evaluation(self):
        tournament = self.create_tournament()
        team = Team.objects.create(
            name="Scored Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Score task",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        submission = Submission.objects.create(
            team=team,
            task=task,
            github_link="https://github.com/example/repo",
            video_link="https://example.com/video",
        )
        self.client.force_login(self.jury_user)

        response = self.client.post(
            reverse("submit_evaluation", args=[submission.id]),
            {
                f"eval-{submission.id}-score_backend": 80,
                f"eval-{submission.id}-score_frontend": 90,
                f"eval-{submission.id}-score_functionality": 85,
                f"eval-{submission.id}-score_ux": 95,
                f"eval-{submission.id}-comment": "Strong work",
            },
        )

        self.assertRedirects(response, reverse("jury_tournament_detail", args=[tournament.id]))
        evaluation = Evaluation.objects.get(assignment__submission=submission, assignment__jury_user=self.jury_user)
        self.assertEqual(evaluation.score_backend, 80)
        self.assertEqual(evaluation.comment, "Strong work")

    def test_captain_sees_jury_evaluation_in_team_results(self):
        tournament = self.create_tournament()
        team = Team.objects.create(
            name="Visible Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Results task",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        submission = Submission.objects.create(
            team=team,
            task=task,
            github_link="https://github.com/example/repo",
            video_link="https://example.com/video",
        )
        self.client.force_login(self.jury_user)
        self.client.post(
            reverse("submit_evaluation", args=[submission.id]),
            {
                f"eval-{submission.id}-score_backend": 80,
                f"eval-{submission.id}-score_frontend": 90,
                f"eval-{submission.id}-score_functionality": 85,
                f"eval-{submission.id}-score_ux": 95,
                f"eval-{submission.id}-comment": "Visible comment",
            },
        )
        self.client.force_login(self.captain)

        response = self.client.get(reverse("team_results", args=[team.id]))

        self.assertContains(response, "Visible comment")
        self.assertContains(response, "87,5")

    def test_participant_sees_jury_evaluation_in_team_results(self):
        tournament = self.create_tournament()
        team = Team.objects.create(
            name="Member Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        Participant.objects.create(
            team=team,
            full_name="Member",
            email=self.participant_user.email,
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Participant results task",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        submission = Submission.objects.create(
            team=team,
            task=task,
            github_link="https://github.com/example/repo",
            video_link="https://example.com/video",
        )
        self.client.force_login(self.jury_user)
        self.client.post(
            reverse("submit_evaluation", args=[submission.id]),
            {
                f"eval-{submission.id}-score_backend": 70,
                f"eval-{submission.id}-score_frontend": 75,
                f"eval-{submission.id}-score_functionality": 80,
                f"eval-{submission.id}-score_ux": 85,
                f"eval-{submission.id}-comment": "Seen by participant",
            },
        )
        self.client.force_login(self.participant_user)

        response = self.client.get(reverse("team_results", args=[team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Seen by participant")

    def test_captain_can_delete_team(self):
        team = Team.objects.create(
            name="Delete Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        self.client.force_login(self.captain)

        response = self.client.post(reverse("delete_team", args=[team.id]))

        self.assertRedirects(response, reverse("participant_dashboard"))
        self.assertFalse(Team.objects.filter(id=team.id).exists())

    def test_participant_can_leave_team(self):
        team = Team.objects.create(
            name="Leave Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        Participant.objects.create(
            team=team,
            full_name="Member",
            email=self.participant_user.email,
        )
        self.client.force_login(self.participant_user)

        response = self.client.post(reverse("leave_team", args=[team.id]))

        self.assertRedirects(response, reverse("participant_dashboard"))
        self.assertFalse(team.participants.filter(email=self.participant_user.email).exists())

    def test_participant_can_open_team_participants_page(self):
        team = Team.objects.create(
            name="Participants Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        Participant.objects.create(
            team=team,
            full_name="Member",
            email=self.participant_user.email,
        )
        self.client.force_login(self.participant_user)

        response = self.client.get(reverse("team_participants", args=[team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member")

    def test_tournament_leaderboard_orders_teams_by_average_score(self):
        tournament = self.create_tournament(
            start_date=timezone.now() - timedelta(hours=1),
            end_date=timezone.now() + timedelta(hours=3),
            registration_end=timezone.now() - timedelta(hours=2),
        )
        task = Task.objects.create(
            tournament=tournament,
            title="Leaderboard task",
            description="desc",
            requirements="req",
            must_have="must",
            is_draft=False,
            created_by=self.admin_user,
        )
        first_team = Team.objects.create(
            name="Alpha Team",
            captain_user=self.captain,
            captain_name="Captain",
            captain_email="captain@example.com",
        )
        second_captain = User.objects.create_user(
            username="captain_b",
            password="secret123",
            role="captain",
            is_approved=True,
            email="captainb@example.com",
        )
        second_team = Team.objects.create(
            name="Beta Team",
            captain_user=second_captain,
            captain_name="Captain B",
            captain_email="captainb@example.com",
        )
        TournamentRegistration.objects.create(
            tournament=tournament,
            team=first_team,
            registered_by=self.captain,
            status=TournamentRegistration.Status.APPROVED,
        )
        TournamentRegistration.objects.create(
            tournament=tournament,
            team=second_team,
            registered_by=second_captain,
            status=TournamentRegistration.Status.APPROVED,
        )
        first_submission = Submission.objects.create(
            team=first_team,
            task=task,
            github_link="https://github.com/example/a",
            video_link="https://example.com/a",
        )
        second_submission = Submission.objects.create(
            team=second_team,
            task=task,
            github_link="https://github.com/example/b",
            video_link="https://example.com/b",
        )
        self.client.force_login(self.jury_user)
        self.client.post(
            reverse("submit_evaluation", args=[first_submission.id]),
            {
                f"eval-{first_submission.id}-score_backend": 95,
                f"eval-{first_submission.id}-score_frontend": 90,
                f"eval-{first_submission.id}-score_functionality": 95,
                f"eval-{first_submission.id}-score_ux": 100,
                f"eval-{first_submission.id}-comment": "Alpha first",
            },
        )
        self.client.post(
            reverse("submit_evaluation", args=[second_submission.id]),
            {
                f"eval-{second_submission.id}-score_backend": 70,
                f"eval-{second_submission.id}-score_frontend": 75,
                f"eval-{second_submission.id}-score_functionality": 80,
                f"eval-{second_submission.id}-score_ux": 85,
                f"eval-{second_submission.id}-comment": "Beta second",
            },
        )
        self.client.force_login(self.captain)

        response = self.client.get(reverse("tournament_leaderboard", args=[tournament.id]))

        self.assertEqual(response.status_code, 200)
        leaderboard = response.context["leaderboard"]
        self.assertEqual(leaderboard[0]["team"].name, "Alpha Team")
        self.assertEqual(leaderboard[0]["place"], 1)
        self.assertEqual(leaderboard[1]["team"].name, "Beta Team")
