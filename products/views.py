from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from admin_side.views import is_admin
from .models import Product,ProductImage,ProductVariant
from django.core.paginator import Paginator,EmptyPage,PageNotAnInteger
from category.models import Category
from decimal import Decimal, InvalidOperation
import base64
import uuid
from django.core.files.base import ContentFile
from django.contrib import messages
import logging
from django.views.decorators.cache import never_cache
import random
from django.http import JsonResponse
import json
from reviews.models import Review
from functools import wraps
from django.urls import reverse




# Create your views here.







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
PRODUCT LISTING
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def product_list(request):
    query = request.GET.get('q', '')
    products = Product.objects.all()

    if query:
        products = products.filter(name__icontains=query)

    # Sort products to show the last added products first
    products = products.order_by('-id')

    page = request.GET.get('page', 1)
    paginator = Paginator(products, 8)

    try:
        paginated_products = paginator.page(page)
    except PageNotAnInteger:
        paginated_products = paginator.page(1)
    except EmptyPage:
        paginated_products = paginator.page(paginator.num_pages)

   
    categories = Category.objects.all()
    return render(request, 'admin/product_list.html', {
        'products': paginated_products,
        'categories': categories,
        'query': query,
    })





"""
CREATE PRODUCT
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def create_product(request):
    logger = logging.getLogger(__name__)

    if request.method == "POST":
        name = request.POST.get('product_name', '').strip()
        description = request.POST.get('description', '').strip()
        category_id = request.POST.get('category', '').strip()
        price_str = request.POST.get('price', '').strip()
        product_images = request.POST.getlist('product_images[]')

        form_data = {
            'product_name': name,
            'description': description,
            'category': category_id,
            'price': price_str,
            'product_images': product_images
        }

        errors = []

        # Product name validation
        if not name:
            errors.append("Product name is required and cannot be empty or only spaces.")
        elif len(name) < 2 or len(name) > 100:
            errors.append("Product name must be between 2 and 100 characters.")

        # Description validation
        if not description:
            errors.append("Description is required and cannot be empty or only spaces.")
        elif len(description) < 5 or len(description) > 3000:
            errors.append("Description must be between 5 and 3000 characters.")

        # Price validation
        try:
            price = Decimal(price_str)
            if price <= Decimal('0.00'):
                errors.append("Price must be greater than zero.")
            elif price > Decimal('1000000.00'):
                errors.append("Price cannot exceed ₹1,000,000.")
        except (InvalidOperation, ValueError):
            errors.append("Price must be a valid decimal number.")

        # Category validation
        category = None
        if not category_id:
            errors.append("Category is required.")
        else:
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                errors.append("Selected category does not exist.")

        # Product images validation
        if not product_images:
            errors.append("Please upload at least one image.")
        else:
            valid_images_data = []
            for idx, base64_image in enumerate(product_images):
                try:
                    if ',' in base64_image:
                        header, imgstr = base64_image.split(';base64,')
                    else:
                        imgstr = base64_image
                    decoded_image = base64.b64decode(imgstr)
                    if len(decoded_image) > 5 * 1024 * 1024:
                        errors.append(f"Image {idx+1} exceeds maximum allowed size of 5MB.")
                    else:
                        valid_images_data.append(decoded_image)
                except Exception:
                    errors.append(f"Image {idx+1} is not a valid base64 image.")

        if errors:
            for err in errors:
                messages.error(request, err)
            categories = Category.objects.filter(is_listed=True)
            return render(request, 'admin/add_product.html', {
                'categories': categories,
                'form_data': form_data,
                'errors': errors,
            })

        try:
            product = Product.objects.create(
                name=name,
                description=description,
                category=category,
                price=price,
            )

            for decoded_image in valid_images_data:
                image_file = ContentFile(decoded_image, name=f'product_{product.id}_{uuid.uuid4()}.jpg')
                ProductImage.objects.create(product=product, image=image_file)

            messages.success(request, "Product created successfully!")
            return redirect('product_management')

        except Exception as e:
            logger.error(f"Product creation failed: {e}")
            messages.error(request, "An unexpected error occurred while creating product. Please try again.")
            categories = Category.objects.filter(is_listed=True)
            return render(request, 'admin/add_product.html', {
                'categories': categories,
                'form_data': form_data,
                'errors': ["Error creating product. Please check the form."],
            })

    categories = Category.objects.filter(is_listed=True)
    return render(request, 'admin/add_product.html', {'categories': categories})




"""
EDIT PRODUCT
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        name = request.POST.get('product_name', '').strip()
        description = request.POST.get('description', '').strip()
        category_id = request.POST.get('category', '').strip()
        price_str = request.POST.get('price', '').strip()

        form_data = {
            'product_name': name,
            'description': description,
            'category': category_id,
            'price': price_str,
        }

        errors = []

        if not name:
            errors.append("Product name is required and cannot be empty or only spaces.")
        elif len(name) < 2 or len(name) > 100:
            errors.append("Product name must be between 2 and 100 characters.")

        if not description:
            errors.append("Description is required and cannot be empty or only spaces.")
        elif len(description) < 5 or len(description) > 3000:
            errors.append("Description must be between 5 and 3000 characters.")

        try:
            price = Decimal(price_str)
            if price <= Decimal('0.00'):
                errors.append("Price must be greater than zero.")
            elif price > Decimal('1000000.00'):
                errors.append("Price cannot exceed ₹1,000,000.")
        except (InvalidOperation, ValueError):
            errors.append("Price must be a valid decimal number.")

        category = None
        if not category_id:
            errors.append("Category is required.")
        else:
            try:
                category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                errors.append("Selected category does not exist.")

        if errors:
            for err in errors:
                messages.error(request, err)
            categories = Category.objects.filter(is_listed=True)
            return render(request, 'admin/edit_product.html', {
                'product': product,
                'categories': categories,
                'form_data': form_data,
                'errors': errors,
            })

        try:
            product.name = name
            product.description = description
            product.price = price
            product.category = category
            product.save()

            # Handle new cropped images
            new_images = request.POST.getlist('product_images[]')
            if new_images:
                for base64_image in new_images:
                    try:
                        if ',' in base64_image:
                            _, imgstr = base64_image.split(';base64,')
                        else:
                            imgstr = base64_image
                        decoded = base64.b64decode(imgstr)
                        image_file = ContentFile(decoded, name=f'product_{product.id}_{uuid.uuid4()}.jpg')
                        ProductImage.objects.create(product=product, image=image_file)
                    except Exception as img_e:
                        logger.error(f"Error saving product image: {img_e}")

            # Handle removed images
            delete_image_ids = request.POST.getlist('delete_images[]')
            if delete_image_ids:
                ProductImage.objects.filter(product=product, id__in=delete_image_ids).delete()

            messages.success(request, 'Product updated successfully.')
            return redirect('product_management')
        except Exception as e:
            messages.error(request, 'Error updating product. Please try again.')
            categories = Category.objects.filter(is_listed=True)
            return render(request, 'admin/edit_product.html', {
                'product': product,
                'categories': categories,
                'form_data': form_data,
                'errors': [str(e)],
            })

    categories = Category.objects.filter(is_listed=True)
    return render(request, 'admin/edit_product.html', {
        'product': product,
        'categories': categories,
    })




"""
VARIANT LISTING
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def variant_list(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    variants = product.variants.all().order_by('id')

    page = request.GET.get('page', 1)
    paginator = Paginator(variants, 10)
    try:
        variants = paginator.page(page)
    except PageNotAnInteger:
        variants = paginator.page(1)
    except EmptyPage:
        variants = paginator.page(paginator.num_pages)

    return render(request, 'admin/variant.html', {'product': product, 'variants': variants})




"""
ADD VARIANT
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def add_variant(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        color = request.POST.get('color', '').strip()
        size = request.POST.get('size', '').strip()
        stock_str = request.POST.get('stock', '').strip()

        errors = []

        if not color:
            errors.append("Color is required and cannot be empty or only spaces.")
        elif len(color) < 2 or len(color) > 30:
            errors.append("Color must be between 2 and 30 characters.")

        if not size:
            errors.append("Size is required and cannot be empty or only spaces.")
        elif len(size) < 1 or len(size) > 15:
            errors.append("Size must be between 1 and 15 characters.")

        stock = 0
        if not stock_str:
            errors.append("Stock is required.")
        else:
            try:
                stock = int(stock_str)
                if stock < 0:
                    errors.append("Stock cannot be negative.")
                elif stock > 100000:
                    errors.append("Stock cannot exceed 100,000 units.")
            except ValueError:
                errors.append("Stock must be a valid integer.")

        # Check for duplicates (same color and size for the product) - case insensitive
        if color and size and ProductVariant.objects.filter(
            product=product, color__iexact=color, size__iexact=size
        ).exists():
            errors.append(f"A variant with color '{color}' and size '{size}' already exists for this product.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'admin/add_variant.html', {
                'product': product,
                'errors': errors,
                'color': color,
                'size': size,
                'stock': stock_str
            })

        try:
            ProductVariant.objects.create(
                product=product,
                color=color,
                size=size,
                stock=stock
            )
            messages.success(request, 'Variant added successfully!')
            return redirect('variant', product_id=product_id)
        except Exception as e:
            messages.error(request, f"Error adding variant: {str(e)}")
            return render(request, 'admin/add_variant.html', {
                'product': product,
                'color': color,
                'size': size,
                'stock': stock_str
            })

    return render(request, 'admin/add_variant.html', {'product': product})




@admin_required
@never_cache
@user_passes_test(is_admin)
def update_variant(request, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id)

    if request.method == 'POST':
        color = request.POST.get('color', '').strip()
        size = request.POST.get('size', '').strip()
        stock_str = request.POST.get('stock', '').strip()

        errors = []

        if not color:
            errors.append("Color is required and cannot be empty or only spaces.")
        elif len(color) < 2 or len(color) > 30:
            errors.append("Color must be between 2 and 30 characters.")

        if not size:
            errors.append("Size is required and cannot be empty or only spaces.")
        elif len(size) < 1 or len(size) > 15:
            errors.append("Size must be between 1 and 15 characters.")

        stock = 0
        if not stock_str:
            errors.append("Stock is required.")
        else:
            try:
                stock = int(stock_str)
                if stock < 0:
                    errors.append("Stock cannot be negative.")
                elif stock > 100000:
                    errors.append("Stock cannot exceed 100,000 units.")
            except ValueError:
                errors.append("Stock must be a valid integer.")

        # Check for duplicate combination - case insensitive
        if color and size and ProductVariant.objects.filter(
            product=variant.product, color__iexact=color, size__iexact=size
        ).exclude(id=variant.id).exists():
            errors.append(f"Another variant with color '{color}' and size '{size}' already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'admin/edit_variant.html', {'variant': variant, 'errors': errors})

        try:
            variant.color = color
            variant.size = size
            variant.stock = stock
            variant.save()

            messages.success(request, 'Variant updated successfully.')
            return redirect('variant', product_id=variant.product_id)

        except Exception as e:
            messages.error(request, f"Error updating variant: {str(e)}")
            return render(request, 'admin/edit_variant.html', {'variant': variant})

    return render(request, 'admin/edit_variant.html', {'variant': variant})






"""
DELETE VARIANT
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def delete_variant(request, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id)
    product_id = variant.product.id
    variant_desc = f"{variant.color} / {variant.size}"
    is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest' or 
               request.headers.get('Accept') == 'application/json' or
               request.POST.get('ajax') == 'true')
    
    variant.delete()

    if is_ajax:
        return JsonResponse({'success': True, 'message': f"Variant '{variant_desc}' deleted successfully!"})

    messages.success(request, f"Variant '{variant_desc}' deleted successfully!")
    return redirect('variant', product_id=product_id)




"""
LISTING AND UNLISTING THE PRODUCTS
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def toggle_product_listing(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
        product.is_listed = not product.is_listed
        product.save()
        status = "listed" if product.is_listed else "unlisted"
        messages.success(request, f"Product successfully {status}")
    except Product.DoesNotExist:
        messages.error(request, "Product not found")
    return redirect('product_management')


"""
DELETE PRODUCT
"""
@admin_required
@never_cache
@user_passes_test(is_admin)
def delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product_name = product.name
    is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest' or 
               request.headers.get('Accept') == 'application/json' or
               request.POST.get('ajax') == 'true')

    product.delete()

    if is_ajax:
        return JsonResponse({'success': True, 'message': f"Product '{product_name}' deleted successfully!"})

    messages.success(request, f"Product '{product_name}' deleted successfully!")
    return redirect('product_management')
        


 
 
 







"""
PRODUCT DETAILS PAGE
"""
def product_details(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if request.method == "POST":
        color = request.POST.get('color', '').strip()
        size = request.POST.get('size', '').strip()
        variants = product.variants.filter(color__iexact=color, size__iexact=size)
        if not variants.exists():
            variants = product.variants.filter(size__iexact=size)
        variant_data = [{"color": v.color, "size": v.size, "stock": v.stock, "id": v.id} for v in variants]
        stock = variants.first().stock if variants.exists() else 0
        return JsonResponse({"variants": variant_data, "stock": stock})

    variants = product.variants.all()
    total_stock = sum(v.stock for v in variants)
    unique_colors = list(dict.fromkeys([v.color for v in variants if v.color]))
    all_sizes = list(dict.fromkeys([v.size for v in variants if v.size]))

    color_size_dict = {}
    for color in unique_colors:
        color_size_dict[color] = [
            {"size": v.size, "stock": v.stock, "id": v.id}
            for v in variants.filter(color=color)
        ]

    # If product has no colors defined, group under "Default"
    if not unique_colors and variants.exists():
        color_size_dict["Default"] = [
            {"size": v.size, "stock": v.stock, "id": v.id}
            for v in variants
        ]
        unique_colors = ["Default"]

    product_images = list(product.images.all())
    related_candidates = list(Product.objects.filter(category=product.category, is_listed=True).exclude(id=product_id))
    related_products = random.sample(related_candidates, min(len(related_candidates), 4)) if related_candidates else []

    can_review = False
    in_wishlist = False
    in_cart = False
    if request.user.is_authenticated:
        can_review = Review.can_review(request.user, product)
        from wishlist.models import WishlistItem
        from cart.models import CartItem
        in_wishlist = WishlistItem.objects.filter(wishlist__user=request.user, product=product).exists()
        in_cart = CartItem.objects.filter(cart__user=request.user, product_variant__product=product).exists()

    reviews = product.review_set.all().select_related('user').order_by('-created_at')
    review_count = reviews.count()
    avg_rating = round(float(product.average_rating), 1)

    # Rating distribution breakdown (5 down to 1)
    rating_breakdown = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for r in reviews:
        if r.rating in rating_breakdown:
            rating_breakdown[r.rating] += 1

    rating_stats = []
    for star in [5, 4, 3, 2, 1]:
        count = rating_breakdown[star]
        pct = round((count / review_count) * 100) if review_count > 0 else 0
        rating_stats.append({
            'star': star,
            'count': count,
            'percent': pct
        })

    # Pre-calculate active offer savings
    has_offer = product.has_offer
    best_offer_price = product.best_offer_price
    savings = (float(product.price) - float(best_offer_price)) if (has_offer and best_offer_price) else 0

    context = {
        'product': product,
        'unique_colors': unique_colors,
        'all_sizes': all_sizes,
        'color_size_dict': json.dumps(color_size_dict),
        'variants': variants,
        'total_stock': total_stock,
        'product_images': product_images,
        'related_products': related_products,
        'can_review': can_review,
        'in_wishlist': in_wishlist,
        'in_cart': in_cart,
        'reviews': reviews,
        'review_count': review_count,
        'avg_rating': avg_rating,
        'rating_stats': rating_stats,
        'has_offer': has_offer,
        'best_offer_price': best_offer_price,
        'savings': savings,
    }
    return render(request, 'user/product_details.html', context)
    

def quick_view(request, product_id):
    """Return JSON details for product quick view modal."""
    try:
        product = get_object_or_404(Product, id=product_id, is_listed=True)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Product not found or unavailable'}, status=404)

    images = [img.image.url for img in product.images.all() if img.image]
    if not images:
        images = ['/static/images/default-product.jpg']

    variants = product.variants.all()
    variant_data = []
    color_size_dict = {}
    unique_colors = []
    total_stock = 0

    for v in variants:
        total_stock += v.stock
        variant_data.append({
            'id': v.id,
            'color': v.color or '',
            'size': v.size,
            'stock': v.stock,
        })
        if v.color:
            if v.color not in color_size_dict:
                color_size_dict[v.color] = []
                unique_colors.append(v.color)
            if v.size not in color_size_dict[v.color]:
                color_size_dict[v.color].append(v.size)

    all_sizes = list(dict.fromkeys([v.size for v in variants]))

    has_offer = product.has_offer
    best_offer_price = float(product.best_offer_price) if has_offer and product.best_offer_price else None
    price = float(product.price)

    return JsonResponse({
        'success': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'description': product.description or 'No description available.',
            'category': product.category.category_name if product.category else '',
            'price': f"{price:.2f}",
            'has_offer': has_offer,
            'best_offer_price': f"{best_offer_price:.2f}" if best_offer_price else None,
            'best_offer_percentage': product.best_offer_percentage if has_offer else 0,
            'average_rating': round(float(product.average_rating), 1),
            'review_count': product.review_count,
            'images': images,
            'unique_colors': unique_colors,
            'color_size_dict': color_size_dict,
            'all_sizes': all_sizes,
            'variants': variant_data,
            'total_stock': total_stock,
            'detail_url': reverse('product_details', kwargs={'product_id': product.id}),
        }
    })

















# """
# PRODUCT DETAILS PAGE
# """
# def product_details(request, product_id):
#     product = get_object_or_404(Product, id=product_id)
    
#     # Get all variants that are in stock
#     variants = product.variants.filter(stock__gt=0)

#     # Calculate total stock
#     total_stock = sum(variant.stock for variant in variants)
    
#     # Get unique colors and sizes
#     unique_colors = variants.values_list('color', flat=True).distinct()
    
#     # Create a dictionary with colors as keys and their available sizes as values
#     color_size_dict = {}
#     for color in unique_colors:
#         color_size_dict[color] = list(variants.filter(color=color).values_list('size', flat=True).distinct())

#     product_images = product.images.all()  # Fetch all images related to the product
#     related_products = Product.objects.filter(category=product.category).exclude(id=product_id)
    
#     # Randomly select 4 related products
#     related_products = random.sample(list(related_products), min(len(related_products), 5))


#     can_review = False
#     if request.user.is_authenticated:
#         can_review = Review.can_review(request.user, product)

#     context = {
#         'product': product,
#         'unique_colors': unique_colors,
#         'color_size_dict': json.dumps(color_size_dict),  # Convert to JSON string
#         'product_images': product_images,
#         'related_products': related_products,
#         'variants':variants,
#         'total_stock':total_stock,
#         'can_review': can_review,
        
#     }
#     return render(request, 'user/product_details.html', context)







# """
# STOCK CHECKING WHEN ADDING TO CART/CHECKOUT
# """
# def check_stock(request):
#     if request.method == "POST":
#         color = request.POST.get('color')
#         size = request.POST.get('size')
#         variants = ProductVariant.objects.filter(product__is_listed=True)
#         variant_data = [{'color': variant.color, 'size': variant.size, 'stock': variant.stock} for variant in variants]
#         return JsonResponse({'variants': variant_data})
#     return JsonResponse({'error': 'Invalid request'}, status=400)