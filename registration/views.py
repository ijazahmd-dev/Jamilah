from django.shortcuts import render,HttpResponse,redirect # type: ignore
from django.contrib.auth.models import User # type: ignore
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.db.models import Q
from django.contrib import messages
from datetime import datetime, timedelta,timezone
from django.core.mail import send_mail # type: ignore
from django.utils import timezone as django_timezone # type: ignore
import random
import re
from django.http import JsonResponse
import secrets
from user_profile.models import Referral
from wallet.models import Wallet, WalletTransaction


"""
GENERATE 4 DIGIT OTP
"""
def generate_otp():
    return str(secrets.randbelow(10000)).zfill(4)





from django.conf import settings


"""
SEND OTP TO EMAIL ACCOUNT
"""

def send_otp_email(email, otp):
    subject = "Your OTP Verification Code - Jamilah"
    message = f"Hello,\n\nYour verification OTP code is: {otp}\n\nThis code is valid for 1 minute. Please do not share this code with anyone.\n\nThank you,\nJamilah Team"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
    print(f"Attempting to send OTP {otp} from {from_email} to {email}")

    try:
        send_mail(subject, message, from_email, [email], fail_silently=False)
        print("OTP email sent successfully!")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False





"""
PASSWORD VALIDATION
"""
def validate_password(password):
    if not password or not password.strip():
        return False, "Password cannot be empty or contain only whitespace."
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."
    if ' ' in password:
        return False, "Password cannot contain spaces."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter (a-z)."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number (0-9)."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character (!@#$%^&*...)."
    return True, ""






"""
USER LOGIN
"""
@never_cache
def LoginPage(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    form_data = {} 
    errors = {}
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        form_data['email'] = email

        # Validation checks
        if not email:
            errors['email'] = 'Email address is required.'
        else:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                errors['email'] = 'Please enter a valid email address.'

        if not password:
            errors['password'] = 'Password is required.'

        if errors:
            for error in errors.values():
                messages.error(request, error)
            return render(request, 'login.html', {'form_data': form_data, 'errors': errors})

        user = authenticate(request, username=email, password=password)
        if user is None:
            # Check if user registered with a different username or case-insensitive email
            user_obj = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).first()
            if user_obj:
                user = authenticate(request, username=user_obj.username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, "Your account has been deactivated. Please contact support.")
                errors['non_field'] = "Your account has been deactivated."
                return render(request, 'login.html', {'form_data': form_data, 'errors': errors})
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, "Invalid email or password.")
            errors['non_field'] = "Invalid email or password."
            return render(request, 'login.html', {'form_data': form_data, 'errors': errors})

    return render(request, 'login.html', {'form_data': form_data, 'errors': errors})






"""
USER SIGN UP/ REGISTRATION
"""
@never_cache
def SignupPage(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    form_data = {}
    errors = {}
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        referral_code = request.POST.get('referral_code', '').strip()
        terms = request.POST.get('terms')

        form_data = {
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'referral_code': referral_code,
        }

        # Username validation: 3-20 characters, letters/numbers/underscores only
        username_pattern = r'^[a-zA-Z0-9_]{3,20}$'
        if not username:
            errors['username'] = "Username is required."
        elif not re.match(username_pattern, username):
            errors['username'] = "Username must be 3-20 characters long and contain only letters, numbers, or underscores."
        elif User.objects.filter(username__iexact=username).exists():
            errors['username'] = "Username already exists. Please choose a different one."

        # First name validation: letters only, 2-30 chars
        name_pattern = r'^[a-zA-Z]{2,30}$'
        if not first_name:
            errors['first_name'] = "First name is required."
        elif not re.match(name_pattern, first_name):
            errors['first_name'] = "First name must contain only letters (2-30 characters)."

        # Last name validation: letters only, 1-30 chars
        last_name_pattern = r'^[a-zA-Z]{1,30}$'
        if not last_name:
            errors['last_name'] = "Last name is required."
        elif not re.match(last_name_pattern, last_name):
            errors['last_name'] = "Last name must contain only letters (1-30 characters)."

        # Email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not email:
            errors['email'] = "Email address is required."
        elif len(email) > 100:
            errors['email'] = "Email address cannot exceed 100 characters."
        elif not re.match(email_pattern, email):
            errors['email'] = "Please enter a valid email address."
        elif User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            errors['email'] = "An account with this email already exists. Please sign in or use a different email."

        # Password validation
        if not password:
            errors['password'] = "Password is required."
        else:
            is_valid_password, password_error = validate_password(password)
            if not is_valid_password:
                errors['password'] = password_error

        # Confirm password validation
        if not confirm_password:
            errors['confirm_password'] = "Please confirm your password."
        elif password != confirm_password:
            errors['confirm_password'] = "Passwords do not match."

        # Validate referral code (optional)
        referred_by = None
        if referral_code:
            try:
                referral = Referral.objects.get(referral_code=referral_code)
                referred_by = referral.user
            except Referral.DoesNotExist:
                errors['referral_code'] = "Invalid referral code. Please verify or leave blank."

        # Validate terms
        if not terms:
            errors['terms'] = "You must agree to the terms & policy."

        if errors:
            for error in errors.values():
                messages.error(request, error)
            return render(request, 'signup.html', {'form_data': form_data, 'errors': errors})

        otp = generate_otp()
        expires_at = django_timezone.now() + timedelta(minutes=1)

        # Store OTP and user information in session
        request.session['otp'] = otp
        request.session['otp_expires_at'] = int(expires_at.timestamp())
        request.session['username'] = username
        request.session['email'] = email 
        request.session['password'] = password
        request.session['first_name'] = first_name
        request.session['last_name'] = last_name
        request.session['referral_code'] = referral_code

        if not send_otp_email(email, otp):
            messages.error(request, "Failed to send OTP email. Please try again.")
            return render(request, 'signup.html', {'form_data': form_data, 'errors': errors})
        
        return redirect('verify_otp')
 
    return render(request, 'signup.html', {'form_data': form_data, 'errors': errors})







"""
OTP VERIFICATION
"""

def verify_otp(request):
    email = request.session.get('email')
    if not email:
        messages.error(request, 'Registration session expired. Please sign up again.')
        return redirect('signup')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()
        otp = request.session.get('otp')
        otp_expires_at = request.session.get('otp_expires_at') 

        if not entered_otp or not entered_otp.isdigit() or len(entered_otp) != 4:
            return render(request, 'verify_otp.html', {'error': 'Please enter a valid 4-digit numeric OTP.', 'email': email})

        if not otp:
            return render(request, 'verify_otp.html', {'error': 'OTP not found. Please request a new OTP.', 'email': email})

        try:
            otp_expires_at_dt = datetime.fromtimestamp(otp_expires_at, tz=timezone.utc)
        except (ValueError, TypeError):
            return render(request, 'verify_otp.html', {'error': 'Invalid OTP expiration format.', 'email': email})

        if django_timezone.now() > otp_expires_at_dt:
            return render(request, 'verify_otp.html', {'error': 'OTP has expired. Please request a new one.', 'email': email})

        if str(otp) == entered_otp:
            # proceed with registration
            username = request.session['username']
            password = request.session['password']
            first_name = request.session['first_name']
            last_name = request.session['last_name']
            referral_code = request.session.get('referral_code')

            user = User.objects.create_user(
                username=email, 
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

            Referral.objects.create(user=user)
            wallet, _ = Wallet.objects.get_or_create(user=user)

            if referral_code:
                try:
                    referral = Referral.objects.get(referral_code=referral_code)
                    referred_by = referral.user
                    Referral.objects.filter(user=user).update(referred_by=referred_by)

                    wallet.balance += 50
                    wallet.save()
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        amount=50,
                        transaction_type='credit',
                        description='Referral bonus for new user'
                    )

                    referred_wallet, _ = Wallet.objects.get_or_create(user=referred_by)
                    referred_wallet.balance += 100
                    referred_wallet.save()
                    WalletTransaction.objects.create(
                        wallet=referred_wallet,
                        amount=100,
                        transaction_type='credit',
                        description='Referral bonus for referring user'
                    )
                except Referral.DoesNotExist:
                    pass 

            # clear session data
            for key in ['otp', 'otp_expires_at', 'username', 'email', 'password', 'first_name', 'last_name', 'referral_code']:
                request.session.pop(key, None)

            messages.success(request, 'Registration successful! Please log in.')
            return redirect('login')
        else:
            return render(request, 'verify_otp.html', {'error': 'Invalid OTP. Please try again.', 'email': email})

    return render(request, 'verify_otp.html', {'email': email})



"""
RESEND OTP
"""

def resend_otp(request):
    if request.method == 'POST':
        otp = request.session.get('otp')
        otp_expires_at = request.session.get('otp_expires_at')

        # Check if the OTP is still valid
        if otp and django_timezone.now() < django_timezone.make_aware(datetime.fromtimestamp(otp_expires_at)):
            # Calculate time remaining for the OTP to expire
            time_remaining = (django_timezone.make_aware(datetime.fromtimestamp(otp_expires_at)) - django_timezone.now()).seconds
            return JsonResponse({'success': False, 'message': f"Please wait {time_remaining} seconds before requesting a new OTP."})

        # Send new OTP if expired or not present
        new_otp = generate_otp()
        expires_at = django_timezone.now() + timedelta(minutes=1)
        request.session['otp'] = new_otp
        request.session['otp_expires_at'] = int(expires_at.timestamp())  

        if send_otp_email(request.session['email'], new_otp):
            return JsonResponse({'success': True, 'message': 'New OTP sent successfully!'})
        else:
            return JsonResponse({'success': False, 'message': 'Failed to send OTP. Please try again.'})
    




def ForgotPassword(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        errors = {}

        if not email:
            errors['email'] = 'Email address is required.'
        else:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                errors['email'] = 'Please enter a valid email address.'

        if errors:
            for error in errors.values():
                messages.error(request, error)
            return render(request, 'forgot_password.html', {'email': email, 'errors': errors})

        # Initialize OTP attempt count if not already set
        if 'otp_attempts' not in request.session:
            request.session['otp_attempts'] = 0

        otp_attempts = request.session.get('otp_attempts', 0)

        if otp_attempts >= 3:
            messages.error(request, "You have exceeded the maximum number of OTP attempts. Please try again later.")
            return render(request, 'forgot_password.html', {'email': email, 'errors': {'email': 'Too many OTP attempts. Please try again later.'}})

        try:
            user = User.objects.get(email__iexact=email)
            if not user.is_active:
                messages.error(request, 'This account is deactivated. Please contact support.')
                return render(request, 'forgot_password.html', {'email': email, 'errors': {'email': 'Account deactivated.'}})

            otp = generate_otp()
            expires_at = django_timezone.now() + timedelta(minutes=3)

            # Store OTP and expiry as timestamps in session
            request.session['password_reset_otp'] = otp
            request.session['password_reset_expires_at'] = int(expires_at.timestamp())
            request.session['reset_email'] = user.email
            request.session['otp_attempts'] = 0
            request.session.modified = True

            if send_otp_email(user.email, otp):
                messages.success(request, 'OTP sent successfully to your email.')
                return redirect('verify_forgot_password_otp')
            else:
                messages.error(request, 'Failed to send OTP. Please try again.')
                return render(request, 'forgot_password.html', {'email': email})
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
            return render(request, 'forgot_password.html', {'email': email, 'errors': {'email': 'No account found with this email address.'}})

    return render(request, 'forgot_password.html')




"""
VERIFY FORGOT PASSWORD OTP
"""
def verify_forgot_password_otp(request):
    otp = request.session.get('password_reset_otp')
    otp_expires_at = request.session.get('password_reset_expires_at')
    email = request.session.get('reset_email')

    if not otp or not otp_expires_at or not email:
        messages.error(request, 'Session expired or invalid. Please request a new OTP.')
        return redirect('forgot_password')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()
        attempts = request.session.get('otp_attempts', 0)

        if not entered_otp or not entered_otp.isdigit() or len(entered_otp) != 4:
            messages.error(request, 'Please enter a valid 4-digit numeric OTP.')
            return render(request, 'verify_forgot_password_otp.html', {'email': email})

        try:
            otp_expires_at_dt = datetime.fromtimestamp(otp_expires_at, tz=timezone.utc)
        except (ValueError, TypeError):
            messages.error(request, 'Invalid OTP expiration format.')
            return redirect('forgot_password')

        if django_timezone.now() > otp_expires_at_dt:
            messages.error(request, 'OTP has expired. Please request a new one.')
            return redirect('forgot_password')

        if attempts >= 3:
            messages.error(request, 'Too many incorrect attempts. Please request a new OTP.')
            return redirect('forgot_password')

        if str(otp) == entered_otp:
            messages.success(request, 'OTP verified successfully.')

            # Clear OTP and attempts from session, mark verified
            del request.session['password_reset_otp']
            del request.session['password_reset_expires_at']
            request.session.pop('otp_attempts', None)
            request.session['reset_verified'] = True
            request.session.modified = True

            return redirect('reset_password')
        else:
            attempts += 1
            request.session['otp_attempts'] = attempts
            request.session.modified = True
            remaining = max(0, 3 - attempts)
            if remaining > 0:
                messages.error(request, f"Invalid OTP. {remaining} attempt(s) remaining.")
            else:
                messages.error(request, "Too many incorrect attempts. Please request a new OTP.")
                return redirect('forgot_password')
            return render(request, 'verify_forgot_password_otp.html', {'email': email})

    return render(request, 'verify_forgot_password_otp.html', {'email': email})





def reset_password(request):
    email = request.session.get('reset_email')
    is_verified = request.session.get('reset_verified', False)

    if not email or not is_verified:
        messages.error(request, 'Session expired or unverified. Please request a password reset.')
        return redirect('forgot_password')

    errors = {}
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not new_password:
            errors['new_password'] = 'Please enter a new password.'
        else:
            is_valid_pwd, pwd_error = validate_password(new_password)
            if not is_valid_pwd:
                errors['new_password'] = pwd_error

        if not confirm_password:
            errors['confirm_password'] = 'Please confirm your new password.'
        elif new_password != confirm_password:
            errors['confirm_password'] = 'Passwords do not match.'

        if errors:
            for error in errors.values():
                messages.error(request, error)
            return render(request, 'reset_password.html', {'errors': errors})

        try:
            user = User.objects.get(email__iexact=email)
            user.set_password(new_password)
            user.save()

            # Clear session data for security   
            request.session.pop('reset_email', None)
            request.session.pop('reset_verified', None)
            request.session.pop('password_reset_otp', None)
            request.session.pop('password_reset_expires_at', None)
            request.session.pop('otp_attempts', None)
            request.session.modified = True

            messages.success(request, 'Password reset successfully. Please log in with your new password.')
            return redirect('login')

        except User.DoesNotExist:
            messages.error(request, 'User not found. Please try again.')
            return redirect('forgot_password')     

    return render(request, 'reset_password.html', {'errors': errors})







#Logout
@never_cache
def User_Logout(request):
    logout(request)
    return redirect('login')









