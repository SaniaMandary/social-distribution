from rest_framework import serializers
from .models import Like, TextEntry

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TextEntry
        fields = ['id', 'belonging_url', 'entry_text', 'pub_date']

class LikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Like
        fields = ['liked_object', 'author', 'timestamp']