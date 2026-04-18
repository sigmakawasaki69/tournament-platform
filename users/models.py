from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('participant', 'Учасник'),
        ('jury', 'Журі'),
        ('organizer', 'Організатор'),
        ('admin', 'Адміністратор'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='participant')
    is_approved = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    announcements_seen_at = models.DateTimeField(null=True, blank=True)
    certificates_seen_at = models.DateTimeField(null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name="Аватар")

    def save(self, *args, **kwargs):
        if self.role == 'participant':
            self.is_approved = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role})"


class LoginThrottle(models.Model):
    identifier = models.CharField(max_length=150, verbose_name="Логін")
    ip_address = models.CharField(max_length=64, verbose_name="IP-адреса")
    failed_attempts = models.PositiveIntegerField(default=0, verbose_name="Кількість невдалих спроб")
    blocked_until = models.DateTimeField(null=True, blank=True, verbose_name="Заблоковано до")
    last_failed_at = models.DateTimeField(null=True, blank=True, verbose_name="Остання невдала спроба")

    class Meta:
        verbose_name = "Обмеження входу"
        verbose_name_plural = "Обмеження входу"
        constraints = [
            models.UniqueConstraint(
                fields=["identifier", "ip_address"],
                name="unique_login_throttle_identifier_ip",
            )
        ]

    def __str__(self):
        return f"{self.identifier} @ {self.ip_address}"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='password_reset_codes')
    code = models.CharField(max_length=6, verbose_name="Код безпеки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата створення")
    is_used = models.BooleanField(default=False, verbose_name="Використано")

    class Meta:
        verbose_name = "Код скидання пароля"
        verbose_name_plural = "Коди скидання пароля"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.code}"

