from django.db import migrations, models


def fill_allowed_contact_methods(apps, schema_editor):
    Tournament = apps.get_model("tournament", "Tournament")
    default_methods = ["telegram", "discord", "viber"]
    for tournament in Tournament.objects.all():
        if not tournament.allowed_contact_methods:
            tournament.allowed_contact_methods = default_methods
            tournament.save(update_fields=["allowed_contact_methods"])


class Migration(migrations.Migration):

    dependencies = [
        ("tournament", "0020_team_preferred_contact_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="tournament",
            name="allowed_contact_methods",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="Доступні способи зв'язку для команди",
            ),
        ),
        migrations.RunPython(fill_allowed_contact_methods, migrations.RunPython.noop),
    ]
