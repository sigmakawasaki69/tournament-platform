from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tournament", "0016_remove_tournament_curator_users"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="deadline",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="Дедлайн здачі",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="start_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="Початок завдання",
            ),
        ),
    ]
