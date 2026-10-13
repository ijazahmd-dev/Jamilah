from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from user_profile.models import Address, ShippingAddress
from cart.models import Cart, CartItem
from django.http import JsonResponse,HttpResponse
from django.contrib import messages
from decimal import Decimal
from orders.models import Order, OrderItem
from django.urls import reverse
from django.db.models import Q, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.template.loader import render_to_string
from weasyprint import HTML
from django.views.decorators.http import require_POST
from wallet.models import Wallet,WalletTransaction
from offers.models import ProductOffer,CategoryOffer
from coupons.models import Coupon,CouponUsage
from django.views.decorators.cache import never_cache
from functools import wraps




# Create your views here.




###############################################USER SIDE START###############################################













@login_required
def place_order(request):
    user = request.user
    addresses = Address.objects.filter(user=user, is_deleted=False)
    default_address = addresses.filter(is_default=True).first()

    try:
        cart = Cart.objects.get(user=user)
        cart_items = CartItem.objects.filter(cart=cart)

        if not cart_items.exists():
            return JsonResponse({"error": "Your cart is empty. Please add items to checkout."}, status=400)

        for item in cart_items:
            if item.quantity > item.product_variant.stock:
                messages.error(request, 'Please remove the out of stock products')
                return redirect('cart_view')

        total_listed_price = Decimal('0.00')
        total_offer_price = Decimal('0.00')
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

            quantity = Decimal(str(item.quantity))
            item.subtotal = final_price * quantity
            item.subtotal_listed_price = product.price * quantity
            item.subtotal_offer_price = final_price * quantity
            total_listed_price += item.subtotal_listed_price
            total_offer_price += item.subtotal_offer_price

        discounted_amount = total_listed_price - total_offer_price
        delivery_charge = Decimal('40.00') if total_offer_price < Decimal('1000.00') else Decimal('0.00')
        grand_total = total_offer_price + delivery_charge

        request.session['cart_total'] = str(total_offer_price)

        coupon_discount = Decimal('0.00')
        coupon_code = request.session.get('coupon_code', None)
        coupon = None
        if coupon_code:
            try:
                coupon = Coupon.objects.get(coupon_code=coupon_code, is_active=True)
                if coupon.is_valid() and total_offer_price >= coupon.minimum_purchase_amount:
                    if not CouponUsage.objects.filter(user=user, coupon=coupon).exists():
                        coupon_discount = (coupon.discount_percentage / Decimal('100.00')) * total_offer_price
                        if coupon_discount > coupon.max_discount_amount:
                            coupon_discount = coupon.max_discount_amount
                        grand_total -= coupon_discount
                        discounted_amount += coupon_discount
                    else:
                        coupon = None  # Coupon already used
                        if 'coupon_code' in request.session:
                            del request.session['coupon_code']
            except Coupon.DoesNotExist:
                coupon = None
                if 'coupon_code' in request.session:
                    del request.session['coupon_code']

        # Filter available coupons
        now = timezone.now().date()
        available_coupons = Coupon.objects.filter(
            valid_from__lte=now,
            valid_to__gte=now,
            is_active=True,
            minimum_purchase_amount__lte=total_offer_price
        ).exclude(coupon_id__in=CouponUsage.objects.filter(user=user).values_list('coupon_id', flat=True))
        available_coupons = available_coupons[:2]

    except Cart.DoesNotExist:
        return JsonResponse({"error": "Cart not found"}, status=400)

    if request.method == "POST":
        try:
            address_id = request.POST.get("address_id")
            payment_method = request.POST.get("payment_method")

            if not address_id or not payment_method:
                return JsonResponse({"error": "Address or payment method not provided."}, status=400)

            address = Address.objects.get(id=address_id, user=user) if address_id else default_address
            if not address:
                return JsonResponse({"error": "No valid address found."}, status=400)

            shipping_address = ShippingAddress.objects.create(
                user=user,
                name=address.name,
                address=address.address,
                city=address.city,
                state=address.state,
                country=address.country,
                postcode=address.postcode,
                phone=address.phone,
            )

            if payment_method == "COD":
                if grand_total > Decimal('1000.00'):
                    return JsonResponse({"error": "Cash on Delivery is unavailable for orders above ₹1,000. Please choose Online Payment or Wallet."}, status=400)
                payment_status = 'Pending'
                order_status = 'pending'
                order_item_status = 'order_placed'
            elif payment_method == "wallet":
                wallet, _ = Wallet.objects.get_or_create(user=user)
                if wallet.balance < grand_total:
                    return JsonResponse({"error": f"Insufficient wallet balance. Available: ₹{wallet.balance:,.2f}, Required: ₹{grand_total:,.2f}"}, status=400)
                payment_status = 'Paid'
                order_status = 'pending'
                order_item_status = 'order_placed'
            elif payment_method == "razorpay":
                payment_status = 'Pending'
                order_status = 'processing'
                order_item_status = 'processing'
            else:
                return JsonResponse({"error": "Invalid payment method selected."}, status=400)

            order = Order.objects.create(
                user=user,
                shipping_address=shipping_address,
                payment_method=payment_method,
                payment_status=payment_status,
                status=order_status,
                total_price=grand_total,
                coupon=coupon,
                discount_coupon_amount=coupon_discount
            )

            for item in cart_items:
                if item.product_variant.stock < item.quantity:
                    order.delete()
                    return JsonResponse({"error": f"Not enough stock for {item.product_variant.product.name}."}, status=400)

                item.product_variant.stock -= item.quantity
                item.product_variant.save()

                product = item.product_variant.product
                product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
                category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()
                final_price = product.price
                if product_offer and category_offer:
                    final_price = min(
                        product.price * (1 - product_offer.discount_percentage / 100),
                        product.price * (1 - category_offer.discount_percentage / 100)
                    )
                elif product_offer:
                    final_price = product.price * (1 - product_offer.discount_percentage / 100)
                elif category_offer:
                    final_price = product.price * (1 - category_offer.discount_percentage / 100)

                OrderItem.objects.create(
                    order=order,
                    product=item.product_variant.product,
                    product_variant=item.product_variant,
                    quantity=item.quantity,
                    status=order_item_status,
                    price=final_price,
                    final_offer_price=final_price
                )

            # Record coupon usage if coupon applied
            if coupon and payment_method in ["COD", "wallet"]:
                CouponUsage.objects.get_or_create(user=user, coupon=coupon)

            request.session['cart_details'] = {'order_id': order.id}

            if payment_method in ["COD", "wallet"]:
                if payment_method == "wallet":
                    wallet, _ = Wallet.objects.get_or_create(user=user)
                    if wallet.balance < grand_total:
                        order.delete()
                        return JsonResponse({"error": "Insufficient funds in wallet."}, status=400)
                    wallet.balance -= grand_total
                    wallet.save()

                    WalletTransaction.objects.create(
                        wallet=wallet,
                        order=order,
                        amount=grand_total,
                        transaction_type='debit',
                        description=f"Payment for Order #{order.id}"
                    )

                # Clear cart and session data
                cart_items.delete()
                redirect_url = reverse('order_success', args=[order.id])
                if 'cart_details' in request.session:
                    del request.session['cart_details']
                if 'coupon_code' in request.session:
                    del request.session['coupon_code']
                return JsonResponse({"redirect": redirect_url})

            elif payment_method == "razorpay":
                return JsonResponse({"redirect": reverse('payments:initiate_payment')})

        except Exception as e:
            # Log the exception for debugging
            print(f"Error in place_order: {str(e)}")
            return JsonResponse({"error": str(e)}, status=400)

    # Calculate wallet sufficiency & COD availability for context
    wallet, _ = Wallet.objects.get_or_create(user=user)
    wallet_balance = wallet.balance
    can_use_wallet = wallet.balance >= grand_total
    wallet_short_amount = max(Decimal('0.00'), grand_total - wallet.balance)
    can_use_cod = grand_total <= Decimal('1000.00')

    context = {
        'addresses': addresses,
        'default_address': default_address,
        'cart_items': cart_items,
        'total_listed_price': total_listed_price,
        'total_offer_price': total_offer_price,
        'discounted_amount': discounted_amount,
        'delivery_charge': delivery_charge,
        'grand_total': grand_total,
        'coupon_discount': coupon_discount,
        'applied_coupon': coupon,
        'available_coupons': available_coupons,
        'wallet_balance': wallet_balance,
        'can_use_wallet': can_use_wallet,
        'wallet_short_amount': wallet_short_amount,
        'can_use_cod': can_use_cod,
    }
    return render(request, 'user/checkout.html', context)











# @login_required
# def place_order(request):
#     user = request.user
#     addresses = Address.objects.filter(user=user, is_deleted=False)
#     default_address = addresses.filter(is_default=True).first()

#     try:
#         cart = Cart.objects.get(user=user)
#         cart_items = CartItem.objects.filter(cart=cart)

#         if not cart_items.exists():
#             return JsonResponse({"error": "Your cart is empty. Please add items to checkout."}, status=400)

#         for item in cart_items:
#             if item.quantity > item.product_variant.stock:
#                 messages.error(request, 'Please remove the out of stock products')
#                 return redirect('cart_view')

#         total_listed_price = Decimal('0.00')
#         total_offer_price = Decimal('0.00')
#         for item in cart_items:
#             product = item.product_variant.product
#             product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
#             category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()

#             if product_offer and category_offer:
#                 final_price = min(
#                     product.price * (1 - product_offer.discount_percentage / 100),
#                     product.price * (1 - category_offer.discount_percentage / 100)
#                 )
#             elif product_offer:
#                 final_price = product.price * (1 - product_offer.discount_percentage / 100)
#             elif category_offer:
#                 final_price = product.price * (1 - category_offer.discount_percentage / 100)
#             else:
#                 final_price = product.price

#             quantity = Decimal(str(item.quantity))
#             item.subtotal = final_price * quantity
#             item.subtotal_listed_price = product.price * quantity
#             item.subtotal_offer_price = final_price * quantity
#             total_listed_price += item.subtotal_listed_price
#             total_offer_price += item.subtotal_offer_price

#         discounted_amount = total_listed_price - total_offer_price
#         delivery_charge = Decimal('40.00') if total_offer_price < Decimal('1000.00') else Decimal('0.00')
#         grand_total = total_offer_price + delivery_charge

#         request.session['cart_total'] = str(total_offer_price)

#         coupon_discount = Decimal('0.00')
#         coupon_code = request.session.get('coupon_code', None)
#         coupon = None
#         if coupon_code:
#             try:
#                 coupon = Coupon.objects.get(coupon_code=coupon_code, is_active=True)
#                 if coupon.is_valid() and total_offer_price >= coupon.minimum_purchase_amount:
#                     if not CouponUsage.objects.filter(user=user, coupon=coupon).exists():
#                         coupon_discount = (coupon.discount_percentage / Decimal('100.00')) * total_offer_price
#                         if coupon_discount > coupon.max_discount_amount:
#                             coupon_discount = coupon.max_discount_amount
#                         grand_total -= coupon_discount
#                         discounted_amount += coupon_discount
#             except Coupon.DoesNotExist:
#                 pass

#         # Filter available coupons
#         now = timezone.now().date()
#         available_coupons = Coupon.objects.filter(
#             valid_from__lte=now,
#             valid_to__gte=now,
#             is_active=True,
#             minimum_purchase_amount__lte=total_offer_price
#         ).exclude(coupon_id__in=CouponUsage.objects.filter(user=user).values_list('coupon_id', flat=True))
#         # Limit to 2 coupons for display
#         available_coupons = available_coupons[:2]

#     except Cart.DoesNotExist:
#         return JsonResponse({"error": "Cart not found"}, status=400)

#     if request.method == "POST":
#         try:
#             address_id = request.POST.get("address_id")
#             payment_method = request.POST.get("payment_method")

#             if not address_id or not payment_method:
#                 return JsonResponse({"error": "Address or payment method not provided."}, status=400)

#             address = Address.objects.get(id=address_id, user=user) if address_id else default_address
#             if not address:
#                 return JsonResponse({"error": "No valid address found."}, status=400)

#             shipping_address = ShippingAddress.objects.create(
#                 user=user,
#                 name=address.name,
#                 address=address.address,
#                 city=address.city,
#                 state=address.state,
#                 country=address.country,
#                 postcode=address.postcode,
#                 phone=address.phone,
#             )

#             if payment_method == "COD":
#                 payment_status = 'Pending'
#                 order_status = 'pending'
#                 order_item_status = 'order_placed'
#             elif payment_method == "wallet":
#                 payment_status = 'Paid'
#                 order_status = 'pending'
#                 order_item_status = 'order_placed'
#             elif payment_method == "razorpay":
#                 payment_status = 'Pending'
#                 order_status = 'processing'
#                 order_item_status = 'processing'
#             else:
#                 return JsonResponse({"error": "Invalid payment method"}, status=400)

#             order = Order.objects.create(
#                 user=user,
#                 shipping_address=shipping_address,
#                 payment_method=payment_method,
#                 payment_status=payment_status,
#                 status=order_status,
#                 total_price=grand_total,
#                 coupon=coupon,
#                 discount_coupon_amount=coupon_discount
#             )

#             for item in cart_items:
#                 if item.product_variant.stock < item.quantity:
#                     order.delete()
#                     return JsonResponse({"error": f"Not enough stock for {item.product_variant.product.name}."}, status=400)

#                 item.product_variant.stock -= item.quantity
#                 item.product_variant.save()

#                 product = item.product_variant.product
#                 product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
#                 category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()
#                 final_price = product.price
#                 if product_offer and category_offer:
#                     final_price = min(
#                         product.price * (1 - product_offer.discount_percentage / 100),
#                         product.price * (1 - category_offer.discount_percentage / 100)
#                     )
#                 elif product_offer:
#                     final_price = product.price * (1 - product_offer.discount_percentage / 100)
#                 elif category_offer:
#                     final_price = product.price * (1 - category_offer.discount_percentage / 100)

#                 OrderItem.objects.create(
#                     order=order,
#                     product=item.product_variant.product,
#                     product_variant=item.product_variant,
#                     quantity=item.quantity,
#                     status=order_item_status,
#                     price=final_price,
#                     final_offer_price=final_price
#                 )

#             if coupon:
#                 CouponUsage.objects.create(user=user, coupon=coupon)

#             request.session['cart_details'] = {'order_id': order.id}

#             if payment_method in ["COD", "wallet"]:
#                 if payment_method == "wallet":
#                     wallet = Wallet.objects.get(user=user)
#                     if wallet.balance < grand_total:
#                         order.delete()
#                         return JsonResponse({"error": "Insufficient funds in wallet."}, status=400)
#                     wallet.balance -= grand_total
#                     wallet.save()

#                     WalletTransaction.objects.create(
#                     wallet=wallet,
#                     order=order,
#                     amount=grand_total,
#                     transaction_type='debit'
#                 )

#                 cart_items.delete()
#                 del request.session['cart_details']
#                 del request.session['coupon_code']  # Clear coupon after use
#                 return JsonResponse({"redirect": reverse('order_success', args=[order.id])})
#             elif payment_method == "razorpay":
#                 return JsonResponse({"redirect": reverse('payments:initiate_payment')})

#         except Exception as e:
#             return JsonResponse({"error": str(e)}, status=400)

#     context = {
#         'addresses': addresses,
#         'default_address': default_address,
#         'cart_items': cart_items,
#         'total_listed_price': total_listed_price,
#         'total_offer_price': total_offer_price,
#         'discounted_amount': discounted_amount,
#         'delivery_charge': delivery_charge,
#         'grand_total': grand_total,
#         'coupon_discount': coupon_discount,
#         'available_coupons': available_coupons,  # Add available coupons to context
#     }
#     return render(request, 'user/checkout.html', context)












# @login_required
# def place_order(request):
#     user = request.user
#     addresses = Address.objects.filter(user=user, is_deleted=False)
#     default_address = addresses.filter(is_default=True).first()

#     try:
#         cart = Cart.objects.get(user=user)
#         cart_items = CartItem.objects.filter(cart=cart)

#         if not cart_items.exists():
#             return JsonResponse({"error": "Your cart is empty. Please add items to checkout."}, status=400)

#         for item in cart_items:
#             if item.quantity > item.product_variant.stock:
#                 messages.error(request, 'Please remove the out of stock products')
#                 return redirect('cart_view')

#         total_listed_price = Decimal('0.00')
#         total_offer_price = Decimal('0.00')
#         for item in cart_items:
#             product = item.product_variant.product
#             product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
#             category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()

#             if product_offer and category_offer:
#                 final_price = min(
#                     product.price * (1 - product_offer.discount_percentage / 100),
#                     product.price * (1 - category_offer.discount_percentage / 100)
#                 )
#             elif product_offer:
#                 final_price = product.price * (1 - product_offer.discount_percentage / 100)
#             elif category_offer:
#                 final_price = product.price * (1 - category_offer.discount_percentage / 100)
#             else:
#                 final_price = product.price

#             quantity = Decimal(str(item.quantity))
#             item.subtotal = final_price * quantity
#             item.subtotal_listed_price = product.price * quantity
#             item.subtotal_offer_price = final_price * quantity
#             total_listed_price += item.subtotal_listed_price
#             total_offer_price += item.subtotal_offer_price

#         discounted_amount = total_listed_price - total_offer_price
#         delivery_charge = Decimal('40.00') if total_offer_price < Decimal('1000.00') else Decimal('0.00')
#         grand_total = total_offer_price + delivery_charge

#         request.session['cart_total'] = str(total_offer_price)

#         coupon_discount = Decimal('0.00')
#         coupon_code = request.session.get('coupon_code', None)
#         coupon = None
#         if coupon_code:
#             try:
#                 coupon = Coupon.objects.get(coupon_code=coupon_code, is_active=True)
#                 if coupon.is_valid() and total_offer_price >= coupon.minimum_purchase_amount:
#                     if not CouponUsage.objects.filter(user=user, coupon=coupon).exists():
#                         coupon_discount = (coupon.discount_percentage / Decimal('100.00')) * total_offer_price
#                         if coupon_discount > coupon.max_discount_amount:
#                             coupon_discount = coupon.max_discount_amount
#                         grand_total -= coupon_discount
#                         discounted_amount += coupon_discount
#             except Coupon.DoesNotExist:
#                 pass

#     except Cart.DoesNotExist:
#         return JsonResponse({"error": "Cart not found"}, status=400)

#     if request.method == "POST":
#         try:
#             address_id = request.POST.get("address_id")
#             payment_method = request.POST.get("payment_method")

#             if not address_id or not payment_method:
#                 return JsonResponse({"error": "Address or payment method not provided."}, status=400)

#             address = Address.objects.get(id=address_id, user=user) if address_id else default_address
#             if not address:
#                 return JsonResponse({"error": "No valid address found."}, status=400)

#             shipping_address = ShippingAddress.objects.create(
#                 user=user,
#                 name=address.name,
#                 address=address.address,
#                 city=address.city,
#                 state=address.state,
#                 country=address.country,
#                 postcode=address.postcode,
#                 phone=address.phone,
#             )

#             if payment_method == "COD":
#                 payment_status = 'Pending'
#                 order_status = 'pending'
#                 order_item_status = 'order_placed'
#             elif payment_method == "wallet":
#                 payment_status = 'Paid'
#                 order_status = 'pending'
#                 order_item_status = 'order_placed'
#             elif payment_method == "razorpay":
#                 payment_status = 'Pending'
#                 order_status = 'processing'
#                 order_item_status = 'processing'
#             else:
#                 return JsonResponse({"error": "Invalid payment method"}, status=400)

#             order = Order.objects.create(
#                 user=user,
#                 shipping_address=shipping_address,
#                 payment_method=payment_method,
#                 payment_status=payment_status,
#                 status=order_status,
#                 total_price=grand_total,
#                 coupon=coupon,
#                 discount_coupon_amount=coupon_discount
#             )

#             for item in cart_items:
#                 if item.product_variant.stock < item.quantity:
#                     order.delete()
#                     return JsonResponse({"error": f"Not enough stock for {item.product_variant.product.name}."}, status=400)

#                 item.product_variant.stock -= item.quantity
#                 item.product_variant.save()

#                 product = item.product_variant.product
#                 product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
#                 category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()
#                 final_price = product.price
#                 if product_offer and category_offer:
#                     final_price = min(
#                         product.price * (1 - product_offer.discount_percentage / 100),
#                         product.price * (1 - category_offer.discount_percentage / 100)
#                     )
#                 elif product_offer:
#                     final_price = product.price * (1 - product_offer.discount_percentage / 100)
#                 elif category_offer:
#                     final_price = product.price * (1 - category_offer.discount_percentage / 100)

#                 OrderItem.objects.create(
#                     order=order,
#                     product=item.product_variant.product,
#                     product_variant=item.product_variant,
#                     quantity=item.quantity,
#                     status=order_item_status,
#                     price=final_price,
#                     final_offer_price=final_price
#                 )

#             if coupon:
#                 CouponUsage.objects.create(user=user, coupon=coupon)

#             request.session['cart_details'] = {'order_id': order.id}

#             if payment_method in ["COD", "wallet"]:
#                 if payment_method == "wallet":
#                     wallet = Wallet.objects.get(user=user)
#                     if wallet.balance < grand_total:
#                         order.delete()
#                         return JsonResponse({"error": "Insufficient funds in wallet."}, status=400)
#                     wallet.balance -= grand_total
#                     wallet.save()

#                 cart_items.delete()
#                 del request.session['cart_details']
#                 del request.session['coupon_code']  # Clear coupon after use
#                 return JsonResponse({"redirect": reverse('order_success', args=[order.id])})
#             elif payment_method == "razorpay":
#                 return JsonResponse({"redirect": reverse('payments:initiate_payment')})

#         except Exception as e:
#             return JsonResponse({"error": str(e)}, status=400)

#     context = {
#         'addresses': addresses,
#         'default_address': default_address,
#         'cart_items': cart_items,
#         'total_listed_price': total_listed_price,
#         'total_offer_price': total_offer_price,
#         'discounted_amount': discounted_amount,
#         'delivery_charge': delivery_charge,
#         'grand_total': grand_total,
#         'coupon_discount': coupon_discount
#     }
#     return render(request, 'user/checkout.html', context)








"""
ORDER CONFIRMATION CONTEXT HELPER
"""
def get_order_confirmation_context(order, is_success, show_retry=False):
    """Enriches order details for the confirmation / payment failure page."""
    order_items = order.items.select_related('product', 'product_variant').all()

    total_listed_price = Decimal('0.00')
    total_offer_price = Decimal('0.00')
    total_units = 0

    for item in order_items:
        product = item.product
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
            final_price = item.final_offer_price or item.price or product.price

        qty = Decimal(str(item.quantity))
        listed_p = product.price * qty
        offer_p = final_price * qty
        item.unit_offer_price = final_price
        item.unit_listed_price = product.price
        item.subtotal = offer_p
        item.listed_subtotal = listed_p
        item.savings = max(Decimal('0.00'), listed_p - offer_p)
        total_listed_price += listed_p
        total_offer_price += offer_p
        total_units += item.quantity

    store_savings = max(Decimal('0.00'), total_listed_price - total_offer_price)
    coupon_savings = order.discount_coupon_amount or Decimal('0.00')
    total_savings = store_savings + coupon_savings

    order_date = order.created_at or timezone.now()
    est_delivery_start = (order_date + timezone.timedelta(days=3)).strftime("%B %d, %Y")
    est_delivery_end = (order_date + timezone.timedelta(days=5)).strftime("%B %d, %Y")

    delivery_charge = Decimal('0.00') if total_offer_price >= Decimal('1000.00') else Decimal('40.00')
    has_invoice = order_items.filter(status__in=['delivered', 'return_requested', 'return_denied', 'returned']).exists()

    return {
        'order': order,
        'order_number': order.id,
        'order_items': order_items,
        'total_units': total_units,
        'total_listed_price': total_listed_price,
        'total_offer_price': total_offer_price,
        'store_savings': store_savings,
        'coupon_savings': coupon_savings,
        'total_savings': total_savings,
        'delivery_charge': delivery_charge,
        'grand_total': order.total_price,
        'payment_status': order.payment_status,
        'payment_method': order.payment_method,
        'shipping_address': order.shipping_address,
        'is_success': is_success,
        'show_retry_button': show_retry,
        'order_date': order_date,
        'est_delivery_start': est_delivery_start,
        'est_delivery_end': est_delivery_end,
        'has_invoice': has_invoice,
    }


"""
ORDER SUCCESS
"""
@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if 'entered_coupon_code' in request.session:
        del request.session['entered_coupon_code']
    if 'coupon_code' in request.session:
        del request.session['coupon_code']

    if order.payment_method == 'COD':
        is_success = True  
    elif order.payment_method in ['razorpay', 'wallet']:
        is_success = order.payment_status == 'Paid'  
    else:
        is_success = False  

    show_retry = (not is_success) and (order.payment_method == 'razorpay')
    context = get_order_confirmation_context(order, is_success=is_success, show_retry=show_retry)
    return render(request, 'user/order_confirm.html', context)







"""
USER SIDE ORDERS LISTING PAGE
"""
@login_required
def user_orders(request):
    base_orders = Order.objects.filter(user=request.user)
    
    # Order Status Metrics
    total_orders_count = base_orders.count()
    processing_count = base_orders.filter(status='processing').count()
    pending_count = base_orders.filter(status='pending').count()
    completed_count = base_orders.filter(status='completed').count()
    canceled_count = base_orders.filter(status__in=['canceled', 'returned']).count()

    # Query Parameters
    status_filter = request.GET.get('status', 'all').strip().lower()
    search_query = request.GET.get('q', '').strip()
    time_filter = request.GET.get('time', 'all').strip()

    orders_qs = base_orders

    if status_filter and status_filter != 'all':
        if status_filter == 'active':
            orders_qs = orders_qs.filter(status__in=['processing', 'pending'])
        elif status_filter == 'canceled_returned':
            orders_qs = orders_qs.filter(status__in=['canceled', 'returned'])
        else:
            orders_qs = orders_qs.filter(status=status_filter)

    if search_query:
        orders_qs = orders_qs.filter(
            Q(id__icontains=search_query) |
            Q(items__product__name__icontains=search_query)
        ).distinct()

    if time_filter == '30_days':
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        orders_qs = orders_qs.filter(created_at__gte=thirty_days_ago)
    elif time_filter == '6_months':
        six_months_ago = timezone.now() - timezone.timedelta(days=180)
        orders_qs = orders_qs.filter(created_at__gte=six_months_ago)
    elif time_filter == 'this_year':
        orders_qs = orders_qs.filter(created_at__year=timezone.now().year)

    orders_qs = orders_qs.prefetch_related(
        'items__product__images',
        'items__product_variant'
    ).order_by('-created_at')

    page = request.GET.get('page', 1)
    paginator = Paginator(orders_qs, 8)

    try:
        orders = paginator.page(page)
    except PageNotAnInteger:
        orders = paginator.page(1)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)

    context = {
        'orders': orders,
        'total_orders_count': total_orders_count,
        'processing_count': processing_count,
        'pending_count': pending_count,
        'completed_count': completed_count,
        'canceled_count': canceled_count,
        'status_filter': status_filter,
        'search_query': search_query,
        'time_filter': time_filter,
    }
    return render(request, 'user/orders_list.html', context)






"""
USER SIDE ORDER ITEMS LISTING PAGE
"""
@login_required
def order_items(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    items_qs = order.items.select_related('product', 'product_variant').prefetch_related('product__images').all().order_by('id')
    
    total_listed_price = sum(item.product.price * item.quantity for item in items_qs)
    total_offer_price = sum(item.final_offer_price * item.quantity for item in items_qs)
    delivery_charge = Decimal('40.00') if total_offer_price < Decimal('1000.00') else Decimal('0.00')
    coupon_discount = order.discount_coupon_amount or Decimal('0.00')
    savings = (total_listed_price - total_offer_price) + coupon_discount
    
    page = request.GET.get('page', 1)
    paginator = Paginator(items_qs, 10)
    try:
        order_items = paginator.page(page)
    except PageNotAnInteger:
        order_items = paginator.page(1)
    except EmptyPage:
        order_items = paginator.page(paginator.num_pages)

    return render(request, 'user/order_items.html', {
        'order': order,
        'order_items': order_items,
        'total_items_count': items_qs.count(),
        'total_listed_price': total_listed_price,
        'total_offer_price': total_offer_price,
        'delivery_charge': delivery_charge,
        'coupon_discount': coupon_discount,
        'savings': savings,
    })








@login_required
def user_order_details(request, item_id):
    particular_product = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    order = particular_product.order
    order_items = order.items.all()

    total_listed_price = Decimal('0.00')
    total_offer_price = Decimal('0.00')
    for item in order_items:
        total_listed_price += item.product.price * Decimal(str(item.quantity))
        total_offer_price += item.final_offer_price * Decimal(str(item.quantity))

    delivery_charge = Decimal('40.00') if total_offer_price < Decimal('1000.00') else Decimal('0.00')
    coupon_discount = order.discount_coupon_amount
    grand_total = total_offer_price + delivery_charge - coupon_discount

    current_time = timezone.now()
    days_since_delivery = (current_time - particular_product.updated_at).days

    return render(request, 'user/order_details.html', {
        'order': order,
        'particular_product': particular_product,
        'other_products_in_order': order_items.exclude(id=particular_product.id),
        'total_listed_price': total_listed_price,
        'total_offer_price': total_offer_price,
        'discounted_amount': total_listed_price - total_offer_price,
        'delivery_charge': delivery_charge,
        'grand_total': grand_total,
        'coupon_discount': coupon_discount,
        'days_since_delivery': days_since_delivery,
    })










# """
# USER SIDE ORDER ITEM DETAILS LISTING PAGE
# """
# @login_required
# def user_order_details(request, item_id):
#     particular_product = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
#     order = particular_product.order
#     order_items = order.items.all()

#     total_listed_price = Decimal('0.00')
#     total_offer_price = Decimal('0.00')
#     for item in order_items:
#         product = item.product
#         product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
#         category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()

#         # # Calculate the final price based on the best offer
#         if product_offer and category_offer:
#             final_price = min(
#                 product.price * (1 - product_offer.discount_percentage / 100),
#                 product.price * (1 - category_offer.discount_percentage / 100)
#             )
#         elif product_offer:
#             final_price = product.price * (1 - product_offer.discount_percentage / 100)
#         elif category_offer:
#             final_price = product.price * (1 - category_offer.discount_percentage / 100)
#         else:
#             final_price = product.price


#         quantity = Decimal(str(item.quantity))
#         item.subtotal_listed_price = product.price * quantity
#         item.subtotal_offer_price = final_price * quantity
#         total_listed_price += item.subtotal_listed_price
#         total_offer_price += item.subtotal_offer_price

#     discounted_amount = total_listed_price - total_offer_price
#     delivery_charge = Decimal('40.00') if total_offer_price < Decimal('1000.00') else Decimal('0.00')
#     grand_total = total_offer_price + delivery_charge

#     # Calculate coupon discount
#     coupon_discount = Decimal('0.00')
#     if order.coupon:
#         coupon_discount = order.discount_coupon_amount
#         grand_total -= coupon_discount
#         discounted_amount += coupon_discount

#     other_products_in_order = order_items.exclude(id=particular_product.id)

#     current_time = timezone.now()
#     days_since_delivery = (current_time - particular_product.updated_at).days

#     return render(request, 'user/order_details.html', {
#         'order': order,
#         'particular_product': particular_product,
#         'other_products_in_order': other_products_in_order,
#         'total_listed_price': total_listed_price,
#         'total_offer_price': total_offer_price,
#         'discounted_amount': discounted_amount,
#         'delivery_charge': delivery_charge,
#         'grand_total': grand_total,
#         'coupon_discount': coupon_discount,
#         'days_since_delivery': days_since_delivery,
#     })








"""
CENTRALIZED REFUND ENGINE (INDUSTRIAL STANDARD)
"""
def calculate_order_item_refund(order_item):
    """
    Calculates the exact refund amount for an OrderItem upon cancellation or return.
    
    Guarantees:
    1. Returns Decimal('0.00') if the order was not paid (e.g. pending COD or unpaid online payment).
    2. Takes into account item purchase price (which already includes Product/Category offers).
    3. Accurately handles coupons:
       - If no coupon: refund is gross item price (quantity * price).
       - If coupon applied:
         * If remaining active items drop below coupon.minimum_purchase_amount, coupon is invalidated.
           The coupon discount is clawed back, customer retains items at their purchase price:
           target_total_refund = max(0, order.total_price - remaining_active_gross)
           refund = max(0, target_total_refund - already_refunded)
         * If remaining active items still satisfy coupon.minimum_purchase_amount, coupon remains valid.
           Item refund is gross minus its proportional share of the coupon discount:
           item_discount = (item_gross / total_order_gross) * order.discount_coupon_amount
           refund = item_gross - item_discount
         * If this is the last active item or full cancellation:
           Customer receives the exact remaining balance of order.total_price:
           refund = max(0, order.total_price - already_refunded)
    4. Capped such that cumulative refunds for the order never exceed order.total_price.
    5. Always non-negative and rounded to 2 decimal places.
    """
    order = order_item.order

    # 1. Money was collected only if payment_status is 'Paid' or 'Refunded'
    if order.payment_status not in ['Paid', 'Refunded']:
        # If COD and delivered, payment was collected upon delivery
        if order.payment_method == 'COD' and (order_item.status in ['delivered', 'return_requested', 'returned', 'return_denied'] or any(i.status == 'delivered' for i in order.items.all())):
            order.payment_status = 'Paid'
            order.save(update_fields=['payment_status'])
        else:
            return Decimal('0.00')

    # 2. Cumulative already refunded amount from wallet ledger for this order
    already_refunded = WalletTransaction.objects.filter(
        order=order,
        transaction_type='credit'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    remaining_order_paid_balance = max(Decimal('0.00'), order.total_price - already_refunded)
    if remaining_order_paid_balance <= Decimal('0.00'):
        return Decimal('0.00')

    # 3. Item Gross Value (reflects recorded price which already has product/category offer applied)
    item_gross = Decimal(str(order_item.price)) * Decimal(str(order_item.quantity))

    # 4. Total Order Gross at placement
    all_order_items = list(order.items.all())
    total_order_gross = sum(
        Decimal(str(item.price)) * Decimal(str(item.quantity)) 
        for item in all_order_items
    )
    if total_order_gross <= Decimal('0.00'):
        total_order_gross = item_gross or Decimal('1.00')

    # 5. Remaining Active Items (excluding this item and already canceled/returned items)
    active_remaining_items = [
        item for item in all_order_items 
        if item.id != order_item.id and item.status not in ['canceled', 'returned']
    ]
    remaining_active_gross = sum(
        Decimal(str(item.price)) * Decimal(str(item.quantity)) 
        for item in active_remaining_items
    )

    coupon = order.coupon
    coupon_discount = Decimal(str(order.discount_coupon_amount or '0.00'))

    # Case A: No Coupon applied
    if not coupon or coupon_discount <= Decimal('0.00'):
        if not active_remaining_items:
            # Entire order / last item: refund remaining paid balance including any delivery fee
            refund_amount = remaining_order_paid_balance
        else:
            refund_amount = min(item_gross, remaining_order_paid_balance)

    # Case B: Coupon applied
    else:
        # B1: Last active item or full order cancellation
        if not active_remaining_items:
            refund_amount = remaining_order_paid_balance
        # B2: Remaining items drop below coupon minimum purchase amount
        elif remaining_active_gross < coupon.minimum_purchase_amount:
            # Coupon clawback: customer charged full price for retained items
            target_total_refund = max(Decimal('0.00'), order.total_price - remaining_active_gross)
            refund_amount = max(Decimal('0.00'), target_total_refund - already_refunded)
        # B3: Remaining items still meet coupon minimum purchase amount
        else:
            # Proportional coupon discount deducted from this item
            item_coupon_share = (item_gross / total_order_gross) * coupon_discount
            refund_amount = max(Decimal('0.00'), item_gross - item_coupon_share)

    # Safety bounds: non-negative and capped by remaining order balance
    refund_amount = max(Decimal('0.00'), min(refund_amount, remaining_order_paid_balance))
    return refund_amount.quantize(Decimal('0.01'))


def process_order_item_refund(order_item, refund_amount, action_type="Cancellation", reason=""):
    """
    Credits the calculated refund to user's wallet and creates an auditable WalletTransaction.
    Returns the created WalletTransaction or None if refund_amount <= 0.
    """
    if refund_amount <= Decimal('0.00'):
        return None

    order = order_item.order
    wallet, _ = Wallet.objects.get_or_create(user=order.user)
    wallet.balance += refund_amount
    wallet.save()

    desc_parts = [f"{action_type} refund for {order_item.product.name} (Qty: {order_item.quantity})"]
    if reason:
        desc_parts.append(f"Reason: {reason}")
    description = " - ".join(desc_parts)[:250]

    tx = WalletTransaction.objects.create(
        wallet=wallet,
        order=order,
        amount=refund_amount,
        transaction_type='credit',
        description=description
    )
    return tx


"""
CANCEL OPTION FOR USER
"""
@login_required
def cancel_order_item(request, item_id):
    order_item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('Accept', '') or
        request.POST.get('ajax') == '1'
    )

    if order_item.status in ['out_for_delivery', 'delivered', 'canceled', 'return_requested', 'return', 'returned']:
        if is_ajax or request.method == 'POST':
            return JsonResponse({
                "error": "This item cannot be canceled in its current status."
            }, status=400)
        messages.warning(request, f"This item is currently '{order_item.get_status_display()}' and cannot be canceled.")
        return redirect('user_order_details', item_id=order_item.id)

    if request.method == "POST":
        cancel_reason = request.POST.get("cancel_reason", "").strip()
        if not cancel_reason:
            if is_ajax:
                return JsonResponse({"error": "Please provide a reason for cancellation (cannot be empty or only spaces)."}, status=400)
            messages.error(request, "Please provide a reason for cancellation.")
            return redirect('cancel_order_item', item_id=order_item.id)

        if len(cancel_reason) < 5:
            if is_ajax:
                return JsonResponse({"error": "Cancellation reason must be at least 5 characters long."}, status=400)
            messages.error(request, "Cancellation reason must be at least 5 characters long.")
            return redirect('cancel_order_item', item_id=order_item.id)

        if len(cancel_reason) > 500:
            if is_ajax:
                return JsonResponse({"error": "Cancellation reason cannot exceed 500 characters."}, status=400)
            messages.error(request, "Cancellation reason cannot exceed 500 characters.")
            return redirect('cancel_order_item', item_id=order_item.id)

        # Restock product variant inventory
        if order_item.product_variant:
            order_item.product_variant.stock += order_item.quantity
            order_item.product_variant.save()

        order_item.status = 'canceled'
        order_item.cancel_reason = cancel_reason
        order_item.save()

        # Update order status
        order_item.order.update_order()
        order_item.order.refresh_from_db()

        # Calculate and execute refund
        refund_amount = calculate_order_item_refund(order_item)
        if refund_amount > Decimal('0.00'):
            process_order_item_refund(
                order_item,
                refund_amount,
                action_type="Cancellation",
                reason=cancel_reason
            )

        # Update master order payment_status if all items are canceled/returned
        order = order_item.order
        final_items = order.items.all()
        if all(i.status in ['canceled', 'returned'] for i in final_items) and order.payment_status in ['Paid', 'Refunded']:
            order.payment_status = 'Refunded'
            order.save(update_fields=['payment_status'])
            # Restore coupon usage if full order canceled
            if order.coupon and all(i.status == 'canceled' for i in final_items):
                CouponUsage.objects.filter(user=order.user, coupon=order.coupon).delete()

        msg = "Order item canceled successfully."
        if refund_amount > Decimal('0.00'):
            msg += f" Refund of ₹{refund_amount:.2f} has been credited to your wallet."

        if is_ajax:
            return JsonResponse({
                "success": True,
                "message": msg,
                "refund_amount": str(refund_amount),
                "redirect_url": reverse('user_order_details', args=[order_item.id])
            })

        messages.success(request, msg)
        return redirect('user_order_details', item_id=order_item.id)

    estimated_refund = calculate_order_item_refund(order_item)
    is_prepaid = order_item.order.payment_status in ['Paid', 'Refunded']

    return render(request, 'user/cancel_reason.html', {
        'order_item': order_item,
        'order': order_item.order,
        'estimated_refund': estimated_refund,
        'is_prepaid': is_prepaid,
    })






"""
RETURN REQUEST - USER
"""
@login_required
def request_return(request, item_id):
    order_item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('Accept', '') or
        request.POST.get('ajax') == '1'
    )

    # Check if the item is eligible for return:
    # Must be delivered within 7 days, and not already return_requested, returned, or canceled
    days_since_delivery = (timezone.now() - order_item.updated_at).days
    is_eligible = (order_item.status == 'delivered' and days_since_delivery <= 7)

    if not is_eligible:
        if is_ajax or request.method == "POST":
            return JsonResponse({
                "error": "This item is not eligible for return. Items can only be returned within 7 days of delivery."
            }, status=400)
        messages.warning(request, f"This item is currently '{order_item.get_status_display()}' and cannot be returned.")
        return redirect('user_order_details', item_id=order_item.id)

    if request.method == "POST":
        return_reason = request.POST.get("return_reason", "").strip()
        if not return_reason:
            if is_ajax:
                return JsonResponse({"error": "Please provide a reason for return (cannot be empty or spaces)."}, status=400)
            messages.error(request, "Please provide a reason for return (cannot be empty or spaces).")
            return redirect('request_return', item_id=item_id)
        elif len(return_reason) < 5:
            if is_ajax:
                return JsonResponse({"error": "Return reason must be at least 5 characters long."}, status=400)
            messages.error(request, "Return reason must be at least 5 characters long.")
            return redirect('request_return', item_id=item_id)
        elif len(return_reason) > 500:
            if is_ajax:
                return JsonResponse({"error": "Return reason cannot exceed 500 characters."}, status=400)
            messages.error(request, "Return reason cannot exceed 500 characters.")
            return redirect('request_return', item_id=item_id)

        order_item.status = 'return_requested'
        order_item.return_reason = return_reason
        order_item.return_requested_at = timezone.now()
        order_item.save()

        # Update parent order status
        order_item.order.update_order()
        order_item.order.refresh_from_db()

        estimated_refund = calculate_order_item_refund(order_item)
        success_msg = "Your return request has been submitted successfully."
        if estimated_refund > Decimal('0.00'):
            success_msg += f" Upon verification, a refund of ₹{estimated_refund:.2f} will be credited to your Jamilah Wallet."

        if is_ajax:
            return JsonResponse({
                "success": True,
                "message": success_msg,
                "estimated_refund": str(estimated_refund),
                "redirect_url": reverse('user_order_details', args=[order_item.id])
            })

        messages.success(request, success_msg)
        return redirect('user_order_details', item_id=item_id)

    estimated_refund = calculate_order_item_refund(order_item)
    remaining_days = max(0, 7 - days_since_delivery)

    return render(request, 'user/return_reason.html', {
        'order_item': order_item,
        'order': order_item.order,
        'estimated_refund': estimated_refund,
        'days_since_delivery': days_since_delivery,
        'remaining_days': remaining_days,
    })








"""
DOWNLOAD INVOICE
"""
def download_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order_items = order.items.all()
    
    # Check if invoice is allowed for this order
    allowed_statuses = ['delivered', 'return_requested', 'return_denied', 'returned']
    if not order_items.filter(status__in=allowed_statuses).exists():
        return redirect('user_order_details')

    # Calculate values for the invoice
    total_listed_price = Decimal('0.00')
    total_offer_price = Decimal('0.00')
    for item in order_items:
        product = item.product
        product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
        category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()

        # Calculate the final price based on the best offer
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
        

        quantity = Decimal(str(item.quantity))
        total_listed_price += product.price * quantity
        total_offer_price += final_price * quantity

    delivery_charge = Decimal('40.00') if total_offer_price < Decimal('1000.00') else Decimal('0.00')
    coupon_discount = order.discount_coupon_amount
    
    grand_total = (total_offer_price - coupon_discount) + delivery_charge

    # Prepare order items with calculated values
    processed_items = []
    for item in order_items:
        product = item.product
        product_offer = ProductOffer.objects.filter(product=product, is_active=True).first()
        category_offer = CategoryOffer.objects.filter(category=product.category, is_active=True).first()

        # Calculate the final price based on the best offer
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
        

        quantity = item.quantity
        item_offer_total = final_price * quantity
        
        # Calculate coupon discount for this item proportionally
        item_coupon_discount = Decimal('0.00')
        if total_offer_price > 0 and coupon_discount > 0:
            item_coupon_discount = (item_offer_total / total_offer_price) * coupon_discount
        
        discounted_price = final_price - (item_coupon_discount / quantity)
        
        processed_items.append({
            'name': item.product.name,
            'quantity': quantity,
            'listed_price': product.price,
            'offer_price': final_price,
            'coupon_discount': item_coupon_discount.quantize(Decimal('0.00')),
            'discount': discounted_price,
            'subtotal': (final_price * quantity) - item_coupon_discount,
        })

    context = {
        'order': order,
        'order_items': processed_items,
        'delivery_charge': delivery_charge,
        'coupon_discount': coupon_discount.quantize(Decimal('0.00')),
        'grand_total': grand_total.quantize(Decimal('0.00')),
        'total_offer_price': total_offer_price.quantize(Decimal('0.00')),
        'total_listed_price': total_listed_price.quantize(Decimal('0.00')),
    }

    # Generate PDF
    html_string = render_to_string('user/invoice_template.html', context)
    html = HTML(string=html_string)
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{order.id}.pdf"'
    return response






###############################################USER SIDE END###############################################



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
ORDERS LIST
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def order_management(request):
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    payment_status_filter = request.GET.get('payment_status', '').strip()
    payment_method_filter = request.GET.get('payment_method', '').strip()
    sort_by = request.GET.get('sort', '-created_at')

    orders = Order.objects.select_related('user', 'shipping_address').prefetch_related('items__product').all()

    # Search filter
    if search_query:
        orders = orders.filter(
            Q(id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(shipping_address__phone__icontains=search_query) |
            Q(items__product__name__icontains=search_query)
        ).distinct()

    # Status filter (supports both Order status and item-level return/cancel statuses)
    if status_filter:
        if status_filter == 'return_requested':
            orders = orders.filter(items__status='return_requested').distinct()
        elif status_filter == 'returned':
            orders = orders.filter(Q(status='returned') | Q(items__status='returned')).distinct()
        elif status_filter == 'return_denied':
            orders = orders.filter(items__status='return_denied').distinct()
        elif status_filter == 'canceled':
            orders = orders.filter(Q(status='canceled') | Q(items__status='canceled')).distinct()
        elif status_filter == 'processing':
            orders = orders.filter(status='processing')
        elif status_filter == 'pending':
            orders = orders.filter(status='pending')
        elif status_filter == 'completed':
            orders = orders.filter(status='completed')
        else:
            orders = orders.filter(status=status_filter)

    # Payment Status filter
    if payment_status_filter:
        orders = orders.filter(payment_status__iexact=payment_status_filter)

    # Payment Method filter
    if payment_method_filter:
        orders = orders.filter(payment_method__iexact=payment_method_filter)

    # Sorting
    valid_sorts = {
        '-created_at': '-created_at',
        'created_at': 'created_at',
        '-total_price': '-total_price',
        'total_price': 'total_price',
    }
    orders = orders.order_by(valid_sorts.get(sort_by, '-created_at'))

    # Overall statistics
    all_orders = Order.objects.all()
    all_items = OrderItem.objects.all()
    stats = {
        'total_orders': all_orders.count(),
        'total_revenue': all_orders.filter(~Q(status='canceled')).aggregate(total=Sum('total_price'))['total'] or Decimal('0.00'),
        'processing_count': all_orders.filter(status__in=['processing', 'pending']).count(),
        'completed_count': all_orders.filter(status='completed').count(),
        'return_requests_count': all_items.filter(status='return_requested').count(),
        'returned_items_count': all_items.filter(status='returned').count(),
        'canceled_returned_count': all_orders.filter(status__in=['canceled', 'returned']).count(),
    }

    order_status_choices = [
        ('return_requested', '⚠️ Return Requested (Action Needed)'),
        ('returned', '↩️ Returned Items'),
        ('processing', 'Processing'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
    ]

    page = request.GET.get('page', 1) 
    paginator = Paginator(orders, 10) 

    try:
        paginated_orders = paginator.page(page)
    except PageNotAnInteger:
        paginated_orders = paginator.page(1)
    except EmptyPage:
        paginated_orders = paginator.page(paginator.num_pages)

    # Attach return flags to paginated orders for quick badge display
    for o in paginated_orders:
        item_list = list(o.items.all())
        o.has_return_requests = any(i.status == 'return_requested' for i in item_list)
        o.has_returned_items = any(i.status == 'returned' for i in item_list)
        o.return_requested_count = sum(1 for i in item_list if i.status == 'return_requested')
        o.returned_count = sum(1 for i in item_list if i.status == 'returned')

    return render(request, 'admin/order_admin.html', {
        'orders': paginated_orders,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'payment_status_filter': payment_status_filter,
        'payment_method_filter': payment_method_filter,
        'sort_by': sort_by,
        'order_status_choices': order_status_choices,
    })


"""
ORDER DETAILS
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def admin_order_details(request, order_id):
    order = get_object_or_404(Order.objects.select_related('user', 'shipping_address', 'coupon'), id=order_id)
    order_items = list(order.items.select_related('product', 'product_variant').all().order_by('id'))

    subtotal_items = Decimal('0.00')
    pending_returns = []
    returned_items = []
    for item in order_items:
        # Use recorded item purchase price (final_offer_price or price)
        item.final_price = item.final_offer_price if item.final_offer_price and item.final_offer_price > 0 else item.price
        item.subtotal = item.quantity * item.final_price
        subtotal_items += item.subtotal
        item.allowed_statuses = item.get_allowed_next_statuses()
        if item.status == 'return_requested':
            item.estimated_refund = calculate_order_item_refund(item)
            pending_returns.append(item)
        elif item.status == 'returned':
            returned_items.append(item)

    status_choices = OrderItem.ORDER_ITEM_STATUS_CHOICES

    total_refunded = WalletTransaction.objects.filter(
        order=order,
        transaction_type='credit'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return render(request, 'admin/order_details_admin.html', {
        'order': order,
        'order_items': order_items,
        'subtotal_items': subtotal_items,
        'status_choices': status_choices,
        'total_refunded': total_refunded,
        'pending_returns': pending_returns,
        'returned_items': returned_items,
        'has_pending_returns': len(pending_returns) > 0,
    })


"""
STATUS UPDATE
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
@require_POST
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    item_id = request.POST.get('item_id')
    new_status = request.POST.get('status')
    reason = request.POST.get('reason', '').strip()

    is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest' or 
               request.headers.get('Accept') == 'application/json' or
               request.POST.get('ajax') == 'true')

    if not item_id or not new_status:
        if is_ajax:
            return JsonResponse({"error": "Invalid request. Item ID and new status are required."}, status=400)
        messages.error(request, "Invalid request.")
        return redirect('admin_order_details', order_id=order.id)

    if new_status == 'return_requested':
        if is_ajax:
            return JsonResponse({"error": "Admins cannot request returns. Only users can initiate return requests."}, status=400)
        messages.error(request, "Admins cannot directly request returns.")
        return redirect('admin_order_details', order_id=order.id)

    def process_item_status(order_item, target_status):
        if not order_item.can_update_status(target_status):
            return False, Decimal('0.00'), f"Cannot transition from {order_item.get_status_display()} to {target_status}."

        refund_issued = Decimal('0.00')

        # If delivered and COD, mark payment as Paid
        if target_status == 'delivered' and order.payment_method == 'COD':
            order.payment_status = 'Paid'
            order.save(update_fields=['payment_status'])

        # Handle Return Approval
        if target_status in ['return', 'returned']:
            if order_item.product_variant:
                order_item.product_variant.stock += order_item.quantity
                order_item.product_variant.save()
            order_item.returned_at = timezone.now()
            order_item.status = 'returned'
            order_item.save()

            # Calculate and Process Refund
            refund_amount = calculate_order_item_refund(order_item)
            if refund_amount > Decimal('0.00'):
                process_order_item_refund(
                    order_item,
                    refund_amount,
                    action_type="Return",
                    reason=order_item.return_reason or reason or "Return approved by admin"
                )
                refund_issued = refund_amount

        # Handle Cancellation by Admin
        elif target_status == 'canceled':
            if order_item.product_variant:
                order_item.product_variant.stock += order_item.quantity
                order_item.product_variant.save()

            order_item.cancel_reason = reason or "Cancelled by Administrator"
            order_item.status = 'canceled'
            order_item.save()

            # Calculate and Process Refund (handles online payments, wallet, or pre-paid COD)
            refund_amount = calculate_order_item_refund(order_item)
            if refund_amount > Decimal('0.00'):
                process_order_item_refund(
                    order_item,
                    refund_amount,
                    action_type="Admin Cancellation",
                    reason=reason or "Cancelled by Administrator"
                )
                refund_issued = refund_amount

        elif target_status == 'return_denied':
            if reason:
                order_item.return_reason = f"{order_item.return_reason or ''} [Admin note: {reason}]"
            order_item.status = 'return_denied'
            order_item.save()

        else:
            order_item.status = target_status
            order_item.save()

        return True, refund_issued, "Updated"

    # Batch Update All Eligible Items
    if item_id == 'all':
        updated_count = 0
        total_batch_refund = Decimal('0.00')
        for itm in order.items.all():
            if not itm.can_update_status(new_status):
                continue
            ok, itm_refund, _ = process_item_status(itm, new_status)
            if ok:
                updated_count += 1
                total_batch_refund += (itm_refund or Decimal('0.00'))

        order.update_order()
        order.refresh_from_db()

        # Update order master payment_status if all items are canceled/returned
        final_items = order.items.all()
        if all(i.status in ['canceled', 'returned'] for i in final_items) and order.payment_status in ['Paid', 'Refunded']:
            order.payment_status = 'Refunded'
            order.save(update_fields=['payment_status'])
            # Restore coupon usage if all items were canceled
            if order.coupon and all(i.status == 'canceled' for i in final_items):
                CouponUsage.objects.filter(user=order.user, coupon=order.coupon).delete()

        msg = f"Successfully updated {updated_count} item(s) to '{new_status}'."
        if total_batch_refund > Decimal('0.00'):
            msg += f" Total refund of ₹{total_batch_refund:.2f} credited to customer wallet."

        if is_ajax:
            return JsonResponse({
                "success": True,
                "message": msg,
                "refund_amount": str(total_batch_refund),
                "redirect_url": reverse('admin_order_details', args=[order.id])
            })
        messages.success(request, msg)
        return redirect('admin_order_details', order_id=order.id)

    # Single Item Update
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)
    ok, refund_amt, error_msg = process_item_status(order_item, new_status)

    if not ok:
        if is_ajax:
            return JsonResponse({"error": error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('admin_order_details', order_id=order.id)

    order.update_order()
    order.refresh_from_db()

    # Update order master payment_status if all items are canceled/returned
    final_items = order.items.all()
    if all(i.status in ['canceled', 'returned'] for i in final_items) and order.payment_status in ['Paid', 'Refunded']:
        order.payment_status = 'Refunded'
        order.save(update_fields=['payment_status'])
        # Restore coupon usage if all items were canceled
        if order.coupon and all(i.status == 'canceled' for i in final_items):
            CouponUsage.objects.filter(user=order.user, coupon=order.coupon).delete()

    success_msg = f"Item '{order_item.product.name}' status updated to '{new_status}'."
    if refund_amt and refund_amt > Decimal('0.00'):
        success_msg += f" Refund of ₹{refund_amt:.2f} credited to customer wallet."

    if is_ajax:
        return JsonResponse({
            "success": True,
            "message": success_msg,
            "refund_amount": str(refund_amt or '0.00'),
            "redirect_url": reverse('admin_order_details', args=[order.id])
        })

    messages.success(request, success_msg)
    return redirect('admin_order_details', order_id=order.id)


###############################################ADMIN SIDE END###############################################
