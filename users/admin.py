from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'is_approved', 'is_staff', 'is_superuser')
    list_filter = ('role', 'is_approved', 'is_staff', 'is_superuser')
    fieldsets = UserAdmin.fieldsets + (
        ('Extra Fields', {'fields': ('role', 'is_approved')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Extra Fields', {'fields': ('role', 'is_approved')}),
    )