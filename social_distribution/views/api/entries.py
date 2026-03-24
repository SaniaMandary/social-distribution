import base64
 
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
 
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
 
from ...models import TextEntry, Author, Follow
from ...serializers import EntrySerializer
from ...utils import (
    NOT_DELETED, get_current_author, friends, can_view_entry,
    authenticate_remote_node, send_entry_to_followers,
    get_page_args, paginate_set, build_paginated_response,
)

ALLOWED_TEXT_CONTENT_TYPES = {'text/plain', 'text/markdown'}
ALLOWED_IMAGE_CONTENT_TYPES = {'image/png;base64', 'image/jpeg;base64', 'application/base64'}


def build_entry_image_url(entry):
    if not entry.content_type.startswith('image/'):
        return ''
    return f"{entry.fqid.rstrip('/')}/image/"


def validate_entry_content_payload(content_type, content):
    ct = (content_type or '').strip()
    if not ct:
        return "Missing contentType."

    if ct in ALLOWED_IMAGE_CONTENT_TYPES:
        if not isinstance(content, str) or not content.strip():
            return "Image content must be a non-empty base64 string."
        try:
            base64.b64decode(content, validate=True)
        except Exception:
            return "Invalid base64 image payload."
        return None

    if ct not in ALLOWED_TEXT_CONTENT_TYPES:
        return f"Unsupported contentType: {ct}"

    return None


@api_view(['GET'])
def get_entries(request):
    """
    Get the list of entries on our node
    """
    entries = TextEntry.objects.filter(NOT_DELETED).order_by('-published')
    page, size, = get_page_args(request)
    total = entries.count()
    page_data = paginate_set(entries, page, size)
    serializer = EntrySerializer(page_data, many=True, context={'request': request})
    return Response(build_paginated_response("entries", "src", serializer.data, page, size, total))


@csrf_exempt
@api_view(['GET', 'POST'])
def api_author_entries(request, author_serial):
    target_author = get_object_or_404(Author, serial=author_serial)

    if request.method == 'GET':
        remote_node = authenticate_remote_node(request)

        if remote_node:
            # Remote node: only public entries
            entries = TextEntry.objects.filter(
                author=target_author, visibility="PUBLIC"
            ).filter(NOT_DELETED).order_by("-published")
        elif not request.user.is_authenticated:
            entries = TextEntry.objects.filter(
                author=target_author, visibility="PUBLIC"
            ).filter(NOT_DELETED).order_by("-published")
        elif request.user.username == target_author.username:
            # Own entries: see everything
            entries = TextEntry.objects.filter(
                author=target_author
            ).filter(NOT_DELETED).order_by("-published")
        else:
            viewer = get_current_author(request)
            if friends(target_author, viewer):
                entries = TextEntry.objects.filter(
                    author=target_author
                ).filter(NOT_DELETED).order_by("-published")
            elif Follow.objects.filter(follower=viewer, following=target_author, approved=True).exists():
                entries = TextEntry.objects.filter(
                    author=target_author, visibility__in=["PUBLIC", "UNLISTED"]
                ).filter(NOT_DELETED).order_by("-published")
            else:
                entries = TextEntry.objects.filter(
                    author=target_author, visibility="PUBLIC"
                ).filter(NOT_DELETED).order_by("-published")
                
        page, size = get_page_args(request)
        total = entries.count()
        page_data = paginate_set(entries, page, size)
        serializer = EntrySerializer(page_data, many=True, context={'request': request})
        return Response(build_paginated_response("entries", "src", serializer.data, page, size, total))

    # POST — create entry as this author
    if not request.user.is_authenticated or request.user.username != target_author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    author = get_current_author(request)
    title = request.data.get('title', '')
    content = request.data.get('content', '')
    description = request.data.get('description', '')
    content_type = request.data.get('contentType', 'text/plain')
    visibility = request.data.get('visibility', 'PUBLIC')

    payload_error = validate_entry_content_payload(content_type, content)
    if payload_error:
        return Response({"error": payload_error}, status=400)

    if not title.strip():
        if content_type.startswith('image/'):
            title = 'Image post'
        else:
            title = content[:80] + ('...' if len(content) > 80 else '')

    entry = TextEntry.objects.create(
        author=author, title=title, description=description,
        content=content, content_type=content_type,
        visibility=visibility, source_type='native',
    )
    send_entry_to_followers(entry, request)

    return Response(EntrySerializer(entry, context={'request': request}).data, status=201)


@csrf_exempt
@api_view(['GET', 'PUT', 'DELETE'])
def api_author_entry_detail(request, author_serial, entry_serial):
    target_author = get_object_or_404(Author, serial=author_serial)
    entry = get_object_or_404(TextEntry, pk=entry_serial, author=target_author)

    if request.method == 'GET':
        if not can_view_entry(request, entry):
            return Response({"error": "Entry not accessible."}, status=404)
        return Response(EntrySerializer(entry, context={'request': request}).data)

    if not request.user.is_authenticated or request.user.username != target_author.username:
        return Response({"error": "Must be authenticated as this author."}, status=403)

    if request.method == 'PUT':
        if entry.is_deleted:
            return Response({"error": "Cannot edit a deleted entry."}, status=404)

        next_content = request.data.get('content', entry.content)
        next_content_type = request.data.get('contentType', entry.content_type)
        payload_error = validate_entry_content_payload(next_content_type, next_content)
        if payload_error:
            return Response({"error": payload_error}, status=400)
        
        if 'title' in request.data:       entry.title = request.data['title']
        entry.content = next_content
        if 'description' in request.data: entry.description = request.data['description']
        entry.content_type = next_content_type
        if 'visibility' in request.data:
            vis = request.data['visibility']
            if vis in ['PUBLIC', 'FRIENDS', 'UNLISTED']: entry.visibility = vis
        entry.save()
        send_entry_to_followers(entry, request)
        return Response(EntrySerializer(entry, context={'request': request}).data)

    if request.method == 'DELETE':
        if entry.is_deleted:
            return Response({"error": "Already deleted."}, status=404)
        entry.visibility = 'DELETED'
        entry.save()
        send_entry_to_followers(entry, request)
        return Response({"success": True, "message": "Entry deleted."}, status=200)


@api_view(['GET'])
def api_entry_image(request, author_serial, entry_serial):
    target_author = get_object_or_404(Author, serial=author_serial)
    entry = get_object_or_404(TextEntry, pk=entry_serial, author=target_author) 

    # return 404 if this entry is not an image or not viewable
    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible"}, status=404)

    if not entry.content_type.startswith('image/'):
        return Response({"error": "Not an image entry."}, status=404)

    try:
        image_bytes = base64.b64decode(entry.content)
        mime = entry.content_type.replace(';base64', '')
        return HttpResponse(image_bytes, content_type=mime)
    except Exception:
        return Response({"error": "Could not decode image."}, status=500)



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
def api_entry_fqid_image(request, entry_fqid):
    """GET /api/entries/{ENTRY_FQID}/image/ — serve image entry as binary by full URL."""
    entry = TextEntry.objects.filter(remote_fqid=entry_fqid).first()
    if not entry:
        try:
            pk = int(entry_fqid.rstrip('/').rsplit('/', 1)[-1])
            entry = TextEntry.objects.filter(pk=pk, remote_fqid='').first()
            if entry and entry.fqid != entry_fqid:
                entry = None
        except (ValueError, IndexError):
            entry = None
    if not entry:
        return Response({"error": "Entry not found."}, status=404)
    if not can_view_entry(request, entry):
        return Response({"error": "Entry not accessible."}, status=404)
    if not entry.content_type.startswith('image/') and entry.content_type != 'application/base64':
        return Response({"error": "Not an image entry."}, status=404)
    try:
        image_bytes = base64.b64decode(entry.content)
        mime = entry.content_type.replace(';base64', '')
        return HttpResponse(image_bytes, content_type=mime)
    except Exception:
        return Response({"error": "Could not decode image."}, status=500)