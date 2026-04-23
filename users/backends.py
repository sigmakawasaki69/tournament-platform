from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from .models import CustomUser

class EmailOrUsernameModelBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using either their
    username or their email address.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(CustomUser.USERNAME_FIELD)
        
        try:
            # Check if the identifier is an email or username
            user = CustomUser.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
        except CustomUser.DoesNotExist:
            # Run the default password hasher to prevent timing attacks
            CustomUser().set_password(password)
        else:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        return None
