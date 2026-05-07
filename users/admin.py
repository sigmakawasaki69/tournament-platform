from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'is_approved', 'is_staff', 'is_tg_verified', 'is_discord_verified')
    list_filter = ('role', 'is_approved', 'is_staff', 'is_superuser', 'is_tg_verified', 'is_discord_verified')
    fieldsets = UserAdmin.fieldsets + (
        ('Ролі та статус', {'fields': ('role', 'is_approved')}),
        ('Верифікація соцмереж', {'fields': ('telegram_id', 'discord_id', 'is_tg_verified', 'is_discord_verified')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Extra Fields', {'fields': ('role', 'is_approved')}),
    )