from rest_framework import serializers
from .models import Like, TextEntry, Comment, Author


class AuthorSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    displayName = serializers.CharField(source='name')
    profileImage = serializers.CharField(source='picture')
    host = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()

    class Meta:
        model = Author
        fields = ['type', 'id', 'host', 'displayName', 'github', 'profileImage', 'web', 'url']

    def get_type(self, obj):
        return "author"

    def get_id(self, obj):
        return obj.fqid

    def get_host(self, obj):
        return f"{obj.host}/social_distribution/api/"

    def get_web(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f'/social_distribution/profiles/{obj.url}')
        return f'/social_distribution/profiles/{obj.url}'


class EntrySerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()

    class Meta:
        model = TextEntry
        fields = ['type', 'id', 'belonging_url', 'entry_text', 'pub_date', 'content_type', 'visibility', 'image']

    def get_type(self, obj):
        return "entry"

    def get_id(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(
                f'/social_distribution/api/authors/{obj.belonging_url}/entries/{obj.id}'
            )
        return f'/social_distribution/api/authors/{obj.belonging_url}/entries/{obj.id}'


class LikeSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()

    class Meta:
        model = Like
        fields = ['type', 'author', 'published', 'id', 'object']

    def get_type(self, obj):
        return "Like"

    def get_id(self, obj):
        return f"{obj.author.fqid}/liked/{obj.id}"


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
        return f"{obj.author.fqid}/commented/{obj.id}"

    def get_author(self, obj):
        return {
            "type": "author",
            "id": obj.author.fqid,
            "displayName": obj.author.name,
            "url": obj.author.url,
            "host": f"{obj.author.host}/social_distribution/api/",
        }

    def get_published(self, obj):
        return obj.created_at.isoformat()