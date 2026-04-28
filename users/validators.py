import re
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import CommonPasswordValidator, NumericPasswordValidator


class CustomSimplePasswordValidator:
    """
    Rejects passwords that are:
    - purely numeric (e.g. 12345678)
    - in the common-passwords list (e.g. qwerty, password)
    - sequential characters (e.g. abcdefgh, 12345678)
    - all same characters (e.g. aaaaaaaa)
    """

    def __init__(self):
        self.common_validator = CommonPasswordValidator()
        self.numeric_validator = NumericPasswordValidator()

    def validate(self, password, user=None):
        # Check all-same characters
        if len(set(password)) == 1:
            raise ValidationError("Пароль занадто простий, оберіть інший.")

        # Check purely numeric
        try:
            self.numeric_validator.validate(password, user)
        except ValidationError:
            raise ValidationError("Пароль занадто простий, оберіть інший.")

        # Check common passwords list
        try:
            self.common_validator.validate(password, user)
        except ValidationError:
            raise ValidationError("Пароль занадто простий, оберіть інший.")

    def get_help_text(self):
        return "Пароль не повинен бути занадто простим."
