from django.shortcuts import render,redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Address,ShippingAddress,Profile, Referral
from django.contrib import messages
import re
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.conf import settings
import random
import string
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST




# Create your views here.










# Helper function for common validations
def validate_address_fields(name, address_line, city, state, country, postcode, phone):
    errors = []

    name = (name or '').strip()
    address_line = (address_line or '').strip()
    city = (city or '').strip()
    state = (state or '').strip()
    country = (country or '').strip()
    postcode = (postcode or '').strip()
    phone = (phone or '').strip()

    # Name validation
    if not name:
        errors.append("Name is required and cannot be whitespace only.")
    elif len(name) < 2:
        errors.append("Name must be at least 2 characters long.")
    elif len(name) > 50:
        errors.append("Name cannot exceed 50 characters.")
    elif not re.match(r'^[A-Za-z]+(?:\s[A-Za-z]+)*$', name):
        errors.append("Name must contain only letters and single spaces between words.")

    # Address validation
    if not address_line:
        errors.append("Address is required and cannot be whitespace only.")
    elif len(address_line) < 5:
        errors.append("Address must be at least 5 characters long.")
    elif len(address_line) > 200:
        errors.append("Address cannot exceed 200 characters.")
    elif not re.search(r'[A-Za-z0-9]', address_line):
        errors.append("Address must contain letters or numbers.")
    elif not re.match(r'^[A-Za-z0-9\s,.#\/-]+$', address_line):
        errors.append("Address can only contain letters, numbers, spaces, and common punctuation (., #, -, /).")

    # City validation
    if not city:
        errors.append("City is required and cannot be whitespace only.")
    elif len(city) < 2:
        errors.append("City must be at least 2 characters long.")
    elif len(city) > 50:
        errors.append("City cannot exceed 50 characters.")
    elif not re.match(r'^[A-Za-z]+(?:\s[A-Za-z]+)*$', city):
        errors.append("City must contain only letters and spaces.")

    # State validation
    if not state:
        errors.append("State is required and cannot be whitespace only.")
    elif len(state) < 2:
        errors.append("State must be at least 2 characters long.")
    elif len(state) > 50:
        errors.append("State cannot exceed 50 characters.")
    elif not re.match(r'^[A-Za-z]+(?:\s[A-Za-z]+)*$', state):
        errors.append("State must contain only letters and spaces.")

    # Country validation
    if not country:
        errors.append("Country is required and cannot be whitespace only.")
    elif len(country) < 2:
        errors.append("Country must be at least 2 characters long.")
    elif len(country) > 50:
        errors.append("Country cannot exceed 50 characters.")
    elif not re.match(r'^[A-Za-z]+(?:\s[A-Za-z]+)*$', country):
        errors.append("Country must contain only letters and spaces.")

    # Postcode validation
    if not postcode:
        errors.append("Postcode is required.")
    elif not postcode.isdigit():
        errors.append("Postcode must be numeric digits only.")
    elif len(postcode) != 6:
        errors.append("Postcode must be exactly 6 digits.")

    # Phone validation
    if not phone:
        errors.append("Phone number is required.")
    else:
        phone_clean = phone.replace(' ', '').replace('-', '')
        if not (re.match(r'^(?:\+91|91)?[6-9]\d{9}$', phone_clean) or re.match(r'^\+?[1-9]\d{9,14}$', phone_clean)):
            errors.append("Please enter a valid 10-digit mobile number.")

    return errors

















@login_required
def user_profile(request):
    if request.method == 'POST':
        # Get form data and strip whitespace
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()

        # Username validation
        username_pattern = r'^[a-zA-Z0-9_]{3,20}$'
        if not username:
            messages.error(request, 'Username is required.')
            return redirect('user_profile')
        elif not re.match(username_pattern, username):
            messages.error(request, 'Username must be 3-20 characters long and contain only letters, numbers, or underscores.')
            return redirect('user_profile')
        elif User.objects.exclude(pk=request.user.pk).filter(username__iexact=username).exists():
            messages.error(request, 'This username is already taken. Please choose a different one.')
            return redirect('user_profile')

        # First name validation
        name_pattern = r'^[a-zA-Z\s]{2,30}$'
        if not first_name:
            messages.error(request, 'First name is required.')
            return redirect('user_profile')
        elif not re.match(name_pattern, first_name) or not first_name.strip():
            messages.error(request, 'First name must contain only letters (2-30 characters).')
            return redirect('user_profile')

        # Last name validation
        last_name_pattern = r'^[a-zA-Z\s]{1,30}$'
        if not last_name:
            messages.error(request, 'Last name is required.')
            return redirect('user_profile')
        elif not re.match(last_name_pattern, last_name) or not last_name.strip():
            messages.error(request, 'Last name must contain only letters (1-30 characters).')
            return redirect('user_profile')

        # Update user information
        user = request.user
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.save()

        messages.success(request, 'Profile updated successfully!')
        return redirect('user_profile')

    addresses = Address.objects.filter(user=request.user, is_deleted=False)
    referral, _ = Referral.objects.get_or_create(user=request.user)
    if not referral.referral_code:
        referral.save()

    # Get user wallet
    wallet = None
    try:
        from wallet.models import Wallet
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
    except Exception:
        pass

    # Orders count & recent orders
    orders_count = 0
    recent_orders = []
    try:
        from orders.models import Order
        orders_qs = Order.objects.filter(user=request.user)
        orders_count = orders_qs.count()
        recent_orders = orders_qs.order_by('-created_at')[:3]
    except Exception:
        pass

    # Wishlist count
    wishlist_count = 0
    try:
        from wishlist.models import WishlistItem
        wishlist_count = WishlistItem.objects.filter(wishlist__user=request.user).count()
    except Exception:
        pass

    # Referrals count
    referrals_count = Referral.objects.filter(referred_by=request.user).count()

    context = {
        'addresses': addresses,
        'referral': referral,
        'wallet': wallet,
        'orders_count': orders_count,
        'recent_orders': recent_orders,
        'wishlist_count': wishlist_count,
        'referrals_count': referrals_count,
    }
    return render(request, 'user/profile.html', context)


@login_required
@require_POST
def update_profile_picture(request):
    try:
        action = request.POST.get('action')
        profile, created = Profile.objects.get_or_create(user=request.user)

        # Handle avatar removal
        if action == 'delete':
            if profile.avatar:
                profile.avatar.delete(save=False)
                profile.avatar = None
                profile.save()
            return JsonResponse({'success': True, 'action': 'deleted'})

        avatar = request.FILES.get('avatar')
        if not avatar:
            return JsonResponse({'success': False, 'error': 'No image file provided.'}, status=400)

        # Validate file size (max 5MB)
        if avatar.size > 5 * 1024 * 1024:
            return JsonResponse({'success': False, 'error': 'Image file size cannot exceed 5MB.'}, status=400)

        # Validate file extension
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
        import os
        ext = os.path.splitext(avatar.name)[1].lower()
        if ext not in valid_extensions:
            return JsonResponse({'success': False, 'error': 'Invalid format. Allowed formats: JPG, JPEG, PNG, WEBP.'}, status=400)

        # Validate MIME content type
        if hasattr(avatar, 'content_type') and avatar.content_type not in ['image/jpeg', 'image/png', 'image/webp']:
            return JsonResponse({'success': False, 'error': 'File is not a valid image format.'}, status=400)

        # Delete old avatar if it exists
        if profile.avatar:
            profile.avatar.delete(save=False)

        # Save new avatar
        profile.avatar = avatar
        profile.save()

        return JsonResponse({'success': True, 'avatar_url': profile.avatar.url})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


"""
VIEW ADDRESS PAGE
"""
@login_required
def view_addresses(request):
    addresses = Address.objects.filter(user=request.user, is_deleted=False)

    # If no address is marked as default, set the oldest address as default
    if not addresses.filter(is_default=True).exists() and addresses.exists():
        oldest_address = addresses.order_by('id').first()
        oldest_address.is_default = True
        oldest_address.save()

    orders_count = 0
    try:
        from orders.models import Order
        orders_count = Order.objects.filter(user=request.user).count()
    except Exception:
        pass

    wallet = None
    try:
        from wallet.models import Wallet
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
    except Exception:
        pass

    wishlist_count = 0
    try:
        from wishlist.models import WishlistItem
        wishlist_count = WishlistItem.objects.filter(wishlist__user=request.user).count()
    except Exception:
        pass

    return render(request, 'user/address.html', {
        'addresses': addresses,
        'orders_count': orders_count,
        'wallet': wallet,
        'wishlist_count': wishlist_count,
    })


"""
DEFAULT ADDRESS SETTING
"""
@login_required
def set_default_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)

    # Set the selected address as default
    address.is_default = True
    address.save()

    messages.success(request, "Default address updated successfully")
    return redirect('addresses')


"""
NEW ADDRESS ADDING
"""
@login_required
def add_address(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        address = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        country = request.POST.get('country', '').strip()
        postcode = request.POST.get('postcode', '').strip()
        phone = request.POST.get('phone', '').strip()
        is_default = request.POST.get('is_default') in ['true', 'on', '1']

        # Validate fields
        errors = validate_address_fields(name, address, city, state, country, postcode, phone)

        # Check for duplicate address
        if not errors and Address.objects.filter(
            user=request.user,
            name=name,
            address=address,
            city=city,
            state=state,
            country=country,
            postcode=postcode,
            phone=phone,
            is_deleted=False
        ).exists():
            errors.append("This address already exists.")

        if errors:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': errors}, status=400)
            return render(request, 'user/add_address.html', {
                'errors': errors,
                'data': {
                    'name': name,
                    'address': address,
                    'city': city,
                    'state': state,
                    'country': country,
                    'postcode': postcode,
                    'phone': phone,
                    'is_default': is_default,
                },
            })

        # If it's user's first active address, make it default
        has_existing_addresses = Address.objects.filter(user=request.user, is_deleted=False).exists()
        if not has_existing_addresses:
            is_default = True

        new_addr = Address.objects.create(
            user=request.user,
            name=name,
            address=address,
            city=city,
            state=state,
            country=country,
            postcode=postcode,
            phone=phone,
            is_default=is_default,
        )
        messages.success(request, 'Address added successfully!')
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'address_id': new_addr.id})
        return redirect('addresses')

    return render(request, 'user/add_address.html')


"""
EDIT ALREADY HAVING ADDRESS
"""
@login_required
def edit_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user, is_deleted=False)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        address_line = request.POST.get('address', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        country = request.POST.get('country', '').strip()
        postcode = request.POST.get('postcode', '').strip()
        phone = request.POST.get('phone', '').strip()
        is_default = request.POST.get('is_default') in ['true', 'on', '1']

        # Validate fields
        errors = validate_address_fields(name, address_line, city, state, country, postcode, phone)

        # Check for duplicate address (excluding current address)
        if not errors and Address.objects.filter(
            user=request.user,
            name=name,
            address=address_line,
            city=city,
            state=state,
            country=country,
            postcode=postcode,
            phone=phone,
            is_deleted=False
        ).exclude(id=address_id).exists():
            errors.append("This address already exists.")

        if errors:
            return render(request, 'user/edit_address.html', {
                'errors': errors,
                'data': {
                    'id': address_id,
                    'name': name,
                    'address': address_line,
                    'city': city,
                    'state': state,
                    'country': country,
                    'postcode': postcode,
                    'phone': phone,
                    'is_default': is_default,
                },
                'address': address,
            })

        address.name = name
        address.address = address_line
        address.city = city
        address.state = state
        address.country = country
        address.postcode = postcode
        address.phone = phone
        if is_default:
            address.is_default = True
        address.save()

        messages.success(request, "Address updated successfully!")
        return redirect('addresses')

    return render(request, 'user/edit_address.html', {'address': address})


"""
DELETING ADDRESS
"""
@login_required
def delete_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)

    if request.method == 'POST':
        was_default = address.is_default
        address.delete()

        # If deleted address was default, promote oldest remaining address
        remaining = Address.objects.filter(user=request.user, is_deleted=False)
        if was_default and remaining.exists():
            new_default = remaining.first()
            new_default.is_default = True
            new_default.save()

        messages.success(request, 'Address deleted successfully!')
        return redirect('addresses')

    return redirect('addresses')


"""
CHANGE PASSWORD
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


@login_required
def change_password(request):
    referer = request.META.get('HTTP_REFERER', '')
    redirect_target = 'user_profile' if 'user-profile' in referer else 'change_password'

    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not current_password:
            messages.error(request, 'Current password is required.')
            return redirect(redirect_target)

        if not new_password:
            messages.error(request, 'New password is required.')
            return redirect(redirect_target)

        if not confirm_password:
            messages.error(request, 'Please confirm your new password.')
            return redirect(redirect_target)

        user = authenticate(username=request.user.username, password=current_password)
        if not user:
            # Check by email in case username was mapped
            user = authenticate(username=request.user.email, password=current_password)
            if not user:
                messages.error(request, 'The current password you entered is incorrect.')
                return redirect(redirect_target)

        if current_password == new_password:
            messages.error(request, 'New password cannot be the same as your current password.')
            return redirect(redirect_target)

        if new_password != confirm_password:
            messages.error(request, 'The new password and confirm password do not match.')
            return redirect(redirect_target)

        is_valid, error_message = validate_password(new_password)
        if not is_valid:
            messages.error(request, error_message)
            return redirect(redirect_target)

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Password changed successfully!')
        return redirect('user_profile')

    return render(request, 'user/change_password.html')


"""
CHANGE EMAIL FUNCTION
"""
@login_required
def change_email(request):
    if request.method == 'POST':
        new_email = request.POST.get('new_email', '').strip()

        if not new_email:
            messages.error(request, 'Email address is required.')
            return render(request, 'user/change_email.html')

        if len(new_email) > 100:
            messages.error(request, 'Email address cannot exceed 100 characters.')
            return render(request, 'user/change_email.html')

        # Validate email format
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, new_email):
            messages.error(request, 'Invalid email address format. Please enter a valid email (e.g. name@example.com).')
            return render(request, 'user/change_email.html')

        if request.user.email and new_email.lower() == request.user.email.lower():
            messages.error(request, 'New email cannot be the same as your current email address.')
            return render(request, 'user/change_email.html')

        # Check if the email is already in use by another user
        if User.objects.exclude(pk=request.user.pk).filter(email__iexact=new_email).exists() or \
           User.objects.exclude(pk=request.user.pk).filter(username__iexact=new_email).exists():
            messages.error(request, 'This email is already registered with another account.')
            return render(request, 'user/change_email.html')

        # Generate OTP and store it in the session
        otp = ''.join(random.choices(string.digits, k=6))
        request.session['new_email'] = new_email
        request.session['otp'] = otp

        # Send OTP to the new email
        subject = 'Email Change Verification - Jamilah'
        message = f'Hello {request.user.first_name or request.user.username},\n\nYour 6-digit OTP code to verify and update your email address is: {otp}\n\nDo not share this code with anyone.\n\nThank you,\nJamilah Team'
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
        try:
            send_mail(subject, message, from_email, [new_email], fail_silently=False)
        except Exception as e:
            messages.error(request, 'Failed to send OTP verification email. Please try again.')
            return render(request, 'user/change_email.html')

        messages.success(request, 'An OTP has been sent to your new email. Please verify to complete the process.')
        return redirect('verify_email')

    return render(request, 'user/change_email.html')


"""
EMAIL VERIFICATION
"""
@login_required
def verify_email(request):
    session_otp = request.session.get('otp')
    new_email = request.session.get('new_email')

    if not session_otp or not new_email:
        messages.error(request, 'Session expired or invalid. Please restart the email change process.')
        return redirect('change_email')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()

        if not entered_otp or not entered_otp.isdigit() or len(entered_otp) != 6:
            messages.error(request, 'Please enter a valid 6-digit numeric OTP.')
            return render(request, 'user/verify_email.html', {'new_email': new_email})

        # Check if OTP matches
        if entered_otp == session_otp:
            user = request.user
            user.email = new_email
            user.save()

            # Clear session variables
            request.session.pop('otp', None)
            request.session.pop('new_email', None)

            messages.success(request, 'Email updated successfully!')
            return redirect('user_profile')

        # Handle invalid OTP
        messages.error(request, 'Invalid OTP code. Please check and try again.')
        return render(request, 'user/verify_email.html', {'new_email': new_email})

    return render(request, 'user/verify_email.html', {'new_email': new_email})
