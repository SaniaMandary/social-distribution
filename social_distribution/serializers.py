from rest_framework import serializers
from .models import TextEntry

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TextEntry
        fields = ['id', 'entry_text', 'pub_date']