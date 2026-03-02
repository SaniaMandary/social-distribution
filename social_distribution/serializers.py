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
    comment_id = serializers.IntegerField(source='id', read_only=True)
    author = serializers.SerializerMethodField()
    published = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['type', 'author', 'content', 'content_type', 'published', 'id', 'comment_id', 'entry']

    def get_type(self, obj):
        return "comment"

    def get_id(self, obj):
        return f"{obj.author.url}/commented/{obj.id}"
    
    def get_author(self, obj):
        return {
            "displayName": obj.author.name,
            "url": obj.author.url
        }
    
    def get_published(self, obj):
        return obj.created_at.isoformat()

    