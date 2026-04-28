from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import CommonPasswordValidator, NumericPasswordValidator

class CustomSimplePasswordValidator:
    def __init__(self):
        self.common_validator = CommonPasswordValidator()
        self.numeric_validator = NumericPasswordValidator()

    def validate(self, password, user=None):
        try:
            self.common_validator.validate(password, user)
            self.numeric_validator.validate(password, user)
        except ValidationError:
            raise ValidationError("Пароль занадто простий, оберіть інший.")

    def get_help_text(self):
        return "Пароль занадто простий, оберіть інший."
