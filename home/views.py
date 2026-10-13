from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.http import JsonResponse
from django.core.validators import validate_email, ValidationError
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from category.models import Category
from products.models import Product
import random
from .forms import ContactForm
from .models import SisterhoodSubscriber
from coupons.models import Coupon
from django.middleware.csrf import get_token

# Create your views here.




from django.db.models import Count, Q
from offers.models import ProductOffer, CategoryOffer


def enrich_product_list(products, user_wishlist_ids):
    enriched = []
    for p in products:
        images_list = list(p.images.all())
        first_img = images_list[0] if len(images_list) > 0 else None
        second_img = images_list[1] if len(images_list) > 1 else None

        variants = list(p.variants.all())
        total_stock = sum(v.stock for v in variants) if variants else 0
        is_in_stock = total_stock > 0
        is_low_stock = 0 < total_stock <= 5

        enriched.append({
            'product': p,
            'first_image': first_img,
            'second_image': second_img,
            'total_stock': total_stock,
            'is_in_stock': is_in_stock,
            'is_low_stock': is_low_stock,
            'in_wishlist': p.id in user_wishlist_ids,
        })
    return enriched


@never_cache
def HomePage(request):
    categories = Category.objects.filter(is_listed=True).annotate(
        product_count=Count('product', filter=Q(product__is_listed=True))
    )

    user_wishlist_ids = set()
    if request.user.is_authenticated:
        from wishlist.models import WishlistItem
        user_wishlist_ids = set(
            WishlistItem.objects.filter(wishlist__user=request.user).values_list('product_id', flat=True)
        )

    base_qs = Product.objects.filter(
        is_listed=True,
        category__is_listed=True
    ).select_related('category').prefetch_related('images', 'variants', 'review_set')

    # 1. Featured Products
    featured_qs = list(base_qs.order_by('-created_at')[:4])
    featured_products = enrich_product_list(featured_qs, user_wishlist_ids)

    # 2. Popular Products
    popular_qs = list(base_qs.order_by('created_at')[:4])
    popular_products = enrich_product_list(popular_qs, user_wishlist_ids)

    # 3. Bestseller Products
    bestseller_qs = list(base_qs.order_by('id')[:8])
    bestseller_products = enrich_product_list(bestseller_qs, user_wishlist_ids)

    # 4. New Arrivals
    newarrival_qs = list(base_qs.order_by('-created_at')[:8])
    newarrival_products = enrich_product_list(newarrival_qs, user_wishlist_ids)

    # Active Discounts
    cat_discounts = list(CategoryOffer.objects.filter(is_active=True).values_list('discount_percentage', flat=True))
    prod_discounts = list(ProductOffer.objects.filter(is_active=True).values_list('discount_percentage', flat=True))
    all_discounts = cat_discounts + prod_discounts
    best_discount = int(max(all_discounts)) if all_discounts else 20

    context = {
        'categories': categories,
        'featured_products': featured_products,
        'popular_products': popular_products,
        'bestseller_products': bestseller_products,
        'newarrival_products': newarrival_products,
        'best_discount': best_discount,
        'csrf_token': get_token(request),
    }

    return render(request, 'user/index.html', context)






"""
ABOUT PAGE
"""
@never_cache
def about(request):
    return render(request, 'user/about.html')






"""
CONTACT US PAGE
"""
@never_cache
def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['message']

            email_message = EmailMessage(
                subject=f"Contact Form: {subject}",
                body=f"Message from {name} ({email}):\n\n{message}",
                from_email=email, 
                to=[settings.CONTACT_EMAIL],
                reply_to=[email],
            )

            email_message.send()

            return redirect('contact_success')
    else:
        form = ContactForm()

    return render(request, 'user/contact.html', {'form': form})


"""
CONTACT SUCCESS PAGE
"""
def contact_success(request):
    return render(request, 'user/contact_success.html')


"""
THE ATELIER SISTERHOOD SUBSCRIPTION HANDLER
"""
def sisterhood_subscribe(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    email = request.POST.get('email', '').strip().lower()

    if not email:
        return JsonResponse({'status': 'error', 'message': 'Please provide an email address.'}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'status': 'error', 'message': 'Please enter a valid email address (e.g. name@example.com).'}, status=400)

    # Check if subscriber already exists
    existing = SisterhoodSubscriber.objects.filter(email=email).first()
    coupon_code = 'SISTERHOOD10'

    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.save(update_fields=['is_active'])

        return JsonResponse({
            'status': 'info',
            'already_subscribed': True,
            'coupon_code': coupon_code,
            'message': 'You are already a cherished member of The Atelier Sisterhood! Use code SISTERHOOD10 for 10% off your next couture purchase.'
        })

    # Create new subscriber
    subscriber = SisterhoodSubscriber.objects.create(email=email, is_active=True)

    # Prepare luxury welcome email
    site_url = request.build_absolute_uri('/')
    subject = "✨ Welcome to The Atelier Sisterhood | Your Exclusive 10% Welcome Gift"

    try:
        html_message = render_to_string('emails/sisterhood_welcome.html', {
            'email': email,
            'coupon_code': coupon_code,
            'site_url': site_url,
        })
    except Exception as tmpl_err:
        print(f"Error rendering sisterhood email template: {tmpl_err}")
        html_message = None

    plain_message = f"""As-salamu alaykum and welcome to The Atelier Sisterhood Circle!

"Grace in Every Drape. Devotion in Every Stitch."

We are honored to welcome you into our global circle of women who cherish elegance, modesty, and spiritual devotion.

YOUR INAUGURAL MEMBER GIFT:
Enjoy 10% OFF your next purchase across all curated abayas, prayer dresses, and couture collections!
Coupon Code: {coupon_code}
(Use at checkout on purchases above ₹500)

WHAT TO EXPECT AS A MEMBER:
✦ Private Atelier Previews: First access to seasonal drops and limited festive releases
✦ Artisan Lookbooks: Editorial drape styling tips & fine fabric care insights
✦ VIP Concierge Care: Direct assistance with custom sizing and priority order handling

Explore our collections: {site_url}shop/

With warmth and elegance,
The Jamilah Atelier Team
"""

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None) or 'contact@jamilah.com'

    email_sent = False
    try:
        msg = EmailMultiAlternatives(subject, plain_message, from_email, [email])
        if html_message:
            msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
        email_sent = True
        subscriber.welcome_email_sent = True
        subscriber.save(update_fields=['welcome_email_sent'])
    except Exception as e:
        print(f"Notice: Could not dispatch live email to {email}: {e}")

    return JsonResponse({
        'status': 'success',
        'email_sent': email_sent,
        'coupon_code': coupon_code,
        'message': f'Welcome to The Atelier Sisterhood! We have dispatched your private welcome note with your exclusive 10% voucher code ({coupon_code}) to your inbox.'
    })
