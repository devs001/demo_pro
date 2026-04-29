from django.shortcuts import render

# Create your views here.

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView

from .models import Plan, Subscription, Invoice
from .serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    SubscriptionCreateSerializer,
    InvoiceSerializer
)
from .tasks import create_invoice_for_subscription, verify_webhook, log, get_open_position, place_market_order, \
    place_sl_with_retry, QUANTITY
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

class PlanListView(generics.ListAPIView):
    """List all available subscription plans"""
    queryset = Plan.objects.filter(is_active=True)
    serializer_class = PlanSerializer
    permission_classes = []  # Allow unauthenticated access to view plans

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def subscribe_to_plan(request):
    """Subscribe user to a plan"""
    serializer = SubscriptionCreateSerializer(data=request.data)
    if serializer.is_valid():
        plan = serializer.validated_data['plan']
        user = request.user

        # Check if user already has an active subscription
        existing_subscription = Subscription.objects.filter(
            user=user,
            status='active'
        ).first()

        if existing_subscription:
            return Response(
                {'error': 'User already has an active subscription'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create subscription
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status='active',
            start_date=timezone.now()
        )

        # Create first invoice
        create_invoice_for_subscription.delay(str(subscription.id))

        return Response(
            SubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_subscription(request, subscription_id):
    """Cancel user's subscription"""
    subscription = get_object_or_404(
        Subscription,
        id=subscription_id,
        user=request.user
    )

    if subscription.status != 'active':
        return Response(
            {'error': 'Subscription is not active'},
            status=status.HTTP_400_BAD_REQUEST
        )

    subscription.cancel()

    return Response(
        {'message': 'Subscription cancelled successfully'},
        status=status.HTTP_200_OK
    )

class UserSubscriptionsView(generics.ListAPIView):
    """List user's subscriptions"""
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)

class UserInvoicesView(generics.ListAPIView):
    """List user's invoices"""
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invoice.objects.filter(user=self.request.user)

class WebhookView(APIView):
    """webhook from trading"""
    permission_classes = [AllowAny]
    authentication_classes = []  # disables session/token auth checks

    def get(self, request):
        print(f"Query params: {request.query_params}")
        if not verify_webhook(request):
            return Response({"error": "Unauthorized"}), 401

        data        = request.data
        signal_type = data.get("type")

        log.info(f"Signal received: {data}")

        # ----------------------------------------------------------
        # ENTRY SIGNAL
        # ----------------------------------------------------------
        if signal_type == "entry":
            side = data.get("side")  # "buy" ya "sell"

            # One trade rule
            if get_open_position():
                log.info("Entry ignored — position already open")
                return Response({"status": "ignored", "reason": "position already open"})

            # Market order
            order_result = place_market_order(side, QUANTITY)

            if not order_result.get("success"):
                log.error(f"Entry order failed: {order_result}")
                return Response({"status": "failed", "reason": "entry order failed"}), 500

            # Average fill price
            avg_fill_price = float(order_result["result"]["average_fill_price"])
            log.info(f"Entry filled @ avg price: {avg_fill_price}")

            # SL lagao
            place_sl_with_retry(side, avg_fill_price)

            return Response({"status": "ok", "fill_price": avg_fill_price})

        # ----------------------------------------------------------
        # EXIT SIGNAL
        # ----------------------------------------------------------
        elif signal_type == "exit":
            position = get_open_position()

            if not position:
                log.info("Exit signal — no open position, skipping")
                return Response({"status": "skipped", "reason": "no open position"})

            close_side = "sell" if float(position["size"]) > 0 else "buy"
            result     = place_market_order(close_side, QUANTITY)
            log.info(f"Position closed: {result}")

            return Response({"status": "closed"})

        else:
            log.warning(f"Unknown signal type: {signal_type}")
            return Response({"error": "Unknown signal type"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pay_invoice(request, invoice_id):
    """Mock payment processing for an invoice"""
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)

    if invoice.status != 'pending':
        return Response(
            {'error': 'Invoice is not pending payment'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=int(invoice.amount * 100),
            currency='inr',
            metadata={'invoice_id': str(invoice.id)}
        )

        # Mark invoice as paid
        invoice.mark_paid()

        return Response({
            'message': 'Payment successful',
            'invoice': InvoiceSerializer(invoice).data,
            'payment_intent_id': payment_intent.id
        }, status=status.HTTP_200_OK)

    except stripe.error.StripeError as e:
        return Response(
            {'error': f'Payment failed: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )

