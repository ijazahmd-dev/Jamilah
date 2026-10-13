from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import ProductOffer, CategoryOffer
from django.core.paginator import Paginator
from django.contrib import messages
from products.models import Product
from category.models import Category
from django.views.decorators.cache import never_cache
from functools import wraps
from decimal import Decimal, InvalidOperation
from django.db.models import Q, Avg, Count
from django.http import JsonResponse


"""
ADMIN AUTHENTICATION HELPERS
"""
def is_admin(user):
    return user.is_authenticated and user.is_superuser


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        if not request.user.is_staff:
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


"""
OFFER MANAGEMENT DASHBOARD HUB
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def offer_management(request):
    all_product_offers = ProductOffer.objects.select_related('product', 'product__category').all()
    all_category_offers = CategoryOffer.objects.select_related('category').all()

    total_product_offers = all_product_offers.count()
    active_product_offers = all_product_offers.filter(is_active=True).count()
    total_category_offers = all_category_offers.count()
    active_category_offers = all_category_offers.filter(is_active=True).count()

    # Calculate previews for recent offers
    recent_product_offers = all_product_offers.order_by('-created_at')[:6]
    for po in recent_product_offers:
        po.final_price = round(po.product.price * (1 - po.discount_percentage / Decimal('100.00')), 2)
        po.savings = round(po.product.price - po.final_price, 2)

    recent_category_offers = all_category_offers.order_by('-created_at')[:6]
    for co in recent_category_offers:
        co.product_count = Product.objects.filter(category=co.category, is_listed=True).count()

    # Max discounts
    max_po = all_product_offers.filter(is_active=True).order_by('-discount_percentage').first()
    max_co = all_category_offers.filter(is_active=True).order_by('-discount_percentage').first()

    stats = {
        'total_product_offers': total_product_offers,
        'active_product_offers': active_product_offers,
        'total_category_offers': total_category_offers,
        'active_category_offers': active_category_offers,
        'total_active_offers': active_product_offers + active_category_offers,
        'max_product_discount': max_po.discount_percentage if max_po else Decimal('0.00'),
        'max_category_discount': max_co.discount_percentage if max_co else Decimal('0.00'),
    }

    return render(request, 'admin/offer_management.html', {
        'stats': stats,
        'recent_product_offers': recent_product_offers,
        'recent_category_offers': recent_category_offers,
    })


"""
PRODUCT OFFER LISTING
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def product_offer_list(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    offers_qs = ProductOffer.objects.select_related('product', 'product__category').all().order_by('-created_at')

    if query:
        offers_qs = offers_qs.filter(
            Q(product__name__icontains=query) |
            Q(product__category__category_name__icontains=query)
        )

    if status_filter == 'active':
        offers_qs = offers_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        offers_qs = offers_qs.filter(is_active=False)

    # Compute KPI statistics
    all_po = ProductOffer.objects.all()
    total_offers = all_po.count()
    active_offers = all_po.filter(is_active=True).count()
    inactive_offers = all_po.filter(is_active=False).count()
    avg_discount = all_po.aggregate(avg=Avg('discount_percentage'))['avg'] or 0

    stats = {
        'total_offers': total_offers,
        'active_offers': active_offers,
        'inactive_offers': inactive_offers,
        'avg_discount': round(avg_discount, 1),
    }

    paginator = Paginator(offers_qs, 10)
    page_number = request.GET.get('page', 1)
    product_offers = paginator.get_page(page_number)

    # Annotate price calculations on page items
    for item in product_offers:
        item.final_price = round(item.product.price * (1 - item.discount_percentage / Decimal('100.00')), 2)
        item.savings = round(item.product.price - item.final_price, 2)

    return render(request, 'admin/product_offer_list.html', {
        'product_offers': product_offers,
        'query': query,
        'status_filter': status_filter,
        'stats': stats,
    })


"""
ADD PRODUCT OFFER
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def add_product_offer(request):
    # Only show products without an existing product offer
    existing_product_ids = ProductOffer.objects.values_list('product_id', flat=True)
    products = Product.objects.filter(is_listed=True).exclude(id__in=existing_product_ids).order_by('name')

    selected_product_id = request.GET.get('product_id', '')

    if request.method == 'POST':
        product_id = request.POST.get('product', '').strip()
        discount_percentage_str = request.POST.get('discount_percentage', '').strip()

        if not product_id or not discount_percentage_str:
            messages.error(request, 'Please select a product and provide a discount percentage.')
            return render(request, 'admin/add_product_offer.html', {
                'products': products,
                'selected_product_id': product_id,
                'discount_percentage': discount_percentage_str,
            })

        try:
            discount_percentage = Decimal(discount_percentage_str)
            if discount_percentage < Decimal('1.00') or discount_percentage > Decimal('90.00'):
                messages.error(request, 'Discount percentage must be between 1% and 90%.')
                return render(request, 'admin/add_product_offer.html', {
                    'products': products,
                    'selected_product_id': product_id,
                    'discount_percentage': discount_percentage_str,
                })
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid discount percentage. Please enter a valid number.')
            return render(request, 'admin/add_product_offer.html', {
                'products': products,
                'selected_product_id': product_id,
                'discount_percentage': discount_percentage_str,
            })

        product = get_object_or_404(Product, id=product_id)
        if ProductOffer.objects.filter(product=product).exists():
            messages.error(request, f"An offer already exists for '{product.name}'.")
            return redirect('product_offer_list')

        ProductOffer.objects.create(
            product=product,
            discount_percentage=discount_percentage,
            is_active=True
        )
        messages.success(request, f"Product offer of {discount_percentage}% created for '{product.name}'.")
        return redirect('product_offer_list')

    return render(request, 'admin/add_product_offer.html', {
        'products': products,
        'selected_product_id': selected_product_id,
    })


"""
EDIT PRODUCT OFFER
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def edit_product_offer(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product_offer = get_object_or_404(ProductOffer, product=product)

    if request.method == 'POST':
        discount_percentage_str = request.POST.get('discount_percentage', '').strip()
        is_active_val = request.POST.get('is_active') == 'on'

        if not discount_percentage_str:
            messages.error(request, 'Discount percentage is required.')
            return render(request, 'admin/edit_product_offer.html', {
                'product_offer': product_offer,
                'product': product,
            })

        try:
            discount_percentage = Decimal(discount_percentage_str)
            if discount_percentage < Decimal('1.00') or discount_percentage > Decimal('90.00'):
                messages.error(request, 'Discount percentage must be between 1% and 90%.')
                return render(request, 'admin/edit_product_offer.html', {
                    'product_offer': product_offer,
                    'product': product,
                })
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid discount percentage. Please enter a valid number.')
            return render(request, 'admin/edit_product_offer.html', {
                'product_offer': product_offer,
                'product': product,
            })

        product_offer.discount_percentage = discount_percentage
        product_offer.is_active = is_active_val
        product_offer.save()
        messages.success(request, f"Product offer for '{product.name}' updated successfully.")
        return redirect('product_offer_list')

    # Calculate preview
    current_final_price = round(product.price * (1 - product_offer.discount_percentage / Decimal('100.00')), 2)
    current_savings = round(product.price - current_final_price, 2)

    return render(request, 'admin/edit_product_offer.html', {
        'product_offer': product_offer,
        'product': product,
        'current_final_price': current_final_price,
        'current_savings': current_savings,
    })


"""
TOGGLE PRODUCT OFFER ACTIVE STATUS
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def toggle_product_offer(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product_offer = get_object_or_404(ProductOffer, product=product)
    product_offer.is_active = not product_offer.is_active
    product_offer.save()
    status_text = "activated" if product_offer.is_active else "deactivated"
    msg = f"Product offer for '{product.name}' {status_text} successfully."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
        return JsonResponse({'success': True, 'message': msg, 'is_active': product_offer.is_active})

    messages.success(request, msg)
    return redirect('product_offer_list')


"""
DELETE PRODUCT OFFER
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def delete_product_offer(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product_offer = get_object_or_404(ProductOffer, product=product)
    product_name = product.name
    product_offer.delete()
    msg = f"Product offer for '{product_name}' deleted successfully."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
        return JsonResponse({'success': True, 'message': msg})

    messages.success(request, msg)
    return redirect('product_offer_list')


"""
CATEGORY OFFER LISTING
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def category_offer_list(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    offers_qs = CategoryOffer.objects.select_related('category').all().order_by('-created_at')

    if query:
        offers_qs = offers_qs.filter(category__category_name__icontains=query)

    if status_filter == 'active':
        offers_qs = offers_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        offers_qs = offers_qs.filter(is_active=False)

    # Compute KPI statistics
    all_co = CategoryOffer.objects.all()
    total_offers = all_co.count()
    active_offers = all_co.filter(is_active=True).count()
    inactive_offers = all_co.filter(is_active=False).count()
    avg_discount = all_co.aggregate(avg=Avg('discount_percentage'))['avg'] or 0

    stats = {
        'total_offers': total_offers,
        'active_offers': active_offers,
        'inactive_offers': inactive_offers,
        'avg_discount': round(avg_discount, 1),
    }

    paginator = Paginator(offers_qs, 10)
    page_number = request.GET.get('page', 1)
    category_offers = paginator.get_page(page_number)

    # Annotate product counts
    for item in category_offers:
        item.product_count = Product.objects.filter(category=item.category, is_listed=True).count()

    return render(request, 'admin/category_offer_list.html', {
        'category_offers': category_offers,
        'query': query,
        'status_filter': status_filter,
        'stats': stats,
    })


"""
ADD CATEGORY OFFER
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def add_category_offer(request):
    # Only show categories without an existing category offer
    existing_category_ids = CategoryOffer.objects.values_list('category_id', flat=True)
    categories = Category.objects.filter(is_listed=True).exclude(id__in=existing_category_ids).order_by('category_name')

    selected_category_id = request.GET.get('category_id', '')

    if request.method == 'POST':
        category_id = request.POST.get('category', '').strip()
        discount_percentage_str = request.POST.get('discount_percentage', '').strip()

        if not category_id or not discount_percentage_str:
            messages.error(request, 'Please select a category and provide a discount percentage.')
            return render(request, 'admin/add_category_offer.html', {
                'categories': categories,
                'selected_category_id': category_id,
                'discount_percentage': discount_percentage_str,
            })

        try:
            discount_percentage = Decimal(discount_percentage_str)
            if discount_percentage < Decimal('1.00') or discount_percentage > Decimal('90.00'):
                messages.error(request, 'Discount percentage must be between 1% and 90%.')
                return render(request, 'admin/add_category_offer.html', {
                    'categories': categories,
                    'selected_category_id': category_id,
                    'discount_percentage': discount_percentage_str,
                })
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid discount percentage. Please enter a valid number.')
            return render(request, 'admin/add_category_offer.html', {
                'categories': categories,
                'selected_category_id': category_id,
                'discount_percentage': discount_percentage_str,
            })

        category = get_object_or_404(Category, id=category_id)
        if CategoryOffer.objects.filter(category=category).exists():
            messages.error(request, f"An offer already exists for '{category.category_name}'.")
            return redirect('category_offer_list')

        CategoryOffer.objects.create(
            category=category,
            discount_percentage=discount_percentage,
            is_active=True
        )
        messages.success(request, f"Category offer of {discount_percentage}% created for '{category.category_name}'.")
        return redirect('category_offer_list')

    return render(request, 'admin/add_category_offer.html', {
        'categories': categories,
        'selected_category_id': selected_category_id,
    })


"""
EDIT CATEGORY OFFER
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def edit_category_offer(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category_offer = get_object_or_404(CategoryOffer, category=category)

    if request.method == 'POST':
        discount_percentage_str = request.POST.get('discount_percentage', '').strip()
        is_active_val = request.POST.get('is_active') == 'on'

        if not discount_percentage_str:
            messages.error(request, 'Discount percentage is required.')
            return render(request, 'admin/edit_category_offer.html', {
                'category_offer': category_offer,
                'category': category,
            })

        try:
            discount_percentage = Decimal(discount_percentage_str)
            if discount_percentage < Decimal('1.00') or discount_percentage > Decimal('90.00'):
                messages.error(request, 'Discount percentage must be between 1% and 90%.')
                return render(request, 'admin/edit_category_offer.html', {
                    'category_offer': category_offer,
                    'category': category,
                })
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid discount percentage. Please enter a valid number.')
            return render(request, 'admin/edit_category_offer.html', {
                'category_offer': category_offer,
                'category': category,
            })

        category_offer.discount_percentage = discount_percentage
        category_offer.is_active = is_active_val
        category_offer.save()
        messages.success(request, f"Category offer for '{category.category_name}' updated successfully.")
        return redirect('category_offer_list')

    product_count = Product.objects.filter(category=category, is_listed=True).count()

    return render(request, 'admin/edit_category_offer.html', {
        'category_offer': category_offer,
        'category': category,
        'product_count': product_count,
    })


"""
TOGGLE CATEGORY OFFER ACTIVE STATUS
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def toggle_category_offer(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category_offer = get_object_or_404(CategoryOffer, category=category)
    category_offer.is_active = not category_offer.is_active
    category_offer.save()
    status_text = "activated" if category_offer.is_active else "deactivated"
    msg = f"Category offer for '{category.category_name}' {status_text} successfully."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
        return JsonResponse({'success': True, 'message': msg, 'is_active': category_offer.is_active})

    messages.success(request, msg)
    return redirect('category_offer_list')


"""
DELETE CATEGORY OFFER
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def delete_category_offer(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category_offer = get_object_or_404(CategoryOffer, category=category)
    category_name = category.category_name
    category_offer.delete()
    msg = f"Category offer for '{category_name}' deleted successfully."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
        return JsonResponse({'success': True, 'message': msg})

    messages.success(request, msg)
    return redirect('category_offer_list')