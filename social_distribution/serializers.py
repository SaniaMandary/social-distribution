from webbrowser import get

from rest_framework import serializers
from .models import Like, TextEntry, Comment

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

class CommentSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['type', 'author', 'comment', 'content_type', 'published', 'id', 'entry']

    def get_type(self, obj):
        return "comment"

    def get_id(self, obj):
        return f"{obj.author.url}/commented/{obj.id}"

    