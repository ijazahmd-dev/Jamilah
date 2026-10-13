from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from coupons.models import Coupon,CouponUsage
from django.core.paginator import Paginator
from .forms import CouponForm
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
from functools import wraps
from django.views.decorators.cache import never_cache
from django.db.models import Q, Avg, Count, Max


# Create your views here.





###############################################USER SIDE START###############################################
"""
APPLY COUPON
"""
@login_required
def apply_coupon(request):
    if request.method == "POST":
        coupon_code = request.POST.get('coupon_code', '').strip().upper()
        if not coupon_code:
            messages.error(request, 'Please enter a coupon code.')
            return redirect('place_order')

        request.session['entered_coupon_code'] = coupon_code
        try:
            coupon = Coupon.objects.get(coupon_code=coupon_code, is_active=True)
            if coupon.is_valid():
                # Check if the user has already used this coupon
                if CouponUsage.objects.filter(user=request.user, coupon=coupon).exists():
                    messages.error(request, 'You have already used this coupon.')
                else:
                    # Check if the cart total meets the minimum purchase amount
                    cart_total = Decimal(request.session.get('cart_total', '0.00'))
                    if cart_total >= coupon.minimum_purchase_amount:
                        request.session['coupon_code'] = coupon_code
                        messages.success(request, 'Coupon applied successfully.')
                    else:
                        messages.error(request, f'Minimum purchase amount of ₹{coupon.minimum_purchase_amount} required to apply this coupon.')
            else:
                messages.error(request, 'This coupon is not valid or has expired.')
        except Coupon.DoesNotExist:
            messages.error(request, 'Invalid coupon code.')
    return redirect('place_order')





"""
REMOVE COUPON
"""
@login_required
def remove_coupon(request):
    if 'coupon_code' in request.session:
        del request.session['coupon_code']
        messages.success(request, 'Coupon removed successfully.')
    return redirect('place_order')





@login_required
def view_coupons(request):
    now = timezone.now().date()
    search_query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'all').strip().lower()

    # User's used coupon records
    usages = CouponUsage.objects.filter(user=request.user).select_related('coupon')
    used_coupon_ids = set(usages.values_list('coupon_id', flat=True))
    usage_dates = {u.coupon_id: u.used_at for u in usages}

    # All coupons query
    all_coupons_qs = Coupon.objects.all().order_by('-discount_percentage')
    if search_query:
        all_coupons_qs = all_coupons_qs.filter(
            Q(coupon_code__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Calculate counts and prepare items
    all_active_coupons = Coupon.objects.filter(is_active=True)
    available_count = 0
    used_count = len(used_coupon_ids)
    expiring_soon_count = 0
    total_coupons_count = all_active_coupons.count()

    coupon_list = []
    for coupon in all_coupons_qs:
        is_used = coupon.coupon_id in used_coupon_ids
        is_expired = coupon.valid_to < now
        is_upcoming = coupon.valid_from > now
        is_active = coupon.is_active and not is_expired and not is_upcoming

        days_remaining = (coupon.valid_to - now).days if not is_expired else 0
        is_expiring_soon = is_active and 0 <= days_remaining <= 7

        if is_active and not is_used:
            available_count += 1
        if is_expiring_soon and not is_used:
            expiring_soon_count += 1

        # Filter tabs
        if filter_type == 'available' and (not is_active or is_used):
            continue
        elif filter_type == 'used' and not is_used:
            continue
        elif filter_type == 'expiring' and (not is_expiring_soon or is_used):
            continue
        elif filter_type == 'expired' and not is_expired:
            continue

        coupon_list.append({
            'coupon': coupon,
            'is_used': is_used,
            'used_at': usage_dates.get(coupon.coupon_id),
            'is_expired': is_expired,
            'is_upcoming': is_upcoming,
            'is_active': is_active,
            'days_remaining': days_remaining,
            'is_expiring_soon': is_expiring_soon,
        })

    # Max discount across valid coupons
    max_discount_val = all_active_coupons.filter(valid_to__gte=now).aggregate(Max('discount_percentage'))['discount_percentage__max'] or 0

    context = {
        'coupon_list': coupon_list,
        'search_query': search_query,
        'filter_type': filter_type,
        'available_count': available_count,
        'used_count': used_count,
        'expiring_soon_count': expiring_soon_count,
        'total_coupons_count': total_coupons_count,
        'max_discount': max_discount_val,
    }
    return render(request, 'user/view_coupons.html', context)






















###############################################ADMIN SIDE START###############################################

"""
ADMIN CHECK
"""
def is_admin(user):
    return user.is_authenticated and user.is_superuser





def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')  # your admin login page route name
        if not request.user.is_staff:  # or use a custom user check like user.role == 'admin'
            return redirect('admin_login')  # or maybe a "permission denied" page
        return view_func(request, *args, **kwargs)
    return _wrapped_view




"""
COUPON LISTING IN THE ADMIN SIDE
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def coupon_list(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    coupons = Coupon.objects.all().order_by('-created_at')

    now = timezone.now().date()

    # Search filter
    if query:
        coupons = coupons.filter(
            Q(coupon_code__icontains=query) |
            Q(description__icontains=query)
        )

    # Status filter
    if status_filter == 'active':
        coupons = coupons.filter(is_active=True, valid_from__lte=now, valid_to__gte=now)
    elif status_filter == 'inactive':
        coupons = coupons.filter(is_active=False)
    elif status_filter == 'expired':
        coupons = coupons.filter(valid_to__lt=now)
    elif status_filter == 'upcoming':
        coupons = coupons.filter(valid_from__gt=now, is_active=True)

    # Calculate statistics for KPI cards
    all_coupons = Coupon.objects.all()
    total_coupons = all_coupons.count()
    active_coupons = all_coupons.filter(is_active=True, valid_from__lte=now, valid_to__gte=now).count()
    expired_coupons = all_coupons.filter(valid_to__lt=now).count()
    avg_discount = all_coupons.aggregate(avg=Avg('discount_percentage'))['avg'] or 0

    stats = {
        'total_coupons': total_coupons,
        'active_coupons': active_coupons,
        'expired_coupons': expired_coupons,
        'avg_discount': round(avg_discount, 1),
    }

    paginator = Paginator(coupons, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'coupons': page_obj,
        'query': query,
        'status_filter': status_filter,
        'stats': stats,
    }
    return render(request, 'admin/coupon_list.html', context)





"""
ADD NEW COUPON
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def add_coupon(request):
    if request.method == 'POST':
        form = CouponForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon added successfully.')
            return redirect('coupon_list')
    else:
        form = CouponForm()
    return render(request, 'admin/add_coupon.html', {'form': form})





"""
EDIT AVAILABLE COUPON
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def edit_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, coupon_id=coupon_id)
    if request.method == 'POST':
        form = CouponForm(request.POST, instance=coupon)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon updated successfully.')
            return redirect('coupon_list')
    else:
        form = CouponForm(instance=coupon)
    return render(request, 'admin/edit_coupon.html', {'form': form, 'coupon': coupon})







from django.http import JsonResponse

"""
COUPON ACTIVATE/DEACTIVATE
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def toggle_coupon_status(request, coupon_id):
    coupon = get_object_or_404(Coupon, coupon_id=coupon_id)
    coupon.is_active = not coupon.is_active
    coupon.save()
    action = "activated" if coupon.is_active else "deactivated"
    msg = f'Coupon "{coupon.coupon_code}" {action} successfully.'
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
        return JsonResponse({"success": True, "message": msg, "is_active": coupon.is_active})
    messages.success(request, msg)
    return redirect('coupon_list')




"""
COUPON DELETING
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def delete_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, coupon_id=coupon_id)
    code = coupon.coupon_code
    coupon.delete()
    msg = f'Coupon "{code}" deleted successfully.'
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
        return JsonResponse({"success": True, "message": msg})
    messages.success(request, msg)
    return redirect('coupon_list')


###############################################ADMIN SIDE END###############################################

