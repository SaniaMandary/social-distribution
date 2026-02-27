from rest_framework import serializers
from .models import TextEntry

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TextEntry
        fields = ['id', 'belonging_url', 'entry_text', 'pub_date']