from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from user_profile.models import Referral
from wallet.models import Wallet, WalletTransaction

"""
Create a referral code and wallet for users who sign up via Allauth (e.g. Google login).
"""
@receiver(user_signed_up)
def create_referral_code_for_user(request, user, **kwargs):
    referral, _ = Referral.objects.get_or_create(user=user)
    wallet, _ = Wallet.objects.get_or_create(user=user)

    # Process referral bonus if user signed up with a referral code
    if request:
        ref_code = (request.session.get('referral_code') or request.GET.get('ref', '')).strip()
        if ref_code and not referral.referred_by:
            try:
                referring_obj = Referral.objects.get(referral_code=ref_code)
                if referring_obj.user != user:
                    referral.referred_by = referring_obj.user
                    referral.save()

                    # Credit new user wallet bonus
                    wallet.balance += 50
                    wallet.save()
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        amount=50,
                        transaction_type='credit',
                        description='Referral bonus for new user'
                    )

                    # Credit referring user wallet bonus
                    ref_wallet, _ = Wallet.objects.get_or_create(user=referring_obj.user)
                    ref_wallet.balance += 100
                    ref_wallet.save()
                    WalletTransaction.objects.create(
                        wallet=ref_wallet,
                        amount=100,
                        transaction_type='credit',
                        description='Referral bonus for referring user'
                    )
                    request.session.pop('referral_code', None)
            except Referral.DoesNotExist:
                pass
    