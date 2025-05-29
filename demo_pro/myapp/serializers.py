from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Plan, Subscription, Invoice

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = '__all__'

class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = '__all__'

class SubscriptionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['plan']

class InvoiceSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    plan = PlanSerializer(read_only=True)
    subscription = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'