from django.shortcuts import render
from django.db.models import Q, Count, Min, Max
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.cache import never_cache
from decimal import Decimal

from products.models import Product, ProductImage
from category.models import Category
from wishlist.models import WishlistItem


@never_cache
def all_products(request):
    """
    Enhanced shop catalogue view featuring responsive filtering,
    category pills, inventory tracking, wishlist state, and multi-option sorting.
    """
    # Fetch active categories with product counts
    categories = Category.objects.filter(is_listed=True).annotate(
        product_count=Count('product', filter=Q(product__is_listed=True))
    )

    # Base queryset for listed products
    products_qs = Product.objects.filter(
        is_listed=True,
        category__is_listed=True
    ).select_related('category').prefetch_related(
        'images', 'variants', 'review_set'
    )

    # Store price boundary defaults
    price_aggregate = products_qs.aggregate(min_p=Min('price'), max_p=Max('price'))
    store_min_price = price_aggregate.get('min_p') or Decimal('0.00')
    store_max_price = price_aggregate.get('max_p') or Decimal('10000.00')

    # 1. Search Query Filter
    search_query = request.GET.get('search', '').strip() or request.GET.get('q', '').strip()
    if search_query:
        products_qs = products_qs.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(category__category_name__icontains=search_query)
        ).distinct()

    # 2. Category Filter (Multiple categories support)
    selected_categories = request.GET.getlist('categories')
    selected_categories = [int(cat) for cat in selected_categories if str(cat).isdigit()]
    if selected_categories:
        products_qs = products_qs.filter(category_id__in=selected_categories)

    # 3. Price Range Filter
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()

    if min_price:
        try:
            min_val = Decimal(min_price)
            if min_val >= 0:
                products_qs = products_qs.filter(price__gte=min_val)
            else:
                min_price = ''
        except Exception:
            min_price = ''

    if max_price:
        try:
            max_val = Decimal(max_price)
            if max_val >= 0:
                products_qs = products_qs.filter(price__lte=max_val)
            else:
                max_price = ''
        except Exception:
            max_price = ''

    # 4. Sorting
    sort_option = request.GET.get('sort', 'featured').strip().lower()
    sort_map = {
        'newest': '-created_at',
        'price-asc': 'price',
        'price-desc': '-price',
        'name-asc': 'name',
        'name-desc': '-name',
        'featured': '-id',
    }
    products_qs = products_qs.order_by(sort_map.get(sort_option, '-id'))

    total_matching_products = products_qs.count()

    # 5. Pagination
    paginator = Paginator(products_qs, 12)
    page_num = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # 6. Current User Wishlist Product IDs
    user_wishlist_ids = set()
    if request.user.is_authenticated:
        user_wishlist_ids = set(
            WishlistItem.objects.filter(wishlist__user=request.user).values_list('product_id', flat=True)
        )

    # 7. Decorate products for template rendering
    decorated_products = []
    for product in page_obj.object_list:
        images_list = list(product.images.all())
        first_img = images_list[0] if len(images_list) > 0 else None
        second_img = images_list[1] if len(images_list) > 1 else None

        variants = list(product.variants.all())
        total_stock = sum(v.stock for v in variants) if variants else 0
        is_in_stock = total_stock > 0
        is_low_stock = 0 < total_stock <= 5

        color_variants = list(dict.fromkeys([v.color for v in variants if v.color]))
        size_variants = list(dict.fromkeys([v.size for v in variants if v.size]))

        decorated_products.append({
            'product': product,
            'first_image': first_img,
            'second_image': second_img,
            'total_stock': total_stock,
            'is_in_stock': is_in_stock,
            'is_low_stock': is_low_stock,
            'color_variants': color_variants,
            'size_variants': size_variants,
            'in_wishlist': product.id in user_wishlist_ids,
        })

    # 8. Active Filters Summary for visual chips
    active_filters = []
    if search_query:
        active_filters.append({'type': 'search', 'label': f'Search: "{search_query}"'})
    if selected_categories:
        cat_names = [c.category_name for c in categories if c.id in selected_categories]
        if cat_names:
            active_filters.append({'type': 'category', 'label': f'Collection: {", ".join(cat_names)}'})
    if min_price and max_price:
        active_filters.append({'type': 'price', 'label': f'₹{min_price} – ₹{max_price}'})
    elif min_price:
        active_filters.append({'type': 'min_price', 'label': f'Above ₹{min_price}'})
    elif max_price:
        active_filters.append({'type': 'max_price', 'label': f'Under ₹{max_price}'})

    context = {
        'products': decorated_products,
        'page_obj': page_obj,
        'categories': categories,
        'selected_categories': selected_categories,
        'search_query': search_query,
        'sort_option': sort_option,
        'min_price': min_price,
        'max_price': max_price,
        'store_min_price': store_min_price,
        'store_max_price': store_max_price,
        'total_matching_products': total_matching_products,
        'active_filters': active_filters,
        'has_active_filters': len(active_filters) > 0,
    }
    return render(request, 'user/shop.html', context)
