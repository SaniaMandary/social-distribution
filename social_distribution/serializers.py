from webbrowser import get

from rest_framework import serializers
from .models import Like, TextEntry

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TextEntry
        fields = ['id', 'belonging_url', 'entry_text', 'pub_date']

class AuthorSerializer(serializers.Serializer):
    url = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    picture = serializers.CharField()
    github = serializers.CharField()

class LikeSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "Like"

    def get_id(self, obj):
        return f"{obj.author.url}/likes/{obj.id}"

    class Meta:
        model = Like
        fields = ['type', 'author', 'published', 'id', 'object']