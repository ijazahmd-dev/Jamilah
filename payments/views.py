import razorpay
from decimal import Decimal
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib import messages
from django.urls import reverse

from orders.models import Order, OrderItem
from cart.models import Cart, CartItem
from wallet.models import Wallet, WalletTransaction
from coupons.models import CouponUsage

logger = logging.getLogger(__name__)

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


@csrf_exempt
def initiate_payment(request):
    """Initiate Razorpay payment for an existing order from initial checkout."""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        user = request.user
        cart_details = request.session.get('cart_details', {})
        order_id = cart_details.get('order_id')
        if not order_id:
            return JsonResponse({"error": "Order not found in session"}, status=400)

        order = Order.objects.get(id=order_id, user=user)
        if order.payment_method != "razorpay":
            return JsonResponse({"error": "Invalid payment method for this order"}, status=400)

        amount = int(order.total_price * 100)  # Convert to paise
        razorpay_order = razorpay_client.order.create({
            "amount": amount,
            "currency": "INR",
            "receipt": f"order_{order.id}",
            "notes": {"django_order_id": order.id, "user_id": user.id},
            "payment_capture": 1  # Auto-capture payment
        })

        order.retry_payment_attempts += 1
        order.save(update_fields=['retry_payment_attempts'])

        callback_url = request.build_absolute_uri(reverse('payments:verify_payment', args=[order.id]))
        return JsonResponse({
            "razorpay_order_id": razorpay_order["id"],
            "django_order_id": order.id,
            "order_id": order.id,
            "razorpay_merchant_key": settings.RAZORPAY_KEY_ID,
            "razorpay_amount": amount,
            "currency": "INR",
            "callback_url": callback_url,
        })
    except Order.DoesNotExist:
        logger.error("Order not found for payment initiation")
        return JsonResponse({"error": "Order not found"}, status=404)
    except Exception as e:
        logger.error(f"Error in initiate_payment: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def verify_payment(request, order_id):
    """Verify Razorpay payment signature and finalize order."""
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('Accept', '') or
        'application/x-www-form-urlencoded' in (request.content_type or '')
    )

    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method")

    try:
        payment_id = request.POST.get('razorpay_payment_id', '')
        razorpay_order_id = request.POST.get('razorpay_order_id', '')
        signature = request.POST.get('razorpay_signature', '')

        failure_url = reverse('payments:payment_failure', args=[order_id])

        if not all([payment_id, razorpay_order_id, signature]):
            messages.error(request, "Missing payment authorization data")
            if is_ajax:
                return JsonResponse({"success": False, "error": "Missing payment data", "redirect_url": failure_url}, status=400)
            return redirect(failure_url)

        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }

        razorpay_client.utility.verify_payment_signature(params_dict)
        order = Order.objects.get(id=order_id, user=request.user)
        payment = razorpay_client.payment.fetch(payment_id)

        # If payment is authorized but not captured yet, capture it now
        if payment.get('status') == 'authorized':
            payment = razorpay_client.payment.capture(payment_id, payment['amount'])

        if payment.get('status') == 'captured':
            order.payment_status = 'Paid'
            order.status = 'pending'
            order.payment_method = 'razorpay'
            order.save(update_fields=['payment_status', 'status', 'payment_method'])

            # Update active (non-canceled) order items to order_placed
            for item in order.items.exclude(status='canceled'):
                item.status = 'order_placed'
                item.save(update_fields=['status'])

            # Record coupon usage if coupon was applied
            if order.coupon:
                CouponUsage.objects.get_or_create(user=order.user, coupon=order.coupon)

            # Clear cart safely
            cart = Cart.objects.filter(user=order.user).first()
            if cart:
                CartItem.objects.filter(cart=cart).delete()
            if 'cart_details' in request.session:
                del request.session['cart_details']

            success_url = reverse('payments:payment_success', args=[order.id])
            if is_ajax:
                return JsonResponse({"success": True, "redirect_url": success_url})
            return redirect(success_url)
        else:
            order.payment_status = 'Pending'
            order.save(update_fields=['payment_status'])
            messages.error(request, "Payment was not captured successfully by the gateway.")
            if is_ajax:
                return JsonResponse({"success": False, "error": "Payment not captured", "redirect_url": failure_url}, status=400)
            return redirect(failure_url)

    except razorpay.errors.SignatureVerificationError:
        order = Order.objects.filter(id=order_id, user=request.user).first()
        if order:
            order.payment_status = 'Pending'
            order.save(update_fields=['payment_status'])
        messages.error(request, "Payment security signature verification failed.")
        failure_url = reverse('payments:payment_failure', args=[order_id])
        if is_ajax:
            return JsonResponse({"success": False, "error": "Signature verification failed", "redirect_url": failure_url}, status=400)
        return redirect(failure_url)

    except Exception as e:
        logger.error(f"Error in verify_payment: {str(e)}")
        order = Order.objects.filter(id=order_id, user=request.user).first()
        if order:
            order.payment_status = 'Pending'
            order.save(update_fields=['payment_status'])
        messages.error(request, f"Payment verification error: {str(e)}")
        failure_url = reverse('payments:payment_failure', args=[order_id])
        if is_ajax:
            return JsonResponse({"success": False, "error": str(e), "redirect_url": failure_url}, status=500)
        return redirect(failure_url)


def payment_success(request, order_id):
    """Display payment success page with full order details."""
    from orders.views import get_order_confirmation_context
    order = get_object_or_404(Order, id=order_id, user=request.user)
    context = get_order_confirmation_context(order, is_success=True, show_retry=False)
    return render(request, 'user/order_confirm.html', context)


def payment_failure(request, order_id):
    """Display payment failure page with retry capability."""
    from orders.views import get_order_confirmation_context
    order = get_object_or_404(Order, id=order_id, user=request.user)
    show_retry = order.payment_status != 'Paid' and order.status != 'canceled'
    context = get_order_confirmation_context(order, is_success=False, show_retry=show_retry)
    return render(request, 'user/order_confirm.html', context)


@login_required
def retry_payment(request, order_id):
    """
    Interactive retry payment view supporting both Razorpay online gateway and Jamilah Wallet.
    Enforces order validation, inventory sanity, and accurate payable calculation.
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # 1. Check if already paid
    if order.payment_status == 'Paid':
        messages.info(request, "This order is already paid for.")
        first_item = order.items.first()
        if first_item:
            return redirect('user_order_details', item_id=first_item.id)
        return redirect('user_orders')

    # 2. Check if canceled or returned
    if order.status in ['canceled', 'returned']:
        messages.warning(request, "This order has been canceled and payment cannot be retried.")
        return redirect('user_orders')

    # 3. Active items check (exclude canceled items)
    active_items = order.items.exclude(status='canceled').select_related('product', 'product_variant')
    if not active_items.exists():
        order.status = 'canceled'
        order.save(update_fields=['status'])
        messages.warning(request, "All items in this order have been canceled.")
        return redirect('user_orders')

    # 4. Calculate net payable amount based on active items and coupon
    active_items_total = sum(
        i.quantity * (i.final_offer_price if i.final_offer_price and i.final_offer_price > 0 else i.price)
        for i in active_items
    )
    coupon_discount = order.discount_coupon_amount or Decimal('0.00')
    payable_amount = max(Decimal('0.00'), active_items_total - coupon_discount)

    # Reconcile order total_price if needed
    if order.total_price != payable_amount:
        order.total_price = payable_amount
        order.save(update_fields=['total_price'])

    # Fetch user wallet details
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    can_pay_with_wallet = wallet.balance >= payable_amount

    # Handle POST (Payment Execution)
    if request.method == "POST":
        is_ajax = (
            request.headers.get('x-requested-with') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('Accept', '') or
            request.POST.get('ajax') == 'true'
        )
        payment_method = request.POST.get('payment_method', 'razorpay').strip().lower()

        # A. RETRY VIA WALLET
        if payment_method == 'wallet':
            if wallet.balance < payable_amount:
                err_msg = f"Insufficient wallet balance. Available: ₹{wallet.balance:,.2f}, Required: ₹{payable_amount:,.2f}."
                if is_ajax:
                    return JsonResponse({"error": err_msg}, status=400)
                messages.error(request, err_msg)
                return redirect('payments:retry_payment', order_id=order.id)

            # Deduct from wallet
            wallet.balance -= payable_amount
            wallet.save(update_fields=['balance'])

            # Record wallet debit transaction
            WalletTransaction.objects.create(
                wallet=wallet,
                order=order,
                amount=payable_amount,
                transaction_type='debit',
                description=f"Payment for Order #{order.id} (Retry Payment)"
            )

            # Update order and items
            order.payment_method = 'wallet'
            order.payment_status = 'Paid'
            order.status = 'pending'
            order.retry_payment_attempts += 1
            order.save(update_fields=['payment_method', 'payment_status', 'status', 'retry_payment_attempts'])

            for itm in active_items:
                itm.status = 'order_placed'
                itm.save(update_fields=['status'])

            if order.coupon:
                CouponUsage.objects.get_or_create(user=request.user, coupon=order.coupon)

            # Clear residual cart items
            cart = Cart.objects.filter(user=request.user).first()
            if cart:
                CartItem.objects.filter(cart=cart).delete()
            if 'cart_details' in request.session:
                del request.session['cart_details']

            success_url = reverse('payments:retry_order_confirm', args=[order.id])
            if is_ajax:
                return JsonResponse({
                    "success": True,
                    "method": "wallet",
                    "message": f"Payment of ₹{payable_amount:,.2f} completed successfully using your Jamilah Wallet balance.",
                    "redirect_url": success_url
                })
            messages.success(request, "Payment completed successfully using your Jamilah Wallet balance.")
            return redirect(success_url)

        # B. RETRY VIA RAZORPAY
        elif payment_method == 'razorpay':
            amount_in_paise = int(payable_amount * 100)
            try:
                razorpay_order = razorpay_client.order.create({
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "receipt": f"retry_order_{order.id}",
                    "notes": {"django_order_id": order.id, "user_id": request.user.id},
                    "payment_capture": 1
                })

                order.payment_method = 'razorpay'
                order.retry_payment_attempts += 1
                order.save(update_fields=['payment_method', 'retry_payment_attempts'])

                callback_url = request.build_absolute_uri(reverse('payments:verify_payment', args=[order.id]))
                return JsonResponse({
                    "success": True,
                    "method": "razorpay",
                    "razorpay_order_id": razorpay_order["id"],
                    "razorpay_merchant_key": settings.RAZORPAY_KEY_ID,
                    "razorpay_amount": amount_in_paise,
                    "currency": "INR",
                    "callback_url": callback_url,
                    "order_id": order.id,
                    "django_order_id": order.id
                })
            except Exception as e:
                logger.error(f"Error creating Razorpay order for retry: {str(e)}")
                return JsonResponse({"error": f"Failed to initialize payment gateway: {str(e)}"}, status=500)

        else:
            return JsonResponse({"error": "Invalid payment method selected for retry."}, status=400)

    # Handle GET: Render retry payment confirmation page
    from orders.views import get_order_confirmation_context
    context = get_order_confirmation_context(order, is_success=False, show_retry=True)
    context.update({
        'wallet': wallet,
        'can_pay_with_wallet': can_pay_with_wallet,
        'payable_amount': payable_amount,
        'active_items': active_items,
        'active_items_total': active_items_total,
    })
    return render(request, 'user/retry_payment_confirmation.html', context)


def retry_order_confirm(request, order_id):
    """Display retry payment success page."""
    from orders.views import get_order_confirmation_context
    order = get_object_or_404(Order, id=order_id, user=request.user)
    context = get_order_confirmation_context(order, is_success=True, show_retry=False)
    context['is_retry_success'] = True
    return render(request, 'user/order_confirm.html', context)
