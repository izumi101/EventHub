from rest_framework import serializers
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'registration', 'stripe_payment_intent_id',
                  'amount', 'currency', 'status', 'created_at']
        read_only_fields = ['id', 'stripe_payment_intent_id', 'status', 'created_at']
