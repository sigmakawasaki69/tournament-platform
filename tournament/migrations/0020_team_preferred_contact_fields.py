from django.db import migrations, models


def fill_preferred_contact_fields(apps, schema_editor):
    Team = apps.get_model("tournament", "Team")
    for team in Team.objects.all():
        if team.preferred_contact_method and team.preferred_contact_value:
            continue

        preferred_method = None
        preferred_value = None
        if team.telegram:
            preferred_method = "telegram"
            preferred_value = team.telegram
        elif team.discord:
            preferred_method = "discord"
            preferred_value = team.discord
        elif team.viber:
            preferred_method = "viber"
            preferred_value = team.viber

        if preferred_method and preferred_value:
            team.preferred_contact_method = preferred_method
            team.preferred_contact_value = preferred_value
            team.save(update_fields=["preferred_contact_method", "preferred_contact_value"])


class Migration(migrations.Migration):

    dependencies = [
        ("tournament", "0018_tournament_evaluation_finished_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="preferred_contact_method",
            field=models.CharField(
                blank=True,
                choices=[("telegram", "Телеграм"), ("discord", "Діскорд"), ("viber", "Вайбер")],
                max_length=20,
                null=True,
                verbose_name="Спосіб зв'язку",
            ),
        ),
        migrations.AddField(
            model_name="team",
            name="preferred_contact_value",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name="Контакт для зв'язку",
            ),
        ),
        migrations.RunPython(fill_preferred_contact_fields, migrations.RunPython.noop),
    ]
