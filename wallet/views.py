from django.shortcuts import render,get_object_or_404,redirect
from .models import Wallet, WalletTransaction
from django.contrib.auth.decorators import login_required,user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.urls import reverse
from django.contrib.auth.models import User
from django.db.models import Sum, Q, Count
from functools import wraps
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import razorpay
import json
import logging

logger = logging.getLogger(__name__)

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))




# Admin access check
def is_admin(user):
    return user.is_authenticated and user.is_staff





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
WALLET PAGE
"""
@login_required
def wallet_view(request):
    try:
        wallet = Wallet.objects.get(user=request.user)
    except Wallet.DoesNotExist:
        wallet = Wallet.objects.create(user=request.user, balance=0.00)
    
    # Base transactions
    base_transactions = WalletTransaction.objects.filter(wallet=wallet)
    
    # Financial KPI summary
    total_credited = base_transactions.filter(transaction_type='credit').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_debited = base_transactions.filter(transaction_type='debit').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_tx_count = base_transactions.count()

    # Filters & Search
    filter_type = request.GET.get('filter', 'all').strip().lower()
    search_query = request.GET.get('q', '').strip()
    
    transactions = base_transactions.order_by('-created_at')
    if filter_type == 'credit':
        transactions = transactions.filter(transaction_type='credit')
    elif filter_type == 'debit':
        transactions = transactions.filter(transaction_type='debit')

    if search_query:
        transactions = transactions.filter(
            Q(description__icontains=search_query) |
            Q(order__id__icontains=search_query)
        )
    
    page = request.GET.get('page', 1) 
    paginator = Paginator(transactions, 10)
    
    try:
        transactions = paginator.page(page)
    except PageNotAnInteger:
        transactions = paginator.page(1)
    except EmptyPage:
        transactions = paginator.page(paginator.num_pages)
    
    return render(request, 'user/wallet.html', {
        'wallet': wallet,
        'transactions': transactions,
        'filter_type': filter_type,
        'search_query': search_query,
        'total_credited': total_credited,
        'total_debited': total_debited,
        'total_tx_count': total_tx_count,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    })


@login_required
def initiate_wallet_topup(request):
    """Create a Razorpay order for wallet top-up."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)

    try:
        raw_amount = request.POST.get('amount')
        if not raw_amount and request.body:
            try:
                body = json.loads(request.body)
                raw_amount = body.get('amount')
            except Exception:
                pass

        if not raw_amount:
            return JsonResponse({"success": False, "error": "Please enter an amount to top up."}, status=400)

        try:
            amount = Decimal(str(raw_amount).strip())
        except Exception:
            return JsonResponse({"success": False, "error": "Please enter a valid numeric amount."}, status=400)

        if amount < Decimal('1.00'):
            return JsonResponse({"success": False, "error": "Minimum top-up amount is ₹1.00."}, status=400)

        if amount > Decimal('100000.00'):
            return JsonResponse({"success": False, "error": "Maximum top-up amount is ₹1,00,000.00."}, status=400)

        amount_paise = int(amount * 100)
        timestamp = int(timezone.now().timestamp())
        receipt = f"topup_{request.user.id}_{timestamp}"

        razorpay_order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": {
                "transaction_type": "wallet_topup",
                "user_id": request.user.id,
                "username": request.user.username,
                "amount": str(amount),
            },
            "payment_capture": 1
        })

        user_name = request.user.get_full_name() or request.user.username

        return JsonResponse({
            "success": True,
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_merchant_key": settings.RAZORPAY_KEY_ID,
            "amount": amount_paise,
            "display_amount": str(amount),
            "currency": "INR",
            "user_name": user_name,
            "user_email": request.user.email or "",
            "user_contact": "",
        })
    except Exception as e:
        logger.error(f"Error in initiate_wallet_topup: {str(e)}")
        return JsonResponse({"success": False, "error": f"Failed to create Razorpay order: {str(e)}"}, status=500)


@login_required
@csrf_exempt
def verify_wallet_topup(request):
    """Verify Razorpay payment and credit user's wallet balance."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)

    try:
        payment_id = request.POST.get('razorpay_payment_id', '').strip()
        razorpay_order_id = request.POST.get('razorpay_order_id', '').strip()
        signature = request.POST.get('razorpay_signature', '').strip()

        if not (payment_id and razorpay_order_id and signature) and request.body:
            try:
                body = json.loads(request.body)
                payment_id = body.get('razorpay_payment_id', '').strip()
                razorpay_order_id = body.get('razorpay_order_id', '').strip()
                signature = body.get('razorpay_signature', '').strip()
            except Exception:
                pass

        if not all([payment_id, razorpay_order_id, signature]):
            return JsonResponse({"success": False, "error": "Missing payment verification parameters."}, status=400)

        # Verify signature with Razorpay utility
        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        razorpay_client.utility.verify_payment_signature(params_dict)

        # Fetch payment details from Razorpay
        payment = razorpay_client.payment.fetch(payment_id)

        # Capture payment if it is in authorized state
        if payment.get('status') == 'authorized':
            payment = razorpay_client.payment.capture(payment_id, payment['amount'])

        if payment.get('status') != 'captured':
            return JsonResponse({
                "success": False,
                "error": f"Payment status is '{payment.get('status')}'. Payment could not be captured."
            }, status=400)

        wallet, _ = Wallet.objects.get_or_create(user=request.user)

        # Idempotency check: Ensure payment_id has not already been credited
        existing_tx = WalletTransaction.objects.filter(description__icontains=payment_id).first()
        if existing_tx:
            return JsonResponse({
                "success": True,
                "message": "Payment has already been credited to your wallet.",
                "new_balance": f"{wallet.balance:.2f}"
            })

        # Calculate amount from Razorpay payment (paise to INR)
        paid_amount = Decimal(payment['amount']) / Decimal(100)

        # Credit wallet balance
        wallet.balance += paid_amount
        wallet.save()

        # Create wallet transaction record
        tx = WalletTransaction.objects.create(
            wallet=wallet,
            order=None,
            amount=paid_amount,
            transaction_type='credit',
            description=f"Wallet Top-Up via Razorpay (Payment ID: {payment_id})"
        )

        return JsonResponse({
            "success": True,
            "message": f"₹{paid_amount:.2f} successfully credited to your wallet!",
            "new_balance": f"{wallet.balance:.2f}",
            "transaction_id": tx.transaction_id,
        })
    except razorpay.errors.SignatureVerificationError:
        logger.error("Razorpay signature verification failed during wallet top-up.")
        return JsonResponse({"success": False, "error": "Signature verification failed. The payment could not be authenticated."}, status=400)
    except Exception as e:
        logger.error(f"Error in verify_wallet_topup: {str(e)}")
        return JsonResponse({"success": False, "error": f"Payment verification error: {str(e)}"}, status=500)



@admin_required
@never_cache
@user_passes_test(is_admin)
def admin_wallet_transaction_list(request):
    query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'all').strip()
    user_id = request.GET.get('user_id', '').strip()

    transactions_qs = WalletTransaction.objects.select_related('wallet', 'wallet__user', 'order').all().order_by('-created_at')

    selected_user = None
    if user_id:
        try:
            selected_user = User.objects.filter(id=user_id).first()
            if selected_user:
                transactions_qs = transactions_qs.filter(wallet__user=selected_user)
        except (ValueError, TypeError):
            pass

    if filter_type == 'credit':
        transactions_qs = transactions_qs.filter(transaction_type='credit')
    elif filter_type == 'debit':
        transactions_qs = transactions_qs.filter(transaction_type='debit')

    if query:
        transactions_qs = transactions_qs.filter(
            Q(transaction_id__icontains=query) |
            Q(wallet__user__username__icontains=query) |
            Q(wallet__user__email__icontains=query) |
            Q(description__icontains=query) |
            Q(order__id__icontains=query)
        )

    # Compute KPI statistics
    all_tx = WalletTransaction.objects.all()
    total_tx_count = all_tx.count()
    total_credits = all_tx.filter(transaction_type='credit').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_debits = all_tx.filter(transaction_type='debit').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_wallets = Wallet.objects.count()
    total_balance_held = Wallet.objects.aggregate(total=Sum('balance'))['total'] or Decimal('0.00')

    stats = {
        'total_count': total_tx_count,
        'total_credits': total_credits,
        'total_debits': total_debits,
        'total_wallets': total_wallets,
        'total_balance_held': total_balance_held,
    }

    # Customers list for user filter dropdown
    users_list = User.objects.filter(is_superuser=False).select_related('wallet').order_by('username')

    paginator = Paginator(transactions_qs, 15)
    page = request.GET.get('page', 1)

    try:
        transactions = paginator.page(page)
    except PageNotAnInteger:
        transactions = paginator.page(1)
    except EmptyPage:
        transactions = paginator.page(paginator.num_pages)

    return render(request, 'admin/wallet_transaction_list.html', {
        'transactions': transactions,
        'filter_type': filter_type,
        'user_id': user_id,
        'selected_user': selected_user,
        'query': query,
        'users_list': users_list,
        'stats': stats,
    })


@admin_required
@never_cache
@user_passes_test(is_admin)
def admin_wallet_transaction_detail(request, transaction_id):
    transaction = get_object_or_404(
        WalletTransaction.objects.select_related('wallet', 'wallet__user', 'order'),
        transaction_id=transaction_id
    )
    user = transaction.wallet.user
    order_url = reverse('admin_order_details', args=[transaction.order.id]) if transaction.order else None
    context = {
        'transaction': transaction,
        'user': user,
        'order_url': order_url,
    }
    return render(request, 'admin/wallet_transaction_detail.html', context)





