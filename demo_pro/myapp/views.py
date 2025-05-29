from django.shortcuts import render

# Create your views here.

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Plan, Subscription, Invoice
from .serializers import (
    PlanSerializer,
    SubscriptionSerializer,
    SubscriptionCreateSerializer,
    InvoiceSerializer
)
from .tasks import create_invoice_for_subscription
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

