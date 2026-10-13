def navbar_counts(request):
    """
    Context processor to provide global cart and wishlist counts for the navbar.
    """
    cart_count = 0
    wishlist_count = 0
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            from cart.models import Cart
            user_cart = Cart.objects.filter(user=request.user).first()
            if user_cart:
                cart_count = user_cart.items.count()
        except Exception:
            cart_count = 0

        try:
            from wishlist.models import Wishlist
            user_wishlist = Wishlist.objects.filter(user=request.user).first()
            if user_wishlist:
                wishlist_count = user_wishlist.items.count()
        except Exception:
            wishlist_count = 0

    return {
        'nav_cart_count': cart_count,
        'nav_wishlist_count': wishlist_count,
    }
