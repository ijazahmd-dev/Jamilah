from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Cart, CartItem
from products.models import Product, ProductVariant
from django.contrib import messages
from decimal import Decimal
import logging
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from offers.models import ProductOffer, CategoryOffer
from wishlist.models import Wishlist, WishlistItem

logger = logging.getLogger(__name__)


def calculate_cart_totals(user):
    """Helper function to calculate cart totals and free shipping progress."""
    cart, _ = Cart.objects.get_or_create(user=user)
    cart_items = cart.items.filter(product_variant__product__is_listed=True).select_related(
        'product_variant', 'product_variant__product', 'product_variant__product__category'
    )

    total_listed_price = Decimal('0.00')
    total_offer_price = Decimal('0.00')
    total_items_count = 0
    out_of_stock_count = 0

    for item in cart_items:
        product = item.product_variant.product
        product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
        category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()

        if product_offer and category_offer:
            final_price = min(
                product.price * (1 - product_offer.discount_percentage / 100),
                product.price * (1 - category_offer.discount_percentage / 100)
            )
        elif product_offer:
            final_price = product.price * (1 - product_offer.discount_percentage / 100)
        elif category_offer:
            final_price = product.price * (1 - category_offer.discount_percentage / 100)
        else:
            final_price = product.price

        qty = Decimal(str(item.quantity))
        subtotal = final_price * qty
        listed_subtotal = product.price * qty

        total_listed_price += listed_subtotal
        total_offer_price += subtotal
        total_items_count += item.quantity

        if item.quantity > item.product_variant.stock:
            out_of_stock_count += 1

    discounted_amount = total_listed_price - total_offer_price
    free_delivery_threshold = Decimal('1000.00')
    is_free_delivery = total_offer_price >= free_delivery_threshold
    delivery_charge = Decimal('40.00') if (not is_free_delivery and total_items_count > 0) else Decimal('0.00')
    grand_total = total_offer_price + delivery_charge

    amount_needed_for_free_delivery = max(Decimal('0.00'), free_delivery_threshold - total_offer_price) if not is_free_delivery else Decimal('0.00')
    if is_free_delivery:
        free_delivery_progress = 100
    elif free_delivery_threshold > Decimal('0.00'):
        free_delivery_progress = min(100, int((total_offer_price / free_delivery_threshold) * 100))
    else:
        free_delivery_progress = 100

    return {
        'cart_count': cart_items.count(),
        'total_units': total_items_count,
        'total_listed_price': total_listed_price,
        'total_offer_price': total_offer_price,
        'discounted_amount': discounted_amount,
        'delivery_charge': delivery_charge,
        'grand_total': grand_total,
        'free_delivery_threshold': free_delivery_threshold,
        'amount_needed_for_free_delivery': amount_needed_for_free_delivery,
        'free_delivery_progress': free_delivery_progress,
        'is_free_delivery': is_free_delivery,
        'has_out_of_stock': out_of_stock_count > 0,
        'is_empty': cart_items.count() == 0,
    }


@login_required
def cart_view(request):
    """Display the user's cart with enriched offer information and stock statuses."""
    if not request.user.is_authenticated:
        return render(request, 'user/cart.html', {'cart_empty': True, 'message': 'Your cart is empty. Please log in to view items.'})

    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.all().order_by('id').filter(product_variant__product__is_listed=True).select_related(
        'product_variant', 'product_variant__product', 'product_variant__product__category'
    )

    out_of_stock_items = []
    enriched_items = []

    for item in cart_items:
        product = item.product_variant.product
        product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
        category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()

        # Calculate final price
        if product_offer and category_offer:
            final_price = min(
                product.price * (1 - product_offer.discount_percentage / 100),
                product.price * (1 - category_offer.discount_percentage / 100)
            )
        elif product_offer:
            final_price = product.price * (1 - product_offer.discount_percentage / 100)
        elif category_offer:
            final_price = product.price * (1 - category_offer.discount_percentage / 100)
        else:
            final_price = product.price

        qty = Decimal(str(item.quantity))
        item.unit_listed_price = product.price
        item.unit_offer_price = final_price
        item.has_discount = product.price > final_price
        if item.has_discount and product.price > 0:
            item.discount_percentage = round(((product.price - final_price) / product.price) * 100)
        else:
            item.discount_percentage = 0

        item.subtotal = final_price * qty
        item.subtotal_listed_price = product.price * qty
        item.savings = (product.price - final_price) * qty

        item.is_out_of_stock = item.product_variant.stock < item.quantity
        item.is_low_stock = (0 < item.product_variant.stock <= 3) and not item.is_out_of_stock
        item.stock_available = item.product_variant.stock
        item.max_selectable = min(5, item.product_variant.stock)
        item.can_increase = item.quantity < min(5, item.product_variant.stock)
        item.can_decrease = item.quantity > 1

        if item.is_out_of_stock:
            out_of_stock_items.append({
                'product_name': product.name,
                'variant': f"{item.product_variant.color} / {item.product_variant.size}",
                'available_stock': item.product_variant.stock,
            })
        enriched_items.append(item)

    totals = calculate_cart_totals(request.user)

    context = {
        'cart_items': enriched_items,
        'cart_empty': len(enriched_items) == 0,
        'out_of_stock_items': out_of_stock_items,
        'has_out_of_stock': len(out_of_stock_items) > 0,
        'cart_count': totals['cart_count'],
        'total_units': totals['total_units'],
        'total_listed_price': totals['total_listed_price'],
        'total_offer_price': totals['total_offer_price'],
        'discounted_amount': totals['discounted_amount'],
        'delivery_charge': totals['delivery_charge'],
        'grand_total': totals['grand_total'],
        'free_delivery_threshold': totals['free_delivery_threshold'],
        'amount_needed_for_free_delivery': totals['amount_needed_for_free_delivery'],
        'free_delivery_progress': totals['free_delivery_progress'],
        'is_free_delivery': totals['is_free_delivery'],
    }

    return render(request, 'user/cart.html', context)


def add_to_cart(request):
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'login_required': True,
            'error': 'Please log in to add items to your cart.',
            'redirect_url': '/login/'
        })
    product_id = request.POST.get('product_id', '').strip()
    color = request.POST.get('color', '').strip()
    size = request.POST.get('size', '').strip()
    quantity_raw = request.POST.get('quantity', 1)

    try:
        quantity = int(str(quantity_raw).strip())
        if quantity < 1 or quantity > 5:
            return JsonResponse({'success': False, 'error': 'Quantity must be between 1 and 5 units.'})
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Quantity must be a valid number between 1 and 5.'})

    logger.info(f"Adding to cart: product_id={product_id}, color={color}, size={size}, quantity={quantity}")

    try:
        product = Product.objects.get(id=product_id, is_listed=True)

        variants = ProductVariant.objects.filter(product=product)
        if not variants.exists():
            logger.error(f"No variants available for product_id={product_id}")
            return JsonResponse({'success': False, 'error': 'No stock available for this product.'})

        product_variant = None
        if color and size:
            product_variant = variants.filter(color__iexact=color, size__iexact=size).first()
        if not product_variant:
            product_variant = variants.first()

        if not product_variant:
            logger.error(f"No valid variant found for product_id={product_id}, color={color}, size={size}")
            return JsonResponse({'success': False, 'error': 'No valid variant found for this product.'})

        if product_variant.stock <= 0:
            logger.error(f"Product variant out of stock: variant_id={product_variant.id}")
            return JsonResponse({'success': False, 'error': 'This product is out of stock.'})

        if quantity > product_variant.stock:
            return JsonResponse({'success': False, 'error': f'Only {product_variant.stock} units available in stock.'})

        # Add to cart or update existing cart item
        cart, _ = Cart.objects.get_or_create(user=request.user)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, 
            product_variant=product_variant,
            defaults={'quantity': quantity}
        )
        if not created:
            if cart_item.quantity >= 5:
                return JsonResponse({'success': False, 'error': 'Maximum limit of 5 units already reached for this item in your cart.'})
            new_qty = min(cart_item.quantity + quantity, product_variant.stock, 5)
            cart_item.quantity = new_qty
            cart_item.save()
            return JsonResponse({'success': True, 'message': 'Cart updated with selected quantity!', 'already_in_cart': True})

        logger.info(f"Item added to cart: product_id={product_id}, variant_id={product_variant.id}, quantity={quantity}")
        return JsonResponse({'success': True, 'message': 'Item added to cart successfully.'})

    except Product.DoesNotExist:
        logger.error(f"Product not found: product_id={product_id}")
        return JsonResponse({'success': False, 'error': 'Product not found or unavailable.'})
    except Exception as e:
        logger.error(f"Error adding to cart: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def update_cart(request, item_id, action):
    """Update item quantity in cart via AJAX and return updated calculation breakdown."""
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        product_variant = cart_item.product_variant
        product = product_variant.product

        MAX_QUANTITY = 5

        if action == "increase":
            if cart_item.quantity >= MAX_QUANTITY:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Maximum limit of {MAX_QUANTITY} units reached for this item.'
                }, status=400)
            elif cart_item.quantity + 1 > product_variant.stock:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Cannot exceed available stock ({product_variant.stock} available).'
                }, status=400)
            cart_item.quantity += 1
        elif action == "decrease":
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Minimum quantity is 1 unit. Click remove to delete this item.'
                }, status=400)
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid action requested.'}, status=400)

        cart_item.save()

        # Recalculate item unit and subtotal
        product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
        category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()
        if product_offer and category_offer:
            final_price = min(
                product.price * (1 - product_offer.discount_percentage / 100),
                product.price * (1 - category_offer.discount_percentage / 100)
            )
        elif product_offer:
            final_price = product.price * (1 - product_offer.discount_percentage / 100)
        elif category_offer:
            final_price = product.price * (1 - category_offer.discount_percentage / 100)
        else:
            final_price = product.price

        item_subtotal = final_price * Decimal(str(cart_item.quantity))
        totals = calculate_cart_totals(request.user)

        return JsonResponse({
            'status': 'success',
            'message': 'Cart quantity updated.',
            'item': {
                'id': cart_item.id,
                'quantity': cart_item.quantity,
                'unit_price': float(final_price),
                'unit_price_formatted': f"₹{final_price:,.2f}",
                'subtotal': float(item_subtotal),
                'subtotal_formatted': f"₹{item_subtotal:,.2f}",
                'can_increase': cart_item.quantity < min(MAX_QUANTITY, product_variant.stock),
                'can_decrease': cart_item.quantity > 1,
            },
            'totals': {
                'cart_count': totals['cart_count'],
                'total_units': totals['total_units'],
                'total_listed_price': float(totals['total_listed_price']),
                'total_listed_price_formatted': f"₹{totals['total_listed_price']:,.2f}",
                'total_offer_price': float(totals['total_offer_price']),
                'total_offer_price_formatted': f"₹{totals['total_offer_price']:,.2f}",
                'discounted_amount': float(totals['discounted_amount']),
                'discounted_amount_formatted': f"₹{totals['discounted_amount']:,.2f}",
                'delivery_charge': float(totals['delivery_charge']),
                'delivery_charge_display': "FREE" if totals['is_free_delivery'] else f"₹{totals['delivery_charge']:,.2f}",
                'grand_total': float(totals['grand_total']),
                'grand_total_formatted': f"₹{totals['grand_total']:,.2f}",
                'free_delivery_progress': totals['free_delivery_progress'],
                'amount_needed_for_free_delivery': float(totals['amount_needed_for_free_delivery']),
                'amount_needed_formatted': f"₹{totals['amount_needed_for_free_delivery']:,.2f}",
                'is_free_delivery': totals['is_free_delivery'],
                'has_out_of_stock': totals['has_out_of_stock'],
                'is_empty': totals['is_empty'],
            }
        })
    except CartItem.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Item not found in cart.'}, status=404)
    except Exception as e:
        logger.error(f"Error in update_cart: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@require_POST
def remove_from_cart(request, item_id):
    """Remove item from cart via AJAX and return updated totals."""
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        product_name = cart_item.product_variant.product.name
        cart_item.delete()
        totals = calculate_cart_totals(request.user)

        return JsonResponse({
            'status': 'success',
            'message': f'"{product_name}" removed from cart.',
            'totals': {
                'cart_count': totals['cart_count'],
                'total_units': totals['total_units'],
                'total_listed_price': float(totals['total_listed_price']),
                'total_listed_price_formatted': f"₹{totals['total_listed_price']:,.2f}",
                'total_offer_price': float(totals['total_offer_price']),
                'total_offer_price_formatted': f"₹{totals['total_offer_price']:,.2f}",
                'discounted_amount': float(totals['discounted_amount']),
                'discounted_amount_formatted': f"₹{totals['discounted_amount']:,.2f}",
                'delivery_charge': float(totals['delivery_charge']),
                'delivery_charge_display': "FREE" if totals['is_free_delivery'] else f"₹{totals['delivery_charge']:,.2f}",
                'grand_total': float(totals['grand_total']),
                'grand_total_formatted': f"₹{totals['grand_total']:,.2f}",
                'free_delivery_progress': totals['free_delivery_progress'],
                'amount_needed_for_free_delivery': float(totals['amount_needed_for_free_delivery']),
                'amount_needed_formatted': f"₹{totals['amount_needed_for_free_delivery']:,.2f}",
                'is_free_delivery': totals['is_free_delivery'],
                'has_out_of_stock': totals['has_out_of_stock'],
                'is_empty': totals['is_empty'],
            }
        })
    except CartItem.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Item not found in cart.'}, status=404)
    except Exception as e:
        logger.error(f"Error in remove_from_cart: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@require_POST
def move_to_wishlist(request, item_id):
    """Move an item from cart to wishlist seamlessly."""
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        product = cart_item.product_variant.product
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        WishlistItem.objects.get_or_create(wishlist=wishlist, product=product)
        cart_item.delete()
        totals = calculate_cart_totals(request.user)

        return JsonResponse({
            'status': 'success',
            'message': f'"{product.name}" moved to your wishlist.',
            'totals': {
                'cart_count': totals['cart_count'],
                'total_units': totals['total_units'],
                'total_listed_price': float(totals['total_listed_price']),
                'total_listed_price_formatted': f"₹{totals['total_listed_price']:,.2f}",
                'total_offer_price': float(totals['total_offer_price']),
                'total_offer_price_formatted': f"₹{totals['total_offer_price']:,.2f}",
                'discounted_amount': float(totals['discounted_amount']),
                'discounted_amount_formatted': f"₹{totals['discounted_amount']:,.2f}",
                'delivery_charge': float(totals['delivery_charge']),
                'delivery_charge_display': "FREE" if totals['is_free_delivery'] else f"₹{totals['delivery_charge']:,.2f}",
                'grand_total': float(totals['grand_total']),
                'grand_total_formatted': f"₹{totals['grand_total']:,.2f}",
                'free_delivery_progress': totals['free_delivery_progress'],
                'amount_needed_for_free_delivery': float(totals['amount_needed_for_free_delivery']),
                'amount_needed_formatted': f"₹{totals['amount_needed_for_free_delivery']:,.2f}",
                'is_free_delivery': totals['is_free_delivery'],
                'has_out_of_stock': totals['has_out_of_stock'],
                'is_empty': totals['is_empty'],
            }
        })
    except CartItem.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Item not found in cart.'}, status=404)
    except Exception as e:
        logger.error(f"Error in move_to_wishlist: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@require_POST
def clear_cart(request):
    """Clear all items from the current user's cart."""
    try:
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            cart.items.all().delete()
        return JsonResponse({'status': 'success', 'message': 'Your cart has been cleared.'})
    except Exception as e:
        logger.error(f"Error in clear_cart: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
