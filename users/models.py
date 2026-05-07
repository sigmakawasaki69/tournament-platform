from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


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

    # Соціальні мережі та валідація
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name="Telegram ID")
    discord_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name="Discord ID")
    is_tg_verified = models.BooleanField(default=False, verbose_name="Telegram підтверджено")
    is_discord_verified = models.BooleanField(default=False, verbose_name="Discord підтверджено")

    def save(self, *args, **kwargs):
        if self.role == 'participant':
            self.is_approved = True
        
        # Автоматично надаємо доступ до адмін-панелі для відповідних ролей
        if self.role in ['admin', 'organizer', 'jury'] or self.is_superuser:
            self.is_staff = True
        else:
            self.is_staff = False
            
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


class SocialAccountValidation(models.Model):
    PROVIDER_CHOICES = (
        ('telegram', 'Telegram'),
        ('discord', 'Discord'),
    )
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='social_validations')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    code = models.CharField(max_length=8, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.username} - {self.provider} - {self.code}"
