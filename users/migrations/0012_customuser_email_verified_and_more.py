from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_alter_customuser_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="email_verified",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="customuser",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
