import uuid
from django.db import models
from django.contrib.auth.models import User
from products.models import Product, ProductVariant
from coupons.models import Coupon, CouponUsage
from user_profile.models import Address, ShippingAddress
from django.utils import timezone

def generate_order_id():
    # ORD-20231025-USER123-ABC123
    date_part = timezone.now().strftime("%Y%m%d")  # Current date in YYYYMMDD format
    random_part = uuid.uuid4().hex[:6].upper()  # Random 6-character string
    return f"ORD-{date_part}-{random_part}"

class Order(models.Model):
    ORDER_STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
        ('returned', 'Returned')
    ]

    id = models.CharField(primary_key=True, max_length=50, default=generate_order_id, editable=False)  # Custom order ID
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    shipping_address = models.ForeignKey(ShippingAddress, on_delete=models.SET_NULL, null=True)
    payment_method = models.CharField(max_length=20)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=20, default='Pending')
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    discount_applied = models.BooleanField(default=False)
    discount_coupon_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    balance_refund = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) 
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='processing')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    retry_payment_attempts = models.PositiveIntegerField(default=0) 


    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"

    def update_order(self):
        order_items = self.items.all()
        if not order_items.exists():
            self.status = 'canceled'
            self.save()
            return

        final_states = ['delivered', 'canceled', 'return_requested', 'returned', 'return_denied']
        all_items_in_final_state = all(item.status in final_states for item in order_items)

        print(f"All items in final state: {all_items_in_final_state}")

        if all_items_in_final_state:
            canceled_count = sum(1 for item in order_items if item.status == 'canceled')
            delivered_count = sum(1 for item in order_items if item.status == 'delivered')
            returned_count = sum(1 for item in order_items if item.status == 'returned')
            total_items = len(order_items)

            print(f"Canceled items: {canceled_count}, Delivered items: {delivered_count}, Returned items: {returned_count}")

            if canceled_count == total_items:
                print("All items are either canceled or returned. Setting order status to 'canceled'.")
                self.status = 'canceled'
            elif canceled_count + returned_count == total_items and returned_count >= 1 and canceled_count >= 1:
                print("All items are either canceled or returned. Setting order status to 'canceled'.")
                self.status = 'canceled'
            elif returned_count == total_items:
                print("All items are returned. Setting order status to 'returned'.")
                self.status = 'returned'
            elif delivered_count == total_items:
                print("All items are delivered. Setting order status to 'completed'.")
                self.status = 'completed'
            else:
                print("Mixed final states. Setting order status to 'completed'.")
                self.status = 'completed' 
        else:
            print("Not all items are in final states. Setting order status to 'pending'.")
            self.status = 'pending'

        self.save(update_fields=['status'])
        print(f"Updated order status: {self.status}")

class OrderItem(models.Model):
    ORDER_ITEM_STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('order_placed', 'Order Placed'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out For Delivery'),
        ('delivered', 'Delivered'),
        ('canceled', 'Canceled'),
        ('return_requested', 'Return Requested'),
        ('returned', 'Returned'),
        ('return', 'Return'),
        ('return_denied', 'Return Denied'),
    ]

    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=ORDER_ITEM_STATUS_CHOICES, default='processing')
    cancel_reason = models.TextField(blank=True, null=True)
    return_reason = models.TextField(blank=True, null=True)
    return_requested_at = models.DateTimeField(blank=True, null=True)
    returned_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    final_offer_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    def can_update_status(self, new_status):
        allowed_transitions = {
            'processing': ['order_placed', 'shipped', 'canceled'],
            'order_placed': ['shipped', 'out_for_delivery', 'canceled'],
            'shipped': ['out_for_delivery', 'delivered', 'canceled'],
            'out_for_delivery': ['delivered', 'canceled'],
            'delivered': ['return_requested'],
            'canceled': [],
            'return_requested': ['return', 'returned', 'return_denied'],
            'return': ['returned'],
            'returned': [],
            'return_denied': [],
        }
        return new_status in allowed_transitions.get(self.status, [])

    def get_allowed_next_statuses(self):
        # Admin-actionable transitions (excluding user-only transitions like return_requested)
        allowed_transitions = {
            'processing': [
                ('order_placed', 'Order Placed'),
                ('shipped', 'Shipped'),
                ('canceled', 'Canceled')
            ],
            'order_placed': [
                ('shipped', 'Shipped'),
                ('out_for_delivery', 'Out For Delivery'),
                ('canceled', 'Canceled')
            ],
            'shipped': [
                ('out_for_delivery', 'Out For Delivery'),
                ('delivered', 'Delivered'),
                ('canceled', 'Canceled')
            ],
            'out_for_delivery': [
                ('delivered', 'Delivered'),
                ('canceled', 'Canceled')
            ],
            'delivered': [],
            'canceled': [],
            'return_requested': [
                ('return', 'Approve Return & Refund'),
                ('return_denied', 'Deny Return')
            ],
            'return': [
                ('returned', 'Mark as Returned')
            ],
            'returned': [],
            'return_denied': [],
        }
        return allowed_transitions.get(self.status, [])


