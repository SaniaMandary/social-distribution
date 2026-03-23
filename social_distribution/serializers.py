from rest_framework import serializers
from .models import Like, TextEntry, Comment, Author, Follow
from .utils import (
    build_likes_object, build_comments_object, build_paginated_response,
)

class AuthorSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    displayName = serializers.CharField(source='name')
    profileImage = serializers.CharField(source='picture')
    host = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()

    class Meta:
        model = Author
        fields = ['type', 'id', 'host', 'displayName', 'github', 'profileImage', 'web']

    def get_type(self, obj):
        return "author"
        

    def get_host(self, obj):
        return obj.host

    def get_web(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f'/social_distribution/authors/{obj.username}')
        return f'{obj.host}/authors/{obj.username}'


class EntrySerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    author = AuthorSerializer(read_only=True)
    contentType = serializers.CharField(source='content_type')
    web = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()

    class Meta:
        model = TextEntry
        fields = ['type', 'id', 'web', 'title', 'description', 'contentType', 
              'content', 'image', 'author', 'comments', 'likes', 'published', 'visibility']

    def get_type(self, obj):
        return "entry"

    def get_id(self, obj):
        return obj.fqid

    def get_web(self, obj): 
        request = self.context.get('request')
        if request: 
            return request.build_absolute_uri(f'/social_distribution/authors/{obj.author.username}/entries/{obj.pk}')
        return f'{obj.author.host}/authors/{obj.author.username}/entries/{obj.pk}'

    def get_image(self, obj):
        if not obj.content_type.startswith('image/'):
            return None
        return f"{obj.fqid.rstrip('/')}/image/"
        
    def get_comments(self, obj):
        return build_comments_object(obj, self.context)
        
    def get_likes(self, obj): 
        web_url = self.get_web(obj)
        return build_likes_object(obj.fqid, web_url, self.context)


class LikeSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    author = AuthorSerializer(read_only=True)
    object = serializers.URLField(source='object_url')

    class Meta:
        model = Like
        fields = ['type', 'author', 'published', 'id', 'object']

    def get_type(self, obj):
        return "like"

    def get_id(self, obj):
        return obj.fqid


class CommentSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    author = AuthorSerializer(read_only=True)
    contentType = serializers.CharField(source='content_type')
    likes = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['type', 'author', 'comment', 'contentType', 'published', 'id', 'entry', 'web', 'likes']

    def get_type(self, obj):
        return "comment"

    def get_id(self, obj):
        return obj.fqid

    def get_web(self, obj):
        # Could be the entry page or a dedicated comment page
        request = self.context.get('request')
        if request:
            # Default to the entry page
            return request.build_absolute_uri(f'/social_distribution/authors/{obj.author.username}/comments/{obj.pk}')
        return f'{obj.author.host}authors/{obj.author.username}/comments/{obj.pk}'


    def get_likes(self, obj):
        web_url = f"{obj.author.host}authors/{obj.author.username}/comments/{obj.pk}/likes"
        return build_likes_object(obj.fqid, web_url, self.context)



class FollowSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    actor = serializers.SerializerMethodField()
    object = serializers.SerializerMethodField()

    class Meta:
        model = Follow
        fields = ['type', 'summary', 'actor', 'object']

    def get_type(self, obj):
        return "follow"

    def get_summary(self, obj):
        return f"{obj.follower.name} wants to follow {obj.following.name}"

    def get_actor(self, obj):
        return AuthorSerializer(obj.follower, context=self.context).data

    def get_object(self, obj):
        return AuthorSerializer(obj.following, context=self.context).data