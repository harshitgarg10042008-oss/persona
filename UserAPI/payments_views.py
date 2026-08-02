"""
Razorpay payment integration for Premium plan purchases.

Endpoints:
  POST /auth/payments/create-order/  — creates a Razorpay Order, returns order_id
  POST /auth/payments/verify/        — verifies payment signature, grants Premium
"""
import hashlib
import hmac
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_razorpay_client():
    """Create a Razorpay client using configured credentials."""
    try:
        import razorpay
    except ImportError:
        logger.error("Razorpay SDK not installed. Run 'pip install razorpay'")
        raise ImportError("Razorpay SDK not installed. Please contact support.")
        
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def _verify_payment_signature(razorpay_order_id, razorpay_payment_id, signature):
    """
    Verify the payment signature returned by Razorpay's frontend callback.

    The signature is: HMAC-SHA256(razorpay_order_id + '|' + razorpay_payment_id,
    RAZORPAY_KEY_SECRET)

    Returns True if the signature is valid.
    """
    key_secret = settings.RAZORPAY_KEY_SECRET
    generated_signature = hmac.new(
        key_secret.encode(),
        (str(razorpay_order_id) + '|' + str(razorpay_payment_id)).encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated_signature, signature)


# ─── Endpoints ──────────────────────────────────────────────────────────────

@login_required
@require_POST
def create_order(request):
    """
    Create a Razorpay Order for the requested plan.

    POST body (JSON):
      { "plan": "monthly" | "season_pass" | "annual" }

    Returns:
      { "order_id": "...", "amount": 49900, "currency": "INR", "key_id": "..." }
    """
    # ── 1. Parse JSON body ──
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        logger.error(f"create_order: Invalid JSON body from user {request.user.email}")
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    plan = body.get('plan', '').strip()
    logger.info(f"create_order: user={request.user.email}, plan={plan}")

    # ── 2. Validate plan ──
    if plan not in settings.PLAN_PRICING:
        logger.error(f"create_order: Unknown plan '{plan}' from user {request.user.email}")
        return JsonResponse({
            'error': f'Unknown plan: {plan}. Valid plans: {list(settings.PLAN_PRICING.keys())}'
        }, status=400)

    # ── 3. Check Razorpay credentials ──
    key_id = settings.RAZORPAY_KEY_ID
    key_secret = settings.RAZORPAY_KEY_SECRET

    if not key_id or not key_secret:
        logger.error(
            f"create_order: Razorpay credentials MISSING — "
            f"KEY_ID={'SET' if key_id else 'EMPTY'}, KEY_SECRET={'SET' if key_secret else 'EMPTY'}"
        )
        return JsonResponse({
            'error': 'Payment system is not configured. Please contact support.'
        }, status=503)

    # Check if credentials are still placeholders
    if 'xxxx' in key_id or 'xxxx' in key_secret:
        logger.error(
            f"create_order: Razorpay credentials are still PLACEHOLDER values — "
            f"KEY_ID starts with '{key_id[:10]}...', "
            f"Update .env with real test keys from dashboard.razorpay.com"
        )
        return JsonResponse({
            'error': 'Payment system is not yet configured with valid Razorpay keys. '
                     'Please contact support.',
            'config_error': True,
        }, status=503)

    # ── 4. Check if user is already on premium ──
    try:
        sub = request.user.subscription
        if sub.is_premium:
            return JsonResponse({
                'error': 'You are already on a Premium plan.',
                'already_premium': True,
            }, status=409)
    except Exception:
        pass  # No subscription record yet, that's fine

    plan_config = settings.PLAN_PRICING[plan]
    amount_paise = plan_config['amount']

    # ── 5. Create Razorpay order ──
    try:
        client = _get_razorpay_client()

        logger.info(
            f"create_order: Calling Razorpay API — "
            f"user={request.user.email}, plan={plan}, amount={amount_paise}, "
            f"key_id_prefix={key_id[:8]}..."
        )

        order = client.order.create({
            'amount': int(amount_paise),
            'currency': 'INR',
            'payment_capture': 1,  # auto-capture
        })
        order_id = order['id']
        logger.info(f"create_order: Razorpay returned order_id={order_id}")

        # ── 6. Create audit trail record ──
        from UserAPI.models import PaymentTransaction
        PaymentTransaction.objects.create(
            user=request.user,
            plan=plan,
            amount=amount_paise,
            razorpay_order_id=order_id,
            status='created',
        )

        return JsonResponse({
            'order_id': order_id,
            'amount': amount_paise,
            'currency': 'INR',
            'key_id': key_id,  # public key, safe to expose
            'plan': plan,
            'plan_label': plan_config['label'],
        })

    except ImportError as e:
        return JsonResponse({'error': str(e)}, status=500)
    except Exception as e:
        # Log the EXACT exception with full context for debugging
        error_type = type(e).__name__
        error_msg = str(e)
        logger.exception(
            f"create_order: Razorpay Order.create FAILED — "
            f"user={request.user.email}, plan={plan}, amount={amount_paise}, "
            f"error_type={error_type}, error_msg={error_msg}"
        )

        # Provide specific error messages based on exception type
        if 'invalid' in error_msg.lower() and 'key' in error_msg.lower():
            return JsonResponse({
                'error': 'Invalid Razorpay API credentials. Please update your keys in the .env file.',
                'config_error': True,
            }, status=500)
        elif 'unauthorized' in error_msg.lower() or 'authentication' in error_msg.lower():
            return JsonResponse({
                'error': 'Razorpay authentication failed. Please check your API keys.',
                'config_error': True,
            }, status=500)
        elif 'api_error' in error_type.lower():
            return JsonResponse({
                'error': f'Razorpay API error: {error_msg}',
            }, status=500)
        else:
            return JsonResponse({
                'error': f'Failed to create payment order: {error_msg}',
            }, status=500)


@csrf_exempt  # Razorpay's callback is a POST from their server
@require_POST
def verify_payment(request):
    """
    Verify a Razorpay payment and grant Premium access.

    POST body (JSON):
      {
        "razorpay_order_id": "order_...",
        "razorpay_payment_id": "pay_...",
        "razorpay_signature": "..."
      }
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        logger.error("verify_payment: Invalid JSON body")
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    razorpay_order_id = body.get('razorpay_order_id', '').strip()
    razorpay_payment_id = body.get('razorpay_payment_id', '').strip()
    signature = body.get('razorpay_signature', '').strip()

    if not (razorpay_order_id and razorpay_payment_id and signature):
        logger.warning(f"verify_payment: Missing fields — order_id={bool(razorpay_order_id)}, payment_id={bool(razorpay_payment_id)}, signature={bool(signature)}")
        return JsonResponse({
            'error': 'Missing required fields: razorpay_order_id, razorpay_payment_id, razorpay_signature'
        }, status=400)

    # Look up the transaction
    from UserAPI.models import PaymentTransaction
    try:
        transaction = PaymentTransaction.objects.get(
            razorpay_order_id=razorpay_order_id
        )
    except PaymentTransaction.DoesNotExist:
        logger.warning(f"verify_payment: Unknown order_id: {razorpay_order_id}")
        return JsonResponse({'error': 'Transaction not found'}, status=404)

    logger.info(
        f"verify_payment: Verifying order={razorpay_order_id}, "
        f"payment={razorpay_payment_id}, user={transaction.user.email}"
    )

    # Security: NEVER trust frontend without server-side signature verification
    if not _verify_payment_signature(razorpay_order_id, razorpay_payment_id, signature):
        transaction.status = 'failed'
        transaction.signature = signature[:10] + '...'  # partial, for log
        transaction.save()
        logger.warning(
            f"verify_payment: SIGNATURE VERIFICATION FAILED — "
            f"order={razorpay_order_id}, user={transaction.user.email}"
        )
        return JsonResponse({
            'error': 'Payment verification failed. Your payment could not be confirmed.',
            'verified': False,
        }, status=400)

    # Signature is valid — grant Premium
    plan = transaction.plan
    duration_days = settings.PLAN_PRICING[plan]['duration_days']

    # Activate premium
    from UserAPI.subscription import activate_premium_for_user
    success, message = activate_premium_for_user(
        transaction.user,
        duration_days=duration_days,
    )

    if not success:
        logger.error(f"verify_payment: Failed to activate premium: {message}")
        return JsonResponse({
            'error': 'Payment verified but failed to activate Premium. Contact support.',
            'verified': True,
        }, status=500)

    # Mark transaction as verified
    transaction.razorpay_payment_id = razorpay_payment_id
    transaction.signature = signature[:10] + '...'  # partial
    transaction.status = 'verified'
    transaction.verified_at = timezone.now()
    transaction.save()

    # Get the updated subscription
    sub = transaction.user.subscription
    expiry_date = sub.premium_expires_at.strftime('%B %d, %Y') if sub.premium_expires_at else 'lifetime'

    logger.info(
        f"verify_payment: SUCCESS — order={razorpay_order_id}, payment={razorpay_payment_id}, "
        f"user={transaction.user.email}, plan={plan}, expires={expiry_date}"
    )

    return JsonResponse({
        'verified': True,
        'success': True,
        'message': message,
        'plan': plan,
        'plan_label': settings.PLAN_PRICING[plan]['label'],
        'expires_at': expiry_date,
        'tier': 'premium',
    })
