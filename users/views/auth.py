import logging
import random
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from urllib.error import HTTPError, URLError

from tournament.models import RegistrationMember
from ..forms import LoginForm, RegisterForm
from ..models import CustomUser, PasswordResetCode
from ..platform_services import (
    LOGIN_THROTTLE_IDENTIFIER_SESSION_KEY,
    LOGIN_THROTTLE_IP_SESSION_KEY,
    clear_login_throttle,
    email_delivery_ready,
    get_client_ip,
    get_login_throttle,
    normalize_login_identifier,
    register_failed_login,
    send_verification_email,
    send_password_reset_code_email,
)
from ..policies import get_safe_redirect
from ..selectors import build_notification_nav_context

logger = logging.getLogger(__name__)

def register_view(request):
    next_url = request.GET.get('next') or request.POST.get('next')
    if request.user.is_authenticated:
        return redirect(get_safe_redirect(request, next_url, reverse('redirect_by_role')))

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            if not email_delivery_ready():
                form.add_error(
                    None,
                    "На сервері не налаштовано реальну відправку email. "
                    "Заповніть SMTP-параметри, а потім повторіть реєстрацію.",
                )
                return render(request, 'register.html', {'form': form, 'next_url': next_url})
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.role = 'participant'
                    user.is_approved = True
                    user.email_verified = False
                    user.email_verified_at = None
                    user.save()
                    RegistrationMember.objects.filter(
                        user__isnull=True,
                        email__iexact=user.email,
                    ).update(user=user)
                    send_verification_email(request, user)
            except Exception as exc:
                logger.exception("Failed to send verification email during registration")
                if isinstance(exc, OSError) and getattr(exc, 'errno', None) == 101:
                    form.add_error(
                        None,
                        "Безкоштовний Render блокує SMTP-порти. "
                        "Для нього краще використати email API, наприклад Brevo.",
                    )
                elif isinstance(exc, (HTTPError, URLError)):
                    form.add_error(
                        None,
                        "Не вдалося відправити лист через email API. Перевірте ключ та підтверджену адресу відправника.",
                    )
                else:
                    form.add_error(
                        None,
                        "Не вдалося надіслати лист підтвердження. Перевірте налаштування пошти або спробуйте пізніше.",
                    )
            else:
                success_url = reverse('register_success')
                if next_url:
                    success_url = f"{success_url}?next={next_url}"
                return redirect(success_url)
    else:
        form = RegisterForm()

    return render(request, 'register.html', {'form': form, 'next_url': next_url})

def register_success_view(request):
    return render(request, 'register_success.html', {'next_url': request.GET.get('next')})

def verify_email_view(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=['email_verified', 'email_verified_at'])
        return redirect(f"{reverse('login')}?verified=1")

    return render(request, 'verify_email_result.html', {'verification_failed': True})

def login_view(request):
    message = ''
    next_url = request.GET.get('next') or request.POST.get('next')
    blocked_until = None
    blocked_identifier = None
    client_ip = get_client_ip(request)

    if request.user.is_authenticated:
        return redirect(get_safe_redirect(request, next_url, reverse('redirect_by_role')))

    if request.method == 'GET':
        session_identifier = request.session.get(LOGIN_THROTTLE_IDENTIFIER_SESSION_KEY)
        session_ip = request.session.get(LOGIN_THROTTLE_IP_SESSION_KEY)
        if session_identifier and session_ip == client_ip:
            throttle = get_login_throttle(session_identifier, client_ip)
            if throttle and throttle.blocked_until and throttle.blocked_until > timezone.now():
                blocked_until = throttle.blocked_until
                blocked_identifier = session_identifier
                message = (
                    'Забагато невдалих спроб входу. '
                    'Спробуйте ще раз після завершення таймера.'
                )
            else:
                clear_login_throttle(request, session_identifier, client_ip)

    if request.method == 'POST':
        blocked_identifier = normalize_login_identifier(request.POST.get('username'))
        throttle = get_login_throttle(blocked_identifier, client_ip)
        if throttle and throttle.blocked_until and throttle.blocked_until > timezone.now():
            blocked_until = throttle.blocked_until
            request.session[LOGIN_THROTTLE_IDENTIFIER_SESSION_KEY] = blocked_identifier
            request.session[LOGIN_THROTTLE_IP_SESSION_KEY] = client_ip
            form = LoginForm(request, data=request.POST)
            message = (
                'Забагато невдалих спроб входу. '
                'Спробуйте ще раз після завершення таймера.'
            )
            return render(
                request,
                'login.html',
                {
                    'form': form,
                    'message': message,
                    'next_url': next_url,
                    'blocked_until': blocked_until,
                    'blocked_until_iso': blocked_until.isoformat(),
                    'blocked_login_identifier': blocked_identifier,
                },
            )

        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            clear_login_throttle(request, blocked_identifier, client_ip)
            if not user.email_verified:
                message = 'Спочатку підтвердіть електронну пошту через лист, який ми надіслали після реєстрації.'
            elif not user.is_approved and not user.is_superuser:
                message = 'Ваш акаунт ще не схвалений адміністратором.'
            else:
                login(request, user)
                return redirect(get_safe_redirect(request, next_url, reverse('redirect_by_role')))
        else:
            throttle, attempts_left = register_failed_login(blocked_identifier, client_ip)
            if throttle and throttle.blocked_until and throttle.blocked_until > timezone.now():
                blocked_until = throttle.blocked_until
                request.session[LOGIN_THROTTLE_IDENTIFIER_SESSION_KEY] = blocked_identifier
                request.session[LOGIN_THROTTLE_IP_SESSION_KEY] = client_ip
                message = (
                    'Забагато невдалих спроб входу. '
                    'Спробуйте ще раз після завершення таймера.'
                )
            elif attempts_left is not None:
                message = f'Неправильний логін або пароль. Залишилося спроб: {attempts_left}.'
            else:
                message = 'Неправильний логін або пароль.'
    else:
        form = LoginForm()
        if request.GET.get('verified') == '1':
            message = 'Пошту підтверджено. Тепер можна увійти в акаунт.'

    context = {
        'form': form,
        'message': message,
        'next_url': next_url,
        'blocked_until': blocked_until,
        'blocked_login_identifier': blocked_identifier,
    }
    if blocked_until:
        context['blocked_until_iso'] = blocked_until.isoformat()
    return render(request, 'login.html', context)

def logout_view(request):
    logout(request)
    return redirect('home')

def password_reset_request_view(request):
    from django.db.models import Q
    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip()
        user = CustomUser.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
        if user:
            code = str(random.randint(100000, 999999))
            PasswordResetCode.objects.create(user=user, code=code)
            send_password_reset_code_email(request, user=user, code=code)
            
            email = user.email
            if len(email) >= 5:
                masked = email[0] + "***********" + email[-4:]
            else:
                masked = email[0] + "***********" + email[-1:] if len(email) > 1 else email + "***********"
                
            request.session['password_reset_email'] = user.email
            request.session['password_reset_masked_email'] = masked
            return redirect('password_reset_verify')
        else:
            messages.error(request, "Користувача з таким логіном або поштою не знайдено.")
    return render(request, 'password_reset_request.html')

def password_reset_verify_view(request):
    email = request.session.get('password_reset_email')
    masked_email = request.session.get('password_reset_masked_email')
    if not email:
        return redirect('password_reset_request')
    
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        reset_code = PasswordResetCode.objects.filter(
            user__email__iexact=email, 
            code=code, 
            is_used=False
        ).order_by('-created_at').first()
        
        if reset_code:
            if timezone.now() > reset_code.created_at + timedelta(minutes=15):
                messages.error(request, "Термін дії коду вичерпано. Будь ласка, спробуйте ще раз.")
                return redirect('password_reset_request')
            
            request.session['password_reset_verified'] = True
            return redirect('password_reset_confirm')
        else:
            messages.error(request, "Невірний код безпеки.")
            
    return render(request, 'password_reset_verify.html', {
        'email': email,
        'masked_email': masked_email
    })

def password_reset_confirm_view(request):
    email = request.session.get('password_reset_email')
    verified = request.session.get('password_reset_verified')
    
    if not email or not verified:
        return redirect('password_reset_request')
        
    if request.method == 'POST':
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if password != confirm_password:
            messages.error(request, "Паролі не співпадають.")
        elif CustomUser.objects.get(email__iexact=email).check_password(password):
            messages.error(request, "Ви не можете змінити пароль на той самий.")
        else:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            user = CustomUser.objects.get(email__iexact=email)
            try:
                validate_password(password, user)
                user.set_password(password)
                user.save()
            
                PasswordResetCode.objects.filter(user=user).update(is_used=True)
                
                request.session.pop('password_reset_email', None)
                request.session.pop('password_reset_verified', None)
                
                messages.success(request, "Пароль успішно змінено. Тепер ви можете увійти.")
                return redirect('login')
            except ValidationError as e:
                messages.error(request, e.messages[0])
            
    return render(request, 'password_reset_confirm.html')
