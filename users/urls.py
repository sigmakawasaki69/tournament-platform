from django.urls import path
from .views import (
    home,
    register_view,
    login_view,
    logout_view,
    redirect_by_role,
    admin_dashboard,
    approve_user,
    create_tournament,
    jury_dashboard,
    participant_dashboard,
)

urlpatterns = [
    path('', home, name='home'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    path('redirect/', redirect_by_role, name='redirect_by_role'),
    path('admin-dashboard/', admin_dashboard, name='admin_dashboard'),
    path('approve-user/<int:user_id>/', approve_user, name='approve_user'),
    path('create-tournament/', create_tournament, name='create_tournament'),
    path('jury-dashboard/', jury_dashboard, name='jury_dashboard'),
    path('participant-dashboard/', participant_dashboard, name='participant_dashboard'),
]