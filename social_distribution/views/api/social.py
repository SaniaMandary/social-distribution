import logging

from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from ...models import Like, TextEntry, Author, Follow, Comment
from ...serializers import (
    AuthorSerializer, LikeSerializer, CommentSerializer, FollowSerializer,
)
from ...utils import (
    NOT_DELETED, get_current_author, friends, can_view_entry,
    authenticate_remote_node, fetch_remote_author,
    send_like_to_inbox, send_like_to_followers,
    send_comment_to_inbox, send_comment_to_followers,
    send_follow_to_inbox,
    get_or_create_remote_author_from_fqid,
    get_page_args, paginate_set, build_paginated_response,
)


@csrf_exempt
@api_view(['GET', 'POST'])
def api_entry_likes(request, author_serial, entry_serial):
    target_author = get_object_or_404(Author, serial=author_serial)
    entry = get_object_or_404(TextEntry, pk=entry_serial, author=target_author)

    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible."}, status=404)

    if request.method == 'GET':
        page, size = get_page_args(request, default_size=50)
        likes_qs = Like.objects.filter(object_url=entry.fqid).order_by('-published')
        total = likes_qs.count()
        page_data = paginate_set(likes_qs, page, size)
        serializer = LikeSerializer(page_data, many=True, context={'request': request})
        result = build_paginated_response("likes", "src", serializer.data, page, size, total)
        result["id"] = f"{entry.fqid}/likes"
        result["web"] = request.build_absolute_uri(
            f'/social_distribution/authors/{entry.author.username}/entries/{entry.pk}'
        ) if entry.author.is_local else entry.fqid
        return Response(result)

    if request.method == 'POST':
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required."}, status=403)

        liker = get_current_author(request)
        if entry.visibility == 'FRIENDS':
            if liker != entry.author and not friends(liker, entry.author):
                return Response({"error": "Only friends can like this entry."}, status=403)

        existing = Like.objects.filter(author=liker, object_url=entry.fqid).first()
        if existing:
            existing.delete()
            return Response({"success": True, "liked": False})

        like = Like.objects.create(author=liker, object_url=entry.fqid)
        send_like_to_inbox(like, entry.author, request)
        send_like_to_followers(like, entry, request)
        return Response({"success": True, "liked": True}, status=201)

@csrf_exempt
@api_view(['GET', 'POST'])
def api_comment_likes(request, author_serial, entry_serial, comment_fqid):
    target_author = get_object_or_404(Author, serial=author_serial)
    entry = get_object_or_404(TextEntry, pk=entry_serial, author=target_author)

    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible."}, status=404)

    for comment in Comment.objects.filter(local_entry=entry):
        if comment.fqid == comment_fqid:
            if request.method == 'GET':
                page, size = get_page_args(request, default_size=50)
                likes_qs = Like.objects.filter(object_url=comment.fqid).order_by('-published')
                total = likes_qs.count()
                page_data = paginate_set(likes_qs, page, size)
                serializer = LikeSerializer(page_data, many=True, context={'request': request})
                result = build_paginated_response("likes", "src", serializer.data, page, size, total)
                result["id"] = f"{comment.fqid}/likes"
                result["web"] = f"{comment.fqid}/likes"
                return Response(result)

            # CHANGED: POST — toggle like on comment (local)
            if request.method == 'POST':
                if not request.user.is_authenticated:
                    return Response({"error": "Authentication required."}, status=403)

                liker = get_current_author(request)
                if entry.visibility == 'FRIENDS':
                    if liker != entry.author and not friends(liker, entry.author):
                        return Response({"error": "Only friends can like this comment."}, status=403)

                existing = Like.objects.filter(author=liker, object_url=comment.fqid).first()
                if existing:
                    existing.delete()
                    return Response({"success": True, "liked": False})

                like = Like.objects.create(author=liker, object_url=comment.fqid)
                send_like_to_inbox(like, entry.author, request)
                send_like_to_followers(like, entry, request)
                return Response({"success": True, "liked": True}, status=201)

    return Response({"error": "Comment not found."}, status=404)


@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def api_inbox(request, author_serial):
    # authenticate remote node 
    remote_node = authenticate_remote_node(request) 
    if not remote_node:
        return Response({"error": "Remote node authentication required."}, status=401)

    author = get_object_or_404(Author, serial=author_serial)
    obj_type = request.data.get('type', '').lower()

    if obj_type == 'follow':
        actor = fetch_remote_author(request.data.get('actor', {}))
        if not actor:
            return Response({"error": "Missing actor id."}, status=400)
        Follow.objects.get_or_create(follower=actor, following=author, defaults={"approved": False})
        return Response({"success": True}, status=201)


    elif obj_type == 'entry':
        remote_author = fetch_remote_author(request.data.get('author', {}))
        if not remote_author:
            return Response({"error": "Missing author id."}, status=400)
        
        entry_fqid = request.data.get('id', '')
        visibility = request.data.get('visibility', 'PUBLIC')
        
        if visibility == 'DELETED':
            if entry_fqid: 
                TextEntry.objects.filter(remote_fqid=entry_fqid).update(visibility='DELETED')
            else: 
                TextEntry.objects.filter(author=remote_author).update(visibility='DELETED')
            return Response({"success": True}, status=200)

        if not entry_fqid: 
            return Response({"error": "Missing entry id (FQID)."}, status=400)

        TextEntry.objects.update_or_create(
            remote_fqid = entry_fqid,
            defaults={
                'author': remote_author,
                'title': request.data.get('title', ''),
                'description': request.data.get('description', ''),
                'content': request.data.get('content', ''),
                'content_type': request.data.get('contentType', 'text/plain'),
                'visibility': visibility,
            })
        return Response({"success": True}, status=201)


    elif obj_type == 'like':
        liker = fetch_remote_author(request.data.get('author', {}))
        if not liker:
            return Response({"error": "Missing author id."}, status=400)
        object_url = request.data.get('object', '')
        Like.objects.get_or_create(author=liker, object_url=object_url)
        return Response({"success": True}, status=201)

    elif obj_type == 'comment':
        commenter = fetch_remote_author(request.data.get('author', {}))
        if not commenter:
            return Response({"error": "Missing author id."}, status=400)

        entry_fqid = request.data.get('entry', '')
        comment_fqid = request.data.get('id', '')

        # Find the local entry this comment belongs to (if we have it)
        local_entry = None
        for e in TextEntry.objects.filter(NOT_DELETED):
            if e.fqid == entry_fqid:
                local_entry = e
                break

        # Deduplicate by remote FQID to avoid duplicate delivery
        if comment_fqid:
            _, created = Comment.objects.get_or_create(
                remote_fqid=comment_fqid,
                defaults={
                    'author': commenter,
                    'entry': entry_fqid,
                    'local_entry': local_entry,
                    'comment': request.data.get('comment', ''),
                    'content_type': request.data.get('contentType', 'text/markdown'),
                }
            )
            return Response({"success": True}, status=201 if created else 200)
        else:
            Comment.objects.create(
                author=commenter,
                entry=entry_fqid,
                local_entry=local_entry,
                comment=request.data.get('comment', ''),
                content_type=request.data.get('contentType', 'text/markdown'),
            )
            return Response({"success": True}, status=201)

    return Response({"error": f"Unknown type: {obj_type}"}, status=400)




@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def api_authors(request):
    page, size = get_page_args(request)
    all_authors = Author.objects.filter(is_local=True, is_approved=True).order_by('serial')
    total = all_authors.count()
    page_data = paginate_set(all_authors, page, size)
    serializer = AuthorSerializer(page_data, many=True, context={'request': request})
    return Response(build_paginated_response("authors", "authors", serializer.data, page, size, total))

@csrf_exempt
@authentication_classes([])
@permission_classes([])
@api_view(['GET', 'PUT'])
def api_single_author(request, author_serial):
    author = get_object_or_404(Author, serial=author_serial)

    if request.method == 'GET':
        return Response(AuthorSerializer(author, context={'request': request}).data)

    if not request.user.is_authenticated or request.user.username != author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    if 'displayName' in request.data:
        author.name = request.data['displayName']
    if 'github' in request.data:
        author.github = request.data['github']
    if 'profileImage' in request.data:
        author.picture = request.data['profileImage']
    author.save()
    return Response(AuthorSerializer(author, context={'request': request}).data)

@api_view(['GET'])
def api_single_author_fqid(request, author_fqid):
    """
    GET /api/authors/{AUTHOR_FQID}/ — remote FQID-based author lookup.
    Used by remote nodes to retrieve an author by their full URL ID.
    """
    author = Author.objects.filter(id=author_fqid).first()
    if not author:
        return Response({"error": "Author not found."}, status=404)
    return Response(AuthorSerializer(author, context={'request': request}).data)



@api_view(['GET'])
def api_author_followers(request, author_serial):
    author = get_object_or_404(Author, serial=author_serial)
    follows = Follow.objects.filter(following=author, approved=True).select_related('follower')
    serializer = AuthorSerializer([f.follower for f in follows], many=True, context={'request': request})
    return Response({"type": "followers", "followers": serializer.data})

@csrf_exempt
@api_view(['GET', 'PUT', 'DELETE'])
def api_author_follower_detail(request, author_serial, foreign_author_fqid):
    author = get_object_or_404(Author, serial=author_serial)

    if request.method == 'GET':
        follow = Follow.objects.filter(follower__id=foreign_author_fqid, following=author, approved=True).select_related('follower').first()
        if not follow:
            return Response({"error": "Not a follower."}, status=404)
        return Response(AuthorSerializer(follow.follower, context={'request': request}).data)

    if not request.user.is_authenticated or request.user.username != author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    if request.method == 'PUT':
        follow = Follow.objects.filter(follower__id=foreign_author_fqid, following=author).first()
        if not follow:
            return Response({"error": "No matching follow request."}, status=404)
        follow.approved = True
        follow.save()
        return Response(AuthorSerializer(follow.follower, context={'request': request}).data)

    if request.method == 'DELETE':
        deleted_count, _ = Follow.objects.filter(
            follower__id=foreign_author_fqid, following=author
        ).delete()
        if deleted_count == 0:
            return Response({"error": "No matching follow request or follower."}, status=404)
        return Response({"success": True}, status=200)



@api_view(['GET'])
def api_author_following(request, author_serial):
    author = get_object_or_404(Author, serial=author_serial)
    follows = Follow.objects.filter(follower=author, approved=True).select_related('following')
    serializer = AuthorSerializer([f.following for f in follows], many=True, context={'request': request})
    return Response({"type": "following", "following": serializer.data})

@csrf_exempt
@api_view(['GET', 'PUT', 'DELETE'])
def api_author_following_detail(request, author_serial, foreign_author_fqid):
    
    author = get_object_or_404(Author, serial=author_serial)

    if request.method == 'GET':
        # GET is local — check if author_serial is following foreign_author_fqid
        if not request.user.is_authenticated or request.user.username != author.username:
            return Response({"error": "Must be authenticated as this author."}, status=403)
        exists = Follow.objects.filter(
            follower=author, following__id=foreign_author_fqid, approved=True
        ).exists()
        if not exists:
            return Response({"error": "Not following."}, status=404)
        target = Author.objects.get(id=foreign_author_fqid)
        return Response(AuthorSerializer(target, context={'request': request}).data)

    # PUT and DELETE require auth
    if not request.user.is_authenticated or request.user.username != author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    if request.method == 'PUT':
        try:
            target = Author.objects.get(id=foreign_author_fqid)
        except Author.DoesNotExist:
            target = get_or_create_remote_author_from_fqid(foreign_author_fqid)
            if not target:
                return Response({"error": "Target author not found."}, status=404)
        follow, created = Follow.objects.get_or_create(
            follower=author, following=target,
            defaults={"approved": False}
        )
        if created and not target.is_local:
            send_follow_to_inbox(follow, request)
        return Response(FollowSerializer(follow, context={'request': request}).data, status=201 if created else 200)

    if request.method == 'DELETE':
        deleted_count, _ = Follow.objects.filter(
            follower=author, following__id=foreign_author_fqid
        ).delete()
        if deleted_count == 0:
            return Response({"error": "Not following."}, status=404)
        return Response({"success": True}, status=200)


@csrf_exempt
@api_view(['GET', 'POST'])
def api_author_commented(request, author_serial):
    author = get_object_or_404(Author, serial=author_serial)

    if request.method == 'GET':
        page, size = get_page_args(request, default_size=5)
        comments_qs = Comment.objects.filter(author=author).order_by('-published')
        total = comments_qs.count()
        page_data = paginate_set(comments_qs, page, size)
        serializer = CommentSerializer(page_data, many=True, context={'request': request})
        result = build_paginated_response("comments", "src", serializer.data, page, size, total)
        result["id"] = f"{author.fqid}/commented"
        result["web"] = author.web or author.fqid
        return Response(result)

    if not request.user.is_authenticated or request.user.username != author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    entry_fqid = request.data.get('entry', '')
    comment_text = request.data.get('comment', '').strip()
    content_type = request.data.get('contentType', 'text/markdown')

    if not comment_text: return Response({"error": "Missing comment content."}, status=400)
    if not entry_fqid:   return Response({"error": "Missing entry field."}, status=400)

    local_entry = TextEntry.objects.filter(remote_fqid=entry_fqid).filter(NOT_DELETED).first()
    if not local_entry:
        # Try matching a local entry whose fqid equals entry_fqid
        try:
            pk = int(entry_fqid.rstrip('/').rsplit('/', 1)[-1])
            candidate = TextEntry.objects.filter(pk=pk, remote_fqid='').filter(NOT_DELETED).first()
            if candidate and candidate.fqid == entry_fqid:
                local_entry = candidate
        except (ValueError, IndexError):
            pass

    comment = Comment.objects.create(
        author=author, entry=entry_fqid, local_entry=local_entry,
        comment=comment_text, content_type=content_type,
    )

    if local_entry:
        send_comment_to_inbox(comment, local_entry.author, request)
    else:
        # Remote entry: find the author from the entry FQID prefix using DB lookup
        remote_author = Author.objects.filter(is_local=False).filter(
            id__in=[a.id for a in Author.objects.filter(is_local=False) if entry_fqid.startswith(a.fqid)]
        ).first()
        # Parse the author portion from the FQID directly
        if not remote_author:
            # FQID: http://node/api/authors/{serial}/entries/{id}
            # strip /entries/{id} to get author FQID
            parts = entry_fqid.rstrip('/').rsplit('/entries/', 1)
            if len(parts) == 2:
                author_fqid = parts[0]
                remote_author = Author.objects.filter(id=author_fqid).first()
        if remote_author:
            send_comment_to_inbox(comment, remote_author, request)

    return Response(CommentSerializer(comment, context={'request': request}).data, status=201)


@api_view(['GET'])
def api_author_comment_by_serial(request, author_serial, comment_serial):
    author = get_object_or_404(Author, serial=author_serial)
    comment = get_object_or_404(Comment, pk=comment_serial, author=author)
    return Response(CommentSerializer(comment, context={'request': request}).data)


@api_view(['GET']) 
def api_follow_requests(request, author_serial):
    if not request.user.is_authenticated:
        return Response({"error": "Must be authenticated."}, status=403)

    author = get_object_or_404(Author, serial=author_serial)
    if request.user.username != author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    pending = Follow.objects.filter(following=author, approved=False)
    serializer = FollowSerializer(pending, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
def api_comment_fqid(request, comment_fqid):
    """GET /api/commented/{COMMENT_FQID}/ — retrieve comment by full URL."""
    # Check remote_fqid first
    comment = Comment.objects.filter(remote_fqid=comment_fqid).first()
    if not comment:
        # Try local: fqid looks like {author.id}/commented/{pk}
        try:
            pk = int(comment_fqid.rstrip('/').rsplit('/', 1)[-1])
            comment = Comment.objects.filter(pk=pk, remote_fqid='').first()
            if comment and comment.fqid != comment_fqid:
                comment = None
        except (ValueError, IndexError):
            comment = None
    if not comment:
        return Response({"error": "Comment not found."}, status=404)
    return Response(CommentSerializer(comment, context={'request': request}).data)

@api_view(['GET'])
def api_author_liked(request, author_serial):
    author = get_object_or_404(Author, serial=author_serial)
    page, size = get_page_args(request, default_size=50)
    likes_qs = Like.objects.filter(author=author).order_by('-published')
    total = likes_qs.count()
    page_data = paginate_set(likes_qs, page, size)
    serializer = LikeSerializer(page_data, many=True, context={'request': request})
    return Response(build_paginated_response("likes", "src", serializer.data, page, size, total))


@api_view(['GET'])
def api_author_like_by_serial(request, author_serial, like_serial):
    author = get_object_or_404(Author, serial=author_serial)
    like = get_object_or_404(Like, pk=like_serial, author=author)
    return Response(LikeSerializer(like, context={'request': request}).data)


@api_view(['GET'])
def api_like_fqid(request, like_fqid):
    """GET /api/liked/{LIKE_FQID}/ — retrieve like by full URL."""
    # Local fqid looks like {author.id}/liked/{pk}
    try:
        pk = int(like_fqid.rstrip('/').rsplit('/', 1)[-1])
        like = Like.objects.filter(pk=pk).first()
        if like and like.fqid != like_fqid:
            like = None
    except (ValueError, IndexError):
        like = None
    if not like:
        return Response({"error": "Like not found."}, status=404)
    return Response(LikeSerializer(like, context={'request': request}).data)

@api_view(['GET'])
def api_entry_fqid(request, entry_fqid):
    """GET /api/entries/{ENTRY_FQID}/ — retrieve entry by full URL."""
    # Try remote_fqid first (entries received from other nodes)
    entry = TextEntry.objects.filter(remote_fqid=entry_fqid).filter(NOT_DELETED).first()
    # Fall back to local entries whose constructed fqid matches
    if not entry:
        # Local fqid looks like: {author.id}/entries/{pk}
        # Extract pk from the tail
        try:
            pk = int(entry_fqid.rstrip('/').rsplit('/', 1)[-1])
            entry = TextEntry.objects.filter(pk=pk, remote_fqid='').filter(NOT_DELETED).first()
            if entry and entry.fqid != entry_fqid:
                entry = None
        except (ValueError, IndexError):
            entry = None
    if not entry:
        return Response({"error": "Entry not found."}, status=404)
    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible."}, status=404)
    return Response(EntrySerializer(entry, context={'request': request}).data)

@api_view(['GET'])
def api_entry_fqid_comments(request, entry_fqid):
    """GET /api/entries/{ENTRY_FQID}/comments/ — get comments for entry by full URL."""
    entry = TextEntry.objects.filter(remote_fqid=entry_fqid).filter(NOT_DELETED).first()
    if not entry:
        try:
            pk = int(entry_fqid.rstrip('/').rsplit('/', 1)[-1])
            entry = TextEntry.objects.filter(pk=pk, remote_fqid='').filter(NOT_DELETED).first()
            if entry and entry.fqid != entry_fqid:
                entry = None
        except (ValueError, IndexError):
            entry = None
    if not entry:
        return Response({"error": "Entry not found."}, status=404)
    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible."}, status=404)

    page, size = get_page_args(request, default_size=5)
    comments_qs = Comment.objects.filter(local_entry=entry).order_by('-published')
    total = comments_qs.count()
    page_data = paginate_set(comments_qs, page, size)
    serializer = CommentSerializer(page_data, many=True, context={'request': request})
    result = build_paginated_response("comments", "src", serializer.data, page, size, total)
    result["id"] = f"{entry.fqid}/comments"
    # web: frontend URL for the entry page (where comments are displayed)
    if entry.remote_fqid:
        result["web"] = entry.remote_fqid.replace('/api/authors/', '/authors/')
    else:
        result["web"] = request.build_absolute_uri(
            f'/social_distribution/authors/{entry.author.username}/entries/{entry.pk}'
        )
    return Response(result)


@api_view(['GET'])
def api_entry_fqid_likes(request, entry_fqid):
    """GET /api/entries/{ENTRY_FQID}/likes/ — get likes for entry by full URL."""
    entry = TextEntry.objects.filter(remote_fqid=entry_fqid).filter(NOT_DELETED).first()
    if not entry:
        try:
            pk = int(entry_fqid.rstrip('/').rsplit('/', 1)[-1])
            entry = TextEntry.objects.filter(pk=pk, remote_fqid='').filter(NOT_DELETED).first()
            if entry and entry.fqid != entry_fqid:
                entry = None
        except (ValueError, IndexError):
            entry = None
    if not entry:
        return Response({"error": "Entry not found."}, status=404)
    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible."}, status=404)

    page, size = get_page_args(request, default_size=50)
    likes_qs = Like.objects.filter(object_url=entry.fqid).order_by('-published')
    total = likes_qs.count()
    page_data = paginate_set(likes_qs, page, size)
    serializer = LikeSerializer(page_data, many=True, context={'request': request})
    result = build_paginated_response("likes", "src", serializer.data, page, size, total)
    result["id"] = f"{entry.fqid}/likes"
    if entry.remote_fqid:
        result["web"] = entry.remote_fqid.replace('/api/authors/', '/authors/')
    else:
        result["web"] = request.build_absolute_uri(
            f'/social_distribution/authors/{entry.author.username}/entries/{entry.pk}'
        )
    return Response(result)



@api_view(['GET'])
def api_author_liked_fqid(request, author_fqid):
    """GET /api/authors/{AUTHOR_FQID}/liked/ — list likes by a remote author (local [GET])."""
    author = Author.objects.filter(id=author_fqid).first()
    if not author:
        return Response({"error": "Author not found."}, status=404)
    page, size = get_page_args(request, default_size=50)
    likes_qs = Like.objects.filter(author=author).order_by('-published')
    total = likes_qs.count()
    page_data = paginate_set(likes_qs, page, size)
    serializer = LikeSerializer(page_data, many=True, context={'request': request})
    return Response(build_paginated_response("likes", "src", serializer.data, page, size, total))


@api_view(['GET'])
def api_author_commented_fqid(request, author_fqid):
    """GET /api/authors/{AUTHOR_FQID}/commented/ — list comments by a remote author (local [GET])."""
    author = Author.objects.filter(id=author_fqid).first()
    if not author:
        return Response({"error": "Author not found."}, status=404)
    page, size = get_page_args(request, default_size=5)
    comments_qs = Comment.objects.filter(author=author).order_by('-published')
    total = comments_qs.count()
    page_data = paginate_set(comments_qs, page, size)
    serializer = CommentSerializer(page_data, many=True, context={'request': request})
    result = build_paginated_response("comments", "src", serializer.data, page, size, total)
    result["id"] = f"{author_fqid}/commented"
    result["web"] = author.web or author_fqid
    return Response(result)

@csrf_exempt
@api_view(['GET', 'POST'])
def api_entry_comments(request, author_serial, entry_serial):
    target_author = get_object_or_404(Author, serial=author_serial)
    entry = get_object_or_404(TextEntry, pk=entry_serial, author=target_author)
    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible."}, status=404)

    if request.method == 'GET':
        page, size = get_page_args(request, default_size=5)
        comments_qs = Comment.objects.filter(local_entry=entry).order_by('-published')
        total = comments_qs.count()
        page_data = paginate_set(comments_qs, page, size)
        serializer = CommentSerializer(page_data, many=True, context={'request': request})
        result = build_paginated_response("comments", "src", serializer.data, page, size, total)
        result["id"] = f"{entry.fqid}/comments"
        result["web"] = request.build_absolute_uri(
            f'/social_distribution/authors/{entry.author.username}/entries/{entry.pk}'
            ) if entry.author.is_local else entry.remote_fqid.replace('/api/authors/', '/authors/')
        return Response(result)

    if not request.user.is_authenticated:
        return Response({"error": "Authentication required."}, status=403)
    commenter = get_current_author(request)
    if entry.visibility == 'FRIENDS':
        if commenter != entry.author and not friends(commenter, entry.author):
            return Response({"error": "Only friends can comment on this entry."}, status=403)
    comment_text = request.data.get('comment', '').strip()
    if not comment_text:
        return Response({"error": "Missing comment content."}, status=400)
    comment = Comment.objects.create(
        author=commenter, entry=entry.fqid, local_entry=entry,
        comment=comment_text, content_type=request.data.get('contentType', 'text/markdown'),
    )
    send_comment_to_inbox(comment, entry.author, request)
    send_comment_to_followers(comment, entry, request)
    return Response(CommentSerializer(comment, context={'request': request}).data, status=201)


@api_view(['GET'])
def api_entry_comment_detail(request, author_serial, entry_serial, comment_fqid):
    target_author = get_object_or_404(Author, serial=author_serial)
    entry = get_object_or_404(TextEntry, pk=entry_serial, author=target_author)
    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible."}, status=404)
    for comment in Comment.objects.filter(local_entry=entry):
        if comment.fqid == comment_fqid:
            return Response(CommentSerializer(comment, context={'request': request}).data)
    return Response({"error": "Comment not found."}, status=404)



