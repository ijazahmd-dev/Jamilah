from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from decimal import Decimal
import logging

from products.models import Product, ProductVariant
from .models import Wishlist, WishlistItem
from cart.models import Cart, CartItem
from offers.models import ProductOffer, CategoryOffer

logger = logging.getLogger(__name__)


@login_required
def wishlist_view(request):
    """Display the user's wishlist with rich filtering, search, and pricing."""
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

    search_query = request.GET.get('q', '').strip()
    stock_filter = request.GET.get('stock', 'all').strip().lower()
    sort_by = request.GET.get('sort', 'newest').strip().lower()

    # Base Query
    items_qs = WishlistItem.objects.filter(wishlist=wishlist).select_related(
        'product', 'product__category'
    ).prefetch_related(
        'product__images', 'product__variants'
    )

    if search_query:
        items_qs = items_qs.filter(
            Q(product__name__icontains=search_query) |
            Q(product__category__category_name__icontains=search_query)
        )

    # Decorate items with pricing, offers, and inventory
    decorated_items = []
    total_wishlist_value = Decimal('0.00')
    total_savings_value = Decimal('0.00')
    in_stock_count = 0
    out_of_stock_count = 0

    for item in items_qs:
        product = item.product
        first_image = product.images.first()
        item.first_image_url = first_image.image.url if first_image else None

        # Stock calculations across variants
        variants = product.variants.all()
        item.total_stock = sum(v.stock for v in variants) if variants.exists() else 0
        item.is_in_stock = item.total_stock > 0
        item.variant_colors = list(variants.values_list('color', flat=True).distinct())
        item.variant_sizes = list(variants.values_list('size', flat=True).distinct())

        if item.is_in_stock:
            in_stock_count += 1
        else:
            out_of_stock_count += 1

        # Offers calculation
        product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
        category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()
        final_price = product.price
        discount_percentage = Decimal('0.00')

        if product_offer and category_offer:
            final_price = min(
                product.price * (1 - product_offer.discount_percentage / 100),
                product.price * (1 - category_offer.discount_percentage / 100)
            )
            discount_percentage = max(product_offer.discount_percentage, category_offer.discount_percentage)
        elif product_offer:
            final_price = product.price * (1 - product_offer.discount_percentage / 100)
            discount_percentage = product_offer.discount_percentage
        elif category_offer:
            final_price = product.price * (1 - category_offer.discount_percentage / 100)
            discount_percentage = category_offer.discount_percentage

        item.final_price = final_price.quantize(Decimal('0.01'))
        item.has_discount = final_price < product.price
        item.discount_percentage = int(discount_percentage)
        item.savings = (product.price - final_price).quantize(Decimal('0.01'))

        total_wishlist_value += item.final_price
        total_savings_value += item.savings

        # Apply stock filter in-memory
        if stock_filter == 'in_stock' and not item.is_in_stock:
            continue
        elif stock_filter == 'out_of_stock' and item.is_in_stock:
            continue

        decorated_items.append(item)

    # Sorting
    if sort_by == 'price_low':
        decorated_items.sort(key=lambda x: x.final_price)
    elif sort_by == 'price_high':
        decorated_items.sort(key=lambda x: x.final_price, reverse=True)
    elif sort_by == 'name':
        decorated_items.sort(key=lambda x: x.product.name.lower())
    else:  # 'newest' default
        decorated_items.sort(key=lambda x: x.added_at, reverse=True)

    # Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(decorated_items, 8)
    try:
        wishlist_items_page = paginator.page(page)
    except PageNotAnInteger:
        wishlist_items_page = paginator.page(1)
    except EmptyPage:
        wishlist_items_page = paginator.page(paginator.num_pages)

    context = {
        'wishlist_items': wishlist_items_page,
        'total_items_count': items_qs.count(),
        'in_stock_count': in_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_wishlist_value': total_wishlist_value,
        'total_savings_value': total_savings_value,
        'search_query': search_query,
        'stock_filter': stock_filter,
        'sort_by': sort_by,
    }
    return render(request, 'user/wishlist.html', context)


@login_required
def add_to_wishlist(request, product_id):
    """Add or toggle a product in the user's wishlist."""
    product = get_object_or_404(Product, id=product_id)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

    existing_item = WishlistItem.objects.filter(wishlist=wishlist, product=product).first()
    is_toggle = request.POST.get('action') == 'toggle' or request.GET.get('action') == 'toggle'

    if existing_item and is_toggle:
        existing_item.delete()
        count = WishlistItem.objects.filter(wishlist=wishlist).count()
        return JsonResponse({
            "success": True,
            "action": "removed",
            "in_wishlist": False,
            "message": f"Removed '{product.name}' from wishlist",
            "wishlist_count": count
        })
    elif not existing_item:
        WishlistItem.objects.create(wishlist=wishlist, product=product)
        count = WishlistItem.objects.filter(wishlist=wishlist).count()
        return JsonResponse({
            "success": True,
            "action": "added",
            "in_wishlist": True,
            "message": f"Added '{product.name}' to wishlist!",
            "wishlist_count": count
        })
    else:
        count = WishlistItem.objects.filter(wishlist=wishlist).count()
        return JsonResponse({
            "success": True,
            "action": "already_exists",
            "in_wishlist": True,
            "message": "Product is already in your wishlist",
            "wishlist_count": count
        })


@login_required
def remove_from_wishlist(request, item_id):
    """Remove an item from the wishlist."""
    item = get_object_or_404(WishlistItem, id=item_id, wishlist__user=request.user)
    item.delete()
    remaining_count = WishlistItem.objects.filter(wishlist__user=request.user).count()

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': 'Product removed from wishlist.',
            'wishlist_count': remaining_count
        })

    messages.success(request, 'Product removed from wishlist.')
    return redirect('wishlist')


@login_required
def move_to_cart(request, item_id):
    """Move an item from the wishlist into the shopping cart."""
    wishlist_item = get_object_or_404(WishlistItem, id=item_id, wishlist__user=request.user)
    product = wishlist_item.product

    # Pick an available in-stock variant or fallback
    product_variant = product.variants.filter(stock__gt=0).first() or product.variants.first()
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

    if not product_variant:
        if is_ajax:
            return JsonResponse({'success': False, 'message': 'No variant found for this product.'})
        messages.error(request, 'No variant found for this product.')
        return redirect('wishlist')

    if product_variant.stock < 1:
        if is_ajax:
            return JsonResponse({'success': False, 'message': 'This product is currently out of stock.'})
        messages.error(request, 'This product is currently out of stock.')
        return redirect('wishlist')

    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, product_variant=product_variant)

    if not created:
        wishlist_item.delete()
        remaining_count = WishlistItem.objects.filter(wishlist__user=request.user).count()
        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': 'Product was already in cart. Removed from wishlist.',
                'wishlist_count': remaining_count
            })
        messages.info(request, 'Product was already in your cart and has been removed from your wishlist.')
        return redirect('wishlist')

    cart_item.quantity = 1
    cart_item.save()
    wishlist_item.delete()
    remaining_count = WishlistItem.objects.filter(wishlist__user=request.user).count()

    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': 'Product moved to cart successfully!',
            'wishlist_count': remaining_count
        })

    messages.success(request, 'Product moved to cart successfully.')
    return redirect('wishlist')


@login_required
def clear_wishlist(request):
    """Clear all items from the user's wishlist."""
    wishlist = Wishlist.objects.filter(user=request.user).first()
    if wishlist:
        wishlist.items.all().delete()

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
    if is_ajax:
        return JsonResponse({'success': True, 'message': 'Wishlist cleared successfully.', 'wishlist_count': 0})

    messages.success(request, 'Your wishlist has been cleared.')
    return redirect('wishlist')


@login_required
def move_all_to_cart(request):
    """Move all in-stock items from the wishlist into the shopping cart."""
    wishlist = Wishlist.objects.filter(user=request.user).first()
    if not wishlist or not wishlist.items.exists():
        messages.info(request, 'Your wishlist is empty.')
        return redirect('wishlist')

    cart, _ = Cart.objects.get_or_create(user=request.user)
    moved_count = 0
    items = wishlist.items.select_related('product').all()

    for item in items:
        product = item.product
        variant = product.variants.filter(stock__gt=0).first()
        if variant:
            cart_item, created = CartItem.objects.get_or_create(cart=cart, product_variant=variant)
            if created:
                cart_item.quantity = 1
                cart_item.save()
            item.delete()
            moved_count += 1

    if moved_count > 0:
        messages.success(request, f'{moved_count} in-stock item(s) moved to your cart!')
    else:
        messages.warning(request, 'No in-stock items were available to move.')

    return redirect('wishlist')
